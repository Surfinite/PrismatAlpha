'use strict';

/**
 * state_adapter.js — Converts JS engine State objects to vectorize.py JSONL format.
 *
 * The JS engine uses internal card names (e.g., "Tesla Tower") while vectorize.py
 * expects display names (e.g., "Tarsier"). This module bridges the two by using
 * each Card's .UIName property.
 *
 * Output format matches what vectorize.py consumes:
 *   { state: { p0_units, p1_units, p0_resources, p1_resources,
 *              p0_attack, p1_attack, card_set },
 *     turn, active_player, result, action: { bought } }
 *
 * Mana pool indices (from C.js):
 *   MANA_P=0 (gold), MANA_G=1 (green), MANA_B=2 (blue),
 *   MANA_R=3 (red), MANA_H=4 (energy), MANA_A=5 (attack)
 */

const C = require('./C');

// Mana pool index constants (duplicated here for clarity and to avoid
// depending on C.js export ordering)
const MANA_P = 0;  // Gold
const MANA_G = 1;  // Green
const MANA_B = 2;  // Blue
const MANA_R = 3;  // Red
const MANA_H = 4;  // Energy
const MANA_A = 5;  // Attack

/**
 * Extract resources from a Mana object into the format vectorize.py expects.
 *
 * @param {Mana} mana - Mana object with .pool array [gold, green, blue, red, energy, attack]
 * @returns {Object} { gold, green, blue, red, energy, attack }
 */
function manaToResources(mana) {
    const pool = mana.pool;
    return {
        gold:   pool[MANA_P] || 0,
        green:  pool[MANA_G] || 0,
        blue:   pool[MANA_B] || 0,
        red:    pool[MANA_R] || 0,
        energy: pool[MANA_H] || 0,
        attack: pool[MANA_A] || 0
    };
}

/**
 * Convert a single Inst object to the per-instance unit format vectorize.py expects.
 *
 * Mapping from AS3/JS engine concepts to vectorize.py features:
 *   - building:    inst.constructionTime > 0
 *   - blocking:    inst.blocking === true AND inst.role === "assigned"
 *                  (assigned as blocker during defense phase)
 *   - abilityUsed: inst.role === "assigned" (used ability during action phase)
 *   - name:        inst.card.UIName (display name, e.g., "Tarsier" not "Tesla Tower")
 *
 * @param {Inst} inst - Card instance from state.table
 * @returns {Object} { name, building, blocking, abilityUsed }
 */
function instToUnit(inst) {
    const isBuilding = inst.constructionTime > 0;
    const isAssigned = inst.role === C.ROLE_ASSIGNED;

    return {
        name:        inst.card.UIName,
        building:    isBuilding,
        blocking:    inst.blocking === true && isAssigned,
        abilityUsed: isAssigned
    };
}

/**
 * Convert a single Inst object to a rich per-instance feature vector for DeepSets training.
 *
 * Extracts 10 instance-state features that capture much richer information than
 * the basic instToUnit() above. Used for DeepSets architecture training data.
 *
 * HP semantics differ by unit type:
 *   - Fragile units: inst.health tracks remaining HP directly
 *   - Non-fragile units: currentHP = inst.health - inst.damage (damage accumulates)
 *
 * Role-based ability inference:
 *   - is_blocking: role===ROLE_ASSIGNED AND inst.blocking===true
 *   - ability_used: role===ROLE_ASSIGNED AND NOT blocking
 *   Note: inst.abilityUsed does NOT exist on Inst; role-based inference matches
 *   existing instToUnit() convention. At start-of-turn snapshots this is typically 0.
 *
 * @param {Inst} inst - Card instance from state.table (must be alive)
 * @returns {Object} {
 *   name, owner, is_constructing, turns_until_ready, is_blocking, ability_used,
 *   current_hp, hp_fraction, is_frozen, lifespan_remaining, stamina_remaining
 * }
 */
function instToRichUnit(inst) {
    const card = inst.card;
    const isBuilding = inst.constructionTime > 0;
    const baseHealth = card.startingHealth || 1;
    const currentHp = card.fragile
        ? inst.health
        : (inst.health - inst.damage);

    return {
        name:               card.UIName,
        owner:              inst.owner,           // 0 or 1
        is_constructing:    isBuilding ? 1 : 0,
        turns_until_ready:  Math.max(inst.constructionTime, inst.delay),
        is_blocking:        (inst.blocking && inst.role === C.ROLE_ASSIGNED) ? 1 : 0,
        ability_used:       (inst.role === C.ROLE_ASSIGNED && !inst.blocking) ? 1 : 0,
        current_hp:         Math.max(0, currentHp),
        hp_fraction:        baseHealth > 0 ? Math.max(0, currentHp) / baseHealth : 0,
        is_frozen:          inst.disruptDamage > 0 ? 1 : 0,
        lifespan_remaining: inst.lifespan === -1 ? 0 : Math.max(0, inst.lifespan),
        stamina_remaining:  inst.charge || 0
    };
}

