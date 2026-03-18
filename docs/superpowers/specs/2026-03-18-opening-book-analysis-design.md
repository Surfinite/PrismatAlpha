# Design Spec: Opening Book Analysis Database & Python Replay Parser

> **Date**: 2026-03-18
> **Goal**: Build a Python replay parser library and opening analysis database from 102,697 expert replays, enabling arbitrary SQL analysis of opening buy sequences, set compositions, and player behavior
> **Parser location**: `replay_parser/` (in PrismataAI repo)
> **Database**: Extends existing `replays.db` at `c:\libraries\prismata-replay-parser\` (path passed via CLI)

---

## 1. Architecture Overview

### 1.1 Directory Structure

```
replay_parser/
├── __init__.py          # Package init, version
├── __main__.py          # CLI entry point: python -m replay_parser
├── models.py            # Data classes: ReplayData, Turn, Action, UnitInstance, ResourcePool
├── decoder.py           # Load .json.gz → ReplayData (structured Python objects)
├── simulator.py         # Tier 2 state walker — processes clicks, tracks units/resources/supply
├── database.py          # Schema migrations, DB read/write, incremental processing
├── fetch.py             # Download replays from S3 (URL-encode + / @)
├── pipeline.py          # Orchestrator: fetch → decode → simulate → store
├── resources.py         # Resource string parser ("6GGGRBB" → ResourcePool)
└── tests/
    ├── test_decoder.py
    ├── test_simulator.py
    ├── test_resources.py
    └── test_database.py
```

### 1.2 Design Principles

1. **Modular and distributable** — someone can `from replay_parser import decoder, simulator` and analyze replays in 10 lines of Python without touching the DB
2. **Tier 2 parser** — click-level analysis with resource tracking, NOT a full game simulator. Known limitations documented (Section 8)
3. **Extend, don't replace** — new tables added to existing `replays.db` via migration. Existing tables untouched
4. **Incremental and resumable** — tracks which replays have been parsed. Can stop and restart
5. **DB path is a CLI argument** — parser code lives in PrismataAI, DB lives in prismata-replay-parser

### 1.3 CLI Interface

```bash
# Full pipeline: parse all eligible replays, write to DB
python -m replay_parser --db c:/libraries/prismata-replay-parser/replays.db \
    --replays-dir c:/libraries/prismata-replay-parser/replays_archive/

# Parse specific replays by code
python -m replay_parser --db replays.db --codes "ABC123,DEF456"

# Fetch + parse new replays (smooth add-new-replays flow)
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ \
    --fetch --codes-file new_codes.txt

# Parse without DB (stdout JSON for piping)
python -m replay_parser --replay path/to/replay.json.gz --json

