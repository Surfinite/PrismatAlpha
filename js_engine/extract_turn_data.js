'use strict';

/**
 * extract_turn_data.js — Extract per-turn state snapshots from replays via the JS engine.
 *
 * Lets the Analyzer auto-play the full game, then diffs beginTurnHistory snapshots
 * to extract per-turn buys, resources, and unit counts.
 *
 * Usage:
 *   node extract_turn_data.js <replay.json.gz>
 *   node extract_turn_data.js --batch <codes_file> --replays-dir <dir> [--limit N]
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');

function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        return JSON.parse(zlib.gunzipSync(raw).toString('utf-8'));
    }
    return JSON.parse(raw.toString('utf-8'));
}

/**
 * Count alive units per player from a State snapshot.
 * Returns { 0: {Drone: 6, ...}, 1: {Drone: 7, ...} }
 */
function countUnits(state) {
    const counts = { 0: {}, 1: {} };
    state.table.forEach(inst => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            const name = inst.card.UIName;
            counts[inst.owner][name] = (counts[inst.owner][name] || 0) + 1;
        }
    });
    return counts;
}

/**
 * Parse a Mana.toString() string into {gold, green, blue, red, energy, attack}.
 */
function parseMana(manaStr) {
    const result = { gold: 0, green: 0, blue: 0, red: 0, energy: 0, attack: 0 };
    if (!manaStr) return result;
    let digits = '';
    for (const ch of String(manaStr)) {
        if (ch >= '0' && ch <= '9') {
            digits += ch;
        } else {
            if (digits) { result.gold += parseInt(digits); digits = ''; }
            switch (ch) {
                case 'G': result.green++; break;
                case 'B': result.blue++; break;
                case 'C': result.red++; break;
                case 'H': result.energy++; break;
                case 'A': result.attack++; break;
            }
        }
    }
    if (digits) result.gold += parseInt(digits);
    return result;
}

/**
 * Extract per-turn data from a replay.
 *
 * Strategy: let the Analyzer auto-play the entire game (via commandInfo),
 * then use beginTurnHistory[] to diff unit counts at each turn boundary.
 * This correctly handles confirm-phase buys/unbuys, undo chains, etc.
 * because the engine resolves everything internally.
 */
function extractTurnData(replay, code) {
    const result = {
        code: code,
        result: replay.result,
        totalTurns: replay.commandInfo.clicksPerTurn.length,
        turns: [],
        error: null
    };

    try {
        // Let engine auto-play the full game
        const initInfo = {
            laneInfo: [{
                initResources: replay.initInfo.initResources,
                base: replay.deckInfo.base,
                randomizer: replay.deckInfo.randomizer,
                initCards: replay.initInfo.initCards
            }],
            mergedDeck: replay.deckInfo.mergedDeck,
            scriptInfo: { whiteStarts: true },
            objectiveInfo: null,
            commandInfo: {
                commandList: replay.commandInfo.commandList,
                clicksPerTurn: replay.commandInfo.clicksPerTurn,
                gamePosition: replay.commandInfo.commandList.length
            }
        };

        const analyzer = new Analyzer(initInfo, -1, -1, null);
        analyzer.loaderInit();

        const history = analyzer.beginTurnHistory;
        if (!history || history.length < 2) {
            result.error = 'No beginTurnHistory available';
            return result;
        }

        const numTurns = Math.min(result.totalTurns, history.length - 1);

        for (let turnIdx = 0; turnIdx < numTurns; turnIdx++) {
            const player = turnIdx % 2;
            const playerTurn = Math.floor(turnIdx / 2) + 1;
            const state = history[turnIdx];

            // Resources at start of turn
            const activeMana = player === 0 ? state.whiteMana : state.blackMana;

            // Units owned at start of turn
            const units = countUnits(state);

            // Buys = unit count diff between this turn start and next turn start
            const nextState = history[turnIdx + 1];
            const preUnits = units[player];
            const postUnits = countUnits(nextState)[player];
            const buys = [];
            const allNames = new Set([
                ...Object.keys(preUnits),
                ...Object.keys(postUnits)
            ]);
            for (const name of allNames) {
                const diff = (postUnits[name] || 0) - (preUnits[name] || 0);
                // Only count positive diffs as buys (negative = died/sacced)
                for (let j = 0; j < diff; j++) {
                    buys.push(name);
                }
            }

            result.turns.push({
                global_turn: turnIdx,
                player: player,
                player_turn: playerTurn,
                resources: parseMana(activeMana ? activeMana.toString() : ''),
                units_owned: units[player],
                buys: buys
            });
        }

    } catch (err) {
        result.error = err.message;
    }

    return result;
}

// --- CLI ---

function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        console.error('Usage: node extract_turn_data.js <replay.json.gz>');
        console.error('       node extract_turn_data.js --batch <codes_file> --replays-dir <dir> [--limit N]');
        process.exit(2);
    }

    if (args[0] === '--batch') {
        const codesFile = args[1];
        let replaysDir = '.';
        let limit = Infinity;

        for (let i = 2; i < args.length; i++) {
            if (args[i] === '--replays-dir' && args[i + 1]) { replaysDir = args[++i]; }
            if (args[i] === '--limit' && args[i + 1]) { limit = parseInt(args[++i]); }
        }

        const codes = fs.readFileSync(codesFile, 'utf-8').trim().split('\n').map(s => s.trim()).filter(Boolean);
        let processed = 0;

        for (const code of codes) {
            if (processed >= limit) break;
            const filename = `${code}.json.gz`;
            const filepath = path.join(replaysDir, filename);
            if (!fs.existsSync(filepath)) {
                continue;
            }
            try {
                const replay = loadReplay(filepath);
                const data = extractTurnData(replay, code);
                process.stdout.write(JSON.stringify(data) + '\n');
                processed++;
                if (processed % 100 === 0) {
                    console.error(`Processed ${processed}/${Math.min(codes.length, limit)}`);
                }
            } catch (err) {
                console.error(`ERROR: ${code}: ${err.message}`);
            }
        }
        console.error(`Done: ${processed} replays processed.`);
    } else {
        const filePath = args[0];
        const replay = loadReplay(filePath);
        const code = path.basename(filePath, '.json.gz').replace('.json', '');
        const data = extractTurnData(replay, code);
        console.log(JSON.stringify(data, null, 2));
    }
}

main();
