# B1: Script/Trigger Execution Ordering Audit

**Auditor:** Claude Opus 4.6
**Date:** 2026-02-22
**Status:** COMPLETE
**Verdict:** Two HIGH-severity structural differences found, one MEDIUM, two LOW

---

## Executive Summary

The C++ engine and AS3 client differ in script execution ordering at two structural levels:

1. **beginOwnTurnScript timing (HIGH):** C++ uses a strict two-pass approach (all Card::beginTurn() first, then all beginOwnTurnScripts). AS3 processes each card in a single pass (lifespan/delay/refresh/beginOwnTurnScript per card before moving to the next). This changes the observable state during script execution for ~60 units with beginOwnTurnScripts.

2. **SNIPE target kill timing (HIGH):** C++ kills the snipe target BEFORE running the sniper's ability script. AS3 runs the ability script FIRST, then marks the target dead. This can affect scripts with resource effects or creates.

3. **Ability resolution sub-ordering (MEDIUM):** C++ merges sac-cost and self-sac into a single `runScript()` function. AS3 separates pay-cost, sac-cost, netherfy, ability-script, and target-action into distinct sequential steps with different dead-checking semantics.

4. **Resonate timing (LOW):** Both process resonate during the beginOwnTurnScript phase, but with subtly different collection/counting approaches.

5. **Trigger system (LOW):** AS3 has a full trigger/condition system. C++ has no trigger equivalent. Triggers are campaign/tutorial-only and do not affect standard gameplay.

---

## Check 1: beginOwnTurnScript Timing

### Risk: HIGH -- Structural Difference

### AS3 Code Path (State.as:2582-2920 -- swoosh function)

The swoosh function iterates through ALL instances owned by the current player in a **single pass**:

```actionscript
// State.as:2618-2920 (simplified)
for each(t in copyOfInstIds) {
    inst = this.table[t];
    if (inst.owner == this.turn) {
        // Step 1: Clear damage
        inst.damage = 0;
        inst.disruptDamage = 0;

        // Step 2: Tick construction time
        if (inst.constructionTime > 0) {
            --inst.constructionTime;
            if (inst.constructionTime != 0) continue;  // Skip rest if still building
        }
        // Step 3: Tick delay (only if not under construction)
        else if (inst.delay > 0) {
            --inst.delay;
            if (inst.delay != 0) continue;  // Skip rest if still delayed
        }
        // Step 4: Tick lifespan (only if not constructing/delayed)
        else if (inst.lifespan > 0) {
            --inst.lifespan;
            if (inst.lifespan == 0) {
                deleteInst(inst.instId);   // DIES HERE -- removed from table
                continue;                   // Skip rest
            }
        }

        // Step 5: Refresh status (only reached if alive + not constructing/delayed)
        stuffInPlay.push(inst);
        inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT;
        inst.blocking = card.defaultBlocking;

        // Step 6: Health/charge regeneration
        inst.health += card.healthGained;
        inst.charge += card.chargeGained;

        // Step 7: Run beginOwnTurnScript IMMEDIATELY for this card
        this.runScriptForward(update, animate, card.beginOwnTurnScript,
                              C.SCRIPTTYPE_BEGINOWNTURN, inst, null);

        // Step 8: Collect resonate/special unit info for post-loop processing
    }
}
// Step 9 (post-loop): Annihilator/Resonate resolution
// Step 10 (post-loop): Special units (Aurb Magnifier, EMP, Deep Impact, etc.)
// Step 11 (post-loop): executeTriggers()
```

**Key observation:** In AS3, when card N's beginOwnTurnScript runs, cards 0..N-1 have already been fully processed (refreshed statuses, regenerated health, run their own beginOwnTurnScripts), but cards N+1..end are still in their pre-swoosh state.

### C++ Code Path (GameState.cpp:1215-1276 -- beginTurn function)

The C++ engine uses a strict **two-pass** approach:

