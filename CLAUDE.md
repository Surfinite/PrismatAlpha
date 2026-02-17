# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play training: see `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (Feb 17, 2026)

**Self-play iteration 2 training COMPLETE.** Best model: 81.9% val accuracy (epoch 1, value-only, 2.3M records from 63K games). Same overfitting pattern as iter 1 — best at epoch 1, train acc hits 98%+ by epoch 9. Weights exported to `neural_weights.bin`. Previous models: `neural_weights_selfplay_v1.bin` (iter 1, 77% val acc, 10K games), `neural_weights_expert_backup.bin` (expert-trained).

**V2 hyperparameter experiments COMPLETE (Feb 17).** 9 experiments across 3 phases (loss function, LR sweep, data & capacity). Winner: E2b (hidden_dim=256, LR=1e-5, tanh+MSE, 739K params) — Brier 0.1213, best at step 10000. Key findings: (1) model capacity matters most — smaller model trains longer before overfitting, (2) LR controls overfitting speed but not ceiling, (3) loss function (MSE vs BCE) is a wash, (4) subsampling hurts. Tournament eval of E1b (512h) and E2b (256h) vs OriginalHardestAI running in `bin_eval_512/` and `bin_eval_256/` (500 games each, 4 threads). Run JSONs: `training/runs/20260217_*.json`. Saved checkpoints: `training/models/best_model_E1b_512h.pt`, `training/models/best_model_E2b_256h.pt`. The v1 experiments (3 runs with confounds: expert data mixed in, tanh mismatch unfixed) are superseded.

**Self-play generation ACTIVE** via TheWatcher (Task Scheduler, every 5 min). ~221K games generated (8.2M records, Feb 17, growing at ~184 games/min with full fleet), targeting 500K for iteration 2+ retraining. Local: `bin/run_selfplay.bat` (double-click from Explorer, 4 threads per process, run multiple times for more CPU). EC2: `bash aws/launch_selfplay.sh c5.2xlarge 5000 1 2` — TheWatcher auto-relaunches when batches finish. GCP: `bash gcp/launch_selfplay.sh n2-standard-8 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Azure: `bash azure/launch_selfplay.sh Standard_D8als_v7 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Use `/status` slash command for a quick dashboard. Crash-safe: each run writes to timestamped `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/` subdirectory.

**AWS EC2 self-play** pipeline verified working (Feb 15-16). Boots Windows Server, downloads exe+config from S3, patches config to enable SelfPlay_CI, runs self-play, uploads shards to `s3://prismata-selfplay-data/results/` every 5 min (copy-to-temp sync), auto-terminates. AWS account on paid plan (c5 instances unlocked). vCPU quotas: 64 on-demand + 128 spot (Standard). Fleet: 8 on-demand + 16 spot c5.2xlarge = 192 vCPUs. Use `USE_SPOT=true` for spot instances (separate quota, can run both simultaneously). TheWatcher handles S3 sync, auto-relaunch, and quota-aware scale-up (confirmed working: auto-detected spot quota 64→128 increase and launched 8 additional instances within 30s).

**GCP Compute Engine self-play** pipeline set up (Feb 16). Uses same S3 bucket (hybrid cloud — GCP instances install AWS CLI). GCP project `prismata-selfplay`, zone `us-central1-a`. Quotas: N2_CPUS=200, INSTANCES=24, PREEMPTIBLE_CPUS=0 (no spot). TheWatcher monitors GCP instances and auto-relaunches. **GCP batch size fixed** (Feb 16) — GCP instances were crashing after ~8 games because `games_per_instance: 5000` → 2500 rounds/process exceeded x86 OOM threshold. EC2 used 2000 (1000 rounds/process) and worked fine. Fixed `watcher_config.json` to use 2000 for GCP too.

