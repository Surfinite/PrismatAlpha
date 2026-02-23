# P2 Sweep: C1-C5 Medium-Priority Edge Cases

Audited: 2026-02-22

---

## C1: Construction Time / Delay Interaction

### How AS3 Works (State.as swoosh, lines 2642-2678)

The AS3 swoosh uses an `if / else if / else if` chain per instance:

```actionscript
if (inst.constructionTime > 0) {
    --inst.constructionTime;
    if (inst.constructionTime != 0) {
        // still constructing — skip everything else
        continue;
    }
    // construction just finished — fall through to healing/charge/refresh
}
else if (inst.delay > 0) {
    --inst.delay;
    if (inst.delay != 0) {
        // still delayed — skip everything else
        continue;
    }
    // delay just finished — fall through to healing/charge/refresh
}
else if (inst.lifespan > 0) {
    --inst.lifespan;
    if (inst.lifespan == 0) {
        // dies — collected and removed
        continue;
    }
}
// ... healing, charge, role refresh follow
```

Key properties:
1. **Mutual exclusivity**: Construction and delay are in an `if/else if` chain. Only one is decremented per swoosh.
2. **Construction checked first**: If `constructionTime > 0`, delay is never touched.
3. **Continue on non-zero**: If the timer didn't reach 0, `continue` skips healing/charge/refresh.
4. **Fall-through on zero**: When timer hits 0, execution continues to healing/charge/refresh within that same swoosh.

### How C++ Works (Card::beginTurn, lines 574-643)

```cpp
// reduce lifespan (only if NOT constructing and NOT delayed)
if (!isUnderConstruction() && !isDelayed() && m_lifespan > 0) {
    --m_lifespan;
    if (m_lifespan == 0) { kill(CauseOfDeath::Lifespan); return; }
}

// reduce delay (only if NOT constructing but IS delayed)
if (!isUnderConstruction() && isDelayed()) {
    --m_currentDelay;
}
if (isDelayed()) {
    setStatus(CardStatus::Inert);
}

// reduce construction time (if constructing)
if (isUnderConstruction()) {
    m_constructionTime--;
}

// healing, role refresh (only if NOT constructing AND NOT delayed)
if (!isUnderConstruction() && !isDelayed()) {
    m_currentHealth += m_type.getHealthGained();
    // ... cap, status set, chill reset
}
```

Key properties:
1. **Sequential checks, not if/else**: Each check is a separate `if`, not chained `else if`.
2. **Construction checked independently of delay**: Both could theoretically decrement in the same turn if both were set. However, a card can only have one or the other set at creation time (see below).
3. **Post-decrement gate**: The final `if (!isUnderConstruction() && !isDelayed())` block only runs if BOTH are zero after decrement. This matches AS3's fall-through behavior.

### Creation: Construction vs Delay

**AS3 (Inst.as lines 91-99):**
```actionscript
if (invulnerable) {
    this.constructionTime = buildTime;
    this.delay = 0;
} else {
    this.constructionTime = 0;
    this.delay = buildTime;
}
```

**C++ (Card.cpp lines 200-229):**
```cpp
case CardCreationMethod::Bought:       m_constructionTime = type.getConstructionTime(); break;
case CardCreationMethod::AbilityScript: m_currentDelay = delay; break;
case CardCreationMethod::BuyScript:     m_constructionTime = delay; break;
```

Both systems ensure a card starts with either `constructionTime > 0` or `delay > 0`, never both simultaneously. The AS3 uses an `invulnerable` flag (bought = invulnerable = uses constructionTime; created by ability = not invulnerable = uses delay).

### Order Difference Analysis

In AS3, construction is checked first via `if`, delay is `else if`. In C++, delay is decremented BEFORE construction (`!isUnderConstruction() && isDelayed()` on line 605, then `isUnderConstruction()` on line 616). However, since a card never has both set simultaneously, the order is irrelevant in practice.

**Edge case: constructionTime=1 finishing**
- AS3: `constructionTime` goes from 1 to 0, falls through to healing/refresh in same swoosh. Delay was never set.
- C++: `isUnderConstruction()` is true, so delay block skipped. `m_constructionTime--` makes it 0. Then the final guard `!isUnderConstruction() && !isDelayed()` is true, so healing/refresh runs. **Match.**

**Edge case: delay=1 finishing**
- AS3: `constructionTime == 0`, so enters `else if (inst.delay > 0)`. Decrements to 0, falls through to healing/refresh.
- C++: `!isUnderConstruction() && isDelayed()` is true, so `m_currentDelay--` makes it 0. Then `isDelayed()` is false, so no Inert status. `isUnderConstruction()` is false, so no construction decrement. Final guard passes, healing/refresh runs. **Match.**

