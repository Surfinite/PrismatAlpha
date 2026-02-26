'use strict';

const C = require('./C');
const Mana = require('./Mana');

/**
 * StateHelper.js — Computed game state properties, transpiled from mcds/engine/StateHelper.as
 *
 * Recomputed each time the state changes. Tracks defense, attack potential,
 * breach/overkill targets, resonate effects, and sniper defense reduction.
 */
class StateHelper {
    constructor() {
        this.reset();
    }

    reset() {
        this.ownDefenders = [];
        this.ownDefense = 0;
        this.ownNonInvTotal = 0;
        this.ownAllUnitsTotal = 0;
        this.contributedToAttackThisTurn = [];
        this.contributedToEconThisTurn = [];
        this.totalProducedThisTurn = new Mana('');
        this.oppDefenders = [];
        this.oppDefense = 0;
        this.maxOppDefenderHealth = 0;
        this.damageReqdToMakeProgressOnFragileBlocker = 0;
        this.oppNonInvTotal = 0;
        this.oppAllUnitsTotal = 0;
        this.allOppUnitsDoomed = true;
        this.oppDoomOneUnits = [];
        this.wipedOut = [];
        this.breached = [];
        this.overkilled = [];
        this.damageReqdToInjureBreach = 32768;
        this.damageReqdToInjureOverkill = 32768;
        this.partiallyDamagedInst = null;
        this.couldDefendThisTurn = [];
        this.maxDefense = 0;
        this.couldAttackThisTurn = [];
        this.maxAttack = 0;
        this.maxDisrupt = 0;
        this.maxSnipers = 0;
        this.couldEconThisTurn = [];
        this.maxEcon = 0;
        this.maxEconLowerBound = 0;
        this.displayOppAttackPotential = false;
        this.oppAttackers = [];
        this.oppAttackPotential = 0;
        this.oppGuaranteedAttack = 0;
        this.oppEconPotentialLowerBound = 0;
        this.oppEconPotential = 0;
        this.oppDisruptPotential = 0;
        this.oppSnipers = 0;
        this.myDefenseReductionFromOppSnipers = 0;
        this.ownEconPotentialNextTurn = 0;
        this.ownEconPotentialNextTurnLowerBound = 0;
    }

