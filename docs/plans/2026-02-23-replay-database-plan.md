# Replay Code Database — Research & Implementation Plan

> **Date**: Feb 23, 2026
> **Status**: PLAN — awaiting approval
> **Branch**: create from master (e.g., `feature/replay-database`)
> **Location**: `c:\libraries\prismata-replay-parser\` (database + migration script live with the data)

## Executive Summary

Consolidate ~98K+ unique replay codes from 25+ JSON files into a single SQLite database. Design for 1M replays. Future-proof for Discord bot / web app access via Turso or FastAPI.

**Why now**: We have 36 per-player JSON files, 4 community source files, 1 expert master file, balance validation results, and sniffer capture logs — all with slightly different schemas and no unified query interface. Questions like "how many training-ready codes on current patch?" require loading and cross-referencing multiple files.

**Why SQLite**: 1M records is trivially small (~320 MB estimated). Python `sqlite3` v3.50.4 is already available. FastAPI + uvicorn already installed for future API serving. Generated columns, json_each(), WAL mode, FTS5 all confirmed working. 100K bulk inserts take 0.27s. Upgrade path to Turso (SQLite-as-a-service) is a one-command migration.

---

## Phase 0: Documentation Discovery (COMPLETE)

### 0.1 Data Inventory — Confirmed Sources

#### V1 Sources (expert API + community)

| File | Records | Key Field | Schema |
|------|---------|-----------|--------|
| `expert_replays.json` | 32,082 | `Code` (capital C) | 15 fields: Code, Format, Deck, Result, EndCondition, TimeCondition, StartTime, EndTime, Version, P1Name, P1RatingIni, P1RatingChange, P2Name, P2RatingIni, P2RatingChange |
| `discord_valid_replays.json` | 2,793 | `code` (lowercase) | {code, status} |
| `tournament_valid_replays.json` | 960 | `code` (lowercase) | {code, status} |
| `reddit_valid_replays.json` | 245 | `code` (lowercase) | {code, p1, p2, r1, r2} |
| `discord_replay_codes_all.json` | 3,626 | (string array) | ["CODE1", "CODE2", ...] |

#### V2 Sources (per-player fetch) — 36 files

Pattern: `{PLAYER}_all_replays_v2.json` in `c:\libraries\prismata-replay-parser\`

Players: 1durbow, 307th, Achaa, Addition_, Asymat, Bleevoe, Esoteric, Jarekom, Kolento, Lycomedes, MasN, Mega-supp, Msven, Polari, Punf, Seederers, Shadourow, Spidi, SpiritFryer, Steel, Surfinite, TheSystem, TheTrumpWall, VanitasCabal, Weill, Wirrtsu, Wonderboat, YizGaemDed, chole, coffeeyay, flopflop, Homeless, jamberine, kamiloslaw, m3dium07th, ruinedshadows

Schema: **Identical to expert_replays.json** (same 15 fields, `Code` capital C, `Deck` is array of unit name strings).

#### Validation Data

| File | Records | Schema |
|------|---------|--------|
| `balance_results.json` | 34,957 | {code, pass, version, date, sources, reason?, mismatches?} |
| `balance_passed_codes.json` | 32,973 | ["CODE1", "CODE2", ...] |

#### Live Capture

| File | Records | Format |
|------|---------|--------|
| `bin/prismata_capture_codes.txt` | 37 | TSV: timestamp, code_or_username, event_type |

### 0.2 Confirmed SQLite Capabilities

All tested against SQLite 3.50.4:

| Feature | Status | Benchmark |
|---------|--------|-----------|
| Generated columns (STORED) | Working | `MIN(a,b)` computed correctly |
| `json_each()` | Working | 50K rows × 8-element arrays: 319ms GROUP BY, 106ms WHERE |
| WAL mode | Working | File-based DBs only |
| `INSERT OR IGNORE` (dedup) | Working | Keeps first row on PK conflict |
| `INSERT OR REPLACE` | Working | Keeps last row (overwrites) |
| `ON CONFLICT DO UPDATE` (upsert) | Working | Selective field merge |
| STRICT tables | Working | Rejects type mismatches |
| Partial indexes | Working | `WHERE` clause on index |
| FTS5 | Working | Full-text search available |
| Bulk insert | Working | 100K rows in 0.27s |

### 0.3 Schema Inconsistencies to Handle

| Issue | Detail | Resolution |
|-------|--------|------------|
| Code field case | Expert/V2: `Code` (capital), community: `code` (lowercase) | Normalize to lowercase `code` in DB |
| Rating precision | Floats like `2152.11962890625` | Store as REAL, display rounded |
| Deck format | Array of display name strings | Store as JSON TEXT column |
| Missing metadata | Discord/tournament only have `{code, status}` — no player/rating data | NULL columns, fill later if S3 fetched |
| Null Decks | Some expert_replays records have `null` Deck | Store as NULL, guard in queries |
| Duplicate codes | Same game appears in expert + v2 + community files | `INSERT OR IGNORE` on PK, merge sources |

### 0.4 Estimated DB Size at Scale

| Scale | Estimated Size | json_each() GROUP BY |
|-------|---------------|---------------------|
| 100K replays | ~32 MB | ~640ms |
| 500K replays | ~160 MB | ~3.2s |
| 1M replays | ~320 MB | ~6.4s |

At 1M, `json_each()` scans become slow for interactive use. Phase 3 adds an optional `replay_units` junction table that makes unit queries sub-millisecond at any scale.

### 0.5 Anti-Patterns to Avoid

- **Do NOT use `sqlite3.Row` factory for bulk inserts** — it's slower than tuple unpacking
- **Do NOT set `page_size` after creating tables** — must be before first `CREATE TABLE`
- **Do NOT assume WAL mode on `:memory:` DBs** — silently ignored
- **Do NOT use `json_extract()` for array iteration** — use `json_each()` instead
- **Do NOT use `AUTOINCREMENT` on the primary key** — replay codes are natural keys
- **Do NOT normalize the Deck column into a junction table in Phase 1** — premature; json_each() is fast enough at 100K. Phase 3 adds it if needed.

---

## Phase 1: Schema & Migration Script

**Goal**: Create the database, define the schema, build the import script.

### 1.1 Create the Database Schema

File: `c:\libraries\prismata-replay-parser\replay_db.py`

```sql
-- Schema to implement in Python
PRAGMA page_size = 4096;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS replays (
    code            TEXT PRIMARY KEY,
    p1_name         TEXT,
    p2_name         TEXT,
    p1_rating       REAL,
    p2_rating       REAL,
    p1_rating_change REAL,
    p2_rating_change REAL,
    result          INTEGER,          -- 0=P1 win, 1=P2 win, NULL=unknown
    deck            TEXT,             -- JSON array of unit name strings
    deck_size       INTEGER GENERATED ALWAYS AS (json_array_length(deck)) STORED,
    start_time      INTEGER,          -- Unix timestamp
    end_time        INTEGER,          -- Unix timestamp
    version         INTEGER,          -- Game engine version (242-769+)
    format          INTEGER,          -- Game format (200, 201, etc.)
    time_condition  INTEGER,          -- Time limit type
    end_condition   INTEGER,          -- How the game ended
    -- Computed columns for fast filtering
    min_rating      REAL GENERATED ALWAYS AS (
        CASE WHEN p1_rating IS NULL OR p2_rating IS NULL THEN NULL
             ELSE MIN(p1_rating, p2_rating) END
    ) STORED,
    max_rating      REAL GENERATED ALWAYS AS (
        CASE WHEN p1_rating IS NULL OR p2_rating IS NULL THEN NULL
             ELSE MAX(p1_rating, p2_rating) END
    ) STORED,
    avg_rating      REAL GENERATED ALWAYS AS (
        CASE WHEN p1_rating IS NULL OR p2_rating IS NULL THEN NULL
             ELSE (p1_rating + p2_rating) / 2.0 END
    ) STORED,
    -- Validation tracking
    balance_validated   INTEGER DEFAULT 0,   -- 0/1
    balance_passed      INTEGER DEFAULT 0,   -- 0/1
    balance_fail_reason TEXT,                 -- 'balance_mismatch', 'event_mode', etc.
    validation_date     TEXT,                 -- ISO date
    -- Training pipeline
    training_eligible   INTEGER DEFAULT 0,   -- 0/1: passed all checks for current patch
    training_extracted  INTEGER DEFAULT 0,   -- 0/1: already converted to training JSONL
    -- Provenance
    sources         TEXT DEFAULT '[]',       -- JSON array: ["expert","v2_flopflop","discord"]
    first_seen      TEXT,                    -- ISO datetime when first imported
    -- Future expansion (nullable, populated later)
    game_length     INTEGER,                 -- Total turns (from full replay fetch)
    replay_fetched  INTEGER DEFAULT 0,       -- 0/1: full replay JSON downloaded from S3
    patch_era       TEXT                     -- Derived label: 'current', 'recent', 'legacy'
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_min_rating ON replays(min_rating);
CREATE INDEX IF NOT EXISTS idx_max_rating ON replays(max_rating);
CREATE INDEX IF NOT EXISTS idx_avg_rating ON replays(avg_rating);
CREATE INDEX IF NOT EXISTS idx_balance_passed ON replays(balance_passed);
CREATE INDEX IF NOT EXISTS idx_training_eligible ON replays(training_eligible);
CREATE INDEX IF NOT EXISTS idx_training_extracted ON replays(training_extracted);
CREATE INDEX IF NOT EXISTS idx_version ON replays(version);
CREATE INDEX IF NOT EXISTS idx_p1_name ON replays(p1_name);
CREATE INDEX IF NOT EXISTS idx_p2_name ON replays(p2_name);
CREATE INDEX IF NOT EXISTS idx_start_time ON replays(start_time);
CREATE INDEX IF NOT EXISTS idx_result ON replays(result);

-- Partial index: only validated codes that passed
CREATE INDEX IF NOT EXISTS idx_training_ready ON replays(min_rating)
    WHERE balance_passed = 1 AND training_eligible = 1;

-- Metadata table for import tracking
CREATE TABLE IF NOT EXISTS import_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file     TEXT NOT NULL,
    import_date     TEXT NOT NULL,        -- ISO datetime
    records_total   INTEGER,
    records_new     INTEGER,
    records_updated INTEGER,
    notes           TEXT
);

