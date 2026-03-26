#!/usr/bin/env node
// tools/compare_layouts.js
// Compares PixiJS layout engine vs Godot layout engine for the same replay/snapshot.
//
// Both engines are AS3 ports. This tool runs both pipelines in pure Node.js
// and diffs unit positions numerically.
//
// Usage:
//   node tools/compare_layouts.js <replay.json[.gz]> [--turn N] [--all] [--verbose]
//   node tools/compare_layouts.js --snapshots <snapshots.json> [--turn N] [--all]

const fs = require('fs');
const path = require('path');
const { processReplayData, loadReplay } = require('./replay_to_snapshots');
const { computePosition, positionToRow, POSITIONS: P } = require('./position_calculator');
const { buildCardIdMap } = require('./card_id_map');

// ---------------------------------------------------------------------------
// PixiJS layout constants (from constants.ts — pixel-based)
// ---------------------------------------------------------------------------
const PIXI = {
    CARD_WIDTH: 83,
    CARD_HEIGHT: 82,
    CARDSPACING: [0, 18, 18, 18, 17, 17, 17, 16],
    DEFAULTCARDSPACING: 16,
    DEFAULTMARGIN: 20,
    CRAMMEDMARGIN: -40,
    MIN_CRAM_PERCENT: 0.8,
    GAP_SIZE: 2.5,
    MID_LINE_GUTTER_REPLAY: 2,
    ROW_GAP_REPLAY: 1,
};

// ---------------------------------------------------------------------------
// Godot layout constants (from layout_engine.gd — world-unit based)
// ---------------------------------------------------------------------------
const GODOT = {
    CARD_UNIT: 1.0,
    CARDSPACING: [0.0, 0.217, 0.217, 0.217, 0.205, 0.205, 0.205, 0.193],
    DEFAULTCARDSPACING: 0.193,
    DEFAULTMARGIN: 0.241,
    CRAMMEDMARGIN: -0.482,
    MIN_CRAM_PERCENT: 0.8,
    GAP_SIZE: 2.5,
    ROW_Z: { front: 1.5, middle: 3.5, back: 5.5 },
    ROW_WIDTH: 20.0,
};

// ---------------------------------------------------------------------------
// PixiJS layout engine (faithful port of layout-engine.ts)
// ---------------------------------------------------------------------------

function pixiStretchFactor(i, len, cramFactor) {
    if (len > 28 && cramFactor > 0) {
        cramFactor = Math.max(cramFactor, 1 + (len - 28) / 45);
    }
    let fullyCrammedAmount;
    if (len < 5) {
        fullyCrammedAmount = 1;
    } else if (i < len - 10) {
        fullyCrammedAmount = 0.58;
    } else if (i < len - 3) {
        fullyCrammedAmount = 1 - 0.06 * (len - 3 - i);
    } else {
        fullyCrammedAmount = 1;
    }
    if (cramFactor < 1) return 1;
    if (cramFactor >= 1.5) {
        if (i < len - 10) {
            const cramIndex = Math.max(0, Math.min(10, len - 10 - i));
            const cramAmount = Math.max(1.5, Math.min(cramFactor, 2.5)) - 1.5;
            return fullyCrammedAmount - 0.03 * cramIndex * cramAmount;
        }
        return fullyCrammedAmount;
    }
    return 2 * (cramFactor - 1) * fullyCrammedAmount + 2 * (1.5 - cramFactor);
}

function pixiDesiredSpacing(numCards) {
    if (numCards > PIXI.CARDSPACING.length) return PIXI.DEFAULTCARDSPACING;
    return PIXI.CARDSPACING[numCards - 1];
}

function pixiPileWidth(cardCount, cramFactor) {
    if (cardCount <= 0) return 0;
    const spacing = pixiDesiredSpacing(cardCount);
    let w = PIXI.CARD_WIDTH;
    for (let i = 0; i < cardCount - 1; i++) {
        w += pixiStretchFactor(i, cardCount, cramFactor) * spacing;
    }
    return w;
}

function pixiPileGap(cardCount, cramFactor) {
    if (cardCount <= 1) return 0;
    const spacing = pixiDesiredSpacing(cardCount);
    let sumSf = 0;
    for (let i = 0; i < cardCount - 1; i++) {
        sumSf += pixiStretchFactor(i, cardCount, cramFactor);
    }
    return (sumSf / (cardCount - 1)) * spacing;
}

