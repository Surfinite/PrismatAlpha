'use strict';

const C = require('./C');
const Mana = require('./Mana');
const Card = require('./Card');
const Inst = require('./Inst');
const Script = require('./Script');
const Rndm = require('./Rndm');
const StateHelper = require('./StateHelper');
const EndTurnObject = require('./EndTurnObject');
const AS3Dictionary = require('./AS3Dictionary');

/**
 * State.js — Core game state machine, transpiled from mcds/engine/State.as
 *
 * Handles game initialization, move processing, turn resolution (swoosh),
 * win detection, and serialization. Faithfully reproduces AS3 game logic
 * for headless PvP games (no tutorials, missions, objectives, or UI events).
 *
 * dispatch() is a no-op in headless mode — all UI event dispatching is stripped.
 */

// Stagnation constants (from State.as:76-104)
const NUM_LEVELS_OF_DRAW_VARIABLES = 4;
const CUTOFFS_FOR_DRAW = [2, 8, 20, 40];
const LEVEL_DELAY_TICKED = 1;
const LEVEL_HP_HEALED_ON_UNIT_WITH_PAY_HP_ABILITY = 1;
const LEVEL_CHARGE_RECHARGED = 1;
const LEVEL_DAMAGE_BY_MORE_THAN_HEALING = 1;
const LEVEL_MONEY_STORED = 2;
const LEVEL_CARD_BOUGHT_OR_INST_CREATED = 3;
const LEVEL_BUILDTIME_TICKED = 3;
const LEVEL_OPP_LIFESPAN_TICKED = 3;
const LEVEL_GAS_STORED_WITH_GAUSSITE_SYMBIOTE = 3;
const LEVEL_GAS_STORED_WITH_GAUSS_CHARGE = 3;
const LEVEL_GAS_STORED_WITH_CLUSTER_BOLT = 3;
const LEVEL_GAS_STORED_WITH_ZEMORA = 3;
const LEVEL_OPP_UNIT_COLLECTED = 4;

// Static PRNG for swoosh randomization (State.as:106-108)
let turnRandomizer = null;
let lazySeed = -1;
let randomizerSeeded = false;

function initRandomizerIfNeeded() {
    if (!turnRandomizer) {
        turnRandomizer = new Rndm(lazySeed);
    } else if (!randomizerSeeded) {
        turnRandomizer.seed = lazySeed;
    }
    randomizerSeeded = true;
}

function lazySeedRandomizer(seed) {
    lazySeed = seed;
    randomizerSeeded = false;
}

/**
 * Deep-clone a 2D array of ints (for createIds).
 * From State.as:676-689.
 */
function cloneCreateIds(createIds) {
    const answer = new Array(createIds.length);
    for (let i = 0; i < answer.length; i++) {
        answer[i] = new Array(createIds[i].length);
        for (let j = 0; j < answer[i].length; j++) {
            answer[i][j] = createIds[i][j];
        }
    }
    return answer;
}

class State {
    /**
     * Construct a new game state.
     *
     * Fresh game: State(laneInfo, mergedDeck, scriptInfo)
     * Clone:      State(null, null, null, null, 0, 0, existingState)
     *
     * @param {Object} laneInfo - Lane configuration with initResources, base, randomizer, initCards
     * @param {Array} mergedDeck - Array of card definition objects from cardLibrary
     * @param {Object} scriptInfo - Script configuration (whiteStarts, initialPhase, etc.)
     * @param {Object} objectiveInfo - Mission objectives (null for PvP)
     * @param {number} inputLaneId - Lane ID (-1 for default)
     * @param {number} controlledLane - Controlled lane (-1 for PvP)
     * @param {State} real - Existing state to clone from (null for fresh)
     */
    constructor(laneInfo, mergedDeck, scriptInfo, objectiveInfo, inputLaneId, controlledLane, real) {
        if (inputLaneId === undefined) inputLaneId = -1;
        if (controlledLane === undefined) controlledLane = -1;
        if (real === undefined) real = null;

        // --- Clone path (State.as:216-342) ---
        if (real !== null) {
            // Deep-copy instance table
            this.table = new AS3Dictionary();
            for (const key of real.table.keys()) {
                this.table.set(key, real.table.get(key).clone());
            }
            this.nextInstId = real.nextInstId;

            // Share card definitions (immutable)
            this.cards = real.cards;
            this.cardNameToCardId = real.cardNameToCardId;

            // Deep-copy mana
            this.whiteMana = real.whiteMana.clone();
            this.blackMana = real.blackMana.clone();

            // Deep-copy supply and bought arrays
            const numCards = this.cards.length;
            this.whiteSupply = new Array(numCards);
            this.blackSupply = new Array(numCards);
            this.whiteBought = new Array(numCards);
            this.blackBought = new Array(numCards);
            for (let i = 0; i < numCards; i++) {
                this.whiteSupply[i] = real.whiteSupply[i];
                this.blackSupply[i] = real.blackSupply[i];
                this.whiteBought[i] = real.whiteBought[i];
                this.blackBought[i] = real.blackBought[i];
            }

            // Deep-copy revealed purchasables
            this.revealedWhitePurchasables = {};
            this.revealedBlackPurchasables = {};
            for (const k of Object.keys(real.revealedWhitePurchasables)) {
                this.revealedWhitePurchasables[k] = real.revealedWhitePurchasables[k];
            }
            for (const k of Object.keys(real.revealedBlackPurchasables)) {
                this.revealedBlackPurchasables[k] = real.revealedBlackPurchasables[k];
            }

            this.numTurns = real.numTurns;
            this.phase = real.phase;
            this.glassBroken = real.glassBroken;
            this.result = real.result;

            // Mission fields (null for PvP)
            this.objectives = real.objectives;
            this.objectivesRevealed = real.objectivesRevealed;
            this.objectivesCompleted = real.objectivesCompleted;
            this.objectivesFailed = real.objectivesFailed;
            this.internalNameToObjectiveId = real.internalNameToObjectiveId;
            this.counters = real.counters ? Object.assign({}, real.counters) : null;
            this.triggers = real.triggers;
            this.triggerExecuted = real.triggerExecuted;

            this.blockTriggers = false;
            this.laneId = real.laneId;
            this.controlledLane = real.controlledLane;

            // Stagnation counters
            this.whiteNoProgress = new Array(NUM_LEVELS_OF_DRAW_VARIABLES);
            this.blackNoProgress = new Array(NUM_LEVELS_OF_DRAW_VARIABLES);
            for (let i = 0; i < NUM_LEVELS_OF_DRAW_VARIABLES; i++) {
                this.whiteNoProgress[i] = real.whiteNoProgress[i];
                this.blackNoProgress[i] = real.blackNoProgress[i];
            }

            this.helper = new StateHelper();
            this.endTurnObject = null;
            return;
        }

        // --- Fresh game path (State.as:344-649) ---
        this.table = new AS3Dictionary();
        this.nextInstId = 0;

        // Build cards array from mergedDeck
        const numCards = mergedDeck.length;
        this.cards = new Array(numCards);
        this.cardNameToCardId = {};
        for (let i = 0; i < numCards; i++) {
            this.cards[i] = new Card(mergedDeck[i], i);
            this.cardNameToCardId[mergedDeck[i].name] = i;
        }

        // Resolve card cross-references (sac targets, create targets)
        for (let i = 0; i < numCards; i++) {
            const c = this.cards[i];
            for (let j = 0; j < c.buySac.length; j++) {
                c.buySac[j].card = this.cardNameToCard(c.buySac[j].cardName);
            }
            if (c.buyScript !== null) {
                for (let j = 0; j < c.buyScript.create.length; j++) {
                    c.buyScript.create[j].card = this.cardNameToCard(c.buyScript.create[j].cardName);
                }
            }
            if (c.beginOwnTurnScript !== null) {
                for (let j = 0; j < c.beginOwnTurnScript.create.length; j++) {
                    c.beginOwnTurnScript.create[j].card = this.cardNameToCard(c.beginOwnTurnScript.create[j].cardName);
                }
            }
            for (let j = 0; j < c.abilitySac.length; j++) {
                c.abilitySac[j].card = this.cardNameToCard(c.abilitySac[j].cardName);
            }
            if (c.abilityScript !== null) {
                for (let j = 0; j < c.abilityScript.create.length; j++) {
                    c.abilityScript.create[j].card = this.cardNameToCard(c.abilityScript.create[j].cardName);
                }
            }
        }

        // Initialize mana from lane info
        const lane = inputLaneId === -1 ? 0 : inputLaneId;
        this.whiteMana = new Mana(laneInfo[lane].initResources[0]);
        this.blackMana = new Mana(laneInfo[lane].initResources[1]);

        // Initialize supply
        this.whiteSupply = new Array(numCards).fill(0);
        this.blackSupply = new Array(numCards).fill(0);
        this.revealedWhitePurchasables = {};
        this.revealedBlackPurchasables = {};

        const supply = [this.whiteSupply, this.blackSupply];
        for (let i = 0; i < 2; i++) {
            const infiniteSupplies = laneInfo[lane].hasOwnProperty('infiniteSupplies') && laneInfo[lane].infiniteSupplies == 1;
            const supplyInfo = [laneInfo[lane].base[i], laneInfo[lane].randomizer[i]];
            for (const supplySet of supplyInfo) {
                for (let j = 0; j < supplySet.length; j++) {
                    const cardData = supplySet[j];
                    let cardSupply = -1;
                    let cardName;
                    let cardID;
                    if (typeof cardData === 'string') {
                        cardName = cardData;
                    } else if (Array.isArray(cardData)) {
                        cardName = cardData[0];
                        if (cardData.length > 1) {
                            cardID = this.cardNameToCardId[cardName] | 0;
                            cardSupply = cardData[1] | 0;
                        }
                    } else {
                        throw new Error('unknown card format');
                    }
                    if (cardSupply === -1) {
                        cardID = this.cardNameToCardId[cardName] | 0;
                        cardSupply = infiniteSupplies ? 1000 : this.cards[cardID].rarity;
                    }
                    C.ASSERT(supply[i][cardID] === 0, 'Duplicate card in buy box.');
                    supply[i][cardID] = cardSupply;
                    if (cardSupply !== 0) {
                        this.playerRevealedPurchasables(i)[cardName] = 0;
                        if (supplySet === supplyInfo[1]) {
                            this.playerRevealedPurchasables(i)[cardName] = 1;
                        }
                    }
                }
            }
        }

        // Initialize bought arrays
        this.whiteBought = new Array(numCards).fill(0);
        this.blackBought = new Array(numCards).fill(0);

        this.numTurns = 0;
        this.phase = C.PHASE_ACTION;
        this.glassBroken = false;
        this.result = C.COLOR_NONE;
        this.laneId = 0;
        this.controlledLane = -1;

        // Stagnation counters
        this.whiteNoProgress = new Array(NUM_LEVELS_OF_DRAW_VARIABLES).fill(0);
        this.blackNoProgress = new Array(NUM_LEVELS_OF_DRAW_VARIABLES).fill(0);

        // Mission fields (null for PvP)
        this.objectives = null;
        this.objectivesRevealed = null;
        this.objectivesCompleted = null;
        this.objectivesFailed = null;
        this.internalNameToObjectiveId = null;
        this.counters = null;
        this.triggers = [];
        this.triggerExecuted = [];
        this.blockTriggers = false;

        // Process scriptInfo
        if (scriptInfo !== null) {
            if (scriptInfo.hasOwnProperty('whiteStarts') && !scriptInfo.whiteStarts) {
                this.numTurns = 1;
            }
            if (scriptInfo.hasOwnProperty('initialPhase')) {
                switch (scriptInfo.initialPhase) {
                    case 'defense': this.phase = C.PHASE_DEFENSE; break;
                    case 'action': this.phase = C.PHASE_ACTION; break;
                    case 'confirm': this.phase = C.PHASE_CONFIRM; break;
                    default: C.ASSERT(false, 'Invalid phase specified in init info.');
                }
            }
            if (scriptInfo.hasOwnProperty('initialGlassBroken') && scriptInfo.initialGlassBroken) {
                this.glassBroken = true;
            }
            this.counters = {};
        }

        if (inputLaneId >= 0) {
            this.laneId = inputLaneId;
            this.controlledLane = controlledLane;
        }

        // Create initial instances
        this._createInstsFromInitArray(laneInfo[lane].initCards[0], C.COLOR_WHITE, true);
        this._createInstsFromInitArray(laneInfo[lane].initCards[1], C.COLOR_BLACK, true);

        this.helper = new StateHelper();
        this.helper.update(this);
        this.endTurnObject = null;
    }

