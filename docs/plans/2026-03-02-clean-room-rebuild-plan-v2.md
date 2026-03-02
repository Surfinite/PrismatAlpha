# Clean Room Rebuild — Detailed Implementation Plan (v2)

<!-- This is the post-review revision. Changes from v1 are marked with CHANGED comments. -->

## Context

Accumulated bugs from incremental fixes (supply=20 for all units, color-specific deadlocks, undefined property crashes) have eroded confidence. Rather than debug forward, we start from known-good baselines: Churchill's untouched `origin/master` for C++ and commit `99d39fe` for JS engine (100% replay validation on 500 replays).

**Principle: C++ = AI brain, JS = game truth.** The JS engine (transpiled from AS3 ground truth) handles all game state. The C++ engine just evaluates positions for AI search.

## Decisions

- **Git:** New branch `clean-baseline` from `origin/master`
- **C++ baseline:** Churchill's `origin/master` — NO engine audit fixes, heuristic changes, or GUI mods
- **JS baseline:** Commit `99d39fe` (validated transpilation)
- **MCDSAI:** Use existing on-disk binary (hash-verified), fresh download optional <!-- CHANGED: Inverted primary/fallback — Reviewers 1-8 -->
- **Units:** 105 additional units from live game screenshots (authoritative)
- **Scope:** Engine + AI + training pipeline + cloud scripts. Skip dashboard, sniffer, commentary.
- **Reference:** Prismata install at `C:\Program Files (x86)\Steam\steamapps\common\Prismata`
- **Rollback:** Git tag after each phase (`phase-N-complete`) for bisection <!-- CHANGED: Added rollback strategy — Reviewers 1,4,5,6,8 -->

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

**PlatformToolset** on origin/master: `v142` (VS 2019). Update to `v145` (VS 2025, local) with `v143` (VS 2022) for CI runners. <!-- CHANGED: Specified exact versions — Reviewers 1,2,4,5,6,8 -->

### Anti-patterns to avoid
- Do NOT add stagnation system (Constants.h Stagnation namespace, GameState m_noProgress)
- Do NOT add Heuristics.cpp improved values or legacy flag routing
- Do NOT add legacy flag routing for GreedyKnapsack/TechHeuristic/Breach <!-- CHANGED: Added explicit mention — Reviewer 1 -->
- Do NOT add GUI watch training mode
- Do NOT use `debugStateHash()` (depends on stagnation infrastructure)
- Do NOT bring Card.cpp instId changes UNLESS --suggest explicitly needs them (it does — see Phase 3)

---

## Phase 0.5: Baseline Tournament Verification
<!-- APPLIED: Optional enhancement #1 — Reviewer 4 -->
**Before any modifications — document baseline behavior**

### Tasks
1. On `origin/master`, build and run a default tournament:
   ```bash
   cd bin && ./Prismata_Testing.exe
   ```
2. Record results: win rates, game count, any errors/warnings
3. Save output to `docs/baseline_tournament_results.txt`
4. Note eval/sec and approximate memory usage (Task Manager peak working set)

### Purpose
Provides a known-good reference point. If any later phase causes tournament results to diverge or performance to regress, this baseline enables comparison.

---

## Phase 1: Branch Setup + Infrastructure (Layer 0)
**Session 1 — mechanical copy, no code changes**

### Tasks
1. `git checkout -b clean-baseline origin/master`
2. Update PlatformToolset in all vcxproj files: `v142` → `v145` (use `v143` for CI builds via `/p:PlatformToolset=v143`)  <!-- CHANGED: Locked to v145 — Reviewers 1,2,4,5,6,8 -->
3. Verify build: `MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86`
4. Copy from current master (non-code only):
   - `git show master:CLAUDE.md > CLAUDE.md`
   - `git checkout master -- docs/ training/ aws/ gcp/ azure/ .gitignore .clang-format`
   - **Note:** `.github/` does NOT exist on origin/master — copy separately: `git checkout master -- .github/` <!-- CHANGED: Fixed — .github/ doesn't exist on origin/master, confirmed by codebase check — Reviewers 5,7,8 -->
