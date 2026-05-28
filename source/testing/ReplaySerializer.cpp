#include "ReplaySerializer.h"
#include "CardType.h"
#include "CardBuyable.h"
#include "Resources.h"
#include "Script.h"
#include "ScriptEffect.h"
#include <algorithm>
#include <utility>
#include <initializer_list>
#include <fstream>
#include <filesystem>
#include <cstdio>
#include "rapidjson/writer.h"
#include "rapidjson/stringbuffer.h"
#include "miniz/miniz.h"

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

    // Wrap `data` as a standard gzip (.gz) stream: 10-byte gzip header + raw
    // DEFLATE body (miniz) + CRC32 + ISIZE footer. The browser's
    // DecompressionStream('gzip') in /replay/local reads this directly (it keys
    // on the 0x1f 0x8b magic). Returns empty on compression failure.
    std::string gzipCompress(const std::string & data)
    {
        size_t deflatedLen = 0;
        // window_bits = -15 => raw deflate (no zlib header); level 9; same params
        // miniz's own zip writer uses for stored entries.
        const mz_uint flags = tdefl_create_comp_flags_from_zip_params(9, -15, MZ_DEFAULT_STRATEGY);
        void * deflated = tdefl_compress_mem_to_heap(data.data(), data.size(), &deflatedLen, flags);
        if (!deflated) { return std::string(); }

        std::string out;
        out.reserve(deflatedLen + 18);

        const unsigned char header[10] = { 0x1f, 0x8b, 0x08, 0x00, 0, 0, 0, 0, 0x00, 0xff };
        out.append(reinterpret_cast<const char *>(header), 10);
        out.append(static_cast<const char *>(deflated), deflatedLen);
        mz_free(deflated);

        const mz_ulong crc = mz_crc32(MZ_CRC32_INIT,
                                      reinterpret_cast<const unsigned char *>(data.data()),
                                      data.size());
        auto appendLE = [&out](mz_uint32 v) {
            const char b[4] = { char(v & 0xff), char((v >> 8) & 0xff),
                                char((v >> 16) & 0xff), char((v >> 24) & 0xff) };
            out.append(b, 4);
        };
        appendLE(static_cast<mz_uint32>(crc));                       // CRC32 of uncompressed data
        appendLE(static_cast<mz_uint32>(data.size() & 0xffffffffu)); // ISIZE mod 2^32
        return out;
    }

    // ===================== Task 17: derived display fields =====================
    // Faithful port of js_engine/StateHelper.js (attack/chill/sniper potential) and
    // replay_exporter.js computeEconEstimate (gold range). Zero engine changes — all
    // values come from existing read-only accessors. Documented approximations:
    //   * snipers count ignores CardTypeInfo.potentiallyMoreAttack (not exposed via
    //     CardType) — only affects a "*" suffix on the attack number.
    //   * chargeGained is not exposed, treated as 0 in the ability-usable gate.
    //   * attack-resonate bonus (rare units, +1 attack) is not modelled.

    // gold a script's effect produces. NOTE: do NOT gate on Script::hasEffect() —
    // that is false for receive-only scripts (no create/destroy), which would drop
    // a Drone's {"receive":"1"} gold. getEffect().getReceive() is safe/empty on a
    // script without an effect (returns 0); callers gate on hasAbility()/hasBeginOwnTurnScript().
    int scriptMoney(const Script & s)
    {
        return static_cast<int>(s.getEffect().getReceive().amountOf(Resources::Gold));
    }

    // "active next turn" window StateHelper uses: built (or finishing), not delayed past
    // next turn, not doomed-this-turn, alive.
    bool inPotentialWindow(const Card & c)
    {
        if (c.isDead()) return false;
        if (c.getConstructionTime() > 1) return false;
        if (c.getCurrentDelay() > 1) return false;
        if (c.getCurrentLifespan() == 1 && c.getConstructionTime() == 0 && c.getCurrentDelay() == 0) return false;
        return true;
    }

    // ability usable next turn (health/charge gate).
    // Charge: only gate when the unit actually uses charges (Card.cpp:681 does the same);
    // otherwise chargeUsed is vestigial (e.g. Drone has chargeUsed=1 but usesCharges()==false).
    // Use startingCharge — beginTurn() refreshes m_currentCharges to it — so this models the
    // unit's charge at the start of the next turn rather than its (possibly tapped) current value.
    bool abilityUsable(const Card & c, const CardType & ct)
    {
        if (c.currentHealth() + ct.getHealthGained() < ct.getHealthUsed()) return false;
        if (ct.usesCharges() && ct.getStartingCharge() < ct.getChargeUsed()) return false;
        return true;
    }

    // count a player's in-window units of a given internal card name (resonate target)
    int countInWindowByName(const GameState & state, const PlayerID player, const std::string & name)
    {
        int n = 0;
        const CardIDVector & ids = state.getCardIDs(player);
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & c = state.getCardByID(ids[i]);
            if (inPotentialWindow(c) && c.getType().getName() == name) ++n;
        }
        return n;
    }

    // Resonate bonuses for a player: {gold, attack}. The engine parses both `resonate`
    // (1 attack/match, e.g. Antima Comet->Engineer) and `goldResonate` (1 gold/match,
    // e.g. Savior->Drone) into a beginOwnTurnScript resonate effect. Bonus per resonator
    // = receive * (# in-window units of the resonate target type), summed over resonators.
    std::pair<int, int> resonateBonus(const GameState & state, const PlayerID player)
    {
        int goldB = 0, atkB = 0;
        const CardIDVector & ids = state.getCardIDs(player);
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & c = state.getCardByID(ids[i]);
            if (!inPotentialWindow(c)) continue;
            const CardType & ct = c.getType();
            for (const Script * s : { &ct.getBeginOwnTurnScript(), &ct.getAbilityScript() })
            {
                if (!s->hasResonate()) continue;
                const ScriptEffect & re = s->getResonateEffect();
                const int g = static_cast<int>(re.getReceive().amountOf(Resources::Gold));
                const int a = static_cast<int>(re.getReceive().amountOf(Resources::Attack));
                if (g == 0 && a == 0) continue;
                const int targets = countInWindowByName(state, player, re.getResonateTypeName());
                goldB += g * targets;
                atkB  += a * targets;
            }
        }
        return std::make_pair(goldB, atkB);
    }

    struct Potential { int attack = 0; int disrupt = 0; int snipers = 0; };

    // What attack / chill / snipers `player` could produce next turn — symmetric look-ahead
    // used for both maxAttack* (turn player) and oppAttackPotential* (opponent).
    Potential computePotential(const GameState & state, const PlayerID player)
    {
        Potential p;
        const CardIDVector & ids = state.getCardIDs(player);
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & c = state.getCardByID(ids[i]);
            if (!inPotentialWindow(c)) continue;
            const CardType & ct = c.getType();

            p.attack += static_cast<int>(ct.getBeginTurnAttackAmount());   // begin-turn attack (always)

            if (abilityUsable(c, ct))
            {
                p.attack += static_cast<int>(ct.getAbilityAttackAmount()); // ability attack
                if (ct.hasTargetAbility())
                {
                    if (ct.getTargetAbilityType() == ActionTypes::CHILL)
                        p.disrupt += static_cast<int>(ct.getTargetAbilityAmount());
                    else if (ct.getTargetAbilityType() == ActionTypes::SNIPE)
                        ++p.snipers;   // approx (potentiallyMoreAttack not exposed)
                }
            }
        }
        p.attack += resonateBonus(state, player).second;   // e.g. Antima Comet: +1 attack per Engineer
        return p;
    }

    // [lowerBound, upperBound] gold for `player` at the start of their next turn (or this
    // turn during their own defense). Port of replay_exporter.js computeEconEstimate.
    std::pair<int, int> computeEconEstimate(const GameState & state, const PlayerID player)
    {
        int high = 0, low = 0;
        const CardIDVector & ids = state.getCardIDs(player);
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & c = state.getCardByID(ids[i]);
            if (!inPotentialWindow(c)) continue;
            const CardType & ct = c.getType();

            if (ct.hasBeginOwnTurnScript())                                // begin-turn money (both bounds)
            {
                const int btMoney = scriptMoney(ct.getBeginOwnTurnScript());
                high += btMoney; low += btMoney;
            }

            // ability money (upper; lower only if free). NOTE: no hasAbility() gate —
            // hasAbility() is false for economy units like Drone, which would drop their
            // {"receive":"1"} gold. getAbilityScript() is NullScript-safe (yields 0).
            if (abilityUsable(c, ct))
            {
                const Script & ab = ct.getAbilityScript();
                const int abMoney = scriptMoney(ab);
                high += abMoney;
                if (!ab.hasManaCost() && !ab.hasSacCost() && !ab.isSelfSac()) low += abMoney;
            }
        }

        const int goldReso = resonateBonus(state, player).first;          // e.g. Savior: +1 gold per Drone
        high += goldReso; low += goldReso;

        const int currentGold = static_cast<int>(state.getResources(player).amountOf(Resources::Gold));
        return std::make_pair(low + currentGold, high + currentGold);
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
            // lifespan: engine convention is 0 == "no lifespan", serialized as -1
            // (matches Card::toJSONString and the input parser; renderer treats -1 as infinite).
            inst.AddMember("lifespan",         static_cast<int>(c.getCurrentLifespan() == 0 ? -1 : c.getCurrentLifespan()), a);
            inst.AddMember("disruptDamage",    static_cast<int>(c.currentChill()),        a);
            // blocking: "currently in a blocking posture." Bare canBlock() — NOT
            // (status==Assigned && canBlock()), which is always false because canBlock()
            // returns getAssignedBlocking() (false for ordinary tapped blockers) once a
            // unit is Assigned. canBlock() reproduces the JS oracle's inst.blocking
            // (defaultBlocking for built/untapped/unfrozen units) and matches Card::toJSONString.
            inst.AddMember("blocking",         c.canBlock(), a);
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

    // ---- Derived display fields (Task 17) — midline attack/chill + gold estimates ----
    const PlayerID turnP = state.getActivePlayer();
    const PlayerID oppP  = state.getInactivePlayer();

    // incoming attack = the (inactive) opponent's committed attack aimed at the defender
    v.AddMember("incomingAttack",
                static_cast<int>(state.getResources(oppP).amountOf(Resources::Attack)), a);

    const Potential mine = computePotential(state, turnP);
    v.AddMember("maxAttack",  mine.attack,  a);
    v.AddMember("maxDisrupt", mine.disrupt, a);
    v.AddMember("maxSnipers", mine.snipers, a);

    const Potential opp = computePotential(state, oppP);
    v.AddMember("oppAttackPotential",  opp.attack,  a);
    v.AddMember("oppDisruptPotential", opp.disrupt, a);
    v.AddMember("oppSnipers",          opp.snipers, a);

    const std::pair<int, int> wEst = computeEconEstimate(state, Players::Player_One);
    rapidjson::Value wArr(rapidjson::kArrayType);
    wArr.PushBack(wEst.first, a); wArr.PushBack(wEst.second, a);
    v.AddMember("whiteGoldEstimate", wArr, a);

    const std::pair<int, int> bEst = computeEconEstimate(state, Players::Player_Two);
    rapidjson::Value bArr(rapidjson::kArrayType);
    bArr.PushBack(bEst.first, a); bArr.PushBack(bEst.second, a);
    v.AddMember("blackGoldEstimate", bArr, a);

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

