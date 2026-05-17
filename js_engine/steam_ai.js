'use strict';

/**
 * steam_ai.js — Manages Steam's PrismataAI.exe for use in the matchup runner.
 *
 * The Steam client's AI is a native C++ binary (PrismataAI.exe) that communicates
 * via stdin/stdout. Each turn receives a full JSON request:
 *   {"mergedDeck": [...], "gameState": {...}, "aiParameters": {...}, "aiPlayerName": "HardestAI"}
 * and responds with a newline-terminated JSON response containing aiclicks.
 *
 * Protocol (from AIThreadHandler.as):
 *   - Process is started fresh per game (killed + restarted)
 *   - Input is piped via stdin (originally chunked at 9KB, we write all at once)
 *   - Output is read from stdout until a newline is received
 *   - Response format matches MCDSAI: {"aiclicks": [...], "aithinktime": N, ...}
 */

const { spawn } = require('child_process');
const path = require('path');

const DEFAULT_EXE_PATH = path.resolve(
    'C:/Program Files (x86)/Steam/steamapps/common/Prismata/AI/PrismataAI.exe'
);

class SteamAI {
    /**
     * @param {string} label - Player label for logging
     * @param {Object} [options]
     * @param {string} [options.exePath] - Override path to PrismataAI.exe
     * @param {number} [options.timeout] - Response timeout in ms (default: 30000)
     */
    constructor(label, options) {
        options = options || {};
        this.label = label;
        this.exePath = options.exePath || DEFAULT_EXE_PATH;
        this.timeout = options.timeout || 30000;
        this._process = null;
    }

    /**
     * Start the AI process. Called once per game (process is restarted each game).
     */
    start() {
        this.stop();
        this._process = spawn(this.exePath, [], {
            stdio: ['pipe', 'pipe', 'ignore']
        });
        this._process.on('error', (err) => {
            console.error(`[SteamAI ${this.label}] Process error: ${err.message}`);
        });
        this._process.on('exit', (code) => {
            if (code !== null && code !== 0) {
                console.error(`[SteamAI ${this.label}] Process exited with code ${code}`);
            }
        });
    }

    /**
     * Stop the AI process.
     */
    stop() {
        if (this._process) {
            try { this._process.kill(); } catch (_) {}
            this._process = null;
        }
    }

    /**
     * Request an AI move. Sends the full request JSON via stdin and reads
     * the response from stdout (newline-terminated).
     *
     * @param {string} requestJson - Full JSON request string (mergedDeck + gameState + aiParameters + aiPlayerName)
     * @returns {Promise<Object>} Parsed response object with aiclicks, aithinktime, etc.
     */
    getMove(requestJson) {
        return new Promise((resolve, reject) => {
            // PrismataAI.exe is a one-shot process: it handles one request then exits.
            // Spawn a fresh process for each move request.
            this.stop();
            this._process = spawn(this.exePath, [], {
                stdio: ['pipe', 'pipe', 'pipe'],
                cwd: path.dirname(this.exePath)
            });
            let stderrBuf = '';
            this._process.stderr.on('data', (d) => {
                stderrBuf += d.toString();
                if (stderrBuf.length > 4096) stderrBuf = stderrBuf.slice(-4096);
            });
            this._lastStderr = () => stderrBuf;

            let outputBuffer = '';
            let resolved = false;

            const cleanup = () => {
                this.stop();
            };

            this._process.on('error', (err) => {
                if (!resolved) {
                    resolved = true;
                    reject(new Error(`[SteamAI ${this.label}] Process error: ${err.message}`));
                }
            });

            const timer = setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    const tail = (this._lastStderr ? this._lastStderr() : '').slice(-1500);
                    cleanup();
                    reject(new Error(`[SteamAI ${this.label}] Response timed out after ${this.timeout}ms\n--- last stderr ---\n${tail}\n--- end stderr ---`));
                }
            }, this.timeout);

            const onData = (data) => {
                outputBuffer += data.toString();
                // Response is newline-terminated (AIThreadHandler.as:628)
                const nlIdx = outputBuffer.indexOf('\n');
                if (nlIdx !== -1) {
                    clearTimeout(timer);
                    if (!resolved) {
                        resolved = true;
                        const responseStr = outputBuffer.substring(0, nlIdx);
                        cleanup();
                        try {
                            // Strip control characters (same as MCDSAI)
                            const clean = responseStr.replace(/[\x00-\x1f]/g, ' ').trim();
                            const response = JSON.parse(clean);
                            resolve(response);
                        } catch (err) {
                            reject(new Error(`[SteamAI ${this.label}] Invalid JSON response: ${err.message}\nRaw: ${responseStr.substring(0, 200)}`));
                        }
                    }
                }
            };

            this._process.stdout.on('data', onData);

            // Handle stdin errors (EPIPE if process exits before we finish writing)
            this._process.stdin.on('error', (err) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timer);
                    cleanup();
                    reject(new Error(`[SteamAI ${this.label}] stdin error: ${err.message}`));
                }
            });

            // Write the request to stdin (newline-terminated)
            const payload = requestJson.endsWith('\n') ? requestJson : requestJson + '\n';
            this._process.stdin.write(payload);
        });
    }
}

module.exports = SteamAI;
