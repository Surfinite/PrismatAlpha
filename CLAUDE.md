# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play training: see `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (Feb 21, 2026)

**Run B 722K-game 256h/3L model: 51.9% WR vs OriginalHardestAI** (2,016 games, CI [49.7%, 54.1%], 12 spot c5.2xlarge). First model to cross 50% WR. Trained on 722K games (27M records), 256h/3L (R12_smooth90), lr=2e-5, dropout=0.20, label_smooth=0.90, tanh+MSE, 85.6% val accuracy, 10 epochs (step 415K). Weights: `bin/asset/config/neural_weights_run_B_256h3L.bin`. Previous champion: 305K model (45.3% WR, 256h/2L) at `neural_weights_305k.bin`. Other models: `neural_weights_run_A_256h2L.bin` (256h/2L, step 20K), `neural_weights_selfplay_v1.bin` (iter 1, 77% val acc, 10K games), `neural_weights_expert_backup.bin` (expert-trained).

**T4 hyperparameter plan COMPLETE (Feb 19).** 12 experiments on GCP L4 in 41 min. Winner: R12_smooth90 (256h/3L, lr=2e-5, dropout=0.20, label_smooth=0.90, val_loss=0.4875). But **tournament showed data > hyperparameters**: R12 trained on 500K records got 19.3% WR (11,060 games), while E2b trained on 2.3M records got 28.9% WR (3,400 games). The 16GB RAM limit on g2-standard-4 forced `--max-records 500000`, nullifying architecture gains. Results: `s3://prismata-selfplay-data/training-runs/plan_2026-02-19_02-27-22/`. Weights: `bin/asset/config/neural_weights_R12_smooth90.bin` (256h/3L, 871K params). Plan: `docs/plans/2026-02-18-t4-training-plan.md`.

**Training pipeline hardened (Feb 19).** 6 fixes from pre-training code review: (1) `max_records` overshoot trimmed in `load_selfplay.py`, (2) streaming mode label sanity check added (samples 10K records at startup), (3) `--num-workers` default lowered from 8→2 (safe for 16GB cloud), (4) LR scheduler state saved/restored on checkpoint resume, (5) double-tanh fix in `export_weights.py` verification for `use_tanh=True` models, (6) vectorized O(N) subsampling loops in both `train.py` and `load_selfplay.py`. These changes have been deployed to S3 (`s3://prismata-selfplay-data/deploy/training/`).

**V2 hyperparameter experiments COMPLETE (Feb 17).** 9 experiments across 3 phases (loss function, LR sweep, data & capacity). Winner: E2b (hidden_dim=256, LR=1e-5, tanh+MSE, 739K params) — Brier 0.1213, best at step 10000. Key findings: (1) model capacity matters most — smaller model trains longer before overfitting, (2) LR controls overfitting speed but not ceiling, (3) loss function (MSE vs BCE) is a wash, (4) subsampling hurts. **Tournament eval COMPLETE (Feb 17):** 24 EC2 c5.2xlarge instances (12 per model), 2 workers each, ~1,008 games per model vs OriginalHardestAI. Results: **E2b (256h) = 26.7% WR** (269.5/1,008), **E1b (512h) = 19.6% WR** (197.5/1,008). Previous baseline was 3.6% — 5-7x improvement from v2 hyperparameter fixes (tanh activation, proper LR). Run JSONs: `training/runs/20260217_*.json`. Saved checkpoints: `training/models/best_model_E1b_512h.pt`, `training/models/best_model_E2b_256h.pt`. The v1 experiments (3 runs with confounds: expert data mixed in, tanh mismatch unfixed) are superseded.

**Self-play generation ACTIVE** via TheWatcher (Task Scheduler, every 5 min). **~722K games generated (Feb 20 audit: 7,804 shards, 26.7M records, 178 GB in S3)**, targeting 1M for iteration 2+ retraining. Local: `bin/run_selfplay.bat` (double-click from Explorer, 4 threads per process, run multiple times for more CPU). EC2: `bash aws/launch_selfplay.sh c5.2xlarge 5000 1 2` — TheWatcher auto-relaunches when batches finish. GCP: `bash gcp/launch_selfplay.sh n2-standard-8 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Azure: `bash azure/launch_selfplay.sh Standard_D8als_v7 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Use `/status` slash command for a quick dashboard. Crash-safe: each run writes to timestamped `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/` subdirectory.

**AWS EC2 self-play** pipeline verified working (Feb 15-16). Boots Windows Server, downloads exe+config from S3, patches config to enable SelfPlay_CI, runs self-play, uploads shards to `s3://prismata-selfplay-data/results/` every 5 min (copy-to-temp sync), auto-terminates. AWS account on paid plan (c5 instances unlocked). vCPU quotas: 192 on-demand + 300 spot (Standard, increased from 256 Feb 18). **AWS selfplay DISABLED (Feb 19)** (`selfplay.enabled: false` in watcher_config.json). Re-enable when needed. Spot-only mode was active (`spot_only: true`). Previous fleet: 37 spot c5.2xlarge = 296 vCPUs (~$5.18/hr). Cost per 1K games: $0.32 spot, $0.88 OD. TheWatcher handles S3 sync, auto-relaunch, and quota-aware scale-up (confirmed working: auto-detected spot quota 64→128→256→300 increases and launched additional instances within 30s). **Note:** `launch_selfplay.sh` only supports 1 instance per invocation — use a bash loop for bulk launches (sequential to avoid temp file race).

**AWS GPU training pipeline TESTED AND WORKING (Feb 19).** `aws/launch_training.sh` launches GPU spot instances in eu-north-1. Default: `g6.2xlarge` (NVIDIA L4, 24GB VRAM, 32GB RAM, ~$0.40/hr spot). AMI: `ami-0bd05d88ea8c3e277` (Deep Learning OSS PyTorch 2.6, Amazon Linux 2023, venv at `/opt/pytorch/`). Downloads training code (5 files including `unit_index.json`) + selfplay data from S3 (~183GB shards, ~22 min download), trains with `--device cuda`, exports weights, uploads results to `s3://prismata-selfplay-data/training-runs/<label>/`, auto-terminates. Uses `request-spot-instances` (queues for capacity instead of instant-fail). Supports env var config (HIDDEN_DIM, LR, EPOCHS, NUM_LAYERS, INSTANCE_TYPE, etc.). **GPU quota APPROVED (Feb 19)** — G/VT Spot = 8 vCPUs. Available types: `g6.2xlarge` (L4, 8 vCPU, 32GB, $0.40/hr — **recommended**), `g6.xlarge` (L4, 4 vCPU, 16GB, $0.35/hr), `g4dn.xlarge` (T4, 4 vCPU, 16GB, $0.20/hr). S3 selfplay data is ~178GB .bin shards (~722K games), crash dumps cleaned. Training code deployed: `s3://prismata-selfplay-data/deploy/training/`.

**GCP GPU training ACTIVE (Feb 20).** `gcp/launch_training.sh` launches Linux DL VM with GPU. Default: `g2-standard-4` + L4 (on-demand). **Use `MACHINE_TYPE=g2-standard-8` for full-dataset streaming** (16GB OOMs). Script creates 16GB swap automatically. Image: `pytorch-2-7-cu128-ubuntu-2204-nvidia-570` (PyTorch 2.7, CUDA 12.8). GPU quotas in us-central1: `NVIDIA_L4_GPUS=1`, `NVIDIA_T4_GPUS=1`, `NVIDIA_V100_GPUS=1` (on-demand and preemptible each). **`GPUS_ALL_REGIONS=1`** is the project-level gate — only 1 GPU instance at a time across all regions. GCP billing upgraded from free trial Feb 16 (credits still apply). Script supports env var config: `HIDDEN_DIM`, `LR`, `NUM_LAYERS`, `WARMUP_EPOCHS`, `DROPOUT`, `WEIGHT_DECAY`, `LABEL_SMOOTH`, `RESUME_FROM`, `GPU_TYPE`, `MACHINE_TYPE`. Uses `--streaming` for large datasets. Downloads all selfplay data from S3 (~94GB, needs 250GB disk). Auto-deletes on completion. Training plan: `docs/plans/2026-02-18-t4-training-plan.md`.

**GCP Compute Engine self-play** pipeline set up (Feb 16). Uses same S3 bucket (hybrid cloud — GCP instances install AWS CLI). GCP project `prismata-selfplay`, zone `us-central1-a`. Quotas: N2_CPUS=200, INSTANCES=24, PREEMPTIBLE_CPUS=0 (no spot), **CPUS_ALL_REGIONS=48 (increased from 12, Feb 18)**. Fleet: 6x n2-standard-8 = 48 vCPUs. $300 free credit (90 days from Feb 16). TheWatcher monitors GCP instances and auto-relaunches. **GCP crash fix (Feb 18):** Instances dying after ~8 games was NOT Defender — root cause was stale exe in S3 with latent stack buffer overrun (0xc0000409) triggered by GCP's VM memory layout. Fresh rebuild + deploy to S3 fixed it. Defender exclusions (`Add-MpPreference`) and `windows-2022` image (switched from `windows-2022-core`) kept as belt-and-suspenders. Boot disk switched from `pd-ssd` to `pd-standard` (SSD_TOTAL_GB quota = 250, only fits 5 instances; CPU-bound workload doesn't need SSD). **GCP batch size fixed** (Feb 16) — `games_per_instance: 5000` → 2500 rounds/process exceeded x86 OOM threshold. Fixed to 2000. **GCP quota gate**: Must wait 48 hours from account creation before GCP accepts quota increase requests. Account created Feb 16, eligible Feb 18+.

**Azure self-play PAUSED and CLEANED (Feb 18).** Azure on-demand is ~2x more expensive per vCPU-hr than AWS spot ($0.091-0.122 vs $0.052). Azure spot unavailable (confirmed by email). Fleet stopped, all resources deleted (only 1 VNET remains, free). Azure billing has 24-48hr lag — charges may appear after cleanup but will stop. ~£65 over free credit charged to card. Pipeline verified working (Feb 16-17). **Fleet rebuilt Feb 17** — 16 VMs across 16 families (8x v7 + 8x v6, D/F series) = 128 vCPUs (regional cap maxed). v7 families: D8als, D8ads, D8as, D8alds, F8als, F8ads, F8as, F8alds. v6 families: D8as, D8ads, D8als, D8alds, F8as, F8als, D8s, D8ds. Each runs 5,000 games at ~3.5 games/min. Multi-family deployment bypasses per-family 10 vCPU limits. Same hybrid S3 pattern as GCP. Regional cap: 128 vCPUs (increased from 64). **IMPORTANT: `az vm delete` does NOT cascade** — orphaned NICs, public IPs, OS disks, NSGs persist and bill. After deleting VMs, run full cleanup (see `docs/cloud-ops-reference.md` → "Azure orphaned resources"). TheWatcher monitors, auto-deallocates stopped VMs, auto-relaunches. Launch: `bash azure/launch_selfplay.sh Standard_D8ads_v7 5000 1 2 N`. Use `LOCATION=australiacentral` for other regions (separate Regional quota).

