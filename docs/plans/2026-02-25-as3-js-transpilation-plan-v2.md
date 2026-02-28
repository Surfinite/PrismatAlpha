# Plan: AS3 → JavaScript Game Engine Transpilation (v2)

<!-- This is the updated plan after meta-review of 9 external reviews. Changes are marked with CHANGED comments. -->

## Context

Our C++ Prismata engine has bugs (50% replay pass rate vs AS3 ground truth). Training data generated on the buggy engine teaches strategies that exploit those bugs — when engine fixes were applied, AI win rate collapsed from 51.9% to ~11%. **We cannot generate useful training data until we have a perfectly faithful game engine.**

The Lunarch `MCDSAI3441.js` (1.83MB Emscripten module) IS the actual Master Bot AI from the live game. It runs in Node.js with only 2 functions: `InitializeAI(json)` and `GetAIMove(json)`. It's a black-box move selector — we can't access its internal game engine. But if we pair it with a faithful JS game engine that speaks its protocol, we get: **real Master Bot + correct game rules + runs on cloud compute**.

The AS3 game engine source is available (decompiled) and is the ground truth. AS3 → JS is a natural port (both ECMAScript-family). ~10,600 LOC of pure game logic, zero UI dependencies.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  selfplay_main.js                                        │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │ JS Game Engine│◄───►│ MCDSAI3441.js (Worker)       │  │
│  │ (AS3 transpile)│    │ Real Master Bot AI            │  │
│  │               │     │ InitializeAI / GetAIMove      │  │
│  └───────┬───────┘     └──────────────────────────────┘  │
│          │                                                │
│          ▼                                                │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │ JSONL Output  │────►│ Python vectorize → shards     │  │
│  │ (per position)│     │ (adapter + existing pipeline) │  │
│  └──────────────┘     └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

<!-- CHANGED: Added "Worker" to MCDSAI label and "adapter" to vectorize — R2, R3, R8 -->

**Game loop**: JS engine manages state → serializes to `State.toString()` JSON → sends to MCDSAI (in worker process) → gets clicks back → applies clicks via Controller → records position → repeat.

<!-- CHANGED: Explicit "worker process" — MCDSAI Emscripten global state requires process isolation for 2-player — R2, R3, R8 -->

**Training data**: JS outputs JSONL (one line per position with full game state). **A `state_adapter.js` converter** transforms `State.toString()` format (`{table, whiteMana, blackMana, ...}`) into vectorize.py's expected format (`{p0_units, p1_units, p0_resources, supply, card_set}`). Python `vectorize.py` converts to 1785-dim feature vectors + binary shards. No changes to existing training pipeline.

<!-- CHANGED: Added state_adapter.js — vectorize.py expects completely different format from State.toString(), confirmed by codebase inspection — R1, R3, R4, R5 -->

## Files to Transpile

### Tier 1 — Data Classes (~1,250 LOC, straightforward)
<!-- CHANGED: Added Rndm.as to Tier 1 (was excluded with "stub with throw") — Rndm IS reachable from PvP paths: swoosh line 3012, defense line 841, card ordering line 1200 — R2, R6, R7, R9 -->

| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `C.as` | 625 | `C.js` | All constants (phases, roles, mana indices, click types, error codes) |
| `Click.as` | 21 | `Click.js` | Click data class |
| `ClickResult.as` | 61 | `ClickResult.js` | Click validation result |
| `Order.as` | 88 | `Order.js` | Move/undo representation |
| `Mana.as` | 224 | `Mana.js` | Resource pool + string parse/serialize ("6HBG" format) |
| `SacDescription.as` | 39 | `SacDescription.js` | Sacrifice cost |
| `CreateDescription.as` | 95 | `CreateDescription.js` | Token creation spec |
| `Rndm.as` | 100 | `Rndm.js` | **Deterministic PRNG — faithful port of BitmapData.noise() algorithm** |

### Tier 2 — Core Engine (~5,800 LOC, the hard part)
| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `Script.as` | 104 | `Script.js` | Ability/buy/turn scripts |
| `Card.as` | 753 | `Card.js` | Card type from mergedDeck entries |
| `Inst.as` | 504 | `Inst.js` | Unit instance + `toObject()` + `compareWithJSON()` |
| `EndTurnObject.as` | 310 | `EndTurnObject.js` | Stagnation tracking stats (achievement fields stubbed, stagnation counters implemented) |
| `StateHelper.as` | 649 | `StateHelper.js` | Computed properties (defense, blocker eligibility) |
| `State.as` | 4,490 | `State.js` | Core game state machine — see section breakdown below |

