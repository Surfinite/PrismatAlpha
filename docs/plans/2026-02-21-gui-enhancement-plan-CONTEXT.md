# Review Context Document — PrismatAI GUI Enhancement Plan

---

## 1. Reviewer Brief

You are receiving two documents:

1. **This context document** — everything you need to understand the project
2. **The plan** — `docs/plans/2026-02-21-gui-enhancement-plan.md` — a 7-phase GUI enhancement proposal

Your role is to **critically analyze** the plan given the context provided. Specifically:

- Identify **weaknesses, risks, missing considerations, and better alternatives**
- Flag **unnecessary complexity** or things that should be removed
- Highlight what is **good and should be preserved**
- Suggest **additions, future features, and architectural improvements**
- Be constructively critical — not rubber-stamping
- Be **specific and actionable** — your review will be synthesized into a meta-review to improve the plan
- **Important**: You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making about the code.

### Review Output Format

Structure your review as follows:

1. **One-line verdict**: Your overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess. The plan author will validate these.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

**PrismatAI** is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game (no hidden information, no randomness — like chess but with an economic/army-building layer). The game was developed by Lunarch Studios and is playable via an Adobe AIR client.

**What the project does:**
- Simulates Prismata game states in C++
- Plays the game using Alpha-Beta search, UCT/MCTS, and a neural network value head
- Trains the neural net via self-play data generation at scale (722K games so far across AWS/GCP/Azure)
- Provides GUI for watching AI games and playing against the AI

**Development stage:** Active R&D, ~6 weeks old. The engine is a mature fork of an academic AI codebase (David Churchill, AIIDE 2015). The neural net training pipeline, cloud infrastructure, and GUI enhancements are new.

**Key goals:**
- Build a competitive neural-network-powered AI for Prismata (currently 45.3% win rate vs the strongest heuristic AI)
- Provide analysis tooling for understanding what the neural net has learned vs traditional heuristics
- Eventually: live game commentary, overlay advisor, and streaming integration

**Constraints:**
- x86 only (no x64 builds) — 4GB address space limit
- Cost-conscious — cloud bills are real money, prefer local compute
- Solo developer (the user is "Surfinite")
- Must not break existing self-play data generation pipeline

**Target users:** The developer (Surfinite) for personal gameplay analysis and AI development. Secondary: potential Prismata community viewers via streaming.

---

## 3. Architecture & Tech Stack

### Languages & Frameworks
- **C++17** — engine, AI, GUI (~36K LOC)
- **Python 3** — training pipeline, tools (~6K LOC)
- **SFML 2.6.2** — GUI rendering (2D graphics, no 3D)
- **RapidJSON** — config/JSON parsing (embedded)
- **PyTorch 2.10** — neural net training (with Intel Arc XPU support)
- **Node.js/Express** — command center dashboard (separate, not part of this plan)

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Prismata_GUI.exe (x86)                    │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │  Engine   │  │    AI    │  │   GUI    │  │  Testing   │ │
│  │ GameState │  │ AlphaBeta│  │ SFML 2D  │  │ Tournament │ │
│  │ Card/Type │  │ UCT/MCTS │  │ GUIState │  │ SelfPlay   │ │
│  │ Resources │  │ NeuralNet│  │ GUICard  │  │ ReplayStep │ │
│  │ Action    │  │ Heuristic│  │ GUITools │  │ DataSink   │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
│        ↑              ↑             ↑                       │
│        └──────────────┴─────────────┘                       │
│              All modules share GameState                    │
└─────────────────────────────────────────────────────────────┘
         ↕ binary weight file
┌─────────────────────────────────────────────────────────────┐
│              Training Pipeline (Python)                      │
│  train.py → export_weights.py → neural_weights.bin          │
│  load_selfplay.py (binary shard reader)                     │
│  Self-play data: 722K games, 26.7M records, 178 GB in S3   │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **PartialPlayer phase decomposition** — AI breaks each turn into phases (Defense, Ability, Buy, Breach) with separate strategies per phase. This reduces branching factor from ~10^6 to ~5 per phase.

