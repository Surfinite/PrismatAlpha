# A4: Damage Application (Fragile vs Non-Fragile)

**Auditor:** Claude Opus 4.6
**Date:** 2026-02-22
**Status:** COMPLETE
**Verdict:** MATCH (all three checks)

---

## 1. Overview of Damage Models

The AS3 client and C++ engine use fundamentally different internal representations for damage, but produce equivalent observable behavior in all cases.

### AS3 (Inst.as) — Dual-field model

Each instance tracks TWO fields:
- `health: int` — base/current HP. Constant for non-fragile units; decremented for fragile.
- `damage: int` — accumulated damage taken this defense/breach phase. Reset to 0 during swoosh.

The effective remaining HP is computed via the `damageItCanTake` getter:
```actionscript
// Inst.as:222-225
public function get damageItCanTake() : int {
    return this.health - (this.card.fragile ? 0 : this.damage);
}
```

Key interpretation:
- **Non-fragile:** `damageItCanTake = health - damage` (health stays constant, damage accumulates)
- **Fragile:** `damageItCanTake = health - 0 = health` (health decrements directly, damage field is also set but ignored by this getter)

### C++ (Card.h/Card.cpp) — Single-field model

Each card tracks ONE primary health field:
- `m_currentHealth: HealthType` — current HP. Reduced only for fragile units.
- `m_damageTaken: HealthType` — damage taken in the MOST RECENT `takeDamage()` call. NOT cumulative. Used only for undo bookkeeping.

```cpp
// Card.h:37-39
HealthType  m_currentHealth      = 0;
HealthType  m_damageTaken        = 0;
```

Effective HP is simply `currentHealth()`:
```cpp
// Card.cpp:320-323
HealthType Card::currentHealth() const {
    return m_currentHealth;
}
```

---

## 2. Code Path Traces

### 2.1 Blocking (Defense Phase)

#### AS3: MOVE_DEFEND (State.as:1712-1746)

```actionscript
inst = this.instIdToInst(instId);
card = inst.card;

// Cap damage at unit's health
if (inst.health > this.oppMana.attack)
    damage = this.oppMana.attack;     // absorb: unit survives
else
    damage = inst.health;             // full kill

this.oppMana.attack -= damage;
inst.damage += damage;                // accumulate damage field

if (inst.card.fragile)
    inst.health -= damage;            // fragile: reduce health directly

if (inst.damageItCanTake == 0)
    inst.deadness = C.DEADNESS_BLOCKED;  // unit killed
```

#### C++: GameState::blockWithCard (GameState.cpp:1543-1558)

```cpp
HealthType currentDamage = getResources(getEnemy(card.getPlayer())).amountOf(Resources::Attack);
HealthType currentHealth = card.currentHealth();
HealthType takeDamage = std::min(currentDamage, currentHealth);

card.takeDamage(takeDamage, DamageSource::Block);
if (card.isDead())
    killCardByID(card.getID(), CauseOfDeath::Blocker);

_getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
```

#### C++: Card::takeDamage (Card.cpp:395-429)

```cpp
void Card::takeDamage(const HealthType amount, const int damageSource) {
    m_damageTaken = std::min(amount, m_currentHealth);

    if (amount >= m_currentHealth) {
        // Unit dies — dispatch to appropriate cause of death
        switch (damageSource) {
            case DamageSource::Block:  kill(CauseOfDeath::Blocker);  break;
            case DamageSource::Breach: kill(CauseOfDeath::Breached); break;
        }
    }

    if (getType().isFragile()) {
        m_currentHealth -= std::min(amount, m_currentHealth);
        // Also sets m_wasBreached for breach source
    }
    // NON-FRAGILE: m_currentHealth is NOT reduced
}
```

### 2.2 Breach

#### AS3: MOVE_BREACH_OR_OVERKILL (State.as:1779-1818)

```actionscript
inst = this.instIdToInst(instId);
card = inst.card;

if (inst.health > this.turnMana.attack) {
    damage = this.turnMana.attack;
    C.ASSERT(inst.card.fragile, "Tried to partially breach a non-fragile unit.");
} else {
    damage = inst.health;
}

this.turnMana.attack -= damage;
inst.damage += damage;

if (inst.card.fragile)
    inst.health -= damage;

if (inst.damageItCanTake == 0) {
    inst.deadness = C.DEADNESS_WBO;       // killed
    // run deathScript if applicable
} else {
    // withstood (only possible for fragile with partial damage)
}
```

