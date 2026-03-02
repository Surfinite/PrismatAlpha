'use strict';

/**
 * matchup_clean.js — Phase 7a/7b/7c/7d: Matchup runner (clean room rebuild)
 *
 * Orchestrates Prismata games between C++ AI players and/or MCDSAI by:
 *   1. Verifying supply at init (rarity-based, no card.supply field)
 *   2. Initializing a JS game via Analyzer
 *   3. Looping: export state -> call C++ --suggest or MCDSAI -> apply clicks -> check game over
 *   4. Handling errors: retry on malformed JSON, forfeit/abort on repeated failure
 *   5. Stuck detection: abort as draw if state unchanged for N consecutive turns
 *   6. Multi-game: random card sets, per-game supply verification, tally results
 *   7. MCDSAI support: spawn workers, init per game, mixed C++/MCDSAI matchups
 *
 * Usage:
 *   node matchup_clean.js                             # Base-set-only single game
 *   node matchup_clean.js --random                    # Random 8-unit set (single game)
 *   node matchup_clean.js --games 10                  # 10 games with random card sets
 *   node matchup_clean.js --games 50 --think-time 1000  # 50 fast games
 *   node matchup_clean.js --player LiveHardestAI      # Same AI for both sides
 *   node matchup_clean.js --player-white HardestAI --player-black LiveHardestAI
 *   node matchup_clean.js --think-time 5000           # Custom think time
 *   node matchup_clean.js --single-turn               # Phase 7a single-turn test mode
 *   node matchup_clean.js --player MCDSAI             # Both sides use MCDSAI
 *   node matchup_clean.js --player-white MCDSAI --player-black OriginalHardestAI  # Mixed
 *   node matchup_clean.js --player MCDSAI --mcdsai-difficulty HardestAI  # Custom difficulty
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const C = require('./C');
const Analyzer = require('./Analyzer');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getSupply, SUPPLY_BY_RARITY } = require('./card_library');

// MCDSAI player identifier (case-insensitive matching in CLI parsing)
const MCDSAI_PLAYER = 'MCDSAI';

// Load config
const CONFIG_PATH = path.join(__dirname, 'matchup_config.json');
const CONFIG = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));

// C++ exe path (Release build)
const EXE_PATH = path.join(__dirname, '..', 'bin', CONFIG.exePath);

// Temp file for --suggest state JSON
const SUGGEST_TMP = path.join(__dirname, '_suggest_state.json');

// ---------------------------------------------------------------------------
// 1. Supply verification
// ---------------------------------------------------------------------------

/**
 * Verify that every active card in the mergedDeck has correct supply
 * based on rarity. Uses getSupply() from card_library.js — NOT card.supply.
 *
 * Special case: Vivid Drone is normal rarity but supply=10 (custom).
 * getSupply() returns 20 for normal, so we accept both 10 and 20 for
 * Vivid Drone until that special case is baked into getSupply.
 *
 * @param {Object[]} mergedDeck
 * @returns {{ ok: boolean, mismatches: string[] }}
 */
function verifySupply(mergedDeck) {
    const mismatches = [];
    for (const card of mergedDeck) {
        if (card._inactive) continue;

        const supply = getSupply(card);
        const expectedByRarity = SUPPLY_BY_RARITY[card.rarity];

        if (expectedByRarity === undefined) {
            mismatches.push(`${card.name || card.UIName}: unknown rarity "${card.rarity}"`);
            continue;
        }

        if (supply !== expectedByRarity) {
            mismatches.push(
                `${card.name || card.UIName}: rarity=${card.rarity} expected=${expectedByRarity} got=${supply}`
            );
        }
    }

    if (mismatches.length > 0) {
        console.error('[Supply] MISMATCHES:');
        for (const m of mismatches) console.error('  ' + m);
    } else {
        console.error('[Supply] All active cards pass rarity-based supply check.');
    }

    return { ok: mismatches.length === 0, mismatches };
}

// ---------------------------------------------------------------------------
// 2. State export for --suggest
// ---------------------------------------------------------------------------

/**
 * Export the JS engine state to the JSON format that C++ DoSuggest expects.
 *
 * Uses State.toString() which serializes gameState with:
 *   cards, table, whiteMana, blackMana, whiteTotalSupply, blackTotalSupply,
 *   whiteSupplySpent, blackSupplySpent, numTurns, turn, phase
 *
 * Wraps it in the F6 format: { CurrentInfo: { mergedDeck, gameState } }
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - The original mergedDeck (active cards only)
 * @returns {Object} JSON object ready for --suggest
 */
function exportStateForSuggest(analyzer, mergedDeck) {
    // State.toString() returns a JSON string with the gameState fields
    const stateStr = analyzer.gameState.toString();
    const gameState = JSON.parse(stateStr);

    // Build the F6 CurrentInfo wrapper
    return {
        CurrentInfo: {
            mergedDeck: mergedDeck,
            gameState: gameState
        }
    };
}

// ---------------------------------------------------------------------------
// 3. Call C++ --suggest
// ---------------------------------------------------------------------------

/**
 * Write state JSON to temp file, spawn Prismata_Testing.exe --suggest,
 * and parse the JSON response.
 *
 * Handles:
 *   - PRISMATA_ASSERT noise before JSON (finds first line starting with '{')
 *   - Process timeout (thinkTime x timeoutMultiplier)
 *   - Non-zero exit codes
 *   - Malformed JSON
 *   - Control characters in output
 *
 * @param {Object} stateJson - The full state JSON (F6 format)
 * @param {string} playerName - AI player name (e.g., "OriginalHardestAI")
 * @param {number} thinkTimeMs - Think time in milliseconds
 * @returns {{ ok: boolean, response: Object|null, error: string|null }}
 */
