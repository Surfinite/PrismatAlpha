'use strict';

/**
 * test_tier1.js — Unit tests for all Tier 1 data classes.
 *
 * Tests:
 * 1. C.js constants
 * 2. Click.js construction
 * 3. ClickResult.js construction
 * 4. Order.js construction + inverse
 * 5. Mana.js string round-trip + arithmetic
 * 6. SacDescription.js construction
 * 7. CreateDescription.js construction
 * 8. Script.js construction
 * 9. Rndm.js sequence determinism
 * 10. Mana round-trip for all 161 cardLibrary buyCosts
 *
 * Run: node js_engine/test_tier1.js
 */

const C = require('./C');
const Click = require('./Click');
const ClickResult = require('./ClickResult');
const Order = require('./Order');
const Mana = require('./Mana');
const SacDescription = require('./SacDescription');
const CreateDescription = require('./CreateDescription');
const Script = require('./Script');
const Rndm = require('./Rndm');
const { loadCardLibrary } = require('./card_library');

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

function main() {
    console.log('=== Tier 1 Data Class Tests ===\n');

    // Test 1: C.js constants
    console.log('Test 1: C.js constants');
    assert(C.CLICK_INST === 'inst clicked', 'CLICK_INST value');
    assert(C.CLICK_CARD === 'card clicked', 'CLICK_CARD value');
    assert(C.CLICK_SPACE === 'space clicked', 'CLICK_SPACE value');
    assert(C.MANA_P === 0, 'MANA_P = 0 (gold)');
    assert(C.MANA_G === 1, 'MANA_G = 1 (green)');
    assert(C.MANA_B === 2, 'MANA_B = 2 (blue)');
    assert(C.MANA_R === 3, 'MANA_R = 3 (red)');
    assert(C.MANA_H === 4, 'MANA_H = 4 (energy)');
    assert(C.MANA_A === 5, 'MANA_A = 5 (attack)');
    assert(C.MANA_NUMBER_OF === 6, 'MANA_NUMBER_OF = 6');
    assert(C.PHASE_ACTION === 'action', 'PHASE_ACTION value');
    assert(C.PHASE_DEFENSE === 'defense', 'PHASE_DEFENSE value');
    assert(C.ROLE_DEFAULT === 'default', 'ROLE_DEFAULT value');
    assert(C.RARITY_LEGENDARY === 1, 'RARITY_LEGENDARY = 1');
    assert(C.RARITY_RARE === 4, 'RARITY_RARE = 4');
    assert(C.RARITY_NORMAL === 10, 'RARITY_NORMAL = 10');
    assert(C.RARITY_TRINKET === 20, 'RARITY_TRINKET = 20');

    // ASSERT function
    let assertThrew = false;
    try { C.ASSERT(false, 'test'); } catch (e) { assertThrew = true; }
    assert(assertThrew, 'ASSERT(false) throws');
    C.ASSERT(true, 'test');  // Should not throw
    assert(true, 'ASSERT(true) does not throw');

    // Test 2: Click.js
    console.log('\nTest 2: Click.js');
    const click1 = new Click('card clicked', 3);
    assert(click1._type === 'card clicked', 'Click type');
    assert(click1._id === 3, 'Click id');
    assert(click1._params === null, 'Click params default null');

    const click2 = new Click('inst clicked');
    assert(click2._id === -1, 'Click default id = -1');

    // Test 3: ClickResult.js
    console.log('\nTest 3: ClickResult.js');
    const cr = new ClickResult(true, true);
    assert(cr.actuallyDoClick === true, 'ClickResult actuallyDoClick');
    assert(cr.canClick === true, 'ClickResult canClick');
    assert(cr.moveResult === '', 'ClickResult moveResult empty string');
    assert(cr.serverResult === null, 'ClickResult serverResult null');
    assert(Array.isArray(cr.instsToHighlight), 'instsToHighlight is array');
    assert(ClickResult.START_OF_CHAIN === 'start of chain', 'START_OF_CHAIN constant');

    // Test 4: Order.js
    console.log('\nTest 4: Order.js');
    const order = new Order(C.MOVE_ASSIGN, 5, -1, -1);
    assert(order.type === C.MOVE_ASSIGN, 'Order type');
    assert(order.instId === 5, 'Order instId');

    const inv = order.inverse();
    assert(inv.type === C.MOVE_UNASSIGN, 'Inverse of ASSIGN = UNASSIGN');
    assert(inv.instId === 5, 'Inverse preserves instId');

    const inv2 = inv.inverse();
    assert(inv2.type === C.MOVE_ASSIGN, 'Double inverse = original');

    // All inverse pairs
    const pairs = [
        [C.MOVE_ASSIGN, C.MOVE_UNASSIGN],
        [C.MOVE_BUY, C.MOVE_SELL],
        [C.MOVE_MELEE, C.MOVE_UNMELEE],
        [C.MOVE_DEFEND, C.MOVE_UNDEFEND],
        [C.MOVE_BREACH_OR_OVERKILL, C.MOVE_UNBREACH_OR_UNOVERKILL],
        [C.MOVE_WIPEOUT, C.MOVE_UNWIPEOUT]
    ];
    for (const [a, b] of pairs) {
        assert(new Order(a).inverse().type === b, `inverse(${a}) = ${b}`);
        assert(new Order(b).inverse().type === a, `inverse(${b}) = ${a}`);
    }

    // Test 5: Mana.js
    console.log('\nTest 5: Mana.js');

    // Parse + toString round-trip
    const mana1 = new Mana('6BGGG');
    assert(mana1.money === 6, 'Mana "6BGGG" gold = 6');
    assert(mana1.pool[C.MANA_B] === 1, 'Mana "6BGGG" blue = 1');
    assert(mana1.pool[C.MANA_G] === 3, 'Mana "6BGGG" green = 3');
    assert(mana1.toString() === '6GGGB', 'Mana toString order: H,G,B,C,A');
    // Note: toString outputs in order H, G, B, R(C), A — not the input order

    const mana2 = new Mana('3H');
    assert(mana2.money === 3, 'Mana "3H" gold = 3');
    assert(mana2.pool[C.MANA_H] === 1, 'Mana "3H" energy = 1');
    assert(mana2.toString() === '3H', 'Mana "3H" round-trips');

    const mana3 = new Mana('0');
    assert(mana3.money === 0, 'Mana "0" gold = 0');
    assert(mana3.isEmpty, 'Mana "0" isEmpty');
    assert(mana3.toString() === '0', 'Mana "0" round-trips');

    const mana4 = new Mana('');
    assert(mana4.isEmpty, 'Mana "" isEmpty');
    assert(mana4.toString() === '0', 'Mana "" toString = "0"');

    const mana5 = new Mana('5C');  // Red uses 'C' internally
    assert(mana5.pool[C.MANA_R] === 1, 'Mana "5C" red = 1');
    assert(mana5.toString() === '5C', 'Mana "5C" round-trips');

    // Arithmetic
    const a = new Mana('6BG');
    const b = new Mana('3G');
    assert(a.has(b), '6BG has 3G');
    a.subtract(b);
    assert(a.money === 3, 'After subtract: gold = 3');
    assert(a.pool[C.MANA_G] === 0, 'After subtract: green = 0');

    const c = new Mana('2H');
    a.add(c);
    assert(a.pool[C.MANA_H] === 1, 'After add 2H: energy = 1');
    assert(a.money === 5, 'After add 2H: gold = 5');

    // Clone
    const cloned = mana1.clone();
    assert(cloned.toString() === mana1.toString(), 'Clone preserves value');
    cloned.money = 99;
    assert(mana1.money === 6, 'Clone is independent');

    // Public facing string
    assert(new Mana('3HC').toPublicFacingString() === '3ER', 'toPublicFacingString: H→E, C→R');
    assert(new Mana('2A').toPublicFacingString() === '2X', 'toPublicFacingString: A→X');

    // hasFailedWith
    const cost = new Mana('5B');
    const pool1 = new Mana('10BBB');
    assert(pool1.hasFailedWith(cost) === -1, 'Pool has enough');
    const pool2 = new Mana('3');
    assert(pool2.hasFailedWith(cost) !== -1, 'Pool insufficient');

    // Test 6: SacDescription.js
    console.log('\nTest 6: SacDescription.js');
    const sac1 = new SacDescription(['Drone']);
    assert(sac1.cardName === 'Drone', 'SacDescription cardName');
    assert(sac1.multiplicity === 1, 'SacDescription default multiplicity');

    const sac2 = new SacDescription(['Engineer', 2]);
    assert(sac2.multiplicity === 2, 'SacDescription explicit multiplicity');

    // Test 7: CreateDescription.js
    console.log('\nTest 7: CreateDescription.js');
    const cd1 = new CreateDescription(['Pixie']);
    assert(cd1.cardName === 'Pixie', 'CreateDescription cardName');
    assert(cd1.own === true, 'CreateDescription default own');
    assert(cd1.multiplicity === 1, 'CreateDescription default multiplicity');
    assert(cd1.buildTime === 1, 'CreateDescription default buildTime');
    assert(cd1.lifespan === -1, 'CreateDescription default lifespan');
    assert(cd1.invuln === false, 'CreateDescription default invuln');

    const cd2 = new CreateDescription(['Gauss Charge', 'opponent', 3, 0, 2, 'invulnerable']);
    assert(cd2.own === false, 'CreateDescription opponent');
    assert(cd2.multiplicity === 3, 'CreateDescription multiplicity 3');
    assert(cd2.buildTime === 0, 'CreateDescription buildTime 0');
    assert(cd2.lifespan === 2, 'CreateDescription lifespan 2');
    assert(cd2.invuln === true, 'CreateDescription invulnerable');

    // Test 8: Script.js
    console.log('\nTest 8: Script.js');
    const script1 = new Script({ receive: '1' });
    assert(script1.receive.money === 1, 'Script receive gold = 1');
    assert(script1.create.length === 0, 'Script no creates');
    assert(script1.selfsac === false, 'Script default selfsac');

    const script2 = new Script({
        receive: 'A',
        create: [['Pixie', 'own', 1, 0, 1]],
        selfsac: true,
        delay: 2
    });
    assert(script2.receive.attack === 1, 'Script receive attack = 1');
    assert(script2.create.length === 1, 'Script 1 create');
    assert(script2.create[0].cardName === 'Pixie', 'Script create Pixie');
    assert(script2.selfsac === true, 'Script selfsac true');
    assert(script2.delay === 2, 'Script delay 2');

    // toPublicJSON
    const pub = script2.toPublicJSON();
    assert(pub.receive === 'X', 'Script toPublicJSON receive → X');
    assert(pub.selfsac === true, 'Script toPublicJSON selfsac');
    assert(pub.delay === 2, 'Script toPublicJSON delay');

    // Test 9: Rndm.js determinism
    console.log('\nTest 9: Rndm.js determinism');

    // Same seed produces same sequence
    const rng1 = new Rndm(42);
    const seq1 = [];
    for (let i = 0; i < 10; i++) seq1.push(rng1.random());

    const rng2 = new Rndm(42);
    const seq2 = [];
    for (let i = 0; i < 10; i++) seq2.push(rng2.random());

    let allMatch = true;
    for (let i = 0; i < 10; i++) {
        if (seq1[i] !== seq2[i]) { allMatch = false; break; }
    }
    assert(allMatch, 'Same seed → identical sequences');

    // Different seed produces different sequence
    const rng3 = new Rndm(99);
    const seq3 = [];
    for (let i = 0; i < 10; i++) seq3.push(rng3.random());
    let anyDifferent = false;
    for (let i = 0; i < 10; i++) {
        if (seq1[i] !== seq3[i]) { anyDifferent = true; break; }
    }
    assert(anyDifferent, 'Different seed → different sequences');

    // Values are in [0, 1)
    const rng4 = new Rndm(12345);
    let allInRange = true;
    for (let i = 0; i < 1000; i++) {
        const v = rng4.random();
        if (v < 0 || v >= 1) { allInRange = false; break; }
    }
    assert(allInRange, 'All random() values in [0, 1)');

    // integer() produces correct range
    const rng5 = new Rndm(777);
    let intRange = true;
    for (let i = 0; i < 1000; i++) {
        const v = rng5.integer(5, 10);
        if (v < 5 || v >= 10) { intRange = false; break; }
    }
    assert(intRange, 'integer(5,10) produces values in [5, 10)');

    // Seed reset produces same sequence (must change seed first to trigger reset)
    rng1.seed = 999;  // Change to a different seed first
    rng1.seed = 42;   // Now setting back to 42 triggers pointer reset + pixel regen
    const seq4 = [];
    for (let i = 0; i < 10; i++) seq4.push(rng1.random());
    let resetMatch = true;
    for (let i = 0; i < 10; i++) {
        if (seq1[i] !== seq4[i]) { resetMatch = false; break; }
    }
    assert(resetMatch, 'Resetting seed reproduces sequence');

    // Same-seed assignment does NOT reset pointer (AS3 Rndm.as:96)
    const rng6 = new Rndm(42);
    rng6.random(); rng6.random(); rng6.random(); // advance pointer to 3
    const ptrBefore = rng6.pointer;
    rng6.seed = 42;  // Same seed — AS3 does not reset pointer
    assert(rng6.pointer === ptrBefore, 'Same-seed assignment preserves pointer (AS3 faithful)');

    // Static singleton interface
    Rndm.seed = 42;
    const sv1 = Rndm.random();
    Rndm.seed = 999;  // Change seed first
    Rndm.seed = 42;   // Reset back triggers pointer reset
    const sv2 = Rndm.random();
    assert(sv1 === sv2, 'Static singleton produces deterministic values');

    // Test 10: Mana round-trip for all cardLibrary buyCosts
    console.log('\nTest 10: Mana round-trip for all 161 cardLibrary buyCosts');
    const library = loadCardLibrary();
    let roundTripCount = 0;
    let roundTripFail = 0;
    for (const [name, card] of library) {
        if (card.buyCost) {
            const mana = new Mana(card.buyCost);
            const rt = mana.toString();
            // Re-parse and compare
            const mana2 = new Mana(rt);
            let match = true;
            for (let i = 0; i < C.MANA_NUMBER_OF; i++) {
                if (mana.pool[i] !== mana2.pool[i]) {
                    match = false;
                    break;
                }
            }
            if (!match) {
                console.error(`    Round-trip fail: ${name} "${card.buyCost}" → "${rt}"`);
                roundTripFail++;
            }
            roundTripCount++;
        }
    }
    assert(roundTripFail === 0,
        `All ${roundTripCount} buyCost strings round-trip successfully`);

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) process.exit(1);
}

main();
