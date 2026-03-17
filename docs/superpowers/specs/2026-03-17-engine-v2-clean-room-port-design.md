# Design Spec: C++ Engine V2 — Clean-Room Port for Linux RL Self-Play

> **Date**: 2026-03-17
> **Approach**: Clean-room port from validated JS/AS3 engine into `source/engine_v2/`
> **Goal**: Replace buggy C++ game engine with a correct implementation, preserve the C++ AI layer, deliver CMake-based Linux build for headless RL self-play

---

## 1. Architecture Overview

### 1.1 Directory Structure

```
source/
├── engine/          # OLD — untouched, still used by VS solution for GUI replay viewer
├── engine_v2/       # NEW — clean-room port from JS/AS3
├── ai/              # MODIFIED — NeuralNet singleton→instance refactor
├── testing/         # INCLUDED in CMake — tournament runner, --suggest CLI, Linux entry point
├── rapidjson/       # INCLUDED in CMake — header-only JSON parsing
├── gui/             # EXCLUDED from CMake — old VS solution only
└── standalone/      # EXCLUDED from CMake — MCDSAI entry point, not needed
```

### 1.2 Build Systems

**CMake** (new): Targets Linux x64. Links `engine_v2` + `ai` + `testing` + `rapidjson`. No SFML, no GUI, no MCDSAI. Two targets:
- `prismata_tests` — validation harness + tournament runner
- `prismata_selfplay` — headless RL self-play binary

**Include path resolution**: CMake sets include directories to `source/engine_v2/` (not `source/engine/`). Since AI files use bare includes like `#include "GameState.h"`, the CMake include path controls which engine they resolve to. One known exception: `AIParameters.h` hardcodes `#include "../engine/Prismata.h"` — this must be updated to `#include "../engine_v2/Prismata.h"` during AI integration (Step 11). The interface audit (Step 0) should grep for all path-qualified engine includes in `source/ai/` to build the complete list.

**Old VS solution** (untouched): Continues to build x86 `Prismata_GUI.exe` against `source/engine/` for replay viewing. The two build systems coexist — CMake never touches `source/engine/`, VS never touches `source/engine_v2/`.

### 1.3 Core Design Principle

The new engine implements the **exact same public interface** as the old engine (`GameState`, `Card`, `Action`, `Move`, `Resources`, etc.) so that the AI layer (`source/ai/`) compiles against it with zero functional changes (only the NeuralNet refactor is a deliberate change). If any interface mismatch is discovered, it is fixed in `engine_v2` to match what the AI expects.

The **JS engine** (`js_engine/`) is the sole reference for game logic. The old C++ engine is not consulted — logic is ported from JS with AS3 (`prismata_decompiled/scripts/mcds/engine/`) as tiebreaker when JS transpilation is unclear.

---

## 2. Interface Contract

### 2.1 Phase 0: Interface Audit

Before writing any `engine_v2` header, an exhaustive audit catalogs every type, enum, typedef, constant, and method signature that `source/ai/` imports from `source/engine/`. This includes:

- `Constants.h` — phase enums, action types, player IDs, search/eval method enums
- `Action.h` / `Move.h` — action data types
- `Resources.h` — resource pool
- `Card.h` — card instance queries (40+ public methods), plus `AliveStatus`, `CauseOfDeath`, `DamageSource`, `CardCreationMethod` enums defined within
- `CardType.h` / `CardTypes.h` — card type definitions, global registry, and `CardStatus` namespace (note: `CardStatus` is defined in `CardType.h`, NOT `Constants.h`)
- `CardBuyable.h` — supply/shop queries
- `CardData.h` — internal card storage container used by GameState; defines `CardIDVector` typedef
- `GameState.h` — ~30 query methods + `doAction()` / `doMove()`
- `Player.h` — base player class
- `Prismata.h` — umbrella header / global init
- `Common.h` / `BaseTypes.hpp` — shared typedefs (`CardID`, `PlayerID`, `HealthType`, `TurnType`, etc.)
- `MoveIterator.h` — base move iterator class (AI files import this)
- Any other headers `source/ai/` includes from `source/engine/` — grep for all path-qualified includes (e.g. `../engine/`) to catch hardcoded paths

