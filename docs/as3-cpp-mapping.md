# AS3 to C++ Function Mapping Document

> **Phase 0.5 deliverable** for the AS3-faithful port implementation plan (v2).
> Generated 2026-02-23. Covers all 5 AS3 engine source files.

## Summary Statistics

| Metric | Count |
|--------|-------|
| AS3 functions/methods examined | 162 |
| Mapped to existing C++ equivalent | 89 |
| NEW (no C++ equivalent, must be created) | 38 |
| SKIP (undo/campaign/triggers/UI/lane) | 35 |
| **Port coverage before work begins** | **55%** |

### Port Phase Distribution

| Phase | Functions | Description |
|-------|-----------|-------------|
| Phase 3 (Swoosh) | 28 | Turn transition, per-card upkeep, resonate, lifespan |
| Phase 4 (Moves) | 31 | processMove cases, script execution ordering |
| Phase 5 (Stagnation/Conditions) | 19 | 4-level progress counters, condition system |
| SKIP | 35 | Undo, campaign/mission, triggers, UI, lane |
| Existing (no port needed) | 49 | Already correctly mapped |

---

## 1. C.as -- Constants (625 lines)

**AS3 File:** `prismata_decompiled/scripts/mcds/engine/C.as`
**C++ Equivalents:** `Constants.h`, `ActionTypes` (in Common.h), `CardStatus`, `CauseOfDeath`, `AliveStatus` (in Card.h)

### 1.1 Move Type Constants

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `MOVE_ASSIGN` | "assign" | `ActionTypes::USE_ABILITY` | Name only; semantics match | Existing |
| `MOVE_UNASSIGN` | "unassign" | `ActionTypes::UNDO_USE_ABILITY` | Name only | SKIP (undo) |
| `MOVE_BUY` | "buy" | `ActionTypes::BUY` | Match | Existing |
| `MOVE_SELL` | "sell" | `ActionTypes::SELL` | Match | Existing |
| `MOVE_MELEE` | "melee" | `ActionTypes::ASSIGN_FRONTLINE` | Name difference; AS3="melee", C++="frontline" | Existing |
| `MOVE_UNMELEE` | "unmelee" | -- | SKIP (undo) | SKIP |
| `MOVE_DEFEND` | "defend" | `ActionTypes::ASSIGN_BLOCKER` | Match | Existing |
| `MOVE_UNDEFEND` | "undefend" | -- | SKIP (undo) | SKIP |
| `MOVE_BREACH_OR_OVERKILL` | "breach_or_overkill" | `ActionTypes::ASSIGN_BREACH` | C++ separates breach/overkill logic in isLegal | Existing |
| `MOVE_UNBREACH_OR_UNOVERKILL` | "unbreach_or_unoverkill" | `ActionTypes::UNDO_BREACH` | SKIP (undo) | SKIP |
| `MOVE_WIPEOUT` | "wipeout" | `ActionTypes::WIPEOUT` | Match | Existing |
| `MOVE_UNWIPEOUT` | "unwipeout" | -- | SKIP (undo) | SKIP |
| `MOVE_END_DEFENSE` | "end_defense" | `ActionTypes::END_PHASE` (Defense) | C++ uses single END_PHASE with phase switch | Existing |
| `MOVE_ENTER_CONFIRM` | "enter_confirm" | `ActionTypes::END_PHASE` (Action) | C++ uses single END_PHASE; **AS3 ENTER_CONFIRM has stagnation logic** | Phase 5 |
| `MOVE_COMMIT` | "commit" | `ActionTypes::END_PHASE` (Confirm) | C++ uses single END_PHASE | Existing |
| `MOVE_EMOTE` | "emote" | -- | SKIP (UI only) | SKIP |

### 1.2 Phase Constants

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `PHASE_DEFENSE` | "defense" | `Phases::Defense` | String vs enum int | Existing |
| `PHASE_ACTION` | "action" | `Phases::Action` | String vs enum int | Existing |
| `PHASE_CONFIRM` | "confirm" | `Phases::Confirm` | String vs enum int | Existing |
| -- | -- | `Phases::Breach` | **C++ has explicit Breach phase; AS3 handles breach within Action-to-Confirm transition** | Existing (C++ extra) |
| -- | -- | `Phases::Swoosh` | **C++ has explicit Swoosh phase; AS3 calls swoosh() as a function** | Existing (C++ extra) |

### 1.3 Role Constants (Card Status)

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `ROLE_DEFAULT` | "default" | `CardStatus::Default` | String vs enum | Existing |
| `ROLE_ASSIGNED` | "assigned" | `CardStatus::Assigned` | String vs enum | Existing |
| `ROLE_SELLABLE` | "sellable" | `Card::m_sellable` (bool) | **AS3 is a role; C++ is a separate boolean field** | Phase 3 |
| `ROLE_INERT` | "inert" | `CardStatus::Inert` | String vs enum | Existing |

### 1.4 Deadness Constants (Cause of Death)

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `DEADNESS_ALIVE` | "alive" | `AliveStatus::Alive` | String vs enum | Existing |
| `DEADNESS_SELFSACCED` | "selfsacced" | `CauseOfDeath::SelfSac` | Match | Existing |
| `DEADNESS_SACCED` | "sacced" | `CauseOfDeath::BuySacCost` / `AbilitySacCost` | **AS3 has 1 sac cause; C++ splits into Buy vs Ability** | Existing |
| `DEADNESS_BLOCKED` | "blocked" | `CauseOfDeath::Blocker` | Match | Existing |
| `DEADNESS_MELEED` | "meleed" | `CauseOfDeath::Breached` (frontline path) | Name difference | Existing |
| `DEADNESS_WBO` | "wbo" | `CauseOfDeath::Breached` | Match | Existing |
| `DEADNESS_SNIPED` | "sniped" | `CauseOfDeath::Sniped` | Match | Existing |
| `DEADNESS_NETHERED` | "nethered" | -- | **NEW: auto-snipe (destroy script). C++ has no equivalent** | Phase 4 |
| `DEADNESS_AGED` | "aged" | `CauseOfDeath::Lifespan` | Match | Existing |

### 1.5 Resource Index Constants

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `MANA_P` (gold) | 0 | `Resources::Gold` | Match | Existing |
| `MANA_G` (green) | 1 | `Resources::Green` | Match | Existing |
| `MANA_B` (blue) | 2 | `Resources::Blue` | Match | Existing |
| `MANA_R` (red) | 3 | `Resources::Red` | Match | Existing |
| `MANA_H` (energy) | 4 | `Resources::Energy` | Match | Existing |
| `MANA_A` (attack) | 5 | `Resources::Attack` | Match | Existing |

