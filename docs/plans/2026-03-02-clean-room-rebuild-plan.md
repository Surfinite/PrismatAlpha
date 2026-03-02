# Clean Room Rebuild — Detailed Implementation Plan

## Context

Accumulated bugs from incremental fixes (supply=20 for all units, color-specific deadlocks, undefined property crashes) have eroded confidence. Rather than debug forward, we start from known-good baselines: Churchill's untouched `origin/master` for C++ and commit `99d39fe` for JS engine (100% replay validation on 500 replays).

**Principle: C++ = AI brain, JS = game truth.** The JS engine (transpiled from AS3 ground truth) handles all game state. The C++ engine just evaluates positions for AI search.

## Decisions

- **Git:** New branch `clean-baseline` from `origin/master`
- **C++ baseline:** Churchill's `origin/master` — NO engine audit fixes, heuristic changes, or GUI mods
- **JS baseline:** Commit `99d39fe` (validated transpilation)
- **MCDSAI:** Fresh from play.prismata.net
- **Units:** 105 additional units from live game screenshots (authoritative)
- **Scope:** Engine + AI + training pipeline + cloud scripts. Skip dashboard, sniffer, commentary.
- **Reference:** Prismata install at `C:\Program Files (x86)\Steam\steamapps\common\Prismata`

## Phase 0: Documentation & API Reference

### Verified APIs on origin/master (DO NOT invent others)

**EvaluationMethods enum** (`source/engine/Constants.h:34`):
```
{ Playout, WillScore, WillScoreInflation, Size }
```
Must add: `NeuralNet, NeuralNetPlusPlayout` before `Size`.

**Eval namespace** (`source/ai/Eval.h`):
```cpp
PlayerID PerformPlayout(const GameState&, const PlayerPtr&, const PlayerPtr&);
double ABPlayoutScore(const GameState&, const PlayerPtr&, const PlayerPtr&, PlayerID);
double WillScoreEvaluation(const GameState&, PlayerID);
double WillScoreInflationEvaluation(const GameState&, PlayerID);
```
Must add: `double NeuralNetEvaluation(const GameState&, PlayerID);`

**Player base** (`source/engine/Player.h`): `virtual void getMove(const GameState&, Move&)`

**Benchmarks namespace** (`source/testing/Benchmarks.h`): Only has `DoBenchmarks`, `DoTournamentBenchmark`, `DoPlayerBenchmark`, `DoChillIteratorBenchmarkJSON`. Must add `DoSuggest`.

**InitFromMergedDeckJSON** — EXISTS on origin/master (`source/engine/Prismata.cpp:23`). Safe to use.

**PlatformToolset** on origin/master: `v142` (VS 2019). Must update to `v145` (VS 2025) or `v143` (VS 2022) for our environment.

### Anti-patterns to avoid
- Do NOT add stagnation system (Constants.h Stagnation namespace, GameState m_noProgress)
- Do NOT add Heuristics.cpp improved values or legacy flag routing
- Do NOT add GUI watch training mode
- Do NOT use `debugStateHash()` (depends on stagnation infrastructure)
- Do NOT bring Card.cpp instId changes UNLESS --suggest explicitly needs them (it does — see Layer 3)

---

## Phase 1: Branch Setup + Infrastructure (Layer 0)
**Session 1 — mechanical copy, no code changes**

### Tasks
1. `git checkout -b clean-baseline origin/master`
2. Update PlatformToolset in all vcxproj files: `v142` → `v143` (or `v145`)
3. Verify build: `MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86`
4. Copy from current master (non-code only):
   - `git show master:CLAUDE.md > CLAUDE.md`
   - `git checkout master -- docs/ training/ aws/ gcp/ azure/ .gitignore`
   - `git checkout master -- .clang-format .github/`
5. Commit: "Layer 0: Branch setup + infrastructure from master"

### Verification
- [ ] MSBuild compiles clean (all 5 projects)
- [ ] `bin/Prismata_Testing.exe` runs (default tournament)
- [ ] No training/, js_engine/, or other code dirs affect the build

