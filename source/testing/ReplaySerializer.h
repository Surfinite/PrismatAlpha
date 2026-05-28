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
// Capture flow: TournamentGame drives this entirely from the harness. After
// each real turn completes (and the think-timer has stopped), it replays the
// just-played Move onto a clone of the pre-move GameState, calling
// captureActionApplied once per action. The engine (Game / GameState) is not
// modified, and the AI's search/playout copies never reach this object.
class ReplaySerializer
{
public:
    ReplaySerializer(const std::string & p0Name,
                     const std::string & p1Name,
                     const std::vector<std::string> & cardSet);

    // Capture the initial state (turn 0) before any move is applied.
    void captureInitialState(const GameState & state);

    // Called by TournamentGame once per action while replaying a completed
    // Move on a throwaway GameState clone. `state` is the clone after `action`
    // has been applied. Pushes a snapshot + action label.
    void captureActionApplied(const GameState & state, const Action & action);

    // Record a turn boundary in turnBoundaries[]. Called once per real turn,
    // AFTER that turn's per-action snapshots have been pushed (so the boundary
    // index points past the turn's last action).
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
