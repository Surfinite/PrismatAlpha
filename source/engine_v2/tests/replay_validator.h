#pragma once

#include "Common.h"
#include "GameState.h"

#include "rapidjson/document.h"

#include <string>
#include <vector>

namespace Prismata
{

/// Result of validating a single replay
struct ReplayValidationResult
{
    std::string filePath;
    bool        loaded          = false;    // Did the JSON parse and state-load succeed?
    bool        outcomeMatch    = false;    // Does the engine outcome match the replay?
    int         replayWinner    = -1;       // Winner from replay (0=P1, 1=P2, -1=unknown/draw)
    int         engineWinner    = -1;       // Winner from engine (-1=ongoing/unknown, -2=draw)
    int         totalTurns      = 0;        // Number of turn boundaries in replay
    int         turnsPlayed     = 0;        // How many turn-boundary states loaded successfully
    int         totalStates     = 0;        // Total state snapshots in replay
    int         statesLoaded    = 0;        // How many turn-boundary states loaded OK
    int         statesFailed    = 0;        // How many turn-boundary states failed to load
    bool        resignation     = false;    // True if game ended by resignation (no elimination)
    std::string errorMessage;               // Error description if failed
    std::string p0Name;                     // Player 0 name
    std::string p1Name;                     // Player 1 name
};

/// Summary of a batch validation run
struct ReplayValidationSummary
{
    int total           = 0;
    int loaded          = 0;    // States loaded successfully
    int outcomePassed   = 0;    // Outcome matched (elimination games)
    int outcomeFailed   = 0;    // Outcome mismatched
    int resignations    = 0;    // Games ended by resignation (outcome N/A)
    int errors          = 0;    // Could not load at all
    std::vector<ReplayValidationResult> results;

    void print() const;
};

/// Load a replay JSON file (uncompressed .json only for now).
/// Returns true if parsing succeeded, fills `doc` with the parsed document.
bool loadReplayJSON(const std::string & filePath, rapidjson::Document & doc);

/// Validate a single replay file.
/// Loads each turn-boundary state into a GameState, checks card counts in
/// the final state, and compares the outcome with the replay's winner.
ReplayValidationResult validateReplay(const std::string & filePath);

/// Validate a single replay from an already-parsed JSON document.
ReplayValidationResult validateReplayFromDoc(const rapidjson::Document & doc, const std::string & filePath);

/// Run validation on multiple replay files.
ReplayValidationSummary validateReplays(const std::vector<std::string> & filePaths);

/// Find replay files for the smoke test tier.
/// Looks in bin/asset/replays/ for .json files, returns up to maxFiles paths.
std::vector<std::string> findSmokeTestReplays(int maxFiles = 100);

} // namespace Prismata
