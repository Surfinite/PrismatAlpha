'use strict';

/**
 * matchup_worker.js -- Worker thread for parallel game execution (Phase 7e).
 *
 * Each worker thread:
 *   1. Loads its own card library and MCDSAI workers (if needed)
 *   2. Receives game assignments via workerData
 *   3. Runs games sequentially within its slot
 *   4. Posts each game result back via parentPort
 *   5. Cleans up MCDSAI workers on exit
 *
 * Communication protocol:
 *   Parent -> Worker (workerData):
 *     { slotIndex, gameNums: [1,2,...], playerWhite, playerBlack, thinkTimeMs,
 *       mcdsaiDifficulty, saveReplaysDir, verbose }
 *
 *   Worker -> Parent (postMessage):
 *     { type: 'game_result', gameNum, gameLog }
 *     { type: 'slot_done', slotIndex, gamesCompleted }
 *     { type: 'error', slotIndex, message }
 */

const { parentPort, workerData } = require('worker_threads');
const fs = require('fs');
const path = require('path');

// Redirect stderr to include slot prefix for clarity
const slotIndex = workerData.slotIndex;
const origStderrWrite = process.stderr.write.bind(process.stderr);
process.stderr.write = function(chunk, encoding, callback) {
    if (typeof chunk === 'string') {
        chunk = `[W${slotIndex}] ${chunk}`;
    }
    return origStderrWrite(chunk, encoding, callback);
};

// Load dependencies (each worker gets its own copies)
const C = require('./C');
const Analyzer = require('./Analyzer');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getSupply } = require('./card_library');

// Import shared functions from matchup_clean.js
// Note: We need the functions but NOT the module-level SUGGEST_TMP constant,
// since each worker uses its own temp file path.
const matchup = require('./matchup_clean');

const CONFIG_PATH = path.join(__dirname, 'matchup_config.json');
const CONFIG = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
const EXE_PATH = path.join(__dirname, '..', 'bin', CONFIG.exePath);

// Slot-specific temp file for --suggest state JSON
const SUGGEST_TMP = path.join(__dirname, `_suggest_state_W${slotIndex}.json`);

/**
 * Call C++ --suggest using this worker's slot-specific temp file.
 * Duplicates the logic from matchup_clean.callSuggest but with a
 * different temp file path to avoid conflicts between parallel workers.
 */
function callSuggestSlot(stateJson, playerName, thinkTimeMs) {
    const { execFileSync } = require('child_process');

    fs.writeFileSync(SUGGEST_TMP, JSON.stringify(stateJson));

    const timeout = thinkTimeMs * CONFIG.timeoutMultiplier;

    let stdout;
    try {
        stdout = execFileSync(EXE_PATH, [
            '--suggest', SUGGEST_TMP,
            '--player', playerName,
            '--think-time', String(thinkTimeMs)
        ], {
            timeout: timeout,
            encoding: 'utf-8',
            maxBuffer: 10 * 1024 * 1024,
            cwd: path.join(__dirname, '..', 'bin')
        });
    } catch (err) {
        if (err.killed) {
            return { ok: false, response: null, error: `Process timed out after ${timeout}ms` };
        }
        if (err.stdout) {
            stdout = err.stdout;
        } else {
            return { ok: false, response: null, error: `Process error: ${err.message}` };
        }
    }

    const cleanStdout = stdout.replace(/[\x00-\x09\x0b\x0c\x0e-\x1f]/g, ' ');
    const lines = cleanStdout.split('\n');
    const jsonLine = lines.find(l => l.trim().startsWith('{'));

    if (!jsonLine) {
        return {
            ok: false,
            response: null,
            error: `No JSON found in output. Raw output (first 500 chars): ${cleanStdout.substring(0, 500)}`
        };
    }

    let parsed;
    try {
        parsed = JSON.parse(jsonLine.trim());
    } catch (parseErr) {
        return {
            ok: false,
            response: null,
            error: `JSON parse error: ${parseErr.message}. Line: ${jsonLine.substring(0, 200)}`
        };
    }

    if (!parsed.ok) {
        return {
            ok: false,
            response: parsed,
            error: `C++ returned error: ${parsed.error || 'unknown'}`
        };
    }

    return { ok: true, response: parsed, error: null };
}

/**
 * Play a single turn using C++ --suggest with slot-specific temp file.
 * Mirrors matchup_clean.playSingleTurn but uses callSuggestSlot.
 */
