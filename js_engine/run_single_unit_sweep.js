#!/usr/bin/env node
/**
 * Single-unit sweep: runs Base+1 matchups for every valid advanced unit.
 * Each unit gets 2 games (with --player-switch), played --parallel 2.
 *
 * Usage:
 *   node run_single_unit_sweep.js                    # run all 105 units
 *   node run_single_unit_sweep.js --start 50         # resume from unit #50 (0-indexed)
 *   node run_single_unit_sweep.js --unit "Tarsier"   # run a single unit only
 *   node run_single_unit_sweep.js --dry-run           # print commands without running
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const VALID_UNITS_PATH = path.resolve(__dirname, '../bin/asset/config/valid_units.json');
const validUnits = JSON.parse(fs.readFileSync(VALID_UNITS_PATH, 'utf8'));
const units = validUnits.randomUnits; // 105 units, already sorted

// Parse args
const args = process.argv.slice(2);
let startIdx = 0;
let singleUnit = null;
let dryRun = false;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--start' && args[i + 1]) startIdx = parseInt(args[i + 1], 10);
    if (args[i] === '--unit' && args[i + 1]) singleUnit = args[i + 1];
    if (args[i] === '--dry-run') dryRun = true;
}

const unitsToRun = singleUnit
    ? units.filter(u => u === singleUnit)
    : units.slice(startIdx);

if (singleUnit && unitsToRun.length === 0) {
    console.error(`ERROR: "${singleUnit}" not found in valid_units.json`);
    process.exit(1);
}

console.log(`=== Single-Unit Sweep: ${unitsToRun.length} units ===`);
console.log(`Starting from index ${startIdx} (${unitsToRun[0]})`);
console.log(`Think time: 7000ms | Games per unit: 2 (player-switch) | Resign threshold: 3x`);
console.log('');

const startTime = Date.now();
let completed = 0;
let failed = 0;

for (let i = 0; i < unitsToRun.length; i++) {
    const unit = unitsToRun[i];
    const globalIdx = singleUnit ? units.indexOf(unit) : startIdx + i;
    const safeName = unit.replace(/[^a-zA-Z0-9_-]/g, '_');
    const dirName = `LiveVsMCDSAI_SingleUnit_${safeName}`;
    const logName = `LiveVsMCDSAI_SingleUnit_${safeName}.log`;

    const progress = `[${globalIdx + 1}/${units.length}]`;
    console.log(`${progress} ${unit}`);

    const cmd = [
        'node', 'matchup_clean.js',
        '--games', '2',
        '--parallel', '2',
        '--player-switch',
        '--think-time', '7000',
        '--player-black', 'MCDSAI',
        '--player-white', 'LiveHardestAI',
        '--cards', `"${unit}"`,
        '--resign', '3',
        '--save-replays', dirName,
    ].join(' ');

    if (dryRun) {
        console.log(`  CMD: ${cmd} 2>${logName}`);
        console.log('');
        completed++;
        continue;
    }

    try {
        execSync(`${cmd} 2>${logName}`, {
            cwd: __dirname,
            stdio: ['ignore', 'inherit', 'ignore'], // stdout to console, stderr to log file via shell redirect
            timeout: 10 * 60 * 1000, // 10 min timeout per unit
        });
        completed++;

        // Quick check: scan log for failures
        if (fs.existsSync(path.join(__dirname, logName))) {
            const log = fs.readFileSync(path.join(__dirname, logName), 'utf8');
            const failMatch = log.match(/([1-9][0-9]*) failed/g);
            if (failMatch) {
                console.log(`  WARNING: ${failMatch.join(', ')}`);
            }
        }
    } catch (err) {
        failed++;
        console.log(`  FAILED: ${err.message.split('\n')[0]}`);
    }

    const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);
    const rate = completed / (elapsed || 1);
    const remaining = ((unitsToRun.length - i - 1) / rate).toFixed(0);
    console.log(`  Done (${elapsed}m elapsed, ~${remaining}m remaining)`);
    console.log('');
}

console.log('=== SWEEP COMPLETE ===');
console.log(`Completed: ${completed} | Failed: ${failed} | Total: ${unitsToRun.length}`);
console.log(`Total time: ${((Date.now() - startTime) / 1000 / 60).toFixed(1)} minutes`);
console.log('');
console.log('Replays saved to LiveVsMCDSAI_SingleUnit_*/ directories');
console.log('Logs at LiveVsMCDSAI_SingleUnit_*.log');
