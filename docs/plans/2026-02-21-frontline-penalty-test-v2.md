# Frontline Penalty Isolation Test Plan (v2)
**Created:** 2026-02-21 | **Updated:** 2026-02-22 (post-review v2)
**Branch:** `test/frontline-penalty` <!-- CHANGED: dedicated branch — Reviewers R1, R3, R6 (S4) -->
**Goal:** Isolate whether the frontline penalty value (5.0 vs 100,000) affects PrismatAI_AB's win rate by running a paired tournament on AWS spot, filtering to games where the penalty can actually fire.
**Meta-review:** `docs/plans/META-REVIEW-2026-02-21-frontline-penalty-test.md`

---

## Phase 0: Facts Gathered (Do Not Re-Gather)

All signatures and line numbers verified from source. Executor must trust these and not re-research.

### Relevant C++ Signatures

**`PartialPlayer_ActionBuy_GreedyKnapsack` constructor** (`source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h:36-39`, `.cpp:7-20`):
```cpp
PartialPlayer_ActionBuy_GreedyKnapsack(
    const PlayerID playerID,
    const CardFilter & filter,
    EvaluationType (*heuristic)(const CardType, const GameState &, const PlayerID) = &Heuristics::BuyHighestCost,
    bool legacy = false);
// Constructor body line 15:
, _frontlinePenalty(legacy ? 100000.0 : 5.0)
```

**`BuyKnapsackCompare` constructor** (`source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h:56-63`):
```cpp
BuyKnapsackCompare(..., double frontlinePenalty = 5.0)
// Member: const double _frontlinePenalty (line 52)
// Used at lines 294, 299: h1 /= _frontlinePenalty  (when isFrontline() && eap >= startingHealth)
```

**`AIParameters.cpp` — how `legacy` is parsed for ActionBuy_GreedyKnapsack** (line 528):
```cpp
bool legacy = playerValue.HasMember("legacy") && playerValue["legacy"].IsBool() && playerValue["legacy"].GetBool();
```

**Float config key parsing pattern** (from UCTConstant at line 745, BlendWeight at line 750):
```cpp
if (playerValue.HasMember("FrontlinePenalty") && playerValue["FrontlinePenalty"].IsDouble())
{
    frontlinePenalty = playerValue["FrontlinePenalty"].GetDouble();
}
```

**Heuristic function mapping** (`AIParameters.cpp:537-545`):
```cpp
else if (heuristic == "BuyAttackValue")
{
    auto fn = legacy ? &Heuristics::BuyAttackValue : &Heuristics::BuyAttackValue_Improved;
    playerPtr = PPPtr(new PartialPlayer_ActionBuy_GreedyKnapsack(player, filter, fn, legacy));
}
```
**The `legacy` flag controls function selection, NOT the string.** With `legacy=false`, `"BuyAttackValue"` maps to `BuyAttackValue_Improved`. The FLLegacy config entries (which omit `"legacy":true`) correctly use the improved functions.

**`CardType::isFrontline()`** (`source/engine/CardType.h:68`):
```cpp
bool isFrontline() const;
```

**`GameState` iteration over buyable cards** (pattern from `GameState.cpp:2056-2061`):
```cpp
for (size_t cb(0); cb < state.numCardsBuyable(); ++cb)
{
    CardBuyable cardBuyable = state.getCardBuyableByIndex(cb);
    CardType type = cardBuyable.getType();
    if (type.isFrontline()) { ... }
}
```

**Tournament skip pattern** (`source/testing/Tournament.h:27`):
```cpp
bool _skipColorSwap = false;  // ← model this for _skipNonFrontline
```

<!-- CHANGED: insertion point moved to round level (before player-pair loops) — Reviewers R1, R3, R4, R5 (M3) -->
**Best insertion point for frontline skip** (`source/testing/Tournament.cpp`, inside `playRound()`, after line 98 `GameState state(stateTemplate);`, before the player-pair loops starting at line 100):
```cpp
// Line 98: GameState state(stateTemplate);  ← state has random cards here
// Line 99: ← INSERT skip check HERE (return early, skipping entire round)
// Line 100: for (size_t p1(0); p1 < ...   ← player pair loops begin
```

### Frontline Unit Reference <!-- CHANGED: added complete frontline unit list — Reviewer R3 (C6, adopted) -->

**10 buyable frontline (undefendable) units** in the dominion pool (~94 cards total):
Wild Drone, Galvani Drone, Shredder, Polywall, Thunderhead, Forcefield, Minimarshal, Arcflare, Hannibull, Summon Fusion.

**1 unbuyable frontline unit:** Behemoth (appears via other card effects only).

