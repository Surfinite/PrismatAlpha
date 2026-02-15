# Self-Play Data Generation — Worker Context Instructions

**Date:** Feb 13, 2026
**Scope:** Implement self-play data generation infrastructure (Step 3 from CLAUDE.md)
**Pre-requisite:** Read `CLAUDE.md` sections 12, 17, 19, 20, 22-24, 29 for full project context.

---

## YOUR MISSION

Build C++ infrastructure that records neural-net feature vectors during OriginalHardestAI self-play tournaments, outputting binary training data. Then build a Python loader so the existing `training/train.py` can train on that data.

Churchill & Campbell (2019) proved this approach: 500K self-play games → 15M training examples → neural eval that beat playout 58.8% of the time. Our current neural net (trained on expert replays) only beats playout ~10% of the time. Self-play data is the critical path to a stronger model.

---

## PHASE 0: GATE CHECKS — Do These FIRST

Before writing any infrastructure code, validate the plan's timing assumptions.

### Gate 1: Measure Actual Game Time

Add this tournament config to `bin/asset/config/config.txt` (in the Benchmarks array):
```json
{ "run":true, "type":"Tournament", "name":"SelfPlayTimingTest", "rounds":25, "Threads":1, "UpdateIntervalSec":5, "RandomCards":8, "SaveReplays":false, "players":[ {"name":"OriginalHardestAI","group":1}, {"name":"OriginalHardestAI_Copy","group":2}] }
```

You'll also need a duplicate player config since both need different group numbers but the same AI:
```json
"OriginalHardestAI_Copy" : { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_Legacy", "MoveIterator":"HardIterator_Legacy", "Eval":"Playout", "PlayoutPlayer":"Playout_Legacy"}
```

**IMPORTANT — games per round math:** For a 2-player tournament with different groups, the `playRound()` method (Tournament.cpp:49-107) uses a double loop over all player pairs PLUS creates 2 games per pair (swapping colors). This means **4 games per round** for a 2-player tournament. With `"rounds": 25`, you get **100 games**. For the full generation run, `rounds = desired_games / 4`.

Run the timing test (build in Release for accurate numbers):
```
MSBuild.exe Prismata.sln //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
```
Then run `bin/Prismata_Testing.exe` and time it externally. Disable all other `"run":true` benchmarks/tournaments first.

**Record:**
- Wall-clock time for 100 games
- Seconds per game (from wall clock / 100)
- Look at the HTML output in `tests/` for turns/game

**OriginalHardestAI uses TimeLimit:7000 (7 seconds per move).** Churchill used 1000ms. After gate checks, create `OriginalHardestAI_1s` with `"TimeLimit":1000` for ~7x faster self-play generation.

### Gate 2: Thread Safety of extractFeatures

Read `source/ai/NeuralNet.cpp:273-412`. The function has:
- `static bool firstCall = true` — but this is inside `#ifdef NEURAL_NET_DEBUG` block (line 396). In Release builds, this code is compiled out entirely. Safe.
- All data read from `const GameState &` (read-only) and `this->` members (read-only after loadWeights)
- Output written to caller-owned `std::vector<float>& features`
- `validateSchema()` called only once during `loadWeights()` (NeuralNet.cpp:198), not per-invocation

**Verdict: Thread-safe.** No action needed.

### Gate 3: Run Multi-Threaded Smoke Test

Run an existing tournament config with 8+ threads to confirm no crashes:
```json
{ "run":true, "type":"Tournament", "name":"ThreadSafetyTest", "rounds":8, "Threads":8, "RandomCards":8, "SaveReplays":false, "players":[ {"name":"OriginalHardestAI","group":1}, {"name":"OriginalHardestAI_Copy","group":2}] }
```
This produces 32 games on 8 threads. Must complete without crashes or asserts.

---

## PHASE 1: C++ IMPLEMENTATION

### Critical API Facts (Verified Against Source)

These were verified by reading the actual source code. The build plan document had some errors which are corrected here.

