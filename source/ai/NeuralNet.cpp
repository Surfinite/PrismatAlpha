#include "NeuralNet.h"
#include "CardTypes.h"
#include <fstream>
#include <cmath>
#include <cstring>
#include <algorithm>

#include "rapidjson/document.h"

using namespace Prismata;

NeuralNet::NeuralNet()
    : _config()
    , _loaded(false)
{
    std::memset(&_config, 0, sizeof(_config));
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

// ---------------------------------------------------------------------------
// Binary file reading helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Unit index loading (JSON)
// ---------------------------------------------------------------------------

bool NeuralNet::loadUnitIndex()
{
    const char * paths[] = {
        "training/data/unit_index.json",
        "../training/data/unit_index.json",
        "asset/config/unit_index.json",
    };

    std::ifstream f;
    std::string foundPath;
    for (const char * path : paths)
    {
        f.open(path);
        if (f.good())
        {
            foundPath = path;
            break;
        }
        f.clear();
    }

    if (!f.is_open())
    {
        printf("NeuralNet: could not find unit_index.json\n");
        return false;
    }

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());
    f.close();

    rapidjson::Document doc;
    doc.Parse(content.c_str());

    if (doc.HasParseError())
    {
        printf("NeuralNet: unit_index.json parse error\n");
        return false;
    }

    if (!doc.HasMember("units") || !doc["units"].IsObject())
    {
        printf("NeuralNet: unit_index.json missing 'units' object\n");
        return false;
    }

    _unitNameToIndex.clear();
    const auto & units = doc["units"];
    for (auto it = units.MemberBegin(); it != units.MemberEnd(); ++it)
    {
        _unitNameToIndex[it->name.GetString()] = it->value.GetInt();
    }

    printf("NeuralNet: loaded %zu unit names from %s\n", _unitNameToIndex.size(), foundPath.c_str());
    return true;
}

// ---------------------------------------------------------------------------
// Load weights (DSN2 format)
// ---------------------------------------------------------------------------

