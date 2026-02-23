# Post-Game Replay Commentary Pipeline — Implementation Plan (v2)

**Date:** 2026-02-22 (v2: post-review revision)
**Branch:** `feature/postgame-commentary`
**Status:** PLAN — revised after 13-review meta-review
**Estimated cost:** ~$0.02-0.04 per game (Haiku 4.5 sync), ~$0.01-0.02 per game (Batch + caching)

<!-- CHANGED: Cost estimates revised upward from $0.01-0.02 to $0.02-0.04 sync based on realistic token counts — R2, R5, R6, R8, R12 -->

## Motivation

The live commentary system (Phase 1, working) generates 1-2 sentences per turn via Claude Haiku with a 40-120 token budget. This produces shallow real-time analysis constrained by time pressure. Post-game commentary removes all constraints: we have the full game context, unlimited time, multi-pass processing, and can reference earlier events. The manual workflow (Feb 20) produced excellent results — 3 commentaries received positive community feedback — but requires 15-20 minutes of human effort per game.

**Goal:** Fully automated pipeline: replay code → polished multi-message Discord commentary in ~60 seconds, with quality matching or exceeding the manually-written examples.

## Phase 0: Research Findings

### What Exists Today

| Component | File | Status | Purpose |
|---|---|---|---|
| Data extraction | `tools/generate_commentary_data.py` (690 lines) | Working | Replay fetch, resource validation, C++ eval/analyze |
| Live commentator | `tools/prismata_commentator.py` (371 lines) | Working | Per-turn Haiku calls, chat injection |
| Game state model | `tools/prismata_game_state.py` (176 lines) | Working | TurnRecord, GameContext, GameNarrative |
| Condensed KB | `tools/commentary_prompt.md` (68 lines) | Working | ~2,400 token system prompt |
| Full KB | `docs/commentary-knowledge/` (7 files) | Complete | 5,090 lines across 7 categories |
| Few-shot examples | `bin/commentary/` (7 files) | Excellent quality | 3 unique replays, multiple iterations |
| Batch API pattern | `tools/discord_knowledge_extractor.py` | Proven | Batch submission, polling, cost tracking |
| Commentary instructions | `docs/plans/commentary-generation-instructions.md` | Complete | Manual workflow, format spec, tone guide |

### Key Research Findings

1. **Multi-stage pipelines dominate** — WSC Sports (NBA, Bundesliga), academic survey (arXiv 2506.17294), and IBM Wimbledon all use extract → analyze → narrate architectures. Single-pass generation produces lower quality and more hallucinations.

2. **Structured data input is critical** — GetStream's real-time football commentator found that raw data produces poor results. WSC Sports' key insight: "explicitly providing information to the model rather than having it guess." Our C++ eval + resource-validated buys are ideal structured input.

3. **Few-shot examples dramatically improve narrative quality** — WSC Sports uses "dynamic few-shot selection" matching example style to game characteristics. We have 3 excellent manually-written commentaries to use as examples.

4. **Batch API + prompt caching stack** — Official Anthropic docs confirm 50% batch discount combines with prompt caching (90% read savings). For 100-game batch: ~$1.50-2.00 total.
<!-- CHANGED: Cost revised from $0.70 to $1.50-2.00 to reflect realistic token counts — R2, R5, R8 -->

5. **CoT verification catches hallucinations** — Having the model verify claims against source data in a separate pass catches factual errors (wrong turn numbers, non-existent units, invented purchases).

### Architecture Decision: Two-Stage LLM Pipeline

**Why not single-pass?** A single prompt asking for both analysis AND narrative produces mediocre results at both tasks. The model either:
- Rushes the analysis to get to the narrative (missing key turning points)
- Gets bogged down in data recitation instead of engaging storytelling

<!-- CHANGED: Added acknowledgment that single-stage may work for short games — R7, R10, R11, R12 -->
**Note on single-stage alternative:** Several reviewers recommended testing a single-stage approach (structured data + few-shot → narrative directly) as it may achieve comparable quality for short games (<15 turns) at lower cost and complexity. We preserve the two-stage architecture as the primary approach based on production research, but add a `--single-pass` flag as a comparison baseline (see Phase 2).

**Why not three+ stages?** Per-turn classification as a separate LLM stage adds cost and latency without proportional quality gain. The C++ eval data already provides turn significance (eval swings = turning points). Two LLM stages is the sweet spot.

**The two stages:**

| Stage | Task | Input | Output | Model | Tokens (estimated) |
|---|---|---|---|---|---|
| **Analysis** | Identify game phases, turning points, key decisions, strategy assessment | Structured game data + KB | JSON (phases, turning points, player assessments) | Haiku 4.5, structured output | ~4-5K in, ~2K out |
| **Narrative** | Transform analysis into engaging prose | Analysis JSON + few-shot examples | Discord-ready markdown | Haiku 4.5, free-form | ~7-10K in, ~3K out |

<!-- CHANGED: Token estimates revised to show ranges — R2, R5, R6, R8, R12 -->

**Token budget breakdown (narrative stage):**
<!-- CHANGED: Added explicit per-component breakdown — R5, R6, R12 -->

| Component | Tokens (est.) | Notes |
|---|---|---|
| System prompt (style guide + rules) | ~1,000 | Cached across games |
| Unit knowledge (random set) | ~500 | Varies by set (8 units × ~60 tokens) |
| Analysis JSON from Stage 1 | ~1,500-2,000 | Varies by game length |
| Few-shot example (primary) | ~3,500 | Full commentary example |
| Few-shot example (secondary, if used) | ~3,500 | Only for long/upset games |
| Per-turn notable data | ~500-1,000 | Only notable turns, not all |
| **Total (1 example)** | **~7,000-8,000** | Typical 15-turn game |
| **Total (2 examples)** | **~10,000-11,000** | Long/upset games — must trim |

**Why Haiku 4.5 over Sonnet?** The manually-written commentaries prove that the *data quality* (resource-validated buys, neural eval, AI comparison) matters more than model capability. Haiku 4.5 with excellent prompts + few-shot examples + structured data produces quality comparable to Sonnet at 1/3 the cost. We offer Sonnet as an optional `--model sonnet` flag.

### What Changes from Live Commentary

| Aspect | Live (current) | Post-game (proposed) |
|---|---|---|
| Context window | Last 5 turns | Full game |
| Token budget | 40-120 per turn | ~3,000 per game |
| Knowledge base | Condensed 68-line prompt | Full 5,090-line KB (relevant sections) |
| Neural eval | Not available | Per-turn eval + AI comparison |
| Few-shot examples | None | 1-2 high-quality commentaries |
| Processing | Single pass, real-time | Two-stage, offline |
| Output format | 1-2 sentences to chat | Multi-message Discord post |
| Batch capability | No | Yes (Batch API, 50% discount) |
| Hallucination check | None | Multi-layer verification against game data |

---

## Phase 1: Enhanced Data Extraction (`generate_commentary_data.py`)

### Goal
Extend the existing data extraction tool to output a single structured JSON file containing everything the LLM stages need — no further data access required.

### What to implement

**1a. Add `--json-output` flag** that writes structured game data to a JSON file instead of printing text summaries.