# Re-parse all (ignore already-parsed flag)
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ --force
```

---

## 2. Replay JSON Structure

Reference for parser implementation. Data comes from S3 `.json.gz` files.

### 2.1 Top-Level Keys

```
code, deckInfo, endCondition, initInfo, format, rawHash, playerInfo,
commandInfo, timeInfo, result, startTime, logInfo, chatInfo,
versionInfo, seed, ratingInfo, endTime
```

### 2.2 Key Structures

**`commandInfo`** (NOT top-level `commandList`):
```json
{
  "commandList": [{"_type": "inst shift clicked", "_id": 1}, ...],
  "clicksPerTurn": [4, 4, 5, 5, ...],
  "commandTimes": [0.85, ...],
  "commandForced": [false, ...]
}
```

**`deckInfo.mergedDeck`** — array of card definitions (index = deck ID):
```json
{
  "name": "Conduit",
  "rarity": "normal",
  "buyCost": "4",
  "toughness": 3,
  "buildTime": 0,
  "beginOwnTurnScript": {"receive": "G"},
  "abilityScript": {},
  "baseSet": 1,
  "defaultBlocking": 0
}
```

**`initInfo`**:
```json
{
  "initCards": [
    [[6, "Drone"], [2, "Engineer"]],   // P1: 6 Drones + 2 Engineers
    [[7, "Drone"], [2, "Engineer"]]    // P2: 7 Drones + 2 Engineers
  ],
  "initResources": ["0", "0"]
}
```

**`result`**: 0 = P1 wins, 1 = P2 wins, 2 = draw

**`playerInfo`** — array indexed by player (0=P1, 1=P2). Key fields:
- `playerInfo[n].displayName` — player's display name (string)
- No `playerNumber` key — use array index

### 2.3 Click Types

| `_type` | Meaning | `_id` maps to |
|---------|---------|---------------|
| `card clicked` | Buy a unit (single) | `mergedDeck` index |
| `card shift clicked` | Buy unit (as many as affordable) | `mergedDeck` index |
| `inst clicked` | Use ability on a unit instance | Instance ID |
| `inst shift clicked` | Use ability on all units of this type | Instance ID (of any one) |
| `space clicked` | Commit / end phase / end turn | Always `-1` |
| `end swipe processed` | End-of-turn animation marker | N/A |
| `emote*` | Chat emote (e.g., `emoteHeart`, `emoteGood luck...`) | Ignored |
| `undo clicked` | Undo last action | N/A |
| `cancel target processed` | Cancel targeting mode | N/A |
| `revert clicked` | Revert to start of turn | N/A |

**Undo/revert handling**: `undo clicked` undoes the most recent action (un-buy, un-ability). `revert clicked` undoes ALL actions in the current turn back to the start. The simulator must handle these by maintaining a per-turn action stack and rolling back state. `cancel target processed` cancels a pending target selection (no state change needed).

### 2.4 Resource Encoding

In `buyCost`, `abilityScript.receive`, and `beginOwnTurnScript.receive`:

| Character | Resource |
|-----------|----------|
| Digits (`0-9`) | Gold |
| `G` | Green |
| `B` | Blue |
| `C` | Red |
| `A` | Attack |
| `H` | Energy |

Examples: `"3H"` = 3 gold + 1 energy (Drone buy cost). `"6GGGRBB"` would be 6 gold + 3 green + 1 red + 2 blue.

**Integer values**: Some `receive` fields use integers instead of strings (e.g., Manticore: `{"receive": 3}`, Trinity Drone: `{"receive": 3}`). These represent gold. Parser must handle both `str` and `int`.

### 2.5 Supply by Rarity

| Rarity | Starting Supply |
|--------|----------------|
| `trinket` | 20 |
| `normal` | 10 |
| `rare` | 4 |
| `legendary` | 1 |

**Supply is per-player and separate from starting units.** Drone supply is asymmetric: P0 gets 21 buyable, P1 gets 20 buyable. Combined with starting Drones (P0: 6, P1: 7), both players can reach 27 Drones max from buying. All other units have symmetric supply derived from rarity (both players share the same pool). The simulator must track Drone supply per-player; other units use a single shared supply counter.

**Implementation note**: The replay JSON does not include explicit supply numbers. Drone supply asymmetry (P0=21, P1=20) must be hardcoded. All other supply is derived from rarity.

### 2.6 Resource Generation: Passive vs Active

Units produce resources in two ways:

- **Passive** (`beginOwnTurnScript.receive`): Automatically credited at turn start. No click required.
  - Examples: Conduit → G, Blastforge → B, Animus → CC, Engineer → H, Tarsier → A
- **Active** (`abilityScript.receive`): Credited when the player clicks the unit. Requires an `inst clicked` or `inst shift clicked`.
  - Examples: Drone → 1 gold, Steelsplitter → A, Synthesizer → BB

Some units have **both** (e.g., Synthesizer: passive GG + active BB, Thorium Dynamo: passive 5G + active 3).

**Build time**: Units with `buildTime > 0` do not produce resources until N turns after purchase (they are "under construction"). The parser tracks construction status per instance.

---

## 3. Data Model (Python)

### 3.1 Core Classes (`models.py`)

```python
@dataclass
class ResourcePool:
    gold: int = 0
    green: int = 0
    blue: int = 0
    red: int = 0
    energy: int = 0
    attack: int = 0

@dataclass
class CardDef:
    """Card definition from mergedDeck (shared across all instances)."""
    deck_index: int           # Index in mergedDeck
    name: str                 # Display name
    rarity: str               # trinket/normal/rare/legendary
    buy_cost: ResourcePool
    toughness: int
    build_time: int
    is_base_set: bool
    default_blocking: bool
    begin_turn_receive: ResourcePool | None   # Passive income
    ability_receive: ResourcePool | None      # On-click income
    ability_selfsac: bool                     # Dies after ability use
    ability_create: list | None               # Creates units on ability
    target_action: str | None                 # "snipe" or "disrupt" (chill)
    supply: int                               # Starting supply (from rarity)

