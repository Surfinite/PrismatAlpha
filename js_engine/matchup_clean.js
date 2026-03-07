'use strict';

/**
 * matchup_clean.js — Phase 7a/7b/7c/7d/7e: Matchup runner (clean room rebuild)
 *
 * Orchestrates Prismata games between C++ AI players and/or MCDSAI by:
 *   1. Verifying supply at init (rarity-based, no card.supply field)
 *   2. Initializing a JS game via Analyzer
 *   3. Looping: export state -> call C++ --suggest or MCDSAI -> apply clicks -> check game over
 *   4. Handling errors: retry on malformed JSON, forfeit/abort on repeated failure
 *   5. Stuck detection: abort as draw if state unchanged for N consecutive turns
 *   6. Multi-game: random card sets, per-game supply verification, tally results
 *   7. MCDSAI support: spawn workers, init per game, mixed C++/MCDSAI matchups
 *   8. Parallel workers: distribute games across worker_threads for concurrent execution
 *   9. Replay saving: optional per-game click sequence JSON files
 *
 * Usage:
 *   node matchup_clean.js                             # Base-set-only single game
 *   node matchup_clean.js --random                    # Random 8-unit set (single game)
 *   node matchup_clean.js --games 10                  # 10 games with random card sets
 *   node matchup_clean.js --games 50 --think-time 1000  # 50 fast games
 *   node matchup_clean.js --player LiveHardestAI      # Same AI for both sides
 *   node matchup_clean.js --player-white HardestAI --player-black LiveHardestAI
 *   node matchup_clean.js --think-time 5000           # Custom think time
 *   node matchup_clean.js --single-turn               # Phase 7a single-turn test mode
 *   node matchup_clean.js --player MCDSAI             # Both sides use MCDSAI
 *   node matchup_clean.js --player-white MCDSAI --player-black OriginalHardestAI  # Mixed
 *   node matchup_clean.js --player MCDSAI --mcdsai-difficulty HardestAI  # Custom difficulty
 *   node matchup_clean.js --games 6 --parallel 2      # 6 games across 2 parallel workers
 *   node matchup_clean.js --games 4 --parallel 2 --save-replays                    # Replays to bin/asset/replays/YYYY-MM-DD_HH-MM-SS/
 *   node matchup_clean.js --games 4 --parallel 2 --save-replays mcdsai_test      # Replays to bin/asset/replays/YYYY-MM-DD_HH-MM-SS_mcdsai_test/
 *   node matchup_clean.js --cards "Tarsier,Rhino,Steelsplitter"                   # Fixed advanced units (base set always included)
 *   node matchup_clean.js --cards "Doomed Drone,R,R,R,R,R,R,R"                   # 1 fixed + 7 random (re-rolled per game)
 *   node matchup_clean.js --games 20 --player-switch --parallel 4                 # 10 pairs, swapped sides per pair
 *   node matchup_clean.js --cards "Apollo,Cynestra" --player-switch --games 4       # 2 pairs with fixed set
 *   
 *   node matchup_clean.js --games 16 --parallel 4 --player-switch --think-time 5000 --player-white LiveHardestAI --player-black MCDSAI --save-replays TEST 2>matchup_run.log
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { Worker } = require('worker_threads');

const C = require('./C');
const Analyzer = require('./Analyzer');
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet, getAdvancedUnitNames, getSupply, SUPPLY_BY_RARITY } = require('./card_library');
const { stateToCppJSON, buildReplayJSON } = require('./replay_exporter');

// MCDSAI player identifier (case-insensitive matching in CLI parsing)
const MCDSAI_PLAYER = 'MCDSAI';

// ---------------------------------------------------------------------------
// Per-action click description
// ---------------------------------------------------------------------------

/**
 * Generate a human-readable label for a click action.
 * @param {Object} click - Click object with _type and _id
 * @param {Object} state - Current game state (after click was applied)
 * @returns {string} Human-readable action label
 */
function describeClick(click, state) {
    const phase = state.phase;
    switch (click._type) {
        case C.CLICK_CARD:
        case C.CLICK_CARD_SHIFT: {
            // Buy action -- look up card name from the cards array
            const cardIdx = click._id;
            if (state.cards && cardIdx >= 0 && cardIdx < state.cards.length) {
                return 'Buy ' + state.cards[cardIdx].UIName;
            }
            return 'Buy card #' + cardIdx;
        }
        case C.CLICK_INST:
        case C.CLICK_INST_SHIFT: {
            // Instance click -- look up unit name from table
            const inst = state.table.get(click._id);
            if (inst) {
                const name = inst.card.UIName;
                // In defense phase, it's blocking; in action phase, it's ability/assign
                if (phase === C.PHASE_DEFENSE) {
                    return 'Block with ' + name;
                }
                return 'Use ' + name;
            }
            return 'Click inst #' + click._id;
        }
        case C.CLICK_SPACE:
            return 'End Phase';
        case C.CLICK_END_SWIPE:
            return 'End Defense';
        case C.CLICK_REVERT:
            return 'Undo';
        default:
            return click._type;
    }
}

// Load config
const CONFIG_PATH = path.join(__dirname, 'matchup_config.json');
const CONFIG = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));

// C++ exe path (Release build)
const EXE_PATH = path.join(__dirname, '..', 'bin', CONFIG.exePath);

// Temp file for --suggest state JSON (PID-suffixed to avoid races between
// concurrent --parallel 1 processes sharing the same directory)
const SUGGEST_TMP = path.join(__dirname, `_suggest_state_${process.pid}.json`);

// Clean up PID-specific temp file on exit
process.on('exit', () => { try { fs.unlinkSync(SUGGEST_TMP); } catch (_) {} });

// ---------------------------------------------------------------------------
// 1. Supply verification
// ---------------------------------------------------------------------------

/**
 * Verify that every active card in the mergedDeck has correct supply
 * based on rarity. Uses getSupply() from card_library.js — NOT card.supply.
 *
 * Special case: Vivid Drone is normal rarity but supply=10 (custom).
 * getSupply() returns 20 for normal, so we accept both 10 and 20 for
 * Vivid Drone until that special case is baked into getSupply.
 *
 * @param {Object[]} mergedDeck
 * @returns {{ ok: boolean, mismatches: string[] }}
 */
function verifySupply(mergedDeck) {
    const mismatches = [];
    for (const card of mergedDeck) {
        if (card._inactive || card._needsOnly) continue;

        const supply = getSupply(card);
        const expectedByRarity = SUPPLY_BY_RARITY[card.rarity];

        if (expectedByRarity === undefined) {
            mismatches.push(`${card.name || card.UIName}: unknown rarity "${card.rarity}"`);
            continue;
        }

        if (supply !== expectedByRarity) {
            mismatches.push(
                `${card.name || card.UIName}: rarity=${card.rarity} expected=${expectedByRarity} got=${supply}`
            );
        }
    }

    if (mismatches.length > 0) {
        console.error('[Supply] MISMATCHES:');
        for (const m of mismatches) console.error('  ' + m);
    } else {
        console.error('[Supply] All active cards pass rarity-based supply check.');
    }

    return { ok: mismatches.length === 0, mismatches };
}

// ---------------------------------------------------------------------------
// 2. State export for --suggest
// ---------------------------------------------------------------------------

/**
 * Export the JS engine state to the JSON format that C++ DoSuggest expects.
 *
 * Uses State.toString() which serializes gameState with:
 *   cards, table, whiteMana, blackMana, whiteTotalSupply, blackTotalSupply,
 *   whiteSupplySpent, blackSupplySpent, numTurns, turn, phase
 *
 * Wraps it in the F6 format: { CurrentInfo: { mergedDeck, gameState } }
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - The original mergedDeck (active cards only)
 * @returns {Object} JSON object ready for --suggest
 */
function exportStateForSuggest(analyzer, mergedDeck) {
    // State.toString() returns a JSON string with the gameState fields
    const stateStr = analyzer.gameState.toString();
    const gameState = JSON.parse(stateStr);

    // Build the F6 CurrentInfo wrapper
    return {
        CurrentInfo: {
            mergedDeck: mergedDeck,
            gameState: gameState
        }
    };
}

// ---------------------------------------------------------------------------
// 3. Call C++ --suggest
// ---------------------------------------------------------------------------

/**
 * Write state JSON to temp file, spawn Prismata_Testing.exe --suggest,
 * and parse the JSON response.
 *
 * Handles:
 *   - PRISMATA_ASSERT noise before JSON (finds first line starting with '{')
 *   - Process timeout (thinkTime x timeoutMultiplier)
 *   - Non-zero exit codes
 *   - Malformed JSON
 *   - Control characters in output
 *
 * @param {Object} stateJson - The full state JSON (F6 format)
 * @param {string} playerName - AI player name (e.g., "OriginalHardestAI")
 * @param {number} thinkTimeMs - Think time in milliseconds
 * @returns {{ ok: boolean, response: Object|null, error: string|null }}
 */
function callSuggest(stateJson, playerName, thinkTimeMs) {
    // Write state to temp file
    fs.writeFileSync(SUGGEST_TMP, JSON.stringify(stateJson));

    const timeout = thinkTimeMs * CONFIG.timeoutMultiplier;

    let stdout;
    try {
        stdout = execFileSync(EXE_PATH, [
            '--suggest', SUGGEST_TMP,
            '--player', playerName,
            '--think-time', String(thinkTimeMs)
        ], {
            timeout: timeout,
            encoding: 'utf-8',
            maxBuffer: 10 * 1024 * 1024,  // 10 MB
            cwd: path.join(__dirname, '..', 'bin')  // working dir = bin/ (for config.txt, etc.)
        });
    } catch (err) {
        if (err.killed) {
            return { ok: false, response: null, error: `Process timed out after ${timeout}ms` };
        }
        // execFileSync throws on non-zero exit but may still have stdout
        if (err.stdout) {
            stdout = err.stdout;
        } else {
            return { ok: false, response: null, error: `Process error: ${err.message}` };
        }
    }

    // Strip control characters (MCDSAI/PRISMATA_ASSERT noise)
    const cleanStdout = stdout.replace(/[\x00-\x09\x0b\x0c\x0e-\x1f]/g, ' ');

    // Find the JSON line (first line starting with '{')
    const lines = cleanStdout.split('\n');
    const jsonLine = lines.find(l => l.trim().startsWith('{'));

    if (!jsonLine) {
        return {
            ok: false,
            response: null,
            error: `No JSON found in output. Raw output (first 500 chars): ${cleanStdout.substring(0, 500)}`
        };
    }

    let parsed;
    try {
        parsed = JSON.parse(jsonLine.trim());
    } catch (parseErr) {
        return {
            ok: false,
            response: null,
            error: `JSON parse error: ${parseErr.message}. Line: ${jsonLine.substring(0, 200)}`
        };
    }

    if (!parsed.ok) {
        return {
            ok: false,
            response: parsed,
            error: `C++ returned error: ${parsed.error || 'unknown'}`
        };
    }

    return { ok: true, response: parsed, error: null };
}

// ---------------------------------------------------------------------------
// 3b. Auto-breach: exhaust remaining attack on weakest opponent units
// ---------------------------------------------------------------------------

/**
 * When glassBroken=true and inEndBO=false, the JS engine requires all breach
 * damage to be assigned before allowing END_PHASE. The C++ engine has a separate
 * Breach phase, so its Move may not include enough ASSIGN_BREACH actions to
 * fully exhaust attack in the JS engine's single-phase model.
 *
 * This function auto-clicks the weakest opponent units until inEndBO becomes
 * true, then retries the space click to end the turn.
 *
 * @param {Analyzer} analyzer
 * @param {string[]} details - Log details array (mutated)
 * @returns {{ applied: number, failed: number }}
 */