    // --- Lookups (State.as:1166-1284) ---

    instIdToInst(instId) {
        return this.table.get(instId);
    }

    scriptToInstIds(script) {
        if (script !== null && script.create.length > 0) {
            const answer = new Array(script.create.length);
            for (let i = 0; i < answer.length; i++) {
                answer[i] = new Array(script.create[i].multiplicity);
                for (let j = 0; j < answer[i].length; j++) {
                    answer[i][j] = this.nextInstId++;
                }
            }
            return answer;
        }
        return null;
    }

    cardIdToCard(cardId) {
        return this.cards[cardId];
    }

    cardNameToCard(cardName) {
        return this.cards[this.cardNameToCardId[cardName]];
    }

    get turnMana() {
        return this.turn === C.COLOR_WHITE ? this.whiteMana : this.blackMana;
    }

    get oppMana() {
        return this.turn === C.COLOR_WHITE ? this.blackMana : this.whiteMana;
    }

    playerMana(color) {
        return color === C.COLOR_WHITE ? this.whiteMana : this.blackMana;
    }

    turnSupply() {
        return this.turn === C.COLOR_WHITE ? this.whiteSupply : this.blackSupply;
    }

    oppSupply() {
        return this.turn === C.COLOR_WHITE ? this.blackSupply : this.whiteSupply;
    }

    playerSupply(color) {
        return color === C.COLOR_WHITE ? this.whiteSupply : this.blackSupply;
    }

    playerRevealedPurchasables(color) {
        return color === C.COLOR_WHITE ? this.revealedWhitePurchasables : this.revealedBlackPurchasables;
    }

    turnBought() {
        return this.turn === C.COLOR_WHITE ? this.whiteBought : this.blackBought;
    }

    oppBought() {
        return this.turn === C.COLOR_WHITE ? this.blackBought : this.whiteBought;
    }

    playerBought(color) {
        return color === C.COLOR_WHITE ? this.whiteBought : this.blackBought;
    }

    get turn() {
        return (this.numTurns + 1) % 2;
    }

    get finished() {
        return this.result !== C.COLOR_NONE;
    }

    // --- Stagnation (State.as:1291-1370) ---

    incrementTurnNoProgressCounters() {
        for (let i = 0; i < NUM_LEVELS_OF_DRAW_VARIABLES; i++) {
            if (this.turn === C.COLOR_WHITE) {
                ++this.whiteNoProgress[i];
            } else {
                ++this.blackNoProgress[i];
            }
        }
    }

    resetTurnNoProgressCounters(level) {
        for (let i = 0; i < level; i++) {
            if (this.turn === C.COLOR_WHITE) {
                this.whiteNoProgress[i] = 0;
            } else {
                this.blackNoProgress[i] = 0;
            }
        }
    }

    resetOppNoProgressCounters(level) {
        for (let i = 0; i < level; i++) {
            if (this.turn === C.COLOR_WHITE) {
                this.blackNoProgress[i] = 0;
            } else {
                this.whiteNoProgress[i] = 0;
            }
        }
    }

    resetColorNoProgressCounters(color, level) {
        for (let i = 0; i < level; i++) {
            if (color === C.COLOR_WHITE) {
                this.whiteNoProgress[i] = 0;
            } else {
                this.blackNoProgress[i] = 0;
            }
        }
    }

    colorIsStagnated(color) {
        for (let i = 0; i < NUM_LEVELS_OF_DRAW_VARIABLES; i++) {
            if (color === C.COLOR_WHITE) {
                if (this.whiteNoProgress[i] >= CUTOFFS_FOR_DRAW[i]) return true;
            } else {
                if (this.blackNoProgress[i] >= CUTOFFS_FOR_DRAW[i]) return true;
            }
        }
        return false;
    }

    // --- Phase queries (State.as:1372-1431) ---

    get inEndDefense() {
        return this.phase === C.PHASE_DEFENSE && this.oppMana.attack === 0;
    }

    get wouldWipeout() {
        return this.phase === C.PHASE_ACTION && !this.glassBroken &&
            this.turnMana.attack >= this.helper.oppDefense &&
            this.turnMana.attack > 0 && this.helper.oppAllUnitsTotal > 0;
    }

    overkillAvailable() {
        return this.phase === C.PHASE_ACTION && this.glassBroken &&
            this.canOverkill && this.turnMana.attack >= this.helper.damageReqdToInjureOverkill;
    }

    get inEndBO() {
        if (this.phase === C.PHASE_ACTION && this.glassBroken) {
            if (this.controlledLane !== -1 && this.turn === C.COLOR_WHITE) return true;
            if (this.canOverkill) {
                return this.turnMana.attack < this.helper.damageReqdToInjureOverkill;
            }
            return this.turnMana.attack < this.helper.damageReqdToInjureBreach;
        }
        return false;
    }

    get canBreach() {
        return this.phase === C.PHASE_ACTION && this.helper.oppDefense === 0;
    }

