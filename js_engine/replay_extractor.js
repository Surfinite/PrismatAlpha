'use strict';

/**
 * replay_extractor.js — Extract training data from S3 replays using the faithful JS engine.
 *
 * Downloads replay JSONs, replays clicks through the transpiled AS3 engine, and
 * captures per-turn game states as training examples for vectorize.py.
 *
 * Replaces the old TS-based extract_training_data.js which had desync issues.
 * JS engine achieves 100% replay pass rate (500 tested).
 *
 * Usage:
 *   node replay_extractor.js --codes expert_replays.json --output training.jsonl
 *   node replay_extractor.js --codes codes.txt --output training.jsonl
 *   node replay_extractor.js --code 2feHk-9nh9S                  # Single replay to stdout
 *   node replay_extractor.js --codes expert_replays.json --output training.jsonl --min-rating 2000
 *   node replay_extractor.js --codes expert_replays.json --output training.jsonl --resume
 *
 * Options:
 *   --codes <file>       JSON array (expert_replays.json format) or text file (one code/line)
 *   --code <code>        Single replay code
 *   --output <file>      Output JSONL file (default: stdout)
 *   --min-rating <N>     Skip replays where both players are below N (JSON input only)
 *   --limit <N>          Process at most N replays
 *   --concurrency <N>    Parallel downloads (default: 5)
 *   --resume             Skip codes already in {output}_processed.txt
 *   --validate-balance   Reject replays where unit stats differ from current patch
 *   --verbose            Print per-replay progress
 */

const fs = require('fs');
const path = require('path');

const C = require('./C');
const Analyzer = require('./Analyzer');
const { downloadReplay, replayToGameInitInfo, isLikelyInfoClick } = require('./replay_validator');
const { stateToTrainingExample } = require('./state_adapter');
const { loadCardLibrary } = require('./card_library');

/**
 * Build a UIName→card lookup from the current card library for balance validation.
 *
 * Compares buyCost and toughness — the fields most likely to change between patches.
 *
 * @returns {Map<string, { buyCost: string, toughness: number }>}
 */
function buildBalanceLookup() {
    const library = loadCardLibrary();
    const lookup = new Map();
    for (const [, card] of library) {
        if (card.UIName) {
            lookup.set(card.UIName, {
                buyCost:   card.buyCost || '',
                toughness: card.toughness || 0
            });
        }
    }
    return lookup;
}

/**
 * Validate a replay's mergedDeck against the current card library.
 *
 * Returns null if all units match, or a string describing the first mismatch.
 * Only checks non-base-set units (the randomizer set) since base set units
 * haven't changed. Compares buyCost and toughness.
 *
 * @param {Object} replay - Parsed replay JSON
 * @param {Map} balanceLookup - From buildBalanceLookup()
 * @returns {string|null} Mismatch description, or null if valid
 */
/**
 * Normalize a buyCost string so resource letter order doesn't matter.
 * E.g., "8GBC" and "8BCG" both become "8BCG".
 */
function normalizeCost(cost) {
    const match = (cost || '').match(/^(\d*)(.*)/);
    const digits = match[1] || '';
    const letters = match[2].split('').sort().join('');
    return digits + letters;
}

function validateBalance(replay, balanceLookup) {
    const deck = replay.deckInfo ? replay.deckInfo.mergedDeck : null;
    if (!deck) return 'no mergedDeck';

    for (const card of deck) {
        if (card.baseSet) continue; // Base set hasn't changed
        const name = card.UIName || card.name;
        const current = balanceLookup.get(name);
        if (!current) continue; // Unknown unit (event mode etc.) — caught by UNK check later

        const replayCost = normalizeCost(card.buyCost);
        const currentCost = normalizeCost(current.buyCost);
        const replayHP   = card.toughness || 0;

        if (replayCost !== currentCost) {
            return `${name}: cost ${card.buyCost} != current ${current.buyCost}`;
        }
        if (replayHP !== current.toughness) {
            return `${name}: HP ${replayHP} != current ${current.toughness}`;
        }
    }
    return null;
}

/**
 * Load replay codes from a file.
 *
 * Supports two formats:
 *   1. JSON array of objects with Code, P1RatingIni, P2RatingIni (expert_replays.json)
 *   2. Text file with one code per line (comments with # or // skipped)
 *
 * @param {string} filePath
 * @returns {{ code: string, p1Rating: number|null, p2Rating: number|null }[]}
 */
