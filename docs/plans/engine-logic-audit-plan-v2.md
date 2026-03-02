# Engine Logic Audit: C++ vs Decompiled AS3 Ground Truth (v2)

> **Purpose**: Systematically compare the C++ Prismata engine (`source/engine/`) against the
> decompiled ground-truth client engine (`prismata_decompiled/scripts/mcds/engine/`) to find
> game rule divergences that could corrupt AI training data or produce incorrect game outcomes.
>
> **v2 changes**: Incorporates feedback from 10 external reviews + codebase validation.
> Changes marked with `<!-- CHANGED -->` comments.

---

## Why This Matters

The defense-reset bug (GameState.cpp:1289-1307) was only discovered by accident. It gave
~40-60% extra defense per Defense phase across 722K self-play games. The replay validation
pipeline (55.7% pass rate) couldn't catch it because replays record player actions, not game
state — the bug makes MORE moves legal, it doesn't break existing ones.

**Only a logic-level comparison against the ground truth can find this class of bug.**

We have the ground truth: ~12,500 lines of ActionScript 3 in `prismata_decompiled/scripts/mcds/engine/`
vs ~4,000 lines of C++ in `source/engine/`. The AS3 code IS the real Prismata game engine
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
- Game over conditions and stagnation <!-- CHANGED: Added stagnation — Reviewers 1,3,4,5,6,7,9 -->
- Script and trigger execution ordering <!-- CHANGED: Added — Reviewers 1,2,3,5,6,8,9 -->

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
| Script data | `Script.as` (104 lines) | `Script.cpp` (143 lines) |
| Trigger data | `Trigger.as` (95 lines) | No direct equivalent |
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
| Breach all units | `glassBroken` flag within Action phase | Separate `Phases::Breach` phase |
| Swoosh/end turn | `swoosh()` function call | `Phases::Swoosh` phase |
| Frontline kill | `MOVE_MELEE` | `ASSIGN_FRONTLINE` |
| Unit death | `deadness` string ("alive"/"blocked"/"breached"/...) | `AliveStatus` + `CauseOfDeath` enums |
| Can block when tapped | `card.assignedBlocking` (Boolean) | `CardTypeInfo::assignedBlocking` (bool) |
| Can block normally | `card.defaultBlocking` (Boolean) | `CardTypeInfo::defaultBlocking` (bool) |
| Instant-win (doomed) | `helper.allOppUnitsDoomed` in `checkWin()` | **Not implemented** | <!-- CHANGED: Added — Reviewers 1,3,4,7,9 -->

---

<!-- CHANGED: Added verification methodology section — Reviewers 1,2,5,6,7,10 -->
## Verification Methodology

### Completion Criteria

An audit area is **verified** when:
1. Every code path that modifies the relevant state has been traced in BOTH engines
2. AS3 function + distinctive snippet and C++ function + distinctive snippet are documented side-by-side
3. At least 2 concrete test cases (1 normal, 1 edge case) have been traced through both implementations
4. The auditor has documented a **Match**, **Mismatch**, or **Uncertain** verdict with reasoning

### Severity Rubric for Findings

| Severity | Definition | Example |
|----------|-----------|---------|
| **CRITICAL** | Changes game outcome in >5% of games | Defense-reset bug (affects every Defense phase) |
| **HIGH** | Changes game outcome in specific but common scenarios | Missing instant-win condition |
| **MEDIUM** | Theoretical divergence with rare triggering scenario | Script ordering difference for unusual unit combinations |
| **LOW** | Cosmetic or architectural difference with no gameplay impact | Different enum values for same concept |

### Required Artifacts Per P0 Area

For each P0 audit area, the auditor must produce:
1. **Code path trace**: AS3 function(s) + C++ function(s) with distinctive code snippets (not just line numbers)
2. **Test case table**: At minimum 2 cases with inputs, expected AS3 behavior, and C++ behavior
3. **Verdict**: Match/Mismatch/Uncertain with reasoning
4. **If Mismatch**: Severity rating, affected unit count estimate, test case for regression suite

### Reference Style

Use stable references throughout: `function_name() + "distinctive code snippet"` + (optional line range).
Line numbers drift when code changes. Function names and code phrases are stable.

