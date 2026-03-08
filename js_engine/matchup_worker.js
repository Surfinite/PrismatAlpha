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
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getAdvancedUnitNames, getSupply } = require('./card_library');
const { stateToCppJSON, buildReplayJSON } = require('./replay_exporter');

// Import shared functions from matchup_clean.js
// Note: We need the functions but NOT the module-level SUGGEST_TMP constant,
// since each worker uses its own temp file path.
const matchup = require('./matchup_clean');

const CONFIG_PATH = path.join(__dirname, 'matchup_config.json');
const CONFIG = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
const EXE_PATH = path.join(__dirname, '..', 'bin', CONFIG.exePath);

// Slot-specific temp file for --suggest state JSON (includes parent PID
// so two concurrent --parallel N processes don't collide on the same slots)
const SUGGEST_TMP = path.join(__dirname, `_suggest_state_${process.pid}_W${slotIndex}.json`);

// Clean up temp file on exit
process.on('exit', () => { try { fs.unlinkSync(SUGGEST_TMP); } catch (_) {} });

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
    const actionStates = [];
    const clickResult = matchup.applyClicks(analyzer, clicks, actionStates);

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

    return { ok: true, suggest: suggestResult, clickResult, actionStates, error: null };
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
async function playSingleGameInWorker(activeDeck, config, mcdsaiWorkerWhite, mcdsaiWorkerBlack, steamConfig) {
    const playerWhite = config.playerWhite;
    const playerBlack = config.playerBlack;
    const thinkTimeMs = config.thinkTimeMs;
    const maxTurns = CONFIG.maxTurns || 200;
    const retryOnError = CONFIG.retryOnError || 1;
    const stuckThreshold = CONFIG.stuckDetectionTurns || 5;
    const resignRatio = config.resignThreshold || 0;  // 0 = disabled
    const MIN_RESIGN_TURN = 10;

    const whiteIsMCDSAI = matchup.isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = matchup.isMCDSAIPlayer(playerBlack);
    const whiteIsSteamAI = matchup.isSteamAIPlayer(playerWhite);
    const blackIsSteamAI = matchup.isSteamAIPlayer(playerBlack);

    const errors = [];
    let abortReason = null;

    // Initialize game
    const gameInitInfo = matchup.buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const mcdsaiDifficulty = config.mcdsaiDifficulty || 'HardestAI';
    const steamDifficulty = steamConfig ? steamConfig.difficulty : 'HardestAI';
    const whiteLabel = whiteIsMCDSAI ? `MCDSAI(${mcdsaiDifficulty})` :
                       whiteIsSteamAI ? `SteamAI(${steamDifficulty})` : playerWhite;
    const blackLabel = blackIsMCDSAI ? `MCDSAI(${mcdsaiDifficulty})` :
                       blackIsSteamAI ? `SteamAI(${steamDifficulty})` : playerBlack;
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

    // Build SteamAI initDeck for this game (one-shot exe spawns per turn)
    if ((whiteIsSteamAI || blackIsSteamAI) && steamConfig) {
        steamConfig.initDeck = buildInitDeck(activeDeck, steamConfig.library,
            steamConfig.fullParams, steamConfig.shortParams);
        console.error('[Game] SteamAI configured (processes spawn per turn)');
    }

    // Stuck detection state
    const recentHashes = [];
    let turnCount = 0;

    // Replay data collection (if saving replays)
    const replayTurns = [];
    const allActionStates = [];    // Per-action state snapshots (parallel to allActionLabels)
    const allActionLabels = [];    // Human-readable action labels
    const turnBoundaries = [];     // Indices into allActionStates where each turn starts

    // Main game loop
    while (!analyzer.gameState.finished && turnCount < maxTurns) {
        turnCount++;

        const activePlayer = analyzer.gameState.turn;
        const playerName = activePlayer === 0 ? playerWhite : playerBlack;
        const playerLabel = activePlayer === 0 ? 'White' : 'Black';
        const isActiveMCDSAI = matchup.isMCDSAIPlayer(playerName);
        const isActiveSteamAI = matchup.isSteamAIPlayer(playerName);

        console.error(`\n[Game] === Turn ${turnCount} (${playerLabel}, player=${playerName}${isActiveMCDSAI ? ' [MCDSAI]' : ''}${isActiveSteamAI ? ' [SteamAI]' : ''}) ===`);

        // Capture pre-turn state snapshot (turn boundary + "Start of Turn")
        try {
            turnBoundaries.push(allActionStates.length);
            allActionStates.push(stateToCppJSON(analyzer.gameState));
            allActionLabels.push('Start of Turn');
        } catch (e) { /* non-critical */ }

        // Stuck detection: capture pre-turn state hash
        const preHash = matchup.getStateHash(analyzer);

        // Call appropriate turn function with retry logic
        let turnResult;
        if (isActiveSteamAI && steamConfig) {
            const steamWorker = activePlayer === 0 ? steamConfig.workerWhite : steamConfig.workerBlack;
            turnResult = await matchup.playSteamAITurn(
                analyzer, activeDeck, steamWorker, steamDifficulty, steamConfig
            );
        } else if (isActiveMCDSAI) {
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
            if (isActiveSteamAI && steamConfig) {
                const steamWorker = activePlayer === 0 ? steamConfig.workerWhite : steamConfig.workerBlack;
                turnResult = await matchup.playSteamAITurn(
                    analyzer, activeDeck, steamWorker, steamDifficulty, steamConfig
                );
            } else if (isActiveMCDSAI) {
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

        // Collect per-action state snapshots from the turn result
        if (turnResult.actionStates && turnResult.actionStates.length > 0) {
            for (const entry of turnResult.actionStates) {
                allActionStates.push(entry.state);
                allActionLabels.push(entry.action);
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

        // WillScore resignation for non-MCDSAI players
        if (resignRatio > 0 && !isActiveMCDSAI && !isActiveSteamAI && turnCount >= MIN_RESIGN_TURN) {
            const selfScore = matchup.computeWillScoreSum(analyzer.gameState, activePlayer);
            const opponentPlayer = activePlayer === 0 ? 1 : 0;
            const oppScore = matchup.computeWillScoreSum(analyzer.gameState, opponentPlayer);

            let oppHasAttack = false;
            analyzer.gameState.table.forEach((inst) => {
                if (inst.owner !== opponentPlayer || inst.dead) return;
                if (inst.card.totalAttack > 0) oppHasAttack = true;
            });

            if (oppHasAttack && selfScore * resignRatio < oppScore) {
                console.error(`[Turn] ${playerName} resigns by WillScore (self=${selfScore.toFixed(1)}, opponent=${oppScore.toFixed(1)}, ratio=${(oppScore / Math.max(selfScore, 0.01)).toFixed(1)}x, threshold=${resignRatio}x)`);
                analyzer.gameState.result = activePlayer === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
                abortReason = `${playerLabel} resigned by WillScore at turn ${turnCount}`;
                break;
            }
        }

        // Check stagnation
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            const adj = matchup.adjudicateByMaterial(analyzer, 'Stagnation', turnCount);
            analyzer.gameState.result = adj.result;
            abortReason = adj.abortReason;
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
                const adj = matchup.adjudicateByMaterial(analyzer, 'Stuck', turnCount);
                analyzer.gameState.result = adj.result;
                abortReason = adj.abortReason;
                console.error(`[Game] ${abortReason}`);
                break;
            }
        }
    }

    // Max turns reached
    if (!analyzer.gameState.finished && !abortReason && turnCount >= maxTurns) {
        const adj = matchup.adjudicateByMaterial(analyzer, 'Max turns', turnCount);
        analyzer.gameState.result = adj.result;
        abortReason = adj.abortReason;
        console.error(`[Game] ${abortReason}`);
    }

    const finalResult = analyzer.gameState.result;
    const winner = matchup.resultToString(finalResult);

    console.error(`\n[Game] RESULT: ${winner} in ${turnCount} turns`);

    // Capture final post-game state
    try {
        allActionStates.push(stateToCppJSON(analyzer.gameState));
        allActionLabels.push('Game Over');
    } catch (e) { /* non-critical */ }

    // Clean up slot-specific temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    return {
        result: finalResult,
        winner: winner,
        turns: turnCount,
        errors: errors,
        abortReason: abortReason,
        replayTurns: replayTurns,
        allActionStates: allActionStates,
        allActionLabels: allActionLabels,
        turnBoundaries: turnBoundaries
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
        verbose,
        playerSwitch = false,
        fixedCards = null,
        resignThreshold = 0
    } = workerData;

    const whiteIsMCDSAI = matchup.isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = matchup.isMCDSAIPlayer(playerBlack);
    const anyMCDSAI = whiteIsMCDSAI || blackIsMCDSAI;
    const whiteIsSteamAI = matchup.isSteamAIPlayer(playerWhite);
    const blackIsSteamAI = matchup.isSteamAIPlayer(playerBlack);
    const anySteamAI = whiteIsSteamAI || blackIsSteamAI;

    // Load card library (worker-local)
    const library = loadCardLibrary();

    // Resolve "R" slots in fixedCards with random picks from the advanced unit pool
    function resolveRandomSlots(cards) {
        if (!cards || !cards.some(n => n === 'R')) return cards;
        const pinned = new Set(cards.filter(n => n !== 'R'));
        const available = getAdvancedUnitNames(library).filter(n => !pinned.has(n));
        for (let i = available.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [available[i], available[j]] = [available[j], available[i]];
        }
        let ri = 0;
        return cards.map(name => (name === 'R') ? available[ri++] : name);
    }

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

    // Set up SteamAI (worker-local, if needed)
    let steamConfig = null;
    if (anySteamAI) {
        const SteamAI = require('./steam_ai');
        // Load AI params if not already loaded by MCDSAI setup
        if (!fullParams || !shortParams) {
            const aiParams = require('./ai_params');
            fullParams = aiParams.loadFullParams();
            shortParams = aiParams.loadShortParams();
        }
        const steamDifficulty = workerData.steamDifficulty || 'HardestAI';
        steamConfig = {
            workerWhite: whiteIsSteamAI ? new SteamAI(`W${slotIndex}-White`, { timeout: Math.max(thinkTimeMs * 3, 30000) }) : null,
            workerBlack: blackIsSteamAI ? new SteamAI(`W${slotIndex}-Black`, { timeout: Math.max(thinkTimeMs * 3, 30000) }) : null,
            difficulty: steamDifficulty,
            fullParams: fullParams,
            shortParams: shortParams,
            initDeck: null,  // Set per-game
            library: library
        };
        console.error(`SteamAI configured for slot ${slotIndex} (difficulty=${steamDifficulty})`);
    }

    const maxRetries = 3;
    let gamesCompleted = 0;

    /**
     * Play a single game with retry logic. Returns gameLog.
     * @param {number} gameNum - 1-based game number
     * @param {string[]} unitNames - Card set to use
     * @param {string} pWhite - Player name for white
     * @param {string} pBlack - Player name for black
     * @param {Object|null} mWorkerWhite - MCDSAI worker for white (or null)
     * @param {Object|null} mWorkerBlack - MCDSAI worker for black (or null)
     */
    async function playOneGameInSlot(gameNum, unitNames, pWhite, pBlack, mWorkerWhite, mWorkerBlack, sCfg) {
        let gameLog = null;
        let attempts = 0;
        const label = playerSwitch ? '[Pair]' : '[Multi]';

        while (attempts < maxRetries) {
            attempts++;
            const startTime = Date.now();

            // On retry: new random set unless fully-fixed cards (R slots re-resolve)
            let currentUnits = unitNames;
            if (attempts > 1 && !fixedCards) {
                currentUnits = randomSet(library, 8);
            } else if (attempts > 1 && fixedCards && fixedCards.some(n => n === 'R')) {
                currentUnits = resolveRandomSlots(fixedCards);
            }
            console.error(`\n${label} Game ${gameNum} (attempt ${attempts}/${maxRetries})`);
            console.error(`${label} Card set: [${currentUnits.join(', ')}]`);

            const mergedDeck = buildMergedDeck(currentUnits, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);

            const supplyResult = matchup.verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error(`${label} Game ${gameNum}: Supply verification FAILED -- logging and continuing`);
            }

            let gameResult;
            let gameError = null;
            try {
                gameResult = await playSingleGameInWorker(activeDeck, {
                    playerWhite: pWhite,
                    playerBlack: pBlack,
                    thinkTimeMs,
                    mcdsaiDifficulty,
                    mcdsaiFullParams: fullParams,
                    mcdsaiShortParams: shortParams,
                    mcdsaiLibrary: library,
                    resignThreshold
                }, mWorkerWhite, mWorkerBlack, sCfg);
            } catch (err) {
                gameError = err.message || String(err);
                console.error(`${label} Game ${gameNum}: Exception: ${gameError}`);
            }

            const endTime = Date.now();

            if (gameError) {
                if (attempts < maxRetries) {
                    console.error(`${label} Game ${gameNum}: Retrying...`);
                    continue;
                }
                gameLog = {
                    game: gameNum, cardSet: currentUnits,
                    winner: 'invalid', result: null, turns: 0,
                    errors: [gameError],
                    abortReason: `Exception after ${attempts} attempts: ${gameError}`,
                    startTime: new Date(startTime).toISOString(),
                    endTime: new Date(endTime).toISOString(),
                    durationMs: endTime - startTime,
                    supplyVerified: supplyResult.ok, attempts: attempts,
                    replayTurns: []
                };
                break;
            }

            if (gameResult.turns === 0 && attempts < maxRetries) {
                console.error(`${label} Game ${gameNum}: 0 turns -- AI failure, retrying...`);
                continue;
            }

            gameLog = {
                game: gameNum, cardSet: currentUnits,
                winner: gameResult.winner, result: gameResult.result,
                turns: gameResult.turns, errors: gameResult.errors,
                abortReason: gameResult.abortReason,
                startTime: new Date(startTime).toISOString(),
                endTime: new Date(endTime).toISOString(),
                durationMs: endTime - startTime,
                supplyVerified: supplyResult.ok, attempts: attempts,
                replayTurns: gameResult.replayTurns || [],
                allActionStates: gameResult.allActionStates || [],
                allActionLabels: gameResult.allActionLabels || [],
                turnBoundaries: gameResult.turnBoundaries || []
            };
            break;
        }

        if (!gameLog) {
            gameLog = {
                game: gameNum, cardSet: [], winner: 'invalid', result: null,
                turns: 0, errors: [`All ${maxRetries} attempts failed`],
                abortReason: `All ${maxRetries} attempts failed`,
                startTime: new Date().toISOString(), endTime: new Date().toISOString(),
                durationMs: 0, supplyVerified: false, attempts: maxRetries,
                replayTurns: []
            };
        }
        return gameLog;
    }

    /**
     * Save replay, strip large data, post result to parent.
     */
    function finishGame(gameLog, pWhite, pBlack) {
        // Save replay file if requested
        const hasStates = gameLog && gameLog.allActionStates && gameLog.allActionStates.length > 0;
        if (saveReplaysDir && hasStates) {
            try {
                const winnerInt = gameLog.result === C.COLOR_WHITE ? 0 :
                                  gameLog.result === C.COLOR_BLACK ? 1 : -1;
                const replayData = buildReplayJSON(
                    gameLog.allActionStates, pWhite, pBlack,
                    winnerInt, gameLog.turns, gameLog.cardSet,
                    gameLog.allActionLabels, gameLog.turnBoundaries
                );
                const replayPath = path.join(saveReplaysDir, `game_${String(gameLog.game).padStart(4, '0')}.json`);
                fs.writeFileSync(replayPath, JSON.stringify(replayData, null, 2));
            } catch (err) {
                console.error(`[Multi] Game ${gameLog.game}: Failed to save replay: ${err.message}`);
            }
        }

        // Remove large replay data from log sent to parent
        const logForParent = Object.assign({}, gameLog);
        delete logForParent.replayTurns;
        delete logForParent.allActionStates;
        delete logForParent.allActionLabels;
        delete logForParent.turnBoundaries;

        parentPort.postMessage({
            type: 'game_result',
            gameNum: gameLog.game,
            gameLog: logForParent
        });

        gamesCompleted++;
        const elapsed = (gameLog.durationMs / 1000).toFixed(1);
        const label = playerSwitch ? '[Pair]' : '[Multi]';
        console.error(`${label} Game ${gameLog.game} result: ${gameLog.winner} in ${gameLog.turns} turns (${elapsed}s)`);
    }

    if (playerSwitch) {
        // --- Pair mode: process gameNums in steps of 2 ---
        for (let i = 0; i < gameNums.length; i += 2) {
            const gameNumA = gameNums[i];
            const gameNumB = gameNums[i + 1];
            const pairIdx = Math.floor(i / 2) + 1;
            const totalPairs = gameNums.length / 2;

            const unitNames = (fixedCards ? resolveRandomSlots(fixedCards) : null) || randomSet(library, 8);

            console.error(`\n[Pair] === Pair ${pairIdx}/${totalPairs} ===`);
            console.error(`[Pair] Card set: [${unitNames.join(', ')}]`);

            // Game A: original assignment
            const logA = await playOneGameInSlot(
                gameNumA, unitNames,
                playerWhite, playerBlack,
                mcdsaiWorkerWhite, mcdsaiWorkerBlack, steamConfig
            );
            logA.pairId = pairIdx;
            logA.swapped = false;
            finishGame(logA, playerWhite, playerBlack);

            // Game B: swapped assignment
            const swappedSteam = steamConfig ? {
                ...steamConfig,
                workerWhite: steamConfig.workerBlack,
                workerBlack: steamConfig.workerWhite
            } : null;
            const logB = await playOneGameInSlot(
                gameNumB, unitNames,
                playerBlack, playerWhite,  // Swapped!
                mcdsaiWorkerBlack, mcdsaiWorkerWhite,  // Swapped!
                swappedSteam
            );
            logB.pairId = pairIdx;
            logB.swapped = true;
            finishGame(logB, playerBlack, playerWhite);
        }
    } else {
        // --- Standard mode ---
        for (const gameNum of gameNums) {
            const unitNames = (fixedCards ? resolveRandomSlots(fixedCards) : null) || randomSet(library, 8);
            const gameLog = await playOneGameInSlot(
                gameNum, unitNames,
                playerWhite, playerBlack,
                mcdsaiWorkerWhite, mcdsaiWorkerBlack, steamConfig
            );
            finishGame(gameLog, playerWhite, playerBlack);
        }
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
