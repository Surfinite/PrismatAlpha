'use strict';

const C = require('./C');

/**
 * Inst.js — Card instance on the board, transpiled from mcds/engine/Inst.as
 *
 * Represents a specific unit/spell instance. Each Inst references its Card
 * type and holds mutable state (health, role, blocking, etc.).
 */
class Inst {
    /**
     * @param {Card} card - Card type definition
     * @param {number} owner - Player index (0 or 1)
     * @param {boolean} bought - Whether this was purchased this turn
     * @param {number} buildTime - Construction time
     * @param {boolean} invulnerable - Under construction (invulnerable)
     * @param {number} instId - Unique instance identifier
     * @param {number} laneId - Lane identifier
     * @param {Object} [toy] - JSON object to restore from (for clone/deserialize)
     */
    constructor(card, owner, bought, buildTime, invulnerable, instId, laneId, toy) {
        let i = 0;
        let j = 0;

        if (toy == null) {
            // Fresh construction
            if (bought) {
                C.ASSERT(invulnerable, 'A bought Inst must be invulnerable.');
                C.ASSERT(buildTime === card.buildTime,
                    'A bought Inst must have buildTime equal to the buildTime of the card.');
            }

            this.instId = instId;
            this.card = card;
            this.owner = owner;
            this.bought = bought;

            if (bought) {
                this.role = C.ROLE_SELLABLE;
            } else {
                this.role = C.ROLE_INERT;
            }

            if (buildTime > 0) {
                this.blocking = false;
            } else {
                this.blocking = card.defaultBlocking;
            }

            this.deadness = C.DEADNESS_ALIVE;
            this.health = card.startingHealth;
            this.damage = 0;
            this.disruptDamage = 0;
            this.charge = card.startingCharge;

            if (invulnerable) {
                this.constructionTime = buildTime;
                this.delay = 0;
            } else {
                this.constructionTime = 0;
                this.delay = buildTime;
            }

            this.lifespan = card.lifespan;
            this.target = -1;

            // Buy create IDs (2D array)
            this.buyCreateIds = new Array(
                card.buyScript === null ? 0 : card.buyScript.create.length
            );
            for (i = 0; i < this.buyCreateIds.length; i++) {
                this.buyCreateIds[i] = new Array(card.buyScript.create[i].multiplicity);
                for (j = 0; j < this.buyCreateIds[i].length; j++) {
                    this.buyCreateIds[i][j] = -1;
                }
            }

            // Begin own turn create IDs
            this.beginOwnTurnCreateIds = new Array(
                card.beginOwnTurnScript === null ? 0 : card.beginOwnTurnScript.create.length
            );
            for (i = 0; i < this.beginOwnTurnCreateIds.length; i++) {
                this.beginOwnTurnCreateIds[i] = new Array(
                    card.beginOwnTurnScript.create[i].multiplicity
                );
                for (j = 0; j < this.beginOwnTurnCreateIds[i].length; j++) {
                    this.beginOwnTurnCreateIds[i][j] = -1;
                }
            }

            // Ability create IDs
            this.abilityCreateIds = new Array(
                card.abilityScript === null ? 0 : card.abilityScript.create.length
            );
            for (i = 0; i < this.abilityCreateIds.length; i++) {
                this.abilityCreateIds[i] = new Array(card.abilityScript.create[i].multiplicity);
                for (j = 0; j < this.abilityCreateIds[i].length; j++) {
                    this.abilityCreateIds[i][j] = -1;
                }
            }

            this.creatorIdFromBuyOrAbility = -1;
            this.creatorIdFromBeginTurn = -1;
            this.disruptorIds = [];
            this.sniperId = -1;
            this.laneId = laneId;
        } else {
            // Restore from serialized object
            this.instId = toy.instId;
            this.card = card;
            this.owner = toy.owner;
            this.bought = false; // Not preserved in toObject

            // Role mapping (AS3 Inst.as:141-157)
            switch (toy.role) {
                case C.ROLE_DEFAULT:
                    this.role = 'default';
                    break;
                case C.ROLE_ASSIGNED:
                    this.role = 'assigned';
                    break;
                case C.ROLE_SELLABLE:
                    this.role = 'sellable';
                    break;
                case C.ROLE_INERT:
                    this.role = 'inert';
                    break;
                default:
                    C.ASSERT(false, 'Invalid role from JSON representation of Inst.');
            }

            this.blocking = toy.blocking;
            this.deadness = toy.deadness;
            this.health = toy.health;
            this.damage = toy.damage;
            this.disruptDamage = toy.disruptDamage;
            this.charge = toy.charge;
            this.constructionTime = toy.constructionTime;
            this.delay = toy.delay;
            this.lifespan = toy.lifespan;
            this.target = toy.target;

            // Deep copy 2D arrays
            this.buyCreateIds = new Array(toy.buyCreateIds.length);
            for (i = 0; i < this.buyCreateIds.length; i++) {
                this.buyCreateIds[i] = new Array(toy.buyCreateIds[i].length);
                for (j = 0; j < this.buyCreateIds[i].length; j++) {
                    this.buyCreateIds[i][j] = toy.buyCreateIds[i][j];
                }
            }

            this.beginOwnTurnCreateIds = new Array(toy.beginOwnTurnCreateIds.length);
            for (i = 0; i < this.beginOwnTurnCreateIds.length; i++) {
                this.beginOwnTurnCreateIds[i] = new Array(toy.beginOwnTurnCreateIds[i].length);
                for (j = 0; j < this.beginOwnTurnCreateIds[i].length; j++) {
                    this.beginOwnTurnCreateIds[i][j] = toy.beginOwnTurnCreateIds[i][j];
                }
            }

            this.abilityCreateIds = new Array(toy.abilityCreateIds.length);
            for (i = 0; i < this.abilityCreateIds.length; i++) {
                this.abilityCreateIds[i] = new Array(toy.abilityCreateIds[i].length);
                for (j = 0; j < this.abilityCreateIds[i].length; j++) {
                    this.abilityCreateIds[i][j] = toy.abilityCreateIds[i][j];
                }
            }

            this.creatorIdFromBuyOrAbility = toy.creatorIdFromBuyOrAbility;
            this.creatorIdFromBeginTurn = toy.creatorIdFromBeginTurn;

            this.disruptorIds = new Array(toy.disruptorIds.length);
            for (i = 0; i < this.disruptorIds.length; i++) {
                this.disruptorIds[i] = toy.disruptorIds[i];
            }

            this.sniperId = toy.sniperId;
            this.laneId = toy.laneId;
        }
    }

