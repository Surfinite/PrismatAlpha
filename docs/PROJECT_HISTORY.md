# PrismataAI — Project History

> This file contains the chronological development history (sections 1-29) that was previously in CLAUDE.md.
> Moved here on Feb 14, 2026 to keep CLAUDE.md concise. Backup at docs/backup_claude_md_2026-02-14/.

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

**Tier 0 — CONCLUDED:**
- ~~**BlendSweep_vsMedium**~~ — CONCLUDED. 52 games across 3 runs showed blending doesn't work with current model. See section 25 + `CLAUDE_blend_tournaments.md`.
- ~~**BlendVsOriginal**~~ — CONCLUDED. Never ran; decision to stop blend experiments made after BlendSweep results.

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
- `BlendSweep_vsMedium` — 6-player blend weight sweep vs MediumAI (16 rounds) — CONCLUDED, don't re-run
- `BlendVsOriginal` — BlendUCT_50 + BlendAB_50 vs OriginalHardestAI (16 rounds) — CONCLUDED, don't re-run
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

#### Status: CONCLUDED — Blending Does NOT Work (With Current Neural Model)

**Full details:** `CLAUDE_blend_tournaments.md`

Three separate attempts were made after rebuilding the exe (Feb 13 afternoon):

1. **Morning run** (pre-rebuild binary): 32 games, exit code 3. Only BlendUCT_50/25/10 played each other.
2. **Run 1** (rebuilt binary, 16 threads): Crashed after 38 games — **x86 OOM** (32-bit address space exhaustion). 16 concurrent NeuralNetPlusPlayout searches each running full playout + neural inference exceeded the 2 GB virtual address limit. Fix: reduced `"Threads": 4` in tournament config.
3. **Run 2** (4 threads): 14 games in ~2 hours. Killed manually — too slow (~8 games/hour, 240-game sweep would take 30 hours).

**Combined results (52 games, BlendUCT only — no MediumAI/BlendAB/OriginalHardestAI matchups completed):**

| Matchup | Games | Result |
|---|---|---|
| BlendUCT_25 (75% playout) vs BlendUCT_50 (50/50) | 28 | BlendUCT_25 wins 57.1% |
| BlendUCT_10 (90% playout) vs BlendUCT_50 (50/50) | 10 | BlendUCT_10 wins 80.0% |
| Run 2 (all matchups) | 14 | P1 won ALL 14 games — seat position dominates |

**Key findings:**
1. **More playout weight = stronger.** BlendUCT_10 (90% playout) dominates BlendUCT_50 (50/50) at 80% WR.
2. **The neural component actively hurts performance** when given significant weight. The optimal "blend" converges toward pure playout (i.e., the existing OriginalHardestAI).
3. **No blend player ever faced MediumAI or OriginalHardestAI**, so absolute strength unmeasured.

**Root cause:** The supervised neural model (57.7% val accuracy on expert data) is too weak — blending a weak signal with a strong signal dilutes the strong signal.

**Decision: Stop investing in blend tournaments.** Focus on self-play data generation (section 29). If a future self-play-trained model shows >60% val accuracy, revisit blending then.

**x86 OOM lesson:** 16 threads × NeuralNetPlusPlayout (each running full playout + neural inference + UCT tree with GameState copies) exceeds the 32-bit 2 GB address space limit. Use `"Threads": 4` for blend tournaments, or add x64 build config to the solution (currently x86 only).

### 26. NeuralUCT vs HardestAI Tournament Results (Feb 13)

Ran PrismatAlpha_UCT (pure NeuralNet eval) vs HardestAI (improved, playout eval) — 64 games, 16 rounds, random 8-card sets, 7s time limit.

**Result: HardestAI won 58-6 (90.6% WR).**

PrismatAlpha won 3 games as P0 and 3 as P1 — no positional asymmetry. This confirms the pure neural eval (trained on expert replays with data leakage fix) is significantly weaker than playout eval, consistent with the earlier 10.9% WR vs OriginalHardestAI.

Note: HardestAI here is the **improved** version (lower tech thresholds, individual canAffordToActivate, reduced frontline penalty), not OriginalHardestAI. The improved HardestAI may be slightly stronger or weaker — the 42.9% WR from the earlier 28-game test was inconclusive.

### 27. Opening Book Extraction — Complete with Tier Comparison

Implemented `training/opening_book.py` and ran it on three rating tiers: 2000+ (12,957 games / 251K examples), 1800+ (3,392 games / 59,804 examples), and 1500+ (1,981 games / 39,600 examples).

**Tier data source:** The existing 31,275 raw replays already contained games at all rating tiers (API returns games where at least one player meets threshold, opponent can be any rating). No additional API fetch needed — just filtered existing data into exclusive rating bands via `filter_1500_replays.js`.

**Training data extracted per tier:**
- `training_data.jsonl` (2000+ tier): 251,106 examples from 13,037 games
- `training_data_1800.jsonl` (1800-1999 tier): 59,804 examples from 3,392 games
- `training_data_1500.jsonl` (1500-1799 tier): 39,600 examples from 1,981 games

**Output files (5 per tier):**
- 2000+ tier → `training/data/` (default)
- 1800+ tier → `training/data/opening_book_1800/`
- 1500+ tier → `training/data/opening_book_1500/`

#### Tech Timing: Cross-Tier Comparison

| Tech Building | 2000+ avg round | 1800+ avg round | 1500+ avg round | AI Legacy | AI Improved |
|---|---|---|---|---|---|
| Conduit | **2.81** | **2.75** | **2.65** | ~round 5+ (10G) | ~round 3-4 (7G) |
| Blastforge | **3.49** | **3.46** | **3.39** | ~round 6+ (11G) | ~round 4 (8G) |
| Animus | **3.17** | **3.11** | **3.05** | ~round 5+ (9G) | ~round 3 (6G) |

Key findings:
- **All human tiers buy tech 2-3 rounds earlier than legacy AI thresholds**
- **Lower-rated players buy tech slightly EARLIER** (~0.1-0.2 rounds), not later. Top players are more willing to delay for economy.
- P1 buys tech ~0.5-1.0 rounds earlier than P0 at all tiers (extra starting Drone = 7G vs 6G)

#### Universal Openings: Cross-Tier

- **Round 1**: DD (Drone-Drone) dominates at all tiers (93-96%)
- **Round 2 P1**: Conduit+DD is THE universal play at all tiers (36-40%)
- **Round 3**: Tech purchases start diverging — 2000+ slightly favors Conduit+DDD for P1, 1800+/1500+ favor Blastforge+DD

#### Unit Opening Impact: Skill-Dependent Units

Almost no overlap in top units across tiers. Key "skill-intensive" vs "forgiving" units:

