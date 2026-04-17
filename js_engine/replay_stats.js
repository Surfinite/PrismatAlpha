'use strict';

/**
 * replay_stats.js — Parse a Prismata replay and report game statistics.
 *
 * Currently reports: breach count per player.
 * A breach is only counted if it was committed (not undone before turn end).
 *
 * Usage:
 *   node replay_stats.js <replay-code>           # Download from S3
 *   node replay_stats.js --file <path.json.gz>   # Load local .json.gz
 *   node replay_stats.js --file <path.json>       # Load local .json
 *
 * Examples:
 *   node replay_stats.js 2feHk-9nh9S
 *   node replay_stats.js --file replays/game.json.gz
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const http = require('http');
const https = require('https');

const C = require('./C');
const Analyzer = require('./Analyzer');

const S3_BASE = 'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/';

// ---------------------------------------------------------------------------
// Replay loading
// ---------------------------------------------------------------------------

function downloadReplay(code) {
    return new Promise((resolve, reject) => {
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
                    reject(new Error(`Decompress/parse failed: ${err.message}`));
                }
            });
            res.on('error', reject);
        }).on('error', reject);
    });
}

function loadReplayFromFile(filePath) {
    const raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        return JSON.parse(zlib.gunzipSync(raw).toString('utf-8'));
    }
    return JSON.parse(raw.toString('utf-8'));
}

// ---------------------------------------------------------------------------
// Engine setup
// ---------------------------------------------------------------------------

function replayToInitInfo(replay) {
    return {
        laneInfo: [{
            initResources: replay.initInfo.initResources,
            base:          replay.deckInfo.base,
            randomizer:    replay.deckInfo.randomizer,
            initCards:     replay.initInfo.initCards
        }],
        mergedDeck:    replay.deckInfo.mergedDeck,
        scriptInfo:    { whiteStarts: true },
        objectiveInfo: null,
        commandInfo:   null   // We step through clicks manually
    };
}

// ---------------------------------------------------------------------------
// Stats collection
// ---------------------------------------------------------------------------

function collectStats(replay) {
    const analyzer = new Analyzer(replayToInitInfo(replay), -1, -1, null);
    analyzer.loaderInit();

    const cmdList = replay.commandInfo.commandList;
    const gs = analyzer.gameState;

    // Track breaches per player (index 0 = P1, 1 = P2)
    // "breached" means: the player whose glass was broken (the defender)
    const breaches = [0, 0];         // breaches suffered by each player
    let prevTurn = gs.numTurns;
    let glassBrokenThisTurn = false;  // was glassBroken true at any committed point?

    for (let i = 0; i < cmdList.length; i++) {
        const cmd = cmdList[i];
        const cmdType = String(cmd._type);

        // Skip emotes
        if (cmdType.indexOf('replay emote') === 0) continue;
        if (gs.finished) break;

        try {
            analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
        } catch (_) {
            // Soft-fail like the real engine
        }

        // Detect turn change
        if (gs.numTurns !== prevTurn) {
            // A turn just ended. If glassBroken was active when the turn
            // committed, that counts as a breach. The defender is the
            // opponent of whoever was acting (prevTurn's active player).
            if (glassBrokenThisTurn) {
                // In Prismata, turns alternate: even turns = P1 acting, odd = P2 acting.
                // The attacker is the player whose turn just ended.
                // The defender (who got breached) is the other player.
                const attacker = prevTurn % 2;  // 0-indexed: 0=P1, 1=P2
                const defender = 1 - attacker;
                breaches[defender]++;
            }
            glassBrokenThisTurn = false;
            prevTurn = gs.numTurns;
        }

        // Track if glassBroken is active right now.
        // Because undos revert this flag, we only see it true if the
        // current (non-undone) state has an active breach.
        if (gs.glassBroken) {
            glassBrokenThisTurn = true;
        }
    }

    // Handle final turn (game might end mid-breach)
    if (glassBrokenThisTurn && gs.finished) {
        const attacker = prevTurn % 2;
        const defender = 1 - attacker;
        breaches[defender]++;
    }

    // Player names
    const p1Name = replay.playerInfo[0].displayName || 'Player 1';
    const p2Name = replay.playerInfo[1].displayName || 'Player 2';

    // Result
    const resultMap = { 0: p1Name, 1: p2Name, 2: 'Draw' };
    const winner = resultMap[gs.finished ? gs.result : replay.result] || 'Unknown';

    // Card set — randomizer is [[cards], [cards]] (one per player, identical)
    const randRaw = replay.deckInfo.randomizer || [];
    const randomSet = Array.isArray(randRaw[0]) ? randRaw[0] : randRaw.map(c => c.name || c);

    // Ratings — in ratingInfo.initialRatings[].displayRating
    const initRatings = (replay.ratingInfo && replay.ratingInfo.initialRatings) || [];
    const p1Rating = initRatings[0] ? Math.round(initRatings[0].displayRating) : null;
    const p2Rating = initRatings[1] ? Math.round(initRatings[1].displayRating) : null;

    return {
        p1Name,
        p2Name,
        p1Rating,
        p2Rating,
        winner,
        totalTurns: gs.numTurns,
        p1Breaches: breaches[0],
        p2Breaches: breaches[1],
        cardSet: randomSet
    };
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

function printStats(stats, code) {
    console.log('');
    console.log(`=== Replay: ${code} ===`);
    console.log(`Card set: ${stats.cardSet.join(', ')}`);
    const r1 = stats.p1Rating ? ` (${stats.p1Rating})` : '';
    const r2 = stats.p2Rating ? ` (${stats.p2Rating})` : '';
    console.log(`${stats.p1Name}${r1} vs ${stats.p2Name}${r2}`);
    console.log(`Winner: ${stats.winner}  |  Turns: ${stats.totalTurns}`);
    console.log('');
    console.log(`Breaches:`);
    console.log(`  ${stats.p1Name}: breached ${stats.p1Breaches} time(s)`);
    console.log(`  ${stats.p2Name}: breached ${stats.p2Breaches} time(s)`);
    console.log('');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.error('Usage: node replay_stats.js <replay-code>');
        console.error('       node replay_stats.js --file <path.json.gz>');
        process.exit(2);
    }

    let replay, code;

    if (args[0] === '--file') {
        const filePath = args[1];
        if (!filePath) {
            console.error('Missing file path after --file');
            process.exit(2);
        }
        code = path.basename(filePath);
        replay = loadReplayFromFile(filePath);
    } else {
        code = args[0];
        replay = await downloadReplay(code);
    }

    const stats = collectStats(replay);
    printStats(stats, code);
}

main().catch(err => {
    console.error(`Error: ${err.message}`);
    process.exit(1);
});
