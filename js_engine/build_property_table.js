'use strict';

/**
 * build_property_table.js — Build static property table for DeepSets architecture.
 *
 * Reads cardLibrary.jso and training/data/unit_index.json, constructs Card objects
 * for all 116 canonical units, and extracts 13 static properties per unit.
 *
 * Output: training/property_table.json
 *
 * Usage:
 *   node js_engine/build_property_table.js
 */

const fs = require('fs');
const path = require('path');
const Card = require('./Card');
const C = require('./C');
const { loadCardLibrary } = require('./card_library');

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const UNIT_INDEX_PATH = path.resolve(__dirname, '../training/data/unit_index.json');
const OUTPUT_PATH = path.resolve(__dirname, '../training/property_table.json');

// ---------------------------------------------------------------------------
// Property definitions
// ---------------------------------------------------------------------------
const PROPERTY_NAMES = [
    'buy_cost_gold',
    'buy_cost_green',
    'buy_cost_blue',
    'buy_cost_red',
    'buy_cost_energy',
    'base_health',
    'fragile',
    'default_blocking',
    'base_build_time',
    'base_lifespan',
    'base_attack',
    'has_ability',
    'max_stamina',
];

/**
 * Extract 13 static properties from a Card object.
 * @param {Card} card
 * @returns {number[]} Array of 13 numeric property values
 */
