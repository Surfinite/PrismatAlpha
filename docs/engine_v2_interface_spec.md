# Engine V2 Interface Specification

**Purpose**: Every symbol listed here is imported by `source/ai/` or `source/testing/`
from `source/engine/`. The new `source/engine_v2/` headers must expose the same
symbols to compile these layers with zero functional changes.

**How this was produced**: All `#include` directives in `source/ai/` and
`source/testing/` were audited. Every engine header discovered was read in full and
its public symbols transcribed.

**Namespace**: All symbols live in `namespace Prismata` unless noted otherwise.

---

## Table of Contents

1. [BaseTypes.hpp](#1-basetypeshpp)
2. [Constants.h](#2-constantsh)
3. [Common.h](#3-commonh)
4. [PrismataAssert.h](#4-prismataassert-h)
5. [Resources.h](#5-resourcesh)
6. [Action.h](#6-actionh)
7. [Move.h](#7-moveh)
8. [Player.h](#8-playerh)
9. [Condition.h](#9-conditionh)
10. [CreateDescription.h](#10-createdescriptionh)
11. [DestroyDescription.h](#11-destroydescriptionh)
12. [SacDescription.h](#12-sacdescriptionh)
13. [ScriptEffect.h](#13-scripteffecth)
14. [Script.h](#14-scripth)
15. [CardType.h + CardTypes namespace](#15-cardtypeh--cardtypes-namespace)
16. [CardTypes.h](#16-cardtypesh)
17. [CardBuyable.h](#17-cardbuyableh)
18. [CardBuyableData.h](#18-cardbuyabledatah)
19. [Card.h](#19-cardh)
20. [CardData.h](#20-carddatah)
21. [CardTypeInfo.h](#21-cardtypeinfoh)
22. [CardTypeData.h](#22-cardtypedatah)
23. [GameState.h](#23-gamestateh)
24. [Game.h](#24-gameh)
25. [GenericValue.h](#25-genericvalueh)
26. [Prismata.h](#26-pristamath)
27. [Timer.h](#27-timerh)
28. [FileUtils.h](#28-fileutilsh)
29. [JSONTools.h](#29-jsontoolsh)
30. [GraphViz.hpp](#30-graphvizhpp)
31. [Linux Portability Issues](#31-linux-portability-issues)

---

## 1. BaseTypes.hpp

**Callers**: Transitively included by every file via `Common.h`.

All primitive typedefs:

```cpp
namespace Prismata {
    typedef unsigned char   PlayerID;
    typedef unsigned char   ActionID;
    typedef size_t          CardID;
    typedef CardID          SupplyType;
    typedef unsigned short  ChargeType;
    typedef unsigned short  HealthType;
    typedef unsigned short  TurnType;
    typedef unsigned short  ResourceType;
    typedef double          EvaluationType;
    typedef double          UCTValue;
    typedef double          AlphaBetaValue;
    typedef double          StateEvalScore;
}
```

---

## 2. Constants.h

**Callers**: Transitively included by every file via `Common.h`.

```cpp
namespace Prismata {

    namespace Players {
        enum { Player_One = 0, Player_Two = 1, Player_Both = 2, Player_None = 3, Size };
    }

    namespace Phases {
        enum { Action, Defense, Breach, Confirm, Swoosh };
    }

    namespace SupplyAmount {
        enum { Unbuyable = 0, Legendary = 1, Rare = 4, Normal = 10, Trinket = 20 };
    }

    namespace ClickTypes {
        enum { BeginSwipe = 2, EndSwipe = 3, Card = 5, Space = 10 };
    }

    namespace SearchMethods {
        enum { AlphaBeta, IDAlphaBeta, MiniMax, Size };
    }

    namespace EvaluationMethods {
        enum { Playout, WillScore, WillScoreInflation, NeuralNet, NeuralNetPlusPlayout, Size };
    }

}
```

---

## 3. Common.h

**Purpose**: Umbrella header. Includes `BaseTypes.hpp`, `Constants.h`,
`PrismataAssert.h`, and standard library headers. Every engine and AI header
includes `Common.h` transitively.

**Required standard library includes pulled in by Common.h**:
`<vector>`, `<stdio.h>`, `<algorithm>`, `<ctime>`, `<memory>`, `<sstream>`,
`<limits>`, `<cstddef>`, `<string>`, `<iostream>`

---

## 4. PrismataAssert.h

**Callers**: Used in nearly every engine and AI `.cpp` file.

```cpp
namespace Prismata {
    namespace Assert {
        const std::string currentDateTime();
        void ReportFailure(const char * condition, const char * file,
                           int line, const char * msg, ...);
    }
}

// Macro (always enabled via PRISMATA_ASSERT_ALL):
#define PRISMATA_ASSERT(cond, msg, ...)  \
    do {                                  \
        if (!(cond)) {                    \
            Prismata::Assert::ReportFailure(#cond, __FILE__, __LINE__, (msg), ##__VA_ARGS__); \
        }                                 \
    } while(0)
```

**Behaviour note**: `ReportFailure` prints to **stdout** but does NOT abort.
This is a soft assert.

---

## 5. Resources.h

**Callers**: `Heuristics.cpp`, `Eval.cpp`, `PartialPlayer_ActionAbility_*`,
`PartialPlayer_ActionBuy_*`, `CardTypeInfo.h`, `Script.h`, `ScriptEffect.h`.

```cpp
namespace Prismata {

class Resources {
public:
    // Resource type indices
    enum { Gold = 0, Energy = 1, Blue = 2, Red = 3, Green = 4, Attack = 5,
           NumTypes = 6, Sac = 255 };

    Resources();
    Resources(const rapidjson::Value & value);
    Resources(const std::string & resourceString);
    Resources(ResourceType p, ResourceType h, ResourceType b,
              ResourceType c, ResourceType g, ResourceType a);

    bool operator==(const Resources & rhs) const;
    bool operator!=(const Resources & rhs) const;

    const ResourceType & amountOf(const size_t & resourceType) const;
    bool   has(const Resources & m) const;
    bool   empty() const;

    void   add(const size_t resourceType, const ResourceType val);
    void   add(const Resources & m);
    void   subtract(const size_t resourceType, const ResourceType val);
    void   subtract(const Resources & m);
    void   set(const size_t resourceType, const ResourceType val);
    void   set(const Resources & m);
    void   multiply(const ResourceType val);

    const std::string getString() const;
    const std::string getIntString() const;

    static char GetChar(size_t resourceIndex);
    static char GetCharReal(size_t resourceIndex);
};

}
```

**Dependency**: `rapidjson/rapidjson.h`, `rapidjson/document.h`

---

## 6. Action.h

**Callers**: `MoveIterator*.cpp`, `PartialPlayer_*.cpp`, `GameState.cpp`,
`UCTSearch.cpp`, `StackAlphaBetaSearch.cpp`.

```cpp
namespace Prismata {

namespace ActionTypes {
    enum {
        USE_ABILITY,
        BUY,
        END_PHASE,
        ASSIGN_BLOCKER,
        ASSIGN_BREACH,
        ASSIGN_FRONTLINE,
        SNIPE,
        CHILL,
        WIPEOUT,
        UNDO_USE_ABILITY,
        UNDO_CHILL,
        UNDO_BREACH,
        SELL,
        NUM_TYPES,
        NONE
    };
}

class Action {
public:
    Action();
    Action(const PlayerID player, const ActionID & actionType, const CardID id = 0);
    Action(const PlayerID player, const ActionID & actionType,
           const CardID id, const CardID target);

    void     setShift(bool shift);
    void     setID(const CardID id);
    bool     getShift() const;

    bool operator==(const Action & rhs) const;
    bool operator!=(const Action & rhs) const;

    ActionID    getType()     const;
    CardID      getID()       const;
    PlayerID    getPlayer()   const;
    CardID      getTargetID() const;

    std::string toString()             const;
    std::string toStringEnglish()      const;
    std::string toStringEnglishShort() const;
    std::string toClientString()       const;
    std::string toHistoryString()      const;
};

} // namespace Prismata
```

**Macro**: `MAX_MOVE_ACTIONS 512` (defined in Action.h)

---

## 7. Move.h

**Callers**: `UCTSearch.cpp`, `StackAlphaBetaSearch.cpp`, `Player*.cpp`,
`MoveIterator*.cpp`, `Game.h`, `GameState.h`, `PlayerBenchmark.h`.

```cpp
namespace Prismata {

class Move {
public:
    Move();

    bool operator==(const Move & rhs) const;
    bool memEquals(const Move & rhs) const;

    void          set(const Move & move);
    void          addAction(const Action & action);
    void          addMove(const Move & move);
    void          popAction();
    void          clear();

    const size_t     size() const;
    const Action &   getAction(const size_t index) const;
    const Action &   getLastAction() const;

    const std::string toString()       const;
    const std::string toClientString() const;
    const std::string toHistoryString() const;
};

} // namespace Prismata
```

---

## 8. Player.h

**Callers**: `Game.h`, `AIParameters.h`, `AllPlayers.h`, `Player_*.h`.

```cpp
namespace Prismata {

class Player;
typedef std::shared_ptr<Player> PlayerPtr;

class Player {
protected:
    PlayerID    m_playerID    = 0;
    std::string m_description = "Base Player";

public:
    virtual void        getMove(const GameState & state, Move & move);
    const int           ID();
    void                setID(const int playerid);
    virtual std::string getDescription();
    virtual void        setDescription(const std::string & desc);
    virtual PlayerPtr   clone();
};

} // namespace Prismata
```

---

## 9. Condition.h

**Callers**: `CardType.h`, `CardTypeInfo.h`, `DestroyDescription.h`,
`JSONTools.h`, `Card.h` (`meetsCondition`).

```cpp
namespace Prismata {

class Condition {
public:
    std::string    _cardName;
    mutable CardID _typeID;
    HealthType     _healthAtMost;
    bool           _isTech;
    bool           _notBlocking;
    bool           _hasHealthCondition;

    Condition();
    Condition(const rapidjson::Value & value);

    const std::string toString() const;
    const CardType    getType() const;
    const CardID      getTypeID() const;
    bool              isTech() const;
    bool              isNotBlocking() const;
    bool              hasCardType() const;
    bool              hasHealthCondition() const;
    const HealthType  getHealthAtMost() const;

    bool operator==(const Condition & rhs) const;
};

} // namespace Prismata
```

---

## 10. CreateDescription.h

**Callers**: `ScriptEffect.h`, `Script.h`, `CardTypeInfo.h`.

```cpp
namespace Prismata {

class CreateDescription {
public:
    std::string    _cardName;
    mutable CardID _typeID;
    CardID         _multiple;
    TurnType       _buildTime;
    TurnType       _lifespan;
    bool           _own;

    CreateDescription();
    CreateDescription(const std::string & cardName, bool bought);
    CreateDescription(const rapidjson::Value & value);

    const std::string toString() const;
    const std::string getCardName() const;
    const CardType    getType() const;
    const CardID      getTypeID() const;
    const CardID      getMultiple() const;
    bool              getOwn() const;
    const TurnType    getBuildTime() const;
    const TurnType    getLifespan() const;

    bool operator==(const CreateDescription & rhs) const;
};

} // namespace Prismata
```

---

## 11. DestroyDescription.h

**Callers**: `ScriptEffect.h`, `CardTypeInfo.h`, `GameState.h` (private methods).

```cpp
namespace Prismata {

class DestroyDescription {
public:
    std::string    _cardName;
    mutable CardID _typeID;
    CardID         _multiple;
    bool           _own;
    Condition      _condition;

    DestroyDescription();
    DestroyDescription(const rapidjson::Value & value);

    const std::string    toString() const;
    const CardType       getType() const;
    const CardID         getTypeID() const;
    const CardID         getMultiple() const;
    bool                 getOwn() const;
    const Condition &    getCondition() const;

    bool operator==(const DestroyDescription & rhs) const;
};

} // namespace Prismata
```

---

## 12. SacDescription.h

**Callers**: `Script.h`, `CardType.h`, `CardTypeInfo.h`, `JSONTools.h`,
`GameState.h` (private methods).

```cpp
namespace Prismata {

class SacDescription {
public:
    SacDescription();
    SacDescription(const rapidjson::Value & value);

    const CardID          getMultiple() const;
    const CardType        getType() const;
    const CardID          getTypeID() const;
    const std::string &   getCardName() const;

    bool operator==(const SacDescription & rhs) const;
};

} // namespace Prismata
```

---

## 13. ScriptEffect.h

**Callers**: `Script.h`, `CardTypeInfo.h`.

```cpp
namespace Prismata {

class ScriptEffect {
public:
    ScriptEffect();
    ScriptEffect(const rapidjson::Value & value);

    void addCreateEffect(const CreateDescription & create);

    bool operator==(const ScriptEffect & rhs) const;

    const int                               getAttackValue()      const;
    bool                                    hasEffect()           const;
    const CardID                            getResonateTypeID()   const;
    const CardType                          getResonateType()     const;
    const std::string &                     getResonateTypeName() const;
    const Resources &                       getGive()             const;
    const Resources &                       getReceive()          const;
    const std::vector<CreateDescription> &  getCreate()           const;
    const std::vector<DestroyDescription> & getDestroy()          const;

    static ScriptEffect ResonateEffect(const std::string & cardName,
                                        const Resources & receive);
};

} // namespace Prismata
```

---

## 14. Script.h

**Callers**: `CardType.h`, `CardTypeInfo.h`, `JSONTools.h`, `GameState.cpp`.

```cpp
namespace Prismata {

namespace ScriptTypes {
    enum { BuyScript, AbilityScript, BeginTurnScript, Size };
}

class Script {
public:
    static const Script NullScript;

    Script();
    Script(const rapidjson::Value & value);

    bool hasEffect()   const;
    bool hasManaCost() const;
    bool hasSacCost()  const;
    bool isSelfSac()   const;
    bool hasResonate() const;

    const TurnType                      getDelay()          const;
    const ScriptEffect &                getEffect()         const;
    const ScriptEffect &                getResonateEffect() const;
    const std::vector<SacDescription> & getSacCost()        const;
    const Resources &                   getManaCost()       const;
    const HealthType                    getHealthUsed()     const;

    bool operator==(const Script & rhs) const;

    void setEffect(const ScriptEffect & effect);
    void setResonateEffect(const ScriptEffect & effect);
    void setHealthUsed(const HealthType health);
    void setManaCost(const Resources & cost);
    void setSacCost(const std::vector<SacDescription> & sacCost);
    void setSelfSac(bool sac);
};

} // namespace Prismata
```

---

## 15. CardType.h + CardTypes namespace

**Callers**: Most AI files, `CardData.h`, `CardBuyable.h`, `GameState.h`,
`CardTypeInfo.h`, `GenericValue.h`, `Condition.h`, `CreateDescription.h`,
`DestroyDescription.h`, `SacDescription.h`.

```cpp
namespace Prismata {

namespace CardStatus {
    enum { Default, Assigned, Inert, NUM_STATUS };
}

class CardType {
public:
    CardType();
    CardType(const CardID id);
    CardType(const CardType & type);

    CardType & operator=(const CardType rhs);
    bool operator==(const CardType rhs) const;
    bool operator!=(const CardType rhs) const;
    bool operator< (const CardType rhs) const;

    // Identity
    CardID          getID()                     const;
    const std::string & getName()               const;
    const std::string & getUIName()             const;
    const std::string   getImageFileName()      const;
    const std::string & getDescription()        const;

    // Combat / stats
    HealthType      getAttack()                 const;
    HealthType      getAttackGivenToEnemy()     const;
    HealthType      getStartingHealth()         const;
    HealthType      getHealthGained()           const;
    HealthType      getHealthUsed()             const;
    HealthType      getHealthMax()              const;
    HealthType      getAbilityAttackAmount()    const;
    HealthType      getBeginTurnAttackAmount()  const;
    SupplyType      getSupply()                 const;
    TurnType        getLifespan()               const;
    TurnType        getConstructionTime()       const;
    const ChargeType  getStartingCharge()       const;
    const ChargeType  getChargeUsed()           const;
    int             getCustomHeuristicValue()   const;
    CardID          getTypeBuySacCost(const CardType type) const;

    // Scripts and abilities
    const Script &  getAbilityScript()          const;
    const Script &  getBeginOwnTurnScript()     const;
    const Script &  getBuyScript()              const;
    ActionID        getTargetAbilityType()      const;
    HealthType      getTargetAbilityAmount()    const;
    ActionID        getActionType()             const;
    const Condition & getTargetAbilityCondition() const;

    // Collections
    const std::vector<SacDescription> & getBuySac()         const;
    const std::vector<SacDescription> & getAbilitySac()     const;
    const std::vector<CardID> &         getResonateFromIDs() const;
    const std::vector<CardID> &         getResonateToIDs()   const;
    const Resources &                   getBuyCost()         const;
    const Resources &                   produces()           const;
    const Resources                     getCreatedUnitsManaProduced() const;

    // Boolean queries
    bool getDefaultBlocking()      const;
    bool getAssignedBlocking()     const;
    bool hasCustomHeuristicValue() const;
    bool hasTargetAbility()        const;
    bool hasAbility()              const;
    bool hasBeginOwnTurnScript()   const;
    bool usesCharges()             const;
    bool usesBuySac()              const;
    bool canBlock(bool assigned)   const;
    bool canProduce(int m)         const;
    bool isSpell()                 const;
    bool isTech()                  const;
    bool isFragile()               const;
    bool isFrontline()             const;
    bool isPromptBlocker()         const;
    bool isEconCard()              const;
    bool isBaseSet()               const;
    bool isAbilityHealthUserOnly() const;
};

// CardTypes free functions (also declared in CardTypes.h — same declaration)
namespace CardTypes {
    void ResetData();
    void Init();
    const std::vector<CardType> & GetAllCardTypes();
    const std::vector<CardType> & GetBaseSetCardTypes();
    const std::vector<CardType> & GetDominionCardTypes();
    CardType GetCardType(const std::string & name);
    bool CardTypeExists(const std::string & name);
    bool IsBaseSet(const CardType type);
    extern const CardType None;   // sentinel for "no card type"
}

} // namespace Prismata
```

---

## 16. CardTypes.h

Standalone header that re-declares the `CardTypes` namespace functions above.
Content is identical to the `CardTypes` block in section 15. AI files that
`#include "CardTypes.h"` get the same declarations.

---

## 17. CardBuyable.h

**Callers**: `CardData.h`, `GameState.h`, `PartialPlayer_ActionBuy_*.cpp`,
`MoveIterator_AllBuy.cpp`.

```cpp
namespace Prismata {

class CardBuyable {
public:
    CardBuyable();
    CardBuyable(const CardType type,
                const CardID p1MaxSupply, const CardID p2MaxSupply,
                const CardID p1Spent,    const CardID p2Spent);

    CardBuyable & operator=(const CardBuyable & rhs);
    bool          operator< (const CardBuyable & rhs) const;

    const CardType  getType()                                      const;
    SupplyType      getSupplyRemaining(const PlayerID player)      const;
    SupplyType      getMaxSupply(const PlayerID player)            const;
    bool            hasSupplyRemaining(const PlayerID player)      const;

    void            setSupplyRemaining(const PlayerID player, const SupplyType & amount);
    void            buyCard(const PlayerID player);
    void            sellCard(const PlayerID player);
};

} // namespace Prismata
```

---

## 18. CardBuyableData.h

**Callers**: `CardData.h` (embedded as `m_cardsBuyable`).

```cpp
namespace Prismata {

class CardBuyableData {
public:
    CardBuyableData();

    const CardBuyable & getCardBuyableByIndex(const CardID cardIndex) const;
          CardBuyable & getCardBuyableByIndex(const CardID cardIndex);
    const CardBuyable & getCardBuyableByID(const CardID cardID)       const;
          CardBuyable & getCardBuyableByID(const CardID cardID);
    const CardBuyable & getCardBuyableByType(const CardType type)     const;
          CardBuyable & getCardBuyableByType(const CardType type);

    const CardID size() const;

    void addCardBuyable(const CardBuyable & cardBuyable);
    void buyCardByID(const PlayerID player, const CardID cardID);
    void buyCardByIndex(const PlayerID player, const CardID cardIndex);
    void sellCardByID(const PlayerID player, const CardID cardID);
};

} // namespace Prismata
```

---

## 19. Card.h

**Callers**: `GameState.h`, `IsomorphicCardSet.h`, `PartialPlayer_Defense_*.cpp`,
`PartialPlayer_Breach_*.cpp`, `Eval.cpp`.

```cpp
namespace Prismata {

enum CardRoles { };   // empty enum — reserved

namespace CardCreationMethod {
    enum { Bought, BuyScript, AbilityScript, Manual };
}

namespace AliveStatus {
    enum { Alive, Dead, KilledThisTurn };
}

namespace CauseOfDeath {
    enum { None, SelfSac, SelfAbilityHealthCost, Sniped, BuySacCost,
           AbilitySacCost, Blocker, Breached, Lifespan, UndoCreate,
           Unknown, Deleted, NumCausesOfDeath };
}

namespace DamageSource {
    enum { Block, Breach, NumDamageSources };
}

class Card {
public:
    Card();
    Card(const std::string & jsonString);
    Card(const rapidjson::Value & cardValue);
    Card(const CardType type, const PlayerID player, const int & creationMethod,
         const TurnType delay, const TurnType lifespan);

    Card & operator=(const Card & rhs);
    bool   operator==(const Card & rhs) const;
    bool   operator< (const Card & rhs) const;

    // Getters
    const CardType  getType()               const;
    CardID          getID()                 const;
    CardID          getTargetID()           const;
    PlayerID        getPlayer()             const;
    HealthType      currentHealth()         const;
    HealthType      currentChill()          const;
    HealthType      getDamageTaken()        const;
    int             getAliveStatus()        const;
    ChargeType      getCurrentCharges()     const;
    TurnType        getConstructionTime()   const;
    TurnType        getCurrentLifespan()    const;
    TurnType        getCurrentDelay()       const;
    int             getStatus()             const;
    int             getClientInstId()       const;

    // Boolean queries
    bool canBlock()               const;
    bool isUnderConstruction()    const;
    bool isDead()                 const;
    bool canUseAbility()          const;
    bool canUndoUseAbility()      const;
    bool canRunBeginOwnTurnScript() const;
    bool canSac()                 const;
    bool isBreachable()           const;
    bool isDelayed()              const;
    bool meetsCondition(const Condition & condition) const;
    bool isIsomorphic(const Card & other) const;
    bool canBreachFor(const HealthType damage) const;
    bool isOverkillable()         const;
    bool canOverkillFor(const HealthType damage) const;
    bool canBeChilled()           const;
    bool canFrontlineFor(const HealthType damagee) const;
    bool canBlockOnly()           const;
    bool isSellable()             const;
    bool isInPlay()               const;
    bool isFrozen()               const;
    bool hasTarget()              const;
    bool selfKilled()             const;
    bool wasBreached()            const;
    bool abilityUsedThisTurn()    const;   // inline in header

    // Mutators (called by GameState internals — needed for engine_v2 impl)
    void setStatus(int status);
    void takeDamage(const HealthType amount, const int damageSource);
    void useAbility();
    void undoUseAbility();
    void runAbilityScript();
    void runBeginTurnScript();
    void beginTurn();
    void kill(const int causeOfDeath);
    void applyChill(const HealthType amount);
    void removeChill(const HealthType amount);
    void setID(const CardID id);
    void addKilledCardID(const CardID id);
    void addCreatedCardID(const CardID id);
    void undoKill();
    void endTurn();
    void setTargetID(const CardID targetID);
    void setInPlay(bool inPlay);
    void clearTarget();
    void undoBreach();

    const std::vector<CardID> & getKilledCardIDs()  const;
    const std::vector<CardID> & getCreatedCardIDs() const;

    const std::string toJSONString(bool formatted = false) const;
};

// Functor for std::find_if — matches cards isomorphic to a given card
class IsomorphicCardComparator {
public:
    IsomorphicCardComparator(const Card & card);
    bool operator()(const Card & c) const;
};

} // namespace Prismata
```

---

## 20. CardData.h

**Callers**: `GameState.h` (embedded as `m_cards`). Transitively used by all
code that calls `GameState::getCardIDs()`, `getCardByID()`, etc.

```cpp
namespace Prismata {

typedef std::vector<CardID> CardIDVector;
typedef std::vector<Card>   CardVector;

class CardData {
public:
    CardData();

    const Card & getCard(const PlayerID player, const CardID cardIndex)        const;
          Card & getCard(const PlayerID player, const CardID cardIndex);
    const Card & getCardByID(const CardID id)                                  const;
          Card & getCardByID(const CardID id);
    const Card & getKilledCard(const PlayerID player, const CardID cardIndex)  const;
          Card & getKilledCard(const PlayerID player, const CardID cardIndex);

    const CardID         numCards(const PlayerID player)                        const;
    const CardID         numKilledCards(const PlayerID player)                  const;
    const CardID         getCardTypeCount(const PlayerID player,
                                          const CardType type)                  const;
    const CardIDVector & getCardIDs(const PlayerID player)                      const;
    const CardIDVector & getKilledCardIDs(const PlayerID player)                const;
    const CardID         numCardsBuyable()                                       const;

    const CardBuyable & getCardBuyableByIndex(const CardID cardIndex)           const;
          CardBuyable & getCardBuyableByIndex(const CardID cardIndex);
    const CardBuyable & getCardBuyableByID(const CardID cardID)                 const;
          CardBuyable & getCardBuyableByID(const CardID cardID);
    const CardBuyable & getCardBuyableByType(const CardType type)               const;
          CardBuyable & getCardBuyableByType(const CardType type);

          Card &    addCard(const Card & card);
          Card &    buyCardByID(const PlayerID player, const CardID cardBuyableIndex);
    void            sellCardByID(const CardID cardID);
    void            addBuyableCardType(const CardType type);
    void            addBuyableCard(const CardBuyable & type);
    void            killCardByID(const CardID cardID, const int causeOfDeath);
    void            removeKilledCards();
    void            undoKill(const CardID cardID);
    void            removeLiveCardByID(const CardID cardID);
    void            removeKilledCardByID(const CardID cardID);
    void            validateUnitArrays();
    const size_t    getMemoryUsed() const;
};

} // namespace Prismata
```

**Typedefs exported**: `CardIDVector` and `CardVector` are used throughout the
AI layer (e.g. `GameState::getCardIDs()` returns `const CardIDVector &`).

---

## 21. CardTypeInfo.h

**Callers**: `CardTypeData.h` (stores a vector of them), `AIParameters.cpp`,
`Heuristics.cpp`.

```cpp
namespace Prismata {

class CardTypeInfo {
public:
    CardTypeInfo();
    CardTypeInfo(const int id, const std::string & name,
                 const rapidjson::Value & value);

    bool operator==(const CardTypeInfo & rhs) const;

    // Public data members (all directly accessible)
    std::string     cardName, description, rarity, uiName, uiShortName;
    std::string     resonateCardName, targetAction;
    CardID          typeID;
    HealthType      attack, startingHealth, healthUsed, healthGained, healthMax;
    HealthType      targetAmount, abilityAttackAmount, beginTurnAttackAmount;
    HealthType      attackGivenToEnemy;
    SupplyType      supply;
    TurnType        buildTime, lifespan;
    ChargeType      startingCharge;
    CardID          droneBuySacCost;
    EvaluationType  customHeuristicValue;
    ActionID        targetActionType;   // ActionTypes::NONE by default

    bool            assignedBlocking, defaultBlocking, frontline, fragile;
    bool            potentiallyMoreAttack, isTech, isSpell, hasAbility;
    bool            hasBeginOwnTurnScript, isEconCard, isBaseSet;
    bool            isAbilityHealthUserOnly, hasCustomHeuristicValue;

    Resources       buyCost, abilityCost, produces, resonateProduces;
    Script          abilityScript, buyScript, beginOwnTurnScript;
    ScriptEffect    abilityScriptEffect, buyScriptEffect, beginOwnTurnScriptEffect;
    Condition       targetAbilityCondition;

    mutable std::vector<SacDescription> buySac;
    mutable std::vector<SacDescription> abilitySac;
    std::vector<CardID>                 resonatesFromIDs;
    std::vector<CardID>                 resonatesToIDs;
};

} // namespace Prismata
```

---

## 22. CardTypeData.h

**Callers**: `Prismata.cpp` (init), `CardType.cpp` (look-ups), `AIParameters.cpp`.

```cpp
namespace Prismata {

class CardTypeData {
public:
    static CardTypeData & Instance();   // singleton accessor

    const CardTypeInfo & getCardTypeInfo(const CardID id);
    const CardTypeInfo & GetCardTypeInfoByName(const std::string & name);

    void   ProcessPostInit();
    void   ResetData();
    void   InitFromCardLibraryFile(const std::string & jsonGameStateCardData);
    void   InitFromMergedDeckJSON(const rapidjson::Value & mergedDeck);
    void   printCardTypeVariableNames();
    std::string getVariableName(const std::string & str);
    size_t numCardTypes();
};

} // namespace Prismata
```

---

## 23. GameState.h

**Callers**: Virtually every AI and testing file — the central type.

```cpp
namespace Prismata {

class GameState {
public:
    GameState();
    GameState(const rapidjson::Value & value);

    // Mutating operations
    bool doAction(const Action & action);
    bool doMove(const Move & move);
    void setStartingState(const PlayerID startPlayer, const CardID numDominionCards);
    void addCard(const PlayerID player, const CardType type, const size_t num,
                 const int creationMethod, const TurnType delay, const TurnType lifespan);
    void addCard(const Card & card);
    void addCardBuyable(const CardType type);
    void setMana(const PlayerID player, const Resources & resource);
    void killCardByID(const CardID cardID, const int causeOfDeath);
    void beginTurn(const PlayerID player);
    void manuallySetAttack(const PlayerID player, const HealthType attackAmount);
    void manuallySetMana(const PlayerID player, const Resources & resource);
    void generateLegalActions(std::vector<Action> & actions) const;

    // Boolean queries
    bool isLegal(const Action & action)                                   const;
    bool isGameOver()                                                     const;
    bool hasBreachableCard(const PlayerID player)                         const;
    bool canBreachEnemyCard(const PlayerID player)                        const;
    bool hasOverkillableCard(const PlayerID player)                       const;
    bool canOverkillEnemyCard(const PlayerID player)                      const;
    bool canRunScript(const PlayerID player, const Script & script)       const;
    bool canRunScriptUndo(const PlayerID player, const CardID card,
                          const Script & script)                          const;
    bool isIsomorphic(const GameState & other)                            const;
    bool isPlayerIsomorphic(const GameState & other,
                            const PlayerID player)                        const;
    bool isBuyable(const PlayerID player, const CardType type)            const;
    bool canBreachFrozenCard()                                             const;
    bool canWipeout(const PlayerID player)                                 const;
    bool isTargetAbilityCardClicked()                                      const;

    // Scalar accessors
    const CardID   numCardsOfType(const PlayerID player, const CardType type,
                                   bool requireActive = false)            const;
    const CardID   numCards(const PlayerID player)                        const;
    const CardID   numKilledCards(const PlayerID player)                  const;
    const CardID   numCompletedCardsOfType(const PlayerID player,
                                            const CardType type)          const;
    const CardID   numCardsBuyable()                                       const;
    const CardID   getLastCardBoughtID()                                   const;
    const CardID   getIsomorphicCardID(const Card & card)                  const;
    const TurnType getTurnNumber()                                         const;
    const PlayerID getActivePlayer()                                       const;
    const PlayerID getInactivePlayer()                                     const;
    const PlayerID getEnemy(const PlayerID player)                        const;
    const PlayerID winner()                                                const;
    const int      getActivePhase()                                        const;
    const HealthType getAttack(const PlayerID player)                     const;
    const HealthType getTotalAvailableDefense(const PlayerID player)      const;

    // Object accessors
    const Card &        getCardByID(const CardID id)                      const;
    const Card &        getTargetAbilityCardClicked()                      const;
    const CardBuyable & getCardBuyableByIndex(const CardID index)         const;
    const CardBuyable & getCardBuyableByID(const CardID cardID)           const;
    const CardBuyable & getCardBuyableByType(const CardType type)         const;
    const Resources &   getResources(const PlayerID player)               const;
    const CardIDVector & getCardIDs(const PlayerID player)                const;
    const CardIDVector & getKilledCardIDs(const PlayerID player)          const;
    Action              getClickAction(const Card & card)                  const;

    // Serialisation / diagnostics
    std::string      getStateString() const;
    std::string      toJSONString()   const;
    const size_t     getMemoryUsed()  const;
};

// Comparator used for ordering cards-to-destroy
// (sorts by: canBlock desc, delay asc, lifespan asc, charges asc,
//  health asc, chill desc, then ID asc)
class DestroyCardCompare {
public:
    DestroyCardCompare(const GameState & state);
    bool operator()(const CardID c1, const CardID c2) const;
};

} // namespace Prismata
```

---

## 24. Game.h

**Callers**: `PlayerBenchmark.h`, `Tournament.cpp`, `TournamentGame.cpp`.

```cpp
namespace Prismata {

class Game {
public:
    Game(const GameState & initialState, PlayerPtr p1, PlayerPtr p2);

    void                play();
    void                playNextTurn();
    void                doMove(const Move & m, bool checkActionLegal = false);
    void                setTurnLimit(const TurnType limit);
    bool                doAction(const Action & action);
    bool                gameOver()       const;
    int                 getTurnsPlayed();
    int                 getActions();
    PlayerPtr           getPlayerToMove();
    const GameState &   getState()       const;
    const Move &        getPreviousMove() const;
    std::string         getWinnerString() const;
    const PlayerPtr     getPlayer(const PlayerID player) const;
};

} // namespace Prismata
```

---

## 25. GenericValue.h

**Callers**: `CardFilterCondition.h` (uses `GenericValue` for condition parameter
evaluation), `CardFilter.cpp`.

```cpp
namespace Prismata {

// Value-type tag enum (file-scope, not inside a namespace)
enum { VAL_NONE, VAL_STRING, VAL_INT, VAL_BOOL, VAL_DOUBLE, VAL_VECTOR,
       VAL_OBJECT, VAL_CARDTYPE };

union genericValue_t {
    int    _i;
    double _d;
    bool   _b;
};

class GenericValue {
public:
    GenericValue();
    GenericValue(const rapidjson::Value & v);
    GenericValue(const int i);
    GenericValue(const double d);
    GenericValue(const std::string & str);
    GenericValue(bool b);
    GenericValue(const CardType type);
    GenericValue(const std::vector<GenericValue> & v);

    const size_t size() const;
    const GenericValue & operator[](const size_t & index) const;

    bool isCardType() const;
    bool isInt()      const;
    bool isDouble()   const;
    bool isBool()     const;
    bool isString()   const;
    bool isVector()   const;

    const CardType          getCardType() const;
    const int               getInt()      const;
    const double            getDouble()   const;
    bool                    getBool()     const;
    const std::string &     getString()   const;
    const std::vector<GenericValue> & getVector() const;
};

} // namespace Prismata
```

---

## 26. Prismata.h

**Callers**: `AIParameters.h`, `PrismataAI.h`, `source/testing/Benchmarks.h`,
`source/testing/Tournament.h`, `source/testing/TestingConfig.h`.

This is the umbrella init header. It includes: `Common.h`, `Player.h`, `Game.h`,
`GameState.h`, `CardType.h`, `Resources.h`, `CardTypeInfo.h`, `FileUtils.h`.

```cpp
namespace Prismata {

    extern std::string AIConfigFile;         // path set by InitFromCardLibrary
    extern bool        PRISMATA_INITIALIZED; // becomes true after init

    // Load card definitions from the bundled cardLibrary.jso file
    void InitFromCardLibrary(const std::string & jsonGameStateCardDataFile);

    // Load card definitions from a parsed mergedDeck JSON array
    // (used by the --suggest pipeline when receiving live game state)
    void InitFromMergedDeckJSON(const rapidjson::Value & mergedDeckArray);

    // Reset all static card-type data (called internally before re-init)
    void ResetData();

} // namespace Prismata
```

---

## 27. Timer.h

**Callers**: `UCTSearch.cpp`, `StackAlphaBetaSearch.cpp`, `AlphaBetaSearch.cpp`,
`PlayerBenchmark.cpp`, `Tournament.cpp`.

```cpp
namespace Prismata {

class Timer {
public:
    Timer();
    ~Timer();

    void   start();
    void   stop();

    double getElapsedTimeInMicroSec();
    double getElapsedTimeInMilliSec();
    double getElapsedTimeInSec();
    double getElapsedTime();   // same as getElapsedTimeInSec
};

} // namespace Prismata
```

**Platform guard in header**: `#ifdef WIN32` includes `<windows.h>` and uses
`LARGE_INTEGER`. Else includes `<sys/time.h>` and uses `timeval`.
The implementation in `Timer.cpp` also guards on `WIN32`.

---

## 28. FileUtils.h

**Callers**: `Prismata.h` (re-exported), `Benchmarks.cpp` (via `PrismataAI.h`).

```cpp
namespace Prismata {
namespace FileUtils {
    std::string ReadFile(const std::string & filename);
}
}
```

**Note**: `FileUtils::ReadFile` writes diagnostic output to `stdout`. AI code
that needs clean stdout (--suggest mode) redirects stdout to stderr before
calling this, then restores it afterwards.

---

## 29. JSONTools.h

**Callers**: `CardTypeInfo.h`, `CardTypeData.cpp`, `AIParameters.cpp`.

All functions share signature `(key, value, dest [, assertExists=false])`:

```cpp
namespace Prismata {
namespace JSONTools {

    template <class T>
    void ReadInt(const char * key, const rapidjson::Value & value,
                 T & dest, bool assertExists = false);

    void ReadIntBool(const char * key, const rapidjson::Value & value,
                     bool & dest, bool assertExists = false);
    void ReadBool(const char * key, const rapidjson::Value & value,
                  bool & dest, bool assertExists = false);
    void ReadDouble(const char * key, const rapidjson::Value & value,
                    double & dest, bool assertExists = false);
    void ReadString(const char * key, const rapidjson::Value & value,
                    std::string & dest, bool assertExists = false);
    void ReadMana(const char * key, const rapidjson::Value & value,
                  Resources & dest, bool assertExists = false);
    void ReadScript(const char * key, const rapidjson::Value & value,
                    Script & dest, bool assertExists = false);
    void ReadScriptEffect(const char * key, const rapidjson::Value & value,
                          ScriptEffect & dest, bool assertExists = false);
    void ReadCondition(const char * key, const rapidjson::Value & value,
                       Condition & dest, bool assertExists = false);
    void ReadSacDescription(const char * key, const rapidjson::Value & value,
                            std::vector<SacDescription> & dest,
                            bool assertExists = false);

} // namespace JSONTools
} // namespace Prismata
```

**Note**: `ReadInt` is a template defined inline in the header. All other
functions are declared here and defined in `JSONTools.cpp`.

---

## 30. GraphViz.hpp

**Callers**: `UCTSearch.cpp` (optional tree-dump), `StackAlphaBetaSearch.cpp`.

This is a self-contained utility header. Engine V2 can copy it verbatim.

```cpp
namespace Prismata {
namespace GraphViz {

class Property {
public:
    std::string prop, value;
    Property(std::string p, std::string val);
    void print(std::ofstream & out);
};

class Node {
public:
    std::vector<Property> props;
    std::string name;
    Node(std::string n);
    Node();
    void set(std::string p, std::string v);
    void print(std::ofstream & out);
};

class Edge {
public:
    std::pair<std::string, std::string> nodes;
    std::vector<Property> props;
    Edge(std::string n1, std::string n2);
    Edge(Node & n1, Node & n2);
    void set(std::string p, std::string v);
    void print(std::ofstream & out);
};

class Graph {
public:
    Graph(std::string n);
    void set(std::string p, std::string v);
    void addNode(Node & n);
    void addEdge(Edge & e);
    void print(std::ofstream & out);
    void printToFile(const std::string & filename);
};

} // namespace GraphViz
} // namespace Prismata
```

---

## 31. Linux Portability Issues

Files in `source/testing/` and `source/engine/` that contain Windows-only code
requiring `#ifdef` guards or POSIX replacements for Linux builds:

### source/testing/main.cpp

| Line(s) | Windows code | Linux replacement |
|---------|-------------|-------------------|
| 9–16 | `#ifdef _WIN32` block: `#include <process.h>`, `#include <io.h>`, `#define GETPID() _getpid()` | `#else` already provides `#include <unistd.h>`, `#define GETPID() getpid()` — **already guarded correctly** |
| 51–52 | `savedStdout = _dup(_fileno(stdout))` / `_dup2(...)` | Replace `_dup`→`dup`, `_dup2`→`dup2`, `_fileno`→`fileno` — **NOT yet guarded** |
| 96–97 | `_dup2(savedStdout, _fileno(stdout))` / `_close(savedStdout)` | `dup2(...)` / `close(...)` — **NOT yet guarded** |

### source/testing/Benchmarks.cpp

| Line(s) | Windows code | Linux replacement |
|---------|-------------|-------------------|
| 12–14 | `#ifdef _WIN32` / `#include <io.h>` | Already guarded |
| 234, 264 | `#ifdef _WIN32` blocks around `_dup`/`_dup2`/`_close` | Already guarded |

**Verdict**: `Benchmarks.cpp` is already correctly guarded. `main.cpp` lines
51–52 and 96–97 are missing `#ifdef _WIN32` guards around `_dup`/`_dup2`/
`_fileno`/`_close` — these will fail to compile on Linux.

### source/engine/Timer.h + Timer.cpp

Already fully guarded via `#ifdef WIN32` / `#else` blocks. No change needed.

---

## Summary: Include Path Requirements

The `source/engine_v2/` directory must be on the include path so that files
like `#include "GameState.h"` resolve correctly. The AI layer uses bare (no
path) includes throughout, relying on the project include path.

The following third-party headers are referenced from engine headers and must
remain available at the same relative paths:

- `rapidjson/rapidjson.h`
- `rapidjson/document.h`

These live in `source/rapidjson/` and are already on the project include path.

---

## Header Dependency Graph (summary)

```
Prismata.h
 └─ Common.h ─── BaseTypes.hpp, Constants.h, PrismataAssert.h
 └─ Player.h ─── GameState.h
 └─ Game.h
 └─ CardType.h ─ Script.h ─ ScriptEffect.h ─ CreateDescription.h
              │                             └ DestroyDescription.h ─ Condition.h
              │            └ SacDescription.h
              └─ Resources.h
 └─ CardTypeInfo.h ─ (all of CardType.h's deps + JSONTools.h)
 └─ FileUtils.h

GameState.h
 └─ CardData.h ─ Card.h ─ CardType.h
              └─ CardBuyableData.h ─ CardBuyable.h ─ CardType.h
 └─ Action.h
 └─ Move.h ─ Action.h
```
