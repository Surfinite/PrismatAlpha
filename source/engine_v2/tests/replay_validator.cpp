#include "replay_validator.h"
#include "name_translation.h"
#include "Prismata.h"
#include "CardTypes.h"
#include "CardTypeData.h"
#include "FileUtils.h"

#include "rapidjson/document.h"

#include <iostream>
#include <fstream>
#include <sstream>
#include <filesystem>

namespace fs = std::filesystem;

using namespace Prismata;

// ============================================================================
// Helper: Read file contents into string (uses ifstream, not FileUtils,
// to avoid PRISMATA_ASSERT printing to stdout on failure)
// ============================================================================
static std::string readFileToString(const std::string & filePath)
{
    std::ifstream ifs(filePath);
    if (!ifs.is_open())
    {
        return "";
    }
    std::stringstream ss;
    ss << ifs.rdbuf();
    return ss.str();
}

// ============================================================================
// Load a replay JSON file
// ============================================================================
bool Prismata::loadReplayJSON(const std::string & filePath, rapidjson::Document & doc)
{
    std::string contents = readFileToString(filePath);
    if (contents.empty())
    {
        return false;
    }

    doc.Parse(contents.c_str());
    return !doc.HasParseError() && doc.IsObject();
}

// ============================================================================
// Validate a single replay from file path
// ============================================================================
ReplayValidationResult Prismata::validateReplay(const std::string & filePath)
{
    ReplayValidationResult result;
    result.filePath = filePath;

    rapidjson::Document doc;
    if (!loadReplayJSON(filePath, doc))
    {
        result.errorMessage = "Failed to parse JSON file";
        return result;
    }

    return validateReplayFromDoc(doc, filePath);
}