**No base set units are frontline** (verified: Drone, Engineer, Conduit, Blastforge, Animus, Tarsier, Rhino, Wall, Steelsplitter, Gauss Cannon, Forcefield — note: base-set Forcefield is NOT in the dominion pool; the buyable Forcefield above is the dominion version). `numCardsBuyable()` includes base set, but none of them pass the `isFrontline()` check.

<!-- CHANGED: fixed hit rate from ~83% to ~61% — All 7 reviewers (M2) -->
### Frontline Hit Rate

`setStartingState()` (`GameState.cpp:2016-2045`) draws 8 random cards from `GetDominionCardTypes()` pool of ~94 cards. With 10 buyable frontline units:

**P(≥1 frontline in 8-card set) = 1 - C(84,8)/C(94,8) ≈ 61%**

At 700 rounds per instance: ~427 rounds per instance yield valid games (2 games each = ~854 valid games/instance).

### Config Architecture — Critical Finding

`BuyComboGreedyAttack`, `BCGAttack_Root` etc. are **`ActionBuy_Combination`** — they reference BuyGK leaf entries by name:
```json
"BuyComboGreedyAttack" : { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue", "BuyGK_WillScore", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard"] }
"BCGAttack_Root" :       { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue", "BuyGK_WillScore", "BuySafeguardRoot"] }
```

Only `ActionBuy_GreedyKnapsack` entries use `_frontlinePenalty`. Confirmed affected leaf entries:
- `BuyGK_AttackValue` (line 110) — also changes fn: `BuyAttackValue` vs `BuyAttackValue_Improved`
- `BuyGK_BlockValue` (line 111) — also changes fn: `BuyBlockValue` vs `BuyBlockValue_Improved`
- `BuyGK_WillScore` (line 109) — fn always `BuyHighestCost`, only penalty changes

<!-- CHANGED: BuySafeguard contamination fully traced — All 7 reviewers (M1) -->
### BuySafeguard Contamination Chain (CRITICAL)

**`BuySafeguard`** (config.txt line 128) is an `ActionBuy_Combination` that references `BuyGK_AttackValue` directly:
```json
"BuySafeguard" : { "type":"ActionBuy_Combination", "combination": ["AbilityAvoidEconomyWaste", "BuyGK_AttackValue", "BuyEcon", "BuyTech_Elyot"] }
```

**`BuySafeguardRoot`** (line 134) references `BuySafeguard`:
```json
"BuySafeguardRoot" : { "type":"ActionBuy_Combination", "combination": ["BuySafeguard", "AbilityAvoidAttackWaste"] }
```

**`BuyEconTech`** (line 125) and **`BuyTechEcon`** (line 127) both reference `BuySafeguard`:
```json
"BuyEconTech" : { "type":"ActionBuy_Combination", "combination": ["BuyEcon", "BuyTech_Elyot", "BuySafeguard"] }
"BuyTechEcon" : { "type":"ActionBuy_Combination", "combination": ["BuyOneDrone", "BuyTech_Elyot", "BuyEcon", "BuySafeguard"] }
```

**Full reachability from `PrismatAI_AB`:**
```
PrismatAI_AB → HardIterator_Root → BuyEconTech → BuySafeguard → BuyGK_AttackValue (penalty=5.0)
PrismatAI_AB → HardIterator_Root → BuyTechEcon → BuySafeguard → BuyGK_AttackValue (penalty=5.0)
PrismatAI_AB → HardIterator_Root → BCG*_Root → BuySafeguardRoot → BuySafeguard → BuyGK_AttackValue (penalty=5.0)
PrismatAI_AB → HardIterator (include BaseIterator) → BuyEconTech → BuySafeguard → ...
PrismatAI_AB → HardIterator (include BaseIterator) → BuyTechEcon → BuySafeguard → ...
PrismatAI_AB → HardIterator (include BaseIterator) → BuyComboGreedy* → BuySafeguard → ...
```

**All four** (`BuySafeguard`, `BuySafeguardRoot`, `BuyEconTech`, `BuyTechEcon`) leak `penalty=5.0` through `BuyGK_AttackValue`. The FLLegacy chain must duplicate all four, following the Legacy chain pattern (config.txt lines 149-155).

### Existing Config Blocks to Use as Templates

**PrismatAI_AB** (config.txt line 188):
```json
"PrismatAI_AB" : { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root", "MoveIterator":"HardIterator", "Eval":"NeuralNet" }
```

**HardIterator_Root** (line 165):
```json
"HardIterator_Root" : { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], ["ACAvoidBreach_ChillSolver"], ["BuyEconTech", "BuyTechEcon", "BCGAttack_Root", "BCGWill_Root", "BCGDef_Root"], ["BreachGreedyKnapsack"] ] }
```

