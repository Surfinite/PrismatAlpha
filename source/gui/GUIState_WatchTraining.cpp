#include "GUIState_WatchTraining.h"
#include "GUIEngine.h"
#include "GUITools.h"
#include "AITools.h"
#include "PrismataAI.h"
#include "Eval.h"
#include "Heuristics.h"
#include "NeuralNet.h"

#include <fstream>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <cmath>
#include <ctime>
#include <filesystem>

using namespace Prismata;

GUIState_WatchTraining::GUIState_WatchTraining(GUIEngine & game)
    : GUIState(game)
{
    m_playerName1 = "OriginalHardestAI_1s";
    m_playerName2 = "OriginalHardestAI_Copy_1s";
    m_exportTrainingData = true;
    m_modeName = "WATCH TRAINING";
    initCommon();
}

GUIState_WatchTraining::GUIState_WatchTraining(GUIEngine & game, const std::string & p1, const std::string & p2,
                                               bool exportData, const std::string & modeName)
    : GUIState(game)
{
    m_playerName1 = p1;
    m_playerName2 = p2;
    m_exportTrainingData = exportData;
    m_modeName = modeName;
    initCommon();
}

void GUIState_WatchTraining::initCommon()
{
    m_view.setWindowSize(Vec2(m_game.window().getSize().x, m_game.window().getSize().y));
    m_view.setView(m_game.window().getView());

    m_text.setFont(Assets::Instance().getFont("Consolas"));
    m_text.setPosition(10, 5);
    m_text.setCharacterSize(10);

    m_randomCards = 8;
    m_displayName1 = m_playerName1;
    m_displayName2 = m_playerName2;

    // Number of worker threads (4 total, matching x86 OOM limit)
    const int NUM_THREADS = 4;

    bool doExport = m_exportTrainingData && NeuralNet::Instance().isLoaded();

    if (doExport)
    {
        // Create timestamped output directory
        auto time = std::time(nullptr);
        auto tm = *std::localtime(&time);
        std::stringstream dateSS;
        dateSS << std::put_time(&tm, "%Y-%m-%d_%H-%M-%S");
        m_outputDir = "training/data/selfplay/run_" + dateSS.str() + "/";
        std::filesystem::create_directories(m_outputDir);

        // Create per-thread SelfPlayDataSinks
        uint32_t featureDim = NeuralNet::Instance().stateDim();
        m_sinks.resize(NUM_THREADS);
        for (int i = 0; i < NUM_THREADS; ++i)
        {
            m_sinks[i] = std::make_unique<SelfPlayDataSink>(i, m_outputDir, m_gameCounter, featureDim);
        }

        fprintf(stderr, "[%s] Starting %d worker threads, output: %s\n", m_modeName.c_str(), NUM_THREADS, m_outputDir.c_str());
    }
    else
    {
        if (m_exportTrainingData && !NeuralNet::Instance().isLoaded())
        {
            fprintf(stderr, "[%s] WARNING: Neural net not loaded. Training data will NOT be generated.\n", m_modeName.c_str());
        }
        fprintf(stderr, "[%s] Starting %d worker threads (no training data)\n", m_modeName.c_str(), NUM_THREADS);
    }

    // Thread 0 always gets a GUIObserverSink (pushes to display queue, optionally wraps training sink)
    SelfPlayDataSink * sink0 = (!m_sinks.empty() && m_sinks[0]) ? m_sinks[0].get() : nullptr;
    m_observerSink = std::make_unique<GUIObserverSink>(sink0, m_stateQueue);

    fflush(stderr);

    // Launch worker threads
    for (int i = 0; i < NUM_THREADS; ++i)
    {
        IDataSink * sink = nullptr;
        if (m_observerSink && i == 0)
            sink = static_cast<IDataSink *>(m_observerSink.get());
        else if (i < (int)m_sinks.size() && m_sinks[i])
            sink = static_cast<IDataSink *>(m_sinks[i].get());
        m_workerThreads.emplace_back(&GUIState_WatchTraining::workerThread, this, i, sink);
    }
}

