# PrismatAlpha

An AI and ML hobby project for [Prismata](https://store.steampowered.com/app/490220/Prismata/), built on the AI architecture and tournament infrastructure from [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI).

**Prismata** is a turn-based perfect-information strategy card game by Lunarch Studios. Think chess meets Dominion — no hidden information, no luck, just pure strategy with 116 unique units.

## What's in this repo

### C++ engine and AI

The Churchill engine, with the AI architecture (PartialPlayer phase decomposition, HardestAI, Stack Alpha-Beta, UCT/MCTS) preserved and extended:

- **DeepSets neural network evaluation** integrated into both search algorithms via `NeuralNet.cpp`
- **LiveHardestAI** — a recreation of the live MasterBot using parameters extracted directly from the game's SWF (50-entry unit-specific opening book, 5 root ability variants, Odin filter)
- **`--suggest` CLI mode** — feed a game state JSON, get back AI move recommendations with click sequences
- **`--eval`, `--analyze`, `--dump-states`** modes for replay analysis and engine verification
- **SFML GUI** with debug overlays, eval graphs, replay stepping, and card images

### JavaScript engine

An AS3-to-JS transpilation of the original Prismata client engine, validated click-by-click against live replays:

- **100% click-level replay validation** on the tested corpus (pulled from the live game's S3)
- **Matchup runner** (`matchup_clean.js`) — pit any combination of C++ AI players, MCDSAI, or SteamAI against each other with parallel workers
- **SteamAI integration** — wraps Steam's native `PrismataAI.exe` as a player (one-shot process per turn)
- **HTML replay viewer** — generates per-game or self-contained drag-and-drop viewers (15MB with all card art embedded)
- **Replay export/validation** — convert between engine formats, validate S3 replays click-by-click

### DeepSets training pipeline

End-to-end PyTorch pipeline for training position-evaluation models on per-instance unit data:

- **Per-instance tokens** — each unit on the board becomes a feature vector (32-dim learned embedding + 13 static properties + 10 instance-state features = 55-dim)
- **DeepSets architecture** — shared encoder + sum pooling, invariant to unit ordering, ~172K parameters
- **Three trained models**: MB-only (82.4% val acc), Human-only (78.2%), Mixed (82.2%). Full results and the open question of how this translates to play strength: [`docs/deepsets-training-results.md`](docs/deepsets-training-results.md)
- **DSN2 binary format** — exported weights load directly into C++ `NeuralNet` at runtime
- **Data sources**: 102K expert replays (1500+ rated, balance-validated) and self-play fleet data

```
Extract (replays) → Convert (V2 JSONL) → Vectorize (HDF5) → Train → Export (DSN2 binary)
```

### DeadGameBot

A Python bot with the ability to log into the Prismata server and play casual games using the C++ AI:

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

### Supporting tools

- **Opening book analysis** — extract and evaluate opening sequences from expert replays
- **Commentary pipeline** — generate post-game analysis using extracted game knowledge
- **Discord knowledge extraction** — mine strategy insights from community Discord channels
- **Asset extraction** — pull card images and UI elements for external viewers
- **Cloud launchers** — AWS/GCP scripts for GPU training and self-play fleet generation

## Engine verification

The C++ engine has been audited in multiple passes against the original AS3 source:

1. **Engine logic audit** — Defense, Swoosh, Action, Breach phases verified against decompiled AS3
2. **AS3 faithful port** — stagnation system, death scripts, single-pass swoosh, SNIPE/CHILL reorder
3. **F6 ground truth validation** — C++ engine states compared against live game clipboard export
4. **Replay oracle** — click-by-click replay validation using the JS transpiled engine

## AI strength and the parity gap

| Player | Description |
|---|---|
| LiveHardestAI | SWF-extracted params, opening book, exposed in C++ engine |
| MCDSAI | Lunarch's C++ AI (closed source) |
| SteamAI | Steam's native `PrismataAI.exe` — i.e. live MasterBot |
| DSNN players | UCT + DeepSets neural evaluation |

A March 2026 single-unit sweep (105 units × 4 games each, `LiveHardestAIUCT` vs `STEAMAI`) found `LiveHardestAIUCT` winning only ~20% of games overall and losing 0/4 on roughly 60% of units. The community assumption that the published code is essentially at parity with live MasterBot is not supported by this data — closing that gap appears to be a prerequisite before the trained DSNN players' validation accuracy can translate into play strength.

Full data and discussion: [`docs/deepsets-training-results.md`](docs/deepsets-training-results.md).

## Building

Build via Visual Studio (`visualstudio/Prismata.sln`). **x86 only** for GUI; Testing and Standalone support x64.

| Config | Notes |
|---|---|
| Debug | `_d` suffix executables |
| Release | Standard optimised build |
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

## Project history

Active development since early 2026, building on Churchill's 2020 open-source release. Major milestones:

- **AS3 transpilation** — JS port of the original Flash game engine, click-by-click replay validated
- **LiveHardestAI extraction** — SWF parameters used to recreate the live MasterBot
- **Engine audit** — multi-phase verification against AS3 source (stagnation, death scripts, swoosh)
- **Clean-room rebuild** — matchup infrastructure rebuilt from scratch
- **Self-play infrastructure** — cloud fleet generation (AWS/GCP), streaming training, XPU acceleration
- **DeepSets pipeline** — end-to-end training with three model variants exported to C++
- **DeadGameBot** — live ranked bot playing on the Prismata server
- **Engine V2** — clean-room C++ rewrite targeting Linux headless RL

Full chronological history in [`docs/PROJECT_HISTORY.md`](docs/PROJECT_HISTORY.md).

## Key references

- [AIIDE 2015 — Hierarchical Portfolio Search](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — the foundational AI architecture
- [Game AI Pro 3 — Prismata AI](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — detailed write-up of the PartialPlayer system
- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation by David Churchill
- [ML State Evaluation (2019)](https://skatgame.net/mburo/aiide19ws/paper-3.pdf) — neural network evaluation for Prismata

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).

## Credits

- **David Churchill / Lunarch Studios** — the original PrismataAI engine and AI architecture ([source](https://github.com/davechurchill/PrismataAI))
- **SFML** — GUI rendering (zlib/libpng license)
- **RapidJSON** — JSON parsing (MIT license)
