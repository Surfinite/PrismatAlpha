#include "NeuralNet.h"
#include "CardTypes.h"
#include <fstream>
#include <cmath>
#include <cstring>
#include <algorithm>

using namespace Prismata;

NeuralNet::NeuralNet()
    : _stateDim(0)
    , _numUnits(0)
    , _hiddenDim(0)
    , _numLayers(0)
    , _loaded(false)
{
}

NeuralNet & NeuralNet::Instance()
{
    static NeuralNet instance;
    return instance;
}

bool NeuralNet::isLoaded() const
{
    return _loaded;
}

// --- Binary file reading helpers ---

static bool readU32(std::ifstream & f, uint32_t & val)
{
    f.read(reinterpret_cast<char*>(&val), 4);
    return f.good();
}

static bool readString(std::ifstream & f, std::string & str, uint32_t len)
{
    std::vector<char> buf(len);
    f.read(buf.data(), len);
    if (!f.good()) return false;
    str.assign(buf.data(), len - 1); // exclude null terminator
    return true;
}

static bool readFloats(std::ifstream & f, std::vector<float> & data, size_t count)
{
    data.resize(count);
    f.read(reinterpret_cast<char*>(data.data()), count * sizeof(float));
    return f.good();
}

// Read a tensor from the binary file and verify its name matches
static bool readTensor(std::ifstream & f, const std::string & expectedName,
                       std::vector<float> & data, std::vector<uint32_t> & shape)
{
    uint32_t nameLen = 0;
    if (!readU32(f, nameLen)) return false;

    std::string name;
    if (!readString(f, name, nameLen)) return false;

    if (name != expectedName)
    {
        printf("NeuralNet: expected tensor '%s', got '%s'\n", expectedName.c_str(), name.c_str());
        return false;
    }

    uint32_t numDims = 0;
    if (!readU32(f, numDims)) return false;

    shape.resize(numDims);
    size_t totalSize = 1;
    for (uint32_t i = 0; i < numDims; ++i)
    {
        if (!readU32(f, shape[i])) return false;
        totalSize *= shape[i];
    }

    return readFloats(f, data, totalSize);
}

bool NeuralNet::readLinearLayer(std::ifstream & f, LinearLayer & layer, const std::string & expectedName)
{
    std::vector<uint32_t> shape;

    // Weight
    if (!readTensor(f, expectedName + ".weight", layer.weight, shape)) return false;
    layer.out_dim = shape[0];
    layer.in_dim = shape[1];

    // Bias
    if (!readTensor(f, expectedName + ".bias", layer.bias, shape)) return false;

    return true;
}

bool NeuralNet::readLayerNormParams(std::ifstream & f, LayerNormParams & params, const std::string & expectedName)
{
    std::vector<uint32_t> shape;

    // Gamma (weight)
    if (!readTensor(f, expectedName + ".weight", params.gamma, shape)) return false;
    params.dim = shape[0];

    // Beta (bias)
    if (!readTensor(f, expectedName + ".bias", params.beta, shape)) return false;

    return true;
}