function callSuggest(stateJson, playerName, thinkTimeMs) {
    // Write state to temp file
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
            maxBuffer: 10 * 1024 * 1024,  // 10 MB
            cwd: path.join(__dirname, '..', 'bin')  // working dir = bin/ (for config.txt, etc.)
        });
    } catch (err) {
        if (err.killed) {
            return { ok: false, response: null, error: `Process timed out after ${timeout}ms` };
        }
        // execFileSync throws on non-zero exit but may still have stdout
        if (err.stdout) {
            stdout = err.stdout;
        } else {
            return { ok: false, response: null, error: `Process error: ${err.message}` };
        }
    }

    // Strip control characters (MCDSAI/PRISMATA_ASSERT noise)
    const cleanStdout = stdout.replace(/[\x00-\x09\x0b\x0c\x0e-\x1f]/g, ' ');

    // Find the JSON line (first line starting with '{')
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

// ---------------------------------------------------------------------------
// 4. Apply clicks from --suggest response
// ---------------------------------------------------------------------------

/**
 * Apply a click array from the --suggest response to the JS analyzer.
 *
 * Click format from C++: {_type: "inst clicked", _id: 0}
 *                         {_type: "card clicked", _id: 0}
 *                         {_type: "space clicked", _id: -1}
 *                         {_type: "end swipe processed", _id: N}
 *
 * The C++ Move already contains individual per-unit actions (one USE_ABILITY
 * per card instance). DoSuggest emits one "inst clicked" per instance with
 * the client instId. No shift-click expansion is needed — the JS engine
 * handles individual clicks correctly.
 *
 * Click types from C++:
 *   "inst clicked"          — ability activation or breach target (per-instance)
 *   "inst clicked" x2       — SNIPE/CHILL (source then target)
 *   "inst clicked" + "end swipe processed" — defense blocker assignment
 *   "card clicked"          — buy (one per purchase)
 *   "space clicked"         — phase transition
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} clicks - Array of {_type, _id} objects
 * @returns {{ applied: number, failed: number, details: string[] }}
 */
function applyClicks(analyzer, clicks) {
    let applied = 0;
    let failed = 0;
    const details = [];

    for (let i = 0; i < clicks.length; i++) {
        const click = clicks[i];
        const clickType = click._type;
        const clickId = click._id !== undefined ? click._id : -1;

        const result = analyzer.recordClick(false, false, clickType, clickId);
        if (result.canClick) {
            applied++;
            details.push(`  [${i}] OK: ${clickType} id=${clickId}`);
        } else {
            failed++;
            details.push(`  [${i}] FAIL: ${clickType} id=${clickId}`);
        }
    }

    // C++ DoSuggest adds ONE "space clicked" at the end (action->confirm),
    // but Prismata requires TWO to fully end a turn (action->confirm->commit).
    // If we're in confirm phase after applying all clicks, auto-commit.
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) {
            applied++;
            details.push(`  [auto] OK: space clicked (confirm->commit)`);
        } else {
            details.push(`  [auto] FAIL: space clicked (confirm->commit)`);
        }
    }

    return { applied, failed, details };
}

// ---------------------------------------------------------------------------
// 5. Play a single turn
// ---------------------------------------------------------------------------

/**
 * Orchestrate one turn: export state, call --suggest, apply clicks.
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - Active mergedDeck for the game
 * @param {string} playerName - AI player name
 * @param {number} thinkTimeMs - Think time
 * @returns {{ ok: boolean, suggest: Object|null, clickResult: Object|null, error: string|null }}
 */
function playSingleTurn(analyzer, mergedDeck, playerName, thinkTimeMs) {
    // Record pre-turn state
    const preTurn = analyzer.gameState.turn;
    const preNumTurns = analyzer.gameState.numTurns;
    const prePhase = analyzer.gameState.phase;

    console.error(`\n[Turn] Player ${preTurn} (${preTurn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns=${preNumTurns}, phase=${prePhase}`);

    // Export state
    const stateJson = exportStateForSuggest(analyzer, mergedDeck);
    console.error('[Turn] State exported for --suggest');

    // Call C++ --suggest
    console.error(`[Turn] Calling --suggest with player=${playerName}, thinkTime=${thinkTimeMs}ms...`);
    const suggestResult = callSuggest(stateJson, playerName, thinkTimeMs);

    if (!suggestResult.ok) {
        console.error(`[Turn] --suggest FAILED: ${suggestResult.error}`);
        return { ok: false, suggest: suggestResult, clickResult: null, error: suggestResult.error };
    }

    const resp = suggestResult.response;
    console.error(`[Turn] --suggest OK: eval=${resp.eval_pct}, think=${resp.think_ms}ms`);
    console.error(`[Turn] Buys: [${(resp.buy || []).join(', ')}]`);
    console.error(`[Turn] Abilities: [${(resp.abilities || []).join(', ')}]`);
    console.error(`[Turn] Clicks: ${(resp.clicks || []).length} total`);

    // Apply clicks to JS engine
    const clicks = resp.clicks || [];
    if (clicks.length === 0) {
        console.error('[Turn] WARNING: 0 clicks returned');
        return { ok: true, suggest: suggestResult, clickResult: { applied: 0, failed: 0, details: [] }, error: null };
    }

    console.error('[Turn] Applying clicks to JS engine...');
    const clickResult = applyClicks(analyzer, clicks);

    console.error(`[Turn] Clicks: ${clickResult.applied} applied, ${clickResult.failed} failed`);
    if (clickResult.failed > 0) {
        for (const d of clickResult.details) {
            if (d.includes('FAIL')) console.error(d);
        }
    }

    // Post-turn state
    const postTurn = analyzer.gameState.turn;
    const postNumTurns = analyzer.gameState.numTurns;
    const postPhase = analyzer.gameState.phase;
    const finished = analyzer.gameState.finished;

    console.error(`[Turn] After: player=${postTurn}, numTurns=${postNumTurns}, ` +
                  `phase=${postPhase}, finished=${finished}`);

    return { ok: true, suggest: suggestResult, clickResult, error: null };
}

// ---------------------------------------------------------------------------
// 5b. Play a single MCDSAI turn (Phase 7d)
// ---------------------------------------------------------------------------

/**
 * Helper: check if a player name is MCDSAI (case-insensitive).
 * @param {string} playerName
 * @returns {boolean}
 */
function isMCDSAIPlayer(playerName) {
    return playerName.toUpperCase() === MCDSAI_PLAYER;
}

