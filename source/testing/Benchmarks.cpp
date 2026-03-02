#include "PrismataAI.h"
#include "Benchmarks.h"
#include "PlayerBenchmark.h"
#include "Tournament.h"
#include "TournamentGame.h"
#include "Game.h"
#include "NeuralNet.h"
#include "Player_StackAlphaBeta.h"
#include "Player_UCT.h"
#include "ReplayStepper.h"
#include "SelfPlayDataSink.h"
#include "rapidjson/document.h"
#include <thread>
#include <map>
#include <set>
#include <algorithm>
#include <iomanip>
#include <cmath>
#include <fstream>
#include <sstream>
#include <atomic>
#include <filesystem>
#ifdef _WIN32
#include <io.h>     // _dup, _dup2, _close, _fileno
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
        // Targeting abilities are two-step in the engine:
        //   Step 1: USE_ABILITY on source card (sets m_targetAbilityCardClicked flag)
        //   Step 2: SNIPE/CHILL action with source + target (requires flag set)
        // If the flag is already set, we're on step 2. Otherwise do step 1 first.
        PlayerID enemy = (activePlayer == 0) ? 1 : 0;
        CardID sourceID = (CardID)-1;

        const CardIDVector & myCards = state.getCardIDs(activePlayer);
        for (size_t i = 0; i < myCards.size(); i++)
        {
            const Card & card = state.getCardByID(myCards[i]);
            if (card.getType().hasTargetAbility() && card.canUseAbility() && !card.hasTarget())
            {
                sourceID = myCards[i];
                break;
            }
        }

        if (sourceID == (CardID)-1)
        {
            return Action();
        }

        // Step 1: If source not yet clicked, return USE_ABILITY to set the targeting flag
        if (!state.isTargetAbilityCardClicked())
        {
            return Action(activePlayer, ActionTypes::USE_ABILITY, sourceID);
        }

        // Step 2: Find target enemy card and issue the targeting action
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

            // Targeting abilities are two-step: USE_ABILITY (step 1) then SNIPE/CHILL (step 2).
            // If resolveAction returned USE_ABILITY for a SNIPE/CHILL request, re-resolve to get step 2.
            if ((actionType == "SNIPE" || actionType == "CHILL") && action.getType() == ActionTypes::USE_ABILITY)
            {
                Action step2 = resolveAction(state, actionType, cardName, activePlayer);
                if (step2.getType() == ActionTypes::NONE)
                {
                    printf("  Turn %zu [P%d %s] action %zu: RESOLVE FAILED (step2): %s '%s' (phase=%d)\n",
                           t, expectedPlayer, playerName.c_str(), a,
                           actionType.c_str(), cardName.c_str(), state.getActivePhase());
                    turnErrors++;
                    continue;
                }
                if (!state.isLegal(step2))
                {
                    printf("  Turn %zu [P%d %s] action %zu: NOT LEGAL (step2): %s '%s' (phase=%d)\n",
                           t, expectedPlayer, playerName.c_str(), a,
                           actionType.c_str(), cardName.c_str(), state.getActivePhase());
                    turnErrors++;
                    continue;
                }
                state.doAction(step2);
            }
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
                // Shift-click expands to all cards of same type
                if (action.getShift())
                {
                    const CardType ct = state.getCardByID(action.getID()).getType();
                    for (const auto & cid : state.getCardIDs(action.getPlayer()))
                    {
                        if (state.getCardByID(cid).getType() == ct && state.getCardByID(cid).getClientInstId() >= 0)
                            abilities.push_back(ct.getUIName());
                    }
                }
                else
                {
                    abilities.push_back(state.getCardByID(action.getID()).getType().getUIName());
                }
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
                break; // END_PHASE, WIPEOUT, UNDO_*, SELL — skip
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
                // Shift-click means "activate all cards of this type" (e.g., all Drones).
                // The C++ engine expands shift internally (GameState.cpp:599-638), but the
                // Move only contains ONE action. We must emit inst clicks for ALL matching
                // cards so the JS engine (which has no shift expansion) activates them all.
                if (action.getShift())
                {
                    const CardType actionCardType = state.getCardByID(action.getID()).getType();
                    for (const auto & cardID : state.getCardIDs(action.getPlayer()))
                    {
                        const Card & card = state.getCardByID(cardID);
                        if (card.getType() == actionCardType && card.getClientInstId() >= 0)
                        {
                            appendClick(clicksOut, hasPrevClick, "inst clicked", card.getClientInstId());
                        }
                    }
                }
                else
                {
                    int instId = state.getCardByID(action.getID()).getClientInstId();
                    appendClick(clicksOut, hasPrevClick, "inst clicked", instId);
                }
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
                // Skip — we insert END_PHASE automatically above
                break;
            default:
                break;
        }
    }
    // Final two END_PHASE clicks: enter confirm + commit (matches Move::toClientString())
    appendClick(clicksOut, hasPrevClick, "space clicked", -1);
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
    out << ",\"state_hash\":\"" << state.debugStateHash() << "\"";
    out << "}";

    printf("%s\n", out.str().c_str());
    fflush(stdout);
}

