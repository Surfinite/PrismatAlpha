// tools/card_id_map.js
// Loads cardLibrary.jso and builds cardId mapping
//
// cardId rules:
//   - lowercase snake_case derived from UIName (display name)
//   - spaces → underscores, lowercase, strip non-alphanumeric except underscore
//   - e.g., "Tarsier" → "tarsier", "Tesla Tower" → "tarsier" (UIName is "Tarsier")

const fs = require('fs');
const path = require('path');

function toCardId(displayName) {
    return displayName
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, '')
        .replace(/\s+/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '');
}

function buildCardIdMap(cardLibraryPath) {
    const raw = fs.readFileSync(cardLibraryPath, 'utf-8');
    const library = JSON.parse(raw);
    const map = {};

    for (const [internalName, cardDef] of Object.entries(library)) {
        if (typeof cardDef !== 'object') continue;
        // Base set units (Drone, Engineer, etc.) have no UIName —
        // the key IS the display name. Randomizer units have UIName
        // (e.g., "Tesla Tower" key → UIName "Tarsier").
        const displayName = cardDef.UIName || internalName;
        const cardId = toCardId(displayName);
        map[internalName] = {
            cardId,
            displayName,
            internalName
        };
    }
    return map;
}

// CLI: node tools/card_id_map.js [--json]
if (require.main === module) {
    const libPath = path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso');
    const map = buildCardIdMap(libPath);
    if (process.argv.includes('--json')) {
        console.log(JSON.stringify(map, null, 2));
    } else {
        console.log('Mapped ' + Object.keys(map).length + ' cards');
        // Check for duplicate cardIds
        const ids = Object.values(map).map(v => v.cardId);
        const dupes = ids.filter((v, i) => ids.indexOf(v) !== i);
        if (dupes.length > 0) {
            console.log('WARNING: Duplicate cardIds:', [...new Set(dupes)]);
        } else {
            console.log('No duplicate cardIds');
        }
        // Print examples
        const examples = ['Drone', 'Tesla Tower', 'Vivid Drone', 'Antima Comet'];
        for (const name of examples) {
            if (map[name]) {
                console.log('  ' + name + ' → cardId: "' + map[name].cardId + '", display: "' + map[name].displayName + '"');
            }
        }
    }
}

module.exports = { buildCardIdMap, toCardId };
