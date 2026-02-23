# AS3 Faithful Port — Implementation Plan

**Date:** February 23, 2026
**Branch:** `feature/as3-faithful-port` (to be created from `master`)
**Prerequisite:** [Feasibility Analysis](as3-faithful-port-feasibility.md) (APPROVED)
**Estimated effort:** 7-12 sessions across 6 phases

---

## Goal

Rewrite C++ `GameState` internals as a faithful port of the decompiled AS3 source, eliminating the 6+ unfixed structural divergences found in the engine audit. The 56-method public API (consumed by 91 files with ~1,000+ call sites) remains **unchanged**.

**Why now:** All 722K self-play games must be regenerated anyway (defense reset bug affects every game). A faithful port gives us a correct engine for regeneration, eliminating the entire class of AS3↔C++ divergence bugs.

---

## Phase 0: Documentation Discovery (Consolidated)

### Allowed APIs (Source-Verified)

**C++ Public API to preserve** (from `source/engine/GameState.h:1-162`):
- 7 mutation methods: `doAction`, `doMove`, `beginTurn`, `killCardByID`, `addCard` (×2), `setMana`
- 28 query methods: `getActivePlayer`, `getCardByID`, `getResources`, `numCardsOfType`, `numCards`, `isGameOver`, `getAttack`, `getTotalAvailableDefense`, `winner`, `getTurnNumber`, `getActivePhase`, etc.
- 3 generation methods: `generateLegalActions`, `isLegal`, `getClickAction`
- 3 serialization methods: `toJSONString`, `getStateString`, `getMemoryUsed`
- Plus: `setStartingState`, `addCardBuyable`, `manuallySetAttack`, `manuallySetMana`, `canWipeout`, `isTargetAbilityCardClicked`, `canBreachFrozenCard`, `isIsomorphic`, `isPlayerIsomorphic`, `isBuyable`, `canRunScript`

**AS3 Ground Truth Files** (from `prismata_decompiled/scripts/mcds/engine/`):
| File | Lines | Role |
|---|---|---|
| `State.as` | 4,490 | Core game state machine — processMove, swoosh, checkWin, stagnation |
| `Inst.as` | 504 | Card instance — properties, computed getters, serialization |
| `Card.as` | 753 | Card type definition — costs, scripts, abilities, targeting |
| `StateHelper.as` | 649 | Cached computed properties — defense, attack potential, doom |
| `C.as` | 625 | Constants — MOVE_*, PHASE_*, ROLE_*, DEADNESS_*, MANA_* |

**C++ Files to Modify** (from `source/engine/`):
| File | Lines | Change |
|---|---|---|
| `GameState.cpp` | 2,443 | Major rewrite (private methods, doAction internals) |
| `GameState.h` | 162 | Private members change, public signatures preserved |
| `Card.cpp` | 993 | Moderate rewrite (beginTurn, useAbility, takeDamage) |
| `Card.h` | 148 | Add new member fields for stagnation/death tracking |
| `Constants.h` | 37 | Add stagnation constants |
| `CardData.h` | 69 | Minor (add stagnation counter storage) |

**Audit Findings Reference** (from `docs/audit/`):
- 4 CRITICAL/HIGH bugs already fixed (commits `d44740e`, `5bf57a8`)
- 6 unfixed structural divergences: script ordering (B1), ability cost timing (B3), snipe kill timing (B4), stagnation (A5), death scripts (B7), 4 Condition types (B8)
- 14 areas verified MATCH

### Anti-Pattern Guards (Global)

1. **NEVER change public method signatures** in GameState.h — these are the API contract
2. **NEVER modify files in `source/ai/`** — AI code consumes the API, does not implement game rules
3. **NEVER add UI/animation dispatch** — C++ engine has zero UI coupling (no SFML imports)
4. **NEVER port undo support** (MOVE_UN* types) — C++ search uses state copy, not reverse execution
5. **NEVER port campaign/mission systems** — objectives, triggers, tutorial modes are irrelevant
6. **NEVER port lane system** — positional layout is UI-only
7. **DO preserve isIsomorphic()** — transposition tables depend on it
8. **DO preserve the CardData container** — it handles ID allocation and player-indexed storage

---

## Phase 1: Preservation Infrastructure

**Goal:** Build safety nets before touching any engine code. Every subsequent phase validates against these baselines.

### Task 1.1: Git Baseline

**What to do:**
1. Ensure all audit fixes are committed on `feature/engine-logic-audit`
2. Merge `feature/engine-logic-audit` to `master`
3. Create tag `pre-port-baseline` on master
4. Create branch `feature/as3-faithful-port` from master
5. Build `Release|x86` and save binary as `bin/Prismata_Testing_pre_port.exe`

**Verification:**
- `git tag -l pre-port-baseline` shows the tag
- `bin/Prismata_Testing_pre_port.exe` exists and runs

### Task 1.2: Replay Oracle

**What to do:**
Create `tools/replay_oracle.py` that:
1. Runs `bin/Prismata_Testing_pre_port.exe` against all 2,127 Master Bot replays
2. Records per-replay: code, pass/fail, failure turn/action, turn count
3. Outputs `tools/data/replay_oracle_baseline.json`

