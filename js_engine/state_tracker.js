'use strict';

/**
 * state_tracker.js — Long-running Node.js state tracker for bot game management.
 *
 * Communicates via JSON lines on stdin/stdout.
 *
 * Protocol:
 *   {"cmd":"INIT","mergedDeck":[...]}       → {"ok":true}
 *   {"cmd":"EXPORT"}                         → {"ok":true,"state":{...}}
 *   {"cmd":"CLICKS","clicks":[...]}          → {"ok":true,"applied":N,"failed":N}
 *
 * Self-contained: does NOT require('./matchup_clean') — that module reads
 * matchup_config.json at load time and would throw if the file is absent.
 * Needed helpers are copied locally below.
 */

// ---------------------------------------------------------------------------
// Redirect console.log to stderr so it cannot corrupt the JSON protocol.
// All internal logging must use process.stderr.write or console.error.
// ---------------------------------------------------------------------------
console.log = (...args) => {
    process.stderr.write('[state_tracker log] ' + args.join(' ') + '\n');
};

const readline = require('readline');
const C = require('./C');
const Analyzer = require('./Analyzer');
const StateUtil = require('./StateUtil');

// ---------------------------------------------------------------------------
// Supply helpers (copied from card_library.js)
// ---------------------------------------------------------------------------

const SUPPLY_BY_RARITY = {
    legendary: 1,
    rare: 4,
    normal: 10,
    trinket: 20
};

function getSupply(card) {
    if (card.rarity === 'unbuyable') return 0;
    const supply = SUPPLY_BY_RARITY[card.rarity];
    if (supply === undefined) {
        process.stderr.write(`[state_tracker] Unknown rarity "${card.rarity}" for card "${card.name}" — defaulting to 20\n`);
        return 20;
    }
    return supply;
}

// ---------------------------------------------------------------------------
// buildGameInitInfo — copied from matchup_clean.js:1153-1192
// ---------------------------------------------------------------------------

/**
 * Build a gameInitInfo object from a mergedDeck for the Analyzer constructor.
 * White gets supply+1 Drones, Black gets supply (standard Prismata asymmetry).
 *
 * @param {Object[]} mergedDeck
 * @returns {Object} gameInitInfo suitable for new Analyzer(gameInitInfo, -1, -1, null)
 */
function buildGameInitInfo(mergedDeck) {
    const baseWhite = [];
    const baseBlack = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        const supply = card._needsOnly ? 0 : getSupply(card);
        if (card.baseSet) {
            if (card.name === 'Drone') {
                // White starts with 6 Drones, Black with 7.
                // Supply compensates so both totals match: 6+21 = 7+20 = 27.
                baseWhite.push([card.name, supply + 1]);  // 21
                baseBlack.push([card.name, supply]);       // 20
            } else {
                baseWhite.push([card.name, supply]);
                baseBlack.push([card.name, supply]);
            }
        } else {
            randomizer.push([card.name, supply]);
        }
    }

    return {
        laneInfo: [{
            initResources: ['0', '0'],
            base: [baseWhite, baseBlack],
            randomizer: [randomizer, randomizer],
            initCards: [
                [[6, 'Drone'], [2, 'Engineer']],   // White starts
                [[7, 'Drone'], [2, 'Engineer']]     // Black starts (extra Drone)
            ]
        }],
        mergedDeck: mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: null
    };
}

// ---------------------------------------------------------------------------
// autoBreachIfNeeded — ported from matchup_clean.js:320-405 (no recoveryStats)
// ---------------------------------------------------------------------------

/**
 * After applying AI clicks, automatically click weakest opponent units to
 * exhaust remaining breach damage if glassBroken is set.
 *
 * C++ emits a separate Breach phase; JS engine resolves breach within
 * the action phase via glassBroken. Without this, breach damage goes unspent.
 *
 * @param {Analyzer} analyzer
 * @returns {{ applied: number, failed: number }}
 */