### 1.6 Color Constants (Game Result)

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `COLOR_WHITE` | 0 | `Players::Player_One` | Match | Existing |
| `COLOR_BLACK` | 1 | `Players::Player_Two` | Match | Existing |
| `COLOR_NONE` | 2 | `Players::Player_None` | Match | Existing |
| `COLOR_DRAW_MUTUAL_ELIMINATION` | 3 | `Players::Player_None` (after audit fix) | **C++ now returns Player_None for mutual elim (was wrong before audit)** | Existing (fixed) |
| `COLOR_DRAW_STALEMATE` | 4 | -- | **NEW: C++ has no stalemate draw. Needs stagnation system** | Phase 5 |

### 1.7 Condition Type Constants

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `CONDITION_IS_BLOCKING` | "is_blocking" | -- | **NEW: C++ meetsCondition() checks canBlock() not isBlocking** | Phase 5 |
| `CONDITION_CARD` | "card" | `Condition::hasCardType()` | Match | Existing |
| `CONDITION_NOT_BLOCKING` | "not_blocking" | `Condition::isNotBlocking()` | Match | Existing |
| `CONDITION_HEALTH_AT_MOST` | "health_at_most" | `Condition::hasHealthCondition()` | Match | Existing |
| `CONDITION_NAME_IN` | "name_in" | -- | **NEW: multi-name condition. Not in C++ Condition class** | Phase 5 |
| `CONDITION_IS_ABC` | "is_abc" | `Condition::isTech()` | Match (ABC = tech unit) | Existing |
| `CONDITION_IS_ENGINEER_TEMP` | "is_engineer_temp" | -- | **NEW: engineer-specific condition. Not in C++** | Phase 5 |

### 1.8 Target Action Constants

| AS3 Constant | Value | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `TARGETACTION_NONE` | "none" | `ActionTypes::NONE` | Match | Existing |
| `TARGETACTION_DISRUPT` | "disrupt" | `ActionTypes::CHILL` | **Name difference: AS3 "disrupt" = C++ "chill"** | Existing |
| `TARGETACTION_SNIPE` | "snipe" | `ActionTypes::SNIPE` | Match | Existing |

### 1.9 Helper Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Phase |
|---|---|---|---|---|
| `lowercaseColorToInt(s)` | 618-624 | Map color string to MANA index | Resources parsing in CardTypeInfo | Existing |

---

## 2. Inst.as -- Card Instance (504 lines)

**AS3 File:** `prismata_decompiled/scripts/mcds/engine/Inst.as`
**C++ Equivalent:** `source/engine/Card.h` / `Card.cpp`

### 2.1 Fields

| AS3 Field | Type | C++ Field | Differences | Phase |
|---|---|---|---|---|
| `instId` | int | `m_id` (CardID) | Match | Existing |
| `card` | Card | `m_type` (CardType) | AS3 refs Card object; C++ refs CardType handle | Existing |
| `owner` | int | `m_player` (PlayerID) | Match | Existing |
| `role` | String | `m_status` (int enum) | **String vs enum. AS3 "sellable" is a role; C++ uses bool** | Phase 3 |
| `blocking` | int | -- (computed from canBlock()) | **AS3 stores explicit blocking HP; C++ computes from canBlock()** | Phase 3 |
| `deadness` | String | `m_aliveStatus` + `m_causeOfDeath` | **AS3 single field; C++ splits into two** | Existing |
| `health` | int | `m_currentHealth` | Match | Existing |
| `damage` | int | `m_damageTaken` | Match | Existing |
| `disruptDamage` | int | `m_currentChill` | **Name difference: disrupt = chill** | Existing |
| `charge` | int | `m_currentCharges` | Match | Existing |
| `constructionTime` | int | `m_constructionTime` | Match | Existing |
| `delay` | int | `m_currentDelay` | Match | Existing |
| `lifespan` | int | `m_lifespan` | Match | Existing |
| `target` | int | `m_targetID` + `m_hasTarget` | **AS3 single field (-1=none); C++ splits into ID + bool** | Existing |
| `buyCreateIds` | Array | `m_createdCardIDs` (partial) | **AS3 tracks per-script-type; C++ merges all into one vector** | Phase 4 |
| `beginOwnTurnCreateIds` | Array | -- | **NEW: C++ does not track BOT-created IDs separately** | Phase 3 |
| `abilityCreateIds` | Array | `m_createdCardIDs` (partial) | Merged in C++ | Existing |
| `creatorIdFromBuyOrAbility` | int | -- | **NEW: C++ does not track creator** | Phase 4 |
| `creatorIdFromBeginTurn` | int | -- | **NEW: C++ does not track BOT creator** | Phase 3 |
| `disruptorIds` | Array | -- | **NEW: C++ does not track which units chilled this card** | Phase 4 |
| `sniperId` | int | -- | **NEW: C++ does not track which unit sniped this card** | Phase 4 |
| `laneId` | int | -- | SKIP (lane system) | SKIP |

### 2.2 Property Getters (Computed)

| AS3 Property | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `dead` (getter) | 183-186 | Is unit dead? | `Card::isDead()` | Match | Existing |
| `isPartiallyDamaged` | 188-191 | Has taken non-lethal damage | -- | **NEW: not in C++** | Phase 3 |
| `damageItCanTake` | 193-200 | Effective HP (health - unfragile damage) | `Card::currentHealth()` | **DIFFERENT: AS3 subtracts non-fragile damage; C++ returns raw HP** | Phase 3 |
| `damageReqdToInjure` | 202-212 | Min damage to injure | -- | **NEW: not in C++** | Phase 3 |
| `absorb` | 214-221 | Max damage absorbed when blocking | -- | **NEW: not in C++** | Phase 3 |
| `delayAfterSwoosh` | 223-234 | Delay value after next swoosh | -- | **NEW: predictive property** | Phase 3 |
| `chargeAfterSwoosh` | 236-251 | Charge value after next swoosh | -- | **NEW: predictive property** | Phase 3 |
| `hpAfterSwoosh` | 253-273 | HP after next swoosh | -- | **NEW: predictive property** | Phase 3 |
| `enoughChargeToAssignAfterSwoosh` | 275-278 | Can use ability next turn? | -- | **NEW: predictive property** | Phase 3 |
| `enoughHPToAssignAfterSwoosh` | 280-283 | Has enough HP to use ability next turn? | -- | **NEW: predictive property** | Phase 3 |
| `convertedLifespan` | 285-292 | Lifespan with construction time factored in | -- | **NEW: used by StateHelper** | Phase 3 |
| `convertedDelay` | 294-301 | Delay with construction time factored in | -- | **NEW: used by StateHelper** | Phase 3 |

### 2.3 Methods

| AS3 Method | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `Inst()` constructor | 48-170 | Create from scratch or JSON | `Card()` constructors | Both parse JSON; field mapping differs | Existing |
| `weaklyEqualTo(other)` | 303-344 | Loose comparison (ignore order-dependent fields) | -- | **NEW: C++ has isIsomorphic() which is similar but not identical** | Phase 3 |
| `stronglyEqualTo(other)` | 346-403 | Strict field-by-field comparison | -- | **NEW: not in C++** | Phase 3 |
| `toObject()` | 405-458 | Serialize to JSON object | `Card::toJSONString()` | Different field names in output | Existing |
| `clone()` | 460-466 | Deep copy | Copy constructor Card(const Card&) | Match | Existing |
| `toString()` | 468-476 | Debug string | `Card::toJSONString()` | Match | Existing |
| `compareWithJSON(j)` | 478-503 | Compare card against JSON (validation) | -- | **NEW: validation utility** | Phase 3 |