#### extractFeatures — NO player parameter
```cpp
// source/ai/NeuralNet.h:75
void extractFeatures(const GameState & state, std::vector<float> & features) const;

// Called via singleton:
NeuralNet::Instance().extractFeatures(state, features);
```
The function reads `state.getActivePlayer()` internally for the active_player feature (index 1784). There is NO player parameter — the plan's `NeuralNet::extractFeatures(state, playerToMove, rec.features)` was WRONG.

#### winner() returns Player_None (3), NOT -1
```cpp
// source/engine/Constants.h:7
enum { Player_One = 0, Player_Two = 1, Player_Both = 2, Player_None = 3, Size };

// source/engine/GameState.cpp:1759-1777
const PlayerID GameState::winner() const
{
    if (!isGameOver()) return Players::Player_None;  // returns 3, not -1
    if (numCards(Player_One) + numKilledCards(Player_One) == 0) return Player_Two;
    if (numCards(Player_Two) + numKilledCards(Player_Two) == 0) return Player_One;
    return Players::Player_None;  // draw (both alive at turn limit)
}
```
The plan's `if (winner < 0)` for draw detection is WRONG. Use `winner == Players::Player_None`.

#### Game loop structure (TournamentGame.cpp:21-57)
```cpp
void TournamentGame::playGame()
{
    _stateSnapshots.push_back(_game.getState().toJSONString());  // initial state

    Timer t;
    int turnNumber = 0;
    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();  // line 30

        t.start();
        _game.playNextTurn();   // <-- AI thinks + executes move (line 33)
        double ms = t.getElapsedTimeInMilliSec();
        // ... timing, snapshot, logging ...
        turnNumber++;
    }
}
```

**Hook insertion point:** Between line 30 (`playerToMove` capture) and line 33 (`playNextTurn()`). At this moment the state represents what the AI is about to evaluate — resources are current, construction resolved, it's the start of this player's Action phase.

#### Game::playNextTurn() internals (Game.cpp:28-41)
```cpp
void Game::playNextTurn()
{
    PlayerPtr player = getPlayerToMove();
    m_previousMove.clear();
    player->getMove(m_state, m_previousMove);  // AI search happens here
    doMove(m_previousMove);                      // move applied to state
    m_actions += m_previousMove.size();
    m_turnsPlayed++;
}
```

#### Tournament thread dispatch (Tournament.cpp:149-163)
```cpp
for (size_t batchStart = 0; batchStart < _rounds; batchStart += _numThreads)
{
    size_t batchEnd = std::min(batchStart + _numThreads, _rounds);
    std::vector<std::thread> threads;
    for (size_t r = batchStart; r < batchEnd; ++r)
    {
        threads.emplace_back(&Tournament::playRound, this, std::cref(roundStates[r]));
    }
    for (auto & t : threads) { t.join(); }
    // ... print results ...
}
```

**Key:** `playRound` currently takes `(const GameState &)` only — no thread index. You'll need to add a thread index parameter for sink assignment. See implementation below.

#### playRound game creation (Tournament.cpp:49-106)
```cpp
void Tournament::playRound(const GameState & stateTemplate)
{
    GameState state(stateTemplate);
    for (size_t p1(0); p1 < _players.size(); ++p1)
    {
        for (size_t p2(0); p2 < _players.size(); ++p2)
        {
            if (_playerGroups[p1] == _playerGroups[p2]) continue;
            // Creates 2 games per pair: g1(p1 white, p2 black), g2(p2 white, p1 black)
            TournamentGame g1(state, _players[p1], w1, _players[p2], b1);
            TournamentGame g2(state, _players[p2], w2, _players[p1], b2);
            g1.playGame();
            g2.playGame();
            // ... results under mutex ...
        }
    }
}
```

For a 2-player mirror match: outer loop p1=0,p2=1 creates g1+g2. Then p1=1,p2=0 creates g1+g2 again (identical matchups, same card set). **4 games per round, 2 unique trajectories** (because OriginalHardestAI is deterministic and the duplicate pair plays the same card set). This is slightly wasteful but harmless for data generation.

---

### New Files to Create

#### 1. `source/testing/IDataSink.h`

