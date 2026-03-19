# Design Spec: JS Engine Extraction Pipeline

> **Date**: 2026-03-19
> **Goal**: Replace the Python replay simulator with JS engine extraction for ground-truth per-turn data, keeping Python as the orchestrator, DB manager, and analysis layer
> **Supersedes**: The simulator component of `2026-03-18-opening-book-analysis-design.md` (DB schema, analysis queries, and OB derivation workflow from that spec remain valid)
> **Key insight**: The JS engine fully simulates every game via `beginTurnHistory` snapshots — fighting for accuracy in a Python reimplementation is the wrong investment

---

## 1. Architecture Overview

```
replay .json.gz files (102k in replays_archive/)
         |
         v
+-------------------------------------+
|  Python CLI (replay_parser/__main__) |  <-- User-facing entry point
|  * Queries DB for unparsed codes     |
|  * Writes temp codes file            |
|  * Spawns: node bulk_extract.js      |
|  * Reads JSONL from stdout           |
|  * Inserts into DB                   |
|  * Runs verification checks          |
+------------------+-------------------+
                   | subprocess (stdout JSONL)
                   v
+-------------------------------------+
|  JS bulk_extract.js                  |
|  * Loads replay .json.gz             |
|  * Analyzer auto-play (full sim)     |
|  * Extract from beginTurnHistory:    |
|    - Supply diffs -> buys            |
|    - Mana -> resources               |
|    - Table -> units_owned            |
|  * Resolve commandList clicks        |
|    against game state -> actions     |
|  * Output: 1 JSONL line per replay   |
+-------------------------------------+
                   |
                   v
+-------------------------------------+
|  SQLite (replays.db)                 |
|  * turn_buys   (supply-diff buys)    |
|  * turn_state  (resources + units)   |
|  * turn_actions (resolved clicks)    |
|  * replay_parse_status (tracking)    |
+-------------------------------------+
```

### Design Principles

1. **JS engine is the single source of truth** — Python never interprets game mechanics
2. **Supply diffs, not unit diffs** — Buys derived from per-player supply array changes between turn boundaries (immune to combat deaths, ability-created units, self-sac)
3. **Resolved actions only** — `turn_actions` stores what actually happened after undo/revert resolution, no noise
4. **Built-in verification** — Every turn carries a self-consistency check comparing supply-diff buys against unit-count-diff buys
5. **DB schema unchanged** — Same four tables from the original spec; data source changes from Python simulator to JS engine

---

## 2. JS Extraction: `bulk_extract.js`

### 2.1 CLI Interface

```bash
# Single replay (pretty-printed JSON to stdout)
node js_engine/bulk_extract.js <replay.json.gz>

# Batch mode (JSONL to stdout, progress to stderr)
node js_engine/bulk_extract.js --batch <codes_file> --replays-dir <dir> [--limit N]
```

### 2.2 Output Format

Each JSONL line is one replay:

```json
{
  "code": "Uim7C-wPvMo",
  "result": 1,
  "totalTurns": 24,
  "error": null,
  "turns": [
    {
      "global_turn": 0,
      "player": 0,
      "player_turn": 1,
      "buys": ["Drone", "Drone"],
      "resources": {
        "gold": 6, "green": 0, "blue": 0,
        "red": 0, "energy": 0, "attack": 0
      },
      "units_owned": {"Drone": 6, "Engineer": 2},
      "total_units": 8,
      "actions": [
        {"type": "ability_shift", "unit": "Drone", "count": 6},
        {"type": "buy", "unit": "Drone", "count": 1},
        {"type": "buy", "unit": "Drone", "count": 1},
        {"type": "commit"},
        {"type": "commit"}
      ],
      "verification": {
        "supply_diff_buys": ["Drone", "Drone"],
        "unit_diff_buys": ["Drone", "Drone"],
        "consistent": true,
        "building": ["Tarsier"]
      }
    }
  ]
}
```

### 2.3 Buy Extraction: Supply Diffs

For each turn N where player P is active:

```
If P=0 (White): buys[cardId] = whiteSupply_at_N[cardId] - whiteSupply_at_N+1[cardId]
If P=1 (Black): buys[cardId] = blackSupply_at_N[cardId] - blackSupply_at_N+1[cardId]
```

**Why supply diffs, not unit count diffs:**

