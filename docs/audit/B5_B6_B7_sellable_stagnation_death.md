# B5 / B6 / B7: Sellable Role, Stagnation Detection, Simultaneous Death Ordering

Engine comparison audit — AS3 (live Prismata client) vs C++ (PrismataAI).

---

## B5: Sellable Role Transition

### Overview

When a unit is purchased, it enters the game with the **sellable** role. This allows the player to "undo" the purchase during the same action phase by clicking the unit, which reverses the buy cost and removes the unit. The sellable role transitions to inert during swoosh.

AS3 represents this as `role = C.ROLE_SELLABLE` (a string). C++ represents it as a separate `m_sellable` bool layered on top of the `m_status` enum.

---

### B5.1: When sellable is set

**AS3 (Inst.as:71-73)**:
```actionscript
if(bought)
{
    this.role = C.ROLE_SELLABLE;
}
else
{
    this.role = C.ROLE_INERT;
}
```
When `Inst` is constructed with `bought=true`, role is set to `C.ROLE_SELLABLE` (which equals the string `"sellable"`).

**C++ (Card.cpp:200-208)**:
```cpp
case CardCreationMethod::Bought:
{
    m_constructionTime = type.getConstructionTime();
    m_status = CardStatus::Inert;
    m_sellable = true;
    break;
}
```
When created via `CardCreationMethod::Bought`, status is set to `Inert` and `m_sellable` is set to `true`.

**C++ JSON import (Card.cpp:62-67)**:
```cpp
else if (role == "sellable")
{
    m_status = CardStatus::Inert;
    m_sellable = true;
}
```

**Verdict: MATCH.** Both set sellable on purchase. The C++ dual-field approach (Inert status + sellable bool) faithfully mirrors the AS3 single-field role.

---

### B5.2: When sellable clears

**AS3 (State.as swoosh, lines 2642-2704)**:
Sellable clears in two situations during swoosh:

1. **Under construction with buildTime > 1 after tick** (lines 2652-2657):
```actionscript
if(inst.role == C.ROLE_SELLABLE)
{
    inst.role = C.ROLE_INERT;
    this.dispatch(update,animate,C.SEND_SELLABLE_TO_INERT,{"inst":inst});
}
continue;  // skip the role refresh below
```

2. **General role refresh** (lines 2698-2705): After construction/delay/lifespan processing, all surviving units get their role reset:
```actionscript
if(card.hasAbility)
{
    inst.role = C.ROLE_DEFAULT;
}
else
{
    inst.role = C.ROLE_INERT;
}
```
This overwrites any remaining sellable role with default/inert.

**C++ (Card.cpp:574-643, beginTurn())**:
```cpp
void Card::beginTurn()
{
    // card is no longer sellable
    m_sellable = false;
    // ...
    // set default status
    if (getType().hasAbility() || getType().hasTargetAbility())
    {
        setStatus(CardStatus::Default);
    }
    else
    {
        setStatus(CardStatus::Inert);
    }
    // ...
}
```
`beginTurn()` is called from `GameState::beginTurn()` which runs during the Swoosh phase (`beginPhase(player, Phases::Swoosh)` at line 1317).

**Verdict: MATCH.** Both clear sellable during swoosh. AS3 clears it by overwriting the role during the swoosh loop. C++ clears it explicitly (`m_sellable = false`) at the start of `beginTurn()`. The timing is equivalent: swoosh runs once per player turn, and sellable is cleared for all owned units.

**Edge case — under-construction units with buildTime > 1**: AS3 clears sellable to inert and `continue`s (skipping the general refresh). C++ calls `beginTurn()` which sets `m_sellable = false` and then, since `isUnderConstruction()` is true, skips the status reset block. Both result in `inert + not sellable`. **MATCH.**

---

### B5.3: Can sellable units block?

**AS3 (StateHelper.as:182-186, 434-437)**:
Defense totals are computed from `inst.blocking`:
```actionscript
if(inst.blocking)
{
    this.ownDefenders.push(inst);
    this.ownDefense += inst.damageItCanTake;
}
```
And similarly for opponent defenders:
```actionscript
if(inst.blocking)
{
    this.oppDefenders.push(inst);
    this.oppDefense += inst.damageItCanTake;
}
```

