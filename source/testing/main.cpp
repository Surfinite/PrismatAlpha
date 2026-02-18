#include "Prismata.h"
#include "PrismataAI.h"
#include "Benchmarks.h"
#include "NeuralNet.h"
#include <iostream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <process.h>
#include <io.h>
#define GETPID() _getpid()
#else
#include <unistd.h>
#define GETPID() getpid()
#endif

using namespace Prismata;

int main(int argc, char* argv[])
{
    // Early detection of --suggest mode: stdout must be clean JSON only
    bool isSuggestMode = false;
    for (int i = 1; i < argc; ++i)
    {
        if (std::string(argv[i]) == "--suggest") { isSuggestMode = true; break; }
    }

    if (!isSuggestMode) printf("Benchmarks!\n");

    // In --suggest mode, redirect stdout to stderr during initialization
    // so that library-internal printfs don't contaminate the JSON output
    int savedStdout = -1;
    if (isSuggestMode)
    {
        fflush(stdout);
        savedStdout = _dup(_fileno(stdout));
        _dup2(_fileno(stderr), _fileno(stdout));
    }

    srand((unsigned int)(time(NULL) ^ (GETPID() << 4)));

    // read all the configuration settings
    std::string configDir = "asset/config/";

    if (!isSuggestMode) printf("Initializing card library\n");
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");

    if (!isSuggestMode) printf("Loading neural network weights\n");
    if (NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin"))
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    if (!isSuggestMode) printf("Parsing AI Parameters\n");
    Prismata::AIParameters::Instance().parseFile(configDir + "config.txt");

    // Restore stdout for JSON output (or normal operation)
    if (isSuggestMode && savedStdout >= 0)
    {
        fflush(stdout);
        _dup2(savedStdout, _fileno(stdout));
        _close(savedStdout);
    }

    // Quick neural net sanity test: evaluate parsed game states
    if (!isSuggestMode && NeuralNet::Instance().isLoaded())
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

    // Check for command line args
    bool runFixedSet = false;
    bool runFixedSetLegacy = false;
    std::string validateReplayFile;
    std::string validateOutputFile = "validation_output.jsonl";
    std::string suggestFile;
    std::string suggestPlayer = "PrismatAlpha_AB";
    int suggestThinkTime = 3000;
    for (int i = 1; i < argc; ++i)
    {
        if (std::string(argv[i]) == "--fixedset")
            runFixedSet = true;
        if (std::string(argv[i]) == "--fixedset-legacy")
            runFixedSetLegacy = true;
        if (std::string(argv[i]) == "--validate-replay" && i + 1 < argc)
            validateReplayFile = argv[++i];
        if (std::string(argv[i]) == "--validate-output" && i + 1 < argc)
            validateOutputFile = argv[++i];
        if (std::string(argv[i]) == "--suggest" && i + 1 < argc)
            suggestFile = argv[++i];
        if (std::string(argv[i]) == "--player" && i + 1 < argc)
            suggestPlayer = argv[++i];
        if (std::string(argv[i]) == "--think-time" && i + 1 < argc)
        {
            try { suggestThinkTime = std::stoi(argv[++i]); }
            catch (...) { /* use default */ }
        }
    }

    if (!suggestFile.empty())
    {
        Benchmarks::DoSuggest(suggestFile, suggestPlayer, suggestThinkTime);
    }
    else if (!validateReplayFile.empty())
    {
        Benchmarks::DoReplayValidation(validateReplayFile, validateOutputFile);
    }
    else if (runFixedSet || runFixedSetLegacy)
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
