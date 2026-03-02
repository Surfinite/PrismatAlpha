# Post-Game Replay Commentary Pipeline — Implementation Plan

**Date:** 2026-02-22
**Branch:** `feature/postgame-commentary`
**Status:** PLAN — awaiting review
**Estimated cost:** ~$0.01-0.02 per game (Haiku 4.5 Batch + caching), ~$0.70 for 100 games

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

4. **Batch API + prompt caching stack** — Official Anthropic docs confirm 50% batch discount combines with prompt caching (90% read savings). For 100-game batch: ~$0.70 total.

5. **CoT verification catches hallucinations** — Having the model verify claims against source data in a separate pass catches factual errors (wrong turn numbers, non-existent units, invented purchases).

### Architecture Decision: Two-Stage LLM Pipeline

**Why not single-pass?** A single prompt asking for both analysis AND narrative produces mediocre results at both tasks. The model either:
- Rushes the analysis to get to the narrative (missing key turning points)
- Gets bogged down in data recitation instead of engaging storytelling

**Why not three+ stages?** Per-turn classification as a separate LLM stage adds cost and latency without proportional quality gain. The C++ eval data already provides turn significance (eval swings = turning points). Two LLM stages is the sweet spot.

**The two stages:**

| Stage | Task | Input | Output | Model | Tokens |
|---|---|---|---|---|---|
| **Analysis** | Identify game phases, turning points, key decisions, strategy assessment | Structured game data + KB | JSON (phases, turning points, player assessments) | Haiku 4.5, structured output | ~4K in, ~2K out |
| **Narrative** | Transform analysis into engaging prose | Analysis JSON + few-shot examples | Discord-ready markdown | Haiku 4.5, free-form | ~6K in, ~3K out |

**Why Haiku 4.5 over Sonnet?** The manually-written commentaries prove that the *data quality* (resource-validated buys, neural eval, AI comparison) matters more than model capability. Haiku 4.5 with excellent prompts + few-shot examples + structured data produces quality comparable to Sonnet at 1/3 the cost. We can offer Sonnet as an optional `--quality high` flag.

### What Changes from Live Commentary

| Aspect | Live (current) | Post-game (proposed) |
|---|---|---|
| Context window | Last 5 turns | Full game |
| Token budget | 40-120 per turn | ~3,000 per game |
| Knowledge base | Condensed 68-line prompt | Full 5,090-line KB (relevant sections) |
| Neural eval | Not available | Per-turn eval + AI comparison |
| Few-shot examples | None | 2-3 high-quality commentaries |
| Processing | Single pass, real-time | Two-stage, offline |
| Output format | 1-2 sentences to chat | Multi-message Discord post |
| Batch capability | No | Yes (Batch API, 50% discount) |
| Hallucination check | None | Verification against game data |

---

## Phase 1: Enhanced Data Extraction (`generate_commentary_data.py`)

### Goal
Extend the existing data extraction tool to output a single structured JSON file containing everything the LLM stages need — no further data access required.

### What to implement

