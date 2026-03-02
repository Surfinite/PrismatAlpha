'use strict';

/**
 * Click.js — Click event data class, transpiled from mcds/engine/Click.as
 *
 * Represents a single user/AI click action.
 */
class Click {
    /**
     * @param {string} type - Click type (C.CLICK_INST, C.CLICK_CARD, etc.)
     * @param {number} [id=-1] - Card index or instance ID
     * @param {Object} [params=null] - Optional extra data
     */
    constructor(type, id, params) {
        this._type = type;
        this._id = (id !== undefined) ? (id | 0) : -1;
        this._params = (params !== undefined) ? params : null;
    }
}

module.exports = Click;