<!-- CHANGED: Added State.js section breakdown — R1, R4, R5, R8 -->

**State.js internal sections** (transpile and test in this order):
1. **Constructor & initialization** (~200 LOC) — `initFromMergedDeck()`, field declarations
2. **toString / serialization** (~400 LOC) — `toString()`, `toJSON()`, state export
3. **Resource management** (~300 LOC) — mana operations, supply tracking
4. **Move execution** (~600 LOC) — `doAction()`, buy, use ability, assign blocker/frontline
5. **Phase transitions** (~400 LOC) — `beginPhase()`, `endPhase()`, phase state machine
6. **Defense & breach** (~500 LOC) — blocker assignment, damage resolution, breach logic
7. **Swoosh** (~460 LOC) — end-of-turn resolution (8 sub-phases: lifespan, sac, construction, buildTime, scripts, heal, regeneration, annihilation)
8. **Stagnation** (~300 LOC) — progress counters, draw detection (Phase 5, behind feature flag)
9. **Win condition** (~100 LOC) — `checkWin()`, game-over detection

### Tier 3 — Click Processing & AI Bridge (~3,400 LOC)
| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `Controller.as` | 2,574 | `Controller.js` | Click routing, undo/redo, phase transitions |
| `Analyzer.as` | 662 | `Analyzer.js` | Click validation, `analyzerFromState()`, `noUpdateClick()` |
| `StateUtil.as` | 156 | `StateUtil.js` | `convertToClicks()` — bridges MCDSAI output → engine |

### Tier 4 — Training Data Adapter (NEW)
<!-- CHANGED: Added explicit adapter tier — R1, R3, R4, R5 -->

| JS File | Purpose |
|---|---|
| `state_adapter.js` | Converts `State.toString()` JSON → vectorize.py expected format |
| `AS3Dictionary.js` | Dictionary wrapper guaranteeing deterministic iteration order |

### Excluded (not needed for PvP self-play)
- ~~`Rndm.as`~~ — **Now included** (Tier 1). PvP paths use it for ordering.
- `Trigger.as`, `Objective.as` — campaign/mission only
- `RaidAnalyzer.as`, `RaidSpawn.as` — raid mode only
- `MCDSEvent.as` — Flash UI events (replace with no-ops)
- `Errorbang.as` — UI error display (replace with console.error)

**Total: ~10,700 LOC across 16 files + 2 new utility files.**

## Critical Protocol Details

### MCDSAI Initialization
```javascript
// From AIThreadHandler.as:312-332
const payload = JSON.stringify({
    mergedDeck: simpleMergedDeck,  // Array of card objects with UIName as cardName
    aiParameters: aiParams         // From tmp_swf_extract/148_*.bin
});
CPPAI_InitializeAI(payload);
```

### MCDSAI Move Request
```javascript
// From AIThreadHandler.as:335-369
const payload = JSON.stringify({
    gameState: state.toString(30000),  // State.toString() output
    aiPlayerName: "HardestAI"
});
const response = JSON.parse(CPPAI_GetAIMove(payload));
// response.aiclicks = [{type: "card clicked", args: "Tarsier"}, ...]
```

### MCDSAI Worker Isolation
<!-- CHANGED: Added worker isolation section — Emscripten global state requires separate processes — R2, R3, R8 -->
```javascript
// Each AI player runs in a separate child process to avoid Emscripten global state conflicts
const { fork } = require('child_process');
const p1Worker = fork('./mcdsai_worker.js');
const p2Worker = fork('./mcdsai_worker.js');

// mcdsai_worker.js loads MCDSAI3441.js independently
// Communication via process.send() / process.on('message')
```

### Click Application (StateUtil.convertToClicks pattern)
```javascript
const analyzer = Analyzer.analyzerFromState(state);  // Clones state
for (const click of response.aiclicks) {
    if (analyzer.controller.inSwipe) {  // Auto end-swipe for daveAI
        analyzer.noUpdateClick(C.CLICK_END_SWIPE);
    }
    if (click.type === "inst clicked") {
        const id = StateUtil.findInstId(click.args, analyzer);  // Match by properties
        analyzer.noUpdateClick("inst clicked", id);
    } else if (click.type === "card clicked") {
        const cardId = analyzer.gameState.cardNameToCard(click.args).cardId;
        analyzer.noUpdateClick("card clicked", cardId);
    } else if (click.type === "space clicked") {
        analyzer.noUpdateClick("space clicked", -1);
    } else {
        // CHANGED: Fail-hard on unrecognized click types — R8
        throw new Error(`Unknown click type: ${click.type}`);
    }
}
state = analyzer.gameState;  // Post-move state
```