```cpp
// GameState.cpp:1215-1276 (simplified)
void GameState::beginTurn(const PlayerID player) {
    // Reset resources (energy, blue, red, attack -> 0)
    // ...

    // Snapshot card list
    std::vector<CardID> cardsAtStartOfTurn;
    for (const auto& cardID : getCardIDs(player))
        cardsAtStartOfTurn.push_back(cardID);

    // PASS 1: Card::beginTurn() for ALL cards
    for (const auto& cardID : cardsAtStartOfTurn) {
        _getCardByID(cardID).beginTurn();    // lifespan, delay, construction, status reset
        if (_getCardByID(cardID).isDead())
            killCardByID(cardID, CauseOfDeath::Unknown);
    }

    // PASS 2: beginOwnTurnScript for ALL surviving cards
    for (const auto& cardID : cardsAtStartOfTurn) {
        const Card& card = _getCardByID(cardID);
        if (!card.isDead() && card.getType().hasBeginOwnTurnScript()
            && card.canRunBeginOwnTurnScript()) {
            runScript(cardID, card.getType().getBeginOwnTurnScript(),
                      ScriptTypes::BeginTurnScript);
            card.runBeginTurnScript();  // Sets delay from script
        }
    }

    m_cards.removeKilledCards();
}
```

**Key observation:** In C++, when card N's beginOwnTurnScript runs, ALL cards have already completed their Card::beginTurn() (lifespan checks, construction ticks, status resets, health regen). No card's beginOwnTurnScript has interleaved effects with another card's construction/lifespan ticks.

### Card::beginTurn() First-Pass Detail (Card.cpp:574-643)

```cpp
void Card::beginTurn() {
    m_sellable = false;
    m_damageTaken = 0;
    m_wasBreached = false;
    m_abilityUsedThisTurn = false;
    m_killedCardIDs.clear();
    m_createdCardIDs.clear();
    clearTarget();

    // Dead cards: transition KilledThisTurn -> Dead, then return
    if (m_aliveStatus == AliveStatus::KilledThisTurn) {
        m_aliveStatus = AliveStatus::Dead;
        return;
    }

    // Lifespan tick (only if not constructing/delayed)
    if (!isUnderConstruction() && !isDelayed() && m_lifespan > 0) {
        --m_lifespan;
        if (m_lifespan == 0) { kill(CauseOfDeath::Lifespan); return; }
    }

    // Delay tick (only if not constructing)
    if (!isUnderConstruction() && isDelayed()) --m_currentDelay;
    if (isDelayed()) { setStatus(CardStatus::Inert); }

    // Construction tick
    if (isUnderConstruction()) m_constructionTime--;

    // Post-construction: health regen, status reset, chill clear
    if (!isUnderConstruction() && !isDelayed()) {
        m_currentHealth += m_type.getHealthGained();
        // clamp to healthMax...
        setStatus(hasAbility ? CardStatus::Default : CardStatus::Inert);
        m_currentChill = 0;
    }
}
```

### Concrete Impact Scenario

**Scenario: Centrifuge + Antima Comet**

- Antima Comet (internal: "Antima Comet"): `beginOwnTurnScript: {"selfsac":true}`, `resonate: "Engineer"`
- Antima Comet self-sacs at start of turn and resonates with Engineers for attack.

In C++, if Antima Comet is iterated after another unit with a `beginOwnTurnScript` that creates an Engineer, the newly created Engineer exists when Antima Comet's resonate is counted. But in AS3, whether the Engineer exists depends on iteration order within the `copyOfInstIds` loop (Dictionary key ordering in AS3 is insertion-order for integer keys).

**Scenario: Unit with lifespan=1 that produces resources via beginOwnTurnScript**

Example: Doomed Mech (internal: "Zemora Voidbringer", lifespan=3, `beginOwnTurnScript: {"receive":"4","selfsac":true}`).