---

## Phase 0: Prerequisite Deliverables <!-- CHANGED: New section — Reviewers 2,5,7 -->

Before starting P0 item-by-item audit, produce these foundation documents:

### P0.1: Phase Transition State Machine Diagram

Create a text-based state machine diagram for BOTH engines showing:

```
AS3 (State.as):
  Action ──[wipeout?]──► glassBroken=true (breach within Action)
  Action ──[confirm]───► Defense (if opponent has attack) ──► swoosh() ──► Action
  Action ──[confirm]───► swoosh() ──► Action (if no opponent attack)

C++ (GameState.cpp):
  Action ──[endPhase]──► Breach (if canWipeout) ──► Confirm ──► Defense ──► Swoosh ──► Action
  Action ──[endPhase]──► Confirm ──► Defense (if attack) ──► Swoosh ──► Action
  Action ──[endPhase]──► Confirm ──► Swoosh ──► Action (if no attack)
```

For each transition boundary, document:
- What state changes occur (status resets, resource clears, script execution)
- The exact function/line in each engine
- Any differences in WHEN things happen

### P0.2: Comprehensive Status Reset Scan <!-- CHANGED: New — Reviewer 10 -->

Before auditing individual areas, search for ALL status reset locations:

**C++ scan**: `grep -n "setStatus\|m_status =" source/engine/Card.cpp source/engine/GameState.cpp`
**AS3 scan**: `grep -n "inst.role =\|\.role =" prismata_decompiled/scripts/mcds/engine/State.as`

Document every location where card status changes in both engines. The known bug was ONE such location — there may be others.

### P0.3: Swoosh/beginTurn Event Timeline <!-- CHANGED: New — Reviewer 2 -->

Side-by-side timeline of what happens during turn transition:

| Step | AS3 swoosh() (State.as) | C++ beginTurn() (GameState.cpp + Card.cpp) |
|------|------------------------|-------------------------------------------|
| 1 | Reset phase to ACTION | Reset Energy, Blue, Red, Attack to 0 |
| 2 | Clear glassBroken | Clear m_canBreachFrozenCard |
| 3 | Clear damage/disruptDamage | Snapshot card list for iteration |
| 4 | Decrement constructionTime | Call Card::beginTurn() on dead cards |
| 5 | Decrement delay | Call Card::beginTurn() on live cards |
| 6 | Decrement lifespan (kill if 0) | (inside Card::beginTurn): clear sellable, damage, flags |
| 7 | Reset role (DEFAULT/INERT) | (inside Card::beginTurn): decrement lifespan, kill if 0 |
| 8 | Reset blocking to defaultBlocking | (inside Card::beginTurn): decrement delay, construction |
| 9 | Run beginOwnTurnScript | (inside Card::beginTurn): heal, set status, clear chill |
| 10 | (within same loop) | **Second pass**: run beginOwnTurnScripts on surviving cards |

**Flag any ordering differences in this timeline.** The C++ two-pass approach (all beginTurns first, then all scripts) vs AS3 single-pass (per-card processing) is a known structural difference that could cause divergence.

---

## Audit Areas (Priority Order)

### P0 — Critical (directly affect game outcomes in training)

<!-- CHANGED: Reordered — A0 (phase transitions) now FIRST — Reviewers 2,3,5,7,8,9,10 -->

#### A0: Phase Transition Sequence (was B1)

**Rationale**: All other P0 items depend on knowing phase boundaries match. The known defense-reset bug IS a phase-boundary bug.

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Phase enumeration | State.as `phase` field (C.PHASE_ACTION, etc.) | `Phases::` enum in Constants.h | MEDIUM |
| Action → Breach/Confirm transition | State.as wipeout check (`wouldWipeout` getter) | `GameState::endPhase()` Action case, `canWipeout()` | HIGH |
| Confirm → Defense/Swoosh transition | State.as (confirm logic) | `GameState::endPhase()` Confirm case (line ~1383) | HIGH |
| Defense → Swoosh transition | State.as (defense ends → `swoosh()` call) | `GameState::endPhase()` Defense → `beginPhase(Swoosh)` | HIGH |
| Swoosh → Action transition | State.as (`swoosh()` returns → next action) | `GameState::endPhase()` Swoosh → `beginPhase(Action)` | HIGH |
| Turn number increment | State.as (when does turn++ happen?) | `GameState::endPhase()` Confirm case, `m_turnNumber++` | MEDIUM |
| Game-over check timing | State.as `checkWin()` (when called?) | `calculateGameOver()` at Confirm (line ~1394) | HIGH |