The `blocking` field is set at construction. For bought units (Inst.as:78-85):
```actionscript
if(buildTime > 0)
{
    this.blocking = false;
}
else
{
    this.blocking = card.defaultBlocking;
}
```
Newly bought units with `buildTime > 0` have `blocking = false`. For instant units (buildTime=0), blocking follows `card.defaultBlocking`. The sellable role itself does NOT prevent blocking; blocking eligibility depends solely on the `blocking` field.

Defense phase blocking (State.as, MOVE_DEFEND handler line 1712): The AS3 defense handler does not check role at all — it processes damage on the clicked instance. The Controller layer determines which units can be clicked for defense (based on `blocking` field).

**C++ (Card.cpp:484-512)**:
```cpp
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned))
    {
        return false;
    }
    if (getCurrentDelay() > 0) { return false; }
    if (isUnderConstruction()) { return false; }
    if (isDead()) { return false; }
    if (isFrozen()) { return false; }
    return true;
}
```
`canBlock()` checks against `CardType::canBlock(assigned)` which uses `getAssignedBlocking()` if assigned, else `getDefaultBlocking()`. A sellable card has `m_status = CardStatus::Inert`, so `canBlock(false)` → `getDefaultBlocking()`.

**Key observation**: Sellable units are newly purchased. If they have `buildTime > 0`, they are under construction and `canBlock()` returns false (both AS3 and C++). If `buildTime == 0`, in AS3 `blocking = card.defaultBlocking` and in C++ `canBlock()` returns `getDefaultBlocking()`. The sellable role/flag itself does not gate blocking in either engine.

**Verdict: MATCH.** Neither engine uses the sellable role to determine blocking eligibility. Blocking depends on construction time, delay, frozen status, and the card's defaultBlocking property.

---

### B5.4: Can sellable units use abilities?

**AS3**: Ability usage requires the unit's role. The assign (ability use) handler in Controller.as checks various conditions. Newly bought units with buildTime > 0 are under construction and cannot use abilities. For instant units (buildTime=0), the role is `ROLE_SELLABLE`, not `ROLE_DEFAULT`. The Controller checks for ability usability through card properties and role state.

In the swoosh, ability-having units get their role set to `ROLE_DEFAULT` (line 2700). Before swoosh, a bought unit with `role = ROLE_SELLABLE` has not been refreshed to `ROLE_DEFAULT`, so it cannot use abilities during the same turn it was bought.

**C++ (Card.cpp:670-703)**:
```cpp
bool Card::canUseAbility() const
{
    if (isDead()) { return false; }
    if (getStatus() != CardStatus::Default) { return false; }
    if (isUnderConstruction()) { return false; }
    if (getType().usesCharges() && (getCurrentCharges() < getType().getChargeUsed())) { return false; }
    if (m_currentDelay > 0) { return false; }
    if (m_currentHealth < m_type.getHealthUsed()) { return false; }
    return true;
}
```
A sellable card has `m_status = CardStatus::Inert`, so `getStatus() != CardStatus::Default` is true, and `canUseAbility()` returns false.

**Verdict: MATCH.** Sellable units cannot use abilities in either engine. AS3 blocks it because the role is not `default`. C++ blocks it because the status is `Inert`, not `Default`.

---

### B5.5: Sellable units in defense total

**AS3 (StateHelper.as:182-186)**: Defense total includes all units where `inst.blocking == true`. Newly bought units with buildTime > 0 have `blocking = false`, so they are excluded. Instant sellable units with `defaultBlocking = true` would be included.

**C++ (GameState.cpp:1523-1539)**:
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
`canBlock()` does not check `m_sellable`. It checks `CardType::canBlock(assigned)`, delay, construction, dead, frozen.

**Important detail**: AS3 uses `inst.damageItCanTake` (which accounts for fragile and damage), while C++ uses `card.currentHealth()`. For a freshly purchased unit with no damage taken, these are equivalent.

**Verdict: MATCH.** Sellable status does not affect defense total in either engine. The defense calculation depends on `blocking`/`canBlock()`, not the sellable role.

---

### B5 Overall Assessment

| Check | Verdict | Risk |
|---|---|---|
| When sellable is set | MATCH | - |
| When sellable clears | MATCH | - |
| Can sellable units block? | MATCH | - |
| Can sellable units use abilities? | MATCH | - |
| Sellable units in defense total | MATCH | - |

**B5 Overall: NO DIVERGENCE FOUND.** The C++ dual-field representation (m_status + m_sellable) correctly mirrors the AS3 single-field role system for all examined behaviors.

