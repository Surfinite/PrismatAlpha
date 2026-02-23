# P0.3: Swoosh/beginTurn Event Timeline

**Auditor**: Claude Opus 4.6
**Date**: 2026-02-22
**Status**: Complete
**Scope**: Side-by-side comparison of turn transition logic in AS3 `swoosh()` vs C++ `beginTurn()`

---

## 1. Context: Where These Functions Sit in the Turn Flow

### AS3 Turn Flow

The AS3 engine processes moves via `State.processMove()`. Turn transition occurs at two points:

1. **MOVE_END_DEFENSE** (line 1900): After the defender finishes blocking:
   - `collectBodies()` — removes dead instances from the table
   - `swoosh()` — full turn-transition processing for new active player

2. **MOVE_COMMIT** (line 1997): After the attacker confirms their turn:
   - `++this.numTurns` (line 2016) — **turn switches before swoosh** (`turn` is computed as `(numTurns + 1) % 2`)
   - If opponent has no attack: `swoosh()` directly (no defense phase)
   - If opponent has attack: enter PHASE_DEFENSE (swoosh deferred until MOVE_END_DEFENSE)

**Resource rot** (`manaRots()`) and **spell collection** (`collectSpells()`) happen during MOVE_ENTER_CONFIRM (line 1956), BEFORE the turn switch. Energy, Blue, Red are zeroed; Attack is zeroed only if opponent has no defense. This is NOT part of swoosh.

### C++ Turn Flow

The C++ engine uses a phase state machine: `beginPhase()` / `endPhase()`.

1. **endPhase(Confirm)** (line 1383):
   - `m_turnNumber++` (line 1385) — turn number incremented
   - `removeKilledCards()` — clean up dead cards
   - `Card::endTurn()` for all current player's cards — clears killedCardIDs, createdCardIDs, target
   - `calculateGameOver()`
   - If attacker has remaining attack: `beginPhase(enemy, Defense)`
   - Else: `beginPhase(enemy, Swoosh)`

2. **endPhase(Defense)** (line 1335):
   - `beginPhase(player, Swoosh)` — same player who just defended

3. **beginPhase(Swoosh)** (line 1315):
   - Calls `beginTurn(player)` — the main turn-transition function
   - Then immediately `endPhase()` -> `beginPhase(player, Action)`

**Resource clearing** happens at the START of `beginTurn()` (lines 1220-1223): Energy, Blue, Red, Attack all set to 0. This IS part of beginTurn, unlike AS3 where resource rot is a separate pre-swoosh step.

---

## 2. AS3 swoosh() Operation Timeline

**Source**: `State.as:2582-3073`

The function operates on ALL instances in `this.table` but filters by `inst.owner == this.turn` (line 2622). It is a **single-pass** design: each card is fully processed (including its beginOwnTurnScript) before moving to the next card.

### Pre-loop Setup

| # | Operation | Code Reference | Notes |
|---|-----------|---------------|-------|
| S0 | Deterministic seed from card names | `deterministicArbitrarySeed = this.numTurns` then multiply by card name lengths (lines 2600-2606) | Used for Robo Santa, Condimus, etc. |
| S1 | Set phase to ACTION | `this.phase = C.PHASE_ACTION` (line 2607) | Phase transition happens here |
| S2 | Clear glass broken flag | `this.glassBroken = false` (line 2608) | |
| S3 | Dispatch BEGIN_SWOOSH event | `this.dispatch(update,animate,C.SEND_BEGIN_SWOOSH)` (line 2609) | UI notification |
| S4 | Create snapshot of all instance IDs | `copyOfInstIds` vector from `this.table` keys (lines 2614-2617) | Prevents iteration issues from mid-loop creates/deletes |

### Per-Card Loop (lines 2618-2920)

For each instance owned by the active player (`inst.owner == this.turn`):

