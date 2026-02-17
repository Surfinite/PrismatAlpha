#pragma once

#include "GUIState.h"
#include "GUICard.h"
#include "GUICardBuyable.h"
#include "WorldView.hpp"
#include "../testing/IDataSink.h"
#include "../testing/SelfPlayDataSink.h"

#include <SFML/Graphics.hpp>
#include <queue>
#include <mutex>
#include <atomic>
#include <thread>
#include <vector>
#include <memory>

namespace Prismata
{

// Thread-safe queue for passing GameState snapshots from worker thread to GUI
class StateQueue
{
    std::queue<GameState> m_queue;
    std::mutex m_mutex;

public:
    void push(const GameState & state)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_queue.push(state);
    }

    bool tryPop(GameState & out)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_queue.empty()) return false;
        out = m_queue.front();
        m_queue.pop();
        return true;
    }
};

// Sentinel value pushed to queue when a game ends
struct GameEndInfo
{
    int winner = -1;
    int turns = 0;
};

// IDataSink that optionally wraps SelfPlayDataSink (for real training data)
// AND pushes GameState snapshots to a StateQueue for GUI display.
// If realSink is null, only pushes to the queue (display-only mode).
class GUIObserverSink : public IDataSink
{
    SelfPlayDataSink *  m_realSink;
    StateQueue &        m_queue;

public:
    GUIObserverSink(SelfPlayDataSink * realSink, StateQueue & queue)
        : m_realSink(realSink), m_queue(queue) {}

    void onTurnStart(const GameState & state) override
    {
        if (m_realSink) m_realSink->onTurnStart(state);
        m_queue.push(state);
    }

    void onGameEnd(PlayerID winner) override
    {
        if (m_realSink) m_realSink->onGameEnd(winner);
    }

    void finalize() override
    {
        if (m_realSink) m_realSink->finalize();
    }
};

class GUIState_WatchTraining : public GUIState
{
    sf::Text m_text;

    // Display state
    GameState                   m_currentState;
    std::vector<GameState>      m_stateHistory;
    std::vector<GUICard>        m_guiCards;
    std::vector<GUICardBuyable> m_guiCardsBuyable;
    bool                        m_drawBaseSetCards = true;
    bool                        m_drawDebugInfo = true;
    bool                        m_drawPotentials = true;
    WorldView                   m_view;

    // Training thread management
    StateQueue                  m_stateQueue;
    std::vector<std::thread>    m_workerThreads;
    std::atomic<bool>           m_stopRequested{false};
    std::atomic<uint32_t>       m_gameCounter{0};
    std::string                 m_outputDir;

    // Per-thread sinks (threads 1-3 use SelfPlayDataSink directly, thread 0 uses GUIObserverSink)
    std::vector<std::unique_ptr<SelfPlayDataSink>> m_sinks;
    std::unique_ptr<GUIObserverSink>               m_observerSink;

    // Playback control
    size_t  m_replayIndex = 0;
    bool    m_autoPaused = false;
    int     m_autoAdvanceFrames = 30;   // frames between auto-advance (0.5s at 60fps)
    int     m_framesSinceAdvance = 0;
    int     m_gameEndPauseFrames = 0;   // countdown for pause between games

    // Stats
    int     m_gamesWatched = 0;
    int     m_currentGameTurns = 0;

    // Displayed game's player names (updated when new game detected in pollQueue)
    std::string m_displayName1;  // Player_One side (top)
    std::string m_displayName2;  // Player_Two side (bottom)
    std::atomic<bool> m_displaySwapped{false};  // set by thread 0 when sides are swapped

    // Player config
    std::string m_playerName1;
    std::string m_playerName2;
    size_t      m_randomCards = 8;
    bool        m_exportTrainingData = true;
    std::string m_modeName;

    void initCommon();
    void pollQueue();
    void autoAdvance();

    // Worker thread functions
    void workerThread(int threadIndex, IDataSink * sink);

    // Rendering (copied from GUIState_Play, stripped of manual play logic)
    void setState(const GameState & state);
    void setGUICards();
    void setCardPositions();
    void drawInterface();
    void drawInformation();
    void drawCards();
    void drawOverlay();
    void drawDebugInfo();

    void sUserInput();
    void sRender();

public:
    GUIState_WatchTraining(GUIEngine & game);
    GUIState_WatchTraining(GUIEngine & game, const std::string & p1, const std::string & p2,
                           bool exportData, const std::string & modeName);
    ~GUIState_WatchTraining();

    void onFrame() override;
};

}
