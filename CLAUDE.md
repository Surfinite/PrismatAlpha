# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play training: see `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (Feb 17, 2026)

**Self-play iteration 2 training COMPLETE.** Best model: 81.9% val accuracy (epoch 1, value-only, 2.3M records from 63K games). Same overfitting pattern as iter 1 — best at epoch 1, train acc hits 98%+ by epoch 9. Weights exported to `neural_weights.bin`. Previous models: `neural_weights_selfplay_v1.bin` (iter 1, 77% val acc, 10K games), `neural_weights_expert_backup.bin` (expert-trained).

**Overfitting experiments PARTIALLY COMPLETE (Feb 17).** Ran 3 v1-plan experiments with 1M records (~27K games, RAM-limited): (1) no warmup + flat LR=6e-5, (2) dropout 0.3 + WD 1e-3, (3) smaller model (256 hidden, 739K params). All converged to ~75.4-75.5% val accuracy ceiling. However, these experiments had confounds: expert data was mixed in (20%), the training/inference tanh mismatch (v2 plan Cause 0) was never fixed, no tournament WR was measured, and no step-level evaluation was used. The v2 experiment plan (`docs/plans/hyperparameter-experiments-v2.md`) identifies fixing the tanh mismatch + loss function as the #1 priority — this was never tested. More data helps val accuracy (1M→2.3M records raised val acc from 75.5%→81.9%), but higher val accuracy has historically produced *worse* WR (77% val→10% WR, 82% val→3% WR), so the training procedure must be fixed before scaling data.

**Self-play generation ACTIVE** via TheWatcher (Task Scheduler, every 5 min). ~175K games generated (6.5M records, Feb 17, growing), targeting 500K for iteration 2+ retraining. Local: `bin/run_selfplay.bat` (double-click from Explorer, 4 threads per process, run multiple times for more CPU). EC2: `bash aws/launch_selfplay.sh c5.2xlarge 5000 1 2` — TheWatcher auto-relaunches when batches finish. GCP: `bash gcp/launch_selfplay.sh n2-standard-8 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Azure: `bash azure/launch_selfplay.sh Standard_D8als_v7 5000 1 2 N` — TheWatcher monitors and auto-relaunches. Use `/status` slash command for a quick dashboard. Crash-safe: each run writes to timestamped `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/` subdirectory.

**AWS EC2 self-play** pipeline verified working (Feb 15-16). Boots Windows Server, downloads exe+config from S3, patches config to enable SelfPlay_CI, runs self-play, uploads shards to `s3://prismata-selfplay-data/results/` every 5 min (copy-to-temp sync), auto-terminates. AWS account on paid plan (c5 instances unlocked). vCPU quotas: 64 on-demand + 128 spot (Standard). Fleet: 8 on-demand + 16 spot c5.2xlarge = 192 vCPUs. Use `USE_SPOT=true` for spot instances (separate quota, can run both simultaneously). TheWatcher handles S3 sync, auto-relaunch, and quota-aware scale-up (confirmed working: auto-detected spot quota 64→128 increase and launched 8 additional instances within 30s).

**GCP Compute Engine self-play** pipeline set up (Feb 16). Uses same S3 bucket (hybrid cloud — GCP instances install AWS CLI). GCP project `prismata-selfplay`, zone `us-central1-a`. Quotas: N2_CPUS=200, INSTANCES=24, PREEMPTIBLE_CPUS=0 (no spot). TheWatcher monitors GCP instances and auto-relaunches. **GCP batch size fixed** (Feb 16) — GCP instances were crashing after ~8 games because `games_per_instance: 5000` → 2500 rounds/process exceeded x86 OOM threshold. EC2 used 2000 (1000 rounds/process) and worked fine. Fixed `watcher_config.json` to use 2000 for GCP too.

