'use strict';

/**
 * SacDescription.js — Sacrifice cost specification, transpiled from mcds/engine/SacDescription.as
 *
 * Describes units that must be sacrificed as part of a buy or ability cost.
 */
class SacDescription {
    /**
     * @param {Array} obj - Array: [cardName, multiplicity?]
     */
    constructor(obj) {
        this.cardName = obj[0];
        this.card = null;  // Resolved later when cards are loaded
        if (obj.length > 1) {
            this.multiplicity = obj[1] | 0;
        } else {
            this.multiplicity = 1;
        }
    }

    /**
     * Convert to public-facing JSON (display names).
     * Uses Util.OldtoNewName mapping — stubbed for now, resolved in Phase 2.
     */
    toPublicJSON() {
        const answer = {};
        // Util.OldtoNewName maps internal→display names
        // For now, use cardName directly; Card.js will provide the mapping
        answer.name = this.cardName;
        answer.multiplicity = this.multiplicity;
        return answer;
    }
}

module.exports = SacDescription;