Key assertion: only fragile units can take partial breach damage (`C.ASSERT(inst.card.fragile, ...)`).

#### C++: GameState::breachCard (GameState.cpp:1562-1574)

```cpp
void GameState::breachCard(Card & card) {
    HealthType currentDamage = getResources(getEnemy(card.getPlayer())).amountOf(Resources::Attack);
    HealthType currentHealth = card.currentHealth();
    HealthType takeDamage = std::min(currentDamage, currentHealth);

    card.takeDamage(takeDamage, DamageSource::Breach);
    if (card.isDead())
        killCardByID(card.getID(), CauseOfDeath::Breached);

    _getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
}
```

#### C++: Card::canBreachFor (Card.cpp:355-373)

```cpp
bool Card::canBreachFor(const HealthType damage) const {
    if (damage == 0)                                      return false;
    if (!isBreachable())                                  return false;
    if (!getType().isFragile() && damage < currentHealth()) return false;
    return true;
}
```

Logic:
- Non-fragile: requires `damage >= currentHealth()` (full kill)
- Fragile: any `damage > 0` is sufficient (partial damage allowed)

### 2.3 Wipeout (Blocks all defenders, then breach)

#### AS3: MOVE_WIPEOUT (State.as:1855-1875)

```actionscript
this.glassBroken = true;
for each (inst in this.helper.oppDefenders) {
    damage = inst.health;
    this.turnMana.attack -= damage;
    inst.damage += damage;
    if (inst.card.fragile)
        inst.health -= damage;
    inst.deadness = C.DEADNESS_WBO;
}
```

All defenders take their full `health` in damage, dying instantly.

#### C++: GameState::blockWithAllBlockers (GameState.cpp:1502-1521)

```cpp
void GameState::blockWithAllBlockers(const PlayerID player) {
    CardID c(0);
    while (c < numCards(player)) {
        Card & card = _getCardByID(getCardIDs(player)[c]);
        if (card.canBlock()) {
            blockWithCard(card);         // uses standard blocking logic
            m_canBreachFrozenCard = true;
            c = 0;                       // restart from beginning (cards may be removed)
        } else {
            ++c;
        }
    }
}
```

Each blocker is processed via `blockWithCard`, which applies `min(currentDamage, currentHealth)` damage. The loop restarts after each block to handle cards removed from the list.

---

## 3. Formula Equivalence Proof

### 3.1 Non-fragile damage threshold

**Claim:** A non-fragile unit with starting health H dies if and only if damage >= H.

**AS3 proof:**
- `health = H` (constant, never decremented for non-fragile)
- Defense: `damage = min(H, oppMana.attack)`. If `oppMana.attack >= H`, then `damage = H`, `inst.damage = H`, `damageItCanTake = H - H = 0` -> DEAD.
- If `oppMana.attack < H`, then `damage = oppMana.attack`, `damageItCanTake = H - oppMana.attack > 0` -> SURVIVES.
- Breach: non-fragile requires `damage = inst.health = H` (the assert at line 1786 prevents partial breach of non-fragile).

**C++ proof:**
- `m_currentHealth = H` (never reduced for non-fragile)
- `takeDamage(amount, _)`: if `amount >= H` -> `kill()` -> DEAD. If `amount < H` -> not killed -> SURVIVES.
- `canBreachFor(damage)`: returns false if `!isFragile() && damage < currentHealth()`. So breach requires `damage >= H`.

**Verdict: MATCH.** Both engines kill non-fragile units if and only if incoming damage >= starting health.

### 3.2 Fragile damage threshold

**Claim:** A fragile unit with current health H dies if and only if damage >= H. Fragile units can also take PARTIAL damage that reduces health permanently.

**AS3 proof:**
- `health` is decremented by damage: `inst.health -= damage`
- `damageItCanTake = health - 0 = health` (fragile flag means `damage` field is ignored in getter)
- After taking D damage: `health = H - D`, `damageItCanTake = H - D`.
- If `D >= H`: `health = 0`, `damageItCanTake = 0` -> DEAD.
- If `D < H`: `health = H - D > 0`, `damageItCanTake = H - D > 0` -> SURVIVES with reduced HP.

