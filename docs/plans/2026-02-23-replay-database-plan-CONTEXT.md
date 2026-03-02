# Context Document: Replay Code Database Plan

> **Accompanying plan**: `2026-02-23-replay-database-plan.md`
> **Date**: Feb 23, 2026

---

## 1. Reviewer Brief

You are receiving two documents: this context document and an implementation plan for building a replay code database.

**Your role** is to critically analyze the plan given the context provided. Specifically:

- Identify weaknesses, risks, missing considerations, and better alternatives
- Flag unnecessary complexity or things that should be removed
- Suggest additions, potential future features worth considering, and architectural improvements
- Be constructively critical — not rubber-stamping
- Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable

**Important**: You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making about the code.

### Review Output Format

Structure your review as follows:

1. **One-line verdict**: Your overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess. The plan author will validate these.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

### What is Prismata?

Prismata is a turn-based, perfect-information strategy card game by Lunarch Studios. Think chess meets card games — no hidden information, no randomness (after the initial random set of available units is determined). Each game uses a "dominion" (set) of 8 random units from a pool of ~105, plus 11 base units always available.

### What is PrismataAI?

A C++ game engine and AI system for Prismata, originally by David Churchill (academic research), now extended with neural network evaluation and self-play training. The AI uses Alpha-Beta search, UCT/MCTS, and a phase-decomposition system. Current best model achieves ~52% win rate vs the hardest built-in AI.

### What is the Replay Data?

Every competitive Prismata game generates a unique replay code (e.g., `g5Gc5-KyRph`) that can be used to retrieve the full game state from Lunarch's S3 storage. We have been systematically collecting replay metadata (players, ratings, outcomes, unit sets) from multiple sources to build a training dataset for the neural network.

### Current Stage

This is a **data infrastructure consolidation** task within a mature project. The AI training pipeline is working (722K self-play games, 27M training records in S3). The replay data has been collected across multiple sessions over weeks, accumulating in ad-hoc JSON files. The database is needed to unify querying and support future tools (Discord bot, web app).

### Constraints

- **Solo developer** (one person, using Claude Code as AI assistant)
- **Cost-conscious** — recent AWS bill of $805 was a shock; preference for free/local solutions
- **Windows 11** development machine (AMD Ryzen 7 5700X3D, 32GB RAM, Intel Arc B580 GPU)
- **No timeline pressure** — quality over speed
- **Prismata is a discontinued game** — the replay dataset is essentially static (no significant new games being generated), though the developer still plays occasionally

---

## 3. Architecture & Tech Stack

### Languages & Tools

| Component | Technology |
|-----------|-----------|
| Game engine & AI | C++ (x86, Visual Studio 2022/2025) |
| Training pipeline | Python (PyTorch, numpy), runs on CPU/XPU/CUDA |
| Replay parser | Node.js (JavaScript) |
| Data fetcher (v2) | Python (`fetch_player_replays.py`) |
| Live tools | Python (sniffer proxy, commentator, advisor) |
| Dashboard | Node.js + Express + vanilla JS |
| Self-play infra | AWS EC2 / GCP Compute Engine (Windows instances) |
| Data storage | AWS S3 (`s3://prismata-selfplay-data/`) |
| Already installed | FastAPI 0.129.0, uvicorn 0.40.0, httpx 0.28.1, requests 2.32.5 |
| Already available | Python sqlite3 (SQLite 3.50.4), no additional install needed |

### Data Flow (Simplified)

```
Prismata Stats API ──→ expert_replays.json (v1, 32K codes)
                   ──→ *_all_replays_v2.json (v2, 36 player files, ~80K codes)

Discord/Reddit/Tournament ──→ community code files (4.6K codes)

Sniffer proxy (live games) ──→ prismata_capture_codes.txt (37 codes)

All sources ──→ [THE PLAN: replays.db] ──→ CLI queries
                                        ──→ Training pipeline (balance validation → extract)
                                        ──→ Discord bot / web app (future)

S3 replay storage ──→ validate_balance_all.js ──→ balance_results.json (34K checked)
(full game data)      (fetches each replay,        balance_passed_codes.json (33K passed)
                       checks unit costs)
```

### Key Architectural Decisions Already Made

