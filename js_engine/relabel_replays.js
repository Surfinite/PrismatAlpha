#!/usr/bin/env node
/**
 * relabel_replays.js — backfill side identity into matchup_clean.js replays.
 *
 * matchup_clean.js used to save replays with p0/p1 = the bare player name
 * ("DaveAI"/"DaveAI"), so both sides looked identical in the viewer. The runner
 * now folds the difficulty in ("DaveAI[HardestAIUCT]"); this script applies the
 * same labels to replays produced BEFORE that fix, using the pairing convention
 * (odd game# = original assignment, even game# = swapped — see matchup_clean.js
 * slotsGames push `p*2+1, p*2+2` and the player-switch A/B pair loop).
 *
 * Usage:
 *   node relabel_replays.js --dir <replayDir> \
 *     --player-white DaveAI --player-black DaveAI \
 *     --difficulty-white HardestAIUCT --difficulty-black DSNN_Mixed35 \
 *     [--no-switch] [--dry-run]
 *
 * --no-switch : games were NOT run with --player-switch (no per-game swap).
 * --dry-run   : print the intended relabeling, write nothing.
 */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { sideLabel } = require('./matchup_clean');

function parseArgs(argv) {
    const o = { switch: true, dryRun: false };
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--dir') o.dir = argv[++i];
        else if (a === '--player-white') o.pWhite = argv[++i];
        else if (a === '--player-black') o.pBlack = argv[++i];
        else if (a === '--difficulty-white') o.dWhite = argv[++i];
        else if (a === '--difficulty-black') o.dBlack = argv[++i];
        else if (a === '--no-switch') o.switch = false;
        else if (a === '--dry-run') o.dryRun = true;
    }
    return o;
}

function main() {
    const o = parseArgs(process.argv.slice(2));
    if (!o.dir || !o.pWhite || !o.pBlack) {
        console.error('Required: --dir <dir> --player-white <p> --player-black <p> [--difficulty-white <d> --difficulty-black <d>] [--no-switch] [--dry-run]');
        process.exit(2);
    }
    const files = fs.readdirSync(o.dir).filter(f => /^game_\d+\.json\.gz$/.test(f)).sort();
    if (files.length === 0) { console.error(`No game_*.json.gz in ${o.dir}`); process.exit(1); }

    let changed = 0, skipped = 0;
    for (const f of files) {
        const n = parseInt(f.match(/game_(\d+)/)[1], 10);
        const swapped = o.switch && (n % 2 === 0);  // even game# = swapped assignment
        // White (p0) and black (p1) for this specific game:
        const whiteLabel = swapped ? sideLabel(o.pBlack, o.dBlack) : sideLabel(o.pWhite, o.dWhite);
        const blackLabel = swapped ? sideLabel(o.pWhite, o.dWhite) : sideLabel(o.pBlack, o.dBlack);

        const fp = path.join(o.dir, f);
        let d;
        try { d = JSON.parse(zlib.gunzipSync(fs.readFileSync(fp))); }
        catch (e) { console.error(`  SKIP ${f}: ${e.message}`); skipped++; continue; }

        const newWinnerName = d.winner === 0 ? whiteLabel : d.winner === 1 ? blackLabel : 'Draw';
        if (d.p0 === whiteLabel && d.p1 === blackLabel && d.winnerName === newWinnerName) { skipped++; continue; }

        d.p0 = whiteLabel;
        d.p1 = blackLabel;
        d.winnerName = newWinnerName;

        if (o.dryRun) {
            console.error(`  [dry] ${f} (${swapped ? 'swapped' : 'orig'}): p0=${whiteLabel} p1=${blackLabel} winner=${d.winner}->${newWinnerName}`);
        } else {
            fs.writeFileSync(fp, zlib.gzipSync(JSON.stringify(d, null, 2)));
        }
        changed++;
    }
    console.error(`${o.dryRun ? '[dry-run] would relabel' : 'Relabeled'} ${changed} file(s), ${skipped} unchanged/skipped, in ${o.dir}`);
}

main();
