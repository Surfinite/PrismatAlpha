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
#define DUP(fd) _dup(fd)
#define DUP2(fd1, fd2) _dup2(fd1, fd2)
#define FILENO(fp) _fileno(fp)
#define CLOSE(fd) _close(fd)
#else
#include <unistd.h>
#define GETPID() getpid()
#define DUP(fd) dup(fd)
#define DUP2(fd1, fd2) dup2(fd1, fd2)
#define FILENO(fp) fileno(fp)
#define CLOSE(fd) close(fd)
#endif

using namespace Prismata;

int main(int argc, char* argv[])
{
    // Early detection of all CLI args: parsed before init so we know modes and overrides
    bool isSuggestMode = false;
    std::string weightsOverride;
    std::string suggestFile;
    std::string suggestPlayer = "PrismatAI_AB";
    int suggestThinkTime = 3000;
    for (int i = 1; i < argc; ++i)
    {
        std::string arg(argv[i]);
        if (arg == "--suggest" && i + 1 < argc) { isSuggestMode = true; suggestFile = argv[i + 1]; }
        if (arg == "--weights" && i + 1 < argc) { weightsOverride = argv[i + 1]; }
        if (arg == "--player" && i + 1 < argc) { suggestPlayer = argv[i + 1]; }
        if (arg == "--think-time" && i + 1 < argc)
        {
            try { suggestThinkTime = std::stoi(argv[i + 1]); }
            catch (...) { /* use default */ }
        }
    }

    bool isQuietMode = isSuggestMode;

    if (!isQuietMode) printf("Benchmarks!\n");

    // In quiet modes, redirect stdout to stderr during initialization
    // so that library-internal printfs don't contaminate JSON output
    int savedStdout = -1;
    if (isQuietMode)
    {
        fflush(stdout);
        savedStdout = DUP(FILENO(stdout));
        DUP2(FILENO(stderr), FILENO(stdout));
    }

    srand((unsigned int)(time(NULL) ^ (GETPID() << 4)));

    // read all the configuration settings
    std::string configDir = "asset/config/";

    if (!isQuietMode) printf("Initializing card library\n");
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");

    // Load neural net weights -- use --weights override if provided, else default
    std::string weightsPath = weightsOverride.empty()
        ? (configDir + "neural_weights.bin")
        : weightsOverride;
    if (!isQuietMode) printf("Loading neural network weights: %s\n", weightsPath.c_str());
    if (NeuralNet::Instance().loadWeights(weightsPath))
    {
        NeuralNet::Instance().buildCardTypeMapping();
    }

    if (!isQuietMode) printf("Parsing AI Parameters\n");
    Prismata::AIParameters::Instance().parseFile(configDir + "config.txt");

    // If in suggest mode, check if the player's config specifies a WeightsFile
    // and reload weights if needed (unless --weights was explicitly provided)
    if (isSuggestMode && weightsOverride.empty())
    {
        std::string playerWeights = AIParameters::Instance().getPlayerWeightsFile(suggestPlayer);
        if (!playerWeights.empty())
        {
            std::string playerWeightsPath = configDir + playerWeights;
            fprintf(stderr, "Loading player-specific weights: %s\n", playerWeightsPath.c_str());
            if (NeuralNet::Instance().loadWeights(playerWeightsPath))
            {
                NeuralNet::Instance().buildCardTypeMapping();
            }
        }
    }

    // Restore stdout for JSON output (or normal operation)
    if (isQuietMode && savedStdout >= 0)
    {
        fflush(stdout);
        DUP2(savedStdout, FILENO(stdout));
        CLOSE(savedStdout);
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

    if (!suggestFile.empty())
    {
        Benchmarks::DoSuggest(suggestFile, suggestPlayer, suggestThinkTime);
    }
    else
    {
        printf("Running Benchmarks\n");
        Benchmarks::DoBenchmarks(configDir + "config.txt");
    }

    return 0;
}
