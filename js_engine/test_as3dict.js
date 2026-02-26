'use strict';

/**
 * test_as3dict.js — Unit tests for AS3Dictionary wrapper.
 *
 * Run: node js_engine/test_as3dict.js
 */

const AS3Dictionary = require('./AS3Dictionary');

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
    console.log('=== AS3Dictionary Tests ===\n');

    // Test 1: Basic set/get
    console.log('Test 1: Basic operations');
    const dict = new AS3Dictionary();
    dict.set('a', 1);
    dict.set('b', 2);
    dict.set('c', 3);
    assert(dict.get('a') === 1, 'get("a") === 1');
    assert(dict.get('b') === 2, 'get("b") === 2');
    assert(dict.get('c') === 3, 'get("c") === 3');
    assert(dict.get('d') === null, 'get("d") === null (not found → null, not undefined)');
    assert(dict.length === 3, 'length === 3');

    // Test 2: Insertion order preservation
    console.log('\nTest 2: Insertion order');
    const keys = [];
    dict.forIn((key) => keys.push(key));
    assert(keys[0] === 'a' && keys[1] === 'b' && keys[2] === 'c',
        'forIn iterates in insertion order: a, b, c');

    const values = [];
    dict.forEach((val) => values.push(val));
    assert(values[0] === 1 && values[1] === 2 && values[2] === 3,
        'forEach iterates values in insertion order: 1, 2, 3');

    // Test 3: has/delete
    console.log('\nTest 3: has/delete');
    assert(dict.has('a') === true, 'has("a") === true');
    assert(dict.has('z') === false, 'has("z") === false');
    dict.delete('b');
    assert(dict.has('b') === false, 'After delete("b"), has("b") === false');
    assert(dict.length === 2, 'length === 2 after delete');

    // Test 4: Order preserved after delete + insert
    console.log('\nTest 4: Order after delete + insert');
    dict.set('d', 4);
    const keys2 = [];
    dict.forIn((key) => keys2.push(key));
    assert(keys2.join(',') === 'a,c,d',
        'After delete(b) + set(d): order is a,c,d');

    // Test 5: Overwrite preserves position
    console.log('\nTest 5: Overwrite preserves position');
    dict.set('a', 99);
    const keys3 = [];
    dict.forIn((key) => keys3.push(key));
    assert(keys3[0] === 'a', 'Overwriting "a" preserves its position at index 0');
    assert(dict.get('a') === 99, 'Value updated to 99');

    // Test 6: Null values
    console.log('\nTest 6: Null values (AS3 null convention)');
    dict.set('nullKey', null);
    assert(dict.has('nullKey') === true, 'has("nullKey") === true');
    assert(dict.get('nullKey') === null, 'get("nullKey") === null');

    // Test 7: Integer keys
    console.log('\nTest 7: Integer keys');
    const intDict = new AS3Dictionary();
    intDict.set(0, 'zero');
    intDict.set(1, 'one');
    intDict.set(2, 'two');
    assert(intDict.get(0) === 'zero', 'Integer key 0 works');
    assert(intDict.get(1) === 'one', 'Integer key 1 works');

    // Test 8: fromObject
    console.log('\nTest 8: fromObject / toObject');
    const obj = { x: 10, y: 20, z: 30 };
    const dict2 = AS3Dictionary.fromObject(obj);
    assert(dict2.length === 3, 'fromObject creates dict with 3 entries');
    assert(dict2.get('x') === 10, 'fromObject preserves values');

    const obj2 = dict2.toObject();
    assert(obj2.x === 10 && obj2.y === 20 && obj2.z === 30, 'toObject round-trips correctly');

    // Test 9: keys() / values() iterators
    console.log('\nTest 9: Iterator protocols');
    const dict3 = new AS3Dictionary();
    dict3.set('alpha', 100);
    dict3.set('beta', 200);

    const keysArr = Array.from(dict3.keys());
    assert(keysArr.length === 2 && keysArr[0] === 'alpha', 'keys() returns iterator');

    const valsArr = Array.from(dict3.values());
    assert(valsArr.length === 2 && valsArr[0] === 100, 'values() returns iterator');

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) process.exit(1);
}

main();