```cpp
#pragma once
#include "../engine/GameState.h"

namespace Prismata
{

// Interface for receiving game events during tournament play.
// Default: no-op. SelfPlayDataSink writes binary training data.
class IDataSink
{
public:
    virtual ~IDataSink() = default;

    // Called at the start of each player's Action phase, BEFORE getMove().
    // state: the game state the AI is about to evaluate.
    virtual void onTurnStart(const GameState & state) {}

    // Called when the game ends.
    // winner: Players::Player_One (0), Player_Two (1), or Player_None (3) for draw.
    virtual void onGameEnd(PlayerID winner) {}

    // Called after all games for this sink are complete. Writes footer, flushes files.
    virtual void finalize() {}
};

}
```

#### 2. `source/testing/SelfPlayDataSink.h`

```cpp
#pragma once
#include "IDataSink.h"
#include "../ai/NeuralNet.h"
#include <fstream>
#include <vector>
#include <string>
#include <cstdint>
#include <atomic>

namespace Prismata
{

struct SelfPlayRecord
{
    std::vector<float> features;   // [featureDim] floats
    uint16_t turnNumber;
    uint8_t  playerIndex;          // which player was active (0 or 1)
};

class SelfPlayDataSink : public IDataSink
{
public:
    SelfPlayDataSink(int threadIndex, const std::string & outputDir,
                     std::atomic<uint32_t> & globalGameCounter,
                     uint32_t featureDim = 1785);
    ~SelfPlayDataSink();

    void onTurnStart(const GameState & state) override;
    void onGameEnd(PlayerID winner) override;
    void finalize() override;

    uint64_t totalRecordsWritten() const { return _totalRecords; }
    uint32_t totalGamesCompleted() const { return _totalGames; }

private:
    void openNewShard();
    void writeHeader();
    void writeRecord(const SelfPlayRecord & rec, float outcome, uint8_t flags);
    void finalizeShard();
    void rotateShardIfNeeded();
    uint32_t updateCRC(uint32_t crc, const void * data, size_t len) const;

    int _threadIndex;
    std::string _outputDir;
    uint32_t _featureDim;
    uint32_t _recordSize;
    std::atomic<uint32_t> & _globalGameCounter;  // shared across threads for unique game IDs

    // Current shard state
    std::ofstream _file;
    int _shardIndex = 0;
    uint64_t _shardRecordCount = 0;
    uint64_t _shardBytes = 0;
    static constexpr uint64_t SHARD_MAX_BYTES = 1ULL * 1024 * 1024 * 1024; // 1 GB

    // Current game accumulator
    uint32_t _currentGameId = 0;
    std::vector<SelfPlayRecord> _pendingRecords;

    // Lifetime stats
    uint64_t _totalRecords = 0;
    uint32_t _totalGames = 0;

    // CRC32 running value for current shard
    uint32_t _crc = 0;
};

}
```

#### 3. `source/testing/SelfPlayDataSink.cpp`

Key implementation points (write the full file, these are the critical sections):

**Constructor:**
- Pre-reserve `_pendingRecords` for 120 entries (typical game: ~60 turns × 2 players)
- Compute `_recordSize = featureDim * 4 + 4 + 4 + 2 + 1 + 1` (= 7152 for featureDim=1785)
- Call `openNewShard()` to create the first output file

**onTurnStart:**
```cpp
void SelfPlayDataSink::onTurnStart(const GameState & state)
{
    SelfPlayRecord rec;
    rec.features.resize(_featureDim, 0.0f);

    // extractFeatures takes (const GameState&, vector<float>&) — NO player parameter
    // It reads state.getActivePlayer() internally for the active_player feature
    NeuralNet::Instance().extractFeatures(state, rec.features);

    rec.turnNumber = static_cast<uint16_t>(state.getTurnNumber());
    rec.playerIndex = static_cast<uint8_t>(state.getActivePlayer());

    _pendingRecords.push_back(std::move(rec));
}
```