### Key: Instance Matching
MCDSAI identifies units by properties (cardName, owner, role, health, etc.), NOT by instId. `StateUtil.findInstId()` searches the state table for a matching instance via `Inst.compareWithJSON()`. This isomorphic matching must be implemented exactly.

<!-- CHANGED: Added deterministic tiebreaker — R8 -->
**Deterministic tiebreaker**: When multiple instances match `compareWithJSON()`, select the one with the **lowest instId**. This must be validated against live game behavior empirically. The AS3Dictionary wrapper ensures iteration order is consistent regardless.

### Key: Card Names
The MCDSAI expects **display names** ("Tarsier", not "Tesla Tower"). The mergedDeck uses `UIName` from `cardLibrary.jso` as the operational `cardName`. This aligns with `unit_index.json` which also uses display names (confirmed by codebase inspection).

### Key: AS3 Iteration Mapping
<!-- CHANGED: Added iteration convention — R9 -->
AS3 has two iteration constructs with different semantics:
- `for (key in obj)` → iterates **keys** → JS: `for (const key of map.keys())`
- `for each (val in obj)` → iterates **values** → JS: `for (const val of map.values())`

Confusing these silently produces wrong results. Every AS3 loop must be classified before transpilation.

### Key: Integer Arithmetic
<!-- CHANGED: Added integer truncation convention — R9, R6 -->
AS3 `int`/`uint` types truncate to 32-bit integers. JS `Number` is 64-bit float. In arithmetic paths (resource calculations, damage, turn counters), use `|0` for signed int truncation and `>>>0` for unsigned. Loop counters don't need this treatment. State.as has ~228 int/uint sites — audit and annotate critical ones during transpilation.

## Implementation Phases

<!-- CHANGED: Restructured phases — added Phase 0.5 (test infra), strengthened checkpoints, removed Phase 6 — R1, R3, R4, R5, R7, R8 -->

### Phase -1: Capture Golden Turn-by-Turn States (1 session)
<!-- APPLIED from Optional Enhancement #5 — R7 -->
- **Instrument sniffer to record full game state at every turn boundary** for 10 reference games via auto-spectate
- Beyond F6 snapshots (point-in-time): capture complete per-turn state sequences showing how the game evolves
- Target: 10 reference games covering diverse scenarios (rushes, long econ games, breach/defense, chill, multi-target abilities, stagnation)
- Output: JSON files with `State.toString()`-equivalent data at each turn boundary
- These become the primary golden reference for Phase 0.5 test infrastructure and Phase 2/3/4 validation
- **Checkpoint**: 10 reference games captured with full turn-by-turn state sequences.

### Phase 0: Scaffolding (1 session)
- Create `js_engine/` directory
- Set up Node.js MCDSAI wrapper (load module, cwrap functions)
- **Verify MCDSAI SHA256 hash on load** (pin to exact version)
- Verify MCDSAI init + first move works with existing `test_init.json`/`test_move.json`
- Parse `cardLibrary.jso` to build mergedDeck
- Parse AI parameters from `tmp_swf_extract/148_*.bin`
- **Implement `AS3Dictionary.js`** — wrapper class guaranteeing deterministic iteration order matching AS3 Dictionary semantics (insertion-order via Map, with `for..in`/`for each..in` helpers)
- **Implement `mcdsai_worker.js`** — child process wrapper for MCDSAI isolation
- **Checkpoint**: MCDSAI responds to init + move queries via worker process. AS3Dictionary wrapper has unit tests.

<!-- CHANGED: Added AS3Dictionary, worker isolation, version pinning to Phase 0 — ALL reviewers, R2, R5 -->