**1a. Add `--json-output` flag** that writes structured game data to a JSON file instead of printing text summaries.

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
  "time_control": "180+60/60",
  "random_set": [
    {
      "name": "Plasmafier",
      "cost": "12GGGB",
      "hp": 4,
      "build_time": 1,
      "fragile": false,
      "abilities": "Click: sacrifice a Drone. Gain 4 attack.",
      "supply": 4,
      "tier": "rare"
    }
  ],
  "turns": [
    {
      "round": 1,
      "player": 0,
      "player_name": "Surfinite",
      "buys": ["Drone", "Drone"],
      "eval_pct": 50.0,
      "eval_raw": 0.0,
      "eval_delta": 0.0,
      "ai_buys": ["Drone", "Drone"],
      "ai_agrees": true,
      "time_used": 2.1,
      "time_bank": 177.9,
      "click_count": 4,
      "undo_count": 0,
      "abilities_used": []
    }
  ],
  "analysis": {
    "agreement_rate": 0.733,
    "biggest_mistake": {"round": 7, "player": 1, "eval_drop": 12.45},
    "max_eval_swing": 28.34,
    "stepper_reliable": true,
    "stepper_applied_pct": 0.87
  },
  "unit_knowledge": {
    "Plasmafier": "Drone-eating attack engine. Click sacrifices Drone for 4 burst attack...",
    "Tesla Coil": "Chill unit. Freezes 1 enemy blocker per turn..."
  }
}
```

**1b. Add unit knowledge lookup** — For each random set unit, extract the relevant strategic notes from `docs/commentary-knowledge/03-advanced-units.md` and include them in the JSON. This gives the LLM domain-specific knowledge about the units in play without needing the full 5,090-line KB.

Implementation: Simple text search for unit name headers in the KB files, extract the paragraph(s). Fall back to mergedDeck stats if no KB entry found.

**1c. Combine resource validation + C++ eval in one pass** — Currently `--validate` and default mode are mutually exclusive. The JSON output mode should run both: resource-validated buys (ground truth) AND neural eval per turn.

### Files to modify
- `tools/generate_commentary_data.py` — Add `--json-output PATH` flag, `build_structured_output()` function, unit knowledge lookup
- New file: `tools/commentary_schema.json` — JSON schema for the structured output (for documentation and validation)

### Verification checklist
- [ ] `python tools/generate_commentary_data.py "FxCfR-K49T+" --json-output tmp/test_game.json` produces valid JSON
- [ ] JSON contains all fields from schema above
- [ ] `unit_knowledge` populated for all random set units
- [ ] `buys` arrays match `--validate` output (resource-validated)
- [ ] `eval_pct` and `eval_delta` present for all turns
- [ ] Runs on 3 different replay codes without errors

### Anti-pattern guards
- Do NOT change the existing text output modes (`--validate`, `--eval-only`, default). The `--json-output` flag adds a new output path.
- Do NOT import the anthropic SDK in this file. Stage 1 is pure local data processing.
- Do NOT read the full KB files into memory. Extract only sections relevant to the random set units.

---

## Phase 2: Game Analysis Stage (New File)

### Goal
Create a new script `tools/generate_postgame_commentary.py` that orchestrates the two-stage LLM pipeline. This phase implements Stage 1: structured game analysis.

### What to implement

**2a. Analysis prompt** — System prompt with:
- Condensed game rules (~1,200 tokens, subset of `commentary_prompt.md`)
- Unit-specific knowledge (from Phase 1 JSON `unit_knowledge` field)
- Structured output schema for analysis JSON

**2b. Analysis call** — Single Claude API call with structured output:

```python
analysis_schema = {
    "game_narrative_arc": str,           # 2-3 sentence game summary
    "phases": [
        {
            "name": str,                  # "Opening", "Development", "Midgame", "Endgame"
            "rounds": [int, int],         # Start/end round
            "summary": str,               # 2-3 sentences
            "key_decisions": [str]        # 1-3 critical purchases/strategies
        }
    ],
    "turning_points": [
        {
            "round": int,
            "player": int,
            "description": str,           # What happened
            "impact": str,                # Why it mattered
            "eval_before": float,
            "eval_after": float
        }
    ],
    "player_assessments": [
        {
            "player": str,
            "strategy_summary": str,      # Overall approach
            "strengths": [str],
            "mistakes": [str],
            "notable_turns": [int]
        }
    ],
    "set_analysis": str,                  # What strategies the random set enables
    "decisive_factor": str,               # One sentence: what decided the game
    "commentary_hooks": [str]             # Interesting angles for narrative (upset, time pressure, etc.)
}
```

**2c. Verification pass** — After analysis, do a cheap programmatic check:
- All referenced turn numbers exist in the game data
- All referenced unit names are in the deck
- Eval values cited match actual eval data (within ±2%)
- Player names are correct

This is NOT an LLM call — just Python assertions against the Phase 1 JSON.

### Files to create
- `tools/generate_postgame_commentary.py` — Main pipeline script (CLI entry point)
- `tools/prompts/analysis_system.md` — Analysis stage system prompt (separate file for easy iteration)

### Files to read (patterns to follow)
- `tools/discord_knowledge_extractor.py:1436-1493` — Synchronous API call pattern with retry
- `tools/prismata_commentator.py:70-115` — System prompt construction with cache control
- `tools/prismata_commentator.py:202-209` — API call pattern

### Verification checklist
- [ ] Analysis JSON validates against schema (all required fields present)
- [ ] All turn numbers in `turning_points` exist in game data
- [ ] All unit names in analysis are in the game's deck
- [ ] `phases` cover the full game (no gaps in round ranges)
- [ ] Verification pass catches injected errors (test with deliberately wrong data)
- [ ] Works on all 3 test replays: `FxCfR-K49T+`, `WjhmP-WWdXx`, `uP8mG-tr75d`

### Anti-pattern guards
- Do NOT use structured outputs for the narrative stage (Phase 3). JSON constraints make prose feel mechanical.
- Do NOT skip the programmatic verification. Even with structured output, Haiku can cite non-existent turns.
- Do NOT include the full 5,090-line KB in the system prompt. Use only the condensed game rules (~1,200 tokens) + unit-specific knowledge for units in this game's random set.

---

## Phase 3: Narrative Generation Stage

### Goal
Implement Stage 2 of the pipeline: transform the structured analysis into engaging prose commentary, using few-shot examples for style calibration.

### What to implement

**3a. Few-shot example selection** — Include 1-2 of the best existing commentaries as examples. Selection criteria:
- Use the shortest high-quality example (`bin/commentary/commentary_WjhmP-WWdXx.txt`, 45 lines, ~3,500 tokens) as the primary few-shot
- If the game is long (>20 rounds), also include the longer example (`commentary_uP8mG-tr75d.txt`)
- If the game involves an upset (rating difference >200), include `commentary_FxCfR-K49T+.txt`

Dynamic selection keeps token count controlled while matching style to game characteristics.

**3b. Narrative prompt** — User message with:
- Analysis JSON from Stage 1
- Selected per-turn data (only notable turns, not every turn)
- Tone/format instructions (from `commentary-generation-instructions.md` lines 163-178)
- Target format: `== MESSAGE N ==` delimiters, <2000 chars per message

**3c. Output formatting** — Post-process the raw LLM output:
- Validate `== MESSAGE N ==` delimiters are present
- Check each message is under 2000 characters (Discord limit)
- If a message exceeds 2000 chars, split at the nearest paragraph boundary
- Append replay code link to final message

**3d. Quality flags** — CLI options:
- `--model haiku` (default, ~$0.015/game) — Claude Haiku 4.5
- `--model sonnet` (~$0.08/game) — Claude Sonnet for premium quality
- `--style analytical` (default) — Expert analysis tone
- `--style hype` — Energetic esports caster
- `--style casual` — Accessible for non-expert audience

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

### Anti-pattern guards
- Do NOT use structured output/JSON mode for narrative generation. Free-form text with few-shot examples produces better prose.
- Do NOT include raw turn-by-turn data dumps in the narrative prompt. Feed only the analysis JSON + selected notable turns. The LLM should narrate from the analysis, not re-analyze raw data.
- Do NOT hardcode commentary style. The few-shot examples + style flag should control tone.
- Do NOT exceed 8K input tokens for the narrative call. If analysis + examples exceed this, trim the less relevant few-shot example.

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
  --model sonnet --style hype --output bin/commentary/ --think-time 50

# Eval-only mode (skip C++ AI comparison, faster)
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --eval-only

# Validate-only mode (no C++ exe needed at all)
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --validate-only
```

