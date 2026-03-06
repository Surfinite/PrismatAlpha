# PrismatAI

A fork of [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI) — the C++ game engine and AI for [Prismata](https://store.steampowered.com/app/490220/Prismata/), a turn-based perfect-information strategy card game by Lunarch Studios.

This project extends the original with neural network evaluation, self-play training, and a JavaScript engine for matchup analysis.

## What's Here

- **C++ Engine** — Full Prismata game simulation with Alpha-Beta and UCT/MCTS search
- **Neural Network Eval** — ResNet value head for position evaluation, used alongside traditional search
- **SFML GUI** — Watch AI vs AI games, with card images and debug overlays
- **JS Engine** — Transpiled game engine for running matchups and AI analysis outside C++
- **LiveHardestAI** — Exact replication of the live Prismata MasterBot, extracted from the original SWF (50-entry unit-specific opening book, 5 root ability variants, full parameter match)
- **Cloud Infrastructure** — Scripts for AWS/GCP self-play generation and GPU training

## Building

Build via Visual Studio (`visualstudio/Prismata.sln`). **x86 only** — Debug, Release, or Static Release configurations.

Produces three executables in `bin/`:
- `Prismata_GUI` — GUI for watching games
- `Prismata_Testing` — Tournament runner and engine tests
- `Prismata_Standalone` — Console tournament runner

## Current Status

The C++ engine has been thoroughly audited against the original AS3 source and is now considered an accurate replication of the live game. The JavaScript engine (transpiled from AS3) passes 100% replay validation and is used to verify C++ AI moves match the real game's expectations.

LiveHardestAI is the best available open-source recreation of the live MasterBot — parameters extracted directly from the game's SWF, with decompiled source code available for inspection. This is the baseline we're training against.

Training is starting fresh from accurate game data for the first time. Previous training runs used an engine with known logic bugs and are discarded. The new pipeline will generate self-play data using the bug-free engine and train a neural network value function using PyTorch.

## Key References

- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation
- [AIIDE 2015 Paper](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — Hierarchical Portfolio Search
- [Game AI Pro 3](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — Detailed AI write-up

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).
