# Context Document: AS3 Faithful Port Implementation Plan

**Date:** February 23, 2026
**Plan file:** `docs/plans/as3-faithful-port-implementation-plan.md`
**Feasibility analysis:** `docs/plans/as3-faithful-port-feasibility.md`

---

## 1. Reviewer Brief

You are receiving **two documents** alongside this context:
1. **This context document** — everything you need to understand the project, codebase, and constraints
2. **The implementation plan** — a 6-phase plan for rewriting C++ game engine internals to match decompiled ActionScript 3 (AS3) source code

Your role is to **critically analyze** the plan given the context provided. Specifically:
- Identify weaknesses, risks, missing considerations, and better alternatives
- Flag unnecessary complexity or things that should be removed
- Suggest additions, potential improvements, and architectural refinements
- Highlight things that are good and should be preserved
- Be constructively critical — the goal is to improve the plan, not rubber-stamp it

**Important**: You do NOT have direct access to the codebase. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making.

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
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

### What It Is
**PrismataAI** is a C++ game engine and AI system for **Prismata**, a turn-based, perfect-information strategy card game by Lunarch Studios. The project includes:
- A complete game state simulator (engine)
- AI players using Alpha-Beta search, UCT/MCTS, and neural network evaluation
- A self-play data generation pipeline for training
- A neural network trained on self-play data (currently 51.9% win rate vs the baseline "HardestAI")
- Live game tools: advisor overlay, autopilot, sniffer proxy, AI commentator

### Current Stage
**Mature AI project in active development.** The engine was originally written as a C++ reimplementation of the game logic (by David Churchill, academic researcher), but was never directly ported from the game's source code. Over the past month, the project has grown significantly: neural network training pipeline, cloud self-play fleet (AWS/GCP/Azure), tournament evaluation infrastructure, and live game integration tools.

### The Problem
The C++ engine has **diverged from the actual game's logic** in multiple ways. An exhaustive engine logic audit (Feb 22-23) compared the C++ code against decompiled AS3 source from the live Prismata client and found:
- **4 bugs fixed** (defense phase status reset, all-units-doomed win condition, mutual elimination draw, wipeout fall-through)
- **6+ unfixed structural divergences** (script execution ordering, ability cost timing, snipe kill timing, stagnation detection system, death scripts, missing Condition types)
- After fixing the 4 bugs, **replay validation regressed** from 55.7% to 50.4% (engine became stricter, revealing more differences)
- **All 722,000 self-play training games** were generated with the defense reset bug

### The Goal
Rewrite the C++ engine **internals** as a faithful port of the AS3 source code, eliminating the entire class of divergence bugs. The public API (56 methods consumed by 91 files) remains unchanged. This gives us:
1. A correct engine for regenerating all training data
2. Near-100% replay compatibility (replays are the ground-truth test suite)
3. Accurate live game tools (advisor/autopilot depend on engine matching the real game)

### Constraints
- **Solo developer** (one person + AI assistants)
- **x86 only** — no x64 build configurations exist
- **No timeline pressure** — quality over speed
- **Data regeneration required regardless** — the 722K games need regeneration whether we port or not

---

## 3. Architecture & Tech Stack

### Languages & Build
- **C++17** (Visual Studio 2022/2025, x86 only)
- **Python** for training pipeline, tooling, and validation scripts
- **ActionScript 3** — the decompiled game source (read-only reference, not executed)

### High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│                  source/ai/ (17.6K LOC)         │
│  Alpha-Beta Search, UCT/MCTS, Neural Net Eval   │
│  PartialPlayer system, Heuristics, Move Ordering │
│       (32 files include GameState.h)             │
├─────────────────────────────────────────────────┤
│             PUBLIC API BOUNDARY                  │
│         56 methods, ~1,000+ call sites           │
├─────────────────────────────────────────────────┤
│              source/engine/ (8K LOC)             │  ← THIS IS WHAT CHANGES
│  GameState.cpp (2,443 lines) — game logic        │
│  Card.cpp (993 lines) — card instance mgmt       │
│  + 25 supporting files (types, data, scripts)    │
├─────────────────────────────────────────────────┤
│           source/testing/ (5.8K LOC)             │
│  Tournament runner, Self-play export, Replay     │
│       (4 files include GameState.h)              │
├─────────────────────────────────────────────────┤
│             source/gui/ (4.9K LOC)               │
│  SFML-based GUI, Watch Training mode             │
└─────────────────────────────────────────────────┘
         Total: ~46,900 LOC across 286 files

