#include "PrismataAI.h"
#include "Benchmarks.h"
#include "PlayerBenchmark.h"
#include "Tournament.h"
#include "NeuralNet.h"
#include "Player_StackAlphaBeta.h"
#include "Player_UCT.h"
#include <thread>
#include <iomanip>
#include <fstream>
#include <sstream>
#ifdef _WIN32
#include <io.h>
#endif

using namespace Prismata;

void Benchmarks::DoBenchmarks(const std::string & filename)
{
    rapidjson::Document document;
    bool parsingFailed = document.Parse(FileUtils::ReadFile(filename).c_str()).HasParseError();

    PRISMATA_ASSERT(!parsingFailed, "Couldn't parse benchmarks file");

    PRISMATA_ASSERT(document.HasMember("Benchmarks"), "JSON has no Benchmarks member");
    PRISMATA_ASSERT(document["Benchmarks"].IsArray(), "JSON Benchmarks member is not an array");

    std::vector<std::thread> threads;

    const rapidjson::Value & benchmarks = document["Benchmarks"];
    for (size_t b(0); b < benchmarks.Size(); ++b)
    {
        bool run = benchmarks[b].HasMember("run") && benchmarks[b]["run"].IsBool() && benchmarks[b]["run"].GetBool();
       
        PRISMATA_ASSERT(benchmarks[b].HasMember("name") && benchmarks[b]["name"].IsString(), "Benchmark must have name string member");
        const std::string & name = benchmarks[b]["name"].GetString();
        
        // must have a true 'run' bool to run the benchmark
        if (!run)
        {
            continue;
        }

        PRISMATA_ASSERT(benchmarks[b].HasMember("type") && benchmarks[b]["type"].IsString(), "Benchmark must have type string member");

        const std::string & benchmarkType = benchmarks[b]["type"].GetString();

        if (benchmarkType == "PlayerBenchmark")
        {
            PlayerBenchmark bm(benchmarks[b]);
            threads.emplace_back(DoPlayerBenchmark, bm);
        }
        else if (benchmarkType == "ChillIterator")
        {
            DoChillIteratorBenchmarkJSON(benchmarks[b]);
        }
        else if (benchmarkType == "Tournament")
        {
            DoTournamentBenchmark(benchmarks[b]);
        }
        else
        {
            PRISMATA_ASSERT(false, "Unknown Benchmark type: %s", benchmarkType.c_str());
        }
    }

    for (auto & t : threads)
    {
        t.join();    
    }
}

void Benchmarks::DoTournamentBenchmark(const rapidjson::Value & value)
{
    Tournament tournament(value);
    tournament.run();
}

void Benchmarks::DoPlayerBenchmark(const PlayerBenchmark & benchmark)
{
    PlayerBenchmark b(benchmark);
    b.run();
}

void Benchmarks::DoChillIteratorBenchmarkJSON(const rapidjson::Value & value)
{
    PRISMATA_ASSERT(value.HasMember("TimeLimitMS") && value["TimeLimitMS"].IsInt(), "ChillIteratorBenchmark must have TimeLimitMS int");
    PRISMATA_ASSERT(value.HasMember("HistogramMinIndex") && value["HistogramMinIndex"].IsInt(), "ChillIteratorBenchmark must have HistogramMinIndex int");
    PRISMATA_ASSERT(value.HasMember("HistogramMaxIndex") && value["HistogramMaxIndex"].IsInt(), "ChillIteratorBenchmark must have HistogramMaxIndex int");
    PRISMATA_ASSERT(value.HasMember("HistogramMaxValue") && value["HistogramMaxValue"].IsInt(), "ChillIteratorBenchmark must have HistogramMaxValue int");

    DoChillIteratorBenchmark(value["TimeLimitMS"].GetInt(), value["HistogramMinIndex"].GetInt(), value["HistogramMaxIndex"].GetInt(), value["HistogramMaxValue"].GetInt());
}

