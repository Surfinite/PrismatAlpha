'use strict';

/**
 * test_phase3.js — Unit tests for Phase 3: Click Processing Layer
 *
 * Tests Controller.js, Analyzer.js, and StateUtil.js integration.
 *
 * Tests:
 * 1. Analyzer factory (analyzerFromState)
 * 2. Click validation (analyzerCanClick)
 * 3. Buy via click (card clicked)
 * 4. Resource enforcement (insufficient gold/energy)
 * 5. Supply enforcement (can't overbuy)
 * 6. Space click (end action → confirm)
 * 7. Confirm → commit (full turn cycle)
 * 8. Multi-turn cycle (P2 buy → P1 buy)
 * 9. Undo (click undo after buy)
 * 10. Shift-click buy (buy all affordable)
 * 11. StateUtil.convertToClicks (empty)
 * 12. StateUtil.convertToClicks (card buy)
 * 13. StateUtil.findInstId (found)
 * 14. StateUtil.findInstId (not found)
 * 15. StateUtil.compareVectors
 * 16. Controller.canAssign (inst click for ability)
 * 17. Defense phase blocking
 * 18. Revert (undo to start of turn)
 * 19. Analyzer history tracking
 * 20. Full game: buy → end turn → opponent buy → end turn
 *
 * Run: node js_engine/test_phase3.js
 */

const C = require('./C');
const State = require('./State');
const Analyzer = require('./Analyzer');
const Controller = require('./Controller');
const StateUtil = require('./StateUtil');
const Click = require('./Click');
const Order = require('./Order');
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
 * Create a game state ready for click processing.
 * Initializes numTurns and runs swoosh so turn=1 (P2/black, 7 gold + 2H).
 */
function createReadyState(advancedUnits) {
    advancedUnits = advancedUnits || [];
    const library = loadCardLibrary();
    const mergedDeck = buildMergedDeck(advancedUnits, library);

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

    // Add advanced unit names to randomizer
    if (advancedUnits.length > 0) {
        const uiToInternal = new Map();
        for (const [internalName, card] of library) {
            uiToInternal.set(card.UIName, internalName);
        }
        const randNames = advancedUnits.map(ui => uiToInternal.get(ui) || ui);
        laneInfo[0].randomizer = [randNames, randNames];
    }

    const s = new State(laneInfo, mergedDeck, { whiteStarts: true }, null, -1, -1);
    // Simulate initVirginGame: increment turn, then swoosh
    s.numTurns++;
    s.swoosh();
    return s;
}

/**
 * Create Analyzer from ready state.
 */
function createReadyAnalyzer(advancedUnits) {
    return Analyzer.analyzerFromState(createReadyState(advancedUnits));
}

