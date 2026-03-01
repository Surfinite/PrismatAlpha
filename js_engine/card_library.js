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

    // Include ALL cards from the library in the mergedDeck.
    // MCDSAI's AI parameters reference cards by name (opening books, strategies).
    // If a referenced card isn't registered, CardType::getCardType() asserts and
    // aborts the entire move computation. By including all cards (with supply=0
    // for non-game cards), MCDSAI can look up any card without failing.
    // Base set and active random cards get normal supply.
    for (const [internalName, card] of library) {
        // Skip unbuyable cards in the JS game engine mergedDeck.
        // Unbuyable tokens (Behemoth, Transwall, Fusion) are created by
        // card scripts at runtime, not bought from supply.
        // Note: buildInitDeck() separately includes them for MCDSAI.
        if (card.rarity === 'unbuyable') {
            continue;
        }
        const entry = buildDeckEntry(card, internalToUIName);
        if (!activeSet.has(card.UIName)) {
            // Not in this game's card set — include but mark inactive (0 supply).
            // MCDSAI AI params reference card names (opening books, strategies)
            // and getCardType() asserts if a name isn't registered.
            entry._inactive = true;
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
        .filter(c => !c._inactive && !c.baseSet)
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
        // UIName is already a display name — don't translate it.
        // "Forcefield" (Blood Barrier's UIName) also happens to be an internal
        // name of a different card, so translateNames would corrupt it.
        if (key === 'UIName') {
            entry[key] = card[key];
            continue;
        }
        entry[key] = nameMap ? translateNames(card[key], nameMap) : card[key];
    }
    // MCDSAI's Card.as uses obj.name as cardName for click matching.
    // Must be the display name (UIName), not the internal name.
    entry.name = card.UIName;
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
 * The 105 advanced units in the real game (from Prismata wiki).
 * cardLibrary.jso contains 42 extra unreleased/beta units that were never
 * playable in the live game. Including them causes MCDSAI failures and
 * produces game states that never occur in real play.
 */
const REAL_ADVANCED_UNITS = new Set([
    'Aegis','Amporilla','Antima Comet','Apollo','Arka Sodara','Arms Race',
    'Asteri Cannon','Auric Impulse','Auride Core','Barrier','Blood Pact',
    'Blood Phage','Bloodrager','Bombarder','Borehole Patroller','Cauterizer',
    'Centrifuge','Centurion','Chieftain','Chrono Filter','Cluster Bolt',
    'Colossus','Corpus','Cryo Ray','Cynestra','Deadeye Operative',
    'Defense Grid','Doomed Drone','Doomed Mech','Doomed Wall','Drake',
    'Ebb Turbine','Electrovore','Endotherm Kit','Energy Matrix',
    'Feral Warden','Ferritin Sac','Fission Turret','Flame Animus',
    'Frost Brooder','Frostbite','Galvani Drone',
    'Gauss Charge','Gauss Fabricator','Gaussite Symbiote','Grenade Mech',
    'Grimbotch','Hannibull','Hellhound','Husk','Iceblade Golem','Immolite',
    'Infusion Grid','Innervi Field','Iso Kronus','Kinetic Driver',
    'Lancetooth','Lucina Spinos','Mahar Rectifier','Manticore','Mega Drone',
    'Militia','Mobile Animus','Nitrocybe','Nivo Charge','Odin',
    'Omega Splitter','Ossified Drone','Oxide Mixer','Perforator',
    'Photonic Fibroid','Pixie','Plasmafier','Plexo Cell','Polywall',
    'Protoplasm','Redeemer','Resophore','Rhino','Savior','Scorchilla',
    'Sentinel','Shadowfang','Shiver Yeti','Shredder','Steelforge',
    'Steelsplitter','Synthesizer','Tantalum Ray','Tarsier','Tatsu Nullifier',
    'Tesla Coil','The Wincer','Thermite Core','Thorium Dynamo','Thunderhead',
    'Tia Thurnax','Trinity Drone','Tyranno Smorcus','Urban Sentry',
    'Vai Mauronax','Valkyrion','Venge Cannon','Vivid Drone','Wild Drone',
    'Xaetron','Xeno Guardian','Zemora Voidbringer'
]);

/**
 * Get all available advanced (non-base-set) unit display names.
 * Filters to only real game units (excludes 42 unreleased/beta cards in cardLibrary.jso).
 */
function getAdvancedUnitNames(library) {
    const names = [];
    for (const [, card] of library) {
        if (!card.baseSet && card.rarity !== 'unbuyable' && REAL_ADVANCED_UNITS.has(card.UIName)) {
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

    // Build init deck: active cards + required cards (with _inactive flag).
    // Includes unbuyable tokens (Behemoth, Transwall, Fusion) when referenced
    // by active cards' needs/scripts — MCDSAI's CardType::getCardType() asserts
    // if these aren't registered.
    var included = new Set(activeDeck.map(function(c) { return c.name; }));
    var deck = activeDeck.slice(); // shallow copy

    for (var displayName of required) {
        if (included.has(displayName)) continue;
        var card = displayToCard.get(displayName);
        if (!card) continue;
        var entry = buildDeckEntry(card, internalToDisplay);
        entry._inactive = true;
        deck.push(entry);
    }

    return deck;
}

module.exports = {
    loadCardLibrary,
    buildMergedDeck,
    buildInitDeck,
    buildDeckEntry,
    getAdvancedUnitNames,
    getActiveCardNames,
    randomSet,
    getSupply,
    SUPPLY_BY_RARITY,
    REAL_ADVANCED_UNITS,
    CARD_LIBRARY_PATH
};