**onGameEnd:**
```cpp
void SelfPlayDataSink::onGameEnd(PlayerID winner)
{
    // Assign globally unique game ID
    _currentGameId = _globalGameCounter.fetch_add(1);

    for (const auto & rec : _pendingRecords)
    {
        float outcome;
        uint8_t flags = 0;

        if (winner == Players::Player_None)  // draw — winner() returns 3, NOT -1
        {
            outcome = 0.0f;
            flags |= 0x01;
        }
        else if (winner == rec.playerIndex)
        {
            outcome = 1.0f;    // this player won
        }
        else
        {
            outcome = -1.0f;   // this player lost
        }

        writeRecord(rec, outcome, flags);
    }

    _pendingRecords.clear();
    _totalGames++;

    // Flush after every game — lose at most 1 game on crash
    if (_file.is_open())
    {
        _file.flush();
    }

    rotateShardIfNeeded();

    // Progress logging every 100 games
    if (_totalGames % 100 == 0)
    {
        fprintf(stderr, "[SelfPlay] Thread %d: %u games, %llu records, shard %d (%.1f MB)\n",
                _threadIndex, _totalGames, (unsigned long long)_totalRecords,
                _shardIndex, (double)_shardBytes / (1024.0 * 1024.0));
        fflush(stderr);
    }
}
```

**Binary format — header (64 bytes):**
```
Offset 0:   uint32  magic         = 0x50534450  ("PSDP")
Offset 4:   uint32  version       = 1
Offset 8:   uint32  feature_dim   = 1785
Offset 12:  uint32  record_size   = 7152
Offset 16:  uint64  record_count  = 0xFFFFFFFFFFFFFFFF  (sentinel; updated on finalize)
Offset 24:  uint32  endian_check  = 0x01020304
Offset 28:  uint8[36] reserved    = zeros
```

**Binary format — per record (7152 bytes):**
```
float32[1785]  features       (7140 bytes)
float32        outcome        (4 bytes)    — +1.0, -1.0, or 0.0
uint32         game_id        (4 bytes)    — globally unique across all threads
uint16         turn_number    (2 bytes)    — from state.getTurnNumber()
uint8          player_index   (1 byte)     — 0 or 1
uint8          flags          (1 byte)     — bit 0: draw
```

**Binary format — footer (4 bytes):**
```
uint32  crc32  — over all record bytes (not header)
```

**finalizeShard():**
1. Write the CRC32 footer
2. Seek back to offset 16 and overwrite the sentinel record_count with actual `_shardRecordCount`
3. Close the file

**CRC32 implementation:**
Use zlib's `crc32()` if available (SFML likely links zlib), or embed a ~30-line table-based implementation. Update the running CRC in `writeRecord()` after writing each record's bytes.

**File naming:** `selfplay_t{threadIndex:02d}_s{shardIndex:03d}.bin`

### Modifications to Existing Files

#### 4. `source/testing/TournamentGame.h` — Add sink member

```cpp
#include "IDataSink.h"
// ... in class TournamentGame:
    IDataSink * _dataSink = nullptr;
public:
    void setDataSink(IDataSink * sink) { _dataSink = sink; }
```

#### 5. `source/testing/TournamentGame.cpp` — Add hooks in playGame()

The modified game loop:
```cpp
void TournamentGame::playGame()
{
    _stateSnapshots.push_back(_game.getState().toJSONString());

    Timer t;
    int turnNumber = 0;
    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        // === SELF-PLAY DATA HOOK: capture state BEFORE AI acts ===
        if (_dataSink)
        {
            _dataSink->onTurnStart(_game.getState());
        }

        t.start();
        _game.playNextTurn();
        double ms = t.getElapsedTimeInMilliSec();
        _playerTotalTimeMS[playerToMove] += ms;
        _maxTimeMS[playerToMove] = std::max((size_t)ms, _maxTimeMS[playerToMove]);

        _stateSnapshots.push_back(_game.getState().toJSONString());

        // ... existing buy logging ...
        turnNumber++;
    }

    // === SELF-PLAY DATA HOOK: record game result ===
    if (_dataSink)
    {
        _dataSink->onGameEnd(_game.getState().winner());
    }
}
```

**Note:** The per-turn `printf` buy logging (lines 42-54 in current code) will produce massive output during 10K+ game generation runs. Consider gating it behind a flag or just leaving it — stdout can be redirected to /dev/null. NOT a blocker.

#### 6. `source/testing/Tournament.h` — Add self-play config + sinks

