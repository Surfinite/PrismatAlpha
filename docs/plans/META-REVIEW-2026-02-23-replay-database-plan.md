# Meta-Review: Replay Code Database Plan

> **Plan**: `docs/plans/2026-02-23-replay-database-plan.md`
> **Reviews ingested**: 5
> **Date**: Feb 23, 2026

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|----------|-----------|----------------|----------------|
| R1 "The Pragmatist" | Mostly positive, pragmatic concerns | Source merging logic, training_eligible semantics, sources as junction table, players as VIEW | Players table should be a VIEW not a table (avoid sync burden) |
| R2 "The Data Engineer" | Mixed — strong on data quality risks | INSERT OR IGNORE data loss, provenance normalization, incremental import by filename, balance upsert | Source-aware merge priority instead of first-wins |
| R3 "The Integration Architect" | Mixed — concerned about Node.js gap | Node.js bridge, json_insert syntax, old expert file recovery, training_eligible as VIEW, balance_check_version | `better-sqlite3` npm package for direct Node.js access |
| R4 "The Systems Thinker" | Strongly critical — scope/complexity concerns | Merge diff logic, 62K unchecked v2 codes, training flags as views, schema bloat, Pandas alternative | Two-table architecture (core + mutable_flags) for extensibility |
| R5 "The Realist" | Mostly positive, focused on edge cases | NULL deck data loss, processed_codes.txt import, phase collapse, case sensitivity, race conditions | Import processed_codes.txt as extraction tracking data |

---

## A.2 — Consensus Points (2+ reviewers agree)

### High consensus (3+ reviewers)

1. **`INSERT OR IGNORE` risks data loss — use UPSERT with COALESCE** (R1, R2, R4, R5)
   - All four raised concerns about first-wins strategy discarding richer data from later sources.
   - **Codebase validation**: I checked all 19,102 overlapping codes between expert and v2 sources. **Zero metadata conflicts** — every shared field matches exactly when both are non-null. The 74 null-Deck records in expert also have null Decks in v2, so COALESCE wouldn't fix them either. **INSERT OR IGNORE is actually safe for our current data**, but UPSERT with COALESCE is still the correct approach for future-proofing (new sources may have richer data).

2. **`training_eligible` should be a VIEW or computed, not a mutable flag** (R1, R3, R4)
   - A mutable flag drifts as eligibility criteria change. A VIEW dynamically applies current logic.
   - **My assessment**: Agree. `training_eligible` = `balance_passed AND version >= X AND deck IS NOT NULL AND min_rating >= Y` — all computable from existing columns. Use a VIEW.

3. **Sources as a junction table, not a JSON array** (R1, R2, R4)
   - JSON arrays can't be indexed, queried efficiently, or used in JOINs.
   - **My assessment**: Agree in principle, but the actual query patterns ("which sources contributed this code?") are rare and low-volume. The JSON array with `json_each()` is fine for 100K records. However, a junction table is cleaner and more correct. **Should-do**, not must-do.

4. **Schema has too many speculative columns** (R1, R4, R5)
   - `patch_era`, `replay_fetched`, `game_length` are all unpopulated. R4 suggested a two-table split (core + flags).
   - **My assessment**: Partially agree. Remove `patch_era` (easily derived from version). Keep `game_length` and `replay_fetched` as nullable — these will be populated when replays are fetched from S3. No need for a two-table split at this scale.

5. **Players table should be a VIEW** (R1, R3)
   - Maintaining a separate `players` table in sync with `replays` is unnecessary work.
   - **My assessment**: Agree. `CREATE VIEW players AS SELECT ... FROM replays GROUP BY name` is simpler and always accurate.

### Moderate consensus (2 reviewers)

6. **Import `processed_codes.txt` for extraction tracking** (R3, R5)
   - 7 files tracking 30,614 unique codes that have been extracted to training JSONL.
   - **Codebase validation**: Confirmed 7 files exist with 30,614 unique codes. This is valuable data. **Should-do**.

7. **Node.js bridge needed for existing tooling** (R3, R5)
   - `validate_balance_all.js` and `extract_training_data.js` are Node.js — they can't use Python's `sqlite3`.
   - **Codebase validation**: Both scripts currently load JSON files and don't need the DB. The DB is a consolidation layer — existing scripts keep working with JSON. If we want them to use the DB later, `better-sqlite3` npm package (R3's suggestion) is the clean path. **Consider** tier — not blocking.

---

## A.3 — Outlier Points (raised by only one reviewer)