2. **Neural net as leaf evaluator** — The neural net doesn't generate moves. It evaluates leaf positions in Alpha-Beta/UCT search trees. Moves are generated by heuristic PartialPlayers. This is deliberate — the policy head is too weak (13.3% accuracy) to guide search.

3. **Value-only training** — Current model trains only the value head. Policy head weights are exported as zeros. This means any policy-dependent GUI features will show no signal until policy training is added.

4. **Self-play uses playout eval, not neural** — Game generation uses `OriginalHardestAI` (heuristic playout evaluation, 1s think time). The neural net only labels positions for training. Data quality depends on playout AI strength.

5. **Engine has zero GUI dependencies** — Engine compiles independently from SFML. GUI is a thin layer (~4.5K LOC) that renders GameState.

---

## 4. Codebase Map

### Directory Structure
```
PrismataAI/
├── source/
│   ├── ai/           18K LOC — AI players, search, neural net, heuristics, eval
│   ├── engine/        8K LOC — GameState, Card, CardType, Resources, Actions
│   ├── gui/          4.5K LOC — SFML rendering, play state, menu, watch modes
│   ├── testing/      5.8K LOC — Tournament runner, self-play, replay stepper
│   ├── standalone/    180 LOC — Console tournament runner (no GUI)
│   └── rapidjson/    (embedded library, not counted)
├── training/         6K LOC Python — train.py, load_selfplay.py, export_weights.py
├── tools/            Python tools — sniffer, advisor, autopilot, commentator
├── bin/              Executables + config + data
│   └── asset/config/ — config.txt, cardLibrary.jso, neural_weights.bin
├── aws/              Cloud launch scripts, TheWatcher monitor
├── gcp/              GCP launch scripts
├── azure/            Azure launch scripts (paused)
├── dashboard/        Node.js command center (not part of this plan)
├── visualstudio/     VS solution + project files
└── docs/             Plans, history, reference docs
```

### Files Relevant to the Plan

| File | LOC | Role in Plan |
|------|-----|-------------|
| `source/gui/GUIState_Play.h` | 117 | Primary modification target — add data members |
| `source/gui/GUIState_Play.cpp` | ~1200 | Primary modification target — rendering, input, AI calls |
| `source/gui/GUIState_WatchTraining.h` | 157 | Threading pattern to copy (StateQueue, worker threads) |
| `source/gui/GUITools.h` | 24 | Drawing primitive declarations |
| `source/gui/GUITools.cpp` | 426 | Drawing primitive implementations |
| `source/gui/GUIState_Menu.cpp` | ~450 | One hardcoded player name to rename |
| `source/ai/NeuralNet.h` | ~90 | NeuralOutput struct, evaluate() API |
| `source/ai/NeuralNet.cpp` | ~600 | Neural evaluation implementation |
| `source/ai/Eval.cpp` | ~80 | WillScore and NeuralNet evaluation wrappers |
| `source/ai/Heuristics.cpp` | ~310 | Card value heuristics (H: display values) |
| `source/ai/AIParameters.cpp` | ~300 | Player name registry (parses config.txt) |
| `source/engine/GameState.h` | ~200 | Resource access, card iteration |
| `source/engine/GameState.cpp` | ~1300 | beginTurn() — resource production logic |
| `source/testing/main.cpp` | ~150 | One hardcoded player name to rename |
| `bin/asset/config/config.txt` | ~300 | AI player definitions, tournament configs |
| `training/export_weights.py` | ~280 | Exports zero policy for value-only models |

### Total Scale
- **C++ source:** ~36K LOC across 296 files
- **Python training:** ~6K LOC
- **Python tools:** ~3K LOC
- **Config/data:** cardLibrary.jso (~7K lines, 105 units), config.txt (~300 lines)

---

## 5. Relevant Existing Patterns & Conventions

