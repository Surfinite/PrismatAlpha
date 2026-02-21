#include "GUIState_Play.h"
#include "GUIEngine.h"
#include "WorldView.hpp"
#include "GUITools.h"
#include "AITools.h"
#include "PrismataAI.h"
#include "Player_UCT.h"
#include "Player_StackAlphaBeta.h"
#include "Player_AlphaBeta.h"
#include "Eval.h"
#include "Heuristics.h"
#include "NeuralNet.h"

#include <fstream>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <cmath>
#include <map>
#include <string>
#include <thread>

using namespace Prismata;

GUIState_Play::GUIState_Play(GUIEngine & game, const GameState & state)
    : GUIState(game)
    , m_currentState(state)
{
    m_stateHistory.push_back(state);

    m_view.setWindowSize(Vec2(m_game.window().getSize().x, m_game.window().getSize().y));
    m_view.setView(m_game.window().getView());
        
    m_text.setFont(Assets::Instance().getFont("Consolas"));
    m_text.setPosition(10, 5);
    m_text.setCharacterSize(10);

    loadPlayers();
}

GUIState_Play::GUIState_Play(GUIEngine & game, const std::vector<GameState> & replayStates,
                             const std::string & p0, const std::string & p1, int winner)
    : GUIState(game)
    , m_currentState(replayStates.front())
    , m_replayMode(true)
    , m_replayIndex(0)
    , m_replayP0(p0)
    , m_replayP1(p1)
    , m_replayWinner(winner)
{
    m_stateHistory = replayStates;

    m_view.setWindowSize(Vec2(m_game.window().getSize().x, m_game.window().getSize().y));
    m_view.setView(m_game.window().getView());

    m_text.setFont(Assets::Instance().getFont("Consolas"));
    m_text.setPosition(10, 5);
    m_text.setCharacterSize(10);

    loadPlayers();
}

void GUIState_Play::init()
{

}

void GUIState_Play::setState(const GameState & state)
{
    m_currentState = state;
    setGUICards();
    setCardPositions();
}

void GUIState_Play::loadPlayers()
{
    const std::vector<std::string> & playerNames = AIParameters::Instance().getPlayerNames();
    for (size_t i(0); i < playerNames.size(); ++i)
    {
        for (PlayerID p(0); p < 2; ++p)
        {
            m_players[p][playerNames[i]] = AIParameters::Instance().getPlayer(p, playerNames[i]);
        }
    }
}

void GUIState_Play::onFrame()
{
    m_view.update();
    setState(m_currentState);
    sRender(); 
    sUserInput();
    m_currentFrame++;
}

void GUIState_Play::setGUICards()
{
    m_guiCards.clear();
    m_guiCardsBuyable.clear();

    for (PlayerID player=0; player<2; ++player)
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
        m_guiCardsBuyable.push_back(GUICardBuyable(cardBuyable, sf::Vector2f(-1,-1), m_game.window()));
    }

    std::sort(m_guiCards.begin(), m_guiCards.end());
}

void GUIState_Play::setCardPositions()
{
    auto CardSize = GUICard::GetCardSize();sf::Vector2f StatusIconSize(CardSize.x / 5, CardSize.y / 5);
    const sf::Vector2f BuyablePaneSize(200, 0);
    const sf::Vector2f BuyableCardSize(200, 60);

    sf::Vector2f buffer = StatusIconSize;
    sf::Vector2f sameBuffer(- 4*CardSize.x/5 , 10);
    sf::Vector2f droneBuffer(- 4.7*CardSize.x/5 , 10);
    sf::Vector2f origin[3][2];

    double droneDiff = sameBuffer.x - droneBuffer.x;
    double droneDiffDelta = droneDiff / 15.0;

    float midX = BuyablePaneSize.x + ((m_game.window().getSize().x - BuyablePaneSize.x) / 2);
    sf::Vector2f mid[2] = { sf::Vector2f(midX, m_game.window().getSize().y/4), sf::Vector2f(sf::Vector2f(midX, 3*m_game.window().getSize().y/4)) };

    float bottomBufferHeight = 60; // how many pixels card bottom will be from bottom of screen
    float playerAreaHeight = m_game.window().getSize().y/2;
    float laneVerticalBuffer = (playerAreaHeight - bottomBufferHeight - 3*CardSize.y) / 4;

    origin[0][0] = sf::Vector2f(0, mid[0].y + CardSize.y );

    for (int i=0; i < 3; ++i)
    {
        origin[i][1] = BuyablePaneSize + sf::Vector2f(0, (m_game.window().getSize().y/2) - (i+1)*laneVerticalBuffer - (i+1)*CardSize.y);
        origin[i][0] = BuyablePaneSize + sf::Vector2f(0, (m_game.window().getSize().y/2) + (i+1)*laneVerticalBuffer + i*CardSize.y);
    }

    CardType lastType;
    
    for (PlayerID player=0; player < 2; ++player)
    {
        sf::Vector2f currentPos[3] = {origin[0][player], origin[1][player], origin[2][player]};
        bool first[3] = {true, true, true};

        for (CardID c(0); c<m_guiCards.size(); ++c)
        {
            int lane = m_guiCards[c].getLane();
            
            if (m_guiCards[c].getCard()->getPlayer() == player)
            {
                bool sameType = (m_guiCards[c].getCard()->getType() == lastType);
                bool droneSame = sameType && lastType.getUIName() == "Drone";
                GUICard * _mouseOverCard = nullptr;
                bool mouseOverType = _mouseOverCard ? (_mouseOverCard->getCard()->getType() == lastType) : false;
                sf::Vector2f buf = sameType ? sameBuffer : buffer;
                if (!first[lane]) { currentPos[lane]  = currentPos[lane] + sf::Vector2f(CardSize.x + buf.x, 0); } 
                m_guiCards[c].setPosition(currentPos[lane]);
                lastType = m_guiCards[c].getCard()->getType();
                first[lane] = false;
            }
        }

        lastType = CardType();

        // fix the lanes to be centered
        float laneMids[3];
        for (int i=0; i < 3; ++i)
        {
            laneMids[i] = origin[i][player].x + (currentPos[i].x - origin[i][player].x + CardSize.x)/2;
        }

        for (CardID c(0); c < m_guiCards.size(); ++c)
        {
            if (m_guiCards[c].getCard()->getPlayer() == player)
            {
                m_guiCards[c].setPosition(m_guiCards[c].pos() + sf::Vector2f(mid[1].x - laneMids[m_guiCards[c].getLane()], 0));
            }
        }
    }

    sf::Vector2f buyableOrigin = sf::Vector2f(0,0);

    sf::Vector2f currentPos = buyableOrigin;
    
    for (CardID c(0); c<m_guiCardsBuyable.size(); ++c)
    {
        if (!m_drawBaseSetCards && CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }
        if (m_drawBaseSetCards && !CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }

        m_guiCardsBuyable[c].setPosition(currentPos);

        currentPos = currentPos + sf::Vector2f(0, BuyableCardSize.y);
    }
}

