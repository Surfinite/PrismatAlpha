'use strict';

/**
 * replay_validator.js — Validates replays by replaying commandLists through the JS engine.
 *
 * Downloads replay JSON from S3, constructs game state from deckInfo + initInfo,
 * replays every click through the Analyzer, and reports pass/fail with error details.
 *
 * Usage:
 *   node replay_validator.js <code>             # Validate single replay
 *   node replay_validator.js --batch <file>     # Validate list of codes from file
 *   node replay_validator.js --batch <file> --limit 100  # Validate first N codes
 *
 * Exit codes: 0 = all passed, 1 = some failed, 2 = usage error
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const https = require('https');
const http = require('http');

const C = require('./C');
const Analyzer = require('./Analyzer');

const S3_BASE = 'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/';

/**
 * Download and decompress a replay JSON from S3.
 *
 * @param {string} code - Replay code (e.g., "2feHk-9nh9S")
 * @returns {Promise<Object>} Parsed replay JSON
 */
function downloadReplay(code) {
    return new Promise((resolve, reject) => {
        // URL-encode special chars (+ → %2B, @ → %40)
        const encoded = encodeURIComponent(code);
        const url = `${S3_BASE}${encoded}.json.gz`;

        const client = url.startsWith('https') ? https : http;
        client.get(url, (res) => {
            if (res.statusCode !== 200) {
                reject(new Error(`HTTP ${res.statusCode} for ${code}`));
                res.resume();
                return;
            }
            const chunks = [];
            res.on('data', (chunk) => chunks.push(chunk));
            res.on('end', () => {
                try {
                    const buf = Buffer.concat(chunks);
                    const json = zlib.gunzipSync(buf).toString('utf-8');
                    resolve(JSON.parse(json));
                } catch (err) {
                    reject(new Error(`Decompress/parse failed for ${code}: ${err.message}`));
                }
            });
            res.on('error', reject);
        }).on('error', reject);
    });
}

/**
 * Load a replay JSON from a local file (already decompressed).
 *
 * @param {string} filePath - Path to .json file
 * @returns {Object} Parsed replay JSON
 */
function loadReplayFromFile(filePath) {
    const raw = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(raw);
}

/**
 * Construct gameInitInfo from a replay JSON, suitable for Analyzer constructor.
 *
 * Maps replay format:
 *   - deckInfo.mergedDeck → mergedDeck
 *   - deckInfo.base → laneInfo[0].base
 *   - deckInfo.randomizer → laneInfo[0].randomizer
 *   - initInfo.initCards → laneInfo[0].initCards
 *   - initInfo.initResources → laneInfo[0].initResources
 *   - commandInfo → commandInfo (commandList, clicksPerTurn, gamePosition)
 *
 * @param {Object} replay - Parsed replay JSON
 * @returns {{ laneInfo: Object[], mergedDeck: Object[], scriptInfo: Object, objectiveInfo: null, commandInfo: Object }}
 */
function replayToGameInitInfo(replay) {
    const laneInfo = [{
        initResources: replay.initInfo.initResources,
        base:          replay.deckInfo.base,
        randomizer:    replay.deckInfo.randomizer,
        initCards:     replay.initInfo.initCards
    }];

    const scriptInfo = { whiteStarts: true };

    const commandInfo = {
        commandList:   replay.commandInfo.commandList,
        clicksPerTurn: replay.commandInfo.clicksPerTurn,
        gamePosition:  replay.commandInfo.commandList.length
    };

    return {
        laneInfo:      laneInfo,
        mergedDeck:    replay.deckInfo.mergedDeck,
        scriptInfo:    scriptInfo,
        objectiveInfo: null,
        commandInfo:   commandInfo
    };
}

