#pragma once

#include "Prismata.h"
#include "IDataSink.h"
#include "rapidjson/document.h"
#include <string>
#include <vector>

namespace Prismata
{

class TournamentGame
{
    Game            _game;
    std::string     _playerNames[2];
    size_t          _playerTotalTimeMS[2];
    size_t          _maxTimeMS[2];
    std::vector<std::string> _stateSnapshots;
    IDataSink *     _dataSink = nullptr;
    bool            _saveReplays = false;
    bool            _detailedReplays = false;

public:

    TournamentGame(GameState & initialState, const std::string & p1name, PlayerPtr p1, const std::string & p2name, const PlayerPtr p2);

    void setDataSink(IDataSink * sink) { _dataSink = sink; }
    void setSaveReplays(bool save) { _saveReplays = save; }
    void setDetailedReplays(bool detailed) { _detailedReplays = detailed; }
    void playGame();
    void saveReplay(const std::string & filename) const;

    const std::string & getPlayerName(const PlayerID player) const;
    const GameState & getFinalGameState() const;
    const size_t getTotalTimeMS(const PlayerID player) const;
    const size_t getMaxTimeMS(const PlayerID player) const;
};

}
