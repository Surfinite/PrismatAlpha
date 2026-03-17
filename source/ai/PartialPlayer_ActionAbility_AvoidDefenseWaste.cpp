#include "PartialPlayer_ActionAbility_AvoidDefenseWaste.h"
#include "AITools.h"

using namespace Prismata;

PartialPlayer_ActionAbility_AvoidDefenseWaste::PartialPlayer_ActionAbility_AvoidDefenseWaste(const PlayerID playerID)
{
    _playerID = playerID;
    _phaseID = PPPhases::ACTION_ABILITY;
    _undoCandidates.reserve(10);
}

// Check if a card type's ability creates a unit that is a lifespan-1 blocker.
// Generic: checks the create list for any created unit with lifespan > 0 and canBlock.
// Also requires HPUsed > 0 (the activation costs HP, so there's something to save).
bool PartialPlayer_ActionAbility_AvoidDefenseWaste::createsLifespan1Blocker(const CardType & type) const
{
    if (type.getHealthUsed() == 0)
    {
        return false;
    }

    const auto & creates = type.getAbilityScript().getEffect().getCreate();
    for (const auto & desc : creates)
    {
        if (!CardTypes::CardTypeExists(desc._cardName))
        {
            continue;
        }

        const CardType createdType = CardTypes::GetCardType(desc._cardName);
        if (createdType.getLifespan() == 1 && createdType.canBlock(false))
        {
            return true;
        }
    }

    return false;
}

// Check if the enemy has any unit with a chill ability (can freeze our blockers).
bool PartialPlayer_ActionAbility_AvoidDefenseWaste::enemyHasChillPotential(const GameState & state) const
{
    const PlayerID enemy = state.getEnemy(_playerID);

    for (const auto & cardID : state.getCardIDs(enemy))
    {
        const Card & card = state.getCardByID(cardID);
        const CardType type = card.getType();

        if (type.hasTargetAbility() && type.getTargetAbilityType() == ActionTypes::CHILL)
        {
            return true;
        }
    }

    return false;
}

// Check if the enemy has any unit whose attack amount is flexible (click-based).
// This includes:
//   - Units with click abilities that produce attack (Steelsplitter, etc.)
//   - Units with abilities that cost attack (Militia, Auride Core, etc.)
//   - Units with chill abilities (can freeze our blockers, changing effective damage)
bool PartialPlayer_ActionAbility_AvoidDefenseWaste::enemyHasFlexibleAttack(const GameState & state) const
{
    const PlayerID enemy = state.getEnemy(_playerID);

    for (const auto & cardID : state.getCardIDs(enemy))
    {
        const Card & card = state.getCardByID(cardID);
        const CardType type = card.getType();

        if (!type.hasAbility() && !type.hasTargetAbility())
        {
            continue;
        }

        // Click produces attack
        if (type.hasAbility() && type.getAbilityScript().getEffect().getAttackValue() > 0)
        {
            return true;
        }

        // Click costs attack (can convert attack to resources)
        if (type.hasAbility() && type.getAbilityScript().getManaCost().amountOf(Resources::Attack) > 0)
        {
            return true;
        }

        // Has chill (can freeze our blockers)
        if (type.hasTargetAbility() && type.getTargetAbilityType() == ActionTypes::CHILL)
        {
            return true;
        }
    }

    return false;
}

// Check if we have any 1-HP defenders that are NOT lifespan-1.
// If we do, a Barrier could potentially swap in for one, saving a permanent unit.
bool PartialPlayer_ActionAbility_AvoidDefenseWaste::hasSmallNonLifespan1Defenders(const GameState & state) const
{
    for (const auto & cardID : state.getCardIDs(_playerID))
    {
        const Card & card = state.getCardByID(cardID);

        if (!card.canBlock())
        {
            continue;
        }

        if (card.currentHealth() == 1 && card.getCurrentLifespan() != 1)
        {
            return true;
        }
    }

    return false;
}

