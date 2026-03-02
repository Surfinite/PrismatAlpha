'use strict';

const C = require('./C');
const Mana = require('./Mana');
const Script = require('./Script');
const SacDescription = require('./SacDescription');

/**
 * Card.js — Card type definition, transpiled from mcds/engine/Card.as
 *
 * Represents a card TYPE (not instance). Parsed from cardLibrary.jso entries.
 * Each unique card (Drone, Tarsier, etc.) has one Card object.
 * Card instances on the board are Inst objects that reference their Card.
 */

// Color type constants
const COLOR_TYPE_GREEN = 'unitGreen';
const COLOR_TYPE_BLUE = 'unitBlue';
const COLOR_TYPE_RED = 'unitRed';
const COLOR_TYPE_WHITE = 'unitWhite';

class Card {
    /**
     * @param {Object} obj - Card definition from cardLibrary.jso / mergedDeck
     * @param {number} cardId - Index in the cards array
     */
    constructor(obj, cardId) {
        let i = 0;

        this.cardId = cardId;
        this.cardName = obj.name;
        this.UIName = obj.UIName || this.cardName;
        this.UIShortname = obj.UIShortname || this.UIName;
        this.UIArt = obj.UIArt || this.UIName;
        this.UIPlural = obj.plural || this.UIName + 's';

        // Article determination
        if ('AEIOU'.indexOf(this.UIName.charAt(0)) !== -1) {
            this.article = 'an';
        } else {
            this.article = 'a';
        }

        // Spell vs Unit
        if (obj.hasOwnProperty('spell') && !!obj.spell) {
            this.cardType = C.CARDTYPE_SPELL;
            this.defaultBlocking = false;
            this.assignedBlocking = false;
            this.fragile = false;
            this.healthUsed = 0;
            this.healthGained = 0;
            this.healthMax = 0;
            this.startingCharge = 0;
            this.chargeUsed = 0;
            this.chargeGained = 0;
            this.chargeMax = 0;
            this.undefendable = false;
            this.lifespan = -1;
        } else {
            this.cardType = C.CARDTYPE_UNIT;
            this.defaultBlocking = !!obj.defaultBlocking;
            this.assignedBlocking = false;
            if (obj.hasOwnProperty('assignedBlocking') && !!obj.assignedBlocking) {
                this.assignedBlocking = true;
            }

            // Health / toughness
            if (obj.hasOwnProperty('toughness')) {
                this.startingHealth = obj.toughness;
            } else {
                this.startingHealth = 1;
            }

            // Fragile
            this.fragile = false;
            this.healthUsed = 0;
            this.healthGained = 0;
            this.healthMax = 0;
            if (obj.hasOwnProperty('fragile') && !!obj.fragile) {
                this.fragile = true;
                if (obj.hasOwnProperty('HPUsed')) {
                    this.healthUsed = obj.HPUsed;
                }
                if (obj.hasOwnProperty('HPGained')) {
                    this.healthGained = obj.HPGained;
                }
                if (obj.hasOwnProperty('HPMax')) {
                    this.healthMax = obj.HPMax;
                } else {
                    this.healthMax = this.startingHealth;
                }
            }

            // Charge (stamina)
            this.startingCharge = 0;
            this.chargeUsed = 0;
            this.chargeGained = 0;
            this.chargeMax = 0;
            if (obj.hasOwnProperty('charge')) {
                this.startingCharge = obj.charge;
                if (obj.hasOwnProperty('chargeUsed')) {
                    this.chargeUsed = obj.chargeUsed;
                } else {
                    this.chargeUsed = 1;
                }
                if (obj.hasOwnProperty('chargeGained')) {
                    this.chargeGained = obj.chargeGained;
                }
                if (obj.hasOwnProperty('chargeMax')) {
                    this.chargeMax = obj.chargeMax;
                } else {
                    this.chargeMax = this.startingCharge;
                }
            }

            // Undefendable (frontline)
            this.undefendable = false;
            if (obj.hasOwnProperty('undefendable') && !!obj.undefendable) {
                this.undefendable = true;
            }

            // Lifespan
            if (obj.hasOwnProperty('lifespan')) {
                this.lifespan = obj.lifespan;
            } else {
                this.lifespan = -1;
            }
        }

        // Build time
        if (obj.hasOwnProperty('buildTime')) {
            this.buildTime = obj.buildTime;
        } else {
            this.buildTime = 1;
        }

        // Rarity and buy properties
        if (obj.hasOwnProperty('rarity') && obj.rarity !== 'unbuyable') {
            if (obj.rarity === 'legendary') {
                this.rarity = C.RARITY_LEGENDARY;
            } else if (obj.rarity === 'rare') {
                this.rarity = C.RARITY_RARE;
            } else if (obj.rarity === 'normal') {
                this.rarity = C.RARITY_NORMAL;
            } else if (obj.rarity === 'trinket') {
                this.rarity = C.RARITY_TRINKET;
            } else {
                C.ASSERT(false, 'Invalid rarity in JSON input.');
            }

            // Buy sacrifice
            if (obj.hasOwnProperty('buySac')) {
                this.buySac = new Array(obj.buySac.length);
                for (i = 0; i < this.buySac.length; i++) {
                    this.buySac[i] = new SacDescription(obj.buySac[i]);
                }
            } else {
                this.buySac = [];
            }

            // Buy script
            this.buyScript = null;
            if (obj.hasOwnProperty('buyScript')) {
                this.buyScript = new Script(obj.buyScript);
            }
        } else {
            this.rarity = C.RARITY_UNBUYABLE;
            this.buySac = [];
            this.buyScript = null;
        }

        // Buy cost
        if (obj.hasOwnProperty('buyCost')) {
            this.buyCost = new Mana(obj.buyCost);
        } else {
            this.buyCost = new Mana('');
        }

        // Begin own turn script
        this.beginOwnTurnScript = null;
        if (obj.hasOwnProperty('beginOwnTurnScript')) {
            this.beginOwnTurnScript = new Script(obj.beginOwnTurnScript);
        }

        // Resonate
        this.resonate = null;
        if (obj.hasOwnProperty('resonate')) {
            this.resonate = obj.resonate;
        }

        // Gold resonate
        this.goldResonate = null;
        if (obj.hasOwnProperty('goldResonate')) {
            this.goldResonate = obj.goldResonate;
        }

        // Ability cost
        if (obj.hasOwnProperty('abilityCost')) {
            this.abilityCost = new Mana(obj.abilityCost);
        } else {
            this.abilityCost = new Mana('');
        }

        // Ability sacrifice
        if (obj.hasOwnProperty('abilitySac')) {
            this.abilitySac = new Array(obj.abilitySac.length);
            for (i = 0; i < this.abilitySac.length; i++) {
                this.abilitySac[i] = new SacDescription(obj.abilitySac[i]);
            }
        } else {
            this.abilitySac = [];
        }

        // Ability netherfy
        this.abilityNetherfy = false;
        if (obj.hasOwnProperty('abilityNetherfy') && !!obj.abilityNetherfy) {
            this.abilityNetherfy = true;
        }

        // Ability script
        this.abilityScript = null;
        if (obj.hasOwnProperty('abilityScript') && obj.abilityScript) {
            this.abilityScript = new Script(obj.abilityScript);
        }

        // Death script — AS3 line 321: assigns to BOTH abilityScript AND deathScript
        this.deathScript = null;
        if (obj.hasOwnProperty('deathScript')) {
            this.deathScript = new Script(obj.deathScript);
            this.abilityScript = this.deathScript;
        }

        // Target action (snipe / chill)
        this.targetAction = C.TARGETACTION_NONE;
        this.targetAmount = 0;
        this.condition = null;
        if (obj.hasOwnProperty('targetAction')) {
            if (obj.targetAction === 'disrupt') {
                this.targetAction = C.TARGETACTION_DISRUPT;
                this.targetAmount = obj.targetAmount;
                this.condition = {};
                this.condition[C.CONDITION_IS_BLOCKING] = true;
            } else if (obj.targetAction === 'snipe') {
                this.targetAction = C.TARGETACTION_SNIPE;
                this.condition = {};
                if (obj.condition.hasOwnProperty('card')) {
                    this.condition[C.CONDITION_CARD] = obj.condition.card;
                }
                if (obj.condition.hasOwnProperty('notBlocking') && !!obj.condition.notBlocking) {
                    this.condition[C.CONDITION_NOT_BLOCKING] = true;
                }
                if (obj.condition.hasOwnProperty('healthAtMost')) {
                    this.condition[C.CONDITION_HEALTH_AT_MOST] = obj.condition.healthAtMost;
                }
                if (obj.condition.hasOwnProperty('nameIn')) {
                    this.condition[C.CONDITION_NAME_IN] = obj.condition.nameIn;
                }
                if (obj.condition.hasOwnProperty('isABC') && !!obj.condition.isABC) {
                    this.condition[C.CONDITION_IS_ABC] = true;
                }
                if (obj.condition.hasOwnProperty('isEngineerTempHack') && !!obj.condition.isEngineerTempHack) {
                    this.condition[C.CONDITION_IS_ENGINEER_TEMP] = true;
                }
            } else {
                C.ASSERT(false, 'Invalid targetAction in JSON input.');
            }
        }

        // Position (UI layout — preserved for faithfulness)
        this.position = 0;
        if (obj.hasOwnProperty('position')) {
            this.position = obj.position;
        } else if (this.cardName === 'Conduit') {
            this.position = C.POSITION_BACK_FAR_LEFT;
        } else if (this.cardName === 'Blastforge') {
            this.position = C.POSITION_BACK_FAR_LEFT_ONE;
        } else if (this.cardName === 'Animus') {
            this.position = C.POSITION_BACK_FAR_LEFT_TWO;
        } else if (this.cardName === 'Drone') {
            this.position = C.POSITION_MIDDLE_FAR_LEFT;
        } else if (this.cardName === 'Engineer') {
            this.position = C.POSITION_FRONT_FAR_LEFT;
        } else if (this.cardType === C.CARDTYPE_SPELL) {
            this.position = C.POSITION_BACK_FAR_RIGHT;
        } else if (this.undefendable) {
            if (this.attackPotential > 0 || this.targetHas) {
                this.position = C.POSITION_FRONT_RIGHT_ONE;
            } else {
                this.position = C.POSITION_FRONT_RIGHT;
            }
        } else if (this.hasAbility) {
            if (this.defaultBlocking && this.assignedBlocking) {
                if (this.attackPotential > 0 || this.targetHas) {
                    this.position = C.POSITION_FRONT_LEFT_ONE;
                } else {
                    this.position = C.POSITION_FRONT_LEFT;
                }
            } else if (this.defaultBlocking && !this.assignedBlocking) {
                if (this.attackPotential > 0 || this.targetHas) {
                    this.position = C.POSITION_MIDDLE_RIGHT;
                } else {
                    this.position = C.POSITION_MIDDLE_FAR_LEFT_ONE;
                }
            } else if (!this.defaultBlocking && !this.assignedBlocking) {
                // PIXIES_IN_BACK_ROW is always false in AS3 (local const)
                if (this.attackPotential > 0 || this.targetHas) {
                    this.position = C.POSITION_MIDDLE_FAR_RIGHT;
                } else {
                    this.position = C.POSITION_MIDDLE_LEFT;
                }
            } else {
                C.ASSERT(false, 'Card is not default-blocking, yet assigned-blocking.');
            }
        } else if (this.defaultBlocking) {
            if (this.attackPotential > 0 || this.targetHas) {
                this.position = C.POSITION_FRONT_FAR_LEFT_TWO;
            } else {
                this.position = C.POSITION_FRONT_FAR_LEFT_ONE;
            }
        } else if (this.attackPotential > 0 || this.targetHas) {
            this.position = C.POSITION_BACK_RIGHT;
        } else {
            this.position = C.POSITION_BACK_LEFT;
        }

        // Potentially more attack
        this.potentiallyMoreAttack = false;
        if (obj.hasOwnProperty('potentiallyMoreAttack') && !!obj.potentiallyMoreAttack) {
            this.potentiallyMoreAttack = true;
        }

        // Description (preserved but not used in headless)
        this.description = null;
        if (obj.hasOwnProperty('description')) {
            this.description = obj.description;
        }

        // Needs array
        if (obj.hasOwnProperty('needs')) {
            this.needs = obj.needs;
        } else {
            this.needs = [];
        }

        // Base set flag
        this.baseSet = false;
        if (obj.hasOwnProperty('baseSet') && !!obj.baseSet) {
            this.baseSet = true;
        }

        // Irregular flag — skip Util.sortedPublicCardsListNewNames() check (UI-only)
        this.irregular = false;
        if (obj.hasOwnProperty('irregular')) {
            this.irregular = true;
        }
    }