void GUIState_Play::doGUIMove(const Move & move, int delayMS)
{
    m_doingAIMove = true;

    for (size_t i(0); i < move.size(); ++i)
    {
        const Action & action = move.getAction(i);

        doGUIAction(action, delayMS);

        if (delayMS > 0) { onFrame(); }
    }

    m_doingAIMove = false;
}

void GUIState_Play::doGUIAction(const Action & action, int delayMS)
{
    if (!m_currentState.isLegal(action)) { return; }
    m_currentState.doAction(action);
    setState(m_currentState);
    m_stateHistory.push_back(m_currentState);
    if (delayMS > 0) { std::this_thread::sleep_for(std::chrono::milliseconds(delayMS)); }
}

void GUIState_Play::rewindToPreviousState()
{
    if (m_replayMode)
    {
        if (m_replayIndex == 0) return;
        m_replayIndex--;
        setState(m_stateHistory[m_replayIndex]);
        return;
    }

    if (m_stateHistory.size() == 1)
    {
        std::cout << "Cannot rewind from starting state\n";
        return;
    }

    m_stateHistory.pop_back();
    setState(m_stateHistory.back());
}

void GUIState_Play::advanceReplayState()
{
    if (!m_replayMode) return;
    if (m_replayIndex >= m_stateHistory.size() - 1) return;
    m_replayIndex++;
    setState(m_stateHistory[m_replayIndex]);
}

void GUIState_Play::endCurrentPhase()
{
    const Action space(m_currentState.getActivePlayer(), ActionTypes::END_PHASE, 0);
    if (m_currentState.isLegal(space))
    {
        doGUIAction(space);

        // After phase transition, check if the new active player has auto-play enabled
        PlayerID newPlayer = m_currentState.getActivePlayer();
        if (m_autoPlay[newPlayer] && !m_selectedPlayerName[newPlayer].empty() && !m_currentState.isGameOver())
        {
            runAutoPlay();
        }
    }
}

void GUIState_Play::activateWorkers()
{
    for (CardID gc(0); gc < m_guiCards.size(); ++gc)
    {
        GUICard & guiCard = m_guiCards[gc];
        const Card * card = guiCard.getCard();
        bool isDrone = (card->getType().getUIName() == "Drone" || card->getType().getUIName() == "Doomed Drone");
        if (card->getPlayer() == m_currentState.getActivePlayer() && isDrone && (card->getStatus() != CardStatus::Assigned) && !card->isUnderConstruction())
        {
            Action a = guiCard.onClick(m_currentState);
            doGUIAction(a);
        }
    }
            
    setState(m_currentState); 
}


