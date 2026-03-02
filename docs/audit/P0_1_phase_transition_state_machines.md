# P0.1: Phase Transition State Machine Diagrams

> **Engine Logic Audit** -- Comparing AS3 (ground truth) vs C++ (AI engine)
> Generated: 2026-02-22

## Table of Contents

1. [Phase Enum Definitions](#1-phase-enum-definitions)
2. [AS3 State Machine (Ground Truth)](#2-as3-state-machine-ground-truth)
3. [C++ State Machine](#3-c-state-machine)
4. [Side-by-Side Transition Comparison](#4-side-by-side-transition-comparison)
5. [Identified Differences with Risk Assessment](#5-identified-differences-with-risk-assessment)

---

## 1. Phase Enum Definitions

### AS3 (String-based phases)

```
File: prismata_decompiled/scripts/mcds/engine/C.as

PHASE_DEFENSE = "defense"
PHASE_ACTION  = "action"
PHASE_CONFIRM = "confirm"
```

AS3 does NOT have explicit Breach or Swoosh phases. Breach is handled as a sub-state
of Action (via `glassBroken` flag). Swoosh is a function call (`swoosh()`), not a phase.

### C++ (Integer enum)

```
File: source/engine/Constants.h

namespace Phases { enum { Action=0, Defense=1, Breach=2, Confirm=3, Swoosh=4 }; }
```

C++ has 5 explicit phases. Breach and Swoosh are first-class phases.

### Key Structural Difference

| Concept | AS3 | C++ |
|---|---|---|
| Breach | Sub-state of Action (`glassBroken=true`) | Separate phase (`Phases::Breach=2`) |
| Swoosh | Function call, no phase assignment | Separate phase (`Phases::Swoosh=4`) |
| Active player | Derived: `turn = (numTurns + 1) % 2` | Explicit: `m_activePlayer` set in `beginPhase()` |
| Turn counter | `numTurns` incremented in COMMIT | `m_turnNumber` incremented in endPhase(Confirm) |

---

## 2. AS3 State Machine (Ground Truth)

```
File: prismata_decompiled/scripts/mcds/engine/State.as (~4,490 lines)
```

### State Machine Diagram

```
                    GAME START
                        |
                        v
                +===============+
                |    ACTION     |  phase = "action"
                | glassBroken=F |  numTurns = 0 (White's turn)
                +===============+
                    |       |
        [USE_ABILITY/BUY/   |
         SELL/MELEE/etc]    |
                    |       |
                    v       v
            +-------+   +-------+
            |WIPEOUT|   | ENTER |  <-- MOVE_ENTER_CONFIRM
            |       |   |CONFIRM|
            +-------+   +-------+
                |           |
                v           v
        +===============+  +===============+
        |    ACTION     |  |    CONFIRM    |  phase = "confirm"
        | glassBroken=T |  +===============+
        | (Breach sub-  |      |
        |  state)       |      | State changes at ENTER_CONFIRM:
        +===============+      |   1. manaRots() -- clear H/B/R/A
        | [BREACH/      |      |   2. collectSpells()
        |  MELEE/       |      |   3. collectBodies()
        |  OVERKILL]    |      |   4. checkWin() -> stored
        |       |       |      |
        |       v       |      v
        | +----------+  |  +--------+
        | |END_BO    |  |  | COMMIT |  <-- MOVE_COMMIT
        | |(inEndBO) |  |  +--------+
        | +----------+  |      |
        |       |       |      +-- executeTriggers()
        +-------+-------+      |  result = checkWin()
                |               |
                v               |
        +=============+         |
        |ENTER_CONFIRM|  <------+ (if glassBroken, path
        +=============+           merges to ENTER_CONFIRM)
                |
                v
        +=============+
        |   CONFIRM   |  phase = "confirm"
        +=============+
                |
                v
            COMMIT
                |
        +-------+--------+
        | result != NONE  |     result == NONE
        |  (game over)    |         |
        v                 |         v
    GAME OVER             |  ++numTurns
                          |         |
                          |  +------+------+
                          |  | oppAttack>0 | oppAttack==0
                          |  +------+------+------+
                          |         |             |
                          |         v             v
                          |  +===========+   +==========+
                          |  |  DEFENSE  |   |  SWOOSH  |
                          |  | phase=    |   | (function|
                          |  | "defense" |   |  call)   |
                          |  +===========+   +==========+
                          |      |                |
                          |      | [DEFEND]       |
                          |      | oppAtk -= dmg  |
                          |      |                |
                          |      v                |
                          |  +----------+         |
                          |  | oppAtk=0 |         |
                          |  | END_DEF  |         |
                          |  +----------+         |
                          |      |                |
                          |      | collectBodies()|
                          |      |                |
                          |      v                |
                          |  +==========+         |
                          |  |  SWOOSH  |<--------+
                          |  +==========+
                          |      |
                          |      | Swoosh operations (in order):
                          |      | 1. phase = "action"
                          |      | 2. glassBroken = false
                          |      | 3. SEND_BEGIN_SWOOSH
                          |      | 4. For each TURN PLAYER's card:
                          |      |    a. Clear damage, disruptDamage
                          |      |    b. Tick construction (-1)
                          |      |    c. Tick delay (-1)
                          |      |    d. Tick lifespan (-1, kill if 0)
                          |      |    e. Set role (Default if hasAbility, else Inert)
                          |      |    f. Set blocking = card.defaultBlocking
                          |      |    g. Apply healthGained (capped at healthMax)
                          |      |    h. Apply chargeGained (capped at chargeMax)
                          |      |    i. Run beginOwnTurnScript
                          |      | 5. Process resonators (attack/gold)
                          |      | 6. incrementTurnNoProgressCounters()
                          |      | 7. executeTriggers()
                          |      | 8. SEND_END_SWOOSH
                          |      v
                          +-> ACTION (next player's turn)
```

### AS3 Key Functions and Code References

#### `processMove()` -- Central move dispatcher
```
State.as: processMove(update, animate, type, instId, targetId, cardId, ...)
Distinctive snippet: "if(type == C.MOVE_ASSIGN)"
```
Handles all move types: ASSIGN, UNASSIGN, BUY, SELL, MELEE, UNMELEE, DEFEND,
UNDEFEND, BREACH, UNBREACH, WIPEOUT, UNWIPEOUT, END_DEFENSE, ENTER_CONFIRM, COMMIT.

#### MOVE_WIPEOUT (Action -> Breach sub-state)
```
State.as line ~1855: "else if(type == C.MOVE_WIPEOUT)"
Distinctive snippet: "this.glassBroken = true; this.dispatch(update,animate,C.SEND_GLASSBROKEN)"
```
State changes:
- `glassBroken = true`
- All enemy defenders take full HP damage, marked as `DEADNESS_WBO`
- `turnMana.attack -= damage` for each defender
- Fragile defenders lose health

#### MOVE_ENTER_CONFIRM (Action -> Confirm)
```
State.as line ~1911: "else if(type == C.MOVE_ENTER_CONFIRM)"
Distinctive snippet: "this.endTurnObject = new EndTurnObject(this)"
```
State changes:
1. Create `EndTurnObject` (snapshot for undo)
2. No-progress counter logic (stalemate detection)
3. `phase = PHASE_CONFIRM`
4. `helper.update(this)`
5. `clearInstArrowIds()`
6. `manaRots()` -- clears Energy(H), Blue(B), Red(R); conditionally clears Attack(A)
7. `collectSpells()` -- removes spell card instances
8. `collectBodies()` -- removes dead instances
9. `checkWin()` stored in `endTurnObject.checkWin`
10. Dispatch warnings (will_lose, could_get_breached, etc.)

#### manaRots() -- Resource decay
```
State.as line ~3090: "private function manaRots(update:Boolean, animate:Boolean)"
Distinctive snippet: "this.turnMana.pool[C.MANA_H] = 0"
```
Clears: Energy (H), Blue (B), Red (R) unconditionally.
Conditionally clears Attack (A) only if `oppDefense == 0` (no enemy blockers).

#### MOVE_COMMIT (Confirm -> Defense/Swoosh)
```
State.as line ~1997: "else if(type == C.MOVE_COMMIT)"
Distinctive snippet: "this.executeTriggers(update,animate)"
```
State changes:
1. `executeTriggers()` -- run game triggers
2. `result = checkWin()` (or stored from endTurnObject)
3. If `result == NONE`:
   - `++numTurns` (switches active player via `turn` getter)
   - If `oppMana.attack == 0`: call `swoosh()` directly
   - If `oppMana.attack > 0`: `phase = PHASE_DEFENSE`
4. If `result != NONE`: game over

#### MOVE_END_DEFENSE (Defense -> Swoosh)
```
State.as line ~1900: "else if(type == C.MOVE_END_DEFENSE)"
Distinctive snippet: "this.collectBodies(update,animate); ... this.swoosh(update,animate)"
```
State changes:
1. No-progress counter for partially-damaged fragile blocker
2. `collectBodies()` -- remove dead cards
3. `swoosh()` -- full begin-turn processing

#### swoosh() -- Begin-turn processing
```
State.as line ~2582: "internal function swoosh(update:Boolean, animate:Boolean)"
Distinctive snippet: "this.phase = C.PHASE_ACTION; this.glassBroken = false; this.dispatch(update,animate,C.SEND_BEGIN_SWOOSH)"
```
State changes (in order):
1. `phase = PHASE_ACTION`
2. `glassBroken = false`
3. Dispatch `SEND_BEGIN_SWOOSH`
4. For each card owned by turn player:
   - Clear `damage` and `disruptDamage`
   - Tick `constructionTime` (if >0, decrement; sellable->inert if still building)
   - Tick `delay` (if >0, decrement; set role to Inert if still delayed)
   - Tick `lifespan` (if >0, decrement; kill and collect if reaches 0)
   - Set `role`: Default (if hasAbility), else Inert
   - Set `blocking = card.defaultBlocking`
   - Dispatch `SEND_INST_REFRESHED`
   - Apply `healthGained` (capped at `healthMax`)
   - Apply `chargeGained` (capped at `chargeMax`)
   - Run `beginOwnTurnScript`
5. Special card handling (Robo Santa, Condimus, etc.)
6. Process resonators (resonate/goldResonate -> attack/gold)
7. Special abilities (Years of Plenty/EMP/Deep Impact/etc.)
8. `SEND_END_SWOOSH_SORT`
9. Process annihilators (resonate pairs)
10. `incrementTurnNoProgressCounters()`
11. `executeTriggers()`
12. `SEND_END_SWOOSH`

#### checkWin() -- Game-over detection
```
State.as line ~3298: "private function checkWin() : int"
Distinctive snippet: "if(this.helper.ownAllUnitsTotal > 0 && this.helper.oppAllUnitsTotal == 0)"
```
Win conditions (non-objective games):
- Turn player has units, opponent has 0 -> turn player wins
- Turn player has 0, opponent has units -> opponent wins
- Both have 0 -> mutual elimination draw
- All opponent units are doomed -> turn player wins

---

## 3. C++ State Machine

```
File: source/engine/GameState.cpp (~2,388 lines)
```

### State Machine Diagram

```
                    GAME START
                        |
                        v
              beginPhase(p, m_activePhase)   [line 186]
                        |
                        v
                +===============+
                |    ACTION     |  m_activePhase = Phases::Action (0)
                +===============+
                    |       |
       [USE_ABILITY/BUY/   |
        SNIPE/CHILL/        |
        ASSIGN_FRONTLINE]   |
                    |       |
                    v       v
            +----------+ +----------+
            | WIPEOUT  | | END_PHASE|
            | (action) | | (action) |
            +----------+ +----------+
                |             |
                | endPhase()  | endPhase()
                | from Action | from Action
                v             v
        +===============+    |
        |    BREACH     |    |   (ourAttack>0 && canWipeout)
        | m_activePhase |    |   -> blockWithAllBlockers(enemy)
        | = Breach (2)  |    |   -> beginPhase(player, Breach)
        +===============+    |
        | [ASSIGN_BREACH/    |   (otherwise)
        |  UNDO_CHILL]  |    |   -> beginPhase(player, Confirm)
        |       |       |    |
        |       v       |    |
        | +----------+  |    |
        | | END_PHASE|  |    |
        | | (breach) |  |    |
        | +----------+  |    |
        |       |       |    |
        |  endPhase()   |    |
        |  from Breach  |    |
        +-------+-------+    |
                |             |
                v             v
        +===============+<---+
        |    CONFIRM    |  m_activePhase = Phases::Confirm (3)
        +===============+
                |
                | endPhase() from Confirm:
                |   1. m_turnNumber++
                |   2. removeKilledCards()
                |   3. card.endTurn() for all player's cards
                |   4. calculateGameOver()
                |
        +-------+--------+
        |  isGameOver()   |     NOT gameOver
        |                 |         |
        v                 |  +------+------+
    GAME OVER             |  | atk > 0     | atk == 0
    (attack zeroed)       |  +------+------+------+
                          |         |             |
                          |         v             v
                          |  +===========+  +==========+
                          |  |  DEFENSE  |  |  SWOOSH  |
                          |  | (enemy)   |  | (enemy)  |
                          |  +===========+  +==========+
                          |      |               |
                          |      | beginPhase(enemy, Defense):
                          |      | *** STATUS RESET ***
                          |      | For each enemy card:
                          |      |   if hasAbility/hasTargetAbility:
                          |      |     setStatus(Default)
                          |      |   else: setStatus(Inert)
                          |      |
                          |      | If enemy attack == 0:
                          |      |   endPhase() immediately
                          |      |   (skips to Swoosh)
                          |      |
                          |      | [ASSIGN_BLOCKER]
                          |      |
                          |      v
                          |  +----------+
                          |  | END_PHASE|  (enemy attack must be 0)
                          |  | (defense)|
                          |  +----------+
                          |      |
                          |      | endPhase() from Defense:
                          |      | -> beginPhase(player, Swoosh)
                          |      |
                          |      v
                          |  +==========+<--------+
                          |  |  SWOOSH  |
                          |  +==========+
                          |      |
                          |      | beginPhase(player, Swoosh):
                          |      |   1. beginTurn(player)
                          |      |   2. endPhase() immediately
                          |      |
                          |      | beginTurn() operations:
                          |      |   1. Reset Energy/Blue/Red/Attack to 0
                          |      |   2. m_canBreachFrozenCard = false
                          |      |   3. For each card: card.beginTurn()
                          |      |      a. m_sellable = false
                          |      |      b. m_damageTaken = 0
                          |      |      c. m_abilityUsedThisTurn = false
                          |      |      d. Clear targets/killed/created lists
                          |      |      e. Reduce lifespan (kill if 0)
                          |      |      f. Reduce delay
                          |      |      g. Reduce constructionTime
                          |      |      h. Apply healthGained (capped)
                          |      |      i. Set status (Default or Inert)
                          |      |      j. Clear chill
                          |      |   4. Run beginOwnTurnScripts
                          |      |   5. removeKilledCards()
                          |      |
                          |      | endPhase() from Swoosh:
                          |      | -> beginPhase(player, Action)
                          |      v
                          +-> ACTION (next player's turn)
```

### C++ Key Functions and Code References

#### `beginPhase()` -- Phase entry point
```
GameState.cpp line ~1278: "void GameState::beginPhase(const PlayerID player, const int newPhase)"
Distinctive snippet: "m_activePlayer = player; m_activePhase = newPhase;"
```
Sets active player and phase, then executes phase-specific entry logic.

#### `endPhase()` -- Phase transition dispatcher
```
GameState.cpp line ~1328: "void GameState::endPhase()"
Distinctive snippet: "switch (m_activePhase)"
```
Routes to the correct next phase based on current phase.

#### beginPhase(Defense) -- Status Reset
```
GameState.cpp line ~1287: "case Phases::Defense:"
Distinctive snippet: "card.setStatus(CardStatus::Default)" inside Defense case
```
State changes:
1. **STATUS RESET for defending player** (lines 1289-1306):
   For each non-dead, non-constructing, non-delayed card:
   - hasAbility or hasTargetAbility -> `setStatus(Default)`
   - else -> `setStatus(Inert)`
2. If enemy attack == 0: `endPhase()` immediately (skip defense)

#### beginPhase(Swoosh) -- Begin-turn processing
```
GameState.cpp line ~1315: "case Phases::Swoosh:"
Distinctive snippet: "beginTurn(player); endPhase();"
```
Calls `beginTurn()` then immediately transitions to Action.

#### beginTurn() -- Card refresh and script execution
```
GameState.cpp line ~1215: "void GameState::beginTurn(const PlayerID player)"
Distinctive snippet: "_getResources(player).set(Resources::Energy, 0)"
```
State changes (in order):
1. Reset resources: Energy=0, Blue=0, Red=0, Attack=0
2. `m_canBreachFrozenCard = false`
3. `card.beginTurn()` for all dead cards of player
4. `card.beginTurn()` for all alive cards (kill if died)
5. Run `beginOwnTurnScript` for eligible cards
6. `removeKilledCards()`

#### Card::beginTurn() -- Individual card refresh
```
Card.cpp line ~574: "void Card::beginTurn()"
Distinctive snippet: "m_sellable = false; m_damageTaken = 0; m_wasBreached = false;"
```
State changes (in order):
1. `m_sellable = false`, `m_damageTaken = 0`, `m_wasBreached = false`
2. `m_abilityUsedThisTurn = false`
3. Clear targets, killed list, created list
4. If `KilledThisTurn` -> set `Dead` and return
5. Reduce lifespan (kill if reaches 0)
6. Reduce delay
7. Reduce construction time
8. If not under construction and not delayed:
   - Apply `healthGained` (capped at `healthMax`)
   - Set status: Default (if hasAbility/hasTargetAbility), else Inert
   - Clear chill (`m_currentChill = 0`)

#### Card::endTurn()
```
Card.cpp line ~766: "void Card::endTurn()"
Distinctive snippet: "m_killedCardIDs.clear(); m_createdCardIDs.clear(); clearTarget();"
```
Minimal cleanup: clears killed/created lists and target.

#### endPhase(Action) -- Action -> Breach or Confirm
```
GameState.cpp line ~1350: "case Phases::Action:"
Distinctive snippet: "if ((ourAttack > 0) && canWipeout(player))"
```
Decision logic:
- If `ourAttack > 0` AND `canWipeout`: `blockWithAllBlockers(enemy)` then Breach
- Otherwise: Confirm

#### endPhase(Breach) -- Breach -> Confirm
```
GameState.cpp line ~1366: "case Phases::Breach:"
Distinctive snippet: "beginPhase(player, Phases::Confirm)"
```
Handles unbreachable/unoverkillable cards (zeroes attack), then transitions to Confirm.

#### endPhase(Confirm) -- Confirm -> Defense or Swoosh
```
GameState.cpp line ~1383: "case Phases::Confirm:"
Distinctive snippet: "m_turnNumber++; ... m_gameOver = calculateGameOver();"
```
State changes:
1. `m_turnNumber++`
2. `removeKilledCards()`
3. `card.endTurn()` for all player's cards
4. `calculateGameOver()`
5. If game over: zero attack
6. If `attack > 0`: `beginPhase(enemy, Defense)`
7. If `attack == 0`: `beginPhase(enemy, Swoosh)`

#### canWipeout() -- Breach eligibility check
```
GameState.cpp line ~1477: "bool GameState::canWipeout(const PlayerID player) const"
Distinctive snippet: "return (atk >= def)"
```
Returns true if: attack > 0, active player, Action phase, enemy has cards, attack >= enemy total defense.

#### blockWithAllBlockers() -- Mass blocking before breach
```
GameState.cpp line ~1502: "void GameState::blockWithAllBlockers(const PlayerID player)"
Distinctive snippet: "while (c < numCards(player)) { ... if (card.canBlock()) { blockWithCard(card); m_canBreachFrozenCard = true; c = 0; }"
```
Kills all enemy blockers, absorbing damage, before entering breach phase.

#### calculateGameOver()
```
GameState.cpp line ~1207: "bool GameState::calculateGameOver() const"
Distinctive snippet: "return p1Cards == 0 || p2Cards == 0"
```
Simple check: either player has zero total cards (alive + killed-this-turn).

#### doAction(WIPEOUT) -- POTENTIAL BUG: Fall-through
```
GameState.cpp line ~704: "case ActionTypes::WIPEOUT: { endPhase(); }"
Distinctive snippet: NO break; statement before "case ActionTypes::UNDO_CHILL:"
```
WIPEOUT calls `endPhase()` but has NO `break;`, falling through into UNDO_CHILL logic.
See Difference D-06 below.

---

## 4. Side-by-Side Transition Comparison

### T-01: Game Initialization

| Aspect | AS3 | C++ |
|---|---|---|
| Initial phase | `phase = PHASE_ACTION` | `m_activePhase` from JSON, then `beginPhase(m_activePlayer, m_activePhase)` |
| Turn counter | `numTurns = 0` | `m_turnNumber` from JSON |
| Active player | Derived: `(numTurns+1) % 2` | Explicit: `m_activePlayer` from JSON |
| Glass broken | `glassBroken = false` | No equivalent (Breach is separate phase) |
| beginPhase side-effects | None at init | `beginPhase()` runs phase-specific entry logic (e.g., Defense status reset) |

### T-02: Action -> Wipeout/Breach

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_WIPEOUT` | `ActionTypes::WIPEOUT` (calls `endPhase()`) |
| Phase change | Stays `PHASE_ACTION`, sets `glassBroken=true` | Transitions to `Phases::Breach` |
| Blocking | All defenders take damage inline | `blockWithAllBlockers()` called in `endPhase(Action)` |
| Damage application | Manual loop: `turnMana.attack -= damage` per defender | `blockWithCard()` loop with `takeDamage()` |
| Dead card handling | Defenders get `deadness = DEADNESS_WBO`, NOT immediately removed | Cards killed via `killCardByID(CauseOfDeath::Blocker)` |
| Return to action | `UNWIPEOUT` sets `glassBroken=false` | `UNDO_CHILL` handler checks `Phases::Breach`, reverts to Action |

### T-03: Action -> Confirm (no breach)

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_ENTER_CONFIRM` | `ActionTypes::END_PHASE` during Action (no wipeout) |
| Phase change | `phase = PHASE_CONFIRM` | `m_activePhase = Phases::Confirm` |
| Mana rot | `manaRots()`: clear H/B/R, conditionally A | **None at this transition** (mana cleared in `beginTurn()` during Swoosh) |
| Spell collection | `collectSpells()`: remove spell instances | **None** (C++ has no spell mechanic) |
| Body collection | `collectBodies()`: remove dead instances | **None at this transition** (`removeKilledCards()` in Confirm endPhase) |
| Win check | `checkWin()` stored in `endTurnObject` | **None at this transition** (checked at end of Confirm) |
| Warnings | Dispatched (will_lose, could_get_breached, etc.) | **None** (no UI layer) |

### T-04: Breach -> Confirm

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_ENTER_CONFIRM` (same as non-breach path) | `ActionTypes::END_PHASE` during Breach |
| Special handling | Same as T-03 (manaRots, collectSpells, etc.) | Zeroes attack if unbreachable/unoverkillable cards remain |
| Phase change | `phase = PHASE_CONFIRM` | `m_activePhase = Phases::Confirm` |

### T-05: Confirm -> Next Turn (no enemy attack)

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_COMMIT` | `ActionTypes::END_PHASE` during Confirm |
| Triggers | `executeTriggers()` before result check | **None** (C++ has no trigger system) |
| Turn increment | `++numTurns` | `m_turnNumber++` |
| Game-over check | `checkWin()` or stored `endTurnObject.checkWin` | `calculateGameOver()` |
| Card cleanup | Bodies already collected at ENTER_CONFIRM | `removeKilledCards()`, then `card.endTurn()` for all cards |
| Path when no attack | Direct call to `swoosh()` | `beginPhase(enemy, Phases::Swoosh)` |

### T-06: Confirm -> Defense (enemy has attack)

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_COMMIT` with `oppMana.attack > 0` | `endPhase(Confirm)` with `getAttack(player) > 0` |
| Phase change | `phase = PHASE_DEFENSE` | `beginPhase(enemy, Phases::Defense)` |
| Status reset | **NONE** -- statuses carry from Action/Swoosh | **YES** -- resets all defending player's card statuses (Default/Inert) |
| Auto-skip | None (defense always entered if attack > 0) | If enemy attack == 0, auto-calls `endPhase()` (skips to Swoosh) |

### T-07: Defense -> Swoosh

| Aspect | AS3 | C++ |
|---|---|---|
| Trigger | `MOVE_END_DEFENSE` (when `oppMana.attack == 0`) | `ActionTypes::END_PHASE` during Defense (enemy attack == 0) |
| Pre-swoosh cleanup | `collectBodies()` removes dead cards | None -- dead cards handled by `beginTurn()` lifespan/`removeKilledCards()` |
| Swoosh entry | Direct `swoosh()` function call | `beginPhase(player, Phases::Swoosh)` -> `beginTurn()` -> `endPhase()` |

### T-08: Swoosh -> Action

| Aspect | AS3 | C++ |
|---|---|---|
| Phase set | `phase = PHASE_ACTION` (line 2607 of swoosh) | `beginPhase(player, Phases::Action)` (via `endPhase(Swoosh)`) |
| Glass reset | `glassBroken = false` | N/A (Breach is separate phase) |
| Resource clear | **Not in swoosh** -- done earlier in manaRots() | `beginTurn()`: Energy=0, Blue=0, Red=0, **Attack=0** |
| Damage clear | `inst.damage = 0` per card | `m_damageTaken = 0` per card in `Card::beginTurn()` |
| Chill clear | `inst.disruptDamage = 0` per card | `m_currentChill = 0` per card in `Card::beginTurn()` |
| Construction tick | `--inst.constructionTime` | `m_constructionTime--` |
| Delay tick | `--inst.delay` | `--m_currentDelay` |
| Lifespan tick | `--inst.lifespan` (kill if 0) | `--m_lifespan` (kill if 0) |
| Status refresh | `role = Default/Inert`, `blocking = card.defaultBlocking` | `setStatus(Default/Inert)` |
| Health regen | `inst.health += card.healthGained` (capped) | `m_currentHealth += m_type.getHealthGained()` (capped) |
| Charge regen | `inst.charge += card.chargeGained` (capped) | Not explicit in `beginTurn()` (may be in scripts) |
| Scripts | `beginOwnTurnScript` per card | `beginOwnTurnScript` per eligible card |
| Resonators | Full annihilator/annihilatee pairing | **Not implemented** |
| Special cards | Robo Santa, EMP, Deep Impact, etc. | **Not implemented** |
| Triggers | `executeTriggers()` | **Not implemented** |
| Order | Status refresh BEFORE scripts | Status refresh BEFORE scripts (same) |

---

## 5. Identified Differences with Risk Assessment

### D-01: Defense Phase Status Reset (CRITICAL -- Known Bug)

**AS3 (ground truth):** No status reset at Defense phase entry. Cards retain their statuses
from the previous Action phase. Tapped units (role=Assigned from ability use) remain
Assigned through Defense. The `swoosh()` function (which runs AFTER defense) resets
statuses with `role = Default/Inert` and `blocking = card.defaultBlocking`.

```
AS3 swoosh() line ~2700: "inst.role = C.ROLE_DEFAULT" / "inst.role = C.ROLE_INERT"
AS3 swoosh() line ~2706: "inst.blocking = card.defaultBlocking"
```

**C++ (current):** `beginPhase(Defense)` resets ALL defending player's card statuses
BEFORE defense processing (lines 1289-1306).

```
C++ beginPhase() line ~1293-1306:
  "for (const auto & cardID : getCardIDs(player)) {
      Card & card = _getCardByID(cardID);
      if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed()) {
          if (card.getType().hasAbility() || card.getType().hasTargetAbility())
              card.setStatus(CardStatus::Default);
          else
              card.setStatus(CardStatus::Inert);
      }
  }"
```

**Impact:** Units that used abilities during their Action phase (status = Assigned) get
reset to Default before Defense. This means they can block when they should not be able
to (depending on their `assignedBlocking` vs `defaultBlocking`). For units where
`assignedBlocking = false` but `defaultBlocking = true` (e.g., Drones that were
"tapped" by having their ability used), the C++ engine incorrectly allows them to block.

**Risk:** HIGH. Affects every game with ability-using blockers. Known bug per commit `5bf57a8`
(Feb 13). Already documented in CLAUDE.md "Known Issues" and `docs/plans/bug-investigation-defense-reset.md`.

**Fix:** Remove lines 1289-1306 from `GameState::beginPhase()`. The AS3 ground truth
shows statuses should persist through Defense and only be reset during `swoosh()`.

---

### D-02: Breach as Sub-State vs First-Class Phase (MODERATE)

**AS3:** Breach is a sub-state of Action phase, controlled by `glassBroken` flag.
Player can WIPEOUT (set glassBroken=true), then BREACH/MELEE targets, then
ENTER_CONFIRM. Player can also UNWIPEOUT to revert.

```
AS3 line ~1857: "this.glassBroken = true"
AS3 line ~1896: "this.glassBroken = false" (UNWIPEOUT)
```

**C++:** Breach is a separate phase (`Phases::Breach = 2`). The transition is:
Action -> endPhase() -> `blockWithAllBlockers(enemy)` -> Breach -> player selects
breach targets -> endPhase() -> Confirm.

```
C++ endPhase(Action) line ~1356-1360:
  "blockWithAllBlockers(enemy); beginPhase(player, Phases::Breach);"
```

**Impact:** The C++ engine auto-blocks with ALL enemy blockers during the Action->Breach
transition. In AS3, the WIPEOUT move damages defenders but does not necessarily kill
them all instantly -- damage is applied but non-fragile units survive with accumulated
damage (they get `deadness = DEADNESS_WBO` which marks them as dead). The end result
is functionally equivalent for blocking, but the mechanics differ.

**Risk:** MODERATE. The C++ simplification combines wipeout + blocking into a single
atomic operation. This prevents partial wipeout states and UNWIPEOUT (undo). The AI
cannot undo a wipeout decision, which affects search quality but not game correctness
for fully committed positions.

---

### D-03: Mana Rot Timing (MODERATE)

**AS3:** Mana rot happens at `ENTER_CONFIRM` (before the player commits):
1. Energy, Blue, Red cleared unconditionally
2. Attack cleared only if `oppDefense == 0`
3. Spells collected (removed from play)

```
AS3 line ~1956: "this.manaRots(update,animate)"
AS3 manaRots() line ~3096-3117: "this.turnMana.pool[C.MANA_H] = 0" etc.
```

**C++:** Resource clearing happens in `beginTurn()` during Swoosh (next turn):
1. Energy, Blue, Red, **Attack** all cleared unconditionally

```
C++ beginTurn() line ~1220-1223:
  "_getResources(player).set(Resources::Energy, 0);
   _getResources(player).set(Resources::Blue, 0);
   _getResources(player).set(Resources::Red, 0);
   _getResources(player).set(Resources::Attack, 0);"
```

**Impact:**
- **Timing difference:** AS3 clears mana before Confirm (player sees warnings with correct
  resources). C++ clears at start of next turn.
- **Attack resource:** AS3 conditionally preserves Attack if enemy has blockers (it carries
  into defense). C++ unconditionally clears Attack at start of beginTurn. However, in C++
  the attack remaining after Confirm is used to decide Defense vs Swoosh transition, so
  the attack is effectively consumed. The C++ approach works because the endPhase(Confirm)
  checks `getAttack(player) > 0` BEFORE beginTurn clears it.
- **Functional equivalence:** For standard play, the result is equivalent -- resources
  that should decay do decay. The timing difference is cosmetic (UI-side effects only).

**Risk:** LOW-MODERATE. Functionally equivalent for game outcomes. Could matter if
intermediate state inspection is needed (e.g., during card scripts that check resources).

---

### D-04: Spell Collection Not Implemented in C++ (LOW)

**AS3:** `collectSpells()` removes spell card instances at ENTER_CONFIRM.

```
AS3 line ~3075: "private function collectSpells(update:Boolean, animate:Boolean)"
Distinctive snippet: "if(inst.card.cardType == C.CARDTYPE_SPELL)"
```

**C++:** No spell collection function exists. The C++ engine does not distinguish spell
cards from unit cards at the type level.

**Risk:** LOW. Spells (one-shot effects) are rare in competitive play. If the C++ engine
encounters spell cards, they would persist incorrectly. However, the AI training pipeline
primarily uses standard unit-based games.

---

### D-05: Trigger System Not Implemented in C++ (LOW)

**AS3:** `executeTriggers()` runs at two points:
1. During `swoosh()` (end of swoosh, for `duringSwoosh` triggers)
2. During `MOVE_COMMIT` (for non-swoosh triggers)

```
AS3 line ~4068: "internal function executeTriggers(update:Boolean, animate:Boolean)"
AS3 line ~4080: "if(!(trigger.duringSwoosh && this.phase != C.PHASE_ACTION))"
```

**C++:** No trigger system. Triggers are used in campaign/tutorial modes.

**Risk:** LOW. Triggers are not used in standard PvP games (self-play or competitive).

---

### D-06: WIPEOUT Action Fall-Through to UNDO_CHILL (MEDIUM — code smell)

> **VERIFICATION UPDATE**: Independent verification confirmed the fall-through exists but
> the original CRITICAL rating was overstated. The UNDO_CHILL guard code mitigates the
> worst-case scenario. Downgraded from CRITICAL to MEDIUM.

**AS3:** WIPEOUT is a clean operation: set `glassBroken=true`, damage defenders, done.

**C++:** The `doAction(WIPEOUT)` case has NO `break;` statement and falls through into
`UNDO_CHILL`:

```
C++ doAction() line ~704-714:
  "case ActionTypes::WIPEOUT:
  {
      endPhase();                          // transitions Action -> Breach
  }                                        // NO BREAK!
  case ActionTypes::UNDO_CHILL:
  {
      if (getActivePhase() == Phases::Breach)  // TRUE after endPhase()
      {
          beginPhase(getActivePlayer(), Phases::Action);  // transitions back
      }"
```

**Verification findings:** The fall-through IS real, but:
1. The UNDO_CHILL guard (`if getActivePhase() == Breach`) is designed for UNDO_CHILL's
   own use case — reverting a chill during breach — not to catch WIPEOUT fall-through
2. The UNDO_CHILL logic then searches for chill targets to undo (finds none in wipeout)
3. The net effect is: WIPEOUT → Breach → immediately back to Action + unnecessary chill search
4. This is **semantically wrong** (two unrelated actions conflated) but **functionally
   tolerable** because the guard code prevents a stuck-in-Breach state

**Impact:** MEDIUM code smell. The fall-through causes unnecessary UNDO_CHILL logic to
execute on every WIPEOUT, but guard code prevents catastrophic state corruption.
Recommend adding `break;` for correctness, but this is not a game-outcome-affecting bug.

**Risk:** CRITICAL to investigate. The `blockWithAllBlockers()` still executes (damage
is applied), but the phase bounces Breach -> Action. The UNDO_CHILL search loop may
have unintended side effects. Needs a `break;` statement after `endPhase()` in the
WIPEOUT case, OR this behavior needs to be verified as intentional.

**NOTE:** If this is intentional (wipeout = block all + stay in action for breach
targeting within action phase), it is a very confusing code pattern that should be
documented.

---

### D-07: Resonator/Annihilator System Not Implemented in C++ (LOW)

**AS3:** Swoosh processes resonators -- pairs of units that generate bonus
attack or gold when both are in play.

```
AS3 swoosh() line ~2874-2895:
  "if(card.resonate != null) { annihilators[card.resonate].push(inst); }"
AS3 swoosh() line ~3036-3069:
  "for(name in annihilators) { ... this.turnMana.attack += tempMana.attack; }"
```

**C++:** No resonator processing in `beginTurn()`.

**Risk:** LOW. Resonators are rarely used in competitive play. Affects unit pairs like
Symbiote + matching card. Self-play data generation and training are unaffected since
both sides use the same engine.

---

### D-08: Special Card Handling Missing in C++ (LOW)

**AS3:** Swoosh has hardcoded handling for: Robo Santa, Robo Santa 2016, Condimus,
Blastuit, Aniforge (randomized effects), EMP, Deep Impact, A.R. Groans, Glaciator
(special destruction/freeze effects), Aurb Magnifier (years of plenty).

**C++:** None of these special cards are handled. Their `beginOwnTurnScript` may
partially cover some effects if properly defined in cardLibrary.

**Risk:** LOW for AI training. These are exotic/event cards not in standard competitive play.

---

### D-09: Dead Card Body Collection Timing (LOW)

**AS3:** `collectBodies()` runs at two points:
1. At `ENTER_CONFIRM` (removes dead cards before confirm phase)
2. At `END_DEFENSE` (removes dead blockers before swoosh)

```
AS3 line ~2566: "private function collectBodies(update:Boolean, animate:Boolean)"
AS3 line ~1906: "this.collectBodies(update,animate)" (END_DEFENSE)
AS3 line ~1958: "this.collectBodies(update,animate)" (ENTER_CONFIRM)
```

**C++:** `removeKilledCards()` runs at two points:
1. End of `beginTurn()` (during Swoosh)
2. Start of `endPhase(Confirm)`

```
C++ beginTurn() line ~1275: "m_cards.removeKilledCards();"
C++ endPhase(Confirm) line ~1386: "m_cards.removeKilledCards();"
```

**Impact:** In AS3, dead cards are removed BEFORE swoosh (via END_DEFENSE collectBodies).
In C++, dead cards persist through Defense and are cleaned up during beginTurn (Swoosh).
The `Card::beginTurn()` function handles `KilledThisTurn -> Dead` transition, so dead
cards are properly skipped during refresh. The C++ `calculateGameOver()` counts both
alive and killed cards (`numCards + numKilledCards`), so dead cards still count toward
the player having "units."

**Risk:** LOW. Timing difference does not affect game outcomes. Dead cards in C++ are
tracked via `AliveStatus` and excluded from gameplay operations.

---

### D-10: Game-Over Check Timing and Method (LOW-MODERATE)

**AS3:** `checkWin()` runs:
1. At `ENTER_CONFIRM`: stored in `endTurnObject.checkWin`
2. At `MOVE_COMMIT`: uses stored value (or re-checks for objective games)

```
AS3 checkWin() line ~3311: "if(this.helper.ownAllUnitsTotal > 0 && this.helper.oppAllUnitsTotal == 0)"
```
Checks: own units > 0 AND opp units == 0, mutual elimination, all-doomed.

**C++:** `calculateGameOver()` runs at end of `endPhase(Confirm)`.

```
C++ calculateGameOver() line ~1207-1213:
  "CardID p1Cards = numCards(Players::Player_One) + numKilledCards(Players::Player_One);
   CardID p2Cards = numCards(Players::Player_Two) + numKilledCards(Players::Player_Two);
   return p1Cards == 0 || p2Cards == 0;"
```
Checks: either player has zero total cards (alive + killed-this-turn).

**Impact:**
- AS3 checks `ownAllUnitsTotal` (alive units) and `oppAllUnitsTotal` (alive units).
  Also detects "all doomed" (all opponent units have lifespan reaching 0).
- C++ counts `numCards + numKilledCards` -- includes killed-this-turn cards in the count.
  Does NOT check for all-doomed condition.
- The "all doomed" detection means AS3 can declare a win before units actually expire.
  C++ waits for units to actually die (lifespan tick kills them in swoosh).

**Risk:** LOW-MODERATE. The "all doomed" detection is an early-termination optimization
in AS3 that the C++ engine lacks. Games may run 1-2 extra turns before detecting the
inevitable outcome. Not a correctness issue -- the same player still wins.

---

### D-11: Stalemate/No-Progress Detection Missing in C++ (LOW)

**AS3:** Extensive no-progress counter system (`incrementTurnNoProgressCounters`,
`resetTurnNoProgressCounters`) tracks multiple levels of game activity to detect
stalemates and force draws.

**C++:** No stalemate detection. Games can theoretically loop forever.

**Risk:** LOW for AI. Self-play games have round limits. Tournament games have time limits.

---

### D-12: `canBlockAtStartOfPhase()` Logic Difference (LOW)

**AS3:** During Defense/Confirm: blocking determined by `inst.blocking` field only.
During Action: blocking includes units with `disruptDamage > 0`.

```
AS3 line ~4136: "private function canBlockAtStartOfPhase(inst:Inst) : Boolean"
  "if(this.phase == C.PHASE_DEFENSE || this.phase == C.PHASE_CONFIRM) return inst.blocking"
  "return inst.blocking || inst.disruptDamage > 0"
```

**C++:** `Card::canBlock()` checks `CardType::canBlock(assigned)` based on current status,
plus delay, construction, dead, frozen checks.

```
C++ Card.cpp line ~484: "bool Card::canBlock() const"
  "if (!getType().canBlock(getStatus() == CardStatus::Assigned)) return false"
```

**Impact:** The AS3 `canBlockAtStartOfPhase` function is used for UI ordering, not for
actual blocking legality. The C++ `canBlock()` is the actual blocking legality check.
These serve different purposes.

**Risk:** LOW. Different functions for different purposes.

---

## Summary of Differences by Risk Level

| Risk | ID | Description |
|---|---|---|
| **CRITICAL** | D-01 | Defense phase status reset (known bug, commit 5bf57a8) |
| **MEDIUM** | D-06 | WIPEOUT action fall-through to UNDO_CHILL (no break; verified non-catastrophic) |
| **MODERATE** | D-02 | Breach as sub-state (AS3) vs first-class phase (C++) |
| **LOW-MODERATE** | D-03 | Mana rot timing (ENTER_CONFIRM vs beginTurn) |
| **LOW-MODERATE** | D-10 | Game-over check method (all-doomed detection missing in C++) |
| **LOW** | D-04 | Spell collection not implemented |
| **LOW** | D-05 | Trigger system not implemented |
| **LOW** | D-07 | Resonator system not implemented |
| **LOW** | D-08 | Special card handling missing |
| **LOW** | D-09 | Dead card body collection timing |
| **LOW** | D-11 | Stalemate detection missing |
| **LOW** | D-12 | canBlockAtStartOfPhase logic difference |

### Recommended Priority Order for Fixes

1. **D-01 (Defense status reset):** Remove lines 1289-1306 from `beginPhase(Defense)`.
   Statuses should persist through Defense and only reset during Swoosh/beginTurn.

2. **D-06 (WIPEOUT fall-through):** Add `break;` after `endPhase()` in the WIPEOUT
   case of `doAction()`. Verified non-catastrophic (guard code in UNDO_CHILL prevents
   stuck state), but semantically wrong — two unrelated actions shouldn't be conflated.

3. **D-02 (Breach modeling):** No code fix needed; this is an architectural simplification.
   Document that Breach is atomic in C++ (no partial wipeout or undo).

4. **D-03 (Mana rot timing):** No fix needed if game outcomes are equivalent. Consider
   aligning if intermediate state accuracy matters for eval quality.

5. **D-10 (All-doomed):** Add optional early termination for all-doomed positions in
   `calculateGameOver()` for faster game resolution.
