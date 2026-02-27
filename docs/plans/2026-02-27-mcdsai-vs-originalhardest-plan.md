# MCDSAI vs OriginalHardestAI Matchup — Implementation Plan

**Goal:** Build a Node.js orchestrator that plays Lunarch's MCDSAI (Master Bot AI, `MCDSAI3441.js`) against our C++ OriginalHardestAI, using the JS engine as the game arbiter (correct AS3 rules). Measure relative win rates to establish a strength baseline.

**Estimated effort:** 4-6 hours implementation, 8-16 hours for 100-game benchmark run.

## Architecture

```
                    matchup_main.js (orchestrator)
                   /                              \
          MCDSAI Worker                    CppSuggestWorker
        (existing infra)                   (new — Phase 2)
              |                                   |
     mcdsai_worker.js                  Prismata_Testing.exe
     (child_process.fork)              --suggest temp.json
              |                        (child_process.spawn)
        MCDSAI3441.js                         |
        (Emscripten)                    stdout → JSON
              |                                |
              +--------- JS Engine -----------+
                    (game state arbiter)
                    State.js + Analyzer
```

**Key principle:** The JS engine manages all game state using correct AS3 rules. Neither AI controls game logic — they just receive a state and return moves (clicks). This ensures fair comparison on identical game states.

## Phase 1: State Format Adapter + Verification

### What to implement

Create `stateToSuggestJSON(state, mergedDeck)` function that produces JSON compatible with C++ `--suggest` mode.

**File:** `js_engine/suggest_adapter.js` (new, ~60 lines)

The function combines:
1. `replay_exporter.stateToCppJSON(state)` — base state (already ~90% compatible)
2. `instId` added to each table entry (missing from `instToCardJSON`)
3. `mergedDeck` array added at root level (required for CardType initialization)
4. Wrapped in `CurrentInfo` envelope (F6 format that `--suggest` expects)

**Output format:**
```json
{
  "CurrentInfo": {
    "mergedDeck": [ /* card definitions from JS mergedDeck */ ],
    "gameState": {
      "whiteMana": "8G",
      "blackMana": "7G",
      "turn": 0,
      "numTurns": 1,
      "phase": "action",
      "cards": ["Drone", "Engineer", "Tarsier", ...],
      "whiteTotalSupply": [20, 20, 4, ...],
      "blackTotalSupply": [20, 20, 4, ...],
      "whiteSupplySpent": [1, 0, 0, ...],
      "blackSupplySpent": [0, 0, 0, ...],
      "table": [
        {
          "cardName": "Drone",
          "instId": 10,
          "owner": 0,
          "health": 1,
          "role": "default",
          "deadness": "alive",
          "constructionTime": 0,
          "charge": 0,
          "delay": 0,
          "lifespan": -1,
          "disruptDamage": 0,
          "blocking": false
        }
      ]
    }
  }
}
```

### Documentation references

- `js_engine/replay_exporter.js:40-113` — `instToCardJSON()` and `stateToCppJSON()` (base format, copy and extend)
- `source/engine/Card.cpp:20-169` — C++ Card constructor JSON field expectations
- `source/engine/GameState.cpp:12-188` — `initFromJSON()` field expectations
- `source/testing/Benchmarks.cpp:835-838` — `CurrentInfo` unwrapping logic

### Key details

- **Name convention:** Use display names throughout (UIName). Both `stateToCppJSON` and F6 format use display names. C++ `--suggest` was built for F6 and handles display names.
- **instId is critical:** Without it, C++ returns `_id=-1` for inst clicks, breaking click application. Add `instId: inst.instId` to each table entry.
- **mergedDeck format:** The JS `buildMergedDeck()` output from `card_library.js` should be passable directly. C++ `CardTypeData.cpp:106-127` parses entries looking for `name`, `buyCost`, `buildTime`, `health`, etc. — the JS entries have these fields.
- **Only alive units in table:** `stateToCppJSON` already filters `deadness === ALIVE`. This matches F6 behavior.

### Verification checklist

