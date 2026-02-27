'use strict';

/**
 * matchup_main.js — Orchestrator for MCDSAI vs C++ AI matchups.
 *
 * Plays Lunarch's MCDSAI (Master Bot AI) against our C++ OriginalHardestAI,
 * using the JS engine as the game state arbiter (correct AS3 rules).
 * Measures relative win rates to establish a strength baseline.
 *
 * Architecture:
 *   matchup_main.js (this file)
 *       ├── MCDSAIWorker (child_process.fork → mcdsai_worker.js → MCDSAI3441.js)
 *       └── CppSuggestWorker (child_process.execFile → Prismata_Testing.exe --suggest)
 *           └── JS Engine (State.js + Analyzer) manages all game state
 *
 * Usage:
 *   node matchup_main.js                                  # 10 games, default settings
 *   node matchup_main.js --games 100 --think-time 7000   # 100-game benchmark
 *   node matchup_main.js --games 5 --think-time 1000 --verbose  # Quick smoke test
 *   node matchup_main.js --mcdsai-color W                 # MCDSAI always White
 *   node matchup_main.js --player LiveHardestAI           # Test different C++ player
 *   node matchup_main.js --jsonl data.jsonl               # Output training data
 */

const fs = require('fs');
const path = require('path');

const C = require('./C');
const Analyzer = require('./Analyzer');
const StateUtil = require('./StateUtil');
const MCDSAIWorker = require('./mcdsai_manager');
const CppSuggestWorker = require('./cpp_suggest_worker');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const { stateToTrainingExample } = require('./state_adapter');
const { suggestClicksToClicks } = require('./suggest_adapter');
const { stateToCppJSON, buildReplayJSON } = require('./replay_exporter');

const MAX_TURNS = 400;

/**
 * Build a gameInitInfo object from a mergedDeck (for Analyzer constructor).
 * Copied from selfplay_main.js — identical logic.
 *
 * @param {Object[]} mergedDeck - Card definitions array
 * @returns {Object} gameInitInfo suitable for Analyzer constructor
 */
function buildGameInitInfo(mergedDeck) {
    const base = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        const supply = card.supply !== undefined ? card.supply : 20;
        if (card.baseSet) {
            base.push([card.name, supply]);
        } else {
            randomizer.push([card.name, supply]);
        }
    }

    const laneInfo = [{
        initResources: ['0', '0'],
        base: [base, base],
        randomizer: [randomizer, randomizer],
        initCards: [
            [[6, 'Drone'], [2, 'Engineer']],
            [[7, 'Drone'], [2, 'Engineer']]
        ]
    }];

    return {
        laneInfo:      laneInfo,
        mergedDeck:    mergedDeck,
        scriptInfo:    { whiteStarts: true },
        objectiveInfo: null,
        commandInfo:   null
    };
}

/**
 * Override TimeLimit on all Player_StackAlphaBeta definitions in AI params.
 * Copied from selfplay_main.js.
 */
function patchThinkTime(paramsStr, timeLimit) {
    const params = JSON.parse(paramsStr);
    if (params.Players) {
        let count = 0;
        for (const key of Object.keys(params.Players)) {
            const player = params.Players[key];
            if (player && typeof player === 'object' && player.TimeLimit !== undefined) {
                player.TimeLimit = timeLimit;
                count++;
            }
        }
        console.error(`  Patched TimeLimit=${timeLimit}ms on ${count} player definitions`);
    }
    return JSON.stringify(params);
}

/**
 * Compute Wilson score 95% confidence interval.
 * @param {number} wins - Number of successes
 * @param {number} total - Total trials
 * @returns {[number, number]} [lower, upper] as percentages
 */
function wilsonCI(wins, total) {
    if (total === 0) return [0, 0];
    const z = 1.96; // 95% CI
    const p = wins / total;
    const denom = 1 + z * z / total;
    const center = p + z * z / (2 * total);
    const spread = z * Math.sqrt(p * (1 - p) / total + z * z / (4 * total * total));
    return [
        Math.max(0, (center - spread) / denom * 100),
        Math.min(100, (center + spread) / denom * 100)
    ];
}

