# PrismataAI - Project Status

## What This Project Is

A C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The engine simulates game states, the AI uses Alpha-Beta search, UCT/MCTS, and a PartialPlayer phase decomposition system (Defense, ActionAbility, ActionBuy, Breach).

## How to Build and Run

Build via the Visual Studio solution in `visualstudio/`. Three executables:

- **Prismata_GUI** - SFML-based GUI for watching AI vs AI games. Select game scenarios from a dropdown (JSON state examples, randomized sets, etc.)
- **Prismata_Testing** - Runs engine unit tests
- **Prismata_Standalone** - Console-based AI tournament runner (no GUI)

There is also a Makefile for Linux/GCC builds, but the primary dev environment is Visual Studio on Windows.

**Build notes:**
- Build via the full solution file `visualstudio/Prismata.sln`, not individual `.vcxproj` files (individual projects may fail due to missing include paths)
- MSBuild path on this machine: `C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe` (found via vswhere)
- **Solution only has x86 (Win32) configs**: Debug|x86, Release|x86, Static Release|x86. There are NO x64 configs.
- Debug builds output with `_d` suffix: e.g. `bin/Prismata_Testing_d.exe`, `bin/Prismata_GUI_d.exe`
- **MSBuild from Git Bash**: Use Unix-style path and `//` for switches: `"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m`
- **WARNING**: MSBuild incremental builds may compile .obj files without relinking the exe. Always use `/t:Rebuild` (not `/t:Build`) to ensure the exe is updated.
- **File lock**: Cannot rebuild while the exe is running (LNK1104 linker error). Stop any running tournaments first.

**User preference:** Efficiency over speed — minimize API credits/usage. Maximize local PC computation (builds, tournaments, training) rather than burning context on things the machine can do autonomously.

## What We've Done

### 1. Engine Unit Database Updated to Current Balance

The engine's card library (`bin/asset/config/cardLibrary.jso`) was significantly out of date. We brought it current by:

- **Fetched 500 latest expert replays** from the Prismata replay API (AWS S3) to extract current unit definitions
- **Added 8 missing competitive units**: Arms Race, Bombarder, Innervi Field, Manticore, Mega Drone, Photonic Fibroid, Tyranno Smorcus, Urban Sentry
- **Updated balance for 41 existing units** with changes including cost adjustments, HP changes, ability redesigns, and complete reworks (Deadeye Operative, Savior, Centrifuge, Militia, Wild Drone, Vivid Drone, Trinity Drone)
- **Fixed internal name references** for newly added units (the engine uses codenames like "Tesla Tower" for "Tarsier", "Brooder" for "Blastforge", etc.)
- **Verified all 105 competitive non-base-set units** are present and match current game balance

### 2. Replay Parsing Infrastructure

Set up at `c:\libraries\prismata-replay-parser\`:

- **Cloned and built** the TypeScript replay parser from GitHub (`plampila/prismata-replay-parser`)
- **Created utility scripts** for fetching and analyzing replay data:
  - `fetch_units.js` - fetch individual replays and extract unit definitions
  - `batch_fetch_units.js` - batch process thousands of replays (10 concurrent)
  - `compare_units.js` - compare replay units vs engine units
  - `verify_coverage.js` - verify all 105 competitive units are in the engine
  - `diff_units.js` - raw field-by-field comparison
  - `smart_diff.js` - field-by-field comparison with internal name translation
  - `apply_updates.js` - programmatically apply balance updates to cardLibrary.jso

### 3. Replay Data Collected

- **31,275 raw replays** fetched from prismata-stats.web.app API (at least one player 2000+, ranked)
- **13,157 filtered expert games** (at least one player 2000+, Format 200 standard ranked, >= 20s time control, no bots)
- **251,106 training examples** from 13,037 successfully parsed replays (19.2 examples/game, 238 errors)
- **All unit costs verified consistent** — no mutated/starred/wild format contamination
- **Deck sizes**: Base+5 (449), Base+8 (2,000), Base+9 (4,480), Base+10 (4,618), Base+11 (1,610)
- **Date range**: March 2020 to September 2025
- Earlier datasets: 4,709 replays from mixed periods (`PrismataReplays.txt`), 500 latest (`latest_replays.txt`), 147 unit definitions (`replay_units.json`)

### 4. Fixed Dominion Card Whitelist

The engine has a hardcoded `dominionNames[]` whitelist in `source/engine/CardTypeData.cpp` (around line 138) that gates which non-base-set cards are loaded as buyable. It was missing 51+ cards. We added all missing buyable cards plus the 8 newly added units, and cleaned up duplicates (Vai Mauronax, Corpus, Psychosis Cannon appeared twice; Husk was redundant with House).

### 5. GUI Improvements

- **Resolution**: Changed default window size from 1600x900 to 2133x1200 in `source/gui/GUIEngine.cpp`
- **Card images**: Copied 7 missing card PNGs from the Steam install (`C:\Program Files (x86)\Steam\steamapps\common\Prismata\user\`) to `bin/asset/images/cards/` for: Arms Race, Bombarder, Innervi Field, Mega Drone, Photonic Fibroid, Tyranno Smorcus, Urban Sentry (Manticore already had one)
- **Test scenarios**: Created 4 new JSON state examples in `bin/asset/states/` and added them to `bin/asset/config/config.txt`:
  - `JSONState_Example2.txt` - "JSON Urban Sentry" - mid-game with Urban Sentries
  - `JSONState_Example3.txt` - "JSON New Units" - showcases all 8 newly added units
  - `JSONState_Example4.txt` - "JSON Fresh Start" - clean start with full buyable set including new units
  - `JSONState_Example5.txt` - "JSON Smorcus Only" - minimal set (Drone/Engineer/Academy/Tyranno Smorcus) for AI testing
- **Buy pane click fix**: Click filtering in `GUIState_Play.cpp` prevents clicking invisible cards behind TAB toggle
- **Tournament logging**: Per-turn buy action logging in `TournamentGame.cpp`

### 6. AI Bug Investigation: Tyranno Smorcus

Investigated why the Alpha-Beta AI (HardestAI) never buys Tyranno Smorcus, a known issue in the live game's masterbot. Root cause identified:

- **`canAffordToActivate()` in `PartialPlayer_ActionBuy_GreedyKnapsack.cpp`** (line 227): Forward-looking check that projects begin-turn income and blocks buying units whose ability costs exceed it
- **Buy combination ordering**: GreedyKnapsack runs BEFORE BuyTech (Elyot formula). When GreedyKnapsack evaluates Smorcus, no Animus exists yet, so red income is 0, so `canAffordToActivate` rejects it. Then BuyTech has no reason to buy Animus since nothing needs red.
- **Chicken-and-egg deadlock**: The AI won't buy Smorcus without red income, and won't buy Animus without a reason to need red
- **Confirmed experimentally**: HardestAIUCT (Monte Carlo) buys Animus + Smorcus successfully via random sampling. HardestAI (Alpha-Beta) does not. This is NOT yet fixed — just diagnosed.

### 7. Frontline Breach Ordering & Blocking Fix

Added `hasBreachableFrontlineCard()` helper and `ASSIGN_BREACH` legality check in `GameState.cpp` — non-frontline units can only be breached when no breachable frontline units remain. Frontline units are killed during the Action phase via `ASSIGN_FRONTLINE` before defense happens.

**Important rule clarification (verified against Prismata wiki)**: Frontline (undefendable) units **CAN block** if they have blocking ability (e.g., Urban Sentry is both frontline and a blocker). Being frontline means the opponent can target the unit directly during their Action phase — it does NOT prevent the unit from blocking during Defense. The `canBlock()` check relies on `defaultBlocking`/`assignedBlocking` flags only, not on frontline status. Wild Drone can't block because `defaultBlocking: 0`, not because it's frontline.

An earlier incorrect version added an `isFrontline()` check to `canBlock()` which prevented frontline blockers like Urban Sentry from blocking — this was removed after verifying rules against the Prismata fandom wiki.

**Note:** Debug `std::cerr` in `canWipeout()` (`GameState.cpp`) fires on every state where attack < defense — will spam during AI search. Should be removed.

### 8. Neural Network Integration

Integrated a C++ neural network inference engine for position evaluation, replacing/augmenting the Will Score heuristic.

**Architecture** (`source/ai/NeuralNet.h/cpp`):
- Input projection → residual blocks (Linear + LayerNorm + ReLU) → policy head + value head
- Binary weight format with magic number validation (`0x504E4554`)
- Policy output: per-unit buy count predictions
- Value output: [-1, 1] win probability via tanh
- Singleton `NeuralNet::Instance()` loaded at startup from `bin/asset/config/neural_weights.bin`
- Card type mapping: UIName → unit index (with internal name fallback)

**Integration points:**
- `Constants.h`: Added `NeuralNet` to `EvaluationMethods` enum
- `AIParameters.cpp`: Parses `"Eval": "NeuralNet"` for UCT and AlphaBeta players
- `AlphaBetaSearch.cpp`, `StackAlphaBetaSearch.cpp`: `Eval::NeuralNetEvaluation()` branch
- `UCTSearch.cpp`: Neural net leaf evaluation returns continuous [0,1] win probability (refactored `traverse()` from `PlayerID` to `double` return type)
- `Eval.cpp`: `NeuralNetEvaluation()` falls back to WillScore if net not loaded; scales [-1,1] to [-100,100]
- `AITools.cpp`, `gui/main.cpp`, `testing/main.cpp`: Load weights at startup

### 9. AI Confidence Display & Comparison

Added GUI debug panel features for evaluating AI move quality:

**Confidence value**: After the AI picks a move, the debug panel (tilde key) shows the evaluation score:
- UCT: win rate (`numWins/numVisits`) of best root node, displayed as percentage (e.g. "Win Rate: 62.3%")
- AlphaBeta: `bestMoveValues[maxDepthCompleted]`, displayed as raw eval score (e.g. "Eval: 145.2")
- Added `UCTSearch::getBestRootWinRate()` and `Player_UCT::getBestRootWinRate()`

**Comparison AI**: Automatically runs a second AI on the same pre-move position:
- If primary uses NeuralNet eval → comparison uses Playout (same search type, same time limit)
- If primary uses Playout → comparison uses WillScore
- Shows AGREE/DISAGREE indicator comparing chosen moves
- Implemented via `createComparisonPlayer()` in `GUIState_Play.cpp`
- Can also be configured via `"DebugComparisonAI"` in config.txt to use a specific named player

**Auto-play**: After selecting an AI via Enter menu, `m_autoPlay[player]` is set. When the user ends their turn (space to confirm), the opponent's AI runs automatically — no need to press Enter each turn. Both primary and comparison AIs run on the same pre-move state. Triggered from `endCurrentPhase()` → `runAutoPlay()`.

**Unit value labels**: When debug mode is on (tilde key), buyable cards show "H:4.2 N:1.8" labels:
- H = `HeuristicValues::GetInflatedTotalCostValue()` (Will Score heuristic's precomputed unit value)
- N = neural net policy output for that unit type (via `NeuralNet::getUnitIndex()`)
- Only displayed when neural net is loaded; otherwise just heuristic values shown

### 10. AI Attacker Buying Investigation (Diagnosed, Not Fixed)

Investigated why the AI doesn't buy attackers enough. Identified **3 key suppression mechanisms**:

#### Mechanism 1: Tech gold thresholds too high
**File:** `source/ai/PartialPlayer_ActionBuy_TechHeuristic.cpp` (lines 102-113)

The TechHeuristic has hardcoded gold thresholds that block tech building purchases until very high income:
- Blastforge: blocked if `!enemyHasAttacker && totalGold < 11` (needs ~11 Drones, ~turn 4-5)
- Conduit: blocked if `totalGold < 10` (needs ~10 Drones, ~turn 4)
- Animus: blocked if `!enemyHasAttacker && totalGold < 9` (needs ~9 Drones, ~turn 3)

Since ALL base-set attackers require colored resources (Tarsier needs R, Steelsplitter needs B+G, Gauss Cannon needs B+G, Rhino needs R), no attacker can be purchased until tech buildings are producing colored income. Both AIs being conservative creates a mutual feedback loop where `enemyHasAttacker` stays false, keeping thresholds high.

In real Prismata, turn 2-3 tech purchases are standard. Proposed fix: lower thresholds to 7-8G.

#### Mechanism 2: canAffordToActivate cumulative check
**File:** `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp` (lines 227-253)

Checks if `_beginTurnIncome >= _totalAbilityActivateCost + newCardAbilityCost` (cumulative across ALL owned units with colored ability costs). Becomes increasingly restrictive as you buy more attackers — e.g., with 2R income and 2 existing units each needing 1R, a 3rd is blocked (3R > 2R). Also contributes to the Smorcus chicken-and-egg deadlock (see section 6).

Proposed fix: check individual card ability cost only (does income cover THIS card's activation), not cumulative total. The search/playout evaluation handles over-commitment.

#### Mechanism 3: frontlinePenalty = 100,000
**File:** `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp` (line 275)

In `BuyKnapsackCompare`, frontline cards are divided by 100,000 in sort priority when the enemy can one-shot them. This makes any frontline unit essentially unbuyable regardless of its value. Note: Wild Drone is frontline but is NOT an attacker — it's an economy unit that produces gold. Frontline units that ARE attackers (e.g., units with `undefendable: 1` and attack > 0) would be the ones most affected by this penalty.

Proposed fix: reduce from 100,000 to ~5.0.

#### Other factors investigated (not primary causes):
- **BuyGK_Filter** (`config.txt` lines 25-41): Has `default: false`, so most cards are NOT filtered. Only blocks base-set econ/tech cards and a few specific cards. Most attackers pass through — this is NOT the main issue.
- **Buy combination ordering** (config.txt lines 122-136): GreedyKnapsack runs before TechHeuristic in most combos, but the search portfolio evaluates multiple strategies including BuyTechEcon (tech-first).
- **Playout evaluation** (Eval.cpp): Plays full game to completion (200 turn limit), returning +/-WinScore. Uses `BuyComboGreedyAttack` playout player which does buy attackers when resources allow.

### 11. Random Set Uniformity Test

Added a `RandomSetTest` benchmark type to verify that "Base + N" random unit selection is uniform across all 105 dominion cards. The test (`Benchmarks::DoRandomSetTest`) generates 100,000 game states via `setStartingState()`, counts how often each unit is selected, and reports frequency deviation.

**Result: Distribution is uniform.** All 105 units selected, max deviation 3.7% (within expected statistical noise). The RNG uses `rand() % pool.size()` with Fisher-Yates partial shuffle (`GameState.cpp:2010-2016`), seeded by `srand(time(NULL))` at startup. No bias, weighting, or filtering in the selection — pure uniform random from the `dominionCardTypes` pool.

**Files:** `source/testing/Benchmarks.cpp` (DoRandomSetTest), `source/testing/Benchmarks.h`, config.txt `RandomSetTest` benchmark entry.

### 12. Deep Dive: HardestAI Architecture

Conducted a thorough code-level analysis of HardestAI (the Masterbot) with cross-reference to Dave Churchill's published work.

#### How HardestAI Works

HardestAI is a **Stack-based Iterative Deepening Alpha-Beta** search (`Player_StackAlphaBeta`) with **Playout evaluation** at leaf nodes. Config:
```
"HardestAI": { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40,
               "RootMoveIterator":"HardIterator_Root", "MoveIterator":"HardIterator",
               "Eval":"Playout", "PlayoutPlayer":"Playout" }
