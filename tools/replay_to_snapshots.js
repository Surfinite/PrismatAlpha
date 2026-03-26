#!/usr/bin/env node
// tools/replay_to_snapshots.js
// Converts an API-format replay JSON into an array of BoardSnapshot objects
// by replaying clicks through the JS engine.
//
// Usage: node tools/replay_to_snapshots.js <replay.json[.gz]> [-o output.json]

const fs = require('fs');
const zlib = require('zlib');
const path = require('path');

const Analyzer = require('../js_engine/Analyzer');
const { replayToGameInitInfo } = require('../js_engine/replay_validator');
const C = require('../js_engine/C');

const { buildCardIdMap, toCardId } = require('./card_id_map');
const { computeRenderInfo } = require('./position_calculator');
const { validateSnapshot } = require('./snapshot_schema');

// ---------------------------------------------------------------------------
// Card ID map (loaded once)
// ---------------------------------------------------------------------------
const CARD_LIBRARY_PATH = path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso');
const cardIdMap = buildCardIdMap(CARD_LIBRARY_PATH);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Load a replay from a .json or .json.gz file.
 */
function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    let json;
    if (filePath.endsWith('.gz')) {
        json = zlib.gunzipSync(raw).toString('utf-8');
    } else {
        json = raw.toString('utf-8');
    }
    return JSON.parse(json);
}

/**
 * Extract resources from a Mana object.
 */
function extractResources(mana) {
    return {
        gold:   mana.pool[C.MANA_P],
        green:  mana.pool[C.MANA_G],
        blue:   mana.pool[C.MANA_B],
        red:    mana.pool[C.MANA_R],
        energy: mana.pool[C.MANA_H],
        attack: mana.pool[C.MANA_A]
    };
}

/**
 * Build a unit snapshot from an Inst object.
 */
function buildUnitSnapshot(inst) {
    const card = inst.card;
    const displayName = card.UIName || card.cardName;
    const internalName = card.cardName;

    // Look up cardId from the card library map
    const mapEntry = cardIdMap[internalName];
    const cardId = mapEntry ? mapEntry.cardId : toCardId(displayName);

    // Compute render position from card properties
    const renderInfo = computeRenderInfo(card);

    return {
        id: inst.instId,
        cardId: cardId,
        displayName: displayName,
        stats: {
            hp: Math.max(0, inst.health - inst.damage),
            maxHp: inst.health,
            attack: card.attack || card.attackPotential || 0,
            chill: card.chill || 0
        },
        state: {
            mode: inst.constructionTime > 0 ? 'under_construction'
                : (inst.role === C.ROLE_INERT || inst.role === 'inert') ? 'exhausted'
                : 'idle',
            blocking: !!inst.blocking,
            attacking: (card.attack || card.attackPotential || 0) > 0
                && (inst.role === C.ROLE_ASSIGNED || inst.role === 'assigned'),
            chilled: inst.disruptDamage || 0,
            buildTurnsRemaining: inst.constructionTime || 0,
            lifespan: inst.lifespan != null ? inst.lifespan : -1,
            fragile: !!card.fragile,
            frontline: !!card.undefendable
        },
        render: renderInfo
    };
}

/**
 * Collect alive unit IDs from the state table.
 */
function collectAliveSet(state) {
    const alive = new Set();
    state.table.forEach((inst) => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            alive.add(inst.instId);
        }
    });
    return alive;
}

/**
 * Build a cache of unit info (cardId, displayName) for all units in state.
 * This persists across clicks so we can identify units even after they die/leave the table.
 */
function cacheUnitInfo(state, cache) {
    state.table.forEach((inst) => {
        if (!cache.has(inst.instId)) {
            const displayName = inst.card.UIName || inst.card.cardName;
            const internalName = inst.card.cardName;
            const mapEntry = cardIdMap[internalName];
            cache.set(inst.instId, {
                cardId: mapEntry ? mapEntry.cardId : toCardId(displayName),
                displayName: displayName
            });
        }
    });
}

/**
 * Build a full BoardSnapshot from the current analyzer state.
 */