bool NeuralNet::loadWeights(const std::string & filename)
{
    std::ifstream f(filename, std::ios::binary);
    if (!f.is_open())
    {
        printf("NeuralNet: could not open weight file: %s\n", filename.c_str());
        return false;
    }

    // Read DSN2 header: 9 x uint32 = 36 bytes
    uint32_t header[9];
    for (int i = 0; i < 9; ++i)
    {
        if (!readU32(f, header[i]))
        {
            printf("NeuralNet: failed to read header field %d\n", i);
            return false;
        }
    }

    uint32_t magic      = header[0];
    uint32_t version    = header[1];
    uint32_t numTensors = header[8];

    if (magic == 0x504E4554)
    {
        printf("NeuralNet: PNET (V1) format detected -- please use DSN2 format weights\n");
        return false;
    }

    if (magic != 0x44534E32)
    {
        printf("NeuralNet: bad magic number %08x (expected DSN2 = 0x44534E32)\n", magic);
        return false;
    }

    _config.num_units           = (int)header[2];
    _config.d_embed             = (int)header[3];
    _config.num_properties      = (int)header[4];
    _config.encoder_hidden      = (int)header[5];
    _config.supply_hidden       = (int)header[6];
    _config.value_hidden        = (int)header[7];
    _config.num_instance_features = 10;  // fixed by design

    printf("NeuralNet: loading DSN2 weights v%u (units=%d, d_embed=%d, props=%d, "
           "enc_h=%d, sup_h=%d, val_h=%d, tensors=%u)\n",
           version, _config.num_units, _config.d_embed, _config.num_properties,
           _config.encoder_hidden, _config.supply_hidden, _config.value_hidden, numTensors);

    if (numTensors != 16)
    {
        printf("NeuralNet: expected 16 tensors, got %u\n", numTensors);
        return false;
    }

    // 1. Unit embedding (num_units x d_embed)
    std::vector<uint32_t> shape;
    if (!readTensor(f, "unit_embedding.weight", _embedding_table, shape)) return false;

    // 2-5. Instance encoder
    if (!readTensor(f, "instance_encoder.0.weight", _enc_linear1.weight, shape)) return false;
    _enc_linear1.out_dim = shape[0];
    _enc_linear1.in_dim = shape[1];
    if (!readTensor(f, "instance_encoder.0.bias", _enc_linear1.bias, shape)) return false;

    if (!readTensor(f, "instance_encoder.2.weight", _enc_linear2.weight, shape)) return false;
    _enc_linear2.out_dim = shape[0];
    _enc_linear2.in_dim = shape[1];
    if (!readTensor(f, "instance_encoder.2.bias", _enc_linear2.bias, shape)) return false;

    // 6-9. Supply encoder
    if (!readTensor(f, "supply_encoder.0.weight", _sup_linear1.weight, shape)) return false;
    _sup_linear1.out_dim = shape[0];
    _sup_linear1.in_dim = shape[1];
    if (!readTensor(f, "supply_encoder.0.bias", _sup_linear1.bias, shape)) return false;

    if (!readTensor(f, "supply_encoder.2.weight", _sup_linear2.weight, shape)) return false;
    _sup_linear2.out_dim = shape[0];
    _sup_linear2.in_dim = shape[1];
    if (!readTensor(f, "supply_encoder.2.bias", _sup_linear2.bias, shape)) return false;

    // 10-15. Value head (3 linear layers)
    if (!readTensor(f, "value_head.0.weight", _val_linear1.weight, shape)) return false;
    _val_linear1.out_dim = shape[0];
    _val_linear1.in_dim = shape[1];
    if (!readTensor(f, "value_head.0.bias", _val_linear1.bias, shape)) return false;

    if (!readTensor(f, "value_head.3.weight", _val_linear2.weight, shape)) return false;
    _val_linear2.out_dim = shape[0];
    _val_linear2.in_dim = shape[1];
    if (!readTensor(f, "value_head.3.bias", _val_linear2.bias, shape)) return false;

    if (!readTensor(f, "value_head.6.weight", _val_linear3.weight, shape)) return false;
    _val_linear3.out_dim = shape[0];
    _val_linear3.in_dim = shape[1];
    if (!readTensor(f, "value_head.6.bias", _val_linear3.bias, shape)) return false;

    // 16. Property table (num_units x num_properties)
    if (!readTensor(f, "property_table", _property_table, shape)) return false;

    printf("NeuralNet: loaded 16 tensors from DSN2 binary\n");

    // Validate expected dimensions
    int tokenDim = _config.d_embed + _config.num_properties + _config.num_instance_features;
    if (_enc_linear1.in_dim != tokenDim)
    {
        printf("NeuralNet: WARNING: encoder input dim %d != expected token_dim %d\n",
               _enc_linear1.in_dim, tokenDim);
    }

    int combinedDim = _config.encoder_hidden * 2 + _config.supply_hidden + 14;
    if (_val_linear1.in_dim != combinedDim)
    {
        printf("NeuralNet: WARNING: value head input dim %d != expected combined_dim %d\n",
               _val_linear1.in_dim, combinedDim);
    }

    // Load unit name -> index mapping from unit_index.json
    if (!loadUnitIndex())
    {
        printf("NeuralNet: WARNING: unit_index.json not loaded -- buildCardTypeMapping() will fail\n");
    }

    allocateScratchBuffers();

    _loaded = true;
    return true;
}

void NeuralNet::allocateScratchBuffers()
{
    const int ENC_H = _config.encoder_hidden;
    const int SUP_H = _config.supply_hidden;
    const int VAL_H = _config.value_hidden;
    const int TOKEN_DIM = _config.d_embed + _config.num_properties + _config.num_instance_features;
    const int COMBINED = ENC_H * 2 + SUP_H + 14;

    _scratch.p0_pool.resize(ENC_H);
    _scratch.p1_pool.resize(ENC_H);
    _scratch.token.resize(TOKEN_DIM);
    _scratch.h1.resize(ENC_H);
    _scratch.encoded.resize(ENC_H);
    _scratch.supplyData.resize(_config.num_units * 3);
    _scratch.supply_pool.resize(SUP_H);
    _scratch.sh1.resize(SUP_H);
    _scratch.senc.resize(SUP_H);
    _scratch.combined.resize(COMBINED);
    _scratch.vh1.resize(VAL_H);
    _scratch.vh2.resize(VAL_H);
}

// ---------------------------------------------------------------------------
// Card type mapping (engine CardType ID -> unit index)
// ---------------------------------------------------------------------------

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
        // Try UIName (display name) first -- this matches the training data
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
}

// ---------------------------------------------------------------------------
// Forward pass primitives
// ---------------------------------------------------------------------------

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

