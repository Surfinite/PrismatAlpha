#include "ReplayStepper.h"
#include "../engine/Prismata.h"
#include "../ai/NeuralNet.h"
#include <algorithm>
#include <sstream>
#include <cstdio>
#include <unordered_set>

using namespace Prismata;

ReplayStepper::ReplayStepper()
    : m_clickIndex(0)
    , m_turnIndex(0)
    , m_gameOver(false)
    , m_commandList(nullptr)
    , m_nextInstId(0)
    , m_snapshotCursor(0)
    , m_appliedClicks(0)
    , m_benignSkips(0)
    , m_fatalErrors(0)
{
}

bool ReplayStepper::init(const rapidjson::Value & mergedDeck,
                          const rapidjson::Value & initInfo,
                          const rapidjson::Value & commandList,
                          const rapidjson::Value & clicksPerTurn,
                          const rapidjson::Value & playerInfo)
{
    // 1. Register card types from this game's deck (global state)
    Prismata::InitFromMergedDeckJSON(mergedDeck);
    if (NeuralNet::Instance().isLoaded())
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    // 2. Store command list reference
    m_commandList = &commandList;

    // 3. Parse clicksPerTurn into vector
    m_clicksPerTurn.clear();
    if (!clicksPerTurn.IsArray())
    {
        logError("clicksPerTurn is not an array");
        return false;
    }
    for (rapidjson::SizeType i = 0; i < clicksPerTurn.Size(); i++)
    {
        m_clicksPerTurn.push_back(clicksPerTurn[i].GetInt());
    }

    // 4. Initialize game state from mergedDeck + initInfo
    if (!initGameState(mergedDeck, initInfo))
    {
        return false;
    }

    // 5. Save initial snapshot (state before any clicks)
    m_snapshots.clear();
    m_snapshots.push_back(captureSnapshot());
    m_snapshotCursor = 0;

    return true;
}

bool ReplayStepper::initGameState(const rapidjson::Value & mergedDeck,
                                   const rapidjson::Value & initInfo)
{
    // 1. Empty default GameState
    m_state = GameState();

    // 2. Add buyable cards from mergedDeck
    //    InitFromMergedDeckJSON assigns CardType IDs starting at 2
    //    in mergedDeck array order. So mergedDeck[i] = CardType(i+2).
    for (rapidjson::SizeType i = 0; i < mergedDeck.Size(); i++)
    {
        CardType type(i + 2);
        m_state.addCardBuyable(type);
    }

    // 3. Add initial units from initCards
    //    Format: initCards[player] = [[count, name, ...attrs], ...]
    //    Client assigns instIds: P1 first, then P2, monotonic from 0
    if (!initInfo.HasMember("initCards") || !initInfo["initCards"].IsArray())
    {
        logError("initInfo missing initCards array");
        return false;
    }
    const auto & initCards = initInfo["initCards"];
    m_nextInstId = 0;

    for (int player = 0; player < 2; player++)
    {
        if (player >= (int)initCards.Size())
        {
            logError("initCards missing player " + std::to_string(player));
            return false;
        }
        const auto & playerCards = initCards[player];
        for (rapidjson::SizeType i = 0; i < playerCards.Size(); i++)
        {
            const auto & entry = playerCards[i];
            if (entry.Size() < 2)
            {
                logError("initCards entry too short");
                return false;
            }

            int count = entry[0].GetInt();
            const std::string cardName = entry[1].GetString();

            if (!CardTypes::CardTypeExists(cardName))
            {
                logError("Unknown card type in initCards: " + cardName);
                return false;
            }
            CardType type = CardTypes::GetCardType(cardName);

            // Parse optional attributes (delay, buildTime, lifespan, etc.)
            int delay = 0;
            int lifespan = 0;
            int buildTime = 0;
            for (rapidjson::SizeType k = 2; k + 1 < entry.Size(); k += 2)
            {
                if (!entry[k].IsString()) continue;
                std::string key = entry[k].GetString();
                if (key == "delay" && entry[k + 1].IsInt())
                    delay = entry[k + 1].GetInt();
                else if (key == "lifespan" && entry[k + 1].IsInt())
                    lifespan = entry[k + 1].GetInt();
                else if (key == "buildTime" && entry[k + 1].IsInt())
                    buildTime = entry[k + 1].GetInt();
            }

            int creationDelay = (buildTime > 0) ? buildTime : delay;

            for (int c = 0; c < count; c++)
            {
                m_state.addCard(player, type, 1, CardCreationMethod::Manual,
                                creationDelay, lifespan);
            }
        }

        // Assign instIds to all currently unmapped live cards.
        // After P1 pass: only P1 cards are unmapped -> assigned.
        // After P2 pass: P1 already mapped, only P2 cards -> assigned.
        updateInstIdMappings();
    }

    // 4. Set starting resources
    if (initInfo.HasMember("initResources") && initInfo["initResources"].IsArray())
    {
        const auto & initResources = initInfo["initResources"];
        if (initResources.Size() >= 2)
        {
            if (initResources[0].IsString())
            {
                std::string resStr = initResources[0].GetString();
                if (resStr != "0" && !resStr.empty())
                    m_state.setMana(Players::Player_One, Resources(resStr));
            }
            if (initResources[1].IsString())
            {
                std::string resStr = initResources[1].GetString();
                if (resStr != "0" && !resStr.empty())
                    m_state.setMana(Players::Player_Two, Resources(resStr));
            }
        }
    }

    // 5. Trigger initial turn setup
    //    beginTurn() is the public equivalent of beginPhase(Swoosh).
    //    It runs removeKilledCards, beginOwnTurnScript, then transitions to Action phase.
    m_state.beginTurn(Players::Player_One);

    // beginTurn may create cards (beginOwnTurnScript) -- track them
    updateInstIdMappings();

    return true;
}

