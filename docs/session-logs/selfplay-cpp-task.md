# Self-Play C++ Implementation — Task Instructions

**Context:** You are implementing the C++ side of self-play data generation. Another context is working on the Python side in parallel. Read `CLAUDE_selfplay_worker_instructions.md` for the full spec — this file is your quick-start.

**Tracking file:** Update `CLAUDE_selfplay_cpp_progress.md` as you work. Create it immediately with a checklist. Another context or the user will check this file for status.

---

## What to do (in order)

### 1. Create your tracking file `CLAUDE_selfplay_cpp_progress.md`
Mark each item as you go: DONE / IN PROGRESS / BLOCKED.

### 2. Phase 0: Gate checks
- Add `OriginalHardestAI_Copy` player config to `config.txt`
- Add `SelfPlayTimingTest` tournament config (25 rounds, 1 thread, SaveReplays:false)
- Build **Release** (`//p:Configuration=Release //p:Platform=x86 //t:Rebuild`)
- Run timing test, record sec/game and turns/game
- Run thread safety test (8 threads, 8 rounds) — no crashes
- Decide: 7s or 1s time limit for generation

### 3. Phase 1: C++ implementation
Create these new files (see `CLAUDE_selfplay_worker_instructions.md` for full code):
- `source/testing/IDataSink.h` — interface (~20 lines)
- `source/testing/SelfPlayDataSink.h` — header (~60 lines)
- `source/testing/SelfPlayDataSink.cpp` — implementation (~250 lines, binary format, CRC32)

Modify these existing files:
- `source/testing/TournamentGame.h` — add `IDataSink*` member + setter
- `source/testing/TournamentGame.cpp` — add `onTurnStart` + `onGameEnd` hooks in `playGame()`
- `source/testing/Tournament.h` — add self-play config members + sink vector
- `source/testing/Tournament.cpp` — parse `SelfPlayDataExport` config, create sinks, wire to games
- `visualstudio/Prismata_Testing.vcxproj` — add new .cpp and .h files
- `bin/asset/config/config.txt` — add player + tournament configs

### 4. Build and smoke test
- Build Debug, verify compiles
- Run `SelfPlay_Smoke` (12 games) — verify .bin files created with correct size
- Check header bytes: magic=0x50534450, version=1, feature_dim=1785

---

## Key gotchas (from the spec)
- `extractFeatures(state, features)` — NO player parameter
- `winner()` returns `Players::Player_None` (3) for draws, NOT -1
- 4 games per round for 2-player tournaments (double loop + color swap)
- Always `//t:Rebuild`, never `//t:Build`
- Cannot rebuild while exe is running (LNK1104)
- Add files to vcxproj or VS won't compile them
- MSBuild from Git Bash: use `//` for switches

## Build commands
```bash
# Release (for gate checks + generation)
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m

# Debug (for development)
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m
```

Run from `bin/` directory: `cd bin && ./Prismata_Testing.exe` (Release) or `./Prismata_Testing_d.exe` (Debug).