**HardIterator** (line 166 — uses include):
```json
"HardIterator" : { "type":"PPPortfolio", "include":"BaseIterator", "PartialPlayers": [ [], ["ACAvoidBreach_ChillSolver"], [], [] ] }
```

**BaseIterator** (line 163):
```json
"BaseIterator" : { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], [], ["BuyEconTech", "BuyTechEcon", "BuyComboGreedyAttack", "BuyComboGreedyWill", "BuyComboGreedyDefense"], ["BreachGreedyKnapsack"] ] }
```

**Tournament entry format** (example from line 293):
```json
{ "run":false, "type":"Tournament", "name":"HeuristicEval_NeuralVsOriginal", "rounds":42, "Threads":4, "UpdateIntervalSec":30, "RandomCards":8, "players":[ {"name":"PrismatAI_AB","group":1}, {"name":"OriginalHardestAI","group":2}] }
```

**launch_tournament.sh** env vars: `WEIGHTS_KEY`, `MODEL_LABEL`, `USE_SPOT`. Positional args: `INSTANCE_TYPE NUM_ROUNDS VM_MULTIPLIER NUM_INSTANCES`. Currently hardcodes tournament name `"NeuralAB_vs_Original"` in the sed patching logic.

---

## Phase 1: C++ Changes

**Goal:** Add `FrontlinePenalty` as an optional JSON config key for `ActionBuy_GreedyKnapsack` entries. Add `SkipNonFrontline` tournament option with skip counter. Build + verify.

### 1a — `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h`

**Change:** Add `double frontlinePenalty` as an explicit constructor parameter (5th param), replacing the internal ternary derivation.

Old signature (line 36-39):
```cpp
PartialPlayer_ActionBuy_GreedyKnapsack( const PlayerID playerID,
                                        const CardFilter & filter,
                                        EvaluationType (*heuristic)(...) = &Heuristics::BuyHighestCost,
                                        bool legacy = false);
```

<!-- CHANGED: constructor sentinel default -1.0 — Reviewers R1, R2, R4 (S3) -->
New signature:
```cpp
PartialPlayer_ActionBuy_GreedyKnapsack( const PlayerID playerID,
                                        const CardFilter & filter,
                                        EvaluationType (*heuristic)(...) = &Heuristics::BuyHighestCost,
                                        bool legacy = false,
                                        double frontlinePenalty = -1.0);
```

### 1b — `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp`

<!-- CHANGED: sentinel default with ternary fallback — Reviewers R1, R2, R4 (S3) -->
**Change:** Update initializer list (line 15) to use the explicit parameter with sentinel fallback:

Old:
```cpp
, _frontlinePenalty(legacy ? 100000.0 : 5.0)
```

New:
```cpp
, _frontlinePenalty(frontlinePenalty > 0 ? frontlinePenalty : (legacy ? 100000.0 : 5.0))
```

This ensures: if `FrontlinePenalty` is set in config, use it; otherwise fall back to the legacy-dependent default. The sentinel `-1.0` makes the API self-documenting — callers that don't specify a penalty get the historical behavior.

### 1c — `source/ai/AIParameters.cpp`

**Location:** Lines 526-551 (ActionBuy_GreedyKnapsack case). After parsing `legacy` (line 528), add:

```cpp
// Parse optional FrontlinePenalty override (default: sentinel -1.0 → constructor resolves via legacy flag)
double frontlinePenalty = -1.0;
if (playerValue.HasMember("FrontlinePenalty") && playerValue["FrontlinePenalty"].IsDouble())
{
    frontlinePenalty = playerValue["FrontlinePenalty"].GetDouble();
}
```

Then in **all three** `ActionBuy_GreedyKnapsack` construction calls (BuyWillScore, BuyAttackValue, BuyBlockValue cases, lines ~535, 540, 545), add `frontlinePenalty` as the 5th argument:
```cpp
playerPtr = PPPtr(new PartialPlayer_ActionBuy_GreedyKnapsack(player, filter, fn, legacy, frontlinePenalty));
```

### 1d — `source/testing/Tournament.h`

<!-- CHANGED: added skip counter — Reviewers R1, R2, R3, R6 (M4) -->
**Change:** Add `_skipNonFrontline` member and skip counter following the `_skipColorSwap` pattern (line 27):
```cpp
bool _skipColorSwap = false;
bool _skipNonFrontline = false;                     // ← add
std::atomic<size_t> _skippedNonFrontlineRounds{0};  // ← add
```

### 1e — `source/testing/Tournament.cpp`

