'use strict';

/**
 * extract_turn_data.js — Extract per-turn state snapshots from replays via the JS engine.
 *
 * Replays clicks through the Analyzer and snapshots game state at each turn boundary.
 * Output is JSON to stdout, consumed by replay_parser/cross_validate.py.
 *
 * Usage:
 *   node extract_turn_data.js <replay.json.gz>
 *   node extract_turn_data.js --batch <codes_file> --replays-dir <dir> [--limit N]
 *
 * Per-turn snapshot includes: resources, unit counts, supply spent (cumulative buys).
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');

/**
 * Load a replay from a .json.gz or .json file.
 */
function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        return JSON.parse(zlib.gunzipSync(raw).toString('utf-8'));
    }
    return JSON.parse(raw.toString('utf-8'));
}

/**
 * Count alive units per player, grouped by display name.
 * Returns { 0: {Drone: 6, Engineer: 2, ...}, 1: {Drone: 7, ...} }
 */
function countUnits(state) {
    const counts = { 0: {}, 1: {} };
    state.table.forEach(inst => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            const name = inst.card.UIName;
            const owner = inst.owner;
            counts[owner][name] = (counts[owner][name] || 0) + 1;
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
 * Extract per-turn snapshots from a replay.
 *
 * Snapshots are taken at the START of each turn (after the previous turn's commit
 * triggers swoosh/defense for the new active player, but before any clicks).
 *
 * We detect turn boundaries by watching numTurns change after each click.
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
        const initOnly = {
            laneInfo: [{
                initResources: replay.initInfo.initResources,
                base: replay.deckInfo.base,
                randomizer: replay.deckInfo.randomizer,
                initCards: replay.initInfo.initCards
            }],
            mergedDeck: replay.deckInfo.mergedDeck,
            scriptInfo: { whiteStarts: true },
            objectiveInfo: null,
            commandInfo: null
        };

        const analyzer = new Analyzer(initOnly, -1, -1, null);
        analyzer.loaderInit();

        const gs = analyzer.gameState;
        const cmdList = replay.commandInfo.commandList;
        const clicksPerTurn = replay.commandInfo.clicksPerTurn;

        // Snapshot initial state (turn 0 = P0's first turn)
        let clickOffset = 0;

        for (let turnIdx = 0; turnIdx < clicksPerTurn.length; turnIdx++) {
            const clickCount = clicksPerTurn[turnIdx];
            const player = turnIdx % 2;
            const playerTurn = Math.floor(turnIdx / 2) + 1;

            // Snapshot at START of turn (before any clicks this turn)
            const activeMana = player === 0 ? gs.whiteMana : gs.blackMana;
            const units = countUnits(gs);

            // Get cumulative supply spent (buys so far)
            const supplySpent = { 0: {}, 1: {} };
            for (let i = 0; i < gs.cards.length; i++) {
                const wb = gs.whiteBought[i] || 0;
                const bb = gs.blackBought[i] || 0;
                if (wb > 0) supplySpent[0][gs.cards[i].UIName] = wb;
                if (bb > 0) supplySpent[1][gs.cards[i].UIName] = bb;
            }

            const turnSnapshot = {
                global_turn: turnIdx,
                player: player,
                player_turn: playerTurn,
                resources: parseMana(activeMana ? activeMana.toString() : ''),
                units_owned: units[player],
                supply_spent: supplySpent
            };

            // Now replay this turn's clicks
            const turnClicks = cmdList.slice(clickOffset, clickOffset + clickCount);
            const buys = [];

            for (const cmd of turnClicks) {
                const cmdType = String(cmd._type);
                if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) continue;
                if (gs.finished) break;

                // Track buys before the click
                const preBoughtW = gs.whiteBought.slice();
                const preBoughtB = gs.blackBought.slice();

                try {
                    const clickResult = analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
                    if (clickResult.canClick) {
                        // Detect buys/unbuys by comparing whiteBought/blackBought
                        const bought = player === 0 ? gs.whiteBought : gs.blackBought;
                        const preBought = player === 0 ? preBoughtW : preBoughtB;
                        for (let i = 0; i < bought.length; i++) {
                            const diff = (bought[i] || 0) - (preBought[i] || 0);
                            if (diff > 0) {
                                for (let j = 0; j < diff; j++) {
                                    buys.push(gs.cards[i].UIName);
                                }
                            } else if (diff < 0) {
                                // Un-buy: remove from buys list (last occurrence)
                                const name = gs.cards[i].UIName;
                                for (let j = 0; j < -diff; j++) {
                                    const idx = buys.lastIndexOf(name);
                                    if (idx >= 0) buys.splice(idx, 1);
                                }
                            }
                        }
                    }
                } catch (err) {
                    // Skip — matches AS3 soft assert behavior
                }
            }

            turnSnapshot.buys = buys;
            result.turns.push(turnSnapshot);
            clickOffset += clickCount;
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
        // Batch mode: process multiple replays, output one JSON object per line (JSONL)
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
                console.error(`SKIP: ${code} (file not found)`);
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
        // Single replay mode
        const filePath = args[0];
        const replay = loadReplay(filePath);
        const code = path.basename(filePath, '.json.gz').replace('.json', '');
        const data = extractTurnData(replay, code);
        console.log(JSON.stringify(data, null, 2));
    }
}

main();