@dataclass
class UnitInstance:
    """A specific unit on the board."""
    instance_id: int          # Runtime instance ID
    card_def: CardDef         # Reference to card definition
    owner: int                # 0 = P1, 1 = P2
    turns_until_ready: int    # Build time remaining (0 = ready)
    is_alive: bool
    used_ability_this_turn: bool

@dataclass
class Action:
    """A single parsed action within a turn."""
    action_type: str          # "buy", "buy_shift", "ability", "ability_shift",
                              # "target", "defend", "commit", "end_swipe"
    unit_name: str | None     # Display name of the unit involved
    deck_index: int | None    # For buys: mergedDeck index
    instance_id: int | None   # For abilities: instance ID
    quantity: int             # For shift-buys: how many purchased (estimated)
    raw_click: dict           # Original {"_type": ..., "_id": ...}

@dataclass
class Turn:
    """All actions and state for one player-turn."""
    global_turn: int          # 0-indexed across both players
    player: int               # 0 = P1, 1 = P2
    player_turn: int          # 1-indexed per player
    actions: list[Action]
    buys: list[str]           # Unit names bought this turn (verified against supply)
    abilities_used: list[str] # Unit names whose abilities were activated
    resources_at_start: ResourcePool  # After passive income, before clicks
    resources_after: ResourcePool     # After all actions
    units_owned: dict[str, int]       # Unit name → count at START of turn (before buys)

@dataclass
class ReplayData:
    """Fully parsed replay."""
    code: str
    result: int               # 0=P1 wins, 1=P2 wins, 2=draw
    card_defs: list[CardDef]  # From mergedDeck
    randomizer: list[str]     # Dominion card names (non-base)
    init_cards: list[list[tuple[int, str]]]  # Per-player starting units
    turns: list[Turn]
    total_global_turns: int
    # Metadata (from replay JSON, not from DB)
    start_time: int | None
    player_names: list[str]   # [P1 name, P2 name] from playerInfo
```

### 3.2 Resource Parser (`resources.py`)

```python
def parse_resource_string(value: str | int | None) -> ResourcePool:
    """Parse '6GGGRBB' → ResourcePool(gold=6, green=3, red=1, blue=2).

    Handles: string encoding, integer gold shorthand, None → empty pool.
    Digits accumulate into gold. Letters map: G=green, B=blue, C=red, A=attack, H=energy.
    """