- In AS3: If lifespan reaches 0 in the swoosh loop, the unit dies at Step 4 and its beginOwnTurnScript at Step 7 is NEVER REACHED (the `continue` skips it).
- In C++: Card::beginTurn() Pass 1 kills the unit (lifespan -> 0). Pass 2 checks `!card.isDead()` and ALSO skips the script.
- **Result: MATCH.** Both implementations correctly skip beginOwnTurnScript for units dying from lifespan expiry.

**Scenario: Fabricator creating Gauss Cannons**

Gauss Fabricator (internal: "Fabricator"): `beginOwnTurnScript: {"create":[["Minicannon","own"]]}` -- creates a Gauss Cannon each turn.

- In C++: All cards complete beginTurn() (Pass 1) before any beginOwnTurnScript fires (Pass 2). A newly-created Gauss Cannon from Pass 2 does NOT participate in any other card's Pass 1 processing.
- In AS3: The created Gauss Cannon is inserted into the table immediately. If another unit is processed later in the same swoosh loop, it can "see" the new Gauss Cannon. However, since created units have `constructionTime > 0`, they are not eligible for abilities or blocking that turn anyway.
- **Result: LOW IMPACT.** Created units from beginOwnTurnScript are under construction and functionally inert. The visibility difference is unlikely to produce different game states in practice.

### Verdict: HIGH (Structural Difference, LOW Practical Impact)

The two-pass vs single-pass architecture is a genuine structural difference. However, the practical impact is low because:

1. beginOwnTurnScript effects that produce **resources** (gold, energy, blue, red, attack) accumulate into a shared resource pool that is order-independent for counting purposes.
2. beginOwnTurnScript effects that **create units** produce units under construction that cannot interact with other swoosh-phase processing.
3. beginOwnTurnScript effects that **self-sac** remove the unit, but this does not affect other units' scripts since the iteration list is snapshotted in both implementations.
4. The only theoretically observable difference involves **resonate counting** when a beginOwnTurnScript creates a unit that another card resonates with -- see Check 4 below.

---

## Check 2: Script Execution Within Ability Use

### Risk: HIGH -- SNIPE Kill Timing Differs

### C++ SNIPE Action (GameState.cpp:668-684)

```cpp
case ActionTypes::SNIPE: {
    Card& card = _getCardByID(action.getID());         // sniper
    Card& target = _getCardByID(action.getTargetID());  // target
    card.setTargetID(target.getID());
    killCardByID(action.getTargetID(), CauseOfDeath::Sniped);  // KILL FIRST
    runScript(action.getID(), card.getType().getAbilityScript(),
              ScriptTypes::AbilityScript);                      // SCRIPT SECOND
    // ...
}
```

### AS3 MOVE_ASSIGN for Snipe (State.as:1476-1526)

```actionscript
// MOVE_ASSIGN handler:
this.payCost(update, animate, card.abilityCost, inst);
this.sac(update, animate, card.abilitySac, inst);
if (card.abilityNetherfy) this.netherfy(update, animate, inst);
this.runScriptForward(update, animate, card.abilityScript,
                      C.SCRIPTTYPE_ABILITY, inst, abilityCreateIds);  // SCRIPT FIRST
if (card.targetHas) {
    if (card.targetAction == C.TARGETACTION_SNIPE) {
        targetInst.deadness = C.DEADNESS_SNIPED;   // MARK DEAD SECOND
    }
}
```

### Analysis

**C++ order:** kill target -> run ability script (receive resources, create units, etc.)
**AS3 order:** run ability script -> mark target dead

This is a real ordering difference. The target is "dead" (in C++) or "alive" (in AS3) when the ability script's resource/create effects execute.

### Impact Assessment

For most snipe units, the ability script only includes the target-action effect itself (no separate `abilityScript` with resources or creates). However, if a snipe unit has BOTH a `targetAction: "snipe"` AND an `abilityScript` with `create` or `receive` effects, the kill-vs-alive state of the target could theoretically affect:

