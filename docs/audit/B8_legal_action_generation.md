# B8: Legal Action Generation Comparison

**Auditor:** Claude Opus 4.6
**Date:** 2026-02-22
**Scope:** Compare C++ `GameState::isLegal()` / `generateLegalActions()` against AS3 `Controller.processClick()` / `canAssign()` / `canBuy()` / `canSell()` / target validation
**Status:** COMPLETE

---

## 1. Legal Action Type Inventory

### C++ Action Types (from `source/engine/Action.h`)

| ActionType ID | C++ Name             | Description                                  |
|---------------|----------------------|----------------------------------------------|
| 0             | USE_ABILITY          | Click own unit to use ability                |
| 1             | BUY                  | Purchase a card from supply                  |
| 2             | END_PHASE            | End current phase (space click)              |
| 3             | ASSIGN_BLOCKER       | Assign a unit to block during defense        |
| 4             | ASSIGN_BREACH        | Assign breach damage to enemy unit           |
| 5             | ASSIGN_FRONTLINE     | Kill enemy frontline unit during action      |
| 6             | SNIPE                | Target enemy unit with snipe ability          |
| 7             | CHILL                | Target enemy unit with chill/disrupt ability  |
| 8             | WIPEOUT              | Break through all enemy defense              |
| 9             | UNDO_USE_ABILITY     | Undo a previously used ability               |
| 10            | UNDO_CHILL           | Undo chill on a frozen enemy unit            |
| 11            | UNDO_BREACH          | Undo a breach assignment                     |
| 12            | SELL                 | Sell back a just-bought unit                 |

### AS3 Equivalents (from `Controller.as` and `C.as`)

| AS3 Click/Move           | Maps to C++ Type       | Notes                                        |
|--------------------------|------------------------|----------------------------------------------|
| CLICK_CARD / canBuy()    | BUY                    | Card panel click                             |
| CLICK_INST + ROLE_DEFAULT + canAssign() | USE_ABILITY | Own unit, default role, action phase |
| CLICK_INST + ROLE_ASSIGNED + canUnassign() | UNDO_USE_ABILITY | Own unit, assigned role        |
| CLICK_INST + ROLE_SELLABLE + canSell() | SELL        | Recently purchased, sellable role            |
| CLICK_INST + defense phase + inst.blocking | ASSIGN_BLOCKER | Own unit during defense phase      |
| CLICK_INST + target mode + instSatisfiesConditionWhy() | SNIPE / CHILL | Two-step: source then target |
| CLICK_SPACE + defense + inEndDefense | END_PHASE (Defense) | All attack absorbed            |
| CLICK_SPACE + action + wouldWipeout  | WIPEOUT + END_PHASE   | Wipeout then transition        |
| CLICK_SPACE + action + !glassBroken + !wouldWipeout | END_PHASE (Action) | Normal end turn    |
| CLICK_SPACE + action + glassBroken + inEndBO | END_PHASE (Action) | After breach done        |
| CLICK_SPACE + confirm phase          | END_PHASE (Confirm)   | Commit the turn              |
| tryToBreach()            | ASSIGN_BREACH          | Enemy non-blocking during glass broken       |
| tryToMelee()             | ASSIGN_FRONTLINE       | Enemy undefendable (frontline) unit          |
| tryToOverkill()          | ASSIGN_BREACH (overkill) | Enemy under-construction unit              |
| tryToWipeout()           | WIPEOUT                | All defense breakable                        |

### Architectural Difference: Phase Handling

**C++ separates phases explicitly**: Action, Defense, Breach, Confirm, Swoosh -- each with dedicated `generateLegalActions` handling.

**AS3 collapses Breach into Action**: There is no separate "Breach" phase in AS3. Breach/overkill/melee happen during the Action phase after `glassBroken = true` (wipeout occurred). The glass-breaking mechanic is an in-phase state toggle, not a phase transition.

**C++ separates Confirm**: The C++ Confirm phase is a distinct phase where END_PHASE is always legal. AS3 has a Confirm phase (`PHASE_CONFIRM`) that similarly always allows CLICK_SPACE.

---

## 2. Per-Action Legality Check Comparison

### 2.1 BUY

**C++ (`isLegal`, ActionTypes::BUY, lines 201-229)**
```
1. getActivePhase() == Phases::Action
2. isBuyable(player, CardType(action.getID()))  -- card exists in supply and max supply > 0
3. getResources(player).has(buyCost)             -- can afford resource cost
4. haveSacCost(player, buySac)                   -- have sac-able units
5. getSupplyRemaining(player) > 0                -- supply not exhausted
```

**AS3 (`canBuy`, lines 1558-1596)**
```
1. state.phase != C.PHASE_DEFENSE               -- not defense phase (implicit: PHASE_ACTION)
2. state.phase != C.PHASE_CONFIRM               -- assert, shouldn't reach here
3. turnBought[card.cardId] < turnSupply[card.cardId]  -- supply check
4. turnMana.hasFailedWith(card.buyCost) < 0      -- resource check
5. sacHasFailedWith(card.buySac) == null          -- sac check
```

**C++ `generateLegalActions` additional filter (line 1888)**:
```cpp
if (getCardBuyableByIndex(cb).getType().getName().compare("Blood Barrier") == 0)
    continue;  // "temp: don't buy forcefields since they 'ruin' the game"
```

| Check             | C++                          | AS3                          | Verdict     |
|-------------------|------------------------------|------------------------------|-------------|
| Phase gate        | `== Phases::Action`          | `!= PHASE_DEFENSE`          | MATCH (*)   |
| Supply remaining  | `getSupplyRemaining() > 0`   | `turnBought < turnSupply`    | MATCH       |
| Resource cost     | `Resources.has(buyCost)`     | `turnMana.hasFailedWith()`   | MATCH       |
| Sac cost          | `haveSacCost()`              | `sacHasFailedWith()`         | MATCH       |
| Buyable           | `isBuyable()` (maxSupply>0)  | No equivalent (implicit)     | MATCH (**)  |
| Forcefield filter | Yes (Blood Barrier excluded) | No                           | **MISMATCH** |

