'use strict';

/**
 * mcdsai_manager.js — Manages MCDSAI worker processes for self-play.
 *
 * Provides async API for initializing AI and requesting moves via
 * isolated child processes. Each worker loads its own copy of MCDSAI3441.js.
 */

const { fork } = require('child_process');
const path = require('path');

const WORKER_PATH = path.resolve(__dirname, 'mcdsai_worker.js');

class MCDSAIWorker {
    /**
     * @param {string} label - Player label for logging (e.g., "P1", "P2")
     */
    constructor(label) {
        this.label = label;
        this._process = null;
        this._pendingCallbacks = new Map();
        this._nextId = 0;
        this._ready = false;
    }

    /**
     * Spawn the worker process.
     * @returns {Promise<void>} Resolves when worker signals ready.
     */
    spawn() {
        return new Promise((resolve, reject) => {
            this._process = fork(WORKER_PATH, [], {
                // Use 'ignore' for stdout/stderr to prevent Emscripten's massive
                // Module.print output from filling pipe buffers and blocking.
                // All meaningful communication happens via IPC.
                stdio: ['ignore', 'ignore', 'ignore', 'ipc']
            });

            this._process.on('message', (msg) => {
                if (msg.type === 'ready') {
                    this._ready = true;
                    resolve();
                    return;
                }
                this._handleResponse(msg);
            });

            this._process.on('error', (err) => {
                reject(new Error(`Worker ${this.label} process error: ${err.message}`));
            });

            this._process.on('exit', (code) => {
                // If process exits before 'ready' was received, reject the spawn promise
                if (!this._ready) {
                    reject(new Error(`Worker ${this.label} exited before ready (code ${code})`));
                }
                this._ready = false;
                // Reject any pending callbacks
                for (const [, cb] of this._pendingCallbacks) {
                    cb.reject(new Error(`Worker ${this.label} exited with code ${code}`));
                }
                this._pendingCallbacks.clear();
                // Clear kill timer if set
                if (this._killTimer) {
                    clearTimeout(this._killTimer);
                    this._killTimer = null;
                }
            });
        });
    }

    /**
     * Initialize the AI with mergedDeck + aiParameters.
     * @param {string} initJson - JSON string: {mergedDeck, aiParameters}
     * @returns {Promise<string>} Init status string from MCDSAI
     */
    initializeAI(initJson) {
        return this._sendAndWait('init', initJson, 'init_result', { skipHashCheck: true });
    }

    /**
     * Request an AI move for the current game state.
     * @param {string} moveJson - JSON string: {gameState, aiPlayerName}
     * @returns {Promise<string>} Move response JSON string from MCDSAI
     */
    getAIMove(moveJson) {
        return this._sendAndWait('move', moveJson, 'move_result');
    }

    /**
     * Gracefully terminate the worker.
     */
    terminate() {
        if (this._process) {
            this._process.send({ type: 'exit' });
            // Force kill after 5s if still alive
            this._killTimer = setTimeout(() => {
                if (this._process && !this._process.killed) {
                    this._process.kill('SIGKILL');
                }
                this._killTimer = null;
            }, 5000);
        }
    }

    /** @private */
    _sendAndWait(type, payload, expectedResponseType, extra) {
        return new Promise((resolve, reject) => {
            if (!this._ready) {
                reject(new Error(`Worker ${this.label} not ready`));
                return;
            }

            const id = this._nextId++;
            this._pendingCallbacks.set(expectedResponseType, { resolve, reject, id });

            const msg = { type: type, payload: payload };
            if (extra) Object.assign(msg, extra);
            this._process.send(msg);
        });
    }

    /** @private */
    _handleResponse(msg) {
        if (msg.type === 'error') {
            // Error responses reject the most recent pending callback
            for (const [key, cb] of this._pendingCallbacks) {
                cb.reject(new Error(msg.message));
                this._pendingCallbacks.delete(key);
                return;
            }
            console.error(`Worker ${this.label} error (no pending callback): ${msg.message}`);
            return;
        }

        const cb = this._pendingCallbacks.get(msg.type);
        if (cb) {
            this._pendingCallbacks.delete(msg.type);
            if (msg.success) {
                // Log debug info if present
                if (msg.debug) {
                    console.error(`Worker ${this.label} debug: clicks=${msg.debug.clickCount} think=${msg.debug.thinkTime}ms payload=${msg.debug.payloadLength}b`);
                    if (msg.debug.mcdsaiOutput && msg.debug.mcdsaiOutput.length > 0) {
                        for (const line of msg.debug.mcdsaiOutput) {
                            console.error(`  MCDSAI: ${line}`);
                        }
                    }
                }
                cb.resolve(msg.result);
            } else {
                cb.reject(new Error(msg.message || 'Unknown error'));
            }
        }
    }
}

module.exports = MCDSAIWorker;
