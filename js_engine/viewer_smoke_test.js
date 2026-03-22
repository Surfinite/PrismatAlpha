#!/usr/bin/env node
'use strict';
// viewer_smoke_test.js — Validates state exports for the PixiJS renderer
//
// Loads replays and validates that every state snapshot has the fields required
// by the browser game viewer: instId, damage, deadness, phase, and no NaN numerics.
//
// Two replay formats are supported:
//   - Pre-computed states format: { states: [...], p0, p1, winner }  (matchup runner output)
//   - S3 replay format: { deckInfo, commandInfo, ... }  (run live through Analyzer)
//
// Usage:
//   node js_engine/viewer_smoke_test.js [--count N] [--dir path/to/replays]
//
// Exit codes: 0 = all checks passed, 1 = validation errors found or no replays loaded

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

// Load engine modules
const C = require('./C');
const Analyzer = require('./Analyzer');
const replay_exporter = require('./replay_exporter');

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
let maxCount = 50;
let replayDir = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--count' && args[i + 1]) maxCount = parseInt(args[i + 1], 10);
  if (args[i] === '--dir' && args[i + 1]) replayDir = args[i + 1];
}

// ---------------------------------------------------------------------------
// File discovery
// ---------------------------------------------------------------------------

/**
 * Find up to maxCount replay files, searching dirs in priority order.
 * Accepts .json and .json.gz files. Recurses one level into subdirectories.
 */
function findReplays() {
  const searchDirs = [
    replayDir,
    path.join(__dirname, 'test_replays'),
    path.join(__dirname, '..', 'bin', 'asset', 'replays'),
  ].filter(Boolean);

  const files = [];

  for (const dir of searchDirs) {
    if (!fs.existsSync(dir)) continue;

    // Collect from top level and one level of subdirectories
    const collect = (d) => {
      let entries;
      try { entries = fs.readdirSync(d); } catch (e) { return; }
      for (const f of entries) {
        if (files.length >= maxCount) return;
        const full = path.join(d, f);
        const stat = fs.statSync(full);
        if (stat.isDirectory()) {
          collect(full);
        } else if (f.endsWith('.json') || f.endsWith('.json.gz')) {
          files.push(full);
        }
      }
    };

    collect(dir);
    if (files.length > 0) break; // Stop at first dir that has any replays
  }

  return files.slice(0, maxCount);
}

// ---------------------------------------------------------------------------
// Replay loading
// ---------------------------------------------------------------------------

function loadReplay(filePath) {
  let data = fs.readFileSync(filePath);
  if (filePath.endsWith('.gz')) {
    data = zlib.gunzipSync(data);
  }
  return JSON.parse(data.toString('utf-8'));
}

// ---------------------------------------------------------------------------
// State validation
// ---------------------------------------------------------------------------

const VALID_PHASES = new Set(['defense', 'action', 'confirm']);

/**
 * Validate a single state snapshot for renderer compatibility.
 *
 * @param {Object} state - State object (from states[] or stateToCppJSON output)
 * @param {number} stateIdx - Index within the replay for error reporting
 * @returns {string[]} Array of error messages (empty = passed)
 */