### C++ Conventions
- **Allman brace style**, 4-space indent, 120 column limit (`.clang-format` at project root)
- Member variables prefixed with `m_` (GUI) or `_` (AI/engine)
- `PlayerID` is `int` (0 or 1). `CardID` is `int`. `CardType` wraps an ID.
- Singletons: `NeuralNet::Instance()`, `HeuristicValues::Instance()`, `AIParameters::Instance()`
- Soft asserts: `PRISMATA_ASSERT` prints to stdout but does NOT abort

### GUI Patterns
- **Game loop:** `onFrame()` → `update()` → `sRender()` → `sUserInput()` at 60 FPS
- **Rendering:** All drawing in `sRender()` → `drawInterface()`, `drawCards()`, `drawInformation()`, `drawDebugInfo()`, etc. No retained-mode scene graph — immediate mode each frame.
- **State history:** `m_stateHistory` vector for undo (Z key). Push on every `doGUIAction()`.
- **AI move execution:** `runAutoPlay()` is synchronous — blocks GUI during AI think time (~7s). `m_doingAIMove` flag blocks input during animation.
- **Debug toggle:** `m_drawDebugInfo` toggled by `#`/`~`/`` ` `` key. All debug rendering gated on this flag.
- **Coordinate system:** Origin top-left, Y increases downward (standard SFML). Window 2133x1200px. Board split at y=600.

### Threading Pattern (from GUIState_WatchTraining)
```cpp
class StateQueue {                          // Thread-safe queue
    std::queue<GameState> m_queue;
    std::mutex m_mutex;
public:
    void push(const GameState & state);     // Lock + push
    bool tryPop(GameState & out);           // Lock + try pop
};
// Workers: std::vector<std::thread> m_workerThreads
// Stop: std::atomic<bool> m_stopRequested
// Each worker gets its own GameState copy — no shared mutable state
```

### Config
- All AI player names are defined in `config.txt` as JSON objects and parsed dynamically by `AIParameters.cpp`
- Only 2 hardcoded player name references in C++ source (main.cpp:98, GUIState_Menu.cpp:416)
- Neural net weights loaded from `bin/asset/config/neural_weights.bin` at startup. Hidden dim and layer count read from file header — no rebuild needed to swap architectures.

### Testing
- No unit test framework. Testing is via tournament evaluation (thousands of games, win rate measurement).
- Build: Visual Studio 2022 solution, x86 only. `MSBuild /t:Rebuild /p:Configuration=Release /p:Platform=x86`
- Three executables: Prismata_GUI (interactive), Prismata_Testing (tournaments), Prismata_Standalone (headless)

---

## 6. Current State & Known Issues

### What Works Today
- **GUI interactive play:** Human can play against any AI via in-game menu (Return key). Works with both neural and heuristic AIs.
- **Debug panel (#):** Shows per-player Will Score, AI eval/buy notation, comparison AI results, AI parameters. Renders H: (heuristic card cost) and N: (neural policy) labels on buyable cards.
- **Neural AI at 45.3% WR** vs strongest heuristic (OriginalHardestAI) over 4,032 games. Significant milestone.
- **Self-play pipeline:** 722K games generated across multi-cloud fleet. Training pipeline proven.
- **Watch Training/Eval modes:** Automated AI-vs-AI with live visualization and threaded game generation.

### Known Issues Relevant to the Plan

1. **Policy head is zero-initialized** — Current 305K model is value-only. `export_weights.py` writes all-zero policy weights. GUI shows uniform N: percentages for all affordable units. This is not a code bug but is misleading to users. **Plan Phase 1A addresses this.**

2. **H: values are static** — `GetInflatedTotalCostValue()` returns precomputed per-CardType costs, not dynamic per-state evaluations. They correctly show the same value every turn. Not a bug, but users may expect dynamic values.

3. **GUI blocks during AI think** — `runAutoPlay()` is synchronous. With 7s think time + 7s comparison AI, the GUI freezes for ~14s per AI turn. **Plan Phase 4 addresses this with threading.**

4. **No resource prediction** — The engine has no built-in "gold next turn" API. Resource production happens via `BeginOwnTurnScript` execution during `beginTurn()`. Calculating predicted income requires iterating cards and checking production scripts. **Plan Phase 1B addresses this.**

5. **GameState is NOT thread-safe** — No mutexes, no atomics. Safe for concurrent reads of separate copies. Must deep-copy before passing to worker threads. The existing `GUIState_WatchTraining` pattern handles this correctly.

6. **x86 memory limit** — 4GB address space with `/LARGEADDRESSAWARE`. Self-play processes die at ~1400 games. GUI is lighter but adding many concurrent AI evaluations could stress memory. Each `GameState` copy is relatively small (~few KB), but AI search trees can consume significant memory.

7. **NeuralNet::Instance() thread safety** — `evaluate()` is const and allocates vectors locally. Likely thread-safe for concurrent reads. However, this has NOT been stress-tested with multiple threads calling evaluate() simultaneously. The plan should verify this.

### Recent Significant Changes
- **Replay ingestion** (Feb 21) — New `ReplayStepper` class converts replay click sequences to GameState transitions. 96.6% extraction rate. On feature branch `feature/cpp-replay-stepper`.
- **Live commentator** (Feb 20) — Claude Haiku generates per-turn commentary injected as in-game chat.
- **Sniffer/autopilot** (Feb 20) — TCP proxy for live game state capture and move injection.
- **305K model trained** (Feb 18) — Major win rate jump from 26.7% to 45.3% with 5x more data.

---

## 7. Context Specific to the Plan

### What the Plan Touches

The plan modifies primarily **2 files** (`GUIState_Play.h/cpp`) with minor changes to config files and a handful of source references. It does NOT modify the engine, AI search, neural net, or training pipeline.

| Plan Phase | Files Modified | Risk |
|-----------|----------------|------|
| Phase 1 (policy fix + gold) | GUIState_Play.cpp | Low — display-only changes |
| Phase 2 (human AI advice) | GUIState_Play.h/cpp | Medium — adds AI calls during human turn |
| Phase 3 (eval bars) | GUIState_Play.h/cpp, possibly GUITools | Medium — new rendering |
| Phase 4 (parallel eval) | GUIState_Play.h/cpp | Higher — introduces threading to GUI |
| Phase 5 (eval graph) | GUIState_Play.h/cpp | Medium — new rendering + data collection |
| Phase 6 (naming) | config.txt, main.cpp, GUIState_Menu.cpp, tools, scripts | Low — string replacements |
| Phase 7 (extras) | GUIState_Play.cpp | Low — future ideas |

### Prior Attempts / Rejected Approaches

- **Blend tournaments** (neural + playout weighted eval) — Concluded that neural component hurts at current accuracy. Don't revisit until model >60% val accuracy.
- **PUCT move ordering** — Implemented in UCT search but disabled (`"UsePUCT": false`) because policy head is too weak (13.3%). Plan Phase 1A's value-only detection relates to this — policy display is useless until policy training happens.

### Performance Considerations

- **Neural eval:** ~0.5ms per call, ~2,000 evals/sec/core. Safe for per-click WillScore bar updates. Safe for per-turn neural eval bar updates. NOT safe for per-frame neural eval (60 FPS × 0.5ms = 30ms/frame = too much).
- **AI search:** 7 seconds per move at default think time. Running 3 AIs in parallel = 3 threads × 7s = 7s wall time (vs 21s sequential). Memory: each search tree consumes ~50-200MB depending on game complexity.
- **x86 memory budget:** ~3.5GB usable after OS overhead. GUI itself uses ~300-400MB. Three concurrent AI searches could consume ~600MB additional. Should be safe but worth monitoring.

### External Dependencies
- **SFML 2.6.2** — only dependency for GUI rendering. Located at `c:\libraries\sfml\`. Statically linked in Release builds.
- **No external charting library** — eval graph must be rendered manually with DrawLine/DrawRect primitives.
- **No GUI framework** — everything is immediate-mode SFML drawing. No widgets, no layout system, no text input boxes.

---

## 8. Scope Boundaries

### Out of Scope

- **Engine/AI algorithm changes** — This plan modifies only GUI rendering and threading. No changes to search algorithms, evaluation functions, neural net architecture, or game logic.
- **Training pipeline changes** — No modifications to train.py, export_weights.py, or the self-play data format. Policy training is a separate future project.
- **Web/mobile GUI** — SFML doesn't support WASM. Any future web port requires a separate abstraction effort.
- **Live commentator / sniffer / autopilot integration** — Those are separate Python tools. This plan focuses on the C++ GUI only.
- **New AI players** — No new AI configurations are being created. Existing players are reused.

### Fixed & Non-Negotiable

- **x86 only** — The entire build chain is x86. Do not suggest x64 migration.
- **SFML for rendering** — No framework switches. All new UI must use existing SFML drawing primitives.
- **Value-only model for now** — Policy head training is a separate track. The plan must work correctly with zero-policy weights.
- **config.txt player names** — Renaming `PrismatAlpha_AB` etc. in config.txt must preserve backward compatibility (games referencing old names in logs/replays).
- **Solo developer** — No team coordination overhead. Changes can be made incrementally and tested manually.

### Accepted Trade-offs

- **No retained-mode GUI** — Immediate-mode SFML drawing means no layout engine, no widget library. Custom positioning for every element.
- **Eval bars are approximate** — Neural eval [-1, +1] is a learned estimate, not ground truth. WillScore is a crude material heuristic. Bars will show AI's opinion, not objective advantage.
- **Threading adds complexity** — Parallel eval introduces thread management to a previously single-threaded GUI. Accepted because sequential 21s freezes are unacceptable for interactive use.

---

## 9. Success Criteria

### Must-Have (plan fails without these)
- Debug panel correctly shows "(value-only model)" when policy weights are zeros, instead of misleading N: percentages
- Gold prediction displays expected gold next turn for both players, reasonably accurate for standard Drone economies
- At least one eval bar (neural or WillScore) renders and updates after AI moves
- AI move computation no longer freezes the GUI (threading works)
- Build succeeds in Release|x86 with no new warnings

### Should-Have
- Human-side AI buy recommendations display correctly when debug mode is on
- Both neural and WillScore eval bars render simultaneously
- Eval bar updates after human confirms action phase (first space press)
- PrismatAlpha → PrismatAI naming consolidation complete in source code

### Nice-to-Have
- Per-click WillScore bar updates (responsive, not too hectic)
- Eval history graph showing progression over the game
- Multiple AI evaluations run in true parallel (not just AI + comparison)

### Performance Targets
- Neural eval call: <1ms (currently ~0.5ms — must not regress)
- GUI frame rate: stays at 60 FPS during rendering (no per-frame AI calls)
- AI think time perceived as same or faster (parallel should mask, not add latency)
- Memory usage: GUI stays under 1.5GB including concurrent AI searches (x86 headroom)

---

## 10. Key Questions for Reviewers

1. **Threading granularity (Phase 4):** The plan proposes moving all AI evaluation to background threads with a result queue. Is there a simpler approach that achieves "GUI doesn't freeze" without full thread management? For example, would a single background thread + future/promise pattern be sufficient, or is the multi-thread queue worth the complexity?

2. **Eval bar design (Phase 3):** The plan proposes both a neural eval bar and a WillScore bar. Chess engines typically show ONE eval bar. Is showing two bars confusing to users, or is the comparison between learned (neural) and heuristic (WillScore) evaluations genuinely useful for AI development analysis? Should one be the default and the other opt-in?

3. **Per-click WillScore updates (Phase 3):** The plan considers updating the WillScore bar after every click/buy action. This gives immediate feedback but could be visually distracting. Is this actually useful for gameplay analysis, or would updating only at phase boundaries (action → defense → swoosh) be better?

4. **Phase ordering (1→6→3→2→4→5):** The plan recommends doing naming consolidation (Phase 6) before eval bars (Phase 3) and human AI advice (Phase 2). Is this ordering optimal? A reviewer might argue that user-facing features should come before cosmetic renaming.

5. **NeuralNet thread safety (Phase 4):** The context notes that `NeuralNet::Instance().evaluate()` is "likely thread-safe" but untested with concurrent callers. What's the appropriate level of verification before shipping? Should the plan include an explicit stress test, or is a mutex wrapper around evaluate() the safer choice even if it serializes calls?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|------|-----------|
| **Prismata** | Turn-based perfect-information strategy card game. Two players build economies and armies. No randomness, no hidden information. |
| **GameState** | C++ class representing the complete state of a Prismata game at a point in time. ~few KB per instance. |
| **Action** | A single game action: BUY a card, USE_ABILITY, ASSIGN_BLOCKER, END_PHASE, etc. |
| **Move** | A sequence of Actions comprising one player's full turn. |
| **Phase** | Turns have phases: Action (buy/ability), Defense (assign blockers), Breach (assign damage to enemy). |
| **PartialPlayer** | AI strategy for a single phase (e.g., GreedyKnapsack for buying). Combined into full-turn players. |
| **Alpha-Beta** | Minimax search with pruning. Used by `Player_StackAlphaBeta`. Deterministic. |
| **UCT/MCTS** | Monte Carlo Tree Search with Upper Confidence bounds. Used by `Player_UCT`. Stochastic. |
| **Playout eval** | Evaluate a position by playing random games to completion and counting wins. Slow but strong signal. |
| **WillScore** | Heuristic material evaluation. Sums card costs using resource weights (Attack=2.25, Gold=1.00, etc.). Fast but crude. |
| **Neural eval** | Neural network value head output. [-1, +1] win probability. ~0.5ms per call. |
| **Policy head** | Neural network output predicting which units to buy. Currently zero-initialized (value-only model). |
| **Value head** | Neural network output predicting win probability from a position. This is the useful part. |
| **H: value** | Heuristic Inflated Total Cost — static per-unit-type cost in gold-equivalent. Displayed in yellow next to buyable cards. |
| **N: value** | Neural policy logit + softmax percentage. Displayed in blue next to buyable cards. Currently meaningless (zero weights). |
| **OriginalHardestAI** | Strongest heuristic AI (playout eval, 7s think). The baseline opponent. |
| **PrismatAlpha / PrismatAI** | The neural-network-powered AI. Being renamed from PrismatAlpha to PrismatAI for consistency. |
| **Self-play** | AI plays against itself to generate training data. 722K games generated so far. |
| **Shard** | Binary file containing self-play training records. 64-byte header + N×7152-byte records + 4-byte CRC. |
| **cardLibrary.jso** | Master unit definition file (105 playable units + 11 base units). Uses internal codenames (e.g., "Tesla Tower" = Tarsier). |
| **config.txt** | JSON config defining all AI players, tournament setups, and game parameters. |
| **TheWatcher** | Persistent PowerShell monitor (Task Scheduler, every 5 min) managing cloud fleet auto-relaunch. |
| **F6** | Keyboard shortcut in the Prismata client that copies game state JSON to clipboard. Used for live analysis. |
| **Buy pane** | Left panel (200px wide) in the GUI showing purchasable cards. |
| **Debug panel** | Right-side overlay (#/~ toggle) showing AI eval, WillScore, buy notation, and neural policy values. |
| **Eval bar** | Proposed chess-style vertical bar showing who's ahead. Similar to the bar in chess.com or Lichess broadcasts. |
| **SFML** | Simple and Fast Multimedia Library. 2D rendering framework used for the GUI. |
