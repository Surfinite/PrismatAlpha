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
#include <future>

namespace Prismata
{

struct AIEvalResult
{
    std::string playerName;
    Move        move;
    double      score         = 0;
    std::string scoreLabel;
    bool        isUCT         = false;
    double      timeMS        = 0;
    std::string moveDesc;
    std::string buyNotation;
    PlayerID    forPlayer     = 0;
    int         forStateRevision = -1;
    bool        isPrimary     = false;
    bool        isAdvice      = false;
};

struct HumanTurnAdvice
{
    std::string neuralBuy;
    double      neuralEval    = 0;
    double      neuralTimeMS  = 0;
    std::string playoutBuy;
    double      playoutEval   = 0;
    double      playoutTimeMS = 0;
    bool        neuralValid   = false;
    bool        playoutValid  = false;
    int         adviseRevision = -1;
    int         forPlayer     = -1;
};

struct EvalHistoryEntry
{
    int   turnNumber;
    float neuralEval;     // [-1, +1]
    float willScoreDiff;  // raw
};

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
    int                         m_predictedGold[2] = {0, 0};        // Predicted gold income next turn

    // Eval bars
    float                       m_evalBarNeural = 0.0f;             // [-1, +1] neural eval for P0
    float                       m_evalBarWillScore = 0.0f;          // [-1, +1] tanh-normalized WillScore diff
    bool                        m_showWillScoreBar = false;         // Toggled via Shift+W
    bool                        m_showEvalBars = false;             // Toggled via Shift+E (independent of debug)

    // Parallel evaluation (Phase 3)
    int                         m_stateRevision = 0;                // Monotonic counter for staleness checks
    int                         m_maxConcurrentEvals = 2;           // Conservative for x86 4GB limit
    bool                        m_parallelEval = true;              // false = synchronous fallback
    std::vector<std::future<AIEvalResult>> m_evalFutures;
    bool                        m_isThinking = false;               // True while background evals running
    Move                        m_pendingAIMove;                    // Move to execute when primary AI completes
    bool                        m_aiMoveReady = false;              // Set when primary AI result arrives
    PlayerID                    m_aiMovePlayer = 0;                 // Which player the pending move is for
    HumanTurnAdvice             m_humanAdvice;                      // AI recommendations for human player

    // Eval history (Phase 4)
    std::vector<EvalHistoryEntry> m_evalHistory;

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
    void updateGoldPrediction();

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
    void drawEvalBars();
    void updateEvalBarNeural();

    void drawEvalGraph();
    void exportEvalHistory();

    // Parallel evaluation methods
    void launchBackgroundEvals(PlayerID player);
    void launchHumanAdvice(PlayerID player);
    void pollEvalResults();
    void applyEvalResult(const AIEvalResult & result);
    void waitForEvals();

    GUICard * getClickedCard(const int x, const int y);
    GUICardBuyable * getClickedCardBuyable(const int x, const int y);


public:

    GUIState_Play(GUIEngine & game, const GameState & state);
    GUIState_Play(GUIEngine & game, const std::vector<GameState> & replayStates,
                  const std::string & p0, const std::string & p1, int winner);
    ~GUIState_Play();

    void onFrame();
};
}
