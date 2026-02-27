'use strict';

/**
 * cpp_suggest_worker.js — Wraps C++ Prismata_Testing.exe --suggest as a per-turn AI worker.
 *
 * Mirrors the MCDSAIWorker interface so it can be used interchangeably in the
 * game loop. Each getAIMove() call:
 *   1. Exports game state to F6-format JSON via stateToSuggestJSON()
 *   2. Writes to a temp file
 *   3. Spawns Prismata_Testing.exe --suggest <file> --player <name> --think-time <ms>
 *   4. Parses stdout JSON response
 *   5. Returns response in MCDSAI-compatible format
 *
 * Process overhead is ~200-300ms per turn (spawn + weight load + JSON parse).
 * At 7s think time this is ~4% overhead — acceptable for benchmarking.
 *
 * CLI reference: source/testing/main.cpp:120-128
 * Output format: source/testing/Benchmarks.cpp:1020-1043
 */

const { execFile } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { stateToSuggestJSON } = require('./suggest_adapter');

class CppSuggestWorker {
    /**
     * @param {Object} [options]
     * @param {string} [options.exePath] - Path to Prismata_Testing.exe
     * @param {string} [options.playerName] - C++ player definition name from config.txt
     * @param {number} [options.thinkTime] - Think time in ms
     * @param {string} [options.label] - Label for logging
     */
    constructor(options = {}) {
        this.exePath = options.exePath || path.resolve(__dirname, '../bin/Prismata_Testing.exe');
        this.playerName = options.playerName || 'OriginalHardestAI';
        this.thinkTime = options.thinkTime || 7000;
        this.label = options.label || 'C++';
        this.mergedDeck = null;
        this._turnCount = 0;
    }

    /**
     * No-op — C++ worker is stateless (new process per turn).
     * @returns {Promise<void>}
     */
    async spawn() {
        // Verify exe exists at startup
        if (!fs.existsSync(this.exePath)) {
            throw new Error(`C++ exe not found: ${this.exePath}`);
        }
        console.error(`CppSuggestWorker: exe=${this.exePath} player=${this.playerName} think=${this.thinkTime}ms`);
    }

    /**
     * Store mergedDeck for later state exports.
     * NOTE: This worker does NOT share the MCDSAIWorker interface exactly.
     * The orchestrator (matchup_main.js) has separate code paths for each AI type.
     * @param {string} initJson - JSON string: {mergedDeck, aiParameters}
     * @returns {Promise<void>}
     */
    async initializeAI(initJson) {
        const parsed = JSON.parse(initJson);
        this.mergedDeck = parsed.mergedDeck;
        this._turnCount = 0;
    }

    /**
     * Get AI move by spawning C++ --suggest process.
     *
     * @param {State} state - JS engine State object
     * @param {Object[]} mergedDeck - Card definitions (overrides stored deck if provided)
     * @returns {Promise<Object>} Response with { ok, clicks, think_ms, eval, ... }
     */
    async getAIMove(state, mergedDeck) {
        const deck = mergedDeck || this.mergedDeck;
        if (!deck) {
            throw new Error('CppSuggestWorker: mergedDeck not set — call initializeAI() first');
        }

        this._turnCount++;

        // 1. Build suggest JSON
        const suggestJSON = stateToSuggestJSON(state, deck);
        const jsonStr = JSON.stringify(suggestJSON);

        // 2. Write to temp file (unique name to prevent conflicts)
        const tmpFile = path.join(os.tmpdir(), `prismata_suggest_${process.pid}_${this._turnCount}.json`);

        try {
            fs.writeFileSync(tmpFile, jsonStr, 'utf8');

            // 3. Spawn exe with timeout (think time + 10s buffer for init overhead)
            const timeout = this.thinkTime + 10000;
            const args = [
                '--suggest', tmpFile,
                '--player', this.playerName,
                '--think-time', String(this.thinkTime)
            ];

            const result = await new Promise((resolve, reject) => {
                execFile(this.exePath, args, {
                    timeout: timeout,
                    maxBuffer: 10 * 1024 * 1024, // 10MB buffer
                    cwd: path.dirname(this.exePath),  // Run from bin/ so config.txt is found
                    windowsHide: true
                }, (error, stdout, stderr) => {
                    if (error) {
                        if (error.killed) {
                            reject(new Error(`C++ process timed out after ${timeout}ms`));
                        } else {
                            reject(new Error(`C++ process error: ${error.message}`));
                        }
                        return;
                    }
                    resolve(stdout.trim());
                });
            });

            // 4. Parse stdout JSON — C++ exe outputs init noise (card counts, NeuralNet
            //    mapping) to stdout before the JSON line. Extract the line starting with '{'.
            if (!result) {
                console.error(`CppSuggestWorker turn ${this._turnCount}: empty stdout`);
                return { ok: false, clicks: [], think_ms: 0 };
            }

            const lines = result.split('\n');
            const jsonLine = lines.find(l => l.trimStart().startsWith('{'));
            if (!jsonLine) {
                console.error(`CppSuggestWorker turn ${this._turnCount}: no JSON in stdout: ${result.substring(0, 200)}`);
                return { ok: false, clicks: [], think_ms: 0 };
            }

            const response = JSON.parse(jsonLine.trim());

            if (!response.ok) {
                console.error(`CppSuggestWorker turn ${this._turnCount}: ok=false — ${response.error || 'unknown error'}`);
                return { ok: false, clicks: [], think_ms: 0 };
            }

            return response;

        } finally {
            // 5. Always clean up temp file
            try {
                fs.unlinkSync(tmpFile);
            } catch (e) {
                // Ignore cleanup errors
            }
        }
    }

    /**
     * No-op — no persistent process to terminate.
     */
    terminate() {
        // Nothing to do — each call spawns and exits
    }
}

module.exports = CppSuggestWorker;