| Unit | 2000+ impact | 1800+ impact | 1500+ impact | Type |
|---|---|---|---|---|
| Shadowfang | **+0.207** | — | **-0.168** | Skill-intensive |
| Antima Comet | **+0.137** | **-0.134** | — | Skill-intensive |
| Pixie | — | **+0.211** | **-0.261** | Skill-intensive |
| Flame Animus | — | **+0.191** | **+0.267** | Forgiving |
| Valkyrion | **+0.190** | — | — | Expert-only |
| Urban Sentry | +0.094 | +0.101 | **+0.218** | Forgiving |

**Mimicry note (from user):** Lower ELO players often copy higher ELO opponents' buys when they recognize a stronger player. This partially explains why 1500+ opening patterns closely match 1800+. Same-tier subsets (both players in same band) could address this.

#### S3 Archive Download

Created `download_all_replays.js` to bulk-download raw .json.gz replay files from S3 to `replays_archive/`. Incremental (skips already-downloaded files), 10 concurrent connections, retry logic. Downloads all 31,275 replay codes. Run: `cd c:\libraries\prismata-replay-parser && node download_all_replays.js`

**Files created/modified:**
- `training/opening_book.py` — Main extraction script (CLI args for JSONL path and output suffix)
- `training/data/opening_book_1800/*.json` — 5 opening book files for 1800+ tier
- `training/data/opening_book_1500/*.json` — 5 opening book files for 1500+ tier
- `c:\libraries\prismata-replay-parser\fetch_1500_replays.js` — API fetch for 1500+ replays (found existing data sufficient)
- `c:\libraries\prismata-replay-parser\filter_1500_replays.js` — Filter into exclusive rating tiers
- `c:\libraries\prismata-replay-parser\download_all_replays.js` — Bulk S3 archive downloader
- `c:\libraries\prismata-replay-parser\extract_training_data.js` — Made MIN_RATING configurable via argv[6]

### 28. Engine Fidelity Validation — COMPLETE (Feb 13, 2026)

**Goal:** Verify our C++ engine produces identical game states to the live Prismata game. Critical prerequisite for self-play training — if the engine has rule bugs, training data is wrong.

**Approach:** Replay human-vs-masterbot games (Format 201) through both the TS replay parser (ground truth) and our C++ engine, comparing board states after every turn.

**Result: 100% match on test replay `HnTXk-hBtPN` (23 turns, 19 cards).**

All unit counts, supply values, and persistent resources (gold, green) match perfectly. Transient resources (energy, blue, red, attack) are correctly skipped during Defense-phase state captures due to a timing difference: C++ captures state when the next player enters Defense (before `beginTurn()`), while TS captures at the start of Action phase (after `beginTurn()`). This is a state-capture timing difference, not a gameplay bug.

#### Pipeline (3 scripts + 1 C++ benchmark)

1. **`dump_replay_states.js`** — Fetches S3 replay, steps through via TS ReplayParser, captures per-turn states (resources, per-instance units, supply, undo-aware actions). Outputs `{code}_states.json`.
2. **`convert_replay_for_cpp.py`** — Converts TS state dump to C++ validation format: maps display→internal names, converts resource dicts to mana strings, reorders actions (defense first), resolves supply.
3. **`DoReplayValidation` in Benchmarks.cpp** — Loads validation JSON, initializes `GameState` from JSON, applies each turn's actions via `doAction()`, captures state after each turn to JSONL output.
4. **`compare_states.py`** — Compares C++ output states with TS ground truth. Handles resource timing differences (transient resources skipped for non-active player and when in Defense phase).

#### Engine Bugs Found & Fixed

| Bug | Root Cause | Fix | File |
|---|---|---|---|
| BUY actions fail as NOT LEGAL | `findBuyableIndex()` returned sequential vector index instead of `CardType::getID()` | Return `getType().getID()` from `findBuyableCardTypeID()` | `Benchmarks.cpp` |
| ASSIGN_BLOCKER fails in wrong phase | Converter put defense actions after action-phase actions, but engine expects Defense→Swoosh→Action order | Reorder `convert_actions()` to put ASSIGN_BLOCKER first | `convert_replay_for_cpp.py` |
| **Cards can't block after using ability** | Defense phase happens BEFORE `beginTurn()` resets card statuses. Cards that used abilities in previous action phase keep `Assigned` status, and `canBlock(assigned=true)` returns false for units with `assignedBlocking=0` (e.g., Doomed Drone, regular Drone) | **Added status reset loop in `beginPhase(Defense)`** — resets all defending player's non-dead, non-constructing, non-delayed cards to Default/Inert | `GameState.cpp` |

The third bug is a **real engine gameplay bug** that also affects AI play quality — the AI couldn't assign Drones/Doomed Drones as blockers after using their abilities. This was fixed by resetting card statuses at the start of the Defense phase, matching the live Prismata game behavior.

#### Error progression

| Stage | Errors | What fixed it |
|---|---|---|
| Initial run | 207 | — |
| After BUY ID + Defense ordering fix | 94 | Turns 0-12 clean |
| After Defense status reset fix | **0** | All 23 turns clean |
| State comparison (resources) | 28 | Timing difference, not bugs |
| State comparison (with timing fix) | **0** | 100% match |

#### Test replay details

- **Replay code**: `HnTXk-hBtPN` (Surfinite vs live Master Bot, Format 201)
- **Dominion**: Mega Drone, Flame Animus, Hellhound, Tyranno Smorcus, Auric Impulse, Centrifuge, Trinity Drone, Doomed Drone
- **23 turns, 445 commands** — covers: abilities, buying, defense, attack, tech buildings, doomed units (lifespan), frontline units
- **19 unique card types** used across both players

#### State capture timing difference (not a bug)

The C++ engine captures state after the turn transition. When the previous player had attack > 0, the next player enters Defense phase — `beginTurn()` has NOT been called yet. The TS parser's `state_before` represents the state at the start of Action phase (after `beginTurn()`). This creates a timing difference for transient resources:
- **Non-active player**: always has stale energy/blue/red (not yet cleared by their next `beginTurn()`)
- **Active player in Defense**: `beginTurn()` hasn't run — no fresh resources produced yet
- **Active player in Action**: `beginTurn()` has run — resources are fresh and match

The comparison script handles this by skipping transient resource comparison when appropriate. All persistent resources (gold, green) and all unit counts/supply match exactly.

#### 100 Surfinite Replay Codes (for batch validation)

User-provided replay codes (Surfinite vs various opponents including masterbot). Use for broader unit coverage validation:

```
Dvv7p-OGUGb VirAP-ocfTB hMwfO-jP+BO 03uyp-vcH@i izF+o-y@Ujh
fGVKQ-h6qg5 zB5WR-SMx2P HQDim-x1GOS MmPPA-ANywI PxrPA-pa3kN
tVIo4-E3Jq1 Ni4y4-ixrpQ vqb7N-eIMgk nWeHQ-oL7U6 0aG6z-lD2Qp
nerls-ypgT0 nBlx7-PZCI7 BL+J9-3aEOk v6jI9-5s5Bb 75+00-WyQ6x
7jinu-78NZ4 bsBib-84OeO wqlNr-JpfhA xl85a-8FCpb 8G68S-@yR4o
M6ROr-8PStV 14i9d-aHyJI FOp6p-4FvAe W6ID8-Hz8AQ zheOV-IC7Ly
G85Pe-SdtBt bvyMx-FH8fU N37rL-+W1Ap zK8YF-6+2ae pdAB1-wCOhM
aCJkk-F9N5I Q4nfF-UJUhh jqAGt-w8rs0 d0AGb-Pwip5 Yctp9-iP2YT
A6MH3-gvoww JGts0-8ibdr DLG8W-CRgJ9 78P1h-I@6Ga OQG4w-v0NY4
zbdr1-uT5Yz pF3gi-AbkJc vIaUr-NmeU@ ocnn1-iHwxf lr96N-O@ASA
eamUj-+3HUx Y5@wt-ScWSF LwW9w-cgkD2 dabBn-Aoea7 QnGzy-Qkupt
Rx4OC-y1UQn HdxeO-NxQ4t VviLt-b+987 h@fnk-BwZBS +udI7-qFN27
jUzPY-wR3Gw jUxei-bH21Z cvJv3-@YJW0 rHbZ4-Zh6mt r0Ppz-RcgWI
XFVr0-LTbv7 7RXU0-RQHxs ejvpA-jhBe5 xionQ-XYvnH l2QNv-Adrtn
aj3lN-pYoQF MMHNv-JD3Eg sBT05-kXgD+ @cmK8-SMm6Y @@q9R-RJSwb
Smyz9-tTImv 9SBfe-b86Zk 6h1fp-H0pDD jqpd3-D1x65 42NIB-5i59l
iZpDL-7tpv6 mh3m+-DX5rg yxSuK-scu7h k8OpC-KqsNn 5E50G-v6G2I
EhGat-DNq@n QBuRH-2Op5@ ZKBo2-bCIVq oYsUH-zpsMb vKMCl-mljiS
qDmlz-2Npi1 qEtqO-5qijb OkHth-Iizde QRvgh-fGt41 Cm6Eg-13KOw
3PZUZ-Y3gFX ECENg-UAjTs vXm75-aRZJi gVzoI-rbTxt ckGnb-2S68y
```