**Concrete test case**: Trace a full turn cycle with attack > 0 (triggers Defense) through both engines. Verify identical state at each phase boundary.

#### A1: Blocking Eligibility & Defense Calculation

**KNOWN BUG HERE.** The defense-reset at GameState.cpp:1289-1307.

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Blocker eligibility filter | State.as `inst.blocking` field + assignment logic | `Card::canBlock()` at Card.cpp | HIGH |
| Blocking state on ASSIGN | State.as:~1451 `inst.blocking = card.assignedBlocking` | Status set to Assigned in `Card::useAbility()` | **KNOWN BUG** |
| Blocking state on swoosh | State.as:~2700 `inst.blocking = card.defaultBlocking` | `Card::beginTurn()` resets status (Card.cpp:~632) | MEDIUM |
| Total defense calc | StateHelper.as:~434 `sum(damageItCanTake)` | `getTotalAvailableDefense()` | HIGH |
| Frozen unit blocking | State.as:~1497 `targetInst.blocking = false` | `Card::canBlock()` calls `isFrozen()` | MEDIUM |
| assignedBlocking per card type | Inst.as constructor + Card.as | `CardTypeInfo::assignedBlocking` loaded from cardLibrary.jso | HIGH |

**Key finding from codebase validation**: Lifespan-1 units CAN block in both engines (no lifespan check in blocking logic). The AS3 StateHelper lifespan-1 exclusion (lines 191, 385) is for ANALYSIS only, not game rules.

**Concrete test cases**:
1. **Normal**: Drone (assignedBlocking=false) uses ability → enters Defense → verify cannot block
2. **Edge**: Unit with assignedBlocking=true (e.g., Infusion Grid) uses ability → enters Defense → verify CAN block

<!-- CHANGED: Added chill formula proof requirement — Reviewers 1,3,5,7,8,9 -->
#### A2: Chill/Freeze Formula (Mathematical Proof Required)

The freeze threshold formulas use different representations. The auditor **must** produce a 4-case verification table:

| Case | AS3 Formula | C++ Formula | Match? |
|------|-------------|-------------|--------|
| Non-fragile, no damage | `disruptDamage >= health` | `currentChill >= m_currentHealth` (where m_currentHealth = startingHealth) | Verify |
| Non-fragile, with damage | `disruptDamage >= (health - damage) + damage` = `disruptDamage >= health` | `currentChill >= m_currentHealth` (where m_currentHealth = startingHealth - damage) | **Verify — representations differ** |
| Fragile, no damage | `disruptDamage >= health + 0` | `currentChill >= m_currentHealth` (where m_currentHealth = startingHealth) | Verify |
| Fragile, with damage | `disruptDamage >= health + damage` | `currentChill >= m_currentHealth` (fragile health tracking?) | **HIGH RISK — may diverge** |

**Key code**: AS3 `damageItCanTake` definition in Inst.as/StateHelper.as. C++ `Card::isFrozen()` = `currentChill() >= currentHealth()` (Card.cpp:290-293), `currentHealth()` returns `m_currentHealth` (Card.cpp:320-322).

**Concrete test cases**:
1. Non-fragile Wall (3 HP, 1 damage taken, 2 chill) — should NOT be frozen
2. Non-fragile Wall (3 HP, 0 damage, 3 chill) — should be frozen
3. Fragile unit (3 HP, 1 damage taken, 2 chill) — verify threshold
4. Fragile unit (3 HP, 0 damage, 3 chill) — should be frozen

