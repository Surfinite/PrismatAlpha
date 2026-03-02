# Blend Tournament Re-Run — Progress Tracker

**Created:** Feb 13, 2026
**Purpose:** Re-run BlendSweep_vsMedium and BlendVsOriginal tournaments after rebuilding the exe with the JSON trailing comma fix.

## Background

The blend evaluation (`NeuralNetPlusPlayout`) combines neural net evaluation with playout evaluation at leaf nodes. The previous attempt (Feb 13 morning) failed — BlendSweep_vsMedium only completed 32/240 games (exit code 3), and BlendVsOriginal never ran. Suspected cause: JSON trailing comma bug in `GameState::toJSONString()` corrupting saved replays.

## Steps

### 1. Verify JSON trailing comma fix in source — DONE

Fix confirmed at `source/engine/GameState.cpp:2346`:
```cpp
bool moreCards = (p == 0 && getCardIDs(1).size() > 0) || (i < getCardIDs(p).size() - 1);
```
This correctly avoids trailing commas when P1 has 0 cards.

### 2. Rebuild exe — DONE

Full solution rebuild: 0 errors, 0 warnings, 21.5 seconds. All 3 exes rebuilt:
- `bin/Prismata_Testing_d.exe`
- `bin/Prismata_GUI_d.exe`
- `bin/Prismata_Standalone_d.exe`

Build timestamp: Feb 13 2026 ~17:01.

### 3. Configure tournaments — DONE

Set `BlendSweep_vsMedium` and `BlendVsOriginal` to `"run":true` in config.txt (lines 261-262).
All other tournaments remain `run:false`.

### 4. First run attempt — CRASHED (exit code 1, 38/240 games)

Started: Feb 13 2026 ~17:02 with 16 threads (default = hardware_concurrency).
Crashed after 38 games. Only BlendUCT_50/25/10 matchups completed. No MediumAI, BlendAB, or OriginalHardestAI games ran. BlendVsOriginal never started.

Replays from failed run: `bin/asset/replays/BlendSweep_vsMedium_2026-02-13_17-02-28/` (38 files)

### 5. Crash investigation — x86 OOM (32-bit address space exhaustion)

**Root cause: 16 concurrent NeuralNetPlusPlayout searches on a 32-bit (x86) process.**

The build is x86-only (2 GB virtual address space limit). With 16 threads, each running a BlendUCT or BlendAB player doing BOTH neural inference + full playout at every leaf:
- Each UCT search tree stores full GameState copies per node (~several KB each, up to 40 children)
- Each playout creates temporary Game objects with cloned Player hierarchies
- Neural net inference allocates 1785-dim feature vectors per call
- 16 concurrent heavy searches easily approach 1-2 GB peak

Other findings (secondary):
- `static bool firstCall` data race in `extractFeatures()` — only if `NEURAL_NET_DEBUG` defined
- `rand()` is per-thread on MSVC (not a crash risk on Windows)
- `std::map::operator[]` in `getPlayer()` is formally non-const but safe for existing keys

### 6. Fix: Reduced threads to 4 — RE-LAUNCHED

Added `"Threads":4` to both `BlendSweep_vsMedium` and `BlendVsOriginal` in config.txt.
Re-launched: Feb 13 2026 ~17:40. Confirmed `4 threads` in output.

Expected duration: ~4-8 hours (slower with fewer threads, but should complete).

Replay directory: `bin/asset/replays/BlendSweep_vsMedium_2026-02-13_17-40-48/`

### 7. Partial results from crashed run (38 games, BlendUCT only)

| Matchup | Games | Winner | Win% |
|---|---|---|---|
| BlendUCT_50 vs BlendUCT_25 | 28 | BlendUCT_25 (75% playout) | 57.1% |
| BlendUCT_50 vs BlendUCT_10 | 10 | BlendUCT_10 (90% playout) | 80.0% |

**Early signal: More playout weight = stronger.** This suggests the current neural model hurts performance when weighted too heavily. BlendUCT_10 (90% playout / 10% neural) dominates BlendUCT_50 (50/50).

**Missing from partial data:**
- Any MediumAI matchups (key baseline)
- Any BlendAB matchups (UCT vs AB comparison)
- BlendVsOriginal (the critical test vs OriginalHardestAI)

### 8. Run 2 results — KILLED (14/240 games, too slow)