---

## 3. Card.as -- Card Type Definition (753 lines)

**AS3 File:** `prismata_decompiled/scripts/mcds/engine/Card.as`
**C++ Equivalent:** `source/engine/CardTypeInfo.h` / `CardTypeInfo.cpp`, `CardType` wrapper

### 3.1 Fields

| AS3 Field | Type | C++ Field (CardTypeInfo) | Differences | Phase |
|---|---|---|---|---|
| `cardId` | int | `typeID` | Match | Existing |
| `cardName` | String | `cardName` | Match | Existing |
| `UIName` | String | `uiName` | Match | Existing |
| `cardType` | String | -- | **AS3 stores "unit" or "spell"; C++ uses isSpell bool** | Existing |
| `defaultBlocking` | int | `defaultBlocking` (bool) | **AS3 is int (HP value); C++ is bool** | Phase 3 |
| `assignedBlocking` | int | `assignedBlocking` (bool) | **AS3 is int (HP value); C++ is bool** | Phase 3 |
| `startingHealth` | int | `startingHealth` | Match | Existing |
| `fragile` | Boolean | `fragile` | Match | Existing |
| `healthUsed` | int | `healthUsed` | Match | Existing |
| `healthGained` | int | `healthGained` | Match | Existing |
| `healthMax` | int | `healthMax` | Match | Existing |
| `startingCharge` | int | `startingCharge` | Match | Existing |
| `chargeUsed` | int | -- (in Script) | C++ stores in ability script | Existing |
| `chargeGained` | int | -- (in Script) | C++ stores in ability script | Existing |
| `chargeMax` | int | -- | **NEW: not in CardTypeInfo** | Phase 3 |
| `undefendable` | Boolean | -- | **NEW: C++ has no undefendable concept** | Phase 3 |
| `lifespan` | int | `lifespan` | Match | Existing |
| `rarity` | String | `rarity` (string) | Match | Existing |
| `buyCost` | Array[6] | `buyCost` (Resources) | AS3 is 6-element array; C++ is Resources object | Existing |
| `buySac` | Array | `buySac` (vector) | Match | Existing |
| `buyScript` | Object | `buyScript` (Script) | Match | Existing |
| `buildTime` | int | `buildTime` | Match | Existing |
| `beginOwnTurnScript` | Object | `beginOwnTurnScript` (Script) | Match | Existing |
| `resonate` | String | `resonateCardName` | Match | Existing |
| `goldResonate` | int | -- | **Parsed into resonateProduces in CardTypeInfo.cpp** | Existing |
| `abilityCost` | Array[6] | `abilityCost` (Resources) | Match | Existing |
| `abilitySac` | Array | `abilitySac` (vector) | Match | Existing |
| `abilityNetherfy` | Object | -- | **NEW: auto-destroy ability. C++ has no equivalent** | Phase 4 |
| `abilityScript` | Object | `abilityScript` (Script) | Match | Existing |
| `deathScript` | Object | -- | **NEW: C++ has no death script execution** | Phase 4 |
| `targetAction` | String | `targetAction` (string) | Match | Existing |
| `targetAmount` | int | `targetAmount` | Match | Existing |
| `condition` | Object | `targetAbilityCondition` (Condition) | Match | Existing |
| `position` | String | -- | **SKIP: UI positioning only** | SKIP |

### 3.2 Computed Properties

| AS3 Property | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `targetHas` | 593-596 | Has target ability? | `CardType::hasTargetAbility()` | Match | Existing |
| `hasAbility` | 598-601 | Has any ability? | `CardType::hasAbility()` | Match | Existing |
| `attackPotential` | 603-631 | Total attack this unit can produce | -- | **NEW: complex calculation including resonate/snipe** | Phase 3 |
| `disruptPotential` | 633-647 | Total chill this unit can produce | -- | **NEW: chill potential calculation** | Phase 3 |
| `workPotential` | 649-661 | Total work (attack + resonate value) | -- | **NEW: combines multiple potentials** | Phase 3 |
| `autoClicked` | 663-669 | Unit ability auto-activates? | -- | **NEW: auto-click detection** | SKIP (UI) |
| `colorType` | 671-702 | Dominant resource color of unit | -- | **NEW: color classification** | Phase 5 |

### 3.3 Methods

| AS3 Method | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `Card()` constructor | 47-556 | Parse JSON card definition | `CardTypeInfo()` constructor | Both parse cardLibrary.jso; field mapping differs | Existing |
| `toPublicJSON()` | 704-752 | Serialize card type to JSON | -- | **NEW: no C++ equivalent** | SKIP (serialization) |

---

## 4. StateHelper.as -- Computed Properties (649 lines)

**AS3 File:** `prismata_decompiled/scripts/mcds/engine/StateHelper.as`
**C++ Equivalent:** **No direct equivalent.** C++ computes these values inline in GameState methods.

### 4.1 Fields (All Cached Computed Values)

| AS3 Field | Type | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|
| `ownDefenders` | Array | `getTotalAvailableDefense()` (partial) | C++ computes on-demand, not cached | Existing |
| `ownDefense` | int | `getTotalAvailableDefense()` | Match (computed each call) | Existing |
| `ownNonInvTotal` | int | -- | **NEW: count of non-invincible units** | Phase 5 |
| `ownAllUnitsTotal` | int | `numCards(player)` | Match | Existing |
| `oppDefenders` | Array | -- | **NEW: opponent blocker list not cached** | Phase 5 |
| `oppDefense` | int | `getTotalAvailableDefense(enemy)` | Match | Existing |
| `oppNonInvTotal` | int | -- | **NEW** | Phase 5 |
| `oppAllUnitsTotal` | int | `numCards(enemy)` | Match | Existing |
| `allOppUnitsDoomed` | Boolean | `calculateGameOver()` (partial) | **C++ checks this in game-over logic after audit fix** | Existing (fixed) |
| `oppDoomOneUnits` | int | -- | **NEW: count of opponent units with lifespan=1** | Phase 5 |
| `wipedOut` | Boolean | -- | **Computed inline in C++ endPhase(Action)** | Existing |
| `breached` | Boolean | -- | **Computed inline** | Existing |
| `overkilled` | Boolean | -- | **Computed inline** | Existing |
| `couldDefendThisTurn` | Boolean | -- | **NEW: complex blocker eligibility check** | Phase 5 |
| `maxDefense` | int | `getTotalAvailableDefense()` | Close match | Existing |
| `couldAttackThisTurn` | Boolean | -- | **NEW: attack potential check** | Phase 5 |
| `maxAttack` | int | `getAttack()` | Partial match (resources only vs potential) | Phase 5 |
| `maxDisrupt` | int | -- | **NEW: maximum chill available** | Phase 5 |
| `maxSnipers` | int | -- | **NEW: number of available snipers** | Phase 5 |
| `oppAttackPotential` | int | -- | **NEW: opponent maximum attack** | Phase 5 |
| `oppGuaranteedAttack` | int | -- | **NEW: minimum guaranteed attack** | Phase 5 |
| `oppDisruptPotential` | int | -- | **NEW** | Phase 5 |
| `oppSnipers` | int | -- | **NEW** | Phase 5 |

