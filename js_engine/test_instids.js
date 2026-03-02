'use strict';
const { loadCardLibrary, buildMergedDeck, buildInitDeck, randomSet } = require('./card_library');
const { loadFullParams, loadShortParams, selectParams } = require('./ai_params');
const { stateToSuggestJSON } = require('./suggest_adapter');
const Analyzer = require('./Analyzer');
const C = require('./C');

const library = loadCardLibrary();
const unitNames = ['Tarsier','Rhino','Wall','Steelsplitter','Forcefield','Gauss Cannon','Conduit','Blastforge'];
const mergedDeck = buildMergedDeck(unitNames, library);
const activeDeck = mergedDeck.filter(c => !c._inactive);

const fullParams = loadFullParams();
const shortParams = loadShortParams();
const initDeck = buildInitDeck(activeDeck, library, fullParams, shortParams);

const base = [], randomizer = [];
for (const card of activeDeck) {
    const supply = card.supply !== undefined ? card.supply : 20;
    if (card.baseSet) base.push([card.name, supply]);
    else randomizer.push([card.name, supply]);
}
const gameInitInfo = {
    laneInfo: [{ initResources: ['0','0'], base: [base,base], randomizer: [randomizer,randomizer],
        initCards: [[[6,'Drone'],[2,'Engineer']], [[7,'Drone'],[2,'Engineer']]] }],
    mergedDeck: activeDeck, scriptInfo: { whiteStarts: true }, objectiveInfo: null, commandInfo: null
};
const analyzer = new Analyzer(gameInitInfo, -1, -1, null);
analyzer.loaderInit();

// P0 turn - just end
analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
// P1 turn - just end
analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
analyzer.recordClick(false, false, C.CLICK_SPACE, -1);

// Now P0's turn 2
const suggestJSON = stateToSuggestJSON(analyzer.gameState, mergedDeck);
const table = suggestJSON.CurrentInfo.gameState.table;

console.log('=== Table entries with instId ===');
for (const entry of table) {
    console.log(JSON.stringify({name: entry.cardName, instId: entry.instId, owner: entry.owner, role: entry.role}));
}

const fs = require('fs');
const tmpFile = 'c:/libraries/PrismataAI/js_engine/test_suggest_state.json';
fs.writeFileSync(tmpFile, JSON.stringify(suggestJSON));
console.log('\nWrote to ' + tmpFile + ', ' + table.length + ' table entries');

// Now run C++ suggest on this and show what clicks it returns
console.log('\n=== Running C++ suggest ===');
