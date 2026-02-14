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
    std::atomic<uint32_t> & _globalGameCounter;

    // Current shard state
    std::ofstream _file;
    int _shardIndex = 0;
    uint64_t _shardRecordCount = 0;
    uint64_t _shardBytes = 0;
    static constexpr uint64_t SHARD_MAX_BYTES = 1ULL * 1024 * 1024 * 1024; // 1 GB

    // Current game accumulator
    uint32_t _currentGameId = 0;
    std::vector<SelfPlayRecord> _pendingRecords;

    // Per-game JSONL metadata accumulator
    std::vector<std::string> _gameMetadata;

    // Lifetime stats
    uint64_t _totalRecords = 0;
    uint32_t _totalGames = 0;

    // CRC32 running value for current shard
    uint32_t _crc = 0;
};

}
