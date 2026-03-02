'use strict';

const C = require('./C');
const State = require('./State');
const Order = require('./Order');
const ClickResult = require('./ClickResult');

/**
 * Controller.js — Click processing engine, transpiled from mcds/engine/Controller.as (2,574 lines)
 *
 * Handles ALL user/AI click types and routes to the appropriate game moves.
 * This is the headless version: dispatch() calls are no-ops, UIEvent/Errorbang removed,
 * tutorial guards are always-off (TUTORIAL_MODE = false).
 *
 * AI clicks come as: "card clicked", "inst clicked", "space clicked",
 *                     "inst shift clicked", "card shift clicked"
 */
class Controller {
    /**
     * @param {Object} laneInfo
     * @param {Array} mergedDeck
     * @param {Object} scriptInfo
     * @param {Object} objectiveInfo
     * @param {number} inputLaneId
     * @param {number} controlledLane
     * @param {State|null} initState - Existing state to clone from
     * @param {boolean} [loader=false]
     */
    constructor(laneInfo, mergedDeck, scriptInfo, objectiveInfo, inputLaneId, controlledLane, initState, loader) {
        if (initState !== undefined && initState !== null) {
            this.state = initState.clone();
        } else {
            this.state = new State(laneInfo, mergedDeck, scriptInfo, objectiveInfo, inputLaneId, controlledLane);
        }
        this.swipePurpose = null;
        this.targetSources = null;
        this.beginTurnState = null;
        this.undoStack = [];
        this.redoStack = [];
        this.revertFromStack = [];
        this.endDefendStack = [];
        this.endActionStack = [];
    }

    // --- Properties ---

    get inSwipe() {
        return this.swipePurpose !== null;
    }

    get inTargetMode() {
        return this.targetSources !== null;
    }

    // ======================================================================
    // processClick — the core routing method (Controller.as:49-1277)
    //
    // actuallyDoClick:   true = execute the move; false = highlight query only
    // update/animate:    ignored in headless (dispatch is no-op)
    // displayErrorMsg:   passed to failure() — no-op in headless
    // alreadyStartedUndoblocksSoDontStartMore: prevents nested undoblock starts
    // isRedirectedClickSoDontStartSwipe: prevents swipe start on redirected clicks
    // type:              CLICK_INST, CLICK_CARD, CLICK_SPACE, etc.
    // id:                card index or instance ID
    // params:            optional extra data (emote params, etc.)
    // ======================================================================