<!-- CHANGED: Schema updated — removed `tier`, removed `time_used`/`time_bank` (not in stored replays), added `game_characteristics`, added `deck_units`, made fields optional based on mode, added `data_quality` block — R5, R6, R8, R10, R12 + codebase validation -->

Output schema (new file: `tools/commentary_schema.json`):
```json
{
  "code": "FxCfR-K49T+",
  "players": [
    {"name": "Surfinite", "rating": 1856, "index": 0},
    {"name": "Kolento", "rating": 2222, "index": 1}
  ],
  "winner": 0,
  "total_rounds": 15,
  "game_characteristics": {
    "length_category": "medium",
    "is_upset": true,
    "rating_diff": 366,
    "biggest_eval_swing": 28.34
  },
  "random_set": [
    {
      "name": "Plasmafier",
      "cost": "12GGGB",
      "hp": 4,
      "build_time": 1,
      "fragile": false,
      "abilities": "Click: sacrifice a Drone. Gain 4 attack.",
      "supply": 4
    }
  ],
  "deck_units": ["Drone", "Engineer", "Conduit", "Blastforge", "Animus",
                  "Tarsier", "Rhino", "Wall", "Steelsplitter",
                  "Gauss Cannon", "Forcefield", "Plasmafier", "..."],
  "turns": [
    {
      "ply": 1,
      "round": 1,
      "turn_in_round": 1,
      "player": 0,
      "player_name": "Surfinite",
      "buys": ["Drone", "Drone"],
      "eval_pct": 50.0,
      "eval_raw": 0.0,
      "eval_delta": 0.0,
      "ai_buys": ["Drone", "Drone"],
      "ai_agrees": true,
      "click_count": 4,
      "undo_count": 0,
      "abilities_used": []
    }
  ],
  "data_quality": {
    "has_eval": true,
    "has_ai": true,
    "stepper_reliable": true,
    "stepper_total_clicks": 145,
    "stepper_applied_clicks": 132,
    "stepper_applied_pct": 0.91,     // Computed: applied_clicks / total_clicks (not a C++ output field)
    "mode": "analyze",
    "notes": []
  },
  "precomputed": {
    "agreement_rate": 0.733,
    "biggest_mistake": {"ply": 13, "player": 1, "eval_drop": 12.45},
    "max_eval_swing": 28.34,
    "top_eval_swings": [
      {"ply": 13, "player": 1, "delta": -12.45},
      {"ply": 7, "player": 0, "delta": 8.2}
    ],
    "turning_point_candidates": [
      {"ply": 13, "reason": "largest_eval_drop", "magnitude": 12.45},
      {"ply": 5, "reason": "first_attacker_buy", "unit": "Tarsier"},
      {"ply": 9, "reason": "burst_buy_spike", "buy_count": 4}
    ]
  },
  "unit_knowledge": {
    "Plasmafier": "Drone-eating attack engine. Click sacrifices Drone for 4 burst attack...",
    "Tesla Coil": "Chill unit. Freezes 1 enemy blocker per turn..."
  }
}
```

**Key schema changes from v1:**
- **Removed `tier`** — field doesn't exist in cardLibrary.jso; would encourage hallucinations
- **Removed `time_used`/`time_bank`/`time_control`** — stored replay JSON from S3 does not contain time data (time data is only available from the live wire protocol). If time data becomes available in future (e.g., from sniffer captures), it can be re-added as optional fields.
- **Added `ply` (1-based half-turn index)** — canonical monotonic index to prevent turn/round confusion in verification
- **Added `turn_in_round`** (1 or 2) — disambiguates which player acted
- **Added `deck_units`** — full list of all units (base + random) for validation
- **Added `game_characteristics`** — pre-computed metadata for few-shot selection and game length handling
- **Added `data_quality` block** — explicit quality flags so LLM and verification know what data is reliable
- **Added `precomputed.turning_point_candidates`** — deterministic pre-computation of likely turning points from eval data, so the LLM selects among candidates rather than inventing them
- **Added `precomputed.top_eval_swings`** — ranked eval deltas for programmatic turning point detection
- **Made `ai_buys`/`ai_agrees`/`eval_*` fields conditional** — only present when C++ mode supports them (absent in `--validate`)

**1b. Build pre-computed unit knowledge index** — One-time parser that builds a JSON lookup table from KB markdown files.

<!-- CHANGED: Replaced fragile text search with structured pre-built index — R1-R13 (near-universal consensus) -->

Implementation:
1. **One-time index build script** (`tools/build_unit_knowledge_index.py`):
   - Scan `docs/commentary-knowledge/03-advanced-units.md` using header-based section extraction (regex: `^### (.+)` capturing unit name, text until next `###`)
   - Normalize names (trim, casefold) and handle format variations (e.g., "### Centurion — The Strongest Unit" → key: "Centurion")
   - **Also scan `docs/commentary-knowledge/02-base-set-units.md`** for base set units (always relevant)
   - **Also scan concept sections** from `01-game-fundamentals.md` and `04-strategy-concepts.md` for mechanic-specific knowledge (e.g., if Chill units present → include Chill theory snippet)
   - Output: `tools/data/unit_knowledge_index.json` mapping `{unit_name → {snippet, source_file, mechanics: []}}`
   - Add name normalization: handle plurals ("Tarsiers" → "Tarsier"), case variations, common abbreviations
2. **At runtime**: Simple dict lookup from the pre-built index. No markdown parsing at runtime.
3. **Fallback**: If a unit isn't in the index, include only its mergedDeck stats (cost, HP, abilities text).
4. **Concept injection**: If random set contains units with specific mechanics (Chill, Absorb, Breachproof), also include the relevant 100-200 token concept snippet.

**1c. Combine resource validation + C++ eval in one pass** — Currently `--validate` and default mode are mutually exclusive. The JSON output mode should run both: resource-validated buys (ground truth) AND neural eval per turn.

<!-- CHANGED: Added automatic C++ fallback chain — R1, R3, R4, R6, R10, R11, R12 -->

**1d. Automatic C++ fallback chain** — If `--analyze` fails (timeout on 40+ turn games, OOM), automatically fall back:
```
--analyze (300s timeout) → --eval-only (60s timeout) → --validate (no C++ needed)
```
Each fallback logs a warning and sets `data_quality.mode` accordingly. The LLM stages adapt their prompts based on available data.

**1e. Pre-compute turning point candidates** — Before any LLM call, deterministically identify:
<!-- CHANGED: Added pre-computation step — R8 -->
- Top K eval swings (from `eval_delta`)
- Burst buy turns (unusually high buy count or spend)
- First attacker purchase timing
- AI disagreement clusters (consecutive `ai_agrees: false` turns)

These are passed as `turning_point_candidates` so the analysis LLM selects among them rather than inventing turning points.

**1f. Pre-compute game characteristics** — Classify the game for downstream use:
<!-- CHANGED: Added game classification — R4, R6, R7, R8, R10, R12 -->
- `length_category`: `"short"` (<12 rounds), `"medium"` (12-25), `"long"` (>25)
- `is_upset`: rating difference > 200 and lower-rated player won
- `rating_diff`: absolute difference
- `biggest_eval_swing`: for significance assessment

