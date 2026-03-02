# Engine Logic Audit: C++ vs Decompiled SWF (ActionScript 3)

> **Purpose**: Systematically compare the C++ Prismata engine (`source/engine/`) against the
> decompiled ground-truth client engine (`prismata_decompiled/scripts/mcds/engine/`) to find
> game rule divergences that could corrupt AI training data or produce incorrect game outcomes.

---

## Why This Matters

The defense-reset bug (GameState.cpp:1289-1307) was only discovered by accident. It gave
~40-60% extra defense per Defense phase across 722K self-play games. The replay validation
pipeline (55.7% pass rate) couldn't catch it because replays record player actions, not game
state — the bug makes MORE moves legal, it doesn't break existing ones.

**Only a logic-level comparison against the ground truth can find this class of bug.**

We have the ground truth: 12,457 lines of ActionScript 3 in `prismata_decompiled/scripts/mcds/engine/`
vs 3,957 lines of C++ in `source/engine/`. The AS3 code IS the real Prismata game engine
(compiled to AVM2 bytecode via CrossBridge in the Adobe AIR client).

---

## Scope

### In Scope (game rules that affect AI training)
- Phase transitions and turn lifecycle
- Blocking eligibility and defense calculation
- Ability use, status changes, and costs
- Chill/freeze mechanics
- Damage, breach, and overkill
- Wipeout detection
- Resource production and payment
- Frontline/melee mechanics
- Lifespan, delay, and construction time
- Card creation via scripts (buy/ability)
- Game over conditions and stagnation

### Out of Scope (no AI impact)
- UI/animation/display logic (Controller.as)
- Undo system (AS3 has full undo, C++ has partial — by design)
- Raid/mission mode (RaidAnalyzer.as)
- Emotes, chat, cosmetics
- Network protocol
- Sound/visual events (SEND_* dispatches)

---

## File Mapping

| Game Logic Area | AS3 Ground Truth | C++ Implementation |
|---|---|---|
| Main game state machine | `State.as` (4,490 lines) | `GameState.cpp` (2,388 lines) |
| Card instance (runtime) | `Inst.as` (504 lines) | `Card.cpp` (~950 lines) |
| Card type (definition) | `Card.as` (753 lines) | `CardType.cpp` + `CardTypeInfo.cpp/h` |
| Computed properties | `StateHelper.as` (649 lines) | Inline in `GameState.cpp` |
| Constants | `C.as` (300 lines) | `Constants.h`, `CardType.h` |
| Resource management | `Mana.as` (180 lines) | `Resources` class |
| Game analysis | `Analyzer.as` (662 lines) | No direct equivalent (AI layer) |
| End-turn processing | `EndTurnObject.as` (350 lines) | Part of `GameState::endPhase()` |

### Key Naming Differences

| Concept | AS3 Name | C++ Name |
|---|---|---|
| Card status | `role` (string: "default"/"assigned"/"inert"/"sellable") | `CardStatus` enum (Default/Assigned/Inert) + `m_sellable` bool |
| Tapped/used ability | `ROLE_ASSIGNED` | `CardStatus::Assigned` |
| Chill damage | `disruptDamage` | `m_currentChill` |
| Frozen check | `disruptDamage >= damageItCanTake + damage` | `currentChill >= currentHealth` |
| Attack resource | `turnMana.attack` (MANA_A=5) | `Resources::Attack` |
| Breach all units | `glassBroken` flag + action phase | Separate `Phases::Breach` phase |
| Swoosh/end turn | `swoosh()` function call | `Phases::Swoosh` phase |
| Frontline kill | `MOVE_MELEE` | `ASSIGN_FRONTLINE` |
| Unit death | `deadness` string ("alive"/"blocked"/"breached"/...) | `AliveStatus` + `CauseOfDeath` enums |
| Can block when tapped | `card.assignedBlocking` (Boolean) | `CardTypeInfo::assignedBlocking` (bool) |
| Can block normally | `card.defaultBlocking` (Boolean) | `CardTypeInfo::defaultBlocking` (bool) |

---

## Audit Areas (Priority Order)

### P0 — Critical (directly affect game outcomes in training)

