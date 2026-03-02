'use strict';

const C = require('./C');

/**
 * Mana.js — Resource pool, transpiled from mcds/engine/Mana.as
 *
 * Represents a mana pool with 6 resource types.
 * String format: gold digits followed by mana letters.
 * Example: "6BGGG" = 6 gold + 1 blue + 3 green
 *
 * Internal mana letter mapping (NOT public-facing):
 *   H = Energy, G = Green, B = Blue, C = Red, A = Attack
 * Public-facing mapping (toPublicFacingString):
 *   E = Energy, G = Green, B = Blue, R = Red, X = Attack
 */

// Mana string constants (internal format)
const STRING_MANA_H = 'H';
const STRING_MANA_G = 'G';
const STRING_MANA_B = 'B';
const STRING_MANA_R = 'C';  // Red uses 'C' internally
const STRING_MANA_A = 'A';

class Mana {
    /**
     * @param {string} manaString - Mana string (e.g., "6BGGG", "3H", "0")
     */
    constructor(manaString) {
        // AS3 auto-coerces non-string args (e.g., number 1 → "1")
        if (typeof manaString !== 'string') {
            manaString = String(manaString == null ? '' : manaString);
        }

        // pool: [gold, green, blue, red, energy, attack]
        this.pool = new Array(C.MANA_NUMBER_OF);
        for (let i = 0; i < C.MANA_NUMBER_OF; i++) {
            this.pool[i] = 0;
        }

        // Parse leading digits as gold
        let counter = 0;
        while (counter < manaString.length) {
            if ('1234567890'.indexOf(manaString.charAt(counter)) === -1) {
                break;
            }
            counter++;
        }
        this.money = parseInt(manaString.substring(0, counter), 10) || 0;

        // Parse remaining characters as resource letters
        while (counter < manaString.length) {
            const ch = manaString.charAt(counter);
            if (ch === STRING_MANA_H) {
                this.pool[C.MANA_H]++;
            } else if (ch === STRING_MANA_G) {
                this.pool[C.MANA_G]++;
            } else if (ch === STRING_MANA_B) {
                this.pool[C.MANA_B]++;
            } else if (ch === STRING_MANA_R) {
                this.pool[C.MANA_R]++;
            } else if (ch === STRING_MANA_A) {
                this.attack++;
            }
            counter++;
        }
    }

    /** Get amount of a specific mana type */
    amountOf(manaType) {
        return this.pool[manaType];
    }

    /** Attack getter/setter (pool index MANA_A) */
    get attack() { return this.pool[C.MANA_A]; }
    set attack(value) { this.pool[C.MANA_A] = value | 0; }

    /** Gold getter/setter (pool index MANA_P) */
    get money() { return this.pool[C.MANA_P]; }
    set money(value) { this.pool[C.MANA_P] = value | 0; }

    /**
     * Check if this pool has enough of all resources in `mana`.
     * Returns the first mana type index that's insufficient, or -1 if all sufficient.
     * Checks in reverse order (attack first, then energy, red, blue, green, gold).
     */
    hasFailedWith(mana) {
        for (let i = C.MANA_NUMBER_OF - 1; i >= 0; i--) {
            if (this.pool[i] < mana.pool[i]) {
                return i;
            }
        }
        return -1;
    }

    /** Check if this pool has at least as much as `mana` in all types */
    has(mana) {
        return this.hasFailedWith(mana) === -1;
    }

    /** Add another mana pool to this one */
    add(change) {
        for (let i = 0; i < C.MANA_NUMBER_OF; i++) {
            this.pool[i] += change.pool[i];
        }
    }

    /** Subtract another mana pool from this one */
    subtract(change) {
        for (let i = 0; i < C.MANA_NUMBER_OF; i++) {
            this.pool[i] -= change.pool[i];
        }
    }

    /** Check if all resources are zero */
    get isEmpty() {
        for (let i = 0; i < C.MANA_NUMBER_OF; i++) {
            if (this.pool[i] > 0) {
                return false;
            }
        }
        return true;
    }

    /** Deep copy */
    clone() {
        return new Mana(this.toString());
    }

    /**
     * Serialize to internal string format.
     * Format: gold digits + H + G + B + C + A
     * Example: "6BGGG" (6 gold, 1 blue, 3 green)
     */
    toString() {
        let r = this.money === 0 ? '' : String(this.money);
        for (let i = 0; i < this.pool[C.MANA_H]; i++) r += STRING_MANA_H;
        for (let i = 0; i < this.pool[C.MANA_G]; i++) r += STRING_MANA_G;
        for (let i = 0; i < this.pool[C.MANA_B]; i++) r += STRING_MANA_B;
        for (let i = 0; i < this.pool[C.MANA_R]; i++) r += STRING_MANA_R;
        for (let i = 0; i < this.attack; i++) r += STRING_MANA_A;
        return r === '' ? '0' : r;
    }

    /**
     * Serialize to public-facing string format.
     * Replaces H→E, C→R, A→X for display.
     */
    toPublicFacingString() {
        let r = this.money === 0 ? '' : String(this.money);
        for (let i = 0; i < this.pool[C.MANA_H]; i++) r += 'E';
        for (let i = 0; i < this.pool[C.MANA_G]; i++) r += 'G';
        for (let i = 0; i < this.pool[C.MANA_B]; i++) r += 'B';
        for (let i = 0; i < this.pool[C.MANA_R]; i++) r += 'R';
        for (let i = 0; i < this.attack; i++) r += 'X';
        return r === '' ? '0' : r;
    }

    /**
     * HTML display for mana type.
     * From Mana.as:66-94. Not used in headless mode.
     */
    static manaTypeToHTML(manaType) {
        if (manaType === C.MANA_P) return '\u24DF'; // Ⓟ
        if (manaType === C.MANA_H) return '\u24BD'; // Ⓗ
        if (manaType === C.MANA_G) return '\u24BC'; // Ⓖ
        if (manaType === C.MANA_B) return '\u24B7'; // Ⓑ
        if (manaType === C.MANA_R) return '\u24B8'; // Ⓒ
        if (manaType === C.MANA_A) return '\u24B6'; // Ⓐ
        C.ASSERT(false, "Code shouldn't get here.");
        return '';
    }
}

// Export string constants for external use
Mana.STRING_MANA_H = STRING_MANA_H;
Mana.STRING_MANA_G = STRING_MANA_G;
Mana.STRING_MANA_B = STRING_MANA_B;
Mana.STRING_MANA_R = STRING_MANA_R;
Mana.STRING_MANA_A = STRING_MANA_A;

module.exports = Mana;