**Azure self-play** pipeline verified working (Feb 16-17). Multi-family deployment in North Europe: 8 VMs across D-series v7 (Dads, Dalds, Dals, Das) + F-series v7 (Fads, Falds, Fals, Fas) = 64 vCPUs (maxed). Each family has 10 vCPU quota, fits one 8-vCPU instance. Same hybrid S3 pattern as GCP. Per-family quota is 10 vCPUs default (1 D8 VM each) — spread across families to bypass. 36+ unrestricted D8 families available. Regional cap: 128 vCPUs (increased from 64, Feb 17). Support request pending for per-family increase (Dalsv7->64, Falsv7->64) to consolidate onto fewer families. TheWatcher monitors, auto-deallocates stopped VMs, auto-relaunches. Launch: `bash azure/launch_selfplay.sh Standard_D8ads_v7 1000 1 2 N`. Use `LOCATION=australiacentral` for other regions (separate Regional quota).

**Command Center dashboard** built (Feb 17). Node.js + Express web app at `dashboard/`. Run via `run_dashboard.bat` (auto-installs deps, opens browser). Features: live fleet status (AWS/GCP/Azure/Local) via SSE, data generation progress, one-click actions (refresh, S3 sync, launch AWS, train E2b), experiment browser with Chart.js training curves, watcher log viewer with filtering. Binds to `0.0.0.0` — accessible from LAN devices. Backend reads `watcher_status.json`, `watcher_config.json`, `watcher_log.txt`, training run JSONs, and walks selfplay shard dirs.

**Next actions:**
1. **Re-run tournament eval** — E1b (512h) and E2b (256h) tournament logs end at results table header with no WR data (crashed or truncated). Need to re-run: `cd bin_eval_256 && ./Prismata_Testing.exe > tournament_256h.log 2>&1`. Baseline: old model got ~3.6% WR.
2. **Implement streaming data loader** for `train.py` — current loader OOMs on full dataset (7.6M records = ~50GB). Need to stream shards from disk during training so we can use all 205K+ games.
3. **Retrain with full dataset** once streaming loader is ready — E2b (256h, LR=1e-5) is the recipe. More data should push past the ~80% val accuracy ceiling.
4. **Continue data generation** toward 500K games. Currently ~221K total (Feb 17).

**Current neural net strength:** Self-play v2 model (81.9% val acc, 63K games) — tournament eval shows **~3.6% WR** vs OriginalHardestAI (1,120 games, AB search + NeuralNet eval). Worse than expert-trained model (~10% WR). Root cause: training procedure issues (tanh mismatch, LR too high) — now fixed in v2 experiments. Tournament eval of fixed models (E1b 512h, E2b 256h) needs re-run (logs truncated, no WR data). Historical: ~42% WR vs MediumAI (expert UCT).

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
# Value-only (current approach — iteration 1 used this):
python training/train.py --selfplay-dir bin/training/data/selfplay/ --value-only --epochs 100 --batch-size 512 --lr 3e-4 --patience 15 --max-records 1000000 --num-workers 0

# Full (policy + value, once policy accuracy improves):
python training/train.py --selfplay-dir bin/training/data/selfplay/ --epochs 100 --batch-size 512 --lr 3e-4 --patience 15

