#pragma once

#include "Prismata.h"
#include "rapidjson/document.h"
#include "TournamentGame.h"
#include "SelfPlayDataSink.h"
#include "Timer.h"
#include <mutex>
#include <thread>
#include <atomic>
#include <memory>

namespace Prismata
{

class Tournament
{
    std::string                         _name;
    std::string                         _type;
    std::string                         _date;
    size_t                              _rounds;
    std::atomic<size_t>                 _totalGamesPlayed;
    size_t                              _updateIntervalSec;
    size_t                              _randomCards;
    size_t                              _numThreads;
    bool                                _saveReplays = true;
    bool                                _skipColorSwap = false;
    std::string                         _replayDir;
    Timer                               _timeElapsed;
    std::mutex                          _resultsMutex;

    std::vector<std::string>            _players;
    std::vector<std::string>            _stateDescriptions;
    std::vector<int>                    _playerGroups;
    std::vector<int>                    _totalGames;
    std::vector<int>                    _totalWins;
    std::vector<int>                    _totalDraws;
    std::vector<int>                    _totalPlayouts;
    std::vector<int>                    _totalTurns;
    std::vector<int>                    _maxTimeMS;
    std::vector<int>                    _totalTimeMS;
    std::vector< std::vector<int> >     _numGames;
    std::vector< std::vector<int> >     _wins;
    std::vector< std::vector<int> >     _draws;
    std::vector< std::vector<int> >     _turns;

    int getPlayerIndex(const std::string & playerName) const;
    void parseResult(std::string & result);
    void parseTournamentGameResult(const TournamentGame & game);
    void playGame(TournamentGame & game);
    void playRound(const GameState & state, IDataSink * sink);
    void writeHTMLResults();
    void printResults() const;
    std::string getTimeStringFromMS(const size_t ms);

    // Self-play data export
    bool                                            _selfPlayEnabled = false;
    std::string                                     _selfPlayOutputDir;
    std::atomic<uint32_t>                           _selfPlayGameCounter{0};
    std::vector<std::unique_ptr<SelfPlayDataSink>>  _selfPlaySinks;

public:

    Tournament(const rapidjson::Value & tournamentValue);
    void run();

};

}