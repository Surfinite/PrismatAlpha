# P0.2: Comprehensive Status Reset Scan

> Produced: 2026-02-22
> Scope: ALL card state mutations in both C++ (`source/engine/`) and AS3 (`prismata_decompiled/scripts/mcds/engine/`)

---

## Table of Contents

1. [C++ Status Changes](#1-c-status-changes)
2. [AS3 Status Changes](#2-as3-status-changes)
3. [Cross-Reference Table](#3-cross-reference-table)
4. [Anomalies](#4-anomalies)
5. [Risk Assessment](#5-risk-assessment)

---

## 1. C++ Status Changes

### 1.1 Card Status (`m_status` / `setStatus`)

C++ has three statuses: `Default` (0), `Assigned` (1), `Inert` (2) -- defined in `CardType.h:12`.

#### 1.1.1 JSON Deserialization -- `Card::Card(const rapidjson::Value &)` (Card.cpp:20-176)

Sets status from the `"role"` JSON property when loading game state from F6 clipboard or replay data.

```cpp
// Card.cpp:51-67
if (role == "default")       { m_status = CardStatus::Default; }
else if (role == "assigned") { m_status = CardStatus::Assigned; }
else if (role == "inert")    { m_status = CardStatus::Inert; }
else if (role == "sellable") { m_status = CardStatus::Inert; m_sellable = true; }
```

Purpose: Reconstruct card state from serialized JSON. "sellable" maps to Inert + `m_sellable=true`.

#### 1.1.2 Card Creation -- `Card::Card(CardType, PlayerID, int, TurnType, TurnType)` (Card.cpp:178-237)

Sets initial status based on how the card was created.

```cpp
// Card.cpp:190 (initializer list)
, m_status(CardStatus::Inert)  // default before switch

// Card.cpp:200-230 (switch on creationMethod)
case Bought:         m_status = CardStatus::Inert; m_sellable = true;    // line 205-206
case AbilityScript:  m_status = CardStatus::Inert;                       // line 211
case BuyScript:      m_status = CardStatus::Inert;                       // line 217
case Manual:         if (hasAbility || hasTargetAbility) m_status = CardStatus::Default; // line 223-225
```

Purpose: All new cards start Inert (under construction / delayed). Manual creation with abilities starts Default (for game state reconstruction).

#### 1.1.3 Begin Turn -- `Card::beginTurn()` (Card.cpp:574-643)

Runs during Swoosh phase (called from `GameState::beginTurn`). This is the PRIMARY status reset for the turn cycle.

```cpp
// Card.cpp:610-612  -- delayed cards stay Inert
if (isDelayed()) { setStatus(CardStatus::Inert); }

// Card.cpp:632-639  -- completed, non-delayed cards get refreshed
if (getType().hasAbility() || getType().hasTargetAbility())
    setStatus(CardStatus::Default);    // line 634
else
    setStatus(CardStatus::Inert);      // line 638
```

Also resets: `m_sellable = false`, `m_damageTaken = 0`, `m_wasBreached = false`, `m_abilityUsedThisTurn = false`, `m_currentChill = 0` (line 641), `clearTarget()`.

Purpose: Refresh all cards at start of turn. Ability-having cards become Default (available), others become Inert.

#### 1.1.4 Use Ability -- `Card::useAbility()` (Card.cpp:775-801)

```cpp
// Card.cpp:798
setStatus(CardStatus::Assigned);
```

Also: `m_abilityUsedThisTurn = true`, decrements charges and health, calls `runAbilityScript()`.

Purpose: Mark card as having used its ability this turn.

#### 1.1.5 Undo Use Ability -- `Card::undoUseAbility()` (Card.cpp:737-764)

```cpp
// Card.cpp:760
setStatus(CardStatus::Default);
```

Also: `m_abilityUsedThisTurn = false`, restores charges and health, clears delay and killed card IDs.

Purpose: Revert ability usage (player undo action).

#### 1.1.6 **[BUG] Defense Phase Reset -- `GameState::beginPhase(Defense)` (GameState.cpp:1289-1307)**

```cpp
// GameState.cpp:1293-1306
for (const auto & cardID : getCardIDs(player))
{
    Card & card = _getCardByID(cardID);
    if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed())
    {
        if (card.getType().hasAbility() || card.getType().hasTargetAbility())
            card.setStatus(CardStatus::Default);     // line 1300
        else
            card.setStatus(CardStatus::Inert);       // line 1304
    }
}
```

Purpose: **KNOWN BUG (commit 5bf57a8)**. Resets all card statuses to Default/Inert at the start of Defense phase. This allows tapped (Assigned) Drones to block when they should not be able to. The AS3 engine has NO equivalent -- defense phase transition does not modify card roles.

### 1.2 Alive Status (`m_dead`, `m_aliveStatus`, `m_causeOfDeath`)

#### 1.2.1 Kill -- `Card::kill(int causeOfDeath)` (Card.cpp:514-519)

```cpp
m_dead = true;
m_aliveStatus = AliveStatus::KilledThisTurn;
m_causeOfDeath = causeOfDeath;
```

Called from: `takeDamage` (Block/Breach death), `useAbility` (health cost = 0 kills), `runAbilityScript` (self-sac), `GameState::killCardByID` (sac cost, snipe, destroy, lifespan, etc.).

#### 1.2.2 Undo Kill -- `Card::undoKill()` (Card.cpp:892-899)

```cpp
m_aliveStatus = AliveStatus::Alive;
m_dead = false;
m_causeOfDeath = CauseOfDeath::None;
```

Called from: `CardData::undoKill`, `GameState::runScriptUndo`, `GameState::undoBreachCard`.

#### 1.2.3 Begin Turn Alive Status Transition -- `Card::beginTurn()` (Card.cpp:586-590)

```cpp
if (m_aliveStatus == AliveStatus::KilledThisTurn)
{
    m_aliveStatus = AliveStatus::Dead;
    return;  // early exit, no further processing
}
```

Purpose: Transition recently killed cards from "KilledThisTurn" to permanent "Dead" status.

#### 1.2.4 Undo Use Ability -- Revive from health cost (Card.cpp:746-758)

```cpp
// Card.cpp:746-750 -- health cost death reversal
if (m_type.getHealthUsed() > 0 && m_currentHealth == 0) {
    m_aliveStatus = AliveStatus::Alive;
    m_causeOfDeath = CauseOfDeath::None;
}

// Card.cpp:754-758 -- self-sac death reversal
if (m_type.getAbilityScript().isSelfSac()) {
    m_aliveStatus = AliveStatus::Alive;
    m_causeOfDeath = CauseOfDeath::None;
}
```

Note: Does NOT set `m_dead = false` directly -- that is handled by `CardData::undoKill` which calls `Card::undoKill()`.

### 1.3 Health (`m_currentHealth`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:32 | JSON constructor | `= type.getStartingHealth()` | Default init |
| Card.cpp:44 | JSON prop "hp"/"health" | `= val.GetInt()` | Deserialize |
| Card.cpp:184 | 4-arg constructor | `= type.getStartingHealth()` | Creation init |
| Card.cpp:397 | `takeDamage` | `m_damageTaken = min(amount, health)` | Track damage |
| Card.cpp:423 | `takeDamage` (fragile) | `-= min(amount, health)` | Fragile HP reduction |
| Card.cpp:547 | `undoBreach` (fragile) | `+= m_damageTaken` | Undo fragile damage |
| Card.cpp:551 | `undoBreach` (non-fragile) | `= startingHealth` | Full health restore |
| Card.cpp:625 | `beginTurn` | `+= healthGained` | Turn health regen |
| Card.cpp:628 | `beginTurn` | `= healthMax` | Cap at max |
| Card.cpp:697 | `canUseAbility` (check) | health < healthUsed | Ability health check |
| Card.cpp:752 | `undoUseAbility` | `+= healthUsed` | Restore ability cost |
| Card.cpp:791 | `useAbility` | `-= healthUsed` | Pay ability cost |

### 1.4 Chill (`m_currentChill`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:77 | JSON prop "disrupt" | `= val.GetInt()` | Deserialize |
| Card.cpp:186 | 4-arg constructor | `= 0` | Init |
| Card.cpp:435 | `applyChill` | `+= amount` | Apply chill to card |
| Card.cpp:442 | `removeChill` | `-= amount` | Remove chill (undo) |
| Card.cpp:641 | `beginTurn` | `= 0` | Clear chill at turn start |

### 1.5 Construction Time (`m_constructionTime`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:107 | JSON prop | `= val.GetInt()` | Deserialize |
| Card.cpp:204 | Bought creation | `= type.getConstructionTime()` | Buy sets build time |
| Card.cpp:218 | BuyScript creation | `= delay` | Script-created build time |
| Card.cpp:618 | `beginTurn` | `--` | Tick down construction |

### 1.6 Delay (`m_currentDelay`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:97 | JSON prop "delay" | `= val.GetInt()` | Deserialize |
| Card.cpp:212 | AbilityScript creation | `= delay` | Ability-created delay |
| Card.cpp:228 | Manual creation | `= delay` | Manual creation delay |
| Card.cpp:607 | `beginTurn` | `--` | Tick down delay |
| Card.cpp:707 | `runAbilityScript` | `= abilityScript.getDelay()` | Apply ability delay |
| Card.cpp:719 | `runBeginTurnScript` | `= beginOwnTurnScript.getDelay()` | Apply BOT delay |
| Card.cpp:762 | `undoUseAbility` | `= 0` | Clear delay on undo |

### 1.7 Lifespan (`m_lifespan`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:34 | JSON constructor | `= type.getLifespan()` | Default init |
| Card.cpp:87 | JSON prop "lifespan" | `= val.GetInt()` (or 0 if -1) | Deserialize |
| Card.cpp:187 | 4-arg constructor | `= lifespan or type.getLifespan()` | Creation init |
| Card.cpp:595 | `beginTurn` | `--` | Tick down; kills if reaches 0 |

### 1.8 Charges (`m_currentCharges`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:33 | JSON constructor | `= type.getStartingCharge()` | Default init |
| Card.cpp:92 | JSON prop "charge" | `= val.GetInt()` | Deserialize |
| Card.cpp:182 | 4-arg constructor | `= type.getStartingCharge()` | Creation init |
| Card.cpp:743 | `undoUseAbility` | `+= chargeUsed` | Restore charges |
| Card.cpp:788 | `useAbility` | `-= chargeUsed` | Spend charges |

### 1.9 Sellable (`m_sellable`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Card.cpp:66 | JSON "sellable" role | `= true` | Deserialize |
| Card.cpp:196 | 4-arg constructor | `= false` | Init |
| Card.cpp:206 | Bought creation | `= true` | Newly bought cards are sellable |
| Card.cpp:577 | `beginTurn` | `= false` | Cards lose sellability after 1 turn |

### 1.10 Other State (GameState-level)

| Location | Function | Change | Purpose |
|---|---|---|---|
| GameState.cpp:589-590 | `doAction(USE_ABILITY)` | `m_targetAbilityCardClicked = true` | Track targeting |
| GameState.cpp:681-682 | `doAction(SNIPE)` | `m_targetAbilityCardClicked = false` | Clear targeting after snipe |
| GameState.cpp:699-700 | `doAction(CHILL)` | `m_targetAbilityCardClicked = false` | Clear targeting after chill |
| GameState.cpp:753-754 | `doAction(UNDO_USE_ABILITY)` | `m_targetAbilityCardClicked = false` | Clear targeting on undo |
| GameState.cpp:1226 | `beginTurn` | `m_canBreachFrozenCard = false` | Reset breach flag |
| GameState.cpp:1220-1223 | `beginTurn` | Resources Energy/Blue/Red/Attack = 0 | Reset resources |

---

## 2. AS3 Status Changes

### 2.1 Role (`inst.role`)

AS3 uses string constants: `"default"`, `"assigned"`, `"sellable"`, `"inert"` (C.as:188-194).

#### 2.1.1 Instance Creation -- `Inst` constructor (Inst.as:60-135)

```as3
// Inst.as:70-77 -- new instances
if (bought)      { this.role = C.ROLE_SELLABLE; }  // line 72
else             { this.role = C.ROLE_INERT; }      // line 76
```

Purpose: Bought cards start Sellable; ability-created/script-created start Inert.

#### 2.1.2 State Reconstruction from initArray -- `State.as:3162-3234`

```as3
// State.as:3162-3176 -- explicit role from save data
case "role":
    "default"  => inst.role = C.ROLE_DEFAULT;     // line 3166
    "assigned" => inst.role = C.ROLE_ASSIGNED;     // line 3169
    "sellable" => inst.role = C.ROLE_SELLABLE;     // line 3172
    "inert"    => inst.role = C.ROLE_INERT;        // line 3175

// State.as:3203-3215 -- delay property sets role
case "delay":
    if (delay > 0) { inst.role = C.ROLE_INERT; }           // line 3207
    else { inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT; } // line 3213

// State.as:3223-3234 -- buildTime property sets role
case "buildTime":
    if (buildTime > 0) { inst.role = C.ROLE_INERT; }       // line 3227
    else { inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT; } // line 3233
```

#### 2.1.3 MOVE_ASSIGN (Use Ability) -- `State.as:1446-1532`

```as3
// State.as:1450
inst.role = C.ROLE_ASSIGNED;
```

Purpose: Mark card as having used its ability (equivalent to C++ `Card::useAbility`).

#### 2.1.4 MOVE_UNASSIGN (Undo Ability) -- `State.as:1534-1615`

```as3
// State.as:1538
inst.role = C.ROLE_DEFAULT;
```

Purpose: Revert ability usage (equivalent to C++ `Card::undoUseAbility`).

#### 2.1.5 Sac (Sacrifice for ability cost) -- `State.sac()` (State.as:2262-2278)

```as3
// State.as:2271 -- sacced units with abilities go to Inert
toSac[i].role = C.ROLE_INERT;
```

Purpose: When a card is sacrificed as ability cost, set its role to Inert.

#### 2.1.6 Unsac (Undo sacrifice) -- `State.unsac()` (State.as:2291-2328)

```as3
// State.as:2316 -- selfsac units go back to Default
toUnsac[j].role = C.ROLE_DEFAULT;

// State.as:2320 -- non-selfsac units go back to Assigned
toUnsac[j].role = C.ROLE_ASSIGNED;
```

Purpose: Restore original role when undoing a sacrifice.

#### 2.1.7 Swoosh (Begin Turn) -- `State.swoosh()` (State.as:2582-3035)

The primary turn-cycle status reset:

```as3
// State.as:2652-2654 -- sellable cards still under construction lose sellable
if (inst.role == C.ROLE_SELLABLE) { inst.role = C.ROLE_INERT; }

// State.as:2671-2674 -- delayed cards that still have delay go to Inert
if (inst.role != C.ROLE_INERT) { inst.role = C.ROLE_INERT; }

// State.as:2700-2704 -- completed, non-delayed units get refreshed
if (card.hasAbility) { inst.role = C.ROLE_DEFAULT; }
else                 { inst.role = C.ROLE_INERT; }
```

Purpose: Equivalent to C++ `Card::beginTurn()`. Refreshes roles for the new turn.

### 2.2 Blocking (`inst.blocking`)

#### 2.2.1 Instance Creation -- `Inst` constructor (Inst.as:78-84)

```as3
if (buildTime > 0) { this.blocking = false; }          // line 80
else               { this.blocking = card.defaultBlocking; } // line 84
```

#### 2.2.2 MOVE_ASSIGN -- `State.as:1451`

```as3
inst.blocking = card.assignedBlocking;
```

Purpose: When ability used, blocking changes to assigned state (e.g., Drone loses blocking).

#### 2.2.3 MOVE_UNASSIGN -- `State.as:1539`

```as3
inst.blocking = card.defaultBlocking;
```

Purpose: Restore default blocking on undo.

#### 2.2.4 Chill freezes (DISRUPT) -- `State.as:1497`

```as3
if (targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
    targetInst.blocking = false;
```

Purpose: Fully chilled cards lose blocking capability.

#### 2.2.5 Undo Chill (UNDISRUPT) -- `State.as:1586`

```as3
if (targetInst.disruptDamage < targetInst.damageItCanTake + targetInst.damage)
    targetInst.blocking = true;
```

#### 2.2.6 Mass Chill (script.massChill) -- `State.as:2454`

```as3
if (targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage)
    targetInst.blocking = false;
```

#### 2.2.7 Undo Mass Chill -- `State.as:2555`

```as3
if (targetInst.disruptDamage < targetInst.damageItCanTake + targetInst.damage)
    targetInst.blocking = true;
```

#### 2.2.8 Swoosh (Begin Turn) -- `State.as:2706`

```as3
inst.blocking = card.defaultBlocking;
```

Also: `State.as:3031` -- Glaciator sets all enemy blocking to `false`.

#### 2.2.9 State Reconstruction -- `State.as:3182, 3208, 3214, 3228, 3234`

Sets blocking from init data or derives from delay/buildTime status.

### 2.3 Deadness (`inst.deadness`)

AS3 has 9 deadness values (C.as:66-82): ALIVE, SELFSACCED, SACCED, BLOCKED, MELEED, WBO (breached), SNIPED, NETHERED (autosniped), AGED.

| Location | Function | Value | Purpose |
|---|---|---|---|
| Inst.as:86 | Constructor | `ALIVE` | Init |
| State.as:1463 | MOVE_ASSIGN (healthUsed=0) | `SELFSACCED` | Self-sac from health cost |
| State.as:1504 | MOVE_ASSIGN (SNIPE target) | `SNIPED` | Snipe kills |
| State.as:1516 | MOVE_ASSIGN (Comm Server) | `SNIPED` | Comm Server cascade |
| State.as:1545 | MOVE_UNASSIGN (healthUsed undo) | `ALIVE` | Undo self-sac |
| State.as:1595 | MOVE_UNASSIGN (undo SNIPE) | `ALIVE` | Undo snipe |
| State.as:1607 | MOVE_UNASSIGN (undo Comm Server) | `ALIVE` | Undo cascade |
| State.as:1677 | MOVE_MELEE | `MELEED` | Melee breach damage |
| State.as:1703 | MOVE_UNMELEE | `ALIVE` | Undo melee |
| State.as:1732 | MOVE_DEFEND | `BLOCKED` | Blocked to death |
| State.as:1761 | MOVE_UNDEFEND | `ALIVE` | Undo block |
| State.as:1800 | MOVE_BREACH_OR_OVERKILL | `WBO` | Breached to death |
| State.as:1833 | MOVE_UNBREACH_OR_UNOVERKILL | `ALIVE` | Undo breach |
| State.as:1868 | MOVE_WIPEOUT | `WBO` | Wipeout kills |
| State.as:1889 | MOVE_UNWIPEOUT | `ALIVE` | Undo wipeout |
| State.as:2042 | Swoosh (lifespan=0) | `AGED` | Lifespan expiry |
| State.as:2267 | sac() | `SACCED` | Sacrifice as cost |
| State.as:2284 | netherfy() | `NETHERED` | Netherfy destruction |
| State.as:2311 | unsac() | `ALIVE` | Undo sacrifice |
| State.as:2348 | unnetherfy() | `ALIVE` | Undo netherfy |
| State.as:2417 | runScriptForward (selfsac) | `SELFSACCED` | Script self-sac |
| State.as:2518 | runScriptBackward (selfsac) | `ALIVE` | Undo script self-sac |
| State.as:2690 | Swoosh (lifespan=0) | `AGED` | Alternate lifespan path |
| State.as:2903 | Swoosh (EMP) | `SELFSACCED` | EMP self-sacs |
| State.as:2909 | Swoosh (Deep Impact) | `SELFSACCED` | Deep Impact self-sacs |
| State.as:2985 | Swoosh (EMP effect) | `NETHERED` | EMP destroys enemy units |
| State.as:3003 | Swoosh (Deep Impact effect) | `NETHERED` | DI destroys enemy workers |
| State.as:3017 | Swoosh (A.R. Groans effect) | `NETHERED` | ARG destroys random enemy |
| State.as:3188-3200 | State reconstruction | Various | From save data |

### 2.4 Damage (`inst.damage`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Inst.as:88 | Constructor | `= 0` | Init |
| State.as:1676 | MOVE_MELEE | `+= health` | Melee damage |
| State.as:1702 | MOVE_UNMELEE | `-= health` | Undo melee |
| State.as:1725 | MOVE_DEFEND | `+= damage` | Block damage |
| State.as:1754 | MOVE_UNDEFEND | `-= damage` | Undo block |
| State.as:1793 | MOVE_BREACH_OR_OVERKILL | `+= damage` | Breach damage |
| State.as:1826 | MOVE_UNBREACH_OR_UNOVERKILL | `-= damage` | Undo breach |
| State.as:1863 | MOVE_WIPEOUT | `+= health` | Wipeout damage |
| State.as:1884 | MOVE_UNWIPEOUT | `-= damage` | Undo wipeout |
| State.as:2627 | Swoosh | `= 0` | Clear damage at turn start |

### 2.5 Disrupt/Chill (`inst.disruptDamage`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Inst.as:89 | Constructor | `= 0` | Init |
| State.as:1488 | MOVE_ASSIGN (disrupt) | `+= targetAmount` | Apply chill |
| State.as:1577 | MOVE_UNASSIGN (undisrupt) | `-= targetAmount` | Remove chill |
| State.as:2445 | runScriptForward (massChill) | `+= massChill` | Mass chill |
| State.as:2636 | Swoosh | `= 0` | Clear chill at turn start |

### 2.6 Health (`inst.health`)

| Location | Function | Change | Purpose |
|---|---|---|---|
| Inst.as:87 | Constructor | `= card.startingHealth` | Init |
| State.as:1455 | MOVE_ASSIGN | `-= healthUsed` | Ability health cost |
| State.as:1548 | MOVE_UNASSIGN | `+= healthUsed` | Undo health cost |
| State.as:1728 | MOVE_DEFEND (fragile) | `-= damage` | Fragile block damage |
| State.as:1757 | MOVE_UNDEFEND (fragile) | `+= damage` | Undo fragile block |
| State.as:1796 | MOVE_BREACH (fragile) | `-= damage` | Fragile breach damage |
| State.as:1829 | MOVE_UNBREACH (fragile) | `+= damage` | Undo fragile breach |
| State.as:1866 | MOVE_WIPEOUT (fragile) | `-= damage` | Fragile wipeout |
| State.as:1887 | MOVE_UNWIPEOUT (fragile) | `+= damage` | Undo fragile wipeout |
| State.as:2711-2714 | Swoosh | `+= healthGained` (capped at healthMax) | Turn regen |
| State.as:3239 | State reconstruction | `= initArray value` | From save data |
| State.as:3954-3957 | healAll action | `+= amount` (capped) | Special ability |

---

## 3. Cross-Reference Table

### 3.1 Status/Role Changes

| # | C++ Location | C++ Code | AS3 Equivalent | Notes |
|---|---|---|---|---|
| R1 | Card.cpp:53-67 (JSON ctor) | `m_status = Default/Assigned/Inert` from "role" | Inst.as:141-156 (JSON toy ctor) | Match. Both deserialize from same role strings. |
| R2 | Card.cpp:190,205 (Bought) | `m_status = Inert; m_sellable = true` | Inst.as:72 `role = ROLE_SELLABLE` | **Structural difference**: C++ uses `Inert + m_sellable`, AS3 has explicit `ROLE_SELLABLE`. Both serialize to "sellable". |
| R3 | Card.cpp:211 (AbilityScript) | `m_status = Inert` | Inst.as:76 `role = ROLE_INERT` | Match. |
| R4 | Card.cpp:217 (BuyScript) | `m_status = Inert` | Inst.as:76 `role = ROLE_INERT` | Match. |
| R5 | Card.cpp:225 (Manual) | `m_status = Default` (if hasAbility) | State.as:3213 `role = hasAbility ? DEFAULT : INERT` | Match. |
| R6 | Card.cpp:634-638 (beginTurn) | `Default` if hasAbility, else `Inert` | State.as:2700-2704 (swoosh) | Match. |
| R7 | Card.cpp:612 (beginTurn delayed) | `Inert` if delayed | State.as:2673 (swoosh delayed) | Match. |
| R8 | Card.cpp:798 (useAbility) | `Assigned` | State.as:1450 (MOVE_ASSIGN) | Match. |
| R9 | Card.cpp:760 (undoUseAbility) | `Default` | State.as:1538 (MOVE_UNASSIGN) | Match. |
| R10 | **GameState.cpp:1300-1304 (beginPhase Defense)** | **Default/Inert reset** | **NO AS3 EQUIVALENT** | **BUG. See Anomaly A1.** |
| R11 | -- | -- | State.as:2271 (sac: role = INERT) | **No direct C++ equivalent.** C++ kills card; doesn't set role to Inert on sac. See A2. |
| R12 | -- | -- | State.as:2316/2320 (unsac: role = DEFAULT/ASSIGNED) | **No direct C++ equivalent.** C++ revives via undoKill. See A2. |
| R13 | -- | -- | State.as:2652-2654 (swoosh: sellable->inert) | C++ handles via `m_sellable = false` in beginTurn. Functionally equivalent. |

### 3.2 Death/Alive Changes

| # | C++ Location | C++ Code | AS3 Equivalent | Notes |
|---|---|---|---|---|
| D1 | Card.cpp:516-518 (kill) | `m_dead=true, KilledThisTurn` | Various: SELFSACCED, SACCED, BLOCKED, MELEED, WBO, SNIPED, NETHERED, AGED | **Structural difference**: C++ has 1 dead state + causeOfDeath enum; AS3 has 8 distinct deadness values. Same semantics. |
| D2 | Card.cpp:586-590 (beginTurn) | `KilledThisTurn -> Dead` | State.as:2566-2580 (collectBodies: deleteInst) | C++ transitions status; AS3 removes from table entirely. |
| D3 | Card.cpp:892-898 (undoKill) | `Alive, dead=false` | Various `DEADNESS_ALIVE` assignments | Match. |
| D4 | Card.cpp:599 (lifespan=0 kill) | `kill(Lifespan)` | State.as:2690 `DEADNESS_AGED` | Match. |

### 3.3 Health Changes

| # | C++ | AS3 | Notes |
|---|---|---|---|
| H1 | Card.cpp:625-628 (beginTurn healthGained) | State.as:2711-2714 (swoosh healthGained) | Match. |
| H2 | Card.cpp:791 (useAbility healthUsed) | State.as:1455 (MOVE_ASSIGN healthUsed) | Match. |
| H3 | Card.cpp:752 (undoUseAbility) | State.as:1548 (MOVE_UNASSIGN) | Match. |
| H4 | Card.cpp:397-428 (takeDamage) | State.as:1724-1728 (DEFEND), 1792-1796 (BREACH) | Match, but AS3 has more detailed damage tracking (inst.damage field). |

### 3.4 Chill Changes

| # | C++ | AS3 | Notes |
|---|---|---|---|
| C1 | Card.cpp:435 (applyChill) | State.as:1488 (+= targetAmount) | Match. |
| C2 | Card.cpp:442 (removeChill) | State.as:1577 (-= targetAmount) | Match. |
| C3 | Card.cpp:641 (beginTurn chill=0) | State.as:2636 (swoosh disruptDamage=0) | Match. |
| C4 | -- | State.as:2445 (massChill) | **No C++ equivalent.** C++ doesn't implement massChill script effect. See A3. |

### 3.5 Blocking Changes

| # | C++ | AS3 | Notes |
|---|---|---|---|
| B1 | Card.cpp:486 canBlock() checks status | State.as:1451 `blocking = card.assignedBlocking` | **Structural difference**: C++ derives blocking from status at query time; AS3 stores explicit `blocking` bool on each state change. |
| B2 | -- | State.as:2706 `blocking = card.defaultBlocking` (swoosh) | C++ equivalent: Card.cpp:634 sets status to Default, then canBlock() derives blocking. |
| B3 | -- | State.as:1497 `blocking = false` (frozen by chill) | C++ equivalent: `Card::isFrozen()` returns `chill >= health`, checked in `canBlock()`. |
| B4 | -- | State.as:3031 `blocking = false` (Glaciator) | **No C++ equivalent.** Glaciator not implemented in C++. |

---

## 4. Anomalies

### A1: Defense Phase Status Reset (C++ ONLY) -- **HIGH RISK / CONFIRMED BUG**

**C++ (GameState.cpp:1289-1307)**: Resets ALL card statuses to Default/Inert at the start of Defense phase.

**AS3**: No role changes occur when transitioning to defense phase. The `MOVE_DEFEND` and `MOVE_UNDEFEND` handlers (State.as:1712-1777) do NOT modify `inst.role` -- they only modify `inst.damage`, `inst.health` (fragile), and `inst.deadness`.

**Impact**: In C++, a Drone that used its ability (status=Assigned) gets reset to Inert before Defense, then `canBlock()` is checked with `CardType::canBlock(false)` (not assigned). Since Drone has `defaultBlocking=true`, it becomes eligible to block. In AS3, the Drone retains `role=ASSIGNED` and `blocking=card.assignedBlocking` (which is `false` for Drone) -- so it cannot block.

This is the known defense-reset bug from commit `5bf57a8`.

### A2: Sac Role Change (AS3 ONLY) -- **LOW RISK**

**AS3 (State.as:2267-2271)**: When a card is sacrificed, AS3 sets:
- `deadness = DEADNESS_SACCED`
- `role = C.ROLE_INERT` (only for ability-having cards)

**C++**: The `killCardByID(sacID, CauseOfDeath::AbilitySacCost)` call in `GameState::runScript` (line 937) calls `Card::kill()` which sets `m_dead=true` and `m_aliveStatus=KilledThisTurn`. The status (`m_status`) is NOT modified. The card is then moved to the killed cards list.

**Assessment**: Functionally equivalent. In C++, once a card is killed, its status becomes irrelevant (it's in the killed list). In AS3, cards remain in the `table` dict until `collectBodies` removes them. The role change to Inert is needed in AS3 to prevent the sacced card from appearing as clickable. No behavioral divergence.

### A3: Mass Chill Script Effect (AS3 ONLY) -- **LOW RISK**

**AS3 (State.as:2438-2460)**: `script.massChill` applies chill to ALL enemy blocking units and updates `blocking = false` when fully frozen.

**C++**: No `massChill` implementation found in `GameState::runScript`. The C++ engine likely handles mass chill through individual chill applications or doesn't implement this card mechanic.

**Assessment**: Only affects specific cards (e.g., "Centurion"). If C++ doesn't have these cards in the game set, this is benign.

### A4: Glaciator Effect (AS3 ONLY) -- **LOW RISK**

**AS3 (State.as:3024-3033)**: Glaciator ("Icy Savior") sets all enemy `blocking = false` during swoosh.

**C++**: No Glaciator-specific logic found in `Card::beginTurn()` or `GameState::beginTurn()`.

**Assessment**: Card-specific mechanic. Only matters if Glaciator is in the game set.

### A5: EMP / Deep Impact / A.R. Groans (AS3 ONLY) -- **LOW RISK**

**AS3 (State.as:2900-3022)**: Special begin-of-turn effects:
- EMP: Self-sacs, destroys all enemy units with `attackPotential != 0`
- Deep Impact: Self-sacs, destroys all enemy workers
- A.R. Groans: Destroys random enemy unit with `health <= 8`

**C++**: These are handled through `beginOwnTurnScript` in C++ (the generic script runner). The C++ approach is data-driven (from `cardLibrary.jso`), while AS3 hard-codes card names. Functionally equivalent as long as card data matches.

### A6: Comm Server Cascade Snipe (AS3 ONLY) -- **LOW RISK**

**AS3 (State.as:1510-1524)**: When Comm Server is sniped, ALL other `COLOR_BLACK` units are also set to `DEADNESS_SNIPED`.

**C++**: No Comm Server special-casing found. This would need to be in the destroy/snipe script in `cardLibrary.jso`.

**Assessment**: Card-specific mechanic, handled through data in C++.

### A7: `inst.damage` field vs C++ `m_damageTaken` -- **INFORMATIONAL**

**AS3**: `inst.damage` accumulates damage taken and is cleared at swoosh (`damage = 0`). It is used during the turn for UI and to determine `damageItCanTake`.

**C++**: `m_damageTaken` tracks damage for the current damage event (single block/breach), reset in `beginTurn()`. Non-fragile cards don't reduce `m_currentHealth` from block/breach damage; fragile cards do.

**Assessment**: Different tracking models but equivalent behavior. Both engines correctly handle fragile vs non-fragile damage.

### A8: Missing Fallthrough in AS3 Init Deadness Switch -- **MEDIUM RISK / LIKELY AS3 BUG**

**AS3 (State.as:3184-3201)**:
```as3
case "dead":
    switch(initArray[i][k + 1]) {
        case "alive":    inst.deadness = C.DEADNESS_ALIVE;      // NO break!
        case "selfsacced": inst.deadness = C.DEADNESS_SELFSACCED; // NO break!
        case "sacced":   inst.deadness = C.DEADNESS_SACCED;      // NO break!
        case "blocked":  inst.deadness = C.DEADNESS_BLOCKED;     // NO break!
        case "meleed":   inst.deadness = C.DEADNESS_MELEED;      // NO break!
        case "wbo":      inst.deadness = C.DEADNESS_WBO;         // NO break!
        case "sniped":   inst.deadness = C.DEADNESS_SNIPED;      // last case
    }
```

**This appears to be a switch fallthrough bug in AS3**: Every case falls through to the next, meaning any deadness value would end up as `DEADNESS_SNIPED`. Since "alive" falls through ALL cases, a card marked "alive" in init data would be set to `SNIPED`.

**C++ (Card.cpp:119-157)**: Uses `if/else if` chain with proper separation. No fallthrough possible.

**Assessment**: This could be a decompiler artifact (real AS3 may have breaks that the decompiler missed), or it could be a genuine bug that only triggers during state reconstruction from specific init data. In normal gameplay, the swoosh initializes cards properly, so this path is rarely hit. **Low practical impact but worth noting.**

### A9: Sellable Handling Difference -- **INFORMATIONAL**

**C++**: Has 3 statuses (Default, Assigned, Inert) + a separate `m_sellable` bool. "Sellable" = `Inert + m_sellable=true`.

**AS3**: Has 4 roles (Default, Assigned, Sellable, Inert). "Sellable" is a first-class role.

Both serialize/deserialize using `"role":"sellable"`. The difference is purely structural -- both engines agree on when a card is sellable and serialize identically.

---

## 5. Risk Assessment

### Critical (Confirmed Bug)

| ID | Anomaly | Risk | Action |
|---|---|---|---|
| **A1** | Defense phase status reset (C++ only) | **CRITICAL** | Remove GameState.cpp:1289-1307. This is the known bug from commit 5bf57a8. Affects ALL 722K self-play games. |

### Medium (Needs Investigation)

| ID | Anomaly | Risk | Action |
|---|---|---|---|
| **A8** | AS3 init deadness switch fallthrough | **MEDIUM** | Verify whether decompiler strips `break` statements. If real bug, only affects state reconstruction from save data (rare path). |

### Low (Intentional Differences)

| ID | Anomaly | Risk | Action |
|---|---|---|---|
| A2 | Sac role change (AS3 only) | LOW | Functionally equivalent. Different data models. |
| A3 | Mass chill (AS3 only) | LOW | Card-specific mechanic not in C++ game set. |
| A4 | Glaciator (AS3 only) | LOW | Card-specific mechanic not in C++ game set. |
| A5 | EMP/DI/ARG hard-coding (AS3 only) | LOW | C++ uses data-driven scripts. |
| A6 | Comm Server cascade (AS3 only) | LOW | C++ uses data-driven scripts. |
| A7 | Damage tracking model difference | INFO | Structurally different, behaviorally identical. |
| A9 | Sellable as 4th role vs bool flag | INFO | Structurally different, serialize identically. |

### Summary

The comprehensive scan found **1 confirmed bug** (A1: defense phase reset), **1 potential AS3 bug** (A8: switch fallthrough in init), and **7 intentional structural differences** between the engines. The only status change in C++ that has NO counterpart in AS3 is the defense phase reset (A1), which is the already-known bug. All other C++ status changes have clear AS3 equivalents, and the additional AS3-only changes are either card-specific mechanics (handled data-driven in C++) or structural modeling differences with equivalent behavior.

---

## Appendix: Complete File Reference

**C++ files scanned:**
- `source/engine/Card.h` -- Field declarations, method signatures
- `source/engine/Card.cpp` -- All Card member mutations
- `source/engine/CardType.h` -- CardStatus enum (Default=0, Assigned=1, Inert=2)
- `source/engine/Constants.h` -- Phases enum (Action, Defense, Breach, Confirm, Swoosh)
- `source/engine/GameState.h` -- GameState fields (m_targetAbilityCardID, etc.)
- `source/engine/GameState.cpp` -- All GameState-level card mutations
- `source/engine/CardData.cpp` -- killCardByID, undoKill (delegates to Card methods)

**AS3 files scanned:**
- `prismata_decompiled/scripts/mcds/engine/C.as` -- Constants (ROLE_*, DEADNESS_*, PHASE_*)
- `prismata_decompiled/scripts/mcds/engine/Inst.as` -- Instance fields, constructor, getters (dead, damageItCanTake)
- `prismata_decompiled/scripts/mcds/engine/State.as` -- All game state mutations (move handlers, swoosh, scripts)
- `prismata_decompiled/scripts/mcds/engine/StateHelper.as` -- Defense calculations (read-only)
- `prismata_decompiled/scripts/mcds/engine/Controller.as` -- UI/input layer (read-only checks)
- `prismata_decompiled/scripts/mcds/engine/EndTurnObject.as` -- End-turn animations (read-only checks)
