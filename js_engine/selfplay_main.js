'use strict';

/**
 * selfplay_main.js — Self-play game loop using MCDSAI workers.
 *
 * Pairs the transpiled JS engine with Lunarch's MCDSAI3441.js to generate
 * ground-truth training data. Two isolated MCDSAI worker processes play
 * both sides, while our engine tracks state for position capture.
 *
 * Usage:
 *   node selfplay_main.js                        # Play 1 game, print summary
 *   node selfplay_main.js --games 10             # Play 10 games
 *   node selfplay_main.js --games 10 --jsonl out.jsonl  # Output training data
 *   node selfplay_main.js --difficulty HardestAI # AI difficulty (default: HardestAI)
 *
 * Output: JSONL training examples (one per turn) to stdout or file.
 */

const fs = require('fs');
const path = require('path');

const C = require('./C');
const State = require('./State');
const Analyzer = require('./Analyzer');
const StateUtil = require('./StateUtil');
const { adjudicateByMaterial } = require('./matchup_clean');
const MCDSAIWorker = require('./mcdsai_manager');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getSupply } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const { stateToTrainingExample } = require('./state_adapter');

const MAX_TURNS = 400; // Safety limit to prevent infinite games

/**
 * Build a gameInitInfo object from a mergedDeck (for Analyzer constructor).
 *
 * @param {Object[]} mergedDeck - Card definitions array
 * @returns {Object} gameInitInfo suitable for Analyzer constructor
 */
function buildGameInitInfo(mergedDeck) {
    // Standard Prismata init: both players start with default starting units
    // base = array of [cardName, supply] for base set cards
    // randomizer = array of [cardName, supply] for random set cards
    const base = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        // Needs-only cards get supply 0 — present for script references, not buyable
        const supply = card._needsOnly ? 0 : getSupply(card);
        if (card.baseSet) {
            base.push([card.name, supply]);
        } else {
            randomizer.push([card.name, supply]);
        }
    }

    const laneInfo = [{
        initResources: ['0', '0'],
        base: [base, base],           // Both players see the same base set
        randomizer: [randomizer, randomizer],
        initCards: [
            [[6, 'Drone'], [2, 'Engineer']],  // White's starting units
            [[7, 'Drone'], [2, 'Engineer']]   // Black's starting units (extra Drone)
        ]
    }];

    const scriptInfo = { whiteStarts: true };

    return {
        laneInfo:      laneInfo,
        mergedDeck:    mergedDeck,
        scriptInfo:    scriptInfo,
        objectiveInfo: null,
        commandInfo:   null
    };
}

/**
 * Play one complete self-play game.
 *
 * @param {MCDSAIWorker} workerWhite - MCDSAI worker for white (P1)
 * @param {MCDSAIWorker} workerBlack - MCDSAI worker for black (P2)
 * @param {Object[]} mergedDeck - Card definitions (full deck from buildMergedDeck)
 * @param {string} difficulty - AI difficulty name
 * @param {string} fullParams - Full AI parameters JSON string
 * @param {string} shortParams - Short AI parameters JSON string
 * @param {number} gameId - Unique game identifier
 * @param {Map} library - Card library for buildInitDeck
 * @returns {Promise<{ examples: Object[], result: number, turns: number, cardSet: string[] }>}
 */