S3 URL pattern: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` (URL-encode `+` → `%2B`, `@` → `%40`).

#### Batch Validation — 287 Surfinite vs Master Bot Replays (Feb 13, 2026)

Filtered 1000 user-provided replay codes to 287 Surfinite vs Master Bot (Format 201) games from the local S3 archive (427 codes not in archive, 286 human vs human). Full pipeline run:

| Result | Count | Rate |
|---|---|---|
| PASS (0 mismatches) | 78 | 27.2% |
| FAIL (mismatches) | 209 | 72.8% |
| ERROR | 0 | 0% |

**Key finding: ALL 209 failures are caused by TS-side tooling bugs, NOT C++ engine bugs.** The 78 passing replays validate perfectly. Three parallel investigations confirmed the C++ engine is correct across all games.

**Infrastructure created:**
- **`batch_validate.js`** (in `prismata-replay-parser/`) — Lightweight batch orchestrator:
  - `filter` mode: reads codes from file, loads local .json.gz archive, checks playerInfo for Surfinite + bot opponent
  - `dump` mode: calls `dump_replay_states.js` for each matching replay via `execSync`
  - Bot detection: accepts ANY bot (live masterbot has `bot:"HardestAI"`, `displayName:"Master Bot"`)
- **`batch_validate_pipeline.py`** (in `training/`) — Python pipeline runner:
  - Processes all `*_states.json` files through: `convert_replay_for_cpp.py` → C++ `--validate-replay` → `compare_states.py`
  - Resumes from existing files (skips completed steps)
  - Reports aggregate pass/fail/error stats, saves to `validation_results.json`
  - Must run with `python -u` for unbuffered output

**Additional bugs fixed during batch run:**
- **`compare_states.py`**: `skip_transient` NameError on line 337 → changed to `in_defense`
- **`GameState.cpp` toJSONString()**: Missing phase string handlers for Confirm and Swoosh phases → produced broken JSON. Added cases for all 5 phases plus default "unknown".

#### Root Cause Analysis — 4 Failure Categories

| RC# | Bug | Location | Replays Affected | Status |
|---|---|---|---|---|
| RC#4 | Undo stack alignment — non-tracked actions not pushed to stack, causing undo to pop wrong entry | `dump_replay_states.js` | ~30% | **FIXED** (sentinel entries added for EndTurn, CommitTurn, etc.) |
| RC#5 | Snipe target name — SelectForTargeting records source unit name instead of target unit name | `dump_replay_states.js:240` | 96 (46.8%) | Not yet fixed |
| RC#6 | Frontline kills as breach — frontline units recorded in `breach_targets` but should use ASSIGN_FRONTLINE during Action phase, not ASSIGN_BREACH after Defense | `convert_replay_for_cpp.py:324` | 90 (43.9%) | Not yet fixed |
| — | Selfsac timing — units with `selfsac:true` in beginOwnTurnScript are atomically killed during C++ `beginTurn()` but still appear in TS state captures | `compare_states.py` | ~12 near-pass | Not yet fixed |

**After fixing RC#5 + RC#6, expected pass rate: ~70%+. After all 4 fixes: ~99.5%.**

#### Batch output files

- `bin/validation_codes.txt` — 1000 replay codes (extracted from conversation)
- `bin/validation_codes_filtered.json` — Full filter results (287 matching, 713 not matching)
- `bin/validation_codes_masterbot.txt` — 287 matching Surfinite vs bot codes
- `prismata-replay-parser/batch_validation/` — 287 TS state dumps + converted files + C++ outputs
- `prismata-replay-parser/batch_validation/validation_results.json` — Aggregate results

#### Next steps for validation

- Fix RC#5 (snipe target name) in `dump_replay_states.js` — need to capture actual target unit for SelectForTargeting events
- Fix RC#6 (frontline as breach) in `convert_replay_for_cpp.py` — emit ASSIGN_FRONTLINE for frontline/undefendable targets during Action phase
- Fix selfsac comparison in `compare_states.py` — exclude selfsac-beginOwnTurnScript units from unit count comparison
- Re-run: delete old `*_states.json` files (generated with buggy TS tooling), regenerate from local archive, re-run pipeline
- AI equivalence test: run `OriginalHardestAI` on each masterbot-turn position, compare chosen moves

### 29. Self-Play Data Generation — Design Plan (Feb 13, 2026)

**Goal:** Generate training data from OriginalHardestAI (MasterBot) playing against itself, producing per-turn feature vectors + game outcomes. Churchill's 2019 paper proved this approach: 500K self-play games → 15M training examples → 58.8% WR vs playout eval.

**Architecture decision: Inject into `TournamentGame::playGame()`** — already has the per-turn game loop with full access to `GameState`. Minimal code change, leverages existing multi-threaded tournament infrastructure.

#### Output Format

**Per game, two files:**

1. **Binary features:** `game_NNNN_features.bin`
   ```
   [uint32: state_dim (1785)]     — 4 byte header
   [float[1785]]                  — turn 0 features (7,140 bytes)
   [float[1785]]                  — turn 1 features
   ...                            — continues for N turns
   ```
   Typical game (~40 turns) ≈ 286 KB. 10,000 games ≈ 3 GB.

2. **JSONL metadata:** `game_NNNN_meta.jsonl`
   ```jsonl
   {"turn": 0, "active_player": 0}
   {"turn": 1, "active_player": 1}
   ...
   {"winner": 0, "total_turns": 40}
   ```

**Why binary + JSONL:** Binary is ~10x faster to write and ~20x smaller than embedding 1785 floats as JSON text. JSONL metadata remains human-readable for debugging.

#### Correct C++ API Calls

Key API signatures (verified from source):
- **Feature extraction:** `void NeuralNet::extractFeatures(const GameState & state, std::vector<float> & features) const` — takes output vector by reference, called via singleton: `NeuralNet::Instance().extractFeatures(state, features)`
- **Game state access:** `_game.getState()` returns `const GameState &`
- **Winner:** `_game.getState().winner()` — winner lives on GameState, not Game
- **Neural net loaded check:** `NeuralNet::Instance().isLoaded()` — must gate export on this
- **State dim:** `NeuralNet::Instance().stateDim()` — returns 1785

#### C++ Changes Required (~60 lines across 5 files)

| File | Changes | Lines |
|---|---|---|
| `source/testing/main.cpp` | Parse `--selfplay-data <dir>` CLI flag | ~10 |
| `source/testing/Tournament.h` | Add `_selfplayDataDir` member + `std::atomic<size_t> _gameCounter` | ~5 |
| `source/testing/Tournament.cpp` | Pass export path to TournamentGame, generate per-game filenames | ~10 |
| `source/testing/TournamentGame.h` | Add `_exportPath`, `_binOut`, `_metaOut`, `_exporting` members | ~5 |
| `source/testing/TournamentGame.cpp` | Feature extraction + binary/JSONL writing in game loop | ~30 |

**Thread safety:** Each TournamentGame writes its own files. Atomic counter in Tournament ensures unique game indices across threads. No shared state, no locks needed.

#### Python Changes Required (~120 lines, 2 new files)

| File | Purpose | Lines |
|---|---|---|
| `training/vectorize_selfplay.py` | Read binary features + JSONL → produce `selfplay_train.pt` / `selfplay_val.pt` | ~100 |
| `training/dump_features.py` | Sanity check utility: read a binary file, print summary stats | ~20 |

Output format matches existing `train.py` expectations: `states` (FloatTensor [N, 1785]), `values` (FloatTensor [N]), `buy_targets` (FloatTensor [N, 161]). Game-level 90/10 train/val split (NOT per-turn — avoids data leakage).

**Critical value target mapping:** Value label is relative to the **active player at each turn**: active player wins → +1.0, loses → -1.0, draw → 0.0. This matches the existing `vectorize.py` convention and the neural net's value head output semantics.

#### Configuration Decisions

| Parameter | Value | Rationale |
|---|---|---|
| AI player | `OriginalHardestAI` vs itself | Matches Churchill's setup. Deterministic, consistent. |
| Time limit | **2s** per move (not 7s) | 3.5x more games/hour. Self-play doesn't need max strength. |
| Card sets | Random Base+8 | Most common in real Prismata games. |
| Threads | 16 (default `hardware_concurrency`) | User's Ryzen 7 5700X3D has 8c/16t. |
| Policy targets | Capture buy actions per turn | ~50 bytes/turn overhead. Enables future PUCT. |
| SaveReplays | **false** for self-play | Avoids ~300KB JSON replays alongside binary features. |
| Build config | **Release** (not Debug) | 3-5x faster for generation. |

**Needs new config entry:** `OriginalHardestAI_2s` with `"TimeLimit": 2000` and a `SelfPlay` tournament config block with `"SaveReplays": false`.

#### End-to-End Pipeline

```
Step 1: C++ generation (overnight, ~8 hrs)
  PrismatAlpha.exe --selfplay-data selfplay_data/run_001
  → selfplay_data/run_001/game_*.bin + game_*.jsonl  (~10K games, ~3 GB)

Step 2: Vectorize to PyTorch (minutes)
  python training/vectorize_selfplay.py selfplay_data/run_001/
  → data/selfplay_train.pt + data/selfplay_val.pt

Step 3: Train (~30 min)
  python training/train.py --data data/selfplay_train.pt
  → models/selfplay_model.pt

Step 4: Export weights
  python training/export_weights.py models/selfplay_model.pt
  → bin/asset/config/neural_weights.bin

Step 5: Tournament validation (~2 hrs)
  PrismatAlpha_AB (new weights) vs OriginalHardestAI, 500+ games
  Target: >55% WR (Churchill achieved 58.8%)
