# Engine Logic Audit Plan — External Review Context Document

---

## 1. Reviewer Brief

You are receiving two documents:

1. **This context document** — background, architecture, and domain knowledge
2. **The plan** (`engine-logic-audit-plan.md`) — a proposed systematic comparison of two game engine implementations

**Your role**: Critically analyze the audit plan. Identify weaknesses, risks, missing areas, better approaches, unnecessary work, and things worth preserving. Be specific and actionable — reference section names or step numbers from the plan.

**Important constraints**:
- You do NOT have direct codebase access. This document is your only window into the code. Flag where you feel uncertain due to limited visibility.
- The plan author has full codebase access and will validate suggestions against real code during the meta-review.
- Don't rubber-stamp. The goal is to find what we missed, especially divergences that could silently corrupt AI training data.

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

---

## 2. Project Overview

**PrismataAI** is a C++ game engine and AI system for **Prismata**, a deterministic, perfect-information, turn-based strategy card game by Lunarch Studios. Think chess-like decision making applied to a resource-management/unit-combat game with ~105 distinct unit types.

The project reimplements Prismata's game rules in C++ for AI search (Alpha-Beta, UCT/MCTS) and trains a neural network via self-play to evaluate board positions. The C++ engine was written by David Churchill (academic researcher) as part of published game AI research, NOT by the original game developer.

**Current stage**: Mature self-play training pipeline. ~722,000 self-play games generated. Neural net achieves 51.9% win rate against the strongest built-in AI. Active development on training improvements and tooling.

**The crisis**: A critical game rule bug was discovered in the C++ engine — a 19-line code block that resets card statuses before the Defense phase, allowing tapped (ability-used) units to incorrectly block. This gives ~40-60% extra defense per Defense phase. All 722K training games were played with this bug. The bug was found by accident during code review, NOT by any automated validation.

**The proposal**: Since we now have the **decompiled source code of the real Prismata client** (ActionScript 3, from the Adobe AIR/Flash client), we can systematically compare our C++ engine against the ground truth to find other silent divergences before they corrupt more training data.

**Team**: Solo developer + Claude Code AI assistant. No timeline pressure, but cost-conscious (cloud compute budget is limited).

---

## 3. Architecture & Tech Stack

### Languages & Frameworks
- **C++ (x86)**: Game engine + AI search. Built via MSBuild/Visual Studio. ~8,000 lines in `source/engine/`.
- **ActionScript 3**: Decompiled real Prismata client engine. ~12,500 lines in `prismata_decompiled/scripts/mcds/engine/`. Read-only reference — never modified.
- **Python**: Training pipeline (PyTorch), tooling, analysis scripts.
- **JSON**: Card definitions (`cardLibrary.jso`, 105+ units), tournament configs, game state serialization.

### High-Level Architecture