async function playGame(workerWhite, workerBlack, mergedDeck, difficulty,
                         fullParams, shortParams, gameId, library) {
    // Active deck = base set + 8 random units (~19 cards)
    const activeDeck = mergedDeck.filter(c => !c._inactive);

    // Init deck = active cards + all cards referenced by AI params and card scripts.
    // MCDSAI's AI params reference ~91 cards by name (opening books, strategies).
    // Card scripts (create, needs, resonate) reference ~27 more. Missing names
    // cause CardType::getCardType() to assert and abort move computation.
    // Using the full 158-card deck breaks MCDSAI (0 AI players), so we use a
    // targeted ~100-card deck that includes only referenced cards.
    const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);

    // aiParameters must be a parsed JSON object, not a string —
    // selectParams returns a JSON string, so parse it before embedding.
    const initParams = JSON.parse(selectParams(difficulty, 1, fullParams, shortParams));
    const initJson = JSON.stringify({
        mergedDeck: initDeck,
        aiParameters: initParams
    });

    await workerWhite.initializeAI(initJson);
    await workerBlack.initializeAI(initJson);

    // Create game state via Analyzer (handles init flow)
    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const examples = [];
    let turnCount = 0;

    while (!analyzer.gameState.finished && turnCount < MAX_TURNS) {
        turnCount++;

        // Capture pre-move training example BEFORE clicks mutate the state.
        // analyzer.gameState is modified in-place by recordClick(), so we
        // serialize features from the current (pre-move) state now.
        const activePlayer = analyzer.gameState.turn;
        const example = stateToTrainingExample(analyzer.gameState, gameId, []);

        // Select AI worker and params based on turn
        const worker = activePlayer === C.COLOR_WHITE ? workerWhite : workerBlack;
        const playerName = activePlayer === C.COLOR_WHITE ? 'White' : 'Black';

        // Build game state JSON for MCDSAI (serialized from pre-move state)
        const stateStr = analyzer.gameState.toString();
        const stateObj = JSON.parse(stateStr);
        const moveJson = JSON.stringify({
            gameState: stateObj,
            aiPlayerName: difficulty
        });

        // Get AI move
        let response;
        try {
            const resultStr = await worker.getAIMove(moveJson);
            // MCDSAI result may contain control characters — strip before parsing
            const cleanResult = resultStr.replace(/[\x00-\x1f]/g, ' ');
            response = JSON.parse(cleanResult);
        } catch (err) {
            console.error(`Game ${gameId} turn ${turnCount} (${playerName}): AI error: ${err.message}`);
            break;
        }

        // Check for resignation
        if (response.airesign) {
            // Record as loss for active player
            analyzer.gameState.result = 1 - activePlayer;
            break;
        }

        // Convert MCDSAI clicks to engine clicks and apply
        const aiclicks = response.aiclicks || [];

        // 0 clicks with short think time = AI exception (missing card name etc.)
        // Break out to prevent infinite loop of empty turns.
        if (aiclicks.length === 0) {
            console.error(`Game ${gameId} turn ${turnCount} (${playerName}): 0 clicks (${response.aithinktime}ms think) — AI failure`);
            break;
        }

        try {
            // Apply each click through the analyzer
            // convertToClicks creates Click objects with _type, _id, _params
            const clicks = StateUtil.convertToClicks(aiclicks, analyzer.gameState, false);

            for (const click of clicks) {
                analyzer.recordClick(false, false, click._type, click._id, click._params);
            }
        } catch (err) {
            // If convertToClicks fails (missing inst, illegal click), apply directly
            for (let i = 0; i < aiclicks.length; i++) {
                const ac = aiclicks[i];
                try {
                    let clickType = ac.type;
                    let clickId = -1;

                    if (clickType === C.CLICK_CARD || clickType === C.CLICK_CARD_SHIFT) {
                        const card = analyzer.gameState.cardNameToCard(ac.args);
                        if (card) clickId = card.cardId;
                    } else if (clickType === C.CLICK_INST || clickType === C.CLICK_INST_SHIFT) {
                        clickId = StateUtil.findInstId(ac.args, analyzer);
                    }

                    analyzer.recordClick(false, false, clickType, clickId);
                } catch (clickErr) {
                    // Skip failed clicks
                }
            }
        }

        // Add pre-move example (captured before clicks were applied)
        examples.push(example);

        // Auto-claim stagnation draws. In the real game, the opponent must
        // actively claim a draw when oppCouldClaimDraw is true. In self-play,
        // we auto-claim to prevent infinite games (e.g., both AIs doing
        // nothing but passing for 400 turns).
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            const adj = adjudicateByMaterial(analyzer, 'Stagnation', turnCount);
            analyzer.gameState.result = adj.result;
            console.error(`Game ${gameId} turn ${turnCount}: ${adj.abortReason}`);
            break;
        }
    }

    // Set final result on all examples
    const finalResult = analyzer.gameState.result;
    for (const ex of examples) {
        ex.result = finalResult === C.COLOR_WHITE ? 0 :
                    finalResult === C.COLOR_BLACK ? 1 :
                    finalResult === C.COLOR_NONE ? null : 2;
    }

    // Extract card set names for reporting
    const cardSet = [];
    for (const card of activeDeck) {
        if (!card.baseSet && !card._needsOnly) {
            cardSet.push(card.UIName || card.name);
        }
    }

    return {
        examples,
        result: finalResult,
        turns: turnCount,
        cardSet
    };
}

/**
 * Run multiple self-play games.
 */
