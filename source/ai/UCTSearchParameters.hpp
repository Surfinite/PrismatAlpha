#pragma once

#include "Common.h"
#include "Player.h"
#include "MoveIterator.h"
#include "NeuralNet.h"
#include <sstream>
#include <memory>

namespace Prismata
{

    class UCTSearchParameters;

    namespace UCTMoveSelect
    {
        enum { HighestValue, MostVisited };
    }
}

class Prismata::UCTSearchParameters
{
    PlayerID        _maxPlayer          = Players::Player_One;
    int        _rootMoveSelection  = UCTMoveSelect::MostVisited;

    size_t          _timeLimit          = 0;
    double          _cValue             = 2.0;
    size_t          _maxTraversals      = 100;
    size_t          _maxChildren        = 10;
    int        _evalMethod         = EvaluationMethods::Playout;
    double          _blendWeight        = 0.5;
    bool            _usePUCT            = false;

    PlayerPtr       _playoutPlayers[2];
    MoveIteratorPtr _moveIterators[2];
    MoveIteratorPtr _rootMoveIterators[2];

    NeuralNetPtr    _neuralNet;

    std::string                             _graphVizFilename;

public:

    UCTSearchParameters() 
    {

    }

    const PlayerID maxPlayer()                                    const   { return _maxPlayer; }
    const int & evalMethod()                                   const   { return _evalMethod; }
    const size_t & timeLimit()                                      const   { return _timeLimit; }
    const double & cValue()                                         const   { return _cValue; }
    const size_t & maxTraversals()                                  const   { return _maxTraversals; }
    const size_t & maxChildren()                                    const   { return _maxChildren; }
    const int & rootMoveSelectionMethod()                      const   { return _rootMoveSelection; }
    const double & blendWeight()                                    const   { return _blendWeight; }
    bool           usePUCT()                                        const   { return _usePUCT; }
    const std::string & graphVizFilename()                          const   { return _graphVizFilename; }
    const PlayerPtr & getPlayoutPlayer(const PlayerID p)            const   { return _playoutPlayers[p]; }
    const MoveIteratorPtr & getMoveIterator(const PlayerID p)       const   { return _moveIterators[p]; }
    const MoveIteratorPtr & getRootMoveIterator(const PlayerID p)   const   { return _rootMoveIterators[p]; }
    NeuralNet * getNeuralNet()                                      const   { return _neuralNet.get(); }
    const NeuralNetPtr & getNeuralNetPtr()                          const   { return _neuralNet; }
 
    void setMaxPlayer(const PlayerID player)                              { _maxPlayer = player; }
    void setEvalMethod(const int & method)                             { _evalMethod = method; }
    void setTimeLimit(const size_t & timeLimit)                             { _timeLimit = timeLimit; }  
    void setCValue(const double & c)                                        { _cValue = c; }
    void setMaxTraversals(const size_t & traversals)                        { _maxTraversals = traversals; }
    void setMaxChildren(const size_t & children)                            { _maxChildren = children; }
    void setRootMoveSelectionMethod(const int & method)                { _rootMoveSelection = method; }
    void setBlendWeight(const double & w)                                 { _blendWeight = w; }
    void setUsePUCT(bool use)                                             { _usePUCT = use; }
    void setGraphVizFilename(const std::string & filename)                  { _graphVizFilename = filename; }
    void setPlayoutPlayer(const PlayerID p, const PlayerPtr & ptr)          { _playoutPlayers[p] = ptr; }
    void setMoveIterator(const PlayerID p, const MoveIteratorPtr & m)       { _moveIterators[p] = m; }
    void setRootMoveIterator(const PlayerID p, const MoveIteratorPtr & m)   { _rootMoveIterators[p] = m; }
    void setNeuralNet(const NeuralNetPtr & nn)                              { _neuralNet = nn; }

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

    UCTSearchParameters clone() const
    {
        UCTSearchParameters copy(*this);
        copy.deepClone();
        return copy;
    }

    std::string getDescription()
    {
        std::stringstream ss;

        ss << "UCT Parameters\n";
        ss << "Time Limit:     ";
        
        if (timeLimit() > 0)
        {
            ss << timeLimit() << "ms\n";
        }
        else
        {
            ss << "None\n";
        }
        
        ss << "Max Traversals: "   << maxTraversals() << "\n";
        ss << "Max Children:   "   << maxChildren() << "\n";
        ss << "C Value:        "   << cValue() << "\n";
                
        return ss.str();
    }
};