    // --- Computed properties ---

    get targetHas() {
        return this.targetAction !== C.TARGETACTION_NONE;
    }

    get hasAbility() {
        return this.abilityScript !== null || this.targetHas;
    }

    get attackPotential() {
        if (this.resonate !== null) {
            return -1;
        }
        let answer = 0;
        if (this.beginOwnTurnScript !== null) {
            answer += this.beginOwnTurnScript.receive.attack;
        }
        if (this.abilityScript !== null) {
            answer += this.abilityScript.receive.attack;
        }
        return answer;
    }

    get disruptPotential() {
        if (this.targetAction === C.TARGETACTION_DISRUPT) {
            return this.targetAmount;
        }
        return 0;
    }

    get workPotential() {
        if (this.goldResonate !== null) {
            return -1;
        }
        let answer = 0;
        if (this.beginOwnTurnScript !== null) {
            answer += this.beginOwnTurnScript.receive.money;
        }
        if (this.abilityScript !== null) {
            answer += this.abilityScript.receive.money;
        }
        return answer;
    }

    get autoClicked() {
        if (this.abilityScript === null) return false;
        if (this.healthUsed > 0) return false;
        if (!this.abilityCost.isEmpty) return false;
        if (this.abilitySac.length > 0) return false;
        if (this.abilityScript.selfsac) return false;
        if (this.defaultBlocking && !this.assignedBlocking &&
            (this.abilityScript.receive.attack > 0 || this.abilityNetherfy)) {
            return false;
        }
        if (this.targetHas) return false;
        if (this.cardName === 'Overheat Ray' ||
            this.cardName === 'Mechaneer' ||
            this.cardName === 'Magna Kronus') {
            return false;
        }
        return true;
    }