| # | Operation | Code Reference | Condition | Notes |
|---|-----------|---------------|-----------|-------|
| A1 | **Clear damage** | `inst.damage = 0` (line 2627) | `inst.damage > 0` | Dispatches SEND_DAMAGE_CLEARED |
| A2 | **Clear disrupt/chill damage** | `inst.disruptDamage = 0` (line 2636) | `inst.disruptDamage > 0` | Dispatches SEND_DISRUPT_CLEARED |
| A3a | **Decrement constructionTime** | `--inst.constructionTime` (line 2644) | `inst.constructionTime > 0` | |
| A3b | If still constructing: sellable->inert, **continue** | `inst.role = C.ROLE_INERT` (line 2654) | `inst.constructionTime != 0` | Skips all remaining steps for this card |
| A3c | If just finished: dispatch DONE_CONSTRUCTING | (line 2659) | `inst.constructionTime == 0` after decrement | Falls through to A6+ |
| A4a | **Decrement delay** (else-if from A3) | `--inst.delay` (line 2663) | `inst.delay > 0` (only if constructionTime was 0) | |
| A4b | If still delayed: set role INERT, **continue** | `inst.role = C.ROLE_INERT` (line 2673) | `inst.delay != 0` | Skips remaining steps |
| A4c | If delay done: dispatch DELAY_DONE | (line 2678) | `inst.delay == 0` after decrement | Falls through to A6+ |
| A5a | **Decrement lifespan** (else-if from A4) | `--inst.lifespan` (line 2682) | `inst.lifespan > 0` (only if constructionTime=0 AND delay=0) | |
| A5b | If lifespan expired: mark AGED, delete, **continue** | `inst.deadness = C.DEADNESS_AGED; this.deleteInst(...)` (lines 2690-2694) | `inst.lifespan == 0` | Card is removed from table |
| A6 | **Push to stuffInPlay** | `stuffInPlay.push(inst)` (line 2697) | Reached only by non-constructing, non-delayed, non-expired cards | |
| A7 | **Set role** (status reset) | `inst.role = C.ROLE_DEFAULT` if `card.hasAbility`, else `C.ROLE_INERT` (lines 2698-2705) | | |
| A8 | **Reset blocking** | `inst.blocking = card.defaultBlocking` (line 2706) | | Explicit blocking reset based on card type |
| A9 | **Apply health gain** | `inst.health += card.healthGained`, capped at `card.healthMax` (lines 2708-2725) | `card.healthGained != 0` | |
| A10 | **Apply charge gain** | `inst.charge += card.chargeGained`, capped at `card.chargeMax` (lines 2726-2738) | `card.chargeGained != 0` | **NOT IN C++** |
| A11 | **Run beginOwnTurnScript** (INLINE) | `this.runScriptForward(update,animate,card.beginOwnTurnScript,...)` (line 2872) | For most cards; special-cased for Robo Santa, Robo Santa 2016, Condimus, Blastuit, Aniforge (lines 2739-2873) | Script runs immediately, interleaved with other cards |
| A12 | **Collect resonate info** | Push to `annihilators`/`goldAnnihilators` dictionaries (lines 2874-2895) | `card.resonate != null` or `card.goldResonate != null` | Only collects; resolution is post-loop |
| A13 | **Handle special units** | Set flags: `yearsOfPlenty` (Aurb Magnifier), `EMP`, `deepImpact`, `ARGroans` (A.R. Groans), `icySavior` (Glaciator) (lines 2896-2919) | Specific card names | Deferred execution post-loop |

### Post-Loop Processing (lines 2922-3072)

