#!/usr/bin/env node
'use strict';

/**
 * fetch_and_preprocess.js — Fetch a replay and preprocess it for the Godot 3D viewer.
 *
 * Usage:
 *   node tools/fetch_and_preprocess.js [replay_code]    # specific replay
 *   node tools/fetch_and_preprocess.js --latest          # latest from prismata-stats
 *   node tools/fetch_and_preprocess.js                   # default: --latest
 *
 * Output: c:\libraries\prismata-3d\data\current_replay.json
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const zlib = require('zlib');

const OUTPUT_DIR = path.join(__dirname, '..', '..', 'prismata-3d', 'data');
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'current_replay.json');

// ---------------------------------------------------------------------------
// Fetch replay from S3
// ---------------------------------------------------------------------------
function fetchReplayFromS3(code) {
    return new Promise((resolve, reject) => {
        const safeCode = code.replace(/\+/g, '%2B').replace(/@/g, '%40');
        const url = `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/${safeCode}.json.gz`;
        console.error('Fetching replay: ' + code);
        http.get(url, (res) => {
            if (res.statusCode !== 200) {
                reject(new Error('HTTP ' + res.statusCode + ' for ' + code));
                return;
            }
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                const buf = Buffer.concat(chunks);
                zlib.gunzip(buf, (err, data) => {
                    if (err) {
                        try { resolve(JSON.parse(buf.toString())); }
                        catch (e) { reject(e); }
                    } else {
                        resolve(JSON.parse(data.toString()));
                    }
                });
            });
        }).on('error', reject);
    });
}

// ---------------------------------------------------------------------------
// Fetch latest replay codes from prismata-stats API
// ---------------------------------------------------------------------------
function fetchLatestCodes(limit) {
    limit = limit || 5;
    return new Promise((resolve, reject) => {
        const postData = JSON.stringify({
            limit: limit,
            sortBy: 'endTime',
            sortOrder: 'desc',
            rated: true
        });
        const options = {
            hostname: 'prismata-stats.web.app',
            path: '/api/search/replays',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            },
            rejectUnauthorized: false
        };
        console.error('Fetching latest replays from prismata-stats...');
        const req = https.request(options, (res) => {
            const chunks = [];
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                try {
                    const body = Buffer.concat(chunks).toString();
                    const data = JSON.parse(body);
                    if (data.replays && data.replays.length > 0) {
                        resolve(data.replays.map(r => r.code || r.Code));
                    } else if (Array.isArray(data) && data.length > 0) {
                        resolve(data.map(r => r.code || r.Code));
                    } else {
                        reject(new Error('No replays found in API response'));
                    }
                } catch (e) {
                    reject(new Error('Failed to parse API response: ' + e.message));
                }
            });
        });
        req.on('error', reject);
        req.write(postData);
        req.end();
    });
}

// ---------------------------------------------------------------------------
// Load replay from local archive (fallback)
// ---------------------------------------------------------------------------
function loadFromArchive() {
    const archiveDir = path.join(__dirname, '..', '..', 'prismata-replay-parser', 'replays_archive');
    if (!fs.existsSync(archiveDir)) return null;
    const files = fs.readdirSync(archiveDir).filter(f => f.endsWith('.json.gz'));
    if (files.length === 0) return null;
    // Pick a random replay
    const pick = files[Math.floor(Math.random() * files.length)];
    const filePath = path.join(archiveDir, pick);
    console.error('Loading from local archive: ' + pick);
    const raw = zlib.gunzipSync(fs.readFileSync(filePath));
    return JSON.parse(raw.toString());
}

// ---------------------------------------------------------------------------
// Preprocess replay to snapshots
// ---------------------------------------------------------------------------
function preprocessReplay(replay) {
    // Use replay_to_snapshots module
    const { processReplayData } = require('./replay_to_snapshots');
    return processReplayData(replay);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
    const arg = process.argv[2] || '--latest';
    let replay = null;
    let replayCode = null;

    if (arg === '--latest') {
        // Try fetching from API
        try {
            const codes = await fetchLatestCodes(5);
            console.error('Latest codes: ' + codes.join(', '));
            // Try each code until one works
            for (const code of codes) {
                if (!code) continue;
                try {
                    replay = await fetchReplayFromS3(code);
                    replayCode = code;
                    break;
                } catch (e) {
                    console.error('Failed to fetch ' + code + ': ' + e.message);
                }
            }
        } catch (e) {
            console.error('API fetch failed: ' + e.message);
        }

        // Fallback to local archive
        if (!replay) {
            console.error('Falling back to local replay archive...');
            replay = loadFromArchive();
            replayCode = 'local';
        }
    } else if (arg === '--local') {
        replay = loadFromArchive();
        replayCode = 'local';
    } else {
        // Treat as replay code
        replayCode = arg;
        // Check if it's a file path
        if (fs.existsSync(arg)) {
            let raw = fs.readFileSync(arg);
            if (arg.endsWith('.gz')) raw = zlib.gunzipSync(raw);
            replay = JSON.parse(raw.toString());
        } else {
            replay = await fetchReplayFromS3(arg);
        }
    }

    if (!replay) {
        console.error('ERROR: Could not load any replay');
        process.exit(1);
    }

    // Print replay info
    const p1 = replay.playerInfo?.[0]?.displayName || '?';
    const p2 = replay.playerInfo?.[1]?.displayName || '?';
    const units = replay.deckInfo?.mergedDeck?.filter(u => !u.baseSet).map(u => u.UIName || u.name).join(', ') || '?';
    console.error('Replay: ' + replayCode);
    console.error('Players: ' + p1 + ' vs ' + p2);
    console.error('Units: ' + units);

    // Preprocess
    const snapshots = preprocessReplay(replay);
    console.error('Generated ' + snapshots.length + ' snapshots');

    // Write output
    if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(snapshots));
    console.error('Written to: ' + OUTPUT_FILE);

    // Also print summary to stdout
    const last = snapshots[snapshots.length - 1];
    console.log(JSON.stringify({
        code: replayCode,
        players: [p1, p2],
        snapshots: snapshots.length,
        turns: last ? last.turn : 0,
        units: units
    }));
}

main().catch(e => { console.error('ERROR: ' + e.message); process.exit(1); });
