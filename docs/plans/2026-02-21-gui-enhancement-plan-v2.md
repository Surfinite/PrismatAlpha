# GUI Enhancement Plan v2 — PrismatAI Analysis Dashboard

> **Status:** PLAN — awaiting approval
> **Branch:** `feature/gui-analysis-dashboard`
> **Estimated phases:** 7 (each independently executable)
> **Previous version:** `2026-02-21-gui-enhancement-plan.md`
> **Changes from v1:** 7 reviews synthesized in `META-REVIEW-gui-enhancement-plan.md`

---

## Phase 0: Documentation & Architecture Summary

### Verified APIs & Patterns

**Drawing primitives** (GUITools.h/cpp):
- `GUITools::DrawRect(tl, size, color, window)` — solid rectangle
- `GUITools::DrawString(pos, str, color, window, fontSize=12)` — text (Consolas font)
- `GUITools::DrawLine(p1, p2, color, window)` — line
- `GUITools::DrawMana(resources, origin, iconSize, numSize, spacing, drawZeros, window)` — resource bar

**Window:** 2133x1200, origin top-left. Buy pane x:0-200. Board split at y:600 (P0 bottom, P1 top).

**Debug panel positions:** P0 at (1683, 620), P1 at (1683, 20). Width ~450px.

**Resource icon positions:** P0 at (210, 1160), P1 at (210, 10). Icons 32x32, 10px horizontal spacing. Order: Gold, Energy, Blue, Red, Green, Attack.

**Evaluation ranges:**
- `NeuralNet::evaluateValue()` -> `[-1, +1]` (tanh), perspective-adjusted for maxPlayer
- `Eval::NeuralNetEvaluation()` -> `[-100, +100]` (value x 100)
- `Eval::WillScoreSum(state, player)` -> unbounded, typically 0-300+ per side
- `Eval::WillScoreEvaluation(state, maxPlayer)` -> difference, typically [-500, +500]

**Neural eval cost:** ~0.5ms per call (2,000 evals/sec/core). Safe to call per-click.

<!-- CHANGED: Added confirmed thread safety documentation — Meta-review finding (validated by code inspection) -->
### Confirmed Thread Safety (Code-Verified)

The following were verified safe for concurrent use via direct code inspection during meta-review:

1. **`NeuralNet::evaluate()` is thread-safe in Release builds.** The method is `const`. All intermediate vectors (`features`, `h`, `blockOut`, `policyHidden`, `valueHidden`) are allocated locally on each call. Forward pass methods (`linearForward`, `layerNormForward`, `reluInPlace`) are `static` — they only read from const weight references and write to provided output buffers. Weights are immutable after `loadWeights()`. The `static bool firstCall` in `extractFeatures()` is gated behind `#ifdef NEURAL_NET_DEBUG` (compiled out in Release). **No mutex needed.**

2. **`AIParameters::getPlayer()` is thread-safe.** Code at line 935: `return _playerMap[player][playerName]->clone()`. The map is populated at init and never modified during gameplay. `clone()` creates fully independent Player objects. `AlphaBetaSearchParameters::clone()` deep-clones all `shared_ptr`s (lines 66-73 of `.hpp`). Concurrent reads from `std::map` with no concurrent writes are safe per C++ standard.

3. **`GameState` deep copy produces independent instances.** Value members only: `CardData m_cards`, `Resources m_resources[2]`, `TurnType m_turnNumber`, `PlayerID m_activePlayer`. No `shared_ptr` or raw pointer sharing. Used safely in `GUIState_WatchTraining` and `Tournament.cpp`.

4. **Not PyTorch/LibTorch.** `NeuralNet.cpp` is a hand-written C++ forward pass with raw `std::vector<float>` storage. No framework, no JIT, no framework allocator. No framework-level concurrency concerns.

### Threading precedent
`GUIState_WatchTraining` uses `StateQueue` (mutex-guarded), `std::vector<std::thread>` workers, `std::atomic<bool>` stop flag. Each worker gets its own `GameState` copy.

`Tournament.cpp` uses `std::thread` vector + `std::mutex` for result aggregation. Each game is independent — copy GameState per thread.

<!-- CHANGED: Added std::async/std::future as recommended pattern — Reviewers R1, R7 -->
### Recommended Threading Pattern: `std::async`/`std::future`

For this plan, use `std::async`/`std::future` instead of a custom queue class. Benefits:
- Eliminates need for custom `EvalResultQueue` class
- `std::future::wait_for(0ms)` provides non-blocking polling in `onFrame()`
- Automatic thread lifecycle (no manual join needed if future is stored)
- Standard C++17 — no external dependencies

