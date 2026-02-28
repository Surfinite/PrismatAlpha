# Frontline Penalty Isolation Test Plan
**Created:** 2026-02-21
**Branch:** `feature/cpp-replay-stepper` (current) or new branch `test/frontline-penalty`
**Goal:** Isolate whether the frontline penalty value (5.0 vs 100,000) affects PrismatAI_AB's win rate by running two controlled tournaments on AWS spot, filtering to games where the penalty can actually fire.

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

**Best insertion point for frontline skip** (`source/testing/Tournament.cpp`, after line 113, before line 115):
```cpp
// Line 104-106: skip same group (continue)
// Line 110-112: skip p2 <= p1 (continue)
// Line 113: ← INSERT HERE
// Line 115: PlayerPtr w1 = AIParameters::Instance().getPlayer(...)
```

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

**Unknown**: Whether `BuySafeguard`/`BuySafeguardRoot` use `ActionBuy_GreedyKnapsack`. Executor must grep for their definition in config.txt and AIParameters.cpp before Phase 2.

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

**Goal:** Add `FrontlinePenalty` as an optional JSON config key for `ActionBuy_GreedyKnapsack` entries. Add `SkipNonFrontline` tournament option. Build + verify.

### 1a — `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h`

**Change:** Add `double frontlinePenalty` as an explicit constructor parameter (5th param), replacing the internal ternary derivation.

Old signature (line 36-39):
```cpp
PartialPlayer_ActionBuy_GreedyKnapsack( const PlayerID playerID,
                                        const CardFilter & filter,
                                        EvaluationType (*heuristic)(...) = &Heuristics::BuyHighestCost,
                                        bool legacy = false);
```

New signature:
```cpp
PartialPlayer_ActionBuy_GreedyKnapsack( const PlayerID playerID,
                                        const CardFilter & filter,
                                        EvaluationType (*heuristic)(...) = &Heuristics::BuyHighestCost,
                                        bool legacy = false,
                                        double frontlinePenalty = 5.0);
```

### 1b — `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp`

**Change:** Update initializer list (line 15) to use the explicit parameter:

Old:
```cpp
, _frontlinePenalty(legacy ? 100000.0 : 5.0)
```

New:
```cpp
, _frontlinePenalty(frontlinePenalty)
```

### 1c — `source/ai/AIParameters.cpp`

**Location:** Lines 526-551 (ActionBuy_GreedyKnapsack case). After parsing `legacy` (line 528), add:

```cpp
// Parse optional FrontlinePenalty override (default: legacy ? 100000.0 : 5.0)
double frontlinePenalty = legacy ? 100000.0 : 5.0;
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

**Change:** Add `_skipNonFrontline` member following the `_skipColorSwap` pattern (line 27):
```cpp
bool _skipColorSwap = false;
bool _skipNonFrontline = false;   // ← add this line
```

### 1e — `source/testing/Tournament.cpp`

**Part 1 — Parse from config JSON** (find where `_skipColorSwap` is parsed, add adjacent):
```cpp
if (_config.HasMember("SkipNonFrontline") && _config["SkipNonFrontline"].IsBool())
{
    _skipNonFrontline = _config["SkipNonFrontline"].GetBool();
}
```

**Part 2 — Implement skip in `playRound()`** (after line 113, before line 115):
```cpp
// Skip game pairs where no frontline units exist in the random set
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
    if (!hasFrontline) { continue; }
}
```

### Phase 1 Verification

1. Build `Debug|x86` — must produce zero errors and zero new warnings
2. Quick sanity: run existing `SelfPlay_CI` tournament for 5 rounds locally — must complete without crashes
3. Grep check: `grep -n "FrontlinePenalty" source/ai/AIParameters.cpp` → must return 2 lines (HasMember check + assignment)
4. Grep check: `grep -n "_skipNonFrontline" source/testing/Tournament.cpp source/testing/Tournament.h` → must return 3+ lines

### Anti-Patterns
- Do NOT change the `BuyKnapsackCompare` constructor default (it's a separate path, leave at 5.0)
- Do NOT change behavior when `FrontlinePenalty` is absent from config (must fall back to `legacy ? 100000 : 5.0`)
- Do NOT skip based on base set cards — only check whether any buyable card (including base set) is frontline. The condition `isFrontline()` is the correct filter.

---

## Phase 2: Config Changes

**Goal:** Add `PrismatAI_AB_FrontlineLegacy` player (neural eval + modern buy functions + frontlinePenalty=100,000) and two test tournament entries.

### Pre-work (do before writing config)

1. Read `bin/asset/config/config.txt` lines 25-45 to get the full `BuyGK_Filter` definition
2. Grep for `BuySafeguard` definition: `grep -n "BuySafeguard" bin/asset/config/config.txt` — check if it uses `ActionBuy_GreedyKnapsack`. If yes, also needs a `_FLLegacy` variant.
3. Grep for `BuySafeguardRoot` definition similarly.

### New BuyGK Leaf Entries (3 entries)

Add after the existing `BuyGK_BlockValue` line (line 111), before the legacy section:
```json
"BuyGK_AttackValue_FLLegacy" : { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyAttackValue", "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
"BuyGK_BlockValue_FLLegacy" :  { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyBlockValue",  "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
"BuyGK_WillScore_FLLegacy" :   { "type":"ActionBuy_GreedyKnapsack", "heuristic":"BuyWillScore",   "filter":"BuyGK_Filter", "FrontlinePenalty":100000.0 },
```

**Note**: No `"legacy":true` — these use the improved heuristic functions (`BuyAttackValue_Improved`, `BuyBlockValue_Improved`) but with the legacy frontline penalty.

### New Combination Entries (3 entries + 3 BCG_Root entries)

```json
"BuyComboGreedyAttack_FLLegacy" :   { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard"] },
"BuyComboGreedyWill_FLLegacy" :     { "type":"ActionBuy_Combination", "combination": ["BuyGK_WillScore_FLLegacy", "BuyGK_AttackValue_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard"] },
"BuyComboGreedyDefense_FLLegacy" :  { "type":"ActionBuy_Combination", "combination": ["BuyGK_BlockValue_FLLegacy", "BuyGK_AttackValue_FLLegacy", "BuyEconLimited", "BuyTech_Elyot", "BuySafeguard"] },
"BCGAttack_Root_FLLegacy" :         { "type":"ActionBuy_Combination", "combination": ["BuyGK_AttackValue_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuySafeguardRoot"] },
"BCGWill_Root_FLLegacy" :           { "type":"ActionBuy_Combination", "combination": ["BuyGK_WillScore_FLLegacy", "BuySafeguardRoot"] },
"BCGDef_Root_FLLegacy" :            { "type":"ActionBuy_Combination", "combination": ["BuyComboGreedyDefense_FLLegacy", "BuyGK_WillScore_FLLegacy", "BuySafeguardRoot"] },
```

**Adjust if BuySafeguard/BuySafeguardRoot use ActionBuy_GreedyKnapsack** (check pre-work): replace with `BuySafeguard_FLLegacy`/`BuySafeguardRoot_FLLegacy` if needed.

### New Iterator Entries (3 entries)

```json
"BaseIterator_FLLegacy" :         { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], [], ["BuyEconTech", "BuyTechEcon", "BuyComboGreedyAttack_FLLegacy", "BuyComboGreedyWill_FLLegacy", "BuyComboGreedyDefense_FLLegacy"], ["BreachGreedyKnapsack"] ] },
"HardIterator_Root_FLLegacy" :    { "type":"PPPortfolio", "PartialPlayers": [ ["DefenseSolver"], ["ACAvoidBreach_ChillSolver"], ["BuyEconTech", "BuyTechEcon", "BCGAttack_Root_FLLegacy", "BCGWill_Root_FLLegacy", "BCGDef_Root_FLLegacy"], ["BreachGreedyKnapsack"] ] },
"HardIterator_FLLegacy" :         { "type":"PPPortfolio", "include":"BaseIterator_FLLegacy", "PartialPlayers": [ [], ["ACAvoidBreach_ChillSolver"], [], [] ] },
```

**Note**: BreachGreedyKnapsack remains non-legacy (modern breach targeting). Only the buy heuristic frontline penalty is changed.

### New Player Entry

Add after `PrismatAI_AB_Legacy` (line 194):
```json
"PrismatAI_AB_FrontlineLegacy" : { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_FLLegacy", "MoveIterator":"HardIterator_FLLegacy", "Eval":"NeuralNet" }
```

**This player is:** Neural eval + improved buy heuristic functions + modern breach + frontlinePenalty=100,000.
**Differs from `PrismatAI_AB_Legacy`:** That uses `HardIterator_*_Legacy` which also reverts to `BuyAttackValue` (not Improved) and legacy breach.

### New Tournament Entries

Add after the last existing tournament entry:
```json
{ "run":false, "type":"Tournament", "name":"FrontlineTest_AB_vs_Original", "rounds":84, "Threads":4, "UpdateIntervalSec":30, "RandomCards":8, "SkipNonFrontline":true, "players":[ {"name":"PrismatAI_AB","group":1}, {"name":"OriginalHardestAI","group":2}] },
{ "run":false, "type":"Tournament", "name":"FrontlineTest_FLLegacy_vs_Original", "rounds":84, "Threads":4, "UpdateIntervalSec":30, "RandomCards":8, "SkipNonFrontline":true, "players":[ {"name":"PrismatAI_AB_FrontlineLegacy","group":1}, {"name":"OriginalHardestAI","group":2}] }
```

Rounds=84 is just the local stub; launch_tournament.sh will override this via sed.

### Phase 2 Verification

1. Build `Release|x86` — must compile and link successfully
2. **Quick local run**: Add `"run":true` to `FrontlineTest_AB_vs_Original` temporarily, set `"rounds":2`, launch `bin/Prismata_Testing.exe` from `bin/` directory. Confirm:
   - Tournament starts without crash
   - `tests/Tournament_FrontlineTest_AB_vs_Original.html` appears in `bin/tests/`
   - Some rounds complete (if all sets have no frontline units, 0 games = bug)
   - Revert `"run":false` after test
3. Grep: `grep -n "FrontlineLegacy\|FrontlineTest\|SkipNonFrontline" bin/asset/config/config.txt` → must return all new entries

### Anti-Patterns
- Do NOT set `"legacy":true` on the new `BuyGK_*_FLLegacy` entries — that would also revert to non-Improved heuristic functions, conflating two separate changes
- Do NOT change the existing `PrismatAI_AB`, `OriginalHardestAI`, or `PrismatAI_AB_Legacy` entries
- Do NOT set `SkipNonFrontline` on any existing tournament entries

---

## Phase 3: AWS Launch Script Update

**Goal:** Parameterize the tournament name in `launch_tournament.sh` so both test tournaments can be launched independently on separate instance fleets.

**File:** `aws/launch_tournament.sh`

### Current Hardcoded Behavior (lines 129-141 approx)

The script currently:
1. Disables ALL tournaments with sed
2. Enables ONLY `"NeuralAB_vs_Original"` tournament by matching that exact name string
3. Patches `rounds` and `Threads` on that tournament's line

### Required Change

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

### Phase 3 Verification

1. Dry-run test: `TOURNAMENT_NAME="FrontlineTest_AB_vs_Original" bash aws/launch_tournament.sh c5.2xlarge 500 1 0` (0 instances = just show the patched config, if supported) or check the generated userdata file
2. Confirm the patched config enables the correct tournament and disables all others
3. Confirm backward compatibility: `bash aws/launch_tournament.sh` (no TOURNAMENT_NAME set) still enables `"NeuralAB_vs_Original"`

---

## Phase 4: Deploy and Launch

**Goal:** Rebuild, deploy to S3, and launch two independent AWS spot fleets.

### 4a — Rebuild Release exe

```
MSBuild.exe visualstudio/Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86 /m
```

Confirm `bin/Prismata_Testing.exe` timestamp updated.

### 4b — Deploy to S3

```bash
bash aws/deploy_for_eval.sh
```

This uploads: `Prismata_Testing.exe`, `config.txt`, `cardLibrary.jso`, `neural_weights.bin` to `s3://$CLOUD_BUCKET/deploy/`.

### 4c — Launch Tournament 1: PrismatAI_AB vs Original

```bash
TOURNAMENT_NAME="FrontlineTest_AB_vs_Original" \
MODEL_LABEL="frontline_test_ab_vs_original" \
USE_SPOT="true" \
bash aws/launch_tournament.sh c5.2xlarge 500 1 6
```

6 instances × 500 rounds × 2 games/round × ~83% frontline hit rate ≈ **~5,000 valid games**.

### 4d — Launch Tournament 2: FrontlineLegacy vs Original

```bash
TOURNAMENT_NAME="FrontlineTest_FLLegacy_vs_Original" \
MODEL_LABEL="frontline_test_fllegacy_vs_original" \
USE_SPOT="true" \
bash aws/launch_tournament.sh c5.2xlarge 500 1 6
```

Same fleet size for directly comparable sample sizes.

### 4e — Monitor and Collect Results

Results upload to:
- `s3://$CLOUD_BUCKET/eval-results/frontline_test_ab_vs_original/`
- `s3://$CLOUD_BUCKET/eval-results/frontline_test_fllegacy_vs_original/`

Download with:
```bash
aws s3 sync s3://$CLOUD_BUCKET/eval-results/frontline_test_ab_vs_original/ eval-results/frontline_test_ab_vs_original/ --region eu-north-1
aws s3 sync s3://$CLOUD_BUCKET/eval-results/frontline_test_fllegacy_vs_original/ eval-results/frontline_test_fllegacy_vs_original/ --region eu-north-1
```

Open `tests/Tournament_FrontlineTest_AB_vs_Original.html` in each results folder.

### Phase 4 Verification

1. After launch: `aws ec2 describe-instances --region eu-north-1 --filters "Name=tag:Name,Values=PrismataEval*" --query 'Reservations[].Instances[].InstanceId' --output text` → should show 12 instances (6 per tournament)
2. After ~30 min: check for result files: `aws s3 ls s3://$CLOUD_BUCKET/eval-results/ --region eu-north-1 | grep frontline`
3. Cost estimate: 12 × c5.2xlarge spot (~$0.14/hr) × ~2hr runtime ≈ **$3.36 total**

---

## Expected Outcomes

| Tournament | Expected Duration | Expected Games |
|---|---|---|
| FrontlineTest_AB_vs_Original | ~2hr | ~5,000 |
| FrontlineTest_FLLegacy_vs_Original | ~2hr | ~5,000 |

**Interpreting results:**
- If WR(AB, 5.0 penalty) ≈ WR(FLLegacy, 100k penalty): frontline penalty value doesn't matter, confirm 5.0 is fine
- If WR(AB) > WR(FLLegacy) by >3%: penalty=5.0 is genuinely better (the AI benefits from sometimes buying frontline)
- If WR(AB) < WR(FLLegacy) by >3%: penalty=100,000 is actually better — the AI shouldn't buy frontline even when it thinks it can
- CI at 5,000 games: ±1.4% — enough to detect a 3% real effect with high confidence

---

## Files Modified Summary

| File | Change |
|---|---|
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.h` | Add `double frontlinePenalty` 5th constructor param (default 5.0) |
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp` | Initializer uses param instead of ternary |
| `source/ai/AIParameters.cpp` | Parse `FrontlinePenalty` JSON key; pass to all 3 GreedyKnapsack constructor call sites |
| `source/testing/Tournament.h` | Add `bool _skipNonFrontline = false` member |
| `source/testing/Tournament.cpp` | Parse `SkipNonFrontline` from config; skip in `playRound()` when no frontline units in set |
| `bin/asset/config/config.txt` | Add ~13 new entries: 3 BuyGK FLLegacy, 6 Combo/BCG FLLegacy, 3 Iterator FLLegacy, 1 player, 2 tournaments |
| `aws/launch_tournament.sh` | Add `TOURNAMENT_NAME` env var to parameterize which tournament to enable |
