#!/usr/bin/env node
/**
 * Compare cardLibrary.jso against SWF-extracted authoritative card data.
 *
 * SWF source: tmp_swf_extract/81_mcds.Util_testNormalCards.bin (275 entries, display-name keys)
 * Our library: bin/asset/config/cardLibrary.jso (161 entries, internal-codename keys + UIName)
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SWF_PATH = path.join(ROOT, 'tmp_swf_extract', '81_mcds.Util_testNormalCards.bin');
const LIB_PATH = path.join(ROOT, 'bin', 'asset', 'config', 'cardLibrary.jso');

const swf = JSON.parse(fs.readFileSync(SWF_PATH, 'utf8'));
const lib = JSON.parse(fs.readFileSync(LIB_PATH, 'utf8'));

// --- Fields to compare (gameplay-relevant, present in both files) ---
const COMPARE_FIELDS = [
    // Core stats
    'rarity', 'toughness', 'defaultBlocking', 'assignedBlocking', 'buyCost', 'buildTime',
    'fragile', 'lifespan', 'spell', 'undefendable',
    // Scripts
    'abilityScript', 'buyScript', 'beginOwnTurnScript',
    // Ability details
    'abilityCost', 'abilitySac', 'abilityNetherfy',
    // Buy details
    'buySac',
    // Targeting
    'targetAction', 'targetAmount',
    // Conditions & charges
    'charge', 'condition', 'needs',
    // Resonate
    'resonate', 'goldResonate',
    // HP system
    'HPGained', 'HPMax', 'HPUsed',
    // Other gameplay
    'potentiallyMoreAttack',
];

// Fields to skip (visual/metadata, or only in one file)
// UIArt, UIName, UIShortname, description, fullDescription, fullDescription_en,
// position, score, baseSet, group

// --- Build display-name → cardLibrary entry mapping ---
// cardLibrary uses internal codenames as keys; UIName maps to display name.
// If no UIName, the key IS the display name.
const libByDisplayName = {};
const internalToDisplay = {};
for (const [internalName, entry] of Object.entries(lib)) {
    const displayName = entry.UIName || internalName;
    libByDisplayName[displayName] = { ...entry, _internalName: internalName };
    internalToDisplay[internalName] = displayName;
}

// --- Categorize SWF entries ---
const swfBuyable = {};   // have rarity field
const swfTokens = {};    // no rarity field (unbuyable tokens)
for (const [name, entry] of Object.entries(swf)) {
    if ('rarity' in entry) {
        swfBuyable[name] = entry;
    } else {
        swfTokens[name] = entry;
    }
}

// --- Comparison ---
const missingFromLib = [];     // In SWF (buyable) but not in our lib
const missingFromSwf = [];     // In our lib but not in SWF
const perfectMatches = [];
const differences = [];

// Deep equality for script objects (order-insensitive)
function deepEqual(a, b) {
    if (a === b) return true;
    if (a == null && b == null) return true;
    if (a == null || b == null) return false;
    if (typeof a !== typeof b) {
        // Handle string/number coercion (SWF sometimes uses numbers where lib uses strings)
        if (String(a) === String(b)) return true;
        return false;
    }
    if (typeof a !== 'object') return a === b;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    if (Array.isArray(a)) {
        if (a.length !== b.length) return false;
        return a.every((v, i) => deepEqual(v, b[i]));
    }
    const keysA = Object.keys(a).sort();
    const keysB = Object.keys(b).sort();
    if (keysA.length !== keysB.length) return false;
    if (!keysA.every((k, i) => k === keysB[i])) return false;
    return keysA.every(k => deepEqual(a[k], b[k]));
}

function formatValue(v) {
    if (v === undefined) return '(absent)';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
}

// Check buyable SWF entries against our library
for (const [displayName, swfEntry] of Object.entries(swfBuyable)) {
    if (!(displayName in libByDisplayName)) {
        missingFromLib.push(displayName);
        continue;
    }
    const libEntry = libByDisplayName[displayName];
    const diffs = [];

    for (const field of COMPARE_FIELDS) {
        const swfVal = swfEntry[field];
        const libVal = libEntry[field];
        // Both absent = match
        if (swfVal === undefined && libVal === undefined) continue;
        if (!deepEqual(swfVal, libVal)) {
            diffs.push({
                field,
                swf: formatValue(swfVal),
                lib: formatValue(libVal),
            });
        }
    }

    if (diffs.length === 0) {
        perfectMatches.push(displayName);
    } else {
        differences.push({
            displayName,
            internalName: libEntry._internalName,
            diffs,
        });
    }
}

// Check our library entries not in SWF
for (const [internalName, entry] of Object.entries(lib)) {
    const displayName = entry.UIName || internalName;
    if (!(displayName in swfBuyable) && !(displayName in swfTokens)) {
        missingFromSwf.push({ internalName, displayName });
    }
}

// Also check: our lib entries that match SWF tokens (not buyable units)
const libMatchesTokens = [];
for (const [internalName, entry] of Object.entries(lib)) {
    const displayName = entry.UIName || internalName;
    if (displayName in swfTokens) {
        libMatchesTokens.push({ internalName, displayName });
    }
}

// --- Report ---
console.log('='.repeat(80));
console.log('CARD LIBRARY COMPARISON: cardLibrary.jso vs SWF-extracted data');
console.log('='.repeat(80));
console.log();
console.log(`SWF entries: ${Object.keys(swf).length} total (${Object.keys(swfBuyable).length} buyable, ${Object.keys(swfTokens).length} tokens)`);
console.log(`cardLibrary entries: ${Object.keys(lib).length}`);
console.log(`Fields compared: ${COMPARE_FIELDS.length}`);
console.log();

// Summary
console.log('-'.repeat(80));
console.log('SUMMARY');
console.log('-'.repeat(80));
console.log(`  Perfect matches:           ${perfectMatches.length}`);
console.log(`  Units with differences:    ${differences.length}`);
console.log(`  In SWF but missing from lib: ${missingFromLib.length}`);
console.log(`  In lib but missing from SWF: ${missingFromSwf.length}`);
console.log(`  Lib entries matching tokens: ${libMatchesTokens.length}`);
console.log();

// Missing from our library
if (missingFromLib.length > 0) {
    console.log('-'.repeat(80));
    console.log(`MISSING FROM cardLibrary.jso (${missingFromLib.length} buyable SWF units not in our lib)`);
    console.log('-'.repeat(80));
    for (const name of missingFromLib.sort()) {
        const s = swfBuyable[name];
        console.log(`  ${name} — rarity: ${s.rarity || '?'}, cost: ${s.buyCost || '?'}, toughness: ${s.toughness || '?'}`);
    }
    console.log();
}

// Missing from SWF
if (missingFromSwf.length > 0) {
    console.log('-'.repeat(80));
    console.log(`IN cardLibrary.jso BUT MISSING FROM SWF (${missingFromSwf.length} units)`);
    console.log('-'.repeat(80));
    for (const { internalName, displayName } of missingFromSwf.sort((a, b) => a.displayName.localeCompare(b.displayName))) {
        const nameStr = internalName !== displayName ? `${displayName} (internal: ${internalName})` : displayName;
        console.log(`  ${nameStr}`);
    }
    console.log();
}

// Differences
if (differences.length > 0) {
    console.log('-'.repeat(80));
    console.log(`FIELD DIFFERENCES (${differences.length} units)`);
    console.log('-'.repeat(80));
    for (const { displayName, internalName, diffs } of differences.sort((a, b) => a.displayName.localeCompare(b.displayName))) {
        const nameStr = internalName !== displayName ? `${displayName} (internal: ${internalName})` : displayName;
        console.log(`\n  ${nameStr}:`);
        for (const { field, swf: swfVal, lib: libVal } of diffs) {
            console.log(`    ${field.padEnd(25)} SWF: ${swfVal.padEnd(30)} Ours: ${libVal}`);
        }
    }
    console.log();
}

// Tokens
if (Object.keys(swfTokens).length > 0) {
    console.log('-'.repeat(80));
    console.log(`SWF TOKENS (${Object.keys(swfTokens).length} unbuyable entries — no rarity field)`);
    console.log('-'.repeat(80));
    const tokenNames = Object.keys(swfTokens).sort();
    // Mark which ones are in our lib
    for (const name of tokenNames) {
        const inLib = libMatchesTokens.some(t => t.displayName === name);
        const marker = inLib ? ' [IN LIB]' : '';
        console.log(`  ${name}${marker}`);
    }
    console.log();
}

// Perfect matches
console.log('-'.repeat(80));
console.log(`PERFECT MATCHES (${perfectMatches.length} units)`);
console.log('-'.repeat(80));
const cols = 3;
const sorted = perfectMatches.sort();
for (let i = 0; i < sorted.length; i += cols) {
    const row = sorted.slice(i, i + cols).map(n => n.padEnd(26)).join('');
    console.log(`  ${row}`);
}
console.log();
console.log('='.repeat(80));
console.log('DONE');
