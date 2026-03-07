# Perforator Resource Bug Investigation Report
**Date:** 2026-03-06
**Status:** Investigation complete — do NOT implement fixes without review
**Branch:** gui-integration
**Checkpoint:** HEAD 48fe594

---

## Executive Summary

The C++ AI over-plans buy actions on turns where `AbilityAvoidAttackWaste` undoes a prior ability activation. The matchup runner JS engine receives a `USE_ABILITY` click (which consumes resources) but no corresponding `UNDO_USE_ABILITY` click (which would restore them), creating a resource discrepancy. The C++ search planned buys against a 4-Red state; the JS executes against a 3-Red state. The 4th Tarsier buy click fails.

There are two independent bugs. The primary bug causes the observed symptom. The secondary bug is a latent accumulation defect.

---

## Bug #1 (Primary) — Missing UNDO_USE_ABILITY Click in DoSuggest

### Location
`source/testing/Benchmarks.cpp`, lines 378–450, function `DoSuggest()`

### Root Cause Chain

**Step 1 — AbilityAttackDefault activates Perforator**

`ACDefault` (used inside `ACAvoidBreach_ChillSolver`) runs `AbilityAttackDefault` as its second sub-player. `AbilityAttackDefault` iterates all attack-giving cards not in `Ability_Filter` and calls `state.doAction(USE_ABILITY(card))` for each. Perforator (ability cost: 1 Red, gives 1 attack) is NOT in `Ability_Filter` (the filter is a blocklist: only Drake and Grenade Mech). Perforator activates. C++ state: 4R → 3R. `USE_ABILITY(Perforator)` is added to the ActionAbility move.

**Step 2 — AbilityAvoidAttackWaste undoes Perforator**

`ACDefault`'s final sub-player is `AbilityAvoidAttackWaste` (`PartialPlayer_ActionAbility_AvoidAttackWaste.cpp`). Its `getMove()` calls `getUntappableAttackers()`, which finds all cards where:
- `card.getType().getAbilityScript().getEffect().getAttackValue() > 0` (ability gives attack)
- `state.isLegal(UNDO_USE_ABILITY(card))` is true (ability was just used)

Perforator matches both conditions. Then `untapAttackingCards()` tentatively undoes Perforator and compares `state.getAttack()` against `lossDecreaseAttackThreshold` (the minimum attack needed to cause the enemy incremental loss). If undoing Perforator leaves attack at or above the threshold (i.e., its 1 attack was genuinely wasted), the undo persists. `UNDO_USE_ABILITY(Perforator)` is added to the move. C++ state: 3R → 4R.

**Step 3 — GreedyKnapsack plans 4 Tarsiers**

The ActionBuy `GreedyKnapsack` (e.g., `BuyGK_AttackValue` inside `BCGAttack_Root`) runs on the C++ state with 4R. Each Tarsier costs 4G + 1R. The buy loop calls `state.isLegal(BUY Tarsier)` which correctly gates on live `m_resources`. With 4R, 4 Tarsiers pass the gate (4R→3R→2R→1R→0R). The move gets 4× `BUY(Tarsier)`.

**Step 4 — DoSuggest silently drops the UNDO click**

`DoSuggest` iterates `move.getAction(i)` and switches on `action.getType()`. The switch has explicit cases for `BUY`, `USE_ABILITY`, `ASSIGN_FRONTLINE`, `ASSIGN_BLOCKER`, `ASSIGN_BREACH`, `SNIPE`, `CHILL`, and `END_PHASE`. All other types fall to:

```cpp
default:
    break;  // END_PHASE, WIPEOUT, UNDO_*, SELL -- skip
```

`UNDO_USE_ABILITY` hits `default`. No JS click is emitted for the Perforator deactivation.

**Step 5 — JS click processing diverges from C++ plan**

The JS engine receives this click sequence:
```
[0] inst shift clicked  drone_id       → all Drones activated, gold produced
[1] inst clicked        perforator_id  → Perforator activated, 4R→3R
    (missing: undo perforator click)
[2] card clicked        wall_idx       → Wall bought (Blue, not Red)
[3] card clicked        8              → Tarsier 1: 3R→2R  ✓
[4] card clicked        8              → Tarsier 2: 2R→1R  ✓
[5] card clicked        8              → Tarsier 3: 1R→0R  ✓
[6] card clicked        8              → Tarsier 4: needs 1R, 0R available  ✗ FAIL
```

Reported in matchup runner: `[6] FAIL: card clicked id=8`