**Pattern to follow:** Existing `training/fast_batch_validate.py` runs parallel C++ validation with 4 workers.

**Verification:**
- `replay_oracle_baseline.json` has 2,127 entries
- Pass rate matches known 50.4% (±0.5%)

### Task 1.3: Feature Extraction Snapshots

**What to do:**
Create `tools/feature_snapshot.py` that:
1. Loads 1,000 diverse game positions (sample from self-play shards: early/mid/late game, both players)
2. Runs each through `bin/Prismata_Testing_pre_port.exe --suggest` to extract state
3. Also runs the Python feature vectorizer (`training/vectorize.py` pattern) on the same positions
4. Saves feature vectors to `tools/data/feature_snapshot_baseline.npz`

**Verification:**
- NPZ file has shape `(1000, 1785)` (state_dim from `training/schema.json`)
- No NaN or Inf values

### Task 1.4: Action Legality Oracle

**What to do:**
Create `tools/legality_oracle.py` that:
1. For 10,000 game states (from replays + self-play), calls the C++ engine's `generateLegalActions`
2. Records the complete set of legal actions at each state
3. Saves to `tools/data/legality_oracle_baseline.json`

**Implementation approach:** Extend `--suggest` mode in C++ to also output `"legal_actions":[...]` array. This requires a small addition to `Benchmarks.cpp` (the `--suggest` handler at line ~1847).

**Verification:**
- JSON has 10,000 entries, each with state hash + sorted action list
- All states from distinct games (no duplicates)

### Task 1.5: Performance Baseline

**What to do:**
1. Run a 100-game tournament: `OriginalHardestAI` vs `OriginalHardestAI` with 1s think time
2. Record: total wall time, games/minute, average turns/game
3. Save to `tools/data/performance_baseline.json`

**Reference:** Tournament config pattern in `bin/asset/config/config.txt`.

**Verification:**
- ~4 games/min per 4-thread process (matches known baseline)
- JSON captures exact timing measurements

### Phase 1 Verification Checklist
- [ ] `pre-port-baseline` tag exists on master
- [ ] `feature/as3-faithful-port` branch created
- [ ] Pre-port binary saved
- [ ] Replay oracle: 2,127 replays, 50.4% pass rate
- [ ] Feature snapshot: 1,000 positions, shape (1000, 1785)
- [ ] Legality oracle: 10,000 states with legal action sets
- [ ] Performance baseline: games/min measurement

---

## Phase 2: Architecture Decisions & Scaffolding

**Goal:** Make structural decisions and prepare the code skeleton before porting game logic.

### Decision 2.1: Single-Pass vs Two-Pass Swoosh

**AS3 (State.as:2582-3045):** Single-pass per-card iteration:
```
for each unit:
    clear damage/disruptDamage
    tick constructionTime OR delay OR lifespan
    reset role (hasAbility → DEFAULT, else → INERT)
    reset blocking to defaultBlocking
    apply healthGained, chargeGained
    run beginOwnTurnScript
    process resonate
```

**C++ current (GameState.cpp:1248-1309):** Two-pass:
```
Pass 1: Card::beginTurn() on all cards (lifespan, delay, construct, status reset, health regen)
Pass 2: Run beginOwnTurnScripts on surviving cards
```

**Decision: PORT TO SINGLE-PASS.** This eliminates audit finding B1 (script ordering divergence). The single-pass approach is the ground truth. Cards that create units during their beginOwnTurnScript will see later cards in pre-swoosh state, matching AS3 behavior exactly.

**Implementation:**
- Merge `Card::beginTurn()` logic and script execution into a unified loop in `GameState::beginTurn()`
- `Card::beginTurn()` becomes a simpler per-card reset (no script execution)
- Script execution happens inline in the GameState loop, between per-card resets

### Decision 2.2: Stagnation Counter Storage

**AS3 (State.as:76-100):** Two vectors of 4 ints each: `whiteNoProgress[4]`, `blackNoProgress[4]`

**Decision: Add to GameState as `m_noProgress[2][4]`.**

**New constants** (add to `Constants.h`):
```cpp
namespace Stagnation {
    const int NUM_LEVELS = 4;
    const int CUTOFFS[4] = {2, 8, 20, 40};
    // Level assignments for tracked events:
    const int LEVEL_DELAY_TICKED = 1;
    const int LEVEL_HP_HEALED_PAY_HP = 1;
    const int LEVEL_CHARGE_RECHARGED = 1;
    const int LEVEL_DAMAGE_MORE_THAN_HEALING = 1;
    const int LEVEL_MONEY_STORED = 2;
    const int LEVEL_CARD_BOUGHT = 3;
    const int LEVEL_BUILDTIME_TICKED = 3;
    const int LEVEL_OPP_LIFESPAN_TICKED = 3;
    const int LEVEL_GAS_STORED = 3;
    const int LEVEL_OPP_UNIT_COLLECTED = 4;
}
```

### Decision 2.3: Death Script Execution