/**
 * Orchestrate one MCDSAI turn: get state, call MCDSAI worker, apply clicks.
 *
 * Follows the selfplay_main.js pattern for MCDSAI interaction:
 *   1. Serialize game state via analyzer.gameState.toString()
 *   2. Select AI params based on turn number
 *   3. Call worker.getAIMove() with {gameState, aiPlayerName}
 *   4. Strip control chars, parse JSON response
 *   5. Handle resignation and 0-click failures
 *   6. Convert clicks via StateUtil.convertToClicks()
 *   7. Apply clicks via analyzer.recordClick()
 *   8. Fall back to direct click application if convertToClicks throws
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - Active mergedDeck for the game (unused but kept for API symmetry)
 * @param {MCDSAIWorker} mcdsaiWorker - Spawned and initialized MCDSAI worker
 * @param {string} difficulty - MCDSAI difficulty name (e.g., "HardestAI")
 * @returns {Promise<{ ok: boolean, clickResult: Object|null, error: string|null }>}
 */
async function playMCDSAITurn(analyzer, mergedDeck, mcdsaiWorker, difficulty) {
    // Lazy-load StateUtil (only needed when MCDSAI is actually used)
    const StateUtil = require('./StateUtil');

    const preTurn = analyzer.gameState.turn;
    const preNumTurns = analyzer.gameState.numTurns;
    const prePhase = analyzer.gameState.phase;

    console.error(`\n[Turn] Player ${preTurn} (${preTurn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns=${preNumTurns}, phase=${prePhase} [MCDSAI]`);

    // 1. Serialize game state
    const stateStr = analyzer.gameState.toString();
    const stateObj = JSON.parse(stateStr);

    // 2. Build move request JSON
    const moveJson = JSON.stringify({
        gameState: stateObj,
        aiPlayerName: difficulty
    });

    // 3. Call MCDSAI worker
    console.error(`[Turn] Calling MCDSAI (difficulty=${difficulty})...`);
    let response;
    try {
        const resultStr = await mcdsaiWorker.getAIMove(moveJson);
        // CRITICAL: MCDSAI response contains control characters — strip before JSON.parse
        const cleanResult = resultStr.replace(/[\x00-\x1f]/g, ' ');
        response = JSON.parse(cleanResult);
    } catch (err) {
        console.error(`[Turn] MCDSAI error: ${err.message}`);
        return { ok: false, clickResult: null, error: `MCDSAI error: ${err.message}` };
    }

    // 4. Handle resignation
    if (response.airesign) {
        console.error(`[Turn] MCDSAI resigned`);
        // Record as loss for active player
        analyzer.gameState.result = preTurn === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
        return { ok: true, clickResult: { applied: 0, failed: 0, details: ['MCDSAI resigned'] }, error: null };
    }

    // 5. Handle 0 clicks (AI failure — missing card name, etc.)
    const aiclicks = response.aiclicks || [];
    if (aiclicks.length === 0) {
        const thinkTime = response.aithinktime || 'unknown';
        console.error(`[Turn] MCDSAI returned 0 clicks (${thinkTime}ms think) — AI failure`);
        return { ok: false, clickResult: { applied: 0, failed: 0, details: [] }, error: `MCDSAI 0 clicks (${thinkTime}ms think)` };
    }

    console.error(`[Turn] MCDSAI returned ${aiclicks.length} AI clicks (${response.aithinktime || '?'}ms think)`);

    // 6-8. Convert and apply clicks
    let applied = 0;
    let failed = 0;
    const details = [];

    try {
        // Primary path: use StateUtil.convertToClicks for validated click resolution
        const clicks = StateUtil.convertToClicks(aiclicks, analyzer.gameState, false);

        for (let i = 0; i < clicks.length; i++) {
            const click = clicks[i];
            const result = analyzer.recordClick(false, false, click._type, click._id, click._params);
            if (result.canClick) {
                applied++;
                details.push(`  [${i}] OK: ${click._type} id=${click._id}`);
            } else {
                failed++;
                details.push(`  [${i}] FAIL: ${click._type} id=${click._id}`);
            }
        }
    } catch (err) {
        // Fallback: if convertToClicks fails (missing inst, illegal click), apply directly
        console.error(`[Turn] convertToClicks failed (${err.message}), falling back to direct application`);
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

                const result = analyzer.recordClick(false, false, clickType, clickId);
                if (result.canClick) {
                    applied++;
                    details.push(`  [${i}] OK (fallback): ${clickType} id=${clickId}`);
                } else {
                    failed++;
                    details.push(`  [${i}] FAIL (fallback): ${clickType} id=${clickId}`);
                }
            } catch (clickErr) {
                failed++;
                details.push(`  [${i}] ERROR (fallback): ${ac.type} — ${clickErr.message}`);
            }
        }
    }

    // Auto-confirm: if we're in PHASE_CONFIRM after applying all MCDSAI clicks, auto-commit
    // (same pattern as applyClicks() does for C++ suggest)
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) {
            applied++;
            details.push(`  [auto] OK: space clicked (confirm->commit)`);
        } else {
            details.push(`  [auto] FAIL: space clicked (confirm->commit)`);
        }
    }

    console.error(`[Turn] MCDSAI clicks: ${applied} applied, ${failed} failed`);
    if (failed > 0) {
        for (const d of details) {
            if (d.includes('FAIL') || d.includes('ERROR')) console.error(d);
        }
    }

    // Post-turn state
    const postTurn = analyzer.gameState.turn;
    const postNumTurns = analyzer.gameState.numTurns;
    const postPhase = analyzer.gameState.phase;
    const finished = analyzer.gameState.finished;

    console.error(`[Turn] After: player=${postTurn}, numTurns=${postNumTurns}, ` +
                  `phase=${postPhase}, finished=${finished}`);

    return { ok: true, clickResult: { applied, failed, details }, error: null };
}

// ---------------------------------------------------------------------------
// 6. State summary printer
// ---------------------------------------------------------------------------

/**
 * Print a concise state summary showing unit counts and mana.
 */