void ReplayStepper::updateInstIdMappings()
{
    // Step 1: Collect all currently live CardIDs
    std::unordered_set<CardID> liveCardIds;
    for (int p = 0; p < 2; p++)
    {
        const CardIDVector & ids = m_state.getCardIDs(p);
        for (size_t i = 0; i < ids.size(); i++)
        {
            liveCardIds.insert(ids[i]);
        }
    }

    // Step 2: Remove mappings for cards no longer live
    //   (handles slot reuse: dead card's slot freed by removeKilledCards,
    //    then reused by a new card in the same doAction cascade)
    std::vector<CardID> toRemove;
    for (auto & pair : m_cardIdToInstId)
    {
        if (liveCardIds.find(pair.first) == liveCardIds.end())
            toRemove.push_back(pair.first);
    }

    for (CardID cardId : toRemove)
    {
        auto it = m_cardIdToInstId.find(cardId);
        if (it != m_cardIdToInstId.end())
        {
            m_instIdToCardId.erase(it->second);
            m_cardIdToInstId.erase(it);
        }
    }

    // Step 3: Find new live cards not yet mapped
    std::vector<CardID> newCards;
    for (int p = 0; p < 2; p++)
    {
        const CardIDVector & ids = m_state.getCardIDs(p);
        for (size_t i = 0; i < ids.size(); i++)
        {
            if (m_cardIdToInstId.find(ids[i]) == m_cardIdToInstId.end())
                newCards.push_back(ids[i]);
        }
    }

    // Step 4: Sort ascending by CardID (matches engine creation order
    //   because getFreeCardID returns lowest available slot, and cards
    //   are created sequentially within a doAction call)
    std::sort(newCards.begin(), newCards.end());

    // Step 5: Assign instIds in order
    for (CardID id : newCards)
    {
        m_cardIdToInstId[id] = m_nextInstId;
        m_instIdToCardId[m_nextInstId] = id;
        m_nextInstId++;
    }
}

