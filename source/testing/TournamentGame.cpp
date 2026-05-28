#include "TournamentGame.h"
#include "Timer.h"

#include <iostream>

using namespace Prismata;

TournamentGame::TournamentGame(const GameState & initialState, const std::string & p1name, PlayerPtr p1, const std::string & p2name, const PlayerPtr p2)
    : _game(initialState, p1, p2)
    , _discarded(false)
{
    _playerNames[0] = p1name;
    _playerNames[1] = p2name;
    _playerTotalTimeMS[0] = 0;
    _playerTotalTimeMS[1] = 0;
    _maxTimeMS[0] = 0;
    _maxTimeMS[1] = 0;
}

void TournamentGame::playGame(size_t updateIntervalSec)
{
    Timer t;
    Timer updateTimer;
    updateTimer.start();

    // Optional replay capture. The serializer + hook are installed only when
    // setReplaySaveDir was called. When disabled the hook stays empty so
    // Game::doAction's one is-callable check resolves to false immediately.
    if (!_replaySaveDir.empty())
    {
        std::vector<std::string> cardSet; // Task 18 may pre-populate this; empty is acceptable.
        _serializer = std::make_unique<ReplaySerializer>(_playerNames[0], _playerNames[1], cardSet);
        _serializer->captureInitialState(_game.getState());
        _game.setActionAppliedHook(
            [this](const GameState & s, const Action & a) { _serializer->captureActionApplied(s, a); }
        );
    }

    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        t.start();
        if (!_game.playNextTurn(false))
        {
            _discarded = true;
            _discardReason = "empty move from " + _playerNames[playerToMove] + " on turn " + std::to_string(_game.getState().getTurnNumber());
            // Serializer is dropped without finalize on discard.
            _serializer.reset();
            return;
        }

        double ms = t.getElapsedTimeInMilliSec();
        _playerTotalTimeMS[playerToMove] += ms;
        _maxTimeMS[playerToMove] = std::max((size_t)ms, _maxTimeMS[playerToMove]);

        // Record a turn boundary after each completed real turn. The trailing
        // boundary on the final turn points past the last action and is
        // harmless for the scrubber.
        if (_serializer)
        {
            _serializer->recordTurnBoundary();
        }

        if (updateIntervalSec > 0 && updateTimer.getElapsedTimeInSec() >= updateIntervalSec)
        {
            std::cout << "  Playing " << _playerNames[0] << " vs " << _playerNames[1]
                      << ", turn " << _game.getState().getTurnNumber() << std::endl;
            updateTimer.start();
        }
    }

    // Finalize at end of game. Task 18 implements the actual gzip + write.
    if (_serializer)
    {
        const GameState & finalState = _game.getState();
        const PlayerID w = finalState.winner();
        const int winnerInt = (w == Players::Player_One) ? 0
                            : (w == Players::Player_Two) ? 1
                            : -1; // draw / no winner
        const int turns = static_cast<int>(finalState.getTurnNumber());
        _serializer->finalize(winnerInt, turns, _replaySaveDir, _replayGameIndex);
        _serializer.reset();
    }
}

bool TournamentGame::wasDiscarded() const
{
    return _discarded;
}

const std::string & TournamentGame::getDiscardReason() const
{
    return _discardReason;
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
