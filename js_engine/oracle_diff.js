'use strict';
// Oracle diff: compare our JS-engine state against an AS3 F6 dev-mode gamestate dump.
// Replays <CODE> through the JS engine, snapshots gameState at every action boundary,
// auto-aligns to the F6 dump by state signature, then diffs scalars + per-inst fields.
// The first divergent field is the root-cause locus.
//
// Usage: node oracle_diff.js <CODE> <F6dumpFile> [actionIndex]
//   actionIndex (optional): force-compare against that snapshot index instead of auto-align.
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
function findFile(dir, code) { const enc = code.replace(/\+/g, '%2B').replace(/@/g, '%40'); let fp = path.join(dir, enc + '.json.gz'); if (!fs.existsSync(fp)) fp = path.join(dir, code + '.json.gz'); return fp; }

// Extract the brace-balanced CurrentInfo object from a raw F6 dump (string-aware).
function extractCurrentInfo(raw) {
    const i = raw.indexOf('"CurrentInfo"'); const j = raw.indexOf('{', i);
    let depth = 0, instr = false, esc = false, k = j;
    for (; k < raw.length; k++) {
        const c = raw[k];
        if (instr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') instr = false; }
        else { if (c === '"') instr = true; else if (c === '{') depth++; else if (c === '}') { depth--; if (depth === 0) { k++; break; } } }
    }
    return JSON.parse(raw.slice(j, k));
}

const SIG_KEYS = ['numTurns', 'phase', 'turn', 'nextInstId', 'whiteMana', 'blackMana', 'glassBroken'];
function sig(gs) { const o = {}; SIG_KEYS.forEach(k => o[k] = gs[k]); o.tableLen = (gs.table || []).length; return o; }
function sigEq(a, b) { return SIG_KEYS.every(k => String(a[k]) === String(b[k])) && a.tableLen === b.tableLen; }
function sigScore(a, b) { let s = SIG_KEYS.filter(k => String(a[k]) === String(b[k])).length; if (a.tableLen === b.tableLen) s++; return s; }

const code = process.argv[2];
const dumpFile = process.argv[3];
const forceIdx = process.argv[4] != null ? parseInt(process.argv[4], 10) : null;

const replay = loadReplay(findFile('C:/libraries/prismata-replay-parser/replays_archive', code));
const ci = extractCurrentInfo(fs.readFileSync(dumpFile, 'utf-8'));
const oracle = ci.gameState;
const oracleSig = sig(oracle);

const analyzer = new Analyzer(buildInitInfo(replay), -1, -1, null);
const snaps = [];
function snap(label) { try { const g = JSON.parse(analyzer.gameState.toString()); snaps.push({ label, sig: sig(g), gs: g }); } catch (e) {} }
const orig = analyzer.recordClick.bind(analyzer);
let idx = 0;
analyzer.recordClick = function (u, d, type, id, params) {
    const r = orig(u, d, type, id, params);
    snap(`after click ${idx} [${String(type)} id=${id} ok=${r && r.canClick}]`);
    idx++;
    return r;
};
snap('initial');
try { analyzer.loaderInit(); } catch (e) { console.log('replay threw:', e.message); }

console.log(`Oracle (F6) signature:`, JSON.stringify(oracleSig));
console.log(`Captured ${snaps.length} snapshots.`);

// Pick the snapshot to compare
let chosen = null;
if (forceIdx != null) { chosen = snaps[forceIdx]; console.log(`Forced snapshot idx=${forceIdx}: ${chosen ? chosen.label : 'MISSING'}`); }
else {
    const exact = snaps.filter(s => sigEq(s.sig, oracleSig));
    if (exact.length) { chosen = exact[exact.length - 1]; console.log(`Exact signature match: ${exact.length} snapshot(s); using last -> ${chosen.label}`); }
    else {
        let best = null, bestScore = -1;
        snaps.forEach(s => { const sc = sigScore(s.sig, oracleSig); if (sc > bestScore) { bestScore = sc; best = s; } });
        chosen = best;
        console.log(`No exact match. Best partial (${bestScore}/${SIG_KEYS.length + 1}): ${best.label}`);
        console.log(`  our sig:`, JSON.stringify(best.sig));
    }
}
if (!chosen) { console.log('No snapshot to compare.'); process.exit(1); }

// ---- DIFF ----
const ours = chosen.gs;
console.log(`\n==== SCALAR DIFFS (ours vs oracle) ====`);
const scalarKeys = Object.keys(oracle).filter(k => k !== 'table');
let scalarDiffs = 0;
scalarKeys.forEach(k => {
    const a = JSON.stringify(ours[k]); const b = JSON.stringify(oracle[k]);
    if (a !== b) { console.log(`  ${k}: ours=${a}  oracle=${b}`); scalarDiffs++; }
});
if (!scalarDiffs) console.log('  (none)');

console.log(`\n==== TABLE DIFFS (matched by instId) ====`);
const ourById = new Map(); (ours.table || []).forEach(t => ourById.set(t.instId, t));
const orcById = new Map(); (oracle.table || []).forEach(t => orcById.set(t.instId, t));
const allIds = Array.from(new Set([...ourById.keys(), ...orcById.keys()])).sort((a, b) => a - b);
let instDiffs = 0;
for (const id of allIds) {
    const a = ourById.get(id), b = orcById.get(id);
    if (!a) { console.log(`  id=${id}: ONLY IN ORACLE -> ${b.cardName} o${b.owner} role=${b.role} dead=${b.deadness}`); instDiffs++; continue; }
    if (!b) { console.log(`  id=${id}: ONLY IN OURS -> ${a.cardName} o${a.owner} role=${a.role} dead=${a.deadness}`); instDiffs++; continue; }
    const keys = Array.from(new Set([...Object.keys(a), ...Object.keys(b)]));
    const fieldDiffs = [];
    keys.forEach(k => { const va = JSON.stringify(a[k]); const vb = JSON.stringify(b[k]); if (va !== vb) fieldDiffs.push(`${k}: ${va}!=${vb}`); });
    if (fieldDiffs.length) { console.log(`  id=${id} (${b.cardName} o${b.owner}): ${fieldDiffs.join('  |  ')}`); instDiffs++; }
}
if (!instDiffs) console.log('  (none) — tables identical');
console.log(`\nSUMMARY: ${scalarDiffs} scalar diff(s), ${instDiffs} inst diff(s).`);