bool NeuralNet::loadWeights(const std::string & filename)
{
    std::ifstream f(filename, std::ios::binary);
    if (!f.is_open())
    {
        printf("NeuralNet: could not open weight file: %s\n", filename.c_str());
        return false;
    }

    // Read header
    uint32_t magic, version, numTensors, numUnitNames;
    readU32(f, magic);
    readU32(f, version);
    readU32(f, (uint32_t&)_stateDim);
    readU32(f, (uint32_t&)_numUnits);
    readU32(f, (uint32_t&)_hiddenDim);
    readU32(f, (uint32_t&)_numLayers);
    readU32(f, numTensors);
    readU32(f, numUnitNames);

    if (magic != 0x504E4554)
    {
        printf("NeuralNet: bad magic number %08x\n", magic);
        return false;
    }

    printf("NeuralNet: loading weights (state_dim=%d, units=%d, hidden=%d, layers=%d)\n",
           _stateDim, _numUnits, _hiddenDim, _numLayers);

    // Read input projection
    if (!readLinearLayer(f, _inputProj, "input_proj")) return false;

    // Read trunk blocks
    _trunkBlocks.resize(_numLayers);
    for (int i = 0; i < _numLayers; ++i)
    {
        std::string prefix = "trunk." + std::to_string(i);
        if (!readLinearLayer(f, _trunkBlocks[i].linear1, prefix + ".linear1")) return false;
        if (!readLayerNormParams(f, _trunkBlocks[i].norm1, prefix + ".norm1")) return false;
        if (!readLinearLayer(f, _trunkBlocks[i].linear2, prefix + ".linear2")) return false;
        if (!readLayerNormParams(f, _trunkBlocks[i].norm2, prefix + ".norm2")) return false;
    }

    // Read policy head
    if (!readLinearLayer(f, _policyLinear1, "policy.linear1")) return false;
    if (!readLinearLayer(f, _policyLinear2, "policy.linear2")) return false;

    // Read value head
    if (!readLinearLayer(f, _valueLinear1, "value.linear1")) return false;
    if (!readLinearLayer(f, _valueLinear2, "value.linear2")) return false;

    // Read unit index
    _unitNameToIndex.clear();
    for (uint32_t i = 0; i < numUnitNames; ++i)
    {
        uint32_t idx, nameLen;
        readU32(f, idx);
        readU32(f, nameLen);

        std::string name;
        readString(f, name, nameLen);
        _unitNameToIndex[name] = idx;
    }

    printf("NeuralNet: loaded %u tensors, %u unit names\n", numTensors, numUnitNames);

    // Validate state_dim layout
    int numGlobalFeatures = _stateDim - _numUnits * 11;
    if (numGlobalFeatures < 0)
    {
        printf("NeuralNet: ERROR: state_dim=%d < numUnits*11=%d — weight file is corrupt\n",
               _stateDim, _numUnits * 11);
        return false;
    }
    if (numGlobalFeatures != 14 && numGlobalFeatures != 2)
    {
        printf("NeuralNet: WARNING: unexpected global feature count: %d (expected 14 or 2)\n",
               numGlobalFeatures);
    }
    printf("NeuralNet: feature layout: %d unit slots × 11 + %d global = %d state_dim\n",
           _numUnits, numGlobalFeatures, _stateDim);

    _loaded = true;

    // Try to validate against schema.json if it exists
    validateSchema();

    return true;
}

void NeuralNet::buildCardTypeMapping()
{
    if (!_loaded) return;

    const auto & allTypes = CardTypes::GetAllCardTypes();
    size_t maxID = 0;
    for (const auto & type : allTypes)
    {
        if (type.getID() > maxID) maxID = type.getID();
    }

    _cardTypeToUnitIndex.assign(maxID + 1, -1);

    int mapped = 0;
    int unmapped = 0;
    for (const auto & type : allTypes)
    {
        // Try UIName (display name) first — this matches the training data
        auto it = _unitNameToIndex.find(type.getUIName());
        if (it != _unitNameToIndex.end())
        {
            _cardTypeToUnitIndex[type.getID()] = it->second;
            mapped++;
        }
        else
        {
            // Try internal name as fallback
            it = _unitNameToIndex.find(type.getName());
            if (it != _unitNameToIndex.end())
            {
                _cardTypeToUnitIndex[type.getID()] = it->second;
                mapped++;
            }
            else
            {
                if (unmapped < 10)
                {
                    printf("NeuralNet: UNMAPPED type id=%d name='%s' uiName='%s'\n",
                           type.getID(), type.getName().c_str(), type.getUIName().c_str());
                }
                unmapped++;
            }
        }
    }

    printf("NeuralNet: mapped %d / %zu engine card types (%d unmapped)\n", mapped, allTypes.size(), unmapped);

#ifdef NEURAL_NET_DEBUG
    printf("NeuralNet: _unitNameToIndex has %zu entries, _cardTypeToUnitIndex has %zu entries\n",
           _unitNameToIndex.size(), _cardTypeToUnitIndex.size());

    for (const auto & type : allTypes)
    {
        if (type.getUIName() == "Drone" || type.getUIName() == "Engineer" || type.getUIName() == "Thorium Dynamo")
        {
            int idx = (type.getID() < _cardTypeToUnitIndex.size()) ? _cardTypeToUnitIndex[type.getID()] : -999;
            printf("NeuralNet: '%s' (id=%d) -> unitIdx=%d\n", type.getUIName().c_str(), type.getID(), idx);
        }
    }
#endif
}

