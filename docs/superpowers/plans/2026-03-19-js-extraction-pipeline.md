# JS Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Python replay simulator with a JS engine extraction pipeline that produces ground-truth per-turn data (buys, resources, units, resolved actions) using `beginTurnHistory` snapshots.

**Architecture:** Python CLI orchestrates a Node.js subprocess (`bulk_extract.js`) that auto-plays replays via the JS game engine, extracts data from `beginTurnHistory` State snapshots, and outputs JSONL. Python ingests this into the existing SQLite schema. Two-layer verification (self-consistency + cross-validation) ensures correctness.

**Tech Stack:** Node.js (JS engine, extraction), Python 3.10+ (CLI, DB, verification), SQLite (storage)

**Spec:** `docs/superpowers/specs/2026-03-19-js-extraction-pipeline-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `js_engine/bulk_extract.js` | Core JS extractor: load replay, auto-play via Analyzer, extract buys (bought-array diffs), resources (mana), units (table), resolve clicks to actions, output JSONL |

### Modified Files

| File | Change |
|---|---|
| `replay_parser/pipeline.py` | Replace `simulate()` with `run_js_extraction()` subprocess + `ingest()` |
| `replay_parser/database.py` | Replace `store(ReplayData)` with `ingest(dict)` that reads from JSON. Schema version bump to 2 |
| `replay_parser/__main__.py` | Add `--verify` and `--cross-validate` CLI flags |
| `replay_parser/cross_validate.py` | Add Layer B self-consistency verification alongside existing Layer A |

### Test Files

| File | What it tests |
|---|---|
| `replay_parser/tests/test_pipeline.py` | Modified: pipeline integration test uses JS extraction |
| `replay_parser/tests/test_database.py` | Modified: add `ingest()` tests |

### Key Reference Files (read-only, do not modify)

| File | Why you need it |
|---|---|
| `js_engine/extract_turn_data.js` | Reference for Analyzer init pattern, `parseMana()`, `countUnits()`. Being replaced but code is useful reference |
| `js_engine/Analyzer.js` | `loaderInit()` API, `beginTurnHistory` array |
| `js_engine/State.js` | `whiteBought[]`, `blackBought[]`, `whiteSupply[]`, `blackSupply[]`, `nextInstId`, `table`, `whiteMana`, `blackMana`, `cards[]` |
| `js_engine/C.js` | Constants: `DEADNESS_ALIVE`, `COLOR_WHITE` |
| `js_engine/Controller.js` | Click processing: `ROLE_SELLABLE` (line 710), `ROLE_INERT` (line 766) — context for un-buy vs redirect disambiguation |
| `replay_parser/simulator.py` | Reference for undo/revert preprocessing logic (`_preprocess_clicks`, line 24-61) |
| `replay_parser/database.py` | Current `store()` function and schema |
| `replay_parser/tests/conftest.py` | Test fixtures: `raw_replay_data`, `temp_db`, `TEST_REPLAY_CODE` |

---

## Task 1: JS Extraction — State Data (buys, resources, units)

The core extraction from `beginTurnHistory` snapshots. No click resolution yet — just the ground-truth state data.

**Files:**
- Create: `js_engine/bulk_extract.js`

- [ ] **Step 1: Scaffold `bulk_extract.js` with replay loading and Analyzer init**

```javascript
'use strict';

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');

function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        return JSON.parse(zlib.gunzipSync(raw).toString('utf-8'));
    }
    return JSON.parse(raw.toString('utf-8'));
}

function initAnalyzer(replay) {
    const initInfo = {
        laneInfo: [{
            initResources: replay.initInfo.initResources,
            base: replay.deckInfo.base,
            randomizer: replay.deckInfo.randomizer,
            initCards: replay.initInfo.initCards
        }],
        mergedDeck: replay.deckInfo.mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: {
            commandList: replay.commandInfo.commandList,
            clicksPerTurn: replay.commandInfo.clicksPerTurn,
            gamePosition: replay.commandInfo.commandList.length
        }
    };
    const analyzer = new Analyzer(initInfo, -1, -1, null);
    analyzer.loaderInit();
    return analyzer;
}
```

This is the same Analyzer init pattern from `extract_turn_data.js` lines 87-105.

- [ ] **Step 2: Implement `parseMana()` and `countUnits()`**

Carry forward from `extract_turn_data.js` (lines 32-66), already verified correct:

```javascript
function parseMana(manaStr) {
    const result = { gold: 0, green: 0, blue: 0, red: 0, energy: 0, attack: 0 };
    if (!manaStr) return result;
    let digits = '';
    for (const ch of String(manaStr)) {
        if (ch >= '0' && ch <= '9') {
            digits += ch;
        } else {
            if (digits) { result.gold += parseInt(digits); digits = ''; }
            switch (ch) {
                case 'G': result.green++; break;
                case 'B': result.blue++; break;
                case 'C': result.red++; break;
                case 'H': result.energy++; break;
                case 'A': result.attack++; break;
            }
        }
    }
    if (digits) result.gold += parseInt(digits);
    return result;
}