| # | Operation | Code Reference | Condition | Notes |
|---|-----------|---------------|-----------|-------|
| B1 | **Collect annihilatees** (resonate targets) | Iterate `stuffInPlay`, build `annihilatees`/`goldAnnihilatees` dicts (lines 2922-2948) | | Matches annihilator card names to target instances |
| B2 | **Aurb Magnifier** (Years of Plenty) | Extra gold per Drone with ROLE_DEFAULT; reduce buy counts (lines 2950-2972) | `yearsOfPlenty == true` | |
| B3 | **EMP** | Kill all enemy attackers (non-constructing) (lines 2973-2990) | `EMP == true` | |
| B4 | **Deep Impact** | Kill all enemy workers (non-constructing) (lines 2991-3008) | `deepImpact == true` | |
| B5 | **A.R. Groans** | Kill one random enemy unit with health <= 8 (lines 3009-3023) | `ARGroans == true` | Uses deterministic random |
| B6 | **Glaciator** (Icy Savior) | Remove blocking from all enemy units (lines 3024-3034) | `icySavior == true` | |
| B7 | Dispatch END_SWOOSH_SORT | (line 3035) | | |
| B8 | **Resolve resonates** (attack) | For each annihilator, add attack = count of matching annihilatees (lines 3036-3052) | | |
| B9 | **Resolve resonates** (gold) | For each gold annihilator, add gold = count of matching gold annihilatees (lines 3053-3069) | | |
| B10 | **Increment no-progress counters** | `this.incrementTurnNoProgressCounters()` (line 3070) | | Stalemate detection |
| B11 | **Execute triggers** | `this.executeTriggers(update,animate)` (line 3071) | | Tutorial/mission only |
| B12 | Dispatch END_SWOOSH | (line 3072) | | |

---

## 3. C++ beginTurn() Operation Timeline

**Source**: `GameState.cpp:1215-1276`, `Card.cpp:574-643`

The C++ function operates in **two passes** over the active player's cards, with resource clearing at the top.

### Resource Clearing (GameState::beginTurn)

| # | Operation | Code Reference | Notes |
|---|-----------|---------------|-------|
| R1 | **Zero Energy** | `_getResources(player).set(Resources::Energy, 0)` (line 1220) | |
| R2 | **Zero Blue** | `_getResources(player).set(Resources::Blue, 0)` (line 1221) | |
| R3 | **Zero Red** | `_getResources(player).set(Resources::Red, 0)` (line 1222) | |
| R4 | **Zero Attack** | `_getResources(player).set(Resources::Attack, 0)` (line 1223) | **Always zeroed** — AS3 only zeroes attack when no enemy defense |
| R5 | **Clear breach-frozen flag** | `m_canBreachFrozenCard = false` (line 1226) | |

### Pass 0: Dead Cards (GameState::beginTurn)

| # | Operation | Code Reference | Notes |
|---|-----------|---------------|-------|
| D1 | **beginTurn() on killed cards** | `_getCardByID(cardID).beginTurn()` for `getKilledCardIDs(player)` (lines 1237-1240) | Transitions `KilledThisTurn` -> `Dead`; clears flags |

### Pass 1: Card::beginTurn() on All Living Cards (lines 1243-1253)

For each living card owned by the active player (snapshot taken at line 1229-1234):

| # | Operation | Code Reference | Condition | Notes |
|---|-----------|---------------|-----------|-------|
| C1 | **Clear sellable flag** | `m_sellable = false` (line 577) | Always | |
| C2 | **Clear damage taken** | `m_damageTaken = 0` (line 578) | Always | |
| C3 | **Clear breached flag** | `m_wasBreached = false` (line 579) | Always | |
| C4 | **Clear ability-used flag** | `m_abilityUsedThisTurn = false` (line 580) | Always | |
| C5 | **Clear killed/created card IDs** | `m_killedCardIDs.clear(); m_createdCardIDs.clear()` (lines 581-582) | Always | |
| C6 | **Clear target** | `clearTarget()` (line 583) | Always | |
| C7 | **Dead status transition** | `KilledThisTurn -> Dead`, return | `m_aliveStatus == AliveStatus::KilledThisTurn` | Early return for dead cards |
| C8 | **Decrement lifespan** | `--m_lifespan`; if 0: `kill(CauseOfDeath::Lifespan)`, return (lines 593-601) | `!isUnderConstruction() && !isDelayed() && m_lifespan > 0` | **Checked FIRST** (before delay/construction) |
| C9 | **Decrement delay** | `--m_currentDelay` (line 607) | `!isUnderConstruction() && isDelayed()` | |
| C10 | If still delayed: set Inert | `setStatus(CardStatus::Inert)` (line 612) | `isDelayed()` after decrement | |
| C11 | **Decrement constructionTime** | `m_constructionTime--` (line 618) | `isUnderConstruction()` | |
| C12 | **Post-construction block**: health gain | `m_currentHealth += m_type.getHealthGained()`, capped at healthMax (lines 625-629) | `!isUnderConstruction() && !isDelayed()` | |
| C13 | **Post-construction block**: status reset | `setStatus(CardStatus::Default)` if hasAbility/hasTargetAbility, else `Inert` (lines 632-639) | Same condition | |
| C14 | **Post-construction block**: clear chill | `m_currentChill = 0` (line 641) | Same condition | |