**Note on the `abilities` output field:** `UNDO_USE_ABILITY` also falls through `default: break` in the categorization loop (lines 337–369), so it does NOT appear in `resp.abilities`. The output `[Turn] Abilities: [Perforator]` reflects only the `USE_ABILITY` entry — the undo is invisible to the caller.

### Empirical Confirmation

Tested card set: Perforator, Blood Phage, Ossified Drone, Centrifuge, Chrono Filter, Barrier, Apollo, Amporilla, Antima Comet. Failure reproduces deterministically on Turn 14. Black has 2× Animus (4R/turn income), activates Perforator (1R cost), C++ plans 4 Tarsiers with remaining 4R (after UNDO), JS executes against 3R, 4th Tarsier buy fails.

### Affected Units

Any unit satisfying both:
1. Has an attack-giving ability (`abilityScript.getEffect().getAttackValue() > 0`)
2. Is NOT in `Ability_Filter` blocklist (default: only Drake and Grenade Mech are blocked)

These units can be activated by `AbilityAttackDefault` and subsequently deactivated by `AbilityAvoidAttackWaste`. The resource-discrepancy impact is proportional to the ability's mana cost:

| Unit | Ability Cost | Attack Given | Resource Restored on UNDO |
|------|-------------|--------------|--------------------------|
| Perforator | 1 Red | 1 | 1 Red — causes buy failures |
| Steelsplitter | None | 1 | None — buy amounts unaffected |
| Hannibull | None | 1 | None — buy amounts unaffected |
| (others with attack abilityScript and no filter entry) | varies | varies | varies |

The symptom (buy failure) only manifests for units with a non-zero ability mana cost, because only those units alter the resource pool available for buys when their activation is undone. Units with free attack abilities can still cause incorrect attack-count assumptions in JS if clicked then un-clicked without the undo click, but this does not cause buy failures.

### Fix Scope

Add a case for `UNDO_USE_ABILITY` in the click-generation switch in `DoSuggest()`. The correct JS click for deactivating a unit is `inst clicked instId` (same format as activating it — the JS engine toggles the state on repeated clicks). The `instId` should be read from `preState`, same as `USE_ABILITY`.

The scope is narrow: one new `case` block in `Benchmarks.cpp`. No engine changes needed.

### Edge Cases for Fix

- The `instId` from `preState` is valid for UNDO_USE_ABILITY: the card was activated in the current turn and thus exists in the pre-move state.
- If both `USE_ABILITY` and `UNDO_USE_ABILITY` appear for the same card in a single move (activate then deactivate), both clicks should be emitted. JS correctly toggles: click 1 = activate, click 2 = deactivate. Net state matches C++ net state.
- `UNDO_USE_ABILITY` for Drones during `AvoidBreachBuyIterator` drone-untapping (the "untap tapped drones to block" mechanic) also falls through `default`. This is a separate but related case — those drone UNDO actions should also be emitted, though the resource impact is different (untapping a Drone in AvoidBreach context recovers 1 Gold, not typically a buy-blocker resource).

---

## Bug #2 (Secondary, Independent) — `_totalAbilityActivateCost` Never Reset

### Location
`source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp`, `calculateStateData()`, lines 203–212

### Description

`calculateStateData()` computes two fields used by `canAffordToActivate()`:
- `_beginTurnIncome` — projected next-turn resource income
- `_totalAbilityActivateCost` — projected total cost to activate all non-cumulative-cost abilities

`_beginTurnIncome` is correctly reset before accumulation (line 170):
```cpp
_beginTurnIncome = Resources();   // ← cleared
for (const auto & cardID : state.getCardIDs(_playerID))
{
    _beginTurnIncome.add(...);
}
```

`_totalAbilityActivateCost` is **not** reset before accumulation (lines 203–212):
```cpp
// NO _totalAbilityActivateCost = Resources() here
for (const auto & cardID : state.getCardIDs(_playerID))
{
    if (hasNonCumulativeManaCostAbility(card.getType()))
    {
        _totalAbilityActivateCost.add(card.getType().getAbilityScript().getManaCost());
    }
}
```

Each call to `getMove()` (which calls `calculateStateData()`) accumulates more ability costs into `_totalAbilityActivateCost` without clearing previous values.

### Effect

`canAffordToActivate(cardType, state)` checks:
```cpp
Resources totalAbilityCost = _totalAbilityActivateCost;
totalAbilityCost.add(abilityCost);  // add this card's cost
if (!beginTurnIncome.has(totalAbilityCost)) return false;  // can't afford all abilities + this card
```

