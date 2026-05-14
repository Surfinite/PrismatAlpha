# PrismatAlpha — Project Instructions

> **Full project history**: `docs/PROJECT_HISTORY.md`
> **Extended reference** (cloud ops, dashboard, sniffer, commentary, full file tables): `docs/CLAUDE_REFERENCE.md`
> **Training plan V1**: `docs/plans/2026-03-06-training-plan-v1.md`
> **Self-play master plan**: `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (May 11, 2026)

**Repo renamed `PrismatAI → PrismatAlpha`** (May 5–9). GitHub at github.com/Surfinite/PrismatAlpha. Local filesystem path unchanged (`c:\libraries\PrismataAI\`).

**prismata.live LIVE.** Split architecture (data box + site box, S3-synced every 60s). Active maintenance and live-spectating work is tracked in the prismata-ladder workspace — related but separate repo.

**DeepSets models exported.** MB-only: 82.4% val acc, Human-only: 78.2%, Mixed: 82.2%. Five DSNN players configured. Results doc: `docs/deepsets-training-results.md`.

**Parity gap quantified.** Mar 17 single-unit sweep (105 units × 4 games): LiveHardestAIUCT wins ~20% vs STEAMAI, 60% of units lose 0/4. Closing this is now a prerequisite to DSNN tournament strength.

**DeadGameBot live** — Plays casual games on the Prismata server using the SteamAI bridge. First live replay Mar 31. State-tracker work ongoing.

**Active work items:**
1. **Engine parity** — narrow `LiveHardestAIUCT` ↔ `STEAMAI` gap (heuristic weights, ability filters, partial-player ordering)
2. **DeadGameBot state-tracker** — divergence after MB turns (no clicks sent)

## What This Project Is

A C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The engine simulates game states, the AI uses Alpha-Beta search, UCT/MCTS, and a PartialPlayer phase decomposition system (Defense, ActionAbility, ActionBuy, Breach).

## User Preferences

- **Cost-conscious** — prefer local compute, minimize cloud spend
- Git comfort: "noob" — explain clearly, always confirm before push/force
- The user is "Surfinite" everywhere

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
- **Static Release config**: If adding new source dirs, check Static Release has matching include paths.
- **CI build uses `/p:PlatformToolset=v143`** (VS 2022) since runners don't have v145.

**Legacy PrismataNet pipeline:** Superseded by DeepSets. See `training/train.py --help` and `training/export_weights.py` if needed.

**Matchup runner (JS engine):**
```bash
node js_engine/matchup_clean.js --games 10 --parallel 4 --think-time 3000
node js_engine/matchup_clean.js --player SteamAI --steam-difficulty HardestAI --games 10
node js_engine/matchup_clean.js --player-white DSNN_MBonly --player-black SteamAI --steam-difficulty HardestAI --games 2048 --parallel 8 --player-switch --think-time 7000 --save-replays DSNN_MBonlyVsMB
```

**Replay viewers:**
```bash
# Per-game HTML from matchup replay JSON:
node js_engine/replay_to_html.js bin/asset/replays/.../game_0001.json

# Build self-contained viewer (15MB HTML, all card art embedded):
node js_engine/build_replay_viewer.js [output.html]
# Output: bin/prismata_replay_viewer.html — drag-drop .json.gz or enter replay code
```

**Expert replay pipeline** (at `c:\libraries\prismata-replay-parser\`):
```bash
node fetch_expert_replays.js    # fetch from API (incremental)
node filter_expert_replays.js   # filter (instant)
node extract_training_data.js   # extract from S3 (incremental, legacy)
```

**Training pipeline (current — DeepSets):**
```bash
# 1. Extract: local .json.gz → V1 JSONL (all turns, both players)
#    102,697 eligible replays in replays_archive/ (both 1500+, balance-passed)
cd c:/libraries/prismata-replay-parser
node extract_training_data.js \
    --codes eligible_1500_codes.txt \
    --output human_1500_all.jsonl \
    --local-dir replays_archive

# 2. Convert: V1 JSONL → V2 JSONL (DeepSets instance format)
cd c:/libraries/PrismataAI
python training/convert_human_to_v2.py \
    --input c:/libraries/prismata-replay-parser/human_1500_all.jsonl \
    --output training/data/human_1500_v2.jsonl

# 3. Vectorize: V2 JSONL → HDF5 (padded tensors for training)
python training/vectorize_v2.py \
    --input training/data/human_1500_v2.jsonl \
    --output training/data/human_1500_v2.h5

