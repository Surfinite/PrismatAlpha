'use strict';
/**
 * build_viewer_bundle.js — Generate prismata-engine.js for the ladder site.
 *
 * Bundles the JS game engine, card metadata, UI assets (base64), and canvas
 * rendering code into a single JS file that exposes window.PrismataViewer.
 *
 * Card art is loaded at runtime from URLs (the ladder site already has them).
 *
 * Usage:
 *   node js_engine/build_viewer_bundle.js [output.js]
 *   Default output: ../<ladder>/<ladder>-site/public/js/prismata-engine.js
 */
const fs = require('fs');
const path = require('path');

const JS_DIR = __dirname;
const BIN_DIR = path.join(JS_DIR, '..', 'bin');
const CARD_BG_DIR = path.join(BIN_DIR, 'asset', 'images', 'cardbg');
const ICON_STATUS_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'status');
const ICON_RESOURCE_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'resource');
const CARD_LIBRARY_PATH = path.join(BIN_DIR, 'asset', 'config', 'cardLibrary.jso');
const DEFAULT_OUTPUT = path.join(JS_DIR, '..', '..', '<ladder>', '<ladder>-site', 'public', 'js', 'prismata-engine.js');

const ENGINE_MODULES = [
    'C.js', 'Mana.js', 'Rndm.js', 'SacDescription.js', 'CreateDescription.js',
    'Script.js', 'Card.js', 'Inst.js', 'AS3Dictionary.js', 'Click.js',
    'ClickResult.js', 'EndTurnObject.js', 'Order.js', 'StateHelper.js',
    'State.js', 'Controller.js', 'Analyzer.js', 'replay_exporter.js'
];

function readImageBase64(filePath) {
    if (!fs.existsSync(filePath)) return null;
    return 'data:image/png;base64,' + fs.readFileSync(filePath).toString('base64');
}

function buildModuleBundle() {
    const factories = [];
    for (const modFile of ENGINE_MODULES) {
        let source = fs.readFileSync(path.join(JS_DIR, modFile), 'utf-8');
        source = source.replace(/^'use strict';\s*/m, '');
        source = source.replace(/require\('\.\/([^']+)'\)/g, '__require("$1")');
        source = source.replace(/require\('(fs|path|zlib|https?|child_process|crypto|worker_threads)'\)/g, '({})');
        const modName = modFile.replace(/\.js$/, '');
        factories.push(`__modules["${modName}"] = (function() {\nvar module = { exports: {} };\nvar exports = module.exports;\n${source}\nreturn module.exports;\n})();`);
    }
    return factories.join('\n\n');
}

function buildCardMetadata(cardLibrary) {
    const byUIName = {};
    for (const [internalName, card] of Object.entries(cardLibrary)) {
        const uiName = card.UIName || internalName;
        let autoAttack = 0, abilityAttack = 0;
        if (card.beginOwnTurnScript && typeof card.beginOwnTurnScript.receive === 'string')
            for (const ch of card.beginOwnTurnScript.receive) { if (ch === 'A') autoAttack++; }
        if (card.abilityScript && typeof card.abilityScript.receive === 'string')
            for (const ch of card.abilityScript.receive) { if (ch === 'A') abilityAttack++; }
        byUIName[uiName] = {
            attack: autoAttack + abilityAttack, autoAttack, abilityAttack,
            toughness: card.toughness || 0,
            hasAbility: !!(card.abilityScript || card.targetAction),
            hasTargetAbility: !!card.targetAction,
            isFrontline: !!card.undefendable, canBlock: !!card.defaultBlocking,
            isFragile: !!card.fragile, defaultBlocking: !!card.defaultBlocking,
            buyCost: card.buyCost || '', buildTime: card.buildTime || 1,
            lifespan: card.lifespan || -1, charge: card.startingCharge || 0,
            baseSet: !!card.baseSet, rarity: card.rarity || 'normal'
        };
    }
    return byUIName;
}