    // --- Computed properties (from Inst.as:207-290) ---

    get cardName() {
        return this.card.cardName;
    }

    get dead() {
        return this.deadness !== C.DEADNESS_ALIVE;
    }

    get isPartiallyDamaged() {
        return (!this.dead || this.deadness === C.DEADNESS_SNIPED) && this.damage > 0;
    }

    get damageItCanTake() {
        return this.health - (this.card.fragile ? 0 : this.damage);
    }

    get damageReqdToInjure() {
        return this.card.fragile ? 1 : this.health;
    }

    get absorb() {
        return this.card.fragile ? this.card.healthGained : (this.health - 1);
    }

    get delayAfterSwoosh() {
        if (this.role === C.ROLE_ASSIGNED) return 0;
        return this.delay;
    }

    get chargeAfterSwoosh() {
        if (this.role === C.ROLE_ASSIGNED) {
            return this.charge + this.card.chargeUsed;
        }
        return this.charge;
    }

    get enoughChargeToAssignAfterSwoosh() {
        return this.chargeAfterSwoosh >= this.card.chargeUsed;
    }

    get hpAfterSwoosh() {
        if (this.role === C.ROLE_ASSIGNED) {
            return this.damageItCanTake + this.damage + this.card.healthUsed;
        }
        return this.damageItCanTake + this.damage;
    }

    get enoughHPToAssignAfterSwoosh() {
        return this.hpAfterSwoosh >= this.card.healthUsed;
    }

    get convertedLifespan() {
        if (this.lifespan === -1) return 32767;
        return this.lifespan + this.delay;
    }

    get convertedDelay() {
        if (this.delay === 1) return 0;
        return this.delay;
    }

    // --- Comparison methods ---

    weaklyEqualTo(model, ignoreDeadness) {
        if (ignoreDeadness === undefined) ignoreDeadness = false;

        if (this.card.cardName !== model.card.cardName) return false;
        if (this.owner !== model.owner) return false;
        if (this.blocking !== model.blocking) return false;
        if ((this.constructionTime === 0 && model.constructionTime > 0) ||
            (this.constructionTime > 0 && model.constructionTime === 0)) {
            return false;
        }

        let deadness1 = this.deadness;
        if (this.isPartiallyDamaged || deadness1 === C.DEADNESS_BLOCKED) {
            deadness1 = C.DEADNESS_WBO;
        }
        if (deadness1 === C.DEADNESS_SELFSACCED) {
            deadness1 = C.DEADNESS_ALIVE;
        }

        let deadness2 = model.deadness;
        if (model.isPartiallyDamaged || deadness2 === C.DEADNESS_BLOCKED) {
            deadness2 = C.DEADNESS_WBO;
        }
        if (deadness2 === C.DEADNESS_SELFSACCED) {
            deadness2 = C.DEADNESS_ALIVE;
        }

        if (deadness1 !== deadness2) return false;
        return true;
    }

    stronglyEqualTo(model) {
        if (!this.weaklyEqualTo(model, true)) return false;
        if (this.role !== model.role) return false;
        if (this.enoughHPToAssignAfterSwoosh !== model.enoughHPToAssignAfterSwoosh) return false;
        if (this.enoughChargeToAssignAfterSwoosh !== model.enoughChargeToAssignAfterSwoosh) {
            return false;
        }
        return true;
    }