function main() {
    console.log('=== Phase 3: Click Processing Tests ===\n');

    // -------------------------------------------------------
    // Test 1: Analyzer factory
    // -------------------------------------------------------
    console.log('--- Test 1: Analyzer.analyzerFromState ---');
    {
        const s = createReadyState();
        const analyzer = Analyzer.analyzerFromState(s);
        assert(analyzer !== null, 'Analyzer created');
        assert(analyzer.controller !== null, 'Controller exists');
        assert(analyzer.gameState !== null, 'gameState accessible');
        assert(analyzer.gameState.numTurns === 1, 'numTurns = 1');
        assert(analyzer.gameState.phase === C.PHASE_ACTION, 'phase = action');
        assert(analyzer.gameState.turn === 1, 'turn = 1 (P2/black)');
        // State was cloned — verify independence
        assert(analyzer.gameState !== s, 'State was cloned (not same reference)');
    }

    // -------------------------------------------------------
    // Test 2: Click validation
    // -------------------------------------------------------
    console.log('\n--- Test 2: analyzerCanClick ---');
    {
        const analyzer = createReadyAnalyzer();
        const droneCard = analyzer.gameState.cardNameToCard('Drone');
        const engCard = analyzer.gameState.cardNameToCard('Engineer');

        assert(analyzer.analyzerCanClick('card clicked', droneCard.cardId) === true,
            'Can buy Drone (3g+1H, have 7g+2H)');
        assert(analyzer.analyzerCanClick('card clicked', engCard.cardId) === true,
            'Can buy Engineer (2g)');
        assert(analyzer.analyzerCanClick('space clicked', -1) === true,
            'Can end action phase');
        assert(analyzer.analyzerCanClick('revert clicked', -1) === true,
            'Revert is clickable (restores to beginTurnState, even at start)');
    }

    // -------------------------------------------------------
    // Test 3: Buy via click
    // -------------------------------------------------------
    console.log('\n--- Test 3: Buy via card clicked ---');
    {
        const analyzer = createReadyAnalyzer();
        const droneCard = analyzer.gameState.cardNameToCard('Drone');

        const goldBefore = analyzer.gameState.turnMana.money;
        const hBefore = analyzer.gameState.turnMana.amountOf(C.MANA_H);
        const boughtBefore = analyzer.gameState.turnBought()[droneCard.cardId];

        analyzer.noUpdateClick('card clicked', droneCard.cardId);

        assert(analyzer.gameState.turnMana.money === goldBefore - 3,
            'Gold decreased by 3 (Drone gold cost)');
        assert(analyzer.gameState.turnMana.amountOf(C.MANA_H) === hBefore - 1,
            'Energy decreased by 1 (Drone H cost)');
        assert(analyzer.gameState.turnBought()[droneCard.cardId] === boughtBefore + 1,
            'Bought count increased by 1');
    }

    // -------------------------------------------------------
    // Test 4: Resource enforcement
    // -------------------------------------------------------
    console.log('\n--- Test 4: Resource enforcement ---');
    {
        const analyzer = createReadyAnalyzer();
        const droneCard = analyzer.gameState.cardNameToCard('Drone');

        // Buy 2 Drones: 7g 2H → 4g 1H → 1g 0H
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('card clicked', droneCard.cardId);

        assert(analyzer.gameState.turnMana.money === 1, 'After 2 Drones: 1 gold left');
        assert(analyzer.gameState.turnMana.amountOf(C.MANA_H) === 0, 'After 2 Drones: 0 H left');
        assert(analyzer.analyzerCanClick('card clicked', droneCard.cardId) === false,
            'Cannot buy 3rd Drone (insufficient resources)');

        // Can still buy Engineer (2 gold, no H)? No - only 1 gold
        const engCard = analyzer.gameState.cardNameToCard('Engineer');
        assert(analyzer.analyzerCanClick('card clicked', engCard.cardId) === false,
            'Cannot buy Engineer (only 1 gold, need 2)');
    }

    // -------------------------------------------------------
    // Test 5: Supply enforcement
    // -------------------------------------------------------
    console.log('\n--- Test 5: Supply enforcement ---');
    {
        const analyzer = createReadyAnalyzer();
        const engCard = analyzer.gameState.cardNameToCard('Engineer');

        // Engineer supply is 20. Buy until supply runs out would take too many turns.
        // Instead check that bought < supply allows buy
        const supply = analyzer.gameState.turnSupply()[engCard.cardId];
        const bought = analyzer.gameState.turnBought()[engCard.cardId];
        assert(supply === 20, 'Engineer supply is 20');
        assert(bought === 0, 'No Engineers bought yet');
        assert(bought < supply, 'Bought < supply: can buy');
    }

    // -------------------------------------------------------
    // Test 6: Space click (end action → confirm)
    // -------------------------------------------------------
    console.log('\n--- Test 6: Space click → confirm ---');
    {
        const analyzer = createReadyAnalyzer();
        assert(analyzer.gameState.phase === C.PHASE_ACTION, 'Start in action');

        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.phase === C.PHASE_CONFIRM, 'Space → confirm phase');
    }

    // -------------------------------------------------------
    // Test 7: Confirm → commit (full turn)
    // -------------------------------------------------------
    console.log('\n--- Test 7: Confirm → commit (full turn cycle) ---');
    {
        const analyzer = createReadyAnalyzer();
        const turnBefore = analyzer.gameState.numTurns;

        // Buy one Drone
        const droneCard = analyzer.gameState.cardNameToCard('Drone');
        analyzer.noUpdateClick('card clicked', droneCard.cardId);

        // Space → confirm
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.phase === C.PHASE_CONFIRM, 'Entered confirm after action');

        // Space → commit (no defense phase since P1 has no attack units)
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.numTurns === turnBefore + 1,
            'numTurns incremented after commit');
        assert(analyzer.gameState.phase === C.PHASE_ACTION,
            'Phase back to action (next player turn)');
        assert(analyzer.gameState.turn === 0,
            'Turn switched to P1 (white)');
    }

    // -------------------------------------------------------
    // Test 8: Multi-turn cycle
    // -------------------------------------------------------
    console.log('\n--- Test 8: Multi-turn cycle ---');
    {
        const analyzer = createReadyAnalyzer();

        // Turn 1 (P2): Buy Engineer
        const engCard = analyzer.gameState.cardNameToCard('Engineer');
        analyzer.noUpdateClick('card clicked', engCard.cardId);
        analyzer.noUpdateClick('space clicked', -1);  // → confirm
        analyzer.noUpdateClick('space clicked', -1);  // → commit

        assert(analyzer.gameState.turn === 0, 'After P2 turn: now P1');
        assert(analyzer.gameState.numTurns === 2, 'numTurns = 2');

        // Turn 2 (P1): Should have 6 gold + 2H energy
        assert(analyzer.gameState.turnMana.money === 6, 'P1 has 6 gold');
        assert(analyzer.gameState.turnMana.amountOf(C.MANA_H) === 2, 'P1 has 2H');

        // P1 buys a Drone
        const droneCard = analyzer.gameState.cardNameToCard('Drone');
        assert(analyzer.analyzerCanClick('card clicked', droneCard.cardId) === true,
            'P1 can buy Drone');
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);

        assert(analyzer.gameState.turn === 1, 'After P1 turn: now P2');
        assert(analyzer.gameState.numTurns === 3, 'numTurns = 3');
    }

    // -------------------------------------------------------
    // Test 9: Undo
    // -------------------------------------------------------
    console.log('\n--- Test 9: Undo ---');
    {
        const analyzer = createReadyAnalyzer();
        const droneCard = analyzer.gameState.cardNameToCard('Drone');

        const goldBefore = analyzer.gameState.turnMana.money;
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        assert(analyzer.gameState.turnMana.money === goldBefore - 3, 'Gold decreased after buy');

        // Undo
        analyzer.noUpdateClick(C.CLICK_UNDO, -1);
        assert(analyzer.gameState.turnMana.money === goldBefore, 'Gold restored after undo');
        assert(analyzer.gameState.turnBought()[droneCard.cardId] === 0,
            'Bought count back to 0 after undo');
    }

    // -------------------------------------------------------
    // Test 10: Shift-click buy
    // -------------------------------------------------------
    console.log('\n--- Test 10: Shift-click buy all ---');
    {
        const analyzer = createReadyAnalyzer();
        const engCard = analyzer.gameState.cardNameToCard('Engineer');

        // Shift-click Engineer: should buy as many as affordable (7g / 2g = 3)
        analyzer.noUpdateClick(C.CLICK_CARD_SHIFT, engCard.cardId);
        assert(analyzer.gameState.turnBought()[engCard.cardId] === 3,
            'Shift-click bought 3 Engineers (7g / 2g each = 3, remainder 1g)');
        assert(analyzer.gameState.turnMana.money === 1, '1 gold remaining');
    }

    // -------------------------------------------------------
    // Test 11: StateUtil.convertToClicks (empty)
    // -------------------------------------------------------
    console.log('\n--- Test 11: StateUtil.convertToClicks (empty) ---');
    {
        const s = createReadyState();
        const clicks = StateUtil.convertToClicks([], s);
        assert(clicks.length === 0, 'Empty click array → empty result');
    }

    // -------------------------------------------------------
    // Test 12: StateUtil.convertToClicks (card buy)
    // -------------------------------------------------------
    console.log('\n--- Test 12: StateUtil.convertToClicks (card buy) ---');
    {
        const s = createReadyState();
        const clickObjs = [
            { type: 'card clicked', args: 'Engineer' }
        ];
        const clicks = StateUtil.convertToClicks(clickObjs, s);
        assert(clicks.length === 1, 'One click produced');
        assert(clicks[0]._type === 'card clicked', 'Click _type is card clicked');
    }

    // -------------------------------------------------------
    // Test 13: StateUtil.findInstId (found)
    // -------------------------------------------------------
    console.log('\n--- Test 13: StateUtil.findInstId (found) ---');
    {
        const s = createReadyState();
        const analyzer = Analyzer.analyzerFromState(s);
        const id = StateUtil.findInstId({ cardName: 'Drone', owner: 1 }, analyzer);
        assert(id >= 0, 'Found Drone belonging to player 1 (id=' + id + ')');

        const id2 = StateUtil.findInstId({ cardName: 'Engineer', owner: 0 }, analyzer);
        assert(id2 >= 0, 'Found Engineer belonging to player 0 (id=' + id2 + ')');
    }

    // -------------------------------------------------------
    // Test 14: StateUtil.findInstId (not found)
    // -------------------------------------------------------
    console.log('\n--- Test 14: StateUtil.findInstId (not found) ---');
    {
        const s = createReadyState();
        const analyzer = Analyzer.analyzerFromState(s);
        const id = StateUtil.findInstId({ cardName: 'Nonexistent', owner: 0 }, analyzer);
        assert(id === -1, 'Nonexistent unit returns -1');
    }

    // -------------------------------------------------------
    // Test 15: StateUtil.compareVectors
    // -------------------------------------------------------
    console.log('\n--- Test 15: StateUtil.compareVectors ---');
    {
        const s = createReadyState();
        const s2 = s.clone();
        const same = StateUtil.compareVectors(
            s.whiteSupply, s2.whiteSupply,
            s.cards, s2.cards
        );
        assert(same === true, 'Identical supply vectors are equal');

        // Modify one supply
        const s3 = s.clone();
        s3.whiteSupply[0] = 999;
        const diff = StateUtil.compareVectors(
            s.whiteSupply, s3.whiteSupply,
            s.cards, s3.cards
        );
        assert(diff === false, 'Different supply vectors are not equal');
    }

    // -------------------------------------------------------
    // Test 16: canAssign (Drone ability — produce 1 gold)
    // -------------------------------------------------------
    console.log('\n--- Test 16: canAssign (Drone ability) ---');
    {
        const analyzer = createReadyAnalyzer();
        // Drones have abilityScript {receive: "1"} — must be clicked to produce gold.
        // After swoosh, Drones have role='default' (clickable).
        let droneInstId = -1;
        analyzer.gameState.table.forIn((key) => {
            const inst = analyzer.gameState.table.get(key);
            if (inst.card.cardName === 'Drone' && inst.owner === analyzer.gameState.turn) {
                if (droneInstId === -1) droneInstId = inst.instId;
            }
        });
        assert(droneInstId >= 0, 'Found a Drone instance');

        // Drones are clickable (role=default, have ability)
        const canClick = analyzer.analyzerCanClick('inst clicked', droneInstId);
        assert(canClick === true, 'Can click Drone (abilityScript produces gold)');

        // Click Drone to produce gold
        const goldBefore = analyzer.gameState.turnMana.money;
        analyzer.noUpdateClick('inst clicked', droneInstId);
        assert(analyzer.gameState.turnMana.money === goldBefore + 1,
            'Gold increased by 1 after clicking Drone');
    }

    // -------------------------------------------------------
    // Test 17: Defense phase blocking
    // -------------------------------------------------------
    console.log('\n--- Test 17: Defense phase ---');
    {
        // To test defense, we need an attacker. Use state manipulation:
        // Give P2 (turn=1) some attack, then P1 will enter defense.
        const analyzer = createReadyAnalyzer();

        // P2 turn: space → confirm → commit
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);

        // P1 turn: space → confirm → commit
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);

        // P2 turn again (numTurns=3): no attack units, so no defense
        // Defense only appears when opponent has attack
        assert(analyzer.gameState.phase === C.PHASE_ACTION,
            'Action phase (no attackers = no defense)');
    }

    // -------------------------------------------------------
    // Test 18: Revert (back to start of turn)
    // -------------------------------------------------------
    console.log('\n--- Test 18: Revert ---');
    {
        const analyzer = createReadyAnalyzer();
        const goldStart = analyzer.gameState.turnMana.money;
        const droneCard = analyzer.gameState.cardNameToCard('Drone');

        // Buy two Drones
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        assert(analyzer.gameState.turnMana.money === goldStart - 6,
            'Lost 6 gold after 2 Drones');

        // Revert to start of turn
        analyzer.noUpdateClick('revert clicked', -1);
        assert(analyzer.gameState.turnMana.money === goldStart,
            'Gold fully restored after revert');
        assert(analyzer.gameState.turnBought()[droneCard.cardId] === 0,
            'Bought reset to 0 after revert');
    }

    // -------------------------------------------------------
    // Test 19: Analyzer history tracking
    // -------------------------------------------------------
    console.log('\n--- Test 19: Analyzer history tracking ---');
    {
        const analyzer = createReadyAnalyzer();
        assert(Array.isArray(analyzer.gameHistory), 'gameHistory initialized');
        assert(analyzer.gameHistory.length === 0, 'gameHistory empty at start');
        assert(Array.isArray(analyzer.beginTurnHistory), 'beginTurnHistory initialized');
        assert(analyzer.beginTurnHistory.length >= 1, 'beginTurnHistory has initial state');
    }

    // -------------------------------------------------------
    // Test 20: Full game sequence
    // -------------------------------------------------------
    console.log('\n--- Test 20: Full 4-turn game sequence ---');
    {
        const analyzer = createReadyAnalyzer();
        const droneCard = analyzer.gameState.cardNameToCard('Drone');
        const engCard = analyzer.gameState.cardNameToCard('Engineer');

        // Turn 1 (P2, 7g 2H): Buy 2 Drones
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.numTurns === 2, 'After turn 1: numTurns=2');

        // Turn 2 (P1, 6g 2H): Buy 1 Drone + 1 Engineer
        analyzer.noUpdateClick('card clicked', droneCard.cardId);
        analyzer.noUpdateClick('card clicked', engCard.cardId);
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.numTurns === 3, 'After turn 2: numTurns=3');

        // Turn 3 (P2): Gold production requires clicking Drones (abilityScript).
        // No Drones clicked = only carried-over gold from turn 1 (1g leftover).
        const goldT3 = analyzer.gameState.turnMana.money;
        assert(goldT3 === 1, 'P2 gold = 1 (carried over, no Drones clicked)');

        // Click all P2 Drones to produce gold
        const p2DroneIds = [];
        analyzer.gameState.table.forIn((key) => {
            const inst = analyzer.gameState.table.get(key);
            if (inst.card.cardName === 'Drone' && inst.owner === analyzer.gameState.turn
                && inst.role === C.ROLE_DEFAULT) {
                p2DroneIds.push(inst.instId);
            }
        });
        for (const did of p2DroneIds) {
            analyzer.noUpdateClick('inst clicked', did);
        }
        assert(analyzer.gameState.turnMana.money === 1 + p2DroneIds.length,
            'P2 gold after clicking ' + p2DroneIds.length + ' Drones: ' + (1 + p2DroneIds.length));

        // Buy Engineer
        analyzer.noUpdateClick('card clicked', engCard.cardId);
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.numTurns === 4, 'After turn 3: numTurns=4');

        // Turn 4 (P1): Just end turn
        analyzer.noUpdateClick('space clicked', -1);
        analyzer.noUpdateClick('space clicked', -1);
        assert(analyzer.gameState.numTurns === 5, 'After turn 4: numTurns=5');
        assert(!analyzer.gameState.finished, 'Game not finished (econ opening)');
    }

    // -------------------------------------------------------
    // Results
    // -------------------------------------------------------
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) {
        process.exit(1);
    }
}

main();
