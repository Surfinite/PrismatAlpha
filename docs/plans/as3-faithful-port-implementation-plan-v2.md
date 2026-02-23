# AS3 Faithful Port — Implementation Plan v2

**Date:** February 23, 2026
**Branch:** `feature/as3-faithful-port` (to be created from `master`)
**Prerequisite:** [Feasibility Analysis](as3-faithful-port-feasibility.md) (APPROVED)
**Meta-review:** [META-REVIEW](META-REVIEW-as3-faithful-port-implementation-plan.md) (9 reviewers, all claims codebase-validated)
<!-- CHANGED: Effort estimate increased from 7-12 to 10-18 sessions — R8, validated by stagnation complexity discovery -->
**Estimated effort:** 10-18 sessions across 7 phases

---

## Goal

Rewrite C++ `GameState` internals as a faithful port of the decompiled AS3 source, eliminating the 6+ unfixed structural divergences found in the engine audit. The 56-method public API (consumed by 91 files with ~1,000+ call sites) remains **unchanged**.

**Why now:** All 722K self-play games must be regenerated anyway (defense reset bug affects every game). A faithful port gives us a correct engine for regeneration, eliminating the entire class of AS3↔C++ divergence bugs.

<!-- CHANGED: Added "correcter vs correct" acknowledgment — R9 -->
**Important framing:** The AS3 decompiled source is our ground truth for *replay compatibility* — matching it guarantees replays pass validation. It may contain its own quirks or edge-case behaviors that differ from "ideal" game design. The goal is **faithfulness to the live game**, not abstract correctness.

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
<!-- CHANGED: Strengthened anti-pattern guard to also cover adding new public methods — R1, R3, R5, R7, R8 -->
2. **NEVER add new public methods** to GameState.h unless absolutely necessary — expanding the API surface creates new contracts to maintain. Stagnation checks, death script execution, and resonator processing must be PRIVATE.
3. **NEVER modify files in `source/ai/`** — AI code consumes the API, does not implement game rules
4. **NEVER add UI/animation dispatch** — C++ engine has zero UI coupling (no SFML imports)
5. **NEVER port undo support** (MOVE_UN* types) — C++ search uses state copy, not reverse execution
6. **NEVER port campaign/mission systems** — objectives, triggers, tutorial modes are irrelevant
7. **NEVER port lane system** — positional layout is UI-only
8. **DO preserve isIsomorphic()** — transposition tables depend on it
9. **DO preserve the CardData container** — it handles ID allocation and player-indexed storage
<!-- CHANGED: Added commit discipline guidance — R5 -->
10. **DO commit per-move-type** in Phase 3 and per-subsystem in Phase 4 — enables `git bisect` when regressions appear

---

<!-- APPLIED: Optional #1 — AS3 code inventory before coding — R7 -->
## Phase 0.5: AS3 Code Inventory

**Goal:** Read ALL relevant AS3 source and produce a line-by-line mapping document before writing any C++ port code. This prevents "translate as you go" mistakes where the implementer misunderstands AS3 semantics mid-port.

### Task 0.5.1: Create AS3 → C++ Mapping Spreadsheet

**What to do:**
1. Read every function in `State.as`, `Inst.as`, `Card.as`, `StateHelper.as`, `C.as` that is in-scope for the port
2. For each AS3 function, record:
   - AS3 file:line range
   - Function name and purpose (1 line)
   - C++ equivalent (existing method or "NEW")
   - Key semantic differences (if any)
   - Port priority (Phase 3/4/5/skip)
3. Output to `docs/as3-cpp-mapping.md`

**What to skip:** Functions tagged SKIP in the feasibility analysis (undo, campaign, triggers, UI dispatch, lane system).

**Verification:**
- Every in-scope AS3 function has a C++ mapping entry
- No "NEW" entries are surprises — all match the plan's scope

---

## Phase 1: Preservation Infrastructure

**Goal:** Build safety nets before touching any engine code. Every subsequent phase validates against these baselines.

<!-- CHANGED: Added oracle split concept — R3, R5, R7, all 9 reviewers -->
**Important distinction:** Phase 1 oracles capture the OLD engine's behavior. They serve as **regression detectors** (did we accidentally break something that was already correct?), NOT as correctness measures. Correctness is measured against AS3 ground truth in Phase 6.

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

### Task 1.2: Replay Oracle (Regression Baseline)

**What to do:**
Create `tools/replay_oracle.py` that:
1. Runs `bin/Prismata_Testing_pre_port.exe` against all 2,127 Master Bot replays
2. Records per-replay: code, pass/fail, failure turn/action, turn count
3. Outputs `tools/data/replay_oracle_baseline.json`

**Pattern to follow:** Existing `training/fast_batch_validate.py` runs parallel C++ validation with 4 workers.

**Verification:**
- `replay_oracle_baseline.json` has 2,127 entries
- Pass rate matches known 50.4% (±0.5%)

### Task 1.3: Feature Extraction Snapshots (Regression Baseline)

**What to do:**
Create `tools/feature_snapshot.py` that:
1. Loads 1,000 diverse game positions (sample from self-play shards: early/mid/late game, both players)
2. Runs each through `bin/Prismata_Testing_pre_port.exe --suggest` to extract state
3. Also runs the Python feature vectorizer (`training/vectorize.py` pattern) on the same positions
4. Saves feature vectors to `tools/data/feature_snapshot_baseline.npz`

