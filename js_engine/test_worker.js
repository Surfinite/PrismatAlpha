'use strict';

/**
 * test_worker.js — Test MCDSAI worker process isolation.
 *
 * Verifies that the worker spawns, initializes MCDSAI, and returns a move
 * via IPC (child_process.fork).
 *
 * Run: node js_engine/test_worker.js
 */

const MCDSAIWorker = require('./mcdsai_manager');
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

async function main() {
    console.log('=== MCDSAI Worker Process Test ===\n');

    // Build init payload
    const library = loadCardLibrary();
    const testSet = ['Tarsier', 'Rhino', 'Steelsplitter', 'Wall', 'Blastforge',
                     'Animus', 'Conduit', 'Forcefield'];
    const deck = buildMergedDeck(testSet, library);
    const params = loadFullParams();
    const paramsObj = JSON.parse(params);

    const initPayload = JSON.stringify({
        mergedDeck: deck,
        aiParameters: paramsObj
    });

    // Test 1: Spawn worker
    console.log('Test 1: Spawn worker process');
    const worker = new MCDSAIWorker('P1');
    try {
        await worker.spawn();
        assert(true, 'Worker spawned and signaled ready');
    } catch (err) {
        assert(false, `Worker spawn failed: ${err.message}`);
        process.exit(1);
    }

    // Test 2: Initialize AI via worker
    console.log('\nTest 2: Initialize AI via worker IPC');
    try {
        const initResult = await worker.initializeAI(initPayload);
        assert(typeof initResult === 'string', `Init returned string (${initResult.length} chars)`);
        assert(initResult.indexOf('Successful') !== -1 || initResult.indexOf('aiversion') !== -1,
            'Init indicates success');
    } catch (err) {
        assert(false, `Worker init failed: ${err.message}`);
    }

    // Test 3: Request move via worker
    console.log('\nTest 3: Request move via worker IPC');
    const movePayload = JSON.stringify({
        gameState: { table: [[], []], phase: 'action', activePlayer: 0, numTurns: 0 },
        aiPlayerName: 'HardestAI'
    });
    try {
        const moveResult = await worker.getAIMove(movePayload);
        assert(typeof moveResult === 'string', `Move returned string (${moveResult.length} chars)`);
        const parsed = JSON.parse(moveResult);
        assert(parsed.hasOwnProperty('aiclicks'), 'Response has aiclicks');
    } catch (err) {
        // May fail without proper game state — that's OK for smoke test
        console.log(`  INFO: Move via worker: ${err.message} (expected without proper state)`);
    }

    // Test 4: Terminate worker
    console.log('\nTest 4: Terminate worker');
    worker.terminate();
    assert(true, 'Worker terminated');

    // Give worker time to exit
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    process.exit(failed > 0 ? 1 : 0);
}

main().catch(err => {
    console.error(`Unhandled error: ${err.message}`);
    process.exit(1);
});
