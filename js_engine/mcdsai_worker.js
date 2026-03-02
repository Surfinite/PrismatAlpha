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

// Suppress Emscripten output BEFORE loading MCDSAI.
// MCDSAI3441.js auto-initializes on require() and writes massive output via
// Module.print/printErr. With stdio:'ignore' (parent closes worker fds),
// these writes would fail on Windows and corrupt module state.
if (typeof globalThis.Module === 'undefined') globalThis.Module = {};
globalThis.Module.print = function() {};
globalThis.Module.printErr = function() {};

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
                // Emscripten may throw strings or numbers, not Error objects
                const errMsg = err instanceof Error ? err.message :
                    (typeof err === 'string' ? err.substring(0, 500) : String(err));
                process.send({ type: 'error', message: `Init failed: ${errMsg}` });
            }
            break;
        }

        case 'move': {
            try {
                if (!ai) {
                    process.send({ type: 'error', message: 'AI not initialized. Send init first.' });
                    return;
                }
                // Debug: capture Module.print output during getAIMove
                const debugOutput = [];
                globalThis.Module.print = function(text) { debugOutput.push(text); };
                globalThis.Module.printErr = function(text) { debugOutput.push('[ERR] ' + text); };

                const result = ai.getAIMove(msg.payload);

                // Restore suppression
                globalThis.Module.print = function() {};
                globalThis.Module.printErr = function() {};

                // Include debug info with move result
                const cleanResult = result.replace(/[\x00-\x1f]/g, ' ');
                let parsed;
                try { parsed = JSON.parse(cleanResult); } catch(e) { parsed = null; }
                const clickCount = parsed ? (parsed.aiclicks || []).length : -1;

                process.send({
                    type: 'move_result',
                    success: true,
                    result: result,
                    debug: {
                        payloadLength: msg.payload.length,
                        resultLength: result.length,
                        clickCount: clickCount,
                        mcdsaiOutput: debugOutput.slice(-10),
                        thinkTime: parsed ? parsed.aithinktime : -1
                    }
                });
            } catch (err) {
                const errMsg = err instanceof Error ? err.message :
                    (typeof err === 'string' ? err.substring(0, 500) : String(err));
                process.send({ type: 'error', message: `Move failed: ${errMsg}` });
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
