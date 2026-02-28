# PrismataAI — Project Instructions

> **Full project history** (sections 1-29, completed milestones, tournament results): see `docs/PROJECT_HISTORY.md`
> **Execution plan** for self-play training: see `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (Feb 28, 2026)

**First correct-data model: ExpertJS R12 256h/3L = 6.0% WR** vs OriginalHardestAI (1.33M examples, epoch 6 best). All prior WR numbers (3.6%→51.9%) were trained on buggy C++ engine data — those models collapsed to ~11% WR when engine bugs were fixed. Historical progression moved to `docs/PROJECT_HISTORY.md`. Current deployed weights: `bin/asset/config/neural_weights.bin`.

**AS3→JS transpilation COMPLETE** (Feb 26, branch `feature/as3-js-transpilation`). Core engine transpiled: 18 AS3 files → 18 JS modules. Integration layer with MCDSAI worker-based self-play. 100% replay validation on 500 replays. Run: `cd js_engine && node selfplay_main.js --games 10 --jsonl out.jsonl 2> log.txt`.

**Expanded training datasets READY**: Expert 1500+ (2.63M examples), Expert 2000+ (1.33M). Retrain pending.

**Training pipeline hardened (Feb 19).** 6 fixes deployed to S3: max_records overshoot, streaming label sanity check, num-workers default 8→2, LR scheduler state on resume, double-tanh verification fix, vectorized subsampling.

**Key training findings** (V2 + T4 experiments, Feb 17-19): (1) data volume > hyperparameters, (2) smaller model (256h) trains longer before overfitting, (3) MSE vs BCE is a wash, (4) subsampling hurts. Winner architecture: R12_smooth90 (256h/3L, lr=2e-5, d=0.20, s=0.90). Full experiment results in `training/runs/` and `docs/PROJECT_HISTORY.md`.

**Self-play data: ~722K games** (Feb 20 audit: 7,804 shards, 26.7M records, 178 GB in S3). Local: `bin/run_selfplay.bat`. Cloud: `aws/launch_selfplay.sh`, `gcp/launch_selfplay.sh`, `azure/launch_selfplay.sh`. **AWS selfplay DISABLED**, **Azure PAUSED/CLEANED**, GCP was active. Use `/status` for dashboard. All self-play data was generated with buggy C++ engine (defense-reset bug) — both sides, internally consistent.

**Cloud GPU training** verified on AWS (`aws/launch_training.sh`, g6.2xlarge L4 spot ~$0.40/hr) and GCP (`gcp/launch_training.sh`, g2-standard-8 L4). Use `--streaming` for full dataset, `MACHINE_TYPE=g2-standard-8` on GCP (16GB OOMs). Full cloud infrastructure details in `docs/cloud-ops-reference.md`.

**Local training: `--device xpu --num-workers 4`** (Intel Arc B580, 3.2x speedup vs CPU). Streaming loader supports `--num-workers 2-4`.

**Pre-public security cleanup COMPLETE** (Feb 28). Cloud resource IDs parameterized via `cloud-config.env` (19 scripts). Sniffer/proxy tools excluded from tracking. Server IPs redacted from docs. Gitleaks verified clean (124 commits). Template: `cloud-config.env.example`.

**Next actions:**
1. **Retrain on expanded dataset** — 2.63M expert examples ready (1500+ rating). Use R12_smooth90 architecture (256h/3L). Local XPU or cloud GPU with `--streaming`.
2. **Mix community replays into training data** — ~35K replays = ~1.3M records. C++ replay stepper (`--replay-dir`) converts to binary shards. Goal: community members' games contribute to training.
3. **Post-game commentary pipeline** — Phases 1-3 COMPLETE. Remaining: Phase 4 (CLI polish), Phase 5 (batch), Phase 6 (Discord bot). Run: `python tools/generate_postgame_commentary.py <CODE>`.
4. **Live commentator Phase 2 (TTS + OBS)** — needs `edge-tts`, `sounddevice`, `obsws-python`, VB-Cable.

**Completed (see `docs/PROJECT_HISTORY.md` for details):** JS transpilation, engine logic audit (4 fixes), LiveHardestAI config port, replay database (128K codes), overlay advisor, autopilot, sniffer live tracking, frontline penalty test (+0.5pp, not significant), MB community issues extraction (350 insights), pre-public security cleanup (cloud config parameterization, sniffer exclusion, IP redaction).

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

**NEVER kill, stop, or unregister the `PrismataAI-TheWatcher` Task Scheduler job.** Runs every 5 min. Manages AWS/GCP/Azure auto-relaunch, quota-aware scale-up, S3 sync. Harmless — only monitors and writes status.

- **Check status**: Read `aws/watcher_status.json` | **Change behavior**: Edit `aws/watcher_config.json` | **View log**: `aws/watcher_log.txt`
- **Boot protection**: Won't auto-launch if status >30 min stale (PC restart or RAM thrashing). Manual launch first, then watcher resumes.
- **RAM pressure hang**: Recovery: `Stop-ScheduledTask -TaskName 'PrismataAI-TheWatcher'; Start-Sleep 2; Start-ScheduledTask -TaskName 'PrismataAI-TheWatcher'`
- **Fleet health**: Check ALL resource types — orphaned disks/NICs/IPs bill silently. See `docs/cloud-ops-reference.md` → "Fleet Health Checks".

## Gotchas & Non-Obvious Patterns

> Cloud provider operational details (AWS/GCP/Azure quotas, CLI quirks, encoding bugs, orphaned resource cleanup) are in `docs/cloud-ops-reference.md`.

- **Cloud config pattern**: All cloud scripts source `cloud-config.env` (gitignored) via `SCRIPT_DIR`/`BASH_SOURCE[0]` relative path. Template at `cloud-config.env.example`. Single-quoted heredocs use `__CLOUD_BUCKET__`/`__AWS_REGION__` placeholders replaced post-heredoc: `USERDATA="${USERDATA/__CLOUD_BUCKET__/$BUCKET}"`.
- **Gitleaks binary**: `/tmp/gitleaks/gitleaks.exe` (v8.22.1). Run: `gitleaks detect --source . --no-banner -v`. Use `--no-git` flag for working tree scan (includes untracked files).

### Engine & Build

- **Internal name system**: The engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full 105-unit mapping in `cardLibrary.jso`.
- **AS3↔C++ naming dictionary**: Key mappings for cross-engine comparison: `role` (string) = `CardStatus` (enum), `disruptDamage` = `m_currentChill`, `MOVE_MELEE` = `ASSIGN_FRONTLINE`, `glassBroken` flag = `Phases::Breach`, `MOVE_ASSIGN` = `USE_ABILITY`, `MOVE_DEFEND` = `ASSIGN_BLOCKER`, `damageItCanTake` = `currentHealth()`, `deadness` (string) = `AliveStatus` + `CauseOfDeath` (enums). Full dictionary in `docs/plans/engine-logic-audit-plan.md` § Key Naming Differences.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork (Surfinite/PrismatAlpha). Push to `PrismatAlpha`.
- **Branch can switch unexpectedly**: When working across multiple branches, always `git branch --show-current` before operations that depend on branch-specific files. Background task completion or context recovery can leave you on a different branch than expected.
- **Config tournament toggles**: Always check which tournaments have `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` preserves original AI behavior. `OriginalHardestAI` is the stable baseline. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NeuralNet.cpp diagnostics**: Gated behind `#ifdef NEURAL_NET_DEBUG`.
- **PRISMATA_ASSERT**: Soft assert — prints to **stdout** (`std::cout` in `PrismataAssert.cpp:30`), does NOT abort. Use `std::ifstream` instead of `FileUtils::ReadFile` when stdout must stay clean (e.g., `--suggest` mode).
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` gives 4GB. Use `"Threads": 4` + multiple bat instances. Process dies silently at ~1400 games — config uses 1000 rounds/batch, `run_selfplay.bat` loops automatically.
- **x86 OOM with large vectors**: Don't pre-allocate large `std::vector<GameState>` upfront. Allocate per-batch. Symptom: silent exit with no `[SelfPlay] COMPLETE` message.
- **Console output routing**: `[SelfPlay]` and `[Progress]` use `fprintf(stderr, ...)`. Per-turn logging only when `SaveReplays: true`. New messages in Tournament.cpp should use stderr.
- **Tournament `tests/` directory required**: `HTMLTable::appendHTMLTableToFile()` crashes (NULL `fprintf`) if `tests/` doesn't exist in the working directory. Always `mkdir tests` when setting up a new tournament directory. The cloud launcher script already handles this (line 85 of `launch_tournament.sh`).
- **GUI Watch Training / Watch Eval modes**: Menu items in Prismata_GUI. Watch Training = self-play (1s think). Watch Eval = PrismatAlpha_AB_Legacy vs OriginalHardestAI (7s think). 4 threads each. Source: `source/gui/GUIState_WatchTraining.cpp/.h`.
- **GUI/engine decoupling**: Engine has zero SFML imports — compiles independently. GUI is ~4,100 LOC. SFML doesn't support WASM — web needs SDL2 abstraction or JS rewrite.
- **Prismata client architecture**: Adobe AIR/Flash app. C++ engine compiled to AVM2 bytecode via CrossBridge. Memory reading infeasible — use clipboard or network proxy for live state access. **Adobe AIR ignores PostMessage/SendMessage** for keystrokes — must use `SetForegroundWindow` + `SendInput` (brief focus steal ~100ms). This is a platform limitation of AIR's input handling.
- **Clipboard game state export (WORKING)**: F6 copies game state JSON to clipboard. F6 = full (with TurnStartInfo), Shift+F6 = compact. Requires SWF dev mode patch (see below). JSON wrapper key is `"CurrentInfo"` containing `mergedDeck`, `gameState`, `aiParameters`. Card names are **display names** (e.g., "Tarsier" not "Tesla Tower"). Table entries are per-instance (with `instId`, `constructionTime`, `role`, `health`). Source: `prismata_decompiled/scripts/client/Game.as:1226-1249`, `UIKeyboard.as:122-135`.
- **SWF developer mode patch (Feb 18)**: Single byte in `Prismata.swf` (CWS compressed, decompressed offset `0x1580196`): `0x27` (pushfalse) → `0x26` (pushtrue) enables `FlashBuildOptions.developerVersion`. Backup at `Prismata.swf.backup`. **Side effect**: disables load balancing — requires hosts entry pointing the Prismata server hostname to its IP (added via `tmp_restore_hosts.ps1` with UAC). Steam "Verify integrity" will revert the patch.
- **JPEXS FFDec (SWF decompiler)**: Installed at `C:\Program Files (x86)\FFDec\`. CLI: `ffdec-cli.exe -export binaryData <outdir> <swf>`. Extracted AI params at `tmp_swf_extract/` (148=full, 93=short) — plain JSON text despite `.bin` extension. Short params (used after turn 16) are a strict subset of full — no HardestAI-relevant differences.
- **Sniffer duplicate process gotcha**: Multiple sniffer processes can bind to the same ports (SO_REUSEADDR) without error, but only the first one receives connections. Always kill existing sniffer processes before launching a new one: check with `tasklist | grep python` and verify port ownership with `Get-NetTCPConnection -LocalPort 11600`. The old bat-file-launched sniffer won't show in Claude's `run_in_background` tasks.
- **Autopilot only activates for bot games**: Safety check — autopilot skips PvP/spectated games (logs "Skipping — not a bot game"). Must use Play → vs Computer → Master Bot for testing. The check looks for `StartBotGame` in the BeginGame message type.
- **Prismata server Moved redirect**: After initial handshake on port 11600, server sends `["Moved", "<server-ip>", 11610, 11611]` redirecting client to new ports. The sniffer proxy intercepts this, rewrites IP to `127.0.0.1`, and dynamically proxies the new ports. Without interception, the client reconnects directly to the real server IP, bypassing the proxy. AMF3 re-encoding handles the string length change. Server IP/hostname details in the sniffer tools (not tracked in public repo).
- **Hosts file proxy/direct mode**: `tmp_proxy_hosts.ps1` (127.0.0.1, for sniffer) and `tmp_restore_hosts.ps1` (server IP, for normal play). Both use `[System.IO.File]::WriteAllText()` — NEVER use `Set-Content` or regex replacement (can wipe to 0 bytes). Both need UAC. **Current state: check hosts file** — if in proxy mode and sniffer isn't running, Prismata can't connect. These scripts are not tracked in the public repo.
- **Move representation**: `Player::getMove(state, move)` returns a `Move` (sequence of `Action`s). BUY actions resolve to display names via `CardType(action.getID()).getUIName()`. Pattern in `TournamentGame.cpp:57-60`.
- **`--suggest` CLI mode** (DONE Feb 18): `Prismata_Testing.exe --suggest state.json [--player PrismatAlpha_AB] [--think-time 3000]` — reads F6 clipboard JSON, runs neural eval + AI search, outputs clean JSON to stdout. Init noise suppressed via `_dup2` fd redirect. Handles both F6 format (`CurrentInfo` wrapper) and bare state format.
- **`--suggest` clicks array (Feb 20)**: Output now includes `"clicks":[{_type,_id},...]` — wire-protocol-ready sequence for protocol injection. BUY: `_type="card clicked"`, `_id=mergedDeck index` (CardType ID - 2). USE_ABILITY/ASSIGN_BLOCKER/BREACH: `_type="inst clicked"`, `_id=client instId`. SNIPE/CHILL: two clicks (source then target). END_PHASE: `_type="space clicked"`, `_id=-1`. Automatic END_PHASE insertion mirrors `Move::toClientString()` logic.
- **Card.cpp now preserves instId (Feb 20)**: `m_clientInstId` field added to Card class. Previously `instId` from F6 JSON was explicitly ignored (Card.cpp:114). Now stored and accessible via `getClientInstId()`. Returns -1 if not set (non-F6 states).
- **Clipboard F6 timing**: AIR may not write clipboard immediately after F6 keypress. The sniffer uses hash-and-wait polling (snapshot clipboard before F6, poll up to 1s for change) to reliably detect the new state. A single `time.sleep(0.1)` is insufficient.
- **mergedDeck buyCost format**: Digits = gold, `G` = green, `B` = blue, `C` = red (attack resource), `H` = energy. E.g., `"6BGGG"` = 6 gold + 1 blue + 3 green. Card click `_id` in Click messages maps to mergedDeck array index.
- **Replay commandList format**: Commands use `_type` (NOT `_action`) and `_id`. Types: `card clicked`/`card shift clicked` = BUY (\_id = mergedDeck index), `inst clicked`/`inst shift clicked` = CLICK ability (\_id = instance ID), `space clicked` = END\_PHASE, `revert clicked` = UNDO. `clicksPerTurn` array (2×N entries for N turns per player) slices commandList into per-turn segments. `playerInfo` has NO `playerNumber` key — use array index. Ratings in `ratingInfo.finalRatings[i].displayRating`.
- **Click counting ≠ buy counting (CRITICAL)**: `card clicked` in commandList does NOT guarantee a successful purchase. Clicks on sold-out cards (legendary supply exhausted, etc.) are recorded but silently rejected by the game engine. `revert clicked` only undoes intentional undos, not failed clicks. **Any code parsing buys from clicks MUST enforce supply limits**: legendary = 1 per player, rare ≈ 4. Without this, buy counts are inflated — e.g., Mega Drone (legendary) showed 3x purchased from click data when only 1 is possible.
- **Spectator commandInfo contains full game history**: When spectating a game already in progress, the BeginGame message includes `commandInfo.commandList` with ALL prior moves and `clicksPerTurn` with per-turn click counts. This allows complete game reconstruction from any spectator join point.
- **Replay JSON structure**: Fetched replays use `deckInfo.mergedDeck` for card data (NOT `initInfo.mergedDeck`). `initInfo` has `initCards` and `initResources`. Player ratings in `ratingInfo.finalRatings[i].displayRating`.
- **Replay `mergedDeck` has no `supply` field**: Derive supply from `rarity` field — legendary=1, rare=4, normal/trinket=20. `buildTime` defaults to 1 if absent, `fragile` defaults to 0 if absent.
- **C++ `eval_pct` is a string with `%` suffix**: `DoAnalyze` outputs `"eval_pct":"72%"` (not `72.0`). Strip `%` before `float()`. Raw eval is under key `"eval"`, not `"eval_raw"`. See `Benchmarks.cpp:1847`.
- **Sniffer protocol**: Live state tracking (auto-F6 + click tracking → `bin/live_game_state.json`), spectator mode works, chat injection (file trigger: `bin/chat_trigger.txt`), game action injection (EndSwoosh → clicks → EndTurn). **Critical**: Ping confirmation rewriting for injected messages — see sniffer source. `_sanitize_gamestate()` is intentionally duplicated across sniffer/advisor/autopilot — do not refactor.
- **prismata-replay-parser git config**: Must set `git config user.name "Surfinite"` and `git config user.email "Surfinite@users.noreply.github.com"` locally.
- **Churchill paper URLs**: Use `davechurchill.ca/publications/` (old `cs.mun.ca/~dchurchill/` is dead).
- **WebFetch blocked on web.archive.org**: Use CDX API via curl instead.
- **Commentary KB**: Discord insights go to `docs/commentary-knowledge/discord/`, NOT canonical files. `commentary_prompt.md` is manually curated — never auto-generated. Pipeline auto-fetches replays from S3 on first use.
- **Commentary eval sanitization**: Strip `\d+%` patterns from analysis JSON and few-shot examples before narrative generation — Haiku ignores prompt-level instructions otherwise.
- **Task agents can't create new files**: Write tool requires prior Read. Pre-create files in parent context before delegating.

### Self-Play & Data

- **SkipColorSwap auto-detection**: Self-play tournaments auto-detect identical AI configs and skip redundant games. `rounds = desired_games` for self-play.
- **Self-play crash safety**: Each run writes to `bin/training/data/selfplay/run_YYYY-MM-DD_HH-MM-SS/`. Restart anytime — only in-flight games lost. Empty run dirs (config file but no shards) mean the exe was killed before completing any games — harmless, can be deleted.
- **Run self-play from Explorer**: Use `bin/run_selfplay.bat`. Has startup exe check and 5s error delay to prevent spin-looping during rebuilds. **The bat loop only auto-restarts if the window stays open** — killing the process externally (e.g., `taskkill`) also kills the bat loop. Must manually re-launch `run_selfplay.bat` after external kills.
- **Selfplay shard CRC**: Use `validate_crc=False` for live data — crashed/in-progress shards have no footer. ~99.8% of local shards are sentinel (only finalized on clean exit).
- **Selfplay positions per game**: ~37 records/game (both players' turns), NOT ~440. A 10K-game run yields ~370K records.
- **Selfplay shard binary format**: Header 64 bytes (magic, version, feature_dim, record_size, record_count, endian_check, padding) + 4-byte CRC32 footer. Record size = 7152 bytes. Games = `(file_size - 68) / 7152 / ~37`. See `training/load_selfplay.py` for `HEADER_SIZE = 64`.
- **Selfplay game counting**: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-68)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>68); print(f'{total} records, ~{total//37} games')"`.
- **S3 download dir structure**: `aws s3 sync` creates timestamp dirs without `run_` prefix containing nested `run_*` subdirs. Must scan recursively.
- **Self-play uses playout eval**: `SelfPlay_CI` runs `OriginalHardestAI_1s` vs itself. Neural net NOT used for generation — only labeling. ~4 games/min per 4-thread process. P2 wins 57.3% (extra Drone advantage, wider gap than human 50.8% due to 1s think time).
- **S3 data audit (Feb 20)**: 7,804 shards, 26.7M records, ~722K games, 178GB — all clean. Tool: `tools/audit_selfplay_s3.py`.
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
- **train.py positional args**: `data_dir` then `model_dir`. Must pass both for custom output: `python training/train.py training/data training/models/my_run --selfplay-dir ...`.
- **Do NOT install IPEX** (EOL). Use native `torch.xpu` (PyTorch 2.10.0+xpu). `--device xpu --num-workers 4` = 3.2x speedup. BF16/torch.compile not beneficial for current model size.
- **RAM pressure rules**: Max 2 concurrent training jobs. Streaming on 32GB: `--num-workers 2` (4 causes system hang). Cloud 16GB: must use `--streaming`, use g2-standard-8 not g2-standard-4 (OOM-kills). Quick smoke tests: `--max-records 100000`.

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
- **Batch validation**: 2,127 Master Bot replays tested. **Baseline (Feb 20)**: 55.7% pass (1,185/2,127). **After engine audit fixes (Feb 23)**: 50.4% pass (1,072/2,127) — REGRESSED by 5.3pp. Fixes made engine stricter (USE_ABILITY 40.7% of failures). Remaining failures are genuine TS↔C++ semantic differences. Not blocking self-play.
- **Replay balance validation**: `validate_balance_all.js` checks costs against `cardLibrary.jso`. Output: `balance_passed_codes.json` (32,973 codes). Incremental via `balance_results.json`.