**C++ proof:**
- `takeDamage(amount, _)` for fragile: `m_currentHealth -= min(amount, m_currentHealth)`.
- If `amount >= H`: `kill()` -> DEAD, `m_currentHealth = 0`.
- If `amount < H`: not killed, `m_currentHealth = H - amount` -> SURVIVES with reduced HP.

**Verdict: MATCH.** Both engines apply damage to fragile health directly, allow partial damage survival, and kill at full health.

### 3.3 Partial breach (fragile only)

**Claim:** Only fragile units can survive breach with reduced HP. Non-fragile breach is always lethal.

**AS3 proof:**
- `MOVE_BREACH_OR_OVERKILL` line 1783-1786: if `inst.health > turnMana.attack`, then `damage = turnMana.attack`, BUT `C.ASSERT(inst.card.fragile, ...)` — non-fragile partial breach is an assertion violation.
- Only fragile units reach the "withstood" path (line 1812).

**C++ proof:**
- `canBreachFor()` returns `false` for non-fragile if `damage < currentHealth()` — so the AI never attempts partial breach of non-fragile.
- For fragile, `canBreachFor()` returns `true` for any `damage > 0`, allowing partial breach.
- `breachCard()` applies `min(currentDamage, currentHealth)` — for fragile, this reduces HP. For non-fragile, since breach is only attempted when `damage >= health`, the min is always `health` (full kill).

**Verdict: MATCH.** Both engines restrict partial breach to fragile units only.

### 3.4 Defense total calculation

**AS3** (StateHelper.as:185): `ownDefense += inst.damageItCanTake`

At start of defense phase (after swoosh clears `damage` to 0):
- Non-fragile: `damageItCanTake = health - 0 = startingHealth`
- Fragile: `damageItCanTake = health - 0 = health` (= startingHealth at full HP, or less if previously partially breached)

**C++** (GameState.cpp:1527-1534): `block += card.currentHealth()`
- Non-fragile: `currentHealth() = startingHealth` (never reduced)
- Fragile: `currentHealth() = remaining HP`

At the start of defense, both compute the same total. During swoosh:
- AS3 clears `inst.damage = 0` and adds `healthGained` (State.as:2626-2627, 2711)
- C++ clears `m_damageTaken = 0` and adds `healthGained` in `beginTurn()` (Card.cpp:625)

Both restore fragile HP identically (capped at `healthMax`).

**Verdict: MATCH.**

---

## 4. Test Cases

### Test Case 1: Non-fragile Wall (5 HP) takes 2 damage (defense)

| Step | AS3 | C++ |
|------|-----|-----|
| Initial | `health=5, damage=0` | `m_currentHealth=5` |
| Incoming attack = 2 | `damage = min(5, 2) = 2` | `takeDamage = min(2, 5) = 2` |
| After damage | `health=5, damage=2, damageItCanTake=3` | `m_currentHealth=5, m_damageTaken=2` |
| Dead? | `damageItCanTake=3 > 0` -> NO | `2 < 5` -> NO |
| Attack remaining | `oppMana.attack -= 2` -> 0 | `set(Attack, 2-2)` -> 0 |
| **Result** | Alive, 3 effective HP remaining | Alive, `currentHealth()=5` (full, since non-fragile) |

Note: The "3 effective HP remaining" in AS3 is only relevant within the same defense phase. Since each unit blocks exactly once per defense, the `damage` field is cleared at swoosh. The C++ model doesn't track partial non-fragile damage at all (it doesn't need to — the unit already blocked).

**Verdict: MATCH** (unit survives, absorbs 2, 0 attack remains).

### Test Case 2: Fragile Forcefield (1 HP, fragile) takes any damage (defense)

| Step | AS3 | C++ |
|------|-----|-----|
| Initial | `health=1, damage=0, fragile=true` | `m_currentHealth=1, isFragile()=true` |
| Incoming attack = 5 | `damage = min(1, 5) = 1` | `takeDamage = min(5, 1) = 1` |
| After damage | `health=1-1=0, damage=1, damageItCanTake=0` | `m_currentHealth=1-1=0` |
| Dead? | `damageItCanTake=0` -> YES (`BLOCKED`) | `1 >= 1` -> YES (`kill(Blocker)`) |
| Attack remaining | `oppMana.attack -= 1` -> 4 | `set(Attack, 5-1)` -> 4 |
| **Result** | Dead, 4 attack passes through | Dead, 4 attack passes through |