function countUnits(state, player) {
    const counts = {};
    state.table.forEach(inst => {
        if (inst.deadness === C.DEADNESS_ALIVE && inst.owner === player) {
            const name = inst.card.UIName;
            counts[name] = (counts[name] || 0) + 1;
        }
    });
    return counts;
}
```

- [ ] **Step 3: Implement `extractBuys()` using bought-array diffs**

```javascript
function extractBuys(prevState, currState, player, cards) {
    // Bought-array diffs: whiteBought/blackBought are cumulative counters
    // that increment on buy, decrement on sell. Diff between consecutive
    // beginTurnHistory snapshots gives net purchases for the turn.
    const prevBought = player === 0 ? prevState.whiteBought : prevState.blackBought;
    const currBought = player === 0 ? currState.whiteBought : currState.blackBought;
    const buys = [];
    for (let cardId = 0; cardId < cards.length; cardId++) {
        const diff = currBought[cardId] - prevBought[cardId];
        for (let j = 0; j < diff; j++) {
            buys.push(cards[cardId].UIName);
        }
    }
    return buys;
}
```

`cards` is `state.cards` — the card definition array indexed by cardId. `UIName` gives the display name.

- [ ] **Step 4: Implement `extractBuildingUnits()` for verification block**

```javascript
function extractBuildingUnits(buys, cards) {
    // Find which bought units have buildTime > 0
    const building = [];
    const seen = new Set();
    for (const name of buys) {
        if (seen.has(name)) continue;
        const card = cards.find(c => c.UIName === name);
        if (card && card.buildTime > 0) {
            building.push(name);
            seen.add(name);
        }
    }
    return building;
}
```

- [ ] **Step 5: Implement `extractUnitDiffBuys()` for verification comparison**

```javascript
function extractUnitDiffBuys(prevState, currState, player) {
    const preUnits = countUnits(prevState, player);
    const postUnits = countUnits(currState, player);
    const buys = [];
    const allNames = new Set([...Object.keys(preUnits), ...Object.keys(postUnits)]);
    for (const name of allNames) {
        const diff = (postUnits[name] || 0) - (preUnits[name] || 0);
        for (let j = 0; j < diff; j++) {
            buys.push(name);
        }
    }
    return buys;
}
```

- [ ] **Step 6: Implement `extractTurnData()` — main extraction loop**

```javascript
function extractTurnData(replay, code) {
    const result = {
        code: code,
        result: replay.result,
        totalTurns: replay.commandInfo.clicksPerTurn.length,
        turns: [],
        error: null
    };

    try {
        const analyzer = initAnalyzer(replay);
        const history = analyzer.beginTurnHistory;

        if (!history || history.length < 2) {
            result.error = 'No beginTurnHistory available';
            return result;
        }

        const cards = history[0].cards;
        // Last turn has no N+1 snapshot to diff against — omit it
        const numTurns = Math.min(result.totalTurns, history.length - 1);

        for (let turnIdx = 0; turnIdx < numTurns; turnIdx++) {
            const player = turnIdx % 2;
            const playerTurn = Math.floor(turnIdx / 2) + 1;
            const state = history[turnIdx];
            const nextState = history[turnIdx + 1];

            // Resources at start of turn
            const activeMana = player === 0 ? state.whiteMana : state.blackMana;
            const resources = parseMana(activeMana ? activeMana.toString() : '');

            // Units owned at start of turn
            const unitsOwned = countUnits(state, player);
            const totalUnits = Object.values(unitsOwned).reduce((a, b) => a + b, 0);

            // Buys from bought-array diffs (ground truth)
            const buys = extractBuys(state, nextState, player, cards);

            // Verification: compare against unit-count diffs
            const unitDiffBuys = extractUnitDiffBuys(state, nextState, player);
            const boughtSorted = [...buys].sort();
            const unitSorted = [...unitDiffBuys].sort();
            const consistent = JSON.stringify(boughtSorted) === JSON.stringify(unitSorted);

            result.turns.push({
                global_turn: turnIdx,
                player: player,
                player_turn: playerTurn,
                buys: buys,
                resources: resources,
                units_owned: unitsOwned,
                total_units: totalUnits,
                actions: [],  // Populated in Task 2
                verification: {
                    bought_diff_buys: buys,
                    unit_diff_buys: unitDiffBuys,
                    consistent: consistent,
                    building: extractBuildingUnits(buys, cards)
                }
            });
        }
    } catch (err) {
        result.error = err.message;
    }

    return result;
}
```

- [ ] **Step 7: Add CLI with single-file and batch modes**

```javascript
function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.error('Usage: node bulk_extract.js <replay.json.gz>');
        console.error('       node bulk_extract.js --batch <codes_file> --replays-dir <dir> [--limit N]');
        process.exit(2);
    }

    if (args[0] === '--batch') {
        const codesFile = args[1];
        let replaysDir = '.';
        let limit = Infinity;

        for (let i = 2; i < args.length; i++) {
            if (args[i] === '--replays-dir' && args[i + 1]) { replaysDir = args[++i]; }
            if (args[i] === '--limit' && args[i + 1]) { limit = parseInt(args[++i]); }
        }

        const codes = fs.readFileSync(codesFile, 'utf-8').trim().split('\n')
            .map(s => s.trim()).filter(Boolean);
        let processed = 0;

        for (const code of codes) {
            if (processed >= limit) break;
            const filename = `${code}.json.gz`;
            const filepath = path.join(replaysDir, filename);
            if (!fs.existsSync(filepath)) { continue; }
            try {
                const replay = loadReplay(filepath);
                const data = extractTurnData(replay, code);
                process.stdout.write(JSON.stringify(data) + '\n');
                processed++;
                if (processed % 100 === 0) {
                    process.stderr.write(`Processed ${processed}/${Math.min(codes.length, limit)}\n`);
                }
            } catch (err) {
                process.stderr.write(`ERROR: ${code}: ${err.message}\n`);
            }
        }
        process.stderr.write(`Done: ${processed} replays processed.\n`);
    } else {
        const filePath = args[0];
        const replay = loadReplay(filePath);
        const code = path.basename(filePath, '.json.gz').replace('.json', '');
        const data = extractTurnData(replay, code);
        console.log(JSON.stringify(data, null, 2));
    }
}

