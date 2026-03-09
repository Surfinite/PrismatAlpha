'use strict';

/**
 * extract_states.js — Extract start-of-turn training states from Prismata replays.
 *
 * Fetches replays from S3, steps through each game using the JS engine,
 * captures ONE training record per player-turn at START-OF-TURN states only.
 * Outputs JSONL with raw state data + metadata.
 *
 * Usage:
 *   node training/extract_states.js --codes training/data/balance_validated_1500plus.json \
 *       --output training/data/raw_states.jsonl [--db c:/libraries/prismata-replay-parser/replays.db] \
 *       [--batch-size 10] [--limit 100] [--verbose]
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const zlib = require('zlib');

// JS engine modules (relative from training/ to js_engine/)
const C = require('../js_engine/C');
const Analyzer = require('../js_engine/Analyzer');
const { _instToUnit, _manaToResources, _buildCardSet, _buildSupply } = require('../js_engine/state_adapter');

// Reuse replay_validator's init logic
const { replayToGameInitInfo } = require('../js_engine/replay_validator');

// --- S3 Replay Fetching ---

const S3_BASE = 'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/';

/**
 * Download and decompress a replay JSON from S3.
 * URL encodes + → %2B, @ → %40.
 */
function fetchReplay(code) {
    return new Promise((resolve, reject) => {
        const safeCode = code.replace(/\+/g, '%2B').replace(/@/g, '%40');
        const url = `${S3_BASE}${safeCode}.json.gz`;
        http.get(url, (res) => {
            if (res.statusCode !== 200) {
                reject(new Error(`HTTP ${res.statusCode} for ${code}`));
                res.resume();
                return;
            }
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                const buf = Buffer.concat(chunks);
                zlib.gunzip(buf, (err, data) => {
                    if (err) {
                        // Maybe not gzipped
                        try { resolve(JSON.parse(buf.toString())); }
                        catch (e) { reject(new Error(`Decompress/parse failed for ${code}: ${e.message}`)); }
                    } else {
                        try { resolve(JSON.parse(data.toString())); }
                        catch (e) { reject(new Error(`JSON parse failed for ${code}: ${e.message}`)); }
                    }
                });
            });
        }).on('error', reject);
    });
}

// --- State Extraction ---

/**
 * Extract state data from a JS engine State object at start of turn.
 * Uses state_adapter.js functions for unit/resource/supply extraction.
 *
 * @param {State} state - JS engine State (from beginTurnHistory)
 * @returns {Object} State data for training record
 */
function extractState(state) {
    const p0Units = [];
    const p1Units = [];

    // Iterate all live instances
    state.table.forEach(function(inst) {
        if (inst.deadness !== C.DEADNESS_ALIVE) return;
        const unit = _instToUnit(inst);
        if (inst.owner === 0) {
            p0Units.push(unit);
        } else {
            p1Units.push(unit);
        }
    });

    const p0Resources = _manaToResources(state.whiteMana);
    const p1Resources = _manaToResources(state.blackMana);

    return {
        p0_units:     p0Units,
        p1_units:     p1Units,
        p0_resources: p0Resources,
        p1_resources: p1Resources,
        supply:       _buildSupply(state),
        card_set:     _buildCardSet(state),
        turn_number:  state.numTurns,
        active_player: state.turn   // 0=white(P0), 1=black(P1)
    };
}

/**
 * Extract the card set (8 random units) from the replay JSON.
 * deckInfo.randomizer is [[p0_units], [p1_units]] with display name strings.
 * Both player arrays are the same for ranked games; take the union.
 */
function extractCardSetFromReplay(replayJSON) {
    const cardSet = new Set();
    if (replayJSON.deckInfo && replayJSON.deckInfo.randomizer) {
        for (const playerCards of replayJSON.deckInfo.randomizer) {
            if (Array.isArray(playerCards)) {
                for (const name of playerCards) {
                    if (typeof name === 'string') {
                        cardSet.add(name);
                    }
                }
            }
        }
    }
    return Array.from(cardSet);
}

/**
 * Extract ratings from the replay JSON's ratingInfo.
 * Returns { p0Rating, p1Rating }.
 */
