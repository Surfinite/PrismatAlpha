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
    // Early detection of quiet modes: stdout must be clean (JSON or no output)
    bool isSuggestMode = false;
    bool isReplayMode = false;
    for (int i = 1; i < argc; ++i)
    {
        std::string arg(argv[i]);
        if (arg == "--suggest") { isSuggestMode = true; break; }
        if (arg == "--eval") { isSuggestMode = true; break; }  // --eval also needs quiet stdout
        if (arg == "--replay" || arg == "--replay-dir") { isReplayMode = true; break; }
    }

    bool isQuietMode = isSuggestMode || isReplayMode;

    if (!isQuietMode) printf("Benchmarks!\n");

    // In quiet modes, redirect stdout to stderr during initialization
    // so that library-internal printfs don't contaminate output
    int savedStdout = -1;
    if (isQuietMode)
    {
        fflush(stdout);
        savedStdout = _dup(_fileno(stdout));
        _dup2(_fileno(stderr), _fileno(stdout));
    }

    srand((unsigned int)(time(NULL) ^ (GETPID() << 4)));

    // read all the configuration settings
    std::string configDir = "asset/config/";

    if (!isQuietMode) printf("Initializing card library\n");
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");

    if (!isQuietMode) printf("Loading neural network weights\n");
    if (NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin"))
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    if (!isQuietMode) printf("Parsing AI Parameters\n");
    Prismata::AIParameters::Instance().parseFile(configDir + "config.txt");

    // Restore stdout for JSON output (or normal operation)
    if (isQuietMode && savedStdout >= 0)
    {
        fflush(stdout);
        _dup2(savedStdout, _fileno(stdout));
        _close(savedStdout);
    }

    // Quick neural net sanity test: evaluate parsed game states
    if (!isQuietMode && NeuralNet::Instance().isLoaded())
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
    std::string evalFile;
    std::string replayFile;
    std::string replayDir;
    std::string replayOutputDir = "training/data/expert/";
    int replayMinRating = 0;
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
        if (std::string(argv[i]) == "--eval" && i + 1 < argc)
            evalFile = argv[++i];
        if (std::string(argv[i]) == "--replay" && i + 1 < argc)
            replayFile = argv[++i];
        if (std::string(argv[i]) == "--replay-dir" && i + 1 < argc)
            replayDir = argv[++i];
        if (std::string(argv[i]) == "--output-dir" && i + 1 < argc)
            replayOutputDir = argv[++i];
        if (std::string(argv[i]) == "--min-rating" && i + 1 < argc)
        {
            try { replayMinRating = std::stoi(argv[++i]); }
            catch (...) { /* use default */ }
        }
    }

    if (!suggestFile.empty())
    {
        Benchmarks::DoSuggest(suggestFile, suggestPlayer, suggestThinkTime);
    }
    else if (!evalFile.empty())
    {
        Benchmarks::DoEval(evalFile);
    }
    else if (!replayFile.empty())
    {
        Benchmarks::DoReplay(replayFile, replayOutputDir, replayMinRating);
    }
    else if (!replayDir.empty())
    {
        Benchmarks::DoReplayBatch(replayDir, replayOutputDir, replayMinRating);
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