**Azure self-play** pipeline verified working (Feb 16-17). Multi-family deployment in North Europe: 8 VMs across D-series v7 (Dads, Dalds, Dals, Das) + F-series v7 (Fads, Falds, Fals, Fas) = 64 vCPUs (maxed). Each family has 10 vCPU quota, fits one 8-vCPU instance. Same hybrid S3 pattern as GCP. Per-family quota is 10 vCPUs default (1 D8 VM each) — spread across families to bypass. 36+ unrestricted D8 families available. Regional cap: 128 vCPUs (increased from 64, Feb 17). Support request pending for per-family increase (Dalsv7->64, Falsv7->64) to consolidate onto fewer families. TheWatcher monitors, auto-deallocates stopped VMs, auto-relaunches. Launch: `bash azure/launch_selfplay.sh Standard_D8ads_v7 1000 1 2 N`. Use `LOCATION=australiacentral` for other regions (separate Regional quota).

**Next actions:**
1. **Fix training/inference mismatch (tanh bug)** — model trains MSE on unbounded logits but C++ applies tanh. Test `tanh`-in-training + MSE vs `BCEWithLogitsLoss`. See v2 plan Phase 0 (`docs/plans/hyperparameter-experiments-v2.md`).
2. **Implement streaming data loader** for `train.py` — current loader OOMs on full dataset (6.5M records = 44GB). Need to stream shards from disk during training so we can use all 175K+ games. Parallel track with #1.
3. **Re-run LR sweep with fixed loss function** — the v1 experiments showed regularization/model-size don't help, but the loss function was broken. See v2 plan Phase 1.
4. **Continue data generation** toward 200K+ games. Currently ~175K total (Feb 17), local fleet generating (cloud fleet idle).

**Current neural net strength:** Self-play v2 model (81.9% val acc, 63K games) — tournament eval shows **~3% WR** vs OriginalHardestAI (500+ games, AB search + NeuralNet eval). Worse than expert-trained model (~10% WR). Root cause: training procedure issues (tanh mismatch, LR too high) — see v2 experiment plan. More data alone made val acc higher but WR worse. Historical: ~42% WR vs MediumAI (expert UCT).

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
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
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