function extractRatings(replayJSON) {
    let p0Rating = 0, p1Rating = 0;
    if (replayJSON.ratingInfo && replayJSON.ratingInfo.initialRatings) {
        const ir = replayJSON.ratingInfo.initialRatings;
        if (ir[0] && ir[0].displayRating) {
            p0Rating = Math.round(ir[0].displayRating);
        }
        if (ir[1] && ir[1].displayRating) {
            p1Rating = Math.round(ir[1].displayRating);
        }
    }
    return { p0Rating, p1Rating };
}

/**
 * Map replay result to outcome_p0.
 * Replay JSON: result=0 → P0 wins (player in slot 0), result=1 → P1 wins.
 * Output: outcome_p0 = 1 if P0 wins, 0 if P1 wins, 0.5 if draw.
 */
function mapOutcome(result) {
    if (result === 0) return 1;    // P0 wins
    if (result === 1) return 0;    // P1 wins
    return 0.5;                     // draw or unknown
}

// --- Core Processing ---

/**
 * Process a single replay: replay all clicks, then extract start-of-turn states.
 *
 * @param {Object} replayJSON - Parsed replay JSON from S3
 * @param {string} code - Replay code
 * @param {Object} [dbMeta] - Optional metadata from replays.db { rating_p0, rating_p1 }
 * @returns {{ error: string|null, records: Object[] }}
 */
function processReplay(replayJSON, code, dbMeta) {
    const records = [];

    // Validate required fields
    if (!replayJSON.deckInfo || !replayJSON.commandInfo || !replayJSON.initInfo) {
        return { error: 'Missing deckInfo/commandInfo/initInfo', records: [] };
    }
    if (!replayJSON.commandInfo.commandList || !replayJSON.commandInfo.clicksPerTurn) {
        return { error: 'Missing commandList or clicksPerTurn', records: [] };
    }

    // Build game init info
    let gameInitInfo;
    try {
        gameInitInfo = replayToGameInitInfo(replayJSON);
    } catch (e) {
        return { error: `replayToGameInitInfo failed: ${e.message}`, records: [] };
    }

    // Create analyzer and replay all clicks
    let analyzer;
    try {
        const initOnly = {
            laneInfo:      gameInitInfo.laneInfo,
            mergedDeck:    gameInitInfo.mergedDeck,
            scriptInfo:    gameInitInfo.scriptInfo,
            objectiveInfo: null,
            commandInfo:   null  // Don't auto-replay; we do it manually below
        };
        analyzer = new Analyzer(initOnly, -1, -1, null);
        analyzer.loaderInit();
    } catch (e) {
        return { error: `Analyzer init failed: ${e.message}`, records: [] };
    }

    // Replay all clicks (tolerating info clicks, matching replay_validator pattern)
    const cmdList = replayJSON.commandInfo.commandList;
    let replayError = null;
    for (let i = 0; i < cmdList.length; i++) {
        const cmd = cmdList[i];
        const cmdType = String(cmd._type);

        // Skip emotes
        if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) continue;

        // Stop if game finished
        if (analyzer.gameState.finished) break;

        try {
            analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
            // Silently ignore canClick=false (info clicks, misclicks — matches AS3 behavior)
        } catch (e) {
            replayError = `Click ${i} threw: ${e.message}`;
            break;
        }
    }

    if (replayError) {
        return { error: replayError, records };
    }

    // Extract metadata
    const ratings = extractRatings(replayJSON);
    const p0Rating = (dbMeta && dbMeta.rating_p0) || ratings.p0Rating;
    const p1Rating = (dbMeta && dbMeta.rating_p1) || ratings.p1Rating;
    const gameDate = replayJSON.startTime ? Math.floor(replayJSON.startTime) : 0;
    const cardSetMeta = extractCardSetFromReplay(replayJSON);
    const outcome_p0 = mapOutcome(replayJSON.result);
    const totalPlies = analyzer.beginTurnHistory.length;

    // Extract start-of-turn states from beginTurnHistory
    for (let turnIdx = 0; turnIdx < totalPlies; turnIdx++) {
        const turnState = analyzer.beginTurnHistory[turnIdx];
        if (!turnState) continue;

        try {
            const stateData = extractState(turnState);

            records.push({
                replay_code:  code,
                ply_index:    turnIdx,
                total_plies:  totalPlies,
                rating_p0:    p0Rating,
                rating_p1:    p1Rating,
                game_date:    gameDate,
                card_set:     cardSetMeta,
                outcome_p0:   outcome_p0,
                state:        stateData
            });
        } catch (e) {
            // Skip this turn but continue
            if (records.length === 0) {
                // First turn failed — likely engine issue
                return { error: `State extraction failed on turn ${turnIdx}: ${e.message}`, records };
            }
        }
    }

    return { error: null, records };
}

