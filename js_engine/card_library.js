'use strict';

const fs = require('fs');
const path = require('path');

/**
 * card_library.js — Parses cardLibrary.jso and builds mergedDeck arrays
 * for MCDSAI initialization.
 *
 * The cardLibrary.jso uses internal names as keys (e.g., "Tesla Tower")
 * with UIName for display names (e.g., "Tarsier"). When UIName is absent,
 * the internal name IS the display name (e.g., "Drone", "Engineer").
 *
 * The mergedDeck sent to MCDSAI contains card objects with a `name` property
 * set to the internal name and all other cardLibrary properties preserved.
 * MCDSAI references cards by their UIName (display name) in click responses.
 */

const CARD_LIBRARY_PATH = path.resolve(__dirname, '../bin/asset/config/cardLibrary.jso');

/** Supply per rarity (AS3 convention) */
const SUPPLY_BY_RARITY = {
    legendary: 1,
    rare: 4,
    normal: 20,
    trinket: 20
};

/**
 * Load and parse cardLibrary.jso.
 * Returns a Map of internalName → card definition object.
 */
function loadCardLibrary(filePath) {
    filePath = filePath || CARD_LIBRARY_PATH;
    const raw = fs.readFileSync(filePath, 'utf-8');
    const library = JSON.parse(raw);
    const cards = new Map();

    for (const internalName of Object.keys(library)) {
        const entry = library[internalName];
        const card = Object.assign({}, entry);
        card.name = internalName;
        // UIName defaults to internal name if not specified
        if (!card.UIName) {
            card.UIName = internalName;
        }
        cards.set(internalName, card);
    }

    return cards;
}

/**
 * Build a mergedDeck array for a specific set of cards.
 *
 * @param {string[]} unitNames - Array of display names (UINames) for the advanced set
 * @param {Map} library - Card library from loadCardLibrary()
 * @returns {Object[]} mergedDeck array suitable for MCDSAI init
 *
 * The mergedDeck includes:
 * - All base set cards (baseSet: 1)
 * - The specified advanced units
 * Each entry includes the `name` (internal name) property that Card.as expects.
 */
function buildMergedDeck(unitNames, library) {
    const deck = [];
    const uiNameToInternal = new Map();

    // Build reverse lookup: UIName → internal name
    for (const [internalName, card] of library) {
        uiNameToInternal.set(card.UIName, internalName);
    }

    // Add all base set cards first
    for (const [internalName, card] of library) {
        if (card.baseSet) {
            deck.push(buildDeckEntry(card));
        }
    }

    // Add specified advanced units
    for (const uiName of unitNames) {
        const internalName = uiNameToInternal.get(uiName);
        if (!internalName) {
            throw new Error(`Unknown unit display name: "${uiName}". Check cardLibrary.jso UIName mappings.`);
        }
        const card = library.get(internalName);
        if (card.baseSet) {
            continue; // Already included
        }
        deck.push(buildDeckEntry(card));
    }

    return deck;
}

/**
 * Build a single mergedDeck entry from a card library entry.
 * Strips description/fullDescription fields (matching simpleMergedDeck logic
 * from GameInitializationInfo.as lines 109-121).
 */
function buildDeckEntry(card) {
    const entry = {};
    for (const key of Object.keys(card)) {
        if (key === 'description' || key.indexOf('fullDescription') !== -1) {
            continue;
        }
        entry[key] = card[key];
    }
    return entry;
}

/**
 * Get all available advanced (non-base-set) unit display names.
 */
function getAdvancedUnitNames(library) {
    const names = [];
    for (const [, card] of library) {
        if (!card.baseSet && card.rarity !== 'unbuyable') {
            names.push(card.UIName);
        }
    }
    return names;
}

/**
 * Pick N random advanced units for a game set.
 * Standard Prismata uses 8 random advanced units + base set.
 */
function randomSet(library, count) {
    count = count || 8;
    const available = getAdvancedUnitNames(library);
    // Fisher-Yates shuffle
    for (let i = available.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const tmp = available[i];
        available[i] = available[j];
        available[j] = tmp;
    }
    return available.slice(0, count);
}

/**
 * Get the supply count for a card based on its rarity.
 */
function getSupply(card) {
    if (card.rarity === 'unbuyable') {
        return 0;
    }
    return SUPPLY_BY_RARITY[card.rarity] || 20;
}

module.exports = {
    loadCardLibrary,
    buildMergedDeck,
    buildDeckEntry,
    getAdvancedUnitNames,
    randomSet,
    getSupply,
    SUPPLY_BY_RARITY,
    CARD_LIBRARY_PATH
};
