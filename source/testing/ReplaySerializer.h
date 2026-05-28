#pragma once

#include "Prismata.h"
#include "rapidjson/document.h"
#include "GameState.h"
#include "Move.h"
#include "Action.h"

namespace Prismata
{

// Accumulates snapshots over the course of a single game, then writes
// one .json.gz file in the matchup-format schema the PixiJS viewer eats.
//
// Lifetime: one instance per game. Owned by TournamentGame when enabled;
// not constructed at all when --save-replays is disabled (zero overhead).
//
// Hook flow: Task 16 wires Game::doAction's new ActionAppliedHook into
// captureActionApplied, so this object accumulates a snapshot after every
// action the real game state actually applies. The AI's search/playout
// copies of GameState never reach this object — captures are top-level
// observers only.
class ReplaySerializer
{
public:
    ReplaySerializer(const std::string & p0Name,
                     const std::string & p1Name,
                     const std::vector<std::string> & cardSet);

    // Capture the initial state (turn 0) before any move is applied.
    void captureInitialState(const GameState & state);

    // Called from Game::doAction's hook after each Action is applied to the
    // real (non-search-clone) GameState. Pushes a snapshot + action label.
    void captureActionApplied(const GameState & state, const Action & action);

    // Record a turn boundary in turnBoundaries[]. Called once per real turn
    // (after the player's Move is returned and timer has stopped, BEFORE the
    // per-action stream for that turn begins).
    void recordTurnBoundary();

    // Finalize: set winner + write `<dir>/game_<idx>.json.gz`.
    // Returns true on success, false if the file couldn't be written.
    bool finalize(int winner,
                  int turns,
                  const std::string & outDir,
                  int gameIndex);

private:
    std::string _p0;
    std::string _p1;
    std::vector<std::string> _cardSet;
    rapidjson::Document _doc;        // root document; states[] / actions[] / turnBoundaries[]
    rapidjson::Value _states;        // arrays owned by _doc
    rapidjson::Value _actions;
    rapidjson::Value _turnBoundaries;

    // Serialize one GameState to a JSON value (allocated in _doc.GetAllocator()).
    rapidjson::Value serializeState(const GameState & state);
};

} // namespace Prismata