### Dashboard, Cloud Ops & External Tools

> Dashboard gotchas, cloud operations details, and external tool notes moved to reference docs:
> - Cloud operations: `docs/cloud-ops-reference.md`
> - Dashboard: Run via `run_dashboard.bat`. Binds to `0.0.0.0:3000`. Edit `dashboard/actions.json` for actions. Restart server after code changes. Costs in GBP (`USD_TO_GBP = 0.79`).
> - **claude-mem 10.0.7**: Chroma runs manually on port 8000. Update when >10.0.7 available.
> - **Anthropic Batch API**: Sonnet may wrap JSON in markdown fences. Strip before `json.loads()`.
> - **Cloud free credits — CRITICAL**: AWS tutorial credits don't cover EC2 Spot. **Feb bill: $805.34 USD.** All cloud spend is real money.

## Claude Code Tooling

**Slash commands**: `/status` (fleet dashboard + game count + running processes), `/selfplay-count` (quick local shard count), `/revise` (update CLAUDE.md), `/preflight` (pre-training verification: S3 deploy diff, code review, fleet/quota/git checks).

**Hooks** (in `.claude/settings.local.json`):
- PreToolUse: Blocks Read/Edit/Write on `.aws_credentials`, `credentials.json`, `.env` files
- PreToolUse: Blocks Bash commands that would unregister/stop TheWatcher Task Scheduler job
- Stop: Reminds to run `/revise` on session close