**Command Center dashboard** built (Feb 17). Node.js + Express web app at `dashboard/`. Run via `run_dashboard.bat` (auto-installs deps, opens browser). Features: live fleet status (AWS/GCP/Azure/Local) via SSE with 30s heartbeat, data generation progress with estimated game rate, config-driven actions from `dashboard/actions.json` (refresh, S3 sync, launch AWS, train E2b), experiment browser with Chart.js training curves and multi-experiment overlay (Ctrl+click up to 3), watcher log viewer with filtering, ARIA accessibility attributes. Auth: Bearer token + CSRF Origin check. Conditional file watchers (only active when SSE clients connected). Binds to `0.0.0.0` — accessible from LAN devices.

**Streaming data loader VERIFIED WORKING (Feb 17, rewritten Feb 20).** Header-only indexer reads 64 bytes per shard (not full data). Shard-level train/val split (`shard_idx % 10 == 0` → val) — no game_id reads needed since games never span shards. LRU file handle cache with 8K FD limit (raised via `ctypes._setmaxstdio`). Multi-worker DataLoader (`--num-workers 2-4`) supported via lazy init pattern. Uses ~12GB RAM at peak (vs 50GB+ without streaming).

**Intel Arc B580 XPU acceleration ENABLED (Feb 17).** PyTorch 2.10.0+xpu installed globally, IPEX removed, native `torch.xpu` backend. New CLI flags: `--device` (force cpu/xpu/cuda), `--amp` (BF16), `--compile` (torch.compile, needs MSVC). Benchmark (100K records, bs=512, seed 42): **XPU+nw4: 13s/epoch vs CPU: 42s/epoch (3.2x per-epoch, 4.5x total)**. BF16 (`--amp`) adds overhead at this model size — skip it. Multi-worker data loading confirmed working (`num_workers=4` is optimal). Earlier "pickle bug" failures were transient Windows handle exhaustion from memory pressure, not a real incompatibility. Plan: `~/.claude/plans/intel-arc-b580-xpu-acceleration-v2.md`. **Production command: `--device xpu --num-workers 4`.**

**Heuristic buy/breach fixes IMPLEMENTED (Feb 21).** EffectiveBuyCost subtracts created sub-unit value from parent card cost (fixes Borehole→Pixie, Corpus→Husk overvaluation). `BuyAttackValue_Improved`/`BuyBlockValue_Improved` use effective cost. Breach targeting gives proportional partial-value density for non-lethal hits (fixes ignoring Drone over cheap Galvani). All gated behind `_legacy` flag — OriginalHardestAI unchanged. **Eval in progress**: 12 spot c5.2xlarge running 3 tournaments (Neural+improved vs Original, Playout+improved vs Original, Neural improved vs legacy). Results: `eval-results/heuristic_eval_*/`. Files: `Heuristics.cpp` (EffectiveBuyCost, improved buy functions), `PartialPlayer_Breach_GreedyKnapsack.cpp` (partial-value density), `AIParameters.cpp` (wiring). Config: `BreachGreedyKnapsack_Legacy` added for legacy iterators.

**Next actions:**
1. ~~**Retrain R12 with full dataset**~~ — DONE (Feb 21). Run B: 256h/3L, 722K games, 10 epochs on GCP L4, 51.9% WR (2,016 games). New champion. Deploy as `neural_weights.bin` for advisor/autopilot use.
2. **Continue data generation** toward 1M games. **AWS selfplay DISABLED (Feb 19)** (`selfplay.enabled: false` in watcher_config.json). **GCP selfplay ACTIVE** (6x n2-standard-8, 48 vCPUs, `gcp.enabled: true`). Azure paused and cleaned. **~722K games generated (Feb 20 audit: 7,804 shards, 26.7M records, 178 GB in S3).** Local selfplay via `run_selfplay.bat` is free.
4. ~~**256h 305K-game eval**~~ — DONE (Feb 18). 45.3% WR (4,032 games). Major milestone — up from 26.7% with 63K games.
5. ~~**Fix streaming DataLoader multi-worker support**~~ — DONE (Feb 17). Lazy init pattern in `MemmapSelfPlayDataset` enables `num_workers>0`. Use `--num-workers 2` for streaming to avoid RAM thrashing (4 causes 94% RAM on 32GB).
6. ~~**Enable Intel Arc B580 GPU acceleration**~~ — DONE (Feb 17). See above.
7. ~~**Build overlay advisor**~~ — DONE (Feb 18). C++ `--suggest` mode + Python overlay (`tools/prismata_advisor.py`) + launcher (`run_advisor.bat`). Run: double-click `run_advisor.bat`, press F6 in Prismata. Plan: `docs/plans/2026-02-18-prismata-overlay-advisor.md`.
8. ~~**Live game state tracking in sniffer**~~ — DONE (Feb 20). Auto-F6 at turn boundaries via Win32 SendInput, clipboard capture, mid-turn click tracking, JSON + console output. See sniffer gotchas below. **Not yet live-tested.**
9. ~~**Build live AI commentator — Phase 1 (text + chat)**~~ — DONE (Feb 20). Claude Haiku generates per-turn strategic commentary, injected as in-game PM via sniffer proxy. Adaptive token budget: short/punchy for fast turns (40 tokens), expanded colour for long thinks (120 tokens, >=15s threshold). Chat target defaults to Surfinite (self-PM); set `CHAT_TARGET=<id>` env var to redirect. Tested live on spectated games. Plan: `docs/plans/2026-02-20-live-commentator-plan.md`. Knowledge base: `docs/commentary-knowledge/`. **Phase 2 (TTS + OBS)** still planned — needs `edge-tts`, `sounddevice`, `obsws-python`, VB-Cable.
10. **Post-game commentary from replay data** — WORKFLOW ESTABLISHED (Feb 21). Full instructions: `docs/plans/commentary-generation-instructions.md`. Tool: `python tools/generate_commentary_data.py "CODE" --think-time 50` (C++ analysis), `--validate` (resource-validated buys), `--eval-only` (neural eval only). Discord posting: `python tools/discord_post_helper.py bin/commentary_{CODE}.txt` (clipboard mode). Webhook mode planned (needs channel webhook URL from Prismata Discord mod). Commentary files: `bin/commentary_*.txt` with `== MESSAGE N ==` delimiters (<2000 chars each for Discord). Community reception positive (3 games commentated). **Known limitation**: click-based buy counting can't distinguish successful purchases from failed clicks (sold-out OR insufficient resources) — `--validate` flag handles this with resource simulation.
11. ~~**Build autopilot — AI move injection via TCP proxy**~~ — DONE (Feb 20). `--suggest` now outputs `clicks` array with wire-protocol-ready `{_type, _id}` pairs. Python autopilot engine captures state (Shift+F6), runs AI, injects Click/EndTurn messages through sniffer proxy. Semi-auto (file trigger) and full-auto (StartTurn callback) modes. Dry-run mode for testing. Launch: `run_prismata_tools.bat --autopilot`. **Proxy integration verified (Feb 20): game traffic flows, StartTurn detected, bot-game check works. Not yet tested with actual bot game click injection.** Plan: `~/.claude/plans/sequential-launching-mountain.md`.
12. ~~**C++ replay ingestion mode**~~ — ALL 3 PHASES DONE (Feb 21). `ReplayStepper` class converts replay click sequences into GameState transitions, outputs binary shards (same format as self-play). CLI modes: `--replay`/`--replay-dir` (training shards), `--eval` (per-turn neural evaluation JSON), `--analyze` (AI vs expert buy comparison JSON with agreement rate). **96.6% extraction rate** (12,852/13,299 turns from 500 expert replays, 291/500 error-free). Branch: `feature/cpp-replay-stepper`. Plan: `docs/plans/2026-02-20-cpp-replay-mode.md`.
13. ~~**GUI analysis enhancements**~~ — ALL 7 PHASES DONE (Feb 21). Policy fix, gold prediction, eval bars (Shift+E/W), parallel async eval (`std::async`), human turn advice (F7), eval history graph + CSV export, card value overlay (V: labels). PrismatAlpha → PrismatAI naming consolidation (7 files). Branch: `feature/cpp-replay-stepper`. Plan: `docs/plans/2026-02-21-gui-enhancement-plan-v2.md`.