(*) The C++ strictly requires `Phases::Action`. AS3 checks `!= PHASE_DEFENSE` (and asserts not PHASE_CONFIRM). In practice both only allow buying during the action phase.

(**) C++ checks `isBuyable()` which verifies the card type exists in the supply AND `maxSupply > 0`. AS3 handles this implicitly through the card panel -- only buyable cards appear.

**FINDING B8-BUY-1: Forcefield (Blood Barrier) suppression in `generateLegalActions`**
The C++ legal action generator explicitly skips Blood Barrier (Forcefield) purchases. This is a hardcoded AI-only restriction -- the `isLegal()` function DOES consider Forcefield purchases legal, but `generateLegalActions()` removes them from the candidate list. This means:
- The AI will never consider buying Forcefields
- This is intentional (marked "temp" in comment but never removed)
- **Does not affect correctness** of `isLegal()` itself

**Verdict: MATCH** (core legality logic matches; Forcefield filter is a generator-level AI policy, not a legality bug)

---

### 2.2 USE_ABILITY

**C++ (`isLegal`, ActionTypes::USE_ABILITY, lines 292-331)**
```
1. getActivePhase() == Phases::Action
2. !isTargetAbilityCardClicked()      -- no pending target ability
3. !card.isDead()
4. card.hasAbility() || card.hasTargetAbility()
5. card.canUseAbility():
   a. !isDead()
   b. getStatus() == CardStatus::Default
   c. !isUnderConstruction()
   d. charges >= chargeUsed (if uses charges)
   e. m_currentDelay == 0
   f. m_currentHealth >= healthUsed
6. canRunScript(player, abilityScript):
   a. Resources.has(manaCost)
   b. haveSacCost(sacCost)
   c. haveDestroyCards(destroyDescriptions)
```

**AS3 (`canAssign`, lines 1422-1473)**
```
1. inst.role == C.ROLE_DEFAULT          -- matches C++ status == Default
2. inst.health >= inst.card.healthUsed  -- health check
3. inst.charge >= inst.card.chargeUsed  -- charge check
4. turnMana.hasFailedWith(abilityCost)  -- resource check
5. sacHasFailedWith(abilitySac)         -- sac check
6. abilityNetherfy check               -- netherfy target exists
7. targetHas + instsSatisfyingCondition -- valid targets exist (target abilities)
8. Valkyrion + haveOverkilled check     -- edge case: no Valkyrion after overkill
```

Controller.as `processClick` additionally checks (lines 375, 629-631):
```
- state.phase == C.PHASE_ACTION         -- action phase
- inst.owner == state.turn              -- own unit
- inst.role == C.ROLE_DEFAULT           -- default state
- canAssign(inst)                       -- passes all checks above
```

| Check                    | C++                          | AS3                           | Verdict       |
|--------------------------|------------------------------|-------------------------------|---------------|
| Phase gate               | `Phases::Action`             | `PHASE_ACTION`                | MATCH         |
| Status check             | `== CardStatus::Default`     | `role == ROLE_DEFAULT`        | MATCH         |
| Dead check               | `!isDead()`                  | Implicit (dead units removed) | MATCH         |
| Under construction       | `!isUnderConstruction()`     | Implicit (role is INERT)      | MATCH         |
| Delay check              | `m_currentDelay == 0`        | Implicit (role is INERT)      | MATCH         |
| Health cost              | `health >= healthUsed`       | `health >= healthUsed`        | MATCH         |
| Charge cost              | `charges >= chargeUsed`      | `charge >= chargeUsed`        | MATCH         |
| Resource cost            | `canRunScript.manaCost`      | `hasFailedWith(abilityCost)`  | MATCH         |
| Sac cost                 | `canRunScript.sacCost`       | `sacHasFailedWith()`          | MATCH         |
| Destroy cost             | `haveDestroyCards()`         | Not checked in canAssign      | **MISMATCH?** |
| Target ability guard     | `!isTargetAbilityCardClicked`| Controller handles separately | MATCH         |
| Has ability check        | Explicit `hasAbility()`      | Implicit (INERT if no ability)| MATCH         |
| Netherfy check           | Not in `isLegal`             | `abilityNetherfy` check       | **MISMATCH**  |
| Valkyrion edge case      | Not in `isLegal`             | Explicit check                | **MISMATCH**  |

**FINDING B8-ABILITY-1: Missing `haveDestroyCards` check in AS3**
C++ `canRunScript()` checks `haveDestroyCards(player, script.getEffect().getDestroy())` for scripts that destroy specific cards. AS3 `canAssign()` does not have an equivalent check. In practice, very few units have destroy effects in their ability scripts, so this may not manifest in normal gameplay. If it does, the AS3 would allow clicking a unit whose ability would fail due to missing destroy targets -- the server would reject the action.

**FINDING B8-ABILITY-2: Netherfy check missing in C++**
AS3 checks `inst.card.abilityNetherfy && this.state.wouldBeNetherfied() == null` -- preventing use of a netherfy ability when there is no valid netherfy target. C++ `isLegal()` does not check for this. The C++ AI might generate USE_ABILITY for a netherfy unit without a valid target. Since `canRunScript()` only checks resource/sac/destroy costs, the netherfy target availability could be missed.

**FINDING B8-ABILITY-3: Valkyrion + overkill edge case missing in C++**
AS3 explicitly prevents clicking Valkyrion after overkill. C++ has no such check. This is an ultra-rare edge case (Valkyrion creates enemy units, which is problematic mid-overkill). Since C++ doesn't have the overkill state during action phase (it collapses to breach phase), this is architecturally different and the check may not be needed.

**Verdict: PARTIAL MATCH** -- Core checks match. Three edge cases differ (destroy targets, netherfy, Valkyrion+overkill).

---

### 2.3 ASSIGN_BLOCKER

**C++ (`isLegal`, ActionTypes::ASSIGN_BLOCKER, line 454)**
```
return (getAttack(enemy) > 0)
    && (getActivePhase() == Phases::Defense)
    && getCardByID(action.getID()).canBlock();
```

