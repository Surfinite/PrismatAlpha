// test_features.cpp — Standalone test for NeuralNet::extractFeatures()
//
// Purpose: Prove that extractFeatures() produces a non-zero feature vector
// for a GameState with known units. Diagnose the all-zeros bug.
//
// Build: Add to Prismata_Testing project (or compile separately linking
//        Prismata_AI.lib + Prismata_Engine.lib with include paths:
//        ../source/ai; ../source/engine; ../source/; ../source/json)
//
// Run: From bin/ directory:  test_features.exe
//      (needs asset/config/cardLibrary.jso and asset/config/neural_weights.bin)

#include "Prismata.h"
#include "NeuralNet.h"
#include "GameState.h"
#include "CardTypes.h"
#include "rapidjson/document.h"

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include <string>
#include <algorithm>
#include <fstream>

using namespace Prismata;

// ============================================================
// Test 1: Construct a GameState from JSON and call extractFeatures
// ============================================================
static bool testKnownState()
{
    printf("\n========================================\n");
    printf("TEST 1: extractFeatures on known state\n");
    printf("========================================\n");

    // Construct a mid-game state with known units:
    // P1 (white): 6 Drones, 2 Engineers, 1 Wall  (mana: 6 gold)
    // P2 (black): 7 Drones, 2 Engineers           (mana: 0)
    // Buyable: base set cards
    const char * jsonState = R"({
        "whiteMana": "6",
        "blackMana": "0",
        "phase": "action",
        "numTurns": 4,
        "table": [
            {"cardName":"Drone",    "color":0, "amount":6},
            {"cardName":"Engineer", "color":0, "amount":2},
            {"cardName":"Wall",     "color":0, "amount":1},
            {"cardName":"Drone",    "color":1, "amount":7},
            {"cardName":"Engineer", "color":1, "amount":2}
        ],
        "cards":["Drone","Engineer","Blastforge","Conduit","Academy",
                 "Gauss Cannon","Forcefield","Steelsplitter","Wall",
                 "Tarsier","Rhino"]
    })";

    rapidjson::Document doc;
    doc.Parse(jsonState);
    if (doc.HasParseError())
    {
        printf("FAIL: JSON parse error\n");
        return false;
    }

    GameState state(doc);

    // Verify the state has the expected units
    printf("\nGameState constructed. Verifying units:\n");
    for (PlayerID p = 0; p < 2; ++p)
    {
        const CardIDVector & ids = state.getCardIDs(p);
        printf("  Player %d: %zu live cards\n", p, ids.size());
        for (size_t i = 0; i < ids.size(); ++i)
        {
            const Card & card = state.getCardByID(ids[i]);
            printf("    [%zu] type=%d name='%s' uiName='%s' dead=%d constr=%d canUseAbility=%d\n",
                   i, card.getType().getID(),
                   card.getType().getName().c_str(),
                   card.getType().getUIName().c_str(),
                   card.isDead() ? 1 : 0,
                   card.isUnderConstruction() ? 1 : 0,
                   card.canUseAbility() ? 1 : 0);
        }
    }
    printf("  Buyable cards: %d\n", (int)state.numCardsBuyable());
    printf("  Turn number: %d\n", (int)state.getTurnNumber());
    printf("  Active player: %d\n", (int)state.getActivePlayer());
    printf("  P0 gold: %d\n", (int)state.getResources(Players::Player_One).amountOf(Resources::Gold));

    // Now call extractFeatures
    NeuralNet & net = NeuralNet::Instance();
    if (!net.isLoaded())
    {
        printf("\nWARNING: Neural net weights not loaded. Testing extractFeatures anyway.\n");
        printf("  _stateDim would be 0 -> features vector will be empty.\n");
        printf("  To test properly, ensure asset/config/neural_weights.bin exists.\n");

        // Even without weights, we can verify the state construction works.
        // Return true but note the limitation.
        printf("\nRESULT: SKIP (no weights loaded)\n");
        return true;
    }

    printf("\nNeural net loaded: stateDim=%d, numUnits=%d\n",
           net.stateDim(), net.numUnits());

    std::vector<float> features;
    net.extractFeatures(state, features);

    printf("\nFeature vector analysis:\n");
    printf("  features.size() = %zu\n", features.size());

    // Count non-zero entries
    int nonZeroCount = 0;
    double sumAbs = 0.0;
    double maxAbs = 0.0;

    for (size_t i = 0; i < features.size(); ++i)
    {
        if (features[i] != 0.0f)
        {
            nonZeroCount++;
        }
        double a = std::fabs((double)features[i]);
        sumAbs += a;
        if (a > maxAbs) maxAbs = a;
    }

    printf("  nonZeroCount = %d / %zu\n", nonZeroCount, features.size());
    printf("  sumAbs       = %.6f\n", sumAbs);
    printf("  maxAbs       = %.6f\n", maxAbs);

    // Print top-20 non-zero entries
    printf("\n  Top-20 non-zero features (index, value):\n");
    std::vector<std::pair<int, float>> nonZeros;
    for (size_t i = 0; i < features.size(); ++i)
    {
        if (features[i] != 0.0f)
        {
            nonZeros.push_back({(int)i, features[i]});
        }
    }
    // Sort by absolute value descending
    std::sort(nonZeros.begin(), nonZeros.end(),
              [](const std::pair<int,float> & a, const std::pair<int,float> & b) {
                  return std::fabs(a.second) > std::fabs(b.second);
              });
    for (size_t i = 0; i < std::min(nonZeros.size(), (size_t)20); ++i)
    {
        int idx = nonZeros[i].first;
        float val = nonZeros[i].second;
        int unitIdx = idx / 11;
        int featureSlot = idx % 11;
        const char * slotNames[] = {
            "p0_ready", "p0_exhaust", "p0_constr", "p0_block",
            "p1_ready", "p1_exhaust", "p1_constr", "p1_block",
            "p0_supply", "p1_supply", "in_set"
        };
        int numUnits = net.numUnits();
        int globalBase = numUnits * 11;
        if (idx >= globalBase)
        {
            int gi = idx - globalBase;
            const char * globalNames[] = {
                "p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
                "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
                "turn/30", "active_player"
            };
            const char * gname = (gi < 14) ? globalNames[gi] : "UNKNOWN_GLOBAL";
            printf("    [%4d] = %8.3f  (global: %s)\n", idx, val, gname);
        }
        else
        {
            printf("    [%4d] = %8.3f  (unit %d, slot %d=%s)\n",
                   idx, val, unitIdx, featureSlot,
                   (featureSlot < 11) ? slotNames[featureSlot] : "?");
        }
    }

    // Assertions
    bool pass = true;
    if (nonZeroCount == 0)
    {
        printf("\n  FAIL: ALL features are zero! Bug confirmed.\n");
        pass = false;
    }
    if (sumAbs < 1e-6)
    {
        printf("\n  FAIL: sumAbs < 1e-6 (effectively all zero).\n");
        pass = false;
    }

    // Check dimension matches weight file
    int weightStateDim = net.stateDim();
    if ((int)features.size() != weightStateDim)
    {
        printf("\n  FAIL: features.size()=%zu != weight stateDim=%d\n",
               features.size(), weightStateDim);
        pass = false;
    }
    else
    {
        printf("  features.size() matches weight stateDim (%d)\n", weightStateDim);
    }

    printf("\nRESULT: %s\n", pass ? "PASS" : "FAIL");
    return pass;
}

