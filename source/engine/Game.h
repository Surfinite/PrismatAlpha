#pragma once

#include "Common.h"
#include "GameState.h"
#include "Player.h"
#include <functional>

namespace Prismata
{

class Game
{

    GameState   m_state;
    PlayerPtr   m_players[2];
    int         m_turnsPlayed    = 0;
    int         m_actions        = 0;
    TurnType    m_turnLimit      = 200;
    Move        m_previousMove;

    // Optional observer fired after every successful Action applied via
    // doAction(). Default null (zero overhead — one is-callable check per
    // real action). Used by ReplaySerializer to capture per-action snapshots
    // outside the AI's search/playout (which use throwaway GameState copies
    // and never go through Game::doAction).
    std::function<void(const GameState &, const Action &)> m_actionAppliedHook;

public:

    Game(const GameState & initialState, PlayerPtr p1, PlayerPtr p2);

    void                play();
    void                playNextTurn();
    bool                playNextTurn(bool assertOnEmptyMove);
    void                doMove(const Move & m, bool checkActionLegal = false);
    void                setTurnLimit(const TurnType limit);
    bool                doAction(const Action & action);
    bool                gameOver() const;
    int                 getTurnsPlayed();
    int                 getActions();
    PlayerPtr           getPlayerToMove();
    const GameState &   getState() const;
    const Move &        getPreviousMove() const;
    std::string         getWinnerString() const;
    const PlayerPtr     getPlayer(const PlayerID player) const;

    // Install a per-action observer. Empty function = disabled (default).
    void                setActionAppliedHook(std::function<void(const GameState &, const Action &)> hook)
                        { m_actionAppliedHook = std::move(hook); }
};


}
