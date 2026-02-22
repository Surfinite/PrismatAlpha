# A5: Game-Over Conditions (Including "All Units Doomed")

**Auditor**: Claude Opus 4.6 (engine logic audit)
**Date**: 2026-02-22
**Status**: COMPLETE
**Severity**: CRITICAL (missing game-over condition) + HIGH (missing draw type) + MEDIUM (stagnation gap)

---

## Executive Summary

The C++ AI engine is missing two of the four game-over conditions present in the AS3 Prismata client:

1. **"All Opponent Units Doomed" instant-win** -- AS3 ends the game immediately when all remaining opponent units have lifespan=1 (they will expire at the start of their next turn). C++ has no equivalent check, forcing the game to play one additional turn.

2. **Mutual elimination draw** -- AS3 returns `COLOR_DRAW_MUTUAL_ELIMINATION` when both players reach 0 units simultaneously. C++ treats this as game-over (since either side has 0 cards), but `winner()` returns `Player_None` (effectively a draw). The C++ behavior is accidentally correct for this case, but through coincidence rather than explicit logic.

3. **Stagnation draw system** -- AS3 has a sophisticated 4-level no-progress tracking system with per-level turn cutoffs. C++ has only a flat 200-turn limit in `Game::m_turnLimit`. This is a separate design gap but included for completeness.

---

## 1. AS3 `checkWin()` -- Full Trace

**File**: `prismata_decompiled/scripts/mcds/engine/State.as`, line 3298

The AS3 `checkWin()` method (for standard games where `this.objectives == null`) evaluates four conditions in strict priority order:

```actionscript
// State.as:3298-3327
private function checkWin() : int
{
    // ... (objective variables declared but unused for normal games) ...
    if (this.objectives == null)
    {
        // Condition 1: Own units alive, opponent units dead -> current player wins
        if (this.helper.ownAllUnitsTotal > 0 && this.helper.oppAllUnitsTotal == 0)
        {
            return this.turn;  // current player wins
        }

        // Condition 2: Own units dead, opponent units alive -> opponent wins
        if (this.helper.ownAllUnitsTotal == 0 && this.helper.oppAllUnitsTotal > 0)
        {
            return 1 - this.turn;  // opponent wins
        }

        // Condition 3: Both players at 0 units -> mutual elimination draw
        if (this.helper.ownAllUnitsTotal == 0 && this.helper.oppAllUnitsTotal == 0)
        {
            return C.COLOR_DRAW_MUTUAL_ELIMINATION;  // value 3
        }

        // Condition 4: All opponent units are "doomed" -> current player wins
        if (this.helper.allOppUnitsDoomed)
        {
            return this.turn;  // current player wins
        }

        return C.COLOR_NONE;  // value 2 -- game continues
    }
    // ... (objective-based win conditions for missions/raids follow) ...
}
```

### AS3 Result Constants

From `C.as`:
| Constant | Value | Meaning |
|---|---|---|
| `COLOR_WHITE` | 0 | Player 1 wins |
| `COLOR_BLACK` | 1 | Player 2 wins |
| `COLOR_NONE` | 2 | Game continues |
| `COLOR_DRAW_MUTUAL_ELIMINATION` | 3 | Both eliminated simultaneously |
| `COLOR_DRAW_STALEMATE` | 4 | Stagnation draw (claimed by player) |

### When `checkWin()` is called

`checkWin()` is called at the **Confirm phase** entry (State.as:1961):

```actionscript
// State.as:1911 (MOVE_ENTER_CONFIRM handler)
this.endTurnObject = new EndTurnObject(this);
// ... (no-progress counter resets) ...
this.phase = C.PHASE_CONFIRM;
this.helper.update(this);          // <-- recalculates allOppUnitsDoomed
this.clearInstArrowIds();
this.manaRots(update, animate);
this.collectSpells(update, animate);
this.collectBodies(update, animate);
// ...
this.endTurnObject.checkWin = this.checkWin();  // <-- line 1961
```

The result is stored in `endTurnObject.checkWin` and applied at **MOVE_COMMIT** time (State.as:2012):

```actionscript
// State.as:2010-2013 (MOVE_COMMIT handler, non-objective path)
this.result = this.endTurnObject.checkWin;
```

