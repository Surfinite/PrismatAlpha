#pragma once

namespace Prismata
{
    namespace Players
    {
        enum { Player_One = 0, Player_Two = 1, Player_Both = 2, Player_None = 3, Size}; 
    }
        
    namespace Phases
    {
        enum { Action, Defense, Breach, Confirm, Swoosh };
    }
    
    // used when parsing card library file, it lists thing by these names
    namespace SupplyAmount
    {
        enum { Unbuyable = 0, Legendary = 1, Rare = 4, Normal = 10, Trinket = 20 };
    }

    // used for converting AI engine moves back to the real game
    namespace ClickTypes
    {   
        enum { BeginSwipe = 2, EndSwipe = 3, Card = 5, Space = 10 };
    }

    namespace SearchMethods
    {
        enum { AlphaBeta, IDAlphaBeta, MiniMax, Size };
    }

    namespace EvaluationMethods
    {
        enum { Playout, WillScore, WillScoreInflation, NeuralNet, NeuralNetPlusPlayout, Size };
    }

    // Stagnation system — faithful port of AS3 State.as:76-100
    // 4-level no-progress counter system with cascading resets
    namespace Stagnation
    {
        const int NUM_LEVELS = 4;
        const int CUTOFFS[4] = {2, 8, 20, 40};

        // Level assignments for tracked events (AS3 State.as:1291-1349)
        const int LEVEL_DELAY_TICKED = 1;
        const int LEVEL_HP_HEALED_PAY_HP = 1;
        const int LEVEL_CHARGE_RECHARGED = 1;
        const int LEVEL_DAMAGE_MORE_THAN_HEALING = 1;
        const int LEVEL_MONEY_STORED = 2;
        const int LEVEL_CARD_BOUGHT = 3;
        const int LEVEL_BUILDTIME_TICKED = 3;
        const int LEVEL_OPP_LIFESPAN_TICKED = 3;
        const int LEVEL_GAS_STORED = 3;
        const int LEVEL_OPP_UNIT_COLLECTED = 4;
    }

    // Centralized stagnation event tracking — dispatches to correct reset function + level
    enum class ProgressEvent
    {
        DelayTicked,            // level 1, resets turn player
        HPHealedOnPayHP,        // level 1, resets turn player
        ChargeRecharged,        // level 1, resets turn player
        DamageMoreThanHealing,  // level 1, resets turn player
        MoneyStored,            // level 2, resets turn player
        CardBought,             // level 3, resets turn player
        BuildTimeTicked,        // level 3, resets turn player
        OppLifespanTicked,      // level 3, resets OPPONENT
        GasStored,              // level 3, resets turn player
        OppUnitCollected,       // level 4, resets turn player
    };

}