1. Run 1 game via `selfplay_main.js --games 1`, capture state after turn 3
2. Export via `stateToSuggestJSON()`, write to temp file
3. Run `Prismata_Testing.exe --suggest temp.json --player OriginalHardestAI`
4. Verify output has `"ok": true` and non-empty `clicks` array
5. Verify click `_id` values correspond to valid mergedDeck indices / instIds

### Anti-pattern guards

- Do NOT use `State.toString()` directly — it uses internal names for `cards` array (line 1646 uses `state.cards[i].name` which may be internal). Use `stateToCppJSON` which explicitly maps to `UIName`.
- Do NOT omit `mergedDeck` — without it, C++ can't initialize CardTypes and all name lookups fail.
- Do NOT use `inst.toObject()` directly for table entries — it uses `inst.card.cardName` (internal name at Inst.js:294). Use `inst.card.UIName` (display name) as `instToCardJSON` does.

## Phase 2: C++ Suggest Worker

### What to implement

Create `CppSuggestWorker` class that wraps `Prismata_Testing.exe --suggest` as a per-turn subprocess.

**File:** `js_engine/cpp_suggest_worker.js` (new, ~120 lines)

**Interface (mirrors MCDSAIWorker):**
```javascript
class CppSuggestWorker {
    constructor(options = {}) {
        this.exePath = options.exePath || '../bin/Prismata_Testing.exe';
        this.playerName = options.playerName || 'OriginalHardestAI';
        this.thinkTime = options.thinkTime || 7000;
        this.label = options.label || 'C++';
    }

    async spawn() { /* no-op — stateless per-turn */ }

    async initializeAI(initJson) {
        /* Store mergedDeck from initJson for later state exports */
        this.mergedDeck = JSON.parse(initJson).mergedDeck;
    }

    async getAIMove(state, mergedDeck) {
        /* 1. Build suggest JSON via stateToSuggestJSON(state, mergedDeck)
           2. Write to temp file (os.tmpdir() + random name)
           3. Spawn: Prismata_Testing.exe --suggest temp.json --player X --think-time Y
           4. Capture stdout, parse JSON
           5. Clean up temp file
           6. Return response in MCDSAI-compatible format */
    }

    terminate() { /* no-op */ }
}
```

**Per-turn flow:**
```
1. stateToSuggestJSON(analyzerState, mergedDeck) → JSON string
2. Write to temp file (e.g., /tmp/suggest_turn_17.json)
3. child_process.spawnSync('Prismata_Testing.exe', ['--suggest', tempFile, ...])
   OR child_process.execFile (async) with timeout
4. Parse stdout JSON: { ok, clicks, eval, think_ms, ... }
5. Convert to MCDSAI-compatible response: { aiclicks, aithinktime, airesign }
6. Delete temp file
```

### Documentation references

- `source/testing/main.cpp:150-153` — CLI argument parsing for --suggest
- `source/testing/Benchmarks.cpp:809-1044` — DoSuggest implementation
- `js_engine/mcdsai_manager.js:31-71` — MCDSAIWorker interface pattern to follow

### Key details

- **Process overhead:** ~200-300ms per turn (process spawn + neural weight load + JSON parsing). At 7s think time this is ~4% overhead. Acceptable for benchmarking.
- **Temp file cleanup:** Always delete temp file in finally block to prevent accumulation.
- **Timeout:** Set `execFile` timeout to `thinkTime + 10000ms` (generous buffer for init overhead).
- **Error handling:** If `ok: false` in response, log error and return `{aiclicks: [], airesign: false}`. The orchestrator handles 0-click responses as AI failure (existing logic from selfplay_main.js).
- **Stderr suppression:** --suggest redirects init noise to stderr. Only stdout contains the JSON response.

### Verification checklist

1. CppSuggestWorker can be instantiated and `spawn()` called (no-op)
2. `initializeAI()` stores mergedDeck correctly
3. `getAIMove()` writes valid temp file, spawns exe, parses response
4. Response contains `aiclicks` array with valid click objects
5. Temp files are cleaned up after each call
6. Timeout triggers if exe hangs (test with --think-time 60000)