function autoBreachIfNeeded(analyzer) {
    const gs = analyzer.gameState;
    let applied = 0;
    let failed = 0;

    if (!gs.glassBroken || gs.inEndBO || gs.finished ||
        gs.phase !== C.PHASE_ACTION) {
        return { applied, failed };
    }

    const opponent = 1 - gs.turn;
    let safety = 200; // prevent infinite loop

    while (gs.glassBroken && !gs.inEndBO && !gs.finished && safety-- > 0) {
        // End any active swipe before breach click
        if (analyzer.controller.inSwipe) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
            }
        }

        // Find weakest breachable opponent unit
        const atk = gs.turnMana.attack;
        let weakest = null;
        let weakestDmg = Infinity;

        gs.table.forEach((inst) => {
            if (inst.owner === opponent && !inst.dead &&
                inst.constructionTime === 0 &&
                inst.damageReqdToInjure <= atk &&
                inst.damageReqdToInjure < weakestDmg) {
                weakest = inst;
                weakestDmg = inst.damageReqdToInjure;
            }
        });

        if (!weakest) break; // no breachable target found

        const result = analyzer.recordClick(false, false, C.CLICK_INST, weakest.instId);
        if (result.canClick) {
            applied++;
        } else {
            failed++;
            break; // stop if click rejected
        }
    }

    if (safety <= 0) {
        process.stderr.write('[state_tracker] autoBreachIfNeeded: safety limit hit\n');
    }

    if (applied > 0) {
        // End breach swipe if active
        if (analyzer.controller.inSwipe) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
            }
        }

        // Try space click to enter confirm
        const spaceResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (spaceResult.canClick) {
            applied++;
        } else {
            failed++;
        }
    }

    return { applied, failed };
}

// ---------------------------------------------------------------------------
// applyClicks — simplified from matchup_clean.js:484-642 (no recoveryStats/diagnostics)
// ---------------------------------------------------------------------------

/**
 * Apply an array of clicks to the analyzer state.
 *
 * Handles:
 * - Auto-commit when in PHASE_CONFIRM and next click is non-space
 * - Breach space skip: ignore space clicks during glassBroken
 * - End-swipe retry: if click fails while in a swipe, end swipe and retry
 * - autoBreachIfNeeded after all clicks
 * - Final auto-commit if still in PHASE_CONFIRM after all clicks
 *
 * @param {Analyzer} analyzer
 * @param {Array<{_type: string, _id?: number}>} clicks
 * @returns {{ applied: number, failed: number }}
 */
function applyClicks(analyzer, clicks) {
    let applied = 0;
    let failed = 0;

    for (let i = 0; i < clicks.length; i++) {
        const click = clicks[i];
        const clickType = click._type;
        const clickId = click._id !== undefined ? click._id : -1;

        // Auto-commit: if in PHASE_CONFIRM and next click is not a space/undo/redo/revert,
        // insert a commit space click first so defense clicks reach the defense phase handler.
        if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished &&
            clickType !== C.CLICK_SPACE &&
            clickType !== 'revert clicked' &&
            clickType !== 'undo clicked' &&
            clickType !== 'redo clicked') {
            const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
            if (commitResult.canClick) {
                applied++;
            }
        }

        // Attempt the click
        let result = analyzer.recordClick(false, false, clickType, clickId);

        // Skip space clicks during breach: JS Controller doesn't accept them
        // during glassBroken; they are cosmetic from SteamAI/C++ breach sequencing.
        if (!result.canClick && clickType === C.CLICK_SPACE && analyzer.gameState.glassBroken) {
            continue;
        }

        // Retry with end-swipe: if click failed while in a swipe, end the swipe
        // and try again (handles cross-purpose transitions).
        if (!result.canClick && analyzer.controller.inSwipe && clickType !== C.CLICK_END_SWIPE) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
                result = analyzer.recordClick(false, false, clickType, clickId);
            }
        }

        if (result.canClick) {
            applied++;
        } else {
            failed++;
        }
    }

    // Auto-breach: if breach damage remains unspent after AI clicks, click weakest targets.
    const breachResult = autoBreachIfNeeded(analyzer);
    applied += breachResult.applied;
    failed += breachResult.failed;

    // Final auto-commit: C++ emits ONE space click (action→confirm), but JS needs TWO
    // (action→confirm + confirm→commit). Auto-commit if still in confirm phase.
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) {
            applied++;
        }
    }

    return { applied, failed };
}

// ---------------------------------------------------------------------------
// State — module-level analyzer instance
// ---------------------------------------------------------------------------

let analyzer = null;

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

/**
 * INIT — initialize a fresh game from a mergedDeck.
 *
 * @param {{ mergedDeck: Object[] }} cmd
 * @returns {{ ok: boolean, error?: string }}
 */