// --- Incremental Processing ---

/**
 * Load the set of already-processed replay codes from the tracking file.
 */
function loadProcessedCodes(trackFile) {
    const codes = new Set();
    if (fs.existsSync(trackFile)) {
        const lines = fs.readFileSync(trackFile, 'utf8').trim().split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed) codes.add(trimmed);
        }
    }
    return codes;
}

// --- DB Metadata (optional) ---

/**
 * Try to load metadata from replays.db for a batch of codes.
 * Returns a Map<code, {rating_p0, rating_p1}>.
 * Requires better-sqlite3. Returns empty map if not available.
 */
function loadDbMetadata(dbPath, codes) {
    const meta = new Map();
    if (!dbPath || !fs.existsSync(dbPath)) return meta;

    try {
        const Database = require('better-sqlite3');
        const db = new Database(dbPath, { readonly: true });

        // Batch query
        const placeholders = codes.map(() => '?').join(',');
        const stmt = db.prepare(
            `SELECT code, p1_rating, p2_rating FROM replays WHERE code IN (${placeholders})`
        );
        const rows = stmt.all(...codes);
        for (const row of rows) {
            meta.set(row.code, {
                rating_p0: Math.round(row.p1_rating || 0),
                rating_p1: Math.round(row.p2_rating || 0)
            });
        }
        db.close();
    } catch (e) {
        // better-sqlite3 not installed or DB schema mismatch — use replay JSON ratings
        process.stderr.write(`[WARN] Could not load DB metadata: ${e.message}\n`);
    }

    return meta;
}

// --- CLI ---

function parseArgs(argv) {
    const args = {
        codesFile: null,
        outputFile: null,
        dbPath: null,
        batchSize: 10,
        limit: 0,
        verbose: false
    };

    for (let i = 2; i < argv.length; i++) {
        switch (argv[i]) {
            case '--codes':
                args.codesFile = argv[++i];
                break;
            case '--output':
                args.outputFile = argv[++i];
                break;
            case '--db':
                args.dbPath = argv[++i];
                break;
            case '--batch-size':
                args.batchSize = parseInt(argv[++i], 10) || 10;
                break;
            case '--limit':
                args.limit = parseInt(argv[++i], 10) || 0;
                break;
            case '--verbose':
                args.verbose = true;
                break;
            default:
                if (!args.codesFile) args.codesFile = argv[i];
                else if (!args.outputFile) args.outputFile = argv[i];
                break;
        }
    }

    if (!args.codesFile) {
        args.codesFile = path.join(__dirname, 'data', 'balance_validated_1500plus.json');
    }
    if (!args.outputFile) {
        args.outputFile = path.join(__dirname, 'data', 'raw_states.jsonl');
    }

    return args;
}

