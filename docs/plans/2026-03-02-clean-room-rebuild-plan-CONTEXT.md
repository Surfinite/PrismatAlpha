# Clean Room Rebuild — External Review Context Document

## 1. Reviewer Brief

You are receiving two documents:
1. **This context document** — everything you need to understand the project and situation.
2. **A plan** (`zesty-meandering-mitten.md`) — a 7-phase "clean room rebuild" of a game AI system.

**Your role:** Critically analyze the plan given this context. You should identify:
- Weaknesses, risks, and missing considerations
- Better alternatives or unnecessary complexity
- Things that should be removed and things that should be preserved
- Additions, potential future features, and architectural improvements

Be constructively critical — not rubber-stamping. Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable.

**Important:** You do NOT have direct access to the codebase. You're working from this context document only. The plan author has full codebase access and will validate all suggestions against actual code during the meta-review. Flag where you feel uncertain and note assumptions you're making.

### Review Output Format

1. **One-line verdict**: Overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility and had to guess.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

**PrismataAI** is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The game has ~116 unit types, resource management, attack/defense phases, and deep strategic complexity comparable to chess.

The project forks Dave Churchill's academic C++ Prismata AI engine and extends it with:
- Neural network evaluation (ResNet, 1785-dim state vectors)
- AS3→JS engine transpilation (for faithful game state simulation)
- Training pipeline (PyTorch, self-play data, expert replays)
- Cloud infrastructure (AWS/GCP/Azure for self-play and training)
- A matchup framework for AI-vs-AI evaluation

**Current stage:** Active development by a single developer. The core engine and neural net are functional. The JS transpilation is validated. But the integration layer (matchup framework connecting C++ AI to JS game engine) has accumulated bugs from incremental patches, eroding confidence in the entire system.

**The problem prompting this plan:** Multiple bugs discovered simultaneously — every unit having supply=20 (should vary by rarity: legendary=1, rare=4, normal=20), color-specific game deadlocks, undefined property crashes. Rather than debug forward through unknown layers of broken fixes, the developer chose to start from known-good baselines and rebuild selectively.

**Key constraints:**
- **Single developer** (Surfinite) — no team, no code review pipeline
- **Cost-conscious** — AWS bill shock ($805 for 4 days). Prefer local compute.
- **x86 only** — C++ engine is 32-bit, max 4GB address space
- **Windows primary** — development on Windows 11, Git Bash shell
- **No live game server access** — Prismata servers are legacy (Adobe AIR/Flash)

---

## 3. Architecture & Tech Stack

### Languages & Frameworks
- **C++ (C++17)** — Game engine, AI search (Alpha-Beta, UCT/MCTS), neural net inference
- **JavaScript (Node.js ≥16)** — Transpiled game engine (from ActionScript 3), self-play integration
- **Python 3** — Training pipeline (PyTorch), data processing
- **Visual Studio 2025** — Build system (MSBuild, x86 only)

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MATCHUP FRAMEWORK (JS)                    │
│  matchup_main.js — orchestrates AI-vs-AI games              │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │ JS Engine    │    │ C++ --suggest │    │ MCDSAI Binary │  │
│  │ (game truth) │◄──►│ (AI brain)   │    │ (opponent AI) │  │
│  │ from AS3     │    │ via CLI JSON  │    │ via workers   │  │
│  └──────────────┘    └──────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────┐      ┌──────────────┐     ┌──────────────┐
  │ Replays  │      │ Neural Net   │     │ Emscripten   │
  │ (JSON)   │      │ Weights .bin │     │ MCDSAI3441.js│
  └──────────┘      └──────────────┘     └──────────────┘