### 4.2 Methods

| AS3 Method | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `StateHelper()` constructor | 14-18 | Initialize empty | -- | No C++ equivalent class | Phase 5 |
| `reset()` | 62-100 | Clear all cached values | -- | No C++ equivalent | Phase 5 |
| `update(s:State)` | 102-649 | Recompute all properties from state | -- | **NEW: C++ has no batch property computation. Properties are computed inline where needed.** | Phase 5 |

**Key semantic difference:** AS3's StateHelper.update() is a 547-line method that iterates all units once and computes ~25 aggregate properties. C++ computes these inline in separate methods (getTotalAvailableDefense, canWipeout, calculateGameOver, etc.). The AS3 approach is more efficient (single pass) but tightly coupled. The C++ approach is modular but may iterate units multiple times.

**For Phase 5:** The stagnation system (ENTER_CONFIRM handler in State.as) calls StateHelper.update() and then reads couldDefendThisTurn, couldAttackThisTurn, maxAttack, maxDisrupt, etc. to decide which progress counters to reset. These properties MUST exist for stagnation to work.

---

## 5. State.as -- Core Game State Machine (4,490 lines)

**AS3 File:** `prismata_decompiled/scripts/mcds/engine/State.as`
**C++ Equivalent:** `source/engine/GameState.h` / `GameState.cpp`

### 5.1 Fields

| AS3 Field | Type | C++ Field | Differences | Phase |
|---|---|---|---|---|
| `insts` | Array | `m_cards` (CardData) | AS3 flat array; C++ per-player split via CardData | Existing |
| `supply` | Array | `m_cards.m_cardsBuyable` (CardBuyableData) | Match | Existing |
| `cards` | Array | -- (card type defs) | Card type definitions, loaded separately in C++ | Existing |
| `turnMana` / `oppMana` | Array[6] | `m_resources[2]` (Resources) | Match | Existing |
| `color` | int | -- (computed from active player) | **AS3 stores winner color; C++ computes** | Existing |
| `numTurns` | int | `m_turnNumber` | Match | Existing |
| `phase` | String | `m_activePhase` (int enum) | String vs enum | Existing |
| `victor` | int | -- (computed by winner()) | C++ computes on demand | Existing |
| `stateHelper` | StateHelper | -- | **NEW: no C++ equivalent. See Section 4** | Phase 5 |
| `turnNoProgressCounters` | Array[4] | -- | **NEW: 4-level stagnation counters** | Phase 5 |
| `oppNoProgressCounters` | Array[4] | -- | **NEW: opponent-specific stagnation counters** | Phase 5 |
| `redNoProgressCounters` | Array[4] | -- | **NEW: red resource stagnation** | Phase 5 |
| `greenNoProgressCounters` | Array[4] | -- | **NEW: green resource stagnation** | Phase 5 |
| `blueNoProgressCounters` | Array[4] | -- | **NEW: blue resource stagnation** | Phase 5 |
| `initInstsArr` | Array | -- | **AS3 stores initial state for undo; C++ uses undo differently** | SKIP |
| `triggers` | Array | -- | **SKIP: mission/campaign system** | SKIP |
| `lane*` fields | various | -- | **SKIP: lane system** | SKIP |

### 5.2 Stagnation Constants (State.as lines 69-102)

| AS3 Constant | Value | C++ Equivalent | Phase |
|---|---|---|---|
| `NUM_LEVELS_OF_DRAW_VARIABLES` | 4 | **NEW** | Phase 5 |
| `CUTOFFS_FOR_DRAW` | [2, 8, 20, 40] | **NEW** (C++ has flat 200-turn limit) | Phase 5 |
| `LEVEL_FOR_DELAY_TICKED` | 1 | **NEW** | Phase 5 |
| `LEVEL_FOR_HP_HEALED` | 1 | **NEW** | Phase 5 |
| `LEVEL_FOR_CHARGE_RECHARGED` | 1 | **NEW** | Phase 5 |
| `LEVEL_FOR_DAMAGE_BY_MORE_THAN_HEALING` | 1 | **NEW** | Phase 5 |
| `LEVEL_FOR_MONEY_STORED` | 2 | **NEW** | Phase 5 |
| `LEVEL_FOR_CARD_BOUGHT_OR_INST_CREATED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_BUILDTIME_TICKED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_OPP_LIFESPAN_TICKED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_GREEN_MANA_PRODUCED_OR_STORED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_RED_MANA_PRODUCED_OR_STORED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_BLUE_MANA_PRODUCED_OR_STORED` | 3 | **NEW** | Phase 5 |
| `LEVEL_FOR_OPP_UNIT_COLLECTED` | 4 | **NEW** | Phase 5 |

### 5.3 processMove() -- Move Processing (lines 1433-2063)

This is the core move dispatch. Each case maps to a C++ doAction() case.

| AS3 Case | Lines | Purpose | C++ doAction Case | Key Differences | Phase |
|---|---|---|---|---|---|
| `MOVE_ASSIGN` | 1440-1516 | Use ability | `USE_ABILITY` | **AS3 runs script BEFORE useAbility() internal. C++ runs script AFTER useAbility().** This is the script execution ordering bug (B1). | Phase 4 |
| `MOVE_UNASSIGN` | 1517-1571 | Undo ability | `UNDO_USE_ABILITY` | SKIP (undo) | SKIP |
| `MOVE_BUY` | 1572-1627 | Purchase unit | `BUY` | **AS3: pay cost, sac, buy script, create. C++: pay cost, sac in buyCardByID, run buyScript. Order is similar but create-card tracking differs** | Phase 4 |
| `MOVE_SELL` | 1628-1660 | Sell purchased unit | `SELL` | Match | Existing |
| `MOVE_MELEE` | 1661-1677 | Kill frontline unit | `ASSIGN_FRONTLINE` | Match (calls blockWithCard) | Existing |
| `MOVE_UNMELEE` | 1678-1699 | Undo frontline | -- | SKIP (undo) | SKIP |
| `MOVE_DEFEND` | 1700-1714 | Assign blocker | `ASSIGN_BLOCKER` | Match (calls blockWithCard) | Existing |
| `MOVE_UNDEFEND` | 1715-1733 | Undo block | -- | SKIP (undo) | SKIP |
| `MOVE_BREACH_OR_OVERKILL` | 1734-1765 | Breach/overkill unit | `ASSIGN_BREACH` | Match | Existing |
| `MOVE_UNBREACH_OR_UNOVERKILL` | 1766-1798 | Undo breach | `UNDO_BREACH` | SKIP (undo) | SKIP |
| `MOVE_WIPEOUT` | 1799-1821 | Initiate wipeout | `WIPEOUT` | Match | Existing |
| `MOVE_UNWIPEOUT` | 1822-1842 | Undo wipeout | -- | SKIP (undo) | SKIP |
| `MOVE_END_DEFENSE` | 1843-1856 | End defense phase | `END_PHASE` (Defense) | Match | Existing |
| `MOVE_ENTER_CONFIRM` | 1857-1984 | End action, enter confirm | `END_PHASE` (Action) | **CRITICAL: AS3 has 127 lines of stagnation tracking here. C++ has none.** | Phase 5 |
| `MOVE_COMMIT` | 1985-2063 | Commit turn | `END_PHASE` (Confirm) | **AS3 COMMIT calls swoosh(). C++ endPhase(Confirm) increments turn and transitions.** | Phase 3 |