/**
 * Play one complete matchup game.
 *
 * @param {MCDSAIWorker} mcdsaiWorker - MCDSAI worker
 * @param {CppSuggestWorker} cppWorker - C++ suggest worker
 * @param {number} mcdsaiColor - Which color MCDSAI plays (C.COLOR_WHITE or C.COLOR_BLACK)
 * @param {Object[]} mergedDeck - Full merged deck from buildMergedDeck
 * @param {string} difficulty - MCDSAI difficulty name
 * @param {string} fullParams - Full AI parameters JSON string
 * @param {string} shortParams - Short AI parameters JSON string
 * @param {number} gameId - Unique game identifier
 * @param {Map} library - Card library for buildInitDeck
 * @param {Object} options - { verbose, captureReplay, outputTraining }
 * @returns {Promise<Object>} Game result
 */
async function playGame(mcdsaiWorker, cppWorker, mcdsaiColor, mergedDeck,
                         difficulty, fullParams, shortParams, gameId, library, options) {
    const { verbose, captureReplay, outputTraining } = options;

    // Active deck = base set + 8 random units
    const activeDeck = mergedDeck.filter(c => !c._inactive);
    const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);

    // Initialize both players with same deck and params
    const initParams = JSON.parse(selectParams(difficulty, 1, fullParams, shortParams));
    const initJson = JSON.stringify({
        mergedDeck: initDeck,
        aiParameters: initParams
    });

    await mcdsaiWorker.initializeAI(initJson);
    await cppWorker.initializeAI(initJson);

    // Create game state via Analyzer
    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const examples = [];
    const replayStates = captureReplay ? [] : null;
    let turnCount = 0;
    let stuckCount = 0;
    let prevStateStr = null;

    // Track per-side think times
    let mcdsaiThinkTotal = 0, mcdsaiThinkCount = 0;
    let cppThinkTotal = 0, cppThinkCount = 0;

    while (!analyzer.gameState.finished && turnCount < MAX_TURNS) {
        turnCount++;

        const activePlayer = analyzer.gameState.turn;
        const isMcdsaiTurn = (activePlayer === mcdsaiColor);
        const sideName = isMcdsaiTurn ? 'MCDSAI' : 'C++';

        // Capture pre-move training example (deferred push — only after stuck check passes)
        let example = null;
        if (outputTraining) {
            example = stateToTrainingExample(analyzer.gameState, gameId, []);
        }

        // Capture full GameState snapshot for GUI replay
        if (replayStates) {
            replayStates.push(stateToCppJSON(analyzer.gameState));
        }

        let clicksApplied = false;

        if (isMcdsaiTurn) {
            // === MCDSAI path (from selfplay_main.js) ===
            const stateStr = analyzer.gameState.toString();
            const stateObj = JSON.parse(stateStr);
            const moveJson = JSON.stringify({
                gameState: stateObj,
                aiPlayerName: difficulty
            });

            let response;
            try {
                const resultStr = await mcdsaiWorker.getAIMove(moveJson);
                const cleanResult = resultStr.replace(/[\x00-\x1f]/g, ' ');
                response = JSON.parse(cleanResult);
            } catch (err) {
                console.error(`Game ${gameId} turn ${turnCount} (MCDSAI): AI error: ${err.message}`);
                break;
            }

            if (response.airesign) {
                analyzer.gameState.result = 1 - activePlayer;
                if (verbose) console.error(`  Turn ${turnCount}: MCDSAI resigned`);
                break;
            }

            const aiclicks = response.aiclicks || [];
            if (aiclicks.length === 0) {
                console.error(`Game ${gameId} turn ${turnCount} (MCDSAI): 0 clicks — AI failure`);
                break;
            }

            mcdsaiThinkTotal += (response.aithinktime || 0);
            mcdsaiThinkCount++;

            try {
                const clicks = StateUtil.convertToClicks(aiclicks, analyzer.gameState, false);
                for (const click of clicks) {
                    analyzer.recordClick(false, false, click._type, click._id, click._params);
                }
                clicksApplied = true;
            } catch (err) {
                // Fallback: apply clicks directly (from selfplay_main.js)
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
                clicksApplied = true;
            }

            if (verbose) {
                console.error(`  Turn ${turnCount} (MCDSAI): ${aiclicks.length} clicks, ${response.aithinktime || '?'}ms`);
            }

        } else {
            // === C++ --suggest path ===
            let response;
            try {
                response = await cppWorker.getAIMove(analyzer.gameState);
            } catch (err) {
                console.error(`Game ${gameId} turn ${turnCount} (C++): AI error: ${err.message}`);
                break;
            }

            if (!response.ok) {
                console.error(`Game ${gameId} turn ${turnCount} (C++): suggest failed — ${response.error || 'unknown'}`);
                break;
            }

            const suggestClicks = response.clicks || [];
            if (suggestClicks.length === 0) {
                console.error(`Game ${gameId} turn ${turnCount} (C++): 0 clicks — AI failure`);
                break;
            }

            cppThinkTotal += (response.think_ms || 0);
            cppThinkCount++;

            try {
                const clicks = suggestClicksToClicks(suggestClicks);
                for (const click of clicks) {
                    analyzer.recordClick(false, false, click._type, click._id, click._params);
                }
                clicksApplied = true;
            } catch (err) {
                console.error(`Game ${gameId} turn ${turnCount} (C++): click application error: ${err.message}`);
                break;
            }

            if (verbose) {
                const buys = response.buy || [];
                console.error(`  Turn ${turnCount} (C++): ${suggestClicks.length} clicks, ${response.think_ms || '?'}ms, buys=[${buys.join(', ')}]`);
            }
        }

        // Stuck detection (from selfplay_main.js)
        const curStateStr = analyzer.gameState.toString();
        if (prevStateStr !== null && curStateStr === prevStateStr) {
            stuckCount++;
            if (stuckCount >= 3) {
                console.error(`Game ${gameId} turn ${turnCount}: State unchanged for ${stuckCount} turns — stuck, aborting`);
                break;
            }
        } else {
            stuckCount = 0;
        }
        prevStateStr = curStateStr;

        // Push training example only if state changed (no duplicate stuck-state data)
        if (example && stuckCount === 0) {
            examples.push(example);
        }

        // Stagnation check (from selfplay_main.js)
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            analyzer.gameState.result = C.COLOR_DRAW_STALEMATE;
            console.error(`Game ${gameId} turn ${turnCount}: Stagnation draw detected`);
            break;
        }
    }

    // Capture final state for replay
    if (replayStates) {
        replayStates.push(stateToCppJSON(analyzer.gameState));
    }

    // Set final result on training examples
    const finalResult = analyzer.gameState.result;
    if (outputTraining) {
        for (const ex of examples) {
            ex.result = finalResult === C.COLOR_WHITE ? 0 :
                        finalResult === C.COLOR_BLACK ? 1 :
                        finalResult === C.COLOR_NONE ? null : 2;
        }
    }

    // Extract card set names
    const cardSet = [];
    for (const card of activeDeck) {
        if (!card.baseSet) {
            cardSet.push(card.UIName || card.name);
        }
    }

    return {
        examples,
        result: finalResult,
        turns: turnCount,
        cardSet,
        replayStates,
        mcdsaiColor,
        mcdsaiThinkAvg: mcdsaiThinkCount > 0 ? Math.round(mcdsaiThinkTotal / mcdsaiThinkCount) : 0,
        cppThinkAvg: cppThinkCount > 0 ? Math.round(cppThinkTotal / cppThinkCount) : 0
    };
}