**Current neural net strength:** **Run B 256h/3L 722K model = 51.9% WR** vs OriginalHardestAI (2,016 games, CI [49.7%, 54.1%], AB search + NeuralNet eval, Feb 21). First model to cross 50%. Up from 45.3% with 305K model (330K games, 256h/2L). **512h confirmed worse** — Run C (512h/2L) peaked at step 15K (val_loss=0.5127, val_acc=77.5%), overfitting after. Terminated Feb 20. Previous: E2b (63K) = 26.7%, E1b (512h, 63K) = 19.6%, unfixed model = 3.6%. Historical: ~42% WR vs MediumAI (expert UCT). Churchill got 58.8% WR vs playout with 500K games — we're at 51.9% with 722K games, closing the gap.

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
python training/train.py --selfplay-dir bin/training/data/selfplay/ --value-only --epochs 100 --batch-size 512 --lr 3e-4 --patience 15 --max-records 1000000

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
- **Boot protection**: Won't auto-launch after PC restart (status goes stale >30 min). A Claude Code context or user must launch instances manually first — TheWatcher then tracks and relaunches. **Also triggers during RAM thrashing** — if watcher can't run a cycle for >30 min (e.g., training with too many workers), status goes stale and boot protection engages. Recovery: manually launch instances, then watcher resumes tracking.
- **Spot-only mode**: Set `selfplay.spot_only: true` in watcher_config.json to prevent on-demand launches. Watcher respects this in both relaunch and scale-up code paths.
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
- **Change detection**: Logs `CHANGE:` lines when values differ between cycles. Grep `CHANGE:` in `watcher_log.txt` to see state transitions. Cost shift >$1/hr also triggers change detection. Log lines now include `cost=$X.XX/hr`.
- **Fleet health checks**: When investigating compute costs, check ALL resource types — not just running VMs. Orphaned disks, NICs, IPs, and NSGs persist after VM deletion and bill silently. See `docs/cloud-ops-reference.md` → "Fleet Health Checks" for per-provider commands (Azure/AWS/GCP). **Warning**: `shard_activity.last_new_shard` in `watcher_status.json` is unreliable (see Cloud Operations gotchas) — use actual S3 data growth or instance counts to verify fleet health.
- **Watcher hangs under memory pressure**: When system RAM thrashing is severe (>90% RAM, high page faults), cloud API calls (gcloud, aws, az) can't spawn and the watcher hangs indefinitely. Task Scheduler shows error code 267009. **Recovery**: `Stop-ScheduledTask -TaskName 'PrismataAI-TheWatcher'; Start-Sleep 2; Start-ScheduledTask -TaskName 'PrismataAI-TheWatcher'`. Root cause must also be fixed (e.g., reduce training workers) or watcher will hang again.
- **Instance counting is unconditional (Feb 20 fix)**: GCP and Azure instances are always counted even when `provider.enabled=false` — prevents blind spots where running instances are invisible in status/cost tracking. Only relaunch and active operations (cleanup, quota checks) are gated behind the enabled flag. Logs `WARNING` when instances detected but provider disabled.
- **v2 enhancements** (branch `feature/watcher-enhancements-v2`, NOT yet merged to master): Three new monitors: (1) **Cost estimation** — per-provider hourly cost tracking with rate table for 19 Azure VM sizes + AWS + GCP, new `cost_estimate` field in status JSON. (2) **Idle fleet detection** — flags when VMs running but shard production <25% expected for >30 min, new `health.low_shard_since` field. (3) **Orphaned Azure resource cleanup** — auto-deletes unattached NICs, disks, IPs, NSGs, new `azure_cleanup` field in status JSON. Also fixes shard sample cap from 20 to 200, and captures Azure VM size for per-VM cost calculation.

## Gotchas & Non-Obvious Patterns

> Cloud provider operational details (AWS/GCP/Azure quotas, CLI quirks, encoding bugs, orphaned resource cleanup) are in `docs/cloud-ops-reference.md`.