-- Players table for quick lookups
CREATE TABLE IF NOT EXISTS players (
    name            TEXT PRIMARY KEY,
    peak_rating     REAL,
    total_games     INTEGER DEFAULT 0,
    v2_fetched      INTEGER DEFAULT 0,   -- 0/1: has a *_all_replays_v2.json file
    fetch_date      TEXT,                 -- When v2 data was collected
    notes           TEXT
);

-- Database metadata
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### 1.2 Build the Migration Script

File: `c:\libraries\prismata-replay-parser\build_replay_db.py`

The script must:
1. Create `replays.db` (or accept `--output` arg)
2. Set `PRAGMA page_size = 4096` and `PRAGMA journal_mode = WAL` before any tables
3. Create all tables and indexes from §1.1
4. Import sources in priority order (richest metadata first):
   a. `expert_replays.json` (32K, full metadata, source=`"expert"`)
   b. All 36 `*_all_replays_v2.json` files (source=`"v2_{player}"`)
   c. `reddit_valid_replays.json` (245, partial metadata, source=`"reddit"`)
   d. `discord_valid_replays.json` (2.8K, code only, source=`"discord"`)
   e. `tournament_valid_replays.json` (960, code only, source=`"tournament"`)
   f. `discord_replay_codes_all.json` (3.6K, code only, source=`"discord"`)
   g. `bin/prismata_capture_codes.txt` (37, code only, source=`"sniffer"`)