5. Verify no stale references in copied docs: `grep -r "stagnation\|debugStateHash" docs/ training/` — resolve any hits <!-- CHANGED: Added grep check — Reviewer 1 -->
6. Commit: "Layer 0: Branch setup + infrastructure from master"
7. `git tag phase-1-complete` <!-- CHANGED: Added rollback tag — Reviewers 4,5,6,8 -->

### Verification
- [ ] MSBuild compiles clean (all 5 projects — GUI may warn about SFML paths, acceptable)
- [ ] `bin/Prismata_Testing.exe` runs (default tournament)
- [ ] No training/, js_engine/, or other code dirs affect the build

### Files modified
- `visualstudio/*.vcxproj` (PlatformToolset only)
- No C++ source changes

---

## Phase 2a: Neural Net Inference (Layer 1)
<!-- CHANGED: Split Phase 2 into 2a/2b/2c — All 8 reviewers -->
**Session 2 — additive C++ files + minimal modifications**

### Tasks
1. Copy `source/ai/NeuralNet.h` (94 lines) from master — entire file is new
2. Copy `source/ai/NeuralNet.cpp` (782 lines) from master — entire file is new
3. Copy `bin/asset/config/neural_weights.bin` from master
4. Add to `visualstudio/Prismata_AI.vcxproj`:
   - `<ClCompile Include="..\source\ai\NeuralNet.cpp" />`
   - `<ClInclude Include="..\source\ai\NeuralNet.h" />`
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
10. Edit `source/ai/AlphaBetaSearchParameters.hpp` — add `_blendWeight`, `deepClone()`  <!-- CHANGED: deepClone stays here — CRITICAL for threading, confirmed by codebase -->
11. Commit: "Layer 1: Neural net inference + AB/SAB eval integration"
12. `git tag phase-2a-complete`

### Verification
- [ ] MSBuild compiles clean
- [ ] `bin/Prismata_Testing.exe` runs default tournament (non-neural)
- [ ] Neural weights load (check stderr for "loaded 26 tensors" — count is fixed at 26)
- [ ] **Neural eval smoke test:** Run a single-position evaluation and verify result is in plausible range (0-100, not NaN, not exactly 0.0 or 100.0). E.g., configure a 1-game tournament with NeuralNet eval and check it completes. <!-- APPLIED: Optional enhancement #2 — Reviewers 5,7,8 -->
- [ ] **Memory check:** Log peak working set after neural weights load. Compare against Phase 0.5 baseline. <!-- APPLIED: Optional enhancement #3 (partial) — Reviewers 2,5,8 -->

### Source references (copy from master)
- NeuralNet.h: `git show master:source/ai/NeuralNet.h`
- NeuralNet.cpp: `git show master:source/ai/NeuralNet.cpp`

---

## Phase 2b: UCT/PUCT Search Integration (Layer 2)
<!-- CHANGED: Isolated UCT changes from Phase 2a — All 8 reviewers -->
**Session 2 (continued) — complex search changes, isolated for bisection**

### Tasks
1. Edit `source/ai/UCTSearch.cpp` — PUCT selection + neural eval in traverse():
   - `#include "NeuralNet.h"`, `#include <algorithm>`
   - `traverse()` return type: `PlayerID` → `double` (2 internal call sites only, no external callers)
   - PUCT node selection formula in `UCTNodeSelect()`
   - `computeRootPriors()` method
   - NeuralNet eval path in traverse()
   - `getBestRootWinRate()` method
   - **DO NOT add rootDiagnostics** — confirmed dead code, never read <!-- CHANGED: Removed rootDiagnostics — Reviewers 4,5,7, confirmed by codebase grep -->
2. Edit `source/ai/UCTSearch.h` — updated signatures
3. Edit `source/ai/UCTSearchParameters.hpp` — add `_blendWeight`, `_usePUCT`, `deepClone()`
4. Edit `source/ai/UCTNode.h/cpp` — add `_policyPrior` member + accessors
5. Edit `source/ai/UCTSearchResults.hpp` — NO rootDiagnostics (dead code removed) <!-- CHANGED: Removed — Reviewers 4,5,7 -->
6. Edit Player_AlphaBeta.h, Player_StackAlphaBeta.h, Player_UCT.h/cpp — deepClone in clone() <!-- deepClone is CRITICAL for multi-threaded tournaments — codebase confirms race conditions without it -->
7. Commit: "Layer 2: UCT/PUCT neural search integration"
8. `git tag phase-2b-complete`

