# Plan: AS3 → JavaScript Game Engine Transpilation

## Context

Our C++ Prismata engine has bugs (50% replay pass rate vs AS3 ground truth). Training data generated on the buggy engine teaches strategies that exploit those bugs — when engine fixes were applied, AI win rate collapsed from 51.9% to ~11%. **We cannot generate useful training data until we have a perfectly faithful game engine.**

The Lunarch `MCDSAI3441.js` (1.83MB Emscripten module) IS the actual Master Bot AI from the live game. It runs in Node.js with only 2 functions: `InitializeAI(json)` and `GetAIMove(json)`. It's a black-box move selector — we can't access its internal game engine. But if we pair it with a faithful JS game engine that speaks its protocol, we get: **real Master Bot + correct game rules + runs on cloud compute**.

The AS3 game engine source is available (decompiled) and is the ground truth. AS3 → JS is a natural port (both ECMAScript-family). ~10,600 LOC of pure game logic, zero UI dependencies.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  selfplay_main.js                                    │
│  ┌──────────────┐     ┌──────────────────────────┐  │
│  │ JS Game Engine│◄───►│ MCDSAI3441.js (Worker)   │  │
│  │ (AS3 transpile)│    │ Real Master Bot AI        │  │
│  │               │     │ InitializeAI / GetAIMove  │  │
│  └───────┬───────┘     └──────────────────────────┘  │
│          │                                            │
│          ▼                                            │
│  ┌──────────────┐     ┌──────────────────────────┐  │
│  │ JSONL Output  │────►│ Python vectorize → shards │  │
│  │ (per position)│     │ (existing pipeline)       │  │
│  └──────────────┘     └──────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Game loop**: JS engine manages state → serializes to `State.toString()` JSON → sends to MCDSAI → gets clicks back → applies clicks via Controller → records position → repeat.

**Training data**: JS outputs JSONL (one line per position with full game state). Python `vectorize.py` converts to 1785-dim feature vectors + binary shards. No changes to existing training pipeline.

## Files to Transpile

### Tier 1 — Data Classes (~1,150 LOC, straightforward)
| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `C.as` | 625 | `C.js` | All constants (phases, roles, mana indices, click types, error codes) |
| `Click.as` | 21 | `Click.js` | Click data class |
| `ClickResult.as` | 61 | `ClickResult.js` | Click validation result |
| `Order.as` | 88 | `Order.js` | Move/undo representation |
| `Mana.as` | 224 | `Mana.js` | Resource pool + string parse/serialize ("6HBG" format) |
| `SacDescription.as` | 39 | `SacDescription.js` | Sacrifice cost |
| `CreateDescription.as` | 95 | `CreateDescription.js` | Token creation spec |

### Tier 2 — Core Engine (~5,800 LOC, the hard part)
| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `Script.as` | 104 | `Script.js` | Ability/buy/turn scripts |
| `Card.as` | 753 | `Card.js` | Card type from mergedDeck entries |
| `Inst.as` | 504 | `Inst.js` | Unit instance + `toObject()` + `compareWithJSON()` |
| `EndTurnObject.as` | 310 | `EndTurnObject.js` | Stagnation tracking stats |
| `StateHelper.as` | 649 | `StateHelper.js` | Computed properties (defense, blocker eligibility) |
| `State.as` | 4,490 | `State.js` | Core game state machine — phases, swoosh, moves, `toString()` |

### Tier 3 — Click Processing & AI Bridge (~3,400 LOC)
| AS3 File | LOC | JS Target | Notes |
|---|---|---|---|
| `Controller.as` | 2,574 | `Controller.js` | Click routing, undo/redo, phase transitions |
| `Analyzer.as` | 662 | `Analyzer.js` | Click validation, `analyzerFromState()`, `noUpdateClick()` |
| `StateUtil.as` | 156 | `StateUtil.js` | `convertToClicks()` — bridges MCDSAI output → engine |

### Excluded (not needed for PvP self-play)
- `Rndm.as` — PvP has no randomness (stub with throw if called)
- `Trigger.as`, `Objective.as` — campaign/mission only
- `RaidAnalyzer.as`, `RaidSpawn.as` — raid mode only
- `MCDSEvent.as` — Flash UI events (replace with no-ops)
- `Errorbang.as` — UI error display (replace with console.error)

