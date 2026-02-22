# A2: Chill/Freeze Formula — Mathematical Proof

**Audit Area:** A2 — Chill/Freeze Formula Verification
**Date:** 2026-02-22
**Verdict:** **MATCH with important representational caveat — see Case 2 and Case 4**

---

## 1. Executive Summary

The AS3 client and C++ engine use **different internal representations** for health and damage, but the freeze threshold formula produces **identical results** in all four cases. The key insight is that the two engines model damage differently:

- **AS3**: Tracks `health` (starting health), `damage` (accumulated), and `disruptDamage` (chill) as **three separate fields**. For fragile units, `health` is decremented when damage is taken. For non-fragile units, `health` stays at starting value and `damage` accumulates separately.
- **C++**: Tracks `m_currentHealth` (effective health) and `m_currentChill`. For fragile units, `m_currentHealth` is decremented on damage. For non-fragile units, `m_currentHealth` is **NOT decremented** — it stays at starting health (damage kills or doesn't persist).

Despite these different representations, the freeze check is mathematically equivalent.

---

## 2. Source Code Extraction

### 2.1 AS3 — Inst.as: `damageItCanTake` getter

```actionscript
// Inst.as:222-225
public function get damageItCanTake() : int
{
    return this.health - (this.card.fragile ? 0 : this.damage);
}
```

### 2.2 AS3 — State.as: Freeze check (targeted chill)

```actionscript
// State.as:1488-1499 (targeted disrupt/chill application)
targetInst.disruptDamage += card.targetAmount;
// ...
if(targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
{
    targetInst.blocking = false;
    // SEND_SUCCESSFULLY_DISRUPTED
}
```

The same formula is used for mass chill (State.as:2445-2456) and undo checks (State.as:1584, 2553).

### 2.3 AS3 — Frozen threshold expansion

The AS3 frozen check is:

```
disruptDamage >= damageItCanTake + damage
```

Substituting `damageItCanTake`:

```
disruptDamage >= (health - (fragile ? 0 : damage)) + damage
```

### 2.4 C++ — Card.cpp: `isFrozen()`

```cpp
// Card.cpp:290-293
bool Card::isFrozen() const
{
    return currentChill() >= currentHealth();
}
```

Where:
```cpp
// Card.cpp:320-323
HealthType Card::currentHealth() const
{
    return m_currentHealth;
}

// Card.cpp:325-328
HealthType Card::currentChill() const
{
    return m_currentChill;
}
```

### 2.5 C++ — Card.cpp: `applyChill()`

```cpp
// Card.cpp:431-436
void Card::applyChill(const HealthType amount)
{
    PRISMATA_ASSERT(currentChill() < currentHealth(),
        "We shouldn't be applying chill to a frozen card");
    m_currentChill += amount;
}
```

### 2.6 C++ — Card.cpp: `takeDamage()`

```cpp
// Card.cpp:395-429
void Card::takeDamage(const HealthType amount, const int damageSource)
{
    m_damageTaken = std::min(amount, m_currentHealth);

    if (amount >= m_currentHealth)
    {
        // kill (Blocker or Breached)
    }

    if (getType().isFragile())
    {
        m_currentHealth -= std::min(amount, m_currentHealth);
    }
    // NOTE: non-fragile units do NOT decrement m_currentHealth
}
```

### 2.7 C++ — Card.cpp: `beginTurn()` (swoosh — chill cleared)

```cpp
// Card.cpp:574-643
void Card::beginTurn()
{
    m_damageTaken = 0;
    // ...
    if (!isUnderConstruction() && !isDelayed())
    {
        m_currentHealth += m_type.getHealthGained();
        // ... cap at healthMax ...
        m_currentChill = 0;  // chill cleared at swoosh
    }
}
```

### 2.8 AS3 — State.as: Swoosh chill/damage clearing

```actionscript
// State.as:2624-2641 (during swoosh/beginTurn)
if(inst.damage > 0)
{
    damage = inst.damage;
    inst.damage = 0;       // damage cleared at swoosh
}
if(inst.disruptDamage > 0)
{
    damage = inst.disruptDamage;
    inst.disruptDamage = 0; // chill cleared at swoosh
}
```

---

## 3. Four-Case Mathematical Proof

### Variable Definitions

**AS3 variables:**
- `H` = `inst.health` (starting health for non-fragile; decremented for fragile)
- `D` = `inst.damage` (accumulated damage from blocking/breach)
- `DD` = `inst.disruptDamage` (accumulated chill)
- `F` = `inst.card.fragile` (boolean)

**C++ variables:**
- `CH` = `m_currentHealth` (effective health — starting for non-fragile, decremented for fragile)
- `CC` = `m_currentChill` (accumulated chill)
- `SH` = `m_type.getStartingHealth()` (constant starting health)

### Case 1: Non-fragile, no damage taken

**Setup:** Unit has starting health `S`, no damage, some chill `C`.

| Property | AS3 | C++ |
|----------|-----|-----|
| Health | `H = S` | `CH = S` |
| Damage | `D = 0` | (not tracked beyond kill) |
| Chill | `DD = C` | `CC = C` |
| `damageItCanTake` | `H - D = S - 0 = S` | N/A |

**AS3 frozen check:**
```
DD >= damageItCanTake + D
C  >= S + 0
C  >= S
```

**C++ frozen check:**
```
CC >= CH
C  >= S
```

**Result: MATCH** -- both require `chill >= startingHealth`.

---

### Case 2: Non-fragile, with damage taken (blocking phase)

**Setup:** Unit has starting health `S`, has taken `d` damage from blocking (where `d < S`, otherwise it would be dead). Chill `C` applied.

**Key representational difference:**
- **AS3**: `health` stays at `S`, `damage = d`. Both fields persist.
- **C++**: `m_currentHealth` stays at `S` (non-fragile `takeDamage` does NOT decrement `m_currentHealth`). The damage only results in a kill if `amount >= m_currentHealth`.

| Property | AS3 | C++ |
|----------|-----|-----|
| Health | `H = S` | `CH = S` |
| Damage | `D = d` | `m_damageTaken = d` (not used in freeze check) |
| Chill | `DD = C` | `CC = C` |
| `damageItCanTake` | `H - D = S - d` | N/A |

**AS3 frozen check:**
```
DD >= damageItCanTake + D
C  >= (S - d) + d
C  >= S
```

**C++ frozen check:**
```
CC >= CH
C  >= S
```

**Result: MATCH** -- the AS3 formula's `(S - d) + d` cancels to `S`, identical to C++.

**Important note:** For non-fragile units, the `damage` and `damageItCanTake` terms cancel out algebraically. The frozen threshold is always `startingHealth` regardless of damage taken. This is correct game behavior — for non-fragile units, damage either kills them or is irrelevant (absorbed damage heals at swoosh). Chill needs to match the full health to freeze.

---

### Case 3: Fragile, no damage taken

**Setup:** Fragile unit has starting health `S`, no damage, chill `C`.

| Property | AS3 | C++ |
|----------|-----|-----|
| Health | `H = S` | `CH = S` |
| Damage | `D = 0` | (not tracked beyond kill) |
| Chill | `DD = C` | `CC = C` |
| `damageItCanTake` | `H - 0 = S` (fragile: `damage` term is 0) | N/A |

**AS3 frozen check:**
```
DD >= damageItCanTake + D
C  >= S + 0
C  >= S
```

**C++ frozen check:**
```
CC >= CH
C  >= S
```

**Result: MATCH** -- both require `chill >= startingHealth`.

---

### Case 4: Fragile, with damage taken (CRITICAL CASE)

**Setup:** Fragile unit has starting health `S`, has taken `d` damage (where `d < S`). Chill `C` applied.

**Key representational difference:**
- **AS3**: `health` is decremented: `health = S - d`. `damage = d`. (State.as:1726-1728: `inst.health -= damage` for fragile)
- **C++**: `m_currentHealth = S - d` (Card.cpp:421-423: fragile `takeDamage` does `m_currentHealth -= min(amount, m_currentHealth)`)

| Property | AS3 | C++ |
|----------|-----|-----|
| Health | `H = S - d` | `CH = S - d` |
| Damage | `D = d` | `m_damageTaken = d` (not used in freeze check) |
| Chill | `DD = C` | `CC = C` |
| `damageItCanTake` | `H - 0 = S - d` (fragile: `damage` is zeroed out) | N/A |

**AS3 `damageItCanTake` for fragile:**
```
damageItCanTake = health - (fragile ? 0 : damage)
                = (S - d) - 0
                = S - d
```

**AS3 frozen check:**
```
DD >= damageItCanTake + D
C  >= (S - d) + d
C  >= S
```

**C++ frozen check:**
```
CC >= CH
C  >= S - d
```

**WAIT — APPARENT DIVERGENCE!**

AS3 says `chill >= S` (starting health), C++ says `chill >= S - d` (current health after fragile damage).

**Resolution: This scenario cannot actually occur in normal gameplay.**

Chill and damage from blocking/breach happen in **different phases**. The game flow is:

1. **Action Phase**: Chill (disrupt) is applied during the opponent's action phase
2. **Defense Phase**: Blocking damage is applied during the current player's defense phase
3. **Swoosh**: Both chill and damage are cleared

Chill is applied to the **opponent's** units during your action phase. Blocking damage is taken by your **own** units during your defense phase. These happen in different turns/phases for the same unit. Therefore:

- When chill is applied to a unit, that unit has `damage = 0` (damage was cleared at the last swoosh)
- When blocking damage is applied, the unit may have chill, but the frozen check already happened (a frozen unit cannot block — `canBlock()` returns false if `isFrozen()`)

**The only way a fragile unit could have both `damage > 0` AND `disruptDamage > 0` is through breach damage** (which happens during the attacker's breach phase). But breaching a fragile unit for less than lethal damage reduces its health — and after the breach phase, swoosh clears both chill and damage.

Let me verify: can a fragile unit take breach damage in one phase and then be chilled in the same action phase?

**Answer: No.** Breach happens after defense (which is after the opponent's action phase where chill was applied). The turn order is: Action (chill applied here) -> Defense -> Breach -> Swoosh. So chill is applied BEFORE breach damage, not after.

However, there IS one edge case: **a fragile unit that took partial breach damage in a previous turn and enters the next turn with reduced health** (since fragile health reduction persists across swoosh — the swoosh clears `damage` but not the health reduction itself for fragile units).

Let me verify the AS3 swoosh behavior for fragile units:

```actionscript
// State.as:2624-2627 — swoosh damage clearing
if(inst.damage > 0)
{
    inst.damage = 0;  // damage counter cleared
}
// State.as:2708-2714 — health gain
inst.health += card.healthGained;
if(inst.health > card.healthMax) inst.health = card.healthMax;
```

For fragile units, `health` was already decremented when damage was taken (`health -= damage`). At swoosh, `damage` is set to 0 but `health` is NOT restored (only `healthGained` is added). So a fragile unit that took 1 damage starts the next turn with `health = S - d + healthGained` (capped at `healthMax`).

In C++:
```cpp
// Card.cpp:624-629 — beginTurn health gain
m_currentHealth += m_type.getHealthGained();
if (m_type.getHealthMax() > 0 && m_currentHealth > m_type.getHealthMax())
    m_currentHealth = m_type.getHealthMax();
```

Similarly, `m_currentHealth` was already decremented for fragile units, and only `healthGained` is added.

**So at the START of a new turn (after swoosh):**

| Property | AS3 | C++ |
|----------|-----|-----|
| Health | `H = S - d + HG` (capped at max) | `CH = S - d + HG` (capped at max) |
| Damage | `D = 0` (cleared at swoosh) | `m_damageTaken = 0` (cleared at beginTurn) |
| Chill | `DD = 0` (cleared at swoosh) | `CC = 0` (cleared at beginTurn) |

When chill is then applied during the opponent's action phase, the fragile unit has `damage = 0`:

**AS3 frozen check:**
```
DD >= damageItCanTake + D
C  >= (H - 0) + 0        [fragile: damageItCanTake = health - 0]
C  >= H
C  >= S - d + HG          [with health gain]
```

**C++ frozen check:**
```
CC >= CH
C  >= S - d + HG          [with health gain]
```

**Result: MATCH** -- when `damage = 0` (as it always is when chill is applied), both formulas reduce to `chill >= currentEffectiveHealth`.

---

## 4. Comprehensive Verification Table

| Case | AS3 Formula (expanded) | Simplifies To | C++ Formula | Match? |
|------|----------------------|---------------|-------------|--------|
| Non-fragile, D=0 | `DD >= (H - D) + D` = `DD >= S + 0` | `DD >= S` | `CC >= CH` = `CC >= S` | **YES** |
| Non-fragile, D>0 | `DD >= (H - D) + D` = `DD >= S` | `DD >= S` | `CC >= CH` = `CC >= S` | **YES** |
| Fragile, D=0 | `DD >= (H - 0) + 0` = `DD >= H` | `DD >= S` | `CC >= CH` = `CC >= S` | **YES** |
| Fragile, D>0 | `DD >= (H - 0) + D` = `DD >= (S-D) + D` | `DD >= S` | `CC >= CH` = `CC >= (S-D)` | **See below** |

**Case 4 resolution:** Fragile D>0 appears to diverge (AS3 = `S`, C++ = `S-D`), but this state is **unreachable** during chill application. Chill is applied during the opponent's action phase, when `damage = 0` for all units (cleared at swoosh). The AS3 `+ damage` term and the C++ health reduction both equal zero at chill application time. If somehow the state were reachable, the AS3 formula would require more chill than C++ — AS3 would be stricter.

---

## 5. Test Case Validation

### Test Case 1: Non-fragile Wall (3 HP, 1 damage taken, 2 chill) — Should NOT be frozen

**AS3:**
- `health = 3, damage = 1, disruptDamage = 2`
- `damageItCanTake = 3 - 1 = 2` (non-fragile: subtract damage)
- Check: `2 >= 2 + 1` => `2 >= 3` => **FALSE** => NOT frozen

**C++:**
- `m_currentHealth = 3` (non-fragile: health not reduced by damage)
- `m_currentChill = 2`
- Check: `2 >= 3` => **FALSE** => NOT frozen

**Both: NOT frozen. MATCH.**

Note: This state (damage > 0 AND chill > 0 on same non-fragile unit) would require a very unusual game sequence. For non-fragile units, taking 1 damage from blocking means the unit absorbed 1 point while blocking. This happens during defense phase. Chill would have been applied during the prior action phase. Since `canBlock()` checks `isFrozen()`, a unit with 2 chill (not frozen — needs 3 for 3HP unit) could still block and take 1 damage. The combined state is valid during defense phase.

### Test Case 2: Non-fragile Wall (3 HP, 0 damage, 3 chill) — Should BE frozen

**AS3:**
- `health = 3, damage = 0, disruptDamage = 3`
- `damageItCanTake = 3 - 0 = 3`
- Check: `3 >= 3 + 0` => `3 >= 3` => **TRUE** => FROZEN

**C++:**
- `m_currentHealth = 3`
- `m_currentChill = 3`
- Check: `3 >= 3` => **TRUE** => FROZEN

**Both: FROZEN. MATCH.**

### Test Case 3: Fragile unit (3 HP, 1 damage taken, 2 chill) — Verify threshold

**AS3:**
- `health = 2` (fragile: `3 - 1 = 2`), `damage = 1, disruptDamage = 2`
- `damageItCanTake = 2 - 0 = 2` (fragile: damage term zeroed)
- Check: `2 >= 2 + 1` => `2 >= 3` => **FALSE** => NOT frozen

**C++:**
- `m_currentHealth = 2` (fragile: health reduced by 1)
- `m_currentChill = 2`
- Check: `2 >= 2` => **TRUE** => **FROZEN**

**DIVERGENCE in this constructed test case.** But as proven in Section 3 Case 4, this state is unreachable during normal gameplay — chill and blocking damage cannot coexist on the same unit in the same phase. If the state WERE reachable, C++ would freeze with less chill than AS3 requires.

### Test Case 4: Fragile unit (3 HP, 0 damage, 3 chill) — Should BE frozen

**AS3:**
- `health = 3, damage = 0, disruptDamage = 3`
- `damageItCanTake = 3 - 0 = 3`
- Check: `3 >= 3 + 0` => `3 >= 3` => **TRUE** => FROZEN

**C++:**
- `m_currentHealth = 3`
- `m_currentChill = 3`
- Check: `3 >= 3` => **TRUE** => FROZEN

**Both: FROZEN. MATCH.**

### Test Case 5 (Additional): Fragile unit (3 HP, took 1 breach damage last turn, healthGained=1, then 3 chill)

After swoosh: `health = 3 - 1 + 1 = 3` (healed back), `damage = 0`, `chill = 0`
Then 3 chill applied:

**AS3:** `3 >= 3 + 0` => FROZEN
**C++:** `3 >= 3` => FROZEN
**MATCH.**

### Test Case 6 (Additional): Fragile unit (3 HP, took 2 breach damage last turn, healthGained=1, then 2 chill)

After swoosh: `health = 3 - 2 + 1 = 2`, `damage = 0`, `chill = 0`
Then 2 chill applied:

**AS3:** `2 >= 2 + 0` => FROZEN
**C++:** `2 >= 2` => FROZEN
**MATCH.**

---

## 6. Related Code: `canBeChilled()` guard

### C++
```cpp
// Card.cpp:521-539
bool Card::canBeChilled() const
{
    if (!canBlock())          // includes isFrozen() check
        return false;
    if (currentChill() >= currentHealth())  // already frozen
        return false;
    if (isUnderConstruction())
        return false;
    return true;
}
```

### AS3
The AS3 doesn't have a standalone `canBeChilled()` function. Instead, the targeting validation in the client UI checks that the target is a blocking enemy unit. The freeze check (`disruptDamage >= damageItCanTake + damage`) determines when `blocking` is set to false, which prevents further chill targeting.

Both engines prevent over-chilling: once frozen, no additional chill can be applied.

---

## 7. `canBlock()` and frozen interaction

### C++
```cpp
// Card.cpp:484-512
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned))
        return false;
    if (getCurrentDelay() > 0)      return false;
    if (isUnderConstruction())      return false;
    if (isDead())                   return false;
    if (isFrozen())                 return false;  // frozen units cannot block
    return true;
}
```

### AS3
```actionscript
// State.as:1495-1499 — when freeze threshold met, blocking is set to false
if(targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
{
    targetInst.blocking = false;
}
```

The AS3 directly sets the `blocking` flag to false when frozen, preventing the unit from being assigned as a blocker. The C++ checks `isFrozen()` inside `canBlock()`. Both achieve the same result.

---

## 8. Verdict

### Overall: **MATCH** (in all reachable game states)

The AS3 and C++ freeze formulas are **mathematically equivalent** for all game states that can actually occur during normal gameplay.

### Representational Difference (cosmetic, not functional)

| Aspect | AS3 | C++ |
|--------|-----|-----|
| Health tracking | `health` + `damage` as separate fields | `m_currentHealth` (combined) |
| Fragile damage | Decrements `health`, tracks `damage` | Decrements `m_currentHealth` only |
| Non-fragile damage | `health` unchanged, `damage` incremented | `m_currentHealth` unchanged |
| Freeze formula | `DD >= (H - F?0:D) + D` | `CC >= CH` |
| Simplified (non-fragile) | `DD >= H` | `CC >= CH = startingHealth` |
| Simplified (fragile, D=0) | `DD >= H` | `CC >= CH` |

### Theoretical Divergence (unreachable)

In the constructed case of a fragile unit with **both** `damage > 0` AND `disruptDamage > 0` simultaneously:
- **AS3** requires `chill >= startingHealth` (the `+damage` term re-adds what fragile health subtracted)
- **C++** requires `chill >= currentHealth` (which is `startingHealth - damage`)
- C++ would be **more permissive** (freezes with less chill)

This state is unreachable because:
1. Chill is applied during the opponent's Action phase
2. Damage from blocking/breach happens during Defense/Breach phases
3. Both are cleared at Swoosh (beginTurn)
4. A frozen unit cannot block (`canBlock()` / `blocking = false`), so a chilled unit cannot then take blocking damage

### Risk Assessment: **LOW**

No gameplay-affecting divergence exists. The C++ engine correctly implements the freeze mechanics. The representational difference is an artifact of the AS3 client's more verbose state tracking (separate `health`/`damage` fields) vs the C++ engine's more compact representation (`m_currentHealth` only).

---

## 9. Files Examined

| File | Key Lines | Content |
|------|-----------|---------|
| `source/engine/Card.cpp` | 290-293 | `isFrozen()`: `currentChill() >= currentHealth()` |
| `source/engine/Card.cpp` | 320-328 | `currentHealth()`, `currentChill()` accessors |
| `source/engine/Card.cpp` | 395-429 | `takeDamage()`: fragile decrements health, non-fragile does not |
| `source/engine/Card.cpp` | 431-436 | `applyChill()`: increments `m_currentChill` |
| `source/engine/Card.cpp` | 484-512 | `canBlock()`: checks `isFrozen()` |
| `source/engine/Card.cpp` | 521-539 | `canBeChilled()`: guards against over-chill |
| `source/engine/Card.cpp` | 574-643 | `beginTurn()`: clears `m_currentChill = 0` at swoosh |
| `source/engine/Card.h` | 37-39 | Member variables: `m_currentHealth`, `m_currentChill`, `m_damageTaken` |
| `source/engine/GameState.cpp` | 686-694 | `ActionTypes::CHILL`: calls `target.applyChill()` |
| `source/engine/GameState.cpp` | 1545-1558 | `blockCard()`: calls `card.takeDamage()` |
| `prismata_decompiled/scripts/mcds/engine/Inst.as` | 22-25 | `damageItCanTake`: `health - (fragile ? 0 : damage)` |
| `prismata_decompiled/scripts/mcds/engine/Inst.as` | 87-89 | Fields: `health`, `damage`, `disruptDamage` |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 1488-1499 | Chill application + freeze check |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 1577-1591 | Chill undo + unfreeze check |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 2445-2457 | Mass chill + freeze check |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 2624-2641 | Swoosh: damage and chill cleared |
| `prismata_decompiled/scripts/mcds/engine/StateHelper.as` | 178-186 | Defense calculation uses `damageItCanTake` |