```

---

## 4. Simulator Design (`simulator.py`)

### 4.1 State Tracking

The simulator maintains per-player:

- **Unit roster**: `dict[int, UnitInstance]` — instance_id → UnitInstance. Populated from `initInfo`, extended by buys
- **Resources**: `ResourcePool` — current available resources
- **Supply**: `dict[int, int]` — deck_index → remaining supply (shared for all units except Drone, which is per-player: P0=21, P1=20)
- **Next instance ID**: Counter for newly created instances (starts after init units)

### 4.2 Turn Processing Flow

For each turn (sliced from `commandInfo.commandList` via `commandInfo.clicksPerTurn`):

1. **Credit passive income**: For all ready (buildTime=0) units owned by the active player, credit `beginOwnTurnScript.receive`
2. **Advance construction**: Decrement `turns_until_ready` for all constructing units. Units reaching 0 become ready (but do NOT produce passive income this turn — they just finished building)
3. **Snapshot `resources_at_start`**
4. **Process clicks sequentially**:
   - `inst clicked` / `inst shift clicked` → ability activation. Credit `abilityScript.receive`. Mark `used_ability_this_turn`. Handle `selfsac` (mark dead)
   - `card clicked` → single buy. Check supply > 0 AND can afford. If yes: deduct cost, decrement supply, create new UnitInstance with `turns_until_ready = buildTime`
   - `card shift clicked` → repeated buy. Buy as many as affordable while supply > 0
   - `space clicked` → phase commit (no state change)
   - `end swipe processed` → animation marker (no state change)
5. **Snapshot `resources_after`**
6. **Record turn data**: buys, abilities, unit counts
7. **Reset per-turn state**: Clear `used_ability_this_turn` flags

### 4.3 Instance ID Assignment

Initial IDs are assigned sequentially from `initInfo.initCards`:
- P1's units: IDs 0, 1, 2, ... (6 Drones = 0-5, 2 Engineers = 6-7 → next_id = 8)
- P2's units: IDs 8, 9, ... (7 Drones = 8-14, 2 Engineers = 15-16 → next_id = 17)

New units from buys get the next available ID, incrementing globally.

**Instance ID → unit type mapping**: When `inst clicked _id=3` occurs, the simulator looks up instance 3 in the roster to determine it's a Drone, then credits 1 gold.

**`inst shift clicked`**: Activates ALL ready units of the same type owned by that player. The `_id` identifies one instance; the simulator finds all instances of the same `CardDef` for that player and activates them all.

### 4.4 Defense Phase Handling

Defense clicks (`inst clicked` on enemy units during defense phase) assign blockers. The parser records these as defense actions but does NOT simulate damage resolution (that's Tier 1 territory). The turn's defense assignments are stored as action records.

**Phase detection**: The simulator tracks phase using `space clicked` count within each turn:
- **Phase 0 (defense)**: Before the first `space clicked`. Any `inst clicked` here is a blocker assignment
- **Phase 1 (action)**: After the first `space clicked`. `inst clicked` = ability use, `card clicked` = buy
- **Phase 2 (confirm/end)**: After the second `space clicked`. Turn is over (remaining clicks are animation markers like `end swipe processed`)

This is reliable because `space clicked` always marks phase boundaries. Early turns with no incoming attack may have defense phase immediately committed (first click is `space clicked`), going straight to action phase.

### 4.5 `card shift clicked` Quantity Estimation

Shift-click buys purchase "as many as affordable." The simulator calculates:
```
quantity = min(
    remaining_supply[deck_index],
    max units affordable given current resources and unit cost
)
```

This is exact for gold-only units (Drone, Conduit, Blastforge, Animus, Engineer). For units requiring colored resources, it's exact if the simulator has tracked resource generation correctly up to that point.

---

## 5. Database Schema

### 5.1 New Tables (added to existing `replays.db`)

```sql
-- Schema version tracking for migrations
-- (uses existing db_meta table: key='parser_schema_version', value='1')

-- Per-replay parsing status
CREATE TABLE IF NOT EXISTS replay_parse_status (
    code            TEXT PRIMARY KEY REFERENCES replays(code),
    parsed          INTEGER DEFAULT 0,        -- 1 = successfully parsed
    parse_date      TEXT,                      -- ISO 8601 timestamp
    parser_version  INTEGER,                   -- Schema version at parse time
    total_turns     INTEGER,                   -- Total global turns in game
    error           TEXT                       -- NULL if success, error message if failed
);

-- Per-turn actions (all turns, all action types)
CREATE TABLE IF NOT EXISTS turn_actions (
    code            TEXT NOT NULL REFERENCES replays(code),
    global_turn     INTEGER NOT NULL,          -- 0-indexed
    player          INTEGER NOT NULL,          -- 0 = P1, 1 = P2
    player_turn     INTEGER NOT NULL,          -- 1-indexed per player
    action_index    INTEGER NOT NULL,          -- Order within turn
    action_type     TEXT NOT NULL,             -- buy, buy_shift, ability, ability_shift,
                                               -- target, defend, commit, end_swipe
    unit_name       TEXT,                      -- Display name (NULL for commit/end_swipe)
    quantity        INTEGER DEFAULT 1,         -- >1 for shift-buys
    deck_index      INTEGER,                   -- mergedDeck index (buys only)
    instance_id     INTEGER,                   -- Runtime instance ID (abilities only)
    PRIMARY KEY (code, global_turn, action_index)
);

-- Per-turn state snapshot (resources and unit counts)
CREATE TABLE IF NOT EXISTS turn_state (
    code            TEXT NOT NULL REFERENCES replays(code),
    global_turn     INTEGER NOT NULL,
    player          INTEGER NOT NULL,
    player_turn     INTEGER NOT NULL,
    -- Resources at start of action phase (after passive income)
    gold            INTEGER NOT NULL DEFAULT 0,
    green           INTEGER NOT NULL DEFAULT 0,
    blue            INTEGER NOT NULL DEFAULT 0,
    red             INTEGER NOT NULL DEFAULT 0,
    energy          INTEGER NOT NULL DEFAULT 0,
    attack          INTEGER NOT NULL DEFAULT 0,
    -- Unit counts (JSON object: {"Drone": 8, "Engineer": 2, "Conduit": 1})
    units_owned     TEXT NOT NULL,             -- JSON
    -- Total unit count (populated during insert, sum of all values in units_owned)
    total_units     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (code, global_turn)
);

