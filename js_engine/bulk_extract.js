'use strict';

/**
 * bulk_extract.js — Bulk extraction of per-turn data from replays via the JS engine.
 *
 * Replaces extract_turn_data.js with bought-array-diff buys (authoritative)
 * and a verification block comparing against unit-count-diff buys.
 *
 * Usage:
 *   node bulk_extract.js <replay.json.gz>
 *   node bulk_extract.js --batch <codes_file> --replays-dir <dir> [--limit N]
 *
 * Output: JSONL to stdout (one line per replay), progress to stderr.
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        return JSON.parse(zlib.gunzipSync(raw).toString('utf-8'));
    }
    return JSON.parse(raw.toString('utf-8'));
}

/**
 * Parse a Mana.toString() string into {gold, green, blue, red, energy, attack}.
 * Digits = gold, G = green, B = blue, C = red, H = energy, A = attack.
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
 * Count alive units per player from a State snapshot.
 * Returns { 0: {UnitName: count, ...}, 1: {UnitName: count, ...} }
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
 * Get building (under-construction) units for a player from a State snapshot.
 * Returns sorted array of UINames for alive units with constructionTime > 0.
 */
function getBuildingUnits(state, player) {
    const building = [];
    state.table.forEach(inst => {
        if (inst.deadness === C.DEADNESS_ALIVE &&
            inst.owner === player &&
            inst.constructionTime > 0) {
            building.push(inst.card.UIName);
        }
    });
    return building.sort();
}

/**
 * Extract buys from bought-array diffs between two State snapshots.
 * state.whiteBought[cardId] / state.blackBought[cardId] are cumulative counters
 * that increment on buy, decrement on sell.
 *
 * Returns sorted array of UINames bought this turn.
 */
function extractBoughtDiffBuys(state, nextState, player) {
    const boughtArr = player === 0 ? state.whiteBought : state.blackBought;
    const nextBoughtArr = player === 0 ? nextState.whiteBought : nextState.blackBought;
    const buys = [];

    for (let cardId = 0; cardId < boughtArr.length; cardId++) {
        const diff = nextBoughtArr[cardId] - boughtArr[cardId];
        if (diff > 0) {
            const name = state.cardIdToCard(cardId).UIName;
            for (let j = 0; j < diff; j++) {
                buys.push(name);
            }
        }
    }
    return buys.sort();
}

/**
 * Extract buys from unit-count diffs (for verification).
 * Only counts positive diffs (negative = died/sacced).
 * Returns sorted array of UINames.
 */
function extractUnitDiffBuys(preUnits, postUnits) {
    const buys = [];
    const allNames = new Set([
        ...Object.keys(preUnits),
        ...Object.keys(postUnits)
    ]);
    for (const name of allNames) {
        const diff = (postUnits[name] || 0) - (preUnits[name] || 0);
        for (let j = 0; j < diff; j++) {
            buys.push(name);
        }
    }
    return buys.sort();
}

/**
 * Compare two sorted arrays for element-wise equality.
 */
function arraysEqual(a, b) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
        if (a[i] !== b[i]) return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Core extraction
// ---------------------------------------------------------------------------

function extractTurnData(replay, code) {
    const result = {
        code: code,
        result: replay.result,
        totalTurns: replay.commandInfo.clicksPerTurn.length,
        error: null,
        turns: []
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

        // Last turn has no N+1 to diff — omit it
        const numTurns = Math.min(result.totalTurns, history.length - 1);

        for (let turnIdx = 0; turnIdx < numTurns; turnIdx++) {
            const player = turnIdx % 2;
            const playerTurn = Math.floor(turnIdx / 2) + 1;
            const state = history[turnIdx];
            const nextState = history[turnIdx + 1];

            // Resources at start of turn
            const activeMana = player === 0 ? state.whiteMana : state.blackMana;
            const resources = parseMana(activeMana ? activeMana.toString() : '');

            // Units owned at start of turn
            const units = countUnits(state);
            const unitsOwned = units[player];
            const totalUnits = Object.values(unitsOwned).reduce((a, b) => a + b, 0);

            // Buys from bought-array diffs (authoritative)
            const boughtDiffBuys = extractBoughtDiffBuys(state, nextState, player);

            // Buys from unit-count diffs (for verification)
            const postUnits = countUnits(nextState)[player];
            const unitDiffBuys = extractUnitDiffBuys(unitsOwned, postUnits);

            // Building units at next turn start (units still under construction)
            const building = getBuildingUnits(nextState, player);

            // Verification block
            const verification = {
                bought_diff_buys: boughtDiffBuys,
                unit_diff_buys: unitDiffBuys,
                consistent: arraysEqual(boughtDiffBuys, unitDiffBuys),
                building: building
            };

            result.turns.push({
                global_turn: turnIdx,
                player: player,
                player_turn: playerTurn,
                buys: boughtDiffBuys,
                resources: resources,
                units_owned: unitsOwned,
                total_units: totalUnits,
                actions: [],
                verification: verification
            });
        }

    } catch (err) {
        result.error = err.message;
    }

    return result;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        process.stderr.write('Usage: node bulk_extract.js <replay.json.gz>\n');
        process.stderr.write('       node bulk_extract.js --batch <codes_file> --replays-dir <dir> [--limit N]\n');
        process.exit(2);
    }

    if (args[0] === '--batch') {
        const codesFile = args[1];
        if (!codesFile) {
            process.stderr.write('ERROR: --batch requires a codes file argument\n');
            process.exit(2);
        }
        let replaysDir = '.';
        let limit = Infinity;

        for (let i = 2; i < args.length; i++) {
            if (args[i] === '--replays-dir' && args[i + 1]) { replaysDir = args[++i]; }
            if (args[i] === '--limit' && args[i + 1]) { limit = parseInt(args[++i]); }
        }

        const codes = fs.readFileSync(codesFile, 'utf-8').trim().split('\n').map(s => s.trim()).filter(Boolean);
        let processed = 0;
        let errors = 0;
        let skipped = 0;

        for (const code of codes) {
            if (processed >= limit) break;
            const filename = `${code}.json.gz`;
            const filepath = path.join(replaysDir, filename);
            if (!fs.existsSync(filepath)) {
                skipped++;
                continue;
            }
            try {
                const replay = loadReplay(filepath);
                const data = extractTurnData(replay, code);
                process.stdout.write(JSON.stringify(data) + '\n');
                processed++;
                if (data.error) errors++;
                if (processed % 100 === 0) {
                    process.stderr.write(`Processed ${processed}/${Math.min(codes.length, limit)} (${errors} errors, ${skipped} skipped)\n`);
                }
            } catch (err) {
                process.stderr.write(`ERROR: ${code}: ${err.message}\n`);
                errors++;
            }
        }
        process.stderr.write(`Done: ${processed} replays processed, ${errors} errors, ${skipped} skipped.\n`);
    } else {
        // Single file mode — pretty-print to stdout
        const filePath = args[0];
        const replay = loadReplay(filePath);
        const code = path.basename(filePath, '.json.gz').replace('.json', '');
        const data = extractTurnData(replay, code);
        console.log(JSON.stringify(data, null, 2));
    }
}

main();