**Part 1 — Parse from config JSON** (find where `_skipColorSwap` is parsed, add adjacent):
```cpp
if (_config.HasMember("SkipNonFrontline") && _config["SkipNonFrontline"].IsBool())
{
    _skipNonFrontline = _config["SkipNonFrontline"].GetBool();
}
```

<!-- CHANGED: skip logic moved to round level using return, with counter — Reviewers R1, R3, R4, R5 (M3, M4) -->
**Part 2 — Implement skip in `playRound()`** (after line 98 `GameState state(stateTemplate);`, BEFORE the player-pair loops at line 100):
```cpp
// Skip entire round when no frontline units exist in the random set
// (the frontline penalty can only affect buying decisions when frontline units are available)
if (_skipNonFrontline)
{
    bool hasFrontline = false;
    for (size_t cb(0); cb < state.numCardsBuyable(); ++cb)
    {
        if (state.getCardBuyableByIndex(cb).getType().isFrontline())
        {
            hasFrontline = true;
            break;
        }
    }
    if (!hasFrontline)
    {
        _skippedNonFrontlineRounds++;
        return;  // skip this entire round — no player pairs played
    }
}
```

**Part 3 — Log skip statistics** (in `run()`, after the batch loop completes, near the existing progress reporting):
```cpp
if (_skipNonFrontline)
{
    size_t skipped = _skippedNonFrontlineRounds.load();
    size_t total = skipped + (_totalGamesPlayed.load() / 2);  // approximate rounds
    fprintf(stderr, "[Tournament] SkipNonFrontline: %zu rounds skipped of ~%zu total (%.1f%% had frontline)\n",
            skipped, total, total > 0 ? 100.0 * (total - skipped) / total : 0.0);
}
```

### Phase 1 Verification

1. Build `Debug|x86` — must produce zero errors and zero new warnings
2. Quick sanity: run existing `SelfPlay_CI` tournament for 5 rounds locally — must complete without crashes
3. Grep check: `grep -n "FrontlinePenalty" source/ai/AIParameters.cpp` → must return 2 lines (HasMember check + assignment)
4. Grep check: `grep -n "_skipNonFrontline" source/testing/Tournament.cpp source/testing/Tournament.h` → must return 4+ lines (member, parse, check, counter)
5. Verify skip counter: temporarily set `"SkipNonFrontline":true` on a quick local tournament (10 rounds), confirm stderr shows skip statistics with ~39% skip rate