/**
 * Map the JS engine's state.result to vectorize.py's result convention.
 *
 * JS engine results (from C.js):
 *   COLOR_NONE (2) = game ongoing
 *   COLOR_WHITE (0) = white (player 0) won
 *   COLOR_BLACK (1) = black (player 1) won
 *   COLOR_DRAW_MUTUAL_ELIMINATION (3) = draw
 *   COLOR_DRAW_STALEMATE (4) = draw
 *
 * vectorize.py convention:
 *   null = ongoing, 0 = player 0 won, 1 = player 1 won, 2 = draw
 *
 * @param {number} result - state.result value
 * @returns {number|null}
 */
function mapResult(result) {
    switch (result) {
        case C.COLOR_WHITE:
            return 0;
        case C.COLOR_BLACK:
            return 1;
        case C.COLOR_NONE:
            return null;
        case C.COLOR_DRAW_MUTUAL_ELIMINATION:
        case C.COLOR_DRAW_STALEMATE:
            return 2;
        default:
            // Other result codes (AFK, WhiteGold, WhiteDiamond) treated as draws
            return 2;
    }
}

/**
 * Build the card_set array: display names of all buyable cards in the merged deck.
 *
 * A card is in the card set if either player has nonzero supply for it.
 * Uses UIName (display name) for each card.
 *
 * @param {State} state - JS engine State object
 * @returns {string[]} Array of display names
 */
function buildCardSet(state) {
    const cardSet = [];
    const numCards = state.cards.length;

    for (let i = 0; i < numCards; i++) {
        const whiteSupply = state.whiteSupply[i] || 0;
        const blackSupply = state.blackSupply[i] || 0;
        // Also check if either player bought any (supply may be 0 if all purchased)
        const whiteBought = state.whiteBought[i] || 0;
        const blackBought = state.blackBought[i] || 0;

        if (whiteSupply > 0 || blackSupply > 0 || whiteBought > 0 || blackBought > 0) {
            cardSet.push(state.cards[i].UIName);
        }
    }

    return cardSet;
}

/**
 * Build the supply object for vectorize.py.
 *
 * Supply is per-card, per-player: how many copies remain available for purchase.
 *
 * @param {State} state - JS engine State object
 * @returns {Object} { "Drone": { p0: N, p1: N }, ... } keyed by display name
 */
function buildSupply(state) {
    const supply = {};
    const numCards = state.cards.length;

    for (let i = 0; i < numCards; i++) {
        const ws = state.whiteSupply[i] || 0;
        const bs = state.blackSupply[i] || 0;

        if (ws > 0 || bs > 0) {
            supply[state.cards[i].UIName] = {
                p0: ws,
                p1: bs
            };
        }
    }

    return supply;
}

/**
 * Convert the state portion of a JS engine State to the format vectorize.py expects.
 *
 * This includes units for both players, resources, attack values, supply, and card_set.
 * All unit names use display names (UIName).
 *
 * @param {State} state - JS engine State object
 * @returns {Object} The "state" portion of a training example
 */
function stateToVectorizeJSON(state) {
    const p0Units = [];
    const p1Units = [];

    // Iterate all instances on the board
    state.table.forEach(function(inst) {
        // Skip dead units
        if (inst.deadness !== C.DEADNESS_ALIVE) {
            return;
        }

        const unit = instToUnit(inst);

        if (inst.owner === 0) {
            p0Units.push(unit);
        } else {
            p1Units.push(unit);
        }
    });

    const p0Resources = manaToResources(state.whiteMana);
    const p1Resources = manaToResources(state.blackMana);

    return {
        p0_units:     p0Units,
        p1_units:     p1Units,
        p0_resources: p0Resources,
        p1_resources: p1Resources,
        p0_attack:    p0Resources.attack,
        p1_attack:    p1Resources.attack,
        supply:       buildSupply(state),
        card_set:     buildCardSet(state)
    };
}

/**
 * Convert a JS engine State to a full training example for vectorize.py.
 *
 * Produces one JSON-serializable object per game position that matches the
 * JSONL format consumed by vectorize.py (and training/train.py).
 *
 * @param {State} state - JS engine State object
 * @param {string|number} gameId - Unique game identifier (used as replay_code)
 * @param {string[]} [boughtCards] - Array of display-name strings bought this turn
 *                                   (optional, defaults to empty)
 * @returns {Object} Training example ready for JSON.stringify + newline
 */
function stateToTrainingExample(state, gameId, boughtCards) {
    const activePlayer = state.turn;  // 0=white, 1=black (computed as (numTurns + 1) % 2)

    const example = {
        state:         stateToVectorizeJSON(state),
        turn:          state.numTurns,
        active_player: activePlayer,
        result:        mapResult(state.result),
        action: {
            bought: Array.isArray(boughtCards) ? boughtCards : []
        }
    };

    // Include game ID as replay_code for train/val split by game
    if (gameId !== undefined && gameId !== null) {
        example.replay_code = String(gameId);
    }

    return example;
}

module.exports = {
    stateToTrainingExample,
    stateToVectorizeJSON,

    // Exported for testing
    _manaToResources: manaToResources,
    _instToUnit:      instToUnit,
    _instToRichUnit:  instToRichUnit,
    _mapResult:       mapResult,
    _buildCardSet:    buildCardSet,
    _buildSupply:     buildSupply
};
