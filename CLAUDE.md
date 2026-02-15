# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play 10K generation + training: see `docs/plans/2026-02-14-selfplay-10k-generation-and-training.md`

## Current Status (Feb 15, 2026)

**Self-play generation IN PROGRESS.** Running via `bin/run_selfplay.bat` (double-click from Explorer — safe from Claude Code contexts). 4 threads per process; run the bat multiple times for more CPU (4 instances = 16 threads, full CPU utilization). ~5.6 games/min per instance. Tournament: `SelfPlay_HardestAI_1s`, 1M rounds, `OriginalHardestAI_1s` (1s think time). Crash-safe: each run writes to timestamped `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/` subdirectory.

**AWS EC2 self-play** also available: `bash aws/launch_selfplay.sh [INSTANCE_TYPE] [NUM_GAMES]`. Pipeline verified working (Feb 15). Boots Windows Server, downloads exe+config from S3, patches config to enable SelfPlay_CI, runs self-play, uploads shards to `s3://prismata-selfplay-data/results/`, auto-terminates. AWS account on paid plan (c5 instances unlocked). vCPU quota: 16 (Standard). Download results: `aws s3 sync s3://prismata-selfplay-data/results/ bin/training/data/selfplay/ --region eu-north-1`.

**Next actions (after generation completes):**
1. **Train on self-play data** — `python training/train.py --selfplay-dir bin/training/data/selfplay/ --expert-weight 0.0`. Target: val accuracy >65%.
2. **Export weights + tournament validation** — PrismatAlpha_AB vs OriginalHardestAI. Target: >55% WR (Churchill: 58.8%).
3. ~~**Fix TS tooling bugs**~~ — RC#5, RC#6, selfsac/lifespan all FIXED. Pass rate improved 27.2%→41.3%. Remaining failures are TS action resolution differences (diminishing returns to fix further).

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
- **Static Release config**: Was historically broken — fixed Feb 2026 (include paths, C++17, linker deps). If adding new source dirs, check Static Release has matching include paths.
- **CI build uses `/p:PlatformToolset=v143`** (VS 2022) since runners don't have v145.

**Training pipeline:**
```bash
# Generate self-play data (from bin/ directory)
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing.exe

# Train (from project root)
python training/train.py --selfplay-dir bin/training/data/selfplay/ --epochs 100 --batch-size 512 --lr 3e-4 --patience 15

# Export weights
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
```

**GitHub Actions self-play** (trigger from GitHub > Actions > "Self-Play Data Generation"):
- Workflow: `.github/workflows/selfplay.yml` — `workflow_dispatch` with inputs for parallel VMs (1-10), games/job, think time, VM multiplier.
- Builds `Static Release|x86` on `windows-latest` (2-core, no larger runners on free plan).
- VM think multiplier (default 1.3x) compensates for slower cloud CPUs vs local Ryzen.
- Output: artifacts with binary shards in timestamped `run_*/` dirs — download and unzip into `bin/training/data/selfplay/`.
- Pushing workflow files requires `workflow` scope: `gh auth login -s workflow`.

