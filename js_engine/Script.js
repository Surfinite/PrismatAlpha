'use strict';

const Mana = require('./Mana');
const CreateDescription = require('./CreateDescription');

/**
 * Script.js — Ability/buy/turn script payload, transpiled from mcds/engine/Script.as
 *
 * Describes what happens when an ability activates, a unit is bought,
 * or a turn begins (resources generated, units created, self-sacrifice, etc.)
 */
class Script {
    /**
     * @param {Object} obj - Script definition from cardLibrary.jso
     *   Properties: receive, create, selfsac, delay, scan, massChill
     */
    constructor(obj) {
        // Resources received
        if (obj.hasOwnProperty('receive')) {
            this.receive = new Mana(obj.receive);
        } else {
            this.receive = new Mana('');
        }

        // Units created
        if (obj.hasOwnProperty('create')) {
            this.create = new Array(obj.create.length);
            for (let i = 0; i < this.create.length; i++) {
                this.create[i] = new CreateDescription(obj.create[i]);
            }
        } else {
            this.create = [];
        }

        // Self-sacrifice
        if (obj.hasOwnProperty('selfsac') && obj.selfsac === true) {
            this.selfsac = true;
        } else {
            this.selfsac = false;
        }

        // Delay (turns before script executes)
        if (obj.hasOwnProperty('delay')) {
            this.delay = obj.delay | 0;
        } else {
            this.delay = 0;
        }

        // Scan effect
        if (obj.hasOwnProperty('scan')) {
            this.scan = obj.scan | 0;
        } else {
            this.scan = 0;
        }

        // Mass chill effect
        if (obj.hasOwnProperty('massChill')) {
            this.massChill = obj.massChill | 0;
        } else {
            this.massChill = 0;
        }
    }

    /**
     * Convert to public-facing JSON.
     * From Script.as:76-101.
     */
    toPublicJSON() {
        const answer = {};
        if (!this.receive.isEmpty) {
            answer.receive = this.receive.toPublicFacingString();
        }
        if (this.create.length > 0) {
            answer.create = new Array(this.create.length);
            for (let i = 0; i < this.create.length; i++) {
                answer.create[i] = this.create[i].toPublicJSON();
            }
        }
        if (this.selfsac) {
            answer.selfsac = true;
        }
        if (this.delay > 0) {
            answer.delay = this.delay;
        }
        return answer;
    }
}

module.exports = Script;