function autoBreachIfNeeded(analyzer, details) {
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
                details.push(`  [auto-breach] OK: end swipe`);
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
            details.push(`  [auto-breach] OK: inst clicked id=${weakest.instId} (${weakest.card.cardName}, hp=${weakest.health})`);
        } else {
            failed++;
            details.push(`  [auto-breach] FAIL: inst clicked id=${weakest.instId} (${weakest.card.cardName})`);
            break; // stop if click rejected
        }
    }

    if (applied > 0) {
        // End breach swipe if active
        if (analyzer.controller.inSwipe) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
                details.push(`  [auto-breach] OK: end swipe (done)`);
            }
        }

        // Try space click to enter confirm
        const spaceResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (spaceResult.canClick) {
            applied++;
            details.push(`  [auto-breach] OK: space clicked (action->confirm)`);
        } else {
            failed++;
            details.push(`  [auto-breach] FAIL: space clicked (action->confirm)`);
        }

        console.error(`[Turn] Auto-breach: ${applied} applied, ${failed} failed`);
    }

    return { applied, failed };
}

// ---------------------------------------------------------------------------
// 4. Apply clicks from --suggest response
// ---------------------------------------------------------------------------

/**
 * Apply a click array from the --suggest response to the JS analyzer.
 *
 * Click format from C++: {_type: "inst clicked", _id: 0}
 *                         {_type: "card clicked", _id: 0}
 *                         {_type: "space clicked", _id: -1}
 *                         {_type: "end swipe processed", _id: N}
 *
 * The C++ Move already contains individual per-unit actions (one USE_ABILITY
 * per card instance). DoSuggest emits one "inst clicked" per instance with
 * the client instId. No shift-click expansion is needed — the JS engine
 * handles individual clicks correctly.
 *
 * Click types from C++:
 *   "inst clicked"          — ability activation or breach target (per-instance)
 *   "inst clicked" x2       — SNIPE/CHILL (source then target)
 *   "inst clicked" + "end swipe processed" — defense blocker assignment
 *   "card clicked"          — buy (one per purchase)
 *   "space clicked"         — phase transition
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} clicks - Array of {_type, _id} objects
 * @returns {{ applied: number, failed: number, details: string[] }}
 */
function applyClicks(analyzer, clicks, actionStates) {
    let applied = 0;
    let failed = 0;
    const details = [];

    for (let i = 0; i < clicks.length; i++) {
        const click = clicks[i];
        const clickType = click._type;
        const clickId = click._id !== undefined ? click._id : -1;

        // Auto end-swipe: C++ --suggest doesn't emit end-swipe clicks.
        // A stale swipe (e.g., SWIPEPURPOSE_ASSIGN from a Rhino ability) blocks
        // subsequent clicks of different purpose (e.g., melee on opponent's unit).
        // Same pattern as StateUtil.convertToClicks() for MCDSAI clicks.
        if (analyzer.controller.inSwipe && clickType !== C.CLICK_END_SWIPE) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
                details.push(`  [auto] OK: end swipe processed`);
            }
        }

        // Auto-commit: C++ AI Move has ONE space click for action→confirm,
        // but JS engine needs TWO (action→confirm + confirm→commit→defense).
        // If we're in confirm phase and next click is a defense click (inst/endswipe),
        // auto-commit so defense clicks reach the defense phase handler.
        if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished &&
            clickType !== C.CLICK_SPACE && clickType !== 'revert clicked' &&
            clickType !== 'undo clicked' && clickType !== 'redo clicked') {
            const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
            if (commitResult.canClick) {
                applied++;
                details.push(`  [auto] OK: space clicked (confirm->commit)`);
            }
        }

        const result = analyzer.recordClick(false, false, clickType, clickId);
        if (result.canClick) {
            applied++;
            details.push(`  [${i}] OK: ${clickType} id=${clickId}`);
            if (actionStates) {
                actionStates.push({
                    state: stateToCppJSON(analyzer.gameState),
                    action: describeClick(click, analyzer.gameState)
                });
            }
        } else {
            failed++;
            // Diagnostic: why did this click fail?
            const gs = analyzer.gameState;
            let diag = `phase=${gs.phase}`;
            if (gs.glassBroken) diag += ` glassBroken`;
            if (gs.inEndBO) diag += ` inEndBO`;
            if (gs.wouldWipeout) diag += ` wouldWipeout`;
            if (gs.finished) diag += ` FINISHED`;
            diag += ` canBreach=${gs.canBreach} canOverkill=${gs.canOverkill}`;
            diag += ` oppNonInv=${gs.helper.oppNonInvTotal} oppDef=${gs.helper.oppDefense}`;
            diag += ` atk=${gs.turnMana.attack}`;
            if (clickType === 'inst clicked' || clickType === 'inst shift clicked') {
                const inst = gs.instIdToInst(clickId);
                if (inst) {
                    diag += ` | inst: ${inst.card.cardName} owner=P${inst.owner} role=${inst.role} hp=${inst.health} dead=${inst.deadness}`;
                    diag += ` dmg=${inst.damage} blocking=${inst.blocking} undef=${inst.card.undefendable}`;
                    diag += ` partDmg=${inst.isPartiallyDamaged} cTime=${inst.constructionTime}`;
                    if (inst.card.abilityScript) diag += ` hasAbility`;
                    if (inst.role === 'assigned') diag += ` assigned`;
                    if (inst.role === 'inert') diag += ` INERT`;
                    if (inst.constructionTime > 0) diag += ` building(${inst.constructionTime})`;
                } else {
                    diag += ` | inst NOT FOUND`;
                }
            }
            details.push(`  [${i}] FAIL: ${clickType} id=${clickId} [${diag}]`);
        }
    }

    // Auto-breach: C++ has a separate Breach phase, so its Move may emit a
    // space click (action->breach) that JS rejects. After all clicks, if breach
    // damage remains unspent, auto-click weakest opponent units to exhaust it.
    const breachResult = autoBreachIfNeeded(analyzer, details);
    applied += breachResult.applied;
    failed += breachResult.failed;

    // C++ DoSuggest adds ONE "space clicked" at the end (action->confirm),
    // but Prismata requires TWO to fully end a turn (action->confirm->commit).
    // If we're in confirm phase after applying all clicks, auto-commit.
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) {
            applied++;
            details.push(`  [auto] OK: space clicked (confirm->commit)`);
            if (actionStates) {
                actionStates.push({
                    state: stateToCppJSON(analyzer.gameState),
                    action: 'End Turn'
                });
            }
        } else {
            details.push(`  [auto] FAIL: space clicked (confirm->commit)`);
        }
    }

    return { applied, failed, details };
}

// ---------------------------------------------------------------------------
// 5. Play a single turn
// ---------------------------------------------------------------------------

/**
 * Orchestrate one turn: export state, call --suggest, apply clicks.
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - Active mergedDeck for the game
 * @param {string} playerName - AI player name
 * @param {number} thinkTimeMs - Think time
 * @returns {{ ok: boolean, suggest: Object|null, clickResult: Object|null, error: string|null }}
 */
function playSingleTurn(analyzer, mergedDeck, playerName, thinkTimeMs) {
    // Record pre-turn state
    const preTurn = analyzer.gameState.turn;
    const preNumTurns = analyzer.gameState.numTurns;
    const prePhase = analyzer.gameState.phase;

    console.error(`\n[Turn] Player ${preTurn} (${preTurn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns=${preNumTurns}, phase=${prePhase}`);

    // Export state
    const stateJson = exportStateForSuggest(analyzer, mergedDeck);
    console.error('[Turn] State exported for --suggest');

    // Call C++ --suggest
    console.error(`[Turn] Calling --suggest with player=${playerName}, thinkTime=${thinkTimeMs}ms...`);
    const suggestResult = callSuggest(stateJson, playerName, thinkTimeMs);

    if (!suggestResult.ok) {
        console.error(`[Turn] --suggest FAILED: ${suggestResult.error}`);
        return { ok: false, suggest: suggestResult, clickResult: null, error: suggestResult.error };
    }

    const resp = suggestResult.response;
    console.error(`[Turn] --suggest OK: eval=${resp.eval_pct}, think=${resp.think_ms}ms`);
    console.error(`[Turn] Buys: [${(resp.buy || []).join(', ')}]`);
    console.error(`[Turn] Abilities: [${(resp.abilities || []).join(', ')}]`);
    console.error(`[Turn] Clicks: ${(resp.clicks || []).length} total`);
    // Apply clicks to JS engine
    const clicks = resp.clicks || [];
    if (clicks.length === 0) {
        console.error('[Turn] WARNING: 0 clicks returned');
        return { ok: true, suggest: suggestResult, clickResult: { applied: 0, failed: 0, details: [] }, error: null };
    }

    console.error('[Turn] Applying clicks to JS engine...');
    const actionStates = [];
    const clickResult = applyClicks(analyzer, clicks, actionStates);

    console.error(`[Turn] Clicks: ${clickResult.applied} applied, ${clickResult.failed} failed`);
    if (clickResult.failed > 0) {
        for (const d of clickResult.details) {
            if (d.includes('FAIL')) console.error(d);
        }
    }

    // Post-turn state
    const postTurn = analyzer.gameState.turn;
    const postNumTurns = analyzer.gameState.numTurns;
    const postPhase = analyzer.gameState.phase;
    const finished = analyzer.gameState.finished;

    console.error(`[Turn] After: player=${postTurn}, numTurns=${postNumTurns}, ` +
                  `phase=${postPhase}, finished=${finished}`);

    return { ok: true, suggest: suggestResult, clickResult, actionStates, error: null };
}

// ---------------------------------------------------------------------------
// 5b. Play a single MCDSAI turn (Phase 7d)
// ---------------------------------------------------------------------------

/**
 * Helper: check if a player name is MCDSAI (case-insensitive).
 * @param {string} playerName
 * @returns {boolean}
 */
function isMCDSAIPlayer(playerName) {
    return playerName.toUpperCase() === MCDSAI_PLAYER;
}

/**
 * Orchestrate one MCDSAI turn: get state, call MCDSAI worker, apply clicks.
 *
 * Follows the selfplay_main.js pattern for MCDSAI interaction:
 *   1. Serialize game state via analyzer.gameState.toString()
 *   2. Select AI params based on turn number
 *   3. Call worker.getAIMove() with {gameState, aiPlayerName}
 *   4. Strip control chars, parse JSON response
 *   5. Handle resignation and 0-click failures
 *   6. Convert clicks via StateUtil.convertToClicks()
 *   7. Apply clicks via analyzer.recordClick()
 *   8. Fall back to direct click application if convertToClicks throws
 *
 * @param {Analyzer} analyzer
 * @param {Object[]} mergedDeck - Active mergedDeck for the game (unused but kept for API symmetry)
 * @param {MCDSAIWorker} mcdsaiWorker - Spawned and initialized MCDSAI worker
 * @param {string} difficulty - MCDSAI difficulty name (e.g., "HardestAI")
 * @returns {Promise<{ ok: boolean, clickResult: Object|null, error: string|null }>}
 */