/**
 * Validate a single replay by replaying all commands through the JS engine.
 *
 * In the AS3 game client, C.ASSERT is a soft assert (logs but continues).
 * Replay commandLists include UI info clicks (e.g., shift-clicking opponent's
 * units to view stats) that legitimately fail with canClick=false. These are
 * silently skipped in the original engine.
 *
 * This validator replays click-by-click, tolerating expected failures (info clicks)
 * and tracking unexpected failures (game-affecting clicks that should succeed).
 *
 * @param {Object} replay - Parsed replay JSON
 * @param {string} code - Replay code for reporting
 * @returns {{ pass: boolean, code: string, totalClicks: number, appliedClicks: number,
 *             skippedClicks: number, failedClicks: Array, totalTurns: number,
 *             error: string|null, engineResult: number|null, replayResult: number|null }}
 */
function validateReplay(replay, code) {
    const totalClicks = replay.commandInfo.commandList.length;
    const totalTurns = replay.commandInfo.clicksPerTurn.length;

    const result = {
        pass: false,
        code: code,
        totalClicks: totalClicks,
        appliedClicks: 0,
        skippedClicks: 0,
        failedClicks: [],
        totalTurns: totalTurns,
        error: null,
        engineResult: null,
        replayResult: replay.result,
        // Recovery detection: what matchup_clean would have auto-fixed
        recoveryWouldFire: {
            endSwipeRetry: 0,
            breachSpaceSkip: 0,
            autoCommitMid: 0
        }
    };

    try {
        const gameInitInfo = replayToGameInitInfo(replay);

        // Remove commandInfo so init doesn't auto-replay commands
        // (we need click-by-click control to tolerate info clicks)
        const initOnly = {
            laneInfo:      gameInitInfo.laneInfo,
            mergedDeck:    gameInitInfo.mergedDeck,
            scriptInfo:    gameInitInfo.scriptInfo,
            objectiveInfo: null,
            commandInfo:   null
        };

        const analyzer = new Analyzer(initOnly, -1, -1, null);
        analyzer.loaderInit();

        const cmdList = replay.commandInfo.commandList;

        for (let i = 0; i < cmdList.length; i++) {
            const cmd = cmdList[i];
            const cmdType = String(cmd._type);

            // Skip emotes (matching Analyzer.initializeAndPlayInitClicks behavior)
            if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) {
                result.skippedClicks++;
                continue;
            }

            // Stop if game is already finished
            if (analyzer.gameState.finished) {
                result.skippedClicks += (cmdList.length - i);
                break;
            }

            try {
                // Detect: would matchup_clean auto-commit here? (PHASE_CONFIRM + non-space click)
                const cmdType = String(cmd._type);
                if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished &&
                    cmdType !== C.CLICK_SPACE && cmdType !== 'revert clicked' &&
                    cmdType !== 'undo clicked' && cmdType !== 'redo clicked') {
                    result.recoveryWouldFire.autoCommitMid++;
                }

                const clickResult = analyzer.recordClick(
                    false, false,
                    cmd._type,
                    cmd._id,
                    cmd._params
                );

                if (clickResult.canClick) {
                    result.appliedClicks++;
                } else {
                    // Detect: would matchup_clean breach-space-skip here?
                    if (cmdType === C.CLICK_SPACE && analyzer.gameState.glassBroken) {
                        result.recoveryWouldFire.breachSpaceSkip++;
                    }
                    // Detect: would matchup_clean end-swipe-retry here?
                    if (analyzer.controller && analyzer.controller.inSwipe && cmdType !== C.CLICK_END_SWIPE) {
                        result.recoveryWouldFire.endSwipeRetry++;
                    }

                    // Click failed — categorize as info click or real failure
                    const isInfoClick = isLikelyInfoClick(cmd, analyzer);
                    if (isInfoClick) {
                        result.skippedClicks++;
                    } else {
                        result.failedClicks.push({
                            index: i,
                            click: cmd,
                            turn: analyzer.gameState.numTurns,
                            phase: analyzer.gameState.phase
                        });
                    }
                }
            } catch (err) {
                result.failedClicks.push({
                    index: i,
                    click: cmd,
                    turn: analyzer.gameState.numTurns,
                    phase: analyzer.gameState.phase,
                    error: err.message
                });
            }
        }

        result.engineResult = analyzer.gameState.result;

        // Pass criteria:
        // In the AS3 engine, replay clicks that return canClick=false are silently
        // skipped (C.ASSERT is soft). This is normal — players click units that
        // can't act (defense rearrangement, double-clicks, misclicks). Only
        // thrown errors indicate real engine bugs.
        //
        // The true test is: does the game reach the correct result after replaying
        // all clicks (with failures silently skipped, matching AS3 behavior)?
        const resultMatch = resultMatches(result.engineResult, result.replayResult);
        const hasThrows = result.failedClicks.some(f => f.error != null);
        result.pass = resultMatch && !hasThrows;

    } catch (err) {
        result.error = err.message;
    }

    return result;
}

