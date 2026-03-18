#include <iostream>
#include <string>
#include <vector>
#include <filesystem>

#include "replay_validator.h"
#include "Prismata.h"

extern void run_resource_tests();
extern void run_card_library_tests();
extern void run_card_tests();
extern void run_game_state_tests();

namespace fs = std::filesystem;

static void printUsage(const char * progName)
{
    std::cout << "Usage:" << std::endl;
    std::cout << "  " << progName << "                               Run unit tests" << std::endl;
    std::cout << "  " << progName << " --validate-replays smoke      Run smoke validation (~100 replays)" << std::endl;
    std::cout << "  " << progName << " --validate-replays <path>     Validate specific replay file(s)" << std::endl;
    std::cout << "  " << progName << " --validate-replays <dir>      Validate all .json replays in directory" << std::endl;
}

/// Collect replay file paths from a path argument.
/// If it's a file, return just that file. If it's a directory, find all .json files in it.
static std::vector<std::string> collectReplayFiles(const std::string & path)
{
    std::vector<std::string> files;

    try
    {
        if (fs::is_regular_file(path))
        {
            files.push_back(path);
        }
        else if (fs::is_directory(path))
        {
            for (const auto & entry : fs::recursive_directory_iterator(path))
            {
                if (entry.is_regular_file())
                {
                    std::string p = entry.path().string();
                    if (p.size() > 5 && p.substr(p.size() - 5) == ".json")
                    {
                        files.push_back(p);
                    }
                }
            }
            std::cout << "Found " << files.size() << " replay files in " << path << std::endl;
        }
        else
        {
            std::cerr << "Path does not exist: " << path << std::endl;
        }
    }
    catch (const std::exception & e)
    {
        std::cerr << "Error scanning path: " << e.what() << std::endl;
    }

    return files;
}

int main(int argc, char * argv[])
{
    // No args: run unit tests
    if (argc < 2)
    {
        run_resource_tests();
        run_card_library_tests();
        run_card_tests();
        run_game_state_tests();
        std::cout << "\nAll tests PASSED" << std::endl;
        return 0;
    }

    std::string arg1 = argv[1];

    if (arg1 == "--help" || arg1 == "-h")
    {
        printUsage(argv[0]);
        return 0;
    }

    if (arg1 == "--validate-replays")
    {
        if (argc < 3)
        {
            std::cerr << "Error: --validate-replays requires a target (smoke, file path, or directory)" << std::endl;
            printUsage(argv[0]);
            return 2;
        }

        // Card library must be loaded before validation
        std::cout << "Loading card library..." << std::endl;
        Prismata::InitFromCardLibrary("bin/asset/config/cardLibrary.jso");

        std::string target = argv[2];
        std::vector<std::string> replayFiles;

        if (target == "smoke")
        {
            replayFiles = Prismata::findSmokeTestReplays(100);
        }
        else
        {
            replayFiles = collectReplayFiles(target);
        }

        if (replayFiles.empty())
        {
            std::cerr << "No replay files found for target: " << target << std::endl;
            return 1;
        }

        std::cout << "Validating " << replayFiles.size() << " replay(s)..." << std::endl;
        Prismata::ReplayValidationSummary summary = Prismata::validateReplays(replayFiles);
        summary.print();

        // Return 0 if all loaded (failures are expected), 1 if load errors
        return (summary.errors > 0) ? 1 : 0;
    }

    std::cerr << "Unknown argument: " << arg1 << std::endl;
    printUsage(argv[0]);
    return 2;
}