5. Use `INSERT OR IGNORE` for initial insert (first source with full metadata wins)
6. For subsequent sources, UPDATE the `sources` JSON array to append the new source tag
7. Import `balance_results.json` — UPDATE existing rows with validation fields
8. Log each import to `import_log` table
9. Populate `players` table from distinct p1_name/p2_name values
10. Set `db_meta` entries: `schema_version=1`, `created_date`, `total_codes`
11. Print summary: total codes, sources breakdown, validation coverage

**Dedup strategy**: `INSERT OR IGNORE` on code PK. Then a second pass per source file does `UPDATE replays SET sources = json_insert(sources, '$[#]', ?) WHERE code = ?` to track provenance without overwriting metadata.

**Performance target**: Full import should complete in <5 seconds (100K inserts at 0.27s + index building).

### 1.3 Verification Checklist

```bash
# After running: python build_replay_db.py
# 1. DB file exists and is reasonable size
python -c "import os; s=os.path.getsize('replays.db'); print(f'DB size: {s/1e6:.1f} MB'); assert s > 1e6, 'Too small'"

# 2. Record count matches expected ~98K unique codes
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT COUNT(*) FROM replays').fetchone()[0]; print(f'Total codes: {r}'); assert r > 90000, f'Expected >90K, got {r}'"

# 3. No duplicate codes
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT code, COUNT(*) FROM replays GROUP BY code HAVING COUNT(*)>1').fetchall(); print(f'Duplicates: {len(r)}'); assert len(r)==0"

# 4. Balance validation imported
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT COUNT(*) FROM replays WHERE balance_validated=1').fetchone()[0]; print(f'Validated: {r}'); assert r > 30000"

# 5. Sources tracking populated
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute(\"SELECT sources, COUNT(*) FROM replays GROUP BY sources ORDER BY COUNT(*) DESC LIMIT 10\").fetchall(); [print(f'  {s}: {n}') for s,n in r]"

# 6. Generated columns working
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT COUNT(*) FROM replays WHERE min_rating > 2000').fetchone()[0]; print(f'Expert (min_rating>2000): {r}')"

# 7. json_each works on deck
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT j.value, COUNT(*) FROM replays, json_each(deck) j WHERE deck IS NOT NULL GROUP BY j.value ORDER BY COUNT(*) DESC LIMIT 5').fetchall(); [print(f'  {u}: {n} games') for u,n in r]"

# 8. Import log populated
python -c "import sqlite3; c=sqlite3.connect('replays.db'); [print(f'  {r[1]}: {r[3]} total, {r[4]} new') for r in c.execute('SELECT * FROM import_log').fetchall()]"

# 9. Players table populated
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT COUNT(*) FROM players').fetchone()[0]; print(f'Unique players: {r}'); assert r > 1000"
```