async function playMCDSAITurn(analyzer, mergedDeck, mcdsaiWorker, difficulty) {
    // Lazy-load StateUtil (only needed when MCDSAI is actually used)
    const StateUtil = require('./StateUtil');

    const preTurn = analyzer.gameState.turn;
    const preNumTurns = analyzer.gameState.numTurns;
    const prePhase = analyzer.gameState.phase;

    console.error(`\n[Turn] Player ${preTurn} (${preTurn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns=${preNumTurns}, phase=${prePhase} [MCDSAI]`);

    // 1. Serialize game state
    const stateStr = analyzer.gameState.toString();
    const stateObj = JSON.parse(stateStr);

    // 2. Build move request JSON
    const moveJson = JSON.stringify({
        gameState: stateObj,
        aiPlayerName: difficulty
    });

    // 3. Call MCDSAI worker
    console.error(`[Turn] Calling MCDSAI (difficulty=${difficulty})...`);
    let response;
    try {
        const resultStr = await mcdsaiWorker.getAIMove(moveJson);
        // CRITICAL: MCDSAI response contains control characters — strip before JSON.parse
        const cleanResult = resultStr.replace(/[\x00-\x1f]/g, ' ');
        response = JSON.parse(cleanResult);
    } catch (err) {
        console.error(`[Turn] MCDSAI error: ${err.message}`);
        return { ok: false, clickResult: null, error: `MCDSAI error: ${err.message}` };
    }

    // 4. Handle resignation
    if (response.airesign) {
        console.error(`[Turn] MCDSAI resigned`);
        // Record as loss for active player
        analyzer.gameState.result = preTurn === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
        return { ok: true, clickResult: { applied: 0, failed: 0, details: ['MCDSAI resigned'] }, error: null };
    }

    // 5. Handle 0 clicks (AI failure — missing card name, etc.)
    const aiclicks = response.aiclicks || [];
    if (aiclicks.length === 0) {
        const thinkTime = response.aithinktime || 'unknown';
        console.error(`[Turn] MCDSAI returned 0 clicks (${thinkTime}ms think) — AI failure`);
        return { ok: false, clickResult: { applied: 0, failed: 0, details: [] }, error: `MCDSAI 0 clicks (${thinkTime}ms think)` };
    }

    console.error(`[Turn] MCDSAI returned ${aiclicks.length} AI clicks (${response.aithinktime || '?'}ms think)`);

    // 6-8. Convert and apply clicks
    let applied = 0;
    let failed = 0;
    const details = [];
    const actionStates = [];

    try {
        // Primary path: use StateUtil.convertToClicks for validated click resolution
        const clicks = StateUtil.convertToClicks(aiclicks, analyzer.gameState, false);

        for (let i = 0; i < clicks.length; i++) {
            const click = clicks[i];
            const result = analyzer.recordClick(false, false, click._type, click._id, click._params);
            if (result.canClick) {
                applied++;
                details.push(`  [${i}] OK: ${click._type} id=${click._id}`);
                actionStates.push({
                    state: stateToCppJSON(analyzer.gameState),
                    action: describeClick(click, analyzer.gameState)
                });
            } else {
                failed++;
                // Diagnostic: why did this click fail?
                const gs = analyzer.gameState;
                let diag = `phase=${gs.phase}`;
                if (gs.glassBroken) diag += ` glassBroken`;
                if (gs.inEndBO) diag += ` inEndBO`;
                if (gs.wouldWipeout) diag += ` wouldWipeout`;
                if (gs.finished) diag += ` FINISHED`;
                diag += ` canBreach=${gs.canBreach} canOverkill=${gs.canOverkill}`;
                diag += ` oppNonInv=${gs.helper.oppNonInvTotal} oppDef=${gs.helper.oppDefense}`;
                diag += ` atk=${gs.turnMana.attack}`;
                if (click._type === 'inst clicked' || click._type === 'inst shift clicked') {
                    const inst = gs.instIdToInst(click._id);
                    if (inst) {
                        diag += ` | inst: ${inst.card.cardName} owner=P${inst.owner} role=${inst.role} hp=${inst.health} dead=${inst.deadness}`;
                        if (inst.card.abilityScript) diag += ` hasAbility`;
                        if (inst.role === 'assigned') diag += ` assigned`;
                        if (inst.role === 'inert') diag += ` INERT`;
                        if (inst.constructionTime > 0) diag += ` building(${inst.constructionTime})`;
                    } else {
                        diag += ` | inst NOT FOUND`;
                    }
                }
                details.push(`  [${i}] FAIL: ${click._type} id=${click._id} [${diag}]`);
            }
        }
    } catch (err) {
        // Fallback: if convertToClicks fails (missing inst, illegal click), apply directly
        console.error(`[Turn] convertToClicks failed (${err.message}), falling back to direct application`);
        for (let i = 0; i < aiclicks.length; i++) {
            const ac = aiclicks[i];
            try {
                let clickType = ac.type;
                let clickId = -1;

                if (clickType === C.CLICK_CARD || clickType === C.CLICK_CARD_SHIFT) {
                    const card = analyzer.gameState.cardNameToCard(ac.args);
                    if (card) clickId = card.cardId;
                } else if (clickType === C.CLICK_INST || clickType === C.CLICK_INST_SHIFT) {
                    clickId = StateUtil.findInstId(ac.args, analyzer);
                }

                const result = analyzer.recordClick(false, false, clickType, clickId);
                if (result.canClick) {
                    applied++;
                    details.push(`  [${i}] OK (fallback): ${clickType} id=${clickId}`);
                    actionStates.push({
                        state: stateToCppJSON(analyzer.gameState),
                        action: describeClick({ _type: clickType, _id: clickId }, analyzer.gameState)
                    });
                } else {
                    failed++;
                    details.push(`  [${i}] FAIL (fallback): ${clickType} id=${clickId}`);
                }
            } catch (clickErr) {
                failed++;
                details.push(`  [${i}] ERROR (fallback): ${ac.type} — ${clickErr.message}`);
            }
        }
    }

    // Auto-breach: MCDSAI may not fully assign breach damage (same C++/JS phase mismatch)
    const breachResult = autoBreachIfNeeded(analyzer, details);
    applied += breachResult.applied;
    failed += breachResult.failed;

    // Auto-confirm: if we're in PHASE_CONFIRM after applying all MCDSAI clicks, auto-commit
    // (same pattern as applyClicks() does for C++ suggest)
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) {
            applied++;
            details.push(`  [auto] OK: space clicked (confirm->commit)`);
            actionStates.push({
                state: stateToCppJSON(analyzer.gameState),
                action: 'End Turn'
            });
        } else {
            details.push(`  [auto] FAIL: space clicked (confirm->commit)`);
        }
    }

    console.error(`[Turn] MCDSAI clicks: ${applied} applied, ${failed} failed`);
    if (failed > 0) {
        for (const d of details) {
            if (d.includes('FAIL') || d.includes('ERROR')) console.error(d);
        }
    }

    // Post-turn state
    const postTurn = analyzer.gameState.turn;
    const postNumTurns = analyzer.gameState.numTurns;
    const postPhase = analyzer.gameState.phase;
    const finished = analyzer.gameState.finished;

    console.error(`[Turn] After: player=${postTurn}, numTurns=${postNumTurns}, ` +
                  `phase=${postPhase}, finished=${finished}`);

    return { ok: true, clickResult: { applied, failed, details }, actionStates, error: null };
}

// ---------------------------------------------------------------------------
// 6. State summary printer
// ---------------------------------------------------------------------------

/**
 * Print a concise state summary showing unit counts and mana.
 */
function printStateSummary(analyzer, label) {
    const gs = analyzer.gameState;
    const stateStr = gs.toString();
    const state = JSON.parse(stateStr);

    console.error(`\n=== ${label} ===`);
    console.error(`Turn: ${state.turn} (${state.turn === 0 ? 'White' : 'Black'}), ` +
                  `numTurns: ${state.numTurns}, phase: ${state.phase}`);
    console.error(`White mana: ${state.whiteMana}`);
    console.error(`Black mana: ${state.blackMana}`);

    // Count units per player
    const whiteCounts = {};
    const blackCounts = {};
    for (const inst of state.table) {
        if (inst.deadness !== 'alive') continue;
        const bucket = inst.owner === 0 ? whiteCounts : blackCounts;
        bucket[inst.cardName] = (bucket[inst.cardName] || 0) + 1;
    }

    const fmtCounts = (counts) => {
        const parts = [];
        for (const [name, count] of Object.entries(counts).sort()) {
            parts.push(`${name}x${count}`);
        }
        return parts.join(', ') || '(none)';
    };

    console.error(`White units: ${fmtCounts(whiteCounts)}`);
    console.error(`Black units: ${fmtCounts(blackCounts)}`);

    // Supply spent
    const spentWhite = [];
    const spentBlack = [];
    for (let i = 0; i < state.cards.length; i++) {
        if (state.whiteSupplySpent[i] > 0) spentWhite.push(`${state.cards[i]}:${state.whiteSupplySpent[i]}`);
        if (state.blackSupplySpent[i] > 0) spentBlack.push(`${state.cards[i]}:${state.blackSupplySpent[i]}`);
    }
    if (spentWhite.length > 0) console.error(`White bought: ${spentWhite.join(', ')}`);
    if (spentBlack.length > 0) console.error(`Black bought: ${spentBlack.join(', ')}`);
    console.error('');
}

// ---------------------------------------------------------------------------
// 7. Build game init info (from selfplay_main.js pattern)
// ---------------------------------------------------------------------------

/**
 * Build a gameInitInfo object from a mergedDeck for the Analyzer constructor.
 * Identical to the pattern in selfplay_main.js.
 *
 * @param {Object[]} mergedDeck - Active card definitions
 * @returns {Object} gameInitInfo suitable for Analyzer constructor
 */
function buildGameInitInfo(mergedDeck) {
    const baseWhite = [];
    const baseBlack = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        // Needs-only cards get supply 0 — present for script references, not buyable.
        // Cards created via ability scripts bypass supply checks entirely.
        const supply = card._needsOnly ? 0 : getSupply(card);
        if (card.baseSet) {
            if (card.name === 'Drone') {
                // White starts with 6 Drones, Black with 7 — supply must
                // compensate so both have equal total: 6+21 = 7+20 = 27
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
                [[7, 'Drone'], [2, 'Engineer']]    // Black starts (extra Drone)
            ]
        }],
        mergedDeck: mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: null
    };
}

// ---------------------------------------------------------------------------
// 8. Play a single complete game (Phase 7b)
// ---------------------------------------------------------------------------

/**
 * Compute a simple hash of the game state for stuck detection.
 * Uses the full state JSON string — any change in units, mana, supply,
 * phase, or turn will produce a different hash.
 *
 * @param {Object} analyzer
 * @returns {string} State hash (the full JSON string)
 */
function getStateHash(analyzer) {
    return analyzer.gameState.toString();
}

/**
 * Map state.result to a human-readable string.
 *
 * @param {number} result - state.result value (C.COLOR_WHITE, C.COLOR_BLACK, etc.)
 * @returns {string}
 */
function resultToString(result) {
    if (result === C.COLOR_WHITE) return 'White (P0)';
    if (result === C.COLOR_BLACK) return 'Black (P1)';
    if (result === C.COLOR_DRAW_MUTUAL_ELIMINATION) return 'Draw (mutual elimination)';
    if (result === C.COLOR_DRAW_STALEMATE) return 'Draw (stalemate)';
    if (result === C.COLOR_NONE) return 'Ongoing';
    return `Unknown (${result})`;
}

// ---------------------------------------------------------------------------
// 8a. WillScore material evaluation (mirrors C++ Eval::WillScoreSum)
// ---------------------------------------------------------------------------

// Resource weights from C++ Heuristics.cpp:7-14
const WILL_VALUE_ATTACK = 2.25;
const WILL_VALUE_BLUE   = 1.50;
const WILL_VALUE_GREEN  = 1.20;
const WILL_VALUE_MONEY  = 1.00;
const WILL_VALUE_RED    = 0.90;
const WILL_VALUE_ENERGY = 0.50;

