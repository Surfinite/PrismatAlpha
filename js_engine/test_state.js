'use strict';

/**
 * test_state.js — Unit tests for State.js core game state machine.
 *
 * Tests:
 * 1. Fresh game construction from laneInfo/mergedDeck
 * 2. Initial state properties (turn, phase, mana, instances)
 * 3. BUY move processing
 * 4. ASSIGN (use ability) move processing
 * 5. ENTER_CONFIRM + COMMIT (end turn cycle)
 * 6. Swoosh (turn resolution — construction tick, role refresh)
 * 7. Multi-turn sequence (full game cycle)
 * 8. Clone deep copy
 * 9. Serialization round-trip
 * 10. StateHelper update integration
 *
 * Run: node js_engine/test_state.js
 */

const C = require('./C');
const State = require('./State');
const Mana = require('./Mana');
const { loadCardLibrary, buildMergedDeck } = require('./card_library');

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
        console.log(`  PASS: ${message}`);
    } else {
        failed++;
        console.error(`  FAIL: ${message}`);
    }
}

/**
 * Build standard Prismata starting position.
 * P1 (white): 6 Drone, 2 Engineer, 6 gold
 * P2 (black): 7 Drone, 2 Engineer, 7 gold
 */
function buildStandardGame(advancedUnits) {
    advancedUnits = advancedUnits || [];
    const library = loadCardLibrary();
    const mergedDeck = buildMergedDeck(advancedUnits, library);

    // Map internal names for base supply (Academy=Animus, Brooder=Blastforge)
    const baseNames = ['Drone', 'Engineer', 'Conduit', 'Brooder', 'Academy',
        'Wall', 'Treant', 'Elephant', 'Tesla Tower', 'Blood Barrier', 'Minicannon'];

    const laneInfo = [{
        initResources: ['6', '7'],
        base: [baseNames, baseNames],
        randomizer: [[], []],
        initCards: [
            [[6, 'Drone'], [2, 'Engineer']],
            [[7, 'Drone'], [2, 'Engineer']]
        ]
    }];

    // Add advanced unit names (internal names) to randomizer
    if (advancedUnits.length > 0) {
        const uiToInternal = new Map();
        for (const [internalName, card] of library) {
            uiToInternal.set(card.UIName, internalName);
        }
        const randNames = advancedUnits.map(ui => uiToInternal.get(ui));
        laneInfo[0].randomizer = [randNames, randNames];
    }

    const scriptInfo = { whiteStarts: true };
    return new State(laneInfo, mergedDeck, scriptInfo, null, -1, -1);
}