function collectSmallAssets() {
    const assets = {};
    const bgFiles = {
        'bg_default': 'Card_Blue.png', 'bg_default_red': 'Card_Red.png',
        'bg_assigned': 'Card_Grey.png', 'bg_construction': 'Card_Orange.png',
        'bg_dead': 'Card_Dead.png', 'bg_border_green': 'Card_Border_Green.png',
        'bg_chilled': 'Card_Blue_Frost.png'
    };
    for (const [key, file] of Object.entries(bgFiles)) {
        const data = readImageBase64(path.join(CARD_BG_DIR, file));
        if (data) assets[key] = data;
    }
    const statusFiles = {
        'icon_attack': 'icon_attack.png', 'icon_defend': 'icon_defend.png',
        'icon_construct': 'status_construct.png', 'icon_doom': 'status_doom.png',
        'icon_delay': 'status_delay.png', 'icon_tap': 'status_tap.png',
        'icon_hp': 'status_hp.png', 'icon_charge0': 'status_charge0.png',
        'icon_charge1': 'status_charge1.png', 'icon_charge2': 'status_charge2.png',
        'icon_charge3': 'status_charge3.png', 'icon_undefendable': 'status_undefendable.png',
        'icon_shield_blue': 'highlight_blueshield.png', 'icon_shield_gold': 'highlight_goldshield.png',
        'icon_shield_white': 'highlight_whiteshield.png', 'icon_clock': 'clock.png'
    };
    for (const [key, file] of Object.entries(statusFiles)) {
        const data = readImageBase64(path.join(ICON_STATUS_DIR, file));
        if (data) assets[key] = data;
    }
    const resourceFiles = {
        'res_gold': 'P.png', 'res_blue': 'B.png', 'res_green': 'G.png',
        'res_red': 'C.png', 'res_energy': 'H.png', 'res_attack': 'A.png'
    };
    for (const [key, file] of Object.entries(resourceFiles)) {
        const data = readImageBase64(path.join(ICON_RESOURCE_DIR, file));
        if (data) assets[key] = data;
    }
    console.error(`Small assets: ${Object.keys(assets).length} (bg + icons)`);
    return assets;
}

