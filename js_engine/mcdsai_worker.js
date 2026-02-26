'use strict';

/**
 * mcdsai_worker.js — Child process wrapper for MCDSAI isolation.
 *
 * Emscripten's global state means a single process can only serve one AI
 * player at a time. For self-play (two AI players), we fork separate
 * child processes, each loading its own MCDSAI module.
 *
 * Communication via Node.js IPC (process.send / process.on('message')):
 *   Parent → Worker: { type: 'init', payload: jsonString }
 *   Parent → Worker: { type: 'move', payload: jsonString }
 *   Worker → Parent: { type: 'init_result', success: true, result: string }
 *   Worker → Parent: { type: 'move_result', success: true, result: string }
 *   Worker → Parent: { type: 'error', message: string }
 *   Parent → Worker: { type: 'exit' }
 */

const { loadMCDSAI } = require('./mcdsai_wrapper');

let ai = null;

function handleMessage(msg) {
    if (!msg || !msg.type) {
        process.send({ type: 'error', message: 'Invalid message: missing type' });
        return;
    }

    switch (msg.type) {
        case 'init': {
            try {
                if (!ai) {
                    ai = loadMCDSAI({ skipHashCheck: msg.skipHashCheck || false });
                }
                const result = ai.initializeAI(msg.payload);
                process.send({ type: 'init_result', success: true, result: result });
            } catch (err) {
                process.send({ type: 'error', message: `Init failed: ${err.message}` });
            }
            break;
        }

        case 'move': {
            try {
                if (!ai) {
                    process.send({ type: 'error', message: 'AI not initialized. Send init first.' });
                    return;
                }
                const result = ai.getAIMove(msg.payload);
                process.send({ type: 'move_result', success: true, result: result });
            } catch (err) {
                process.send({ type: 'error', message: `Move failed: ${err.message}` });
            }
            break;
        }

        case 'exit': {
            process.exit(0);
            break;
        }

        default: {
            process.send({ type: 'error', message: `Unknown message type: ${msg.type}` });
        }
    }
}

process.on('message', handleMessage);

// Signal ready
process.send({ type: 'ready' });
