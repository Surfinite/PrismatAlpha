#include "TournamentGame.h"
#include "Timer.h"
#include "Eval.h"

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
    Timer t;
    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        t.start();
        _game.playNextTurn();
        double ms = t.getElapsedTimeInMilliSec();
        _playerTotalTimeMS[playerToMove] += ms;
        _maxTimeMS[playerToMove] = std::max((size_t)ms, _maxTimeMS[playerToMove]);
    }

    // Determine winner: natural game-over or WillScore adjudication
    _adjudicatedWinner = _game.getState().winner();

    // If turn limit reached without natural game-over, adjudicate by material
    if (_adjudicatedWinner == Players::Player_None && !_game.getState().isGameOver())
    {
        double scoreP0 = Eval::WillScoreSum(_game.getState(), Players::Player_One);
        double scoreP1 = Eval::WillScoreSum(_game.getState(), Players::Player_Two);

        double maxScore = std::max(scoreP0, scoreP1);
        double minScore = std::min(scoreP0, scoreP1);

        fprintf(stderr, "[TournamentGame] Turn limit reached. WillScore: P0=%.1f, P1=%.1f\n",
                scoreP0, scoreP1);

        if (maxScore >= (minScore + 0.01) * 1.3)
        {
            _adjudicatedWinner = (scoreP0 > scoreP1) ? Players::Player_One : Players::Player_Two;
            fprintf(stderr, "[TournamentGame] Material win for P%d (%.1f vs %.1f)\n",
                    (int)_adjudicatedWinner, scoreP0, scoreP1);
        }
        else
        {
            fprintf(stderr, "[TournamentGame] Material too close — draw (%.1f vs %.1f)\n",
                    scoreP0, scoreP1);
        }
    }
}

PlayerID TournamentGame::getWinner() const
{
    return _adjudicatedWinner;
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