// --- Feature extraction ---
// Converts a GameState into a 1785-dim feature vector for neural net inference.
// Layout: 161 unit types × 11 features each + 14 global features.
// Per-unit features (at unitIdx*11): [P0 ready, P0 constructing, P0 exhausted, P0 blocking,
//   P1 ready, P1 constructing, P1 exhausted, P1 blocking, P0 supply, P1 supply, in_card_set]
// Global features (at 161*11=1771): [P0 gold/blue/red/green/energy/attack, P1 same, turn, active_player]
// All values normalized to ~[0,1] via clamp-divide (see training/FEATURES.md and training/schema.json).

void NeuralNet::extractFeatures(const GameState & state, std::vector<float> & features) const
{
    static bool firstCall = true;

    features.assign(_stateDim, 0.0f);

    int unitsMapped = 0;
    int unitsSkipped = 0;

    // Per-player unit features
    for (PlayerID player = 0; player < 2; ++player)
    {
        int offset = (player == 0) ? 0 : 4;
        const CardIDVector & cardIDs = state.getCardIDs(player);

        for (size_t c = 0; c < cardIDs.size(); ++c)
        {
            const Card & card = state.getCardByID(cardIDs[c]);
            if (card.isDead()) continue;

            CardID typeID = card.getType().getID();
            if (typeID >= _cardTypeToUnitIndex.size())
            {
                unitsSkipped++;
                continue;
            }

            int unitIdx = _cardTypeToUnitIndex[typeID];
            if (unitIdx < 0)
            {
                unitsSkipped++;
                continue;
            }

            int base = unitIdx * 11 + offset;

            // Bounds safety: ensure we don't write past the unit feature region
            if (base + 3 >= _numUnits * 11)
            {
                unitsSkipped++;
                continue;
            }

            unitsMapped++;

            if (card.isUnderConstruction())
            {
                features[base + 2] += 1.0f;  // constructing
            }
            else if (card.getStatus() == CardStatus::Assigned)
            {
                features[base + 3] += 1.0f;  // blocking
            }
            else if (card.canUseAbility())
            {
                features[base + 0] += 1.0f;  // ready
            }
            else
            {
                features[base + 1] += 1.0f;  // exhausted
            }
        }
    }

    // Supply and card set
    int supplyMapped = 0;
    for (CardID i = 0; i < state.numCardsBuyable(); ++i)
    {
        const CardBuyable & cb = state.getCardBuyableByIndex(i);
        CardID typeID = cb.getType().getID();
        if (typeID >= _cardTypeToUnitIndex.size()) continue;

        int unitIdx = _cardTypeToUnitIndex[typeID];
        if (unitIdx < 0) continue;

        int base = unitIdx * 11;
        if (base + 10 >= _numUnits * 11) continue;  // bounds safety
        features[base + 8] = (float)cb.getSupplyRemaining(Players::Player_One);
        features[base + 9] = (float)cb.getSupplyRemaining(Players::Player_Two);
        features[base + 10] = 1.0f;  // in card set
        supplyMapped++;
    }

    // Global features (14 total) — order and normalization MUST match schema.json / FEATURES.md
    // Normalization: clamp_divide(value, cap) = min(value, cap) / cap → range [0, 1]
    // Layout: p0 resources (6), p1 resources (6), turn_number (1), active_player (1)
    int globalBase = _numUnits * 11;
    int numGlobalSlots = _stateDim - globalBase;

    if (numGlobalSlots >= 14)
    {
        const Resources & p0res = state.getResources(Players::Player_One);
        const Resources & p1res = state.getResources(Players::Player_Two);

        // P0 resources with clamp_divide normalization (caps from schema.json)
        features[globalBase + 0]  = std::min((float)p0res.amountOf(Resources::Gold),   20.0f) / 20.0f;
        features[globalBase + 1]  = std::min((float)p0res.amountOf(Resources::Blue),    5.0f) /  5.0f;
        features[globalBase + 2]  = std::min((float)p0res.amountOf(Resources::Red),     5.0f) /  5.0f;
        features[globalBase + 3]  = std::min((float)p0res.amountOf(Resources::Green),  15.0f) / 15.0f;
        features[globalBase + 4]  = std::min((float)p0res.amountOf(Resources::Energy), 10.0f) / 10.0f;
        features[globalBase + 5]  = std::min((float)state.getAttack(Players::Player_One), 25.0f) / 25.0f;

        // P1 resources with clamp_divide normalization
        features[globalBase + 6]  = std::min((float)p1res.amountOf(Resources::Gold),   20.0f) / 20.0f;
        features[globalBase + 7]  = std::min((float)p1res.amountOf(Resources::Blue),    5.0f) /  5.0f;
        features[globalBase + 8]  = std::min((float)p1res.amountOf(Resources::Red),     5.0f) /  5.0f;
        features[globalBase + 9]  = std::min((float)p1res.amountOf(Resources::Green),  15.0f) / 15.0f;
        features[globalBase + 10] = std::min((float)p1res.amountOf(Resources::Energy), 10.0f) / 10.0f;
        features[globalBase + 11] = std::min((float)state.getAttack(Players::Player_Two), 25.0f) / 25.0f;

        // Turn number: clamp to [0,30], divide by 30
        features[globalBase + 12] = std::min((float)state.getTurnNumber(), 30.0f) / 30.0f;

        // Active player: raw (0 or 1)
        features[globalBase + 13] = (float)state.getActivePlayer();
    }
    else if (numGlobalSlots >= 2)
    {
        // Legacy 2-feature layout (older weight files)
        features[globalBase + 0] = std::min((float)state.getTurnNumber(), 30.0f) / 30.0f;
        features[globalBase + 1] = (float)state.getActivePlayer();
    }

#ifdef NEURAL_NET_DEBUG
    if (firstCall)
    {
        int nonZero = 0;
        for (int i = 0; i < _stateDim; ++i)
        {
            if (features[i] != 0.0f) nonZero++;
        }
        printf("NeuralNet::extractFeatures DIAGNOSTIC (first call):\n");
        printf("  Cards mapped: %d, skipped: %d\n", unitsMapped, unitsSkipped);
        printf("  Supply types mapped: %d / %d\n", supplyMapped, (int)state.numCardsBuyable());
        printf("  Non-zero features: %d / %d\n", nonZero, _stateDim);
        printf("  _cardTypeToUnitIndex size: %zu\n", _cardTypeToUnitIndex.size());
        printf("  Global feature slots: %d (at indices %d..%d)\n", numGlobalSlots, globalBase, _stateDim - 1);
        if (numGlobalSlots >= 14)
        {
            printf("  P0 resources [gold=%g, blue=%g, red=%g, green=%g, energy=%g, attack=%g]\n",
                   features[globalBase+0], features[globalBase+1], features[globalBase+2],
                   features[globalBase+3], features[globalBase+4], features[globalBase+5]);
        }
        else if (numGlobalSlots >= 2)
        {
            printf("  Legacy global: [turn/50=%g, active_player=%g]\n",
                   features[globalBase+0], features[globalBase+1]);
        }
        firstCall = false;
    }
#endif
}