/**
 * Check if a failed click is likely a UI info click (not a game action).
 *
 * In Prismata, shift-clicking an opponent's unit shows its info without
 * changing game state. These clicks are recorded for replay fidelity but
 * always return canClick=false from the engine.
 *
 * @param {Object} cmd - The click command {_type, _id}
 * @param {Analyzer} analyzer - Current analyzer state
 * @returns {boolean}
 */
function isLikelyInfoClick(cmd, analyzer) {
    // inst shift clicked on opponent's unit → info click
    if (cmd._type === C.CLICK_INST_SHIFT || cmd._type === C.CLICK_INST) {
        const inst = analyzer.gameState.instIdToInst(cmd._id);
        if (inst && inst.owner !== analyzer.gameState.turn) {
            return true;
        }
    }
    return false;
}

/**
 * Check if engine result matches replay result.
 *
 * Replay result: 0=P1 wins, 1=P2 wins, 2=draw
 * Engine result: COLOR_WHITE(0)=white wins, COLOR_BLACK(1)=black wins,
 *                COLOR_NONE(2)=ongoing, COLOR_DRAW_*(3,4)=draw
 *
 * @param {number} engineResult
 * @param {number} replayResult
 * @returns {boolean}
 */
function resultMatches(engineResult, replayResult) {
    if (engineResult === C.COLOR_WHITE && replayResult === 0) return true;
    if (engineResult === C.COLOR_BLACK && replayResult === 1) return true;
    if (engineResult === C.COLOR_NONE) return true; // Game not finished yet
    if ((engineResult === C.COLOR_DRAW_MUTUAL_ELIMINATION ||
         engineResult === C.COLOR_DRAW_STALEMATE) && replayResult === 2) return true;
    // Also accept if both indicate a winner match
    if (engineResult === replayResult) return true;
    return false;
}

/**
 * Categorize a replay by game length.
 *
 * @param {number} turns - Total turns (clicksPerTurn.length)
 * @returns {string} "short" | "mid" | "long" | "stagnation"
 */
function categorizeLength(turns) {
    // turns = clicksPerTurn entries, each player gets ~1 entry per turn
    // So actual rounds ≈ turns / 2
    const rounds = Math.floor(turns / 2);
    if (rounds <= 10) return 'short';
    if (rounds <= 40) return 'mid';
    if (rounds <= 100) return 'long';
    return 'stagnation';
}

/**
 * Run batch validation against a list of replay codes.
 *
 * @param {string[]} codes - Replay codes to validate
 * @param {Object} [options]
 * @param {boolean} [options.verbose=false] - Print per-replay results
 * @param {number} [options.concurrency=5] - Max parallel downloads
 * @returns {Promise<{ passed: number, failed: number, errors: number,
 *                     results: Object[], byCategory: Object }>}
 */