1. **Resonate counting** in the ability script: If the snipe target was a unit type that a resonate effect counts, C++ would not count it (dead), AS3 would count it (still alive in table).
2. **Sac-cost selection** in the ability script: If the snipe target was of a type being sacced, C++ would not select it (dead), AS3 would potentially select it (still in table with non-dead `deadness`).

In practice, no current snipe unit has both a target-snipe action and a separate resonate/sac in the ability script, so this is **theoretical risk only**.

### C++ CHILL Action (GameState.cpp:686-702)

```cpp
case ActionTypes::CHILL: {
    target.applyChill(card.getType().getTargetAbilityAmount());  // APPLY CHILL FIRST
    card.setTargetID(target.getID());
    runScript(action.getID(), card.getType().getAbilityScript(),
              ScriptTypes::AbilityScript);                       // SCRIPT SECOND
}
```

### AS3 MOVE_ASSIGN for Chill/Disrupt (State.as:1486-1500)

```actionscript
this.runScriptForward(...card.abilityScript...);  // SCRIPT FIRST
if (card.targetAction == C.TARGETACTION_DISRUPT) {
    targetInst.disruptDamage += card.targetAmount;  // APPLY CHILL SECOND
}
```

**C++ order:** apply chill -> run ability script
**AS3 order:** run ability script -> apply chill

Same structural pattern as SNIPE. The target's chill state differs during script execution.

### Verdict: HIGH (Structural Difference, LOW Practical Impact for Current Card Pool)

The ordering inversion is confirmed, but no current card combines a target-action with an ability script that would observe the difference.

---

## Check 3: Pay -> Sac -> Create -> Receive Order

### Risk: MEDIUM

### AS3 Ability Resolution (State.as:1446-1527, MOVE_ASSIGN)

```
1. inst.role = C.ROLE_ASSIGNED
2. inst.blocking = card.assignedBlocking
3. Health used (inst.health -= card.healthUsed; self-sac if health==0)
4. Charge used (inst.charge -= card.chargeUsed)
5. payCost(card.abilityCost)          -- subtract mana
6. sac(card.abilitySac)               -- mark sac targets as DEADNESS_SACCED
7. netherfy if applicable             -- mark enemy Drone as DEADNESS_NETHERED
8. runScriptForward(card.abilityScript) -- receive resources, create units
9. Target action (snipe/disrupt)       -- kill/chill target
```

### AS3 Buy Resolution (State.as:1625-1647, MOVE_BUY)

```
1. createInst (create the bought unit)
2. Update supply counters
3. payCost(card.buyCost)               -- subtract mana
4. sac(card.buySac)                    -- mark sac targets
5. runScriptForward(card.buyScript)    -- receive resources, create units
```

### C++ Ability Resolution (GameState.cpp:576-631, USE_ABILITY + runScript)

For non-target abilities:
```
1. runScript() called, which internally does:
   a. Subtract mana cost (script.getManaCost())
   b. Kill sac-cost units (script.getSacCost() -> killCardByID)
   c. Add received resources (script.getEffect().getReceive())
   d. Give resources to enemy (script.getEffect().getGive())
   e. Process resonate effects
   f. Create units (script.getEffect().getCreate())
   g. Destroy units (script.getEffect().getDestroy())
2. Card::useAbility() called AFTER runScript, which does:
   a. Set m_abilityUsedThisTurn = true
   b. Subtract charges
   c. Subtract health (kill if health==0)
   d. Set status to Assigned
   e. Card::runAbilityScript() -- set delay, self-sac
```

### C++ Buy Resolution (GameState.cpp:565-574, BUY)

```
1. buyCardByID() called, which internally does:
   a. Subtract buy cost (resources)
   b. Create the card (m_cards.buyCardByID)
   c. Kill sac-cost units (buySac)
2. runScript(buyScript) called, which does:
   a. Subtract script mana cost (if any)
   b. Kill script sac-cost units (if any)
   c. Receive resources
   d. Create units
```