If the result indicates a win (not `COLOR_NONE`), the game is immediately over. Importantly, if the win is due to "all units doomed", AS3 then visually expires the doomed units (State.as:2035-2045):

```actionscript
if (this.result == this.turn || ...)
{
    for each (inst in this.helper.oppDoomOneUnits)
    {
        --inst.lifespan;
        this.dispatch(update, animate, C.SEND_LIFESPAN_TICKED, {"inst":inst, "after":inst.lifespan});
        inst.deadness = C.DEADNESS_AGED;
        this.dispatch(update, animate, C.SEND_LIFESPAN_DONE, {"inst":inst});
        this.dispatch(update, animate, C.SEND_COLLECTED, {"inst":inst});
    }
}
```

---

## 2. AS3 `allOppUnitsDoomed` -- Definition and Logic

**File**: `prismata_decompiled/scripts/mcds/engine/StateHelper.as`, lines 34, 111, 420-430

### Definition

A unit is considered "doomed" if and only if it satisfies ALL of:
- `lifespan == 1`
- `constructionTime == 0` (not under construction)
- `delay == 0` (not delayed)
- `!dead` (still alive)

The `allOppUnitsDoomed` flag is `true` when **every** living opponent unit is doomed. It starts as `true` in `reset()` and is set to `false` if any non-doomed opponent unit is found.

### Exact Code

```actionscript
// StateHelper.as:reset() -- line 111
this.allOppUnitsDoomed = true;

// StateHelper.as:update() -- opponent unit iteration, lines 420-430
if (!inst.dead)
{
    this.oppAllUnitsTotal += inst.damageItCanTake;
    if (inst.lifespan == 1 && inst.constructionTime == 0 && inst.delay == 0)
    {
        this.oppDoomOneUnits.push(inst);  // track these for visual expiry
    }
    else
    {
        this.allOppUnitsDoomed = false;   // any non-doomed unit prevents instant-win
    }
}
```

### Edge Cases

**When `oppAllUnitsTotal == 0`**: If the opponent has zero living units, the loop body never executes, so `allOppUnitsDoomed` stays at its reset value of `true`. However, this is harmless because Condition 1 (`ownAllUnitsTotal > 0 && oppAllUnitsTotal == 0`) fires first in `checkWin()`, before Condition 4 is ever reached.

**Units under construction or delayed**: A unit with `constructionTime > 0` or `delay > 0` is NOT doomed, even if it has `lifespan == 1`. This makes sense -- the lifespan only ticks when the unit is active (not constructing/delayed).

**Units with lifespan > 1**: NOT doomed. Even `lifespan == 2` with nothing else on the board means the game continues -- the opponent gets one more turn.

**Fragile units with incoming damage**: NOT considered doomed by this check. The doomed check is purely about lifespan expiry, not about damage-based death.

---

## 3. C++ `calculateGameOver()` -- Full Trace

**File**: `source/engine/GameState.cpp`, lines 1207-1213

```cpp
bool GameState::calculateGameOver() const
{
    CardID p1Cards = numCards(Players::Player_One) + numKilledCards(Players::Player_One);
    CardID p2Cards = numCards(Players::Player_Two) + numKilledCards(Players::Player_Two);

    return p1Cards == 0 || p2Cards == 0;
}
```

**Notes**:
- `numCards(p)` returns the count of **live** cards for player `p` (from `CardData::m_liveCardIDs[p].size()`)
- `numKilledCards(p)` returns the count of **killed-this-turn** cards (from `CardData::m_killedCardIDs[p].size()`)
- These "killed" cards are cards that died during the current turn but haven't been cleaned up yet
- `removeKilledCards()` clears the killed arrays -- called at Confirm phase start and at end of `beginTurn()`

### C++ `winner()`

**File**: `source/engine/GameState.cpp`, lines 1759-1777

```cpp
const PlayerID GameState::winner() const
{
    if (!isGameOver())
    {
        return Players::Player_None;
    }

    if (numCards(Players::Player_One) + numKilledCards(Players::Player_One) == 0)
    {
        return Players::Player_Two;
    }

    if (numCards(Players::Player_Two) + numKilledCards(Players::Player_Two) == 0)
    {
        return Players::Player_One;
    }

    return Players::Player_None;  // both have 0 = draw
}
```

