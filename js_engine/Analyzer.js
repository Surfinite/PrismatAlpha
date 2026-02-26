'use strict';

const C = require('./C');
const Click = require('./Click');
const ClickResult = require('./ClickResult');
const Order = require('./Order');
const State = require('./State');
const EndTurnObject = require('./EndTurnObject');

/**
 * Analyzer.js — Game analyzer/click dispatcher, transpiled from mcds/engine/Analyzer.as
 *
 * Manages game history, click processing, and replay navigation.
 * In headless mode, all UI update/animate parameters are false and dispatch() is a no-op.
 *
 * Key entry points:
 *   Analyzer.analyzerFromState(state) — factory for AI analysis
 *   noUpdateClick(type, id, record) — execute a click without UI updates
 *   analyzerCanClick(type, id) — check if a click is legal
 *   recordClick(...) — record a click into history
 *   gotoTurn/gotoCommand/nextClick/prevMove/etc. — replay navigation
 */

/**
 * Clone a redo stack (Vector.<Order> → Array of Order).
 * From Analyzer.as:70-78.
 */
function cloneStack(stack) {
    const answer = new Array(stack.length);
    for (let i = 0; i < answer.length; i++) {
        answer[i] = stack[i];
    }
    return answer;
}

class Analyzer {
    /**
     * Constructor matching AS3 Analyzer(gameInitInfo, inputLaneId, controlledLane, initState).
     *
     * For headless self-play, use the static factory Analyzer.analyzerFromState(state).
     * The gameInitInfo path is preserved for replay loading but simplified:
     * - laneInfo/mergedDeck/scriptInfo/objectiveInfo extracted from gameInitInfo
     * - inputLaneId and controlledLane control replay mode (-1 = replay/analysis)
     *
     * From Analyzer.as:45-63.
     *
     * @param {Object|null} gameInitInfo - GameInitializationInfo equivalent (or null)
     * @param {number} inputLaneId
     * @param {number} controlledLane
     * @param {State|null} [initState=null] - Pre-existing state to analyze
     */
    constructor(gameInitInfo, inputLaneId, controlledLane, initState) {
        // Lazy-require Controller to break potential circular dependency
        const Controller = require('./Controller');

        this.initialized = false;
        this.gameInitInfo = null;

        // History tracking arrays (initialized in initializeAndPlayInitClicks)
        this.gameHistory = null;           // Vector.<Click>
        this.clickParsing = null;          // Vector.<String> — moveResult per click
        this.clickGotConvertedToUndo = null; // Vector.<Boolean>
        this.redoStackBeforeClick = null;  // Vector.<Vector.<Order>>
        this.nextInstIdBeforeClick = null; // Vector.<int>
        this.commandIndex = 0;
        this.beginTurnHistory = null;      // Vector.<State>
        this.turnStarts = null;            // Vector.<int>
        this.turnEnds = null;              // Vector.<int>
        this.endDefenses = null;           // Vector.<int>
        this.defendedThisTurn = false;
        this.inEndDefense = false;
        this.endTurnHistory = null;        // Vector.<EndTurnObject>
        this.lastTurnObject = null;
        this.turnIndex = 0;

        if (initState != null) {
            // From Analyzer.as:48-53: Clone state, init, play init clicks
            this.controller = new Controller(null, null, null, null, 0, 0, initState);
            this.initialized = false;
            this.initializeAndPlayInitClicks(false);
        } else if (gameInitInfo != null) {
            // From Analyzer.as:56-62: Fresh game from init info
            this.controller = new Controller(
                gameInitInfo.laneInfo,
                gameInitInfo.mergedDeck,
                gameInitInfo.scriptInfo,
                gameInitInfo.objectiveInfo,
                inputLaneId,
                controlledLane
            );
            this.initialized = false;
            if (controlledLane === -1) {
                this.gameInitInfo = gameInitInfo;
            }
        } else {
            // Called with all nulls (e.g., from analyzerFromState which passes initState)
            // This path shouldn't normally be hit, but matches AS3 new Analyzer(null,0,0,state)
            this.controller = null;
        }
    }