#### A3: Wipeout / Breach Transition & Ordering <!-- CHANGED: Expanded — Reviewers 2,3,8 -->

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Wipeout threshold | State.as `wouldWipeout` getter (`attack >= oppDefense`) | `GameState::canWipeout()` | HIGH |
| glassBroken vs Phases::Breach | State.as `glassBroken` flag within Action | Separate `Phases::Breach` enum value | HIGH |
| Breach unit ordering | State.as death processing iteration | `GameState` breach loop iteration | HIGH |
| Death script timing during breach | State.as `deadness` assignment + deleteInst | `Card::kill()` + `m_cards.removeKilledCards()` | HIGH |
| Overkill handling | State.as overkill damage after breach | C++ breach phase continuation | MEDIUM |

**Concrete test cases**:
1. Attack = total defense exactly → wipeout triggers → verify all blockers die
2. Attack > total defense → breach damage applied → verify which unit(s) get breached and in what order

#### A4: Damage Application (Fragile vs Non-Fragile)

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Fragile damage tolerance | Inst.as/StateHelper.as `damageItCanTake` with fragile check | `Card::canBreachFor()` at Card.cpp:~355 | HIGH |
| Non-fragile cumulative damage | Inst.as `damage` field accumulation | `m_currentHealth` reduction (Card.cpp:~423) | MEDIUM |
| Fragile death threshold | State.as fragile breach handling | C++ fragile branch in breach | HIGH |

<!-- CHANGED: New P0 item — Reviewers 1,3,4,7,9 (validated by codebase) -->
#### A5: Game-Over Conditions (Including "All Units Doomed")

**CONFIRMED MISSING from C++.** AS3 `checkWin()` (State.as:~3298) has 4 win conditions:
1. Own alive, opponent dead → current player wins
2. Own dead, opponent alive → opponent wins
3. Both dead → mutual elimination draw
4. **All opponent units doomed** (`helper.allOppUnitsDoomed`) → current player wins

C++ `calculateGameOver()` (GameState.cpp:1207-1213) has ONLY:
```cpp
return p1Cards == 0 || p2Cards == 0;
```

**Missing**: Conditions 3 (mutual elimination draw) and 4 (all units doomed).

C++ has `m_turnLimit = 200` (Game.h:17) as a stagnation safety net, but this is cruder than AS3's 4-level progress-tracking system.

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| All-units-doomed instant-win | State.as `checkWin()` + `helper.allOppUnitsDoomed` | `calculateGameOver()` — **MISSING** | **CRITICAL** |
| Mutual elimination draw | State.as `COLOR_DRAW_MUTUAL_ELIMINATION` | Not implemented (both-dead case) | HIGH |
| Game-over check timing | State.as `checkWin()` call location | `calculateGameOver()` at Confirm phase end | MEDIUM |

**Concrete test cases**:
1. One player has only lifespan-1 units remaining → AS3 ends immediately, C++ continues 1 more turn
2. Both players reach 0 units simultaneously → verify draw vs win

### P1 — High (affect game flow)

<!-- CHANGED: New P1 item — Reviewers 1,2,3,5,6,8,9 (validated: ordering difference confirmed) -->
#### B1: Script/Trigger Execution Ordering

C++ runs beginOwnTurnScripts in a **second pass** after all Card::beginTurn() calls (GameState.cpp:1256-1273).
AS3 swoosh processes cards in a **single pass** — lifespan/delay/script per card.

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| beginOwnTurnScript timing | State.as swoosh (intermixed with lifespan/delay) | GameState::beginTurn() second pass (line ~1256) | **HIGH — structural difference** |
| Script execution within ability use | State.as ASSIGN handler | `GameState::doAbilityUseAction()` | HIGH |
| Pay → sac → create → receive order | State.as ability resolution | GameState ability resolution | HIGH |
| Death script execution | State.as `deleteInst()` triggers | `Card::kill()` + script | MEDIUM |
| Trigger conditions evaluation | Trigger.as `conditions` + State.as | No direct equivalent in C++ | MEDIUM |

**Concrete test cases**:
1. Unit A (lifespan-2) has beginOwnTurnScript producing gold. Unit B costs that gold. In AS3 single-pass, does A produce before B's script runs? In C++ two-pass, does the order differ?
2. Ability that sacrifices unit X and creates unit Y — verify sac happens before create in both engines.

