#include "Tournament.h"
#include "TestingConfig.h"
#include "Timer.h"
#include "PrismataAI.h"
#include "NeuralNet.h"

#include <iostream>
#include <iomanip>
#include <ctime>
#include <sstream>
#include <algorithm>
#include <filesystem>
using namespace Prismata;

Tournament::Tournament(const rapidjson::Value & tournamentValue)
    : _totalGamesPlayed(0)
    , _updateIntervalSec(0)
    , _randomCards(8)
    , _numThreads(std::thread::hardware_concurrency())
{
    PRISMATA_ASSERT(tournamentValue.HasMember("name"), "Tournament has no name");
    PRISMATA_ASSERT(tournamentValue.HasMember("rounds"), "Tournament has no rounds number");
    PRISMATA_ASSERT(tournamentValue.HasMember("players"), "Tournament has no players");

    JSONTools::ReadString("name", tournamentValue, _name);
    JSONTools::ReadInt("rounds", tournamentValue, _rounds);
    JSONTools::ReadInt("RandomCards", tournamentValue, _randomCards);
    JSONTools::ReadInt("UpdateIntervalSec", tournamentValue, _updateIntervalSec);

    if (tournamentValue.HasMember("Threads"))
    {
        JSONTools::ReadInt("Threads", tournamentValue, _numThreads);
    }
    if (_numThreads < 1) _numThreads = 1;

    if (tournamentValue.HasMember("SaveReplays") && tournamentValue["SaveReplays"].IsBool())
    {
        _saveReplays = tournamentValue["SaveReplays"].GetBool();
    }

    if (tournamentValue.HasMember("SkipColorSwap") && tournamentValue["SkipColorSwap"].IsBool())
    {
        _skipColorSwap = tournamentValue["SkipColorSwap"].GetBool();
    }

    // Parse self-play data export config
    if (tournamentValue.HasMember("SelfPlayDataExport") && tournamentValue["SelfPlayDataExport"].IsObject())
    {
        const auto & spConfig = tournamentValue["SelfPlayDataExport"];
        if (spConfig.HasMember("Enabled") && spConfig["Enabled"].IsBool())
            _selfPlayEnabled = spConfig["Enabled"].GetBool();
        if (spConfig.HasMember("OutputDir") && spConfig["OutputDir"].IsString())
            _selfPlayOutputDir = spConfig["OutputDir"].GetString();
    }

    PRISMATA_ASSERT(tournamentValue["players"].Size() >= 2, "Tournament has less than 2 players");

    for (size_t i(0); i < tournamentValue["players"].Size(); ++i)
    {
        _players.push_back(tournamentValue["players"][i]["name"].GetString());
        _playerGroups.push_back(tournamentValue["players"][i]["group"].GetInt());
    }

    // Auto-detect self-play: if all cross-group player pairs have identical configs,
    // skip color-swapped games (they'd be duplicates for deterministic AIs)
    if (!_skipColorSwap)
    {
        bool allPairsSame = true;
        bool foundPair = false;
        for (size_t i = 0; i < _players.size() && allPairsSame; ++i)
        {
            for (size_t j = i + 1; j < _players.size() && allPairsSame; ++j)
            {
                if (_playerGroups[i] != _playerGroups[j])
                {
                    foundPair = true;
                    if (!AIParameters::Instance().playersHaveSameConfig(_players[i], _players[j]))
                    {
                        allPairsSame = false;
                    }
                }
            }
        }
        if (foundPair && allPairsSame)
        {
            _skipColorSwap = true;
            printf("Auto-detected self-play (identical AI configs). Skipping color-swapped games.\n");
            fflush(stdout);
        }
    }
}

