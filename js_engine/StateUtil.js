'use strict';

/**
 * StateUtil.js — Utility functions for state comparison and click conversion.
 * Transpiled from mcds/engine/StateUtil.as (156 lines).
 *
 * Key function: convertToClicks() bridges MCDSAI AI output to engine clicks.
 */

const C = require('./C');
const Click = require('./Click');
const Analyzer = require('./Analyzer');

class StateUtil {
    /**
     * Convert MCDSAI click output into engine-compatible Click objects.
     * Creates a temporary Analyzer, applies each click to validate and resolve IDs.
     *
     * @param {Array} clickObject - Array of {type, args} from MCDSAI response
     * @param {State} s - Current game state
     * @param {boolean} [daveAI=false] - If true, auto-inject end-swipe between clicks
     * @returns {Click[]} Array of resolved Click objects
     */
    static convertToClicks(clickObject, s, daveAI) {
        if (daveAI === undefined) daveAI = false;

        const tempAnalyzer = Analyzer.analyzerFromState(s);
        const tempClicks = [];
        let id = 0;

        for (let i = 0; i < clickObject.length; i++) {
            // Auto end-swipe for daveAI (MCDSAI doesn't emit end-swipe clicks)
            if (tempAnalyzer.controller.inSwipe && daveAI) {
                tempClicks.push(new Click(C.CLICK_END_SWIPE));
                tempAnalyzer.noUpdateClick(C.CLICK_END_SWIPE);
            }

            if (clickObject[i].type === C.CLICK_INST) {
                id = StateUtil.findInstId(clickObject[i].args, tempAnalyzer);
                if (id === -1) {
                    throw new Error('**WARNING**: Isomorphic Inst Not Found on click ' + i +
                        ': ' + JSON.stringify(clickObject[i]));
                }
                if (!tempAnalyzer.analyzerCanClick(clickObject[i].type, id)) {
                    throw new Error('**WARNING**: Illegal Inst click imminent on click ' + i +
                        ': ' + JSON.stringify(clickObject[i]));
                }
                tempClicks.push(new Click(clickObject[i].type, id));
                tempAnalyzer.noUpdateClick(clickObject[i].type, id);
            } else if (clickObject[i].type === C.CLICK_INST_SHIFT) {
                id = StateUtil.findInstId(clickObject[i].args, tempAnalyzer);
                if (id !== -1) {
                    tempClicks.push(new Click(clickObject[i].type, id));
                    tempAnalyzer.noUpdateClick(clickObject[i].type, id);
                }
            } else if (clickObject[i].type === C.CLICK_CARD || clickObject[i].type === C.CLICK_CARD_SHIFT) {
                const cardId = tempAnalyzer.gameState.cardNameToCard(clickObject[i].args).cardId;
                if (!tempAnalyzer.analyzerCanClick(clickObject[i].type, cardId)) {
                    throw new Error('**WARNING**: Cannot click buy card: ' +
                        JSON.stringify(clickObject[i]));
                }
                tempClicks.push(new Click(clickObject[i].type, cardId));
                tempAnalyzer.noUpdateClick(clickObject[i].type, cardId);
            } else if (clickObject[i].type === C.CLICK_SPACE) {
                tempClicks.push(new Click(clickObject[i].type));
                tempAnalyzer.noUpdateClick(clickObject[i].type, -1);
            } else {
                // Unknown click type — pass through
                tempClicks.push(new Click(clickObject[i].type));
                tempAnalyzer.noUpdateClick(clickObject[i].type, -1);
            }
        }

        return tempClicks;
    }

    /**
     * Compare two supply/bought vectors using card names as keys.
     * Used to check if two states have equivalent supply distributions.
     *
     * @param {number[]} vector1
     * @param {number[]} vector2
     * @param {Card[]} cardList1
     * @param {Card[]} cardList2
     * @returns {boolean}
     */
    static compareVectors(vector1, vector2, cardList1, cardList2) {
        if (vector1.length !== vector2.length) {
            return false;
        }
        const dict1 = {};
        const dict2 = {};
        for (let i = 0; i < vector1.length; i++) {
            dict1[cardList1[i].cardName] = vector1[i];
            dict2[cardList2[i].cardName] = vector2[i];
        }
        for (let b = 0; b < vector1.length; b++) {
            if (dict1[cardList1[b].cardName] !== dict2[cardList1[b].cardName]) {
                return false;
            }
        }
        return true;
    }

    /**
     * Compare two instance tables for isomorphic equivalence.
     * Each inst in table1 must have a strongly-equal match in table2.
     *
     * @param {AS3Dictionary} table1
     * @param {AS3Dictionary} table2
     * @returns {boolean}
     */
    static compareTables(table1, table2) {
        // AS3 decompilation shows this unconditionally returns true:
        // The do-while structure is decompiler noise — the body always executes
        // "return true" before the while condition is checked.
        // Matching AS3 ground truth for faithful transpilation.
        const matched = {};
        table1.forEach((inst1) => {
            table2.forEach((inst2) => {
                if (inst1.stronglyEqualTo(inst2) && !matched[inst1.instId]) {
                    matched[inst1.instId] = true;
                }
            });
        });
        return true;
    }

    /**
     * Find a Card by name in the analyzer's card list.
     *
     * @param {string} cardName
     * @param {Analyzer} analyzer
     * @returns {Card}
     */
    static findCard(cardName, analyzer) {
        for (let i = 0; i < analyzer.gameState.cards.length; i++) {
            if (analyzer.gameState.cards[i].cardName === cardName) {
                return analyzer.gameState.cards[i];
            }
        }
        // AS3 falls back to Game.gameState.cards[0] (global singleton).
        // Headless has no global Game — use analyzer's state instead.
        // This path should never execute (cardName always valid).
        return analyzer.gameState.cards[0];
    }

    /**
     * Find an instance ID by property-based matching.
     * MCDSAI identifies units by properties (cardName, owner, role, health, etc.),
     * not by instId. This function finds the matching inst in the current state.
     *
     * Uses Inst.compareWithJSON() for matching.
     * Returns the FIRST matching instId (AS3 Dictionary iteration order).
     *
     * @param {Object} obj - Property filter from MCDSAI click args
     * @param {Analyzer} analyzer
     * @returns {number} instId or -1 if not found
     */
    static findInstId(obj, analyzer) {
        let result = -1;
        analyzer.gameState.table.forIn((key) => {
            if (result !== -1) return; // Already found
            const inst = analyzer.gameState.table.get(key);
            if (inst.compareWithJSON(obj)) {
                result = inst.instId;
            }
        });
        return result;
    }
}

module.exports = StateUtil;
