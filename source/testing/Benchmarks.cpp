#include "PrismataAI.h"
#include "Benchmarks.h"
#include "PlayerBenchmark.h"
#include "Tournament.h"
#include "TournamentGame.h"
#include "Game.h"
#include "rapidjson/document.h"
#include <thread>
#include <map>
#include <set>
#include <algorithm>
#include <iomanip>
#include <cmath>
#include <fstream>
#include <sstream>

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
        else if (benchmarkType == "RandomSetTest")
        {
            size_t numTrials = benchmarks[b].HasMember("NumTrials") ? benchmarks[b]["NumTrials"].GetInt() : 100000;
            size_t cardsPerSet = benchmarks[b].HasMember("CardsPerSet") ? benchmarks[b]["CardsPerSet"].GetInt() : 8;
            DoRandomSetTest(numTrials, cardsPerSet);
        }
        else if (benchmarkType == "ReplayValidation")
        {
            PRISMATA_ASSERT(benchmarks[b].HasMember("ValidationFile") && benchmarks[b]["ValidationFile"].IsString(),
                "ReplayValidation must have ValidationFile string");
            std::string validationFile = benchmarks[b]["ValidationFile"].GetString();
            std::string outputFile = "validation_output.jsonl";
            if (benchmarks[b].HasMember("OutputFile") && benchmarks[b]["OutputFile"].IsString())
            {
                outputFile = benchmarks[b]["OutputFile"].GetString();
            }
            DoReplayValidation(validationFile, outputFile);
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

void Benchmarks::DoRandomSetTest(size_t numTrials, size_t cardsPerSet)
{
    const auto & dominionTypes = CardTypes::GetDominionCardTypes();
    size_t poolSize = dominionTypes.size();

    std::cout << "\n=== Random Set Uniformity Test ===\n";
    std::cout << "Dominion pool size: " << poolSize << "\n";
    std::cout << "Trials: " << numTrials << ", Cards per set: " << cardsPerSet << "\n\n";

    if (poolSize == 0)
    {
        std::cout << "ERROR: No dominion cards loaded!\n";
        return;
    }

    // Count selections per unit (by internal name)
    std::map<std::string, size_t> counts;
    for (size_t i = 0; i < poolSize; ++i)
    {
        counts[dominionTypes[i].getUIName()] = 0;
    }

    // Run trials
    for (size_t trial = 0; trial < numTrials; ++trial)
    {
        GameState state;
        state.setStartingState(Players::Player_One, (CardID)cardsPerSet);

        // Count non-base-set buyable cards in this state
        for (CardID i = 0; i < state.numCardsBuyable(); ++i)
        {
            const CardBuyable & cb = state.getCardBuyableByIndex(i);
            if (!CardTypes::IsBaseSet(cb.getType()))
            {
                counts[cb.getType().getUIName()]++;
            }
        }
    }

    // Sort by count ascending
    std::vector<std::pair<std::string, size_t>> sorted(counts.begin(), counts.end());
    std::sort(sorted.begin(), sorted.end(), [](const auto & a, const auto & b) { return a.second < b.second; });

    double expected = (double)(numTrials * cardsPerSet) / poolSize;
    size_t neverSelected = 0;
    double maxDevPct = 0;

    std::cout << std::left << std::setw(30) << "Unit"
              << std::right << std::setw(8) << "Count"
              << std::setw(12) << "Expected"
              << std::setw(10) << "Dev%" << "\n";
    std::cout << std::string(60, '-') << "\n";

    for (const auto & entry : sorted)
    {
        double devPct = ((entry.second - expected) / expected) * 100.0;
        double absDevPct = std::abs(devPct);
        if (absDevPct > maxDevPct) maxDevPct = absDevPct;

        std::string flag = "";
        if (entry.second == 0) { flag = " *** NEVER SELECTED ***"; neverSelected++; }
        else if (absDevPct > 5.0) { flag = " *"; }

        std::cout << std::left << std::setw(30) << entry.first
                  << std::right << std::setw(8) << entry.second
                  << std::setw(12) << std::fixed << std::setprecision(1) << expected
                  << std::setw(9) << std::fixed << std::setprecision(1) << devPct << "%"
                  << flag << "\n";
    }

    std::cout << std::string(60, '-') << "\n";
    std::cout << "Expected per unit: " << std::fixed << std::setprecision(1) << expected << "\n";
    std::cout << "Max deviation: " << std::fixed << std::setprecision(1) << maxDevPct << "%\n";
    std::cout << "Units never selected: " << neverSelected << " / " << poolSize << "\n";

    if (neverSelected > 0)
        std::cout << "\nWARNING: Some units were NEVER selected! Pool size mismatch or filtering bug.\n";
    else if (maxDevPct < 5.0)
        std::cout << "\nRESULT: Distribution looks uniform (max deviation < 5%).\n";
    else
        std::cout << "\nWARNING: Significant deviation detected (> 5%). Possible bias.\n";

    std::cout << "=== End Random Set Test ===\n\n";
}

void Benchmarks::DoFixedSetTest(const std::vector<std::string> & dominionCards, const std::string & playerName, size_t numGames, size_t trackTurns)
{
    printf("\n=== Fixed Set Buy Test ===\n");
    printf("Player: %s\n", playerName.c_str());
    printf("Games: %zu, Tracking first %zu turns\n", numGames, trackTurns);
    printf("Dominion cards: ");
    for (const auto & c : dominionCards) printf("%s, ", c.c_str());
    printf("\n\n");

    // Track per-unit buy counts per turn across all games
    // buyCountsByTurn[turn][unitName] = total buys across all games
    std::vector<std::map<std::string, int>> buyCountsByTurn(trackTurns);
    // Also track which games bought each unit within the turn window
    std::map<std::string, int> gamesBoughtUnit;

    for (size_t game = 0; game < numGames; ++game)
    {
        // Build starting state with specific card set using setStartingState for base setup,
        // but we need specific dominion cards. Use the JSON constructor approach instead.
        // Build a JSON string for the state
        std::string cardsJson = "[\"Drone\",\"Engineer\",\"Academy\",\"Brooder\",\"Conduit\",\"Tesla Tower\",\"Elephant\",\"Wall\",\"Treant\",\"Blood Barrier\",\"Minicannon\"";
        for (const auto & cardName : dominionCards)
        {
            // Need internal name for JSON state
            if (CardTypes::CardTypeExists(cardName))
            {
                cardsJson += ",\"" + CardTypes::GetCardType(cardName).getName() + "\"";
            }
            else
            {
                printf("WARNING: Card '%s' not found!\n", cardName.c_str());
            }
        }
        cardsJson += "]";

        std::string jsonStr = "{\"whiteMana\":\"0\",\"blackMana\":\"0\",\"phase\":\"action\","
            "\"table\":["
            "{\"cardName\":\"Drone\",\"color\":0,\"amount\":6},"
            "{\"cardName\":\"Engineer\",\"color\":0,\"amount\":2},"
            "{\"cardName\":\"Drone\",\"color\":1,\"amount\":7},"
            "{\"cardName\":\"Engineer\",\"color\":1,\"amount\":2}"
            "],\"cards\":" + cardsJson + "}";

        rapidjson::Document doc;
        doc.Parse(jsonStr.c_str());
        PRISMATA_ASSERT(!doc.HasParseError(), "Failed to parse fixed set JSON");
        GameState state(doc);

        // Create players
        PlayerPtr p1 = AIParameters::Instance().getPlayer(Players::Player_One, playerName);
        PlayerPtr p2 = AIParameters::Instance().getPlayer(Players::Player_Two, playerName);

        printf("--- Game %zu ---\n", game + 1);

        // Play the game turn by turn, logging buys
        Game g(state, p1, p2);
        int turnNumber = 0;
        std::set<std::string> boughtThisGame;

        while (!g.gameOver() && turnNumber < (int)(trackTurns * 2))  // *2 because each player gets a turn
        {
            PlayerID playerToMove = g.getState().getActivePlayer();
            g.playNextTurn();

            // Extract buy actions from the move
            const Move & move = g.getPreviousMove();
            std::string buys;
            for (size_t a = 0; a < move.size(); ++a)
            {
                const Action & action = move.getAction(a);
                if (action.getType() == ActionTypes::BUY)
                {
                    std::string unitName = CardType(action.getID()).getUIName();
                    if (!buys.empty()) buys += ", ";
                    buys += unitName;

                    if ((size_t)turnNumber < trackTurns * 2)
                    {
                        size_t playerTurn = turnNumber / 2;  // Convert to round number
                        if (playerTurn < trackTurns)
                        {
                            buyCountsByTurn[playerTurn][unitName]++;
                        }
                        boughtThisGame.insert(unitName);
                    }
                }
            }
            printf("  [T%d P%d] %s: %s\n", turnNumber, (int)playerToMove, playerName.c_str(),
                   buys.empty() ? "(no buys)" : buys.c_str());
            fflush(stdout);
            turnNumber++;
        }

        // Record which units were bought in this game
        for (const auto & name : boughtThisGame)
        {
            gamesBoughtUnit[name]++;
        }
        printf("\n");
    }

    // Summary
    printf("\n=== SUMMARY: %zu games, first %zu rounds ===\n", numGames, trackTurns);
    printf("Unit buy frequency (games where unit was purchased / total games):\n\n");

    // Sort by games bought descending
    std::vector<std::pair<std::string, int>> sortedUnits(gamesBoughtUnit.begin(), gamesBoughtUnit.end());
    std::sort(sortedUnits.begin(), sortedUnits.end(), [](const auto & a, const auto & b) { return a.second > b.second; });

    printf("%-30s %8s %8s\n", "Unit", "Games", "Rate");
    printf("%s\n", std::string(50, '-').c_str());
    for (const auto & entry : sortedUnits)
    {
        double rate = (double)entry.second / numGames * 100.0;
        printf("%-30s %8d %7.1f%%\n", entry.first.c_str(), entry.second, rate);
    }

    // Check specific dominion cards
    printf("\n--- Dominion card buy rates ---\n");
    for (const auto & cardName : dominionCards)
    {
        int count = gamesBoughtUnit.count(cardName) ? gamesBoughtUnit[cardName] : 0;
        double rate = (double)count / numGames * 100.0;
        printf("%-30s %d/%zu games (%.1f%%)\n", cardName.c_str(), count, numGames, rate);
    }
    printf("\n=== End Fixed Set Test ===\n\n");
}

// Helper: find a card owned by player with matching type name that satisfies a predicate
static CardID findCard(const GameState & state, PlayerID player, const std::string & cardName,
                       bool (Card::*predicate)() const)
{
    const CardIDVector & cardIDs = state.getCardIDs(player);
    for (size_t i = 0; i < cardIDs.size(); i++)
    {
        const Card & card = state.getCardByID(cardIDs[i]);
        if ((card.getType().getUIName() == cardName || card.getType().getName() == cardName)
            && (card.*predicate)())
        {
            return cardIDs[i];
        }
    }
    return (CardID)-1;
}

// Helper: find CardType ID for a buyable card by name (BUY action uses CardType ID, not sequential index)
static CardID findBuyableCardTypeID(const GameState & state, const std::string & cardName)
{
    for (CardID i = 0; i < state.numCardsBuyable(); i++)
    {
        const CardBuyable & buyable = state.getCardBuyableByIndex(i);
        if (buyable.getType().getUIName() == cardName || buyable.getType().getName() == cardName)
        {
            return buyable.getType().getID();
        }
    }
    return (CardID)-1;
}

// Helper: resolve an action from the validation file to a C++ Action
static Action resolveAction(const GameState & state, const std::string & type,
                            const std::string & cardName, PlayerID activePlayer)
{
    if (type == "END_PHASE")
    {
        return Action(activePlayer, ActionTypes::END_PHASE, 0);
    }

    if (type == "USE_ABILITY")
    {
        CardID cardID = findCard(state, activePlayer, cardName, &Card::canUseAbility);
        if (cardID != (CardID)-1)
        {
            return Action(activePlayer, ActionTypes::USE_ABILITY, cardID);
        }
        return Action();
    }

    if (type == "BUY")
    {
        CardID typeID = findBuyableCardTypeID(state, cardName);
        if (typeID != (CardID)-1)
        {
            return Action(activePlayer, ActionTypes::BUY, typeID);
        }
        return Action();
    }

    if (type == "ASSIGN_BLOCKER")
    {
        CardID cardID = findCard(state, activePlayer, cardName, &Card::canBlock);
        if (cardID != (CardID)-1)
        {
            return Action(activePlayer, ActionTypes::ASSIGN_BLOCKER, cardID);
        }
        return Action();
    }

    if (type == "ASSIGN_BREACH")
    {
        PlayerID enemy = (activePlayer == 0) ? 1 : 0;
        CardID cardID = findCard(state, enemy, cardName, &Card::isBreachable);
        if (cardID != (CardID)-1)
        {
            return Action(activePlayer, ActionTypes::ASSIGN_BREACH, cardID);
        }
        return Action();
    }

    if (type == "ASSIGN_FRONTLINE")
    {
        PlayerID enemy = (activePlayer == 0) ? 1 : 0;
        const CardIDVector & enemyCards = state.getCardIDs(enemy);
        for (size_t i = 0; i < enemyCards.size(); i++)
        {
            const Card & card = state.getCardByID(enemyCards[i]);
            if ((card.getType().getUIName() == cardName || card.getType().getName() == cardName)
                && card.isInPlay() && !card.isDead())
            {
                Action a(activePlayer, ActionTypes::ASSIGN_FRONTLINE, enemyCards[i]);
                if (state.isLegal(a))
                {
                    return a;
                }
            }
        }
        return Action();
    }

    if (type == "SNIPE" || type == "CHILL")
    {
        // Find source: our card with a targeting ability that can use its ability
        PlayerID enemy = (activePlayer == 0) ? 1 : 0;
        CardID sourceID = (CardID)-1;

        const CardIDVector & myCards = state.getCardIDs(activePlayer);
        for (size_t i = 0; i < myCards.size(); i++)
        {
            const Card & card = state.getCardByID(myCards[i]);
            if (card.getType().hasTargetAbility() && card.canUseAbility())
            {
                sourceID = myCards[i];
                break;
            }
        }

        if (sourceID == (CardID)-1)
        {
            return Action();
        }

        // Find target: enemy card matching name
        const CardIDVector & enemyCards = state.getCardIDs(enemy);
        for (size_t i = 0; i < enemyCards.size(); i++)
        {
            const Card & card = state.getCardByID(enemyCards[i]);
            if ((card.getType().getUIName() == cardName || card.getType().getName() == cardName)
                && card.isInPlay())
            {
                ActionID actionType = state.getCardByID(sourceID).getType().getTargetAbilityType();
                return Action(activePlayer, actionType, sourceID, enemyCards[i]);
            }
        }
        return Action();
    }

    printf("  WARNING: Unknown action type '%s'\n", type.c_str());
    return Action();
}

void Benchmarks::DoReplayValidation(const std::string & validationFile, const std::string & outputFile)
{
    printf("\n=== Replay Validation ===\n");
    printf("Input:  %s\n", validationFile.c_str());
    printf("Output: %s\n", outputFile.c_str());

    // Read validation JSON
    std::string content = FileUtils::ReadFile(validationFile);
    if (content.empty())
    {
        printf("ERROR: Could not read validation file\n");
        return;
    }

    rapidjson::Document doc;
    if (doc.Parse(content.c_str()).HasParseError())
    {
        printf("ERROR: Failed to parse validation JSON (offset %zu)\n", doc.GetErrorOffset());
        return;
    }

    std::string replayCode = doc.HasMember("replay_code") ? doc["replay_code"].GetString() : "unknown";
    printf("Replay: %s\n", replayCode.c_str());

    if (!doc.HasMember("initial_state") || !doc.HasMember("turns"))
    {
        printf("ERROR: Validation file missing initial_state or turns\n");
        return;
    }

    // Construct initial game state from the converted JSON
    GameState state(doc["initial_state"]);

    printf("Initial state loaded: P%d to move, %d cards buyable\n",
           (int)state.getActivePlayer(), (int)state.numCardsBuyable());
    printf("P0 cards: %d, P1 cards: %d\n",
           (int)state.numCards(0), (int)state.numCards(1));

    // Open output file (JSONL: one JSON object per line)
    std::ofstream out(outputFile);
    if (!out.is_open())
    {
        printf("ERROR: Could not open output file '%s'\n", outputFile.c_str());
        return;
    }

    // Write initial state (turn -1)
    out << "{\"turn\":-1,\"label\":\"initial\",\"active_player\":"
        << (int)state.getActivePlayer()
        << ",\"state\":" << state.toJSONString() << "}\n";

    const rapidjson::Value & turns = doc["turns"];
    int totalErrors = 0;
    int turnsProcessed = 0;

    for (size_t t = 0; t < turns.Size(); t++)
    {
        const rapidjson::Value & turn = turns[t];
        int expectedPlayer = turn["active_player"].GetInt();
        std::string playerName = turn.HasMember("player_name") ? turn["player_name"].GetString() : "";

        // Check active player matches
        if ((int)state.getActivePlayer() != expectedPlayer)
        {
            printf("Turn %zu: ACTIVE PLAYER MISMATCH (engine=%d expected=%d)\n",
                   t, (int)state.getActivePlayer(), expectedPlayer);
            totalErrors++;
            // Try to continue anyway
        }

        PlayerID activePlayer = state.getActivePlayer();

        // If we're in Defense phase but the first action is not ASSIGN_BLOCKER,
        // the engine needs defense resolved first. The reordered converter puts
        // defense actions first, but if there are no defense actions (empty defense),
        // we need to skip Defense -> Swoosh -> Action automatically.
        if (state.getActivePhase() == Phases::Defense)
        {
            bool hasDefenseActions = false;
            for (size_t a = 0; a < turn["actions"].Size(); a++)
            {
                std::string aType = turn["actions"][a]["type"].GetString();
                if (aType == "ASSIGN_BLOCKER") { hasDefenseActions = true; break; }
                if (aType != "END_PHASE") break; // first non-END_PHASE action is not defense
            }
            if (!hasDefenseActions)
            {
                // No defense actions but engine is in Defense — fire END_PHASE to skip
                Action endPhase(activePlayer, ActionTypes::END_PHASE, 0);
                if (state.isLegal(endPhase))
                {
                    state.doAction(endPhase);
                }
                else
                {
                    printf("  Turn %zu: WARNING: In Defense phase with no defense actions, END_PHASE not legal (attack=%d)\n",
                           t, 0);
                }
            }
        }

        // Apply actions for this turn
        const rapidjson::Value & actions = turn["actions"];
        int turnErrors = 0;

        for (size_t a = 0; a < actions.Size(); a++)
        {
            std::string actionType = actions[a]["type"].GetString();
            std::string cardName = actions[a].HasMember("card_name") ?
                                   actions[a]["card_name"].GetString() : "";

            Action action = resolveAction(state, actionType, cardName, activePlayer);

            if (action.getType() == ActionTypes::NONE)
            {
                printf("  Turn %zu [P%d %s] action %zu: RESOLVE FAILED: %s '%s' (phase=%d)\n",
                       t, expectedPlayer, playerName.c_str(), a,
                       actionType.c_str(), cardName.c_str(), state.getActivePhase());
                // On first error per turn, dump player's card list for debugging
                if (turnErrors == 0)
                {
                    printf("    P%d cards:", activePlayer);
                    for (const auto & cid : state.getCardIDs(activePlayer))
                    {
                        const Card & dc = state.getCardByID(cid);
                        printf(" %s(s%d)", dc.getType().getUIName().c_str(), dc.getStatus());
                    }
                    printf("\n");
                }
                turnErrors++;
                continue;
            }

            if (!state.isLegal(action))
            {
                printf("  Turn %zu [P%d %s] action %zu: NOT LEGAL: %s '%s' (phase=%d)\n",
                       t, expectedPlayer, playerName.c_str(), a,
                       actionType.c_str(), cardName.c_str(), state.getActivePhase());
                turnErrors++;
                continue;
            }

            state.doAction(action);
        }

        // After all explicit actions, ensure turn transition completes.
        // The engine may need additional END_PHASE calls for phases
        // not explicitly in the validation file (e.g., empty defense).
        int safety = 10;
        while ((int)state.getActivePlayer() == expectedPlayer && !state.isGameOver() && safety-- > 0)
        {
            Action endPhase(activePlayer, ActionTypes::END_PHASE, 0);
            if (state.isLegal(endPhase))
            {
                state.doAction(endPhase);
            }
            else
            {
                break;
            }
        }

        totalErrors += turnErrors;
        turnsProcessed++;

        // Write post-turn state
        out << "{\"turn\":" << t
            << ",\"player\":" << expectedPlayer
            << ",\"player_name\":\"" << playerName << "\""
            << ",\"errors\":" << turnErrors
            << ",\"active_player_after\":" << (int)state.getActivePlayer()
            << ",\"phase_after\":" << state.getActivePhase()
            << ",\"game_over\":" << (state.isGameOver() ? "true" : "false")
            << ",\"state\":" << state.toJSONString() << "}\n";

        if (state.isGameOver())
        {
            printf("  Game over after turn %zu (winner: P%d)\n", t, (int)state.winner());
            break;
        }
    }

    out.close();

    printf("\n--- Validation Summary ---\n");
    printf("Turns processed: %d / %d\n", turnsProcessed, (int)turns.Size());
    printf("Total errors:    %d\n", totalErrors);
    printf("Output written:  %s\n", outputFile.c_str());
    printf("=== End Replay Validation ===\n\n");
}
