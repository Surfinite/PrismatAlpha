# Feasibility Analysis: AS3 Faithful Port of GameState Internals

**Date:** February 23, 2026
**Branch:** `feature/engine-logic-audit`
**Status:** Planning — no code changes yet

## Executive Summary

This document assesses the feasibility of rewriting C++ `GameState` internals as a faithful port of the decompiled AS3 source code (`State.as`, `Inst.as`, `Card.as`, `StateHelper.as`, `C.as`). The goal is to eliminate the class of bugs found during the engine logic audit (4 bugs fixed, 6+ structural divergences remaining) by directly translating the game's ground-truth implementation.

**Recommendation: FEASIBLE with HIGH confidence.** The C++ public API (56 methods, 91 dependent files) can be preserved while replacing internal logic. The AS3 source is 7,021 lines of clean, well-structured code that maps naturally to C++. The key risk is not the port itself but ensuring zero regression in the 91 AI/testing files that consume the API.

---

## 1. Motivation

### 1.1 Current State of the C++ Engine

The engine logic audit (Feb 22-23, 2026) found:
- **4 bugs fixed** (defense reset, all-units-doomed, mutual draw, wipeout fall-through)
- **6+ unfixed structural divergences** (stagnation system, death scripts, script ordering, 4 Condition types, resonator system, spell collection)
- **Batch validation regressed** from 55.7% to 50.4% after fixes (engine became stricter)
- **All 722K self-play games** were generated with the defense reset bug

The patch-and-audit approach has diminishing returns. Each fix risks introducing new inconsistencies, and the remaining gaps (stagnation, death scripts) require significant new infrastructure rather than surgical patches.

### 1.2 Why Port Instead of Patch

| Approach | Pros | Cons |
|---|---|---|
| **Continue patching** | Low risk per change, incremental | Diminishing returns, 50.4% replay pass rate, unknown unknowns remain |
| **Faithful port** | Eliminates entire class of divergence bugs, single source of truth, enables near-100% replay compatibility | Higher upfront effort, regression risk, requires thorough validation |

The port gives us:
1. **Correct engine for data regeneration** — all 722K games need regeneration anyway
2. **Near-100% replay compatibility** — replays are the ground truth test suite
3. **Future-proof** — any new card interactions are correct by default
4. **Live advisor accuracy** — sniffer/overlay/autopilot tools rely on engine matching the live game

---

## 2. Scope Analysis

### 2.1 What Changes (Internal Implementation)

The port rewrites the **internals** of these C++ files:

| C++ File | Lines | AS3 Equivalent | AS3 Lines | Change Type |
|---|---|---|---|---|
| `GameState.cpp` | 2,443 | `State.as` | 4,490 | Major rewrite |
| `GameState.h` | 162 | (same) | — | Private members change, public API preserved |
| `Card.cpp` | 993 | `Inst.as` + `Card.as` | 1,257 | Moderate rewrite |
| `Card.h` | 148 | (same) | — | Private members may change |
| *New file* | — | `StateHelper.as` | 649 | New (cached computed properties) |

**Total C++ engine code affected:** ~3,746 lines rewritten
**AS3 source to translate:** ~7,021 lines (includes UI dispatch, undo, mission logic we can skip)

Estimated net C++ after port: ~3,500-4,500 lines (larger than current due to stagnation + death scripts + resonators, but smaller than AS3 due to no UI/undo/mission code).

### 2.2 What Does NOT Change (Public API)

The C++ public API — **56 methods across 91 dependent files** — remains identical:

| API Category | Methods | Call Sites | Preserved? |
|---|---|---|---|
| Mutation | 7 (`doAction`, `doMove`, `beginTurn`, etc.) | 133 | Yes |
| Query | 28 (`getResources`, `getCardByID`, etc.) | 745+ | Yes |
| Generation | 3 (`generateLegalActions`, `isLegal`, `getClickAction`) | 117 | Yes |
| Serialization | 3 (`toJSONString`, `getStateString`, `getMemoryUsed`) | 18+ | Yes |
| **Total** | **56** | **~1,000+** | **All preserved** |

No AI, search, neural net, tournament, or testing code needs to change. The port is entirely behind the `GameState` API boundary.

### 2.3 AS3 → C++ Method Mapping

Core game logic maps cleanly:

| AS3 Method | C++ Method | Mapping Quality |
|---|---|---|
| `processMove(type, instId, targetId, cardId, ...)` | `doAction(Action)` | Clean — Action encapsulates params |
| `swoosh()` | `beginTurn()` | Clean — same lifecycle |
| `checkWin()` | `calculateGameOver()` | Clean — same semantics |
| `helper.update()` | (new) `updateStateHelper()` | New addition |
| `allCardsOfColorWithName()` | `numCardsOfType()` + iteration | Adaptation needed |
| `runScriptForward()` | `runScript()` | Exists but incomplete |
| `collectBodies()` | (inline in `endPhase`) | Restructure |
| `manaRots()` | (not implemented) | New addition |
| `executeTriggers()` | (not implemented) | Skip — campaign only |

### 2.4 Systems to Add