```

The search tree has a **branching factor of 5** (not millions of raw moves). Each "move" is a complete player turn generated by the PPPortfolio move iterator, which combines PartialPlayers across 4 phases:

| Phase | Options | Count |
|---|---|---|
| Defense | DefenseSolver | 1 |
| ActionAbility | ACAvoidBreach_ChillSolver | 1 |
| **ActionBuy** | **BuyEconTech, BuyTechEcon, GreedyAttack, GreedyWill, GreedyDefense** | **5** |
| Breach | BreachGreedyKnapsack | 1 |

With branching 5 and iterative deepening, depth 2=25 evals, depth 3=125, depth 4=625. Each leaf is a full game playout. In 7 seconds, typically reaches depth 2-3.

#### The 5 Buy Strategies (in detail)

Each is a chain of sub-strategies spending remaining resources in order:
1. **BuyEconTech** = Drones/Engineers → Tech(Elyot) → Safeguard
2. **BuyTechEcon** = OneDrone → Tech(Elyot) → Econ → Safeguard
3. **BuyComboGreedyAttack** = GK(AttackValue) → GK(WillScore) → EconLimited → Tech → Safeguard
4. **BuyComboGreedyWill** = GK(WillScore) → GK(AttackValue) → EconLimited → Tech → Safeguard
5. **BuyComboGreedyDefense** = GK(BlockValue) → GK(AttackValue) → EconLimited → Tech → Safeguard

#### GreedyKnapsack Heuristic Functions

Three pluggable heuristics (function pointers) used by GreedyKnapsack, defined in `Heuristics.cpp`:

- **`BuyHighestCost`** (line 268): Returns `GetInflatedTotalCostValue(type)` — buy the most expensive affordable card. Used by `BuyGK_WillScore`.
- **`BuyAttackValue`** (line 339): `attackProduced / GetBuyTotalCost(type)` (attack efficiency per resource) + 10000 bonus for permanent attackers + 1000 for dominion. Falls back to BuyHighestCost if unit produces no attack.
- **`BuyBlockValue`** (line 372): `(startingHP^2) / GetBuyTotalCost(type)` — block efficiency per resource.

#### Will Score Evaluation: Cost IS the Value

The "Will Score" heuristic (named after designer Will Ma) values each unit at its **purchase cost** with resource weights:

```
ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50
CONSTRUCTION_INFLATION=1.28 per turn, PROMPT_DISCOUNT=1/1.13
```

**Computation chain** (`Heuristics.cpp`):
1. `BuyManaCost` = sum of (resource_amount × resource_weight) for all resources in buy cost
2. `BuySacCost` = sum of BuyManaCost for each sacrificed unit type
3. `BuyTotalCost` = BuyManaCost + BuySacCost
4. `InflatedTotalCostValue` = BuyTotalCost × 1.28^(constructionTime-1)

The **H: value** shown in the GUI debug panel = `GetInflatedTotalCostValue()` = this is a COST metric, not a strategic value.

**WillScoreEvaluation** (`Eval.cpp:58-67`) = sum(H: for all your units) - sum(H: for all opponent units). This is pure material counting by cost. Churchill's 2019 paper explicitly states this is "flawed, as it fails to take into account the strategic position that those units may be in."

Special cases: Forcefield hardcoded to 3.75, 1HP block-only units hardcoded to 1.875, doom cards (lifespan=1) valued at 0.

#### Neural Net GUI Labels

- **H: value** = `GetInflatedTotalCostValue(type)` — static per-unit-type, position-independent, IS the purchase cost
- **N: value** = raw policy head output from neural net — dynamic per-position, predicted buy count, NOT cost-adjusted, NOT softmaxed, can be negative
- Neither represents true strategic value of a unit

#### TechHeuristic Copy-Paste Bug (Found)

`PartialPlayer_ActionBuy_TechHeuristic.cpp` lines 69-71: `hasBlastforge` and `hasAnimus` both check `conduitType` instead of their respective types. Cascades to lines 195-197 where max tech limits are incorrectly calculated.

#### MoveIterator_PPPortfolio Details

`MoveIterator_PPPortfolio.cpp` generates moves via odometer-style iteration over the Cartesian product of partial players. Key optimization: `m_previousMoveChanged` tracks which phases changed between combinations — unchanged phases reuse previous moves without re-generating. Moves are deduplicated (line 78) since different strategy combinations can produce identical action sequences.

#### Stack Alpha-Beta Implementation

`StackAlphaBetaSearch.cpp` uses goto-based state machine (labels `AB_BEGIN`/`AB_RETURN`) instead of recursive calls to avoid stack overflow on deep searches. Supports search resumption across time-limited calls (`_resuming` flag). Alpha-beta bounds initialized at +/-1000000.

### 13. Churchill's Published Work & The 2019 ML Paper

#### Key Publications

Dave Churchill (Associate Professor, Memorial University of Newfoundland; PhD U of Alberta under Jonathan Schaeffer; co-founder Lunarch Studios):

| Paper | Year | Venue | Key Contribution |
|---|---|---|---|
| Hierarchical Portfolio Search: Prismata's Robust AI Architecture | 2015 | AIIDE (Best Student Paper) | Core HPS algorithm — portfolio of partial players + search |
| Hierarchical Portfolio Search in Prismata | 2017 | Game AI Pro 3 | Practitioner-oriented implementation guide |
| **Machine Learning State Evaluation in Prismata** | **2019** | **AIIDE Workshop** | **Learned eval beats playout eval (58.8% WR)** |
| Portfolio Greedy Search for RTS Combat | 2013 | CIG (Best Paper) | Original portfolio search concept (for StarCraft) |
| Machine Learning State Evaluation in Prismata (MSc Thesis) | 2020 | MUN | Rory Campbell's full thesis, supervised by Churchill |

Full publications list: https://davechurchill.ca/publications/

#### The 2019 ML Paper: Critical Findings

**Paper**: Campbell & Churchill, "Machine Learning State Evaluation in Prismata", AIIDE 2019 Strategy Game AI Workshop

**State representation**: `[P, U1_1...U1_n, R1_1...R1_m, U2_1...U2_n, R2_1...R2_m]`
- P = current player to move (0 or 1)
- U = unit type counts per player (one-hot encoded, max 40)
- R = **resource counts per player** (one-hot encoded, max 40)
- **Resources were included** — critical finding for our current implementation which omits them

**Network**: 2 hidden layers, 512 neurons each. Adam optimizer, lr=0.00001. Tensorflow/Keras. C++ inference via Frugally Deep (CPU only, no GPU).

**Training data**: 500,000 games of **Master Bot vs Master Bot** (self-play), ~30 turns/game = **15,090,199 training samples**. Training accuracy reached ~90%.

**Speed comparison** (evals per second, 1s time limit Alpha-Beta):
| Method | Eval/Sec |
|---|---|
| Resource (WillScore) | 8,010 |
| **Learned (Neural)** | **1,766** |
| Playout | 147 |

**Tournament results** (12,800 games, 1000ms time limit Alpha-Beta):
| Matchup | Learned AI Score |
|---|---|
| Learned vs Resource | **0.664** (66.4% win rate) |
| Learned vs Playout | **0.588** (58.8% win rate) |

**Key quotes from the paper**:
- "The original heuristic used for the Prismata AI system was similar to this - the resource values for each unit owned by each player were summed... This type of evaluation however is flawed, as it fails to take into account the strategic position that those units may be in"
- "Even though [playout] was approximately 100x slower than the formula-based evaluation... the heuristic evaluation was so much more accurate that the resulting player was stronger, winning more than 65% of games"
- "If we can learn to predict the outcome of a Master Bot game for a given state, then we can effectively replace the playout player evaluation"

**Their recommended future work** (which we are now implementing):
1. Iterate: train on games from the new stronger agent (self-play improvement loop)
2. Improve network topology and state representation
3. Learn policies for the entire game, not just evaluation functions

#### Gap Analysis: Our Implementation vs Churchill's

| Feature | Churchill 2019 | Our Current | Gap |
|---|---|---|---|
| Resources in features | Yes (one-hot) | **Yes** (clamp-divide normalized, 14 global features) | **Done** (section 20) |
| Current player in features | Yes | **Yes** (global feature index 1784) | **Done** (section 20) |
| Unit counts | Yes (one-hot) | Yes (raw counts) | Different encoding |
| Training data source | Self-play (15M samples) | Expert replays (251K) | Different but valid |
| Network architecture | 2-layer MLP (512) | 2-layer ResNet (512) | Similar |
| Output heads | Value only | Policy + Value | Ours has more |
| Policy head usage | N/A | **Computed but unused** | Must integrate |
| C++ inference | Frugally Deep (CPU) | Custom (CPU) | Ours is native |
| Proven to beat playout | **Yes (58.8%)** | **10.9% WR** (UCT cValue=2.0 broken; AB test pending) | Fix cValue / run AB test |

### 14. Pro Player Discord Discussion (Feb 2026)

Key insights from competitive Prismata players (Wonderboat, Apooche, siepu, Pikachu Memes, Spyrfyr, Liquid Egg Product) discussing AI improvement:

**Apooche** (understands Masterbot internals):
- Confirms: "Masterbot breaks the turn down into 4 different parts, considers a few different simple algorithms for each, and does Monte Carlo Tree Search over different turns"
- Confirms cost-based evaluation: "It evaluates board states based on total cost of units on board. Cost of units obviously isn't correct, it's just simpler and more robust to implement."
- Key insight: "The first big thing to improve is the set of algorithms it considers for each sub-turn. There are some good turns that it can never even consider because the limited algorithms can't produce them."
- Key insight: "Dave noted that letting it search deeper doesn't really do anything to improve it because of these limitations."
- Recommends: "The other thing to do now, 12 years later, is to use an Alpha-Go type of approach"

**Wonderboat**: Masterbot was "great" but designed for generality (wouldn't break with new units). A tighter bot knowing the game won't change could be stronger.

**siepu**: Current masterbot has "simple misevaluations and rigid refusing to gambit ever"

**Pikachu Memes**: "as long as you don't float resources, absorb with the biggest absorber, and go for the strongest attacker with the econ available given the absorb, you reach at least 1700 without problems"

**Spyrfyr**: Suggests opening book approach — rank units by dominance, create opening books for base+2 sets.

**Estimated Masterbot rating**: ~1200 ELO according to community estimates. Expert humans are 2000+.

### 15. Planned Implementation: Heuristic Fixes + Neural Net Improvement

#### Track A: Heuristic Bug Fixes (DONE + Legacy Mode)

All 5 fixes applied. Original behavior preserved via `"legacy": true` config flag (see section 17):

1. **Fix TechHeuristic copy-paste bug** — `hasBlastforge`/`hasAnimus` now check correct types (always active, even in legacy mode — was a genuine bug)
2. **Lower tech gold thresholds** — 11/10/9 → 8/7/6 (configurable: legacy mode uses original thresholds)
3. **Fix canAffordToActivate** — cumulative → individual check (configurable: legacy mode uses cumulative)
4. **Reduce frontline penalty** — 100,000 → 5.0 (configurable: legacy mode uses 100,000)
5. **Debug stderr** — removed

#### Track B: Neural Net Feature Enhancement

1. **Add missing features** to both Python (`training/vectorize.py`) and C++ (`source/ai/NeuralNet.cpp:extractFeatures()`):
   - Turn number (normalized)
   - Active player ID
   - Per-player resource income rates (gold, red, blue, green, energy) — estimated from unit ownership
   - New state_dim: 1278 → 1290 (12 new features)

2. **Retrain supervised model** with loss weighting: 1.5x value + 0.5x policy (prioritize value accuracy per Churchill's approach)

3. **Validate**: Run tournament PrismatAlpha_UCT vs HardestAI to verify learned eval beats playout (targeting Churchill's 58.8% benchmark)

4. **(Stretch) Policy-guided UCT**: Add PUCT formula using policy priors for move ordering in `UCTSearch.cpp:UCTNodeSelect()`

#### Execution Order

Track A first (immediate gains), then Track B (retrain with better features). Separate effort: collect all 2000+ rated games from prismata-stats for expanded training corpus.

### 16. Training Data Pipeline Overhaul

Rewrote the replay fetch/filter/extraction pipeline to maximize training corpus and capture comprehensive game state.

#### Expanded Replay Collection (At Least One Player 2000+)

Previously required **both** players to be 2000+ rated (7,205 games). Changed to require **at least one** player to be 2000+, dramatically expanding the corpus. Only the 2000+ player's turns are used for training — the lower-rated opponent's turns are discarded.

**Changes:**
- `fetch_expert_replays.js`: Removed `rating_strict: 'on'` from API params — API now returns games where at least one player meets the 2000 threshold
- `filter_expert_replays.js`: Changed `r1 >= 2000 && r2 >= 2000` to `r1 >= 2000 || r2 >= 2000`
- `extract_training_data.js`: Player ratings loaded from `expert_2000_replays.json`, each example filtered by active player's rating before emission

#### Comprehensive State Capture

Rewrote `extractTrainingData()` to capture everything the replay parser exposes, so replays never need to be re-fetched from S3.

**State (per training example):**
- `p0_resources`, `p1_resources`: `{ gold, blue, red, green, energy, attack }` via `state.resources[player]`
- `p0_units`, `p1_units`: **per-instance** unit arrays (not aggregated counts), each with: `name, toughness, toughnessMax, delay, lifespan, charge, disruption, abilityUsed, blocking, building, frozen, frontline, defaultBlocking, fragile`
- `p0_attack`, `p1_attack`: total attack values
- `supply`: per-unit-type remaining supply per player
- `card_set`: buyable unit type names
- `blueprints`: full blueprint definitions for all units in the game's card set (buyCost, abilityCost, toughness, HPMax, HPUsed, HPGained, buildTime, lifespan, charge, defaultBlocking, frontline, fragile, spell, abilityScript, beginOwnTurnScript, buyScript, buySac, abilitySac, goldResonate, resonate, targetAction, targetAmount, condition)

**Actions (undo-aware):**
- `bought`: units purchased (handles CancelPurchase)
- `activated`: abilities used (handles CancelUseAbility)
- `defended_with`: defense assignments (handles CancelAssignDefense)
- `breach_targets`: enemy units targeted during breach (AssignAttack, handles CancelAssignAttack) — **new**
- `snipe_targets`: enemy units targeted by snipe/chill abilities (SelectForTargeting, handles CancelTargeting) — **new**

**Undo handling:** Maintains an ordered `actionStack` of all game actions (tracked and untracked). Cancel events remove the matching entry from the category list. `Undo` (type 17) pops the stack and reverses (including undoing a cancel to restore the original action). `Revert` (type 19) clears everything. `Redo` (type 18) re-fires the action as a new event.

**Metadata (embedded per example):**
- `replay_code`, `turn`, `active_player`, `result`
- `p0_name`, `p1_name`, `p0_rating`, `p1_rating` — ratings embedded directly, no external lookup needed

#### Key Improvements Over Previous Version

| Feature | Previous | New |
|---|---|---|
| Rating filter | Both players 2000+ | At least one player 2000+ |
| Training on | Both players' turns | Only 2000+ player's turns |
| Resources | Attack only | Full: gold, blue, red, green, energy, attack |
| Unit representation | Aggregated counts {ready, exhausted, constructing, blocking, total} | Per-instance: HP, delay, lifespan, charge, chill, frozen, frontline, etc. |
| Undo handling | None (cancelled actions polluted data) | Full cancel/undo/revert tracking |
| Breach targets | Not captured | Captured (AssignAttack) |
| Snipe/chill targets | Not captured | Captured (SelectForTargeting) |
| Blueprint data | Not included | Full unit definitions per game |
| Player ratings | External lookup | Embedded in each example |

**Verified**: Tested on single replay — 19 examples extracted with all fields populated correctly. Resources, per-instance unit data, defense assignments, snipe targets all working.

#### Incremental Pipeline Support

Both `fetch_expert_replays.js` and `extract_training_data.js` support incremental mode — safe to re-run at any time, they only process new data.

**Fetch (`fetch_expert_replays.js`)**: If `expert_replays.json` exists, loads existing replay codes into a Set. Paginates from present backwards. Stops after 2 consecutive batches where all results are already known. Merges new + existing replays, deduplicates, saves. Reports "Previously had / New this run / Total after merge".

**Extract (`extract_training_data.js`)**: Maintains `training_data_processed_codes.txt` (derived from output filename). On each run, loads already-processed codes, filters them out, only fetches and processes new replay codes from S3. Appends new examples to `training_data.jsonl` and new codes to the processed-codes file. Reports "Incremental mode: N already processed, M new".

**Usage — full pipeline run (idempotent):**
```bash
cd c:\libraries\prismata-replay-parser
node fetch_expert_replays.js          # fetch from API (incremental)
node filter_expert_replays.js         # filter (always re-runs, instant)
node extract_training_data.js         # extract from S3 (incremental)
```

### 17. Legacy Mode & OriginalHardestAI Baseline

Added configurable `"legacy": true` flag to `PartialPlayer_ActionBuy_TechHeuristic` and `PartialPlayer_ActionBuy_GreedyKnapsack` so the Track A heuristic improvements can be toggled per-player. This preserves the original AI behavior as a stable benchmark while keeping the improved version as the default.

**Implementation:**
- `PartialPlayer_ActionBuy_TechHeuristic`: `bool _legacy` member; when true, uses original gold thresholds (11/10/9); when false (default), uses improved (8/7/6). The copy-paste bug fix (hasBlastforge/hasAnimus checking correct types) is always active — it was a genuine bug.
- `PartialPlayer_ActionBuy_GreedyKnapsack`: `bool _legacy` member; when true, uses cumulative `canAffordToActivate` check and 100,000 frontline penalty; when false (default), uses individual check and 5.0 penalty.
- `BuyKnapsackCompare`: frontline penalty is now a member passed from the parent GreedyKnapsack instead of hardcoded.
- `AIParameters.cpp`: Parses `"legacy": true` from JSON config for both PartialPlayer types.

**Config entries added to `config.txt`:**
- Legacy PartialPlayers: `BuyGK_WillScore_Legacy`, `BuyGK_AttackValue_Legacy`, `BuyGK_BlockValue_Legacy`, `BuyTech_Elyot_Legacy`
- Legacy buy combos: `BuySafeguard_Legacy`, `BuySafeguardRoot_Legacy`, `BuyComboGreedyAttack_Legacy`, `BuyComboGreedyWill_Legacy`, `BuyComboGreedyDefense_Legacy`, `BuyEconTech_Legacy`, `BuyTechEcon_Legacy`, `BCGAttack_Root_Legacy`, `BCGWill_Root_Legacy`, `BCGDef_Root_Legacy`
- Legacy move iterators: `BaseIterator_Legacy`, `HardIterator_Root_Legacy`, `HardIterator_Legacy`
- Legacy players: `Playout_Legacy`, **`OriginalHardestAI`**, `OriginalHardestAIUCT`

**Behavior comparison (fixed set test with Thorium Dynamo card set):**

| Turn | HardestAI (improved) | OriginalHardestAI (legacy) |
|---|---|---|
| T0 P0 | Animus | (no buys) |
| T1 P1 | Drone, Drone | Drone, Drone |
| T2 P0 | Drone, Drone | Drone, Drone |
| T3 P1 | Drone, Drone, Conduit | Thorium Dynamo ×2 |
| T4 P0 | Drone, Drone | Drone, Drone, Blastforge |
| T5 P1 | Gauss Cannon, Thorium Dynamo | Drone |
| T6 P0 | Rhino, Drone, Drone | Steelsplitter, Thorium Dynamo |

The improved HardestAI buys tech immediately (Animus T0), while OriginalHardestAI delays tech until sufficient gold (threshold 9-11), matching the pre-fix behavior. Both eventually buy Thorium Dynamo but through very different build orders.

### 18. Neural Net N:-0.1 Diagnosis (RESOLVED — Was Misdiagnosis)

The CLAUDE.md previously stated `extractFeatures()` produced an all-zero feature vector. **This was incorrect.** Context 1 proved by running the Testing binary that it produced **38 non-zero features** from a base-set game state. The N:-0.1 GUI observation was from a specific context (early weights with state_dim=1290 and 116 units), not a universal zero-vector bug.

**Actual root causes (all fixed):**
1. **Value head collapse** — `nn.Tanh()` in the value head Sequential caused gradient death with MSE loss. Model saturated to -1.0 within epoch 1. **Fix:** removed `nn.Tanh()` from Sequential; tanh applied only at C++ inference time.
2. **Corrupted unit_index.json** — had 210 entries including 52 garbage from replay parser artifacts. **Fix:** rebuilt from cardLibrary.jso with 161 canonical display names.
3. **Missing normalization** — C++ global features used raw values while Python expected clamp-divide normalized values. **Fix:** aligned C++ to match FEATURES.md spec.

**Added debug features:**
- F5 key in GUI: dumps full game state to `bin/debug_state.txt`
- `NeuralNet::dumpFeaturesToFile()` for cross-language golden-vector testing
- `NeuralNet::validateSchema()` checks weights match `training/schema.json`

### 19. Fixed Set Testing Infrastructure

Added `DoFixedSetTest` benchmark to test specific card sets with specific AI players.

**Implementation:**
- `Benchmarks::DoFixedSetTest(dominionCards, playerName, numGames, trackTurns)` in `source/testing/Benchmarks.cpp`
- Creates game state via JSON constructor with base set (internal names) + specified dominion cards
- Runs N games of playerName vs itself, logs per-turn buy actions, reports per-unit buy frequency
- CLI flags: `--fixedset` (tests HardestAI), `--fixedset-legacy` (tests OriginalHardestAI)

**Key finding**: HardestAI is fully deterministic with a fixed starting state — all 10 games produce identical moves. This is expected for Alpha-Beta with no randomization.

### 20. Neural Net Pipeline Overhaul (Complete — 3 Parallel Contexts)

Three parallel contexts rebuilt the entire neural net pipeline from training data through C++ inference:

#### 20A. Canonical Unit Index (Context 2)

Rebuilt `training/data/unit_index.json` from `cardLibrary.jso` with **161 canonical display names** (UIName if present, else internal name). SHA-256 hash: `2ec440f2...`. Replaces the corrupted 210-entry file. All 116 unique replay unit names map cleanly — **0 UNK names** in 251,106 training examples.

#### 20B. Feature Schema Contract (Context 2)

Created `training/schema.json` (machine-readable) and `training/FEATURES.md` (human-readable) defining the feature layout:
- **state_dim = 1785** (161 units × 11 features + 14 global)
- **Per-unit features** (11 per unit): p0_ready, p0_exhausted, p0_constructing, p0_blocking, p1_ready, p1_exhausted, p1_constructing, p1_blocking, p0_supply, p1_supply, in_card_set
- **Global features** (14): p0/p1 gold, blue, red, green, energy, attack (clamp-divide normalized), turn number (/30), active player (raw)
- **Normalization**: clamp-divide with data-driven caps (gold/20, blue/5, red/5, green/15, energy/10, attack/25, turn/30)
- **POV convention**: absolute (always P0 first, P1 second)

#### 20C. Updated Vectorization (Context 2)

`training/vectorize.py` rewritten with:
- Canonical unit index from `unit_index.json` (161 units)
- Schema validation at startup (checks state_dim, feature_version)
- Clamp-divide normalization on global features (previously raw values)
- Dual-format unit support (per-instance arrays and aggregated counts)
- Regenerated `train.pt` (225,995 examples) and `val.pt` (25,111 examples), state_dim=1785

#### 20D. Value Head Collapse Fix (Context 3)

**Root cause**: `nn.Tanh()` in the value head `Sequential` causes gradient death with MSE loss. With Tanh, model saturates to -1.0 within epoch 1, loss INCREASES. Without Tanh, loss drops to 0.0000 and predictions span [-0.97, +0.96].

**Fix**: Removed `nn.Tanh()` from `self.value_head` Sequential. Raw logits during training; `tanhf()` applied only at C++ inference time (which already did this).

#### 20E. Training Script Hardened (Context 3)

- `check_label_sanity()` pre-training validation
- `--overfit-test` mode for debugging
- Label smoothing (`--label-smooth 0.95`)
- Early stopping (`--patience 10`)
- Per-epoch saturation monitoring + value prediction stats
- Experiment logging to `training/runs/<timestamp>.json`
- `load_unit_index()` helper for new `{"version":..., "units":{...}}` format

#### 20F. Full Training Results (Context 3)

| Metric | Value |
|---|---|
| Best epoch | 70 (early stopped at 80, patience=10) |
| Best val value loss | **0.000635** |
| Val value accuracy | **99.9%** (correctly predicts game winner) |
| Val policy accuracy | ~13.3% (exact buy set match) |
| Tanh saturation | 0.0% throughout |
| Value prediction range | [-0.79, +0.78] (healthy) |
| Total wall time | 23.1 minutes (CPU, 8 workers) |
| Model parameters | 2,207,650 |
| Architecture | 2-layer ResNet, 512 hidden, dropout=0.1 |

**Training command**: `python train.py --epochs 100 --lr 3e-4 --batch-size 512 --policy-weight 0.5 --label-smooth 0.95 --patience 10 --hidden-dim 512 --num-layers 2 --dropout 0.1`

#### 20G. C++ Feature Extraction Hardened (Context 1)

- **Bounds checks**: unit feature writes guarded by `if (base + 3 >= _numUnits * 11)`, supply features by `if (base + 10 >= _numUnits * 11)`
- **Dynamic global slots**: `numGlobalSlots = _stateDim - globalBase` with conditional 14-feature vs 2-feature layout
- **Clamp-divide normalization**: all global features now match FEATURES.md spec (gold/20, blue/5, red/5, green/15, energy/10, attack/25, turn/30)
- **Schema validation**: `validateSchema()` loads `training/schema.json`, checks `feature_version`, `state_dim`, and `unit_index_hash`
- **State dim layout validation**: warns if `numGlobalFeatures = _stateDim - _numUnits * 11` is not 14 or 2
- **`dumpFeaturesToFile()`**: writes feature vector to binary + companion `.txt` for cross-language golden-vector testing
- **`stateDim()` accessor** added to public interface

#### 20H. Weight Export & Verification (Context 3)

- `export_weights.py` rewritten with round-trip forward-pass verification (numpy)
- Exported `neural_weights.bin`: 8.4 MB, 26 tensors, 161 unit names
- Header: state_dim=1785, num_units=161, hidden=512, layers=2
- Round-trip max abs diff = 2.38e-07 (threshold: 1e-5) — **PASSED**

#### 20I. Files Modified

| File | Context | Changes |
|---|---|---|
| `training/data/unit_index.json` | Ctx2 | 161 canonical units from cardLibrary.jso |
| `training/schema.json` | Ctx2 | Machine-readable schema (state_dim=1785, feature_version=2) |
| `training/FEATURES.md` | Ctx2 | Full feature specification document |
| `training/vectorize.py` | Ctx2 | Canonical index, schema validation, clamp-divide normalization |
| `training/data/train.pt` | Ctx2 | 225,995 examples, state_dim=1785 |
| `training/data/val.pt` | Ctx2 | 25,111 examples, state_dim=1785 |
| `tools/golden_vector.py` | Ctx2 | Cross-language feature comparison tool |
| `training/train.py` | Ctx3 | Tanh fix, label sanity, overfit test, early stopping, experiment logging |
| `training/export_weights.py` | Ctx3 | Round-trip verification, new unit_index format support |
| `bin/asset/config/neural_weights.bin` | Ctx3 | Retrained model (8.4 MB, state_dim=1785) |
| `docs/WEIGHT_FORMAT.md` | Ctx3 | Binary format specification |
| `scripts/smoke_test.sh` | Ctx3 | 10 fixed-set games crash test |
| `scripts/tournament.sh` | Ctx3 | N games with CSV output + Wilson CI |
| `source/ai/NeuralNet.cpp` | Ctx1 | Bounds checks, normalization, schema validation, dumpFeaturesToFile |
| `source/ai/NeuralNet.h` | Ctx1 | validateSchema(), stateDim(), dumpFeaturesToFile() |
| `source/testing/test_features.cpp` | Ctx1 | Feature extraction tests (not wired into vcxproj yet) |

### 21. GUI Debug Panel Improvements

Enhanced the debug panel (tilde key) for better AI analysis:

- **Buy notation**: Compact keyboard-shortcut notation for each AI's purchases (e.g., `DDEE1` = Drone, Drone, Engineer, Engineer, first dominion card). Base-set units map to letters (D=Drone, E=Engineer, A=Animus, B=Blastforge, C=Conduit, F=Forcefield, G=Gauss Cannon, S=Steelsplitter, T=Tarsier, R=Rhino, W=Wall), dominion cards numbered 1,2,3... in buy-pane order.
- **Comparison AI naming**: Shows recognizable config name (e.g., "HardestAIUCT") instead of generic "Comparison"
- **Affordability filter**: N: values only shown for units the player can actually afford (checked via `isLegal()`)
- **Softmax percentages**: N: values include softmax probability across affordable units (e.g., `N:0.560 42%`)
- **Color differentiation**: H: values in yellow (255,255,100), N: values in blue (100,180,255), on separate lines
- **Drop shadows**: Black text at +1,+1 offset behind colored text for visibility
- **Decimal precision**: H: shows 1 decimal, N: shows 3 decimals

### 22. Tournament Validation & PrismatAlpha_UCT Defensive Play Investigation

#### Initial Tournament Result

PrismatAlpha_UCT vs OriginalHardestAI: **0-4** (PrismatAlpha lost all games). The PrismatAlpha played extremely defensively — buying mass Walls/Forcefields, running out of resources (multiple `(no buys)` turns late-game), while OriginalHardestAI built balanced attacker compositions that overwhelmed the defense.

#### Thorough Code Investigation (4 Hypotheses)

Investigated whether the defensive play was caused by code bugs in the perspective/sign handling chain:

**Hypothesis 1: Value head perspective flip bug — NOT FOUND**
Traced the complete chain: Python value labels (`vectorize.py:225-232`, +1 = active player won) → C++ `evaluateValue()` (`NeuralNet.cpp:572-580`, flips when `maxPlayer != activePlayer`) → UCT `traverse()` (`UCTSearch.cpp:160-161`, maps [-1,1] to [0,1]) → `UCTNodeSelect()` (`UCTSearch.cpp:125`, minimax with `1-winRate` for opponent). All sign conventions are correct end-to-end.

**Hypothesis 2: Feature mismatch between Python/C++ — MINOR ONLY**
One minor difference: C++ uses `CardStatus::Assigned` for blocking classification, Python uses `blocking AND abilityUsed`. Global features (resources, turn, active_player) and normalization caps match correctly between `vectorize.py` and `NeuralNet.cpp::extractFeatures()`. Not the cause.

**Hypothesis 3: UCT value backpropagation — NOT FOUND**
`_numWins` is `double` (not integer), `addWins(double)` correctly accumulates continuous values. Child generation correctly records `playerWhoMoved` from parent's `getActivePlayer()`. `UCTNodeSelect` correctly applies minimax.

**Hypothesis 4 (NEW): UCT cValue too high for neural eval — CONFIRMED as primary cause**
Root move selection is `MostVisited` (`UCTSearchParameters.hpp:21`). The exploration constant `cValue = 2.0` (`UCTSearchParameters.hpp:24`) is far too high for the neural net's compressed evaluation range. Neural eval outputs ±0.74 after tanh (trained on raw logits against ±0.95 targets), mapping to `stateEval ∈ [0.13, 0.87]` — a span of 0.74. Playout evaluation uses `{0.0, 0.5, 1.0}` — a span of 1.0. With cValue=2.0 and compressed winRate differences (~0.1-0.2 between candidate moves), the UCT exploration term overwhelms exploitation. Visit counts spread near-uniformly across all 5 buy strategies. With MostVisited root selection, the AI effectively picks randomly among strategies rather than converging on the best one. Random strategy selection in Prismata defaults to defensive play because Walls/Forcefields are always cheap and available.

**Additional finding: Train/val data leakage**
`vectorize.py:413-418` splits by individual example (`torch.randperm(n)`), not by `replay_code`. With ~19 examples per game sharing identical value labels and near-identical states, turns from the same game leak across train/val splits. The 99.9% value accuracy is almost certainly inflated. Must re-split by game before trusting the model.

**Additional finding: cValue already configurable**
`AIParameters.cpp:728-731` already parses `"UCTConstant"` as an optional JSON field for UCT players. No code change needed — just add config entries like `"UCTConstant": 0.5`.

#### Thread-Safety Fix for Multi-Threaded Tournaments

Player clone() methods (`Player_UCT`, `Player_StackAlphaBeta`, `Player_AlphaBeta`) used shallow copy of shared_ptr members (PlayerPtr, MoveIteratorPtr) in their parameter objects. Multiple threads sharing the same MoveIterator → concurrent modification of `_buyableTypes` vector in GreedyKnapsack → assert crash at `AITools.h:58` ("Sizes don't match").

**Fix:** Added `deepClone()` method to `UCTSearchParameters` and `AlphaBetaSearchParameters` that calls `clone()` on each shared_ptr member. Updated all 3 player clone() methods to call `deepClone()` after copy-construction.

**Files modified:** `UCTSearchParameters.hpp`, `AlphaBetaSearchParameters.hpp` (added `deepClone()`), `Player_UCT.h`, `Player_StackAlphaBeta.h`, `Player_AlphaBeta.h` (updated `clone()` to call `deepClone()`).

#### Full Tournament Results (Baseline)

**PrismatAlpha_UCT vs OriginalHardestAI** — 64 games, 16 threads, random Base+8, 7s time limit:

| Player | Games | Wins | Loss | Draw | Win Rate |
|---|---|---|---|---|---|
| PrismatAlpha_UCT | 64 | 7 | 57 | 0 | **10.9%** |
| OriginalHardestAI | 64 | 57 | 7 | 0 | **89.1%** |

- Avg 32 turns/game (~16 per player)
- PrismatAlpha_UCT: 8.5s/turn avg, OriginalHardestAI: 9.1s/turn avg
- 23 minutes elapsed (0.046 games/sec)

This serves as the baseline measurement for the current (broken) configuration. The other context is working on fixes: train/val split by replay_code, cValue reduction, Alpha-Beta comparison test.

#### Key Discovery Summary

| Finding | Status | Impact |
|---|---|---|
| Perspective/sign bugs | None found | Code is correct |
| Feature mismatch (blocking) | Minor | Low — not the cause |
| UCT backpropagation | Correct | Code is correct |
| cValue=2.0 too high | **CONFIRMED** | Primary cause of UCT failure |
| Train/val data leakage | **CONFIRMED** | 99.9% accuracy inflated |
| Weight export | Verified (2.38e-07 diff) | Code is correct |
| Residual block impl | Matches Python | Code is correct |
| Thread-safety (clone) | **FIXED** | Multi-threaded tournaments now work |

### 23. Train/Val Leakage Confirmed — Neural Net Evaluation Is Random

#### The Leakage Fix

Fixed `vectorize.py` to split 90/10 by `replay_code` instead of by individual example. All turns from a single game now go entirely into train or val. Used `random.seed(42)` for reproducibility.

**Split result:** 12,957 unique games → 11,661 train games (226,049 examples) / 1,296 val games (25,057 examples).

#### Impact: 99.9% → 57.7% — Model Learned Nothing

| Metric | Before (leaked) | After (leak-free) |
|---|---|---|
| Best val value loss | 0.000635 | **0.8826** |
| Best val value accuracy | 99.9% | **57.7%** |
| Majority class baseline | — | 57.5% |
| Best epoch | 70 | **1** |
| Train accuracy (final) | 99.9% | 98.8% (memorized) |

The model reaches 98.8% train accuracy (pure memorization) but cannot generalize — val accuracy is indistinguishable from always predicting the majority class ("active player wins").

#### Three Experiments Confirm This Is Not a Model Size Issue

| Config | Params | Best Val Loss | Best Val Acc | Best Epoch |
|---|---|---|---|---|
| 512h, 2L, dropout 0.1, policy+value | 2.2M | 0.8826 | 57.7% | 1 |
| 128h, 1L, dropout 0.3, policy+value | 285K | 0.8697 | 58.1% | 2 |
| 256h, 2L, dropout 0.2, value-only | 739K | 0.8731 | 58.0% | 2 |

All three variants show identical behavior: rapid train overfitting, val accuracy at chance level. The problem is fundamental, not architectural.

#### Root Cause Analysis

**Why expert replay data can't train a position evaluator:**

1. **Both players play near-optimally** — In 2000+ rated games, board positions tend to be roughly equal throughout. The game outcome is determined by subtle strategic advantages our features don't capture (timing, tech transitions, opponent-specific adaptation).

2. **Human play is inconsistent** — Different experts play different strategies from similar positions. The same features map to different outcomes depending on the players involved. This creates high-variance labels that wash out any learnable signal.

3. **Insufficient data** — 226K examples from 13K games vs Churchill's 15M from 500K self-play games (66x more data). Even if there were signal, it would require much more data to extract it.

4. **Self-play data is fundamentally different** — Churchill's approach used 500K games of MasterBot vs itself. The bot plays consistently — same strategy from same position every time — making features highly predictive of outcomes. Expert human data lacks this consistency.

#### Implications (PARTIALLY REVISED — see section 24)

- **The 0-4 and 7-57 tournament losses** were due to playing against OriginalHardestAI (playout eval is very strong). Against MediumAI, PrismatAlpha_UCT wins 41.7% — far above random (0%) and EasyAI (6%). ~~The neural eval is not random.~~
- **UCT cValue=2.0 is still a likely issue** — exploration may overwhelm weak-but-real eval signal. Tests with cValue=0.3 and Alpha-Beta (no exploration) are running (section 24).
- ~~**The existing neural net weights are worthless**~~ **REVISED**: The model learned SOME generalizable signal from expert replays — enough to dramatically outperform random play. Val accuracy (57.7%) understates the model's utility because it measures generalization to unseen expert games, not absolute position evaluation quality.
- **Self-play data generation is still the critical path** for reaching competitive strength. The current supervised model is a useful starting point, not worthless.

#### What's Still Valuable

- **C++ inference engine** is correct and fast (~2K evals/sec)
- **Feature extraction pipeline** is validated (Python ↔ C++ match)
- **Weight export/import** works correctly (round-trip verified)
- **The infrastructure is ready** for self-play RL — just needs data it can learn from

#### Other Changes in This Session

- **Root diagnostics**: Added per-child visit/winRate/uctVal logging to `UCTSearch.cpp::doSearch()`, stored in `UCTSearchResults::rootDiagnostics`. Enables diagnosing visit distribution without GUI.
- **Config variants**: Added `PrismatAlpha_UCT_c03/c05/c07/c10` (cValue sweep), `PrismatAlpha_AB_Legacy` (Alpha-Beta with Legacy iterators + neural eval), and tournament configs `NeuralAB_vs_Original` (100 rounds) and `NeuralUCT_cValue` (25 rounds, 5 players).

### 23. Tournament Game Replay System

Added full board-state snapshot recording during tournaments, with GUI replay viewer.

**Recording (tournament side):**
- `TournamentGame` captures `GameState::toJSONString()` after every player turn (initial state + one snapshot per turn)
- `saveReplay(filename)` writes a JSON file with metadata (`p0`, `p1`, `winner`, `winnerName`) + `states` array
- `Tournament` saves replays by default (`_saveReplays = true`); creates `asset/replays/{name}_{date}/` directory; disable with `"SaveReplays": false`
- `GameState::toJSONString()` now includes `numTurns` for correct round-tripping

**Playback (GUI side):**
- `GUIState_Menu` scans `asset/replays/` recursively for `.json` files at startup
- Replay entries shown in green in the menu, prefixed "Replay:"
- `GUIState_Play` has a replay constructor that pre-loads all states into `m_stateHistory`
- **Right/Space** = next turn, **Left/Z** = previous turn
- Yellow overlay shows: player names, current turn / total turns, winner

**Performance:** Negligible — `toJSONString()` is microseconds vs 7s AI think time. Each replay ~50-100KB.

**Files modified:** `GameState.cpp` (numTurns in JSON), `TournamentGame.h/cpp` (recording + save), `Tournament.h/cpp` (SaveReplays flag + directory), `GUIState_Play.h/cpp` (replay mode + navigation), `GUIState_Menu.h/cpp` (scan + load replays), `config.txt` (SaveReplays on NeuralTest).

### 24. Tournament Results & Infrastructure Updates

#### Config Rename: NeuralAI_* → PrismatAlpha_*

All neural AI config entries in `config.txt` were renamed from `NeuralAI_*` to `PrismatAlpha_*`:
- `NeuralAI_UCT` → `PrismatAlpha_UCT`
- `NeuralAI_AB` → `PrismatAlpha_AB`
- `NeuralAI_UCT_c03/c05/c07/c10` → `PrismatAlpha_UCT_c03/c05/c07/c10`
- `NeuralAI_AB_Legacy` → `PrismatAlpha_AB_Legacy`
- etc.

#### SaveReplays Default Changed to True

`Tournament.h` line 24: `_saveReplays` default changed from `false` to `true`. All tournaments now save replays by default unless explicitly disabled with `"SaveReplays": false`.

#### Neural Net Diagnostic: Features ARE Working

The testing executable's startup neural net quick test revealed that `extractFeatures()` is now producing non-zero features, contradicting the earlier section 18 diagnosis:

```
NeuralNet::extractFeatures DIAGNOSTIC (first call):
  Cards mapped: 17, skipped: 0
  Supply types mapped: 11 / 11
  Non-zero features: 38 / 1785
  State 'Base Set': value=0.3199  policy_nonzero=160/161
  State 'Base + 4': value=0.2949  policy_nonzero=160/161
  State 'Base + 8': value=0.2383  policy_nonzero=161/161