#### B2: Begin-Turn Resource Reset Order

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Resource types cleared | State.as swoosh (attack, mana types) | GameState::beginTurn() lines 1220-1223 (Energy, Blue, Red, Attack) | MEDIUM |
| Gold persistence | State.as (gold NOT cleared at swoosh) | Gold NOT in the reset list | Verify match |
| Green persistence | State.as (green treatment) | Green NOT in the reset list | Verify match |
| Resource clear vs card beginTurn order | State.as (resources cleared when?) | Resources cleared BEFORE card processing | MEDIUM |
| Lifespan decrement vs script timing | State.as swoosh (lifespan in same loop as scripts) | Card::beginTurn() lifespan (line ~593) vs scripts (second pass, line ~1256) | **HIGH** |

#### B3: Ability Use Side Effects Order

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Health cost deduction | State.as ASSIGN handler | `Card::useAbility()` | MEDIUM |
| Charge cost deduction | State.as charge handling | `Card::useAbility()` charge logic | MEDIUM |
| Ability cost (resources) | State.as mana payment | GameState ability cost payment | MEDIUM |
| Self-sacrifice timing | State.as `abilitySac` | GameState sac processing | HIGH |
| Script execution (create/receive) | State.as abilityScript | GameState `runScript()` | HIGH |

#### B4: Snipe Mechanics

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Immediate vs deferred death | State.as `deadness = C.DEADNESS_SNIPED` | `Card::kill(CauseOfDeath::Sniped)` | MEDIUM |
| Defense total update after snipe | State.as defense recalculation | getTotalAvailableDefense() after kill | HIGH |
| Snipe during defense phase | State.as snipe in defense context | C++ snipe action legality | MEDIUM |

<!-- CHANGED: New P1 item — Reviewers 1,3,5,6,7,9,10 -->
#### B5: Sellable Role Transition

C++ uses `m_sellable` bool (Card.cpp:206, cleared at beginTurn line 577).
AS3 uses `role = "sellable"` string (Inst.as, cleared at swoosh).

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| When sellable is set | State.as buy handler | Card constructor (Card.cpp:~206) | MEDIUM |
| When sellable clears | State.as swoosh role reset | Card::beginTurn() line 577 | MEDIUM |
| Can sellable units block? | State.as — check blocking with sellable role | C++ — canBlock() with m_sellable=true | HIGH |
| Can sellable units use abilities? | State.as | C++ canUseAbility() | MEDIUM |
| Sellable units in defense total | StateHelper.as defense calc | getTotalAvailableDefense() | MEDIUM |

<!-- CHANGED: New P1 item — Reviewers 1,3,4,5,6,7,9 -->
#### B6: Stagnation Detection System

AS3 has 4-level stagnation counters (State.as:~1291-1368, cutoffs [2,8,20,40]).
C++ has only `m_turnLimit = 200` (Game.h:17).

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Progress counter logic | State.as `incrementTurnNoProgressCounters()` | **Not implemented** | HIGH |
| Stagnation check | State.as `colorIsStagnated()` | `m_turnsPlayed >= m_turnLimit` (Game.cpp:90) | HIGH |
| Draw claim mechanism | State.as stagnation → draw | Game.cpp turn limit → game over | MEDIUM |
| What counts as "progress" | State.as `resetTurnNoProgressCounters(level)` | N/A | HIGH |

**Impact assessment**: The 200-turn limit prevents infinite games but is much cruder than AS3's progress-tracking system. Games near economic stalemate would run longer in C++ before terminating. Affects value targets in late-game training positions.

<!-- CHANGED: New P1 item — Reviewers 2,3,8,9 -->
#### B7: Simultaneous Death Ordering

When multiple units die in the same phase (breach, swoosh, ability scripts):

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Death processing order during breach | State.as breach loop iteration | GameState breach iteration order | MEDIUM |
| Death processing order during swoosh | State.as swoosh `deleteInst()` | Card::beginTurn() kill + removeKilledCards | MEDIUM |
| Death trigger execution | State.as death → script triggers | GameState kill → any triggers | MEDIUM |

### P2 — Medium (edge cases)

