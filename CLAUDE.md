# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play 10K generation + training: see `docs/plans/2026-02-14-selfplay-10k-generation-and-training.md`

## Current Status (Feb 15, 2026)

**10K self-play generation IN PROGRESS.** Running `SelfPlay_10K` tournament: 10,000 rounds, 8 threads, `OriginalHardestAI_1s` (following Churchill's 1s think time). ~22 games/min, ETA ~7.5 hours. Output: `bin/training/data/selfplay/`.

**Next actions (after generation completes):**
1. **Train on self-play data** — `python training/train.py --selfplay-dir bin/training/data/selfplay/ --expert-weight 0.0`. Target: val accuracy >65%.
2. **Export weights + tournament validation** — PrismatAlpha_AB vs OriginalHardestAI. Target: >55% WR (Churchill: 58.8%).
3. **Fix TS tooling bugs** (RC#5, RC#6, selfsac) — lower priority, not blocking self-play.

**Current neural net strength:** ~42% WR vs MediumAI, ~10% WR vs OriginalHardestAI. Dramatically better than random (0%) but weaker than playout eval.

## What This Project Is

A C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The engine simulates game states, the AI uses Alpha-Beta search, UCT/MCTS, and a PartialPlayer phase decomposition system (Defense, ActionAbility, ActionBuy, Breach).

## How to Build and Run

Build via the Visual Studio solution in `visualstudio/`. Three executables:

- **Prismata_GUI** — SFML-based GUI for watching AI vs AI games
- **Prismata_Testing** — Engine unit tests + tournament runner
- **Prismata_Standalone** — Console-based tournament runner (no GUI)

**Build notes:**
- Build the full solution `visualstudio/Prismata.sln`, not individual `.vcxproj` files
- MSBuild path: `C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\MSBuild.exe`
- **x86 only**: Debug|x86, Release|x86, Static Release|x86. No x64 configs.
- Debug builds have `_d` suffix: `bin/Prismata_Testing_d.exe`
- **MSBuild from Git Bash**: `"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m`
- **Always use `/t:Rebuild`** (not `/t:Build`) — incremental builds may not relink the exe
- **File lock**: Cannot rebuild while exe is running (LNK1104 error). Stop tournaments first.

**Training pipeline:**
```bash
# Generate self-play data (from bin/ directory)
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing.exe

# Train (from project root)
python training/train.py --selfplay-dir bin/training/data/selfplay/ --epochs 100 --batch-size 512 --lr 3e-4 --patience 15

# Export weights
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
```

**Expert replay pipeline** (at `c:\libraries\prismata-replay-parser\`):
```bash
node fetch_expert_replays.js    # fetch from API (incremental)
node filter_expert_replays.js   # filter (instant)
node extract_training_data.js   # extract from S3 (incremental)
```

## Gotchas & Non-Obvious Patterns

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping table below.
- **Two git remotes**: `origin` = davechurchill upstream, `prismat` = user's fork (Surfinite/PrismatAlpha). Push to `prismat`.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` config flag preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to stderr, does NOT abort.
- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **x86 OOM with NeuralNetPlusPlayout**: 16 threads exceeds 2 GB address space. Use `"Threads": 4` for blend tournaments.
- **Blend tournaments concluded**: Neural component hurts performance. Don't revisit until model >60% val accuracy. See `docs/blend-tournament-results.md`.
- **Batch validation**: 287 replays tested, C++ engine correct. 209 FAILs are ALL TS tooling bugs. See `docs/plans/engine-validation-plan.md`.

## User Preferences

- Efficiency over speed — minimize API credits, maximize local PC computation
- Comfortable with long-running unattended tasks (hours). Tell them when something can run overnight.
- Git comfort level: self-described "noob" — explain git ops clearly, always confirm before push/force
- The user is "Surfinite" in Prismata

## Key Architecture

### Engine Internal Name System

Common mappings (full 105-unit table follows):

| Internal Name | Display Name | | Internal Name | Display Name |
|---|---|---|---|---|
| Tesla Tower | Tarsier | | Brooder | Blastforge |
| Treant | Steelsplitter | | Elephant | Rhino |
| Blood Barrier | Forcefield | | Minicannon | Gauss Cannon |
| House | Husk | | Flame Kin | Gauss Charge |

All script references in `cardLibrary.jso` must use **internal names**, not display names.

<details>
<summary>Full 105-unit name mapping table (click to expand)</summary>

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

</details>

### Game Phases & Turn Numbering

Action → Breach (if wipeout) → Confirm → Defense (if enemy has attack) → Swoosh → next player's Action. `m_turnNumber` increments once per **player-turn** (not per round). Frontline kills happen during Action phase via `ASSIGN_FRONTLINE`.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval (branching factor 5 from PPPortfolio). **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): resource values ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50. Cost-based material counting — not strategic value.

**Neural net**: 2-layer ResNet, 512 hidden, state_dim=1785, policy+value heads. C++ inference via `NeuralNet::Instance()`. ~2,000 evals/sec/core.

### Training Approach

**Phase 1: Supervised** (DONE) — 251K expert examples, 57.7% val accuracy (weak but provides real signal).
**Phase 2: Self-Play** (NEXT) — MasterBot vs itself, Churchill got 58.8% WR vs playout with 500K games.
**Phase 3: Iterative RL** (future) — AlphaZero-style loop. Keep expert data in mix (start 50/50, never below 20%).

### Hardware

AMD Ryzen 7 5700X3D (8c/16t), 32GB RAM, Intel Arc B580 (12GB VRAM). Self-play generation: ~30s/game at 1s think time (~22 games/min with 8 threads). Training: ~30 min on CPU.

## Known Issues (Current)

- **Neural policy head weak** — 13.3% accuracy. Computed but unused for move ordering.
- **Blocking feature mismatch** — C++ uses `CardStatus::Assigned`, Python uses `blocking AND abilityUsed`. Low priority.
- **Track A regression inconclusive** — HardestAI (improved) vs OriginalHardestAI: 50/50 over 60 games. Fixes are neutral, not harmful.
- **3 TS tooling bugs** — RC#5 (snipe target name), RC#6 (frontline→breach), selfsac timing. Not blocking self-play.

## Key Files

| Path | Description |
|---|---|
| `bin/asset/config/config.txt` | AI player definitions, tournament configs |
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (105+11 units) |
| `bin/asset/config/neural_weights.bin` | Neural network weights (8.4 MB) |
| `source/ai/NeuralNet.h/cpp` | Neural network inference engine |
| `source/ai/UCTSearch.cpp` | UCT/MCTS search |
| `source/ai/StackAlphaBetaSearch.cpp` | Stack Alpha-Beta search |
| `source/ai/Eval.cpp` | Evaluation functions (WillScore, Playout, NeuralNet) |
| `source/ai/Heuristics.cpp` | Will Score evaluation and resource values |
| `source/ai/AIParameters.cpp` | AI config JSON parser |
| `source/engine/GameState.cpp` | Core game logic |
| `source/engine/Constants.h` | Game constants, EvaluationMethods enum |
| `source/testing/Tournament.cpp` | Multi-threaded tournament runner |
| `source/testing/TournamentGame.cpp` | Single game runner with self-play data export |
| `source/testing/SelfPlayDataSink.h/cpp` | Binary shard writer for self-play features |
| `source/testing/IDataSink.h` | Virtual interface for game event capture |
| `source/gui/GUIState_Play.cpp` | Game play GUI, debug panel, replay viewer |
| `training/train.py` | PyTorch training (PrismataNet, supports `--selfplay-dir`) |
| `training/load_selfplay.py` | Binary shard loader → numpy arrays |
| `training/vectorize.py` | Expert JSONL → PyTorch tensors |
| `training/export_weights.py` | PyTorch → C++ binary weight format |
| `training/schema.json` | Feature schema contract (state_dim=1785) |
| `training/FEATURES.md` | Human-readable feature specification |
| `training/data/unit_index.json` | 161 canonical unit names |
| `training/opening_book.py` | Opening book extraction from expert replays |
| `tools/verify_selfplay.py` | Validates self-play binary output |
| `c:\libraries\prismata-replay-parser\` | TS replay parser + data extraction scripts |

## Documentation Index

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full chronological dev history (sections 1-29) |
| `docs/plans/2026-02-14-selfplay-10k-generation-and-training.md` | Current execution plan |
| `docs/plans/opening-book-plan.md` | Opening book extraction plan (DONE) |
| `docs/plans/engine-validation-plan.md` | Engine validation plan (DONE) |
| `docs/selfplay-worker-instructions.md` | Source-verified self-play implementation spec |
| `docs/blend-tournament-results.md` | Blend tournament results (CONCLUDED) |
| `docs/session-logs/` | Historical parallel session logs (ctx1-4, selfplay progress) |
| `docs/backup_claude_md_2026-02-14/` | Backup of all original CLAUDE*.md files |
| `training/FEATURES.md` | Neural net feature layout specification |
| `docs/WEIGHT_FORMAT.md` | Binary weight format specification |

## Tournament Results Summary

| Matchup | Games | Win Rate | Notes |
|---|---|---|---|
| PrismatAlpha_UCT vs MediumAI | 60 | 41.7% | Neural eval has real signal |
| PrismatAlpha_UCT vs OriginalHardestAI | 64 | 10.9% | Weak but not random |
| PrismatAlpha_AB vs MediumAI | 128 | 43.8% | Search type doesn't matter |
| HardestAI vs OriginalHardestAI | 60 | 50.0% | Track A fixes are neutral |
| RandomAI vs MediumAI | 100 | 0% | Baseline floor |
| EasyAI vs MediumAI | 100 | 6% | Baseline |

## Replay API

Replays stored as gzipped JSON on S3: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` (URL-encode `+` → `%2B`, `@` → `%40`).

## Third-Party Credits

| Dependency | License | Description |
|---|---|---|
| **PrismataAI** (base) | CC BY-NC-SA 2.5 CA | Game engine and AI by David Churchill / Lunarch Studios |
| **SFML 2.6.2** | zlib/libpng | GUI rendering (at `c:\libraries\sfml\`) |
| **RapidJSON** | MIT | JSON parsing (embedded at `source/rapidjson/`) |
| **prismata-replay-parser** | Open source | TS replay parser (at `c:\libraries\prismata-replay-parser\`) |

## External Resources

| Resource | URL |
|---|---|
| Prismata Wiki | https://prismata.fandom.com/wiki/ |
| Churchill Publications | https://davechurchill.ca/publications/ |
| ML State Eval Paper (2019) | https://skatgame.net/mburo/aiide19ws/paper-3.pdf |
| HPS Paper (AIIDE 2015) | http://www.cs.mun.ca/~dchurchill/pdf/aiide15_churchill_prismata.pdf |
| Replay API Wiki | https://prismata.fandom.com/wiki/Replay_API |
| prismata-stats | https://gitlab.com/prismata-stats/v3/-/tree/dev |

**Note:** The [Prismata Wiki](https://prismata.fandom.com/wiki/) has unit pages with costs, stats, abilities, and strategy notes. Use `WebFetch` to check game rules, unit interactions, or verify card data against `cardLibrary.jso` when needed.