Ground Truth Reference:
┌─────────────────────────────────────────────────┐
│  prismata_decompiled/scripts/mcds/engine/        │
│  State.as (4,490 lines) — game state machine     │
│  Inst.as (504 lines) — card instances            │
│  Card.as (753 lines) — card type definitions     │
│  StateHelper.as (649 lines) — cached computations│
│  C.as (625 lines) — constants                    │
│            Total: 7,021 lines                    │
└─────────────────────────────────────────────────┘
```

### Key Architectural Decisions Already Made
1. **Public API is frozen** — 56 methods, zero signature changes. All AI/search/testing code is untouched.
2. **C++ data structures preserved** — flat arrays (CardData), Resources struct, enum-based phases. Performance-critical for AI search (thousands of state copies per second).
3. **No undo system** — C++ search uses full state copy (GameState copy constructor), not AS3-style forward/backward execution. This eliminates ~400 lines of AS3 undo code from scope.
4. **Campaign/mission systems skipped** — Objectives, triggers, tutorial modes, lane system. Only competitive PvP logic is ported. Eliminates ~1,160 lines (16.5% of AS3).

---

## 4. Codebase Map

### Directory Structure (relevant portions)
```
PrismataAI/
├── source/
│   ├── engine/         # 55 files, 8K LOC — THE PORT TARGET
│   │   ├── GameState.cpp/h    # Core: 2,443 + 162 lines
│   │   ├── Card.cpp/h         # Card instances: 993 + 148 lines
│   │   ├── CardType.cpp/h     # Card type definitions (read from cardLibrary)
│   │   ├── CardData.cpp/h     # Card container (ID allocation, player-indexed)
│   │   ├── Constants.h        # Enums: Phases, CardStatus, ActionTypes
│   │   ├── Action.h           # Action class + ActionTypes enum
│   │   ├── Script.h/ScriptEffect.h  # Script execution system
│   │   ├── Condition.cpp/h    # Card condition checking
│   │   └── ... (25 more supporting files)
│   ├── ai/             # 161 files, 17.6K LOC — UNTOUCHED
│   │   ├── StackAlphaBetaSearch.cpp  # AB search
│   │   ├── UCTSearch.cpp             # MCTS
│   │   ├── NeuralNet.cpp/h           # NN inference
│   │   ├── Eval.cpp                  # Evaluation (WillScore, Playout, NN)
│   │   ├── PartialPlayer*.cpp        # Phase decomposition system
│   │   └── ... (32 files include GameState.h)
│   ├── testing/        # 21 files, 5.8K LOC — UNTOUCHED
│   │   ├── Tournament.cpp            # Multi-threaded tournament runner
│   │   ├── TournamentGame.cpp        # Single game + self-play export
│   │   └── ReplayStepper.h           # Replay validation
│   └── gui/            # 19 files, 4.9K LOC — UNTOUCHED
│
├── prismata_decompiled/scripts/mcds/engine/  # AS3 reference (read-only)
│   ├── State.as        # 4,490 lines — game state machine
│   ├── Inst.as         # 504 lines — card instances
│   ├── Card.as         # 753 lines — card type defs
│   ├── StateHelper.as  # 649 lines — cached computed properties
│   └── C.as            # 625 lines — constants
│
├── bin/asset/config/
│   ├── config.txt              # AI player definitions, tournament configs
│   ├── cardLibrary.jso         # Master unit definitions (105+11 units)
│   └── neural_weights.bin      # Neural network weights
│
├── training/           # Python training pipeline
│   ├── train.py, load_selfplay.py, export_weights.py
│   ├── schema.json             # Feature schema (state_dim=1785)
│   └── fast_batch_validate.py  # Parallel C++ validation
│
├── tools/              # Python tooling
│   ├── replay_oracle.py (TO BE CREATED in Phase 1)
│   ├── feature_snapshot.py (TO BE CREATED)
│   └── legality_oracle.py (TO BE CREATED)
│
├── docs/audit/         # 16 audit finding documents
│   ├── AUDIT_SUMMARY.md
│   ├── A0-A5, B1-B8, C1-C5, P0 (phase analysis)
│   └── Phase3_5_cardLibrary_parity.md
│
└── docs/plans/         # Planning documents
    ├── as3-faithful-port-feasibility.md
    ├── as3-faithful-port-implementation-plan.md  ← THE PLAN
    └── engine-logic-audit-plan-v2.md