---

## B6: Stagnation Detection System

### Overview

The live Prismata client (AS3) implements a sophisticated multi-level stagnation counter system to detect draw-by-stalemate conditions. This prevents infinite games where neither player can make progress. The C++ AI engine does not implement this system at all, using only a simple turn limit.

---

### B6.1: AS3 Progress Counter Architecture

**Constants (C.as, State.as:76-103)**:
```actionscript
private static const NUM_LEVELS_OF_DRAW_VARIABLES:int = 4;
private static const CUTOFFS_FOR_DRAW:Vector.<int> = new <int>[2,8,20,40];
```

Four levels of stagnation, each with its own counter and cutoff threshold:

| Level | Cutoff | What resets it (progress events) |
|---|---|---|
| 0 | 2 turns | (Hardest to stagnate — almost everything resets this) |
| 1 | 8 turns | Delay ticked, HP healed on pay-HP unit, charge recharged, damage > healing |
| 2 | 20 turns | Money stored, gas stored (Cluster Bolt/Gauss Charge/Zemora/Gaussite Symbiote) |
| 3 | 40 turns | Card bought or inst created, buildtime ticked, opp lifespan ticked |

**Stagnation occurs** when ANY level's counter reaches its cutoff for either player.

**Per-player counters (State.as:180-182)**:
```actionscript
public var whiteNoProgress:Vector.<int>;  // 4-element vector
public var blackNoProgress:Vector.<int>;  // 4-element vector
```

---

### B6.2: AS3 Counter Increment Logic

**State.as:1291-1303 (`incrementTurnNoProgressCounters()`)**:
```actionscript
public function incrementTurnNoProgressCounters() : void
{
    for(var i:int = 0; i < NUM_LEVELS_OF_DRAW_VARIABLES; i++)
    {
        if(this.turn == C.COLOR_WHITE)
        {
            ++this.whiteNoProgress[i];
        }
        else
        {
            ++this.blackNoProgress[i];
        }
    }
}
```
Called once per swoosh (State.as:3070), incrementing ALL 4 levels for the current player.

---

### B6.3: AS3 Counter Reset Logic

Three reset functions:

**`resetTurnNoProgressCounters(level)` (State.as:1306-1318)** — resets counters for levels < `level` for the current turn player:
```actionscript
public function resetTurnNoProgressCounters(level:int) : void
{
    for(var i:int = 0; i < level; i++)
    {
        if(this.turn == C.COLOR_WHITE)
            this.whiteNoProgress[i] = 0;
        else
            this.blackNoProgress[i] = 0;
    }
}
```

**`resetOppNoProgressCounters(level)` (State.as:1321-1333)** — resets counters for the opponent.

**`resetColorNoProgressCounters(color, level)` (State.as:1336-1348)** — resets for a specific color.

**IMPORTANT**: The reset resets all levels **below** the specified level. For example, `resetTurnNoProgressCounters(LEVEL_CARD_BOUGHT_OR_INST_CREATED)` where `LEVEL_CARD_BOUGHT_OR_INST_CREATED = 3` resets levels 0, 1, 2 but NOT level 3.

---

### B6.4: AS3 Progress Event Catalog

Progress events are detected at two points: during swoosh and during confirm phase entry.

**During swoosh (State.as:2582-3070)**:
| Event | Level | Reset function |
|---|---|---|
| Buildtime ticked (construction progress) | 3 | `resetTurnNoProgressCounters(LEVEL_BUILDTIME_TICKED=3)` |
| Delay ticked | 1 | `resetTurnNoProgressCounters(LEVEL_DELAY_TICKED=1)` |
| Opp lifespan ticked | 3 | `resetOppNoProgressCounters(LEVEL_OPP_LIFESPAN_TICKED=3)` |
| HP healed on unit with pay-HP ability | 1 | `resetTurnNoProgressCounters(LEVEL_HP_HEALED=1)` |
| Charge recharged | 1 | `resetTurnNoProgressCounters(LEVEL_CHARGE_RECHARGED=1)` |
| Dead opp unit collected | 4 | `resetColorNoProgressCounters(opponent, LEVEL_OPP_UNIT_COLLECTED=4)` |