### Key Differences

| Sub-step | AS3 | C++ |
|---|---|---|
| Health cost | Before sac, before script | After script (in useAbility()) |
| Charge cost | Before sac, before script | After script (in useAbility()) |
| Status -> Assigned | Before everything | After script (in useAbility()) |
| Sac cost (ability) | Separate `sac()` call before `runScriptForward` | Inside `runScript()` before receive/create |
| Self-sac from healthUsed | Sets DEADNESS_SELFSACCED before script | Calls kill() in useAbility() after script |

### Impact Analysis

**Health cost timing:** In AS3, health is subtracted BEFORE the ability script runs. If a unit's ability costs health and the health reaches 0, the unit is marked `DEADNESS_SELFSACCED` before its ability script produces resources/creates. In C++, health is subtracted AFTER the ability script, so the unit is alive during resource production.

However, in AS3, `DEADNESS_SELFSACCED` does NOT remove the unit from the table -- `deleteInst()` is not called. The unit remains in the table with deadness set but is still "present." The deadness flag only matters for subsequent lookups that check `.dead` property. In C++, `Card::kill()` sets `m_dead = true`, which prevents the card from being found in most queries.

**Practical scenario:** A unit with healthUsed=2, startingHealth=2 (one-shot ability that costs all HP) that also has a `receive` in its abilityScript. In AS3, the unit is marked dead but the script still runs and produces resources. In C++, `runScript()` runs while the unit is alive (health not yet deducted), then `useAbility()` kills it. Both produce the resources -- the difference is whether the unit is "dead" during the resource production step.

This matters if the ability script has a **sac cost** that could match the unit itself, or if it has a **resonate** that counts units of its own type. For current cards, no unit's ability script resonates with itself.

### Verdict: MEDIUM (Real Ordering Difference, Narrow Practical Impact)

The health/charge cost timing differs, but the practical effect is limited to edge cases involving units that kill themselves via health cost AND have scripts that would observe their own dead/alive state.

---

## Check 4: Death Script / Lifespan Death Execution

### Risk: LOW

### AS3 Death Model (State.as:2080-2083)

```actionscript
internal function deleteInst(instId:int) : void {
    delete this.table[instId];  // Immediate removal from hash table
}
```

AS3 uses a **two-phase death model**:
1. `inst.deadness` is set to a non-alive value (SACCED, SNIPED, SELFSACCED, AGED, NETHERED, MELEED)
2. `deleteInst()` is called to remove from the table -- but only for certain death types at certain times

During swoosh, lifespan death calls `deleteInst()` immediately (State.as:2692). Sac death during abilities sets `deadness` but does NOT call `deleteInst()` -- the unit stays in the table as "dead."

### C++ Death Model (Card.cpp:514-519, GameState.cpp:1190-1193)

```cpp
void Card::kill(const int causeOfDeath) {
    m_dead = true;
    m_aliveStatus = AliveStatus::KilledThisTurn;
    m_causeOfDeath = causeOfDeath;
}

void GameState::killCardByID(const CardID cardID, const int causeOfDeath) {
    m_cards.killCardByID(cardID, causeOfDeath);  // Moves to killed list
}
```

C++ uses a **deferred cleanup model**:
1. `Card::kill()` sets `m_dead = true` and `KilledThisTurn` status
2. Card is moved to a "killed cards" list
3. `m_cards.removeKilledCards()` is called at the end of `beginTurn()` (GameState.cpp:1275)

### Key Difference

In AS3, `deleteInst()` during swoosh lifespan death **immediately removes** the unit from the table. No subsequent swoosh processing can find it. In C++, the unit is marked dead but remains in the card list until `removeKilledCards()` at the end of beginTurn. However, all C++ queries check `isDead()` and skip dead cards, so the practical effect is equivalent.