The output is a **locked interface spec** — a document listing every symbol the AI depends on, with exact signatures. `engine_v2` headers must satisfy this spec exactly.

### 2.2 GameState — Primary Interface

The AI layer's dependency on GameState is read-heavy and action-generative:

**State queries** (const):
- `isGameOver()`, `winner()`, `getActivePlayer()`, `getActivePhase()`, `getTurnNumber()`
- `getAttack(player)`, `getTotalAvailableDefense(player)`, `getResources(player)`
- `getCardIDs(player)`, `getCardByID(id)`, `numCards(player)`, `numCardsOfType(player, type)`
- `numCardsBuyable()`, `getCardBuyableByIndex(i)`, `isBuyable(player, type)`
- `hasBreachableCard(player)`, `canOverkillEnemyCard(player)`

**Legal move generation**:
- `generateLegalActions(vector<Action>&)` — all legal actions in current phase
- `isLegal(const Action&)` — validate single action

**State mutation**:
- `doAction(const Action&)` — apply single action (returns success)
- `doMove(const Move&)` — apply action sequence

**Serialization**:
- `toJSONString()` — state export
- `initFromJSON(...)` — state import

**Critical invariant**: The AI layer never directly mutates cards or resources. All changes go through `doAction()`.

**Copy semantics**: `GameState` must be cheaply copyable — UCT and Alpha-Beta copy states millions of times for tree exploration. Internally, GameState contains a `CardData` member (card storage container with vectors). Default copy constructor does deep copies of these vectors. This is acceptable for correctness; if profiling shows copy cost is a bottleneck, consider pre-reserved fixed-capacity storage. Do not prematurely optimize — measure first.

**Serialization format**: `toJSONString()` / `initFromJSON()` must be compatible with the format used by `js_engine/replay_exporter.js` (the JS→C++ state exchange format). This is the same format the GUI's replay loader expects. The interface audit should document the exact JSON schema from the old C++ `GameState::toJSONString()`.

### 2.3 Card — Instance Interface

The AI queries ~40 methods on Card instances. Key groups:

- **Identity**: `getType()`, `getID()`, `getPlayer()`
- **State**: `currentHealth()`, `currentChill()`, `getDamageTaken()`, `getCurrentCharges()`, `getCurrentDelay()`, `getCurrentLifespan()`, `getConstructionTime()`, `getStatus()`, `getAliveStatus()`
- **Capabilities**: `canBlock()`, `canUseAbility()`, `canSac()`, `isBreachable()`, `canBeChilled()`, `isSellable()`, `isDead()`, `isUnderConstruction()`, `isFrozen()`, `abilityUsedThisTurn()`
- **Comparison**: `isIsomorphic(const Card&)`

### 2.4 Player — Base Class

```cpp
class Player {
    virtual void getMove(const GameState & state, Move & move);
    const int ID();
    void setID(const int playerid);
    virtual std::string getDescription();
    virtual void setDescription(const std::string & desc);
    virtual PlayerPtr clone();
};
```

All AI player subclasses (`Player_UCT`, `Player_StackAlphaBeta`, `Player_PPSequence`, etc.) receive `const GameState&` — read-only contract.

---

## 3. File Mapping: JS Source → C++ Target

### 3.1 Ported from JS/AS3 (Game Logic)

| JS Source | Lines | C++ Target (`engine_v2/`) | Scope |
|-----------|-------|--------------------------|-------|
| `State.js` | 1,686 | `GameState.cpp/h` | Phase machine, swoosh, turn logic, action application |
| `Controller.js` | 2,268 | Folded into `GameState.cpp` | Click processing → `doAction()` / `isLegal()` internals. UI/undo/animation parts dropped. |
| `Analyzer.js` | 889 | Folded into `GameState.cpp` | `generateLegalActions()` — legal move enumeration |
| `StateHelper.js` | 525 | Folded into `GameState.cpp/h` | Derived/cached state — defense totals, blockable unit lists, attack calculations |
| `Inst.js` | 405 | `Card.cpp/h` | Unit instance state, status, capability checks |
| `Card.js` | 517 | `CardType.cpp/h` | Card type definitions, ability specs, costs |
| `Mana.js` | 182 | `Resources.cpp/h` | Resource pool arithmetic |
| `Script.js` | 89 | `Script.cpp/h` | Script execution, effects, resonance |
| `C.js` | 475 | `Constants.h` | Enums, phase IDs, action types |
| `StateUtil.js` | 184 | Utility functions in `GameState.cpp` | Helper calculations |
| `EndTurnObject.js` | ~50 | Folded into `GameState.cpp` | Win detection logic (`checkWin`) called during confirm phase |

