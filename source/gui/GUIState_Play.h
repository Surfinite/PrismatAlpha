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

struct AIDebugInfo
{
    std::string primaryName;
    std::string primaryMoveDesc;
    double      primaryScore        = 0;
    std::string primaryScoreLabel;
    bool        primaryIsUCT        = false;
    double      primaryTimeMS       = 0;

    std::string comparisonName;
    std::string comparisonMoveDesc;
    double      comparisonScore     = 0;
    std::string comparisonScoreLabel;
    bool        comparisonIsUCT     = false;
    double      comparisonTimeMS    = 0;
    bool        comparisonRan       = false;

    bool        movesAgree          = false;

    std::string primaryBuyNotation;
    std::string comparisonBuyNotation;
};

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
    bool                        m_autoPlay[2] = {false, false};     // Auto-play AI for each side
    AIDebugInfo                 m_aiDebugInfo[2];                    // Per-player debug info

    // Replay mode
    bool                        m_replayMode = false;
    size_t                      m_replayIndex = 0;
    std::string                 m_replayP0;
    std::string                 m_replayP1;
    int                         m_replayWinner = -1;
    void advanceReplayState();

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
    void runAutoPlay();
    PlayerPtr createComparisonPlayer(PlayerPtr primary, PlayerID player, std::string & outName);
    void toggleBool(bool & value);
    void dumpStateToFile();

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


public:

    GUIState_Play(GUIEngine & game, const GameState & state);
    GUIState_Play(GUIEngine & game, const std::vector<GameState> & replayStates,
                  const std::string & p0, const std::string & p1, int winner);

    void onFrame();
};
}