1. **Replay data lives at `c:\libraries\prismata-replay-parser\`** — a separate repository from the main C++ engine. The database plan places new files here alongside existing data.
2. **Balance validation requires S3 fetches** — the replay metadata (JSON files) only stores unit *names*, not unit *costs*. To verify a game uses current-patch unit costs, each replay must be fetched from S3 (~100 codes/second at 15 concurrency). This is already implemented in Node.js.
3. **Training data extraction is also Node.js** — `extract_training_data.js` fetches full replays from S3 and produces JSONL training files. It uses `processed_codes.txt` files for incremental tracking.

---

## 4. Codebase Map

### Replay Parser Directory (`c:\libraries\prismata-replay-parser\`)

This is where all the replay data lives and where the database would be created:

```
prismata-replay-parser/
├── expert_replays.json           # 32,082 replays, 18 MB (v1 master, from API search)
├── expert_2000_replays.json      # 13,726 replays, 8 MB (filtered ≥2000 rating)
├── expert_1800_replays.json      #  3,420 replays, 2 MB
├── expert_1500_replays.json      #  1,997 replays, 1 MB
├── expert_replays_old_both2000.json # 31,275 replays (older version, superset)
│
├── flopflop_all_replays_v2.json  # 13,461 replays (largest v2 file, 7.2 MB)
├── jamberine_all_replays_v2.json # 11,819 replays
├── ... (34 more *_all_replays_v2.json files, 36 total)
│
├── reddit_valid_replays.json     # 245 replays {code, p1, p2, r1, r2}
├── discord_valid_replays.json    # 2,793 replays {code, status}
├── tournament_valid_replays.json # 960 replays {code, status}
├── discord_replay_codes_all.json # 3,626 bare codes (string array)
│
├── balance_results.json          # 34,957 validation results {code, pass, version, date, sources}
├── balance_passed_codes.json     # 32,973 passed codes (string array)
│
├── fetch_expert_replays.js       # V1 fetcher (API search by rating threshold)
├── fetch_player_replays.py       # V2 fetcher (API search by player name, month-by-month)
├── filter_expert_replays.js      # Rating threshold filter
├── validate_balance_all.js       # Balance checker (S3 fetch, cost comparison)
├── extract_training_data.js      # Training JSONL generator (S3 fetch, per-turn state)
│
├── *_processed_codes.txt         # Incremental tracking (one code per line)
├── lib/                          # Node.js replay parser library
└── ... (20+ other JS scripts for analysis/validation)
```

### PrismataAI Main Directory (relevant files only)

```
PrismataAI/
├── bin/
│   ├── prismata_capture_codes.txt    # Live sniffer captures (TSV, 37 entries)
│   └── asset/config/
│       └── cardLibrary.jso           # Master unit definitions (balance validation reference)
│
├── tools/
│   ├── prismata_sniffer.py           # TCP proxy (captures replay codes, injects chat)
│   └── generate_postgame_commentary.py  # Commentary pipeline (fetches replays from S3)
│
├── training/
│   └── data/unit_index.json          # 161 canonical unit names
│
└── docs/plans/
    └── 2026-02-23-replay-database-plan.md  # THE PLAN
