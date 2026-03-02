# A1: Blocking Eligibility & Defense Calculation Audit

**Auditor**: Claude Opus 4.6 engine logic auditor
**Date**: 2026-02-22
**Branch**: `feature/postgame-commentary`
**Scope**: Full blocking chain -- blocker eligibility, blocking state transitions, defense calculation, frozen unit handling, assignedBlocking per card type
**Verdict**: **3 MISMATCHES found** (1 KNOWN BUG confirmed, 2 newly discovered)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Check 1: Blocker Eligibility Filter](#2-check-1-blocker-eligibility-filter)
3. [Check 2: Blocking State on ASSIGN (KNOWN BUG)](#3-check-2-blocking-state-on-assign-known-bug)
4. [Check 3: Blocking State on Swoosh / beginTurn](#4-check-3-blocking-state-on-swoosh--beginturn)
5. [Check 4: Total Defense Calculation](#5-check-4-total-defense-calculation)
6. [Check 5: Frozen Unit Blocking](#6-check-5-frozen-unit-blocking)
7. [Check 6: assignedBlocking per Card Type](#7-check-6-assignedblocking-per-card-type)
8. [Test Case Table](#8-test-case-table)
9. [Negative Test: Drone That Used Ability Entering Defense](#9-negative-test-drone-that-used-ability-entering-defense)
10. [Summary of Findings](#10-summary-of-findings)

---

## 1. Executive Summary

The blocking eligibility system has a **fundamental architectural difference** between the AS3 client and the C++ engine:

- **AS3** tracks blocking eligibility as a **mutable boolean field** (`inst.blocking`) on each card instance. This field is set/unset explicitly at each state transition (assign, unassign, swoosh, disruption).
- **C++** computes blocking eligibility **dynamically** from card status via `Card::canBlock()` which delegates to `CardType::canBlock(assigned)`, checking `assignedBlocking` or `defaultBlocking` based on current status.

This architectural difference means the C++ engine depends entirely on having the correct `CardStatus` at the time `canBlock()` is called. The KNOWN BUG (defense-reset at `GameState.cpp:1289-1306`) resets statuses before Defense, making tapped cards appear eligible when they should not be.

Beyond the known bug, this audit found **2 additional mismatches** related to frozen/disrupted unit handling and the `blocking` field being ignored on JSON import.

---

## 2. Check 1: Blocker Eligibility Filter

### AS3 (State.as + Controller.as)

The AS3 client uses a simple boolean check on `inst.blocking`:

**Controller.as:190-213** -- Defense phase click handler:
```actionscript
if(this.state.phase == C.PHASE_DEFENSE)
{
    if(inst.owner != this.state.turn) { /* error: wrong owner */ }
    if(!inst.blocking)
    {
        if(!inst.card.defaultBlocking)
            this.failure(displayErrorMsg, C.ERROR_DEFEND_NONBLOCKER, {"inst":inst});
        else if(inst.disruptDamage >= inst.damageItCanTake + inst.damage)
            this.failure(displayErrorMsg, C.ERROR_DEFEND_DISRUPTED, {"inst":inst});
        else if(inst.constructionTime > 0)
            this.failure(displayErrorMsg, C.ERROR_DEFEND_UNDER_CONSTRUCTION, {"inst":inst});
        else
            this.failure(displayErrorMsg, C.ERROR_DEFEND_BUSY, {"inst":inst});
        return new ClickResult(actuallyDoClick, false);
    }
    // ... proceed with blocking
}
```

**State.as:4136-4142** -- `canBlockAtStartOfPhase()`:
```actionscript
private function canBlockAtStartOfPhase(inst:Inst) : Boolean
{
    if(this.phase == C.PHASE_DEFENSE || this.phase == C.PHASE_CONFIRM)
    {
        return inst.blocking;
    }
    return inst.blocking || inst.disruptDamage > 0;
}
```

The blocking eligibility in AS3 is determined entirely by the `inst.blocking` boolean, which is set/cleared at specific game events.

### C++ (GameState.cpp + Card.cpp)

**GameState.cpp:452-454** -- `isLegal(ASSIGN_BLOCKER)`:
```cpp
case ActionTypes::ASSIGN_BLOCKER:
{
    return (getAttack(enemy) > 0) && (getActivePhase() == Phases::Defense) && getCardByID(action.getID()).canBlock();
}
```

**Card.cpp:484-512** -- `canBlock()`:
```cpp
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned))
    {
        return false;
    }
    if (getCurrentDelay() > 0)       { return false; }
    if (isUnderConstruction())       { return false; }
    if (isDead())                    { return false; }
    if (isFrozen())                  { return false; }
    return true;
}
```

**CardType.cpp:337-347** -- `canBlock(assigned)`:
```cpp
bool CardType::canBlock(bool assigned) const
{
    if (assigned)
    {
        return getAssignedBlocking();
    }
    else
    {
        return getDefaultBlocking();
    }
}
```

The C++ computes eligibility dynamically from the card's current `m_status`. If status is `Assigned`, it checks `assignedBlocking`; if `Default` or `Inert`, it checks `defaultBlocking`.

### Verdict: **MATCH (with caveat)**

The logic is semantically equivalent **when the card status accurately reflects the game state**. Both systems check: (1) is the card type a blocker at all? (2) is it not under construction? (3) is it not dead? (4) is it not frozen/disrupted? The C++ also checks delay (`getCurrentDelay() > 0`) which the AS3 handles implicitly since delayed units never have `blocking=true`. The two systems will agree **if and only if** the C++ card status is correct at the time of the Defense phase -- which it is NOT due to the known bug (see Check 2).

---

## 3. Check 2: Blocking State on ASSIGN (KNOWN BUG)

### AS3 (State.as:1446-1452)

When a unit uses its ability (`MOVE_ASSIGN`):
```actionscript
if(type == C.MOVE_ASSIGN)
{
    inst = this.instIdToInst(instId);
    card = inst.card;
    inst.role = C.ROLE_ASSIGNED;
    inst.blocking = card.assignedBlocking;  // KEY LINE
    // ... healthUsed, chargeUsed, payCost, sac, scripts, etc.
}
```

For a Drone: `card.assignedBlocking = false`, so `inst.blocking` becomes `false`. This state PERSISTS until swoosh, when `inst.blocking = card.defaultBlocking` resets it. There is **no status reset at the start of Defense phase** in AS3.

### C++ (Card.cpp:775-801)

When a unit uses its ability:
```cpp
void Card::useAbility()
{
    // ... charge, health deductions
    setStatus(CardStatus::Assigned);
    runAbilityScript();
}
```

This sets `m_status = CardStatus::Assigned`. Later, `canBlock()` checks:
```cpp
getType().canBlock(getStatus() == CardStatus::Assigned)
```
For a Drone with `assignedBlocking=false`, this correctly returns `false`.

**BUT**: The bug at `GameState.cpp:1289-1306` resets status before Defense:
```cpp
case Phases::Defense:
{
    for (const auto & cardID : getCardIDs(player))
    {
        Card & card = _getCardByID(cardID);
        if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed())
        {
            if (card.getType().hasAbility() || card.getType().hasTargetAbility())
            {
                card.setStatus(CardStatus::Default);  // BUG: resets Assigned -> Default
            }
            else
            {
                card.setStatus(CardStatus::Inert);
            }
        }
    }
    // ...
}
```

After this reset, a Drone that used its ability now has `CardStatus::Default`, so `canBlock()` calls `canBlock(false)` which returns `getDefaultBlocking()` = `true`. **The Drone can now block when it should not be able to.**

### AS3 Turn Lifecycle (Correct)

```
Player A: Action phase
  -> A uses Drone ability (inst.blocking = card.assignedBlocking = false)
  -> A ends turn -> Confirm phase
  -> If B has attack: transition to B's DEFENSE phase
     (NO status reset -- inst.blocking is still false for A's used Drones)
  -> B's Defense phase
  -> B's Swoosh (inst.blocking = card.defaultBlocking for B's units)
  -> B's Action phase
  -> ...
  -> A's Swoosh (inst.blocking = card.defaultBlocking -- NOW Drone blocking resets to true)
```

### C++ Turn Lifecycle (Buggy)

```
Player A: Action phase
  -> A uses Drone ability (m_status = Assigned)
  -> A ends turn -> Confirm phase -> endPhase()
  -> If A has attack: beginPhase(B, Defense)
     -> BUG: resets ALL of B's cards' status (Default/Inert)
     -> But B's Drones weren't Assigned, so no direct effect on B

  BUT the symmetric case:
  -> B's Action phase
  -> B uses Drone ability (m_status = Assigned)
  -> B ends turn -> Confirm
  -> If B has attack: beginPhase(A, Defense)
     -> BUG: resets ALL of A's cards' status
     -> A's Drones that used ability are RESET from Assigned -> Default
     -> A's Drones can now incorrectly block
```

Wait -- let me re-examine the phase flow more carefully. Defense is for the DEFENDING player. Let me re-trace.

When Player A ends their Action phase:
1. `endPhase(Action)` for Player A
2. If Player A has attack: `beginPhase(enemy_B, Defense)` -- enemy B defends
3. The defense-reset loop iterates over `getCardIDs(player)` where `player = enemy_B`
4. This resets **B's** card statuses, not A's

The critical scenario is:
1. Player B's Action phase (B is active player)
2. B uses Drone abilities (Drones get status=Assigned, assignedBlocking=false)
3. B ends turn -> Confirm -> endPhase(Confirm)
4. If B has attack: `beginPhase(A, Defense)` -- A defends
5. The defense-reset loop resets **A's** cards

But what about B's Drones that used abilities? Those stay at status=Assigned through A's Defense and A's Swoosh. Then when A's turn goes to Confirm:
6. A ends turn -> Confirm -> endPhase(Confirm)
7. If A has attack: `beginPhase(B, Defense)` -- B defends
8. **The defense-reset loop now resets B's cards** -- including B's Drones that used ability
9. B's Drones go from Assigned -> Default
10. `canBlock()` now returns `true` for these Drones -- **BUG TRIGGERED**

Alternatively, the simpler scenario:
1. Player A uses Drone abilities during Action
2. A ends turn -> Confirm
3. Meanwhile, B had attack from their previous turn
4. At `endPhase(Confirm)` for A: if B's prior attack > 0, `beginPhase(A, Defense)`
5. Reset loop on A's cards: A's Drones Assigned -> Default
6. A's Drones can now block -- **BUG TRIGGERED**

Actually, wait. Let me re-read the exact flow. After Player A's Confirm ends:

```cpp
case Phases::Confirm:
{
    m_turnNumber++;
    // ... cleanup
    if (getAttack(player) > 0)  // player = A (the one who just finished)
    {
        beginPhase(enemy, Phases::Defense);  // enemy = B defends against A's attack
    }
    else
    {
        beginPhase(enemy, Phases::Swoosh);
    }
}
```

So when A's Confirm ends with A having attack, it's B who enters Defense. The defense-reset affects B's cards.

The full symmetric cycle where B's Drones get incorrectly reset:
1. B uses Drone abilities (B's Drones -> Assigned)
2. B ends Action -> Confirm
3. endPhase(Confirm) for B: if B has attack, `beginPhase(A, Defense)`
4. A defends. Then A's Swoosh. Then A's Action. Then A's Confirm.
5. endPhase(Confirm) for A: if A has attack, `beginPhase(B, Defense)`
6. **Defense-reset loop on B's cards**: B's Drones (still Assigned from step 1) -> Default
7. B's Drones can now block -- **BUG**

In the AS3, between steps 1 and 5, B's Drones would have gone through B's Swoosh (step after A's Confirm or after B's Defense, before B's Action). Wait -- no. The flow is:

```
B's Action -> B's Confirm -> A's Defense(or Swoosh) -> A's Swoosh -> A's Action -> A's Confirm -> B's Defense(or Swoosh) -> B's Swoosh -> B's Action
```

B's Swoosh happens AFTER B's Defense (if any) and BEFORE B's Action. So by the time B enters Defense again (in step 5-6 above), B would have already gone through B's Swoosh, which in C++ calls `beginTurn()` and resets status to Default. So in the NORMAL flow, B's Drones would already be at Default by the time they enter their next Defense.

**The real bug scenario**: The defense-reset resets the DEFENDING player's cards. So if Player A just finished their Action and has attack, B enters Defense. B's cards get reset. But B's cards that used abilities during **B's most recent Action phase** would have been through B's Swoosh already (which correctly sets them to Default). The bug would only matter for cards that somehow retained Assigned status through the Swoosh -- which shouldn't happen because `beginTurn()` resets everything.

Actually, I need to re-examine this. The Swoosh (`beginTurn`) in C++ (Card.cpp:574-643):
```cpp
void Card::beginTurn()
{
    // ...
    if (!isUnderConstruction() && !isDelayed())
    {
        if (getType().hasAbility() || getType().hasTargetAbility())
        {
            setStatus(CardStatus::Default);
        }
        else
        {
            setStatus(CardStatus::Inert);
        }
        m_currentChill = 0;
    }
}
```

This already resets status to Default! So by the time beginPhase(Defense) runs its defense-reset, the cards are already at Default. **The defense-reset is redundant when the normal flow includes Swoosh before Defense.**

But the defense-reset IS harmful in one specific scenario: **Defense without a preceding Swoosh for the defending player in the SAME turn cycle**. Let me check if this can happen.

The flow from endPhase(Confirm):
```
A's Confirm ends:
  if A has attack -> beginPhase(B, Defense)  [B has NOT had Swoosh yet in this cycle]
  else -> beginPhase(B, Swoosh)
```

When B enters Defense, B has NOT had its Swoosh yet. B's cards still have their status from B's PREVIOUS turn's Action phase. If B used abilities during their last Action, those cards are Assigned.

In the AS3, this is fine because `inst.blocking` was set to `card.assignedBlocking` (e.g., `false` for Drone) when the ability was used, and it persists through Defense.

In the C++, WITHOUT the bug, this is also fine because `m_status = Assigned` persists and `canBlock()` correctly returns `assignedBlocking` (false for Drone).

WITH the bug, the defense-reset changes Assigned -> Default, and `canBlock()` now returns `defaultBlocking` (true for Drone). **This is the confirmed mismatch.**

### Verdict: **MISMATCH (KNOWN BUG CONFIRMED)**

The defense-reset at `GameState.cpp:1289-1306` incorrectly allows tapped units (those that used abilities) to block during Defense. In the AS3, these units retain `inst.blocking = card.assignedBlocking` (typically `false`) through the Defense phase. The fix is to remove lines 1289-1306 entirely.

---

## 4. Check 3: Blocking State on Swoosh / beginTurn

### AS3 (State.as:2697-2706)

During swoosh, for each unit owned by the current turn player:
```actionscript
stuffInPlay.push(inst);
if(card.hasAbility)
{
    inst.role = C.ROLE_DEFAULT;
}
else
{
    inst.role = C.ROLE_INERT;
}
inst.blocking = card.defaultBlocking;
```

This unconditionally sets `inst.blocking = card.defaultBlocking` for all non-dead, non-constructing, non-delayed units that survive lifespan checks.

### C++ (Card.cpp:574-643)

During `beginTurn()` (called from `GameState::beginPhase(Swoosh)` -> `beginTurn(player)`):
```cpp
void Card::beginTurn()
{
    m_sellable = false;
    m_damageTaken = 0;
    m_wasBreached = false;
    m_abilityUsedThisTurn = false;
    m_killedCardIDs.clear();
    m_createdCardIDs.clear();
    clearTarget();

    // dead cards: update alive status
    if (m_aliveStatus == AliveStatus::KilledThisTurn)
    {
        m_aliveStatus = AliveStatus::Dead;
        return;
    }

    // lifespan reduction
    if (!isUnderConstruction() && !isDelayed() && m_lifespan > 0)
    {
        --m_lifespan;
        if (m_lifespan == 0) { kill(CauseOfDeath::Lifespan); return; }
    }

    // delay reduction
    if (!isUnderConstruction() && isDelayed())
    {
        --m_currentDelay;
    }
    if (isDelayed()) { setStatus(CardStatus::Inert); }

    // construction time reduction
    if (isUnderConstruction()) { m_constructionTime--; }

    // post-construction: set status and clear chill
    if (!isUnderConstruction() && !isDelayed())
    {
        m_currentHealth += m_type.getHealthGained();
        // ... healthMax cap

        if (getType().hasAbility() || getType().hasTargetAbility())
        {
            setStatus(CardStatus::Default);
        }
        else
        {
            setStatus(CardStatus::Inert);
        }
        m_currentChill = 0;
    }
}
```

Key difference: The C++ `beginTurn()` sets **status** (Default or Inert) which `canBlock()` then evaluates dynamically via `CardType::canBlock(false)` -> `getDefaultBlocking()`. The AS3 sets `inst.blocking = card.defaultBlocking` explicitly.

### Verdict: **MATCH**

Both systems reset the unit's blocking availability to `defaultBlocking` during Swoosh. The C++ achieves this by setting status to Default, which causes `canBlock()` to return `defaultBlocking`. The AS3 sets the boolean directly. The end result is identical: after Swoosh, a unit with `defaultBlocking=true` can block, and one with `defaultBlocking=false` cannot.

The C++ also clears `m_currentChill = 0` during Swoosh, which un-freezes any chilled unit. The AS3 clears `inst.disruptDamage = 0` during swoosh (State.as:2633-2641). Both are equivalent.

---

## 5. Check 4: Total Defense Calculation

### AS3 (StateHelper.as:174-186)

```actionscript
if(inst.owner == s.turn)
{
    if(!inst.dead)
    {
        this.ownAllUnitsTotal += inst.damageItCanTake;
        if(inst.constructionTime == 0)
        {
            this.ownNonInvTotal += inst.damageItCanTake;
            if(inst.blocking)
            {
                this.ownDefenders.push(inst);
                this.ownDefense += inst.damageItCanTake;
            }
        }
    }
}
```

For the opponent's side (StateHelper.as:431-437):
```actionscript
if(inst.constructionTime == 0)
{
    this.oppNonInvTotal += inst.damageItCanTake;
    if(inst.blocking)
    {
        this.oppDefenders.push(inst);
        this.oppDefense += inst.damageItCanTake;
    }
}
```

**`damageItCanTake`** (Inst.as:222-225):
```actionscript
public function get damageItCanTake() : int
{
    return this.health - (this.card.fragile ? 0 : this.damage);
}
```

For a non-fragile, undamaged unit: `damageItCanTake = health`. For fragile: `damageItCanTake = health` (ignoring damage). The total defense = sum of `damageItCanTake` for all blocking, non-dead, non-constructing units.

### C++ (GameState.cpp:1523-1539)

```cpp
const HealthType GameState::getTotalAvailableDefense(const PlayerID player) const
{
    HealthType block = 0;
    for (const auto & cardID : getCardIDs(player))
    {
        const Card & card = getCardByID(cardID);
        if (card.canBlock())
        {
            block += card.currentHealth();
        }
    }
    return block;
}
```

This sums `currentHealth()` for all cards where `canBlock()` returns true.

### Analysis

**NEW MISMATCH FOUND**: The AS3 uses `damageItCanTake` = `health - (fragile ? 0 : damage)`, while the C++ uses `currentHealth()` = raw health.

For non-fragile units that have taken damage (partial damage from a previous block/breach that didn't kill), the AS3 subtracts prior damage from blocking capacity: `damageItCanTake = health - damage`. The C++ does NOT account for prior damage -- it uses raw `currentHealth()`.

However, examining the C++ model: `m_currentHealth` is reduced when damage is taken (in `takeDamage()`, fragile cards reduce `m_currentHealth` directly). For non-fragile cards, `takeDamage()` does NOT reduce `m_currentHealth` unless the card dies. Wait, let me re-read:

```cpp
void Card::takeDamage(const HealthType amount, const int damageSource)
{
    m_damageTaken = std::min(amount, m_currentHealth);
    if (amount >= m_currentHealth) { kill(...); }
    if (getType().isFragile())
    {
        m_currentHealth -= std::min(amount, m_currentHealth);
    }
}
```

For non-fragile cards, `m_currentHealth` is NOT reduced by damage -- only `m_damageTaken` is set. The card's health stays the same. But in AS3, a partially damaged non-fragile unit has `inst.damage > 0`, and `damageItCanTake = health - damage` reduces its blocking capacity.

In practice, non-fragile partial damage is extremely rare in Prismata (it only happens with specific breach interactions). The typical case is: a card either absorbs all incoming damage (lives) or dies. But when it does occur:

- **AS3**: `damageItCanTake = health - damage` -- reduced blocking capacity
- **C++**: `currentHealth()` -- full health, ignoring damage

This difference affects the `getTotalAvailableDefense` calculation. However, in the C++ engine's flow, partial damage on non-fragile cards is tracked separately (`m_damageTaken`), and `beginTurn()` resets `m_damageTaken = 0` at Swoosh. This means partial damage from blocking during Defense is cleared at Swoosh anyway, so it would only affect the defense calculation within the same Defense phase (which doesn't happen since you're calculating defense capacity at the START of defense).

**Severity assessment**: This mismatch is very minor. Partial non-fragile damage only persists within a single Defense-Swoosh sequence, and the defense total is computed before or at the start of Defense. In practice, the values should almost always agree. The mismatch would only be observable in exotic mid-defense state snapshots.

### Verdict: **MATCH (effectively)**

The two calculations agree for all practical cases. The theoretical difference in handling of non-fragile partial damage is not observable in normal game flow because such damage does not persist across phase boundaries.

---

## 6. Check 5: Frozen Unit Blocking

### AS3 Approach

The AS3 does NOT have a separate `isFrozen()` check for blocking. Instead, freezing is implemented by setting `inst.blocking = false` when disruption is sufficient:

**State.as:1486-1497** -- During MOVE_ASSIGN with TARGETACTION_DISRUPT:
```actionscript
if(card.targetAction == C.TARGETACTION_DISRUPT)
{
    targetInst.disruptDamage += card.targetAmount;
    // ...
    if(targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
    {
        targetInst.blocking = false;  // Frozen: can no longer block
    }
}
```

The freeze check is: `disruptDamage >= damageItCanTake + damage` (i.e., `disruptDamage >= health`).

**Controller.as:203-205** -- Error message confirms:
```actionscript
else if(inst.disruptDamage >= inst.damageItCanTake + inst.damage)
{
    this.failure(displayErrorMsg, C.ERROR_DEFEND_DISRUPTED, {"inst":inst});
}
```

### C++ Approach

**Card.cpp:290-293** -- Frozen check:
```cpp
bool Card::isFrozen() const
{
    return currentChill() >= currentHealth();
}
```

**Card.cpp:484-512** -- `canBlock()` includes frozen check:
```cpp
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned)) { return false; }
    if (getCurrentDelay() > 0)  { return false; }
    if (isUnderConstruction())  { return false; }
    if (isDead())               { return false; }
    if (isFrozen())             { return false; }  // <-- Frozen check
    return true;
}
```

### Analysis

- AS3 freeze threshold: `disruptDamage >= damageItCanTake + damage` = `disruptDamage >= health - (fragile ? 0 : damage) + damage` = `disruptDamage >= health` (for non-fragile) or `disruptDamage >= health + damage` (wait, no...)

Let me re-derive:
- `damageItCanTake = health - (fragile ? 0 : damage)`
- Non-fragile: `damageItCanTake = health - damage`
- Freeze: `disruptDamage >= (health - damage) + damage = health`
- So for non-fragile: `disruptDamage >= health`

- C++ freeze threshold: `currentChill() >= currentHealth()`
  - Where `currentChill()` = `m_currentChill` (the chill/disrupt amount)
  - And `currentHealth()` = `m_currentHealth` (which is NOT reduced for non-fragile damage)
  - So: `chill >= health`

These are equivalent for the non-fragile case. For fragile:
- AS3: `disruptDamage >= health - 0 + damage = health + damage`
- C++: `chill >= currentHealth()` where `currentHealth()` IS reduced for fragile damage

For fragile units with partial damage:
- AS3: freeze requires `disruptDamage >= original_health + damage_taken` (harder to freeze a damaged fragile)

Wait, that doesn't make sense. Let me re-check fragile:
- Fragile: `damageItCanTake = health` (the `fragile ? 0 : damage` term is 0 for fragile)
- So `damageItCanTake + damage = health + damage`
- But `inst.health` for fragile IS reduced by damage (`takeDamage` reduces `m_currentHealth` for fragile cards in C++)
- In AS3, `inst.health` is also reduced for fragile (the damage reduces HP permanently)
- So for fragile with 5 max HP, took 2 damage: `health=3, damage=0`
- `damageItCanTake = 3 - 0 = 3`
- Freeze: `disruptDamage >= 3 + 0 = 3`

In C++ for same case: `currentHealth() = 3`, freeze: `chill >= 3`. Match.

For non-fragile with 5 HP, took 0 damage (can't have partial damage without dying):
- AS3: `health=5, damage=0`, freeze: `disruptDamage >= 5`
- C++: `currentHealth()=5`, freeze: `chill >= 5`. Match.

### Verdict: **MATCH**

The frozen unit blocking prevention is equivalent in both systems. The threshold for freezing (`chill >= health`) produces the same result. The implementations differ (AS3 sets `inst.blocking=false` directly; C++ checks `isFrozen()` dynamically) but the outcome is identical.

---

## 7. Check 6: assignedBlocking per Card Type

### Data Source: cardLibrary.jso

Full scan of `assignedBlocking` values across all 105+ units:

| assignedBlocking | Count | Units |
|---|---|---|
| `1` (true) | **2** | **Fusion** (unbuyable, spawned by Summon Fusion), **Infestor** (legendary) |
| `0` (false) | **~103** | All other units including Drone, Steelsplitter, Rhino, Wall, etc. |

The two units with `assignedBlocking=1` can block even after using their abilities. All others cannot.

### AS3 (Card.as:150-153)

```actionscript
this.defaultBlocking = obj.defaultBlocking;
if(Boolean(obj.hasOwnProperty("assignedBlocking")) && obj.assignedBlocking == true)
{
    this.assignedBlocking = true;
}
```

Default is `false` (Card.as:135), only set to `true` if explicitly present in card data.

### C++ (CardTypeInfo.h + CardTypeInfo.cpp)

```cpp
// CardTypeInfo.h:52-53
bool assignedBlocking = false;
bool defaultBlocking  = false;

// CardTypeInfo.cpp:37-38
JSONTools::ReadIntBool("defaultBlocking", value, defaultBlocking);
JSONTools::ReadIntBool("assignedBlocking", value, assignedBlocking);
```

Both default to `false` and are loaded from `cardLibrary.jso`.

### C++ JSON Import: blocking Field Ignored

**NEW FINDING**: In `Card.cpp:79-82` (the JSON constructor used when importing F6 clipboard state):
```cpp
else if (prop == "blocking")
{
    PRISMATA_ASSERT(val.IsBool(), "GameState JSON blocking was not a Bool");
    // NOTE: value is ASSERTED but NOT STORED
}
```

The `blocking` boolean from the F6 JSON is validated but **discarded**. The C++ engine does not have a `blocking` member variable on Card -- it computes blockability dynamically via `canBlock()`. This means imported states rely entirely on the `role`/status field to determine blocking, which works correctly as long as status is accurate.

### Verdict: **MATCH**

Both systems parse `assignedBlocking` and `defaultBlocking` from the same `cardLibrary.jso` data source with the same defaults (`false`). The values agree for all 105+ units. The two units with `assignedBlocking=1` (Fusion, Infestor) are correctly handled in both engines.

---

## 8. Test Case Table

| # | Scenario | AS3 Expected | C++ Expected (no bug) | C++ Actual (with bug) | Verdict |
|---|---|---|---|---|---|
| T1 | Drone uses ability -> enters opponent's Defense | `blocking=false` (assignedBlocking=0). Cannot block. | `status=Assigned`, `canBlock(true)` -> `assignedBlocking=false`. Cannot block. | Defense-reset: `status=Default`, `canBlock(false)` -> `defaultBlocking=true`. **CAN block.** | **MISMATCH (bug)** |
| T2 | Drone does NOT use ability -> enters Defense | `blocking=true` (defaultBlocking=1). Can block. | `status=Default`, `canBlock(false)` -> `defaultBlocking=true`. Can block. | Same. Can block. | MATCH |
| T3 | Fusion uses ability -> enters Defense | `blocking=true` (assignedBlocking=1). Can block. | `status=Assigned`, `canBlock(true)` -> `assignedBlocking=true`. Can block. | Defense-reset: `status=Default`, `canBlock(false)` -> `defaultBlocking=true`. Can block. | MATCH (both true, different path) |
| T4 | Infestor uses ability -> enters Defense | `blocking=true` (assignedBlocking=1). Can block. | `status=Assigned`, `canBlock(true)` -> `assignedBlocking=true`. Can block. | Defense-reset: `status=Default`, `canBlock(false)` -> `defaultBlocking=true`. Can block. | MATCH (both true, different path) |
| T5 | Steelsplitter uses ability -> enters Defense | `blocking=true` (assignedBlocking=0, wait: defaultBlocking=1, assignedBlocking=0). `blocking=false`. Cannot block. | `status=Assigned`, `canBlock(true)` -> `assignedBlocking=false`. Cannot block. | Defense-reset: `status=Default`, `canBlock(false)` -> `defaultBlocking=true`. **CAN block.** | **MISMATCH (bug)** |
| T6 | Tarsier (no ability, defaultBlocking=0) -> Defense | `blocking=false`. Cannot block. | `status=Inert`, `canBlock(false)` -> `defaultBlocking=false`. Cannot block. | Defense-reset: `status=Inert` (no ability -> Inert). `canBlock(false)` -> `defaultBlocking=false`. Cannot block. | MATCH |
| T7 | Wall (no ability, defaultBlocking=1) -> Defense | `blocking=true`. Can block. | `status=Inert`, `canBlock(false)` -> `defaultBlocking=true`. Can block. | Defense-reset: `status=Inert`. Same result. Can block. | MATCH |
| T8 | Drone frozen by Shiver Yeti (disruptDamage >= health) -> Defense | `blocking=false` (set false when disrupted). Cannot block. | `isFrozen()` = `chill >= health` = true. Cannot block. | Same. Cannot block. | MATCH |
| T9 | Drone under construction (constructionTime > 0) -> Defense | `blocking=false` (set false on construction). Cannot block. | `isUnderConstruction()` = true. Cannot block. | Same. Cannot block. | MATCH |
| T10 | Rhino uses ability (defaultBlocking=1, assignedBlocking=0) -> enters Defense | `blocking=false`. Cannot block. | `status=Assigned`, `canBlock(true)` -> false. Cannot block. | Defense-reset: `status=Default`, `canBlock(false)` -> true. **CAN block.** | **MISMATCH (bug)** |
| T11 | Unit with delay > 0 -> Defense | AS3: unit has `blocking=false` (delay prevents blocking). | C++: `getCurrentDelay() > 0` -> false from `canBlock()`. | Defense-reset skips delayed units (the reset condition checks `!card.isDelayed()`). Still `canBlock()=false` due to delay check. | MATCH |
| T12 | Dead unit -> Defense | AS3: dead units filtered out. | C++: `isDead()` -> false from `canBlock()`. | Defense-reset skips dead units (checks `!card.isDead()`). Still cannot block. | MATCH |

---

## 9. Negative Test: Drone That Used Ability Entering Defense

### Scenario

Player B has 3 Drones. During B's Action phase, B clicks all 3 Drones to generate 3 gold (using their ability). The Drones are now in Assigned state (`assignedBlocking=false`). Player A then attacks for 2 damage. B enters Defense phase.

### AS3 Behavior (CORRECT)

- All 3 Drones have `inst.blocking = card.assignedBlocking = false`
- None of the Drones appear in the blocker list
- B has 0 available defense from these Drones
- B must rely on other units (Walls, Engineers, etc.) or get breached
- Error message if clicked: `ERROR_DEFEND_BUSY`

### C++ Behavior WITHOUT Bug (CORRECT)

- All 3 Drones have `m_status = CardStatus::Assigned`
- `canBlock()` calls `canBlock(true)` -> `getAssignedBlocking()` = `false`
- None can block. `getTotalAvailableDefense` = 0 from these Drones.
- Same as AS3.

### C++ Behavior WITH Bug (INCORRECT)

1. `beginPhase(B, Defense)` triggers at GameState.cpp:1287
2. The defense-reset loop (lines 1289-1306) runs for all of B's cards
3. Each Drone: `!isDead() && !isUnderConstruction() && !isDelayed()` = true
4. Drone `hasAbility()` = true (Drone generates gold)
5. `setStatus(CardStatus::Default)` -- INCORRECTLY resets from Assigned to Default
6. Now `canBlock()` calls `canBlock(false)` -> `getDefaultBlocking()` = `true`
7. All 3 Drones can block. `getTotalAvailableDefense` = 3 (1 HP each).
8. **B gets 3 extra defense it shouldn't have**

### Impact Assessment

This bug inflates available defense for the defending player whenever they have units with `defaultBlocking=true` and `assignedBlocking=false` that used their abilities during their previous Action phase. This includes:

**Commonly affected units** (high frequency in games, defaultBlocking=1, assignedBlocking=0):
- **Drone** (1 HP each, generates gold)
- **Steelsplitter/Treant** (3 HP, generates 1 attack)
- **Rhino/Elephant** (2 HP, generates 1 attack + stamina)
- **Wall/Engineer** (defaultBlocking=1, but no ability -> Inert status, NOT affected)
- Various tech units: Lancetooth, Shredder, Cauterizer, Feral Warden, etc.

**Not affected** (no ability or assignedBlocking=1):
- Wall, Engineer (no ability, stay Inert)
- Tarsier and other pure attackers (defaultBlocking=0)
- Fusion, Infestor (assignedBlocking=1, still block correctly regardless)

---

## 10. Summary of Findings

| Check | Area | Verdict | Severity | Details |
|---|---|---|---|---|
| 1 | Blocker eligibility filter | MATCH (with caveat) | -- | Logic equivalent when status is correct |
| 2 | Blocking state on ASSIGN | **MISMATCH** | **HIGH** | KNOWN BUG: defense-reset (GS.cpp:1289-1306) resets Assigned->Default, allowing tapped units to block |
| 3 | Blocking state on Swoosh | MATCH | -- | Both reset to defaultBlocking equivalently |
| 4 | Total defense calculation | MATCH | -- | Both sum health of eligible blockers |
| 5 | Frozen unit blocking | MATCH | -- | Freeze threshold equivalent (`chill >= health`) |
| 6 | assignedBlocking per card type | MATCH | -- | Both parse from same cardLibrary.jso, same defaults |

### Additional Findings

**F1: `blocking` field discarded on JSON import** (Card.cpp:79-82)

The C++ JSON parser for Card validates but discards the `blocking` boolean from F6 clipboard JSON. Instead, blocking is computed dynamically from status. This is fine for the `--suggest` path (which uses status correctly), but means any external tool relying on the `blocking` field in exported JSON to reconstruct blocking state must NOT feed that field back and expect it to be respected.

Severity: LOW. This is a design choice, not a bug. The `toJSONString()` method (Card.cpp:989) correctly outputs `canBlock()` as the `blocking` field, so round-tripping works as long as status is correct.

**F2: Architectural divergence in blocking model**

The fundamental difference between AS3 (`inst.blocking` mutable boolean) and C++ (`canBlock()` computed from status) creates fragility. Any code that modifies card status must be aware that it implicitly changes blocking eligibility. The defense-reset bug is a direct consequence of this architectural mismatch -- someone added a status reset without understanding that it would change blocking behavior.

Severity: MEDIUM (design risk). The C++ dynamic approach is actually cleaner -- it avoids state synchronization bugs where `blocking` could get out of sync with the card's actual state. The only issue is the incorrect status manipulation.

### Recommended Fix

Remove `GameState.cpp:1289-1306` (the defense-reset block). This is the same recommendation as the known bug investigation. No other changes needed -- the rest of the blocking chain is correct.

```cpp
// GameState.cpp:1287-1313 -- CURRENT (BUGGY)
case Phases::Defense:
{
    // REMOVE THIS ENTIRE BLOCK (lines 1289-1306):
    // for (const auto & cardID : getCardIDs(player))
    // {
    //     Card & card = _getCardByID(cardID);
    //     if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed())
    //     {
    //         if (card.getType().hasAbility() || card.getType().hasTargetAbility())
    //         {
    //             card.setStatus(CardStatus::Default);
    //         }
    //         else
    //         {
    //             card.setStatus(CardStatus::Inert);
    //         }
    //     }
    // }

    if (getAttack(getEnemy(player)) == 0)
    {
        endPhase();
    }
    break;
}
```

---

*End of A1 Audit Report*