### Verdict: MATCH

Construction and delay are mutually exclusive at creation. Both engines decrement exactly one per turn, and both engines gate healing/charge/refresh behind "construction done AND delay done". The different check ordering in C++ is safe because both fields are never simultaneously non-zero.

**Risk: NONE for current card set.**

---

## C2: Health Gained / Healing Cap

### AS3 (State.as swoosh, lines 2708-2725)

```actionscript
if (card.healthGained != 0) {
    oldHealth = inst.health;
    inst.health += card.healthGained;
    if (inst.health > card.healthMax) {
        inst.health = card.healthMax;
    }
    // dispatch event
}
```

Runs after construction/delay resolution, after role refresh (line 2700-2705), before charge gain (line 2726).

### C++ (Card::beginTurn, lines 624-629)

```cpp
m_currentHealth += m_type.getHealthGained();
if (m_type.getHealthMax() > 0 && m_currentHealth > m_type.getHealthMax()) {
    m_currentHealth = m_type.getHealthMax();
}
```

Runs inside the `if (!isUnderConstruction() && !isDelayed())` block, after lifespan/delay/construction processing, before status set.

### Differences

1. **healthMax == 0 guard**: C++ has an extra check `m_type.getHealthMax() > 0` before applying the cap. AS3 does not have this guard — it unconditionally caps at `healthMax`. If `healthMax == 0` and `healthGained > 0`, AS3 would set health to 0 (killing the unit), while C++ would let health grow unbounded. However, in practice, `healthGained > 0` only exists on units with a meaningful `healthMax` (e.g., Wall, Infusion Grid). No unit has `healthGained > 0` with `healthMax == 0` in the current card set.

2. **Timing within swoosh**: Both execute after construction/delay resolution. AS3 runs after role refresh but before charge. C++ runs before role refresh (status set). The ordering between healing and role refresh doesn't interact — they affect different fields.

3. **healthGained != 0 guard**: AS3 checks `card.healthGained != 0` before applying. C++ unconditionally adds `m_type.getHealthGained()`. If `getHealthGained()` returns 0 (default), this is a no-op addition of 0, functionally identical.

### Verdict: MATCH (practical)

The `healthMax > 0` guard difference is defensive code in C++ that prevents an edge case that doesn't exist in the current card set. Both engines heal at the correct time (after construction/delay resolution) and cap at the same value.

**Risk: NONE for current card set.** Theoretical divergence only if a card had `healthGained > 0, healthMax == 0`, which would be a nonsensical card definition.

---

## C3: Charge System

### AS3 Charge Model

Three separate properties (Card.as lines 51-55, 141-204):
- `chargeUsed`: consumed per ability use (default 1 if ability uses charges)
- `chargeGained`: restored per swoosh
- `chargeMax`: upper cap on charges

**Swoosh (State.as lines 2726-2737):**
```actionscript
if (card.chargeGained != 0) {
    inst.charge += card.chargeGained;
    if (inst.charge > card.chargeMax) {
        inst.charge = card.chargeMax;
    }
}
```

**Ability use (State.as line 1469):**
```actionscript
inst.charge -= card.chargeUsed;
```

**chargeAfterSwoosh (Inst.as line 246-253):**
```actionscript
if (this.role == C.ROLE_ASSIGNED) {
    return this.charge + this.card.chargeUsed;
}
return this.charge;
```

Default if `chargeGained` not specified: 0 (Card.as line 142).
Default `chargeMax` if not specified: `startingCharge` (Card.as line 204).

### C++ Charge Model

Only two properties:
- `chargeUsed` (via `getChargeUsed()`)
- `startingCharge` (via `getStartingCharge()`)

No `chargeGained` or `chargeMax` exist in C++.

**beginTurn (Card::beginTurn):** No charge restoration logic at all.

**Ability use (Card::useAbility, line 788):**
```cpp
m_currentCharges -= getType().getChargeUsed();
```

**Undo ability (Card::undoUseAbility, line 743):**
```cpp
m_currentCharges += getType().getChargeUsed();
```

### Analysis

The C++ engine does NOT restore charges during beginTurn/swoosh. Charges are only restored via `undoUseAbility()` (which is the search undo mechanism, not a game mechanic).

Checking the card library for any units that actually use `chargeGained`:
- No unit in `cardLibrary.jso` defines `chargeGained`.
- Therefore AS3's `chargeGained` is always 0, and the swoosh charge restoration never fires.

For standard charge-based units (e.g., Centurion with startingCharge=1, chargeUsed=1):
- **AS3**: Starts with 1 charge. Uses ability (charge goes to 0). Next swoosh: `chargeGained == 0`, so no restoration. Unit can never use ability again. This matches design intent.
- **C++**: Starts with 1 charge. Uses ability (charge goes to 0). beginTurn: no charge logic. Unit can never use ability again. **Match.**