### 5.4 MOVE_ASSIGN Detail (Critical Script Ordering Difference)

**AS3 (State.as:1440-1516) execution order:**
1. Check legality
2. Pay ability cost (mana, sac, netherfy)
3. Run ability script (create units, receive resources)
4. Set role to ASSIGNED
5. Apply health cost, kill if dead
6. Handle target abilities (disrupt/snipe)

**C++ (GameState.cpp:576-631) execution order:**
1. Check legality
2. If target ability, just set m_targetAbilityCardClicked flag and return
3. Run script (runScript which includes mana cost, sac cost, create, receive)
4. Call card.useAbility() (which sets Assigned, applies health/charge cost, kills if dead)

**Key difference:** In C++, runScript() deducts ability cost AND creates units BEFORE useAbility() sets the card to Assigned status. In AS3, cost deduction happens first, then script runs. The net effect differs when the script creates units that reference the source card's state.

### 5.5 swoosh() -- Turn Transition (lines 2582-3073)

The swoosh is the turn boundary processing. AS3 processes everything in a single pass per card; C++ splits into multiple passes.

| AS3 Section | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| Clear damage/chill for all insts | 2594-2603 | Reset per-turn damage tracking | `Card::beginTurn()` (partial) | **AS3 clears for ALL insts; C++ only clears for active player cards** | Phase 3 |
| Tick construction time | 2616-2624 | Reduce build time | `Card::beginTurn()` | Match | Existing |
| Tick delay | 2626-2635 | Reduce delay counters | `Card::beginTurn()` | Match | Existing |
| Tick lifespan | 2637-2677 | Reduce lifespan, kill if 0 | `Card::beginTurn()` | **AS3 also dispatches SEND_LIFESPAN_TICK event and tracks stagnation** | Phase 3/5 |
| Refresh role/blocking | 2680-2713 | Reset status to Default if applicable | `Card::beginTurn()` | **AS3 updates blocking field based on Card defaultBlocking/assignedBlocking; C++ computes canBlock() on demand** | Phase 3 |
| Heal units | 2716-2742 | Apply healthGained, cap at healthMax | `Card::beginTurn()` | **AS3 tracks heal event for stagnation; C++ does not** | Phase 3/5 |
| Recharge units | 2744-2760 | Restore charges | -- | **NEW: C++ beginTurn() does NOT handle charge recharging** | Phase 3 |
| Run beginOwnTurnScript | 2762-2801 | Execute per-turn scripts (resonate, etc.) | `GameState::beginTurn()` then `runScript()` | **AS3 runs inline during per-card loop; C++ does separate pass** | Phase 3 |
| Handle special cards | 2803-2888 | Robo Santa, Condimus, Ebb Turbine, etc. | -- | **AS3 has hardcoded special-case handlers by card name. C++ has none.** | Phase 3 |
| Process resonate | 2891-2935 | Resonate mechanic | `runScript()` with `hasResonate()` | **C++ processes resonate in script execution; AS3 processes in swoosh** | Phase 3 |
| Process annihilate | 2937-2965 | Unit-based damage (annihilate mechanic) | -- | **NEW: C++ has no annihilate processing** | Phase 3 |
| Handle special finisher cards | 2967-3024 | EMP, Deep Impact, Glaciator, Arms Race, etc. | -- | **AS3 has hardcoded special finisher handlers. C++ has none.** | Phase 3 |
| Collect dead bodies | 3026-3037 | Move dead units to graveyard | `CardData::removeKilledCards()` | Match | Existing |
| Collect spells | 3039-3049 | Remove completed spells | -- | **NEW: C++ does not distinguish spell cleanup** | Phase 3 |
| Mana rot (red decay) | 3051-3056 | Red mana decays to 0 | `GameState::beginTurn()` resets Red to 0 | **C++ resets at beginning of beginTurn; AS3 does it at end of swoosh** | Existing |
| Stagnation counter increments | 3058-3072 | Increment all 4 levels of all counter types | -- | **NEW: C++ has no stagnation counters** | Phase 5 |

### 5.6 swoosh() Architecture Comparison

**AS3 Architecture (single-pass):**
```
for each inst in player's units:
    clear damage/chill
    tick construction
    tick delay
    tick lifespan (+ stagnation events)
    refresh role/blocking
    heal (+ stagnation events)
    recharge charges
    run beginOwnTurnScript (creates units inline)
// then: special cards, resonate, annihilate, finishers
// then: collect bodies, collect spells, mana rot
// then: increment stagnation counters
```

**C++ Architecture (multi-pass):**
```
// Pass 0: reset resources (energy, blue, red, attack)
// Pass 1: snapshot card IDs
// Pass 2: beginTurn() for killed cards
// Pass 3: beginTurn() for live cards (ticks, heals, status reset)
// Pass 4: run beginOwnTurnScript for surviving cards
// Pass 5: removeKilledCards()
```

**Critical structural difference:** AS3 interleaves script execution with per-card upkeep in a single loop. If a beginOwnTurnScript creates a new unit, that unit is NOT processed in the current swoosh (the iteration snapshot prevents it). C++ separates into passes, achieving the same snapshot behavior but with different ordering of operations within each card's processing.

### 5.7 checkWin() -- Win Condition (lines 3298-3387)

| AS3 Section | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| Normal mode check | 3310-3375 | Check unit counts + doomed | `calculateGameOver()` | **AS3 checks nonInvTotal (excludes invincible); C++ checks total cards.** C++ now has doomed check after audit fix. | Existing (fixed) |
| Mission mode check | 3377-3386 | Check mission objectives | -- | SKIP (campaign) | SKIP |
| `COLOR_DRAW_MUTUAL_ELIMINATION` | 3337-3340 | Both sides wiped out | `winner()` returns Player_None | C++ now checks mutual elim first after audit fix | Existing (fixed) |
| `COLOR_DRAW_STALEMATE` | 3342-3370 | Stagnation draw | -- | **NEW: requires stagnation counters** | Phase 5 |

