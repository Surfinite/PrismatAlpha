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

    struct DeepSetsConfig
    {
        int num_units;              // 116
        int d_embed;                // 32
        int num_properties;         // 13
        int num_instance_features;  // 10
        int encoder_hidden;         // 128
        int supply_hidden;          // 32
        int value_hidden;           // 256
    };

    DeepSetsConfig          _config;

    // Unit-type embedding table (num_units x d_embed)
    std::vector<float>      _embedding_table;

    // Static property table (num_units x num_properties) -- loaded from DSN2 binary
    std::vector<float>      _property_table;

    // Shared instance encoder (2 linear layers with ReLU)
    LinearLayer             _enc_linear1;    // (token_dim -> encoder_hidden)
    LinearLayer             _enc_linear2;    // (encoder_hidden -> encoder_hidden)

    // Supply encoder (2 linear layers with ReLU)
    LinearLayer             _sup_linear1;    // (3 -> supply_hidden)
    LinearLayer             _sup_linear2;    // (supply_hidden -> supply_hidden)

    // Value head (3 linear layers: Linear->ReLU->Linear->ReLU->Linear)
    LinearLayer             _val_linear1;    // (302 -> value_hidden)
    LinearLayer             _val_linear2;    // (value_hidden -> value_hidden)
    LinearLayer             _val_linear3;    // (value_hidden -> 1)

    // Unit display name -> unit_index position
    std::unordered_map<std::string, int> _unitNameToIndex;

    // Engine CardType ID -> unit_index position (-1 if unmapped)
    std::vector<int>        _cardTypeToUnitIndex;

    bool _loaded;

    // Pre-allocated scratch buffers for evaluateValue() (avoid per-call heap allocs)
    // Mutable because evaluateValue() is const but needs to reuse these buffers.
    // Thread safety: evaluation is single-threaded per NeuralNet instance.
    struct ScratchBuffers
    {
        std::vector<float> p0_pool, p1_pool;
        std::vector<float> token, h1, encoded;
        std::vector<float> supplyData;
        std::vector<float> supply_pool, sh1, senc;
        std::vector<float> combined;
        std::vector<float> vh1, vh2;
    };
    mutable ScratchBuffers _scratch;

    void allocateScratchBuffers();

    static void linearForward(const LinearLayer & layer, const float * input, float * output);
    static void reluInPlace(float * data, int size);

    void extractInstanceFeatures(const Card & card, int unitIdx, float * out) const;
    bool loadUnitIndex();

public:

    NeuralNet();

    bool loadWeights(const std::string & filename);
    void buildCardTypeMapping();
    bool isLoaded() const;

    // DeepSets is value-only; evaluate() kept for backward compatibility (returns empty policy)
    struct NeuralOutput
    {
        std::vector<float> policy;  // empty (DeepSets has no policy head)
        float value;                // [-1, 1] win probability for P0
    };

    NeuralOutput evaluate(const GameState & state) const;
    double evaluateValue(const GameState & state, const PlayerID maxPlayer) const;
    int getUnitIndex(int cardTypeID) const;
    int numUnits() const { return _config.num_units; }

    void dumpFeaturesToFile(const GameState & state, const std::string & path) const;

    static NeuralNet & Instance();
};

}