Action ReplayStepper::clickToAction(const rapidjson::Value & click)
{
    if (!click.HasMember("_type") || !click.HasMember("_id"))
    {
        logError("Click missing _type or _id");
        return Action();
    }

    const std::string type = click["_type"].GetString();
    const int id = click["_id"].GetInt();
    const PlayerID player = m_state.getActivePlayer();

    // BUY clicks: card clicked / card shift clicked
    if (type == "card clicked" || type == "card shift clicked")
    {
        // mergedDeck[_id] -> CardType(id + 2)
        // BUY action ID is the CardType ID, not the buyable array index.
        // The engine's isLegal/doAction use getCardBuyableByID which searches by CardType ID.
        CardType cardType(id + 2);

        Action action(player, ActionTypes::BUY, cardType.getID());
        if (type == "card shift clicked")
            action.setShift(true);
        return action;
    }

    // END_PHASE clicks
    if (type == "space clicked")
    {
        return Action(player, ActionTypes::END_PHASE, 0);
    }

    // Instance clicks: inst clicked / inst shift clicked
    if (type == "inst clicked" || type == "inst shift clicked")
    {
        // Look up CardID from instId
        auto it = m_instIdToCardId.find(id);
        if (it == m_instIdToCardId.end())
        {
            // Unknown instId — card died in our engine but survives in real game (or vice versa).
            // Treat as benign skip with a tolerance limit. After too many, the state is
            // too desynchronized to extract useful data.
            logError("Unknown instId " + std::to_string(id) + " at click " + std::to_string(m_clickIndex - 1));
            return Action();  // Returns NONE, handled by caller as benign skip for inst clicks
        }

        CardID cardId = it->second;
        const Card & card = m_state.getCardByID(cardId);

        // Delegate to engine's authoritative click-to-action mapping
        Action action = m_state.getClickAction(card);

        if (type == "inst shift clicked")
            action.setShift(true);

        return action;
    }

    // revert/redo are handled in applyNextClick before clickToAction is called
    // If we somehow get here, it's an unrecognized click type
    logError("Unrecognized click type: " + type);
    return Action();
}