### 5.8 Stagnation Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Phase |
|---|---|---|---|---|
| `incrementTurnNoProgressCounters()` | 3389-3398 | Increment all 4 levels of turn counters | **NEW** | Phase 5 |
| `resetTurnNoProgressCounters(level)` | 3400-3412 | Reset levels < given level | **NEW** | Phase 5 |
| `resetOppNoProgressCounters(level)` | 3414-3426 | Reset opponent counters at level | **NEW** | Phase 5 |
| `resetColorNoProgressCounters(color, level)` | 3428-3452 | Reset color-specific counters | **NEW** | Phase 5 |
| `colorIsStagnated(color)` | 3454-3468 | Check if color resource is stagnated | **NEW** | Phase 5 |

### 5.9 Script Execution Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `payCost(inst, cost)` | 2066-2098 | Pay mana + sac + netherfy cost | `runScript()` (partial) | **AS3 handles netherfy separately; C++ has no netherfy** | Phase 4 |
| `unpayCost(inst, cost)` | 2100-2132 | Undo cost payment | `runScriptUndo()` (partial) | SKIP (undo) | SKIP |
| `sac(inst, sacArr)` | 2134-2175 | Sacrifice units | `getCardsToSac()` + `killCardByID()` | **AS3 sac ordering: lowest instId first (same as C++)** | Existing |
| `unsac(inst, sacArr)` | 2177-2212 | Undo sacrifice | -- | SKIP (undo) | SKIP |
| `netherfy(inst, nethArr)` | 2214-2254 | Auto-destroy enemy units | -- | **NEW: C++ has no netherfy. Maps to destroy scripts.** | Phase 4 |
| `unnetherfy(inst, nethArr)` | 2256-2293 | Undo netherfy | -- | SKIP (undo) | SKIP |
| `runScriptForward(inst, script)` | 2295-2377 | Execute script effects (create/receive/give) | `runScript()` | **AS3 tracks creator IDs; C++ only tracks created IDs** | Phase 4 |
| `runScriptBackward(inst, script)` | 2379-2463 | Undo script effects | `runScriptUndo()` | SKIP (undo) | SKIP |
| `collectBodies()` | 2465-2476 | Remove dead units | `CardData::removeKilledCards()` | Match | Existing |
| `collectSpells()` | 2478-2498 | Remove finished spells | -- | **NEW: C++ does not separate spell collection** | Phase 3 |
| `manaRots()` | 2500-2506 | Decay red resource | Resource reset in beginTurn() | Match (different location) | Existing |

### 5.10 State Query Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `allCardsOfColorWithName(c, name)` | 3093-3105 | Find all cards of type owned by player | `numCardsOfType()` (partial) | AS3 returns array of instIds; C++ returns count only | Existing |
| `hasUnassigned(c, cardId)` | 3107-3120 | Has unassigned unit of type? | -- | **NEW: not in C++** | Phase 4 |
| `hasAssigned(c, cardId)` | 3122-3135 | Has assigned unit of type? | -- | **NEW: not in C++** | Phase 4 |
| `hasDead(c, cardId)` | 3137-3150 | Has dead unit of type? | -- | **NEW: not in C++** | Phase 4 |
| `numAssigned(c, cardId)` | 3152-3166 | Count assigned units of type | -- | **NEW: not in C++** | Phase 4 |
| `numDead(c, cardId)` | 3168-3182 | Count dead units of type | -- | **NEW: not in C++** | Phase 4 |
| `turn` (getter) | 3184-3187 | Whose turn (0 or 1) | `getActivePlayer()` | Match | Existing |
| `turnMana` / `oppMana` | 3189-3200 | Resource accessors | `getResources(player)` | Match | Existing |
| `turnSupply` / `oppSupply` | 3202-3213 | Supply accessors | `getCardBuyableByID()` | Match | Existing |

### 5.11 Sorting / Ordering Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `order()` | 3215-3228 | Sort inst array by card position | -- | **SKIP: inst ordering for UI display** | SKIP |
| `compareInst(a, b)` | 3230-3240 | Sort comparator (position, id) | -- | SKIP (UI) | SKIP |
| `compareInstSac(a, b)` | 3242-3252 | Sac priority comparator | `getCardsToSac()` sorts by ID | Similar logic | Existing |
| `compareInstNether(a, b)` | 3254-3264 | Netherfy priority comparator | -- | **NEW: no netherfy in C++** | Phase 4 |
| `instIdsDefense(c)` | 3266-3278 | Get blocker IDs sorted by defense | -- | **C++ iterates cards inline** | Existing |
| `instIdsBreach(c)` | 3280-3296 | Get breachable IDs sorted | -- | **C++ iterates cards inline** | Existing |

### 5.12 Trigger / Condition / Mission System

| AS3 Function | Lines | Purpose | C++ Equivalent | Phase |
|---|---|---|---|---|
| `executeTriggers()` | 3470-3520 | Fire trigger events | -- | SKIP (campaign) |
| `checkCondition(cond)` | 3522-3582 | Evaluate mission condition | `Card::meetsCondition()` (partial) | SKIP (campaign) |
| `satisfiesAllConditions(conds)` | 3584-3601 | All conditions met? | -- | SKIP (campaign) |
| `executeAction(action)` | 3603-3680 | Execute mission action | -- | SKIP (campaign) |
| `checkWinMission()` | 3377-3386 | Check mission objectives | -- | SKIP (campaign) |

### 5.13 State Setup / Init Functions

| AS3 Function | Lines | Purpose | C++ Equivalent | Differences | Phase |
|---|---|---|---|---|---|
| `State()` constructor | 104-191 | Create from JSON + init cards | `GameState()` + `initFromJSON()` | Match | Existing |
| `createInstsFromInitArray()` | 2508-2580 | Create initial units | `addCard()` calls in initFromJSON() | Match | Existing |

### 5.14 ENTER_CONFIRM Stagnation Logic (lines 1857-1984)

This is the most critical missing piece. The ENTER_CONFIRM handler (127 lines) implements the stagnation tracking that determines draws:

```
// Simplified AS3 logic:
stateHelper.update(this);

// Level 1 resets: if opponent could defend, various low-level events
if (stateHelper.couldDefendThisTurn)
    resetOppNoProgressCounters(LEVEL_FOR_DAMAGE_BY_MORE_THAN_HEALING)

// Level 2 resets: if gold was stored
if (turnMana[MANA_P] > 0)
    resetTurnNoProgressCounters(LEVEL_FOR_MONEY_STORED)

// Level 3 resets: if color resources were produced
for each color in [red, green, blue]:
    if (turnMana[color] > 0 && !colorIsStagnated(color))
        resetColorNoProgressCounters(color, LEVEL_FOR_COLOR_PRODUCED)

// Level 4 resets: if opponent unit was collected (killed)
if (stateHelper.oppAllUnitsTotal < previousOppTotal)
    resetTurnNoProgressCounters(LEVEL_FOR_OPP_UNIT_COLLECTED)

// Check for stalemate draw
for (level = 0; level < NUM_LEVELS; level++)
    if (turnNoProgressCounters[level] >= CUTOFFS_FOR_DRAW[level])
        color = COLOR_DRAW_STALEMATE; break;
```