async function main() {
    const args = parseArgs(process.argv);
    const log = (msg) => process.stderr.write(msg + '\n');

    // Load code list
    if (!fs.existsSync(args.codesFile)) {
        log(`ERROR: Codes file not found: ${args.codesFile}`);
        process.exit(1);
    }

    const codesJSON = JSON.parse(fs.readFileSync(args.codesFile, 'utf8'));
    let allCodes;
    if (Array.isArray(codesJSON)) {
        allCodes = codesJSON;
    } else if (codesJSON.codes && Array.isArray(codesJSON.codes)) {
        allCodes = codesJSON.codes;
    } else {
        log('ERROR: Codes file must be a JSON array or { codes: [...] }');
        process.exit(1);
    }
    log(`Loaded ${allCodes.length} codes from ${args.codesFile}`);

    // Incremental tracking
    const trackFile = args.outputFile.replace(/\.jsonl$/, '') + '_processed.txt';
    const processedCodes = loadProcessedCodes(trackFile);
    const unprocessed = allCodes.filter(c => !processedCodes.has(c));

    if (processedCodes.size > 0) {
        log(`Incremental: ${processedCodes.size} already processed, ${unprocessed.length} remaining`);
    }

    // Apply limit
    const toProcess = args.limit > 0 ? unprocessed.slice(0, args.limit) : unprocessed;
    if (toProcess.length === 0) {
        log('No new replays to process.');
        return;
    }
    log(`Processing ${toProcess.length} replays → ${args.outputFile}`);

    // Ensure output directory exists
    const outDir = path.dirname(args.outputFile);
    if (!fs.existsSync(outDir)) {
        fs.mkdirSync(outDir, { recursive: true });
    }

    // Open output streams (append mode if incremental)
    const appendMode = processedCodes.size > 0 && fs.existsSync(args.outputFile);
    const outStream = fs.createWriteStream(args.outputFile, { flags: appendMode ? 'a' : 'w' });
    const trackStream = fs.createWriteStream(trackFile, { flags: 'a' });

    // Counters
    let totalRecords = 0;
    let processedCount = 0;
    let errorCount = 0;
    let fetchErrorCount = 0;
    const startTime = Date.now();
    const errors = []; // First N errors for summary

    // Process in batches
    for (let i = 0; i < toProcess.length; i += args.batchSize) {
        const batch = toProcess.slice(i, i + args.batchSize);

        // Optionally load DB metadata for this batch
        const dbMeta = loadDbMetadata(args.dbPath, batch);

        // Fetch all replays in parallel
        const fetches = batch.map(code =>
            fetchReplay(code)
                .then(json => ({ code, json, fetchError: null }))
                .catch(e => ({ code, json: null, fetchError: e.message }))
        );
        const results = await Promise.all(fetches);

        // Process each replay
        for (const { code, json, fetchError } of results) {
            if (fetchError) {
                fetchErrorCount++;
                if (args.verbose) log(`  FETCH_ERROR ${code}: ${fetchError}`);
                if (errors.length < 20) errors.push({ code, error: `fetch: ${fetchError}` });
                // Don't mark as processed — retry on next run
                continue;
            }

            const meta = dbMeta.get(code) || null;
            const { error, records } = processReplay(json, code, meta);

            if (error) {
                errorCount++;
                if (args.verbose) log(`  ERROR ${code}: ${error}`);
                if (errors.length < 20) errors.push({ code, error });
                // Mark as processed to avoid retrying engine failures
                trackStream.write(code + '\n');
                continue;
            }

            // Write records
            for (const record of records) {
                outStream.write(JSON.stringify(record) + '\n');
            }
            totalRecords += records.length;
            processedCount++;

            // Mark as processed
            trackStream.write(code + '\n');

            if (args.verbose && records.length > 0) {
                log(`  OK ${code}: ${records.length} records`);
            }
        }

        // Progress logging
        const done = Math.min(i + args.batchSize, toProcess.length);
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const rate = processedCount > 0 ? (processedCount / (Date.now() - startTime) * 1000).toFixed(1) : '0';
        log(`  [${done}/${toProcess.length}] ${processedCount} ok, ${errorCount} err, ${fetchErrorCount} fetch_err, ${totalRecords} records (${elapsed}s, ${rate}/s)`);
    }

    // Close streams
    await new Promise(resolve => outStream.end(resolve));
    await new Promise(resolve => trackStream.end(resolve));

    // Summary
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    log('');
    log('=== Extraction Complete ===');
    log(`  Replays processed: ${processedCount}`);
    log(`  Engine errors:     ${errorCount}`);
    log(`  Fetch errors:      ${fetchErrorCount} (will retry on next run)`);
    log(`  Records extracted: ${totalRecords}`);
    if (processedCount > 0) {
        log(`  Avg records/game:  ${(totalRecords / processedCount).toFixed(1)}`);
    }
    log(`  Total processed:   ${processedCodes.size + processedCount + errorCount}`);
    log(`  Time:              ${elapsed}s`);
    log(`  Output:            ${args.outputFile}`);
    log(`  Track file:        ${trackFile}`);

    if (errors.length > 0) {
        log('');
        log(`First ${errors.length} errors:`);
        for (const { code, error } of errors) {
            log(`  ${code}: ${error}`);
        }
    }

    log('===========================');
}

// --- Entry Point ---

if (require.main === module) {
    main().catch(err => {
        process.stderr.write(`FATAL: ${err.stack || err.message}\n`);
        process.exit(2);
    });
}

module.exports = {
    fetchReplay,
    processReplay,
    extractState,
    extractCardSetFromReplay,
    extractRatings,
    mapOutcome
};
