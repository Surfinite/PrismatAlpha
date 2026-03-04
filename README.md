# PrismatAI

A fork of [David Churchill's PrismataAI](https://github.com/davechurchill/PrismataAI) — the C++ game engine and AI for [Prismata](https://store.steampowered.com/app/490220/Prismata/), a turn-based perfect-information strategy card game by Lunarch Studios.

This project extends the original with neural network evaluation, self-play training, and a JavaScript engine for matchup analysis.

## What's Here

- **C++ Engine** — Full Prismata game simulation with Alpha-Beta and UCT/MCTS search
- **Neural Network Eval** — ResNet value head trained on 700K+ self-play games, used alongside traditional search
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

The neural net (256 hidden, 3 layers) achieves **~52% win rate vs OriginalHardestAI** (the original strongest AI) over 2,000+ games. Trained on 700K+ self-play games using value-only prediction with tanh+MSE loss.

## Key References

- [GDC 2017 Talk](https://youtu.be/sQSL9j7W7uA) — Prismata AI presentation
- [AIIDE 2015 Paper](https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf) — Hierarchical Portfolio Search
- [Game AI Pro 3](https://davechurchill.ca/publications/pdf/prismata_gaip3.pdf) — Detailed AI write-up

## License

[CC BY-NC-SA 2.5 Canada](https://creativecommons.org/licenses/by-nc-sa/2.5/ca/) (inherited from the original project).
