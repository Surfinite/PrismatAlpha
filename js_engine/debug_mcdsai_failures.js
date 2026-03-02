'use strict';

/**
 * debug_mcdsai_failures.js — Diagnostic script to investigate MCDSAI 0-click failures.
 *
 * Runs many games with MCDSAI only (no C++ player), testing just the first MCDSAI move.
 * Logs card sets, MCDSAI response, and any debug output for failures.
 */

const path = require('path');
const fs = require('fs');

// Suppress Emscripten output
if (typeof globalThis.Module === 'undefined') globalThis.Module = {};
globalThis.Module.print = function() {};
globalThis.Module.printErr = function() {};

const { loadMCDSAI } = require('./mcdsai_wrapper');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const Analyzer = require('./Analyzer');
const C = require('./C');

function buildGameInitInfo(mergedDeck) {
    const base = [];
    const randomizer = [];
    for (const card of mergedDeck) {
        const supply = card.supply !== undefined ? card.supply : 20;
        if (card.baseSet) {
            base.push([card.name, supply]);
        } else {
            randomizer.push([card.name, supply]);
        }
    }
    const laneInfo = [{
        initResources: ['0', '0'],
        base: [base, base],
        randomizer: [randomizer, randomizer],
        initCards: [
            [[6, 'Drone'], [2, 'Engineer']],
            [[7, 'Drone'], [2, 'Engineer']]
        ]
    }];
    return {
        laneInfo:      laneInfo,
        mergedDeck:    mergedDeck,
        scriptInfo:    { whiteStarts: true },
        objectiveInfo: null,
        commandInfo:   null
    };
}