-- Per-turn buy summary (denormalized for fast opening queries)
CREATE TABLE IF NOT EXISTS turn_buys (
    code            TEXT NOT NULL REFERENCES replays(code),
    global_turn     INTEGER NOT NULL,
    player          INTEGER NOT NULL,
    player_turn     INTEGER NOT NULL,
    buy_sequence    TEXT NOT NULL,             -- JSON array: ["Drone", "Drone", "Conduit"]
    buy_hash        TEXT NOT NULL,             -- Sorted+joined for grouping: "Conduit,Drone,Drone"
    PRIMARY KEY (code, global_turn)
);
```

### 5.2 Indexes

```sql
-- Fast opening queries by player turn number
CREATE INDEX IF NOT EXISTS idx_turn_buys_player_turn
    ON turn_buys(player, player_turn);

-- Set composition + opening queries (JOIN through replay_units)
CREATE INDEX IF NOT EXISTS idx_turn_buys_code_turn
    ON turn_buys(code, player_turn);

-- Find all turns for a replay
CREATE INDEX IF NOT EXISTS idx_turn_actions_code
    ON turn_actions(code, global_turn);

-- Parse status for incremental processing
CREATE INDEX IF NOT EXISTS idx_parse_status_parsed
    ON replay_parse_status(parsed);

-- Buy pattern grouping
CREATE INDEX IF NOT EXISTS idx_turn_buys_hash
    ON turn_buys(buy_hash, player_turn);
```

### 5.3 Migration Strategy

1. **Backup first**: `cp replays.db replays.db.bak.YYYYMMDD`
2. **Version check**: Read `db_meta` key `parser_schema_version`. If missing, set to 0.
3. **Apply migrations**: Sequential migration functions (v0→v1 creates tables, future v1→v2 adds columns, etc.)
4. **Atomic**: Each migration wrapped in a transaction

### 5.4 Existing Tables Used (Not Modified)

- **`replays`**: JOIN for `result`, `p1_rating`, `p2_rating`, `balance_passed`, `min_rating`
- **`replay_units`**: JOIN for set composition queries ("all games containing Blastforge AND Tarsier")

---

## 6. Pipeline Flow

### 6.1 Full Pipeline (`pipeline.py`)

```
1. Open DB, run migrations if needed
2. Query eligible replays:
   SELECT r.code FROM replays r
   LEFT JOIN replay_parse_status rps ON r.code = rps.code
   WHERE r.balance_passed = 1
     AND (rps.parsed IS NULL OR rps.parsed = 0)
     AND r.p1_rating > 1 AND r.p2_rating > 1
3. For each replay code:
   a. Load .json.gz from replays_dir/{code_to_filename(code)}
   b. decoder.decode(raw_json) → ReplayData (structured objects, no simulation)
   c. simulator.simulate(replay_data) → ReplayData with populated turns
   d. database.store(replay_data) → INSERT into turn_actions, turn_state, turn_buys
   e. UPDATE replay_parse_status SET parsed=1