    get canOverkill() {
        return this.phase === C.PHASE_ACTION && this.helper.oppNonInvTotal === 0;
    }

    get haveWBOed() {
        return this.phase === C.PHASE_ACTION && this.glassBroken &&
            (this.helper.wipedOut.length > 0 || this.helper.breached.length > 0 || this.helper.overkilled.length > 0);
    }

    get haveBOed() {
        return this.phase === C.PHASE_ACTION && this.glassBroken &&
            (this.helper.breached.length > 0 || this.helper.overkilled.length > 0);
    }

    get haveOverkilled() {
        return this.phase === C.PHASE_ACTION && this.glassBroken && this.helper.overkilled.length > 0;
    }

    // --- Instance queries (State.as:2120-2260) ---

    allCardsOfColorWithName(color, cardName, countUnderConstruction, countDelayed, excludeAssigned, exclude, countConstructionOne) {
        if (exclude === undefined) exclude = null;
        if (countConstructionOne === undefined) countConstructionOne = false;
        const answer = [];
        this.table.forEach((inst) => {
            if (inst.cardName === cardName && inst.owner === color && !inst.dead) {
                if (exclude !== null && inst.instId === exclude.instId) return;
                if (inst.constructionTime > 1 && !countUnderConstruction) return;
                if (inst.constructionTime === 1 && !countConstructionOne && !countUnderConstruction) return;
                if (!countDelayed && inst.delay > 0) return;
                if (excludeAssigned && inst.role === C.ROLE_ASSIGNED) return;
                answer.push(inst);
            }
        });
        return answer;
    }

    hasUnassigned(color, cardName, num) {
        if (num === undefined) num = 0;
        return this.allCardsOfColorWithName(color, cardName, false, false, true).length > num;
    }

    hasAssigned(color, cardName) {
        let found = false;
        this.table.forEach((inst) => {
            if (inst.cardName === cardName && inst.owner === color && !inst.dead && inst.role === C.ROLE_ASSIGNED) {
                found = true;
            }
        });
        return found;
    }

    hasDead(color, cardName) {
        let found = false;
        this.table.forEach((inst) => {
            if (inst.cardName === cardName && inst.owner === color && inst.dead) {
                found = true;
            }
        });
        return found;
    }

    numAssigned(color, cardName) {
        let answer = 0;
        this.table.forEach((inst) => {
            if (inst.cardName === cardName && inst.owner === color && !inst.dead && inst.role === C.ROLE_ASSIGNED) {
                answer++;
            }
        });
        return answer;
    }

    numDead(color, cardName) {
        let answer = 0;
        this.table.forEach((inst) => {
            if (inst.cardName === cardName && inst.owner === color && inst.dead) {
                answer++;
            }
        });
        return answer;
    }

    maxNumInstsPerPlayer() {
        let count0 = 0, count1 = 0;
        this.table.forEach((inst) => {
            if (inst.owner === 0) count0++;
            else count1++;
        });
        return Math.max(count0, count1);
    }

    instIdsInRandomOrder(randomSeed, onlyEnemies) {
        if (randomSeed === undefined || randomSeed === null) randomSeed = State.rnd;
        if (onlyEnemies === undefined) onlyEnemies = false;
        const sortedInts = [];
        this.table.forIn((key) => {
            const inst = this.table.get(key);
            if (inst.owner !== this.turn || !onlyEnemies) {
                sortedInts.push(Number(key));
            }
        });
        sortedInts.sort((a, b) => a - b);
        const answer = [];
        for (const tt of sortedInts) {
            answer.splice(randomSeed.integer(answer.length + 1), 0, tt);
        }
        return answer;
    }

    cardIdsInRandomOrder() {
        const answer = [];
        for (let i = 0; i < this.cards.length; i++) {
            answer.splice(Rndm.integer(answer.length + 1), 0, this.cards[i].cardId);
        }
        return answer;
    }

    // --- Sac/Netherfy helpers (State.as:2224-2353) ---

    wouldBeSacced(sac, originInst) {
        if (originInst === undefined) originInst = null;
        const answer = [];
        for (let i = 0; i < sac.length; i++) {
            const toSac = this.allCardsOfColorWithName(this.turn, sac[i].cardName, false, false, false, originInst);
            toSac.sort((a, b) => this._order(a, b, true));
            for (let j = 0; j < sac[i].multiplicity; j++) {
                answer.push(toSac[j]);
            }
        }
        return answer;
    }

    wouldBeNetherfied() {
        const candidates = [];
        this.table.forEach((inst) => {
            if (inst.cardName === 'Drone' && inst.owner === 1 - this.turn &&
                !inst.dead && inst.constructionTime === 0 && !inst.blocking) {
                candidates.push(inst);
            }
        });
        if (candidates.length === 0) return null;
        candidates.sort((a, b) => this._compareInstNether(a, b));
        return candidates[0];
    }

    // --- Private mutation helpers ---

    _createInst(card, owner, bought, buildTime, invulnerable, instId) {
        this.nextInstId = Math.max(this.nextInstId, instId + 1);
        const tempInst = new Inst(card, owner, bought, buildTime, invulnerable, instId, this.laneId);
        this.table.set(tempInst.instId, tempInst);
        return tempInst;
    }

    _deleteInst(instId) {
        C.ASSERT(this.table.has(instId), "Tried to delete an Inst that doesn't exist.");
        this.table.delete(instId);
    }

    _payCost(cost, inst) {
        if (!cost.isEmpty) {
            this.turnMana.subtract(cost);
        }
    }

    _unpayCost(cost, inst) {
        if (!cost.isEmpty) {
            this.turnMana.add(cost);
        }
    }

    _sac(sacDesc, originInst) {
        const toSac = this.wouldBeSacced(sacDesc, originInst);
        for (let i = 0; i < toSac.length; i++) {
            toSac[i].deadness = C.DEADNESS_SACCED;
            if (toSac[i].card.hasAbility) {
                C.ASSERT(toSac[i].role === C.ROLE_ASSIGNED || toSac[i].card.abilityScript.selfsac,
                    'Tried to sac without enough assigned ' + toSac[i].card.UIPlural + ' to sac.');
                toSac[i].role = C.ROLE_INERT;
            }
        }
    }

    _unsac(sacDesc, originInst) {
        for (let i = 0; i < sacDesc.length; i++) {
            const toUnsac = [];
            this.table.forEach((inst) => {
                if (inst.cardName === sacDesc[i].cardName && inst.owner === this.turn &&
                    inst.constructionTime === 0 && inst.delay === 0 &&
                    inst.deadness === C.DEADNESS_SACCED && inst.instId !== originInst.instId) {
                    toUnsac.push(inst);
                }
            });
            toUnsac.sort((a, b) => this._order(b, a, true));
            for (let j = 0; j < sacDesc[i].multiplicity; j++) {
                toUnsac[j].deadness = C.DEADNESS_ALIVE;
                if (toUnsac[j].card.hasAbility) {
                    if (toUnsac[j].card.abilityScript.selfsac) {
                        toUnsac[j].role = C.ROLE_DEFAULT;
                    } else {
                        toUnsac[j].role = C.ROLE_ASSIGNED;
                    }
                }
            }
        }
    }

    _netherfy(nether) {
        const toNetherfy = this.wouldBeNetherfied();
        C.ASSERT(toNetherfy !== null, 'Tried to netherfy when there is no legal target.');
        toNetherfy.deadness = C.DEADNESS_NETHERED;
    }

    _unnetherfy(nether) {
        const candidates = [];
        this.table.forEach((inst) => {
            if (inst.cardName === 'Drone' && inst.deadness === C.DEADNESS_NETHERED) {
                candidates.push(inst);
            }
        });
        candidates.sort((a, b) => this._compareInstNether(b, a));
        C.ASSERT(candidates.length > 0, 'Found no candidates to unnetherfy.');
        candidates[0].deadness = C.DEADNESS_ALIVE;
    }

    // --- Script execution (State.as:2355-2564) ---