function pixiPerformCramming(piles, rowWidth) {
    const n = piles.length;
    if (n === 0) return [];
    const numGaps = n - 1;

    let prelimWidth = 0;
    for (let p = 0; p < n; p++) {
        prelimWidth += pixiPileWidth(piles[p].cardCount, 0);
        if (p < n - 1) prelimWidth += PIXI.DEFAULTMARGIN;
    }

    const cramFactor = prelimWidth / (PIXI.MIN_CRAM_PERCENT * rowWidth);

    const widths = piles.map(p => pixiPileWidth(p.cardCount, cramFactor));
    const totalPileArea = widths.reduce((a, b) => a + b, 0);

    const positions = [];
    if (cramFactor <= 1) {
        const totalW = totalPileArea + numGaps * PIXI.DEFAULTMARGIN;
        const startX = (rowWidth - totalW) / 2;
        let x = startX;
        for (let p = 0; p < n; p++) {
            positions.push({ x, gap: pixiPileGap(piles[p].cardCount, 0) });
            x += widths[p];
            if (p < n - 1) x += PIXI.DEFAULTMARGIN;
        }
        return positions;
    }

    const marginSpace = rowWidth - totalPileArea;
    const margin = numGaps > 0
        ? Math.max(PIXI.CRAMMEDMARGIN, Math.min(PIXI.DEFAULTMARGIN, marginSpace / numGaps))
        : 0;
    const actualTotal = totalPileArea + numGaps * margin;
    const startX = Math.max(0, (rowWidth - actualTotal) / 2);

    let x = startX;
    for (let p = 0; p < n; p++) {
        positions.push({ x, gap: pixiPileGap(piles[p].cardCount, cramFactor) });
        x += widths[p];
        if (p < n - 1) x += margin;
    }
    return positions;
}

// ---------------------------------------------------------------------------
// Godot layout engine (faithful port of layout_engine.gd)
// ---------------------------------------------------------------------------

function godotStretchFactor(i, len, cramFactor) {
    let cf = cramFactor;
    if (len > 28 && cf > 0) {
        cf = Math.max(cf, 1.0 + (len - 28) / 45.0);
    }
    let fullyCramped;
    if (len < 5) {
        fullyCramped = 1.0;
    } else if (i < len - 10) {
        fullyCramped = 0.58;
    } else if (i < len - 3) {
        fullyCramped = 1.0 - 0.06 * (len - 3 - i);
    } else {
        fullyCramped = 1.0;
    }
    if (cf < 1.0) return 1.0;
    if (cf >= 1.5) {
        if (i < len - 10) {
            const cramIndex = Math.max(0, Math.min(10, len - 10 - i));
            const cramAmount = Math.max(1.5, Math.min(cf, 2.5)) - 1.5;
            return fullyCramped - 0.03 * cramIndex * cramAmount;
        }
        return fullyCramped;
    }
    return 2.0 * (cf - 1.0) * fullyCramped + 2.0 * (1.5 - cf);
}

function godotDesiredSpacing(numCards) {
    if (numCards <= 0) return 0.0;
    if (numCards > GODOT.CARDSPACING.length) return GODOT.DEFAULTCARDSPACING;
    return GODOT.CARDSPACING[numCards - 1];
}

function godotPileWidth(cardCount, cramFactor) {
    if (cardCount <= 0) return 0.0;
    const spacing = godotDesiredSpacing(cardCount);
    let w = GODOT.CARD_UNIT;
    for (let i = 0; i < cardCount - 1; i++) {
        w += godotStretchFactor(i, cardCount, cramFactor) * spacing;
    }
    return w;
}

function godotPileGap(cardCount, cramFactor) {
    if (cardCount <= 1) return 0.0;
    const spacing = godotDesiredSpacing(cardCount);
    let sumSf = 0.0;
    for (let i = 0; i < cardCount - 1; i++) {
        sumSf += godotStretchFactor(i, cardCount, cramFactor);
    }
    return (sumSf / (cardCount - 1)) * spacing;
}

