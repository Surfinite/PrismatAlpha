# PrismatAlpha

A fork of [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI) — significantly extended with neural network evaluation, a transpiled JavaScript engine, a live bot system, and tooling for matchup analysis, replay validation, and training data generation.

**[Prismata](https://store.steampowered.com/app/490220/Prismata/)** is a turn-based perfect-information strategy card game by Lunarch Studios. Think chess meets Dominion — no hidden information, no luck, just pure strategy with over 100 unique units.

## What's in this repo

### C++ Engine & AI (~18K LOC)

The original Churchill engine with substantial additions:

- **Alpha-Beta + UCT/MCTS search** with configurable time limits, thread counts, and evaluation functions
- **PartialPlayer phase decomposition** — Defense, ActionAbility, ActionBuy, Breach — each phase can use different strategies
- **DeepSets neural network evaluation** integrated into both search algorithms via `NeuralNet.cpp`
- **LiveHardestAI** — best-effort recreation of the live MasterBot, with parameters extracted directly from the game's SWF (50-entry unit-specific opening book, 5 root ability variants, Odin filter)
- **`--suggest` CLI mode** — feed a game state JSON, get back AI move recommendations with click sequences
- **`--eval`, `--analyze`, `--dump-states`** CLI modes for replay analysis and engine verification
- **SFML GUI** with debug overlays, eval graphs, replay stepping, and card images

### JavaScript Engine (~22K LOC)

A faithful AS3-to-JS transpilation of the original Prismata client engine, validated against thousands of replays:

- **100% replay validation** on tested corpus — click-by-click game state verification
- **Matchup runner** (`matchup_clean.js`) — pit any combination of C++ AI players, MCDSAI, or SteamAI against each other with parallel workers
- **SteamAI integration** — wraps Steam's native `PrismataAI.exe` as a player (one-shot process per turn)
- **HTML replay viewer** — generates per-game or self-contained drag-and-drop viewers (15MB with all card art embedded)
- **Replay export/validation** — convert between engine formats, validate S3 replays click-by-click

### DeepSets Training Pipeline

End-to-end PyTorch pipeline for training position evaluation models:

- **Per-instance feature extraction** — each unit on the board is a feature vector (11 features x 161 unit types + 14 global features = 1785-dim state)
- **DeepSets architecture** — shared encoder + sum pooling, invariant to unit ordering
- **Three trained models**: MB-only (82.4% val acc), Human-only (78.2%), Mixed (82.2%)
- **DSN2 binary format** — exported weights load directly into C++ `NeuralNet` at runtime with dynamic hidden_dim/num_layers
- **Data sources**: 102K expert replays (1500+ rated) and MasterBot self-play fleet data

```
Extract (replays) → Convert (V2 JSONL) → Vectorize (HDF5) → Train → Export (DSN2 binary)
```

### DeadGameBot

A Python bot that logs into the Prismata server and plays ranked games using the C++ AI:

- **AMF3 binary protocol** — full client implementation extracted from the game
- **Headless game client** — auth, matchmaking, game state tracking, click submission
- **SteamAI bridge** — converts server game state to C++ AI input and back
- **PvP challenge support** — accepts challenges from other players
- **Web frontend** with gating, audit logging, and status display

### Engine V2 (in progress)

A clean-room C++ rewrite targeting Linux and headless RL self-play:

- CMake build system (no Visual Studio dependency)
- Instance-based `NeuralNet` (no singleton — can run multiple models simultaneously)
- Replay validation harness with name translation

### Supporting Tools

- **Opening book analysis** — extract and evaluate opening sequences from expert replays
- **Commentary pipeline** — generate post-game analysis using extracted game knowledge
- **Discord knowledge extraction** — mine strategy insights from community Discord channels
- **Asset extraction** — pull card images and UI elements for external viewers
- **Dashboard** — fleet monitoring, tournament launching, cost estimation
- **Cloud launchers** — AWS/GCP scripts for GPU training and self-play fleet generation

## Engine Verification

The C++ engine has been audited in multiple passes against the original AS3 source code:

1. **Engine logic audit** — Defense, Swoosh, Action, Breach phases verified against decompiled AS3
2. **AS3 faithful port** — stagnation system, death scripts, single-pass swoosh, SNIPE/CHILL reorder
3. **F6 ground truth validation** — C++ engine states compared against live game clipboard export
4. **Replay oracle** — click-by-click replay validation using the JS transpiled engine

## AI Strength

| Player | Description | Relative Strength |
|---|---|---|
| LiveHardestAI | SWF-extracted params, opening book | Baseline |
| MCDSAI | Lunarch's C++ AI (closed source) | ~78% WR vs LiveHardestAI |
| SteamAI | Steam's native PrismataAI.exe | ~ MCDSAI |
| MasterBot (Steam) | Live ranked bot | ~ SteamAI |
| DSNN players | UCT + DeepSets neural eval | Under evaluation |

LiveHardestAI is the strongest open-source Prismata AI available. The gap to MasterBot is primarily in internal tuning not visible in the extracted parameters.

## Building

Build via Visual Studio (`visualstudio/Prismata.sln`). **x86 only** for GUI; Testing and Standalone support x64.

| Config | Notes |
|---|---|
| Debug | `_d` suffix executables |
| Release | Standard optimized build |
| Static Release | For distribution (check include paths when adding source dirs) |

Produces three executables in `bin/`:
- **Prismata_GUI** — GUI for watching AI games and replays
- **Prismata_Testing** — Tournament runner, engine tests, `--suggest`/`--eval`/`--analyze` modes
- **Prismata_Standalone** — Console tournament runner (no GUI dependency)

### Quick start

```bash
# Build (from Git Bash)
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  visualstudio/Prismata.sln //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m

# Run a matchup (JS engine)
node js_engine/matchup_clean.js --games 10 --parallel 4 --think-time 3000

# Run with SteamAI opponent
node js_engine/matchup_clean.js --player SteamAI --steam-difficulty HardestAI --games 10

# Build replay viewer
node js_engine/build_replay_viewer.js bin/prismata_replay_viewer.html

# Get AI suggestion for a game state
bin/Prismata_Testing.exe --suggest state.json --player PrismatAlpha_AB --think-time 3000
```

## Project History

This project has been in active development since early 2026, building on Churchill's 2020 open-source release. Major milestones:

- **Neural net integration** — ResNet value head, then DeepSets architecture with per-instance features
- **AS3 transpilation** — faithful JS port of the original Flash game engine, 100% replay validated
- **LiveHardestAI extraction** — decompiled SWF parameters to recreate the live MasterBot
- **Engine audit** — multi-phase verification against AS3 source (stagnation, death scripts, swoosh)
- **Clean room rebuild** — complete matchup infrastructure rebuilt from scratch for reliability
- **Self-play infrastructure** — cloud fleet generation (AWS/GCP/Azure), streaming training, XPU acceleration
- **DeepSets pipeline** — end-to-end training with three model variants exported to C++
- **DeadGameBot** — live ranked bot playing on the Prismata server
- **Engine V2** — clean-room C++ rewrite targeting Linux headless RL

370+ commits across multiple feature branches. Full chronological history in `docs/PROJECT_HISTORY.md`.

## Key References

- [AIIDE 2015 — Hierarchical Portfolio Search](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — the foundational AI architecture
- [Game AI Pro 3 — Prismata AI](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — detailed write-up of the PartialPlayer system
- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation by David Churchill
- [ML State Evaluation (2019)](https://skatgame.net/mburo/aiide19ws/paper-3.pdf) — neural network evaluation for Prismata

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).

## Credits

- **David Churchill / Lunarch Studios** — original PrismataAI engine and AI ([source](https://github.com/davechurchill/PrismataAI))
- **SFML** — GUI rendering (zlib/libpng license)
- **RapidJSON** — JSON parsing (MIT license)