### Phase 0.5: Test Infrastructure (1 session)
<!-- CHANGED: NEW PHASE — unanimous reviewer consensus that test infra must precede transpilation -->
- **Capture 5-10 golden state fixtures** via F6 from live game at known positions (opening, mid-game, defense, breach, post-swoosh)
- Build **replay runner** — loads replay JSON, feeds clicks to engine, reports first failure point
- Build **turn-by-turn state comparator** — compares `State.toString()` output at each turn boundary against golden reference
- Build **automatic bisection tool** — given a failing replay, binary-searches for the first turn where state diverges
- Build **stratified test reporter** — categorizes results by game length (short ≤10, mid 11-40, long 41+, stagnation)
- **Ruffle oracle spike** (Optional Enhancement #2 — R4, R5, R6, R7): Test if [Ruffle](https://ruffle.rs/) (Rust Flash VM) can run the AS3 engine headless. If it can load `State.as` and execute game logic without UI, it becomes a perfect state comparison oracle — the ultimate golden reference beyond F6 captures and replays. If Ruffle can't run headless AS3 (likely — it targets SWF playback), move on; we have sufficient validation from Phase -1 captures and replays.
- **Checkpoint**: Can run a replay through a stub engine and get structured failure output with turn-by-turn diffs. Ruffle spike result documented (works/doesn't work).

### Phase 1: Tier 1 Data Classes (1 session)
- **AST-assisted transpilation spike** (Optional Enhancement #1 — R4, R9): Before hand-transpiling, try Apache Royale or an AS3 parser to auto-transpile `Mana.as` (224 LOC, pure data class). If output is >70% correct (only needs minor fixups), use AST-assisted approach for remaining Tier 1 files. If <70% correct or tooling setup takes >2 hours, abandon and hand-transpile — these are small files.
- Transpile C.js, Click.js, ClickResult.js, Order.js, Mana.js, SacDescription.js, CreateDescription.js, Script.js
- **Transpile Rndm.js** — faithful port of BitmapData.noise() PRNG algorithm (reverse-engineer seed→pixel mapping, validate output sequence against known AS3 seeds)
- Unit tests: Mana string round-trip, resource arithmetic, Rndm sequence verification
- **Checkpoint**: All constants and data classes working. Rndm produces identical sequences to AS3 for test seeds.

<!-- CHANGED: Added Rndm.js to Phase 1, strengthened checkpoint — R2, R6, R7, R9 -->

### Phase 2: Core Engine (2-3 sessions)
- Transpile Card.js, Inst.js, StateHelper.js, EndTurnObject.js (stub achievement fields, implement stagnation counters). **Mark stubbed vs implemented fields explicitly** (Optional Enhancement #6 — R4): each achievement field gets `/* STUB: achievement-only, not needed for PvP */` comment, each stagnation counter gets `/* IMPL: required for stagnation detection */` comment. This makes it obvious which parts are intentionally incomplete.
- Transpile State.js in section order:
  1. Constructor & initialization
  2. toString / serialization → **validate against golden fixtures immediately**
  3. Resource management
  4. Move execution
  5. Phase transitions
  6. Defense & breach
  7. Swoosh (8 sub-phases, ~460 LOC — most complex single function)
  8. Win condition
- **Checkpoint**: Can create initial state from mergedDeck, **apply 5 turns of hardcoded moves, serialize with `toString()`, and match golden reference at each step**. Replay runner passes on at least 3 short reference games.

<!-- CHANGED: Strengthened checkpoint from "can serialize" to "apply moves + match golden at each step" — R7 -->
<!-- CHANGED: Added State.js section ordering — R1, R4, R5, R8 -->

### Phase 3: Click Processing (1-2 sessions)
- Transpile Controller.js (2,574 lines — biggest after State)
  - `dispatch()` calls → no-op (headless)
  - `UIEvent.say()` → no-op
  - **Fail-hard on unrecognized click types** (throw, not silent ignore)
- Transpile Analyzer.js, StateUtil.js
  - `findInstId()` uses AS3Dictionary with lowest-instId tiebreaker
- **Checkpoint**: Can apply clicks from `test_move.json` MCDSAI response and get valid next state. Replay runner passes on **50+ reference games**.

<!-- CHANGED: Added fail-hard, instId tiebreaker, stronger checkpoint — R8 -->

### Phase 4: Integration & Validation (2-3 sessions)
<!-- CHANGED: Merged old Phase 4 (integration) and Phase 5 (validation) — R1, R5 -->
- Build complete self-play game loop with MCDSAI worker processes
- Build set randomizer (8 random advanced units + base set)
- Build **`state_adapter.js`** — converts State.toString() → vectorize.py format
- Build JSONL position exporter
- **Run replay validation against 2,127 Master Bot replays**
  - Target: **99%+ pass rate** with all remaining failures characterized
  - Use stratified reporter: short/mid/long/stagnation buckets
  - Use bisection tool for each failure to find first divergence
- Fix issues found by replay validation
- Run 10 self-play games end-to-end, verify data format compatibility with vectorize.py
- **Checkpoint**: 99%+ replay pass rate. 10 complete self-play games with valid JSONL output that vectorize.py accepts.

### Phase 5: Stagnation System (1-2 sessions)
<!-- CHANGED: Explicit stagnation phase with feature flag — R5, R6, R7, R8 -->
- Implement 4-level progress counter system behind feature flag:
  - Cutoffs: [2, 8, 20, 40] turns without progress
  - 12+ event types that count as "progress" (buy, attack, breach, etc.)
  - `reportProgress()` calls throughout State.js
  - `ENTER_CONFIRM` priority chain
  - "ANY" semantics for progress detection
- Validate stagnation against long games in replay set
- **Checkpoint**: Stagnation-length games in replay set pass. Feature flag toggles stagnation on/off cleanly.

### Abort/Rollback Criteria
<!-- CHANGED: Added per-phase abort criteria — R5 -->

| Phase | Abort Trigger | Pivot Action |
|---|---|---|
| Phase 0 | MCDSAI fails to load or respond | Investigate Emscripten compatibility; try older Node.js |
| Phase 0.5 | Can't capture golden states from live game | Use replay-derived states as golden reference |
| Phase 1 | Rndm.js can't reproduce AS3 sequences | Capture Rndm output tables from live game via F6 instrumentation; use lookup table |
| Phase 2 | State.toString() diverges on >50% of golden fixtures after 3 sessions | Evaluate AST-assisted transpilation for remaining sections |
| Phase 3 | Click processing fails on >30% of replays after 2 sessions | Compare Controller.js line-by-line with AS3; consider simpler click routing |
| Phase 4 | Replay pass rate stuck below 95% after 2 fix sessions | Triage remaining failures — if systematic, indicates architectural mismatch |

## Transpilation Conventions

- **ES2020+ JavaScript**, CommonJS modules (`require`/`module.exports`)
- **No TypeScript, no bundler** — correctness over elegance
- `flash.utils.Dictionary` → **`AS3Dictionary` wrapper class** (insertion-order iteration, `forIn()`/`forEach()` helpers)
- `Vector.<T>` → regular JavaScript `Array`
- `int`/`uint` arithmetic → **`|0` truncation** in resource/damage/counter paths (not loop vars)
- `for (key in dict)` → `dict.forIn((key, val) => ...)` or `for (const key of dict.keys())`
- `for each (val in dict)` → `dict.forEach((val) => ...)` or `for (const val of dict.values())`
- `state.dispatch(update, animate, event)` → no-op (no UI)
- `MCDSEvent` → no-op
- `Progression.inMissionWithName()` → return `false`
- `Game.gameInfo` / `Client.game` → stub objects
- `CheatCodes.enableTestingTools` → `false`
- Preserve AS3 class/method/variable names wherever possible
- Each AS3 file → one JS file in `js_engine/`
- **Unrecognized click types → throw** (fail-hard, not silent ignore)
- **`null` vs `undefined` convention** (Optional Enhancement #4 — R6): All AS3 `null` values map to JS `null`, never `undefined`. Use `=== null` checks (strict equality). This prevents subtle bugs where AS3 null-checks pass but JS undefined-checks fail silently. Initialize unset fields to `null`, not `undefined`.
- **Stub marking convention** (Optional Enhancement #6 — R4): Fields intentionally stubbed (achievements, campaign, UI) get `/* STUB: <reason> */` comments. Implemented fields get `/* IMPL: <purpose> */`. Aids future maintainability when revisiting partial implementations.

<!-- CHANGED: Added AS3Dictionary, int truncation, for..in/for each mapping, fail-hard, UI stub conventions — ALL reviewers, R9, R8, R3 -->

## Validation Strategy

<!-- CHANGED: Restructured and strengthened — R1, R5, R7, R8 -->

1. **Golden serialization tests** (Phase 0.5): 5-10 F6-captured states → `State.toString()` byte-for-byte comparison. Earliest gate.
2. **Mana round-trip**: Parse + serialize all 161 units' buyCost from cardLibrary.jso
3. **Rndm sequence verification**: Compare JS Rndm output against AS3 for known seeds (capture reference sequences from live game)
4. **Replay validation** (Phase 4): 2,127 Master Bot replays through JS engine
   - **Target: 99%+ pass rate** with all remaining failures characterized
   - **Turn-by-turn state comparison** (not just action legality)
   - **Stratified by game length**: short (≤10 turns), mid (11-40), long (41+), stagnation
   - **Automatic bisection** to find first divergence turn
5. **MCDSAI smoke test**: Complete self-play games that reach conclusion within 200 turns
6. **Feature extraction cross-check**: Run `state_adapter.js` output through `vectorize.py`, compare against C++ `extractFeatures()` on same position
7. **MCDSAI version pin**: SHA256 hash check of MCDSAI3441.js on every load

## MCDSAI Version Pin
<!-- CHANGED: Added version pinning section — R5 -->
```javascript
const crypto = require('crypto');
const EXPECTED_HASH = '<sha256 of MCDSAI3441.js>';  // Set during Phase 0
const actual = crypto.createHash('sha256').update(fs.readFileSync('MCDSAI3441.js')).digest('hex');
if (actual !== EXPECTED_HASH) throw new Error(`MCDSAI version mismatch: ${actual}`);
```

## Performance Estimate

- MCDSAI at ~1s think time: ~74 AI calls/game × 1s = ~74s/game
- Throughput: ~0.8 games/min per Node.js process
- 6 processes on c5.2xlarge: ~5 games/min
- 100K faithful games: ~$47 spot cost, ~333 instance-hours
- Slower than C++ (~4 games/min) but data is ground-truth quality

## Output Format

JSONL (one line per position):
```json
{"gameState": "<State.toString() JSON>", "turnNumber": 4, "playerIndex": 0, "outcome": 1.0, "gameId": 42}
```

**`state_adapter.js`** converts each gameState to vectorize.py format:
<!-- CHANGED: Added adapter documentation — R1, R3, R4, R5 -->
```json
{
  "state": {
    "p0_units": [{"name": "Drone", "blocking": false, "abilityUsed": false, ...}],
    "p1_units": [...],
    "p0_resources": {"gold": 6, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0},
    "supply": {"Drone": 20, "Engineer": 20, "Tarsier": 4, ...},
    "card_set": ["Tarsier", "Rhino", ...]
  },
  "turn": 4, "active_player": 0, "result": 1.0,
  "action": {"bought": ["Tarsier"]}
}
```

Python post-processing converts to binary shards (reuses existing `vectorize.py` + `load_selfplay.py` format).

## Key Files

| File | Purpose |
|---|---|
| `prismata_decompiled/scripts/mcds/engine/State.as` | Ground truth game engine (4,490 LOC) |
| `prismata_decompiled/scripts/mcds/engine/Controller.as` | Click processing (2,574 LOC) |
| `prismata_decompiled/scripts/mcds/engine/StateUtil.as` | MCDSAI ↔ engine bridge (156 LOC) |
| `prismata_decompiled/scripts/mcds/engine/Rndm.as` | Deterministic PRNG (100 LOC) |
| `prismata_decompiled/scripts/AI/AIThreadHandler.as` | MCDSAI protocol reference |
| `tmp_browser_client/MCDSAI3441.js` | Official Lunarch AI module |
| `tmp_browser_client/AIworker3441.js` | Worker wrapper (shows cwrap interface) |
| `tmp_swf_extract/148_*.bin` | AI parameters (full, JSON text) |
| `tmp_swf_extract/93_*.bin` | AI parameters (short, post-turn-16) |
| `bin/asset/config/cardLibrary.jso` | Unit definitions (161 units) |
| `training/data/unit_index.json` | Canonical unit index for features |
| `training/vectorize.py` | Python feature extraction (reuse for JSONL→shards) |
| `training/schema.json` | Feature schema (1785-dim) |

---

## Optional Enhancements

<!-- Enhancements 1, 2, 4, 5, 6 APPLIED (incorporated into plan above). Only #3 remains unapplied. -->

| # | Enhancement | Status |
|---|---|---|
| 1 | **Apache Royale / AST spike for Tier 1** | **APPLIED** → Phase 1 |
| 2 | **Ruffle spike for golden oracle** | **APPLIED** → Phase 0.5 |
| 3 | **Barrel `index.js`** for clean imports | Not applied — 15 files, explicit requires are fine |
| 4 | **Explicit `null` vs `undefined` convention** | **APPLIED** → Transpilation Conventions |
| 5 | **Phase -1: Capture per-turn intermediate states** | **APPLIED** → New Phase -1 |
| 6 | **EndTurnObject partial stub marking** | **APPLIED** → Phase 2 + Transpilation Conventions |