function godotComputeRowLayout(pileCounts, rowWidth) {
    const n = pileCounts.length;
    if (n === 0) return [];
    const numGaps = n - 1;

    let prelimWidth = 0.0;
    for (let p = 0; p < n; p++) {
        prelimWidth += godotPileWidth(pileCounts[p], 0.0);
        if (p < n - 1) prelimWidth += GODOT.DEFAULTMARGIN;
    }

    const cramFactor = prelimWidth / (GODOT.MIN_CRAM_PERCENT * rowWidth);

    const widths = pileCounts.map(c => godotPileWidth(c, cramFactor));
    const totalPileArea = widths.reduce((a, b) => a + b, 0.0);

    const results = [];
    if (cramFactor <= 1.0) {
        const totalW = totalPileArea + numGaps * GODOT.DEFAULTMARGIN;
        const startX = (rowWidth - totalW) / 2.0;
        let x = startX;
        for (let p = 0; p < n; p++) {
            results.push({ x, gap: godotPileGap(pileCounts[p], 0.0) });
            x += widths[p];
            if (p < n - 1) x += GODOT.DEFAULTMARGIN;
        }
        return results;
    }

    const marginSpace = rowWidth - totalPileArea;
    const margin = numGaps > 0
        ? Math.max(GODOT.CRAMMEDMARGIN, Math.min(GODOT.DEFAULTMARGIN, marginSpace / numGaps))
        : GODOT.DEFAULTMARGIN;
    const actualTotal = totalPileArea + numGaps * margin;
    const startX = Math.max(0.0, (rowWidth - actualTotal) / 2.0);

    let x = startX;
    for (let p = 0; p < n; p++) {
        results.push({ x, gap: godotPileGap(pileCounts[p], cramFactor) });
        x += widths[p];
        if (p < n - 1) x += margin;
    }
    return results;
}

// ---------------------------------------------------------------------------
// Card library for position calculation
// ---------------------------------------------------------------------------
const CARD_LIBRARY_PATH = path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso');
const cardLibrary = JSON.parse(fs.readFileSync(CARD_LIBRARY_PATH, 'utf-8'));
const cardIdMap = buildCardIdMap(CARD_LIBRARY_PATH);

// Reverse lookup: cardId -> cardLibrary entry (for position calculation)
const cardIdToLibEntry = {};
for (const [internalName, entry] of Object.entries(cardIdMap)) {
    cardIdToLibEntry[entry.cardId] = { ...cardLibrary[internalName], UIName: entry.displayName, cardName: internalName };
}

// ---------------------------------------------------------------------------
// Layout pipeline: run both engines on a snapshot
// ---------------------------------------------------------------------------

/**
 * Run the PixiJS layout pipeline on a snapshot.
 * Returns per-unit positions in NORMALIZED coordinates (pixels / CARD_WIDTH).
 */