# 4. Train DeepSets model
python training/train.py training/data training/models/deepsets_human \
    --model deepsets --streaming --epochs 100 --batch-size 512 --lr 3e-4 --patience 15

# 5. Export weights (DSN2 binary format for C++ inference)
python training/export_weights_v2.py \
    training/models/deepsets_human/best_model.pt \
    bin/asset/config/neural_weights.bin
```

## Gotchas & Non-Obvious Patterns

> Cloud provider operational details: `docs/cloud-ops-reference.md`
> Extended gotchas (dashboard, sniffer, commentary, cloud ops): `docs/CLAUDE_REFERENCE.md`

### Engine & Build

- **Internal name system**: Engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full mapping in `cardLibrary.jso`.
- **AS3↔C++ naming dictionary**: `role`=`CardStatus`, `disruptDamage`=`m_currentChill`, `MOVE_MELEE`=`ASSIGN_FRONTLINE`, `glassBroken`=breach flag (not a phase — no `Phases::Breach` equivalent in JS), `MOVE_ASSIGN`=`USE_ABILITY`, `MOVE_DEFEND`=`ASSIGN_BLOCKER`. Full dictionary in `docs/plans/engine-logic-audit-plan.md`.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork. Push to `PrismatAlpha`.
- **Branch can switch unexpectedly**: Always `git branch --show-current` before branch-dependent operations.
- **Config tournament toggles**: Check `"run":true` in `config.txt` before launching.
- **Feature schema contract (DeepSets, current)**: `training/schema_v2.json` + `training/property_table.json`. Per-instance tokens (32 embed + 13 static + 10 instance state = 55-dim). Changes must sync across `vectorize_v2.py`, `model_deepsets.py`, `NeuralNet.cpp`, and `schema_v2.json`.
- **Legacy flat schema (PrismataNet)**: `training/schema.json` + `training/FEATURES.md`, state_dim=1785. Kept for the value-only baseline; not the current path.
- **Per-player NN weights**: Players with `"WeightsFile":"neural_weights_X.bin"` in config.txt auto-load their weights in `--suggest` mode. `--weights <path>` CLI arg overrides. Weight files live in `bin/asset/config/`.
- **DSNN players**: `DSNN_MBonly` (ep98, 82.4%), `DSNN_MBonly_SWA` (SWA avg), `DSNN_Human` (ep26, 78.2%). All use UCT + NeuralNet eval + LiveHardestAI opening book.
- **NeuralNet singleton**: All NN eval goes through `NeuralNet::Instance()`. Can't pit two NN players in same C++ process. For matchup_clean.js this is fine (fresh process per turn).
- **PRISMATA_ASSERT**: Soft assert — prints to **stdout**, does NOT abort. Use `std::ifstream` instead of `FileUtils::ReadFile` when stdout must stay clean.
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` = 4GB. Use `"Threads": 4` + multiple bat instances. Process dies silently at ~1400 games.
- **Console output routing**: `[SelfPlay]`/`[Progress]` use `fprintf(stderr, ...)`. New Tournament.cpp messages should use stderr.
- **Tournament `tests/` directory required**: `HTMLTable::appendHTMLTableToFile()` crashes if `tests/` doesn't exist.
- **Prismata client architecture**: Adobe AIR/Flash app. Memory reading infeasible — use clipboard or network proxy.
- **Clipboard game state export**: F6 copies JSON to clipboard. Requires SWF dev mode patch. JSON key is `"CurrentInfo"` with `mergedDeck`, `gameState`, `aiParameters`. Card names are **display names**.
- **SWF developer mode patch**: Single byte at decompressed offset `0x1580196`: `0x27`→`0x26`. Requires hosts entry for load balancing bypass.
- **matchup_clean.js auto end-swipe**: Applies to ALL AIs. Without it, stale BREACH swipes block OVERKILL clicks.
- **matchup_clean.js confirm→defense auto-commit**: Auto-inserts commit click when confirm phase has incoming defense clicks.
- **SteamAI is one-shot**: `PrismataAI.exe` exits after each response. Must spawn fresh process per turn. EPIPE if you reuse stdin.
- **SteamAI protocol differs from MCDSAI**: SteamAI gets ALL 4 fields every turn (mergedDeck, gameState, aiParameters, aiPlayerName). MCDSAI only gets gameState + aiPlayerName per turn.
- **Don't add LiveHardestAI resignation until click verification (V11) is complete**: Early resignation hides click failures.
- **matchup log false positives**: Use `grep -E "[1-9][0-9]* failed"`, not bare keyword grep.
- **Move representation**: `Player::getMove(state, move)` returns `Move` (sequence of `Action`s). BUY resolves via `CardType(action.getID()).getUIName()`.
- **`--suggest` CLI mode**: `Prismata_Testing.exe --suggest state.json [--player PrismatAlpha_AB] [--think-time 3000] [--weights path/to/weights.bin]`. Output includes `"clicks":[{_type,_id},...]` for wire protocol. If `--weights` is omitted, uses the player's `WeightsFile` from config.txt.
- **mergedDeck buyCost format**: Digits = gold, `G` = green, `B` = blue, `C` = red, `H` = energy.
- **Replay commandList format**: `_type` (NOT `_action`) and `_id`. `clicksPerTurn` slices commandList. `playerInfo` has NO `playerNumber` key — use array index.
- **Click counting ≠ buy counting (CRITICAL)**: `card clicked` does NOT guarantee purchase. Must enforce supply limits.
- **Replay JSON structure**: `deckInfo.mergedDeck` for card data. Derive supply from `rarity`: legendary=1, rare=4, normal=10, trinket=20.
- **C++ `eval_pct` is a string with `%` suffix**: Strip `%` before `float()`.
- **prismata-replay-parser git config**: Must set `git config user.name "Surfinite"` locally before first commit.
- **SQLite trigger DDL splitting**: Never split on `;` — split on `END;` boundary.
- **`build_replay_db.py --source X` wipes the DB**: Always use `--incremental --source` for partial updates.