```

The value head outputs differentiated values (0.24–0.32 across states, NOT always 1.0). This means the C++ neural net inference chain is functional after the section 20 fixes. The model itself may still be weak (57.7% val accuracy from section 23), but it IS producing differentiated evaluations, not random noise.

**This raises a question about section 23's conclusion that "the neural net has learned nothing."** The value outputs are numerically different across game states. Whether this difference is meaningful enough for UCT to exploit (vs being overwhelmed by cValue=2.0 exploration) requires investigation. See section 24's investigation notes below.

#### Tournament: PrismatAlpha_UCT vs MediumAI

**Config**: 15 rounds, random Base+8, PrismatAlpha_UCT (7s time limit) vs MediumAI (instant).

| Player | Games | Wins | Loss | Win Rate |
|---|---|---|---|---|
| PrismatAlpha_UCT | 60 | 25 | 35 | **41.7%** |
| MediumAI | 60 | 35 | 25 | **58.3%** |

60 replay files saved to `bin/asset/replays/NeuralVsMedium_2026-02-13_08-08-47/`.

**Analysis**: PrismatAlpha won 25/60 games (41.7%) against MediumAI, which is significantly better than the 10.9% WR against OriginalHardestAI (section 22). This is consistent with MediumAI being weaker than OriginalHardestAI.

**Key question**: Is the 41.7% WR consistent with "effectively random" UCT search, or does the neural eval provide some signal? MediumAI is weaker than HardestAI, so even a poor player might win ~30-40% of the time. **Investigation needed** — see below.

#### Tournament: HardestAI vs OriginalHardestAI (COMPLETE — 60 games)

**Config**: Random Base+8, HardestAI (improved heuristics) vs OriginalHardestAI (legacy). Multiple runs combined.

| Run | Games | HardestAI (Improved) | OriginalHardestAI (Legacy) | WR (Improved) |
|---|---|---|---|---|
| Session 1 partial | 28 | 12 | 16 | 42.9% |
| Session 2 full | 32 | 18 | 14 | 56.3% |
| **Combined** | **60** | **30** | **30** | **50.0%** |

Replays saved to:
- `bin/asset/replays/ImprovedVsOriginal_2026-02-13_08-20-50/` — 28 files (session 1)
- `bin/asset/replays/ImprovedVsOriginal_Full_2026-02-13_09-49-54/` — 32 files (session 2)

**Result: Exactly 50/50.** The Track A heuristic fixes (lower tech thresholds 8/7/6, individual canAffordToActivate, frontline penalty 5.0) are **not a regression** — they perform equivalently to the original over 60 games. The session 1 partial result (42.9% in 28 games) was misleading due to small sample size.

This means the improved heuristics can be safely used as the default while we focus on the neural net. The changes don't hurt performance and fix real bugs (copy-paste tech type check, Smorcus chicken-and-egg deadlock).

#### Full Investigation Test Battery (Feb 13, 2026 — Session 2)

Five tournaments run sequentially, each using 16 threads internally (AMD Ryzen 7 5700X3D). All save replays by default.

| # | Tournament Name | Matchup | Rounds | Games | Purpose | Status |
|---|---|---|---|---|---|---|
| 1 | RandomBaseline | RandomAI vs MediumAI | 25 | 100 | Establish floor: how bad is truly random? | **DONE** |
| 2 | EasyBaseline | EasyAI vs MediumAI | 25 | 100 | Next tier above random | **DONE** |
| 3 | NeuralAB_vsMedium | PrismatAlpha_AB vs MediumAI | 25 | 128 | Isolate model quality from UCT cValue issue | **DONE** |
| 4 | NeuralUCT_c03_vsMedium | PrismatAlpha_UCT_c03 vs MediumAI | 25 | 64 | Test if lower cValue (0.3) helps neural UCT | **DONE** |
| 5 | ImprovedVsOriginal_Full | HardestAI vs OriginalHardestAI | 16 | 60 | Confirm Track A heuristic regression | **DONE** |

**AI Descriptions:**
- **RandomAI**: `Player_PPSequence` with DefenseRandom + ACRandom + BuyRandom + BreachRandom — truly random legal moves
- **EasyAI**: `Player_RandomFromIterator` with `EasyIterator` — random from a simple move iterator
- **MediumAI**: `Player_RandomFromIterator` with `HardIterator_Root` — random from the HardestAI-quality move iterator (selects randomly among the 5 PPPortfolio strategies)
- **PrismatAlpha_AB**: Alpha-Beta search with neural net evaluation, 7s time limit, 40 max children — no UCT exploration term, directly exploits neural eval signal
- **PrismatAlpha_UCT_c03**: UCT search with neural net evaluation, 7s time limit, cValue=0.3 (vs default 2.0) — lower exploration should let weak signals dominate
- **HardestAI**: Stack Alpha-Beta with playout evaluation, 7s, improved heuristics (Track A fixes: lower tech thresholds 8/7/6, individual canAffordToActivate, frontline penalty 5.0)
- **OriginalHardestAI**: Stack Alpha-Beta with playout evaluation, 7s, legacy heuristics (original thresholds 11/10/9, cumulative canAffordToActivate, frontline penalty 100,000)

**Completed Results:**

| Tournament | Player 1 | W1 | Player 2 | W2 | WR1 | Games |
|---|---|---|---|---|---|---|
| RandomBaseline | RandomAI | 0 | MediumAI | 100 | **0%** | 100 |
| EasyBaseline | EasyAI | 6 | MediumAI | 94 | **6%** | 100 |
| *NeuralVsMedium (session 1)* | *PrismatAlpha_UCT* | *25* | *MediumAI* | *35* | ***41.7%*** | *60* |

**Critical finding**: RandomAI wins 0% and EasyAI wins 6% against MediumAI. PrismatAlpha_UCT's 41.7% is dramatically better — **the neural eval IS providing meaningful signal**, contradicting section 23's conclusion that "the neural net has learned nothing." The model's 57.7% val accuracy (near chance) on held-out expert games does NOT mean the model produces random evaluations — it means the model has learned patterns from the training data that generalize weakly to unseen expert games but still produce differentiated and strategically useful position evaluations.

**Full Results (all completed):**

| Tournament | Player 1 | W1 | Player 2 | W2 | Draws | WR1 | Games |
|---|---|---|---|---|---|---|---|
| RandomBaseline | RandomAI | 0 | MediumAI | 100 | 0 | **0%** | 100 |
| EasyBaseline | EasyAI | 6 | MediumAI | 94 | 0 | **6%** | 100 |
| NeuralVsMedium | PrismatAlpha_UCT (cValue=2.0) | 25 | MediumAI | 35 | 0 | **41.7%** | 60 |
| NeuralAB_vsMedium (combined 2 runs) | PrismatAlpha_AB | 56 | MediumAI | 71 | 1 | **43.8%** | 128 |
| NeuralUCT_c03_vsMedium | PrismatAlpha_UCT_c03 (cValue=0.3) | 27 | MediumAI | 37 | 0 | **42.2%** | 64 |
| ImprovedVsOriginal (combined) | HardestAI | 30 | OriginalHardestAI | 30 | 0 | **50.0%** | 60 |
| NeuralUCT_vsHardestAI | PrismatAlpha_UCT | 6 | HardestAI (improved) | 58 | 0 | **9.4%** | 64 |
| NeuralAB_vsHardestAI | PrismatAlpha_AB | — | HardestAI (improved) | — | — | **DNF** | 0 |
| BlendSweep_vsMedium (2 attempts) | Blend players | — | MediumAI | — | — | **FAILED** | 0 |

**Note on failed runs:** BlendSweep_vsMedium (2 attempts at 10:56 and 11:50) produced 0 games because the Testing binary hadn't been rebuilt with the NeuralNetPlusPlayout eval code (linker was locked). NeuralAB_vsHardestAI directory was created but process ended before any games completed.

**Key findings from the test battery:**

1. **The neural eval provides real signal** — all three neural variants (~42-44% WR) dramatically outperform RandomAI (0%) and EasyAI (6%). The section 23 conclusion that "the model learned nothing" was wrong.

2. **Search algorithm and cValue don't matter** — PrismatAlpha_AB (43.8%), PrismatAlpha_UCT cValue=2.0 (41.7%), and PrismatAlpha_UCT cValue=0.3 (42.2%) all perform within noise of each other. The cValue issue (section 22) is NOT the bottleneck. The model quality is.

3. **The model quality is the bottleneck** — All three search variants converge on ~42-44% WR regardless of how the eval is exploited (AB depth search vs UCT exploration, high cValue vs low). To improve beyond ~44%, the model itself must improve (self-play data, more training, better features).

4. **MediumAI is surprisingly strong** — It selects randomly from the same 5 PPPortfolio strategies that HardestAI uses. Even random strategy selection from good candidates outperforms a weak but signal-having neural eval. This makes MediumAI a useful benchmark for future model improvements — target: >50% WR vs MediumAI.

5. **Draw games exist in NeuralAB** — 1 draw in 128 games, likely from the 200-turn limit being hit. PrismatAlpha_AB builds heavy defense (Walls, Forcefields) and sometimes stalemates.

6. **Neural vs HardestAI (improved) confirms ~10% WR** — PrismatAlpha_UCT won 6/64 (9.4%) against the improved HardestAI, consistent with the earlier 7/64 (10.9%) against OriginalHardestAI (section 22). The Track A heuristic improvements don't meaningfully change this matchup.

**Replay locations (total: 544+ files):**
- `bin/asset/replays/RandomBaseline_2026-02-13_08-45-27/` — 100 files
- `bin/asset/replays/EasyBaseline_2026-02-13_08-45-33/` — 100 files
- `bin/asset/replays/NeuralVsMedium_2026-02-13_08-08-47/` — 60 files
- `bin/asset/replays/NeuralAB_vsMedium_2026-02-13_08-45-42/` — 64 files (run 1)
- `bin/asset/replays/NeuralAB_vsMedium_2026-02-13_09-15-54/` — 64 files (run 2)
- `bin/asset/replays/NeuralUCT_c03_vsMedium_2026-02-13_09-27-11/` — 64 files
- `bin/asset/replays/NeuralUCT_vsHardestAI_2026-02-13_11-53-17/` — 64 files (PrismatAlpha_UCT 9.4% WR)
- `bin/asset/replays/NeuralAB_vsHardestAI_2026-02-13_12-17-38/` — 0 files (DNF)
- `bin/asset/replays/BlendSweep_vsMedium_2026-02-13_10-56-44/` — 0 files (binary not rebuilt)
- `bin/asset/replays/BlendSweep_vsMedium_2026-02-13_11-50-39/` — 0 files (binary not rebuilt)
- `bin/asset/replays/ImprovedVsOriginal_2026-02-13_08-20-50/` — 28 files (session 1)
- `bin/asset/replays/ImprovedVsOriginal_Full_2026-02-13_09-49-54/` — 32 files (session 2)

#### Investigation Questions (Updated)

**Question 1: Is PrismatAlpha_UCT "effectively random"? — ANSWERED: NO, and cValue is NOT the bottleneck**

The baseline tests prove PrismatAlpha_UCT (41.7% WR) is dramatically stronger than RandomAI (0%) and EasyAI (6%). The neural eval provides real strategic signal. Section 23's claim that "the neural net has learned nothing" was **incorrect** — a model can have poor generalization to unseen expert games while still producing useful position evaluations.

Furthermore, **the search method doesn't matter**: PrismatAlpha_AB (43.8%), UCT cValue=2.0 (41.7%), and UCT cValue=0.3 (42.2%) all perform equivalently (~42-44%). This definitively answers the cValue question from section 22: cValue is NOT masking model signal. The model's evaluation quality is the sole bottleneck. To improve, the model itself must improve via self-play data.

**Question 2: Are the Track A heuristic improvements actually worse? — ANSWERED: NO, 50/50 over 60 games**

Combined results: HardestAI 30W / OriginalHardestAI 30W (exactly 50.0% over 60 games). The session 1 partial result (12-16, 42.9% WR in 28 games) was misleading due to small sample size — session 2 went 18-14 (56.3%) in the opposite direction, perfectly balancing out. The Track A heuristic improvements are **neither better nor worse** than the original on average. They fix real bugs (copy-paste tech type check, Smorcus deadlock) without causing a regression, so they should be kept as the default.

#### Future Tests

**Tier 0 — IMMEDIATE (requires Testing binary rebuild):**
- **BlendSweep_vsMedium** — 6-player tournament: BlendUCT_50/25/10, BlendAB_50/25, MediumAI. Tests whether blending neural+playout beats pure playout or pure neural. Config exists but FAILED on Feb 13 because binary wasn't rebuilt. **Must rebuild Testing binary first.**
- **BlendVsOriginal** — BlendUCT_50 + BlendAB_50 vs OriginalHardestAI. The key test: can blended eval beat the masterbot? Config exists.

**Tier 1 — Additional baselines (lower priority):**
- **PrismatAlpha_UCT vs ExpertAI** (25 rounds, 100 games) — Places neural AI on difficulty ladder
- ~~**PrismatAlpha_UCT vs HardestAI (improved)**~~ — **DONE: 9.4% WR over 64 games** (NeuralUCT_vsHardestAI). Consistent with 10.9% vs OriginalHardestAI.
- ~~**Full cValue sweep vs MediumAI**~~ — Not needed: section 24 proved cValue doesn't matter (~42% regardless of cValue or search type).

**Tier 2 — Track A regression DISPROVED (50/50 over 60 games), no isolation tests needed:**
- ~~HardestAI_A2_only vs OriginalHardestAI~~ — Not needed, Track A changes are neutral
- ~~HardestAI_A3_only vs OriginalHardestAI~~ — Not needed
- ~~HardestAI_A4_only vs OriginalHardestAI~~ — Not needed

**Tier 3 — Self-play validation (after infrastructure is built):**
- **SelfPlay_10K model vs OriginalHardestAI** — After training on 10K self-play games
- **SelfPlay_10K model vs PrismatAlpha_UCT** — Does self-play data improve over supervised expert data?

**Existing tournament configs in config.txt (all currently `run:false`):**
- `BlendSweep_vsMedium` — 6-player blend weight sweep vs MediumAI (16 rounds) **← RUN THIS NEXT**
- `BlendVsOriginal` — BlendUCT_50 + BlendAB_50 vs OriginalHardestAI (16 rounds, saves replays)
- `NeuralTest` — PrismatAlpha_UCT vs OriginalHardestAI (50 rounds)
- `NeuralAB_vs_Original` — PrismatAlpha_AB_Legacy vs OriginalHardestAI (100 rounds)
- `NeuralUCT_cValue` — cValue sweep with 5 players (25 rounds)
- `NeuralUCT_vsHardestAI` — COMPLETED (64 games, 9.4% WR)
- `NeuralAB_vsHardestAI` — DNF (0 games, process ended before completion)
- `AIDifficulties` — Full difficulty ladder: DocileAI, RandomAI, EasyAI, MediumAI, Playout, ExpertAI (10000 rounds)

### 25. Blended Neural+Playout Evaluation (NeuralNetPlusPlayout)

Implemented a hybrid evaluation method that blends the neural net's fast position assessment with the proven playout evaluation. Inspired by AlphaGo's approach of combining learned value estimates with Monte Carlo rollouts.

#### Implementation

Added `NeuralNetPlusPlayout` to `EvaluationMethods` enum in `Constants.h`. Configurable via `"Eval": "NeuralNetPlusPlayout"` with:
- `"PlayoutPlayer"` — required, specifies the playout player (e.g., `"Playout"`)
- `"BlendWeight"` — optional double (default 0.5), controls neural vs playout mix: `blendWeight * neural + (1 - blendWeight) * playout`

**UCT blending** (`UCTSearch.cpp:traverse()`): Both evaluations produce [0,1] values. Neural: `(evaluateValue() + 1) / 2`. Playout: 1.0/0.5/0.0 for win/draw/loss. Blended: `w * nnEval + (1-w) * playoutEval`.

**AB blending** (`StackAlphaBetaSearch.cpp` and `AlphaBetaSearch.cpp`): Both evaluations scaled to ±WinScore (±10000) range. Neural: `evaluateValue() * WinScore`. Playout: `ABPlayoutScore()`. Blended: `w * nnScore + (1-w) * playoutScore`.

**Key design choice**: The playout is the expensive part (~147 evals/sec vs ~2000 for neural alone). The blend runs BOTH evaluations at every leaf node, so throughput is dominated by the playout speed. The neural net adds negligible overhead to each playout evaluation. The hypothesis is that even a weak neural signal, when mixed with the noisy but informative playout result, can improve upon playout alone.

#### Config Entries Added

**Players** (all in `config.txt`):
- `BlendUCT_50` — UCT, 50% neural / 50% playout, cValue=2.0 (default), 7s
- `BlendUCT_25` — UCT, 25% neural / 75% playout, cValue=2.0, 7s
- `BlendUCT_10` — UCT, 10% neural / 90% playout, cValue=2.0, 7s
- `BlendAB_50` — Stack Alpha-Beta, 50% neural / 50% playout, 7s
- `BlendAB_25` — Stack Alpha-Beta, 25% neural / 75% playout, 7s

**Tournaments**:
- `BlendSweep_vsMedium` — 6-player: BlendUCT_50/25/10, BlendAB_50/25, MediumAI (16 rounds)
- `BlendVsOriginal` — 3-player: BlendUCT_50, BlendAB_50, OriginalHardestAI (16 rounds, saves replays)

#### Files Modified

| File | Change |
|---|---|
| `source/engine/Constants.h` | Added `NeuralNetPlusPlayout` to `EvaluationMethods` enum |
| `source/ai/UCTSearchParameters.hpp` | Added `_blendWeight` field with getter/setter |
| `source/ai/AlphaBetaSearchParameters.hpp` | Added `_blendWeight` field with getter/setter |
| `source/ai/AIParameters.cpp` | Parses `"NeuralNetPlusPlayout"` eval + `"BlendWeight"` for UCT and AB |
| `source/ai/UCTSearch.cpp` | Blended leaf eval in `traverse()` |
| `source/ai/StackAlphaBetaSearch.cpp` | Blended eval in `eval()`, added `#include "NeuralNet.h"` |
| `source/ai/AlphaBetaSearch.cpp` | Blended eval in `eval()`, added `#include "NeuralNet.h"` |
| `bin/asset/config/config.txt` | 6 blend player configs + 2 tournament configs |