**Total: ~10,600 LOC across 15 files.**

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
    }
}
state = analyzer.gameState;  // Post-move state
```

### Key: Instance Matching
MCDSAI identifies units by properties (cardName, owner, role, health, etc.), NOT by instId. `StateUtil.findInstId()` searches the state table for a matching instance via `Inst.compareWithJSON()`. This isomorphic matching must be implemented exactly.

### Key: Card Names
The MCDSAI expects **display names** ("Tarsier", not "Tesla Tower"). The mergedDeck uses `UIName` from `cardLibrary.jso` as the operational `cardName`.

## Implementation Phases

### Phase 0: Scaffolding (1 session)
- Create `js_engine/` directory
- Set up Node.js MCDSAI wrapper (load module, cwrap functions)
- Verify MCDSAI init + first move works with existing `test_init.json`/`test_move.json`
- Parse `cardLibrary.jso` to build mergedDeck
- Parse AI parameters from `tmp_swf_extract/148_*.bin`

### Phase 1: Tier 1 Data Classes (1 session)
- Transpile C.js, Click.js, ClickResult.js, Order.js, Mana.js, SacDescription.js, CreateDescription.js, Script.js
- Unit tests: Mana string round-trip, resource arithmetic
- **Checkpoint**: All constants and data classes working

### Phase 2: Core Engine (2-3 sessions)
- Transpile Card.js, Inst.js, StateHelper.js, EndTurnObject.js
- Transpile State.js (the big one — break into: constructor, toString, moves, phases, swoosh, defense, breach, stagnation, checkWin)
- **Checkpoint**: Can create initial state from mergedDeck, serialize with `toString()`, verify output matches `test_move.json` format

### Phase 3: Click Processing (1-2 sessions)
- Transpile Controller.js (2,574 lines — biggest after State)
- Transpile Analyzer.js, StateUtil.js
- **Checkpoint**: Can apply clicks from `test_move.json` MCDSAI response and get valid next state

### Phase 4: Integration (1 session)
- Build complete self-play game loop
- Build set randomizer (8 random advanced units + base set)
- Build JSONL position exporter
- **Checkpoint**: First complete self-play game runs end-to-end

### Phase 5: Validation (1-2 sessions)
- Replay validation against 2,127 Master Bot replays (target: >90% pass rate)
- Fix issues found by replay validation
- Run 100 self-play games, verify data format compatibility
- **Checkpoint**: High replay pass rate, clean training data

### Phase 6: Cloud Deployment (1 session)
- Package as self-contained Node.js app
- Cloud launcher script (Linux instances, S3 upload)
- Python vectorizer adaptation for JSONL → binary shards
- **Checkpoint**: Generating faithful training data on cloud

## Transpilation Conventions

- **ES2020+ JavaScript**, CommonJS modules (`require`/`module.exports`)
- **No TypeScript, no bundler** — correctness over elegance
- `flash.utils.Dictionary` → `Map` or plain object
- `Vector.<T>` → regular JavaScript `Array`
- `state.dispatch(update, animate, event)` → no-op (no UI)
- `MCDSEvent` → no-op
- Preserve AS3 class/method/variable names wherever possible
- Each AS3 file → one JS file in `js_engine/`

## Validation Strategy

1. **Mana round-trip**: Parse + serialize all 161 units' buyCost from cardLibrary.jso
2. **State.toString() parity**: Init state from test data, compare JSON output field-by-field
3. **Replay validation**: Run 2,127 Master Bot replays through JS engine; every click must be legal, game result must match
4. **MCDSAI smoke test**: Complete self-play games that reach conclusion within 200 turns
5. **Feature extraction cross-check**: Compare Python-vectorized features from JS state vs C++ `extractFeatures()` on same position

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

Python post-processing converts to binary shards (reuses existing `vectorize.py` + `load_selfplay.py` format).

## Key Files

| File | Purpose |
|---|---|
| `prismata_decompiled/scripts/mcds/engine/State.as` | Ground truth game engine (4,490 LOC) |
| `prismata_decompiled/scripts/mcds/engine/Controller.as` | Click processing (2,574 LOC) |
| `prismata_decompiled/scripts/mcds/engine/StateUtil.as` | MCDSAI ↔ engine bridge (156 LOC) |
| `prismata_decompiled/scripts/AI/AIThreadHandler.as` | MCDSAI protocol reference |
| `tmp_browser_client/MCDSAI3441.js` | Official Lunarch AI module |
| `tmp_browser_client/AIworker3441.js` | Worker wrapper (shows cwrap interface) |
| `tmp_swf_extract/148_*.bin` | AI parameters (full, JSON text) |
| `tmp_swf_extract/93_*.bin` | AI parameters (short, post-turn-16) |
| `bin/asset/config/cardLibrary.jso` | Unit definitions (161 units) |
| `training/data/unit_index.json` | Canonical unit index for features |
| `training/vectorize.py` | Python feature extraction (reuse for JSONL→shards) |
| `training/schema.json` | Feature schema (1785-dim) |
