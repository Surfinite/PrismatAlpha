#include "Prismata.h"
#include "PrismataAI.h"
#include "Benchmarks.h"
#include "NeuralNet.h"
#include <iostream>
#include <string>
#include <vector>

using namespace Prismata;

int main(int argc, char* argv[])
{
    printf("Benchmarks!\n");

    srand((unsigned int)time(NULL));

    // read all the configuration settings
    std::string configDir = "asset/config/";

    printf("Initializing card library\n");
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");

    printf("Loading neural network weights\n");
    if (NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin"))
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    printf("Parsing AI Parameters\n");
    Prismata::AIParameters::Instance().parseFile(configDir + "config.txt");

    // Quick neural net sanity test: evaluate parsed game states
    if (NeuralNet::Instance().isLoaded())
    {
        printf("\n--- Neural Net Quick Test ---\n");
        const auto & stateNames = AIParameters::Instance().getStateNames();
        for (size_t si = 0; si < stateNames.size() && si < 3; ++si)
        {
            GameState testState = AIParameters::Instance().getState(stateNames[si]);
            auto output = NeuralNet::Instance().evaluate(testState);
            int policyNonzero = 0;
            for (size_t p = 0; p < output.policy.size(); ++p)
                if (std::abs(output.policy[p]) > 0.01f) policyNonzero++;
            printf("  State '%s': value=%.4f  policy_nonzero=%d/%d\n",
                   stateNames[si].c_str(), output.value,
                   policyNonzero, (int)output.policy.size());
        }
        printf("--- End Neural Net Test ---\n\n");
        fflush(stdout);
    }

    // Check for --fixedset / --fixedset-legacy command line args
    bool runFixedSet = false;
    bool runFixedSetLegacy = false;
    for (int i = 1; i < argc; ++i)
    {
        if (std::string(argv[i]) == "--fixedset")
            runFixedSet = true;
        if (std::string(argv[i]) == "--fixedset-legacy")
            runFixedSetLegacy = true;
    }

    if (runFixedSet || runFixedSetLegacy)
    {
        // Exact card set from the screenshot game
        std::vector<std::string> dominionCards = {
            "Thorium Dynamo",
            "Borehole Patroller",
            "Innervi Field",
            "Tesla Coil",
            "Kinetic Driver",
            "Odin",
            "Zemora Voidbringer",
            "Synthesizer"
        };

        std::string playerName = runFixedSetLegacy ? "OriginalHardestAI" : "HardestAI";
        Benchmarks::DoFixedSetTest(dominionCards, playerName, 10, 8);
    }
    else
    {
        printf("Running Benchmarks\n");
        Benchmarks::DoBenchmarks(configDir + "config.txt");
    }

    return 0;
}