// --- Forward pass primitives ---

void NeuralNet::linearForward(const LinearLayer & layer, const float * input, float * output)
{
    for (int j = 0; j < layer.out_dim; ++j)
    {
        float sum = layer.bias[j];
        const float * row = &layer.weight[j * layer.in_dim];
        for (int i = 0; i < layer.in_dim; ++i)
        {
            sum += row[i] * input[i];
        }
        output[j] = sum;
    }
}

void NeuralNet::layerNormForward(const LayerNormParams & params, float * data)
{
    const int dim = params.dim;
    const float eps = 1e-5f;

    float mean = 0.0f;
    for (int i = 0; i < dim; ++i) mean += data[i];
    mean /= dim;

    float var = 0.0f;
    for (int i = 0; i < dim; ++i)
    {
        float d = data[i] - mean;
        var += d * d;
    }
    var /= dim;

    float inv_std = 1.0f / sqrtf(var + eps);
    for (int i = 0; i < dim; ++i)
    {
        data[i] = params.gamma[i] * (data[i] - mean) * inv_std + params.beta[i];
    }
}

void NeuralNet::reluInPlace(float * data, int size)
{
    for (int i = 0; i < size; ++i)
    {
        if (data[i] < 0.0f) data[i] = 0.0f;
    }
}

