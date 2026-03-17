#!/usr/bin/env node
/**
 * Single-unit sweep: runs Base+1 matchups for every valid advanced unit.
 * Each unit gets 2 games (with --player-switch).
 * Runs up to 8 units concurrently (each as a separate matchup_clean.js process).
 *
 * Usage:
 *   node run_single_unit_sweep.js                    # run all 105 units
 *   node run_single_unit_sweep.js --start 50         # resume from unit #50 (0-indexed)
 *   node run_single_unit_sweep.js --unit "Tarsier"   # run a single unit only
 *   node run_single_unit_sweep.js --dry-run           # print commands without running
 *   node run_single_unit_sweep.js --parallel 4        # override concurrency (default 8)
 */

const { spawn } = require('child_process');
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
let maxParallel = 2;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--start' && args[i + 1]) startIdx = parseInt(args[i + 1], 10);
    if (args[i] === '--unit' && args[i + 1]) singleUnit = args[i + 1];
    if (args[i] === '--dry-run') dryRun = true;
    if (args[i] === '--parallel' && args[i + 1]) maxParallel = parseInt(args[i + 1], 10);
}

const unitsToRun = singleUnit
    ? units.filter(u => u === singleUnit)
    : units.slice(startIdx);

if (singleUnit && unitsToRun.length === 0) {
    console.error(`ERROR: "${singleUnit}" not found in valid_units.json`);
    process.exit(1);
}

console.log(`=== Single-Unit Sweep: ${unitsToRun.length} units, ${maxParallel} concurrent ===`);
console.log(`Starting from index ${startIdx} (${unitsToRun[0]})`);
console.log(`Think time: 10000/5000ms | Games per unit: 8 (player-switch)`);
console.log('');

const startTime = Date.now();
const resultsPath = path.join(__dirname, 'sweep_results.jsonl');
fs.writeFileSync(resultsPath, ''); // clear previous results
let completed = 0;
let failed = 0;
let nextIdx = 0;
let activeCount = 0;

function formatElapsed() {
    return ((Date.now() - startTime) / 1000 / 60).toFixed(1);
}

function runUnit(i) {
    const unit = unitsToRun[i];
    const globalIdx = singleUnit ? units.indexOf(unit) : startIdx + i;
    const safeName = unit.replace(/[^a-zA-Z0-9_-]/g, '_');
    const dirName = `LiveUCTVsMB_SingleUnit_UnevenThink_${safeName}`;
    const logName = `LiveUCTVsMB_SingleUnit_UnevenThink_${safeName}.log`;

    const progress = `[${globalIdx + 1}/${units.length}]`;
    console.log(`${progress} ${unit} — starting`);

    const cmdArgs = [
        'matchup_clean.js',
        '--games', '2',
        '--player-switch',
        '--think-time-black', '5000',
        '--think-time-white', '10000',
        '--resign', '1.5',
        '--player-black', 'SteamAI',
        '--player-white', 'LiveHardestAIUCT',
        '--cards', unit,
        '--save-replays', dirName,
    ];

    if (dryRun) {
        console.log(`  CMD: node ${cmdArgs.join(' ')} 2>${logName}`);
        console.log('');
        completed++;
        scheduleNext();
        return;
    }

    const logStream = fs.openSync(path.join(__dirname, logName), 'w');
    activeCount++;

    const child = spawn('node', cmdArgs, {
        cwd: __dirname,
        stdio: ['ignore', 'pipe', logStream],
        timeout: 120 * 60 * 1000,
    });

    // Capture stdout (JSON game results) to shared results file
    child.stdout.on('data', (data) => {
        fs.appendFileSync(resultsPath, data);
    });

    child.on('close', (code) => {
        fs.closeSync(logStream);
        activeCount--;

        if (code !== 0) {
            failed++;
            console.log(`${progress} ${unit} — FAILED (exit ${code})`);
        } else {
            completed++;
            // Check log for click failures
            try {
                const log = fs.readFileSync(path.join(__dirname, logName), 'utf8');
                const failMatch = log.match(/([1-9][0-9]*) failed/g);
                if (failMatch) {
                    console.log(`${progress} ${unit} — done (${formatElapsed()}m) WARNING: ${failMatch.join(', ')}`);
                } else {
                    console.log(`${progress} ${unit} — done (${formatElapsed()}m)`);
                }
            } catch (e) {
                console.log(`${progress} ${unit} — done (${formatElapsed()}m)`);
            }
        }

        const total = completed + failed;
        if (total === unitsToRun.length) {
            printSummary();
        } else {
            scheduleNext();
        }
    });

    child.on('error', (err) => {
        activeCount--;
        failed++;
        console.log(`${progress} ${unit} — ERROR: ${err.message}`);
        scheduleNext();
    });
}

function scheduleNext() {
    while (activeCount < maxParallel && nextIdx < unitsToRun.length) {
        runUnit(nextIdx++);
    }
}

function printSummary() {
    console.log('');
    console.log('=== SWEEP COMPLETE ===');
    console.log(`Completed: ${completed} | Failed: ${failed} | Total: ${unitsToRun.length}`);
    console.log(`Total time: ${formatElapsed()} minutes`);
    console.log('');
    console.log('Replays saved to LiveUCTVsMB_SingleUnit_*/ directories');
    console.log('Logs at LiveUCTVsMB_SingleUnit_*.log');
}

// Kick off initial batch
scheduleNext();