### Anti-Patterns
- GameState is NOT thread-safe for concurrent mutation. Always deep-copy before passing to threads.
- `m_doingAIMove` blocks all input — must not set this during background evaluation.
- Policy head on value-only models has all-zero weights — uniform softmax is expected, not a bug.
- H: values (`GetInflatedTotalCostValue`) are static per-CardType, not per-state — correct behavior.
- `HeuristicValues::Instance()` is a singleton populated at init — thread-safe for reads only.
<!-- CHANGED: Never detach threads — ALL reviewers -->
- **NEVER use `std::thread::detach()`.** Always store futures/threads and ensure completion before destruction or new batch. Detach = use-after-free risk on application exit.

### Key Files
| File | Role |
|------|------|
| `source/gui/GUIState_Play.h` | Play state — add new members here |
| `source/gui/GUIState_Play.cpp` | Play state impl — modify drawDebugInfo(), add new methods |
| `source/gui/GUIState_WatchTraining.h` | **REFERENCE**: StateQueue pattern, worker thread pattern |
| `source/gui/GUITools.h/cpp` | Drawing primitives (add DrawEvalBar helper) |
| `source/ai/Eval.cpp` | WillScoreSum, NeuralNetEvaluation — call these |
| `source/ai/NeuralNet.h/cpp` | evaluate(), evaluateValue() — call these |
| `source/ai/AIParameters.cpp` | Player name registry — all from config.txt JSON |
| `source/ai/AITools.h` | `PredictEnemyNextTurn()` — for resource prediction |
| `source/engine/GameState.h/cpp` | beginTurn() at line 1215 — resource production logic |
| `bin/asset/config/config.txt` | AI player definitions — rename here |

---

## Phase 1: Policy Bug Fix + Resource Prediction *(~1 hour, low risk)*

### 1A: Fix Policy Display for Value-Only Models

**Problem:** The 305K model is value-only. `export_weights.py` (line 258-262) writes all-zero policy weights. In C++, all-zero linear layers produce `policy[i] = 0.0` for every unit, so softmax gives uniform `100/N%` for all affordable units. The display is "correct" but misleading.

**Fix:** In `drawDebugInfo()` (GUIState_Play.cpp ~line 833), detect zero-policy and show a clear message instead of misleading percentages.

**Implementation:**
```
In drawDebugInfo(), after line 837 (nnOut = evaluate):
  - Check if all policy values are ~0 (max - min < 0.001)
  - If so, set a flag `bool policyIsZero = true`
  - When rendering N: labels (~line 895-910):
    - If policyIsZero, show "N: (value-only)" in grey instead of fake percentages
    - Otherwise show current N: + % display
```

<!-- CHANGED: Softer messaging for policy display — Reviewers R2, R5 -->
**Note:** Use neutral messaging like `"N: (value-only model)"` rather than alarming language like "BUG" or "BROKEN". The behavior is correct for the current model — it just needs to be communicated clearly.

**Files:** `source/gui/GUIState_Play.cpp` only.

### 1B: Gold Prediction Display

**Goal:** Show "(+X)" predicted gold next turn near the resource display. Updates on every user input (buy, click, undo).

**Implementation:**

Simple: count alive, non-under-construction Drones for each player. That's the gold income next turn. Recompute on every `doGUIAction()` call so it stays live.

```cpp
// In GUIState_Play.h
int m_predictedGold[2] = {0, 0};

// Recompute helper — call from doGUIAction() and on turn start
void GUIState_Play::updateGoldPrediction()
{
    for (int p = 0; p < 2; p++) {
        int gold = 0;
        for (const auto & cardID : m_currentState.getCardIDs(p)) {
            const Card & card = m_currentState.getCardByID(cardID);
            if (!card.isDead() && !card.isUnderConstruction()
                && card.getType().getUIName() == "Drone")
                gold++;
        }
        m_predictedGold[p] = gold;
    }
}
```

**Rendering:**
- Show `"(+N)"` next to the gold icon
- P0: below resource bar at ~(210, 1160 + 34)
- P1: above resource bar at ~(210, 10 - 16)
- Use `sf::Color(200, 200, 200)` (light grey) for prediction text

**Files:** `source/gui/GUIState_Play.h` (member), `source/gui/GUIState_Play.cpp` (helper + rendering + call from doGUIAction).