void Benchmarks::DoChillIteratorBenchmark(size_t timeLimitMS, size_t histogramMinIndex, size_t histogramMaxIndex, size_t histogramMaxValue)
{
    std::cout << "\nStarting " << timeLimitMS << "ms ChillIterator Benchmark: \n";

    Timer t;
    t.start();

    double msElapsed = 0;
    size_t totalChillScenarios = 0;
    size_t totalSolveIterations = 0;

    while (msElapsed < timeLimitMS)
    {
        ChillScenario chillScenario;
        chillScenario.setRandomData(histogramMinIndex, histogramMaxIndex, histogramMaxValue);

        ChillIterator chillIterator(chillScenario);
        chillIterator.solve();
        
        totalSolveIterations += chillIterator.getNodesSearched();

        totalChillScenarios++;

        msElapsed = t.getElapsedTimeInMilliSec();
    }

    double ms = msElapsed;
    double gps = (totalChillScenarios / ms) * 1000;

    std::cout << "  Solved " << totalChillScenarios << "  in " << ms << " ms @ " << gps << " games per second" << std::endl;
    std::cout << "  Solves took an average of " << (totalSolveIterations / totalChillScenarios) << " iterations @ " << (totalSolveIterations / ms) * 1000 << " iterations per second\n\n";
}

// ---------------------------------------------------------------------------
// --suggest mode: JSON game state -> neural eval + AI move -> JSON output
// ---------------------------------------------------------------------------

static std::string jsonEscape(const std::string & s)
{
    std::string out;
    out.reserve(s.size() + 16);
    for (char c : s)
    {
        switch (c)
        {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if ((unsigned char)c < 0x20)
                {
                    char buf[8];
                    snprintf(buf, sizeof(buf), "\\u%04x", (unsigned char)c);
                    out += buf;
                }
                else
                {
                    out += c;
                }
                break;
        }
    }
    return out;
}

static std::string jsonStringArray(const std::vector<std::string> & arr)
{
    std::stringstream ss;
    ss << "[";
    for (size_t i = 0; i < arr.size(); ++i)
    {
        if (i > 0) ss << ",";
        ss << "\"" << jsonEscape(arr[i]) << "\"";
    }
    ss << "]";
    return ss.str();
}

static const char * phaseToString(int phase)
{
    switch (phase)
    {
        case Phases::Action:  return "action";
        case Phases::Defense: return "defense";
        case Phases::Breach:  return "breach";
        case Phases::Confirm: return "confirm";
        case Phases::Swoosh:  return "swoosh";
        default:              return "unknown";
    }
}

static void suggestError(const std::string & msg)
{
    printf("{\"ok\":false,\"error\":\"%s\"}\n", jsonEscape(msg).c_str());
    fflush(stdout);
}

static void appendClick(std::stringstream & ss, bool & hasPrev, const char * clickType, int clickId)
{
    if (hasPrev) { ss << ","; }
    ss << "{\"_type\":\"" << clickType << "\",\"_id\":" << clickId << "}";
    hasPrev = true;
}