1. **Two-table architecture: core + mutable_flags** (R4)
   - Immutable replay data in one table, all mutable status flags in another.
   - **My assessment**: Over-engineering at 100K rows. One table with nullable columns is simpler. The "mutable flags as views" approach (consensus point #2) already solves the drift problem without table splitting.

2. **Pandas DataFrame + pickle as simpler alternative** (R4)
   - Skip the database entirely, use Pandas.
   - **My assessment**: Reject. Pickle is non-queryable, fragile across Python versions, and doesn't support concurrent access. SQLite is just as easy and vastly more capable.

3. **`json_insert('$[#]')` is libSQL-only, not standard SQLite** (R3)
   - **Codebase validation**: **WRONG.** I tested `json_insert('$[#]', value)` directly in SQLite 3.50.4 via Python `sqlite3` and it works correctly. The `$[#]` append syntax is standard SQLite, not libSQL-specific. Reviewer was mistaken.

4. **Old expert_replays_old_both2000.json may contain unique data** (R3)
   - **Codebase validation**: **WRONG.** Checked — current `expert_replays.json` is a strict superset. Zero unique codes in the old file. Safe to exclude.

5. **Collapse Phase 2 (CLI) into Phase 1** (R5)
   - Write queries alongside schema creation.
   - **My assessment**: Agree — the CLI is small (~100 LOC) and validates the schema immediately. No reason to separate.

6. **Add `balance_check_version` to track which cardLibrary was used** (R3)
   - Know when a validation result is stale.
   - **My assessment**: Good idea. The `version` field on the balance result already exists in `balance_results.json` — just import it. **Should-do**.

7. **Race condition on concurrent DB writes** (R5)
   - Multiple tools writing simultaneously.
   - **My assessment**: Non-issue. WAL mode handles concurrent reads. Writes are single-tool (migration script or CLI). No daemon processes writing to the DB.

8. **Case sensitivity of replay codes** (R5)
   - Could codes differ only in case?
   - **My assessment**: Replay codes are base64-like (alphanumeric + special chars), case-sensitive by design. SQLite `TEXT PRIMARY KEY` is case-sensitive by default. No issue — but worth a note in the schema comments.

---

## A.4 — Category Breakdown

### Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|----------|------------|------------------|------------|
| Two-table core + flags | R4 | Single table works fine at 100K | Reject — over-engineering |
| Sources as junction table | R1, R2, R4 | JSON array works, but junction is cleaner | Should-do |
| Players as VIEW not TABLE | R1, R3 | Current plan has standalone TABLE | Must-do — VIEW is simpler and always correct |
| `training_eligible` as VIEW | R1, R3, R4 | Currently a mutable flag | Must-do — derivable from existing columns |
| `training_extracted` as VIEW/flag from processed_codes | R3, R5 | 30,614 codes tracked in 7 txt files | Should-do — import and track |

### Risks & Concerns

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|----------|------------|------------------|------------|
| INSERT OR IGNORE loses data | R1, R2, R4, R5 | **Zero actual conflicts** in 19K overlapping codes | Switch to UPSERT anyway (future-proofing) — Should-do |
| 62K v2 codes not balance-validated | R2, R4 | Correct — `validate_balance_all.js` only loads 4 source files | Document in plan; not blocking for Phase 1 |
| Incremental import keyed on filename | R2 | Plan uses filename in import_log | Add content hash for safety — Consider |
| NULL deck data loss from INSERT OR IGNORE | R5 | 74 NULL decks, 0 fixable from v2 | UPSERT with COALESCE is the right pattern anyway |

### Suggested Removals / Simplifications

| Feedback | Reviewer(s) | Assessment |
|----------|------------|------------|
| Remove `patch_era` column | R1, R4 | Must-do — derivable from version |
| Remove standalone `players` TABLE | R1, R3 | Must-do — replace with VIEW |
| Collapse Phase 2 into Phase 1 | R5 | Should-do — CLI validates schema |
| Remove Turso Phase 4 details | R4 | Reject — it's clearly marked "Future" |

### Suggested Additions / Features

| Feedback | Reviewer(s) | Assessment |
|----------|------------|------------|
| Import processed_codes.txt | R3, R5 | Should-do — 30K extraction records |
| `balance_check_version` field | R3 | Should-do — already in balance_results.json |
| Content hash for import_log | R2 | Consider — belt-and-suspenders |
| Metadata diff logging during merge | R2, R4 | Consider — zero current conflicts make this low-value |
| `better-sqlite3` for Node.js access | R3 | Consider — not blocking, JSON files still work |
| Result=2 documentation | (codebase) | Must-do — plan says "0=P1 win, 1=P2 win" but Result=2 exists |
| EndCondition value documentation | (codebase) | Should-do — 7 distinct values undocumented |

### Confirmed Good / Keep As-Is

| What | Reviewer(s) |
|------|------------|
| SQLite as database choice | R1, R2, R3, R4, R5 (unanimous) |
| Replay code as natural PK | R1, R3, R5 |
| JSON deck column (Phase 1) + junction table (Phase 3) | R1, R3, R5 |
| Generated columns for rating aggregates | R1, R3 |
| WAL mode | R3, R5 |
| Phase 3 junction table for unit queries | R1, R2, R5 |
| Keep JSON files as source-of-truth backups | R1, R5 |
| Verification checklists | R1, R2, R3 |
| import_log table for provenance | R1, R2 |

---

## A.5 — Conflicts & Contradictions

### 1. Merge strategy: INSERT OR IGNORE vs UPSERT vs source-priority

- **R1, R5**: UPSERT with COALESCE (fill NULLs from later sources)
- **R2**: Source-aware priority ranking (expert > v2 > community)
- **R4**: Log conflicts, alert on differences exceeding thresholds

**Resolution**: Codebase shows **zero actual conflicts** across 19K overlapping records. UPSERT with COALESCE is the right pattern — it handles the theoretical case cleanly without needing priority ranking or diff logging. Source priority ranking is over-engineering given the data reality.

### 2. Schema scope: minimal vs comprehensive

- **R4, R5**: Trim speculative columns, keep schema tight
- **R3**: Add more columns (`balance_check_version`, extraction metadata)

**Resolution**: Remove truly speculative columns (`patch_era`). Keep useful nullable columns (`game_length`, `replay_fetched`). Add `balance_check_version` (exists in source data). Net: slight reduction in column count.

### 3. Phase structure: 5 phases vs collapsed

- **R5**: Collapse Phases 1+2
- **R4**: Remove Phase 4 entirely
- **R1, R2, R3**: Phase structure is fine as-is

**Resolution**: Collapse Phases 1+2 (CLI is small). Keep Phase 4 as documented future path.

---

## A.6 — Recommended Plan Changes

### Must-do (high consensus + high impact)

1. **Replace `training_eligible` flag with a VIEW** — R1, R3, R4. Criteria are computable from existing columns. Eliminates drift.
2. **Replace `players` TABLE with a VIEW** — R1, R3. Always accurate, zero maintenance.
3. **Remove `patch_era` column** — R1, R4. Derivable from `version`. Speculative.
4. **Document Result=2 and EndCondition values** — codebase validation. Plan's schema comment is incomplete (says "0=P1, 1=P2" but Result=2 exists; EndCondition has 7 values: 0,1,2,11,30,31,32).

### Should-do (strong suggestions, meaningful improvement)

5. **Use UPSERT with COALESCE instead of INSERT OR IGNORE** — R1, R2, R4, R5. Even though current data has zero conflicts, UPSERT is the correct pattern for future-proofing.
6. **Import processed_codes.txt extraction status** — R3, R5. 30,614 codes across 7 files. Valuable for `training_extracted` tracking.
7. **Add `balance_check_version` field** — R3. Already exists in `balance_results.json`, trivial to import.
8. **Collapse Phase 2 (CLI) into Phase 1** — R5. CLI is small and validates schema immediately.
9. **Document EndCondition enum values** — codebase validation. Schema should note all 7 values.
10. **Handle 2,963 orphan balance codes** — R2, codebase validation. Balance results contain codes not in any replay file. UPSERT approach naturally handles this (INSERT with balance data, NULL metadata).

### Consider (good ideas, not critical)

11. **Replace `sources` JSON array with junction table** — R1, R2, R4. Cleaner but adds complexity. JSON array works fine at this scale.
12. **Add content hash to import_log** — R2. Detect changed source files. Low value given immutable replay data.
13. **Metadata diff logging during merge** — R2, R4. Zero current conflicts, but could catch future issues.
14. **`better-sqlite3` npm shim for Node.js tools** — R3. Not blocking — JSON files continue working.
15. **Add a `STRICT` table declaration** — R3. Type safety enforcement. Minor change.

### Reject (with reason)

16. **Pandas + pickle alternative** (R4) — Non-queryable, fragile, no concurrent access. SQLite is equally simple and vastly more capable.
17. **Two-table core + mutable_flags architecture** (R4) — Over-engineering at 100K rows. Views solve the mutability concern.
18. **Fix `json_insert('$[#]')` "bug"** (R3) — Not a bug. Tested and confirmed working in SQLite 3.50.4. Standard SQLite, not libSQL-specific.
19. **Import old expert_replays_old_both2000.json** (R3) — Zero unique codes not in current file. Strict subset. No value.
20. **Remove Phase 4 (online access)** (R4) — It's clearly labeled "Future" and documents real upgrade paths. Costs nothing to keep.

---

## A.7 — What Stays

The following elements were confirmed good by reviewers and validated by codebase inspection:

- **SQLite as the database engine** (unanimous)
- **Replay code as natural primary key** (no surrogate ID needed)
- **JSON text column for deck** with `json_each()` for Phase 1 queries
- **Generated STORED columns** for `min_rating`, `max_rating`, `avg_rating`, `deck_size`
- **WAL journal mode** for concurrent readers
- **Phase 3 `replay_units` junction table** with triggers for sync
- **`import_log` table** for provenance tracking
- **JSON source files kept as backups** (DB is consolidation, not replacement)
- **Verification checklists** after each phase
- **Phased approach** with clear deliverables
- **Performance targets** (<5s full import, sub-ms indexed queries)
- **Turso as documented upgrade path** for future online access
