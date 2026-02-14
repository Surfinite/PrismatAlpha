#include "SelfPlayDataSink.h"
#include <cstdio>
#include <cstring>
#include <sstream>

using namespace Prismata;

// CRC32 lookup table, computed at startup (IEEE 802.3 polynomial 0xEDB88320)
static uint32_t crc32_table[256];
static bool crc32_table_initialized = false;

static void initCRC32Table()
{
    if (crc32_table_initialized) return;
    for (uint32_t i = 0; i < 256; i++)
    {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++)
        {
            if (crc & 1)
                crc = (crc >> 1) ^ 0xEDB88320;
            else
                crc >>= 1;
        }
        crc32_table[i] = crc;
    }
    crc32_table_initialized = true;
}

SelfPlayDataSink::SelfPlayDataSink(int threadIndex, const std::string & outputDir,
                                   std::atomic<uint32_t> & globalGameCounter,
                                   uint32_t featureDim)
    : _threadIndex(threadIndex)
    , _outputDir(outputDir)
    , _featureDim(featureDim)
    , _recordSize(featureDim * 4 + 4 + 4 + 2 + 1 + 1)  // features + outcome + game_id + turn + player + flags
    , _globalGameCounter(globalGameCounter)
{
    initCRC32Table();
    _pendingRecords.reserve(120);  // typical game: ~60 turns x 2 players
    openNewShard();
}

SelfPlayDataSink::~SelfPlayDataSink()
{
    if (_file.is_open())
    {
        finalizeShard();
    }
}

void SelfPlayDataSink::openNewShard()
{
    char filename[128];
    snprintf(filename, sizeof(filename), "selfplay_t%02d_s%03d.bin", _threadIndex, _shardIndex);

    std::string path = _outputDir + "/" + filename;
    _file.open(path, std::ios::binary);
    if (!_file.is_open())
    {
        fprintf(stderr, "[SelfPlay] ERROR: Cannot open %s for writing\n", path.c_str());
        return;
    }

    _shardRecordCount = 0;
    _shardBytes = 0;
    _crc = 0;

    writeHeader();
}

void SelfPlayDataSink::writeHeader()
{
    // 64-byte header
    uint8_t header[64];
    memset(header, 0, sizeof(header));

    uint32_t magic = 0x50534450;       // "PSDP"
    uint32_t version = 1;
    uint32_t featureDim = _featureDim;
    uint32_t recordSize = _recordSize;
    uint64_t recordCount = 0xFFFFFFFFFFFFFFFFULL;  // sentinel, updated on finalize
    uint32_t endianCheck = 0x01020304;

    memcpy(header + 0,  &magic,       4);
    memcpy(header + 4,  &version,     4);
    memcpy(header + 8,  &featureDim,  4);
    memcpy(header + 12, &recordSize,  4);
    memcpy(header + 16, &recordCount, 8);
    memcpy(header + 24, &endianCheck, 4);
    // bytes 28-63 are reserved zeros

    _file.write(reinterpret_cast<const char *>(header), 64);
    _shardBytes = 64;
}

void SelfPlayDataSink::writeRecord(const SelfPlayRecord & rec, float outcome, uint8_t flags)
{
    if (!_file.is_open()) return;

    // Write features
    _file.write(reinterpret_cast<const char *>(rec.features.data()), _featureDim * sizeof(float));
    _crc = updateCRC(_crc, rec.features.data(), _featureDim * sizeof(float));

    // Write outcome
    _file.write(reinterpret_cast<const char *>(&outcome), sizeof(float));
    _crc = updateCRC(_crc, &outcome, sizeof(float));

    // Write game_id
    _file.write(reinterpret_cast<const char *>(&_currentGameId), sizeof(uint32_t));
    _crc = updateCRC(_crc, &_currentGameId, sizeof(uint32_t));

    // Write turn_number
    _file.write(reinterpret_cast<const char *>(&rec.turnNumber), sizeof(uint16_t));
    _crc = updateCRC(_crc, &rec.turnNumber, sizeof(uint16_t));

    // Write player_index
    _file.write(reinterpret_cast<const char *>(&rec.playerIndex), sizeof(uint8_t));
    _crc = updateCRC(_crc, &rec.playerIndex, sizeof(uint8_t));

    // Write flags
    _file.write(reinterpret_cast<const char *>(&flags), sizeof(uint8_t));
    _crc = updateCRC(_crc, &flags, sizeof(uint8_t));

    _shardRecordCount++;
    _shardBytes += _recordSize;
    _totalRecords++;
}