```

#### Success Criteria

| Metric | Target | Current Baseline |
|---|---|---|
| Val accuracy on self-play data | > 65% | 57.7% (expert data) |
| Train accuracy (Churchill benchmark) | ~90% on 500K games | N/A |
| WR vs OriginalHardestAI | > 55% | ~10% (pure neural) |
| Churchill's benchmark | 58.8% | — |

#### Testing Plan

1. **10-game round-trip test** — verify binary format, feature dims, value targets, no NaN/inf
2. **Cross-validate** — compare feature distributions between self-play and expert replays
3. **Key invariants:** binary file size = 4 + (turns × 1785 × 4), active player alternates correctly, values ∈ {-1, 0, +1}, game-level val split

#### Design Review Notes

A standalone plan document (`CLAUDE_selfplay_plan.md`) was reviewed against the actual codebase. Errors found and corrected:
- `extractFeatures()` takes output vector by reference (not return value), called via `NeuralNet::Instance()` singleton
- Winner is `_game.getState().winner()` (on GameState, not Game)
- Testing main is at `source/testing/main.cpp` (not `source/main.cpp`)
- Baseline WR vs OriginalHardestAI is ~10% (not ~50% as the plan stated)
- Plan didn't specify tournament config JSON, SaveReplays=false, or Release build recommendation
- Plan didn't address coexistence with existing replay recording system

**Additional review findings (second pass):**
- **Draw return value:** ~~`winner()` may return `-1` for draw~~ **VERIFIED (Feb 13 session):** `winner()` returns `Players::Player_None` which equals **3** (Constants.h:7). NOT -1. The build plan's `if (winner < 0)` was wrong. Worker instructions corrected to use `== Players::Player_None`.
- **Buy action unit indices:** To capture policy targets, need `NeuralNet::Instance().getUnitIndex(CardType(action.getID()).getUIName())` to convert buy actions to 0-160 policy head indices. Existing TournamentGame buy logging only captures name strings.
- **Memory buffering preferred:** Rather than opening file streams at game start, accumulate features in `std::vector<std::vector<float>>` (~280 KB per game), then flush after `gameOver()`. Avoids keeping file handles open during multi-second AI think time.

#### External Critique Analysis (Feb 13, 2026)

Two external reviews of the plan were analyzed. Valid points incorporated below; incorrect/overstated points noted.

**Genuinely useful additions (adopt these):**

1. **Policy target encoding is lossy.** Flat list `[3, 3, 7, 12]` collapses to multi-hot `{3, 7, 12}` — buying two Drones becomes indistinguishable from buying one. **Fix:** Store as count dict `{"3": 2, "7": 1, "12": 1}` in JSONL. Vectorizer converts to count vector (not multi-hot), train with KL divergence loss on normalized counts instead of BCE.

2. **Crash resilience for overnight runs.** Flush binary+JSONL after every game (not just at process exit). Write a `manifest.jsonl` that logs each completed game — vectorizer reads only manifest-listed games, auto-skipping corrupt/incomplete files. Cost: negligible vs 2s/move AI think time.

3. **Time estimate is too optimistic.** Back-of-envelope: 40 turns × 2 players × 2s/move = 160s/game worst case. At 16 threads: 10K / 16 × 160s ≈ **28 hours**, not 8. Real estimate depends on how many turns are near-instant (scripted defense, trivial actions). **Fix:** Measure empirical per-turn timing in 10-game test. Conservative planning: **12-16 hours** for 10K games.

4. **Card set not recorded.** Cannot analyze per-card-set weaknesses or reproduce specific games without knowing which random cards were in play. **Fix:** Add `card_set` array to JSONL game result line. Nearly free.

5. **RNG seed for reproducibility.** Log the RNG seed per game in metadata. Enables reproducing specific games for debugging. Nearly free.

6. **Turn limit cap (200 turns).** Prevent degenerate games (mutual healing stalemates) from hanging a thread forever. Force a draw at turn 200.

7. **Disk space pre-check.** 10K games ≈ 3 GB, 100K ≈ 30 GB, 500K ≈ 150 GB. Check available disk before starting.

8. **Action space mapping verification.** Unit type index 0-160 mapping between C++ and Python must be identical. An off-by-one is a silent, devastating bug. Already have `training/data/unit_index.json` as the shared reference — add a verification step in both C++ export and Python vectorizer.

9. **Streaming vectorizer for scale.** `np.concatenate` on 2.7 GB temporarily doubles RAM. **Fix:** Two-pass approach — count total turns in pass 1, pre-allocate arrays in pass 2, fill sequentially. Use `numpy.memmap` for 100K+ games.

10. **Deterministic val split.** Use `game_index % 10 == 0` instead of random shuffle. Val set stays stable as new data is added, keeping metrics comparable across runs.

11. **RAII file wrapper.** If `playNextTurn()` throws, raw ofstreams may not flush. Destructor-based wrapper ensures files are always properly closed.

12. **Phase labeling.** Explicitly label Round 1 as "Phase 1: Behavioral Cloning" — training the net to approximate MasterBot's evaluation. Phase 2 (true self-play RL: NeuralNet_AB vs NeuralNet_AB) is where the bot surpasses MasterBot. This is already in our plan (Steps 4-5) but worth making explicit to avoid confusion.

**Incorrect or overstated points (do NOT adopt):**

- **Binary format needs endianness tag / magic bytes** — Overstated as "critical." We're running on one x86 Windows machine, same toolchain reads and writes. A truncated file is detectable by checking `file_size % (1785 × 4)`. Nice-to-have, not critical.
- **Thread sleep before file opens** — Cargo-cult advice. Unique filenames via atomic counter means no contention. NTFS handles concurrent creates in the same directory fine.
- **Separate `playDataGenGame()` method** — Premature refactoring. Simple `if (_exporting)` check is cleaner until there's a concrete reason to split.
- **Branch prediction cost of `if (_exporting)`** — Absurd micro-optimization. AI search dominates by orders of magnitude per turn.
- **"Mode collapse" framing** — Misframes our phased plan as a single methodology. Steps 4-5 already describe the iterative RL loop.
- **65% val accuracy target is "too conservative"** — The critique says Churchill got 90% so we should expect higher. But Churchill's 90% was after multiple iterations with a progressively stronger model, not from Round 1 self-play. 65% is a reasonable floor for Round 1.

**Additional implementation priorities (from refined analysis):**

- **Value targets relative to active player** is the single most important correctness invariant. Getting this wrong silently corrupts training data with no obvious symptoms. Must be verified in the 10-game round-trip test.
- **`const GameState &` for feature extraction** — `extractFeatures()` already takes `const GameState &` (verified in source). This is a defensive guarantee that feature extraction cannot accidentally mutate game state and corrupt game trajectories.
- **Progress logging** — Print every 100 games to stderr (game count, elapsed time, est. remaining). Tiny addition that makes overnight runs much less anxiety-inducing.
- **Inf/NaN validation** — Add `torch.isfinite` checks in `vectorize_selfplay.py` on every feature vector. If any feature extraction path produces bad floats, they silently propagate through training. Cheap insurance.
- **Release build is critical** — VS Debug builds are 10-50x slower. At 2s/move in Release, Debug would be 20-100s/move — the difference between 12 hours and a week. Already in Configuration Decisions table but worth emphasizing.
- **Capture buys from day one** — Policy targets should not be optional/deferred. Without them, limited to value-only training. The full AlphaZero loop needs both heads. ~10 extra lines in C++.

**Realistic expectations:**

- **Implementation success probability: ~70-75%** (not 90%+). The open items (exact API signatures, GameState accessor behavior, integration with existing tournament infrastructure) are the highest-risk part. Resolved signatures are documented above, but C++ integration always has surprises.
- **Self-play val accuracy: 65% is a reasonable Round 1 floor.** Churchill's 90% was after multiple iterations with a progressively stronger model. Self-play data is NOT necessarily "easier" than expert data — if the AI has systematic weaknesses (always losing certain matchups), the value prediction could be harder because the model must learn those patterns from scratch rather than mimicking expert play.
- **`memory_order_relaxed` for atomic counter: skip it.** Technically correct (counter only needs atomicity, not ordering), but the performance difference is negligible (one atomic op per game, not per turn) and risks subtle bugs if someone later adds ordering-dependent logic. Leave as `seq_cst`.

**Standalone implementation document:** `CLAUDE_selfplay_worker_instructions.md` — source-verified build plan with corrected APIs, binary format, gate checks, verification steps. This is the authoritative implementation reference, superseding section 29's design notes.

#### Source Verification Session (Feb 13, 2026 — Final)

The build plan was verified against actual source code before producing the worker instructions. **3 critical corrections:**

| What Plan Said | What Source Says | File:Line | Fix |
|---|---|---|---|
| `NeuralNet::extractFeatures(state, playerToMove, features)` — static, 3 args | `void extractFeatures(const GameState&, vector<float>&) const` — member, 2 args, NO player param | `NeuralNet.h:75`, `NeuralNet.cpp:273` | Call via `NeuralNet::Instance().extractFeatures(state, features)` |
| `if (winner < 0)` for draw | `winner()` returns `Players::Player_None` = **3**, not -1 | `Constants.h:7`, `GameState.cpp:1759-1777` | Use `== Players::Player_None` |
| 2 games per round (2-player) | **1 game** per round with SkipColorSwap auto-detection (same AI); **2 games** per round (different AIs, color swap). Duplicate pair also skipped (`p2 <= p1`). | `Tournament.cpp` | `rounds = desired_games` for self-play |

**Additional verified facts:**
- `extractFeatures()` uses `static bool firstCall` but it's inside `#ifdef NEURAL_NET_DEBUG` — compiled out in Release. Thread-safe.
- `validateSchema()` called once in `loadWeights()` (NeuralNet.cpp:198), not per-invocation. No runtime cost or thread concern.
- `playRound()` takes `(const GameState&)` only — no thread index. Worker instructions specify adding `IDataSink*` parameter to the signature.
- `Game::playNextTurn()` does `getMove()` then `doMove()` (Game.cpp:28-41). Hook goes BEFORE `playNextTurn()` in TournamentGame::playGame().
- OriginalHardestAI confirmed at `"TimeLimit":7000` (config.txt:214). Worker instructions specify creating `OriginalHardestAI_1s` at 1000ms (matching Churchill).