### Anti-pattern guards

- Do NOT use `spawnSync` for the exe — it blocks the Node.js event loop. Use `execFile` with callback or promisified version.
- Do NOT forget to quote the temp file path (may contain spaces on Windows).
- Do NOT assume exe is in PATH — use explicit path relative to project root.

## Phase 3: Click Converter

### What to implement

Create `suggestClicksToClicks(suggestClicks, gameState)` function that converts C++ --suggest click format to JS engine Click objects.

**File:** `js_engine/suggest_adapter.js` (add to same file as Phase 1, ~40 lines)

**C++ --suggest click format:**
```json
[
  { "_type": "card clicked", "_id": 0 },
  { "_type": "inst clicked", "_id": 42 },
  { "_type": "space clicked", "_id": -1 },
  { "_type": "end swipe processed", "_id": 42 }
]
```

**Conversion logic:**
```javascript
function suggestClicksToClicks(suggestClicks) {
    return suggestClicks
        .filter(c => c._type !== 'end swipe processed')  // Skip swipe animations
        .map(c => {
            // Map --suggest _type strings to JS engine C.CLICK_* constants
            let clickType;
            switch (c._type) {
                case 'card clicked':       clickType = C.CLICK_CARD; break;
                case 'card shift clicked': clickType = C.CLICK_CARD_SHIFT; break;
                case 'inst clicked':       clickType = C.CLICK_INST; break;
                case 'inst shift clicked': clickType = C.CLICK_INST_SHIFT; break;
                case 'space clicked':      clickType = C.CLICK_SPACE; break;
                default: throw new Error(`Unknown click type: ${c._type}`);
            }
            return new Click(clickType, c._id);
        });
}
```

### Documentation references

- `source/testing/Benchmarks.cpp:948-1018` — Click array generation (BUY=mergedDeck index, INST=instId)
- `js_engine/Click.js:8-19` — Click constructor (`_type`, `_id`, `_params`)
- `js_engine/C.js:14-27` — Click type constants
- `js_engine/StateUtil.js:24-75` — MCDSAI click conversion (reference for patterns, NOT to copy — different format)

### Key details

- **ID mapping is direct:** C++ `_id` for `card clicked` = mergedDeck index = JS `cardId`. C++ `_id` for `inst clicked` = client instId = JS `instId`. No name resolution needed.
- **end swipe processed:** This is a GUI animation hint, not a game action. Filter it out. The JS engine handles defense-phase transitions internally.
- **Auto-inserted END_PHASE:** --suggest inserts `space clicked` between action phases and at turn end (mirrors `Move::toClientString()` logic). The JS engine's click processing handles these transitions.
- **No validation needed:** The clicks come from our own AI — if they're illegal, that's a bug to investigate, not silently swallow.

### Verification checklist

1. `card clicked` with `_id: 0` → `Click(CLICK_CARD, 0)` — verify card at index 0 matches expected
2. `inst clicked` with `_id: 42` → `Click(CLICK_INST, 42)` — verify instance 42 exists in state
3. `space clicked` → `Click(CLICK_SPACE, -1)` — verify phase transition
4. `end swipe processed` entries are filtered out
5. Full click sequence from --suggest can be applied to JS state without errors

### Anti-pattern guards

- Do NOT use `StateUtil.convertToClicks()` for C++ clicks — that function does name-based instance lookup (for MCDSAI format). C++ clicks are already ID-based.
- Do NOT blindly apply all clicks if one fails — log the failure with full context for debugging.

## Phase 4: matchup_main.js Orchestrator

### What to implement

Create `matchup_main.js` — the main orchestrator script for MCDSAI vs C++ AI matchups.

**File:** `js_engine/matchup_main.js` (new, ~300 lines — based on `selfplay_main.js`)

**Copy from `selfplay_main.js`:**
- Module imports and initialization (lines 1-30)
- `playGame()` function structure (lines 119-280) — main game loop
- Card library + mergedDeck + AI params loading
- Game state initialization
- Turn loop with click application
- Stagnation detection
- Result tracking and summary output