### 3.2 Carried from Old C++ (Data Containers — No Game Logic)

| Old C++ Source | C++ Target (`engine_v2/`) | Rationale |
|----------------|--------------------------|-----------|
| `Action.h/cpp` | `Action.h/cpp` | Pure data tuple (type + player + IDs). Trivially auditable. |
| `Move.h/cpp` | `Move.h/cpp` | Vector of Actions. No game logic. |
| `Player.h/cpp` | `Player.h/cpp` | Base class + ID + description. No JS equivalent (player data lives in State). AI depends on this type. |
| `CreateDescription.h/cpp` | Same | Token creation spec — data descriptor |
| `DestroyDescription.h/cpp` | Same | Unit destruction spec — data descriptor |
| `SacDescription.h/cpp` | Same | Sacrifice cost spec — data descriptor |
| `Condition.h/cpp` | Same | Conditional script logic — data descriptor |

These are 50-100 line data containers with no game rules. Rewriting from JS would reproduce identical structs.

### 3.3 New Files (No Direct JS Equivalent)

| File | Purpose |
|------|---------|
| `Prismata.cpp/h` | Global init — card library loading from `cardLibrary.jso` |
| `CardTypes.cpp/h` | Global registry of all 116 card types (11 base + 105 Dominion) |
| `CardBuyable.cpp/h` | Buyable card in shop — supply tracking |
| `Common.h` / `BaseTypes.hpp` | Shared typedefs (`CardID`, `PlayerID`, `HealthType`, `CardIDVector`, etc.) |
| `CardData.cpp/h` | Internal card storage container — holds all card instances, manages IDs, `removeKilledCards()`. Used by GameState. |
| `Game.cpp/h` | Game orchestration |
| `Timer.h/cpp` | High-resolution timing (already has `#ifdef WIN32` guards) |
| `FileUtils.h/cpp` | File I/O utilities |
| `JSONTools.h/cpp` | RapidJSON helpers |
| `PrismataAssert.h/cpp` | Soft assert macro |
| `ScriptEffect.h/cpp` | Effect definition (damage, create, destroy actions) |

---

## 4. Key Translation Decisions

### 4.1 Phase Model Reconciliation

The JS engine has 3 explicit phases (`PHASE_DEFENSE`, `PHASE_ACTION`, `PHASE_CONFIRM`) plus `glassBroken` flag and `swoosh()` as a function call. The C++ AI expects 5 phase enum identifiers: `Action=0, Defense=1, Breach=2, Confirm=3, Swoosh=4`.

**A player's turn flows**: Defense (if incoming attack) → Swoosh (transient) → Action → [Breach] (if wipeout) → Confirm.

**Critical implementation point**: Defense belongs to the **incoming** player's turn start. The JS does `++numTurns` (switching active player) *before* the defense phase check. Engine_v2 replicates this: commit switches who's active, then checks if the new active player needs to defend.

**`getActivePhase()` contract**:

| Game Moment | Returns |
|---|---|
| New player's turn starts, opponent had attack | `Phases::Defense` |
| Player assigns blockers, commits defense | → swoosh runs internally → |
| After swoosh, player's resources refreshed | `Phases::Action` |
| Player clicks abilities / buys / attackers | `Phases::Action` |
| Attack total crosses wipeout threshold | `Phases::Breach` |
| Player clicks undefended enemy units | `Phases::Breach` |
| Player ends turn | `Phases::Confirm` |
| After confirm committed | → `++m_turnNumber` (after win check), switch active player, then next player's Defense or Action |

`Phases::Swoosh` is transient — the AI never sees it as a decision point. The Confirm→next-player transition is where `m_turnNumber` increments and the active player changes. This is the implementation of the JS `MOVE_COMMIT` handler.

### 4.2 Action Type Mapping