GUIState_WatchTraining::~GUIState_WatchTraining()
{
    m_stopRequested = true;
    for (auto & t : m_workerThreads)
    {
        if (t.joinable()) t.join();
    }

    // Finalize sinks (writes CRC footer, etc.)
    uint64_t totalRecords = 0;
    uint32_t totalGames = 0;
    for (auto & sink : m_sinks)
    {
        if (sink)
        {
            sink->finalize();
            totalRecords += sink->totalRecordsWritten();
            totalGames += sink->totalGamesCompleted();
        }
    }

    fprintf(stderr, "[%s] STOPPED: %u games, %llu records written to %s\n",
            m_modeName.c_str(), totalGames, (unsigned long long)totalRecords, m_outputDir.c_str());
    fflush(stderr);
}

void GUIState_WatchTraining::workerThread(int threadIndex, IDataSink * sink)
{
    while (!m_stopRequested)
    {
        // Generate a random starting state
        // Play twice with swapped sides for eval (different AIs); once for self-play (same AI)
        GameState state;
        state.setStartingState(Players::Player_One, m_randomCards);
        int passes = (m_playerName1 == m_playerName2) ? 1 : 2;

        for (int colorPass = 0; colorPass < passes && !m_stopRequested; ++colorPass)
        {
            bool swapped = (colorPass == 1);
            const std::string & name1 = swapped ? m_playerName2 : m_playerName1;
            const std::string & name2 = swapped ? m_playerName1 : m_playerName2;

            // Tell the GUI which names are on which side (thread 0 only)
            if (threadIndex == 0)
            {
                m_displaySwapped.store(swapped);
            }

            PlayerPtr p1 = AIParameters::Instance().getPlayer(Players::Player_One, name1);
            PlayerPtr p2 = AIParameters::Instance().getPlayer(Players::Player_Two, name2);

            // Play the game using the same pattern as TournamentGame::playGame()
            Game game(state, p1, p2);

            while (!game.gameOver() && !m_stopRequested)
            {
                if (sink)
                {
                    sink->onTurnStart(game.getState());
                }

                game.playNextTurn();
            }

            if (sink && !m_stopRequested)
            {
                sink->onGameEnd(game.getState().winner());
            }
        }
    }
}

void GUIState_WatchTraining::pollQueue()
{
    GameState state;
    while (m_stateQueue.tryPop(state))
    {
        // Check if this state indicates a new game (turn 0 after we had states)
        if (!m_stateHistory.empty() && state.getTurnNumber() == 0)
        {
            // New game starting - record end of previous game
            m_gamesWatched++;
            m_stateHistory.clear();
            m_replayIndex = 0;
            m_framesSinceAdvance = 0;
            m_gameEndPauseFrames = 120; // 2 second pause between games

            // Update displayed player names based on current swap state
            bool swapped = m_displaySwapped.load();
            m_displayName1 = swapped ? m_playerName2 : m_playerName1;
            m_displayName2 = swapped ? m_playerName1 : m_playerName2;
        }

        m_stateHistory.push_back(state);
    }
}

void GUIState_WatchTraining::autoAdvance()
{
    if (m_autoPaused) return;
    if (m_stateHistory.empty()) return;

    // Pause between games
    if (m_gameEndPauseFrames > 0)
    {
        m_gameEndPauseFrames--;
        return;
    }

    m_framesSinceAdvance++;
    if (m_framesSinceAdvance >= m_autoAdvanceFrames)
    {
        m_framesSinceAdvance = 0;

        if (m_replayIndex + 1 < m_stateHistory.size())
        {
            m_replayIndex++;
        }
        // If we're at the end, just wait for more states from the queue
    }
}

void GUIState_WatchTraining::onFrame()
{
    m_view.update();
    pollQueue();
    autoAdvance();

    if (!m_stateHistory.empty() && m_replayIndex < m_stateHistory.size())
    {
        setState(m_stateHistory[m_replayIndex]);
    }

    sRender();
    sUserInput();
    m_currentFrame++;
}

// --- Rendering code (adapted from GUIState_Play) ---

void GUIState_WatchTraining::setState(const GameState & state)
{
    m_currentState = state;
    setGUICards();
    setCardPositions();
}