void NeuralNet::reluInPlace(float * data, int size)
{
    for (int i = 0; i < size; ++i)
    {
        if (data[i] < 0.0f) data[i] = 0.0f;
    }
}

// ---------------------------------------------------------------------------
// Instance feature extraction (10 floats per alive card instance)
// ---------------------------------------------------------------------------
// Feature order:
//   [0] owner           -- 0.0 = P0, 1.0 = P1
//   [1] is_constructing -- 1.0 if under construction
//   [2] build_time      -- max(constructionTime, currentDelay)
//   [3] is_blocking     -- 1.0 if Assigned AND ability NOT used this turn
//   [4] ability_used    -- 1.0 if ability was used this turn
//   [5] current_hp      -- raw HP (fragile: currentHealth; non-fragile: currentHealth - damageTaken)
//   [6] hp_ratio        -- current_hp / base_health (0 if base_health == 0)
//   [7] is_frozen       -- 1.0 if currentChill > 0
//   [8] lifespan        -- remaining turns to live (0 if immortal / lifespan < 0)
//   [9] charges         -- current charge count

void NeuralNet::extractInstanceFeatures(const Card & card, int unitIdx, float * out) const
{
    out[0] = (float)card.getPlayer();
    out[1] = card.isUnderConstruction() ? 1.0f : 0.0f;
    out[2] = (float)std::max(card.getConstructionTime(), card.getCurrentDelay());
    out[3] = (card.getStatus() == CardStatus::Assigned && !card.abilityUsedThisTurn()) ? 1.0f : 0.0f;
    out[4] = card.abilityUsedThisTurn() ? 1.0f : 0.0f;

    // base_health is at property index 5, fragile at index 6
    float baseHP = _property_table[unitIdx * _config.num_properties + 5];
    bool fragile = _property_table[unitIdx * _config.num_properties + 6] > 0.5f;
    float currentHP = fragile
        ? (float)card.currentHealth()
        : (float)(card.currentHealth() - card.getDamageTaken());
    out[5] = std::max(0.0f, currentHP);
    out[6] = baseHP > 0 ? std::max(0.0f, currentHP) / baseHP : 0.0f;
    out[7] = card.currentChill() > 0 ? 1.0f : 0.0f;

    int lifespan = card.getCurrentLifespan();
    out[8] = lifespan < 0 ? 0.0f : (float)std::max(0, lifespan);
    out[9] = (float)card.getCurrentCharges();
}

// ---------------------------------------------------------------------------
// DeepSets value inference
// ---------------------------------------------------------------------------
// Architecture:
//   1. For each alive unit instance:
//      - Build token = [embedding(32) | properties(13) | instance_state(10)] = 55
//      - Encode: Linear(55->128)->ReLU->Linear(128->128)->ReLU
//      - Sum-pool into owner's accumulator (P0 or P1)
//   2. For each of the 116 unit types:
//      - Supply input = [p0_supply, p1_supply, in_card_set] (3 floats)
//      - Encode: Linear(3->32)->ReLU->Linear(32->32)->ReLU
//      - Sum-pool into supply accumulator
//   3. Concatenate: [P0_pool(128) | P1_pool(128) | supply_pool(32) | globals(14)] = 302
//   4. Value MLP: Linear(302->256)->ReLU->Linear(256->256)->ReLU->Linear(256->1)
//   5. sigmoid -> map to [-1,1]