**Modify:**
- Replace one MCDSAIWorker with CppSuggestWorker
- Game loop: on C++ player's turn, call CppSuggestWorker.getAIMove() instead of MCDSAIWorker.getAIMove()
- Click application: on C++ player's turn, use suggestClicksToClicks() instead of StateUtil.convertToClicks()
- Training data generation: OPTIONAL (could skip for pure benchmarking, add later)

**CLI interface:**
```
node matchup_main.js [options]
  --games N          Number of games to play (default: 10)
  --think-time MS    C++ AI think time in ms (default: 7000)
  --mcdsai-color W|B Which color MCDSAI plays (default: alternate)
  --player NAME      C++ player name (default: OriginalHardestAI)
  --exe PATH         Path to Prismata_Testing.exe
  --jsonl FILE       Output training data (optional)
  --verbose          Per-turn logging
```

**Per-game flow (pseudocode):**
```javascript
async function playGame(gameId, mcdsaiColor, mergedDeck, ...) {
    // 1. Build deck (same as selfplay_main.js)
    const activeDeck = mergedDeck.filter(c => !c._inactive);
    const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);

    // 2. Initialize both players
    const initJson = JSON.stringify({ mergedDeck: initDeck, aiParameters: initParams });
    await mcdsaiWorker.initializeAI(initJson);
    cppWorker.initializeAI(initJson);  // Just stores mergedDeck

    // 3. Create fresh game state
    const analyzer = Analyzer.analyzerFromDeck(initDeck);

    // 4. Turn loop
    while (!analyzer.gameState.finished && turnCount < 400) {
        const activePlayer = analyzer.gameState.turn;
        const isMcdsaiTurn = (activePlayer === mcdsaiColor);

        if (isMcdsaiTurn) {
            // MCDSAI path (existing code from selfplay_main.js)
            const stateStr = analyzer.gameState.toString();
            const moveJson = JSON.stringify({ gameState: JSON.parse(stateStr), aiPlayerName: 'HardestAI' });
            const response = await mcdsaiWorker.getAIMove(moveJson);
            const clicks = StateUtil.convertToClicks(response.aiclicks, analyzer.gameState, false);
            for (const click of clicks) {
                analyzer.recordClick(false, false, click._type, click._id, click._params);
            }
        } else {
            // C++ --suggest path (new)
            const response = await cppWorker.getAIMove(analyzer.gameState, initDeck);
            const clicks = suggestClicksToClicks(response.clicks);
            for (const click of clicks) {
                analyzer.recordClick(false, false, click._type, click._id, click._params);
            }
        }

        // Stagnation check (same as selfplay_main.js)
    }

    return { result, turns, ... };
}
```

**Results summary output:**
```
=== MCDSAI vs OriginalHardestAI ===
Games: 100
MCDSAI wins: 62 (62.0%)
C++ wins: 35 (35.0%)
Draws: 3 (3.0%)
Avg game length: 34.2 turns
Avg MCDSAI think: 6,847ms
Avg C++ think: 7,123ms
Wilson 95% CI: [52.0%, 71.2%]
```

### Documentation references

- `js_engine/selfplay_main.js:119-280` — `playGame()` to copy and modify
- `js_engine/selfplay_main.js:347-420` — Main function structure (argument parsing, worker setup, game loop)
- `js_engine/mcdsai_manager.js` — MCDSAIWorker interface
- `js_engine/StateUtil.js:24-75` — MCDSAI click conversion (keep for MCDSAI turns)

### Key details