void GUIState_WatchTraining::setGUICards()
{
    m_guiCards.clear();
    m_guiCardsBuyable.clear();

    for (PlayerID player = 0; player < 2; ++player)
    {
        for (const auto & cardID : m_currentState.getCardIDs(player))
        {
            const Card & card = const_cast<const GameState &>(m_currentState).getCardByID(cardID);
            m_guiCards.push_back(GUICard(card, {-1, -1}, m_game.window()));
        }

        for (const auto & cardID : m_currentState.getKilledCardIDs(player))
        {
            const Card & card = const_cast<const GameState &>(m_currentState).getCardByID(cardID);
            if (card.getAliveStatus() == AliveStatus::KilledThisTurn)
            {
                m_guiCards.push_back(GUICard(card, {-1, -1}, m_game.window()));
            }
        }
    }

    for (CardID cb(0); cb < m_currentState.numCardsBuyable(); ++cb)
    {
        const CardBuyable & cardBuyable = const_cast<const GameState &>(m_currentState).getCardBuyableByIndex(cb);
        m_guiCardsBuyable.push_back(GUICardBuyable(cardBuyable, sf::Vector2f(-1, -1), m_game.window()));
    }

    std::sort(m_guiCards.begin(), m_guiCards.end());
}

void GUIState_WatchTraining::setCardPositions()
{
    auto CardSize = GUICard::GetCardSize();
    sf::Vector2f StatusIconSize(CardSize.x / 5, CardSize.y / 5);
    const sf::Vector2f BuyablePaneSize(200, 0);
    const sf::Vector2f BuyableCardSize(200, 60);

    sf::Vector2f buffer = StatusIconSize;
    sf::Vector2f sameBuffer(-4 * CardSize.x / 5, 10);
    sf::Vector2f droneBuffer(-4.7 * CardSize.x / 5, 10);
    sf::Vector2f origin[3][2];

    float midX = BuyablePaneSize.x + ((m_game.window().getSize().x - BuyablePaneSize.x) / 2);
    sf::Vector2f mid[2] = {
        sf::Vector2f(midX, m_game.window().getSize().y / 4),
        sf::Vector2f(midX, 3 * m_game.window().getSize().y / 4)
    };

    float bottomBufferHeight = 60;
    float playerAreaHeight = m_game.window().getSize().y / 2;
    float laneVerticalBuffer = (playerAreaHeight - bottomBufferHeight - 3 * CardSize.y) / 4;

    origin[0][0] = sf::Vector2f(0, mid[0].y + CardSize.y);

    for (int i = 0; i < 3; ++i)
    {
        origin[i][1] = BuyablePaneSize + sf::Vector2f(0, (m_game.window().getSize().y / 2) - (i + 1) * laneVerticalBuffer - (i + 1) * CardSize.y);
        origin[i][0] = BuyablePaneSize + sf::Vector2f(0, (m_game.window().getSize().y / 2) + (i + 1) * laneVerticalBuffer + i * CardSize.y);
    }

    CardType lastType;

    for (PlayerID player = 0; player < 2; ++player)
    {
        sf::Vector2f currentPos[3] = {origin[0][player], origin[1][player], origin[2][player]};
        bool first[3] = {true, true, true};

        for (CardID c(0); c < m_guiCards.size(); ++c)
        {
            int lane = m_guiCards[c].getLane();

            if (m_guiCards[c].getCard()->getPlayer() == player)
            {
                bool sameType = (m_guiCards[c].getCard()->getType() == lastType);
                sf::Vector2f buf = sameType ? sameBuffer : buffer;
                if (!first[lane]) { currentPos[lane] = currentPos[lane] + sf::Vector2f(CardSize.x + buf.x, 0); }
                m_guiCards[c].setPosition(currentPos[lane]);
                lastType = m_guiCards[c].getCard()->getType();
                first[lane] = false;
            }
        }

        lastType = CardType();

        // Center lanes
        float laneMids[3];
        for (int i = 0; i < 3; ++i)
        {
            laneMids[i] = origin[i][player].x + (currentPos[i].x - origin[i][player].x + CardSize.x) / 2;
        }

        for (CardID c(0); c < m_guiCards.size(); ++c)
        {
            if (m_guiCards[c].getCard()->getPlayer() == player)
            {
                m_guiCards[c].setPosition(m_guiCards[c].pos() + sf::Vector2f(mid[1].x - laneMids[m_guiCards[c].getLane()], 0));
            }
        }
    }

    sf::Vector2f currentPos(0, 0);
    for (CardID c(0); c < m_guiCardsBuyable.size(); ++c)
    {
        if (!m_drawBaseSetCards && CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }
        if (m_drawBaseSetCards && !CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }

        m_guiCardsBuyable[c].setPosition(currentPos);
        currentPos = currentPos + sf::Vector2f(0, BuyableCardSize.y);
    }
}

