# Self-Play C++ Implementation — Progress Tracker

## Phase 0: Gate Checks
- [x] Add `OriginalHardestAI_Copy` + `OriginalHardestAI_1s` + `OriginalHardestAI_Copy_1s` player configs
- [x] Add `SelfPlayTimingTest` tournament config
- [x] Add `SelfPlay_Smoke` + `SelfPlay_10K` tournament configs
- [x] Build **Release** — 0 warnings, 0 errors (49.1s)
- [x] Run timing test — **30.3 sec/game** (20 games, 1 thread, 1s time limit, Release), ~36 turns/game avg
- [x] Run thread safety test (8 threads, 32 games, with data export) — **PASS**, no crashes, 1,216 records, all 8 CRCs valid, game_ids 0-31 unique+sequential
- [x] DECISION: **1s time limit** — 30s/game wall clock. 10K games ≈ 10.4 hrs at 8 threads, ≈ 5.2 hrs at 16 threads.

## Phase 1: C++ Implementation
- [x] Create `source/testing/IDataSink.h` — virtual interface (onTurnStart, onGameEnd, finalize)
- [x] Create `source/testing/SelfPlayDataSink.h` — SelfPlayRecord struct + SelfPlayDataSink class
- [x] Create `source/testing/SelfPlayDataSink.cpp` — binary shard writer, CRC32 (computed table), per-game flush, shard rotation at 1 GB, JSONL metadata, progress logging every 100 games
- [x] Modify `source/testing/TournamentGame.h` — added IDataSink* member + setDataSink()
- [x] Modify `source/testing/TournamentGame.cpp` — onTurnStart before playNextTurn(), onGameEnd after game loop
- [x] Modify `source/testing/Tournament.h` — self-play config members, changed playRound signature
- [x] Modify `source/testing/Tournament.cpp` — parse SelfPlayDataExport JSON, create per-thread sinks, wire to games, finalize after all rounds
- [x] Add new files to `visualstudio/Prismata_Testing.vcxproj`
- [x] Add configs to `bin/asset/config/config.txt`
- [x] Build **Debug** — 0 warnings, 0 errors (24.6s)
- [x] Build **Release** — 0 warnings, 0 errors (49.1s)

## Phase 2: Verification
- [x] V1: Smoke test (12 games, 1 thread, Debug) — 380 records, file size exact (2,717,828 = 64 + 380×7152 + 4), header correct (magic=0x50534450, version=1, feature_dim=1785, record_size=7152), CRC32 match (0x86C5FF15), 12 sequential game_ids, outcomes only {-1.0, +1.0}, ~79.3 non-zero features/record avg
- [x] V1b: Thread safety test (32 games, 8 threads, Release, with export) — 1,216 records across 8 shards, all CRCs valid, game_ids 0-31 unique, 30-53 turns/game (avg 38), no NaN/Inf
- [x] V2: Python loader validates CRC, records parse correctly — `load_selfplay.py` already existed. Loaded smoke (380 records) + threadtest (1,216 records across 8 shards). All CRCs validated, numpy structured array parsed correctly.
- [x] V3: Outcome labels correct — Cross-checked all 1,216 records against JSONL metadata: 0 errors. Signs match player_index vs winner for every record.
- [x] V4: Feature spot-check — 62-93 non-zero features/record (reasonable, grows during game). No NaN/Inf. Outcome consistency OK across all 32 games.
- [x] V5: Overfit test — Trained 200 epochs on threadtest data (32 games, 1,216 records). Val accuracy 100% by epoch 6, val loss 0.0085. Train accuracy 98.1%. Prediction range [-0.75, +0.74]. Full end-to-end pipeline confirmed working: C++ binary → Python loader → PyTorch training.

## Verification tool
- `tools/verify_selfplay.py` — created during thread safety test, validates binary format, CRC, game_id uniqueness, record structure

## Test output locations
- Smoke test: `bin/training/data/selfplay_smoke/` (selfplay_t00_s000.bin + .jsonl)
- Thread test: `bin/training/data/selfplay_threadtest/` (8 shards: selfplay_t00..t07_s000.bin + .jsonl)

## Config entries added
- Players: `OriginalHardestAI_Copy`, `OriginalHardestAI_1s`, `OriginalHardestAI_Copy_1s`
- Tournaments (all `run:false`): `SelfPlayTimingTest`, `ThreadSafetyTest`, `SelfPlay_Smoke`, `SelfPlay_10K`

## Notes
- Started: Feb 13, 2026
- CRC32 table: initially hardcoded with duplicate entries in second half — replaced with computed `initCRC32Table()` approach
- Header magic reads as 0x50445350 ("PDSP") due to little-endian byte order of 0x50534450
- BlendQuick_10 and BlendQuick_05 tournaments were found `run:true` from previous session — disabled during gate checks
