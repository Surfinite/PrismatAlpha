# Deploying the DSNN as a swap-in `PrismataAI.exe` (play against it in the real client)

How to drop the DeepSets value-net AI into the actual Prismata (Steam/AIR) client and
play against it. The client launches `AI/PrismataAI.exe` as a child process and talks to it
over stdin/stdout (a one-shot JSON request → move reply per turn), so a 64-bit replacement
works fine alongside the 32-bit AIR client — they're separate processes.

Engine: the **dave-line** engine (`dave-master-jsonclean`, engine_v1) at
`C:\libraries\PrismataAI-dave-master`. The DSNN override + cwd-independent asset loading live
in `source/ai/AITools.cpp` + `source/ai/NeuralNet.cpp`.

## 1. Build the standalone (x64, GUI-off → no SFML needed)

```bat
cd C:\libraries\PrismataAI-dave-master
build_win.bat                              :: or, GUI-off explicitly:
"<VS>\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" ^
   --build build --config Release --target Prismata_Standalone --parallel 8
```
Output: `C:\libraries\PrismataAI-dave-master\bin\Prismata_Standalone.exe`
(the VS "Standalone Release" target names it `PrismataAI.exe`; either works — the client only
cares about the filename you drop in).

## 2. Deploy into the client

Replace the client's AI exe and place the model assets **next to the exe** (asset paths are
resolved relative to the executable's own location, so this works no matter what working
directory the client launches it from):

```
<Prismata>\AI\PrismataAI.exe                                  (the built standalone)
<Prismata>\AI\asset\config\neural_weights_mixed_35prop.bin    (the 35-prop SWA weights)
<Prismata>\AI\asset\config\unit_index.json                    (NN unit-name → index map)
<Prismata>\AI\use_dsnn.txt                                    (empty file = "DSNN on" switch)
```
`<Prismata>` = e.g. `C:\Program Files (x86)\Steam\steamapps\common\Prismata`.
**Back up the original `AI\PrismataAI.exe` first.** No `cardLibrary.jso` is needed — the live
path builds cards from the request's `mergedDeck`.

## 3. Trigger + which bot

The exe runs the DSNN only when forced; otherwise it plays whatever the client requested
(normal Master Bot). Force it either way:
- **Sentinel file** (recommended): an empty `AI\use_dsnn.txt` next to the exe. No env var.
- **Env var**: `PRISMATA_FORCE_DSNN=1` in the launching environment.
- Optional `PRISMATA_DSNN_WEIGHTS=<file>` to use a different weights file (default
  `neural_weights_mixed_35prop.bin`).

In-game, pick the **"7 second" Master Bot** (`aiPlayerName=HardestAI`). The override bumps its
7000 ms budget to **10000 ms**, so:
- **~10 s of thinking ⇒ you're playing the DSNN** (the confirmation tell + a slightly stronger
  opponent). The "3 second" bot (`HardAI`) stays DSNN @ 3 s.
- If it responds in ~7 s like normal, the override didn't fire (sentinel/weights not found) and
  you got the stock Master Bot.

## 4. Revert

Delete `AI\use_dsnn.txt` (or restore the backed-up original exe). With the sentinel gone the
exe behaves exactly like the stock AI it replaced.

## How it works (for maintainers)

- Spawn + protocol: `AIThreadHandler.as` launches `AI/PrismataAI.exe` via `NativeProcess`
  (no working directory set) and writes `{"mergedDeck":…,"gameState":…,"aiParameters":…,"aiPlayerName":"…"}\n`
  to stdin per turn, reading the `{"aiclicks":…}` reply from stdout.
- The two Master Bots are distinct difficulties: `HardAI` (3000 ms) and `HardestAI` (7000 ms),
  both `Player_StackAlphaBeta` + `NewIterator`. The SWF param blob the client sends also defines
  `HardIterator`/`HardIterator_Root`.
- Override (`AITools::GetAIMove`): if triggered, it ignores the requested player and builds a
  `Player_UCT` with `EvaluationMethods::NeuralNet` + the 35-prop weights, reusing the request's
  registered `HardIterator`/`HardIterator_Root`. Think time = requested `TimeLimit`, but 7000→10000.
  It falls back to the requested player (logging to stderr) if weights/iterators don't load.
- cwd-independent assets: `NeuralNet::getExecutableDir()` (Win32 `GetModuleFileNameA`) lets
  `loadWeights`/`loadUnitIndex`/`--dump-features` find `asset/config/...` relative to the exe.

## Notes / gotchas

- **Opponent name** shown in-game is the server account's `displayName` (`UITopBar.as`), not the
  exe — so it still reads "Master Bot". Renaming to "DSNN" needs an SWF/server change; the 10 s
  timing tell is the practical confirmation instead.
- **x64 vs the 32-bit AIR client**: fine — separate processes over stdin/stdout. The dave engine
  is x64-only (`CMakeLists.txt`).
- **VC++ runtime**: the exe is an MSVC build; the dev machine has it. For distribution to another
  machine, ship the VC++ redist (or build static).
- **Observed**: when far ahead in the endgame the AI may "stop thinking properly" — UCT converging
  on a near-certain win and not tightening the closing line. Evaluator-adjacent overconfidence, not
  a deployment bug.