<!-- CHANGED: Clarified that feature snapshots are regression baselines, not intermediate comparison targets — R6 -->
**Note:** Feature vectors WILL change during the port (ability cost timing, swoosh order, status resets all affect intermediate state). This baseline is for final Phase 6 comparison and forensics, NOT for intermediate phase gates.

**Verification:**
- NPZ file has shape `(1000, 1785)` (state_dim from `training/schema.json`)
- No NaN or Inf values

### Task 1.4: Action Legality Oracle (Regression Baseline)

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

<!-- CHANGED: Added Task 1.6 State-Hash Differential Oracle — R3, R5, R6, R7, R8 (highest-value addition per R5) -->
### Task 1.6: State-Hash Differential Oracle

**What to do:**
Create `tools/state_diff_oracle.py` that:
1. Runs replays through BOTH old (`pre_port.exe`) and new (current build) engines simultaneously
2. After each action, compares game state via `toJSONString()` output
3. Detects the first point of state divergence per replay
4. Records: replay code, divergence turn, divergence action, old state snippet, new state snippet

**Why this matters:** Replay pass/fail only checks action legality — a replay can "pass" while the engine produces completely different game states. This oracle catches semantic divergence that legality testing misses.

**Implementation:** Extend `--suggest` mode to accept a sequence of actions and output state JSON after each. Or use `toJSONString()` comparison from the replay validation harness.

**Verification:**
- Run against 100 known-passing replays — should show 0 divergences (old vs old)
- Infrastructure ready for Phase 3+ incremental use

<!-- APPLIED: Optional #7 — Debug state hash for lightweight state comparison — R5 -->
### Task 1.7: Debug State Hash

**What to do:**
Implement a lightweight `debugStateHash()` method on GameState that produces a cheap numeric hash for rapid state comparison. Unlike `isIsomorphic()` (which does full structural comparison) or `toJSONString()` (which produces large strings), this hash is designed for high-frequency differential testing.

**Implementation:**
```cpp
uint64_t GameState::debugStateHash() const {
    uint64_t h = 0;
    h ^= std::hash<int>()(m_turnNumber) * 0x9e3779b97f4a7c15ULL;
    h ^= std::hash<int>()(m_activePlayer) * 0x517cc1b727220a95ULL;
    h ^= std::hash<int>()(m_activePhase) * 0x6c62272e07bb0142ULL;
    for (int p = 0; p < 2; p++) {
        h ^= m_resources[p].hash() * (p + 1);
        for (int i = 0; i < 4; i++)
            h ^= std::hash<int>()(m_noProgress[p][i]) * (i + 5);
    }
    // Hash card states (order-independent via XOR)
    for (each card) h ^= card.debugHash();
    return h;
}
```

**Use case:** State-hash differential oracle (Task 1.6) can compare `debugStateHash()` after every action for fast divergence detection, falling back to `toJSONString()` only when hashes differ.

**Verification:**
- Different game states produce different hashes (test on 1,000 state pairs)
- Isomorphic states produce identical hashes (test on 100 known-isomorphic pairs)

### Phase 1 Verification Checklist
- [ ] `pre-port-baseline` tag exists on master
- [ ] `feature/as3-faithful-port` branch created
- [ ] Pre-port binary saved
- [ ] Replay oracle: 2,127 replays, 50.4% pass rate
- [ ] Feature snapshot: 1,000 positions, shape (1000, 1785)
- [ ] Legality oracle: 10,000 states with legal action sets
- [ ] Performance baseline: games/min measurement
<!-- CHANGED: Added state-hash differential to checklist -->
- [ ] State-hash differential oracle: infrastructure validated on known-passing replays
- [ ] Debug state hash: implemented and tested

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
    // Level assignments for tracked events (1-based in AS3, 0-indexed in arrays):
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

<!-- CHANGED: Expanded stagnation to 3 reset functions matching AS3 — R1-R9 (9/9), validated by AS3 State.as:1291-1349 -->
### Decision 2.2b: Stagnation Reset Functions

**AS3 has THREE distinct reset functions** (State.as:1291-1349), not one:
1. `resetTurnNoProgressCounters(level)` — resets CURRENT TURN player's counters for indices `0..level-1`
2. `resetOppNoProgressCounters(level)` — resets OPPONENT's counters for indices `0..level-1`
3. `resetColorNoProgressCounters(color, level)` — resets a specific color's counters for indices `0..level-1`

**Decision: Port all 3 reset functions as private methods.**
```cpp
void resetTurnProgress(int level);   // Resets active player's counters [0..level)
void resetOppProgress(int level);    // Resets opponent's counters [0..level)
void resetColorProgress(PlayerID player, int level);  // Resets specific player's counters [0..level)
```

<!-- CHANGED: Centralized stagnation behind ProgressEvent enum — R1-R9 (9/9) -->
**Centralized tracking via enum:**
```cpp
enum class ProgressEvent {
    DelayTicked,          // level 1, resets turn player
    HPHealedOnPayHP,      // level 1, resets turn player
    ChargeRecharged,      // level 1, resets turn player
    DamageMoreThanHealing,// level 1, resets turn player
    MoneyStored,          // level 2, resets turn player
    CardBought,           // level 3, resets turn player
    BuildTimeTicked,      // level 3, resets turn player
    OppLifespanTicked,    // level 3, resets OPPONENT
    GasStored,            // level 3, resets turn player
    OppUnitCollected,     // level 4, resets turn player
};

void reportProgress(ProgressEvent event);  // Dispatches to correct reset function + level
```