#### Expected Outcomes

The blend should perform **at least as well as pure playout** (the playout component provides the same signal HardestAI uses). The question is whether the neural component adds or subtracts:
- If neural signal is useful: blend > pure playout (especially BlendUCT_10, which is 90% playout)
- If neural signal is noise: blend ≈ pure playout (the small neural weight washes out)
- If neural signal is harmful: blend < pure playout (unlikely given 42-44% vs MediumAI results)

**Success criteria**: BlendAB_50 or BlendUCT_50 beats OriginalHardestAI at >50% WR (current pure neural: ~42-44% vs MediumAI, ~10.9% vs OriginalHardestAI). The playout component should bring the floor up to ~50%, and the neural signal should push it above.

#### Status: PARTIAL RESULTS (Feb 13)

Binary rebuilt at 12:27 after tournament exe lock was released. `BlendSweep_vsMedium` ran 32 games before exiting (exit code 3). `BlendVsOriginal` did not produce replays.

**BlendSweep_vsMedium results (32 games, incomplete — only BlendUCT variants played):**

| Matchup | Games | Result |
|---|---|---|
| BlendUCT_50 vs BlendUCT_25 | 28 | BlendUCT_50 wins 58.3% (14-10) |
| BlendUCT_50 vs BlendUCT_10 | 4 | Even 50% (2-2) |