**4b. Pipeline orchestration:**
1. Call `generate_commentary_data.py` internally (subprocess or import) → structured JSON
2. Run analysis stage → analysis JSON
3. Run narrative stage → commentary text
4. Format and save to `bin/commentary/commentary_{CODE}.txt`
5. Print summary: cost, token counts, time taken

**4c. Cost tracking** — Print API usage after each run:
```
Commentary generated for FxCfR-K49T+ in 12.3s
  Analysis: 3,842 input / 1,456 output tokens ($0.006)
  Narrative: 5,921 input / 2,834 output tokens ($0.020)
  Total: $0.026 (would be $0.013 with Batch API)
```

**4d. Intermediate file caching** — Save analysis JSON alongside commentary:
```
bin/commentary/
  commentary_FxCfR-K49T+.txt        # Final narrative
  analysis_FxCfR-K49T+.json         # Analysis stage output (for debugging/iteration)
  data_FxCfR-K49T+.json             # Phase 1 structured data (for re-running without C++)
```

This enables iterating on the narrative prompt without re-running the expensive C++ analysis.

### Files to modify
- `tools/generate_postgame_commentary.py` — Add end-to-end CLI, caching, cost tracking

### Verification checklist
- [ ] Single command produces complete commentary from just a replay code
- [ ] `--eval-only` works without C++ --analyze (faster, less data)
- [ ] `--validate-only` works without any C++ exe
- [ ] Intermediate files cached and reused on re-run
- [ ] Cost tracking accurate (compare to API dashboard)
- [ ] Commentary file naming follows existing convention
- [ ] Previous commentary versions preserved with timestamp suffix