### Anti-Patterns
- Do NOT change the `BuyKnapsackCompare` constructor default (it's a separate path, leave at 5.0)
- Do NOT change behavior when `FrontlinePenalty` is absent from config (sentinel -1.0 falls back to `legacy ? 100000 : 5.0`)
- Do NOT skip based on base set cards — only check whether any buyable card (including base set) is frontline. The condition `isFrontline()` is the correct filter.
- Do NOT use `continue` inside the player-pair loop for the skip — use `return` to exit `playRound()` entirely, avoiding any loop-nesting ambiguity

---

## Phase 2: Config Changes

<!-- CHANGED: paired tournament design replaces two separate tournaments — Reviewers R2, R5, R6 (S1) -->
**Goal:** Add `PrismatAI_AB_FrontlineLegacy` player (neural eval + modern buy functions + frontlinePenalty=100,000), a paired 3-player tournament (primary), and a head-to-head tournament (secondary).

### Pre-work (do before writing config)

1. Read `bin/asset/config/config.txt` lines 25-45 to get the full `BuyGK_Filter` definition
2. ~~Grep for `BuySafeguard` definition~~ — **DONE in meta-review. BuySafeguard uses `BuyGK_AttackValue` directly (line 128). Four entries need FLLegacy variants.**
3. Verify the existing Legacy chain pattern (lines 145-158) matches the structure below

<!-- CHANGED: 4 additional Safeguard/EconTech entries to fix contamination — All 7 reviewers (M1) -->
### New BuyGK Leaf Entries (3 entries)

Add after the existing `BuyGK_BlockValue` line (line 111), before the legacy section:
```json
"BuyGK_AttackValue_FLLegacy" : { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyAttackValue", "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
"BuyGK_BlockValue_FLLegacy" :  { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyBlockValue",  "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
"BuyGK_WillScore_FLLegacy" :   { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyWillScore",   "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
```

**Note**: No `"legacy":true` — these use the improved heuristic functions (`BuyAttackValue_Improved`, `BuyBlockValue_Improved`) but with the legacy frontline penalty. The `legacy` flag controls function selection, NOT the penalty.

### New Safeguard & EconTech Entries (4 entries) <!-- CHANGED: fixes contamination chain — All 7 reviewers (M1) -->

These prevent `BuyGK_AttackValue` (with penalty=5.0) from leaking through the Safeguard/EconTech paths:
```json
"BuySafeguard_FLLegacy" :      { "type":"ActionBuy_Combination", "combination": ["AbilityAvoidEconomyWaste", "BuyGK_AttackValue_FLLegacy", "BuyEcon", "BuyTech_Elyot"] },
"BuySafeguardRoot_FLLegacy" :  { "type":"ActionBuy_Combination", "combination": ["BuySafeguard_FLLegacy", "AbilityAvoidAttackWaste"] },
"BuyEconTech_FLLegacy" :       { "type":"ActionBuy_Combination", "combination": ["BuyEcon", "BuyTech_Elyot", "BuySafeguard_FLLegacy"] },
"BuyTechEcon_FLLegacy" :       { "type":"ActionBuy_Combination", "combination": ["BuyOneDrone", "BuyTech_Elyot", "BuyEcon", "BuySafeguard_FLLegacy"] },
```

These mirror the existing `_Legacy` chain (config.txt lines 149-155), except:
- They reference `BuyGK_AttackValue_FLLegacy` (not `_Legacy`) — uses improved heuristic function
- They reference `BuyTech_Elyot` (not `_Legacy`) — we only isolate frontline penalty, not tech heuristic

### New Combination Entries (3 entries + 3 BCG_Root entries)

```json
"BuyComboGreedyAttack_FLLegacy" :   { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard_FLLegacy"] },
"BuyComboGreedyWill_FLLegacy" :     { "type":"ActionBuy_Combination", "combination": ["BuyGK_WillScore_FLLegacy", "BuyGK_AttackValue_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard_FLLegacy"] },
"BuyComboGreedyDefense_FLLegacy" :  { "type":"ActionBuy_Combination", "combination": ["BuyGK_BlockValue_FLLegacy", "BuyGK_AttackValue_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard_FLLegacy"] },
"BCGAttack_Root_FLLegacy" :         { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuySafeguardRoot_FLLegacy"] },
"BCGWill_Root_FLLegacy" :           { "type":"ActionBuy_Combination", "combination": ["BuyGK_WillScore_FLLegacy", "BuySafeguardRoot_FLLegacy"] },
"BCGDef_Root_FLLegacy" :            { "type":"ActionBuy_Combination", "combination": ["BuyComboGreedyDefense_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuySafeguardRoot_FLLegacy"] },
```

**All combo entries now reference `BuySafeguard_FLLegacy`** (not the base `BuySafeguard`), closing all contamination paths.

### New Iterator Entries (3 entries)

```json
"BaseIterator_FLLegacy" :         { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], [], ["BuyEconTech_FLLegacy", "BuyTechEcon_FLLegacy", "BuyComboGreedyAttack_FLLegacy", "BuyComboGreedyWill_FLLegacy", "BuyComboGreedyDefense_FLLegacy"], ["BreachGreedyKnapsack"] ] },
"HardIterator_Root_FLLegacy" :    { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], ["ACAvoidBreach_ChillSolver"], ["BuyEconTech_FLLegacy", "BuyTechEcon_FLLegacy", "BCGAttack_Root_FLLegacy", "BCGWill_Root_FLLegacy", "BCGDef_Root_FLLegacy"], ["BreachGreedyKnapsack"] ] },
"HardIterator_FLLegacy" :         { "type":"PPPortfolio", "include":"BaseIterator_FLLegacy", "PartialPlayers": [ [], ["ACAvoidBreach_ChillSolver"], [], [] ] },
```

**Note**: `BaseIterator_FLLegacy` and `HardIterator_Root_FLLegacy` now reference `BuyEconTech_FLLegacy`/`BuyTechEcon_FLLegacy` (not the base versions), preventing contamination through the iterator level. `BreachGreedyKnapsack` remains non-legacy (modern breach targeting). Only the buy heuristic frontline penalty is changed.

### New Player Entry

Add after `PrismatAI_AB_Legacy` (line 194):
```json
"PrismatAI_AB_FrontlineLegacy" : { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_FLLegacy", "MoveIterator":"HardIterator_FLLegacy", "Eval":"NeuralNet" }
```

**This player is:** Neural eval + improved buy heuristic functions + modern breach + frontlinePenalty=100,000.
**Differs from `PrismatAI_AB_Legacy`:** That uses `HardIterator_*_Legacy` which also reverts to `BuyAttackValue` (not Improved) and legacy breach.

<!-- CHANGED: single paired tournament (3 players) replaces two separate tournaments — Reviewers R2, R5, R6 (S1) -->
### New Tournament Entries

**Primary — Paired tournament** (both arms vs same opponent, same card sets per round):
```json
{ "run":false, "type":"Tournament", "name":"FrontlineTest_Paired", "rounds":84, "Threads":4, "UpdateIntervalSec":30, "RandomCards":8, "SkipNonFrontline":true, "players":[ {"name":"PrismatAI_AB","group":1}, {"name":"PrismatAI_AB_FrontlineLegacy","group":1}, {"name":"OriginalHardestAI","group":2}] }
```

Both test arms (AB and FLLegacy) are in **group 1** — they won't play each other. Each round, both play against OriginalHardestAI (group 2) with the **same random card set**. This is strictly superior to separate tournaments: paired data enables direct comparison, half the instances needed, same statistical power.

<!-- CHANGED: added head-to-head secondary tournament — Reviewers R1, R3, R4, R5, R7 (S2) -->
**Secondary — Head-to-head tournament** (direct AB vs FLLegacy):
```json
{ "run":false, "type":"Tournament", "name":"FrontlineTest_HeadToHead", "rounds":84, "Threads":4, "UpdateIntervalSec":30, "RandomCards":8, "SkipNonFrontline":true, "players":[ {"name":"PrismatAI_AB","group":1}, {"name":"PrismatAI_AB_FrontlineLegacy","group":2}] }
```

The most sensitive test for detecting the penalty's effect directly between the two AI variants.

Rounds=84 is just the local stub; launch_tournament.sh will override via config patching.

### Phase 2 Verification

1. Build `Release|x86` — must compile and link successfully
2. **Quick local run**: Add `"run":true` to `FrontlineTest_Paired` temporarily, set `"rounds":5`, launch `bin/Prismata_Testing.exe` from `bin/` directory. Confirm:
   - Tournament starts without crash
   - `tests/Tournament_FrontlineTest_Paired.html` appears in `bin/tests/`
   - HTML shows both AB and FLLegacy vs OriginalHardestAI results (never AB vs FLLegacy)
   - Skip counter prints to stderr showing ~39% skip rate
   - Some rounds complete (if all sets have no frontline units, 0 games = bug)
   - Revert `"run":false` after test
3. Repeat for `FrontlineTest_HeadToHead` with `"rounds":3` — confirm AB vs FLLegacy matchups appear
4. Grep: `grep -n "FrontlineLegacy\|FrontlineTest\|SkipNonFrontline" bin/asset/config/config.txt` → must return all new entries
5. **Contamination audit**: Trace every entry in the FLLegacy chain and verify NO reference to `BuySafeguard` (base), `BuyEconTech` (base), `BuyTechEcon` (base), or `BuyGK_AttackValue` (base). All must point to `_FLLegacy` variants.

### Config Entry Count

| Category | Count | Entries |
|---|---|---|
| BuyGK leaf | 3 | AttackValue, BlockValue, WillScore |
| Safeguard/EconTech | 4 | BuySafeguard, BuySafeguardRoot, BuyEconTech, BuyTechEcon |
| Combo/BCG | 6 | 3 BuyComboGreedy + 3 BCG_Root |
| Iterator | 3 | BaseIterator, HardIterator_Root, HardIterator |
| Player | 1 | PrismatAI_AB_FrontlineLegacy |
| Tournament | 2 | FrontlineTest_Paired, FrontlineTest_HeadToHead |
| **Total** | **19** | |

### Anti-Patterns
- Do NOT set `"legacy":true` on the new `BuyGK_*_FLLegacy` entries — that would also revert to non-Improved heuristic functions, conflating two separate changes
- Do NOT change the existing `PrismatAI_AB`, `OriginalHardestAI`, or `PrismatAI_AB_Legacy` entries
- Do NOT set `SkipNonFrontline` on any existing tournament entries
- Do NOT reference base `BuySafeguard`, `BuySafeguardRoot`, `BuyEconTech`, or `BuyTechEcon` from ANY FLLegacy combo/iterator entry — all four must use their `_FLLegacy` variants

---

## Phase 3: AWS Launch Script Update

**Goal:** Parameterize the tournament name in `launch_tournament.sh` so both test tournaments can be launched independently on separate instance fleets. Add TimeLimit patching for all test players.

**File:** `aws/launch_tournament.sh`

### Current Hardcoded Behavior (lines 129-141 approx)

The script currently:
1. Disables ALL tournaments with sed
2. Enables ONLY `"NeuralAB_vs_Original"` tournament by matching that exact name string
3. Patches `rounds` and `Threads` on that tournament's line

### Required Change 1 — Tournament Name Parameterization

Add `TOURNAMENT_NAME` env var with default:
```bash
TOURNAMENT_NAME=${TOURNAMENT_NAME:-"NeuralAB_vs_Original"}
```

Update the sed commands to use the variable instead of the hardcoded string. Find the current sed pattern that enables the tournament by name and replace the literal name with `${TOURNAMENT_NAME}`.

Example pattern change (adapt to actual sed syntax in the script):
```bash
# Before:
sed -i 's/"name":"NeuralAB_vs_Original"[^}]*"run":false/"name":"NeuralAB_vs_Original"..., "run":true/' ...

# After: use TOURNAMENT_NAME variable (exact sed syntax depends on what's in the script)
```

**Read the actual sed lines in the script first** to understand the exact pattern before modifying.

<!-- CHANGED: TimeLimit patching for new players — Code inspection (S5) -->
### Required Change 2 — TimeLimit Patching for Test Players

The existing script (lines 145-146) only patches TimeLimit for `PrismatAI_AB_Legacy` and `OriginalHardestAI`:
```powershell
$config = $config -replace '("PrismatAI_AB_Legacy"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
```

Add equivalent lines for `PrismatAI_AB` and `PrismatAI_AB_FrontlineLegacy`:
```powershell
$config = $config -replace '("PrismatAI_AB"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("PrismatAI_AB_FrontlineLegacy"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
```

Also update the debug output pattern (line 154) to include the new player names:
```powershell
if ($_ -match 'NeuralAB_vs_Original|FrontlineTest|PrismatAI_AB|OriginalHardestAI') {
```

### Phase 3 Verification

1. Dry-run test: `TOURNAMENT_NAME="FrontlineTest_Paired" bash aws/launch_tournament.sh c5.2xlarge 700 1 0` (0 instances = just show the patched config, if supported) or check the generated userdata file
2. Confirm the patched config enables the correct tournament and disables all others
3. Confirm backward compatibility: `bash aws/launch_tournament.sh` (no TOURNAMENT_NAME set) still enables `"NeuralAB_vs_Original"`
4. Verify all 3 player TimeLimits are patched in the generated userdata

---

## Phase 4: Deploy and Launch

<!-- CHANGED: rounds increased from 500 to 700, paired design halves instance count — Reviewers (M2, S1) -->
**Goal:** Rebuild, deploy to S3, and launch AWS spot fleets for both tournaments.

### 4a — Rebuild Release exe

```
MSBuild.exe visualstudio/Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86 /m
```

Confirm `bin/Prismata_Testing.exe` timestamp updated.

### 4b — Deploy to S3

```bash
bash aws/deploy_for_eval.sh
```

This uploads: `Prismata_Testing.exe`, `config.txt`, `cardLibrary.jso`, `neural_weights.bin` to `s3://prismata-selfplay-data/deploy/`.

### 4c — Launch Tournament 1: Paired (Primary)

```bash
TOURNAMENT_NAME="FrontlineTest_Paired" \
MODEL_LABEL="frontline_test_paired" \
USE_SPOT="true" \
bash aws/launch_tournament.sh c5.2xlarge 700 1 6
```

<!-- CHANGED: rounds 500→700, corrected hit rate math, paired design — Reviewers (M2, S1) -->
6 instances × 700 rounds × 2 arms × 2 games/arm × ~61% frontline hit rate ≈ **~10,248 valid games** (~5,124 per arm).

The paired design means both AB and FLLegacy play each round against the same OriginalHardestAI with the same card set, yielding perfectly paired data for direct comparison.

### 4d — Launch Tournament 2: Head-to-Head (Secondary) <!-- CHANGED: added — Reviewers R1, R3, R4, R5, R7 (S2) -->

```bash
TOURNAMENT_NAME="FrontlineTest_HeadToHead" \
MODEL_LABEL="frontline_test_h2h" \
USE_SPOT="true" \
bash aws/launch_tournament.sh c5.2xlarge 700 1 3
```

3 instances × 700 rounds × 2 games/round × ~61% ≈ **~2,562 valid games**. Most sensitive test — direct comparison between the two penalty values.

### 4e — Monitor and Collect Results

Results upload to:
- `s3://prismata-selfplay-data/eval-results/frontline_test_paired/`
- `s3://prismata-selfplay-data/eval-results/frontline_test_h2h/`

Download with:
```bash
aws s3 sync s3://prismata-selfplay-data/eval-results/ eval-results/ --region eu-north-1
```

Open `tests/Tournament_FrontlineTest_Paired.html` and `tests/Tournament_FrontlineTest_HeadToHead.html` in results folders.

### Phase 4 Verification

1. After launch: `aws ec2 describe-instances --region eu-north-1 --filters "Name=tag:Name,Values=PrismataEval*" --query 'Reservations[].Instances[].InstanceId' --output text` → should show 9 instances (6 paired + 3 h2h)
2. After ~30 min: check for result files: `aws s3 ls s3://prismata-selfplay-data/eval-results/ --region eu-north-1 | grep frontline`
3. Cost estimate: 9 × c5.2xlarge spot (~$0.14/hr) × ~2hr runtime ≈ **$2.52 total**

---

## Expected Outcomes

<!-- CHANGED: updated game counts for paired design + corrected hit rate — Reviewers (M2, S1, S2) -->
| Tournament | Instances | Expected Duration | Expected Games | Games Per Arm |
|---|---|---|---|---|
| FrontlineTest_Paired | 6 | ~2hr | ~10,248 | ~5,124 |
| FrontlineTest_HeadToHead | 3 | ~2hr | ~2,562 | ~1,281 each |

**Interpreting results:**

**Paired tournament (primary):**
- If WR(AB, 5.0 penalty) ≈ WR(FLLegacy, 100k penalty): frontline penalty value doesn't matter, confirm 5.0 is fine
- If WR(AB) > WR(FLLegacy) by >3%: penalty=5.0 is genuinely better (the AI benefits from sometimes buying frontline)
- If WR(AB) < WR(FLLegacy) by >3%: penalty=100,000 is actually better — the AI shouldn't buy frontline even when it thinks it can
- CI at ~5,100 games/arm: ±1.4% — enough to detect a 3% real effect with high confidence

**Head-to-head (secondary — most sensitive):**
- AB consistently beats FLLegacy → penalty=5.0 is better
- FLLegacy consistently beats AB → penalty=100,000 is better
- ~50/50 → penalty value has no meaningful impact

**Decision rules:**
- If both tournaments agree: high confidence in the conclusion
- If paired shows <3% difference AND head-to-head shows ~50/50: confirm penalty doesn't matter, keep 5.0
- If results disagree: investigate further (card-set composition, game length effects)

---

## Files Modified Summary

| File | Change |
|---|---|
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h` | Add `double frontlinePenalty` 5th constructor param (default -1.0 sentinel) |
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp` | Initializer uses param with sentinel fallback |
| `source/ai/AIParameters.cpp` | Parse `FrontlinePenalty` JSON key; pass to all 3 GreedyKnapsack constructor call sites |
| `source/testing/Tournament.h` | Add `bool _skipNonFrontline`, `std::atomic<size_t> _skippedNonFrontlineRounds` |
| `source/testing/Tournament.cpp` | Parse `SkipNonFrontline` from config; skip with `return` before player-pair loops; log skip statistics |
| `bin/asset/config/config.txt` | Add 19 new entries: 3 BuyGK, 4 Safeguard/EconTech, 6 Combo/BCG, 3 Iterator, 1 player, 2 tournaments |
| `aws/launch_tournament.sh` | Add `TOURNAMENT_NAME` env var; add TimeLimit patching for PrismatAI_AB and FrontlineLegacy |

---

## Optional Enhancements (pick what you want)

The following are Consider-tier items from the meta-review. Tell me which numbers to add and I'll incorporate them.

| # | Enhancement | Reviewer(s) | Effort | Recommendation |
|---|---|---|---|---|
| C1 | **Local sanity check** (50-100 rounds) before AWS launch — verify skip rate matches ~39%, both arms produce results, no crashes | R3, R5, R6 | Small | Lean yes |
| C2 | **Python result analysis script** — parse tournament HTML, compute WR + 95% CI + z-test for paired comparison | R1, R5, R6 | Medium | Lean yes |
| C3 | **EC2 max-runtime safety timeout** — add 3-hour `Stop-Computer` background job in launch script userdata to prevent runaway billing | R3 | Trivial | Lean yes |
| C4 | **RapidJSON `IsNumber()` fallback** — accept both `IsDouble()` and `IsNumber()` for `FrontlinePenalty` parsing (robustness for integer values like `100000`) | R2 | Trivial | Neutral |
| C5 | **Rollback plan documentation** — document how to revert all changes if experiment is inconclusive or causes issues | R1, R3, R5 | Trivial | Lean yes |
| C6 | ~~**List all frontline units in plan**~~ — **Already applied** (see Phase 0, "Frontline Unit Reference" section) | R3 | — | Done |
| C7 | **Penalty fire instrumentation** — add a counter for how many times the frontline penalty actually divides a heuristic value during a game (validates experiment isn't vacuous) | R2, R5 | Small | Lean yes |
| C8 | **Parameter sweep follow-up plan** — document next steps if binary test shows an effect: test {1, 5, 10, 100, 100K} penalty values | R2, R5 | Trivial (doc only) | Neutral |