    _runScriptForward(script, scriptType, inst, createIds) {
        if (script === null) return;

        if (!script.receive.isEmpty) {
            this.turnMana.add(script.receive);
        }

        for (let i = 0; i < script.create.length; i++) {
            const temp = script.create[i];
            const color = temp.own ? this.turn : (1 - this.turn);
            for (let j = 0; j < temp.multiplicity; j++) {
                let createdInst;
                if (scriptType === C.SCRIPTTYPE_BUY) {
                    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, true, createIds[i][j]);
                    inst.buyCreateIds[i][j] = createdInst.instId;
                    createdInst.creatorIdFromBuyOrAbility = inst.instId;
                } else if (scriptType === C.SCRIPTTYPE_BEGINOWNTURN) {
                    C.ASSERT(createIds === null, 'Tried to give createIds for beginOwnTurnScript.');
                    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, temp.invuln, this.nextInstId++);
                    inst.beginOwnTurnCreateIds[i][j] = createdInst.instId;
                    createdInst.creatorIdFromBeginTurn = inst.instId;
                } else if (scriptType === C.SCRIPTTYPE_ABILITY) {
                    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, temp.invuln, createIds[i][j]);
                    inst.abilityCreateIds[i][j] = createdInst.instId;
                    createdInst.creatorIdFromBuyOrAbility = inst.instId;
                } else {
                    C.ASSERT(false, 'Invalid scripttype.');
                }
                if (temp.lifespan !== -1) {
                    createdInst.lifespan = temp.lifespan;
                }
            }
        }

        if (script.selfsac) {
            inst.deadness = C.DEADNESS_SELFSACCED;
        }
        if (script.delay > 0) {
            inst.delay = script.delay;
        }
        if (script.scan > 0 && this.counters) {
            this.counters['numScanned'] = (this.counters['numScanned'] || 0) + script.scan;
        }
        if (script.massChill > 0) {
            this.table.forEach((targetInst) => {
                if (targetInst.owner !== inst.owner && targetInst.blocking) {
                    targetInst.disruptDamage += script.massChill;
                    if (targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage) {
                        targetInst.blocking = false;
                    }
                    targetInst.disruptorIds.push(inst.instId);
                }
            });
        }
    }

    _runScriptBackward(script, scriptType, inst) {
        if (script === null) return;
        C.ASSERT(scriptType !== C.SCRIPTTYPE_BEGINOWNTURN, 'Tried to run a beginOwnTurnScript backwards.');

        if (!script.receive.isEmpty) {
            this.turnMana.subtract(script.receive);
        }

        // Delete created instances
        const deleteInsts = (instIds) => {
            for (let i = 0; i < instIds.length; i++) {
                for (let j = 0; j < instIds[i].length; j++) {
                    this._deleteInst(instIds[i][j]);
                    instIds[i][j] = -1;
                }
            }
        };

        if (scriptType === C.SCRIPTTYPE_BUY) {
            deleteInsts(inst.buyCreateIds);
        } else if (scriptType === C.SCRIPTTYPE_ABILITY) {
            deleteInsts(inst.abilityCreateIds);
        } else {
            C.ASSERT(false, 'Invalid scripttype.');
        }

        if (script.selfsac) {
            inst.deadness = C.DEADNESS_ALIVE;
        }
        if (script.delay > 0) {
            inst.delay = 0;
        }
        if (script.scan > 0 && this.counters) {
            this.counters['numScanned'] -= script.scan;
        }
        if (script.massChill > 0) {
            this.table.forEach((targetInst) => {
                if (targetInst.disruptorIds.indexOf(inst.instId) >= 0) {
                    targetInst.disruptDamage -= script.massChill;
                    if (targetInst.disruptDamage < targetInst.damageItCanTake + targetInst.damage) {
                        targetInst.blocking = true;
                    }
                    const location = targetInst.disruptorIds.indexOf(inst.instId);
                    C.ASSERT(location >= 0, 'disruptorIds messed up.');
                    targetInst.disruptorIds.splice(location, 1);
                }
            });
        }
    }

    // --- Body/spell collection and mana rot (State.as:2566-3142) ---

    _collectBodies() {
        const toDelete = [];
        this.table.forEach((inst) => {
            if (inst.dead) {
                this.resetColorNoProgressCounters(1 - inst.owner, LEVEL_OPP_UNIT_COLLECTED);
                toDelete.push(inst.instId);
            }
        });
        for (const id of toDelete) {
            this._deleteInst(id);
        }
    }

    _collectSpells() {
        const toDelete = [];
        this.table.forEach((inst) => {
            if (inst.card.cardType === C.CARDTYPE_SPELL) {
                toDelete.push(inst.instId);
            }
        });
        for (const id of toDelete) {
            this._deleteInst(id);
        }
    }

    _manaRots() {
        if (this.turnMana.pool[C.MANA_H] > 0) {
            this.turnMana.pool[C.MANA_H] = 0;
        }
        if (this.turnMana.pool[C.MANA_B] > 0) {
            this.turnMana.pool[C.MANA_B] = 0;
        }
        if (this.turnMana.pool[C.MANA_R] > 0) {
            this.turnMana.pool[C.MANA_R] = 0;
        }
        if (this.turnMana.pool[C.MANA_A] > 0 && this.helper.oppDefense === 0 &&
            !(this.controlledLane !== -1 && this.turn === C.COLOR_WHITE)) {
            this.turnMana.pool[C.MANA_A] = 0;
        }
    }

    // --- Swoosh (State.as:2582-3073) ---

    swoosh() {
        // Deterministic seed for randomized effects (Robo Santa, etc.)
        let deterministicArbitrarySeed = this.numTurns;
        for (let i = 0; i < this.cards.length; i++) {
            deterministicArbitrarySeed = (deterministicArbitrarySeed * this.cards[i].cardName.length % 49979687) | 0;
            deterministicArbitrarySeed = (deterministicArbitrarySeed + this.cards[i].startingHealth) | 0;
        }
        lazySeedRandomizer(deterministicArbitrarySeed);

        this.phase = C.PHASE_ACTION;
        this.glassBroken = false;

        const stuffInPlay = [];
        const annihilators = {};
        const goldAnnihilators = {};

        // Snapshot instIds (iteration over mutable table)
        const copyOfInstIds = [];
        this.table.forIn((key) => copyOfInstIds.push(key));

        for (const t of copyOfInstIds) {
            const inst = this.table.get(t);
            if (!inst) continue; // May have been deleted during iteration
            const card = inst.card;

            if (inst.owner === this.turn) {
                // Clear damage/disruption
                if (inst.damage > 0) inst.damage = 0;
                if (inst.disruptDamage > 0) inst.disruptDamage = 0;

                // Construction tick
                if (inst.constructionTime > 0) {
                    --inst.constructionTime;
                    this.resetTurnNoProgressCounters(LEVEL_BUILDTIME_TICKED);
                    if (inst.constructionTime !== 0) {
                        if (inst.role === C.ROLE_SELLABLE) inst.role = C.ROLE_INERT;
                        continue;
                    }
                }
                // Delay tick
                else if (inst.delay > 0) {
                    --inst.delay;
                    this.resetTurnNoProgressCounters(LEVEL_DELAY_TICKED);
                    if (inst.delay !== 0) {
                        if (inst.role !== C.ROLE_INERT) inst.role = C.ROLE_INERT;
                        continue;
                    }
                }
                // Lifespan tick
                else if (inst.lifespan > 0) {
                    --inst.lifespan;
                    this.resetOppNoProgressCounters(LEVEL_OPP_LIFESPAN_TICKED);
                    if (inst.lifespan === 0) {
                        inst.deadness = C.DEADNESS_AGED;
                        this._deleteInst(inst.instId);
                        continue;
                    }
                }

                stuffInPlay.push(inst);

                // Refresh role and blocking
                if (card.hasAbility) {
                    inst.role = C.ROLE_DEFAULT;
                } else {
                    inst.role = C.ROLE_INERT;
                }
                inst.blocking = card.defaultBlocking;

                // Health regeneration (fragile units)
                if (card.healthGained !== 0) {
                    inst.health += card.healthGained;
                    if (inst.health > card.healthMax) inst.health = card.healthMax;
                    if (card.healthUsed > 0) {
                        this.resetTurnNoProgressCounters(LEVEL_HP_HEALED_ON_UNIT_WITH_PAY_HP_ABILITY);
                    }
                }

                // Charge regeneration
                if (card.chargeGained !== 0) {
                    inst.charge += card.chargeGained;
                    if (inst.charge > card.chargeMax) inst.charge = card.chargeMax;
                    this.resetTurnNoProgressCounters(LEVEL_CHARGE_RECHARGED);
                }

                // Special card handling (Robo Santa, Condimus, etc.)
                if (card.cardName === 'Robo Santa') {
                    initRandomizerIfNeeded();
                    const scripts = [
                        { create: [['Gauss Cannon', 'own', 1, 1]] },
                        { create: [['Infusion Grid', 'own', 1, 1]] },
                        { create: [['Wild Drone', 'own', 1, 1]] },
                        { create: [['Shiver Yeti', 'own', 1, 1]] },
                        { create: [['Scorchilla', 'own', 1, 2]] },
                        { create: [['Protoplasm', 'own', 1, 2]] },
                        { create: [['Resophore', 'own', 1, 2]] },
                        { create: [['Shredder', 'own', 1, 1]] },
                    ];
                    const choice = turnRandomizer.integer(1, 9) - 1;
                    this._runScriptForward(new Script(scripts[choice]), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                } else if (card.cardName === 'Robo Santa 2016') {
                    // Deterministic 20-outcome switch (no PRNG needed)
                    // AS3: int(this.numTurns / 3) — integer division
                    const rs2016choice = ((deterministicArbitrarySeed + this.numTurns * this.numTurns + ((this.numTurns / 3) | 0)) % 20 + 20) % 20;
                    const rs2016scripts = [
                        { create: [['Xaetron', 'own', 1, 4]] },
                        { create: [['Feral Warden', 'own', 1, 1]] },
                        { create: [['Infusion Grid', 'own', 1, 1]] },
                        { create: [['Wild Drone', 'own', 1, 1]] },
                        { create: [['Blood Phage', 'own', 1, 2]] },
                        { create: [['Scorchilla', 'own', 1, 2]] },
                        { create: [['Cauterizer', 'own', 1, 1]] },
                        { create: [['Centrifuge', 'own', 1, 4]] },
                        { create: [['Shredder', 'own', 1, 1]] },
                        { create: [['Chieftain', 'own', 1, 2]] },
                        { create: [['Cynestra', 'own', 1, 5]] },
                        { create: [['Frost Brooder', 'own', 1, 1]] },
                        { create: [['Hannibull', 'own', 1, 3]] },
                        { create: [['Iceblade Golem', 'own', 1, 2]] },
                        { create: [['Iso Kronus', 'own', 1, 3]] },
                        { create: [['Lucina Spinos', 'own', 1, 6]] },
                        { create: [['Protoplasm', 'own', 1, 2]] },
                        { create: [['Sentinel', 'own', 1, 2]] },
                        { create: [['Wall', 'own', 1, 0]] },
                        { create: [['Doomed Wall', 'own', 1, 1]] },
                    ];
                    this._runScriptForward(new Script(rs2016scripts[rs2016choice]), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                } else if (card.cardName === 'Condimus') {
                    initRandomizerIfNeeded();
                    const choice = turnRandomizer.integer(1, 3);
                    if (choice === 1) this._runScriptForward(new Script({ receive: 'G' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                    else this._runScriptForward(new Script({ receive: 'C' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                } else if (card.cardName === 'Blastuit') {
                    initRandomizerIfNeeded();
                    const choice = turnRandomizer.integer(1, 3);
                    if (choice === 1) this._runScriptForward(new Script({ receive: 'B' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                    else this._runScriptForward(new Script({ receive: 'G' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                } else if (card.cardName === 'Aniforge') {
                    initRandomizerIfNeeded();
                    const choice = turnRandomizer.integer(1, 3);
                    if (choice === 1) this._runScriptForward(new Script({ receive: 'CC' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                    else this._runScriptForward(new Script({ receive: 'B' }), C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                } else {
                    this._runScriptForward(card.beginOwnTurnScript, C.SCRIPTTYPE_BEGINOWNTURN, inst, null);
                }

                // Resonate tracking
                if (card.resonate !== null) {
                    if (annihilators[card.resonate]) annihilators[card.resonate].push(inst);
                    else annihilators[card.resonate] = [inst];
                }
                if (card.goldResonate !== null) {
                    if (goldAnnihilators[card.goldResonate]) goldAnnihilators[card.goldResonate].push(inst);
                    else goldAnnihilators[card.goldResonate] = [inst];
                }

                // Special global effects
                if (card.cardName === 'EMP') {
                    inst.deadness = C.DEADNESS_SELFSACCED;
                    // EMP effect handled below
                } else if (card.cardName === 'Deep Impact') {
                    inst.deadness = C.DEADNESS_SELFSACCED;
                } else if (card.cardName === 'Glaciator') {
                    // icySavior handled below
                }
            }
        }

        // Resonate resolution — match annihilators with annihilatees
        const annihilatees = {};
        const goldAnnihilatees = {};
        for (const inst of stuffInPlay) {
            const name = inst.card.cardName;
            if (annihilators[name]) {
                if (annihilatees[name]) annihilatees[name].push(inst);
                else annihilatees[name] = [inst];
            }
            if (goldAnnihilators[name]) {
                if (goldAnnihilatees[name]) goldAnnihilatees[name].push(inst);
                else goldAnnihilatees[name] = [inst];
            }
        }

        // Aurb Magnifier effect
        let yearsOfPlenty = false;
        let EMP = false;
        let deepImpact = false;
        let ARGroans = false;
        let icySavior = false;
        for (const inst of stuffInPlay) {
            if (inst.card.cardName === 'Aurb Magnifier') yearsOfPlenty = true;
            else if (inst.card.cardName === 'EMP' && inst.deadness === C.DEADNESS_SELFSACCED) EMP = true;
            else if (inst.card.cardName === 'Deep Impact' && inst.deadness === C.DEADNESS_SELFSACCED) deepImpact = true;
            else if (inst.card.cardName === 'A.R. Groans') ARGroans = true;
            else if (inst.card.cardName === 'Glaciator') icySavior = true;
        }

        if (yearsOfPlenty) {
            this.table.forEach((inst) => {
                if (inst.cardName === 'Drone' && inst.owner === this.turn && inst.role === C.ROLE_DEFAULT) {
                    ++this.turnMana.pool[C.MANA_P];
                }
            });
            for (let i = 0; i < this.cards.length; i++) {
                if (this.turnBought()[i] > 0 && this.turnSupply()[i] - this.turnBought()[i] > 0) {
                    --this.turnBought()[i];
                }
            }
        }

        if (EMP) {
            const ids = [];
            this.table.forIn((key) => ids.push(key));
            for (const t2 of ids) {
                const inst2 = this.table.get(t2);
                if (inst2 && inst2.card.attackPotential !== 0 && inst2.owner !== this.turn && inst2.constructionTime === 0) {
                    inst2.deadness = C.DEADNESS_NETHERED;
                    this._deleteInst(inst2.instId);
                }
            }
        }

        if (deepImpact) {
            const ids = [];
            this.table.forIn((key) => ids.push(key));
            for (const t2 of ids) {
                const inst2 = this.table.get(t2);
                if (inst2 && inst2.card.workPotential > 0 && inst2.owner !== this.turn && inst2.constructionTime === 0) {
                    inst2.deadness = C.DEADNESS_NETHERED;
                    this._deleteInst(inst2.instId);
                }
            }
        }

        if (ARGroans) {
            initRandomizerIfNeeded();
            for (const t2 of this.instIdsInRandomOrder(turnRandomizer, true)) {
                const inst2 = this.table.get(t2);
                if (inst2 && inst2.owner !== this.turn && inst2.health <= 8 && inst2.constructionTime === 0) {
                    inst2.deadness = C.DEADNESS_NETHERED;
                    this._deleteInst(inst2.instId);
                    break;
                }
            }
        }

        if (icySavior) {
            this.table.forEach((inst) => {
                if (inst.owner !== this.turn && inst.blocking) {
                    inst.blocking = false;
                }
            });
        }

        // Apply resonate bonuses
        for (const name of Object.keys(annihilators)) {
            if (annihilatees[name]) {
                for (const inst of annihilators[name]) {
                    this.turnMana.attack += annihilatees[name].length;
                }
            }
        }
        for (const name of Object.keys(goldAnnihilators)) {
            if (goldAnnihilatees[name]) {
                for (const inst of goldAnnihilators[name]) {
                    this.turnMana.money += goldAnnihilatees[name].length;
                }
            }
        }

        this.incrementTurnNoProgressCounters();
        // executeTriggers is no-op for PvP (empty triggers array)
    }

    // --- processMove (State.as:1433-2064) ---

    processMove(type, instId, targetId, cardId, buyCreateIds, abilityCreateIds, delayStateHelperUpdate) {
        if (instId === undefined) instId = -1;
        if (targetId === undefined) targetId = -1;
        if (cardId === undefined) cardId = -1;
        if (buyCreateIds === undefined) buyCreateIds = null;
        if (abilityCreateIds === undefined) abilityCreateIds = null;
        if (delayStateHelperUpdate === undefined) delayStateHelperUpdate = false;

        if (this.blockTriggers) return;

        let inst, card, targetInst, damage;

        if (type === C.MOVE_ASSIGN) {
            inst = this.instIdToInst(instId);
            card = inst.card;
            inst.role = C.ROLE_ASSIGNED;
            inst.blocking = card.assignedBlocking;

            if (card.healthUsed > 0) {
                inst.health -= card.healthUsed;
                if (inst.health === 0) {
                    inst.deadness = C.DEADNESS_SELFSACCED;
                }
            }
            if (card.chargeUsed > 0) {
                inst.charge -= card.chargeUsed;
            }
            this._payCost(card.abilityCost, inst);
            this._sac(card.abilitySac, inst);
            if (card.abilityNetherfy) {
                this._netherfy(inst);
            }
            this._runScriptForward(card.abilityScript, C.SCRIPTTYPE_ABILITY, inst, abilityCreateIds);

            if (card.targetHas) {
                targetInst = this.instIdToInst(targetId);
                if (card.targetAction === C.TARGETACTION_DISRUPT) {
                    targetInst.disruptDamage += card.targetAmount;
                    if (targetInst.disruptDamage >= targetInst.damageItCanTake + targetInst.damage) {
                        targetInst.blocking = false;
                    }
                    targetInst.disruptorIds.push(instId);
                } else if (card.targetAction === C.TARGETACTION_SNIPE) {
                    targetInst.deadness = C.DEADNESS_SNIPED;
                    targetInst.sniperId = instId;
                    // Comm Server chain snipe
                    if (targetInst.cardName === 'Comm Server') {
                        this.table.forEach((other) => {
                            if (other.owner === C.COLOR_BLACK && other !== targetInst) {
                                other.deadness = C.DEADNESS_SNIPED;
                                other.sniperId = instId;
                            }
                        });
                    }
                }
                inst.target = targetId;
            }
            if (!delayStateHelperUpdate) this.helper.update(this);
        }
        else if (type === C.MOVE_UNASSIGN) {
            inst = this.instIdToInst(instId);
            card = inst.card;
            inst.role = C.ROLE_DEFAULT;
            inst.blocking = card.defaultBlocking;

            if (card.healthUsed > 0) {
                if (inst.health === 0) inst.deadness = C.DEADNESS_ALIVE;
                inst.health += card.healthUsed;
            }
            if (card.chargeUsed > 0) {
                inst.charge += card.chargeUsed;
            }
            this._unpayCost(card.abilityCost, inst);
            this._unsac(card.abilitySac, inst);
            if (card.abilityNetherfy) {
                this._unnetherfy(inst);
            }
            this._runScriptBackward(card.abilityScript, C.SCRIPTTYPE_ABILITY, inst);

            if (card.targetHas) {
                C.ASSERT(targetId === inst.target, 'Target mismatch.');
                targetInst = this.instIdToInst(targetId);
                if (card.targetAction === C.TARGETACTION_DISRUPT) {
                    targetInst.disruptDamage -= card.targetAmount;
                    if (targetInst.disruptDamage < targetInst.damageItCanTake + targetInst.damage) {
                        targetInst.blocking = true;
                    }
                    const loc = targetInst.disruptorIds.indexOf(instId);
                    C.ASSERT(loc >= 0, 'disruptorIds messed up.');
                    targetInst.disruptorIds.splice(loc, 1);
                } else if (card.targetAction === C.TARGETACTION_SNIPE) {
                    targetInst.deadness = C.DEADNESS_ALIVE;
                    targetInst.sniperId = -1;
                    if (targetInst.cardName === 'Comm Server') {
                        this.table.forEach((other) => {
                            if (other.owner === C.COLOR_BLACK && other !== targetInst) {
                                other.deadness = C.DEADNESS_ALIVE;
                                other.sniperId = -1;
                            }
                        });
                    }
                }
                inst.target = -1;
            }
            if (!delayStateHelperUpdate) this.helper.update(this);
        }
        else if (type === C.MOVE_BUY) {
            card = this.cardIdToCard(cardId);
            inst = this._createInst(card, this.turn, true, card.buildTime, true, instId);
            ++this.turnBought()[card.cardId];
            this._payCost(card.buyCost, inst);
            this._sac(card.buySac, inst);
            this._runScriptForward(card.buyScript, C.SCRIPTTYPE_BUY, inst, buyCreateIds);
            if (!delayStateHelperUpdate) this.helper.update(this);
        }
        else if (type === C.MOVE_SELL) {
            inst = this.instIdToInst(instId);
            card = inst.card;
            C.ASSERT(card.cardId === cardId);
            --this.turnBought()[card.cardId];
            this._unpayCost(card.buyCost, inst);
            this._unsac(card.buySac, inst);
            this._runScriptBackward(card.buyScript, C.SCRIPTTYPE_BUY, inst);
            this._deleteInst(inst.instId);
            if (!delayStateHelperUpdate) this.helper.update(this);
        }
        else if (type === C.MOVE_MELEE) {
            inst = this.instIdToInst(instId);
            card = inst.card;
            C.ASSERT(!card.fragile, 'Fragile cards cannot be meleed.');
            damage = inst.health;
            this.turnMana.attack -= damage;
            inst.damage += damage;
            inst.deadness = C.DEADNESS_MELEED;
            this.helper.update(this);
        }
        else if (type === C.MOVE_UNMELEE) {
            inst = this.instIdToInst(instId);
            damage = inst.health;
            this.turnMana.attack += damage;
            inst.damage -= damage;
            inst.deadness = C.DEADNESS_ALIVE;
            this.helper.update(this);
        }
        else if (type === C.MOVE_DEFEND) {
            inst = this.instIdToInst(instId);
            damage = inst.health > this.oppMana.attack ? this.oppMana.attack : inst.health;
            this.oppMana.attack -= damage;
            inst.damage += damage;
            if (inst.card.fragile) inst.health -= damage;
            if (inst.damageItCanTake === 0) {
                inst.deadness = C.DEADNESS_BLOCKED;
            }
            this.helper.update(this);
        }
        else if (type === C.MOVE_UNDEFEND) {
            inst = this.instIdToInst(instId);
            damage = inst.damage;
            this.oppMana.attack += damage;
            inst.damage -= damage;
            if (inst.card.fragile) inst.health += damage;
            if (inst.deadness === C.DEADNESS_BLOCKED) {
                inst.deadness = C.DEADNESS_ALIVE;
            }
            this.helper.update(this);
        }
        else if (type === C.MOVE_BREACH_OR_OVERKILL) {
            inst = this.instIdToInst(instId);
            if (inst.health > this.turnMana.attack) {
                damage = this.turnMana.attack;
                C.ASSERT(inst.card.fragile, 'Tried to partially breach a non-fragile unit.');
            } else {
                damage = inst.health;
            }
            this.turnMana.attack -= damage;
            inst.damage += damage;
            if (inst.card.fragile) inst.health -= damage;
            if (inst.damageItCanTake === 0) {
                inst.deadness = C.DEADNESS_WBO;
                if (inst.card.deathScript) {
                    this._runScriptForward(inst.card.deathScript, C.SCRIPTTYPE_ABILITY, inst, abilityCreateIds);
                }
            }
            this.helper.update(this);
        }
        else if (type === C.MOVE_UNBREACH_OR_UNOVERKILL) {
            inst = this.instIdToInst(instId);
            damage = inst.damage;
            this.turnMana.attack += damage;
            inst.damage -= damage;
            if (inst.card.fragile) inst.health += damage;
            if (inst.deadness === C.DEADNESS_WBO) {
                inst.deadness = C.DEADNESS_ALIVE;
                if (inst.card.deathScript) {
                    this._runScriptBackward(inst.card.deathScript, C.SCRIPTTYPE_ABILITY, inst);
                }
            }
            this.helper.update(this);
        }
        else if (type === C.MOVE_WIPEOUT) {
            this.glassBroken = true;
            for (const defender of this.helper.oppDefenders) {
                damage = defender.health;
                this.turnMana.attack -= damage;
                defender.damage += damage;
                if (defender.card.fragile) defender.health -= damage;
                defender.deadness = C.DEADNESS_WBO;
            }
            this.helper.update(this);
        }
        else if (type === C.MOVE_UNWIPEOUT) {
            for (const wInst of this.helper.wipedOut) {
                damage = wInst.damage;
                this.turnMana.attack += damage;
                wInst.damage -= damage;
                if (wInst.card.fragile) wInst.health += damage;
                wInst.deadness = C.DEADNESS_ALIVE;
            }
            this.glassBroken = false;
            this.helper.update(this);
        }
        else if (type === C.MOVE_END_DEFENSE) {
            if (this.helper.partiallyDamagedInst !== null &&
                this.helper.partiallyDamagedInst.card.fragile &&
                this.helper.partiallyDamagedInst.damage > this.helper.partiallyDamagedInst.card.healthGained) {
                this.resetOppNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING);
            }
            this._collectBodies();
            this.swoosh();
            this.helper.update(this);
        }
        else if (type === C.MOVE_ENTER_CONFIRM) {
            this.endTurnObject = new EndTurnObject(this);

            // Stagnation priority chain (State.as:1913-1952)
            if (this.turnMana.attack > 0 && this.helper.oppDefense > 0 &&
                this.turnMana.attack >= this.helper.maxOppDefenderHealth) {
                this.resetTurnNoProgressCounters(LEVEL_OPP_UNIT_COLLECTED);
            } else if (this.endTurnObject.unitsCreated.length > 0 || this.endTurnObject.unitsBought.length > 0) {
                this.resetTurnNoProgressCounters(LEVEL_CARD_BOUGHT_OR_INST_CREATED);
            } else if (this.helper.partiallyDamagedInst !== null &&
                       this.helper.partiallyDamagedInst.damage > this.helper.partiallyDamagedInst.card.healthGained) {
                this.resetTurnNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING);
            } else if (this.turnMana.attack > 0 && this.helper.oppDefense > 0 &&
                       this.turnMana.attack >= this.helper.damageReqdToMakeProgressOnFragileBlocker) {
                this.resetTurnNoProgressCounters(LEVEL_DAMAGE_BY_MORE_THAN_HEALING);
            } else if (this.helper.totalProducedThisTurn.money > 0) {
                this.resetTurnNoProgressCounters(LEVEL_MONEY_STORED);
            }

            // Green mana stagnation checks
            if (this.helper.totalProducedThisTurn.amountOf(C.MANA_G) > 0) {
                const hasCard = (name) => this.cardNameToCardId.hasOwnProperty(name);
                if (hasCard('Cluster Bolt') &&
                    this.turnMana.amountOf(C.MANA_G) < 4 * (this.turnSupply()[this.cardNameToCardId['Cluster Bolt']] - this.turnBought()[this.cardNameToCardId['Cluster Bolt']])) {
                    this.resetTurnNoProgressCounters(LEVEL_GAS_STORED_WITH_CLUSTER_BOLT);
                } else if (hasCard('Gauss Charge') &&
                    this.turnMana.amountOf(C.MANA_G) < Math.min(
                        this.turnSupply()[this.cardNameToCardId['Gauss Charge']] - this.turnBought()[this.cardNameToCardId['Gauss Charge']],
                        this.turnMana.money)) {
                    this.resetTurnNoProgressCounters(LEVEL_GAS_STORED_WITH_GAUSS_CHARGE);
                } else if (this.allCardsOfColorWithName(this.turn, 'Zemora Voidbringer', true, true, false).length > 0 &&
                    this.turnMana.amountOf(C.MANA_G) < 8) {
                    this.resetTurnNoProgressCounters(LEVEL_GAS_STORED_WITH_ZEMORA);
                } else if (this.turnMana.amountOf(C.MANA_G) < 3 * this.allCardsOfColorWithName(this.turn, 'Gaussite Symbiote', true, true, false).length) {
                    this.resetTurnNoProgressCounters(LEVEL_GAS_STORED_WITH_GAUSSITE_SYMBIOTE);
                }
            }

            this.phase = C.PHASE_CONFIRM;
            this.helper.update(this);
            this._clearInstArrowIds();
            this._manaRots();
            this._collectSpells();
            this._collectBodies();
            this.endTurnObject.checkWin = this._checkWin();
            this.endTurnObject.oppCouldClaimDraw = this.colorIsStagnated(this.turn);
        }
        else if (type === C.MOVE_COMMIT) {
            if (this.controlledLane === -1) {
                // executeTriggers — no-op for PvP (empty triggers array)
                if (this.objectives !== null) {
                    this.result = this._checkWin();
                } else {
                    this.result = this.endTurnObject.checkWin;
                }
                if (this.result === C.COLOR_NONE) {
                    ++this.numTurns;
                    if (this.oppMana.attack === 0) {
                        this.swoosh();
                        this.helper.update(this);
                    } else {
                        this.phase = C.PHASE_DEFENSE;
                        this.helper.update(this);
                    }
                }
            }
        }
        else if (type !== C.MOVE_EMOTE) {
            C.ASSERT(false, 'Invalid Move type in processMove.');
        }
    }

    // --- Win detection (State.as:3298-3327 — PvP only) ---

    _checkWin() {
        // For PvP (no objectives), use simple unit-counting logic
        if (this.objectives === null) {
            if (this.helper.ownAllUnitsTotal > 0 && this.helper.oppAllUnitsTotal === 0) {
                return this.turn;
            }
            if (this.helper.ownAllUnitsTotal === 0 && this.helper.oppAllUnitsTotal > 0) {
                return 1 - this.turn;
            }
            if (this.helper.ownAllUnitsTotal === 0 && this.helper.oppAllUnitsTotal === 0) {
                return C.COLOR_DRAW_MUTUAL_ELIMINATION;
            }
            if (this.helper.allOppUnitsDoomed) {
                return this.turn;
            }
            // NOTE: do NOT win just because the opponent has only under-construction units.
            // Those units build next turn and survive (golden armor) — the opponent isn't
            // defeated; you must actually kill them (overkill once their build completes, or
            // they remain). AS3 checkWin (State.as:3309-3327) has no such rule. The previous
            // port added `oppAllUnitsTotal>0 && oppNonInvTotal===0 -> win`, which ended games
            // prematurely whenever a breach left the opponent with only under-construction
            // units (e.g. salty 1-unit-a-turn buys), truncating the remaining recorded turns.
            return C.COLOR_NONE;
        }
        // Mission objectives not supported in headless PvP
        return C.COLOR_NONE;
    }

    // --- Init helpers (State.as:3144-3258) ---

    _createInstsFromInitArray(initArray, color, calledAtInit, parent) {
        if (parent === undefined) parent = null;
        for (let i = 0; i < initArray.length; i++) {
            const card = this.cardNameToCard(initArray[i][1]);
            const multiplicity = initArray[i][0] | 0;
            for (let j = 0; j < multiplicity; j++) {
                const inst = this._createInst(card, color, false,
                    calledAtInit ? 0 : card.buildTime, false, this.nextInstId++);
                // For init units at buildTime=0, set role based on ability
                // (Inst constructor defaults non-bought to INERT, but units with
                // abilities need DEFAULT to be clickable from the start)
                if (calledAtInit) {
                    inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT;
                }
                for (let k = 2; k < initArray[i].length; k += 2) {
                    switch (initArray[i][k]) {
                        case 'role':
                            switch (initArray[i][k + 1]) {
                                case 'default': inst.role = C.ROLE_DEFAULT; break;
                                case 'assigned': inst.role = C.ROLE_ASSIGNED; break;
                                case 'sellable': inst.role = C.ROLE_SELLABLE; break;
                                case 'inert': inst.role = C.ROLE_INERT; break;
                                default: C.ASSERT(false, 'Invalid role.');
                            }
                            break;
                        case 'blocking': inst.blocking = !!initArray[i][k + 1]; break;
                        case 'dead':
                            switch (initArray[i][k + 1]) {
                                case 'alive': inst.deadness = C.DEADNESS_ALIVE; break;
                                case 'selfsacced': inst.deadness = C.DEADNESS_SELFSACCED; break;
                                case 'sacced': inst.deadness = C.DEADNESS_SACCED; break;
                                case 'blocked': inst.deadness = C.DEADNESS_BLOCKED; break;
                                case 'meleed': inst.deadness = C.DEADNESS_MELEED; break;
                                case 'wbo': inst.deadness = C.DEADNESS_WBO; break;
                                case 'sniped': inst.deadness = C.DEADNESS_SNIPED; break;
                            }
                            break;
                        case 'delay':
                            inst.delay = initArray[i][k + 1];
                            if (inst.delay > 0) {
                                inst.role = C.ROLE_INERT;
                                inst.blocking = false;
                                inst.constructionTime = 0;
                            } else {
                                inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT;
                                inst.blocking = card.defaultBlocking;
                            }
                            break;
                        case 'lifespan': inst.lifespan = initArray[i][k + 1]; break;
                        case 'charge': inst.charge = initArray[i][k + 1]; break;
                        case 'buildTime':
                            inst.constructionTime = initArray[i][k + 1];
                            if (inst.constructionTime > 0) {
                                inst.role = C.ROLE_INERT;
                                inst.blocking = false;
                                inst.delay = 0;
                            } else {
                                inst.role = card.hasAbility ? C.ROLE_DEFAULT : C.ROLE_INERT;
                                inst.blocking = card.defaultBlocking;
                            }
                            break;
                        case 'toughness':
                        case 'hp':
                            inst.health = initArray[i][k + 1];
                            break;
                    }
                }
            }
        }
    }

    _clearInstArrowIds() {
        this.table.forEach((inst) => {
            inst.target = -1;
            for (let i = 0; i < inst.buyCreateIds.length; i++) {
                for (let j = 0; j < inst.buyCreateIds[i].length; j++) {
                    inst.buyCreateIds[i][j] = -1;
                }
            }
            for (let i = 0; i < inst.beginOwnTurnCreateIds.length; i++) {
                for (let j = 0; j < inst.beginOwnTurnCreateIds[i].length; j++) {
                    inst.beginOwnTurnCreateIds[i][j] = -1;
                }
            }
            for (let i = 0; i < inst.abilityCreateIds.length; i++) {
                for (let j = 0; j < inst.abilityCreateIds[i].length; j++) {
                    inst.abilityCreateIds[i][j] = -1;
                }
            }
            inst.creatorIdFromBuyOrAbility = -1;
            inst.creatorIdFromBeginTurn = -1;
            inst.disruptorIds = [];
            inst.sniperId = -1;
        });
    }

    // --- Comparison functions for sorting (State.as:4150-4388) ---

    _cameOnTableThisPhase(inst) {
        // AS3 State.as:4131 — the previous port (just `role === SELLABLE`) returned true
        // for an opponent's freshly-bought unit on your turn, making it bypass the _order
        // state comparison and lose the id tie-break, so e.g. a chill/snipe targeting one
        // of several similar units hit the wrong instId (Bc6rc-HwTZO: two Iceblade Golems
        // froze the wrong Protoplasm). Sellable only counts on the owner's own action turn;
        // otherwise the creatorId fields (reset at turn boundary) gate it.
        return (inst.owner === this.turn && this.phase === C.PHASE_ACTION && inst.role === C.ROLE_SELLABLE)
            || inst.creatorIdFromBuyOrAbility >= 0
            || inst.creatorIdFromBeginTurn >= 0;
    }

    _canBlockAtStartOfPhase(inst) {
        // AS3 State.as:4136 — this is NOT "can this card ever block"; it is "is this inst
        // currently blocking" (phase-dependent). The previous port
        // (card.defaultBlocking && ct===0 && delay===0 && !dead) was a wrong rewrite that
        // returned true for tapped/assigned default-blockers, flipping the charge tie-break
        // in _order() and selecting the wrong one of several identical units for
        // snipe/defend/undefend/sac/sell — desyncing the surviving instId on replay
        // (e.g. JbIWN-lD5mz: sniped the lower-charge Deadeye instead of the higher one).
        if (this.phase === C.PHASE_DEFENSE || this.phase === C.PHASE_CONFIRM) {
            return inst.blocking;
        }
        return inst.blocking || inst.disruptDamage > 0;
    }

    _order(inst1, inst2, saccing) {
        if (!this._cameOnTableThisPhase(inst1) && !this._cameOnTableThisPhase(inst2)) {
            if (saccing) {
                if (!inst1.blocking && inst2.blocking) return -1;
                if (inst1.blocking && !inst2.blocking) return 1;
            } else if (inst1.owner === this.turn && this.phase === C.PHASE_ACTION) {
                if (inst1.constructionTime > inst2.constructionTime) return -1;
                if (inst1.constructionTime < inst2.constructionTime) return 1;
                if (inst1.delayAfterSwoosh > inst2.delayAfterSwoosh) return -1;
                if (inst1.delayAfterSwoosh < inst2.delayAfterSwoosh) return 1;
                if (inst1.enoughHPToAssignAfterSwoosh && !inst2.enoughHPToAssignAfterSwoosh) return 1;
                if (!inst1.enoughHPToAssignAfterSwoosh && inst2.enoughHPToAssignAfterSwoosh) return -1;
                if (inst1.enoughChargeToAssignAfterSwoosh && !inst2.enoughChargeToAssignAfterSwoosh) return 1;
                if (!inst1.enoughChargeToAssignAfterSwoosh && inst2.enoughChargeToAssignAfterSwoosh) return -1;
                if (inst1.card.defaultBlocking && !inst1.card.assignedBlocking) {
                    if (inst1.convertedLifespan > inst2.convertedLifespan) return 1;
                    if (inst1.convertedLifespan < inst2.convertedLifespan) return -1;
                } else {
                    if (inst1.convertedLifespan > inst2.convertedLifespan) return -1;
                    if (inst1.convertedLifespan < inst2.convertedLifespan) return 1;
                }
                if (inst1.card.healthUsed === 0) {
                    if (inst1.hpAfterSwoosh > inst2.hpAfterSwoosh) return -1;
                    if (inst1.hpAfterSwoosh < inst2.hpAfterSwoosh) return 1;
                } else {
                    if (inst1.hpAfterSwoosh > inst2.hpAfterSwoosh) return 1;
                    if (inst1.hpAfterSwoosh < inst2.hpAfterSwoosh) return -1;
                }
                if (inst1.chargeAfterSwoosh > inst2.chargeAfterSwoosh) return 1;
                if (inst1.chargeAfterSwoosh < inst2.chargeAfterSwoosh) return -1;
            } else {
                if (inst1.constructionTime > inst2.constructionTime) return -1;
                if (inst1.constructionTime < inst2.constructionTime) return 1;
                if (inst1.convertedDelay > inst2.convertedDelay) return -1;
                if (inst1.convertedDelay < inst2.convertedDelay) return 1;
                if (this._canBlockAtStartOfPhase(inst1) && !this._canBlockAtStartOfPhase(inst2)) return 1;
                if (!this._canBlockAtStartOfPhase(inst1) && this._canBlockAtStartOfPhase(inst2)) return -1;
                if (this._canBlockAtStartOfPhase(inst1)) {
                    if (inst1.convertedLifespan > inst2.convertedLifespan) return -1;
                    if (inst1.convertedLifespan < inst2.convertedLifespan) return 1;
                    if (inst1.damageItCanTake + inst1.damage > inst2.damageItCanTake + inst2.damage) return 1;
                    if (inst1.damageItCanTake + inst1.damage < inst2.damageItCanTake + inst2.damage) return -1;
                    if (inst1.charge > inst2.charge) return -1;
                    if (inst1.charge < inst2.charge) return 1;
                } else {
                    if (inst1.convertedLifespan > inst2.convertedLifespan) return 1;
                    if (inst1.convertedLifespan < inst2.convertedLifespan) return -1;
                    if (inst1.damageItCanTake + inst1.damage > inst2.damageItCanTake + inst2.damage) return -1;
                    if (inst1.damageItCanTake + inst1.damage < inst2.damageItCanTake + inst2.damage) return 1;
                    if (inst1.charge > inst2.charge) return 1;
                    if (inst1.charge < inst2.charge) return -1;
                }
            }
        }
        return inst2.instId - inst1.instId;
    }

    _compareInstNether(inst1, inst2) {
        const score = (inst) => {
            if (inst.role === C.ROLE_ASSIGNED) return 200;
            if (inst.delay > 0) return 100;
            return 50 - inst.disruptDamage;
        };
        const s1 = score(inst1);
        const s2 = score(inst2);
        if (s1 === s2) return inst2.instId - inst1.instId;
        return s2 - s1;
    }

    // --- Serialization (State.as:4390-4434) ---

    toString(timeRemainingMS) {
        if (timeRemainingMS === undefined) timeRemainingMS = -1;
        const toy = {};
        toy.table = [];
        this.table.forEach((inst) => {
            toy.table.push(inst.toObject());
        });
        toy.nextInstId = this.nextInstId;
        toy.cards = new Array(this.cards.length);
        toy.whiteTotalSupply = new Array(this.cards.length);
        toy.blackTotalSupply = new Array(this.cards.length);
        toy.whiteSupplySpent = new Array(this.cards.length);
        toy.blackSupplySpent = new Array(this.cards.length);
        for (let i = 0; i < this.cards.length; i++) {
            toy.cards[i] = this.cards[i].cardName;
            toy.whiteTotalSupply[i] = this.whiteSupply[i];
            toy.blackTotalSupply[i] = this.blackSupply[i];
            toy.whiteSupplySpent[i] = this.whiteBought[i];
            toy.blackSupplySpent[i] = this.blackBought[i];
        }
        toy.whiteMana = this.whiteMana.toString();
        toy.blackMana = this.blackMana.toString();
        toy.numTurns = this.numTurns;
        toy.turn = this.turn;
        switch (this.phase) {
            case C.PHASE_DEFENSE: toy.phase = 'defense'; break;
            case C.PHASE_ACTION: toy.phase = 'action'; break;
            case C.PHASE_CONFIRM: toy.phase = 'confirm'; break;
        }
        toy.glassBroken = this.glassBroken;
        toy.result = this.result;
        toy.timeRemainingMS = timeRemainingMS;
        return JSON.stringify(toy);
    }

    clone() {
        return new State(null, null, null, null, 0, 0, this);
    }
}

// Static PRNG instance matching AS3 State.rnd (seed 100)
State.rnd = new Rndm(100);

// Static method — deep clone 2D createIds arrays (Controller.js calls State.cloneCreateIds)
State.cloneCreateIds = cloneCreateIds;

// Export stagnation constants for external use
State.NUM_LEVELS_OF_DRAW_VARIABLES = NUM_LEVELS_OF_DRAW_VARIABLES;
State.CUTOFFS_FOR_DRAW = CUTOFFS_FOR_DRAW;

module.exports = State;
