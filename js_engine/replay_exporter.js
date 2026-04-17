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
 *   JS inst.instId                 → "instId" (unique instance identifier)
 *   JS inst.damage                 → "damage" (for absorb/damage counter rendering)
 *   JS inst.creatorIdFromBuyOrAbility >= 0 → "boughtThisPhase" (big gap pile spacing)
 *   JS inst.card.defaultBlocking   → "defaultBlocking"
 *   JS inst.card.fragile           → "isFragile"
 *   JS inst.card.cardType          → "cardType" ('unit' default)
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
        instId:           inst.instId,
        cardName:         inst.card.UIName,
        owner:            inst.owner,
        health:           inst.health,
        damage:           inst.damage,
        role:             inst.role,
        deadness:         inst.deadness,
        constructionTime: inst.constructionTime,
        charge:           inst.charge,
        delay:            inst.delay,
        lifespan:         inst.lifespan,
        disruptDamage:    inst.disruptDamage,
        blocking:         inst.blocking,
        boughtThisPhase:  inst.creatorIdFromBuyOrAbility >= 0,
        defaultBlocking:  inst.card.defaultBlocking || false,
        isFragile:        inst.card.fragile || false,
        cardType:         inst.card.cardType || 'unit',
        autoClicked:      inst.card.autoClicked || false
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

    // Build table array — include all cards (dead units rendered with skull until swoosh)
    const table = [];
    state.table.forEach(function(inst) {
        table.push(instToCardJSON(inst));
    });

    // Gold estimate for next turn — faithful port of StateHelper.update() econ logic.
    // Computes [lowerBound, upperBound] for each player.
    // This runs from the OPPONENT's perspective of "next turn" — for the active player
    // (state.turn), we compute what they'll have when their next turn starts.
    function computeEconEstimate(player) {
        const C = require('./C');
        let econPotential = 0, econPotentialLower = 0;
        const goldAnnihilate = {};     // goldResonate name → [insts]
        const goldAnnihilateNext = {}; // for units finishing construction
        let numDrones = 0;
        const saviorResoName = 'Drone';
        const isDefensePhase = state.phase === C.PHASE_DEFENSE && state.turn === player;

        state.table.forEach(function(inst) {
            if (inst.owner !== player) return;
            const card = inst.card;

            if (isDefensePhase) {
                // Defense phase: compute for THIS turn (what we'll produce after defending)
                if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                    if (card.goldResonate != null) {
                        if (goldAnnihilate[card.goldResonate])
                            goldAnnihilate[card.goldResonate].push(inst);
                        else
                            goldAnnihilate[card.goldResonate] = [inst];
                    }
                    if (card.cardName === saviorResoName) numDrones++;

                    if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                        const money = card.beginOwnTurnScript.receive.money || 0;
                        econPotential += money;
                        econPotentialLower += money;
                    }
                    if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                        inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0)) {
                        if (card.abilityScript && card.abilityScript.receive) {
                            const money = card.abilityScript.receive.money || 0;
                            econPotential += money;
                            if (card.abilityCost && card.abilityCost.isEmpty &&
                                (!card.abilitySac || card.abilitySac.length === 0) &&
                                !(card.abilityScript && card.abilityScript.selfsac)) {
                                econPotentialLower += money;
                            }
                        }
                    }
                }
            } else {
                // Action/confirm phase: compute for NEXT turn
                if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                    if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                        const money = card.beginOwnTurnScript.receive.money || 0;
                        econPotential += money;
                        econPotentialLower += money;
                    }
                    if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                        inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0) &&
                        card.abilityScript && card.abilityScript.receive) {
                        const money = card.abilityScript.receive.money || 0;
                        econPotential += money;
                        if (card.abilityCost && card.abilityCost.isEmpty &&
                            (!card.abilitySac || card.abilitySac.length === 0) &&
                            !(card.abilityScript && card.abilityScript.selfsac)) {
                            econPotentialLower += money;
                        }
                    }
                    // goldResonate for units finishing construction (will be ready next turn)
                    if (card.goldResonate != null && (inst.constructionTime === 1 || inst.delay === 1)) {
                        if (goldAnnihilateNext[card.goldResonate])
                            goldAnnihilateNext[card.goldResonate].push(inst);
                        else
                            goldAnnihilateNext[card.goldResonate] = [inst];
                    }
                    if (card.cardName === saviorResoName) numDrones++;
                }
            }
        });

        // goldResonate bonus: each goldResonate source multiplies by numDrones
        if (numDrones > 0) {
            if (isDefensePhase) {
                if (goldAnnihilate[saviorResoName]) {
                    const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
            } else {
                if (goldAnnihilate[saviorResoName]) {
                    const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
                if (goldAnnihilateNext[saviorResoName]) {
                    const bonus = goldAnnihilateNext[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
            }
        }

        // SWF: UIPlayerManaBar adds current gold to the estimate
        // turnMana.money for active player, oppMana.money for opponent
        const currentGold = (player === 0 ? state.whiteMana : state.blackMana).money || 0;
        return [econPotentialLower + currentGold, econPotential + currentGold];
    }

    return {
        whiteMana:        whiteMana,
        blackMana:        blackMana,
        turn:             state.turn,
        numTurns:         state.numTurns,
        phase:            state.phase,
        glassBroken:      state.glassBroken || false,
        incomingAttack:   state.oppMana ? state.oppMana.attack : 0,
        // --- StateHelper-derived fields consumed by the viewer's midline ---
        // Turn player's potential next-attack / chill (shown bracketed during their defense phase)
        maxAttack:            state.helper ? state.helper.maxAttack : 0,
        maxDisrupt:           state.helper ? state.helper.maxDisrupt : 0,
        maxSnipers:           state.helper ? state.helper.maxSnipers : 0,
        // Opponent's predicted next-turn output (shown bracketed outside defense)
        oppAttackPotential:   state.helper ? state.helper.oppAttackPotential : 0,
        oppDisruptPotential:  state.helper ? state.helper.oppDisruptPotential : 0,
        oppSnipers:           state.helper ? state.helper.oppSnipers : 0,
        cards:            cards,
        whiteTotalSupply: whiteTotalSupply,
        blackTotalSupply: blackTotalSupply,
        whiteSupplySpent: whiteSupplySpent,
        blackSupplySpent: blackSupplySpent,
        table:            table,
        whiteGoldEstimate: computeEconEstimate(0),
        blackGoldEstimate: computeEconEstimate(1)
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
