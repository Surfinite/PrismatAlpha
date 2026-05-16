# Iterator-chain structural diff
- Local root: **LiveHardestAI_Root** (from `bin/asset/config/config.txt`)
- SWF short-blob root: **NewIterator_Root** (from `tmp_swf_extract/93_*.bin`)
- SWF full-blob root: **NewIterator_Root** (from `tmp_swf_extract/148_*.bin`)

Local `Live_*` names are normalised to compare against SWF names.
Slots are the four PPPortfolio positions: Defense, ActionAbility, ActionBuy, Breach.

## 1. Slot membership (after include resolution)
### Slot 0 — Defense
| # | Local (normalised) | SWF short | SWF full |
|---|---|---|---|
| 0 | `DefenseSolver` | `DefenseSolver` | `DefenseSolver` |

### Slot 1 — ActionAbility
| # | Local (normalised) | SWF short | SWF full |
|---|---|---|---|
| 0 | `ACAvoidBreach_CS2` | `ACAvoidBreach_ChillSolver2` | `ACAvoidBreach_ChillSolver2` | ❗
| 1 | `ACAvoidBreach_CS` | `ACAvoidBreach_ChillSolver` | `ACAvoidBreach_ChillSolver` | ❗
| 2 | `ACAvoidBreach_CSNF` | `ACAvoidBreach_ChillSolverNF` | `ACAvoidBreach_ChillSolverNF` | ❗
| 3 | `ACAvoidBreach_CSClickNC` | `ACAvoidBreach_ChillSolverClickNoChill` | `ACAvoidBreach_ChillSolverClickNoChill` | ❗
| 4 | `ACAvoidBreach_CSClickNF` | `ACAvoidBreach_ChillSolverClickNF` | `ACAvoidBreach_ChillSolverClickNF` | ❗

### Slot 2 — ActionBuy
| # | Local (normalised) | SWF short | SWF full |
|---|---|---|---|
| 0 | `BuyEconTech` | `BuyEconTech` | `BuyEconTech` |
| 1 | `BuyTechEcon` | `BuyTechEcon` | `BuyTechEcon` |
| 2 | `BCGAttack_Root` | `BCGAttack_Root` | `BCGAttack_Root` |
| 3 | `BCGWill_Root` | `BCGWill_Root` | `BCGWill_Root` |
| 4 | `BCGDef_Root` | `BCGDef_Root` | `BCGDef_Root` |

### Slot 3 — Breach
| # | Local (normalised) | SWF short | SWF full |
|---|---|---|---|
| 0 | `BreachGreedyKnapsack` | `BreachGreedyKnapsack` | `BreachGreedyKnapsack` |

## 2. Per-slot chain resolution (ActionAbility_Combination flattened)
### Slot 0 — Defense
**Branch 0** ✅  local=`DefenseSolver` | short=`DefenseSolver` | full=`DefenseSolver`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `DefenseSolver` | `DefenseSolver` | `DefenseSolver` |

### Slot 1 — ActionAbility
**Branch 0** ❗  local=`ACAvoidBreach_CS2` | short=`ACAvoidBreach_ChillSolver2` | full=`ACAvoidBreach_ChillSolver2`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `AbilityEconomyDefault` | `AbilityEconomyDefault` | `AbilityEconomyDefault` |
| 1 | `AbilityAttackDefault` | `AbilityAttackDefault` | `AbilityAttackDefault` |
| 2 | `AbilityActivateUtility` | `AbilityActivateUtility` | `AbilityActivateUtility` |
| 3 | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` |
| 4 | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` |
| 5 | `AbilityChillGKWill` | `AbilityChillGKWill` | `AbilityChillGKWill` |
| 6 | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` |
| 7 | `BuyOpeningBook2` | `BuyOpeningBook2` | `BuyOpeningBook2` |
| 8 | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` |
| 9 | `AbilityAvoidDefenseWaste` | `—` | `—` | ❗

**Branch 1** ❗  local=`ACAvoidBreach_CS` | short=`ACAvoidBreach_ChillSolver` | full=`ACAvoidBreach_ChillSolver`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `AbilityEconomyDefault` | `AbilityEconomyDefault` | `AbilityEconomyDefault` |
| 1 | `AbilityAttackDefault` | `AbilityAttackDefault` | `AbilityAttackDefault` |
| 2 | `AbilityActivateUtility` | `AbilityActivateUtility` | `AbilityActivateUtility` |
| 3 | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` |
| 4 | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` |
| 5 | `AbilityChillGKWill` | `AbilityChillGKWill` | `AbilityChillGKWill` |
| 6 | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` |
| 7 | `BuyOpeningBook` | `BuyOpeningBook` | `BuyOpeningBook` |
| 8 | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` |
| 9 | `AbilityAvoidDefenseWaste` | `—` | `—` | ❗