**Subagents**: `fleet-health` (`~/.claude/agents/fleet-health.md`) — audits AWS/GCP/Azure for running instances and orphaned resources.

**MCP**: context7 configured in `.mcp.json` (project-level) — live docs for PyTorch, Express, Chart.js, cloud CLIs.
**MCP on Windows**: `npx`-based MCP servers need `cmd /c` wrapper to work: `"command": "cmd", "args": ["/c", "npx", "-y", "@pkg"]`. Local MCP servers (github, aws-kb-retrieval, ssh) configured in `.claude.json` under `projects["C:/libraries/PrismataAI"].mcpServers`.

**C++ style**: `.clang-format` at project root (Allman braces, 4-space indent, 120 col limit). Matches existing codebase conventions.

## Session Close-Out

When the user says "wrapping up", "closing context", or "save everything":
1. Check for undocumented results (experiments, tournaments, benchmarks) — if any exist only in conversation, write them to appropriate docs
2. Update any stale plan/results docs with actual outcomes (e.g., mark plans COMPLETE, add results tables)
3. Map any unnamed artifacts to human-readable names (e.g., run timestamps → experiment names)
4. Run `/revise-claude-md` for CLAUDE.md status and gotcha updates
5. List anything still only in conversation context so the user knows what would be lost
6. Save important conversation-only findings to claude-mem (audit results, stale deploy warnings, unfinished work items). Use judgement — no clutter, only items a future session would genuinely benefit from knowing.