void Tournament::playRound(const GameState & stateTemplate, IDataSink * sink)
{
    try
    {
        // Each thread gets its own copy of the state
        GameState state(stateTemplate);

        for (size_t p1(0); p1 < _players.size(); ++p1)
        {
            for (size_t p2(0); p2 < _players.size(); ++p2)
            {
                if (_playerGroups[p1] == _playerGroups[p2])
                {
                    continue;
                }

                // Skip duplicate pair: g1+g2 already cover both color orders
                if (p2 <= p1)
                {
                    continue;
                }

                PlayerPtr w1 = AIParameters::Instance().getPlayer(Players::Player_One, _players[p1]);
                PlayerPtr b1 = AIParameters::Instance().getPlayer(Players::Player_Two, _players[p2]);

                TournamentGame g1(state, _players[p1], w1, _players[p2], b1);
                if (sink) g1.setDataSink(sink);
                if (_saveReplays) g1.setSaveReplays(true);
                g1.playGame();

                // Color-swapped game: skip for self-play (identical AIs produce identical games)
                TournamentGame * g2ptr = nullptr;
                TournamentGame g2(state, "", PlayerPtr(), "", PlayerPtr());  // placeholder
                if (!_skipColorSwap)
                {
                    PlayerPtr w2 = AIParameters::Instance().getPlayer(Players::Player_One, _players[p2]);
                    PlayerPtr b2 = AIParameters::Instance().getPlayer(Players::Player_Two, _players[p1]);
                    g2 = TournamentGame(state, _players[p2], w2, _players[p1], b2);
                    if (sink) g2.setDataSink(sink);
                    if (_saveReplays) g2.setSaveReplays(true);
                    g2.playGame();
                    g2ptr = &g2;
                }

                {
                    std::lock_guard<std::mutex> lock(_resultsMutex);
                    parseTournamentGameResult(g1);
                    size_t gameNum1 = _totalGamesPlayed++;

                    if (_saveReplays)
                    {
                        char buf[64];
                        snprintf(buf, sizeof(buf), "game_%04zu.json", gameNum1);
                        g1.saveReplay(_replayDir + "/" + buf);
                    }

                    if (g2ptr)
                    {
                        parseTournamentGameResult(g2);
                        size_t gameNum2 = _totalGamesPlayed++;
                        if (_saveReplays)
                        {
                            char buf[64];
                            snprintf(buf, sizeof(buf), "game_%04zu.json", gameNum2);
                            g2.saveReplay(_replayDir + "/" + buf);
                        }
                    }
                }
            }
        }
    }
    catch (const std::exception & e)
    {
        std::lock_guard<std::mutex> lock(_resultsMutex);
        fprintf(stderr, "\n*** TOURNAMENT THREAD EXCEPTION: %s\n", e.what());
        fflush(stderr);
    }
    catch (...)
    {
        std::lock_guard<std::mutex> lock(_resultsMutex);
        fprintf(stderr, "\n*** TOURNAMENT THREAD UNKNOWN EXCEPTION\n");
        fflush(stderr);
    }
}

