# PrismataAI — Project Instructions

> **Full project history**: `docs/PROJECT_HISTORY.md`
> **Extended reference** (cloud ops, dashboard, sniffer, commentary, full file tables): `docs/CLAUDE_REFERENCE.md`
> **Training plan V1**: `docs/plans/2026-03-06-training-plan-v1.md`
> **Self-play master plan**: `docs/plans/2026-02-15-selfplay-training-master-plan.md`

## Current Status (Mar 7, 2026)

**gui-integration branch.** GUI menu overhaul, debug overlays, matchup runner enhancements (player-switch, WillScore adjudication, `--cards` filtering, parallel workers, replay saving). Base set unit supply fixed in C++ and JS. Needs dependency fix: cards added via `needs` arrays get `supply=0`.

**Neural net weights: ALL GARBAGE.** All committed weights were trained on a broken engine. LiveHardestAI and matchup-runner players use `"Eval":"Playout"`. Retraining deferred until clean engine self-play data is available.

**Self-play data**: ~722K games (7,804 shards, 26.7M records, 178 GB in S3). AWS selfplay DISABLED. GCP selfplay fleet available (6x n2-standard-8). Local: `bin/run_selfplay.bat`.

**Training plan V1** finalized — supervised training on human replays with verification gates V1-V11. Meta-review complete (7 reviews absorbed). Ready for implementation.

**Active work items:**
1. **Training plan V1** — DONE, ready for implementation (`docs/plans/2026-03-06-training-plan-v1.md`)
2. **Retrain with full dataset** — R12_smooth90 architecture, `--streaming` on cloud GPU
3. **Continue data generation** toward 1M games (local selfplay is free)
4. **Mix community replays** into training data (~35K replays, ~1.3M records)

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
- **Static Release config**: If adding new source dirs, check Static Release has matching include paths.
- **CI build uses `/p:PlatformToolset=v143`** (VS 2022) since runners don't have v145.

**Training pipeline:**
```bash
# Generate self-play data (from bin/ directory)
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing.exe

# Train (value-only, current approach):
python training/train.py --selfplay-dir bin/training/data/selfplay/ --value-only --epochs 100 --batch-size 512 --lr 3e-4 --patience 15 --max-records 1000000

# Full (policy + value, once policy accuracy improves):
python training/train.py --selfplay-dir bin/training/data/selfplay/ --epochs 100 --batch-size 512 --lr 3e-4 --patience 15

# Export weights
python training/export_weights.py training/models/best_model.pt bin/asset/config/neural_weights.bin
```

**Matchup runner (JS engine):**
```bash
node js_engine/matchup_clean.js --games 10 --parallel 4 --think-time 3000
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
node extract_training_data.js   # extract from S3 (incremental)
```

## TheWatcher (Persistent Multi-Cloud Monitor)

**NEVER kill, stop, or unregister the `PrismataAI-TheWatcher` Task Scheduler job.** It runs every 5 minutes, manages cloud auto-relaunch and S3 sync. Harmless — only monitors and writes status.

- **Check status**: Read `aws/watcher_status.json`
- **Change behavior**: Edit `aws/watcher_config.json` (e.g., `selfplay.enabled: false`)
- **View log**: Read `aws/watcher_log.txt` (append-only)
- **Boot protection**: Won't auto-launch after PC restart or RAM thrashing (status stale >30 min). Launch instances manually first, then watcher resumes.
- **Watcher hangs under memory pressure**: Recovery: `Stop-ScheduledTask -TaskName 'PrismataAI-TheWatcher'; Start-Sleep 2; Start-ScheduledTask -TaskName 'PrismataAI-TheWatcher'`

| File | Purpose |
|---|---|
| `aws/watcher.ps1` | The script (Task Scheduler) |
| `aws/watcher_config.json` | What to do (AWS, GCP, eval, S3 sync) |
| `aws/watcher_status.json` | Current state |
| `aws/watcher_log.txt` | Append-only log |

## Gotchas & Non-Obvious Patterns

> Cloud provider operational details: `docs/cloud-ops-reference.md`
> Extended gotchas (dashboard, sniffer, commentary, cloud ops): `docs/CLAUDE_REFERENCE.md`

### Engine & Build