**AS3 (State.as:1805-1807, Card.as:320):** `deathScript` runs when unit dies from breach (MOVE_BREACH_OR_OVERKILL and MOVE_WIPEOUT).

**Decision: Add death script execution to `killCardByID()` when cause is Breached or Blocker.**

**Implementation:** After marking card dead in `CardData::killCardByID()`, check if `card.getType().getDeathScript()` is non-empty. If so, call `runScript(cardID, deathScript, ScriptTypes::DeathScript)`. Add `DeathScript` to `ScriptTypes` enum.

**Note:** Currently no cards in `cardLibrary.jso` have deathScript. Verify with: `grep -c "deathScript" bin/asset/config/cardLibrary.jso`. The infrastructure must exist for correctness even if unused.

### Decision 2.4: Resonator/Annihilator Processing

**AS3 (State.as:2770-3000):** During swoosh, after beginOwnTurnScripts:
1. Build dictionary of annihilators (units with `resonate` property) → target card name
2. Build dictionary of annihilatees (units matching target name)
3. For each match: add Attack resource equal to count
4. Similar for `goldResonate` → add Gold resource

**Decision: Port directly.** Add resonator processing as a new private method `processResonators(PlayerID player)` called at end of `beginTurn()`.

**Reference:** `Card.as:243-248` for `resonate` and `goldResonate` property definitions. `cardLibrary.jso` entries with `"resonate"` key.

### Decision 2.5: Ability Cost Timing

**AS3 (State.as:1446-1533):** In MOVE_ASSIGN: health/charge deducted BEFORE script execution.
**C++ current (Card.cpp:775-800):** `useAbility()` deducts AFTER `runAbilityScript()`.

**Decision: PORT TO AS3 ORDER.** Deduct health/charge costs before running the ability script, matching AS3 audit finding B3. Move the cost deduction from `Card::useAbility()` into `GameState::doAction(USE_ABILITY)` before the `runScript()` call.

### Decision 2.6: Snipe Kill Timing

**AS3 (State.as:1484-1510):** In MOVE_ASSIGN with target: runs ability script FIRST, then marks target dead.
**C++ current (GameState.cpp:668-684):** Kills target FIRST, then runs script.

**Decision: PORT TO AS3 ORDER.** Run ability script before killing target, matching AS3 audit finding B4.

### Decision 2.7: Phase Architecture

**AS3:** 3 phases (Action, Defense, Confirm) + `glassBroken` flag for breach state.
**C++:** 5 phases (Action, Defense, Breach, Confirm, Swoosh).

**Decision: KEEP C++ 5-PHASE ARCHITECTURE.** The 5-phase model is more explicit and already works. The extra phases (Breach, Swoosh) are compatible with AS3 semantics — they just make sub-states explicit. Map AS3's `glassBroken=true` to C++'s `Phases::Breach`.

### Task 2.8: Scaffolding Changes

**What to do:**
1. Add stagnation fields to `GameState.h`:
   ```cpp
   int m_noProgress[2][4] = {};  // [player][level]
   ```
2. Add stagnation constants to `Constants.h` (as above)
3. Add `DeathScript` to `ScriptTypes` enum
4. Add `processResonators(PlayerID player)` private method declaration to `GameState.h`
5. Add `resetStagnation(PlayerID player, int level)` and `incrementStagnation()` private method declarations
6. Add `isStagnated(PlayerID player) const` public method to `GameState.h`
7. Verify `Card.as:320` `deathScript` property exists in `CardType` — check `source/engine/CardType.h` for `getDeathScript()`

**Verification:**
- Clean compile with scaffolding (no functional changes yet)
- All existing tests pass
- `isStagnated()` returns false (counters initialized to 0)

### Phase 2 Verification Checklist
- [ ] Architecture decisions documented in code comments
- [ ] Stagnation fields added to GameState.h
- [ ] Constants added to Constants.h
- [ ] ScriptTypes::DeathScript added
- [ ] New method declarations added to GameState.h
- [ ] Clean compile (Debug + Release)
- [ ] Existing tests pass (unchanged behavior)

---

## Phase 3: Core Port — Move Processing

**Goal:** Rewrite `doAction()` internals to match AS3 `processMove()` semantics. This is the largest phase.

### Important Context for Implementer

The C++ `doAction()` switch (GameState.cpp:549-809) maps to AS3 `processMove()` switch (State.as:1433-2063). The mapping is NOT 1:1 — AS3 has 16 move types, C++ has 13 action types. Some AS3 moves map to C++ phase transitions rather than explicit actions.

**AS3 → C++ Action Type Mapping:**