function pixiLayout(snapshot, fieldWidth) {
    // PixiJS rowWidth = fieldWidth in pixels
    const rowWidth = fieldWidth || 720;  // typical game field width

    const results = {};  // unitId -> { normX, normY, row, pileIdx, cardIdx, cardId }

    for (let owner = 0; owner < 2; owner++) {
        const player = snapshot.players[owner];
        const units = player.units;

        // Group by row
        const rowGroups = { front: [], middle: [], back: [] };
        for (const unit of units) {
            const row = unit.render ? unit.render.row : 'middle';
            if (!rowGroups[row]) rowGroups[row] = [];
            rowGroups[row].push(unit);
        }

        const isTop = owner === 1;
        const gutter = PIXI.MID_LINE_GUTTER_REPLAY;
        const rowGap = PIXI.ROW_GAP_REPLAY;

        // Row Y positions (PixiJS BoardView.ts)
        const rowYPositions = {};
        if (isTop) {
            rowYPositions.front  = -(PIXI.CARD_HEIGHT + gutter);
            rowYPositions.middle = -(2 * PIXI.CARD_HEIGHT + rowGap + gutter);
            rowYPositions.back   = -(3 * PIXI.CARD_HEIGHT + 2 * rowGap + gutter);
        } else {
            rowYPositions.front  = gutter;
            rowYPositions.middle = PIXI.CARD_HEIGHT + rowGap + gutter;
            rowYPositions.back   = 2 * PIXI.CARD_HEIGHT + 2 * rowGap + gutter;
        }

        for (const rowName of ['front', 'middle', 'back']) {
            const unitsInRow = rowGroups[rowName];
            if (!unitsInRow || unitsInRow.length === 0) continue;

            // Group by cardId (PixiJS groups by cardName)
            const piles = {};
            const pileSlots = {};
            for (const unit of unitsInRow) {
                const key = unit.cardId;
                if (!piles[key]) {
                    piles[key] = [];
                    pileSlots[key] = unit.render ? unit.render.slot : 15;
                }
                piles[key].push(unit);
            }

            // Sort piles by slot position
            const sortedKeys = Object.keys(piles).sort((a, b) => pileSlots[a] - pileSlots[b]);

            // Build pile inputs
            const pileInputs = sortedKeys.map(key => ({
                cardCount: piles[key].length,
                hasBigGap: false,  // RowView passes false; big gap is at PileView level
            }));

            // Run PixiJS cramming
            const positions = pixiPerformCramming(pileInputs, rowWidth);

            // Position each unit
            const rowY = rowYPositions[rowName];
            for (let pIdx = 0; pIdx < sortedKeys.length; pIdx++) {
                const key = sortedKeys[pIdx];
                const pileUnits = piles[key];
                const pos = positions[pIdx];
                const gap = pos.gap;

                // Sort within pile: constructionTime DESC, boughtThisPhase DESC
                pileUnits.sort((a, b) => {
                    const aBt = a.state ? a.state.buildTurnsRemaining || 0 : 0;
                    const bBt = b.state ? b.state.buildTurnsRemaining || 0 : 0;
                    return bBt - aBt;
                });

                for (let cIdx = 0; cIdx < pileUnits.length; cIdx++) {
                    const unit = pileUnits[cIdx];
                    const pixelX = pos.x + cIdx * gap;
                    const pixelY = rowY;

                    // Normalize: divide by CARD_WIDTH, center-relative (subtract half row width)
                    const pixiRowWidthInCards = rowWidth / PIXI.CARD_WIDTH;
                    results[unit.id] = {
                        normX: (pixelX / PIXI.CARD_WIDTH) - pixiRowWidthInCards / 2,
                        normY: pixelY / PIXI.CARD_WIDTH,
                        row: rowName,
                        owner: owner,
                        pileIdx: pIdx,
                        cardIdx: cIdx,
                        cardId: unit.cardId,
                        displayName: unit.displayName,
                        rawPixelX: pixelX,
                        rawPixelY: pixelY,
                    };
                }
            }
        }
    }
    return results;
}

/**
 * Run the Godot layout pipeline on a snapshot.
 * @param rowWidthOverride - if provided, use this row width (in card-units) instead of GODOT.ROW_WIDTH.
 *                           Use this to match PixiJS field width for algorithm comparison.
 */
