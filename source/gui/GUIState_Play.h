#pragma once

#include "GameState.h"
#include "GUIState.h"
#include "WorldView.hpp"
#include "GUICard.h"
#include "GUICardBuyable.h"

#include <SFML/Graphics.hpp>
#include <SFML/Audio.hpp>
#include <chrono>
#include <iostream>

namespace Prismata
{
class GUIState_Play : public GUIState
{   
    sf::Text m_text;

    GameState                   m_currentState;             // State that the GUI will be drawing
    std::vector<GameState>      m_stateHistory;             // Stack of state history, push on doGUIAction
    GUICard *                   m_mouseOverCard = nullptr;  // The card the mouse is over
    GUICardBuyable *            m_mouseOverCardBuyable = nullptr;  // The buyable card the mouse is over
    std::vector<GUICard>        m_guiCards;                 // Handles and draws each card in the state
    std::vector<GUICardBuyable> m_guiCardsBuyable;          // Handles and draws cardBuyable in the state
    bool                        m_drawBaseSetCards = true;  // Toggle drawing base set or dominion set
    bool                        m_doingAIMove      = false; // whether AI move being beformed / animated
    bool                        m_drawAIMenu       = false; // Is the AI menu visible
    bool                        m_drawDebugInfo    = false; // whether to draw debug info
    bool                        m_drawMouseOver    = false; // whether to draw mouseover panes
    bool                        m_drawPotentials   = false; // whether to draw atk/def potentials
    Vec2                        m_drag = { -1, -1 };
    WorldView                   m_view;
    Vec2                        m_mouseScreen;
    Vec2                        m_mouseGrid;
    sf::Vector2f                m_mouseWorld;
    int                         m_selectedPlayer[2] = {0, 0};       // AI selected player index
    std::string                 m_selectedPlayerName[2];            // AI selected player name
    std::string                 m_aiDescription[2];
    std::map<std::string, PlayerPtr> m_players[2];  // AI players for each side

    void init();  
    void setState(const GameState & state);
    void setGUICards();
    void setCardPositions();
    void rewindToPreviousState();
    void activateWorkers();
    void endCurrentPhase();
    void buyCardByName(const std::string & name, bool shift);
    void loadPlayers();
    void handleAIMenu();
    void toggleBool(bool & value);
    
    void doGUIAction(const Action & action, int delayMS = 0);
    void doGUIMove(const Move & move, int delayMS = 0);

    void sUserInput();  
    void sRender();

    void drawInformation();
    void drawInterface();
    void drawCards();
    void drawAIMenu();
    void drawDebugInfo();
    void drawTargetAbility();
    void drawMouseOverPanes();

    GUICard * getClickedCard(const int x, const int y);
    GUICardBuyable * getClickedCardBuyable(const int x, const int y);

    // Replay mode
    bool                        m_replayMode = false;
    size_t                      m_replayIndex = 0;
    std::string                 m_replayP0;
    std::string                 m_replayP1;
    int                         m_replayWinner = -1;

    // Per-action replay metadata (empty for legacy per-turn replays)
    std::vector<std::string>    m_actionLabels;      // Human-readable label per state
    std::vector<size_t>         m_turnBoundaries;    // Indices where turns start
    int                         m_totalTurns = 0;    // Total turn count from replay

    void advanceReplayState();
    void rewindReplayState();
    void jumpToNextTurn();
    void jumpToPrevTurn();
    void drawReplayHUD();
    size_t getCurrentTurnIndex() const;

public:

    GUIState_Play(GUIEngine & game, const GameState & state);
    GUIState_Play(GUIEngine & game, std::vector<GameState> replayStates,
                  const std::string & p0, const std::string & p1, int winner,
                  std::vector<std::string> actionLabels = {},
                  std::vector<size_t> turnBoundaries = {},
                  int totalTurns = 0);

    void onFrame();
};
}