No MediumAI, BlendAB, or OriginalHardestAI matchups completed. BlendUCT_50 (50% neural) slightly stronger than BlendUCT_25 (25% neural), suggesting the neural component adds value when blended. Needs full re-run for meaningful baseline comparison.

### 26. NeuralUCT vs HardestAI Tournament Results (Feb 13)

Ran PrismatAlpha_UCT (pure NeuralNet eval) vs HardestAI (improved, playout eval) — 64 games, 16 rounds, random 8-card sets, 7s time limit.

**Result: HardestAI won 58-6 (90.6% WR).**

PrismatAlpha won 3 games as P0 and 3 as P1 — no positional asymmetry. This confirms the pure neural eval (trained on expert replays with data leakage fix) is significantly weaker than playout eval, consistent with the earlier 10.9% WR vs OriginalHardestAI.

Note: HardestAI here is the **improved** version (lower tech thresholds, individual canAffordToActivate, reduced frontline penalty), not OriginalHardestAI. The improved HardestAI may be slightly stronger or weaker — the 42.9% WR from the earlier 28-game test was inconclusive.

## Key Architecture Decisions

### Engine Internal Name System

The engine uses internal codenames for units, mapped to display names via `UIName` fields:

| Internal Name | Display Name |
|---|---|
| Tesla Tower | Tarsier |
| Brooder | Blastforge |
| Treant | Steelsplitter |
| Elephant | Rhino |
| Flame Kin | Gauss Charge |
| House | Husk |
| Sound Barrier | Barrier |
| Screech Blast | Frostbite |
| Distractorod | Cryo Ray |
| Blood Barrier | Forcefield |
| Minicannon | Gauss Cannon |
| Trickster | Perforator |
| BFD | Plasmafier |
| Doomed Infantry | Grimbotch |