// --- Full inference ---
// Runs the full neural net: extractFeatures → input projection → residual blocks → policy + value heads.
// Returns NeuralOutput with:
//   .policy: raw logits per unit type (161 values, NOT softmaxed — caller must softmax if needed)
//   .value:  tanh output in [-1, 1] from the active player's perspective (positive = active player winning)
// Architecture: Linear(1785→512) → N×ResBlock(512) → policy head (512→256→161) + value head (512→256→1→tanh)
// Note: policy head output is currently unused by search (future: PUCT move ordering in UCTSearch).

NeuralNet::NeuralOutput NeuralNet::evaluate(const GameState & state) const
{
    NeuralOutput output;

    // Extract features
    std::vector<float> features;
    extractFeatures(state, features);

    // Trunk: input projection
    std::vector<float> h(_hiddenDim);
    linearForward(_inputProj, features.data(), h.data());
    reluInPlace(h.data(), _hiddenDim);

    // Trunk: residual blocks
    std::vector<float> blockOut(_hiddenDim);
    for (int b = 0; b < _numLayers; ++b)
    {
        const auto & block = _trunkBlocks[b];

        // First linear + layernorm + relu
        linearForward(block.linear1, h.data(), blockOut.data());
        layerNormForward(block.norm1, blockOut.data());
        reluInPlace(blockOut.data(), _hiddenDim);

        // Second linear + layernorm
        std::vector<float> blockOut2(_hiddenDim);
        linearForward(block.linear2, blockOut.data(), blockOut2.data());
        layerNormForward(block.norm2, blockOut2.data());

        // ReLU on block output, then residual add
        for (int i = 0; i < _hiddenDim; ++i)
        {
            float relu_out = blockOut2[i] > 0.0f ? blockOut2[i] : 0.0f;
            h[i] = h[i] + relu_out;
        }
    }

    // Policy head
    output.policy.resize(_numUnits);
    std::vector<float> policyHidden(_policyLinear1.out_dim);
    linearForward(_policyLinear1, h.data(), policyHidden.data());
    reluInPlace(policyHidden.data(), _policyLinear1.out_dim);
    linearForward(_policyLinear2, policyHidden.data(), output.policy.data());

    // Value head
    std::vector<float> valueHidden(_valueLinear1.out_dim);
    linearForward(_valueLinear1, h.data(), valueHidden.data());
    reluInPlace(valueHidden.data(), _valueLinear1.out_dim);

    float rawValue = 0.0f;
    linearForward(_valueLinear2, valueHidden.data(), &rawValue);
    output.value = tanhf(rawValue);

    return output;
}

