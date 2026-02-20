#pragma once

#include "../engine/GameState.h"
#include "../engine/CardTypes.h"
#include "rapidjson/document.h"
#include <unordered_map>
#include <vector>
#include <string>

namespace Prismata
{

class ReplayStepper
{
public:

    enum class StepResult { OK, BenignSkip, FatalError, GameOver };

    ReplayStepper();

    // Initialize from replay JSON components.
    // Calls InitFromMergedDeckJSON internally.
    // Returns false if init fails (malformed JSON, unknown cards).
    bool init(const rapidjson::Value & mergedDeck,
              const rapidjson::Value & initInfo,
              const rapidjson::Value & commandList,
              const rapidjson::Value & clicksPerTurn,
              const rapidjson::Value & playerInfo);

    // Turn-level stepping (preferred API)
    bool hasNextTurn() const;
    StepResult advanceTurn();
    int getTurnClickCount() const;

    // Click-level stepping (lower-level, used by advanceTurn)
    bool hasNextClick() const;
    StepResult applyNextClick();

    // State access
    const GameState & getState() const;
    int getCurrentTurn() const;
    PlayerID getActivePlayer() const;
    int getClickIndex() const;
    bool isGameOver() const;

    // Error/stats
    int getTotalClicks() const;
    int getAppliedClicks() const;
    int getBenignSkips() const;
    int getFatalErrors() const;
    const std::vector<std::string> & getErrors() const;

private:

    // Core state
    GameState m_state;
    int m_clickIndex;
    int m_turnIndex;
    bool m_gameOver;

    // Replay data (stored references — caller must keep replay JSON alive)
    const rapidjson::Value * m_commandList;
    std::vector<int> m_clicksPerTurn;       // Pre-parsed turn boundaries

    // instId tracking
    int m_nextInstId;
    std::unordered_map<int, CardID> m_instIdToCardId;
    std::unordered_map<CardID, int> m_cardIdToInstId;

    // Undo/redo snapshots
    struct Snapshot
    {
        GameState state;
        std::unordered_map<int, CardID> instIdToCardId;
        std::unordered_map<CardID, int> cardIdToInstId;
        int nextInstId;
    };
    std::vector<Snapshot> m_snapshots;
    int m_snapshotCursor;

    // Error tracking
    int m_appliedClicks;
    int m_benignSkips;
    int m_fatalErrors;
    std::vector<std::string> m_errors;

    // Internal methods
    Action clickToAction(const rapidjson::Value & click);
    void updateInstIdMappings();
    void saveSnapshot();
    void restoreSnapshot(int cursor);
    Snapshot captureSnapshot() const;
    bool initGameState(const rapidjson::Value & mergedDeck,
                       const rapidjson::Value & initInfo);
    void logError(const std::string & msg);
};

}