### Verification
- [ ] MSBuild compiles clean
- [ ] Default tournament still runs (non-neural)
- [ ] UCT player with NeuralNet eval runs without crash (configure a test tournament)

---

## Phase 2c: AI Configuration (Layer 2 config)
<!-- CHANGED: Separated config from search code — Reviewers 4,5,7 -->
**Session 2 (continued) — configuration only, no algorithmic changes**

### Tasks
1. Edit `source/ai/AIParameters.cpp` — add parsing for:
   - NeuralNet/NeuralNetPlusPlayout eval methods in UCT and StackAlphaBeta player sections
   - BlendWeight, UsePUCT parameters
   - `playersHaveSameConfig()` for SkipColorSwap auto-detection (convenience optimization — explicit `"SkipColorSwap":true` in config.txt also works without this) <!-- CHANGED: Documented purpose — Reviewer 7 -->
   - **DO NOT add** `legacy` flag routing for GreedyKnapsack/TechHeuristic/Breach
2. Edit `source/ai/AIParameters.h` — `_rootValue` type change, `playersHaveSameConfig()` declaration
3. Edit `bin/asset/config/config.txt` — add:
   - OriginalHardestAI as a named copy of the original HardestAI config (baseline reference)
   - Neural eval player definitions (PrismatAI_UCT, PrismatAI_AB, etc.)
   - LiveHardestAI player definitions (from SWF extraction)
   - LiveHardestAI partial players and filters
4. LiveHardestAI opening books — add in same commit (these are config data, not code) <!-- CHANGED: Kept opening books here but documented they're config-only — Reviewers 4,5 wanted deferral but these are just JSON data -->
5. Commit: "Layer 2 config: AI parameters + player definitions"
6. `git tag phase-2c-complete`

### Verification
- [ ] MSBuild compiles clean
- [ ] Config parses LiveHardestAI and neural players without errors
- [ ] Neural weights load successfully
- [ ] Run a 2-round tournament: LiveHardestAI vs OriginalHardestAI — completes without crash
- [ ] **Performance check:** Compare tournament speed (games/sec) against Phase 0.5 baseline <!-- APPLIED: Optional enhancement #3 (partial) — Reviewers 2,5,8 -->

---

## Phase 3: --suggest CLI Mode (Layer 3)
**Session 3 — Benchmarks.cpp + main.cpp changes**

### Tasks
1. Edit `source/testing/main.cpp` — rewrite to add:
   - CLI argument parsing (--suggest, --player, --think-time)
   - Stdout redirect to stderr during init (`_dup`/`_dup2`)
   - NeuralNet weight loading at startup
   - PID-based random seeding: `srand((unsigned int)(time(NULL) ^ (_getpid() << 4)))` <!-- CHANGED: GETPID→_getpid for MSVC clarity — Reviewer 7 -->

2. Edit `source/testing/Benchmarks.h` — add:
   ```cpp
   void DoSuggest(const std::string & stateFile, const std::string & playerName, int thinkTimeMs);
   ```

3. Edit `source/testing/Benchmarks.cpp` — add DoSuggest (lines 740-1077 from master):
   - Helper functions: `jsonEscape`, `jsonStringArray`, `phaseToString`, `suggestError`, `appendClick`
   - DoSuggest main function
   - **KEEP shift-click expansion code** — it correctly expands shift-flagged actions into individual `inst clicked` entries (iterates all cards of same type, emits per-instance clicks). The expansion at lines 993-1016 is verified correct. <!-- CHANGED: REVERSED plan's "remove expansion" — All 8 reviewers flagged the gap this would create. Codebase confirms expansion code works correctly; bugs were in suggest_adapter.js (being discarded), not in DoSuggest -->
   - **MODIFICATION:** Remove `state_hash` from JSON output (depends on `debugStateHash()` which needs stagnation infrastructure)
   - Add necessary includes: `NeuralNet.h`, `Player_StackAlphaBeta.h`, `Player_UCT.h`, `<fstream>`, etc.