**Verdict: MATCH.**

### Test Case 3: Non-fragile unit at exactly 1 HP remaining (breach)

A non-fragile unit with `startingHealth=1` (e.g., Drone with 1 HP) facing 1 damage:

| Step | AS3 | C++ |
|------|-----|-----|
| Initial | `health=1, damage=0, fragile=false` | `m_currentHealth=1, isFragile()=false` |
| Breach with attack = 1 | `damage = min(1, 1) = 1` | `takeDamage = min(1, 1) = 1` |
| After damage | `health=1, damage=1, damageItCanTake=0` | `m_damageTaken=1, m_currentHealth=1` (non-fragile, not reduced) |
| Dead? | `damageItCanTake=0` -> YES (`WBO`) | `1 >= 1` -> YES (`kill(Breached)`) |
| **Result** | Dead | Dead |

**Verdict: MATCH.**

### Test Case 4: Fragile Polywall (4 HP, fragile, healthGained=4) takes 2 breach damage

| Step | AS3 | C++ |
|------|-----|-----|
| Initial | `health=4, damage=0, fragile=true` | `m_currentHealth=4, isFragile()=true` |
| canBreach with attack=2? | `2 > 0 && fragile` -> YES | `canBreachFor(2): isFragile() -> skip non-fragile check -> true` |
| Breach with attack = 2 | `damage = min(4, 2) = 2` | `takeDamage = min(2, 4) = 2` |
| After damage | `health=4-2=2, damage=2, damageItCanTake=2` | `m_currentHealth=4-2=2` |
| Dead? | `damageItCanTake=2 > 0` -> NO | `2 < 4` -> NO |
| Attack remaining | `turnMana.attack -= 2` -> 0 | `set(Attack, 2-2)` -> 0 |
| **Result** | Alive with 2 HP, survives breach | Alive with `currentHealth()=2`, survives breach |

**Verdict: MATCH.**

### Test Case 5: Melee on non-fragile (AS3 MOVE_MELEE)

Melee is an AS3 concept for the action-phase "assign frontline" mechanic.

```actionscript
C.ASSERT(!card.fragile, "Fragile cards cannot be meleed.");
damage = inst.health;
turnMana.attack -= damage;
inst.damage += damage;
inst.deadness = C.DEADNESS_MELEED;
```

Non-fragile melee: `damage = inst.health` (full HP), unit marked as meleed. `inst.health` unchanged (non-fragile).

C++ equivalent: `canFrontlineFor()` (Card.cpp:650-668):
```cpp
bool Card::canFrontlineFor(const HealthType damage) const {
    if (!getType().isFrontline()) return false;
    if (isUnderConstruction()) return false;
    if (!getType().isFragile() && (damage < currentHealth())) return false;
    return true;
}
```

Non-fragile frontline requires `damage >= currentHealth()` — full kill only, matching AS3's assertion.

**Verdict: MATCH.**

---

## 5. Undo Logic Comparison

### AS3 Undo (MOVE_UNBREACH_OR_UNOVERKILL, State.as:1820-1853)

```actionscript
damage = inst.damage;
turnMana.attack += damage;
inst.damage -= damage;       // reset damage to 0
if (inst.card.fragile)
    inst.health += damage;   // restore fragile health
if (inst.deadness == C.DEADNESS_WBO)
    inst.deadness = C.DEADNESS_ALIVE;
```

### C++ Undo (Card::undoBreach, Card.cpp:541-557)

```cpp
void Card::undoBreach() {
    if (getType().isFragile()) {
        m_currentHealth += m_damageTaken;     // restore fragile health
    } else {
        m_currentHealth = getType().getStartingHealth();  // restore non-fragile to full
    }
    m_wasBreached = false;
    m_damageTaken = 0;
}
```