- **Internal name system**: Engine uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). Full mapping in `cardLibrary.jso`.
- **AS3↔C++ naming dictionary**: `role`=`CardStatus`, `disruptDamage`=`m_currentChill`, `MOVE_MELEE`=`ASSIGN_FRONTLINE`, `glassBroken`=`Phases::Breach`, `MOVE_ASSIGN`=`USE_ABILITY`, `MOVE_DEFEND`=`ASSIGN_BLOCKER`. Full dictionary in `docs/plans/engine-logic-audit-plan.md`.
- **Two git remotes**: `origin` = davechurchill upstream, `PrismatAlpha` = user's fork. Push to `PrismatAlpha`.
- **Branch can switch unexpectedly**: Always `git branch --show-current` before branch-dependent operations.
- **Config tournament toggles**: Check `"run":true` in `config.txt` before launching.
- **Legacy mode**: `"legacy": true` preserves original AI behavior. Never modify legacy behavior.
- **Feature schema contract**: `training/schema.json` + `training/FEATURES.md`. State dim = 1785 (161 units × 11 + 14 global). Changes must sync across `vectorize.py`, `NeuralNet.cpp`, and `schema.json`.
- **NN weights are garbage — skip in `--suggest` mode**: `main.cpp` skips NN loading when `isSuggestMode` is true. All players use `"Eval":"Playout"`.
- **PRISMATA_ASSERT**: Soft assert — prints to **stdout**, does NOT abort. Use `std::ifstream` instead of `FileUtils::ReadFile` when stdout must stay clean.
- **x86 OOM — 4 threads max per process**: `/LARGEADDRESSAWARE` = 4GB. Use `"Threads": 4` + multiple bat instances. Process dies silently at ~1400 games.
- **Console output routing**: `[SelfPlay]`/`[Progress]` use `fprintf(stderr, ...)`. New Tournament.cpp messages should use stderr.
- **Tournament `tests/` directory required**: `HTMLTable::appendHTMLTableToFile()` crashes if `tests/` doesn't exist.
- **Prismata client architecture**: Adobe AIR/Flash app. Memory reading infeasible — use clipboard or network proxy.
- **Clipboard game state export**: F6 copies JSON to clipboard. Requires SWF dev mode patch. JSON key is `"CurrentInfo"` with `mergedDeck`, `gameState`, `aiParameters`. Card names are **display names**.
- **SWF developer mode patch**: Single byte at decompressed offset `0x1580196`: `0x27`→`0x26`. Requires hosts entry for load balancing bypass.
- **matchup_clean.js auto end-swipe**: Applies to ALL AIs. Without it, stale BREACH swipes block OVERKILL clicks.
- **matchup_clean.js confirm→defense auto-commit**: Auto-inserts commit click when confirm phase has incoming defense clicks.
- **Don't add LiveHardestAI resignation until click verification (V11) is complete**: Early resignation hides click failures.
- **matchup log false positives**: Use `grep -E "[1-9][0-9]* failed"`, not bare keyword grep.
- **Move representation**: `Player::getMove(state, move)` returns `Move` (sequence of `Action`s). BUY resolves via `CardType(action.getID()).getUIName()`.
- **`--suggest` CLI mode**: `Prismata_Testing.exe --suggest state.json [--player PrismatAlpha_AB] [--think-time 3000]`. Output includes `"clicks":[{_type,_id},...]` for wire protocol.
- **mergedDeck buyCost format**: Digits = gold, `G` = green, `B` = blue, `C` = red, `H` = energy.
- **Replay commandList format**: `_type` (NOT `_action`) and `_id`. `clicksPerTurn` slices commandList. `playerInfo` has NO `playerNumber` key — use array index.
- **Click counting ≠ buy counting (CRITICAL)**: `card clicked` does NOT guarantee purchase. Must enforce supply limits.
- **Replay JSON structure**: `deckInfo.mergedDeck` for card data. Derive supply from `rarity`: legendary=1, rare=4, normal=20.
- **C++ `eval_pct` is a string with `%` suffix**: Strip `%` before `float()`.
- **prismata-replay-parser git config**: Must set `git config user.name "Surfinite"` locally before first commit.
- **SQLite trigger DDL splitting**: Never split on `;` — split on `END;` boundary.
- **`build_replay_db.py --source X` wipes the DB**: Always use `--incremental --source` for partial updates.

### Self-Play & Data

