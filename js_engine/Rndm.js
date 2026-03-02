'use strict';

/**
 * Rndm.js — Deterministic PRNG, transpiled from mcds/engine/Rndm.as
 *
 * The AS3 version uses BitmapData.noise() which internally uses the
 * Park-Miller MINSTD (Lehmer RNG):
 *   seed = (seed * 16807) % 2147483647
 *
 * With BitmapData(1000, 200) and channelOptions = 1|2|4|8 (all ARGB),
 * noise() generates 200,000 pixels. Each pixel advances the RNG 4 times
 * (once per channel: R, G, B, A). getPixel32() returns ARGB packed uint32.
 *
 * The pointer cycles through 200,000 pixels, reading sequentially.
 *
 * Algorithm verified against Ruffle (Rust) and Lightspark (C++) Flash emulators.
 * Both confirm Park-Miller with a=16807, m=2^31-1.
 *
 * JS Number handles the multiplication correctly since max product (~3.6e13)
 * is within Number.MAX_SAFE_INTEGER (9e15).
 */

const BITMAP_WIDTH = 1000;
const BITMAP_HEIGHT = 200;
const BITMAP_SIZE = BITMAP_WIDTH * BITMAP_HEIGHT;  // 200,000 pixels

/**
 * Park-Miller MINSTD PRNG step.
 * @param {{value: number}} seedRef - Mutable seed reference
 * @returns {number} Next random value (1 to 2^31-2)
 */
function lehmerRandom(seedRef) {
    seedRef.value = (seedRef.value * 16807) % 2147483647;
    return seedRef.value;
}

/**
 * Generate the full pixel buffer matching BitmapData.noise(seed, 0, 255, 15).
 * Returns Uint32Array of 200,000 ARGB pixel values.
 */
function generatePixels(seed) {
    // Seed initialization: AS3 handles negative/zero seeds
    let trueSeed = seed <= 0 ? (-seed + 1) : seed;
    const rng = { value: trueSeed };

    const pixels = new Uint32Array(BITMAP_SIZE);

    for (let y = 0; y < BITMAP_HEIGHT; y++) {
        for (let x = 0; x < BITMAP_WIDTH; x++) {
            // All 4 channels enabled (channelOptions = 15 = 1|2|4|8)
            // Range: low=0, high=255, so range+1 = 256
            const r = lehmerRandom(rng) % 256;
            const g = lehmerRandom(rng) % 256;
            const b = lehmerRandom(rng) % 256;
            const a = lehmerRandom(rng) % 256;

            // Pack as ARGB uint32 (same as getPixel32 return format)
            pixels[y * BITMAP_WIDTH + x] = ((a << 24) | (r << 16) | (g << 8) | b) >>> 0;
        }
    }

    return pixels;
}

class Rndm {
    /**
     * @param {number} [seed=0] - Initial seed (uint)
     */
    constructor(seed) {
        this._seed = (seed !== undefined) ? (seed >>> 0) : 0;
        this._pointer = 0;
        this._pixels = null;    // Lazy-generated pixel buffer
        this._seedInvalid = true;
    }

    // --- Instance property accessors ---

    get seed() { return this._seed; }
    set seed(value) {
        value = value >>> 0;
        if (value !== this._seed) {
            this._seedInvalid = true;
            this._pointer = 0;
        }
        this._seed = value;
    }

    get pointer() { return this._pointer; }
    set pointer(value) { this._pointer = value; }

    /**
     * Core random function — returns float in [0, 1).
     * Matches Rndm.as:114-123 exactly.
     */
    random() {
        if (this._seedInvalid) {
            this._pixels = generatePixels(this._seed);
            this._seedInvalid = false;
        }

        this._pointer = (this._pointer + 1) % BITMAP_SIZE;

        const pixel = this._pixels[this._pointer];
        // AS3: (bmpd.getPixel32(...) * 0.999999999999998 + 1e-15) / 4294967295
        return (pixel * 0.999999999999998 + 1e-15) / 4294967295;
    }

    /**
     * Random float in [min, max).
     * If only one arg, returns [0, min).
     */
    float(min, max) {
        if (max === undefined || max !== max) {  // isNaN check
            max = min;
            min = 0;
        }
        return this.random() * (max - min) + min;
    }

    /** Random boolean with given probability */
    boolean(chance) {
        if (chance === undefined) chance = 0.5;
        return this.random() < chance;
    }

    /** Random sign: 1 or -1 */
    sign(chance) {
        if (chance === undefined) chance = 0.5;
        return this.random() < chance ? 1 : -1;
    }

    /** Random bit: 1 or 0 */
    bit(chance) {
        if (chance === undefined) chance = 0.5;
        return this.random() < chance ? 1 : 0;
    }

    /**
     * Random integer in [min, max).
     * If only one arg, returns [0, min).
     */
    integer(min, max) {
        if (max === undefined || max !== max) {
            max = min;
            min = 0;
        }
        return Math.floor(this.float(min, max));
    }

    /** Reset pointer to 0 */
    reset() {
        this._pointer = 0;
    }

    // --- Static singleton interface (mirrors AS3 static methods) ---

    static get instance() {
        if (!Rndm._instance) {
            Rndm._instance = new Rndm();
        }
        return Rndm._instance;
    }

    static get seed() { return Rndm.instance.seed; }
    static set seed(value) { Rndm.instance.seed = value; }

    static get pointer() { return Rndm.instance.pointer; }
    static set pointer(value) { Rndm.instance.pointer = value; }

    static random() { return Rndm.instance.random(); }
    static float(min, max) { return Rndm.instance.float(min, max); }
    static boolean(chance) { return Rndm.instance.boolean(chance); }
    static sign(chance) { return Rndm.instance.sign(chance); }
    static bit(chance) { return Rndm.instance.bit(chance); }
    static integer(min, max) { return Rndm.instance.integer(min, max); }
    static reset() { Rndm.instance.reset(); }
}

Rndm._instance = null;

module.exports = Rndm;