### Files to modify
- `tools/generate_commentary_data.py` — Add `--json-output PATH` flag, `build_structured_output()` function, fallback chain
- New file: `tools/build_unit_knowledge_index.py` — One-time KB index builder
- New file: `tools/data/unit_knowledge_index.json` — Pre-built unit knowledge lookup
- New file: `tools/commentary_schema.json` — JSON schema for structured output

### Verification checklist
- [ ] `python tools/generate_commentary_data.py "FxCfR-K49T+" --json-output tmp/test_game.json` produces valid JSON
- [ ] JSON contains all required fields from schema
- [ ] `unit_knowledge` populated for all random set units AND relevant base set units
- [ ] `buys` arrays match `--validate` output (resource-validated)
- [ ] `eval_pct` and `eval_delta` present for all turns (when C++ available)
- [ ] Fallback chain works: kill C++ mid-run → falls back to --eval-only → still produces JSON
- [ ] `--validate` mode produces valid JSON without C++ exe (eval/ai fields absent)
- [ ] `game_characteristics` correctly classifies all 3 test replays
- [ ] `turning_point_candidates` identifies the biggest eval swings
- [ ] `deck_units` includes all base set + random set unit names
- [ ] Runs on 3 different replay codes without errors
- [ ] `jsonschema.validate()` passes on output JSON against `tools/commentary_schema.json`

### Anti-pattern guards
- Do NOT change the existing text output modes (`--validate`, `--eval-only`, default). The `--json-output` flag adds a new output path.
- Do NOT import the anthropic SDK in this file. Phase 1 is pure local data processing.
- Do NOT read the full KB files into memory at runtime. Use the pre-built index.
- Do NOT include `tier` in the schema — it doesn't exist in the data and would encourage hallucinations.
- Do NOT include `time_used`/`time_bank` — stored replay JSON from S3 does not contain time data.

---

## Phase 2: Game Analysis Stage (New File)

### Goal
Create a new script `tools/generate_postgame_commentary.py` that orchestrates the two-stage LLM pipeline. This phase implements Stage 1: structured game analysis.

### What to implement

**2a. Analysis prompt** — System prompt with:
- Condensed game rules (~1,200 tokens, subset of `commentary_prompt.md`)
- Unit-specific knowledge (from Phase 1 JSON `unit_knowledge` field)
- Structured output schema for analysis JSON

<!-- CHANGED: Added prompt outline — R5, R6, R11, R13 -->

**Analysis system prompt outline** (file: `tools/prompts/analysis_system.md`):
```
Section 1: Game Rules Summary (~800 tokens)
  - Resources, phases, turn structure
  - Win conditions
  - Key mechanics (Absorb, Chill, Frontline, Breach)

Section 2: Task Description (~200 tokens)
  - "You are analyzing a completed Prismata game..."
  - Explain what constitutes a "turning point" vs routine turn
  - Explain phase identification criteria
  - Emphasize: only reference data provided, never invent
  - "Only cite a turn as a mistake if `ai_agrees` is false for that turn" — prevents inventing errors where AI agreed with the player
  <!-- APPLIED: Optional #11 (constrain mistakes to AI-flagged turns) -->
  - "If eval data is not available (data_quality.has_eval=false), omit numerical eval claims and focus on purchase patterns"

Section 3: Unit Knowledge (~variable, from unit_knowledge field)
  - Injected per-game: strategic notes for each unit in random set
  - Concept snippets for relevant mechanics

Section 4: Output Schema (~200 tokens)
  - JSON schema description with field explanations
```

**2b. Analysis call** — Single Claude API call with structured output:

<!-- CHANGED: Made schema more flexible — allow empty arrays, added has_clear_phases, phase_confidence — R10, R12 -->
<!-- CHANGED: Added max_tokens specification — R6 -->

```python
# Structured output schema (will be converted to proper JSON Schema)
analysis_schema = {
    "game_narrative_arc": str,           # 2-3 sentence game summary
    "has_clear_phases": bool,            # false for rush games or unclear structure
    "phase_confidence": str,             # "high", "medium", "low"
    "phases": [                          # May be empty for very short games
        {
            "name": str,                 # Flexible: not limited to Opening/Mid/End
            "rounds": [int, int],        # Start/end round (or null if unclear)
            "summary": str,
            "key_decisions": [str]
        }
    ],
    "turning_points": [                  # May be empty if no significant swings
        {
            "ply": int,                  # Canonical half-turn index
            "round": int,
            "player": int,
            "description": str,
            "impact": str,
            "eval_before": float,
            "eval_after": float
        }
    ],
    "player_assessments": [
        {
            "player": str,              # Player name (not index)
            "strategy_summary": str,
            "strengths": [str],
            "mistakes": [str],
            "notable_plies": [int]      # Using ply index
        }
    ],
    "set_analysis": str,                # Optional: what strategies the random set enables
    "decisive_factor": str,             # One sentence: what decided the game
    # "commentary_hooks" removed — meta-reasoning is hit-or-miss at Haiku quality. Re-add in V2 if analysis quality warrants it.
}

# API call parameters
max_tokens = 3000  # Conservative ceiling for analysis output
```

<!-- CHANGED: Resolved to use direct import — codebase validation confirmed no side effects — R5, R6, R10, R11, R12 -->

**2b-note: Integration with Phase 1** — `generate_commentary_data.py` is cleanly structured with `if __name__ == "__main__"` guard and no module-level side effects. **Use direct import** of its functions (`fetch_replay`, `run_analyze`, `run_eval_only`, `ResourceTracker`, `get_deck_info`, `get_players`) rather than subprocess. This gives cleaner error handling and shared memory.

Phase 1 adds a new `build_structured_output(code, mode="analyze")` function that wraps these internal functions into a single callable — returns the complete structured dict from the schema above. The pipeline in `generate_postgame_commentary.py` should call this wrapper rather than orchestrating the internal functions directly.

**2c. Verification pass** — After analysis, programmatic checks against Phase 1 JSON:

<!-- CHANGED: Substantially expanded verification — R1, R4, R6, R8, R10, R11, R12, R13 -->

**Basic referential checks:**
- All referenced ply/turn numbers exist in the game data
- All referenced unit names are in `deck_units`
- Player names are correct and not swapped
- Winner identification matches game data

**Eval-grounded checks:**
- Every turning point's `eval_before`/`eval_after` matches actual eval data (±3%)
- Eval directionality claims (e.g., "took a commanding lead") match `eval_delta` sign
- `biggest_mistake` in analysis matches actual largest `eval_drop` in game data

**Purchase attribution checks:**
- Every specific buy claim ("Player X bought Y on turn Z") cross-referenced against `turns[Z].buys`
- "AI disagreed" claims verified against `turns[Z].ai_agrees`

**Structural checks:**
- Phase round ranges don't overlap or have gaps (if phases present)
- All `notable_plies` in player_assessments exist in game data

This is NOT an LLM call — just Python assertions against the Phase 1 JSON. If any check fails, log a warning and flag the specific claim. Do NOT auto-reject; instead, pass failure list to the narrative stage for avoidance.

<!-- CHANGED: Added single-pass comparison flag — R7, R10, R11, R12 -->