function buildSnapshot(analyzer, seq, events) {
    const state = analyzer.gameState;

    // Build unit lists per player
    const playerUnits = [[], []];
    state.table.forEach((inst) => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            const unit = buildUnitSnapshot(inst);
            playerUnits[inst.owner].push(unit);
        }
    });

    // Map phase constants to strings
    let phaseStr;
    switch (state.phase) {
        case C.PHASE_DEFENSE: phaseStr = 'defense'; break;
        case C.PHASE_ACTION:  phaseStr = 'action';  break;
        case C.PHASE_CONFIRM: phaseStr = 'confirm'; break;
        default: phaseStr = 'action';
    }

    const snapshot = {
        schemaVersion: 1,
        seq: seq,
        turn: state.numTurns,
        phase: phaseStr,
        activePlayer: state.turn,
        players: [
            {
                id: 0,
                resources: extractResources(state.whiteMana),
                units: playerUnits[0]
            },
            {
                id: 1,
                resources: extractResources(state.blackMana),
                units: playerUnits[1]
            }
        ],
        events: events
    };

    return snapshot;
}

/**
 * Detect events by comparing alive sets before and after a click.
 * Uses unitInfoCache for unit metadata (survives unit removal from table).
 */
function detectUnitEvents(prevAlive, state, unitInfoCache) {
    const events = [];
    const currAlive = new Set();

    state.table.forEach((inst) => {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            currAlive.add(inst.instId);
        }
    });

    // New units (in currAlive but not prevAlive) = buy events
    for (const id of currAlive) {
        if (!prevAlive.has(id)) {
            const info = unitInfoCache.get(id) || { cardId: 'unknown', displayName: 'unknown' };
            events.push({
                type: 'buy',
                unitId: id,
                cardId: info.cardId,
                displayName: info.displayName
            });
        }
    }

    // Removed units (in prevAlive but not currAlive) = kill/sacrifice events
    for (const id of prevAlive) {
        if (!currAlive.has(id)) {
            const info = unitInfoCache.get(id) || { cardId: 'unknown', displayName: 'unknown' };

            // Check deadness from the table (unit may still be there but dead)
            let deadness = null;
            state.table.forEach((inst) => {
                if (inst.instId === id) {
                    deadness = inst.deadness;
                }
            });

            if (deadness === C.DEADNESS_SACCED || deadness === C.DEADNESS_SELFSACCED || deadness === C.DEADNESS_AGED) {
                events.push({
                    type: 'sacrifice',
                    unitId: id,
                    cardId: info.cardId,
                    displayName: info.displayName,
                    cause: deadness
                });
            } else if (deadness === C.DEADNESS_BLOCKED) {
                events.push({
                    type: 'kill',
                    unitId: id,
                    cardId: info.cardId,
                    displayName: info.displayName,
                    cause: 'blocker_killed'
                });
            } else if (deadness === C.DEADNESS_WBO) {
                events.push({
                    type: 'kill',
                    unitId: id,
                    cardId: info.cardId,
                    displayName: info.displayName,
                    cause: 'breached'
                });
            } else if (deadness === C.DEADNESS_SNIPED || deadness === C.DEADNESS_NETHERED) {
                events.push({
                    type: 'kill',
                    unitId: id,
                    cardId: info.cardId,
                    displayName: info.displayName,
                    cause: deadness
                });
            } else {
                events.push({
                    type: 'kill',
                    unitId: id,
                    cardId: info.cardId,
                    displayName: info.displayName,
                    cause: deadness || 'combat'
                });
            }
        }
    }

    return events;
}

// ---------------------------------------------------------------------------
// Main processing
// ---------------------------------------------------------------------------