**During confirm phase (State.as:1911-1952)**:
| Event | Level | Reset function |
|---|---|---|
| Attack >= max opp defender health (will kill a blocker) | 4 | `resetTurnNoProgressCounters(LEVEL_OPP_UNIT_COLLECTED=4)` |
| Units bought or created this turn | 3 | `resetTurnNoProgressCounters(LEVEL_CARD_BOUGHT_OR_INST_CREATED=3)` |
| Partially damaged inst with damage > healthGained | 1 | `resetTurnNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING=1)` |
| Attack vs fragile blocker progress | 1 | `resetTurnNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING=1)` |
| Gold produced this turn | 2 | `resetTurnNoProgressCounters(LEVEL_MONEY_STORED=2)` |
| Green produced + Cluster Bolt/Gauss Charge/Zemora/Gaussite available | 3 | `resetTurnNoProgressCounters(LEVEL_GAS_STORED_WITH_*=3)` |

**During defense end (State.as:1902-1904)**:
| Event | Level | Reset function |
|---|---|---|
| Partially damaged fragile inst with damage > healthGained | 1 | `resetOppNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING=1)` |

---

### B6.5: AS3 Stagnation Check

**State.as:1351-1370 (`colorIsStagnated()`)**:
```actionscript
public function colorIsStagnated(color:int) : Boolean
{
    for(var i:int = 0; i < NUM_LEVELS_OF_DRAW_VARIABLES; i++)
    {
        if(color == C.COLOR_WHITE)
        {
            if(this.whiteNoProgress[i] >= CUTOFFS_FOR_DRAW[i])
                return true;
        }
        else if(this.blackNoProgress[i] >= CUTOFFS_FOR_DRAW[i])
            return true;
    }
    return false;
}
```
Returns true if ANY level's counter >= its cutoff for the specified color.

**Usage (State.as:1962)**: During confirm phase entry:
```actionscript
this.endTurnObject.oppCouldClaimDraw = this.colorIsStagnated(this.turn);
```
This checks if the CURRENT player is stagnated (meaning the OPPONENT could claim a draw). The result is stored in `endTurnObject.oppCouldClaimDraw` and used to display a warning (`WARNING_OPP_CAN_CLAIM_STALEMATE`).

**Important**: The stalemate claim appears to be a **server-enforced rule** where the opponent can optionally claim a draw when stagnation is detected. The client shows a warning, but the actual draw enforcement happens server-side. The `COLOR_DRAW_STALEMATE` constant exists (C.as:44) but is never set as `result` in the AS3 State engine — it is likely enforced by the server.

---

### B6.6: C++ Implementation

**Game.h:17**:
```cpp
TurnType m_turnLimit = 200;
```

**Game.cpp:88-91**:
```cpp
bool Game::gameOver() const
{
    return m_state.isGameOver() || (m_turnsPlayed >= m_turnLimit);
}
```

**GameState.cpp:1207-1213**:
```cpp
bool GameState::calculateGameOver() const
{
    CardID p1Cards = numCards(Players::Player_One) + numKilledCards(Players::Player_One);
    CardID p2Cards = numCards(Players::Player_Two) + numKilledCards(Players::Player_Two);
    return p1Cards == 0 || p2Cards == 0;
}
```

The C++ engine has:
- **No progress counters** of any kind
- **No stagnation detection**
- **No per-level cutoff system**
- Only a flat 200-turn limit at the `Game` level (not `GameState`)
- `GameState::isGameOver()` only checks if a player has zero cards

---

### B6.7: Impact Analysis

**For self-play**: Games that would be drawn by stagnation in real Prismata run until the 200-turn limit in C++. This means:
1. Self-play games may run much longer than real games in stalemate situations
2. Training data from turns 40-200 in stalemate games represents unrealistic game states
3. Value targets for stalemate positions are not labeled as draws — they continue to produce win/loss labels

**For tournament evaluation**: A game judged as a draw by stagnation in real Prismata would be played to completion (or turn 200) in the C++ engine, potentially producing a different winner.

**For live play**: If the AI engine is used for suggestion/autopilot in real games, it has no awareness that the opponent could claim a stalemate draw. This could lead to strategies that are "winning" by C++ evaluation but actually drawable in real Prismata.

---

### B6 Verdict Summary

| Check | AS3 | C++ | Verdict |
|---|---|---|---|
| Progress counter infrastructure | 4 levels, 2 players, 8 counters | **Not implemented** | **DIVERGENCE** |
| Stagnation check | `colorIsStagnated()` — any level >= cutoff | `m_turnsPlayed >= 200` | **DIVERGENCE** |
| What counts as "progress" | 12+ event types across 4 levels | N/A | **DIVERGENCE** |
| Draw determination | Opponent can claim stalemate | Turn limit only | **DIVERGENCE** |
| Cutoff values | [2, 8, 20, 40] turns per level | 200 flat | **DIVERGENCE** |