**2d. `--single-pass` comparison mode** — For benchmarking, bypass the analysis stage entirely. Feed structured game data + few-shot examples directly to the narrative call. Compare quality against the two-stage approach on the 3 test replays to empirically validate the two-stage decision.

### Files to create
- `tools/generate_postgame_commentary.py` — Main pipeline script (CLI entry point)
- `tools/prompts/analysis_system.md` — Analysis stage system prompt

### Files to read (patterns to follow)
- `tools/discord_knowledge_extractor.py` — `_extract_chunk_sync()`: synchronous API call pattern with retry
- `tools/prismata_commentator.py` — `_build_system_prompt()`: system prompt construction with cache control
- `tools/prismata_commentator.py` — `_generate_commentary()`: API call pattern

### Verification checklist
- [ ] Analysis JSON validates against schema (all required fields present)
- [ ] All ply numbers in `turning_points` exist in game data
- [ ] All unit names in analysis are in `deck_units`
- [ ] `phases` cover the full game (no gaps in round ranges) when `has_clear_phases` is true
- [ ] Verification pass catches injected errors (test with deliberately wrong data)
- [ ] Expanded checks catch: wrong eval direction, incorrect buy attribution, swapped player names
- [ ] Works on all 3 test replays: `FxCfR-K49T+`, `WjhmP-WWdXx`, `uP8mG-tr75d`
- [ ] `--single-pass` mode produces complete commentary (for comparison)
- [ ] Short game (<12 rounds) handles gracefully: phases may be empty, turning_points may be empty

### Anti-pattern guards
- Do NOT use structured outputs for the narrative stage (Phase 3). JSON constraints make prose feel mechanical.
- Do NOT skip the programmatic verification. Even with structured output, Haiku can cite non-existent turns.
- Do NOT include the full 5,090-line KB in the system prompt. Use only the condensed game rules (~1,200 tokens) + unit-specific knowledge for units in this game's random set.
- Do NOT let the LLM invent turning points from scratch. Pass `turning_point_candidates` and require it to select from and explain them.
- **Turn indexing convention**: Schema uses `ply` (1-based half-turn index) internally. Prompts instruct the model to use "Turn N" (round-based, human-readable) in narrative prose. Verification maps between the two using `round` and `turn_in_round` fields. Never mix conventions within a single context.
<!-- APPLIED: Optional #14 (standardize turn indexing) -->

---

## Phase 3: Narrative Generation Stage

### Goal
Implement Stage 2 of the pipeline: transform the structured analysis into engaging prose commentary, using few-shot examples for style calibration.

### What to implement

**3a. Few-shot example selection** — Include 1-2 of the best existing commentaries as examples.

<!-- CHANGED: Codified selection as explicit function — R6 -->

```python
def select_few_shot_examples(game_data: dict) -> list[str]:
    """Returns 1-2 commentary file paths based on game characteristics.

    Current examples (will expand over time):
    - WjhmP-WWdXx.txt (45 lines, ~3,500 tokens) — standard analytical, 16 turns
    - FxCfR-K49T+.txt (46 lines, ~3,500 tokens) — upset game, 15 rounds
    - uP8mG-tr75d.txt (64 lines, ~4,500 tokens) — long grind, 39 turns
    """
    examples = []
    gc = game_data["game_characteristics"]

    # Always include the primary example (shortest high-quality)
    examples.append("bin/commentary/commentary_WjhmP-WWdXx.txt")

    # Add second example only if budget allows AND game matches
    if gc["is_upset"] and gc["rating_diff"] > 200:
        examples.append("bin/commentary/commentary_FxCfR-K49T+.txt")
    elif gc["length_category"] == "long":
        examples.append("bin/commentary/commentary_uP8mG-tr75d.txt")

    return examples
```

**Token budget management** — When input exceeds soft cap:
<!-- CHANGED: Added explicit trim priority — R6 -->
1. First: drop the second few-shot example
2. Then: truncate per-turn data to only plies with |eval_delta| > threshold
3. Then: truncate the primary few-shot example to first and last message only
4. Hard abort if input still exceeds 12K tokens after all trimming

**3b. Narrative prompt** — User message with:
- Analysis JSON from Stage 1
- Selected per-turn data (only notable turns, not every turn)
- Tone/format instructions (from `commentary-generation-instructions.md` § "Tone & Format" section)
- Target format: `== MESSAGE N ==` delimiters, <2000 chars per message

<!-- CHANGED: Added prompt outline and grounding constraint — R6, R13 -->

**Narrative system prompt outline** (file: `tools/prompts/narrative_system.md`):
```
Section 1: Role & Style (~300 tokens)
  - "You are writing post-game analysis for the Prismata Discord community"
  - Expert audience: assume knowledge of base set units and basic mechanics
  - Present-tense play-by-play for turning points
  - Open each message with a hook; end with forward-reference

Section 2: Grounding Constraints (~200 tokens)
  - "Only reference purchases confirmed in the buys arrays"
  - "Do not invent or infer purchases not in the data"
  - "If a turn has empty buys, the player passed or only used abilities"
  - "Only cite eval percentages from the analysis JSON"
  - "Never mention player statistics not in the data"

Section 3: Format Requirements (~200 tokens)
  - == MESSAGE N == delimiters
  - Each message under 2000 characters
  - Target message count based on game length (see below)
  - Replay code link in final message

Section 4: Style Guide (~300 tokens, extracted from examples)
  - Sentence structure patterns from manual commentaries
  - How to reference turns: "Turn 8" or "T8" not "ply 15"
  - How to use eval data: natural integration, not data dumps
  - Vocabulary: "punish", "commit", "tech into", "float gold"
```

**Narrative user message template** (file: `tools/prompts/narrative_user_template.md`):
```
Game: {code} — {p1_name} ({p1_rating}) vs {p2_name} ({p2_rating})
Winner: {winner_name}
Random Set: {unit_names}

=== ANALYSIS ===
{analysis_json}

=== NOTABLE TURNS ===
{notable_turns_data}

=== VERIFICATION WARNINGS (if any) ===
{verification_warnings}

Write {target_messages} Discord messages analyzing this game.
```

<!-- CHANGED: Added game length → message count mapping — R4, R6, R8, R10, R12 -->

**3c. Game length adaptation:**

| Length Category | Rounds | Target Messages | Focus |
|---|---|---|---|
| Short | <12 | 2-3 | Opening + decisive moment only |
| Medium | 12-25 | 3-5 | Full analysis with phases |
| Long | >25 | 5-7 | Chaptered (early/mid/late), cap per-phase detail |

<!-- APPLIED: Optional #2 (LLM judge) and #3 (repair loop) — cheap insurance against hallucinations -->

**3d. Post-narrative verification and repair:**
1. **Programmatic checks** — Run the same referential/eval/buy checks from Phase 2c against the narrative text (regex extraction of turn numbers, unit names, eval claims).
2. **LLM judge call (if programmatic checks pass)** — Fire a cheap Haiku call (~200 tokens): "List every factual claim in this commentary not directly supported by the analysis JSON below." Cost: ~$0.002/game. If the list is non-empty, proceed to repair.
3. **Repair loop (if issues found)** — One repair call: "Here is the commentary. Here are the failed checks: {issues}. Rewrite only the incorrect sentences; preserve style and structure." Triggers at most once — if repair also fails, save with `[needs-review]` prefix in filename.