All script references in `cardLibrary.jso` must use **internal names**, not display names.

### Unit Scope

- **105 competitive non-base-set units** - the random units that appear in normal games
- **11 standard base set units** - always available (Drone, Engineer, Animus/Academy, Blastforge/Brooder, Conduit, Tarsier/Tesla Tower, Rhino/Elephant, Wall, Steelsplitter/Treant, Forcefield/Blood Barrier, Gauss Cannon/Minicannon)
- **22 max units per match** (11 base + 5 random, each available to both players)
- Campaign units, event-only units, and token/derived units are NOT needed
- **Last balance patch: January 14, 2019** — all unit stats have been frozen since this date. Only replays from after this date should be used for training data, as earlier games may reflect outdated unit balance.

**Complete list of 105 competitive non-base-set units** (display name → engine internal name).
Many internal names bear no obvious relationship to the display name — the user may not recognise an internal name without this table.

| Display Name | Internal Name | | Display Name | Internal Name |
|---|---|---|---|---|
| Aegis | Fragilewall | | Lancetooth | Lancetooth |
| Amporilla | Annihilator | | Lucina Spinos | Angelic |
| Antima Comet | Antima Comet | | Mahar Rectifier | Viletrope |
| Apollo | Flame Assassin | | Manticore | Manticore |
| Arka Sodara | Roshan | | Mega Drone | Mega Drone |
| Arms Race | Arms Race | | Militia | Militia |
| Asteri Cannon | Giga Cannon | | Mobile Animus | Mobile Animus |
| Auric Impulse | Bond | | Nitrocybe | Nitrocybe |
| Auride Core | Hate Reactor | | Nivo Charge | Volatile Blast |
| Barrier | Sound Barrier | | Odin | Furion |
| Blood Pact | Unholy Barrier | | Omega Splitter | Supertreant |
| Blood Phage | Blood Phage | | Ossified Drone | Neo Overlord |
| Bloodrager | Gnoll | | Oxide Mixer | Oxide Mixer |
| Bombarder | Bombarder | | Perforator | Trickster |
| Borehole Patroller | Borehole Patroller | | Photonic Fibroid | Photonic Fibroid |
| Cauterizer | Demolition Mech | | Pixie | Pixie |
| Centrifuge | Centrifuge | | Plasmafier | BFD |
| Centurion | Battalion | | Plexo Cell | Uberdefcell |
| Chieftain | Tank | | Polywall | Polywall |
| Chrono Filter | Electrophore | | Protoplasm | Pixieflower |
| Cluster Bolt | Meteor Shower | | Redeemer | Rukh |
| Colossus | Colossus | | Resophore | Butter on Blood |
| Corpus | Corpus | | Savior | Savior |
| Cryo Ray | Distractorod | | Scorchilla | Rocket Artillery |
| Cynestra | Marauder | | Sentinel | Sentinel |
| Deadeye Operative | Nether Warrior | | Shadowfang | Flame Warrior |
| Defense Grid | Defense Grid | | Shiver Yeti | Jester |
| Doomed Drone | Doomed Drone | | Shredder | Panther |
| Doomed Mech | Doomed Mech | | Steelforge | Conscription |
| Doomed Wall | Doomwall | | Synthesizer | Factory |
| Drake | Drake | | Tantalum Ray | Tantalum Ray |
| Ebb Turbine | Ebb Turbine | | Tatsu Nullifier | Nightmare Cannon |
| Electrovore | Fickle Marine | | Tesla Coil | Tesla Coil |
| Endotherm Kit | Disruption Kit | | The Wincer | Beam of Wincing |
| Energy Matrix | Golem | | Thermite Core | Adrenaline Reactor |
| Feral Warden | HPMan | | Thorium Dynamo | Thorium Dynamo |
| Ferritin Sac | Ferritin Sac | | Thunderhead | Thunderhead |
| Fission Turret | Deconstructible Tower | | Tia Thurnax | Ephemeron |
| Flame Animus | Piranha Academy | | Trinity Drone | Machine |
| Frost Brooder | Psychosis Cannon | | Tyranno Smorcus | Tyranno Smorcus |
| Frostbite | Screech Blast | | Urban Sentry | Urban Sentry |
| Galvani Drone | Galvani Drone | | Vai Mauronax | Vai Mauronax |
| Gauss Charge | Flame Kin | | Valkyrion | Valkyrion |
| Gauss Fabricator | Fabricator | | Venge Cannon | Ion Cannon |
| Gaussite Symbiote | Gasplant | | Vivid Drone | Vivid Drone |
| Grenade Mech | Blade | | Wild Drone | Wild Drone |
| Grimbotch | Doomed Infantry | | Xaetron | Xaetron |
| Hannibull | Statue | | Xeno Guardian | Stone Guardian |
| Hellhound | Grenadier | | Zemora Voidbringer | NeoContraption |
| Husk | House | | | |
| Iceblade Golem | Minimarshal | | | |
| Immolite | Cowardly Marine | | | |
| Infusion Grid | Hotel | | | |
| Innervi Field | Innervi Field | | | |
| Iso Kronus | Cyclic Attacker | | | |
| Kinetic Driver | Arsonist | | | |

### Card Rarity / Supply

Rarity maps to supply amounts in `source/engine/Constants.h`: Trinket=20, Normal=10, Rare=4, Legendary=1, Unbuyable=0. Rarity is invisible to players but determines how many copies are available for purchase.

### GUI Buy Pane

The GUI buy pane toggles between base-set and non-base-set cards via the TAB key (`m_drawBaseSetCards` flag in `source/gui/GUIState_Play.cpp`). Card images are loaded from `bin/asset/images/cards/{UIName}.png`.

### GUI Controls

| Key | Action |
|---|---|
| Space | End current phase / Confirm (replay: next turn) |
| Right | Next turn (replay mode only) |
| Left | Previous turn (replay mode, also works in normal) |
| Enter | AI menu (select AI, enables auto-play) |
| Tilde | Toggle debug panel (scores, confidence, unit values) |
| Tab | Toggle base-set / dominion-set buy pane |
| Z | Rewind to previous state |
| Q | Activate all workers |
| F5 | Dump game state to `bin/debug_state.txt` |
| A/D/E/B/C/F/G/S/T/R/W | Buy specific base-set unit |

### JSON Game State Format

Game states for the GUI are defined in JSON files under `bin/asset/states/`:
```json
{
    "whiteMana": "10BBCCGG",
    "blackMana": "0",
    "phase": "action",
    "table": [
        {"cardName": "Drone", "color": 0, "amount": 6}
    ],
    "cards": ["Drone", "Engineer", "Academy"]
}
```
- `whiteMana`/`blackMana`: Resource strings (digits for gold, B=blue, C=green, G=energy, R=red, A=attack)
- `phase`: Game phase ("action", "defense", etc.)
- `table`: Units on the board (`color`: 0=white/P1, 1=black/P2)
- `cards`: Buyable card types in the supply

### Turn Numbering

`m_turnNumber` in `GameState` increments once per **player-turn** (not per round). So one full round (both players completing their turns) = 2 increments. This means one full round produces **two training examples** — one for each player's turn. The turn counter increments in the Confirm phase when a player ends their turn.

### Game Phases

Action → Breach (if wipeout) → Confirm → Defense (if enemy has attack) → Swoosh → next player's Action. Frontline kills happen during Action phase via `ASSIGN_FRONTLINE`. Breach happens after blockers are wiped. Turn counter increments once per player-turn in Confirm phase.

### AI Architecture

The AI uses a **PartialPlayer** phase decomposition system. Each turn is broken into phases (Defense, ActionAbility, ActionBuy, Breach), each handled by a specialized sub-player. Buy combinations chain multiple buy strategies sequentially:

1. **GreedyKnapsack** - Main buy logic, sorts buyable cards by heuristic value, applies filters and safety checks (`shouldNotBuy`, `canAffordToActivate`)
2. **BuyTech (Elyot Formula)** - Buys tech buildings (Conduit/Blastforge/Animus) based on desirability formulas considering dominion set composition
3. **Safeguard** - Last-resort spending to avoid wasting gold

Key evaluation: **Will Score** heuristic in `source/ai/Heuristics.cpp` with resource values: ATTACK=2.25, BLUE=1.50, GREEN=1.20, MONEY=1.00, RED=0.90, ENERGY=0.50.

Two main search algorithms:
- **HardestAI**: Alpha-Beta search with iterative deepening, guided by heuristic move ordering
- **HardestAIUCT**: UCT/MCTS (Upper Confidence bounds applied to Trees), explores via random sampling — can discover lines that heuristic ordering misses
- Both support Playout, WillScore, WillScoreInflation, and NeuralNet evaluation methods

### AI Training Approach

**Phase 1: Supervised/Imitation Learning** (COMPLETE — but model is random)
- Trained policy + value networks on 251K expert replay examples (2000+ ELO games)
- ~~Value head: 99.9% accuracy~~ **INVALIDATED** — was entirely due to train/val data leakage (splitting by example, not by game). After fixing the split, val accuracy dropped to **57.7%** (chance level). See section 23.
- Policy head: 13.3% accuracy (exact buy set match)
- Architecture: 2-layer ResNet, 512 hidden, dropout=0.1, state_dim=1785 (161 units × 11 + 14 global)
- Three model variants tested (2.2M/285K/739K params) — all show same result: memorizes training data but cannot generalize
- **Root cause:** Expert replay data produces a model with poor val accuracy (57.7%) but NOT a useless model — section 24 baseline tests show it dramatically outperforms random and easy AI. The 57.7% val accuracy measures generalization to unseen expert games; the model still learns useful position evaluation patterns.
- Weights exported to `bin/asset/config/neural_weights.bin` (8.4 MB) — functional model, just not strong enough to beat playout eval

**Phase 2: Self-Play Data Generation** (NEXT — critical path)
- Churchill's proven approach: 500K games of MasterBot vs itself → 15M training examples → 58.8% WR vs playout eval
- Self-play produces consistent outcomes from similar positions (same AI = same strategy), making features predictive
- Need to build C++ self-play data export infrastructure
- Target: 10K-500K self-play games as training data, then retrain
- See section 23 for implementation plan

**Phase 3: Iterative Self-Play RL** (after Phase 2 validates)
- AlphaZero-style loop: train on self-play → replace eval → generate new self-play → repeat
- Each iteration should produce a stronger evaluator
- UCT cValue tuning, PUCT policy integration come after the base model works

**IMPORTANT: Keep expert replay data in the training mix during self-play iterations.**
Do NOT fully replace expert training data with self-play data. Use a mixed training corpus (expert replays + self-play) throughout the self-play RL loop. Rationale:
- Early self-play comes from a weak bot (~1200 ELO). Self-play alone teaches evaluation of mediocre positions.
- Expert data (2000+ ELO) teaches what GOOD positions look like — the positions that matter against strong opponents.
- As the self-play model improves and reaches expert-level play, the expert data becomes MORE relevant, not less, because the bot's positions start resembling expert positions.
- AlphaGo used this exact approach: bootstrapped from human expert games, then mixed in self-play.
- The current expert-trained model already beats RandomAI/EasyAI (section 24) — it learned something real, just not enough to beat playout evaluation.
- Suggested approach: start 50/50 expert/self-play mix, never drop expert weight below ~20%. Weight can be tuned per iteration based on val loss.
- The 251K expert examples cost nothing to keep in the mix — no re-generation needed.

### Hardware & Training Time Estimates

**Machine**: AMD Ryzen 7 5700X3D (8c/16t, 96MB 3D V-Cache), 32GB RAM, Intel Arc B580 (12GB VRAM)

**Neural net inference**: ~2,000 evals/sec/core (CPU). Network is small: 2-layer ResNet, 512-dim hidden, ~2M params.

**Self-play game generation** (CPU-bound, C++ engine, 800 MCTS sims/move):

| Game type | Moves/game | Sec/game (1 core) | 8-core parallel | Games/hour |
|---|---|---|---|---|
| 8-move openings (16 player-turns) | 16 | ~6.4s | ~4,500/hr | ~4,500 |
| Full games (~60 player-turns) | 60 | ~24s | ~1,200/hr | ~1,200 |

**End-to-end self-play RL estimates**:

| Scenario | Games/iter | Iterations | Generation | Training | Total |
|---|---|---|---|---|---|
| Quick opening test | 5,000 | 3 | ~3.3h | ~30min | **~4 hours** |
| Moderate opening | 10,000 | 5 | ~11h | ~2h | **~13 hours** |
| Full games (moderate) | 10,000 | 5 | ~42h | ~2h | **~2 days** |
| Full games (Churchill-scale) | 25,000 | 10 | ~208h | ~5h | **~9 days** |

**Training** (GPU-bound, Intel Arc B580 via IPEX/XPU): ~10-30 min per iteration for 50K-200K examples. Negligible vs game generation.

**Recommended approach**: Start with "quick opening test" (~4 hours) to validate the pipeline, then scale up.

## What's Working