```

**Key architectural decision:** The plan establishes a new principle: **"C++ = AI brain, JS = game truth."** The C++ engine evaluates positions for AI search but doesn't need to perfectly simulate games. The JS engine (faithful AS3 transpilation) is the ground truth for game state transitions. This decoupling is new and central to the rebuild rationale.

### Data Flow for a Matchup Game
1. JS engine initializes game state (card set, supplies, init deck)
2. For each player's turn: export JS state → JSON file → C++ `--suggest` reads it → AI search → outputs clicks JSON
3. JS engine applies clicks via `analyzer.recordClick()` to advance game state
4. Repeat until game over
5. Save replay/results

### Build System
- Visual Studio solution with 5 projects:
  - `Prismata_Engine` (static lib) — 29 cpp, 30 h
  - `Prismata_AI` (static lib) — 65 cpp, 65 h
  - `Prismata_GUI` (exe) — SFML-based viewer
  - `Prismata_Testing` (exe) — tournaments + `--suggest` mode
  - `Prismata_Standalone` (exe) — console AI for live game integration
- x86 only: Debug, Release, Static Release configurations

---

## 4. Codebase Map

### Directory Structure (what matters)
```
PrismataAI/
├── source/
│   ├── engine/         # 58 files — GameState, Card, Action, Move, Script, etc.
│   ├── ai/             # 130 files — Players, Search, Eval, Heuristics, NeuralNet
│   ├── testing/        # 15 files — Benchmarks, Tournament, main.cpp
│   ├── gui/            # 19 files — SFML GUI (GUIState_Play, GUIState_Menu)
│   ├── standalone/     # 2 files — Console AI entry point
│   └── rapidjson/      # 21 files — Embedded JSON library
├── js_engine/          # 38 files — AS3→JS transpiled engine + integration
├── training/           # Python training pipeline (train.py, load_selfplay.py, etc.)
├── bin/asset/config/   # cardLibrary.jso, config.txt, neural_weights.bin
├── visualstudio/       # .sln + 5 .vcxproj files
├── aws/, gcp/, azure/  # Cloud launch/monitor scripts
├── docs/               # Plans, audits, strategy guides, commentary knowledge
└── tmp_swf_extract/    # Decompiled Prismata SWF AI parameters
```

### Scale
- **C++ source:** 296 files, ~48,600 lines
- **JS engine:** 38 files, ~13,450 lines
- **Total C++ changes from upstream:** 62 files, +9,373 / -309 lines (across 130+ commits)

### Key Files Referenced by the Plan
| File | Lines | Role |
|------|-------|------|
| `source/engine/GameState.cpp` | 2,957 | Core game logic (plan: DO NOT MODIFY) |
| `source/ai/NeuralNet.cpp` | 782 | Neural inference (plan: copy as new file) |
| `source/ai/AIParameters.cpp` | 1,137 | Config parsing (plan: add neural/live parsing) |
| `source/testing/Benchmarks.cpp` | 2,027 | Benchmarks + --suggest (plan: add DoSuggest only) |
| `source/ai/UCTSearch.cpp` | ~600 | MCTS search (plan: add PUCT + neural eval) |
| `js_engine/State.js` | 1,682 | JS game state machine (plan: copy from 99d39fe) |
| `js_engine/Controller.js` | 2,268 | JS click processing (plan: copy from 99d39fe) |
| `js_engine/card_library.js` | 321 | Card data loading (plan: copy from 99d39fe) |
| `bin/asset/config/cardLibrary.jso` | ~3,000+ | Master unit definitions (plan: verify 105 units) |
| `bin/asset/config/config.txt` | ~440 | AI player configs (plan: add LiveHardestAI) |

---

## 5. Relevant Existing Patterns & Conventions

### C++ Conventions
- `.clang-format` at project root: Allman braces, 4-space indent, 120 col limit
- `PRISMATA_ASSERT` is a soft assert (prints to stdout, does NOT abort)
- Namespace-based enums (e.g., `EvaluationMethods::Playout`)
- Singleton pattern for `AIParameters::Instance()`, `NeuralNet::Instance()`
- `PlayerPtr = std::shared_ptr<Player>` with virtual `getMove()` / `clone()`

### JS Engine Conventions
- CommonJS modules (`require`/`module.exports`), zero npm dependencies
- Constants in `C.js` (~150+ game constants)
- Click data uses underscore-prefixed keys: `_type`, `_id` (not `.type`, `.id`)
- State machine follows AS3 source faithfully (same variable names, same logic flow)

### Config Management
- `config.txt` — JSON-based AI player definitions, tournament configs
- `cardLibrary.jso` — unit definitions with internal codenames (e.g., "Tesla Tower" = Tarsier)
- Neural weights — custom binary format with magic header, dynamic hidden_dim/num_layers

### Testing
- JS engine: 5 test files (`test_state.js`, `test_phase3.js`, `test_tier1.js`, `test_tier2.js`, `test_selfplay.js`)
- JS replay validation: `replay_validator.js` downloads replays from S3, replays through engine (100% pass on 500 replays at commit `99d39fe`)
- C++ testing: Tournament-based evaluation (round-robin with result tables)
- No formal unit test framework (no gtest, no catch2)

### Error Handling
- C++ uses `PRISMATA_ASSERT` (non-fatal) for internal checks
- JS uses `C.ASSERT()` function (throws on failure in tests, logs in production)
- MCDSAI responses need control character stripping (`[\x00-\x1f]`) before JSON parsing

---

## 6. Current State & Known Issues

### What Works Today
- C++ game engine simulates Prismata games correctly for AI search (with known minor bugs)
- Neural net inference: ~2,000 evals/sec/core, ResNet architecture
- `--suggest` CLI mode: accepts F6 game state JSON, outputs AI move as JSON
- JS transpiled engine: 100% replay validation on 500 replays (at commit `99d39fe`)
- Training pipeline: PyTorch, streaming data loader, XPU acceleration
- Self-play data generation: ~722K games in S3

### Known Technical Debt & Bugs (Triggering This Rebuild)
1. **Supply bug**: Every unit gets supply=20 because `card.supply` doesn't exist on mergedDeck entries — code defaults to 20 instead of using rarity-based mapping
2. **Color-specific deadlock**: MCDSAI-as-White games deadlock after 50+ turns; Black games complete normally
3. **JS engine crashes**: undefined property errors for `defaultBlocking` and `startingHealth` during complex AI games
4. **Shift-click expansion bugs**: DoSuggest's expansion of shift-flagged actions into multiple clicks was producing incorrect results
5. **C++ engine has known divergences from AS3**: defense-reset bug, missing stagnation detection, missing death scripts (these are NOT being fixed in this plan — JS engine is ground truth)

### Recent Significant Changes (Last 5 Commits on Working Branch)
1. `c16d5f9` — Document DetailedReplays feature
2. `8f3e619` — Fix C++ --suggest missing commit click, JS card name bugs, matchup framework improvements (THIS commit introduced/attempted to fix several of the problematic areas)
3. `929e395` — CLAUDE.md updates
4. `e6a3cfe` — Cloud config parameterization
5. `4ab0b98` — Pre-public repo cleanup

---

## 7. Context Specific to the Plan

### What the Plan Touches
- **C++ AI layer** (Phases 2-3): Adding NeuralNet, PUCT search, --suggest mode on top of Churchill's clean baseline
- **Config files** (Phase 4): cardLibrary.jso unit definitions — must match live game exactly
- **JS engine** (Phase 5): Snapshot from validated commit, no modifications
- **Integration layer** (Phase 7): Complete rewrite of matchup framework from scratch

### Prior Attempts & Why They Failed
The current state represents ~130 commits of incremental development. The matchup framework was built by layering:
1. Initial selfplay_main.js (Phase 4 of transpilation) — this worked
2. matchup_main.js added for AI-vs-AI evaluation — introduced bugs
3. suggest_adapter.js for C++ → JS click translation — complex, fragile
4. Shift-click expansion in DoSuggest — attempted to handle multi-instance abilities, introduced more bugs
5. Card name translation fixes — fixing display name ↔ internal name mapping caused UIName corruption
6. Stuck detection threshold changes — changed from 3 to 30, masking real issues

Each fix addressed a visible symptom but introduced subtle new issues. The "supply=20 for all units" bug went unnoticed because it was in code that *looked* correct (`card.supply !== undefined ? card.supply : 20`) but the field simply doesn't exist on the data structure being accessed.

### Dependencies & External Systems
- **play.prismata.net**: Source for fresh MCDSAI binary (Emscripten-compiled AI). Game servers are legacy — may not be permanently available.
- **S3 replay storage**: `saved-games-alpha.s3-website-us-east-1.amazonaws.com` — used for replay validation
- **SWF-extracted AI parameters**: `tmp_swf_extract/` contains AI params decompiled from Prismata.swf using JPEXS FFDec. These define HardestAI behavior in the live game.
- **Prismata Steam installation**: `C:\Program Files (x86)\Steam\steamapps\common\Prismata` — card images, game data reference

### Performance Considerations
- C++ AI search: 7-second default think time for HardestAI
- Neural net: ~2,000 evals/sec/core (x86, no GPU in C++)
- x86 address space: 4GB max with LARGEADDRESSAWARE, max 4 threads per process
- Matchup games: each takes 1-5 minutes depending on think time

---

## 8. Scope Boundaries

### Explicitly Out of Scope
| Item | Reason |
|------|--------|
| Dashboard (Node.js web UI) | Monitoring tool, not core functionality |
| Sniffer/advisor/autopilot tools | Local-only tools for live game integration |
| Commentary pipeline | Separate feature, not dependent on engine correctness |
| GUI enhancements (eval bar, graphs, resolution) | User explicitly excluded — wants baseline GUI |
| C++ engine bug fixes (defense-reset, stagnation, death scripts) | JS engine is ground truth; C++ bugs only affect search quality |
| Self-play data generation improvements | Separate concern, future work |

### Fixed, Non-Negotiable Decisions
- **Start from `origin/master`** — Churchill's untouched upstream. Do not suggest starting from a midpoint.
- **JS engine from commit `99d39fe`** — 100% validated. Do not suggest modifications to core engine modules.
- **105 units from live game screenshots** — authoritative source. Do not suggest alternative unit lists.
- **No `debugStateHash()`** — depends on stagnation infrastructure which is excluded.
- **x86 only** — hardware/toolchain constraint, not changeable.

### Accepted Trade-offs
- C++ engine has known bugs (defense-reset, missing stagnation) — accepted because JS engine is ground truth for game state
- No shift-click expansion in DoSuggest — simpler but may need JS-side handling
- No GUI enhancements — functionality loss accepted for confidence gain
- NeuralNet policy head unused (13.3% accuracy) — value-only evaluation for now

---

## 9. Success Criteria

### Per-Phase Success
| Phase | Success Criterion |
|-------|-------------------|
| 1 | MSBuild compiles clean from origin/master + PlatformToolset update |
| 2 | Neural weights load, tournament runs with LiveHardestAI |
| 3 | `--suggest state.json` produces valid JSON with correct click array |
| 4 | Exactly 105 additional units, all matching live game, tournament runs |
| 5 | 100% replay validation on 500 replays (matching original validation) |
| 6 | MCDSAI starts, accepts state, returns valid move |
| 7 | AI-vs-AI matchup games complete with correct supply values and plausible results |

### Overall Success
- Can run MCDSAI vs OriginalHardestAI matchups that complete without crashes
- Supply values are correct (legendary=1, rare=4, normal/trinket=20)
- No color-specific deadlocks
- No undefined property errors
- Replays from matchup games are viewable and make sense
- Confidence to build on top of this baseline without fear of hidden bugs

---

## 10. Key Questions for Reviewers

1. **Phase 2 scope**: The plan bundles NeuralNet (Layer 1) and full AI search integration including PUCT/UCT changes (Layer 2) into one phase. UCTSearch.cpp alone has 218 lines of changes including a return type change on `traverse()`. Is this too much for one phase? Should Layer 2 be split further?

2. **Removing shift-click expansion from DoSuggest**: The plan removes the buggy shift-click expansion from C++ and says "let JS engine handle it." But the plan doesn't specify HOW the JS engine will handle multi-instance abilities (e.g., activating 6 Drones). Is this a gap that needs addressing in Phase 7?

3. **MCDSAI binary availability**: The plan depends on downloading MCDSAI from play.prismata.net. Prismata is a legacy game with declining infrastructure. What's the fallback if the binary is no longer available? Is the existing copy on disk sufficient?

4. **Phase 7 sub-phase granularity**: The matchup rewrite (Phase 7) is where all previous bugs lived. The plan has 5 sub-phases but they're described at a high level. Does this phase need more detailed specification, or is the incremental "test at every step" approach sufficient?

5. **cardLibrary.jso diff approach**: Phase 4 says to diff origin/master's cardLibrary against master's. But if Churchill's original already had some units, and our changes modified existing entries (not just added new ones), how do we handle modified-but-not-new entries? Should we use origin/master's definitions verbatim for units that existed upstream?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|------|------------|
| **Prismata** | Turn-based perfect-information strategy card game by Lunarch Studios |
| **Unit** | A card type in the game (e.g., Tarsier, Drone, Wall). ~116 total. |
| **Supply** | How many copies of a unit can be purchased. Varies by rarity: legendary=1, rare=4, normal/trinket=20 |
| **mergedDeck** | The combined deck of all available units for a game (base set + random units) |
| **cardLibrary.jso** | Master JSON file defining all unit types, their costs, abilities, scripts |
| **Internal name / codename** | Engine's name for a unit (e.g., "Tesla Tower" for Tarsier, "Brooder" for Blastforge) |
| **UIName / display name** | Human-readable name shown in the game UI (e.g., "Tarsier", "Blastforge") |
| **HardestAI** | Churchill's strongest AI player — Stack Alpha-Beta search with playout evaluation |
| **OriginalHardestAI** | Preserved copy of Churchill's original HardestAI config (legacy baseline) |
| **LiveHardestAI** | Configuration extracted from Prismata.swf matching the actual live game AI |
| **MCDSAI** | Lunarch Studios' AI (compiled to Emscripten/WASM), used as opponent in matchups |
| **PartialPlayer** | AI decomposition: Defense → ActionAbility → ActionBuy → Breach phases |
| **PUCT** | Predictor + Upper Confidence Bound for Trees — neural-guided MCTS selection |
| **--suggest mode** | CLI mode where C++ exe reads game state JSON, runs AI search, outputs move as JSON |
| **F6 JSON** | Game state exported via F6 key in Prismata client (clipboard). Wrapper key: `CurrentInfo` |
| **Shift-click** | Game mechanic: clicking with shift activates ability on ALL matching card instances |
| **Click** | Protocol-level action: `{_type: "card clicked"/"inst clicked"/"space clicked", _id: <int>}` |
| **Replay validation** | Running a replay's commands through the engine and checking the final state matches |
| **AS3** | ActionScript 3 — original Prismata game engine language (Adobe Flash/AIR) |
| **origin/master** | Dave Churchill's upstream repository (untouched, dormant) |
| **99d39fe** | Git commit where JS transpilation achieved 100% replay validation (our JS baseline) |
| **Will Score** | Heuristic evaluation: sums material value using fixed resource prices |
| **Playout** | Evaluation by simulating random games to completion and counting wins |
| **Neural eval** | Evaluation using trained neural network (ResNet, value head outputs win probability) |
| **Self-play** | AI playing against itself to generate training data |
| **Shard** | Binary file containing self-play training records (7,152 bytes per record) |