void PartialPlayer_ActionAbility_AvoidDefenseWaste::getMove(GameState & state, Move & move)
{
    PRISMATA_ASSERT(state.getActivePlayer() == _playerID, "GameState player does not match PartialPlayer player: %d != %d", (int)state.getActivePlayer(), (int)_playerID);

    if (state.getActivePhase() != Phases::Action)
    {
        return;
    }

    // Find cards that were activated this turn and create lifespan-1 blockers.
    // These are candidates for undoing if the defense they provide is wasteful.
    _undoCandidates.clear();
    for (const auto & cardID : state.getCardIDs(_playerID))
    {
        const Card & card = state.getCardByID(cardID);
        const Action undoAbility(_playerID, ActionTypes::UNDO_USE_ABILITY, cardID);

        if (state.isLegal(undoAbility) && createsLifespan1Blocker(card.getType()))
        {
            _undoCandidates.push_back(cardID);
        }
    }

    if (_undoCandidates.empty())
    {
        return;
    }

    // Predict enemy's next turn attack
    GameState predictedState(state);
    AITools::PredictEnemyNextTurn(predictedState);
    const HealthType predictedEnemyAttack = predictedState.getAttack(state.getEnemy(_playerID));

    // If enemy has zero predicted attack, undo everything — no defense needed at all
    if (predictedEnemyAttack == 0)
    {
        for (const auto & cardID : _undoCandidates)
        {
            const Action undoAbility(_playerID, ActionTypes::UNDO_USE_ABILITY, cardID);
            if (state.isLegal(undoAbility))
            {
                state.doAction(undoAbility);
                move.addAction(undoAbility);
            }
        }
        return;
    }

    // Pre-compute enemy threat properties (only needs to be done once per turn).
    const bool enemyChill = enemyHasChillPotential(state);
    const bool flexibleEnemy = enemyHasFlexibleAttack(state);

    // Undo loop: try undoing one candidate at a time, re-checking each time
    // since undoing changes our defense totals.
    bool undidSomething = true;
    while (undidSomething)
    {
        undidSomething = false;

        for (size_t i = 0; i < _undoCandidates.size(); ++i)
        {
            const CardID cardID = _undoCandidates[i];
            const Action undoAbility(_playerID, ActionTypes::UNDO_USE_ABILITY, cardID);

            if (!state.isLegal(undoAbility))
            {
                continue;
            }

            // Calculate current defense metrics
            HealthType largestAbsorber = 0;
            HealthType lifespan1DefenseHP = 0;
            HealthType totalDefense = 0;

            for (const auto & defCardID : state.getCardIDs(_playerID))
            {
                const Card & defCard = state.getCardByID(defCardID);

                if (!defCard.canBlock())
                {
                    continue;
                }

                totalDefense += defCard.currentHealth();

                // Largest non-fragile absorber
                if (!defCard.getType().isFragile())
                {
                    largestAbsorber = std::max(largestAbsorber, defCard.currentHealth());
                }

                // Total HP of lifespan-1 blockers (expendable — dying this turn anyway)
                if (defCard.getCurrentLifespan() == 1)
                {
                    lifespan1DefenseHP += defCard.currentHealth();
                }
            }

            // Case 1: Damage is fully covered by absorber + expendable lifespan-1 defense.
            // The -1 is because the absorber survives with at least 1 HP.
            // Skip if enemy has chill — frozen blockers reduce effective defense.
            if (!enemyChill && predictedEnemyAttack <= largestAbsorber + lifespan1DefenseHP - 1)
            {
                state.doAction(undoAbility);
                move.addAction(undoAbility);
                _undoCandidates.erase(_undoCandidates.begin() + i);
                undidSomething = true;
                break;
            }

            // Case 2: Over-defended with non-granular defense and fixed enemy attack.
            // All three conditions must hold:
            //   (a) Enemy attack is fixed (no click attackers, no chill)
            //   (b) Still over-defended without this barrier: (totalDefense - 1) >= predictedEnemyAttack + 1
            //   (c) No 1-HP non-lifespan-1 defenders (barrier can't swap in to save one)
            if (!flexibleEnemy
                && (totalDefense - 1) >= (predictedEnemyAttack + 1)
                && !hasSmallNonLifespan1Defenders(state))
            {
                state.doAction(undoAbility);
                move.addAction(undoAbility);
                _undoCandidates.erase(_undoCandidates.begin() + i);
                undidSomething = true;
                break;
            }
        }
    }
}
