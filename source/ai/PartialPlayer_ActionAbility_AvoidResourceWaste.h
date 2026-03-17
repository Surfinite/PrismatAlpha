#pragma once

#include "Common.h"
#include "PartialPlayer.h"

namespace Prismata
{

// Runs after all buys are committed. Asks: "I am about to end my turn,
// these resources will decay -- can I click to save the decay?"
//
// Two patterns handled:
//
//   CLICK candidates (ability costs decaying red, produces persistent gold):
//     e.g. Blood Phage: C -> 1G
//     Red will decay at end of turn anyway. Convert it to persistent gold.
//     Click if USE_ABILITY is legal.
//
//   UNDO candidates (ability costs persistent green, produced decaying blue):
//     e.g. Synthesizer: GGG -> BB
//     Blue will decay at end of turn. Recover the green by undoing the click.
//     Undo if UNDO_USE_ABILITY is legal (engine enforces that the blue hasn't
//     been spent -- if it has, the undo won't be legal).
//
// Should run LAST in BuySafeguardRoot, after AbilityAvoidAttackWaste.

class PartialPlayer_ActionAbility_AvoidResourceWaste : public PartialPlayer
{
    bool isClickCandidate(const CardType & type) const;
    bool isUndoCandidate(const CardType & type) const;

public:

    PartialPlayer_ActionAbility_AvoidResourceWaste(const PlayerID playerID);
    void getMove(GameState & state, Move & move);

    PPPtr clone() { return PPPtr(new PartialPlayer_ActionAbility_AvoidResourceWaste(*this)); }
};

}