// Material advantage threshold (matches C++ PlayerShouldResign Stage 1)
const WILL_SCORE_THRESHOLD = 1.3;

/**
 * Compute WillScore material evaluation for a player.
 * Mirrors C++ Eval::WillScoreSum / Heuristics::CalculateBuyManaCost.
 *
 * For each non-dead unit owned by the player, sums the cost-weighted
 * buy cost using Churchill's resource multipliers. Skips doomed units
 * (lifespan === 1) since they're about to die.
 *
 * @param {State} state - Game state (state.table is AS3Dictionary of Inst)
 * @param {number} playerIndex - 0 or 1
 * @returns {number} WillScore sum (higher = more material)
 */
function computeWillScoreSum(state, playerIndex) {
    let sum = 0;
    state.table.forEach((inst) => {
        if (inst.owner !== playerIndex) return;
        if (inst.dead) return;
        if (inst.lifespan === 1) return;  // Doomed — about to expire

        const cost = inst.card.buyCost;
        sum += cost.amountOf(C.MANA_P) * WILL_VALUE_MONEY
             + cost.amountOf(C.MANA_G) * WILL_VALUE_GREEN
             + cost.amountOf(C.MANA_B) * WILL_VALUE_BLUE
             + cost.amountOf(C.MANA_R) * WILL_VALUE_RED
             + cost.amountOf(C.MANA_H) * WILL_VALUE_ENERGY
             + cost.attack * WILL_VALUE_ATTACK;
    });
    return sum;
}

/**
 * Adjudicate a terminated game by material advantage.
 *
 * Called when stagnation, stuck detection, or max turns fires.
 * Computes WillScoreSum for both players and awards win if one
 * has >= 1.3x the other's material. Otherwise declares draw.
 *
 * @param {Object} analyzer - Game analyzer (analyzer.gameState)
 * @param {string} reason - Termination reason label (e.g. "Stagnation", "Stuck", "Max turns")
 * @param {number} turnCount - Current turn number
 * @returns {{ result: number, abortReason: string }}
 */
function adjudicateByMaterial(analyzer, reason, turnCount) {
    const ws0 = computeWillScoreSum(analyzer.gameState, 0);
    const ws1 = computeWillScoreSum(analyzer.gameState, 1);
    console.error(`[${reason}] WillScore: P0=${ws0.toFixed(1)}, P1=${ws1.toFixed(1)}`);

    const maxWs = Math.max(ws0, ws1);
    const minWs = Math.min(ws0, ws1);

    if (maxWs >= (minWs + 0.01) * WILL_SCORE_THRESHOLD) {
        const winner = ws0 > ws1 ? 0 : 1;
        return {
            result: winner,
            abortReason: `${reason}: P${winner} wins by material (${ws0.toFixed(1)} vs ${ws1.toFixed(1)}) at turn ${turnCount}`
        };
    }
    return {
        result: C.COLOR_DRAW_STALEMATE,
        abortReason: `${reason} draw at turn ${turnCount} (material close: ${ws0.toFixed(1)} vs ${ws1.toFixed(1)})`
    };
}

// ---------------------------------------------------------------------------
// 8b. Play a single complete game (Phase 7b)
// ---------------------------------------------------------------------------

/**
 * Play a complete game from init to game-over (or abort).
 *
 * Alternates Player 0 (White) and Player 1 (Black) turns,
 * calling C++ --suggest or MCDSAI for each turn and applying clicks to the JS engine.
 *
 * Error handling:
 *   - Malformed JSON from --suggest: retry once (retryOnError), then forfeit
 *   - --suggest crash (non-zero exit): mark game invalid
 *   - --suggest timeout: mark game invalid
 *   - MCDSAI error: retry once, then forfeit
 *   - recordClick failure: log and continue (applyClicks handles this)
 *   - Stuck detection: if state hash unchanged for stuckDetectionTurns
 *     consecutive turns, abort as draw
 *
 * @param {Object[]} activeDeck - Active mergedDeck cards
 * @param {Object} config - Game configuration
 * @param {string} config.playerWhite - White player name or "MCDSAI"
 * @param {string} config.playerBlack - Black player name or "MCDSAI"
 * @param {number} config.thinkTimeMs - Think time for C++ players
 * @param {Object} [config.mcdsai] - MCDSAI configuration (required if any player is MCDSAI)
 * @param {MCDSAIWorker|null} [config.mcdsai.workerWhite] - MCDSAI worker for white
 * @param {MCDSAIWorker|null} [config.mcdsai.workerBlack] - MCDSAI worker for black
 * @param {string} [config.mcdsai.difficulty] - MCDSAI difficulty name (default: "HardestAI")
 * @param {string} [config.mcdsai.fullParams] - Full AI params string
 * @param {string} [config.mcdsai.shortParams] - Short AI params string
 * @param {Map} [config.mcdsai.library] - Card library for buildInitDeck
 * @returns {Promise<{ result: number, winner: string, turns: number, errors: string[], abortReason: string|null }>}
 */
