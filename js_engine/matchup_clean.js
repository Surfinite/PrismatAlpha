'use strict';

/**
 * matchup_clean.js — Phase 7a: Single-turn matchup test (clean room rebuild)
 *
 * Orchestrates one turn of Prismata by:
 *   1. Verifying supply at init (rarity-based, no card.supply field)
 *   2. Initializing a JS game via Analyzer
 *   3. Exporting JS state to JSON for C++ --suggest
 *   4. Calling Prismata_Testing.exe --suggest
 *   5. Parsing the JSON response
 *   6. Applying clicks back to JS engine
 *
 * Usage:
 *   node matchup_clean.js                             # Base-set-only single turn test
 *   node matchup_clean.js --random                    # Random 8-unit set
 *   node matchup_clean.js --player LiveHardestAI      # Specific AI player
 *   node matchup_clean.js --think-time 5000           # Custom think time
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const C = require('./C');
const Analyzer = require('./Analyzer');
const { loadCardLibrary, buildMergedDeck, randomSet, getSupply, SUPPLY_BY_RARITY } = require('./card_library');

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
// 8. Main test runner
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);

    // Parse CLI args
    let useRandom = false;
    let playerName = CONFIG.defaultPlayer;
    let thinkTimeMs = CONFIG.thinkTimeMs;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--random') useRandom = true;
        if (args[i] === '--player' && args[i + 1]) { playerName = args[++i]; }
        if (args[i] === '--think-time' && args[i + 1]) { thinkTimeMs = parseInt(args[++i], 10); }
    }

    // Check exe exists
    if (!fs.existsSync(EXE_PATH)) {
        console.error(`ERROR: C++ exe not found at ${EXE_PATH}`);
        console.error('Build with: MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86');
        process.exit(1);
    }

    console.error('=== Phase 7a: Single-Turn Matchup Test ===');
    console.error(`Exe: ${EXE_PATH}`);
    console.error(`Player: ${playerName}`);
    console.error(`Think time: ${thinkTimeMs}ms`);
    console.error('');

    // 1. Load card library
    const library = loadCardLibrary();
    console.error(`Loaded card library: ${library.size} entries`);

    // 2. Pick card set
    let unitNames;
    if (useRandom) {
        unitNames = randomSet(library, 8);
        console.error(`Random set: [${unitNames.join(', ')}]`);
    } else {
        // Fixed set: base set only (no random units) for maximum reproducibility
        unitNames = [];
        console.error('Using base-set-only (no random units) for reproducibility');
    }

    // 3. Build merged deck (active cards only)
    const mergedDeck = buildMergedDeck(unitNames, library);
    const activeDeck = mergedDeck.filter(c => !c._inactive);
    console.error(`MergedDeck: ${mergedDeck.length} total, ${activeDeck.length} active`);

    // 4. Verify supply
    console.error('\n--- Supply Verification ---');
    const supplyResult = verifySupply(activeDeck);
    if (!supplyResult.ok) {
        console.error('WARNING: Supply verification found mismatches (proceeding anyway)');
    }

    // 5. Initialize game
    console.error('\n--- Game Initialization ---');
    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();
    console.error('Game initialized successfully.');

    // Print initial state
    printStateSummary(analyzer, 'INITIAL STATE');

    // 6. Play a single turn (Player 0 = White)
    console.error('\n--- Playing Single Turn ---');
    const turnResult = playSingleTurn(analyzer, activeDeck, playerName, thinkTimeMs);

    // Print post-turn state
    printStateSummary(analyzer, 'AFTER TURN');

    // 7. Verify results
    console.error('\n--- Verification ---');
    const postState = JSON.parse(analyzer.gameState.toString());

    let verifyOk = true;

    // Check that something happened (mana should have changed, or buys made)
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

    // Check if turn advanced (either turn player changed, or numTurns increased)
    // In action phase, ending turn should advance to the other player
    if (turnResult.ok) {
        // Post state should be different from initial (turn 0 White -> turn 1 Black or still action)
        if (postState.numTurns > 1 || postState.turn !== 0) {
            console.error('OK: Turn advanced (numTurns or active player changed)');
        } else {
            console.error('NOTE: Turn did not advance (may still be in action phase if clicks failed)');
        }
    }

    // Final summary
    console.error('\n=== RESULT ===');
    if (turnResult.ok && verifyOk) {
        console.error('PASS: Single-turn matchup test completed successfully.');
    } else if (turnResult.ok) {
        console.error('PARTIAL: --suggest succeeded but some clicks failed.');
    } else {
        console.error('FAIL: --suggest failed.');
    }

    // Clean up temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    // Output the suggest response as JSON to stdout for inspection
    if (turnResult.suggest && turnResult.suggest.response) {
        const output = {
            ok: turnResult.ok,
            suggest: turnResult.suggest.response,
            clicksApplied: turnResult.clickResult ? turnResult.clickResult.applied : 0,
            clicksFailed: turnResult.clickResult ? turnResult.clickResult.failed : 0
        };
        console.log(JSON.stringify(output, null, 2));
    }
}

// ---------------------------------------------------------------------------
// Module exports (for use by future multi-turn matchup runner)
// ---------------------------------------------------------------------------

module.exports = {
    verifySupply,
    exportStateForSuggest,
    callSuggest,
    applyClicks,
    playSingleTurn,
    buildGameInitInfo,
    printStateSummary
};

if (require.main === module) {
    main();
}