#### C1: Construction Time / Delay Interaction

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| constructionTime and delay separation | State.as swoosh (separate decrements) | Card::beginTurn() lines 604-618 | MEDIUM |
| Interaction when both are set | State.as (constructionTime checked first) | Card::beginTurn() (construction checked after delay) | **Verify order** |

#### C2: Health Gained / Healing Cap

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Healing formula | State.as `health += card.healthGained; min(health, healthMax)` | Card::beginTurn() lines 625-629 | LOW |
| Healing timing relative to other effects | State.as swoosh position | Card::beginTurn() position (after lifespan, before scripts) | MEDIUM |

#### C3: Charge System

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Charge gain and cap | State.as `charge += card.chargeGained; min(charge, chargeMax)` | Card::beginTurn() charge logic | LOW |

#### C4: Supply Tracking

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Supply limits enforcement | State.as `turnSupply[]` | C++ supply tracking | LOW |
| Legendary/rare supply values | State.as supply init | CardType supply | LOW |

#### C5: Frontline/Melee Mechanics

| Check | AS3 Location | C++ Location | Risk |
|---|---|---|---|
| Frontline kill during Action | State.as `MOVE_MELEE` | `ASSIGN_FRONTLINE` action | MEDIUM |
| Frontline interaction with wipeout | State.as frontline + glassBroken | C++ frontline + Breach phase | MEDIUM |

---

## Execution Strategy

<!-- CHANGED: Condensed Options A-C to brief mentions — Reviewers 1,2,3,6,7,10 -->
**Approach: Hybrid (Option D)**

Manual P0 audit with targeted code reading, followed by test case documentation and regression tests. Automated approaches (differential testing, AST extraction, property-based testing) were considered but rejected due to: AS3 cannot be run programmatically, cross-language tooling would require significant custom development, and manual audit catches semantic differences that pattern matching cannot.

The manual audit is supplemented by:
1. **Prerequisite deliverables** (Phase 0) that force structural understanding before item-by-item audit
2. **Concrete test cases** per P0 area to prevent "looks equivalent" false confidence
3. **Negative test construction** to probe for "extra legality" bugs (the blocking bug pattern) <!-- CHANGED: Added — Reviewers 5,8,9,10 -->

---

## Recommended Execution Plan

<!-- CHANGED: Restructured phases, removed time estimates — Reviewers 1,2,3,4,6,7,8 -->

### Phase 1: Foundation (Prerequisites)

- [ ] **P0.1**: Create phase transition state machine diagrams for both engines
- [ ] **P0.2**: Comprehensive status reset scan (all `setStatus`/`inst.role =` locations)
- [ ] **P0.3**: Swoosh/beginTurn event timeline (side-by-side operation order)

### Phase 2: P0 Audit (Critical Areas)

Execute in this order (A0 first, as all others depend on it):

- [ ] **A0**: Phase transition sequence — verify linearized C++ phases produce identical transitions to AS3
- [ ] **A1**: Full blocking chain — verify canBlock(), assignedBlocking, swoosh reset (beyond known bug)
- [ ] **A2**: Chill/freeze formula — produce 4-case mathematical proof table
- [ ] **A3**: Wipeout/breach transition + ordering — verify threshold, unit death order, death scripts
- [ ] **A4**: Fragile unit damage handling — verify `damageItCanTake` equivalence
- [ ] **A5**: Game-over conditions — verify missing "all units doomed" and mutual elimination

### Phase 3: P1 Audit (High-Impact Areas)

- [ ] **B1**: Script/trigger execution ordering — compare two-pass (C++) vs single-pass (AS3)
- [ ] **B2**: Begin-turn resource reset order — verify resource types and clearing timing
- [ ] **B3**: Ability use side effects order — verify pay/sac/create/receive sequence
- [ ] **B4**: Snipe mechanics — verify immediate death and defense total update
- [ ] **B5**: Sellable role transition — verify timing and code paths where checked
- [ ] **B6**: Stagnation detection — document gap between 200-turn limit and 4-level system
- [ ] **B7**: Simultaneous death ordering — verify death processing iteration order
- [ ] **B8**: Legal action generation comparison — verify `getLegalActions()` against AS3 for representative states

