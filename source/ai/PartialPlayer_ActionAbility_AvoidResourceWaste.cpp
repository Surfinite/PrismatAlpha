#include "PartialPlayer_ActionAbility_AvoidResourceWaste.h"

using namespace Prismata;

PartialPlayer_ActionAbility_AvoidResourceWaste::PartialPlayer_ActionAbility_AvoidResourceWaste(const PlayerID playerID)
{
    _playerID = playerID;
    _phaseID = PPPhases::ACTION_ABILITY;
}

// Ability costs decaying red, produces persistent gold.
// e.g. Blood Phage: C -> 1G
bool PartialPlayer_ActionAbility_AvoidResourceWaste::isClickCandidate(const CardType & type) const
{
    if (!type.hasAbility() || type.hasTargetAbility() || type.getAbilityScript().isSelfSac())
    {
        return false;
    }

    return type.getAbilityScript().getManaCost().amountOf(Resources::Red) > 0
        && type.getAbilityScript().getEffect().getReceive().amountOf(Resources::Gold) > 0;
}

// Ability costs persistent green, produced decaying blue.
// e.g. Synthesizer: GGG -> BB
bool PartialPlayer_ActionAbility_AvoidResourceWaste::isUndoCandidate(const CardType & type) const
{
    if (!type.hasAbility() || type.hasTargetAbility())
    {
        return false;
    }

    return type.getAbilityScript().getManaCost().amountOf(Resources::Green) > 0
        && type.getAbilityScript().getEffect().getReceive().amountOf(Resources::Blue) > 0;
}

void PartialPlayer_ActionAbility_AvoidResourceWaste::getMove(GameState & state, Move & move)
{
    PRISMATA_ASSERT(state.getActivePlayer() == _playerID, "GameState player does not match PartialPlayer player: %d != %d", (int)state.getActivePlayer(), (int)_playerID);

    if (state.getActivePhase() != Phases::Action)
    {
        return;
    }

    for (const auto & cardID : state.getCardIDs(_playerID))
    {
        const Card & card = state.getCardByID(cardID);
        const CardType & type = card.getType();

        // CLICK: red will decay, convert it to persistent gold
        if (isClickCandidate(type))
        {
            const Action doAbility(_playerID, ActionTypes::USE_ABILITY, card.getID());
            if (state.isLegal(doAbility))
            {
                state.doAction(doAbility);
                move.addAction(doAbility);
                fprintf(stderr, "[AvoidResourceWaste] Clicked %s: red -> gold\n", type.getUIName().c_str());
            }
        }

        // UNDO: blue will decay, recover the persistent green
        if (isUndoCandidate(type))
        {
            const Action undoAbility(_playerID, ActionTypes::UNDO_USE_ABILITY, card.getID());
            if (state.isLegal(undoAbility))
            {
                state.doAction(undoAbility);
                move.addAction(undoAbility);
                fprintf(stderr, "[AvoidResourceWaste] Undid %s: blue -> green\n", type.getUIName().c_str());
            }
        }
    }
}