    /**
     * Recompute all helper fields from the current state.
     * From StateHelper.as:141-646 — the core analysis method.
     * @param {State} s - The game state to analyze
     */
    update(s) {
        let inst = null;
        let card = null;
        let pushToAttackers = false;
        let pushToWorkers = false;
        let pushToAttackContributors = false;
        let pushToEconContributors = false;
        let damageReqd = 0;
        let pushToOppAttackers = false;

        this.reset();

        const ownStuffAfterDefensePhase = [];
        const oppStuffNextTurn = [];

        // AS3 Dictionary → JS object (string keys for card names)
        const ownAnnihilate = {};
        const oppAnnihilate = {};
        const ownGoldAnnihilate = {};
        const ownGoldAnnihilateNextTurn = {};
        const oppGoldAnnihilate = {};

        let numDrones = 0;
        const saviorResoName = 'Drone';

        // Collect instances from AS3Dictionary (Map-backed, not plain object)
        const tableInsts = [];
        s.table.forEach((inst) => tableInsts.push(inst));

        for (let ti = 0; ti < tableInsts.length; ti++) {
            inst = tableInsts[ti];
            card = inst.card;

            if (inst.isPartiallyDamaged) {
                C.ASSERT(this.partiallyDamagedInst === null,
                    'There is more than one partially damaged Inst on the table.');
                this.partiallyDamagedInst = inst;
            }

            if (inst.owner === s.turn) {
                // Own units
                if (!inst.dead) {
                    this.ownAllUnitsTotal += inst.damageItCanTake;
                    if (inst.constructionTime === 0) {
                        this.ownNonInvTotal += inst.damageItCanTake;
                        if (inst.blocking) {
                            this.ownDefenders.push(inst);
                            this.ownDefense += inst.damageItCanTake;
                        }
                    }
                }

                if (s.phase === C.PHASE_DEFENSE) {
                    // Defense phase: look ahead to next turn
                    if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                        !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) &&
                        !inst.dead) {
                        ownStuffAfterDefensePhase.push(inst);

                        if (card.resonate !== null) {
                            if (ownAnnihilate.hasOwnProperty(card.resonate)) {
                                ownAnnihilate[card.resonate].push(inst);
                            } else {
                                ownAnnihilate[card.resonate] = [inst];
                            }
                        }
                        if (card.goldResonate !== null) {
                            if (ownGoldAnnihilate.hasOwnProperty(card.goldResonate)) {
                                ownGoldAnnihilate[card.goldResonate].push(inst);
                            } else {
                                ownGoldAnnihilate[card.goldResonate] = [inst];
                            }
                        }
                        if (card.cardName === saviorResoName) {
                            numDrones += 1;
                        }

                        pushToAttackers = false;
                        pushToWorkers = false;
                        if (card.beginOwnTurnScript !== null) {
                            if (card.beginOwnTurnScript.receive.attack > 0) {
                                pushToAttackers = true;
                                this.maxAttack += card.beginOwnTurnScript.receive.attack;
                            }
                            if (card.beginOwnTurnScript.receive.money > 0) {
                                pushToWorkers = true;
                                this.maxEcon += card.beginOwnTurnScript.receive.money;
                                this.maxEconLowerBound += card.beginOwnTurnScript.receive.money;
                            }
                        }
                        if (inst.health + card.healthGained >= card.healthUsed &&
                            inst.charge + card.chargeGained >= card.chargeUsed) {
                            if (card.abilityScript !== null) {
                                if (card.abilityScript.receive.attack > 0) {
                                    pushToAttackers = true;
                                    this.maxAttack += card.abilityScript.receive.attack;
                                }
                                if (card.abilityScript.receive.money > 0) {
                                    pushToWorkers = true;
                                    this.maxEcon += card.abilityScript.receive.money;
                                    if (card.abilityCost.isEmpty && card.abilitySac.length === 0 &&
                                        (card.abilityScript === null || !card.abilityScript.selfsac)) {
                                        this.maxEconLowerBound += card.abilityScript.receive.money;
                                    }
                                }
                            }
                            this.maxDisrupt += card.disruptPotential;
                            if (card.targetAction === C.TARGETACTION_SNIPE) {
                                if (card.potentiallyMoreAttack) {
                                    ++this.maxSnipers;
                                }
                            }
                        }
                        if (pushToAttackers) {
                            this.couldAttackThisTurn.push(inst);
                        }
                        if (pushToWorkers) {
                            this.couldEconThisTurn.push(inst);
                        }
                    }
                } else {
                    // Action phase
                    if (inst.role === C.ROLE_SELLABLE) {
                        if (card.buyScript !== null) {
                            if (card.buyScript.receive.money > 0) {
                                this.contributedToEconThisTurn.push(inst);
                            }
                            this.totalProducedThisTurn.add(card.buyScript.receive);
                        }
                        this.maxAttack += card.buyCost.attack;
                        this.maxEcon += card.buyCost.money;
                    } else if (!(inst.creatorIdFromBeginTurn >= 0 || inst.creatorIdFromBuyOrAbility >= 0)) {
                        if (inst.constructionTime === 0 &&
                            (inst.delay === 0 ||
                             (inst.card.abilityScript !== null && inst.delay === inst.card.abilityScript.delay) ||
                             (inst.card.beginOwnTurnScript !== null && inst.delay === inst.card.beginOwnTurnScript.delay))) {
                            ownStuffAfterDefensePhase.push(inst);

                            if (card.resonate !== null) {
                                if (ownAnnihilate.hasOwnProperty(card.resonate)) {
                                    ownAnnihilate[card.resonate].push(inst);
                                } else {
                                    ownAnnihilate[card.resonate] = [inst];
                                }
                            }
                            if (card.goldResonate !== null) {
                                if (ownGoldAnnihilate.hasOwnProperty(card.goldResonate)) {
                                    ownGoldAnnihilate[card.goldResonate].push(inst);
                                } else {
                                    ownGoldAnnihilate[card.goldResonate] = [inst];
                                }
                            }

                            pushToAttackContributors = false;
                            pushToEconContributors = false;
                            if (card.beginOwnTurnScript !== null) {
                                if (card.beginOwnTurnScript.receive.attack > 0) {
                                    pushToAttackContributors = true;
                                }
                                if (card.beginOwnTurnScript.receive.money > 0) {
                                    pushToEconContributors = true;
                                }
                                this.totalProducedThisTurn.add(card.beginOwnTurnScript.receive);
                            }
                            if (inst.role === C.ROLE_DEFAULT) {
                                if (inst.health >= card.healthUsed && inst.charge >= card.chargeUsed &&
                                    card.abilityScript !== null) {
                                    if (card.abilityScript.receive.attack > 0) {
                                        this.couldAttackThisTurn.push(inst);
                                        this.maxAttack += card.abilityScript.receive.attack;
                                    }
                                    if (card.abilityScript.receive.money > 0) {
                                        this.couldEconThisTurn.push(inst);
                                        this.maxEcon += card.abilityScript.receive.money;
                                    }
                                }
                            } else if (inst.role === C.ROLE_ASSIGNED ||
                                       inst.deadness === C.DEADNESS_SACCED ||
                                       inst.deadness === C.DEADNESS_SELFSACCED) {
                                if (card.abilityScript !== null) {
                                    if (card.abilityScript.receive.attack > 0) {
                                        pushToAttackContributors = true;
                                    }
                                    if (card.abilityScript.receive.money > 0) {
                                        pushToEconContributors = true;
                                    }
                                    this.totalProducedThisTurn.add(card.abilityScript.receive);
                                    this.maxAttack += card.abilityCost.attack;
                                    this.maxEcon += card.abilityCost.money;
                                }
                                if (card.defaultBlocking &&
                                    (!card.assignedBlocking || inst.deadness === C.DEADNESS_SACCED ||
                                     inst.deadness === C.DEADNESS_SELFSACCED || card.healthUsed > 0)) {
                                    this.couldDefendThisTurn.push(inst);
                                    if (!card.assignedBlocking || inst.deadness === C.DEADNESS_SACCED ||
                                        inst.deadness === C.DEADNESS_SELFSACCED) {
                                        this.maxDefense += inst.health;
                                    }
                                    if (card.healthUsed > 0) {
                                        this.maxDefense += card.healthUsed;
                                    }
                                }
                            }
                            if (pushToAttackContributors) {
                                this.contributedToAttackThisTurn.push(inst);
                            }
                            if (pushToEconContributors) {
                                this.contributedToEconThisTurn.push(inst);
                            }
                        }
                    }

                    // Next turn econ potential (regardless of role)
                    if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                        !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) &&
                        !inst.dead) {
                        if (card.beginOwnTurnScript !== null) {
                            this.ownEconPotentialNextTurn += card.beginOwnTurnScript.receive.money;
                            this.ownEconPotentialNextTurnLowerBound += card.beginOwnTurnScript.receive.money;
                        }
                        if (inst.health + card.healthGained >= card.healthUsed &&
                            inst.charge + card.chargeGained >= card.chargeUsed &&
                            card.abilityScript !== null) {
                            this.ownEconPotentialNextTurn += card.abilityScript.receive.money;
                            if (card.abilityCost.isEmpty && card.abilitySac.length === 0 &&
                                (card.abilityScript === null || !card.abilityScript.selfsac)) {
                                this.ownEconPotentialNextTurnLowerBound += card.abilityScript.receive.money;
                            }
                        }
                        if (card.goldResonate !== null &&
                            (inst.constructionTime === 1 || inst.delay === 1)) {
                            if (ownGoldAnnihilateNextTurn.hasOwnProperty(card.goldResonate)) {
                                ownGoldAnnihilateNextTurn[card.goldResonate].push(inst);
                            } else {
                                ownGoldAnnihilateNextTurn[card.goldResonate] = [inst];
                            }
                        }
                        if (card.cardName === saviorResoName) {
                            numDrones += 1;
                        }
                    }
                }
            } else {
                // Opponent units
                if (!inst.dead) {
                    this.oppAllUnitsTotal += inst.damageItCanTake;
                    if (inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) {
                        this.oppDoomOneUnits.push(inst);
                    } else {
                        this.allOppUnitsDoomed = false;
                    }
                    if (inst.constructionTime === 0) {
                        this.oppNonInvTotal += inst.damageItCanTake;
                        if (inst.blocking) {
                            this.oppDefenders.push(inst);
                            this.oppDefense += inst.damageItCanTake;
                            this.maxOppDefenderHealth = Math.max(
                                this.maxOppDefenderHealth, inst.damageItCanTake
                            );
                            if (!inst.card.fragile) {
                                this.damageReqdToMakeProgressOnFragileBlocker = Math.max(
                                    this.damageReqdToMakeProgressOnFragileBlocker, inst.health
                                );
                            } else {
                                damageReqd = Math.min(
                                    inst.card.healthGained + 1, inst.health
                                );
                                this.damageReqdToMakeProgressOnFragileBlocker = Math.max(
                                    this.damageReqdToMakeProgressOnFragileBlocker, damageReqd
                                );
                            }
                        }
                    }
                    this.damageReqdToInjureOverkill = Math.min(
                        this.damageReqdToInjureOverkill, inst.damageReqdToInjure
                    );
                    if (inst.constructionTime === 0) {
                        this.damageReqdToInjureBreach = Math.min(
                            this.damageReqdToInjureBreach, inst.damageReqdToInjure
                        );
                    }
                }

                // Breach/wipeout/overkill tracking
                if (inst.deadness === C.DEADNESS_WBO || inst.isPartiallyDamaged) {
                    if (inst.blocking) {
                        this.wipedOut.push(inst);
                    } else if (inst.constructionTime > 0) {
                        this.overkilled.push(inst);
                    } else {
                        this.breached.push(inst);
                    }
                }

                // Opponent next-turn potential
                if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0)) {
                    if (card.attackPotential !== 0) {
                        this.displayOppAttackPotential = true;
                    }
                    if (!inst.dead) {
                        oppStuffNextTurn.push(inst);

                        if (card.resonate !== null) {
                            if (oppAnnihilate.hasOwnProperty(card.resonate)) {
                                oppAnnihilate[card.resonate].push(inst);
                            } else {
                                oppAnnihilate[card.resonate] = [inst];
                            }
                        }
                        if (card.goldResonate !== null) {
                            if (oppGoldAnnihilate.hasOwnProperty(card.goldResonate)) {
                                oppGoldAnnihilate[card.goldResonate].push(inst);
                            } else {
                                oppGoldAnnihilate[card.goldResonate] = [inst];
                            }
                        }

                        pushToOppAttackers = false;
                        if (card.beginOwnTurnScript !== null &&
                            card.beginOwnTurnScript.receive.attack > 0) {
                            pushToOppAttackers = true;
                            this.oppAttackPotential += card.beginOwnTurnScript.receive.attack;
                            this.oppGuaranteedAttack += card.beginOwnTurnScript.receive.attack;
                        }
                        if (card.beginOwnTurnScript !== null &&
                            card.beginOwnTurnScript.receive.money > 0) {
                            this.oppEconPotential += card.beginOwnTurnScript.receive.money;
                            this.oppEconPotentialLowerBound += card.beginOwnTurnScript.receive.money;
                        }
                        if (inst.health + card.healthGained >= card.healthUsed &&
                            inst.charge + card.chargeGained >= card.chargeUsed) {
                            if (card.abilityScript !== null &&
                                card.abilityScript.receive.attack > 0) {
                                pushToOppAttackers = true;
                                this.oppAttackPotential += card.abilityScript.receive.attack;
                            }
                            if (card.abilityScript !== null &&
                                card.abilityScript.receive.money > 0) {
                                this.oppEconPotential += card.abilityScript.receive.money;
                                if (card.abilityCost.isEmpty &&
                                    (card.abilityScript === null || !card.abilityScript.selfsac) &&
                                    card.abilitySac.length === 0) {
                                    this.oppEconPotentialLowerBound += card.abilityScript.receive.money;
                                }
                            }
                            if (card.targetAction === C.TARGETACTION_DISRUPT) {
                                pushToOppAttackers = true;
                                this.oppDisruptPotential += card.targetAmount;
                            } else if (card.targetAction === C.TARGETACTION_SNIPE) {
                                if (card.potentiallyMoreAttack) {
                                    pushToOppAttackers = true;
                                    ++this.oppSnipers;
                                }
                            }
                        }
                        if (card.cardName === 'Cryo Kronus') {
                            this.oppDisruptPotential += 999;
                        }
                        if (pushToOppAttackers) {
                            this.oppAttackers.push(inst);
                        }
                    }
                }
            }
        }

        // Resonate resolution — own side
        let wentOff = {};
        for (let si = 0; si < ownStuffAfterDefensePhase.length; si++) {
            inst = ownStuffAfterDefensePhase[si];
            card = inst.card;
            if (ownAnnihilate.hasOwnProperty(inst.card.cardName)) {
                if (s.phase === C.PHASE_DEFENSE) {
                    if (!wentOff.hasOwnProperty(card.cardName)) {
                        this.couldAttackThisTurn = this.couldAttackThisTurn.concat(
                            ownAnnihilate[card.cardName]
                        );
                        wentOff[card.cardName] = true;
                    }
                    this.maxAttack += ownAnnihilate[card.cardName].length;
                } else {
                    if (!wentOff.hasOwnProperty(card.cardName)) {
                        this.contributedToAttackThisTurn = this.contributedToAttackThisTurn.concat(
                            ownAnnihilate[card.cardName]
                        );
                        wentOff[card.cardName] = true;
                    }
                    this.totalProducedThisTurn.attack += ownAnnihilate[card.cardName].length;
                }
            }
            if (ownGoldAnnihilate.hasOwnProperty(inst.card.cardName)) {
                if (s.phase !== C.PHASE_DEFENSE) {
                    this.totalProducedThisTurn.money += ownGoldAnnihilate[card.cardName].length;
                }
            }
        }

        // Gold resonate with Drones
        if (numDrones > 0 && ownGoldAnnihilate.hasOwnProperty(saviorResoName)) {
            if (s.phase === C.PHASE_DEFENSE) {
                this.maxEcon += ownGoldAnnihilate[saviorResoName].length * numDrones;
                this.maxEconLowerBound += ownGoldAnnihilate[saviorResoName].length * numDrones;
            } else {
                this.ownEconPotentialNextTurn +=
                    ownGoldAnnihilate[saviorResoName].length * numDrones;
                this.ownEconPotentialNextTurnLowerBound +=
                    ownGoldAnnihilate[saviorResoName].length * numDrones;
            }
        }

        if (numDrones > 0 && ownGoldAnnihilateNextTurn.hasOwnProperty(saviorResoName)) {
            if (s.phase !== C.PHASE_DEFENSE) {
                this.ownEconPotentialNextTurn +=
                    ownGoldAnnihilateNextTurn[saviorResoName].length * numDrones;
                this.ownEconPotentialNextTurnLowerBound +=
                    ownGoldAnnihilateNextTurn[saviorResoName].length * numDrones;
            }
        }

        // Resonate resolution — opponent side
        wentOff = {};
        for (let oi = 0; oi < oppStuffNextTurn.length; oi++) {
            inst = oppStuffNextTurn[oi];
            card = inst.card;
            if (oppAnnihilate.hasOwnProperty(card.cardName)) {
                if (!wentOff.hasOwnProperty(card.cardName)) {
                    this.oppAttackers = this.oppAttackers.concat(
                        oppAnnihilate[card.cardName]
                    );
                    wentOff[card.cardName] = true;
                }
                this.oppAttackPotential += oppAnnihilate[card.cardName].length;
                this.oppGuaranteedAttack += oppAnnihilate[card.cardName].length;
            }
            if (oppGoldAnnihilate.hasOwnProperty(card.cardName)) {
                this.oppEconPotential += oppGoldAnnihilate[card.cardName].length;
                this.oppEconPotentialLowerBound += oppGoldAnnihilate[card.cardName].length;
            }
        }

        // Sniper defense reduction
        if (this.oppSnipers > 0) {
            const myHealths = [];
            for (let di = 0; di < this.ownDefenders.length; di++) {
                inst = this.ownDefenders[di];
                if (inst.health <= 3) {
                    myHealths.push(inst.health);
                }
            }
            myHealths.sort((a, b) => b - a); // Descending (AS3: NUMERIC then reverse)
            const limit = Math.min(this.oppSnipers, myHealths.length);
            for (let i = 0; i < limit; i++) {
                this.myDefenseReductionFromOppSnipers += myHealths[i];
            }
        }
    }
}

module.exports = StateHelper;
