'use strict';

const C = require('./C');

/**
 * Order.js — Move/undo representation, transpiled from mcds/engine/Order.as
 *
 * Represents a single atomic game action (assign, buy, defend, etc.)
 * with its inverse for undo support.
 */
class Order {
    /**
     * @param {string} type - Move type (C.MOVE_ASSIGN, C.MOVE_BUY, etc.)
     * @param {number} [instId=-1] - Target instance ID
     * @param {number} [targetId=-1] - Secondary target (for two-step abilities)
     * @param {number} [cardId=-1] - Card type index (for BUY)
     * @param {Array[]|null} [buyCreateIds=null] - IDs of units created by buy
     * @param {Array[]|null} [abilityCreateIds=null] - IDs of units created by ability
     */
    constructor(type, instId, targetId, cardId, buyCreateIds, abilityCreateIds) {
        this.type = type;
        this.instId = (instId !== undefined) ? (instId | 0) : -1;
        this.targetId = (targetId !== undefined) ? (targetId | 0) : -1;
        this.cardId = (cardId !== undefined) ? (cardId | 0) : -1;
        this.buyCreateIds = (buyCreateIds !== undefined) ? buyCreateIds : null;
        this.abilityCreateIds = (abilityCreateIds !== undefined) ? abilityCreateIds : null;
    }

    /**
     * Returns the inverse Order for undo.
     * From Order.as:29-85.
     */
    inverse() {
        let inverseType = null;

        if (this.type === C.MOVE_ASSIGN) {
            inverseType = C.MOVE_UNASSIGN;
        } else if (this.type === C.MOVE_UNASSIGN) {
            inverseType = C.MOVE_ASSIGN;
        } else if (this.type === C.MOVE_BUY) {
            inverseType = C.MOVE_SELL;
        } else if (this.type === C.MOVE_SELL) {
            inverseType = C.MOVE_BUY;
        } else if (this.type === C.MOVE_MELEE) {
            inverseType = C.MOVE_UNMELEE;
        } else if (this.type === C.MOVE_UNMELEE) {
            inverseType = C.MOVE_MELEE;
        } else if (this.type === C.MOVE_DEFEND) {
            inverseType = C.MOVE_UNDEFEND;
        } else if (this.type === C.MOVE_UNDEFEND) {
            inverseType = C.MOVE_DEFEND;
        } else if (this.type === C.MOVE_BREACH_OR_OVERKILL) {
            inverseType = C.MOVE_UNBREACH_OR_UNOVERKILL;
        } else if (this.type === C.MOVE_UNBREACH_OR_UNOVERKILL) {
            inverseType = C.MOVE_BREACH_OR_OVERKILL;
        } else if (this.type === C.MOVE_WIPEOUT) {
            inverseType = C.MOVE_UNWIPEOUT;
        } else if (this.type === C.MOVE_UNWIPEOUT) {
            inverseType = C.MOVE_WIPEOUT;
        } else {
            C.ASSERT(false, 'Tried to take inverse of Move with no inverse.');
        }

        return new Order(inverseType, this.instId, this.targetId,
            this.cardId, this.buyCreateIds, this.abilityCreateIds);
    }
}

module.exports = Order;