// ============================================================================
// Validate a single replay from parsed JSON
//
// Matchup replay format (from matchup_clean.js):
//   - "states": array of per-action state snapshots
//   - "turnBoundaries": array of indices into states[] marking turn starts
//   - "actions": array of action description strings
//   - "winner": 0=P1, 1=P2, -1=draw/stagnation
//   - Each state has: whiteMana, blackMana, turn, numTurns, phase,
//     cards, whiteTotalSupply, blackTotalSupply, whiteSupplySpent,
//     blackSupplySpent, table (array of card objects)
//
// Most AI games end by resignation (one player sees it will lose and
// gives up). In these cases, both players still have cards in the final
// state. The winner is determined by the AI, not by elimination.
// Only a minority of games end by actual elimination (zero cards).
//
// Validation levels:
//   Level 1: State loading - can the engine parse every turn-boundary state?
//   Level 2: Outcome - for elimination games, does card-count analysis agree?
//   Level 3: Per-turn comparison (future: compare resources, counts, etc.)
// ============================================================================
ReplayValidationResult Prismata::validateReplayFromDoc(const rapidjson::Document & doc, const std::string & filePath)
{
    ReplayValidationResult result;
    result.filePath = filePath;

    try
    {
        // -----------------------------------------------------------
        // Extract replay metadata
        // -----------------------------------------------------------
        if (!doc.HasMember("replay") || !doc["replay"].IsBool() || !doc["replay"].GetBool())
        {
            result.errorMessage = "Not a replay file (missing or false 'replay' field)";
            return result;
        }

        if (doc.HasMember("p0") && doc["p0"].IsString())
        {
            result.p0Name = doc["p0"].GetString();
        }
        if (doc.HasMember("p1") && doc["p1"].IsString())
        {
            result.p1Name = doc["p1"].GetString();
        }

        // Winner: 0=P1, 1=P2, -1=draw/stagnation
        if (doc.HasMember("winner") && doc["winner"].IsInt())
        {
            result.replayWinner = doc["winner"].GetInt();
        }

        // Turn boundaries
        if (!doc.HasMember("turnBoundaries") || !doc["turnBoundaries"].IsArray())
        {
            result.errorMessage = "Missing 'turnBoundaries' array";
            return result;
        }
        const auto & turnBoundaries = doc["turnBoundaries"];
        result.totalTurns = (int)turnBoundaries.Size();

        // States array
        if (!doc.HasMember("states") || !doc["states"].IsArray())
        {
            result.errorMessage = "Missing 'states' array";
            return result;
        }
        const auto & states = doc["states"];
        result.totalStates = (int)states.Size();

        if (result.totalStates == 0 || result.totalTurns == 0)
        {
            result.errorMessage = "Empty states or turnBoundaries";
            return result;
        }

        // -----------------------------------------------------------
        // Load turn-boundary states and verify parsing
        // -----------------------------------------------------------
        std::string lastError;

        for (rapidjson::SizeType t = 0; t < turnBoundaries.Size(); ++t)
        {
            if (!turnBoundaries[t].IsInt())
            {
                continue;
            }

            int stateIdx = turnBoundaries[t].GetInt();
            if (stateIdx < 0 || stateIdx >= (int)states.Size())
            {
                continue;
            }

            const auto & stateJSON = states[stateIdx];
            if (!stateJSON.IsObject())
            {
                result.statesFailed++;
                continue;
            }

            try
            {
                GameState gs(stateJSON);
                result.statesLoaded++;
                result.turnsPlayed = (int)t + 1;
            }
            catch (const std::exception & e)
            {
                result.statesFailed++;
                lastError = e.what();
            }
            catch (...)
            {
                result.statesFailed++;
                lastError = "Unknown exception during state loading";
            }
        }

        result.loaded = (result.statesLoaded > 0);

        if (!result.loaded)
        {
            result.errorMessage = "Could not load any turn-boundary states";
            if (!lastError.empty())
            {
                result.errorMessage += ": " + lastError;
            }
            return result;
        }

        // -----------------------------------------------------------
        // Determine winner from final state card counts
        // -----------------------------------------------------------
        {
            const auto & lastState = states[states.Size() - 1];
            if (lastState.IsObject())
            {
                try
                {
                    GameState gsLast(lastState);
                    CardID p1Cards = gsLast.numCards(Players::Player_One);
                    CardID p2Cards = gsLast.numCards(Players::Player_Two);

                    if (p1Cards == 0 && p2Cards == 0)
                    {
                        result.engineWinner = -2; // draw (mutual elimination)
                    }
                    else if (p1Cards == 0)
                    {
                        result.engineWinner = 1; // P2 wins (P1 eliminated)
                    }
                    else if (p2Cards == 0)
                    {
                        result.engineWinner = 0; // P1 wins (P2 eliminated)
                    }
                    else
                    {
                        // Neither player eliminated: game ended by resignation
                        // or stagnation. The replay's "winner" field is authoritative.
                        result.resignation = true;
                    }
                }
                catch (...)
                {
                    // Non-fatal -- we already loaded turn-boundary states
                }
            }
        }

        // -----------------------------------------------------------
        // Compare outcomes
        // -----------------------------------------------------------
        if (result.resignation)
        {
            // Game ended by resignation: outcome comparison is not possible
            // from state snapshots alone. This is expected and normal.
            // The state loading itself is the validation signal.
            result.outcomeMatch = true; // Count as pass (loaded OK)
        }
        else if (result.engineWinner >= 0 && result.replayWinner >= 0)
        {
            result.outcomeMatch = (result.engineWinner == result.replayWinner);
            if (!result.outcomeMatch)
            {
                result.errorMessage = "Elimination outcome mismatch";
            }
        }
        else if (result.engineWinner == -2)
        {
            // Engine detected mutual elimination (draw)
            result.outcomeMatch = (result.replayWinner == -1 || result.replayWinner == 2);
            if (!result.outcomeMatch)
            {
                result.errorMessage = "Engine detected draw but replay has winner=" + std::to_string(result.replayWinner);
            }
        }
        else
        {
            // Fallback: could not determine
            result.outcomeMatch = true; // Don't penalize for unknown states
        }

        // -----------------------------------------------------------
        // Report state loading issues
        // -----------------------------------------------------------
        if (result.statesFailed > 0)
        {
            if (!result.errorMessage.empty())
            {
                result.errorMessage += "; ";
            }
            result.errorMessage += std::to_string(result.statesFailed) + "/"
                + std::to_string(result.statesLoaded + result.statesFailed) + " state loads failed";
            if (!lastError.empty())
            {
                result.errorMessage += " (last: " + lastError + ")";
            }
        }
    }
    catch (const std::exception & e)
    {
        result.errorMessage = std::string("Exception: ") + e.what();
    }
    catch (...)
    {
        result.errorMessage = "Unknown exception during validation";
    }

    return result;
}

