'use strict';

const C = require('./C');

/**
 * CreateDescription.js — Token/unit creation specification,
 * transpiled from mcds/engine/CreateDescription.as
 *
 * Describes units spawned by abilities, buy scripts, or death triggers.
 * Parsed from array format: [cardName, "own"|"opponent"?, multiplicity?, buildTime?, lifespan?, "invulnerable"?]
 */
class CreateDescription {
    /**
     * @param {Array} obj - Creation spec array
     */
    constructor(obj) {
        this.cardName = obj[0];
        this.card = null;  // Resolved later when cards are loaded

        // Owner (default: own)
        if (obj.length > 1) {
            if (obj[1] === 'own') {
                this.own = true;
            } else if (obj[1] === 'opponent') {
                this.own = false;
            } else {
                C.ASSERT(false, 'Invalid owner in CreateDescription in JSON input.');
            }
        } else {
            this.own = true;
        }

        // Multiplicity (default: 1)
        if (obj.length > 2) {
            this.multiplicity = obj[2] | 0;
        } else {
            this.multiplicity = 1;
        }

        // Build time (default: 1)
        if (obj.length > 3) {
            this.buildTime = obj[3] | 0;
        } else {
            this.buildTime = 1;
        }

        // Lifespan (default: -1 = permanent)
        if (obj.length > 4) {
            this.lifespan = obj[4] | 0;
        } else {
            this.lifespan = -1;
        }

        // Invulnerable (default: false)
        if (obj.length > 5) {
            this.invuln = obj[5] === 'invulnerable';
        } else {
            this.invuln = false;
        }
    }

    /**
     * Convert to public-facing JSON.
     * From CreateDescription.as:80-92.
     */
    toPublicJSON() {
        const answer = {};
        // Util.OldtoNewName mapping — stubbed, resolved in Phase 2
        answer.name = this.cardName;
        if (!this.own) {
            answer.forOpponent = true;
        }
        answer.multiplicity = this.multiplicity;
        answer.buildTime = this.buildTime;
        answer.lifespan = this.lifespan;
        return answer;
    }
}

module.exports = CreateDescription;
