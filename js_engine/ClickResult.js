'use strict';

/**
 * ClickResult.js — Click validation result, transpiled from mcds/engine/ClickResult.as
 *
 * Reports whether a click was valid, what move it produced, and UI feedback.
 * UI highlight vectors are preserved but unused in headless mode.
 */
class ClickResult {
    /**
     * @param {boolean} actuallyDoClick
     * @param {boolean} canClick
     */
    constructor(actuallyDoClick, canClick) {
        this.actuallyDoClick = actuallyDoClick;
        this.canClick = canClick;
        this.moveResult = '';
        this.clickGotConvertedToUndo = false;
        this.instsToHighlight = [];    // Vector.<Inst> → Array
        this.cardsToHighlight = [];    // Vector.<Card> → Array
        this.buttonsToHighlight = [];  // Vector.<String> → Array
        this.spawnsToHighlight = [];   // Vector.<RaidSpawn> → Array (not used in PvP)
        this.serverResult = null;      // AS3 null → JS null
    }
}

// Chain position constants
ClickResult.START_OF_CHAIN = 'start of chain';
ClickResult.MIDDLE_OF_CHAIN = 'middle of chain';
ClickResult.END_OF_CHAIN = 'end of chain';
ClickResult.END_OF_CHAIN_DOUBLE_UNDO = 'end of chain double undo';
ClickResult.ITSELF_A_CHAIN = 'itself a chain';

// Button types
ClickResult.BUTTON_END_TURN = 'button end turn';
ClickResult.BUTTON_REVERT = 'button revert';
ClickResult.BUTTON_UNDO = 'button undo';
ClickResult.BUTTON_REDO = 'button redo';

// Server types
ClickResult.SERVER_END_TURN = 'server end turn';
ClickResult.SERVER_END_GAME = 'server end game';

module.exports = ClickResult;
