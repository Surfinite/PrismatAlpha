# PrismatAlpha

An AI improvement project for [Prismata](https://store.steampowered.com/app/490220/Prismata/), the turn-based strategy card game by [Lunarch Studios](http://lunarchstudios.com/). The goal is to push the AI beyond the original Masterbot (~1200 Elo) toward expert-level play (2000+ Elo) using neural network evaluation and self-play reinforcement learning, following the approach outlined in [Churchill & Campbell's 2019 ML paper](https://skatgame.net/mburo/aiide19ws/paper-3.pdf).

## Foundation

This project is built on **[PrismataAI](https://github.com/davechurchill/PrismataAI)** by [David Churchill](https://davechurchill.ca/) (Memorial University of Newfoundland / Lunarch Studios), the open-source C++ AI engine that powers the Masterbot in the retail game. Churchill published the code under a [CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) license in 2020.

The original engine includes:
- **Prismata_Engine** — Full game rules simulation
- **Prismata_AI** — The retail Masterbot: Stack Alpha-Beta search with Hierarchical Portfolio Search (branching factor 5, playout evaluation at leaf nodes)
- **Prismata_GUI** — SFML-based GUI for playing against the AI
- **Prismata_Testing** — Tournament runner and benchmarks

### Key Publications

| Paper | Year | Venue |
|---|---|---|
| [Hierarchical Portfolio Search: Prismata's Robust AI Architecture](http://www.cs.mun.ca/~dchurchill/pdf/aiide15_churchill_prismata.pdf) | 2015 | AIIDE (Best Student Paper) |
| [Hierarchical Portfolio Search in Prismata](http://www.cs.mun.ca/~dchurchill/pdf/prismata_gaip3.pdf) | 2017 | Game AI Pro 3 |
| [GDC 2017: Building the AI for Prismata](https://youtu.be/sQSL9j7W7uA) | 2017 | GDC |
| [Machine Learning State Evaluation in Prismata](https://skatgame.net/mburo/aiide19ws/paper-3.pdf) | 2019 | AIIDE Workshop |

## What We've Done

### Card Library Update
The engine's unit database was years out of date. We fetched 500+ expert replays from the [Prismata replay API](https://prismata.fandom.com/wiki/Replay_API), extracted current unit definitions, added 8 missing competitive units, updated balance for 41 existing units, and verified all 105 competitive non-base-set units match the final balance patch (January 14, 2019).

### Heuristic Bug Fixes
Diagnosed and fixed 5 issues in the Masterbot's buy heuristics that suppressed attacker purchasing:
1. **Copy-paste bug** in TechHeuristic — `hasBlastforge`/`hasAnimus` both checked the wrong type
2. **Tech gold thresholds too high** — lowered from 11/10/9 to 8/7/6 for earlier tech transitions
3. **Cumulative ability cost check** — changed to per-card check (also fixes the known "Tyranno Smorcus deadlock")
4. **Frontline penalty 100,000x** — reduced to 5x (frontline units were effectively unbuyable)
5. **Debug stderr spam** — removed from hot path

Original behavior preserved via `"legacy": true` config flag. `OriginalHardestAI` available as a stable baseline.

### Neural Network Integration
Built a C++ neural network inference engine trained on expert replay data:
- **Architecture:** Input(1785) → Linear(512) → 2x ResBlock(512) → policy head (161 unit types) + value head (tanh, [-1,1])
- **Training data:** 251,106 examples from 13,037 expert games (2000+ Elo, standard ranked)
- **Feature vector:** 161 unit types × 11 features + 14 global features (resources, turn, active player)
- **Integration:** Plugs into both Alpha-Beta and UCT search as a leaf evaluation function
- **Blended evaluation:** `NeuralNetPlusPlayout` mode mixes neural value with playout score at configurable weight

### Expert Replay Data Pipeline
- **31,275 raw replays** fetched from [prismata-stats](https://prismata-stats.web.app/) API
- **13,157 filtered expert games** (2000+ Elo, Format 200, 20s+ time control, human vs human)
- Per-turn extraction with full state capture: resources, per-instance unit data, supply, blueprints, undo-aware actions
- Incremental pipeline — safe to re-run without reprocessing
- Uses [prismata-replay-parser](https://github.com/plampila/prismata-replay-parser) (TypeScript) for game state reconstruction

### GUI Improvements
- Higher resolution (2133x1200), card images for all new units
- Debug panel with AI confidence display, unit value labels (heuristic + neural), comparison AI
- Auto-play mode, tournament replay viewer, F5 state dump
- 5 test scenarios including new unit showcases

### Tournament Infrastructure
- Multi-threaded tournament runner with per-turn state snapshots
- Replay save/load system (GUI auto-scans replay files)
- Fixed-set testing for reproducible benchmarks
- Tournament configs for systematic AI comparison

## Current Results

| Matchup | Games | Win Rate |
|---|---|---|
| PrismAlphaBot (neural UCT) vs MediumAI | 60 | 41.7% |
| PrismAlphaBot (neural UCT) vs HardestAI (playout) | 64 | 9.4% |
| BlendUCT_50 vs BlendUCT_25 | 28 | 58.3% (50% blend wins) |
| HardestAI (improved) vs OriginalHardestAI | 28 | 42.9% (inconclusive) |

The neural evaluation provides real strategic signal (dramatically beats Random and Easy AI) but is much weaker than the Masterbot's playout evaluation. Blending neural + playout shows promise — the 50/50 blend outperforms the 25/75 blend, suggesting the neural component adds value.

For reference, Churchill's 2019 paper achieved **58.8% WR** with a learned evaluation trained on 500K self-play games. Our model is trained on 13K expert replays — self-play data should close the gap.

## Future Plans

1. **Fix PyTorch installation** — Windows long path limit blocking retraining
2. **Complete blend tournaments** — BlendUCT/AB variants vs OriginalHardestAI baseline
3. **Self-play data generation** — Run Masterbot vs itself, capture (state, outcome) pairs at scale
4. **Retrain on self-play data** — Churchill got ~90% accuracy on self-play vs our 57.7% on expert data
5. **Iterative self-play RL** — AlphaZero-style: neural Masterbot vs itself → retrain → repeat
6. **Policy-guided UCT (PUCT)** — Use neural policy head for move ordering in MCTS
7. **Opening book extraction** — Statistical analysis of expert openings by unit pair/triple

## Building

Build via Visual Studio solution (`visualstudio/Prismata.sln`). Only x86 (Win32) configs are available.

```
# From Git Bash (note // for MSBuild switches):
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m
```

Debug builds output to `bin/` with `_d` suffix (e.g., `Prismata_Testing_d.exe`).

**Dependencies:** [SFML 2.6.2](https://www.sfml-dev.org/) (zlib/libpng license), [RapidJSON](https://rapidjson.org/) (MIT, embedded in `source/rapidjson/`).

## Project Structure

| Path | Description |
|---|---|
| `source/ai/` | AI: search algorithms, evaluation, neural net, partial players |
| `source/engine/` | Game engine: rules, state, cards |
| `source/gui/` | SFML GUI: game display, debug panel, replay viewer |
| `source/testing/` | Tournaments, benchmarks, tests |
| `training/` | Python ML pipeline: vectorization, training, weight export |
| `bin/asset/config/` | Card library, AI config, neural weights |
| `CLAUDE.md` | Detailed project status and technical documentation |

## Credits

| Component | Author | License |
|---|---|---|
| [PrismataAI](https://github.com/davechurchill/PrismataAI) (base project) | David Churchill / Lunarch Studios | [CC BY-NC-SA 2.5 CA](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) |
| [SFML 2.6.2](https://www.sfml-dev.org/) | Laurent Gomila | zlib/libpng |
| [RapidJSON](https://rapidjson.org/) | Tencent / Milo Yip | MIT |
| [prismata-replay-parser](https://github.com/plampila/prismata-replay-parser) | plampila | Open source |
| [prismata-stats](https://gitlab.com/prismata-stats/v3/-/tree/dev) | Community | Open source |
| [Prismata](https://store.steampowered.com/app/490220/Prismata/) (the game) | Lunarch Studios | - |