void GUIState_Play::sUserInput()
{
    // if an AI move is being carried out, don't allow any input
    if (m_doingAIMove) { return; }

    sf::Event event;
    int menuIndexChange = 0;
    PlayerID player = m_currentState.getActivePlayer();
    bool shift = sf::Keyboard::isKeyPressed(sf::Keyboard::LShift);
    while (m_game.window().pollEvent(event))
    {
        // this event triggers when the window is closed
        if (event.type == sf::Event::Closed) { m_game.quit(); }

        // this event is triggered when a key is pressed
        if (event.type == sf::Event::KeyPressed)
        {
            switch (event.key.code)
            {
                case sf::Keyboard::Escape:  { m_game.popState(); break; }
                case sf::Keyboard::Tab:     { toggleBool(m_drawBaseSetCards); break; }
                case sf::Keyboard::Q:       { activateWorkers(); break; }
                case sf::Keyboard::Space:   { if (m_replayMode) advanceReplayState(); else endCurrentPhase(); break; }
                case sf::Keyboard::Right:   { advanceReplayState(); break; }
                case sf::Keyboard::Left:    { rewindToPreviousState(); break; }
                case sf::Keyboard::A:       { buyCardByName("Animus", shift); break; }
                case sf::Keyboard::D:       { buyCardByName("Drone", shift); break; }
                case sf::Keyboard::E:       { buyCardByName("Engineer", shift); break; }
                case sf::Keyboard::B:       { buyCardByName("Blastforge", shift); break; }
                case sf::Keyboard::C:       { buyCardByName("Conduit", shift); break; }
                case sf::Keyboard::F:       { buyCardByName("Forcefield", shift); break; }
                case sf::Keyboard::G:       { buyCardByName("Gauss Cannon", shift); break; }
                case sf::Keyboard::S:       { buyCardByName("Steelsplitter", shift); menuIndexChange = 1; break; }
                case sf::Keyboard::T:       { buyCardByName("Tarsier", shift); break; }
                case sf::Keyboard::R:       { buyCardByName("Rhino", shift); break; }
                case sf::Keyboard::W:       { buyCardByName("Wall", shift); menuIndexChange = -1; break; }
                case sf::Keyboard::Z:       { rewindToPreviousState(); break; }
                case sf::Keyboard::M:       { toggleBool(m_drawMouseOver); break; }
                case sf::Keyboard::X:       { toggleBool(m_drawPotentials); break; }
                case sf::Keyboard::Tilde:   { toggleBool(m_drawDebugInfo); break; }
                case sf::Keyboard::BackSlash: { toggleBool(m_drawDebugInfo); break; }
                case sf::Keyboard::F5:      { dumpStateToFile(); break; }
                case sf::Keyboard::Num3:    { if (shift) toggleBool(m_drawDebugInfo); break; }
                case sf::Keyboard::Return:  { handleAIMenu(); break; }
                case sf::Keyboard::Up:      { menuIndexChange = -1; break; }
                case sf::Keyboard::Down:    { menuIndexChange =  1; break; }

                default:                    { break; }
            }

            // change the ai menu selected item based on the input above
            m_selectedPlayer[player] = (m_selectedPlayer[player] + (m_drawAIMenu ? menuIndexChange : 0));
            if (m_selectedPlayer[player] < 0) { m_selectedPlayer[player] += m_players[player].size(); }
            else { m_selectedPlayer[player] = m_selectedPlayer[player] % m_players[player].size(); }
        }

        // TextEntered handles keyboard layout differences (UK keyboard # key, etc.)
        if (event.type == sf::Event::TextEntered)
        {
            if (event.text.unicode == '#' || event.text.unicode == '~' || event.text.unicode == '`')
            {
                toggleBool(m_drawDebugInfo);
            }
        }

        if (event.type == sf::Event::MouseButtonPressed)
        {
            auto mouse = m_view.windowToWorld(Vec2(event.mouseButton.x, event.mouseButton.y));

            // happens when the left mouse button is pressed
            if (event.mouseButton.button == sf::Mouse::Left)
            {
                m_view.stopScroll();

                // determine which element of the gui was clicked, if any
                GUICard * guiCard = getClickedCard(mouse.x, mouse.y);
                GUICardBuyable * cardBuyable = guiCard ? NULL : getClickedCardBuyable(mouse.x, mouse.y);
                bool shift = sf::Keyboard::isKeyPressed(sf::Keyboard::LShift);

                // if a card was clicked
                if (guiCard)
                {
                    Action a = guiCard->onClick(m_currentState);
                    a.setShift(shift);
                    if (m_currentState.isLegal(a)) { doGUIAction(a); }
                }
                // if a buyable card pane was clicked
                else if (cardBuyable != NULL)
                {
                    Action a = cardBuyable->onClick(m_currentState.getActivePlayer(), m_currentState.getActivePhase());
                    a.setShift(shift);
                    if (m_currentState.isLegal(a)) { doGUIAction(a); }
                }
            }

            // happens when the right mouse button is pressed
            if (event.mouseButton.button == sf::Mouse::Right)
            {
                m_drag = { event.mouseButton.x, event.mouseButton.y };
                m_view.stopScroll();
            }
        }

        // happens when the mouse button is released
        if (event.type == sf::Event::MouseButtonReleased)
        {
            if (event.mouseButton.button == sf::Mouse::Left)  { }
            if (event.mouseButton.button == sf::Mouse::Right) { m_drag = { -1, -1 }; }
        }

        if (event.type == sf::Event::MouseWheelMoved)
        {
            double zoom = 1.0 - (0.2 * event.mouseWheel.delta);
            m_view.zoomTo(zoom, Vec2(event.mouseWheel.x, event.mouseWheel.y));
        }

        // happens whenever the mouse is being moved
        if (event.type == sf::Event::MouseMoved)
        {
            auto world = m_view.windowToWorld(Vec2(event.mouseMove.x, event.mouseMove.y));
            m_mouseWorld = sf::Vector2f(world.x, world.y);
            m_mouseOverCard = getClickedCard(world.x, world.y);
            m_mouseOverCardBuyable = getClickedCardBuyable(world.x, world.y);

            // dragging with rmb
            if (m_drag.x != -1)
            {
                auto prev = m_view.windowToWorld(m_drag);
                auto curr = m_view.windowToWorld({ event.mouseMove.x, event.mouseMove.y });
                auto scroll = prev - curr;
                m_view.scroll(prev - curr);
                m_drag = { event.mouseMove.x, event.mouseMove.y };
            }

        }
    }
}

void GUIState_Play::toggleBool(bool & val)
{
    val = !val;
}