```
┌──────────────────────────────────────────────┐
│              TRAINING PIPELINE               │
│  Self-play data → PyTorch → Weight export    │
└────────────────────┬─────────────────────────┘
                     │ neural_weights.bin
┌────────────────────▼─────────────────────────┐
│              C++ AI SYSTEM                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ GameState │  │ AI Search│  │ NeuralNet │  │
│  │ (engine) │──│ (AB/UCT) │──│ (eval)    │  │
│  └──────────┘  └──────────┘  └───────────┘  │
│       ▲                                      │
│       │ Game rules                           │
│  ┌────┴─────┐                                │
│  │cardLib.  │ (105 unit definitions)         │
│  │jso       │                                │
│  └──────────┘                                │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│     GROUND TRUTH (decompiled, read-only)     │
│  State.as ← THE authoritative game rules     │
│  Inst.as, Card.as, StateHelper.as, C.as      │
│  ~12,500 lines ActionScript 3                │
└──────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **C++ engine is a SUBSET of the real game**: It implements only what the AI needs — no undo (except breach), no UI events, no raid/mission mode, no cosmetics. This is intentional and correct.

2. **Phase model differs structurally**: The real game (AS3) has 3 named phases (Action, Defense, Confirm) with "Swoosh" as a processing function call. The C++ engine has 5 explicit phase enum values (Action, Defense, Breach, Confirm, Swoosh). The linearized C++ phases SHOULD produce the same state transitions but this architectural difference creates risk for divergence.

3. **Card status vs blocking boolean**: The real game tracks `inst.blocking` as a separate Boolean field, set from `card.assignedBlocking` or `card.defaultBlocking` at specific transition points. The C++ engine derives blocking eligibility from `CardStatus` (Default/Assigned/Inert) via `canBlock(status == Assigned)`. This is the root cause of the known blocking bug — the two approaches diverge when a blanket status reset occurs.

4. **No stagnation detection in C++**: The real game has complex stagnation counters (`incrementTurnNoProgressCounters`, `colorIsStagnated`) and an "all opponent units doomed" (lifespan-1) instant-win rule. The C++ engine's `calculateGameOver()` only checks if either player has 0 cards.

---

## 4. Codebase Map

### C++ Engine (`source/engine/`, ~7,936 lines total)

| File | Lines | Role |
|---|---|---|
| `GameState.cpp` + `.h` | ~2,550 | **Core game state machine** — phase transitions, action execution, legal move checking, turn lifecycle |
| `Card.cpp` + `.h` | ~1,100 | **Card instance** — runtime state (health, chill, status, damage), blocking eligibility, ability use |
| `CardType.cpp` + `.h` | ~400 | **Card type** — static properties accessor (delegates to CardTypeInfo) |
| `CardTypeInfo.cpp` + `.h` | ~350 | **Card type data** — JSON deserialization of unit definitions from cardLibrary.jso |
| `Script.cpp` + `.h` | ~250 | **Ability/buy scripts** — effect execution (create units, grant resources, sacrifice) |
| `Resources.cpp` + `.h` | ~200 | **Resource management** — Gold, Green, Blue, Red, Energy, Attack |
| `Action.cpp` + `.h` | ~150 | **Action representation** — player, type, target |
| `Constants.h` | ~37 | **Enums** — Phases, Players, SupplyAmounts, EvaluationMethods |
| Other files | ~2,900 | CardData, CardBuyable, Move, Condition, CreateDescription, etc. |

### AS3 Engine (`prismata_decompiled/scripts/mcds/engine/`, ~12,457 lines total)

| File | Lines | Role |
|---|---|---|
| `State.as` | 4,490 | **Core game logic** — equivalent to GameState.cpp |
| `Controller.as` | 2,574 | **Game controller** — UI interaction layer (OUT OF SCOPE) |
| `Card.as` | 753 | **Card definition** — static properties (equivalent to CardType/CardTypeInfo) |
| `StateHelper.as` | 649 | **Computed properties** — defense totals, wipeout analysis, resource projections |
| `Analyzer.as` | 662 | **Game analysis** — strategic evaluation (no C++ equivalent, AI layer) |
| `Inst.as` | 504 | **Card instance** — runtime state (equivalent to Card.cpp) |
| `EndTurnObject.as` | 350 | **Turn processing** — end-of-turn result packaging |
| `C.as` | 300 | **Constants** — string-based enums for roles, phases, moves |
| `Mana.as` | 180 | **Resources** — 6 mana types |
| Other files | ~1,995 | RaidAnalyzer, Script, Trigger, Rndm, Click, etc. |

### Shared Data

| File | Role |
|---|---|
| `bin/asset/config/cardLibrary.jso` | Master unit definitions — 105+ units with costs, stats, abilities, blocking flags |
| `bin/asset/config/config.txt` | Tournament and AI player configurations |

---

## 5. Relevant Existing Patterns & Conventions

### How Card Properties Work

Each of the ~105 unit types in Prismata has properties defined in `cardLibrary.jso`:

```json
{
    "cardName": "Drone",
    "defaultBlocking": 1,      // CAN block when not tapped
    "assignedBlocking": 0,     // CANNOT block when tapped (ability used)
    "fragile": 0,              // Non-fragile (damage accumulates, doesn't reduce health directly)
    "healthMax": 1,
    "lifespan": -1,            // Permanent (-1 = never expires)
    "buyCost": { "money": 3 },
    "beginOwnTurnScript": { "receive": { "money": 1 } },
    "abilityScript": { "receive": { "money": 1 } }
}
```

Of 93 units with blocking capability:
- **91 units**: `assignedBlocking: 0` — cannot block after using ability (standard rule)
- **2 units**: `assignedBlocking: 1` — CAN still block after ability (Fusion, Infestor — exceptions)

### How Status/Blocking Works

**In the real game (AS3)**:
```
Unit created → blocking = card.defaultBlocking
Unit uses ability → role = ASSIGNED, blocking = card.assignedBlocking
End of turn (swoosh) → role = DEFAULT/INERT, blocking = card.defaultBlocking
```

The `blocking` Boolean is a first-class field on each unit instance (`Inst.as`). It is explicitly set at each transition point from the card type's `assignedBlocking` or `defaultBlocking` property.

**In the C++ engine**:
```
Unit created → status = Default
Unit uses ability → status = Assigned
Begin turn → status = Default/Inert (proper reset)
```

Blocking eligibility is DERIVED: `Card::canBlock()` → `CardType::canBlock(status == Assigned)` → returns `assignedBlocking` if assigned, else `defaultBlocking`.

**The divergence**: The C++ engine added a 19-line block that resets ALL card statuses from Assigned to Default/Inert at the START of the Defense phase (before blocking decisions). This makes every unit appear "not tapped" during Defense, allowing all 91 units with `assignedBlocking: 0` to incorrectly block.

### How Chill/Freeze Works

Chill is the game mechanic that prevents units from blocking by "freezing" them.

**In the real game (AS3)**:
- Each unit has `disruptDamage` (chill damage) and `damage` (combat damage) fields
- `damageItCanTake` = `health - (fragile ? 0 : damage)` — how much more damage the unit can absorb
- Frozen when: `disruptDamage >= damageItCanTake + damage`
- Simplifies to: `disruptDamage >= health` for non-fragile undamaged units
- For damaged non-fragile units: `disruptDamage >= health - damage + damage` = `disruptDamage >= health`
- For fragile units: `disruptDamage >= health + damage` (different!)

**In the C++ engine**:
- `m_currentChill` (chill damage) and `m_currentHealth` (current health, REDUCED for fragile units)
- Frozen when: `currentChill >= currentHealth`
- For fragile units that have taken damage: `currentHealth` is already reduced, so `currentChill` threshold is lower

**Potential divergence**: For fragile units that have taken damage, the freeze thresholds may differ. This needs verification during the audit.

### Testing Strategy

- **No unit tests for game rules**: The C++ engine has no formal test suite for rule correctness.
- **Replay validation** (55.7% pass rate): Replays human games through the C++ engine and checks move legality. This catches moves that SHOULD be legal but AREN'T — it does NOT catch moves that shouldn't be legal but ARE (like the blocking bug).
- **Tournament testing**: AI vs AI games check for crashes/asserts but not rule correctness.
- **The audit plan proposes creating the first game-rule regression tests**.

---

## 6. Current State & Known Issues

### What Works
- Self-play game generation at ~4 games/min/instance
- Neural net inference in C++ at ~2,000 evals/sec/core
- 51.9% win rate vs strongest built-in AI (from 3.6% pre-training)
- Tournament evaluation pipeline (EC2 fleet)
- Live game advisor and autopilot (sniffer proxy + C++ `--suggest` mode)

### The Known Bug (CRITICAL)

`GameState.cpp` lines 1289-1307: A for-loop that resets ALL cards' statuses at Defense phase start. This was introduced on Feb 13, 2026. Self-play started Feb 15. All 722K games are affected.

**Impact**: ~40-60% extra defense per Defense phase. Bug is symmetric (both players equally affected). Model learned "variant Prismata" where tapping is free — you can tap AND block. The fix is straightforward (delete the 19 lines), already planned, not yet applied.

### Other Known Issues
- **No stagnation detection**: C++ engine doesn't detect infinite loops or force draws. Real game does.
- **No "all units doomed" check**: Real game declares instant win when all opponent units have lifespan 1. C++ doesn't.
- **Phase model mismatch**: C++ uses 5 explicit phases vs AS3's 3 phases + swoosh function. Equivalence unverified.
- **Sellable role difference**: AS3 has explicit "sellable" role; C++ uses separate `m_sellable` bool.
- **Missing undo**: C++ only has UNDO_BREACH; AS3 has full undo for every move. By design (AI doesn't need undo), but means we can't use undo-based testing strategies.

### Recent Significant Changes
- Defense-reset bug investigation completed (Feb 22)
- Decompiled SWF engine discovered and integrated into repo (Feb 17)
- Post-game commentary pipeline Phase 2 shipped (Feb 22)
- Frontline penalty isolation test running on EC2 (Feb 22)

---

## 7. Context Specific to the Plan

### What the Plan Touches

The audit is **read-only** — it reads both codebases and documents divergences. No code modifications. The key files being compared:

| AS3 File | C++ File | Audit Focus |
|---|---|---|
| `State.as` (4,490 lines) | `GameState.cpp` (2,388 lines) | Phase transitions, action execution, blocking, wipeout |
| `Inst.as` (504 lines) | `Card.cpp` (~950 lines) | Status management, health/damage, chill, abilities |
| `StateHelper.as` (649 lines) | Various GameState methods | Defense calculation, offense analysis |
| `Card.as` (753 lines) | `CardTypeInfo.cpp/h` | Card property definitions |
| `C.as` (300 lines) | `Constants.h` | Enum/constant mapping |

### Why Replay Validation Didn't Catch This

The replay validation pipeline tests move LEGALITY — it replays recorded human actions and checks if each action is legal in the C++ engine. The blocking bug makes actions MORE legal (tapped units can now block), so human replays that never attempted to block with tapped units pass validation fine. The bug only manifests when the AI generates defense moves, not when replaying human games.

### Prior Approaches Considered

1. **Automated fuzzing**: Generate random game states and compare legal moves. Rejected because we'd need the AS3 engine running programmatically, which requires the Adobe AIR runtime.
2. **Differential testing via replay API**: Play games through both engines and compare outcomes. Same AS3 runtime problem.
3. **Wiki-based validation**: Compare rules against Prismata wiki pages. Rejected because the wiki is incomplete and may not match the actual implementation.
4. **Manual code audit** (the chosen approach): Most practical given that both codebases are readable source code in the same repository.

---

## 8. Scope Boundaries

### Out of Scope (non-negotiable)
- **UI/animation logic** (Controller.as) — no AI impact
- **Undo system differences** — C++ intentionally omits full undo; AI doesn't need it
- **Raid/mission mode** (RaidAnalyzer.as) — not used in self-play or tournaments
- **Network protocol** — handled by the sniffer proxy, not the engine
- **Modifying any code during the audit** — findings only, fixes are a separate step

### Fixed Constraints
- **The C++ engine IS the production engine** — we cannot replace it with the AS3 code. We can only fix divergences in C++.
- **cardLibrary.jso is shared** — both engines use the same card definitions, so card property differences are not possible (only logic differences).
- **Budget**: No cloud compute needed for the audit (it's a code reading exercise). But fixes that require regenerating training data have cost implications (~722K games = ~$250 in cloud compute).

### Accepted Trade-offs
- The C++ engine is intentionally smaller/simpler than the AS3 engine. Missing features (full undo, stagnation) are acceptable IF they don't change game outcomes.
- The audit is manual (human/AI reading code), not automated. Coverage depends on auditor thoroughness.

---

## 9. Success Criteria

1. **All P0 audit areas verified**: Blocking, chill/freeze, wipeout/breach, and fragile damage have been compared line-by-line with documented conclusions (match, diverge, or N/A).
2. **All divergences documented**: Each finding includes AS3 line reference, C++ line reference, severity, and whether it affects training data.
3. **No new CRITICAL divergences remain unaddressed**: Any bug as severe as the blocking bug is flagged for immediate fixing.
4. **Regression test cases proposed**: Each verified divergence becomes a test case spec for future C++ game rule tests.
5. **Audit findings are reproducible**: Another developer (or AI assistant) can follow the documented references and verify each conclusion.

---

## 10. Key Questions for Reviewers

1. **Is the priority ordering correct?** Are there areas rated P2/P3 that should be P0/P1, or vice versa? Could a P2 issue (like stagnation) actually corrupt training data in ways we haven't considered?

2. **Is manual audit sufficient for P0?** The plan recommends manual code reading for the most critical areas. Should we require a second pass (e.g., automated property extraction) to reduce human error? What confidence level should we demand before declaring an area "verified"?

3. **Are there audit areas we missed entirely?** The plan lists 15 areas across 4 tiers. Given the file mapping and naming dictionary, are there game mechanics or edge cases not covered? (e.g., how does the C++ engine handle simultaneous unit deaths? What about trigger ordering?)

4. **Should the "Sellable" role difference (Known Divergence #3) be higher priority?** The AS3 has 4 roles (default, assigned, inert, sellable); C++ has 3 statuses + a separate bool. This architectural difference could have subtle effects on the beginning of each turn when recently-bought units transition from sellable to their proper status.

5. **Is the execution strategy (Option D: Hybrid) the right call?** The plan recommends manual audit first, then test cases, then GUI verification. Would a different ordering (e.g., start with test case construction to force precise understanding) be more effective?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **Tapped** | A unit that has used its ability this turn. Sets status to Assigned. In real Prismata, most tapped units CANNOT block during Defense. |
| **Blocking** | Assigning a unit to absorb incoming attack damage during the Defense phase. |
| **Defense phase** | Phase where the defending player assigns blockers to absorb the attacker's damage. |
| **Action phase** | Main phase where the active player buys units, uses abilities, and attacks. |
| **Swoosh** | End-of-turn processing: reset statuses, decrement timers, produce resources, heal. In AS3 it's a function; in C++ it's an explicit phase. |
| **Breach** | When attack exceeds total defense, excess damage kills individual units (starting with the most vulnerable). |
| **Wipeout** | When attack >= total defense, ALL blockers die before individual breaching begins. |
| **Overkill** | Damage to units under construction after all active units are breached. |
| **Frontline** | Units killed during the Action phase (before Defense) by the attacking player's own attack. Called "Melee" in AS3. |
| **Chill / Disrupt** | Mechanic that prevents units from blocking by accumulating freeze damage. Called `disruptDamage` in AS3, `m_currentChill` in C++. |
| **Frozen** | A unit with enough chill damage that it can no longer block. |
| **Fragile** | A unit type where damage reduces actual health (not just accumulated damage). Affects breach thresholds and freeze calculations. |
| **Lifespan** | Number of turns a unit survives. -1 = permanent. Decremented each swoosh. Unit dies when lifespan reaches 0. |
| **Construction time** | Turns until a newly bought unit becomes active. Decremented each swoosh. |
| **Delay** | Additional wait time before a created-by-script unit becomes active. |
| **assignedBlocking** | Per-card-type Boolean: can this unit block when tapped (Assigned status)? Most units: false. Exceptions: Fusion, Infestor. |
| **defaultBlocking** | Per-card-type Boolean: can this unit block when not tapped (Default status)? Most blockers: true. |
| **cardLibrary.jso** | Master JSON file defining all ~105 unit types with costs, stats, abilities, and blocking flags. Shared between both engines. |
| **Self-play** | AI playing against itself to generate training data. Uses playout evaluation (not neural net) for game generation. |
| **OriginalHardestAI** | The strongest built-in AI. Uses Alpha-Beta search with playout evaluation. Serves as the baseline opponent for measuring neural net strength. |
| **Ground truth** | The decompiled AS3 engine from the real Prismata client. This IS the official game implementation. |
| **PRISMATA_ASSERT** | Soft assertion in C++ — prints to stdout, does NOT abort. Used throughout the engine for sanity checks. |
| **F6 state export** | In-game feature (via SWF developer patch) that copies the current game state as JSON to the clipboard. Used by the advisor/autopilot tooling. |
| **`--suggest` mode** | C++ CLI flag that reads an F6 JSON game state and outputs the AI's recommended move. Used by the live advisor overlay. |
