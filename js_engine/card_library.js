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
 * set to the DISPLAY name (UIName). MCDSAI's Card.as uses obj.name as
 * cardName for matching clicks and game state. The internal name is
 * preserved as `internalName` for reverse lookups.
 */

const CARD_LIBRARY_PATH = path.resolve(__dirname, '../bin/asset/config/cardLibrary.jso');
const VALID_UNITS_PATH = path.resolve(__dirname, '../bin/asset/config/valid_units.json');

/** Supply per rarity (AS3 convention) */
const SUPPLY_BY_RARITY = {
    legendary: 1,
    rare: 4,
    normal: 10,
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
    const internalToUIName = new Map();

    // Build name lookups
    for (const [internalName, card] of library) {
        uiNameToInternal.set(card.UIName, internalName);
        internalToUIName.set(internalName, card.UIName);
    }

    // Track which cards are in the active game set
    const activeSet = new Set();
    // Base set is always active
    for (const [, card] of library) {
        if (card.baseSet) activeSet.add(card.UIName);
    }
    // Add the specified random units
    for (const uiName of unitNames) {
        if (!uiNameToInternal.has(uiName)) {
            throw new Error(`Unknown unit display name: "${uiName}". Check cardLibrary.jso UIName mappings.`);
        }
        activeSet.add(uiName);
    }

    // Snapshot before needs resolution — cards added only by needs get supply=0
    // (present for script cross-references but not buyable)
    const drawnSet = new Set(activeSet);

    // Resolve 'needs' dependencies — cards like Pixie and House (Husk) are tokens
    // created by other cards' scripts. They must be active when their parent is.
    let changed = true;
    while (changed) {
        changed = false;
        for (const uiName of activeSet) {
            const intName = uiNameToInternal.get(uiName);
            if (!intName) continue;
            const card = library.get(intName);
            if (!card || !card.needs) continue;
            for (const neededInternal of card.needs) {
                const neededUI = internalToUIName.get(neededInternal) || neededInternal;
                if (!activeSet.has(neededUI)) {
                    activeSet.add(neededUI);
                    changed = true;
                }
            }
        }
    }

    // Include cards from the library in the mergedDeck.
    // Only include valid units (from valid_units.json) — cardLibrary.jso contains
    // deprecated/renamed units (e.g., "Forcefield2") that the C++ engine can't
    // resolve, causing "None" entries in the GUI supply panel.
    // MCDSAI uses buildInitDeck() separately with its own targeted card set.
    const validUnits = loadValidUnits();
    const validSet = validUnits
        ? new Set([...validUnits.baseSet, ...validUnits.randomUnits])
        : null;

    for (const [internalName, card] of library) {
        if (card.rarity === 'unbuyable') {
            continue;
        }
        // Skip cards whose display name isn't a valid game unit
        // (e.g., "Forcefield2", "Blasto", "Corracks" are deprecated)
        if (validSet && !validSet.has(card.UIName)) {
            continue;
        }
        const entry = buildDeckEntry(card, internalToUIName);
        if (!activeSet.has(card.UIName)) {
            entry._inactive = true;
        } else if (!drawnSet.has(card.UIName)) {
            // Card was added by needs resolution, not drawn randomly.
            // Must be in deck for script cross-references (create, sac)
            // but should not be buyable (supply = 0).
            entry._needsOnly = true;
        }
        deck.push(entry);
    }

    return deck;
}

/**
 * Get the active card set names from a mergedDeck (excludes inactive cards).
 */
function getActiveCardNames(mergedDeck) {
    return mergedDeck
        .filter(c => !c._inactive && !c._needsOnly && !c.baseSet)
        .map(c => c.name);
}

/**
 * Build a single mergedDeck entry from a card library entry.
 * Strips description/fullDescription fields (matching simpleMergedDeck logic
 * from GameInitializationInfo.as lines 109-121).
 *
 * Translates all internal card name references to display names throughout
 * the entry, matching the real game's server-side mergedDeck format.
 * Fields like create, resonate, buySac, needs use internal names in
 * cardLibrary.jso but display names in the wire protocol.
 *
 * @param {Object} card - Card library entry
 * @param {Map} [nameMap] - Internal name → display name mapping
 */
function buildDeckEntry(card, nameMap) {
    const entry = {};
    for (const key of Object.keys(card)) {
        if (key === 'description' || key.indexOf('fullDescription') !== -1) {
            continue;
        }
        entry[key] = nameMap ? translateNames(card[key], nameMap) : card[key];
    }
    // MCDSAI's Card.as uses obj.name as cardName for click matching.
    // Must be the display name (UIName), not the internal name.
    entry.name = card.UIName;
    // Preserve UIName after translateNames — when a display name collides
    // with an internal name (e.g., "Forcefield" is both Blood Barrier's UIName
    // and the deprecated Forcefield card's internal name), translateNames
    // incorrectly converts it to "Forcefield2".
    entry.UIName = card.UIName;
    return entry;
}

/**
 * Recursively translate internal card names to display names in a value.
 * Handles strings, arrays, and nested objects.
 */