**B6 Overall: MAJOR DIVERGENCE.** The entire stagnation detection system is absent from C++. This is an intentional simplification for the AI engine — implementing the full system would require tracking 12+ progress event types and 8 counters.

**Risk Assessment: MEDIUM for self-play, LOW for tournament eval.**
- **Medium for self-play**: Stalemate games generate low-quality training data. However, stalemates are rare in practice (the AI plays aggressively), and the 200-turn limit provides a coarse backstop.
- **Low for tournament eval**: Against OriginalHardestAI, games almost always end by unit elimination, not stagnation. The 200-turn limit is rarely hit.
- **HIGH for live advisor/autopilot**: The AI cannot reason about stalemate threats. If deployed for live advice, it may miss that the opponent could claim a draw.

**Recommended test cases**:
1. Build a position with only Drones and no attackers on both sides — AS3 should trigger stagnation after 2 turns (level 0 cutoff), C++ should play to turn 200.
2. Build a position with only Walls and Drones — no buying possible. Check when each engine declares the game over.
3. Position where one player stores green but has no Cluster Bolt/Gauss Charge/Zemora — level 2 should not be reset.

---

## B7: Simultaneous Death Ordering

### Overview

When multiple units die in the same game action (breach, wipeout, swoosh), the order in which they are processed can matter for units with death triggers (deathScript). This section examines whether the AS3 and C++ engines process deaths in the same order.

---

### B7.1: Death order during breach

**AS3 (State.as:1779-1818, MOVE_BREACH_OR_OVERKILL)**:
In the AS3 client, breach is applied to ONE unit at a time. The Controller (Controller.as) determines which unit to breach and issues individual `MOVE_BREACH_OR_OVERKILL` orders. Each breached unit that dies (`damageItCanTake == 0`) gets:
```actionscript
inst.deadness = C.DEADNESS_WBO;
if(inst.card.deathScript)
{
    this.runScriptForward(update, animate, inst.card.deathScript, C.SCRIPTTYPE_ABILITY, inst, abilityCreateIds);
}
```
Death scripts run **immediately** when the unit dies from breach, before the next breach target is processed. The Controller orchestrates the order: it processes breach targets one at a time, typically breaching the cheapest/most fragile first.

**C++ (GameState.cpp:1561-1575)**:
```cpp
void GameState::breachCard(Card & card)
{
    HealthType currentDamage = (HealthType)getResources(getEnemy(card.getPlayer())).amountOf(Resources::Attack);
    HealthType currentHealth = card.currentHealth();
    HealthType takeDamage = std::min(currentDamage, currentHealth);

    card.takeDamage(takeDamage, DamageSource::Breach);
    if (card.isDead())
    {
        killCardByID(card.getID(), CauseOfDeath::Breached);
    }

    _getResources(getEnemy(card.getPlayer())).set(Resources::Attack, currentDamage - takeDamage);
}
```

Breach in C++ also processes one card at a time. The `doAction()` handler for `ActionTypes::BREACH` (not shown, part of the action dispatch) calls `breachCard()` for individual targets. There is **no death script execution** — C++ has no concept of deathScripts.

**Key difference**: AS3 runs `deathScript` on breach kills (e.g., a unit that creates tokens on death). C++ does not run any death-triggered effects.

**Units with deathScript**: Checking `Card.as:320-322`:
```actionscript
if(obj.hasOwnProperty("deathScript"))
{
    this.abilityScript = this.deathScript = new Script(obj.deathScript);
}
```
DeathScript is assigned from the card data JSON. Units like Centurion, Valkyrion, and others may have death triggers that create tokens or produce resources.

**Verdict: DIVERGENCE (death triggers only).** The ordering of breach damage application is the same (one unit at a time, sequential). However, the C++ engine does not execute deathScripts at all, meaning any units with death triggers will have different game outcomes when breached.

---

### B7.2: Death order during wipeout