    /**
     * Factory: create an Analyzer from an existing State (clones it internally).
     * From Analyzer.as:65-68.
     *
     * @param {State} state
     * @returns {Analyzer}
     */
    static analyzerFromState(state) {
        return new Analyzer(null, 0, 0, state);
    }

    // --- Property accessors ---

    /**
     * The current game state (delegated to controller).
     * From Analyzer.as:80-83.
     * @returns {State}
     */
    get gameState() {
        return this.controller.state;
    }

    /**
     * Total number of clicks recorded in the replay history.
     * From Analyzer.as:85-88.
     * @returns {number}
     */
    get numClicksInReplay() {
        return this.gameHistory.length;
    }

    /**
     * End-turn history including the final partial turn if game is over.
     * From Analyzer.as:90-100.
     * @returns {EndTurnObject[]}
     */
    get endTurnHistoryForGraphs() {
        if (this.lastTurnObject) {
            const v = [];
            v.push(this.lastTurnObject);
            return this.endTurnHistory.concat(v);
        }
        return this.endTurnHistory;
    }

    /**
     * Number of turns in the replay (equals beginTurnHistory.length).
     * From Analyzer.as:102-105.
     * @returns {number}
     */
    get numTurnsInReplay() {
        return this.beginTurnHistory.length;
    }

    // --- Game construction / initialization ---

    /**
     * Construct a virgin game (dispatch loadstate — no-op in headless).
     * From Analyzer.as:107-110.
     */
    constructVirginGame() {
        /* STUB: UI-only — state.dispatch(true, false, C.SEND_LOADSTATE) is a no-op in headless */
    }

    /**
     * Initialize a virgin game: run triggers, swoosh, then init history.
     * From Analyzer.as:112-121.
     */
    initVirginGame() {
        if (!this.initialized) {
            this.runTriggersAndGotoW1(false, false);
            /* STUB: UI-only — state.dispatch(true, true, C.SEND_REFRESH) */
            this.gameState.swoosh();
            this.initializeAndPlayInitClicks(false);
        }
    }

    /**
     * Loader initialization (non-animated).
     * From Analyzer.as:123-128.
     */
    loaderInit() {
        this.runTriggersAndGotoW1(false, false);
        this.gameState.swoosh();
        this.initializeAndPlayInitClicks(false);
    }

    /**
     * Execute triggers (no-op for PvP) and increment numTurns.
     * From Analyzer.as:130-134.
     *
     * In AS3, executeTriggers handles mission/objective triggers.
     * For PvP headless, triggers array is empty so this is a no-op increment.
     *
     * @param {boolean} update - ignored in headless
     * @param {boolean} animate - ignored in headless
     */
    runTriggersAndGotoW1(update, animate) {
        // executeTriggers — no-op for PvP (empty triggers array in headless State.js)
        ++this.gameState.numTurns;
    }