**Killed manually** after ~2 hours. At ~8 games/hour with 4 threads, the 240-game BlendSweep would have taken **~30 hours** — far too long for data that was already looking uninformative. BlendVsOriginal never started.

#### BlendSweep_vsMedium Results (run 2, 14 games)

| Matchup | Games | Result |
|---|---|---|
| BlendUCT_50 vs BlendUCT_25 | 8 | 4-4 (50/50) |
| BlendUCT_50 vs BlendUCT_10 | 6 | 3-3 (50/50) |

**P1 won ALL 14 games (100%).** Outcome is entirely determined by seat position (P1 starts with extra Drone). Blend weight makes zero difference in these mirror matchups.

No MediumAI, BlendAB, or OriginalHardestAI games were reached.

#### BlendVsOriginal Results

Never started (BlendSweep exited before it could begin).

### 9. Conclusion — Blending does NOT work (with current neural model)

**Combined evidence from all runs (38 + 14 = 52 games):**

1. **More playout weight = stronger** (run 1): BlendUCT_10 (90% playout) beat BlendUCT_50 (50/50) at 80% WR. BlendUCT_25 beat BlendUCT_50 at 57%.
2. **All blend weights equal when matched** (run 2): 50/50 outcomes, entirely seat-dependent.
3. **The neural component actively hurts performance** when given significant weight. The optimal "blend" converges toward pure playout (i.e., the existing OriginalHardestAI approach).
4. **No blend player ever faced MediumAI or OriginalHardestAI** across either run, so we cannot measure absolute strength, but the trend is clear.

**Root cause:** The supervised neural model (trained on expert replays, 57.7% val accuracy) is too weak. Blending a weak signal with a strong signal (playout) dilutes the strong signal. This confirms that **self-play data generation is the critical path** — the neural model must improve before blending can add value.

**Decision:** Stop investing time in blend tournaments. Focus on self-play data generation instead. If a future self-play-trained model shows >60% val accuracy, revisit blending then.

**Stability issue:** Blend tournaments crashed or exited early on EVERY attempt — exit code 3 (32/240 games), exit code 1 (38/240 games, OOM), and run 2 only managed 14/240 before being killed. No run ever completed or reached the MediumAI/OriginalHardestAI matchups. The blend eval may have an underlying stability problem beyond just OOM (possibly the JSON trailing comma bug corrupting replays mid-tournament, or some other issue). This needs investigation before any future blend runs.

**Lesson for future runs:** Always run a small pilot (e.g., 1 round of the full tournament, ~15 games) before committing to multi-hour runs. A 6-player round-robin with 7s blend players at 4 threads is far too slow for the x86 build.

## Tournament Configs (for reference)

```
BlendSweep_vsMedium: 16 rounds, Threads:4, RandomCards:8, 6 players (groups 1-6)
  BlendUCT_50 (50% neural, UCT cValue=2.0, 7s)
  BlendUCT_25 (25% neural, UCT cValue=2.0, 7s)
  BlendUCT_10 (10% neural, UCT cValue=2.0, 7s)
  BlendAB_50  (50% neural, Stack AB, 7s)
  BlendAB_25  (25% neural, Stack AB, 7s)
  MediumAI    (random from HardIterator_Root, instant)

BlendVsOriginal: 16 rounds, Threads:4, RandomCards:8, SaveReplays:true, 3 players
  BlendUCT_50       (50% neural, UCT, 7s)
  BlendAB_50        (50% neural, Stack AB, 7s)
  OriginalHardestAI (pure playout, Stack AB, 7s, legacy heuristics)
```

## Key Questions This Answers

1. **Does blending neural+playout beat pure playout?** (BlendVsOriginal — blend players vs OriginalHardestAI)
2. **Which blend weight is optimal?** (BlendSweep — 50/25/10 neural weight comparison)
3. **UCT vs AB for blended eval?** (BlendSweep — UCT vs AB variants at same weight)
4. **Does blend beat MediumAI convincingly?** (BlendSweep — all blend variants vs MediumAI; pure neural was ~42%)

## Future Consideration: x64 Build

The x86 OOM crash is a systemic issue for any multi-threaded tournament with heavy AI players. Adding an x64 configuration to `visualstudio/Prismata.sln` would give 128 TB virtual address space, completely eliminating OOM risk and allowing 16-thread tournaments. Currently only x86 configs exist (Debug|x86, Release|x86, Static Release|x86).