```

### Scale

- **Replay metadata**: ~130 MB across 56 JSON files
- **Training JSONL**: ~14 GB (extracted game states, not part of this plan)
- **Self-play binary shards**: ~178 GB in S3 (not part of this plan)
- **Unique replay codes**: ~98,474 across all sources

---

## 5. Relevant Existing Patterns & Conventions

### Data Format Conventions

**Replay record schema** (15 fields, identical across v1 and v2 sources):
```json
{
    "Code": "g5Gc5-KyRph",
    "Format": 200,
    "Deck": ["Ossified Drone", "Ferritin Sac", "Venge Cannon", ...],
    "Result": 0,
    "EndCondition": 0,
    "TimeCondition": 20,
    "StartTime": 1771604164,
    "EndTime": 1771604611,
    "Version": 769,
    "P1Name": "Lycomedes",
    "P1RatingIni": 2152.12,
    "P1RatingChange": 5.77,
    "P2Name": "flopflop",
    "P2RatingIni": 2138.99,
    "P2RatingChange": -5.84
}
```

**Field name inconsistency**: Expert and v2 files use `Code` (capital C). Community files use `code` (lowercase). The `reddit_valid_replays.json` uses different field names entirely: `{code, p1, p2, r1, r2}`.

**Replay code format**: 11 characters, base64-like with special characters (`+`, `@`, `-`). Examples: `g5Gc5-KyRph`, `+BSp9-NTWUZ`, `5sw@m-CSRN@`. The `-` at position 6 appears consistent.

**Deck field**: JSON array of display-name strings (e.g., `"Tarsier"` not `"Tesla Tower"`). Always 8 random units (the dominion). Can be `null` for some older records.

### Incremental Processing Pattern

All existing tools use the same pattern:
1. Read a `*_processed_codes.txt` file (one code per line)
2. Load source data, skip already-processed codes
3. Process new codes
4. Append to output + update processed_codes.txt

The database plan's incremental import (Phase 3) should be compatible with this pattern.

### Balance Validation

The existing `validate_balance_all.js` loads 4 source files (expert, discord, tournament, reddit), fetches each replay from S3, checks unit costs against `cardLibrary.jso`, and writes results to `balance_results.json`. It does NOT currently load v2 per-player files — this is a known gap.

Failure reasons:
- `balance_mismatch` (1,183 codes) — unit costs differ from current patch
- `event_mode` (801 codes) — event/special modes with starred units

### Testing Strategy

There are no automated tests for the replay parser scripts. Validation is done by manual inspection and cross-referencing counts. The plan's verification checklists serve as the test suite.

---

## 6. Current State & Known Issues

### What Works Today

- **V1 expert replay collection**: `fetch_expert_replays.js` incrementally fetches from the prismata-stats API. 32,082 replays collected with `lower_rating=2000`.
- **V2 per-player collection**: `fetch_player_replays.py` fetches all rated games for a specific player, month-by-month with adaptive range splitting for saturated months. 36 players collected, ~80K unique codes.
- **Balance validation**: 34,957 codes checked, 32,973 passed. But 62,641 v2 codes haven't been checked yet.
- **Training data extraction**: Produces JSONL files from S3 replay fetches. Incremental via processed_codes.txt.
- **Live capture**: Sniffer proxy captures replay codes from games played/spectated through the proxy.

### Known Issues / Technical Debt

1. **No unified query interface**: Answering "how many training-ready codes?" requires loading ~25 files, deduplicating, and cross-referencing. This is the primary motivation for the database.
2. **V2 codes not in balance validator**: 62,641 codes haven't been checked. The validator script only loads v1 sources.
3. **Redundant data**: Same games appear in multiple files (expert + v2 + community overlap). ~18K codes are shared between v1 and v2.
4. **Schema inconsistencies**: Different field names across sources (see §5).
5. **No version/patch tracking**: No easy way to filter "current patch only" games.
6. **Processed_codes.txt files are fragile**: Plain text, no timestamps, no error tracking.
7. **Mixed languages**: Fetchers are Python (v2) and Node.js (v1, validation, extraction). The database scripts would be Python, adding to the polyglot nature.

### Recent Changes

- **Feb 22-23**: Bulk collection of v2 per-player replays (36 players, 96K+ total records)
- **Feb 22**: Engine logic audit (C++ vs AS3 ground truth comparison) — separate effort, not related to replay database
- **Feb 20**: Self-play data audit completed (722K games, 27M records, all clean)
- **Feb 15**: Balance validation pipeline created

---

## 7. Context Specific to the Plan

### What the Plan Touches

The plan creates 4-5 new Python files in the `prismata-replay-parser/` directory. It reads from all existing JSON data files but does **not modify them**. The database is positioned as a consolidation layer — JSON files remain as source-of-truth backups.

### Prior Approaches

Before this plan, the project used:
- **Ad-hoc Python one-liners** to count/filter across JSON files (slow, error-prone, non-reusable)
- **Separate `*_codes.txt` lists** for each filtered subset (redundant, hard to maintain)
- **`balance_results.json`** as the only cross-source tracking mechanism

No previous database attempt has been made. The plan represents the first structured data consolidation effort.

### Dependencies & Integrations

| System | Interaction |
|--------|------------|
| `validate_balance_all.js` (Node.js) | Currently writes `balance_results.json`. The DB imports this. Future: could read unvalidated codes from DB. |
| `extract_training_data.js` (Node.js) | Currently uses `processed_codes.txt`. Future: could mark codes as extracted in DB. |
| `fetch_player_replays.py` (Python) | Produces v2 JSON files. DB imports these. New players would use `--incremental`. |
| S3 replay storage | Not directly accessed by the DB. Balance validation and training extraction fetch from S3 separately. |
| `cardLibrary.jso` (C++) | Reference for balance validation. DB doesn't access this — validation results are imported. |
| Sniffer (`prismata_sniffer.py`) | Writes `prismata_capture_codes.txt`. DB imports this. |

### Performance Considerations

Benchmarked on SQLite 3.50.4 (in-memory):

| Operation | 50K rows | Projected 1M rows |
|-----------|----------|-------------------|
| Bulk insert | 0.54s | ~11s |
| `COUNT WHERE rating > X` (indexed) | 1.2ms | ~25ms |
| `json_each()` GROUP BY (8-element arrays) | 319ms | ~6.4s |
| Player lookup (indexed) | 0.1ms | ~0.1ms |
| Unit search via `json_each()` WHERE | 106ms | ~2.1s |
| Unit search via junction table (Phase 3) | <1ms | <1ms |

The `json_each()` approach is the known bottleneck. At 100K rows it's acceptable (~640ms). At 1M rows, interactive unit queries would be slow (~2-6s) without the junction table from Phase 3.

### Security Considerations

- The database contains only game metadata — no personal data, credentials, or sensitive information
- Player names are public (visible in-game and on the prismata-stats website)
- Replay codes are publicly accessible (anyone can view any replay with the code)
- The FastAPI path (Phase 4B) should still implement rate limiting and input sanitization to prevent SQL injection, even though the data is non-sensitive

---

## 8. Scope Boundaries

### Explicitly Out of Scope

| What | Why |
|------|-----|
| Storing full replay game states | Too large (~1-10 MB per replay × 100K = terabytes). S3 is the source. |
| Replacing the Node.js training extraction pipeline | Works fine. DB is for metadata, not game state parsing. |
| Migrating balance validation to Python | The Node.js validator works. DB just imports its output. |
| Real-time ingestion from Prismata servers | The game is discontinued. Data collection is batch/manual. |
| User authentication for the API | Non-sensitive public data. Add later if needed. |
| Mobile app or complex web frontend | Phase 4 is a simple REST API, not a full application. |

### Fixed / Non-Negotiable Decisions

1. **SQLite** — already decided after comparing 6 database options. PostgreSQL, DuckDB, Firebase all evaluated and rejected for specific reasons. Don't suggest switching to PostgreSQL.
2. **Python** for all new code — the v2 fetcher and most tools are already Python. Node.js is legacy (v1 scripts).
3. **Keep JSON files** — the DB is additive, not a replacement. Must be rebuildable from source JSON at any time.
4. **Replay code as natural primary key** — codes are globally unique, immutable, and the universal identifier.
5. **Location in `prismata-replay-parser/`** — where the data lives.

### Accepted Trade-Offs

- **`json_each()` is slow at 1M rows** — acceptable because Phase 3's junction table solves it, and 1M is a future scenario
- **No ORM** — raw `sqlite3` module. Deliberate simplicity for a solo developer.
- **No automated tests** — verification checklists serve as the test suite. Consistent with the rest of the replay parser codebase.
- **Mixed Python/Node.js ecosystem** — adding Python DB tools alongside existing Node.js scripts. Accepted because Python is the direction of travel.

---

## 9. Success Criteria

### Must-Have (Phase 1-2)

1. **Single `replays.db` file** containing all ~98K unique replay codes with metadata
2. **Zero data loss**: every code from every source file appears in the DB
3. **Deduplication**: no duplicate codes, source provenance tracked
4. **Balance validation imported**: 34,957 validation results reflected in the DB
5. **Common queries run in <1 second**: training-ready count, rating filters, player lookups
6. **CLI tool answers "how many training-ready codes?"** in one command
7. **Full rebuild from JSON** takes <10 seconds

### Should-Have (Phase 3)

8. **Unit-based queries run in <10ms** at any scale (junction table)
9. **Incremental import** for new player data without full rebuild

### Nice-to-Have (Phase 4)

10. **Remote queryability** from a Discord bot or web app
11. **API response time <200ms** for common queries

### Non-Goals

- Replacing existing Node.js scripts
- Sub-millisecond query performance on all query types
- Multi-user concurrent write support

---

## 10. Key Questions for Reviewers

1. **Source merging strategy**: The plan uses `INSERT OR IGNORE` (first source with full metadata wins) plus a second pass to update the `sources` JSON array. Is this the right approach? What happens when the same game appears in expert (with full metadata) AND a v2 file (also with full metadata but possibly different rating precision)?

2. **Schema future-proofing**: The plan includes future columns (`game_length`, `replay_fetched`, `patch_era`) as nullable placeholders. Is this good schema design, or should these be deferred entirely? At what point does the schema have too many columns for a single table?

3. **Junction table timing**: Phase 3 defers the `replay_units` junction table. Given the plan targets 1M rows eventually, should the junction table and triggers be part of Phase 1 from the start? Or is the phased approach correct?

4. **Training pipeline integration**: The plan tracks `training_eligible` and `training_extracted` flags but doesn't modify the Node.js extraction pipeline. Is a Python-only database useful if the main consumers (validation, extraction) are Node.js? Should the plan include a thin Node.js adapter or at minimum a JSON export?

5. **Online access path**: The plan documents two future paths (Turso vs FastAPI). Should it commit to one now, or is leaving both options open the right call? Does the Turso free tier's startup risk concern you?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|------|-----------|
| **Replay code** | Unique 11-character identifier for a Prismata game (e.g., `g5Gc5-KyRph`). Used to fetch full game data from S3. |
| **Dominion / Deck** | The set of 8 random units available in a specific game (from ~105 total). Plus 11 base units always available. |
| **Balance validation** | Checking that a replay's unit costs match the current game patch. Games from old patches may have different unit costs, making them unsuitable for training. |
| **Balance pass** | A replay whose unit costs match the current `cardLibrary.jso`. Safe for training. |
| **Event mode** | Special game format with modified rules/units (starred units). Not suitable for training. |
| **V1 source** | Replays collected via `fetch_expert_replays.js` (API search by rating threshold). 32K codes. |
| **V2 source** | Replays collected via `fetch_player_replays.py` (API search by player name). 80K codes. V2 captures games V1 missed (e.g., expert vs sub-2000 opponent). |
| **prismata-stats API** | Third-party replay search API at `prismata-stats.web.app`. Returns max 100 results per query. |
| **S3 replay storage** | Lunarch's S3 bucket where full game replays are stored as gzipped JSON. URL pattern: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz`. |
| **mergedDeck** | The full card data inside a fetched S3 replay (includes unit costs, build times, abilities — not just names). |
| **cardLibrary.jso** | The C++ engine's master unit definition file. Contains internal names, display names, costs, and abilities for all ~105 units. Used as ground truth for balance validation. |
| **Training eligible** | A replay code that has passed all checks: balance validated, correct patch version, rated game, no weird units. |
| **Sniffer** | A Python TCP proxy (`prismata_sniffer.py`) that intercepts Prismata client-server traffic for live game state capture, chat injection, and replay code collection. |
| **Turso** | A hosted SQLite service (SQLite-as-a-service) using libSQL. Allows remote HTTP queries against a SQLite database. Free tier: 5GB, 500M reads/month. |
| **WAL mode** | Write-Ahead Logging — a SQLite journal mode that allows concurrent readers while one writer is active. Must be set on file-based databases (not in-memory). |
| **Generated column** | A SQLite column whose value is automatically computed from other columns (e.g., `min_rating = MIN(p1_rating, p2_rating)`). Can be STORED (persisted) or VIRTUAL (computed on read). |
| **`json_each()`** | A SQLite table-valued function that expands a JSON array into rows. Used to query the `deck` column (e.g., "find all games containing Tarsier"). |
| **Junction table** | A many-to-many relationship table (e.g., `replay_units` linking codes to unit names). Faster than `json_each()` for indexed lookups at scale. |
| **Self-play** | AI playing against itself to generate training data. Produces binary `.bin` shards stored in S3 (~722K games, 27M records, 178 GB). Separate from replay data. |
| **OriginalHardestAI** | The baseline AI opponent used for evaluation. Current best model: 51.9% win rate. |