4. Report: X parsed, Y skipped (already done), Z errors
```

### 6.2 Code-to-Filename Mapping

Replay codes contain special characters (`+`, `@`, `-`). The archive filenames use the **raw code** (not URL-encoded) with `.json.gz` extension — e.g., `++A4h-1QDmB.json.gz`. URL-encoding is only needed for S3 fetch URLs, not local file lookup.

### 6.3 Fetch + Parse Flow (New Replays)

For adding newly discovered replays:
```
1. Input: list of replay codes (from codes file, API search, etc.)
2. fetch.py: Download each code from S3 → replays_dir/{filename}.json.gz
3. Insert/update replay metadata in replays table (if not already present)
4. Run standard parse pipeline on the new codes
```

This gives the smooth "add a replay code, everything happens" flow.

### 6.4 Error Handling

- **Missing file**: Log warning, mark `error` in `replay_parse_status`, continue
- **Malformed JSON**: Same — log + mark + continue
- **Simulation error** (unexpected click type, instance ID not found): Log warning with replay code and turn number, store what was successfully parsed up to that point, mark error
- **DB constraint violation**: Transaction rollback for that replay, continue with next

### 6.5 Performance

Estimated throughput: ~500-1000 replays/second (mostly I/O bound on gzip decompression + SQLite writes). Full 102k dataset should complete in 2-4 minutes on local SSD. No parallelism needed at this scale.

Batch inserts: Use `executemany()` with batches of 1000 replays per COMMIT for SQLite write efficiency.

---

## 7. Analysis Queries

### 7.1 Opening Buy Frequency

"What do 1500+ players buy on turn 1 as P2 when Blastforge is in the set?"

```sql
SELECT tb.buy_sequence, COUNT(*) as freq,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
JOIN replay_units ru ON tb.code = ru.code
WHERE tb.player = 1 AND tb.player_turn = 1
  AND ru.unit_name = 'Blastforge'
  AND r.min_rating >= 1500
  AND r.balance_passed = 1
GROUP BY tb.buy_sequence
ORDER BY freq DESC
LIMIT 20;
```

### 7.2 Consensus Across Set Compositions

"What is the consensus turn-2 buy when Synthesizer AND Blood Phage are both present?"

```sql
SELECT tb.buy_sequence, COUNT(*) as freq
FROM turn_buys tb
WHERE tb.player_turn = 2
  AND tb.code IN (
    SELECT code FROM replay_units WHERE unit_name = 'Synthesizer'
    INTERSECT
    SELECT code FROM replay_units WHERE unit_name = 'Blood Phage'
  )
GROUP BY tb.buy_sequence
ORDER BY freq DESC
LIMIT 10;
```

### 7.3 Winning-Side Openings

"Turn 1-3 buy sequences for the winning player in sets containing Tarsier"

```sql
SELECT tb.player_turn, tb.buy_sequence, COUNT(*) as freq
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
WHERE tb.player = r.result              -- winner's turns only
  AND r.result IN (0, 1)                -- exclude draws
  AND tb.player_turn <= 3
  AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = 'Tarsier')
  AND r.min_rating >= 1500
GROUP BY tb.player_turn, tb.buy_sequence
ORDER BY tb.player_turn, freq DESC;
```

### 7.4 High Variance Sets (No Consensus)

"Which Dominion unit pairs have the most varied turn-1 buys?"

```sql
WITH pair_games AS (
    SELECT ru1.unit_name AS u1, ru2.unit_name AS u2, tb.code, tb.buy_hash
    FROM replay_units ru1
    JOIN replay_units ru2 ON ru1.code = ru2.code AND ru1.unit_name < ru2.unit_name
    JOIN turn_buys tb ON tb.code = ru1.code
    WHERE tb.player_turn = 1
),
pair_stats AS (
    SELECT u1, u2,
           COUNT(DISTINCT buy_hash) as unique_buys,
           COUNT(*) as total_games
    FROM pair_games
    GROUP BY u1, u2
    HAVING total_games >= 50
)
SELECT u1, u2, unique_buys, total_games,
       ROUND(1.0 * unique_buys / total_games, 3) as variance_ratio
FROM pair_stats
ORDER BY unique_buys DESC
LIMIT 20;
```

### 7.5 OB Condition Matching

"What do players buy when they have exactly 7 Drones and 2 Engineers (P2 turn 1 starting state)?"

```sql
SELECT tb.buy_sequence, COUNT(*) as freq
FROM turn_buys tb
JOIN turn_state ts ON tb.code = ts.code AND tb.global_turn = ts.global_turn
WHERE tb.player_turn = 1 AND tb.player = 1
  AND json_extract(ts.units_owned, '$.Drone') = 7
  AND json_extract(ts.units_owned, '$.Engineer') = 2
GROUP BY tb.buy_sequence
ORDER BY freq DESC
LIMIT 10;
```

### 7.6 Rating-Stratified Analysis

"Do top players (1700+) open differently from average (1500-1600)?"

```sql
SELECT
    CASE WHEN r.min_rating >= 1700 THEN 'elite' ELSE 'average' END as tier,
    tb.buy_sequence, COUNT(*) as freq
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
WHERE tb.player_turn = 1 AND tb.player = 0
  AND r.min_rating >= 1500