The `chargeAfterSwoosh` helper in AS3 (Inst.as line 250) adds `chargeUsed` if ASSIGNED — this is a prediction helper for UI/AI, not a state mutation. It predicts that after swoosh, the unit will regain charges. But since `chargeGained == 0` for all current units, the actual swoosh doesn't restore charges. The helper is slightly misleading but only used for predictive display.

### Verdict: MATCH (practical)

No current unit uses `chargeGained`, so the missing charge restoration in C++ is harmless. If a future unit defined `chargeGained > 0`, C++ would fail to restore charges.

**Risk: NONE for current card set.** Future risk if custom cards use `chargeGained`.

---

## C4: Supply Tracking

### AS3 Supply Model

- `whiteSupply[cardId]` and `blackSupply[cardId]`: total supply per player per card
- `turnBought()[cardId]`: how many of this card have been bought this game by current player
- Remaining = `turnSupply()[cardId] - turnBought()[cardId]`
- Initialized from `rarity`: Legendary=1, Rare=4, Normal=10, Trinket=20 (C.as lines 180-186)

**Buy (State.as line 1629):**
```actionscript
++this.turnBought()[card.cardId];
```

**Supply enforcement**: Done at the Controller level (click validation), not in State.as's `processOrder`. The state trusts the controller to have validated.

### C++ Supply Model

- `CardBuyable` class with `m_maxSupply[2]` and `m_supplyRemaining[2]`
- `supplyRemaining` = max - spent (initialized in constructor, CardBuyable.cpp line 15-16)
- Rarity values: Legendary=1, Rare=4, Normal=10, Trinket=20 (Constants.h line 18) **-- exact match**

**Buy legality check (GameState.cpp line 223):**
```cpp
if (getCardBuyableByID(action.getID()).getSupplyRemaining(player) == 0)
    return false;
```

**Buy execution (CardBuyable::buyCard, line 54-58):**
```cpp
PRISMATA_ASSERT(getSupplyRemaining(player) != 0, "Can't remove from 0 supply");
m_supplyRemaining[player]--;
```

**Sell (CardBuyable::sellCard, line 61-65):**
```cpp
PRISMATA_ASSERT(getSupplyRemaining(player) < getMaxSupply(player), "Can't sell at max");
m_supplyRemaining[player]++;
```

### Per-Player Supply

Both engines track supply per player:
- AS3: `whiteSupply` and `blackSupply` are separate vectors
- C++: `m_maxSupply[2]` and `m_supplyRemaining[2]` indexed by player ID

Both engines initialize each player's supply from the card's rarity. Both decrement on buy, increment on sell.

### State Init from JSON

C++ (GameState.cpp lines 148-172): If `whiteSupplySpent`/`blackSupplySpent` not present, defaults to 0. If `whiteTotalSupply`/`blackTotalSupply` not present, derives from `CardType::getSupply()` (the rarity value). Constructs `CardBuyable` with (type, maxP1, maxP2, spentP1, spentP2).

### Verdict: MATCH

Supply values, enforcement, per-player tracking, buy/sell mutations all match. The only structural difference is AS3 stores "total supply" and "bought count" while C++ stores "max supply" and "remaining count" — mathematically equivalent.

**Risk: NONE.**

---

## C5: Frontline/Melee Mechanics

### Terminology Mapping

| AS3 | C++ | Meaning |
|---|---|---|
| `MOVE_MELEE` | `ASSIGN_FRONTLINE` | Kill a frontline unit during Action phase |
| `undefendable` | `isFrontline()` | Card property: can be killed pre-breach |
| `glassBroken` | Phases::Breach | Whether wipeout has occurred |
| `MOVE_WIPEOUT` | `blockWithAllBlockers` + beginPhase(Breach) | Transition to breach |

### AS3 Frontline/Melee (State.as lines 1669-1693, Controller.as lines 1639-1695)

**Legality (Controller.as tryToMelee, line 1644):**
- Card must have `card.undefendable == true` (checked at Controller.as line 417)
- `state.turnMana.attack >= inst.health` (enough attack to kill)
- Phase must be ACTION (implicit from Controller flow)
- `!card.fragile` enforced by assert (State.as line 1673)

**Execution (State.as MOVE_MELEE, lines 1669-1693):**
```actionscript
damage = inst.health;
this.turnMana.attack -= damage;
inst.damage += damage;
inst.deadness = C.DEADNESS_MELEED;
```

The full health of the unit is consumed as damage. Attack is reduced by the unit's health. The unit is marked as meleed (dead but can be un-meleed).

