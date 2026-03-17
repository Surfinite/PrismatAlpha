# PrismatAI

A fork of [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI) — the C++ game engine and AI for [Prismata](https://store.steampowered.com/app/490220/Prismata/), a turn-based perfect-information strategy card game by Lunarch Studios.

This project extends the original with neural network evaluation, self-play training, and a JavaScript engine for matchup analysis.

## What's Here

- **C++ Engine** — Full Prismata game simulation with Alpha-Beta and UCT/MCTS search
- **Neural Network Eval** — ResNet value head for position evaluation, used alongside traditional search
- **SFML GUI** — Watch AI vs AI games, with card images and debug overlays
- **JS Engine** — Transpiled game engine for running matchups and AI analysis outside C++
- **LiveHardestAI** — Best-effort recreation of the live Prismata MasterBot using parameters extracted from the original SWF (50-entry unit-specific opening book, 5 root ability variants). Falls short of the actual MasterBot (MCDSAI) due to internal tuning that isn't visible in the extracted parameters.
- **Cloud Infrastructure** — Scripts for AWS/GCP self-play generation and GPU training

## Building

Build via Visual Studio (`visualstudio/Prismata.sln`). Debug, Release, or Static Release configurations.

- `Prismata_Testing` and `Prismata_Standalone` build as **x64** (no memory limit)
- `Prismata_GUI` builds as **x86** (pending SFML x64 libraries)

Produces three executables in `bin/`:
- `Prismata_GUI` — GUI for watching games and replays
- `Prismata_Testing` — Tournament runner, engine tests, and `--suggest` mode
- `Prismata_Standalone` — Console tournament runner

## Current Status

The C++ engine has been thoroughly audited against the original AS3 source and is considered an accurate replication of the live game. The JavaScript engine (transpiled from AS3) passes 100% replay validation and is used to run matchups between C++ AI players and the live SteamAI executable.

**LiveHardestAI** is the best available open-source recreation of the live MasterBot — parameters extracted directly from the game's SWF, with decompiled source code available for inspection. A single-unit sweep against SteamAI (LiveHardestAI at 2x think time) is underway to identify which units have strategic gaps in the partial player system.

**DeepSets neural network** evaluation is working. Three trained models are available: MB-only (82.4% val acc), Human-only (78.2%), and Mixed MB+Human (82.2%). Five DSNN players are configured with per-player weight files and evaluated via the JS matchup runner.

## Key References

- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation
- [AIIDE 2015 Paper](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — Hierarchical Portfolio Search
- [Game AI Pro 3](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — Detailed AI write-up

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).
