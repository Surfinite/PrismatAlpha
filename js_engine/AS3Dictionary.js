'use strict';

/**
 * AS3Dictionary — faithful port of AVM2 (Adobe Tamarin / avmplus) `InlineHashtable`
 * iteration order for INTEGER keys.
 *
 * The engine's `State.table` is a `flash.utils.Dictionary` keyed by integer instId. AS3
 * `for (t in dict)` / `for each (v in dict)` over an int-keyed Dictionary iterates in the
 * hash table's PHYSICAL-SLOT order — NOT insertion order and NOT numeric order. That order
 * decides the sequence in which units run their begin-turn `create` scripts during swoosh,
 * and therefore which instId each created token receives. Backing this with a JS Map
 * (insertion order) silently mis-assigns token instIds, so a later recorded click lands on
 * the wrong card (begin-turn-token-swap bug; see docs/scratch faithfulness campaign).
 *
 * Algorithm transcribed from avmplus `core/avmplusHashtable.cpp` (find / isFull / grow /
 * rehash / deletePairAt / two-pass next) and `core/atom*.h` (int atom = (n<<3)|6):
 *   - entries stored as adjacent (keyAtom, value) pairs in a flat array; capacity counts atoms
 *   - fresh capacity = 4 atoms (kDefaultCapacity=2 -> *2); load factor 0.80; grow x2 with rehash
 *   - int key n -> atom (n<<3)|6; bucket = ((0x7FFFFFF8 & atom) >> 2) & ((cap-1)&~1) = (2n)&mask
 *   - quadratic probe: n0=14, n+=2, i=(i+n)&mask; stops at the key or first EMPTY (skips DELETED)
 *   - delete writes a DELETED tombstone (skipped on iterate, lengthens probe chains)
 *   - for-in emits integer keys in ascending physical-slot order
 * Validated against game evidence ({62,148} -> [148,62]) and AS3 F6 oracle dumps.
 *
 * Keys are integers (instId). Values are arbitrary JS objects (Inst). All AS3 null values
 * map to JS null. Used only for State.table (the sole int-keyed Dictionary instance).
 */

const EMPTY = 0;       // atomNotFound
const DELETED = 4;     // undefinedAtom (tombstone)
const KIND_INT = 6;    // kIntptrType

function intAtom(n) { return (n << 3) | KIND_INT; }       // valid for small non-negative instIds
function nextPow2(x) { let p = 1; while (p < x) p <<= 1; return p; }

class AS3Dictionary {
    constructor() {
        // initialize(kDefaultCapacity=2): cap = nextPow2(2)=2; setCapacity(cap*2) => 4 atoms (2 entry slots)
        this._atoms = [EMPTY, EMPTY, EMPTY, EMPTY];
        this._cap = 4;            // atom-capacity (entry slots = cap/2)
        this._occupied = 0;       // live + tombstone slots (drives isFull / grow timing; matches avmplus m_size)
        this._count = 0;          // live entries (for length)
        this._hasDeleted = false;
    }

    // Returns the even slot index holding key atom x, or the first EMPTY slot in its probe chain.
    _find(x) {
        const t = this._atoms;
        const bitmask = (this._cap - 1) & ~1;
        let i = ((0x7FFFFFF8 & x) >>> 2) & bitmask;
        let n = 7 << 1;                                  // 14
        let k;
        while ((k = t[i]) !== x && k !== EMPTY) {        // NB: does not stop on DELETED
            n += 2;
            i = (i + n) & bitmask;
        }
        return i;
    }

    _isFull() { return (5 * (this._occupied + 1)) >= (2 * this._cap); }

    _grow() {
        const oldAtoms = this._atoms;
        const oldCap = this._cap;
        // grow x2 normally; if there are tombstones, rehash at same capacity to purge them.
        const newCap = this._hasDeleted ? oldCap : nextPow2(oldCap + 1);
        this._atoms = new Array(newCap).fill(EMPTY);
        this._cap = newCap;
        let live = 0;
        for (let j = 0; j < oldCap; j += 2) {
            const a = oldAtoms[j];
            if (a !== EMPTY && a !== DELETED) {
                const p = this._find(a);
                this._atoms[p] = a;
                this._atoms[p + 1] = oldAtoms[j + 1];
                live++;
            }
        }
        this._occupied = live;       // tombstones purged
        this._count = live;
        this._hasDeleted = false;
    }

    /** Set a key-value pair (AS3: dict[key] = value). */
    set(key, value) {
        const x = intAtom(key);
        const i = this._find(x);
        if (this._atoms[i] !== x) {
            this._atoms[i] = x;
            this._atoms[i + 1] = value;
            this._occupied++;
            this._count++;
            if (this._isFull()) this._grow();
        } else {
            this._atoms[i + 1] = value;
        }
    }

    /** Get value by key (AS3: dict[key]). Returns null if not found. */
    get(key) {
        const x = intAtom(key);
        const i = this._find(x);
        return this._atoms[i] === x ? this._atoms[i + 1] : null;
    }

    /** Check if key exists (AS3: key in dict). */
    has(key) {
        const x = intAtom(key);
        return this._atoms[this._find(x)] === x;
    }

    /** Delete a key (AS3: delete dict[key]). Writes a tombstone; slot stays occupied. */
    delete(key) {
        const x = intAtom(key);
        const i = this._find(x);
        if (this._atoms[i] === x) {
            this._atoms[i] = DELETED;
            this._atoms[i + 1] = DELETED;
            this._hasDeleted = true;
            this._count--;
            return true;
        }
        return false;
    }

    /** Number of live entries. */
    get length() { return this._count; }

    // Physical-slot iteration (AVM2 for-in order for integer keys). All non-int handling is
    // unnecessary: State.table is exclusively int-keyed.
    _orderedEntries() {
        const out = [];
        const t = this._atoms;
        for (let i = 0; i < this._cap; i += 2) {
            const a = t[i];
            if (a !== EMPTY && a !== DELETED) out.push([a >> 3, t[i + 1]]);
        }
        return out;
    }

    /** Iterate keys — AS3 "for (key in dict)". Returns an iterable of keys in AVM2 order. */
    keys() { return this._orderedEntries().map(e => e[0]); }

    /** Iterate values — AS3 "for each (val in dict)". */
    values() { return this._orderedEntries().map(e => e[1]); }

    /** Iterate entries as [key, value] pairs in AVM2 order. */
    entries() { return this._orderedEntries(); }

    /** AS3 "for (key in dict)" — callback: (key, value) => void. */
    forIn(callback) { for (const [k, v] of this._orderedEntries()) callback(k, v); }

    /** AS3 "for each (val in dict)" — callback: (value, key) => void. */
    forEach(callback) { for (const [k, v] of this._orderedEntries()) callback(v, k); }

    /** Convert to plain object (for JSON serialization). Keys become string instIds. */
    toObject() {
        const obj = {};
        for (const [k, v] of this._orderedEntries()) obj[k] = v;
        return obj;
    }

    /** Create from plain object (numeric-string keys -> int). */
    static fromObject(obj) {
        const dict = new AS3Dictionary();
        for (const key of Object.keys(obj)) dict.set(Number(key), obj[key]);
        return dict;
    }

    /** Create from array of [key, value] pairs. */
    static fromEntries(entries) {
        const dict = new AS3Dictionary();
        for (const [key, value] of entries) dict.set(Number(key), value);
        return dict;
    }
}

module.exports = AS3Dictionary;
