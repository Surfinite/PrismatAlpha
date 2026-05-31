'use strict';
// Full-corpus faithfulness scanner: replay every code through the JS engine, record
// per-replay illegal-click count + first-illegal signature, group failures by class.
// Usage: node corpus_scan.js <codesFile> [replaysDir] [outJson]
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');

function loadReplay(fp) { const raw = fs.readFileSync(fp); return fp.endsWith('.gz') ? JSON.parse(zlib.gunzipSync(raw).toString('utf-8')) : JSON.parse(raw.toString('utf-8')); }
function buildInitInfo(r) {
    return { laneInfo: [{ initResources: r.initInfo.initResources, base: r.deckInfo.base, randomizer: r.deckInfo.randomizer, initCards: r.initInfo.initCards }],
        mergedDeck: r.deckInfo.mergedDeck, scriptInfo: { whiteStarts: true }, objectiveInfo: null,
        commandInfo: { commandList: r.commandInfo.commandList, clicksPerTurn: r.commandInfo.clicksPerTurn, gamePosition: r.commandInfo.commandList.length } };
}
function findFile(dir, code) { const enc = code.replace(/\+/g, '%2B').replace(/@/g, '%40'); let fp = path.join(dir, enc + '.json.gz'); if (!fs.existsSync(fp)) fp = path.join(dir, code + '.json.gz'); return fs.existsSync(fp) ? fp : null; }
function phaseName(p) { return p === C.PHASE_DEFENSE ? 'DEF' : p === C.PHASE_ACTION ? 'ACT' : p === C.PHASE_CONFIRM ? 'CONF' : ('p' + p); }

const codesFile = process.argv[2];
const REPLAYS = process.argv[3] || 'C:/libraries/prismata-replay-parser/replays_archive';
const outJson = process.argv[4] || 'C:/libraries/PrismataAI/docs/scratch/corpus_failures.json';
const codes = fs.readFileSync(codesFile, 'utf-8').trim().split('\n').map(s => s.trim()).filter(Boolean);

let processed = 0, skipped = 0, errored = 0, totalIllegal = 0;
const failures = [];        // {code, n, sig, recordedTurns, jsTurns}
const classHist = {};       // sig -> count
const errHist = {};         // error message -> count
const t0 = Date.now();

for (const code of codes) {
    const fp = findFile(REPLAYS, code);
    if (!fp) { skipped++; continue; }
    let replay;
    try { replay = loadReplay(fp); } catch (e) { errored++; continue; }
    const recordedTurns = (replay.commandInfo && replay.commandInfo.clicksPerTurn || []).length;
    let n = 0, first = null, idx = 0;
    const analyzer = new Analyzer(buildInitInfo(replay), -1, -1, null);
    const orig = analyzer.recordClick.bind(analyzer);
    analyzer.recordClick = function (u, d, type, id, params) {
        const gs = analyzer.gameState;
        const ctx = { phase: phaseName(gs.phase), inT: analyzer.controller.inTargetMode, inS: analyzer.controller.inSwipe, glass: gs.glassBroken };
        const r = orig(u, d, type, id, params);
        if (r && r.canClick === false) {
            n++;
            if (!first) {
                let tgtNull = false;
                if (id >= 0) { try { tgtNull = analyzer.gameState.instIdToInst(id) == null; } catch (e) { tgtNull = true; } }
                first = `${ctx.phase}|${String(type)}|tgtNull=${tgtNull}|inT=${ctx.inT}|inS=${ctx.inS}|glass=${ctx.glass}`;
            }
        }
        idx++;
        return r;
    };
    let jsTurns = 0;
    try { analyzer.loaderInit(); jsTurns = (analyzer.beginTurnHistory || []).length; }
    catch (e) { errored++; errHist[e.message] = (errHist[e.message] || 0) + 1; }
    processed++;
    if (n > 0) {
        totalIllegal += n;
        failures.push({ code, n, sig: first, rec: recordedTurns, js: jsTurns });
        classHist[first] = (classHist[first] || 0) + 1;
    }
    if (processed % 5000 === 0) process.stderr.write(`  ${processed} processed, ${failures.length} failing, ${totalIllegal} illegal [${(processed / ((Date.now() - t0) / 1000)).toFixed(0)}/s]\n`);
}

failures.sort((a, b) => a.n - b.n);
fs.writeFileSync(outJson, JSON.stringify({ processed, skipped, errored, totalIllegal, failing: failures.length, classHist, errHist, failures }, null, 1));
console.log(`\n==== CORPUS SCAN ====`);
console.log(`codes=${codes.length} processed=${processed} skipped(no file)=${skipped} errored=${errored}`);
console.log(`FAILING replays=${failures.length}  TOTAL illegal clicks=${totalIllegal}`);
console.log(`\nfailure CLASSES (first-illegal signature  ->  #replays):`);
Object.entries(classHist).sort((a, b) => b[1] - a[1]).forEach(([s, c]) => console.log(`  ${String(c).padStart(5)}  ${s}`));
if (Object.keys(errHist).length) { console.log(`\nERRORS (exception msg -> count):`); Object.entries(errHist).sort((a, b) => b[1] - a[1]).slice(0, 15).forEach(([m, c]) => console.log(`  ${String(c).padStart(5)}  ${m}`)); }
console.log(`\nfull failure list -> ${outJson}`);