**3e. Output formatting** — Post-process the raw LLM output:
- Validate `== MESSAGE N ==` delimiters are present
- Check each message is under 2000 characters (Discord limit)
- If a message exceeds 2000 chars, split at the nearest paragraph boundary
- Check last message ends with complete sentence (`.`, `!`, or `?`)
- Verify at least 2 messages generated
- Append replay code link to final message
- **Discord emoji pass** — Replace unit name mentions with `:unit_name:` Discord custom emoji shorthand (e.g., `:Tarsier:`, `:Wall:`). Only for units with known server emojis. Controlled by `--discord-emoji` flag (off by default for plain text output).
<!-- APPLIED: Optional #10 (Discord emoji shorthand) — nice polish for Discord posting -->

<!-- CHANGED: Added max_tokens specification — R6 -->

```python
# Narrative stage API parameters
max_tokens = 4096  # Ceiling for narrative output
```

**3f. Quality flags** — CLI options:
- `--model haiku` (default, ~$0.02-0.04/game) — Claude Haiku 4.5
- `--model sonnet` (~$0.08-0.12/game) — Claude Sonnet for premium quality

<!-- CHANGED: Removed --style hype and --style casual — R1, R2, R4, R5, R7, R8, R10, R11, R12, R13 (near-universal) -->
<!-- Style variants deferred until analytical style is proven and community requests alternatives -->

### Files to modify
- `tools/generate_postgame_commentary.py` — Add narrative stage, CLI flags, output formatting
- New file: `tools/prompts/narrative_system.md` — Narrative stage system prompt
- New file: `tools/prompts/narrative_user_template.md` — User message template with placeholders

### Verification checklist
- [ ] Output has `== MESSAGE N ==` delimiters
- [ ] Each message is under 2000 characters
- [ ] Commentary references specific turn numbers that exist in the game
- [ ] Commentary mentions units that are actually in the deck
- [ ] Commentary correctly identifies the winner
- [ ] Commentary quality comparable to `commentary_FxCfR-K49T+.txt` (subjective, human review)
- [ ] `--model sonnet` produces noticeably higher quality than `--model haiku`
- [ ] All 3 test replays produce coherent, complete commentary
- [ ] Short game produces 2-3 messages; long game produces 5-7 messages
- [ ] No empty or incomplete messages (last message ends with sentence)

### Anti-pattern guards
- Do NOT use structured output/JSON mode for narrative generation. Free-form text with few-shot examples produces better prose.
- Do NOT include raw turn-by-turn data dumps in the narrative prompt. Feed only the analysis JSON + selected notable turns.
- Do NOT exceed soft cap of 10K input tokens without trimming. Use the priority order above.
- Do NOT mention time pressure or clock data (not available from stored replays).
- Do NOT claim player statistics, win rates, or historical information not present in the data.

---

## Phase 4: End-to-End CLI

### Goal
Wire everything together into a single command that takes a replay code and produces commentary.

### What to implement

**4a. Single-command workflow:**
```bash
# Basic usage
python tools/generate_postgame_commentary.py "FxCfR-K49T+"

# With options
python tools/generate_postgame_commentary.py "FxCfR-K49T+" \
  --model sonnet --output bin/commentary/ --think-time 50
# --think-time: milliseconds for C++ AI search (passed to generate_commentary_data.run_analyze(), default 50)

# Eval-only mode (skip C++ AI comparison, faster)
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --eval-only

# Validate-only mode (no C++ exe needed at all)
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --validate

# Dry run: show prompts and estimated cost without making API calls
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --dry-run

# Single-pass mode: bypass analysis stage (for comparison)
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --single-pass

# Resume narrative only: re-run Stage 2 from cached analysis
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --resume-narrative

# Force regeneration: ignore all caches
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --force-regen

# Local replay JSON (bypass S3 fetch, useful for testing/offline dev)
python tools/generate_postgame_commentary.py --replay-json path/to/replay.json
```
<!-- APPLIED: Optional #4 (--replay-json) — trivial, useful for testing -->

<!-- CHANGED: Added --dry-run — R2, R5, R7, R10, R11, R12 -->
<!-- CHANGED: Added --single-pass — R7, R10, R11, R12 -->
<!-- CHANGED: Added --resume-narrative — R12 -->
<!-- CHANGED: Added --force-regen — R6 -->

**4b. Pipeline orchestration:**
1. Validate replay code format (alphanumeric + `+` and `@`) before doing any work
<!-- CHANGED: Added input validation — R6 -->
1b. **Cost guard** — If `--max-cost` is set (e.g., `--max-cost 0.10`), estimate total cost from token counts after Phase 1 and abort before any API calls if the estimate exceeds the limit. Print the estimate and suggest `--dry-run` for details.
<!-- APPLIED: Optional #13 (--max-cost budget limit) -->
2. Import `generate_commentary_data` functions directly (clean module, no side effects)
<!-- CHANGED: Resolved import vs subprocess — codebase validated clean — R5, R6, R10, R11, R12 -->
3. Call data extraction → structured JSON (with automatic C++ fallback chain). Validate output against `tools/commentary_schema.json` using `jsonschema.validate()` before proceeding.
4. Run analysis stage → analysis JSON (skip if `--resume-narrative` and cached analysis exists)
5. Run verification pass → warnings list
6. Run narrative stage → commentary text
7. Format and save to `bin/commentary/commentary_{CODE}.txt`
8. Print summary: cost, token counts, time taken, any verification warnings

**4c. Cost tracking** — Print API usage after each run:
```
Commentary generated for FxCfR-K49T+ in 12.3s
  Data extraction: 2.1s (--analyze mode, stepper_reliable=true)
  Analysis: 4,200 input / 1,800 output tokens ($0.008)
  Narrative: 7,500 input / 2,900 output tokens ($0.022)
  Total: $0.030 (would be ~$0.015 with Batch API)
  Verification: 0 warnings
```

<!-- CHANGED: Cost numbers adjusted to reflect realistic token counts — R2, R5, R8 -->
<!-- APPLIED: Optional #8 (structured JSON logging) — useful for tracking costs and quality over time -->

**4c-note: Structured JSON logging** — In addition to console output, write a JSON log per run to `bin/commentary/logs/{CODE}_{timestamp}.json` containing: tokens (input/output per stage), cost, wall-clock time, model used, prompt file versions (hash or mtime), verification warnings, rubric scores (once Phase 6 exists). Enables post-hoc cost analysis and quality tracking.

**4d. `--dry-run` mode** — Run Phase 1 data extraction, build the analysis prompt, and print:
<!-- CHANGED: Added as Phase 4 feature, not Phase 6 — R2, R5 -->
- The exact prompts that would be sent (truncated to first/last 200 chars each)
- Estimated token counts per component
- Estimated cost (sync and batch)
- Data quality assessment
- No API calls made