After Card::beginTurn(), if card became dead: `killCardByID(cardID, CauseOfDeath::Unknown)` (lines 1249-1252).

### Pass 2: BeginOwnTurnScripts (GameState::beginTurn, lines 1256-1273)

For each card from the original snapshot, if still alive:

| # | Operation | Code Reference | Condition | Notes |
|---|-----------|---------------|-----------|-------|
| P1 | **Check eligibility** | `!card.isDead() && card.getType().hasBeginOwnTurnScript() && card.canRunBeginOwnTurnScript()` (line 1261) | `canRunBeginOwnTurnScript()` = `!isUnderConstruction() && m_currentDelay == 0` | |
| P2 | **Run script** | `runScript(cardID, card.getType().getBeginOwnTurnScript(), ScriptTypes::BeginTurnScript)` (line 1263) | | Script effects: mana cost, sac cost, receive mana, give mana, resonate, create cards, destroy cards, self-sac |
| P3 | **Post-script delay** | `_getCardByID(cardID).runBeginTurnScript()` (line 1266) | | Sets `m_currentDelay` from script's delay value |
| P4 | **Death check** | If card died from script and wasn't already dead: `killCardByID(...)` (lines 1268-1271) | | |

### Cleanup (GameState::beginTurn)

| # | Operation | Code Reference | Notes |
|---|-----------|---------------|-------|
| E1 | **Remove killed cards** | `m_cards.removeKilledCards()` (line 1275) | Purges all dead cards from the card set |

---

## 4. Side-by-Side Comparison