## User Preferences

- **Cost-conscious** — AWS bill shock ($805 for 4 days of spot fleet). No cloud safety net. Prefer local compute, minimize cloud spend.
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

Action → Breach (if wipeout) → Confirm → Defense (if enemy has attack) → Swoosh → next player's Action. `m_turnNumber` increments once per **player-turn** (not per round). Frontline kills happen during Action phase via `ASSIGN_FRONTLINE`. **`beginTurn()` runs during Swoosh** (GameState.cpp:1317), NOT at the start of Defense — cards keep their status from the previous Action phase through Defense. Tapped units (Assigned) cannot block; untapped units (Default) can. Do NOT reset statuses before Defense.

**Targeting abilities are two-step**: USE_ABILITY on source card (sets `m_targetAbilityCardClicked` flag in GameState), then SNIPE/CHILL on target (checked by `isTargetAbilityCardClicked()` in `isLegal`). `"disrupt"` in cardLibrary maps to `ActionTypes::CHILL` (CardTypeInfo.cpp:127). 12 units have `targetAction`. After CHILL execution, source card's `canUseAbility()` stays true (no abilityScript), but `hasTarget()` becomes true — must check both to avoid reuse.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval (branching factor 5 from PPPortfolio). **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): resource values ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50. Cost-based material counting — not strategic value.