- **Color alternation:** Default behavior alternates MCDSAI between White and Black each game. `--mcdsai-color W` forces MCDSAI to always play White (P0). Important for measuring first-player advantage.
- **Both AIs use same mergedDeck and params:** Ensures identical game setup. MCDSAI gets full AI params (with HardestAI config). C++ gets state + mergedDeck (uses its own config.txt for player definitions).
- **MCDSAI always uses HardestAI difficulty:** Hardcoded `aiPlayerName: 'HardestAI'` in move request (same as selfplay_main.js).
- **C++ player name from config.txt:** The `--player` CLI arg maps to a player definition in `bin/asset/config/config.txt`. `OriginalHardestAI` uses playout eval with 7s think time (legacy behavior).
- **No training data by default:** Skip `stateToTrainingExample()` unless `--jsonl` is specified. Simplifies the initial implementation.
- **Game retry on AI failure:** If either AI returns 0 clicks or crashes, log the failure and start a new game (don't count it). Track failure count separately.

### Verification checklist

1. Both workers initialize without errors
2. MCDSAI turns work identically to selfplay_main.js
3. C++ turns return valid clicks that advance the game state
4. Color alternation works (MCDSAI plays White in game 1, Black in game 2)
5. Results summary is accurate (wins + losses + draws = total games)
6. 5-game smoke test completes without crashes
7. AI failures are logged and retried

### Anti-pattern guards

- Do NOT modify selfplay_main.js — create a new file. selfplay_main.js is production code for data generation.
- Do NOT share state between games — create fresh Analyzer per game.
- Do NOT assume identical think times — log actual think times for both sides.
- Do NOT count failed/crashed games in win rate — track separately.

## Phase 5: Test & Benchmark

### Smoke test (5 games)
```bash
cd js_engine
node matchup_main.js --games 5 --think-time 1000 --verbose 2> matchup_log.txt
```
- Should complete in ~5 minutes (1s think × ~37 turns × 5 games, both sides)
- Check: all 5 games complete, no crashes, results printed
- Check: both AIs make reasonable moves (not all pass/resign)

### Benchmark (100 games)
```bash
cd js_engine
node matchup_main.js --games 100 --think-time 7000 2> matchup_benchmark.txt
```
- Estimated time: 8-16 hours (7s × ~37 turns × 2 sides × 100 games ÷ ~parallel potential)
- Actually sequential: ~7s per half-turn × ~74 half-turns × 100 = ~51,800s ≈ **14.4 hours**
- Run overnight. Can start with `--games 20` for quicker signal (~3 hours)

### What we expect to learn

1. **MCDSAI vs OriginalHardestAI relative strength** — If MCDSAI dominates (>70% WR), then our 51.9% WR against OriginalHardestAI (even if valid) would mean very little. If they're close (45-55%), then OriginalHardestAI is a reasonable proxy for Master Bot difficulty.

2. **Think time fairness** — Both AIs should use comparable think times. MCDSAI defaults to 7s. Our C++ AI can be configured to match.

3. **Game quality** — Do games look reasonable? Are there draw/stagnation issues? This validates the JS engine as a fair arbiter.

### Results analysis

After benchmark completes:
```bash
# Parse results
node -e "
const fs = require('fs');
const log = fs.readFileSync('matchup_benchmark.txt', 'utf8');
// ... parse and compute Wilson CI
"
```

Or use existing `tools/analyze_tournament.py` if results are in compatible format.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| State format incompatibility | Medium | Blocks Phase 2+ | Phase 1 verification test catches this early |
| C++ process spawn too slow | Low | Slow benchmark | Acceptable for benchmarking; optimize later with stdin pipe mode |
| instId mismatch between JS/C++ | Low | Broken click application | Phase 1 verification confirms round-trip |
| MCDSAI AI exceptions on some card sets | Known (~5%) | Failed games | Retry logic (existing from selfplay_main.js) |
| C++ exe not built / wrong config | Low | Crashes | Pre-flight check in matchup_main.js |

## Future optimizations (not in scope)

- **stdin pipe mode for C++:** Add `--suggest-loop` mode that reads multiple states from stdin. Eliminates process spawn + weight load overhead. Would be ~10ms per turn instead of ~300ms.
- **Parallel games:** Run multiple games concurrently (limited by CPU for think time). Would reduce benchmark wall time.
- **Neural net model as C++ player:** Test our trained neural model against MCDSAI (the real goal after benchmarking).
- **Training data generation:** Add `--jsonl` output to generate training data from mixed MCDSAI/C++ games.