function loadCodes(filePath) {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const trimmed = raw.trim();

    // Try JSON first
    if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        const data = JSON.parse(trimmed);
        const arr = Array.isArray(data) ? data : [data];
        return arr.map(entry => ({
            code:     entry.Code || entry.code || entry.replay_code,
            p1Rating: entry.P1RatingIni || entry.p1Rating || entry.p1_rating || null,
            p2Rating: entry.P2RatingIni || entry.p2Rating || entry.p2_rating || null
        })).filter(e => e.code);
    }

    // Text file: one code per line
    return trimmed.split('\n')
        .map(line => line.trim().split(/\s+/)[0])
        .filter(line => line && !line.startsWith('#') && !line.startsWith('//'))
        .map(code => ({ code, p1Rating: null, p2Rating: null }));
}

/**
 * Extract training examples from a single replay.
 *
 * Steps through clicks turn-by-turn using clicksPerTurn boundaries.
 * Captures pre-move state at the start of each turn and tracks buys.
 *
 * @param {Object} replay - Parsed replay JSON from S3
 * @param {string} code - Replay code
 * @param {number|null} p1Rating - Player 1 rating (optional)
 * @param {number|null} p2Rating - Player 2 rating (optional)
 * @returns {{ examples: Object[], turns: number, engineResult: number, replayResult: number, errors: string[] }}
 */
function extractFromReplay(replay, code, p1Rating, p2Rating) {
    const errors = [];
    const cmdList = replay.commandInfo.commandList;
    const clicksPerTurn = replay.commandInfo.clicksPerTurn;

    // Suppress ASSERT console.error noise during replay (cancel-target asserts are expected)
    const origError = console.error;
    console.error = function() {};

    // Build game state via Analyzer (no commandInfo — we step manually)
    const gameInitInfo = replayToGameInitInfo(replay);
    const initOnly = {
        laneInfo:      gameInitInfo.laneInfo,
        mergedDeck:    gameInitInfo.mergedDeck,
        scriptInfo:    gameInitInfo.scriptInfo,
        objectiveInfo: null,
        commandInfo:   null
    };

    const analyzer = new Analyzer(initOnly, -1, -1, null);
    analyzer.loaderInit();

    const examples = [];
    let cmdIndex = 0;

    for (let turnIdx = 0; turnIdx < clicksPerTurn.length; turnIdx++) {
        const numClicks = clicksPerTurn[turnIdx];

        if (analyzer.gameState.finished) break;

        // Capture pre-move state BEFORE any clicks for this turn
        const bought = [];
        const example = stateToTrainingExample(analyzer.gameState, code, bought);

        // Add rating info if available
        if (p1Rating != null) example.p0_rating = p1Rating;
        if (p2Rating != null) example.p1_rating = p2Rating;

        // Apply all clicks for this turn
        for (let c = 0; c < numClicks && cmdIndex < cmdList.length; c++, cmdIndex++) {
            const cmd = cmdList[cmdIndex];
            const cmdType = String(cmd._type);

            // Skip emotes
            if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) continue;
            if (analyzer.gameState.finished) break;

            try {
                const clickResult = analyzer.recordClick(
                    false, false, cmd._type, cmd._id, cmd._params
                );

                // Track successful buys
                if (clickResult.canClick &&
                    (cmdType === C.CLICK_CARD || cmdType === C.CLICK_CARD_SHIFT)) {
                    const card = analyzer.gameState.cards[cmd._id];
                    if (card) bought.push(card.UIName);
                }
            } catch (err) {
                // Soft error — skip like the validator does
            }
        }

        examples.push(example);
    }

    // Skip any remaining clicks (shouldn't happen normally)
    // cmdIndex may be < cmdList.length if game ended early

    // Determine final result
    const engineResult = analyzer.gameState.result;
    const replayResult = replay.result;

    // Use engine result if game completed, otherwise fall back to replay result
    let mappedResult;
    if (engineResult === C.COLOR_WHITE)                              mappedResult = 0;
    else if (engineResult === C.COLOR_BLACK)                         mappedResult = 1;
    else if (engineResult === C.COLOR_DRAW_MUTUAL_ELIMINATION ||
             engineResult === C.COLOR_DRAW_STALEMATE)                mappedResult = 2;
    else if (engineResult === C.COLOR_NONE) {
        // Engine didn't reach terminal — expected, since replay click sequences don't
        // include the server-side game-over trigger. Use replay's recorded result.
        mappedResult = replayResult;
    } else {
        mappedResult = 2; // Unknown result codes → draw
    }

    // Restore console.error
    console.error = origError;

    // Set final result on all examples
    for (const ex of examples) {
        ex.result = mappedResult;
    }

    return {
        examples,
        turns: clicksPerTurn.length,
        engineResult,
        replayResult,
        errors
    };
}