# Export weights
python training/export_weights.py training/models/best_model.pt bin/asset/config/neural_weights.bin
```

**GitHub Actions self-play** (trigger from GitHub > Actions > "Self-Play Data Generation"):
- Workflow: `.github/workflows/selfplay.yml` — `workflow_dispatch` with inputs for parallel VMs (1-10), games/job, think time, VM multiplier.
- Builds `Static Release|x86` on `windows-latest` (2-core, no larger runners on free plan).
- VM think multiplier (default 1.3x) compensates for slower cloud CPUs vs local Ryzen.
- **Windows runners cost 2x minutes** — 3,000 included monthly minutes = ~1,500 actual Windows minutes. Budget exhausted Feb 16; resets monthly. EC2 Spot is more cost-effective for bulk self-play.
- Output: artifacts with binary shards in timestamped `run_*/` dirs — download and unzip into `bin/training/data/selfplay/`.
- Pushing workflow files requires `workflow` scope: `gh auth login -s workflow`.

**Expert replay pipeline** (at `c:\libraries\prismata-replay-parser\`):
```bash
node fetch_expert_replays.js    # fetch from API (incremental)
node filter_expert_replays.js   # filter (instant)
node extract_training_data.js   # extract from S3 (incremental, see args below)
```

**extract_training_data.js args**: `codesFile outputFile limit replaysFile minRating balanceFile`
- Balance filter: pass `balance_passed_codes.json` as arg 7 to reject old-balance replays
- Rating threshold: arg 6 (default 2000). Use 1500 for broader training data
- Incremental: tracks processed codes in `{output}_processed_codes.txt`, safe to re-run

## TheWatcher (Persistent Multi-Cloud Monitor)

**NEVER kill, stop, or unregister the `PrismataAI-TheWatcher` Task Scheduler job.** It runs every 5 minutes and manages AWS EC2 + GCP Compute Engine + Azure auto-relaunch, quota-aware scale-up, and S3 sync. It is harmless — it only monitors and writes status.

- **Check status**: Read `aws/watcher_status.json` (updated every 5 min automatically)
- **Change behavior**: Edit `aws/watcher_config.json` (e.g., set `selfplay.enabled: false` to pause AWS, `gcp.enabled: false` to pause GCP)
- **View log**: Read `aws/watcher_log.txt` (append-only)
- **Boot protection**: Won't auto-launch after PC restart (status goes stale >30 min). A Claude Code context or user must launch instances manually first — TheWatcher then tracks and relaunches.
- **Manual launch**: Use `bash aws/launch_selfplay.sh` (EC2), `bash gcp/launch_selfplay.sh` (GCP), `bash azure/launch_selfplay.sh` (Azure), or `bash aws/launch_tournament.sh` (eval). TheWatcher will detect them and auto-relaunch when they finish.
- **Quota-aware scale-up**: Detects unused capacity (e.g., after a quota increase) and launches additional instances to fill it. Works for both AWS (on-demand + spot separately) and GCP (N2 vCPU + instance count limits).
- **Multi-cloud quotas**: Tracks AWS quotas via `service-quotas` API and GCP quotas via `gcloud compute regions describe`. All quotas logged and visible in `watcher_status.json`.

| File | Purpose |
|---|---|
| `aws/watcher.ps1` | The script (runs via Task Scheduler) |
| `aws/watcher_config.json` | What to do — AWS (`selfplay`), GCP (`gcp`), Azure (`azure`), eval, S3 sync |
| `aws/watcher_status.json` | Current state — instance counts, quotas, batch tracking |
| `aws/watcher_log.txt` | Append-only log |

- **Reliability**: All cloud API calls go through `Invoke-CloudApi` wrapper. Relaunch requires API success. After 6 consecutive failures (30 min), force-reset. Tests: `test_watcher_e2e.ps1` (22 scenarios), `test_watcher_smoke.ps1`, `test_watcher_canary.ps1`, `test_watcher_log_health.ps1`.
- **Change detection**: Logs `CHANGE:` lines when values differ between cycles. Grep `CHANGE:` in `watcher_log.txt` to see state transitions.

## Gotchas & Non-Obvious Patterns

> Cloud provider operational details (AWS/GCP/Azure quotas, CLI quirks, encoding bugs) are in `docs/cloud-ops-reference.md`.

### Engine & Build

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping in `cardLibrary.jso`.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork (Surfinite/PrismatAlpha). Push to `PrismatAlpha`.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to stderr, does NOT abort.
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` gives 4GB. Use `"Threads": 4` + multiple bat instances. Process dies silently at ~1400 games — config uses 1000 rounds/batch, `run_selfplay.bat` loops automatically.
- **x86 OOM with large vectors**: Don't pre-allocate large `std::vector<GameState>` upfront. Allocate per-batch. Symptom: silent exit with no `[SelfPlay] COMPLETE` message.
- **Console output routing**: `[SelfPlay]` and `[Progress]` use `fprintf(stderr, ...)`. Per-turn logging only when `SaveReplays: true`. New messages in Tournament.cpp should use stderr.
- **Tournament `tests/` directory required**: `HTMLTable::appendHTMLTableToFile()` crashes (NULL `fprintf`) if `tests/` doesn't exist in the working directory. Always `mkdir tests` when setting up a new tournament directory. The cloud launcher script already handles this (line 85 of `launch_tournament.sh`).
- **GUI Watch Training / Watch Eval modes**: Menu items in Prismata_GUI. Watch Training = self-play (1s think). Watch Eval = PrismatAlpha_AB_Legacy vs OriginalHardestAI (7s think). 4 threads each. Source: `source/gui/GUIState_WatchTraining.cpp/.h`.
- **GUI/engine decoupling**: Engine has zero SFML imports — compiles independently. GUI is ~4,100 LOC. SFML doesn't support WASM — web needs SDL2 abstraction or JS rewrite.
- **Churchill paper URLs**: Use `davechurchill.ca/publications/` (old `cs.mun.ca/~dchurchill/` is dead).