---

## Phase 2: Query Library & CLI Tool

**Goal**: Build a Python module with canned queries + a CLI for interactive exploration.

### 2.1 Query Module

File: `c:\libraries\prismata-replay-parser\replay_queries.py`

Implement these query functions (all return plain Python data, no ORM):

```python
# Core counts
def total_codes(db) -> int
def training_ready_count(db, min_version=None) -> int
def validation_summary(db) -> dict  # {validated, passed, failed, unchecked}

# Filtering
def codes_by_rating(db, min_rating=0, max_rating=9999) -> list[str]
def codes_by_player(db, player_name) -> list[dict]
def codes_by_version(db, min_version, max_version=None) -> list[str]
def codes_by_unit(db, unit_name) -> list[str]  # uses json_each

# Analytics
def rating_distribution(db, buckets=None) -> list[tuple]  # [(range, count), ...]
def unit_frequency(db, min_rating=0) -> list[tuple]  # [(unit, count), ...]
def player_stats(db, player_name) -> dict  # {games, wins, losses, avg_rating, ...}
def source_breakdown(db) -> list[tuple]  # [(source_tag, count), ...]
def top_players(db, limit=20) -> list[dict]  # by game count

# Training pipeline
def unvalidated_codes(db) -> list[str]  # codes needing balance check
def mark_validated(db, code, passed, reason=None)
def mark_training_eligible(db, code)
def export_training_codes(db, output_file, min_rating=0, version=None)
```

### 2.2 CLI Interface

File: `c:\libraries\prismata-replay-parser\replay_cli.py`