**Neural net**: ResNet, state_dim=1785, policy+value heads. C++ inference via `NeuralNet::Instance()`. ~2,000 evals/sec/core. Hidden dim AND num_layers are dynamic (read from weight file header) — current best: 256h/3L (R12_smooth90). Can deploy 256h/2L, 256h/3L, or 512h by swapping weight files, no C++ rebuild needed.

**Three HardestAI baselines**: `OriginalHardestAI` (Dave Churchill's original with Legacy components), `HardestAI` (our modified — different opening books, 1 root ability variant), `LiveHardestAI` (exact match to live Prismata SWF — 5 root ability variants, 50-entry unit-specific opening book, Odin in ability filter). Use `LiveHardestAI` when comparing against the actual game. Tournament configs: `LiveHardestAI_Smoke` (2 rounds), `LiveVsOriginal` (1500 rounds).

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

- **All 722K self-play games used buggy C++ engine** — defense-reset bug (fixed Feb 23, commit `d44740e`). Both sides affected equally, internally consistent. Models trained on this data showed inflated WR.
- **Neural policy head weak** — 13.3% accuracy. Computed but unused. PUCT move ordering implemented (`"UsePUCT": true`) but disabled — don't enable until policy accuracy >30%.
- **C++ missing stagnation detection**: AS3 has 4-level progress counter system. C++ only has flat 200-turn limit. See `docs/audit/B5_B6_B7_sellable_stagnation_death.md`.
- **C++ missing death scripts**: `killCardByID` doesn't execute `deathScript`. Units with death effects (Centurion, Valkyrion) behave differently.
- **Replay validation tests legality, not state correctness**: 50.4% pass rate (post-audit). Remaining failures are genuine TS↔C++ semantic differences.
- **Blocking feature mismatch** — C++ uses `CardStatus::Assigned`, Python uses `blocking AND abilityUsed`. Low priority.

## Key Files

> Full file reference (115 entries): `docs/KEY_FILES.md`

| Path | Description |
|---|---|
| `bin/asset/config/config.txt` | AI player definitions, tournament configs |
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (105+11 units, internal codenames) |
| `bin/asset/config/neural_weights.bin` | Neural network weights (deployed) |
| `source/engine/GameState.cpp` | Core game logic |
| `source/ai/NeuralNet.h/cpp` | Neural network inference engine |
| `source/ai/AIParameters.cpp` | AI config JSON parser |
| `source/testing/Tournament.cpp` | Multi-threaded tournament runner |
| `source/testing/TournamentGame.cpp` | Single game runner with self-play data export |
| `training/train.py` | PyTorch training (PrismataNet, `--selfplay-dir`, `--streaming`) |
| `training/load_selfplay.py` | Binary shard loader → numpy arrays |
| `training/export_weights.py` | PyTorch → C++ binary weight format |
| `training/schema.json` | Feature schema contract (state_dim=1785) |
| `js_engine/selfplay_main.js` | JS self-play data generator (AS3→JS transpilation) |
| `tools/prismata_sniffer.py` | *(local only)* TCP proxy for Prismata protocol |
| `tools/prismata_advisor.py` | *(local only)* Neural eval overlay |
| `run_prismata_tools.bat` | *(local only)* Combined launcher — sniffer + advisor + autopilot |
| `aws/watcher.ps1` | TheWatcher — persistent cloud monitor (Task Scheduler) |
| `aws/watcher_config.json` | TheWatcher config (edit to change behavior) |
| `docs/cloud-ops-reference.md` | Cloud provider operational details (AWS/GCP/Azure) |
| `c:\libraries\prismata-replay-parser\` | TS replay parser + database (128K codes) |
| `prismata_decompiled/scripts/mcds/engine/State.as` | AS3 ground truth game state machine (4,490 lines) |

## Documentation Index

> Full documentation index (54 entries): `docs/DOCUMENTATION_INDEX.md`

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full dev history + historical tournament results |
| `docs/plans/2026-02-15-selfplay-training-master-plan.md` | Self-play training execution plan |
| `docs/cloud-ops-reference.md` | Cloud provider gotchas (AWS/GCP/Azure quotas, CLI quirks) |
| `docs/plans/engine-logic-audit-plan-v2.md` | Engine logic audit (COMPLETE — 4 fixes, 22 areas) |
| `docs/plans/2026-02-25-as3-js-transpilation-plan-v2.md` | AS3→JS transpilation plan (COMPLETE) |
| `training/FEATURES.md` | Neural net feature layout specification |
| `docs/WEIGHT_FORMAT.md` | Binary weight format specification |
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference |
| `docs/commentary-knowledge/` | Strategy knowledge for commentator (400+ sources) |
| `docs/prismata-strategy-guide.md` | Comprehensive strategy guide (17 chapters) |

## Tournament Results Summary

**Current (correct engine data):**

| Matchup | Games | Win Rate | Notes |
|---|---|---|---|
| ExpertJS R12 256h/3L vs OriginalHardestAI | — | **6.0%** | First correct-data model, 1.33M examples |

**Baselines (engine-independent):**

| Matchup | Games | Win Rate | Notes |
|---|---|---|---|
| HardestAI vs OriginalHardestAI | 60 | 50.0% | Track A fixes are neutral |
| RandomAI vs MediumAI | 100 | 0% | Baseline floor |
| EasyAI vs MediumAI | 100 | 6% | Baseline |

**Historical (INVALID — trained on buggy C++ engine data, see `docs/PROJECT_HISTORY.md`):**
Models trained on pre-fix engine showed 3.6%→51.9% WR progression but collapsed to ~11% WR after engine fixes. Full table in PROJECT_HISTORY.md.

## Replay API

Replays stored as gzipped JSON on S3: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` (URL-encode `+` → `%2B`, `@` → `%40`).

**Replay search API**: `POST https://prismata-stats.web.app/api/search/replays` (form-encoded: `lower_date`, `upper_date`, `lower_rating`, `replay_rated`). Needs `ssl.CERT_NONE` in Python. `prismata.net` SSL cert expired. 31,506 expert replays fully synced as of Feb 19, 2026 — no new replays missing.

**prismata-stats submit API**: `POST https://prismata-stats.web.app/replays/submit` — form field `codes` (newline-separated). Batches of 50 work fine, processes every 5 min. Used to bulk-submit 4,306 community codes (Feb 20).

**expert_replays.json key format**: Uses capital `Code` (not `code` or `replayCode`). Other fields: `P1Name`, `P2Name`, `P1RatingIni`, `P2RatingIni`, `StartTime`, `Result`, `Deck`.
- **expert_replays.json null Decks**: Some games have `null` Deck field. Always guard: `if not g['deck']: continue` before iterating units in stats scripts.
- **Discord usernames ≠ in-game names**: Players may use different names on Discord (e.g., `_wonderboat` for Wonderboat, `SpyrFyr` for SpiritFryer). Search broadly with partial matching when looking up Discord activity.
- **Shalev rating fields in replay JSON**: `displayRating = shalevU + 350`. `shalevV` = uncertainty (high = inactive/vacation). `score` with TC-index key (e.g. `"23"`) is cumulative XP, not rating. Vacation penalty inflates `shalevV`, not `shalevU`. `peakAdjustedShalevU` tracks all-time peak.

### Replay Code Sources

| Source | Codes | Location |
|---|---|---|
| Per-player V2 (163 players, rated) | ~224,412 | `prismata-replay-parser/*_all_replays_v2.json` |
| Expert (prismata-stats API, 2000+) | ~31,506 | `prismata-replay-parser/expert_replays.json` |
| Reddit /r/prismata | 245 | `prismata-replay-parser/reddit_valid_replays.json` |
| Tournament (Grand Prix + leagues) | 960 | `prismata-replay-parser/tournament_valid_replays.json` |
| Discord (Prismata + League servers) | 3,626 | `prismata-replay-parser/discord_replay_codes_all.json` |
| **Total unique across all sources** | **~170,926** | — |

- **Per-player V2 fetch** (`fetch_player_replays.py` at `c:\libraries\prismata-replay-parser\`): Month-by-month queries with adaptive date-range splitting bypass the 100-per-page API cap. `--rated-only --delay 2` is stable. 163 players fetched (Feb 23, 311 more pending — API down): all 2000+ players, plus partial 1800-1999 and lower tiers via `batch_fetch.py`. V2 records have identical structure to expert_replays.json (same 15 keys, `Code`/`Deck`/`P1Name`/etc.).

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
