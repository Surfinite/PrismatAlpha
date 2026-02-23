# A3: Wipeout / Breach Transition & Ordering

**Auditor:** Claude Opus 4.6 engine logic audit
**Date:** 2026-02-22
**Status:** COMPLETE
**Verdict:** 3 MATCH, 1 MISMATCH (latent, zero current impact), 1 STRUCTURAL DIVERGENCE

---

## Summary of Findings

| # | Check | Verdict | Severity | Notes |
|---|---|---|---|---|
| 1 | Wipeout threshold | **MATCH** | -- | Both use `attack >= defense` with identical guards |
| 2 | glassBroken vs Phases::Breach | **STRUCTURAL DIVERGENCE** | LOW | Different state machines achieve same outcome; C++ WIPEOUT action has fallthrough bug (unused by AI) |
| 3 | Breach unit ordering | **MATCH** (with caveat) | -- | Both iterate creation-order; C++ adds frontline priority constraint absent from AS3 |
| 4 | Death script timing during breach | **MISMATCH** | LATENT | AS3 runs `deathScript` on breach kill; C++ has zero death script support. No current units use deathScript, so zero gameplay impact today. |
| 5 | Overkill handling | **MATCH** | -- | Semantics equivalent: only when all remaining units are under construction |

---

## 1. Wipeout Threshold

### AS3 (`State.as:1377-1379`)

```actionscript
public function get wouldWipeout() : Boolean
{
   return this.phase == C.PHASE_ACTION
       && !this.glassBroken
       && this.turnMana.attack >= this.helper.oppDefense
       && this.turnMana.attack > 0
       && this.helper.oppAllUnitsTotal > 0;
}
```

**Defense calculation** (`StateHelper.as:434-437`):
```actionscript
if(inst.blocking)
{
   this.oppDefenders.push(inst);
   this.oppDefense += inst.damageItCanTake;
}
```

Where `damageItCanTake` (`Inst.as:222-225`):
```actionscript
public function get damageItCanTake() : int
{
   return this.health - (this.card.fragile ? 0 : this.damage);
}
```

**Condition:** `attack >= oppDefense` AND `attack > 0` AND `oppAllUnitsTotal > 0` AND in Action phase AND glass not already broken.

`oppDefense` sums `damageItCanTake` across all non-under-construction, alive, blocking opponent units.

### C++ (`GameState.cpp:1477-1487`)

```cpp
bool GameState::canWipeout(const PlayerID player) const
{
    if (getAttack(player) == 0)             { return false; }
    if (getActivePlayer() != player)        { return false; }
    if (getActivePhase() != Phases::Action) { return false; }
    if (numCards(getEnemy(player)) == 0)    { return false; }

    HealthType atk = getAttack(player);
    HealthType def = getTotalAvailableDefense(getEnemy(player));
    return (atk >= def);
}
```

**Defense calculation** (`GameState.cpp:1523-1538`):
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

Where `Card::canBlock()` (`Card.cpp:484-512`):
```cpp
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned))
        return false;
    if (getCurrentDelay() > 0)
        return false;
    if (isUnderConstruction())
        return false;
    if (isDead())
        return false;
    if (isFrozen())
        return false;
    return true;
}
```

**Condition:** `attack >= defense` AND `attack > 0` AND in Action phase AND enemy has cards.

`getTotalAvailableDefense` sums `currentHealth()` across cards where `canBlock()` is true. `canBlock()` excludes under-construction, dead, frozen, and delayed cards -- semantically equivalent to the AS3 requirement that `constructionTime == 0` and `blocking == true`.

### Verdict: MATCH

The threshold formula is identical: `attack >= totalDefense`. Both:
- Require `attack > 0`
- Require Action phase
- Require enemy units exist
- Sum health of all blockable (non-frozen, non-under-construction, alive) enemy units