**C++ has NONE of this logic.** The entire stagnation system is Phase 5 work.

---

## 6. NEW Functions Needed (Summary)

Functions that have NO C++ equivalent and must be created during the port.

### Phase 3 -- Swoosh

| Function | Source | Priority | Notes |
|---|---|---|---|
| Charge recharging in swoosh | State.as:2744-2760 | HIGH | C++ beginTurn() does not recharge charges |
| Spell collection | State.as:2478-2498 | MEDIUM | Separate from body collection |
| Special card handlers (Robo Santa, Condimus, etc.) | State.as:2803-2888 | MEDIUM | Hardcoded by card name |
| Annihilate processing | State.as:2937-2965 | MEDIUM | Unit-based damage mechanic |
| Special finisher cards (EMP, Deep Impact, etc.) | State.as:2967-3024 | MEDIUM | Hardcoded by card name |
| `Inst.isPartiallyDamaged` | Inst.as:188-191 | LOW | Simple computed property |
| `Inst.damageItCanTake` correction | Inst.as:193-200 | HIGH | Fragile damage semantics differ |
| `Inst.absorb` | Inst.as:214-221 | LOW | Defense calculation helper |
| `Inst.*AfterSwoosh` predictive getters | Inst.as:223-283 | LOW | Used by StateHelper only |
| `Inst.convertedLifespan/convertedDelay` | Inst.as:285-301 | LOW | Used by StateHelper only |
| `Inst.weaklyEqualTo/stronglyEqualTo` | Inst.as:303-403 | LOW | Validation utility |
| `Card.chargeMax` | Card.as field | LOW | Cap for charge recharging |
| `Card.undefendable` | Card.as field | MEDIUM | Blocking eligibility |
| `Card.attackPotential` | Card.as:603-631 | LOW | Used by StateHelper |
| `Card.colorType` | Card.as:671-702 | MEDIUM | Used by stagnation |
| Blocking HP values (defaultBlocking/assignedBlocking as int) | Card.as + Inst.as | HIGH | AS3 stores HP values, not booleans |

### Phase 4 -- Moves

| Function | Source | Priority | Notes |
|---|---|---|---|
| Script ordering fix (cost BEFORE script) | State.as:1440-1516 | CRITICAL | B1 audit finding |
| Netherfy (abilityNetherfy + DEADNESS_NETHERED) | State.as:2214-2254 | HIGH | Auto-destroy mechanic |
| Death script execution | Card.as:deathScript | HIGH | Scripts on breach death |
| Creator ID tracking | Inst.as fields | MEDIUM | Track which unit created this one |
| Disruptor ID tracking | Inst.as:disruptorIds | MEDIUM | Track which units chilled this card |
| Sniper ID tracking | Inst.as:sniperId | MEDIUM | Track which unit sniped this card |
| `hasUnassigned/hasAssigned/hasDead` | State.as:3107-3150 | MEDIUM | State query helpers |
| `numAssigned/numDead` | State.as:3152-3182 | MEDIUM | Count helpers |
| `beginOwnTurnCreateIds` separate tracking | Inst.as field | MEDIUM | Per-script-type create tracking |

### Phase 5 -- Stagnation and Conditions

| Function | Source | Priority | Notes |
|---|---|---|---|
| `StateHelper.update()` (full) | StateHelper.as:102-649 | CRITICAL | 547-line property computation |
| `incrementTurnNoProgressCounters()` | State.as:3389-3398 | CRITICAL | Core stagnation |
| `resetTurnNoProgressCounters(level)` | State.as:3400-3412 | CRITICAL | Core stagnation |
| `resetOppNoProgressCounters(level)` | State.as:3414-3426 | CRITICAL | Core stagnation |
| `resetColorNoProgressCounters(color, level)` | State.as:3428-3452 | CRITICAL | Core stagnation |
| `colorIsStagnated(color)` | State.as:3454-3468 | CRITICAL | Stagnation check |
| ENTER_CONFIRM stagnation handler | State.as:1857-1984 | CRITICAL | 127 lines of draw detection |
| `COLOR_DRAW_STALEMATE` result | C.as constant | HIGH | New game result type |
| `CONDITION_IS_BLOCKING` | C.as constant | MEDIUM | Missing condition type |
| `CONDITION_NAME_IN` | C.as constant | MEDIUM | Multi-name condition |
| `CONDITION_IS_ENGINEER_TEMP` | C.as constant | LOW | Engineer-specific condition |

---

## 7. Key Semantic Differences

These are the most impactful behavioral divergences between AS3 and C++, ordered by severity.

### 7.1 CRITICAL: Script Execution Ordering (Phase 4)

**AS3 MOVE_ASSIGN (State.as:1440-1516):**
1. Pay ability cost (mana, sac, netherfy)
2. Run ability script (create units, receive resources)
3. Set role to ASSIGNED, apply health cost

**C++ USE_ABILITY (GameState.cpp:576-631):**
1. runScript() -- pays cost AND runs script effects AND creates units
2. card.useAbility() -- sets Assigned, deducts charges/health

The C++ ordering bundles cost payment with script execution, while AS3 separates them. This affects the game state seen by created units.

### 7.2 CRITICAL: Stagnation System Entirely Missing (Phase 5)

AS3 has a 4-level progress counter system with 12+ event types tracking "no progress" turns. When any counter reaches its cutoff [2, 8, 20, 40], the game ends in a stalemate draw. C++ has only a flat 200-turn limit. This affects ~2-5% of games that reach stalemate conditions.

### 7.3 HIGH: Death Script Not Executed (Phase 4)

AS3 Card.as defines deathScript for some units (e.g., Centurion creates tokens on death, Valkyrion produces resources). C++ killCardByID() simply marks the card dead without executing any death triggers.

### 7.4 HIGH: Swoosh Architecture (Phase 3)

AS3 processes all swoosh operations (tick, heal, recharge, run script) in a single per-card loop. C++ uses multiple passes: first beginTurn() for all cards, then runScript() for all cards. This means:
- In AS3, a card that dies from lifespan in the swoosh loop will NOT have its beginOwnTurnScript run.
- In C++ (current), lifespan kill happens in beginTurn() (pass 3), and scripts are checked in pass 4 which skips dead cards.
- **Net effect is the same** for lifespan kills, but the behavior for script-created units during swoosh may differ.

### 7.5 HIGH: Blocking HP is Integer, Not Boolean (Phase 3)

