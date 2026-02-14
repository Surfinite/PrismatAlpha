#pragma once
#include "../engine/GameState.h"

namespace Prismata
{

// Interface for receiving game events during tournament play.
// Default: no-op. SelfPlayDataSink writes binary training data.
class IDataSink
{
public:
    virtual ~IDataSink() = default;

    // Called at the start of each player's Action phase, BEFORE getMove().
    // state: the game state the AI is about to evaluate.
    virtual void onTurnStart(const GameState & state) {}

    // Called when the game ends.
    // winner: Players::Player_One (0), Player_Two (1), or Player_None (3) for draw.
    virtual void onGameEnd(PlayerID winner) {}

    // Called after all games for this sink are complete. Writes footer, flushes files.
    virtual void finalize() {}
};

}