// Value-only inference (skips policy head for speed). Returns [-1, 1] from maxPlayer's perspective.
// If maxPlayer == activePlayer, returns the raw tanh output; otherwise negates it.
// Used by AlphaBeta and UCT leaf evaluation when only the position score is needed.
double NeuralNet::evaluateValue(const GameState & state, const PlayerID maxPlayer) const
{
    // Extract features
    std::vector<float> features;
    extractFeatures(state, features);

    // Trunk: input projection
    std::vector<float> h(_hiddenDim);
    linearForward(_inputProj, features.data(), h.data());
    reluInPlace(h.data(), _hiddenDim);

    // Trunk: residual blocks
    std::vector<float> blockOut(_hiddenDim);
    for (int b = 0; b < _numLayers; ++b)
    {
        const auto & block = _trunkBlocks[b];

        linearForward(block.linear1, h.data(), blockOut.data());
        layerNormForward(block.norm1, blockOut.data());
        reluInPlace(blockOut.data(), _hiddenDim);

        std::vector<float> blockOut2(_hiddenDim);
        linearForward(block.linear2, blockOut.data(), blockOut2.data());
        layerNormForward(block.norm2, blockOut2.data());

        // ReLU on block output, then residual add
        for (int i = 0; i < _hiddenDim; ++i)
        {
            float relu_out = blockOut2[i] > 0.0f ? blockOut2[i] : 0.0f;
            h[i] = h[i] + relu_out;
        }
    }

    // Value head only
    std::vector<float> valueHidden(_valueLinear1.out_dim);
    linearForward(_valueLinear1, h.data(), valueHidden.data());
    reluInPlace(valueHidden.data(), _valueLinear1.out_dim);

    float rawValue = 0.0f;
    linearForward(_valueLinear2, valueHidden.data(), &rawValue);
    float value = tanhf(rawValue);  // [-1, 1] from active player's perspective

    // The network predicts from the active player's perspective.
    // If maxPlayer == activePlayer, return as-is. Otherwise negate.
    PlayerID activePlayer = state.getActivePlayer();
    if (maxPlayer != activePlayer)
    {
        value = -value;
    }

    return (double)value;
}

int NeuralNet::getUnitIndex(int cardTypeID) const
{
    if (cardTypeID < 0 || cardTypeID >= (int)_cardTypeToUnitIndex.size())
    {
        return -1;
    }
    return _cardTypeToUnitIndex[cardTypeID];
}

void NeuralNet::validateSchema() const
{
    // Try multiple paths for schema.json
    const char * schemaPaths[] = {
        "training/schema.json",
        "../training/schema.json",
        "asset/config/schema.json",
    };

    std::string schemaContent;
    std::string foundPath;
    for (const char * path : schemaPaths)
    {
        std::ifstream f(path);
        if (f.good())
        {
            schemaContent.assign(std::istreambuf_iterator<char>(f),
                                 std::istreambuf_iterator<char>());
            foundPath = path;
            break;
        }
    }

    if (schemaContent.empty())
    {
        printf("NeuralNet: schema.json not found (Context 2 hasn't delivered it yet). "
               "Skipping cross-language validation.\n");
        return;
    }

    printf("NeuralNet: validating against %s\n", foundPath.c_str());

    // Parse with RapidJSON
    rapidjson::Document doc;
    if (doc.Parse(schemaContent.c_str()).HasParseError())
    {
        printf("NeuralNet: WARNING: schema.json parse error\n");
        return;
    }

    // Check feature_version
    if (doc.HasMember("feature_version") && doc["feature_version"].IsInt())
    {
        printf("NeuralNet: schema feature_version = %d\n", doc["feature_version"].GetInt());
    }

    // Check state_dim
    if (doc.HasMember("state_dim") && doc["state_dim"].IsInt())
    {
        int schemaStateDim = doc["state_dim"].GetInt();
        if (schemaStateDim != _stateDim)
        {
            printf("NeuralNet: ERROR: state_dim mismatch! schema=%d, weights=%d\n",
                   schemaStateDim, _stateDim);
        }
        else
        {
            printf("NeuralNet: state_dim matches schema: %d\n", _stateDim);
        }
    }

    // Check unit_index_hash
    if (doc.HasMember("unit_index_hash") && doc["unit_index_hash"].IsString())
    {
        const char * expectedHash = doc["unit_index_hash"].GetString();

        // Compute hash of our unit names: SHA-256 of newline-joined sorted names
        // For now, just report the expected hash — full SHA-256 requires a library
        // or manual implementation. Report name count for sanity check.
        std::vector<std::string> sortedNames;
        for (const auto & pair : _unitNameToIndex)
        {
            sortedNames.push_back(pair.first);
        }
        std::sort(sortedNames.begin(), sortedNames.end());

        printf("NeuralNet: schema expects unit_index_hash = %.16s...\n", expectedHash);
        printf("NeuralNet: loaded %zu unit names (hash comparison requires SHA-256 impl)\n",
               sortedNames.size());
    }
}