void GUIState_Play::dumpStateToFile()
{
    std::string path = "debug_state.txt";
    std::ofstream out(path);
    if (!out.is_open())
    {
        printf("Failed to open %s for writing\n", path.c_str());
        return;
    }

    PlayerID active = m_currentState.getActivePlayer();
    out << "=== PRISMATA STATE DUMP (F5) ===\n";
    out << "Turn: " << m_currentState.getTurnNumber() << "\n";
    out << "Active Player: " << (int)active << "\n";
    out << "Phase: " << (int)m_currentState.getActivePhase() << "\n\n";

    // Per-player info
    for (PlayerID p = 0; p < 2; ++p)
    {
        out << "--- Player " << (int)p << " ---\n";
        out << "Will Score: " << std::fixed << std::setprecision(1) << Eval::WillScoreSum(m_currentState, p) << "\n";
        out << "Attack: " << m_currentState.getAttack(p) << "\n";

        // Units
        out << "Units:\n";
        std::map<std::string, int> unitCounts;
        const CardIDVector & cardIDs = m_currentState.getCardIDs(p);
        for (size_t c = 0; c < cardIDs.size(); ++c)
        {
            const Card & card = m_currentState.getCardByID(cardIDs[c]);
            if (card.isDead()) continue;
            std::string status = "ready";
            if (card.isUnderConstruction()) status = "constructing";
            else if (card.getStatus() == CardStatus::Assigned) status = "blocking";
            else if (!card.canUseAbility()) status = "exhausted";
            std::string key = card.getType().getUIName() + " (" + status + ")";
            unitCounts[key]++;
        }
        for (auto & kv : unitCounts)
        {
            out << "  " << kv.second << "x " << kv.first << "\n";
        }

        // AI debug info
        const AIDebugInfo & info = m_aiDebugInfo[p];
        if (!info.primaryName.empty())
        {
            out << "AI: " << info.primaryName << "\n";
            out << info.primaryScoreLabel << ": ";
            if (info.primaryIsUCT)
                out << std::fixed << std::setprecision(1) << (info.primaryScore * 100.0) << "%";
            else
                out << std::fixed << std::setprecision(1) << info.primaryScore;
            out << " (" << (int)info.primaryTimeMS << "ms)\n";
        }
        if (info.comparisonRan)
        {
            out << info.comparisonName << " " << info.comparisonScoreLabel << ": " << std::fixed << std::setprecision(1) << info.comparisonScore;
            out << " (" << (int)info.comparisonTimeMS << "ms)\n";
            out << "Moves: " << (info.movesAgree ? "AGREE" : "DISAGREE") << "\n";
        }
        out << "\n";
    }

    // Buyable supply
    out << "--- Buyable Supply ---\n";
    for (CardID i = 0; i < m_currentState.numCardsBuyable(); ++i)
    {
        const CardBuyable & cb = m_currentState.getCardBuyableByIndex(i);
        const CardType type = cb.getType();
        bool isBase = CardTypes::IsBaseSet(type);
        double hVal = HeuristicValues::Instance().GetInflatedTotalCostValue(type);

        out << (isBase ? "[BASE] " : "[DOM]  ");
        out << std::left << std::setw(25) << type.getUIName();
        out << " H:" << std::fixed << std::setprecision(1) << hVal;

        // Neural net policy value
        if (NeuralNet::Instance().isLoaded())
        {
            int unitIdx = NeuralNet::Instance().getUnitIndex(type.getID());
            out << " unitIdx:" << unitIdx;
        }

        out << " supply:" << cb.getSupplyRemaining(Players::Player_One) << "/" << cb.getSupplyRemaining(Players::Player_Two);
        out << " typeID:" << type.getID();
        out << " name:'" << type.getName() << "'";
        out << "\n";
    }

    // Neural net feature diagnostic
    if (NeuralNet::Instance().isLoaded())
    {
        out << "\n--- Neural Net Feature Diagnostic ---\n";
        NeuralNet::NeuralOutput nnOut = NeuralNet::Instance().evaluate(m_currentState);
        out << "Value: " << std::fixed << std::setprecision(4) << nnOut.value << "\n";
        out << "Policy (top 15):\n";

        // Find top 15 policy values
        std::vector<std::pair<float, int>> policyPairs;
        for (int i = 0; i < (int)nnOut.policy.size(); ++i)
        {
            policyPairs.push_back({nnOut.policy[i], i});
        }
        std::sort(policyPairs.begin(), policyPairs.end(), [](const auto & a, const auto & b) { return a.first > b.first; });
        for (int i = 0; i < 15 && i < (int)policyPairs.size(); ++i)
        {
            out << "  idx=" << policyPairs[i].second << " val=" << std::fixed << std::setprecision(4) << policyPairs[i].first << "\n";
        }
    }

    // JSON state
    out << "\n--- JSON State ---\n";
    out << m_currentState.toJSONString() << "\n";

    out.close();
    printf("State dumped to %s\n", path.c_str());
}

void GUIState_Play::buyCardByName(const std::string & name, bool shift)
{
    if (CardTypes::CardTypeExists(name))
    {
        Action buy(m_currentState.getActivePlayer(), ActionTypes::BUY, CardTypes::GetCardType(name).getID());
        buy.setShift(shift);
        doGUIAction(buy);
    }
}

GUICard * GUIState_Play::getClickedCard(const int x, const int y)
{
    GUICard * clicked = nullptr;
    int maxCardLayer = -1;
    for (CardID c(0); c<m_guiCards.size(); ++c)
    {
        if (m_guiCards[c].isClicked(x, y) && (!clicked || m_guiCards[c].getLayer() > maxCardLayer))
        {
            clicked = &m_guiCards[c];
            maxCardLayer = m_guiCards[c].getLayer();
        }
    }
    
    return clicked;
}

GUICardBuyable * GUIState_Play::getClickedCardBuyable(const int x, const int y)
{
    GUICardBuyable * clicked = nullptr;
    int maxCardLayer = -1;
    for (CardID c(0); c<m_guiCardsBuyable.size(); ++c)
    {
        // skip cards not shown in current buy pane view
        if (!m_drawBaseSetCards && CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }
        if (m_drawBaseSetCards && !CardTypes::IsBaseSet(m_guiCardsBuyable[c].getType())) { continue; }

        if (m_guiCardsBuyable[c].isClicked(x, y) && (!clicked || m_guiCardsBuyable[c].getLayer() > maxCardLayer))
        {
            clicked = &m_guiCardsBuyable[c];
            maxCardLayer = m_guiCardsBuyable[c].getLayer();
        }
    }

    return clicked;
}