function extractProperties(card) {
    const buyCost = card.buyCost;

    const buyCostGold   = buyCost.pool[C.MANA_P] || 0;
    const buyCostGreen  = buyCost.pool[C.MANA_G] || 0;
    const buyCostBlue   = buyCost.pool[C.MANA_B] || 0;
    const buyCostRed    = buyCost.pool[C.MANA_R] || 0;
    const buyCostEnergy = buyCost.pool[C.MANA_H] || 0;

    // Spells have startingHealth=0 (they don't set it), default to 0
    const baseHealth = card.cardType === C.CARDTYPE_UNIT ? (card.startingHealth || 0) : 0;

    const fragile        = card.fragile ? 1 : 0;
    const defaultBlocking = card.defaultBlocking ? 1 : 0;

    const baseBuildTime = card.buildTime !== undefined ? card.buildTime : 1;

    // lifespan: -1 means permanent → 0. Spells also get lifespan -1 → 0.
    const lifespan = card.lifespan;
    const baseLifespan = (lifespan === -1 || lifespan === undefined) ? 0 : lifespan;

    // attackPotential: -1 for resonate units (variable), treat as 0 for the table
    const ap = card.attackPotential;
    const baseAttack = ap >= 0 ? ap : 0;

    const hasAbility  = card.hasAbility ? 1 : 0;
    const maxStamina  = card.startingCharge || 0;

    return [
        buyCostGold,
        buyCostGreen,
        buyCostBlue,
        buyCostRed,
        buyCostEnergy,
        baseHealth,
        fragile,
        defaultBlocking,
        baseBuildTime,
        baseLifespan,
        baseAttack,
        hasAbility,
        maxStamina,
    ];
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
    // Load unit_index.json (display name → index)
    const unitIndexData = JSON.parse(fs.readFileSync(UNIT_INDEX_PATH, 'utf-8'));
    const unitIndexMap = unitIndexData.units; // { "Engineer": 0, "Drone": 1, ... }
    const numUnits = unitIndexData.count;

    console.log(`Loaded unit_index.json: ${numUnits} units`);

    // Load cardLibrary.jso (internal name → card def with .name and .UIName set)
    const library = loadCardLibrary();
    console.log(`Loaded cardLibrary.jso: ${library.size} entries`);

    // Build a lookup: display name → Card object
    const displayNameToCard = new Map();
    let cardId = 0;
    for (const [, cardDef] of library) {
        const card = new Card(cardDef, cardId++);
        displayNameToCard.set(card.UIName, card);
    }
    console.log(`Constructed ${displayNameToCard.size} Card objects`);

    // Build the units output object, ordered by index
    const units = {};
    const missing = [];

    for (const [displayName, index] of Object.entries(unitIndexMap)) {
        const card = displayNameToCard.get(displayName);
        if (!card) {
            missing.push(displayName);
            continue;
        }
        const properties = extractProperties(card);
        units[displayName] = { index, properties };
    }

    if (missing.length > 0) {
        console.error(`WARNING: ${missing.length} units from unit_index.json not found in cardLibrary.jso:`);
        for (const name of missing) {
            console.error(`  - ${name}`);
        }
    }

    const numFound = Object.keys(units).length;
    console.log(`Extracted properties for ${numFound}/${numUnits} units`);

    // Build output JSON
    const output = {
        schema_version: 'v2',
        num_units: numFound,
        num_properties: PROPERTY_NAMES.length,
        property_names: PROPERTY_NAMES,
        units,
    };

    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2), 'utf-8');
    console.log(`Written: ${OUTPUT_PATH}`);

    // ---------------------------------------------------------------------------
    // Spot-checks
    // ---------------------------------------------------------------------------
    console.log('\n--- Spot checks ---');
    const checks = [
        // Engineer: costs 2 gold, health=1, defaultBlocking, buildTime=1, no ability
        { name: 'Engineer',     expected: { buy_cost_gold: 2, base_health: 1, default_blocking: 1, base_build_time: 1, has_ability: 0 } },
        // Drone: costs 3 gold + 1 energy (buyCost="3H"), health=1, defaultBlocking, has ability (sac for gold)
        { name: 'Drone',        expected: { buy_cost_gold: 3, buy_cost_energy: 1, base_health: 1, default_blocking: 1, base_build_time: 1, has_ability: 1 } },
        // Tarsier (Tesla Tower): 4 gold + 1 red, health=1, buildTime=2, generates 1 attack/turn
        { name: 'Tarsier',      expected: { buy_cost_gold: 4, buy_cost_red: 1, base_health: 1, base_build_time: 2, base_attack: 1 } },
        // Zemora Voidbringer: buildTime=6, health=20, fragile
        { name: 'Zemora Voidbringer', expected: { base_build_time: 6, base_health: 20, fragile: 1 } },
        // Iso Kronus: buildTime=2, health=5, fragile, base_attack=2
        { name: 'Iso Kronus',   expected: { base_build_time: 2, base_health: 5, fragile: 1, base_attack: 2 } },
        // Wall: buildTime=0, health=3, blue cost, defaultBlocking
        { name: 'Wall',         expected: { buy_cost_gold: 5, buy_cost_blue: 1, base_health: 3, base_build_time: 0, default_blocking: 1 } },
        // Rhino (Elephant): stamina=2, red cost, defaultBlocking, has_ability
        { name: 'Rhino',        expected: { buy_cost_gold: 5, buy_cost_red: 1, base_health: 2, max_stamina: 2, default_blocking: 1, has_ability: 1 } },
    ];

    let allPassed = true;
    for (const check of checks) {
        const entry = units[check.name];
        if (!entry) {
            console.log(`  SKIP (not found): ${check.name}`);
            continue;
        }
        let pass = true;
        const errors = [];
        for (const [prop, expectedVal] of Object.entries(check.expected)) {
            const propIdx = PROPERTY_NAMES.indexOf(prop);
            if (propIdx === -1) {
                errors.push(`unknown property ${prop}`);
                pass = false;
                continue;
            }
            const actual = entry.properties[propIdx];
            if (actual !== expectedVal) {
                errors.push(`${prop}: expected ${expectedVal}, got ${actual}`);
                pass = false;
            }
        }
        if (pass) {
            console.log(`  PASS: ${check.name}`);
        } else {
            console.log(`  FAIL: ${check.name} — ${errors.join(', ')}`);
            allPassed = false;
        }
    }

    if (missing.length > 0 || !allPassed) {
        process.exit(1);
    }
    console.log('\nAll checks passed.');
}

main();