| Step | AS3 swoosh() | C++ beginTurn() | Match? |
|------|-------------|-----------------|--------|
| **Resource clearing** | Done externally in `manaRots()` during MOVE_ENTER_CONFIRM. Energy, Blue, Red zeroed. Attack zeroed only if no enemy defense. Gold preserved. | Done at top of `beginTurn()`: Energy, Blue, Red, Attack ALL zeroed. Gold preserved (not in the set calls). | **PARTIAL** - Attack handling differs. See [D1]. |
| **Phase set to ACTION** | `this.phase = C.PHASE_ACTION` (line 2607) in swoosh | Separate: `beginPhase(player, Phases::Action)` called after swoosh's endPhase | Match (different mechanism, same result) |
| **Instance ID snapshot** | Copy all table keys to vector (lines 2614-2617) | Copy all live card IDs to vector (lines 1229-1234) | Match |
| **Dead card processing** | Dead cards already removed by `collectBodies()` before swoosh | Explicit pass over `getKilledCardIDs()` to transition KilledThisTurn->Dead (lines 1237-1240) | **STRUCTURAL** - Different dead card lifecycle. See [D2]. |
| **Damage clearing** | `inst.damage = 0` (line 2627), per-card in main loop | `m_damageTaken = 0` (line 578), per-card in Card::beginTurn | Match |
| **Chill/disrupt clearing** | `inst.disruptDamage = 0` (line 2636), per-card, BEFORE construction/delay/lifespan checks | `m_currentChill = 0` (line 641), per-card, INSIDE post-construction block (only for non-constructing, non-delayed) | **DIFFERENCE** - See [D3]. |
| **Construction countdown** | Checked FIRST (`inst.constructionTime > 0`, line 2642) | Checked THIRD, after lifespan and delay (line 616) | **ORDERING** - See [D4]. |
| **Delay countdown** | Checked SECOND (`else if inst.delay > 0`, line 2661) | Checked SECOND, after lifespan (lines 604-608) | **ORDERING** - See [D4]. |
| **Lifespan countdown** | Checked THIRD (`else if inst.lifespan > 0`, line 2680) | Checked FIRST (lines 593-601) | **ORDERING** - See [D4]. |
| **Lifespan expiry** | `inst.deadness = DEADNESS_AGED; deleteInst()` — removed from table immediately | `kill(CauseOfDeath::Lifespan)` — marked dead, removed later | Match (functionally equivalent) |
| **Status/role reset** | `inst.role = ROLE_DEFAULT` if hasAbility, else `ROLE_INERT` (lines 2698-2705) | `setStatus(Default)` if hasAbility/hasTargetAbility, else `Inert` (lines 632-639) | **MINOR** - C++ also checks `hasTargetAbility()`. See [D5]. |
| **Blocking reset** | `inst.blocking = card.defaultBlocking` (line 2706) | No explicit blocking reset in beginTurn | **DIFFERENCE** - See [D6]. |
| **Health gain** | `inst.health += card.healthGained` (line 2711), capped at healthMax | `m_currentHealth += m_type.getHealthGained()` (line 625), capped at healthMax | Match |
| **Charge gain** | `inst.charge += card.chargeGained` (line 2728), capped at chargeMax | **NOT IMPLEMENTED** | **MISSING** - See [D7]. |
| **BeginOwnTurnScript execution** | INLINE within per-card loop (line 2872) — runs immediately after card's own refresh | SEPARATE second pass (lines 1256-1273) — runs after ALL cards refreshed | **STRUCTURAL** - See [D8]. |
| **Resonate resolution** | Two-phase: (1) collect in per-card loop, (2) resolve post-loop (lines 3036-3069) | Inline within `runScript()` — resonates computed during script execution (lines 952-964) | **STRUCTURAL** - See [D9]. |
| **Special unit handling** (EMP, Deep Impact, A.R. Groans, Glaciator, Aurb Magnifier) | Flag-based, executed post-loop (lines 2950-3034) | Not implemented (these are event/promotional units) | **N/A** - Promotional units not in competitive play |
| **No-progress counter increment** | `incrementTurnNoProgressCounters()` (line 3070) | Not present in beginTurn | **N/A** - Stalemate detection not in C++ AI engine |
| **Trigger execution** | `executeTriggers()` (line 3071) | Not present | **N/A** - Tutorial/mission system only |
| **Dead card cleanup** | Already done (deleteInst during loop or pre-swoosh collectBodies) | `m_cards.removeKilledCards()` at end of beginTurn (line 1275) | Match (different timing, same final state) |

---

## 5. Identified Ordering Differences

### [D1] Attack Resource Clearing — MEDIUM RISK

**AS3**: Attack is cleared in `manaRots()` during MOVE_ENTER_CONFIRM, but ONLY if opponent has no defense (`this.helper.oppDefense == 0`, line 3113). If the opponent has defense (blockers), attack carries over into the defense/swoosh phases.

**C++**: Attack is ALWAYS zeroed at the start of `beginTurn()` (`_getResources(player).set(Resources::Attack, 0)`, line 1223).

