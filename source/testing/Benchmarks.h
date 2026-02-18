#pragma once

#include "Prismata.h"
#include "rapidjson/rapidjson.h"
#include "PlayerBenchmark.h"

namespace Prismata
{

namespace Benchmarks
{
    void DoBenchmarks(const std::string & filename);

    void DoTournamentBenchmark(const rapidjson::Value & value);
    void DoPlayerBenchmark(const PlayerBenchmark & benchmark);

    void DoChillIteratorBenchmarkJSON(const rapidjson::Value & value);
    void DoChillIteratorBenchmark(size_t timeLimitMS, size_t histogramMinIndex, size_t histogramMaxIndex, size_t histogramMaxValue);

    void DoRandomSetTest(size_t numTrials, size_t cardsPerSet);
    void DoFixedSetTest(const std::vector<std::string> & dominionCards, const std::string & playerName, size_t numGames, size_t trackTurns);
    void DoReplayValidation(const std::string & validationFile, const std::string & outputFile);
    void DoSuggest(const std::string & stateFile, const std::string & playerName, int thinkTimeMs);
}
}
