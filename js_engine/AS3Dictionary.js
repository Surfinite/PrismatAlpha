'use strict';

/**
 * AS3Dictionary — JavaScript wrapper guaranteeing deterministic iteration order
 * matching ActionScript 3 Dictionary semantics.
 *
 * AS3 Dictionary iterates in insertion order. JavaScript Map also iterates in
 * insertion order, so Map is the natural backing store.
 *
 * AS3 iteration conventions:
 *   for (key in dict)      → iterates KEYS   → use forIn() or keys()
 *   for each (val in dict) → iterates VALUES  → use forEach() or values()
 *
 * All AS3 null values map to JS null, never undefined (per transpilation conventions).
 */
class AS3Dictionary {
    constructor() {
        this._map = new Map();
    }

    /** Set a key-value pair (AS3: dict[key] = value) */
    set(key, value) {
        this._map.set(key, value);
    }

    /** Get value by key (AS3: dict[key]). Returns null if not found. */
    get(key) {
        if (this._map.has(key)) {
            return this._map.get(key);
        }
        return null;
    }

    /** Check if key exists (AS3: key in dict) */
    has(key) {
        return this._map.has(key);
    }

    /** Delete a key (AS3: delete dict[key]) */
    delete(key) {
        return this._map.delete(key);
    }

    /** Number of entries */
    get length() {
        return this._map.size;
    }

    /** Iterate keys — equivalent to AS3 "for (key in dict)" */
    keys() {
        return this._map.keys();
    }

    /** Iterate values — equivalent to AS3 "for each (val in dict)" */
    values() {
        return this._map.values();
    }

    /** Iterate entries as [key, value] pairs */
    entries() {
        return this._map.entries();
    }

    /**
     * AS3 "for (key in dict)" pattern.
     * Callback: (key, value) => void
     */
    forIn(callback) {
        for (const [key, value] of this._map) {
            callback(key, value);
        }
    }

    /**
     * AS3 "for each (val in dict)" pattern.
     * Callback: (value, key) => void
     */
    forEach(callback) {
        for (const [key, value] of this._map) {
            callback(value, key);
        }
    }

    /** Convert to plain object (for JSON serialization) */
    toObject() {
        const obj = {};
        for (const [key, value] of this._map) {
            obj[key] = value;
        }
        return obj;
    }

    /** Create from plain object */
    static fromObject(obj) {
        const dict = new AS3Dictionary();
        for (const key of Object.keys(obj)) {
            dict.set(key, obj[key]);
        }
        return dict;
    }

    /** Create from array of [key, value] pairs */
    static fromEntries(entries) {
        const dict = new AS3Dictionary();
        for (const [key, value] of entries) {
            dict.set(key, value);
        }
        return dict;
    }
}

module.exports = AS3Dictionary;
