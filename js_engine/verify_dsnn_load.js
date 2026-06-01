#!/usr/bin/env node
/**
 * verify_dsnn_load.js — definitively confirm the DaveAI/Standalone path actually
 * loads the 35-prop DSNN weights for aiPlayerName=DSNN_Mixed35 (vs silently
 * falling back to a non-NN eval). Builds a real turn-0 request exactly like
 * matchup_clean.playSteamAITurn and captures the exe's stderr (which steam_ai.js
 * normally ignores).
 */
const { spawnSync } = require('child_process');
const path = require('path');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const Analyzer = require('./Analyzer');
const { buildGameInitInfo } = (() => {
    // buildGameInitInfo lives in matchup_clean; require it lazily
    const m = require('./matchup_clean');
    return { buildGameInitInfo: m.buildGameInitInfo };
})();

const EXE = process.argv[2] || 'C:/libraries/PrismataAI-dave-master/bin/Prismata_Standalone.exe';
const DIFF = process.argv[3] || 'DSNN_Mixed35';
const WEIGHTS = { DSNN_Mixed35: 'neural_weights_mixed_35prop.bin' };

const library = loadCardLibrary();
const units = randomSet(library, 8);
const mergedDeck = buildMergedDeck(units, library);
const activeDeck = mergedDeck.filter(c => !c._inactive);
const initDeck = buildInitDeck(activeDeck, library,
    loadFullParams(path.join(__dirname, '..', 'tmp_swf_extract', '148_AI.AIThreadHandler_aiParamTextLoad.bin')),
    loadShortParams(path.join(__dirname, '..', 'tmp_swf_extract', '93_AI.AIThreadHandler_aiParam_shortTextLoad.bin')));

const gi = buildGameInitInfo(activeDeck);
const analyzer = new Analyzer(gi, -1, -1, null);
analyzer.loaderInit();
const stateObj = JSON.parse(analyzer.gameState.toString());

const fullParams = loadFullParams(path.join(__dirname, '..', 'tmp_swf_extract', '148_AI.AIThreadHandler_aiParamTextLoad.bin'));
const shortParams = loadShortParams(path.join(__dirname, '..', 'tmp_swf_extract', '93_AI.AIThreadHandler_aiParam_shortTextLoad.bin'));
const aiParams = JSON.parse(selectParams(DIFF, 1, fullParams, shortParams));
if (DIFF.startsWith('DSNN_')) {
    aiParams.Players = aiParams.Players || {};
    aiParams.Players[DIFF] = {
        type: 'Player_UCT', TimeLimit: 700, MaxChildren: 40, MaxTraversals: 100000,
        RootMoveIterator: 'HardIterator_Root', MoveIterator: 'HardIterator',
        Eval: 'NeuralNet', WeightsFile: WEIGHTS[DIFF]
    };
}
const request = JSON.stringify({ mergedDeck: initDeck, gameState: stateObj, aiParameters: aiParams, aiPlayerName: DIFF });

const res = spawnSync(EXE, [], { input: request, cwd: path.dirname(EXE), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const err = res.stderr || '';
const nnLines = err.split(/\r?\n/).filter(l => /NeuralNet:|DSN2|props=|tensors|weights/i.test(l));
console.log('=== exe stderr NN lines ===');
console.log(nnLines.length ? nnLines.join('\n') : '(none — NN may NOT have loaded!)');
const loaded = /props=35/.test(err) && /loaded \d+ tensors/i.test(err);
console.log('\nVERDICT: 35-prop DSNN weights loaded =', loaded);
let resp = null; try { resp = JSON.parse(res.stdout); } catch (_) {}
console.log('exe returned clicks:', resp ? (resp.aiclicks ? resp.aiclicks.length : 'n/a') : 'PARSE FAIL', '| aithinktime:', resp && resp.aithinktime);
