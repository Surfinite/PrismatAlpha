# GUI Enhancement Plan — PrismatAI Analysis Dashboard

> **Status:** PLAN — awaiting approval
> **Branch:** `feature/gui-analysis-dashboard`
> **Estimated phases:** 7 (each independently executable)

---

## Phase 0: Documentation & Architecture Summary

### Verified APIs & Patterns

**Drawing primitives** (GUITools.h/cpp):
- `GUITools::DrawRect(tl, size, color, window)` — solid rectangle
- `GUITools::DrawString(pos, str, color, window, fontSize=12)` — text (Consolas font)
- `GUITools::DrawLine(p1, p2, color, window)` — line
- `GUITools::DrawMana(resources, origin, iconSize, numSize, spacing, drawZeros, window)` — resource bar

**Window:** 2133×1200, origin top-left. Buy pane x:0-200. Board split at y:600 (P0 bottom, P1 top).

**Debug panel positions:** P0 at (1683, 620), P1 at (1683, 20). Width ~450px.

**Resource icon positions:** P0 at (210, 1160), P1 at (210, 10). Icons 32×32, 10px horizontal spacing. Order: Gold, Energy, Blue, Red, Green, Attack.

**Evaluation ranges:**
- `NeuralNet::evaluateValue()` → `[-1, +1]` (tanh), perspective-adjusted for maxPlayer
- `Eval::NeuralNetEvaluation()` → `[-100, +100]` (value × 100)
- `Eval::WillScoreSum(state, player)` → unbounded, typically 0-300+ per side
- `Eval::WillScoreEvaluation(state, maxPlayer)` → difference, typically [-500, +500]

**Neural eval cost:** ~0.5ms per call (2,000 evals/sec/core). Safe to call per-click.

**Threading precedent:** `GUIState_WatchTraining` uses `StateQueue` (mutex-guarded), `std::vector<std::thread>` workers, `std::atomic<bool>` stop flag. Each worker gets its own `GameState` copy. This is the pattern to copy for parallel AI evaluation.

**Tournament threading:** `Tournament.cpp` uses `std::thread` vector + `std::mutex` for result aggregation. Each game is independent — copy GameState per thread.

### Anti-Patterns
- GameState is NOT thread-safe for concurrent mutation. Always deep-copy before passing to threads.
- `m_doingAIMove` blocks all input — must not set this during background evaluation.
- Policy head on value-only models has all-zero weights — uniform softmax is expected, not a bug.
- H: values (`GetInflatedTotalCostValue`) are static per-CardType, not per-state — correct behavior.
- `HeuristicValues::Instance()` is a singleton populated at init — thread-safe for reads only.
- `NeuralNet::Instance()` is a singleton — `evaluate()` is const and allocates locally, likely thread-safe for reads.

### Key Files
| File | Role |
|------|------|
| `source/gui/GUIState_Play.h` | Play state — add new members here |
| `source/gui/GUIState_Play.cpp` | Play state impl — modify drawDebugInfo(), add new methods |
| `source/gui/GUIState_WatchTraining.h` | **COPY FROM**: StateQueue pattern, worker thread pattern |
| `source/gui/GUITools.h/cpp` | Drawing primitives (add DrawFilledBar if needed) |
| `source/ai/Eval.cpp` | WillScoreSum, NeuralNetEvaluation — call these |
| `source/ai/NeuralNet.h/cpp` | evaluate(), evaluateValue() — call these |
| `source/ai/AIParameters.cpp` | Player name registry — all from config.txt JSON |
| `source/engine/GameState.h/cpp` | beginTurn() at line 1215 — resource production logic |
| `bin/asset/config/config.txt` | AI player definitions — rename here |

---

## Phase 1: Policy Bug Fix + Gold Prediction *(~1 hour, low risk)*

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

**Files:** `source/gui/GUIState_Play.cpp` only.

### 1B: Gold Prediction Display

**Goal:** Show "(+X)" predicted gold next turn in brackets near the resource display.

**Implementation:**
```
In drawInformation() (line 625), after DrawMana calls (line 645):
  For each player:
    1. Iterate state.getCardIDs(player)
    2. Count gold-producing cards:
       - Skip isDead(), isUnderConstruction()
       - Check type.hasBeginOwnTurnScript() && card.canRunBeginOwnTurnScript()
       - For simplicity: count Drones (type.getUIName() == "Drone") as +1 gold each
       - Also count Conduit → green, Blastforge → blue, Animus → red, Engineer → energy
    3. Draw "(+N)" text to the right of gold icon, slightly offset
       - P0: below resource bar at ~(210 + goldIconWidth + offset, 1160 + 34)
       - P1: below resource bar at ~(210 + goldIconWidth + offset, 10 + 34)
    4. Use sf::Color(200, 200, 200) (light grey) for prediction text
```