### Engine & Build

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping in `cardLibrary.jso`.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork (Surfinite/PrismatAlpha). Push to `PrismatAlpha`.
- **PrismatAlpha → PrismatAI rename (Feb 21)**: All AI player names in config.txt and C++ code renamed (`PrismatAlpha_AB` → `PrismatAI_AB`, etc.). The **git remote** is still called `PrismatAlpha` — only the in-game AI identity changed.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior. **Config gotcha**: When adding `_legacy` parameters with defaults to partial players, ALL users of the shared config entry silently get the new default behavior. Must create separate `_Legacy` config entries (e.g., `BreachGreedyKnapsack_Legacy`) and update legacy iterators to reference them.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to **stdout** (`std::cout` in `PrismataAssert.cpp:30`), does NOT abort. Use `std::ifstream` instead of `FileUtils::ReadFile` when stdout must stay clean (e.g., `--suggest` mode).
- **`isLegal()` doesn't fully validate USE_ABILITY side effects**: `isLegal(USE_ABILITY)` can return true but `doAction()` triggers PRISMATA_ASSERT (e.g., "not enough cards to destroy"). When trying speculative/fallback actions, only ASSIGN_BLOCKER and ASSIGN_BREACH are safe — they're simple state changes with no scripts or card destruction.
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` gives 4GB. Use `"Threads": 4` + multiple bat instances. Process dies silently at ~1400 games — config uses 1000 rounds/batch, `run_selfplay.bat` loops automatically.
- **x86 OOM with large vectors**: Don't pre-allocate large `std::vector<GameState>` upfront. Allocate per-batch. Symptom: silent exit with no `[SelfPlay] COMPLETE` message.
- **Console output routing**: `[SelfPlay]` and `[Progress]` use `fprintf(stderr, ...)`. Per-turn logging only when `SaveReplays: true`. New messages in Tournament.cpp should use stderr.
- **Tournament `tests/` directory required**: `HTMLTable::appendHTMLTableToFile()` crashes (NULL `fprintf`) if `tests/` doesn't exist in the working directory. Always `mkdir tests` when setting up a new tournament directory. The cloud launcher script already handles this (line 85 of `launch_tournament.sh`).
- **GUI Watch Training / Watch Eval modes**: Menu items in Prismata_GUI. Watch Training = self-play (1s think). Watch Eval = PrismatAI_AB_Legacy vs OriginalHardestAI (7s think). 4 threads each. Source: `source/gui/GUIState_WatchTraining.cpp/.h`.
- **GUI analysis overlay (Feb 21)**: 7-phase enhancement. (1) **Policy fix**: detects value-only models, shows "(value-only)" instead of bogus N: percentages. (2) **Gold prediction**: `(+N)` label from Drone count. (3) **Eval bars**: Shift+E toggles neural eval bar (vertical, right edge), Shift+W toggles WillScore bar. (4) **Parallel eval**: `std::async`/`std::future` background AI evaluation (max 2 concurrent for x86 4GB limit), non-blocking polling in `onFrame()`. (5) **Human advice**: F7 runs PrismatAI_AB + OriginalHardestAI on human's position, shows recommended buys. Auto-triggers when debug on. (6) **Eval history graph**: 300x200px at bottom-right, neural (blue) + WillScore (yellow). CSV export on game end. (7) **Card value overlay**: V: labels on buyable cards showing neural eval delta from simulated purchase (green=good, red=bad, grey=neutral). Plan: `docs/plans/2026-02-21-gui-enhancement-plan-v2.md`. Source: `GUIState_Play.cpp/.h`.
- **GUI key conflicts**: E = buy Engineer, W = buy Wall. Analysis toggles use Shift+E (eval bars), Shift+W (WillScore bar). Any new hotkeys must check for conflicts with buy keys (A-Z map to card names via `buyCardByName`).
- **GUI/engine decoupling**: Engine has zero SFML imports — compiles independently. GUI is ~4,100 LOC. SFML doesn't support WASM — web needs SDL2 abstraction or JS rewrite.
- **Prismata client architecture**: Adobe AIR/Flash app. C++ engine compiled to AVM2 bytecode via CrossBridge. Memory reading infeasible — use clipboard or network proxy for live state access. **Adobe AIR ignores PostMessage/SendMessage** for keystrokes — must use `SetForegroundWindow` + `SendInput` (brief focus steal ~100ms). This is a platform limitation of AIR's input handling.
- **Clipboard game state export (WORKING)**: F6 copies game state JSON to clipboard. F6 = full (with TurnStartInfo), Shift+F6 = compact. Requires SWF dev mode patch (see below). JSON wrapper key is `"CurrentInfo"` containing `mergedDeck`, `gameState`, `aiParameters`. Card names are **display names** (e.g., "Tarsier" not "Tesla Tower"). Table entries are per-instance (with `instId`, `constructionTime`, `role`, `health`). Source: `prismata_decompiled/scripts/client/Game.as:1226-1249`, `UIKeyboard.as:122-135`.
- **SWF developer mode patch (Feb 18)**: Single byte in `Prismata.swf` (CWS compressed, decompressed offset `0x1580196`): `0x27` (pushfalse) → `0x26` (pushtrue) enables `FlashBuildOptions.developerVersion`. Backup at `Prismata.swf.backup`. **Side effect**: disables load balancing — requires hosts entry `3.229.49.48 ec2-54-83-83-240.compute-1.amazonaws.com` (added via `tmp_restore_hosts.ps1` with UAC). Steam "Verify integrity" will revert the patch.
- **Sniffer duplicate process gotcha**: Multiple sniffer processes can bind to the same ports (SO_REUSEADDR) without error, but only the first one receives connections. Always kill existing sniffer processes before launching a new one: check with `tasklist | grep python` and verify port ownership with `Get-NetTCPConnection -LocalPort 11600`. The old bat-file-launched sniffer won't show in Claude's `run_in_background` tasks.
- **Autopilot only activates for bot games**: Safety check — autopilot skips PvP/spectated games (logs "Skipping — not a bot game"). Must use Play → vs Computer → Master Bot for testing. The check looks for `StartBotGame` in the BeginGame message type.
- **Prismata server Moved redirect**: After initial handshake on port 11600, server sends `["Moved", "3.229.49.48", 11610, 11611]` redirecting client to new ports. The sniffer proxy intercepts this, rewrites IP to `127.0.0.1`, and dynamically proxies the new ports. Without interception, the client reconnects directly to the real server IP, bypassing the proxy. AMF3 re-encoding handles the string length change.
- **Hosts file proxy/direct mode**: `tmp_proxy_hosts.ps1` (127.0.0.1, for sniffer) and `tmp_restore_hosts.ps1` (3.229.49.48, for normal play). Both use `[System.IO.File]::WriteAllText()` — NEVER use `Set-Content` or regex replacement (can wipe to 0 bytes). Both need UAC. **Current state: check hosts file** — if in proxy mode and sniffer isn't running, Prismata can't connect.
- **Move representation**: `Player::getMove(state, move)` returns a `Move` (sequence of `Action`s). BUY actions resolve to display names via `CardType(action.getID()).getUIName()`. Pattern in `TournamentGame.cpp:57-60`.
- **`--suggest` CLI mode** (DONE Feb 18): `Prismata_Testing.exe --suggest state.json [--player PrismatAI_AB] [--think-time 3000]` — reads F6 clipboard JSON, runs neural eval + AI search, outputs clean JSON to stdout. Init noise suppressed via `_dup2` fd redirect. Handles both F6 format (`CurrentInfo` wrapper) and bare state format.
- **`--suggest` clicks array (Feb 20)**: Output now includes `"clicks":[{_type,_id},...]` — wire-protocol-ready sequence for protocol injection. BUY: `_type="card clicked"`, `_id=mergedDeck index` (CardType ID - 2). USE_ABILITY/ASSIGN_BLOCKER/BREACH: `_type="inst clicked"`, `_id=client instId`. SNIPE/CHILL: two clicks (source then target). END_PHASE: `_type="space clicked"`, `_id=-1`. Automatic END_PHASE insertion mirrors `Move::toClientString()` logic.
- **`--eval` CLI mode** (DONE Feb 21): `Prismata_Testing_d.exe --eval replay.json` — steps through replay with ReplayStepper, runs `NeuralNet::evaluate()` at each turn, outputs JSON with per-turn eval curves (P1 perspective), eval swing, biggest mistake detection. ~2000 evals/sec.
- **`--analyze` CLI mode** (DONE Feb 21): `Prismata_Testing_d.exe --analyze replay.json --player PrismatAI_AB --think-time 500` — extends `--eval` with full AI search at each position. Compares human buys (from commandList clicks) vs AI buys (from `Player::getMove()`). Outputs per-turn agreement, sorted buy lists, AI full move. ~300ms/turn at 200ms think. Output includes both `humanBuys` (click-based) and `validatedBuys` (engine-validated via ReplayStepper, handles reverts and failed clicks correctly).
- **`displayRating` is a float, not int**: Replay JSON `ratingInfo.finalRatings[i].displayRating` is a float (e.g., 2173.802...). Calling `GetInt()` triggers RapidJSON assertion. Use `(int)GetDouble()`.
- **Card.cpp now preserves instId (Feb 20)**: `m_clientInstId` field added to Card class. Previously `instId` from F6 JSON was explicitly ignored (Card.cpp:114). Now stored and accessible via `getClientInstId()`. Returns -1 if not set (non-F6 states).
- **Clipboard F6 timing**: AIR may not write clipboard immediately after F6 keypress. The sniffer uses hash-and-wait polling (snapshot clipboard before F6, poll up to 1s for change) to reliably detect the new state. A single `time.sleep(0.1)` is insufficient.
- **mergedDeck buyCost format**: Digits = gold, `G` = green, `B` = blue, `C` = red (attack resource), `H` = energy. E.g., `"6BGGG"` = 6 gold + 1 blue + 3 green. Card click `_id` in Click messages maps to mergedDeck array index.
- **Replay commandList format**: Commands use `_type` (NOT `_action`) and `_id`. Types: `card clicked`/`card shift clicked` = BUY (\_id = mergedDeck index), `inst clicked`/`inst shift clicked` = CLICK ability (\_id = instance ID), `space clicked` = END\_PHASE, `revert clicked` = UNDO. `clicksPerTurn` array (2×N entries for N turns per player) slices commandList into per-turn segments. `playerInfo` has NO `playerNumber` key — use array index. Ratings in `ratingInfo.finalRatings[i].displayRating`.
- **Click counting ≠ buy counting (CRITICAL)**: `card clicked` in commandList does NOT guarantee a successful purchase. Clicks on sold-out cards (legendary supply exhausted, etc.) are recorded but silently rejected by the game engine. `revert clicked` only undoes intentional undos, not failed clicks. **Any code parsing buys from clicks MUST enforce supply limits**: legendary = 1 per player, rare ≈ 4. Without this, buy counts are inflated — e.g., Mega Drone (legendary) showed 3x purchased from click data when only 1 is possible.
- **Spectator commandInfo contains full game history**: When spectating a game already in progress, the BeginGame message includes `commandInfo.commandList` with ALL prior moves and `clicksPerTurn` with per-turn click counts. This allows complete game reconstruction from any spectator join point.
- **Replay `shift clicked` = buy max for Drones**: In `commandList`, `card shift clicked` on Drones in the opening = "buy max affordable" (usually 2). For non-Drone units, shift-click likely buys 1 (shift key held as UI habit). Each shift-click is a single entry regardless of quantity purchased.
- **Failed clicks from resource constraints**: The `commandList` gotcha about sold-out cards also applies to insufficient resources — clicks on unaffordable units are recorded but silently rejected by the server. When reconstructing games, track gold (persists), green (persists), blue (use-or-lose), red (use-or-lose), energy (use-or-lose) to determine which clicks actually succeeded.
- **Replay JSON structure**: Fetched replays use `deckInfo.mergedDeck` for card data (NOT `initInfo.mergedDeck`). `initInfo` has `initCards` and `initResources`. Player ratings in `ratingInfo.finalRatings[i].displayRating`.
- **Sniffer live state tracking (Feb 20)**: Auto-F6 on each StartTurn, clipboard capture with hash-and-wait, mid-turn Click buy tracking via mergedDeck lookup, EndTurn summary logging, GameOver cleanup. Output: `bin/live_game_state.json` + formatted console. Uses `_capture_seq` debounce to prevent overlapping F6 sends from rapid StartTurn messages. Thread-safe via Session._lock. Architecture: `Session` (thread-safe state), `MessageDispatcher` (registry), `@on_message` decorator, 12 handlers (7 core + 5 live state).
- **Sniffer spectator mode works**: Proxy captures replay codes from spectated PvP games (not just your own). The GameOver handler fires for all games observed through the proxy, including spectated matches.
- **Sniffer chat injection (Feb 20)**: C->S `["Msg", msgId, ["PrivateChat", playerId, text]]` for PM, `["Msg", msgId, ["Chat", "globalEnglish", text]]` for global chat. Requires C->S msgId offset tracking — injected messages increment `_c2s_offset`, real C->S Msgs get offset added. **Critical**: S->C Ping confirmation rewriting — must subtract `_c2s_offset` from `Ping[2]` (lastC2SMsgConfirmed) or client asserts "Confirmation cannot be received before sending a message" and disconnects. File trigger: write to `bin/chat_trigger.txt` (prefix `global:` for global chat). Default target: Surfinite (7709, self-PM); override with `CHAT_TARGET` env var.
- **Sniffer game action injection (Feb 20)**: Same `_inject_msg` mechanism as chat. C->S Click: `["Click", gameId, {_type, _id}, turn]`. C->S EndTurn: `["EndTurn", gameId, timeTaken, turn, finalClick]`. C->S EndSwoosh: `["EndSwoosh", gameId, turn]`. Must send EndSwoosh before any clicks. Turn lifecycle: EndSwoosh → abilities → buys → space → EndTurn (action), EndSwoosh → inst+endswipe per blocker → space → EndTurn (defense). Server validates moves — illegal clicks silently dropped.
- **`_sanitize_gamestate()` in sniffer, advisor, and autopilot**: Intentional duplication — the tools are independent (sniffer is a network proxy, advisor is a clipboard overlay). Both need to parse F6 clipboard JSON. Do not refactor into a shared module.
- **Churchill paper URLs**: Use `davechurchill.ca/publications/` (old `cs.mun.ca/~dchurchill/` is dead).
- **307th's Prismata Library blog** is at `prismatalibrary.blog` (NOT `blog.prismata.net/prismatalibrary/`). 27 articles, all live as of Feb 2026. Archive: `prismatalibrary.blog/archive/`.
- **WebFetch blocked on web.archive.org**: Use the CDX API via curl instead: `curl -s "https://web.archive.org/cdx/search/cdx?url=DOMAIN/*&output=json&fl=timestamp,original,statuscode&limit=50"`. Then fetch archived pages: `curl -sL "https://web.archive.org/web/{timestamp}/{url}"`. Process HTML to text with Python.

### Self-Play & Data

- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **Self-play crash safety**: Each run writes to `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/`. Restart anytime — only in-flight games lost. Empty run dirs (config file but no shards) mean the exe was killed before completing any games — harmless, can be deleted.
- **Run self-play from Explorer**: Use `bin/run_selfplay.bat`. Has startup exe check and 5s error delay to prevent spin-looping during rebuilds. **The bat loop only auto-restarts if the window stays open** — killing the process externally (e.g., `taskkill`) also kills the bat loop. Must manually re-launch `run_selfplay.bat` after external kills.
- **Selfplay shard CRC**: CRC check fails on shards from crashed/in-progress runs (no footer). Use `validate_crc=False` for live data.
- **In-progress shard detection**: Sentinel record_count (0xFFFFFFFFFFFFFFFF) + non-zero payload remainder = shard was being written when process died. No valid CRC footer exists — the trailing bytes are an incomplete record. ~99.8% of local shards are sentinel (only properly finalized on clean exit).
- **Selfplay positions per game**: ~37 records/game (both players' turns), NOT ~440. A 10K-game run yields ~370K records.
- **Selfplay shard binary format**: Header 64 bytes (magic, version, feature_dim, record_size, record_count, endian_check, padding) + 4-byte CRC32 footer. Record size = 7152 bytes. Games = `(file_size - 68) / 7152 / ~37`. See `training/load_selfplay.py` for `HEADER_SIZE = 64`.
- **Selfplay game counting**: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-68)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>68); print(f'{total} records, ~{total//37} games')"`.
- **S3 download dir structure**: `aws s3 sync` creates timestamp dirs without `run_` prefix containing nested `run_*` subdirs. Must scan recursively.
- **S3 data audit COMPLETE (Feb 20)**: 7,804 shards, 26.7M records, ~722K games, 178GB — all clean. 0 CRC failures, 0 NaN, 0 Inf, 0 duplicates, 0 error shards. P0 win rate 43.9%, P1 57.3% (P2 advantage, see below). Results: `s3://prismata-selfplay-data/audit-results/audit_20260220_005826.json`. Tool: `tools/audit_selfplay_s3.py`.
- **Self-play uses playout eval**: `SelfPlay_CI` runs `OriginalHardestAI_1s` vs itself (playout eval, 1s think). The neural net is NOT used for game generation — only for position labeling. Data quality depends on playout AI strength, not model WR. ~4 games/min per 4-thread process.
- **P2 (second player) wins 57.3% of self-play games**: P0 43.9% / P1 57.3% across 26.7M records. Human play at 1800+ is 48.6/50.8 (Lunarch stats). P2 starts with an extra Drone, enabling openings P1 can't execute. The wider gap vs human play is likely because 1s think time is insufficient for P1 to find precise equalizing openings. Not a data quality issue — the model should learn this real game asymmetry.
- **PID-based random seeding**: All 3 exe entry points use `srand(time ^ PID)` — prevents identical sequences when launching multiple instances in the same second.
- **Game_id namespacing**: `load_selfplay.py` offsets game_ids by 1M per source dir to prevent collisions across runs and train/val split leakage. `audit_selfplay_s3.py` uses `(shard_index, game_id)` composite keys. **Any new code touching game_ids must scope them per-shard** — each selfplay process starts its counter at 0.
- **Value-only model export**: `export_weights.py` exports zero-initialized policy tensors for value-only models (4 extra). C++ loader requires all 26 tensors — a 22-tensor export will fail.
- **SelfPlayDataExport requires loaded neural net**: If `neural_weights.bin` fails to load, exe writes ZERO shards silently. Only stderr warning. Always verify 26 tensors.