**Impact**: In the C++ engine, if a card's beginOwnTurnScript produces attack, it starts from 0. In AS3, leftover attack from the previous turn's action phase (if opponent had defense) might persist into swoosh. However, in practice the Confirm -> Defense -> Swoosh flow means any attack should have been fully resolved during defense before swoosh runs. The difference is that C++ unconditionally zeroes attack, while AS3 conditionally zeroes it — but both should produce the same result in normal gameplay because attack is consumed during breach/defense resolution.

**Risk**: LOW in practice. The C++ approach is more conservative (always zero). The only scenario where this matters is if attack somehow survives the defense phase, which shouldn't happen in a correctly played game.

### [D2] Dead Card Lifecycle — LOW RISK

**AS3**: Dead cards are removed from the table via `deleteInst()` during `collectBodies()` (called before swoosh) or inline during lifespan expiry. By the time swoosh runs, dead cards are gone.

**C++**: Dead cards persist in the card set with status `KilledThisTurn`. `beginTurn()` explicitly iterates killed cards to transition them to `Dead` status (lines 1237-1240), then removes them at the end (line 1275).

**Impact**: Purely structural. The two-pass C++ approach exists because it tracks killed cards for undo support. The final game state is the same — dead cards are removed before the action phase begins.

**Risk**: NONE for game logic. This is an implementation detail for undo support.

### [D3] Chill/Disrupt Clearing Position — LOW RISK

**AS3**: Chill (`inst.disruptDamage`) is cleared BEFORE the construction/delay/lifespan checks (line 2636), unconditionally for all owned cards.

**C++**: Chill (`m_currentChill`) is cleared INSIDE the post-construction block (line 641), only for cards that are NOT under construction AND NOT delayed.

**Impact**: In AS3, a card under construction or delayed still gets its chill cleared. In C++, chill on constructing/delayed cards persists across turns.

**Risk**: LOW. Chill typically targets active (non-constructing) units. A chill on a constructing unit would be unusual and the per-game impact is minimal. The AS3 approach (always clear) is more correct — chill should not persist indefinitely on a constructing unit.

### [D4] Lifespan/Delay/Construction Check Ordering — NONE

**AS3 order**: constructionTime -> delay -> lifespan (using `else if` chain)
**C++ order**: lifespan -> delay -> constructionTime (using guarded `if` blocks)

**Impact**: NONE. The conditions are mutually exclusive due to the guards:
- AS3 uses `else if`, so only one branch executes
- C++ guards: lifespan requires `!isUnderConstruction() && !isDelayed()`, delay requires `!isUnderConstruction()`

A card can only be in one state: constructing, delayed (but not constructing), or active (with possible lifespan). The different ordering produces identical results because the guard conditions prevent overlap.

**Risk**: NONE.

### [D5] Status Reset hasTargetAbility Check — LOW RISK

**AS3**: `inst.role = ROLE_DEFAULT` only if `card.hasAbility` (line 2698). Otherwise `ROLE_INERT` (line 2704).

**C++**: `setStatus(Default)` if `getType().hasAbility() || getType().hasTargetAbility()` (line 632). Otherwise `Inert`.

**Impact**: Cards with `targetAbility` but no regular `ability` (e.g., units with only a targeted action like SNIPE/CHILL) would get `INERT` in AS3 but `Default` in C++.

**Risk**: LOW. Need to check if any unit has `targetAction` but not `hasAbility`. Most target-ability units also have an ability script. If such a unit exists, it would not show as clickable in AS3 but would in C++.

### [D6] Blocking Reset — MEDIUM RISK

**AS3**: Explicit blocking reset: `inst.blocking = card.defaultBlocking` (line 2706). This restores each card's blocking status to its card-type default every turn.

**C++**: NO explicit blocking reset in `Card::beginTurn()` or `GameState::beginTurn()`. However, there IS a reset in `GameState::beginPhase(Defense)` (lines 1289-1306, commit 5bf57a8) which resets statuses before the defense phase.