**More robust approach:** Use `AITools::PredictEnemyNextTurn()` — it already simulates a full turn. Copy state, call beginTurn(), read resulting resources. This captures resonance, construction completions, etc.

```cpp
// Gold prediction using engine simulation
GameState nextTurnState(m_currentState);
// Simulate end of current player's turn + begin of their next
// This is complex — simpler approach: just count drones
int droneCount = 0;
for (const auto & cardID : m_currentState.getCardIDs(player)) {
    const Card & card = m_currentState.getCardByID(cardID);
    if (!card.isDead() && !card.isUnderConstruction()
        && card.getType().getUIName() == "Drone")
        droneCount++;
}
// Draw "(+droneCount)" near gold
```

**Files:** `source/gui/GUIState_Play.cpp` (drawInformation method).

### Verification
- Build GUI, launch, toggle debug (#)
- Value-only model: N: labels should show "(value-only)" instead of fake percentages
- Gold prediction: "(+N)" should appear near gold and change as drones are bought/killed
- Test with different game states (early game few drones, late game many drones)

---

## Phase 2: Human-Side AI Recommendations *(~2 hours, medium risk)*

### Goal
When debug (#) is on and it's the human's turn, show what PrismatAI_AB and OriginalHardestAI would buy.

### Implementation

**New data members** in GUIState_Play.h:
```cpp
struct HumanTurnAdvice {
    std::string neuralBuy;      // e.g. "DDBA"
    double neuralEval = 0;
    double neuralTimeMS = 0;
    std::string playoutBuy;     // e.g. "DDEW"
    double playoutEval = 0;
    double playoutTimeMS = 0;
    bool valid = false;         // true when advice computed for current state
    int adviseTurnNumber = -1;  // turn number advice was computed for
};
HumanTurnAdvice m_humanAdvice;
```

**Trigger:** In `endCurrentPhase()` or at the start of the human's turn, when `!m_autoPlay[player]` (human is playing) and `m_drawDebugInfo` is on:
1. Copy `m_currentState` to local variable
2. Run `PrismatAI_AB` (neural) with reduced think time (2-3s) on the copy
3. Run `OriginalHardestAI` (playout) with same think time on the copy
4. Store results in `m_humanAdvice`
5. Set `m_humanAdvice.adviseTurnNumber = m_currentState.getTurnNumber()`

**Note:** This will block the GUI for ~4-6s total (2 sequential AI calls). Phase 4 (parallel eval) will make this non-blocking. For now, sequential is simpler and still useful.

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

Use the same rendering pattern as the existing AI debug info (lines 788-825).

**Invalidation:** Set `m_humanAdvice.valid = false` whenever the human makes any action (in `doGUIAction`). This prevents stale advice after partial moves. Re-trigger advice only at turn start, not after every click.

**Files:** `source/gui/GUIState_Play.h`, `source/gui/GUIState_Play.cpp`.

### Verification
- Play a game, debug on. Human's turn should show AI recommendations.
- Check that advice matches what the AI would actually do (run same position through `--suggest`).
- Verify advice clears after human makes an action.

---

## Phase 3: Eval Bar *(~2 hours, medium risk)*

### Goal
Chess-style eval bar on the right side of the board, showing who's ahead according to the neural net.

### Design
Vertical bar, 30px wide × 500px tall, positioned at x = window_width - 50 (rightmost edge), centered vertically at y = 600 (board midline).

- **Neural eval bar**: filled proportionally based on neural value [-1, +1]
  - Value = 0 → bar split 50/50
  - Value = +1 → bar fully green (P0 winning)
  - Value = -1 → bar fully red (P1 winning)
  - Formula: `greenHeight = (value + 1.0) / 2.0 * barHeight`
- **WillScore bar**: second bar 30px to the left, same height
  - Normalize using tanh: `normalized = tanh(willScoreDiff / 100.0)` to map unbounded range to [-1, 1]

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
- **WillScore bar:** Update on every `doGUIAction()` call (every click/action). Cost is trivial (sum over ~40 cards, <0.01ms).
- Both bars also update when debug is toggled on.

### New Data Members
```cpp
float m_evalBarNeural = 0.0f;  // [-1, +1]
float m_evalBarWillScore = 0.0f; // [-1, +1] (tanh-normalized)
```

Update `m_evalBarWillScore` in `doGUIAction()`:
```cpp
double wsP0 = Eval::WillScoreSum(m_currentState, 0);
double wsP1 = Eval::WillScoreSum(m_currentState, 1);
m_evalBarWillScore = tanhf((wsP0 - wsP1) / 100.0f);
```

Update `m_evalBarNeural` after AI moves and phase transitions:
```cpp
if (NeuralNet::Instance().isLoaded()) {
    m_evalBarNeural = NeuralNet::Instance().evaluateValue(m_currentState, 0);
}
```

### Rendering Position
```
x: 2083 (50px from right edge) — Neural bar
x: 2043 (90px from right edge) — WillScore bar
y: 350 to 850 (500px tall, centered on midline)
Labels: "NN" above neural bar, "WS" above willscore bar
Value label between bars: "+0.35" or "-12.4" etc.
```

### Files
`source/gui/GUIState_Play.h` (new members), `source/gui/GUIState_Play.cpp` (rendering + update hooks), optionally `source/gui/GUITools.h/cpp` (DrawEvalBar helper).

### Verification
- Bar should be green-dominant when player is ahead, red when behind
- WillScore bar should move with every buy action
- Neural bar should update after AI moves
- Check boundary: winning position → bar nearly full green, losing → nearly full red
- Early game (even): bars should be near 50/50

---

## Phase 4: Parallel AI Evaluation *(~3 hours, higher risk)*

### Goal
Run multiple AI evaluations concurrently when the AI's turn starts, so all debug info populates faster and we can show richer data.

### Architecture
Copy the `StateQueue` pattern from `GUIState_WatchTraining.h` (lines 21-42):

```cpp
// Result queue for background AI evaluations
struct AIEvalResult {
    std::string playerName;     // "PrismatAI_AB", "OriginalHardestAI", etc.
    Move move;
    double score;
    std::string scoreLabel;
    bool isUCT;
    double timeMS;
    std::string buyNotation;
    PlayerID forPlayer;
    int forTurnNumber;          // Match to current turn to avoid stale results
};

class EvalResultQueue {
    std::queue<AIEvalResult> m_queue;
    std::mutex m_mutex;
public:
    void push(const AIEvalResult & result);
    bool tryPop(AIEvalResult & out);
};
```

### Worker Thread Pattern
```cpp
void GUIState_Play::evalWorkerThread(GameState stateCopy, std::string playerName,
                                      PlayerID player, int turnNumber)
{
    // Each worker gets its OWN deep copy of GameState — thread-safe
    PlayerPtr ai = AIParameters::Instance().getPlayer(player, playerName);
    Move move;
    ai->getMove(stateCopy, move);  // Blocking ~7s

    AIEvalResult result;
    result.playerName = playerName;
    result.move = move;
    result.forPlayer = player;
    result.forTurnNumber = turnNumber;
    // ... extract score, timing from Player casts ...

    m_evalResultQueue.push(result);
}
```

### Integration Points

**Launch threads:** In `runAutoPlay()`, instead of sequential primary + comparison:
```cpp
// Launch 3 evaluations in parallel
GameState copy1(m_currentState), copy2(m_currentState), copy3(m_currentState);
std::thread t1(&GUIState_Play::evalWorkerThread, this, copy1, "PrismatAI_AB", player, turnNum);
std::thread t2(&GUIState_Play::evalWorkerThread, this, copy2, "OriginalHardestAI", player, turnNum);
std::thread t3(&GUIState_Play::evalWorkerThread, this, copy3, "HardestAI", player, turnNum);
// Detach or store in m_evalThreads vector
```

**Consume results:** In `onFrame()` or `sUserInput()`, poll the queue:
```cpp
AIEvalResult result;
while (m_evalResultQueue.tryPop(result)) {
    if (result.forTurnNumber == currentTurnNumber) {
        // Update m_aiDebugInfo with this result
    }
    // Stale results (wrong turn) are silently discarded
}
```

**Primary AI still runs synchronously** for the actual move execution. But the comparison AI and human-side recommendations run in background threads.

### Thread Lifecycle
- Store threads in `std::vector<std::thread> m_evalThreads`
- Join all threads in destructor and before launching new batch
- Use `std::atomic<bool> m_evalStop` for early termination on game exit/new turn

### Safety
- Deep copy GameState before passing to thread (verified: GameState has no shared mutable state after copy)
- NeuralNet::Instance().evaluate() is const — only reads weights, allocates local vectors. Thread-safe for concurrent reads.
- AIParameters::Instance().getPlayer() creates new Player objects — thread-safe if it doesn't mutate shared state. **Verify:** check if getPlayer copies or shares internal state.

### Files
`source/gui/GUIState_Play.h` (EvalResultQueue, thread members), `source/gui/GUIState_Play.cpp` (worker thread, queue polling, launch logic).

### Verification
- AI turn should still produce correct moves (primary AI unchanged)
- Debug panel should populate with 2-3 AI evaluations
- Stale results from previous turns should not appear
- No crashes on game exit or rapid turn changes
- Memory: verify no leaks from detached threads

---

## Phase 5: Eval History Graph *(~2 hours, medium risk)*

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
- Position: (1800, 900) to (2100, 1100) — 300×200px
- Background: semi-transparent black rect
- X axis: turn number (0 to current)
- Y axis: eval [-1, +1] for neural
- Center line at y=0 (50/50)
- Plot as connected line segments using DrawLine
- Neural eval in blue, WillScore (tanh-normalized) in yellow

### Files
`source/gui/GUIState_Play.h` (history vector), `source/gui/GUIState_Play.cpp` (collection + rendering).

### Verification
- Graph should grow with each turn
- Early game should be near center line
- Dramatic swings should be visible after big trades/attacks
- Graph should reset on new game

---

## Phase 6: Naming Consolidation — PrismatAlpha → PrismatAI *(~1 hour, low risk)*

### Scope
Rename AI player references from `PrismatAlpha` to `PrismatAI` across active code. **Do NOT touch historical logs, eval-results, or docs.**

### Files to Change

**Config (must all match):**
1. `bin/asset/config/config.txt` — 18 occurrences: player names and tournament references
2. `aws/.s3_config.txt` — 18 occurrences (mirror of config.txt for cloud deploy)

**C++ source (2 hardcoded references):**
3. `source/testing/main.cpp:98` — `"PrismatAlpha_AB"` → `"PrismatAI_AB"` (--suggest default)
4. `source/gui/GUIState_Menu.cpp:416` — `"PrismatAlpha_AB_Legacy"` → `"PrismatAI_AB_Legacy"` (Watch Eval mode)

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
Old                          → New
PrismatAlpha_AB              → PrismatAI_AB
PrismatAlpha_UCT             → PrismatAI_UCT
PrismatAlpha_UCT_Fast        → PrismatAI_UCT_Fast
PrismatAlpha_UCT_c03/05/07/10 → PrismatAI_UCT_c03/05/07/10
PrismatAlpha_AB_Legacy       → PrismatAI_AB_Legacy
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
- `grep -r "PrismatAlpha" source/ bin/asset/config/ tools/ aws/launch_tournament.sh` → 0 results
- Build + launch GUI → Watch Eval mode uses new name
- `--suggest` mode uses new default player name
- Cloud config matches local config

---

## Phase 7: Additional Enhancements *(~2 hours, ideas for future)*

These are lower-priority ideas that emerged during investigation. Each could be a separate mini-phase:

### 7A: Move Diff Visualization
When the neural AI and playout AI DISAGREE, highlight the differing buys in the debug panel (green for neural-only buys, red for playout-only buys). Makes disagreements immediately informative.

### 7B: Card Value Overlay
Instead of just H: (static cost) and N: (policy, currently zero), show the neural net's **value** assessment of buying each card. For each affordable unit: copy state → simulate buy → evaluate → show delta. Cost: ~20 evals × 0.5ms = 10ms, trivially fast. This would be genuinely useful — shows "how much does buying this unit improve my position?"

### 7C: Threat Indicator
Show incoming attack and whether current defense can absorb it. Already partially implemented via `m_drawPotentials` (X key toggle, lines 688-716). Could enhance with color coding (green = safe, yellow = losing units, red = lethal breach).

### 7D: Turn Timer
Show elapsed time for human's turn. Simple frame counter, displayed near status text.

### 7E: Opening Book Display
If we have the opening book data (`training/opening_book.py`), show known opening names and win rates for the current position.

---

## Execution Order & Dependencies

```
Phase 1 (bug fix + gold)     → Independent, do first
Phase 6 (naming)             → Independent, do anytime
Phase 2 (human AI advice)    → Independent, but benefits from Phase 4
Phase 3 (eval bar)           → Independent
Phase 5 (eval graph)         → Depends on Phase 3 (shares eval collection)
Phase 4 (parallel eval)      → Most complex, improves Phase 2+3
Phase 7 (extras)             → After core phases done
```

**Recommended order:** 1 → 6 → 3 → 2 → 4 → 5 → 7

Each phase can be given to a fresh context with this plan document + the relevant source files. No phase requires knowledge of other phases' implementation details beyond the data members added to GUIState_Play.h.

---

## Build & Test Protocol

After each phase:
1. Build: `MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86 /m`
2. Launch: `cd bin && start Prismata_GUI.exe`
3. Play a few turns with debug (#) on
4. Verify new features render correctly
5. Check no regression in existing features (AI menu, auto-play, replay mode)