**AS3 (State.as:1855-1875, MOVE_WIPEOUT)**:
```actionscript
else if(type == C.MOVE_WIPEOUT)
{
    this.glassBroken = true;
    this.dispatch(update,animate,C.SEND_GLASSBROKEN);
    for each(inst in this.helper.oppDefenders)
    {
        damage = inst.health;
        this.turnMana.attack -= damage;
        inst.damage += damage;
        if(inst.card.fragile) { inst.health -= damage; }
        inst.deadness = C.DEADNESS_WBO;
        this.dispatch(update,animate,C.SEND_WIPEDOUT,{"inst":inst,"delta":damage});
    }
    this.helper.update(this);
}
```
Wipeout iterates through `helper.oppDefenders` and kills them all. **No death scripts are run during wipeout itself** — all defenders get `DEADNESS_WBO` but deathScripts are only run on individual `MOVE_BREACH_OR_OVERKILL` actions, not wipeout. The wipeout simply marks them as dead.

**C++ (GameState.cpp:1502-1521, `blockWithAllBlockers()`)**:
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
            c = 0;  // restart from beginning
        }
        else
        {
            ++c;
        }
    }
}
```
C++ does wipeout by blocking all blockers against the attacker's damage. After each `blockWithCard()`, if the card dies, `killCardByID()` is called, and the iteration restarts from index 0. This means C++ processes blockers in CardID order (lowest ID first), restarting after each kill.

**Ordering difference**: AS3 processes defenders in `helper.oppDefenders` order (order they were added during StateHelper.update, which is Dictionary iteration order — effectively arbitrary/insertion order). C++ processes them in CardID array order, restarting from the beginning after each kill.

**Practical impact**: Since wipeout kills ALL blockers (all damage is applied), the final state should be identical regardless of order — all blockers end up dead with all damage applied. The only case where order matters is if a deathScript creates new blockers or modifies the board, which only AS3 supports (and even AS3 doesn't run deathScripts during wipeout).

**Verdict: MATCH for outcome, MINOR DIVERGENCE in processing order.** The final board state after wipeout is identical. The processing order differs but is inconsequential because no side effects (death triggers) are executed during wipeout in either engine.

---

### B7.3: Death order during swoosh

**AS3 (State.as:2582-3073, swoosh function)**:
During swoosh, units die from lifespan expiry:
```actionscript
else if(inst.lifespan > 0)
{
    --inst.lifespan;
    // ...
    if(inst.lifespan == 0)
    {
        inst.deadness = C.DEADNESS_AGED;
        this.deleteInst(inst.instId);
        // ...
        continue;
    }
}
```
Dead units from lifespan are immediately deleted via `deleteInst()` during the swoosh loop. The iteration uses a pre-copied list of instIds (`copyOfInstIds`), so deletions don't affect the iteration.

Also, `collectBodies()` (State.as:2570-2579) runs before swoosh (at end of defense) and after confirm, removing all dead units:
```actionscript
for(t in this.table)
{
    inst = this.table[t];
    if(inst.dead)
    {
        this.resetColorNoProgressCounters(1 - inst.owner, LEVEL_OPP_UNIT_COLLECTED);
        this.deleteInst(inst.instId);
    }
}
```

**C++ (Card.cpp:574-643, beginTurn())**:
```cpp
void Card::beginTurn()
{
    // ...
    if (!isUnderConstruction() && !isDelayed() && m_lifespan > 0)
    {
        --m_lifespan;
        if (m_lifespan == 0)
        {
            kill(CauseOfDeath::Lifespan);
            return;
        }
    }
    // ...
}
```

And in GameState::beginTurn() (line 1249-1252):
```cpp
_getCardByID(cardID).beginTurn();
if (_getCardByID(cardID).isDead())
{
    killCardByID(cardID, CauseOfDeath::Unknown);
}
```

After all cards process beginTurn, killed cards are bulk-removed:
```cpp
m_cards.removeKilledCards();  // line 1275
```

**Ordering**: AS3 iterates through a copied list of instIds and processes each unit sequentially, deleting dead ones immediately. C++ iterates through a copied list of cardIDs, marks dead ones, then bulk-removes at the end. The key difference:

- AS3: Dead units are removed from the table immediately during iteration (but iteration is safe because of the pre-copied ID list).
- C++: Dead units are marked but remain in the card array until `removeKilledCards()` runs at the end.

**Impact**: If a beginTurnScript of one unit creates or destroys another unit, the order matters. Both engines iterate in their respective data structure order (Dictionary key order for AS3, array index order for C++). Since AS3 uses a Dictionary and C++ uses a vector, the iteration order may differ.

---

### B7.4: Death trigger execution (deathScript)

**AS3**: `deathScript` is a property of `Card.as` (line 85), parsed from card data (line 320-322). When a unit with a deathScript dies from breach, the script is run immediately:
```actionscript
if(inst.card.deathScript)
{
    this.runScriptForward(update, animate, inst.card.deathScript, ...);
}
```
deathScript can create new units, produce resources, or have other side effects.

DeathScripts are run during:
- `MOVE_BREACH_OR_OVERKILL` (State.as:1805-1808) — when a unit is breached to death
- `MOVE_UNBREACH_OR_UNOVERKILL` (State.as:1839-1841) — reversed when unbreach

DeathScripts are **NOT** run during:
- `MOVE_WIPEOUT` — blockers are marked dead but scripts don't run
- `MOVE_DEFEND` — blocker dies but no deathScript
- Swoosh lifespan expiry — units are deleted, no deathScript
- `collectBodies()` — cleanup only

**C++**: There is no deathScript concept. `killCardByID()` simply moves the card to the killed list. No scripts run on death.

```
$ grep -r "deathScript\|death_script\|getDeathScript" source/engine/
(no matches)
```

**Verdict: DIVERGENCE.** C++ does not implement death triggers at all. Units with deathScripts (like units that spawn tokens on death) will behave differently. This is a known simplification of the C++ engine.

**Affected units**: Any unit in `cardLibrary.jso` with a `deathScript` field. Based on Card.as:320, when deathScript is set, it is also assigned as `abilityScript` — this means the C++ engine may already model part of the effect through the ability system, but the death-triggered execution is missing.

---

### B7 Verdict Summary

| Check | AS3 | C++ | Verdict |
|---|---|---|---|
| Death order during breach | Sequential, one at a time, Controller-ordered | Sequential, one at a time, player-ordered | MATCH (order) |
| Death trigger during breach | `deathScript` runs immediately on kill | No death triggers | **DIVERGENCE** |
| Death order during wipeout | All blockers killed in oppDefenders order | All blockers killed in CardID order, restart-from-0 | MATCH (outcome) |
| Death order during swoosh | Lifespan expiry, immediate delete, Dict order | Lifespan expiry, deferred removal, vector order | MATCH (outcome) |
| Death trigger execution | Supported via `deathScript` on breach | **Not implemented** | **DIVERGENCE** |

**B7 Overall: DIVERGENCE on death triggers, MATCH on death ordering.**

The death processing order is functionally equivalent — both engines process deaths sequentially, and the final board state is the same (all dead units end up removed). The significant divergence is the complete absence of `deathScript` execution in C++.

**Risk Assessment: LOW-MEDIUM.**
- Most common units (Drone, Engineer, Wall, Tarsier, Steelsplitter, Rhino, etc.) have no deathScript
- Units with deathScripts are relatively rare in the card pool
- In self-play (OriginalHardestAI vs itself), both players have the same missing behavior, so the training data is internally consistent
- For tournament evaluation, the impact depends on which units are in the random set

**Recommended test cases**:
1. Identify all units with `deathScript` in cardLibrary.jso
2. Create a game where a deathScript unit is breached — verify AS3 creates the spawned units and C++ does not
3. Check if any common base set units have deathScripts (these would affect every game)
4. Verify that C++ correctly handles the abilityScript assignment that accompanies deathScript in Card.as

---

## Cross-Cutting Summary

| Area | Verdict | Severity | Impact on Self-Play | Impact on Eval |
|---|---|---|---|---|
| **B5: Sellable Role** | MATCH | None | None | None |
| **B6: Stagnation Detection** | DIVERGENCE | MEDIUM | Stalemate games run too long | Rare |
| **B7: Death Ordering** | MATCH (order) | None | None | None |
| **B7: Death Triggers** | DIVERGENCE | LOW-MEDIUM | Consistent (both sides) | Depends on unit pool |

**Priority actions**:
1. **(B6) Audit self-play data for stalemate-like games** — count games that reach 100+ turns. If >1%, the stagnation system matters for data quality.
2. **(B7) Identify deathScript units** — scan `cardLibrary.jso` for the `deathScript` field to enumerate affected units and assess how often they appear in the random unit pool.
3. **(B6) No immediate code change needed** — implementing the full stagnation system would be complex (~200 LOC) and the 200-turn limit is a reasonable approximation for AI training.