- **SkipColorSwap auto-detection**: Self-play auto-detects identical AI configs. `rounds = desired_games`.
- **Self-play crash safety**: Timestamped `run_*` subdirs. Restart anytime — only in-flight games lost.
- **Run self-play from Explorer**: `bin/run_selfplay.bat`. Auto-restarts only if window stays open.
- **Selfplay shard CRC**: Use `validate_crc=False` for live/crashed data.
- **Selfplay positions per game**: ~37 records/game (both players' turns).
- **Selfplay shard binary format**: Header 64 bytes + 4-byte CRC32 footer. Record size = 7152 bytes.
- **Selfplay game counting**: `python -c "import os; base='bin/training/data/selfplay'; total=sum((os.path.getsize(os.path.join(r,f))-68)//7152 for r,_,fs in os.walk(base) for f in fs if f.endswith('.bin') and os.path.getsize(os.path.join(r,f))>68); print(f'{total} records, ~{total//37} games')"`.
- **Self-play uses playout eval**: `SelfPlay_CI` runs `OriginalHardestAI_1s` vs itself. Neural net NOT used for generation. ~4 games/min per 4-thread process.
- **P2 wins 57.3%**: P2 starts with extra Drone. Not a data quality issue — real game asymmetry.
- **PID-based random seeding**: `srand(time ^ PID)` prevents identical sequences.
- **Game_id namespacing**: `load_selfplay.py` offsets by 1M per source dir. Any new code must scope game_ids per-shard.
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
- **Replay balance validation**: 203,602 validated, 154,061 passed, 102,697 training-eligible (rated, 1500+, balance-passed). Re-validate: `reset_for_rarity_revalidation.py` → `validate_db_codes.py` → `build_replay_db.py --incremental`.
- **Revalidation is destructive**: Always backup `replays.db` and `balance_results.json` first.

## Claude Code Tooling

**Slash commands**: `/status` (fleet dashboard), `/selfplay-count` (local shard count), `/revise` (update CLAUDE.md), `/preflight` (pre-training checks).

**Hooks** (`.claude/settings.local.json`):
- PreToolUse: Blocks access to credential files
- PreToolUse: Blocks TheWatcher unregister/stop commands
- Stop: Reminds to run `/revise`

**MCP**: context7 in `.mcp.json`. `npx`-based MCP servers need `cmd /c` wrapper on Windows.

**C++ style**: `.clang-format` (Allman braces, 4-space indent, 120 col limit).

## Session Close-Out

When the user says "wrapping up" or "closing context":
1. Check for undocumented results — write to appropriate docs
2. Update stale plan/results docs with actual outcomes
3. Run `/revise-claude-md` for CLAUDE.md updates
4. List anything only in conversation context
5. Save important findings to claude-mem

## User Preferences

- **Cost-conscious** — AWS bill shock ($805). No safety net. Prefer local compute.
- Efficiency over speed — minimize API credits, maximize local PC
- Comfortable with long-running unattended tasks (hours)
- Git comfort: "noob" — explain clearly, always confirm before push/force
- The user is "Surfinite" everywhere

## Key Architecture

### Engine Internal Name System

Common mappings (full 105-unit table in `cardLibrary.jso`):

| Internal Name | Display Name | | Internal Name | Display Name |
|---|---|---|---|---|
| Tesla Tower | Tarsier | | Brooder | Blastforge |
| Treant | Steelsplitter | | Elephant | Rhino |
| Blood Barrier | Forcefield | | Minicannon | Gauss Cannon |

All script references in `cardLibrary.jso` must use **internal names**, not display names.

### Game Phases & Turn Numbering

Action → Breach (if wipeout) → Confirm → Defense (if enemy has attack) → Swoosh → next player's Action. `m_turnNumber` increments once per **player-turn**. **`beginTurn()` runs during Swoosh** (GameState.cpp:1317), NOT at start of Defense. Tapped units cannot block; untapped can. Do NOT reset statuses before Defense.

**Targeting abilities are two-step**: USE_ABILITY on source (sets `m_targetAbilityCardClicked`), then SNIPE/CHILL on target. `"disrupt"` maps to `ActionTypes::CHILL`. 12 units have `targetAction`.

### AI Architecture

**PartialPlayer** phase decomposition: Defense, ActionAbility, ActionBuy, Breach. **HardestAI** = Stack Alpha-Beta + playout eval. **HardestAIUCT** = UCT/MCTS. Both support Playout, WillScore, and NeuralNet evaluation.

**Will Score** heuristic (`source/ai/Heuristics.cpp`): ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50.

**Three HardestAI baselines**: `OriginalHardestAI` (Churchill's original), `HardestAI` (our modified), `LiveHardestAI` (exact SWF match — 5 ability variants, 50-entry opening book, Odin filter). **Strength: LiveHardestAI < MCDSAI <= MasterBot (Steam).**

### Training Approach

**Phase 1: Supervised** (DONE) — 544K examples, 57.7% val accuracy.
**Phase 2: Self-Play** (ITERATION 1 DONE) — 12K games, 77% val acc, severe overfitting.
**Phase 3: Iterative RL** (future) — AlphaZero-style. Keep 10-20% human data.

### Training Data Inventory

| Dataset | File | Replays | Examples | Min Rating |
|---|---|---|---|---|
| Expert 2000+ | `training_data.jsonl` | ~13,157 | ~251K | 2000 |
| Expert 1500+ | `expert_1500_training_data.jsonl` | 15,010 | 269K | 1500 |
| Community | `community_training_data.jsonl` | 2,468 | 24K | 2000 |

All at `c:\libraries\prismata-replay-parser\`. Balance-validated.

### Hardware

AMD Ryzen 7 5700X3D (8c/16t), 32GB DDR4-3200, Intel Arc B580 (12GB VRAM). Self-play: ~16 games/min (4 instances). Training: XPU `--device xpu --num-workers 4` = ~7 min/epoch (4.5x speedup).

## Known Issues (Current)

- **Neural policy head weak** — 13.3% accuracy. Unused for move ordering.
- **PUCT implemented but disabled** — `"UsePUCT": true` in config. Don't enable until policy >30%.
- **C++ missing stagnation detection**: AS3 has 4-level progress counter. C++ only has flat 200-turn limit.
- **C++ missing death scripts**: `killCardByID` marks dead without running triggers (Centurion, Valkyrion).
- **Replay validation tests legality, not state correctness**: 50.4% pass rate validates action legality only.

## Key Files

| Path | Description |
|---|---|
| `bin/asset/config/config.txt` | AI player definitions, tournament configs |
| `bin/asset/config/cardLibrary.jso` | Master unit definitions (105+11 units) |
| `bin/asset/config/neural_weights.bin` | Neural network weights — **GARBAGE, do not use** |
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
| `source/testing/SelfPlayDataSink.h/cpp` | Binary shard writer |
| `source/gui/GUIState_Play.cpp` | Game play GUI, debug panel |
| `training/train.py` | PyTorch training (PrismataNet) |
| `training/load_selfplay.py` | Binary shard loader → numpy |
| `training/export_weights.py` | PyTorch → C++ binary weights |
| `training/schema.json` | Feature schema (state_dim=1785) |
| `training/FEATURES.md` | Human-readable feature spec |
| `training/data/unit_index.json` | 161 canonical unit names |
| `js_engine/matchup_clean.js` | JS matchup runner (LiveHardestAI vs MCDSAI) |
| `js_engine/matchup_worker.js` | Parallel worker script |
| `js_engine/replay_to_html.js` | Per-game HTML replay viewer generator |
| `js_engine/build_replay_viewer.js` | Self-contained replay viewer builder (15MB HTML) |
| `js_engine/replay_exporter.js` | JS State → C++ GameState JSON converter |
| `js_engine/replay_validator.js` | S3 replay validator (click-by-click) |
| `tools/verify_selfplay.py` | Validates self-play binary output |
| `tools/analyze_tournament.py` | Tournament HTML → Wilson CI, z-test |
| `bin/run_selfplay.bat` | Crash-safe self-play launcher |
| `aws/watcher.ps1` | TheWatcher persistent monitor |
| `.clang-format` | C++ code style |
| `.mcp.json` | MCP server config |

> Full file tables (cloud launchers, sniffer, commentary, replay parser, decompiled sources): `docs/CLAUDE_REFERENCE.md`

## Documentation Index

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full chronological dev history (sections 1-29) |
| `docs/CLAUDE_REFERENCE.md` | Extended reference (cloud, sniffer, commentary, full file tables) |
| `docs/plans/2026-03-06-training-plan-v1.md` | **Training plan V1** — finalized, ready for implementation |
| `docs/plans/META-REVIEW-2026-03-06-training-plan-v1-draft.md` | Training plan meta-review (7 reviews analyzed) |
| `docs/plans/2026-02-15-selfplay-training-master-plan.md` | Self-play training master plan |
| `docs/cloud-ops-reference.md` | Cloud provider operational gotchas |
| `docs/audit/` | Engine logic audit findings |
| `training/FEATURES.md` | Neural net feature layout |
| `docs/WEIGHT_FORMAT.md` | Binary weight format spec |
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference |
| `docs/plans/engine-logic-audit-plan-v2.md` | Engine audit plan (COMPLETE) |
| `docs/commentary-knowledge/` | Strategy knowledge for commentator |
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