    // --- Serialization ---

    toObject() {
        let j = 0;
        const toy = {};
        toy.instId = this.instId;
        toy.cardName = this.card.cardName;
        toy.owner = this.owner;

        switch (this.role) {
            case C.ROLE_DEFAULT:
                toy.role = 'default';
                break;
            case C.ROLE_ASSIGNED:
                toy.role = 'assigned';
                break;
            case C.ROLE_SELLABLE:
                toy.role = 'sellable';
                break;
            case C.ROLE_INERT:
                toy.role = 'inert';
                break;
        }

        toy.blocking = this.blocking;
        toy.deadness = this.deadness;
        toy.dead = this.dead;
        toy.health = this.health;
        toy.damage = this.damage;
        toy.disruptDamage = this.disruptDamage;
        toy.charge = this.charge;
        toy.constructionTime = this.constructionTime;
        toy.delay = this.delay;
        toy.lifespan = this.lifespan;
        toy.target = this.target;

        toy.buyCreateIds = new Array(this.buyCreateIds.length);
        for (let i = 0; i < this.buyCreateIds.length; i++) {
            toy.buyCreateIds[i] = new Array(this.buyCreateIds[i].length);
            for (j = 0; j < this.buyCreateIds[i].length; j++) {
                toy.buyCreateIds[i][j] = this.buyCreateIds[i][j];
            }
        }

        toy.beginOwnTurnCreateIds = new Array(this.beginOwnTurnCreateIds.length);
        for (let i = 0; i < this.beginOwnTurnCreateIds.length; i++) {
            toy.beginOwnTurnCreateIds[i] = new Array(this.beginOwnTurnCreateIds[i].length);
            for (j = 0; j < this.beginOwnTurnCreateIds[i].length; j++) {
                toy.beginOwnTurnCreateIds[i][j] = this.beginOwnTurnCreateIds[i][j];
            }
        }

        toy.abilityCreateIds = new Array(this.abilityCreateIds.length);
        for (let i = 0; i < this.abilityCreateIds.length; i++) {
            toy.abilityCreateIds[i] = new Array(this.abilityCreateIds[i].length);
            for (j = 0; j < this.abilityCreateIds[i].length; j++) {
                toy.abilityCreateIds[i][j] = this.abilityCreateIds[i][j];
            }
        }

        toy.creatorIdFromBuyOrAbility = this.creatorIdFromBuyOrAbility;
        toy.creatorIdFromBeginTurn = this.creatorIdFromBeginTurn;

        toy.disruptorIds = new Array(this.disruptorIds.length);
        for (let i = 0; i < this.disruptorIds.length; i++) {
            toy.disruptorIds[i] = this.disruptorIds[i];
        }

        toy.sniperId = this.sniperId;
        toy.laneId = this.laneId;

        return toy;
    }

    clone() {
        return new Inst(this.card, 0, false, 0, false, 0, 0, this.toObject());
    }

    toString() {
        const temp = {};
        temp.cardName = this.card.cardName;
        temp.owner = this.owner;
        temp.role = this.role;
        temp.blocking = this.blocking;
        temp.deadness = this.deadness;
        temp.health = this.health;
        temp.damage = this.damage;
        temp.disruptDamage = this.disruptDamage;
        temp.charge = this.charge;
        temp.constructionTime = this.constructionTime;
        temp.delay = this.delay;
        temp.lifespan = this.lifespan;
        return JSON.stringify(temp);
    }

    compareWithJSON(obj) {
        if (obj.hasOwnProperty('cardName') && obj.cardName !== this.card.cardName) return false;
        if (obj.hasOwnProperty('owner') && obj.owner !== this.owner) return false;
        if (obj.hasOwnProperty('role') && obj.role !== this.role) return false;
        if (obj.hasOwnProperty('blocking') && obj.blocking !== this.blocking) return false;
        if (obj.hasOwnProperty('deadness') && obj.deadness !== this.deadness) return false;
        if (obj.hasOwnProperty('health') && obj.health !== this.health) return false;
        if (obj.hasOwnProperty('damage') && obj.damage !== this.damage) return false;
        if (obj.hasOwnProperty('disruptDamage') && obj.disruptDamage !== this.disruptDamage) {
            return false;
        }
        if (obj.hasOwnProperty('charge') && obj.charge !== this.charge) return false;
        if (obj.hasOwnProperty('constructionTime') &&
            obj.constructionTime !== this.constructionTime) {
            return false;
        }
        if (obj.hasOwnProperty('delay') && obj.delay !== this.delay) return false;
        if (obj.hasOwnProperty('lifespan') && obj.lifespan !== this.lifespan) return false;
        return true;
    }
}

module.exports = Inst;