    get colorType() {
        if (this.fragile) return COLOR_TYPE_GREEN;
        if (this.buyCost.amountOf(C.MANA_B) > 0) return COLOR_TYPE_BLUE;
        if (this.buyCost.amountOf(C.MANA_G) > 0) return COLOR_TYPE_GREEN;
        if (this.buyCost.amountOf(C.MANA_R) > 0) return COLOR_TYPE_RED;
        return COLOR_TYPE_WHITE;
    }

    /**
     * Serialize to public-facing JSON.
     * From Card.as:640-750.
     */
    toPublicJSON() {
        let i = 0;
        const answer = {};
        answer.name = this.UIName;

        if (this.cardType === C.CARDTYPE_SPELL) {
            answer.spell = true;
        } else {
            answer.defaultBlocking = this.defaultBlocking;
            if (this.hasAbility) {
                answer.assignedBlocking = this.assignedBlocking;
            }
            answer.health = this.startingHealth;
            if (this.fragile) answer.fragile = true;
            if (this.undefendable) answer.frontline = true;
            if (this.lifespan !== -1) answer.lifespan = this.lifespan;
            if (this.healthGained > 0) answer.healthGained = this.healthGained;
        }

        answer.supply = this.rarity;
        if (this.rarity > 0) {
            answer.buyCost = this.buyCost.toPublicFacingString();
            if (this.buySac.length > 0) {
                answer.buySac = new Array(this.buySac.length);
                for (i = 0; i < this.buySac.length; i++) {
                    answer.buySac[i] = this.buySac[i].toPublicJSON();
                }
            }
            if (this.buyScript !== null) {
                answer.buyScript = this.buyScript.toPublicJSON();
            }
            answer.buildTime = this.buildTime;
        }

        if (this.beginOwnTurnScript !== null) {
            answer.startTurnScript = this.beginOwnTurnScript.toPublicJSON();
        }

        if (this.hasAbility) {
            if (!this.abilityCost.isEmpty) {
                answer.abilityCost = this.abilityCost.toPublicFacingString();
            }
            if (this.startingCharge > 0) {
                answer.stamina = this.startingCharge;
            }
            if (this.healthUsed > 0) {
                answer.healthCostToClick = this.healthUsed;
            }
            if (this.abilitySac.length > 0) {
                answer.abilitySac = new Array(this.abilitySac.length);
                for (i = 0; i < this.abilitySac.length; i++) {
                    answer.abilitySac[i] = this.abilitySac[i].toPublicJSON();
                }
            }
            if (this.abilityScript !== null) {
                answer.abilityScript = this.abilityScript.toPublicJSON();
            }
            if (this.abilityNetherfy) {
                answer.clickToDestroyNonblockingDrone = true;
            }
            if (this.targetAction === C.TARGETACTION_DISRUPT) {
                answer.targetAction = 'chill';
                answer.targetAmount = this.targetAmount;
            } else if (this.targetAction === C.TARGETACTION_SNIPE) {
                answer.targetAction = 'snipe';
                answer.targetCondition = this.condition;
            }
        }

        if (this.baseSet) {
            answer.baseSet = true;
        }

        return answer;
    }
}

// Color type constants
Card.COLOR_TYPE_GREEN = COLOR_TYPE_GREEN;
Card.COLOR_TYPE_BLUE = COLOR_TYPE_BLUE;
Card.COLOR_TYPE_RED = COLOR_TYPE_RED;
Card.COLOR_TYPE_WHITE = COLOR_TYPE_WHITE;

module.exports = Card;