function main() {
    console.log('=== State.js Core Engine Tests ===\n');

    // Test 1: Fresh game construction
    console.log('Test 1: Fresh game construction');
    const state = buildStandardGame();
    assert(state !== null, 'State constructed');
    assert(state.numTurns === 0, 'numTurns = 0 (white starts)');
    assert(state.turn === C.COLOR_WHITE, 'turn = white (turn 0)');
    assert(state.phase === C.PHASE_ACTION, 'phase = action');
    assert(state.glassBroken === false, 'glassBroken = false');
    assert(state.result === C.COLOR_NONE, 'result = none');
    assert(state.finished === false, 'not finished');

    // Test 2: Initial mana
    console.log('\nTest 2: Initial mana');
    assert(state.whiteMana.money === 6, 'White mana = 6 gold');
    assert(state.blackMana.money === 7, 'Black mana = 7 gold');
    assert(state.turnMana.money === 6, 'Turn mana (white) = 6 gold');
    assert(state.oppMana.money === 7, 'Opp mana (black) = 7 gold');

    // Test 3: Initial instances
    console.log('\nTest 3: Initial instances');
    let whiteCount = 0, blackCount = 0;
    let whiteDrones = 0, whiteEngineers = 0;
    let blackDrones = 0, blackEngineers = 0;
    state.table.forEach((inst) => {
        if (inst.owner === C.COLOR_WHITE) {
            whiteCount++;
            if (inst.cardName === 'Drone') whiteDrones++;
            if (inst.cardName === 'Engineer') whiteEngineers++;
        } else {
            blackCount++;
            if (inst.cardName === 'Drone') blackDrones++;
            if (inst.cardName === 'Engineer') blackEngineers++;
        }
    });
    assert(whiteCount === 8, `White has 8 units (got ${whiteCount})`);
    assert(blackCount === 9, `Black has 9 units (got ${blackCount})`);
    assert(whiteDrones === 6, `White has 6 Drones (got ${whiteDrones})`);
    assert(whiteEngineers === 2, `White has 2 Engineers (got ${whiteEngineers})`);
    assert(blackDrones === 7, `Black has 7 Drones (got ${blackDrones})`);
    assert(blackEngineers === 2, `Black has 2 Engineers (got ${blackEngineers})`);
    assert(state.table.length === 17, `17 total instances (got ${state.table.length})`);

    // Test 4: Instance properties
    console.log('\nTest 4: Initial instance properties');
    let droneInst = null;
    state.table.forEach((inst) => {
        if (inst.cardName === 'Drone' && inst.owner === C.COLOR_WHITE && !droneInst) {
            droneInst = inst;
        }
    });
    assert(droneInst !== null, 'Found a white Drone');
    assert(droneInst.constructionTime === 0, 'Drone constructionTime = 0 (init)');
    assert(droneInst.role === C.ROLE_DEFAULT, 'Drone role = default (has ability)');
    assert(droneInst.blocking === true, 'Drone blocking = true (defaultBlocking)');
    assert(droneInst.dead === false, 'Drone alive');
    assert(droneInst.health === 1, 'Drone health = 1');

    // Test 5: Supply
    console.log('\nTest 5: Supply arrays');
    const droneId = state.cardNameToCardId['Drone'];
    assert(droneId !== undefined, 'Drone has cardId');
    assert(state.whiteSupply[droneId] === 20, `White Drone supply = 20 (trinket rarity)`);
    assert(state.blackSupply[droneId] === 20, `Black Drone supply = 20`);
    const condId = state.cardNameToCardId['Conduit'];
    assert(state.whiteSupply[condId] === 10, 'White Conduit supply = 10 (normal rarity)');

    // Test 6: StateHelper integration
    console.log('\nTest 6: StateHelper after init');
    assert(state.helper.ownDefense > 0, `Own defense > 0 (got ${state.helper.ownDefense})`);
    assert(state.helper.oppDefense > 0, `Opp defense > 0 (got ${state.helper.oppDefense})`);
    assert(state.helper.ownAllUnitsTotal > 0, `Own total > 0 (got ${state.helper.ownAllUnitsTotal})`);
    assert(state.helper.oppAllUnitsTotal > 0, `Opp total > 0 (got ${state.helper.oppAllUnitsTotal})`);

    // Test 7: BUY move
    console.log('\nTest 7: BUY move');
    const preGold = state.turnMana.money;
    const droneCost = state.cards[droneId].buyCost.money;
    const instId = state.nextInstId;
    state.processMove(C.MOVE_BUY, instId, -1, droneId);
    assert(state.turnMana.money === preGold - droneCost,
        `Gold decreased by ${droneCost} (now ${state.turnMana.money})`);
    const boughtInst = state.instIdToInst(instId);
    assert(boughtInst !== null, 'Bought inst exists in table');
    assert(boughtInst.cardName === 'Drone', 'Bought inst is Drone');
    assert(boughtInst.role === C.ROLE_SELLABLE, 'Bought inst is sellable');
    assert(boughtInst.constructionTime === 1, 'Drone constructionTime = 1');
    assert(boughtInst.blocking === false, 'Under construction — not blocking');
    assert(state.whiteBought[droneId] === 1, 'whiteBought incremented');

    // Buy another Drone
    const instId2 = state.nextInstId;
    state.processMove(C.MOVE_BUY, instId2, -1, droneId);
    assert(state.whiteBought[droneId] === 2, 'whiteBought = 2 after second buy');

    // Test 8: SELL (undo buy)
    console.log('\nTest 8: SELL (undo buy)');
    const goldBeforeSell = state.turnMana.money;
    state.processMove(C.MOVE_SELL, instId2, -1, droneId);
    assert(state.turnMana.money === goldBeforeSell + droneCost, 'Gold restored after sell');
    assert(state.whiteBought[droneId] === 1, 'whiteBought decremented after sell');
    assert(state.instIdToInst(instId2) === null, 'Sold inst removed from table');

    // Test 9: ASSIGN (use Drone ability — click to produce gold)
    console.log('\nTest 9: ASSIGN (use ability)');
    const goldBefore = state.turnMana.money;
    state.processMove(C.MOVE_ASSIGN, droneInst.instId);
    assert(droneInst.role === C.ROLE_ASSIGNED, 'Drone role = assigned');
    assert(state.turnMana.money === goldBefore + 1, 'Gold +1 from Drone ability');

    // Test 10: UNASSIGN (undo ability)
    console.log('\nTest 10: UNASSIGN');
    state.processMove(C.MOVE_UNASSIGN, droneInst.instId);
    assert(droneInst.role === C.ROLE_DEFAULT, 'Drone role = default after unassign');
    assert(state.turnMana.money === goldBefore, 'Gold restored after unassign');

    // Re-assign for turn progression
    state.processMove(C.MOVE_ASSIGN, droneInst.instId);

    // Test 11: ENTER_CONFIRM + COMMIT (end turn)
    console.log('\nTest 11: ENTER_CONFIRM + COMMIT');
    assert(state.phase === C.PHASE_ACTION, 'Phase = action before confirm');
    state.processMove(C.MOVE_ENTER_CONFIRM);
    assert(state.phase === C.PHASE_CONFIRM, 'Phase = confirm after ENTER_CONFIRM');
    assert(state.endTurnObject !== null, 'EndTurnObject created');

    state.processMove(C.MOVE_COMMIT);
    // After commit: numTurns increments, now black's turn
    assert(state.numTurns === 1, 'numTurns = 1 after commit');
    assert(state.turn === C.COLOR_BLACK, 'Turn = black');
    // If no attack, swoosh runs immediately (no defense phase)
    assert(state.phase === C.PHASE_ACTION, 'Phase = action (no enemy attack → swoosh)');

    // Test 12: Black's turn — verify mana
    console.log('\nTest 12: Black turn state');
    assert(state.turnMana === state.blackMana, 'turnMana points to blackMana');
    assert(state.turnMana.money === 7, `Black mana = 7 gold (got ${state.turnMana.money})`);

    // Test 13: Swoosh effects — Drone that was under construction
    console.log('\nTest 13: Swoosh — construction ticked');
    // The white Drone we bought (instId) should have ticked construction 1→0
    // But swoosh only ticks the CURRENT player's units, which is black now
    // The white Drone won't tick until white's next swoosh
    const boughtDrone = state.instIdToInst(instId);
    assert(boughtDrone !== null, 'Bought Drone still exists');
    assert(boughtDrone.constructionTime === 1, 'White Drone still under construction (black turn)');

    // Assign all black Drones, end turn
    let blackDroneCount = 0;
    state.table.forEach((inst) => {
        if (inst.cardName === 'Drone' && inst.owner === C.COLOR_BLACK &&
            inst.role === C.ROLE_DEFAULT) {
            state.processMove(C.MOVE_ASSIGN, inst.instId);
            blackDroneCount++;
        }
    });
    assert(blackDroneCount === 7, `Assigned ${blackDroneCount} black Drones`);

    state.processMove(C.MOVE_ENTER_CONFIRM);
    state.processMove(C.MOVE_COMMIT);

    // Now it's white's turn again (numTurns = 2)
    assert(state.numTurns === 2, `numTurns = 2 (got ${state.numTurns})`);
    assert(state.turn === C.COLOR_WHITE, 'Turn = white again');

    // Test 14: Swoosh construction tick
    console.log('\nTest 14: Swoosh construction tick on bought Drone');
    assert(boughtDrone.constructionTime === 0, 'Bought Drone finished construction');
    assert(boughtDrone.role === C.ROLE_DEFAULT, 'Finished Drone role = default');
    assert(boughtDrone.blocking === true, 'Finished Drone blocking = true');

    // The assigned white Drone should be refreshed by swoosh
    assert(droneInst.role === C.ROLE_DEFAULT, 'Previously assigned Drone refreshed to default');
    assert(droneInst.blocking === true, 'Refreshed Drone blocking = true');

    // Test 15: Clone
    console.log('\nTest 15: Clone deep copy');
    const clone = state.clone();
    assert(clone.numTurns === state.numTurns, 'Clone numTurns matches');
    assert(clone.turn === state.turn, 'Clone turn matches');
    assert(clone.phase === state.phase, 'Clone phase matches');
    assert(clone.whiteMana.money === state.whiteMana.money, 'Clone white mana matches');
    assert(clone.blackMana.money === state.blackMana.money, 'Clone black mana matches');
    assert(clone.table.length === state.table.length, 'Clone table size matches');
    assert(clone.cards === state.cards, 'Clone shares card definitions (immutable)');

    // Mutate clone — verify independence
    clone.whiteMana.money = 999;
    assert(state.whiteMana.money !== 999, 'Clone mutation does not affect original');

    // Test 16: Serialization
    console.log('\nTest 16: Serialization');
    const json = state.toString();
    assert(typeof json === 'string', 'toString returns string');
    const parsed = JSON.parse(json);
    assert(parsed.numTurns === state.numTurns, 'Serialized numTurns');
    assert(parsed.turn === state.turn, 'Serialized turn');
    assert(parsed.phase === 'action', 'Serialized phase = "action"');
    assert(parsed.glassBroken === false, 'Serialized glassBroken');
    assert(parsed.result === C.COLOR_NONE, 'Serialized result');
    assert(Array.isArray(parsed.table), 'Serialized table is array');
    assert(parsed.table.length === state.table.length,
        `Serialized table length = ${parsed.table.length}`);
    assert(parsed.whiteMana === state.whiteMana.toString(), 'Serialized whiteMana');
    assert(parsed.blackMana === state.blackMana.toString(), 'Serialized blackMana');
    assert(Array.isArray(parsed.whiteTotalSupply), 'Serialized whiteTotalSupply');
    assert(Array.isArray(parsed.whiteSupplySpent), 'Serialized whiteSupplySpent');

    // Table entries have correct fields
    const firstEntry = parsed.table[0];
    assert(firstEntry.hasOwnProperty('cardName'), 'Table entry has cardName');
    assert(firstEntry.hasOwnProperty('instId'), 'Table entry has instId');
    assert(firstEntry.hasOwnProperty('role'), 'Table entry has role');
    assert(firstEntry.hasOwnProperty('health'), 'Table entry has health');
    assert(firstEntry.hasOwnProperty('blocking'), 'Table entry has blocking');

    // Test 17: Stagnation counters
    console.log('\nTest 17: Stagnation counters');
    assert(Array.isArray(state.whiteNoProgress), 'whiteNoProgress is array');
    assert(state.whiteNoProgress.length === 4, 'whiteNoProgress length = 4');
    assert(State.CUTOFFS_FOR_DRAW.length === 4, 'CUTOFFS_FOR_DRAW length = 4');
    assert(State.CUTOFFS_FOR_DRAW[0] === 2, 'Cutoff[0] = 2');
    assert(State.CUTOFFS_FOR_DRAW[1] === 8, 'Cutoff[1] = 8');
    assert(State.CUTOFFS_FOR_DRAW[2] === 20, 'Cutoff[2] = 20');
    assert(State.CUTOFFS_FOR_DRAW[3] === 40, 'Cutoff[3] = 40');
    assert(!state.colorIsStagnated(C.COLOR_WHITE), 'White not stagnated');
    assert(!state.colorIsStagnated(C.COLOR_BLACK), 'Black not stagnated');

    // Test 18: beginOwnTurnScript — pre-built Tarsier produces attack
    // (Tesla Tower is base set, so we add it to initCards instead of randomizer)
    console.log('\nTest 18: beginOwnTurnScript — Tarsier attack production');
    const library2 = loadCardLibrary();
    const mergedDeck2 = buildMergedDeck([], library2);
    const baseNames2 = ['Drone', 'Engineer', 'Conduit', 'Brooder', 'Academy',
        'Wall', 'Treant', 'Elephant', 'Tesla Tower', 'Blood Barrier', 'Minicannon'];
    const laneInfo2 = [{
        initResources: ['6', '7'],
        base: [baseNames2, baseNames2],
        randomizer: [[], []],
        initCards: [
            [[6, 'Drone'], [2, 'Engineer'], [1, 'Tesla Tower']],
            [[7, 'Drone'], [2, 'Engineer']]
        ]
    }];
    const scriptInfo2 = { whiteStarts: true };
    const state2 = new State(laneInfo2, mergedDeck2, scriptInfo2, null, -1, -1);

    // Verify Tarsier exists in white's units
    let tarsInst = null;
    state2.table.forEach((inst) => {
        if (inst.cardName === 'Tesla Tower' && inst.owner === C.COLOR_WHITE) {
            tarsInst = inst;
        }
    });
    assert(tarsInst !== null, 'White has a Tarsier (Tesla Tower)');
    assert(tarsInst.constructionTime === 0, 'Tarsier already built (from initCards)');

    // White turn 0: no attack yet (beginOwnTurnScript hasn't run — no swoosh before first turn)
    assert(state2.turnMana.attack === 0, `White attack = 0 at start (got ${state2.turnMana.attack})`);

    // End white turn
    state2.processMove(C.MOVE_ENTER_CONFIRM);
    state2.processMove(C.MOVE_COMMIT);

    // Black turn — end it
    state2.processMove(C.MOVE_ENTER_CONFIRM);
    state2.processMove(C.MOVE_COMMIT);

    // White turn 2: swoosh ran beginOwnTurnScript → Tarsier produces 1 attack
    assert(state2.turnMana.attack >= 1, `White attack ≥ 1 after swoosh (got ${state2.turnMana.attack})`);

    // Test 19: Lookups
    console.log('\nTest 19: Lookups');
    assert(state.cardNameToCard('Drone') !== null, 'cardNameToCard(Drone) works');
    assert(state.cardNameToCard('Drone').UIName === 'Drone', 'Drone UIName');
    assert(state.cardIdToCard(droneId).cardName === 'Drone', 'cardIdToCard works');
    assert(state.playerMana(C.COLOR_WHITE) === state.whiteMana, 'playerMana(white)');
    assert(state.playerMana(C.COLOR_BLACK) === state.blackMana, 'playerMana(black)');

    // Test 20: Instance queries
    console.log('\nTest 20: Instance queries');
    const whiteDroneList = state.allCardsOfColorWithName(C.COLOR_WHITE, 'Drone', false, false, false);
    assert(whiteDroneList.length >= 6, `White has ≥6 Drones (got ${whiteDroneList.length})`);
    assert(!state.hasAssigned(C.COLOR_WHITE, 'Drone'), 'No white Drones assigned (refreshed by swoosh)');
    assert(state.hasUnassigned(C.COLOR_WHITE, 'Drone'), 'White has unassigned Drones');

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) process.exit(1);
}

main();
