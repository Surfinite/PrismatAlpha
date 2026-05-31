'use strict';

/**
 * training_example.js — Shared V2 training-example extractor (single source of truth).
 *
 * Produces the DeepSets V2 per-turn training record from a live JS-engine State
 * (a turn-start snapshot). Used by BOTH:
 *   - matchup_clean.js          (MB self-play / matchup corpus)
 *   - extract_training_jsengine.js (human replay corpus)
 * so the two corpora are produced by IDENTICAL feature code — no convert step, no drift.
 *
 * The record is the per-STATE core. Callers stamp game-level metadata afterwards:
 *   outcome_p0, total_plies, replay_code, rating_p0, rating_p1, game_date.
 *
 * Feature helpers come from state_adapter.js (_instToRichUnit, _manaToResources), the
 * same ones the MB path has always used.
 */

const C = require('./C');
const { _instToRichUnit: instToRichUnit, _manaToResources: manaToResources } = require('./state_adapter');

/**
 * Build the V2 per-turn training record.
 *
 * @param {State}    gameState - live State (analyzer.gameState, or beginTurnHistory[i])
 * @param {string[]} cardSet   - display names of the advanced (non-base) units in the deck
 * @param {number}   plyIndex  - 0-based ply index within the game
 * @returns {Object} V2 record core (without outcome_p0/total_plies/replay_code/ratings/game_date)
 */
function extractTrainingExampleV2(gameState, cardSet, plyIndex) {
    const instances = [];

    gameState.table.forEach((inst) => {
        if (inst.deadness !== C.DEADNESS_ALIVE) return;  // match state_adapter.js pattern
        instances.push(instToRichUnit(inst));
    });

    const p0Mana = gameState.playerMana(C.COLOR_WHITE);
    const p1Mana = gameState.playerMana(C.COLOR_BLACK);

    // Supply — include ALL units in card set, even sold-out (supply=0).
    // in_card_set flag must persist so model knows the unit was available.
    const supply = {};
    for (let i = 0; i < gameState.cards.length; i++) {
        const card = gameState.cards[i];
        const ws = gameState.whiteSupply[i] || 0;
        const bs = gameState.blackSupply[i] || 0;
        const inSet = cardSet.includes(card.UIName) ? 1 : 0;
        // Include if unit has supply OR is in the card set (even if sold out)
        if (ws > 0 || bs > 0 || inSet) {
            supply[card.UIName] = [ws, bs, inSet];
        }
    }

    return {
        schema_version: "v2",
        ply_index: plyIndex,
        card_set: cardSet,
        instances: instances,   // per-instance list (includes owner field)
        supply: supply,
        p0_resources: manaToResources(p0Mana),
        p1_resources: manaToResources(p1Mana),
        p0_attack: p0Mana.pool[C.MANA_A],
        p1_attack: p1Mana.pool[C.MANA_A],
        turn_number: gameState.numTurns,
        active_player: gameState.turn
    };
}

module.exports = { extractTrainingExampleV2 };
