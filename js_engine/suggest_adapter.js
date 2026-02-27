'use strict';

/**
 * suggest_adapter.js — Adapter between JS engine State and C++ --suggest mode.
 *
 * Two functions:
 *   stateToSuggestJSON(state, mergedDeck) — Convert JS State + mergedDeck to F6-format
 *       JSON compatible with C++ Prismata_Testing --suggest.
 *   suggestClicksToClicks(suggestClicks) — Convert C++ --suggest click output to JS
 *       engine Click objects.
 *
 * The F6 format wraps the game state in a CurrentInfo envelope with mergedDeck,
 * matching the clipboard JSON produced by Prismata's F6 key. The C++ --suggest
 * mode reads this format (see Card.cpp: m_clientInstId, GameState::initFromJSON).
 */

const C = require('./C');
const Click = require('./Click');
const { stateToCppJSON } = require('./replay_exporter');

/**
 * Convert a JS engine State + mergedDeck into F6-format JSON for C++ --suggest.
 *
 * Uses stateToCppJSON() for the base game state, then adds instId to each table
 * entry (critical — without instId, C++ returns _id=-1 in click output) and wraps
 * in the CurrentInfo envelope with mergedDeck.
 *
 * @param {State} state - JS engine State object
 * @param {Object[]} mergedDeck - Array of card definition objects for this game
 * @returns {Object} F6-format JSON: { CurrentInfo: { mergedDeck, gameState } }
 */
function stateToSuggestJSON(state, mergedDeck) {
    // Get the base C++ game state JSON (whiteMana, blackMana, cards, supply, table)
    const gameState = stateToCppJSON(state);

    // Rebuild the table with instId added to each entry.
    // stateToCppJSON filters for alive units but does NOT include instId.
    // We iterate state.table in parallel to get the instId from each Inst.
    const tableWithInstId = [];
    state.table.forEach(function(inst) {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            tableWithInstId.push({
                cardName:         inst.card.UIName,
                instId:           inst.instId,
                owner:            inst.owner,
                health:           inst.health,
                role:             inst.role,
                deadness:         inst.deadness,
                constructionTime: inst.constructionTime,
                charge:           inst.charge,
                delay:            inst.delay,
                lifespan:         inst.lifespan,
                disruptDamage:    inst.disruptDamage,
                blocking:         inst.blocking
            });
        }
    });

    // Replace the table with the instId-augmented version
    gameState.table = tableWithInstId;

    // Wrap in CurrentInfo envelope matching F6 clipboard format
    return {
        CurrentInfo: {
            mergedDeck: mergedDeck,
            gameState:  gameState
        }
    };
}

/**
 * Convert C++ --suggest click output to JS engine Click objects.
 *
 * C++ --suggest returns clicks as: [{ _type: "card clicked", _id: 0 }, ...]
 * This filters out "end swipe processed" entries (GUI animation artifacts) and
 * creates Click objects for the remaining actions.
 *
 * The _type strings from C++ match JS engine constants directly:
 *   "card clicked"       → C.CLICK_CARD
 *   "card shift clicked" → C.CLICK_CARD_SHIFT
 *   "inst clicked"       → C.CLICK_INST
 *   "inst shift clicked" → C.CLICK_INST_SHIFT
 *   "space clicked"      → C.CLICK_SPACE
 *
 * @param {Object[]} suggestClicks - Array of { _type, _id } from C++ --suggest output
 * @returns {Click[]} Array of JS engine Click objects
 */
function suggestClicksToClicks(suggestClicks) {
    const clicks = [];
    for (let i = 0; i < suggestClicks.length; i++) {
        const c = suggestClicks[i];
        // Filter out GUI animation artifacts — not game actions
        if (c._type === C.CLICK_END_SWIPE || c._type === C.CLICK_CANCEL_TARGET) {
            continue;
        }
        clicks.push(new Click(c._type, c._id));
    }
    return clicks;
}

module.exports = { stateToSuggestJSON, suggestClicksToClicks };