**4e. Intermediate file caching** — Save intermediate artifacts alongside commentary:
```
bin/commentary/
  commentary_FxCfR-K49T_PLUS_.txt        # Final narrative
  analysis_FxCfR-K49T_PLUS_.json          # Analysis stage output
  data_FxCfR-K49T_PLUS_.json              # Phase 1 structured data
```

<!-- CHANGED: File naming uses _PLUS_ convention consistently — R5, R8 -->

This enables:
- `--resume-narrative`: Re-run narrative stage from cached analysis (most common iteration)
- `--force-regen`: Bypass all caches and re-extract data
- Default: reuse cached `data_*.json` if present (avoids re-running C++), regenerate analysis and narrative

**4f. `--validate` degradation handling** — When running without C++ exe:
<!-- CHANGED: Added explicit degradation specification — R6 -->
- `data_quality.mode` = `"validate"`
- Analysis prompt adapted: no turning points from eval (since no eval data), focus on purchase patterns and strategic arc
- Target message count reduced by 1 (less data = shorter commentary)
- Narrative prompt includes note: "Limited analysis — no neural eval or AI comparison available"
- Commentary header: no special marker (quality difference handled by prompts)

### Files to modify
- `tools/generate_postgame_commentary.py` — Add end-to-end CLI, caching, cost tracking

### Verification checklist
- [ ] Single command produces complete commentary from just a replay code
- [ ] `--eval-only` works without C++ --analyze (faster, less data)
- [ ] `--validate` works without any C++ exe, produces shorter but coherent commentary
- [ ] `--dry-run` shows prompts and costs without API calls
- [ ] `--resume-narrative` reuses cached analysis, only calls narrative API
- [ ] `--single-pass` bypasses analysis stage entirely
- [ ] Intermediate files cached and reused on re-run
- [ ] Cost tracking accurate (compare to API response usage fields)
- [ ] Commentary file naming uses `_PLUS_` / `_AT_` convention
- [ ] Previous commentary versions preserved with timestamp suffix
- [ ] Input validation rejects malformed replay codes early

### Anti-pattern guards
- Do NOT require the C++ exe for basic operation. The `--validate` mode must work with pure Python.
- Do NOT silently overwrite existing commentary files. Always check and rename first.
- Do NOT make API calls in `--dry-run` mode.
- Do NOT use subprocess for `generate_commentary_data.py` — use direct import (verified clean).

---

## Phase 5: Batch Processing Mode

### Goal
Process multiple replay codes in a single batch for cost efficiency (50% Batch API discount + prompt caching amortization).

### What to implement

**5a. Batch CLI:**
```bash
# Process multiple codes from file
python tools/generate_postgame_commentary.py --batch codes.txt

# Where codes.txt contains one replay code per line
# Lines starting with # are comments, empty lines skipped
```

<!-- CHANGED: Removed --batch-codes inline option — R6 (replay codes contain + and @ which complicate CSV parsing) -->

**5b. Batch pipeline:**
1. Phase 1 (data extraction) — Run locally for all codes sequentially (C++ subprocess is CPU-bound, limit concurrency to 1 to avoid x86 OOM)
<!-- CHANGED: Added concurrency limit — R8 -->
2. Stage 1 (analysis) — Submit all as a single Batch API request
3. Poll for batch completion (60s intervals, following `discord_knowledge_extractor.py` pattern)
4. **Check results, separate successes and failures**
<!-- CHANGED: Added partial failure handling — R1, R10, R12, R13 -->
5. Stage 2 (narrative) — Submit only successful analyses as second Batch API request
6. Collect results, format, save files
7. **Final report:** "N games processed, M failed (see batch_errors.json)"

**Batch failure handling:**
<!-- CHANGED: Added explicit failure modes — R10 -->
```python
def handle_batch_results(batch_results):
    """Process analysis batch results with partial failure handling."""
    success_list = []
    failed_list = []

    for code, result in batch_results.items():
        if result.get("error"):
            failed_list.append({"code": code, "error": result["error"]})
            logger.warning(f"Analysis failed for {code}: {result['error']}")
        else:
            success_list.append((code, result))

    if failed_list:
        # Save failures for review
        with open("bin/commentary/batch_errors.json", "w") as f:
            json.dump(failed_list, f, indent=2)
        logger.info(f"{len(failed_list)} games failed analysis, "
                     f"proceeding with {len(success_list)} successful games")

    return success_list, failed_list
```

**5c. Prompt caching for batch** — Structure system prompts so the shared knowledge base is the cached prefix:
```python
system = [
    {
        "type": "text",
        "text": game_rules + commentary_instructions,  # ~3K tokens, shared across all games
        "cache_control": {"type": "ephemeral"}         # See TTL note below
    },
    {
        "type": "text",
        "text": per_game_unit_knowledge   # ~500 tokens, varies per game
    }
]
```

<!-- CHANGED: Fixed cache TTL guidance — R6, R8, R9 -->

**Cache TTL considerations:**
- The shared prefix must be **≥4,096 tokens** for Haiku 4.5 caching to engage. The ~3K game rules alone may be too short — include commentary style guide in the cached prefix to reach the threshold.
- **Batch API processes requests asynchronously** over minutes to hours. The default 5-minute ephemeral TTL (`"cache_control": {"type": "ephemeral"}`) may expire between requests within the same batch. This is a known limitation — cache hit rate in batch mode will be lower than sync.
- **Only `"type": "ephemeral"` is documented** as of Feb 2026. Check [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) for any new TTL options before implementing.
- Cache writes cost more than base input; factor this into cost estimates.

**5d. Checkpoint and resume** — Follow the proven pattern from `discord_knowledge_extractor.py`:
- Save batch IDs to `bin/commentary/batch_status.json`
- `--resume-batch BATCH_ID` to resume polling a submitted batch
- Track which codes completed vs failed
- **On resume, validate that all expected analysis JSONs exist** before submitting narrative batch
<!-- CHANGED: Added dependency validation on resume — R13 -->

**5e. Cost projection** — Before submitting, show estimated cost:
```
Batch: 15 replay codes
  Estimated input: ~63K tokens (analysis) + ~112K tokens (narrative)
  Estimated output: ~27K tokens (analysis) + ~43K tokens (narrative)
  Estimated cost: $0.30-0.45 (Haiku 4.5 Batch, cache hit rate varies)
```

<!-- CHANGED: Removed interactive [y/N] prompt — R5. Use --dry-run instead for cost preview. -->
<!-- CHANGED: Cost estimates revised upward — R2, R5, R8 -->

### Files to modify
- `tools/generate_postgame_commentary.py` — Add `--batch`, `--resume-batch` flags

### Documentation references
- `tools/discord_knowledge_extractor.py` — `extract_batch()` function: batch submission pattern
- `tools/discord_knowledge_extractor.py` — `_poll_batch_status()`: polling loop with status tracking
- `tools/discord_knowledge_extractor.py` — `_process_batch_results()`: results collection and routing

### Verification checklist
- [ ] Batch of 5 codes submits and completes successfully
- [ ] `--dry-run --batch codes.txt` shows estimated cost without submitting
- [ ] Resume works after interruption (kill and restart)
- [ ] Failed codes reported in `batch_errors.json`, successful codes saved
- [ ] Successful games proceed to narrative stage even when some analyses fail
- [ ] Prompt caching active (check cache read tokens in API response)
- [ ] 50% batch discount reflected in billing