function printStateSummary(analyzer, label) {
    const gs = analyzer.gameState;
    const stateStr = gs.toString();
    const state = JSON.parse(stateStr);

    console.error(`\n=== ${label} ===`);
    console.error(`Turn: ${state.turn} (${state.turn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns: ${state.numTurns}, phase: ${state.phase}`);
    console.error(`White mana: ${state.whiteMana}`);
    console.error(`Black mana: ${state.blackMana}`);

    // Count units per player
    const whiteCounts = {};
    const blackCounts = {};
    for (const inst of state.table) {
        if (inst.deadness !== 'alive') continue;
        const bucket = inst.owner === 0 ? whiteCounts : blackCounts;
        bucket[inst.cardName] = (bucket[inst.cardName] || 0) + 1;
    }

    const fmtCounts = (counts) => {
        const parts = [];
        for (const [name, count] of Object.entries(counts).sort()) {
            parts.push(`${name}x${count}`);
        }
        return parts.join(', ') || '(none)';
    };

    console.error(`White units: ${fmtCounts(whiteCounts)}`);
    console.error(`Black units: ${fmtCounts(blackCounts)}`);

    // Supply spent
    const spentWhite = [];
    const spentBlack = [];
    for (let i = 0; i < state.cards.length; i++) {
        if (state.whiteSupplySpent[i] > 0) spentWhite.push(`${state.cards[i]}:${state.whiteSupplySpent[i]}`);
        if (state.blackSupplySpent[i] > 0) spentBlack.push(`${state.cards[i]}:${state.blackSupplySpent[i]}`);
    }
    if (spentWhite.length > 0) console.error(`White bought: ${spentWhite.join(', ')}`);
    if (spentBlack.length > 0) console.error(`Black bought: ${spentBlack.join(', ')}`);
    console.error('');
}

// ---------------------------------------------------------------------------
// 7. Build game init info (from selfplay_main.js pattern)
// ---------------------------------------------------------------------------

/**
 * Build a gameInitInfo object from a mergedDeck for the Analyzer constructor.
 * Identical to the pattern in selfplay_main.js.
 *
 * @param {Object[]} mergedDeck - Active card definitions
 * @returns {Object} gameInitInfo suitable for Analyzer constructor
 */
function buildGameInitInfo(mergedDeck) {
    const base = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        // Use getSupply for rarity-based supply -- NOT card.supply
        const supply = getSupply(card);
        if (card.baseSet) {
            base.push([card.name, supply]);
        } else {
            randomizer.push([card.name, supply]);
        }
    }

    return {
        laneInfo: [{
            initResources: ['0', '0'],
            base: [base, base],
            randomizer: [randomizer, randomizer],
            initCards: [
                [[6, 'Drone'], [2, 'Engineer']],   // White starts
                [[7, 'Drone'], [2, 'Engineer']]    // Black starts (extra Drone)
            ]
        }],
        mergedDeck: mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: null
    };
}

// ---------------------------------------------------------------------------
// 8. Play a single complete game (Phase 7b)
// ---------------------------------------------------------------------------

/**
 * Compute a simple hash of the game state for stuck detection.
 * Uses the full state JSON string — any change in units, mana, supply,
 * phase, or turn will produce a different hash.
 *
 * @param {Object} analyzer
 * @returns {string} State hash (the full JSON string)
 */
function getStateHash(analyzer) {
    return analyzer.gameState.toString();
}

/**
 * Map state.result to a human-readable string.
 *
 * @param {number} result - state.result value (C.COLOR_WHITE, C.COLOR_BLACK, etc.)
 * @returns {string}
 */
function resultToString(result) {
    if (result === C.COLOR_WHITE) return 'White (P0)';
    if (result === C.COLOR_BLACK) return 'Black (P1)';
    if (result === C.COLOR_DRAW_MUTUAL_ELIMINATION) return 'Draw (mutual elimination)';
    if (result === C.COLOR_DRAW_STALEMATE) return 'Draw (stalemate)';
    if (result === C.COLOR_NONE) return 'Ongoing';
    return `Unknown (${result})`;
}

/**
 * Play a complete game from init to game-over (or abort).
 *
 * Alternates Player 0 (White) and Player 1 (Black) turns,
 * calling C++ --suggest or MCDSAI for each turn and applying clicks to the JS engine.
 *
 * Error handling:
 *   - Malformed JSON from --suggest: retry once (retryOnError), then forfeit
 *   - --suggest crash (non-zero exit): mark game invalid
 *   - --suggest timeout: mark game invalid
 *   - MCDSAI error: retry once, then forfeit
 *   - recordClick failure: log and continue (applyClicks handles this)
 *   - Stuck detection: if state hash unchanged for stuckDetectionTurns
 *     consecutive turns, abort as draw
 *
 * @param {Object[]} activeDeck - Active mergedDeck cards
 * @param {Object} config - Game configuration
 * @param {string} config.playerWhite - White player name or "MCDSAI"
 * @param {string} config.playerBlack - Black player name or "MCDSAI"
 * @param {number} config.thinkTimeMs - Think time for C++ players
 * @param {Object} [config.mcdsai] - MCDSAI configuration (required if any player is MCDSAI)
 * @param {MCDSAIWorker|null} [config.mcdsai.workerWhite] - MCDSAI worker for white
 * @param {MCDSAIWorker|null} [config.mcdsai.workerBlack] - MCDSAI worker for black
 * @param {string} [config.mcdsai.difficulty] - MCDSAI difficulty name (default: "HardestAI")
 * @param {string} [config.mcdsai.fullParams] - Full AI params string
 * @param {string} [config.mcdsai.shortParams] - Short AI params string
 * @param {Map} [config.mcdsai.library] - Card library for buildInitDeck
 * @returns {Promise<{ result: number, winner: string, turns: number, errors: string[], abortReason: string|null }>}
 */