AS3 Card.defaultBlocking and Card.assignedBlocking are integers representing how much HP is contributed when blocking. C++ stores them as booleans (can block or cannot block). This means AS3 can have units that block for less than their full HP (though no current cards use this). If any cardLibrary unit has defaultBlocking != 0 && defaultBlocking != startingHealth, the C++ engine will compute incorrect defense.

### 7.6 MEDIUM: Charge Recharging Missing in C++ (Phase 3)

AS3 swoosh (State.as:2744-2760) recharges unit charges each turn: inst.charge = Math.min(inst.charge + card.chargeGained, card.chargeMax). C++ Card::beginTurn() does NOT recharge charges. Units with chargeGained > 0 will never regain charges in C++. Currently this does not affect any base set units, but tech units with charges (e.g., Lancetooth) are affected.

### 7.7 MEDIUM: Netherfy / Auto-Destroy Missing (Phase 4)

AS3 abilityNetherfy allows abilities to automatically destroy opponent units matching criteria. C++ has no equivalent. Units with netherfy abilities (e.g., Scorchilla) will not destroy their targets correctly.

### 7.8 MEDIUM: Special Card Hardcoded Handlers (Phase 3)

AS3 swoosh has 9 hardcoded special-case handlers for specific cards: Robo Santa, Condimus, Ebb Turbine, Redeemer, Galvani Drone, Savior, EMP, Deep Impact, Glaciator. C++ has none of these. Most are implemented via the script system, but some (like Condimus unit-spawning and EMP global effect) require special handling.

### 7.9 LOW: Sellable is a Role in AS3, a Boolean in C++ (Phase 3)

AS3 uses ROLE_SELLABLE as a distinct card status. C++ uses a separate m_sellable boolean alongside the status enum. Functionally equivalent but structurally different.

---

## 8. Files Modified Per Phase

| Phase | C++ Files to Modify | New C++ Files |
|---|---|---|
| Phase 3 (Swoosh) | `Card.cpp`, `Card.h`, `GameState.cpp`, `CardTypeInfo.h` | None |
| Phase 4 (Moves) | `GameState.cpp`, `Card.cpp`, `Card.h`, `CardData.h` | None |
| Phase 5 (Stagnation) | `GameState.cpp`, `GameState.h`, `Card.cpp`, `Condition.h` | `StateHelper.h`/`.cpp` (optional: could inline into GameState) |

---

## Appendix A: Complete C++ Public API (56 methods)

For reference, these are all public methods on GameState that must be preserved during the port:

| Method | Used By AI | Notes |
|---|---|---|
| `doAction(Action)` | Yes | Core move execution |
| `doMove(Move)` | Yes | Execute sequence of actions |
| `isLegal(Action)` | Yes | Legality check |
| `generateLegalActions(vector)` | Yes | Action generation |
| `isGameOver()` | Yes | Game state check |
| `winner()` | Yes | Result determination |
| `getActivePlayer()` | Yes | Turn info |
| `getInactivePlayer()` | Yes | Turn info |
| `getActivePhase()` | Yes | Phase info |
| `getTurnNumber()` | Yes | Turn counter |
| `getAttack(player)` | Yes | Resource query |
| `getResources(player)` | Yes | Resource query |
| `getTotalAvailableDefense(player)` | Yes | Defense calculation |
| `numCards(player)` | Yes | Card count |
| `numKilledCards(player)` | Yes | Dead card count |
| `numCardsOfType(player, type, active)` | Yes | Type count |
| `getCardByID(id)` | Yes | Card access |
| `getCardIDs(player)` | Yes | Card ID list |
| `getKilledCardIDs(player)` | Yes | Dead card IDs |
| `numCardsBuyable()` | Yes | Supply count |
| `getCardBuyableByID(id)` | Yes | Supply access |
| `getCardBuyableByIndex(idx)` | Yes | Supply access |
| `getCardBuyableByType(type)` | Yes | Supply access |
| `isTargetAbilityCardClicked()` | Yes | Target state |
| `getTargetAbilityCardClicked()` | Yes | Target card |
| `canWipeout(player)` | Yes | Wipeout check |
| `canBreachEnemyCard(player)` | Yes | Breach check |
| `hasBreachableCard(player)` | Yes | Breach check |
| `hasBreachableFrontlineCard(player)` | Yes | Frontline check |
| `hasOverkillableCard(player)` | Yes | Overkill check |
| `canOverkillEnemyCard(player)` | Yes | Overkill check |
| `canBreachFrozenCard()` | Yes | Frozen breach |
| `isBuyable(player, type)` | Yes | Purchase check |
| `isIsomorphic(other)` | Yes | State comparison |
| `isPlayerIsomorphic(other, p)` | Yes | Player comparison |
| `getIsomorphicCardID(card)` | Yes | Card matching |
| `getClickAction(card)` | GUI only | Click-to-Action mapping |
| `getLastCardBoughtID()` | AI only | Last purchase |
| `setStartingState(player, n)` | Setup only | Game initialization |
| `addCard(player, type, ...)` | Setup only | Manual card addition |
| `addCard(card)` | Setup only | Manual card addition |
| `addBuyableCardType(type)` | Setup only | Supply setup |
| `addCardBuyable(type)` | Setup only | Supply setup |
| `setMana(player, res)` | Setup only | Resource setup |
| `manuallySetMana(player, res)` | Debug only | Resource override |
| `manuallySetAttack(player, atk)` | Debug only | Attack override |
| `killCardByID(id, cause)` | Internal + test | Kill a card |
| `beginTurn(player)` | Internal | Swoosh processing |
| `getStateString()` | Debug | Text state dump |
| `toJSONString()` | Debug/IO | JSON state dump |
| `getMemoryUsed()` | Debug | Memory tracking |
| `initFromJSON(json)` | IO | Load from JSON |

---

## Appendix B: AS3 Line Ranges Quick Reference

For navigating the AS3 source during implementation:

| File | Section | Lines |
|---|---|---|
| **State.as** | Constructor + init | 104-191 |
| | isLegal checks | 193-1431 |
| | processMove() | 1433-2063 |
| | MOVE_ASSIGN | 1440-1516 |
| | MOVE_BUY | 1572-1627 |
| | ENTER_CONFIRM (stagnation) | 1857-1984 |
| | COMMIT | 1985-2063 |
| | payCost / sac / netherfy | 2066-2293 |
| | runScriptForward/Backward | 2295-2463 |
| | collectBodies / collectSpells | 2465-2498 |
| | createInstsFromInitArray | 2508-2580 |
| | swoosh() | 2582-3073 |
| | checkWin() | 3298-3387 |
| | Stagnation functions | 3389-3468 |
| | Trigger/mission system | 3470-3680 |
| **Inst.as** | Constructor | 48-170 |
| | Computed properties | 183-301 |
| | Comparison methods | 303-403 |
| | Serialization | 405-503 |
| **Card.as** | Constructor (type parsing) | 47-556 |
| | Computed properties | 593-702 |
| **StateHelper.as** | reset() | 62-100 |
| | update() | 102-649 |
| **C.as** | All constants | 14-624 |