**Branch 2** ❗  local=`ACAvoidBreach_CSNF` | short=`ACAvoidBreach_ChillSolverNF` | full=`ACAvoidBreach_ChillSolverNF`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `AbilityEconomyDefault` | `AbilityEconomyDefault` | `AbilityEconomyDefault` |
| 1 | `AbilityAttackDefault` | `AbilityAttackDefault` | `AbilityAttackDefault` |
| 2 | `AbilityActivateUtility` | `AbilityActivateUtility` | `AbilityActivateUtility` |
| 3 | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` |
| 4 | `AbilityChillGKWill` | `AbilityChillGKWill` | `AbilityChillGKWill` |
| 5 | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` |
| 6 | `BuyOpeningBook` | `BuyOpeningBook` | `BuyOpeningBook` |
| 7 | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` |
| 8 | `AbilityAvoidDefenseWaste` | `—` | `—` | ❗

**Branch 3** ❗  local=`ACAvoidBreach_CSClickNC` | short=`ACAvoidBreach_ChillSolverClickNoChill` | full=`ACAvoidBreach_ChillSolverClickNoChill`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `AbilityEconomyDefault` | `AbilityEconomyDefault` | `AbilityEconomyDefault` |
| 1 | `AbilityAttackDefaultClick` | `AbilityAttackDefaultClick` | `AbilityAttackDefaultClick` |
| 2 | `AbilityActivateUtilityClick` | `AbilityActivateUtilityClick` | `AbilityActivateUtilityClick` |
| 3 | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` | `AbilityFrontlineGKWill` |
| 4 | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` |
| 5 | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` |
| 6 | `BuyOpeningBook` | `BuyOpeningBook` | `BuyOpeningBook` |
| 7 | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` |
| 8 | `AbilityAvoidDefenseWaste` | `—` | `—` | ❗

**Branch 4** ❗  local=`ACAvoidBreach_CSClickNF` | short=`ACAvoidBreach_ChillSolverClickNF` | full=`ACAvoidBreach_ChillSolverClickNF`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `AbilityEconomyDefault` | `AbilityEconomyDefault` | `AbilityEconomyDefault` |
| 1 | `AbilityAttackDefaultClick` | `AbilityAttackDefaultClick` | `AbilityAttackDefaultClick` |
| 2 | `AbilityActivateUtilityClick` | `AbilityActivateUtilityClick` | `AbilityActivateUtilityClick` |
| 3 | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` | `AbilitySnipeGKWill` |
| 4 | `AbilityChillGKWill` | `AbilityChillGKWill` | `AbilityChillGKWill` |
| 5 | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` | `AbilityAvoidAttackWaste` |
| 6 | `BuyOpeningBook` | `BuyOpeningBook` | `BuyOpeningBook` |
| 7 | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` | `AvoidBreach_SolveChill` |
| 8 | `AbilityAvoidDefenseWaste` | `—` | `—` | ❗

### Slot 2 — ActionBuy
**Branch 0** ✅  local=`BuyEconTech` | short=`BuyEconTech` | full=`BuyEconTech`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BuyEconTech` | `BuyEconTech` | `BuyEconTech` |

**Branch 1** ✅  local=`BuyTechEcon` | short=`BuyTechEcon` | full=`BuyTechEcon`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BuyTechEcon` | `BuyTechEcon` | `BuyTechEcon` |

**Branch 2** ✅  local=`BCGAttack_Root` | short=`BCGAttack_Root` | full=`BCGAttack_Root`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BCGAttack_Root` | `BCGAttack_Root` | `BCGAttack_Root` |

**Branch 3** ✅  local=`BCGWill_Root` | short=`BCGWill_Root` | full=`BCGWill_Root`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BCGWill_Root` | `BCGWill_Root` | `BCGWill_Root` |

**Branch 4** ✅  local=`BCGDef_Root` | short=`BCGDef_Root` | full=`BCGDef_Root`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BCGDef_Root` | `BCGDef_Root` | `BCGDef_Root` |

### Slot 3 — Breach
**Branch 0** ✅  local=`BreachGreedyKnapsack` | short=`BreachGreedyKnapsack` | full=`BreachGreedyKnapsack`

| # | Local chain | SWF short chain | SWF full chain |
|---|---|---|---|
| 0 | `BreachGreedyKnapsack` | `BreachGreedyKnapsack` | `BreachGreedyKnapsack` |

## 3. Leaf-partial definition diffs
All leaf partials reachable from any branch in any blob. Definitions are normalised (Live_ prefix stripped) before comparison.

- **17 leaves identical across all three sources**
- **2 leaves with content diff**
- **1 leaves present in only some sources**

### 3a. Leaves with content diffs (definitions normalised)

#### `BuyOpeningBook`
Local vs SWF short:
  - `openingBook`: LEFT=`"LiveOpeningBook"` vs RIGHT=`"DefaultOpeningBook"`

#### `BuyOpeningBook2`
Local vs SWF short:
  - `openingBook`: LEFT=`"LiveOpeningBook2"` vs RIGHT=`"DefaultOpeningBook2"`

### 3b. Leaves present in only some sources

| Leaf | Local | SWF short | SWF full |
|---|---|---|---|
| `AbilityAvoidDefenseWaste` | ✅ | — | — |

### 3c. Leaves identical across all three sources

- `AbilityActivateUtility`
- `AbilityActivateUtilityClick`
- `AbilityAttackDefault`
- `AbilityAttackDefaultClick`
- `AbilityAvoidAttackWaste`
- `AbilityChillGKWill`
- `AbilityEconomyDefault`
- `AbilityFrontlineGKWill`
- `AbilitySnipeGKWill`
- `AvoidBreach_SolveChill`
- `BCGAttack_Root`
- `BCGDef_Root`
- `BCGWill_Root`
- `BreachGreedyKnapsack`
- `BuyEconTech`
- `BuyTechEcon`
- `DefenseSolver`

## 4. Referenced supporting tables
### 4a. Buy Limits referenced
| Name | Local | SWF short | SWF full | Content match? |
|---|---|---|---|---|

### 4b. Filters referenced
| Name | Local | SWF short | SWF full | Content match? |
|---|---|---|---|---|
| `Ability_Filter` | ✅ | ✅ | ✅ | ❗ DIFFER |

### 4c. Opening Books referenced
| Name | Local | SWF short | SWF full | Content match? |
|---|---|---|---|---|
| `DefaultOpeningBook` | ✅ | ✅ | ✅ | ❗ DIFFER |
| `DefaultOpeningBook2` | — | ✅ | ✅ | n/a |
| `LiveOpeningBook` | ✅ | — | — | n/a |
| `LiveOpeningBook2` | ✅ | — | — | n/a |

