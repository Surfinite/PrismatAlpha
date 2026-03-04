# PrismatAI

A fork of [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI) — the C++ game engine and AI for [Prismata](https://store.steampowered.com/app/490220/Prismata/), a turn-based perfect-information strategy card game by Lunarch Studios.

This project extends the original with neural network evaluation, self-play training, and a JavaScript engine for matchup analysis.

## What's Here

- **C++ Engine** — Full Prismata game simulation with Alpha-Beta and UCT/MCTS search
- **Neural Network Eval** — ResNet value head for position evaluation, used alongside traditional search
- **SFML GUI** — Watch AI vs AI games, with card images and debug overlays
- **JS Engine** — Transpiled game engine for running matchups and AI analysis outside C++
- **Training Pipeline** — PyTorch training on self-play data with binary shard I/O and streaming support
- **Cloud Infrastructure** — Scripts for AWS/GCP self-play generation and GPU training

## Building

Build via Visual Studio (`visualstudio/Prismata.sln`). **x86 only** — Debug, Release, or Static Release configurations.

Produces three executables in `bin/`:
- `Prismata_GUI` — GUI for watching games
- `Prismata_Testing` — Tournament runner and engine tests
- `Prismata_Standalone` — Console tournament runner

## Current Status

Work in progress. The C++ engine has been audited against the original AS3 source, with several logic fixes applied. A JavaScript transpilation of the game engine enables matchup analysis and AI-vs-AI testing outside C++. The neural net training pipeline is ready — next step is generating clean self-play data and training a model on bug-free game simulations.

## Key References

- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation
- [AIIDE 2015 Paper](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — Hierarchical Portfolio Search
- [Game AI Pro 3](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — Detailed AI write-up

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).
