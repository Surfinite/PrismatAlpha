#!/usr/bin/env node
/**
 * audit_visual_fidelity.js — Visual Fidelity Audit Tool
 *
 * Compares what the PixiJS viewer renders per-card against what the Godot viewer
 * currently supports, producing a quantified gap report.
 *
 * Usage:
 *   node tools/audit_visual_fidelity.js <replay.json[.gz]>
 *   node tools/audit_visual_fidelity.js <replay.json.gz> --turn 15
 *   node tools/audit_visual_fidelity.js <replay.json.gz> --verbose
 *   node tools/audit_visual_fidelity.js <replay.json.gz> --output report.json
 *   node tools/audit_visual_fidelity.js --batch 50 --seed 42
 *   node tools/audit_visual_fidelity.js --capabilities
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { processReplayData, loadReplay } = require('./replay_to_snapshots');
const { buildCardIdMap, toCardId } = require('./card_id_map');
const { computeVisualState, BACK_BOUGHT, COVER_INVSPAWN, COVER_INVBOUGHT,
    BACK_BLOCK, BACK_BLOCKRED, BACK_BUSYBLUE, BACK_BUSYRED, BACK_BLOCK_FROST,
    BACK_DEAD, BACK_ABSORB, BACK_WHITEPINK, COVER_BANG, COVER_ASSIGNED,
    SHADING_BLOCK, SHADING_REDBLOCK, SHADING_NOTBLOCK, SHADING_DEAD_BLOCK,
    SHADING_EMPTY, COVER_EMPTY } = require('./visual_state');
const { computeStatusIcons } = require('./status_overlay');

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const CARD_LIBRARY_PATH = path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso');
const PRISMATA_LADDER_PATH = path.resolve(__dirname, '..', '..', '<ladder>');
const PRISMATA_3D_PATH = path.resolve(__dirname, '..', '..', 'prismata-3d');
const REPLAY_ARCHIVE_PATH = path.resolve(__dirname, '..', '..', 'prismata-replay-parser', 'replays_archive');

// ---------------------------------------------------------------------------
// Godot Capability Model (v2.1 — semantic features)
// ---------------------------------------------------------------------------
const CAPABILITY_MODEL_VERSION = '2026-03-26';

const GODOT_CAPABILITIES = {
    // === STATE PARITY ===
    layout_position:      'exact',
    card_sprite:          'exact',
    player_color_frame:   'approximate',   // Real textures but not pixel-identical to PixiJS
    construction_signal:  'approximate',   // BACK_BOUGHT + clock, but no INVBOUGHT distinction
    blocking_signal:      'approximate',   // Shield overlays, but missing NOTBLOCK
    attack_signal:        'approximate',   // Cage overlay, but no sellable handling
    chill_signal:         'approximate',   // Frost bg + snowflake, but no phase suppression
    damage_signal:        'approximate',   // ABSORB + BANG, but no WHITEPINK
    attack_icon:          'approximate',   // Real sprite + number, positioning may differ
    defense_icon:         'approximate',   // Real sprite + number, uses maxHp not metadata toughness
    construction_timer:   'approximate',   // Number shown, positioning may differ
    hp_icon:              'approximate',   // Real sprite + number
    frontline_icon:       'approximate',   // Real sprite
    delay_icon:           'approximate',   // Real sprite + number
    lifespan_icon:        'approximate',   // Real sprite + number
    charge_icon:          'approximate',   // Real sprite + number
    chill_icon:           'approximate',   // Real sprite + number
    p1_card_flip:         'unsupported',
    name_label:           'excluded',
    sellable_prompt:      'excluded',

    // === TRANSITION PARITY ===
    buy_effect:           'approximate',
    death_effect:         'approximate',
    damage_effect:        'unsupported',
    breach_effect:        'unsupported',
};

// Feature type classification
const STATE_FEATURES = new Set([
    'layout_position', 'card_sprite', 'player_color_frame',
    'construction_signal', 'blocking_signal', 'attack_signal',
    'chill_signal', 'damage_signal', 'attack_icon', 'defense_icon',
    'construction_timer', 'hp_icon', 'frontline_icon', 'delay_icon',
    'lifespan_icon', 'charge_icon', 'chill_icon', 'p1_card_flip',
    'name_label', 'sellable_prompt',
]);

const TRANSITION_FEATURES = new Set([
    'buy_effect', 'death_effect', 'damage_effect', 'breach_effect',
]);

// Weights (from spec v2.1)
const WEIGHTS = {
    // State
    player_color_frame:   1.0,
    attack_icon:          0.9,
    defense_icon:         0.9,
    construction_signal:  0.8,
    construction_timer:   0.8,
    blocking_signal:      0.7,
    attack_signal:        0.7,
    damage_signal:        0.7,
    chill_signal:         0.6,
    hp_icon:              0.8,
    frontline_icon:       0.5,
    delay_icon:           0.5,
    lifespan_icon:        0.5,
    charge_icon:          0.5,
    p1_card_flip:         0.4,
    layout_position:      1.0,
    card_sprite:          1.0,
    // Transition
    buy_effect:           0.5,
    death_effect:         0.6,
    damage_effect:        0.6,
    breach_effect:        0.7,
};

// ---------------------------------------------------------------------------
// Card metadata loader
// ---------------------------------------------------------------------------

/**
 * Derive attack value from cardLibrary.jso entry.
 * Attack isn't a flat field — it comes from beginOwnTurnScript.receive ("A" = 1 attack,
 * "AA" = 2, etc.) or abilityScript.receive.
 */