## Gotchas & Non-Obvious Patterns

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping table below.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork (Surfinite/PrismatAlpha). Push to `PrismatAlpha`.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` config flag preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to stderr, does NOT abort.
- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` gives 4GB address space (Feb 15 fix). Still use `"Threads": 4` in config.txt and run multiple bat instances for parallelism. Each process gets its own limit. CI workflow overrides Threads via `nproc` (2 on windows-latest, safe). Verbose per-turn logging and `_stateSnapshots` JSON serialization are now suppressed when `SaveReplays: false` to reduce heap churn. Process silently dies at ~1400 games with 1M rounds — config now uses 1000 rounds per batch and `run_selfplay.bat` loops automatically. Cloud instances must also use ≤1000 rounds/process (`games_per_instance: 2000` with 2 processes) — GCP was crashing at 2500 rounds/process until this was fixed.
- **Debugging cloud worker crashes**: Download `log_worker_*.txt` and `selfplay_boot.log` from S3 results dir. Working instances show `[Progress] X / N rounds` lines; crashing instances cut off at `[SelfPlay] Exporting...` with no progress. Compare patched configs between providers — differing `rounds` values are a common misconfiguration.
- **Blend tournaments concluded**: Neural component hurts performance. Don't revisit until model >60% val accuracy. See `docs/blend-tournament-results.md`.
- **Batch validation**: 287 replays tested, C++ engine confirmed correct. After fixing 3 TS tooling bugs: 117 PASS (41.3%), 166 FAIL (all TS-side), 4 ERROR. Remaining failures are action resolution differences in TS→C++ conversion (70% start with gold/green resource divergence). See `docs/plans/engine-validation-plan.md`.
- **Self-play crash safety**: Each run writes to `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/`. Restart anytime — only in-flight games lost. `load_selfplay.py` auto-scans all `run_*` subdirectories.
- **Run self-play from Explorer**: Use `bin/run_selfplay.bat` — runs in its own cmd window, immune to Claude Code context kills. Has startup exe check and 5s error delay to prevent spin-looping during rebuilds (previously created 18K+ junk log files when exe was missing).
- **GUI Watch Training / Watch Eval modes**: Menu items in Prismata_GUI that run self-play or eval games with live display. Both generate training shards. Watch Training = same AI self-play (1s think). Watch Eval = PrismatAlpha_AB_Legacy vs OriginalHardestAI (7s think). 4 threads each (1 displayed + 3 background). Color swap (same board, swapped sides) auto-enabled when players differ. Source: `source/gui/GUIState_WatchTraining.cpp/.h`.
- **Console output routing**: `[SelfPlay]` and `[Progress]` messages use `fprintf(stderr, ...)` so they appear on console. Per-turn buy action logging only runs when `SaveReplays: true` (suppressed in self-play mode). New user-facing messages in Tournament.cpp should use stderr.
- **EC2 config patching**: `launch_selfplay.sh` patches config line-by-line (not regex across properties) because JSON property ordering varies — `"run"` may come before or after `"name"` in tournament entries. Don't switch back to cross-property regexes.
- **AWS CLI in Git Bash**: AWS CLI is a native Windows exe. Temp file paths must be Windows-accessible (not `/tmp/`). Use `file://` prefix for user-data (not `base64`). PATH needs: `export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"`.
- **x86 OOM with large vectors**: Don't pre-allocate large `std::vector<GameState>` upfront (e.g., 10K rounds). GameState objects are heavy — allocate per-batch instead. Symptom: process exits silently mid-tournament with no `[SelfPlay] COMPLETE` message.
- **Selfplay shard CRC**: `load_selfplay.py` CRC check fails on shards from runs that crashed or are still in progress (no footer written). Use `validate_crc=False` for live/partial data.
- **Selfplay positions per game**: Actual average is ~37 records/game (both players' turns combined), NOT ~440 as originally estimated. A 10K-game run yields ~370K training records, not 4.4M.
- **Selfplay shard binary format**: Header is 16 bytes: magic `0x50445350` ("PDSP") + version(4) + state_dim(4) + record_size(4). Record size = 7152 bytes. No game count stored — calculate: `(file_size - 16) / 7152` = positions, `positions / ~37` = estimated games.
- **Selfplay game counting**: To count total games across all shards: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-16)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>16); print(f'{total} records, ~{total//37} games')"`.