// ============================================================
// Test 2: Verify card type mapping is correct
// ============================================================
static bool testCardTypeMapping()
{
    printf("\n========================================\n");
    printf("TEST 2: Card type mapping verification\n");
    printf("========================================\n");

    NeuralNet & net = NeuralNet::Instance();
    if (!net.isLoaded())
    {
        printf("SKIP: Neural net not loaded\n");
        return true;
    }

    const auto & allTypes = CardTypes::GetAllCardTypes();
    int mapped = 0, unmapped = 0;

    printf("\nAll card types and their unit index mappings:\n");
    for (const auto & type : allTypes)
    {
        int unitIdx = net.getUnitIndex(type.getID());
        if (unitIdx >= 0)
        {
            mapped++;
        }
        else
        {
            printf("  UNMAPPED: id=%d name='%s' uiName='%s'\n",
                   type.getID(), type.getName().c_str(), type.getUIName().c_str());
            unmapped++;
        }
    }
    printf("\n  Mapped: %d / %zu (unmapped: %d)\n", mapped, allTypes.size(), unmapped);

    // Check specific important types
    const char * importantTypes[] = {"Drone", "Engineer", "Wall", "Tarsier", "Rhino", "Blastforge"};
    printf("\nImportant type checks:\n");
    for (const char * name : importantTypes)
    {
        if (CardTypes::CardTypeExists(name))
        {
            CardType type = CardTypes::GetCardType(name);
            int unitIdx = net.getUnitIndex(type.getID());
            printf("  '%s' (id=%d, internal='%s') -> unitIdx=%d\n",
                   type.getUIName().c_str(), type.getID(),
                   type.getName().c_str(), unitIdx);
        }
        else
        {
            printf("  '%s' -> NOT FOUND in engine\n", name);
        }
    }

    printf("\nRESULT: %s\n", (mapped > 0) ? "PASS" : "FAIL");
    return mapped > 0;
}