**Wipeout interaction**: After melee, `glassBroken` may become true via `MOVE_WIPEOUT` if remaining attack >= remaining defense. Melee targets can be undone (`MOVE_UNMELEE`). If `glassBroken` is already true, melee shows as "breached" instead of "meleed" (visual only, line 1680-1693).

### C++ Frontline (GameState.cpp, Card.cpp)

**Legality (GameState.cpp ASSIGN_FRONTLINE, lines 456-471):**
```cpp
if (getActivePhase() != Phases::Action) return false;
if (player == target.getPlayer()) return false;  // must be enemy
return target.canFrontlineFor(getAttack(action.getPlayer()));
```

**canFrontlineFor (Card.cpp lines 650-668):**
```cpp
if (!getType().isFrontline()) return false;
if (isUnderConstruction()) return false;
if (!getType().isFragile() && (damage < currentHealth())) return false;
return true;
```

For non-fragile units: requires `damage >= currentHealth()` (enough attack to kill).
For fragile units: skips the damage check (always killable if frontline).

**Execution (GameState.cpp ASSIGN_FRONTLINE, line 665):**
```cpp
blockWithCard(_getCardByID(action.getID()));
```

This calls the same `blockWithCard` used for regular blocking:
```cpp
HealthType takeDamage = std::min(currentDamage, currentHealth);
card.takeDamage(takeDamage, DamageSource::Block);
if (card.isDead()) killCardByID(card.getID(), CauseOfDeath::Blocker);
_getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
```

**Wipeout transition (GameState.cpp endPhase Action, lines 1350-1361):**
After action phase ends, if `ourAttack > 0 && canWipeout(player)`, it auto-blocks all enemy blockers and transitions to Breach.

### Differences

1. **Fragile frontline**: C++ allows fragile frontline cards (the isFragile check skips the damage threshold). AS3 asserts `!card.fragile` on melee. No current unit is both `undefendable` and `fragile`, so this is academic.

2. **Under-construction check**: C++ checks `isUnderConstruction()` in `canFrontlineFor`. AS3 does not explicitly check this — but units under construction wouldn't be clickable targets in the AS3 UI controller flow anyway (they have no valid interaction).

3. **Damage source**: C++ uses `DamageSource::Block` (same as regular blocking). AS3 sets `deadness = DEADNESS_MELEED`. This is a metadata difference — the kill effect is the same.

4. **Partial damage**: C++ uses `std::min(currentDamage, currentHealth)` via `blockWithCard`. If attack somehow exceeded health, only health is consumed. AS3 uses `damage = inst.health` directly, consuming exactly the unit's health. Since the legality check requires `attack >= health`, the result is the same: exactly `health` points of attack consumed.

5. **Attack deduction**: Both engines deduct the unit's health from the attacker's attack resource. Same result.

### Wipeout Interaction

**AS3**: Melee reduces attack. After melees, if `turnMana.attack >= helper.oppDefense`, `MOVE_WIPEOUT` auto-blocks all enemy defenders and sets `glassBroken = true`. Then breach targets can be selected.

**C++**: Frontline kills reduce attack. At end of Action phase, if `canWipeout(player)` (attack >= total available defense), auto-blocks all and transitions to Breach phase.

The key difference is timing: AS3 allows melee during action phase with explicit wipeout as a separate action. C++ allows ASSIGN_FRONTLINE during action phase, with wipeout occurring at phase transition. The functional result is the same: frontline kills happen first, then remaining attack is compared against remaining defense.

### Verdict: MATCH (practical)

Frontline kill mechanics are functionally equivalent. The fragile-frontline edge case doesn't exist in the current card set. Damage consumption, attack deduction, and wipeout transition all produce the same game state.

**Risk: LOW.** The fragile+frontline theoretical edge case is the only divergence, and it affects no existing units.

---

## Summary

| Area | Verdict | Risk | Notes |
|---|---|---|---|
| C1: Construction/Delay | MATCH | NONE | Mutually exclusive at creation; both engines gate refresh behind "done" |
| C2: Health/Healing Cap | MATCH | NONE | `healthMax > 0` guard in C++ is extra safety; same behavior for all real units |
| C3: Charge System | MATCH | NONE | No unit uses `chargeGained`; C++ omission of charge restoration is invisible |
| C4: Supply Tracking | MATCH | NONE | Same rarity values, per-player tracking, buy/sell mutations |
| C5: Frontline/Melee | MATCH | LOW | Fragile+frontline combo doesn't exist; all other mechanics equivalent |

**Overall assessment**: All five areas are functionally equivalent for the current card set. No code changes needed. The only theoretical risk is C3 (missing `chargeGained` support in C++) and C5 (fragile frontline behavior), but neither affects any existing unit.