4. Edit `source/engine/Card.h` — add `int m_clientInstId = -1;` + `int getClientInstId() const;`
   (Required because DoSuggest uses `card.getClientInstId()` for click _id mapping. Single int field, no engine behavior change.)

5. Edit `source/engine/Card.cpp` — parse `instId` from JSON + getter implementation

6. Commit: "Layer 3: --suggest CLI mode for AI move generation"
7. `git tag phase-3-complete`

<!-- CHANGED: Deleted old Step 6 (debugStateHash "WAIT" discussion) — confusing to include something we're NOT doing — Reviewers 5,7,8 -->

### Verification
- [ ] MSBuild compiles clean
- [ ] Prepare a test state JSON (bare format — no CurrentInfo wrapper) <!-- CHANGED: Specified format — Reviewer 7 -->
- [ ] `bin/Prismata_Testing.exe --suggest test_state.json` produces valid JSON to stdout
- [ ] JSON contains: ok, eval, eval_pct, active_player, phase, clicks array
- [ ] JSON does NOT contain state_hash
- [ ] Clicks array contains individual `inst clicked` entries for multi-instance abilities (no shift flag in output)

### Anti-patterns
- Do NOT add DoReplay, DoReplayBatch, DoEval, DoAnalyze, DoDumpStates (not needed for baseline)
- Do NOT add SelfPlayDataSink or ReplayStepper includes

---

## Phase 3.5: Click Protocol Specification
<!-- CHANGED: New phase — Reviewers 2,5,7 (7/8 wanted explicit schema) -->
**Before Phase 7 — document the C++↔JS interface contract**

### Tasks
1. Write `docs/suggest_protocol.md` containing:
   - **Input schema:** bare format (what matchup code writes) vs F6 format (what clipboard produces). Matchup code uses bare format.
   - **Output schema:** JSON fields (`ok`, `eval`, `eval_pct`, `active_player`, `phase`, `clicks`, `buy`, `abilities`, `defense`, `breach`, `think_ms`, `timing_ms`, `full_move`), with types and examples
   - **Click types:** `"card clicked"` (BUY, _id=mergedDeck index), `"inst clicked"` (USE_ABILITY/ASSIGN_BLOCKER/BREACH, _id=client instId), `"space clicked"` (END_PHASE, _id=-1)
   - **Multi-instance handling:** C++ expands shift-flagged actions into individual inst clicks. JS receives and applies sequentially. No shift flag in output.
   - **End-turn protocol:** Two "space clicked" entries (enter confirm + commit turn)
   - **Error format:** `{"ok":false, "error":"<message>"}`
   - **Determinism:** Same state + same player + same think-time → same output (seeded RNG)
2. Commit: "Add --suggest click protocol specification"

### Verification
- [ ] Document exists and covers all click types
- [ ] Example JSON matches actual --suggest output from Phase 3

---

## Phase 4: Card Library — 105 Units (Layer 4)
**Session 4 — cardLibrary.jso verification**

### Tasks
1. Read current `bin/asset/config/cardLibrary.jso` from master
2. Read origin/master's `cardLibrary.jso` (has 78 UIName entries) <!-- CHANGED: Added known count — codebase check -->
3. Diff the two — identify exactly which units were added or modified
4. **Merge strategy for existing units:** Live game screenshots are authoritative for ALL field values. If origin/master has a unit that differs from the live game, use live game data. <!-- CHANGED: Added explicit merge rule — Reviewers 4,5,6,7,8 -->
5. **Run SWF card data comparison** (primary automated verification): <!-- APPLIED: Optional enhancement #6 — Reviewers 7,8. SWF data confirmed available: tmp_swf_extract/81_mcds.Util_testNormalCards.bin (275 entries, 77KB JSON with full card definitions) -->
   ```bash
   node tools/compare_card_libraries.js
   ```
   This compares `cardLibrary.jso` against the authoritative SWF-extracted card data at `tmp_swf_extract/81_mcds.Util_testNormalCards.bin` (275 entries, keyed by display name). Reports: missing units, extra units, field mismatches (rarity, toughness, buyCost, scripts). Check claude-mem for comparison script results.
