'use strict';

// Smoke test: send one turn-1 request to Dave's Prismata_Standalone with
// aiPlayerName=DSNN_MBonly and verify the binary responds with clicks.
//
// Usage: node js_engine/smoke_dsnn.js [path/to/Prismata_Standalone.exe]

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const Analyzer = require('./Analyzer');
const aiParamsModule = require('./ai_params');
const {
    loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getSupply
} = require('./card_library');
const { buildGameInitInfo } = require('./matchup_clean');

const exePath = process.argv[2] || 'c:/libraries/PrismataAI-dave-master/bin/Prismata_Standalone.exe';
const thinkTimeMs = 2000;

// Mirror the config.txt block added to Dave's worktree.
const DSNN_PLAYER_BLOCK = {
    type: 'Player_UCT',
    TimeLimit: thinkTimeMs,
    MaxChildren: 40,
    MaxTraversals: 100000,
    RootMoveIterator: 'HardIterator_Root',
    MoveIterator: 'HardIterator',
    Eval: 'NeuralNet',
    WeightsFile: 'neural_weights_mbonly.bin'
};

async function main() {
    console.error('[smoke] Loading library + params...');
    const library = loadCardLibrary();
    const shortParams = aiParamsModule.loadShortParams();
    const aiParams = JSON.parse(shortParams);
    aiParams.Players.DSNN_MBonly = DSNN_PLAYER_BLOCK;
    aiParams.Players.HardestAI.TimeLimit = thinkTimeMs;

    const randomSetSize = 8;
    const cards = randomSet(library, randomSetSize);
    console.error('[smoke] Random card set: ' + cards.join(', '));

    const activeDeck = buildMergedDeck(cards, library);
    const initDeck = buildInitDeck(activeDeck, library, shortParams, shortParams);
    console.error('[smoke] activeDeck size=' + activeDeck.length + ', initDeck size=' + initDeck.length);

    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const stateStr = analyzer.gameState.toString();
    const stateObj = JSON.parse(stateStr);
    console.error('[smoke] Turn-1 state: turn=' + stateObj.turn + ', activePlayer=' + stateObj.activePlayer + ', phase=' + stateObj.phase);

    const requestJson = JSON.stringify({
        mergedDeck: initDeck,
        gameState: stateObj,
        aiParameters: aiParams,
        aiPlayerName: 'DSNN_MBonly'
    });

    console.error('[smoke] Request size: ' + requestJson.length + ' bytes');
    console.error('[smoke] Spawning ' + exePath + '...');

    const t0 = Date.now();
    const exeCwd = path.dirname(exePath);
    console.error('[smoke] exe cwd: ' + exeCwd);
    const child = spawn(exePath, [], { stdio: ['pipe', 'pipe', 'pipe'], cwd: exeCwd });

    let stdoutBuf = '';
    let stderrBuf = '';
    child.stdout.on('data', d => stdoutBuf += d.toString());
    child.stderr.on('data', d => stderrBuf += d.toString());

    const done = new Promise((resolve, reject) => {
        child.on('exit', code => resolve(code));
        child.on('error', err => reject(err));
    });

    child.stdin.write(requestJson + '\n');
    child.stdin.end();

    const code = await done;
    const elapsed = Date.now() - t0;

    console.error('\n========== STDERR (' + stderrBuf.length + ' bytes) ==========');
    console.error(stderrBuf);
    console.error('========== END STDERR ==========\n');

    console.error('[smoke] Exit code: ' + code + ', total elapsed: ' + elapsed + 'ms');

    let aiclicks = null;
    let aithinktime = null;
    try {
        const lastNL = stdoutBuf.lastIndexOf('\n');
        const jsonText = lastNL >= 0 ? stdoutBuf.substring(0, lastNL) : stdoutBuf;
        // Same control-char strip as steam_ai.js
        const clean = jsonText.replace(/[\x00-\x1f]/g, ' ').trim();
        const resp = JSON.parse(clean);
        aiclicks = resp.aiclicks;
        aithinktime = resp.aithinktime;
        console.error('[smoke] aiclicks count: ' + (aiclicks ? aiclicks.length : 'null'));
        console.error('[smoke] aithinktime: ' + aithinktime + 'ms');
        console.error('[smoke] aicomment: ' + (resp.aicomment || ''));
    } catch (err) {
        console.error('[smoke] JSON parse FAILED: ' + err.message);
        console.error('[smoke] Raw stdout (first 500 chars): ' + stdoutBuf.substring(0, 500));
        process.exit(2);
    }

    if (!aiclicks || aiclicks.length === 0) {
        console.error('[smoke] FAIL: 0 clicks returned');
        process.exit(3);
    }
    console.error('[smoke] First 5 clicks: ' + JSON.stringify(aiclicks.slice(0, 5)));
    console.error('[smoke] PASS');
    process.exit(0);
}

main().catch(err => {
    console.error('[smoke] EXCEPTION: ' + err.message + '\n' + err.stack);
    process.exit(1);
});