function deriveAttack(cardDef) {
    let attack = 0;
    // beginOwnTurnScript auto-attack
    const autoReceive = cardDef.beginOwnTurnScript && cardDef.beginOwnTurnScript.receive;
    if (typeof autoReceive === 'string') {
        const m = autoReceive.match(/A+/);
        if (m) attack += m[0].length;
    }
    // abilityScript attack
    const abilityReceive = cardDef.abilityScript && cardDef.abilityScript.receive;
    if (typeof abilityReceive === 'string') {
        const m = abilityReceive.match(/A+/);
        if (m) attack += m[0].length;
    }
    return attack;
}

function loadCardMeta() {
    const raw = fs.readFileSync(CARD_LIBRARY_PATH, 'utf-8');
    const library = JSON.parse(raw);
    const idMap = buildCardIdMap(CARD_LIBRARY_PATH);

    // Build cardId → metadata map
    const metaByCardId = {};
    for (const [internalName, cardDef] of Object.entries(library)) {
        if (typeof cardDef !== 'object') continue;
        const info = idMap[internalName];
        if (!info) continue;

        metaByCardId[info.cardId] = {
            attack: deriveAttack(cardDef),
            toughness: cardDef.toughness || 0,
            isFragile: !!cardDef.fragile,
            isFrontline: !!cardDef.undefendable,
            defaultBlocking: !!cardDef.defaultBlocking,
            cardType: cardDef.spell ? 'spell' : 'unit',
            charge: cardDef.charge || 0,
            lifespan: cardDef.lifespan || -1,
            buildTime: cardDef.buildTime || 0,
            canBlock: cardDef.canBlock !== false,
        };
    }
    return metaByCardId;
}

// ---------------------------------------------------------------------------
// Feature applicability + classification per unit-render
// ---------------------------------------------------------------------------

/**
 * For a single unit in a single snapshot, determine which features are applicable
 * and classify each against the Godot capability model.
 */