```bash
# Usage examples:
python replay_cli.py status                    # Summary dashboard
python replay_cli.py count --min-rating 1800 --balance-passed
python replay_cli.py player flopflop           # Player profile
python replay_cli.py unit "Tia Thurnax"        # Games containing unit
python replay_cli.py rating-dist               # Rating histogram
python replay_cli.py unit-freq --min-rating 2000  # Expert unit popularity
python replay_cli.py unvalidated --limit 100   # Codes needing balance check
python replay_cli.py export training_codes.txt --min-rating 1800 --balance-passed
```

### 2.3 Verification Checklist

```bash
# 1. CLI status runs without error
python replay_cli.py status

# 2. Player lookup returns expected data
python replay_cli.py player flopflop | grep -c "games"

# 3. Unit query returns reasonable count
python replay_cli.py unit "Tarsier" | head -3

# 4. Export produces a file
python replay_cli.py export /tmp/test_export.txt --min-rating 2000 --balance-passed
wc -l /tmp/test_export.txt
```

---

## Phase 3: Expansion — Junction Table & Incremental Updates

**Goal**: Add `replay_units` junction table for fast unit queries. Add incremental import support for new data sources.

### 3.1 replay_units Junction Table

```sql
CREATE TABLE IF NOT EXISTS replay_units (
    code      TEXT NOT NULL REFERENCES replays(code),
    unit_name TEXT NOT NULL,
    PRIMARY KEY (code, unit_name)
);
CREATE INDEX IF NOT EXISTS idx_unit_name ON replay_units(unit_name);
```

Populated from existing `deck` JSON column:
```sql
INSERT INTO replay_units (code, unit_name)
SELECT r.code, j.value
FROM replays r, json_each(r.deck) j
WHERE r.deck IS NOT NULL;
```

This makes unit queries O(log N) instead of full-table json_each() scans:
```sql
-- Before (Phase 1): ~320ms at 50K rows
SELECT COUNT(*) FROM replays, json_each(deck) j WHERE j.value = 'Tia Thurnax';

-- After (Phase 3): <1ms at any scale
SELECT COUNT(*) FROM replay_units WHERE unit_name = 'Tia Thurnax';
```

### 3.2 Incremental Import

Add to `build_replay_db.py`:
- `--incremental` flag: only import records not already in DB
- `--source <file>`: import a single new source file
- Reads `import_log` to skip already-imported files
- Supports new v2 player files as they're collected

```bash
# Import a newly fetched player
python build_replay_db.py --incremental --source Vargus225_all_replays_v2.json

# Re-run balance validation import after new checks
python build_replay_db.py --incremental --source balance_results.json
```

### 3.3 Trigger: Auto-Populate replay_units

```sql
-- SQLite trigger to keep junction table in sync on INSERT
CREATE TRIGGER IF NOT EXISTS trg_replay_units_insert
AFTER INSERT ON replays
WHEN NEW.deck IS NOT NULL
BEGIN
    INSERT OR IGNORE INTO replay_units (code, unit_name)
    SELECT NEW.code, j.value FROM json_each(NEW.deck) j;
END;

-- Trigger for UPDATE (deck changes)
CREATE TRIGGER IF NOT EXISTS trg_replay_units_update
AFTER UPDATE OF deck ON replays
WHEN NEW.deck IS NOT NULL
BEGIN
    DELETE FROM replay_units WHERE code = NEW.code;
    INSERT INTO replay_units (code, unit_name)
    SELECT NEW.code, j.value FROM json_each(NEW.deck) j;
END;
```

### 3.4 Verification Checklist

```bash
# 1. Junction table populated
python -c "import sqlite3; c=sqlite3.connect('replays.db'); r=c.execute('SELECT COUNT(*) FROM replay_units').fetchone()[0]; print(f'Unit-replay pairs: {r}')"

# 2. Unit query is fast
python -c "import sqlite3, time; c=sqlite3.connect('replays.db'); t=time.time(); r=c.execute(\"SELECT COUNT(*) FROM replay_units WHERE unit_name='Tarsier'\").fetchone()[0]; print(f'Tarsier games: {r} in {(time.time()-t)*1000:.1f}ms')"

# 3. Incremental import works (re-run should add 0 new)
python build_replay_db.py --incremental 2>&1 | grep "new"

# 4. Trigger works (insert a test record, check junction table)
python -c "
import sqlite3, json
c = sqlite3.connect('replays.db')
c.execute(\"INSERT OR IGNORE INTO replays(code, deck, sources) VALUES ('TEST_CODE', ?, '[]')\", [json.dumps(['Tarsier','Rhino'])])
c.commit()
r = c.execute(\"SELECT * FROM replay_units WHERE code='TEST_CODE'\").fetchall()
print(f'Trigger created {len(r)} unit entries: {r}')
c.execute(\"DELETE FROM replays WHERE code='TEST_CODE'\")
c.commit()
"
```