| Scenario | Unit count diff | Supply diff |
|---|---|---|
| Buy + combat death same turn | Missed (net 0) | Correct |
| Ability-created unit (Steelforge->Steelsplitter) | False positive buy | Correct (supply unchanged) |
| Self-sac after buy same turn | Missed | Correct |
| Buy then un-buy (resolved before next turn) | Correct (net 0) | Correct (net 0) |

Supply is per-player (not shared). Each player starts with the same supply per card type (derived from rarity), tracked independently via `whiteSupply[]` and `blackSupply[]` in the State object. A player's supply only changes on their own turn.

**Source data**: `beginTurnHistory` contains full State clones with deep-copied `whiteSupply[cardId]` and `blackSupply[cardId]` arrays (State.js:111-122). These are the authoritative record.

### 2.4 Resources & Units: Direct State Reads

- **Resources**: `parseMana(state.whiteMana)` or `parseMana(state.blackMana)` depending on active player. Direct ground truth from the engine's Mana objects.
- **Units owned**: Count alive units in `state.table` for the active player. The table only contains live units (`deadness === C.DEADNESS_ALIVE`); dead units are removed.
- Both are direct reads from `beginTurnHistory` snapshots — no computation or approximation.

### 2.5 Mana String Parsing

Carried forward from `extract_turn_data.js` (verified correct):

| Character | Resource |
|---|---|
| Digits (`0-9`) | Gold (accumulate, e.g., `12` = 12 gold) |
| `G` | Green |
| `B` | Blue |
| `C` | Red |
| `H` | Energy |
| `A` | Attack |

### 2.6 Click Resolution: Resolved Actions

Walk the `commandList` slice for each turn, resolve to action records.

**Step 1: Undo/revert preprocessing**

Remove clicks cancelled by explicit undo/revert:
1. Walk clicks left-to-right, build a stack
2. `revert clicked` -> clear all actionable clicks and phase markers from stack
3. `undo clicked` -> pop most recent actionable click from stack
4. Emotes -> skip entirely
5. Everything else -> push to stack

Output is the resolved click sequence.

**Step 2: Phase tracking**

Track phase using `space clicked` count within each turn:
- **Phase 0** (before first space): Defense — `inst clicked` = blocker assignment
- **Phase 1** (after first space): Action — `inst clicked` = ability, `card clicked` = buy
- **Phase 2+** (after second space): Turn over, animation markers only

**Step 3: Instance resolution**

For `inst clicked` / `inst shift clicked` in action phase, classify using instance IDs:

1. From `beginTurnHistory[N].table`, build a lookup: `instanceId -> unit type` for all alive units at turn start
2. Record the max instance ID present at turn start
3. For each `inst clicked _id=X`:
   - If `X > maxId` at turn start -> this is an **un-buy** (targeting a unit purchased during this turn)
   - If `X <= maxId` and found in turn-start table -> **ability activation** (resolve to unit name)
   - If `X <= maxId` and in defense phase -> **defense assignment**

This sidesteps resource tracking entirely — the game's sequential instance ID assignment is the signal.

**Step 4: Output action records**

| Click type | Phase | Resolution | Action output |
|---|---|---|---|
| `card clicked` | Action | Look up `mergedDeck[_id]` | `{"type": "buy", "unit": "Tarsier", "count": 1}` |
| `card shift clicked` | Action | Look up card, count from supply diff | `{"type": "buy_shift", "unit": "Drone", "count": 3}` |
| `inst clicked` | Action, in table | Ability activation | `{"type": "ability", "unit": "Synthesizer", "count": 1}` |
| `inst shift clicked` | Action, in table | All instances of type | `{"type": "ability_shift", "unit": "Drone", "count": 6}` |
| `inst clicked` | Action, > maxId | Un-buy | `{"type": "unbuy", "unit": "Drone", "count": 1}` |
| `inst clicked` | Defense | Blocker assignment | `{"type": "defend", "unit": "Wall", "count": 1}` |
| `space clicked` | Any | Phase commit | `{"type": "commit"}` |

Un-buys are kept in the actions list as deliberate player actions (distinct from undo/revert noise which is stripped). The `turn_buys` table has the net result from supply diffs regardless.

### 2.7 Verification Block

Each turn carries a self-consistency check:

```json
"verification": {
  "supply_diff_buys": ["Tarsier", "Drone"],
  "unit_diff_buys": ["Tarsier", "Drone"],
  "consistent": true,
  "building": ["Tarsier"]
}
```

- **`supply_diff_buys`**: Ground-truth buys from supply array diffs (authoritative)
- **`unit_diff_buys`**: Buys computed from alive-unit-count diffs (for comparison)
- **`consistent`**: `true` when both methods agree
- **`building`**: Units in `supply_diff_buys` with `buildTime > 0` (not usable until later — relevant for opening analysis)

When `consistent: false`, legitimate causes are:
- Combat deaths (unit-diff undercounts)
- Ability-created units like Steelforge->Steelsplitter (unit-diff overcounts)
- Self-sac after buy in same turn (unit-diff undercounts)

A `consistent: false` with none of these explanations is a real bug.

---

## 3. Python Pipeline Changes

### 3.1 Modified Pipeline Flow

```python
def run_pipeline(db_path, replays_dir, codes, force, fetch):
    conn = connect(db_path)
    migrate(conn)
    codes = get_eligible_codes(conn, codes, force)

    # Spawn JS extraction (replaces Python simulate())
    for entry in run_js_extraction(codes, replays_dir):
        if entry.get("error"):
            mark_error(conn, entry["code"], entry["error"])
            continue
        ingest(conn, entry)

    run_verification(conn, codes)
    conn.close()
```

### 3.2 JS Subprocess Management

```python
def run_js_extraction(codes, replays_dir):
    """Spawn node bulk_extract.js, yield parsed JSONL entries."""
    codes_file = write_temp_codes_file(codes)
    proc = subprocess.Popen(
        ["node", "js_engine/bulk_extract.js", "--batch", codes_file,
         "--replays-dir", replays_dir],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1  # line-buffered
    )
    for line in proc.stdout:
        if line.strip():
            yield json.loads(line)
    # stderr contains progress messages — log them
```

Streaming line-by-line: Python inserts into the DB as replays are extracted. No need to buffer the full 102k dataset in memory.

### 3.3 DB Ingestion

`ingest(conn, entry)` replaces the current `store(conn, ReplayData)`. Same INSERT statements targeting the same tables, but reads from JSON dict instead of Python dataclass:

- `turn_buys`: `entry["turns"][i]["buys"]` -> `buy_sequence` (JSON array) + `buy_hash` (sorted, comma-joined)
- `turn_state`: `entry["turns"][i]["resources"]` + `entry["turns"][i]["units_owned"]`
- `turn_actions`: `entry["turns"][i]["actions"]` -> one row per action
- `replay_parse_status`: `parser_version=2` to distinguish JS-extracted data from Python-parsed (version 1)

### 3.4 CLI Interface

```bash
# Full pipeline (default — extract + ingest + verify)
python -m replay_parser --db replays.db --replays-dir ./replays_archive/

# Parse specific codes
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ \
    --codes "Uim7C-wPvMo,ABC123"

# Fetch + parse new replays
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ \
    --fetch --codes-file new_codes.txt

# Single replay to stdout (no DB)
python -m replay_parser --replay path/to/replay.json.gz --json

# Verification-only (no extraction)
python -m replay_parser --verify --db replays.db

# Cross-validation (Layer A + B)
python -m replay_parser --cross-validate --db replays.db \
    --replays-dir ./replays_archive/ --sample 500

# Force re-parse (ignore already-parsed)
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ --force
```

---

## 4. Verification System

### 4.1 Layer B: Self-Consistency (Primary)

Built into every extraction run. For each turn, the `verification` block compares supply-diff buys against unit-count-diff buys.

**Aggregated report after extraction:**

```
Verification summary: 102,697 replays
  Turns processed: 1,847,234
  Consistent: 1,612,408 (87.3%)
  Inconsistent: 234,826 (12.7%) -- expected, combat/ability/sac turns

  Inconsistency breakdown:
    Turns with combat deaths: 198,412
    Turns with ability-created units: 31,204
    Turns with self-sac-after-buy: 5,210
    UNEXPLAINED: 0  <-- this is the bug signal
```

A `consistent: false` turn where none of the known causes apply is flagged as `UNEXPLAINED` — these are real bugs requiring investigation.