### Training

- **Quick training/loader tests**: Full shard index scan (~3,000 shards) takes ~3 min. For quick tests, use a single small run dir: `--selfplay-dir bin/training/data/selfplay/2026-02-15_11-31-33/` (4 shards, 134 records, completes instantly).
- **Training CRC**: `train.py` uses `validate_crc=False` — required because in-progress/crashed shards lack CRC footers.
- **Training overfitting**: V2 experiments (Feb 17) confirmed: smaller model (256h) trains longer and achieves better calibration. LR controls overfitting speed but not ceiling. Loss function (MSE vs BCE) is a wash. Subsampling hurts. See run JSONs in `training/runs/20260217_*.json`.
- **Training RAM limit**: Full dataset (8.2M+ records) = ~50GB+. With 32GB RAM: max ~1M records with `--max-records 1000000`. For full dataset, use `--streaming` flag (memory-mapped, never loads full dataset into RAM). Streaming mode supports `--num-workers 2-4` (lazy init fix, Feb 17). Non-streaming mode: `num_workers` works normally. Expert data mixing not supported in streaming mode.
- **Training RAM: max 2 concurrent jobs**: Running 3 `train.py` jobs simultaneously OOMs during `np.concatenate` in `load_all_shards` (32GB RAM). Safe limit: 2 concurrent runs with `--max-records 1000000`.
- **best_model.pt gets overwritten**: Each `train.py` run writes to `training/models/best_model.pt`. Copy to a unique filename immediately after a run finishes if you need to preserve it.
- **Training lock file**: `train.py` creates `training.lock` in model directory (PID + timestamp). Prevents zombie processes writing to same output dir. Auto-cleaned on exit via `atexit`. Stale locks from dead processes are auto-removed. To force-clear: delete `<model_dir>/training.lock`.
- **C++ NeuralNet hidden_dim AND num_layers are dynamic**: Both `_hiddenDim` and `_numLayers` are read from the weight file header (NeuralNet.cpp:129), not hardcoded. Can deploy 256h/2L, 256h/3L, 512h/2L etc. by swapping weight files — no C++ rebuild needed.
- **Tournament output needs `2>&1`**: Tournament progress/results use `fprintf(stderr, ...)`. Redirect with `> log.txt 2>&1` to capture. Without this, only per-turn buy actions (stdout) are logged.
- **Parallel tournament eval**: Use separate directories (`bin_eval_X/`) each with own exe, config.txt, cardLibrary.jso, and neural_weights.bin to run multiple tournaments simultaneously.
- **D: drive backup**: `D:\PrismataAI_backup\` has selfplay data, models, weights, config, run logs. Created Feb 15.
- **Experiment logs**: `training/runs/{timestamp}.json` — full per-epoch metrics, hyperparameters, git hash.
- **Streaming DataLoader num_workers>0** (FIXED Feb 17): Was crashing with `TypeError: cannot pickle 'module' object` — root cause is transient Windows handle exhaustion under memory pressure, not a real pickle incompatibility. Lazy init pattern (`self._torch = None` in `__init__`, import in `_ensure_init()`) is still good practice. `persistent_workers=True` ensures init happens only once per worker. `num_workers=4` confirmed working when RAM is adequate.
- **train.py positional args**: TWO positional args — `data_dir` (default `training/data`) then `model_dir` (default `training/models`). Must pass both when using custom model output dirs: `python training/train.py training/data training/models/my_run --selfplay-dir ...`.
- **IPEX is EOL (removed Feb 17)**: `intel_extension_for_pytorch` end-of-life March 2026. Replaced with native `torch.xpu` (PyTorch 2.10.0+xpu). Do NOT install IPEX. `get_device()` uses `hasattr(torch, 'xpu')` — works on any PyTorch version.
- **XPU training: use `--device xpu --num-workers 4`**: Auto-detected if XPU available. With `num_workers=4`: 3.2x per-epoch speedup vs CPU (13s vs 42s). BF16 (`--amp`) adds overhead for small models — skip it. `torch.compile` (`--compile`) needs MSVC vcvars64.bat — skip unless model gets larger.
- **XPU + streaming + RAM pressure**: Two concurrent training jobs (~18GB) plus XPU streaming causes disk thrashing (mmap page faults) and transient "cannot pickle 'module' object" errors from Windows handle exhaustion. Keep to 1-2 concurrent training jobs when using streaming mode. Use `--max-records 100000` for quick smoke tests.
- **Streaming num_workers=2 on 32GB RAM**: With 12M+ records, `--num-workers 4` causes 94% RAM usage, 410K page faults/sec, disk queue 27 — system becomes unusable (watcher hangs, boot protection triggers). **Use `--num-workers 2`** for streaming on 32GB RAM. Default is now 2 (changed from 8, Feb 19). Use `--num-workers 4` explicitly only on 32GB+ local machines.
- **Cloud GPU RAM constraint (16GB)**: Both GCP g2-standard-4 and AWS g4dn.xlarge have only 16GB system RAM. Non-streaming mode: `--max-records 500000` safe, 800K OOMs during `np.concatenate`, 1.5M definitely OOMs. **Must use `--streaming` for full dataset on cloud GPUs.** Default `--num-workers 2` is safe for 16GB; use `--num-workers 4` only on 32GB+ local. **WARNING: g2-standard-4 (16GB) OOM-kills streaming training with 27M+ records even with `--num-workers 2`** — mmap page cache grows over ~30K steps until OOM killer fires. Use **g2-standard-8 (32GB)** for full-dataset streaming. `gcp/launch_training.sh` now creates 16GB swap as belt-and-suspenders.

### Windows & Python Environment

- **Windows file size caching**: `ls`/`Get-ChildItem` may show 0 bytes for files with open write handles. Use `python -c "import os; print(os.path.getsize(path))"`.
- **`nohup &` broken in Git Bash on Windows**: Background processes get killed when the bash shell exits. Use the Bash tool's `run_in_background` parameter instead, or launch from a persistent cmd/PowerShell window.
- **Python stdout buffering**: Long-running Python processes show no output in Claude Code Bash tool. Use `PYTHONUNBUFFERED=1` prefix.
- **Python cp1252 on Windows**: Python defaults to cp1252 for stdout. Use `PYTHONIOENCODING=utf-8` or stick to ASCII.
- **`python3` not available on Windows**: Git Bash only has `python` on PATH. All shell scripts must use `python`, not `python3`.
- **`gcloud` only available in Git Bash**: Not on Python/cmd PATH. `subprocess.run(['gcloud', ...])` fails. Either use `bash -c "export PATH=...; gcloud ..."` via the Bash tool, or use full path `C:/google-cloud-sdk/bin/gcloud.cmd` with `shell=True`.
- **PowerShell JSON files have UTF-8 BOM**: `watcher_status.json` and `watcher_config.json` written with BOM. Python: use `encoding='utf-8-sig'`.
- **Git Bash mangles `$_` in PowerShell inline commands**: `$_` becomes `\extglob`, breaking `Where-Object` filters and `ForEach-Object` blocks. Workaround: write a `.ps1` script file and invoke with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File script.ps1`.
- **Bash tool breaks after crash**: After Claude Code crash, shell builtins (`echo`, `pwd`, `ls`) return exit code 1 with no output. External programs (`python`, `aws`) still work. Use `python -c "import subprocess; subprocess.run([...])"` as workaround until shell recovers.
- **Env vars don't reliably pass to bash scripts in Claude Code**: `DRY_RUN=true bash script.sh` silently fails to set the var. Workaround: use `python -c "import subprocess, os; env = os.environ.copy(); env['VAR'] = 'val'; subprocess.run(['bash', 'script.sh'], env=env)"`.
- **Hosts file editing danger**: PowerShell `Set-Content` on `C:\Windows\System32\drivers\etc\hosts` can wipe the file if regex replacement removes all content. Always read-verify after writing. Use `[System.IO.File]::WriteAllText()` with a complete replacement string, never incremental regex. Requires UAC elevation. Flush DNS after: `ipconfig /flushdns`.

### Historical / Concluded

- **Blend tournaments concluded**: Neural component hurts. Don't revisit until model >60% val accuracy. See `docs/blend-tournament-results.md`.
- **Batch validation**: 2,127 Master Bot replays tested (Feb 20). Pass rate: 55.7% (1,185/2,127) after RC#5–RC#9 fixes (action legality metric — stricter than previous state-comparison metric). Remaining 849 failures: USE_ABILITY (276), SNIPE (173), END_PHASE (130), BUY (116), BLOCKER (58), OTHER (96). These are genuine TS↔C++ semantic differences, diminishing returns to fix further. Not blocking self-play.
- **Replay balance validation**: `validate_balance_all.js` checks costs against `cardLibrary.jso`. Output: `balance_passed_codes.json` (32,973 codes). Incremental via `balance_results.json`.

### Dashboard

- **BOM stripping required**: `watcher_status.json` and `watcher_config.json` have UTF-8 BOM from PowerShell. Server.js strips with `raw.replace(/^\uFEFF/, '')`.
- **fs.watchFile, not fs.watch**: `fs.watch` is unreliable on Windows for network/mapped drives. `fs.watchFile` polls at 5s interval — reliable but uses CPU. 200ms debounce for half-written files. Watchers only activate when SSE clients are connected (`startWatchers`/`stopWatchers`).
- **Git Bash for bash scripts**: Action system spawns bash scripts with `shell: 'C:/Program Files/Git/bin/bash.exe'`. Python actions use `PYTHONUNBUFFERED=1`.
- **LAN access**: Server binds to `0.0.0.0:3000`. Logs local LAN IP on startup. Firewall may need port 3000 opened for other devices.
- **Config-driven actions**: Action definitions live in `dashboard/actions.json` (tier, label, description, command array, optional conflicts array). Edit this file to add/modify actions — no server.js changes needed.
- **Conflict prevention**: `activeOps` Map tracks running child processes. Returns 409 if same action running OR if bidirectional `conflicts` array in `actions.json` blocks it.
- **Game rate estimation**: `gamesPerShard = total_games / total_shards` ratio computed from cumulative data. Display: `shards_last_hour × gamesPerShard` → auto-selects GAMES/MIN or GAMES/HR label.
- **watcher_log.txt EBUSY crash (FIXED Feb 18)**: `logWatcher` in server.js previously used bare `fs.openSync` — crashed the server when the watcher held an exclusive lock on the log file. Fixed with try-catch; silently skips the poll cycle and retries next time.
- **Local process monitoring**: `get_local_stats.ps1` detects selfplay, training (with model label, device, worker count from cmdline), and Claude Code processes. Provides CPU%, GPU%, RAM, disk I/O via CIM/WMI (NO Get-Counter — those block ~1s each). Served at `/api/local-stats` with 30s cache. Dashboard shows training/Claude job rows and utilization bars.
- **All costs displayed in GBP**: `USD_TO_GBP = 0.79` constant in app.js. AWS costs converted from USD, Azure already in GBP. Cloud cost cache TTL: 5 minutes.
- **Dashboard server restart required for code changes**: `server.js` edits don't take effect until the Node.js process is restarted. Find PID: `Get-NetTCPConnection -LocalPort 3000 -State Listen | Select OwningProcess`, then `Stop-Process -Id <PID>; node dashboard/server.js`.

