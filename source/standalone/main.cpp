#include "Prismata.h"
#include "PrismataAI.h"
#include "NeuralNet.h"
#include "Random.h"
#include "rapidjson/document.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <stdio.h>

#ifdef WIN32
    #include <Windows.h>
    #include <io.h>
    #define DUP(fd) _dup(fd)
    #define DUP2(fd1, fd2) _dup2(fd1, fd2)
    #define FILENO(fp) _fileno(fp)
    #define CLOSE(fd) _close(fd)
#else
    #include <unistd.h>
    #define DUP(fd) dup(fd)
    #define DUP2(fd1, fd2) dup2(fd1, fd2)
    #define FILENO(fp) fileno(fp)
    #define CLOSE(fd) close(fd)
#endif

using namespace Prismata;

void printVersionInfo()
{
    std::stringstream ss;
    ss << "C++ AI compiled on: " << __DATE__ << " at " << __TIME__ << std::endl;
 
    printf("%s", ss.str().c_str());
}

int main(int argc, char *argv[])
{
#ifdef WIN32
    // disables pop up box on crash
    DWORD dwMode = SetErrorMode(SEM_NOGPFAULTERRORBOX);
    SetErrorMode(dwMode | SEM_NOGPFAULTERRORBOX);
#endif

    // --- Parity oracle (offline harness): dump DeepSets features + value for a fixed state ---
    // Usage: Prismata_Standalone --dump-features <stateJson> <outJson> [weightsBin]
    // Run from bin/ so the relative asset paths resolve. Not part of the AI move protocol.
    if (argc >= 4 && std::string(argv[1]) == "--dump-features")
    {
        const std::string statePath   = argv[2];
        const std::string outPath     = argv[3];
        const std::string weightsPath = (argc >= 5) ? argv[4] : "asset/config/neural_weights_mbonly.bin";

        std::ifstream sin(statePath);
        if (!sin.is_open())
        {
            fprintf(stderr, "dump-features: cannot open state file %s\n", statePath.c_str());
            return 1;
        }
        std::string stateStr((std::istreambuf_iterator<char>(sin)), std::istreambuf_iterator<char>());
        sin.close();

        // Load the 116-unit training card library (matches the NN unit_index + property_table)
        Prismata::InitFromCardLibrary("asset/config/cardLibrary.jso");

        rapidjson::Document doc;
        if (doc.Parse(stateStr.c_str()).HasParseError())
        {
            fprintf(stderr, "dump-features: JSON parse error in %s\n", statePath.c_str());
            return 1;
        }
        const rapidjson::Value & gs = doc.HasMember("gameState") ? doc["gameState"] : doc;
        const GameState state(gs);

        if (!NeuralNet::Instance().loadWeights(weightsPath))
        {
            fprintf(stderr, "dump-features: failed to load weights %s\n", weightsPath.c_str());
            return 1;
        }
        NeuralNet::Instance().buildCardTypeMapping();
        NeuralNet::Instance().dumpFeaturesJSON(state, outPath);
        return 0;
    }

    Random::Seed((uint64_t)time(NULL));
    
    // get the input line from stdin
    std::string inputLine;
    std::getline(std::cin, inputLine);

    // if the input string is 'version' print to stdout
    if (inputLine == "version")
    {
        printVersionInfo();
        return 0;
    }

    bool debugPrintToFile = false;

    if (debugPrintToFile)
    {
        // test print the line we got to a file for debugging
        std::ofstream fout("stdin_contents.txt", std::ofstream::out);
        fout << inputLine;
        fout.close();
    }

    // Redirect stdout to stderr during init/search so engine-internal printfs
    // (e.g. "Base set has 11 cards" from CardTypes.cpp) don't corrupt the
    // JSON response on stdout. The matchup runner parses our stdout as JSON.
    fflush(stdout);
    int savedStdout = DUP(FILENO(stdout));
    DUP2(FILENO(stderr), FILENO(stdout));

    // initialize, compute the move, and print the resulting move
    std::string moveString = AITools::InitializeAIAndGetAIMove(inputLine);

    // Restore stdout for the JSON response
    fflush(stdout);
    DUP2(savedStdout, FILENO(stdout));
    CLOSE(savedStdout);

    // remove newlines from the resulting string so it counts as one line for stdout
    for (size_t i(0); i < moveString.size(); ++i)
    {
        #ifdef WIN32
        if (moveString[i] == '\n' || moveString[i] == '\r\n')
        #else
        if (moveString[i] == '\n')
        #endif
        {
            moveString[i] = ' ';
        }
    }

    if (debugPrintToFile)
    {
        std::ofstream fout("stdout_move_string.txt", std::ofstream::out);
        fout << moveString;
        fout.close();
    }
    
    std::cout << moveString << "\n";

    return 0;
}