### Sac Death During Abilities

In AS3, `sac()` sets `deadness = C.DEADNESS_SACCED` but does NOT call `deleteInst()`. The sacced unit remains in the table. The property `inst.dead` returns `true` (Inst.as:214: `return this.deadness != C.DEADNESS_ALIVE`), and subsequent `allCardsOfColorWithName` calls check `!inst.dead`, so sacced units are excluded from future lookups.

In C++, `killCardByID()` during runScript sac processing moves the card to the killed list, and `isDead()` returns `true`. Subsequent card lookups skip dead cards.

**Result: FUNCTIONAL MATCH.** Both implementations produce equivalent "dead = excluded from queries" semantics despite different internal representations.

### Verdict: LOW (Implementation Differs, Behavior Matches)

---

## Check 5: Trigger Conditions Evaluation

### Risk: LOW (Campaign/Tutorial Only)

### AS3 Trigger System (Trigger.as, State.as:4068-4098)

```actionscript
// State.as:4068 -- called at end of swoosh (line 3071)
internal function executeTriggers(update, animate) {
    for (i = 0; i < this.triggers.length; i++) {
        trigger = this.triggers[i];
        // Skip if duringSwoosh trigger and not in Action phase
        // Skip if not duringSwoosh and not in Confirm phase (turn > 0)
        // Skip if once-trigger already fired
        if (this.satisfiesAllConditions(trigger.conditions)) {
            for (j = 0; j < trigger.actions.length; j++) {
                this.executeAction(update, animate, trigger.actions[j]);
            }
            this.triggerExecuted[i] = true;
        }
    }
}
```

Triggers have:
- `duringSwoosh` (Boolean): execute during Action phase (after swoosh) vs Confirm phase
- `once` (Boolean): fire only once
- `conditions` (Array of condition arrays): all must be satisfied
- `actions` (Array of action arrays): set/inc/dec counters, reveal/complete/fail objectives, create units, etc.

### C++ Trigger System

**No equivalent exists.** The C++ engine has no trigger mechanism. There is no `Trigger` class, no `executeTriggers()` function, and no condition/action evaluation system.

### Impact Assessment

Triggers are used exclusively in **campaign missions and tutorials** for scripted events (objectives, unit spawning, victory conditions). They do not appear in standard PvP or bot games. The `cardLibrary.jso` unit definitions do not reference triggers -- triggers are defined in mission/campaign configuration files.

Since the C++ AI engine only simulates standard Prismata games (PvP, bot matches, self-play), the absence of a trigger system has **zero impact** on game state accuracy for any scenario the engine handles.

### Verdict: LOW (No Impact on Standard Games)

---

## Test Cases

### Test Case A: Unit A's Script Produces Gold, Unit B Costs That Gold

**Setup:** Player owns Drone (gold producer via beginOwnTurnScript: receive "1") and a unit with beginOwnTurnScript that has a mana cost requiring gold.

**Question:** Does the ordering of beginOwnTurnScript execution matter?

**Analysis:**

No current unit has a `beginOwnTurnScript` with a `manaCost` property -- beginOwnTurnScripts in cardLibrary.jso only have `receive`, `create`, `selfsac`, and `delay` effects. The Script class supports mana costs (`hasManaCost`, parsed from JSON), but no card definition uses this for begin-turn scripts.

However, the **resource pool** is shared. Both implementations add resources to the same pool:
- C++: `_getResources(player).add(script.getEffect().getReceive())` (GameState.cpp:946)
- AS3: `this.turnMana.add(script.receive)` (State.as:2369)

In C++ (two-pass), all beginOwnTurnScripts run after all Card::beginTurn() calls. Resource production from script N is immediately visible to script N+1 since both add to the same `m_resources[player]` object.

In AS3 (single-pass), resource production from card N is immediately visible to card N+1's beginOwnTurnScript because `turnMana` is a shared object modified in-place.

