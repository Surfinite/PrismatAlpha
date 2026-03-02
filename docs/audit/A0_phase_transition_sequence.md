# A0: Phase Transition Sequence Audit

> **Engine Logic Audit** -- Comparing AS3 (ground truth) vs C++ (AI engine)
> Generated: 2026-02-22
> Prerequisite: `P0_1_phase_transition_state_machines.md`

---

## Table of Contents

1. [Check C0: Phase Enumeration](#check-c0-phase-enumeration)
2. [Check C1: Action to Breach/Confirm Transition](#check-c1-action-to-breachconfirm-transition)
3. [Check C2: Confirm to Defense/Swoosh Transition](#check-c2-confirm-to-defenseswoosh-transition)
4. [Check C3: Defense to Swoosh Transition](#check-c3-defense-to-swoosh-transition)
5. [Check C4: Swoosh to Action Transition](#check-c4-swoosh-to-action-transition)
6. [Check C5: Turn Number Increment](#check-c5-turn-number-increment)
7. [Check C6: Game-Over Check Timing](#check-c6-game-over-check-timing)
8. [Concrete Trace: Full Turn Cycle with Attack > 0](#concrete-trace-full-turn-cycle-with-attack--0)
9. [Concrete Trace: Full Turn Cycle with Attack = 0](#concrete-trace-full-turn-cycle-with-attack--0-1)
10. [Summary Verdict Table](#summary-verdict-table)
11. [Appendix: Defense Phase Status Reset Deep Dive](#appendix-defense-phase-status-reset-deep-dive)

---

## Check C0: Phase Enumeration

### AS3 Code Path

**File:** `prismata_decompiled/scripts/mcds/engine/C.as`, lines 136-140

```actionscript
public static const PHASE_DEFENSE:String = "defense";
public static const PHASE_ACTION:String  = "action";
public static const PHASE_CONFIRM:String = "confirm";
```

AS3 has **3 named phases**. Breach is a sub-state of Action (controlled by `glassBroken` flag, State.as line 1857). Swoosh is a function call (`swoosh()`, State.as line 2582), not a phase assignment.

### C++ Code Path

**File:** `source/engine/Constants.h`, lines 11-13

```cpp
namespace Phases
{
    enum { Action=0, Defense=1, Breach=2, Confirm=3, Swoosh=4 };
}
```

C++ has **5 integer-based phases**. Breach and Swoosh are first-class phases.

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | Normal turn start | `phase = "action"` | `m_activePhase = 0 (Action)` | YES |
| 2 | Player triggers wipeout | `phase = "action"`, `glassBroken = true` | `m_activePhase = 2 (Breach)` | Structural difference, functional equivalent |

### Verdict: MATCH (functional)

The game states reachable are functionally equivalent. Both engines support Action, Defense, Breach sub-mode, Confirm, and Swoosh processing. The structural difference (AS3 encodes Breach/Swoosh inline; C++ gives them explicit phase IDs) does not affect game outcomes because the legal actions available in each state are equivalent.

---

## Check C1: Action to Breach/Confirm Transition

### AS3 Code Path (Action -> Breach sub-state)

**File:** `State.as`, lines 1855-1876 (`processMove`, MOVE_WIPEOUT)

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
    }
}
```

Behavior:
- Sets `glassBroken = true` (stays in "action" phase)
- Each defender: `damage = inst.health`, attack reduced, damage accumulated
- Fragile defenders lose actual health; non-fragile only accumulate `damage`
- Defenders marked `DEADNESS_WBO` (NOT removed from table yet)
- **Reversible** via `MOVE_UNWIPEOUT` (line 1877)

### AS3 Code Path (Action -> Confirm, no breach)

**File:** `State.as`, lines 1911-1961 (`processMove`, MOVE_ENTER_CONFIRM)

```actionscript
this.phase = C.PHASE_CONFIRM;
this.helper.update(this);
this.clearInstArrowIds();
this.manaRots(update,animate);
this.collectSpells(update,animate);
this.collectBodies(update,animate);
this.endTurnObject.checkWin = this.checkWin();
```

### C++ Code Path

**File:** `GameState.cpp`, lines 1350-1364 (`endPhase()`, Action case)

```cpp
case Phases::Action:
{
    HealthType ourAttack = getAttack(getActivePlayer());
    if ((ourAttack > 0) && canWipeout(player))
    {
        blockWithAllBlockers(enemy);
        beginPhase(player, Phases::Breach);
        break;
    }
    beginPhase(player, Phases::Confirm);
    break;
}
```

**File:** `GameState.cpp`, lines 1477-1487 (`canWipeout`)

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

### Comparison

| Aspect | AS3 | C++ |
|--------|-----|-----|
| Wipeout test | attack >= defense (helper/UI gated) | `canWipeout()`: attack >= `getTotalAvailableDefense()` |
| Blocking on wipeout | Marks `DEADNESS_WBO`, subtracts from attack inline | `blockWithAllBlockers()` -> `blockWithCard()` kills via `killCardByID()` |
| Dead card persistence | Remain in table until `collectBodies()` | `KilledThisTurn` status, moved to killed list immediately |
| Undo support | `MOVE_UNWIPEOUT` (full reversal) | No undo (Breach is committed) |
| Confirm entry processing | `manaRots()`, `collectSpells()`, `collectBodies()`, `checkWin()` | None (deferred to Confirm endPhase) |

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | 5 attack vs Wall (5 HP, blocker) | `glassBroken=true`, Wall: `damage=5, deadness=WBO`, attack=0 | `blockWithAllBlockers()` kills Wall, attack=0, `Phases::Breach` | YES (Wall dead, attack consumed) |
| 2 | 3 attack vs Wall (5 HP) -- no wipeout | ENTER_CONFIRM, phase="confirm", manaRots clears H/B/R | `canWipeout` false (3<5), enters `Phases::Confirm` | YES (enter confirm, attack preserved) |
| 3 | 10 attack vs Wall(5)+Drone(1) -- wipeout | `glassBroken=true`, Wall: dmg=5, Drone: dmg=1, attack=4 remaining | `blockWithAllBlockers` kills both (5+1=6 absorbed), attack=4, `Phases::Breach` | YES |

### Verdict: MATCH

Core wipeout/confirm transition is functionally equivalent. Differences are structural (dead card handling, undo support, timing of mana rot) and do not affect game outcomes.

**Note:** The WIPEOUT fall-through bug in `doAction()` (line 704, no `break;` before UNDO_CHILL) is a code-level issue. The search engine uses `endPhase()` directly, so the bug only manifests via the `doAction(WIPEOUT)` path. Rated MEDIUM per D-06 in P0.1.

---

## Check C2: Confirm to Defense/Swoosh Transition

### AS3 Code Path

**File:** `State.as`, lines 1997-2028 (`processMove`, MOVE_COMMIT)

```actionscript
this.executeTriggers(update,animate);
this.result = this.endTurnObject.checkWin;   // Stored from ENTER_CONFIRM
if(this.result == C.COLOR_NONE)
{
    ++this.numTurns;                          // Flips active player
    if(this.oppMana.attack == 0)              // Previous player's attack
    {
        this.swoosh(update,animate);          // Skip defense
    }
    else
    {
        this.phase = C.PHASE_DEFENSE;         // Enter defense
    }
}
```

Key: After `++numTurns`, `turn = (numTurns + 1) % 2` flips. `oppMana` now references the **committing** player's resources. So `oppMana.attack` is the attack of the player who just ended their turn.

### C++ Code Path

**File:** `GameState.cpp`, lines 1383-1413 (`endPhase()`, Confirm case)

```cpp
case Phases::Confirm:
{
    m_turnNumber++;
    m_cards.removeKilledCards();
    for (const auto & cardID : getCardIDs(player))
        _getCardByID(cardID).endTurn();
    m_gameOver = calculateGameOver();
    if (isGameOver())
        m_resources[player].set(Resources::Attack, 0);
    if (getAttack(player) > 0)
    {
        PRISMATA_ASSERT(getAttack(player) < getTotalAvailableDefense(enemy), ...);
        beginPhase(enemy, Phases::Defense);
    }
    else
    {
        beginPhase(enemy, Phases::Swoosh);
    }
    break;
}
```

Note: `player` is captured at top of `endPhase()` before `m_turnNumber` increment. `getAttack(player)` checks the committing player's remaining attack.

### Comparison

| Aspect | AS3 | C++ |
|--------|-----|-----|
| Turn increment | `++numTurns` | `m_turnNumber++` |
| Attack check | `oppMana.attack` (commit player, after turn flip) | `getAttack(player)` (commit player, var captured before flip) |
| Defense entry | `phase = PHASE_DEFENSE` | `beginPhase(enemy, Phases::Defense)` |
| Swoosh entry | Direct `swoosh()` call | `beginPhase(enemy, Phases::Swoosh)` |
| Triggers | `executeTriggers()` before win check | Not implemented |
| Win check | Stored from ENTER_CONFIRM (or re-checked for objectives) | `calculateGameOver()` after `removeKilledCards` and `endTurn` |
| Card cleanup | Already done at ENTER_CONFIRM | `removeKilledCards()` + `card.endTurn()` |

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | Commit with 3 attack, enemy has Wall(5 HP) | `++numTurns`, `oppMana.attack=3 > 0`, `phase="defense"` | `m_turnNumber++`, `getAttack(player)=3 > 0`, `beginPhase(enemy, Defense)` | YES |
| 2 | Commit with 0 attack | `++numTurns`, `oppMana.attack=0`, calls `swoosh()` | `m_turnNumber++`, `getAttack(player)=0`, `beginPhase(enemy, Swoosh)` | YES |
| 3 | Commit, game over (opp 0 units) | `result != COLOR_NONE`, game over | `calculateGameOver()` true, attack zeroed, no further transition | YES |

### Verdict: MATCH

The Confirm-to-Defense/Swoosh transition is functionally equivalent. The attack direction check is semantically identical despite different reference frames. The new active player enters Defense or Swoosh in both engines.

---

## Check C3: Defense to Swoosh Transition

### AS3 Code Path

**File:** `State.as`, lines 1900-1909 (`processMove`, MOVE_END_DEFENSE)

```actionscript
else if(type == C.MOVE_END_DEFENSE)
{
    // stalemate counter for partially-damaged fragile blockers
    this.collectBodies(update,animate);   // Remove dead blockers
    this.swoosh(update,animate);          // Begin-turn processing
}
```

**AS3 Defense eligibility (MOVE_DEFEND):**

**File:** `Controller.as`, lines 190-197

```actionscript
if(this.state.phase == C.PHASE_DEFENSE)
{
    if(inst.owner != this.state.turn)
        // ERROR_OPPONENT
    if(!inst.blocking)
        // ERROR: non-blocker / disrupted / construction / busy
```

The check is `inst.blocking` -- a boolean set to `card.assignedBlocking` when ability is used (State.as line 1451) and to `card.defaultBlocking` during swoosh (State.as line 2706).

**AS3 ability use (MOVE_ASSIGN):**

**File:** `State.as`, lines 1448-1452

```actionscript
inst.role = C.ROLE_ASSIGNED;
inst.blocking = card.assignedBlocking;    // Critical: changes blocking eligibility
```

### C++ Code Path

**File:** `GameState.cpp`, lines 1335-1342 (`endPhase()`, Defense case)

```cpp
case Phases::Defense:
{
    PRISMATA_ASSERT(getAttack(enemy) == 0, "Cannot end DEFENSE phase with remaining enemy damage");
    beginPhase(player, Phases::Swoosh);
    break;
}
```

**File:** `GameState.cpp`, lines 1287-1313 (`beginPhase()`, Defense case)

```cpp
case Phases::Defense:
{
    // *** STATUS RESET (lines 1289-1306) -- BUG ***
    for (const auto & cardID : getCardIDs(player))
    {
        Card & card = _getCardByID(cardID);
        if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed())
        {
            if (card.getType().hasAbility() || card.getType().hasTargetAbility())
                card.setStatus(CardStatus::Default);
            else
                card.setStatus(CardStatus::Inert);
        }
    }
    if (getAttack(getEnemy(player)) == 0) { endPhase(); }
    break;
}
```

**C++ blocking eligibility:**

**File:** `Card.cpp`, lines 484-511

```cpp
bool Card::canBlock() const
{
    if (!getType().canBlock(getStatus() == CardStatus::Assigned))
        return false;
    if (getCurrentDelay() > 0) return false;
    if (isUnderConstruction()) return false;
    if (isDead()) return false;
    if (isFrozen()) return false;
    return true;
}
```

`CardType::canBlock(bool assigned)` returns `getAssignedBlocking()` if status is Assigned, `getDefaultBlocking()` if not.

### CRITICAL MISMATCH: Defense Phase Status Reset

See **[Appendix: Defense Phase Status Reset Deep Dive](#appendix-defense-phase-status-reset-deep-dive)** for the full derivation.

**Summary:** The status reset at `beginPhase(Defense)` (lines 1289-1306, commit 5bf57a8) is **incorrect**. It resets Assigned cards to Default before defense, changing their blocking eligibility via `canBlock()`. In AS3, ability use sets `inst.blocking = card.assignedBlocking` (line 1451), and the defense check uses `inst.blocking` (Controller.as line 197). Without the reset, C++ correctly models this: Assigned status -> `canBlock(true)` -> `getAssignedBlocking()`.

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected (with reset) | C++ Expected (without reset) |
|---|----------|-------------|---------------------------|------------------------------|
| 1 | Drone used ability (Assigned), enemy has 1 attack | `inst.blocking = false` (assignedBlocking), CANNOT defend | Status reset to Default, `canBlock(false)` -> `defaultBlocking=true`, CAN defend | Status stays Assigned, `canBlock(true)` -> `assignedBlocking=false`, CANNOT defend |
| 2 | Wall never used ability (Default), enemy has 3 attack | `inst.blocking = true` (defaultBlocking), CAN defend | Status stays Default (already Default), CAN defend | Status stays Default, CAN defend |
| 3 | Steelsplitter used ability (Assigned), enemy has 2 attack | `inst.blocking = assignedBlocking`, check `assignedBlocking` value for Steelsplitter | Reset to Default, checks `defaultBlocking` | Stays Assigned, checks `assignedBlocking` |
| 4 | Defense end -> Swoosh | `collectBodies()` then `swoosh()` | `endPhase(Defense)` -> `beginPhase(player, Swoosh)` -> `beginTurn()` -> `endPhase()` | Same as with reset (no difference at transition) |

### Verdict: MISMATCH

**Severity:** HIGH
**Root cause:** Status reset at `beginPhase(Defense)`, lines 1289-1306 of `GameState.cpp`
**Fix:** Remove lines 1289-1306. The status must persist through Defense, matching AS3 behavior where `inst.blocking = card.assignedBlocking` is set at ability use and checked during defense.
**Affected unit count:** Every unit with `assignedBlocking != defaultBlocking`. Common examples: Drone (defaultBlocking=true, assignedBlocking=false), and any unit whose blocking changes when tapped.
**Regression test:** Drone uses ability in Action phase, enemy has attack, Drone should NOT be able to block during Defense.

---

## Check C4: Swoosh to Action Transition

### AS3 Code Path

**File:** `State.as`, lines 2607-2608 (top of `swoosh()`)

```actionscript
this.phase = C.PHASE_ACTION;
this.glassBroken = false;
```

Swoosh performs all begin-turn processing (card refresh, construction tick, lifespan tick, health/charge gain, scripts, resonators, triggers) and then control naturally falls through to the caller, which either proceeds to the new Action phase or updates the helper.

### C++ Code Path

**File:** `GameState.cpp`, lines 1315-1320 (`beginPhase()`, Swoosh case)

```cpp
case Phases::Swoosh:
{
    beginTurn(player);
    endPhase();    // -> endPhase(Swoosh) -> beginPhase(player, Action)
    break;
}
```

**File:** `GameState.cpp`, lines 1344-1348 (`endPhase()`, Swoosh case)

```cpp
case Phases::Swoosh:
{
    beginPhase(player, Phases::Action);
    break;
}
```

### Comparison

| Aspect | AS3 | C++ |
|--------|-----|-----|
| Phase set | `phase = "action"` (line 2607) | `beginPhase(player, Phases::Action)` via `endPhase(Swoosh)` |
| Glass reset | `glassBroken = false` (line 2608) | N/A (Breach is a separate phase, no flag) |
| Begin-turn processing | Inline in `swoosh()`: damage clear, construction tick, delay tick, lifespan tick, status refresh, health/charge gain, scripts, resonators, triggers | `beginTurn()`: resource reset, `card.beginTurn()` (lifespan, delay, construction, health, status, chill clear), scripts, `removeKilledCards()` |
| Resource reset | Not in swoosh -- done earlier in `manaRots()` at ENTER_CONFIRM | `beginTurn()`: Energy=0, Blue=0, Red=0, Attack=0 |
| Resonators | Full annihilator/annihilatee pairing + gold resonators | Not implemented |
| Triggers | `executeTriggers()` at end of swoosh | Not implemented |
| Special cards | Hardcoded: Robo Santa, Condimus, Blastuit, Aniforge, EMP, Deep Impact, A.R. Groans, Glaciator | Not implemented |

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | Swoosh with Drone (default unit) | `phase="action"`, Drone: `role="default"`, `blocking=true`, `damage=0` | `Phases::Action`, Drone: `status=Default`, `damageTaken=0`, `chill=0` | YES |
| 2 | Swoosh with Tarsier under construction (1 turn left) | `constructionTime` decremented to 0, role set to Default, begins producing attack on NEXT swoosh | `m_constructionTime--` to 0, status set to Default (if has ability) or Inert | YES |
| 3 | Swoosh with unit at lifespan=1 | `lifespan` decremented to 0, `deadness="aged"`, deleted from table | `m_lifespan--` to 0, killed via `CauseOfDeath::Lifespan`, removed by `removeKilledCards()` | YES |

### Verdict: MATCH (for standard units)

The Swoosh-to-Action transition is functionally equivalent for all standard competitive units. Differences in resource reset timing (AS3: manaRots at ENTER_CONFIRM; C++: beginTurn at Swoosh) are harmless because the same resources are zeroed before the next Action. Missing systems (resonators, triggers, special cards) only affect exotic/event cards not used in competitive play or self-play.

---

## Check C5: Turn Number Increment

### AS3 Code Path

**File:** `State.as`, line 2016

```actionscript
++this.numTurns;
```

Located inside MOVE_COMMIT, AFTER `executeTriggers()` and game-over check, BEFORE defense/swoosh transition. The `turn` getter derives active player: `(numTurns + 1) % 2`.

`numTurns` starts at 0. `turn` at numTurns=0 is `(0+1)%2 = 1` (Black/Player 2). After `++numTurns` (numTurns=1), `turn = (1+1)%2 = 0` (White/Player 1).

### C++ Code Path

**File:** `GameState.cpp`, line 1385

```cpp
m_turnNumber++;
```

Located at the START of `endPhase(Confirm)`, BEFORE `removeKilledCards()`, `endTurn()`, and `calculateGameOver()`. The active player is tracked explicitly via `m_activePlayer` (set in `beginPhase()`).

### Comparison

| Aspect | AS3 | C++ |
|--------|-----|-----|
| When | After game-over check, before transition | Before cleanup and game-over check |
| Initial value | 0 | From JSON (typically 0) |
| Player derivation | `turn = (numTurns + 1) % 2` | `m_activePlayer` set explicitly |
| Ordering vs game-over | Increment only if `result == COLOR_NONE` | Increment unconditionally (game-over checked after) |

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | Normal commit (no game over) | `numTurns` increments | `m_turnNumber` increments | YES |
| 2 | Commit causing game over | `numTurns` NOT incremented (result != NONE) | `m_turnNumber` incremented even on game over | MISMATCH (turn count differs at game end) |
| 3 | After 4 player-turns (2 full rounds) | `numTurns = 4` | `m_turnNumber = 4` (if no game over) | YES |

### Verdict: MATCH (with minor edge-case mismatch)

For active games, the turn counter behavior is equivalent. The mismatch on game-over is that C++ increments unconditionally (line 1385 is before the calculateGameOver check on line 1394), while AS3 only increments if the game continues. This has **no gameplay impact** because the turn counter is not consulted after game-over. It could affect turn-count-based metrics (reported game length off by 1).

**Severity:** LOW (cosmetic, no gameplay effect)

---

## Check C6: Game-Over Check Timing

### AS3 Code Path

Game-over is checked at TWO points:

**Point 1:** At ENTER_CONFIRM (stored for later use)

**File:** `State.as`, line 1961

```actionscript
this.endTurnObject.checkWin = this.checkWin();
```

**Point 2:** At MOVE_COMMIT (uses stored value or re-checks for objectives)

**File:** `State.as`, lines 2002-2013

```actionscript
if(this.objectives != null)
{
    this.result = this.checkWin();   // Re-check for objective games
}
else
{
    this.result = this.endTurnObject.checkWin;  // Use stored value
}
```

**`checkWin()` logic** (State.as lines 3298-3327, non-objective games):

```actionscript
if(this.helper.ownAllUnitsTotal > 0 && this.helper.oppAllUnitsTotal == 0)
    return this.turn;                    // Turn player wins
if(this.helper.ownAllUnitsTotal == 0 && this.helper.oppAllUnitsTotal > 0)
    return 1 - this.turn;               // Opponent wins
if(this.helper.ownAllUnitsTotal == 0 && this.helper.oppAllUnitsTotal == 0)
    return C.COLOR_DRAW_MUTUAL_ELIMINATION;
if(this.helper.allOppUnitsDoomed)
    return this.turn;                    // Turn player wins (all opp units will die)
return C.COLOR_NONE;
```

### C++ Code Path

Game-over is checked at ONE point:

**File:** `GameState.cpp`, line 1394

```cpp
m_gameOver = calculateGameOver();
```

Located in `endPhase(Confirm)`, AFTER `m_turnNumber++`, `removeKilledCards()`, and `endTurn()`.

**`calculateGameOver()` logic** (GameState.cpp lines 1207-1213):

```cpp
bool GameState::calculateGameOver() const
{
    CardID p1Cards = numCards(Players::Player_One) + numKilledCards(Players::Player_One);
    CardID p2Cards = numCards(Players::Player_Two) + numKilledCards(Players::Player_Two);
    return p1Cards == 0 || p2Cards == 0;
}
```

### Comparison

| Aspect | AS3 | C++ |
|--------|-----|-----|
| When checked | ENTER_CONFIRM (stored) + COMMIT (used) | endPhase(Confirm), after cleanup |
| What is checked | `ownAllUnitsTotal` and `oppAllUnitsTotal` (alive units) | `numCards + numKilledCards` (alive + killed-this-turn) |
| Mutual elimination | Explicit: `ownAll == 0 && oppAll == 0` -> DRAW | Implicit: both p1Cards and p2Cards == 0 triggers game-over, but no draw distinction |
| All-doomed detection | `allOppUnitsDoomed` -> turn player wins early | Not implemented |
| Stalemate detection | Full no-progress counter system | Not implemented |

### Test Cases

| # | Scenario | AS3 Expected | C++ Expected | Match? |
|---|----------|-------------|-------------|--------|
| 1 | Player eliminates all enemy units | `checkWin()` at ENTER_CONFIRM: `oppAllUnitsTotal=0` -> turn player wins | After cleanup: `p2Cards=0` -> game over | YES (same outcome) |
| 2 | Both players lose all units same turn | `ownAll=0, oppAll=0` -> `COLOR_DRAW_MUTUAL_ELIMINATION` | `p1Cards=0` -> game over (no draw distinction) | MISMATCH (draw vs generic game-over) |
| 3 | All enemy units have lifespan=1 (doomed) | `allOppUnitsDoomed=true` -> turn player wins immediately | No detection -- game continues 1+ more turns until units actually die | MISMATCH (timing, same final outcome) |
| 4 | Stalemate (no progress for 40 turns) | Draw declared via stalemate counters | Game continues indefinitely (tournament round limit prevents infinite loop) | MISMATCH (missing feature, mitigated by tournament limits) |

### Verdict: MATCH (with feature gaps)

For standard game-ending conditions (one player eliminated), the engines agree. The C++ engine lacks:
1. **All-doomed early termination** -- games run 1-2 extra turns (no outcome change)
2. **Mutual elimination draw** -- C++ reports generic game-over, not a draw
3. **Stalemate detection** -- mitigated by tournament round limits

**Severity:** LOW for AI training. Games end correctly; the timing and classification of edge-case endings differ slightly.

---

## Concrete Trace: Full Turn Cycle with Attack > 0

### Scenario

Player A (White, active) has 3 Tarsiers (each producing 1 attack) and 2 Drones. Player B (Black) has 1 Wall (5 HP blocker) and 3 Drones. Player A assigns all 3 Tarsiers, buying nothing, ending with 3 attack. Player B must defend.

### AS3 Trace

```
State: numTurns=2, turn=(2+1)%2=1 (Black... wait)
```

Let me recalibrate. For the trace, assume numTurns=0, so turn=1 (Black is first). After ++numTurns, turn=0 (White). Let me use explicit player labels instead.

**Starting state:** Player A's Action phase, 3 attack accumulated.

1. **Player A: MOVE_ENTER_CONFIRM**
   - `endTurnObject` created (snapshot)
   - `phase = "confirm"`
   - `manaRots()`: Energy=0, Blue=0, Red=0. Attack NOT cleared (oppDefense > 0, Wall exists)
   - `collectSpells()`: no spells
   - `collectBodies()`: no dead cards
   - `checkWin()`: both players have units -> `COLOR_NONE`, stored

2. **Player A: MOVE_COMMIT**
   - `executeTriggers()`: no triggers
   - `result = endTurnObject.checkWin = COLOR_NONE`
   - `++numTurns` (active player flips to Player B)
   - `oppMana.attack = 3 > 0` (Player A's attack remains)
   - `phase = "defense"` (Player B must defend)

3. **Player B: Defense Phase**
   - Player B clicks Wall to defend: MOVE_DEFEND(Wall)
   - `damage = min(Wall.health=5, oppMana.attack=3) = 3`
   - `oppMana.attack -= 3` -> 0
   - `Wall.damage += 3` -> 3
   - Wall is NOT fragile, health unchanged (5), `damageItCanTake = 5 - 3 = 2 > 0`
   - Wall absorbs, NOT dead
   - `oppMana.attack = 0` -> `inEndDefense = true`

4. **Player B: MOVE_END_DEFENSE**
   - `collectBodies()`: no dead cards (Wall survived)
   - `swoosh()`: Player B's begin-turn
     - `phase = "action"`, `glassBroken = false`
     - For each Player B card: clear damage, tick construction/delay/lifespan, set role, set blocking
     - Wall: `damage = 0` cleared, `role = "default"`, `blocking = true`
     - Drones: `role = "default"`, `blocking = true`
     - Scripts run, resonators processed

5. **Player B: Action Phase begins**

### C++ Trace

**Starting state:** Player A active, Action phase, 3 attack.

1. **Player A: doAction(END_PHASE)** -- endPhase() from Action
   - `ourAttack = getAttack(playerA) = 3`
   - `canWipeout(playerA)`: attack=3, defense=`getTotalAvailableDefense(playerB)` = Wall.health=5 -> 3 < 5 -> **false**
   - `beginPhase(playerA, Phases::Confirm)`: no entry processing for Confirm

2. **endPhase() from Confirm**
   - `m_turnNumber++`
   - `removeKilledCards()`: none
   - `card.endTurn()` for all Player A cards: clears killed/created lists, targets
   - `calculateGameOver()`: both players have cards -> false
   - `getAttack(playerA) = 3 > 0`
   - ASSERT: `3 < getTotalAvailableDefense(playerB) = 5` -> true (passes)
   - `beginPhase(playerB, Phases::Defense)`

3. **beginPhase(playerB, Defense)**
   - **STATUS RESET (BUG):** For each Player B card:
     - Wall: hasAbility? No -> `setStatus(Inert)` (Wall has no ability)
     - Drones: hasAbility? Yes (produce gold) -> `setStatus(Default)`
   - `getAttack(getEnemy(playerB)) = getAttack(playerA) = 3 > 0` -> does NOT auto-skip

4. **Player B: doAction(ASSIGN_BLOCKER, Wall)**
   - `isLegal`: `getAttack(enemy)=3 > 0`, `Phases::Defense`, `Wall.canBlock()`
   - `Wall.canBlock()`: `canBlock(status==Assigned)` = `canBlock(false)` (Wall is Inert after reset)
   - For Wall: `getType().canBlock(false)` = `getDefaultBlocking()` -- depends on Wall's defaultBlocking
   - **Wall IS a blocker** (defaultBlocking = true), so canBlock returns true
   - `blockWithCard(Wall)`: damage = min(3, 5) = 3, Wall takes 3 damage, health=2, NOT dead
   - Attack = 3 - 3 = 0

5. **Player B: doAction(END_PHASE)** -- endPhase() from Defense
   - ASSERT: `getAttack(enemy) == 0` -> true (passes)
   - `beginPhase(playerB, Phases::Swoosh)`

6. **beginPhase(playerB, Swoosh)**
   - `beginTurn(playerB)`:
     - Resources: Energy=0, Blue=0, Red=0, Attack=0
     - `card.beginTurn()` for each Player B card:
       - Wall: `damageTaken=0`, lifespan/delay/construction untouched, health += healthGained (0 for Wall), `status=Inert` (no ability)
       - Drones: `damageTaken=0`, `status=Default`, `chill=0`
     - Scripts: Drone beginOwnTurnScript (produce 1 gold each)
     - `removeKilledCards()`: none
   - `endPhase()` -> `beginPhase(playerB, Phases::Action)`

7. **Player B: Action Phase begins**

### Trace Comparison

| Step | AS3 | C++ | Match? |
|------|-----|-----|--------|
| Enter Confirm | manaRots + collectBodies + checkWin | No processing | Timing diff, OK |
| Turn increment | After game-over check | Before game-over check | Edge case on game-over turns |
| Attack check for defense | `oppMana.attack = 3 > 0` | `getAttack(playerA) = 3 > 0` | YES |
| Defense entry | `phase = "defense"`, NO status reset | Status reset (BUG): resets all to Default/Inert | **MISMATCH** |
| Wall blocking | `inst.blocking = true` (defaultBlocking) | `canBlock(false)` = `defaultBlocking` = true | YES (Wall was not tapped) |
| Wall takes 3 damage | `damage=3, Wall.damage=3, health stays 5` | `takeDamage(3)`, health=5-3=2 (direct health reduction) | **MISMATCH** (damage model) |
| End defense -> Swoosh | `collectBodies()` then `swoosh()` | `beginPhase(Swoosh)` -> `beginTurn()` | Equivalent |
| Swoosh card refresh | role, blocking, damage cleared, scripts | status, damageTaken, chill cleared, scripts | Equivalent |

**Damage model note:** AS3 accumulates `inst.damage` separately from `inst.health` (non-fragile units keep full health, damage is a separate counter). C++ reduces `m_currentHealth` directly. For non-fragile units, this is a structural difference: AS3 tracks "potential damage absorbed" while C++ reduces actual health. The game outcome is equivalent because both engines kill the unit when accumulated damage equals health, and surviving units have their damage cleared in swoosh. For fragile units, both reduce health directly.

---

## Concrete Trace: Full Turn Cycle with Attack = 0

### Scenario

Player A (active) has 3 Drones, no attackers. Player B has 3 Drones. Player A buys something and ends turn with 0 attack.

### AS3 Trace

1. **Player A: MOVE_ENTER_CONFIRM**
   - `phase = "confirm"`
   - `manaRots()`: Energy=0, Blue=0, Red=0. Attack = 0, `oppDefense > 0` check is irrelevant (attack already 0)
   - `checkWin()`: both have units -> `COLOR_NONE`

2. **Player A: MOVE_COMMIT**
   - `result = COLOR_NONE`
   - `++numTurns` (Player B now active)
   - `oppMana.attack = 0` (Player A has no attack)
   - **Skips defense**, calls `swoosh()` directly

3. **swoosh()** for Player B
   - `phase = "action"`, `glassBroken = false`
   - Card refresh for all Player B cards
   - Scripts, resonators

4. **Player B: Action Phase**

### C++ Trace

1. **Player A: doAction(END_PHASE)** from Action
   - `ourAttack = 0`, `canWipeout` returns false (attack == 0)
   - `beginPhase(playerA, Phases::Confirm)`

2. **endPhase(Confirm)**
   - `m_turnNumber++`
   - `removeKilledCards()`, `endTurn()`, `calculateGameOver()` -> false
   - `getAttack(playerA) = 0`
   - `beginPhase(playerB, Phases::Swoosh)` (SKIP defense)

3. **beginPhase(playerB, Swoosh)**
   - `beginTurn(playerB)`: resource reset, card refresh, scripts
   - `endPhase()` -> `beginPhase(playerB, Phases::Action)`

4. **Player B: Action Phase**

### Trace Comparison

| Step | AS3 | C++ | Match? |
|------|-----|-----|--------|
| Attack check | `oppMana.attack = 0` | `getAttack(playerA) = 0` | YES |
| Defense skipped | Yes, `swoosh()` called directly | Yes, `beginPhase(Swoosh)` directly | YES |
| Swoosh processing | Full card refresh + scripts | `beginTurn()` + scripts | Equivalent |

### Verdict: MATCH

Both engines correctly skip the Defense phase when attack is 0 and proceed directly to Swoosh/Action for the next player.

---

## Summary Verdict Table

| Check | AS3 Reference | C++ Reference | Verdict | Severity |
|-------|---------------|---------------|---------|----------|
| C0: Phase Enumeration | C.as:136-140 | Constants.h:11-13 | **MATCH** (functional) | N/A |
| C1: Action -> Breach/Confirm | State.as:1855-1961 | GameState.cpp:1350-1364 | **MATCH** | N/A |
| C2: Confirm -> Defense/Swoosh | State.as:1997-2028 | GameState.cpp:1383-1413 | **MATCH** | N/A |
| C3: Defense -> Swoosh | State.as:1900-1909 | GameState.cpp:1287-1342 | **MISMATCH** | HIGH |
| C4: Swoosh -> Action | State.as:2607-2608 | GameState.cpp:1315-1348 | **MATCH** | N/A |
| C5: Turn Number Increment | State.as:2016 | GameState.cpp:1385 | **MATCH** (minor edge case) | LOW |
| C6: Game-Over Check Timing | State.as:1961,2004-2013 | GameState.cpp:1394 | **MATCH** (feature gaps) | LOW |

### Mismatches Requiring Action

| ID | Description | Severity | Fix |
|----|-------------|----------|-----|
| C3-M1 | Defense phase status reset (commit 5bf57a8) resets Assigned cards to Default, changing blocking eligibility | **HIGH** | Remove lines 1289-1306 from `GameState::beginPhase()` |
| C1-N1 | WIPEOUT doAction fall-through to UNDO_CHILL (no `break;`) | **MEDIUM** | Add `break;` after `endPhase()` in WIPEOUT case (line 707) |
| C5-N1 | Turn counter increments unconditionally (C++) vs conditionally (AS3) on game-over | **LOW** | Cosmetic, no fix needed |
| C6-N1 | All-doomed early termination missing in C++ | **LOW** | Optional optimization, no urgency |

### Mismatches NOT Requiring Action (Architectural)

| ID | Description | Why OK |
|----|-------------|--------|
| C0-A1 | Breach/Swoosh as sub-state (AS3) vs first-class phase (C++) | Legal actions equivalent |
| C1-A1 | Wipeout blocking mechanics differ (deferred kill vs immediate) | Same units die, same attack consumed |
| C1-A2 | Mana rot timing (ENTER_CONFIRM vs beginTurn) | Same resources cleared before next action |
| C3-A1 | collectBodies timing (pre-swoosh vs during beginTurn) | Dead cards excluded from gameplay either way |
| C4-A1 | Resonators/triggers/special cards missing | Not used in competitive play or self-play |

---

## Appendix: Defense Phase Status Reset Deep Dive

This appendix provides the full code-level derivation of why the status reset at `beginPhase(Defense)` is a bug.

### The AS3 Ground Truth: Ability Use Changes Blocking

When a card uses its ability in AS3, the MOVE_ASSIGN handler explicitly updates blocking:

**File:** `State.as`, lines 1448-1452

```actionscript
inst.role = C.ROLE_ASSIGNED;
inst.blocking = card.assignedBlocking;   // <-- KEY LINE
```

When the ability is undone (MOVE_UNASSIGN):

**File:** `State.as`, lines 1536-1539

```actionscript
inst.role = C.ROLE_DEFAULT;
inst.blocking = card.defaultBlocking;
```

During swoosh (begin-turn):

**File:** `State.as`, line 2706

```actionscript
inst.blocking = card.defaultBlocking;
```

### The AS3 Ground Truth: Defense Checks `inst.blocking`

**File:** `Controller.as`, lines 190-197

```actionscript
if(this.state.phase == C.PHASE_DEFENSE)
{
    if(inst.owner != this.state.turn)
    {
        // ERROR: opponent's unit
    }
    if(!inst.blocking)         // <-- Uses inst.blocking, NOT inst.role
    {
        // ERROR: non-blocker / disrupted / construction / busy
    }
```

### Chain of Events: Drone Uses Ability Then Enters Defense

**AS3:**
1. Swoosh: `Drone.blocking = true` (defaultBlocking)
2. Action: Drone clicks (MOVE_ASSIGN): `Drone.role = "assigned"`, `Drone.blocking = false` (assignedBlocking)
3. ENTER_CONFIRM: no change to blocking
4. COMMIT: `++numTurns`, `phase = "defense"`
5. Defense: Controller checks `Drone.blocking` -> `false` -> **CANNOT defend**

**C++ WITHOUT status reset (original):**
1. beginTurn: `Drone.status = Default`, `canBlock(false)` -> `defaultBlocking = true`
2. Action: Drone uses ability: `Drone.status = Assigned`, `canBlock(true)` -> `assignedBlocking = false`
3. endPhase(Confirm): no status change
4. beginPhase(Defense): no status change
5. Defense: `canBlock()` -> `canBlock(true)` -> `assignedBlocking = false` -> **CANNOT defend**
6. **MATCHES AS3**

**C++ WITH status reset (commit 5bf57a8, current):**
1. beginTurn: `Drone.status = Default`
2. Action: Drone uses ability: `Drone.status = Assigned`
3. endPhase(Confirm): no status change
4. beginPhase(Defense): **STATUS RESET** -> `Drone.status = Default` (Drone hasAbility -> Default)
5. Defense: `canBlock()` -> `canBlock(false)` -> `defaultBlocking = true` -> **CAN defend**
6. **DOES NOT MATCH AS3** -- Drone incorrectly allowed to block

### Conclusion

The status reset was introduced with the comment "In the live Prismata game, units can block during defense regardless of prior ability use." This comment is **incorrect** based on the AS3 source code. The AS3 client explicitly sets `inst.blocking = card.assignedBlocking` when a card uses its ability, and the defense eligibility check uses this value.

**Fix:** Remove lines 1289-1306 from `GameState::beginPhase()`. No replacement logic needed -- the status should persist from the Action phase through Defense, exactly as AS3 does it.