```cpp
#include "SelfPlayDataSink.h"
#include <memory>
// ... in class Tournament:
    // Self-play data export
    bool _selfPlayEnabled = false;
    std::string _selfPlayOutputDir;
    std::atomic<uint32_t> _selfPlayGameCounter{0};
    std::vector<std::unique_ptr<SelfPlayDataSink>> _selfPlaySinks;
```

#### 7. `source/testing/Tournament.cpp` — Parse config, create sinks, wire to games

**In constructor:** Parse the new config fields:
```cpp
if (tournamentValue.HasMember("SelfPlayDataExport") && tournamentValue["SelfPlayDataExport"].IsObject())
{
    const auto & spConfig = tournamentValue["SelfPlayDataExport"];
    if (spConfig.HasMember("Enabled") && spConfig["Enabled"].IsBool())
        _selfPlayEnabled = spConfig["Enabled"].GetBool();
    if (spConfig.HasMember("OutputDir") && spConfig["OutputDir"].IsString())
        _selfPlayOutputDir = spConfig["OutputDir"].GetString();
}
```

**In run(), before thread dispatch:** Create per-thread sinks:
```cpp
if (_selfPlayEnabled && NeuralNet::Instance().isLoaded())
{
    std::filesystem::create_directories(_selfPlayOutputDir);
    _selfPlaySinks.resize(_numThreads);
    for (size_t i = 0; i < _numThreads; ++i)
    {
        _selfPlaySinks[i] = std::make_unique<SelfPlayDataSink>(
            (int)i, _selfPlayOutputDir, _selfPlayGameCounter,
            NeuralNet::Instance().stateDim());
    }
    printf("[SelfPlay] Exporting to %s (%zu threads)\n", _selfPlayOutputDir.c_str(), _numThreads);
}
```

**Modify playRound signature** to accept a thread-local sink:
```cpp
// Old:  void playRound(const GameState & state);
// New:  void playRound(const GameState & state, IDataSink * sink);
```

**In playRound**, set the sink on each game before playing:
```cpp
TournamentGame g1(state, _players[p1], w1, _players[p2], b1);
TournamentGame g2(state, _players[p2], w2, _players[p1], b2);
if (sink) g1.setDataSink(sink);
if (sink) g2.setDataSink(sink);
g1.playGame();
g2.playGame();
```

**Modify thread dispatch** to pass the sink:
```cpp
for (size_t r = batchStart; r < batchEnd; ++r)
{
    size_t threadIdx = r - batchStart;
    IDataSink * sink = (_selfPlayEnabled && threadIdx < _selfPlaySinks.size())
                       ? _selfPlaySinks[threadIdx].get() : nullptr;
    threads.emplace_back(&Tournament::playRound, this, std::cref(roundStates[r]), sink);
}
```

**After all rounds complete:** Finalize sinks and write metadata:
```cpp
if (_selfPlayEnabled)
{
    uint64_t totalRecords = 0;
    uint32_t totalGames = 0;
    for (auto & sink : _selfPlaySinks)
    {
        if (sink)
        {
            sink->finalize();
            totalRecords += sink->totalRecordsWritten();
            totalGames += sink->totalGamesCompleted();
        }
    }
    printf("[SelfPlay] COMPLETE: %u games, %llu records\n",
           totalGames, (unsigned long long)totalRecords);

    // Write selfplay_meta.json (use fprintf or RapidJSON)
    // Write selfplay_games.jsonl — this needs per-game data which
    // SelfPlayDataSink should accumulate (card_set, winner, turns, game_id)
}
```

**selfplay_games.jsonl:** For each game, SelfPlayDataSink should also accumulate a one-line JSON entry:
```json
{"game_id":0,"winner":0,"turns":58,"records":58,"draw":false}
```
Store these in a `std::vector<std::string>` and write them all out in `finalize()` or expose them for Tournament to collect.

Getting the card set into the JSONL requires passing it through. The card set is embedded in the GameState — you can extract it from `state.numCardsBuyable()` and `state.getCardBuyableByIndex(i).getType().getUIName()`. Do this in `onTurnStart` on the first turn (when `_pendingRecords` is empty).