6. Cross-reference any SWF comparison mismatches against live game screenshots (Aegis through Zemora Voidbringer)
7. Also reference card data from Prismata install: `C:\Program Files (x86)\Steam\steamapps\common\Prismata`
8. Write the clean cardLibrary.jso with ONLY:
   - Base set units (Drone, Engineer, Conduit, Blastforge, Animus, Wall, Forcefield, Tarsier, Rhino, Steelsplitter, Gauss Cannon)
   - 105 additional units from screenshots
   - Unbuyable tokens referenced by active cards' scripts (Behemoth, Transwall, Fusion, etc.)
   - NO unreleased/beta units
9. **Run cardLibrary validation script:** <!-- CHANGED: Added automated validation — Reviewers 1,2,6,7,8 -->
   ```bash
   node -e "
     const lib = JSON.parse(require('fs').readFileSync('bin/asset/config/cardLibrary.jso','utf8'));
     const cards = Object.values(lib);
     const withUI = cards.filter(c => c.UIName);
     const issues = [];
     withUI.forEach(c => {
       if (!c.rarity) issues.push(c.UIName + ': missing rarity');
       if (!c.toughness && c.toughness !== 0) issues.push(c.UIName + ': missing toughness');
       // check script references exist
       if (c.buyScript) { /* validate referenced card names exist in lib */ }
     });
     console.log('Units with UIName:', withUI.length);
     console.log('Issues:', issues.length ? issues.join('\\n') : 'none');
   "
   ```
10. Commit: "Layer 4: Card library with 105 verified additional units"
11. `git tag phase-4-complete`

### Verification
- [ ] Count UINames: exactly 105 additional + ~11 base + unbuyable tokens
- [ ] Every UIName matches a unit in the live game screenshots
- [ ] No unreleased/beta units present
- [ ] SWF comparison script reports no unexpected mismatches (all differences explained)
- [ ] Validation script reports no issues (required fields present, no duplicate names)
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

2. Verify file count: `find js_engine/ -type f | wc -l` and reconcile against manifest <!-- CHANGED: Verify actual count rather than assuming 32 — Reviewer 5 -->

3. Verify external dependencies exist:
   - `bin/asset/config/cardLibrary.jso` (from Phase 4 — **must complete Phase 4 first**) <!-- CHANGED: Added dependency note — Reviewer 7 -->
   - `tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin` (SWF AI params — gitignored, on disk)
   - `tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin` (SWF AI params — gitignored, on disk)

4. Run test suite:
   ```bash
   cd js_engine && node test_state.js && node test_tier1.js && node test_tier2.js
   ```

5. Run replay validation:
   ```bash
   cd js_engine && node replay_validator.js --count 500
   ```

6. Commit: "Layer 5: Validated JS transpiled engine from 99d39fe"
7. `git tag phase-5-complete`

### Verification
- [ ] All test files pass
- [ ] Replay validation: 100% pass on 500 replays (matching original validation)
- [ ] No files from post-99d39fe commits present (no suggest_adapter.js, no matchup_main.js)

### External file check
| File | Source | Required by |
|------|--------|-------------|
| `bin/asset/config/cardLibrary.jso` | Phase 4 | card_library.js |
| `tmp_swf_extract/148_*.bin` | Already on disk (SWF extract, gitignored) | ai_params.js |
| `tmp_swf_extract/93_*.bin` | Already on disk (SWF extract, gitignored) | ai_params.js |

---

## Phase 6: MCDSAI Binary (Layer 6)
**Session 5 (continued) or Session 6**