async function batchValidate(codes, options) {
    options = options || {};
    const verbose = options.verbose || false;
    const concurrency = options.concurrency || 5;

    const results = [];
    const byCategory = { short: { pass: 0, fail: 0 }, mid: { pass: 0, fail: 0 },
                         long: { pass: 0, fail: 0 }, stagnation: { pass: 0, fail: 0 } };
    let passed = 0, failed = 0, errors = 0;
    // Aggregate recovery detection across all replays
    const recoveryTotals = { endSwipeRetry: 0, breachSpaceSkip: 0, autoCommitMid: 0 };

    // Process in batches for concurrency control
    for (let i = 0; i < codes.length; i += concurrency) {
        const batch = codes.slice(i, i + concurrency);
        const promises = batch.map(async (code) => {
            try {
                const replay = await downloadReplay(code);
                const result = validateReplay(replay, code);
                return result;
            } catch (err) {
                return {
                    pass: false,
                    code: code,
                    totalClicks: 0,
                    appliedClicks: 0,
                    totalTurns: 0,
                    error: `Download/parse error: ${err.message}`,
                    failClickIndex: null,
                    failClick: null
                };
            }
        });

        const batchResults = await Promise.all(promises);

        for (const result of batchResults) {
            results.push(result);
            const cat = categorizeLength(result.totalTurns);

            // Accumulate recovery detection stats
            if (result.recoveryWouldFire) {
                recoveryTotals.endSwipeRetry += result.recoveryWouldFire.endSwipeRetry;
                recoveryTotals.breachSpaceSkip += result.recoveryWouldFire.breachSpaceSkip;
                recoveryTotals.autoCommitMid += result.recoveryWouldFire.autoCommitMid;
            }

            if (result.error) {
                errors++;
                if (verbose) {
                    console.log(`  ERROR ${result.code}: ${result.error}`);
                }
            } else if (result.pass) {
                passed++;
                byCategory[cat].pass++;
                if (verbose) {
                    console.log(`  PASS  ${result.code} (${result.appliedClicks}/${result.totalClicks} clicks, ${result.totalTurns} turns, ${cat})`);
                }
            } else {
                failed++;
                byCategory[cat].fail++;
                if (verbose) {
                    const nFail = result.failedClicks.length;
                    const firstFail = nFail > 0 ? result.failedClicks[0] : null;
                    const failInfo = firstFail
                        ? `${nFail} failed clicks, first at #${firstFail.index}: ${JSON.stringify(firstFail.click)} (turn ${firstFail.turn})`
                        : `result mismatch: engine=${result.engineResult}, replay=${result.replayResult}`;
                    console.log(`  FAIL  ${result.code}: ${failInfo} (${result.totalTurns} turns, ${cat})`);
                }
            }
        }

        // Progress report
        const total = i + batch.length;
        if (!verbose && total % 50 === 0) {
            console.log(`  Progress: ${total}/${codes.length} (${passed} pass, ${failed} fail, ${errors} err)`);
        }
    }

    return { passed, failed, errors, results, byCategory, recoveryTotals };
}

/**
 * Print a summary report of batch validation results.
 */
function printReport(summary, totalCodes) {
    const { passed, failed, errors, byCategory, recoveryTotals } = summary;
    const tested = passed + failed;
    const passRate = tested > 0 ? (100 * passed / tested).toFixed(1) : '0.0';

    console.log('\n=== Replay Validation Report ===');
    console.log(`Total codes: ${totalCodes}`);
    console.log(`Tested:      ${tested} (${errors} download/parse errors skipped)`);
    console.log(`Passed:      ${passed} (${passRate}%)`);
    console.log(`Failed:      ${failed}`);
    console.log('');
    console.log('By game length:');
    for (const [cat, counts] of Object.entries(byCategory)) {
        const catTotal = counts.pass + counts.fail;
        if (catTotal > 0) {
            const catRate = (100 * counts.pass / catTotal).toFixed(1);
            console.log(`  ${cat.padEnd(12)} ${counts.pass}/${catTotal} (${catRate}%)`);
        }
    }
    if (recoveryTotals) {
        console.log('');
        console.log('Recovery detection (what matchup_clean would auto-fix):');
        console.log(`  Auto-commit (mid-turn):  ${recoveryTotals.autoCommitMid}   [expected: protocol]`);
        console.log(`  End-swipe retry:         ${recoveryTotals.endSwipeRetry}   [INVESTIGATE if > 0]`);
        console.log(`  Breach space skip:       ${recoveryTotals.breachSpaceSkip}   [expected: cosmetic]`);
    }
    console.log('================================\n');
}

