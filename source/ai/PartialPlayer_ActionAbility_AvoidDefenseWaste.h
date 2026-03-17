#pragma once

#include "Common.h"
#include "PartialPlayer.h"

namespace Prismata
{

// Undoes HP-burning ability activations that created lifespan-1 defenders
// when those defenders are not needed for survival.
//
// Currently only fires for Asteri Cannon (burns 3 HP to create a Barrier
// with lifespan=1, blocking=1, toughness=1), but uses generic card property
// checks so it will work for any future unit with the same pattern.
//
// Two cases for undoing:
//   Case 1: predictedEnemyAttack <= largestAbsorber + totalLifespan1DefenseHP - 1
//           AND enemy has no chill (chill can freeze blockers, reducing effective defense)
//   Case 2: enemy attack is fixed (no click attackers, no chill) AND
//           we're over-defending (defense without barrier still >= attack + 1) AND
//           no 1-HP non-lifespan-1 defenders (barrier can't save one by swapping in)
//
// Should run LAST in the ActionAbility combination, after AvoidBreachSolver
// has bought prompt blockers and all defense decisions are finalized.

class PartialPlayer_ActionAbility_AvoidDefenseWaste : public PartialPlayer
{
    std::vector<CardID> _undoCandidates;

    bool createsLifespan1Blocker(const CardType & type) const;
    bool enemyHasChillPotential(const GameState & state) const;
    bool enemyHasFlexibleAttack(const GameState & state) const;
    bool hasSmallNonLifespan1Defenders(const GameState & state) const;

public:

    PartialPlayer_ActionAbility_AvoidDefenseWaste(const PlayerID playerID);
    void getMove(GameState & state, Move & move);

    PPPtr clone() { return PPPtr(new PartialPlayer_ActionAbility_AvoidDefenseWaste(*this)); }
};
}