// ---------------------------------------------------------------------------
// --replay mode: Process replay JSON -> binary training shards
// ---------------------------------------------------------------------------

// Process a single replay JSON, writing training data via the provided sink.
// Returns true if the replay was processed (even partially), false if skipped/failed to init.
static bool processReplay(const std::string & replayFile, int minRating, SelfPlayDataSink & sink)
{
    // 1. Read replay JSON
    std::ifstream ifs(replayFile);
    if (!ifs.is_open())
    {
        fprintf(stderr, "[Replay] Cannot open: %s\n", replayFile.c_str());
        return false;
    }
    std::string raw((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    ifs.close();
    if (raw.empty())
    {
        fprintf(stderr, "[Replay] Empty file: %s\n", replayFile.c_str());
        return false;
    }

    // 2. Parse JSON
    rapidjson::Document doc;
    if (doc.Parse(raw.c_str()).HasParseError())
    {
        fprintf(stderr, "[Replay] JSON parse error: %s\n", replayFile.c_str());
        return false;
    }

    // 3. Extract required sections
    if (!doc.HasMember("deckInfo") || !doc["deckInfo"].HasMember("mergedDeck"))
    {
        fprintf(stderr, "[Replay] Missing deckInfo.mergedDeck: %s\n", replayFile.c_str());
        return false;
    }
    if (!doc.HasMember("initInfo"))
    {
        fprintf(stderr, "[Replay] Missing initInfo: %s\n", replayFile.c_str());
        return false;
    }
    if (!doc.HasMember("commandInfo") || !doc["commandInfo"].HasMember("commandList")
        || !doc["commandInfo"].HasMember("clicksPerTurn"))
    {
        fprintf(stderr, "[Replay] Missing commandInfo: %s\n", replayFile.c_str());
        return false;
    }
    if (!doc.HasMember("playerInfo"))
    {
        fprintf(stderr, "[Replay] Missing playerInfo: %s\n", replayFile.c_str());
        return false;
    }

    // 4. Rating filter
    if (minRating > 0 && doc.HasMember("ratingInfo") && doc["ratingInfo"].HasMember("finalRatings"))
    {
        const auto & ratings = doc["ratingInfo"]["finalRatings"];
        if (ratings.IsArray() && ratings.Size() >= 2)
        {
            int r0 = ratings[0].HasMember("displayRating") ? (int)ratings[0]["displayRating"].GetDouble() : 0;
            int r1 = ratings[1].HasMember("displayRating") ? (int)ratings[1]["displayRating"].GetDouble() : 0;
            int minR = std::min(r0, r1);
            if (minR < minRating)
            {
                return false;  // Skip — below rating threshold
            }
        }
    }

    const auto & mergedDeck = doc["deckInfo"]["mergedDeck"];
    const auto & initInfo = doc["initInfo"];
    const auto & commandList = doc["commandInfo"]["commandList"];
    const auto & clicksPerTurn = doc["commandInfo"]["clicksPerTurn"];
    const auto & playerInfo = doc["playerInfo"];

    // 5. Initialize stepper
    ReplayStepper stepper;
    if (!stepper.init(mergedDeck, initInfo, commandList, clicksPerTurn, playerInfo))
    {
        fprintf(stderr, "[Replay] Init failed: %s\n", replayFile.c_str());
        return false;
    }

    // 6. Step through turns, capturing training data
    //    Continue after FatalError (up to a limit) to extract later turns
    //    Only capture training data when recent errors are low
    int turnsExtracted = 0;
    int fatalErrorCount = 0;
    const int maxFatalErrors = 5;
    while (stepper.hasNextTurn())
    {
        // Only capture training data if we haven't hit too many errors
        if (fatalErrorCount <= 1)
        {
            sink.onTurnStart(stepper.getState());
            turnsExtracted++;
        }

        ReplayStepper::StepResult result = stepper.advanceTurn();
        if (result == ReplayStepper::StepResult::FatalError)
        {
            fatalErrorCount++;
            if (fatalErrorCount >= maxFatalErrors)
                break;
            // Continue to next turn — state may recover
            continue;
        }
        if (result == ReplayStepper::StepResult::GameOver)
            break;

        // Reset error streak on successful turn
        // (but keep total count for quality gating)
    }

    // 7. Determine winner from replay result field
    //    result=0 means P1 wins, result=1 means P2 wins
    PlayerID winner = Players::Player_None;
    if (doc.HasMember("result"))
    {
        int result = doc["result"].GetInt();
        if (result == 0)
            winner = Players::Player_One;
        else if (result == 1)
            winner = Players::Player_Two;
    }

    // Call onGameEnd to label all captured turns with the outcome
    sink.onGameEnd(winner);

    // 8. Log stats to stderr
    fprintf(stderr, "[Replay] %s: %d turns extracted, %d/%d clicks applied, %d skips, %d errors\n",
            replayFile.c_str(), turnsExtracted,
            stepper.getAppliedClicks(), stepper.getTotalClicks(),
            stepper.getBenignSkips(), stepper.getFatalErrors());

    return true;
}

void Benchmarks::DoReplay(const std::string & replayFile, const std::string & outputDir, int minRating)
{
    // Create output directory if it doesn't exist
    std::filesystem::create_directories(outputDir);

    // Create sink — single replay mode
    std::atomic<uint32_t> gameCounter{0};
    SelfPlayDataSink sink(0, outputDir, gameCounter);

    bool ok = processReplay(replayFile, minRating, sink);

    sink.finalize();

    if (ok)
    {
        fprintf(stderr, "[Replay] Done: %u games, %llu records written to %s\n",
                sink.totalGamesCompleted(), (unsigned long long)sink.totalRecordsWritten(),
                outputDir.c_str());
    }
    else
    {
        fprintf(stderr, "[Replay] Failed to process: %s\n", replayFile.c_str());
    }
}

void Benchmarks::DoReplayBatch(const std::string & replayDir, const std::string & outputDir, int minRating)
{
    // Create output directory if it doesn't exist
    std::filesystem::create_directories(outputDir);

    // Scan directory for .json files
    std::vector<std::string> replayFiles;
    for (const auto & entry : std::filesystem::recursive_directory_iterator(replayDir))
    {
        if (!entry.is_regular_file()) continue;
        std::string ext = entry.path().extension().string();
        if (ext == ".json")
        {
            replayFiles.push_back(entry.path().string());
        }
    }

    if (replayFiles.empty())
    {
        fprintf(stderr, "[Replay] No .json files found in %s\n", replayDir.c_str());
        return;
    }

    std::sort(replayFiles.begin(), replayFiles.end());

    fprintf(stderr, "[Replay] Found %zu replay files in %s\n", replayFiles.size(), replayDir.c_str());

    // Create shared sink for all replays (long-lived — avoids 32K tiny shards)
    std::atomic<uint32_t> gameCounter{0};
    SelfPlayDataSink sink(0, outputDir, gameCounter);

    int successCount = 0;
    int failCount = 0;
    int skipCount = 0;

    for (size_t i = 0; i < replayFiles.size(); i++)
    {
        bool ok = processReplay(replayFiles[i], minRating, sink);
        if (ok)
            successCount++;
        else
            failCount++;

        // Progress every 100 replays
        if ((i + 1) % 100 == 0 || i + 1 == replayFiles.size())
        {
            fprintf(stderr, "[Replay] Progress: %zu/%zu files, %d success, %d failed, %u games, %llu records\n",
                    i + 1, replayFiles.size(), successCount, failCount,
                    sink.totalGamesCompleted(), (unsigned long long)sink.totalRecordsWritten());
        }
    }

    sink.finalize();

    fprintf(stderr, "\n=== Replay Batch Summary ===\n");
    fprintf(stderr, "Total files:     %zu\n", replayFiles.size());
    fprintf(stderr, "Successful:      %d\n", successCount);
    fprintf(stderr, "Failed:          %d\n", failCount);
    fprintf(stderr, "Games written:   %u\n", sink.totalGamesCompleted());
    fprintf(stderr, "Records written: %llu\n", (unsigned long long)sink.totalRecordsWritten());
    fprintf(stderr, "Output dir:      %s\n", outputDir.c_str());
    fprintf(stderr, "============================\n");
}

// ---------------------------------------------------------------------------
// --eval mode: Replay JSON -> per-turn neural evaluation -> JSON output
// ---------------------------------------------------------------------------

void Benchmarks::DoEval(const std::string & replayFile)
{
    // 1. Check neural net is loaded
    if (!NeuralNet::Instance().isLoaded())
    {
        printf("{\"ok\":false,\"error\":\"Neural network weights not loaded\"}\n");
        fflush(stdout);
        return;
    }

    // 2. Read and parse replay JSON
    std::ifstream ifs(replayFile);
    if (!ifs.is_open())
    {
        printf("{\"ok\":false,\"error\":\"Cannot open: %s\"}\n", jsonEscape(replayFile).c_str());
        fflush(stdout);
        return;
    }
    std::string raw((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    ifs.close();

    rapidjson::Document doc;
    if (doc.Parse(raw.c_str()).HasParseError())
    {
        printf("{\"ok\":false,\"error\":\"JSON parse error\"}\n");
        fflush(stdout);
        return;
    }

    // 3. Validate required sections
    if (!doc.HasMember("deckInfo") || !doc["deckInfo"].HasMember("mergedDeck")
        || !doc.HasMember("initInfo")
        || !doc.HasMember("commandInfo") || !doc["commandInfo"].HasMember("commandList")
        || !doc["commandInfo"].HasMember("clicksPerTurn")
        || !doc.HasMember("playerInfo"))
    {
        printf("{\"ok\":false,\"error\":\"Missing required replay sections\"}\n");
        fflush(stdout);
        return;
    }

    // 4. Extract player names and ratings
    const auto & playerInfo = doc["playerInfo"];
    std::string p0Name = "Player 1";
    std::string p1Name = "Player 2";
    int p0Rating = 0, p1Rating = 0;

    if (playerInfo.IsArray() && playerInfo.Size() >= 2)
    {
        if (playerInfo[0].HasMember("name"))
            p0Name = playerInfo[0]["name"].GetString();
        if (playerInfo[1].HasMember("name"))
            p1Name = playerInfo[1]["name"].GetString();
    }
    if (doc.HasMember("ratingInfo") && doc["ratingInfo"].HasMember("finalRatings"))
    {
        const auto & ratings = doc["ratingInfo"]["finalRatings"];
        if (ratings.IsArray() && ratings.Size() >= 2)
        {
            if (ratings[0].HasMember("displayRating"))
                p0Rating = (int)ratings[0]["displayRating"].GetDouble();
            if (ratings[1].HasMember("displayRating"))
                p1Rating = (int)ratings[1]["displayRating"].GetDouble();
        }
    }

    // 5. Determine winner
    int winner = -1;
    if (doc.HasMember("result"))
        winner = doc["result"].GetInt();

    // 6. Extract replay code from filename (strip path and .json extension)
    std::string code = replayFile;
    size_t lastSlash = code.find_last_of("/\\");
    if (lastSlash != std::string::npos) code = code.substr(lastSlash + 1);
    size_t dotPos = code.rfind(".json");
    if (dotPos != std::string::npos) code = code.substr(0, dotPos);

    // 7. Initialize stepper and run eval loop
    //    Redirect stdout to stderr for the entire stepping phase to suppress
    //    PRISMATA_ASSERT noise (prints to stdout, can corrupt JSON output)
    const auto & mergedDeck = doc["deckInfo"]["mergedDeck"];
    const auto & initInfo = doc["initInfo"];
    const auto & commandList = doc["commandInfo"]["commandList"];
    const auto & clicksPerTurn = doc["commandInfo"]["clicksPerTurn"];

    fflush(stdout);
    int savedFd = _dup(_fileno(stdout));
    _dup2(_fileno(stderr), _fileno(stdout));

    ReplayStepper stepper;
    bool initOk = stepper.init(mergedDeck, initInfo, commandList, clicksPerTurn, playerInfo);

    if (!initOk)
    {
        fflush(stdout);
        _dup2(savedFd, _fileno(stdout));
        _close(savedFd);
        printf("{\"ok\":false,\"error\":\"ReplayStepper init failed\"}\n");
        fflush(stdout);
        return;
    }

    // 8. Step through turns, evaluating each position
    struct TurnEval
    {
        int turn;
        int player;
        float eval;     // raw value from neural net (P1 perspective)
    };
    std::vector<TurnEval> turnEvals;
    int fatalErrorCount = 0;
    const int maxFatalErrors = 5;

    while (stepper.hasNextTurn())
    {
        const GameState & state = stepper.getState();

        // Neural eval — value is from active player's perspective
        // Convert to P1's perspective for consistent output
        auto output = NeuralNet::Instance().evaluate(state);
        float evalP1 = (state.getActivePlayer() == Players::Player_One)
            ? output.value : -output.value;

        TurnEval te;
        te.turn = stepper.getCurrentTurn();
        te.player = (int)stepper.getActivePlayer();
        te.eval = evalP1;
        turnEvals.push_back(te);

        ReplayStepper::StepResult result = stepper.advanceTurn();
        if (result == ReplayStepper::StepResult::FatalError)
        {
            fatalErrorCount++;
            if (fatalErrorCount >= maxFatalErrors)
                break;
            continue;
        }
        if (result == ReplayStepper::StepResult::GameOver)
            break;
    }

    // Restore stdout now that stepping is complete (PRISMATA_ASSERT noise suppressed)
    fflush(stdout);
    _dup2(savedFd, _fileno(stdout));
    _close(savedFd);

    // 9. Compute eval statistics
    float maxSwing = 0.0f;
    int biggestMistakeTurn = -1;
    float biggestMistakeDrop = 0.0f;

    for (size_t i = 1; i < turnEvals.size(); i++)
    {
        float delta = turnEvals[i].eval - turnEvals[i - 1].eval;
        float absDelta = std::abs(delta);
        if (absDelta > maxSwing)
            maxSwing = absDelta;

        // A "mistake" is when the eval drops significantly for the player who just moved
        // If P1 just moved (turnEvals[i-1].player == 0) and eval dropped, P1 made a mistake
        // If P2 just moved (turnEvals[i-1].player == 1) and eval rose, P2 made a mistake
        float mistake = 0.0f;
        if (turnEvals[i - 1].player == 0)
            mistake = -delta;  // P1 moved; drop in P1 eval = P1 mistake
        else
            mistake = delta;   // P2 moved; rise in P1 eval = P2 mistake

        if (mistake > biggestMistakeDrop)
        {
            biggestMistakeDrop = mistake;
            biggestMistakeTurn = turnEvals[i - 1].turn;
        }
    }

    // 10. Output JSON
    printf("{\"ok\":true");
    printf(",\"code\":\"%s\"", jsonEscape(code).c_str());
    printf(",\"players\":[\"%s\",\"%s\"]", jsonEscape(p0Name).c_str(), jsonEscape(p1Name).c_str());
    printf(",\"ratings\":[%d,%d]", p0Rating, p1Rating);
    printf(",\"winner\":%d", winner);
    printf(",\"turns_evaluated\":%zu", turnEvals.size());
    printf(",\"fatal_errors\":%d", fatalErrorCount);

    // Turn-by-turn evals
    printf(",\"turns\":[");
    for (size_t i = 0; i < turnEvals.size(); i++)
    {
        if (i > 0) printf(",");
        float pct = (turnEvals[i].eval + 1.0f) / 2.0f * 100.0f;  // [-1,1] -> [0%,100%]
        printf("{\"turn\":%d,\"player\":%d,\"eval\":%.4f,\"eval_pct\":\"%.0f%%\"}",
               turnEvals[i].turn, turnEvals[i].player, turnEvals[i].eval, pct);
    }
    printf("]");

    // Summary stats
    printf(",\"eval_swing\":%.4f", maxSwing);
    if (biggestMistakeTurn >= 0)
    {
        printf(",\"biggest_mistake\":{\"turn\":%d,\"eval_drop\":%.4f}",
               biggestMistakeTurn, biggestMistakeDrop);
    }

    printf("}\n");
    fflush(stdout);
}

// ---------------------------------------------------------------------------
// --analyze mode: Replay JSON -> per-turn AI comparison -> JSON output
// ---------------------------------------------------------------------------

// Helper: categorize a Move into buy/ability/defense/breach string lists
static void categorizeMove(const Move & move, const GameState & state,
                           std::vector<std::string> & buys,
                           std::vector<std::string> & abilities,
                           std::vector<std::string> & defense,
                           std::vector<std::string> & breach)
{
    buys.clear(); abilities.clear(); defense.clear(); breach.clear();
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
                break;
        }
    }
    std::sort(buys.begin(), buys.end());
    std::sort(abilities.begin(), abilities.end());
    std::sort(defense.begin(), defense.end());
    std::sort(breach.begin(), breach.end());
}

// Helper: extract human buys from commandList clicks for a given turn
static std::vector<std::string> extractHumanBuys(
    const rapidjson::Value & commandList, int clickStart, int clickCount,
    const rapidjson::Value & mergedDeck)
{
    std::vector<std::string> buys;
    int clickEnd = clickStart + clickCount;
    if (clickEnd > (int)commandList.Size())
        clickEnd = (int)commandList.Size();

    for (int i = clickStart; i < clickEnd; ++i)
    {
        if (!commandList[i].IsObject()) continue;
        if (!commandList[i].HasMember("_type")) continue;

        std::string type = commandList[i]["_type"].GetString();
        if (type == "card clicked" || type == "card shift clicked")
        {
            int deckIdx = commandList[i]["_id"].GetInt();
            if (deckIdx >= 0 && deckIdx < (int)mergedDeck.Size())
            {
                const auto & card = mergedDeck[deckIdx];
                if (card.HasMember("UIName") && card["UIName"].IsString())
                    buys.push_back(card["UIName"].GetString());
                else if (card.HasMember("name") && card["name"].IsString())
                    buys.push_back(card["name"].GetString());
            }
        }
        else if (type == "revert clicked")
        {
            // Undo last buy if any
            if (!buys.empty()) buys.pop_back();
        }
    }
    std::sort(buys.begin(), buys.end());
    return buys;
}

void Benchmarks::DoAnalyze(const std::string & replayFile, const std::string & playerName, int thinkTimeMs)
{
    // 1. Check neural net
    if (!NeuralNet::Instance().isLoaded())
    {
        printf("{\"ok\":false,\"error\":\"Neural network weights not loaded\"}\n");
        fflush(stdout);
        return;
    }

    // 2. Read and parse replay JSON
    std::ifstream ifs(replayFile);
    if (!ifs.is_open())
    {
        printf("{\"ok\":false,\"error\":\"Cannot open: %s\"}\n", jsonEscape(replayFile).c_str());
        fflush(stdout);
        return;
    }
    std::string raw((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    ifs.close();

    rapidjson::Document doc;
    if (doc.Parse(raw.c_str()).HasParseError())
    {
        printf("{\"ok\":false,\"error\":\"JSON parse error\"}\n");
        fflush(stdout);
        return;
    }

    // 3. Validate required sections
    if (!doc.HasMember("deckInfo") || !doc["deckInfo"].HasMember("mergedDeck")
        || !doc.HasMember("initInfo")
        || !doc.HasMember("commandInfo") || !doc["commandInfo"].HasMember("commandList")
        || !doc["commandInfo"].HasMember("clicksPerTurn")
        || !doc.HasMember("playerInfo"))
    {
        printf("{\"ok\":false,\"error\":\"Missing required replay sections\"}\n");
        fflush(stdout);
        return;
    }

    // 4. Extract player names, ratings, winner, code
    const auto & playerInfo = doc["playerInfo"];
    std::string p0Name = "Player 1";
    std::string p1Name = "Player 2";
    int p0Rating = 0, p1Rating = 0;

    if (playerInfo.IsArray() && playerInfo.Size() >= 2)
    {
        if (playerInfo[0].HasMember("name"))
            p0Name = playerInfo[0]["name"].GetString();
        if (playerInfo[1].HasMember("name"))
            p1Name = playerInfo[1]["name"].GetString();
    }
    if (doc.HasMember("ratingInfo") && doc["ratingInfo"].HasMember("finalRatings"))
    {
        const auto & ratings = doc["ratingInfo"]["finalRatings"];
        if (ratings.IsArray() && ratings.Size() >= 2)
        {
            if (ratings[0].HasMember("displayRating"))
                p0Rating = (int)ratings[0]["displayRating"].GetDouble();
            if (ratings[1].HasMember("displayRating"))
                p1Rating = (int)ratings[1]["displayRating"].GetDouble();
        }
    }

    int winner = -1;
    if (doc.HasMember("result"))
        winner = doc["result"].GetInt();

    std::string code = replayFile;
    size_t lastSlash = code.find_last_of("/\\");
    if (lastSlash != std::string::npos) code = code.substr(lastSlash + 1);
    size_t dotPos = code.rfind(".json");
    if (dotPos != std::string::npos) code = code.substr(0, dotPos);

    // 5. Redirect stdout → stderr for noisy init/stepping
    const auto & mergedDeck = doc["deckInfo"]["mergedDeck"];
    const auto & initInfo = doc["initInfo"];
    const auto & commandList = doc["commandInfo"]["commandList"];
    const auto & clicksPerTurn = doc["commandInfo"]["clicksPerTurn"];

    fflush(stdout);
    int savedFd = _dup(_fileno(stdout));
    _dup2(_fileno(stderr), _fileno(stdout));

    ReplayStepper stepper;
    bool initOk = stepper.init(mergedDeck, initInfo, commandList, clicksPerTurn, playerInfo);

    if (!initOk)
    {
        fflush(stdout);
        _dup2(savedFd, _fileno(stdout));
        _close(savedFd);
        printf("{\"ok\":false,\"error\":\"ReplayStepper init failed\"}\n");
        fflush(stdout);
        return;
    }

    // 6. Create AI player
    PlayerPtr player;
    try
    {
        player = AIParameters::Instance().getPlayer(Players::Player_One, playerName);
    }
    catch (std::exception & e)
    {
        fflush(stdout);
        _dup2(savedFd, _fileno(stdout));
        _close(savedFd);
        printf("{\"ok\":false,\"error\":\"Cannot create player '%s': %s\"}\n",
               jsonEscape(playerName).c_str(), jsonEscape(std::string(e.what())).c_str());
        fflush(stdout);
        return;
    }

    // Override think time
    if (thinkTimeMs > 0)
    {
        auto * sabPlayer = dynamic_cast<Player_StackAlphaBeta *>(player.get());
        auto * uctPlayer = dynamic_cast<Player_UCT *>(player.get());
        if (sabPlayer)
            sabPlayer->getParams().setTimeLimit(thinkTimeMs);
        else if (uctPlayer)
            uctPlayer->getParams().setTimeLimit(thinkTimeMs);
    }

    // 7. Step through turns: eval + AI search + human move extraction
    struct TurnAnalysis
    {
        int turn;
        int player;
        float eval;             // neural eval (P1 perspective)
        std::vector<std::string> humanBuys;     // from click parsing (may overcount)
        std::vector<std::string> validatedBuys; // from engine-validated actions
        std::vector<std::string> aiBuys;
        std::vector<std::string> aiAbilities;
        std::vector<std::string> aiDefense;
        std::vector<std::string> aiBreach;
        std::string aiFullMove;
        bool buyAgreement;
        double searchMs;
    };
    std::vector<TurnAnalysis> turns;
    int fatalErrorCount = 0;
    const int maxFatalErrors = 5;

    while (stepper.hasNextTurn())
    {
        const GameState & state = stepper.getState();

        TurnAnalysis ta;
        ta.turn = stepper.getCurrentTurn();
        ta.player = (int)stepper.getActivePlayer();

        // Neural eval
        auto output = NeuralNet::Instance().evaluate(state);
        ta.eval = (state.getActivePlayer() == Players::Player_One)
            ? output.value : -output.value;

        // AI search — create player for correct side
        PlayerPtr turnPlayer;
        try
        {
            turnPlayer = AIParameters::Instance().getPlayer(state.getActivePlayer(), playerName);
            if (thinkTimeMs > 0)
            {
                auto * sab = dynamic_cast<Player_StackAlphaBeta *>(turnPlayer.get());
                auto * uct = dynamic_cast<Player_UCT *>(turnPlayer.get());
                if (sab) sab->getParams().setTimeLimit(thinkTimeMs);
                else if (uct) uct->getParams().setTimeLimit(thinkTimeMs);
            }
        }
        catch (...)
        {
            turnPlayer = player;  // fallback
        }

        Timer searchTimer;
        searchTimer.start();
        Move aiMove;
        try
        {
            turnPlayer->getMove(state, aiMove);
        }
        catch (std::exception &)
        {
            // AI search failed — leave aiMove empty
        }
        ta.searchMs = searchTimer.getElapsedTimeInMilliSec();

        // Categorize AI move
        categorizeMove(aiMove, state, ta.aiBuys, ta.aiAbilities, ta.aiDefense, ta.aiBreach);
        ta.aiFullMove = aiMove.toString();

        // Extract human buys from click data (naive, may overcount from stimming)
        int clickStart = stepper.getClickIndex();
        int clickCount = stepper.getTurnClickCount();
        ta.humanBuys = extractHumanBuys(commandList, clickStart, clickCount, mergedDeck);

        // Advance turn — this populates stepper's ground-truth buy tracking
        ReplayStepper::StepResult result = stepper.advanceTurn();

        // Engine-validated buys (only purchases the engine confirmed as legal)
        ta.validatedBuys = stepper.getTurnBuys();
        std::sort(ta.validatedBuys.begin(), ta.validatedBuys.end());

        // Compare human buys vs AI buys (sorted set equality)
        ta.buyAgreement = (ta.humanBuys == ta.aiBuys);

        turns.push_back(ta);

        if (result == ReplayStepper::StepResult::FatalError)
        {
            fatalErrorCount++;
            if (fatalErrorCount >= maxFatalErrors)
                break;
            continue;
        }
        if (result == ReplayStepper::StepResult::GameOver)
            break;
    }

    // Restore stdout
    fflush(stdout);
    _dup2(savedFd, _fileno(stdout));
    _close(savedFd);

    // 8. Compute statistics
    int agreements = 0;
    double totalSearchMs = 0.0;
    for (const auto & t : turns)
    {
        if (t.buyAgreement) agreements++;
        totalSearchMs += t.searchMs;
    }
    float agreementRate = turns.empty() ? 0.0f : (float)agreements / (float)turns.size();

    float maxSwing = 0.0f;
    int biggestMistakeTurn = -1;
    float biggestMistakeDrop = 0.0f;
    for (size_t i = 1; i < turns.size(); i++)
    {
        float delta = turns[i].eval - turns[i - 1].eval;
        float absDelta = std::abs(delta);
        if (absDelta > maxSwing) maxSwing = absDelta;

        float mistake = (turns[i - 1].player == 0) ? -delta : delta;
        if (mistake > biggestMistakeDrop)
        {
            biggestMistakeDrop = mistake;
            biggestMistakeTurn = turns[i - 1].turn;
        }
    }

    // 9. Output JSON
    printf("{\"ok\":true");
    printf(",\"code\":\"%s\"", jsonEscape(code).c_str());
    printf(",\"players\":[\"%s\",\"%s\"]", jsonEscape(p0Name).c_str(), jsonEscape(p1Name).c_str());
    printf(",\"ratings\":[%d,%d]", p0Rating, p1Rating);
    printf(",\"winner\":%d", winner);
    printf(",\"ai_player\":\"%s\"", jsonEscape(playerName).c_str());
    printf(",\"think_time_ms\":%d", thinkTimeMs);
    printf(",\"turns_analyzed\":%zu", turns.size());
    printf(",\"fatal_errors\":%d", fatalErrorCount);
    printf(",\"stepper_benign_skips\":%d", stepper.getBenignSkips());
    printf(",\"stepper_applied_clicks\":%d", stepper.getAppliedClicks());
    printf(",\"stepper_total_clicks\":%d", stepper.getTotalClicks());
    printf(",\"agreement_rate\":%.4f", agreementRate);
    printf(",\"agreements\":%d", agreements);
    printf(",\"total_search_ms\":%.0f", totalSearchMs);

    // Per-turn data
    printf(",\"turns\":[");
    for (size_t i = 0; i < turns.size(); i++)
    {
        if (i > 0) printf(",");
        float pct = (turns[i].eval + 1.0f) / 2.0f * 100.0f;
        printf("{\"turn\":%d,\"player\":%d,\"eval\":%.4f,\"eval_pct\":\"%.0f%%\"",
               turns[i].turn, turns[i].player, turns[i].eval, pct);
        printf(",\"human_buy\":%s", jsonStringArray(turns[i].humanBuys).c_str());
        printf(",\"validated_buy\":%s", jsonStringArray(turns[i].validatedBuys).c_str());
        printf(",\"ai_buy\":%s", jsonStringArray(turns[i].aiBuys).c_str());
        printf(",\"ai_abilities\":%s", jsonStringArray(turns[i].aiAbilities).c_str());
        printf(",\"ai_defense\":%s", jsonStringArray(turns[i].aiDefense).c_str());
        printf(",\"ai_breach\":%s", jsonStringArray(turns[i].aiBreach).c_str());
        printf(",\"buy_agree\":%s", turns[i].buyAgreement ? "true" : "false");
        printf(",\"search_ms\":%.0f", turns[i].searchMs);
        printf(",\"ai_move\":\"%s\"", jsonEscape(turns[i].aiFullMove).c_str());
        printf("}");
    }
    printf("]");

    // Summary stats
    printf(",\"eval_swing\":%.4f", maxSwing);
    if (biggestMistakeTurn >= 0)
    {
        printf(",\"biggest_mistake\":{\"turn\":%d,\"eval_drop\":%.4f}",
               biggestMistakeTurn, biggestMistakeDrop);
    }

    printf("}\n");
    fflush(stdout);
}

void Benchmarks::DoDumpStates(const std::string & replayFile, const std::string & outputFile)
{
    // 1. Read and parse replay JSON
    std::ifstream ifs(replayFile);
    if (!ifs.is_open())
    {
        fprintf(stderr, "[DumpStates] Cannot open replay: %s\n", replayFile.c_str());
        return;
    }
    std::string raw((std::istreambuf_iterator<char>(ifs)), std::istreambuf_iterator<char>());
    ifs.close();

    rapidjson::Document doc;
    if (doc.Parse(raw.c_str()).HasParseError())
    {
        fprintf(stderr, "[DumpStates] JSON parse error in %s\n", replayFile.c_str());
        return;
    }

    // 2. Validate required sections
    if (!doc.HasMember("deckInfo") || !doc["deckInfo"].HasMember("mergedDeck")
        || !doc.HasMember("initInfo")
        || !doc.HasMember("commandInfo") || !doc["commandInfo"].HasMember("commandList")
        || !doc["commandInfo"].HasMember("clicksPerTurn")
        || !doc.HasMember("playerInfo"))
    {
        fprintf(stderr, "[DumpStates] Missing required replay sections\n");
        return;
    }

    // 3. Extract replay components
    const auto & mergedDeck = doc["deckInfo"]["mergedDeck"];
    const auto & initInfo = doc["initInfo"];
    const auto & commandList = doc["commandInfo"]["commandList"];
    const auto & clicksPerTurn = doc["commandInfo"]["clicksPerTurn"];
    const auto & playerInfo = doc["playerInfo"];

    // 4. Redirect stdout → stderr during stepper init (suppresses PRISMATA_ASSERT noise)
    fflush(stdout);
    int savedFd = _dup(_fileno(stdout));
    _dup2(_fileno(stderr), _fileno(stdout));

    ReplayStepper stepper;
    bool initOk = stepper.init(mergedDeck, initInfo, commandList, clicksPerTurn, playerInfo);

    // Restore stdout
    fflush(stdout);
    _dup2(savedFd, _fileno(stdout));
    _close(savedFd);

    if (!initOk)
    {
        fprintf(stderr, "[DumpStates] ReplayStepper init failed for %s\n", replayFile.c_str());
        return;
    }

    // 5. Open output file
    FILE * out = fopen(outputFile.c_str(), "w");
    if (!out)
    {
        fprintf(stderr, "[DumpStates] Cannot open output: %s\n", outputFile.c_str());
        return;
    }

    // Helper lambda: strip newlines from toJSONString() output so each JSONL line is a single line
    auto singleLineState = [](const GameState & s) -> std::string
    {
        std::string json = s.toJSONString();
        json.erase(std::remove(json.begin(), json.end(), '\n'), json.end());
        json.erase(std::remove(json.begin(), json.end(), '\r'), json.end());
        return json;
    };

    // 6. Dump initial state (before any turns)
    {
        const GameState & state = stepper.getState();
        fprintf(out, "{\"turn\":-1,\"label\":\"initial\",\"player\":%d,\"hash\":\"%016llx\",\"state\":%s}\n",
            (int)state.getActivePlayer(), (unsigned long long)state.debugStateHash(), singleLineState(state).c_str());
    }

    // 7. Step through turns, dumping state at each boundary
    int turnCount = 0;

    // Redirect stdout → stderr during stepping (suppresses PRISMATA_ASSERT noise)
    fflush(stdout);
    savedFd = _dup(_fileno(stdout));
    _dup2(_fileno(stderr), _fileno(stdout));

    while (stepper.hasNextTurn())
    {
        ReplayStepper::StepResult result = stepper.advanceTurn();
        const GameState & state = stepper.getState();
        int turn = stepper.getCurrentTurn();
        int player = (int)state.getActivePlayer();

        fprintf(out, "{\"turn\":%d,\"player\":%d,\"hash\":\"%016llx\",\"state\":%s}\n",
            turn, player, (unsigned long long)state.debugStateHash(), singleLineState(state).c_str());

        turnCount++;

        if (result == ReplayStepper::StepResult::FatalError ||
            result == ReplayStepper::StepResult::GameOver)
            break;
    }

    // Restore stdout
    fflush(stdout);
    _dup2(savedFd, _fileno(stdout));
    _close(savedFd);

    // 8. Write summary line
    const GameState & finalState = stepper.getState();
    fprintf(out, "{\"summary\":true,\"total_turns\":%d,\"final_hash\":\"%016llx\",\"game_over\":%s,\"benign_skips\":%d,\"fatal_errors\":%d}\n",
        turnCount, (unsigned long long)finalState.debugStateHash(),
        finalState.isGameOver() ? "true" : "false",
        stepper.getBenignSkips(), stepper.getFatalErrors());

    fclose(out);
    fprintf(stderr, "[DumpStates] Wrote %d turns to %s\n", turnCount, outputFile.c_str());
}
