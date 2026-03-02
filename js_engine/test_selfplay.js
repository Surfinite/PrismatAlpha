'use strict';

/**
 * test_selfplay.js — Test self-play integration: init, first move, apply clicks.
 * Uses MCDSAIWorker (child process) to avoid Emscripten stdout noise.
 */

const MCDSAIWorker = require('./mcdsai_manager');
const { loadCardLibrary, buildMergedDeck, randomSet } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const Analyzer = require('./Analyzer');
const C = require('./C');
const StateUtil = require('./StateUtil');

function buildGameInitInfo(mergedDeck) {
    const base = [], randomizer = [];
    for (const card of mergedDeck) {
        const supply = (card._inactive || card.rarity === 'unbuyable') ? 0 :
            (card.supply !== undefined ? card.supply : 20);
        if (card.baseSet) base.push([card.name, supply]);
        else randomizer.push([card.name, supply]);
    }
    return {
        laneInfo: [{
            initResources: ['0', '0'],
            base: [base, base], randomizer: [randomizer, randomizer],
            initCards: [[[6, 'Drone'], [2, 'Engineer']], [[7, 'Drone'], [2, 'Engineer']]]
        }],
        mergedDeck: mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null, commandInfo: null
    };
}

async function main() {
    const lib = loadCardLibrary();
    const units = randomSet(lib, 8);
    console.log('Random set:', units.join(', '));
    const deck = buildMergedDeck(units, lib);
    console.log('Deck:', deck.length, 'cards');

    // Spawn worker
    const worker = new MCDSAIWorker('Test');
    console.log('Spawning MCDSAI worker...');
    await worker.spawn();
    console.log('Worker ready.');

    // Init AI
    const fullParams = loadFullParams();
    const shortParams = loadShortParams();
    const parsedParams = JSON.parse(selectParams('HardestAI', 1, fullParams, shortParams));
    const initJson = JSON.stringify({ mergedDeck: deck, aiParameters: parsedParams });

    console.log('Initializing AI...');
    try {
        const initResult = await worker.initializeAI(initJson);
        const clean = initResult.replace(/[\x00-\x1f]/g, ' ');
        const parsed = JSON.parse(clean);
        console.log('Init:', parsed.aiinitcomment, '-', parsed.aiinfo);
    } catch(e) {
        console.log('Init error:', e.message);
        worker.terminate();
        return;
    }

    // Build game state
    const gii = buildGameInitInfo(deck);
    const analyzer = new Analyzer(gii, -1, -1, null);
    analyzer.loaderInit();
    console.log('Game ready, cards:', analyzer.gameState.cards.length,
        'turn:', analyzer.gameState.turn === 0 ? 'White' : 'Black',
        'phase:', analyzer.gameState.phase);

    // Play up to 5 turns
    const MAX_TURNS = 5;
    for (let turn = 0; turn < MAX_TURNS; turn++) {
        if (analyzer.gameState.finished) {
            console.log('Game finished! Result:', analyzer.gameState.result);
            break;
        }

        const activePlayer = analyzer.gameState.turn;
        const playerName = activePlayer === C.COLOR_WHITE ? 'White' : 'Black';

        const stateStr = analyzer.gameState.toString();
        const stateObj = JSON.parse(stateStr);
        const moveJson = JSON.stringify({ gameState: stateObj, aiPlayerName: 'HardestAI' });

        console.log('\n--- Turn ' + (turn + 1) + ' (' + playerName + ') ---');
        console.log('Mana:', stateObj.whiteMana, '/', stateObj.blackMana);

        let response;
        try {
            const resultStr = await worker.getAIMove(moveJson);
            const clean = resultStr.replace(/[\x00-\x1f]/g, ' ');
            response = JSON.parse(clean);
        } catch(e) {
            console.log('Move error:', e.message);
            break;
        }

        console.log('Think:', response.aithinktime + 'ms, Resign:', response.airesign);
        console.log('Clicks:', response.aiclicks.length);

        if (response.airesign) {
            console.log(playerName, 'resigns!');
            break;
        }

        const aiclicks = response.aiclicks || [];
        for (let i = 0; i < Math.min(10, aiclicks.length); i++) {
            console.log('  Click ' + i + ':', JSON.stringify(aiclicks[i]));
        }
        if (aiclicks.length > 10) {
            console.log('  ... and', aiclicks.length - 10, 'more');
        }

        // Apply clicks through our engine
        try {
            const clicks = StateUtil.convertToClicks(aiclicks, analyzer.gameState, false);
            let applied = 0, failed = 0;
            for (const click of clicks) {
                const cr = analyzer.recordClick(false, false, click.type, click.id, click.params);
                if (cr.canClick) applied++;
                else failed++;
            }
            console.log('Applied:', applied, 'Failed:', failed);
        } catch(e) {
            // Fallback: apply clicks directly
            console.log('convertToClicks failed:', e.message.substring(0, 100));
            let applied = 0;
            for (const ac of aiclicks) {
                try {
                    const cr = analyzer.recordClick(false, false, ac.type, ac.args || -1);
                    if (cr.canClick) applied++;
                } catch(e2) {
                    // skip
                }
            }
            console.log('Direct apply:', applied, 'clicks');
        }
    }

    console.log('\nFinal state - Turn:', analyzer.gameState.numTurns,
        'Phase:', analyzer.gameState.phase,
        'Finished:', analyzer.gameState.finished);

    worker.terminate();
    console.log('Done.');
}

main().catch(e => {
    console.error('Fatal:', e.message);
    process.exit(1);
});