void Tournament::run()
{
    auto time = std::time(nullptr);
    auto tm = *std::localtime(&time);

    std::stringstream startDate;
    startDate << std::put_time(&tm, "%Y-%m-%d_%H-%M-%S");
    _date = startDate.str();

    _totalGames = std::vector<int>(_players.size(), 0);
    _totalWins = std::vector<int>(_players.size(), 0);
    _totalDraws = std::vector<int>(_players.size(), 0);
    _totalTurns = std::vector<int>(_players.size(), 0);
    _totalPlayouts = std::vector<int>(_players.size(), 0);
    _totalTimeMS = std::vector<int>(_players.size(), 0);
    _maxTimeMS = std::vector<int>(_players.size(), 0);
    _numGames = std::vector< std::vector<int> >(_players.size(), std::vector<int>(_players.size(), 0));
    _wins = std::vector< std::vector<int> >(_players.size(), std::vector<int>(_players.size(), 0));
    _draws = std::vector< std::vector<int> >(_players.size(), std::vector<int>(_players.size(), 0));
    _turns = std::vector< std::vector<int> >(_players.size(), std::vector<int>(_players.size(), 0));

    if (_saveReplays)
    {
        _replayDir = "asset/replays/" + _name + "_" + _date;
        std::filesystem::create_directories(_replayDir);
        printf("Saving replays to: %s/\n", _replayDir.c_str());
    }

    printf("Tournament '%s': %zu rounds, %zu threads\n", _name.c_str(), _rounds, _numThreads);
    fflush(stdout);

    // Create per-thread self-play data sinks if enabled
    if (_selfPlayEnabled && NeuralNet::Instance().isLoaded())
    {
        // Append timestamped subdirectory so each run is independent (crash-safe)
        _selfPlayOutputDir += "run_" + startDate.str() + "/";
        std::filesystem::create_directories(_selfPlayOutputDir);
        _selfPlaySinks.resize(_numThreads);
        for (size_t i = 0; i < _numThreads; ++i)
        {
            _selfPlaySinks[i] = std::make_unique<SelfPlayDataSink>(
                (int)i, _selfPlayOutputDir, _selfPlayGameCounter,
                NeuralNet::Instance().stateDim());
        }
        fprintf(stderr, "[SelfPlay] Exporting to %s (%zu threads, feature_dim=%d)\n",
                _selfPlayOutputDir.c_str(), _numThreads, NeuralNet::Instance().stateDim());
        fflush(stderr);
    }
    else if (_selfPlayEnabled && !NeuralNet::Instance().isLoaded())
    {
        fprintf(stderr, "[SelfPlay] WARNING: SelfPlayDataExport enabled but neural net not loaded. Skipping export.\n");
        fflush(stderr);
        _selfPlayEnabled = false;
    }

    _timeElapsed.start();

    // Process rounds in batches of _numThreads
    // Generate random states per-batch (rand() is not thread-safe, but one batch at a time is fine)
    for (size_t batchStart = 0; batchStart < _rounds; batchStart += _numThreads)
    {
        size_t batchEnd = std::min(batchStart + _numThreads, _rounds);
        size_t batchSize = batchEnd - batchStart;

        // Generate random states for this batch only (avoids OOM from pre-allocating all rounds)
        std::vector<GameState> batchStates(batchSize);
        for (size_t i = 0; i < batchSize; ++i)
        {
            batchStates[i].setStartingState(Players::Player_One, _randomCards);
        }

        std::vector<std::thread> threads;
        for (size_t i = 0; i < batchSize; ++i)
        {
            IDataSink * sink = (_selfPlayEnabled && i < _selfPlaySinks.size())
                               ? _selfPlaySinks[i].get() : nullptr;
            threads.emplace_back(&Tournament::playRound, this, std::cref(batchStates[i]), sink);
        }

        for (auto & t : threads)
        {
            t.join();
        }

        // Print results after each batch
        {
            std::lock_guard<std::mutex> lock(_resultsMutex);
            printResults();
            writeHTMLResults();
            double elapsed = _timeElapsed.getElapsedTimeInMilliSec() / 1000.0;
            size_t gamesPlayed = _totalGamesPlayed.load();
            double gamesPerMin = elapsed > 0 ? (gamesPlayed * 60.0 / elapsed) : 0;
            fprintf(stderr, "[Progress] %zu / %zu rounds, %zu games completed (%.1f games/min)\n",
                    batchEnd, _rounds, gamesPlayed, gamesPerMin);
            fflush(stderr);
        }
    }

    // Finalize self-play sinks and report totals
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
        fprintf(stderr, "[SelfPlay] COMPLETE: %u games, %llu records written to %s\n",
                totalGames, (unsigned long long)totalRecords, _selfPlayOutputDir.c_str());
        fflush(stderr);
    }
}

void Tournament::playGame(TournamentGame & game)
{
    game.playGame();
    parseTournamentGameResult(game);

    _totalGamesPlayed++;
}