// ============================================================
// Test 3: Verify features change with different states
// ============================================================
static bool testFeaturesDiffer()
{
    printf("\n========================================\n");
    printf("TEST 3: Features differ between states\n");
    printf("========================================\n");

    NeuralNet & net = NeuralNet::Instance();
    if (!net.isLoaded())
    {
        printf("SKIP: Neural net not loaded\n");
        return true;
    }

    // State A: 6 Drones for P1
    const char * jsonA = R"({
        "whiteMana": "6",
        "blackMana": "0",
        "phase": "action",
        "table": [
            {"cardName":"Drone", "color":0, "amount":6},
            {"cardName":"Engineer", "color":0, "amount":2}
        ],
        "cards":["Drone","Engineer","Wall","Tarsier"]
    })";

    // State B: 10 Drones for P1, 1 Wall
    const char * jsonB = R"({
        "whiteMana": "10",
        "blackMana": "0",
        "phase": "action",
        "table": [
            {"cardName":"Drone", "color":0, "amount":10},
            {"cardName":"Engineer", "color":0, "amount":2},
            {"cardName":"Wall", "color":0, "amount":1}
        ],
        "cards":["Drone","Engineer","Wall","Tarsier"]
    })";

    rapidjson::Document docA, docB;
    docA.Parse(jsonA);
    docB.Parse(jsonB);

    GameState stateA(docA);
    GameState stateB(docB);

    std::vector<float> featA, featB;
    net.extractFeatures(stateA, featA);
    net.extractFeatures(stateB, featB);

    if (featA.size() != featB.size())
    {
        printf("  FAIL: feature sizes differ (%zu vs %zu)\n", featA.size(), featB.size());
        return false;
    }

    int diffCount = 0;
    for (size_t i = 0; i < featA.size(); ++i)
    {
        if (featA[i] != featB[i])
        {
            diffCount++;
            if (diffCount <= 10)
            {
                printf("  diff[%zu]: A=%.3f  B=%.3f\n", i, featA[i], featB[i]);
            }
        }
    }
    printf("  Total differing features: %d / %zu\n", diffCount, featA.size());

    bool pass = (diffCount > 0);
    printf("\nRESULT: %s\n", pass ? "PASS (features differ)" : "FAIL (features identical)");
    return pass;
}

// ============================================================
// Diagnostic: Dump the full _cardTypeToUnitIndex mapping
// ============================================================
static void dumpMappingDiagnostic()
{
    printf("\n========================================\n");
    printf("DIAGNOSTIC: _unitNameToIndex entries in weight file\n");
    printf("========================================\n");

    NeuralNet & net = NeuralNet::Instance();
    if (!net.isLoaded())
    {
        printf("SKIP: Neural net not loaded\n");
        return;
    }

    // Check each engine card type
    const auto & allTypes = CardTypes::GetAllCardTypes();
    printf("\nEngine has %zu card types total\n", allTypes.size());

    // For each type, show whether it maps, and to what index
    for (const auto & type : allTypes)
    {
        int unitIdx = net.getUnitIndex(type.getID());
        if (unitIdx >= 0)
        {
            // Annotate: which feature range does this occupy?
            int base = unitIdx * 11;
            printf("  typeID=%3d -> unitIdx=%3d  features[%4d..%4d]  name='%s' ui='%s'\n",
                   type.getID(), unitIdx, base, base + 10,
                   type.getName().c_str(), type.getUIName().c_str());
        }
    }
}