Where `canBlock()` (Card.cpp:484-512) checks:
```
1. getType().canBlock(getStatus() == CardStatus::Assigned)
   -- If Assigned: check assignedBlocking
   -- If Default: check defaultBlocking
2. getCurrentDelay() == 0
3. !isUnderConstruction()
4. !isDead()
5. !isFrozen()  (currentChill() >= currentHealth())
```

**AS3 (Controller.as, defense phase handling, lines 190-267)**
```
1. state.phase == PHASE_DEFENSE
2. inst.owner == state.turn            -- own unit
3. inst.blocking == true               -- THE key check
   If !inst.blocking, error messages based on:
   - !card.defaultBlocking              -- non-blocker unit type
   - disruptDamage >= damageItCanTake + damage  -- disrupted
   - constructionTime > 0               -- under construction
   - else: "busy" (assigned/inert)
4. !inst.dead && !inst.isPartiallyDamaged
5. !state.inEndDefense (oppMana.attack == 0)
```

| Check               | C++                              | AS3                            | Verdict       |
|----------------------|----------------------------------|--------------------------------|---------------|
| Phase gate           | `Phases::Defense`                | `PHASE_DEFENSE`                | MATCH         |
| Enemy attack > 0     | `getAttack(enemy) > 0`          | `!inEndDefense` (attack == 0)  | MATCH         |
| Blocking eligible    | `canBlock()` (type-based + status) | `inst.blocking == true`     | **MISMATCH**  |
| Dead check           | `!isDead()`                      | `!inst.dead`                   | MATCH         |
| Frozen check         | `!isFrozen()` in `canBlock()`    | `disruptDamage >= dmg` → !blocking | MATCH    |
| Under construction   | `!isUnderConstruction()`         | Implicit (blocking = false)    | MATCH         |
| Delay check          | `getCurrentDelay() == 0`         | Implicit (blocking = false)    | MATCH         |

**FINDING B8-BLOCK-1: The `inst.blocking` property vs C++ `canBlock()` -- CRITICAL**

This finding connects directly to the **A1 audit** and the known defense phase blocking bug.

In AS3, `inst.blocking` is a boolean that is set during game state transitions:
- On MOVE_ASSIGN (ability use): `inst.blocking = card.assignedBlocking` (line 1451)
- On MOVE_UNASSIGN (undo ability): `inst.blocking = card.defaultBlocking` (line 1539)
- On beginTurn/swoosh equivalent: `inst.blocking = card.defaultBlocking` (line 2706)

In the **real AS3 game**, a unit that used its ability during the opponent's previous action phase would have `inst.blocking = card.assignedBlocking` at the start of defense. For most units, `assignedBlocking = false` (they can't block after being tapped). The swoosh/beginTurn logic resets this back to `defaultBlocking`.

In C++, the commit `5bf57a8` added a status reset in `beginPhase(Defense)` (lines 1289-1306) that resets cards with abilities to `CardStatus::Default`, which makes `canBlock()` check `defaultBlocking` instead of `assignedBlocking`. This means **tapped units can block when they shouldn't** -- they should retain their Assigned status through defense.

However, looking at the C++ code more carefully:

```cpp
// In beginPhase(Defense), lines 1289-1306:
if (card.getType().hasAbility() || card.getType().hasTargetAbility())
{
    card.setStatus(CardStatus::Default);  // <-- Makes canBlock() use defaultBlocking
}
else
{
    card.setStatus(CardStatus::Inert);
}
```

This reset makes `canBlock()` evaluate against `defaultBlocking` for ALL ability-having cards. For a Drone that was tapped (used ability to produce gold), in the original C++ code the Drone would still be `CardStatus::Assigned`, and `canBlock()` would check `assignedBlocking` which is `false` for Drones. With the reset, it checks `defaultBlocking = true`, allowing the Drone to block.

**In AS3**: The blocking state is tracked via `inst.blocking` property, which is set to `card.assignedBlocking` when the ability is used. It stays that way until beginTurn/swoosh resets it. Defense happens BEFORE swoosh, so tapped units correctly have `blocking = assignedBlocking` during defense.

**This confirms the A1 finding**: The C++ defense reset (5bf57a8) is incorrect. It allows units that used abilities to block during defense, which the AS3/real game does not.

**Verdict: MISMATCH (known bug, see A1 audit)**

---

### 2.4 SNIPE

**C++ (`isLegal`, ActionTypes::SNIPE, lines 256-291)**
```
1. isTargetAbilityCardClicked()     -- source unit must be clicked first
2. !targetCard.isDead()
3. player != targetCard.getPlayer() -- must target enemy
4. targetCard.meetsCondition(card.getTargetAbilityCondition()):
   a. !isUnderConstruction()
   b. condition.hasCardType() check
   c. condition.isNotBlocking() && canBlock() check
   d. condition.isTech() check
   e. condition.hasHealthCondition() check (healthAtMost)
```

**AS3 (`instSatisfiesConditionWhy`, lines 2500-2547, called from target mode)**
```
1. !inst.dead
2. inst.constructionTime == 0      -- not under construction
3. inst.owner != state.turn        -- must be enemy
4. CONDITION_IS_BLOCKING: disruptDamage < health AND inst.blocking
5. CONDITION_CARD: card name match
6. CONDITION_NOT_BLOCKING: !inst.blocking
7. CONDITION_HEALTH_AT_MOST: health <= threshold
8. CONDITION_NAME_IN: name in list
9. CONDITION_IS_ABC: name in "AnimusBlastforgeConduit"
10. CONDITION_IS_ENGINEER_TEMP: name == "Engineer"
```