void Tournament::parseTournamentGameResult(const TournamentGame & game)
{
    int winnerID = game.getFinalGameState().winner();
    int loserID = (game.getFinalGameState().winner() + 1) % 2;

    int playerIndex[2] = {getPlayerIndex(game.getPlayerName(0)), getPlayerIndex(game.getPlayerName(1))};

    _maxTimeMS[playerIndex[0]] = std::max(_maxTimeMS[playerIndex[0]], (int)game.getMaxTimeMS(0));
    _maxTimeMS[playerIndex[1]] = std::max(_maxTimeMS[playerIndex[1]], (int)game.getMaxTimeMS(1));
    _totalTimeMS[playerIndex[0]] += game.getTotalTimeMS(0);
    _totalTimeMS[playerIndex[1]] += game.getTotalTimeMS(1);
    _totalGames[playerIndex[0]]++;
    _totalGames[playerIndex[1]]++;
    _numGames[playerIndex[0]][playerIndex[1]]++;
    _numGames[playerIndex[1]][playerIndex[0]]++;
    _totalTurns[playerIndex[0]] += game.getFinalGameState().getTurnNumber()/2;
    _totalTurns[playerIndex[1]] += game.getFinalGameState().getTurnNumber()/2;
    _turns[playerIndex[0]][playerIndex[1]] += game.getFinalGameState().getTurnNumber();
    _turns[playerIndex[1]][playerIndex[0]] += game.getFinalGameState().getTurnNumber();


    // case of a draw
    if (winnerID == Players::Player_None)
    {
        _draws[playerIndex[0]][playerIndex[1]]++;
        _draws[playerIndex[1]][playerIndex[0]]++;
        _totalDraws[playerIndex[0]]++;
        _totalDraws[playerIndex[1]]++;
    }
    else
    {
        // case of a non-draw
        int winnerIndex = playerIndex[winnerID];
        int loserIndex = playerIndex[loserID];

        _totalWins[winnerIndex]++;
        _wins[winnerIndex][loserIndex]++;
    }
}

#include "HTMLTable.h"
void Tournament::writeHTMLResults()
{
    std::string filename = "tests/Tournament_" + _name + "_" + _date + ".html";

    std::string assertLevel = "No Asserts";

#ifdef PRISMATA_ASSERT_NORMAL
    assertLevel = "Normal Asserts";
#endif

#ifdef PRISMATA_ASSERT_ALL
    assertLevel = "All Asserts";
#endif
    
    std::stringstream ss;
    double timeElapsed = _timeElapsed.getElapsedTimeInMilliSec();

    ss << "<table cellpadding=2 rules=all style=\"font: 12px/1.5em Verdana; border: 1px solid #cccccc;\">\n";
    ss << "<tr><td width=150><b>Tournament Name</b></td><td width=200 align=right>" << _name << "</td></tr>\n";
    ss << "<tr><td><b>Date Started</b></td><td align=right>" << _date << "</td></tr>\n";
    ss << "<tr><td><b>AI Compiled</b></td><td align=right>" << __DATE__ << " " __TIME__ << "</td></tr>";
    ss << "<tr><td><b>Assert Level</b></td><td align=right>" << assertLevel << "</td></tr>";
    ss << "<tr><td><b>Tournament Rounds</b></td><td align=right>" << _rounds << "</td></tr>\n";
    ss << "<tr><td><b>Time Elapsed</b></td><td align=right>" << getTimeStringFromMS(timeElapsed) << "</td></tr>\n";
    ss << "<tr><td><b>Games Played</b></td><td align=right>" << _totalGamesPlayed << " (" << (1000.0 * _totalGamesPlayed / timeElapsed) << "/s)</td></tr>\n";
    ss << "</table>\n<br><br>\n";

    FILE * f = fopen(filename.c_str(), "w");
    if (!f) return;
    fprintf(f, "<html>\n<head>\n");
    fprintf(f, "<script type=\"text/javascript\" src=\"javascript/jquery-1.10.2.min.js\"></script>\n<script type=\"text/javascript\" src=\"javascript/jquery.tablesorter.js\"></script>\n<link rel=\"stylesheet\" href=\"javascript/themes/blue/style.css\" type=\"text/css\" media=\"print, projection, screen\" />\n");
    fprintf(f, "</head>\n");
    fprintf(f, ss.str().c_str());
    fclose(f);

    HTMLTable stats("Overall Statistics");
    stats.setHeader({"Player", "Score", "Games", "Wins", "Loss", "Draw", "Turns", "Turns/G", "MS/Turn", "Max MS"});
    stats.setColWidth({120, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80});

    for (size_t p(0); p < _players.size(); ++p)
    {
        size_t col = 0;
        stats.setData(p, col++, _players[p]);
        stats.setData(p, col++, (_totalWins[p] + 0.5*_totalDraws[p])/_totalGames[p]);
        stats.setData(p, col++, _totalGames[p]);
        stats.setData(p, col++, _totalWins[p]);
        stats.setData(p, col++, _totalGames[p] - _totalWins[p] - _totalDraws[p]);
        stats.setData(p, col++, _totalDraws[p]);
        stats.setData(p, col++, _totalTurns[p]);
        stats.setData(p, col++, (double)_totalTurns[p] / _totalGames[p]);
        stats.setData(p, col++, (double)_totalTimeMS[p] / _totalTurns[p]);
        stats.setData(p, col++, _maxTimeMS[p]);
    }

    HTMLTable turnTable("Bot vs. Bot Avg Turns Per Game");
    HTMLTable tableWinPerc("Bot vs. Bot Score Table (row score vs. column)");
    std::vector<std::string> header = {""};
    header.insert(header.end(), _players.begin(), _players.end());
    header.push_back("Total");
    turnTable.setHeader(header);
    tableWinPerc.setHeader(header);
    
    std::vector<size_t> colWidth(header.size(), 120);
    turnTable.setColWidth(colWidth);
    tableWinPerc.setColWidth(colWidth);

    for (size_t r(0); r < _players.size(); ++r)
    {
        size_t col = 0;
        turnTable.setData(r, col, _players[r]);
        tableWinPerc.setData(r, col, _players[r]);
        col++;

        for (size_t p(0); p < _players.size(); ++p)
        {
            if (r == p)
            {
                turnTable.setData(r, col, "-");
                tableWinPerc.setData(r, col, "-");
            }
            else
            {
                turnTable.setData(r, col, _numGames[r][p] == 0 ? 0 : (double)_turns[r][p] / _numGames[r][p]);
                tableWinPerc.setData(r, col, _numGames[r][p] == 0 ? 0 : ((double)_wins[r][p] + 0.5*_draws[r][p]) / _numGames[r][p]);
            }

            col++;
        }

        turnTable.setData(r, col, _totalTurns[r]);
        tableWinPerc.setData(r, col, _totalGames[r] == 0 ? 0 : ((double)_totalWins[r] + 0.5*_totalDraws[r]) / _totalGames[r]);
        col++;
    }

    stats.appendHTMLTableToFile(filename, "statsTable");
    tableWinPerc.appendHTMLTableToFile(filename, "winPercentageTable");
    turnTable.appendHTMLTableToFile(filename, "totalScoreTable");
}