#### 8. `bin/asset/config/config.txt` — Add configs

**Player configs (add to the "Players" section):**
```json
"OriginalHardestAI_1s" : { "type":"Player_StackAlphaBeta", "TimeLimit":1000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_Legacy", "MoveIterator":"HardIterator_Legacy", "Eval":"Playout", "PlayoutPlayer":"Playout_Legacy"},
"OriginalHardestAI_Copy" : { "type":"Player_StackAlphaBeta", "TimeLimit":7000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_Legacy", "MoveIterator":"HardIterator_Legacy", "Eval":"Playout", "PlayoutPlayer":"Playout_Legacy"}
```

**Tournament configs (add to Benchmarks array):**
```json
{ "run":false, "type":"Tournament", "name":"SelfPlayTimingTest", "rounds":25, "Threads":1, "UpdateIntervalSec":5, "RandomCards":8, "SaveReplays":false, "players":[ {"name":"OriginalHardestAI","group":1}, {"name":"OriginalHardestAI_Copy","group":2}] },

{ "run":false, "type":"Tournament", "name":"SelfPlay_Smoke", "rounds":3, "Threads":1, "UpdateIntervalSec":5, "RandomCards":8, "SaveReplays":false, "SelfPlayDataExport":{"Enabled":true, "OutputDir":"training/data/selfplay_smoke/"}, "players":[ {"name":"OriginalHardestAI_1s","group":1}, {"name":"OriginalHardestAI_Copy_1s","group":2}] },

{ "run":false, "type":"Tournament", "name":"SelfPlay_10K", "rounds":2500, "Threads":8, "UpdateIntervalSec":30, "RandomCards":8, "SaveReplays":false, "SelfPlayDataExport":{"Enabled":true, "OutputDir":"training/data/selfplay/"}, "players":[ {"name":"OriginalHardestAI_1s","group":1}, {"name":"OriginalHardestAI_Copy_1s","group":2}] }
```

Note: `rounds:2500` produces `2500 × 4 = 10,000` games (the double loop + color swap = 4 games per round for 2 players). Similarly, `rounds:3` produces 12 games for the smoke test.

Also add the 1s copy:
```json
"OriginalHardestAI_Copy_1s" : { "type":"Player_StackAlphaBeta", "TimeLimit":1000, "MaxChildren":40, "RootMoveIterator":"HardIterator_Root_Legacy", "MoveIterator":"HardIterator_Legacy", "Eval":"Playout", "PlayoutPlayer":"Playout_Legacy"}
```

#### 9. `visualstudio/Prismata_Testing.vcxproj` — Add new files

Add to the `<ItemGroup>` containing ClCompile entries (around lines 30-37):
```xml
<ClCompile Include="..\source\testing\SelfPlayDataSink.cpp" />
```

Add to the `<ItemGroup>` containing ClInclude entries (around lines 40-46):
```xml
<ClInclude Include="..\source\testing\IDataSink.h" />
<ClInclude Include="..\source\testing\SelfPlayDataSink.h" />
```

---

## PHASE 2: VERIFICATION

After building (`//t:Rebuild //p:Configuration=Debug //p:Platform=x86`), run these in order:

### V1: Smoke Test (12 games)
Set `SelfPlay_Smoke` to `"run":true`, all others to `"run":false`.
Run `bin/Prismata_Testing_d.exe`.

**Check:**
- [ ] Files created in `training/data/selfplay_smoke/`
- [ ] File name matches `selfplay_t00_s000.bin`
- [ ] File size = 64 (header) + N × 7152 (records) + 4 (footer), where N ≈ 12 games × ~60 turns = ~720 records
- [ ] Header: magic=0x50534450, version=1, feature_dim=1785, record_size=7152, endian=0x01020304

### V2: Python Loader Test
Run the Python loader (see Phase 3) on the smoke test output:
```bash
python training/load_selfplay.py training/data/selfplay_smoke/
```
- [ ] CRC32 validates
- [ ] Record count matches header (or inferred from size if sentinel)
- [ ] All outcomes are exactly +1.0, -1.0, or 0.0
- [ ] player_index values are all 0 or 1
- [ ] No NaN or Inf in features
- [ ] game_id values are sequential with no gaps