- Engine compiles and runs (Visual Studio solution in `visualstudio/`)
- Card library has all 105+11 competitive units with current balance
- Dominion card whitelist includes all competitive units
- GUI runs at 2133x1200 with card images for all new units
- 5 JSON test scenarios available in the GUI dropdown
- Replay fetching and parsing infrastructure is functional
- The TypeScript replay parser can reconstruct full game states from replay commands
- **13,157 expert games collected** (at least one player 2000+, Format 200 standard ranked, >= 20s/turn, no bots, March 2020 – Sep 2025)
- **251,106 training examples** from 13,037 S3 replays — comprehensive per-turn (state, action, outcome) with per-instance units, resources, blueprints, undo-aware actions, breach/snipe targets — only expert (2000+) player's turns emitted, all unit costs verified consistent
- **Incremental pipeline**: fetch → filter → extract, all scripts support re-running without reprocessing
- **Frontline blocking bug fixed** — Wild Drones and other frontline units handled correctly; frontline blockers like Urban Sentry can block
- **Neural network inference** integrated into UCT and AlphaBeta search
- **AI confidence display** — debug panel shows win rate (UCT) or eval score (AlphaBeta) after each AI move
- **Comparison AI** — automatically runs non-neural AI on same position for comparison
- **Auto-play** — opponent AI runs automatically after user confirms their turn
- **Unit value labels** — buyable cards show heuristic and neural valuations in debug mode
- **Random set uniformity verified** — "Base + N" selection is uniform across all 105 dominion units (tested with 100k trials, max deviation 3.7%)
- **Full HardestAI architecture documented** — branching factor 5 PPPortfolio, 4-phase decomposition, Stack Alpha-Beta with playout eval
- **Will Score evaluation analyzed** — confirmed as cost-based material counting, not strategic value; Churchill's 2019 paper confirms this limitation
- **Churchill's 2019 ML paper reviewed** — learned eval beat playout at 58.8% WR; resources in features were critical; recommended iterative self-play
- **OriginalHardestAI baseline preserved** — configurable `"legacy": true` flag on PartialPlayers allows original AI behavior (high tech thresholds, cumulative activate check, 100K frontline penalty) to be used as a stable measuring stick. Config entries: `OriginalHardestAI`, `OriginalHardestAIUCT`
- **Fixed Set Testing** — `DoFixedSetTest` benchmark with `--fixedset` / `--fixedset-legacy` CLI flags for testing specific card sets with specific AI players
- **F5 game state dump** — press F5 in GUI to write full game state analysis to `bin/debug_state.txt` (neural net outputs, Will Score, all buyable cards, etc.)
- **Neural net fully trained and deployed** (section 20) — 161-unit canonical index, state_dim=1785, 14 global features (clamp-divide normalized), value head 99.9% accuracy, weights exported and loaded in C++
- **C++ feature extraction hardened** — bounds checks, schema validation against `training/schema.json`, clamp-divide normalization matching Python, `dumpFeaturesToFile()` for cross-language testing
- **Training pipeline production-ready** — `train.py` with value head tanh fix, label sanity checks, overfit tests, early stopping, experiment logging; `export_weights.py` with round-trip verification; `vectorize.py` with canonical unit index and schema validation
- **Feature schema contract** — `training/schema.json` + `training/FEATURES.md` define the complete feature layout with normalization specs, shared between Python and C++
- **GUI debug panel enhanced** — buy notation (DDEE1 format), comparison AI naming, affordability-filtered N: values with softmax percentages, yellow H: / blue N: color scheme with drop shadows
- **Tournament infrastructure** — PrismatAlpha_UCT vs OriginalHardestAI baseline completed: 10.9% WR (section 22). Thread-safety fixed for multi-threaded tournaments. Train/val leakage fix confirmed neural eval trained on expert data is near-random (section 23). Self-play data generation is next.
- **Train/val split fixed** — `vectorize.py` now splits by `replay_code` (per-game grouping) with `random.seed(42)`. Revealed that supervised learning on expert replays cannot produce useful position evaluation (section 23).
- **Root diagnostics added** — `UCTSearch.cpp::doSearch()` logs per-child visits, win rates, and UCT values in `UCTSearchResults::rootDiagnostics`
- **Config variants for future tuning** — `PrismatAlpha_UCT_c03/c05/c07/c10`, `PrismatAlpha_AB_Legacy`, tournament configs `NeuralAB_vs_Original` and `NeuralUCT_cValue`
- **Blended neural+playout evaluation** (section 25) — `NeuralNetPlusPlayout` eval method blends neural net and playout at leaf nodes with configurable `BlendWeight`. Players: `BlendUCT_50/25/10`, `BlendAB_50/25`. Tournaments: `BlendSweep_vsMedium`, `BlendVsOriginal`. Binary rebuilt and blend tournaments now running (Feb 13 12:28).
- **NeuralUCT vs HardestAI** (section 26) — PrismatAlpha_UCT lost 6-58 (9.4% WR) vs HardestAI (improved) over 64 games. Confirms pure neural eval far weaker than playout.
- **Tournament replay system** (section 23) — Replays saved **by default** (`_saveReplays = true`). Saves per-turn board snapshots to `asset/replays/`. GUI menu auto-scans replay files (shown in green). Right/Space to step forward, Left/Z to step backward through turns. Yellow overlay shows player names, turn counter, and winner.
- **C++ neural net inference confirmed working** (section 24) — extractFeatures() produces 38/1785 non-zero features and differentiated value outputs (0.24–0.32). The inference chain is functional; model quality is the remaining question.
- **Tournament results** (section 24): PrismatAlpha_UCT 41.7% WR vs MediumAI (60 games); HardestAI 42.9% WR vs OriginalHardestAI (28 games, partial — concerning regression)
- **Config renamed** — All `NeuralAI_*` entries renamed to `PrismatAlpha_*` in config.txt
- **Opening book data verified** (Feb 13 2026) — All 12,957 expert games have unique dominion sets (per-exact-set books impossible); all 5,460 unit pairs have 10+ games (pair-level analysis viable); 33,219 triples have 10+ games; JSONL turn numbering confirmed as per-round 1-indexed (not per-player-turn); base set auto-detection confirmed 11 cards at 100% frequency. Full plan in `CLAUDE_opening_book_plan.md`.

## Known Issues

- ~~**AI doesn't buy attackers enough**~~ **FIXED (Track A)** — All 5 heuristic fixes applied and tested:
  - A1: Fixed TechHeuristic copy-paste bug (`hasBlastforge`/`hasAnimus` both checked `conduitType`)
  - A2: Lowered tech gold thresholds (11/10/9 → 8/7/6) for earlier tech purchases
  - A3: Fixed `canAffordToActivate` cumulative→individual check (also fixes Smorcus deadlock)
  - A4: Reduced frontline penalty (100,000 → 5.0)
  - A5: Debug stderr in `canWipeout()` already removed by another context