function classifyUnit(unit, cardMeta, phase, colorOnBottom) {
    const vs = computeVisualState(unit, cardMeta, phase, colorOnBottom);
    const so = computeStatusIcons(unit, cardMeta);
    const meta = cardMeta || {};
    const results = {};

    // Helper: record a feature classification
    function record(feature, capability) {
        if (capability === 'excluded') {
            results[feature] = 'excluded';
        } else {
            results[feature] = capability;
        }
    }

    // --- Layout (always applicable for alive units) ---
    record('layout_position', GODOT_CAPABILITIES.layout_position);
    record('card_sprite', GODOT_CAPABILITIES.card_sprite);

    // --- Player color frame (always applicable) ---
    record('player_color_frame', GODOT_CAPABILITIES.player_color_frame);

    // --- Construction signal ---
    if (vs.backFrame === BACK_BOUGHT) {
        record('construction_signal', GODOT_CAPABILITIES.construction_signal);
    }

    // --- Construction timer ---
    if (so.constructionTimer !== null) {
        record('construction_timer', GODOT_CAPABILITIES.construction_timer);
    }

    // --- Blocking signal ---
    if (unit.state.blocking) {
        record('blocking_signal', GODOT_CAPABILITIES.blocking_signal);
    }

    // --- Attack signal (assigned to attack) ---
    if (unit.state.attacking) {
        record('attack_signal', GODOT_CAPABILITIES.attack_signal);
    }

    // --- Chill signal ---
    if ((unit.state.chilled || 0) > 0) {
        record('chill_signal', GODOT_CAPABILITIES.chill_signal);
    }

    // --- Damage signal ---
    if (vs.damageCounter > 0) {
        record('damage_signal', GODOT_CAPABILITIES.damage_signal);
    }

    // --- Attack icon ---
    // Use unit.stats.attack (from snapshot, authoritative) falling back to meta
    const unitAttack = unit.stats.attack || meta.attack || 0;
    if (unitAttack > 0) {
        record('attack_icon', GODOT_CAPABILITIES.attack_icon);
    }

    // --- Defense icon ---
    if (!meta.isFragile && meta.cardType !== 'spell' && (meta.toughness || 0) > 0) {
        record('defense_icon', GODOT_CAPABILITIES.defense_icon);
    }

    // --- HP icon (fragile units) ---
    if (meta.isFragile) {
        record('hp_icon', GODOT_CAPABILITIES.hp_icon);
    }

    // --- Frontline icon ---
    if (meta.isFrontline) {
        record('frontline_icon', GODOT_CAPABILITIES.frontline_icon);
    }

    // --- Delay icon ---
    if ((unit.state.delay || 0) > 0) {
        record('delay_icon', GODOT_CAPABILITIES.delay_icon);
    }

    // --- Lifespan icon ---
    if (unit.state.lifespan > 0) {
        record('lifespan_icon', GODOT_CAPABILITIES.lifespan_icon);
    }

    // --- Charge icon ---
    if ((unit.state.charge || 0) > 0) {
        record('charge_icon', GODOT_CAPABILITIES.charge_icon);
    }

    // --- Chill icon (number, separate from tint) ---
    if ((unit.state.chilled || 0) > 0) {
        record('chill_icon', GODOT_CAPABILITIES.chill_icon);
    }

    // --- P1 card flip ---
    if (unit.owner === 1) {
        record('p1_card_flip', GODOT_CAPABILITIES.p1_card_flip);
    }

    // --- Excluded features ---
    record('name_label', GODOT_CAPABILITIES.name_label);
    record('sellable_prompt', GODOT_CAPABILITIES.sellable_prompt);

    return results;
}

/**
 * Classify transition events between two snapshots.
 */