function processReplay(replayPath) {
    const replay = loadReplay(replayPath);

    // Validate replay has required fields
    if (!replay.commandInfo || !replay.deckInfo || !replay.initInfo) {
        throw new Error(
            'Replay is not in API format (missing commandInfo/deckInfo/initInfo). ' +
            'This tool requires replays from the Prismata replay API, not matchup_clean.js output.'
        );
    }

    const gameInitInfo = replayToGameInitInfo(replay);

    // Init WITHOUT auto-replay (commandInfo: null)
    const initOnly = {
        laneInfo:      gameInitInfo.laneInfo,
        mergedDeck:    gameInitInfo.mergedDeck,
        scriptInfo:    gameInitInfo.scriptInfo,
        objectiveInfo: null,
        commandInfo:   null
    };
    const analyzer = new Analyzer(initOnly, -1, -1, null);
    analyzer.loaderInit();

    const snapshots = [];
    const validationErrors = [];
    let seq = 0;

    // Unit info cache — persists across all clicks so dead/removed units still have metadata
    const unitInfoCache = new Map();
    cacheUnitInfo(analyzer.gameState, unitInfoCache);

    // --- Emit initial snapshot (seq 0) ---
    const initialSnapshot = buildSnapshot(analyzer, seq, []);
    const initValidation = validateSnapshot(initialSnapshot);
    if (!initValidation.valid) {
        validationErrors.push({ seq: seq, errors: initValidation.errors });
    }
    snapshots.push(initialSnapshot);
    seq++;

    // --- Replay clicks ---
    const cmdList = replay.commandInfo.commandList;
    let prevPhase = analyzer.gameState.phase;
    let prevTurn = analyzer.gameState.numTurns;
    let prevAlive = collectAliveSet(analyzer.gameState);

    let pendingEvents = [];

    for (let i = 0; i < cmdList.length; i++) {
        const cmd = cmdList[i];

        // Skip emotes
        if (String(cmd._type).indexOf('emote') === 0) continue;

        // Record the click
        const result = analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);

        if (!result.canClick) {
            // Info clicks / UI clicks that legitimately fail — skip
            continue;
        }

        const state = analyzer.gameState;

        // Cache any new unit info before event detection
        cacheUnitInfo(state, unitInfoCache);

        const currPhase = state.phase;
        const currTurn = state.numTurns;

        // Detect unit events from this click
        const unitEvents = detectUnitEvents(prevAlive, state, unitInfoCache);
        pendingEvents = pendingEvents.concat(unitEvents);

        // Check for phase/turn changes
        const phaseChanged = currPhase !== prevPhase;
        const turnChanged = currTurn !== prevTurn;

        if (phaseChanged) {
            pendingEvents.push({
                type: 'phase_change',
                from: prevPhase,
                to: currPhase
            });
        }

        if (turnChanged) {
            pendingEvents.push({
                type: 'turn_start',
                turn: currTurn,
                activePlayer: state.turn
            });
        }

        // Emit snapshot on phase change, turn change, or game end
        if (phaseChanged || turnChanged || state.finished) {
            const snapshot = buildSnapshot(analyzer, seq, pendingEvents);
            const validation = validateSnapshot(snapshot);
            if (!validation.valid) {
                validationErrors.push({ seq: seq, errors: validation.errors });
            }
            snapshots.push(snapshot);
            seq++;
            pendingEvents = [];
        }

        // Update tracking state
        prevPhase = currPhase;
        prevTurn = currTurn;
        prevAlive = collectAliveSet(state);
    }

    // --- Emit final snapshot if there are pending events ---
    if (pendingEvents.length > 0) {
        const finalSnapshot = buildSnapshot(analyzer, seq, pendingEvents);
        const validation = validateSnapshot(finalSnapshot);
        if (!validation.valid) {
            validationErrors.push({ seq: seq, errors: validation.errors });
        }
        snapshots.push(finalSnapshot);
        seq++;
    }

    return { snapshots, validationErrors };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);

    if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
        console.log('Usage: node tools/replay_to_snapshots.js <replay.json[.gz]> [-o output.json]');
        console.log('');
        console.log('Converts an API-format replay into an array of BoardSnapshot objects.');
        console.log('Default output: <input>_snapshots.json');
        process.exit(0);
    }

    const inputPath = args[0];
    if (!fs.existsSync(inputPath)) {
        console.error('Error: file not found: ' + inputPath);
        process.exit(1);
    }

    // Determine output path
    let outputPath;
    const oIdx = args.indexOf('-o');
    if (oIdx !== -1 && args[oIdx + 1]) {
        outputPath = args[oIdx + 1];
    } else {
        // Strip .json.gz or .json, add _snapshots.json
        const base = inputPath.replace(/\.json(\.gz)?$/, '');
        outputPath = base + '_snapshots.json';
    }

    console.log('Processing: ' + inputPath);

    try {
        const { snapshots, validationErrors } = processReplay(inputPath);

        fs.writeFileSync(outputPath, JSON.stringify(snapshots, null, 2));

        console.log('Output: ' + outputPath);
        console.log('Snapshots: ' + snapshots.length);

        if (validationErrors.length > 0) {
            console.log('Validation errors: ' + validationErrors.length + ' snapshot(s) had issues');
            for (const ve of validationErrors) {
                console.log('  seq ' + ve.seq + ': ' + ve.errors.join(', '));
            }
        } else {
            console.log('Validation: all snapshots passed');
        }

        // Print summary
        if (snapshots.length > 0) {
            const first = snapshots[0];
            const last = snapshots[snapshots.length - 1];
            console.log('First snapshot: turn=' + first.turn + ', phase=' + first.phase +
                        ', units=[' + first.players[0].units.length + ',' + first.players[1].units.length + ']');
            console.log('Last snapshot:  turn=' + last.turn + ', phase=' + last.phase +
                        ', units=[' + last.players[0].units.length + ',' + last.players[1].units.length + ']');

            // Count total events
            let totalEvents = 0;
            const eventCounts = {};
            for (const snap of snapshots) {
                for (const evt of snap.events) {
                    totalEvents++;
                    eventCounts[evt.type] = (eventCounts[evt.type] || 0) + 1;
                }
            }
            console.log('Total events: ' + totalEvents);
            if (totalEvents > 0) {
                const parts = Object.entries(eventCounts).map(([k, v]) => k + '=' + v);
                console.log('  ' + parts.join(', '));
            }
        }
    } catch (err) {
        console.error('Error: ' + err.message);
        if (err.stack) {
            console.error(err.stack);
        }
        process.exit(1);
    }
}