void GUIState_WatchTraining::drawInterface()
{
    const sf::Vector2f BuyablePaneSize(200, 0);
    GUITools::DrawTexturedRect({0, 0}, sf::Vector2f(m_game.window().getSize()), "TexBG", sf::Color::White, &m_game.window());
    GUITools::DrawRect(sf::Vector2f(0, 0), sf::Vector2f(BuyablePaneSize.x, m_game.window().getSize().y), sf::Color::Black, &m_game.window());
    sf::Vector2f p1Origin = BuyablePaneSize;
    sf::Vector2f p2Origin(BuyablePaneSize.x, m_game.window().getSize().y / 2);
    GUITools::DrawRect(p2Origin, sf::Vector2f(m_game.window().getSize().x - BuyablePaneSize.x, 3), sf::Color(127, 127, 127, 127), &m_game.window());
    GUITools::DrawRect(p1Origin, sf::Vector2f(3, m_game.window().getSize().y), sf::Color(127, 127, 127, 64), &m_game.window());
}

void GUIState_WatchTraining::drawCards()
{
    for (size_t i = 0; i < m_guiCards.size(); i++)
    {
        m_guiCards[i].draw(i, m_currentState, false);
    }

    for (CardID i(0); i < m_guiCardsBuyable.size(); ++i)
    {
        bool isBase = CardTypes::IsBaseSet(m_guiCardsBuyable[i].getType());
        bool visible = (m_drawBaseSetCards && isBase) || (!m_drawBaseSetCards && !isBase);
        if (visible)
        {
            m_guiCardsBuyable[i].draw(i, m_currentState);
        }
    }
}

void GUIState_WatchTraining::drawInformation()
{
    const sf::Vector2f BuyablePaneSize(200, 0);
    sf::Vector2f iconSize(32, 32);
    sf::Vector2f numberSize(iconSize.x / 2, iconSize.y / 2);
    sf::Vector2f origin[2] = {
        BuyablePaneSize + sf::Vector2f(10, -10) + sf::Vector2f(0, m_game.window().getSize().y - iconSize.y),
        BuyablePaneSize + sf::Vector2f(10, 10)
    };

    for (PlayerID player = 0; player < 2; ++player)
    {
        GUITools::DrawMana(m_currentState.getResources(player), origin[player], iconSize, numberSize, sf::Vector2f(10, 0), true, &m_game.window());
    }

    int phase = m_currentState.getActivePhase();
    PlayerID player = m_currentState.getActivePlayer();
    sf::Vector2f attackSize(300, 300);
    sf::Vector2f midPoint(m_game.window().getSize().x / 2 + BuyablePaneSize.x / 2, m_game.window().getSize().y / 2);

    if (phase == Phases::Breach || phase == Phases::Defense)
    {
        HealthType attack = m_currentState.getAttack(player);
        if (phase == Phases::Defense)
        {
            midPoint = midPoint + sf::Vector2f(0, player ? midPoint.y / 2 : -midPoint.y / 2);
            attack = m_currentState.getAttack(m_currentState.getEnemy(player));
            GUITools::DrawTexturedRect(midPoint - sf::Vector2f(attackSize.x / 2, attackSize.y / 2), sf::Vector2f(attackSize.x, attackSize.y), "TexAttackBig", sf::Color::White, &m_game.window());
        }
        else
        {
            midPoint = midPoint + sf::Vector2f(0, player ? -midPoint.y / 2 : midPoint.y / 2);
            GUITools::DrawTexturedRect(midPoint - sf::Vector2f(attackSize.x / 2, attackSize.y / 2), sf::Vector2f(attackSize.x, attackSize.y), "TexAttackBigRed", sf::Color::White, &m_game.window());
        }

        sf::Vector2f numSize(80, 80);
        GUITools::DrawTexturedRect(midPoint - sf::Vector2f(numSize.x / 2, numSize.y / 2), sf::Vector2f(numSize.x / 2, numSize.y / 2), std::to_string(attack), sf::Color::White, &m_game.window());
    }

    // Attack and defense potentials
    if (m_drawPotentials)
    {
        auto wSize = m_game.window().getSize();
        sf::Vector2f atkPos[2] = { sf::Vector2f(BuyablePaneSize.x + 20, wSize.y / 2 + 20), sf::Vector2f(BuyablePaneSize.x + 20, wSize.y / 2 - 70) };
        HealthType def[2] = { m_currentState.getTotalAvailableDefense(0), m_currentState.getTotalAvailableDefense(1) };

        for (PlayerID p(0); p < 2; ++p)
        {
            std::stringstream ss;
            ss << "Defense: " << def[p] << "\n";

            HealthType atk = 0;
            if (m_currentState.getActivePlayer() == p)
            {
                atk = m_currentState.getAttack(p);
            }
            else
            {
                GameState atkState(m_currentState);
                AITools::PredictEnemyNextTurn(atkState);
                atk = atkState.getAttack(p);
            }

            ss << "Attack:  " << atk;
            GUITools::DrawString(atkPos[p], ss.str(), sf::Color::White, &m_game.window(), 24);
        }
    }
}