function playSingleTurnSlot(analyzer, mergedDeck, playerName, thinkTimeMs) {
    const preTurn = analyzer.gameState.turn;
    const preNumTurns = analyzer.gameState.numTurns;
    const prePhase = analyzer.gameState.phase;

    console.error(`\n[Turn] Player ${preTurn} (${preTurn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns=${preNumTurns}, phase=${prePhase}`);

    const stateJson = matchup.exportStateForSuggest(analyzer, mergedDeck);
    console.error('[Turn] State exported for --suggest');

    console.error(`[Turn] Calling --suggest with player=${playerName}, thinkTime=${thinkTimeMs}ms...`);
    const suggestResult = callSuggestSlot(stateJson, playerName, thinkTimeMs);

    if (!suggestResult.ok) {
        console.error(`[Turn] --suggest FAILED: ${suggestResult.error}`);
        return { ok: false, suggest: suggestResult, clickResult: null, error: suggestResult.error };
    }

    const resp = suggestResult.response;
    console.error(`[Turn] --suggest OK: eval=${resp.eval_pct}, think=${resp.think_ms}ms`);
    console.error(`[Turn] Buys: [${(resp.buy || []).join(', ')}]`);
    console.error(`[Turn] Abilities: [${(resp.abilities || []).join(', ')}]`);
    console.error(`[Turn] Clicks: ${(resp.clicks || []).length} total`);

    const clicks = resp.clicks || [];
    if (clicks.length === 0) {
        console.error('[Turn] WARNING: 0 clicks returned');
        return { ok: true, suggest: suggestResult, clickResult: { applied: 0, failed: 0, details: [] }, error: null };
    }

    console.error('[Turn] Applying clicks to JS engine...');
    const clickResult = matchup.applyClicks(analyzer, clicks);

    console.error(`[Turn] Clicks: ${clickResult.applied} applied, ${clickResult.failed} failed`);
    if (clickResult.failed > 0) {
        for (const d of clickResult.details) {
            if (d.includes('FAIL')) console.error(d);
        }
    }

    const postTurn = analyzer.gameState.turn;
    const postNumTurns = analyzer.gameState.numTurns;
    const postPhase = analyzer.gameState.phase;
    const finished = analyzer.gameState.finished;

    console.error(`[Turn] After: player=${postTurn}, numTurns=${postNumTurns}, ` +
                  `phase=${postPhase}, finished=${finished}`);

    return { ok: true, suggest: suggestResult, clickResult, error: null };
}

/**
 * Play a complete game within a worker thread.
 * Mirrors playSingleGame from matchup_clean.js but uses slot-specific
 * temp files for C++ --suggest and worker-local MCDSAI workers.
 *
 * @param {Object[]} activeDeck - Active mergedDeck cards
 * @param {Object} config - Game configuration
 * @param {MCDSAIWorker|null} mcdsaiWorkerWhite - Worker-local MCDSAI for white
 * @param {MCDSAIWorker|null} mcdsaiWorkerBlack - Worker-local MCDSAI for black
 * @returns {Promise<Object>} Game result
 */
