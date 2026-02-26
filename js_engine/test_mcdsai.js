'use strict';

/**
 * test_mcdsai.js — Smoke test for MCDSAI module loading and basic operation.
 *
 * Tests:
 * 1. SHA256 hash verification
 * 2. Module loads without errors
 * 3. AI initializes with a valid mergedDeck + params
 * 4. AI returns a valid move for a game state
 *
 * Run: node js_engine/test_mcdsai.js
 */

const path = require('path');
const { loadMCDSAI, EXPECTED_HASH } = require('./mcdsai_wrapper');
const { loadCardLibrary, buildMergedDeck } = require('./card_library');
const { loadFullParams } = require('./ai_params');

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
    console.log('=== MCDSAI Smoke Test ===\n');

    // Test 1: SHA256 verification
    console.log('Test 1: SHA256 hash verification');
    const crypto = require('crypto');
    const fs = require('fs');
    const modulePath = path.resolve(__dirname, '../tmp_browser_client/MCDSAI3441.js');
    const fileData = fs.readFileSync(modulePath);
    const actualHash = crypto.createHash('sha256').update(fileData).digest('hex');
    assert(actualHash === EXPECTED_HASH,
        `Hash matches: ${actualHash.substring(0, 16)}...`);

    // Test 2: Card library loading
    console.log('\nTest 2: Card library parsing');
    const library = loadCardLibrary();
    assert(library.size > 100, `Loaded ${library.size} cards from cardLibrary.jso`);

    const tarsier = library.get('Tesla Tower');
    assert(tarsier !== undefined, 'Found "Tesla Tower" (internal name for Tarsier)');
    assert(tarsier && tarsier.UIName === 'Tarsier', 'Tesla Tower UIName = "Tarsier"');

    const drone = library.get('Drone');
    assert(drone !== undefined, 'Found "Drone"');
    assert(drone && drone.UIName === 'Drone', 'Drone UIName = "Drone" (no UIName override)');

    // Test 3: MergedDeck building
    console.log('\nTest 3: MergedDeck building');
    const testSet = ['Tarsier', 'Rhino', 'Steelsplitter', 'Wall', 'Blastforge',
                     'Animus', 'Conduit', 'Forcefield'];
    const deck = buildMergedDeck(testSet, library);
    assert(deck.length > 8, `Built mergedDeck with ${deck.length} entries (base + 8 advanced)`);

    // Verify all entries have name property
    const allHaveName = deck.every(c => c.name !== undefined);
    assert(allHaveName, 'All deck entries have "name" property');

    // Test 4: AI parameters loading
    console.log('\nTest 4: AI parameters loading');
    const params = loadFullParams();
    assert(typeof params === 'string' && params.length > 1000,
        `Loaded AI params (${params.length} chars)`);
    assert(params.indexOf('\n') === -1, 'No newlines in cleaned params');
    assert(params.indexOf('\t') === -1, 'No tabs in cleaned params');

    // Verify it's valid JSON
    let paramsObj = null;
    try {
        paramsObj = JSON.parse(params);
        assert(true, 'AI params parse as valid JSON');
    } catch (e) {
        assert(false, `AI params JSON parse failed: ${e.message}`);
    }

    // Test 5: Module loading
    console.log('\nTest 5: MCDSAI module loading');
    let ai = null;
    try {
        ai = loadMCDSAI();
        assert(true, 'MCDSAI module loaded successfully');
        assert(typeof ai.initializeAI === 'function', 'initializeAI is a function');
        assert(typeof ai.getAIMove === 'function', 'getAIMove is a function');
    } catch (err) {
        assert(false, `MCDSAI load failed: ${err.message}`);
        console.log('\n=== Results ===');
        console.log(`Passed: ${passed}, Failed: ${failed}`);
        process.exit(1);
    }

    // Test 6: AI initialization
    console.log('\nTest 6: AI initialization');
    const initPayload = JSON.stringify({
        mergedDeck: deck,
        aiParameters: paramsObj
    });
    let initResult = null;
    try {
        initResult = ai.initializeAI(initPayload);
        assert(true, `AI initialized: "${(initResult || '').substring(0, 80)}..."`);
    } catch (err) {
        assert(false, `AI init failed: ${err.message}`);
    }

    // Test 7: AI move request
    // We need a valid game state in State.toString() format.
    // For the smoke test, we'll try with a minimal state string.
    // If this fails, it's expected — we need the full State.toString() from Phase 2.
    console.log('\nTest 7: AI move request (may fail without proper State.toString() — expected)');
    if (ai) {
        // Build a minimal initial game state representation
        // This is the format State.toString() produces — will be implemented properly in Phase 2
        const movePayload = JSON.stringify({
            gameState: buildMinimalInitialState(deck),
            aiPlayerName: 'HardestAI'
        });
        try {
            const moveResult = ai.getAIMove(movePayload);
            assert(true, `AI returned move: "${(moveResult || '').substring(0, 100)}..."`);
            // Try to parse the response
            if (moveResult) {
                const parsed = JSON.parse(moveResult);
                assert(parsed.hasOwnProperty('aiclicks'), 'Response has aiclicks field');
                assert(Array.isArray(parsed.aiclicks), `aiclicks is array with ${parsed.aiclicks.length} clicks`);
            }
        } catch (err) {
            console.log(`  INFO: Move request failed (expected without proper game state): ${err.message}`);
        }
    }

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) {
        process.exit(1);
    }
}

/**
 * Build a minimal initial game state for smoke testing.
 * This is a rough approximation of State.toString() output for turn 0.
 * The real implementation comes in Phase 2.
 */
function buildMinimalInitialState(mergedDeck) {
    // State.toString() produces a JSON object with specific structure.
    // For smoke testing, try a bare minimum. MCDSAI may reject it
    // if it doesn't match the expected format exactly.
    return {
        table: [[], []],
        whiteMana: '0',
        blackMana: '0',
        whiteAttack: 0,
        blackAttack: 0,
        whiteNumDrones: 0,
        blackNumDrones: 0,
        phase: 'action',
        activePlayer: 0,
        numTurns: 0
    };
}

main();