void GUIState_WatchTraining::drawOverlay()
{
    // Top header
    std::stringstream header;
    header << m_modeName;
    header << "  |  Game #" << (m_gamesWatched + 1);
    if (!m_stateHistory.empty())
    {
        header << "  |  Turn " << m_replayIndex << "/" << (m_stateHistory.size() - 1);
    }

    uint32_t totalGames = m_gameCounter.load();
    header << "  |  Total games: " << totalGames;

    if (m_autoPaused)
    {
        header << "  |  PAUSED";
    }

    sf::Vector2f headerPos(210.0f, 4.0f);
    GUITools::DrawString(headerPos, header.str(), sf::Color::Cyan, &m_game.window(), 14);

    // Speed indicator
    float speed = 60.0f / (float)m_autoAdvanceFrames;
    std::stringstream speedStr;
    speedStr << std::fixed << std::setprecision(1) << "Speed: " << speed << " t/s";
    GUITools::DrawString(sf::Vector2f(m_game.window().getSize().x - 160.0f, 4.0f), speedStr.str(), sf::Color::Cyan, &m_game.window(), 14);

    // Game end pause indicator
    if (m_gameEndPauseFrames > 0 && !m_stateHistory.empty())
    {
        // Show winner of last game
        std::string endMsg = "Next game starting...";
        sf::Vector2f endPos(m_game.window().getSize().x / 2.0f - 100.0f, m_game.window().getSize().y / 2.0f - 20.0f);
        GUITools::DrawString(endPos, endMsg, sf::Color::Yellow, &m_game.window(), 20);
    }

    // Controls help at bottom-left (only new/unique controls)
    int spacing = 15;
    int top = 80;
    float y = m_game.window().getSize().y - top;
    sf::Color helpColor(127, 127, 127);

    GUITools::DrawString(sf::Vector2f(5, y),                   "Space: Pause   Arrows: Step/Speed   N: Next Game   ESC: Menu", helpColor, &m_game.window());
}

