#!/usr/bin/env python3
"""Post-game commentary pipeline for Prismata replays.

Two-stage LLM pipeline:
  Stage 1 (Phase 2): Structured game analysis via Claude API
  Stage 2 (Phase 3): Narrative generation (not yet implemented)

Usage:
    # Dry run (no API calls, shows assembled prompt + token estimate)
    python tools/generate_postgame_commentary.py FxCfR-K49T+ --dry-run

    # Run analysis stage only
    python tools/generate_postgame_commentary.py FxCfR-K49T+ --analyze-only

    # Full pipeline (analysis + narrative, when Phase 3 is ready)
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

# Models
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-5-20241022"

# Token limits
ANALYSIS_MAX_TOKENS = 4096

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
                        help="Output file path (default: stdout)")
    args = parser.parse_args()

    model = MODEL_HAIKU if args.model == "haiku" else MODEL_SONNET

    if args.single_pass:
        print("ERROR: --single-pass mode not yet implemented (Phase 3)", file=sys.stderr)
        sys.exit(1)

    analysis, game_data, warnings = run_analysis(
        args.code, think_time=args.think_time, model=model, dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n[DRY RUN complete — no API calls made]")
        return

    if not analysis:
        print("ERROR: Analysis failed", file=sys.stderr)
        sys.exit(1)

    # Output
    output = {
        "code": args.code,
        "stage": "analysis",
        "model": model,
        "analysis": analysis,
        "verification_warnings": warnings,
        "data_quality": game_data.get("data_quality", {}),
    }

    output_json = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Analysis written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    if not args.analyze_only:
        print("\n[Phase 3 narrative generation not yet implemented]", file=sys.stderr)


if __name__ == "__main__":
    main()