/**
 * Process a batch of replay codes, writing training examples to output.
 *
 * @param {{ code: string, p1Rating: number|null, p2Rating: number|null }[]} entries
 * @param {Object} options
 * @param {fs.WriteStream|null} options.outStream
 * @param {number} options.concurrency
 * @param {Set<string>} options.processedCodes
 * @param {string|null} options.processedFile
 * @param {boolean} options.verbose
 * @param {Map|null} options.balanceLookup - If set, validate mergedDeck against current card library
 * @returns {Promise<{ processed: number, skipped: number, failed: number, balanceRejected: number, totalExamples: number }>}
 */
async function batchExtract(entries, options) {
    const { outStream, concurrency, processedCodes, processedFile, verbose, balanceLookup } = options;
    let processed = 0, skipped = 0, failed = 0, balanceRejected = 0, totalExamples = 0;

    for (let i = 0; i < entries.length; i += concurrency) {
        const batch = entries.slice(i, i + concurrency);

        const promises = batch.map(async (entry) => {
            if (processedCodes.has(entry.code)) {
                return { status: 'skipped', code: entry.code };
            }

            try {
                const replay = await downloadReplay(entry.code);

                // Balance validation: reject replays with changed unit stats
                if (balanceLookup) {
                    const mismatch = validateBalance(replay, balanceLookup);
                    if (mismatch) {
                        return { status: 'balance_rejected', code: entry.code, reason: mismatch };
                    }
                }

                const result = extractFromReplay(
                    replay, entry.code, entry.p1Rating, entry.p2Rating
                );
                return { status: 'ok', ...entry, ...result };
            } catch (err) {
                return { status: 'error', code: entry.code, error: err.message };
            }
        });

        const results = await Promise.all(promises);

        for (const r of results) {
            if (r.status === 'skipped') {
                skipped++;
                continue;
            }

            if (r.status === 'balance_rejected') {
                balanceRejected++;
                if (verbose) {
                    console.error(`  BAL   ${r.code}: ${r.reason}`);
                }
                // Track as processed so resume skips it
                processedCodes.add(r.code);
                if (processedFile) {
                    fs.appendFileSync(processedFile, r.code + '\n');
                }
                continue;
            }

            if (r.status === 'error') {
                failed++;
                if (verbose) {
                    console.error(`  ERROR ${r.code}: ${r.error}`);
                }
                continue;
            }

            // Write examples
            for (const ex of r.examples) {
                const line = JSON.stringify(ex) + '\n';
                if (outStream) {
                    outStream.write(line);
                } else {
                    process.stdout.write(line);
                }
            }

            totalExamples += r.examples.length;
            processed++;

            // Track processed code
            processedCodes.add(r.code);
            if (processedFile) {
                fs.appendFileSync(processedFile, r.code + '\n');
            }

            if (verbose) {
                const warns = r.errors.length > 0 ? ` [${r.errors.join('; ')}]` : '';
                console.error(`  OK    ${r.code}: ${r.examples.length} examples, ${r.turns} turns${warns}`);
            }
        }

        // Progress every 50 replays
        const total = Math.min(i + batch.length, entries.length);
        if (total % 50 === 0 || total === entries.length) {
            const balStr = balanceRejected > 0 ? `, ${balanceRejected} bal` : '';
            console.error(`  Progress: ${total}/${entries.length} (${processed} ok, ${skipped} skipped, ${failed} err${balStr}, ${totalExamples} examples)`);
        }
    }

    return { processed, skipped, failed, balanceRejected, totalExamples };
}