**Subtle difference in defense accounting:** AS3 uses `damageItCanTake = health - (fragile ? 0 : damage)` which accounts for existing damage on non-fragile units. C++ uses `currentHealth()` which is the actual remaining HP. For non-fragile units, `currentHealth` returns the starting health (non-fragile units don't lose HP from damage until death). For fragile units, `currentHealth` reflects HP reduction from damage. Both approaches yield the same number because non-fragile damage reduces `damageItCanTake` but the unit's `currentHealth()` stays at starting health until killed, and the only damage a blocking unit can have taken before wipeout check is from chill (which makes them unable to block, removing them from the sum entirely). Net result is identical.

---

## 2. glassBroken vs Phases::Breach

### AS3 Model

The AS3 uses a boolean flag `glassBroken` within the Action phase:

```actionscript
// State.as:140
public var glassBroken:Boolean;

// Wipeout sets glassBroken=true, stays in PHASE_ACTION
// State.as:1855-1858 (MOVE_WIPEOUT)
this.glassBroken = true;
this.dispatch(update,animate,C.SEND_GLASSBROKEN);
for each(inst in this.helper.oppDefenders) {
    damage = inst.health;
    this.turnMana.attack -= damage;
    inst.damage += damage;
    // ... fragile handling ...
    inst.deadness = C.DEADNESS_WBO;
}

// Breach is MOVE_BREACH_OR_OVERKILL, still in PHASE_ACTION
// State.as:1779-1818 (MOVE_BREACH_OR_OVERKILL)
damage = Math.min(inst.health, this.turnMana.attack);
this.turnMana.attack -= damage;
inst.damage += damage;
if(inst.damageItCanTake == 0) {
    inst.deadness = C.DEADNESS_WBO;
    // Run deathScript if present (see Finding #4)
    if(inst.card.deathScript) {
        this.runScriptForward(..., inst.card.deathScript, ...);
    }
}
```

Key: The AS3 **never leaves PHASE_ACTION** during breach. `glassBroken` is a sub-state flag. The player individually clicks units to breach (MOVE_BREACH_OR_OVERKILL) or melee-targets frontline units (MOVE_MELEE). Everything stays in PHASE_ACTION. After all breaching is done, the player clicks "end turn" which transitions to PHASE_CONFIRM.

### C++ Model

The C++ uses a separate `Phases::Breach` enum value:

```cpp
// endPhase() for Phases::Action (GameState.cpp:1350-1361)
case Phases::Action:
{
    HealthType ourAttack = getAttack(getActivePlayer());
    if ((ourAttack > 0) && canWipeout(player))
    {
        blockWithAllBlockers(enemy);    // Kill all blockers
        beginPhase(player, Phases::Breach);  // Enter Breach phase
        break;
    }
    beginPhase(player, Phases::Confirm);
    break;
}
```

Then in Breach phase, ASSIGN_BREACH actions are generated (`GameState.cpp:1945-1956`):
```cpp
case Phases::Breach:
{
    for (const auto & cardID : getCardIDs(enemy))
    {
        const Action breach(player, ActionTypes::ASSIGN_BREACH, cardID);
        if (isLegal(breach))
            actions.push_back(breach);
    }
    // ...
}
```

Each breach action calls `breachCard()` (`GameState.cpp:1562-1575`):
```cpp
void GameState::breachCard(Card & card)
{
    HealthType currentDamage = (HealthType)getResources(getEnemy(card.getPlayer())).amountOf(Resources::Attack);
    HealthType currentHealth = card.currentHealth();
    HealthType takeDamage = std::min(currentDamage, currentHealth);

    card.takeDamage(takeDamage, DamageSource::Breach);
    if (card.isDead())
        killCardByID(card.getID(), CauseOfDeath::Breached);

    _getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
}
```

### C++ WIPEOUT Action Fallthrough Bug

The C++ `doAction` handler for `ActionTypes::WIPEOUT` has a missing `break` statement causing fallthrough into `ActionTypes::UNDO_CHILL`:

```cpp
// GameState.cpp:704-714
case ActionTypes::WIPEOUT:
{
    endPhase();        // Transitions Action -> Breach
}                      // NO BREAK - falls through!
case ActionTypes::UNDO_CHILL:
{
    if (getActivePhase() == Phases::Breach)   // TRUE (just entered Breach)
    {
        beginPhase(getActivePlayer(), Phases::Action);  // Reverts to Action!
    }
    // ... undo chill logic ...
    break;
}
```

This means calling `doAction(WIPEOUT)` transitions to Breach via `endPhase()` (which calls `blockWithAllBlockers` and `beginPhase(Breach)`), then immediately reverts to Action phase due to the fallthrough.

**Impact:** The AI never uses `ActionTypes::WIPEOUT` -- it uses `ActionTypes::END_PHASE` which correctly transitions through the phase machine. The WIPEOUT action is only used by the click-based GUI path (`getClickAction()` at line 2235). Since the PrismataAI engine primarily runs AI vs AI tournaments, this fallthrough bug has no practical impact on gameplay results. However, it means the WIPEOUT action type is effectively broken and should never be called.

### Verdict: STRUCTURAL DIVERGENCE

The AS3 uses `glassBroken` flag within Action phase; C++ uses a separate Breach phase. Both achieve the same outcome: after wipeout, the attacking player can target individual enemy units. The C++ approach is cleaner (explicit phase) but has the vestigial WIPEOUT fallthrough bug. The difference is architectural, not behavioral, for AI search paths.

---

## 3. Breach Unit Ordering

### AS3

Breach targeting in AS3 is **player-driven with no ordering constraints**. The player clicks individual units via `MOVE_BREACH_OR_OVERKILL` (non-frontline) or `MOVE_MELEE` (frontline/undefendable). The only validation is sufficient attack:

```actionscript
// MOVE_BREACH_OR_OVERKILL (State.as:1779-1818)
if(inst.health > this.turnMana.attack) {
    damage = this.turnMana.attack;
    C.ASSERT(inst.card.fragile, "Tried to partially breach a non-fragile unit.");
} else {
    damage = inst.health;
}
this.turnMana.attack -= damage;
```

No ordering is enforced between frontline and non-frontline units during breach. The AS3 `Controller.as` UI routes frontline clicks through `tryToMelee()` and blocking clicks through the normal breach path, but these are independent UI handlers with no mutual exclusion.

### C++

The C++ enforces **frontline priority** during Breach phase:

```cpp
// ASSIGN_BREACH legality check (GameState.cpp:490-494)
if (!target.getType().isFrontline() && hasBreachableFrontlineCard(getEnemy(action.getPlayer())))
{
    return false;  // Cannot breach non-frontline if frontline exists
}
```

Where `hasBreachableFrontlineCard` (`GameState.cpp:1843-1856`):
```cpp
bool GameState::hasBreachableFrontlineCard(const PlayerID player) const
{
    HealthType atk = getAttack(getEnemy(player));
    for (const auto & cardID : getCardIDs(player))
    {
        const Card & card = getCardByID(cardID);
        if (card.getType().isFrontline() && card.canBreachFor(atk))
            return true;
    }
    return false;
}
```

Within the same priority tier, breach actions are generated in **CardID order** (vector iteration of `m_liveCardIDs`), which corresponds to card creation order.

### Iteration Order During Wipeout

**C++ `blockWithAllBlockers`** (`GameState.cpp:1502-1521`):
```cpp
void GameState::blockWithAllBlockers(const PlayerID player)
{
    CardID c(0);
    while (c < numCards(player))
    {
        Card & card = _getCardByID(getCardIDs(player)[c]);
        if (card.canBlock())
        {
            blockWithCard(card);
            m_canBreachFrozenCard = true;
            c = 0;                // Reset to beginning after each kill
        }
        else
        {
            ++c;
        }
    }
}
```

Note the `c = 0` reset after each block: this restarts iteration from the beginning because `killCardByID` modifies `m_liveCardIDs` (removes the killed card). This ensures all blockers are killed regardless of vector mutation.

**AS3 `MOVE_WIPEOUT`** (`State.as:1859-1873`):
```actionscript
for each(inst in this.helper.oppDefenders)
{
    damage = inst.health;
    this.turnMana.attack -= damage;
    inst.damage += damage;
    inst.deadness = C.DEADNESS_WBO;
}
```

AS3 iterates `oppDefenders` (populated during `helper.update()` from the Dictionary-based `table`). Dictionary iteration order in ActionScript is implementation-defined (typically insertion order for integer keys, but not guaranteed). However, since wipeout kills ALL defenders, ordering doesn't affect the outcome -- all defenders die and their total health is deducted from attack.

### Verdict: MATCH (with caveat)

Wipeout order doesn't matter (all blockers die, same total damage). For post-wipeout breach targeting, both engines let the attacker choose which unit to breach. The C++ adds a frontline-priority constraint (`isFrontline` must be breached before non-frontline) that the AS3 does not enforce. This is a C++ **addition**, not a divergence from AS3 behavior -- the AS3 lets the player choose freely, while the C++ constrains the AI to breach frontline first. Since the AI is the consumer, this is a reasonable heuristic constraint.

---

## 4. Death Script Timing During Breach

### AS3 (`State.as:1798-1808`)

```actionscript
// Inside MOVE_BREACH_OR_OVERKILL handler
if(inst.damageItCanTake == 0) {
    inst.deadness = C.DEADNESS_WBO;
    this.dispatch(update,animate,C.SEND_BREACHED,{
        "inst":inst, "delta":damage
    });
    if(inst.card.deathScript) {
        this.runScriptForward(update, animate,
            inst.card.deathScript, C.SCRIPTTYPE_ABILITY,
            inst, abilityCreateIds);
    }
}
```

The AS3 runs `deathScript` **immediately** when a unit is killed by breach, before the next breach target is selected. The death script runs in the `runScriptForward` framework, which can create units, modify resources, etc.

Death script also executes during undo (`MOVE_UNBREACH_OR_UNOVERKILL`, `State.as:1839-1841`):
```actionscript
if(inst.card.deathScript) {
    this.runScriptBackward(update, animate, inst.card.deathScript, ...);
}
```

### C++ (`GameState.cpp:1562-1575`)

```cpp
void GameState::breachCard(Card & card)
{
    HealthType currentDamage = ...;
    HealthType currentHealth = card.currentHealth();
    HealthType takeDamage = std::min(currentDamage, currentHealth);

    card.takeDamage(takeDamage, DamageSource::Breach);
    if (card.isDead())
        killCardByID(card.getID(), CauseOfDeath::Breached);

    _getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
}
```

**No death script execution.** The `killCardByID` function (`CardData.cpp:151-164`) only calls `card.kill(causeOfDeath)` (sets dead flag + cause) and moves the card from live to killed list. No script is checked or run.

Confirmed via search: the string "deathScript" appears zero times in the entire C++ `source/` directory.

### Current Impact

**Checked `cardLibrary.jso`:** Zero units in the current card library define a `deathScript` property. The AS3 Card class shows it's only loaded when `obj.hasOwnProperty("deathScript")` (`Card.as:320-322`).

### Verdict: MISMATCH (LATENT)

The AS3 supports death scripts triggered on breach; the C++ does not implement the feature at all. Since no current units use death scripts, this has **zero gameplay impact today**. If a custom card set were to include units with `deathScript`, the C++ engine would silently ignore the effect, producing incorrect game states.

---

## 5. Overkill Handling

### AS3

Overkill is available when **all remaining opponent units are under construction** (none are non-invulnerable/deployed):

```actionscript
// State.as:1409-1416
internal function get canOverkill() : Boolean
{
    if(TUTORIAL_CANNOT_OVERKILL_BOT && this.turn == C.COLOR_WHITE)
        return false;
    return this.phase == C.PHASE_ACTION && this.helper.oppNonInvTotal == 0;
}
```

Where `oppNonInvTotal` sums `damageItCanTake` for alive, non-under-construction opponent units (`StateHelper.as:431-433`):
```actionscript
if(inst.constructionTime == 0) {
    this.oppNonInvTotal += inst.damageItCanTake;
}
```

Overkill uses the same `MOVE_BREACH_OR_OVERKILL` handler as breach (`State.as:1779`). The damage logic is identical.

### C++

Overkill in C++ is gated by `hasOverkillableCard` (`GameState.cpp:1779-1791`):
```cpp
bool GameState::hasOverkillableCard(const PlayerID player) const
{
    for (const auto & cardID : getCardIDs(player))
    {
        if (!getCardByID(cardID).isOverkillable())
            return false;  // ALL cards must be overkillable
    }
    return true;
}
```

Where `isOverkillable` (`Card.cpp:350-352`):
```cpp
bool Card::isOverkillable() const
{
    return isUnderConstruction() && !isDead();
}
```

This returns true only for alive, under-construction units. `hasOverkillableCard` returns true only when **all** remaining enemy units are under construction -- equivalent to `oppNonInvTotal == 0` in AS3.

The actual overkill legality check is in `ASSIGN_BREACH` (`GameState.cpp:496-505`):
```cpp
if (target.isOverkillable())
{
    if (!canOverkillEnemyCard(action.getPlayer()))
        return false;
    else
        return target.canOverkillFor(getAttack(getActivePlayer()));
}
```

Where `canOverkillFor` (`Card.cpp:375-393`):
```cpp
bool Card::canOverkillFor(const HealthType damage) const
{
    if (damage == 0)        return false;
    if (!isOverkillable())  return false;
    if (!getType().isFragile() && damage < currentHealth())
        return false;
    return true;
}
```

### End-of-Breach Overkill Cleanup

C++ handles residual attack when breach phase ends (`GameState.cpp:1366-1382`):
```cpp
case Phases::Breach:
{
    if (hasBreachableCard(enemy) && !canBreachEnemyCard(player))
        _getResources(player).set(Resources::Attack, 0);  // Can't kill remaining card
    if (hasOverkillableCard(enemy) && !canOverkillEnemyCard(player))
        _getResources(player).set(Resources::Attack, 0);  // Can't kill remaining UC card
    beginPhase(player, Phases::Confirm);
    break;
}
```

AS3 handles this through `inEndBO` (`State.as:1387-1402`):
```actionscript
public function get inEndBO() : Boolean
{
    if(this.phase == C.PHASE_ACTION && this.glassBroken)
    {
        if(this.canOverkill)
            return this.turnMana.attack < this.helper.damageReqdToInjureOverkill;
        return this.turnMana.attack < this.helper.damageReqdToInjureBreach;
    }
    return false;
}
```

Both discard remaining attack when it's insufficient to kill any remaining target.

### Verdict: MATCH

Overkill semantics are equivalent: only available when all remaining enemy units are under construction, damage must be sufficient to kill (or partially damage fragile). Both engines discard remaining attack when no more targets can be killed.

---

## Test Case Table

### Normal: Attack = Total Defense Exactly

**Scenario:** Player A has 5 attack. Enemy B has Wall (5 HP, blocking) + Tarsier (1 HP, non-blocking).

| Step | AS3 | C++ |
|---|---|---|
| Wipeout check | `attack(5) >= oppDefense(5)` = true | `getAttack(5) >= getTotalAvailableDefense(5)` = true |
| Wipeout | `glassBroken=true`, Wall gets `damage=5, deadness=WBO`, `attack` drops to 0 | `blockWithAllBlockers`: Wall blocked (5 damage, killed), attack drops to 0 |
| Breach available? | `attack(0) < Tarsier.health(1)` = no | No ASSIGN_BREACH legal (attack = 0) |
| End state | Tarsier survives, attack = 0 | Tarsier survives, attack = 0 |

**Result: Identical outcome.**

### Edge: Attack > Total Defense (Breach Damage)

**Scenario:** Player A has 8 attack. Enemy B has Wall (5 HP, blocking) + Drone (1 HP) + Steelsplitter (3 HP).

| Step | AS3 | C++ |
|---|---|---|
| Wipeout check | `attack(8) >= oppDefense(5)` = true | `getAttack(8) >= getTotalAvailableDefense(5)` = true |
| Wipeout | Wall killed (`damage=5, deadness=WBO`), attack drops to 3 | `blockWithAllBlockers`: Wall killed, attack = 3 |
| Breach: Drone | Player clicks Drone: `damage=1, attack` drops to 2 | AI picks ASSIGN_BREACH(Drone): `breachCard` does 1 damage, attack = 2 |
| Breach: Steelsplitter | Player clicks Steelsplitter: `damage=2` (partial, fragile? no), needs 3 to kill, can't kill | AI cannot ASSIGN_BREACH(Steelsplitter): `canBreachFor(2)` returns false (non-fragile, 2 < 3) |
| Remaining attack | Discarded (inEndBO = true) | Discarded (`!canBreachEnemyCard` -> attack set to 0) |
| End state | Drone dead, Steelsplitter alive, attack = 0 | Drone dead, Steelsplitter alive, attack = 0 |

**Result: Identical outcome.** (Order may differ for AI -- but Steelsplitter can't be killed either way.)

### Edge: Frontline Unit Present During Breach

**Scenario:** Player A has 10 attack. Enemy B has Wall (3 HP, blocking) + Rhino (4 HP, frontline) + Drone (1 HP).

| Step | AS3 | C++ |
|---|---|---|
| Wipeout check | `attack(10) >= oppDefense(3)` = true | Same |
| Wipeout | Wall killed, attack = 7 | Wall killed, attack = 7 |
| Breach: Rhino (frontline) | Player can melee Rhino (MOVE_MELEE) or breach Drone first -- no ordering enforced | ASSIGN_BREACH(Drone) is **ILLEGAL** while Rhino (frontline, `canBreachFor(7)=true`) exists. Must breach Rhino first. |
| Breach: Rhino | `damage=4`, attack = 3 | `breachCard(Rhino)`: 4 damage, killed, attack = 3 |
| Breach: Drone | `damage=1`, attack = 2 | `breachCard(Drone)`: 1 damage, killed, attack = 2 |
| End state | Rhino dead, Drone dead, attack = 2 (or 0 after discard) | Rhino dead, Drone dead, attack = 2 (discarded at phase end) |

**C++ forces frontline-first ordering that AS3 does not.** Same final state in this case, but the C++ would reject a Drone-first order that AS3 would accept.

---

## Negative Test: Two Units With Death Triggers, Both Breached

### Scenario Design

Since no current units have `deathScript`, this is a **hypothetical test** to demonstrate the mismatch.

Suppose two custom units:
- **Sentinel A** (2 HP, non-fragile, `deathScript: {receive: {attack: 1}}`): On death, gives owner 1 attack.
- **Sentinel B** (3 HP, non-fragile, `deathScript: {receive: {attack: 2}}`): On death, gives owner 2 attack.

Attacker has 10 attack. Defender has no blockers (both Sentinels are non-blocking).

| Step | AS3 (Expected) | C++ (Actual) |
|---|---|---|
| Breach Sentinel A (2 HP) | A dies, `deathScript` runs: defender gains 1 attack. Attacker: 8 attack. | A dies, no script. Attacker: 8 attack. Defender gains nothing. |
| Breach Sentinel B (3 HP) | B dies, `deathScript` runs: defender gains 2 attack. Attacker: 5 attack. | B dies, no script. Attacker: 5 attack. Defender gains nothing. |
| Post-breach state | Defender has 3 attack from death triggers | Defender has 0 attack from death triggers |

**Death order is irrelevant here** (same units die, same damage), but the **post-breach state differs** because C++ ignores death scripts entirely.

**Current impact: NONE.** No units in `cardLibrary.jso` define `deathScript`. This test documents the latent capability gap.

---

## Detailed Code Path Traces

### Trace 1: Action Phase -> Wipeout -> Breach -> Confirm (C++ AI path)

```
1. AI calls END_PHASE during Action
   -> doAction(END_PHASE) -> endPhase()           [GameState.cpp:633-636]

2. endPhase() for Phases::Action:
   -> getAttack(player) > 0 AND canWipeout(player)
   -> blockWithAllBlockers(enemy)                   [GameState.cpp:1357]
      -> iterates getCardIDs(enemy), kills each canBlock() card
      -> sets m_canBreachFrozenCard = true           [GameState.cpp:1513]
   -> beginPhase(player, Phases::Breach)             [GameState.cpp:1359]

3. AI generates legal actions in Phases::Breach:
   -> iterates getCardIDs(enemy)                     [GameState.cpp:1948]
   -> for each, checks isLegal(ASSIGN_BREACH):
      - must be enemy card                           [GameState.cpp:475-478]
      - attack > 0                                   [GameState.cpp:480-483]
      - must be in Phases::Breach                    [GameState.cpp:485-488]
      - frontline priority enforced                  [GameState.cpp:490-494]
      - if overkillable: check canOverkillEnemyCard  [GameState.cpp:496-505]
      - if breachable: check canBreachFor(attack)    [GameState.cpp:509-512]
      - if frozen: check canBreachFrozenCard()       [GameState.cpp:514-517]

4. AI does ASSIGN_BREACH for chosen card:
   -> breachCard(card)                               [GameState.cpp:649]
      -> takeDamage(min(attack, health))             [Card.cpp:395-428]
      -> if dead: killCardByID(CauseOfDeath::Breached)
      -> reduce attack by damage dealt

5. Repeat step 3-4 until no legal breach actions / END_PHASE is chosen.

6. endPhase() for Phases::Breach:
   -> discard attack if can't kill remaining cards   [GameState.cpp:1369-1377]
   -> beginPhase(player, Phases::Confirm)            [GameState.cpp:1380]

7. endPhase() for Phases::Confirm:
   -> m_turnNumber++                                 [GameState.cpp:1385]
   -> m_cards.removeKilledCards()                    [GameState.cpp:1386]
   -> card.endTurn() for all live cards              [GameState.cpp:1388-1391]
   -> calculateGameOver()                            [GameState.cpp:1394]
   -> transition to enemy Defense or Swoosh          [GameState.cpp:1401-1411]
```

### Trace 2: Action Phase -> Wipeout -> Breach -> Confirm (AS3 client path)

```
1. Player clicks "Wipeout" button (or it auto-fires):
   -> processMove(MOVE_WIPEOUT)                      [State.as:1855]

2. MOVE_WIPEOUT handler:
   -> glassBroken = true                             [State.as:1857]
   -> for each(inst in helper.oppDefenders):
      -> damage = inst.health
      -> turnMana.attack -= damage
      -> inst.damage += damage
      -> inst.deadness = DEADNESS_WBO
   -> helper.update(this)                            [State.as:1874]

3. Player clicks individual units to breach/melee:
   a. Frontline (undefendable) units via MOVE_MELEE:
      -> damage = inst.health
      -> turnMana.attack -= damage
      -> inst.deadness = DEADNESS_MELEED             [State.as:1677]
      -> (visual dispatch depends on glassBroken)    [State.as:1680-1693]

   b. Non-frontline units via MOVE_BREACH_OR_OVERKILL:
      -> damage = min(inst.health, turnMana.attack)
      -> turnMana.attack -= damage
      -> inst.damage += damage
      -> if inst.damageItCanTake == 0:
         -> inst.deadness = DEADNESS_WBO             [State.as:1800]
         -> if(inst.card.deathScript):               [State.as:1805]
            -> runScriptForward(deathScript)          [State.as:1807]
      -> helper.update(this)                         [State.as:1817]

4. End breach (inEndBO detected or player clicks end):
   -> processMove(MOVE_ENTER_CONFIRM)                [State.as:1911]
   -> phase = PHASE_CONFIRM                          [State.as:1953]
   -> manaRots(), collectSpells()                    [State.as:1956-1957]
   -> collectBodies() -- deletes dead units          [State.as:1958]

5. Commit turn:
   -> processMove(MOVE_COMMIT)                       [State.as:1997]
   -> executeTriggers()                              [State.as:2001]
   -> checkWin()                                     [State.as:2004]
   -> if no winner: swoosh() or enter PHASE_DEFENSE  [State.as:2017-2028]
```

---

## Key Differences Summary

| Aspect | AS3 | C++ | Impact |
|---|---|---|---|
| Phase model | `glassBroken` flag within Action | Separate `Phases::Breach` | Architectural only |
| Body removal | `collectBodies()` at Confirm entry | `removeKilledCards()` at Confirm end | Cards stay "in play but killed" during C++ Confirm; AS3 removes them at Confirm start |
| Frontline ordering | No enforcement (player chooses freely) | Frontline must be breached before non-frontline | C++ is stricter |
| Death scripts | Supported, runs immediately on breach kill | Not implemented | Zero impact (no units use it) |
| Frozen card breach | Implicit (no special handling needed since player clicks directly) | `m_canBreachFrozenCard` flag, set true after blockWithAllBlockers or non-frontline breach | C++ explicitly tracks frozen-card-breach eligibility |
| WIPEOUT action | Single move kills all blockers | Calls `endPhase()` but has **fallthrough bug** to UNDO_CHILL (reverts to Action) | AI uses END_PHASE instead; WIPEOUT action is broken but unused |