void NeuralNet::dumpFeaturesToFile(const GameState & state, const std::string & path) const
{
    if (!_loaded)
    {
        printf("NeuralNet: cannot dump features — not loaded\n");
        return;
    }

    // Extract features
    std::vector<float> features;
    extractFeatures(state, features);

    // Write feature values
    {
        std::ofstream f(path);
        if (!f.is_open())
        {
            printf("NeuralNet: cannot open %s for writing\n", path.c_str());
            return;
        }

        f << _stateDim << "\n";
        f.precision(8);
        for (int i = 0; i < _stateDim; ++i)
        {
            f << features[i] << "\n";
        }
        printf("NeuralNet: dumped %d features to %s\n", _stateDim, path.c_str());
    }

    // Write companion state description
    std::string descPath = path + ".desc";
    {
        std::ofstream f(descPath);
        if (!f.is_open()) return;

        f << "=== Game State Description ===\n";
        f << "Turn: " << state.getTurnNumber() << "\n";
        f << "Active player: " << (int)state.getActivePlayer() << "\n";
        f << "Phase: " << state.getActivePhase() << "\n";

        const Resources & p0res = state.getResources(Players::Player_One);
        const Resources & p1res = state.getResources(Players::Player_Two);
        f << "\nP0 resources: gold=" << (int)p0res.amountOf(Resources::Gold)
          << " blue=" << (int)p0res.amountOf(Resources::Blue)
          << " red=" << (int)p0res.amountOf(Resources::Red)
          << " green=" << (int)p0res.amountOf(Resources::Green)
          << " energy=" << (int)p0res.amountOf(Resources::Energy)
          << " attack=" << (int)state.getAttack(Players::Player_One) << "\n";
        f << "P1 resources: gold=" << (int)p1res.amountOf(Resources::Gold)
          << " blue=" << (int)p1res.amountOf(Resources::Blue)
          << " red=" << (int)p1res.amountOf(Resources::Red)
          << " green=" << (int)p1res.amountOf(Resources::Green)
          << " energy=" << (int)p1res.amountOf(Resources::Energy)
          << " attack=" << (int)state.getAttack(Players::Player_Two) << "\n";

        for (PlayerID p = 0; p < 2; ++p)
        {
            f << "\nPlayer " << (int)p << " units:\n";
            const CardIDVector & ids = state.getCardIDs(p);
            for (size_t i = 0; i < ids.size(); ++i)
            {
                const Card & card = state.getCardByID(ids[i]);
                if (card.isDead()) continue;
                int unitIdx = getUnitIndex(card.getType().getID());
                f << "  " << card.getType().getUIName()
                  << " (typeID=" << card.getType().getID()
                  << ", unitIdx=" << unitIdx
                  << ", constr=" << card.isUnderConstruction()
                  << ", canUse=" << card.canUseAbility()
                  << ", assigned=" << (card.getStatus() == CardStatus::Assigned ? 1 : 0)
                  << ")\n";
            }
        }

        f << "\nBuyable cards: " << state.numCardsBuyable() << "\n";
        for (CardID i = 0; i < state.numCardsBuyable(); ++i)
        {
            const CardBuyable & cb = state.getCardBuyableByIndex(i);
            int unitIdx = getUnitIndex(cb.getType().getID());
            f << "  " << cb.getType().getUIName()
              << " (unitIdx=" << unitIdx
              << ", p0_supply=" << cb.getSupplyRemaining(Players::Player_One)
              << ", p1_supply=" << cb.getSupplyRemaining(Players::Player_Two)
              << ")\n";
        }

        f << "\n=== Feature vector summary ===\n";
        int nonZero = 0;
        for (int i = 0; i < _stateDim; ++i)
        {
            if (features[i] != 0.0f) nonZero++;
        }
        f << "state_dim=" << _stateDim << ", nonzero=" << nonZero << "\n";

        printf("NeuralNet: dumped state description to %s\n", descPath.c_str());
    }
}