function translateNames(value, nameMap) {
    if (typeof value === 'string') {
        return nameMap.has(value) ? nameMap.get(value) : value;
    }
    if (Array.isArray(value)) {
        return value.map(v => translateNames(v, nameMap));
    }
    if (value !== null && typeof value === 'object') {
        const result = {};
        for (const key of Object.keys(value)) {
            result[key] = translateNames(value[key], nameMap);
        }
        return result;
    }
    return value;
}

/**
 * Load the valid units list from valid_units.json.
 * Returns { baseSet: string[], randomUnits: string[] } or null if file missing.
 */
function loadValidUnits() {
    try {
        const raw = fs.readFileSync(VALID_UNITS_PATH, 'utf-8');
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

/**
 * Get all available advanced (non-base-set) unit display names.
 * Filters against valid_units.json if available (116 canonical units).
 */
function getAdvancedUnitNames(library) {
    const validUnits = loadValidUnits();
    if (validUnits && validUnits.randomUnits) {
        // Use the authoritative 105 random units from valid_units.json
        // Verify each exists in the library
        const uiNames = new Set();
        for (const [, card] of library) {
            uiNames.add(card.UIName);
        }
        return validUnits.randomUnits.filter(name => uiNames.has(name));
    }
    // Fallback: all non-base, non-unbuyable from cardLibrary
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

/**
 * Build an init deck for MCDSAI that includes all cards the AI might reference.
 *
 * MCDSAI's AI params reference ~91 card names (opening books, strategies).
 * Card scripts (create, needs, resonate, buySac) reference ~27 more.
 * If any referenced name isn't registered via the mergedDeck, MCDSAI's
 * CardType::getCardType() asserts and aborts move computation.
 *
 * Sending ALL 158 non-unbuyable cards breaks MCDSAI (0 AI players loaded).
 * This function builds a targeted deck: active cards + only the cards
 * referenced by AI params and card scripts (~100 total). Achieves ~95%
 * success rate across random sets (vs ~33% with active-only 19-card deck).
 *
 * @param {Object[]} activeDeck - Active game cards (base + 8 random, ~19 entries)
 * @param {Map} library - Full card library from loadCardLibrary()
 * @param {string} fullParamsStr - Full AI parameters JSON string
 * @param {string} shortParamsStr - Short AI parameters JSON string
 * @returns {Object[]} Init deck suitable for MCDSAI initializeAI
 */
function buildInitDeck(activeDeck, library, fullParamsStr, shortParamsStr) {
    // Build name lookup tables
    const allDisplayNames = new Set();
    const displayToCard = new Map();
    const internalToDisplay = new Map();
    for (const [intName, card] of library) {
        allDisplayNames.add(card.UIName);
        displayToCard.set(card.UIName, card);
        internalToDisplay.set(intName, card.UIName);
    }

    // Collect all card names MCDSAI might reference
    const required = new Set();

    // 1. Scan AI params for card names
    function scanForCardNames(obj) {
        if (typeof obj === 'string') {
            if (allDisplayNames.has(obj)) required.add(obj);
            return;
        }
        if (Array.isArray(obj)) { obj.forEach(scanForCardNames); return; }
        if (obj && typeof obj === 'object') {
            for (const key of Object.keys(obj)) scanForCardNames(obj[key]);
        }
    }
    scanForCardNames(JSON.parse(fullParamsStr));
    scanForCardNames(JSON.parse(shortParamsStr));

    // 2. Scan card scripts for referenced card names (create, needs, resonate, buySac)
    // These use internal names in cardLibrary.jso — translate to display names
    for (const [, card] of library) {
        if (card.rarity === 'unbuyable') continue;
        if (card.needs) {
            for (const n of card.needs) {
                var dn = internalToDisplay.get(n);
                if (dn) required.add(dn);
            }
        }
        var scriptFields = ['buyScript', 'abilityScript', 'beginOwnTurnScript', 'deathScript'];
        for (var si = 0; si < scriptFields.length; si++) {
            var script = card[scriptFields[si]];
            if (script && script.create) {
                for (var ci = 0; ci < script.create.length; ci++) {
                    dn = internalToDisplay.get(script.create[ci][0]);
                    if (dn) required.add(dn);
                }
            }
        }
        if (card.resonate) {
            dn = internalToDisplay.get(card.resonate);
            if (dn) required.add(dn);
        }
        if (card.buySac) {
            for (var bi = 0; bi < card.buySac.length; bi++) {
                dn = internalToDisplay.get(card.buySac[bi][0]);
                if (dn) required.add(dn);
            }
        }
    }

    // Build init deck: active cards + required cards (with _inactive flag)
    var included = new Set(activeDeck.map(function(c) { return c.name; }));
    var deck = activeDeck.slice(); // shallow copy

    for (var displayName of required) {
        if (included.has(displayName)) continue;
        var card = displayToCard.get(displayName);
        if (!card || card.rarity === 'unbuyable') continue;
        var entry = buildDeckEntry(card, internalToDisplay);
        entry._inactive = true;
        deck.push(entry);
    }

    return deck;
}

module.exports = {
    loadCardLibrary,
    loadValidUnits,
    buildMergedDeck,
    buildInitDeck,
    buildDeckEntry,
    getAdvancedUnitNames,
    getActiveCardNames,
    randomSet,
    getSupply,
    SUPPLY_BY_RARITY,
    CARD_LIBRARY_PATH,
    VALID_UNITS_PATH
};