GROUP BY tier, tb.buy_sequence
ORDER BY tier, freq DESC;
```

---

## 8. Known Limitations (Tier 2)

### 8.1 Chill/Freeze Tracking

The parser records chill/snipe targeting actions (sees "Shiver Yeti activated, then enemy Wall targeted") but does **not** compute accumulated chill per unit or determine whether a unit is frozen. 9 units have `targetAction`: Apollo, Cryo Ray, Frostbite, Iceblade Golem, Kinetic Driver, Nivo Charge, Shiver Yeti, Tatsu Nullifier, Vai Mauronax.

**Impact**: Cannot verify whether a frozen unit was available as a blocker. Defense analysis is incomplete when chill units are present. For opening analysis (turns 1-5), this is essentially irrelevant — chill units are rarely built and used that early.

### 8.2 Damage Resolution

The parser does not simulate combat damage. It records defense assignments and breach events (from click patterns) but cannot compute exact HP remaining on partially-damaged units.

### 8.3 Unit Death from Damage

When units die from combat, the parser may have stale entries in the unit roster. Self-sac deaths (from `abilityScript.selfsac`) ARE tracked. Combat deaths are NOT. This can cause instance ID lookups to reference dead units in late-game turns.

### 8.4 Created Units

Some abilities create new units (e.g., Steelforge creates Steelsplitter, Venge Cannon creates Gauss Charges). The parser handles `abilityScript.create` and adds new instances to the roster. However, the instance IDs assigned to created units may not match the game's internal assignment if combat deaths have occurred (since the game recycles IDs differently than our sequential counter).

### 8.5 Shift-Click Buy Quantity

For units costing only gold (Drone, Conduit, Blastforge, Animus, Engineer), shift-click quantity is exact. For units requiring colored resources, accuracy depends on the resource tracker having correctly accumulated all prior income. Expected to be accurate for 95%+ of cases; may miscount in complex late-game scenarios.

### 8.6 Resource Decay

Only gold and green persist between turns. Blue, red, energy, and attack reset to zero at turn start, then passive income (`beginOwnTurnScript`) re-adds them. The parser implements this decay.

### 8.7 In-Game Un-Buy Mechanic

Prismata has TWO undo mechanisms:
1. **`undo clicked`** — explicit undo button (rare, ~0.3% of clicks)
2. **`inst clicked` on a just-bought unit** — in-game click-to-un-buy (very common, ~65% of turns)

Clicking a unit purchased this turn refunds its buy cost, removes the instance, and restores supply. The parser detects this by tracking which instance IDs were created by buys in the current turn. This is the dominant undo pattern and is NOT encoded as `undo clicked` in the replay data.

### 8.8 Cross-Validation Results (Python vs JS engine, beginTurnHistory ground truth)

**500 replays (seed=42):**

| Player Turn | Buy Accuracy |
|-------------|-------------|
| 1 | **99.9%** (1 mismatch in 989) |
| 2 | **92.7%** |
| 3 | **90.8%** |
| 4 | 77.0% |
| 5 | 64.4% |

**100 replays (seed=777, independent validation):**

| Player Turn | Buy Accuracy |
|-------------|-------------|
| 1 | **99.0%** |
| 2 | **92.9%** |
| 3 | **92.3%** |
| 4 | 78.9% |
| 5 | 68.1% |

Game result (100%) and turn count (100%) match perfectly across all samples.

**Fixes applied during cross-validation:**
1. Resource decay — blue/red/energy/attack reset to 0 at turn start
2. Un-buy detection — `inst clicked` on just-bought unit refunds purchase
3. Shift-click unbuy — `inst shift clicked` unbuys ALL bought instances of that type
4. Confirm-phase detection — first non-space click after action-commit space is skipped
5. Turn boundary alignment — emotes pushing buy/commit clicks into wrong turn slice
6. JS extraction — uses `beginTurnHistory` auto-play (not manual `recordClick`)

**Remaining pt2-5 gap** is from resource tracking drift during complex buy/unbuy/rebuy chains within a single turn. The parser's approximate resource model diverges from the engine's exact state, causing shift-click buy quantity miscalculation. Not fixable without full engine simulation.

### 8.9 Build Time Edge Cases

A unit with `buildTime: N` takes N turns to become ready. The parser tracks this per-instance. Edge case: `beginOwnTurnScript` with `"delay": N` (e.g., Chrono Filter, Iso Kronus) — the passive script doesn't fire until N turns after construction. The parser implements this.

---

## 9. OB Derivation Workflow

### 9.1 From Database to Opening Book Entries

1. **Select a set composition** (or key unit presence, e.g., "sets containing Wild Drone")
2. **Query winning-side buy sequences** for turns 1-N, stratified by player position (P1/P2) and starting state
3. **Apply consensus threshold**: If the top buy sequence accounts for >60% of games at that state, it's a strong candidate. If >40%, it's a moderate candidate. Below 40%, the position is "contested" — no single OB entry is justified
4. **Format as OB entry**: Convert to `{"self": [...], "buyable": [...], "buy": [...]}`
5. **Validate**: Run tournament games with the candidate OB vs without, measuring win rate impact

### 9.2 Consensus Thresholds

| Threshold | Meaning | Action |
|-----------|---------|--------|
| >60% | Strong consensus | Auto-include in OB |
| 40-60% | Moderate consensus | Include with review, or pick top if clear #1 |
| <40% | No consensus | Skip — let AI search handle it |

### 9.3 Self Condition Derivation

The `self` condition in OB entries specifies what units the player must own for the entry to match. This comes directly from `turn_state.units_owned`:

```sql
-- Find the dominant starting state for P2 turn 1 (should be 7 Drone + 2 Engineer)
SELECT ts.units_owned, COUNT(*)
FROM turn_state ts
WHERE ts.player = 1 AND ts.player_turn = 1
GROUP BY ts.units_owned
ORDER BY COUNT(*) DESC LIMIT 5;
```

### 9.4 Buyable Condition Derivation

The `buyable` condition specifies which Dominion cards must be in the set. For unit-specific entries (e.g., "when Wild Drone is present"), this is the key unit(s). For generic entries, `buyable` is empty.

The analysis can discover which units most strongly influence opening buys by measuring buy variance when a unit is present vs absent.

---

## 10. Integration: Smooth "Add New Replays" Flow

The user wants a single smooth flow for adding new replays that handles everything:

```bash
# 1. Have a file of new replay codes
# 2. One command does: fetch → insert metadata → validate → parse → store
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ \
    --fetch --codes-file new_codes.txt