| Check                  | C++                            | AS3                           | Verdict       |
|------------------------|--------------------------------|-------------------------------|---------------|
| Two-step targeting     | `isTargetAbilityCardClicked()` | `inTargetMode` + redirect     | MATCH         |
| Target alive           | `!targetCard.isDead()`         | `!inst.dead`                  | MATCH         |
| Target is enemy        | `player != target.getPlayer()` | `inst.owner != state.turn`    | MATCH         |
| Not under construction | In `meetsCondition()`          | `constructionTime == 0`       | MATCH         |
| Card type condition    | `condition.hasCardType()`      | `CONDITION_CARD`              | MATCH         |
| Health condition       | `condition.hasHealthCondition()`| `CONDITION_HEALTH_AT_MOST`   | MATCH         |
| Not-blocking condition | `condition.isNotBlocking()`    | `CONDITION_NOT_BLOCKING`      | MATCH         |
| Is-blocking condition  | Not in C++ Condition class     | `CONDITION_IS_BLOCKING`       | **MISMATCH**  |
| isTech condition       | `condition.isTech()`           | Not present                   | **MISMATCH**  |
| NAME_IN condition      | Not in C++ Condition class     | `CONDITION_NAME_IN`           | **MISMATCH**  |
| IS_ABC condition       | Not in C++ Condition class     | `CONDITION_IS_ABC`            | **MISMATCH**  |
| IS_ENGINEER_TEMP       | Not in C++ Condition class     | `CONDITION_IS_ENGINEER_TEMP`  | **MISMATCH**  |

**FINDING B8-SNIPE-1: C++ Condition class is incomplete compared to AS3**
The C++ `Condition` class (Condition.h) only has:
- `_cardName` / `_typeID` (hasCardType)
- `_healthAtMost` (hasHealthCondition)
- `_isTech`
- `_notBlocking`

Missing from C++:
- **`IS_BLOCKING`** -- Used by CHILL/DISRUPT targeting (checks if target is blocking). C++ handles CHILL through `canBeChilled()` which calls `canBlock()` instead.
- **`NAME_IN`** -- List of valid card names. Used by some targeted abilities that can only hit specific units.
- **`IS_ABC`** -- "Animus, Blastforge, or Conduit" condition (used by Grenade Mech).
- **`IS_ENGINEER_TEMP`** -- "Is Engineer" condition (temporary hack in AS3).

For units with `NAME_IN`, `IS_ABC`, or `IS_ENGINEER_TEMP` conditions, the C++ `meetsCondition()` would allow targeting ANY enemy unit that passes the basic checks, when it should be restricted to specific card types.

**Impact**: If the set of playable cards (randomized each game) includes units with these condition types (e.g., Grenade Mech with IS_ABC), the C++ AI would generate snipe targets that include illegal targets. This could cause the AI to attempt invalid moves.

**Verdict: MISMATCH (multiple condition types missing)**

---

### 2.5 CHILL

**C++ (`isLegal`, ActionTypes::CHILL, lines 256-291)**
```
Same as SNIPE except:
- action.getType() == ActionTypes::CHILL
- targetCard.canBeChilled():
  a. canBlock() -- type blocking check + not dead/delayed/frozen/constructing
  b. currentChill() < currentHealth()
  c. !isUnderConstruction()
```

**AS3 (target mode handling, lines 113-184)**
```
Uses instSatisfiesConditionWhy() with CONDITION_IS_BLOCKING:
- !inst.dead
- inst.constructionTime == 0
- inst.owner != state.turn
- disruptDamage < health (not already fully disrupted)
- inst.blocking == true
```

| Check                  | C++                         | AS3                           | Verdict       |
|------------------------|-----------------------------|-------------------------------|---------------|
| Target can block       | `canBlock()` (complex)      | `inst.blocking == true`       | SEE BELOW     |
| Not fully chilled      | `chill < health`            | `disruptDamage < health`      | MATCH         |
| Not under construction | In `canBeChilled()`         | `constructionTime == 0`       | MATCH         |

**FINDING B8-CHILL-1: `canBlock()` vs `inst.blocking` for chill targeting**

C++ `canBeChilled()` delegates to `canBlock()` which checks:
```
CardType::canBlock(status == Assigned)
  -> if Assigned: check assignedBlocking
  -> if Default: check defaultBlocking
```
Plus: delay == 0, not under construction, not dead, not frozen.

AS3 checks `inst.blocking == true` directly. This is a state property that is maintained during game transitions.

These are **semantically equivalent** in normal gameplay: `inst.blocking` is set to `assignedBlocking` or `defaultBlocking` based on the unit's current state, and the AS3 game engine updates it correctly. The C++ `canBlock()` computes the same value based on status and type.

However, the **defense reset bug (A1)** means that during the C++ defense phase, cards that should have `status == Assigned` (and thus `canBlock() -> assignedBlocking = false`) instead have `status == Default` (and thus `canBlock() -> defaultBlocking = true`). This could affect chill targeting if chill can be used during defense, but CHILL requires `isTargetAbilityCardClicked()` and the `isLegal()` for USE_ABILITY (which sets the target ability flag) requires `Phases::Action`. So chill targeting only happens during action phase, where the defense reset bug does not apply.

**Verdict: MATCH (for action phase targeting; defense bug is irrelevant to chill)**

---

### 2.6 END_PHASE

**C++ (`isLegal`, ActionTypes::END_PHASE, lines 332-378)**

| Phase    | C++ Condition                                        |
|----------|------------------------------------------------------|
| Defense  | `getAttack(enemy) == 0` (all damage absorbed)        |
| Swoosh   | `false` (never legal -- auto-transition)              |
| Action   | `true` (always legal)                                 |
| Breach   | Complex: no enemy cards, OR no attack, OR no breachable/overkillable cards |
| Confirm  | `true` (always legal)                                 |

**AS3 (CLICK_SPACE handling, lines 1011-1197)**

| Phase    | AS3 Condition                                                        |
|----------|----------------------------------------------------------------------|
| Defense  | `state.inEndDefense` = `oppMana.attack == 0`                         |
| Action   | If `wouldWipeout`: wipeout first (implicit END via ENTER_CONFIRM)     |
|          | If `glassBroken && !inEndBO`: can't end (must breach/overkill)        |
|          | Otherwise: legal, issues MOVE_ENTER_CONFIRM                          |
| Confirm  | Always legal, issues MOVE_COMMIT                                      |