---

## Phase 4: Online Access Path (Future)

**Goal**: Make the database queryable from a Discord bot or web app. Two paths documented — choose one when ready.

### Path A: Turso (Recommended — Zero Server)

```bash
# 1. Install Turso CLI
curl -sSfL https://get.tur.so/install.sh | bash

# 2. Upload existing SQLite DB
turso db create prismata-replays --from-file replays.db

# 3. Get connection URL and auth token
turso db show prismata-replays --url
turso db tokens create prismata-replays

# 4. Query from Discord bot (Python)
pip install libsql-client
```

```python
# Discord bot query example
import libsql_client
client = libsql_client.create_client(
    url="libsql://prismata-replays-YOUR_ORG.turso.io",
    auth_token="YOUR_TOKEN"
)
result = await client.execute(
    "SELECT COUNT(*) FROM replays WHERE min_rating > ? AND balance_passed = 1",
    [1800]
)
```

**Free tier**: 5 GB storage, 500M reads/month, 10M writes/month. More than enough.

### Path B: FastAPI Wrapper (Self-Hosted)

```python
# Already have FastAPI + uvicorn installed
# File: c:\libraries\prismata-replay-parser\replay_api.py

from fastapi import FastAPI
import sqlite3

app = FastAPI()

@app.get("/api/count")
def count(min_rating: float = 0, balance_passed: bool = False):
    conn = sqlite3.connect("replays.db")
    query = "SELECT COUNT(*) FROM replays WHERE min_rating >= ?"
    params = [min_rating]
    if balance_passed:
        query += " AND balance_passed = 1"
    return {"count": conn.execute(query, params).fetchone()[0]}

@app.get("/api/player/{name}")
def player(name: str):
    conn = sqlite3.connect("replays.db")
    rows = conn.execute(
        "SELECT * FROM replays WHERE p1_name = ? OR p2_name = ? LIMIT 100",
        [name, name]
    ).fetchall()
    return {"games": len(rows), "data": rows}

# Run: uvicorn replay_api:app --host 0.0.0.0 --port 8080
```

Host on Fly.io (~$5/mo) or run locally for LAN access.

### 4.1 Verification Checklist

```bash
# Path A (Turso):
# 1. DB uploads successfully
turso db show prismata-replays

# 2. Remote query works
python -c "
import asyncio, libsql_client
async def test():
    c = libsql_client.create_client(url='...', auth_token='...')
    r = await c.execute('SELECT COUNT(*) FROM replays')
    print(r)
asyncio.run(test())
"

# Path B (FastAPI):
# 1. Server starts
uvicorn replay_api:app --port 8080 &
curl http://localhost:8080/api/count?min_rating=2000
curl http://localhost:8080/api/player/flopflop
```

---

## Phase 5: Final Verification & Integration

**Goal**: Prove the database is correct and integrate with existing pipelines.

### 5.1 Data Integrity Checks

```bash
# Cross-reference against original JSON files
python -c "
import sqlite3, json

conn = sqlite3.connect('replays.db')

# Check expert count matches
with open('expert_replays.json') as f:
    expert = json.load(f)
expert_codes = {r['Code'] for r in expert}
db_expert = {r[0] for r in conn.execute(
    \"SELECT code FROM replays WHERE sources LIKE '%expert%'\"
).fetchall()}
missing = expert_codes - db_expert
print(f'Expert codes in JSON: {len(expert_codes)}')
print(f'Expert codes in DB: {len(db_expert)}')
print(f'Missing from DB: {len(missing)}')
assert len(missing) == 0, f'Missing {len(missing)} expert codes!'

# Check balance validation matches
with open('balance_results.json') as f:
    balance = json.load(f)
json_passed = sum(1 for r in balance if r.get('pass'))
db_passed = conn.execute('SELECT COUNT(*) FROM replays WHERE balance_passed=1').fetchone()[0]
print(f'Balance passed (JSON): {json_passed}')
print(f'Balance passed (DB): {db_passed}')
assert db_passed >= json_passed, 'DB has fewer passed codes than JSON!'
"
```