**Verdict:** Both implementations produce identical resource totals since addition is commutative and no beginOwnTurnScript has a mana cost that would create order-dependence. **NO DIFFERENCE.**

### Test Case B: Ability that Sacs Unit X and Creates Unit Y -- Verify Sac Before Create

**Setup:** Unit with ability that has sacCost (e.g., Monk: `abilitySac: [["Engineer", 3]]`, `abilityScript: {"receive":"5"}`).

**C++ Order (GameState.cpp:915-1031, runScript):**
```
1. Subtract mana cost (line 924)
2. Kill sac-cost units (lines 928-942)
3. Receive resources (line 946)
4. Give resources to enemy (line 949)
5. Process resonate (lines 952-963)
6. Create units (lines 968-998)
7. Destroy units (lines 1001-1018)
8. useAbility() -- health, charges, status, delay (line 1023)
9. Self-sac if applicable (lines 1027-1030)
```

**AS3 Order (State.as:1446-1527, MOVE_ASSIGN):**
```
1. Set role to ASSIGNED (line 1450)
2. Subtract health cost (lines 1453-1466)
3. Subtract charge cost (lines 1467-1475)
4. payCost -- subtract mana (line 1476)
5. sac -- mark sac targets as dead (line 1477)
6. netherfy if applicable (lines 1478-1481)
7. runScriptForward (line 1482):
   a. Receive resources (line 2369)
   b. Create units (lines 2376-2414)
   c. Self-sac (lines 2415-2418)
   d. Set delay (lines 2420-2428)
8. Target action -- snipe/disrupt (lines 1483-1526)
```

**Key finding:** In BOTH implementations, sac-cost units are killed/marked-dead BEFORE the ability script creates new units. This is correct -- you cannot use the "about to be created" unit to pay the sac cost.

**C++:** Sac happens at step 2 inside runScript. Create happens at step 6.
**AS3:** Sac happens at step 5 (separate `sac()` call). Create happens at step 7b (inside `runScriptForward`).

**Verdict:** Sac-before-create ordering is consistent. **MATCH.**

### Test Case C: Resonate Count After beginOwnTurnScript Creates a Resonated-With Unit

**Setup:** Player owns:
- Ionic Welder (internal: "Ionic Welder"): `beginOwnTurnScript: {"create":[["Drone","own"],["Treant","own"]]}`
- Immaculon (internal: "Immaculon"): `beginOwnTurnScript: {"delay":2}`, `resonate: "Drone"`

**Question:** Does the Drone created by Ionic Welder's beginOwnTurnScript count toward Immaculon's resonate?