async function playSingleGame(activeDeck, config) {
    const playerWhite = config.playerWhite;
    const playerBlack = config.playerBlack;
    const thinkTimeMs = config.thinkTimeMs;
    const maxTurns = CONFIG.maxTurns || 200;
    const retryOnError = CONFIG.retryOnError || 1;
    const stuckThreshold = CONFIG.stuckDetectionTurns || 5;

    // MCDSAI config (may be null if no MCDSAI players)
    const mcdsaiConfig = config.mcdsai || null;
    const whiteIsMCDSAI = isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = isMCDSAIPlayer(playerBlack);

    const errors = [];
    let abortReason = null;

    // Initialize game
    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const whiteLabel = whiteIsMCDSAI ? `MCDSAI(${mcdsaiConfig ? mcdsaiConfig.difficulty : '?'})` : playerWhite;
    const blackLabel = blackIsMCDSAI ? `MCDSAI(${mcdsaiConfig ? mcdsaiConfig.difficulty : '?'})` : playerBlack;
    console.error('[Game] Initialized. White=' + whiteLabel + ', Black=' + blackLabel);
    printStateSummary(analyzer, 'GAME START');

    // Initialize MCDSAI workers for this game (per-game init with deck)
    if ((whiteIsMCDSAI || blackIsMCDSAI) && mcdsaiConfig) {
        const _sp = require('./ai_params').selectParams;
        const fullParams = mcdsaiConfig.fullParams;
        const shortParams = mcdsaiConfig.shortParams;
        const difficulty = mcdsaiConfig.difficulty || 'HardestAI';
        const library = mcdsaiConfig.library;

        // Build init deck (includes AI param-referenced cards beyond the activeDeck)
        const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
        const initParams = JSON.parse(_sp(difficulty, 1, fullParams, shortParams));
        const initJson = JSON.stringify({
            mergedDeck: initDeck,
            aiParameters: initParams
        });

        if (whiteIsMCDSAI && mcdsaiConfig.workerWhite) {
            console.error('[Game] Initializing MCDSAI worker for White...');
            await mcdsaiConfig.workerWhite.initializeAI(initJson);
        }
        if (blackIsMCDSAI && mcdsaiConfig.workerBlack) {
            console.error('[Game] Initializing MCDSAI worker for Black...');
            await mcdsaiConfig.workerBlack.initializeAI(initJson);
        }
    }

    // Stuck detection state
    const recentHashes = [];  // circular buffer of last N state hashes
    let turnCount = 0;

    // Main game loop
    while (!analyzer.gameState.finished && turnCount < maxTurns) {
        turnCount++;

        const activePlayer = analyzer.gameState.turn;
        const playerName = activePlayer === 0 ? playerWhite : playerBlack;
        const playerLabel = activePlayer === 0 ? 'White' : 'Black';
        const isActiveMCDSAI = isMCDSAIPlayer(playerName);

        console.error(`\n[Game] === Turn ${turnCount} (${playerLabel}, player=${playerName}${isActiveMCDSAI ? ' [MCDSAI]' : ''}) ===`);

        // --- Stuck detection: capture pre-turn state hash ---
        const preHash = getStateHash(analyzer);

        // --- Call appropriate turn function with retry logic ---
        let turnResult;
        if (isActiveMCDSAI && mcdsaiConfig) {
            const worker = activePlayer === 0 ? mcdsaiConfig.workerWhite : mcdsaiConfig.workerBlack;
            turnResult = await playMCDSAITurn(
                analyzer, activeDeck, worker,
                mcdsaiConfig.difficulty || 'HardestAI'
            );
        } else {
            turnResult = playSingleTurn(analyzer, activeDeck, playerName, thinkTimeMs);
        }

        if (!turnResult.ok) {
            // Retry once on error (malformed JSON, parse failure, etc.)
            console.error(`[Game] Turn ${turnCount} failed: ${turnResult.error}`);
            console.error(`[Game] Retrying (attempt 2/${retryOnError + 1})...`);

            // Dump state for debugging
            try {
                const stateDump = analyzer.gameState.toString();
                console.error(`[Game] State dump at failure:\n${stateDump.substring(0, 1000)}`);
            } catch (dumpErr) {
                console.error(`[Game] State dump failed: ${dumpErr.message}`);
            }

            // Retry
            if (isActiveMCDSAI && mcdsaiConfig) {
                const worker = activePlayer === 0 ? mcdsaiConfig.workerWhite : mcdsaiConfig.workerBlack;
                turnResult = await playMCDSAITurn(
                    analyzer, activeDeck, worker,
                    mcdsaiConfig.difficulty || 'HardestAI'
                );
            } else {
                turnResult = playSingleTurn(analyzer, activeDeck, playerName, thinkTimeMs);
            }

            if (!turnResult.ok) {
                // Second failure — check error type for appropriate handling
                const errMsg = turnResult.error || '';
                errors.push(`Turn ${turnCount} (${playerLabel}): ${errMsg}`);

                if (errMsg.includes('timed out')) {
                    // Timeout: mark game invalid
                    abortReason = `Timeout on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else if (errMsg.includes('Process error')) {
                    // Crash (non-zero exit): mark game invalid
                    abortReason = `Crash on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else {
                    // Malformed JSON, MCDSAI failure, or other: forfeit for this player
                    abortReason = `Forfeit by ${playerLabel} on turn ${turnCount}: ${errMsg}`;
                    console.error(`[Game] FORFEIT: ${abortReason}`);
                    // Set result to opponent wins
                    analyzer.gameState.result = activePlayer === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
                    break;
                }
            } else {
                errors.push(`Turn ${turnCount} (${playerLabel}): recovered after retry`);
            }
        }

        // Log click failures (non-fatal — applyClicks handles them)
        if (turnResult.clickResult && turnResult.clickResult.failed > 0) {
            const failMsg = `Turn ${turnCount} (${playerLabel}): ${turnResult.clickResult.failed} click(s) failed`;
            errors.push(failMsg);
            // Detailed click failures already logged by playSingleTurn/playMCDSAITurn
        }

        // --- Check for game over ---
        if (analyzer.gameState.finished) {
            console.error(`[Game] Game over detected after turn ${turnCount}`);
            break;
        }

        // --- Check stagnation (AS3-style) ---
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            analyzer.gameState.result = C.COLOR_DRAW_STALEMATE;
            abortReason = `Stagnation draw detected at turn ${turnCount}`;
            console.error(`[Game] ${abortReason}`);
            break;
        }

        // --- Stuck detection: compare post-turn hash ---
        const postHash = getStateHash(analyzer);
        recentHashes.push(postHash);

        // Keep only the last stuckThreshold hashes
        if (recentHashes.length > stuckThreshold) {
            recentHashes.shift();
        }

        // Check if all recent hashes are identical (state unchanged)
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

    // Final state
    const finalResult = analyzer.gameState.result;
    const winner = resultToString(finalResult);

    printStateSummary(analyzer, 'GAME END');

    console.error(`\n[Game] ========== RESULT ==========`);
    console.error(`[Game] Winner: ${winner}`);
    console.error(`[Game] Turns: ${turnCount}`);
    console.error(`[Game] Errors: ${errors.length}`);
    if (abortReason) console.error(`[Game] Abort reason: ${abortReason}`);
    if (errors.length > 0) {
        console.error(`[Game] Error log:`);
        for (const e of errors) console.error(`  - ${e}`);
    }
    console.error(`[Game] ================================\n`);

    // Clean up temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    return {
        result: finalResult,
        winner: winner,
        turns: turnCount,
        errors: errors,
        abortReason: abortReason
    };
}