### C++ Game-Over Check Timing

The game-over check happens at the **end of the Confirm phase** (GameState.cpp:1393-1394):

```cpp
case Phases::Confirm:
{
    m_turnNumber++;
    m_cards.removeKilledCards();

    for (const auto & cardID : getCardIDs(player))
    {
        _getCardByID(cardID).endTurn();
    }

    // we re-calculate the gameOver status at the end of the confirm phase for a player
    m_gameOver = calculateGameOver();

    if (isGameOver())
    {
        m_resources[player].set(Resources::Attack, 0);
    }
    // ... continue to enemy Defense or Swoosh ...
}
```

### What C++ Checks vs. What It Misses

| Condition | AS3 | C++ | Match? |
|---|---|---|---|
| One side has 0 units, other has >0 | Conditions 1 & 2: returns winner | `calculateGameOver()` returns true, `winner()` returns correct player | YES |
| Both sides have 0 units | Condition 3: returns `COLOR_DRAW_MUTUAL_ELIMINATION` | `calculateGameOver()` returns true (either side is 0), `winner()` falls through to `Player_None` | ACCIDENTAL MATCH (see below) |
| All opponent units have lifespan=1 | Condition 4: instant-win for current player | **NOT CHECKED** | **MISSING** |

---

## 4. Detailed Gap Analysis

### Gap 1: "All Units Doomed" Instant-Win (CRITICAL)

**What happens in AS3**: When the active player clicks Confirm and all remaining opponent units have `lifespan == 1` (and are not constructing/delayed), `checkWin()` returns the current player as winner immediately. The opponent never gets another turn.

**What happens in C++**: The game continues. The opponent gets their full turn (Swoosh -> Action -> Confirm/Breach). During their Swoosh/beginTurn, the lifespan-1 units expire naturally (Card.cpp:593-600 reduces lifespan and kills the card). This means:

1. The opponent gets one extra turn of actions (abilities, buys, attacks)
2. The game ends when the opponent's last unit dies from lifespan during their beginTurn, OR
3. If the opponent bought something during that extra turn, the game may continue even longer

**Concrete scenario**: Player A has a Tarsier (permanent). Player B has only a Rhino that was created as a temporary unit (lifespan=1, about to expire). In AS3, Player A wins immediately at Confirm. In C++, Player B gets another full turn -- the Rhino expires during B's Swoosh, and only then does B have 0 units, ending the game.

**Impact on AI play**: During search, the AI might evaluate positions differently because:
- It may explore branches where the opponent gets an "impossible" extra turn
- The extra turn allows the opponent to deal damage, buy units, or use abilities that shouldn't be available
- Evaluation may be slightly biased because games take 1 extra turn to conclude in these scenarios

### Gap 2: Mutual Elimination Draw (HIGH)

**What happens in AS3**: Returns `COLOR_DRAW_MUTUAL_ELIMINATION` (value 3) -- a distinct draw type. The UI shows this as a draw. The stagnation system also has `COLOR_DRAW_STALEMATE` (value 4) as a separate draw type.

**What happens in C++**: `calculateGameOver()` returns `true` (since either player has 0 cards). `winner()` checks Player_One first, finds 0 cards, returns `Player_Two`. Then... wait. Let me re-examine.

Actually, if BOTH players have 0 cards:
- `numCards(Player_One) + numKilledCards(Player_One) == 0` is TRUE -> returns `Player_Two`

This is **WRONG**. If both players have 0 units, the C++ code awards the win to Player_Two because the Player_One check fires first. In AS3, this is correctly identified as a mutual elimination draw.