function godotLayout(snapshot, rowWidthOverride) {
    const effectiveRowWidth = rowWidthOverride || GODOT.ROW_WIDTH;
    const results = {};

    for (let owner = 0; owner < 2; owner++) {
        const player = snapshot.players[owner];
        const units = player.units;

        // Group by row
        const rowGroups = { front: [], middle: [], back: [] };
        for (const unit of units) {
            const row = unit.render ? unit.render.row : 'middle';
            if (!rowGroups[row]) rowGroups[row] = [];
            rowGroups[row].push(unit);
        }

        for (const rowName of ['front', 'middle', 'back']) {
            const unitsInRow = rowGroups[rowName];
            if (!unitsInRow || unitsInRow.length === 0) continue;

            // Group by cardId
            const piles = {};
            const pileSlots = {};
            for (const unit of unitsInRow) {
                const key = unit.cardId;
                if (!piles[key]) {
                    piles[key] = [];
                    pileSlots[key] = unit.render ? unit.render.slot : 15;
                }
                piles[key].push(unit);
            }

            // Sort piles by slot position
            const sortedKeys = Object.keys(piles).sort((a, b) => pileSlots[a] - pileSlots[b]);

            // Build pile counts
            const pileCounts = sortedKeys.map(key => piles[key].length);

            // Run Godot cramming
            const layouts = godotComputeRowLayout(pileCounts, effectiveRowWidth);

            // Position each unit
            let zOffset = GODOT.ROW_Z[rowName] || 3.5;
            if (owner === 1) zOffset = -zOffset;

            for (let pIdx = 0; pIdx < sortedKeys.length; pIdx++) {
                const key = sortedKeys[pIdx];
                const pileUnits = piles[key];
                const layout = layouts[pIdx];
                const gap = layout.gap;

                // Sort within pile: buildTurnsRemaining DESC
                pileUnits.sort((a, b) => {
                    const aBt = a.state ? a.state.buildTurnsRemaining || 0 : 0;
                    const bBt = b.state ? b.state.buildTurnsRemaining || 0 : 0;
                    return bBt - aBt;
                });

                for (let cIdx = 0; cIdx < pileUnits.length; cIdx++) {
                    const unit = pileUnits[cIdx];
                    const xPos = layout.x + cIdx * gap;
                    const centeredX = xPos - effectiveRowWidth / 2.0;

                    results[unit.id] = {
                        normX: xPos - effectiveRowWidth / 2.0,  // center-relative
                        normZ: zOffset,
                        godotX: centeredX,
                        godotZ: zOffset,
                        row: rowName,
                        owner: owner,
                        pileIdx: pIdx,
                        cardIdx: cIdx,
                        cardId: unit.cardId,
                        displayName: unit.displayName,
                    };
                }
            }
        }
    }
    return results;
}

// ---------------------------------------------------------------------------
// Comparison logic
// ---------------------------------------------------------------------------

/**
 * Compare PixiJS and Godot layouts for a single snapshot.
 * Returns a diff report.
 */
/**
 * Compare PixiJS and Godot layouts for a single snapshot.
 * @param mode - 'algorithm' (same row width, verify port) or 'visual' (actual widths, show real diffs)
 */
function compareSnapshot(snapshot, pixiFieldWidth, mode, customGodotWidth) {
    const pixiPositions = pixiLayout(snapshot, pixiFieldWidth);
    let godotPositions;
    if (mode === 'visual') {
        const gw = customGodotWidth || GODOT.ROW_WIDTH;
        godotPositions = godotLayout(snapshot, gw);
    } else {
        // 'algorithm' — use same row width to verify algorithm correctness
        const pixiRowWidthInCards = pixiFieldWidth / PIXI.CARD_WIDTH;
        godotPositions = godotLayout(snapshot, pixiRowWidthInCards);
    }

    const allUnitIds = new Set([...Object.keys(pixiPositions), ...Object.keys(godotPositions)]);
    const diffs = [];
    let totalUnits = 0;
    let matchingUnits = 0;

    for (const idStr of allUnitIds) {
        const id = parseInt(idStr);
        const pixi = pixiPositions[id];
        const godot = godotPositions[id];

        if (!pixi || !godot) {
            diffs.push({
                unitId: id,
                issue: !pixi ? 'missing_in_pixi' : 'missing_in_godot',
                cardId: (pixi || godot).cardId,
                displayName: (pixi || godot).displayName,
            });
            continue;
        }

        totalUnits++;

        // Compare structural properties
        const rowMatch = pixi.row === godot.row;
        const pileMatch = pixi.pileIdx === godot.pileIdx;
        const cardIdxMatch = pixi.cardIdx === godot.cardIdx;

        // Compare X positions — both are center-relative in card-units at the same row width
        const xDiff = Math.abs(pixi.normX - godot.normX);

        // Threshold: 0.01 card-widths (~0.8px at 83px/card)
        const X_THRESHOLD = 0.01;
        const xMatch = xDiff < X_THRESHOLD;

        if (rowMatch && pileMatch && cardIdxMatch && xMatch) {
            matchingUnits++;
        } else {
            diffs.push({
                unitId: id,
                issue: 'position_mismatch',
                cardId: pixi.cardId,
                displayName: pixi.displayName,
                owner: pixi.owner,
                rowMatch,
                pileMatch,
                cardIdxMatch,
                xDiff: xDiff.toFixed(6),
                pixi: { propX: pixi.normX.toFixed(6), row: pixi.row, pile: pixi.pileIdx, idx: pixi.cardIdx },
                godot: { propX: godot.normX.toFixed(6), row: godot.row, pile: godot.pileIdx, idx: godot.cardIdx },
            });
        }
    }

    return {
        seq: snapshot.seq,
        turn: snapshot.turn,
        phase: snapshot.phase,
        totalUnits,
        matchingUnits,
        matchPct: totalUnits > 0 ? ((matchingUnits / totalUnits) * 100).toFixed(1) : '100.0',
        diffs,
    };
}