```

### Where The Important Logic Lives

**GameState.cpp** (2,443 lines) — the core target:
- `doAction()` (lines 549-809): Switch on 13 ActionTypes — BUY, USE_ABILITY, SNIPE, CHILL, ASSIGN_BLOCKER, ASSIGN_BREACH, ASSIGN_FRONTLINE, WIPEOUT, END_PHASE, SELL, UNDO_USE_ABILITY, UNDO_BREACH, CANCEL_USE_ABILITY
- `beginTurn()` (lines 1248-1309): Turn transition (swoosh) — currently two-pass (all card resets, then all scripts). Must become single-pass to match AS3.
- `beginPhase()` / `endPhase()` (lines 1289-1433): Phase transitions — Action → Defense → Breach → Confirm → Swoosh
- `calculateGameOver()` (lines 1438-1510): Win/draw/stagnation detection
- `isLegal()` (lines 189-545): Legal action validation (per-type checks)
- `generateLegalActions()` (lines 60-188): Legal action enumeration
- `runScript()` (lines 960-1050): Script execution (buy scripts, ability scripts, beginOwnTurn scripts)

**Card.cpp** (993 lines) — card instance management:
- `beginTurn()` (lines 574-643): Per-card turn reset (status, lifespan, delay, health regen)
- `useAbility()` (lines 775-800): Ability execution with cost deduction
- `takeDamage()`, `applyChill()`: Combat mechanics

---

## 5. Relevant Existing Patterns & Conventions

### Coding Conventions
- **Allman braces**, 4-space indent, 120-column limit (`.clang-format` at root)
- Member variables: `m_` prefix (e.g., `m_resources`, `m_cards`, `m_activePhase`)
- Enums in namespaces: `ActionTypes::BUY`, `Phases::Action`, `CardStatus::Default`
- Internal card names differ from display names (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). 105-unit mapping in `cardLibrary.jso`.

### Testing Strategy
- **No unit test framework** — tests are run via tournament games and replay validation
- **Replay validation** (`training/fast_batch_validate.py`): Replays recorded actions against C++ engine, checking legality. 2,127 Master Bot replays, currently 50.4% pass rate.
- **Tournament evaluation**: AI vs AI games with statistical analysis (Wilson CI, z-test)
- **Self-play data validation**: CRC checks, NaN/Inf checks, outcome consistency

### How Config Works
- `config.txt`: JSON-like format defining AI players, tournaments, and parameters
- `cardLibrary.jso`: JSON defining all 105+ game units (costs, scripts, abilities, stats)
- Neural net weights loaded from `neural_weights.bin` (binary format with header containing hidden_dim and num_layers)

### Patterns The Plan Must Respect
- **CardData container**: Manages card ID allocation, player-indexed storage, `removeKilledCards()`. The port must use this container, not AS3's Dictionary.
- **Script system**: `runScript(cardID, script, scriptType)` processes `ScriptEffect` arrays. Already exists but is incomplete relative to AS3.
- **Resources struct**: Indexed by resource type (`Resources::Gold`, `Resources::Attack`, etc.). Isomorphic to AS3's Mana class.
- **x86 memory constraints**: 4GB address space with `/LARGEADDRESSAWARE`. AI search copies GameState thousands of times per second. Any memory growth in GameState has outsized performance impact.

---

## 6. Current State & Known Issues

### What Works Today
- Game simulation runs, AI plays games, tournaments complete
- 722K self-play games generated (178 GB in S3)
- Neural net at 51.9% WR vs baseline AI (first to cross 50%)
- Live game tools (advisor overlay, sniffer proxy, autopilot) functional
- 4 engine bugs fixed in most recent audit

### Known Technical Debt / Bugs
1. **6 unfixed structural divergences** (the reason for this port):
   - **Script execution ordering**: C++ two-pass (all resets then all scripts) vs AS3 single-pass (interleaved). Affects which cards see updated vs stale state.
   - **Ability cost timing**: C++ deducts health/charge AFTER script; AS3 deducts BEFORE. Affects units that use HP as ability cost.
   - **Snipe kill timing**: C++ kills target BEFORE running script; AS3 runs script FIRST. Could affect scripts that check target existence.
   - **Stagnation system**: C++ has flat 200-turn limit; AS3 has 4-level counter tracking 12+ event types with cutoffs [2, 8, 20, 40]. Stalemate games run 160+ extra turns generating low-quality data.
   - **Death scripts**: AS3 runs `deathScript` when units die from breach; C++ does nothing. Units like Centurion may behave differently.
   - **Missing Condition types**: 4 card conditions (`IS_BLOCKING`, `NAME_IN`, `IS_ABC`, `IS_ENGINEER_TEMP`) not implemented, potentially restricting some targeting abilities.

2. **All 722K training games have the defense reset bug** — both sides equally, so internally consistent but doesn't match real game.

3. **Replay validation tests legality, not state correctness** — a replay "passing" means recorded actions are legal, NOT that intermediate states match. Bugs that make MORE moves legal (like defense-reset) are invisible to replay validation.

### Recent Significant Changes
- **Engine audit** (Feb 22-23): 4 bugs fixed, 16 audit documents produced
- **Defense reset fix** (commit `d44740e`): Removed incorrect status reset in `beginPhase(Defense)` — was making tapped units eligible to block
- **LiveHardestAI** (Feb 23): Extracted live game's AI parameters from SWF, created faithful AI config

---

## 7. Context Specific to the Plan

### What the Plan Touches
The plan modifies **only `source/engine/` files** (primarily `GameState.cpp`, `Card.cpp`, and their headers). It creates 3 new Python validation tools and 1 new C++ test file. No changes to AI, search, testing, or GUI code.

### Prior Attempts
- **Patch-and-audit approach** (Feb 22-23): Fixed 4 bugs individually by comparing C++ vs AS3. Replay pass rate went from 55.7% → 50.4% (got worse because fixes made engine stricter). Remaining 6 divergences resist surgical patching — they require new infrastructure (stagnation counters, death script dispatch, etc.).
- **This plan is the "do it right" alternative** to continued patching.

### The AS3 Source
The AS3 source was obtained by decompiling the live Prismata client (`Prismata.swf`) using JPEXS FFDec. The game engine was originally compiled to AVM2 bytecode via Adobe CrossBridge (C++ → Flash). The decompiled AS3 is clean, well-structured, and serves as the **authoritative ground truth** for game behavior.

Key structural difference: AS3 uses string-based dispatch (`role = "default"`, `phase = "action"`, `deadness = "sniped"`), while C++ uses enum-based dispatch. The plan preserves C++ enums (type-safe, faster) while matching AS3 semantics.

### Dependencies and Integrations
- **Neural net feature extraction** (`training/schema.json`): state_dim=1785, 161 units x 11 features + 14 global. The port must not change feature semantics — the neural net was trained on specific feature definitions.
- **Self-play data format**: Binary shards with 64-byte header + 7,152-byte records. Feature extraction happens inside `TournamentGame.cpp` which calls GameState query methods. As long as query methods return the same values, shard format is unaffected.
- **Replay stepper** (`source/testing/ReplayStepper.h`): Feeds recorded actions into the engine. Used for validation — must continue working identically.
- **`--suggest` CLI mode** (`source/testing/Benchmarks.cpp`): Reads game state JSON, runs AI, outputs suggestions. Used by advisor overlay and autopilot.

### Performance Considerations
- AI search copies `GameState` thousands of times per second (Alpha-Beta creates a copy per node, UCT creates copies for playouts)
- **GameState size matters**: every byte added to GameState is multiplied by search tree size. The stagnation counters add 32 bytes (`int[2][4]`), which is acceptable.
- **Single-pass swoosh** may be faster than two-pass (one loop instead of two over all cards), but script execution inline could cause cache misses if scripts allocate.
- Target: ≤10% performance regression. If >20%, the rollback strategy applies.

---

## 8. Scope Boundaries

### Explicitly Out of Scope
| What | Why |
|---|---|
| **AI code changes** (`source/ai/`) | Port is behind the API boundary; AI consumes but doesn't implement game rules |
| **Testing code changes** (`source/testing/`) | Same — consumes API |
| **GUI code changes** (`source/gui/`) | Same — consumes API |
| **Undo system** (AS3 `MOVE_UN*` types) | C++ search uses state copy; undo is unnecessary overhead |
| **Campaign/mission systems** | Objectives, triggers, tutorials, lane system — irrelevant to PvP |
| **UI event dispatch** | AS3 `SEND_*` events are for GUI feedback — C++ engine has zero UI coupling |
| **Neural net retraining** | Happens after port is complete and data is regenerated |
| **StateHelper full port** | AS3's cached computation layer — partially useful but can be added incrementally post-port |
| **x64 build support** | Separate concern, not related to engine correctness |

### Fixed / Non-Negotiable Decisions
1. **Public API is frozen** — this is the fundamental constraint. 56 methods, zero changes.
2. **C++ data structures stay** — flat arrays, enums, Resources struct. No conversion to AS3-style Dictionaries.
3. **Single-pass swoosh** — the audit proved two-pass diverges from AS3. This is not up for debate.
4. **Stagnation implementation** — must match AS3's 4-level counter system exactly. The 200-turn flat limit is wrong.
5. **Pre-port binary preserved** — rollback path must always exist.

### Known Trade-offs Accepted
- **Port adds ~500-1,000 lines** to the engine (stagnation, death scripts, resonators). Accepted because these systems exist in the real game.
- **Phase 1 infrastructure (oracles)** is effort spent on tools, not features. Accepted as essential safety net.
- **Temporary performance regression** possible during port. Accepted with ≤10% target and profiling plan.

---

## 9. Success Criteria

| Metric | Pre-Port Baseline | Target | Stretch |
|---|---|---|---|
| **Replay pass rate** | 50.4% (1,072/2,127) | >80% | >90% |
| **Feature extraction match** | Not measured | >99% positions identical | 100% |
| **Legal action match** | Not measured | >99.5% identical | 100% |
| **Performance** | ~4 games/min/4-thread | ≤10% regression (>3.6/min) | No regression |
| **Structural divergences** | 6+ unfixed | 0 | — |
| **Self-play data quality** | Defense bug in all 722K games | Bug-free generation | — |
| **Zero regressions** | — | No replay that passed before should fail after | Mandatory |

### Observable Outcomes
- After Phase 3: at least some replay pass rate improvement
- After Phase 4: significant improvement from swoosh fix
- After Phase 6: all metrics meet targets, documented in `docs/port-validation-results.md`
- Post-port: regenerated self-play data with correct engine

---

## 10. Key Questions for Reviewers

1. **Phase ordering**: The plan ports move processing (Phase 3) before swoosh/beginTurn (Phase 4). Is this the right dependency order, or should swoosh be fixed first since it affects every turn while individual move types affect specific actions?

2. **Stagnation event tracking granularity**: The plan adds `resetStagnation()` calls at 10+ trigger points throughout the codebase. Is there a cleaner architecture for this (event bus, observer pattern, centralized tracking) that wouldn't scatter stagnation logic across every method?

3. **Testing sufficiency**: The plan relies on 3 oracles (replay, feature, legality) plus tournament smoke tests. Is this enough? Should there be a **differential fuzzing** approach where random games are played on both old and new engines simultaneously, comparing state at every step?

4. **Feature extraction risk**: The plan claims >99% feature match, but the swoosh rewrite changes when statuses reset, when health regenerates, etc. If features are extracted mid-turn (after partial actions), won't many feature vectors change legitimately? How should the plan handle this?

5. **Incremental vs big-bang testing**: The plan says "run replay oracle after each sub-step" but doesn't specify whether partial ports (e.g., swoosh fixed but move processing not yet ported) could actually cause MORE failures temporarily. Should the plan explicitly allow for a "valley" in pass rate during intermediate phases?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **Swoosh** | Turn transition phase — cards reset, construction ticks, scripts run, resources regenerate. AS3 calls it `swoosh()`, C++ calls it `beginTurn()`. |
| **Breach** | When an attacker's damage exceeds all defenders, remaining damage targets individual enemy units directly. |
| **Wipeout** | A breach that kills all remaining blockers at once. |
| **Frontline** | Units assigned to die at end of turn, dealing attack damage. Self-sacrifice for damage. |
| **Chill** | Disruptive damage that temporarily freezes units, preventing them from blocking. |
| **Snipe** | Targeted ability that kills a specific enemy unit (bypasses normal combat). |
| **Death Script** | Code that executes when a unit dies (e.g., spawning tokens). Present in AS3, missing from C++. |
| **Stagnation** | Game-ending condition when no meaningful progress occurs for too many turns. AS3 uses 4 counters with different cutoffs. |
| **Resonator/Annihilator** | Units that generate resources based on the presence of specific other units. Synergy mechanic. |
| **PartialPlayer** | AI architecture that decomposes turn decisions into phases (Defense, ActionAbility, ActionBuy, Breach) with specialized sub-players for each. |
| **Playout** | A random or heuristic-guided game simulation from a position to completion, used for position evaluation in MCTS/UCT. |
| **WillScore** | A heuristic evaluation function based on material counting with resource-type weights (Attack=2.25, Blue=1.50, etc.). |
| **CardData** | C++ container managing card instances — flat array with ID allocation, player-indexed access, `removeKilledCards()`. |
| **CardType** | Static definition of a card (costs, stats, abilities, scripts). Read from `cardLibrary.jso`. C++ equivalent of AS3's `Card.as`. |
| **Card** | A specific instance of a CardType in play (has current HP, status, construction timer). C++ equivalent of AS3's `Inst.as`. |
| **Script / ScriptEffect** | A sequence of effects (create unit, add resources, deal damage) attached to card abilities, beginOwnTurn, buy, or death events. |
| **Condition** | A predicate on a card (e.g., "is blocking", "is type X") used for targeting restrictions and ability prerequisites. |
| **Alpha-Beta Search** | Tree search algorithm that prunes suboptimal branches. Used by HardestAI with stack-based implementation. |
| **UCT/MCTS** | Monte Carlo Tree Search with Upper Confidence bounds for Trees. Alternative to Alpha-Beta. |
| **Replay Oracle** | Validation tool that runs recorded game replays through the engine, checking that all actions are legal. A proxy for engine correctness. |
| **AS3** | ActionScript 3, the language of the decompiled Prismata client. The game engine was compiled from C++ to AVM2 bytecode via CrossBridge. |
| **SWF** | Shockwave Flash file — the compiled Prismata client. Decompiled using JPEXS FFDec. |
| **`cardLibrary.jso`** | Master JSON file defining all 105+ game units with internal codenames (e.g., "Tesla Tower" for Tarsier). |
| **`config.txt`** | Configuration file defining AI players, tournaments, and game parameters. |
| **Self-play shard** | Binary file containing training data (game positions + evaluations). 64-byte header + N records of 7,152 bytes each. |
| **state_dim=1785** | Neural net input size: 161 units x 11 features + 14 global features. |