ReplayStepper::StepResult ReplayStepper::applyNextClick()
{
    if (!hasNextClick())
        return StepResult::GameOver;

    const auto & click = (*m_commandList)[m_clickIndex++];

    if (!click.HasMember("_type"))
    {
        logError("Click at index " + std::to_string(m_clickIndex - 1) + " missing _type");
        m_fatalErrors++;
        return StepResult::FatalError;
    }

    const std::string type = click["_type"].GetString();

    // Handle undo/redo via snapshots (not engine actions)
    if (type == "revert clicked" || type == "undo clicked")
    {
        if (m_snapshotCursor > 0)
        {
            m_snapshotCursor--;
            restoreSnapshot(m_snapshotCursor);
        }
        // else: can't undo past start — benign skip
        return StepResult::OK;
    }
    if (type == "redo clicked")
    {
        if (m_snapshotCursor + 1 < (int)m_snapshots.size())
        {
            m_snapshotCursor++;
            restoreSnapshot(m_snapshotCursor);
        }
        // else: nothing to redo — benign skip
        return StepResult::OK;
    }

    // UI-only events: blocker swipe begin/end, no engine action needed
    if (type == "end swipe processed" || type == "begin swipe processed")
    {
        return StepResult::OK;
    }

    // Emote clicks: in-game chat emotes (emoteGLHF!, emoteHeart, etc.)
    if (type.substr(0, 5) == "emote")
    {
        return StepResult::OK;
    }

    // Map click to engine action (delegates to getClickAction for inst clicks)
    Action action = clickToAction(click);
    if (action.getType() == ActionTypes::NONE)
    {
        // clickToAction returned NONE. For inst clicks this usually means unknown instId
        // (card died in our engine but still alive in real game). Treat as benign skip
        // since the click targets a card we can't resolve.
        if (type == "inst clicked" || type == "inst shift clicked")
        {
            m_benignSkips++;
            return StepResult::BenignSkip;
        }
        // For other click types, NONE is a genuine error
        m_fatalErrors++;
        return StepResult::FatalError;
    }

    // Check legality
    if (!m_state.isLegal(action))
    {
        // Cancel-targeting fallback: if target pending and inst click is
        // illegal as SNIPE/CHILL, try cancelling the targeting first
        if (m_state.isTargetAbilityCardClicked()
            && (action.getType() == ActionTypes::SNIPE
                || action.getType() == ActionTypes::CHILL))
        {
            const Card & targetCard = m_state.getTargetAbilityCardClicked();
            Action cancel(m_state.getActivePlayer(),
                          ActionTypes::UNDO_USE_ABILITY,
                          targetCard.getID());

            if (m_state.isLegal(cancel))
            {
                // Save snapshot before cancel
                m_snapshots.resize(m_snapshotCursor + 1);
                m_snapshots.push_back(captureSnapshot());
                m_snapshotCursor = (int)m_snapshots.size() - 1;

                m_state.doAction(cancel);
                // UNDO_USE_ABILITY when isTargetAbilityCardClicked() only
                // clears the flag, no card changes — updateInstIdMappings not needed

                // Re-interpret via getClickAction (targeting flag now cleared)
                int instId = click["_id"].GetInt();
                auto instIt = m_instIdToCardId.find(instId);
                if (instIt != m_instIdToCardId.end())
                {
                    const Card & card = m_state.getCardByID(instIt->second);
                    Action reinterp = m_state.getClickAction(card);
                    if (m_state.isLegal(reinterp))
                    {
                        action = reinterp;
                        // Fall through to apply below — snapshot already saved
                        m_state.doAction(action);
                        updateInstIdMappings();
                        m_appliedClicks++;

                        if (m_state.isGameOver())
                        {
                            m_gameOver = true;
                            return StepResult::GameOver;
                        }
                        return StepResult::OK;
                    }
                }

                // Click just cancelled targeting with no further effect
                m_benignSkips++;
                return StepResult::BenignSkip;
            }
        }

        // Benign skips: clicks the client recorded but server silently rejected.
        // BUY: sold-out supply, insufficient resources, double-click.
        // Inst clicks (USE_ABILITY, UNDO_USE_ABILITY, SELL, ASSIGN_BLOCKER, etc.):
        //   card is Inert, already used, can't block, etc. — server ignores.
        // These are NOT state desyncs — instId resolved correctly, the action
        // just isn't valid in the current game state.
        bool isBenign = false;
        if (action.getType() == ActionTypes::BUY)
        {
            isBenign = true;
        }
        else if (type == "inst clicked" || type == "inst shift clicked")
        {
            // InstId resolved correctly (we got past clickToAction), but
            // the action isn't legal — server would silently reject this click
            isBenign = true;
        }

        if (isBenign)
        {
            m_benignSkips++;
            return StepResult::BenignSkip;
        }

        // Fatal: END_PHASE desync or other unexpected illegal action
        std::ostringstream oss;
        oss << "Illegal action at click " << (m_clickIndex - 1)
            << ": actionType=" << (int)action.getType()
            << " actionId=" << (int)action.getID()
            << " phase=" << m_state.getActivePhase()
            << " player=" << (int)m_state.getActivePlayer()
            << " clickType=" << type
            << " clickId=" << click["_id"].GetInt();
        logError(oss.str());
        m_fatalErrors++;
        return StepResult::FatalError;
    }

    // Save PRE-action snapshot (for undo — restoring undoes this action)
    m_snapshots.resize(m_snapshotCursor + 1);  // truncate redo history
    m_snapshots.push_back(captureSnapshot());
    m_snapshotCursor = (int)m_snapshots.size() - 1;

    // Apply action
    m_state.doAction(action);
    updateInstIdMappings();

    m_appliedClicks++;

    if (m_state.isGameOver())
    {
        m_gameOver = true;
        return StepResult::GameOver;
    }

    return StepResult::OK;
}

