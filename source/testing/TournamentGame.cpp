#include "TournamentGame.h"
#include "Timer.h"
#include "Action.h"
#include "CardType.h"

#include <fstream>

using namespace Prismata;

TournamentGame::TournamentGame(GameState & initialState, const std::string & p1name, PlayerPtr p1, const std::string & p2name, const PlayerPtr p2)
    : _game(initialState, p1, p2)
{
    _playerNames[0] = p1name;
    _playerNames[1] = p2name;
    _playerTotalTimeMS[0] = 0;
    _playerTotalTimeMS[1] = 0;
    _maxTimeMS[0] = 0;
    _maxTimeMS[1] = 0;
}

void TournamentGame::playGame()
{
    // Snapshot the initial state (before any moves)
    _stateSnapshots.push_back(_game.getState().toJSONString());

    Timer t;
    int turnNumber = 0;
    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        t.start();
        _game.playNextTurn();
        double ms = t.getElapsedTimeInMilliSec();
        _playerTotalTimeMS[playerToMove] += ms;
        _maxTimeMS[playerToMove] = std::max((size_t)ms, _maxTimeMS[playerToMove]);

        // Snapshot state after this turn
        _stateSnapshots.push_back(_game.getState().toJSONString());

        // Log buy actions with card names
        const Move & move = _game.getPreviousMove();
        std::string buys;
        for (size_t a = 0; a < move.size(); ++a)
        {
            const Action & action = move.getAction(a);
            if (action.getType() == ActionTypes::BUY)
            {
                if (!buys.empty()) buys += ", ";
                buys += CardType(action.getID()).getUIName();
            }
        }
        printf("  [T%d] %s: %s\n", turnNumber, _playerNames[playerToMove].c_str(), buys.empty() ? "(no buys)" : buys.c_str());
        fflush(stdout);
        turnNumber++;
    }
}

void TournamentGame::saveReplay(const std::string & filename) const
{
    std::ofstream file(filename);
    if (!file.is_open()) return;

    int winnerID = _game.getState().winner();
    std::string winnerName = (winnerID >= 0 && winnerID <= 1) ? _playerNames[winnerID] : "Draw";

    file << "{\n";
    file << "\"replay\": true,\n";
    file << "\"p0\": \"" << _playerNames[0] << "\",\n";
    file << "\"p1\": \"" << _playerNames[1] << "\",\n";
    file << "\"winner\": " << winnerID << ",\n";
    file << "\"winnerName\": \"" << winnerName << "\",\n";
    file << "\"turns\": " << _stateSnapshots.size() << ",\n";
    file << "\"states\": [\n";

    for (size_t i = 0; i < _stateSnapshots.size(); ++i)
    {
        file << _stateSnapshots[i];
        if (i < _stateSnapshots.size() - 1)
        {
            file << ",\n";
        }
    }

    file << "\n]\n}\n";
    file.close();
}

const std::string & TournamentGame::getPlayerName(const PlayerID player) const
{
    return _playerNames[player];
}

const GameState & TournamentGame::getFinalGameState() const
{
    return _game.getState();
}

const size_t TournamentGame::getTotalTimeMS(const PlayerID player) const
{
    return _playerTotalTimeMS[player];
}

const size_t TournamentGame::getMaxTimeMS(const PlayerID player) const
{
    return _maxTimeMS[player];
}
