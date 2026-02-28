# PrismatAlpha

An AI improvement project for [Prismata](https://store.steampowered.com/app/490220/Prismata/), the turn-based perfect-information strategy card game by [Lunarch Studios](http://lunarchstudios.com/). The goal is to push the AI beyond the original Masterbot (~1200 Elo) toward expert-level play (2000+ Elo) using neural network evaluation and self-play reinforcement learning, following the approach outlined in [Churchill & Campbell's 2019 ML paper](https://skatgame.net/mburo/aiide19ws/paper-3.pdf).

The project now spans a C++ game engine, a faithful JavaScript port of the original AS3 engine, a PyTorch training pipeline, multi-cloud self-play infrastructure, and a suite of live-game tools.

## Foundation

Built on **[PrismataAI](https://github.com/davechurchill/PrismataAI)** by [David Churchill](https://davechurchill.ca/) (Memorial University of Newfoundland / Lunarch Studios), the open-source C++ AI engine that powers the Masterbot in the retail game. Published under [CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) in 2020.

The original engine includes:
- **Prismata_Engine** — Full game rules simulation
- **Prismata_AI** — The retail Masterbot: Stack Alpha-Beta search with Hierarchical Portfolio Search (branching factor 5, playout evaluation at leaf nodes)
- **Prismata_GUI** — SFML-based GUI for playing against the AI
- **Prismata_Testing** — Tournament runner and benchmarks

### Key Publications

| Paper | Year | Venue |
|---|---|---|
| [Hierarchical Portfolio Search: Prismata's Robust AI Architecture](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) | 2015 | AIIDE (Best Student Paper) |
| [Hierarchical Portfolio Search in Prismata](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) | 2017 | Game AI Pro 3 |
| [GDC 2017: Building the AI for Prismata](https://youtu.be/sQSL9j7W7uA) | 2017 | GDC |
| [Machine Learning State Evaluation in Prismata](https://skatgame.net/mburo/aiide19ws/paper-3.pdf) | 2019 | AIIDE Workshop |

## What We've Built

### Card Library Update
The engine's unit database was years out of date. We fetched 500+ expert replays from the [Prismata replay API](https://prismata.fandom.com/wiki/Replay_API), extracted current unit definitions, added 8 missing competitive units, updated balance for 41 existing units, and verified all 105 competitive non-base-set units match the final balance patch (January 14, 2019).

### Neural Network Integration
C++ inference engine with configurable architecture, plugged into both Alpha-Beta and UCT search as a leaf evaluation function.

- **Architecture:** ResNet — Input(1785) → Linear → N x ResBlock → policy head (161 unit types) + value head (tanh, [-1,1]). Hidden dimension and layer count are read from the weight file header at runtime — deploy 256h/2L, 256h/3L, or 512h by swapping weight files, no C++ rebuild needed.
- **Feature vector:** 161 unit types x 11 features + 14 global features (resources, turn, active player). Schema: `training/schema.json`.
- **Current best:** R12 (256 hidden, 3 layers, dropout 0.20, label smoothing 0.90, 871K params).
- **Evaluation modes:** `NeuralNet`, `Playout`, `NeuralNetPlusPlayout` (configurable blend weight). PUCT move ordering implemented but disabled until policy accuracy improves past ~30%.
- **Performance:** ~2,000 evals/sec/core (CPU).

### AS3 → JS Game Engine Transpilation
The retail Prismata client runs on a Flash/AS3 engine compiled to AVM2 bytecode. We decompiled and transpiled 18 AS3 source files into a faithful JavaScript engine, then paired it with Lunarch's official `MCDSAI3441.js` (Emscripten, Feb 2017) for ground-truth training data generation.

- **18 AS3 files → 18 JS modules** covering game state, cards, phases, moves, abilities, blocking, swoosh
- **100% replay validation** (500/500 expert replays reproduce exactly)
- Self-play data generation: `node selfplay_main.js --games 100 --think-time 1000 --jsonl out.jsonl`
- Expert replay extraction: `node replay_extractor.js` with per-replay balance validation
- Stuck-game detection auto-discards stalemate positions (~5% of random card sets)

### Expert Replay Data Pipeline
- **173,471 unique replay codes** from 8 sources (API, per-player fetches, Reddit, Discord, tournaments, community contributions)
- **2.63M training examples** (1500+ Elo, 104K games) extracted via the faithful JS engine
- Per-replay balance validation recovers pre-patch games safely (46,603 games from before Jan 2019 patch)
- SQLite replay database with junction tables, CLI tool, and incremental import
- Incremental pipeline — safe to re-run without reprocessing

### Self-Play Data Generation
- **~722K games** (26.7M records, 178 GB) generated via C++ engine self-play (`OriginalHardestAI` 1s think vs itself)
- Multi-cloud fleet: AWS EC2 (spot), GCP Compute Engine, Azure VMs — all uploading to a shared S3 bucket
- **TheWatcher** — persistent monitor (Task Scheduler, every 5 min) that auto-relaunches terminated instances, manages quota-aware scale-up, and tracks fleet health across all three providers
- Local generation via `bin/run_selfplay.bat` (crash-safe, auto-restarts)
- JS engine self-play also available: `MCDSAI` vs `MCDSAI` or `MCDSAI` vs C++ `OriginalHardestAI`

### Training Pipeline
PyTorch training with multiple data loading modes:
- **Vectorized expert data** (`.pt` tensors) for expert replay training
- **Streaming binary loader** for large self-play datasets (memory-mapped, never loads full dataset into RAM)
- **Intel Arc B580 XPU acceleration** — 4.5x speedup over CPU via native `torch.xpu` backend
- **Cloud GPU support** — AWS (g6.2xlarge L4) and GCP (g2-standard-4/8 L4) launch scripts with auto-terminate
- Hyperparameter sweep infrastructure with experiment logging (`training/runs/*.json`)
- Weight export to C++ binary format: `python training/export_weights.py model.pt output.bin`

### Engine State Verification
5-phase pipeline comparing C++ engine output against AS3 ground truth:
- C++ `--dump-states` produces JSONL state snapshots
- F6 ground truth captured from Prismata's built-in replay viewer (22 replays, 542 states, 83/147 buyable units)
- Comparison tool with internal↔display name mapping via `cardLibrary.jso`
- Regression mode: `python tools/validate_engine_states.py --regression`

### Live Game Tools
- **TCP sniffer proxy** (`tools/prismata_sniffer.py`) — intercepts AMF3 protocol, captures replay codes, tracks live game state, supports message injection (chat + game actions)
- **Neural advisor overlay** (`tools/prismata_advisor.py`) — clipboard F6 monitor → C++ `--suggest` → tkinter always-on-top display with eval and recommended moves
- **Autopilot** (`tools/prismata_autopilot.py`) — captures game state, runs AI search, injects moves via sniffer proxy. Semi-auto and full-auto modes.
- **Post-game commentary** (`tools/generate_postgame_commentary.py`) — two-stage LLM pipeline (structured analysis → narrative) using Claude Haiku
- **Command Center dashboard** (`dashboard/`) — Node.js web app with live fleet status, training curves, action buttons

### GUI Improvements
- Higher resolution (2133x1200), card images for all units
- Debug panel with AI confidence, unit value labels (heuristic + neural), comparison AI
- Watch Training mode (self-play with live display) and Watch Eval mode (benchmark games)
- Per-action replay viewer with `DetailedReplays` tournament config option
- Tournament replay save/load (GUI auto-scans replay files)

## Current Status

Early models were trained on C++ engine data that had a ~50% replay reproduction rate (engine bugs made more moves legal than intended). Those results are invalidated. The project now generates training data from the faithful JS engine.

**First correct-data model (Feb 2026):**
| Metric | Value |
|---|---|
| Architecture | R12 (256 hidden, 3 layers, 871K params) |
| Training data | 1.33M expert examples (JS engine, 1500+ Elo) |
| Validation accuracy | 61.2% (policy) |
| Win rate vs OriginalHardestAI | **6.0%** (5W 93L 2D, 100 games) |

**Next step:** Re-vectorize and retrain on the expanded dataset (2.63M examples, 78% more data from balance-validated pre-patch games). An initial training run hit 19.5% policy accuracy but value head failed to learn due to a tensor shape bug in vectorize.py (now fixed — dataset needs regeneration).

For reference, Churchill's 2019 paper achieved **58.8% WR** against the playout evaluator using 500K self-play games. Our model uses expert replays rather than self-play data, and the training loop is not yet iterative — closing this gap is the primary goal.

## Building

### C++ Engine
Build via Visual Studio solution (`visualstudio/Prismata.sln`). **x86 only** (Win32 configs). Always use `/t:Rebuild` — incremental builds may not relink.

```bash
# From Git Bash (note // for MSBuild switches):
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m
```

Debug builds output to `bin/` with `_d` suffix (e.g., `Prismata_Testing_d.exe`).

### Training
```bash
# Vectorize expert data (from project root)
python training/vectorize.py js_engine/combined_all_expert_1500.jsonl training/data_expert_1500/

# Train
python training/train.py training/data_expert_1500/ training/models/my_run \
  --epochs 100 --batch-size 512 --lr 2e-5 --num-layers 3 --hidden-dim 256 \
  --dropout 0.20 --label-smooth 0.90 --device xpu --num-workers 4

# Export weights to C++ binary format
python training/export_weights.py training/models/my_run/best_model.pt bin/asset/config/neural_weights.bin
```

### JS Engine Self-Play
```bash
cd js_engine

# Generate training data (MCDSAI vs MCDSAI)
node selfplay_main.js --games 100 --think-time 1000 --jsonl out.jsonl 2> log.txt

# Extract from expert replays
node replay_extractor.js
```

### CLI Suggest Mode
```bash
# AI move recommendation from F6 clipboard JSON
bin/Prismata_Testing.exe --suggest state.json --player PrismatAlpha_AB --think-time 3000
```

## Project Structure

| Path | Description |
|---|---|
| `source/ai/` | AI: search (Alpha-Beta, UCT/MCTS), evaluation, neural net inference, partial players |
| `source/engine/` | Game engine: rules, state, cards, phases |
| `source/gui/` | SFML GUI: game display, debug panel, replay viewer |
| `source/testing/` | Tournament runner, benchmarks, self-play data export |
| `js_engine/` | Faithful AS3→JS game engine port + MCDSAI integration |
| `training/` | PyTorch ML pipeline: vectorization, training, streaming loader, weight export |
| `tools/` | Sniffer proxy, advisor overlay, autopilot, commentary, state verification |
| `dashboard/` | Command Center web app (Node.js + Express + Chart.js) |
| `aws/`, `gcp/`, `azure/` | Cloud launch scripts, TheWatcher monitor, fleet management |
| `bin/asset/config/` | Card library (`cardLibrary.jso`), AI config (`config.txt`), neural weights |
| `docs/` | Plans, audit findings, strategy knowledge base, project history |
| `CLAUDE.md` | Detailed technical documentation — architecture, gotchas, operational details |

## Credits

| Component | Author | License |
|---|---|---|
| [PrismataAI](https://github.com/davechurchill/PrismataAI) (base project) | David Churchill / Lunarch Studios | [CC BY-NC-SA 2.5 CA](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) |
| [SFML 2.6.2](https://www.sfml-dev.org/) | Laurent Gomila | zlib/libpng |
| [RapidJSON](https://rapidjson.org/) | Tencent / Milo Yip | MIT |
| [prismata-replay-parser](https://github.com/plampila/prismata-replay-parser) | plampila | Open source |
| [prismata-stats](https://gitlab.com/prismata-stats/v3/-/tree/dev) | Community | Open source |
| [MCDSAI3441.js](https://play.prismata.net) | Lunarch Studios | Proprietary |
| [Prismata](https://store.steampowered.com/app/490220/Prismata/) (the game) | Lunarch Studios | — |