// ---------------------------------------------------------------------------
// 9. Play multiple games with random card sets (Phase 7c)
// ---------------------------------------------------------------------------

/**
 * Play multiple games with random card sets.
 *
 * For each game:
 *   1. Generate a random card set (8 random units + base set)
 *   2. Build mergedDeck from card library
 *   3. Verify supply on the mergedDeck (assert per-game, not just first)
 *   4. Call playSingleGame() with the random card set
 *   5. Log per-game structured JSON
 *
 * ~5% of random card sets trigger AI exceptions (from selfplay_main.js experience).
 * On failure, retry with a different random set up to maxRetries times.
 *
 * @param {Object} config - Game config (playerWhite, playerBlack, thinkTimeMs, mcdsai)
 * @param {number} numGames - Number of games to play
 * @param {Map} library - Card library from loadCardLibrary()
 * @returns {Promise<{ games: Object[], tally: { white: number, black: number, draws: number, invalid: number }, avgTurns: number }>}
 */
async function playMultipleGames(config, numGames, library) {
    const maxRetries = 3;  // Retry with different set if AI fails (~5% of sets)
    const games = [];
    let whiteWins = 0;
    let blackWins = 0;
    let draws = 0;
    let invalid = 0;
    let totalTurns = 0;
    let completedGames = 0;

    for (let g = 0; g < numGames; g++) {
        const gameNum = g + 1;
        let gameLog = null;
        let attempts = 0;

        while (attempts < maxRetries) {
            attempts++;
            const startTime = Date.now();

            // 1. Generate random card set
            const unitNames = randomSet(library, 8);
            console.error(`\n[Multi] Game ${gameNum}/${numGames} (attempt ${attempts}/${maxRetries})`);
            console.error(`[Multi] Card set: [${unitNames.join(', ')}]`);

            // 2. Build mergedDeck
            const mergedDeck = buildMergedDeck(unitNames, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);

            // 3. Verify supply BEFORE each game (not just first)
            const supplyResult = verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error(`[Multi] Game ${gameNum}: Supply verification FAILED — logging and continuing`);
            }

            // 4. Play the game (async — MCDSAI workers use Promises)
            let gameResult;
            let gameError = null;
            try {
                gameResult = await playSingleGame(activeDeck, config);
            } catch (err) {
                gameError = err.message || String(err);
                console.error(`[Multi] Game ${gameNum}: Exception: ${gameError}`);
            }

            const endTime = Date.now();

            // Check if game produced a valid result
            if (gameError) {
                if (attempts < maxRetries) {
                    console.error(`[Multi] Game ${gameNum}: Retrying with different card set...`);
                    continue;
                }
                // Max retries exhausted — log as invalid
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
                    attempts: attempts
                };
                break;
            }

            // Game completed (possibly with abort/forfeit)
            if (gameResult.turns === 0 && attempts < maxRetries) {
                console.error(`[Multi] Game ${gameNum}: 0 turns — AI failure, retrying...`);
                continue;
            }

            // 5. Build per-game log
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
                attempts: attempts
            };
            break;
        }

        // If all retries failed without setting gameLog
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
                attempts: maxRetries
            };
        }

        games.push(gameLog);

        // Tally results
        if (gameLog.winner === 'invalid' || gameLog.result === null) {
            invalid++;
        } else if (gameLog.result === C.COLOR_WHITE) {
            whiteWins++;
            totalTurns += gameLog.turns;
            completedGames++;
        } else if (gameLog.result === C.COLOR_BLACK) {
            blackWins++;
            totalTurns += gameLog.turns;
            completedGames++;
        } else {
            // Draw (stalemate, mutual elimination, max turns, stuck)
            draws++;
            totalTurns += gameLog.turns;
            completedGames++;
        }

        // Progress summary per game
        const elapsed = (gameLog.durationMs / 1000).toFixed(1);
        console.error(`[Multi] Game ${gameNum} result: ${gameLog.winner} in ${gameLog.turns} turns (${elapsed}s)`);
    }

    // Final tally
    const avgTurns = completedGames > 0 ? Math.round(totalTurns / completedGames) : 0;
    const tally = { white: whiteWins, black: blackWins, draws, invalid };

    console.error(`\n[Multi] ========== TALLY ==========`);
    console.error(`[Multi] Games:   ${numGames}`);
    console.error(`[Multi] White:   ${whiteWins} (${numGames > 0 ? (100 * whiteWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Multi] Black:   ${blackWins} (${numGames > 0 ? (100 * blackWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Multi] Draws:   ${draws}`);
    console.error(`[Multi] Invalid: ${invalid}`);
    console.error(`[Multi] Avg turns: ${avgTurns}`);
    console.error(`[Multi] ================================\n`);

    return { games, tally, avgTurns };
}

// ---------------------------------------------------------------------------
// 10. Main
// ---------------------------------------------------------------------------