### Files modified
- `visualstudio/*.vcxproj` (PlatformToolset only)
- No C++ source changes

---

## Phase 2: Neural Net + Eval Integration (Layers 1-2)
**Session 2 — additive C++ files + minimal modifications**

### Layer 1: New files
1. Copy `source/ai/NeuralNet.h` (94 lines) from master — entire file is new
2. Copy `source/ai/NeuralNet.cpp` (782 lines) from master — entire file is new
3. Copy `bin/asset/config/neural_weights.bin` from master
4. Add to `visualstudio/Prismata_AI.vcxproj`:
   - `<ClCompile Include="..\source\ai\NeuralNet.cpp" />`
   - `<ClInclude Include="..\source\ai\NeuralNet.h" />`

### Layer 2: Search integration
5. Edit `source/engine/Constants.h` line 34:
   ```
   OLD: enum { Playout, WillScore, WillScoreInflation, Size };
   NEW: enum { Playout, WillScore, WillScoreInflation, NeuralNet, NeuralNetPlusPlayout, Size };
   ```
   **DO NOT add Stagnation namespace or ProgressEvent enum.**

6. Edit `source/ai/Eval.h` — add declaration:
   ```cpp
   double NeuralNetEvaluation(const GameState & state, const PlayerID maxPlayer);
   ```

7. Edit `source/ai/Eval.cpp` — add implementation (12 lines):
   ```cpp
   double NeuralNetEvaluation(const GameState & state, const PlayerID maxPlayer)
   {
       if (!NeuralNet::Instance().isLoaded()) return WillScoreEvaluation(state, maxPlayer);
       return NeuralNet::Instance().evaluateValue(state, maxPlayer) * 100.0;
   }
   ```
   Plus `#include "NeuralNet.h"`.

8. Edit `source/ai/AlphaBetaSearch.cpp` — add NeuralNet cases to `eval()`:
   - `#include "NeuralNet.h"`
   - Case `EvaluationMethods::NeuralNet`: return `Eval::NeuralNetEvaluation()`
   - Case `EvaluationMethods::NeuralNetPlusPlayout`: blend formula

9. Edit `source/ai/StackAlphaBetaSearch.cpp` — identical pattern to #8

10. Edit `source/ai/UCTSearch.cpp` — PUCT selection + neural eval in traverse():
    - `#include "NeuralNet.h"`
    - PUCT node selection formula in `UCTNodeSelect()`
    - `computeRootPriors()` method
    - `traverse()` return type change (PlayerID → double) + NeuralNet eval path
    - `getBestRootWinRate()` method

11. Edit `source/ai/UCTSearch.h` — updated signatures

12. Edit `source/ai/UCTSearchParameters.hpp` — add `_blendWeight`, `_usePUCT`, `deepClone()`

13. Edit `source/ai/AlphaBetaSearchParameters.hpp` — add `_blendWeight`, `deepClone()`

14. Edit `source/ai/UCTNode.h/cpp` — add `_policyPrior` member + accessors

15. Edit `source/ai/UCTSearchResults.hpp` — add `rootDiagnostics`

16. Edit `source/ai/AIParameters.cpp` — add parsing for:
    - NeuralNet/NeuralNetPlusPlayout eval methods in UCT and StackAlphaBeta player sections
    - BlendWeight, UsePUCT parameters
    - `playersHaveSameConfig()` for SkipColorSwap
    - **DO NOT add** `legacy` flag routing for GreedyKnapsack/TechHeuristic/Breach

17. Edit `source/ai/AIParameters.h` — `_rootValue` type change, `playersHaveSameConfig()` declaration

18. Edit Player_AlphaBeta.h, Player_StackAlphaBeta.h, Player_UCT.h/cpp — deepClone in clone()