| System | AS3 Lines | C++ Effort | Priority |
|---|---|---|---|
| **Stagnation detection** | ~80 | ~120 lines | HIGH — affects draw detection |
| **Death scripts** | ~40 | ~60 lines | HIGH — affects breach outcomes |
| **Resonator/annihilator** | ~60 | ~80 lines | MEDIUM — rare but real |
| **Spell collection** | ~30 | ~40 lines | LOW — spell units rare |
| **Mana rot** | ~20 | ~30 lines | LOW — temporary resources |
| **Full Condition types** | ~100 | Skip | SKIP — campaign/tutorial only |
| **Trigger system** | ~150 | Skip | SKIP — campaign/tutorial only |
| **Objective system** | ~200 | Skip | SKIP — campaign/tutorial only |

We skip ~450 lines of campaign/mission-only code. Everything relevant to competitive PvP gets ported.

---

## 3. API Compatibility Analysis

### 3.1 Method-Level Compatibility

Every public method has a clear AS3 equivalent or remains unchanged:

**Direct equivalents (semantic match):**
- `doAction` ← `processMove` (different param encoding, same logic)
- `generateLegalActions` ← StateHelper computed properties + move legality checks
- `isLegal` ← per-move-type legality checks inside `processMove`
- `isGameOver` ← `finished` getter
- `getActivePlayer` ← `turn` getter
- `getAttack` ← `turnMana.attack` / `oppMana.attack`
- `getResources` ← `playerMana(color)`
- `numCardsOfType` ← `allCardsOfColorWithName().length`
- `beginTurn` ← `swoosh()`
- `killCardByID` ← `deleteInst()` + death script execution

**No AS3 equivalent (C++ additions, keep as-is):**
- `isIsomorphic` / `isPlayerIsomorphic` — transposition table support
- `getStateString` / `toJSONString` — serialization (already correct)
- `manuallySetAttack` / `manuallySetMana` — debug helpers
- `getMemoryUsed` — profiling

### 3.2 Data Structure Mapping

| AS3 | C++ Current | C++ After Port |
|---|---|---|
| `table` (Dictionary: instId→Inst) | `m_cards` (CardData, flat array) | Keep flat array (performance) |
| `whiteMana` / `blackMana` (Mana) | `m_resources[2]` (Resources) | Keep Resources (isomorphic) |
| `whiteSupply[cardId]` | `CardBuyable.m_supply` | Keep (cleaner) |
| `numTurns` (int) | `m_turnNumber` (TurnType) | Keep (same semantics) |
| `phase` (String) | `m_activePhase` (Phases enum) | Keep enum (type-safe) |
| `glassBroken` (Boolean) | Phases::Breach (separate phase) | **Change** — use flag like AS3 |
| `whiteNoProgress[4]` | (not present) | **Add** — `m_noProgress[2][4]` |
| `helper` (StateHelper) | (not present) | **Add** — cached computed state |

### 3.3 Breaking Change Risk: NONE

The port does not change:
- Method signatures or return types
- Action/Move/Card/CardType/Resources class interfaces
- Enum values (ActionTypes, Phases, CardStatus, etc.)
- Binary shard format or feature extraction
- Config file parsing or AI parameter system

---

## 4. Risk Assessment

### 4.1 High-Confidence Areas

| Area | Confidence | Rationale |
|---|---|---|
| API preservation | 99% | 56 methods with clear contracts, all callers use const getters |
| Move processing (buy, assign, defend) | 95% | Direct 1:1 mapping, well-understood |
| Phase transitions | 95% | Already audited exhaustively (15 deliverables) |
| Swoosh/beginTurn | 90% | Complex but well-documented in AS3 |
| Game-over detection | 95% | Already fixed, AS3 logic is clear |

### 4.2 Medium-Confidence Areas

| Area | Confidence | Risk | Mitigation |
|---|---|---|---|
| Script execution ordering | 80% | Two-pass vs single-pass architectural choice | Dual-engine test harness validates equivalence |
| Stagnation system | 85% | New code, must track 12+ event types correctly | Port directly from AS3, test with known stalemate replays |
| Death scripts | 85% | New trigger mechanism | Port directly, validate with Centurion/Valkyrion replays |
| Resonator/annihilator | 80% | Rarely exercised path | Port directly, find replays with resonator units |

### 4.3 Low-Confidence / Watch Areas

| Area | Confidence | Risk | Mitigation |
|---|---|---|---|
| Performance regression | 70% | StateHelper recomputation, stagnation counter overhead | Profile before/after; StateHelper can be lazily computed |
| Undo support | 75% | AS3 has full forward/backward; C++ may need undo for search | Search uses state copy, not undo — may be unnecessary |
| Edge cases in card interactions | 70% | 105 units × diverse scripts = combinatorial explosion | Replay test suite (2,127+ replays) catches most |

### 4.4 Estimated Effort