### Cloud Operations

- **Cloud config isolation**: Each provider (AWS/GCP/Azure) downloads base config from S3 and patches it locally on the VM. No shared local config files are modified — providers can run simultaneously without conflicts.
- **AWS launch_selfplay.sh temp file race**: Script writes `.userdata_tmp.ps1` then reads it — parallel launches cause file-not-found errors. Even sequential launches can collide with TheWatcher (which also uses this file). Launch serially and accept occasional failures; TheWatcher will fill gaps on the next cycle. Proper fix: use per-PID unique temp filenames.
- **launch_selfplay.sh 5th arg is instance count**: Pass a number (e.g., `1`) or omit. Passing `N` (literal) breaks the `seq` command inside the script. Applies to both `gcp/launch_selfplay.sh` and `azure/launch_selfplay.sh`.
- **launch_tournament.sh fleet verification**: Always verify actual fleet size with `aws ec2 describe-instances` after launch — sequential calls may launch more instances than expected if each call spawns multiple.
- **watcher_log.txt file lock**: TheWatcher (Task Scheduler instance) holds an exclusive lock on `aws/watcher_log.txt`. Standard file reads (`cat`, `Get-Content`, Python `open()`, `Copy-Item`) all fail. PowerShell `Add-Content` also fails with "Stream was not readable" when another process holds the file. Use `robocopy aws/ <dest>/ watcher_log.txt` to copy the locked file, then read the copy.
- **Azure Public IP quota (increased to 40)**: Subscription-level limit, not per-region. Orphaned NICs and public IPs persist after VM deallocation/deletion, consuming quota even with no running VMs. Clean up: `az network nic delete` first, then `az network public-ip delete`. Check with `az network public-ip list -o table`.
- **GCP GPU quotas**: Per-GPU-type regional quotas (e.g., `NVIDIA_L4_GPUS=1`, `NVIDIA_T4_GPUS=1`) AND a project-level `GPUS_ALL_REGIONS=1` global cap. The global cap limits total GPUs across all regions/types to 1. Check project-level: `gcloud compute project-info describe --format=json` filtering for `GPU`. Check regional: `gcloud compute regions describe us-central1 --format=json` filtering for `NVIDIA`.
- **GCP has THREE separate CPU quotas**: (1) N2_CPUS (per-family, 200), (2) regional CPUS (per-region, 200), (3) **CPUS_ALL_REGIONS (global/project-level, 48)**. The global quota is the real bottleneck — search for `CPUS_ALL_REGIONS` in the GCP Console quota page (NOT "CPUS" which shows per-region). Request ID `91228b40031744c590` got 48 approved (200 was denied — new accounts get incremental increases).
- **GCP exe crash (was misdiagnosed as Defender)**: GCP instances died after ~8 games with `0xc0000409` (STATUS_STACK_BUFFER_OVERRUN). Initially blamed on Defender (null exit code = external termination), but root cause was **stale exe in S3** — same exe worked on EC2/local but GCP's VM memory layout triggered a latent buffer overrun. Fix: rebuild exe fresh and redeploy to S3. Image switched from `windows-2022-core` to `windows-2022`. Defender exclusions (`Add-MpPreference -ExclusionPath/-ExclusionProcess`) kept. **Always redeploy exe to S3 after rebuilding** (`aws/deploy_for_eval.sh` or manual `aws s3 cp`).
- **GCP SSD_TOTAL_GB quota = 250**: Each 50GB pd-ssd boot disk counts against this. Max 5 instances with SSD. Switched to `pd-standard` (2048GB quota) since selfplay is CPU-bound. Warning about "disk size under 200GB" is cosmetic — ignore it.
- **Cloud training disk sizing**: Selfplay data is ~178GB (Feb 20, ~722K games, 7,804 shards). Cloud training instances need 350GB boot disk and `--streaming` flag. Without streaming, loading 13M records requires ~50GB RAM. The `n1-standard-4` (15GB) will OOM; use `n1-standard-8` (30GB) minimum with streaming. Boot disk type must be `pd-standard` (not `pd-ssd`) to avoid `SSD_TOTAL_GB` quota conflict with selfplay instances.
- **EBS IOPS scaling diminishing returns**: For streaming mmap training on gp3 EBS, 3K→6K IOPS gives 2x speedup (314s→157s/1K steps), but 6K→12K→16K gives only ~5% more. Bottleneck shifts from IOPS throughput to EBS read latency (~1.1ms/IO). GPU stays at 2% (fully I/O-bound). `aws ec2 modify-volume` applies live (no restart) but only one modification at a time (blocks while OPTIMIZING).
- **SSH to EC2 training instances**: `ssh -i ~/.ssh/prismata-selfplay.pem ec2-user@<IP>`. Key name is `prismata-selfplay`. Training logs at `/home/ec2-user/training/training_output.log`.
- **S3 crash dumps waste storage**: `s3://prismata-selfplay-data/results/` contains .dmp crash dump files (~93 GB as of Feb 19, 22 files). These are from early GCP/Azure instance crashes. Delete periodically: `aws s3 rm s3://prismata-selfplay-data/results/ --recursive --exclude "*" --include "*.dmp" --region eu-north-1`. Actual selfplay data: 7,756 .bin shards (182 GB) + 3,230 .txt configs + 658 .log files.
- **`aws s3 ls --recursive` fails on large prefixes**: The results/ prefix has 8,000+ objects and times out. Use `aws s3api list-objects-v2 --query "Contents | sort_by(@, &LastModified) | [-5:]"` instead.
- **S3 provider identification**: EC2 instances don't upload boot logs. GCP boot logs say "GCP Worker Starting". Azure doesn't upload boot logs either. To distinguish EC2 vs Azure in S3 results, check the `patched_config.txt` (Azure uses 250-round batches, EC2 uses 1000-round runs) or check instance naming patterns in logs.
- **watcher_status.json shard tracking unreliable**: `shard_activity.last_new_shard` can show stale dates (e.g., Feb 16) even with 56+ active EC2 instances. `shards_last_hour` also underreports. Don't rely on these fields for fleet health — check actual S3 data growth or instance counts instead.
- **watcher `spot_only: true` doesn't terminate existing on-demand**: Setting `spot_only` in watcher_config only prevents NEW on-demand launches. Existing on-demand instances keep running and consuming quota. Must manually terminate them: `aws ec2 terminate-instances --instance-ids $(aws ec2 describe-instances --region eu-north-1 --filters 'Name=tag:Name,Values=PrismataSelfplay*' 'Name=instance-lifecycle,Values=normal' --query 'Reservations[].Instances[].InstanceId' --output text)`.
- **Cloud free credits — CRITICAL**: AWS $200 is **NOT auto-applied** — it's 6x $20 "Explore AWS" tutorial credits restricted to specific services. They do **NOT** cover EC2 Spot, Data Transfer, or VPC. **Feb bill: $805.34 USD** ($671 pre-tax + $134 tax) for ~4 days of 37-instance spot fleet. Check credits page: https://console.aws.amazon.com/billing/home#/credits. Azure $200/30days (HIGH RISK — hard 30-day deadline, ~£65 over-credit charged). GCP $300/90days (from Feb 16). **All cloud spend is real money — there is no safety net.**
- **Cloud compute cost comparison (Windows, 8 vCPU, Feb 2026)**: AWS c5.2xlarge: $0.384/hr on-demand, **$0.14/hr spot** (eu-north-1 Stockholm rates from watcher.ps1 rate table). Cost per 1K games: $0.88 OD, **$0.32 spot** (64% savings). Azure D8als_v7: $0.726/hr on-demand, $0.134/hr spot (82% off, **but spot unavailable** for this subscription). **Spot-only mode recommended** — set `spot_only: true` in watcher_config.json.
- **AWS GPU training costs**: g4dn.xlarge (T4, 4 vCPU, 16GB RAM): ~$0.20/hr spot in eu-north-1. Parallel sweeps: 10 configs x 1 hour = ~$2. Separate G/VT vCPU quota from Standard (selfplay) — both can run simultaneously.
- **S3 deploy bucket**: `s3://prismata-selfplay-data/deploy/training/` contains 5 required files: `train.py`, `load_selfplay.py`, `export_weights.py`, `schema.json`, `unit_index.json`. Missing `unit_index.json` causes `FileNotFoundError`. Redeploy after local changes.
- **`aws s3 sync` non-zero exits**: S3 sync returns non-zero on partial transfer warnings even when data transferred OK. Scripts with `set -eo pipefail` die silently. Wrap critical syncs with `|| { echo "WARNING..."; }` to continue.
- **Cloud launch scripts have trap EXIT (Feb 20 fix)**: Both `aws/launch_training.sh` and `gcp/launch_training.sh` use `trap cleanup_and_shutdown EXIT` to ensure instances self-terminate on ANY exit — `set -eo pipefail` crashes, signals (SIGTERM from spot termination), or errors. Does best-effort log upload before shutdown. Previously, crashed instances ran indefinitely billing ~$0.40/hr.
- **GCP quota gate**: New GCP accounts must wait 48 hours from creation before quota increase requests are accepted.

### External Tools

