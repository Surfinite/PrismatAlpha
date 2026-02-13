#pragma once

#include "Common.h"
#include "PartialPlayer.h"

#include "Heuristics.h"
#include "BuyLimits.h"
#include "CardFilter.h"

namespace Prismata
{

class PartialPlayer_ActionBuy_GreedyKnapsack : public PartialPlayer
{
    EvaluationType          (*_heuristic)(const CardType, const GameState &, const PlayerID);
    CardFilter              _filter;
    Resources                    _beginTurnIncome;
    Resources                    _totalAbilityActivateCost;
    HealthType              _ourDefense;
    HealthType              _enemyChillPotential;
    HealthType              _enemyAttackPotential;
    std::vector<CardType>   _buyableTypes;
    bool                    _enemyWasChilled;
    bool                    _legacy;
    double                  _frontlinePenalty;

    void sortBuyables(const GameState & state);
    void updateStateData(const CardType cardTypeBought);
    void calculateStateData(const GameState & state);
    bool shouldNotBuy(const CardType cb, const GameState & state) const;
    bool canAffordToActivate(const CardType cb, const GameState & state) const;
    bool hasNonCumulativeManaCostAbility(const CardType type) const;

public:

    PartialPlayer_ActionBuy_GreedyKnapsack( const PlayerID playerID,
                                            const CardFilter & filter,
                                            EvaluationType (*heuristic)(const CardType, const GameState &, const PlayerID) = &Heuristics::BuyHighestCost,
                                            bool legacy = false);

    void getMove(GameState & state, Move & move);
    void addToBlacklist(const CardType type);
    PPPtr clone() { return PPPtr(new PartialPlayer_ActionBuy_GreedyKnapsack(*this));}
};

class BuyKnapsackCompare
{
    EvaluationType (*_heuristic)(const CardType, const GameState &, const PlayerID);
    const GameState & _state;
    const PlayerID _player;
    const HealthType _enemyAttackPotential;
    const double _frontlinePenalty;

public:

    BuyKnapsackCompare(EvaluationType (*heuristic)(const CardType, const GameState &, const PlayerID), const GameState & state, const PlayerID player, const HealthType enemyAttackPotential, double frontlinePenalty = 5.0)
        : _heuristic(heuristic)
        , _state(state)
        , _player(player)
        , _enemyAttackPotential(enemyAttackPotential)
        , _frontlinePenalty(frontlinePenalty)
    {
    }

    bool operator() (const CardType c1, const CardType c2) const;
};
}