if (require.main === module) {
    main();
}

/**
 * Process a replay object directly (no file I/O).
 * Returns array of BoardSnapshot objects.
 */
function processReplayData(replay) {
    if (!replay.commandInfo || !replay.deckInfo || !replay.initInfo) {
        throw new Error(
            'Replay is not in API format (missing commandInfo/deckInfo/initInfo).'
        );
    }

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

    const snapshots = [];
    let seq = 0;
    const unitInfoCache = new Map();
    cacheUnitInfo(analyzer.gameState, unitInfoCache);

    const initialSnapshot = buildSnapshot(analyzer, seq, []);
    snapshots.push(initialSnapshot);
    seq++;

    const cmdList = replay.commandInfo.commandList;
    let prevPhase = analyzer.gameState.phase;
    let prevTurn = analyzer.gameState.numTurns;
    let prevAlive = collectAliveSet(analyzer.gameState);
    let pendingEvents = [];

    for (let i = 0; i < cmdList.length; i++) {
        const cmd = cmdList[i];
        if (String(cmd._type).indexOf('emote') === 0) continue;

        const result = analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
        if (!result || !result.canClick) continue;

        const state = analyzer.gameState;
        cacheUnitInfo(state, unitInfoCache);

        const unitEvents = detectUnitEvents(prevAlive, state, unitInfoCache);
        pendingEvents.push(...unitEvents);

        const currPhase = state.phase;
        const currTurn = state.numTurns;
        const phaseChanged = currPhase !== prevPhase;
        const turnChanged = currTurn !== prevTurn;

        if (phaseChanged) {
            pendingEvents.push({ type: 'phase_change', from: prevPhase, to: currPhase });
        }
        if (turnChanged) {
            pendingEvents.push({ type: 'turn_start', turn: currTurn, activePlayer: state.turn });
        }

        if (phaseChanged || turnChanged || state.finished) {
            const snap = buildSnapshot(analyzer, seq, pendingEvents);
            snapshots.push(snap);
            seq++;
            pendingEvents = [];
        }

        prevPhase = currPhase;
        prevTurn = currTurn;
        prevAlive = collectAliveSet(state);
    }

    if (pendingEvents.length > 0) {
        const snap = buildSnapshot(analyzer, seq, pendingEvents);
        snapshots.push(snap);
    }

    return snapshots;
}

module.exports = { processReplay, processReplayData, loadReplay };