### Self-Play & Data

- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **Self-play crash safety**: Each run writes to `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/`. Restart anytime — only in-flight games lost.
- **Run self-play from Explorer**: Use `bin/run_selfplay.bat`. Has startup exe check and 5s error delay to prevent spin-looping during rebuilds.
- **Selfplay shard CRC**: CRC check fails on shards from crashed/in-progress runs (no footer). Use `validate_crc=False` for live data.
- **Selfplay positions per game**: ~37 records/game (both players' turns), NOT ~440. A 10K-game run yields ~370K records.
- **Selfplay shard binary format**: Header 64 bytes (magic, version, feature_dim, record_size, record_count, endian_check, padding) + 4-byte CRC32 footer. Record size = 7152 bytes. Games = `(file_size - 68) / 7152 / ~37`. See `training/load_selfplay.py` for `HEADER_SIZE = 64`.
- **Selfplay game counting**: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-68)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>68); print(f'{total} records, ~{total//37} games')"`.
- **S3 download dir structure**: `aws s3 sync` creates timestamp dirs without `run_` prefix containing nested `run_*` subdirs. Must scan recursively.
- **Self-play uses playout eval**: `SelfPlay_CI` runs `OriginalHardestAI_1s` vs itself (playout eval, 1s think). The neural net is NOT used for game generation — only for position labeling. Data quality depends on playout AI strength, not model WR. ~4 games/min per 4-thread process.
- **PID-based random seeding**: All 3 exe entry points use `srand(time ^ PID)` — prevents identical sequences when launching multiple instances in the same second.
- **Game_id namespacing**: `load_selfplay.py` offsets game_ids by 1M per source dir to prevent collisions across runs and train/val split leakage.
- **Value-only model export**: `export_weights.py` exports zero-initialized policy tensors for value-only models (4 extra). C++ loader requires all 26 tensors — a 22-tensor export will fail.
- **SelfPlayDataExport requires loaded neural net**: If `neural_weights.bin` fails to load, exe writes ZERO shards silently. Only stderr warning. Always verify 26 tensors.

### Training

