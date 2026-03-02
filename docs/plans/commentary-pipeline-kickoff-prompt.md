## Task: Implement Post-Game Commentary Pipeline (Phase 1)

### Context
We have a fully reviewed and revised implementation plan for an automated post-game commentary pipeline for Prismata replays. The plan went through 13 external reviews and a meta-review, with all must-do and should-do changes applied. Your job is to start implementing it.

### Step 0: Branch Setup
You are starting fresh. Create a new branch from master:

```bash
git checkout master && git pull && git checkout -b feature/postgame-commentary
```

The plan specifies branch name `feature/postgame-commentary`.

### Required Reading (read these BEFORE writing any code)

1. **The Plan** — `docs/plans/2026-02-22-postgame-commentary-pipeline-plan-v2.md` (~1,050 lines)
   - This is your primary reference. Read the FULL document.
   - Pay special attention to Anti-pattern Guards in each phase.
   - The plan has 6 phases. Start with Phase 1 only.

2. **The existing data extraction tool** — `tools/generate_commentary_data.py` (~690 lines)
   - This is the file you'll be extending in Phase 1.
   - It already handles: replay fetching from S3, C++ --analyze/--eval-only/--validate modes, resource validation, buy extraction.
   - It has a clean `__main__` guard — safe to import functions from it.
   - DO NOT rewrite this file. Extend it with `--json-output` flag.

3. **Existing commentary examples** — Read at least 2 files from `bin/commentary/`:
   - `commentary_FxCfR-K49T+_full.txt` (best quality, full analysis)
   - `commentary_WjhmP-WWdXx.txt` (different game style)
   - These are the gold standard the pipeline aims to match.

4. **Knowledge base files** (scan structure, don't memorize):
   - `docs/commentary-knowledge/` — 7 category files, 5,090 lines total
   - `docs/commentary-knowledge/03-advanced-units.md` — unit-specific strategy (key for Phase 1b index builder)
   - `docs/commentary-knowledge/02-base-set-units.md` — base set units
   - `tools/commentary_prompt.md` — condensed 68-line KB for live system

5. **The meta-review** — `docs/plans/META-REVIEW-2026-02-22-postgame-commentary-pipeline-plan.md`
   - Read sections A.5 (Conflicts) and A.6 (Recommended Changes) to understand WHY certain decisions were made.

### Critical Implementation Notes (from QA + meta-review)

- **`--validate` not `--validate-only`**: The actual CLI flag in generate_commentary_data.py is `--validate`. The plan was corrected during QA.
- **`stepper_applied_pct`**: This must be COMPUTED as `applied_clicks / total_clicks` from C++ stepper output. It is NOT a direct C++ output field.
- **Pre-built unit knowledge index**: 12 of 13 reviewers flagged fragile runtime markdown text search. Use `tools/build_unit_knowledge_index.py` to pre-build a JSON index. Runtime does dict lookup only.
- **`ply` indexing**: Use 1-based half-turn index as canonical turn reference throughout. "Turn N" in prose, `ply` in data.
- **Prompt caching**: Use `"type": "ephemeral"` cache_control (NOT `"type": "1h"` which doesn't exist). Minimum 4,096 tokens for Haiku 4.5 cache eligibility. System prompt + KB + few-shot examples should be cached.
- **`time_used`/`time_bank`**: Do NOT include these fields. Stored S3 replays don't have time data (only live wire protocol has it). No reviewer caught this; it was found during codebase validation.
- **Import, don't subprocess**: The plan says to import functions from `generate_commentary_data.py` directly (it has a clean `__main__` guard), NOT to shell out to it as a subprocess.

### Phase 1 Deliverables

The plan's Phase 1 has sub-tasks 1a through 1f. In order:

1. **1a**: Add `--json-output PATH` flag to `generate_commentary_data.py` + output schema
2. **1b**: Build `tools/build_unit_knowledge_index.py` (one-time KB index builder)
3. **1c**: Combine resource validation + C++ eval in one pass for JSON output mode
4. **1d**: Automatic C++ fallback chain (`--analyze` -> `--eval-only` -> `--validate`)
5. **1e**: Pre-compute turning point candidates from eval data
6. **1f**: Pre-compute game characteristics (length, upset detection, etc.)
7. **Schema file**: Create `tools/commentary_schema.json` for validation

### Test Replay Codes

Use these for testing (all confirmed working):
- `FxCfR-K49T+` — medium game, upset, good eval data
- `WjhmP-WWdXx` — different style
- `uP8mG-tr75d` — another variation

### What NOT to Do

- Do NOT modify existing text output modes (`--validate`, `--eval-only`, default)
- Do NOT import the anthropic SDK in Phase 1 (pure local data processing)
- Do NOT start Phase 2 until Phase 1 passes all verification checks in the plan
- Do NOT create a `tools/prompts/` directory yet (that's Phase 2)
- Do NOT delete or reorganize existing code — this is additive

### After Phase 1

When Phase 1 is complete and all verification checks pass, proceed to Phase 2 (Analysis Stage) following the same plan. Each phase has its own verification checklist — use those as your definition of done.

Commit after each phase with a clear message describing what was implemented.