| Phase    | C++                           | AS3                           | Verdict       |
|----------|-------------------------------|-------------------------------|---------------|
| Defense  | `attack == 0`                 | `oppMana.attack == 0`         | MATCH         |
| Action   | `true` (always legal)         | Complex: wipeout/breach gates  | **MISMATCH**  |
| Breach   | Complex logic                 | No separate phase              | N/A (arch.)   |
| Confirm  | `true`                        | `true`                         | MATCH         |

**FINDING B8-ENDPHASE-1: Action phase END_PHASE is unconditionally legal in C++**

In C++, `isLegal(END_PHASE)` during Action phase returns `true` unconditionally. The player can always end their action phase, even if they have attack that could wipeout the enemy.

In AS3, the action phase CLICK_SPACE has two gatekeepers:
1. If `wouldWipeout` is true (enough attack to break through all defense), clicking space does a WIPEOUT rather than ending the turn
2. If `glassBroken && !inEndBO` (glass is broken but breach damage remains), CLICK_SPACE is **rejected** -- you MUST deal your breach damage

This means:
- **C++ allows ending action with unspent attack** -- the AI can choose to not wipeout
- **AS3 forces wipeout** -- if you have enough attack, space click triggers wipeout first
- **AS3 forces breach completion** -- after glass breaks, you must deal all possible breach damage

The C++ engine handles wipeout/breach through its phase transition in `endPhase()` (line 1350-1364): when action phase ends, if `canWipeout()`, it auto-blocks with all blockers and transitions to Breach phase. So the C++ handles mandatory breach AFTER the player ends the action phase, while AS3 handles it DURING the action phase (by preventing end).

**Impact on AI**: The C++ AI always has END_PHASE available during action, so `generateLegalActions()` always includes it. The AI's search will naturally discover that ending action with enough attack leads to breach, so this architectural difference doesn't create incorrect moves -- just different UI flow.

**Verdict: ARCHITECTURAL MISMATCH (equivalent outcomes, different flow)**

---

### 2.7 ASSIGN_BREACH

**C++ (`isLegal`, ActionTypes::ASSIGN_BREACH, lines 472-521)**
```
1. target.getPlayer() != getActivePlayer()     -- enemy unit
2. getAttack(player) > 0                        -- have attack
3. getActivePhase() == Phases::Breach
4. Frontline priority: if target is not frontline, no breachable frontline exists
5. If target isOverkillable: canOverkillEnemyCard() AND canOverkillFor(attack)
6. If not overkillable: canBreachFor(attack) AND frozen card check
```

**AS3 (`tryToBreach`, lines 1732-1797)**
```
1. state.canBreach (oppDefense == 0, action phase)
2. turnMana.attack >= inst.damageReqdToInjure
-- No separate breach phase; happens during action after glassBroken
```

**AS3 (`tryToOverkill`, lines 1799-1866)**
```
1. state.canOverkill (oppNonInvTotal == 0, action phase)
2. turnMana.attack >= inst.damageReqdToInjure
```

| Check                  | C++                              | AS3                           | Verdict       |
|------------------------|----------------------------------|-------------------------------|---------------|
| Target is enemy        | `target.getPlayer() != active`   | Implicit (enemy section)      | MATCH         |
| Has attack             | `getAttack() > 0`               | `turnMana.attack >= dmg`      | MATCH         |
| Phase gate             | `Phases::Breach`                 | `PHASE_ACTION + glassBroken`  | ARCH DIFF     |
| Frontline priority     | Explicit check                   | Not checked (UI handles)      | **MISMATCH**  |
| Damage sufficient      | `canBreachFor(attack)`           | `attack >= damageReqdToInjure`| MATCH         |
| Frozen card handling   | `canBreachFrozenCard()` check    | Not present in tryToBreach    | **MISMATCH**  |
| Overkill vs breach     | Separate checks for each         | Separate tryToOverkill()      | MATCH         |

**FINDING B8-BREACH-1: Frontline priority not enforced in AS3 breach**
C++ enforces that frontline units must be breached before non-frontline units (line 491-494). AS3 `tryToBreach()` does not have this check -- the player can click any breachable unit. However, AS3's `tryToMelee()` handles frontline (undefendable) units separately, and the client UI guides users. The server may enforce ordering.

**FINDING B8-BREACH-2: Frozen card breach handling differs**
C++ has an explicit `canBreachFrozenCard()` check (line 514-517) that prevents breaching frozen cards unless certain conditions are met (set to true during `blockWithAllBlockers`). AS3 does not have this check in `tryToBreach()`.

**Verdict: PARTIAL MATCH (architectural differences in phase structure; frontline priority and frozen card handling differ)**

---

### 2.8 ASSIGN_FRONTLINE

**C++ (`isLegal`, ActionTypes::ASSIGN_FRONTLINE, lines 456-471)**
```
1. getActivePhase() == Phases::Action
2. player != target.getPlayer()        -- enemy unit
3. target.canFrontlineFor(getAttack()):
   a. getType().isFrontline()
   b. !isUnderConstruction()
   c. Non-fragile: damage >= currentHealth()
   d. Fragile: always (fragile can take any damage?)
```

**AS3 (`tryToMelee`, lines 1639-1701)**
```
1. inst.card.undefendable == true      -- only for undefendable units
2. turnMana.attack >= inst.health      -- enough attack
-- Triggered when clicking enemy undefendable unit during action phase
```

| Check              | C++                          | AS3                           | Verdict       |
|--------------------|------------------------------|-------------------------------|---------------|
| Phase gate         | `Phases::Action`             | `PHASE_ACTION`                | MATCH         |
| Target is enemy    | `player != target.player`    | Implicit (enemy section)      | MATCH         |
| Unit is frontline  | `isFrontline()`              | `card.undefendable`           | MATCH (*)     |
| Damage sufficient  | `canFrontlineFor(attack)`    | `attack >= inst.health`       | MATCH (**)    |
| Under construction | `!isUnderConstruction()`     | Not checked                   | **MISMATCH**  |

(*) C++ `isFrontline()` and AS3 `undefendable` represent the same property from different angles. "Frontline" units cannot hide behind defense -- they must be killed first if attack is sufficient.