### Phase 3.5: Supplementary Checks

- [ ] cardLibrary.jso parsing parity check (all 105 units, gameplay-relevant fields)

### Phase 4: Fix & Regression Tests

- [ ] Remove defense-reset bug (GameState.cpp lines 1289-1307) <!-- CHANGED: Explicit step — Reviewers 7,10 -->
- [ ] Verify the fix matches AS3 behavior (ASSIGN sets blocking per card type, no blanket reset)
- [ ] Fix any new divergences found in Phase 2-3
- [ ] Create C++ regression test cases for each verified area
- [ ] Add "all units doomed" game-over check to `calculateGameOver()`
- [ ] Run 100-game tournament with OLD engine and 100 with FIXED engine — compare game lengths and defense totals to quantify bug impact <!-- CHANGED: Specified comparison — Reviewer 1 -->

### Phase 5: P2 Sweep

- [ ] Construction/delay, healing, charge, supply, frontline

---

## How to Use This Plan

**For a new Claude Code context**: Paste this plan along with the CONTEXT document.
The auditor should:

1. Read the AS3 files directly (at `prismata_decompiled/scripts/mcds/engine/`)
2. Read the C++ files side by side (at `source/engine/`)
3. **Start with Phase 1 prerequisite deliverables** before any item-by-item audit
4. For each audit area: trace code paths → document AS3 function + C++ function → produce test cases → record verdict
5. Flag any divergence with severity rating (using the rubric above)
6. Do NOT modify any code — report findings only
7. **Chunk large files by function** — do not attempt to read State.as (4,490 lines) in one pass

**CAN read**: All files in both `prismata_decompiled/` and `source/engine/`
**CANNOT modify**: Any engine code

---

## Already-Known Divergences

| # | Area | AS3 Behavior | C++ Behavior | Impact | Status |
|---|---|---|---|---|---|
| 1 | Blocking after ability use | `inst.blocking = card.assignedBlocking` (per-card) | Blanket status reset to Default/Inert before Defense (lines 1289-1307) | **CRITICAL** — 40-60% extra defense | Fix planned |
| 2 | Phase model | 3 phases + swoosh function | 5 explicit phase enum values | Architectural — verify equivalence | **Audit in A0** |
| 3 | Sellable role | Explicit "sellable" role string in AS3 | `m_sellable` bool, not part of CardStatus enum | Unknown — verify transition timing | **Audit in B5** |
| 4 | Undo system | Full undo for every move type | Only UNDO_BREACH | By design — AI doesn't need undo | Low risk |
| 5 | All-units-doomed instant-win | `helper.allOppUnitsDoomed` → current player wins | Not implemented | **HIGH** — games end later | **Audit in A5** | <!-- CHANGED: New entry — codebase validated -->
| 6 | Stagnation system | 4-level counters [2,8,20,40] | 200-turn limit only | **MEDIUM** — longer games near stalemate | **Audit in B6** | <!-- CHANGED: New entry — codebase validated -->
| 7 | Script execution ordering | Single-pass in swoosh (per-card) | Two-pass in beginTurn (all cards then all scripts) | **MEDIUM** — ordering may differ | **Audit in B1** | <!-- CHANGED: New entry — codebase validated -->

---

<!-- CHANGED: Added negative testing section — Reviewers 5,8,9,10 -->
## Negative Testing Strategy

For each P0 area, construct a game state where the "extra legality" bug pattern would manifest:

| Area | Negative Test | What to Check |
|------|---------------|---------------|
| A0 (Phases) | State where a status reset at the wrong phase boundary changes blocking | Does C++ allow blocking that AS3 forbids? |
| A1 (Blocking) | Drone that used ability, then enters Defense phase | Can it block in C++? (Should not) |
| A2 (Chill) | Fragile unit with damage + chill at exact threshold | Is it frozen in C++ but not AS3, or vice versa? |
| A3 (Breach) | Two units with different death triggers, both breached | Same death order? Same post-breach state? |
| A5 (Game-over) | Board where all opponent units are lifespan-1 | Does C++ end the game? (Should, but currently doesn't) |

---

## Success Criteria

1. Phase transition diagram produced and verified
2. All P0 areas have Match/Mismatch/Uncertain verdict with code references
3. At least 2 concrete test cases per P0 area (1 normal, 1 edge case)
4. Mathematical equivalence documented for formula comparisons (chill, damage)
5. Comprehensive status reset scan completed (all locations documented)
6. All findings reproducible by another developer (function names + code snippets, not just line numbers)
7. Regression test cases proposed for each confirmed divergence
8. Negative tests constructed for each P0 area
9. Self-play impact estimate documented for each confirmed divergence
10. cardLibrary.jso parsing parity check completed for gameplay-relevant fields

---

## Reference: Codebase Sizes

| Codebase | Files | Lines | Purpose |
|---|---|---|---|
| AS3 engine | ~23 files | ~12,500 lines | Ground truth (decompiled client) |
| C++ engine (core) | ~8 files | ~4,000 lines | Reimplementation for AI |
| C++ engine (full) | ~20 files | ~6,000 lines | Including AI integration |

The C++ engine is intentionally smaller — it implements game rules for AI search, not for
a full game client. Some AS3 features (undo, display, raid mode) are correctly omitted.
The audit focuses on features that ARE implemented and whether they match.

---

## Additional Audit Supplements (Applied)

<!-- Items 1,3,5,7 selected by user from Consider-tier list -->

### Replay Failure Categories as Diagnostic Data <!-- From Reviewer 4 -->

The existing replay validation has a 55.7% pass rate. The 849 failing replays are categorized:

| Failure Type | Count | Relevant Audit Area |
|---|---|---|
| USE_ABILITY | 276 | B1 (Script ordering), B3 (Ability side effects) |
| SNIPE | 173 | B4 (Snipe mechanics), A0 (Phase transitions) |
| END_PHASE | 130 | A0 (Phase transitions), A1 (Blocking) |
| BUY | 116 | C4 (Supply), B5 (Sellable) |
| BLOCKER | 58 | A1 (Blocking chain) — may correlate with defense-reset bug |
| OTHER | 96 | Various |

These failures represent C++ being **stricter** than AS3 (rejecting moves the real client allows). This is a complementary signal to the audit's focus on C++ being **more permissive**. During Phase 2-3 audit, cross-reference findings against these failure categories to see if a divergence explains a cluster of failures.

### cardLibrary.jso Parsing Parity Check <!-- From Reviewers 3,5,9,10 -->

Both engines parse `cardLibrary.jso` independently. Add to Phase 2 (after A0):

- [ ] Write a quick script or manual check: for all 105 units, compare C++ `CardTypeInfo` parsed values against raw JSON for gameplay-relevant fields: `defaultBlocking`, `assignedBlocking`, `fragile`, `lifespan`, `healthMax`, `healthGained`, `beginOwnTurnScript`, `abilityScript`, `abilityCost`
- Focus on: missing fields defaulting differently, type coercion (int vs float), boolean parsing

### Self-Play Impact Estimator Per Finding <!-- From Reviewer 6 -->

For each divergence found during the audit, document:

| Field | Description |
|---|---|
| **Affected unit types** | Which of the 105 units trigger this code path? |
| **Frequency estimate** | What % of self-play games contain these units? |
| **Symmetry** | Is the bug symmetric (both sides equally affected) or asymmetric? |
| **Data regen needed?** | Yes (retrain required) / Partial (fine-tune) / No (negligible impact) |

Symmetric bugs (like the defense-reset) corrupt training data less severely because both sides have the same advantage. Asymmetric bugs are more damaging.

### Legal Action Generation Comparison <!-- From Reviewer 4 -->

Add to Phase 3 (P1 audit):

- [ ] **B8: Legal Action Generation** — For a set of 5-10 representative game states (exported via F6), compare the legal move list generated by C++ `GameState::getLegalActions()` against what AS3 would allow. This catches cases where state rules match but the move generator has a bug (e.g., failing to generate a legal ability use, or generating an illegal buy).

Method: Export F6 states from the real client at interesting decision points, feed to `--suggest` mode, manually verify the action list includes all expected options and excludes illegal ones.
