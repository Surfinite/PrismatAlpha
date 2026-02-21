#include "ReplayStepper.h"
#include "../engine/Prismata.h"
#include "../ai/NeuralNet.h"
#include <algorithm>
#include <sstream>
#include <cstdio>
#include <unordered_set>

#define REPLAY_STEPPER_DEBUG

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
#ifdef REPLAY_STEPPER_DEBUG
            auto histIt = m_instIdHistory.find(it->second);
            std::string typeName = histIt != m_instIdHistory.end()
                ? histIt->second.cardType.getUIName() : "?";
            fprintf(stderr, "[ReplayStepper] Removing instId %d (CardID %d, %s) — card no longer live\n",
                    it->second, (int)cardId, typeName.c_str());
#endif
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

        // Record historical type info (append-only, never deleted)
        const Card & card = m_state.getCardByID(id);
        m_instIdHistory[m_nextInstId] = { card.getType(), card.getPlayer() };

#ifdef REPLAY_STEPPER_DEBUG
        fprintf(stderr, "[ReplayStepper] Mapped instId %d -> CardID %d (%s, P%d)\n",
                m_nextInstId, (int)id, card.getType().getUIName().c_str(), card.getPlayer());
#endif
        m_nextInstId++;
    }
}

CardID ReplayStepper::tryRecoverInstId(int instId)
{
    // If instId is ahead of our counter, the real game created cards we didn't.
    // Advance our counter to stay synchronized.
    if (instId >= m_nextInstId)
    {
        fprintf(stderr, "[ReplayStepper] Advancing instId counter from %d to %d\n",
                m_nextInstId, instId + 1);
        m_nextInstId = instId + 1;
    }

    // Look up the expected card type from history
    auto histIt = m_instIdHistory.find(instId);
    if (histIt == m_instIdHistory.end())
        return (CardID)-1;  // Never seen this instId

    CardType expectedType = histIt->second.cardType;
    PlayerID expectedPlayer = histIt->second.player;

    // Pass 1: Find a live card of the same type and player with no current instId mapping
    const CardIDVector & liveCards = m_state.getCardIDs(expectedPlayer);
    for (size_t i = 0; i < liveCards.size(); i++)
    {
        CardID candidateId = liveCards[i];
        const Card & card = m_state.getCardByID(candidateId);

        if (card.getType() != expectedType)
            continue;

        // Must not already be mapped
        if (m_cardIdToInstId.find(candidateId) != m_cardIdToInstId.end())
            continue;

        // Found a match — establish mapping
        m_instIdToCardId[instId] = candidateId;
        m_cardIdToInstId[candidateId] = instId;

        fprintf(stderr, "[ReplayStepper] Recovered instId %d -> CardID %d (%s, P%d)\n",
                instId, (int)candidateId, expectedType.getUIName().c_str(), expectedPlayer);

        return candidateId;
    }

    // Pass 2: Steal mapping from a mapped card of the same type.
    // Handles buySac mismatches: the engine sacrificed specific cards (by CardID)
    // but the real game sacrificed different cards of the same type. Total count
    // per type is correct, but specific instId<->CardID assignments differ.
    // We steal from the first mapped same-type card — its instId was likely
    // the one the real game sacrificed (so the client won't reference it again).
    for (size_t i = 0; i < liveCards.size(); i++)
    {
        CardID candidateId = liveCards[i];
        const Card & card = m_state.getCardByID(candidateId);

        if (card.getType() != expectedType)
            continue;

        auto oldIt = m_cardIdToInstId.find(candidateId);
        if (oldIt == m_cardIdToInstId.end())
            continue;

        int displacedInstId = oldIt->second;

        // Don't steal from the instId we're trying to recover (shouldn't happen, but guard)
        if (displacedInstId == instId)
            continue;

        // Steal: unmap the old instId, remap to the requested instId
        m_instIdToCardId.erase(displacedInstId);
        m_cardIdToInstId.erase(oldIt);

        m_instIdToCardId[instId] = candidateId;
        m_cardIdToInstId[candidateId] = instId;

        fprintf(stderr, "[ReplayStepper] Recovered instId %d -> CardID %d (%s, P%d) "
                "[displaced instId %d — likely killed in real game]\n",
                instId, (int)candidateId, expectedType.getUIName().c_str(), expectedPlayer,
                displacedInstId);

        return candidateId;
    }

    return (CardID)-1;  // No matching card found (type extinct?)
}

