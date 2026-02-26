'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * mcdsai_wrapper.js — Loads and wraps the Lunarch MCDSAI3441.js Emscripten module.
 *
 * The MCDSAI module is the official Master Bot AI from live Prismata (build 3441, Feb 2017).
 * It exposes two C++ functions via Emscripten cwrap:
 *   - CPPAI_JS_InitializeAI(jsonString) → statusString
 *   - CPPAI_JS_GetAIMove(jsonString) → moveJsonString
 *
 * Version pinning via SHA256 hash ensures we always use the exact known binary.
 */

const MCDSAI_PATH = path.resolve(__dirname, '../tmp_browser_client/MCDSAI3441.js');
const EXPECTED_HASH = 'a57e3bac052a826d17cae1c545bf46343f48071076a145abdc516970374bcbc1';

/**
 * Load and verify the MCDSAI module.
 *
 * @param {Object} [options]
 * @param {string} [options.modulePath] - Override path to MCDSAI3441.js
 * @param {boolean} [options.skipHashCheck] - Skip SHA256 verification (testing only)
 * @returns {{ initializeAI: Function, getAIMove: Function, Module: Object }}
 */
function loadMCDSAI(options) {
    options = options || {};
    const modulePath = options.modulePath || MCDSAI_PATH;

    // Version pin: SHA256 hash check
    if (!options.skipHashCheck) {
        const fileData = fs.readFileSync(modulePath);
        const actualHash = crypto.createHash('sha256').update(fileData).digest('hex');
        if (actualHash !== EXPECTED_HASH) {
            throw new Error(
                `MCDSAI version mismatch!\n` +
                `  Expected: ${EXPECTED_HASH}\n` +
                `  Actual:   ${actualHash}\n` +
                `  File:     ${modulePath}`
            );
        }
    }

    // Load the Emscripten module
    // MCDSAI3441.js auto-initializes on require() and exports Module
    const Module = require(modulePath);

    // Wrap the C++ functions with string marshalling via cwrap
    // Signature from AIworker3441.js: Module.cwrap(name, returnType, paramTypes)
    const initializeAI = Module.cwrap('CPPAI_JS_InitializeAI', 'string', ['string']);
    const getAIMove = Module.cwrap('CPPAI_JS_GetAIMove', 'string', ['string']);

    return {
        initializeAI,
        getAIMove,
        Module
    };
}

module.exports = {
    loadMCDSAI,
    MCDSAI_PATH,
    EXPECTED_HASH
};
