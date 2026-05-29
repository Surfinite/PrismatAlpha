#pragma once

#include "Prismata.h"
#include "rapidjson/document.h"
#include "GameState.h"
#include "Move.h"
#include "Action.h"

#include <unordered_map>
#include <unordered_set>

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

    // --- Synthetic monotonic instId remapping ---
    // Dave's engine recycles CardID slots when units die, so a single CardID can
    // refer to several different units over a game (~40% of slots in practice).
    // The PixiJS viewer assumes instIds are unique and increase with creation
    // order (JS uses a never-reused nextInstId++): it relies on that for the
    // pile "newest-sorts-left" tiebreak AND for pairing card sprites across
    // frames. We therefore map each *distinct* unit to a stable, ever-increasing
    // synthetic id. A slot is treated as a new unit when its CardID is seen for
    // the first time, when the occupant's identity (cardType+owner) changes, or
    // when the CardID was absent from the previous snapshot (swept then reused).
    int _nextInstId = 0;
    std::unordered_map<CardID, int> _synthId;        // CardID -> current synthetic instId
    std::unordered_map<CardID, int> _synthIdentity;  // CardID -> last-seen identity key
    std::unordered_set<CardID>      _presentLastState;

    // --- Freshness (bornThisTurn) tracking ---
    // A unit "came on the table this turn" should bunch left in the viewer.
    // Directly-bought units are detected by isSellable(); script-created units
    // (ability spawns AND begin-turn spawns) are NOT — and the engine omits
    // begin-turn creates from getCreatedCardIDs() (GameState.cpp:1043), so that
    // set can't be used. Instead: a non-initial unit that first appears NOT
    // sellable is a script creation; we tag it with its owner's turn index and
    // expire it at the owner's NEXT turn (mirroring the SWF resetting creatorId
    // at the owner's beginTurn). _ownerTurnSeq advances when the active player
    // changes; _synthBornOwnerSeq holds each born unit's owner-turn at creation.
    bool                       _initialDone = false;
    PlayerID                   _lastActivePlayer = Players::Player_None;
    int                        _ownerTurnSeq[2] = { 0, 0 };
    std::unordered_map<int, int> _synthBornOwnerSeq;  // synthetic id -> owner turn-seq at birth

    // Update the synthetic-id + freshness maps for the given state's cards (call
    // once per serialized snapshot, in temporal order, before reading _synthId).
    void updateSyntheticIds(const GameState & state);

    // Serialize one GameState to a JSON value (allocated in _doc.GetAllocator()).
    rapidjson::Value serializeState(const GameState & state);
};

} // namespace Prismata