**Impact**: In AS3, blocking is reset during swoosh (at the start of your own turn). In C++, blocking is managed through the CardStatus system (Default/Assigned/Inert), not a separate boolean. Cards with `defaultBlocking=true` can block when in Default status (checked via `CardType::canBlock(assigned=false)`), and cards with `assignedBlocking=true` can block even when Assigned. The status reset in `Card::beginTurn()` (lines 632-639) effectively handles this by resetting to Default/Inert.

**Note**: The defense phase status reset (commit 5bf57a8, lines 1289-1306) is already identified as a bug in CLAUDE.md. It resets tapped Drones to Default before defense, allowing them to block when they shouldn't. In AS3, `inst.blocking = card.defaultBlocking` only runs during swoosh (your OWN turn start), NOT before defending. The blocking state during defense comes from whatever happened during the previous action phase.

**Risk**: MEDIUM. The blocking system works differently between engines. The C++ approach uses CardStatus as a proxy for blocking capability, while AS3 has an explicit `blocking` boolean. The known defense-phase reset bug (commit 5bf57a8) is a separate issue from the swoosh/beginTurn comparison.

### [D7] Charge Gain — MISSING IN C++ (verified: LOW — technical debt only)

> **VERIFICATION UPDATE**: Independent verification confirmed that C++ has no `chargeGained`
> implementation, BUT scanning `cardLibrary.jso` found **0 units with chargeGained > 0**.
> No units in the game use passive per-turn charge restoration. Downgraded from HIGH to LOW.

**AS3**: `inst.charge += card.chargeGained`, capped at `card.chargeMax` (lines 2726-2738). This is a per-card-type property parsed from card data (`Card.as:194`). The AS3 engine prepared for this feature, but no units in the current card library use it.

**C++**: The `CardTypeInfo` struct has NO `chargeGained` field. Charges are only consumed (`m_currentCharges -= getType().getChargeUsed()` in `Card::useAbility()`, line 788) and restored during undo (`m_currentCharges += getType().getChargeUsed()` in `Card::undoUseAbility()`, line 743). There is no per-turn charge restoration.

**Impact**: ZERO gameplay impact. All 9 charge-using units (Bombarder, Charged Drone, Corpus, Nether Warrior, Elephant Graveyard, Rhino, Sentinel, Tia Thurnax, Twin-Barrel Mech) only have `startingCharge` — none have `chargeGained`. This is technical debt only.

**Risk**: LOW. Would become a bug if Lunarch ever added a unit with `chargeGained > 0`, but the game is no longer actively developed.

### [D8] Single-Pass vs Two-Pass Script Execution — MEDIUM RISK

**AS3**: BeginOwnTurnScript runs INLINE within the per-card loop (line 2872). When card A's script runs, cards B, C, D later in the iteration order have NOT yet been refreshed (status reset, health gain, etc.).

**C++**: BeginOwnTurnScript runs in a SEPARATE second pass (lines 1256-1273). When card A's script runs, ALL cards have already been refreshed by pass 1.

**Impact**: The observable difference occurs when:
1. Card A's beginOwnTurnScript **creates** a new unit or **destroys** an existing unit
2. Card B later in the loop is affected by that creation/destruction
3. Card B's own refresh or script depends on the game state