// ============================================================
// Main
// ============================================================
int main(int argc, char * argv[])
{
    printf("=== NeuralNet Feature Extraction Test ===\n\n");

    srand(42);

    // Determine config directory
    // If run from bin/, path is asset/config/
    // If run from project root, path is bin/asset/config/
    std::string configDir = "asset/config/";
    {
        std::ifstream check(configDir + "cardLibrary.jso");
        if (!check.good())
        {
            configDir = "bin/asset/config/";
            std::ifstream check2(configDir + "cardLibrary.jso");
            if (!check2.good())
            {
                printf("ERROR: Cannot find cardLibrary.jso in asset/config/ or bin/asset/config/\n");
                printf("       Run this from the bin/ directory or the project root.\n");
                return 1;
            }
        }
    }
    printf("Config directory: %s\n", configDir.c_str());

    // Step 1: Initialize card library
    printf("\n[1/3] Initializing card library...\n");
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");
    printf("  Card types loaded: %zu\n", CardTypes::GetAllCardTypes().size());

    // Step 2: Load neural net weights
    printf("\n[2/3] Loading neural network weights...\n");
    bool weightsLoaded = NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin");
    if (weightsLoaded)
    {
        printf("  Weights loaded successfully.\n");
        NeuralNet::Instance().buildCardTypeMapping();
    }
    else
    {
        printf("  WARNING: Failed to load weights. Some tests will be skipped.\n");
    }

    // Step 3: Schema validation
    printf("\n[3/3] Checking schema.json...\n");
    {
        std::string schemaPath = "training/schema.json";
        std::ifstream schemaFile(schemaPath);
        if (!schemaFile.good())
        {
            schemaPath = "../training/schema.json";
            schemaFile.open(schemaPath);
        }
        if (schemaFile.good())
        {
            printf("  schema.json found at: %s\n", schemaPath.c_str());

            // Read and parse schema
            std::string schemaStr((std::istreambuf_iterator<char>(schemaFile)),
                                   std::istreambuf_iterator<char>());
            rapidjson::Document schemaDoc;
            schemaDoc.Parse(schemaStr.c_str());
            if (!schemaDoc.HasParseError())
            {
                int schemaStateDim = schemaDoc.HasMember("state_dim") ? schemaDoc["state_dim"].GetInt() : -1;
                int schemaNumUnits = schemaDoc.HasMember("num_units") ? schemaDoc["num_units"].GetInt() : -1;
                int schemaGlobal   = schemaDoc.HasMember("num_global_features") ? schemaDoc["num_global_features"].GetInt() : -1;
                int schemaVersion  = schemaDoc.HasMember("feature_version") ? schemaDoc["feature_version"].GetInt() : -1;

                printf("  schema: feature_version=%d, state_dim=%d, num_units=%d, num_global=%d\n",
                       schemaVersion, schemaStateDim, schemaNumUnits, schemaGlobal);

                if (weightsLoaded)
                {
                    int weightStateDim = net.stateDim();
                    int weightNumUnits = net.numUnits();
                    if (weightStateDim != schemaStateDim)
                        printf("  WARNING: state_dim mismatch: weights=%d, schema=%d (retrain needed)\n",
                               weightStateDim, schemaStateDim);
                    else
                        printf("  OK: state_dim matches (%d)\n", weightStateDim);

                    if (weightNumUnits != schemaNumUnits)
                        printf("  WARNING: num_units mismatch: weights=%d, schema=%d\n",
                               weightNumUnits, schemaNumUnits);
                    else
                        printf("  OK: num_units matches (%d)\n", weightNumUnits);
                }
            }
            else
            {
                printf("  WARNING: Failed to parse schema.json\n");
            }
        }
        else
        {
            printf("  schema.json not found. Skipping validation.\n");
        }
    }

    // Run tests
    int passed = 0, failed = 0, skipped = 0;

    printf("\n\n");

    if (testKnownState()) passed++; else failed++;
    if (testCardTypeMapping()) passed++; else failed++;
    if (testFeaturesDiffer()) passed++; else failed++;

    // Diagnostic dump (always runs if weights loaded)
    if (weightsLoaded)
    {
        dumpMappingDiagnostic();
    }

    printf("\n\n========================================\n");
    printf("SUMMARY: %d passed, %d failed\n", passed, failed);
    printf("========================================\n");

    return (failed > 0) ? 1 : 0;
}