void Tournament::printResults() const
{
    std::stringstream ss;
  
    size_t colWidth = 10;
    for (size_t i(0); i < _players.size(); ++i)
    {
        colWidth = std::max(colWidth, _players[i].length() + 2);
    }

    ss << std::endl << std::endl;

    std::stringstream header;
    for (size_t i(0); i < _players.size(); ++i)
    {
        while (header.str().length() < (i+1)*colWidth) header << " ";
        header << _players[i];
    }

    header << "  TotalScore";

    std::cout << header.str() << std::endl;
    ss << header.str() << std::endl;

    for (size_t i(0); i < _players.size(); ++i)
    {
        std::stringstream line;
        line << _players[i]; while (line.str().length() < colWidth) line << " ";

        for (size_t j(0); j < _players.size(); ++j)
        {
            if (_playerGroups[i] != _playerGroups[j])
            {
                line << _wins[i][j] + (0.5*_draws[i][j]) ;
            }
            else
            {
                line << "-";
            }

            while (line.str().length() < colWidth + (j+1)*colWidth) line << " ";
        }

        line << _totalWins[i] + (0.5*_totalDraws[i]);
        line << std::endl;
        ss << line.str();
        std::cout << line.str();
    }
}

int Tournament::getPlayerIndex(const std::string & playerName) const
{
    for (size_t i(0); i < _players.size(); ++i)
    {
        if (_players[i].compare(playerName) == 0)
        {
            return i;
        }
    }

    return -1;
}


std::string Tournament::getTimeStringFromMS(const size_t ms)
{
    size_t totalSec = ms / 1000;

    size_t sec = totalSec % 60;
    size_t min = (totalSec / 60) % 60;
    size_t hour = (totalSec / 3600);

    std::stringstream ss;
    if (hour > 0)
    {
        ss << hour << "h ";
    }
    if (min > 0)
    {
        ss << min << "m ";
    }

    ss << sec << "s";
    return ss.str();
}