// ---------------------------------------------------------------------------
// Constant comparison: verify the Godot constants are correct conversions
// ---------------------------------------------------------------------------

function compareConstants() {
    const issues = [];

    // Check CARDSPACING conversion (pixel / CARD_WIDTH = world-unit)
    for (let i = 0; i < PIXI.CARDSPACING.length; i++) {
        const expected = PIXI.CARDSPACING[i] / PIXI.CARD_WIDTH;
        const actual = GODOT.CARDSPACING[i];
        const diff = Math.abs(expected - actual);
        if (diff > 0.002) {
            issues.push(`CARDSPACING[${i}]: PixiJS=${PIXI.CARDSPACING[i]}px → expected ${expected.toFixed(4)}, Godot=${actual.toFixed(4)}, diff=${diff.toFixed(4)}`);
        }
    }

    // Check other constants
    const checks = [
        ['DEFAULTCARDSPACING', PIXI.DEFAULTCARDSPACING / PIXI.CARD_WIDTH, GODOT.DEFAULTCARDSPACING],
        ['DEFAULTMARGIN', PIXI.DEFAULTMARGIN / PIXI.CARD_WIDTH, GODOT.DEFAULTMARGIN],
        ['CRAMMEDMARGIN', PIXI.CRAMMEDMARGIN / PIXI.CARD_WIDTH, GODOT.CRAMMEDMARGIN],
    ];
    for (const [name, expected, actual] of checks) {
        const diff = Math.abs(expected - actual);
        if (diff > 0.002) {
            issues.push(`${name}: expected ${expected.toFixed(4)}, Godot=${actual.toFixed(4)}, diff=${diff.toFixed(4)}`);
        }
    }

    return issues;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);

    if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
        console.log('Usage: node tools/compare_layouts.js <replay.json[.gz]> [options]');
        console.log('       node tools/compare_layouts.js --snapshots <snapshots.json> [options]');
        console.log('');
        console.log('Options:');
        console.log('  --turn N       Compare only turn N (default: all turns)');
        console.log('  --seq N        Compare only seq N');
        console.log('  --all          Show all diffs, not just summary');
        console.log('  --verbose      Show per-unit details even for matching units');
        console.log('  --field-width  PixiJS field width in pixels (default: 720)');
        console.log('  --constants    Only compare layout constants (no replay needed)');
        console.log('  --snapshots F  Use pre-computed snapshots file');
        console.log('  --mode M       "algorithm" (same row width, default) or "visual" (actual widths)');
        console.log('  --godot-width  Godot row width in card-units (default: 20, only for visual mode)');
        console.log('  --sweep        Sweep Godot row widths from 8-24 to find optimal match');
        process.exit(0);
    }

    // Parse args
    const verbose = args.includes('--verbose');
    const showAll = args.includes('--all');
    const constantsOnly = args.includes('--constants');
    let turnFilter = null;
    let seqFilter = null;
    let fieldWidth = 720;
    let snapshotsFile = null;
    let replayFile = null;
    let mode = 'algorithm';
    let godotWidth = null;  // null = use GODOT.ROW_WIDTH
    const doSweep = args.includes('--sweep');

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--turn' && args[i + 1]) turnFilter = parseInt(args[i + 1]);
        if (args[i] === '--seq' && args[i + 1]) seqFilter = parseInt(args[i + 1]);
        if (args[i] === '--field-width' && args[i + 1]) fieldWidth = parseInt(args[i + 1]);
        if (args[i] === '--snapshots' && args[i + 1]) snapshotsFile = args[i + 1];
        if (args[i] === '--mode' && args[i + 1]) mode = args[i + 1];
        if (args[i] === '--godot-width' && args[i + 1]) godotWidth = parseFloat(args[i + 1]);
    }

    // Find the replay/snapshots file
    const paramArgs = ['--turn', '--seq', '--field-width', '--snapshots', '--mode'];
    if (!snapshotsFile) {
        replayFile = args.find(a => !a.startsWith('--') && !paramArgs.includes(args[args.indexOf(a) - 1]));
    }

    // --- Constants comparison ---
    console.log('=== Layout Constant Comparison ===');
    const constIssues = compareConstants();
    if (constIssues.length === 0) {
        console.log('All constants match (within 0.002 tolerance)');
    } else {
        console.log('CONSTANT MISMATCHES:');
        for (const issue of constIssues) console.log('  ' + issue);
    }
    console.log('');

    if (constantsOnly) return;

    // --- Load snapshots ---
    let snapshots;
    if (snapshotsFile) {
        console.log('Loading snapshots from: ' + snapshotsFile);
        snapshots = JSON.parse(fs.readFileSync(snapshotsFile, 'utf-8'));
    } else if (replayFile) {
        console.log('Processing replay: ' + replayFile);
        const replay = loadReplay(replayFile);
        snapshots = processReplayData(replay);
    } else {
        console.error('Error: provide a replay file or --snapshots <file>');
        process.exit(1);
    }

    console.log('Loaded ' + snapshots.length + ' snapshots');
    console.log('Mode: ' + mode + (mode === 'algorithm' ? ' (same row width — verifies port)' : ' (actual widths — shows real diffs)'));
    console.log('PixiJS field width: ' + fieldWidth + 'px (' + (fieldWidth / PIXI.CARD_WIDTH).toFixed(2) + ' card-widths)');
    if (mode === 'visual') {
        console.log('Godot ROW_WIDTH: ' + GODOT.ROW_WIDTH + ' card-widths');
    }
    console.log('');

    // --- Filter snapshots ---
    let filtered = snapshots;
    if (seqFilter !== null) {
        filtered = snapshots.filter(s => s.seq === seqFilter);
    } else if (turnFilter !== null) {
        filtered = snapshots.filter(s => s.turn === turnFilter);
    }

    if (filtered.length === 0) {
        console.error('No snapshots match the filter');
        process.exit(1);
    }

    // --- Compare ---
    let totalUnitsAll = 0;
    let matchingUnitsAll = 0;
    let totalDiffs = 0;
    const rowMismatches = [];
    const pileMismatches = [];
    const xDiffs = [];

    for (const snap of filtered) {
        const report = compareSnapshot(snap, fieldWidth, mode, godotWidth);
        totalUnitsAll += report.totalUnits;
        matchingUnitsAll += report.matchingUnits;
        totalDiffs += report.diffs.length;

        if (showAll || report.diffs.length > 0) {
            console.log(`--- Seq ${report.seq} | Turn ${report.turn} | Phase: ${report.phase} | Units: ${report.totalUnits} | Match: ${report.matchPct}% ---`);
        }

        for (const d of report.diffs) {
            if (d.issue === 'position_mismatch') {
                if (!d.rowMatch) rowMismatches.push(d);
                else if (!d.pileMatch) pileMismatches.push(d);
                else xDiffs.push(d);

                if (showAll || verbose) {
                    const flags = [];
                    if (!d.rowMatch) flags.push('ROW');
                    if (!d.pileMatch) flags.push('PILE');
                    if (!d.cardIdxMatch) flags.push('IDX');
                    if (parseFloat(d.xDiff) >= 0.001) flags.push('X');
                    console.log(`  [${flags.join(',')}] P${d.owner} ${d.displayName} (${d.cardId}) #${d.unitId}: pixi(prop=${d.pixi.propX}, ${d.pixi.row}[${d.pixi.pile}][${d.pixi.idx}]) vs godot(prop=${d.godot.propX}, ${d.godot.row}[${d.godot.pile}][${d.godot.idx}]) diff=${d.xDiff}`);
                }
            } else if (showAll || verbose) {
                console.log(`  [${d.issue.toUpperCase()}] ${d.displayName} (${d.cardId}) #${d.unitId}`);
            }
        }
    }

    // --- Summary ---
    console.log('');
    console.log('=== SUMMARY ===');
    console.log(`Snapshots compared: ${filtered.length}`);
    console.log(`Total units compared: ${totalUnitsAll}`);
    console.log(`Matching units: ${matchingUnitsAll} (${totalUnitsAll > 0 ? ((matchingUnitsAll / totalUnitsAll) * 100).toFixed(1) : 100}%)`);
    console.log(`Total diffs: ${totalDiffs}`);
    if (totalDiffs > 0) {
        console.log(`  Row mismatches: ${rowMismatches.length}`);
        console.log(`  Pile order mismatches: ${pileMismatches.length}`);
        console.log(`  X position diffs (>0.1%): ${xDiffs.filter(d => parseFloat(d.xDiff) >= 0.001).length}`);
        console.log(`  Card index mismatches only: ${xDiffs.filter(d => parseFloat(d.xDiff) < 0.001).length}`);
    }

    // Show the biggest X diffs
    const allPosDiffs = [...rowMismatches, ...pileMismatches, ...xDiffs].filter(d => parseFloat(d.xDiff) >= 0.001);
    if (allPosDiffs.length > 0) {
        const sorted = allPosDiffs.sort((a, b) => parseFloat(b.xDiff) - parseFloat(a.xDiff));
        console.log('');
        console.log('Top proportional X diffs (0=left edge, 1=right edge):');
        for (const d of sorted.slice(0, 10)) {
            console.log(`  ${d.displayName} (${d.cardId}): diff=${d.xDiff} (pixi=${d.pixi.propX}, godot=${d.godot.propX})`);
        }
    }

    // Constant conversion accuracy (only show in non-sweep mode)
    if (!doSweep) {
        console.log('');
        console.log('=== Constant Conversion Accuracy ===');
        const spacingDiffs = [];
        for (let i = 0; i < PIXI.CARDSPACING.length; i++) {
            const pixiNorm = PIXI.CARDSPACING[i] / PIXI.CARD_WIDTH;
            const godot = GODOT.CARDSPACING[i];
            spacingDiffs.push({ index: i, pixiNorm: pixiNorm.toFixed(6), godot: godot.toFixed(6), diff: Math.abs(pixiNorm - godot).toFixed(6) });
        }
        console.log('CARDSPACING (pixel/83 vs world-unit):');
        for (const s of spacingDiffs) {
            console.log(`  [${s.index}]: pixi=${s.pixiNorm}, godot=${s.godot}, diff=${s.diff}`);
        }
    }

    // --- Sweep mode: try different Godot ROW_WIDTHs ---
    if (doSweep) {
        console.log('');
        console.log('=== ROW_WIDTH Sweep (visual mode) ===');
        console.log('PixiJS field width: ' + fieldWidth + 'px (' + (fieldWidth / PIXI.CARD_WIDTH).toFixed(2) + ' card-widths)');
        console.log('');
        console.log('ROW_WIDTH  | Match%  | Diffs | Avg X Diff');
        console.log('-----------|---------|-------|----------');

        const sweepWidths = [6, 7, 8, 8.5, 9, 9.5, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24];
        for (const gw of sweepWidths) {
            let sweepTotal = 0;
            let sweepMatch = 0;
            let sweepXDiffSum = 0;
            let sweepXDiffCount = 0;

            for (const snap of filtered) {
                const report = compareSnapshot(snap, fieldWidth, 'visual', gw);
                sweepTotal += report.totalUnits;
                sweepMatch += report.matchingUnits;
                for (const d of report.diffs) {
                    if (d.issue === 'position_mismatch' && d.xDiff) {
                        sweepXDiffSum += parseFloat(d.xDiff);
                        sweepXDiffCount++;
                    }
                }
            }

            const pct = sweepTotal > 0 ? ((sweepMatch / sweepTotal) * 100).toFixed(1) : '100.0';
            const avgDiff = sweepXDiffCount > 0 ? (sweepXDiffSum / sweepXDiffCount).toFixed(6) : '0';
            const diffs = sweepTotal - sweepMatch;
            console.log(`${String(gw).padStart(9)}  | ${pct.padStart(5)}%  | ${String(diffs).padStart(5)} | ${avgDiff}`);
        }
    }
}

if (require.main === module) {
    main();
}

module.exports = { compareSnapshot, pixiLayout, godotLayout, compareConstants };