### Tasks
1. **Verify existing MCDSAI binary** at `tmp_browser_client/MCDSAI3441.js`: <!-- CHANGED: Existing binary is primary, not fresh download — All 8 reviewers -->
   ```bash
   node -e "const crypto=require('crypto'); const fs=require('fs'); const h=crypto.createHash('sha256').update(fs.readFileSync('tmp_browser_client/MCDSAI3441.js')).digest('hex'); console.log(h);"
   ```
   Compare against `EXPECTED_HASH` in `js_engine/mcdsai_wrapper.js`.

2. **Optional:** Download fresh from play.prismata.net and compare SHA256. If different hash, log version difference and investigate before proceeding. If download fails, continue with existing binary. <!-- CHANGED: Fresh download is optional validation — Reviewers 5,7 -->

3. Verify the binary loads:
   ```bash
   node -e "const m = require('./js_engine/mcdsai_wrapper.js'); m.loadMCDSAI()"
   ```

4. Test MCDSAI worker lifecycle:
   ```bash
   node js_engine/test_selfplay.js
   ```

5. Commit: "Layer 6: MCDSAI binary verified"
6. `git tag phase-6-complete`

### Verification
- [ ] SHA256 of binary matches pinned hash in mcdsai_wrapper.js
- [ ] MCDSAI process starts without errors
- [ ] `test_selfplay.js` passes (single game completes)

---

## Phase 7: Matchup Integration — REWRITE (Layer 7)
**Session 7+ — careful incremental development**

This is the layer that was the SOURCE of accumulated bugs. Build from scratch with verification at each step.

### Matchup Configuration
<!-- APPLIED: Optional enhancement #7 — Reviewer 8 -->
Create `js_engine/matchup_config.json` with tunable parameters:
```json
{
    "maxTurns": 200,
    "thinkTimeMs": 3000,
    "timeoutMultiplier": 3,
    "retryOnError": 1,
    "stuckDetectionTurns": 5,
    "logLevel": "info"
}
```
Avoids hardcoding, makes debugging easier (set `logLevel: "debug"` for full state dumps).

### Sub-phase 7a: Single Turn — Protocol Conformance
<!-- CHANGED: Added protocol conformance emphasis and supply test — Reviewers 2,4,5,6,8 -->
Write minimal `matchup_clean.js` that: <!-- CHANGED: Renamed from matchup_v2.js — Reviewer 7 -->

**Step 0: Supply verification (FIRST — before any game logic)** <!-- CHANGED: Added — 6/8 reviewers -->
```javascript
// After initializing game state, IMMEDIATELY verify:
const SUPPLY_BY_RARITY = { legendary: 1, rare: 4, normal: 20, trinket: 20 };
state.mergedDeck.forEach(card => {
    if (card._inactive) return; // skip inactive/token cards
    const expected = SUPPLY_BY_RARITY[card.rarity];
    const actual = getSupply(card); // from card_library.js
    console.assert(actual === expected, `Supply mismatch: ${card.UIName} rarity=${card.rarity} expected=${expected} got=${actual}`);
});
```
This catches the headline bug (supply=20 for all units) before a single move is made.

**Steps 1-6: Single-turn test**
1. Initializes a game (JS engine) with a fixed card set
2. Exports current state to JSON (bare format — see `docs/suggest_protocol.md`)
3. Calls `Prismata_Testing.exe --suggest state.json --player HardestAI --think-time 3000`
4. Parses the JSON response
5. Applies clicks to JS engine one at a time via `analyzer.recordClick()`
6. Verifies: turn number incremented, resources changed, units built

**Verification:** Print before/after state. Manually inspect that the AI move makes sense. Verify click count matches expectations from protocol spec.

### Sub-phase 7b: Single Game
Extend to loop both players' turns:
1. Alternate: Player 0 turn → Player 1 turn
2. Check `state.gameover` after each turn
3. Record winner, turn count
4. **Error handling:** <!-- CHANGED: Added concrete error handling — Reviewers 4,5,6,8 -->
   - AI `--suggest` returns malformed JSON → log error + state dump, retry once, then forfeit game
   - AI `--suggest` crashes (non-zero exit) → log error, mark game invalid, continue
   - AI `--suggest` timeout (>thinkTime × 3) → kill process, mark game invalid
   - `analyzer.recordClick()` returns failure → log click + state, skip click, continue
   - Stuck detection: if game state unchanged for 5 consecutive turns, abort game as draw