#### A1: Blocking Eligibility & Defense Calculation
**KNOWN BUG HERE.** The defense-reset at GameState.cpp:1289-1307 already found.
But we should verify the ENTIRE blocking chain:

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Blocker eligibility filter | StateHelper.as:179-186 | Card::canBlock() L484-512 | HIGH |
| Blocking state on ASSIGN | State.as:1451 `inst.blocking = card.assignedBlocking` | Status set to Assigned in Card::useAbility() L798 | **KNOWN BUG** |
| Blocking state on UNASSIGN | State.as:1539 `inst.blocking = card.defaultBlocking` | No explicit UNASSIGN | N/A (AI doesn't undo) |
| Blocking state on swoosh | State.as:2706 `inst.blocking = card.defaultBlocking` | Card::beginTurn() resets status | MEDIUM |
| Total defense calc | StateHelper.as:434-437 `sum(damageItCanTake)` | `getTotalAvailableDefense()` | HIGH |
| Lifespan-1 blocker exclusion | StateHelper.as (lifespan==1 can't block) | Check if C++ has this | **HIGH** |
| Frozen unit blocking | State.as:1497 `disruptDamage >= damageItCanTake` | Card::isFrozen() `chill >= health` | MEDIUM |

**Key question**: Does the AS3 engine exclude lifespan-1 units from blocking? If so, does C++?

#### A2: Chill/Freeze Formula
The freeze threshold formulas differ in representation:
- AS3: `disruptDamage >= damageItCanTake + damage` where `damageItCanTake = health - (fragile ? 0 : damage)`
- C++: `currentChill >= currentHealth`

**These might be equivalent** (if C++ `currentHealth` already accounts for damage), but needs verification.
If fragile units handle damage differently, the freeze threshold could diverge.

#### A3: Wipeout / Breach Transition
- AS3: Uses `glassBroken` flag within Action phase, separate `wipedOut[]`/`breached[]`/`overkilled[]` vectors
- C++: Separate `Phases::Breach` phase, `canWipeout()` check at Action→Breach transition

**Risk**: The phase boundary is architecturally different. Need to verify that `blockWithAllBlockers()`
in C++ produces the same result as the AS3's `MOVE_WIPEOUT` handling.

#### A4: Damage Application (Fragile vs Non-Fragile)
- AS3: `damageItCanTake = health - (fragile ? 0 : damage)` — fragile ignores accumulated damage
- C++: `Card::canBreachFor()` at L355-372 — check fragile branch

**Risk**: Fragile unit damage tolerance could differ, changing breach/overkill decisions.

### P1 — High (affect game flow)

#### B1: Phase Transition Sequence
- AS3: Action → Confirm/Defense → Swoosh → next Action
- C++: Action → Breach(if wipeout) → Confirm → Defense(if attack) → Swoosh → next Action

The C++ has **5 phases** vs AS3's **3 phases + functions**. Need to verify the linearized
C++ phase machine produces identical state transitions.

#### B2: Begin-Turn Resource Reset
- AS3 swoosh: Clears damage, disruptDamage, decrements constructionTime/delay/lifespan, resets role/blocking, heals, recharges, runs beginOwnTurnScript
- C++ beginTurn: Resets resources, calls Card::beginTurn() on each card

**Risk**: Order of operations matters. If lifespan decrement kills a unit before its
beginOwnTurnScript runs, resources could differ.

#### B3: Ability Use Side Effects
- AS3: ASSIGN deducts healthUsed, chargeUsed, pays abilityCost, runs abilitySac, runs abilityScript
- C++: Card::useAbility() + GameState::doAbilityUseAction()

**Risk**: If the order of deductions differs (health before charge? cost before sac?), edge
cases with exactly-enough resources could diverge.

#### B4: Snipe Mechanics
- AS3: `deadness = C.DEADNESS_SNIPED` immediately
- C++: Card killed with CauseOfDeath::Sniped

**Risk**: Does a sniped unit's defense get removed from the total immediately? Does it
trigger death scripts? Order matters.

### P2 — Medium (edge cases)

#### C1: Stagnation / Draw Detection
- AS3: Complex counter system with `incrementTurnNoProgressCounters()`, `resetTurnNoProgressCounters(level)`, `colorIsStagnated(color)`
- C++: Check if equivalent system exists

**Risk**: Different stagnation rules → different game lengths → different training outcomes.

#### C2: Construction Time / Delay Interaction
- AS3: `constructionTime` and `delay` are separate fields, both decrement in swoosh
- C++: `m_currentDelay` and `isUnderConstruction()` — verify interaction

#### C3: Health Gained / Healing Cap
- AS3: `health = Math.min(health + card.healthGained, card.healthMax)` during swoosh
- C++: Card::beginTurn() — verify healing is capped

#### C4: Charge System
- AS3: `charge = Math.min(charge + card.chargeGained, card.chargeMax)`
- C++: Verify charge gain and cap

#### C5: Supply Tracking
- AS3: `turnSupply[]` tracks available copies, decremented on buy
- C++: Verify supply enforcement (legendary=1, rare limits)

### P3 — Low (unlikely to affect training)

#### D1: Resonance / Buildtime Reduction
- AS3: Special swoosh processing for resonance
- C++: Verify if resonance exists

#### D2: Invulnerability
- AS3: Newly bought units are invulnerable
- C++: Check invulnerability during construction

#### D3: Mass Chill Scripts
- AS3: Some scripts have `massChill` property
- C++: Verify mass chill implementation

---

## Execution Strategy

### Option A: Manual Audit (Current Context)
- One auditor reads AS3 and C++ side by side for each area
- ~2-4 hours of focused comparison
- Best for P0 items where nuance matters
- Risk: human error, fatigue

### Option B: Automated Cross-Reference (New Tool)
- Write a Python script that extracts key logic patterns from both codebases
- Generate a comparison report
- Better coverage but may miss semantic differences
- Risk: pattern matching can't understand intent

### Option C: Test-Driven Audit (Recommended)
- For each audit area, construct specific game states that exercise the logic
- Run the same state through both engines (AS3 via replay, C++ via --suggest or tournament)
- Compare outputs
- **Most reliable** but requires both engines to be runnable
- The AS3 engine runs in the live Prismata client — we can use F6 state export to capture
- Problem: AS3 client may not be easy to drive programmatically

### Option D: Hybrid (Recommended for our situation)
1. **Manual P0 audit first** — Read AS3 and C++ side by side for the 4 critical areas
2. **Document each finding** as a specific test case
3. **Verify findings in GUI** where possible (visual spot-check)
4. **Create regression tests** in C++ for confirmed divergences

---

## Recommended Execution Plan

### Phase 1: P0 Manual Audit (1 context, ~2 hours)
Compare AS3 vs C++ for:
- [ ] A1: Full blocking chain (beyond the known bug)
- [ ] A2: Chill/freeze threshold formula
- [ ] A3: Wipeout/breach transition logic
- [ ] A4: Fragile unit damage handling

### Phase 2: P1 Audit (1 context, ~1-2 hours)
- [ ] B1: Phase transition sequence
- [ ] B2: Begin-turn resource reset order
- [ ] B3: Ability use side effects order
- [ ] B4: Snipe mechanics

### Phase 3: Fix & Regression Tests
- [ ] Apply defense-reset fix (already planned)
- [ ] Fix any new divergences found
- [ ] Write C++ game rule regression tests
- [ ] Run 100-game tournament to verify

### Phase 4: P2/P3 Sweep (optional, if time permits)
- [ ] Stagnation, construction, healing, charge, supply, resonance

---

## How to Use This Plan

**For a new Claude Code context**: Paste this plan along with the defense-reset-fix-handoff.md.
The auditor should:

1. Read the AS3 files directly (they're in the repo at `prismata_decompiled/scripts/mcds/engine/`)
2. Read the C++ files side by side
3. For each audit area, document: "AS3 does X at line Y, C++ does Z at line W"
4. Flag any divergence with severity assessment
5. Do NOT modify any code — report findings only

**CAN read**: All files in both `prismata_decompiled/` and `source/engine/`
**CANNOT modify**: Any engine code (same restrictions as defense-reset-fix-handoff.md)

---

## Already-Known Divergences

| # | Area | AS3 Behavior | C++ Behavior | Impact | Status |
|---|---|---|---|---|---|
| 1 | Blocking after ability use | `inst.blocking = card.assignedBlocking` (per-card) | Blanket status reset to Default/Inert before Defense | **CRITICAL** — 40-60% extra defense | Fix planned |
| 2 | Phase model | 3 phases + swoosh function | 5 explicit phase enum values | Architectural — need to verify equivalence | Audit needed |
| 3 | Sellable role | Explicit "sellable" role in AS3 | `m_sellable` bool, not part of CardStatus enum | Unknown — verify sell/undo interaction | Audit needed |
| 4 | Undo system | Full undo for every move type | Only UNDO_BREACH | By design — AI doesn't need undo | Low risk |

---

## Reference: Codebase Sizes

| Codebase | Files | Lines | Purpose |
|---|---|---|---|
| AS3 engine | 25 files | 12,457 lines | Ground truth (decompiled client) |
| C++ engine (core) | ~8 files | ~3,957 lines | Reimplementation for AI |
| C++ engine (full) | ~20 files | ~6,000 lines | Including AI integration |

The C++ engine is intentionally smaller — it implements game rules for AI search, not for
a full game client. Some AS3 features (undo, display, raid mode) are correctly omitted.
The audit focuses on features that ARE implemented and whether they match.
