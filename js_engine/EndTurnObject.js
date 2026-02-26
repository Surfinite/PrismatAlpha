'use strict';

const C = require('./C');

/**
 * EndTurnObject.js — End-of-turn summary, transpiled from mcds/engine/EndTurnObject.as
 *
 * Computed at end of each turn. Tracks resources produced, damage dealt,
 * units bought/created, and achievement-tracking counters.
 * Some fields are used for achievement/progression tracking only (client-side).
 */
class EndTurnObject {
    /**
     * @param {State} s - The game state at end of turn
     */
    constructor(s) {
        const produced = s.helper.totalProducedThisTurn;
        this.moneyProduced = produced.money;
        this.hproduced = produced.pool[C.MANA_H];
        this.rproduced = produced.pool[C.MANA_R];
        this.gproduced = produced.pool[C.MANA_G];
        this.bproduced = produced.pool[C.MANA_B];
        this.techProduced = 2 * produced.pool[C.MANA_H] + 3 * produced.pool[C.MANA_R] +
                            4 * produced.pool[C.MANA_G] + 5 * produced.pool[C.MANA_B];
        this.manaRotted = 3 * s.turnMana.pool[C.MANA_R] + 5 * s.turnMana.pool[C.MANA_B];
        if (s.helper.oppDefense === 0) {
            this.manaRotted += 6 * s.turnMana.pool[C.MANA_A];
        }
        this.goldSaved = s.turnMana.pool[C.MANA_P];
        this.greenSaved = s.turnMana.pool[C.MANA_G];
        this.damageDealt = produced.attack;
        this.totalDefense = 0;
        this.totalButt = 0;
        this.totalInvulnerableButt = 0;
        this.unitsCreated = [];
        this.unitsBought = [];
        this.checkWin = 0;
        this.oppCouldClaimDraw = false;

        // Achievement/stat tracking counters
        this._gaussCannonCount = 0;
        this._centurionBoughtCount = 0;
        this._wallBoughtCount = 0;
        this._doomeddroneBoughtCount = 0;
        this._hellhoundBoughtCount = 0;
        this._chieftainBoughtCount = 0;
        this._legendaryBoughtCount = 0;
        this._vengeBoughtCount = 0;
        this._unitsTabledCount = 0;
        this._rhinoAttackingCount = 0;
        this._zemoraAttackingCount = 0;
        this._ossifiedAttackingCount = 0;
        this._ramboAttackingCount = 0;
        this._deadeyeAttackingCount = 0;
        this._isFourAmporillaTenTarsier = false;
        this._isTiaAndVaiClicked = false;
        this._isRainmakerClicked = false;
        this._isTenIsosSynced = false;
        this._GaussCannonDamagedAndSniped = false;
        this._FrozenButt = 0;
        this._DeadHellhounds = 0;
        this._deadLitterbombs = 0;
        this._boughtABC = false;
        this._boughtAB = false;
        this._antimaDamage = 0;
        this._deadRube = 0;
        this._deadConduits = 0;
        this._killedXanthoTalos = false;

        const __unitsseen = {};
        const __legendariesSeen = {};
        let __tarsierAttackingCount = 0;
        let __amporillaAttackingCount = 0;
        let __tiaThurnaxClicked = false;
        let __vaiMauronaxClicked = false;
        let __engineerReadyCount = 0;
        let __antimaCount = 0;
        let __isoAttackedCount = 0;

        // Collect instances from AS3Dictionary (Map-backed, not plain object)
        const tableInsts = [];
        s.table.forEach((inst) => tableInsts.push(inst));
        for (let ti = 0; ti < tableInsts.length; ti++) {
            const inst = tableInsts[ti];

            if (inst.owner !== s.turn) {
                // Opponent units
                if (inst.cardName === 'Gauss Cannon' && inst.deadness === C.DEADNESS_SNIPED) {
                    this._GaussCannonDamagedAndSniped = true;
                }
                if (inst.disruptDamage >= inst.health) {
                    this._FrozenButt += inst.health;
                }
                if (inst.cardName === 'Hellhound' && inst.deadness === C.DEADNESS_WBO) {
                    this._DeadHellhounds += 1;
                }
                if (inst.cardName === 'Rube' && inst.deadness === C.DEADNESS_WBO) {
                    this._deadRube += 1;
                }
                if (inst.cardName === 'Conduit' && inst.deadness === C.DEADNESS_WBO) {
                    this._deadConduits += 1;
                }
                if (inst.cardName === 'Litterbomb' && inst.deadness === C.DEADNESS_WBO) {
                    this._deadLitterbombs += 1;
                }
                if (inst.cardName === 'Xantho Talos, The War Machine' &&
                    inst.deadness === C.DEADNESS_WBO) {
                    this._killedXanthoTalos = true;
                }
            } else {
                // Own units
                if ((inst.creatorIdFromBuyOrAbility >= 0 || inst.creatorIdFromBeginTurn >= 0) &&
                    inst.constructionTime === 0) {
                    this.unitsCreated.push(inst);
                }
                if (inst.role === C.ROLE_SELLABLE) {
                    this.damageDealt -= inst.card.buyCost.attack;
                    this.unitsBought.push(inst);
                    if (inst.cardName === 'Centurion') this._centurionBoughtCount += 1;
                    else if (inst.cardName === 'Doomed Drone') this._doomeddroneBoughtCount += 1;
                    else if (inst.cardName === 'Hellhound') this._hellhoundBoughtCount += 1;
                    else if (inst.cardName === 'Wall') this._wallBoughtCount += 1;
                    else if (inst.cardName === 'Chieftain') this._chieftainBoughtCount += 1;
                    else if (inst.cardName === 'Animus' || inst.cardName === 'Blastforge') {
                        this._boughtAB = true;
                        this._boughtABC = true;
                    } else if (inst.cardName === 'Conduit') {
                        this._boughtABC = true;
                    } else if (inst.cardName === 'Venge Cannon') {
                        this._vengeBoughtCount += 1;
                    }
                    if (inst.card.rarity === C.RARITY_LEGENDARY) {
                        __legendariesSeen[inst.cardName] = true;
                    }
                } else if (inst.role === C.ROLE_ASSIGNED) {
                    this.damageDealt -= inst.card.abilityCost.attack;
                }

                if (inst.card.cardType === C.CARDTYPE_UNIT && !inst.dead) {
                    if (inst.cardName === 'Gauss Cannon' && inst.role !== C.ROLE_SELLABLE) {
                        this._gaussCannonCount += 1;
                    } else if (inst.cardName === 'Rhino' && inst.role === C.ROLE_ASSIGNED) {
                        this._rhinoAttackingCount += 1;
                    } else if (inst.cardName === 'Zemora Voidbringer' && inst.role === C.ROLE_ASSIGNED) {
                        this._zemoraAttackingCount += 1;
                    } else if (inst.cardName === 'Ossified Drone' && inst.role === C.ROLE_ASSIGNED) {
                        this._ossifiedAttackingCount += 1;
                    } else if (inst.cardName === 'Shield Killer') {
                        if (inst.role === C.ROLE_ASSIGNED) this._ramboAttackingCount += 1;
                    } else if (inst.cardName === 'Deadeye Operative' && inst.role === C.ROLE_ASSIGNED) {
                        this._deadeyeAttackingCount += 1;
                    } else if (inst.cardName === 'Tarsier' && inst.role === C.ROLE_INERT &&
                               inst.constructionTime === 0) {
                        __tarsierAttackingCount += 1;
                    } else if (inst.cardName === 'Amporilla' && inst.role === C.ROLE_INERT) {
                        __amporillaAttackingCount += 1;
                    } else if (inst.cardName === 'Tia Thurnax' && inst.role === C.ROLE_ASSIGNED) {
                        __tiaThurnaxClicked = true;
                    } else if (inst.cardName === 'Photonic Rainmaker' && inst.role === C.ROLE_ASSIGNED) {
                        this._isRainmakerClicked = true;
                    } else if (inst.cardName === 'Vai Mauronax' && inst.role === C.ROLE_ASSIGNED) {
                        __vaiMauronaxClicked = true;
                    } else if (inst.cardName === 'Iso Kronus' && inst.delayAfterSwoosh === 2) {
                        __isoAttackedCount += 1;
                    }

                    __unitsseen[inst.cardName] = true;
                    if (inst.blocking) {
                        this.totalDefense += inst.health;
                    }
                    this.totalButt += inst.health;
                } else {
                    this.totalInvulnerableButt += inst.health;
                }

                if (inst.cardName === 'Engineer' && inst.role !== C.ROLE_SELLABLE &&
                    inst.creatorIdFromBeginTurn === -1 && inst.creatorIdFromBuyOrAbility === -1) {
                    __engineerReadyCount += 1;
                }
                if (inst.cardName === 'Antima Comet' && inst.deadness === C.DEADNESS_SELFSACCED) {
                    __antimaCount += 1;
                }
            }
        }

        // Count unique unit types and legendaries
        const unitKeys = Object.keys(__unitsseen);
        this._unitsTabledCount = unitKeys.length;
        const legendaryKeys = Object.keys(__legendariesSeen);
        this._legendaryBoughtCount = legendaryKeys.length;

        if (__antimaCount >= 1) {
            this._antimaDamage = __engineerReadyCount;
        }

        this._isFourAmporillaTenTarsier =
            __tarsierAttackingCount >= 10 && __amporillaAttackingCount >= 4;
        this._isTiaAndVaiClicked = __tiaThurnaxClicked && __vaiMauronaxClicked;
        this._isTenIsosSynced = __isoAttackedCount >= 10;
    }
}

module.exports = EndTurnObject;