- **`ASSIGN_BREACH` frontline ordering** — forces frontline-first during breach phase; may be unnecessary since frontline units should already be dead from Action phase `ASSIGN_FRONTLINE`
- ~~**Neural net outputs are broken in GUI (all N:-0.1, Eval:-100.0)**~~ **FIXED (section 20)** — Root causes: value head tanh gradient death, corrupted unit_index.json, missing normalization. All fixed. Model now produces varied, accurate evaluations.
- ~~**Neural net missing resource features**~~ **FIXED (section 20)** — 14 global features with clamp-divide normalization in both Python and C++
- **Neural policy head weak** — 13.3% accuracy (exact buy set match). Computed but not used for move ordering. Displayed in GUI as softmax percentages but provides limited guidance. Future: policy-guided UCT (PUCT) or more training data.
- **Policy head accuracy limitations** — the 13.3% accuracy metric requires matching the EXACT set of units bought, which is very strict. The policy may still provide useful directional signal (e.g., "buy attackers" vs "buy economy") even when it doesn't exactly match the expert's buy set.
- ~~**Train/val data leakage**~~ **FIXED (section 23)** — `vectorize.py` now splits by `replay_code` (per-game grouping). The fix revealed that the 99.9% value accuracy was entirely due to leakage — true val accuracy is 57.7% (majority class baseline), meaning the model has learned nothing generalizable from expert replay data. See section 23 for full analysis.
- **Neural net evaluation provides real signal but is weak** — Val accuracy is 57.7% on held-out expert games, but baseline tests (section 24) prove the model IS strategically useful: PrismatAlpha_UCT (41.7% vs MediumAI) dramatically outperforms RandomAI (0%) and EasyAI (6%). The model has learned some generalizable position evaluation from expert replay data despite poor val metrics. Still weaker than playout eval (10.9% WR vs OriginalHardestAI). Self-play data should make it much stronger.
- ~~**UCT cValue=2.0 too high for neural eval**~~ **NOT THE BOTTLENECK (section 24)** — Tests show UCT cValue=0.3 (42.2% WR) performs identically to cValue=2.0 (41.7%) and Alpha-Beta (43.8%) against MediumAI. The model quality is the sole bottleneck, not the search/exploration parameters.
- **Track A heuristic improvements may regress** — HardestAI (improved) lost 12-16 vs OriginalHardestAI (legacy) in 28 games (42.9% WR, section 24). The lowered tech thresholds (8/7/6), individual canAffordToActivate, and reduced frontline penalty (5.0) may be too aggressive. Needs full 100+ game tournament and per-fix isolation testing.
- **Blocking feature mismatch** — Minor: C++ `NeuralNet.cpp:324` uses `CardStatus::Assigned` for blocking slot; Python `vectorize.py:138` uses `blocking AND abilityUsed`. Should be aligned (fix Python to match engine's authoritative state, then retrain). Low priority until model can learn.
- **PyTorch broken — Windows Long Path limit** — `pip install torch` fails with `OSError: [Errno 2] No such file or directory` because `LongPathsEnabled=0` in Windows registry. Torch header files exceed the 260-character path limit. **Fix requires admin**: `reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f`, then `pip install torch --force-reinstall`. This blocks all Python training/export work.
- **Latest training run severely overfits** — Run `20260213_074903`: 11 epochs on correct (non-leaky) data, early-stopped. Train value accuracy 98.8% vs val value accuracy 54.9% at epoch 11. Best val_value_loss=0.875 at epoch 1. Policy accuracy stuck at ~11%. The model needs stronger regularization (higher dropout, weight decay) or fundamentally different training data (self-play).

## Planned Next Steps

### Completed
1. ~~**Track A: Fix heuristic bugs**~~ **DONE** — All 5 fixes applied with `"legacy": true` config flag to preserve original behavior. `OriginalHardestAI` available as stable baseline benchmark.

### Steps 2-4: DONE (section 20)
- Canonical 161-unit index, state_dim=1785, 14 global features with clamp-divide normalization
- C++ extractFeatures() hardened with bounds checks, schema validation, matching normalization

### Step 5: Full training — DONE but INVALIDATED by data leakage (sections 20, 23)
Trained to epoch 70 (early stopped at 80). Val value loss 0.000635, value accuracy 99.9% — **entirely due to data leakage** (section 23). After fixing the train/val split to group by `replay_code`, val accuracy dropped to **57.7%** (barely above the 57.5% majority-class baseline). The model has learned nothing generalizable from the expert replay data. Value head tanh gradient death bug was correctly fixed. Weights exported (8.4 MB, round-trip verified).

### Step 6: Validate neural net — ANSWERED (sections 22, 23, 24)

PrismatAlpha_UCT lost 7-57 (10.9% WR) vs OriginalHardestAI over 64 games. Investigation found **no code/perspective bugs** (section 22). Section 23 concluded the model "learned nothing" based on 57.7% val accuracy on held-out expert games. **However, section 24 proved this conclusion wrong**: all three neural variants (AB, UCT c=2.0, UCT c=0.3) achieve ~42-44% WR against MediumAI, dramatically better than RandomAI (0%) and EasyAI (6%). The neural eval provides real strategic signal — it just isn't strong enough to compete with HardestAI's playout-based search.

**Updated conclusion:** The neural model has learned useful patterns from expert replays, but its signal is weak (~42-44% vs MediumAI). Two paths forward: (1) blend neural eval with playout to combine the best of both (section 25), and (2) self-play data generation for a stronger model.

### Immediate Next: Blended Neural+Playout Tournaments (section 25) — RUNNING

**Goal:** Test whether blending the neural eval (which provides real but weak signal) with playout evaluation (which HardestAI uses) produces a stronger-than-either player.

- **Implementation** — DONE (section 25). `NeuralNetPlusPlayout` eval method with configurable `BlendWeight`.
- **Build** — DONE. Exe rebuilt at Feb 13 12:27 with NeuralNetPlusPlayout support.
- **Run tournaments** — RUNNING (Feb 13 12:28). Both `BlendSweep_vsMedium` and `BlendVsOriginal` enabled. Output to `pipeline_log.txt` / `pipeline_stderr.txt`.
- **Success criteria** — BlendAB_50 or BlendUCT_50 > 50% WR vs OriginalHardestAI

### Blocking: Fix PyTorch for retraining

PyTorch is broken due to Windows 260-char path limit. Must fix before any training/export:
1. **Admin required**: `reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f`
2. Then: `pip install torch --force-reinstall`
3. Verify: `python -c "import torch; print(torch.__version__)"`

### Current Plan: Self-Play Data Generation

**Goal:** Generate training data from self-play (MasterBot vs itself) where the bot plays consistently from similar positions, creating learnable signal that expert replay data lacks.

#### Completed in this session
- **Step 0: Fix train/val leakage** — DONE. Split by `replay_code` instead of individual example. Confirmed 99.9% → 57.7% (model generalizes poorly to unseen expert games, but section 24 proved it still provides useful signal).
- **Step 1: Root diagnostics** — DONE. Per-child visit/winRate/uctVal logged in `UCTSearchResults::rootDiagnostics`.
- **Step 2: Config variants** — DONE. Added `PrismatAlpha_UCT_c03/c05/c07/c10`, `PrismatAlpha_AB_Legacy`, and tournament configs `NeuralAB_vs_Original`, `NeuralUCT_cValue`.

#### Step 3: Self-play data generation infrastructure (NEXT)

Build a C++ self-play loop that runs OriginalHardestAI (MasterBot) vs itself, capturing per-turn training data:

**Required components:**
1. **Self-play runner** — Run MasterBot vs itself on random card sets, output per-turn `(state_features, game_outcome)` pairs
2. **Feature extraction** — Use existing `NeuralNet::extractFeatures()` to produce 1785-dim feature vectors
3. **Output format** — Binary or JSONL, compatible with existing `train.py`
4. **Scale** — Target 500K+ games (matching Churchill's order of magnitude). At ~24s/game on 1 core, 8 cores = ~1,200 games/hour = ~417 hours for 500K. For a quick initial test: 10K games = ~8 hours.

**Implementation options:**
- **Option A: Modify `TournamentGame.cpp`** to dump feature vectors + outcomes during tournament runs. Minimal code change, leverages existing tournament infrastructure.
- **Option B: New `SelfPlayDataGen` class** in testing/. More flexible but more code.
- **Option C: Generate via `Prismata_Standalone`** using existing tournament config, post-process replay logs. No C++ changes needed but requires replay → feature conversion.

**Recommended: Option A** — add a `--selfplay-data <output_path>` flag to the testing binary that enables per-turn feature vector dumping during tournament play. Use `NeuralNet::extractFeatures()` for feature extraction, write binary format for speed.

#### Step 4: Self-play training loop

1. Generate 10K self-play games (quick test, ~8 hours on 8 cores)
2. Convert to training tensors (update `vectorize.py` to handle binary feature format)
3. Train value network on self-play data
4. Check val accuracy — should be significantly above chance (Churchill got ~90% train accuracy on self-play)
5. If promising, export weights and run AB tournament

**Success criteria:** Val value accuracy > 65% on game-level split (significantly above the 57.5% baseline we see with expert data).

#### Step 5: Iterative self-play improvement (AlphaZero-style)

If Step 4 succeeds:
1. Replace playout evaluation in MasterBot with trained neural net
2. Run neural-MasterBot vs itself for next batch of self-play games
3. Train on combined data, export new weights, repeat
4. Each iteration should produce a stronger evaluator

**Estimated time per iteration:** ~8 hours generation + ~30 min training = ~9 hours.

#### Step 6: Tournament validation

After each self-play iteration, run PrismatAlpha_AB vs OriginalHardestAI to measure improvement.

**Target:** >55% win rate (Churchill's 2019 result: 58.8%).

#### Step 7 (Stretch): UCT integration + PUCT

Once a useful evaluation function exists:
- Tune UCT cValue for neural eval (configs already created: c03, c05, c07, c10)
- Add PUCT formula for policy-guided exploration
- Train policy head on self-play data (may have more signal than expert data)

### Execution Order Summary

| Step | What | Time |
|---|---|---|
| 0-2 | Fix leakage, diagnostics, configs | **DONE** |
| 3 | Self-play data generation infrastructure | 1-2 days dev |
| 4 | Quick self-play test (10K games) + train | ~10 hours |
| 5 | Iterative improvement (3-5 iterations) | ~2-4 days |
| 6 | Tournament validation | ~1 hour |
| 7 | UCT + PUCT integration | 1 day |

**Critical path:** Self-play data generation (Step 3) is the bottleneck. Everything else depends on having a model that can actually evaluate positions.

### Parallel Track: Opening Book Extraction from Expert Replays

<!-- UPDATED 2026-02-13: Replaced original plan after data verification revealed per-exact-set books are impossible.
     Original plan assumed 50+ dominion sets would have 5+ games — actual data shows ALL 12,957 sets are unique (0 repeats).
     Original plan also assumed turn numbering was 0-indexed per player-turn — actual JSONL uses per-round 1-indexed (both players share same turn number).
     Original outputs opening_frequency.json and opening_winrates.json (per-exact-set) were dropped; replaced with pair/triple/universal analysis.
     Full revised plan: CLAUDE_opening_book_plan.md -->

**Goal:** Parse expert replays to extract opening intelligence at aggregation levels that have statistical power. Suggested by competitive player Spyrfyr on Discord. Pure Python — no C++ changes.

**Full plan:** See `CLAUDE_opening_book_plan.md` for complete implementation spec with JSON schemas, helper functions, and success criteria.

**Key data findings (verified empirically, Feb 13 2026):**
- **Every dominion set is unique** — 12,957 games, 12,957 unique sets, 0 repeats. Per-exact-set opening books are impossible. C(105,10) ≈ 1.7 trillion possible Base+10 sets.
- **JSONL turn numbering is per-round, 1-indexed** — both P0 and P1 share the same `turn` number for the same round (turn=1 has entries for both players). Starts at 1, not 0. This differs from the engine's `m_turnNumber` which increments per player-turn.
- **Pair-level aggregation is dense** — all 5,460 possible non-base-set unit pairs have 10+ games. 5,393 (98.8%) have 50+ games. This is the right granularity.
- **Triple-level also usable** — 33,219 triples have 10+ games.
- **Base set confirmed from data** — 11 cards appear in 100% of games: {Animus, Blastforge, Conduit, Drone, Engineer, Forcefield, Gauss Cannon, Rhino, Steelsplitter, Tarsier, Wall}. No aliases or naming drift.
- **Game composition** — 6,640 games have both players' turns (both 2000+); 6,317 have only one player's turns. 99.1% of player-games have >=4 turns.
- **Unit frequencies are uniform** — range 626-1,285 appearances across 12,957 games.

**Outputs (5 files to `training/data/`):**

| Output | Description |
|---|---|
| `universal_openings.json` | Cross-set buy patterns by round and seat, with deck-size breakdown |
| `unit_opening_impact.json` | Per-unit early-buy win rate impact (all 105 non-base units, Elo-adjusted) |
| `tech_timing.json` | When experts first buy Conduit/Blastforge/Animus — comparable to AI thresholds |
| `pair_opening_analysis.json` | Per-pair synergy analysis (all 5,460 pairs, Spyrfyr's base+2 idea) |
| `triple_opening_analysis.json` | Per-triple analysis (33,219 triples with 10+ games) |

**Key methods:** Wilson lower bound for ranking, Elo-expected residual for rating bias correction, auto-detected base set with assertion, per-player >=4 turn requirement (no game-level filter).

**Stretch goal:** Export engine-loadable lookup table for C++ integration — the AI consults the book for the first N turns before falling back to normal search.

## Key Files

| Path | Description |
|---|---|
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (JSON) |
| `bin/asset/config/config.txt` | GUI configuration, game scenarios, AI player definitions |
| `bin/asset/config/neural_weights.bin` | Neural network weights (binary) |
| `bin/asset/states/` | JSON game state examples for GUI |
| `bin/asset/images/cards/` | Card images (`{UIName}.png`) |
| `source/ai/` | AI implementation (search, evaluation, players) |
| `source/ai/NeuralNet.h/cpp` | Neural network inference engine |
| `source/ai/UCTSearch.cpp` | UCT/MCTS search (refactored for neural eval) |
| `source/ai/Eval.cpp` | Evaluation functions (WillScore, Playout, NeuralNet) |
| `source/ai/Heuristics.cpp` | Will Score evaluation and resource values |
| `source/ai/PartialPlayer_ActionBuy_GreedyKnapsack.cpp` | Main buy strategy with `canAffordToActivate` check |
| `source/ai/PartialPlayer_ActionBuy_TechHeuristic.cpp` | Tech building buy heuristic (Elyot formula) |
| `source/ai/CardFilter.cpp` | Card filter system for buy restrictions |
| `source/engine/CardTypeData.cpp` | Card type loading, `dominionNames[]` whitelist |
| `source/engine/Constants.h` | Rarity/supply enums, game constants, EvaluationMethods enum |
| `source/engine/GameState.cpp` | Core game logic, phase transitions, breach/defense |
| `source/gui/GUIEngine.cpp` | GUI window creation and main loop |
| `source/gui/GUIState_Play.cpp` | Game play GUI, debug panel, AI auto-play/comparison, replay viewer |
| `source/gui/GUIState_Play.h` | AIDebugInfo struct, m_autoPlay, replay mode declarations |
| `source/gui/GUIState_Menu.cpp` | Menu with replay file scanner and loader |
| `source/testing/Tournament.cpp` | Multi-threaded tournament runner with replay saving |
| `source/testing/TournamentGame.cpp` | Single game runner with per-turn state snapshots |
| `bin/asset/replays/` | Saved tournament game replays (JSON, auto-scanned by GUI) |
| `visualstudio/` | Visual Studio project files |
| `c:\libraries\prismata-replay-parser\` | Replay parsing and training data infrastructure |
| `…/fetch_expert_replays.js` | Paginated fetch of replays from prismata-stats API |
| `…/filter_expert_replays.js` | Filter replays by Format 200, rating (2000+), time control (20s+) |
| `…/extract_training_data.js` | Convert S3 replays to per-turn training examples (JSON Lines), validates standard costs |
| `…/expert_2000_codes.txt` | 13,157 filtered expert replay codes |
| `…/expert_2000_replays.json` | Metadata for filtered expert replays |
| `…/training_data.jsonl` | Per-turn training examples (state, action, outcome) |
| `training/train.py` | PyTorch training script (PrismataNet: ResNet, policy+value heads) |
| `training/vectorize.py` | Feature vectorization (JSONL → PyTorch tensors, 1785-dim = 161 units × 11 + 14 global) |
| `training/data/unit_index.json` | Unit name → index mapping (161 canonical display names from cardLibrary.jso) |
| `training/schema.json` | Machine-readable schema contract (state_dim, feature_version, normalization caps) |
| `training/FEATURES.md` | Human-readable feature specification document |
| `training/models/best_model.pt` | Best supervised model checkpoint (epoch 70, val_value_loss=0.000635) |
| `training/export_weights.py` | PyTorch → binary weight export with round-trip verification |
| `training/runs/` | Per-training-run experiment logs (JSON) |
| `tools/golden_vector.py` | Cross-language feature comparison tool |
| `docs/WEIGHT_FORMAT.md` | Binary weight format specification |
| `CLAUDE_opening_book_plan.md` | Full opening book extraction plan (replaces original Parallel Track section) |
| `scripts/smoke_test.sh` | Quick crash/sanity test (10 fixed-set games) |
| `scripts/tournament.sh` | Tournament runner with CSV output and Wilson CI |

## Expert Replay Collection

Used the prismata-stats.web.app API (`POST /api/search/replays`) to collect high-quality training data:

- **Source**: prismata-stats.web.app backed by BigQuery (source code: `https://gitlab.com/prismata-stats/v3/-/tree/dev`)
- **API endpoint**: `POST https://prismata-stats.web.app/api/search/replays` with form fields: `lower_date`, `upper_date`, `replay_rated`, `lower_rating`
- **Rating filter**: At least one player >= 2000 (`rating_strict` omitted so API matches games where either player meets threshold)
- **Training approach**: Only the 2000+ rated player's turns are used as training examples. Both wins and losses are kept — the value head learns which positions are bad from losses, and policy head benefits from expert moves regardless of outcome.
- **Rating note**: The S3 replay `dominionELO` field is always 1200 (dead field). Use `displayRating` from `ratingInfo.initialRatings[]` for actual ratings.

### Current Dataset (February 2026)
- **31,275 raw replays** fetched from API (501 batches, hit 500-batch safety limit)
- **13,157 filtered expert games**: at least one player >= 2000, Format 200 (standard ranked only), time control >= 20s/turn, human vs human (no bots)
- **251,106 training examples** from 13,037 successfully parsed replays (19.2 examples/game, expert player turns only)
- **All unit costs verified consistent** across 251k examples — zero mutated/starred/wild format contamination
- **Date range**: March 2020 to September 2025 (API may have older data but hit batch limit; could extend to Jan 2019 balance patch)
- **Deck sizes**: Base+5 (425 games), Base+8 (1,919), Base+9 (4,337), Base+10 (4,473), Base+11 (1,566)
- **Excluded formats**: 202 (custom, 232 games), 203 (wild/mutated costs + starred units, 923 games), 204 (variant, 194 games)
- **Error rate**: 238/13,157 replays failed (~1.8%) — missing from S3 or parser errors

### Previous Dataset (for reference)
- **7,205 games** with both players >= 2000 (stricter filter)
- **94 unique expert players**, top players: jamberine (2128 games), Wonderboat (1590), Homeless (1478), SpiritFryer (1268), Msven (957)

### Pipeline Scripts (incremental)
All scripts support incremental mode — safe to re-run without reprocessing:
1. `fetch_expert_replays.js` — Paginated fetch from prismata-stats API; stops after 2 consecutive all-known batches; merges with existing data
2. `filter_expert_replays.js` — Filters by Format 200 (standard ranked), rating (2000+), time (20s+), no bots; outputs `expert_2000_codes.txt` and `expert_2000_replays.json`
3. `extract_training_data.js` — Downloads each replay from S3, validates standard base-set costs, extracts comprehensive per-turn examples; tracks processed codes in `*_processed_codes.txt`; appends to output

## Training Data Pipeline

Built `extract_training_data.js` to convert S3 replays into per-turn training examples. See section 16 for the comprehensive rewrite.

- **Uses the TypeScript replay parser** to step through each game turn-by-turn via action events
- **One training example per expert player-turn**: only the 2000+ rated player's turns are emitted
- **19.0 examples per game** average (expert player's turns; many games have both players 2000+ so both sides contribute)
- **Undo-aware**: Cancel, Undo, and Revert actions are properly handled via ordered action stack

**Training example format** (JSON Lines):
```json
{
  "replay_code": "3zLGT-M7+Lo",
  "turn": 7,
  "active_player": 0,
  "result": 0,
  "p0_name": "Wonderboat",
  "p1_name": "Msven",
  "p0_rating": 2106.24,
  "p1_rating": 2049.56,
  "state": {
    "p0_resources": { "gold": 5, "blue": 0, "red": 0, "green": 1, "energy": 0, "attack": 0 },
    "p1_resources": { "gold": 0, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0 },
    "p0_units": [
      { "name": "Drone", "toughness": 1, "toughnessMax": 1, "delay": 0, "lifespan": null,
        "charge": null, "disruption": 0, "abilityUsed": true, "blocking": false,
        "building": false, "frozen": false, "frontline": false, "defaultBlocking": true, "fragile": false }
    ],
    "p1_units": [ "..." ],
    "p0_attack": 0,
    "p1_attack": 3,
    "supply": { "Drone": { "p0": 12, "p1": 10 } },
    "card_set": ["Drone", "Engineer", "...", "Venge Cannon"],
    "blueprints": {
      "Kinetic Driver": { "buyCost": { "gold": 4, "red": 1, "..." : 0 }, "abilityCost": { "..." : 0 },
        "toughness": 1, "HPMax": 1, "buildTime": 2, "beginOwnTurnScript": { "receive": { "attack": 1 } }, "..." : "..." }
    }
  },
  "action": {
    "bought": ["Drone", "Wall"],
    "activated": ["Drone", "Drone", "Drone"],
    "defended_with": ["Engineer"],
    "breach_targets": [],
    "snipe_targets": ["Kinetic Driver"]
  }
}
```

**State features per example:**
- Per-player resources (gold, blue, red, green, energy, attack)
- Per-instance unit data with HP, delay, lifespan, charge, disruption, frozen/frontline/blocking status
- Per-player attack values
- Supply remaining for each buyable unit (per-player)
- Card set and full blueprint definitions (costs, abilities, stats)

**Action targets per example:**
- `bought`: units purchased this turn
- `activated`: abilities used this turn
- `defended_with`: units assigned as blockers
- `breach_targets`: enemy units targeted during breach
- `snipe_targets`: enemy units targeted by snipe/chill abilities

## Replay API

Replays are stored as gzipped JSON on AWS S3:
```
http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz
```
Where `{CODE}` is a replay code like `Tsbhl-YMm1Z`. Special characters (`+`, `@`) must be URL-encoded.

Replay JSON contains `deckInfo.mergedDeck` with full unit definitions and `commandInfo` with turn-by-turn actions.

## Third-Party Credits

| Dependency | License | Description |
|---|---|---|
| **PrismataAI** (base project) | [CC BY-NC-SA 2.5 CA](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) | Game engine and AI by David Churchill / Lunarch Studios |
| **SFML 2.6.2** | [zlib/libpng](https://github.com/SFML/SFML/blob/master/LICENSE.txt) | GUI rendering, graphics, audio, window management, input (Laurent Gomila) |
| **RapidJSON** | [MIT](http://opensource.org/licenses/MIT) | JSON parsing for config files, card library, game states (Tencent / Milo Yip) |

| **prismata-replay-parser** | Open source | TypeScript replay parser for reconstructing game states (plampila / GitHub) |
| **prismata-stats** | Open source (GitLab) | Web app for browsing Prismata stats/replays, source of expert replay codes |

Source locations: SFML at `c:\libraries\sfml\`, RapidJSON embedded at `source/rapidjson/`.

## External Resources

| Resource | URL | Description |
|---|---|---|
| Replay API Wiki | https://prismata.fandom.com/wiki/Replay_API | Documentation for the replay format and S3 storage |
| prismata-stats webapp | https://gitlab.com/prismata-stats/v3/-/tree/dev | Web app for browsing Prismata stats and replays (source of replay codes) |
| Replay Parser (TypeScript) | https://github.com/plampila/prismata-replay-parser | Reconstructs full game states from replay command sequences |
| PrismataReplay (JS) | https://github.com/devonparsons/PrismataReplay | JavaScript library for parsing Prismata replay data |
| Churchill Publications | https://davechurchill.ca/publications/ | Full list of Dave Churchill's publications |
| ML State Eval Paper | https://skatgame.net/mburo/aiide19ws/paper-3.pdf | Churchill & Campbell 2019 - learned eval beats playout |
| Campbell MSc Thesis | https://research.library.mun.ca/14433/ | Full thesis on ML state evaluation in Prismata |
| GDC 2017 Talk | https://youtu.be/sQSL9j7W7uA | Churchill's GDC talk on Prismata AI design |
| HPS Paper (AIIDE 2015) | http://www.cs.mun.ca/~dchurchill/pdf/aiide15_churchill_prismata.pdf | Hierarchical Portfolio Search (Best Student Paper) |
| Game AI Pro 3 Chapter | http://www.cs.mun.ca/~dchurchill/pdf/prismata_gaip3.pdf | Implementation-focused HPS guide |