| AS3 Move | C++ ActionType | Notes |
|---|---|---|
| `MOVE_ASSIGN` | `USE_ABILITY` | Same: activate ability, pay costs, run script |
| `MOVE_BUY` | `BUY` | Same: purchase card |
| `MOVE_SELL` | `SELL` | Same: sell card back |
| `MOVE_DEFEND` | `ASSIGN_BLOCKER` | Same: block with unit |
| `MOVE_BREACH_OR_OVERKILL` | `ASSIGN_BREACH` | Same: breach enemy unit |
| `MOVE_WIPEOUT` | `WIPEOUT` | Same: break through all blockers |
| `MOVE_MELEE` | `ASSIGN_FRONTLINE` | Same: frontline attack |
| `MOVE_END_DEFENSE` | `END_PHASE` (from Defense) | Phase transition |
| `MOVE_ENTER_CONFIRM` | `END_PHASE` (from Action) | Phase transition |
| `MOVE_COMMIT` | Implicit in `endPhase(Confirm)` | Turn boundary |
| (snipe part of ASSIGN) | `SNIPE` | C++ split targeting into separate action |
| (chill part of ASSIGN) | `CHILL` | C++ split targeting into separate action |
| `MOVE_UNASSIGN` | `UNDO_USE_ABILITY` | Skip — keep C++ version |
| `MOVE_UNBREACH_OR_UNOVERKILL` | `UNDO_BREACH` | Skip — keep C++ version |
| `MOVE_UNWIPEOUT` | N/A | Skip — C++ uses state copy |
| `MOVE_UNMELEE` | N/A | Skip — C++ uses state copy |
| `MOVE_UNDEFEND` | N/A | Skip — C++ uses state copy |

### Task 3.1: Port BUY Action

**AS3 Reference:** State.as:1625-1648 (MOVE_BUY)
**C++ Location:** GameState.cpp:565-574

**What to change:**
1. Verify buy cost subtraction matches AS3 `payCost()` (State.as cost handling)
2. Verify buy-sac card selection matches AS3 `wouldBeSacced()` sort order (State.as:1242-1280)
3. Add stagnation reset: `resetStagnation(player, Stagnation::LEVEL_CARD_BOUGHT)` after successful buy
4. Run buy script with AS3 timing (currently correct — runs after purchase)

**Verification:** Replay oracle — BUY actions should not regress.

### Task 3.2: Port USE_ABILITY Action (Critical — Timing Change)

**AS3 Reference:** State.as:1446-1533 (MOVE_ASSIGN)
**C++ Location:** GameState.cpp:576-631

**What to change:**
1. **Reorder cost deduction** (Decision 2.5): Move health/charge cost deduction BEFORE `runScript()`. Currently in `Card::useAbility()` which runs after script.
2. For target abilities: keep the two-step model (USE_ABILITY sets target state, SNIPE/CHILL applies effect)
3. AS3 sets `inst.role = ASSIGNED` before script — verify C++ matches
4. AS3 pays `abilityCost` (mana) separately from health/charge — verify separation

**Key AS3 sequence (State.as:1446-1533):**
```
1. card.healthUsed > 0 → inst.health -= card.healthUsed  (BEFORE script)
2. card.chargeUsed > 0 → inst.charge -= card.chargeUsed  (BEFORE script)
3. inst.role = ASSIGNED
4. payCost(card.abilityCost)   — mana cost
5. sac(card.abilitySac)         — sacrifice cost
6. netherfy() if needed
7. runScriptForward(card.abilityScript)
8. Handle target ability (snipe/chill)
```

**C++ current sequence:**
```
1. runScript(cardID, abilityScript)  — which calls card.useAbility() at end
2. card.useAbility() → deducts health/charge, sets Assigned
```

**Implementation:**
- Extract health/charge deduction from `Card::useAbility()` into a new `Card::payAbilityCost()` method
- Call `payAbilityCost()` in `doAction(USE_ABILITY)` BEFORE `runScript()`
- `Card::useAbility()` still sets status to Assigned but no longer deducts costs

