#!/usr/bin/env python3
"""Post-game commentary pipeline for Prismata replays.

Two-stage LLM pipeline:
  Stage 1 (Phase 2): Structured game analysis via Claude API
  Stage 2 (Phase 3): Narrative generation from analysis JSON

Usage:
    # Dry run (no API calls, shows assembled prompt + token estimate)
    python tools/generate_postgame_commentary.py FxCfR-K49T+ --dry-run

    # Run analysis stage only
    python tools/generate_postgame_commentary.py FxCfR-K49T+ --analyze-only

    # Full pipeline (analysis + narrative)
    python tools/generate_postgame_commentary.py FxCfR-K49T+

    # Single-pass comparison (bypass analysis, direct narrative)
    python tools/generate_postgame_commentary.py FxCfR-K49T+ --single-pass
"""
import argparse
import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(SCRIPT_DIR, "prompts")
ANALYSIS_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "analysis_system.md")
NARRATIVE_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "narrative_system.md")
BIN_DIR = os.path.join(SCRIPT_DIR, "..", "bin")
COMMENTARY_DIR = os.path.join(BIN_DIR, "commentary")

# Models
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-5-20241022"

# Token limits
ANALYSIS_MAX_TOKENS = 4096
NARRATIVE_MAX_TOKENS = 4096

# Input token soft cap — trim few-shot examples if exceeded
NARRATIVE_INPUT_SOFT_CAP = 10000
NARRATIVE_INPUT_HARD_CAP = 12000

# Discord message character limit
DISCORD_CHAR_LIMIT = 2000

# Retry config (matches discord_knowledge_extractor.py pattern)
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2


