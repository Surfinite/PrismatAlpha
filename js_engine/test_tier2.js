'use strict';

/**
 * test_tier2.js — Unit tests for Tier 2 core engine classes.
 *
 * Tests:
 * 1. Card.js construction from cardLibrary.jso
 * 2. Card computed properties
 * 3. Inst.js construction and computed properties
 * 4. Inst serialization round-trip
 * 5. StateHelper.js construction
 * 6. EndTurnObject.js construction
 *
 * Run: node js_engine/test_tier2.js
 */

const C = require('./C');
const Card = require('./Card');
const Inst = require('./Inst');
const Mana = require('./Mana');
const StateHelper = require('./StateHelper');
const { loadCardLibrary } = require('./card_library');

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
        console.log(`  PASS: ${message}`);
    } else {
        failed++;
        console.error(`  FAIL: ${message}`);
    }
}

function main() {
    console.log('=== Tier 2 Core Engine Tests ===\n');

    // Load card library for testing
    const library = loadCardLibrary();

    // Test 1: Card.js construction from cardLibrary
    console.log('Test 1: Card.js construction');

    // Build Cards array from cardLibrary (mimic State constructor)
    const cards = [];
    const cardNameToCardId = {};
    let cardId = 0;
    for (const [internalName, entry] of library) {
        const card = new Card(entry, cardId);
        cards.push(card);
        cardNameToCardId[internalName] = cardId;
        cardId++;
    }

    assert(cards.length === 161, `Loaded ${cards.length} cards (expected 161)`);

    // Find Drone by internal name
    const droneId = cardNameToCardId['Drone'];
    assert(droneId !== undefined, 'Found Drone in card list');
    const drone = cards[droneId];
    assert(drone.cardName === 'Drone', 'Drone cardName');
    assert(drone.UIName === 'Drone', 'Drone UIName (no override)');
    assert(drone.cardType === C.CARDTYPE_UNIT, 'Drone is a unit');
    assert(drone.defaultBlocking === true, 'Drone is default blocking');
    assert(drone.startingHealth === 1, 'Drone health = 1');
    assert(drone.buildTime === 1, 'Drone buildTime = 1');
    assert(drone.baseSet === true, 'Drone is base set');
    assert(drone.abilityScript !== null, 'Drone has abilityScript');
    assert(drone.abilityScript.receive.money === 1, 'Drone produces 1 gold (on click)');
    assert(drone.beginOwnTurnScript === null, 'Drone has no beginOwnTurnScript');
    assert(drone.rarity === C.RARITY_TRINKET, 'Drone rarity = trinket');

    // Find Tarsier (internal name: Tesla Tower)
    const tarsierId = cardNameToCardId['Tesla Tower'];
    assert(tarsierId !== undefined, 'Found Tesla Tower (Tarsier)');
    const tarsier = cards[tarsierId];
    assert(tarsier.cardName === 'Tesla Tower', 'Internal name is Tesla Tower');
    assert(tarsier.UIName === 'Tarsier', 'UIName is Tarsier');
    assert(tarsier.defaultBlocking === false, 'Tarsier is not blocking');
    assert(tarsier.beginOwnTurnScript !== null, 'Tarsier has beginOwnTurnScript');
    assert(tarsier.beginOwnTurnScript.receive.attack === 1, 'Tarsier produces 1 attack');

    // Find Engineer
    const engId = cardNameToCardId['Engineer'];
    const engineer = cards[engId];
    assert(engineer.defaultBlocking === true, 'Engineer is default blocking');
    assert(engineer.hasAbility === false, 'Engineer has no ability');
    assert(engineer.attackPotential === 0, 'Engineer attack potential = 0');

    // Test 2: Card computed properties
    console.log('\nTest 2: Card computed properties');

    // Wall
    const wallId = cardNameToCardId['Wall'];
    const wall = cards[wallId];
    assert(wall.startingHealth === 3, 'Wall health = 3');
    assert(wall.defaultBlocking === true, 'Wall is blocking');
    assert(wall.hasAbility === false, 'Wall has no ability');

    // Find a unit with an ability (e.g., Steelsplitter = Treant)
    const steelId = cardNameToCardId['Treant'];
    if (steelId !== undefined) {
        const steel = cards[steelId];
        assert(steel.UIName === 'Steelsplitter', 'Treant UIName = Steelsplitter');
        assert(steel.hasAbility === true, 'Steelsplitter has ability');
        assert(steel.abilityScript !== null, 'Steelsplitter has abilityScript');
    }

    // Find a fragile unit (e.g., Forcefield = Blood Barrier)
    const ffId = cardNameToCardId['Blood Barrier'];
    if (ffId !== undefined) {
        const ff = cards[ffId];
        assert(ff.UIName === 'Forcefield', 'Blood Barrier UIName = Forcefield');
        assert(ff.fragile === true, 'Forcefield is fragile');
        assert(ff.healthMax === 2, 'Forcefield healthMax = 2 (toughness)');
    }

    // Find a chill unit (e.g., Frostbite)
    const frostId = cardNameToCardId['Frostbite'];
    if (frostId !== undefined) {
        const frost = cards[frostId];
        assert(frost.targetAction === C.TARGETACTION_DISRUPT, 'Frostbite has disrupt');
        assert(frost.targetAmount > 0, 'Frostbite targetAmount > 0');
        assert(frost.targetHas === true, 'Frostbite targetHas');
    }

    // Find a snipe unit
    const sharkId = cardNameToCardId['Deadeye Operative'];
    if (sharkId !== undefined) {
        const shark = cards[sharkId];
        assert(shark.targetAction === C.TARGETACTION_SNIPE, 'Deadeye has snipe');
        assert(shark.condition !== null, 'Deadeye has condition');
    }

    // autoClicked property
    assert(drone.autoClicked === true, 'Drone is autoClicked (free abilityScript, no cost)');

    // Test 3: Inst.js construction
    console.log('\nTest 3: Inst.js construction');

    // Create a bought Drone
    const droneInst = new Inst(drone, 0, true, drone.buildTime, true, 100, 0);
    assert(droneInst.instId === 100, 'Inst instId');
    assert(droneInst.card === drone, 'Inst card reference');
    assert(droneInst.owner === 0, 'Inst owner');
    assert(droneInst.role === C.ROLE_SELLABLE, 'Bought inst is sellable');
    assert(droneInst.blocking === false, 'Under construction — not blocking');
    assert(droneInst.deadness === C.DEADNESS_ALIVE, 'Alive');
    assert(droneInst.health === 1, 'Health = 1');
    assert(droneInst.constructionTime === 1, 'constructionTime = 1 (invulnerable)');
    assert(droneInst.delay === 0, 'delay = 0 (invulnerable)');

    // Create a non-bought inst (e.g., created by ability)
    const tarsierInst = new Inst(tarsier, 1, false, 0, false, 101, 0);
    assert(tarsierInst.role === C.ROLE_INERT, 'Non-bought inst is inert');
    assert(tarsierInst.blocking === false, 'Tarsier not blocking by default');
    assert(tarsierInst.constructionTime === 0, 'Non-invulnerable constructionTime = 0');

    // Test 4: Inst computed properties
    console.log('\nTest 4: Inst computed properties');

    assert(droneInst.cardName === 'Drone', 'cardName getter');
    assert(droneInst.dead === false, 'Not dead');
    assert(droneInst.isPartiallyDamaged === false, 'Not partially damaged');
    assert(droneInst.damageItCanTake === 1, 'damageItCanTake = 1 (non-fragile)');
    assert(droneInst.damageReqdToInjure === 1, 'damageReqdToInjure = 1');
    assert(droneInst.absorb === 0, 'absorb = health - 1 = 0');

    // Test with a high-health unit
    const wallInst = new Inst(wall, 0, true, wall.buildTime, true, 102, 0);
    assert(wallInst.health === 3, 'Wall health = 3');
    assert(wallInst.damageItCanTake === 3, 'Wall damageItCanTake = 3');
    assert(wallInst.absorb === 2, 'Wall absorb = 2');

    // Damage a non-fragile unit
    wallInst.damage = 2;
    assert(wallInst.damageItCanTake === 1, 'After 2 damage: damageItCanTake = 1');
    assert(wallInst.isPartiallyDamaged === true, 'isPartiallyDamaged after damage');

    // Test convertedLifespan
    assert(droneInst.convertedLifespan === 32767, 'Permanent unit lifespan = 32767');
    const tempInst = new Inst(drone, 0, false, 0, false, 103, 0);
    tempInst.lifespan = 3;
    tempInst.delay = 1;
    assert(tempInst.convertedLifespan === 4, 'Lifespan 3 + delay 1 = 4');

    // Test 5: Inst serialization round-trip
    console.log('\nTest 5: Inst serialization round-trip');

    const obj = droneInst.toObject();
    assert(obj.cardName === 'Drone', 'toObject cardName');
    assert(obj.instId === 100, 'toObject instId');
    assert(obj.role === 'sellable', 'toObject role (string)');
    assert(obj.dead === false, 'toObject includes dead');

    // Clone via toObject
    const cloned = droneInst.clone();
    assert(cloned.instId === droneInst.instId, 'Clone instId matches');
    assert(cloned.card === droneInst.card, 'Clone card same reference');
    assert(cloned.role === droneInst.role, 'Clone role matches');
    assert(cloned.health === droneInst.health, 'Clone health matches');
    cloned.health = 99;
    assert(droneInst.health === 1, 'Clone is independent');

    // toString
    const str = droneInst.toString();
    assert(typeof str === 'string', 'toString returns string');
    const parsed = JSON.parse(str);
    assert(parsed.cardName === 'Drone', 'toString parses correctly');

    // compareWithJSON
    assert(droneInst.compareWithJSON({cardName: 'Drone'}), 'compareWithJSON match');
    assert(!droneInst.compareWithJSON({cardName: 'Wall'}), 'compareWithJSON mismatch');
    assert(droneInst.compareWithJSON({}), 'compareWithJSON empty obj matches all');

    // Test 6: StateHelper construction
    console.log('\nTest 6: StateHelper construction');

    const helper = new StateHelper();
    assert(helper.ownDefense === 0, 'Initial ownDefense = 0');
    assert(helper.oppDefense === 0, 'Initial oppDefense = 0');
    assert(helper.allOppUnitsDoomed === true, 'Initial allOppUnitsDoomed = true');
    assert(helper.partiallyDamagedInst === null, 'Initial partiallyDamagedInst = null');
    assert(helper.damageReqdToInjureBreach === 32768, 'Initial damageReqdToInjureBreach = 32768');
    assert(Array.isArray(helper.ownDefenders), 'ownDefenders is array');
    assert(helper.ownDefenders.length === 0, 'ownDefenders empty');

    // Test 7: All cards parse without error
    console.log('\nTest 7: All 161 cards parse as Card objects');
    let parseErrors = 0;
    for (let i = 0; i < cards.length; i++) {
        const c = cards[i];
        if (!c.cardName || !c.UIName) {
            parseErrors++;
            console.error(`    Card ${i} missing cardName or UIName`);
        }
        if (c.buyCost === undefined || c.buyCost === null) {
            parseErrors++;
            console.error(`    Card ${i} (${c.cardName}) missing buyCost`);
        }
    }
    assert(parseErrors === 0, `All ${cards.length} cards parsed without errors`);

    // Summary
    console.log('\n=== Results ===');
    console.log(`Passed: ${passed}, Failed: ${failed}`);
    if (failed > 0) process.exit(1);
}

main();
