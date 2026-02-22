# B2/B3/B4 Audit: Resource Reset, Ability Side Effects, Snipe Mechanics

**Auditor**: Claude Opus 4.6
**Date**: 2026-02-22
**Files examined**:
- `prismata_decompiled/scripts/mcds/engine/State.as` (swoosh, processMove/MOVE_ASSIGN, runScriptForward, manaRots, sac, netherfy)
- `prismata_decompiled/scripts/mcds/engine/Mana.as` (resource pool management)
- `prismata_decompiled/scripts/mcds/engine/C.as` (MANA constants)
- `prismata_decompiled/scripts/mcds/engine/StateHelper.as` (oppDefense computation)
- `source/engine/GameState.cpp` (beginTurn, runScript, doAction for SNIPE/CHILL, getTotalAvailableDefense)
- `source/engine/Card.cpp` (beginTurn, useAbility, kill, applyChill, canBlock)
- `source/engine/Resources.cpp` (pool management)
- `source/engine/Resources.h` (enum: Gold=0, Energy=1, Blue=2, Red=3, Green=4, Attack=5)
- `source/engine/CardType.cpp` (canBlock with assigned flag)

---

## B2: Begin-Turn Resource Reset Order

### B2.1: Resource Types Cleared

**AS3 (State.as swoosh, lines 2582-3072)**:
Resources are NOT explicitly zeroed at swoosh start. Instead, the AS3 client uses a **mana rotation** system at end-of-turn (MOVE_ENTER_CONFIRM, line 1956: `this.manaRots()`). The `manaRots` function (lines 3090-3142) zeros out:
- `turnMana.pool[C.MANA_H]` (Energy, index 4) -> set to 0
- `turnMana.pool[C.MANA_B]` (Blue, index 2) -> set to 0
- `turnMana.pool[C.MANA_R]` (Red, index 3) -> set to 0
- `turnMana.pool[C.MANA_A]` (Attack, index 5) -> set to 0, BUT **only if** `this.helper.oppDefense == 0` (and not controlled lane)

Resources that persist across turns in AS3:
- **Gold** (`MANA_P`, index 0) -- NOT cleared in `manaRots`
- **Green** (`MANA_G`, index 1) -- NOT cleared in `manaRots`
- **Attack** -- conditionally persists if opponent has defense > 0

Then during swoosh, cards produce new resources via `beginOwnTurnScript` / `runScriptForward` which calls `this.turnMana.add(script.receive)` (line 2369).

**C++ (GameState.cpp beginTurn, lines 1215-1276)**:
Resources are explicitly zeroed at the START of beginTurn:
```cpp
_getResources(player).set(Resources::Energy, 0);  // index 1
_getResources(player).set(Resources::Blue, 0);     // index 2
_getResources(player).set(Resources::Red, 0);      // index 3
_getResources(player).set(Resources::Attack, 0);   // index 5
```

Resources that persist in C++:
- **Gold** (index 0) -- NOT in the reset list
- **Green** (index 4) -- NOT in the reset list

**VERDICT: MATCH (with architectural difference)**

Both engines clear {Energy, Blue, Red, Attack} and preserve {Gold, Green}. The resource type mapping is:

| AS3 Constant | AS3 Index | C++ Enum | C++ Index | Cleared? |
|---|---|---|---|---|
| MANA_P (Gold) | 0 | Gold | 0 | NO -- persists |
| MANA_G (Green) | 1 | Green | 4 | NO -- persists |
| MANA_B (Blue) | 2 | Blue | 2 | YES |
| MANA_R (Red) | 3 | Red | 3 | YES |
| MANA_H (Energy) | 4 | Energy | 1 | YES |
| MANA_A (Attack) | 5 | Attack | 5 | YES |

Note: The index ordering differs (AS3: P=0,G=1,B=2,R=3,H=4,A=5 vs C++: Gold=0,Energy=1,Blue=2,Red=3,Green=4,Attack=5) but resource names map correctly. Both clear the same 4 types and preserve the same 2.

### B2.2: Gold Persistence

**AS3**: Gold (`MANA_P`, index 0) is NOT cleared in `manaRots()` (lines 3096-3117 only clear H, B, R, A). Gold persists across turns.