# ---------------------------------------------------------------------------
# Phase 1 integration — import from generate_commentary_data.py
# ---------------------------------------------------------------------------
def _get_phase1_data(code, think_time=50):
    """Get structured game data from Phase 1.

    Imports build_structured_output directly (clean __main__ guard, no side effects).
    Returns the complete structured dict.
    """
    # Add tools/ to path if needed for import
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)

    from generate_commentary_data import build_structured_output
    return build_structured_output(code, think_time=think_time)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def _load_analysis_system_prompt():
    """Load the analysis stage system prompt from markdown file."""
    with open(ANALYSIS_SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_analysis_messages(game_data, system_prompt_text):
    """Build the system + user messages for the analysis API call.

    Returns (system_messages, user_content) tuple.
    system_messages is a list of content blocks with cache_control on the static part.
    """
    # System prompt: static rules (cached) + dynamic unit knowledge
    unit_knowledge = game_data.get("unit_knowledge", {})
    unit_kb_lines = []
    for name, snippet in unit_knowledge.items():
        if name.startswith("_concept_"):
            concept = name.replace("_concept_", "").title()
            unit_kb_lines.append(f"**{concept}**: {snippet}")
        else:
            unit_kb_lines.append(f"**{name}**: {snippet}")

    unit_kb_text = "\n".join(unit_kb_lines) if unit_kb_lines else "(No unit knowledge available)"

    # System: static prompt (cacheable) + per-game unit knowledge
    system_messages = [
        {
            "type": "text",
            "text": system_prompt_text,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"## Unit Knowledge for This Game\n\n{unit_kb_text}",
        },
    ]

    # User message: game data
    # Include only the fields the LLM needs (not full turns array for analysis)
    players = game_data.get("players", [])
    winner = game_data.get("winner", -1)
    if 0 <= winner < len(players):
        winner_name = players[winner]["name"]
    else:
        winner_name = "Unknown"
    random_set = [u["name"] for u in game_data.get("random_set", [])]

    # Summarize per-turn data (only notable turns to save tokens)
    turns = game_data.get("turns", [])
    turn_summaries = []
    for t in turns:
        buys_str = ", ".join(t.get("buys", [])) or "(no buys)"
        line = f"Ply {t['ply']} (Round {t['round']}, {t['player_name']}): {buys_str}"

        # Add eval data if available
        if "eval_pct" in t:
            line += f" | eval={t['eval_pct']}%"
        if "eval_delta" in t:
            delta = t["eval_delta"]
            if abs(delta) > 3:
                line += f" (delta={delta:+.1f})"

        # Flag AI disagreement
        if t.get("ai_agrees") is False:
            ai_buys = ", ".join(t.get("ai_buys", []))
            line += f" [AI disagrees, would buy: {ai_buys}]"

        turn_summaries.append(line)

    # Game characteristics
    gc = game_data.get("game_characteristics", {})

    # Turning point candidates from Phase 1
    tp_candidates = game_data.get("precomputed", {}).get("turning_point_candidates", [])
    tp_text = json.dumps(tp_candidates, indent=2) if tp_candidates else "[]"

    # Data quality info
    dq = game_data.get("data_quality", {})

    user_content = f"""## Game Data

**Code:** {game_data.get('code', '?')}
**Players:** {players[0]['name']} ({players[0]['rating']}) vs {players[1]['name']} ({players[1]['rating']})
**Winner:** {winner_name} (player index {winner})
**Rounds:** {game_data.get('total_rounds', '?')}
**Length:** {gc.get('length_category', '?')}
**Upset:** {'Yes' if gc.get('is_upset') else 'No'} (rating diff: {gc.get('rating_diff', 0)})
**Random Set:** {', '.join(random_set)}

## Data Quality
- Eval data available: {dq.get('has_eval', False)}
- AI comparison available: {dq.get('has_ai', False)}
- Mode: {dq.get('mode', '?')}

## Turning Point Candidates (from game engine)
{tp_text}

## Per-Turn Data
{chr(10).join(turn_summaries)}

Analyze this game and return a JSON object following the output schema."""

    return system_messages, user_content


def _estimate_tokens(text):
    """Rough token estimate: ~4 chars per token for English text."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------
def _call_analysis_api(system_messages, user_content, model=MODEL_HAIKU,
                       max_tokens=ANALYSIS_MAX_TOKENS):
    """Make the Claude API call for game analysis.

    Returns the parsed JSON analysis dict, or None on failure.
    Uses retry with exponential backoff (pattern from discord_knowledge_extractor.py).
    """
    from anthropic import Anthropic

    client = Anthropic()

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_messages,
                messages=[{"role": "user", "content": user_content}],
            )
            if not response.content:
                raise ValueError(f"API returned empty content, stop={response.stop_reason}")
            raw_text = response.content[0].text.strip()

            # Track usage and stop reason
            usage = response.usage
            stop = response.stop_reason
            print(f"  API usage: input={usage.input_tokens}, output={usage.output_tokens}, "
                  f"stop={stop}, "
                  f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}, "
                  f"cache_creation={getattr(usage, 'cache_creation_input_tokens', 0)}",
                  file=sys.stderr)

            if stop == "max_tokens":
                print(f"  WARNING: Response truncated (hit max_tokens={max_tokens}). "
                      f"Output may be incomplete JSON.", file=sys.stderr)

            # Parse JSON from response (may be wrapped in ```json blocks or preceded by text)
            json_text = raw_text
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                json_text = "\n".join(lines)

            # Fallback: extract first JSON object if fence stripping didn't help
            if not json_text.lstrip().startswith("{"):
                match = re.search(r'\{[\s\S]*\}', json_text)
                if match:
                    json_text = match.group(0)

            analysis = json.loads(json_text)
            return analysis

        except json.JSONDecodeError as e:
            print(f"  WARNING: JSON parse error (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}",
                  file=sys.stderr)
            print(f"  Raw text (first 500 chars): {raw_text[:500]}", file=sys.stderr)
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                return None

        except Exception as e:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"  API error (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. "
                      f"Retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"  API error (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. "
                      f"Giving up.", file=sys.stderr)
                return None

    return None


# ---------------------------------------------------------------------------
# Programmatic verification (Phase 2c)
# ---------------------------------------------------------------------------
def verify_analysis(analysis, game_data):
    """Verify analysis JSON against Phase 1 game data.

    Returns a list of warning strings. Empty list = all checks passed.
    This is NOT an LLM call — just Python assertions.
    """
    warnings = []
    if not analysis:
        return ["Analysis is None or empty"]

    turns = game_data.get("turns", [])
    players = game_data.get("players", [])
    player_names = {p["name"] for p in players}
    total_rounds = game_data.get("total_rounds", 0)
    valid_plies = {t["ply"] for t in turns}

    # --- Basic referential checks ---

    # Check turning points reference valid plies
    for tp in analysis.get("turning_points", []):
        ply = tp.get("ply")
        if ply and ply not in valid_plies:
            warnings.append(f"Turning point references non-existent ply {ply}")

    # Check player names in assessments
    for pa in analysis.get("player_assessments", []):
        pname = pa.get("player", "")
        if pname and pname not in player_names:
            warnings.append(f"Player assessment references unknown player '{pname}'")

        # Check notable_plies exist
        for ply in pa.get("notable_plies", []):
            if ply not in valid_plies:
                warnings.append(f"Notable ply {ply} for {pname} doesn't exist in game data")

    # --- Structural checks ---

    # Phase round ranges should cover game and not overlap
    phases = analysis.get("phases", [])
    has_clear = analysis.get("has_clear_phases", False)
    if has_clear and phases:
        prev_end = 0
        for phase in phases:
            rounds = phase.get("rounds")
            if rounds and len(rounds) == 2 and rounds[0] is not None and rounds[1] is not None:
                start, end = rounds
                if start < 1:
                    warnings.append(f"Phase '{phase.get('name')}' starts at round {start} (should be >= 1)")
                if end > total_rounds:
                    warnings.append(f"Phase '{phase.get('name')}' ends at round {end} but game is {total_rounds} rounds")
                if start <= prev_end:
                    warnings.append(f"Phase '{phase.get('name')}' overlaps with previous (starts {start}, prev ended {prev_end})")
                prev_end = end

    # --- Eval-grounded checks (only if eval data available) ---
    dq = game_data.get("data_quality", {})
    if dq.get("has_eval"):
        turn_by_ply = {t["ply"]: t for t in turns}
        for tp in analysis.get("turning_points", []):
            ply = tp.get("ply")
            eval_before = tp.get("eval_before")
            eval_after = tp.get("eval_after")

            if ply and ply in turn_by_ply and eval_before is not None and eval_after is not None:
                actual = turn_by_ply[ply]
                actual_pct = actual.get("eval_pct")
                if actual_pct is not None:
                    # Check eval_after is within ±5% of actual
                    if abs(eval_after - actual_pct) > 5:
                        warnings.append(
                            f"Turning point ply {ply}: eval_after={eval_after} but actual eval={actual_pct}"
                        )

    # --- Purchase attribution checks (only if we have buy data) ---
    # Deferred to narrative verification (Phase 3) since analysis doesn't typically
    # make specific "Player X bought Y on turn Z" claims — that's narrative territory.

    return warnings


# ---------------------------------------------------------------------------
# Phase 3: Narrative generation
# ---------------------------------------------------------------------------
def _load_narrative_system_prompt():
    """Load the narrative stage system prompt from markdown file."""
    with open(NARRATIVE_SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _select_few_shot_examples(game_data):
    """Select 1-2 commentary file paths based on game characteristics.

    Returns list of file paths to existing commentary examples.
    """
    gc = game_data.get("game_characteristics", {})
    examples = []

    # Primary example — shortest high-quality, always included
    primary = os.path.join(COMMENTARY_DIR, "commentary_WjhmP-WWdXx.txt")
    if os.path.exists(primary):
        examples.append(primary)

    # Second example based on game characteristics
    if gc.get("is_upset") and gc.get("rating_diff", 0) > 200:
        secondary = os.path.join(COMMENTARY_DIR, "commentary_FxCfR-K49T+_full.txt")
    elif gc.get("length_category") == "long":
        secondary = os.path.join(COMMENTARY_DIR, "commentary_uP8mG-tr75d.txt")
    else:
        secondary = None

    if secondary and os.path.exists(secondary):
        examples.append(secondary)

    return examples


def _build_narrative_messages(analysis, game_data, few_shot_paths, system_prompt_text):
    """Build the system + user messages for the narrative API call.

    Returns (system_messages, user_content) tuple.
    Token budget management: drops second example, then truncates, then hard aborts.
    """
    players = game_data.get("players", [])
    winner = game_data.get("winner", -1)
    if 0 <= winner < len(players):
        winner_name = players[winner]["name"]
    else:
        winner_name = "Unknown"
    random_set = [u["name"] for u in game_data.get("random_set", [])]
    gc = game_data.get("game_characteristics", {})
    total_rounds = game_data.get("total_rounds", 0)

    # Target message count based on game length
    if total_rounds < 12:
        target_messages = "2-3"
    elif total_rounds <= 25:
        target_messages = "3-5"
    else:
        target_messages = "5-7"

    # System prompt with cache
    system_messages = [
        {
            "type": "text",
            "text": system_prompt_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # Load few-shot examples (strip eval percentages to match prompt constraint)
    few_shot_texts = []
    for path in few_shot_paths:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        # Remove patterns like "59%", "at 73% eval", "eval 31%", "(59%)"
        text = re.sub(r"\s*\(?\d+%\s*(?:eval)?\)?\s*", " ", text)
        text = re.sub(r"\beval\s+\d+%", "eval shifts", text)
        text = re.sub(r"\d+%\s*eval\b", "the eval", text)
        few_shot_texts.append(text)

    # Build notable turns section from game data
    turns = game_data.get("turns", [])
    notable_turns = []
    for t in turns:
        buys_str = ", ".join(t.get("buys", [])) or "(no buys)"
        line = f"T{t['round']} ({t['player_name']}): {buys_str}"
        if "eval_pct" in t:
            # Convert eval to qualitative label for the narrative model
            pct = t["eval_pct"]
            if pct >= 80:
                line += " | eval=dominant"
            elif pct >= 60:
                line += " | eval=ahead"
            elif pct >= 45:
                line += " | eval=even"
            elif pct >= 25:
                line += " | eval=behind"
            else:
                line += " | eval=losing"
        if t.get("ai_agrees") is False:
            ai_buys = ", ".join(t.get("ai_buys", []))
            line += f" [AI wanted: {ai_buys}]"
        notable_turns.append(line)

    # Verification warnings from Phase 2
    analysis_warnings = game_data.get("_analysis_warnings", [])
    warnings_text = "\n".join(analysis_warnings) if analysis_warnings else "(none)"

    # Build user content — strip eval_pct from analysis JSON to prevent number leakage
    analysis_copy = json.loads(json.dumps(analysis))  # deep copy
    for phase in analysis_copy.get("phases", []):
        for tp in phase.get("turning_points", []):
            if "eval_after" in tp:
                val = tp["eval_after"]
                if val >= 80:
                    tp["eval_after"] = "dominant"
                elif val >= 60:
                    tp["eval_after"] = "ahead"
                elif val >= 45:
                    tp["eval_after"] = "even"
                elif val >= 25:
                    tp["eval_after"] = "behind"
                else:
                    tp["eval_after"] = "losing"
            if "eval_before" in tp:
                val = tp["eval_before"]
                if val >= 80:
                    tp["eval_before"] = "dominant"
                elif val >= 60:
                    tp["eval_before"] = "ahead"
                elif val >= 45:
                    tp["eval_before"] = "even"
                elif val >= 25:
                    tp["eval_before"] = "behind"
                else:
                    tp["eval_before"] = "losing"
    analysis_json = json.dumps(analysis_copy, indent=2, ensure_ascii=False)
    # Final sanitization: strip any remaining numeric percentages from analysis text
    # Phase 2 LLM may embed eval numbers in narrative descriptions
    analysis_json = re.sub(r"\d+%", "", analysis_json)
    notable_turns_text = "\n".join(notable_turns)

    user_parts = []

    # Few-shot examples
    if few_shot_texts:
        user_parts.append("## Example Commentary (for style reference)\n")
        for i, ex in enumerate(few_shot_texts, 1):
            user_parts.append(f"### Example {i}\n{ex}\n")

    user_parts.append(f"""## Game to Analyze

Game: {game_data.get('code', '?')} — {players[0]['name']} ({players[0]['rating']}) vs {players[1]['name']} ({players[1]['rating']})
Winner: {winner_name}
Random Set: {', '.join(random_set)}

=== ANALYSIS ===
{analysis_json}

=== NOTABLE TURNS ===
{notable_turns_text}

=== VERIFICATION WARNINGS ===
{warnings_text}

Write {target_messages} Discord messages analyzing this game.""")

    user_content = "\n".join(user_parts)

    # Token budget management
    total_est = _estimate_tokens(system_prompt_text + user_content)

    # Step 1: drop second few-shot example if over soft cap
    if total_est > NARRATIVE_INPUT_SOFT_CAP and len(few_shot_texts) > 1:
        few_shot_texts = few_shot_texts[:1]
        user_parts_trimmed = ["## Example Commentary (for style reference)\n",
                              f"### Example 1\n{few_shot_texts[0]}\n"]
        user_parts_trimmed.append(user_parts[-1])  # game data section
        user_content = "\n".join(user_parts_trimmed)
        total_est = _estimate_tokens(system_prompt_text + user_content)
        print("  Token budget: dropped second few-shot example", file=sys.stderr)

    # Step 2: truncate primary few-shot to first and last message
    if total_est > NARRATIVE_INPUT_SOFT_CAP and few_shot_texts:
        messages = few_shot_texts[0].split("== MESSAGE")
        if len(messages) > 2:
            truncated = messages[0] + "== MESSAGE" + messages[1]
            truncated += "\n[... middle messages omitted ...]\n"
            truncated += "== MESSAGE" + messages[-1]
            few_shot_texts[0] = truncated.strip()
            user_parts_trimmed = ["## Example Commentary (for style reference)\n",
                                  f"### Example 1\n{few_shot_texts[0]}\n"]
            user_parts_trimmed.append(user_parts[-1])
            user_content = "\n".join(user_parts_trimmed)
            total_est = _estimate_tokens(system_prompt_text + user_content)
            print("  Token budget: truncated primary few-shot example", file=sys.stderr)

    # Step 3: hard abort if still over cap
    if total_est > NARRATIVE_INPUT_HARD_CAP:
        print(f"  WARNING: Input tokens (~{total_est}) exceed hard cap ({NARRATIVE_INPUT_HARD_CAP})",
              file=sys.stderr)

    return system_messages, user_content


def _call_narrative_api(system_messages, user_content, model=MODEL_HAIKU,
                        max_tokens=NARRATIVE_MAX_TOKENS):
    """Make the Claude API call for narrative generation.

    Returns raw text (not JSON). Uses same retry pattern as analysis.
    """
    from anthropic import Anthropic

    client = Anthropic()

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_messages,
                messages=[{"role": "user", "content": user_content}],
            )
            if not response.content:
                raise ValueError(f"API returned empty content, stop={response.stop_reason}")
            raw_text = response.content[0].text.strip()

            usage = response.usage
            stop = response.stop_reason
            print(f"  API usage: input={usage.input_tokens}, output={usage.output_tokens}, "
                  f"stop={stop}, "
                  f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}, "
                  f"cache_creation={getattr(usage, 'cache_creation_input_tokens', 0)}",
                  file=sys.stderr)

            if stop == "max_tokens":
                print(f"  WARNING: Narrative truncated (hit max_tokens={max_tokens}). "
                      f"Output may be incomplete.", file=sys.stderr)

            return raw_text

        except Exception as e:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < RETRY_ATTEMPTS - 1:
                print(f"  API error (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. "
                      f"Retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"  API error (attempt {attempt + 1}/{RETRY_ATTEMPTS}): {e}. "
                      f"Giving up.", file=sys.stderr)
                return None

    return None


def verify_narrative(narrative_text, analysis, game_data):
    """Programmatic verification of narrative text against game data.

    Returns list of warning strings. Empty = all checks passed.
    """
    warnings = []
    if not narrative_text:
        return ["Narrative is empty"]

    players = game_data.get("players", [])
    winner = game_data.get("winner", -1)
    if 0 <= winner < len(players):
        winner_name = players[winner]["name"]
    else:
        winner_name = None
    random_set = {u["name"] for u in game_data.get("random_set", [])}
    total_rounds = game_data.get("total_rounds", 0)

    # Check == MESSAGE N == delimiters exist
    msg_pattern = re.findall(r"==\s*MESSAGE\s+(\d+)\s*==", narrative_text)
    if not msg_pattern:
        warnings.append("No == MESSAGE N == delimiters found")
    elif len(msg_pattern) < 2:
        warnings.append(f"Only {len(msg_pattern)} message(s) found (expected at least 2)")

    # Check message character limits
    messages = re.split(r"==\s*MESSAGE\s+\d+\s*==", narrative_text)
    messages = [m.strip() for m in messages if m.strip()]
    for i, msg in enumerate(messages, 1):
        if len(msg) > DISCORD_CHAR_LIMIT:
            warnings.append(f"Message {i} exceeds {DISCORD_CHAR_LIMIT} chars ({len(msg)} chars)")

    # Check winner is mentioned
    if winner_name and winner_name.lower() not in narrative_text.lower():
        warnings.append(f"Winner '{winner_name}' not mentioned in narrative")

    # Check turn references are in valid range (exclude backtick code spans)
    text_for_turn_check = re.sub(r'`[^`]+`', '', narrative_text)
    turn_refs = re.findall(r"\bT(\d+)\b", text_for_turn_check)
    for ref in turn_refs:
        turn_num = int(ref)
        if turn_num > total_rounds:
            warnings.append(f"Turn reference T{turn_num} exceeds game length ({total_rounds} rounds)")

    # Check last message ends with sentence
    if messages:
        last_msg = messages[-1].rstrip()
        if last_msg and not last_msg[-1] in ".!?`":
            warnings.append("Last message does not end with a complete sentence")

    # Check replay code appears in narrative
    code = game_data.get("code", "")
    if code and code not in narrative_text:
        warnings.append(f"Replay code '{code}' not found in narrative")

    # Check no raw eval percentages leaked into narrative
    text_no_code = re.sub(r'`[^`]+`', '', narrative_text)
    eval_nums = re.findall(r"\d+%", text_no_code)
    if eval_nums:
        warnings.append(f"Raw eval percentages found in narrative (should use qualitative language): {eval_nums}")

    # Check no time pressure/clock references (not available from stored replays)
    time_patterns = re.findall(r"\b(?:time pressure|time bank|clock|seconds? (?:left|remaining))\b",
                               narrative_text, re.IGNORECASE)
    if time_patterns:
        warnings.append(f"Narrative mentions time/clock data not available from replays: {time_patterns}")

    return warnings


def _format_narrative(narrative_text, game_data):
    """Post-process narrative: ensure delimiters, char limits, replay link.

    Returns the formatted narrative text.
    """
    code = game_data.get("code", "")

    # Ensure replay code in last message
    if code and code not in narrative_text:
        narrative_text = narrative_text.rstrip() + f"\n\n`{code}`"

    # Split oversized messages at paragraph boundaries
    parts = re.split(r"(==\s*MESSAGE\s+\d+\s*==)", narrative_text)
    result_parts = []
    msg_counter = 0

    for part in parts:
        if re.match(r"==\s*MESSAGE\s+\d+\s*==", part):
            result_parts.append(part)
            msg_counter += 1
        elif len(part.strip()) > DISCORD_CHAR_LIMIT:
            # Split at nearest paragraph boundary
            paragraphs = part.split("\n\n")
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 2 > DISCORD_CHAR_LIMIT and current.strip():
                    result_parts.append(current)
                    msg_counter += 1
                    result_parts.append(f"\n== MESSAGE {msg_counter} ==\n")
                    current = para
                else:
                    current = current + "\n\n" + para if current else para
                # Fallback: if a single paragraph exceeds limit, split at sentences
                if len(current) > DISCORD_CHAR_LIMIT:
                    sentences = re.split(r'(?<=[.!?])\s+', current)
                    current = ""
                    for sent in sentences:
                        if len(current) + len(sent) + 1 > DISCORD_CHAR_LIMIT and current.strip():
                            result_parts.append(current)
                            msg_counter += 1
                            result_parts.append(f"\n== MESSAGE {msg_counter} ==\n")
                            current = sent
                        else:
                            current = (current + " " + sent).strip()
            if current.strip():
                result_parts.append(current)
        else:
            result_parts.append(part)

    return "".join(result_parts)


def run_narrative(analysis, game_data, analysis_warnings, model=MODEL_HAIKU, dry_run=False):
    """Run the narrative generation stage of the commentary pipeline.

    Returns (narrative_text, narrative_warnings) tuple.
    """
    print("\n[Phase 3] Generating narrative...", file=sys.stderr)

    # Store analysis warnings for narrative prompt
    game_data["_analysis_warnings"] = analysis_warnings

    # Select few-shot examples
    few_shot_paths = _select_few_shot_examples(game_data)
    print(f"  Few-shot examples: {len(few_shot_paths)}", file=sys.stderr)
    for p in few_shot_paths:
        print(f"    - {os.path.basename(p)}", file=sys.stderr)

    # Build prompts
    system_prompt_text = _load_narrative_system_prompt()
    system_messages, user_content = _build_narrative_messages(
        analysis, game_data, few_shot_paths, system_prompt_text
    )

    # Token estimation
    system_text = " ".join(
        block["text"] for block in system_messages if isinstance(block, dict)
    )
    total_input_tokens = _estimate_tokens(system_text + user_content)
    print(f"  Estimated input tokens: ~{total_input_tokens}", file=sys.stderr)
    print(f"  Model: {model}", file=sys.stderr)

    if dry_run:
        print("\n=== DRY RUN: Narrative System Prompt ===", file=sys.stderr)
        for block in system_messages:
            cached = " [CACHED]" if block.get("cache_control") else ""
            print(f"--- Block{cached} ({_estimate_tokens(block['text'])} tokens est.) ---",
                  file=sys.stderr)
            print(block["text"][:300], file=sys.stderr)
            if len(block["text"]) > 300:
                print(f"  ... ({len(block['text'])} chars total)", file=sys.stderr)
            print(file=sys.stderr)

        print("=== DRY RUN: Narrative User Message (first 1000 chars) ===", file=sys.stderr)
        print(user_content[:1000], file=sys.stderr)
        if len(user_content) > 1000:
            print(f"  ... ({len(user_content)} chars total)", file=sys.stderr)

        print(f"\n=== Token Estimates (Narrative) ===", file=sys.stderr)
        print(f"  System: ~{_estimate_tokens(system_text)} tokens", file=sys.stderr)
        print(f"  User: ~{_estimate_tokens(user_content)} tokens", file=sys.stderr)
        print(f"  Total input: ~{total_input_tokens} tokens", file=sys.stderr)
        print(f"  Max output: {NARRATIVE_MAX_TOKENS} tokens", file=sys.stderr)

        if model == MODEL_HAIKU:
            input_cost = total_input_tokens * 0.80 / 1_000_000
            output_cost = NARRATIVE_MAX_TOKENS * 4.00 / 1_000_000
            print(f"  Est. cost (Haiku, no cache): ${input_cost + output_cost:.4f}", file=sys.stderr)

        return None, []

    # Make the API call
    print(f"\n[Phase 3] Calling Claude API ({model})...", file=sys.stderr)
    narrative_text = _call_narrative_api(system_messages, user_content, model=model)

    if not narrative_text:
        print("ERROR: Narrative API call failed", file=sys.stderr)
        return None, ["Narrative API call failed"]

    # Post-process: format narrative
    narrative_text = _format_narrative(narrative_text, game_data)

    # Verify
    print("[Phase 3c] Running narrative verification...", file=sys.stderr)
    narrative_warnings = verify_narrative(narrative_text, analysis, game_data)

    if narrative_warnings:
        print(f"  Narrative verification warnings ({len(narrative_warnings)}):", file=sys.stderr)
        for w in narrative_warnings:
            print(f"    - {w}", file=sys.stderr)
    else:
        print("  Narrative verification: all checks passed", file=sys.stderr)

    return narrative_text, narrative_warnings


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_analysis(code, think_time=50, model=MODEL_HAIKU, dry_run=False):
    """Run the analysis stage of the commentary pipeline.

    Returns (analysis_dict, game_data, warnings) tuple.
    """
    print(f"[Phase 1] Extracting game data for {code}...", file=sys.stderr)
    game_data = _get_phase1_data(code, think_time=think_time)

    if not game_data:
        print("ERROR: Phase 1 returned no data", file=sys.stderr)
        return None, None, ["Phase 1 failed"]

    mode = game_data.get("data_quality", {}).get("mode", "?")
    turns = game_data.get("turns", [])
    print(f"  Phase 1 complete: mode={mode}, turns={len(turns)}", file=sys.stderr)

    # Build prompts
    system_prompt_text = _load_analysis_system_prompt()
    system_messages, user_content = _build_analysis_messages(game_data, system_prompt_text)

    # Token estimation
    system_text = " ".join(
        block["text"] for block in system_messages if isinstance(block, dict)
    )
    total_input_tokens = _estimate_tokens(system_text + user_content)
    print(f"  Estimated input tokens: ~{total_input_tokens}", file=sys.stderr)
    print(f"  Model: {model}", file=sys.stderr)

    if dry_run:
        print("\n=== DRY RUN: Analysis System Prompt ===", file=sys.stderr)
        for block in system_messages:
            cached = " [CACHED]" if block.get("cache_control") else ""
            print(f"--- Block{cached} ({_estimate_tokens(block['text'])} tokens est.) ---", file=sys.stderr)
            print(block["text"][:500], file=sys.stderr)
            if len(block["text"]) > 500:
                print(f"  ... ({len(block['text'])} chars total)", file=sys.stderr)
            print(file=sys.stderr)

        print("=== DRY RUN: User Message ===", file=sys.stderr)
        print(user_content, file=sys.stderr)
        print(f"\n=== Token Estimates ===", file=sys.stderr)
        print(f"  System: ~{_estimate_tokens(system_text)} tokens", file=sys.stderr)
        print(f"  User: ~{_estimate_tokens(user_content)} tokens", file=sys.stderr)
        print(f"  Total input: ~{total_input_tokens} tokens", file=sys.stderr)
        print(f"  Max output: {ANALYSIS_MAX_TOKENS} tokens", file=sys.stderr)

        # Estimate cost (Haiku 4.5 pricing)
        if model == MODEL_HAIKU:
            input_cost = total_input_tokens * 0.80 / 1_000_000
            output_cost = ANALYSIS_MAX_TOKENS * 4.00 / 1_000_000
            print(f"  Est. cost (Haiku, no cache): ${input_cost + output_cost:.4f}", file=sys.stderr)
            print(f"  Est. cost (Haiku, cached): ${total_input_tokens * 0.08 / 1_000_000 + output_cost:.4f}", file=sys.stderr)

        return None, game_data, []

    # Make the API call
    print(f"\n[Phase 2] Calling Claude API ({model})...", file=sys.stderr)
    analysis = _call_analysis_api(system_messages, user_content, model=model)

    if not analysis:
        print("ERROR: Analysis API call failed", file=sys.stderr)
        return None, game_data, ["API call failed"]

    # Post-process: fix player names (LLM sometimes appends "(P0)" etc.)
    players = game_data.get("players", [])
    player_names = {p["name"] for p in players}
    for pa in analysis.get("player_assessments", []):
        pname = pa.get("player", "")
        if pname not in player_names:
            # Try stripping common LLM annotations like "(P0)", "(P1)"
            cleaned = re.sub(r"\s*\(P\d+\)\s*$", "", pname).strip()
            if cleaned in player_names:
                pa["player"] = cleaned

    # Verify
    print("[Phase 2c] Running verification...", file=sys.stderr)
    warnings = verify_analysis(analysis, game_data)

    if warnings:
        print(f"  Verification warnings ({len(warnings)}):", file=sys.stderr)
        for w in warnings:
            print(f"    - {w}", file=sys.stderr)
    else:
        print("  Verification: all checks passed", file=sys.stderr)

    return analysis, game_data, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Post-game commentary pipeline for Prismata replays"
    )
    parser.add_argument("code", help="Replay code (e.g., FxCfR-K49T+)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show assembled prompts and token estimates without calling API")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Run analysis stage only (skip narrative)")
    parser.add_argument("--single-pass", action="store_true",
                        help="Bypass analysis, generate narrative directly (comparison mode)")
    parser.add_argument("--model", choices=["haiku", "sonnet"], default="haiku",
                        help="LLM model to use (default: haiku)")
    parser.add_argument("--think-time", type=int, default=50,
                        help="C++ think time in ms (default: 50)")
    parser.add_argument("--output", "-o", type=str,
                        help="Output file path (default: bin/commentary/commentary_<code>.txt)")
    args = parser.parse_args()

    model = MODEL_HAIKU if args.model == "haiku" else MODEL_SONNET

    # Default output path set after Phase 1 (needs player names)
    _auto_output = not args.output and not args.dry_run

    if args.single_pass:
        print("ERROR: --single-pass mode not yet implemented", file=sys.stderr)
        sys.exit(1)

    # --- Phase 2: Analysis ---
    analysis, game_data, analysis_warnings = run_analysis(
        args.code, think_time=args.think_time, model=model, dry_run=args.dry_run,
    )

    # Set default output path now that we have player names
    if _auto_output and game_data:
        os.makedirs(COMMENTARY_DIR, exist_ok=True)
        players = game_data.get("players", [])
        if len(players) >= 2:
            p1 = re.sub(r'[^\w]', '', players[0]["name"])
            p2 = re.sub(r'[^\w]', '', players[1]["name"])
            safe_code = args.code.replace("+", "_PLUS_").replace("@", "_AT_")
            args.output = os.path.join(COMMENTARY_DIR, f"commentary_{p1}_vs_{p2}_{safe_code}.md")
        else:
            safe_code = args.code.replace("+", "_PLUS_").replace("@", "_AT_")
            args.output = os.path.join(COMMENTARY_DIR, f"commentary_{safe_code}.md")

    if args.dry_run and not args.analyze_only:
        # Also show narrative dry-run
        if game_data:
            # Use a placeholder analysis for dry-run token estimation
            placeholder = {"game_narrative_arc": "(dry run)", "phases": [],
                           "turning_points": [], "player_assessments": [],
                           "set_analysis": "(dry run)", "decisive_factor": "(dry run)"}
            run_narrative(placeholder, game_data, [], model=model, dry_run=True)
        print("\n[DRY RUN complete — no API calls made]", file=sys.stderr)
        return

    if args.dry_run:
        print("\n[DRY RUN complete — no API calls made]", file=sys.stderr)
        return

    if not analysis:
        print("ERROR: Analysis failed", file=sys.stderr)
        sys.exit(1)

    # --- Analyze-only output ---
    if args.analyze_only:
        output = {
            "code": args.code,
            "stage": "analysis",
            "model": model,
            "analysis": analysis,
            "verification_warnings": analysis_warnings,
            "data_quality": game_data.get("data_quality", {}),
        }
        output_json = json.dumps(output, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"Analysis written to {args.output}", file=sys.stderr)
        else:
            print(output_json)
        return

    # --- Phase 3: Narrative ---
    narrative_text, narrative_warnings = run_narrative(
        analysis, game_data, analysis_warnings, model=model,
    )

    if not narrative_text:
        print("ERROR: Narrative generation failed", file=sys.stderr)
        sys.exit(1)

    # Strip == MESSAGE N == delimiters for final output (kept internally for verification)
    output_text = re.sub(r"\n*==\s*MESSAGE\s+\d+\s*==\n*", "\n\n", narrative_text).strip()

    # Output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"Commentary written to {args.output}", file=sys.stderr)
    else:
        print(output_text)

    # Summary
    all_warnings = analysis_warnings + narrative_warnings
    if all_warnings:
        print(f"\nTotal warnings: {len(all_warnings)}", file=sys.stderr)
        for w in all_warnings:
            print(f"  - {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
