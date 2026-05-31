'use strict';

/**
 * extract_training_jsengine.js — Human replay -> DeepSets V2 per-turn training records.
 *
 * Replays a recorded human replay's commandList click-by-click through PrismatAlpha's OWN
 * transpiled JS engine (Analyzer) — the SAME engine that generated the MB self-play corpus —
 * and emits one V2 training record per player-turn, captured at the START of each turn
 * (analyzer.beginTurnHistory = the turn-start snapshot, the mixed Defense/Action point the
 * AI search actually evaluates as leaves).
 *
 * Emits V2 DIRECTLY via the shared extractTrainingExampleV2 (./training_example.js) — the SAME
 * function matchup_clean.js uses for the MB corpus. This REPLACES the old V1 ->
 * convert_human_to_v2.py path, which silently diverged from MB on three axes now eliminated by
 * construction:
 *   1. card_set: old human = "all units with supply"; MB = advanced (non-base) units only.
 *   2. turn_number: old human = 0-based; MB = gameState.numTurns (1-based).
 *   3. p0_resources: old human stripped attack; MB keeps it.
 * Plus hp_fraction is now computed from the live Card (startingHealth) rather than a
 * reconstructed blueprints lookup.
 *
 * Snapshot point: turn-start (matches what the C++ value evaluator is queried on). Kept as-is;
 * post-swoosh normalization is a separate future A/B experiment.
 *
 * Validate-and-drop: any replay the engine cannot faithfully replay (throws / no history /
 * no result) is skipped and its code logged to <output>.dropped.txt.
 *
 * Usage:
 *   node extract_training_jsengine.js --codes <file> --replays-dir <dir> --output <jsonl> [--limit N]
 *   node extract_training_jsengine.js --one <replay.json.gz>      # single replay -> stdout (pretty)
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const C = require('./C');
const Analyzer = require('./Analyzer');
const { extractTrainingExampleV2 } = require('./training_example');

// --- replay load + init (mirrors bulk_extract.js) ---
function loadReplay(filePath) {
    const raw = fs.readFileSync(filePath);
    return filePath.endsWith('.gz')
        ? JSON.parse(zlib.gunzipSync(raw).toString('utf-8'))
        : JSON.parse(raw.toString('utf-8'));
}

function buildInitInfo(replay) {
    return {
        laneInfo: [{
            initResources: replay.initInfo.initResources,
            base: replay.deckInfo.base,
            randomizer: replay.deckInfo.randomizer,
            initCards: replay.initInfo.initCards,
        }],
        mergedDeck: replay.deckInfo.mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: {
            commandList: replay.commandInfo.commandList,
            clicksPerTurn: replay.commandInfo.clicksPerTurn,
            gamePosition: replay.commandInfo.commandList.length,
        },
    };
}

function ratingsFromReplay(replay) {
    let p0 = 0, p1 = 0;
    const ir = replay.ratingInfo && replay.ratingInfo.initialRatings;
    if (ir && ir[0] && ir[0].displayRating) p0 = Math.round(ir[0].displayRating);
    if (ir && ir[1] && ir[1].displayRating) p1 = Math.round(ir[1].displayRating);
    return { p0, p1 };
}

// card_set = the DRAWN advanced units of this game, by display name. The authoritative
// source is deckInfo.randomizer (per-player arrays, normally identical) — it lists the
// purchasable random units and EXCLUDES needs-only created tokens (e.g. Gauss Charge),
// matching MB's config.cardSet semantics so `in_card_set` means the same in both corpora.
// Fallback (older replays lacking randomizer): non-base merged-deck entries (may include
// created tokens — a minor over-inclusion).
function buildAdvancedCardSet(replay) {
    const di = replay.deckInfo || {};
    const rnd = di.randomizer;
    if (Array.isArray(rnd) && rnd.length) {
        const set = new Set();
        for (const item of rnd) {
            if (Array.isArray(item)) { for (const n of item) set.add(n); }
            else if (typeof item === 'string') { set.add(item); }
        }
        if (set.size) return Array.from(set);
    }
    const md = di.mergedDeck || [];
    return md.filter(c => !c.baseSet).map(c => c.name);
}

// outcome_p0 = P(player 0 / first / white wins). Replay result: 0 = P0 wins, 1 = P1 wins,
// 2 = draw. Matches convert_human_to_v2.py (outcome_p0 = 1.0 - result, draw -> 0.5).
function outcomeP0(result) {
    if (result === 0) return 1.0;
    if (result === 1) return 0.0;
    return 0.5;  // draw (2) or any other code
}

function extractReplay(replay, code) {
    const examples = [];
    const analyzer = new Analyzer(buildInitInfo(replay), -1, -1, null);
    analyzer.loaderInit();
    const history = analyzer.beginTurnHistory;
    if (!history || history.length < 1) {
        return { error: 'no beginTurnHistory', examples };
    }
    const result = replay.result;
    if (result === undefined || result === null) {
        return { error: 'no result', examples };
    }
    const op0 = outcomeP0(result);
    const ratings = ratingsFromReplay(replay);
    const totalPlies = history.length;
    const cardSet = buildAdvancedCardSet(replay);  // fixed for the game

    // One V2 record per player-turn (state captured at start of that turn).
    for (let turnIdx = 0; turnIdx < history.length; turnIdx++) {
        const state = history[turnIdx];
        if (!state) continue;
        const ex = extractTrainingExampleV2(state, cardSet, turnIdx);
        // Stamp game-level metadata (matches MB record keys exactly).
        ex.outcome_p0 = op0;
        ex.replay_code = code;
        ex.total_plies = totalPlies;
        ex.rating_p0 = ratings.p0;
        ex.rating_p1 = ratings.p1;
        ex.game_date = '';
        examples.push(ex);
    }
    return { error: null, examples };
}

// --- CLI ---
function main() {
    const args = process.argv.slice(2);
    if (args[0] === '--one') {
        const replay = loadReplay(args[1]);
        const code = path.basename(args[1], '.json.gz').replace('.json', '');
        const { error, examples } = extractReplay(replay, code);
        if (error) { process.stderr.write(`ERROR: ${error}\n`); process.exit(1); }
        console.log(JSON.stringify({ code, turns: examples.length, examples }, null, 2));
        return;
    }

    let codesFile = null, replaysDir = '.', output = null, limit = Infinity;
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--codes') codesFile = args[++i];
        else if (args[i] === '--replays-dir') replaysDir = args[++i];
        else if (args[i] === '--output') output = args[++i];
        else if (args[i] === '--limit') limit = parseInt(args[++i]) || Infinity;
    }
    if (!codesFile || !output) {
        process.stderr.write('Usage: --codes <file> --replays-dir <dir> --output <jsonl> [--limit N]\n');
        process.exit(2);
    }

    const codes = fs.readFileSync(codesFile, 'utf-8').trim().split('\n').map(s => s.trim()).filter(Boolean);
    const out = fs.createWriteStream(output, { flags: 'w' });
    const droppedPath = output + '.dropped.txt';
    const dropped = fs.createWriteStream(droppedPath, { flags: 'w' });
    // Windows Node can emit a benign ERR_SYSTEM_ERROR on WriteStream close AFTER a full
    // flush; log it instead of crashing the process post-completion. A genuine write
    // failure (e.g. disk full) is still caught by the completeness check (last record's
    // replay_code == last code in the list).
    out.on('error', (e) => process.stderr.write(`[out stream] ${e.message}\n`));
    dropped.on('error', (e) => process.stderr.write(`[dropped stream] ${e.message}\n`));
    let ok = 0, droppedCount = 0, totalExamples = 0;
    const t0 = Date.now();

    for (const code of codes) {
        if (ok >= limit) break;
        const enc = code.replace(/\+/g, '%2B').replace(/@/g, '%40');
        let fp = path.join(replaysDir, enc + '.json.gz');
        if (!fs.existsSync(fp)) fp = path.join(replaysDir, code + '.json.gz');
        if (!fs.existsSync(fp)) { dropped.write(`${code}\tmissing-file\n`); droppedCount++; continue; }
        try {
            const replay = loadReplay(fp);
            const { error, examples } = extractReplay(replay, code);
            if (error) { dropped.write(`${code}\t${error}\n`); droppedCount++; continue; }
            for (const ex of examples) out.write(JSON.stringify(ex) + '\n');
            totalExamples += examples.length;
            ok++;
        } catch (e) {
            dropped.write(`${code}\t${(e && e.message) || 'exception'}\n`);
            droppedCount++;
            if (droppedCount <= 5) process.stderr.write(`  ${code}: ${e.message}\n`);
        }
        if ((ok + droppedCount) % 500 === 0 && ok > 0) {
            const rate = ok / ((Date.now() - t0) / 1000);
            process.stderr.write(`  ${ok} ok, ${totalExamples} examples, ${droppedCount} dropped [${rate.toFixed(1)}/s]\n`);
        }
    }
    out.end();
    dropped.end();
    process.stderr.write(`Done: ${ok} replays ok, ${totalExamples} examples, ${droppedCount} dropped (codes -> ${droppedPath}) -> ${output}\n`);
}

main();