### Anti-pattern guards
- Do NOT require the C++ exe for basic operation. The `--validate-only` mode must work with pure Python.
- Do NOT silently overwrite existing commentary files. Always check and rename first.
- Do NOT import `generate_commentary_data.py` if it has side effects at module level. Use subprocess if needed.

---

## Phase 5: Batch Processing Mode

### Goal
Process multiple replay codes in a single batch for cost efficiency (50% Batch API discount + prompt caching amortization).

### What to implement

**5a. Batch CLI:**
```bash
# Process multiple codes
python tools/generate_postgame_commentary.py --batch codes.txt

# Where codes.txt contains one replay code per line
# Lines starting with # are comments, empty lines skipped

# Or inline:
python tools/generate_postgame_commentary.py --batch-codes "FxCfR-K49T+,WjhmP-WWdXx,uP8mG-tr75d"
```

**5b. Batch pipeline:**
1. Phase 1 (data extraction) — Run locally for all codes (parallelizable, no API cost)
2. Stage 1 (analysis) — Submit all as a single Batch API request
3. Poll for batch completion (60s intervals, following `discord_knowledge_extractor.py` pattern)
4. Stage 2 (narrative) — Submit all as a second Batch API request
5. Collect results, format, save files

**5c. Prompt caching for batch** — Structure system prompts so the shared knowledge base is the cached prefix:
```python
system = [
    {
        "type": "text",
        "text": game_rules + commentary_instructions,  # ~3K tokens, shared across all games
        "cache_control": {"type": "ephemeral"}         # 5-min cache (batch processes fast)
    },
    {
        "type": "text",
        "text": per_game_unit_knowledge   # ~500 tokens, varies per game
    }
]
```

**5d. Checkpoint and resume** — Follow the proven pattern from `discord_knowledge_extractor.py`:
- Save batch IDs to `bin/commentary/batch_status.json`
- `--resume-batch BATCH_ID` to resume polling a submitted batch
- Track which codes completed vs failed

**5e. Cost projection** — Before submitting, show estimated cost:
```
Batch: 15 replay codes
  Estimated input: ~60K tokens (analysis) + ~90K tokens (narrative)
  Estimated output: ~30K tokens (analysis) + ~45K tokens (narrative)
  Estimated cost: $0.22 (Haiku 4.5 Batch with caching)
  Proceed? [y/N]
```

### Files to modify
- `tools/generate_postgame_commentary.py` — Add `--batch`, `--batch-codes`, `--resume-batch` flags

### Documentation references
- `tools/discord_knowledge_extractor.py:1496-1599` — Batch submission pattern
- `tools/discord_knowledge_extractor.py:1580-1594` — Polling loop with status tracking
- `tools/discord_knowledge_extractor.py:1624` — Results collection from batch

### Verification checklist
- [ ] Batch of 5 codes submits and completes successfully
- [ ] Cost shown before submission, actual cost matches estimate (±20%)
- [ ] Resume works after interruption (kill and restart)
- [ ] Failed codes reported, successful codes saved
- [ ] Prompt caching active (check cache read tokens in API response)
- [ ] 50% batch discount reflected in billing

### Anti-pattern guards
- Do NOT submit narrative batch before analysis batch completes. Stage 2 depends on Stage 1 output.
- Do NOT use Batch API for single-game processing. Synchronous is faster for one-off commentary.
- Do NOT hardcode batch size limits. Anthropic allows 100K requests per batch.

---

## Phase 6: Quality Assurance & Iteration

### Goal
Establish quality baselines and iteration workflow for prompt tuning.

### What to implement

**6a. A/B comparison tool** — Generate commentary with different settings and compare side-by-side:
```bash
python tools/generate_postgame_commentary.py "FxCfR-K49T+" --compare \
  --variant-a "haiku,analytical" --variant-b "sonnet,analytical"
```
Output: Both commentaries saved, plus a diff summary showing where they diverge.

**6b. Quality rubric** — Automated scoring against the game data:
- **Factual accuracy**: % of referenced turns that exist, % of unit names in deck
- **Coverage**: Does commentary mention the biggest eval swing? The decisive factor?
- **Structure**: Correct `== MESSAGE N ==` delimiters, under 2000 chars each
- **Specificity**: Count of specific turn references, unit name mentions, resource cost references