### 5.2 Update Existing Tools (Optional)

These existing scripts could be updated to read from the DB instead of JSON files, but this is **optional** — the JSON files continue to work:

| Script | Current Source | DB Replacement |
|--------|---------------|----------------|
| `validate_balance_all.js` | Loads 4 JSON files | Could read `SELECT code FROM replays WHERE balance_validated=0` |
| `extract_training_data.js` | Reads processed_codes.txt | Could read `SELECT code FROM replays WHERE training_extracted=0` |
| `tools/generate_postgame_commentary.py` | Fetches replay from S3 | Could check `replay_fetched` flag first |

### 5.3 Anti-Pattern Guards

```bash
# Grep for common mistakes in implementation

# 1. No autoincrement on replay code (should be natural key)
grep -r "AUTOINCREMENT" replay_db.py replay_queries.py build_replay_db.py | grep -v "import_log" && echo "WARNING: AUTOINCREMENT found outside import_log"

# 2. No hardcoded paths (should use relative or configurable)
grep -r "c:\\\\libraries" replay_db.py replay_queries.py build_replay_db.py && echo "WARNING: Hardcoded paths found"

# 3. No bare except clauses
grep -r "except:" replay_db.py replay_queries.py build_replay_db.py && echo "WARNING: Bare except found"

# 4. WAL mode is set
python -c "import sqlite3; c=sqlite3.connect('replays.db'); print('Journal mode:', c.execute('PRAGMA journal_mode').fetchone()[0])"
```

---

## Implementation Notes

### File Layout

```
c:\libraries\prismata-replay-parser\
├── replays.db                    # The database (gitignored, ~30 MB)
├── build_replay_db.py            # Migration + incremental import script
├── replay_db.py                  # Schema definitions + connection helpers
├── replay_queries.py             # Query library
├── replay_cli.py                 # CLI tool
├── replay_api.py                 # FastAPI wrapper (Phase 4)
├── expert_replays.json           # (existing, kept as source-of-truth backup)
├── *_all_replays_v2.json         # (existing, kept)
├── balance_results.json          # (existing, kept)
└── ...
```

### Key Design Decisions

1. **SQLite over PostgreSQL**: 1M records is trivially small. No server process. Python stdlib. Turso upgrade path for online access.

2. **JSON deck column over normalized junction table**: `json_each()` is 320ms at 50K rows — acceptable for Phase 1-2. Junction table added in Phase 3 for sub-millisecond unit queries when needed.

3. **`INSERT OR IGNORE` + source tracking**: First import with full metadata wins PK. Subsequent imports only append to the `sources` array. This preserves the richest data while tracking provenance.

4. **Generated columns for rating filters**: `min_rating`, `max_rating`, `avg_rating` are computed and indexed. Zero maintenance, always consistent.

5. **Keep JSON files**: The DB is a consolidation layer, not a replacement. JSON files remain as source-of-truth backups. The `build_replay_db.py` script can recreate the DB from scratch at any time.

6. **Replay code as natural primary key**: No surrogate integer ID needed. Codes are globally unique, immutable, and used as lookup keys everywhere.

### Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|-------------|
| Phase 1: Schema + Migration | ~2 hours | None |
| Phase 2: Query Library + CLI | ~2 hours | Phase 1 |
| Phase 3: Junction Table + Incremental | ~1 hour | Phase 2 |
| Phase 4: Online Access | ~1-2 hours | Phase 3 (optional) |
| Phase 5: Verification | ~30 min | All phases |

**Total: ~6-8 hours of implementation work across 1-2 sessions.**