### Verification
- Build GUI, launch, toggle debug (#)
- Value-only model: N: labels should show "(value-only model)" instead of fake percentages
- Gold prediction: "(+N)" should appear near gold and update immediately when you buy/lose a Drone
- Verify count matches your mental Drone count
- Test early game (6-8 drones) and late game (many drones)

---

<!-- CHANGED: Eval bars moved to Phase 2 (was Phase 3) — reordered per reviewer consensus to put before threading -->
## Phase 2: Eval Bars *(~2 hours, medium risk)*

### Goal
Chess-style eval bar on the right side of the board, showing who's ahead according to the neural net.

### Design
Vertical bar, 30px wide x 500px tall, positioned at x = window_width - 50 (rightmost edge), centered vertically at y = 600 (board midline).

- **Neural eval bar**: filled proportionally based on neural value [-1, +1]
  - Value = 0 -> bar split 50/50
  - Value = +1 -> bar fully green (P0 winning)
  - Value = -1 -> bar fully red (P1 winning)
  - Formula: `greenHeight = (value + 1.0) / 2.0 * barHeight`
  <!-- APPLIED Optional #8: Clamp eval bar values to [-0.98, 0.98] — R6 -->
  - **Clamp displayed value to [-0.98, 0.98]** — ensures the losing side always has at least 1% of the bar visible, preventing an invisible sliver in extreme positions
<!-- CHANGED: WillScore bar is opt-in, toggled via W key — Reviewers R1, R4, R5 -->
- **WillScore bar**: second bar 30px to the left, same height. **Opt-in: toggled via `W` key when debug is active.** Hidden by default.
  <!-- APPLIED Optional #7: WillScore normalization tuning — R1, R3, R6 -->
  - Normalize using tanh: `normalized = tanh(willScoreDiff / 30.0)` to map unbounded range to [-1, 1]. **Note:** 30.0f chosen over 100.0f to avoid over-compressing typical WillScore differences (which are usually in the -50 to +50 range). Experiment with this constant during implementation — try 30, 50, 100 and see which gives the most readable bar movement.

### Drawing Helper
Add to GUITools (or inline in GUIState_Play):
```cpp
void DrawEvalBar(sf::Vector2f topLeft, float width, float height,
                 float value, // [-1, +1], positive = P0 advantage
                 sf::Color topColor, sf::Color bottomColor,
                 sf::RenderWindow * window)
{
    float midY = topLeft.y + height * (1.0f - (value + 1.0f) / 2.0f);
    // Top portion (P1 color) from topLeft.y to midY
    DrawRect(topLeft, sf::Vector2f(width, midY - topLeft.y), topColor, window);
    // Bottom portion (P0 color) from midY to bottom
    DrawRect(sf::Vector2f(topLeft.x, midY), sf::Vector2f(width, topLeft.y + height - midY), bottomColor, window);
}
```

### Update Timing
- **Neural eval bar:** Update after every AI move and after human confirms action phase (first Space press). Uses `NeuralNet::Instance().evaluateValue(m_currentState, 0)`.
<!-- CHANGED: WillScore updates at phase boundaries only, not per-click — ALL reviewers -->
- **WillScore bar:** Update on `END_PHASE` actions only (not per-click). This prevents visual noise during mid-turn actions while still capturing meaningful state transitions.
- Both bars also update when debug is toggled on.

### New Data Members
```cpp
float m_evalBarNeural = 0.0f;      // [-1, +1]
float m_evalBarWillScore = 0.0f;   // [-1, +1] (tanh-normalized)
bool m_showWillScoreBar = false;   // Toggled via W key
bool m_showEvalBars = false;       // Toggled via E key (independent of debug #)
```

<!-- APPLIED Optional #2: Eval bars with own toggle separate from debug — R1 -->
The eval bars are visible when **either** `m_drawDebugInfo` (# key) **or** `m_showEvalBars` (E key) is active. This allows clean eval bar display during streaming/spectating without the full debug panel.

Update `m_evalBarWillScore` on END_PHASE in `doGUIAction()`:
```cpp
if (action.type() == ActionTypes::END_PHASE) {
    double wsP0 = Eval::WillScoreSum(m_currentState, 0);
    double wsP1 = Eval::WillScoreSum(m_currentState, 1);
    m_evalBarWillScore = std::clamp(tanhf((wsP0 - wsP1) / 30.0f), -0.98f, 0.98f);
}
```

Update `m_evalBarNeural` after AI moves and phase transitions:
```cpp
if (NeuralNet::Instance().isLoaded()) {
    m_evalBarNeural = std::clamp((float)NeuralNet::Instance().evaluateValue(m_currentState, 0), -0.98f, 0.98f);
}
```

Toggle keys in key handler:
```cpp
if (key == sf::Keyboard::W && (m_drawDebugInfo || m_showEvalBars)) {
    m_showWillScoreBar = !m_showWillScoreBar;
}
if (key == sf::Keyboard::E) {
    m_showEvalBars = !m_showEvalBars;
}
```

### Rendering Position
```
x: 2083 (50px from right edge) — Neural bar (always shown when debug on)
x: 2043 (90px from right edge) — WillScore bar (only when m_showWillScoreBar)
y: 350 to 850 (500px tall, centered on midline)
Labels: "NN" above neural bar, "WS" above willscore bar (when shown)
Value label between bars: "+0.35" or "-12.4" etc.
```

### Files
`source/gui/GUIState_Play.h` (new members), `source/gui/GUIState_Play.cpp` (rendering + update hooks + key handler), optionally `source/gui/GUITools.h/cpp` (DrawEvalBar helper).

### Verification
- Bar should be green-dominant when player is ahead, red when behind
- WillScore bar should appear/disappear with W key
- WillScore bar should move at phase transitions (not per-click)
- Neural bar should update after AI moves
- Check boundary: winning position -> bar nearly full green, losing -> nearly full red
- Early game (even): bars should be near 50/50

---

<!-- CHANGED: Combined Phase 2 (Human AI Advice) + Phase 4 (Parallel Eval) into single phase — Reviewers R1, R2, R3, R4, R7 -->
<!-- CHANGED: Primary AI runs in background (not just comparison) — Reviewer R2 -->
<!-- CHANGED: Uses std::async/std::future instead of custom EvalResultQueue — Reviewers R1, R7 -->
<!-- CHANGED: State revision counter for stale-result detection — Reviewers R2, R7 -->
<!-- CHANGED: Cap concurrent background evals to 2 — Reviewers R2, R3, R6, R7 -->
<!-- CHANGED: "Thinking..." indicator — Reviewers R3, R5, R7 -->
<!-- CHANGED: Memory monitoring in debug panel — Reviewers R3, R6, R7 -->
## Phase 3: Parallel Evaluation + Human AI Advice *(~4 hours, higher risk)*

### Goal
Run all AI evaluations (primary AI move, comparison AI, human-side advice) in background threads so the GUI never freezes. Show human-side AI recommendations when debug is on.

### Architecture: `std::async`/`std::future`

Instead of a custom `EvalResultQueue` class, use `std::async` to launch evaluations and `std::future` to collect results non-blockingly.

```cpp
// Result structure for background AI evaluations
struct AIEvalResult {
    std::string playerName;     // "PrismatAI_AB", "OriginalHardestAI", etc.
    Move move;
    double score;
    std::string scoreLabel;
    bool isUCT;
    double timeMS;
    std::string buyNotation;
    PlayerID forPlayer;
    int forStateRevision;       // Match to m_stateRevision to discard stale results
};
```

### State Revision Counter

Add to GUIState_Play.h:
```cpp
int m_stateRevision = 0;  // Monotonic counter, incremented on every state change
```

Increment in `doGUIAction()`, undo handler, and new game:
```cpp
m_stateRevision++;  // Every time m_currentState changes for any reason
```

This replaces turn-number-based staleness checks. Turn numbers don't distinguish mid-turn states or undo actions, but `m_stateRevision` does.

### Background Evaluation Pattern

```cpp
// New members in GUIState_Play.h
int m_maxConcurrentEvals = 2;  // Configurable, conservative default for x86 memory safety
std::vector<std::future<AIEvalResult>> m_evalFutures;
bool m_isThinking = false;  // True while background evals are running

// Launch function — called at turn start
void GUIState_Play::launchBackgroundEvals(PlayerID player)
{
    // Wait for any prior evals to complete first
    waitForEvals();

    m_isThinking = true;
    int revision = m_stateRevision;

    // Primary AI (the one that actually makes the move)
    {
        GameState copy(m_currentState);
        std::string primaryName = m_autoPlayPlayerName[player];
        m_evalFutures.push_back(std::async(std::launch::async,
            [copy, primaryName, player, revision]() mutable -> AIEvalResult {
                PlayerPtr ai = AIParameters::Instance().getPlayer(player, primaryName);
                Move move;
                ai->getMove(copy, move);
                AIEvalResult result;
                result.playerName = primaryName;
                result.move = move;
                result.forPlayer = player;
                result.forStateRevision = revision;
                // ... extract score, timing from Player casts ...
                return result;
            }));
    }

    // Comparison AI (if enabled and within concurrency cap)
    if (m_evalFutures.size() < m_maxConcurrentEvals) {
        GameState copy(m_currentState);
        std::string compName = /* comparison player name */;
        m_evalFutures.push_back(std::async(std::launch::async,
            [copy, compName, player, revision]() mutable -> AIEvalResult {
                PlayerPtr ai = AIParameters::Instance().getPlayer(player, compName);
                Move move;
                ai->getMove(copy, move);
                AIEvalResult result;
                result.playerName = compName;
                result.move = move;
                result.forPlayer = player;
                result.forStateRevision = revision;
                return result;
            }));
    }
}
```

### Non-Blocking Result Polling

In `onFrame()` (called every frame):
```cpp
void GUIState_Play::pollEvalResults()
{
    for (auto it = m_evalFutures.begin(); it != m_evalFutures.end(); ) {
        if (it->wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
            AIEvalResult result = it->get();
            if (result.forStateRevision == m_stateRevision) {
                // Result is current — apply it
                applyEvalResult(result);
            }
            // Stale results silently discarded
            it = m_evalFutures.erase(it);
        } else {
            ++it;
        }
    }

    m_isThinking = !m_evalFutures.empty();
}
```

### Primary AI Move Execution

When the primary AI result arrives, apply the move:
```cpp
void GUIState_Play::applyEvalResult(const AIEvalResult & result)
{
    if (result.playerName == m_autoPlayPlayerName[result.forPlayer]) {
        // This is the primary AI — execute the move
        m_aiMove = result.move;
        m_aiMoveReady = true;
        // Update eval bars
        if (NeuralNet::Instance().isLoaded()) {
            m_evalBarNeural = NeuralNet::Instance().evaluateValue(m_currentState, 0);
        }
    }
    // Update debug panel with result info (eval, timing, buy notation)
    updateDebugInfo(result);
}
```

### "Thinking..." Indicator

In `drawDebugInfo()`:
```cpp
if (m_isThinking) {
    GUITools::DrawString(sf::Vector2f(1683, y), "Thinking...",
                         sf::Color(255, 255, 100), window, 14);
}
```

### Human-Side AI Recommendations

When debug (#) is on and it's the human's turn, launch advice evaluations:

**New data members** in GUIState_Play.h:
```cpp
struct HumanTurnAdvice {
    std::string neuralBuy;      // e.g. "DDBA"
    double neuralEval = 0;
    double neuralTimeMS = 0;
    std::string playoutBuy;     // e.g. "DDEW"
    double playoutEval = 0;
    double playoutTimeMS = 0;
    bool valid = false;
    int adviseRevision = -1;    // state revision advice was computed for
};
HumanTurnAdvice m_humanAdvice;
```

**Trigger:** At the start of the human's turn, when `!m_autoPlay[player]` and `m_drawDebugInfo`:
```cpp
// Launch human advice as background evals (non-blocking from the start)
void GUIState_Play::launchHumanAdvice(PlayerID player)
{
    int revision = m_stateRevision;

    // Neural AI advice
    {
        GameState copy(m_currentState);
        m_evalFutures.push_back(std::async(std::launch::async,
            [this, copy, player, revision]() mutable -> AIEvalResult {
                PlayerPtr ai = AIParameters::Instance().getPlayer(player, "PrismatAI_AB");
                Move move;
                ai->getMove(copy, move);
                AIEvalResult result;
                result.playerName = "PrismatAI_AB_Advice";
                result.move = move;
                result.forPlayer = player;
                result.forStateRevision = revision;
                return result;
            }));
    }

    // Playout AI advice (if within concurrency cap)
    if (m_evalFutures.size() < m_maxConcurrentEvals) {
        GameState copy(m_currentState);
        m_evalFutures.push_back(std::async(std::launch::async,
            [this, copy, player, revision]() mutable -> AIEvalResult {
                PlayerPtr ai = AIParameters::Instance().getPlayer(player, "OriginalHardestAI");
                Move move;
                ai->getMove(copy, move);
                AIEvalResult result;
                result.playerName = "OriginalHardestAI_Advice";
                result.move = move;
                result.forPlayer = player;
                result.forStateRevision = revision;
                return result;
            }));
    }
}
```

**Rendering:** In `drawDebugInfo()`, for the human player's panel:
```
After Will Score line, add:
  --- PrismatAI Suggests ---
  Eval: 72.6  (2001ms)
  Buy: DDBA

  --- OriginalHardestAI ---
  Eval: 9983.0  (2003ms)
  Buy: DDEW
```

**Invalidation:** Increment `m_stateRevision` on any human action (in `doGUIAction`). Stale results (wrong revision) are automatically discarded by `pollEvalResults()`.

### Thread Lifecycle

```cpp
// Wait for all outstanding evaluations to complete
void GUIState_Play::waitForEvals()
{
    for (auto & fut : m_evalFutures) {
        if (fut.valid()) {
            fut.get();  // Block until complete, discard result
        }
    }
    m_evalFutures.clear();
    m_isThinking = false;
}

// Call in destructor and before new game
GUIState_Play::~GUIState_Play()
{
    waitForEvals();
}
```

### Configurable Eval Cap
<!-- CHANGED: Eval cap made configurable instead of hardcoded — User preference on item #10 -->

Parse from config.txt GUI section (or hardcode default of 2):
```cpp
// In GUIState_Play constructor or init, read from config
m_maxConcurrentEvals = configVal.HasMember("MaxConcurrentEvals")
    ? configVal["MaxConcurrentEvals"].GetInt() : 2;
```

Config.txt entry (optional, defaults to 2 if absent):
```json
"MaxConcurrentEvals": 2
```

Valid range: 1-4. Values >2 risk x86 OOM under 4GB address space. Use 1 for single-threaded fallback.

<!-- APPLIED Optional #3: Config toggle for parallel eval fallback — R7 -->
### Parallel Eval Toggle

Config.txt entry (optional, defaults to true):
```json
"ParallelEval": true
```

When `false`, all AI evaluations run sequentially on the main thread (original behavior). This provides a fallback if threading causes instability. Parse alongside `MaxConcurrentEvals`:
```cpp
m_parallelEval = !configVal.HasMember("ParallelEval") || configVal["ParallelEval"].GetBool();
```

When `m_parallelEval` is false, `launchBackgroundEvals()` runs the primary AI synchronously and skips comparison/advice launches.

<!-- APPLIED Optional #4: On-demand advice via F7 hotkey — R4 -->
### On-Demand Advice (F7)

In addition to automatic advice at turn start, pressing **F7** during the human's turn re-launches advice evaluations for the current state. Useful after mid-turn actions (partial buys, ability usage) to get fresh advice for the modified position.

```cpp
if (key == sf::Keyboard::F7 && !m_autoPlay[m_currentState.getActivePlayer()]
    && (m_drawDebugInfo || m_showEvalBars)) {
    launchHumanAdvice(m_currentState.getActivePlayer());
}
```

### Memory Monitoring

Add to debug panel (Windows-specific):
```cpp
#include <psapi.h>  // GetProcessMemoryInfo

void GUIState_Play::drawMemoryInfo(sf::RenderWindow * window, float y)
{
    PROCESS_MEMORY_COUNTERS pmc;
    if (GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof(pmc))) {
        size_t workingSetMB = pmc.WorkingSetSize / (1024 * 1024);
        std::string memStr = "Mem: " + std::to_string(workingSetMB) + " MB";
        sf::Color color = (workingSetMB > 3000) ? sf::Color::Red :
                          (workingSetMB > 2000) ? sf::Color::Yellow :
                          sf::Color(180, 180, 180);
        GUITools::DrawString(sf::Vector2f(1683, y), memStr, color, window, 10);
    }
}
```

### Files
`source/gui/GUIState_Play.h` (future members, HumanTurnAdvice, state revision), `source/gui/GUIState_Play.cpp` (background launch, polling, rendering, memory monitor).

### Verification
- AI turn should produce correct moves (primary AI result applied)
- GUI should NOT freeze during AI thinking — "Thinking..." shows, UI remains responsive
- Debug panel should populate with evaluation results as they complete
- Stale results from previous turns/undone states should not appear
- Human's turn: AI recommendations appear in debug panel after a few seconds
- No crashes on game exit or rapid turn changes (destructor joins all futures)
- Memory display shows current working set, turns yellow >2GB, red >3GB
- Test with 2 concurrent evals — verify no crashes or corruption

---

## Phase 4: Eval History Graph *(~2 hours, medium risk)*

### Goal
Show a mini-graph of neural eval over the game so far, like the eval graph in chess broadcasts.

### Data Collection
Add to GUIState_Play.h:
```cpp
struct EvalHistoryEntry {
    int turnNumber;
    float neuralEval;    // [-1, +1]
    float willScoreDiff; // raw
};
std::vector<EvalHistoryEntry> m_evalHistory;
```

**Collection point:** After every turn (in `doGUIAction` when action is END_PHASE and turn changes):
```cpp
EvalHistoryEntry entry;
entry.turnNumber = m_currentState.getTurnNumber();
entry.neuralEval = NeuralNet::Instance().evaluateValue(m_currentState, 0);
entry.willScoreDiff = Eval::WillScoreSum(m_currentState, 0) - Eval::WillScoreSum(m_currentState, 1);
m_evalHistory.push_back(entry);
```

### Rendering
Small graph in bottom-right corner (or below the eval bars):
- Position: (1800, 900) to (2100, 1100) — 300x200px
- Background: semi-transparent black rect
<!-- APPLIED Optional #6: Dynamic X-axis scaling — R3 -->
- X axis: turn number, **dynamically scaled** — the graph always fills its full width regardless of game length. `xScale = graphWidth / max(1, m_evalHistory.size() - 1)`. Short games (10 turns) and long games (40+ turns) both use the full 300px width.
- Y axis: eval [-1, +1] for neural
- Center line at y=0 (50/50)
- Plot as connected line segments using DrawLine
- Neural eval in blue, WillScore (tanh-normalized) in yellow

<!-- APPLIED Optional #1: Eval history CSV export on game end — R1 -->
### CSV Export on Game End

When a game ends (in `GameOver` handler or equivalent), write `eval_history.csv` to the `bin/` directory:
```cpp
void GUIState_Play::exportEvalHistory()
{
    if (m_evalHistory.empty()) return;
    std::ofstream f("eval_history.csv");
    f << "turn,neural_eval,willscore_diff\n";
    for (const auto & e : m_evalHistory) {
        f << e.turnNumber << "," << e.neuralEval << "," << e.willScoreDiff << "\n";
    }
}
```

Overwrites each game. Useful for cross-game analysis in Excel/Python.

### Files
`source/gui/GUIState_Play.h` (history vector), `source/gui/GUIState_Play.cpp` (collection + rendering + CSV export).

### Verification
- Graph should grow with each turn
- Early game should be near center line
- Dramatic swings should be visible after big trades/attacks
- Graph should reset on new game
- Undo should remove the last entry (track via `m_stateRevision`)
- After game ends, `bin/eval_history.csv` should contain per-turn data

---

<!-- APPLIED Optional #5: Promote Card Value Overlay to core phase — R1, R3 -->
## Phase 5: Card Value Overlay *(~1.5 hours, medium risk)*

### Goal
For each affordable unit in the buy panel, show the neural net's **value delta** — how much does buying this unit improve (or worsen) the position? This replaces the currently-useless N: policy percentages with genuinely actionable information.

### Implementation

When debug (#) is on, for each buyable card type:
1. Copy current state
2. Simulate buying that unit (if affordable)
3. Evaluate the resulting state with the neural net
4. Show the delta vs. current eval as a color-coded number

```cpp
// In drawDebugInfo(), after existing N: label rendering (~line 895-910):
if (NeuralNet::Instance().isLoaded() && m_drawDebugInfo) {
    float baseEval = NeuralNet::Instance().evaluateValue(m_currentState, player);

    for (each affordable card type) {
        GameState buyCopy(m_currentState);
        // Simulate buy action
        Action buyAction(player, ActionTypes::BUY, cardTypeID);
        if (buyCopy.isLegal(buyAction)) {
            buyCopy.doAction(buyAction);
            float newEval = NeuralNet::Instance().evaluateValue(buyCopy, player);
            float delta = newEval - baseEval;

            // Render delta next to unit in buy panel
            // Green = positive (good buy), Red = negative (bad buy), Grey = neutral
            sf::Color color = (delta > 0.01f) ? sf::Color::Green :
                              (delta < -0.01f) ? sf::Color::Red :
                              sf::Color(180, 180, 180);
            std::string label = (delta >= 0 ? "+" : "") + std::to_string(delta).substr(0, 5);
            GUITools::DrawString(pos, label, color, window, 10);
        }
    }
}
```

**Cost:** ~20 buyable units x 0.5ms per eval = ~10ms total. Runs once per state change (not per frame). Well within the 16ms frame budget as a one-shot calculation.

### Rendering Position
Show the delta value below or next to each unit's existing H: and N: labels in the buy panel. Use `V:` prefix (for "value"):
```
V: +0.032  (green — buying this improves position)
V: -0.015  (red — buying this hurts position)
V: +0.001  (grey — negligible impact)
```

### Files
`source/gui/GUIState_Play.cpp` (drawDebugInfo, new rendering block).

### Verification
- Drones in early game should show positive V: values (economy building is good)
- Expensive units the AI wouldn't buy should show negative or neutral values
- Values should be consistent with what PrismatAI_AB actually buys
- Performance: no visible frame drop (10ms is well under budget for one-shot)

---

## Phase 6: Naming Consolidation — PrismatAlpha -> PrismatAI *(~1 hour, low risk)*

### Scope
Rename AI player references from `PrismatAlpha` to `PrismatAI` across active code. **Do NOT touch historical logs, eval-results, or docs.**

### Files to Change

**Config (must all match):**
1. `bin/asset/config/config.txt` — 18 occurrences: player names and tournament references
2. `aws/.s3_config.txt` — 18 occurrences (mirror of config.txt for cloud deploy)

**C++ source (2 hardcoded references):**
3. `source/testing/main.cpp:98` — `"PrismatAlpha_AB"` -> `"PrismatAI_AB"` (--suggest default)
4. `source/gui/GUIState_Menu.cpp:416` — `"PrismatAlpha_AB_Legacy"` -> `"PrismatAI_AB_Legacy"` (Watch Eval mode)

**Python tools (2 references):**
5. `tools/prismata_autopilot.py:5` — player name reference
6. `tools/prismata_advisor.py:1` — player name reference

**Launch scripts:**
7. `aws/launch_tournament.sh` — 2 occurrences

**Documentation (update to match):**
8. `CLAUDE.md` — 6 occurrences (update player name references)
9. `README.md` — 1 occurrence

### Naming Pattern
```
Old                          -> New
PrismatAlpha_AB              -> PrismatAI_AB
PrismatAlpha_UCT             -> PrismatAI_UCT
PrismatAlpha_UCT_Fast        -> PrismatAI_UCT_Fast
PrismatAlpha_UCT_c03/05/07/10 -> PrismatAI_UCT_c03/05/07/10
PrismatAlpha_AB_Legacy       -> PrismatAI_AB_Legacy
```

### DO NOT Change
- `eval-results-305k/` — historical log files (thousands of occurrences)
- `bin/tournament_eval_log*.txt` — historical
- `docs/PROJECT_HISTORY.md` — historical record (55 occurrences)
- `docs/plans/` — completed plans
- `bin/asset/replays/` — saved replay JSONs

### Safety
- Config.txt player names are parsed dynamically by AIParameters.cpp — names are just JSON keys
- No C++ code hardcodes player names except the 2 locations listed above
- Cloud deploy: update .s3_config.txt AND redeploy to S3 after rename

### Verification
- `grep -r "PrismatAlpha" source/ bin/asset/config/ tools/ aws/launch_tournament.sh` -> 0 results
- Build + launch GUI -> Watch Eval mode uses new name
- `--suggest` mode uses new default player name
- Cloud config matches local config

---

## Phase 7: Additional Enhancements *(ideas for future)*

These are lower-priority ideas that emerged during investigation. Each could be a separate mini-phase:

### 7A: Move Diff Visualization
When the neural AI and playout AI DISAGREE, highlight the differing buys in the debug panel (green for neural-only buys, red for playout-only buys). Makes disagreements immediately informative.

### 7B: Threat Indicator
Show incoming attack and whether current defense can absorb it. Already partially implemented via `m_drawPotentials` (X key toggle, lines 688-716). Could enhance with color coding (green = safe, yellow = losing units, red = lethal breach).

### 7C: Turn Timer
Show elapsed time for human's turn. Simple frame counter, displayed near status text.

### 7D: Opening Book Display
If we have the opening book data (`training/opening_book.py`), show known opening names and win rates for the current position.

---

## Execution Order & Dependencies

```
Phase 1 (bug fix + gold)         -> Independent, do first (quick wins)
Phase 2 (eval bars)              -> Independent, no threading needed
Phase 3 (parallel eval + advice) -> Most complex, makes everything non-blocking
Phase 4 (eval graph)             -> Builds on Phase 2+3 data collection
Phase 5 (card value overlay)     -> Needs neural net, benefits from Phase 1A fix
Phase 6 (naming)                 -> Independent, cosmetic
Phase 7 (extras)                 -> After core phases done
```

**Execution order:** 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

Each phase can be given to a fresh context with this plan document + the relevant source files. No phase requires knowledge of other phases' implementation details beyond the data members added to GUIState_Play.h.

---

## Build & Test Protocol

After each phase:
1. Build: `MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86 /m`
2. Launch: `cd bin && start Prismata_GUI.exe`
3. Play a few turns with debug (#) on
4. Verify new features render correctly
5. Check no regression in existing features (AI menu, auto-play, replay mode)

---

> **All 8 optional enhancements have been applied.** See `<!-- APPLIED Optional #N -->` comments throughout the plan for where each was integrated.