**Verification:** Run replay oracle — watch for USE_ABILITY regressions (this is the #1 failure category at 40.7%).

### Task 3.3: Port SNIPE Action (Critical — Timing Change)

**AS3 Reference:** State.as:1484-1510 (snipe within MOVE_ASSIGN)
**C++ Location:** GameState.cpp:668-684

**What to change (Decision 2.6):**
1. **Reorder kill timing:** Run ability script BEFORE killing target
2. AS3 sequence: `runScriptForward()` → `target.deadness = SNIPED`
3. C++ current: `killCardByID(target, Sniped)` → `runScript(source, abilityScript)`

**New C++ sequence:**
```cpp
case ActionTypes::SNIPE:
    card.setTargetID(target.getID());
    runScript(cardID, card.getType().getAbilityScript(), AbilityScript);  // FIRST
    killCardByID(targetCardID, CauseOfDeath::Sniped);                    // THEN kill
    // Clear target ability state
    break;
```

**Verification:** Find replays with snipe units (Tarsier variants, Apollo, Lancetooth) and verify no regressions.

### Task 3.4: Port CHILL Action

**AS3 Reference:** State.as:1484-1510 (chill within MOVE_ASSIGN)
**C++ Location:** GameState.cpp:686-702

**What to change:**
1. Match AS3 chill application: `target.disruptDamage += card.targetAmount`
2. AS3 checks if chill kills: `if disruptDamage >= damageItCanTake+damage → blocking=false`
3. Verify C++ `applyChill()` matches this logic
4. Verify script runs BEFORE applying chill (matching Decision 2.6 pattern)

**Verification:** Chill-heavy replays (Shiver Yeti, Frostbite, Cryo Ray games).

### Task 3.5: Port ASSIGN_BLOCKER (Defense Phase Blocking)

**AS3 Reference:** State.as:1712-1778 (MOVE_DEFEND)
**C++ Location:** GameState.cpp:638-644

**What to verify (mostly correct already):**
1. `blockWithCard()` (GameState.cpp:1564-1580) reduces enemy attack by `min(attack, health)`
2. Card takes damage, killed if lethal
3. **Confirm no status reset before defense** (audit fix already applied)
4. Add stagnation tracking: when own unit blocks, this constitutes "progress" for the attacker

**Verification:** Defense-heavy replays; verify blocker eligibility matches AS3 `couldDefendThisTurn` (StateHelper.as).

### Task 3.6: Port ASSIGN_BREACH

**AS3 Reference:** State.as:1779-1854 (MOVE_BREACH_OR_OVERKILL)
**C++ Location:** GameState.cpp:646-655

**What to change:**
1. **Add death script execution:** When breach kills a unit, check for `deathScript` and execute
2. AS3 runs `runScriptForward(card.deathScript)` on breach kill (State.as:1805-1807)
3. C++ `breachCard()` (line 1583-1596) calls `killCardByID` but no death script

**New logic after `breachCard()`:**
```cpp
if (card.isDead() && card.getType().hasDeathScript()) {
    runScript(card.getID(), card.getType().getDeathScript(), ScriptTypes::DeathScript);
}
```

**Verification:** Check `cardLibrary.jso` for any units with `deathScript`. If none exist, add a synthetic test.

### Task 3.7: Port WIPEOUT

**AS3 Reference:** State.as:1855-1876 (MOVE_WIPEOUT)
**C++ Location:** GameState.cpp:704-707

**What to verify:**
1. Break statement is present (already fixed, commit d44740e)
2. Wipeout damage to all blockers happens in `blockWithAllBlockers()` (called from `endPhase(Action)`)
3. Add death script execution for each blocker killed during wipeout
4. AS3 sets `glassBroken = true` — verify C++ enters `Phases::Breach` equivalently

**Verification:** Replays with wipeout scenarios (high-attack games).

### Task 3.8: Port endPhase() — Confirm Phase Turn Boundary

**AS3 Reference:** State.as:1911-1970 (MOVE_ENTER_CONFIRM + MOVE_COMMIT)
**C++ Location:** GameState.cpp:1404-1433

**What to change:**
1. **Add stagnation increment:** Call `incrementStagnation()` at turn boundary
2. **Add stagnation win check:** In `calculateGameOver()`, check `isStagnated()` for both players
3. Match AS3's stagnation check timing: happens during ENTER_CONFIRM (State.as:1911-1951)

**New stagnation check in calculateGameOver():**
```cpp
// After existing doomed check:
for (int p = 0; p < 2; p++) {
    bool stagnated = true;
    for (int level = 0; level < Stagnation::NUM_LEVELS; level++) {
        if (m_noProgress[p][level] < Stagnation::CUTOFFS[level]) {
            stagnated = false;
            break;
        }
    }
    if (stagnated) return true;  // Draw by stagnation
}
```

**Verification:** Create synthetic game states that trigger stagnation at each level.

### Task 3.9: Port isLegal()

**AS3 Reference:** StateHelper.as computed properties determine legality; State.as processMove validates
**C++ Location:** GameState.cpp:189-545

**What to change:**
1. **Add missing Condition types** (audit finding B8): `IS_BLOCKING`, `NAME_IN`, `IS_ABC`, `IS_ENGINEER_TEMP`
2. These are in `Card::meetsCondition()` — check `source/engine/Card.cpp` for the condition switch
3. Reference: `C.as:52-64` for condition constant definitions

**Verification:** Find replays using units with target conditions (Kinetic Driver, Centurion).

### Phase 3 Verification Checklist
- [ ] BUY action matches AS3 (stagnation reset added)
- [ ] USE_ABILITY cost timing: health/charge BEFORE script
- [ ] SNIPE kill timing: script BEFORE kill
- [ ] CHILL application matches AS3 formula
- [ ] ASSIGN_BLOCKER: no status reset, correct damage
- [ ] ASSIGN_BREACH: death script execution added
- [ ] WIPEOUT: death scripts for killed blockers
- [ ] Turn boundary: stagnation increment + win check
- [ ] isLegal: 4 missing Condition types added
- [ ] Clean compile (Debug + Release)
- [ ] Replay oracle: pass rate equal or better than 50.4% baseline
- [ ] Legality oracle: no regressions on 10,000 states

---

## Phase 4: Core Port — Swoosh/beginTurn Rewrite

**Goal:** Port the swoosh (turn transition) to single-pass architecture matching AS3.

### Task 4.1: Rewrite beginTurn() to Single-Pass

**AS3 Reference:** State.as:2582-3045 (swoosh method)
**C++ Location:** GameState.cpp:1248-1309

**What to change:** Replace the two-pass architecture with single-pass:

**New sequence (per-card, matching AS3:2614-2770):**
```cpp
void GameState::beginTurn(PlayerID player) {
    // 1. Reset per-turn resources (keep existing: lines 1252-1256)
    m_resources[player].set(Resources::Attack, 0);
    m_resources[player].set(Resources::Energy, 0);
    // ... etc

    // 2. Reset breach flag
    m_canBreachFrozenCard = false;

    // 3. Snapshot alive cards (for safe iteration during kills)
    CardIDVector aliveAtStart = m_cards.getCardIDs(player);

    // 4. Single-pass: per-card processing
    for (CardID cardID : aliveAtStart) {
        Card& card = _getCardByID(cardID);
        if (card.isDead()) continue;

        // a. Clear damage and chill (AS3:2624-2640)
        card.clearDamage();
        card.clearChill();

        // b. Tick construction OR delay OR lifespan (AS3:2642-2695)
        if (card.isUnderConstruction()) {
            card.tickConstruction();
            // Stagnation: resetStagnation(player, LEVEL_BUILDTIME_TICKED)
        } else if (card.isDelayed()) {
            card.tickDelay();
            // Stagnation: resetStagnation(player, LEVEL_DELAY_TICKED)
        } else if (card.getCurrentLifespan() > 0) {
            card.tickLifespan();
            if (card.getCurrentLifespan() == 0) {
                killCardByID(cardID, CauseOfDeath::Lifespan);
                // Stagnation: resetStagnation(getEnemy(player), LEVEL_OPP_LIFESPAN_TICKED)
                continue;
            }
        }

        // c. Reset role (AS3:2698-2705)
        if (card.getType().hasAbility()) {
            card.setStatus(CardStatus::Default);
        } else {
            card.setStatus(CardStatus::Inert);
        }

        // d. Reset blocking (AS3:2706)
        // (blocking is derived from status in C++, no explicit field)

        // e. Apply health regen (AS3:2708-2725)
        card.applyHealthRegen();

        // f. Apply charge regen (AS3:2726-2738)
        card.applyChargeRegen();

        // g. Run beginOwnTurnScript INLINE (AS3:2739+)
        if (card.canRunBeginOwnTurnScript()) {
            const Script& script = card.getType().getBeginOwnTurnScript();
            if (!script.isEmpty()) {
                runScript(cardID, script, ScriptTypes::BeginTurnScript);
                if (card.isDead()) {
                    killCardByID(cardID, CauseOfDeath::Unknown);
                }
            }
        }
    }

    // 5. Process resonators (NEW — see Task 4.2)
    processResonators(player);

    // 6. Increment stagnation counters
    incrementStagnation();

    // 7. Remove killed cards
    m_cards.removeKilledCards();
}
```

**Key difference from current C++:** Scripts run INLINE per-card, not in a separate pass. This means when card N's script runs, cards 0..N-1 have been processed but cards N+1..end are still in pre-swoosh state. This exactly matches AS3.

### Task 4.2: Implement Resonator Processing

**AS3 Reference:** State.as:2770-3000 (resonance/annihilation in swoosh)
**C++ Reference:** `cardLibrary.jso` entries with `"resonate"` or `"goldResonate"` keys

**New method `processResonators(PlayerID player)`:**
```cpp
void GameState::processResonators(PlayerID player) {
    // For each alive card with resonate property:
    //   Count matching alive cards of the resonance target type
    //   Add Attack resource per match
    // For each alive card with goldResonate property:
    //   Count matching alive cards
    //   Add Gold resource per match
}
```

**Reference for card properties:** `CardType::getResonate()` and `CardType::getGoldResonate()` — verify these exist in `source/engine/CardType.h`. If not, check `cardLibrary.jso` parsing in `CardTypeInfo.cpp`.

### Task 4.3: Update Card::beginTurn() to Simpler Reset

**C++ Location:** Card.cpp:574-643

**What to change:** Since the per-card logic is now in `GameState::beginTurn()`, simplify `Card::beginTurn()` to only handle:
1. Reset per-turn flags (`m_sellable`, `m_damageTaken`, `m_wasBreached`, `m_abilityUsedThisTurn`)
2. Clear killed/created IDs
3. Clear target
4. Transition `KilledThisTurn` → `Dead`

Remove from `Card::beginTurn()`:
- Lifespan decrement (moved to GameState)
- Delay decrement (moved to GameState)
- Health regen (moved to GameState)
- Chill reset (moved to GameState)
- Status reset (moved to GameState)

### Task 4.4: Implement Stagnation Event Tracking

**AS3 Reference:** State.as:76-100 (constants), State.as:1293-1363 (reset logic)

**Where to add stagnation resets** (each resets counters for levels ≤ the event's level):

| Event | Level | Where in C++ |
|---|---|---|
| Card bought / unit created | 3 | `doAction(BUY)`, `runScript()` create section |
| BuildTime ticked | 3 | `beginTurn()` construction tick |
| Delay ticked | 1 | `beginTurn()` delay tick |
| HP healed on pay-HP unit | 1 | `beginTurn()` health regen (if unit has healthUsed>0) |
| Charge recharged | 1 | `beginTurn()` charge regen |
| Money stored | 2 | `endPhase()` or resource tracking |
| Opp lifespan ticked | 3 | `beginTurn()` for opponent's lifespan tick |
| Opp unit collected | 4 | `endPhase(Confirm)` body collection |
| Gas stored (Gaussite/Gauss Charge/Cluster Bolt) | 3 | Unit-specific, check scripts |
| Damage > healing | 1 | `endPhase(Action)` attack calculation |

**Implementation:** Call `resetStagnation(player, level)` at each trigger point. The reset function zeros counters for levels 0 through `level-1`:
```cpp
void GameState::resetStagnation(PlayerID player, int level) {
    for (int i = 0; i < level; i++) {
        m_noProgress[player][i] = 0;
    }
}
```

### Phase 4 Verification Checklist
- [ ] Single-pass swoosh matches AS3 card processing order
- [ ] Resonator processing produces correct Attack/Gold resources
- [ ] Card::beginTurn() simplified, no duplicate logic
- [ ] Stagnation counters increment correctly
- [ ] Stagnation resets fire at correct trigger points
- [ ] Games that should stagnate now end before turn 200
- [ ] Clean compile (Debug + Release)
- [ ] Replay oracle: pass rate improved (target: >60%)
- [ ] Feature snapshot: <1% positions changed (health regen / status values)
- [ ] Performance: <10% regression vs baseline

---

## Phase 5: New Systems

**Goal:** Add remaining AS3 systems not present in C++.

### Task 5.1: Spell Collection

**AS3 Reference:** State.as `collectSpells()` — called during swoosh
**What:** Units with `cardType == "spell"` have duration-based removal. After their effect resolves, they are collected (removed from play).

**Implementation:** Add check in `beginTurn()`: if card type is spell and conditions met, kill card.

**Verification:** Check `cardLibrary.jso` for spell-type units.

### Task 5.2: Mana Rot

**AS3 Reference:** State.as `manaRots()` — called during MOVE_ENTER_CONFIRM
**What:** Certain temporary resources decay at turn boundary.

**Implementation:** Check if any resource types have decay in AS3. If so, add decay logic to `endPhase(Confirm)`.

**Verification:** Check AS3 for which resources rot and under what conditions.

### Task 5.3: Missing Condition Types

**AS3 Reference:** C.as:52-64
**C++ Location:** `Card::meetsCondition()` in Card.cpp

**What to add:**
1. `IS_BLOCKING` — card is currently blocking (`canBlock() && status == Default`)
2. `NAME_IN` — card name is in a list of names
3. `IS_ABC` — card meets ABC criteria (check AS3 for semantics)
4. `IS_ENGINEER_TEMP` — special check for Engineer unit

**Verification:** Find unit abilities that use these conditions (grep `cardLibrary.jso` for `"condition"`).

### Phase 5 Verification Checklist
- [ ] Spell collection implemented (if applicable)
- [ ] Mana rot implemented (if applicable)
- [ ] 4 Condition types added
- [ ] All conditions tested with relevant unit abilities
- [ ] Clean compile
- [ ] Replay oracle: further improvement

---

## Phase 6: Validation & Regression Testing

**Goal:** Comprehensive validation that the port is correct and nothing regressed.

### Task 6.1: Replay Oracle Comparison

**What to do:**
1. Run all 2,127 Master Bot replays through the ported engine
2. Compare against `replay_oracle_baseline.json`
3. Categorize: newly passing, still failing, newly failing (REGRESSIONS)

**Success criteria:**
- **Target: >80% pass rate** (up from 50.4%)
- **Zero regressions** — no replay that passed before should now fail
- Any regressions must be investigated and explained before proceeding

### Task 6.2: Feature Extraction Comparison

**What to do:**
1. Run same 1,000 positions through ported engine
2. Extract feature vectors
3. Diff against `feature_snapshot_baseline.npz`

**Success criteria:**
- **>99% positions identical** features
- Changed positions must be explainable (e.g., stagnation counters are new features, health values differ due to corrected regen timing)

### Task 6.3: Action Legality Comparison

**What to do:**
1. Run same 10,000 states through ported engine
2. Generate legal action sets
3. Diff against `legality_oracle_baseline.json`

**Success criteria:**
- **>99.5% identical** legal action sets
- Differences must be explainable (e.g., new Condition types unlock/restrict actions, stagnation draw enables "claim draw" action)

### Task 6.4: Performance Comparison

**What to do:**
1. Run same 100-game tournament benchmark
2. Compare games/minute

**Success criteria:**
- **≤10% regression** (>3.6 games/min if baseline is 4)
- If regression >10%, profile with `/PROFILE` and identify hotspot (likely StateHelper recomputation)

### Task 6.5: Tournament Smoke Test

**What to do:**
1. Run 100-game tournament: `PrismatAlpha_AB` vs `OriginalHardestAI` with 7s think
2. Verify AI functions correctly (no crashes, reasonable win rate)
3. Run 100-game tournament: `OriginalHardestAI` vs `OriginalHardestAI` (self-play quality check)

**Success criteria:**
- No crashes or assertions
- Win rates within expected ranges (±5pp of known baselines)

### Task 6.6: Edge Case Testing

**What to do:**
1. Test stagnation: create game states that should trigger each stagnation level
2. Test death scripts: create game states with units that have deathScript (if any exist)
3. Test resonators: create game states with resonator units
4. Test all-doomed: verify instant-win with lifespan units
5. Test mutual elimination: verify draw when both lose all units

**Implementation:** Add these as C++ unit tests in a new `source/testing/PortValidation.cpp`.

### Phase 6 Verification Checklist
- [ ] Replay oracle: >80% pass rate, 0 regressions
- [ ] Feature extraction: >99% identical
- [ ] Action legality: >99.5% identical
- [ ] Performance: ≤10% regression
- [ ] Tournament smoke test: no crashes, reasonable win rates
- [ ] Edge cases: stagnation, death scripts, resonators, doomed, mutual elimination
- [ ] All results documented in `docs/port-validation-results.md`

---

## Rollback Strategy

### If the Port Goes Wrong

At any point during Phases 3-5, if a phase introduces unrecoverable issues:

1. **Revert to phase boundary:** Each phase begins with a clean commit. `git reset --hard <phase-start-commit>`.
2. **Revert to pre-port:** `git checkout pre-port-baseline` restores the original engine.
3. **Pre-port binary is preserved:** `bin/Prismata_Testing_pre_port.exe` can regenerate data with the old (buggy but known) engine.

### If Performance Regresses >20%

1. Profile with VS2022 Performance Profiler
2. Most likely culprit: stagnation counter checks (12 events × every action)
3. Optimization: batch stagnation updates per turn instead of per action
4. Fallback: disable stagnation entirely (revert to 200-turn limit) while keeping other port improvements

### If Replay Pass Rate Decreases

This should never happen — the port makes the engine MORE correct. If it does:
1. Run both old and new engines on the failing replay
2. Identify the first divergent action
3. Compare against AS3 ground truth to determine which engine is correct
4. If old engine was accidentally correct, the new engine has a bug — fix it

---

## Appendix A: Complete AS3 → C++ Naming Dictionary

| AS3 | C++ | Notes |
|---|---|---|
| `role` (String) | `m_status` (CardStatus enum) | "default"→Default, "assigned"→Assigned, "inert"→Inert, "sellable"→Inert+m_sellable |
| `deadness` (String) | `m_dead` + `m_causeOfDeath` | "alive"→Alive, "breached"→Breached, "sniped"→Sniped, etc. |
| `disruptDamage` | `m_currentChill` | Same semantics |
| `blocking` (Boolean) | Derived from `canBlock()` | AS3 explicit field, C++ computed |
| `damageItCanTake` | `currentHealth()` | Similar but not identical computation |
| `MOVE_ASSIGN` | `USE_ABILITY` | Plus SNIPE/CHILL for target abilities |
| `MOVE_MELEE` | `ASSIGN_FRONTLINE` | Same: frontline attack |
| `MOVE_DEFEND` | `ASSIGN_BLOCKER` | Same: block with unit |
| `glassBroken` | `Phases::Breach` | Flag vs separate phase |
| `processMove()` | `doAction()` | Different parameter encoding |
| `swoosh()` | `beginTurn()` | Same lifecycle |
| `checkWin()` | `calculateGameOver()` + `winner()` | Split into detection and determination |
| `helper` (StateHelper) | N/A (to be added) | Cached computed properties |
| `whiteNoProgress[4]` | `m_noProgress[0][4]` | Stagnation counters |
| `blackNoProgress[4]` | `m_noProgress[1][4]` | Stagnation counters |
| `table` (Dictionary) | `m_cards` (CardData) | Different container type |
| `turnMana` | `m_resources[getActivePlayer()]` | Player-indexed resources |
| `COLOR_WHITE/BLACK` | `Players::Player_One/Two` | Player IDs |

## Appendix B: Files Modified Per Phase

| Phase | Files Created | Files Modified |
|---|---|---|
| 1 | `tools/replay_oracle.py`, `tools/feature_snapshot.py`, `tools/legality_oracle.py` | None (infrastructure only) |
| 2 | None | `GameState.h`, `Constants.h` (scaffolding) |
| 3 | None | `GameState.cpp`, `Card.cpp` (core port) |
| 4 | None | `GameState.cpp`, `Card.cpp`, `Card.h` (swoosh rewrite) |
| 5 | None | `Card.cpp` (conditions), `GameState.cpp` (spell/mana rot) |
| 6 | `source/testing/PortValidation.cpp`, `docs/port-validation-results.md` | None (validation only) |

## Appendix C: Success Metrics Summary

| Metric | Pre-Port Baseline | Phase 3 Target | Phase 6 Final Target |
|---|---|---|---|
| Replay pass rate | 50.4% | >55% | **>80%** |
| Feature match | (not measured) | >95% | **>99%** |
| Legal action match | (not measured) | >98% | **>99.5%** |
| Performance | ~4 games/min | No regression | **≤10% regression** |
| Structural divergences | 6+ unfixed | 3 remaining | **0** |
| Self-play data quality | Defense bug | Bug-free | **All fixes applied** |