### Live Spectating (<ladder> repo)

- **Prismata server sends `Moved` during login**: Load-balancing redirect. `login()` must handle it or auth times out silently. Fixed in `headless_client.py`.
- **React `useState` drops rapid WebSocket messages**: Batching means only the last message survives per render. Use queue-based hook (`useWebSocket.ts`) with `drainMessages()`.
- **Late-joiner cache race condition**: Server adds client to subscribers before sending cached history. Live clicks can interleave with cache replay. Fixed with seq-based dedup on client.
- **`npx next build` needs `--webpack`**: Next.js 16 defaults to Turbopack which fails with webpack config.
- **VPS spectator files must be in repo**: `ws_broadcast.py`, `spectator_bridge.py` were VPS-only and got lost on deploy. Now tracked in git.
- **`prismata_amf3.py` is the canonical module name**: Renamed from `prismata_sniffer.py`. Deploy script and all imports updated.
- **S3 replay URL must be HTTPS**: `https://saved-games-alpha.s3.amazonaws.com/` (not `s3-website`). HTTP causes mixed content block on HTTPS sites.
- **VPS deployment gotchas**: See memory file `project_prismata_live_infrastructure.md` for deploy script, credentials path, python symlink, disk constraints, and deploy key details.
- **AWS default region is `eu-north-1`**: prismata.live infra is in `us-east-1`. Always pass `--region us-east-1`.
- **ARM Ubuntu 24.04 has no `python` command**: Only `python3`. Subprocess calls to `python` fail silently. Data box has `/usr/bin/python` symlink.
- **SSH to data box**: `ssh -i ~/.ssh/<SSH_KEY>.pem -o ProxyCommand="ssh -i ~/.ssh/<SSH_KEY>.pem -W %h:%p ubuntu@<SITE_EIP>" ubuntu@<DATA_BOX_PRIVATE_IP>`
- **Client7 is PrismataLiveBot**: Replaced SpectatorBot3. Login fails if the account is already logged in elsewhere (Prismata allows only one session). Running several spectator bots.
- **S3 export prefix is `exports/`**: Not `site-data/`. Data box uploads here, site box syncs from here.
- **`headless_multi.py` has no `--quiet` flag**: Only `--add-account`. Don't add unknown flags to systemd ExecStart.

### Self-Play & Data