**Expert replay pipeline** (at `c:\libraries\prismata-replay-parser\`):
```bash
node fetch_expert_replays.js    # fetch from API (incremental)
node filter_expert_replays.js   # filter (instant)
node extract_training_data.js   # extract from S3 (incremental)
```

## Gotchas & Non-Obvious Patterns

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping table below.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork (Surfinite/PrismatAlpha). Push to `PrismatAlpha`.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` config flag preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to stderr, does NOT abort.
- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **x86 OOM — 4 threads max per process**: x86 2GB address space exhausts after ~456 games with 8 threads (any AI, not just blend). Use `"Threads": 4` in config.txt and run multiple bat instances for parallelism. Each process gets its own 2GB limit. CI workflow overrides Threads via `nproc` (2 on windows-latest, safe).
- **Blend tournaments concluded**: Neural component hurts performance. Don't revisit until model >60% val accuracy. See `docs/blend-tournament-results.md`.
- **Batch validation**: 287 replays tested, C++ engine confirmed correct. After fixing 3 TS tooling bugs: 117 PASS (41.3%), 166 FAIL (all TS-side), 4 ERROR. Remaining failures are action resolution differences in TS→C++ conversion (70% start with gold/green resource divergence). See `docs/plans/engine-validation-plan.md`.
- **Self-play crash safety**: Each run writes to `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/`. Restart anytime — only in-flight games lost. `load_selfplay.py` auto-scans all `run_*` subdirectories.
- **Run self-play from Explorer**: Use `bin/run_selfplay.bat` — runs in its own cmd window, immune to Claude Code context kills.
- **Console output routing**: `[SelfPlay]` and `[Progress]` messages use `fprintf(stderr, ...)` so they appear on console. All other verbose output (scores, buy actions) goes to stdout, which the batch file redirects to `selfplay_log.txt`. New user-facing messages in Tournament.cpp should use stderr.
- **EC2 config patching**: `launch_selfplay.sh` patches config line-by-line (not regex across properties) because JSON property ordering varies — `"run"` may come before or after `"name"` in tournament entries. Don't switch back to cross-property regexes.
- **AWS CLI in Git Bash**: AWS CLI is a native Windows exe. Temp file paths must be Windows-accessible (not `/tmp/`). Use `file://` prefix for user-data (not `base64`). PATH needs: `export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"`.
- **x86 OOM with large vectors**: Don't pre-allocate large `std::vector<GameState>` upfront (e.g., 10K rounds). GameState objects are heavy — allocate per-batch instead. Symptom: process exits silently mid-tournament with no `[SelfPlay] COMPLETE` message.
- **Selfplay shard CRC**: `load_selfplay.py` CRC check fails on shards from runs that crashed or are still in progress (no footer written). Use `validate_crc=False` for live/partial data.
- **Windows file size caching**: `ls`/`Get-ChildItem` may show 0 bytes for files with open write handles. Use `python -c "import os; print(os.path.getsize(path))"` to get actual size.

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

AMD Ryzen 7 5700X3D (8c/16t), 32GB RAM, Intel Arc B580 (12GB VRAM). Self-play generation: ~5.6 games/min per 4-thread instance (~22 games/min with 4 instances). Training: ~30 min on CPU.

## Known Issues (Current)

- **Neural policy head weak** — 13.3% accuracy. Computed but unused for move ordering.
- **PUCT move ordering implemented** — `"UsePUCT": true` in Player_UCT config. Uses policy head as priors in UCT search (AlphaZero-style). Disabled by default — don't enable until policy accuracy improves past ~30%. Files: `UCTSearch.cpp` (computeRootPriors, PUCT formula in UCTNodeSelect), `UCTNode.h` (_policyPrior), `UCTSearchParameters.hpp` (_usePUCT), `AIParameters.cpp` (UsePUCT parsing).
- **Blocking feature mismatch** — C++ uses `CardStatus::Assigned`, Python uses `blocking AND abilityUsed`. Low priority.
- **Track A regression inconclusive** — HardestAI (improved) vs OriginalHardestAI: 50/50 over 60 games. Fixes are neutral, not harmful.
- **TS tooling bugs (FIXED, validation improved)** — RC#5 (snipe target), RC#6 (frontline→breach), selfsac/lifespan tolerance all fixed. Pass rate 27.2%→41.3% (117/283). Remaining 166 failures are action resolution differences in TS conversion. Not blocking self-play.

## Key Files

| Path | Description |
|---|---|
| `bin/asset/config/config.txt` | AI player definitions, tournament configs |
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (105+11 units) |
| `bin/asset/config/neural_weights.bin` | Neural network weights (8.8 MB, committed for CI) |
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
| `tools/download_wiki.py` | Downloads full Prismata wiki from Fandom API |
| `bin/run_selfplay.bat` | Crash-safe self-play launcher (run from Explorer) |
| `.github/workflows/selfplay.yml` | GitHub Actions self-play workflow |
| `aws/launch_selfplay.sh` | EC2 self-play launcher (Windows instances, auto-terminate) |
| `aws/download_results.sh` | Download self-play results from S3 |
| `c:\libraries\prismata-replay-parser\` | TS replay parser + data extraction scripts |
| `c:\libraries\DiscordChatExporter\` | Discord message export tool (CLI at `cli/`) |

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
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference (from wiki) |
| `docs/wiki/` | Full wiki dump (448 pages, raw wikitext) |

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

### Replay Code Sources

| Source | Codes | Location |
|---|---|---|
| Expert (prismata-stats API, 2000+) | ~31,506 | `prismata-replay-parser/expert_replays.json` |
| Reddit /r/prismata | 245 | `prismata-replay-parser/reddit_valid_replays.json` |
| Tournament (Grand Prix + leagues) | 960 | `prismata-replay-parser/tournament_valid_replays.json` |
| Discord (Prismata + League servers) | 3,626 | `prismata-replay-parser/discord_replay_codes_all.json` |

**Discord export tool**: `c:\libraries\DiscordChatExporter\cli\DiscordChatExporter.Cli.exe` (pre-built v2.46, no .NET SDK needed).
Discord server IDs: Prismata = `112616041175089152`, Prismata League = `412991183355248640`.
Giselle bot posts replay embeds in response to codes. Export with `--filter "from:Giselle" -f Json`.

**Code extraction scripts** (at `c:\libraries\prismata-replay-parser\`):
- `extract_discord_codes.js` — extract replay codes from Discord export JSONs
- `extract_tournament_codes.py` — extract codes from tournament data text
- `validate_tournament_codes.js` — validate codes against S3 (HTTP 200 check, concurrency-limited)

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