async function main() {
    const args = process.argv.slice(2);

    // Parse CLI args
    let useRandom = false;
    let singleTurnMode = false;
    let numGames = 1;
    let playerWhite = CONFIG.defaultPlayer;
    let playerBlack = CONFIG.defaultPlayer;
    let thinkTimeMs = CONFIG.thinkTimeMs;
    let mcdsaiDifficulty = 'HardestAI';  // Default MCDSAI difficulty

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--random') useRandom = true;
        if (args[i] === '--single-turn') singleTurnMode = true;
        if (args[i] === '--games' && args[i + 1]) { numGames = parseInt(args[++i], 10); }
        if (args[i] === '--player' && args[i + 1]) {
            playerWhite = args[++i];
            playerBlack = playerWhite;  // same player for both sides unless overridden
        }
        if (args[i] === '--player-white' && args[i + 1]) { playerWhite = args[++i]; }
        if (args[i] === '--player-black' && args[i + 1]) { playerBlack = args[++i]; }
        if (args[i] === '--think-time' && args[i + 1]) { thinkTimeMs = parseInt(args[++i], 10); }
        if (args[i] === '--mcdsai-difficulty' && args[i + 1]) { mcdsaiDifficulty = args[++i]; }
    }

    // Detect MCDSAI players (case-insensitive matching)
    const whiteIsMCDSAI = isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = isMCDSAIPlayer(playerBlack);
    const anyMCDSAI = whiteIsMCDSAI || blackIsMCDSAI;

    // Normalize MCDSAI player names to consistent casing
    if (whiteIsMCDSAI) playerWhite = MCDSAI_PLAYER;
    if (blackIsMCDSAI) playerBlack = MCDSAI_PLAYER;

    // Check exe exists (only needed for C++ players)
    const anyCpp = !whiteIsMCDSAI || !blackIsMCDSAI;
    if (anyCpp && !fs.existsSync(EXE_PATH)) {
        console.error(`ERROR: C++ exe not found at ${EXE_PATH}`);
        console.error('Build with: MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86');
        process.exit(1);
    }

    // Determine mode
    const isMultiGame = numGames > 1 && !singleTurnMode;
    const modeLabel = singleTurnMode ? 'Single-Turn Test (Phase 7a)'
                    : isMultiGame ? `Multi-Game (Phase 7c/7d) — ${numGames} games`
                    : 'Single Game (Phase 7b/7d)';
    console.error(`=== ${modeLabel} ===`);
    if (anyCpp) console.error(`Exe: ${EXE_PATH}`);
    console.error(`White: ${playerWhite}${whiteIsMCDSAI ? ` (MCDSAI difficulty=${mcdsaiDifficulty})` : ''}`);
    console.error(`Black: ${playerBlack}${blackIsMCDSAI ? ` (MCDSAI difficulty=${mcdsaiDifficulty})` : ''}`);
    if (anyCpp) console.error(`Think time: ${thinkTimeMs}ms`);
    if (!singleTurnMode) {
        console.error(`Max turns: ${CONFIG.maxTurns}, Stuck detection: ${CONFIG.stuckDetectionTurns} turns`);
    }
    console.error('');

    // 1. Load card library
    const library = loadCardLibrary();
    console.error(`Loaded card library: ${library.size} entries`);

    // 2. Load MCDSAI dependencies (only when needed)
    let fullParams = null;
    let shortParams = null;
    let mcdsaiWorkerWhite = null;
    let mcdsaiWorkerBlack = null;

    if (anyMCDSAI) {
        const MCDSAIWorker = require('./mcdsai_manager');
        const aiParams = require('./ai_params');
        fullParams = aiParams.loadFullParams();
        shortParams = aiParams.loadShortParams();

        // Spawn MCDSAI workers
        if (whiteIsMCDSAI) {
            mcdsaiWorkerWhite = new MCDSAIWorker('White');
            console.error('Spawning MCDSAI worker for White...');
            await mcdsaiWorkerWhite.spawn();
            console.error('MCDSAI worker for White ready.');
        }
        if (blackIsMCDSAI) {
            mcdsaiWorkerBlack = new MCDSAIWorker('Black');
            console.error('Spawning MCDSAI worker for Black...');
            await mcdsaiWorkerBlack.spawn();
            console.error('MCDSAI worker for Black ready.');
        }
    }

    // Build MCDSAI config object (passed through to playSingleGame)
    const mcdsaiConfig = anyMCDSAI ? {
        workerWhite: mcdsaiWorkerWhite,
        workerBlack: mcdsaiWorkerBlack,
        difficulty: mcdsaiDifficulty,
        fullParams: fullParams,
        shortParams: shortParams,
        library: library
    } : null;

    // Helper to clean up MCDSAI workers on exit
    function terminateWorkers() {
        if (mcdsaiWorkerWhite) {
            console.error('Terminating MCDSAI worker for White...');
            mcdsaiWorkerWhite.terminate();
        }
        if (mcdsaiWorkerBlack) {
            console.error('Terminating MCDSAI worker for Black...');
            mcdsaiWorkerBlack.terminate();
        }
    }

    try {
        // -------------------------------------------------------------------
        // Single-turn mode (Phase 7a compatibility)
        // -------------------------------------------------------------------
        if (singleTurnMode) {
            // Pick card set
            let unitNames;
            if (useRandom) {
                unitNames = randomSet(library, 8);
                console.error(`Random set: [${unitNames.join(', ')}]`);
            } else {
                unitNames = [];
                console.error('Using base-set-only (no random units) for reproducibility');
            }

            const mergedDeck = buildMergedDeck(unitNames, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);
            console.error(`MergedDeck: ${mergedDeck.length} total, ${activeDeck.length} active`);

            console.error('\n--- Supply Verification ---');
            const supplyResult = verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error('WARNING: Supply verification found mismatches (proceeding anyway)');
            }

            console.error('\n--- Game Initialization ---');
            const gameInitInfo = buildGameInitInfo(activeDeck);
            const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
            analyzer.loaderInit();
            console.error('Game initialized successfully.');

            printStateSummary(analyzer, 'INITIAL STATE');

            console.error('\n--- Playing Single Turn ---');
            let turnResult;
            if (whiteIsMCDSAI && mcdsaiConfig) {
                // Initialize MCDSAI for this game
                const aiParams = require('./ai_params');
                const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
                const initParams = JSON.parse(aiParams.selectParams(mcdsaiDifficulty, 1, fullParams, shortParams));
                const initJson = JSON.stringify({ mergedDeck: initDeck, aiParameters: initParams });
                await mcdsaiWorkerWhite.initializeAI(initJson);

                turnResult = await playMCDSAITurn(
                    analyzer, activeDeck, mcdsaiWorkerWhite,
                    mcdsaiDifficulty
                );
            } else {
                turnResult = playSingleTurn(analyzer, activeDeck, playerWhite, thinkTimeMs);
            }

            printStateSummary(analyzer, 'AFTER TURN');

            // Verify results
            console.error('\n--- Verification ---');
            const postState = JSON.parse(analyzer.gameState.toString());
            let verifyOk = true;

            if (turnResult.ok && turnResult.clickResult) {
                if (turnResult.clickResult.applied === 0) {
                    console.error('WARNING: No clicks were applied');
                    verifyOk = false;
                } else {
                    console.error(`OK: ${turnResult.clickResult.applied} clicks applied`);
                }
                if (turnResult.clickResult.failed > 0) {
                    console.error(`WARNING: ${turnResult.clickResult.failed} clicks failed`);
                    verifyOk = false;
                }
            }

            if (turnResult.ok) {
                if (postState.numTurns > 1 || postState.turn !== 0) {
                    console.error('OK: Turn advanced (numTurns or active player changed)');
                } else {
                    console.error('NOTE: Turn did not advance (may still be in action phase if clicks failed)');
                }
            }

            console.error('\n=== RESULT ===');
            if (turnResult.ok && verifyOk) {
                console.error('PASS: Single-turn matchup test completed successfully.');
            } else if (turnResult.ok) {
                console.error('PARTIAL: Turn succeeded but some clicks failed.');
            } else {
                console.error('FAIL: Turn failed.');
            }

            try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

            // Output JSON (compatible with C++ suggest output format where applicable)
            const output = {
                mode: 'single-turn',
                ok: turnResult.ok,
                playerType: whiteIsMCDSAI ? 'MCDSAI' : 'cpp-suggest',
                clicksApplied: turnResult.clickResult ? turnResult.clickResult.applied : 0,
                clicksFailed: turnResult.clickResult ? turnResult.clickResult.failed : 0
            };
            // Include suggest response for C++ players (MCDSAI doesn't produce it)
            if (turnResult.suggest && turnResult.suggest.response) {
                output.suggest = turnResult.suggest.response;
            }
            console.log(JSON.stringify(output, null, 2));
            return;
        }

        // -------------------------------------------------------------------
        // Multi-game mode (Phase 7c/7d — --games N where N > 1)
        // -------------------------------------------------------------------
        if (isMultiGame) {
            console.error(`\n--- Starting ${numGames} Games with Random Card Sets ---`);
            const multiResult = await playMultipleGames(
                { playerWhite, playerBlack, thinkTimeMs, mcdsai: mcdsaiConfig },
                numGames,
                library
            );

            // Output structured results as JSON to stdout
            const output = {
                mode: 'multi-game',
                numGames: numGames,
                tally: multiResult.tally,
                avgTurns: multiResult.avgTurns,
                players: { white: playerWhite, black: playerBlack },
                thinkTimeMs: thinkTimeMs,
                mcdsaiDifficulty: anyMCDSAI ? mcdsaiDifficulty : undefined,
                games: multiResult.games
            };
            console.log(JSON.stringify(output, null, 2));
            return;
        }

        // -------------------------------------------------------------------
        // Single-game mode (Phase 7b/7d — default, --games 1 or no --games)
        // -------------------------------------------------------------------

        // Pick card set
        let unitNames;
        if (useRandom) {
            unitNames = randomSet(library, 8);
            console.error(`Random set: [${unitNames.join(', ')}]`);
        } else {
            unitNames = [];
            console.error('Using base-set-only (no random units) for reproducibility');
        }

        const mergedDeck = buildMergedDeck(unitNames, library);
        const activeDeck = mergedDeck.filter(c => !c._inactive);
        console.error(`MergedDeck: ${mergedDeck.length} total, ${activeDeck.length} active`);

        console.error('\n--- Supply Verification ---');
        const supplyResult = verifySupply(activeDeck);
        if (!supplyResult.ok) {
            console.error('WARNING: Supply verification found mismatches (proceeding anyway)');
        }

        console.error('\n--- Starting Single Game ---');
        const gameResult = await playSingleGame(activeDeck, {
            playerWhite: playerWhite,
            playerBlack: playerBlack,
            thinkTimeMs: thinkTimeMs,
            mcdsai: mcdsaiConfig
        });

        // Output result as JSON to stdout
        const output = {
            mode: 'single-game',
            result: gameResult.result,
            winner: gameResult.winner,
            turns: gameResult.turns,
            errors: gameResult.errors,
            abortReason: gameResult.abortReason,
            players: { white: playerWhite, black: playerBlack },
            thinkTimeMs: thinkTimeMs,
            mcdsaiDifficulty: anyMCDSAI ? mcdsaiDifficulty : undefined,
            cardSet: activeDeck.filter(c => !c.baseSet).map(c => c.UIName || c.name)
        };
        console.log(JSON.stringify(output, null, 2));

    } finally {
        // Always clean up MCDSAI workers
        terminateWorkers();
    }
}

// ---------------------------------------------------------------------------
// Module exports (for use by multi-game matchup runner)
// ---------------------------------------------------------------------------

module.exports = {
    verifySupply,
    exportStateForSuggest,
    callSuggest,
    applyClicks,
    playSingleTurn,
    playMCDSAITurn,
    isMCDSAIPlayer,
    buildGameInitInfo,
    printStateSummary,
    playSingleGame,
    playMultipleGames,
    getStateHash,
    resultToString,
    MCDSAI_PLAYER
};

if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(1);
    });
}