double NeuralNet::evaluateValue(const GameState & state, const PlayerID maxPlayer) const
{
    const int ENC_H = _config.encoder_hidden;
    const int SUP_H = _config.supply_hidden;
    const int VAL_H = _config.value_hidden;
    const int TOKEN_DIM = _config.d_embed + _config.num_properties + _config.num_instance_features;
    const int COMBINED = ENC_H * 2 + SUP_H + 14;

    // Zero-init per-player pooling accumulators (reuse pre-allocated scratch buffers)
    std::fill(_scratch.p0_pool.begin(), _scratch.p0_pool.end(), 0.0f);
    std::fill(_scratch.p1_pool.begin(), _scratch.p1_pool.end(), 0.0f);
    float * p0_pool = _scratch.p0_pool.data();
    float * p1_pool = _scratch.p1_pool.data();
    float * token   = _scratch.token.data();
    float * h1      = _scratch.h1.data();
    float * encoded = _scratch.encoded.data();

    // --- 1. Process each alive unit instance ---
    for (PlayerID player = 0; player < 2; ++player)
    {
        const CardIDVector & cardIDs = state.getCardIDs(player);
        for (size_t c = 0; c < cardIDs.size(); ++c)
        {
            const Card & card = state.getCardByID(cardIDs[c]);
            if (card.isDead()) continue;

            CardID typeID = card.getType().getID();
            if (typeID >= _cardTypeToUnitIndex.size()) continue;
            int unitIdx = _cardTypeToUnitIndex[typeID];
            if (unitIdx < 0) continue;

            // Build token: [embedding(d_embed) | properties(num_properties) | instance_state(10)]
            const float * emb = &_embedding_table[unitIdx * _config.d_embed];
            std::memcpy(token, emb, _config.d_embed * sizeof(float));

            const float * props = &_property_table[unitIdx * _config.num_properties];
            std::memcpy(token + _config.d_embed, props, _config.num_properties * sizeof(float));

            extractInstanceFeatures(card, unitIdx, token + _config.d_embed + _config.num_properties);

            // Shared encoder: Linear->ReLU->Linear->ReLU
            linearForward(_enc_linear1, token, h1);
            reluInPlace(h1, ENC_H);
            linearForward(_enc_linear2, h1, encoded);
            reluInPlace(encoded, ENC_H);

            // Accumulate into owner's pool
            float * pool = (card.getPlayer() == Players::Player_One) ? p0_pool : p1_pool;
            for (int i = 0; i < ENC_H; ++i)
            {
                pool[i] += encoded[i];
            }
        }
    }

    // --- 2. Process supply pathway (all 116 unit types) ---
    // Build a lookup table from unit index -> (p0_supply, p1_supply, in_card_set)
    // Default: [0, 0, 0] for units not in the card set
    std::fill(_scratch.supplyData.begin(), _scratch.supplyData.end(), 0.0f);
    float * supplyData = _scratch.supplyData.data();

    for (CardID i = 0; i < state.numCardsBuyable(); ++i)
    {
        const CardBuyable & cb = state.getCardBuyableByIndex(i);
        CardID typeID = cb.getType().getID();
        if (typeID >= _cardTypeToUnitIndex.size()) continue;
        int unitIdx = _cardTypeToUnitIndex[typeID];
        if (unitIdx < 0) continue;

        supplyData[unitIdx * 3 + 0] = (float)cb.getSupplyRemaining(Players::Player_One);
        supplyData[unitIdx * 3 + 1] = (float)cb.getSupplyRemaining(Players::Player_Two);
        supplyData[unitIdx * 3 + 2] = 1.0f;  // in_card_set = true
    }

    // Encode each unit type's supply and sum into pool
    std::fill(_scratch.supply_pool.begin(), _scratch.supply_pool.end(), 0.0f);
    float * supply_pool = _scratch.supply_pool.data();
    float * sh1  = _scratch.sh1.data();
    float * senc = _scratch.senc.data();

    for (int u = 0; u < _config.num_units; ++u)
    {
        linearForward(_sup_linear1, &supplyData[u * 3], sh1);
        reluInPlace(sh1, SUP_H);
        linearForward(_sup_linear2, sh1, senc);
        reluInPlace(senc, SUP_H);

        for (int j = 0; j < SUP_H; ++j)
        {
            supply_pool[j] += senc[j];
        }
    }

    // --- 3. Build combined vector ---
    // [p0_pool(ENC_H) | p1_pool(ENC_H) | supply_pool(SUP_H) | globals(14)] = COMBINED
    float * combined = _scratch.combined.data();
    int pos = 0;
    std::memcpy(combined + pos, p0_pool, ENC_H * sizeof(float));
    pos += ENC_H;
    std::memcpy(combined + pos, p1_pool, ENC_H * sizeof(float));
    pos += ENC_H;
    std::memcpy(combined + pos, supply_pool, SUP_H * sizeof(float));
    pos += SUP_H;

    // Global features (14): V2 normalization caps
    const Resources & p0res = state.getResources(Players::Player_One);
    const Resources & p1res = state.getResources(Players::Player_Two);

    combined[pos++] = std::min((float)p0res.amountOf(Resources::Gold),   20.0f) / 20.0f;
    combined[pos++] = std::min((float)p0res.amountOf(Resources::Blue),    5.0f) /  5.0f;
    combined[pos++] = std::min((float)p0res.amountOf(Resources::Red),     5.0f) /  5.0f;
    combined[pos++] = std::min((float)p0res.amountOf(Resources::Green),  15.0f) / 15.0f;
    combined[pos++] = std::min((float)p0res.amountOf(Resources::Energy), 10.0f) / 10.0f;
    combined[pos++] = std::min((float)state.getAttack(Players::Player_One), 25.0f) / 25.0f;

    combined[pos++] = std::min((float)p1res.amountOf(Resources::Gold),   20.0f) / 20.0f;
    combined[pos++] = std::min((float)p1res.amountOf(Resources::Blue),    5.0f) /  5.0f;
    combined[pos++] = std::min((float)p1res.amountOf(Resources::Red),     5.0f) /  5.0f;
    combined[pos++] = std::min((float)p1res.amountOf(Resources::Green),  15.0f) / 15.0f;
    combined[pos++] = std::min((float)p1res.amountOf(Resources::Energy), 10.0f) / 10.0f;
    combined[pos++] = std::min((float)state.getAttack(Players::Player_Two), 25.0f) / 25.0f;

    combined[pos++] = std::min((float)state.getTurnNumber(), 50.0f) / 50.0f;
    combined[pos++] = (float)state.getActivePlayer();

    // --- 4. Value MLP: Linear->ReLU->Linear->ReLU->Linear ---
    float * vh1 = _scratch.vh1.data();
    linearForward(_val_linear1, combined, vh1);
    reluInPlace(vh1, VAL_H);

    float * vh2 = _scratch.vh2.data();
    linearForward(_val_linear2, vh1, vh2);
    reluInPlace(vh2, VAL_H);

    float logit = 0.0f;
    linearForward(_val_linear3, vh2, &logit);

    // Sigmoid -> [0,1] -> map to [-1,1]
    float prob = 1.0f / (1.0f + expf(-logit));
    float value = 2.0f * prob - 1.0f;  // [-1, 1] where +1 = P0 wins

    // Convert to maxPlayer's perspective
    if (maxPlayer != Players::Player_One)
    {
        value = -value;
    }

    return (double)value;
}

