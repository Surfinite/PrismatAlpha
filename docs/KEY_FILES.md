# PrismataAI — Complete Key Files Reference

> This is the exhaustive file reference. CLAUDE.md contains only the ~20 most critical files.
> Updated: Feb 28, 2026

## Core Engine & AI

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

## Training Pipeline

| Path | Description |
|---|---|
| `training/train.py` | PyTorch training (PrismataNet, supports `--selfplay-dir`) |
| `training/load_selfplay.py` | Binary shard loader → numpy arrays |
| `training/vectorize.py` | Expert JSONL → PyTorch tensors |
| `training/export_weights.py` | PyTorch → C++ binary weight format |
| `training/schema.json` | Feature schema contract (state_dim=1785) |
| `training/FEATURES.md` | Human-readable feature specification |
| `training/data/unit_index.json` | 161 canonical unit names |
| `training/requirements.txt` | Python deps (torch, numpy, tqdm) with XPU install instructions |
| `training/opening_book.py` | Opening book extraction from expert replays |

## Validation & Analysis Tools

| Path | Description |
|---|---|
| `tools/verify_selfplay.py` | Validates self-play binary output |
| `tools/analyze_tournament.py` | Parse tournament HTML results: Wilson CI, z-test, multi-file aggregation |
| `training/retest_validation.py` | Re-test failed replays against fixed C++ engine with error categorization |
| `training/analyze_mismatches.py` | Aggregate mismatch analysis across failed replay validations |
| `training/convert_replay_for_cpp.py` | Convert TS replay states to C++ validation format (RC#9 cap for snipe_targets) |
| `training/fast_batch_validate.py` | Fast batch validation: in-process conversion + parallel C++ validation (4 workers) |
| `tools/download_wiki.py` | Downloads full Prismata wiki from Fandom API |
| `tools/audit_selfplay_s3.py` | S3 data integrity audit (11 checks: CRC, NaN, outcome consistency, duplicates, win rates) |

## Self-Play & Cloud Infrastructure

| Path | Description |
|---|---|
| `bin/run_selfplay.bat` | Crash-safe self-play launcher (run from Explorer) |
| `.github/workflows/selfplay.yml` | GitHub Actions self-play workflow |
| `aws/launch_selfplay.sh` | EC2 self-play launcher (Windows instances, auto-terminate) |
| `aws/launch_training.sh` | EC2 GPU training launcher (g6.2xlarge, Linux, env var config, trap EXIT auto-terminate) |
| `aws/launch_tournament.sh` | EC2 tournament fleet launcher (supports NUM_INSTANCES, WEIGHTS_KEY, MODEL_LABEL env vars) |
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

## Dashboard

| Path | Description |
|---|---|
| `dashboard/server.js` | Command Center backend (Express + SSE + action system) |
| `dashboard/actions.json` | Action button definitions (tier, command, conflicts) — edit to add new actions |
| `dashboard/public/` | Command Center frontend (HTML + CSS + vanilla JS + Chart.js) |
| `run_dashboard.bat` | One-click dashboard launcher (auto-installs deps, opens browser) |

## Configuration & Tooling

| Path | Description |
|---|---|
| `.clang-format` | C++ code style (Allman, 4-space, 120 col) |
| `.mcp.json` | Project-level MCP server config (context7) |
| `~/.claude/agents/fleet-health.md` | Cloud fleet health audit subagent |

## Replay Parser & Database (at `c:\libraries\prismata-replay-parser\`)

| Path | Description |
|---|---|
| `c:\libraries\prismata-replay-parser\` | TS replay parser + data extraction scripts |
| `c:\libraries\prismata-replay-parser\fetch_player_replays.py` | Per-player month-by-month replay fetcher (v2, adaptive splitting, --rated-only) |
| `c:\libraries\prismata-replay-parser\replays.db` | SQLite replay database (128K codes, 177 MB, rebuild via `build_replay_db.py`) |
| `c:\libraries\prismata-replay-parser\replay_db.py` | DB schema definitions + connection helpers |
| `c:\libraries\prismata-replay-parser\build_replay_db.py` | DB migration + import from all JSON sources |
| `c:\libraries\prismata-replay-parser\replay_queries.py` | Query library (counts, player stats, unit search) |
| `c:\libraries\prismata-replay-parser\replay_cli.py` | CLI: status, count, player, unit, sources, export |
| `c:\libraries\prismata-replay-parser\batch_fetch.py` | Concurrent batch player fetcher (reads player list, skips existing, max-concurrent limiting) |
| `c:\libraries\DiscordChatExporter\` | Discord message export tool (CLI at `cli/`) |
| `c:\libraries\prismata-replay-parser\validate_balance_all.js` | Balance validation across all replay sources |
| `c:\libraries\prismata-replay-parser\balance_passed_codes.json` | 32,973 balance-validated replay codes |

## Prismata Client Tools (Sniffer, Advisor, Autopilot, Commentary)

> **Note:** Sniffer, advisor, and proxy tools are local-only (not tracked in the public repo).
> They contain server infrastructure details. See `.gitignore` for the full exclusion list.

| Path | Description |
|---|---|
| `tools/prismata_sniffer.py` | *(local only)* TCP proxy for Prismata AMF3 protocol |
| `bin/live_game_state.json` | Live game state output from sniffer (written each turn, deleted on GameOver) |
| `tools/prismata_advisor.py` | *(local only)* Python overlay — clipboard monitor + C++ --suggest + tkinter display |
| `run_advisor.bat` | One-click overlay launcher (pre-flight checks for exe + weights) |
| `run_prismata_tools.bat` | *(local only)* Combined launcher — sniffer proxy + advisor overlay + autopilot |
| `tools/prismata_autopilot.py` | AI move injection engine — captures F6 state, runs --suggest, injects clicks via sniffer proxy |
| `bin/prismata_capture_codes.txt` | Sniffer-captured replay codes (TSV: timestamp, code, source). Append-only. |
| `tools/prismata_commentator.py` | Live AI commentator — sniffer events → Claude Haiku → chat injection (Phase 1 working) |
| `tools/prismata_game_state.py` | Shared game state model — TurnRecord, GameContext, GameNarrative with callback registration |
| `tools/generate_postgame_commentary.py` | Two-stage LLM commentary pipeline (Phase 2 analysis + Phase 3 narrative) |
| `tools/prompts/analysis_system.md` | Phase 2 system prompt — structured game analysis |
| `tools/prompts/narrative_system.md` | Phase 3 system prompt — narrative generation with qualitative eval |
| `bin/commentary/` | Generated commentary output (.md files with player names in filename) |
| `tools/commentary_prompt.md` | Condensed Prismata knowledge base for commentary system prompt (~2,400 tokens) |
| `tools/build_unit_knowledge_index.py` | Scans KB markdown → `tools/data/unit_knowledge_index.json` (163 units, 5 concepts, mechanics tags) |
| `tools/commentary_schema.json` | JSON Schema draft-07 for Phase 1 structured output validation |
| `tools/data/unit_knowledge_index.json` | Pre-built unit knowledge lookup (rebuild via `build_unit_knowledge_index.py`) |

## Discord Knowledge Extraction

| Path | Description |
|---|---|
| `tools/discord_knowledge_extractor.py` | Discord knowledge extraction pipeline — 5 phases: `--dry-run`, `--extract`, `--consolidate`, `--preview`, `--integrate` |
| `tools/discord_extraction/` | Working directory for extraction pipeline (chunks, extractions, consolidated JSON, manifest) |
| `docs/commentary-knowledge/discord/` | Discord-sourced strategy insights (7 category files, 1,426 insights) |
| `docs/discord-knowledge-extraction-preview.md` | Human-reviewable preview of extracted Discord insights |
| `docs/discord-replay-codes.json` | 93 replay codes extracted from Discord strategy discussions |
| `tools/discord_extraction/consolidated_mb_insights.json` | Consolidated MB insights JSON (350 MB-specific + 33 bot-related) |

## Stats & Visualization

| Path | Description |
|---|---|
| `tools/spiritfryer_stats.py` | SpiritFryer player stats analysis (expert_replays.json) |
| `tools/wonderboat_stats.py` | Wonderboat/1durbow player stats analysis |
| `tools/flopflop_stats.py` | flopflop player stats analysis |
| `tools/generate_excalidraw.py` | Excalidraw stats dashboard generator (SpiritFryer, v3: Helvetica, W=1350) |
| `tools/wonderboat_excalidraw.py` | Excalidraw stats dashboard generator (Wonderboat) |
| `docs/spiritfryer_stats.excalidraw` | Generated SpiritFryer stats visualization |
| `docs/wonderboat_stats.excalidraw` | Generated Wonderboat stats visualization |

## Hosts & SWF Tools

> **Note:** Hosts file scripts are local-only (not tracked in the public repo).

| Path | Description |
|---|---|
| `tmp_proxy_hosts.ps1` | *(local only)* Set hosts to PROXY mode for sniffer — needs UAC |
| `tmp_restore_hosts.ps1` | *(local only)* Set hosts to DIRECT mode for normal play — needs UAC |

## Decompiled AS3 Source (Ground Truth)

| Path | Description |
|---|---|
| `prismata_decompiled/` | Decompiled Prismata client ActionScript source (Game.as, State.as, UIKeyboard.as) |
| `prismata_decompiled/scripts/mcds/engine/State.as` | AS3 ground truth game state machine (4,490 lines) — phases, moves, blocking, swoosh |
| `prismata_decompiled/scripts/mcds/engine/Inst.as` | AS3 card instance (504 lines) — damageItCanTake, role, blocking, health |
| `prismata_decompiled/scripts/mcds/engine/Card.as` | AS3 card type definition (753 lines) — static properties, scripts |
| `prismata_decompiled/scripts/mcds/engine/StateHelper.as` | AS3 computed properties (649 lines) — blocker eligibility, defense calc, couldDefendThisTurn |
| `prismata_decompiled/scripts/mcds/engine/C.as` | AS3 constants (300 lines) — role/phase/move string constants, resource indices |
| `prismata_decompiled/scripts/mcds/engine/Analyzer.as` | AS3 game analysis (662 lines) — no direct C++ equivalent |
| `tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin` | Live game's full AI parameters (JSON text, extracted from SWF via JPEXS) |
| `tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin` | Live game's short AI parameters (used after turn 16, subset of full) |

## Engine Audit

| Path | Description |
|---|---|
| `docs/audit/` | Engine logic audit findings (B1 script ordering, B2-B4 resources/ability/snipe, B5-B7 sellable/stagnation/death) |