Both restore the card to its pre-breach state. Note:
- AS3 uses `inst.damage` (accumulated) to restore fragile health.
- C++ uses `m_damageTaken` (last call's amount) to restore fragile health.

Since breach damage is applied once per card per breach phase, `m_damageTaken` equals the total breach damage for that card, matching AS3's `inst.damage`.

For non-fragile, AS3 restores by subtracting `damage` from `inst.damage` (resetting it to 0) and leaving `inst.health` alone. C++ restores `m_currentHealth` to `startingHealth`. Both are equivalent since non-fragile `m_currentHealth` was never changed.

**Verdict: MATCH.**

---

## 6. Swoosh (Turn Boundary) Health Reset

### AS3 (State.as:2622-2725)

```actionscript
if (inst.damage > 0) {
    inst.damage = 0;                         // clear accumulated damage
}
// ... then later:
inst.health += card.healthGained;            // heal
if (inst.health > card.healthMax)
    inst.health = card.healthMax;            // cap at max
```

### C++ (Card.cpp:574-642, beginTurn)

```cpp
m_damageTaken = 0;
// ... then later for non-delayed, non-constructing:
m_currentHealth += m_type.getHealthGained();
if (m_type.getHealthMax() > 0 && m_currentHealth > m_type.getHealthMax())
    m_currentHealth = m_type.getHealthMax();
```

Both clear damage tracking and apply health regeneration capped at max. For fragile units (e.g., Forcefield: healthGained=1, healthMax=1), this fully restores HP each turn. For non-fragile units, `healthGained` is typically 0, so health stays at `startingHealth`.

**Verdict: MATCH.**

---

## 7. Architectural Difference Summary

| Aspect | AS3 | C++ | Equivalent? |
|--------|-----|-----|-------------|
| Health representation | `health` + `damage` fields | `m_currentHealth` only | YES (at all observable points) |
| Non-fragile damage tracking | `damage` accumulates, `health` constant | `m_currentHealth` constant, `m_damageTaken` = last call | YES (death at same threshold) |
| Fragile damage tracking | `health -= damage`, `damage` accumulates | `m_currentHealth -= amount` | YES (health decreases identically) |
| Effective HP getter | `damageItCanTake = health - (fragile ? 0 : damage)` | `currentHealth()` | YES (same result) |
| Block absorption cap | `min(inst.health, oppMana.attack)` | `min(currentDamage, currentHealth)` | YES |
| Breach eligibility | Fragile: any damage. Non-fragile: `atk >= health` | `canBreachFor`: Fragile: `damage > 0`. Non-fragile: `damage >= currentHealth()` | YES |
| Partial breach | Only fragile (assert enforced) | Only fragile (`canBreachFor` gate) | YES |
| Undo | Restores `damage`/`health` to pre-action values | Restores `m_currentHealth` via `m_damageTaken` or `startingHealth` | YES |
| Swoosh reset | `damage = 0`, then `health += healthGained` | `m_damageTaken = 0`, then `m_currentHealth += healthGained` | YES |

---

## 8. Final Verdicts

| Check | AS3 Location | C++ Location | Verdict |
|-------|-------------|-------------|---------|
| Fragile damage tolerance | Inst.as:222-225 `damageItCanTake` | Card.cpp:355-373 `canBreachFor()` + Card.cpp:395-429 `takeDamage()` | **MATCH** |
| Non-fragile cumulative damage | Inst.as `damage` field + State.as:1712-1746 | Card.cpp:395-429 `takeDamage()` (non-fragile path) | **MATCH** |
| Fragile death threshold | State.as:1779-1818 `MOVE_BREACH_OR_OVERKILL` | Card.cpp:395-429 + GameState.cpp:1562-1574 `breachCard()` | **MATCH** |

### Key Finding: Architectural Divergence, Behavioral Equivalence

The AS3 and C++ engines use fundamentally different internal representations:

- **AS3** uses a dual-field model (`health` + `damage`) where `health` is the "base/starting" value for non-fragile and "current remaining" for fragile, and `damage` tracks accumulated damage.
- **C++** uses a single-field model (`m_currentHealth`) where the value is the "current remaining" HP for fragile and stays at starting health for non-fragile.

Despite this architectural divergence, the two models produce identical observable behavior at every decision point: death thresholds, breach eligibility, defense totals, absorb calculations, undo restoration, and swoosh reset.

**No mismatches found. All three checks PASS.**