- **Training CRC**: `train.py` uses `validate_crc=False` — required because in-progress/crashed shards lack CRC footers.
- **Training overfitting**: V2 experiments (Feb 17) confirmed: smaller model (256h) trains longer and achieves better calibration. LR controls overfitting speed but not ceiling. Loss function (MSE vs BCE) is a wash. Subsampling hurts. See run JSONs in `training/runs/20260217_*.json`.
- **Training RAM limit**: Full dataset (7.6M records) = ~50GB. With 32GB RAM: max ~1M records with `--max-records 1000000`. Use `--num-workers 0`. Need streaming loader for full dataset.
- **Training RAM: max 2 concurrent jobs**: Running 3 `train.py` jobs simultaneously OOMs during `np.concatenate` in `load_all_shards` (32GB RAM). Safe limit: 2 concurrent runs with `--max-records 1000000`.
- **best_model.pt gets overwritten**: Each `train.py` run writes to `training/models/best_model.pt`. Copy to a unique filename immediately after a run finishes if you need to preserve it.
- **C++ NeuralNet hidden_dim is dynamic**: `_hiddenDim` is read from the weight file header, not hardcoded. Can deploy 256h or 512h models by just exporting different weights — no C++ rebuild needed.
- **Tournament output needs `2>&1`**: Tournament progress/results use `fprintf(stderr, ...)`. Redirect with `> log.txt 2>&1` to capture. Without this, only per-turn buy actions (stdout) are logged.
- **Parallel tournament eval**: Use separate directories (`bin_eval_X/`) each with own exe, config.txt, cardLibrary.jso, and neural_weights.bin to run multiple tournaments simultaneously.
- **D: drive backup**: `D:\PrismataAI_backup\` has selfplay data, models, weights, config, run logs. Created Feb 15.
- **Experiment logs**: `training/runs/{timestamp}.json` — full per-epoch metrics, hyperparameters, git hash.

### Windows & Python Environment

- **Windows file size caching**: `ls`/`Get-ChildItem` may show 0 bytes for files with open write handles. Use `python -c "import os; print(os.path.getsize(path))"`.
- **`nohup &` broken in Git Bash on Windows**: Background processes get killed when the bash shell exits. Use the Bash tool's `run_in_background` parameter instead, or launch from a persistent cmd/PowerShell window.
- **Python stdout buffering**: Long-running Python processes show no output in Claude Code Bash tool. Use `PYTHONUNBUFFERED=1` prefix.
- **Python cp1252 on Windows**: Python defaults to cp1252 for stdout. Use `PYTHONIOENCODING=utf-8` or stick to ASCII.
- **PowerShell JSON files have UTF-8 BOM**: `watcher_status.json` and `watcher_config.json` written with BOM. Python: use `encoding='utf-8-sig'`.

### Historical / Concluded

- **Blend tournaments concluded**: Neural component hurts. Don't revisit until model >60% val accuracy. See `docs/blend-tournament-results.md`.
- **Batch validation**: 287 replays tested, 117 PASS (41.3%), 166 FAIL (TS-side). Not blocking self-play.
- **Replay balance validation**: `validate_balance_all.js` checks costs against `cardLibrary.jso`. Output: `balance_passed_codes.json` (32,973 codes). Incremental via `balance_results.json`.

### Dashboard

- **BOM stripping required**: `watcher_status.json` and `watcher_config.json` have UTF-8 BOM from PowerShell. Server.js strips with `raw.replace(/^\uFEFF/, '')`.
- **fs.watchFile, not fs.watch**: `fs.watch` is unreliable on Windows for network/mapped drives. `fs.watchFile` polls at 5s interval — reliable but uses CPU. 200ms debounce for half-written files.
- **Git Bash for bash scripts**: Action system spawns bash scripts with `shell: 'C:/Program Files/Git/bin/bash.exe'`. Python actions use `PYTHONUNBUFFERED=1`.
- **LAN access**: Server binds to `0.0.0.0:3000`. Logs local LAN IP on startup. Firewall may need port 3000 opened for other devices.
- **Double-launch prevention**: `activeOps` Map tracks running child processes by action name. Returns 409 if same action already running.
- **getDataStats() header size bug**: `server.js` line 112 uses `(size - 16) / 7152` but correct header is 64 bytes. Should be `(size - 68) / 7152`. Causes minor overcount of records/games on Data Generation panel.

### External Tools

- **claude-mem 10.0.7**: Bug #1104 filed. Chroma runs manually on port 8000. **Update when >10.0.7 available.**
- **Future feature plans in claude-mem**: GUI spectator mode (#1385), web-based remote advisor (#1524). Use MCP search to retrieve.

## Session Close-Out

When the user says "wrapping up", "closing context", or "save everything":
1. Check for undocumented results (experiments, tournaments, benchmarks) — if any exist only in conversation, write them to appropriate docs
2. Update any stale plan/results docs with actual outcomes (e.g., mark plans COMPLETE, add results tables)
3. Map any unnamed artifacts to human-readable names (e.g., run timestamps → experiment names)
4. Run `/revise-claude-md` for CLAUDE.md status and gotcha updates
5. List anything still only in conversation context so the user knows what would be lost

## User Preferences

- Efficiency over speed — minimize API credits, maximize local PC computation
- Comfortable with long-running unattended tasks (hours). Tell them when something can run overnight.
- Git comfort level: self-described "noob" — explain git ops clearly, always confirm before push/force
- The user is "Surfinite" everywhere — GitHub, Prismata, Discord, etc.

## Key Architecture

### Engine Internal Name System

Common mappings (full 105-unit table in `cardLibrary.jso`):

| Internal Name | Display Name | | Internal Name | Display Name |
|---|---|---|---|---|
| Tesla Tower | Tarsier | | Brooder | Blastforge |
| Treant | Steelsplitter | | Elephant | Rhino |
| Blood Barrier | Forcefield | | Minicannon | Gauss Cannon |
| House | Husk | | Flame Kin | Gauss Charge |

All script references in `cardLibrary.jso` must use **internal names**, not display names.

### Game Phases & Turn Numbering

Action → Breach (if wipeout) → Confirm → Defense (if enemy has attack) → Swoosh → next player's Action. `m_turnNumber` increments once per **player-turn** (not per round). Frontline kills happen during Action phase via `ASSIGN_FRONTLINE`.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval (branching factor 5 from PPPortfolio). **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): resource values ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50. Cost-based material counting — not strategic value.

**Neural net**: 2-layer ResNet, 512 hidden, state_dim=1785, policy+value heads. C++ inference via `NeuralNet::Instance()`. ~2,000 evals/sec/core.

### Training Approach

**Phase 1: Supervised** (DONE) — 544K examples total (see Training Data Inventory), 57.7% val accuracy (weak but provides real signal).
**Phase 2: Self-Play** (ITERATION 1 DONE) — 12K games, 77% val acc (value-only), severe overfitting after epoch 1. Need more data or regularization. Churchill got 58.8% WR vs playout with 500K games.
**Phase 3: Iterative RL** (future) — AlphaZero-style loop. Keep expert data in mix (start 50/50, never below 20%).

### Training Data Inventory

| Dataset | File | Replays | Examples | Min Rating |
|---|---|---|---|---|
| Expert 2000+ | `training_data.jsonl` | ~13,157 | ~251K | 2000 |
| Expert 1500+ | `expert_1500_training_data.jsonl` | 15,010 | 269K | 1500 |
| Community (Discord/tournament/Reddit) | `community_training_data.jsonl` | 2,468 | 24K | 2000 |

All datasets at `c:\libraries\prismata-replay-parser\`. All balance-validated. Community replays use embedded replay ratings (not metadata file).

### Hardware

AMD Ryzen 7 5700X3D (8c/16t), 32GB RAM, Intel Arc B580 (12GB VRAM). Self-play generation: ~4 games/min per 4-thread instance (~16 games/min with 4 instances). Training: ~30 min on CPU.

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
| `source/gui/GUIState_WatchTraining.cpp/.h` | Watch Training/Eval GUI — live display + training data generation |
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
| `aws/launch_tournament.sh` | EC2 tournament fleet launcher (supports NUM_INSTANCES, WEIGHTS_KEY, MODEL_LABEL env vars) |
| `aws/deploy_for_eval.sh` | Upload exe/config/weights to S3 for EC2 tournament eval |
| `aws/download_results.sh` | Download self-play results from S3 |
| `aws/sync_results.bat` | S3 → local sync for self-play results (Task Scheduler compatible) |
| `aws/test_watcher_smoke.ps1` | Smoke test — status freshness, Task Scheduler, API health |
| `aws/test_watcher_canary.ps1` | Canary check — independent cloud API connectivity test |
| `aws/test_watcher_log_health.ps1` | Log anomaly detection — stuck state, thrashing, errors |
| `aws/test_watcher_e2e.ps1` | E2E decision logic tests (22 scenarios, no cloud calls) |
| `aws/watcher.ps1` | TheWatcher — persistent monitor + auto-relauncher (Task Scheduler) |
| `aws/watcher_config.json` | TheWatcher config (edit to change behavior) |
| `aws/watcher_status.json` | TheWatcher status (read for current state) |
| `aws/watcher_log.txt` | TheWatcher append-only log |
| `gcp/launch_selfplay.sh` | GCP Compute Engine self-play launcher (uploads to S3, auto-deletes) |
| `gcp/.aws_credentials` | AWS credentials for GCP→S3 uploads (gitignored, not committed) |
| `azure/launch_selfplay.sh` | Azure VM self-play launcher (Windows VMs, auto-terminate) |
| `azure/.aws_credentials` | AWS credentials for Azure→S3 uploads (gitignored, not committed) |
| `dashboard/server.js` | Command Center backend (Express + SSE + action system) |
| `dashboard/public/` | Command Center frontend (HTML + CSS + vanilla JS + Chart.js) |
| `run_dashboard.bat` | One-click dashboard launcher (auto-installs deps, opens browser) |
| `c:\libraries\prismata-replay-parser\` | TS replay parser + data extraction scripts |
| `c:\libraries\DiscordChatExporter\` | Discord message export tool (CLI at `cli/`) |
| `c:\libraries\prismata-replay-parser\validate_balance_all.js` | Balance validation across all replay sources |
| `c:\libraries\prismata-replay-parser\balance_passed_codes.json` | 32,973 balance-validated replay codes |

## Documentation Index

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full chronological dev history (sections 1-29) |
| `docs/plans/2026-02-15-selfplay-training-master-plan.md` | Current execution plan (iteration 1 complete, iteration 2 pending) |
| `docs/plans/2026-02-14-selfplay-10k-generation-and-training.md` | Earlier 10K-game generation plan (superseded by master plan) |
| `docs/plans/opening-book-plan.md` | Opening book extraction plan (DONE) |
| `docs/plans/engine-validation-plan.md` | Engine validation plan (DONE) |
| `docs/plans/2026-02-16-azure-compute-plan.md` | Azure compute integration plan (DONE — D8als_v7 in North Europe) |
| `docs/plans/2026-02-17-hyperparameter-experiments.md` | Hyperparameter experiment plan v1 (overfitting fix, Churchill/Lc0 research) |
| `docs/plans/hyperparameter-experiments-v2.md` | **CURRENT** experiment plan v2 (tanh fix, 6 expert critiques, phased approach) |
| `docs/selfplay-worker-instructions.md` | Source-verified self-play implementation spec |
| `docs/blend-tournament-results.md` | Blend tournament results (CONCLUDED) |
| `docs/session-logs/` | Historical parallel session logs (ctx1-4, selfplay progress) |
| `docs/backup_claude_md_2026-02-14/` | Backup of all original CLAUDE*.md files |
| `training/FEATURES.md` | Neural net feature layout specification |
| `docs/WEIGHT_FORMAT.md` | Binary weight format specification |
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference (from wiki) |
| `docs/wiki/` | Full wiki dump (448 pages, raw wikitext) |
| `docs/plans/reproducibility-plan.md` | Training reproducibility standard (seeds, determinism) |
| `docs/cloud-ops-reference.md` | Cloud provider operational gotchas (AWS/GCP/Azure) |
| `~/.claude/plans/bubbly-tinkering-kahan.md` | Prioritized development guide (roadmap research synthesis) |
| `~/.claude/plans/roadmap-phase2-instructions.md` | Phase 2 execution instructions (tournament eval, streaming loader, retrain) |
| `~/.claude/plans/prismata-command-center-build.md` | Command Center build plan + full source code appendix |

## Tournament Results Summary

| Matchup | Games | Win Rate | Notes |
|---|---|---|---|
| PrismatAlpha_UCT vs MediumAI | 60 | 41.7% | Neural eval has real signal |
| PrismatAlpha_UCT vs OriginalHardestAI | 64 | 10.9% | Weak but not random |
| PrismatAlpha_AB vs MediumAI | 128 | 43.8% | Search type doesn't matter |
| HardestAI vs OriginalHardestAI | 60 | 50.0% | Track A fixes are neutral |
| RandomAI vs MediumAI | 100 | 0% | Baseline floor |
| EasyAI vs MediumAI | 100 | 6% | Baseline |
| Self-play v1 training | 16 ep (early stop) | 76.9% val acc | 10K games, epoch 1 best, value-only |

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
- `extract_all_discord_codes.js` — extract codes from ALL channel messages (not just Giselle)
- `extract_tournament_codes.py` — extract codes from tournament data text
- `validate_tournament_codes.js` — validate codes against S3 (HTTP 200 check, concurrency-limited)
- `validate_balance_all.js` — validate unit costs across all sources against `cardLibrary.jso`

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
| HPS Paper (AIIDE 2015) | https://davechurchill.ca/publications/pdf/aiide15_churchill_prismata.pdf |
| Replay API Wiki | https://prismata.fandom.com/wiki/Replay_API |
| prismata-stats | https://gitlab.com/prismata-stats/v3/-/tree/dev |

**Note:** The [Prismata Wiki](https://prismata.fandom.com/wiki/) has unit pages with costs, stats, abilities, and strategy notes. Use `WebFetch` to check game rules, unit interactions, or verify card data against `cardLibrary.jso` when needed.
