#pragma once

#include "Common.h"
#include "Player.h"
#include "MoveIterator.h"
#include "AlphaBetaSearchSaveState.hpp"
#include "NeuralNet.h"
#include <string>
#include <memory>

namespace Prismata
{

class AlphaBetaSearchParameters
{
    int         _searchMethod = SearchMethods::IDAlphaBeta;
    PlayerID    _maxPlayer = Players::Player_One;
    int         _maxDepth = 20;

    double      _timeLimit = 0;
    size_t      _maxChildren = 40;
    int         _evalMethod = EvaluationMethods::WillScore;
    double      _blendWeight = 0.5;

    bool    _resumeSearch = false;
    AlphaBetaSearchSaveState _saveState;

    PlayerPtr       _playoutPlayers[2];
    MoveIteratorPtr _moveIterators[2];
    MoveIteratorPtr _rootMoveIterators[2];

    NeuralNetPtr    _neuralNet;

    //std::string                             _graphVizFilename;


public:

    // default constructor
    AlphaBetaSearchParameters()
    {

    }

    int searchMethod() const { return _searchMethod; }
    PlayerID maxPlayer() const { return _maxPlayer; }
    int maxDepth() const { return _maxDepth; }
    double timeLimit() const { return _timeLimit; }
    size_t maxChildren() const { return _maxChildren; }
    int evalMethod() const { return _evalMethod; }
    double blendWeight() const { return _blendWeight; }
    PlayerPtr getPlayoutPlayer(const PlayerID p) const { return _playoutPlayers[p]; }
    bool resumeSearch() const { return _resumeSearch; }
    const AlphaBetaSearchSaveState & getSaveState() const { return _saveState; }
    MoveIteratorPtr & getMoveIterator(const PlayerID p) { return _moveIterators[p]; }
    MoveIteratorPtr & getRootMoveIterator(const PlayerID p) { return _rootMoveIterators[p]; }
    const MoveIteratorPtr & getMoveIterator(const PlayerID p) const { return _moveIterators[p]; }
    const MoveIteratorPtr & getRootMoveIterator(const PlayerID p) const { return _rootMoveIterators[p]; }
    NeuralNet * getNeuralNet() const { return _neuralNet.get(); }
    const NeuralNetPtr & getNeuralNetPtr() const { return _neuralNet; }

    void setSearchMethod(const int & method) { _searchMethod = method; }
    void setMaxPlayer(const PlayerID player) { _maxPlayer = player; }
    void setMaxDepth(const int & depth) { _maxDepth = depth; }
    void setResumeSearch(bool resume, AlphaBetaSearchSaveState ss) { _resumeSearch = resume; _saveState = ss; }
    void setTimeLimit(const double & timeLimit) { _timeLimit = timeLimit; }
    void setMaxChildren(const size_t & children) { _maxChildren = children; }
    void setEvalMethod(const int & eval) { _evalMethod = eval; }
    void setBlendWeight(const double & w) { _blendWeight = w; }
    void setPlayoutPlayer(const PlayerID p, const PlayerPtr & ptr) { _playoutPlayers[p] = ptr; }
    void setMoveIterator(const PlayerID p, const MoveIteratorPtr & m) { _moveIterators[p] = m; }
    void setRootMoveIterator(const PlayerID p, const MoveIteratorPtr & m) { _rootMoveIterators[p] = m; }
    void setNeuralNet(const NeuralNetPtr & nn) { _neuralNet = nn; }

    // Deep-clone all shared_ptrs so this instance is fully independent (thread-safe)
    void deepClone()
    {
        for (int p = 0; p < 2; ++p)
        {
            if (_playoutPlayers[p])    _playoutPlayers[p] = _playoutPlayers[p]->clone();
            if (_moveIterators[p])     _moveIterators[p] = _moveIterators[p]->clone();
            if (_rootMoveIterators[p]) _rootMoveIterators[p] = _rootMoveIterators[p]->clone();
        }
        // NeuralNet has mutable scratch buffers — each thread needs its own copy.
        // clone() copies all weights and allocates fresh scratch buffers.
        if (_neuralNet) _neuralNet = _neuralNet->clone();
    }

    AlphaBetaSearchParameters clone() const
    {
        AlphaBetaSearchParameters copy(*this);
        copy.deepClone();
        return copy;
    }

    std::string getDescription()
    {
        std::stringstream ss;

        ss << "AB Parameters\n";
        ss << "Time Limit:     ";

        if (timeLimit() > 0)
        {
            ss << timeLimit() << "ms\n";
        }
        else
        {
            ss << "None\n";
        }

        ss << "Max Depth:      "   << (int)maxDepth() << "\n";
        ss << "Max Children:   "   << (int)maxChildren() << "\n";

        return ss.str();
    }
};
}