function classifyTransitions(prevSnapshot, currSnapshot) {
    const results = {};
    if (!currSnapshot.events || currSnapshot.events.length === 0) return results;

    const counts = { buy: 0, kill: 0, sacrifice: 0 };
    for (const evt of currSnapshot.events) {
        if (evt.type === 'buy') counts.buy++;
        if (evt.type === 'kill') counts.kill++;
        if (evt.type === 'sacrifice') counts.sacrifice++;
    }

    if (counts.buy > 0) {
        results.buy_effect = { count: counts.buy, capability: GODOT_CAPABILITIES.buy_effect };
    }
    if (counts.kill > 0 || counts.sacrifice > 0) {
        results.death_effect = {
            count: counts.kill + counts.sacrifice,
            capability: GODOT_CAPABILITIES.death_effect,
        };
    }

    // Damage effect: units that took damage between snapshots
    // We detect this by comparing HP of units present in both snapshots
    if (prevSnapshot) {
        const prevUnits = new Map();
        for (const p of prevSnapshot.players) {
            for (const u of p.units) {
                prevUnits.set(u.id, u);
            }
        }
        let damageCount = 0;
        for (const p of currSnapshot.players) {
            for (const u of p.units) {
                const prev = prevUnits.get(u.id);
                if (prev && u.stats.hp < prev.stats.hp) {
                    damageCount++;
                }
            }
        }
        if (damageCount > 0) {
            results.damage_effect = {
                count: damageCount,
                capability: GODOT_CAPABILITIES.damage_effect,
            };
        }
    }

    // Breach effect: check events for breach-related kills
    const breachKills = currSnapshot.events.filter(e =>
        e.type === 'kill' && e.cause === 'breach'
    );
    if (breachKills.length > 0) {
        results.breach_effect = {
            count: 1, // breach is one event regardless of how many units die
            capability: GODOT_CAPABILITIES.breach_effect,
        };
    }

    return results;
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

function initFeatureCounts() {
    const counts = {};
    for (const feature of Object.keys(GODOT_CAPABILITIES)) {
        counts[feature] = {
            applicable: 0,
            exact: 0,
            approximate: 0,
            unsupported: 0,
            excluded: 0,
            unauditable: 0,
            weight: WEIGHTS[feature] || 0,
        };
    }
    return counts;
}

function computeScores(counts, featureSet) {
    let sumExact = 0, sumApprox = 0, sumApplicable = 0;
    let weightedNum = 0, weightedDen = 0;

    for (const feature of featureSet) {
        const c = counts[feature];
        if (!c || c.applicable === 0 || GODOT_CAPABILITIES[feature] === 'excluded') continue;

        sumExact += c.exact;
        sumApprox += c.exact + c.approximate;
        sumApplicable += c.applicable;

        const w = c.weight;
        if (w > 0) {
            weightedNum += w * (c.exact + 0.5 * c.approximate) / c.applicable;
            weightedDen += w;
        }
    }

    return {
        rawExact: sumApplicable > 0 ? round4(sumExact / sumApplicable) : 0,
        rawExactApproximate: sumApplicable > 0 ? round4(sumApprox / sumApplicable) : 0,
        weighted: weightedDen > 0 ? round4(weightedNum / weightedDen) : 0,
    };
}

function round4(n) { return Math.round(n * 10000) / 10000; }

// ---------------------------------------------------------------------------
// Audit a single replay
// ---------------------------------------------------------------------------

function auditReplay(replayPath, options = {}) {
    const replay = loadReplay(replayPath);
    const snapshots = processReplayData(replay);
    const cardMeta = loadCardMeta();
    const colorOnBottom = 0; // P0 = bottom

    // Filter snapshots
    let targetSnapshots = snapshots;
    if (options.turn != null) {
        targetSnapshots = snapshots.filter(s => s.turn === options.turn);
        if (targetSnapshots.length === 0) {
            console.error(`No snapshots found for turn ${options.turn}`);
            process.exit(1);
        }
    }

    const counts = initFeatureCounts();
    let totalUnitRenders = 0;

    // State parity: classify each unit in each snapshot
    for (const snapshot of targetSnapshots) {
        for (const player of snapshot.players) {
            for (const unit of player.units) {
                const meta = cardMeta[unit.cardId] || {};
                const classification = classifyUnit(unit, meta, snapshot.phase, colorOnBottom);

                for (const [feature, state] of Object.entries(classification)) {
                    const c = counts[feature];
                    if (state === 'excluded') {
                        c.excluded++;
                    } else {
                        c.applicable++;
                        c[state]++;
                    }
                }
                totalUnitRenders++;
            }
        }
    }

    // Transition parity: classify events between consecutive snapshots
    for (let i = 1; i < targetSnapshots.length; i++) {
        const transitions = classifyTransitions(targetSnapshots[i - 1], targetSnapshots[i]);
        for (const [feature, info] of Object.entries(transitions)) {
            const c = counts[feature];
            c.applicable += info.count;
            c[info.capability] += info.count;
        }
    }

    // Get reference commits
    const pixiCommit = getGitCommit(PRISMATA_LADDER_PATH);
    const godotCommit = getGitCommit(PRISMATA_3D_PATH);

    // Compute scores
    const stateScores = computeScores(counts, STATE_FEATURES);
    const transitionScores = computeScores(counts, TRANSITION_FEATURES);
    const allFeatures = new Set([...STATE_FEATURES, ...TRANSITION_FEATURES]);
    const combinedScores = computeScores(counts, allFeatures);

    // Identify gaps
    const rendererGaps = [];
    const dataModelGaps = [];
    for (const [feature, cap] of Object.entries(GODOT_CAPABILITIES)) {
        if (cap === 'unsupported' && counts[feature].applicable > 0) {
            rendererGaps.push(feature);
        }
    }
    // Known data model gaps
    if (counts.sellable_prompt && counts.sellable_prompt.excluded > 0) {
        dataModelGaps.push('boughtThisPhase', 'sellable');
    }

    const replayId = replay.code || path.basename(replayPath, path.extname(replayPath));

    return {
        auditVersion: 2,
        pixiReference: {
            repo: '<ladder>-site',
            path: 'src/components/game-renderer/',
            commit: pixiCommit,
        },
        godotReference: {
            repo: 'prismata-3d',
            capabilityModelVersion: CAPABILITY_MODEL_VERSION,
            commit: godotCommit,
        },
        replayId,
        snapshotCount: targetSnapshots.length,
        unitRenderCount: totalUnitRenders,
        stateParity: extractFeatureCounts(counts, STATE_FEATURES),
        transitionParity: extractFeatureCounts(counts, TRANSITION_FEATURES),
        scores: {
            state: stateScores,
            transition: transitionScores,
            combined: combinedScores,
        },
        gapClassification: {
            rendererGaps,
            dataModelGaps,
        },
    };
}

function extractFeatureCounts(counts, featureSet) {
    const result = {};
    for (const feature of featureSet) {
        if (counts[feature]) {
            result[feature] = { ...counts[feature] };
        }
    }
    return result;
}

function getGitCommit(repoPath) {
    try {
        return execSync(`git -C "${repoPath}" rev-parse --short HEAD`, { encoding: 'utf-8' }).trim();
    } catch {
        return 'unknown';
    }
}

// ---------------------------------------------------------------------------
// Human-readable report
// ---------------------------------------------------------------------------

function printReport(report, verbose) {
    console.log('=== Visual Fidelity Audit ===');
    console.log(`Replay: ${report.replayId}`);
    console.log(`PixiJS: ${report.pixiReference.repo} @ ${report.pixiReference.commit}`);
    console.log(`Godot:  ${report.godotReference.repo} @ ${report.godotReference.commit}  (capability model ${report.godotReference.capabilityModelVersion})`);
    console.log(`Snapshots: ${report.snapshotCount}  |  Unit-renders: ${report.unitRenderCount}`);
    console.log('');

    // State parity
    printFeatureSection('STATE PARITY', report.stateParity);

    // Transition parity
    console.log('');
    printFeatureSection('TRANSITION PARITY', report.transitionParity);

    // Gap classification
    console.log('');
    console.log('GAP CLASSIFICATION:');
    console.log(`  Renderer gaps:    ${report.gapClassification.rendererGaps.length} features (need Godot implementation)`);
    console.log(`  Data-model gaps:  ${report.gapClassification.dataModelGaps.length} features (need snapshot schema additions)`);

    // Scores
    console.log('');
    console.log('SCORES:');
    const s = report.scores;
    console.log(`  State:      exact ${pct(s.state.rawExact)}  |  exact+approx ${pct(s.state.rawExactApproximate)}  |  weighted ${pct(s.state.weighted)}`);
    console.log(`  Transition: exact ${pct(s.transition.rawExact)}  |  exact+approx ${pct(s.transition.rawExactApproximate)}  |  weighted ${pct(s.transition.weighted)}`);
    console.log(`  Combined:   exact ${pct(s.combined.rawExact)}  |  exact+approx ${pct(s.combined.rawExactApproximate)}  |  weighted ${pct(s.combined.weighted)}`);
}

function printFeatureSection(title, features) {
    console.log(`${title} (sorted by unsupported count):`);

    // Sort by unsupported count descending
    const sorted = Object.entries(features).sort((a, b) => {
        if (GODOT_CAPABILITIES[a[0]] === 'excluded' && GODOT_CAPABILITIES[b[0]] !== 'excluded') return 1;
        if (GODOT_CAPABILITIES[b[0]] === 'excluded' && GODOT_CAPABILITIES[a[0]] !== 'excluded') return -1;
        return (b[1].unsupported || 0) - (a[1].unsupported || 0);
    });

    for (const [feature, c] of sorted) {
        if (GODOT_CAPABILITIES[feature] === 'excluded') {
            console.log(`  ${feature}`);
            console.log(`    excluded (intentional)`);
        } else if (c.applicable > 0) {
            console.log(`  ${feature}`);
            console.log(`    applicable: ${pad(c.applicable)}  exact: ${pad(c.exact)}  approximate: ${pad(c.approximate)}  unsupported: ${pad(c.unsupported)}  unauditable: ${pad(c.unauditable)}`);
        }
    }
}

function pct(n) { return (n * 100).toFixed(1) + '%'; }
function pad(n) { return String(n).padStart(5); }

// ---------------------------------------------------------------------------
// Batch mode
// ---------------------------------------------------------------------------

function auditBatch(count, seed) {
    const rng = seedRng(seed);
    const replayFiles = findReplayFiles();

    if (replayFiles.length === 0) {
        console.error(`No replay files found in ${REPLAY_ARCHIVE_PATH}`);
        process.exit(1);
    }

    // Sample N replays
    const sampled = sampleArray(replayFiles, count, rng);
    console.log(`=== Batch Visual Fidelity Audit (${sampled.length} replays, seed=${seed}) ===`);

    const allCounts = initFeatureCounts();
    let totalUnitRenders = 0;
    const perReplayScores = [];
    const sampledIds = [];
    let errors = 0;

    for (let i = 0; i < sampled.length; i++) {
        const file = sampled[i];
        try {
            const report = auditReplay(file);
            sampledIds.push(report.replayId);
            totalUnitRenders += report.unitRenderCount;

            // Aggregate counts
            for (const bucket of ['stateParity', 'transitionParity']) {
                for (const [feature, c] of Object.entries(report[bucket])) {
                    const ac = allCounts[feature];
                    ac.applicable += c.applicable;
                    ac.exact += c.exact;
                    ac.approximate += c.approximate;
                    ac.unsupported += c.unsupported;
                    ac.excluded += c.excluded;
                    ac.unauditable += c.unauditable;
                }
            }

            perReplayScores.push(report.scores);
            process.stderr.write(`\r  ${i + 1}/${sampled.length} replays processed`);
        } catch (err) {
            errors++;
            process.stderr.write(`\r  ${i + 1}/${sampled.length} (${errors} errors)`);
        }
    }
    process.stderr.write('\n');

    if (perReplayScores.length === 0) {
        console.error('No replays processed successfully');
        process.exit(1);
    }

    // Print batch report
    console.log(`Total unit-renders: ${totalUnitRenders.toLocaleString()}`);
    if (errors > 0) console.log(`Errors: ${errors} replays failed`);
    console.log('');

    console.log('AGGREGATED STATE PARITY:');
    for (const feature of STATE_FEATURES) {
        const c = allCounts[feature];
        if (GODOT_CAPABILITIES[feature] === 'excluded') continue;
        if (c.applicable === 0) continue;
        const dominant = c.unsupported > c.approximate && c.unsupported > c.exact
            ? 'unsupported' : c.approximate > c.exact ? 'approximate' : 'exact';
        const dominantCount = c[dominant];
        const pctVal = (dominantCount / c.applicable * 100).toFixed(1);
        console.log(`  ${feature.padEnd(24)} ${pad(dominantCount)}/${pad(c.applicable)} (${pctVal.padStart(5)}%) ${dominant}`);
    }

    console.log('');
    console.log(`SCORES (across ${perReplayScores.length} replays):`);
    const stateExacts = perReplayScores.map(s => s.state.rawExact);
    const transExacts = perReplayScores.map(s => s.transition.rawExact);
    const combinedWeighted = perReplayScores.map(s => s.combined.weighted);
    console.log(`  State:      exact avg ${pct(avg(stateExacts))} (min ${pct(min(stateExacts))}, max ${pct(max(stateExacts))})`);
    console.log(`  Transition: exact avg ${pct(avg(transExacts))} (min ${pct(min(transExacts))}, max ${pct(max(transExacts))})`);
    console.log(`  Combined weighted: avg ${pct(avg(combinedWeighted))} (min ${pct(min(combinedWeighted))}, max ${pct(max(combinedWeighted))})`);

    return {
        auditVersion: 2,
        batchSize: sampled.length,
        seed,
        sampledReplayIds: sampledIds,
        totalUnitRenders,
        errors,
        aggregatedCounts: allCounts,
        scores: {
            state: { avg: avg(stateExacts), min: min(stateExacts), max: max(stateExacts) },
            transition: { avg: avg(transExacts), min: min(transExacts), max: max(transExacts) },
            combinedWeighted: { avg: avg(combinedWeighted), min: min(combinedWeighted), max: max(combinedWeighted) },
        },
    };
}

function findReplayFiles() {
    if (!fs.existsSync(REPLAY_ARCHIVE_PATH)) return [];
    const files = [];
    for (const entry of fs.readdirSync(REPLAY_ARCHIVE_PATH)) {
        if (entry.endsWith('.json.gz') || entry.endsWith('.json')) {
            files.push(path.join(REPLAY_ARCHIVE_PATH, entry));
        }
    }
    return files;
}

// Simple seedable RNG (xorshift32)
function seedRng(seed) {
    let state = seed | 0;
    if (state === 0) state = 1;
    return function() {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        return (state >>> 0) / 4294967296;
    };
}

function sampleArray(arr, n, rng) {
    const copy = [...arr];
    const result = [];
    const count = Math.min(n, copy.length);
    for (let i = 0; i < count; i++) {
        const idx = Math.floor(rng() * copy.length);
        result.push(copy[idx]);
        copy.splice(idx, 1);
    }
    return result;
}

function timestamp() {
    const d = new Date();
    return d.getFullYear()
        + '-' + String(d.getMonth() + 1).padStart(2, '0')
        + '-' + String(d.getDate()).padStart(2, '0')
        + '_' + String(d.getHours()).padStart(2, '0')
        + String(d.getMinutes()).padStart(2, '0')
        + String(d.getSeconds()).padStart(2, '0');
}

function avg(arr) { return arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }
function min(arr) { return arr.length > 0 ? Math.min(...arr) : 0; }
function max(arr) { return arr.length > 0 ? Math.max(...arr) : 0; }

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);

    if (args.includes('--capabilities')) {
        console.log('=== Godot Capability Model ===');
        console.log(`Version: ${CAPABILITY_MODEL_VERSION}`);
        console.log('');
        console.log('State features:');
        for (const f of STATE_FEATURES) {
            console.log(`  ${f.padEnd(24)} ${GODOT_CAPABILITIES[f]}`);
        }
        console.log('');
        console.log('Transition features:');
        for (const f of TRANSITION_FEATURES) {
            console.log(`  ${f.padEnd(24)} ${GODOT_CAPABILITIES[f]}`);
        }
        return;
    }

    const batchIdx = args.indexOf('--batch');
    if (batchIdx !== -1) {
        const count = parseInt(args[batchIdx + 1]) || 50;
        const seedIdx = args.indexOf('--seed');
        const seed = seedIdx !== -1 ? parseInt(args[seedIdx + 1]) : Date.now();
        const outputIdx = args.indexOf('--output');

        const report = auditBatch(count, seed);

        const outPath = outputIdx !== -1
            ? args[outputIdx + 1]
            : `audit_batch_${timestamp()}.json`;
        fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
        console.log(`\nJSON report written to ${outPath}`);
        return;
    }

    // Single replay mode
    const replayPath = args.find(a => !a.startsWith('--'));
    if (!replayPath) {
        console.error('Usage: node tools/audit_visual_fidelity.js <replay.json[.gz]> [--turn N] [--verbose] [--output path]');
        console.error('       node tools/audit_visual_fidelity.js --batch N [--seed S] [--output path]');
        console.error('       node tools/audit_visual_fidelity.js --capabilities');
        process.exit(1);
    }

    const turnIdx = args.indexOf('--turn');
    const turn = turnIdx !== -1 ? parseInt(args[turnIdx + 1]) : undefined;
    const verbose = args.includes('--verbose');
    const outputIdx = args.indexOf('--output');

    const report = auditReplay(replayPath, { turn, verbose });
    printReport(report, verbose);

    const outPath = outputIdx !== -1
        ? args[outputIdx + 1]
        : `audit_${report.replayId.replace(/[^a-zA-Z0-9_-]/g, '_')}_${timestamp()}.json`;
    fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
    console.log(`\nJSON report written to ${outPath}`);
}

if (require.main === module) {
    main();
}

module.exports = {
    auditReplay,
    auditBatch,
    classifyUnit,
    classifyTransitions,
    GODOT_CAPABILITIES,
    CAPABILITY_MODEL_VERSION,
    STATE_FEATURES,
    TRANSITION_FEATURES,
    WEIGHTS,
};