ReplayStepper::StepResult ReplayStepper::advanceTurn()
{
    if (m_turnIndex >= (int)m_clicksPerTurn.size())
        return StepResult::GameOver;

    int clicksThisTurn = m_clicksPerTurn[m_turnIndex];
    int unknownInstIdSkipsThisTurn = 0;

    for (int i = 0; i < clicksThisTurn && hasNextClick(); i++)
    {
        StepResult result = applyNextClick();
        if (result == StepResult::FatalError)
            return result;
        if (result == StepResult::GameOver)
            return result;
        if (result == StepResult::BenignSkip)
            unknownInstIdSkipsThisTurn++;
    }

    // If most clicks in this turn were benign skips, state is severely desynced.
    // Allow up to half of clicks as skips before giving up.
    if (unknownInstIdSkipsThisTurn > 0 && unknownInstIdSkipsThisTurn > clicksThisTurn / 2)
    {
        logError("Too many benign skips in turn " + std::to_string(m_turnIndex)
                 + ": " + std::to_string(unknownInstIdSkipsThisTurn) + "/" + std::to_string(clicksThisTurn));
        m_fatalErrors++;
        return StepResult::FatalError;
    }

    m_turnIndex++;
    return StepResult::OK;
}

// --- State access ---

bool ReplayStepper::hasNextTurn() const
{
    return m_turnIndex < (int)m_clicksPerTurn.size() && !m_gameOver;
}

bool ReplayStepper::hasNextClick() const
{
    return m_commandList != nullptr
        && m_clickIndex < (int)m_commandList->Size()
        && !m_gameOver;
}

const GameState & ReplayStepper::getState() const
{
    return m_state;
}

int ReplayStepper::getCurrentTurn() const
{
    return m_turnIndex;
}

PlayerID ReplayStepper::getActivePlayer() const
{
    return m_state.getActivePlayer();
}

int ReplayStepper::getClickIndex() const
{
    return m_clickIndex;
}

bool ReplayStepper::isGameOver() const
{
    return m_gameOver;
}

int ReplayStepper::getTotalClicks() const
{
    return m_commandList ? (int)m_commandList->Size() : 0;
}

int ReplayStepper::getAppliedClicks() const
{
    return m_appliedClicks;
}

int ReplayStepper::getBenignSkips() const
{
    return m_benignSkips;
}

int ReplayStepper::getFatalErrors() const
{
    return m_fatalErrors;
}

int ReplayStepper::getTurnClickCount() const
{
    if (m_turnIndex < (int)m_clicksPerTurn.size())
        return m_clicksPerTurn[m_turnIndex];
    return 0;
}

const std::vector<std::string> & ReplayStepper::getErrors() const
{
    return m_errors;
}

// --- Snapshot management ---

ReplayStepper::Snapshot ReplayStepper::captureSnapshot() const
{
    Snapshot snap;
    snap.state = m_state;
    snap.instIdToCardId = m_instIdToCardId;
    snap.cardIdToInstId = m_cardIdToInstId;
    snap.nextInstId = m_nextInstId;
    return snap;
}

void ReplayStepper::restoreSnapshot(int cursor)
{
    if (cursor < 0 || cursor >= (int)m_snapshots.size())
        return;

    const Snapshot & snap = m_snapshots[cursor];
    m_state = snap.state;
    m_instIdToCardId = snap.instIdToCardId;
    m_cardIdToInstId = snap.cardIdToInstId;
    m_nextInstId = snap.nextInstId;
}

void ReplayStepper::saveSnapshot()
{
    m_snapshots.resize(m_snapshotCursor + 1);
    m_snapshots.push_back(captureSnapshot());
    m_snapshotCursor = (int)m_snapshots.size() - 1;
}

void ReplayStepper::logError(const std::string & msg)
{
    m_errors.push_back(msg);
    fprintf(stderr, "[ReplayStepper] %s\n", msg.c_str());
}