### Anti-pattern guards
- Do NOT submit narrative batch before analysis batch completes. Stage 2 depends on Stage 1 output.
- Do NOT use Batch API for single-game processing. Synchronous is faster for one-off commentary.
- Do NOT hardcode batch size limits. Anthropic allows 100K requests per batch.
- Do NOT assume 100% cache hit rate in cost estimates. Batch processing reduces cache effectiveness.
- Do NOT run multiple C++ subprocesses concurrently in batch (x86 OOM risk). Process data extraction sequentially.

---

## Phase 6: Quality Assurance & Iteration

### Goal
Establish quality baselines and iteration workflow for prompt tuning.

<!-- CHANGED: Simplified Phase 6 — removed A/B comparison tool, focused on rubric and iteration workflow — R1, R2, R4, R5, R7, R10, R11, R12, R13 (near-universal) -->

### What to implement

**6a. Quality rubric** — Automated scoring against the game data:
- **Factual accuracy**: % of referenced turns that exist, % of unit names in `deck_units`, winner correct
- **Coverage**: Does commentary mention the biggest eval swing? The decisive factor?
- **Structure**: Correct `== MESSAGE N ==` delimiters, under 2000 chars each, appropriate message count for game length
- **Specificity**: Count of specific turn references, unit name mentions, resource cost references
- **Buy attribution accuracy**: Every specific purchase claim cross-referenced against game data (from expanded verification)

This is NOT an LLM judge — it's a programmatic check against the structured data.

**6b. Test suite** — Run all 3 test replays through the pipeline, verify quality rubric passes:
```bash
python tools/generate_postgame_commentary.py --test
```

<!-- CHANGED: Added iteration workflow — R6 -->

**6c. Prompt iteration workflow:**
When rubric shows failures:
1. Identify which claim type failed (turn reference, buy attribution, eval direction, etc.)
2. Check whether the error originates in analysis JSON or narrative prose
3. If analysis: adjust `analysis_system.md` and re-run `--resume-narrative` to test narrative impact
4. If narrative: adjust `narrative_system.md` and re-run `--resume-narrative` (uses cached analysis)
5. Re-run `--test` to verify fix doesn't regress other replays

**6d. Comparison support** — For manual A/B comparison between settings:
```bash
# Generate with different models, compare manually
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --model haiku --output tmp/haiku/
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --model sonnet --output tmp/sonnet/
diff tmp/haiku/commentary_FxCfR-K49T_PLUS_.txt tmp/sonnet/commentary_FxCfR-K49T_PLUS_.txt

# Compare single-pass vs two-stage
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --single-pass --output tmp/single/
```

No automated comparison tool — use `diff` and human judgement. Build tooling only if manual comparison becomes insufficient.

### Verification checklist
- [ ] All 3 test replays pass quality rubric (factual accuracy >95%)
- [ ] Commentary quality subjectively matches or exceeds manually-written examples
- [ ] Quality rubric catches known bad commentary (test with intentionally degraded prompt)
- [ ] `--test` flag runs all 3 replays and reports pass/fail per rubric dimension
- [ ] Iteration workflow works: edit prompt → `--resume-narrative` → re-check rubric

---

## Implementation Order & Dependencies

```
Phase 1 (Data extraction + unit index)    ← No dependencies, extends existing tool
    ↓
Phase 2 (Analysis stage)                  ← Depends on Phase 1 JSON output
    ↓
Phase 3 (Narrative stage)                 ← Depends on Phase 2 analysis output
    ↓
Phase 4 (End-to-end CLI)                  ← Depends on Phases 1-3
    ↓
Phase 5 (Batch processing)                ← Depends on Phase 4 working for single games
    ↓
Phase 6 (Quality assurance)               ← Depends on Phase 4, iterates on Phases 2-3
```

**Phases 1-4** are the core deliverable. Phases 5-6 are enhancements.

**Before Phase 2:** Run the 3 test replays through Phase 1 `--json-output`, assemble the full analysis prompts in `--dry-run` mode, and measure actual token counts. Update the cost table and token budget breakdown if estimates are off by >20%.

<!-- CHANGED: Added decision gate — R7, R10 -->
**Decision gate after Phase 4:** Run `--single-pass` vs two-stage on all 3 test replays. If single-pass achieves >90% rubric score AND prose quality is comparable, consider collapsing to single-stage for the default mode (keep two-stage as `--quality high`). This costs ~$0.10 in API calls and could save significant implementation complexity.

## Cost Estimates

<!-- CHANGED: All cost estimates revised upward to reflect realistic token counts — R2, R5, R6, R8, R12 -->

| Mode | Per Game | 100 Games | Model | Notes |
|---|---|---|---|---|
| Sync (Haiku 4.5) | ~$0.03 | ~$3.00 | Default | ~12K in + ~5K out total |
| Sync (Sonnet 4.5) | ~$0.12 | ~$12.00 | `--model sonnet` | Same tokens, higher rate |
| Batch (Haiku 4.5) | ~$0.015 | ~$1.50 | `--batch` | 50% discount, variable cache hit |
| Batch (Sonnet 4.5) | ~$0.06 | ~$6.00 | `--batch --model sonnet` | 50% discount |
| Single-pass (Haiku) | ~$0.02 | ~$2.00 | `--single-pass` | One LLM call only |

*Assumes ~5K analysis input + ~8K narrative input + ~5K total output. Cache hit rates estimated at 60-80% for batch mode. Actual costs may vary by game length.*

## Files Summary

| File | Action | Purpose |
|---|---|---|
| `tools/generate_commentary_data.py` | Modify | Add `--json-output` flag, fallback chain, game characteristics |
| `tools/generate_postgame_commentary.py` | **Create** | Main pipeline script (analysis + narrative + CLI + batch) |
| `tools/build_unit_knowledge_index.py` | **Create** | One-time KB → JSON index builder |
| `tools/data/unit_knowledge_index.json` | **Create** | Pre-built unit knowledge lookup table |
| `tools/commentary_schema.json` | **Create** | JSON schema for structured game data |
| `tools/prompts/analysis_system.md` | **Create** | Analysis stage system prompt |
| `tools/prompts/narrative_system.md` | **Create** | Narrative stage system prompt |
| `tools/prompts/narrative_user_template.md` | **Create** | Narrative user message template |
| `bin/commentary/` | Output | Commentary files + intermediate analysis/data JSON |

## Success Criteria

<!-- CHANGED: Revised from v1 to be more precise — R6 -->

| Criterion | Target | How Measured |
|---|---|---|
| Factual accuracy | >95% | Programmatic rubric (turn refs, unit names, eval values, buy attribution) |
| Commentary quality | Match manual examples | Human review (developer judgement) |
| Pipeline reliability | Works on all 3 test replays | `--test` flag |
| Cost per game | <$0.05 sync Haiku | API response usage tracking |
| Latency | <60s end-to-end | Wall clock timing |
| Works without C++ | Yes (`--validate`) | Produces shorter but coherent commentary |
| Graceful degradation | Automatic fallback | `--analyze` timeout → `--eval-only` → `--validate` |