| JS Constant | C++ ActionType | Notes |
|---|---|---|
| `MOVE_ASSIGN` | `USE_ABILITY` | Click unit to use ability |
| `MOVE_UNASSIGN` | `UNDO_USE_ABILITY` | Undo ability use |
| `MOVE_BUY` | `BUY` | Purchase from supply |
| `MOVE_SELL` | `SELL` | Sell unit back |
| `MOVE_DEFEND` | `ASSIGN_BLOCKER` | Block incoming attack |
| `MOVE_MELEE` | `ASSIGN_FRONTLINE` | Frontline assignment |
| `MOVE_BREACH_OR_OVERKILL` | `ASSIGN_BREACH` | Breach/overkill targeting |
| `MOVE_UNBREACH_OR_UNOVERKILL` | `UNDO_BREACH` | Undo breach selection |
| (targeting) | `SNIPE` | Target snipe damage |
| (targeting) | `CHILL` | Target chill/freeze |
| (targeting) | `UNDO_CHILL` | Undo chill targeting |
| `MOVE_WIPEOUT` | `WIPEOUT` | Trigger glass-break |
| `MOVE_ENTER_CONFIRM` | `END_PHASE` (Action) | End action phase |
| `MOVE_COMMIT` | `END_PHASE` (Confirm) | Commit turn |
| `MOVE_END_DEFENSE` | `END_PHASE` (Defense) | End defense phase |

### 4.3 Field Name Translations

| JS/AS3 | C++ | Notes |
|--------|-----|-------|
| `role` (string) | `CardStatus` enum | Defined in `CardType.h` (NOT `Constants.h`). Enum values must match exactly. |
| `disruptDamage` | `m_currentChill` | Field name only |
| `glassBroken` flag | `Phases::Breach` phase | In JS, `glassBroken=true` does NOT change `state.phase` (stays `PHASE_ACTION`). Engine_v2 must detect this sub-state and report `Phases::Breach` via `getActivePhase()` even though the internal phase is still Action. See Section 4.1. |
| `numTurns` | `m_turnNumber` | Increments at COMMIT. **Timing difference**: JS increments `++numTurns` AFTER checking for a winner; old C++ increments BEFORE game-over check. Engine_v2 must follow JS timing (increment after win check). |

### 4.4 Structural Translations

| JS/AS3 Pattern | C++ Translation |
|---|---|
| Dynamic arrays | Pre-reserved `std::vector` with sensible initial capacity. The old engine uses `std::vector` for card storage. Avoid per-action heap allocations but don't over-engineer fixed-size arrays before profiling shows they're needed. |
| `null` checks | `isDead()` checks and `CardID(-1)` sentinels |
| Single-pass swoosh | **Must** implement single-pass (not old C++ two-pass). Per-card: lifespan/delay tick → script execution. |
| 4-level stagnation counters | New implementation. Thresholds: [2, 8, 20, 40]. Missing entirely from old C++. |
| All-units-doomed instant win | New implementation. Missing from old C++. |
| Two-step targeting abilities | USE_ABILITY on source → SNIPE/CHILL on target. 12 units have `targetAction`. |
| `beginOwnTurnScript` vs `abilityScript` | Automatic (no click) vs player-activated (click). Must correctly distinguish. |

### 4.5 Performance Requirements

- `doAction()` / `isLegal()` must be **allocation-free** in the hot path — search calls these millions of times
- Card storage: contiguous array indexed by `CardID`
- `GameState` must be **cheaply copyable** — UCT/AlphaBeta copy states for tree exploration
- Idiomatic C++ (value types, `std::vector`, RAII) but logic and ordering must match JS exactly

---

## 5. Validation Strategy

### 5.1 Tiered Replay Validation

| Tier | Size | When | Purpose |
|------|------|------|---------|
| **Smoke** | ~100-500 replays | After every function port | Immediate feedback, seconds to run |
| **Milestone** | ~5,000 replays | After each file is complete | `dataset_validation.json` likely fits here |
| **Full archive** | 102,697 replays | Final gate before declaring done | Complete confidence |

### 5.2 Per-Turn State Comparison

The validation harness compares **full game state at each turn boundary**, not just final outcome. Compared fields:
- Resources (gold, energy, blue, red, green, attack)
- Card states (health, chill, damage, status, lifespan, charges, delay, construction time)
- Phase, active player
- Attack totals
- Supply counts