function validateState(state, stateIdx) {
  const errors = [];

  // --- phase ---
  if (!VALID_PHASES.has(state.phase)) {
    errors.push(`state[${stateIdx}]: invalid phase "${state.phase}"`);
  }

  // --- table ---
  if (!Array.isArray(state.table)) {
    errors.push(`state[${stateIdx}]: table is not an array`);
    return errors; // Can't continue without table
  }

  for (let i = 0; i < state.table.length; i++) {
    const card = state.table[i];
    const loc = `state[${stateIdx}].table[${i}]`;

    // Required fields added by Task 1
    if (card.instId === undefined || card.instId === null) {
      errors.push(`${loc}: missing instId`);
    }
    if (card.damage === undefined || card.damage === null) {
      errors.push(`${loc}: missing damage`);
    }
    if (card.deadness === undefined || card.deadness === null) {
      errors.push(`${loc}: missing deadness`);
    }
    if (card.cardName === undefined) {
      errors.push(`${loc}: missing cardName`);
    }

    // NaN check on numeric fields
    const numericFields = [
      'instId', 'health', 'damage', 'constructionTime',
      'charge', 'delay', 'lifespan', 'disruptDamage', 'owner',
    ];
    for (const field of numericFields) {
      if (card[field] !== undefined && typeof card[field] === 'number' && isNaN(card[field])) {
        errors.push(`${loc}: NaN in field "${field}"`);
      }
    }
  }

  // --- supply arrays must match cards array length ---
  if (Array.isArray(state.cards)) {
    const numCards = state.cards.length;
    const supplyArrays = [
      'whiteTotalSupply', 'blackTotalSupply',
      'whiteSupplySpent', 'blackSupplySpent',
    ];
    for (const key of supplyArrays) {
      if (state[key] !== undefined && state[key].length !== numCards) {
        errors.push(
          `state[${stateIdx}]: ${key}.length=${state[key].length} != cards.length=${numCards}`
        );
      }
    }
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Replay processing — pre-computed states format
// ---------------------------------------------------------------------------

function processStatesFormat(replay, fileName, stats) {
  const statesArr = replay.states;
  let replayErrors = 0;
  let deadUnits = 0;
  // Print up to 5 unique error messages per replay to avoid flooding
  const printedMsgs = new Set();

  for (let s = 0; s < statesArr.length; s++) {
    stats.totalStates++;
    const errs = validateState(statesArr[s], s);
    if (errs.length > 0) {
      replayErrors += errs.length;
      stats.totalErrors += errs.length;
      // Print novel error types (strip the index so similar errors collapse)
      for (const e of errs) {
        // Normalize: replace "[N]" with "[*]" to deduplicate across states/cards
        const key = e.replace(/\[\d+\]/g, '[*]');
        if (!printedMsgs.has(key) && printedMsgs.size < 5) {
          if (printedMsgs.size === 0) console.error(`  ${fileName}:`);
          console.error(`    ${e}`);
          printedMsgs.add(key);
        }
      }
    }
    const table = statesArr[s].table || [];
    deadUnits += table.filter(c => c.deadness && c.deadness !== 'alive').length;
  }

  if (printedMsgs.size >= 5) {
    console.error(`    ... (${replayErrors} total errors, showing first 5 unique types)`);
  }

  stats.totalDeadUnits += deadUnits;
  if (replayErrors > 0) stats.failedReplays++;
}

// ---------------------------------------------------------------------------
// Replay processing — S3 click-by-click format
// ---------------------------------------------------------------------------

/**
 * Build a gameInitInfo struct from an S3 replay (same logic as replay_validator.js).
 */
function replayToInitOnly(replay) {
  return {
    laneInfo: [{
      initResources: replay.initInfo.initResources,
      base:          replay.deckInfo.base,
      randomizer:    replay.deckInfo.randomizer,
      initCards:     replay.initInfo.initCards,
    }],
    mergedDeck:    replay.deckInfo.mergedDeck,
    scriptInfo:    { whiteStarts: true },
    objectiveInfo: null,
    // No commandInfo — we apply clicks manually
  };
}

function processS3Format(replay, fileName, stats) {
  const commands      = (replay.commandInfo && replay.commandInfo.commandList)  || [];
  const clicksPerTurn = (replay.commandInfo && replay.commandInfo.clicksPerTurn) || [];

  let replayErrors = 0;
  let deadUnits    = 0;
  const printedMsgs = new Set();

  const reportErrs = (errs) => {
    for (const e of errs) {
      const key = e.replace(/\[\d+\]/g, '[*]');
      if (!printedMsgs.has(key) && printedMsgs.size < 5) {
        if (printedMsgs.size === 0) console.error(`  ${fileName}:`);
        console.error(`    ${e}`);
        printedMsgs.add(key);
      }
    }
  };

  try {
    const analyzer = new Analyzer(replayToInitOnly(replay), -1, -1, null);

    // Validate initial state
    const initState = replay_exporter.stateToCppJSON(analyzer.gameState);
    stats.totalStates++;
    const initErrs = validateState(initState, 0);
    replayErrors += initErrs.length;
    stats.totalErrors += initErrs.length;
    reportErrs(initErrs);

    let cmdIdx = 0;
    for (let turn = 0; turn < clicksPerTurn.length; turn++) {
      const numClicks = clicksPerTurn[turn];
      for (let c = 0; c < numClicks && cmdIdx < commands.length; c++, cmdIdx++) {
        const click = commands[cmdIdx];
        try {
          analyzer.recordClick(false, false, click._type, click._id);
        } catch (e) {
          // Tolerate info-click failures (same policy as replay_validator.js)
        }
      }

      const state = replay_exporter.stateToCppJSON(analyzer.gameState);
      stats.totalStates++;
      const errs = validateState(state, turn + 1);
      if (errs.length > 0) {
        replayErrors += errs.length;
        stats.totalErrors += errs.length;
        reportErrs(errs);
      }
      const table = state.table || [];
      deadUnits += table.filter(c => c.deadness && c.deadness !== 'alive').length;
    }

    if (printedMsgs.size >= 5) {
      console.error(`    ... (${replayErrors} total errors, showing first 5 unique types)`);
    }
  } catch (e) {
    stats.totalErrors++;
    stats.failedReplays++;
    console.error(`  ${fileName}: engine error — ${e.message}`);
    return;
  }

  stats.totalDeadUnits += deadUnits;
  if (replayErrors > 0) stats.failedReplays++;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const replayFiles = findReplays();

if (replayFiles.length === 0) {
  console.error('No replay files found.');
  console.error('Use --dir path/to/replays, or place files in js_engine/test_replays/');
  console.error('or bin/asset/replays/');
  process.exit(1);
}

console.log(`Testing ${replayFiles.length} replay(s)...`);

const stats = {
  totalReplays:  0,
  totalStates:   0,
  totalErrors:   0,
  totalDeadUnits: 0,
  failedReplays: 0,
  unknownFormat: 0,
};

for (const file of replayFiles) {
  const fileName = path.basename(file);
  try {
    const replay = loadReplay(file);
    stats.totalReplays++;

    // Pre-computed states format (matchup_clean.js / replay_to_html.js output)
    if (replay.states && Array.isArray(replay.states)) {
      processStatesFormat(replay, fileName, stats);
      continue;
    }

    // S3 replay format (commandList-driven)
    if (replay.deckInfo && replay.commandInfo) {
      processS3Format(replay, fileName, stats);
      continue;
    }

    console.error(`  ${fileName}: unrecognized format (no "states" or "deckInfo")`);
    stats.unknownFormat++;
    stats.failedReplays++;

  } catch (e) {
    console.error(`  ${fileName}: failed to load — ${e.message}`);
    stats.failedReplays++;
  }
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log('');
console.log('--- Results ---');
console.log(`Replays loaded:   ${stats.totalReplays} (${stats.failedReplays} with errors, ${stats.unknownFormat} unknown format)`);
console.log(`States checked:   ${stats.totalStates}`);
console.log(`Dead units seen:  ${stats.totalDeadUnits}`);
console.log(`Errors found:     ${stats.totalErrors}`);

if (stats.totalErrors > 0) {
  process.exit(1);
} else {
  console.log('All checks passed!');
}