Specific scenarios:
- **Script creates a unit that has resonate**: In AS3, resonate collection happens per-card in the same loop. A newly created unit might or might not be in `stuffInPlay` depending on iteration order. In C++, resonate is computed within `runScript()` by counting existing cards of that type — all cards from pass 1 are already processed.
- **Script destroys a unit**: In AS3, the destroyed unit is removed immediately. In C++, it's marked dead but still in the card set during pass 2 (other scripts can still see it, though `isDead()` checks would catch it).
- **Script produces resources**: In both engines, resources are immediately available. But in AS3, the next card in the loop might be able to use those resources (e.g., for its beginOwnTurnScript's mana cost). In C++, all scripts run in pass 2 with all resources already cleared and pass-1 processing complete.

**Risk**: MEDIUM. Most beginOwnTurnScripts are simple (produce resources, create a unit). The two-pass vs single-pass difference would only manifest with cards whose scripts have side effects that interact. For standard competitive play, this is unlikely to matter. For edge cases with multiple script-bearing units, the ordering could produce different game states.

### [D9] Resonate Resolution Timing — LOW RISK

**AS3**: Resonate is a two-phase process:
1. During the per-card loop: collect which cards are `annihilators` and which are `annihilatees` (lines 2874-2895, 2922-2948)
2. After the loop: resolve resonates by counting pairs and adding attack/gold (lines 3036-3069)

**C++**: Resonate is computed inline during `runScript()` (lines 952-964). When a card's beginOwnTurnScript runs, it counts how many matching resonateType cards exist at that moment and adds resources proportionally.

**Impact**: In AS3, resonate resolution sees the FINAL state after all cards have been processed and all scripts have run. In C++, resonate resolution during each script sees the state at that point in pass 2 iteration.

If script A creates a new unit that is a resonateType target for script B (later in iteration), then:
- AS3: B's resonate count includes A's created unit (because resonate is resolved post-loop)
- C++: B's resonate count includes A's created unit (because A's script ran first in pass 2, creating the unit before B's script runs)

If script B runs BEFORE script A in C++ pass 2 iteration order:
- AS3: B's resonate count STILL includes A's created unit (post-loop resolution)
- C++: B's resonate count does NOT include A's created unit (A hasn't run yet)

**Risk**: LOW. Resonate interactions between beginOwnTurnScripts are very rare. The post-loop resolution in AS3 is technically more correct (order-independent), while C++ is order-dependent.

---

## 6. Risk Summary

| ID | Difference | Severity | Practical Impact | Action |
|----|-----------|----------|-----------------|--------|
| D1 | Attack resource clearing (conditional vs unconditional) | LOW | Identical in normal gameplay | None needed |
| D2 | Dead card lifecycle (table removal vs status transition) | NONE | Implementation detail | None needed |
| D3 | Chill clearing position (unconditional vs post-construction only) | LOW | Chill on constructing units is unusual | Consider moving `m_currentChill = 0` before construction check |
| D4 | Check ordering (construction-first vs lifespan-first) | NONE | Mutually exclusive conditions | None needed |
| D5 | Status reset hasTargetAbility check | LOW | Need to verify affected units | Check `cardLibrary.jso` for units with targetAction but no ability |
| D6 | Blocking reset mechanism | MEDIUM | Different systems; known defense reset bug | Fix defense reset bug (commit 5bf57a8), verify blocking equivalence |
| D7 | Charge gain missing in C++ | **LOW** (verified: no units use chargeGained) | Technical debt only | No action needed — no units define chargeGained |
| D8 | Single-pass vs two-pass scripts | MEDIUM | Edge cases with interacting scripts | Document as known divergence; test with multi-script boards |
| D9 | Resonate resolution timing | LOW | Rare resonate-script interactions | Document as known divergence |

---

## 7. Recommended Follow-ups

1. ~~**[D7]**: Scan `cardLibrary.jso` for units with `chargeGained > 0`.~~ **RESOLVED**: Verification confirmed 0 units use chargeGained. No action needed.

2. **[D6]**: The defense-phase reset bug (commit 5bf57a8) should be fixed by removing lines 1289-1306 from `GameState::beginPhase(Defense)`. The AS3 engine resets blocking only during swoosh (own turn start), not before defense.

3. **[D3]**: Consider moving `m_currentChill = 0` in `Card::beginTurn()` to before the construction/delay checks, matching AS3's unconditional clearing.

4. **[D8]**: Create a test case with two units that have beginOwnTurnScripts where one's script creates/destroys something relevant to the other. Compare AS3 vs C++ outcomes.

5. **[D5]**: Verify which units have `targetAction` set in `cardLibrary.jso` and whether they also have `hasAbility`. If any unit has only targetAction without ability, the C++ status reset is more permissive than AS3.