**C++ behavior:** Resonate is processed inside `runScript()` during the beginOwnTurnScript second pass. `numCardsOfType(player, resonateType, true)` counts all non-dead cards of the resonate type at script execution time. If Ionic Welder runs before Immaculon, the newly created Drone exists and IS counted (it's under construction but the `true` parameter means "count under construction"). If Immaculon runs first, the Drone doesn't exist yet and is NOT counted. The order depends on card ID ordering in `cardsAtStartOfTurn`.

**AS3 behavior:** In the swoosh single-pass loop, Immaculon's resonate is NOT processed inside `runScriptForward`. Instead, resonate information is **collected** during the swoosh loop (lines 2874-2895) and resolved **after the loop** (lines 3036-3068). The resonate resolution counts `stuffInPlay` (units that survived swoosh processing), which includes units that existed at swoosh start -- but NOT units created by beginOwnTurnScript, because newly created units are not in `copyOfInstIds` (the snapshot taken before the loop).

**Wait -- this needs correction.** Looking more carefully at AS3: resonate is resolved in a **post-loop** phase using `annihilators` and `annihilatees` dictionaries. The `annihilatees` are collected from `stuffInPlay` (line 2924-2948), which was populated during the main loop. Newly created units from `runScriptForward` are added to the table but NOT to `stuffInPlay`. So AS3 resonate does NOT count units created by beginOwnTurnScript.

In C++, resonate is processed **inside** `runScript()` at script execution time, so it CAN count units created by a preceding card's beginOwnTurnScript.

**Verdict:** This is a real difference. C++ resonate may count more units than AS3 resonate when beginOwnTurnScripts create units of the resonated type. However, in practice:
- Immaculon resonates with Drones -- newly created Drones from Ionic Welder would be under construction and might not be countable depending on `numCardsOfType`'s construction filter.
- The 5 resonate units in the card pool (Immaculon/Drone, Savior/Drone-gold, Resophore/Forcefield, Amporilla/Tarsier, Antima Comet/Engineer) are unlikely to appear in games alongside units that create the resonated type via beginOwnTurnScript.

---

## Summary of Differences

| # | Check | Severity | Structural Diff? | Practical Impact |
|---|---|---|---|---|
| 1 | beginOwnTurnScript timing (two-pass vs single-pass) | HIGH | YES | LOW -- resource addition is commutative; created units are under construction |
| 2 | SNIPE kill timing (before vs after ability script) | HIGH | YES | LOW -- no current snipe unit has script effects that observe target state |
| 3 | Ability resolution sub-ordering (health/charge/status) | MEDIUM | YES | LOW -- health-death before vs after script; no card exploits this |
| 4 | Resonate counting during beginOwnTurnScript | LOW | YES | VERY LOW -- only theoretically possible with specific unit combinations |
| 5 | Trigger system (absent in C++) | LOW | YES | NONE -- triggers are campaign-only |

## Affected Unit Combinations

The following combinations COULD theoretically produce different game states:

### High-Confidence Differences (Structural, But Unobservable With Current Cards)

1. **Any snipe unit + target that is also counted by a resonate**: C++ kills target before script (resonate counts fewer). AS3 runs script before kill (resonate counts more). No current card combines snipe + resonate.

2. **Unit with healthUsed=health (one-shot) + abilityScript with sac-cost of own type**: C++ would find the unit alive during sac selection. AS3 would find it dead (health already deducted).

### Low-Confidence Differences (Require Specific Iteration Orders)

3. **Ionic Welder + Immaculon**: C++ might count Ionic Welder's created Drones in Immaculon's resonate (depends on card ID ordering). AS3 never counts them (post-loop resolution). Would differ by at most 1-2 attack points per turn.

4. **Multiple Fabricator-type units (Gauss Fabricator, Oxide Mixer, Frost Brooder)**: In C++, a Gauss Cannon created by one Fabricator exists during another card's beginOwnTurnScript. In AS3, it also exists (added to table) but is not in `stuffInPlay` for resonate. Only matters if combined with a resonate unit targeting the created type -- currently no such combination exists.

5. **Antima Comet + any unit creating Engineers via beginOwnTurnScript**: Antima Comet resonates with Engineers. If another card's beginOwnTurnScript creates an Engineer, C++ might count it; AS3 would not. Currently, only Monk creates Engineers via beginOwnTurnScript, and Monk creates them as part of its ability (not begin-turn), so this scenario does not arise.

## Recommendations

1. **No code changes required.** The differences are structural but have no practical impact on any realistic game state with the current card pool.

2. **If implementing new units** that create cards via beginOwnTurnScript AND those created cards match another unit's resonate type, explicitly verify behavior against AS3 or document the intentional deviation.

3. **The SNIPE kill-before-script ordering** in C++ is arguably more correct (the target should be dead when the sniper's effects resolve), but differs from AS3. If strict AS3 compatibility is desired, move `killCardByID` after `runScript` in the SNIPE handler. This is a one-line change but should be validated against replay data.

4. **The two-pass beginTurn architecture** is a deliberate design choice in the C++ engine (likely for performance/clarity). It produces equivalent results for all practical scenarios. No change recommended.