This centralizes the mapping from event → player → level in ONE place, avoiding scattered `resetTurnProgress(Stagnation::LEVEL_CARD_BOUGHT)` calls.

**IMPORTANT: Complex ENTER_CONFIRM stagnation** (State.as:1895-1954) is a separate if-else chain that depends on StateHelper computed properties (`oppDefense`, `maxOppDefenderHealth`, `partiallyDamagedInst`, `totalProducedThisTurn`). This will be ported in Phase 5 after simple stagnation events are working.

### Decision 2.3: Death Script Execution

**AS3 (State.as:1805-1807, Card.as:320):** `deathScript` runs when unit dies from breach (MOVE_BREACH_OR_OVERKILL and MOVE_WIPEOUT).

<!-- CHANGED: Single dispatch from killCardByID instead of per-caller — R1, R2, R3, R6, R7 (5/9) -->
**Decision: Dispatch death scripts from `killCardByID()` when cause is Breached.**

**Implementation:** In `killCardByID(CardID id, CauseOfDeath cause)`, after marking card dead, check:
```cpp
if ((cause == CauseOfDeath::Breached || cause == CauseOfDeath::Blocker) &&
    card.getType().hasDeathScript()) {
    runScript(id, card.getType().getDeathScript(), ScriptTypes::DeathScript);
}
```
Add `DeathScript` to `ScriptTypes` enum.

**Note:** Currently no cards in `cardLibrary.jso` have deathScript (verified by grep). The infrastructure must exist for correctness even if unused.

### Decision 2.4: Resonator/Annihilator Processing

**AS3 (State.as:2770-3000):** During swoosh, after beginOwnTurnScripts:
1. Build dictionary of annihilators (units with `resonate` property) → target card name
2. Build dictionary of annihilatees (units matching target name)
3. For each match: add Attack resource equal to count
4. Similar for `goldResonate` → add Gold resource

**Decision: Port directly.** Add resonator processing as a new private method `processResonators(PlayerID player)` called at end of `beginTurn()`.

**Reference:** `CardType::getResonate()` and `CardType::getGoldResonate()` already parsed in `CardTypeInfo.cpp`. 4 cards have `resonate`, 1 has `goldResonate` in `cardLibrary.jso`.

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
2. Add stagnation constants and `ProgressEvent` enum to `Constants.h` (as above)
3. Add `DeathScript` to `ScriptTypes` enum
4. Add private method declarations to `GameState.h`:
   - `processResonators(PlayerID player)`
   - `resetTurnProgress(int level)`
   - `resetOppProgress(int level)`
   - `resetColorProgress(PlayerID player, int level)`
   - `reportProgress(ProgressEvent event)`
   - `incrementStagnation()`
<!-- CHANGED: isStagnated is now private, not public — R1, R3, R5, R7, R8 (5/9) -->
5. Add PRIVATE `checkStagnation()` method (used inside `calculateGameOver()`, NOT public API)
6. Verify `Card.as:320` `deathScript` property exists in `CardType` — check `source/engine/CardType.h` for `getDeathScript()`
<!-- CHANGED: Added isIsomorphic stagnation update — R5, confirmed by codebase -->
7. Update `isIsomorphic()` and `isPlayerIsomorphic()` to compare `m_noProgress` arrays — transposition table correctness requires this

**Verification:**
- Clean compile with scaffolding (no functional changes yet)
- All existing tests pass
- `checkStagnation()` returns false (counters initialized to 0)
- isIsomorphic now compares stagnation counters

<!-- APPLIED: Optional #3 — CardData integrity assertions — R8 -->
### Task 2.9: CardData Integrity Assertions

