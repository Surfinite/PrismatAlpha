// tools/position_calculator.js
// Port of position-calculator.ts — assigns render.row and render.slot
// based on unit properties from cardLibrary.jso.
//
// Row mapping: positions 0-9 = "front", 10-19 = "middle", 20-29 = "back"
//
// Ported 1:1 from <ladder>-site/src/components/game-renderer/position-calculator.ts

// Position constants (sparse — gaps intentional, matching AS3 Card.js lines 269-324)
const P = {
    FRONT_FAR_LEFT:      0,
    FRONT_FAR_LEFT_ONE:  1,
    FRONT_FAR_LEFT_TWO:  2,
    FRONT_LEFT:          3,
    FRONT_LEFT_ONE:      4,
    FRONT_RIGHT:         6,
    FRONT_RIGHT_ONE:     7,
    MIDDLE_FAR_LEFT:     10,
    MIDDLE_FAR_LEFT_ONE: 11,
    MIDDLE_LEFT:         13,
    MIDDLE_RIGHT:        16,
    MIDDLE_FAR_RIGHT:    18,
    BACK_FAR_LEFT:       20,
    BACK_FAR_LEFT_ONE:   21,
    BACK_FAR_LEFT_TWO:   22,
    BACK_LEFT:           23,
    BACK_RIGHT:          26,
    BACK_FAR_RIGHT:      29,
};

/**
 * Compute the display position for a card.
 * @param {object} card - Card metadata with properties from cardLibrary.jso
 * @returns {number} Position 0-29 (sparse)
 */
function computePosition(card) {
    // 1. Explicit position wins
    if (card.position !== undefined && card.position !== null) {
        return card.position;
    }

    // Resolve card name from either convention
    const name = card.UIName || card.cardName;

    // 2. Named base units
    if (name === 'Conduit')    return P.BACK_FAR_LEFT;
    if (name === 'Blastforge') return P.BACK_FAR_LEFT_ONE;
    if (name === 'Animus')     return P.BACK_FAR_LEFT_TWO;
    if (name === 'Drone')      return P.MIDDLE_FAR_LEFT;
    if (name === 'Engineer')   return P.FRONT_FAR_LEFT;

    // 3. Spells go to far back-right
    if (card.cardType === 'spell') return P.BACK_FAR_RIGHT;

    // Helper: does this card attack or have targeting?
    const attacksOrTargets =
        (card.attackPotential || card.attack || 0) > 0 ||
        !!card.targetHas ||
        !!card.hasTargetAbility;

    // 4. Undefendable units
    if (card.undefendable) {
        return attacksOrTargets ? P.FRONT_RIGHT_ONE : P.FRONT_RIGHT;
    }

    // 5. Units with an activated ability
    if (card.hasAbility) {
        if (card.defaultBlocking && card.assignedBlocking) {
            return attacksOrTargets ? P.FRONT_LEFT_ONE : P.FRONT_LEFT;
        }
        if (card.defaultBlocking && !card.assignedBlocking) {
            return attacksOrTargets ? P.MIDDLE_RIGHT : P.MIDDLE_FAR_LEFT_ONE;
        }
        // !defaultBlocking && !assignedBlocking
        return attacksOrTargets ? P.MIDDLE_FAR_RIGHT : P.MIDDLE_LEFT;
    }

    // 6. Default-blocking units (no ability)
    if (card.defaultBlocking) {
        return attacksOrTargets ? P.FRONT_FAR_LEFT_TWO : P.FRONT_FAR_LEFT_ONE;
    }

    // 7. Plain attackers / targeting units
    if (attacksOrTargets) return P.BACK_RIGHT;

    // 8. Everything else (pure economy / structures with no ability)
    return P.BACK_LEFT;
}

/**
 * Map position to row name.
 */
function positionToRow(position) {
    const rowIndex = Math.floor(position / 10);
    return ['front', 'middle', 'back'][rowIndex] || 'back';
}

/**
 * Compute render info (row + slot) for a card.
 */
function computeRenderInfo(card) {
    const slot = computePosition(card);
    return {
        row: positionToRow(slot),
        slot: slot
    };
}

// CLI: node tools/position_calculator.js
if (require.main === module) {
    const { buildCardIdMap } = require('./card_id_map');
    const path = require('path');
    const fs = require('fs');

    const libPath = path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso');
    const library = JSON.parse(fs.readFileSync(libPath, 'utf-8'));
    const idMap = buildCardIdMap(libPath);

    // Test with known units
    const testUnits = ['Drone', 'Engineer', 'Tesla Tower', 'Conduit', 'Wall', 'Brooder'];
    for (const name of testUnits) {
        const card = library[name];
        if (!card) continue;
        // Ensure UIName is available for position calc
        const cardWithName = { ...card, UIName: card.UIName || name };
        const info = computeRenderInfo(cardWithName);
        const displayName = idMap[name] ? idMap[name].displayName : name;
        console.log(displayName + ' (' + name + '): row=' + info.row + ', slot=' + info.slot);
    }
}

module.exports = { computePosition, positionToRow, computeRenderInfo, POSITIONS: P };