/**
 * Main entry point.
 */
async function main() {
    const args = process.argv.slice(2);

    // Parse arguments
    let numGames = 10;
    let outputPath = null;
    let replayDir = null;
    let difficulty = 'HardestAI';
    let mcdsaiThinkTime = null;
    let cppThinkTime = 7000;
    let mcdsaiColorArg = null; // null = alternate
    let playerName = 'OriginalHardestAI';
    let exePath = null;
    let verbose = false;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--games' && args[i + 1]) {
            numGames = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--jsonl' && args[i + 1]) {
            outputPath = args[i + 1];
            i++;
        } else if (args[i] === '--replay-dir' && args[i + 1]) {
            replayDir = args[i + 1];
            i++;
        } else if (args[i] === '--difficulty' && args[i + 1]) {
            difficulty = args[i + 1];
            i++;
        } else if (args[i] === '--think-time' && args[i + 1]) {
            cppThinkTime = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--mcdsai-think-time' && args[i + 1]) {
            mcdsaiThinkTime = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--mcdsai-color' && args[i + 1]) {
            const c = args[i + 1].toUpperCase();
            if (c === 'W' || c === 'WHITE' || c === '0') mcdsaiColorArg = C.COLOR_WHITE;
            else if (c === 'B' || c === 'BLACK' || c === '1') mcdsaiColorArg = C.COLOR_BLACK;
            else console.error(`Warning: unknown color '${args[i + 1]}', defaulting to alternate`);
            i++;
        } else if (args[i] === '--player' && args[i + 1]) {
            playerName = args[i + 1];
            i++;
        } else if (args[i] === '--exe' && args[i + 1]) {
            exePath = args[i + 1];
            i++;
        } else if (args[i] === '--verbose') {
            verbose = true;
        }
    }

    // Create replay directory if needed
    if (replayDir) {
        fs.mkdirSync(replayDir, { recursive: true });
    }

    console.error(`=== MCDSAI vs ${playerName} Matchup ===`);
    console.error(`Games: ${numGames}, C++ think: ${cppThinkTime}ms, MCDSAI difficulty: ${difficulty}`);
    console.error(`MCDSAI color: ${mcdsaiColorArg === null ? 'alternating' : mcdsaiColorArg === C.COLOR_WHITE ? 'always White' : 'always Black'}`);

    // Load card library and AI params
    const library = loadCardLibrary();
    let fullParams = loadFullParams();
    let shortParams = loadShortParams();

    // Override MCDSAI think time if specified
    if (mcdsaiThinkTime) {
        fullParams = patchThinkTime(fullParams, mcdsaiThinkTime);
        shortParams = patchThinkTime(shortParams, mcdsaiThinkTime);
        console.error(`MCDSAI think time override: ${mcdsaiThinkTime}ms`);
    }

    // Open output file if specified
    let outStream = null;
    if (outputPath) {
        outStream = fs.createWriteStream(outputPath, { flags: 'w' });
    }

    // Spawn workers
    const mcdsaiWorker = new MCDSAIWorker('MCDSAI');
    const cppWorkerOpts = { playerName, thinkTime: cppThinkTime };
    if (exePath) cppWorkerOpts.exePath = exePath;
    const cppWorker = new CppSuggestWorker(cppWorkerOpts);

    console.error('Spawning workers...');
    await Promise.all([mcdsaiWorker.spawn(), cppWorker.spawn()]);
    console.error('Workers ready.\n');

    // Stats tracking
    let mcdsaiWins = 0, cppWins = 0, draws = 0, failures = 0;
    let totalExamples = 0;
    let totalMcdsaiThink = 0, totalCppThink = 0;
    let totalTurns = 0;
    const MAX_RETRIES = 3;

    for (let g = 0; g < numGames; g++) {
        const gameId = g + 1;
        const startTime = Date.now();

        // Determine MCDSAI color for this game
        const mcdsaiColor = mcdsaiColorArg !== null
            ? mcdsaiColorArg
            : (g % 2 === 0 ? C.COLOR_WHITE : C.COLOR_BLACK);

        const mcdsaiSide = mcdsaiColor === C.COLOR_WHITE ? 'White' : 'Black';
        const cppSide = mcdsaiColor === C.COLOR_WHITE ? 'Black' : 'White';

        let gameResult = null;
        let attempts = 0;

        while (attempts < MAX_RETRIES) {
            attempts++;
            const unitNames = randomSet(library, 8);
            const mergedDeck = buildMergedDeck(unitNames, library);

            try {
                gameResult = await playGame(
                    mcdsaiWorker, cppWorker, mcdsaiColor, mergedDeck,
                    difficulty, fullParams, shortParams, gameId, library,
                    {
                        verbose,
                        captureReplay: !!replayDir,
                        outputTraining: !!outputPath
                    }
                );

                // Check if game produced moves
                if (gameResult.turns === 0) {
                    if (attempts < MAX_RETRIES) {
                        console.error(`Game ${gameId}: No moves produced, retrying (${attempts}/${MAX_RETRIES})`);
                        gameResult = null;
                        continue;
                    }
                }
                break;
            } catch (err) {
                if (attempts < MAX_RETRIES) {
                    console.error(`Game ${gameId}: Error (${attempts}/${MAX_RETRIES}): ${err.message}, retrying...`);
                    gameResult = null;
                } else {
                    console.error(`Game ${gameId}: Failed after ${MAX_RETRIES} attempts: ${err.message}`);
                }
            }
        }

        if (!gameResult || gameResult.turns === 0) {
            console.error(`Game ${gameId}: Skipped (no valid game produced)`);
            failures++;
            continue;
        }

        // Don't count games with no decisive result
        if (gameResult.result === C.COLOR_NONE) {
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
            console.error(`Game ${gameId}: No result after ${gameResult.turns} turns (${elapsed}s) — discarded`);
            failures++;
            continue;
        }

        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

        // Determine winner relative to MCDSAI vs C++
        let mcdsaiWon, resultLabel;
        if (gameResult.result === C.COLOR_WHITE || gameResult.result === C.COLOR_BLACK) {
            mcdsaiWon = (gameResult.result === mcdsaiColor);
            resultLabel = mcdsaiWon ? 'MCDSAI' : playerName;
            if (mcdsaiWon) mcdsaiWins++;
            else cppWins++;
        } else {
            mcdsaiWon = null;
            resultLabel = 'Draw';
            draws++;
        }

        totalTurns += gameResult.turns;
        totalMcdsaiThink += gameResult.mcdsaiThinkAvg;
        totalCppThink += gameResult.cppThinkAvg;

        console.error(`Game ${gameId}: ${resultLabel} wins in ${gameResult.turns} turns (${elapsed}s) ` +
            `[MCDSAI=${mcdsaiSide}] [${gameResult.cardSet.join(', ')}]`);

        // Write replay
        if (replayDir && gameResult.replayStates && gameResult.replayStates.length > 0) {
            const winner = gameResult.result === C.COLOR_WHITE ? 0 :
                           gameResult.result === C.COLOR_BLACK ? 1 : -1;
            const p0Name = mcdsaiColor === C.COLOR_WHITE ? 'MCDSAI' : playerName;
            const p1Name = mcdsaiColor === C.COLOR_BLACK ? 'MCDSAI' : playerName;
            const replay = buildReplayJSON(
                gameResult.replayStates, p0Name, p1Name,
                winner, gameResult.turns, gameResult.cardSet
            );
            const replayPath = path.join(replayDir, `game_${String(gameId).padStart(4, '0')}.json`);
            fs.writeFileSync(replayPath, JSON.stringify(replay));
        }

        // Output training examples
        if (outStream && gameResult.examples.length > 0) {
            for (const example of gameResult.examples) {
                outStream.write(JSON.stringify(example) + '\n');
            }
            totalExamples += gameResult.examples.length;
        }

        // Progress report every 10 games
        if (numGames > 10 && (g + 1) % 10 === 0) {
            const completedGames = mcdsaiWins + cppWins + draws;
            const wr = completedGames > 0 ? (100 * mcdsaiWins / completedGames).toFixed(1) : '0.0';
            console.error(`Progress: ${g + 1}/${numGames} games, MCDSAI WR: ${wr}%`);
        }
    }

    // Cleanup
    mcdsaiWorker.terminate();
    cppWorker.terminate();
    if (outStream) {
        await new Promise(resolve => outStream.end(resolve));
    }

    // Final results
    const completedGames = mcdsaiWins + cppWins + draws;
    const mcdsaiWR = completedGames > 0 ? (100 * mcdsaiWins / completedGames).toFixed(1) : '0.0';
    const cppWR = completedGames > 0 ? (100 * cppWins / completedGames).toFixed(1) : '0.0';
    const drawPct = completedGames > 0 ? (100 * draws / completedGames).toFixed(1) : '0.0';
    const avgTurns = completedGames > 0 ? (totalTurns / completedGames).toFixed(1) : '0';
    const avgMcdsaiThink = completedGames > 0 ? Math.round(totalMcdsaiThink / completedGames) : 0;
    const avgCppThink = completedGames > 0 ? Math.round(totalCppThink / completedGames) : 0;
    const [ciLow, ciHigh] = wilsonCI(mcdsaiWins, completedGames);

    console.error(`\n=== MCDSAI vs ${playerName} ===`);
    console.error(`Games: ${completedGames} (${failures} failed/discarded)`);
    console.error(`MCDSAI wins: ${mcdsaiWins} (${mcdsaiWR}%)`);
    console.error(`${playerName} wins: ${cppWins} (${cppWR}%)`);
    console.error(`Draws: ${draws} (${drawPct}%)`);
    console.error(`Avg game length: ${avgTurns} turns`);
    console.error(`Avg MCDSAI think: ${avgMcdsaiThink}ms`);
    console.error(`Avg C++ think: ${avgCppThink}ms`);
    console.error(`Wilson 95% CI (MCDSAI WR): [${ciLow.toFixed(1)}%, ${ciHigh.toFixed(1)}%]`);
    if (outputPath) console.error(`Training examples: ${totalExamples}`);
    console.error('================================');
}

if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(1);
    });
}
