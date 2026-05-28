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

    // Optional replay capture. The serializer is constructed only when
    // setReplaySaveDir was called. Capture is done entirely here in the
    // tournament harness (see the per-action replay below) — Dave's engine
    // (Game / GameState) is unmodified, and nothing runs on the AI's
    // search/playout hot path. When disabled, none of this runs.
    if (!_replaySaveDir.empty())
    {
        std::vector<std::string> cardSet; // Task 18 may pre-populate this; empty is acceptable.
        _serializer = std::make_unique<ReplaySerializer>(_playerNames[0], _playerNames[1], cardSet);
        _serializer->captureInitialState(_game.getState());
    }

    while(!_game.gameOver())
    {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        // Snapshot the pre-move state when recording, so per-action frames can be
        // reconstructed off the think-timer below. Allocated only when recording;
        // this is per-turn (not per-search-node), so it is well off the AI hot path.
        std::unique_ptr<GameState> preMoveState;
        if (_serializer) { preMoveState = std::make_unique<GameState>(_game.getState()); }

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

        // Per-action replay capture, OFF the think-timer (ms already recorded
        // above). Re-apply the move that was just played onto a clone of the
        // pre-move state, emitting one snapshot per action. This reproduces
        // exactly the states the real game passed through — Game::doMove applies
        // the same actions via GameState::doAction — without any engine-side hook.
        // Order matches the schema: per-action states first, then the trailing
        // turn boundary (which points past the last action and is harmless for
        // the scrubber).
        if (_serializer)
        {
            const Move & move = _game.getPreviousMove();
            for (ActionID a(0); a < move.size(); ++a)
            {
                const Action & action = move.getAction(a);
                preMoveState->doAction(action);
                _serializer->captureActionApplied(*preMoveState, action);
            }
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