function handleInit(cmd) {
    if (!Array.isArray(cmd.mergedDeck) || cmd.mergedDeck.length === 0) {
        return { ok: false, error: 'INIT requires non-empty mergedDeck array' };
    }
    try {
        const gameInitInfo = buildGameInitInfo(cmd.mergedDeck);
        analyzer = new Analyzer(gameInitInfo, -1, -1, null);
        analyzer.loaderInit();
        return { ok: true };
    } catch (err) {
        analyzer = null;
        return { ok: false, error: String(err) };
    }
}

/**
 * EXPORT — serialize current game state to JSON object.
 *
 * @returns {{ ok: boolean, state?: Object, error?: string }}
 */
function handleExport() {
    if (!analyzer) {
        return { ok: false, error: 'Not initialized — send INIT first' };
    }
    try {
        const stateJson = analyzer.gameState.toString();
        const state = JSON.parse(stateJson);
        return { ok: true, state };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}

/**
 * CLICKS — apply a sequence of clicks to the current state.
 *
 * Accepts two click formats:
 *   1. Resolved format: [{_type: "inst clicked", _id: 42}, ...]
 *      Used when the caller has already resolved instance IDs (e.g. from C++).
 *   2. Raw SteamAI format: [{type: "inst clicked", args: {owner, cardName, ...}}, ...]
 *      Used when forwarding raw PrismataAI.exe aiclicks output.
 *      These are converted via StateUtil.convertToClicks before application.
 *
 * Detection: if the first click has a "type" key (not "_type"), it's raw SteamAI format.
 *
 * @param {{ clicks: Array }} cmd
 * @returns {{ ok: boolean, applied?: number, failed?: number, error?: string }}
 */
function handleClicks(cmd) {
    if (!analyzer) {
        return { ok: false, error: 'Not initialized — send INIT first' };
    }
    if (!Array.isArray(cmd.clicks)) {
        return { ok: false, error: 'CLICKS requires a clicks array' };
    }
    if (cmd.clicks.length > 500) {
        return { ok: false, error: `CLICKS array too large: ${cmd.clicks.length}` };
    }
    try {
        let clicks = cmd.clicks;

        // Detect raw SteamAI format: {type, args} vs resolved {_type, _id}
        if (clicks.length > 0 && clicks[0].type !== undefined && clicks[0]._type === undefined) {
            process.stderr.write(`[state_tracker] Converting ${clicks.length} raw SteamAI clicks via StateUtil\n`);
            try {
                const resolved = StateUtil.convertToClicks(clicks, analyzer.gameState, false);
                clicks = resolved;
            } catch (convertErr) {
                process.stderr.write(`[state_tracker] convertToClicks failed: ${convertErr.message} — applying raw\n`);
                // Fall back to raw application: map {type, args} to {_type, _id: -1}
                clicks = clicks.map(c => ({ _type: c.type, _id: -1 }));
            }
        }

        const { applied, failed } = applyClicks(analyzer, clicks);
        // Return resolved clicks so Python can send them to the server
        // in the correct {_type, _id} format
        return { ok: true, applied, failed, resolvedClicks: clicks };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}

// ---------------------------------------------------------------------------
// Uncaught exception handler — write to stderr and exit
// ---------------------------------------------------------------------------

process.on('uncaughtException', (err) => {
    process.stderr.write('[state_tracker] Uncaught exception: ' + err.stack + '\n');
    process.exit(1);
});

process.on('unhandledRejection', (reason) => {
    process.stderr.write('[state_tracker] Unhandled rejection: ' + String(reason) + '\n');
    process.exit(1);
});

// ---------------------------------------------------------------------------
// Main readline loop — read JSON lines from stdin, dispatch to handlers
// ---------------------------------------------------------------------------

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', (line) => {
    line = line.trim();
    if (!line) return;

    let cmd;
    try {
        cmd = JSON.parse(line);
    } catch (e) {
        const resp = { ok: false, error: 'Invalid JSON: ' + String(e) };
        process.stdout.write(JSON.stringify(resp) + '\n');
        return;
    }

    let resp;
    switch (cmd.cmd) {
        case 'INIT':
            resp = handleInit(cmd);
            break;
        case 'EXPORT':
            resp = handleExport();
            break;
        case 'CLICKS':
            resp = handleClicks(cmd);
            break;
        default:
            resp = { ok: false, error: 'Unknown command: ' + cmd.cmd };
    }

    process.stdout.write(JSON.stringify(resp) + '\n');
});

rl.on('close', () => {
    process.stderr.write('[state_tracker] stdin closed, exiting\n');
    process.exit(0);
});