```

Steps internally:
1. Read codes from file
2. For each code not yet in `replays_archive/`: fetch from S3, save `.json.gz`
3. For each code not yet in `replays` table: extract metadata from the replay JSON (ratings, result, deck, timestamps) and INSERT
4. For each code not yet balance-validated: run balance validation (existing logic)
5. For each code not yet parsed: decode + simulate + store turn data

**Existing DB insert code** currently lives in the JS parser (`filter_expert_replays.js`, `extract_training_data.js`). The Python pipeline would replicate the metadata extraction for new replays. For codes already in the DB (just needing parsing), step 3 is skipped.

---

## 11. Testing Strategy

### 11.1 Unit Tests

- **`test_resources.py`**: Parse `"6GGGRBB"` → correct ResourcePool. Handle integer values. Handle empty/None.
- **`test_decoder.py`**: Load a known `.json.gz`, verify card definitions, init cards, click count, turn count.
- **`test_simulator.py`**: Process a known replay's first 3 turns, verify: buy list matches expected, resource tracking correct, instance ID mapping correct, supply decrements.

### 11.2 Validation Against Known Games

Pick 5-10 replays where we know the opening sequence (from watching the game or from the JS viewer). Run the parser and verify the extracted buy sequences match.

### 11.3 Bulk Consistency Checks

After parsing all 102k replays:
- P1 turn 1 should always have starting state: `{"Drone": 6, "Engineer": 2}`
- P2 turn 1 should always have starting state: `{"Drone": 7, "Engineer": 2}`
- No negative supply values
- No negative resource values (would indicate tracking bug)
- Turn count distribution should be reasonable (median ~20-30 turns per game)

---

## 12. Dependencies

- Python 3.10+ (for `match` statements and `X | Y` union types)
- Standard library only: `sqlite3`, `gzip`, `json`, `dataclasses`, `pathlib`, `argparse`, `urllib`, `logging`
- **No external packages required** — maximizes portability for distribution
- Optional: `tqdm` for progress bars (graceful fallback if not installed)