## Scope Boundaries

**In scope:**
- Automated commentary from replay codes (S3)
- Analytical style (expert audience)
- Haiku default, Sonnet opt-in
- Single game and batch processing
- Quality rubric and test suite

**Out of scope (deferred):**
- Style variants (`--style hype/casual`) — add after analytical is proven
- A/B comparison tooling — use manual diff for now
- Commentary for non-expert audiences
- Live game commentary improvements (separate system)
- Integration with Discord bot for auto-posting
- Player statistics or historical data not in replay

## Research Sources

- [AI-Generated Game Commentary: A Survey (arXiv 2506.17294)](https://arxiv.org/html/2506.17294v1) — Multi-type commentary taxonomy, hybrid approach recommendation
<!-- NOTE: Citation date (June 2025) should be verified — R3, R6 flagged potential issues -->
- [WSC Sports Production System (ZenML)](https://www.zenml.io/llmops-database/automated-sports-commentary-generation-using-llms) — 4-stage pipeline, dynamic few-shot, structured data grounding
- [GetStream Real-Time Commentator Lessons](https://getstream.io/blog/ai-football-commentator-lessons/) — Structured data >> raw input, negative results on vision models
- [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — 5-min/1-hr TTL, batch interaction, pricing
- [Anthropic Batch Processing Docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing) — 50% discount, 100K request limit, SDK patterns
- [Anthropic Structured Outputs Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — GA on Haiku 4.5, JSON schema mode
- [PromptingGuide.ai — Prompt Chaining](https://www.promptingguide.ai/techniques/prompt_chaining) — Sequential, branching, iterative architectures

---

## Optional Enhancements (pick what you want)

The following items were suggested by reviewers. Items marked **[APPLIED]** have been incorporated into the main plan. Remaining items are deferred — revisit after the core pipeline is working.

### 1. Style guide extraction instead of full few-shot examples
**What:** Extract a ~500-token "style guide" from the 3 manual commentaries (sentence patterns, vocabulary, structural conventions) and use that instead of 3,500-token full examples. Frees significant context budget.
**Reviewers:** R7, R8, R13
**Effort:** Medium
**Recommendation:** Lean no for now — concrete examples likely outperform abstract rules for Haiku 4.5. Revisit if token budget becomes a bottleneck.

### 2. LLM judge verification after narrative **[APPLIED]**
**What:** After narrative generation, fire a cheap Haiku call: "List every factual claim not directly supported by the analysis JSON." If non-empty, regenerate once. Cost: ~$0.002 per game.
**Reviewers:** R8, R10, R13
**Effort:** Small
**Recommendation:** Lean yes — cheap insurance against hallucinations the programmatic check can't catch. But wait until programmatic checks are proven first.

### 3. Post-narrative verification + repair loop **[APPLIED]**
**What:** If programmatic checks find issues in the narrative, do one cheap repair call: "Here is the commentary. Here are the failed checks. Rewrite only the incorrect sentences; preserve style." Triggers only on failure.
**Reviewers:** R8
**Effort:** Medium
**Recommendation:** Lean yes — elegant approach. Implement after the basic pipeline works.

### 4. `--replay-json` flag for local file input **[APPLIED]**
**What:** Accept a local replay JSON file directly, bypassing S3 fetch. Useful for testing with modified/synthetic replays and offline development.
**Reviewers:** R5
**Effort:** Trivial
**Recommendation:** Lean yes — easy to add and useful for testing.

### 5. Unit synergy detection
**What:** Pre-compute known unit combos (e.g., "Plasmafier + Galvani Drone") from the KB and include synergy notes in the analysis prompt. Currently the pipeline looks at units in isolation.
**Reviewers:** R11, R13
**Effort:** Medium
**Recommendation:** Neutral — could improve analysis quality but adds complexity. Best done after the unit knowledge index is built.

### 6. Sonnet as default for narrative stage
**What:** Use Haiku for analysis (structured output) but Sonnet for narrative (prose quality). Cost increase: ~$0.04/game → ~$0.08/game.
**Reviewers:** R11
**Effort:** Trivial (flag change)
**Recommendation:** Lean no initially — test Haiku first. If narrative quality is insufficient, this is the easiest upgrade path.

### 7. Config YAML for prompts/models
**What:** Move prompt file paths, model selection, think-time defaults into a `config.yaml` for easy A/B testing without code changes.
**Reviewers:** R7
**Effort:** Small
**Recommendation:** Lean no — CLI flags are sufficient for a solo developer. Add if prompt iteration reveals the need.

### 8. Structured JSON logging **[APPLIED]**
**What:** Write JSON logs to `bin/commentary/logs/` with tokens, cost, time, rubric scores, model used, prompt version. Enables post-hoc analysis.
**Reviewers:** R7, R10
**Effort:** Small
**Recommendation:** Lean yes — useful for tracking costs and quality over time. Simple to add alongside existing cost tracking.

### 9. Extended thinking mode as alternative
**What:** Instead of two stages, use Haiku 4.5's extended thinking mode for a single call that thinks internally then writes. Potentially simpler than two-stage.
**Reviewers:** R10
**Effort:** Small to test
**Recommendation:** Neutral — worth a quick test alongside `--single-pass`. Check if extended thinking is available for Haiku 4.5.

### 10. Discord emoji shorthand **[APPLIED]**
**What:** Allow the prompt to use `:unit_name:` placeholders that get replaced with Discord custom emojis already in the server.
**Reviewers:** R13
**Effort:** Trivial
**Recommendation:** Lean yes — nice polish. Add when the commentary is being posted to Discord.

### 11. Constrain "mistake" language to AI-flagged turns **[APPLIED]**
**What:** In the analysis prompt: "Only cite a turn as a mistake if `ai_agrees` is false for that turn." Limits hallucination surface for subjective claims.
**Reviewers:** R4
**Effort:** Trivial (prompt wording)
**Recommendation:** Lean yes — simple guardrail that prevents the model from inventing mistakes where none occurred.

### 12. Reduce analysis schema for V1
**What:** Drop `commentary_hooks` (already done), make `key_decisions` optional, keep schema minimal for V1. Expand fields after validating Haiku's performance.
**Reviewers:** R2, R7
**Effort:** Trivial
**Recommendation:** Neutral — schema is already leaner after removing commentary_hooks. Further reduction depends on how well Haiku fills the remaining fields.

### 13. `--max-cost` budget limit **[APPLIED]**
**What:** Abort if estimated cost exceeds a configurable threshold (e.g., `--max-cost 0.10`). Defensive engineering against unexpectedly large games or prompt blow-up.
**Reviewers:** R6
**Effort:** Small
**Recommendation:** Lean yes — fits the user's cost-conscious profile and prevents surprises.

### 14. Standardize turn indexing convention **[APPLIED]**
**What:** Define a canonical index (ply, round+player, or T-number) used consistently in schema, verification, and prompts. Prevents "T8" vs "round 4, player 1" confusion across the pipeline.
**Reviewers:** R8
**Effort:** Small
**Recommendation:** Lean yes — the plan already uses `ply` in the schema. Codify the display convention: prompts use "Turn N" (round-based) for human readability, schema uses `ply` internally.