- **claude-mem 10.0.7**: Bug #1104 filed. Chroma runs manually on port 8000. **Update when >10.0.7 available.**
- **Future feature plans in claude-mem**: GUI spectator mode (#1385), web-based remote advisor (#1524). Use MCP search to retrieve.
- **Live commentator deps**: `anthropic` (Claude API, installed). Phase 2 deps (not yet installed): `edge-tts` (neural TTS, async), `sounddevice` + `pydub` (audio playback/decode), `obsws-python` (OBS WebSocket). External: VB-Cable (virtual audio for OBS routing). See `docs/plans/2026-02-20-live-commentator-plan.md`.
- **Twitch VODs have no captions**: No subtitle tracks stored or served via API. Use `yt-dlp -x --audio-format mp3` to extract audio, then `openai-whisper` (local) or `faster-whisper` for speech-to-text transcription.

## Claude Code Tooling

**Slash commands**: `/status` (fleet dashboard + game count + running processes), `/selfplay-count` (quick local shard count), `/revise` (update CLAUDE.md), `/preflight` (pre-training verification: S3 deploy diff, code review, fleet/quota/git checks), `/document-context` (generate reviewer context doc for most recent plan in `docs/plans/`), `/review-intake` (ingest external reviews + meta-review with tiered plan updates — must-do/should-do auto-applied, consider as pick list), `/start-work` (create clean branch from master for new work), `/audit` (repo health check — branches, uncommitted changes, stale files).

**Hooks** (in `.claude/settings.local.json`):
- PreToolUse: Blocks Read/Edit/Write on `.aws_credentials`, `credentials.json`, `.env` files
- PreToolUse: Blocks Bash commands that would unregister/stop TheWatcher Task Scheduler job
- Stop: Reminds to run `/revise` on session close

**Subagents**: `fleet-health` (`~/.claude/agents/fleet-health.md`) — audits AWS/GCP/Azure for running instances and orphaned resources. **NOTE: agent file currently missing — needs recreation.**

**MCP**: context7 configured in `.mcp.json` (project-level) — live docs for PyTorch, Express, Chart.js, cloud CLIs.

**Excalidraw diagrams**: MCP tools available (`read_me`, `create_view`, `export_to_excalidraw`, `read_checkpoint`, `save_checkpoint`). Call `read_me` first for format reference. **VS Code extension can't render Excalidraw** — `create_view` only renders inline on claude.ai web; in VS Code shows raw JSON. Always use `export_to_excalidraw` for a shareable excalidraw.com URL. **`label` property doesn't export** — the `label` shorthand on shapes only works in the MCP inline renderer. For exported diagrams, use native bound text elements: `boundElements` array on rectangles + separate text elements with `containerId`, `originalText`, `textAlign: "center"`, `verticalAlign: "middle"`. Architecture diagram checkpoint: `bae5ace4d2484e41b5` (4-layer diagram with DC/S attribution stamps).

**C++ style**: `.clang-format` at project root (Allman braces, 4-space indent, 120 col limit). Matches existing codebase conventions.

## Session Close-Out

When the user says "wrapping up", "closing context", or "save everything":
1. Check for undocumented results (experiments, tournaments, benchmarks) — if any exist only in conversation, write them to appropriate docs
2. Update any stale plan/results docs with actual outcomes (e.g., mark plans COMPLETE, add results tables)
3. Map any unnamed artifacts to human-readable names (e.g., run timestamps → experiment names)
4. Run `/revise-claude-md` for CLAUDE.md status and gotcha updates
5. List anything still only in conversation context so the user knows what would be lost
6. Save important conversation-only findings to claude-mem (audit results, stale deploy warnings, unfinished work items). Use judgement — no clutter, only items a future session would genuinely benefit from knowing.
7. Commit all changes (unless a good reason exists not to). Group into logical commits if work spans multiple areas.

## User Preferences

- **Cost-conscious** — AWS bill shock ($805 for 4 days of spot fleet). No cloud safety net. Prefer local compute, minimize cloud spend.
- Efficiency over speed — minimize API credits, maximize local PC computation
- Comfortable with long-running unattended tasks (hours). Tell them when something can run overnight.
- Git comfort level: self-described "noob" — explain git ops clearly, always confirm before push/force
- The user is "Surfinite" everywhere — GitHub, Prismata, Discord, etc.

## Git Workflow

**Branch naming:** `{type}/{short-description}` where type is `fix/`, `feature/`, `docs/`, or `training/`.

**When to branch:** Create a new branch from `master` when starting logically independent work. Use `/start-work fix/description` to automate this. Small related fixes (typos, one-liners) can go on the current branch.

**Branch lifecycle:**
1. `/start-work fix/description` (or manually: `git checkout PrismatAlpha/master -b fix/description`)
2. Work, commit with `/commit` as you go
3. When done: `/commit-push-pr` to push + open PR, or merge locally: `git checkout master && git merge fix/description && git push PrismatAlpha master`
4. Delete branch after merge: `git branch -d fix/description`

**Push target:** Always `PrismatAlpha` (never `origin`).
**Commit style:** Imperative mood, focus on "why". One logical change per commit.
**Before starting new work:** Check if current branch has unrelated uncommitted changes. If so, suggest `/start-work` for a clean branch.

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

**Targeting abilities are two-step**: USE_ABILITY on source card (sets `m_targetAbilityCardClicked` flag in GameState), then SNIPE/CHILL on target (checked by `isTargetAbilityCardClicked()` in `isLegal`). `"disrupt"` in cardLibrary maps to `ActionTypes::CHILL` (CardTypeInfo.cpp:127). 12 units have `targetAction`. After CHILL execution, source card's `canUseAbility()` stays true (no abilityScript), but `hasTarget()` becomes true — must check both to avoid reuse.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval (branching factor 5 from PPPortfolio). **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): resource values ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50. Cost-based material counting — not strategic value.

**Neural net**: ResNet, state_dim=1785, policy+value heads. C++ inference via `NeuralNet::Instance()`. ~2,000 evals/sec/core. Hidden dim AND num_layers are dynamic (read from weight file header) — current best: 256h/3L (R12_smooth90). Can deploy 256h/2L, 256h/3L, or 512h by swapping weight files, no C++ rebuild needed.

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

AMD Ryzen 7 5700X3D (8c/16t), ASUS TUF Gaming X570-PLUS (Wi-Fi), 4x8GB Crucial Ballistix DDR4-3200 CL16 (32GB, all slots filled, max 128GB), Intel Arc B580 (12GB VRAM). DDR4-3600 is the max practical speed (1:1 FCLK at 1800MHz on Zen 3). Self-play generation: ~4 games/min per 4-thread instance (~16 games/min with 4 instances). Training: ~30 min/epoch on CPU (full 8.7M dataset, streaming). **XPU training enabled:** ~7 min/epoch with `--device xpu --num-workers 4` (4.5x total speedup). PyTorch 2.10.0+xpu, native `torch.xpu` backend.

## Known Issues (Current)

- **Neural policy head weak** — 13.3% accuracy. Computed but unused for move ordering.
- **PUCT move ordering implemented** — `"UsePUCT": true` in Player_UCT config. Uses policy head as priors in UCT search (AlphaZero-style). Disabled by default — don't enable until policy accuracy improves past ~30%. Files: `UCTSearch.cpp` (computeRootPriors, PUCT formula in UCTNodeSelect), `UCTNode.h` (_policyPrior), `UCTSearchParameters.hpp` (_usePUCT), `AIParameters.cpp` (UsePUCT parsing).
- **Blocking feature mismatch** — C++ uses `CardStatus::Assigned`, Python uses `blocking AND abilityUsed`. Low priority.
- **Heuristic eval in progress (Feb 21)** — 3 tournaments on 12 AWS spot instances: Neural+improved vs Original (~2,016 games), Playout+improved vs Original (~768), Neural improved vs legacy (~768). Baseline: 45.3% WR. Results: `eval-results/heuristic_eval_*/`.
- **TS tooling bugs (FIXED, validation improved)** — RC#5 (snipe target), RC#6 (frontline→breach), RC#7 (two-step targeting: USE_ABILITY before SNIPE/CHILL), RC#8 (action ordering: abilities→snipe→frontline→buy), RC#9 (SNIPE overcounting: CancelUseAbility routing fix in TS parser + converter cap), selfsac/lifespan tolerance all fixed. Pass rate 27.2%→55.7% (1,185/2,127, action legality metric). Remaining failures are genuine TS↔C++ semantic differences. Not blocking self-play.

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
| `source/testing/ReplayStepper.h/cpp` | Replay click→action stepper with instId tracking and error recovery (96.6% extraction) |
| `source/testing/SelfPlayDataSink.h/cpp` | Binary shard writer for self-play features |
| `source/testing/IDataSink.h` | Virtual interface for game event capture |
| `source/gui/GUIState_Play.cpp` | Game play GUI, debug panel, replay viewer, eval bars, parallel AI eval, card value overlay |
| `source/gui/GUIState_WatchTraining.cpp/.h` | Watch Training/Eval GUI — live display + training data generation |
| `training/train.py` | PyTorch training (PrismataNet, supports `--selfplay-dir`) |
| `training/load_selfplay.py` | Binary shard loader → numpy arrays |
| `training/vectorize.py` | Expert JSONL → PyTorch tensors |
| `training/export_weights.py` | PyTorch → C++ binary weight format |
| `training/schema.json` | Feature schema contract (state_dim=1785) |
| `training/FEATURES.md` | Human-readable feature specification |
| `training/data/unit_index.json` | 161 canonical unit names |
| `training/requirements.txt` | Python deps (torch, numpy, tqdm) with XPU install instructions |
| `training/opening_book.py` | Opening book extraction from expert replays |
| `tools/verify_selfplay.py` | Validates self-play binary output |
| `tools/download_replays.py` | Download expert replay JSONs from S3 (gzipped, threaded, rating filter) |
| `training/retest_validation.py` | Re-test failed replays against fixed C++ engine with error categorization |
| `training/analyze_mismatches.py` | Aggregate mismatch analysis across failed replay validations |
| `training/convert_replay_for_cpp.py` | Convert TS replay states to C++ validation format (RC#9 cap for snipe_targets) |
| `training/fast_batch_validate.py` | Fast batch validation: in-process conversion + parallel C++ validation (4 workers) |
| `tools/download_wiki.py` | Downloads full Prismata wiki from Fandom API |
| `bin/run_selfplay.bat` | Crash-safe self-play launcher (run from Explorer) |
| `.github/workflows/selfplay.yml` | GitHub Actions self-play workflow |
| `aws/launch_selfplay.sh` | EC2 self-play launcher (Windows instances, auto-terminate) |
| `aws/launch_training.sh` | EC2 GPU training launcher (g6.2xlarge, Linux, env var config, trap EXIT auto-terminate) |
| `aws/launch_tournament.sh` | EC2 tournament fleet launcher (supports NUM_INSTANCES, WEIGHTS_KEY, MODEL_LABEL env vars) |
| `aws/launch_heuristic_eval.sh` | Multi-tournament heuristic eval launcher (3 tournaments, spot, auto-terminate) |
| `aws/launch_audit.sh` | EC2 spot launcher for S3 data integrity audit (c5.xlarge, <$0.10, auto-terminate) |
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
| `gcp/launch_training.sh` | GCP GPU training launcher (L4/T4, Linux DL VM, env var config, trap EXIT auto-delete) |
| `gcp/.aws_credentials` | AWS credentials for GCP→S3 uploads (gitignored, not committed) |
| `azure/launch_selfplay.sh` | Azure VM self-play launcher (Windows VMs, auto-terminate) |
| `azure/.aws_credentials` | AWS credentials for Azure→S3 uploads (gitignored, not committed) |
| `dashboard/server.js` | Command Center backend (Express + SSE + action system) |
| `dashboard/actions.json` | Action button definitions (tier, command, conflicts) — edit to add new actions |
| `dashboard/public/` | Command Center frontend (HTML + CSS + vanilla JS + Chart.js) |
| `run_dashboard.bat` | One-click dashboard launcher (auto-installs deps, opens browser) |
| `.clang-format` | C++ code style (Allman, 4-space, 120 col) |
| `.mcp.json` | Project-level MCP server config (context7) |
| `~/.claude/agents/fleet-health.md` | Cloud fleet health audit subagent |
| `c:\libraries\prismata-replay-parser\` | TS replay parser + data extraction scripts |
| `c:\libraries\DiscordChatExporter\` | Discord message export tool (CLI at `cli/`) |
| `c:\libraries\prismata-replay-parser\validate_balance_all.js` | Balance validation across all replay sources |
| `c:\libraries\prismata-replay-parser\balance_passed_codes.json` | 32,973 balance-validated replay codes |
| `tools/prismata_sniffer.py` | TCP proxy for Prismata AMF3 protocol — hook framework, Moved redirect interception, dynamic port proxying, replay code capture, live game state tracking (auto-F6 + clipboard + click tracking) |
| `bin/live_game_state.json` | Live game state output from sniffer (written each turn, deleted on GameOver) |
| `tools/prismata_advisor.py` | Python overlay — clipboard monitor + F6 sanitization + C++ --suggest + tkinter always-on-top display |
| `tools/audit_selfplay_s3.py` | S3 data integrity audit (11 checks: CRC, NaN, outcome consistency, duplicates, win rates) |
| `tools/export_discord_full.sh` | Full Discord channel export (strategy channels, both servers, needs token arg) |
| `tools/search_discord_ai_feedback.py` | Search Discord exports for AI/bot feedback (5 keyword categories) |
| `run_advisor.bat` | One-click overlay launcher (pre-flight checks for exe + weights) |
| `run_prismata_tools.bat` | Combined launcher — sniffer proxy + advisor overlay + autopilot (pass --autopilot to enable, --auto for full-auto, --dry-run for testing) |
| `tools/prismata_autopilot.py` | AI move injection engine — captures F6 state, runs --suggest, injects clicks via sniffer proxy. Semi-auto (file trigger) and full-auto modes |
| `bin/prismata_capture_codes.txt` | Sniffer-captured replay codes (TSV: timestamp, code, source). Append-only. |
| `bin/commentary_*.txt` | AI-generated game commentary. `== MESSAGE N ==` delimited for Discord (<2000 chars each). Named by replay code. |
| `tools/prismata_commentator.py` | Live AI commentator — sniffer events → Claude Haiku → chat injection (Phase 1 working) |
| `tools/prismata_game_state.py` | Shared game state model — TurnRecord, GameContext, GameNarrative with callback registration |
| `tools/discord_post_helper.py` | Clipboard-based Discord message poster — reads `== MESSAGE N ==` delimited commentary files, copies each to clipboard sequentially |
| `tools/generate_commentary_data.py` | Fetches replay from S3, runs C++ `--analyze`, outputs per-turn eval/buys/agreement. Flags: `--validate` (resource-validated buys), `--eval-only` (neural eval only), `--verbose` |
| `tools/commentary_prompt.md` | Condensed Prismata knowledge base for commentary system prompt (~2,400 tokens) |
| `docs/plans/commentary-generation-instructions.md` | Full commentary writing workflow: data extraction commands, game knowledge reference, Discord format requirements, tone guidelines |
| `tmp_proxy_hosts.ps1` | Set hosts to PROXY mode (127.0.0.1) for sniffer — needs UAC |
| `tmp_restore_hosts.ps1` | Set hosts to DIRECT mode (3.229.49.48) for normal play — needs UAC |
| `prismata_decompiled/` | Decompiled Prismata client ActionScript source (Game.as, State.as, UIKeyboard.as) |

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
| `docs/plans/hyperparameter-experiments-v2.md` | Experiment plan v2 (COMPLETE — tanh fix, 6 expert critiques, phased approach) |
| `~/.claude/plans/intel-arc-b580-xpu-acceleration-v2.md` | Intel Arc B580 GPU acceleration plan v2 (DONE — 4.5x speedup with XPU+nw4) |
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
| `docs/plans/2026-02-18-prismata-overlay-advisor.md` | Neural eval overlay plan (clipboard → C++ --suggest → tkinter overlay) |
| `docs/plans/2026-02-18-overlay-context.md` | Standalone context document for overlay plan (no prior knowledge needed) |
| `docs/plans/2026-02-18-t4-training-plan.md` | GPU training experiment plan (L4 on GCP, T4 spot on AWS, 6 phases, 15 runs) |
| `docs/plans/2026-02-18-training-plan-context.md` | Standalone context doc for external review of training plan |
| `docs/plans/2026-02-19-training-next-steps.md` | Training plan v3 FINAL — 9 expert reviews incorporated, 3 parallel runs |
| `docs/plans/2026-02-19-training-plan-context.md` | Context doc v3 FINAL — accompanies training plan for external reviewers |
| `docs/plans/2026-02-19-selfplay-audit-plan.md` | S3 selfplay data integrity audit plan (CRC, duplicates, statistics) |
| `docs/claude-app-instructions.md` | Updated project instructions for Claude Windows app |
| `docs/plans/2026-02-20-live-commentator-plan.md` | Live AI commentator plan (sniffer → Haiku → edge-tts → OBS/Twitch) |
| `docs/plans/2026-02-20-commentary-knowledge-extraction.md` | Instructions for new context to extract game knowledge from guides |
| `docs/commentary-knowledge/` | Extracted Prismata strategy knowledge for commentator (7 KB files + README + sources, ~5,090 lines). 280+ sources: 148 YouTube transcripts, 24 Twitch VODs (36.5h), 45 blog articles, 629 Reddit posts, 27 prismatalibrary.blog articles, 12 wiki guides, 24 Wayback recoveries. See README.md for index. |
| `docs/commentary-knowledge/RESEARCH-HANDOFF.md` | Instructions for delegating further Prismata research to external AI — lists all processed sources to avoid duplication |
| `docs/prismata-strategy-guide.md` | Comprehensive human-readable strategy guide (17 chapters, synthesized from all sources) |
| `docs/recovered-sources/` | Full-text archive of recovered wiki guides + Wayback Machine content (21 files) |
| `docs/plans/2026-02-21-gui-enhancement-plan-v2.md` | GUI enhancement plan v2 (7 phases: policy fix, eval bars, parallel eval, history graph, card overlay, naming) |

## Tournament Results Summary

| Matchup | Games | Win Rate | Notes |
|---|---|---|---|
| PrismatAI_UCT vs MediumAI | 60 | 41.7% | Neural eval has real signal |
| PrismatAI_UCT vs OriginalHardestAI | 64 | 10.9% | Weak but not random |
| PrismatAI_AB vs MediumAI | 128 | 43.8% | Search type doesn't matter |
| HardestAI vs OriginalHardestAI | 60 | 50.0% | Track A fixes are neutral |
| RandomAI vs MediumAI | 100 | 0% | Baseline floor |
| EasyAI vs MediumAI | 100 | 6% | Baseline |
| **Run B (256h/3L, 722K) AB vs OriginalHardestAI** | **2,016** | **51.9%** | **722K games, 85.6% val acc, CI [49.7%, 54.1%]. NEW CHAMPION** |
| 256h (305K games) AB vs OriginalHardestAI | 4,032 | 45.3% | 330K games, 86.1% val acc, CI [43.8%, 46.8%] |
| E2b (256h) AB vs OriginalHardestAI | 1,008 | 26.7% | V2 winner, 63K games, tanh+MSE, LR=1e-5 |
| E1b (512h) AB vs OriginalHardestAI | 1,008 | 19.6% | V2, tanh+MSE, LR=1e-5 |
| Unfixed model AB vs OriginalHardestAI | 1,120 | 3.6% | Pre-v2 (tanh mismatch, high LR) |
| R12_smooth90 (256h/3L) AB vs OriginalHardestAI | 11,060 | 19.3% | 500K records, d=0.20, s=0.90 |
| E2b (256h) AB vs OriginalHardestAI (reconfirmed) | 3,400 | 28.9% | 2.3M records, same 26.7% ballpark |
| Self-play v1 training | 16 ep (early stop) | 76.9% val acc | 10K games, epoch 1 best, value-only |

## Replay API

Replays stored as gzipped JSON on S3: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` (URL-encode `+` → `%2B`, `@` → `%40`).

**Replay search API**: `POST https://prismata-stats.web.app/api/search/replays` (form-encoded: `lower_date`, `upper_date`, `lower_rating`, `replay_rated`). Needs `ssl.CERT_NONE` in Python. `prismata.net` SSL cert expired. 31,506 expert replays fully synced as of Feb 19, 2026 — no new replays missing.

**prismata-stats submit API**: `POST https://prismata-stats.web.app/replays/submit` — form field `codes` (newline-separated). Batches of 50 work fine, processes every 5 min. Used to bulk-submit 4,306 community codes (Feb 20).

**expert_replays.json key format**: Uses capital `Code` (not `code` or `replayCode`). Other fields: `P1Name`, `P2Name`, `P1RatingIni`, `P2RatingIni`, `StartTime`, `Result`, `Deck`.

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