void GUIState_WatchTraining::drawDebugInfo()
{
    if (!m_drawDebugInfo) return;

    sf::Vector2f origins[2] = {
        sf::Vector2f(m_game.window().getSize().x - 450, (m_game.window().getSize().y / 2) + 20),
        sf::Vector2f(m_game.window().getSize().x - 450, 20)
    };

    for (PlayerID p(0); p < 2; ++p)
    {
        std::stringstream ss;
        const std::string & name = (p == 0) ? m_displayName1 : m_displayName2;
        ss << name << "   Will Score: " << std::fixed << std::setprecision(1) << Eval::WillScoreSum(m_currentState, p) << "\n";
        GUITools::DrawString(origins[p], ss.str(), sf::Color::White, &m_game.window(), 18);
    }

    // Show neural net policy labels on buyable cards
    if (!NeuralNet::Instance().isLoaded()) return;

    NeuralNet::NeuralOutput nnOut = NeuralNet::Instance().evaluate(m_currentState);
    PlayerID activePlayer = m_currentState.getActivePlayer();

    // Compute softmax percentages over affordable units
    float maxVal = -1e9f;
    std::vector<std::pair<CardID, float>> affordable;
    for (CardID i(0); i < m_guiCardsBuyable.size(); ++i)
    {
        const CardType type = m_guiCardsBuyable[i].getType();
        Action buyAction(activePlayer, ActionTypes::BUY, type.getID());
        if (!m_currentState.isLegal(buyAction)) continue;

        int unitIdx = NeuralNet::Instance().getUnitIndex(type.getID());
        if (unitIdx >= 0 && unitIdx < (int)nnOut.policy.size())
        {
            float val = nnOut.policy[unitIdx];
            affordable.push_back({type.getID(), val});
            if (val > maxVal) maxVal = val;
        }
    }

    std::map<CardID, float> policyPct;
    if (!affordable.empty())
    {
        float sumExp = 0;
        for (auto & p : affordable) sumExp += expf(p.second - maxVal);
        for (auto & p : affordable) policyPct[p.first] = (expf(p.second - maxVal) / sumExp) * 100.0f;
    }

    for (CardID i(0); i < m_guiCardsBuyable.size(); ++i)
    {
        bool isBase = CardTypes::IsBaseSet(m_guiCardsBuyable[i].getType());
        bool visible = (m_drawBaseSetCards && isBase) || (!m_drawBaseSetCards && !isBase);
        if (!visible) continue;

        const CardType type = m_guiCardsBuyable[i].getType();
        sf::Vector2f labelPos = m_guiCardsBuyable[i].pos() + sf::Vector2f(205, 5);

        // H: heuristic value
        std::stringstream hs;
        hs << std::fixed << std::setprecision(1);
        double hVal = HeuristicValues::Instance().GetInflatedTotalCostValue(type);
        hs << "H:" << hVal;
        GUITools::DrawString(labelPos + sf::Vector2f(1, 1), hs.str(), sf::Color::Black, &m_game.window(), 24);
        GUITools::DrawString(labelPos, hs.str(), sf::Color(255, 255, 100), &m_game.window(), 24);

        // N: neural net policy
        auto it = policyPct.find(type.getID());
        if (it != policyPct.end())
        {
            int unitIdx = NeuralNet::Instance().getUnitIndex(type.getID());
            std::stringstream ns;
            ns << std::fixed << std::setprecision(3) << " N:" << nnOut.policy[unitIdx];
            ns << std::setprecision(0) << " " << it->second << "%";

            sf::Vector2f nPos = labelPos + sf::Vector2f(0, 26);
            GUITools::DrawString(nPos + sf::Vector2f(1, 1), ns.str(), sf::Color::Black, &m_game.window(), 24);
            GUITools::DrawString(nPos, ns.str(), sf::Color(100, 180, 255), &m_game.window(), 24);
        }
    }
}

void GUIState_WatchTraining::sUserInput()
{
    sf::Event event;
    while (m_game.window().pollEvent(event))
    {
        if (event.type == sf::Event::Closed)
        {
            m_game.quit();
            return;
        }

        if (event.type != sf::Event::KeyPressed) continue;

        switch (event.key.code)
        {
            case sf::Keyboard::Escape:
            {
                m_game.popState();
                return;
            }
            case sf::Keyboard::Space:
            {
                m_autoPaused = !m_autoPaused;
                break;
            }
            case sf::Keyboard::Right:
            {
                // Step forward
                if (m_replayIndex + 1 < m_stateHistory.size())
                {
                    m_replayIndex++;
                    setState(m_stateHistory[m_replayIndex]);
                }
                break;
            }
            case sf::Keyboard::Left:
            {
                // Step backward
                if (m_replayIndex > 0)
                {
                    m_replayIndex--;
                    setState(m_stateHistory[m_replayIndex]);
                }
                break;
            }
            case sf::Keyboard::Up:
            {
                // Speed up (fewer frames between advances, min 5)
                m_autoAdvanceFrames = std::max(5, m_autoAdvanceFrames - 5);
                break;
            }
            case sf::Keyboard::Down:
            {
                // Slow down (more frames between advances, max 300)
                m_autoAdvanceFrames = std::min(300, m_autoAdvanceFrames + 5);
                break;
            }
            case sf::Keyboard::N:
            {
                // Skip to next game - clear history and wait for queue
                m_stateHistory.clear();
                m_replayIndex = 0;
                m_gamesWatched++;
                break;
            }
            case sf::Keyboard::Tab:
            {
                m_drawBaseSetCards = !m_drawBaseSetCards;
                break;
            }
            default: break;
        }
    }
}

void GUIState_WatchTraining::sRender()
{
    m_game.window().clear();
    m_game.window().setView(m_view.getSFMLView());

    if (!m_stateHistory.empty())
    {
        drawInterface();
        drawCards();
        drawInformation();
        drawDebugInfo();
    }
    else
    {
        // Waiting for first game state
        sf::Vector2f waitPos(m_game.window().getSize().x / 2.0f - 150.0f, m_game.window().getSize().y / 2.0f - 20.0f);
        GUITools::DrawString(waitPos, "Waiting for game data...", sf::Color::Cyan, &m_game.window(), 24);
    }

    drawOverlay();

    m_game.window().display();
}