    /**
     * Initialize tracking arrays and replay any stored command history.
     * From Analyzer.as:136-186.
     *
     * This is the core initialization after Controller is set up.
     * Sets up history arrays, processes any pre-loaded commands (from gameInitInfo),
     * and finalizes turn boundary sentinels.
     *
     * @param {boolean} appendEndSwipesCancelTargets - if true, auto-close swipe/target mode
     */
    initializeAndPlayInitClicks(appendEndSwipesCancelTargets) {
        this.initialized = true;
        this.gameState.helper.update(this.gameState);
        this.controller.newTurn();

        if (this.gameState.controlledLane === -1) {
            // Analysis/replay mode: set up all history tracking
            this.gameHistory = [];
            this.clickParsing = [];
            this.clickGotConvertedToUndo = [];
            this.redoStackBeforeClick = [];
            this.nextInstIdBeforeClick = [];
            this.commandIndex = 0;

            this.beginTurnHistory = [];
            this.beginTurnHistory.push(this.controller.beginTurnState);

            this.turnStarts = [];
            this.turnStarts.push(0);

            this.turnEnds = [];
            this.turnEnds.push(0);

            this.endDefenses = [];
            this.endDefenses.push(0);

            this.endTurnHistory = [];
            this.lastTurnObject = null;
            this.turnIndex = 0;

            // Replay pre-loaded commands from gameInitInfo if present
            if (this.gameInitInfo != null && this.gameInitInfo.commandInfo != null) {
                const cmdList = this.gameInitInfo.commandInfo.commandList;
                for (let i = 0; i < cmdList.length; i++) {
                    const cmdType = String(cmdList[i]._type);
                    // Skip emotes unless in replay mode (headless has no MODE_REPLAY concept)
                    if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) {
                        continue;
                    }
                    const result = this.recordClick(
                        false, false,
                        cmdList[i]._type,
                        cmdList[i]._id,
                        cmdList[i]._params
                    );
                    C.ASSERT(result.canClick,
                        'Illegal clicks encountered when playing through clicks at start of game.');
                }

                if (appendEndSwipesCancelTargets) {
                    if (this.controller.inTargetMode) {
                        const cancelResult = this.recordClick(false, false, C.CLICK_CANCEL_TARGET);
                        C.ASSERT(cancelResult.canClick,
                            'Illegal clicks encountered when playing through clicks at start of game.');
                    } else if (this.controller.inSwipe) {
                        const endSwipeResult = this.recordClick(false, false, C.CLICK_END_SWIPE);
                        C.ASSERT(endSwipeResult.canClick,
                            'Illegal clicks encountered when playing through clicks at start of game.');
                    }
                }
            }

            // Sentinel values for turn boundary tracking
            // int.MAX_VALUE in AS3 = 2147483647
            this.endDefenses.push(2147483647);
            this.turnEnds.push(this.numClicksInReplay - 2);
            this.turnEnds.push(this.numClicksInReplay);
        }
    }

    // --- Click processing ---

    /**
     * Record a click into the game history.
     * Snapshots redo stack and nextInstId BEFORE executing the click,
     * then processes via controller. On success, updates history and turn tracking.
     *
     * From Analyzer.as:188-246.
     *
     * @param {boolean} update - UI update flag (always false in headless)
     * @param {boolean} displayErrorMsg - show error messages (always false in headless)
     * @param {string} type - click type
     * @param {number} [id=-1] - target id
     * @param {Object} [params=null] - extra parameters
     * @returns {ClickResult}
     */
    recordClick(update, displayErrorMsg, type, id, params) {
        if (id === undefined) id = -1;
        if (params === undefined) params = null;

        const oldTurn = this.gameState.turn;
        const redoStack = cloneStack(this.controller.redoStack);
        const nextInstId = this.gameState.nextInstId;

        // State.TRACE is not used in headless mode

        const tempClickResult = this.controller.processClick(
            true,           // actuallyDoClick
            update,         // update
            update,         // animate (same as update in AS3)
            displayErrorMsg,// displayErrorMsg
            false,          // alreadyStartedUndoblocksSoDontStartMore
            false,          // isRedirectedClickSoDontStartSwipe
            type,
            id,
            params
        );

        if (tempClickResult.canClick) {
            this.clearGameFuture();

            this.gameHistory.push(new Click(type, id, params));
            this.clickParsing.push(tempClickResult.moveResult);
            this.clickGotConvertedToUndo.push(tempClickResult.clickGotConvertedToUndo);
            this.redoStackBeforeClick.push(redoStack);
            this.nextInstIdBeforeClick.push(nextInstId);
            ++this.commandIndex;

            // Detect turn boundary
            if (this.gameState.turn !== oldTurn && !this.gameState.finished) {
                ++this.turnIndex;
                this.defendedThisTurn = false;
                this.beginTurnHistory.push(this.controller.beginTurnState);
                this.turnStarts.push(this.numClicksInReplay);
                this.turnEnds.push(this.numClicksInReplay - 2);
                this.endTurnHistory.push(this.gameState.endTurnObject);
            }

            // Track game-over turn object
            if (this.gameState.finished) {
                this.lastTurnObject = this.gameState.endTurnObject;
            }

            // Track end-of-defense transitions
            if (!this.gameState.inEndDefense && this.inEndDefense && !this.gameState.finished) {
                if (this.defendedThisTurn) {
                    this.endDefenses.pop();
                }
                this.endDefenses.push(this.numClicksInReplay - 1);
                this.defendedThisTurn = true;
            }
            this.inEndDefense = this.gameState.inEndDefense;

            C.ASSERT(this.commandIndex === this.numClicksInReplay,
                'commandIndex !== numClicksInReplay after recordClick');
            C.ASSERT(this.turnIndex + 1 === this.numTurnsInReplay,
                'turnIndex + 1 !== numTurnsInReplay after recordClick');
        }

        return tempClickResult;
    }

    /**
     * Truncate forward history when branching from mid-replay.
     * Removes clicks beyond commandIndex, popping turn boundaries as needed.
     *
     * From Analyzer.as:248-264.
     */
    clearGameFuture() {
        while (this.numClicksInReplay > this.commandIndex) {
            this.gameHistory.pop();
            this.clickParsing.pop();
            this.clickGotConvertedToUndo.pop();
            this.redoStackBeforeClick.pop();
            this.nextInstIdBeforeClick.pop();

            if (this.numTurnsInReplay > 1 &&
                this.numClicksInReplay < this.turnStarts[this.numTurnsInReplay - 1]) {
                this.beginTurnHistory.pop();
                this.turnStarts.pop();
                this.endTurnHistory.pop();
            }
        }
    }

    /**
     * Check whether a click is legal (does not execute it).
     * From Analyzer.as:266-269.
     *
     * @param {string} type
     * @param {number} [id=-1]
     * @returns {boolean}
     */
    analyzerCanClick(type, id) {
        if (id === undefined) id = -1;
        return this.analyzerWhatToHighlight(type, id).canClick;
    }

    /**
     * Check what a click would do and return highlight info (without executing).
     * From Analyzer.as:271-274.
     *
     * @param {string} type
     * @param {number} [id=-1]
     * @returns {ClickResult}
     */
    analyzerWhatToHighlight(type, id) {
        if (id === undefined) id = -1;
        return this.controller.processClick(
            false,  // actuallyDoClick = false (query only)
            false,  // update
            false,  // animate
            false,  // displayErrorMsg
            false,  // alreadyStartedUndoblocksSoDontStartMore
            false,  // isRedirectedClickSoDontStartSwipe
            type,
            id
        );
    }

    /**
     * Execute a click without UI updates.
     * Optionally records in history (for AI self-play, record=true preserves undo info).
     *
     * From Analyzer.as:276-287.
     *
     * @param {string} type
     * @param {number} [id=-1]
     * @param {boolean} [record=false]
     */
    noUpdateClick(type, id, record) {
        if (id === undefined) id = -1;
        if (record === undefined) record = false;

        if (record) {
            this.recordClick(false, false, type, id);
            // AS3 silently ignores failure here (empty block on canClick==false)
        } else {
            this.controller.processClick(
                true,   // actuallyDoClick
                false,  // update
                false,  // animate
                false,  // displayErrorMsg
                false,  // alreadyStartedUndoblocksSoDontStartMore
                false,  // isRedirectedClickSoDontStartSwipe
                type,
                id
            );
            // AS3 silently ignores failure here (empty block on canClick!=true)
        }
    }

    // --- Replay navigation ---

    /**
     * Jump to start of a specific turn by restoring the saved state.
     * From Analyzer.as:289-296.
     *
     * @param {number} index - Turn index (0-based)
     */
    gotoTurn(index) {
        this.turnIndex = index;
        this.commandIndex = this.turnStarts[this.turnIndex];
        this.controller.state = this.beginTurnHistory[this.turnIndex].clone();
        /* STUB: UI-only — state.dispatch(true, false, C.SEND_LOADSTATE) */
        this.controller.newTurn();
    }

    /**
     * Jump to a specific command index by finding the containing turn and replaying.
     * From Analyzer.as:298-309.
     *
     * @param {number} index - Command index (0-based)
     */
    gotoCommand(index) {
        let i = 1;
        for (; i < this.numTurnsInReplay; i++) {
            if (this.turnStarts[i] > index) {
                break;
            }
        }
        this.gotoTurn(i - 1);
        this.playForwardUntil(index);
    }

    /**
     * Whether we are at the start of the current turn.
     * From Analyzer.as:311-314.
     * @returns {boolean}
     */
    atStartOfTurn() {
        return this.commandIndex === this.turnStarts[this.turnIndex];
    }

    /**
     * Whether there are more clicks to play forward.
     * From Analyzer.as:316-319.
     * @returns {boolean}
     */
    canNext() {
        return this.commandIndex < this.numClicksInReplay;
    }

    /**
     * Play the next click with UI updates (animate=true in AS3, ignored in headless).
     * From Analyzer.as:321-330.
     */
    nextClick() {
        const oldTurn = this.gameState.turn;
        this.controller.processClick(
            true,   // actuallyDoClick
            true,   // update
            true,   // animate
            false,  // displayErrorMsg
            false,  // alreadyStartedUndoblocksSoDontStartMore
            false,  // isRedirectedClickSoDontStartSwipe
            this.gameHistory[this.commandIndex]._type,
            this.gameHistory[this.commandIndex]._id,
            this.gameHistory[this.commandIndex]._params
        );
        ++this.commandIndex;
        if (this.gameState.turn !== oldTurn && !this.gameState.finished) {
            ++this.turnIndex;
        }
    }

    /**
     * Play the next click without animation (animate=false).
     * From Analyzer.as:332-341.
     */
    nextClickNoAnimate() {
        const oldTurn = this.gameState.turn;
        this.controller.processClick(
            true,   // actuallyDoClick
            true,   // update
            false,  // animate
            false,  // displayErrorMsg
            false,  // alreadyStartedUndoblocksSoDontStartMore
            false,  // isRedirectedClickSoDontStartSwipe
            this.gameHistory[this.commandIndex]._type,
            this.gameHistory[this.commandIndex]._id,
            this.gameHistory[this.commandIndex]._params
        );
        ++this.commandIndex;
        if (this.gameState.turn !== oldTurn && !this.gameState.finished) {
            ++this.turnIndex;
        }
    }

    /**
     * Play one atomic move forward (click + complete any chain).
     * From Analyzer.as:343-347.
     */
    nextMove() {
        this.nextClickNoAnimate();
        this.completeMove();
    }

    /**
     * Advance to the next turn boundary.
     * From Analyzer.as:349-363.
     */
    nextTurn() {
        if (this.turnIndex === this.numTurnsInReplay - 1) {
            this.playForwardUntil(this.numClicksInReplay);
        } else if (this.commandIndex === this.turnStarts[this.turnIndex + 1] - 1) {
            this.nextMove();
        } else {
            this.playForwardUntil(this.turnStarts[this.turnIndex + 1] - 1);
        }
    }

    /**
     * Advance to next turn as used by the replay viewer UI.
     * From Analyzer.as:365-386.
     */
    nextTurnUsedByReplayer() {
        if (this.turnIndex === this.numTurnsInReplay - 1) {
            this.playForwardUntil(this.numClicksInReplay);
        } else if (this.commandIndex === this.turnStarts[this.turnIndex + 1] - 1) {
            if (this.turnIndex === this.numTurnsInReplay - 2) {
                this.playForwardUntil(this.numClicksInReplay);
            } else {
                this.playForwardUntil(this.turnStarts[this.turnIndex + 2] - 1);
            }
        } else {
            this.playForwardUntil(this.turnStarts[this.turnIndex + 1] - 1);
        }
    }

    /**
     * Advance to the next phase boundary (endDefense or turnEnd, whichever comes first).
     * From Analyzer.as:388-401.
     */
    nextPhase() {
        let i = 0;
        let j = 0;
        while (this.commandIndex >= this.endDefenses[i]) {
            i++;
        }
        while (this.commandIndex >= this.turnEnds[j]) {
            j++;
        }
        this.playForwardUntil(Math.min(this.endDefenses[i], this.turnEnds[j]));
    }

    /**
     * Go back to the previous phase boundary.
     * From Analyzer.as:403-416.
     */
    prevPhase() {
        let i = this.endDefenses.length - 1;
        let j = this.turnEnds.length - 1;
        while (this.endDefenses[i] >= this.commandIndex) {
            i--;
        }
        while (this.turnEnds[j] >= this.commandIndex) {
            j--;
        }
        this.gotoCommand(Math.max(this.endDefenses[i], this.turnEnds[j]));
    }

    /**
     * Whether there are earlier clicks to navigate back to.
     * From Analyzer.as:418-421.
     * @returns {boolean}
     */
    canPrev() {
        return this.commandIndex > 0;
    }

    /**
     * Navigate backward one atomic move.
     * Uses undo/redo stack snapshots to reverse the click without full state replay.
     *
     * From Analyzer.as:423-464.
     */
    prevMove() {
        if (this.commandIndex === this.turnStarts[this.turnIndex] ||
            this.gameState.result !== C.COLOR_NONE) {
            // At turn start or game over: must re-derive from saved state
            this.gotoCommand(this.commandIndex - 1);
        } else {
            this.completeMove();
            --this.commandIndex;
            const prevClick = this.gameHistory[this.commandIndex];

            if (prevClick._type.indexOf(C.CLICK_REPLAY_EMOTE) !== 0) {
                if (prevClick._type === C.CLICK_UNDO ||
                    this.clickGotConvertedToUndo[this.commandIndex]) {
                    // Undo click: reverse by redoing
                    this.controller.redo(true);
                } else {
                    // Normal click: reverse by undoing
                    this.controller.undo(true);

                    if (this.clickParsing[this.commandIndex] === ClickResult.END_OF_CHAIN ||
                        this.clickParsing[this.commandIndex] === ClickResult.END_OF_CHAIN_DOUBLE_UNDO) {
                        // Multi-click chain: undo back to start
                        if (this.clickParsing[this.commandIndex] === ClickResult.END_OF_CHAIN_DOUBLE_UNDO) {
                            this.controller.undo(true);
                        }
                        while (this.clickParsing[this.commandIndex] !== ClickResult.START_OF_CHAIN) {
                            --this.commandIndex;
                        }
                    } else if (this.clickParsing[this.commandIndex] !== ClickResult.ITSELF_A_CHAIN) {
                        C.ASSERT(false, 'Game history is messed up.');
                    }

                    // Restore saved redo stack and nextInstId from before the click
                    this.controller.redoStack = cloneStack(this.redoStackBeforeClick[this.commandIndex]);
                    this.gameState.nextInstId = this.nextInstIdBeforeClick[this.commandIndex];
                }
            }
            // Emote clicks: nothing to undo
        }
    }

    /**
     * Navigate backward one turn.
     * From Analyzer.as:466-476.
     */
    prevTurn() {
        if (this.commandIndex === this.turnStarts[this.turnIndex]) {
            this.prevMove();
        } else {
            this.gotoTurn(this.turnIndex);
        }
    }

    /**
     * Navigate backward one turn (replayer variant — always shows previous turn boundary).
     * From Analyzer.as:478-488.
     */
    prevTurnUsedByReplayer() {
        if (this.turnIndex === 0) {
            this.gotoTurn(0);
        } else {
            this.gotoCommand(this.turnStarts[this.turnIndex] - 1);
        }
    }

    /**
     * Return full click history as plain objects [{_type, _id}, ...].
     * From Analyzer.as:490-502.
     *
     * @returns {Array.<{_type: string, _id: number}>}
     */
    historyForAnalysis() {
        const answer = [];
        for (let i = 0; i < this.gameHistory.length; i++) {
            const click = this.gameHistory[i];
            answer.push({
                '_type': click._type,
                '_id': click._id
            });
        }
        return answer;
    }

    /**
     * Restart analysis: reload all commands from gameInitInfo and go to saved position.
     * From Analyzer.as:504-523.
     */
    restartAnalysis() {
        this.turnIndex = 0;
        this.commandIndex = 0;
        this.controller.state = this.beginTurnHistory[0].clone();
        this.controller.newTurn();

        let numEmotes = 0;
        const cmdList = this.gameInitInfo.commandInfo.commandList;
        for (let i = 0; i < cmdList.length; i++) {
            const cmdType = String(cmdList[i]._type);
            if (cmdType.indexOf(C.CLICK_REPLAY_EMOTE) === 0) {
                numEmotes += 1;
            } else {
                this.recordClick(false, false, cmdList[i]._type, cmdList[i]._id);
            }
        }
        this.gotoCommand(this.gameInitInfo.commandInfo.gamePosition - numEmotes);
    }

    /**
     * Whether we can advance two full turns.
     * From Analyzer.as:525-542.
     * @returns {boolean}
     */
    canNextTwoTurns() {
        if (this.turnIndex === this.numTurnsInReplay - 1) {
            if (this.commandIndex === this.numClicksInReplay) {
                return false;
            }
        } else if (this.turnIndex === this.numTurnsInReplay - 2) {
            if (this.commandIndex === this.turnStarts[this.turnIndex + 1] - 1) {
                return false;
            }
        }
        return true;
    }

    /**
     * Advance two full turns.
     * From Analyzer.as:544-562.
     */
    nextTwoTurns() {
        if (this.turnIndex === this.numTurnsInReplay - 1) {
            this.playForwardUntil(this.numClicksInReplay);
        } else if (this.turnIndex === this.numTurnsInReplay - 2) {
            this.playForwardUntil(this.turnStarts[this.turnIndex + 1] - 1);
        } else if (this.commandIndex >= this.turnStarts[this.turnIndex + 1] - 2) {
            this.gotoTurn(this.turnIndex + 2);
        } else {
            this.playForwardUntil(this.turnStarts[this.turnIndex + 1] - 2);
        }
    }

    /**
     * Whether we can go back two full turns.
     * From Analyzer.as:564-585.
     * @returns {boolean}
     */
    canPrevTwoTurns() {
        if (this.gameState.result !== C.COLOR_NONE) {
            return true;
        }
        if (this.turnIndex === 0) {
            if (this.commandIndex === 0) {
                return false;
            }
        } else if (this.turnIndex === 1) {
            if (this.commandIndex === this.turnStarts[this.turnIndex]) {
                return false;
            }
        }
        return true;
    }

    /**
     * Go back two full turns.
     * From Analyzer.as:587-619.
     */
    prevTwoTurns() {
        if (this.gameState.result !== C.COLOR_NONE) {
            if (this.gameState.turn === C.COLOR_BLACK) {
                this.gotoTurn(this.turnIndex - 1);
            } else {
                this.gotoTurn(this.turnIndex);
            }
            this.clearGameFuture();
            return;
        }
        if (this.turnIndex === 0) {
            this.gotoTurn(this.turnIndex);
        } else if (this.turnIndex === 1) {
            this.gotoTurn(this.turnIndex);
        } else if (this.commandIndex === this.turnStarts[this.turnIndex]) {
            this.gotoTurn(this.turnIndex - 2);
            this.playForwardUntil(this.turnStarts[this.turnIndex + 1] - 2);
        } else {
            this.gotoTurn(this.turnIndex);
        }
    }

    /**
     * Return clicks from the most recent turn as plain objects.
     * From Analyzer.as:621-632.
     *
     * @returns {Array.<{_type: string, _id: number}>}
     */
    mostRecentTurnHistory() {
        const answer = [];
        for (let i = this.turnStarts[this.turnStarts.length - 1]; i < this.gameHistory.length; i++) {
            answer.push({
                '_type': this.gameHistory[i]._type,
                '_id': this.gameHistory[i]._id
            });
        }
        return answer;
    }

    // --- Private helpers ---

    /**
     * Advance past MIDDLE_OF_CHAIN clicks to the next atomic move boundary.
     * A move boundary is START_OF_CHAIN, ITSELF_A_CHAIN, or end of history.
     *
     * From Analyzer.as:634-640.
     */
    completeMove() {
        while (!(this.commandIndex === this.numClicksInReplay ||
                 this.clickParsing[this.commandIndex] === ClickResult.START_OF_CHAIN ||
                 this.clickParsing[this.commandIndex] === ClickResult.ITSELF_A_CHAIN)) {
            this.nextClickNoAnimate();
        }
    }

    /**
     * Play forward (without animation) until reaching the target command index.
     * From Analyzer.as:642-648.
     *
     * @param {number} index - Target command index
     */
    playForwardUntil(index) {
        while (this.commandIndex < index) {
            this.nextClickNoAnimate();
        }
    }

    /**
     * Drop clicks beyond a given count (used when server rejects late clicks).
     * From Analyzer.as:650-659.
     *
     * @param {number} numAcceptedClicks
     */
    dropLateClicks(numAcceptedClicks) {
        if (!this.initialized) {
            this.initVirginGame();
            return;
        }
        this.gotoCommand(numAcceptedClicks);
        this.clearGameFuture();
    }
}

module.exports = Analyzer;