    processClick(actuallyDoClick, update, animate, displayErrorMsg,
                 alreadyStartedUndoblocksSoDontStartMore,
                 isRedirectedClickSoDontStartSwipe,
                 type, id, params) {
        if (id === undefined) id = -1;
        if (params === undefined) params = null;

        let tempClickResult = null;
        let inst = null;
        let tempReason = null;
        let answer = null;
        let insts = null;
        let card = null;
        let i = 0;
        let location = 0;
        let endedSwipeOrTarget = false;

        // --- Early exits ---

        if (this.state.numTurns === 0) {
            this.failure(actuallyDoClick, C.ERROR_GAME_NOT_STARTED);
            return new ClickResult(actuallyDoClick, false);
        }
        if (this.state.finished) {
            this.failure(actuallyDoClick, C.ERROR_GAME_OVER);
            return new ClickResult(actuallyDoClick, false);
        }
        if (type === null) {
            // AS3 has empty block; fall through to bottom ASSERT
        }

        // --- Emote ---

        if (type && type.indexOf(C.CLICK_REPLAY_EMOTE) === 0) {
            /* STUB: UI-only — UIEvent.say(EMOTE, ...) */
            this.processOrder(update, animate, new Order(C.MOVE_EMOTE));
            answer = new ClickResult(actuallyDoClick, true);
            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
            return answer;
        }

        // --- Confirm phase: non-space/revert/undo/redo clicks become undo ---

        if (this.state.phase === C.PHASE_CONFIRM) {
            if (type !== C.CLICK_SPACE && type !== C.CLICK_REVERT &&
                type !== C.CLICK_UNDO && type !== C.CLICK_REDO) {
                C.ASSERT(this.undoStack.length > 0, 'In confirm phase, yet undoStack is empty.');
                tempClickResult = this.processClick(actuallyDoClick, update, animate,
                    displayErrorMsg, false, true, C.CLICK_UNDO);
                tempClickResult.clickGotConvertedToUndo = true;
                return tempClickResult;
            }
        } else if (this.inTargetMode) {
            // --- Target mode: inst clicks routed to target resolution ---
            if (type === C.CLICK_INST || type === C.CLICK_INST_SHIFT) {
                C.ASSERT(!(type === C.CLICK_INST_SHIFT && this.inSwipe),
                    'Got a shift click in the middle of a swipe.');
                inst = this.state.instIdToInst(id);
                tempReason = this.instSatisfiesConditionWhy(inst, this.targetSources[0].card.condition);

                if (tempReason === null) {
                    answer = new ClickResult(actuallyDoClick, true);
                    if (actuallyDoClick) {
                        if (type === C.CLICK_INST_SHIFT) {
                            insts = this.instsWeaklyEqualTo(inst);
                            insts.sort((a, b) => this._compareInstBackward(a, b));
                        } else {
                            insts = [inst];
                        }
                        card = this.targetSources[0].card;
                        while (insts.length > 0) {
                            if (this.instSatisfiesConditionWhy(insts[0], card.condition) !== null) {
                                insts.shift();
                                if (card.targetAction === C.TARGETACTION_DISRUPT) {
                                    while (insts.length > 0 &&
                                           insts[0].health > card.targetAmount * this.targetSources.length) {
                                        insts.shift();
                                    }
                                }
                            } else {
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_ASSIGN,
                                        this.targetSources[0].instId,
                                        insts[0].instId,
                                        -1, null,
                                        this.state.scriptToInstIds(this.targetSources[0].card.abilityScript)));
                                /* STUB: UI-only — state.dispatch(SEND_TARGET_CHANGE) */
                                this.targetSources.shift();
                                if (this.targetSources.length === 0 ||
                                    !this.canAssign(false, this.targetSources[0])) {
                                    return this.processClick(actuallyDoClick, update, animate,
                                        displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                                }
                            }
                        }
                        if (type === C.CLICK_INST) {
                            if (!this.inSwipe) {
                                this.swipePurpose = C.SWIPEPURPOSE_DISRUPT;
                            }
                        }
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else if (type === C.CLICK_INST_SHIFT) {
                        answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                    } else {
                        answer.instsToHighlight.push(inst);
                    }
                    return answer;
                }

                // Target condition failed
                this.failure(displayErrorMsg, tempReason, {
                    inst: this.targetSources[0],
                    targetInst: inst
                });
                return new ClickResult(actuallyDoClick, false);
            }
        }

        // ======================================================================
        // CLICK_INST / CLICK_INST_SHIFT — instance clicks
        // ======================================================================

        if (type === C.CLICK_INST || type === C.CLICK_INST_SHIFT) {
            C.ASSERT(!(type === C.CLICK_INST_SHIFT && this.inSwipe),
                'Got a shift click in the middle of a swipe.');
            inst = this.state.instIdToInst(id);

            // Guard against null inst (can happen during replay if state diverged)
            if (inst === null || inst === undefined) {
                return new ClickResult(actuallyDoClick, false);
            }

            // ------------------------------------------------------------------
            // DEFENSE PHASE
            // ------------------------------------------------------------------
            if (this.state.phase === C.PHASE_DEFENSE) {
                if (inst.owner !== this.state.turn) {
                    this.failure(displayErrorMsg, C.ERROR_OPPONENT, { inst: inst });
                    return new ClickResult(actuallyDoClick, false);
                }

                if (!inst.blocking) {
                    if (!inst.card.defaultBlocking) {
                        this.failure(displayErrorMsg, C.ERROR_DEFEND_NONBLOCKER, { inst: inst });
                    } else if (inst.disruptDamage >= inst.damageItCanTake + inst.damage) {
                        this.failure(displayErrorMsg, C.ERROR_DEFEND_DISRUPTED, { inst: inst });
                    } else if (inst.constructionTime > 0) {
                        this.failure(displayErrorMsg, C.ERROR_DEFEND_UNDER_CONSTRUCTION, { inst: inst });
                    } else {
                        this.failure(displayErrorMsg, C.ERROR_DEFEND_BUSY, { inst: inst });
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // --- Defend (not dead, not partially damaged) ---
                if (!inst.dead && !inst.isPartiallyDamaged) {
                    if (this.state.inEndDefense) {
                        this.failure(displayErrorMsg, C.ERROR_DEFEND_NO_ATTACK, { inst: inst });
                        return new ClickResult(actuallyDoClick, false);
                    }

                    answer = new ClickResult(actuallyDoClick, true);
                    if (type === C.CLICK_INST_SHIFT) {
                        if (actuallyDoClick) {
                            insts = this.instsWeaklyEqualTo(inst);
                            insts.sort((a, b) => this._compareInstBackward(a, b));
                            this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                            for (i = 0; i < insts.length; i++) {
                                this.processOrder(update, animate, new Order(C.MOVE_DEFEND, insts[i].instId));
                                if (this.state.inEndDefense) {
                                    break;
                                }
                            }
                            this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        } else {
                            answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                        }
                    } else if (actuallyDoClick) {
                        if (this.inSwipe) {
                            this.processOrder(update, animate, new Order(C.MOVE_DEFEND, inst.instId));
                            answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                        } else {
                            this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                            this.processOrder(update, animate, new Order(C.MOVE_DEFEND, inst.instId));
                            this.swipePurpose = C.SWIPEPURPOSE_DEFEND;
                            answer.moveResult = ClickResult.START_OF_CHAIN;
                        }
                    } else {
                        answer.instsToHighlight.push(inst);
                    }
                    return answer;
                }

                // --- Undefend (dead or partially damaged) ---
                // TUTORIAL_DISABLE_UNDEFEND — always false in headless

                answer = new ClickResult(actuallyDoClick, true);
                if (this.state.helper.partiallyDamagedInst !== null) {
                    if (type === C.CLICK_INST_SHIFT) {
                        insts = this.instsWeaklyEqualTo(inst);
                        location = insts.indexOf(this.state.helper.partiallyDamagedInst) | 0;
                        if (location >= 0) {
                            if (actuallyDoClick) {
                                this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_UNDEFEND, this.state.helper.partiallyDamagedInst.instId, inst.instId));
                                insts.splice(location, 1);
                                for (i = 0; i < insts.length; i++) {
                                    this.processOrder(update, animate,
                                        new Order(C.MOVE_UNDEFEND, insts[i].instId, inst.instId));
                                }
                                this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                            } else {
                                answer.instsToHighlight = insts;
                            }
                        } else if (actuallyDoClick) {
                            this.processOrder(update, animate,
                                new Order(C.MOVE_UNDEFEND, this.state.helper.partiallyDamagedInst.instId));
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        } else {
                            answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
                        }
                    } else if (actuallyDoClick) {
                        if (inst.instId === this.state.helper.partiallyDamagedInst.instId) {
                            if (this.inSwipe) {
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_UNDEFEND, this.state.helper.partiallyDamagedInst.instId));
                                answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                            } else {
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_UNDEFEND, this.state.helper.partiallyDamagedInst.instId));
                                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                            }
                        } else {
                            this.processOrder(update, animate,
                                new Order(C.MOVE_UNDEFEND, this.state.helper.partiallyDamagedInst.instId));
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        }
                    } else {
                        answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
                    }
                } else if (type === C.CLICK_INST_SHIFT) {
                    if (actuallyDoClick) {
                        insts = this.instsWeaklyEqualTo(inst);
                        this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        for (i = 0; i < insts.length; i++) {
                            this.processOrder(update, animate,
                                new Order(C.MOVE_UNDEFEND, insts[i].instId, inst.instId));
                        }
                        this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                        answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                    } else {
                        answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                    }
                } else if (actuallyDoClick) {
                    if (this.inSwipe) {
                        this.processOrder(update, animate, new Order(C.MOVE_UNDEFEND, inst.instId));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        this.processOrder(update, animate, new Order(C.MOVE_UNDEFEND, inst.instId));
                        this.swipePurpose = C.SWIPEPURPOSE_UNDEFEND;
                        answer.moveResult = ClickResult.START_OF_CHAIN;
                    }
                } else {
                    answer.instsToHighlight.push(inst);
                }
                return answer;

            } // end PHASE_DEFENSE

            // ------------------------------------------------------------------
            // ACTION PHASE
            // ------------------------------------------------------------------
            if (this.state.phase === C.PHASE_ACTION) {
                // --- Opponent's units ---
                if (inst.owner !== this.state.turn) {
                    if (!inst.dead && !inst.isPartiallyDamaged) {
                        // --- Under construction: try overkill, or redirect to creator ---
                        if (inst.constructionTime > 0) {
                            answer = this.tryToOverkill(actuallyDoClick, update, animate, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            if (inst.creatorIdFromBuyOrAbility >= 0 &&
                                (!actuallyDoClick || !this.inSwipe)) {
                                answer = this.processClick(actuallyDoClick, update, animate,
                                    false, false, true, type, inst.creatorIdFromBuyOrAbility);
                                if (answer.canClick) {
                                    return answer;
                                }
                            }
                            if (this.state.canOverkill) {
                                this.failure(displayErrorMsg, C.ERROR_OVERKILL_ATTACK, {
                                    inst: inst,
                                    manaType: C.MANA_A,
                                    turn: this.state.turn
                                });
                            } else if (this.state.canBreach) {
                                this.failure(displayErrorMsg, C.ERROR_OPPONENT_INVULNERABLE, { inst: inst });
                            } else if (this.state.wouldWipeout) {
                                this.failure(displayErrorMsg, C.ERROR_MUST_WIPEOUT_FIRST, { inst: inst });
                            } else {
                                this.failure(displayErrorMsg, C.ERROR_OPPONENT, { inst: inst });
                            }
                        }
                        // --- Undefendable (e.g., Gauss Charge): try undisrupt, then melee ---
                        else if (inst.card.undefendable) {
                            answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            answer = this.tryToMelee(actuallyDoClick, update, animate, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            this.failure(displayErrorMsg, C.ERROR_MELEE_ATTACK, {
                                inst: inst,
                                manaType: C.MANA_A,
                                turn: this.state.turn
                            });
                        }
                        // --- Blocking: try undisrupt, then wipeout ---
                        else if (inst.blocking) {
                            // TUTORIAL_MODE check skipped (always false in headless)
                            answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            answer = this.tryToWipeout(actuallyDoClick, update, animate);
                            if (answer.canClick) {
                                return answer;
                            }
                            this.failure(displayErrorMsg, C.ERROR_OPPONENT, { inst: inst });
                        }
                        // --- Non-blocking: try breach/undisrupt (order depends on glassBroken) ---
                        else {
                            // TUTORIAL_MODE and TUTORIAL_ALLOW_CLICKBREACH checks skipped
                            if (this.state.glassBroken) {
                                answer = this.tryToBreach(actuallyDoClick, update, animate, inst,
                                    type === C.CLICK_INST_SHIFT);
                                if (answer.canClick) {
                                    return answer;
                                }
                                answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                    type === C.CLICK_INST_SHIFT);
                                if (answer.canClick) {
                                    return answer;
                                }
                            } else {
                                answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                    type === C.CLICK_INST_SHIFT);
                                if (answer.canClick) {
                                    return answer;
                                }
                                answer = this.tryToBreach(actuallyDoClick, update, animate, inst,
                                    type === C.CLICK_INST_SHIFT);
                                if (answer.canClick) {
                                    return answer;
                                }
                            }
                            if (this.state.canBreach) {
                                this.failure(displayErrorMsg, C.ERROR_BREACH_ATTACK, {
                                    inst: inst,
                                    manaType: C.MANA_A,
                                    endTurn: this.state.turnMana.attack <= 0 ||
                                             this.state.helper.oppAllUnitsTotal <= 0 ||
                                             this.state.inEndBO,
                                    attackLeft: this.state.turnMana.attack
                                });
                            } else if (this.state.wouldWipeout) {
                                this.failure(displayErrorMsg, C.ERROR_MUST_WIPEOUT_FIRST, { inst: inst });
                            } else {
                                this.failure(displayErrorMsg, C.ERROR_OPPONENT, { inst: inst });
                            }
                        }
                    }
                    // --- Dead opponent units: undo actions ---
                    else if (inst.deadness === C.DEADNESS_MELEED) {
                        answer = this.tryToUnmelee(actuallyDoClick, update, inst,
                            type === C.CLICK_INST_SHIFT);
                        if (answer.canClick) {
                            return answer;
                        }
                        answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                            type === C.CLICK_INST_SHIFT);
                        if (answer.canClick) {
                            return answer;
                        }
                        if (this.state.haveOverkilled) {
                            this.failure(displayErrorMsg, C.ERROR_UNMELEE_UNIT_AFTER_O, {
                                inst: inst,
                                overkilled: this.state.helper.overkilled
                            });
                        } else {
                            this.failure(displayErrorMsg, C.ERROR_UNMELEE_DEFENDER_AFTER_WB, {
                                inst: inst,
                                wipedOut: this.state.helper.wipedOut,
                                breached: this.state.helper.breached
                            });
                        }
                    } else if (inst.deadness === C.DEADNESS_WBO || inst.isPartiallyDamaged) {
                        if (inst.blocking) {
                            // TUTORIAL_MODE check skipped
                            answer = this.tryToUnwipeout(actuallyDoClick, update);
                            if (answer.canClick) {
                                return answer;
                            }
                            answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            this.failure(displayErrorMsg, C.ERROR_UNWIPEOUT_AFTER_BO, {
                                breached: this.state.helper.breached,
                                overkilled: this.state.helper.overkilled
                            });
                        } else {
                            if (inst.constructionTime > 0) {
                                return this.unoverkill(actuallyDoClick, update,
                                    alreadyStartedUndoblocksSoDontStartMore, inst,
                                    type === C.CLICK_INST_SHIFT);
                            }
                            // TUTORIAL_DISABLE_UNBREACH check skipped
                            answer = this.tryToUnbreach(actuallyDoClick, update,
                                alreadyStartedUndoblocksSoDontStartMore, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                                type === C.CLICK_INST_SHIFT);
                            if (answer.canClick) {
                                return answer;
                            }
                            this.failure(displayErrorMsg, C.ERROR_UNBREACH_AFTER_OVERKILL, {
                                overkilled: this.state.helper.overkilled
                            });
                        }
                    } else if (inst.deadness === C.DEADNESS_SNIPED) {
                        answer = this.tryToUnsnipe(actuallyDoClick, update, inst,
                            type === C.CLICK_INST_SHIFT);
                        if (answer.canClick) {
                            return answer;
                        }
                        answer = this.tryToUndisrupt(actuallyDoClick, update, inst,
                            type === C.CLICK_INST_SHIFT);
                        if (answer.canClick) {
                            return answer;
                        }
                        if (this.state.haveOverkilled) {
                            this.failure(displayErrorMsg, C.ERROR_UNASSIGN_SNIPE_OVERKILL, {
                                inst: this.state.instIdToInst(inst.sniperId),
                                targetInst: inst,
                                wipedOut: this.state.helper.wipedOut,
                                breached: this.state.helper.breached,
                                overkilled: this.state.helper.overkilled
                            });
                        } else {
                            this.failure(displayErrorMsg, C.ERROR_UNSNIPE_DEFENDER_AFTER_WBO, {
                                inst: this.state.instIdToInst(inst.sniperId),
                                targetInst: inst,
                                wipedOut: this.state.helper.wipedOut,
                                breached: this.state.helper.breached,
                                overkilled: this.state.helper.overkilled
                            });
                        }
                    } else if (inst.deadness === C.DEADNESS_NETHERED) {
                        this.failure(displayErrorMsg, C.ERROR_NETHERED, { inst: inst });
                    } else {
                        C.ASSERT(false, "Code shouldn't get here.");
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // --- Own units: role-based dispatch ---

                // ROLE_DEFAULT — assign (use ability)
                if (inst.role === C.ROLE_DEFAULT) {
                    if (this.canAssign(displayErrorMsg, inst)) {
                        answer = new ClickResult(actuallyDoClick, true);
                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        }
                        // Auto-resolve partially-damaged inst if this ability gives attack
                        if (this.state.helper.partiallyDamagedInst !== null &&
                            inst.card.abilityScript !== null &&
                            inst.card.abilityScript.receive.attack > 0) {
                            tempClickResult = this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_INST,
                                this.state.helper.partiallyDamagedInst.instId);
                            if (!actuallyDoClick) {
                                answer.instsToHighlight = answer.instsToHighlight.concat(
                                    tempClickResult.instsToHighlight);
                            }
                        }

                        if (type === C.CLICK_INST_SHIFT) {
                            if (actuallyDoClick) {
                                if (inst.card.targetHas) {
                                    // Shift-click on targeting unit: fill all matching sources
                                    this.targetSources = this.instsStronglyEqualTo(inst);
                                    this.targetSources.sort((a, b) => this._compareInstBackward(a, b));
                                    /* STUB: UI-only — dispatch(SEND_TARGET_BEGIN), dispatch(SEND_REFRESH) */
                                    answer.moveResult = ClickResult.START_OF_CHAIN;
                                } else {
                                    insts = this.instsStronglyEqualTo(inst);
                                    insts.sort((a, b) => this._compareInstBackward(a, b));
                                    for (i = 0; i < insts.length; i++) {
                                        if (this.canAssign(false, insts[i])) {
                                            this.assignBeforeSaccing(update, animate,
                                                this.state.wouldBeSacced(insts[i].card.abilitySac, insts[i]));
                                            this.processOrder(update, animate,
                                                new Order(C.MOVE_ASSIGN, insts[i].instId, -1, -1, null,
                                                    this.state.scriptToInstIds(insts[i].card.abilityScript)),
                                                true);
                                        }
                                    }
                                    this.processStateHelperUpdate(update, animate);
                                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                                }
                            } else {
                                answer.instsToHighlight = this.instsStronglyEqualTo(inst);
                            }
                        } else if (actuallyDoClick) {
                            if (inst.card.targetHas) {
                                // Single click on targeting unit: enter target mode
                                this.targetSources = [inst];
                                /* STUB: UI-only — dispatch(SEND_TARGET_BEGIN), dispatch(SEND_REFRESH) */
                                answer.moveResult = ClickResult.START_OF_CHAIN;
                            } else if (this.inSwipe) {
                                this.assignBeforeSaccing(update, animate,
                                    this.state.wouldBeSacced(inst.card.abilitySac, inst));
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_ASSIGN, inst.instId, -1, -1, null,
                                        this.state.scriptToInstIds(inst.card.abilityScript)));
                                answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                            } else {
                                this.assignBeforeSaccing(update, animate,
                                    this.state.wouldBeSacced(inst.card.abilitySac, inst));
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_ASSIGN, inst.instId, -1, -1, null,
                                        this.state.scriptToInstIds(inst.card.abilityScript)));
                                this.swipePurpose = C.SWIPEPURPOSE_ASSIGN;
                                answer.moveResult = ClickResult.START_OF_CHAIN;
                                if (inst.cardName === 'Care Package') {
                                    this.swipePurpose = null;
                                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                                }
                            }
                        } else {
                            answer.instsToHighlight.push(inst);
                        }

                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                        }
                        return answer;
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // ROLE_ASSIGNED — unassign
                if (inst.role === C.ROLE_ASSIGNED) {
                    if (this.canUnassign(displayErrorMsg, inst)) {
                        answer = new ClickResult(actuallyDoClick, true);
                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        }
                        // Auto-resolve partially-damaged inst if ability gives attack
                        if (this.state.helper.partiallyDamagedInst !== null &&
                            inst.card.abilityCost.attack > 0) {
                            tempClickResult = this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_INST,
                                this.state.helper.partiallyDamagedInst.instId);
                            if (!actuallyDoClick) {
                                answer.instsToHighlight = answer.instsToHighlight.concat(
                                    tempClickResult.instsToHighlight);
                            }
                        }

                        if (type === C.CLICK_INST_SHIFT) {
                            if (actuallyDoClick) {
                                insts = this.instsStronglyEqualTo(inst);
                                insts.sort((a, b) => this._compareInstBackward(a, b));
                                for (i = 0; i < insts.length; i++) {
                                    if (!this.canUnassign(false, insts[i])) {
                                        break;
                                    }
                                    this.unbreakGlassBeforeUnassign(update, insts[i]);
                                    this.processOrder(update, animate,
                                        new Order(C.MOVE_UNASSIGN, insts[i].instId, insts[i].target,
                                            -1, null,
                                            State.cloneCreateIds(insts[i].abilityCreateIds)));
                                }
                                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                            } else {
                                answer.instsToHighlight = this.instsStronglyEqualTo(inst);
                            }
                        } else if (actuallyDoClick) {
                            if (this.inSwipe) {
                                this.unbreakGlassBeforeUnassign(update, inst);
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_UNASSIGN, inst.instId, inst.target,
                                        -1, null,
                                        State.cloneCreateIds(inst.abilityCreateIds)));
                                answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                            } else {
                                this.unbreakGlassBeforeUnassign(update, inst);
                                this.processOrder(update, animate,
                                    new Order(C.MOVE_UNASSIGN, inst.instId, inst.target,
                                        -1, null,
                                        State.cloneCreateIds(inst.abilityCreateIds)));
                                if (isRedirectedClickSoDontStartSwipe) {
                                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                                } else {
                                    this.swipePurpose = C.SWIPEPURPOSE_UNASSIGN;
                                    answer.moveResult = ClickResult.START_OF_CHAIN;
                                }
                            }
                        } else {
                            answer.instsToHighlight.push(inst);
                        }

                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                        }
                        return answer;
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // ROLE_SELLABLE — sell (unsummon/undo-buy)
                if (inst.role === C.ROLE_SELLABLE) {
                    if (this.canSell(displayErrorMsg, inst)) {
                        answer = new ClickResult(actuallyDoClick, true);
                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        }
                        // Auto-resolve partially-damaged inst if buy cost has attack
                        if (this.state.helper.partiallyDamagedInst !== null &&
                            inst.card.buyCost.attack > 0) {
                            tempClickResult = this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_INST,
                                this.state.helper.partiallyDamagedInst.instId);
                            if (!actuallyDoClick) {
                                answer.instsToHighlight = answer.instsToHighlight.concat(
                                    tempClickResult.instsToHighlight);
                            }
                        }

                        if (type === C.CLICK_INST_SHIFT) {
                            if (actuallyDoClick) {
                                insts = this.instsStronglyEqualTo(inst);
                                insts.sort((a, b) => this._compareInstBackward(a, b));
                                for (i = 0; i < insts.length; i++) {
                                    if (!this.canSell(false, insts[i])) {
                                        break;
                                    }
                                    this.processOrder(update, animate,
                                        new Order(C.MOVE_SELL, insts[i].instId, inst.instId,
                                            insts[i].card.cardId,
                                            State.cloneCreateIds(insts[i].buyCreateIds)));
                                }
                                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                            } else {
                                answer.instsToHighlight = this.instsStronglyEqualTo(inst);
                            }
                        } else if (actuallyDoClick) {
                            this.processOrder(update, animate,
                                new Order(C.MOVE_SELL, inst.instId, -1,
                                    inst.card.cardId,
                                    State.cloneCreateIds(inst.buyCreateIds)));
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        } else {
                            answer.instsToHighlight.push(inst);
                        }

                        if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                            !alreadyStartedUndoblocksSoDontStartMore) {
                            this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                        }
                        return answer;
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // ROLE_INERT — redirect to creator if possible, then error
                if (inst.role === C.ROLE_INERT) {
                    if (inst.creatorIdFromBuyOrAbility >= 0) {
                        tempClickResult = this.processClick(actuallyDoClick, update, animate,
                            false, false, true, type, inst.creatorIdFromBuyOrAbility);
                        if (tempClickResult.canClick) {
                            return tempClickResult;
                        }
                    }
                    // All TUTORIAL_CUSTOM_ERROR_MSGS checks skipped (always false)
                    if (inst.deadness === C.DEADNESS_SACCED) {
                        this.failure(displayErrorMsg, C.ERROR_CANT_CLICK_SACCED, { inst: inst });
                    } else if (inst.constructionTime > 0 && inst.creatorIdFromBuyOrAbility >= 0) {
                        this.failure(displayErrorMsg, C.ERROR_CANT_CLICK_CREATOR_UNSELLABLE, {
                            inst: inst,
                            creator: this.state.instIdToInst(inst.creatorIdFromBuyOrAbility)
                        });
                    } else if (inst.constructionTime > 0) {
                        this.failure(displayErrorMsg, C.ERROR_CANT_CLICK_UNDER_CONSTRUCTION, { inst: inst });
                    } else if (inst.card.abilityScript) {
                        if (inst.delay > 0) {
                            this.failure(displayErrorMsg, C.ERROR_CANT_CLICK_EXHAUST, { inst: inst });
                        } else {
                            this.failure(displayErrorMsg, C.ERROR_CANT_CLICK_OTHER, { inst: inst });
                        }
                    } else {
                        this.failure(displayErrorMsg, C.ERROR_UNIT_HAS_NO_CLICK_ABILITY, { inst: inst });
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                C.ASSERT(false, "Code shouldn't get here.");

            } // end PHASE_ACTION
            else {
                C.ASSERT(false, "Code shouldn't get here.");
            }
        }

        // ======================================================================
        // Non-inst click types
        // ======================================================================

        // --- END_SWIPE ---
        else if (type === C.CLICK_END_SWIPE) {
            if (this.inSwipe) {
                answer = new ClickResult(actuallyDoClick, true);
                C.ASSERT(actuallyDoClick, 'Click type END_SWIPE but not actually doing click.');
                if (this.inTargetMode) {
                    this.swipePurpose = null;
                    answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                } else {
                    this.swipePurpose = null;
                    this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    answer.moveResult = ClickResult.END_OF_CHAIN;
                }
                return answer;
            }
            return new ClickResult(actuallyDoClick, false);
        }

        // --- CANCEL_TARGET ---
        else if (type === C.CLICK_CANCEL_TARGET) {
            if (this.inTargetMode) {
                answer = new ClickResult(actuallyDoClick, true);
                C.ASSERT(actuallyDoClick, 'Click type CANCEL_TARGET but not actually doing click.');
                if (this.inSwipe) {
                    this.swipePurpose = null;
                }
                this.targetSources = null;
                this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                /* STUB: UI-only — dispatch(SEND_TARGET_END), dispatch(SEND_REFRESH) */
                answer.moveResult = ClickResult.END_OF_CHAIN;
                return answer;
            }
            C.ASSERT(false,
                'Should never (check legality of cancel target)/(attempt to cancel target) when not in target mode.');
            return new ClickResult(actuallyDoClick, false);
        }

        // --- CLICK_CARD / CLICK_CARD_SHIFT — buy ---
        else if (type === C.CLICK_CARD || type === C.CLICK_CARD_SHIFT) {
            card = this.state.cardIdToCard(id);
            if (this.canBuy(displayErrorMsg, card)) {
                answer = new ClickResult(actuallyDoClick, true);
                if (actuallyDoClick) {
                    if (this.inTargetMode) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                        endedSwipeOrTarget = true;
                    } else if (this.inSwipe) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_END_SWIPE);
                        endedSwipeOrTarget = true;
                    } else {
                        endedSwipeOrTarget = false;
                    }

                    if (type === C.CLICK_CARD_SHIFT) {
                        this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        this.assignBeforeSaccing(update, animate,
                            this.state.wouldBeSacced(card.buySac));
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BUY, this.state.nextInstId++, -1,
                                card.cardId, this.state.scriptToInstIds(card.buyScript)));
                        while (this.canBuy(false, card)) {
                            this.assignBeforeSaccing(update, animate,
                                this.state.wouldBeSacced(card.buySac));
                            this.processOrder(update, animate,
                                new Order(C.MOVE_BUY, this.state.nextInstId++, -1,
                                    card.cardId, this.state.scriptToInstIds(card.buyScript)));
                        }
                        this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    } else {
                        this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                        this.assignBeforeSaccing(update, animate,
                            this.state.wouldBeSacced(card.buySac));
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BUY, this.state.nextInstId++, -1,
                                card.cardId, this.state.scriptToInstIds(card.buyScript)));
                        this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    }
                    answer.moveResult = endedSwipeOrTarget ?
                        ClickResult.END_OF_CHAIN_DOUBLE_UNDO : ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.cardsToHighlight.push(card);
                }
                return answer;
            }
            return new ClickResult(actuallyDoClick, false);
        }

        // --- CLICK_SPACE — end phase / wipeout / confirm ---
        else if (type === C.CLICK_SPACE) {
            // Defense phase: end defense
            if (this.state.phase === C.PHASE_DEFENSE) {
                if (this.state.inEndDefense) {
                    answer = new ClickResult(actuallyDoClick, true);
                    if (actuallyDoClick) {
                        if (this.inTargetMode) {
                            this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                            endedSwipeOrTarget = true;
                        } else if (this.inSwipe) {
                            this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_END_SWIPE);
                            endedSwipeOrTarget = true;
                        } else {
                            endedSwipeOrTarget = false;
                        }
                        this.processOrder(update, animate, new Order(C.MOVE_END_DEFENSE));
                        answer.moveResult = endedSwipeOrTarget ?
                            ClickResult.END_OF_CHAIN_DOUBLE_UNDO : ClickResult.ITSELF_A_CHAIN;
                    } else {
                        answer.buttonsToHighlight.push(ClickResult.BUTTON_END_TURN);
                    }
                    return answer;
                }
                this.failure(displayErrorMsg, C.ERROR_END_DEFENSE);
                return new ClickResult(actuallyDoClick, false);
            }

            // Action phase: wipeout or enter confirm
            if (this.state.phase === C.PHASE_ACTION) {
                if (this.state.wouldWipeout) {
                    // TUTORIAL_MODE + errorbangs checks skipped (always false)
                    answer = new ClickResult(actuallyDoClick, true);
                    if (actuallyDoClick) {
                        if (this.inTargetMode) {
                            this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                            endedSwipeOrTarget = true;
                        } else if (this.inSwipe) {
                            this.processClick(actuallyDoClick, update, animate,
                                displayErrorMsg, true, true, C.CLICK_END_SWIPE);
                            endedSwipeOrTarget = true;
                        } else {
                            endedSwipeOrTarget = false;
                        }
                        this.processOrder(update, animate, new Order(C.MOVE_WIPEOUT));
                        answer.moveResult = endedSwipeOrTarget ?
                            ClickResult.END_OF_CHAIN_DOUBLE_UNDO : ClickResult.ITSELF_A_CHAIN;
                    } else {
                        answer.buttonsToHighlight.push(ClickResult.BUTTON_END_TURN);
                    }
                    return answer;
                }

                // Must wipeout/breach before ending turn
                if (this.state.glassBroken && !this.state.inEndBO) {
                    if (this.state.haveBOed) {
                        this.failure(displayErrorMsg, C.ERROR_END_BREACH);
                    } else if (this.state.haveWBOed) {
                        this.failure(displayErrorMsg, C.ERROR_DEAL_BREACH_DAMAGE);
                    } else {
                        this.failure(displayErrorMsg, C.ERROR_DEAL_BREACH_DAMAGE_NO_WIPEOUT);
                    }
                    return new ClickResult(actuallyDoClick, false);
                }

                // Errorbangs and softerrorbangs: skipped (TUTORIAL_MODE always false, errorbangs null)

                // Enter confirm
                answer = new ClickResult(actuallyDoClick, true);
                if (actuallyDoClick) {
                    if (this.inTargetMode) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                        endedSwipeOrTarget = true;
                    } else if (this.inSwipe) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_END_SWIPE);
                        endedSwipeOrTarget = true;
                    } else {
                        endedSwipeOrTarget = false;
                    }
                    this.processOrder(update, animate, new Order(C.MOVE_ENTER_CONFIRM));
                    answer.moveResult = endedSwipeOrTarget ?
                        ClickResult.END_OF_CHAIN_DOUBLE_UNDO : ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.buttonsToHighlight.push(ClickResult.BUTTON_END_TURN);
                }
                return answer;
            }

            // Confirm phase: commit
            if (this.state.phase === C.PHASE_CONFIRM) {
                answer = new ClickResult(actuallyDoClick, true);
                if (actuallyDoClick) {
                    if (this.inTargetMode) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_CANCEL_TARGET);
                        endedSwipeOrTarget = true;
                    } else if (this.inSwipe) {
                        this.processClick(actuallyDoClick, update, animate,
                            displayErrorMsg, true, true, C.CLICK_END_SWIPE);
                        endedSwipeOrTarget = true;
                    } else {
                        endedSwipeOrTarget = false;
                    }
                    this.processOrder(update, animate, new Order(C.MOVE_COMMIT));
                    answer.moveResult = endedSwipeOrTarget ?
                        ClickResult.END_OF_CHAIN_DOUBLE_UNDO : ClickResult.ITSELF_A_CHAIN;
                    if (this.state.result !== C.COLOR_NONE) {
                        answer.serverResult = ClickResult.SERVER_END_GAME;
                    } else {
                        answer.serverResult = ClickResult.SERVER_END_TURN;
                    }
                } else {
                    answer.buttonsToHighlight.push(ClickResult.BUTTON_END_TURN);
                }
                return answer;
            }

            C.ASSERT(false, "Code shouldn't get here.");
        }

        // --- CLICK_REVERT ---
        else if (type === C.CLICK_REVERT) {
            // TUTORIAL_SPECIAL_REVERTS check skipped (always false)
            if (this.inTargetMode || this.inSwipe) {
                this.failure(displayErrorMsg, C.ERROR_GET_OUT_OF_TARGET_OR_SWIPE);
                return new ClickResult(actuallyDoClick, false);
            }
            answer = new ClickResult(actuallyDoClick, true);
            if (actuallyDoClick) {
                this.processOrder(update, animate, new Order(C.ORDER_REVERT));
                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
            } else {
                answer.buttonsToHighlight.push(ClickResult.BUTTON_REVERT);
            }
            return answer;
        }

        // --- CLICK_UNDO ---
        else if (type === C.CLICK_UNDO) {
            if (this.undoStack.length > 0) {
                if (this.inTargetMode || this.inSwipe) {
                    this.failure(displayErrorMsg, C.ERROR_GET_OUT_OF_TARGET_OR_SWIPE);
                    return new ClickResult(actuallyDoClick, false);
                }
                answer = new ClickResult(actuallyDoClick, true);
                if (actuallyDoClick) {
                    this.undo(update);
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.buttonsToHighlight.push(ClickResult.BUTTON_UNDO);
                }
                return answer;
            }
            this.failure(displayErrorMsg, C.ERROR_UNDO);
            return new ClickResult(actuallyDoClick, false);
        }

        // --- CLICK_REDO ---
        else if (type === C.CLICK_REDO) {
            if (this.redoStack.length > 0) {
                if (this.inTargetMode || this.inSwipe) {
                    this.failure(displayErrorMsg, C.ERROR_GET_OUT_OF_TARGET_OR_SWIPE);
                    return new ClickResult(actuallyDoClick, false);
                }
                answer = new ClickResult(actuallyDoClick, true);
                if (actuallyDoClick) {
                    this.redo(update);
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.buttonsToHighlight.push(ClickResult.BUTTON_REDO);
                }
                return answer;
            }
            this.failure(displayErrorMsg, C.ERROR_REDO);
            return new ClickResult(actuallyDoClick, false);
        }

        C.ASSERT(false, 'Invalid click type.');
        return null;
    }

    // ======================================================================
    // processOrder (Controller.as:1279-1290)
    // ======================================================================

    processOrder(update, animate, order, delayStateHelperUpdate) {
        if (delayStateHelperUpdate === undefined) delayStateHelperUpdate = false;
        if (order.type !== C.MOVE_EMOTE) {
            this.undoStack.push(order);
            this.redoStack = [];
            this.processMoveOrRevert(update, animate, order, delayStateHelperUpdate);
        }
    }

    // ======================================================================
    // undo (Controller.as:1292-1334)
    // ======================================================================

    undo(update) {
        let tempOrder = this.undoStack.pop();
        C.ASSERT(tempOrder.type !== C.MOVE_COMMIT, 'Tried to undo a commit.');
        this.redoStack.push(tempOrder);

        if (tempOrder.type === C.MOVE_END_DEFENSE) {
            this.state = this.endDefendStack.pop();
            /* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */
        } else if (tempOrder.type === C.MOVE_ENTER_CONFIRM) {
            this.state = this.endActionStack.pop();
            /* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */
        } else if (tempOrder.type === C.ORDER_REVERT) {
            this.state = this.revertFromStack.pop();
            /* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */
        } else if (tempOrder.type === C.ORDER_END_UNDOBLOCK) {
            while (true) {
                tempOrder = this.undoStack.pop();
                this.redoStack.push(tempOrder);
                if (tempOrder.type === C.ORDER_START_UNDOBLOCK) {
                    break;
                }
                if (tempOrder.type !== C.MOVE_EMOTE) {
                    tempOrder = tempOrder.inverse();
                    this.processMoveOrRevert(update, false, tempOrder);
                }
            }
        } else if (tempOrder.type !== C.MOVE_EMOTE) {
            tempOrder = tempOrder.inverse();
            this.processMoveOrRevert(update, false, tempOrder);
        }
    }

    // ======================================================================
    // redo (Controller.as:1336-1358)
    // ======================================================================

    redo(update) {
        let tempOrder = this.redoStack.pop();
        C.ASSERT(tempOrder.type !== C.MOVE_COMMIT, 'Tried to redo a commit.');
        this.undoStack.push(tempOrder);

        if (tempOrder.type === C.ORDER_START_UNDOBLOCK) {
            while (true) {
                tempOrder = this.redoStack.pop();
                this.undoStack.push(tempOrder);
                if (tempOrder.type === C.ORDER_END_UNDOBLOCK) {
                    break;
                }
                this.processMoveOrRevert(update, false, tempOrder);
            }
        } else {
            this.processMoveOrRevert(update, false, tempOrder);
        }
    }

    // ======================================================================
    // processStateHelperUpdate (Controller.as:1360-1364)
    // ======================================================================

    processStateHelperUpdate(update, animate) {
        this.state.helper.update(this.state);
        /* STUB: UI-only — state.dispatch(SEND_REFRESH) */
    }

    // ======================================================================
    // processMoveOrRevert (Controller.as:1366-1408)
    // ======================================================================

    processMoveOrRevert(update, animate, order, delayStateHelperUpdate) {
        if (delayStateHelperUpdate === undefined) delayStateHelperUpdate = false;

        if (order.type === C.ORDER_REVERT) {
            this.revertFromStack.push(this.state);
            if (this.state.phase === C.PHASE_DEFENSE) {
                this.state = this.beginTurnState.clone();
            } else if (this.state.phase === C.PHASE_ACTION) {
                if (this.endDefendStack.length > 0) {
                    this.state = this.endDefendStack[this.endDefendStack.length - 1].clone();
                } else {
                    this.state = this.beginTurnState.clone();
                }
            } else if (this.state.phase === C.PHASE_CONFIRM) {
                this.state = this.endActionStack[this.endActionStack.length - 1].clone();
            }
            /* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */
        } else if (order.type !== C.ORDER_START_UNDOBLOCK && order.type !== C.ORDER_END_UNDOBLOCK) {
            if (order.type === C.MOVE_END_DEFENSE) {
                this.endDefendStack.push(this.state.clone());
            } else if (order.type === C.MOVE_ENTER_CONFIRM) {
                this.endActionStack.push(this.state.clone());
            }
            this.state.processMove(order.type, order.instId, order.targetId,
                order.cardId, order.buyCreateIds, order.abilityCreateIds, delayStateHelperUpdate);
            if (order.type === C.MOVE_COMMIT && !this.state.finished &&
                this.state.controlledLane === -1) {
                this.newTurn();
            }
        }
    }

    // ======================================================================
    // newTurn (Controller.as:1410-1420)
    // ======================================================================

    newTurn() {
        this.swipePurpose = null;
        this.targetSources = null;
        this.beginTurnState = this.state.clone();
        this.undoStack = [];
        this.redoStack = [];
        this.endDefendStack = [];
        this.endActionStack = [];
        this.revertFromStack = [];
    }

    // ======================================================================
    // canAssign (Controller.as:1422-1473)
    // ======================================================================

    canAssign(displayErrorMsg, inst) {
        if (inst.role !== C.ROLE_DEFAULT) {
            return false;
        }
        if (inst.health < inst.card.healthUsed) {
            this.failure(displayErrorMsg, C.ERROR_ASSIGN_HP, { inst: inst });
            return false;
        }
        if (inst.charge < inst.card.chargeUsed) {
            this.failure(displayErrorMsg, C.ERROR_ASSIGN_CHARGE, { inst: inst });
            return false;
        }
        const tempManaType = this.state.turnMana.hasFailedWith(inst.card.abilityCost);
        if (tempManaType >= 0) {
            this.failure(displayErrorMsg, C.ERROR_ASSIGN_RESOURCE, {
                inst: inst,
                manaType: tempManaType,
                turn: this.state.turn
            });
            return false;
        }
        const tempCardName = this.sacHasFailedWith(inst.card.abilitySac, inst);
        if (tempCardName !== null) {
            this.failure(displayErrorMsg, C.ERROR_ASSIGN_SAC, {
                inst: inst,
                cardToSac: this.state.cardNameToCard(tempCardName)
            });
            return false;
        }
        if (inst.card.abilityNetherfy && this.state.wouldBeNetherfied() === null) {
            this.failure(displayErrorMsg, C.ERROR_NETHERFY, { inst: inst });
            return false;
        }
        if (inst.card.targetHas && this.instsSatisfyingCondition(inst.card.condition).length === 0) {
            this.failure(displayErrorMsg, C.ERROR_ASSIGN_NO_TARGET, { inst: inst });
            return false;
        }
        if (this.state.haveOverkilled && inst.cardName === 'Valkyrion') {
            this.failure(displayErrorMsg, C.ERROR_CREATE_ENEMY_UNITS_DURING_OVERKILL, { inst: inst });
            return false;
        }
        return true;
    }

    // ======================================================================
    // canUnassign (Controller.as:1475-1556)
    // ======================================================================

    canUnassign(displayErrorMsg, inst) {
        let tempManaType = 0;
        let i = 0;
        let j = 0;
        let tempInst = null;
        let targetInst = null;
        let snipecard = null;

        // TUTORIAL_DISABLE_UNASSIGN check skipped (always false)

        if (inst.card.abilityScript !== null) {
            tempManaType = this.state.turnMana.hasFailedWith(inst.card.abilityScript.receive);
            if (tempManaType >= 0) {
                this.failure(displayErrorMsg, C.ERROR_UNASSIGN_RESOURCE, {
                    inst: inst,
                    manaType: tempManaType
                });
                return false;
            }
            for (i = 0; i < inst.abilityCreateIds.length; i++) {
                for (j = 0; j < inst.abilityCreateIds[i].length; j++) {
                    tempInst = this.state.instIdToInst(inst.abilityCreateIds[i][j]);
                    if (tempInst.damage > 0 || tempInst.dead) {
                        this.failure(displayErrorMsg, C.ERROR_UNASSIGN_CREATE, {
                            inst: inst,
                            created: tempInst
                        });
                        return false;
                    }
                }
            }
        }

        if (inst.card.targetAction === C.TARGETACTION_DISRUPT) {
            targetInst = this.state.instIdToInst(inst.target);
            if (targetInst.disruptDamage - inst.card.targetAmount < targetInst.damageItCanTake + targetInst.damage) {
                if (!targetInst.dead && this.state.haveWBOed) {
                    this.failure(displayErrorMsg, C.ERROR_UNASSIGN_DISRUPT_BREACH, { inst: inst });
                    return false;
                }
                if (targetInst.deadness === C.DEADNESS_NETHERED) {
                    this.failure(displayErrorMsg, C.ERROR_UNASSIGN_DISRUPT_NETHER_WARRIOR, { inst: inst });
                    return false;
                }
                if (targetInst.deadness === C.DEADNESS_SNIPED) {
                    snipecard = this.state.instIdToInst(targetInst.sniperId).card;
                    if (snipecard.condition.hasOwnProperty(C.CONDITION_HEALTH_AT_MOST) &&
                        targetInst.health + targetInst.damage > snipecard.condition[C.CONDITION_HEALTH_AT_MOST]) {
                        this.failure(displayErrorMsg, C.ERROR_UNASSIGN_DISRUPT_BREACH, { inst: inst });
                        return false;
                    }
                }
            }
        }

        if (inst.card.targetAction === C.TARGETACTION_SNIPE) {
            targetInst = this.state.instIdToInst(inst.target);
            if (this.state.haveWBOed && targetInst.blocking) {
                this.failure(displayErrorMsg, C.ERROR_UNASSIGN_SNIPE_BREACH, { inst: inst });
                return false;
            }
            if (this.state.haveOverkilled) {
                this.failure(displayErrorMsg, C.ERROR_UNASSIGN_SNIPE_OVERKILL, { inst: inst });
                return false;
            }
        }

        return true;
    }

    // ======================================================================
    // canBuy (Controller.as:1558-1596)
    // ======================================================================

    canBuy(displayErrorMsg, card) {
        // TUTORIAL_DISABLE_BUY_AFTER_BREACH check skipped (always false)
        C.ASSERT(this.state.phase !== C.PHASE_CONFIRM);
        if (this.state.phase === C.PHASE_DEFENSE) {
            this.failure(displayErrorMsg, C.ERROR_BUY_DEFENSE);
            return false;
        }
        if (this.state.turnBought()[card.cardId] >= this.state.turnSupply()[card.cardId]) {
            this.failure(displayErrorMsg, C.ERROR_BUY_SUPPLY, { card: card });
            return false;
        }
        const tempManaType = this.state.turnMana.hasFailedWith(card.buyCost);
        if (tempManaType >= 0) {
            this.failure(displayErrorMsg, C.ERROR_BUY_RESOURCE, {
                card: card,
                manaType: tempManaType,
                turn: this.state.turn
            });
            return false;
        }
        const tempCardName = this.sacHasFailedWith(card.buySac);
        if (tempCardName !== null) {
            this.failure(displayErrorMsg, C.ERROR_BUY_SAC, {
                card: card,
                cardToSac: this.state.cardNameToCard(tempCardName)
            });
            return false;
        }
        return true;
    }

    // ======================================================================
    // canSell (Controller.as:1598-1637)
    // ======================================================================

    canSell(displayErrorMsg, inst) {
        let tempManaType = 0;
        let i = 0;
        let j = 0;
        let tempInst = null;

        // TUTORIAL_DISABLE_SELL check skipped (always false)

        if (inst.card.buyScript !== null) {
            tempManaType = this.state.turnMana.hasFailedWith(inst.card.buyScript.receive);
            if (tempManaType >= 0) {
                this.failure(displayErrorMsg, C.ERROR_SELL_RESOURCE, {
                    inst: inst,
                    manaType: tempManaType
                });
                return false;
            }
            for (i = 0; i < inst.buyCreateIds.length; i++) {
                for (j = 0; j < inst.buyCreateIds[i].length; j++) {
                    tempInst = this.state.instIdToInst(inst.buyCreateIds[i][j]);
                    if (tempInst.damage > 0 || tempInst.dead) {
                        this.failure(displayErrorMsg, C.ERROR_SELL_CREATE, {
                            inst: inst,
                            created: tempInst
                        });
                        return false;
                    }
                }
            }
        }
        return true;
    }

    // ======================================================================
    // tryToMelee (Controller.as:1639-1701)
    // ======================================================================

    tryToMelee(actuallyDoClick, update, animate, inst, shift) {
        let insts = null;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (this.state.turnMana.attack >= inst.health) {
            if (shift) {
                if (actuallyDoClick) {
                    insts = this.instsWeaklyEqualTo(inst);
                    insts.sort((a, b) => this._compareInstBackward(a, b));
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    for (i = 0; i < insts.length; i++) {
                        if (this.state.turnMana.attack < insts[i].health) {
                            break;
                        }
                        this.processOrder(update, animate, new Order(C.MOVE_MELEE, insts[i].instId));
                    }
                    this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                }
            } else if (actuallyDoClick) {
                if (this.inSwipe) {
                    if (this.swipePurpose === C.SWIPEPURPOSE_MELEE ||
                        this.swipePurpose === C.SWIPEPURPOSE_UNMELEE) {
                        this.processOrder(update, animate, new Order(C.MOVE_MELEE, inst.instId));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        answer.canClick = false;
                    }
                } else {
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    this.processOrder(update, animate, new Order(C.MOVE_MELEE, inst.instId));
                    this.swipePurpose = C.SWIPEPURPOSE_MELEE;
                    answer.moveResult = ClickResult.START_OF_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(inst);
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToWipeout (Controller.as:1703-1730)
    // ======================================================================

    tryToWipeout(actuallyDoClick, update, animate) {
        const answer = new ClickResult(actuallyDoClick, true);
        if (this.state.wouldWipeout) {
            if (actuallyDoClick) {
                if (this.inSwipe) {
                    answer.canClick = false;
                } else {
                    this.processOrder(update, animate, new Order(C.MOVE_WIPEOUT));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                }
            } else {
                answer.instsToHighlight = this.state.helper.oppDefenders;
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToBreach (Controller.as:1732-1797)
    // ======================================================================

    tryToBreach(actuallyDoClick, update, animate, inst, shift) {
        let insts = null;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (this.state.canBreach && this.state.turnMana.attack >= inst.damageReqdToInjure) {
            if (shift) {
                if (actuallyDoClick) {
                    insts = this.instsWeaklyEqualTo(inst);
                    insts.sort((a, b) => this._compareInstBackward(a, b));
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    for (i = 0; i < insts.length; i++) {
                        if (this.state.turnMana.attack < insts[i].damageReqdToInjure) {
                            break;
                        }
                        this.breakGlassBeforeKilling(update, animate);
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BREACH_OR_OVERKILL, insts[i].instId, -1, -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    }
                    this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                }
            } else if (actuallyDoClick) {
                if (this.inSwipe) {
                    if (this.swipePurpose === C.SWIPEPURPOSE_BREACH ||
                        this.swipePurpose === C.SWIPEPURPOSE_UNBREACH) {
                        this.breakGlassBeforeKilling(update, animate);
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BREACH_OR_OVERKILL, inst.instId, -1, -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        answer.canClick = false;
                    }
                } else {
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    this.breakGlassBeforeKilling(update, animate);
                    this.processOrder(update, animate,
                        new Order(C.MOVE_BREACH_OR_OVERKILL, inst.instId, -1, -1, null,
                            inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    this.swipePurpose = C.SWIPEPURPOSE_BREACH;
                    answer.moveResult = ClickResult.START_OF_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(inst);
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToOverkill (Controller.as:1799-1864)
    // ======================================================================

    tryToOverkill(actuallyDoClick, update, animate, inst, shift) {
        let insts = null;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (this.state.canOverkill && this.state.turnMana.attack >= inst.damageReqdToInjure) {
            if (shift) {
                if (actuallyDoClick) {
                    insts = this.instsWeaklyEqualTo(inst);
                    insts.sort((a, b) => this._compareInstBackward(a, b));
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    for (i = 0; i < insts.length; i++) {
                        if (this.state.turnMana.attack < insts[i].damageReqdToInjure) {
                            break;
                        }
                        this.breakGlassBeforeKilling(update, animate);
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BREACH_OR_OVERKILL, insts[i].instId, -1, -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    }
                    this.processOrder(update, animate, new Order(C.ORDER_END_UNDOBLOCK));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                }
            } else if (actuallyDoClick) {
                if (this.inSwipe) {
                    if (this.swipePurpose === C.SWIPEPURPOSE_OVERKILL ||
                        this.swipePurpose === C.SWIPEPURPOSE_UNOVERKILL) {
                        this.breakGlassBeforeKilling(update, animate);
                        this.processOrder(update, animate,
                            new Order(C.MOVE_BREACH_OR_OVERKILL, inst.instId, -1, -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        answer.canClick = false;
                    }
                } else {
                    this.processOrder(update, animate, new Order(C.ORDER_START_UNDOBLOCK));
                    this.breakGlassBeforeKilling(update, animate);
                    this.processOrder(update, animate,
                        new Order(C.MOVE_BREACH_OR_OVERKILL, inst.instId, -1, -1, null,
                            inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    this.swipePurpose = C.SWIPEPURPOSE_OVERKILL;
                    answer.moveResult = ClickResult.START_OF_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(inst);
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToUnmelee (Controller.as:1866-1930)
    // ======================================================================

    tryToUnmelee(actuallyDoClick, update, inst, shift) {
        let insts = null;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (!(this.state.haveWBOed && inst.blocking) && !this.state.haveOverkilled) {
            if (this.state.helper.partiallyDamagedInst !== null) {
                return this.processClick(actuallyDoClick, update, false, false, false, true,
                    C.CLICK_INST, this.state.helper.partiallyDamagedInst.instId);
            }
            if (shift) {
                if (actuallyDoClick) {
                    insts = this.instsWeaklyEqualTo(inst);
                    this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
                    for (i = 0; i < insts.length; i++) {
                        this.unbreakGlassBeforeUnkilling(update, insts[i]);
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNMELEE, insts[i].instId, inst.instId));
                    }
                    this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                }
            } else if (actuallyDoClick) {
                if (this.inSwipe) {
                    if (this.swipePurpose === C.SWIPEPURPOSE_UNMELEE ||
                        this.swipePurpose === C.SWIPEPURPOSE_MELEE) {
                        this.unbreakGlassBeforeUnkilling(update, inst);
                        this.processOrder(update, false, new Order(C.MOVE_UNMELEE, inst.instId));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        answer.canClick = false;
                    }
                } else {
                    this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
                    this.unbreakGlassBeforeUnkilling(update, inst);
                    this.processOrder(update, false, new Order(C.MOVE_UNMELEE, inst.instId));
                    this.swipePurpose = C.SWIPEPURPOSE_UNMELEE;
                    answer.moveResult = ClickResult.START_OF_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(inst);
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToUnwipeout (Controller.as:1932-1959)
    // ======================================================================

    tryToUnwipeout(actuallyDoClick, update) {
        const answer = new ClickResult(actuallyDoClick, true);
        if (!this.state.haveBOed) {
            if (actuallyDoClick) {
                if (this.inSwipe) {
                    answer.canClick = false;
                } else {
                    this.processOrder(update, false, new Order(C.MOVE_UNWIPEOUT));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                }
            } else {
                answer.instsToHighlight = this.state.helper.wipedOut;
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToUnbreach (Controller.as:1961-2100)
    // ======================================================================

    tryToUnbreach(actuallyDoClick, update, alreadyStartedUndoblocksSoDontStartMore, inst, shift) {
        let sniper = null;
        let insts = null;
        let location = 0;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (!this.state.haveOverkilled) {
            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                !alreadyStartedUndoblocksSoDontStartMore) {
                this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
            }

            if (this.state.helper.partiallyDamagedInst !== null) {
                // If partially damaged inst is dead from sniping, and sniper condition
                // prevents unbreach, unassign the sniper first
                if (this.state.helper.partiallyDamagedInst.dead) {
                    C.ASSERT(this.state.helper.partiallyDamagedInst.deadness === C.DEADNESS_SNIPED,
                        'Partially damaged Inst is dead, but not from sniping.');
                    sniper = this.state.instIdToInst(this.state.helper.partiallyDamagedInst.sniperId);
                    if (sniper.card.condition.hasOwnProperty(C.CONDITION_HEALTH_AT_MOST) &&
                        this.state.helper.partiallyDamagedInst.health +
                        this.state.helper.partiallyDamagedInst.damage >
                        sniper.card.condition[C.CONDITION_HEALTH_AT_MOST]) {
                        if (actuallyDoClick) {
                            this.processOrder(update, false,
                                new Order(C.MOVE_UNASSIGN, sniper.instId, sniper.target,
                                    -1, null, State.cloneCreateIds(sniper.abilityCreateIds)));
                        } else {
                            answer.instsToHighlight.push(sniper);
                        }
                    }
                }

                if (shift) {
                    insts = this.instsWeaklyEqualTo(inst);
                    location = insts.indexOf(this.state.helper.partiallyDamagedInst) | 0;
                    if (location >= 0) {
                        if (actuallyDoClick) {
                            this.processOrder(update, false,
                                new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                    this.state.helper.partiallyDamagedInst.instId, inst.instId,
                                    -1, null,
                                    inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                            insts.splice(location, 1);
                            for (i = 0; i < insts.length; i++) {
                                this.processOrder(update, false,
                                    new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                        insts[i].instId, inst.instId,
                                        -1, null,
                                        inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                            }
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        } else {
                            answer.instsToHighlight = insts;
                        }
                    } else if (actuallyDoClick) {
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                this.state.helper.partiallyDamagedInst.instId, -1,
                                -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                        answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                    } else {
                        answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
                    }
                } else if (actuallyDoClick) {
                    if (inst.instId === this.state.helper.partiallyDamagedInst.instId) {
                        if (this.inSwipe) {
                            this.processOrder(update, false,
                                new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                    this.state.helper.partiallyDamagedInst.instId, -1,
                                    -1, null,
                                    inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                            answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                        } else {
                            this.processOrder(update, false,
                                new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                    this.state.helper.partiallyDamagedInst.instId, -1,
                                    -1, null,
                                    inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                            answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                        }
                    } else {
                        // Different inst: use partiallyDamagedInst's deathScript
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                this.state.helper.partiallyDamagedInst.instId, -1,
                                -1, null,
                                this.state.helper.partiallyDamagedInst.card.deathScript ?
                                    this.state.scriptToInstIds(this.state.helper.partiallyDamagedInst.card.deathScript) :
                                    null));
                        answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                    }
                } else {
                    answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
                }
            } else if (shift) {
                if (actuallyDoClick) {
                    insts = this.instsWeaklyEqualTo(inst);
                    for (i = 0; i < insts.length; i++) {
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                insts[i].instId, inst.instId,
                                -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    }
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
                }
            } else if (actuallyDoClick) {
                if (this.inSwipe) {
                    if (this.swipePurpose === C.SWIPEPURPOSE_UNBREACH ||
                        this.swipePurpose === C.SWIPEPURPOSE_BREACH) {
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, inst.instId, -1,
                                -1, null,
                                inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        answer.canClick = false;
                    }
                } else {
                    this.processOrder(update, false,
                        new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, inst.instId, -1,
                            -1, null,
                            inst.card.deathScript ? this.state.scriptToInstIds(inst.card.deathScript) : null));
                    this.swipePurpose = C.SWIPEPURPOSE_UNBREACH;
                    answer.moveResult = ClickResult.START_OF_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(inst);
            }

            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode &&
                !alreadyStartedUndoblocksSoDontStartMore) {
                this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // unoverkill (Controller.as:2102-2214)
    // ======================================================================

    unoverkill(actuallyDoClick, update, alreadyStartedUndoblocksSoDontStartMore, inst, shift) {
        let insts = null;
        let location = 0;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (this.state.helper.partiallyDamagedInst !== null) {
            if (shift) {
                insts = this.instsWeaklyEqualTo(inst);
                location = insts.indexOf(this.state.helper.partiallyDamagedInst) | 0;
                if (location >= 0) {
                    if (actuallyDoClick) {
                        this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                this.state.helper.partiallyDamagedInst.instId, inst.instId));
                        insts.splice(location, 1);
                        for (i = 0; i < insts.length; i++) {
                            this.processOrder(update, false,
                                new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, insts[i].instId, inst.instId));
                        }
                        this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
                        answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                    } else {
                        answer.instsToHighlight = insts;
                    }
                } else if (actuallyDoClick) {
                    this.processOrder(update, false,
                        new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                            this.state.helper.partiallyDamagedInst.instId));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
                }
            } else if (actuallyDoClick) {
                if (inst.instId === this.state.helper.partiallyDamagedInst.instId) {
                    if (this.inSwipe) {
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                this.state.helper.partiallyDamagedInst.instId));
                        answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                    } else {
                        this.processOrder(update, false,
                            new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                                this.state.helper.partiallyDamagedInst.instId));
                        answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                    }
                } else {
                    this.processOrder(update, false,
                        new Order(C.MOVE_UNBREACH_OR_UNOVERKILL,
                            this.state.helper.partiallyDamagedInst.instId));
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                }
            } else {
                answer.instsToHighlight.push(this.state.helper.partiallyDamagedInst);
            }
        } else if (shift) {
            if (actuallyDoClick) {
                insts = this.instsWeaklyEqualTo(inst);
                this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
                for (i = 0; i < insts.length; i++) {
                    this.processOrder(update, false,
                        new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, insts[i].instId, inst.instId));
                }
                this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
                answer.moveResult = ClickResult.ITSELF_A_CHAIN;
            } else {
                answer.instsToHighlight = this.instsWeaklyEqualTo(inst);
            }
        } else if (actuallyDoClick) {
            if (this.inSwipe) {
                if (this.swipePurpose === C.SWIPEPURPOSE_OVERKILL ||
                    this.swipePurpose === C.SWIPEPURPOSE_UNOVERKILL) {
                    this.processOrder(update, false,
                        new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, inst.instId));
                    answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                } else {
                    answer.canClick = false;
                }
            } else {
                this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
                this.processOrder(update, false,
                    new Order(C.MOVE_UNBREACH_OR_UNOVERKILL, inst.instId));
                this.swipePurpose = C.SWIPEPURPOSE_UNOVERKILL;
                answer.moveResult = ClickResult.START_OF_CHAIN;
            }
        } else {
            answer.instsToHighlight.push(inst);
        }
        return answer;
    }

    // ======================================================================
    // tryToUndisrupt (Controller.as:2216-2310)
    // ======================================================================

    tryToUndisrupt(actuallyDoClick, update, inst, shift) {
        let allDisruptors = null;
        let insts = null;
        let i = 0;
        let j = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (inst.disruptorIds.length > 0 && !(!inst.dead && this.state.haveWBOed)) {
            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode) {
                this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
            }

            allDisruptors = [];
            if (shift) {
                insts = this.instsWeaklyEqualTo(inst);
                for (i = 0; i < insts.length; i++) {
                    for (j = 0; j < insts[i].disruptorIds.length; j++) {
                        allDisruptors.push(this.state.instIdToInst(insts[i].disruptorIds[j]));
                    }
                }
                if (actuallyDoClick) {
                    for (i = 0; i < allDisruptors.length; i++) {
                        this.unbreakGlassBeforeUnassign(update, allDisruptors[i]);
                        this.processClick(actuallyDoClick, update, false, false, true, true,
                            C.CLICK_INST, allDisruptors[i].instId);
                    }
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    for (i = 0; i < allDisruptors.length; i++) {
                        answer.instsToHighlight = answer.instsToHighlight.concat(
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allDisruptors[i].instId).instsToHighlight);
                    }
                }
            } else {
                for (i = 0; i < inst.disruptorIds.length; i++) {
                    allDisruptors.push(this.state.instIdToInst(inst.disruptorIds[i]));
                }
                if (actuallyDoClick) {
                    if (this.inSwipe) {
                        if (this.swipePurpose === C.SWIPEPURPOSE_UNDISRUPT) {
                            for (i = 0; i < allDisruptors.length; i++) {
                                this.unbreakGlassBeforeUnassign(update, allDisruptors[i]);
                                this.processClick(actuallyDoClick, update, false, false, true, true,
                                    C.CLICK_INST, allDisruptors[i].instId);
                            }
                            answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                        } else {
                            answer.canClick = false;
                        }
                    } else {
                        for (i = 0; i < allDisruptors.length; i++) {
                            this.unbreakGlassBeforeUnassign(update, allDisruptors[i]);
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allDisruptors[i].instId);
                        }
                        this.swipePurpose = C.SWIPEPURPOSE_UNDISRUPT;
                        answer.moveResult = ClickResult.START_OF_CHAIN;
                    }
                } else {
                    for (i = 0; i < allDisruptors.length; i++) {
                        answer.instsToHighlight = answer.instsToHighlight.concat(
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allDisruptors[i].instId).instsToHighlight);
                    }
                }
            }

            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode) {
                this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // tryToUnsnipe (Controller.as:2312-2399)
    // ======================================================================

    tryToUnsnipe(actuallyDoClick, update, inst, shift) {
        let allSnipers = null;
        let insts = null;
        let i = 0;
        const answer = new ClickResult(actuallyDoClick, true);

        if (this.canUnassign(false, this.state.instIdToInst(inst.sniperId))) {
            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode) {
                this.processOrder(update, false, new Order(C.ORDER_START_UNDOBLOCK));
            }

            allSnipers = [];
            if (shift) {
                insts = this.instsWeaklyEqualTo(inst);
                for (i = 0; i < insts.length; i++) {
                    allSnipers.push(this.state.instIdToInst(insts[i].sniperId));
                }
                if (actuallyDoClick) {
                    for (i = 0; i < allSnipers.length; i++) {
                        this.unbreakGlassBeforeUnassign(update, allSnipers[i]);
                        this.processClick(actuallyDoClick, update, false, false, true, true,
                            C.CLICK_INST, allSnipers[i].instId);
                    }
                    answer.moveResult = ClickResult.ITSELF_A_CHAIN;
                } else {
                    for (i = 0; i < allSnipers.length; i++) {
                        answer.instsToHighlight = answer.instsToHighlight.concat(
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allSnipers[i].instId).instsToHighlight);
                    }
                }
            } else {
                allSnipers.push(this.state.instIdToInst(inst.sniperId));
                if (actuallyDoClick) {
                    if (this.inSwipe) {
                        if (this.swipePurpose === C.SWIPEPURPOSE_UNSNIPE) {
                            for (i = 0; i < allSnipers.length; i++) {
                                this.unbreakGlassBeforeUnassign(update, allSnipers[i]);
                                this.processClick(actuallyDoClick, update, false, false, true, true,
                                    C.CLICK_INST, allSnipers[i].instId);
                            }
                            answer.moveResult = ClickResult.MIDDLE_OF_CHAIN;
                        } else {
                            answer.canClick = false;
                        }
                    } else {
                        for (i = 0; i < allSnipers.length; i++) {
                            this.unbreakGlassBeforeUnassign(update, allSnipers[i]);
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allSnipers[i].instId);
                        }
                        this.swipePurpose = C.SWIPEPURPOSE_UNSNIPE;
                        answer.moveResult = ClickResult.START_OF_CHAIN;
                    }
                } else {
                    for (i = 0; i < allSnipers.length; i++) {
                        answer.instsToHighlight = answer.instsToHighlight.concat(
                            this.processClick(actuallyDoClick, update, false, false, true, true,
                                C.CLICK_INST, allSnipers[i].instId).instsToHighlight);
                    }
                }
            }

            if (actuallyDoClick && !this.inSwipe && !this.inTargetMode) {
                this.processOrder(update, false, new Order(C.ORDER_END_UNDOBLOCK));
            }
        } else {
            answer.canClick = false;
        }
        return answer;
    }

    // ======================================================================
    // instsWeaklyEqualTo (Controller.as:2401-2415)
    // ======================================================================

    instsWeaklyEqualTo(model) {
        const answer = [];
        this.state.table.forEach((inst) => {
            if (inst.weaklyEqualTo(model)) {
                answer.push(inst);
            }
        });
        return answer;
    }

    // ======================================================================
    // instsStronglyEqualTo (Controller.as:2417-2431)
    // ======================================================================

    instsStronglyEqualTo(model) {
        const answer = [];
        this.state.table.forEach((inst) => {
            if (inst.stronglyEqualTo(model)) {
                answer.push(inst);
            }
        });
        return answer;
    }

    // ======================================================================
    // sacHasFailedWith (Controller.as:2433-2443)
    // ======================================================================

    sacHasFailedWith(sac, originInst) {
        if (originInst === undefined) originInst = null;
        for (let i = 0; i < sac.length; i++) {
            if (this.state.allCardsOfColorWithName(
                    this.state.turn, sac[i].cardName, false, false, false, originInst).length <
                sac[i].multiplicity) {
                return sac[i].cardName;
            }
        }
        return null;
    }

    // ======================================================================
    // assignBeforeSaccing (Controller.as:2445-2458)
    // ======================================================================

    assignBeforeSaccing(update, animate, wouldBeSacced) {
        for (let i = 0; i < wouldBeSacced.length; i++) {
            if (wouldBeSacced[i].role === C.ROLE_DEFAULT &&
                !wouldBeSacced[i].card.abilityScript.selfsac) {
                if (this.state.helper.partiallyDamagedInst !== null &&
                    wouldBeSacced[i].card.abilityScript !== null &&
                    wouldBeSacced[i].card.abilityScript.receive.attack > 0) {
                    this.processClick(true, update, animate, false, true, true,
                        C.CLICK_INST, this.state.helper.partiallyDamagedInst.instId);
                }
                this.processOrder(update, animate,
                    new Order(C.MOVE_ASSIGN, wouldBeSacced[i].instId, -1, -1, null,
                        this.state.scriptToInstIds(wouldBeSacced[i].card.abilityScript)));
            }
        }
    }

    // ======================================================================
    // breakGlassBeforeKilling (Controller.as:2460-2466)
    // ======================================================================

    breakGlassBeforeKilling(update, animate) {
        if (!this.state.glassBroken) {
            this.processOrder(update, animate, new Order(C.MOVE_WIPEOUT));
        }
    }

    // ======================================================================
    // unbreakGlassBeforeUnkilling (Controller.as:2468-2474)
    // ======================================================================

    unbreakGlassBeforeUnkilling(update, inst) {
        if (this.state.glassBroken && inst.blocking) {
            this.processOrder(update, false, new Order(C.MOVE_UNWIPEOUT));
        }
    }

    // ======================================================================
    // unbreakGlassBeforeUnassign (Controller.as:2476-2498)
    // ======================================================================

    unbreakGlassBeforeUnassign(update, inst) {
        let targetInst = null;
        if (this.state.glassBroken && !this.state.haveWBOed) {
            if (inst.card.targetAction === C.TARGETACTION_DISRUPT) {
                targetInst = this.state.instIdToInst(inst.target);
                if (!targetInst.dead &&
                    targetInst.disruptDamage - inst.card.targetAmount <
                    targetInst.damageItCanTake + targetInst.damage) {
                    this.processOrder(update, false, new Order(C.MOVE_UNWIPEOUT));
                }
            } else if (inst.card.targetAction === C.TARGETACTION_SNIPE) {
                targetInst = this.state.instIdToInst(inst.target);
                if (targetInst.blocking) {
                    this.processOrder(update, false, new Order(C.MOVE_UNWIPEOUT));
                }
            }
        }
    }

    // ======================================================================
    // instSatisfiesConditionWhy (Controller.as:2500-2547)
    // ======================================================================

    instSatisfiesConditionWhy(inst, condition) {
        if (inst.dead) {
            return C.ERROR_BADTARGET_DEAD;
        }
        if (inst.constructionTime > 0) {
            return C.ERROR_BADTARGET_UNDER_CONSTRUCTION;
        }
        if (inst.owner === this.state.turn) {
            return C.ERROR_BADTARGET_YOURS;
        }
        if (condition.hasOwnProperty(C.CONDITION_IS_BLOCKING) && inst.disruptDamage >= inst.health) {
            return C.ERROR_BADTARGET_DISRUPT_FROZEN;
        }
        if (condition.hasOwnProperty(C.CONDITION_IS_BLOCKING) && !inst.blocking) {
            return C.ERROR_BADTARGET_DISRUPT_NONBLOCKING;
        }
        if (condition.hasOwnProperty(C.CONDITION_CARD) && inst.cardName !== condition[C.CONDITION_CARD]) {
            return C.ERROR_BADTARGET_WRONG_CARD;
        }
        if (condition.hasOwnProperty(C.CONDITION_NOT_BLOCKING) && inst.blocking) {
            return C.ERROR_BADTARGET_BLOCKING;
        }
        if (condition.hasOwnProperty(C.CONDITION_HEALTH_AT_MOST) &&
            inst.health > condition[C.CONDITION_HEALTH_AT_MOST]) {
            return C.ERROR_BADTARGET_HEALTH;
        }
        if (condition.hasOwnProperty(C.CONDITION_NAME_IN) &&
            condition[C.CONDITION_NAME_IN].indexOf(inst.cardName) === -1) {
            return C.ERROR_BADTARGET_WRONG_CARD;
        }
        if (condition.hasOwnProperty(C.CONDITION_IS_ABC) &&
            'AnimusBlastforgeConduit'.indexOf(inst.cardName) === -1) {
            return C.ERROR_BADTARGET_NOT_ABC;
        }
        if (condition.hasOwnProperty(C.CONDITION_IS_ENGINEER_TEMP) &&
            inst.cardName !== 'Engineer') {
            return C.ERROR_BADTARGET_NOT_ENGINEER;
        }
        return null;
    }

    // ======================================================================
    // instsSatisfyingCondition (Controller.as:2549-2563)
    // ======================================================================

    instsSatisfyingCondition(condition) {
        const answer = [];
        this.state.table.forEach((inst) => {
            if (this.instSatisfiesConditionWhy(inst, condition) === null) {
                answer.push(inst);
            }
        });
        return answer;
    }

    // ======================================================================
    // failure (Controller.as:2565-2571)
    // No-op in headless — UI error display only.
    // ======================================================================

    failure(displayErrorMsg, type, data) {
        /* STUB: UI-only — in AS3 this dispatches error events when not in swipe mode */
    }

    // ======================================================================
    // _compareInstBackward — internal sort comparator
    //
    // AS3: state.compareInstBackward(inst1, inst2) = state.order(inst2, inst1, false)
    // State.js exposes _order() as a private method, so we call it directly.
    // ======================================================================

    _compareInstBackward(inst1, inst2) {
        return this.state._order(inst2, inst1, false);
    }
}

module.exports = Controller;