void SelfPlayDataSink::onTurnStart(const GameState & state)
{
    SelfPlayRecord rec;
    rec.features.resize(_featureDim, 0.0f);

    // extractFeatures takes (const GameState&, vector<float>&) — NO player parameter
    NeuralNet::Instance().extractFeatures(state, rec.features);

    rec.turnNumber = static_cast<uint16_t>(state.getTurnNumber());
    rec.playerIndex = static_cast<uint8_t>(state.getActivePlayer());

    _pendingRecords.push_back(std::move(rec));
}

void SelfPlayDataSink::onGameEnd(PlayerID winner)
{
    // Assign globally unique game ID
    _currentGameId = _globalGameCounter.fetch_add(1);

    uint32_t turnCount = static_cast<uint32_t>(_pendingRecords.size());
    bool isDraw = (winner == Players::Player_None);

    for (const auto & rec : _pendingRecords)
    {
        float outcome;
        uint8_t flags = 0;

        if (isDraw)
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

    // Build per-game JSONL metadata line
    std::ostringstream meta;
    meta << "{\"game_id\":" << _currentGameId
         << ",\"winner\":" << (int)winner
         << ",\"turns\":" << turnCount
         << ",\"records\":" << turnCount
         << ",\"draw\":" << (isDraw ? "true" : "false")
         << "}";
    _gameMetadata.push_back(meta.str());

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

void SelfPlayDataSink::finalizeShard()
{
    if (!_file.is_open()) return;

    // Write CRC32 footer
    _file.write(reinterpret_cast<const char *>(&_crc), sizeof(uint32_t));

    // Seek back to offset 16 and write actual record count
    _file.seekp(16, std::ios::beg);
    _file.write(reinterpret_cast<const char *>(&_shardRecordCount), sizeof(uint64_t));

    _file.close();
}

void SelfPlayDataSink::finalize()
{
    // Finalize the current shard
    finalizeShard();

    // Write per-game metadata JSONL file
    if (!_gameMetadata.empty())
    {
        char filename[128];
        snprintf(filename, sizeof(filename), "selfplay_t%02d_games.jsonl", _threadIndex);
        std::string path = _outputDir + "/" + filename;

        std::ofstream metaFile(path);
        if (metaFile.is_open())
        {
            for (const auto & line : _gameMetadata)
            {
                metaFile << line << "\n";
            }
            metaFile.close();
        }
    }

    fprintf(stderr, "[SelfPlay] Thread %d FINALIZED: %u games, %llu records, %d shards\n",
            _threadIndex, _totalGames, (unsigned long long)_totalRecords, _shardIndex + 1);
    fflush(stderr);
}

void SelfPlayDataSink::rotateShardIfNeeded()
{
    if (_shardBytes >= SHARD_MAX_BYTES)
    {
        finalizeShard();
        _shardIndex++;
        openNewShard();
    }
}

uint32_t SelfPlayDataSink::updateCRC(uint32_t crc, const void * data, size_t len) const
{
    const uint8_t * bytes = static_cast<const uint8_t *>(data);
    crc = crc ^ 0xFFFFFFFF;
    for (size_t i = 0; i < len; ++i)
    {
        crc = crc32_table[(crc ^ bytes[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFF;
}