async function main() {
    const args = process.argv.slice(2);

    // Parse arguments
    let numGames = 1;
    let outputPath = null;
    let difficulty = 'HardestAI';
    let verbose = false;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--games' && args[i + 1]) {
            numGames = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--jsonl' && args[i + 1]) {
            outputPath = args[i + 1];
            i++;
        } else if (args[i] === '--difficulty' && args[i + 1]) {
            difficulty = args[i + 1];
            i++;
        } else if (args[i] === '--verbose') {
            verbose = true;
        }
    }

    console.error(`Self-play: ${numGames} games, difficulty=${difficulty}`);

    // Load card library and AI params
    const library = loadCardLibrary();
    const fullParams = loadFullParams();
    const shortParams = loadShortParams();

    // Open output file if specified
    let outStream = null;
    if (outputPath) {
        outStream = fs.createWriteStream(outputPath, { flags: 'w' });
    }

    // Spawn MCDSAI workers
    const workerWhite = new MCDSAIWorker('White');
    const workerBlack = new MCDSAIWorker('Black');

    console.error('Spawning MCDSAI workers...');
    await Promise.all([workerWhite.spawn(), workerBlack.spawn()]);
    console.error('Workers ready.');

    let totalExamples = 0;
    let whiteWins = 0, blackWins = 0, draws = 0, ongoing = 0;

    const MAX_RETRIES = 3; // Retry with different set if AI fails (~5% of sets)

    for (let g = 0; g < numGames; g++) {
        const gameId = g + 1;
        let gameResult = null;
        let attempts = 0;
        const startTime = Date.now();

        while (attempts < MAX_RETRIES) {
            attempts++;
            const unitNames = randomSet(library, 8);
            const mergedDeck = buildMergedDeck(unitNames, library);

            try {
                gameResult = await playGame(
                    workerWhite, workerBlack, mergedDeck, difficulty,
                    fullParams, shortParams, gameId, library
                );

                // Check if the game actually produced moves (not a 0-turn AI failure)
                if (gameResult.turns === 0 || gameResult.examples.length === 0) {
                    if (attempts < MAX_RETRIES) {
                        console.error(`Game ${gameId}: AI produced no moves, retrying with different set (attempt ${attempts}/${MAX_RETRIES})`);
                        gameResult = null;
                        continue;
                    }
                }
                break;
            } catch (err) {
                if (attempts < MAX_RETRIES) {
                    console.error(`Game ${gameId}: error (attempt ${attempts}/${MAX_RETRIES}): ${err.message}, retrying...`);
                    gameResult = null;
                } else {
                    console.error(`Game ${gameId}: Failed after ${MAX_RETRIES} attempts: ${err.message}`);
                }
            }
        }

        if (!gameResult || gameResult.examples.length === 0) {
            console.error(`Game ${gameId}: Skipped (no valid moves produced)`);
            ongoing++;
            continue;
        }

        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const resultStr = gameResult.result === C.COLOR_WHITE ? 'White' :
                          gameResult.result === C.COLOR_BLACK ? 'Black' :
                          gameResult.result === C.COLOR_NONE ? 'Ongoing' : 'Draw';

        if (verbose || numGames <= 10) {
            console.error(`Game ${gameId}: ${resultStr} in ${gameResult.turns} turns (${elapsed}s) [${gameResult.cardSet.join(', ')}]`);
        }

        // Track stats
        if (gameResult.result === C.COLOR_WHITE) whiteWins++;
        else if (gameResult.result === C.COLOR_BLACK) blackWins++;
        else if (gameResult.result === C.COLOR_NONE) ongoing++;
        else draws++;

        // Output training examples
        for (const example of gameResult.examples) {
            const line = JSON.stringify(example);
            if (outStream) {
                outStream.write(line + '\n');
            } else {
                process.stdout.write(line + '\n');
            }
        }
        totalExamples += gameResult.examples.length;

        // Progress report every 10 games
        if (numGames > 10 && (g + 1) % 10 === 0) {
            console.error(`Progress: ${g + 1}/${numGames} games, ${totalExamples} examples`);
        }
    }

    // Cleanup
    workerWhite.terminate();
    workerBlack.terminate();
    if (outStream) {
        await new Promise(resolve => outStream.end(resolve));
    }

    // Final report
    console.error('\n=== Self-Play Summary ===');
    console.error(`Games:    ${numGames}`);
    console.error(`Examples: ${totalExamples} (~${Math.round(totalExamples / numGames)} per game)`);
    console.error(`Results:  White=${whiteWins} Black=${blackWins} Draw=${draws} Ongoing=${ongoing}`);
    console.error(`WR(P1):   ${numGames > 0 ? (100 * whiteWins / numGames).toFixed(1) : 0}%`);
    console.error('=========================');
}

module.exports = {
    buildGameInitInfo,
    playGame
};

if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(1);
    });
}