If `_totalAbilityActivateCost` inflates across calls, cards with ability costs will be incorrectly filtered out by `shouldNotBuy()`. This is a false-negative (buys that would be correct are suppressed), not a false-positive.

Units affected: those passing `hasNonCumulativeManaCostAbility()` — ability costs involving Energy, Blue, or Red (not Gold/Green):
- Perforator (1 Red), Blood Phage (1 Blue), Electrovore (1 Energy), and any card in the deck with Energy/Blue/Red ability costs.

### Impact

The impact grows with the number of times the same GreedyKnapsack instance is called across turns. In practice, during a single `--suggest` call, the same instance is called once per child in the portfolio. Since `m_previousMoveChanged[2]` is true on the first child and false on subsequent ones for the SAME buy option (but a different GreedyKnapsack instance is used for each portfolio option), the accumulation within a single search turn is:
- Each GK instance (e.g., `BuyGK_AttackValue`) is called at most once per root `getMove()` call (since it's only the phase-2 option for `BCGAttack_Root`, which is a portfolio option, not the cached one). Actually, depending on whether the same GreedyKnapsack instance is shared or cloned for the root vs non-root iterator, accumulated costs could persist across moves in a game.

The observed symptom (buy failures) in the investigation was caused by Bug #1, not Bug #2.

### Fix Scope

Add `_totalAbilityActivateCost = Resources();` before the accumulation loop at line 203 of `calculateStateData()`. One-line fix.

---

## Configuration Context

The relevant player configuration chain for `HardestAI`:

```
HardestAI → HardIterator_Root (root) + HardIterator (non-root)

HardIterator_Root ActionAbility: ["ACAvoidBreach_ChillSolver"]
ACAvoidBreach_ChillSolver = [ACEasy, AvoidBreach_SolveChill]
ACEasy = [ACDefault, BuyOpeningBook]
ACDefault = [AbilityEconomyDefault, AbilityAttackDefault, AbilityActivateUtility,
             AbilityFrontlineGKWill, AbilitySnipeGKWill, AbilityChillGKWill,
             AbilityAvoidAttackWaste]           ← triggers Bug #1

HardIterator_Root ActionBuy (5 options):
  "BCGAttack_Root" = [BuyGK_AttackValue, BuyGK_WillScore, BuySafeguardRoot]
  "BuySafeguardRoot" = [BuySafeguard, AbilityAvoidAttackWaste]
                                               ← AbilityAvoidAttackWaste also here
  "BuySafeguard" = [AbilityAvoidEconomyWaste, BuyGK_AttackValue, BuyEcon, BuyTech_Elyot]
```

The `AbilityAvoidAttackWaste` component in `BuySafeguardRoot` (ActionBuy phase) could also add UNDO_USE_ABILITY actions after the ActionAbility phase has already run — but since `AbilityAvoidAttackWaste` only targets activated units, and Perforator was activated (then undone) in ActionAbility, it would not be re-activated at the ActionBuy stage. The primary trigger path is through ACDefault in the ActionAbility phase.

---

## Files Examined

| File | Relevance |
|------|-----------|
| `source/testing/Benchmarks.cpp:378-450` | DoSuggest click encoder — Bug #1 location |
| `source/ai/PartialPlayer_ActionAbility_AvoidAttackWaste.cpp` | Generates UNDO_USE_ABILITY actions |
| `source/ai/PartialPlayer_ActionAbility_AttackDefault.cpp` | Generates USE_ABILITY for Perforator |
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp:167-225` | Bug #2 location (calculateStateData) |
| `source/ai/PartialPlayer_ActionAbility_AvoidBreachSolver.cpp` | Confirms ACAvoidBreach wraps ACEasy |
| `source/ai/AvoidBreachBuyIterator.cpp` | Confirms AvoidBreach only handles prompt-blockers |
| `source/ai/MoveIterator_PPPortfolio.cpp` | Confirms ActionAbility phase is cached and replayed |
| `source/ai/StackAlphaBetaSearch.cpp` | Confirms root move = best child's movePerformed |
| `bin/asset/config/config.txt` | Full player configuration hierarchy |

---

## Do NOT Implement Without Review

This report covers investigation only. The two fixes are distinct and should be implemented and tested separately:
- Bug #1 fix touches `Benchmarks.cpp` (suggest protocol) — must verify JS click handling for `inst clicked` on activated unit
- Bug #2 fix touches `GreedyKnapsack.cpp` (buy planning) — must verify no regression in buy quantity heuristics