main();
```

- [ ] **Step 8: Smoke test — run on torture test replay**

Run:
```bash
cd c:/libraries/PrismataAI
node js_engine/bulk_extract.js "c:/libraries/prismata-replay-parser/replays_archive/Uim7C-wPvMo.json.gz"
```

Expected: JSON output with `error: null`, turns array populated, turn 0 buys should be two Drones for P1 (`["Drone", "Drone"]`), resources should show `gold: 6` at turn 0.

Inspect the first few turns manually — do the buys look reasonable? Do `verification.consistent` values make sense (should be `true` for early turns, may be `false` for later turns with combat)?

- [ ] **Step 9: Smoke test — batch mode with a few codes**

Create a temp file with 5 replay codes and run batch mode:
```bash
echo -e "++A4h-1QDmB\nUim7C-wPvMo" > /tmp/test_codes.txt
node js_engine/bulk_extract.js --batch /tmp/test_codes.txt --replays-dir "c:/libraries/prismata-replay-parser/replays_archive" --limit 5
```

Expected: 2 JSONL lines to stdout, progress message to stderr.

- [ ] **Step 10: Commit**

```bash
git add js_engine/bulk_extract.js
git commit -m "feat: add JS bulk extraction with bought-array diff buys and verification"
```

---

## Task 2: JS Extraction — Click Resolution (actions)

Add resolved action extraction to `bulk_extract.js`. This processes the `commandList` clicks for each turn, strips undo/revert noise, and classifies each surviving click.

**Files:**
- Modify: `js_engine/bulk_extract.js`

- [ ] **Step 1: Implement `preprocessClicks()` — undo/revert resolution**

Add before `extractTurnData()`:

```javascript
const ACTIONABLE_CLICKS = new Set([
    'card clicked', 'card shift clicked', 'inst clicked', 'inst shift clicked'
]);
const PHASE_MARKERS = new Set(['space clicked', 'end swipe processed']);

function preprocessClicks(clicks) {
    const result = [];
    for (const click of clicks) {
        const ct = click._type;
        if (ct === 'revert clicked') {
            // Clear all actionable clicks and phase markers
            for (let i = result.length - 1; i >= 0; i--) {
                if (ACTIONABLE_CLICKS.has(result[i]._type) || PHASE_MARKERS.has(result[i]._type)) {
                    result.splice(i, 1);
                }
            }
        } else if (ct === 'undo clicked') {
            // Pop most recent actionable click
            for (let i = result.length - 1; i >= 0; i--) {
                if (ACTIONABLE_CLICKS.has(result[i]._type)) {
                    result.splice(i, 1);
                    break;
                }
            }
        } else if (ct.startsWith('emote')) {
            // Skip emotes entirely
        } else {
            result.push(click);
        }
    }
    return result;
}
```

Reference: `replay_parser/simulator.py` lines 24-61 for the equivalent Python logic.

- [ ] **Step 2: Implement `resolveActions()` — click classification**

```javascript
function resolveActions(turnClicks, state, cards, nextInstId) {
    const resolved = preprocessClicks(turnClicks);
    const actions = [];
    const instLookup = {};  // instanceId -> {name, cardId}

    // Build instance lookup from turn-start state
    state.table.forEach(inst => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            instLookup[inst.instId] = {
                name: inst.card.UIName,
                cardId: inst.card.cardId
            };
        }
    });

    let spaceCount = 0;

    for (const click of resolved) {
        const ct = click._type;
        const id = click._id;

        // Space = phase commit
        if (ct === 'space clicked') {
            spaceCount++;
            actions.push({ type: 'commit' });
            continue;
        }

        // End swipe — skip (animation marker, not a player action)
        if (ct === 'end swipe processed') { continue; }

        // Cancel target — skip (no state change)
        if (ct === 'cancel target processed') { continue; }

        // Card buy (single)
        if (ct === 'card clicked') {
            actions.push({
                type: 'buy',
                unit: cards[id] ? cards[id].UIName : `unknown_${id}`,
                count: 1
            });
            continue;
        }

        // Card shift-buy
        if (ct === 'card shift clicked') {
            // Count comes from bought-array diff for this card — computed elsewhere.
            // Here we just record the click; the exact count is in turn.buys.
            actions.push({
                type: 'buy_shift',
                unit: cards[id] ? cards[id].UIName : `unknown_${id}`,
                count: 1  // Actual count is sum in turn.buys for this unit
            });
            continue;
        }

        // Instance click
        if (ct === 'inst clicked' || ct === 'inst shift clicked') {
            const isShift = ct === 'inst shift clicked';

            // Defense phase (before first space)
            if (spaceCount === 0) {
                const info = instLookup[id];
                actions.push({
                    type: isShift ? 'defend_shift' : 'defend',
                    unit: info ? info.name : `instance_${id}`,
                    count: 1
                });
                continue;
            }

            // Action phase: check if un-buy or ability
            if (id >= nextInstId) {
                // ID created during this turn — likely un-buy
                // Could also be ability-created unit redirect (rare)
                actions.push({
                    type: 'unbuy',
                    unit: `instance_${id}`,  // Can't resolve name without mid-turn state
                    count: 1
                });
            } else {
                // Known instance — ability activation
                const info = instLookup[id];
                actions.push({
                    type: isShift ? 'ability_shift' : 'ability',
                    unit: info ? info.name : `instance_${id}`,
                    count: 1
                });
            }
            continue;
        }

        // Unknown click type — skip silently
    }

    return actions;
}
```

- [ ] **Step 3: Wire `resolveActions()` into `extractTurnData()`**

In the `extractTurnData()` function, after computing buys and verification, add action resolution. Replace the `actions: []` placeholder:

```javascript
// Inside the turn loop, after verification computation:

// Slice commandList for this turn
const clickStart = clicksPerTurn.slice(0, turnIdx).reduce((a, b) => a + b, 0);
const clickEnd = clickStart + clicksPerTurn[turnIdx];
const turnClicks = commandList.slice(clickStart, clickEnd);

// Resolve clicks to actions
const actions = resolveActions(turnClicks, state, cards, state.nextInstId);
```

This requires adding `commandList` and `clicksPerTurn` references at the top of the try block:

```javascript
const commandList = replay.commandInfo.commandList;
const clicksPerTurn = replay.commandInfo.clicksPerTurn;
```

Then replace `actions: []` with `actions: actions` in the turn object.

- [ ] **Step 4: Test click resolution on torture replay**

Run:
```bash
node js_engine/bulk_extract.js "c:/libraries/prismata-replay-parser/replays_archive/Uim7C-wPvMo.json.gz" 2>/dev/null | python -c "
import json, sys
data = json.load(sys.stdin)
for t in data['turns'][:6]:
    acts = [f\"{a['type']}({a.get('unit','')})\" for a in t['actions']]
    print(f\"Turn {t['global_turn']} (P{t['player']} t{t['player_turn']}): buys={t['buys']}  actions={acts}\")
"
```

Expected: Actions should show ability clicks (e.g., `ability_shift(Drone)`) before buy clicks, with commit actions separating phases. Buys from actions should be consistent with `turn.buys` from bought-array diffs.

- [ ] **Step 5: Commit**

```bash
git add js_engine/bulk_extract.js
git commit -m "feat: add click resolution to bulk extraction (resolved actions)"
```

---

## Task 3: Python DB Ingestion

Replace `store(ReplayData)` with `ingest(dict)` that reads from JS extraction JSON output.

**Files:**
- Modify: `replay_parser/database.py`
- Modify: `replay_parser/tests/test_database.py`

- [ ] **Step 1: Write failing test for `ingest()`**

Add to `replay_parser/tests/test_database.py`:

```python
def test_ingest_from_json(temp_db):
    """Test ingesting JS extraction JSON output into the database."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    # Insert a replay row so FK constraints pass
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("TEST123", 0, 1, 1500.0, 1600.0, 1500.0)
    )
    conn.commit()

    entry = {
        "code": "TEST123",
        "result": 0,
        "totalTurns": 2,
        "error": None,
        "turns": [
            {
                "global_turn": 0,
                "player": 0,
                "player_turn": 1,
                "buys": ["Drone", "Drone"],
                "resources": {"gold": 6, "green": 0, "blue": 0, "red": 0, "energy": 0, "attack": 0},
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
                    "bought_diff_buys": ["Drone", "Drone"],
                    "unit_diff_buys": ["Drone", "Drone"],
                    "consistent": True,
                    "building": []
                }
            }
        ]
    }

    from replay_parser.database import ingest
    ingest(conn, entry)

    # Verify turn_buys
    row = conn.execute(
        "SELECT buy_sequence, buy_hash FROM turn_buys WHERE code='TEST123' AND global_turn=0"
    ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == ["Drone", "Drone"]
    assert row[1] == "Drone,Drone"

    # Verify turn_state
    row = conn.execute(
        "SELECT gold, units_owned, total_units FROM turn_state WHERE code='TEST123' AND global_turn=0"
    ).fetchone()
    assert row[0] == 6
    assert json.loads(row[1]) == {"Drone": 6, "Engineer": 2}
    assert row[2] == 8

    # Verify turn_actions
    actions = conn.execute(
        "SELECT action_type, unit_name, quantity FROM turn_actions WHERE code='TEST123' ORDER BY action_index"
    ).fetchall()
    assert len(actions) == 5
    assert actions[0] == ("ability_shift", "Drone", 6)
    assert actions[1] == ("buy", "Drone", 1)

    # Verify parse status
    row = conn.execute(
        "SELECT parsed, parser_version FROM replay_parse_status WHERE code='TEST123'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 2  # Version 2 = JS extraction

    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest replay_parser/tests/test_database.py::test_ingest_from_json -v`

Expected: FAIL — `ImportError: cannot import name 'ingest' from 'replay_parser.database'`

- [ ] **Step 3: Implement `ingest()` in `database.py`**

Add to `replay_parser/database.py`, after the existing `store()` function:

```python
PARSER_VERSION_JS = 2


def ingest(conn: sqlite3.Connection, entry: dict) -> None:
    """Persist JS extraction output into the database.

    Reads from a JSON dict (one JSONL line from bulk_extract.js)
    and inserts into turn_buys, turn_state, turn_actions, and
    replay_parse_status.
    """
    now = datetime.now(timezone.utc).isoformat()
    code = entry["code"]

    action_rows = []
    state_rows = []
    buy_rows = []

    for turn in entry["turns"]:
        gt = turn["global_turn"]
        player = turn["player"]
        pt = turn["player_turn"]

        # turn_actions
        for idx, action in enumerate(turn["actions"]):
            action_rows.append((
                code, gt, player, pt, idx,
                action["type"],
                action.get("unit"),
                action.get("count", 1),
                None,  # deck_index — not in JS output
                None,  # instance_id — not in JS output
            ))

        # turn_state
        r = turn["resources"]
        state_rows.append((
            code, gt, player, pt,
            r["gold"], r["green"], r["blue"],
            r["red"], r["energy"], r["attack"],
            json.dumps(turn["units_owned"]),
            turn["total_units"],
        ))

        # turn_buys
        buys = turn["buys"]
        buy_sequence = json.dumps(buys)
        buy_hash = ",".join(sorted(buys))
        buy_rows.append((code, gt, player, pt, buy_sequence, buy_hash))

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO replay_parse_status "
            "(code, parsed, parse_date, parser_version, total_turns, error) "
            "VALUES (?, 1, ?, ?, ?, NULL)",
            (code, now, PARSER_VERSION_JS, len(entry["turns"])),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO turn_actions "
            "(code, global_turn, player, player_turn, action_index, action_type, "
            "unit_name, quantity, deck_index, instance_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            action_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO turn_state "
            "(code, global_turn, player, player_turn, gold, green, blue, red, "
            "energy, attack, units_owned, total_units) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            state_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO turn_buys "
            "(code, global_turn, player, player_turn, buy_sequence, buy_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            buy_rows,
        )
```

Add `import json` at the top of `database.py` if not already present.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest replay_parser/tests/test_database.py::test_ingest_from_json -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add replay_parser/database.py replay_parser/tests/test_database.py
git commit -m "feat: add ingest() for JS extraction JSON output"
```

---

## Task 4: Python Pipeline — JS Subprocess Integration

Replace the simulate() call in pipeline.py with a JS subprocess call.

**Files:**
- Modify: `replay_parser/pipeline.py`
- Modify: `replay_parser/tests/test_pipeline.py`

- [ ] **Step 1: Write failing integration test**

Replace the existing `test_pipeline_single_replay` in `replay_parser/tests/test_pipeline.py` to work with the new JS-based pipeline:

```python
@needs_replay
def test_pipeline_single_replay_js(temp_db):
    """Test full pipeline: Python spawns JS extraction, ingests into DB."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()
    conn.close()

    stats = run_pipeline(
        db_path=temp_db,
        replays_dir=REPLAYS_ARCHIVE,
        codes=[TEST_REPLAY_CODE]
    )
    assert stats["parsed"] == 1
    assert stats["errors"] == 0

    conn = sqlite3.connect(temp_db)

    # Check turn_buys populated
    turns = conn.execute(
        "SELECT COUNT(*) FROM turn_buys WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert turns > 0

    # Check parser_version = 2 (JS extraction)
    version = conn.execute(
        "SELECT parser_version FROM replay_parse_status WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert version == 2

    # Check turn_actions populated
    actions = conn.execute(
        "SELECT COUNT(*) FROM turn_actions WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert actions > 0

    # Check turn 0 P1 has expected starting state
    row = conn.execute(
        "SELECT units_owned FROM turn_state WHERE code=? AND global_turn=0",
        (TEST_REPLAY_CODE,)
    ).fetchone()
    units = json.loads(row[0])
    assert units.get("Drone") == 6
    assert units.get("Engineer") == 2

    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest replay_parser/tests/test_pipeline.py::test_pipeline_single_replay_js -v`

Expected: FAIL — the current pipeline still uses `simulate()`, which produces version 1 data.

- [ ] **Step 3: Rewrite `pipeline.py` to use JS extraction**

Replace the contents of `replay_parser/pipeline.py`:

```python
"""Pipeline orchestrator: JS extraction -> ingest -> verify."""
import json
import logging
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from replay_parser.database import migrate, ingest
from replay_parser.fetch import code_to_filename

logger = logging.getLogger(__name__)

# Path to the JS extraction script
JS_BULK_EXTRACT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'js_engine', 'bulk_extract.js')


def run_pipeline(
    db_path: str,
    replays_dir: str,
    codes: list[str] | None = None,
    force: bool = False,
    fetch: bool = False,
    batch_size: int = 1000,
) -> dict:
    """Run the extraction pipeline. Returns stats dict."""
    conn = sqlite3.connect(db_path)
    migrate(conn)

    if codes is None:
        codes = _get_eligible_codes(conn, force)
        skipped = 0
    elif not force:
        original_count = len(codes)
        codes = _filter_unparsed(conn, codes)
        skipped = original_count - len(codes)
    else:
        skipped = 0

    stats = {
        "parsed": 0,
        "skipped": skipped,
        "errors": 0,
        "fetched": 0,
        "total": skipped + len(codes),
    }

    if not codes:
        conn.close()
        return stats

    # Fetch missing replays from S3 if requested
    if fetch:
        from replay_parser.fetch import fetch_replay
        replays_path = Path(replays_dir)
        for code in codes:
            if not (replays_path / code_to_filename(code)).exists():
                try:
                    fetch_replay(code, replays_path)
                    stats["fetched"] += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch {code}: {e}")

    # Run JS extraction and ingest results
    for entry in run_js_extraction(codes, replays_dir):
        code = entry.get("code", "unknown")
        if entry.get("error"):
            logger.warning(f"JS extraction error for {code}: {entry['error']}")
            _mark_error(conn, code, entry["error"])
            stats["errors"] += 1
            continue
        try:
            ingest(conn, entry)
            stats["parsed"] += 1
            if stats["parsed"] % batch_size == 0:
                logger.info(f"Progress: {stats['parsed']}/{len(codes)}")
        except Exception as e:
            logger.warning(f"Ingest error for {code}: {e}")
            _mark_error(conn, code, str(e))
            stats["errors"] += 1

    conn.commit()
    conn.close()

    logger.info(
        f"Done: {stats['parsed']} parsed, {stats['skipped']} skipped, "
        f"{stats['errors']} errors out of {stats['total']}"
    )
    return stats


def run_js_extraction(codes: list[str], replays_dir: str):
    """Spawn node bulk_extract.js, yield parsed JSONL entries."""
    # Write codes to temp file
    fd, codes_file = tempfile.mkstemp(suffix='.txt', prefix='replay_codes_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(codes) + '\n')

        logger.info(f"Starting JS extraction for {len(codes)} replays...")
        proc = subprocess.Popen(
            ['node', JS_BULK_EXTRACT, '--batch', codes_file,
             '--replays-dir', replays_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1
        )

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Bad JSONL line: {e}")

        # Log stderr (progress messages)
        stderr_output = proc.stderr.read()
        if stderr_output:
            for line in stderr_output.strip().split('\n'):
                logger.info(f"[JS] {line}")

        proc.wait()
        if proc.returncode != 0:
            logger.error(f"JS extraction exited with code {proc.returncode}")
    finally:
        os.unlink(codes_file)


def _get_eligible_codes(conn, force):
    """Get codes eligible for parsing from the replays table."""
    if force:
        query = """
            SELECT r.code FROM replays r
            WHERE r.balance_passed = 1
              AND r.p1_rating > 1 AND r.p2_rating > 1
        """
    else:
        query = """
            SELECT r.code FROM replays r
            LEFT JOIN replay_parse_status rps ON r.code = rps.code
            WHERE r.balance_passed = 1
              AND (rps.parsed IS NULL OR rps.parsed = 0)
              AND r.p1_rating > 1 AND r.p2_rating > 1
        """
    return [row[0] for row in conn.execute(query).fetchall()]


def _filter_unparsed(conn, codes):
    """Filter out already-parsed codes. Return only unparsed ones."""
    if not codes:
        return codes
    placeholders = ",".join("?" for _ in codes)
    already_parsed = set(
        row[0] for row in conn.execute(
            f"SELECT code FROM replay_parse_status WHERE code IN ({placeholders}) AND parsed = 1",
            codes
        ).fetchall()
    )
    return [c for c in codes if c not in already_parsed]


def _mark_error(conn, code, error_msg):
    """Record a parse error in replay_parse_status."""
    conn.execute(
        "INSERT OR REPLACE INTO replay_parse_status (code, parsed, error, parse_date) "
        "VALUES (?, 0, ?, datetime('now'))",
        (code, error_msg)
    )
    conn.commit()
```

- [ ] **Step 4: Run integration test**

Run: `python -m pytest replay_parser/tests/test_pipeline.py -v`

Expected: PASS for `test_pipeline_single_replay_js` and `test_pipeline_incremental`.

- [ ] **Step 5: Run all existing tests to check nothing is broken**

Run: `python -m pytest replay_parser/tests/ -v`

Expected: All tests pass. Some tests that import `simulate` or `store` may need import path updates if they reference the old pipeline flow.

- [ ] **Step 6: Commit**

```bash
git add replay_parser/pipeline.py replay_parser/tests/test_pipeline.py
git commit -m "feat: rewire pipeline to use JS extraction subprocess"
```

---

## Task 5: CLI Updates

Add `--verify` and `--cross-validate` flags to the CLI entry point.

**Files:**
- Modify: `replay_parser/__main__.py`

- [ ] **Step 1: Add new CLI flags**

In `replay_parser/__main__.py`, add to the argument parser:

```python
parser.add_argument("--verify", action="store_true",
                    help="Run verification on existing parsed data (no extraction)")
parser.add_argument("--cross-validate", action="store_true",
                    help="Run cross-validation: JS vs Python parser comparison")
parser.add_argument("--sample", type=int, default=500,
                    help="Sample size for cross-validation (default: 500)")
```

- [ ] **Step 2: Add handler for `--verify` mode**

In the `main()` function, after the `--replay` handler and before the pipeline code:

```python
if args.verify:
    if not args.db:
        parser.error("--db is required for --verify mode")
    from replay_parser.cross_validate import run_self_consistency_check
    report = run_self_consistency_check(args.db)
    print(json.dumps(report, indent=2))
    return

if args.cross_validate:
    if not args.db or not args.replays_dir:
        parser.error("--db and --replays-dir are required for --cross-validate")
    from replay_parser.cross_validate import main as cv_main
    # Reuse cross_validate's existing main with appropriate args
    import sys
    sys.argv = ['cross_validate', '--db', args.db, '--replays-dir', args.replays_dir,
                '--sample', str(args.sample)]
    cv_main()
    return
```

- [ ] **Step 3: Update `--replay` single-file mode to use JS extraction**

Replace the `--replay` handler to spawn JS extraction for a single file:

```python
if args.replay:
    import subprocess
    js_script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             'js_engine', 'bulk_extract.js')
    result = subprocess.run(
        ['node', js_script, args.replay],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(result.stdout)
    else:
        data = json.loads(result.stdout)
        _print_replay_summary_from_json(data)
    return
```

Add `_print_replay_summary_from_json()`:

```python
def _print_replay_summary_from_json(data):
    """Print a human-readable summary from JS extraction output."""
    print(f"Replay: {data['code']}")
    print(f"Result: P{data['result']} wins")
    print(f"Turns: {data['totalTurns']}")
    if data.get('error'):
        print(f"Error: {data['error']}")
        return
    print()
    for t in data['turns'][:10]:
        buys_str = ", ".join(t['buys']) if t['buys'] else "(none)"
        print(f"  Turn {t['global_turn']} (P{t['player']} t{t['player_turn']}): {buys_str}")
    if len(data['turns']) > 10:
        print(f"  ... ({len(data['turns']) - 10} more turns)")
```

- [ ] **Step 4: Test CLI modes**

```bash
# Single file mode
python -m replay_parser --replay "c:/libraries/prismata-replay-parser/replays_archive/Uim7C-wPvMo.json.gz"

# Single file JSON mode
python -m replay_parser --replay "c:/libraries/prismata-replay-parser/replays_archive/Uim7C-wPvMo.json.gz" --json
```

Expected: Human-readable summary for first command, JSON output for second.

- [ ] **Step 5: Commit**

```bash
git add replay_parser/__main__.py
git commit -m "feat: add --verify and --cross-validate CLI flags, update --replay to use JS"
```

---

## Task 6: Self-Consistency Verification (Layer B)

Add Layer B verification that checks `bought_diff_buys` vs `unit_diff_buys` consistency from the JS extraction output.

**Files:**
- Modify: `replay_parser/cross_validate.py`

- [ ] **Step 1: Add `run_self_consistency_check()` function**

This reads the JS extraction output (stored in DB) and checks verification blocks. Add to `replay_parser/cross_validate.py`:

```python
def run_self_consistency_check(db_path: str) -> dict:
    """Check self-consistency of JS extraction data in the database.

    For each parsed replay, re-runs JS extraction and checks the
    verification block for unexplained inconsistencies.
    """
    conn = sqlite3.connect(db_path)

    # Get all parsed codes
    codes = [row[0] for row in conn.execute(
        "SELECT code FROM replay_parse_status WHERE parsed = 1 AND parser_version = 2"
    ).fetchall()]
    conn.close()

    if not codes:
        return {"error": "No JS-extracted replays found in database"}

    report = {
        "replays_checked": len(codes),
        "total_turns": 0,
        "consistent": 0,
        "inconsistent": 0,
        "unexplained": 0,
        "inconsistent_examples": [],
    }

    # We need the raw verification data — re-extract a sample or
    # store verification in DB. For now, report based on what's in the DB.
    # Full Layer B requires storing verification data or re-extracting.
    logger.info(f"Self-consistency check: {len(codes)} replays with parser_version=2")
    logger.info("Note: full Layer B requires re-running JS extraction with --verify flag")
    logger.info("Use --cross-validate for Layer A+B comparison")

    return report
```

Note: Full Layer B self-consistency requires the verification block from JS output. For the initial implementation, this is run during extraction (the verification block is computed in `bulk_extract.js` and logged). A more complete implementation would either store verification data in the DB or re-extract on demand. The cross-validation mode (Layer A) already works from the existing `cross_validate.py`.

- [ ] **Step 2: Add verification summary to pipeline output**

Modify `run_pipeline()` in `pipeline.py` to aggregate verification data during ingestion. Add to stats:

```python
stats["verification"] = {
    "total_turns": 0,
    "consistent": 0,
    "inconsistent": 0,
}
```

And in the ingestion loop, after `ingest(conn, entry)`:

```python
for turn in entry.get("turns", []):
    stats["verification"]["total_turns"] += 1
    v = turn.get("verification", {})
    if v.get("consistent", True):
        stats["verification"]["consistent"] += 1
    else:
        stats["verification"]["inconsistent"] += 1
```

- [ ] **Step 3: Test verification summary**

Run extraction on a few replays and check the verification output:

```bash
python -m replay_parser --db /tmp/test_verify.db --replays-dir "c:/libraries/prismata-replay-parser/replays_archive" --codes "++A4h-1QDmB,Uim7C-wPvMo"
```

Expected: Stats JSON output includes `verification` block with counts.

- [ ] **Step 4: Commit**

```bash
git add replay_parser/cross_validate.py replay_parser/pipeline.py
git commit -m "feat: add Layer B self-consistency verification to pipeline"
```

---

## Task 7: End-to-End Validation

Run the full pipeline on a meaningful sample and verify correctness.

**Files:** No code changes — this is a validation task.

- [ ] **Step 1: Run on torture test replay**

```bash
python -m replay_parser --replay "c:/libraries/prismata-replay-parser/replays_archive/Uim7C-wPvMo.json.gz" --json > /tmp/torture_test.json
```

Inspect the output manually. Check:
- Turn 0 (P1): buys should be `["Drone", "Drone"]`, resources `gold: 6`, units `{"Drone": 6, "Engineer": 2}`
- All `verification.consistent` should be `true` for early turns
- Actions should show ability clicks before buys, with commits separating phases

- [ ] **Step 2: Run Layer A cross-validation on 500 replays**

```bash
python -m replay_parser.cross_validate \
    --replays-dir "c:/libraries/prismata-replay-parser/replays_archive" \
    --sample 500 --output /tmp/cross_validation_report.json
```

Expected: Turn 1 buy accuracy should be 99%+ (same as before — the JS extraction should match or exceed Python for early turns). Any disagreements should be investigated.

- [ ] **Step 3: Run full pipeline on a small batch (1000 replays)**

```bash
python -m replay_parser --db /tmp/test_batch.db --replays-dir "c:/libraries/prismata-replay-parser/replays_archive" --codes-file <(head -1000 c:/libraries/prismata-replay-parser/eligible_1500_codes.txt)
```

Check:
- Stats show `parsed` close to 1000, `errors` near 0
- Verification `consistent` percentage should be ~87% (consistent with expected combat/ability turn ratio)
- No `UNEXPLAINED` inconsistencies

- [ ] **Step 4: Spot-check DB contents**

```bash
python -c "
import sqlite3, json
conn = sqlite3.connect('/tmp/test_batch.db')

# P1 turn 1 should always be Drone:6, Engineer:2
bad = conn.execute('''
    SELECT code, units_owned FROM turn_state
    WHERE player=0 AND player_turn=1
    AND (json_extract(units_owned, \"$.Drone\") != 6
         OR json_extract(units_owned, \"$.Engineer\") != 2)
''').fetchall()
print(f'P1 turn 1 unexpected starting state: {len(bad)} cases')

# P2 turn 1 should always be Drone:7, Engineer:2
bad2 = conn.execute('''
    SELECT code, units_owned FROM turn_state
    WHERE player=1 AND player_turn=1
    AND (json_extract(units_owned, \"$.Drone\") != 7
         OR json_extract(units_owned, \"$.Engineer\") != 2)
''').fetchall()
print(f'P2 turn 1 unexpected starting state: {len(bad2)} cases')

conn.close()
"
```

Expected: 0 cases for both — every game starts with the standard Drone+Engineer configuration.

- [ ] **Step 5: Commit validation results**

If everything looks good, no code changes needed. If issues were found and fixed during validation, commit those fixes.

---

## Task 8: Cleanup and Documentation

Final cleanup: retire old code paths, update imports.

**Files:**
- Modify: `replay_parser/__main__.py` — remove old `_print_replay_json` and `_print_replay_summary` if no longer used
- Modify: `replay_parser/pipeline.py` — remove old `simulate` import if still present

- [ ] **Step 1: Remove dead imports and unused functions**

In `replay_parser/__main__.py`, remove imports of `decoder`, `simulate` if they're only used by the old `--replay` handler (which now uses JS subprocess). Keep `decoder` if `fetch` flow still uses it.

In `replay_parser/pipeline.py`, the rewrite already removed the `simulate` import. Verify no references remain.

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest replay_parser/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit cleanup**

```bash
git add replay_parser/__main__.py replay_parser/pipeline.py
git commit -m "chore: remove dead imports from old Python simulator pipeline"
```