**C++**: Gold (index 0) is NOT in the `beginTurn()` reset list (lines 1220-1223). Gold persists across turns.

**VERDICT: MATCH** -- Gold correctly persists in both engines.

### B2.3: Green Persistence

**AS3**: Green (`MANA_G`, index 1) is NOT cleared in `manaRots()`. Green persists across turns.

**C++**: Green (index 4) is NOT in the `beginTurn()` reset list. Green persists across turns.

**VERDICT: MATCH** -- Green correctly persists in both engines.

### B2.4: Attack Persistence (Conditional)

**AS3**: Attack (`MANA_A`) is conditionally cleared in `manaRots()` (line 3113):
```actionscript
if(this.turnMana.pool[C.MANA_A] > 0 && this.helper.oppDefense == 0
   && !(this.controlledLane != -1 && this.turn == C.COLOR_WHITE))
{
    manaToRot.pool[C.MANA_A] = this.turnMana.pool[C.MANA_A];
    this.turnMana.pool[C.MANA_A] = 0;
}
```
Attack persists if the opponent has defense > 0 (i.e., if attack will be used during the opponent's upcoming defense phase).

**C++**: Attack is unconditionally zeroed in `beginTurn()` (line 1223). However, the C++ engine handles this differently at the phase-transition level. In `endPhase()` for Confirm (lines 1383-1412), it checks `getAttack(player) > 0` and if so, routes to `beginPhase(enemy, Phases::Defense)` instead of swoosh. The attack value carries through to the defense phase, then is consumed during blocking. After defense, the flow goes Defense -> Swoosh -> `beginTurn()` which then zeros attack.

If attack = 0 after action phase, endPhase goes Confirm -> Swoosh -> `beginTurn()` which zeros attack (already 0, no-op).

**VERDICT: MATCH (architecturally)** -- In both engines, attack persists into the opponent's defense phase when > 0. The C++ engine just zeros it later (at swoosh/beginTurn) rather than conditionally at end-of-turn. The net effect is identical: attack produced during your action phase persists through the opponent's defense, then gets cleared before your next action phase.

### B2.5: Resource Clear vs Card beginTurn Order

**AS3** (`swoosh`, lines 2582-3072):
1. Phase set to `PHASE_ACTION` (line 2607)
2. Iterate over all instances owned by current player:
   - Clear damage (line 2627)
   - Clear disruption damage (line 2636)
   - Tick construction time (line 2644)
   - Tick delay (line 2663)
   - Tick lifespan (line 2682)
   - Set role to DEFAULT/INERT (lines 2700-2705)
   - Set blocking to defaultBlocking (line 2706)
   - Gain health (lines 2708-2725)
   - Gain charge (lines 2726-2738)
   - Run `beginOwnTurnScript` which adds resources via `turnMana.add(script.receive)` (line 2872)
3. Resonate/annihilate processing (lines 3036-3068)

Key observation: In AS3, resources are rotted BEFORE swoosh (during `MOVE_ENTER_CONFIRM`), and then new resources are generated DURING swoosh via card scripts. There is no separate "zero resources, then generate" step within swoosh itself.

**C++** (`beginTurn`, lines 1215-1276):
1. Zero Energy, Blue, Red, Attack (lines 1220-1223)
2. beginTurn for dead cards (line 1239)
3. beginTurn for alive cards (line 1247) -- handles lifespan, delay, construction, health/charge gain, status reset, chill clear
4. Run beginOwnTurn scripts (line 1263) -- which call `runScript` -> `_getResources(player).add(script.getEffect().getReceive())`

**VERDICT: MATCH**

Both engines follow the same logical sequence:
1. Clear volatile resources (E/B/R/A)
2. Process per-card begin-turn effects (timers, status reset, health/charge gain)
3. Run begin-own-turn scripts that produce new resources

In AS3 the clearing happens at end-of-previous-turn (`manaRots`) while in C++ it happens at start-of-next-turn (`beginTurn`). Between these two points, no actions can occur (it is the swoosh phase), so the timing difference has no gameplay effect.

### B2 Test Cases

1. **Gold persistence**: Player has 3 Gold, ends turn. Next turn should start with 3 Gold (plus any Drone production). Both engines: Gold untouched.
2. **Green persistence**: Player has 2 Green, ends turn. Next turn should start with 2 Green (plus any new production). Both engines: Green untouched.
3. **Blue/Red/Energy decay**: Player has 3 Blue, 2 Red, 1 Energy. Ends turn. Next turn starts with 0 of each. Both engines: cleared.
4. **Attack carries to defense**: Player produces 5 attack. Opponent has defenders. After ENTER_CONFIRM, attack persists into opponent's defense phase. Both engines: attack available for blocking.
5. **Attack decays when no defense**: Player produces 5 attack. Opponent has 0 defense (all units invulnerable/under construction). Attack decays. AS3: `manaRots` clears it. C++: attack = 0 at `beginTurn` after swoosh.

---

## B3: Ability Use Side Effects Order

### B3.1: Health Cost Deduction

**AS3** (State.as `processMove`, MOVE_ASSIGN handler, lines 1446-1533):
Order within MOVE_ASSIGN:
```
1. inst.role = ROLE_ASSIGNED                     (line 1450)
2. inst.blocking = card.assignedBlocking         (line 1451)
3. inst.health -= card.healthUsed                (line 1455)
   -> if health == 0: deadness = SELFSACCED      (line 1463)
4. inst.charge -= card.chargeUsed                (line 1469)
5. this.payCost(card.abilityCost)                (line 1476)
6. this.sac(card.abilitySac)                     (line 1477)
7. if abilityNetherfy: this.netherfy()           (line 1478-1480)
8. this.runScriptForward(card.abilityScript)     (line 1482)
9. Target handling (snipe/disrupt)               (lines 1483-1525)
10. helper.update(this)                          (line 1530)
```

**C++** (GameState.cpp `runScript` called from USE_ABILITY handler, lines 915-1031):
The USE_ABILITY doAction handler (lines 576-631) calls `runScript()` which does:
```
1. Subtract mana cost (script.getManaCost())     (line 924)
2. Subtract sac cost (kill sac'd cards)          (lines 928-943)
3. Receive mana (script.getEffect().getReceive()) (line 946)
4. Give mana to enemy                            (line 949)
5. Resonate effects                              (lines 952-963)
6. Create cards                                  (lines 966-998)
7. Destroy cards                                 (lines 1000-1018)
8. card.useAbility()                             (line 1023)
   -> sets m_abilityUsedThisTurn = true          (Card.cpp:784)
   -> m_currentCharges -= chargeUsed             (Card.cpp:788)
   -> m_currentHealth -= healthUsed              (Card.cpp:791)
   -> if health == 0: kill(SelfAbilityHealthCost)(Card.cpp:795)
   -> setStatus(Assigned)                        (Card.cpp:798)
   -> runAbilityScript() [sets delay, self-sac]  (Card.cpp:800)
9. if script.isSelfSac(): killCardByID()         (lines 1027-1030)
```

For target abilities (SNIPE/CHILL), the USE_ABILITY handler sets `m_targetAbilityCardClicked = true` and returns early (lines 587-591). The actual effects happen in the SNIPE/CHILL handlers (lines 668-703), which call `runScript` AFTER the target kill/chill.

**CRITICAL DIFFERENCE IDENTIFIED**:

In AS3, health/charge costs are deducted BEFORE the script runs:
```
healthUsed -> chargeUsed -> payCost -> sac -> netherfy -> runScriptForward
```

In C++, health/charge costs are deducted AFTER the script runs (inside `card.useAbility()` which is called at line 1023, after `runScript` has already processed mana costs, sac costs, receive mana, create cards, and destroy cards):
```
manaCost -> sacCost -> receiveMana -> giveEnemy -> resonate -> createCards -> destroyCards -> useAbility(health/charge/status)
```

**VERDICT: MISMATCH (MEDIUM RISK)**

The health and charge deductions happen at different points relative to script execution. Specifically:
- **AS3**: Health/charge deducted FIRST, then script runs (create/receive/sac)
- **C++**: Script runs FIRST (create/receive/sac), then health/charge deducted

**Impact analysis**: This matters for units that have health cost AND script effects AND conditions. If a unit's health cost would kill it (health == 0), in AS3 it is marked dead BEFORE script effects run. In C++, the script effects run first, then the unit dies. For most units this is equivalent because the script still executes either way. However, the death timing could affect:
- Self-sac detection (AS3 checks `deadness == DEADNESS_SELFSACCED` before script)
- Card creation with creator tracking (C++ `addCreatedCardID` references the card which might be dead in AS3 but alive in C++)

In practice, units with `healthUsed > 0` (Tia Thurnax, Centurion, Blood Pact, etc.) typically have healthUsed < startingHealth, so they do NOT die from the health cost alone. The mismatch only triggers when `healthUsed == currentHealth`, which is rare.

### B3.2: Charge Cost Deduction

**AS3**: `inst.charge -= card.chargeUsed` at line 1469, BEFORE `payCost` and `runScriptForward`.

**C++**: `m_currentCharges -= getType().getChargeUsed()` in `Card::useAbility()` at Card.cpp:788, AFTER `runScript` completes.

**VERDICT: MISMATCH (same as B3.1)**

Same ordering difference as health cost. Charge deduction is early in AS3, late in C++. Impact is lower because running out of charges does not kill the unit -- it just prevents future ability use.

### B3.3: Ability Cost (Resource Payment)

**AS3**: `this.payCost(card.abilityCost)` at line 1476 -- directly subtracts from `turnMana`.

**C++**: `_getResources(player).subtract(script.getManaCost())` at GameState.cpp:924 -- first step inside `runScript()`.

Both deduct mana resources early in the process. In AS3 it is step 5 (after health/charge); in C++ it is step 1 of `runScript` (before everything else in the script, but after the USE_ABILITY handler checks legality).

**VERDICT: MATCH (effectively)**

Both deduct resource costs before script effects (create/receive/give). The ordering relative to health/charge differs (see B3.1), but resource payment itself is correctly early in both.

### B3.4: Self-Sacrifice Timing

**AS3** (`runScriptForward`, lines 2355-2461):
Self-sac is checked AFTER create/receive effects:
```
1. turnMana.add(script.receive)      (line 2369)
2. Create cards                       (lines 2376-2414)
3. if script.selfsac:                 (line 2415)
      inst.deadness = DEADNESS_SELFSACCED  (line 2417)
4. Delay assignment                   (line 2420)
```

**C++** (`runScript`, lines 915-1031):
Self-sac is checked AFTER card.useAbility:
```
1. manaCost, sacCost, receive, give, resonate, create, destroy  (lines 920-1018)
2. card.useAbility()                  (line 1023)
   -> inside: runAbilityScript() -> if selfSac: kill()  (Card.cpp:709-712)
3. if script.isSelfSac() || card.isDead():  (line 1027)
      killCardByID(cardID, SelfSac)   (line 1029)
```

**VERDICT: MATCH**

Both engines process self-sacrifice AFTER the script's create/receive effects. The unit produces its resources and creates its children before dying. The C++ has a redundant double-check (both `runAbilityScript()` at Card level and the outer `isSelfSac()` check at GameState level), but the net effect is identical.

### B3.5: Script Execution (Create/Receive)

**AS3** (`runScriptForward`, lines 2355-2461):
```
1. Receive mana (turnMana.add)
2. Create cards (iterate script.create[])
3. Self-sac
4. Delay
5. Scan
6. Mass chill
```

**C++** (`runScript`, lines 915-1031):
```
1. Mana cost subtraction
2. Sac cost
3. Receive mana
4. Give mana to enemy
5. Resonate effects
6. Create cards
7. Destroy cards
8. useAbility (health/charge/status/selfSac)
9. Self-sac kill
```

**VERDICT: MATCH (with structural differences)**

The core create/receive operations are in the same relative order in both. The C++ version includes additional steps (mana cost, sac cost, give enemy, resonate, destroy) that are handled outside `runScriptForward` in AS3 (see B3.3 -- mana cost is in `payCost`, sac cost is in `sac()`, both called from `processMove` before `runScriptForward`).

Reconstructed full AS3 order (from processMove + runScriptForward):
```
1. role = ASSIGNED
2. blocking = assignedBlocking
3. health -= healthUsed
4. charge -= chargeUsed
5. payCost (mana cost)
6. sac (sac cost)
7. netherfy
8. receive mana (in runScriptForward)
9. create cards (in runScriptForward)
10. self-sac (in runScriptForward)
11. delay (in runScriptForward)
12. mass chill (in runScriptForward)
13. target handling (snipe/disrupt)
```

Reconstructed C++ order (from doAction USE_ABILITY -> runScript -> useAbility):
```
1. [for target abilities: just set flag and return]
2. mana cost subtraction (in runScript)
3. sac cost (in runScript)
4. receive mana (in runScript)
5. give mana to enemy (in runScript)
6. resonate (in runScript)
7. create cards (in runScript)
8. destroy cards (in runScript)
9. abilityUsedThisTurn = true (in useAbility)
10. charge -= chargeUsed (in useAbility)
11. health -= healthUsed (in useAbility)
12. if health == 0: kill (in useAbility)
13. status = Assigned (in useAbility)
14. delay assignment (in runAbilityScript)
15. self-sac (in runAbilityScript + outer check)
```

Key ordering differences summarized:
| Step | AS3 Position | C++ Position |
|---|---|---|
| Status = Assigned | 1st (before everything) | 13th (after script) |
| Health cost | 3rd (before script) | 11th (after script) |
| Charge cost | 4th (before script) | 10th (after script) |
| Mana cost | 5th | 2nd (1st in runScript) |
| Sac cost | 6th | 3rd |
| Receive mana | 8th | 4th |
| Create cards | 9th | 7th |
| Self-sac | 10th | 15th |

The AS3 sets status to Assigned and deducts health/charge FIRST, then runs script effects. The C++ runs script effects FIRST, then sets status and deducts health/charge. This is a structural difference, but for most units it produces identical outcomes because health/charge deductions are unconditional once the ability is activated.

### B3 Test Cases

1. **Simple ability (Tarsier)**: Click Tarsier. Both: produces 1 Attack, sets Assigned. No health/charge cost. Match.
2. **Resource-costing ability (Zemora Voidbringer)**: Uses 8 Green. AS3: payCost subtracts Green, then script runs. C++: runScript subtracts Green first, then script effects. Both deduct before create. Match.
3. **Self-sac ability (Gauss Charge)**: Click Gauss Charge. Produces 1 Attack. Unit dies (self-sac). Both: receive attack, THEN mark dead. Match.
4. **Health cost ability (Tia Thurnax, healthUsed=1 of 4)**: AS3: health goes 4->3 first, then script. C++: script first, then health goes 4->3. No death trigger. Functionally equivalent.
5. **Health cost killing (theoretical: healthUsed == currentHealth)**: AS3: unit marked dead BEFORE script. C++: script runs BEFORE unit marked dead. Could cause difference in created-card tracking. **Potential mismatch but extremely rare in practice.**
6. **Sac cost (Odin, sacs a Drone)**: Both: find Drone, kill it as sac cost, then run rest of script. Match.

---

## B4: Snipe Mechanics

### B4.1: Immediate vs Deferred Death

**AS3** (State.as `processMove` MOVE_ASSIGN with targetAction == TARGETACTION_SNIPE, lines 1502-1524):
```actionscript
targetInst.deadness = C.DEADNESS_SNIPED;       // line 1504
this.dispatch(update,animate,C.SEND_SNIPED,...); // line 1505
targetInst.sniperId = instId;                    // line 1509
```
The target is marked as `DEADNESS_SNIPED` immediately. However, the instance is NOT removed from the table (`deleteInst` is NOT called). The sniped unit persists in `this.table` until `collectBodies` runs (during `MOVE_ENTER_CONFIRM` or `MOVE_END_DEFENSE`). The `deadness` flag prevents the unit from being interacted with, but it remains in the table.

This means sniped units are "logically dead but physically present" -- they cannot block, cannot be targeted again, but their instance still exists.

**C++** (GameState.cpp SNIPE handler, lines 668-684):
```cpp
card.setTargetID(target.getID());
killCardByID(action.getTargetID(), CauseOfDeath::Sniped);  // line 677
runScript(action.getID(), card.getType().getAbilityScript(), ScriptTypes::AbilityScript); // line 679
```
`killCardByID` calls `m_cards.killCardByID(cardID, causeOfDeath)` which calls `Card::kill()`:
```cpp
void Card::kill(const int causeOfDeath)
{
    m_dead = true;
    m_aliveStatus = AliveStatus::KilledThisTurn;
    m_causeOfDeath = causeOfDeath;
}
```
The card is marked dead immediately (`m_dead = true`). It moves to the killed cards list via `CardManager::killCardByID`. It is NOT removed from the CardManager entirely until `m_cards.removeKilledCards()` is called (at `beginTurn` line 1275 or endPhase(Confirm) line 1386).

**VERDICT: MATCH**

Both engines mark the sniped target as dead immediately upon snipe execution. Neither engine removes the card from its container immediately -- both defer physical removal to a later cleanup step (AS3: `collectBodies`, C++: `removeKilledCards`). The sniped card is excluded from all future interactions via its dead/deadness flag.

### B4.2: Defense Total Update After Snipe

**AS3** (State.as):
After a MOVE_ASSIGN with snipe, `this.helper.update(this)` is called at line 1530. The StateHelper's `update()` method (StateHelper.as lines 141+) recalculates `oppDefense` by iterating all non-dead, non-under-construction opponent instances that have `inst.blocking == true` (line 434):
```actionscript
if(inst.blocking)
{
    this.oppDefenders.push(inst);
    this.oppDefense += inst.damageItCanTake;  // line 437
}
```
Since the sniped unit has `deadness = DEADNESS_SNIPED` and the loop checks `!inst.dead` (line 420), the sniped unit is excluded from the defense total. Defense is correctly updated.

Key detail: The `helper.update()` is called AFTER the snipe is fully processed (line 1530), so the defense reflects the post-snipe state.

**C++** (GameState.cpp):
`getTotalAvailableDefense()` (lines 1523-1539) iterates live cards:
```cpp
for (const auto & cardID : getCardIDs(player))
{
    const Card & card = getCardByID(cardID);
    if (card.canBlock())
    {
        block += card.currentHealth();
    }
}
```
`getCardIDs(player)` returns only alive (non-killed) cards. Since `killCardByID` was called during the SNIPE handler, the killed card is moved to the killed cards list and no longer in the alive cards iteration. Therefore `getTotalAvailableDefense` automatically excludes sniped units.

However, there is a subtlety: `getTotalAvailableDefense` is NOT explicitly called after every snipe. It is called:
- At `endPhase(Confirm)` line 1404: `PRISMATA_ASSERT(getAttack(player) < getTotalAvailableDefense(enemy))`
- At `endPhase(Action)` line 1355: `canWipeout(player)` which likely uses defense
- At various legality checks

The C++ engine does NOT maintain a cached defense value like AS3's `helper.oppDefense`. Instead it recomputes on demand. Since killed cards are immediately excluded from `getCardIDs()`, any subsequent call to `getTotalAvailableDefense` will reflect the snipe.

**VERDICT: MATCH**

Both engines correctly exclude sniped units from defense calculations. AS3 does it via flag-based exclusion in `helper.update()`. C++ does it via structural exclusion (killed cards removed from alive list). Both produce correct post-snipe defense totals.

### B4.3: Snipe During Defense Phase

**AS3**:
Snipe is a target ability, which is activated via MOVE_ASSIGN. MOVE_ASSIGN requires `phase == PHASE_ACTION` (abilities can only be used during action phase). The defense phase is `PHASE_DEFENSE`. Therefore, snipe CANNOT occur during defense phase in AS3.

Evidence: The `canWipeBreachOverkill()` function (line 1379) and the general structure show that abilities (MOVE_ASSIGN) are only available during action phase. The defense phase only supports MOVE_BLOCK.

**C++**:
The `isLegal` check for SNIPE/CHILL (GameState.cpp lines 256-291) checks:
```cpp
if (!isTargetAbilityCardClicked())
{
    return false;
}
```
And `isTargetAbilityCardClicked()` can only be true when USE_ABILITY was previously called, which requires (line 297):
```cpp
if (getActivePhase() != Phases::Action)
{
    return false;
}
```

Therefore SNIPE can only occur after USE_ABILITY in Action phase, which means SNIPE itself implicitly requires Action phase. SNIPE cannot occur during Defense phase.

**VERDICT: MATCH**

Both engines restrict snipe (and all target abilities) to the Action phase. Snipe cannot occur during Defense phase in either engine.

### B4.4: Snipe Target Validation

**AS3** (MOVE_ASSIGN with TARGETACTION_SNIPE, line 1502):
No explicit target validation is shown in the `processMove` handler for SNIPE -- the target is assumed valid (the UI prevents illegal targets). The sniped target just gets `deadness = DEADNESS_SNIPED` directly.

**C++** (isLegal for SNIPE, lines 256-291):
```cpp
// can't snipe a dead card
if (targetCard.isDead()) return false;

// we can't target our own cards
if (player == getCardByID(action.getTargetID()).getPlayer()) return false;

// check snipe condition
if ((action.getType() == ActionTypes::SNIPE) && !targetCard.meetsCondition(card.getType().getTargetAbilityCondition()))
    return false;
```

The C++ validates: target alive, target is enemy, target meets the snipe condition (e.g., health <= N for units like Deadeye Operative). The AS3 relies on UI validation but the game server enforces these same checks.

**VERDICT: MATCH** -- Both engines enforce the same target restrictions, just at different layers (C++ in legality check, AS3 in UI + server).

### B4.5: Snipe Execution Order (Target Kill vs Script)

**AS3** (processMove MOVE_ASSIGN, lines 1446-1533):
The snipe target handling (lines 1502-1524) occurs AFTER `runScriptForward` (line 1482). The order is:
```
1. Role = Assigned
2. Health/charge deduction
3. payCost
4. sac
5. netherfy
6. runScriptForward (receive mana, create cards, self-sac)
7. TARGET HANDLING: snipe target (set deadness = SNIPED)
```

**C++** (doAction SNIPE, lines 668-684):
```cpp
card.setTargetID(target.getID());
killCardByID(action.getTargetID(), CauseOfDeath::Sniped);  // KILL FIRST
runScript(action.getID(), card.getType().getAbilityScript(), ...); // THEN SCRIPT
```

The C++ kills the target BEFORE running the ability script.

**IMPORTANT DIFFERENCE**: In AS3, the script runs BEFORE the target is sniped. In C++, the target is killed BEFORE the script runs.

**VERDICT: MISMATCH (MEDIUM RISK)**

The ordering of snipe-kill vs script-execution is reversed:
- **AS3**: script effects first, then target dies
- **C++**: target dies first, then script effects

**Impact analysis**: For most snipe units (Deadeye Operative, Lancetooth, etc.), the ability script produces resources (`receive` mana). Whether the target dies before or after resource production does not matter -- the resources are produced regardless. The difference would only matter if:
1. The script creates a card that depends on the target being alive
2. The script has a destroy effect that could target the same unit being sniped
3. The script has a resonate effect counting units of the sniped type

These scenarios are rare-to-nonexistent in the current card pool. The mismatch is present but practically harmless.

### B4.6: Chill (Disrupt) Mechanics Comparison

**AS3** (processMove MOVE_ASSIGN with TARGETACTION_DISRUPT, lines 1486-1501):
```actionscript
targetInst.disruptDamage += card.targetAmount;          // line 1488
if(targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
{
    targetInst.blocking = false;                        // line 1497
}
targetInst.disruptorIds.push(instId);                   // line 1500
```
Chill damage accumulates in `disruptDamage`. When total chill meets or exceeds the target's `damageItCanTake + damage`, blocking is set to false (unit is frozen). The `damageItCanTake` is the unit's effective HP after accounting for existing damage.

**C++** (doAction CHILL, lines 686-703):
```cpp
target.applyChill(card.getType().getTargetAbilityAmount());  // line 694
card.setTargetID(target.getID());                            // line 695
runScript(action.getID(), card.getType().getAbilityScript(), ...); // line 697
```

`Card::applyChill` (Card.cpp:431-436):
```cpp
m_currentChill += amount;
```

The blocking check is implicit in `Card::canBlock()` (Card.cpp:484-512):
```cpp
if (isFrozen())  // currentChill >= currentHealth
{
    return false;
}
```

And `canBlock` also checks `canBlock(getStatus() == CardStatus::Assigned)` which delegates to `CardType::canBlock(bool assigned)` which returns `getAssignedBlocking()` if assigned or `getDefaultBlocking()` if not.

**VERDICT: MATCH (with different mechanisms)**

Both engines correctly implement chill/freeze:
- AS3: tracks `disruptDamage` and explicitly toggles `blocking = false` when frozen
- C++: tracks `m_currentChill` and implicitly prevents blocking via `isFrozen()` check in `canBlock()`

The freeze threshold is equivalent: AS3 uses `disruptDamage >= damageItCanTake + damage` and C++ uses `currentChill >= currentHealth`. Since `damageItCanTake = health - damage` in AS3 terms, both resolve to `chill >= health`.

### B4 Test Cases

1. **Simple snipe (Deadeye Operative sniping a Drone)**: Both: Drone marked dead immediately, excluded from defense. Match.
2. **Snipe a blocker during action phase**: Player snipes opponent's Wall (3 HP blocker). Defense should decrease by 3. AS3: helper.update recalculates. C++: Wall removed from alive cards. Match.
3. **Cannot snipe during defense phase**: Both: ability activation requires Action phase. Match.
4. **Chill freezing a unit (Shiver Yeti on Engineer)**: Apply 1 chill to 1-HP Engineer. AS3: disruptDamage=1 >= damageItCanTake=1, blocking=false. C++: currentChill=1 >= currentHealth=1, isFrozen()=true, canBlock()=false. Match.
5. **Partial chill (Frostbite on Wall)**: Apply 1 chill to 3-HP Wall. AS3: disruptDamage=1, still blocking. C++: currentChill=1 < 3, not frozen, can still block. Match.
6. **Multiple chills accumulate**: Two Shiver Yetis chill a 3-HP Wall. AS3: disruptDamage=2, still blocking. C++: currentChill=2 < 3. Match. Third chill: AS3: disruptDamage=3 >= 3, frozen. C++: currentChill=3 >= 3, frozen. Match.

---

## Summary of Findings

| Check | Area | Verdict | Risk | Notes |
|---|---|---|---|---|
| B2.1 | Resource types cleared | MATCH | NONE | Both clear {E,B,R,A}, preserve {Gold,Green} |
| B2.2 | Gold persistence | MATCH | NONE | Gold persists in both |
| B2.3 | Green persistence | MATCH | NONE | Green persists in both |
| B2.4 | Attack persistence | MATCH | NONE | Both carry attack to defense phase |
| B2.5 | Clear vs card order | MATCH | NONE | Both: clear first, then card processing |
| B3.1 | Health cost deduction | **MISMATCH** | **MEDIUM** | AS3: before script. C++: after script |
| B3.2 | Charge cost deduction | **MISMATCH** | **LOW** | Same ordering issue as B3.1 |
| B3.3 | Ability cost (resources) | MATCH | NONE | Both deduct early |
| B3.4 | Self-sacrifice timing | MATCH | NONE | Both after create/receive |
| B3.5 | Script execution order | MATCH | NONE | Core effects in same relative order |
| B4.1 | Immediate vs deferred death | MATCH | NONE | Both mark dead immediately, defer removal |
| B4.2 | Defense update after snipe | MATCH | NONE | Both exclude sniped units |
| B4.3 | Snipe during defense | MATCH | NONE | Both restrict to Action phase |
| B4.4 | Snipe target validation | MATCH | NONE | Same checks, different layers |
| B4.5 | Snipe kill vs script order | **MISMATCH** | **MEDIUM** | AS3: script then kill. C++: kill then script |
| B4.6 | Chill mechanics | MATCH | NONE | Same freeze threshold, different mechanism |

### Mismatches Requiring Attention

**B3.1/B3.2 (Health/Charge deduction ordering)**: The C++ engine deducts health and charge costs AFTER running the ability script, while AS3 deducts them BEFORE. This affects units where `healthUsed == currentHealth` (unit dies from ability cost). In practice, very few standard units trigger this edge case. **Recommendation**: Move `useAbility()` call (or at least the health/charge deduction portion) to BEFORE `runScript()` in GameState.cpp.

**B4.5 (Snipe kill vs script ordering)**: The C++ engine kills the snipe target BEFORE running the sniper's ability script, while AS3 runs the script FIRST. This is reversed from expectation. **Recommendation**: In the SNIPE handler (GameState.cpp lines 668-684), move `killCardByID` to AFTER `runScript`. However, verify that no snipe unit's script depends on the target being alive/dead.