// Backward-compatible full evaluate() -- returns NeuralOutput with empty policy
NeuralNet::NeuralOutput NeuralNet::evaluate(const GameState & state) const
{
    NeuralOutput output;
    output.value = (float)evaluateValue(state, Players::Player_One);
    // DeepSets has no policy head; return empty policy vector
    return output;
}

int NeuralNet::getUnitIndex(int cardTypeID) const
{
    if (cardTypeID < 0 || cardTypeID >= (int)_cardTypeToUnitIndex.size())
    {
        return -1;
    }
    return _cardTypeToUnitIndex[cardTypeID];
}

// ---------------------------------------------------------------------------
// Debug feature dump
// ---------------------------------------------------------------------------

void NeuralNet::dumpFeaturesToFile(const GameState & state, const std::string & path) const
{
    if (!_loaded)
    {
        printf("NeuralNet: cannot dump features -- not loaded\n");
        return;
    }

    std::ofstream f(path);
    if (!f.is_open())
    {
        printf("NeuralNet: cannot open %s for writing\n", path.c_str());
        return;
    }

    f << "=== DeepSets Instance Dump ===\n";
    f << "Turn: " << state.getTurnNumber() << "\n";
    f << "Active player: " << (int)state.getActivePlayer() << "\n";

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

    float instFeats[10];
    for (PlayerID p = 0; p < 2; ++p)
    {
        f << "\nPlayer " << (int)p << " instances:\n";
        const CardIDVector & ids = state.getCardIDs(p);
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & card = state.getCardByID(ids[i]);
            if (card.isDead()) continue;
            int unitIdx = getUnitIndex(card.getType().getID());
            f << "  " << card.getType().getUIName()
              << " (unitIdx=" << unitIdx << ")";
            if (unitIdx >= 0)
            {
                extractInstanceFeatures(card, unitIdx, instFeats);
                f << " feats=[";
                for (int fi = 0; fi < 10; ++fi)
                {
                    if (fi > 0) f << ", ";
                    f << instFeats[fi];
                }
                f << "]";
            }
            f << "\n";
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

    // Compute and print the value
    double val = evaluateValue(state, Players::Player_One);
    f << "\nNeural value (P0 perspective): " << val << "\n";

    printf("NeuralNet: dumped DeepSets features to %s\n", path.c_str());
}