This is NOT an LLM judge — it's a programmatic check against the structured data.

**6c. Test suite** — Run all 3 test replays through the pipeline, verify quality rubric passes:
```bash
python tools/generate_postgame_commentary.py --test
```

### Verification checklist
- [ ] All 3 test replays pass quality rubric (factual accuracy >95%)
- [ ] Commentary quality subjectively matches or exceeds manually-written examples
- [ ] `--compare` produces readable side-by-side output
- [ ] Quality rubric catches known bad commentary (test with intentionally degraded prompt)

---

## Implementation Order & Dependencies

```
Phase 1 (Data extraction)     ← No dependencies, extends existing tool
    ↓
Phase 2 (Analysis stage)      ← Depends on Phase 1 JSON output
    ↓
Phase 3 (Narrative stage)     ← Depends on Phase 2 analysis output
    ↓
Phase 4 (End-to-end CLI)      ← Depends on Phases 1-3
    ↓
Phase 5 (Batch processing)    ← Depends on Phase 4 working for single games
    ↓
Phase 6 (Quality assurance)   ← Depends on Phase 4, iterates on Phases 2-3
```

**Phases 1-4** are the core deliverable. Phases 5-6 are enhancements.

## Cost Estimates

| Mode | Per Game | 100 Games | Model |
|---|---|---|---|
| Sync (Haiku 4.5) | ~$0.02 | ~$2.00 | Default |
| Sync (Sonnet 4.5) | ~$0.10 | ~$10.00 | `--model sonnet` |
| Batch (Haiku 4.5) | ~$0.01 | ~$0.70 | `--batch` |
| Batch (Sonnet 4.5) | ~$0.05 | ~$5.00 | `--batch --model sonnet` |

*Assumes prompt caching active, ~5K input + ~3K output per stage.*

## Files Summary

| File | Action | Purpose |
|---|---|---|
| `tools/generate_commentary_data.py` | Modify | Add `--json-output` flag for structured data |
| `tools/generate_postgame_commentary.py` | **Create** | Main pipeline script (analysis + narrative + CLI) |
| `tools/commentary_schema.json` | **Create** | JSON schema for structured game data |
| `tools/prompts/analysis_system.md` | **Create** | Analysis stage system prompt |
| `tools/prompts/narrative_system.md` | **Create** | Narrative stage system prompt |
| `tools/prompts/narrative_user_template.md` | **Create** | Narrative user message template |
| `bin/commentary/` | Output | Commentary files + intermediate analysis/data JSON |

## External Review Notes

This plan is designed for independent review. Key questions for reviewers:

1. **Is two-stage LLM processing the right split?** Could a single well-prompted call match quality? (Our research says no — WSC Sports and academic survey both recommend multi-stage.)
2. **Is Haiku 4.5 sufficient for narrative quality?** We chose it for cost, but Sonnet may produce significantly better prose. The `--model` flag allows switching.
3. **Should the analysis stage use structured output or free-form JSON?** Structured output guarantees parseable JSON but may constrain the model's reasoning. We chose structured for Stage 1 and free-form for Stage 2.
4. **Is the few-shot example strategy sound?** Using 1-2 real commentaries as examples adds ~3-4K tokens but should dramatically improve style matching.
5. **Should we support streaming output?** Current plan writes complete files. Streaming could show progress for long games but adds complexity.

## Research Sources

- [AI-Generated Game Commentary: A Survey (arXiv 2506.17294)](https://arxiv.org/html/2506.17294v1) — Multi-type commentary taxonomy, hybrid approach recommendation
- [WSC Sports Production System (ZenML)](https://www.zenml.io/llmops-database/automated-sports-commentary-generation-using-llms) — 4-stage pipeline, dynamic few-shot, structured data grounding
- [GetStream Real-Time Commentator Lessons](https://getstream.io/blog/ai-football-commentator-lessons/) — Structured data >> raw input, negative results on vision models
- [Anthropic Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — 5-min/1-hr TTL, batch interaction, pricing
- [Anthropic Batch Processing Docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing) — 50% discount, 100K request limit, SDK patterns
- [Anthropic Structured Outputs Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — GA on Haiku 4.5, JSON schema mode
- [PromptingGuide.ai — Prompt Chaining](https://www.promptingguide.ai/techniques/prompt_chaining) — Sequential, branching, iterative architectures