**What to do:**
Add debug assertions (using `PRISMATA_ASSERT`) that verify CardData consistency after every `doAction()` call:
1. Total card count matches sum of per-player card counts
2. No card has an invalid player owner (must be Player_One or Player_Two)
3. No card appears in both alive and dead lists simultaneously
4. Card IDs are unique (no duplicates in any player's card list)

**Implementation:** Add a private `validateCardIntegrity()` method. Call it at the end of `doAction()` inside `#ifdef _DEBUG`. Zero cost in Release builds.

**Verification:**
- Run 10 games in Debug mode — no assertion fires
- Intentionally corrupt a card's player ID — assertion fires immediately

<!-- APPLIED: Optional #8 — Determinism contract — R6 -->
### Task 2.10: Determinism Contract

**What to do:**
Document which operations are order-dependent and add assertions:
1. **Card iteration order:** `getCardIDs()` returns cards in insertion order. The port must preserve this — AS3 iterates `copyOfInstIds` which is insertion-ordered. Add a comment to `CardData::getCardIDs()` documenting this contract.
2. **Script execution order:** Scripts that create units append to the card list. Later cards in the same swoosh pass see the pre-swoosh state of these new cards. Document this in the beginTurn loop.
3. **Stagnation event order:** Multiple stagnation events in the same action are processed left-to-right. Only the HIGHEST level matters (reset is monotonic). Document in `reportProgress()`.

**Implementation:** Add comments and, where feasible, `PRISMATA_ASSERT` checks:
```cpp
// Assert card IDs are monotonically increasing (insertion order preserved)
PRISMATA_ASSERT(cardIDs.empty() || cardIDs.back() < newCardID);
```

**Verification:**
- Existing tests pass (assertions don't fire)
- Comments added to CardData::getCardIDs(), GameState::beginTurn(), reportProgress()

### Phase 2 Verification Checklist
- [ ] Architecture decisions documented in code comments
- [ ] Stagnation fields added to GameState.h
- [ ] Constants and ProgressEvent enum added to Constants.h
- [ ] ScriptTypes::DeathScript added
- [ ] New private method declarations added to GameState.h
- [ ] isIsomorphic updated for stagnation counters
- [ ] CardData integrity assertions added (Debug-only)
- [ ] Determinism contract documented with assertions
- [ ] Clean compile (Debug + Release)
- [ ] Existing tests pass (unchanged behavior)

---

<!-- CHANGED: SWAPPED Phase 3 and Phase 4 — ALL 9 REVIEWERS agreed swoosh before moves -->
## Phase 3: Core Port — Swoosh/beginTurn Rewrite

**Goal:** Port the swoosh (turn transition) to single-pass architecture matching AS3. This phase was moved BEFORE move processing because: (1) swoosh is self-contained with clear AS3 mapping, (2) provides immediate replay validation signal, (3) move processing depends on correct turn boundary state.

### Task 3.1: Rewrite beginTurn() to Single-Pass

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
            reportProgress(ProgressEvent::BuildTimeTicked);
        } else if (card.isDelayed()) {
            card.tickDelay();
            reportProgress(ProgressEvent::DelayTicked);
        } else if (card.getCurrentLifespan() > 0) {
            card.tickLifespan();
            if (card.getCurrentLifespan() == 0) {
                killCardByID(cardID, CauseOfDeath::Lifespan);
                reportProgress(ProgressEvent::OppLifespanTicked);  // Resets OPPONENT
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
        if (card.applyHealthRegen()) {
            // If unit has healthUsed > 0 AND healed, track for stagnation
            if (card.getType().getHealthUsed() > 0) {
                reportProgress(ProgressEvent::HPHealedOnPayHP);
            }
        }

        // f. Apply charge regen (AS3:2726-2738)
        if (card.applyChargeRegen()) {
            reportProgress(ProgressEvent::ChargeRecharged);
        }

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

    // 5. Process resonators (NEW — see Task 3.2)
    processResonators(player);

    // 6. Increment stagnation counters
    incrementStagnation();

    // 7. Remove killed cards
    m_cards.removeKilledCards();
}
```

**Key difference from current C++:** Scripts run INLINE per-card, not in a separate pass. This means when card N's script runs, cards 0..N-1 have been processed but cards N+1..end are still in pre-swoosh state. This exactly matches AS3.

<!-- CHANGED: Added commit guidance — R5 -->
**Commit:** `git commit -m "Port beginTurn to single-pass swoosh (AS3 State.as:2582-3045)"` — this is the single most impactful change.

### Task 3.2: Implement Resonator Processing

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

**Reference:** `CardType::getResonate()` and `CardType::getGoldResonate()` already parsed in `CardTypeInfo.cpp` (lines 40-104). 4 cards have resonate, 1 has goldResonate.

### Task 3.3: Update Card::beginTurn() to Simpler Reset

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

### Task 3.4: Implement Simple Stagnation Events in Swoosh

Stagnation events that fire during swoosh (already embedded in Task 3.1 pseudocode):

| Event | ProgressEvent | Reset Target | Where |
|---|---|---|---|
| BuildTime ticked | `BuildTimeTicked` | Turn player | Construction tick |
| Delay ticked | `DelayTicked` | Turn player | Delay tick |
| Opp lifespan ticked | `OppLifespanTicked` | Opponent | Lifespan death |
| HP healed on pay-HP unit | `HPHealedOnPayHP` | Turn player | Health regen |
| Charge recharged | `ChargeRecharged` | Turn player | Charge regen |

### Phase 3 Verification Checklist
- [ ] Single-pass swoosh matches AS3 card processing order
- [ ] Resonator processing produces correct Attack/Gold resources
- [ ] Card::beginTurn() simplified, no duplicate logic
- [ ] Stagnation counters increment correctly
- [ ] Simple stagnation resets fire at correct trigger points
- [ ] Clean compile (Debug + Release)
<!-- CHANGED: Valley-of-despair policy — replay may temporarily regress — ALL 9 REVIEWERS -->
- [ ] Replay oracle: categorize changes — newly passing replays are wins, newly failing replays must be checked against AS3 (if AS3-correct, this is EXPECTED not a regression)
- [ ] State-hash differential: run on 100 replays, document all divergence points vs old engine
- [ ] Performance: <10% regression vs baseline

<!-- CHANGED: Added per-phase diff report — R7 -->
### Phase 3 Diff Report
After completing this phase, document:
1. Git diff stats (files changed, lines added/removed)
2. Replay oracle delta: +X newly passing, -Y newly failing, categorized
3. State-hash differential results on sample replays
4. Commit hash for phase boundary

---

## Phase 4: Core Port — Move Processing

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
| `MOVE_UNASSIGN` | `UNDO_USE_ABILITY` | Keep C++ version but update for new cost timing |
| `MOVE_UNBREACH_OR_UNOVERKILL` | `UNDO_BREACH` | Skip — keep C++ version |
| `MOVE_UNWIPEOUT` | N/A | Skip — C++ uses state copy |
| `MOVE_UNMELEE` | N/A | Skip — C++ uses state copy |
| `MOVE_UNDEFEND` | N/A | Skip — C++ uses state copy |

### Task 4.1: Port BUY Action

**AS3 Reference:** State.as:1625-1648 (MOVE_BUY)
**C++ Location:** GameState.cpp:565-574

**What to change:**
1. Verify buy cost subtraction matches AS3 `payCost()` (State.as cost handling)
2. Verify buy-sac card selection matches AS3 `wouldBeSacced()` sort order (State.as:1242-1280)
3. Add stagnation reset: `reportProgress(ProgressEvent::CardBought)` after successful buy
4. Run buy script with AS3 timing (currently correct — runs after purchase)

**Commit:** `git commit -m "Port BUY action + stagnation tracking"`

**Verification:** Replay oracle — BUY actions should not regress.

### Task 4.2: Port USE_ABILITY Action (Critical — Timing Change)

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

<!-- CHANGED: Added UNDO_USE_ABILITY update requirement — R5, R8, R9 (3/9), confirmed as live code path -->
### Task 4.2b: Update UNDO_USE_ABILITY Path

**C++ Location:** GameState.cpp:747-793

**What to change:** Since ability costs are now deducted BEFORE script execution (in `doAction`), the undo path (`UNDO_USE_ABILITY`) must RESTORE costs in the reverse order:
1. Run `runScriptUndo()` to reverse script effects
2. THEN restore health/charge costs (new — currently done inside `card.undoUseAbility()`)

This mirrors the change in Task 4.2: if `doAction` deducts costs then runs script, `UNDO` must undo script then restore costs.

**Commit:** `git commit -m "Port USE_ABILITY cost timing + update undo path"`

**Verification:** Run replay oracle — watch for USE_ABILITY regressions (this is the #1 failure category at 40.7%).

### Task 4.3: Port SNIPE Action (Critical — Timing Change)

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

**Commit:** `git commit -m "Port SNIPE timing: script before kill (AS3 audit B4)"`

**Verification:** Find replays with snipe units (Tarsier variants, Apollo, Lancetooth) and verify no regressions.

### Task 4.4: Port CHILL Action

**AS3 Reference:** State.as:1484-1510 (chill within MOVE_ASSIGN)
**C++ Location:** GameState.cpp:686-702

**What to change:**
1. Match AS3 chill application: `target.disruptDamage += card.targetAmount`
2. AS3 checks if chill kills: `if disruptDamage >= damageItCanTake+damage → blocking=false`
3. Verify C++ `applyChill()` matches this logic
4. Verify script runs BEFORE applying chill (matching Decision 2.6 pattern)

**Commit:** `git commit -m "Port CHILL action to match AS3 semantics"`

**Verification:** Chill-heavy replays (Shiver Yeti, Frostbite, Cryo Ray games).

### Task 4.5: Port ASSIGN_BLOCKER (Defense Phase Blocking)

**AS3 Reference:** State.as:1712-1778 (MOVE_DEFEND)
**C++ Location:** GameState.cpp:638-644

**What to verify (mostly correct already):**
1. `blockWithCard()` (GameState.cpp:1564-1580) reduces enemy attack by `min(attack, health)`
2. Card takes damage, killed if lethal
3. **Confirm no status reset before defense** (audit fix already applied)
4. Add stagnation tracking: when own unit blocks, this constitutes "progress" for the attacker

**Commit:** `git commit -m "Verify ASSIGN_BLOCKER matches AS3"`

**Verification:** Defense-heavy replays; verify blocker eligibility matches AS3 `couldDefendThisTurn` (StateHelper.as).

### Task 4.6: Port ASSIGN_BREACH

**AS3 Reference:** State.as:1779-1854 (MOVE_BREACH_OR_OVERKILL)
**C++ Location:** GameState.cpp:646-655

**What to change:**
1. Death script execution now handled by `killCardByID()` (Decision 2.3) — no per-caller changes needed
2. AS3 runs `runScriptForward(card.deathScript)` on breach kill (State.as:1805-1807)
3. Verify `killCardByID` is called with `CauseOfDeath::Breached` to trigger death script dispatch

**Commit:** `git commit -m "Verify ASSIGN_BREACH + death script dispatch"`

**Verification:** Check `cardLibrary.jso` for any units with `deathScript`. If none exist, add a synthetic test.

### Task 4.7: Port WIPEOUT

**AS3 Reference:** State.as:1855-1876 (MOVE_WIPEOUT)
**C++ Location:** GameState.cpp:704-707

**What to verify:**
1. Break statement is present (already fixed, commit d44740e)
2. Wipeout damage to all blockers happens in `blockWithAllBlockers()` (called from `endPhase(Action)`)
3. Death scripts now handled by `killCardByID()` — no per-caller changes needed
4. AS3 sets `glassBroken = true` — verify C++ enters `Phases::Breach` equivalently

**Commit:** `git commit -m "Verify WIPEOUT + death script via killCardByID"`

**Verification:** Replays with wipeout scenarios (high-attack games).

### Task 4.8: Port endPhase() — Confirm Phase Turn Boundary

**AS3 Reference:** State.as:1911-1970 (MOVE_ENTER_CONFIRM + MOVE_COMMIT)
**C++ Location:** GameState.cpp:1404-1433

**What to change:**
1. **Add stagnation increment:** Call `incrementStagnation()` at turn boundary
2. **Add stagnation win check:** In `calculateGameOver()`, call private `checkStagnation()` for both players
3. Match AS3's stagnation check timing: happens during ENTER_CONFIRM (State.as:1911-1951)

**New stagnation check (PRIVATE) in calculateGameOver():**
```cpp
bool GameState::checkStagnation() const {
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
    return false;
}
```

**Commit:** `git commit -m "Port endPhase stagnation increment + win check"`

**Verification:** Create synthetic game states that trigger stagnation at each level.

### Task 4.9: Port isLegal()

**AS3 Reference:** StateHelper.as computed properties determine legality; State.as processMove validates
**C++ Location:** GameState.cpp:189-545

**What to change:**
1. **Add missing Condition types** (audit finding B8): `IS_BLOCKING`, `NAME_IN`, `IS_ABC`, `IS_ENGINEER_TEMP`
2. These are in `Card::meetsCondition()` — check `source/engine/Card.cpp` for the condition switch
3. Reference: `C.as:52-64` for condition constant definitions

**Commit:** `git commit -m "Add 4 missing Condition types (IS_BLOCKING, NAME_IN, IS_ABC, IS_ENGINEER_TEMP)"`

**Verification:** Find replays using units with target conditions (Kinetic Driver, Centurion).

### Phase 4 Verification Checklist
- [ ] BUY action matches AS3 (stagnation reset added)
- [ ] USE_ABILITY cost timing: health/charge BEFORE script
- [ ] UNDO_USE_ABILITY updated to mirror new cost timing
- [ ] SNIPE kill timing: script BEFORE kill
- [ ] CHILL application matches AS3 formula
- [ ] ASSIGN_BLOCKER: no status reset, correct damage
- [ ] ASSIGN_BREACH: death script via killCardByID
- [ ] WIPEOUT: death scripts via killCardByID
- [ ] Turn boundary: stagnation increment + win check
- [ ] isLegal: 4 missing Condition types added
- [ ] Clean compile (Debug + Release)
<!-- CHANGED: Valley-of-despair policy applied here too -->
- [ ] Replay oracle: categorize all changes vs baseline — AS3-correct regressions are expected
- [ ] State-hash differential: document divergence points
- [ ] Legality oracle: no regressions on 10,000 states

### Phase 4 Diff Report
After completing this phase, document:
1. Git diff stats
2. Replay oracle delta with AS3-correctness categorization
3. State-hash differential results
4. Commit hash for phase boundary

---

## Phase 5: New Systems & Complex Stagnation

**Goal:** Add remaining AS3 systems and complete stagnation port.

<!-- CHANGED: Restructured Phase 5 — deferred spell/mana rot, added complex stagnation — R2, R3, R5, R7, R8, R9 -->

### Task 5.1: Complex Stagnation Events (ENTER_CONFIRM)

**AS3 Reference:** State.as:1895-1954 (MOVE_ENTER_CONFIRM stagnation logic)

**What to port:** The complex if-else chain that fires during ENTER_CONFIRM:
```
1. If attack > oppDefense AND attack >= maxOppDefenderHealth → resetTurn(LEVEL_OPP_UNIT_COLLECTED)
2. Else if unitsCreated or unitsBought → resetTurn(LEVEL_CARD_BOUGHT)
3. Else if partiallyDamagedInst with damage > healthGained → resetTurn(LEVEL_DAMAGE_MORE_THAN_HEALING)
4. Else if attack > oppDefense AND attack >= damageReqdToMakeProgressOnFragileBlocker → resetTurn(LEVEL_DAMAGE_MORE_THAN_HEALING)
5. Else if totalProducedThisTurn.money > 0 → resetTurn(LEVEL_MONEY_STORED)
6. THEN (separate if) gas storage checks for specific units (Cluster Bolt, Gauss Charge, Zemora, Gaussite Symbiote)
```

**Dependencies:** This logic requires computed properties from AS3 StateHelper:
- `oppDefense` — total defense available to opponent
- `maxOppDefenderHealth` — max HP of any opponent blocker
- `partiallyDamagedInst` — any opponent card that has taken non-lethal damage
- `totalProducedThisTurn` — resources produced this turn
- `damageReqdToMakeProgressOnFragileBlocker` — computed from opponent's fragile blocker stats

**Implementation options:**
1. **Port required StateHelper functions inline** — compute these values on-demand in `endPhase(Action)`. Avoids a full StateHelper port.
2. **Track "units created/bought this turn" as a turn-scoped counter** — reset in beginTurn, increment in BUY/runScript-create.
3. **Track "total produced this turn" via resource delta** — snapshot resources at turn start, diff at ENTER_CONFIRM.

**Note:** This is the hardest stagnation sub-task because it has StateHelper dependencies. If it proves too complex, the simple stagnation events (already ported in Phase 3/4) still provide meaningful improvement over the flat 200-turn limit.

### Task 5.2: Missing Condition Types

**AS3 Reference:** C.as:52-64
**C++ Location:** `Card::meetsCondition()` in Card.cpp

**What to add:**
1. `IS_BLOCKING` — card is currently blocking (`canBlock() && status == Default`)
2. `NAME_IN` — card name is in a list of names
3. `IS_ABC` — card meets ABC criteria (check AS3 for semantics)
4. `IS_ENGINEER_TEMP` — special check for Engineer unit

**Verification:** Find unit abilities that use these conditions (grep `cardLibrary.jso` for `"condition"`).

### Task 5.3: Spell Collection (Deferred — Low Priority)

**AS3 Reference:** State.as `collectSpells()` — called during swoosh
**What:** Units with `cardType == "spell"` have duration-based removal. After their effect resolves, they are collected (removed from play).

**Status:** 8 units have `"spell": 1` in cardLibrary.jso. These affect a small fraction of games. Port if time permits after core validation.

### Task 5.4: Mana Rot (Deferred — Low Priority)

**AS3 Reference:** State.as `manaRots()` — called during MOVE_ENTER_CONFIRM
**What:** Certain temporary resources decay at turn boundary.

**Status:** Defer until core port is validated. Check AS3 for which resources rot and under what conditions.

<!-- CHANGED: Added serialization update task — R5, R6 -->
### Task 5.5: Update Serialization Methods

**C++ Location:** `GameState::toJSONString()` (line 2336), `GameState::getStateString()` (line 2107)

**What to change:**
1. Add `m_noProgress[2][4]` stagnation counters to `toJSONString()` output
2. Update `getStateString()` to include stagnation state (for transposition tables)
3. Ensure new state fields are included in any state comparison/hashing

**Verification:**
- JSON output includes stagnation counters
- State string includes stagnation for transposition correctness

### Phase 5 Verification Checklist
- [ ] Complex stagnation events (ENTER_CONFIRM) implemented or deferred with justification
- [ ] 4 Condition types added and tested
- [ ] Serialization updated with new fields
- [ ] Clean compile
- [ ] Replay oracle: further improvement
- [ ] Spell/mana rot: ported or documented as deferred

---

## Phase 6: Validation & Regression Testing

**Goal:** Comprehensive validation that the port is correct and nothing regressed.

### Task 6.1: Replay Oracle Comparison

**What to do:**
1. Run all 2,127 Master Bot replays through the ported engine
2. Compare against `replay_oracle_baseline.json`
3. Categorize: newly passing, still failing, newly failing (REGRESSIONS)
<!-- CHANGED: Categorize regressions by AS3-correctness — ALL 9 REVIEWERS -->
4. For each newly failing replay: check whether the old engine was correct or the new engine is correct by comparing against AS3 ground truth

**Success criteria:**
- **Target: >80% pass rate** (up from 50.4%)
- **Zero AS3-incorrect regressions** — no replay should fail because the new engine does something AS3 doesn't
- AS3-correct regressions (where the old engine was accidentally right for the wrong reason) are acceptable and expected

### Task 6.2: Feature Extraction Comparison

**What to do:**
1. Run same 1,000 positions through ported engine
2. Extract feature vectors
3. Diff against `feature_snapshot_baseline.npz`

<!-- CHANGED: Adjusted target — feature vectors WILL change — R6 -->
**Success criteria:**
- Document ALL positions with changed features
- Changes must be explainable (ability cost timing changes status before script, swoosh order changes intermediate state, stagnation counters are entirely new)
- **No NaN, Inf, or corrupted features** — structural integrity is the gate, not identity

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
- If regression >10%, profile with VS2022 Performance Profiler and identify hotspot (likely stagnation counter checks or resonator iteration)

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

<!-- CHANGED: Added NN evaluation gate — R4, R6 -->
### Task 6.7: Neural Network Evaluation Gate

**What to do:**
1. Run 100 game states through `NeuralNet::Instance()` with ported engine
2. Verify no NaN/Inf outputs (structural integrity)
3. Compare eval distribution to pre-port — values WILL differ, but should remain in [0,1] range
4. Document the magnitude of eval shift (this informs retraining priority)

**Why this matters:** The neural net trained on 722K games with the old engine's feature extraction. Changing swoosh order, ability cost timing, and status resets WILL produce different feature vectors for the same game positions. The model must be retrained, but it should still function (no crashes, no NaN) with the ported engine.

### Phase 6 Verification Checklist
- [ ] Replay oracle: >80% pass rate, 0 AS3-incorrect regressions
- [ ] Feature extraction: all changes explainable, no corruption
- [ ] Action legality: >99.5% identical
- [ ] Performance: ≤10% regression
- [ ] Tournament smoke test: no crashes, reasonable win rates
- [ ] Edge cases: stagnation, death scripts, resonators, doomed, mutual elimination
- [ ] NN evaluation: no NaN/Inf, eval distribution documented
- [ ] All results documented in `docs/port-validation-results.md`

---

<!-- CHANGED: Added Phase 7: Data Regeneration — R7, supported by R4, R6 -->
## Phase 7: Data Regeneration & Deployment

**Goal:** Regenerate self-play data with the corrected engine and retrain the neural network.

### Task 7.1: Self-Play Data Regeneration Plan

**What to do:**
1. Deploy ported engine to S3 (`aws/deploy_for_eval.sh`)
2. Configure self-play with same parameters as original 722K games (`OriginalHardestAI_1s` vs itself, 4 threads)
3. Target: 722K+ games (minimum to match current dataset size)
4. Estimate: ~4 games/min per 4-thread process → ~180K games/day with 50 cloud instances → ~4 days

**Infrastructure:** Use existing AWS EC2 spot pipeline (c5.2xlarge, $0.14/hr spot). TheWatcher handles auto-relaunch.

### Task 7.2: Neural Network Retraining

**What to do:**
1. Train on regenerated data with current best hyperparameters (256h/3L, lr=2e-5, dropout=0.20, label_smooth=0.90)
2. Use `--streaming` mode for full dataset
3. Export weights and evaluate vs `OriginalHardestAI`

**Success criteria:**
- Val accuracy ≥ 86% (matching current model)
- Tournament WR ≥ 50% vs OriginalHardestAI (matching current 51.9%)
- If WR drops >5pp, investigate feature extraction changes

### Task 7.3: Merge to Master

**What to do:**
1. Final replay oracle run (document pass rate)
2. Merge `feature/as3-faithful-port` to `master`
3. Tag `post-port-v1`
4. Update CLAUDE.md with new engine status

---

## Rollback Strategy

### If the Port Goes Wrong

At any point during Phases 3-5, if a phase introduces unrecoverable issues:

1. **Revert to phase boundary:** Each phase begins with a clean commit. `git reset --hard <phase-start-commit>`.
2. **Revert to pre-port:** `git checkout pre-port-baseline` restores the original engine.
3. **Pre-port binary is preserved:** `bin/Prismata_Testing_pre_port.exe` can regenerate data with the old (buggy but known) engine.

### If Performance Regresses >20%

1. Profile with VS2022 Performance Profiler
2. Most likely culprit: stagnation counter checks (12 events × every action) or resonator iteration
3. Optimization: batch stagnation updates per turn instead of per action
4. Fallback: disable stagnation entirely (revert to 200-turn limit) while keeping other port improvements

### If Replay Pass Rate Decreases

<!-- CHANGED: Refined rollback guidance with valley-of-despair awareness — ALL 9 REVIEWERS -->
This CAN happen during intermediate phases and is expected when correcting semantics. The key question is: **is the new engine matching AS3?**

1. Run both old and new engines on the failing replay
2. Identify the first divergent action
3. Compare against AS3 ground truth to determine which engine is correct
4. If the old engine was accidentally right: the new failure is EXPECTED (AS3-correct regression). Document and continue.
5. If the new engine diverges from AS3: this is a BUG in the port — fix it before proceeding.
6. If replay pass rate drops below 40% at any phase boundary: STOP. Investigate whether the phase introduced a systematic error. Consider reverting the phase.

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
| `helper` (StateHelper) | N/A (computed inline where needed) | Cached computed properties |
| `whiteNoProgress[4]` | `m_noProgress[0][4]` | Stagnation counters |
| `blackNoProgress[4]` | `m_noProgress[1][4]` | Stagnation counters |
| `table` (Dictionary) | `m_cards` (CardData) | Different container type |
| `turnMana` | `m_resources[getActivePlayer()]` | Player-indexed resources |
| `COLOR_WHITE/BLACK` | `Players::Player_One/Two` | Player IDs |
| `resetTurnNoProgressCounters` | `resetTurnProgress` | Resets active player |
| `resetOppNoProgressCounters` | `resetOppProgress` | Resets opponent |
| `resetColorNoProgressCounters` | `resetColorProgress` | Resets specific player |

## Appendix B: Files Modified Per Phase

| Phase | Files Created | Files Modified |
|---|---|---|
| 0.5 | `docs/as3-cpp-mapping.md` | None (documentation only) |
| 1 | `tools/replay_oracle.py`, `tools/feature_snapshot.py`, `tools/legality_oracle.py`, `tools/state_diff_oracle.py` | `GameState.h/cpp` (debugStateHash) |
| 2 | None | `GameState.h`, `GameState.cpp` (isIsomorphic, integrity assertions, determinism), `Constants.h` (scaffolding) |
| 3 | None | `GameState.cpp` (beginTurn rewrite), `Card.cpp` (simplified reset) |
| 4 | None | `GameState.cpp` (doAction port), `Card.cpp` (payAbilityCost, conditions) |
| 5 | None | `GameState.cpp` (complex stagnation, serialization), `Card.cpp` (conditions) |
| 6 | `source/testing/PortValidation.cpp`, `docs/port-validation-results.md` | None (validation only) |
| 7 | None | Deploy + retrain (no engine code changes) |

## Appendix C: Success Metrics Summary

| Metric | Pre-Port Baseline | Phase 3 Target | Phase 4 Target | Phase 6 Final Target |
|---|---|---|---|---|
| Replay pass rate | 50.4% | Categorize changes | Categorize changes | **>80%** |
| Feature match | (not measured) | N/A (deferred) | N/A (deferred) | **Explainable changes, no corruption** |
| Legal action match | (not measured) | N/A | >98% | **>99.5%** |
| Performance | ~4 games/min | No regression | No regression | **≤10% regression** |
| Structural divergences | 6+ unfixed | Script ordering fixed | 3 remaining | **0** |
| Self-play data quality | Defense bug | — | — | **Bug-free (Phase 7 regen)** |

---

## Optional Enhancements (resolved)

| # | Enhancement | Reviewer(s) | Status |
|---|---|---|---|
| 1 | **Phase 0.5: AS3 code inventory** | R7 | **APPLIED** — Added as Phase 0.5 |
| 2 | **Feature flags** | R8 | Declined — git rollback is simpler for solo dev |
| 3 | **CardData integrity assertions** | R8 | **APPLIED** — Added as Task 2.9 |
| 4 | **"Correcter but not accurate" note** | R9 | **APPLIED** — Already in plan preamble |
| 5 | **Cache miss profiling** | R4 | Declined — profile only if >10% regression materializes |
| 6 | **Staged swoosh** | R9 | Declined — differential oracle achieves same goal |
| 7 | **Debug state hash** | R5 | **APPLIED** — Added as Task 1.7 |
| 8 | **Determinism contract** | R6 | **APPLIED** — Added as Task 2.10 |