(**) C++ `canFrontlineFor()` has a fragile check: non-fragile needs `damage >= health`, fragile needs only to exist (damage > 0 implicit from `getAttack > 0`). AS3 checks `attack >= inst.health` for all units without a fragile distinction. For non-fragile units this matches. For fragile frontline units, AS3 would require `attack >= health` which might be stricter than necessary.

**FINDING B8-FRONTLINE-1: Under-construction check missing in AS3**
C++ prevents frontline-killing units that are under construction. AS3 `tryToMelee` does not check `constructionTime > 0`. However, units under construction in AS3 would be in a different code path (line 381: `inst.constructionTime > 0` goes to `tryToOverkill` instead), so this is effectively handled architecturally.

**Verdict: MATCH (with minor fragile edge case)**

---

### 2.9 WIPEOUT

**C++ (`isLegal`, ActionTypes::WIPEOUT, lines 379-392)**
```
1. getCardByID(action.getID()).canBlock()  -- card can block
2. canWipeout(player):
   a. getAttack(player) > 0
   b. getActivePlayer() == player
   c. getActivePhase() == Phases::Action
   d. numCards(enemy) > 0
   e. attack >= totalAvailableDefense(enemy)
```

**AS3 (`tryToWipeout`, lines 1703-1730)**
```
1. state.wouldWipeout:
   a. phase == PHASE_ACTION
   b. !glassBroken
   c. turnMana.attack >= helper.oppDefense
   d. turnMana.attack > 0
   e. helper.oppAllUnitsTotal > 0
```

| Check               | C++                           | AS3                           | Verdict       |
|---------------------|-------------------------------|-------------------------------|---------------|
| Phase gate          | `Phases::Action`              | `PHASE_ACTION`                | MATCH         |
| Has attack          | `getAttack() > 0`            | `turnMana.attack > 0`         | MATCH         |
| Enough attack       | `>= totalAvailableDefense`    | `>= oppDefense`               | MATCH         |
| Enemy has units     | `numCards(enemy) > 0`         | `oppAllUnitsTotal > 0`        | MATCH         |
| Not already broken  | Not checked                   | `!glassBroken`                | **MISMATCH**  |
| Card can block      | `canBlock()` on specific card | Not applicable                | **MISMATCH**  |

**FINDING B8-WIPEOUT-1: C++ WIPEOUT takes a card ID parameter**
In C++, WIPEOUT is issued with a specific card ID and checks `canBlock()` on that card. In AS3, wipeout is a global action that kills all defenders at once (no specific card). The C++ design seems to model wipeout as "clicking on a blocking unit triggers wipeout" which is how the AS3 UI works (clicking a blocking enemy during action with sufficient attack triggers wipeout). But in `generateLegalActions()`, the C++ iterates enemy cards and includes WIPEOUT for each one that `canBlock()` -- this means multiple WIPEOUT actions could be generated, all of which do the same thing.

**FINDING B8-WIPEOUT-2: AS3 checks `!glassBroken`**
AS3 prevents wipeout if glass is already broken (breach already happened). C++ does not check for this because C++ uses an explicit breach phase -- wipeout would only occur before breach. This is an architectural difference, not a bug.

**Verdict: MATCH (architectural differences, equivalent semantics)**

---

### 2.10 SELL

**C++ (`isLegal`, ActionTypes::SELL, lines 230-255)**
```
1. getActivePhase() == Phases::Action
2. card.isSellable()                  -- m_sellable flag
3. card.getPlayer() == player          -- own card
4. canRunScriptUndo(buyScript):
   a. Resources.has(script.receive)    -- have produced resources to refund
   b. All created cards still alive
```

**AS3 (`canSell`, lines 1598-1637)**
```
1. inst.role == ROLE_SELLABLE          -- in sellable state
   (Note: canSell is only called when role == ROLE_SELLABLE, line 796)
2. buyScript resource undo check       -- hasFailedWith(buyScript.receive)
3. Created units alive check           -- buyCreateIds units not dead/damaged
```

| Check              | C++                          | AS3                           | Verdict       |
|--------------------|------------------------------|-------------------------------|---------------|
| Phase gate         | `Phases::Action`             | Implicit (action phase)       | MATCH         |
| Is sellable        | `card.isSellable()`          | `role == ROLE_SELLABLE`       | MATCH         |
| Own card           | `card.player == player`      | Implicit (own unit section)   | MATCH         |
| Resource undo      | `canRunScriptUndo()`         | `hasFailedWith(receive)`      | MATCH         |
| Created alive      | Created cards check          | `buyCreateIds` check          | MATCH         |

**Verdict: MATCH**

---

### 2.11 UNDO_USE_ABILITY

**C++ (`isLegal`, ActionTypes::UNDO_USE_ABILITY, lines 393-435)**
```
1. getActivePhase() == Phases::Action
2. If isTargetAbilityCardClicked() and ID matches: true (cancel pending target)
3. card.isDead(): only if still inPlay and selfKilled
4. card.getStatus() == CardStatus::Assigned
5. Not snipe target ability (undo snipe not implemented)
6. card has ability
7. canRunScriptUndo(abilityScript)
```

**AS3 (`canUnassign`, lines 1475-1556)**
```
1. abilityScript resource undo check
2. Created units alive check (abilityCreateIds)
3. Disrupt target: check that undoing wouldn't invalidate breach state
4. Snipe target: check that undoing wouldn't invalidate wipeout/overkill state
```

| Check                  | C++                          | AS3                           | Verdict       |
|------------------------|------------------------------|-------------------------------|---------------|
| Phase gate             | `Phases::Action`             | Implicit                      | MATCH         |
| Status == Assigned     | Explicit check               | Role must be ASSIGNED         | MATCH         |
| Snipe undo blocked     | `return false` for snipe     | Conditional (no blanket block)| **MISMATCH**  |
| Resource undo          | `canRunScriptUndo()`         | `hasFailedWith(receive)`      | MATCH         |
| Created alive          | In `canRunScriptUndo()`      | `abilityCreateIds` check      | MATCH         |
| Breach state integrity | Not checked                  | Explicit checks               | **MISMATCH**  |