19. Edit `bin/asset/config/config.txt` — add:
    - LiveHardestAI player definitions (from SWF extraction)
    - Neural eval player definitions (PrismatAI_UCT, PrismatAI_AB, etc.)
    - LiveHardestAI opening books, filters, partial players
    - **Keep** OriginalHardestAI as a named copy of the original HardestAI config

20. Commit: "Layer 1-2: Neural net inference + AI config integration"

### Verification
- [ ] MSBuild compiles clean
- [ ] `bin/Prismata_Testing.exe` runs default tournament (non-neural)
- [ ] Config parses LiveHardestAI and neural players without errors
- [ ] Neural weights load (check stderr for "loaded 26 tensors" or similar)

### Source references (copy from master)
- NeuralNet.h: `git show master:source/ai/NeuralNet.h`
- NeuralNet.cpp: `git show master:source/ai/NeuralNet.cpp`
- All diffs: `git diff origin/master master -- source/ai/`
- Config: `git show master:bin/asset/config/config.txt`

---

## Phase 3: --suggest CLI Mode (Layer 3)
**Session 3 — Benchmarks.cpp + main.cpp changes**

### Tasks
1. Edit `source/testing/main.cpp` — rewrite to add:
   - CLI argument parsing (--suggest, --player, --think-time)
   - Stdout redirect to stderr during init (`_dup`/`_dup2`)
   - NeuralNet weight loading at startup
   - PID-based random seeding: `srand((unsigned int)(time(NULL) ^ (GETPID() << 4)))`

2. Edit `source/testing/Benchmarks.h` — add:
   ```cpp
   void DoSuggest(const std::string & stateFile, const std::string & playerName, int thinkTimeMs);
   ```

3. Edit `source/testing/Benchmarks.cpp` — add DoSuggest (lines 740-1077 from master):
   - Helper functions: `jsonEscape`, `jsonStringArray`, `phaseToString`, `suggestError`, `appendClick`
   - DoSuggest main function
   - **MODIFICATION:** Remove `state_hash` from JSON output (depends on `debugStateHash()` which needs stagnation infrastructure)
   - **MODIFICATION:** Remove shift-click expansion code (the buggy part) — output raw actions, let JS engine handle expansion
   - Add necessary includes: `NeuralNet.h`, `Player_StackAlphaBeta.h`, `Player_UCT.h`, `<fstream>`, etc.

4. Edit `source/engine/Card.h` — add `int m_clientInstId = -1;` + `int getClientInstId() const;`
   (Required because DoSuggest uses `card.getClientInstId()` for click _id)

5. Edit `source/engine/Card.cpp` — parse `instId` from JSON + getter implementation

6. Edit `source/engine/GameState.h` — add `debugStateHash()` declaration
   **WAIT:** We decided NOT to do this. Instead, remove state_hash from DoSuggest output.

7. Commit: "Layer 3: --suggest CLI mode for AI move generation"

### Verification
- [ ] MSBuild compiles clean
- [ ] Prepare a test state JSON (F6 format or bare format)
- [ ] `bin/Prismata_Testing.exe --suggest test_state.json` produces valid JSON to stdout
- [ ] JSON contains: ok, eval, eval_pct, active_player, phase, clicks array
- [ ] JSON does NOT contain state_hash

### Anti-patterns
- Do NOT add DoReplay, DoReplayBatch, DoEval, DoAnalyze, DoDumpStates (not needed for baseline)
- Do NOT add SelfPlayDataSink or ReplayStepper includes
- Do NOT add shift-click expansion to DoSuggest (source of bugs — rewrite fresh in Layer 7 if needed)

---

## Phase 4: Card Library — 105 Units (Layer 4)
**Session 4 — cardLibrary.jso verification**

### Tasks
1. Read current `bin/asset/config/cardLibrary.jso` from master
2. Read origin/master's `cardLibrary.jso` to see what Churchill had
3. Diff the two — identify exactly which units were added
4. Cross-reference every UIName against the 105 live game screenshots:
   - Aegis through Zemora Voidbringer (alphabetical)