### V3: Outcome Label Correctness
For a few game_ids, verify:
- All records where player_index=0 in a game won by player 0 have outcome=+1.0
- All records where player_index=1 in that same game have outcome=-1.0
- Vice versa for games won by player 1
- Draw games (rare): all outcomes=0.0

### V4: Feature Spot-Check
Compare features from the binary against a manual `NeuralNet::Instance().dumpFeaturesToFile()` call on the same game state. Values must match exactly (float32 round-trip).

### V5: Overfit Test
Train on smoke test data with no regularization:
```bash
python training/train.py --selfplay-dir training/data/selfplay_smoke/ --epochs 200 --lr 1e-3 --dropout 0.0 --batch-size 64
```
- [ ] Training loss → near zero (< 0.01)
- [ ] Training accuracy → > 95%
If this fails, the data pipeline has a bug.

---

## PHASE 3: PYTHON PIPELINE

### `training/load_selfplay.py`

Binary shard loader. Key requirements:
- Parse the 64-byte header, validate magic/version/endianness
- If record_count is sentinel (0xFFFFFFFFFFFFFFFF), infer from file size
- Validate CRC32 over record bytes (use `zlib.crc32()`)
- Parse records into numpy structured array via `np.frombuffer` with custom dtype
- `load_all_shards(directory)` loads and concatenates all `selfplay_t*_s*.bin` files

Record dtype:
```python
dt = np.dtype([
    ('features', np.float32, (1785,)),
    ('outcome', np.float32),
    ('game_id', np.uint32),
    ('turn_number', np.uint16),
    ('player_index', np.uint8),
    ('flags', np.uint8),
])
```

### Modifications to `training/train.py`

Add CLI arguments:
- `--selfplay-dir PATH` — path to directory with binary shards
- `--expert-weight FLOAT` — fraction of training data from expert replays (default 0.5)

When `--selfplay-dir` is provided:
1. Load self-play data via `load_selfplay.load_all_shards()`
2. Split self-play data into train/val **by game_id** (NOT by record — same lesson as the section 23 leakage disaster). Use `game_id % 10 == 0` for val (deterministic, stable across runs).
3. If `--expert-weight > 0`, also load `training/data/train.pt` and mix using WeightedRandomSampler
4. Train as normal

**CRITICAL: Train/val split MUST be by game_id.** All records from the same game share the same outcome label and near-identical features. Random per-record splitting causes massive data leakage (section 23 proved this — accuracy went from 99.9% to 57.7% after fixing the split).

### No changes to `training/vectorize.py`

Self-play features are pre-computed by C++ `extractFeatures()`. The JSONL→tensor pipeline is only for expert replay data.

---

## DECISIONS ALREADY MADE — DO NOT RE-DECIDE

1. **Absolute POV features (P0 first, P1 second).** Matches extractFeatures() and the trained supervised model. DO NOT rotate features to "current player first."

2. **Use OriginalHardestAI (not HardestAI with fixes) for self-play.** It's the stable, unmodified baseline matching Churchill's setup.

3. **Keep expert data in the training mix.** Start 50/50, never below 20%. The 251K expert examples are free to include and provide exposure to expert-level positions the weak self-play bot won't visit.

4. **Train both value and policy heads.** Keep `--policy-weight 0.5`. Policy head needed for future PUCT.

5. **tanh is NOT in the PyTorch model.** Raw logits during training. `tanhf()` at C++ inference time only.

6. **Card set format: random Base+8** (most common tournament format).

---

## PITFALLS TO AVOID

1. **extractFeatures has NO player parameter.** It's `(const GameState&, vector<float>&)`. Active player is read from state internally.

2. **winner() returns 3 (Player_None) for draws, NOT -1.** Use `== Players::Player_None` not `< 0`.

3. **4 games per round for 2-player tournaments.** Round count = desired_games / 4.

4. **Add new files to Prismata_Testing.vcxproj.** VS won't compile files not in the project.

5. **Always `//t:Rebuild`, never `//t:Build`.** Incremental builds may compile .obj without relinking the exe.

