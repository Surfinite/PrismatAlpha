'use strict';

/**
 * replay_exporter.js — Convert JS engine State objects to C++ GameState JSON format.
 *
 * Produces replay files loadable by GUIState_Menu::loadReplay() in the C++ GUI.
 * Each replay contains pre-computed GameState snapshots (one per turn) that the
 * GUI steps through via Right/Left arrow keys.
 *
 * C++ format reference: GameState::initFromJSON() in GameState.cpp,
 *                       Card::Card(rapidjson::Value) in Card.cpp.
 *
 * Field mapping:
 *   JS state.whiteMana.toString()  → C++ "whiteMana" (resource string)
 *   JS state.blackMana.toString()  → C++ "blackMana"
 *   JS state.turn                  → C++ "turn" (active player: 0=white, 1=black)
 *   JS state.numTurns              → C++ "numTurns"
 *   JS state.phase                 → C++ "phase" ("action", "defense", "confirm")
 *   JS inst.card.UIName            → C++ "cardName" (display name)
 *   JS inst.owner                  → C++ "owner" (0 or 1)
 *   JS inst.health                 → C++ "health"
 *   JS inst.role                   → C++ "role" ("default"/"assigned"/"inert"/"sellable")
 *   JS inst.deadness               → C++ "deadness" ("alive"/"dead"/...)
 *   JS inst.constructionTime       → C++ "constructionTime"
 *   JS inst.charge                 → C++ "charge"
 *   JS inst.delay                  → C++ "delay"
 *   JS inst.lifespan               → C++ "lifespan" (-1 = infinite)
 *   JS inst.disruptDamage          → C++ "disruptDamage"
 *   JS inst.blocking               → C++ "blocking"
 */

const C = require('./C');

/**
 * Convert a single Inst to C++ Card JSON format.
 *
 * @param {Inst} inst - Card instance from state.table
 * @returns {Object} Card JSON compatible with Card::Card(rapidjson::Value)
 */
function instToCardJSON(inst) {
    return {
        cardName:         inst.card.UIName,
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
    };
}

/**
 * Convert a JS engine State to C++ GameState JSON format.
 *
 * @param {State} state - JS engine State object
 * @returns {Object} GameState JSON compatible with GameState::initFromJSON()
 */
function stateToCppJSON(state) {
    // Resource strings — Mana.toString() produces the same format as C++ Resources::getString()
    // (digits for gold, H/B/C/G/A characters — parser is order-independent)
    const whiteMana = state.whiteMana.toString();
    const blackMana = state.blackMana.toString();

    // Build cards array and supply arrays — only include cards with nonzero supply or purchases
    const cards = [];
    const whiteTotalSupply = [];
    const blackTotalSupply = [];
    const whiteSupplySpent = [];
    const blackSupplySpent = [];

    const numCards = state.cards.length;
    for (let i = 0; i < numCards; i++) {
        const ws = state.whiteSupply[i] || 0;
        const bs = state.blackSupply[i] || 0;
        const wb = state.whiteBought[i] || 0;
        const bb = state.blackBought[i] || 0;

        // Include card if it was ever buyable (has supply or was purchased)
        if (ws > 0 || bs > 0 || wb > 0 || bb > 0) {
            cards.push(state.cards[i].UIName);
            whiteTotalSupply.push(ws); // whiteSupply is the initial total (constant)
            blackTotalSupply.push(bs);
            whiteSupplySpent.push(wb);
            blackSupplySpent.push(bb);
        }
    }

    // Build table array — only alive cards
    const table = [];
    state.table.forEach(function(inst) {
        if (inst.deadness === C.DEADNESS_ALIVE) {
            table.push(instToCardJSON(inst));
        }
    });

    return {
        whiteMana:        whiteMana,
        blackMana:        blackMana,
        turn:             state.turn,
        numTurns:         state.numTurns,
        phase:            state.phase,
        cards:            cards,
        whiteTotalSupply: whiteTotalSupply,
        blackTotalSupply: blackTotalSupply,
        whiteSupplySpent: whiteSupplySpent,
        blackSupplySpent: blackSupplySpent,
        table:            table
    };
}

/**
 * Build a complete replay JSON object for the C++ GUI.
 *
 * The replay format is loaded by GUIState_Menu::loadReplay() which expects:
 *   { "states": [...], "p0": "name", "p1": "name", "winner": int }
 *
 * @param {Object[]} gameStateJSONs - Array of C++ GameState JSON objects (from stateToCppJSON)
 * @param {string} p0 - Player 0 (white) name
 * @param {string} p1 - Player 1 (black) name
 * @param {number} winner - 0 for white, 1 for black, -1 for draw/ongoing
 * @param {number} turns - Number of turns played
 * @param {string[]} cardSet - Display names of the random units in this game
 * @param {string[]} [actions] - Per-state action labels (parallel to gameStateJSONs). Omitted from JSON if undefined.
 * @param {number[]} [turnBoundaries] - Indices into gameStateJSONs where each turn starts. Omitted from JSON if undefined.
 * @returns {Object} Complete replay JSON
 */
function buildReplayJSON(gameStateJSONs, p0, p1, winner, turns, cardSet, actions, turnBoundaries) {
    const winnerName = winner === 0 ? p0 : winner === 1 ? p1 : 'Draw';

    return {
        replay:         true,
        p0:             p0,
        p1:             p1,
        winner:         winner,
        winnerName:     winnerName,
        turns:          turns,
        cardSet:        cardSet,
        states:         gameStateJSONs,
        actions:        actions || undefined,
        turnBoundaries: turnBoundaries || undefined
    };
}

module.exports = {
    stateToCppJSON,
    buildReplayJSON,
    instToCardJSON
};