// draws the large scale interface elements
void GUIState_Play::drawInterface()
{
    const sf::Vector2f BuyablePaneSize(200, 0);
    GUITools::DrawTexturedRect({0, 0}, sf::Vector2f(m_game.window().getSize()), "TexBG", sf::Color::White, &m_game.window()); // board bg
    GUITools::DrawRect(sf::Vector2f(0,0), sf::Vector2f(BuyablePaneSize.x, m_game.window().getSize().y), sf::Color::Black, &m_game.window()); // buy pane bg
    sf::Vector2f p1Origin = BuyablePaneSize;
    sf::Vector2f p2Origin(BuyablePaneSize.x, m_game.window().getSize().y/2);
    GUITools::DrawRect(p2Origin, sf::Vector2f(m_game.window().getSize().x-BuyablePaneSize.x, 3), sf::Color(127, 127, 127, 127), &m_game.window()); // horizontal board sep
    GUITools::DrawRect(p1Origin, sf::Vector2f(3, m_game.window().getSize().y), sf::Color(127, 127, 127, 64), &m_game.window()); // vertical buy sep
}

// draws resources, attack amounts, phase, etc
void GUIState_Play::drawInformation()
{
    // draw resource
    const sf::Vector2f BuyablePaneSize(200, 0);
    sf::Vector2f iconSize(32, 32);
    sf::Vector2f bigIconSize(64, 64);
    sf::Vector2f numberSize(iconSize.x/2, iconSize.y/2);
    sf::Vector2f diffSize((iconSize.x - numberSize.x) / 2, (iconSize.y - numberSize.y) / 2);
    sf::Vector2f buffer(10,-10);
    sf::Vector2f p1Origin = BuyablePaneSize;
    sf::Vector2f p2Origin(BuyablePaneSize.x, m_game.window().getSize().y/2);
    sf::Vector2f origin[2] = {BuyablePaneSize + sf::Vector2f(10, -10) + sf::Vector2f(0, m_game.window().getSize().y - iconSize.y), BuyablePaneSize + sf::Vector2f(10, 10)};

    int iconNum = 0;
    sf::Color white(255, 255, 255, 255);
    sf::Color white2(255, 255, 255, 127);
    sf::Color bg(0, 0, 0, 127);

    for (PlayerID player=0; player<2; ++player)
    {
        GUITools::DrawMana(m_currentState.getResources(player), origin[player], iconSize, numberSize, sf::Vector2f(10, 0), true, &m_game.window());
    }

    int phase = m_currentState.getActivePhase();
    PlayerID player = m_currentState.getActivePlayer();
    sf::Vector2f attackSize(300, 300);
    sf::Vector2f numSize(80, 80);
    sf::Vector2f midPoint(m_game.window().getSize().x/2 + BuyablePaneSize.x/2, m_game.window().getSize().y/2);
    if (phase == Phases::Breach || phase == Phases::Defense)
    {        
        HealthType attack = m_currentState.getAttack(player);
        if (phase == Phases::Defense)
        {
            midPoint = midPoint + sf::Vector2f(0, player ? midPoint.y/2 : -midPoint.y/2);
            attack = m_currentState.getAttack(m_currentState.getEnemy(player));
            GUITools::DrawTexturedRect(midPoint - sf::Vector2f(attackSize.x/2, attackSize.y/2), sf::Vector2f(attackSize.x, attackSize.y), "TexAttackBig", white, &m_game.window());
        }
        else
        {
            midPoint = midPoint + sf::Vector2f(0, player ? -midPoint.y/2 : midPoint.y/2);
            GUITools::DrawTexturedRect(midPoint - sf::Vector2f(attackSize.x/2, attackSize.y/2), sf::Vector2f(attackSize.x, attackSize.y), "TexAttackBigRed", white, &m_game.window());
        }

        GUITools::DrawTexturedRect(midPoint - sf::Vector2f(numSize.x/2, numSize.y/2), sf::Vector2f(numSize.x/2, numSize.y/2), std::to_string(attack), white, &m_game.window());
    }

    // print status message
    sf::Vector2f space = m_currentState.getActivePlayer() != 0 ? sf::Vector2f(m_game.window().getSize().x/2 - 200, 8) : sf::Vector2f(m_game.window().getSize().x/2 - 200, m_game.window().getSize().y - 24);
    std::string status = "";

    if (m_currentState.isLegal(Action(m_currentState.getActivePlayer(), ActionTypes::END_PHASE, 0)))
    {
        status = m_currentState.getActivePhase() == Phases::Action ? "ACTION PHASE - PRESS SPACE TO END PHASE" : "PRESS SPACE TO CONFIRM END PHASE";
    }
    else
    {
        switch (m_currentState.getActivePhase())
        {
            case Phases::Defense: { status = "DEFENSE PHASE - ASSIGN BLOCKERS"; break; }
            case Phases::Breach:  { status = "BREACH PHASE - ASSIGN BREACH"; break; }
        }
    }

    // draw attack and defense potentials
    if (m_drawPotentials && !m_currentState.isTargetAbilityCardClicked())
    {
        auto wSize = m_game.window().getSize();
        sf::Vector2f atkPos[2] = { sf::Vector2f(BuyablePaneSize.x + 20, wSize.y/2 + 20), sf::Vector2f(BuyablePaneSize.x + 20, wSize.y/2 - 70) };
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

    GUITools::DrawString(space, status, sf::Color::White, &m_game.window(), 16);
    int spacing = 15;
    int top = 140;

    if (m_replayMode)
    {
        // Replay mode overlay
        std::stringstream replayInfo;
        replayInfo << "REPLAY: " << m_replayP0 << " vs " << m_replayP1;
        replayInfo << "   Turn " << m_replayIndex << "/" << (m_stateHistory.size() - 1);
        std::string winStr = m_replayWinner == 0 ? m_replayP0 : (m_replayWinner == 1 ? m_replayP1 : "Draw");
        replayInfo << "   Winner: " << winStr;
        sf::Vector2f replayPos(210.0f, 4.0f);
        GUITools::DrawString(replayPos, replayInfo.str(), sf::Color::Yellow, &m_game.window(), 14);

        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top), "Right/Space: Next Turn", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 1*spacing), "Left/Z:      Prev Turn", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 2*spacing), "ESC:         Main Menu", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 3*spacing), "TAB:         Buy Pane", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 4*spacing), "~/# :        Toggle Debug", sf::Color(127, 127, 127), &m_game.window());
    }
    else
    {
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top), "Enter: AI Menu" , sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 1*spacing),  "ESC:   Main Menu", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 2*spacing),  "TAB:   Buy Pane", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 3*spacing),  "Q:     Tap Drones", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 4*spacing),  "Z:     Undo Action", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 5*spacing),  "X:     Toggle Atk/Def", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 6*spacing),  "M:     Toggle Mouseover", sf::Color(127, 127, 127), &m_game.window());
        GUITools::DrawString(sf::Vector2f(5, m_game.window().getSize().y - top + 7*spacing),  "~/# :  Toggle Debug", sf::Color(127, 127, 127), &m_game.window());
    }
}