void Benchmarks::DoSuggest(const std::string & stateFile, const std::string & playerName, int thinkTimeMs)
{
    // 1. Read and parse JSON file (use ifstream to avoid PRISMATA_ASSERT stdout noise)
    std::ifstream ifs(stateFile);
    if (!ifs.is_open())
    {
        suggestError("Cannot read file: " + stateFile);
        return;
    }
    std::string raw((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    ifs.close();
    if (raw.empty())
    {
        suggestError("File is empty: " + stateFile);
        return;
    }

    rapidjson::Document doc;
    if (doc.Parse(raw.c_str()).HasParseError())
    {
        suggestError("JSON parse error in " + stateFile);
        return;
    }

    // 2. Unwrap CurrentInfo wrapper (F6 clipboard export format)
    const rapidjson::Value * root = &doc;
    if (doc.IsObject() && doc.HasMember("CurrentInfo"))
    {
        root = &doc["CurrentInfo"];
    }

    // Redirect stdout to stderr during noisy init (InitFromMergedDeckJSON, GameState ctor)
    // so that only clean JSON goes to stdout
#ifdef _WIN32
    int savedOut = -1;
    {
        fflush(stdout);
        savedOut = _dup(_fileno(stdout));
        _dup2(_fileno(stderr), _fileno(stdout));
    }
#endif

    // 3. Initialize card set from mergedDeck if present (required for F6 JSON)
    if (root->HasMember("mergedDeck") && (*root)["mergedDeck"].IsArray())
    {
        Prismata::InitFromMergedDeckJSON((*root)["mergedDeck"]);
        if (NeuralNet::Instance().isLoaded())
        {
            NeuralNet::Instance().buildCardTypeMapping();
        }
    }

    // 4. Extract and build GameState
    // Support both F6 format (has "gameState" sub-object) and bare format (state at root)
    const rapidjson::Value & stateVal = root->HasMember("gameState")
        ? (*root)["gameState"] : *root;

    Timer parseTimer;
    parseTimer.start();
    GameState state(stateVal);
    double parseMs = parseTimer.getElapsedTimeInMilliSec();

    // Restore stdout for JSON output
#ifdef _WIN32
    if (savedOut >= 0)
    {
        fflush(stdout);
        _dup2(savedOut, _fileno(stdout));
        _close(savedOut);
    }
#endif

    const PlayerID activePlayer = state.getActivePlayer();
    const char * phase = phaseToString(state.getActivePhase());

    // 5. Neural eval
    Timer evalTimer;
    evalTimer.start();
    float neuralValue = 0.0f;
    if (NeuralNet::Instance().isLoaded())
    {
        auto output = NeuralNet::Instance().evaluate(state);
        neuralValue = output.value;
    }
    double evalMs = evalTimer.getElapsedTimeInMilliSec();

    // 6. Get AI move with think time override
    Timer searchTimer;
    searchTimer.start();

    PlayerPtr player;
    try
    {
        player = AIParameters::Instance().getPlayer(activePlayer, playerName);
    }
    catch (std::exception & e)
    {
        suggestError(std::string("Cannot create player '") + playerName + "': " + e.what());
        return;
    }

    // Override think time
    if (thinkTimeMs > 0)
    {
        auto * sabPlayer = dynamic_cast<Player_StackAlphaBeta *>(player.get());
        auto * uctPlayer = dynamic_cast<Player_UCT *>(player.get());
        if (sabPlayer)
        {
            sabPlayer->getParams().setTimeLimit(thinkTimeMs);
        }
        else if (uctPlayer)
        {
            uctPlayer->getParams().setTimeLimit(thinkTimeMs);
        }
    }

    Move move;
    try
    {
        player->getMove(state, move);
    }
    catch (std::exception & e)
    {
        suggestError(std::string("AI search failed: ") + e.what());
        return;
    }
    double searchMs = searchTimer.getElapsedTimeInMilliSec();

    // 7. Categorize actions by type
    std::vector<std::string> buys, abilities, defense, breach;
    for (size_t i = 0; i < move.size(); ++i)
    {
        const Action & action = move.getAction(i);
        switch (action.getType())
        {
            case ActionTypes::BUY:
                buys.push_back(CardType(action.getID()).getUIName());
                break;
            case ActionTypes::USE_ABILITY:
                abilities.push_back(state.getCardByID(action.getID()).getType().getUIName());
                break;
            case ActionTypes::ASSIGN_BLOCKER:
                defense.push_back(state.getCardByID(action.getID()).getType().getUIName());
                break;
            case ActionTypes::ASSIGN_BREACH:
                breach.push_back(state.getCardByID(action.getID()).getType().getUIName());
                break;
            case ActionTypes::SNIPE:
                abilities.push_back(state.getCardByID(action.getID()).getType().getUIName()
                    + " snipe " + state.getCardByID(action.getTargetID()).getType().getUIName());
                break;
            case ActionTypes::CHILL:
                abilities.push_back(state.getCardByID(action.getID()).getType().getUIName()
                    + " chill " + state.getCardByID(action.getTargetID()).getType().getUIName());
                break;
            default:
                break; // END_PHASE, WIPEOUT, UNDO_*, SELL -- skip
        }
    }

    // 8. Build click-ready actions for protocol injection
    //    Mirrors Move::toClientString() logic for automatic END_PHASE insertion
    std::stringstream clicksOut;
    clicksOut << "[";
    bool hasPrevClick = false;
    for (size_t i = 0; i < move.size(); ++i)
    {
        const Action & action = move.getAction(i);

        // Insert END_PHASE between blockers and non-blockers
        if (i > 0 && action.getType() != ActionTypes::ASSIGN_BLOCKER
            && move.getAction(i - 1).getType() == ActionTypes::ASSIGN_BLOCKER)
        {
            appendClick(clicksOut, hasPrevClick, "space clicked", -1);
        }

        // Insert END_PHASE before first breach action
        if (i > 0 && action.getType() == ActionTypes::ASSIGN_BREACH
            && move.getAction(i - 1).getType() != ActionTypes::ASSIGN_BREACH)
        {
            appendClick(clicksOut, hasPrevClick, "space clicked", -1);
        }

        switch (action.getType())
        {
            case ActionTypes::BUY:
            {
                // CardType global ID -> mergedDeck index (offset by 2 empty entries)
                int deckIdx = (int)action.getID() - 2;
                appendClick(clicksOut, hasPrevClick, "card clicked", deckIdx);
                break;
            }
            case ActionTypes::USE_ABILITY:
            {
                int instId = state.getCardByID(action.getID()).getClientInstId();
                appendClick(clicksOut, hasPrevClick, "inst clicked", instId);
                break;
            }
            case ActionTypes::ASSIGN_BLOCKER:
            {
                int instId = state.getCardByID(action.getID()).getClientInstId();
                appendClick(clicksOut, hasPrevClick, "inst clicked", instId);
                appendClick(clicksOut, hasPrevClick, "end swipe processed", instId);
                break;
            }
            case ActionTypes::ASSIGN_BREACH:
            {
                int instId = state.getCardByID(action.getID()).getClientInstId();
                appendClick(clicksOut, hasPrevClick, "inst clicked", instId);
                break;
            }
            case ActionTypes::SNIPE:
            case ActionTypes::CHILL:
            {
                // Two-step targeting: click source, then click target
                int srcId = state.getCardByID(action.getID()).getClientInstId();
                int tgtId = state.getCardByID(action.getTargetID()).getClientInstId();
                appendClick(clicksOut, hasPrevClick, "inst clicked", srcId);
                appendClick(clicksOut, hasPrevClick, "inst clicked", tgtId);
                break;
            }
            case ActionTypes::END_PHASE:
                // Skip -- we insert END_PHASE automatically above
                break;
            default:
                break;
        }
    }
    // Final END_PHASE to commit the turn
    appendClick(clicksOut, hasPrevClick, "space clicked", -1);
    clicksOut << "]";

    // 9. Build JSON output
    double evalPct = (neuralValue + 1.0) / 2.0 * 100.0;
    std::stringstream out;
    out << std::fixed;
    out << "{\"ok\":true";
    out << ",\"eval\":" << std::setprecision(4) << neuralValue;
    out << ",\"eval_pct\":\"" << std::setprecision(0) << evalPct << "%\"";
    out << ",\"active_player\":" << (int)activePlayer;
    out << ",\"phase\":\"" << phase << "\"";
    out << ",\"buy\":" << jsonStringArray(buys);
    out << ",\"abilities\":" << jsonStringArray(abilities);
    out << ",\"defense\":" << jsonStringArray(defense);
    out << ",\"breach\":" << jsonStringArray(breach);
    out << ",\"clicks\":" << clicksOut.str();
    out << ",\"think_ms\":" << (int)searchMs;
    out << ",\"timing_ms\":{\"parse\":" << (int)parseMs
        << ",\"eval\":" << (int)evalMs
        << ",\"search\":" << (int)searchMs << "}";
    out << ",\"full_move\":\"" << jsonEscape(move.toString()) << "\"";
    out << "}";

    printf("%s\n", out.str().c_str());
    fflush(stdout);
}