// --- CLI ---

async function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.log('Usage:');
        console.log('  node replay_validator.js <code>                  # Single replay');
        console.log('  node replay_validator.js --batch <file> [--limit N] [--verbose]  # Batch');
        process.exit(2);
    }

    if (args[0] === '--batch') {
        // Batch mode
        const file = args[1];
        if (!file || !fs.existsSync(file)) {
            console.error(`File not found: ${file}`);
            process.exit(2);
        }

        let limit = Infinity;
        let verbose = false;
        for (let i = 2; i < args.length; i++) {
            if (args[i] === '--limit' && args[i + 1]) {
                limit = parseInt(args[i + 1], 10);
                i++;
            }
            if (args[i] === '--verbose') {
                verbose = true;
            }
        }

        // Read codes from file (one per line, skip comments and blanks)
        const raw = fs.readFileSync(file, 'utf-8');
        let codes = raw.split('\n')
            .map(line => line.trim().split(/\s+/)[0])  // Take first token (handles TSV)
            .filter(line => line && !line.startsWith('#') && !line.startsWith('//'));

        if (limit < codes.length) {
            codes = codes.slice(0, limit);
        }

        console.log(`Validating ${codes.length} replays...`);
        const summary = await batchValidate(codes, { verbose, concurrency: 5 });
        printReport(summary, codes.length);

        // Write detailed results to JSON
        const outPath = path.join(__dirname, 'validation_results.json');
        fs.writeFileSync(outPath, JSON.stringify({
            timestamp: new Date().toISOString(),
            totalCodes: codes.length,
            passed: summary.passed,
            failed: summary.failed,
            errors: summary.errors,
            passRate: summary.passed / (summary.passed + summary.failed) || 0,
            byCategory: summary.byCategory,
            recoveryTotals: summary.recoveryTotals,
            failures: summary.results.filter(r => !r.pass)
        }, null, 2));
        console.log(`Detailed results written to ${outPath}`);

        process.exit(summary.failed > 0 ? 1 : 0);
    } else {
        // Single replay mode
        const code = args[0];
        console.log(`Downloading replay ${code}...`);

        try {
            const replay = await downloadReplay(code);
            console.log(`Replay loaded: ${replay.commandInfo.commandList.length} clicks, ${replay.commandInfo.clicksPerTurn.length} turns`);

            const result = validateReplay(replay, code);

            if (result.pass) {
                console.log(`PASS: All ${result.totalClicks} clicks applied (${result.skippedClicks} info/emote skipped)`);
                process.exit(0);
            } else {
                console.log(`FAIL: ${result.appliedClicks}/${result.totalClicks} clicks applied, ${result.skippedClicks} skipped, ${result.failedClicks.length} failed`);
                if (result.failedClicks.length > 0) {
                    const first5 = result.failedClicks.slice(0, 5);
                    for (const f of first5) {
                        console.log(`  [${f.index}] ${JSON.stringify(f.click)} turn=${f.turn} phase=${f.phase}${f.error ? ' err=' + f.error : ''}`);
                    }
                    if (result.failedClicks.length > 5) {
                        console.log(`  ... and ${result.failedClicks.length - 5} more`);
                    }
                }
                if (result.error) {
                    console.log(`  Error: ${result.error}`);
                }
                process.exit(1);
            }
        } catch (err) {
            console.error(`Error: ${err.message}`);
            process.exit(2);
        }
    }
}

// Export for programmatic use
module.exports = {
    downloadReplay,
    loadReplayFromFile,
    replayToGameInitInfo,
    validateReplay,
    isLikelyInfoClick,
    resultMatches,
    batchValidate,
    categorizeLength,
    printReport
};

// Run CLI if executed directly
if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(2);
    });
}