function buildBundle(moduleBundle, cardMeta) {
    return `'use strict';
// prismata-engine.js — Generated by build_viewer_bundle.js
// Do not edit manually. Re-run: node js_engine/build_viewer_bundle.js

var __modules = {};
function __require(name) {
    name = name.replace(/\\.js$/, '');
    if (__modules[name]) return __modules[name];
    throw new Error('Module not found: ' + name);
}

${moduleBundle}

var CARD_META = ${JSON.stringify(cardMeta)};

window.PrismataViewer = (function() {
    var C = __require('C');
    var Analyzer = __require('Analyzer');
    var replay_exporter = __require('replay_exporter');
    var stateToCppJSON = replay_exporter.stateToCppJSON;

    var REPLAY = null;
    var liveAnalyzer = null;
    var stateIndex = 0;
    var totalStates = 0;
    var onStateChange = null;

    // ── Init ──
    function init(options) {
        onStateChange = (options && options.onStateChange) || null;
    }

    // ── S3 Fetch ──
    var S3_BASE = 'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/';

    function loadFromCode(code) {
        var url = S3_BASE + encodeURIComponent(code) + '.json.gz';
        return fetch(url).then(function(resp) {
            if (!resp.ok) throw new Error('Replay not found (HTTP ' + resp.status + ')');
            return resp.arrayBuffer();
        }).then(function(buf) {
            return processArrayBuffer(buf);
        });
    }

    async function processArrayBuffer(arrayBuf) {
        var jsonStr;
        var header = new Uint8Array(arrayBuf.slice(0, 2));
        if (header[0] === 0x1f && header[1] === 0x8b) {
            var ds = new DecompressionStream('gzip');
            var writer = ds.writable.getWriter();
            var reader = ds.readable.getReader();
            writer.write(new Uint8Array(arrayBuf));
            writer.close();
            var chunks = [];
            while (true) {
                var result = await reader.read();
                if (result.done) break;
                chunks.push(result.value);
            }
            var totalLen = 0;
            for (var i = 0; i < chunks.length; i++) totalLen += chunks[i].length;
            var combined = new Uint8Array(totalLen);
            var offset = 0;
            for (var j = 0; j < chunks.length; j++) {
                combined.set(chunks[j], offset);
                offset += chunks[j].length;
            }
            jsonStr = new TextDecoder().decode(combined);
        } else {
            jsonStr = new TextDecoder().decode(arrayBuf);
        }

        var replayData = JSON.parse(jsonStr);

        if (replayData.states && replayData.states.length > 0) {
            loadMatchupReplay(replayData);
        } else if (replayData.deckInfo && replayData.commandInfo) {
            processS3Replay(replayData);
        } else {
            throw new Error('Unrecognized replay format');
        }

        notify();
        return getInfo();
    }

    function loadMatchupReplay(data) {
        REPLAY = {
            p0: data.p0 || 'Player 0', p1: data.p1 || 'Player 1',
            winner: data.winner,
            winnerName: data.winnerName || (data.winner === 0 ? data.p0 : data.winner === 1 ? data.p1 : 'Draw'),
            turns: data.turns || 0, cardSet: data.cardSet || [],
            states: data.states, actions: data.actions || [],
            turnBoundaries: data.turnBoundaries || []
        };
        stateIndex = 0;
        totalStates = REPLAY.states.length;
    }

    function processS3Replay(replay) {
        var laneInfo = [{
            initResources: replay.initInfo.initResources,
            base: replay.deckInfo.base,
            randomizer: replay.deckInfo.randomizer,
            initCards: replay.initInfo.initCards
        }];
        var gameInitInfo = {
            laneInfo: laneInfo,
            mergedDeck: replay.deckInfo.mergedDeck,
            scriptInfo: { whiteStarts: true },
            objectiveInfo: null, commandInfo: null
        };

        var analyzer = new Analyzer(gameInitInfo, -1, -1, null);
        analyzer.loaderInit();

        var states = [stateToCppJSON(analyzer.gameState)];
        var actions = ['Start'];
        var turnBoundaries = [0];
        var lastTurn = analyzer.gameState.numTurns;
        var cmdList = replay.commandInfo.commandList;

        var p0 = 'Player 0', p1 = 'Player 1';
        if (replay.playerInfo) {
            if (replay.playerInfo[0]) p0 = replay.playerInfo[0].displayName || replay.playerInfo[0].name || 'Player 0';
            if (replay.playerInfo[1]) p1 = replay.playerInfo[1].displayName || replay.playerInfo[1].name || 'Player 1';
        }

        for (var i = 0; i < cmdList.length; i++) {
            var cmd = cmdList[i];
            if (String(cmd._type).indexOf(String(C.CLICK_REPLAY_EMOTE)) === 0) continue;
            if (analyzer.gameState.finished) break;
            var prePhase = analyzer.gameState.phase;
            try {
                var clickResult = analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
                if (clickResult.canClick) {
                    states.push(stateToCppJSON(analyzer.gameState));
                    actions.push(describeClick(cmd, analyzer.gameState, prePhase));
                    if (analyzer.gameState.numTurns !== lastTurn) {
                        turnBoundaries.push(states.length - 1);
                        lastTurn = analyzer.gameState.numTurns;
                    }
                }
            } catch (err) { /* skip failed clicks */ }
        }

        var winner = -1, winnerName = 'Draw';
        if (replay.result !== undefined && replay.result !== null) {
            if (replay.result === C.COLOR_WHITE || replay.result === 0) { winner = 0; winnerName = p0; }
            else if (replay.result === C.COLOR_BLACK || replay.result === 1) { winner = 1; winnerName = p1; }
        } else if (analyzer.gameState.finished) {
            var r = analyzer.gameState.result;
            if (r === C.COLOR_WHITE) { winner = 0; winnerName = p0; }
            else if (r === C.COLOR_BLACK) { winner = 1; winnerName = p1; }
        }

        var cardSet = [];
        if (replay.deckInfo && replay.deckInfo.randomizer) {
            for (var ri = 0; ri < replay.deckInfo.randomizer.length; ri++) {
                var rz = replay.deckInfo.randomizer[ri];
                if (rz) for (var rj = 0; rj < rz.length; rj++) {
                    if (rz[rj].UIName) cardSet.push(rz[rj].UIName);
                    else if (rz[rj].name) cardSet.push(rz[rj].name);
                }
            }
        }

        var totalTurns = replay.commandInfo.clicksPerTurn ? replay.commandInfo.clicksPerTurn.length : 0;

        REPLAY = {
            p0: p0, p1: p1, winner: winner, winnerName: winnerName,
            turns: totalTurns, cardSet: cardSet,
            states: states, actions: actions, turnBoundaries: turnBoundaries
        };
        stateIndex = 0;
        totalStates = states.length;
    }

    // ── Live Spectating ──
    function initLive(gameInitInfo) {
        // Live BeginGame has data inside laneInfo[0] directly,
        // not in separate deckInfo/initInfo wrappers like S3 replays
        var lane = {};
        if (gameInitInfo.laneInfo && gameInitInfo.laneInfo[0]) {
            lane = gameInitInfo.laneInfo[0];
        }
        var deckInfo = gameInitInfo.deckInfo || lane;
        var initInfo = gameInitInfo.initInfo || lane;
        var laneInfo = [{
            initResources: initInfo.initResources,
            base: deckInfo.base,
            randomizer: deckInfo.randomizer,
            initCards: initInfo.initCards
        }];
        var analyzerInit = {
            laneInfo: laneInfo,
            mergedDeck: deckInfo.mergedDeck || lane.mergedDeck || [],
            scriptInfo: { whiteStarts: true },
            objectiveInfo: null, commandInfo: null
        };

        liveAnalyzer = new Analyzer(analyzerInit, -1, -1, null);
        liveAnalyzer.loaderInit();

        var p0 = 'Player 0', p1 = 'Player 1';
        if (gameInitInfo.players) { p0 = gameInitInfo.players[0] || p0; p1 = gameInitInfo.players[1] || p1; }

        REPLAY = {
            p0: p0, p1: p1, winner: -1, winnerName: '',
            turns: 0, cardSet: [],
            states: [stateToCppJSON(liveAnalyzer.gameState)],
            actions: ['Start'], turnBoundaries: [0]
        };
        stateIndex = 0; totalStates = 1;
        notify();
        return getInfo();
    }

    function processClick(clickType, clickId, clickParams) {
        if (!liveAnalyzer) return { accepted: false, info: getInfo() };
        var prePhase = liveAnalyzer.gameState.phase;
        try {
            var result = liveAnalyzer.recordClick(false, false, clickType, clickId, clickParams);
            if (result.canClick) {
                var newState = stateToCppJSON(liveAnalyzer.gameState);
                REPLAY.states.push(newState);
                REPLAY.actions.push(describeClick({_type: clickType, _id: clickId}, liveAnalyzer.gameState, prePhase));
                if (liveAnalyzer.gameState.numTurns !== REPLAY.turns) {
                    REPLAY.turnBoundaries.push(REPLAY.states.length - 1);
                    REPLAY.turns = liveAnalyzer.gameState.numTurns;
                }
                totalStates = REPLAY.states.length;
                stateIndex = totalStates - 1;
                notify();
                return { accepted: true, info: getInfo() };
            }
            return { accepted: false, info: getInfo() };
        } catch (e) {
            return { accepted: false, error: e.message, info: getInfo() };
        }
    }

    function describeClick(click, state, prePhase) {
        var type = click._type, id = click._id;
        switch (type) {
            case C.CLICK_CARD: case C.CLICK_CARD_SHIFT:
                if (state.cards && id >= 0 && id < state.cards.length) return 'Buy ' + state.cards[id].UIName;
                return 'Buy card ' + id;
            case C.CLICK_INST: case C.CLICK_INST_SHIFT: {
                var inst = state.table.get(id);
                if (inst) {
                    var name = inst.card.UIName;
                    if (state.phase === C.PHASE_DEFENSE) return 'Block with ' + name;
                    if (inst.owner !== state.turn) return name;
                    return 'Use ' + name;
                }
                return 'Click unit ' + id;
            }
            case C.CLICK_SPACE: {
                var p = prePhase || state.phase;
                if (p === C.PHASE_ACTION) return 'End Action';
                if (p === C.PHASE_DEFENSE) return 'End Defense';
                if (p === C.PHASE_CONFIRM) return 'Confirm';
                return 'End Phase';
            }
            default: return 'Click ' + type;
        }
    }

    // ── State access (React handles all rendering) ──
    function getGameState() { return REPLAY ? REPLAY.states[stateIndex] : null; }
    function getCardMeta() { return CARD_META; }
    function getReplay() { return REPLAY; }
    
    // ── Navigation ──
    function getCurrentTurnIndex() {
        if (!REPLAY || !REPLAY.turnBoundaries || REPLAY.turnBoundaries.length === 0) return 0;
        var turnIdx = 0;
        for (var i = 1; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] <= stateIndex) turnIdx = i; else break;
        }
        return turnIdx;
    }

    function notify() { if (onStateChange) onStateChange(getInfo()); }

    function nextAction() { if (stateIndex < totalStates - 1) { stateIndex++; notify(); } }
    function prevAction() { if (stateIndex > 0) { stateIndex--; notify(); } }
    function nextTurn() {
        if (!REPLAY || !REPLAY.turnBoundaries) return;
        for (var i = 0; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] > stateIndex) { stateIndex = REPLAY.turnBoundaries[i]; notify(); return; }
        }
    }
    function prevTurn() {
        if (!REPLAY || !REPLAY.turnBoundaries) return;
        var ct = getCurrentTurnIndex();
        if (ct > 0) stateIndex = REPLAY.turnBoundaries[ct - 1]; else stateIndex = 0;
        notify();
    }
    function goToStart() { stateIndex = 0; notify(); }
    function goToEnd() { stateIndex = totalStates - 1; notify(); }
    function setStateIndex(idx) { stateIndex = Math.max(0, Math.min(idx, totalStates - 1)); notify(); }

    function getInfo() {
        if (!REPLAY) return { loaded: false, stateIndex: 0, totalStates: 0, turn: 0, totalTurns: 0, phase: '', action: '', p0: '', p1: '', winnerName: '', winner: -1 };
        var state = REPLAY.states[stateIndex];
        var turnIdx = getCurrentTurnIndex();
        var phase = state.phase || '';
        var action = (REPLAY.actions && stateIndex < REPLAY.actions.length) ? REPLAY.actions[stateIndex] : '';
        return {
            loaded: true, stateIndex: stateIndex, totalStates: totalStates,
            turn: turnIdx + 1, totalTurns: REPLAY.turns, phase: phase, action: action,
            p0: REPLAY.p0, p1: REPLAY.p1, winnerName: REPLAY.winnerName, winner: REPLAY.winner
        };
    }

    return {
        init: init, loadFromCode: loadFromCode,
        initLive: initLive, processClick: processClick,
        nextAction: nextAction, prevAction: prevAction,
        nextTurn: nextTurn, prevTurn: prevTurn,
        goToStart: goToStart, goToEnd: goToEnd,
        setStateIndex: setStateIndex, getInfo: getInfo,
        getGameState: getGameState, getCardMeta: getCardMeta, getReplay: getReplay
    };
})();
`;
}

function main() {
    const args = process.argv.slice(2);
    const outputPath = args[0] || DEFAULT_OUTPUT;

    // Ensure output directory exists
    const outputDir = path.dirname(outputPath);
    if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

    console.error('Building viewer bundle...');
    const moduleBundle = buildModuleBundle();
    const cardLibrary = JSON.parse(fs.readFileSync(CARD_LIBRARY_PATH, 'utf-8'));
    const cardMeta = buildCardMetadata(cardLibrary);

    const bundle = buildBundle(moduleBundle, cardMeta);
    fs.writeFileSync(outputPath, bundle, 'utf-8');

    const sizeMB = (Buffer.byteLength(bundle) / 1024 / 1024).toFixed(1);
    console.error(`Written: ${outputPath} (${sizeMB} MB)`);
}

main();