**FINDING B8-UNDO-1: C++ blanket blocks snipe undo**
C++ `isLegal()` line 419-422: "undo snipe is not implemented yet" -- returns false for any unit with a snipe target ability. AS3 allows unsnipe in some cases but prevents it when it would invalidate breach/overkill state.

**FINDING B8-UNDO-2: Breach state integrity not checked in C++ undo**
AS3 `canUnassign()` has complex checks for disrupt and snipe target undo -- if undoing a chill would un-freeze a unit that was subsequently breached, or if undoing a snipe would invalidate a breach, the undo is blocked. C++ does not have these integrity checks. Since C++ handles breach in a separate phase (after action ends), and undo happens during action, the C++ approach may be safe -- but if an undo action is performed after breach damage has been dealt (not possible in C++ architecture), it could cause inconsistency.

**Verdict: PARTIAL MATCH (snipe undo and breach integrity differ)**

---

## 3. Generator-Level Analysis: `generateLegalActions()`

The C++ `generateLegalActions()` (lines 1858-1981) iterates through all possible actions per phase:

### Defense Phase
```
For each own card: if isLegal(ASSIGN_BLOCKER) -> add
If empty: add END_PHASE
```
**Correct**: All blocking candidates plus mandatory end-phase.

### Action Phase
```
1. For each buyable card (skip Blood Barrier): if isLegal(BUY) -> add
2. For each own card:
   a. If hasTargetAbility: for each enemy card, if isLegal(SNIPE/CHILL) -> add
   b. Else if hasAbility: if isLegal(USE_ABILITY) -> add
3. For each enemy card: if isLegal(ASSIGN_FRONTLINE) -> add
If empty: add END_PHASE
```

**FINDING B8-GEN-1: Target abilities are pre-composed**
The generator creates combined source+target actions for target abilities, bypassing the two-step click mechanism. This is an optimization that produces correct moves but differs from the AS3 click-by-click model.

**FINDING B8-GEN-2: WIPEOUT not generated in action phase**
The `generateLegalActions()` does NOT generate WIPEOUT actions during action phase. Instead, wipeout happens automatically during `endPhase()` when the player ends action with enough attack. The generator includes END_PHASE which triggers the wipeout cascade. This means the AI never "decides" to wipeout -- it just ends the action phase and wipeout happens if applicable.

**FINDING B8-GEN-3: SELL and UNDO actions not generated**
The generator does not include SELL, UNDO_USE_ABILITY, UNDO_CHILL, or UNDO_BREACH actions. These are available via `isLegal()` but the AI search never explores them. The AI always makes forward progress, never undoing moves.

### Breach Phase
```
For each enemy card: if isLegal(ASSIGN_BREACH) -> add
If empty and !isLegal(END_PHASE): add UNDO_CHILL options
If empty: add END_PHASE
```
**FINDING B8-GEN-4: UNDO_CHILL as escape from frozen breach deadlock**
If all remaining enemy cards are frozen and can't be breached, the generator offers UNDO_CHILL to un-freeze them. This is a correct handling of the freeze deadlock scenario.

---

## 4. Test Scenarios

### Scenario 1: Early Game Action Phase (Turn 3, Player 1)
**State**: Player has 6 Drones, 2 Engineers, resources: 9 Gold. Enemy has similar.

| Action          | C++ Legal? | AS3 Legal? | Notes                              |
|-----------------|------------|------------|------------------------------------|
| BUY Drone       | Yes        | Yes        | 3G, supply available               |
| BUY Engineer    | Yes        | Yes        | 2G, supply available               |
| BUY Blastforge  | Yes        | Yes        | 4BB, wait -- no blue resource. No  |
| USE_ABILITY Drone| Yes       | Yes        | Tap for gold (if not already tapped)|
| END_PHASE       | Yes        | Yes        | Can always end action              |
| ASSIGN_BLOCKER  | No         | No         | Not defense phase                  |

**Result: MATCH** for all actions in this scenario.

### Scenario 2: Defense Phase with Tapped Drones
**State**: Player has 6 Drones (3 tapped from previous action, 3 untapped), 2 Engineers. Enemy attack = 4.

| Action               | C++ Legal?      | AS3 Legal? | Notes                                        |
|----------------------|-----------------|------------|----------------------------------------------|
| BLOCK Engineer       | Yes             | Yes        | Engineers always block (defaultBlocking=true)  |
| BLOCK untapped Drone | Yes             | Yes        | Default Drone can block                       |
| BLOCK tapped Drone   | **Yes (BUG)**   | **No**     | C++ resets to Default, AS3 keeps assigned     |
| END_PHASE            | No (attack > 0) | No         | Must absorb all damage                        |

**Result: MISMATCH** -- Tapped Drones are illegally allowed to block in C++ (known A1 bug).

### Scenario 3: Breach Phase with Mixed Enemy Units
**State**: Player has 8 attack remaining. Enemy has: 1 Tarsier (1 HP, frontline), 1 Steelsplitter (4 HP), 1 Wall (3 HP, under construction/overkillable).

| Action                  | C++ Legal? | AS3 Legal? | Notes                                     |
|-------------------------|------------|------------|-------------------------------------------|
| BREACH Tarsier          | Yes        | N/A (*)    | Frontline, 1 HP <= 8 attack               |
| BREACH Steelsplitter    | No         | N/A        | Must kill frontline Tarsier first          |
| BREACH Wall (overkill)  | No         | N/A        | Must kill frontline first; also must check overkill separately |
| END_PHASE               | No         | N/A        | Has attack and breachable targets          |

(*) AS3 does not have a separate breach phase. In AS3 after wipeout, `tryToBreach()` checks `canBreach && attack >= damageReqdToInjure`. The frontline priority is NOT enforced in AS3's `tryToBreach()`.

**Result: C++ correctly enforces frontline priority; AS3 does not enforce it in code (may rely on server validation)**

---

## 5. Summary of Findings

### Critical