6. **Cannot rebuild while exe is running.** LNK1104 linker error.

7. **Pre-size feature vector with zeros before extractFeatures().** `features.resize(featureDim, 0.0f)` or use `features.assign(featureDim, 0.0f)`.

8. **Redirect stdout for large runs.** The per-turn buy logging in playGame() will produce gigabytes of output for 10K games. Use `> NUL` on Windows or consider gating the printf.

9. **Build Release for generation, Debug for testing.** Release is 3-5x faster. Debug has `_d` suffix on exe name.

10. **Disable the currently `"run":true` BlendCrashTest tournament** in config.txt before running self-play configs.

---

## BUILD COMMANDS

**Debug (for testing/verification):**
```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m
```
Output: `bin/Prismata_Testing_d.exe`

**Release (for data generation):**
```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
```
Output: `bin/Prismata_Testing.exe`

The exe runs from the `bin/` directory (working directory matters for config file paths):
```bash
cd bin && ./Prismata_Testing.exe    # Release
cd bin && ./Prismata_Testing_d.exe  # Debug
```

---

## EXECUTION CHECKLIST

```
Phase 0: Gate Checks
  [ ] Add OriginalHardestAI_Copy + SelfPlayTimingTest config
  [ ] Build Release
  [ ] Run timing test (100 games, 1 thread) — record sec/game, turns/game
  [ ] Run thread safety test (32 games, 8 threads) — no crashes
  [ ] DECISION: Use 7s or 1s time limit for generation (based on timing results)

Phase 1: C++ Implementation
  [ ] Create IDataSink.h
  [ ] Create SelfPlayDataSink.h
  [ ] Create SelfPlayDataSink.cpp (with CRC32, header/footer, per-game flush)
  [ ] Modify TournamentGame.h (add IDataSink* member + setter)
  [ ] Modify TournamentGame.cpp (add onTurnStart + onGameEnd hooks)
  [ ] Modify Tournament.h (add self-play config members + sink vector)
  [ ] Modify Tournament.cpp (parse config, create sinks, wire to games, write metadata)
  [ ] Add new files to Prismata_Testing.vcxproj
  [ ] Add tournament configs to config.txt
  [ ] Build Debug — verify compiles

Phase 2: Verification
  [ ] V1: Smoke test (12 games) — files created, sizes correct
  [ ] V2: Python loader — CRC validates, records parsed correctly
  [ ] V3: Outcome labels correct (cross-check winner vs per-record outcomes)
  [ ] V4: Feature spot-check (match dumpFeaturesToFile output)
  [ ] V5: Overfit test — training loss → ~0 on smoke data

Phase 3: Python Pipeline
  [ ] Create training/load_selfplay.py
  [ ] Modify training/train.py (--selfplay-dir, --expert-weight, game-level val split)
  [ ] V5 overfit test (above) validates the full pipeline

Phase 4: Generate + Train
  [ ] Build Release
  [ ] Generate 10K self-play games (SelfPlay_10K config, ~8-16 hours depending on time limit)
  [ ] Load and validate data (load_selfplay.py)
  [ ] Train with 50/50 expert/self-play mix
  [ ] Export weights (training/export_weights.py)
  [ ] Tournament: new model vs OriginalHardestAI (200+ games)
  [ ] Record results in CLAUDE.md
```

---

## FILE SUMMARY

| File | Action | Lines (est) |
|------|--------|-------------|
| `source/testing/IDataSink.h` | NEW | ~20 |
| `source/testing/SelfPlayDataSink.h` | NEW | ~60 |
| `source/testing/SelfPlayDataSink.cpp` | NEW | ~250 |
| `source/testing/TournamentGame.h` | MODIFY | +3 |
| `source/testing/TournamentGame.cpp` | MODIFY | +8 |
| `source/testing/Tournament.h` | MODIFY | +8 |
| `source/testing/Tournament.cpp` | MODIFY | +50 |
| `bin/asset/config/config.txt` | MODIFY | +15 |
| `visualstudio/Prismata_Testing.vcxproj` | MODIFY | +3 |
| `training/load_selfplay.py` | NEW | ~100 |
| `training/train.py` | MODIFY | +40 |
