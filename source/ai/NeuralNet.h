#pragma once

#include "Common.h"
#include "GameState.h"
#include <vector>
#include <string>
#include <unordered_map>

namespace Prismata
{

class NeuralNet
{
    struct LinearLayer
    {
        std::vector<float> weight;  // [out_dim * in_dim], row-major
        std::vector<float> bias;    // [out_dim]
        int in_dim;
        int out_dim;
    };

    struct LayerNormParams
    {
        std::vector<float> gamma;   // [dim]
        std::vector<float> beta;    // [dim]
        int dim;
    };

    struct ResidualBlock
    {
        LinearLayer linear1;
        LayerNormParams norm1;
        LinearLayer linear2;
        LayerNormParams norm2;
    };

    int _stateDim;
    int _numUnits;
    int _hiddenDim;
    int _numLayers;

    LinearLayer _inputProj;
    std::vector<ResidualBlock> _trunkBlocks;

    LinearLayer _policyLinear1;
    LinearLayer _policyLinear2;

    LinearLayer _valueLinear1;
    LinearLayer _valueLinear2;

    // Unit display name -> unit_index position
    std::unordered_map<std::string, int> _unitNameToIndex;

    // Engine CardType ID -> unit_index position (-1 if unmapped)
    std::vector<int> _cardTypeToUnitIndex;

    bool _loaded;

    static void linearForward(const LinearLayer & layer, const float * input, float * output);
    static void layerNormForward(const LayerNormParams & params, float * data);
    static void reluInPlace(float * data, int size);

    bool readLinearLayer(std::ifstream & f, LinearLayer & layer, const std::string & expectedName);
    bool readLayerNormParams(std::ifstream & f, LayerNormParams & params, const std::string & expectedName);
    void validateSchema() const;

public:

    NeuralNet();

    bool loadWeights(const std::string & filename);
    void buildCardTypeMapping();
    bool isLoaded() const;

    void extractFeatures(const GameState & state, std::vector<float> & features) const;

    struct NeuralOutput
    {
        std::vector<float> policy;  // [num_units] buy count predictions
        float value;                // [-1, 1] win probability for active player
    };

    NeuralOutput evaluate(const GameState & state) const;
    double evaluateValue(const GameState & state, const PlayerID maxPlayer) const;
    int getUnitIndex(int cardTypeID) const;
    int numUnits() const { return _numUnits; }
    int stateDim() const { return _stateDim; }

    void dumpFeaturesToFile(const GameState & state, const std::string & path) const;

    static NeuralNet & Instance();
};

}