5. **State observability:** Log every --suggest input/output to stderr for debugging <!-- CHANGED: Added — Reviewer 7 -->

**Verification:** Run 1 game to completion. Check winner, turn count, final state.

### Sub-phase 7c: Multi-Game
1. Random card set generation (use `card_library.js.randomSet()`)
2. Loop N games, tally results
3. Save per-game structured JSON logs: <!-- APPLIED: Optional enhancement #4 — Reviewers 5,8 -->
   ```json
   {"game": 1, "cardSet": [...], "winner": 0, "turns": 47, "thinkTimeMs": 3000,
    "errors": [], "startTime": "...", "endTime": "...", "supplyVerified": true}
   ```
4. Supply must be correct: legendary=1, rare=4, normal/trinket=20
5. **Supply verification per game** — assert at init, not just first game <!-- CHANGED: Added — Reviewers 2,3,4,5,6,8 -->

**Verification:**
- [ ] Run 10 games, all complete (or marked invalid with logged reason)
- [ ] Supply values correct in every game (verified by init-time assert)
- [ ] Win rate roughly plausible (not 100/0)
- [ ] No undefined property errors in JS engine

### Sub-phase 7d: MCDSAI Integration
1. Add MCDSAI as a player option (via mcdsai_manager.js)
2. MCDSAI plays via JS engine directly (clicks, not --suggest)
3. Test: MCDSAI vs HardestAI via --suggest
4. **Color-symmetry test:** Run at least 2 games each way — MCDSAI as P0 AND as P1 — to verify no color-specific deadlocks <!-- CHANGED: Added — Reviewers 3,4 -->

**Verification:**
- [ ] MCDSAI vs HardestAI matchup runs to completion (both color assignments)
- [ ] No deadlocks in either direction

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
- C++ DoSuggest ALREADY expands shift-clicks into individual inst clicked entries — JS just applies them sequentially <!-- CHANGED: Clarified shift-click handling — All 8 reviewers -->
- End-turn requires TWO "space clicked" events (enter confirm + commit turn)
- MCDSAI response contains control chars — strip `[\x00-\x1f]` before JSON.parse
- Click.js uses `_type`, `_id` (underscore prefix), not `.type`, `.id`
- Matchup code writes bare format state JSON (no CurrentInfo wrapper) — DoSuggest handles both but bare is standard <!-- CHANGED: Clarified — Reviewer 7 -->

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
| rootDiagnostics in UCTSearchResults | Dead code — never read | Unnecessary complexity | <!-- CHANGED: Added — Reviewers 4,5,7, confirmed by codebase -->

---

## Execution Summary

| Phase | Layer | Session | Est. Effort | Key Risk |
|-------|-------|---------|-------------|----------|
| 1 | 0 | 1 | Low | PlatformToolset compatibility |
| 2a | 1 | 2 | Low-Medium | NeuralNet.cpp dependency on origin/master headers |
| 2b | 2 | 2 | Medium | UCTSearch traverse() return type (2 internal call sites) |
| 2c | 2-config | 2 | Low | Config parsing correctness |
| 3 | 3 | 3 | Medium | DoSuggest cleanup (remove stale deps) |
| 3.5 | — | 3 | Low | Documentation only |
| 4 | 4 | 4 | Medium | Unit name mapping accuracy |
| 5 | 5 | 5 | Low | Mechanical copy + validate |
| 6 | 6 | 5-6 | Low | MCDSAI binary integrity |
| 7 | 7 | 7+ | High | Integration — where bugs lived before |

---

## Deferred Enhancements

| Enhancement | Reviewers | Rationale for Deferral |
|-------------|-----------|----------------------|
| **Long-lived subprocess protocol** — Keep C++ exe alive, communicate via stdin/stdout JSON lines instead of spawning per turn | R2, R7 | Large effort. CLI-per-turn is simpler for baseline. Revisit as performance optimization after Phase 7e if turn latency is a bottleneck. |