5. For each unit: verify internal name, display name, rarity, costs, abilities
6. Also reference card data from Prismata install: `C:\Program Files (x86)\Steam\steamapps\common\Prismata`
7. Write the clean cardLibrary.jso with ONLY:
   - Base set units (Drone, Engineer, Conduit, Blastforge, Animus, Wall, Forcefield, Tarsier, Rhino, Steelsplitter, Gauss Cannon)
   - 105 additional units from screenshots
   - Unbuyable tokens referenced by active cards' scripts (Behemoth, Transwall, Fusion, etc.)
   - NO unreleased/beta units
8. Commit: "Layer 4: Card library with 105 verified additional units"

### Verification
- [ ] Count UINames: exactly 105 additional + ~11 base + unbuyable tokens
- [ ] Every UIName matches a unit in the live game screenshots
- [ ] No unreleased/beta units present
- [ ] Tournament still runs with expanded library
- [ ] `grep -c "UIName" bin/asset/config/cardLibrary.jso` matches expected count

---

## Phase 5: JS Transpiled Engine (Layer 5)
**Session 5 — copy from validated commit**

### Tasks
1. Extract entire js_engine/ from validated commit:
   ```bash
   git archive 99d39fe -- js_engine/ | tar -x
   ```

2. Verify all 32 files present (18 core + 3 data/config + 4 MCDSAI + 5 test + 1 validator + 1 package.json)

3. Verify external dependencies exist:
   - `bin/asset/config/cardLibrary.jso` (from Phase 4)
   - `tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin` (SWF AI params)
   - `tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin` (SWF AI params)

4. Run test suite:
   ```bash
   cd js_engine && node test_state.js && node test_tier1.js && node test_tier2.js
   ```

5. Run replay validation:
   ```bash
   cd js_engine && node replay_validator.js --count 500
   ```

6. Commit: "Layer 5: Validated JS transpiled engine from 99d39fe"

### Verification
- [ ] All test files pass
- [ ] Replay validation: 100% pass on 500 replays (matching original validation)
- [ ] No files from post-99d39fe commits present (no suggest_adapter.js, no matchup_main.js)

### External file check
| File | Source | Required by |
|------|--------|-------------|
| `bin/asset/config/cardLibrary.jso` | Phase 4 | card_library.js |
| `tmp_swf_extract/148_*.bin` | Already on disk (SWF extract) | ai_params.js |
| `tmp_swf_extract/93_*.bin` | Already on disk (SWF extract) | ai_params.js |

---

## Phase 6: MCDSAI Binary (Layer 6)
**Session 5 (continued) or Session 6**

### Tasks
1. Download fresh MCDSAI binary from play.prismata.net
   - This is `MCDSAI3441.js` — an Emscripten-compiled C++ AI
   - Currently at `tmp_browser_client/MCDSAI3441.js`
   - SHA256 hash is pinned in `mcdsai_wrapper.js` (`EXPECTED_HASH`)

2. Verify the binary:
   ```bash
   node -e "const m = require('./js_engine/mcdsai_wrapper.js'); m.loadMCDSAI()"
   ```

3. Test MCDSAI worker lifecycle:
   ```bash
   node js_engine/test_selfplay.js
   ```

4. Commit: "Layer 6: Fresh MCDSAI binary"

### Verification
- [ ] MCDSAI process starts without errors
- [ ] `test_selfplay.js` passes (single game completes)
- [ ] SHA256 of binary matches pinned hash in mcdsai_wrapper.js

---

## Phase 7: Matchup Integration — REWRITE (Layer 7)
**Session 7+ — careful incremental development**

This is the layer that was the SOURCE of accumulated bugs. Build from scratch with verification at each step.

### Sub-phase 7a: Single Turn
Write minimal `matchup_v2.js` that:
1. Initializes a game (JS engine) with a fixed card set
2. Exports current state to JSON (for C++ --suggest)
3. Calls `Prismata_Testing.exe --suggest state.json --player HardestAI --think-time 3000`
4. Parses the JSON response
5. Applies clicks to JS engine one at a time via `analyzer.recordClick()`
6. Verifies: turn number incremented, resources changed, units built