async function main() {
    const args = process.argv.slice(2);

    let codesFile = null;
    let singleCode = null;
    let outputPath = null;
    let minRating = 0;
    let limit = Infinity;
    let concurrency = 5;
    let resume = false;
    let verbose = false;
    let validateBalanceFlag = false;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--codes' && args[i + 1])        { codesFile = args[++i]; }
        else if (args[i] === '--code' && args[i + 1])    { singleCode = args[++i]; }
        else if (args[i] === '--output' && args[i + 1])  { outputPath = args[++i]; }
        else if (args[i] === '--min-rating' && args[i+1]){ minRating = parseInt(args[++i], 10); }
        else if (args[i] === '--limit' && args[i + 1])   { limit = parseInt(args[++i], 10); }
        else if (args[i] === '--concurrency' && args[i+1]){ concurrency = parseInt(args[++i], 10); }
        else if (args[i] === '--resume')                  { resume = true; }
        else if (args[i] === '--verbose')                 { verbose = true; }
        else if (args[i] === '--validate-balance')        { validateBalanceFlag = true; }
    }

    if (!codesFile && !singleCode) {
        console.error('Usage:');
        console.error('  node replay_extractor.js --codes <file> --output <file> [--min-rating N] [--limit N] [--resume] [--verbose]');
        console.error('  node replay_extractor.js --code <replay-code>');
        process.exit(2);
    }

    // Single replay mode
    if (singleCode) {
        console.error(`Extracting from replay ${singleCode}...`);
        const replay = await downloadReplay(singleCode);
        const result = extractFromReplay(replay, singleCode, null, null);

        for (const ex of result.examples) {
            process.stdout.write(JSON.stringify(ex) + '\n');
        }

        console.error(`Extracted ${result.examples.length} examples from ${result.turns} turns (result=${result.replayResult})`);
        if (result.errors.length > 0) {
            console.error(`Warnings: ${result.errors.join('; ')}`);
        }
        process.exit(0);
    }

    // Batch mode
    let entries = loadCodes(codesFile);
    console.error(`Loaded ${entries.length} codes from ${codesFile}`);

    // Filter by rating
    if (minRating > 0) {
        const before = entries.length;
        entries = entries.filter(e => {
            if (e.p1Rating == null && e.p2Rating == null) return true; // No rating info → keep
            const maxRating = Math.max(e.p1Rating || 0, e.p2Rating || 0);
            return maxRating >= minRating;
        });
        console.error(`Rating filter (>=${minRating}): ${before} → ${entries.length}`);
    }

    // Apply limit
    if (limit < entries.length) {
        entries = entries.slice(0, limit);
        console.error(`Limited to ${limit} replays`);
    }

    // Resume support
    const processedFile = outputPath ? outputPath.replace(/\.jsonl?$/, '') + '_processed.txt' : null;
    const processedCodes = new Set();

    if (resume && processedFile && fs.existsSync(processedFile)) {
        const lines = fs.readFileSync(processedFile, 'utf-8').trim().split('\n').filter(Boolean);
        for (const line of lines) processedCodes.add(line.trim());
        console.error(`Resume: ${processedCodes.size} codes already processed`);
    }

    // Open output stream
    let outStream = null;
    if (outputPath) {
        const flags = resume && fs.existsSync(outputPath) ? 'a' : 'w';
        outStream = fs.createWriteStream(outputPath, { flags });
    }

    // Build balance lookup if validation requested
    let balanceLookup = null;
    if (validateBalanceFlag) {
        balanceLookup = buildBalanceLookup();
        console.error(`Balance validation enabled (${balanceLookup.size} units in current library)`);
    }

    console.error(`Extracting training data: ${entries.length} replays, concurrency=${concurrency}`);
    const startTime = Date.now();

    const stats = await batchExtract(entries, {
        outStream,
        concurrency,
        processedCodes,
        processedFile,
        verbose,
        balanceLookup
    });

    if (outStream) {
        await new Promise(resolve => outStream.end(resolve));
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    console.error('\n=== Extraction Summary ===');
    console.error(`Replays processed: ${stats.processed}`);
    console.error(`Replays skipped:   ${stats.skipped} (already processed)`);
    if (stats.balanceRejected > 0) {
        console.error(`Balance rejected:  ${stats.balanceRejected} (unit stats changed)`);
    }
    console.error(`Replays failed:    ${stats.failed}`);
    console.error(`Total examples:    ${stats.totalExamples}`);
    console.error(`Time:              ${elapsed}s`);
    if (stats.processed > 0) {
        console.error(`Avg examples/game: ${(stats.totalExamples / stats.processed).toFixed(1)}`);
    }
    if (outputPath) {
        console.error(`Output:            ${outputPath}`);
        if (processedFile) {
            console.error(`Processed codes:   ${processedFile}`);
        }
    }
    console.error('==========================');

    process.exit(stats.failed > 0 ? 1 : 0);
}

module.exports = {
    loadCodes,
    extractFromReplay,
    batchExtract,
    buildBalanceLookup,
    validateBalance
};

if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(2);
    });
}
