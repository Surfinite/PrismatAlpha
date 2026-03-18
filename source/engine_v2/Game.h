#pragma once

#include "Common.h"
#include "GameState.h"
#include "Player.h"

namespace Prismata
{
 
class Game
{    
    
    GameState   m_state;
    PlayerPtr   m_players[2];
    int         m_turnsPlayed    = 0;
    int         m_actions        = 0;
    // TODO: Port 4-level stagnation from JS State.js (thresholds [2,8,20,40]).
    // JS uses per-player progress counters at 4 levels, reset by different game events:
    //   Level 1: delay ticked, HP healed on pay-HP unit, charge recharged, damage > healing
    //   Level 2: money stored
    //   Level 3: card bought/created, buildtime ticked, opp lifespan ticked, green resource stored
    //   Level 4: opponent unit collected (killed via attack)
    // A player is stagnated when ANY level counter >= its threshold.
    // Current implementation uses flat 200-turn limit as a reasonable fallback.
    TurnType    m_turnLimit      = 200;
    Move        m_previousMove;

public:
    
    Game(const GameState & initialState, PlayerPtr p1, PlayerPtr p2);

    void                play();
    void                playNextTurn();
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
};


}