async function playSingleGame(activeDeck, config) {
    const playerWhite = config.playerWhite;
    const playerBlack = config.playerBlack;
    const thinkTimeMs = config.thinkTimeMs;
    const maxTurns = CONFIG.maxTurns || 200;
    const retryOnError = CONFIG.retryOnError || 1;
    const stuckThreshold = CONFIG.stuckDetectionTurns || 5;

    // MCDSAI config (may be null if no MCDSAI players)
    const mcdsaiConfig = config.mcdsai || null;
    const whiteIsMCDSAI = isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = isMCDSAIPlayer(playerBlack);

    const errors = [];
    let abortReason = null;

    // Initialize game
    const gameInitInfo = buildGameInitInfo(activeDeck);
    const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    const whiteLabel = whiteIsMCDSAI ? `MCDSAI(${mcdsaiConfig ? mcdsaiConfig.difficulty : '?'})` : playerWhite;
    const blackLabel = blackIsMCDSAI ? `MCDSAI(${mcdsaiConfig ? mcdsaiConfig.difficulty : '?'})` : playerBlack;
    console.error('[Game] Initialized. White=' + whiteLabel + ', Black=' + blackLabel);
    printStateSummary(analyzer, 'GAME START');

    // Initialize MCDSAI workers for this game (per-game init with deck)
    if ((whiteIsMCDSAI || blackIsMCDSAI) && mcdsaiConfig) {
        const _sp = require('./ai_params').selectParams;
        const fullParams = mcdsaiConfig.fullParams;
        const shortParams = mcdsaiConfig.shortParams;
        const difficulty = mcdsaiConfig.difficulty || 'HardestAI';
        const library = mcdsaiConfig.library;

        // Build init deck (includes AI param-referenced cards beyond the activeDeck)
        const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
        const initParams = JSON.parse(_sp(difficulty, 1, fullParams, shortParams));
        const initJson = JSON.stringify({
            mergedDeck: initDeck,
            aiParameters: initParams
        });

        if (whiteIsMCDSAI && mcdsaiConfig.workerWhite) {
            console.error('[Game] Initializing MCDSAI worker for White...');
            await mcdsaiConfig.workerWhite.initializeAI(initJson);
        }
        if (blackIsMCDSAI && mcdsaiConfig.workerBlack) {
            console.error('[Game] Initializing MCDSAI worker for Black...');
            await mcdsaiConfig.workerBlack.initializeAI(initJson);
        }
    }

    // Stuck detection state
    const recentHashes = [];  // circular buffer of last N state hashes
    let turnCount = 0;

    // Replay data collection
    const allActionStates = [];
    const allActionLabels = [];
    const turnBoundaries = [];

    // Main game loop
    while (!analyzer.gameState.finished && turnCount < maxTurns) {
        turnCount++;

        const activePlayer = analyzer.gameState.turn;
        const playerName = activePlayer === 0 ? playerWhite : playerBlack;
        const playerLabel = activePlayer === 0 ? 'White' : 'Black';
        const isActiveMCDSAI = isMCDSAIPlayer(playerName);

        console.error(`\n[Game] === Turn ${turnCount} (${playerLabel}, player=${playerName}${isActiveMCDSAI ? ' [MCDSAI]' : ''}) ===`);

        // Capture pre-turn state snapshot for replay
        try {
            turnBoundaries.push(allActionStates.length);
            allActionStates.push(stateToCppJSON(analyzer.gameState));
            allActionLabels.push('Start of Turn');
        } catch (e) { /* non-critical */ }

        // --- Stuck detection: capture pre-turn state hash ---
        const preHash = getStateHash(analyzer);

        // --- Call appropriate turn function with retry logic ---
        let turnResult;
        if (isActiveMCDSAI && mcdsaiConfig) {
            const worker = activePlayer === 0 ? mcdsaiConfig.workerWhite : mcdsaiConfig.workerBlack;
            turnResult = await playMCDSAITurn(
                analyzer, activeDeck, worker,
                mcdsaiConfig.difficulty || 'HardestAI'
            );
        } else {
            turnResult = playSingleTurn(analyzer, activeDeck, playerName, thinkTimeMs);
        }

        if (!turnResult.ok) {
            // Retry once on error (malformed JSON, parse failure, etc.)
            console.error(`[Game] Turn ${turnCount} failed: ${turnResult.error}`);
            console.error(`[Game] Retrying (attempt 2/${retryOnError + 1})...`);

            // Dump state for debugging
            try {
                const stateDump = analyzer.gameState.toString();
                console.error(`[Game] State dump at failure:\n${stateDump.substring(0, 1000)}`);
            } catch (dumpErr) {
                console.error(`[Game] State dump failed: ${dumpErr.message}`);
            }

            // Retry
            if (isActiveMCDSAI && mcdsaiConfig) {
                const worker = activePlayer === 0 ? mcdsaiConfig.workerWhite : mcdsaiConfig.workerBlack;
                turnResult = await playMCDSAITurn(
                    analyzer, activeDeck, worker,
                    mcdsaiConfig.difficulty || 'HardestAI'
                );
            } else {
                turnResult = playSingleTurn(analyzer, activeDeck, playerName, thinkTimeMs);
            }

            if (!turnResult.ok) {
                // Second failure — check error type for appropriate handling
                const errMsg = turnResult.error || '';
                errors.push(`Turn ${turnCount} (${playerLabel}): ${errMsg}`);

                if (errMsg.includes('timed out')) {
                    // Timeout: mark game invalid
                    abortReason = `Timeout on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else if (errMsg.includes('Process error')) {
                    // Crash (non-zero exit): mark game invalid
                    abortReason = `Crash on turn ${turnCount} (${playerLabel}): ${errMsg}`;
                    console.error(`[Game] ABORT: ${abortReason}`);
                    break;
                } else {
                    // Malformed JSON, MCDSAI failure, or other: forfeit for this player
                    abortReason = `Forfeit by ${playerLabel} on turn ${turnCount}: ${errMsg}`;
                    console.error(`[Game] FORFEIT: ${abortReason}`);
                    // Set result to opponent wins
                    analyzer.gameState.result = activePlayer === 0 ? C.COLOR_BLACK : C.COLOR_WHITE;
                    break;
                }
            } else {
                errors.push(`Turn ${turnCount} (${playerLabel}): recovered after retry`);
            }
        }

        // Log click failures (non-fatal — applyClicks handles them)
        if (turnResult.clickResult && turnResult.clickResult.failed > 0) {
            const failMsg = `Turn ${turnCount} (${playerLabel}): ${turnResult.clickResult.failed} click(s) failed`;
            errors.push(failMsg);
            // Detailed click failures already logged by playSingleTurn/playMCDSAITurn
        }

        // Collect per-action state snapshots for replay
        if (turnResult.actionStates && turnResult.actionStates.length > 0) {
            for (const entry of turnResult.actionStates) {
                allActionStates.push(entry.state);
                allActionLabels.push(entry.action);
            }
        }

        // --- Check for game over ---
        if (analyzer.gameState.finished) {
            console.error(`[Game] Game over detected after turn ${turnCount}`);
            break;
        }

        // --- Check stagnation (AS3-style) ---
        if (analyzer.gameState.colorIsStagnated(C.COLOR_WHITE) ||
            analyzer.gameState.colorIsStagnated(C.COLOR_BLACK)) {
            const adj = adjudicateByMaterial(analyzer, 'Stagnation', turnCount);
            analyzer.gameState.result = adj.result;
            abortReason = adj.abortReason;
            console.error(`[Game] ${abortReason}`);
            break;
        }

        // --- Stuck detection: compare post-turn hash ---
        const postHash = getStateHash(analyzer);
        recentHashes.push(postHash);

        // Keep only the last stuckThreshold hashes
        if (recentHashes.length > stuckThreshold) {
            recentHashes.shift();
        }

        // Check if all recent hashes are identical (state unchanged)
        if (recentHashes.length >= stuckThreshold) {
            const allSame = recentHashes.every(h => h === recentHashes[0]);
            if (allSame) {
                const adj = adjudicateByMaterial(analyzer, 'Stuck', turnCount);
                analyzer.gameState.result = adj.result;
                abortReason = adj.abortReason;
                console.error(`[Game] ${abortReason}`);
                break;
            }
        }
    }

    // Max turns reached
    if (!analyzer.gameState.finished && !abortReason && turnCount >= maxTurns) {
        const adj = adjudicateByMaterial(analyzer, 'Max turns', turnCount);
        analyzer.gameState.result = adj.result;
        abortReason = adj.abortReason;
        console.error(`[Game] ${abortReason}`);
    }

    // Capture final state for replay
    try {
        allActionStates.push(stateToCppJSON(analyzer.gameState));
        allActionLabels.push('Game Over');
    } catch (e) { /* non-critical */ }

    // Final state
    const finalResult = analyzer.gameState.result;
    const winner = resultToString(finalResult);

    printStateSummary(analyzer, 'GAME END');

    console.error(`\n[Game] ========== RESULT ==========`);
    console.error(`[Game] Winner: ${winner}`);
    console.error(`[Game] Turns: ${turnCount}`);
    console.error(`[Game] Errors: ${errors.length}`);
    if (abortReason) console.error(`[Game] Abort reason: ${abortReason}`);
    if (errors.length > 0) {
        console.error(`[Game] Error log:`);
        for (const e of errors) console.error(`  - ${e}`);
    }
    console.error(`[Game] ================================\n`);

    // Clean up temp file
    try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

    return {
        result: finalResult,
        winner: winner,
        turns: turnCount,
        errors: errors,
        abortReason: abortReason,
        allActionStates: allActionStates,
        allActionLabels: allActionLabels,
        turnBoundaries: turnBoundaries
    };
}

// ---------------------------------------------------------------------------
// 9. Play multiple games with random card sets (Phase 7c)
// ---------------------------------------------------------------------------

/**
 * Play multiple games with random card sets.
 *
 * For each game:
 *   1. Generate a random card set (8 random units + base set)
 *   2. Build mergedDeck from card library
 *   3. Verify supply on the mergedDeck (assert per-game, not just first)
 *   4. Call playSingleGame() with the random card set
 *   5. Log per-game structured JSON
 *
 * ~5% of random card sets trigger AI exceptions (from selfplay_main.js experience).
 * On failure, retry with a different random set up to maxRetries times.
 *
 * @param {Object} config - Game config (playerWhite, playerBlack, thinkTimeMs, mcdsai)
 * @param {number} numGames - Number of games to play
 * @param {Map} library - Card library from loadCardLibrary()
 * @returns {Promise<{ games: Object[], tally: { white: number, black: number, draws: number, invalid: number }, avgTurns: number }>}
 */
async function playMultipleGames(config, numGames, library, options = {}) {
    const { playerSwitch = false, fixedCards = null, saveReplaysDir = null } = options;
    const maxRetries = 3;  // Retry with different set if AI fails (~5% of sets)

    // Resolve "R" slots in fixedCards with random picks from the advanced unit pool
    function resolveRandomSlots(cards) {
        if (!cards || !cards.some(n => n === 'R')) return cards;
        const pinned = new Set(cards.filter(n => n !== 'R'));
        const available = getAdvancedUnitNames(library).filter(n => !pinned.has(n));
        for (let i = available.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [available[i], available[j]] = [available[j], available[i]];
        }
        let ri = 0;
        return cards.map(name => {
            if (name === 'R') return available[ri++];
            return name;
        });
    }
    const games = [];
    let whiteWins = 0;
    let blackWins = 0;
    let draws = 0;
    let invalid = 0;
    let totalTurns = 0;
    let completedGames = 0;

    /**
     * Play a single game with retry logic. Returns a gameLog object.
     */
    async function playOneGame(gameNum, totalGames, unitNames, gameConfig, attemptOffset = 0) {
        let gameLog = null;
        let attempts = 0;

        while (attempts < maxRetries) {
            attempts++;
            const startTime = Date.now();

            // Generate card set (on retry: new random set unless fully-fixed; R slots re-resolve)
            let currentUnits = unitNames;
            if (attempts > 1 && !fixedCards) {
                currentUnits = randomSet(library, 8);
            } else if (attempts > 1 && fixedCards && fixedCards.some(n => n === 'R')) {
                currentUnits = resolveRandomSlots(fixedCards);
            }
            const label = playerSwitch ? '[Pair]' : '[Multi]';
            console.error(`\n${label} Game ${gameNum}/${totalGames} (attempt ${attempts}/${maxRetries})`);
            console.error(`${label} Card set: [${currentUnits.join(', ')}]`);

            const mergedDeck = buildMergedDeck(currentUnits, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);

            const supplyResult = verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error(`${label} Game ${gameNum}: Supply verification FAILED — logging and continuing`);
            }

            let gameResult;
            let gameError = null;
            try {
                gameResult = await playSingleGame(activeDeck, gameConfig);
            } catch (err) {
                gameError = err.message || String(err);
                console.error(`${label} Game ${gameNum}: Exception: ${gameError}`);
            }

            const endTime = Date.now();

            if (gameError) {
                if (attempts < maxRetries) {
                    console.error(`${label} Game ${gameNum}: Retrying...`);
                    continue;
                }
                gameLog = {
                    game: gameNum, cardSet: currentUnits, winner: 'invalid', result: null,
                    turns: 0, errors: [gameError],
                    abortReason: `Exception after ${attempts} attempts: ${gameError}`,
                    startTime: new Date(startTime).toISOString(),
                    endTime: new Date(endTime).toISOString(),
                    durationMs: endTime - startTime,
                    supplyVerified: supplyResult.ok, attempts: attempts
                };
                break;
            }

            if (gameResult.turns === 0 && attempts < maxRetries) {
                console.error(`${label} Game ${gameNum}: 0 turns — AI failure, retrying...`);
                continue;
            }

            gameLog = {
                game: gameNum, cardSet: currentUnits,
                winner: gameResult.winner, result: gameResult.result,
                turns: gameResult.turns, errors: gameResult.errors,
                abortReason: gameResult.abortReason,
                startTime: new Date(startTime).toISOString(),
                endTime: new Date(endTime).toISOString(),
                durationMs: endTime - startTime,
                supplyVerified: supplyResult.ok, attempts: attempts,
                allActionStates: gameResult.allActionStates || [],
                allActionLabels: gameResult.allActionLabels || [],
                turnBoundaries: gameResult.turnBoundaries || []
            };
            break;
        }

        if (!gameLog) {
            gameLog = {
                game: gameNum, cardSet: [], winner: 'invalid', result: null,
                turns: 0, errors: [`All ${maxRetries} attempts failed`],
                abortReason: `All ${maxRetries} attempts failed`,
                startTime: new Date().toISOString(), endTime: new Date().toISOString(),
                durationMs: 0, supplyVerified: false, attempts: maxRetries
            };
        }
        return gameLog;
    }

    function tallyGame(gameLog) {
        if (gameLog.winner === 'invalid' || gameLog.result === null) {
            invalid++;
        } else if (gameLog.result === C.COLOR_WHITE) {
            whiteWins++;
            totalTurns += gameLog.turns;
            completedGames++;
        } else if (gameLog.result === C.COLOR_BLACK) {
            blackWins++;
            totalTurns += gameLog.turns;
            completedGames++;
        } else {
            draws++;
            totalTurns += gameLog.turns;
            completedGames++;
        }
        const elapsed = (gameLog.durationMs / 1000).toFixed(1);
        const label = playerSwitch ? '[Pair]' : '[Multi]';
        console.error(`${label} Game ${gameLog.game} result: ${gameLog.winner} in ${gameLog.turns} turns (${elapsed}s)`);
    }

    function saveAndStripReplay(gameLog, pWhite, pBlack) {
        const hasStates = gameLog && gameLog.allActionStates && gameLog.allActionStates.length > 0;
        if (saveReplaysDir && hasStates) {
            try {
                fs.mkdirSync(saveReplaysDir, { recursive: true });
                const winnerInt = gameLog.result === C.COLOR_WHITE ? 0 :
                                  gameLog.result === C.COLOR_BLACK ? 1 : -1;
                const replayData = buildReplayJSON(
                    gameLog.allActionStates, pWhite, pBlack,
                    winnerInt, gameLog.turns, gameLog.cardSet,
                    gameLog.allActionLabels, gameLog.turnBoundaries
                );
                const replayPath = path.join(saveReplaysDir, `game_${String(gameLog.game).padStart(4, '0')}.json`);
                fs.writeFileSync(replayPath, JSON.stringify(replayData, null, 2));
                console.error(`[Replay] Saved ${replayPath}`);
            } catch (err) {
                console.error(`[Replay] Game ${gameLog.game}: Failed to save: ${err.message}`);
            }
        }
        // Strip heavy replay data from in-memory log
        delete gameLog.allActionStates;
        delete gameLog.allActionLabels;
        delete gameLog.turnBoundaries;
    }

    if (playerSwitch) {
        // --- Pair-mode: games in pairs, same card set, swapped sides ---
        const numPairs = numGames / 2;
        const pairResults = { aWins2: 0, bWins2: 0, splits: 0, invalidPairs: 0 };
        let playerAWins = 0;

        // Build swapped config (reverse player assignment and MCDSAI workers)
        const swappedConfig = {
            ...config,
            playerWhite: config.playerBlack,
            playerBlack: config.playerWhite,
            mcdsai: config.mcdsai ? {
                ...config.mcdsai,
                workerWhite: config.mcdsai.workerBlack,
                workerBlack: config.mcdsai.workerWhite
            } : null
        };

        for (let p = 0; p < numPairs; p++) {
            const gameNumA = p * 2 + 1;
            const gameNumB = p * 2 + 2;
            const unitNames = (fixedCards ? resolveRandomSlots(fixedCards) : null) || randomSet(library, 8);

            console.error(`\n[Pair] === Pair ${p + 1}/${numPairs} ===`);
            console.error(`[Pair] Card set: [${unitNames.join(', ')}]`);

            // Game A: original assignment
            const logA = await playOneGame(gameNumA, numGames, unitNames, config);
            logA.pairId = p + 1;
            logA.swapped = false;
            saveAndStripReplay(logA, config.playerWhite, config.playerBlack);
            games.push(logA);
            tallyGame(logA);

            // Game B: swapped assignment (same card set)
            const logB = await playOneGame(gameNumB, numGames, unitNames, swappedConfig);
            logB.pairId = p + 1;
            logB.swapped = true;
            saveAndStripReplay(logB, swappedConfig.playerWhite, swappedConfig.playerBlack);
            games.push(logB);
            tallyGame(logB);

            // Compute pair outcome from Player A's perspective
            // Game A: white win = Player A win. Game B: black win = Player A win.
            const aWinsInA = (logA.result === C.COLOR_WHITE) ? 1 : 0;
            const aWinsInB = (logB.result === C.COLOR_BLACK) ? 1 : 0;
            const aWinsThisPair = aWinsInA + aWinsInB;
            playerAWins += aWinsThisPair;

            if (logA.winner === 'invalid' || logB.winner === 'invalid') {
                pairResults.invalidPairs++;
            } else if (aWinsThisPair === 2) {
                pairResults.aWins2++;
            } else if (aWinsThisPair === 0) {
                pairResults.bWins2++;
            } else {
                pairResults.splits++;
            }

            console.error(`[Pair] Pair ${p + 1} outcome: A=${aWinsInA}, B(swapped)=${aWinsInB}`);
        }

        // Compute player win rates (seat-independent)
        // Use playerA/playerB keys to stay unambiguous even when both names are identical
        const validGames = numGames - invalid;
        const playerBWins = validGames - playerAWins - draws;
        const playerWinRates = {
            playerA: { name: config.playerWhite, wins: playerAWins, winRate: 0 },
            playerB: { name: config.playerBlack, wins: playerBWins, winRate: 0 }
        };
        if (validGames > 0) {
            playerWinRates.playerA.winRate = parseFloat((100 * playerAWins / validGames).toFixed(1));
            playerWinRates.playerB.winRate = parseFloat((100 * playerBWins / validGames).toFixed(1));
        }

        // Final tally
        const avgTurns = completedGames > 0 ? Math.round(totalTurns / completedGames) : 0;
        const tally = { white: whiteWins, black: blackWins, draws, invalid };

        console.error(`\n[Pair] ========== TALLY ==========`);
        console.error(`[Pair] Games:    ${numGames} (${numPairs} pairs)`);
        console.error(`[Pair] White:    ${whiteWins} (${numGames > 0 ? (100 * whiteWins / numGames).toFixed(1) : 0}%)`);
        console.error(`[Pair] Black:    ${blackWins} (${numGames > 0 ? (100 * blackWins / numGames).toFixed(1) : 0}%)`);
        console.error(`[Pair] Draws:    ${draws}`);
        console.error(`[Pair] Invalid:  ${invalid}`);
        console.error(`[Pair] Avg turns: ${avgTurns}`);
        const labelA = `Player A [${config.playerWhite}]`;
        const labelB = `Player B [${config.playerBlack}]`;
        console.error(`[Pair] --- Pair Results (A=initially White, B=initially Black) ---`);
        console.error(`[Pair] ${labelA} sweeps (2-0): ${pairResults.aWins2}`);
        console.error(`[Pair] ${labelB} sweeps (2-0): ${pairResults.bWins2}`);
        console.error(`[Pair] Splits (1-1):  ${pairResults.splits}`);
        console.error(`[Pair] Invalid pairs:  ${pairResults.invalidPairs}`);
        if (validGames > 0) {
            console.error(`[Pair] --- Win Rates (seat-independent) ---`);
            console.error(`[Pair] ${labelA}: ${playerWinRates.playerA.winRate}%`);
            console.error(`[Pair] ${labelB}: ${playerWinRates.playerB.winRate}%`);
        }
        console.error(`[Pair] ================================\n`);

        return { games, tally, avgTurns, pairResults, playerWinRates };
    }

    // --- Standard mode (no player-switch) ---
    for (let g = 0; g < numGames; g++) {
        const gameNum = g + 1;
        const unitNames = (fixedCards ? resolveRandomSlots(fixedCards) : null) || randomSet(library, 8);
        const gameLog = await playOneGame(gameNum, numGames, unitNames, config);
        saveAndStripReplay(gameLog, config.playerWhite, config.playerBlack);
        games.push(gameLog);
        tallyGame(gameLog);
    }

    // Final tally
    const avgTurns = completedGames > 0 ? Math.round(totalTurns / completedGames) : 0;
    const tally = { white: whiteWins, black: blackWins, draws, invalid };

    console.error(`\n[Multi] ========== TALLY ==========`);
    console.error(`[Multi] Games:   ${numGames}`);
    console.error(`[Multi] White:   ${whiteWins} (${numGames > 0 ? (100 * whiteWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Multi] Black:   ${blackWins} (${numGames > 0 ? (100 * blackWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Multi] Draws:   ${draws}`);
    console.error(`[Multi] Invalid: ${invalid}`);
    console.error(`[Multi] Avg turns: ${avgTurns}`);
    console.error(`[Multi] ================================\n`);

    return { games, tally, avgTurns };
}

// ---------------------------------------------------------------------------
// 10. Play multiple games in parallel with worker_threads (Phase 7e)
// ---------------------------------------------------------------------------

/**
 * Path to the worker thread script for parallel game execution.
 * @type {string}
 */
const WORKER_SCRIPT_PATH = path.join(__dirname, 'matchup_worker.js');

/**
 * Play multiple games in parallel using worker_threads.
 *
 * Distributes games round-robin across `numWorkers` worker threads.
 * Each worker thread loads its own card library, MCDSAI workers (if needed),
 * and uses slot-specific temp files (e.g., _suggest_state_W0.json) for
 * C++ --suggest calls to avoid file conflicts.
 *
 * Each worker runs its assigned games sequentially and posts results back
 * to the main thread via parentPort.postMessage().
 *
 * Constraints (from CLAUDE.md):
 *   - x86 OOM: max 4 concurrent C++ exe invocations
 *   - MCDSAI: ~100MB per Emscripten module, so each worker pair costs ~200MB
 *
 * @param {Object} config - Game config (playerWhite, playerBlack, thinkTimeMs)
 * @param {number} numGames - Total number of games to play
 * @param {Map} library - Card library (not passed to workers; they load their own)
 * @param {number} numWorkers - Number of parallel worker threads
 * @param {string} mcdsaiDifficulty - MCDSAI difficulty name
 * @param {string|null} saveReplaysDir - Directory for replay files (null = no saving)
 * @param {boolean} verbose - Verbose output
 * @returns {Promise<{ games: Object[], tally: { white: number, black: number, draws: number, invalid: number }, avgTurns: number }>}
 */
async function playMultipleGamesParallel(config, numGames, library, numWorkers, mcdsaiDifficulty, saveReplaysDir, verbose, options = {}) {
    const { playerSwitch = false, fixedCards = null } = options;

    // Distribute game numbers across worker slots
    const slotsGames = Array.from({ length: numWorkers }, () => []);
    if (playerSwitch) {
        // Distribute PAIRS round-robin — keep each pair on the same worker
        const numPairs = numGames / 2;
        for (let p = 0; p < numPairs; p++) {
            const w = p % numWorkers;
            slotsGames[w].push(p * 2 + 1, p * 2 + 2);  // Keep pair together
        }
    } else {
        for (let g = 0; g < numGames; g++) {
            slotsGames[g % numWorkers].push(g + 1);  // 1-based game numbers
        }
    }

    // Create replay directory if saving replays
    if (saveReplaysDir) {
        try {
            fs.mkdirSync(saveReplaysDir, { recursive: true });
            console.error(`[Parallel] Replay directory: ${saveReplaysDir}`);
        } catch (err) {
            console.error(`[Parallel] WARNING: Could not create replay dir: ${err.message}`);
        }
    }

    console.error(`[Parallel] Launching ${numWorkers} worker threads for ${numGames} games`);
    for (let i = 0; i < numWorkers; i++) {
        console.error(`[Parallel]   Worker ${i}: ${slotsGames[i].length} games (${slotsGames[i].join(', ')})`);
    }

    // Collect all game results (indexed by game number for ordering)
    const gameLogsByNum = new Map();
    let whiteWins = 0, blackWins = 0, draws = 0, invalid = 0;
    let totalTurns = 0, completedGames = 0;
    let gamesReported = 0;

    // Launch all workers and collect results
    const workerPromises = slotsGames.map((gameNums, slotIdx) => {
        // Skip empty slots (happens when numGames < numWorkers)
        if (gameNums.length === 0) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const worker = new Worker(WORKER_SCRIPT_PATH, {
                workerData: {
                    slotIndex: slotIdx,
                    gameNums: gameNums,
                    playerWhite: config.playerWhite,
                    playerBlack: config.playerBlack,
                    thinkTimeMs: config.thinkTimeMs,
                    mcdsaiDifficulty: mcdsaiDifficulty,
                    saveReplaysDir: saveReplaysDir,
                    verbose: verbose,
                    playerSwitch: playerSwitch,
                    fixedCards: fixedCards
                }
            });

            worker.on('message', (msg) => {
                if (msg.type === 'game_result') {
                    const log = msg.gameLog;
                    gameLogsByNum.set(msg.gameNum, log);

                    // Tally results immediately
                    if (log.winner === 'invalid' || log.result === null) {
                        invalid++;
                    } else if (log.result === C.COLOR_WHITE) {
                        whiteWins++;
                        totalTurns += log.turns;
                        completedGames++;
                    } else if (log.result === C.COLOR_BLACK) {
                        blackWins++;
                        totalTurns += log.turns;
                        completedGames++;
                    } else {
                        draws++;
                        totalTurns += log.turns;
                        completedGames++;
                    }

                    gamesReported++;
                    const elapsed = (log.durationMs / 1000).toFixed(1);
                    console.error(`[Parallel] Game ${msg.gameNum} (W${slotIdx}): ${log.winner} in ${log.turns} turns (${elapsed}s) [${gamesReported}/${numGames}]`);

                    // Progress summary every 10 games
                    if (numGames > 10 && gamesReported % 10 === 0) {
                        const pct = (100 * gamesReported / numGames).toFixed(0);
                        console.error(`[Parallel] Progress: ${gamesReported}/${numGames} (${pct}%) — W:${whiteWins} B:${blackWins} D:${draws} I:${invalid}`);
                    }
                } else if (msg.type === 'slot_done') {
                    console.error(`[Parallel] Worker ${msg.slotIndex} done (${msg.gamesCompleted} games)`);
                } else if (msg.type === 'error') {
                    console.error(`[Parallel] Worker ${msg.slotIndex} error: ${msg.message}`);
                }
            });

            worker.on('error', (err) => {
                console.error(`[Parallel] Worker ${slotIdx} thread error: ${err.message}`);
                reject(err);
            });

            worker.on('exit', (code) => {
                if (code !== 0) {
                    console.error(`[Parallel] Worker ${slotIdx} exited with code ${code}`);
                    // Don't reject — some games may have completed before the crash
                }
                resolve();
            });
        });
    });

    // Wait for all workers to finish
    await Promise.all(workerPromises);

    // Build ordered games array (sorted by game number)
    const games = [];
    for (let g = 1; g <= numGames; g++) {
        const log = gameLogsByNum.get(g);
        if (log) {
            games.push(log);
        } else {
            // Worker may have crashed before completing this game
            games.push({
                game: g,
                cardSet: [],
                winner: 'invalid',
                result: null,
                turns: 0,
                errors: ['Worker thread crashed before completing this game'],
                abortReason: 'Worker thread crash',
                startTime: new Date().toISOString(),
                endTime: new Date().toISOString(),
                durationMs: 0,
                supplyVerified: false,
                attempts: 0
            });
            invalid++;
        }
    }

    // Final tally
    const avgTurns = completedGames > 0 ? Math.round(totalTurns / completedGames) : 0;
    const tally = { white: whiteWins, black: blackWins, draws, invalid };

    console.error(`\n[Parallel] ========== TALLY ==========`);
    console.error(`[Parallel] Games:    ${numGames} (${numWorkers} workers)`);
    console.error(`[Parallel] White:    ${whiteWins} (${numGames > 0 ? (100 * whiteWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Parallel] Black:    ${blackWins} (${numGames > 0 ? (100 * blackWins / numGames).toFixed(1) : 0}%)`);
    console.error(`[Parallel] Draws:    ${draws}`);
    console.error(`[Parallel] Invalid:  ${invalid}`);
    console.error(`[Parallel] Avg turns: ${avgTurns}`);
    if (saveReplaysDir) console.error(`[Parallel] Replays:  ${saveReplaysDir}`);

    // Pair-level tallying (computed from game logs, not from worker messages)
    let pairResults = null;
    let playerWinRates = null;
    if (playerSwitch) {
        pairResults = { aWins2: 0, bWins2: 0, splits: 0, invalidPairs: 0 };
        let playerAWins = 0;
        const numPairs = numGames / 2;

        for (let p = 0; p < numPairs; p++) {
            const logA = games[p * 2];      // Game A: original assignment
            const logB = games[p * 2 + 1];  // Game B: swapped assignment

            // Game A: white win = Player A win. Game B: black win = Player A win.
            const aWinsInA = (logA && logA.result === C.COLOR_WHITE) ? 1 : 0;
            const aWinsInB = (logB && logB.result === C.COLOR_BLACK) ? 1 : 0;
            const aWinsThisPair = aWinsInA + aWinsInB;
            playerAWins += aWinsThisPair;

            if (!logA || !logB || logA.winner === 'invalid' || logB.winner === 'invalid') {
                pairResults.invalidPairs++;
            } else if (aWinsThisPair === 2) {
                pairResults.aWins2++;
            } else if (aWinsThisPair === 0) {
                pairResults.bWins2++;
            } else {
                pairResults.splits++;
            }
        }

        const validGames = numGames - invalid;
        const playerBWins = validGames - playerAWins - draws;
        playerWinRates = {
            playerA: { name: config.playerWhite, wins: playerAWins, winRate: 0 },
            playerB: { name: config.playerBlack, wins: playerBWins, winRate: 0 }
        };
        if (validGames > 0) {
            playerWinRates.playerA.winRate = parseFloat((100 * playerAWins / validGames).toFixed(1));
            playerWinRates.playerB.winRate = parseFloat((100 * playerBWins / validGames).toFixed(1));
        }

        const labelA = `Player A [${config.playerWhite}]`;
        const labelB = `Player B [${config.playerBlack}]`;
        console.error(`[Parallel] --- Pair Results (A=initially White, B=initially Black) ---`);
        console.error(`[Parallel] ${labelA} sweeps (2-0): ${pairResults.aWins2}`);
        console.error(`[Parallel] ${labelB} sweeps (2-0): ${pairResults.bWins2}`);
        console.error(`[Parallel] Splits (1-1):  ${pairResults.splits}`);
        console.error(`[Parallel] Invalid pairs:  ${pairResults.invalidPairs}`);
        if (validGames > 0) {
            console.error(`[Parallel] --- Win Rates (seat-independent) ---`);
            console.error(`[Parallel] ${labelA}: ${playerWinRates.playerA.winRate}%`);
            console.error(`[Parallel] ${labelB}: ${playerWinRates.playerB.winRate}%`);
        }
    }

    console.error(`[Parallel] ================================\n`);

    return { games, tally, avgTurns, pairResults, playerWinRates };
}

// ---------------------------------------------------------------------------
// 11. Main
// ---------------------------------------------------------------------------

async function main() {
    const args = process.argv.slice(2);

    // Parse CLI args
    let useRandom = false;
    let singleTurnMode = false;
    let numGames = 1;
    let playerWhite = CONFIG.defaultPlayer;
    let playerBlack = CONFIG.defaultPlayer;
    let thinkTimeMs = CONFIG.thinkTimeMs;
    let mcdsaiDifficulty = 'HardestAI';  // Default MCDSAI difficulty
    let parallelWorkers = 1;             // Phase 7e: 1 = sequential (default)
    let saveReplaysDir = null;           // Phase 7e: null = no replay saving
    let playerSwitch = false;            // --player-switch: run games in pairs with swapped sides
    let fixedCards = null;               // --cards "A,B,C": fixed advanced units (null = random)

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--random') useRandom = true;
        if (args[i] === '--single-turn') singleTurnMode = true;
        if (args[i] === '--games' && args[i + 1]) { numGames = parseInt(args[++i], 10); }
        if (args[i] === '--player' && args[i + 1]) {
            playerWhite = args[++i];
            playerBlack = playerWhite;  // same player for both sides unless overridden
        }
        if (args[i] === '--player-white' && args[i + 1]) { playerWhite = args[++i]; }
        if (args[i] === '--player-black' && args[i + 1]) { playerBlack = args[++i]; }
        if (args[i] === '--think-time' && args[i + 1]) { thinkTimeMs = parseInt(args[++i], 10); }
        if (args[i] === '--mcdsai-difficulty' && args[i + 1]) { mcdsaiDifficulty = args[++i]; }
        if (args[i] === '--parallel' && args[i + 1]) { parallelWorkers = parseInt(args[++i], 10); }
        if (args[i] === '--player-switch') playerSwitch = true;
        if (args[i] === '--cards' && args[i + 1]) {
            fixedCards = args[++i].split(',').map(s => s.trim()).filter(s => s.length > 0);
        }
        if (args[i] === '--save-replays') {
            // Flat folder under bin/asset/replays/ with timestamp prefix.
            // Format: YYYY-MM-DD_HH-MM-SS[_label]/
            // GUI loads replays from immediate subdirectories of replays/.
            const now = new Date();
            const ts = now.getFullYear()
                + '-' + String(now.getMonth() + 1).padStart(2, '0')
                + '-' + String(now.getDate()).padStart(2, '0')
                + '_' + String(now.getHours()).padStart(2, '0')
                + '-' + String(now.getMinutes()).padStart(2, '0')
                + '-' + String(now.getSeconds()).padStart(2, '0');
            const replaysRoot = path.join(__dirname, '..', 'bin', 'asset', 'replays');
            if (args[i + 1] && !args[i + 1].startsWith('--')) {
                const label = args[++i];
                // If label looks like a path (contains / or \), use it directly
                if (label.includes('/') || label.includes('\\') || path.isAbsolute(label)) {
                    saveReplaysDir = label;
                } else {
                    saveReplaysDir = path.join(replaysRoot, ts + '_' + label);
                }
            } else {
                // No label — timestamp only
                saveReplaysDir = path.join(replaysRoot, ts);
            }
        }
    }

    // Validate parallel workers count
    if (parallelWorkers < 1) parallelWorkers = 1;
    if (parallelWorkers > 8) {
        console.error(`WARNING: --parallel ${parallelWorkers} is very high (x86 OOM risk). Clamping to 4.`);
        parallelWorkers = 4;
    }

    // Validate --player-switch
    if (playerSwitch) {
        if (singleTurnMode) {
            console.error('WARNING: --player-switch ignored in single-turn mode');
            playerSwitch = false;
        } else if (numGames % 2 !== 0) {
            numGames++;
            console.error(`WARNING: --player-switch requires even game count. Rounded up to ${numGames}.`);
        }
    }

    // --cards implies not random (for single-game path)
    if (fixedCards) {
        useRandom = false;
    }

    // Detect MCDSAI players (case-insensitive matching)
    const whiteIsMCDSAI = isMCDSAIPlayer(playerWhite);
    const blackIsMCDSAI = isMCDSAIPlayer(playerBlack);
    const anyMCDSAI = whiteIsMCDSAI || blackIsMCDSAI;

    // Normalize MCDSAI player names to consistent casing
    if (whiteIsMCDSAI) playerWhite = MCDSAI_PLAYER;
    if (blackIsMCDSAI) playerBlack = MCDSAI_PLAYER;

    // Check exe exists (only needed for C++ players)
    const anyCpp = !whiteIsMCDSAI || !blackIsMCDSAI;
    if (anyCpp && !fs.existsSync(EXE_PATH)) {
        console.error(`ERROR: C++ exe not found at ${EXE_PATH}`);
        console.error('Build with: MSBuild Prismata.sln /t:Rebuild /p:Configuration=Release /p:Platform=x86');
        process.exit(1);
    }

    // Determine mode
    const isMultiGame = numGames > 1 && !singleTurnMode;
    const isParallel = isMultiGame && parallelWorkers > 1;
    const modeLabel = singleTurnMode ? 'Single-Turn Test (Phase 7a)'
                    : isParallel ? `Parallel Multi-Game (Phase 7e) — ${numGames} games, ${parallelWorkers} workers`
                    : isMultiGame ? `Multi-Game (Phase 7c/7d) — ${numGames} games`
                    : 'Single Game (Phase 7b/7d)';
    console.error(`=== ${modeLabel} ===`);
    if (anyCpp) console.error(`Exe: ${EXE_PATH}`);
    console.error(`White: ${playerWhite}${whiteIsMCDSAI ? ` (MCDSAI difficulty=${mcdsaiDifficulty})` : ''}`);
    console.error(`Black: ${playerBlack}${blackIsMCDSAI ? ` (MCDSAI difficulty=${mcdsaiDifficulty})` : ''}`);
    if (anyCpp) console.error(`Think time: ${thinkTimeMs}ms`);
    if (!singleTurnMode) {
        console.error(`Max turns: ${CONFIG.maxTurns}, Stuck detection: ${CONFIG.stuckDetectionTurns} turns`);
    }
    if (isParallel) console.error(`Parallel workers: ${parallelWorkers}`);
    if (playerSwitch) console.error(`Player switch: enabled (${numGames / 2} pairs)`);
    if (fixedCards) console.error(`Fixed cards: [${fixedCards.join(', ')}]`);
    if (saveReplaysDir) console.error(`Replay saving: ${saveReplaysDir}`);
    console.error('');

    // 1. Load card library
    const library = loadCardLibrary();
    console.error(`Loaded card library: ${library.size} entries`);

    // Validate --cards names against library (must be advanced/non-base units, or "R" for random)
    const hasRandomSlots = fixedCards && fixedCards.some(name => name === 'R');
    if (fixedCards) {
        if (fixedCards.length > 11) {
            console.error(`ERROR: --cards has ${fixedCards.length} units (max 11 advanced units per game).`);
            process.exit(1);
        }
        const advancedNames = new Set(getAdvancedUnitNames(library));
        for (const name of fixedCards) {
            if (name === 'R') continue;  // Random slot — resolved per game
            if (!advancedNames.has(name)) {
                // Check if it's a base set name for a better error message
                let isBase = false;
                for (const [, card] of library) {
                    if (card.UIName === name && card.baseSet) { isBase = true; break; }
                }
                if (isBase) {
                    console.error(`ERROR: "${name}" is a base set unit — --cards should only list advanced units.`);
                } else {
                    console.error(`ERROR: Unknown card name "${name}". Use display names (e.g., Tarsier, not Tesla Tower).`);
                }
                process.exit(1);
            }
        }
        if (hasRandomSlots) {
            const numRandom = fixedCards.filter(n => n === 'R').length;
            const numFixed = fixedCards.length - numRandom;
            console.error(`Cards template: ${numFixed} fixed + ${numRandom} random slots`);
        }
    }

    // Resolve "R" slots in fixedCards with random picks from the advanced unit pool
    function resolveRandomSlots(cards) {
        if (!cards || !cards.some(n => n === 'R')) return cards;
        const pinned = new Set(cards.filter(n => n !== 'R'));
        const available = getAdvancedUnitNames(library).filter(n => !pinned.has(n));
        // Shuffle available pool
        for (let i = available.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [available[i], available[j]] = [available[j], available[i]];
        }
        let ri = 0;
        return cards.map(name => {
            if (name === 'R') return available[ri++];
            return name;
        });
    }

    // 2. Load MCDSAI dependencies (only when needed, and NOT in parallel mode
    //    where each worker_thread spawns its own MCDSAI workers)
    let fullParams = null;
    let shortParams = null;
    let mcdsaiWorkerWhite = null;
    let mcdsaiWorkerBlack = null;

    if (anyMCDSAI && !isParallel) {
        const MCDSAIWorker = require('./mcdsai_manager');
        const aiParams = require('./ai_params');
        fullParams = aiParams.loadFullParams();
        shortParams = aiParams.loadShortParams();

        // Spawn MCDSAI workers (main thread — for sequential mode only)
        if (whiteIsMCDSAI) {
            mcdsaiWorkerWhite = new MCDSAIWorker('White');
            console.error('Spawning MCDSAI worker for White...');
            await mcdsaiWorkerWhite.spawn();
            console.error('MCDSAI worker for White ready.');
        }
        if (blackIsMCDSAI) {
            mcdsaiWorkerBlack = new MCDSAIWorker('Black');
            console.error('Spawning MCDSAI worker for Black...');
            await mcdsaiWorkerBlack.spawn();
            console.error('MCDSAI worker for Black ready.');
        }
    } else if (anyMCDSAI && isParallel) {
        console.error('MCDSAI workers will be spawned in each worker thread (parallel mode).');
    }

    // Build MCDSAI config object (passed through to playSingleGame)
    const mcdsaiConfig = anyMCDSAI ? {
        workerWhite: mcdsaiWorkerWhite,
        workerBlack: mcdsaiWorkerBlack,
        difficulty: mcdsaiDifficulty,
        fullParams: fullParams,
        shortParams: shortParams,
        library: library
    } : null;

    // Helper to clean up MCDSAI workers on exit
    function terminateWorkers() {
        if (mcdsaiWorkerWhite) {
            console.error('Terminating MCDSAI worker for White...');
            mcdsaiWorkerWhite.terminate();
        }
        if (mcdsaiWorkerBlack) {
            console.error('Terminating MCDSAI worker for Black...');
            mcdsaiWorkerBlack.terminate();
        }
    }

    try {
        // -------------------------------------------------------------------
        // Single-turn mode (Phase 7a compatibility)
        // -------------------------------------------------------------------
        if (singleTurnMode) {
            // Pick card set
            let unitNames;
            if (useRandom) {
                unitNames = randomSet(library, 8);
                console.error(`Random set: [${unitNames.join(', ')}]`);
            } else {
                unitNames = [];
                console.error('Using base-set-only (no random units) for reproducibility');
            }

            const mergedDeck = buildMergedDeck(unitNames, library);
            const activeDeck = mergedDeck.filter(c => !c._inactive);
            console.error(`MergedDeck: ${mergedDeck.length} total, ${activeDeck.length} active`);

            console.error('\n--- Supply Verification ---');
            const supplyResult = verifySupply(activeDeck);
            if (!supplyResult.ok) {
                console.error('WARNING: Supply verification found mismatches (proceeding anyway)');
            }

            console.error('\n--- Game Initialization ---');
            const gameInitInfo = buildGameInitInfo(activeDeck);
            const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
            analyzer.loaderInit();
            console.error('Game initialized successfully.');

            printStateSummary(analyzer, 'INITIAL STATE');

            console.error('\n--- Playing Single Turn ---');
            let turnResult;
            if (whiteIsMCDSAI && mcdsaiConfig) {
                // Initialize MCDSAI for this game
                const aiParams = require('./ai_params');
                const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);
                const initParams = JSON.parse(aiParams.selectParams(mcdsaiDifficulty, 1, fullParams, shortParams));
                const initJson = JSON.stringify({ mergedDeck: initDeck, aiParameters: initParams });
                await mcdsaiWorkerWhite.initializeAI(initJson);

                turnResult = await playMCDSAITurn(
                    analyzer, activeDeck, mcdsaiWorkerWhite,
                    mcdsaiDifficulty
                );
            } else {
                turnResult = playSingleTurn(analyzer, activeDeck, playerWhite, thinkTimeMs);
            }

            printStateSummary(analyzer, 'AFTER TURN');

            // Verify results
            console.error('\n--- Verification ---');
            const postState = JSON.parse(analyzer.gameState.toString());
            let verifyOk = true;

            if (turnResult.ok && turnResult.clickResult) {
                if (turnResult.clickResult.applied === 0) {
                    console.error('WARNING: No clicks were applied');
                    verifyOk = false;
                } else {
                    console.error(`OK: ${turnResult.clickResult.applied} clicks applied`);
                }
                if (turnResult.clickResult.failed > 0) {
                    console.error(`WARNING: ${turnResult.clickResult.failed} clicks failed`);
                    verifyOk = false;
                }
            }

            if (turnResult.ok) {
                if (postState.numTurns > 1 || postState.turn !== 0) {
                    console.error('OK: Turn advanced (numTurns or active player changed)');
                } else {
                    console.error('NOTE: Turn did not advance (may still be in action phase if clicks failed)');
                }
            }

            console.error('\n=== RESULT ===');
            if (turnResult.ok && verifyOk) {
                console.error('PASS: Single-turn matchup test completed successfully.');
            } else if (turnResult.ok) {
                console.error('PARTIAL: Turn succeeded but some clicks failed.');
            } else {
                console.error('FAIL: Turn failed.');
            }

            try { fs.unlinkSync(SUGGEST_TMP); } catch (e) { /* ignore */ }

            // Output JSON (compatible with C++ suggest output format where applicable)
            const output = {
                mode: 'single-turn',
                ok: turnResult.ok,
                playerType: whiteIsMCDSAI ? 'MCDSAI' : 'cpp-suggest',
                clicksApplied: turnResult.clickResult ? turnResult.clickResult.applied : 0,
                clicksFailed: turnResult.clickResult ? turnResult.clickResult.failed : 0
            };
            // Include suggest response for C++ players (MCDSAI doesn't produce it)
            if (turnResult.suggest && turnResult.suggest.response) {
                output.suggest = turnResult.suggest.response;
            }
            console.log(JSON.stringify(output, null, 2));
            return;
        }

        // -------------------------------------------------------------------
        // Multi-game mode — parallel (Phase 7e) or sequential (Phase 7c/7d)
        // -------------------------------------------------------------------
        if (isMultiGame) {
            let multiResult;

            if (isParallel) {
                // Phase 7e: Parallel execution via worker_threads
                // Workers load their own card libraries and MCDSAI workers.
                // No main-thread MCDSAI workers are spawned in parallel mode.
                console.error(`\n--- Starting ${numGames} Games in Parallel (${parallelWorkers} workers)${playerSwitch ? ` [${numGames / 2} pairs, player-switch]` : ''} ---`);
                multiResult = await playMultipleGamesParallel(
                    { playerWhite, playerBlack, thinkTimeMs },
                    numGames,
                    library,
                    parallelWorkers,
                    mcdsaiDifficulty,
                    saveReplaysDir,
                    false,  // verbose
                    { playerSwitch, fixedCards }
                );
            } else {
                // Phase 7c/7d: Sequential execution
                console.error(`\n--- Starting ${numGames} Games${playerSwitch ? ` [${numGames / 2} pairs, player-switch]` : ''} ---`);
                multiResult = await playMultipleGames(
                    { playerWhite, playerBlack, thinkTimeMs, mcdsai: mcdsaiConfig },
                    numGames,
                    library,
                    { playerSwitch, fixedCards, saveReplaysDir }
                );
            }

            // Output structured results as JSON to stdout
            const output = {
                mode: isParallel ? 'parallel-multi-game' : 'multi-game',
                numGames: numGames,
                tally: multiResult.tally,
                avgTurns: multiResult.avgTurns,
                players: { white: playerWhite, black: playerBlack },
                thinkTimeMs: thinkTimeMs,
                parallelWorkers: isParallel ? parallelWorkers : undefined,
                mcdsaiDifficulty: anyMCDSAI ? mcdsaiDifficulty : undefined,
                playerSwitch: playerSwitch || undefined,
                fixedCards: fixedCards || undefined,
                pairResults: multiResult.pairResults || undefined,
                playerWinRates: multiResult.playerWinRates || undefined,
                saveReplaysDir: saveReplaysDir || undefined,
                games: multiResult.games
            };
            console.log(JSON.stringify(output, null, 2));
            return;
        }

        // -------------------------------------------------------------------
        // Single-game mode (Phase 7b/7d — default, --games 1 or no --games)
        // -------------------------------------------------------------------

        // Pick card set
        let unitNames;
        if (fixedCards) {
            unitNames = resolveRandomSlots(fixedCards);
            console.error(`Fixed card set: [${unitNames.join(', ')}]`);
        } else if (useRandom) {
            unitNames = randomSet(library, 8);
            console.error(`Random set: [${unitNames.join(', ')}]`);
        } else {
            unitNames = [];
            console.error('Using base-set-only (no random units) for reproducibility');
        }

        const mergedDeck = buildMergedDeck(unitNames, library);
        const activeDeck = mergedDeck.filter(c => !c._inactive);
        console.error(`MergedDeck: ${mergedDeck.length} total, ${activeDeck.length} active`);

        console.error('\n--- Supply Verification ---');
        const supplyResult = verifySupply(activeDeck);
        if (!supplyResult.ok) {
            console.error('WARNING: Supply verification found mismatches (proceeding anyway)');
        }

        console.error('\n--- Starting Single Game ---');
        const gameResult = await playSingleGame(activeDeck, {
            playerWhite: playerWhite,
            playerBlack: playerBlack,
            thinkTimeMs: thinkTimeMs,
            mcdsai: mcdsaiConfig
        });

        // Output result as JSON to stdout
        const output = {
            mode: 'single-game',
            result: gameResult.result,
            winner: gameResult.winner,
            turns: gameResult.turns,
            errors: gameResult.errors,
            abortReason: gameResult.abortReason,
            players: { white: playerWhite, black: playerBlack },
            thinkTimeMs: thinkTimeMs,
            mcdsaiDifficulty: anyMCDSAI ? mcdsaiDifficulty : undefined,
            cardSet: activeDeck.filter(c => !c.baseSet && !c._needsOnly).map(c => c.UIName || c.name)
        };
        console.log(JSON.stringify(output, null, 2));

    } finally {
        // Always clean up MCDSAI workers
        terminateWorkers();
    }
}

// ---------------------------------------------------------------------------
// Module exports (for use by multi-game matchup runner)
// ---------------------------------------------------------------------------

module.exports = {
    verifySupply,
    exportStateForSuggest,
    callSuggest,
    applyClicks,
    describeClick,
    playSingleTurn,
    playMCDSAITurn,
    isMCDSAIPlayer,
    buildGameInitInfo,
    printStateSummary,
    playSingleGame,
    playMultipleGames,
    playMultipleGamesParallel,
    getStateHash,
    resultToString,
    computeWillScoreSum,
    adjudicateByMaterial,
    WILL_SCORE_THRESHOLD,
    MCDSAI_PLAYER
};

if (require.main === module) {
    main().catch(err => {
        console.error('Fatal:', err.message);
        process.exit(1);
    });
}