Detection of known causes (computed from `beginTurnHistory` diffs):
- **Combat deaths**: Unit present in turn N table, absent in turn N+1 table, not self-sacced
- **Ability-created units**: Unit in turn N+1 table that isn't in turn N supply diff and wasn't in turn N table
- **Self-sac after buy**: Unit in supply diff (bought), absent from turn N+1 table, card has `selfsac: true`

### 4.2 Layer A: Cross-Validation Against Python (Secondary)

Run Python parser on the same replays, compare `turn_buys` for player turns 1-3 where Python is 99%+ accurate.

**Interpreting flags:**
- Layer B `consistent: true` + Layer A disagrees -> likely Python parser bug (expected, especially turns 2-3)
- Layer B `consistent: true` + Layer A disagrees + **turn 1** -> investigate, possible JS bug
- Layer B `consistent: false` + Layer A disagrees -> expected divergence, supply-diff is correct

Flagged cases are for manual review in the replay viewer.

### 4.3 Torture Test

`Uim7C-wPvMo` is included in every verification pass. This replay exercises edge cases the Python parser struggled with (complex buy/unbuy chains, turn boundary misalignment). Its output is compared against known-good values verified once in the live client.

---

## 5. File Changes

### New Files

| File | Description |
|---|---|
| `js_engine/bulk_extract.js` | Core JS extractor: auto-play, supply-diff buys, click resolution, verification, JSONL output |

### Modified Files

| File | Change |
|---|---|
| `replay_parser/pipeline.py` | Replace `simulate()` with `run_js_extraction()` subprocess + `ingest()` |
| `replay_parser/database.py` | Replace `store(ReplayData)` with `ingest(dict)` reading from JSON. Schema unchanged |
| `replay_parser/__main__.py` | Add `--verify` and `--cross-validate` CLI flags |
| `replay_parser/cross_validate.py` | Add Layer B self-consistency checks alongside existing Layer A |

### Unchanged Files

| File | Reason |
|---|---|
| `replay_parser/models.py` | Type definitions still useful for package consumers |
| `replay_parser/decoder.py` | Used by `--replay` single-file mode and fetch flow |
| `replay_parser/fetch.py` | Unchanged |
| `replay_parser/resources.py` | Unchanged |
| `replay_parser/tests/` | Existing tests still valid; new tests added for `ingest()` and verification |

### Retired (kept in repo, not called by pipeline)

| File | Reason |
|---|---|
| `replay_parser/simulator.py` | Replaced by JS engine extraction |
| `js_engine/extract_turn_data.js` | Replaced by `bulk_extract.js` |

### DB Schema

**No table changes.** Same four tables (`turn_buys`, `turn_state`, `turn_actions`, `replay_parse_status`) with same columns and indexes from the original spec.

`parser_version` incremented to `2` in `replay_parse_status` to distinguish JS-extracted rows from Python-parsed rows.

---

## 6. Performance

### Extraction Throughput

- Per replay: ~150ms (engine load + auto-play + extraction)
- 102k replays, single-threaded: ~4.25 hours
- Parallelizable later via `worker_threads` (proven pattern in `matchup_clean.js`): ~30-40 min with 8 workers

### DB Ingestion

- Streaming insertion as JSONL lines arrive — no buffering the full dataset
- `executemany()` with periodic commits (every 1000 replays) for SQLite write efficiency
- DB ingestion is I/O bound and fast relative to JS extraction

### Memory

- Python: one JSONL line in memory at a time (~10-50KB per replay)
- JS: one Analyzer instance + one replay at a time. `beginTurnHistory` for a 30-turn game is ~30 State clones — modest memory

---

## 7. Relationship to Original Spec

This spec supersedes the **simulator component** (Sections 4, 6.1) of `2026-03-18-opening-book-analysis-design.md`. Everything else from that spec remains valid:

- **DB schema** (Section 5) — unchanged, reused as-is
- **Analysis queries** (Section 7) — unchanged, work against same tables
- **OB derivation workflow** (Section 9) — unchanged
- **CLI interface** (Section 1.3) — extended with `--verify` and `--cross-validate`
- **Testing strategy** (Section 11) — extended with verification layers
- **Known limitations** (Section 8) — most are eliminated by using the JS engine. Remaining limitations are engine-level (the ~0.3% of replays that trigger JS engine exceptions from null instance IDs on Frostbite/Gauss Charge/Cryo Ray units)