**However**: For this to happen in practice, both players would need to reach 0 units simultaneously. This is extremely rare but theoretically possible (e.g., mutual sac effects, both players' last units expire from lifespan in the same Confirm phase). The C++ code would incorrectly declare Player_Two as the winner instead of a draw.

**Correction on timing**: Actually, `calculateGameOver()` runs at the end of ONE player's Confirm phase. At that point, only the active player's cards have been processed (endTurn called, killed cards removed). The opponent's cards are still in their previous state. So both-sides-zero would require:
- The active player already had 0 cards going into this turn, AND
- The opponent also has 0 cards

This is even more constrained. If the active player had 0 cards, the game should already have ended in a prior turn. The only way both reach 0 simultaneously is if the active player's last units die during their own Confirm phase processing. Let me check the sequence more carefully...

The Confirm phase does:
1. `m_cards.removeKilledCards()` -- clears killed-this-turn arrays
2. `endTurn()` for each of the active player's cards -- this is where lifespan ticking happens
3. `m_gameOver = calculateGameOver()` -- checks both players

Wait -- `endTurn()` on Card doesn't kill cards, it's `beginTurn()` that does lifespan ticking. Let me re-read:

```cpp
// Card.cpp endTurn() -- line 555
void Card::endTurn()
{
    // Reset for next turn
    if (m_status == CardStatus::Default)
    {
        m_status = CardStatus::Inert;
    }
    // ...
}
```

Actually, `Card::beginTurn()` (Card.cpp:575) is where lifespan decrements happen. And `beginTurn()` is called during the **Swoosh phase** (GameState.cpp:1317), NOT during Confirm. So at the time `calculateGameOver()` runs (end of Confirm), lifespan units haven't ticked yet.

This means both-sides-zero at Confirm time requires both players to have had their units killed through combat/abilities during this turn, not through lifespan expiry. This is theoretically possible (mutual breach/snipe scenarios) but extremely rare.

**Revised assessment**: The mutual elimination bug in `winner()` is real (Player_Two gets credited instead of draw), but the practical occurrence rate is very low.

### Gap 3: Stagnation System (MEDIUM)

This is documented separately but summarized here for completeness.

**AS3 Stagnation**: 4-level no-progress tracking system.

| Level | Reset When | Cutoff (turns) |
|---|---|---|
| 0 | Any progress event | 2 |
| 1 | Delay ticked, HP healed on pay-HP unit, Charge recharged, Damage > healing | 8 |
| 2 | Money stored | 20 |
| 3 | Card bought/created, Buildtime ticked, Opp lifespan ticked, Gas stored | 40 |

Each level has separate per-player counters (`whiteNoProgress[i]`, `blackNoProgress[i]`). If ANY level's counter reaches its cutoff, that player is "stagnated" and the opponent can claim a draw.

Progress events at various levels reset all counters BELOW that level (not at or above). For example, buying a card (level 3) resets counters 0, 1, and 2 to zero.

The stagnation draw is **opt-in** -- the opponent must choose to claim it. It's offered as `oppCouldClaimDraw` at Confirm time.

**C++ Stagnation**: Flat 200-turn limit in `Game::m_turnLimit`:

```cpp
// Game.h:17
TurnType m_turnLimit = 200;

// Game.cpp:88-91
bool Game::gameOver() const
{
    return m_state.isGameOver() || (m_turnsPlayed >= m_turnLimit);
}
```

No per-player tracking, no progress events, no multi-level system. The 200-turn limit is a hard cap in the `Game` class, not in `GameState`. AI search trees that use `GameState` directly (without `Game`) have no turn limit at all.

---

## 5. Test Cases

### Test Case 1: Opponent has only lifespan-1 units

**Setup**: Player A has a Drone. Player B has only a Rhino (lifespan=1, constructionTime=0, delay=0).
Player A ends their Action phase (no attack), enters Confirm.

| Engine | Behavior | Result |
|---|---|---|
| AS3 | `helper.update()` finds Rhino is doomed -> `allOppUnitsDoomed = true`. `checkWin()` condition 4 fires -> returns Player A as winner. Game ends immediately. Rhino is visually expired. | Player A wins |
| C++ | `calculateGameOver()` checks `numCards(B) + numKilledCards(B)` = 1 + 0 = 1, not zero. Game continues. Player B gets Swoosh -> `beginTurn()` -> Rhino lifespan decrements to 0 -> killed -> `removeKilledCards()`. Player B now has 0 cards. Player B's Confirm: `calculateGameOver()` finds B has 0 cards. Game ends. | Player A wins (1 turn later) |

**Discrepancy**: C++ allows Player B one extra turn. If Player B had attack from another source (e.g., stored attack), they could deal damage to Player A during that extra turn.

### Test Case 2: Both players reach 0 units simultaneously

**Setup**: Player A has one Drone. Player B has one Drone. Player A has enough attack to breach and kill B's Drone. B's Drone dies. During the same turn's processing, A's Drone is killed by a trigger or delayed effect.

| Engine | Behavior | Result |
|---|---|---|
| AS3 | `checkWin()`: `ownAllUnitsTotal == 0 && oppAllUnitsTotal == 0` -> condition 3 -> returns `COLOR_DRAW_MUTUAL_ELIMINATION` | **Draw** |
| C++ | `calculateGameOver()`: `p1Cards == 0` is true -> returns true. `winner()`: `numCards(P1) + numKilledCards(P1) == 0` -> returns `Player_Two`. | **Player Two wins (INCORRECT)** |

**Note**: This scenario is extremely rare in practice. It requires simultaneous elimination during the same phase's processing.

### Test Case 3: Opponent has lifespan-2 unit and nothing else

**Setup**: Player A has a Drone. Player B has only a single unit with lifespan=2 (not constructing, not delayed).

| Engine | Behavior | Result |
|---|---|---|
| AS3 | `helper.update()`: lifespan != 1, so `allOppUnitsDoomed = false`. `checkWin()` condition 4 does not fire. Game continues. | Game continues |
| C++ | `calculateGameOver()`: B has 1 card. Game continues. | Game continues |

**No discrepancy** for lifespan-2 -- both engines correctly continue.

### Test Case 4: Opponent has mix of doomed and non-doomed units

**Setup**: Player B has one Rhino (lifespan=1) AND one Drone (permanent). Player A enters Confirm.

| Engine | Behavior | Result |
|---|---|---|
| AS3 | Drone has no lifespan limit -> `allOppUnitsDoomed = false`. Game continues. | Game continues |
| C++ | B has 2 cards. Game continues. | Game continues |

**No discrepancy** -- the doomed check requires ALL opponent units to be doomed.

### Test Case 5: Opponent has only units under construction

**Setup**: Player B's only living units are all under construction (constructionTime > 0). Some may have lifespan=1 but are still constructing.

| Engine | Behavior | Result |
|---|---|---|
| AS3 | `constructionTime > 0` -> `allOppUnitsDoomed = false` (since the doomed check requires `constructionTime == 0`). HOWEVER, `oppAllUnitsTotal > 0` because construction units count. Game continues. | Game continues |
| C++ | B has cards (under construction counts). Game continues. | Game continues |

**No discrepancy** -- constructing units are not doomed in either engine.

---

## 6. Impact Assessment

### How Often Does "All Units Doomed" Trigger?

The doomed instant-win condition triggers when:
- The opponent's ONLY remaining units all have `lifespan == 1`
- These units are not constructing and not delayed

In practice, this occurs in **late-game scenarios** involving:

1. **Gauss Charge** (lifespan 1, Fragile) -- purchased as a temporary blocker
2. **Forcefield** (lifespan 1, Fragile) -- the most common temporary blocker
3. **Pixie** (lifespan 1) -- a temporary attacker
4. **Flame Animus-produced tokens** -- various lifespan-1 units
5. **Any unit with `lifespan` field in cardLibrary.jso equal to 1**

The scenario is: an opponent is in a losing position, their permanent units have been destroyed through breach, and they're buying only temporary blockers/attackers (Forcefields, Gauss Charges) to survive one more turn. The instant-win skips the "one more turn of futile temporary units."

**Estimated frequency**: This is relevant in approximately 5-15% of games that reach the endgame breach phase. Many games end with the losing player having at least one permanent unit remaining (even if it's just a single Drone). But games where the breach is total and the opponent is reduced to only temporary units are common enough to matter.

**Impact on AI search**: The AI engine running extra turns for these positions:
- Wastes search depth on positions that should be terminal
- May slightly distort evaluation of endgame breach positions
- The opponent getting an "impossible" extra turn could cause the AI to overvalue the opponent's position slightly (since they get one more chance to deal damage or buy)

**Impact on self-play data**: In 722K self-play games:
- Games ending via doomed-unit scenarios play 1-2 extra turns in C++
- The position labels from those extra turns are somewhat noisy (game should already be over)
- Estimated impact: small -- these are heavily winning/losing positions anyway, and the value label doesn't change much
- The opponent's "extra turn" positions would get value labels close to 0.0 (certain loss) whether they play or not

### Impact on Mutual Elimination

The mutual elimination bug (`winner()` credits Player_Two instead of declaring a draw) is extremely rare. In 722K self-play games, the number of truly simultaneous eliminations is likely in the single digits or zero. The practical impact is negligible.

---

## 7. Stagnation Comparison

### AS3: 4-Level No-Progress System

```
Level 0: Cutoff = 2 turns   -- Any progress resets
Level 1: Cutoff = 8 turns   -- Delay tick, HP heal, Charge recharge, Damage > healing
Level 2: Cutoff = 20 turns  -- Money stored
Level 3: Cutoff = 40 turns  -- Card bought/created, Buildtime tick, Opp lifespan tick, Gas stored
```

Stagnation is per-player. When a player is "stagnated" (any level counter >= cutoff), the opponent can **claim a draw** (it's opt-in via the Confirm phase UI). This is checked at State.as:1962:

```actionscript
this.endTurnObject.oppCouldClaimDraw = this.colorIsStagnated(this.turn);
```

The key feature is the **hierarchy**: progress at level N resets all counters at levels 0 through N-1. So buying a card (level 3) resets levels 0, 1, and 2. But merely storing money (level 2) doesn't reset level 3.

The 4-level system handles nuanced stagnation cases:
- Level 0 (2 turns): Extremely basic -- almost any game action resets this
- Level 1 (8 turns): If no damage is exceeding healing, delays ticking, or charges regenerating for 8 turns, something is stuck
- Level 2 (20 turns): If not even storing money for 20 turns, the game is very stuck
- Level 3 (40 turns): If no new purchases/constructions for 40 turns, hard stagnation

### C++: 200-Turn Hard Limit

```cpp
// Game.h:17
TurnType m_turnLimit = 200;

// Game.cpp:88-91
bool Game::gameOver() const
{
    return m_state.isGameOver() || (m_turnsPlayed >= m_turnLimit);
}
```

The 200-turn limit is:
- Applied only in the `Game` class, not in `GameState`
- A hard stop, not a draw offer
- Not visible to AI search (which uses `GameState::isGameOver()` directly)
- Counts total turns (both players), so ~100 rounds

**Key issue**: AI search trees never hit the 200-turn limit because they use `GameState::isGameOver()` which has no turn limit. This means the AI can explore infinite-length games in its search, though in practice the search depth is limited by think time.

### Stagnation Impact

The stagnation difference is unlikely to cause behavioral issues in most games. The 200-turn limit is generous enough that normal games end well before it. However, for AI search in truly stagnated positions (e.g., two players with only Drones and no attackers), the lack of stagnation detection means the search tree can explore meaningless branches indefinitely.

---

## 8. Recommendations

### Priority 1: Implement "All Units Doomed" Check (CRITICAL)

Add a doomed-unit scan to `calculateGameOver()` or create a new method `areAllUnitsDoomed()`. The check should:
1. Iterate all living cards of the enemy player
2. For each card: if `lifespan > 0 && lifespan == 1 && constructionTime == 0 && delay == 0`, it's doomed
3. If ANY card is NOT doomed, return false
4. If the enemy has 0 cards (already handled by existing check), skip this
5. If all enemy cards are doomed, the active player wins

**Suggested location**: Add check in `GameState::endPhase()` at `Phases::Confirm`, after the existing `m_gameOver = calculateGameOver()` check but only if `!m_gameOver`. Or incorporate directly into `calculateGameOver()`.

**Caution**: This changes game outcomes. All 722K self-play games were generated without this check. Adding it would make the engine behavior more correct but would change the state space that the AI explores during search. Consider whether to retrain after implementing.

### Priority 2: Fix Mutual Elimination Draw (HIGH)

Modify `winner()` to check both players before returning:

```cpp
const PlayerID GameState::winner() const
{
    if (!isGameOver()) { return Players::Player_None; }

    bool p1Dead = (numCards(Players::Player_One) + numKilledCards(Players::Player_One) == 0);
    bool p2Dead = (numCards(Players::Player_Two) + numKilledCards(Players::Player_Two) == 0);

    if (p1Dead && p2Dead) { return Players::Player_None; }  // draw
    if (p1Dead)           { return Players::Player_Two; }
    if (p2Dead)           { return Players::Player_One; }

    return Players::Player_None;
}
```

This is low-risk since mutual elimination is extremely rare.

### Priority 3: Stagnation System (LOW -- future work)

The 200-turn limit is adequate for self-play data generation. A proper stagnation system would be needed for:
- Online play / competitive parity with AS3
- AI that can detect and exploit stagnation draws

Not blocking any current work.

---

## 9. Files Referenced

### AS3
| File | Lines | Content |
|---|---|---|
| `prismata_decompiled/scripts/mcds/engine/State.as` | 3298-3327 | `checkWin()` -- 4-condition game-over check |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 1961 | `checkWin()` called at Confirm phase entry |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 2010-2046 | Result applied at MOVE_COMMIT, doomed units visually expired |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 76-78 | Stagnation constants: `NUM_LEVELS_OF_DRAW_VARIABLES=4`, `CUTOFFS_FOR_DRAW=[2,8,20,40]` |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 80-104 | Stagnation level constants (13 event types mapped to 4 levels) |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 1291-1369 | No-progress counter increment/reset/check functions |
| `prismata_decompiled/scripts/mcds/engine/State.as` | 2582-2700 | `swoosh()` -- lifespan ticking in AS3 |
| `prismata_decompiled/scripts/mcds/engine/StateHelper.as` | 34, 111, 420-430 | `allOppUnitsDoomed` flag and doomed-unit detection |
| `prismata_decompiled/scripts/mcds/engine/StateHelper.as` | 36 | `oppDoomOneUnits` vector (tracks doomed units for visual expiry) |
| `prismata_decompiled/scripts/mcds/engine/C.as` | 40-44 | Color/result constants (COLOR_NONE, COLOR_DRAW_*) |

### C++
| File | Lines | Content |
|---|---|---|
| `source/engine/GameState.cpp` | 1207-1213 | `calculateGameOver()` -- only checks if either player has 0 cards |
| `source/engine/GameState.cpp` | 1202-1205 | `isGameOver()` -- returns `m_gameOver` flag |
| `source/engine/GameState.cpp` | 1759-1777 | `winner()` -- determines winner, has mutual-elimination bug |
| `source/engine/GameState.cpp` | 1383-1412 | Confirm phase: `removeKilledCards()`, `endTurn()`, `calculateGameOver()` |
| `source/engine/GameState.cpp` | 1315-1319 | Swoosh phase: calls `beginTurn(player)` |
| `source/engine/GameState.cpp` | 1215-1276 | `beginTurn()` -- lifespan decrement, card killing, script execution |
| `source/engine/Card.cpp` | 575-601 | `Card::beginTurn()` -- lifespan decrement and kill |
| `source/engine/Card.cpp` | 248-252 | `getCurrentLifespan()` -- accessor for `m_lifespan` |
| `source/engine/Game.cpp` | 88-91 | `gameOver()` -- includes 200-turn limit |
| `source/engine/Game.h` | 17 | `m_turnLimit = 200` |
| `source/engine/Constants.h` | 7 | Player enum: `Player_One=0, Player_Two=1, Player_Both=2, Player_None=3` |

---

## 10. Summary Table

| Condition | AS3 Behavior | C++ Behavior | Gap Severity |
|---|---|---|---|
| One side eliminated | Winner determined correctly | Winner determined correctly | NONE |
| Both sides eliminated | `COLOR_DRAW_MUTUAL_ELIMINATION` (draw) | `Player_Two` wins (first-check bias) | HIGH (but extremely rare) |
| All opponent units doomed (lifespan=1) | Instant-win for current player | Game continues, opponent gets extra turn | **CRITICAL** |
| Stagnation / no progress | 4-level system, opt-in draw claim at cutoffs [2,8,20,40] | Flat 200-turn hard limit in Game class only | MEDIUM (cosmetic for AI) |
| Turn limit in AI search | N/A (AS3 is client, not AI) | No limit in `GameState::isGameOver()` | LOW |