A winner match with divergent internal state is a **failure**. This matches the rigour of `js_engine/replay_validator.js`.

### 5.3 Cross-Engine Diffing

On validation failure, the harness exports both engines' state at the point of divergence:
- Turn number and phase
- Full card-by-card state dump
- Resource snapshots
- The action that caused divergence

This enables precise bug diagnosis without re-running the full replay.

### 5.4 Name Translation

Replays use **display names** (UINames: "Synthesizer", "Tarsier"). The C++ engine uses **internal names** ("Factory", "Tesla Tower"). The test harness needs a hardcoded translation table.

Source: `bin/asset/config/cardLibrary.jso`
- Key = internal name (used by C++ engine and AS3)
- `"UIName"` field = display name (used by JS engine and replays)
- When UIName is absent, internal name = display name (most base units)
- 105 Dominion units all have UIName entries. 11 base units mostly don't.

Translation path: **replay display name → UIName lookup → internal name → C++ card match**.

The mapping is frozen (116 units, never changes) and can be hardcoded rather than loaded at runtime.

### 5.5 Functional Parity Standard

The target is **functional parity**: identical game outcomes for all replay inputs. Minor serialization or cosmetic differences (JSON field ordering, floating point formatting) are acceptable. The new engine does NOT need to produce byte-identical JSON — it needs to produce identical game state transitions.

---

## 6. NeuralNet Singleton → Instance Refactor

This happens in `source/ai/`, not `engine_v2/`. Deferred to after AI integration proves the interface works (Step 12, after Step 11).

### 6.1 Current State

`NeuralNet::Instance()` returns a single global instance. Weight file loaded once at init. All evaluation goes through this singleton. This prevents two NN players with different weight files in one process.

### 6.2 Target State

`NeuralNet` becomes a regular class. Each player that uses NN eval holds its own `NeuralNet` instance (or a `std::shared_ptr<NeuralNet>` if single-threaded). Players with different weight files always get separate instances. Players with the same weight file on different threads also need separate instances due to mutable scratch buffers (see Section 6.5).

**Wiring**: `AIParameters` already parses per-player `"WeightsFile"` config. After refactor, it constructs a `NeuralNet` per unique weight file path and passes it to the player.

### 6.3 Eval Signature Cascade

Eval functions currently call `NeuralNet::Instance()` internally. After refactor, they need a `NeuralNet*` parameter. This changes Eval function signatures, which ripple into UCT search and Alpha-Beta call sites. This is more involved than a single-file change — it's a systematic signature update across the search layer.

### 6.4 Pre-Implementation Audit

Before implementing:
1. **Read `NeuralNet.h/cpp`** — confirm no hidden mutable state (caches, statistics counters). If found, the thread safety analysis needs revision.
2. **Grep all `NeuralNet::Instance()` call sites** — build the complete change list. Don't miss call sites outside the expected files.

### 6.5 Thread Safety

NN weights are read-only after loading. However, `NeuralNet.h` has `mutable ScratchBuffers _scratch` — pre-allocated scratch buffers for inference. The code comments state: "Thread safety: evaluation is single-threaded per NeuralNet instance." This means **concurrent reads on the same instance are NOT safe**.

Design consequence: players sharing the same weight file need **separate NeuralNet instances** (not a shared pointer to one instance) if they run on different threads. Alternatively, scratch buffers can be refactored to thread-local or per-call allocation. The pre-implementation audit (Step 12) must choose the approach based on performance profiling — separate instances are simpler, thread-local buffers save memory.

---

## 7. What Gets Dropped / Kept / Modified

| Component | Decision | Rationale |
|---|---|---|
| `source/engine/` | **Kept untouched** | Old VS solution uses it for GUI replay viewer |
| `source/engine_v2/` | **New** | Clean-room port from JS/AS3 |
| `source/ai/` | **Modified in-place** | NeuralNet singleton→instance refactor, Eval signature changes |
| `source/gui/` | **Excluded from CMake** | Not in Linux build. Old VS solution still links it. |
| `source/testing/` | **Included in CMake** | Tournament runner, `--suggest` CLI, Linux entry point |
| `source/standalone/` | **Excluded from CMake** | MCDSAI entry point — not needed |
| `source/rapidjson/` | **Included in CMake** | Header-only, no changes |
| SFML | **Excluded from CMake** | GUI-only dependency |
| MCDSAI protocol | **Not implemented** | New engine runs AI natively |
| `--suggest` CLI mode | **Kept** | Lives in `source/testing/main.cpp`. Useful for JS matchup runner integration. |
| Old VS solution | **Untouched** | Still builds x86 GUI for replay viewing |