async function playSingleGameInWorker(activeDeck, config, mcdsaiWorkerWhite, mcdsaiWorkerBlack) {
    const playerWhite = config.playerWhite;
    const playerBlack = config.playerBlack;
    const thinkTimeMs = config.thinkTimeMs;
    const maxTurns = CONFIG.maxTurns || 200;
    const retryOnError = CONFIG.retryOnError || 1;
    const stuckThreshold = CONFIG.stuckDetectionTurns || 5;

    const whiteIsMCDSAI = matchup.isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = matchup.isMCDSAIPlayer(playerBlack);

    const errors = [];
    let abortReason = null;

    // Initialize game
    const gameInitInfo = matchup.buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const mcdsaiDifficulty = config.mcdsaiDifficulty || 'HardestAI';
    const whiteLabel = whiteIsMCDSAI ? `MCDSAI(${mcdsaiDifficulty})` : playerWhite;
    const blackLabel = blackIsMCDSAI ? `MCDSAI(${mcdsaiDifficulty})` : playerBlack;
    console.error('[Game] Initialized. White=' + whiteLabel + ', Black=' + blackLabel);

    // Initialize MCDSAI workers for this game (per-game init with deck)
    if ((whiteIsMCDSAI || blackIsMCDSAI) && config.mcdsaiFullParams) {
        const _sp = require('./ai_params').selectParams;
        const fullParams = config.mcdsaiFullParams;
        const shortParams = config.mcdsaiShortParams;
        const library = config.mcdsaiLibrary;

        const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
        const initParams = JSON.parse(_sp(mcdsaiDifficulty, 1, fullParams, shortParams));
        const initJson = JSON.stringify({
            mergedDeck: initDeck,
            aiParameters: initParams
        });

        if (whiteIsMCDSAI && mcdsaiWorkerWhite) {
            console.error('[Game] Initializing MCDSAI worker for White...');
            await mcdsaiWorkerWhite.initializeAI(initJson);
        }
        if (blackIsMCDSAI && mcdsaiWorkerBlack) {
            console.error('[Game] Initializing MCDSAI worker for Black...');
            await mcdsaiWorkerBlack.initializeAI(initJson);
        }
    }

    // Stuck detection state
    const recentHashes = [];
    let turnCount = 0;

    // Replay data collection (if saving replays)
    const replayTurns = [];

    // Main game loop
    while (!analyzer.gameState.finished && turnCount < maxTurns) {
        turnCount++;

        const activePlayer = analyzer.gameState.turn;
        const playerName = activePlayer === 0 ? playerWhite : playerBlack;
        const playerLabel = activePlayer === 0 ? 'White' : 'Black';
        const isActiveMCDSAI = matchup.isMCDSAIPlayer(playerName);

        console.error(`\n[Game] === Turn ${turnCount} (${playerLabel}, player=${playerName}${isActiveMCDSAI ? ' [MCDSAI]' : ''}) ===`);

        // Stuck detection: capture pre-turn state hash
        const preHash = matchup.getStateHash(analyzer);

        // Call appropriate turn function with retry logic
        let turnResult;
        if (isActiveMCDSAI) {
            const worker = activePlayer === 0 ? mcdsaiWorkerWhite : mcdsaiWorkerBlack;
            turnResult = await matchup.playMCDSAITurn(
                analyzer, activeDeck, worker, mcdsaiDifficulty
            );
        } else {
            // Use slot-specific suggest for C++ players
            turnResult = playSingleTurnSlot(analyzer, activeDeck, playerName, thinkTimeMs);
        }

        if (!turnResult.ok) {
            console.error(`[Game] Turn ${turnCount} failed: ${turnResult.error}`);
            console.error(`[Game] Retrying (attempt 2/${retryOnError + 1})...`);

            try {
                const stateDump = analyzer.gameState.toString();
                console.error(`[Game] State dump at failure:\n${stateDump.substring(0, 1000)}`);
            } catch (dumpErr) {
                console.error(`[Game] State dump failed: ${dumpErr.message}`);
            }

            // Retry
            if (isActiveMCDSAI) {
                const worker = activePlayer === 0 ? mcdsaiWorkerWhite : mcdsaiWorkerBlack;
                turnResult = await matchup.playMCDSAITurn(
                    analyzer, activeDeck, worker, mcdsaiDifficulty
                );
            } else {
                turnResult = playSingleTurnSlot(analyzer, activeDeck, playerName, thinkTimeMs);
            }

            if (!turnResult.ok) {
                const errMsg = turnResult.error || '';
                errors.push(`Turn ${turnCount} (${playerLabel}): ${errMsg}`);

                if (errMsg.includes('timed out')) {
                    abortReason = `Timeout on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else if (errMsg.includes('Process error')) {
                    abortReason = `Crash on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else {
                    abortReason = `Forfeit by ${playerLabel} on turn ${turnCount}: ${errMsg}`;
                    console.error(`[Game] FORFEIT: ${abortReason}`);
                    analyzer.gameState.result = activePlayer === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
                    break;
                }
            } else {
                errors.push(`Turn ${turnCount} (${playerLabel}): recovered after retry`);
            }
        }

        // Collect click data for replay (if suggest response available)
        if (turnResult.suggest && turnResult.suggest.response && turnResult.suggest.response.clicks) {
            replayTurns.push({
                turn: turnCount,
                player: playerLabel,
                playerName: playerName,
                clicks: turnResult.suggest.response.clicks,
                eval_pct: turnResult.suggest.response.eval_pct,
                buy: turnResult.suggest.response.buy,
                abilities: turnResult.suggest.response.abilities
            });
        } else if (turnResult.clickResult) {
            // MCDSAI turns don't have suggest response, log click summary
            replayTurns.push({
                turn: turnCount,
                player: playerLabel,
                playerName: playerName,
                clicksApplied: turnResult.clickResult.applied,
                clicksFailed: turnResult.clickResult.failed
            });
        }

        // Log click failures
        if (turnResult.clickResult && turnResult.clickResult.failed > 0) {
            errors.push(`Turn ${turnCount} (${playerLabel}): ${turnResult.clickResult.failed} click(s) failed`);
        }

        // Check for game over
        if (analyzer.gameState.finished) {
            console.error(`[Game] Game over detected after turn ${turnCount}`);
            break;
        }

        // Check stagnation
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            analyzer.gameState.result = C.COLOR_DRAW_STALEMATE;
            abortReason = `Stagnation draw detected at turn ${turnCount}`;
            console.error(`[Game] ${abortReason}`);
            break;
        }

        // Stuck detection
        const postHash = matchup.getStateHash(analyzer);
        recentHashes.push(postHash);
        if (recentHashes.length > stuckThreshold) recentHashes.shift();
        if (recentHashes.length >= stuckThreshold) {
            const allSame = recentHashes.every(h => h === recentHashes[0]);
            if (allSame) {
                abortReason = `Stuck: state unchanged for ${stuckThreshold} consecutive turns at turn ${turnCount}`;
                console.error(`[Game] ABORT: ${abortReason}`);
                analyzer.gameState.result = C.COLOR_DRAW_STALEMATE;
                break;
            }
        }
    }

    // Max turns reached
    if (!analyzer.gameState.finished && !abortReason && turnCount >= maxTurns) {
        abortReason = `Max turns reached (${maxTurns})`;
        console.error(`[Game] ABORT: ${abortReason}`);
        analyzer.gameState.result = C.COLOR_DRAW_STALEMATE;
    }

    const finalResult = analyzer.gameState.result;
    const winner = matchup.resultToString(finalResult);

    console.error(`\n[Game] RESULT: ${winner} in ${turnCount} turns`);

    // Clean up slot-specific temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    return {
        result: finalResult,
        winner: winner,
        turns: turnCount,
        errors: errors,
        abortReason: abortReason,
        replayTurns: replayTurns
    };
}

