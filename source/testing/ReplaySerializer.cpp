#include "ReplaySerializer.h"
#include "CardType.h"
#include "CardBuyable.h"
#include "Resources.h"
#include <algorithm>

namespace Prismata
{

namespace
{
    const char * phaseToString(int phase)
    {
        switch (phase)
        {
            case Phases::Action:  return "action";
            case Phases::Defense: return "defense";
            case Phases::Breach:  return "breach";   // engine_v1 has Breach as a phase; renderer expects this string
            case Phases::Confirm: return "confirm";
            case Phases::Swoosh:  return "swoosh";
            default:              return "action";
        }
    }

    const char * roleToString(const Card & card)
    {
        // renderer expects: 'default' | 'assigned' | 'sellable' | 'inert'
        if (card.isSellable())                       return "sellable";
        if (card.getStatus() == CardStatus::Assigned) return "assigned";
        if (card.getStatus() == CardStatus::Inert)    return "inert";
        return "default";
    }

    const char * deadnessToString(const Card & card)
    {
        // Coarse mapping for now — renderer accepts richer reasons
        // ('selfsacced', 'sacced', 'blocked', 'meleed', 'breached', 'sniped',
        // 'autosniped', 'aged'), but engine_v1's m_causeOfDeath has no public
        // accessor. Task 17 can add one and map properly; for now alive/dead
        // is sufficient for the viewer to differentiate fading state.
        return card.isDead() ? "dead" : "alive";
    }

    // Helper: push a Value member with a heap-allocated string copy
    void addStr(rapidjson::Value & obj, const char * key, const std::string & s,
                rapidjson::Document::AllocatorType & a)
    {
        rapidjson::Value v(s.c_str(), static_cast<rapidjson::SizeType>(s.size()), a);
        obj.AddMember(rapidjson::StringRef(key), v, a);
    }