- **SkipColorSwap auto-detection**: Self-play auto-detects identical AI configs. `rounds = desired_games`.
- **Self-play crash safety**: Timestamped `run_*` subdirs. Restart anytime — only in-flight games lost.
- **Selfplay shard CRC**: Use `validate_crc=False` for live/crashed data.
- **Selfplay positions per game**: ~37 records/game (both players' turns).
- **Selfplay shard binary format**: Header 64 bytes + 4-byte CRC32 footer. Record size = 7152 bytes.
- **Selfplay game counting**: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-68)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>68); print(f'{total} records, ~{total//37} games')"`.
- **Self-play uses playout eval**: `SelfPlay_CI` runs `OriginalHardestAI_1s` vs itself. Neural net NOT used for generation. ~4 games/min per 4-thread process.
- **P2 wins ~57% in current AI matchups**: Real observed asymmetry, not a data quality issue. The *cause* isn't fully settled — the extra Drone is compensation for going second, not an advantage in itself. Community view is it may equalise under strong-enough AI.
- **PID-based random seeding**: `srand(time ^ PID)` prevents identical sequences.
- **Value-only model export**: `export_weights.py` exports zero-initialized policy tensors. C++ requires all 26 tensors.

### Training

- **Quick training tests**: Use `--selfplay-dir bin/training/data/selfplay/2026-02-15_11-31-33/` (4 shards, instant).
- **Training CRC**: `train.py` uses `validate_crc=False`.
- **Training RAM limit**: Full dataset = ~50GB+. Use `--streaming` (memory-mapped) or `--max-records 1000000` (32GB).
- **Training RAM: max 2 concurrent jobs** on 32GB.
- **best_model.pt gets overwritten**: Copy to unique filename immediately after run.
- **Training lock file**: `training.lock` in model dir. Auto-cleaned on exit.
- **C++ NeuralNet hidden_dim AND num_layers are dynamic**: Read from weight file header. No C++ rebuild needed.
- **Tournament output needs `2>&1`**: stderr routing.
- **Parallel tournament eval**: Separate `bin_eval_X/` directories.
- **train.py positional args**: `data_dir` then `model_dir`. Must pass both for custom output.
- **XPU training**: `--device xpu --num-workers 4`. 3.2x speedup. BF16 adds overhead — skip.
- **Streaming num_workers=2 on 32GB RAM**: `--num-workers 4` causes 94% RAM, system unusable.
- **Cloud GPU RAM (16GB)**: Must use `--streaming`. g2-standard-8 (32GB) for full dataset. g2-standard-4 OOM-kills.
- **D: drive backup**: `D:\PrismataAI_backup\` has selfplay data, models, weights.
- **Replay `result` field is 1-indexed**: `result=0` = P1 (first player) wins, `result=1` = P2 wins, `result=2` = draw. Training uses 0-indexed: `outcome_p0 = 1.0 - float(result)`, draws → 0.5. Verify P0 win rate <50%.
- **Labels must be in [0,1] for BCE**: Out-of-range labels (e.g. draw=2) cause loss explosion. Validate before training.
- **TF32 disabled for CUDA training**: `train.py` sets `torch.backends.cuda.matmul.allow_tf32 = False` — safety net for small models on Ampere+ GPUs.
- **GCP spot L4 unreliable**: Frequent preemption and stockouts. AWS eu-north-1 spot (g6.2xlarge) more stable for long runs.

### Windows & Python Environment

- **`nohup &` broken in Git Bash**: Use `run_in_background` parameter or persistent PowerShell.
- **Python stdout buffering**: Use `PYTHONUNBUFFERED=1`.
- **Python cp1252**: Use `PYTHONIOENCODING=utf-8` or ASCII.
- **`python3` not available**: Use `python` on Windows.
- **`gcloud` only in Git Bash**: Use full path `C:/google-cloud-sdk/bin/gcloud.cmd` with `shell=True` for subprocess.
- **PowerShell JSON BOM**: Use `encoding='utf-8-sig'` in Python.
- **Git Bash mangles `$_`**: Write `.ps1` script files instead of inline PowerShell.
- **Env vars unreliable in bash scripts**: Use `python -c "import subprocess, os; ..."` workaround.
- **Hosts file editing**: Use `[System.IO.File]::WriteAllText()`, never `Set-Content`. Needs UAC.

### Historical / Concluded

- **Blend tournaments**: Neural component hurts. Don't revisit until model >60% val accuracy.
- **Batch validation**: 50.4% pass (1,072/2,127). Remaining failures are genuine TS↔C++ differences.
- **Replay balance validation**: 102,697 training-eligible replays in `replays_archive/`. Full query and re-validation steps in `docs/CLAUDE_REFERENCE.md`.
- **Revalidation is destructive**: Always backup `replays.db` and `balance_results.json` first.

## Claude Code Tooling

**Slash commands**: `/revise-claude-md` (capture session learnings into CLAUDE.md), `/claude-md-improver` (periodic CLAUDE.md audit). Older `/status`, `/selfplay-count`, `/preflight` exist but are stale — don't trust their output without verifying.

**Hooks** (`.claude/settings.local.json`):
- PreToolUse: Blocks access to credential files
- Stop: Reminds to run `/revise`

**MCP**: context7 in `.mcp.json`. `npx`-based MCP servers need `cmd /c` wrapper on Windows.

**C++ style**: `.clang-format` (Allman braces, 4-space indent, 120 col limit).

## Claude Code Behavior

**Session close-out** — when the user says "wrapping up" or "closing context":
1. Check for undocumented results — write to appropriate docs
2. Update stale plan/results docs with actual outcomes
3. Run `/revise-claude-md` for CLAUDE.md updates
4. List anything only in conversation context
5. Save important findings to claude-mem

## Key Architecture

### Engine Internal Name System

Engine uses codenames internally (e.g., "Tesla Tower" = Tarsier). Full mapping in `cardLibrary.jso` (105 competitive + 11 base = 116 units; canonical names in `training/data/unit_index.json`). All script references must use **internal names**, not display names.

### Game Phases & Turn Numbering

From the **player's experience**: Defense (assign blockers for incoming attack) → Breach if wipeout (opponent clicks through undefended units) → Swoosh → Action → Confirm → back to Defense or Swoosh.

From the **engine's internal sequence**: a player's `MOVE_COMMIT` (end of action) triggers the *opponent's* Defense phase, then Swoosh, then the opponent's Action. JS engine has 3 explicit phases: `PHASE_DEFENSE`, `PHASE_ACTION`, `PHASE_CONFIRM`. There is **no `PHASE_BREACH`** — breach is the `glassBroken` flag resolved within the defense/swoosh transition. The old CLAUDE.md sequence "Action → Breach → Confirm → Defense → Swoosh" described engine ownership order but read as the wrong player-turn sequence.

`m_turnNumber` increments once per **player-turn**. **`beginTurn()` runs during Swoosh** (GameState.cpp:1317), NOT at start of Defense. Tapped units cannot block; untapped can. Do NOT reset statuses before Defense.

**Targeting abilities are two-step**: USE_ABILITY on source (sets `m_targetAbilityCardClicked`), then SNIPE/CHILL on target. `"disrupt"` maps to `ActionTypes::CHILL`. 12 units have `targetAction`.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval. **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50.

**Three HardestAI baselines**: `OriginalHardestAI` (Churchill's original), `HardestAI` (our modified), `LiveHardestAI` (exact SWF match — 5 ability variants, 50-entry opening book, Odin filter). 
`HardestAI` should be exactly equivalent to `OriginalHardestAI` at default configurations.
**Strength: LiveHardestAI < MCDSAI <= SteamAI ≈ MasterBot (Steam).** Quantified gap: ~20% WR overall in single-unit matchups (60% of units at 0/4). Full data: `docs/deepsets-training-results.md`.

### Training Data Inventory

| Dataset | File | Replays | Examples | Min Rating |
|---|---|---|---|---|
| Human HDF5 | `training/data/human_1500_no6s_v2.h5` | 97,317 | 2.49M | 1500 |
| MB Fleet v3 | `training/data/fleet_v3.h5` | ~160K | 5.9M | — (self-play) |
| MB Fleet v4 | `training/data/fleet_v4.h5` | ~160K | 5.9M | — (self-play) |
| MB Local | `training/data/local_mbvmb.h5` | ~11K | 414K | — (self-play, val set) |

HDF5 files at `training/data/`. JSONL files at `c:\libraries\prismata-replay-parser\`. Only use balance-validated.

### Hardware

AMD Ryzen 7 5700X3D (8c/16t), 32GB DDR4-3200, Intel Arc B580 (12GB VRAM). Self-play: ~16 games/min (4 instances). Training: XPU `--device xpu --num-workers 4` = ~7 min/epoch (4.5x speedup).

## Known Issues (Current)

- **PUCT implemented but disabled** — `"UsePUCT": true` in config. Don't enable until policy >30%.
- **C++ missing stagnation detection**: AS3 has 4-level progress counter. C++ only has flat 200-turn limit.
- **Neural policy head weak** — 13.3% accuracy (unverified). Unused for move ordering.
- **C++ `killCardByID` may have cleanup bugs** (unverified): Prismata has no on-death triggers — actual bug unknown.
- **Replay validation tests legality, not state correctness** (unverified): 50.4% pass rate.

## Key Files

| Path | Description |
|---|---|
| `bin/asset/config/config.txt` | AI player definitions, tournament configs |
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (105+11 units) |
| `bin/asset/config/neural_weights_*.bin` | Per-player NN weights (mbonly, human, mbonly_swa) |
| `source/ai/NeuralNet.h/cpp` | Neural network inference engine |
| `source/ai/UCTSearch.cpp` | UCT/MCTS search |
| `source/ai/StackAlphaBetaSearch.cpp` | Stack Alpha-Beta search |
| `source/ai/Eval.cpp` | Evaluation functions (WillScore, Playout, NeuralNet) |
| `source/ai/Heuristics.cpp` | Will Score evaluation and resource values |
| `source/ai/AIParameters.cpp` | AI config JSON parser |
| `source/engine/GameState.cpp` | Core game logic |
| `source/engine/Constants.h` | Game constants, EvaluationMethods enum |
| `source/testing/Tournament.cpp` | Multi-threaded tournament runner |
| `source/testing/TournamentGame.cpp` | Single game runner with self-play export |
| `source/gui/GUIState_Play.cpp` | Game play GUI, debug panel |
| `training/train.py` | PyTorch training (`--model deepsets` or legacy PrismataNet) |
| `training/export_weights.py` | PyTorch → C++ binary weights (legacy format) |
| `training/export_weights_v2.py` | PyTorch → DSN2 binary weights (current DeepSets format) |
| `training/schema_v2.json` | DeepSets per-instance feature schema (current) |
| `training/property_table.json` | Static per-unit properties (DeepSets) |
| `training/schema.json` + `training/FEATURES.md` | Legacy flat PrismataNet schema (state_dim=1785) |
| `training/data/unit_index.json` | 116 canonical unit names |
| `js_engine/matchup_clean.js` | JS matchup runner (LiveHardestAI, MCDSAI, SteamAI) |
| `js_engine/matchup_worker.js` | Parallel worker script |
| `js_engine/steam_ai.js` | SteamAI wrapper for Steam's PrismataAI.exe (one-shot process) |
| `js_engine/replay_to_html.js` | Per-game HTML replay viewer generator |
| `js_engine/build_replay_viewer.js` | Self-contained replay viewer builder (15MB HTML) |
| `js_engine/replay_exporter.js` | JS State → C++ GameState JSON converter |
| `js_engine/replay_validator.js` | S3 replay validator (click-by-click) |
| `gcp/launch_human_training.sh` | GCP human-only DeepSets training launcher |
| `aws/launch_deepsets_training.sh` | AWS mixed MB+Human DeepSets training |
| `.clang-format` | C++ code style |
| `.mcp.json` | MCP server config |

> <ladder> repo files: see `<LADDER_REPO_PATH>\` directly. Full file tables: `docs/CLAUDE_REFERENCE.md`

## Documentation Index

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full chronological dev history (sections 1-29) |
| `docs/deepsets-training-results.md` | DeepSets training results + parity-gap finding (May 2026) |
| `docs/CLAUDE_REFERENCE.md` | Extended reference (cloud, sniffer, commentary, full file tables) |
| `docs/plans/2026-03-09-training-plan-v3-READY-v3.md` | Training plan v3 (finalized) |
| `docs/plans/2026-02-15-selfplay-training-master-plan.md` | Self-play training master plan |
| `docs/cloud-ops-reference.md` | Cloud provider operational gotchas |
| `training/FEATURES.md` | Neural net feature layout |
| `docs/WEIGHT_FORMAT.md` | Binary weight format spec |
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference |
| `docs/prismata-strategy-guide.md` | Comprehensive strategy guide |

## Replay API

Replays: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` (URL-encode `+`→`%2B`, `@`→`%40`).

Search: `POST https://prismata-stats.web.app/api/search/replays` (needs `ssl.CERT_NONE`). Submit: `POST .../replays/submit` (field `codes`, newline-separated, batches of 50).

**Key format**: `expert_replays.json` uses capital `Code`. Null Decks possible — guard before iterating.

> Full replay API details, code sources, Discord export: `docs/CLAUDE_REFERENCE.md`

## Third-Party Credits

| Dependency | License | Description |
|---|---|---|
| **PrismataAI** (base) | CC BY-NC-SA 2.5 CA | Engine and AI by David Churchill / Lunarch Studios |
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
| prismata-stats | https://gitlab.com/prismata-stats/v3/-/tree/dev |