bool ReplaySerializer::finalize(int winner, int turns,
                                const std::string & outDir, int gameIndex)
{
    auto & a = _doc.GetAllocator();

    // ---- Top-level wrapper (matchup-format schema the PixiJS viewer consumes) ----
    _doc.AddMember("replay", true, a);
    addStr(_doc, "p0", _p0, a);
    addStr(_doc, "p1", _p1, a);
    _doc.AddMember("winner", winner, a);             // 0 = white, 1 = black, -1 = draw
    const std::string winnerName = (winner == 0) ? _p0
                                 : (winner == 1) ? _p1
                                 : std::string("Draw");
    addStr(_doc, "winnerName", winnerName, a);
    _doc.AddMember("turns", turns, a);

    rapidjson::Value cardSet(rapidjson::kArrayType);   // random units in play (UINames)
    for (const std::string & name : _cardSet)
    {
        rapidjson::Value n(name.c_str(), static_cast<rapidjson::SizeType>(name.size()), a);
        cardSet.PushBack(n, a);
    }
    _doc.AddMember("cardSet", cardSet, a);

    // Move the accumulated arrays in (transfers ownership; safe — finalize runs once).
    _doc.AddMember("states", _states, a);
    _doc.AddMember("actions", _actions, a);
    _doc.AddMember("turnBoundaries", _turnBoundaries, a);

    // ---- Serialize the document to a JSON string ----
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    _doc.Accept(writer);

    // ---- gzip-compress (the viewer reads .json.gz via DecompressionStream) ----
    const std::string json(buffer.GetString(), buffer.GetSize());
    const std::string gz = gzipCompress(json);
    if (gz.empty()) { return false; }   // compression failed

    // ---- Write <outDir>/game_NNNN.json.gz ----
    std::error_code ec;
    std::filesystem::create_directories(outDir, ec);
    if (ec) { return false; }

    char filename[64];
    std::snprintf(filename, sizeof(filename), "game_%04d.json.gz", gameIndex);
    const std::string path = outDir + "/" + filename;

    std::ofstream out(path, std::ios::binary);
    if (!out) { return false; }
    out.write(gz.data(), static_cast<std::streamsize>(gz.size()));
    return out.good();
}

} // namespace Prismata