    void addStr(rapidjson::Value & obj, const char * key, const char * s,
                rapidjson::Document::AllocatorType & a)
    {
        rapidjson::Value v(s, a);
        obj.AddMember(rapidjson::StringRef(key), v, a);
    }
}

ReplaySerializer::ReplaySerializer(const std::string & p0Name,
                                   const std::string & p1Name,
                                   const std::vector<std::string> & cardSet)
    : _p0(p0Name), _p1(p1Name), _cardSet(cardSet)
{
    _doc.SetObject();
    _states.SetArray();
    _actions.SetArray();
    _turnBoundaries.SetArray();
}

rapidjson::Value ReplaySerializer::serializeState(const GameState & state)
{
    auto & a = _doc.GetAllocator();
    rapidjson::Value v(rapidjson::kObjectType);

    // ---- Mana / phase / turn ----
    addStr(v, "whiteMana", state.getResources(Players::Player_One).getString(), a);
    addStr(v, "blackMana", state.getResources(Players::Player_Two).getString(), a);
    v.AddMember("turn",     static_cast<int>(state.getActivePlayer()),      a);
    v.AddMember("numTurns", static_cast<int>(state.getTurnNumber()),        a);
    addStr(v, "phase", phaseToString(state.getActivePhase()), a);
    // engine_v1 represents breach as a distinct Phase (not a flag), so glassBroken
    // is true exactly when the active phase IS Breach. The renderer treats
    // (phase==='breach' || glassBroken) as the breach signal — emit both for clarity.
    v.AddMember("glassBroken", state.getActivePhase() == Phases::Breach, a);

    // ---- Supply arrays (buy panel) ----
    rapidjson::Value cards(rapidjson::kArrayType);
    rapidjson::Value whiteTotal(rapidjson::kArrayType);
    rapidjson::Value blackTotal(rapidjson::kArrayType);
    rapidjson::Value whiteSpent(rapidjson::kArrayType);
    rapidjson::Value blackSpent(rapidjson::kArrayType);

    const CardID numBuyable = state.numCardsBuyable();
    for (CardID i = 0; i < numBuyable; ++i)
    {
        const CardBuyable & cb = state.getCardBuyableByIndex(i);
        const CardType ct = cb.getType();

        rapidjson::Value name(ct.getUIName().c_str(), a);
        cards.PushBack(name, a);

        const int p0Max  = cb.getMaxSupply(Players::Player_One);
        const int p1Max  = cb.getMaxSupply(Players::Player_Two);
        const int p0Rem  = cb.getSupplyRemaining(Players::Player_One);
        const int p1Rem  = cb.getSupplyRemaining(Players::Player_Two);

        whiteTotal.PushBack(p0Max, a);
        blackTotal.PushBack(p1Max, a);
        whiteSpent.PushBack(std::max(0, p0Max - p0Rem), a);
        blackSpent.PushBack(std::max(0, p1Max - p1Rem), a);
    }
    v.AddMember("cards",            cards,      a);
    v.AddMember("whiteTotalSupply", whiteTotal, a);
    v.AddMember("blackTotalSupply", blackTotal, a);
    v.AddMember("whiteSupplySpent", whiteSpent, a);
    v.AddMember("blackSupplySpent", blackSpent, a);

    // ---- table[] (per-instance) ----
    rapidjson::Value table(rapidjson::kArrayType);
    // Iterate both players' alive cards, then killed cards (renderer's table
    // includes dead units until they're swept).
    for (PlayerID p = 0; p < 2; ++p)
    {
        const CardIDVector & alive  = state.getCardIDs(p);
        const CardIDVector & killed = state.getKilledCardIDs(p);

        auto emit = [&](const CardID id) {
            const Card & c = state.getCardByID(id);
            rapidjson::Value inst(rapidjson::kObjectType);
            inst.AddMember("instId",           static_cast<int>(c.getID()),        a);
            addStr(inst, "cardName",           c.getType().getUIName(),            a);
            inst.AddMember("owner",            static_cast<int>(c.getPlayer()),    a);
            inst.AddMember("health",           static_cast<int>(c.currentHealth()),a);
            inst.AddMember("damage",           static_cast<int>(c.getDamageTaken()),a);
            addStr(inst, "role",               roleToString(c),                    a);
            addStr(inst, "deadness",           deadnessToString(c),                a);
            inst.AddMember("constructionTime", static_cast<int>(c.getConstructionTime()), a);
            inst.AddMember("charge",           static_cast<int>(c.getCurrentCharges()),   a);
            inst.AddMember("delay",            static_cast<int>(c.getCurrentDelay()),     a);
            inst.AddMember("lifespan",         static_cast<int>(c.getCurrentLifespan()),  a);
            inst.AddMember("disruptDamage",    static_cast<int>(c.currentChill()),        a);
            inst.AddMember("blocking",         c.getStatus() == CardStatus::Assigned && c.canBlock(), a);
            // boughtThisPhase / bornThisTurn need engine-side tracking. Task 17
            // adds the creator-id-equivalent member to Card. Emit placeholders
            // for now so the JSON shape is contract-complete.
            inst.AddMember("boughtThisPhase",  false, a);
            inst.AddMember("bornThisTurn",     false, a);
            table.PushBack(inst, a);
        };

        for (size_t i = 0; i < alive.size();  ++i) emit(alive[i]);
        for (size_t i = 0; i < killed.size(); ++i) emit(killed[i]);
    }
    v.AddMember("table", table, a);

    // Derived fields (incomingAttack, maxAttack, gold estimates, ...) deferred
    // to Task 17 per the reconciliation table.

    return v;
}

void ReplaySerializer::captureInitialState(const GameState & state)
{
    auto & a = _doc.GetAllocator();
    _turnBoundaries.PushBack(0, a);
    _states.PushBack(serializeState(state), a);
    _actions.PushBack(rapidjson::Value("Start of game", a), a);
}

void ReplaySerializer::captureActionApplied(const GameState & state, const Action & action)
{
    auto & a = _doc.GetAllocator();
    _states.PushBack(serializeState(state), a);
    // Action::toHistoryString() — quick human label; mapping to richer
    // strings ('Buy Drone', 'Assign blocker', etc.) is renderer-side
    // cosmetics and can be improved in a follow-up.
    _actions.PushBack(rapidjson::Value(action.toHistoryString().c_str(), a), a);
}

void ReplaySerializer::recordTurnBoundary()
{
    auto & a = _doc.GetAllocator();
    _turnBoundaries.PushBack(static_cast<int>(_states.Size()), a);
}

bool ReplaySerializer::finalize(int /*winner*/, int /*turns*/,
                                const std::string & /*outDir*/, int /*gameIndex*/)
{
    // Filled in Task 18 (top-level wrapper + gzip + write).
    return false;
}

} // namespace Prismata