// draws all cards and buyable cards
void GUIState_Play::drawCards()
{
    // draw the live cards
    for (size_t i=0; i<m_guiCards.size(); i++)
    {
        m_guiCards[i].draw(i, m_currentState, false);
    }
    // draw the buyable cards
    for (CardID i(0); i<m_guiCardsBuyable.size(); ++i)
    {
        bool isBase = CardTypes::IsBaseSet(m_guiCardsBuyable[i].getType());
        bool visible = (m_drawBaseSetCards && isBase) || (!m_drawBaseSetCards && !isBase);

        if (visible)
        {
            m_guiCardsBuyable[i].draw(i, m_currentState);
        }
    }

}

// draws debug info output from ai players
void GUIState_Play::drawDebugInfo()
{
    if (!m_drawDebugInfo) { return; }
    sf::Vector2f origins[2] = { sf::Vector2f(m_game.window().getSize().x - 450, (m_game.window().getSize().y / 2) + 20), sf::Vector2f(m_game.window().getSize().x - 450, 20)};

    std::stringstream ss[2];

    for (PlayerID p(0); p<2; ++p)
    {
        ss[p] << "Will Score: " << std::fixed << std::setprecision(1) << Eval::WillScoreSum(m_currentState, p) << "\n";

        const AIDebugInfo & info = m_aiDebugInfo[p];

        if (!info.primaryName.empty())
        {
            ss[p] << "\n--- " << info.primaryName << " ---\n";
            ss[p] << info.primaryScoreLabel << ": ";
            if (info.primaryIsUCT)
            {
                ss[p] << std::fixed << std::setprecision(1) << (info.primaryScore * 100.0) << "%";
            }
            else
            {
                ss[p] << std::fixed << std::setprecision(1) << info.primaryScore;
            }
            ss[p] << "  (" << (int)info.primaryTimeMS << "ms)\n";
            if (!info.primaryBuyNotation.empty())
            {
                ss[p] << "Buy: " << info.primaryBuyNotation << "\n";
            }
        }

        if (info.comparisonRan)
        {
            ss[p] << "\n--- " << info.comparisonName << " ---\n";
            ss[p] << info.comparisonScoreLabel << ": ";
            if (info.comparisonIsUCT)
            {
                ss[p] << std::fixed << std::setprecision(1) << (info.comparisonScore * 100.0) << "%";
            }
            else
            {
                ss[p] << std::fixed << std::setprecision(1) << info.comparisonScore;
            }
            ss[p] << "  (" << (int)info.comparisonTimeMS << "ms)\n";
            ss[p] << "Moves: " << (info.movesAgree ? "AGREE" : "DISAGREE") << "\n";
            if (!info.comparisonBuyNotation.empty())
            {
                ss[p] << "Buy: " << info.comparisonBuyNotation << "\n";
            }
        }

        ss[p] << "\n" << m_aiDescription[p];

        GUITools::DrawString(origins[p], ss[p].str(), sf::Color::White, &m_game.window(), 18);
    }

    // draw unit value labels next to buyable cards (drawn last so they render on top of resources)
    NeuralNet::NeuralOutput nnOut;
    bool hasNN = NeuralNet::Instance().isLoaded();
    if (hasNN)
    {
        nnOut = NeuralNet::Instance().evaluate(m_currentState);
    }

    // Compute softmax percentages over affordable units only
    PlayerID activePlayer = m_currentState.getActivePlayer();
    std::map<CardID, float> policyPct; // typeID -> softmax percentage
    if (hasNN)
    {
        // Collect policy values for affordable units
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

        // Softmax with numerical stability (subtract max)
        if (!affordable.empty())
        {
            float sumExp = 0;
            for (auto & p : affordable)
            {
                sumExp += expf(p.second - maxVal);
            }
            for (auto & p : affordable)
            {
                policyPct[p.first] = (expf(p.second - maxVal) / sumExp) * 100.0f;
            }
        }
    }

    for (CardID i(0); i<m_guiCardsBuyable.size(); ++i)
    {
        bool isBase = CardTypes::IsBaseSet(m_guiCardsBuyable[i].getType());
        bool visible = (m_drawBaseSetCards && isBase) || (!m_drawBaseSetCards && !isBase);
        if (!visible) continue;

        const CardType type = m_guiCardsBuyable[i].getType();
        sf::Vector2f labelPos = m_guiCardsBuyable[i].pos() + sf::Vector2f(205, 5);

        // H: value in yellow
        std::stringstream hs;
        hs << std::fixed << std::setprecision(1);
        double hVal = HeuristicValues::Instance().GetInflatedTotalCostValue(type);
        hs << "H:" << hVal;
        GUITools::DrawString(labelPos + sf::Vector2f(1, 1), hs.str(), sf::Color::Black, &m_game.window(), 24);
        GUITools::DrawString(labelPos, hs.str(), sf::Color(255, 255, 100), &m_game.window(), 24);

        // N: value + percentage in blue (only for affordable units)
        if (hasNN)
        {
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
}

void GUIState_Play::drawTargetAbility()
{
    if (m_currentState.isTargetAbilityCardClicked() && !m_doingAIMove)
    {   
        GUICard * targetAbilityCard = NULL;

        // find the guicard corresponding to the target ability card that was clicked
        for (size_t i(0); i < m_guiCards.size(); ++i)
        {
            CardID guiCardID = m_guiCards[i].getCard()->getID();
            CardID targetAbilityCardID = m_currentState.getTargetAbilityCardClicked().getID();
            if (guiCardID == targetAbilityCardID)
            {
                targetAbilityCard = &m_guiCards[i];
                break;
            }
        }

        if (targetAbilityCard)
        {
            GUITools::DrawLine(targetAbilityCard->pos() + sf::Vector2f(55, 55), m_mouseWorld, sf::Color::Red, &m_game.window());
        }
    }
}

void GUIState_Play::drawMouseOverPanes()
{
    if (!m_drawMouseOver) { return; }

    // draw mouseover box
    if (m_mouseOverCard)
    {
        GUITools::DrawMouseOverPane(m_mouseOverCard->getCard()->getType(), m_mouseOverCard->pos() + sf::Vector2f(120, 0), m_mouseOverCard->getCard(), &m_game.window());
    }

    if (m_mouseOverCardBuyable)
    {
        GUITools::DrawMouseOverPane(m_mouseOverCardBuyable->getType(), m_mouseOverCardBuyable->pos() + sf::Vector2f(210, 0), nullptr, &m_game.window());
    }
}

static std::string buildBuyNotation(const Move & move, const GameState & state)
{
    static const std::map<std::string, char> baseShortcuts = {
        {"Drone", 'D'}, {"Engineer", 'E'}, {"Animus", 'A'},
        {"Blastforge", 'B'}, {"Conduit", 'C'}, {"Forcefield", 'F'},
        {"Gauss Cannon", 'G'}, {"Steelsplitter", 'S'},
        {"Tarsier", 'T'}, {"Rhino", 'R'}, {"Wall", 'W'}
    };

    // Number dominion (non-base) buyable cards 1, 2, 3... in buy-pane order
    std::map<CardID, int> dominionNumbers;
    int domNum = 1;
    for (CardID i = 0; i < state.numCardsBuyable(); ++i)
    {
        const CardType type = state.getCardBuyableByIndex(i).getType();
        if (!CardTypes::IsBaseSet(type))
        {
            dominionNumbers[type.getID()] = domNum++;
        }
    }

    std::string result;
    for (size_t i = 0; i < move.size(); ++i)
    {
        const Action & action = move.getAction(i);
        if (action.getType() == ActionTypes::BUY)
        {
            const CardType type = state.getCardBuyableByID(action.getID()).getType();
            std::string uiName = type.getUIName();
            auto it = baseShortcuts.find(uiName);
            if (it != baseShortcuts.end())
            {
                result += it->second;
            }
            else
            {
                auto dit = dominionNumbers.find(type.getID());
                if (dit != dominionNumbers.end())
                {
                    result += std::to_string(dit->second);
                }
                else
                {
                    result += "?";
                }
            }
        }
    }

    return result.empty() ? "(none)" : result;
}

PlayerPtr GUIState_Play::createComparisonPlayer(PlayerPtr primary, PlayerID player, std::string & outName)
{
    Player_UCT * uctPlayer = dynamic_cast<Player_UCT *>(primary.get());
    Player_StackAlphaBeta * abPlayer = dynamic_cast<Player_StackAlphaBeta *>(primary.get());

    if (uctPlayer)
    {
        UCTSearchParameters params = uctPlayer->getParams();
        int currentEval = params.evalMethod();

        if (currentEval == EvaluationMethods::NeuralNet)
        {
            params.setEvalMethod(EvaluationMethods::Playout);
            PlayerPtr playoutP1 = AIParameters::Instance().getPlayer(0, "Playout");
            PlayerPtr playoutP2 = AIParameters::Instance().getPlayer(1, "Playout");
            params.setPlayoutPlayer(0, playoutP1);
            params.setPlayoutPlayer(1, playoutP2);
            outName = "HardestAIUCT";
        }
        else if (currentEval == EvaluationMethods::Playout)
        {
            params.setEvalMethod(EvaluationMethods::WillScore);
            outName = "UCT_WillScore";
        }
        else
        {
            return nullptr;
        }

        params.setMaxPlayer(player);
        return PlayerPtr(new Player_UCT(player, params));
    }
    else if (abPlayer)
    {
        AlphaBetaSearchParameters params = abPlayer->getParams();
        int currentEval = params.evalMethod();

        if (currentEval == EvaluationMethods::NeuralNet)
        {
            params.setEvalMethod(EvaluationMethods::Playout);
            PlayerPtr playoutP1 = AIParameters::Instance().getPlayer(0, "Playout");
            PlayerPtr playoutP2 = AIParameters::Instance().getPlayer(1, "Playout");
            params.setPlayoutPlayer(0, playoutP1);
            params.setPlayoutPlayer(1, playoutP2);
            outName = "HardestAI";
        }
        else if (currentEval == EvaluationMethods::Playout)
        {
            params.setEvalMethod(EvaluationMethods::WillScore);
            outName = "AB_WillScore";
        }
        else
        {
            return nullptr;
        }

        params.setMaxPlayer(player);
        return PlayerPtr(new Player_StackAlphaBeta(player, params));
    }

    return nullptr;
}

void GUIState_Play::runAutoPlay()
{
    PlayerID player = m_currentState.getActivePlayer();
    if (m_selectedPlayerName[player].empty()) { return; }

    // Save pre-move state for comparison AI
    GameState preMoveState = m_currentState;

    // Run primary AI
    PlayerPtr primary = AIParameters::Instance().getPlayer(player, m_selectedPlayerName[player]);
    Move primaryMove;
    primary->getMove(m_currentState, primaryMove);
    m_aiDescription[player] = primary->getDescription();

    // Extract primary confidence
    AIDebugInfo & info = m_aiDebugInfo[player];
    info = AIDebugInfo();
    info.primaryName = m_selectedPlayerName[player];

    Player_UCT * uctPlayer = dynamic_cast<Player_UCT *>(primary.get());
    Player_StackAlphaBeta * abPlayer = dynamic_cast<Player_StackAlphaBeta *>(primary.get());

    if (uctPlayer)
    {
        UCTSearchResults & results = uctPlayer->getResults();
        info.primaryIsUCT = true;
        info.primaryScoreLabel = "Win Rate";
        info.primaryScore = uctPlayer->getBestRootWinRate();
        info.primaryTimeMS = results.timeElapsed;
        info.primaryMoveDesc = results.bestMoveDescription;
    }
    else if (abPlayer)
    {
        AlphaBetaSearchResults & results = abPlayer->getResults();
        info.primaryIsUCT = false;
        info.primaryScoreLabel = "Eval";
        info.primaryScore = results.bestMoveValues[results.maxDepthCompleted];
        info.primaryTimeMS = results.totalTimeElapsed;
        info.primaryMoveDesc = results.bestMoveDescs[results.maxDepthCompleted];
    }

    // Run comparison AI on the same pre-move state
    std::string compName;
    PlayerPtr compPlayer = createComparisonPlayer(primary, player, compName);
    if (compPlayer)
    {
        Move compMove;
        compPlayer->getMove(preMoveState, compMove);
        info.comparisonRan = true;
        info.comparisonName = compName;

        Player_UCT * compUCT = dynamic_cast<Player_UCT *>(compPlayer.get());
        Player_StackAlphaBeta * compAB = dynamic_cast<Player_StackAlphaBeta *>(compPlayer.get());

        if (compUCT)
        {
            UCTSearchResults & compResults = compUCT->getResults();
            info.comparisonIsUCT = true;
            info.comparisonScoreLabel = "Win Rate";
            info.comparisonScore = compUCT->getBestRootWinRate();
            info.comparisonTimeMS = compResults.timeElapsed;
            info.comparisonMoveDesc = compResults.bestMoveDescription;
        }
        else if (compAB)
        {
            AlphaBetaSearchResults & compResults = compAB->getResults();
            info.comparisonIsUCT = false;
            info.comparisonScoreLabel = "Eval";
            info.comparisonScore = compResults.bestMoveValues[compResults.maxDepthCompleted];
            info.comparisonTimeMS = compResults.totalTimeElapsed;
            info.comparisonMoveDesc = compResults.bestMoveDescs[compResults.maxDepthCompleted];
        }

        info.movesAgree = (primaryMove.toString() == compMove.toString());
        info.comparisonBuyNotation = buildBuyNotation(compMove, preMoveState);
    }

    info.primaryBuyNotation = buildBuyNotation(primaryMove, preMoveState);

    doGUIMove(primaryMove, 200);
}

void GUIState_Play::handleAIMenu()
{
    // ai menu button clicked, so toggle it
    m_drawAIMenu = !m_drawAIMenu;
    if (m_drawAIMenu) { return; }

    PlayerID player = m_currentState.getActivePlayer();
    m_autoPlay[player] = true;
    runAutoPlay();
}

void GUIState_Play::drawAIMenu()
{
    if (!m_drawAIMenu) { return; }

    int fontSize = 18;
    int fontVertSpacing = 20;
    sf::Vector2f size(700, 40 + m_players[0].size() * fontVertSpacing + 100);
    auto windowSize = m_game.window().getSize();

    sf::Vector2f pos(windowSize.x/2 - size.x/2, windowSize.y/2 - size.y/2);
    const PlayerID player(m_currentState.getActivePlayer());
    GUITools::DrawRect(pos, size, sf::Color(0, 0, 0, 230), &m_game.window());
    std::stringstream ss;
    ss << "Select AI to Move for Player ID " << (int)m_currentState.getActivePlayer() << "  " << (player ? "(Top)" : "(Bottom)");
    GUITools::DrawString(pos + sf::Vector2f(25, 20), ss.str(), sf::Color::Yellow, &m_game.window(), fontSize);

    size_t index = 0;
    std::map<std::string, PlayerPtr>::iterator it;
    for (it = m_players[player].begin(); it != m_players[player].end(); it++)
    {
        std::stringstream ss;
        ss << (index < 10 ? "0" : "") << (index)<< ": " << (*it).first;

        if (index == m_selectedPlayer[player])
        {
            GUITools::DrawString(pos + sf::Vector2f(25, 60 + index * fontVertSpacing), ss.str(), player ? sf::Color::Red : sf::Color::Green, &m_game.window(), fontSize);
            m_selectedPlayerName[player] = (*it).first;
                
            std::string header = it->first + " Description:\n";
            GUITools::DrawString(pos + sf::Vector2f(330, 60), header, player ? sf::Color::Red : sf::Color::Green, &m_game.window(), fontSize);
            GUITools::DrawString(pos + sf::Vector2f(330, 80), it->second->getDescription(), sf::Color::White, &m_game.window(), fontSize);
        }
        else
        {
            GUITools::DrawString(pos + sf::Vector2f(25, 60 + index * fontVertSpacing), ss.str(), sf::Color::White, &m_game.window(), fontSize);
        }

        ++index;
    }
}

// renders the scene
void GUIState_Play::sRender()
{
    // switch to world view to draw things in world coordinates
    m_game.window().clear();
    m_game.window().setView(m_view.getSFMLView());
        
    // render all the relevant game information
    drawInterface();
    drawCards();
    drawInformation();
    drawAIMenu();
    drawDebugInfo();
    drawTargetAbility();
    drawMouseOverPanes();
    

    // swap the buffers and draw the frame
    m_game.window().display();
}