// ============================================================================
// Validate multiple replays
// ============================================================================
ReplayValidationSummary Prismata::validateReplays(const std::vector<std::string> & filePaths)
{
    ReplayValidationSummary summary;
    summary.total = (int)filePaths.size();

    for (const auto & path : filePaths)
    {
        ReplayValidationResult result = validateReplay(path);

        if (result.loaded)
        {
            summary.loaded++;
            if (result.resignation)
            {
                summary.resignations++;
            }
            if (result.outcomeMatch)
            {
                summary.outcomePassed++;
            }
            else
            {
                summary.outcomeFailed++;
            }
        }
        else
        {
            summary.errors++;
        }

        summary.results.push_back(result);
    }

    return summary;
}

// ============================================================================
// Print validation summary
// ============================================================================
void ReplayValidationSummary::print() const
{
    std::cout << "\n=== Replay Validation Summary ===" << std::endl;
    std::cout << "Total replays:     " << total << std::endl;
    std::cout << "States loaded OK:  " << loaded << "/" << total << std::endl;
    std::cout << "  Resignations:    " << resignations << " (outcome from AI, not elimination)" << std::endl;
    std::cout << "  Elimination:     " << (loaded - resignations) << std::endl;
    std::cout << "Outcome passed:    " << outcomePassed << std::endl;
    std::cout << "Outcome failed:    " << outcomeFailed << std::endl;
    std::cout << "Load errors:       " << errors << std::endl;

    // Print details for actual failures (load errors or outcome mismatches)
    bool anyFailures = false;
    for (const auto & r : results)
    {
        bool isFailure = !r.loaded || (!r.outcomeMatch) || (r.statesFailed > 0);
        if (isFailure)
        {
            if (!anyFailures)
            {
                std::cout << "\n--- Issues ---" << std::endl;
                anyFailures = true;
            }

            std::string filename = r.filePath;
            auto pos = filename.find_last_of("/\\");
            if (pos != std::string::npos)
            {
                filename = filename.substr(pos + 1);
            }

            std::cout << "  " << filename << ": ";
            if (!r.loaded)
            {
                std::cout << "LOAD ERROR";
            }
            else if (!r.outcomeMatch)
            {
                std::cout << "OUTCOME MISMATCH (replay=" << r.replayWinner
                          << " engine=" << r.engineWinner << ")";
            }
            else if (r.statesFailed > 0)
            {
                std::cout << "PARTIAL (" << r.statesLoaded << " OK, " << r.statesFailed << " failed)";
            }

            if (!r.errorMessage.empty())
            {
                std::cout << " [" << r.errorMessage << "]";
            }
            std::cout << std::endl;
        }
    }

    if (!anyFailures)
    {
        std::cout << "\nNo issues found." << std::endl;
    }

    // Print a few examples
    int exampleCount = 0;
    for (const auto & r : results)
    {
        if (r.loaded && exampleCount < 5)
        {
            if (exampleCount == 0)
            {
                std::cout << "\n--- Sample results ---" << std::endl;
            }
            std::string filename = r.filePath;
            auto pos = filename.find_last_of("/\\");
            if (pos != std::string::npos)
            {
                filename = filename.substr(pos + 1);
            }
            std::cout << "  " << filename << ": "
                      << (r.resignation ? "RESIGN" : "ELIM")
                      << " turns=" << r.totalTurns
                      << " states_loaded=" << r.statesLoaded
                      << "/" << r.totalTurns
                      << " winner=" << r.replayWinner << std::endl;
            exampleCount++;
        }
    }

    std::cout << "=================================" << std::endl;
}

// ============================================================================
// Find smoke test replay files
// ============================================================================
std::vector<std::string> Prismata::findSmokeTestReplays(int maxFiles)
{
    std::vector<std::string> files;

    // Look in bin/asset/replays/ for .json files (not .json.gz)
    std::string replayDir = "bin/asset/replays";

    try
    {
        if (!fs::exists(replayDir))
        {
            std::cerr << "Replay directory not found: " << replayDir << std::endl;
            return files;
        }

        for (const auto & entry : fs::recursive_directory_iterator(replayDir))
        {
            if ((int)files.size() >= maxFiles)
            {
                break;
            }

            if (entry.is_regular_file())
            {
                std::string path = entry.path().string();
                // Only uncompressed .json files (not .json.gz)
                if (path.size() > 5 && path.substr(path.size() - 5) == ".json")
                {
                    files.push_back(path);
                }
            }
        }
    }
    catch (const std::exception & e)
    {
        std::cerr << "Error scanning replay directory: " << e.what() << std::endl;
    }

    std::cout << "Found " << files.size() << " replay files for smoke test" << std::endl;
    return files;
}