**Verification:** Print before/after state. Manually inspect that the AI move makes sense.

### Sub-phase 7b: Single Game
Extend to loop both players' turns:
1. Alternate: Player 0 turn → Player 1 turn
2. Check `state.gameover` after each turn
3. Record winner, turn count
4. Handle: AI errors (retry? skip?), stuck detection (N turns no change), game-over conditions

**Verification:** Run 1 game to completion. Check winner, turn count, final state.

### Sub-phase 7c: Multi-Game
1. Random card set generation (use `card_library.js.randomSet()`)
2. Loop N games, tally results
3. Save per-game results (winner, turns, card set, think time)
4. Supply must be correct: legendary=1, rare=4, normal/trinket=20

**Verification:**
- [ ] Run 10 games, all complete
- [ ] Supply values correct (grep output for supply counts)
- [ ] Win rate roughly plausible (not 100/0)

### Sub-phase 7d: MCDSAI Integration
1. Add MCDSAI as a player option (via mcdsai_manager.js)
2. MCDSAI plays via JS engine directly (clicks, not --suggest)
3. Test: MCDSAI vs HardestAI via --suggest

**Verification:** MCDSAI vs HardestAI matchup runs to completion.

### Sub-phase 7e: Parallel Workers
Only after single-threaded is rock solid:
1. Worker-based parallel games
2. Aggregate results
3. Replay saving

### Key learnings from previous bugs (DO NOT repeat)
- `card.supply` does NOT exist on mergedDeck entries — use `getSupply(card)` from card_library.js which maps rarity string → numeric value
- Do NOT check `card.supply !== undefined ? card.supply : 20` — this always defaults to 20
- Use `SUPPLY_BY_RARITY = { legendary:1, rare:4, normal:20, trinket:20 }` from card_library.js
- `_inactive` cards must be excluded from supply initialization
- Shift-click expansion is complex — consider having JS engine handle it rather than C++ DoSuggest
- End-turn requires TWO "space clicked" events (enter confirm + commit turn)
- MCDSAI response contains control chars — strip `[\x00-\x1f]` before JSON.parse
- Click.js uses `_type`, `_id` (underscore prefix), not `.type`, `.id`

---

## What We're NOT Bringing Back

| Excluded Change | Reason | Risk if included |
|--------|--------|---------|
| ALL GameState.cpp modifications (711 lines) | JS engine is ground truth | Stagnation/swoosh bugs |
| Card.cpp instId (partial — only what --suggest needs) | Minimal footprint | Over-engineering |
| Heuristics.cpp improved values | Experimental | Unknown side effects |
| PartialPlayer buy/breach changes | Experimental | Unknown side effects |
| GUI modifications (eval bar, graph, gold) | User excluded | Wasted effort |
| Old matchup/suggest/replay JS code | Source of bugs | Bug inheritance |
| Death script scaffolding | Incomplete | Compilation issues |
| Stagnation system | Decreased replay pass rate | 48.1% vs 50.4% |
| Dashboard, sniffer, commentary | Out of scope | Scope creep |
| debugStateHash() | Depends on stagnation | Missing deps |

---

## Execution Summary

| Phase | Layer | Session | Est. Effort | Key Risk |
|-------|-------|---------|-------------|----------|
| 1 | 0 | 1 | Low | PlatformToolset compatibility |
| 2 | 1-2 | 2 | Medium | UCTSearch.cpp is complex (218 lines) |
| 3 | 3 | 3 | Medium | DoSuggest cleanup (remove stale deps) |
| 4 | 4 | 4 | Medium | Unit name mapping accuracy |
| 5 | 5 | 5 | Low | Mechanical copy + validate |
| 6 | 6 | 5-6 | Low | MCDSAI binary availability |
| 7 | 7 | 7+ | High | Integration — where bugs lived before |
