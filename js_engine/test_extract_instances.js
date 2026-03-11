'use strict';

/**
 * test_extract_instances.js — Unit tests for instToRichUnit() in state_adapter.js.
 *
 * Uses plain mock objects rather than real Inst/Card instances to test the
 * feature extraction logic in isolation.
 *
 * Properties accessed by instToRichUnit():
 *   inst.card.UIName, inst.card.startingHealth, inst.card.fragile
 *   inst.constructionTime, inst.delay, inst.health, inst.damage
 *   inst.blocking, inst.role, inst.owner, inst.disruptDamage
 *   inst.lifespan, inst.charge
 */

const C = require('./C');
const { _instToRichUnit: instToRichUnit } = require('./state_adapter');

let passed = 0;
let failed = 0;

function assert(condition, testName, detail) {
    if (condition) {
        console.log(`  PASS: ${testName}`);
        passed++;
    } else {
        console.error(`  FAIL: ${testName}${detail ? ' — ' + detail : ''}`);
        failed++;
    }
}

function assertEqual(actual, expected, testName) {
    if (actual === expected) {
        console.log(`  PASS: ${testName}`);
        passed++;
    } else {
        console.error(`  FAIL: ${testName} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
        failed++;
    }
}

function makeInst(overrides) {
    // Sensible defaults for a healthy, ready, non-special unit
    const defaults = {
        card: {
            UIName: 'Drone',
            startingHealth: 1,
            fragile: false
        },
        owner:           0,
        constructionTime: 0,
        delay:           0,
        health:          1,
        damage:          0,
        blocking:        false,
        role:            C.ROLE_DEFAULT,
        disruptDamage:   0,
        lifespan:        -1,   // permanent
        charge:          0
    };
    // Deep merge card overrides
    const inst = Object.assign({}, defaults, overrides);
    if (overrides && overrides.card) {
        inst.card = Object.assign({}, defaults.card, overrides.card);
    }
    return inst;
}

// ---------------------------------------------------------------------------
// Test 1: Fresh Drone (ready, healthy, no special state)
// ---------------------------------------------------------------------------
console.log('\nTest 1: Fresh Drone (ready, healthy, no special state)');
{
    const inst = makeInst({
        card: { UIName: 'Drone', startingHealth: 1, fragile: false },
        owner: 0,
        health: 1,
        damage: 0,
        lifespan: -1,   // permanent
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,               'Drone', 'name');
    assertEqual(result.owner,              0,       'owner');
    assertEqual(result.is_constructing,    0,       'is_constructing');
    assertEqual(result.turns_until_ready,  0,       'turns_until_ready');
    assertEqual(result.is_blocking,        0,       'is_blocking');
    assertEqual(result.ability_used,       0,       'ability_used');
    assertEqual(result.current_hp,         1,       'current_hp');
    assertEqual(result.hp_fraction,        1,       'hp_fraction');
    assertEqual(result.is_frozen,          0,       'is_frozen');
    assertEqual(result.lifespan_remaining, 0,       'lifespan_remaining (permanent → 0)');
    assertEqual(result.stamina_remaining,  0,       'stamina_remaining');
}

// ---------------------------------------------------------------------------
// Test 2: Constructing Tarsier (buildTime=2, constructionTime=2)
// ---------------------------------------------------------------------------
console.log('\nTest 2: Constructing Tarsier (constructionTime=2)');
{
    const inst = makeInst({
        card: { UIName: 'Tarsier', startingHealth: 1, fragile: false },
        owner: 1,
        constructionTime: 2,
        delay: 0,
        health: 1,
        damage: 0,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,              'Tarsier', 'name');
    assertEqual(result.owner,             1,         'owner');
    assertEqual(result.is_constructing,   1,         'is_constructing');
    assertEqual(result.turns_until_ready, 2,         'turns_until_ready');
    assertEqual(result.is_blocking,       0,         'is_blocking');
    assertEqual(result.ability_used,      0,         'ability_used');
}

// ---------------------------------------------------------------------------
// Test 3: Frozen Wall (disruptDamage > 0)
// ---------------------------------------------------------------------------
console.log('\nTest 3: Frozen Wall (disruptDamage=1)');
{
    const inst = makeInst({
        card: { UIName: 'Wall', startingHealth: 3, fragile: false },
        owner: 0,
        health: 3,
        damage: 0,
        disruptDamage: 1,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,       'Wall', 'name');
    assertEqual(result.is_frozen,  1,      'is_frozen');
    // turns_until_ready comes from max(constructionTime=0, delay=0)=0, not disruptDamage
    assertEqual(result.turns_until_ready, 0, 'turns_until_ready (freeze does not affect delay)');
    assertEqual(result.current_hp,  3,    'current_hp (non-fragile: health - damage)');
    assertEqual(result.hp_fraction, 1,    'hp_fraction');
}

// ---------------------------------------------------------------------------
// Test 4: Iso Kronus with delay=2 (cycle timer)
// ---------------------------------------------------------------------------
console.log('\nTest 4: Iso Kronus with delay=2 (cycle timer / ability exhaust)');
{
    const inst = makeInst({
        card: { UIName: 'Iso Kronus', startingHealth: 1, fragile: false },
        owner: 0,
        constructionTime: 0,
        delay: 2,
        health: 1,
        damage: 0,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,              'Iso Kronus', 'name');
    assertEqual(result.is_constructing,   0,            'is_constructing (delay≠constructionTime)');
    assertEqual(result.turns_until_ready, 2,            'turns_until_ready (delay=2)');
}

// ---------------------------------------------------------------------------
// Test 5: Fragile unit (Zemora) with health=15 of 20 (damaged)
// ---------------------------------------------------------------------------
console.log('\nTest 5: Fragile Zemora Voidbringer (health=15, startingHealth=20)');
{
    const inst = makeInst({
        card: { UIName: 'Zemora Voidbringer', startingHealth: 20, fragile: true },
        owner: 1,
        health: 15,   // for fragile: health IS the remaining HP
        damage: 0,    // damage field unused for fragile
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,        'Zemora Voidbringer', 'name');
    assertEqual(result.current_hp,  15,                   'current_hp (fragile: uses health directly)');
    assert(
        Math.abs(result.hp_fraction - 15/20) < 1e-9,
        'hp_fraction ≈ 0.75',
        `got ${result.hp_fraction}`
    );
}

// ---------------------------------------------------------------------------
// Test 6: Forcefield with lifespan=2
// ---------------------------------------------------------------------------
console.log('\nTest 6: Forcefield with lifespan=2');
{
    const inst = makeInst({
        card: { UIName: 'Forcefield', startingHealth: 5, fragile: false },
        owner: 0,
        health: 5,
        damage: 0,
        lifespan: 2,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.name,               'Forcefield', 'name');
    assertEqual(result.lifespan_remaining, 2,            'lifespan_remaining');
}

// ---------------------------------------------------------------------------
// Test 7: Dead unit — instToRichUnit is not responsible for filtering, but
// we verify the function still runs without crashing on a dead-ish inst.
// (In real usage, callers skip dead units before calling this function.)
// ---------------------------------------------------------------------------
console.log('\nTest 7: Unit with 0 health and damage (should not crash; caller filters dead)');
{
    const inst = makeInst({
        card: { UIName: 'Wall', startingHealth: 3, fragile: false },
        owner: 0,
        health: 0,
        damage: 0,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    // current_hp clamped to 0 via Math.max(0, ...)
    assertEqual(result.current_hp,  0, 'current_hp clamped to 0');
    assertEqual(result.hp_fraction, 0, 'hp_fraction clamped to 0');
    assert(result !== null && result !== undefined, 'no crash on zero-health unit');
}

// ---------------------------------------------------------------------------
// Bonus Test 8: Unit with ability used (role=assigned, not blocking)
// ---------------------------------------------------------------------------
console.log('\nTest 8: Gauss Cannon that used its ability (role=assigned, blocking=false)');
{
    const inst = makeInst({
        card: { UIName: 'Gauss Cannon', startingHealth: 1, fragile: false },
        owner: 0,
        role: C.ROLE_ASSIGNED,
        blocking: false,
        health: 1,
        damage: 0,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.ability_used, 1, 'ability_used (assigned, not blocking)');
    assertEqual(result.is_blocking,  0, 'is_blocking (false even though assigned)');
}

// ---------------------------------------------------------------------------
// Bonus Test 9: Blocking Wall (role=assigned, blocking=true)
// ---------------------------------------------------------------------------
console.log('\nTest 9: Wall assigned as blocker (role=assigned, blocking=true)');
{
    const inst = makeInst({
        card: { UIName: 'Wall', startingHealth: 3, fragile: false },
        owner: 0,
        role: C.ROLE_ASSIGNED,
        blocking: true,
        health: 3,
        damage: 0,
        lifespan: -1,
        charge: 0
    });
    const result = instToRichUnit(inst);
    assertEqual(result.is_blocking,  1, 'is_blocking (assigned + blocking)');
    assertEqual(result.ability_used, 0, 'ability_used (blocking, not ability)');
}

// ---------------------------------------------------------------------------
// Bonus Test 10: Unit with stamina/charge (e.g., Plasmafier)
// ---------------------------------------------------------------------------
console.log('\nTest 10: Plasmafier with charge=2');
{
    const inst = makeInst({
        card: { UIName: 'Plasmafier', startingHealth: 1, fragile: false },
        owner: 1,
        health: 1,
        damage: 0,
        charge: 2,
        lifespan: -1
    });
    const result = instToRichUnit(inst);
    assertEqual(result.stamina_remaining, 2, 'stamina_remaining (charge=2)');
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log(`\n${'='.repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed === 0) {
    console.log('All tests passed.');
} else {
    console.error(`${failed} test(s) FAILED.`);
    process.exit(1);
}