async function main() {
    const NUM_TRIALS = 200;

    const library = loadCardLibrary();
    const fullParams = loadFullParams();
    const shortParams = loadShortParams();

    console.error('Loading MCDSAI directly (no worker)...');
    const ai = loadMCDSAI({ skipHashCheck: true });

    // Capture Module.print output
    let capturedOutput = [];

    let successes = 0;
    let zeroClickFailures = 0;
    let initFailures = 0;
    let otherFailures = 0;
    const failedSets = [];

    for (let i = 0; i < NUM_TRIALS; i++) {
        const unitNames = randomSet(library, 8);
        const mergedDeck = buildMergedDeck(unitNames, library);
        const activeDeck = mergedDeck.filter(c => !c._inactive);

        let initDeck, initParams, initJson;
        try {
            initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
            initParams = JSON.parse(selectParams('HardestAI', 1, fullParams, shortParams));
            initJson = JSON.stringify({
                mergedDeck: initDeck,
                aiParameters: initParams
            });
        } catch (e) {
            console.error(`Trial ${i}: buildInitDeck failed: ${e.message}`);
            initFailures++;
            failedSets.push({ trial: i, cards: unitNames, stage: 'buildInitDeck', error: e.message });
            continue;
        }

        // Initialize AI
        let initResult;
        try {
            capturedOutput = [];
            globalThis.Module.print = function(text) { capturedOutput.push(text); };
            globalThis.Module.printErr = function(text) { capturedOutput.push('[ERR] ' + text); };

            initResult = ai.initializeAI(initJson);

            globalThis.Module.print = function() {};
            globalThis.Module.printErr = function() {};
        } catch (e) {
            globalThis.Module.print = function() {};
            globalThis.Module.printErr = function() {};
            const errMsg = e instanceof Error ? e.message : String(e);
            console.error(`Trial ${i}: initializeAI threw: ${errMsg}`);
            initFailures++;
            failedSets.push({ trial: i, cards: unitNames, stage: 'initializeAI', error: errMsg, output: capturedOutput.slice(-5) });
            continue;
        }

        // Build game state for turn 1 (White's turn)
        const gameInitInfo = buildGameInitInfo(activeDeck);
        const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
        analyzer.loaderInit();

        const stateStr = analyzer.gameState.toString();
        const stateObj = JSON.parse(stateStr);
        const moveJson = JSON.stringify({
            gameState: stateObj,
            aiPlayerName: 'HardestAI'
        });

        // Get AI move
        let response;
        try {
            capturedOutput = [];
            globalThis.Module.print = function(text) { capturedOutput.push(text); };
            globalThis.Module.printErr = function(text) { capturedOutput.push('[ERR] ' + text); };

            const resultStr = ai.getAIMove(moveJson);
            const cleanResult = resultStr.replace(/[\x00-\x1f]/g, ' ');
            response = JSON.parse(cleanResult);

            globalThis.Module.print = function() {};
            globalThis.Module.printErr = function() {};
        } catch (e) {
            globalThis.Module.print = function() {};
            globalThis.Module.printErr = function() {};
            const errMsg = e instanceof Error ? e.message : String(e);
            console.error(`Trial ${i}: getAIMove threw: ${errMsg}`);
            otherFailures++;
            failedSets.push({ trial: i, cards: unitNames, stage: 'getAIMove', error: errMsg, output: capturedOutput.slice(-5) });
            continue;
        }

        const clicks = response.aiclicks || [];
        if (clicks.length === 0) {
            zeroClickFailures++;
            failedSets.push({
                trial: i,
                cards: unitNames,
                stage: 'zero_clicks',
                response: {
                    airesign: response.airesign,
                    aithinktime: response.aithinktime,
                    aiclicks: response.aiclicks,
                    // Include any other keys in the response
                    keys: Object.keys(response)
                },
                output: capturedOutput.slice(-10)
            });
            if (zeroClickFailures <= 5) {
                console.error(`Trial ${i}: 0 clicks! Cards: [${unitNames.join(', ')}]`);
                console.error(`  Response keys: ${Object.keys(response).join(', ')}`);
                console.error(`  airesign: ${response.airesign}, aithinktime: ${response.aithinktime}`);
                console.error(`  Full response: ${JSON.stringify(response).substring(0, 500)}`);
                if (capturedOutput.length > 0) {
                    console.error(`  Module output: ${capturedOutput.join(' | ')}`);
                }
            }
        } else {
            successes++;
        }

        if ((i + 1) % 50 === 0) {
            console.error(`Progress: ${i + 1}/${NUM_TRIALS} — ${successes} ok, ${zeroClickFailures} zero-click, ${initFailures} init-fail, ${otherFailures} other`);
        }
    }

    console.error(`\n=== Results ===`);
    console.error(`Total trials: ${NUM_TRIALS}`);
    console.error(`Successes: ${successes} (${(successes/NUM_TRIALS*100).toFixed(1)}%)`);
    console.error(`Zero-click failures: ${zeroClickFailures} (${(zeroClickFailures/NUM_TRIALS*100).toFixed(1)}%)`);
    console.error(`Init failures: ${initFailures} (${(initFailures/NUM_TRIALS*100).toFixed(1)}%)`);
    console.error(`Other failures: ${otherFailures} (${(otherFailures/NUM_TRIALS*100).toFixed(1)}%)`);

    if (failedSets.length > 0) {
        console.error(`\n=== Failed Card Sets ===`);
        for (const f of failedSets) {
            console.error(`  Trial ${f.trial} [${f.stage}]: [${f.cards.join(', ')}]`);
            if (f.response) {
                console.error(`    response: ${JSON.stringify(f.response)}`);
            }
            if (f.output && f.output.length > 0) {
                console.error(`    module output: ${f.output.join(' | ')}`);
            }
            if (f.error) {
                console.error(`    error: ${f.error}`);
            }
        }

        // Look for card frequency in failures
        const cardFreq = {};
        for (const f of failedSets) {
            for (const c of f.cards) {
                cardFreq[c] = (cardFreq[c] || 0) + 1;
            }
        }
        const sorted = Object.entries(cardFreq).sort((a, b) => b[1] - a[1]);
        console.error(`\n=== Card Frequency in Failures ===`);
        for (const [card, count] of sorted.slice(0, 20)) {
            console.error(`  ${card}: ${count} (${(count/failedSets.length*100).toFixed(0)}%)`);
        }
    }
}

main().catch(err => {
    console.error('Fatal:', err.message);
    console.error(err.stack);
    process.exit(1);
});