| Phase | Effort | Description |
|---|---|---|
| 1. Preservation infrastructure | 1-2 sessions | Baseline tag, oracles, test harnesses |
| 2. Core port (GameState + Card) | 3-5 sessions | processMove, swoosh, game-over, scripts |
| 3. New systems (stagnation, death, resonate) | 1-2 sessions | Direct AS3 translation |
| 4. Validation & regression testing | 2-3 sessions | Replay suite, dual-engine, feature extraction |
| **Total** | **7-12 sessions** | — |

---

## 5. Preservation Infrastructure (Pre-Port Requirements)

Before any code changes, build these safety nets:

### 5.1 Git Baseline

```bash
git tag pre-port-baseline    # Tag current state on master
git checkout -b feature/as3-faithful-port master
```

### 5.2 Replay Oracle (2,127 replays)

Run all 2,127 Master Bot replays through the current engine. Record:
- Per-replay: pass/fail, turn count, final game state hash
- Aggregate: pass rate, failure categories

This becomes the regression baseline. After the port, the same test must pass at least as many replays (target: significantly more).

### 5.3 Feature Extraction Snapshots (1,000 positions)

Extract neural net features from 1,000 diverse game positions using the current engine. After the port, re-extract and diff. Any feature vector changes indicate behavioral divergence.

### 5.4 Action Legality Oracle (10,000 positions)

For 10,000 game states, record the complete set of legal actions. After port, verify identical legal action sets. This catches subtle rule changes that might not surface in replay validation.

### 5.5 Dual-Engine Test Harness

A test mode that runs both old and new engines in parallel on the same game, comparing:
- Legal actions at each decision point
- Game state after each action
- Game outcome

This is the most powerful validation tool but requires keeping the old code accessible (e.g., in a separate namespace or via the pre-port binary).

---

## 6. Migration Strategy

### Phase 1: Infrastructure (sessions 1-2)
- Create branch from master
- Build all 4 oracles (replay, feature, legality, dual-engine)
- Verify oracles produce stable baseline measurements

### Phase 2: Core Port (sessions 3-7)
Port in dependency order:
1. **Constants & enums** — Align C.as constants with C++ enums
2. **Card/Inst** — Port instance management (Inst.as → Card.cpp)
3. **processMove → doAction** — Port all 16 move types, one at a time
4. **swoosh → beginTurn** — Port turn transition with single-pass architecture
5. **calculateGameOver** — Port full win/draw/stagnation detection
6. **Script execution** — Port runScriptForward (no backward needed for AI)
7. **Legal action generation** — Port from StateHelper computed properties

After each sub-step, run the replay oracle to detect regressions immediately.

### Phase 3: New Systems (sessions 7-9)
- Stagnation counter system (4 levels, 12 event types)
- Death script execution in breach/killCardByID
- Resonator/annihilator processing in beginTurn
- Spell collection, mana rot

### Phase 4: Validation (sessions 9-12)
- Full replay oracle comparison (target: >80% pass rate, up from 50.4%)
- Feature extraction diff (target: <1% positions with changed features)
- Action legality diff (target: 0 differences on valid game states)
- Performance benchmarking (target: <10% regression in games/sec)
- Tournament smoke test (100 games, verify AI still functions)

---

## 7. What We Explicitly Skip

These AS3 systems are **not ported** because they are irrelevant to competitive PvP and AI training:

| System | AS3 Lines | Reason to Skip |
|---|---|---|
| Tutorial mode flags (25 static bools) | ~50 | Campaign UI only |
| Objective/mission system | ~200 | Single-player campaign only |
| Trigger/condition evaluation (40+ types) | ~150 | Campaign scripting only |
| UI event dispatch (`SEND_*` events) | ~300 | GUI feedback only |
| Undo support (`runScriptBackward`, `MOVE_UN*`) | ~400 | C++ search uses state copy |
| Emote handling (`MOVE_EMOTE`) | ~10 | Cosmetic |
| Checkpoint/save system | ~30 | Campaign only |
| Lane/controlled lane | ~20 | Multi-lane mode unused |

Total skipped: ~1,160 lines (16.5% of AS3). This is why the C++ port will be ~3,500-4,500 lines despite AS3 being 7,021.

---

## 8. Success Criteria

| Metric | Current | Target | Stretch |
|---|---|---|---|
| Replay pass rate | 50.4% (1,072/2,127) | >80% | >90% |
| Feature extraction match | (not measured) | >99% positions identical | 100% |
| Legal action match | (not measured) | >99.5% | 100% |
| Performance (games/sec) | ~4/min/4-thread | >3.6/min (≤10% regression) | No regression |
| New divergences found | 6+ unfixed | 0 structural | — |
| Self-play data quality | Defense bug in all 722K games | Bug-free generation | — |

---

## 9. Decision

**Proceed with the faithful port.** The analysis shows:

1. **Clean API boundary** — 56 public methods, 91 dependent files, zero signature changes needed
2. **Manageable scope** — ~3,500-4,500 lines of C++ to write, translating from well-structured AS3
3. **Strong safety net** — 4 validation oracles catch regressions at every step
4. **Clear motivation** — 722K games need regeneration anyway, remaining 6+ divergences resist patching
5. **Bounded risk** — worst case is reverting to the tagged baseline

**Next step:** Build preservation infrastructure (Phase 1) on a new branch from master.