Action ReplayStepper::tryAlternativeActions(CardID cardId)
{
    const Card & card = m_state.getCardByID(cardId);
    PlayerID player = m_state.getActivePlayer();

    // Try safe action types for this click.
    // Only ASSIGN_BLOCKER and ASSIGN_BREACH are simple state changes.
    // USE_ABILITY/UNDO_USE_ABILITY can trigger complex side effects
    // (card destruction, scripts) that may assert even when isLegal passes.
    Action candidates[] = {
        Action(player, ActionTypes::ASSIGN_BLOCKER, cardId),
        Action(player, ActionTypes::ASSIGN_BREACH, cardId),
    };

    for (const Action & candidate : candidates)
    {
        if (m_state.isLegal(candidate))
        {
            fprintf(stderr, "[ReplayStepper] Fallback action type=%d for CardID %d at click %d\n",
                    (int)candidate.getType(), (int)cardId, m_clickIndex - 1);
            return candidate;
        }
    }

    return Action();  // No legal fallback
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
            // Try type-based recovery: find a live card of the same type
            CardID recovered = tryRecoverInstId(id);
            if (recovered != (CardID)-1)
            {
                it = m_instIdToCardId.find(id);  // Re-lookup after recovery
            }
            else
            {
                logError("Unknown instId " + std::to_string(id) + " at click " + std::to_string(m_clickIndex - 1)
                         + " (no recovery candidate)");
                return Action();
            }
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
            // Fix 4: Before giving up, try alternative actions for this card.
            // The click might work under a different phase interpretation.
            Action alt = tryAlternativeActions(action.getID());
            if (alt.getType() != ActionTypes::NONE && m_state.isLegal(alt))
            {
                // Save snapshot and apply the alternative action
                m_snapshots.resize(m_snapshotCursor + 1);
                m_snapshots.push_back(captureSnapshot());
                m_snapshotCursor = (int)m_snapshots.size() - 1;

                m_state.doAction(alt);
                updateInstIdMappings();
                m_appliedClicks++;

                if (m_state.isGameOver())
                {
                    m_gameOver = true;
                    return StepResult::GameOver;
                }
                return StepResult::OK;
            }

            // InstId resolved correctly (we got past clickToAction), but
            // no legal action found — server would silently reject this click
            isBenign = true;
        }

        if (isBenign)
        {
            m_benignSkips++;
            return StepResult::BenignSkip;
        }

        // Fix 2: Permissive END_PHASE during Defense.
        // When END_PHASE is illegal in Defense (attack != 0), the replay says defense is done.
        // Trust the replay: zero remaining attack and force-apply.
        if (action.getType() == ActionTypes::END_PHASE
            && m_state.getActivePhase() == Phases::Defense)
        {
            PlayerID player = m_state.getActivePlayer();
            PlayerID enemy = m_state.getEnemy(player);
            HealthType remainingAttack = m_state.getAttack(enemy);

            if (remainingAttack > 0)
            {
                fprintf(stderr, "[ReplayStepper] Force-ending Defense: absorbing %d attack at click %d\n",
                        (int)remainingAttack, m_clickIndex - 1);

                m_state.manuallySetAttack(enemy, 0);

                m_snapshots.resize(m_snapshotCursor + 1);
                m_snapshots.push_back(captureSnapshot());
                m_snapshotCursor = (int)m_snapshots.size() - 1;

                m_state.doAction(action);
                updateInstIdMappings();
                m_appliedClicks++;
                m_benignSkips++;

                if (m_state.isGameOver())
                {
                    m_gameOver = true;
                    return StepResult::GameOver;
                }
                return StepResult::OK;
            }
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

    // Record successful BUY before doAction (type info available from action)
    if (action.getType() == ActionTypes::BUY)
    {
        CardType cardType(action.getID());
        m_turnBuys.push_back(cardType.getUIName());
    }

#ifdef REPLAY_STEPPER_DEBUG
    {
        int liveP0 = (int)m_state.getCardIDs(0).size();
        int liveP1 = (int)m_state.getCardIDs(1).size();
        fprintf(stderr, "[ReplayStepper] APPLY click %d: actionType=%d actionId=%d phase=%d player=%d (live: P0=%d P1=%d)\n",
                m_clickIndex - 1, (int)action.getType(), (int)action.getID(),
                m_state.getActivePhase(), (int)m_state.getActivePlayer(), liveP0, liveP1);
    }
#endif

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

    // Clear buy tracking for this turn
    m_turnBuys.clear();

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
    // Allow up to 80% of clicks as skips (raised from 50% — with instId recovery,
    // remaining skips are more likely genuine server-rejected clicks).
    if (unknownInstIdSkipsThisTurn > 0 && unknownInstIdSkipsThisTurn > (clicksThisTurn * 4) / 5)
    {
        logError("Too many benign skips in turn " + std::to_string(m_turnIndex)
                 + ": " + std::to_string(unknownInstIdSkipsThisTurn) + "/" + std::to_string(clicksThisTurn));
        m_fatalErrors++;
        // Don't return FatalError — try next turn anyway
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

const std::vector<std::string> & ReplayStepper::getTurnBuys() const
{
    return m_turnBuys;
}

// --- Snapshot management ---

ReplayStepper::Snapshot ReplayStepper::captureSnapshot() const
{
    Snapshot snap;
    snap.state = m_state;
    snap.instIdToCardId = m_instIdToCardId;
    snap.cardIdToInstId = m_cardIdToInstId;
    snap.nextInstId = m_nextInstId;
    snap.turnBuys = m_turnBuys;
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
    m_turnBuys = snap.turnBuys;
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
