#!/usr/bin/env node
// tools/extract_viewer_assets.js
// Extracts PixiJS viewer assets to Godot project directories.
// Generates a manifest JSON for verification.
'use strict';
const fs = require('fs');
const path = require('path');

const BIN_IMAGES = path.join(__dirname, '..', 'bin', 'asset', 'images');
const DST_ROOT = path.resolve(__dirname, '..', '..', 'prismata-3d', 'assets');

// Source directories (matching build_viewer_bundle.js constants)
const CARDBG = 'cardbg';
const STATUS = 'icons/status';
const MOUSEOVER = 'icons/mouseover';
const HD = 'icons/extracted_hd';

// Verified mappings: bundle_key → [source_subdir, source_filename]
const ASSETS = {
    backgrounds: {
        'bg_dead.png':       [CARDBG, 'Card_Inver.png'],
        'bg_block.png':      [CARDBG, 'Card_Blue.png'],
        'bg_busy.png':       [CARDBG, 'Card_Grey.png'],
        'bg_absorb.png':     [CARDBG, 'Card_Orange.png'],
        'bg_chilled.png':    [CARDBG, 'Card_Blue_Frost.png'],
        'bg_bought.png':     [CARDBG, 'Card_Trans.png'],
        'bg_whitepink.png':  [CARDBG, 'Card_WhitePink.png'],
        'bg_blockred.png':   [CARDBG, 'Card_Red.png'],
        'bg_busyblue.png':   [CARDBG, 'Card_BlueGrey.png'],
        'bg_busyred.png':    [CARDBG, 'Card_RedGrey.png'],
    },
    overlays: {
        'cover_blackclock.png':   [STATUS, 'highlight_blackclock.png'],
        'cover_goldclock.png':    [STATUS, 'highlight_goldclock.png'],
        'cover_cage.png':         [CARDBG, 'highlight_cage2.png'],
        'cover_goldshield.png':   [STATUS, 'highlight_goldshield.png'],
        'cover_damagebang.png':   [STATUS, 'highlight_damagebang.png'],
        'shade_whiteshield.png':  [STATUS, 'highlight_whiteshield.png'],
        'shade_blueshield.png':   [STATUS, 'highlight_blueshield.png'],
        'shade_whiteshieldB.png': [STATUS, 'highlight_whiteshieldB.png'],
        'shade_redshield.png':    [STATUS, 'highlight_redshield.png'],
    },
    icons: {
        'sword_blue.png':         [MOUSEOVER, 'attack_big_blue.png'],
        'icon_defend.png':        [STATUS, 'icon_defend.png'],
        'icon_clock.png':         [STATUS, 'clock.png'],
        'icon_hp.png':            [STATUS, 'status_hp.png'],
        'icon_undefendable.png':  [STATUS, 'status_undefendable.png'],
        'icon_delay.png':         [STATUS, 'status_delay.png'],
        'icon_doom.png':          [STATUS, 'status_doom.png'],
        'icon_charge0.png':       [STATUS, 'status_charge0.png'],
        'icon_charge1.png':       [STATUS, 'status_charge1.png'],
        'icon_charge2.png':       [STATUS, 'status_charge2.png'],
        'icon_charge3.png':       [STATUS, 'status_charge3.png'],
        'icon_tap.png':           [STATUS, 'status_tap.png'],
        'icon_attack.png':        [STATUS, 'icon_attack.png'],
    },
    effects: {
        'chill_snowflake.png':    [CARDBG, 'Card_Chilled.png'],
    },
};

function readPngDimensions(filepath) {
    const buf = fs.readFileSync(filepath);
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const manifest = {};
let copied = 0, missing = 0;

for (const [subdir, mapping] of Object.entries(ASSETS)) {
    const dstDir = path.join(DST_ROOT, subdir);
    fs.mkdirSync(dstDir, { recursive: true });
    manifest[subdir] = {};

    for (const [dstName, [srcSubdir, srcFile]] of Object.entries(mapping)) {
        const srcPath = path.join(BIN_IMAGES, srcSubdir, srcFile);
        const dstPath = path.join(dstDir, dstName);

        if (fs.existsSync(srcPath)) {
            fs.copyFileSync(srcPath, dstPath);
            const dims = readPngDimensions(srcPath);
            manifest[subdir][dstName] = {
                source: `${srcSubdir}/${srcFile}`,
                width: dims.width,
                height: dims.height,
            };
            copied++;
        } else {
            console.error(`MISSING: ${srcSubdir}/${srcFile}`);
            manifest[subdir][dstName] = { source: `${srcSubdir}/${srcFile}`, error: 'NOT FOUND' };
            missing++;
        }
    }
}

const manifestPath = path.join(DST_ROOT, 'asset_manifest.json');
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

console.log(`Extracted ${copied} assets (${missing} missing)`);
console.log(`Manifest written to ${manifestPath}`);
if (missing > 0) process.exit(1);