| ID | Finding | Impact |
|----|---------|--------|
| B8-BLOCK-1 | Defense phase blocking: C++ resets card statuses, allowing tapped units to block | **HIGH** -- All 722K self-play games affected. Known bug (A1 audit, commit 5bf57a8) |

### Moderate

| ID | Finding | Impact |
|----|---------|--------|
| B8-SNIPE-1 | C++ Condition class missing IS_BLOCKING, NAME_IN, IS_ABC, IS_ENGINEER_TEMP conditions | **MODERATE** -- Affects units with these condition types (Grenade Mech, etc.). Could generate illegal snipe targets. |
| B8-ABILITY-2 | Netherfy ability check missing in C++ isLegal | **LOW-MODERATE** -- Could allow AI to click netherfy units with no valid target. |
| B8-BREACH-1 | Frontline priority not enforced in AS3 breach | **LOW** -- AS3 relies on server validation. C++ is stricter. |
| B8-UNDO-1 | C++ blanket blocks snipe undo; AS3 is more nuanced | **LOW** -- AI doesn't use undo actions anyway (not in generator). |

### Low / Architectural

| ID | Finding | Impact |
|----|---------|--------|
| B8-BUY-1 | Forcefield excluded from generateLegalActions | **NONE** -- Intentional AI policy |
| B8-ENDPHASE-1 | C++ always allows END_PHASE in action; AS3 gates behind wipeout/breach | **NONE** -- Different flow, same outcome |
| B8-ABILITY-1 | Missing haveDestroyCards in AS3 canAssign | **LOW** -- Few units have destroy effects |
| B8-ABILITY-3 | Valkyrion+overkill edge case missing in C++ | **LOW** -- Architectural difference makes it irrelevant |
| B8-GEN-2 | WIPEOUT not explicitly generated; auto-triggered on END_PHASE | **NONE** -- Correct behavior |
| B8-GEN-3 | SELL and UNDO actions not in generator | **NONE** -- By design, AI doesn't explore undo |
| B8-WIPEOUT-1 | C++ WIPEOUT takes card ID; AS3 is global | **NONE** -- Functionally equivalent |

---

## 6. Per-Action Verdict Table

| Action Type        | Verdict              | Notes                                           |
|--------------------|----------------------|-------------------------------------------------|
| BUY                | **MATCH**            | Core logic identical; Forcefield filter is AI policy |
| USE_ABILITY        | **PARTIAL MATCH**    | Core checks match; netherfy/Valkyrion edge cases differ |
| END_PHASE          | **ARCH. MATCH**      | Same outcomes, different flow (C++ auto-transitions) |
| ASSIGN_BLOCKER     | **MISMATCH (BUG)**   | A1 defense reset bug makes tapped units blockable |
| ASSIGN_BREACH      | **PARTIAL MATCH**    | Architectural phase difference; frontline priority differs |
| ASSIGN_FRONTLINE   | **MATCH**            | Minor fragile edge case                         |
| SNIPE              | **MISMATCH**         | Missing condition types in C++ Condition class   |
| CHILL              | **MATCH**            | canBlock() vs inst.blocking equivalent during action |
| WIPEOUT            | **MATCH**            | Architectural differences, equivalent semantics  |
| SELL               | **MATCH**            | Identical checks                                |
| UNDO_USE_ABILITY   | **PARTIAL MATCH**    | Snipe undo blanket-blocked; breach integrity unchecked |
| UNDO_CHILL         | **MATCH**            | Same check: currentChill > 0                    |
| UNDO_BREACH        | **MATCH**            | Same check: wasBreached flag                    |

---

## 7. Recommendations

1. **Fix the A1 defense reset bug** (commit 5bf57a8, lines 1289-1306) -- Remove the status reset block. This is the highest-impact finding, affecting blocking legality.

2. **Extend C++ Condition class** to support `IS_BLOCKING`, `NAME_IN`, `IS_ABC`, and `IS_ENGINEER_TEMP` conditions. Without these, units like Grenade Mech would have incorrect targeting in AI search. Parse these from `cardLibrary.jso` condition fields.

3. **Add netherfy target check** to C++ `isLegal(USE_ABILITY)` -- verify that a valid netherfy target exists before allowing the ability.

4. The remaining differences (Forcefield filter, UNDO handling, architectural phase differences) are either intentional design decisions or have zero practical impact on the AI.

---

*Audit complete. Files examined:*
- `c:/libraries/PrismataAI/source/engine/GameState.cpp` (isLegal: lines 189-545, generateLegalActions: lines 1858-1981, beginPhase: lines 1278-1326, endPhase: lines 1328-1380, canWipeout: lines 1477-1487)
- `c:/libraries/PrismataAI/source/engine/Action.h` (ActionTypes enum)
- `c:/libraries/PrismataAI/source/engine/Constants.h` (Phases enum)
- `c:/libraries/PrismataAI/source/engine/Card.cpp` (canBlock: 484-512, canUseAbility: 670-703, canBeChilled: 521-539, canBreachFor: 355-373, canFrontlineFor: 650-668, meetsCondition: 803-831, isBreachable: 345-348, isSellable: 921-924)
- `c:/libraries/PrismataAI/source/engine/CardType.cpp` (canBlock: 337-347)
- `c:/libraries/PrismataAI/source/engine/Condition.h` (Condition class fields)
- `c:/libraries/PrismataAI/prismata_decompiled/scripts/mcds/engine/Controller.as` (processClick: 49-1277, canAssign: 1422-1473, canUnassign: 1475-1556, canBuy: 1558-1596, canSell: 1598-1637, tryToMelee: 1639-1701, tryToWipeout: 1703-1730, tryToBreach: 1732-1797, tryToOverkill: 1799-1866, instSatisfiesConditionWhy: 2500-2547)
- `c:/libraries/PrismataAI/prismata_decompiled/scripts/mcds/engine/State.as` (processMove: 1433+, canBlockAtStartOfPhase: 4136-4143, inEndDefense: 1372-1375, wouldWipeout: 1377-1380, canBreach: 1404-1407, canOverkill: 1409-1416)
- `c:/libraries/PrismataAI/prismata_decompiled/scripts/mcds/engine/C.as` (constants)