/**
 * Main worker loop: run assigned games sequentially and post results.
 */
async function runWorkerSlot() {
    const {
        gameNums,
        playerWhite,
        playerBlack,
        thinkTimeMs,
        mcdsaiDifficulty,
        saveReplaysDir,
        verbose
    } = workerData;

    const whiteIsMCDSAI = matchup.isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = matchup.isMCDSAIPlayer(playerBlack);
    const anyMCDSAI = whiteIsMCDSAI || blackIsMCDSAI;

    // Load card library (worker-local)
    const library = loadCardLibrary();

    // Load MCDSAI dependencies (worker-local, if needed)
    let mcdsaiWorkerWhite = null;
    let mcdsaiWorkerBlack = null;
    let fullParams = null;
    let shortParams = null;

    if (anyMCDSAI) {
        const MCDSAIWorker = require('./mcdsai_manager');
        const aiParams = require('./ai_params');
        fullParams = aiParams.loadFullParams();
        shortParams = aiParams.loadShortParams();

        if (whiteIsMCDSAI) {
            mcdsaiWorkerWhite = new MCDSAIWorker(`W${slotIndex}-White`);
            console.error('Spawning MCDSAI worker for White...');
            await mcdsaiWorkerWhite.spawn();
            console.error('MCDSAI worker for White ready.');
        }
        if (blackIsMCDSAI) {
            mcdsaiWorkerBlack = new MCDSAIWorker(`W${slotIndex}-Black`);
            console.error('Spawning MCDSAI worker for Black...');
            await mcdsaiWorkerBlack.spawn();
            console.error('MCDSAI worker for Black ready.');
        }
    }

    const maxRetries = 3;
    let gamesCompleted = 0;

    for (const gameNum of gameNums) {
        let gameLog = null;
        let attempts = 0;

        while (attempts < maxRetries) {
            attempts++;
            const startTime = Date.now();

            // Generate random card set
            const unitNames = randomSet(library, 8);
            console.error(`\n[Multi] Game ${gameNum} (attempt ${attempts}/${maxRetries})`);
            console.error(`[Multi] Card set: [${unitNames.join(', ')}]`);

            // Build mergedDeck
            const mergedDeck = buildMergedDeck(unitNames, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);

            // Verify supply
            const supplyResult = matchup.verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error(`[Multi] Game ${gameNum}: Supply verification FAILED -- logging and continuing`);
            }

            // Play the game
            let gameResult;
            let gameError = null;
            try {
                gameResult = await playSingleGameInWorker(activeDeck, {
                    playerWhite,
                    playerBlack,
                    thinkTimeMs,
                    mcdsaiDifficulty,
                    mcdsaiFullParams: fullParams,
                    mcdsaiShortParams: shortParams,
                    mcdsaiLibrary: library
                }, mcdsaiWorkerWhite, mcdsaiWorkerBlack);
            } catch (err) {
                gameError = err.message || String(err);
                console.error(`[Multi] Game ${gameNum}: Exception: ${gameError}`);
            }

            const endTime = Date.now();

            if (gameError) {
                if (attempts < maxRetries) {
                    console.error(`[Multi] Game ${gameNum}: Retrying with different card set...`);
                    continue;
                }
                gameLog = {
                    game: gameNum,
                    cardSet: unitNames,
                    winner: 'invalid',
                    result: null,
                    turns: 0,
                    errors: [gameError],
                    abortReason: `Exception after ${attempts} attempts: ${gameError}`,
                    startTime: new Date(startTime).toISOString(),
                    endTime: new Date(endTime).toISOString(),
                    durationMs: endTime - startTime,
                    supplyVerified: supplyResult.ok,
                    attempts: attempts,
                    replayTurns: []
                };
                break;
            }

            // 0-turn game = AI failure, retry
            if (gameResult.turns === 0 && attempts < maxRetries) {
                console.error(`[Multi] Game ${gameNum}: 0 turns -- AI failure, retrying...`);
                continue;
            }

            // Build per-game log
            gameLog = {
                game: gameNum,
                cardSet: unitNames,
                winner: gameResult.winner,
                result: gameResult.result,
                turns: gameResult.turns,
                errors: gameResult.errors,
                abortReason: gameResult.abortReason,
                startTime: new Date(startTime).toISOString(),
                endTime: new Date(endTime).toISOString(),
                durationMs: endTime - startTime,
                supplyVerified: supplyResult.ok,
                attempts: attempts,
                replayTurns: gameResult.replayTurns || []
            };
            break;
        }

        // If all retries failed
        if (!gameLog) {
            gameLog = {
                game: gameNum,
                cardSet: [],
                winner: 'invalid',
                result: null,
                turns: 0,
                errors: [`All ${maxRetries} attempts failed`],
                abortReason: `All ${maxRetries} attempts failed`,
                startTime: new Date().toISOString(),
                endTime: new Date().toISOString(),
                durationMs: 0,
                supplyVerified: false,
                attempts: maxRetries,
                replayTurns: []
            };
        }

        // Save replay file if requested
        if (saveReplaysDir && gameLog.replayTurns && gameLog.replayTurns.length > 0) {
            try {
                const replayData = {
                    game: gameLog.game,
                    cardSet: gameLog.cardSet,
                    playerWhite: playerWhite,
                    playerBlack: playerBlack,
                    thinkTimeMs: thinkTimeMs,
                    mcdsaiDifficulty: anyMCDSAI ? mcdsaiDifficulty : undefined,
                    result: gameLog.result,
                    winner: gameLog.winner,
                    turns: gameLog.turns,
                    replayTurns: gameLog.replayTurns,
                    timestamp: gameLog.startTime
                };
                const replayPath = path.join(saveReplaysDir, `game_${String(gameLog.game).padStart(4, '0')}.json`);
                fs.writeFileSync(replayPath, JSON.stringify(replayData, null, 2));
            } catch (err) {
                console.error(`[Multi] Game ${gameNum}: Failed to save replay: ${err.message}`);
            }
        }

        // Remove replayTurns from gameLog sent to parent (they can be large)
        const logForParent = Object.assign({}, gameLog);
        delete logForParent.replayTurns;

        // Post result to parent
        parentPort.postMessage({
            type: 'game_result',
            gameNum: gameNum,
            gameLog: logForParent
        });

        gamesCompleted++;

        const elapsed = (gameLog.durationMs / 1000).toFixed(1);
        console.error(`[Multi] Game ${gameNum} result: ${gameLog.winner} in ${gameLog.turns} turns (${elapsed}s)`);
    }

    // Clean up MCDSAI workers
    if (mcdsaiWorkerWhite) {
        console.error('Terminating MCDSAI worker for White...');
        mcdsaiWorkerWhite.terminate();
    }
    if (mcdsaiWorkerBlack) {
        console.error('Terminating MCDSAI worker for Black...');
        mcdsaiWorkerBlack.terminate();
    }

    // Clean up temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    // Signal completion
    parentPort.postMessage({
        type: 'slot_done',
        slotIndex: slotIndex,
        gamesCompleted: gamesCompleted
    });
}

// Run the worker slot
runWorkerSlot().catch(err => {
    console.error(`Worker slot ${slotIndex} fatal error: ${err.message}`);
    parentPort.postMessage({
        type: 'error',
        slotIndex: slotIndex,
        message: err.message
    });
    process.exit(1);
});