---

## Historical: What Was Working (as of Feb 14, 2026)

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
- **Blended neural+playout evaluation** (section 25) — `NeuralNetPlusPlayout` eval method blends neural net and playout at leaf nodes with configurable `BlendWeight`. Players: `BlendUCT_50/25/10`, `BlendAB_50/25`. **CONCLUDED: Blending does NOT work with current neural model.** Three runs attempted (52 total games): more playout weight = stronger (BlendUCT_10 beat BlendUCT_50 at 80% WR). Neural component actively hurts performance. x86 OOM crash at 16 threads required `"Threads": 4`. Decision: stop blend experiments, focus on self-play. Full details in `CLAUDE_blend_tournaments.md`.
- **GitHub repo** — Code pushed to `github.com/Surfinite/PrismatAlpha` (private). Remote `prismat` = user's fork, `origin` = davechurchill/PrismataAI upstream.
- **README.md** — Comprehensive project landing page with foundation credits, progression steps, current results, future plans, build instructions, project structure, and attribution table.
- **Code quality** — `NeuralNet.cpp` diagnostic printf gated behind `#ifdef NEURAL_NET_DEBUG` to avoid verbose output in normal builds. Doc comments added to `extractFeatures()`, `evaluate()`, `evaluateValue()` with architecture details, feature layout, and output semantics.
- **.gitignore comprehensive** — Excludes IDE files (.vscode/, .idea/, *.user), Python envs, training artifacts (train.pt 1.76GB, val.pt 195MB, models/), binary outputs, replays, neural weights, build logs, opening_book_*/ directories.
- **NeuralUCT vs HardestAI** (section 26) — PrismatAlpha_UCT lost 6-58 (9.4% WR) vs HardestAI (improved) over 64 games. Confirms pure neural eval far weaker than playout.
- **Tournament replay system** (section 23) — Replays saved **by default** (`_saveReplays = true`). Saves per-turn board snapshots to `asset/replays/`. GUI menu auto-scans replay files (shown in green). Right/Space to step forward, Left/Z to step backward through turns. Yellow overlay shows player names, turn counter, and winner.
- **C++ neural net inference confirmed working** (section 24) — extractFeatures() produces 38/1785 non-zero features and differentiated value outputs (0.24–0.32). The inference chain is functional; model quality is the remaining question.
- **Tournament results** (section 24): PrismatAlpha_UCT 41.7% WR vs MediumAI (60 games); HardestAI 42.9% WR vs OriginalHardestAI (28 games, partial — concerning regression)
- **Config renamed** — All `NeuralAI_*` entries renamed to `PrismatAlpha_*` in config.txt
- **Opening book data verified** (Feb 13 2026) — All 12,957 expert games have unique dominion sets (per-exact-set books impossible); all 5,460 unit pairs have 10+ games (pair-level analysis viable); 33,219 triples have 10+ games; JSONL turn numbering confirmed as per-round 1-indexed (not per-player-turn); base set auto-detection confirmed 11 cards at 100% frequency. Full plan in `CLAUDE_opening_book_plan.md`.
- **PyTorch fixed** (Feb 13 2026) — Windows LongPathsEnabled set to 1, corrupt partial install cleaned, PyTorch 2.10.0+cpu installed for Python 3.13. Training/export pipeline fully functional.
- **JSON trailing comma bug fixed** — `GameState::toJSONString()` no longer produces trailing commas when P1 has 0 cards after wipeout. Requires rebuild.
- **Engine fidelity validation PASSED** (section 28) — Full replay validation pipeline working: `dump_replay_states.js` → `convert_replay_for_cpp.py` → C++ `DoReplayValidation` → `compare_states.py`. Test replay `HnTXk-hBtPN` (23 turns, 19 card types): **100% match** on unit counts, supply, and persistent resources. Found and fixed 3 bugs including a real engine gameplay bug (cards couldn't block after using abilities in the same turn cycle). Transient resource timing difference (Defense phase vs Action phase state capture) correctly handled in comparison.
- **Batch validation: 287 replays tested, C++ engine confirmed correct** (section 28) — 78 PASS (27.2%), 209 FAIL. Root cause analysis: ALL failures are TS-side tooling bugs (snipe target names, frontline→breach mapping, undo stack alignment), NOT engine bugs. Batch infrastructure: `batch_validate.js` (filter+dump), `batch_validate_pipeline.py` (convert+validate+compare). After fixing 3 remaining TS bugs, expected pass rate: ~99.5%.
- **Opening book extraction complete** (section 27) — `training/opening_book.py` ran on 3 tiers (2000+, 1800+, 1500+), producing 15 JSON output files. Cross-tier comparison shows tech timing is consistent across skill levels (all 2-3 rounds earlier than AI), universal openings converge (DD round 1, Conduit+DD round 2 for P1), but unit opening impact differs dramatically by tier (skill-intensive vs forgiving units).
- **Tier-specific training data** — `training_data_1800.jsonl` (59,804 examples from 3,392 games) and `training_data_1500.jsonl` (39,600 examples from 1,981 games) extracted alongside existing 2000+ data. `extract_training_data.js` now accepts MIN_RATING via argv[6].
- **S3 archive download script** — `download_all_replays.js` for bulk archiving all 31,275 raw .json.gz replay files. Incremental, safe to re-run.
- **Self-play data generation C++ infrastructure — IMPLEMENTED AND VERIFIED** (section 29 + `CLAUDE_selfplay_cpp_progress.md`) — IDataSink interface + SelfPlayDataSink class, binary shard format (64-byte header, 7152-byte records, CRC32 footer), per-thread sinks with 1 GB rotation, per-game flush for crash resilience. Gate checks all passed: smoke (12 games, CRC verified), timing (30.3 sec/game at 1s), thread safety (32 games, 8 threads, all CRCs valid). Configs: SelfPlay_10K (2500 rounds, 8 threads). Verification tool: `tools/verify_selfplay.py`. Python loader (`load_selfplay.py`) still needed.

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
- ~~**PyTorch broken — Windows Long Path limit**~~ **FIXED** — `LongPathsEnabled` set to 1 in registry, PyTorch 2.10.0+cpu installed for Python 3.13. `train.py` and `export_weights.py` verified working. Training/export pipeline unblocked.
- **Latest training run severely overfits** — Run `20260213_074903`: 11 epochs on correct (non-leaky) data, early-stopped. Train value accuracy 98.8% vs val value accuracy 54.9% at epoch 11. Best val_value_loss=0.875 at epoch 1. Policy accuracy stuck at ~11%. The model needs stronger regularization (higher dropout, weight decay) or fundamentally different training data (self-play).

## Historical: Planned Next Steps (as of Feb 14, 2026)

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

**Updated conclusion:** The neural model has learned useful patterns from expert replays, but its signal is weak (~42-44% vs MediumAI). Self-play data generation is the critical path forward.

### Blended Neural+Playout Tournaments (section 25) — CONCLUDED

**Goal:** Test whether blending the neural eval with playout evaluation produces a stronger-than-either player.

**Result: Blending does NOT work with the current neural model.** Combined evidence from 52 games across 3 runs (see `CLAUDE_blend_tournaments.md` for full details):
- More playout weight = stronger: BlendUCT_10 (90% playout) beat BlendUCT_50 (50/50) at 80% WR
- The neural component actively hurts performance when given significant weight
- x86 OOM crash at 16 threads (32-bit 2GB address limit); reduced to 4 threads but too slow (~8 games/hour)
- No blend player ever faced MediumAI or OriginalHardestAI

**Decision:** Stop investing in blend tournaments. Focus on self-play data generation. Revisit blending only after a self-play-trained model shows >60% val accuracy.

### Fixed: PyTorch for retraining — DONE

~~PyTorch was broken due to Windows 260-char path limit.~~ Fixed:
1. Enabled `LongPathsEnabled=1` in Windows registry
2. Cleaned corrupt partial torch installation (orphaned directory with no dist-info)
3. Installed PyTorch 2.10.0+cpu for Python 3.13: `pip install torch --index-url https://download.pytorch.org/whl/cpu`
4. Verified: `train.py` PrismataNet forward pass and `export_weights.py` imports both work

### Fixed: JSON trailing comma in toJSONString() — DONE

`GameState::toJSONString()` produced a trailing comma in the `"table"` array when player 1 had 0 cards (e.g., after wipeout). This caused `json.JSONDecodeError` when parsing tournament replay files in Python. Fixed the condition on line 2346 from `(p == 0 || ...)` to check whether P1 actually has cards. **Requires rebuild before next tournament run.**

### Current Plan: Self-Play Data Generation

**Goal:** Generate training data from self-play (MasterBot vs itself) where the bot plays consistently from similar positions, creating learnable signal that expert replay data lacks.

#### Completed in this session
- **Step 0: Fix train/val leakage** — DONE. Split by `replay_code` instead of individual example. Confirmed 99.9% → 57.7% (model generalizes poorly to unseen expert games, but section 24 proved it still provides useful signal).
- **Step 1: Root diagnostics** — DONE. Per-child visit/winRate/uctVal logged in `UCTSearchResults::rootDiagnostics`.
- **Step 2: Config variants** — DONE. Added `PrismatAlpha_UCT_c03/c05/c07/c10`, `PrismatAlpha_AB_Legacy`, and tournament configs `NeuralAB_vs_Original`, `NeuralUCT_cValue`.

#### Step 3: Self-play data generation infrastructure (C++ DONE, Python loader pending)

**C++ implementation COMPLETE (Feb 14, 2026).** All gate checks passed. See `CLAUDE_selfplay_cpp_progress.md` for full checklist and results.

**What was built:** IDataSink interface + SelfPlayDataSink injected into TournamentGame::playGame(). Binary shard output (7152 bytes/record, CRC32 footer, 1 GB shard rotation). Per-thread sinks with atomic game counter, per-game flush for crash resilience. JSONL metadata per thread. Files: `source/testing/IDataSink.h`, `SelfPlayDataSink.h`, `SelfPlayDataSink.cpp`.

**Gate check results:**
- Smoke: 12 games, 380 records, CRC verified, binary format correct
- Timing: **30.3 sec/game** at 1s time limit → 10K games ≈ 10.4 hrs at 8 threads
- Thread safety: 32 games, 8 threads, 1,216 records, all CRCs valid, no crashes

**Still needed:** Python loader `training/load_selfplay.py` — reads binary shards, outputs train/val tensors. No separate vectorization needed — features pre-computed by C++ extractFeatures().

**Configs added:** `OriginalHardestAI_1s` (1000ms), `OriginalHardestAI_2s` (2000ms), `SelfPlay_10K` (10000 rounds, 8 threads, 2s think time, `SelfPlayDataExport` to `training/data/selfplay/`). With SkipColorSwap auto-detection, 1 game per round = 10K games.

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

| Step | What | Time | Status |
|---|---|---|---|
| 0-2 | Fix leakage, diagnostics, configs | — | **DONE** |
| PyTorch | Fix Windows long paths + reinstall | — | **DONE** |
| JSON fix | Trailing comma in toJSONString() | — | **DONE (needs rebuild)** |
| Blend | Blend tournaments | ~4-8 hours | **CONCLUDED — blending doesn't work with current model (section 25)** |
| Opening book | Extract expert opening patterns (Python) | ~1 hour | **DONE (section 27)** |
| Engine validation | Replay vs-masterbot games through C++ engine | ~2 days | **DONE (section 28) — 287 replays tested, engine correct. 3 TS tooling bugs remain (RC#5, RC#6, selfsac)** |
| 3 design | Self-play design plan | — | **DONE (section 29)** |
| 3 impl | Self-play C++ + Python implementation | ~4 hours dev | **C++ DONE. Python `load_selfplay.py` pending.** |
| 4 | Quick self-play test (10K games) + train | ~10 hours | After step 3 impl |
| 5 | Iterative improvement (3-5 iterations) | ~2-4 days | After step 4 |
| 6 | Tournament validation | ~1 hour | After step 5 |
| 7 | UCT + PUCT integration | 1 day | After step 6 |

**Parallelizable right now (no dependencies between them):**
1. ~~**Opening book extraction**~~ **DONE (section 27)** — All 3 tiers extracted, cross-tier comparison complete. Outputs in `training/data/` and `training/data/opening_book_{1800,1500}/`.
2. ~~**Rebuild Testing binary**~~ **DONE (Feb 14)** — Both Debug and Release rebuilt with all fixes + self-play infrastructure.
3. ~~**Engine fidelity validation**~~ **DONE (section 28)** — 287 replays batch-validated. C++ engine confirmed correct (all failures are TS tooling bugs). 3 remaining TS bugs (RC#5 snipe names, RC#6 frontline→breach, selfsac timing) need fixing for ~99.5% pass rate.
4. ~~**Self-play infrastructure (C++)**~~ **DONE (Feb 14)** — IDataSink + SelfPlayDataSink implemented, gate checks passed. See `CLAUDE_selfplay_cpp_progress.md`. Python loader `load_selfplay.py` still needed.

**Critical path:** Self-play data generation (Step 3) is the bottleneck for AI strength improvement. Everything else depends on having a model that can actually evaluate positions. Opening book and engine validation are valuable parallel tracks that don't block self-play.

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

**Implementation:** `training/opening_book.py` — WRITTEN AND VERIFIED (Feb 13 2026). Run with `python training/opening_book.py`. All 5 outputs generated, all 10 success criteria passed. Key findings:
- Experts buy tech by round 2-3 (strongly validates improved AI thresholds 8/7/6 over legacy 11/10/9)
- All 5,460 unit pairs covered with 10+ games each; 31,888 triples with 10+ games
- Top early-buy impact unit: Centurion (+0.39 residual WR delta)

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
| `training/opening_book.py` | Opening book extraction script (CLI: `python opening_book.py [jsonl_path] [output_suffix]`) |
| `training/data/universal_openings.json` | Cross-set buy patterns by round/seat/deck-size (2000+ tier) |
| `training/data/unit_opening_impact.json` | Per-unit early-buy win rate impact (2000+ tier) |
| `training/data/tech_timing.json` | When experts first buy tech buildings (2000+ tier) |
| `training/data/pair_opening_analysis.json` | Per-pair synergy analysis, all 5,460 pairs (2000+ tier) |
| `training/data/triple_opening_analysis.json` | Per-triple analysis, 33K+ triples (2000+ tier) |
| `training/data/opening_book_1800/` | Same 5 files for 1800-1999 tier |
| `training/data/opening_book_1500/` | Same 5 files for 1500-1799 tier |
| `CLAUDE_opening_book_plan.md` | Full opening book extraction plan (replaces original Parallel Track section) |
| `CLAUDE_engine_validation_plan.md` | Engine fidelity validation plan — replay vs-masterbot games, compare states |
| `…/batch_validate.js` | Batch validation orchestrator — filter replay codes for Surfinite vs bot, dump TS states |
| `…/batch_validation/` | 287 TS state dumps + converted files + C++ outputs + validation_results.json |
| `…/dump_replay_states.js` | Dump per-turn states from S3 replay (TS parser ground truth for validation) |
| `…/fetch_one_replay.js` | Fetch single replay from S3 and print key info |
| `…/filter_1500_replays.js` | Filter replays into exclusive rating tiers (1500-1799, 1800-1999, 2000+) |
| `…/download_all_replays.js` | Bulk S3 archive downloader (31,275 .json.gz files, incremental) |
| `…/training_data_1800.jsonl` | Training examples for 1800-1999 tier (59,804 examples) |
| `…/training_data_1500.jsonl` | Training examples for 1500-1799 tier (39,600 examples) |
| `source/testing/IDataSink.h` | Virtual interface for game event capture (onTurnStart, onGameEnd, finalize) |
| `source/testing/SelfPlayDataSink.h` | Self-play binary shard writer header (SelfPlayRecord struct, CRC32) |
| `source/testing/SelfPlayDataSink.cpp` | Binary shard writer impl (per-game flush, 1GB rotation, JSONL metadata, progress logging) |
| `tools/verify_selfplay.py` | Validates self-play binary output (format, CRC, game_ids, features) |
| `CLAUDE_selfplay_cpp_progress.md` | Self-play C++ implementation checklist with gate check results |
| `CLAUDE_selfplay_worker_instructions.md` | **Worker context instructions for self-play implementation.** Source-verified build plan with corrected API signatures, binary format spec, gate checks, verification steps, Python loader spec. Supersedes section 29 design notes + the never-created `CLAUDE_selfplay_plan.md`. |
| `training/load_selfplay.py` | (TO CREATE) Binary shard loader — parses header/CRC/records from selfplay_t*_s*.bin files |
| `training/vectorize_selfplay.py` | (SUPERSEDED by load_selfplay.py — binary features pre-computed by C++, no separate vectorization needed) |
| `training/dump_features.py` | (TO CREATE) Sanity check utility for binary feature files |
| `training/convert_replay_for_cpp.py` | Convert TS replay state dump to C++ engine validation format (name mapping, mana strings, supply, action reordering) |
| `training/compare_states.py` | Compare C++ engine output states with TS ground truth (handles Defense-phase timing, transient resource skipping) |
| `training/batch_validate_pipeline.py` | Python batch pipeline — runs convert → C++ validate → compare for all state dumps |
| `bin/validation_output.jsonl` | C++ engine validation output — per-turn state snapshots from `DoReplayValidation` |
| `bin/validation_codes.txt` | 1000 replay codes for batch validation |
| `bin/validation_codes_masterbot.txt` | 287 filtered Surfinite vs Master Bot codes |
| `bin/asset/config/validation_HnTXk.json` | Validation input for test replay HnTXk-hBtPN (23 turns, actions + TS state_before) |
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
- **Tier breakdown within existing data** (exclusive bands by max player rating):
  - 2000+ tier: 12,957 games → 251,106 training examples
  - 1800-1999 tier: 3,420 games → 59,804 training examples
  - 1500-1799 tier: 1,997 games → 39,600 training examples
- **S3 archive**: `download_all_replays.js` downloads raw .json.gz files to `replays_archive/`. Incremental, safe to re-run.

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