- **S3 download dir structure**: `aws s3 sync` creates timestamp dirs without `run_` prefix (e.g., `2026-02-15_12-25-50/`) containing nested `run_*` subdirs. Must scan recursively to count all data.
- **Windows file size caching**: `ls`/`Get-ChildItem` may show 0 bytes for files with open write handles. Use `python -c "import os; print(os.path.getsize(path))"` to get actual size.
- **Replay balance validation**: `validate_balance_all.js` checks all replay costs against `cardLibrary.jso`. Output: `balance_passed_codes.json` (32,973 safe codes). Replays with old unit costs (pre-balance-patch), event-mode starred units, or removed units are rejected. Cost normalization sorts resource letters (`8GBC` == `8BCG`). Run once; incremental via `balance_results.json`.
- **Python stdout buffering**: Long-running Python processes (e.g., `train.py`) show no output in Claude Code Bash tool. Use `PYTHONUNBUFFERED=1` prefix to get real-time output.
- **Training CRC**: `train.py` calls `load_all_shards(validate_crc=False)` — required because shards from in-progress/crashed runs lack CRC footers.
- **Training overfitting — partially investigated**: Feb 17 experiments showed regularization (dropout 0.3, WD 1e-3) and model size (256 hidden) don't change the ~75.5% val ceiling with 1M records. More data raises val accuracy (1M→2.3M: 75.5%→81.9%). BUT: higher val accuracy produced worse WR (77% val→10% WR, 82% val→3% WR), and the v2 experiment plan identifies a critical untested issue: training/inference tanh mismatch (trains MSE on unbounded logits, deploys with tanh). All Feb 17 experiments ran with the broken loss function and unplanned expert data mixing (20%). Fix the loss function before scaling data. See `docs/plans/hyperparameter-experiments-v2.md`.
- **Training RAM limit**: Full dataset (6.5M records, 1837 shards) = ~44GB raw data. `load_all_shards` loads everything into RAM then concatenates (doubling peak usage). With 32GB RAM: max ~1M records safely with `--max-records 1000000`. Use `--num-workers 0` to avoid PyTorch shared memory errors with large datasets. Need streaming data loader for full dataset.
- **D: drive backup**: `D:\PrismataAI_backup\` has selfplay data (3 GB, 200 shards), models, weights (expert + selfplay v1), config, and training run logs. Created Feb 15.
- **Experiment logs**: `training/runs/{timestamp}.json` — full per-epoch metrics, hyperparameters, git hash. Use for plotting/analysis.
- **PID-based random seeding**: All 3 exe entry points use `srand(time ^ PID)` instead of `srand(time)`. Prevents identical random sequences when launching multiple bat instances in the same second — critical for the parallel self-play pattern.
- **Game_id namespacing**: `load_selfplay.py` offsets game_ids by 1M per source directory to prevent collisions across runs. Each C++ process starts game_id at 0, so without namespacing, different runs share IDs and train/val splits leak data.
- **Value-only model export**: `export_weights.py` exports zero-initialized policy tensors for value-only models (4 extra tensors). C++ loader requires all 26 tensors unconditionally — a value-only export with only 22 tensors will fail to load with `expected tensor 'policy.linear1.weight', got 'value.linear1.weight'`.
- **EC2 spot has separate vCPU quota**: `USE_SPOT=true bash aws/launch_selfplay.sh ...` uses spot pricing under a separate quota. Run on-demand + spot simultaneously for double capacity. Quota codes: `L-34B43A08` (spot), `L-1216C47A` (on-demand).
- **SelfPlayDataExport requires loaded neural net**: If `neural_weights.bin` fails to load (e.g., missing tensors), the exe runs games but writes ZERO training shards silently. Only a stderr warning: `[SelfPlay] WARNING: SelfPlayDataExport enabled but neural net not loaded. Skipping export.` Always verify weights have all 26 tensors before deploying.
- **EC2 file-lock sync**: `Write-S3Object` cannot read files held open by the C++ exe. The periodic sync in `launch_selfplay.sh` copies to a temp dir first via `Copy-Item` (which can read locked files), then uploads from temp.
- **AWS quota management**: Check quota: `aws service-quotas get-service-quota --service-code ec2 --quota-code <CODE> --region eu-north-1`. Request increase: `aws service-quotas request-service-quota-increase --service-code ec2 --quota-code <CODE> --desired-value <N> --region eu-north-1`. No penalty for requesting — AWS may partially approve. Modest asks (64-128) more likely auto-approved.
- **GCP hybrid cloud**: GCP instances install AWS CLI and upload to the same S3 bucket (`prismata-selfplay-data`). No GCS infrastructure. AWS credentials passed via instance metadata from `gcp/.aws_credentials`. GCP project: `prismata-selfplay`, zone: `us-central1-a`.
- **GCP quotas**: N2_CPUS=200 (25 n2-standard-8), INSTANCES=24, PREEMPTIBLE_CPUS=0 (no spot). SSD_TOTAL_GB=250 may limit concurrent instances with 50GB SSD boot disks. Check: `gcloud compute regions describe us-central1 --project=prismata-selfplay --format="json(quotas)"`.
- **GCP instance self-deletion**: GCP instances use `gcloud compute instances delete` (not Stop-Computer like EC2). Requires `compute-rw` scope. Falls back to Stop-Computer if delete fails.
- **GCP gcloud.cmd vs gcloud**: Use `gcloud.cmd` in PowerShell scripts, `gcloud` in bash scripts. Git Bash cannot execute `.cmd` files directly — using `gcloud.cmd` in bash fails silently. SDK path: `C:\google-cloud-sdk\bin`. TheWatcher pipes bash output through `2>&1` capture (not `Out-Null`) to make errors visible in the log.
- **gcloud.cmd stderr noise**: `gcloud.cmd` emits harmless stderr about temp files ("Access is denied; Could Not Find tmpfile") even on successful calls. TheWatcher's `Invoke-CloudApi` logs these as warnings but correctly reports the call as successful. Don't treat as errors.
- **TheWatcher reliability (Feb 16 refactor)**: All cloud API calls go through `Invoke-CloudApi` wrapper (captures stderr, returns success/failure). Relaunch and scale-up decisions require `$awsApiSuccess`/`$gcpApiSuccess` = true. When API fails, tracked_instances preserved (not reset to 0). After 6 consecutive failures (30 min), force-reset. S3 shard activity monitoring provides ground truth. Status file includes `api_health`, `shard_activity`, `health` sections. Test suite: `test_watcher_e2e.ps1` (22 scenarios), `test_watcher_smoke.ps1`, `test_watcher_canary.ps1`, `test_watcher_log_health.ps1`.
- **TheWatcher change detection**: Watcher logs `CHANGE:` lines when values differ between cycles (instance counts, quotas, API health transitions, local processes). Grep `CHANGE:` in `watcher_log.txt` to see all state transitions.
- **GCP quota increase on new projects**: Google denies quota requests if the project is <48 hours old or lacks billing history. Must wait 48 hours and resubmit, or escalate via Sales Rep. Our request for CPUS_ALL_REGIONS 12→128 was denied Feb 16; resubmit after Feb 18. **CPUS_ALL_REGIONS=12 is the actual GCP bottleneck** — not N2_CPUS (200) or INSTANCES (24). Only fits 2 instances (1x n2-standard-8 + 1x n2-standard-4 = 12 vCPUs).
- **Cloud provider comparison (Feb 16)**: Oracle Cloud is not competitive for Windows batch compute — Windows licensing ($0.092/OCPU/hr) eliminates price advantage, x86 "Out of Capacity" is common, no spot for Windows. Azure is the better third cloud option (spot VMs at ~$0.07/hr for D8s_v5, $200 free credits, but default quota ~10 vCPUs requires increase request).
- **Azure `--custom-data` encoding**: No Unicode chars > U+00FF (em-dashes, smart quotes) in startup scripts. Azure CLI's Python encodes to latin-1. Use `PYTHONUTF8=1` before `az` commands as safety net.
- **Azure VM name limit**: Windows VMs max 15 chars for computer name. Script uses `prsm-HHMMSS-N` (13 chars).
- **Azure VM billing + quota**: `Stop-Computer` only stops OS ("VM stopped" state, still bills AND consumes family vCPU quota). Must `az vm deallocate` (releases quota, stops billing) then `az vm delete`. TheWatcher handles this automatically.
- **Azure batch loop for OOM**: Azure launch script runs 250 rounds per batch in a restart loop (same pattern as `run_selfplay.bat`). Without this, processes crash at ~80 games due to x86 4GB address space exhaustion. The config is patched to `"rounds":250` and the PowerShell loop runs `totalBatches = ceil(gamesPerProcess / 250)` iterations. EC2 has the same vulnerability but hasn't hit it yet — consider applying the same fix.
- **Azure FSv2 unavailable**: FSv2 returns empty from `az vm list-skus` across all tested European regions (northeurope, westeurope, uksouth, ukwest, francecentral) despite showing in `az vm list-sizes`. Always use `list-skus` (actual availability) not `list-sizes` (theoretical). D-series v7 (`Standard_D8als_v7`) works. Check: `az vm list-skus --location northeurope --size Standard_D --query "[?restrictions[].reasonCode!='NotAvailableForSubscription']"`.
- **Azure `az.cmd` JMESPath broken**: `az.cmd` routes through `cmd.exe` which mangles JMESPath special characters (`]`, `.`, `{`, `:`). Symptoms: `"was unexpected at this time"` errors. Fix: skip `--query`, fetch full JSON with `--output json`, filter in PowerShell with `Where-Object`. The watcher was fixed Feb 17.
- **Azure quota increases auto-reject on new/free-credit accounts**: Both "My Quotas" direct submit and the `az quota` CLI extension get auto-rejected. Must submit support requests (Severity C, 24-48hr response). Per-family increase auto-increases regional quota by the same amount (per MS docs). v7 families don't appear in the support ticket VM family dropdown — request through My Quotas → auto-reject → "Create a support request" button.
- **Azure CLI path**: `"$AZ"` where `AZ="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az"`. In PowerShell: `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd`.
- **Writing shell variables to files**: Use `printf '%s' "$VAR" > file` not `echo "$VAR" > file`. `echo` may interpret backslash sequences in variable content, corrupting PowerShell scripts.
- **Azure VM think-time multipliers**: Based on thread-to-core ratio vs local Ryzen 5700X3D. F2s_v2 (2 vCPUs, 4 threads = 2:1 oversubscription): **3x**. F8s_v2/D8als_v7 (8 vCPUs, 4 threads = 1:2 ratio): **2x**. Formula: base cloud penalty (2x) × oversubscription factor (threads/cores if >1).
- **Azure hybrid cloud**: Same S3 bucket pattern as GCP — Azure VMs install AWS CLI, upload to `s3://prismata-selfplay-data/`. AWS credentials from `azure/.aws_credentials`.
- **Azure quota management**: Two-tier system — Total Regional vCPUs (ceiling, 64) + per-family vCPU limits (default 10 each). Both must allow a VM. Current fleet: 8 VMs across D-series v7 (Dads, Dalds, Dals, Das) + F-series v7 (Fads, Falds, Fals, Fas) = 64/64 vCPUs maxed. Each family at 8/10. Request per-family increases (Dalsv7 + Falsv7 to 128) to consolidate. "VM stopped" still consumes quota — must deallocate to release. Check: `az vm list-usage --location northeurope --output json`. Increase via Portal > Quotas > Compute. **Quotas are per-region.**
- **PowerShell JSON files have UTF-8 BOM**: `watcher_status.json` and `watcher_config.json` are written by PowerShell with BOM. Python must use `open(path, encoding='utf-8-sig')` — default `utf-8` encoding will fail on `json.load()`.
- **Python cp1252 on Windows**: Python defaults to cp1252 for stdout on Windows, which can't encode Unicode (e.g., block characters). Prefix scripts with `PYTHONIOENCODING=utf-8` or stick to ASCII output.
- **Churchill paper URLs**: His papers moved from `cs.mun.ca/~dchurchill/` to `davechurchill.ca/publications/`. Use the latter for any PDF links.
- **GUI/engine decoupling**: Engine (`source/engine/`, `source/ai/`) has zero SFML imports — compiles independently (proven by `source/standalone/`). GUI is ~4,100 LOC across 19 files in `source/gui/`, with ~2,200 lines of direct SFML rendering. No rendering abstraction layer exists. 264 PNG assets (~10 MB). SFML doesn't support Emscripten/WASM — web conversion requires either SDL2 abstraction or JS rewrite of rendering layer.
- **Future feature plans in claude-mem**: Non-essential feature ideas are stored in persistent memory (not plan files): GUI spectator mode (#1385), web-based remote advisor (#1524). Use `mcp__plugin_claude-mem_mcp-search__search` to retrieve.
- **claude-mem 10.0.7 vector search**: We filed bug #1104 (onnxruntime-common resolution fails on Windows). Chroma runs manually (not auto-start) on port 8000 with 11K+ vectors. Fixes landed upstream (WASM backend `67ba17c`, cache corruption `224567f`, orphaned subprocesses `e1ef14d`). **Update claude-mem when >10.0.7 available** — after update verify Chroma auto-starts. See claude-mem memory #2153.

## User Preferences

- Efficiency over speed — minimize API credits, maximize local PC computation
- Comfortable with long-running unattended tasks (hours). Tell them when something can run overnight.
- Git comfort level: self-described "noob" — explain git ops clearly, always confirm before push/force
- The user is "Surfinite" everywhere — GitHub, Prismata, Discord, etc.

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
| `aws/launch_tournament.sh` | EC2 tournament launcher (NeuralTest + NeuralAB vs OriginalHardestAI) |
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