---

## 8. Migration Sequence (Build Order)

Bottom-up port. CMake stub created at Step 1 — each file is added as it's written, so Linux compile errors surface immediately rather than all at once.

| Step | Files | Depends On | Validation |
|------|-------|------------|------------|
| **0** | **Interface audit** — catalog every type/enum/typedef AI imports from engine | Nothing | Produces locked interface spec |
| **1** | **CMake stub + Constants, Common, typedefs** — phase enums, action types, player IDs | Step 0 spec | Compiles on both platforms |
| **2** | **Resources** — resource pool arithmetic (from `Mana.js`) | Step 1 | Unit tests vs JS Mana |
| **3** | **Action, Move** — data containers (from old C++) | Step 1 | Unit tests |
| **4** | **Script, ScriptEffect, Condition, CreateDescription, DestroyDescription, SacDescription** — ability/effect descriptors | Steps 1-2 | Unit tests |
| **5** | **CardType, CardTypes** — type definitions + global registry + `cardLibrary.jso` loader | Steps 1-4 | Load library, verify 116 units parse |
| **6** | **Card** — unit instance (from `Inst.js`) | Steps 1-5 | Unit tests for state transitions |
| **7** | **CardBuyable** — shop/supply tracking | Steps 1-6 | Unit tests |
| **8** | **GameState** — the largest step, broken into sub-steps: | Steps 1-7 | |
| 8a | Phase state machine (Defense → Swoosh → Action → Breach → Confirm) | Steps 1-7 | Phase transition tests |
| 8b | Action handlers (`doAction` for each ActionType) | Step 8a | Per-action-type tests |
| 8c | Swoosh / beginTurn scripts (resource refresh, lifespan/delay ticks, script execution) | Step 8b | Script execution tests |
| 8d | Legality (`isLegal`, `generateLegalActions` — from `Analyzer.js`) | Step 8c | Legal move generation tests |
| 8e | Win detection, all-units-doomed, game over | Step 8d | Game termination tests |
| 8f | Stagnation detection (4-level progress counters: [2, 8, 20, 40]) | Step 8e | Stagnation scenario tests |
| 8g | Derived/cached state (from `StateHelper.js` — defense totals, blockable units) | Step 8f | Smoke replay set |
| **9** | **Player, Game, Prismata (init)** — player base class, game orchestration, global init | Steps 1-8 | Full engine compiles |
| **10** | **Validation harness** — replay loader, per-turn state diff, name translation | Steps 1-9 | Smoke → Milestone → Full archive |
| **11** | **AI layer integration** — link `source/ai/` against `engine_v2/`, fix interface mismatches | Steps 1-10 | Tournament runs with AI players |
| **12** | **NeuralNet refactor** — singleton→instance in `source/ai/` | Step 11 | Two different NN players in one process |

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Interface mismatch discovered mid-port | Phase 0 audit locks the spec. Any surprise is fixed in `engine_v2`, not the AI layer. |
| GameState port is too large for one session | Sub-steps 8a-8g are independently testable. Can pause and resume between sub-steps. |
| JS logic ambiguity (transpilation artifacts) | AS3 source (`prismata_decompiled/scripts/mcds/engine/`) is the tiebreaker |
| Performance regression vs old C++ | Contiguous card arrays, allocation-free hot paths, cheap copies. Profile after integration. |
| Linux portability surprises | CMake from Step 1, compile each file as written. `source/testing/main.cpp` gets a portability check during audit. |
| NeuralNet has hidden mutable state | Pre-implementation audit (read NeuralNet.h/cpp) before designing thread safety |

---

## 10. Out of Scope

- GUI / SFML — old VS solution handles this
- MCDSAI protocol / `source/standalone/` — not needed
- Policy head / PUCT improvements — separate project
- Cloud deployment — local development first
- Windows CMake support — bonus, not a requirement (Linux x64 primary)
