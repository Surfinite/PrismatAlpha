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
const ICON_MOUSEOVER_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'mouseover');
const ICON_HD_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'extracted_hd');
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
    // Build internal→display name map (buySac references internal names)
    const internalToDisplay = {};
    for (const [internalName, card] of Object.entries(cardLibrary)) {
        internalToDisplay[internalName] = card.UIName || internalName;
    }
    const byUIName = {};
    for (const [internalName, card] of Object.entries(cardLibrary)) {
        const uiName = card.UIName || internalName;
        let autoAttack = 0, abilityAttack = 0, autoGold = 0, abilityGold = 0;
        // Parse receive field — can be string ("5G", "A", "1") or number (3)
        // Format: leading digits = gold, A=attack, G/B/C/H = resources
        function parseReceive(receive) {
            if (receive == null) return { gold: 0, attack: 0 };
            const s = String(receive);
            const goldMatch = s.match(/^(\d+)/);
            const gold = goldMatch ? parseInt(goldMatch[1], 10) : 0;
            const attack = (s.match(/A/g) || []).length;
            return { gold, attack };
        }
        if (card.beginOwnTurnScript) {
            const r = parseReceive(card.beginOwnTurnScript.receive);
            autoAttack = r.attack; autoGold = r.gold;
        }
        if (card.abilityScript) {
            const r = parseReceive(card.abilityScript.receive);
            abilityAttack = r.attack; abilityGold = r.gold;
        }
        // Is ability gold "free"? (no cost, no sac, no selfsac) — counts toward lower bound
        const abilityGoldFree = abilityGold > 0 && !card.abilityCost && (!card.abilitySac || card.abilitySac.length === 0) &&
            !(card.abilityScript && card.abilityScript.selfsac);

        const isSpell = !!card.spell;
        const hasTargetAbility = !!card.targetAction;
        const hasAbility = !!(card.abilityScript || card.targetAction);
        const defaultBlocking = isSpell ? false : !!card.defaultBlocking;
        const assignedBlocking = isSpell ? false : !!card.assignedBlocking;
        const undefendable = isSpell ? false : !!card.undefendable;
        const hasResonate = !!card.resonate;
        // attackPotential: -1 if resonate, else sum of autoAttack + abilityAttack
        const attackPotential = hasResonate ? -1 : (autoAttack + abilityAttack);
        const attacks = attackPotential > 0 || hasTargetAbility;

        // Position priority chain — mirrors Card.js lines 269-324
        let position = 23; // default: BACK_LEFT
        if (card.hasOwnProperty('position'))          { position = card.position; }
        else if (uiName === 'Conduit')                { position = 20; } // BACK_FAR_LEFT
        else if (uiName === 'Blastforge')             { position = 21; } // BACK_FAR_LEFT_ONE
        else if (uiName === 'Animus')                 { position = 22; } // BACK_FAR_LEFT_TWO
        else if (uiName === 'Drone')                  { position = 10; } // MIDDLE_FAR_LEFT
        else if (uiName === 'Engineer')               { position = 0;  } // FRONT_FAR_LEFT
        else if (isSpell)                             { position = 29; } // BACK_FAR_RIGHT
        else if (undefendable && attacks)             { position = 7;  } // FRONT_RIGHT_ONE
        else if (undefendable)                        { position = 6;  } // FRONT_RIGHT
        else if (hasAbility && defaultBlocking && assignedBlocking && attacks)  { position = 4;  } // FRONT_LEFT_ONE
        else if (hasAbility && defaultBlocking && assignedBlocking)             { position = 3;  } // FRONT_LEFT
        else if (hasAbility && defaultBlocking && !assignedBlocking && attacks) { position = 16; } // MIDDLE_RIGHT
        else if (hasAbility && defaultBlocking && !assignedBlocking)            { position = 11; } // MIDDLE_FAR_LEFT_ONE
        else if (hasAbility && !defaultBlocking && attacks)                     { position = 18; } // MIDDLE_FAR_RIGHT
        else if (hasAbility && !defaultBlocking)                                { position = 13; } // MIDDLE_LEFT
        else if (defaultBlocking && attacks)          { position = 2;  } // FRONT_FAR_LEFT_TWO
        else if (defaultBlocking)                     { position = 1;  } // FRONT_FAR_LEFT_ONE
        else if (attacks)                             { position = 26; } // BACK_RIGHT
        // else default 23 (BACK_LEFT)

        // Target ability info (chill/snipe)
        let targetAction = '';
        let targetAmount = 0;
        if (card.targetAction === 'disrupt') { targetAction = 'chill'; targetAmount = card.targetAmount || 0; }
        else if (card.targetAction === 'snipe') { targetAction = 'snipe'; targetAmount = card.targetAmount || 0; }

        // Map buySac internal names to display names
        const buySac = (card.buySac || []).map(entry => ({
            cardName: internalToDisplay[entry[0]] || entry[0],
            amount: entry.length > 1 ? (entry[1] | 0) : 1
        }));

        byUIName[uiName] = {
            attack: autoAttack + abilityAttack, autoAttack, abilityAttack, autoGold, abilityGold, abilityGoldFree,
            toughness: card.toughness || 0,
            hasAbility, hasTargetAbility, targetAction, targetAmount,
            isFrontline: undefendable, canBlock: defaultBlocking,
            isFragile: !!card.fragile, defaultBlocking, assignedBlocking,
            buyCost: card.buyCost || '', buildTime: Object.prototype.hasOwnProperty.call(card, 'buildTime') ? card.buildTime : 1,
            lifespan: card.lifespan || -1, charge: card.startingCharge || 0,
            baseSet: !!card.baseSet, rarity: card.rarity || 'normal',
            position, buySac
        };
    }
    return byUIName;
}

function collectSmallAssets() {
    const assets = {};
    const bgFiles = {
        'bg_dead':          'Card_Inver.png',      // BACK_DEAD (0) — inverted bg for dead units
        'bg_block':         'Card_Blue.png',       // BACK_BLOCK (1)
        'bg_busy':          'Card_Grey.png',       // BACK_BUSY (2)
        'bg_absorb':        'Card_Orange.png',     // BACK_ABSORB (3)
        'bg_chilled':       'Card_Blue_Frost.png', // BACK_BLOCK_FROST (4)
        'bg_bought':        'Card_Trans.png',      // BACK_BOUGHT (5)
        'bg_whitepink':     'Card_WhitePink.png',  // BACK_WHITEPINK (6)
        'bg_blockred':      'Card_Red.png',        // BACK_BLOCKRED (7)
        'bg_busyblue':      'Card_BlueGrey.png',   // BACK_BUSYBLUE (8) — default P0
        'bg_busyred':       'Card_RedGrey.png',    // BACK_BUSYRED (9) — default P1
        'bg_border_green':  'Card_Border_Green.png',
        'skull_death':      'Card_Dead.png',        // SkullEffect.as — skull overlay for dead units
        'icon_cage':        'highlight_cage2.png',  // COVER_ASSIGNED — cage overlay for assigned units
        'chill_snowflake':  'Card_Chilled.png',     // ChillSnowflake effect overlay
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
        'icon_shield_white': 'highlight_whiteshield.png', 'icon_shield_whiteb': 'highlight_whiteshieldB.png',
        'icon_shield_red': 'highlight_redshield.png', 'icon_clock': 'clock.png',
        'icon_damagebang': 'highlight_damagebang.png',   // COVER_BANG — damage burst overlay
        'icon_blackclock': 'highlight_blackclock.png',   // COVER_INVSPAWN — construction clock
        'icon_goldclock': 'highlight_goldclock.png',     // COVER_INVBOUGHT — just-bought clock
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
    // Mouseover icons (colored swords for attack display)
    const mouseoverFiles = {
        'sword_red': 'attack_big_red.png',
        'sword_blue': 'attack_big_blue.png',
    };
    for (const [key, file] of Object.entries(mouseoverFiles)) {
        const data = readImageBase64(path.join(ICON_MOUSEOVER_DIR, file));
        if (data) assets[key] = data;
    }
    // HD sprites extracted from SWF sprite sheet (108x108 shield/sword, 97x97 breach icons)
    const hdFiles = {
        'shield_big': 'shield_big.png',
        'shield_big_glow': 'shield_big_glow.png',  // red glow variant for breach threat
        'sword_big': 'sword_big.png',
        'sword_large': 'sword_large.png',           // 461x461 large sword for Big Sword HUD
        'interro': 'interro.png',                   // breach warning octagon "!"
        'interro2': 'interro2.png',                 // wipeout warning
        'tap_big': 'tap_big.png',                   // chill/tap icon
    };
    for (const [key, file] of Object.entries(hdFiles)) {
        const data = readImageBase64(path.join(ICON_HD_DIR, file));
        if (data) assets[key] = data;
    }
    console.error(`Small assets: ${Object.keys(assets).length} (bg + icons)`);
    return assets;
}

function buildBundle(moduleBundle, cardMeta, smallAssets, cardLibrary) {
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
var SMALL_ASSETS = ${JSON.stringify(smallAssets)};
var CARD_LIBRARY = ${JSON.stringify(cardLibrary)};

/**
 * buildRuntimeCardMeta(cardLibrary) — runtime mirror of the build-time buildCardMetadata().
 * Used by loadPuzzle() to rebuild card meta after cardUpdates are applied, so that
 * getCardMeta() returns accurate stats (e.g. buildTime) for modified cards.
 */
function buildRuntimeCardMeta(lib) {
    var internalToDisplay = {};
    for (var k in lib) {
        if (!lib.hasOwnProperty(k)) continue;
        internalToDisplay[k] = lib[k].UIName || k;
    }
    var byUIName = {};
    for (var internalName in lib) {
        if (!lib.hasOwnProperty(internalName)) continue;
        var card = lib[internalName];
        var uiName = card.UIName || internalName;
        var autoAttack = 0, abilityAttack = 0, autoGold = 0, abilityGold = 0;
        function parseReceive(receive) {
            if (receive == null) return { gold: 0, attack: 0 };
            var s = String(receive);
            var goldMatch = s.match(/^(\\d+)/);
            var gold = goldMatch ? parseInt(goldMatch[1], 10) : 0;
            var attack = (s.match(/A/g) || []).length;
            return { gold: gold, attack: attack };
        }
        if (card.beginOwnTurnScript) { var r1 = parseReceive(card.beginOwnTurnScript.receive); autoAttack = r1.attack; autoGold = r1.gold; }
        if (card.abilityScript) { var r2 = parseReceive(card.abilityScript.receive); abilityAttack = r2.attack; abilityGold = r2.gold; }
        var abilityGoldFree = abilityGold > 0 && !card.abilityCost && (!card.abilitySac || card.abilitySac.length === 0) &&
            !(card.abilityScript && card.abilityScript.selfsac);
        var isSpell = !!card.spell;
        var hasTargetAbility = !!card.targetAction;
        var hasAbility = !!(card.abilityScript || card.targetAction);
        var defaultBlocking = isSpell ? false : !!card.defaultBlocking;
        var assignedBlocking = isSpell ? false : !!card.assignedBlocking;
        var undefendable = isSpell ? false : !!card.undefendable;
        var hasResonate = !!card.resonate;
        var attackPotential = hasResonate ? -1 : (autoAttack + abilityAttack);
        var attacks = attackPotential > 0 || hasTargetAbility;
        var position = 23;
        if (card.hasOwnProperty('position'))     { position = card.position; }
        else if (uiName === 'Conduit')            { position = 20; }
        else if (uiName === 'Blastforge')         { position = 21; }
        else if (uiName === 'Animus')             { position = 22; }
        else if (uiName === 'Drone')              { position = 10; }
        else if (uiName === 'Engineer')           { position = 0; }
        else if (isSpell)                         { position = 29; }
        else if (undefendable && attacks)         { position = 7; }
        else if (undefendable)                    { position = 6; }
        else if (hasAbility && defaultBlocking && assignedBlocking && attacks)  { position = 4; }
        else if (hasAbility && defaultBlocking && assignedBlocking)             { position = 3; }
        else if (hasAbility && defaultBlocking && !assignedBlocking && attacks) { position = 16; }
        else if (hasAbility && defaultBlocking && !assignedBlocking)            { position = 11; }
        else if (hasAbility && !defaultBlocking && attacks)                     { position = 18; }
        else if (hasAbility && !defaultBlocking)                                { position = 13; }
        else if (defaultBlocking && attacks)      { position = 2; }
        else if (defaultBlocking)                 { position = 1; }
        else if (attacks)                         { position = 26; }
        var targetAction = '';
        var targetAmount = 0;
        if (card.targetAction === 'disrupt') { targetAction = 'chill'; targetAmount = card.targetAmount || 0; }
        else if (card.targetAction === 'snipe') { targetAction = 'snipe'; targetAmount = card.targetAmount || 0; }
        var buySac = [];
        if (card.buySac) {
            for (var bi = 0; bi < card.buySac.length; bi++) {
                var entry = card.buySac[bi];
                buySac.push({ cardName: internalToDisplay[entry[0]] || entry[0], amount: entry.length > 1 ? (entry[1] | 0) : 1 });
            }
        }
        byUIName[uiName] = {
            attack: autoAttack + abilityAttack, autoAttack: autoAttack, abilityAttack: abilityAttack,
            autoGold: autoGold, abilityGold: abilityGold, abilityGoldFree: abilityGoldFree,
            toughness: card.toughness || 0,
            hasAbility: hasAbility, hasTargetAbility: hasTargetAbility,
            targetAction: targetAction, targetAmount: targetAmount,
            isFrontline: undefendable, canBlock: defaultBlocking,
            isFragile: !!card.fragile, defaultBlocking: defaultBlocking, assignedBlocking: assignedBlocking,
            buyCost: card.buyCost || '', buildTime: card.hasOwnProperty('buildTime') ? card.buildTime : 1,
            lifespan: card.lifespan || -1, charge: card.startingCharge || 0,
            baseSet: !!card.baseSet, rarity: card.rarity || 'normal',
            position: position, buySac: buySac
        };
    }
    return byUIName;
}

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
    var PUZZLE_CARD_META = null; // Set by loadPuzzle when cardUpdates are present; null = use static CARD_META

    // ── Init ──
    function init(options) {
        onStateChange = (options && options.onStateChange) || null;
    }

    // ── S3 Fetch ──
    var S3_BASE = 'https://saved-games-alpha.s3.amazonaws.com/';

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

        // Track per-state timestamps from commandTimes (actual click times in seconds)
        var commandTimes = replay.commandInfo.commandTimes || [];
        var stateTimestampMs = [commandTimes.length > 0 ? commandTimes[0] * 1000 : 0]; // state 0

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
                    // Map this state to its command timestamp
                    stateTimestampMs.push(i < commandTimes.length ? commandTimes[i] * 1000 : stateTimestampMs[stateTimestampMs.length - 1]);
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

        // Build per-turn timing from stateTimestampMs and turnBoundaries
        var turnStartMs = [];
        var turnEndMs = [];
        for (var ti = 0; ti < turnBoundaries.length; ti++) {
            var tStart = stateTimestampMs[turnBoundaries[ti]] || 0;
            var tEnd = ti + 1 < turnBoundaries.length
                ? stateTimestampMs[turnBoundaries[ti + 1]] || tStart
                : stateTimestampMs[stateTimestampMs.length - 1] || tStart;
            turnStartMs.push(tStart);
            turnEndMs.push(tEnd);
        }

        // Build per-state turn index: which turn each state belongs to
        var stateTurnIndex = new Array(states.length);
        var tbIdx = 0;
        for (var si = 0; si < states.length; si++) {
            while (tbIdx + 1 < turnBoundaries.length && turnBoundaries[tbIdx + 1] <= si) tbIdx++;
            stateTurnIndex[si] = tbIdx;
        }

        REPLAY = {
            p0: p0, p1: p1, winner: winner, winnerName: winnerName,
            turns: totalTurns, cardSet: cardSet,
            states: states, actions: actions, turnBoundaries: turnBoundaries,
            commandInfo: replay.commandInfo,
            playerInfo: replay.playerInfo || null,
            timeInfo: replay.timeInfo || null,
            stateTimestampMs: stateTimestampMs,
            stateTurnIndex: stateTurnIndex,
            turnStartMs: turnStartMs,
            turnEndMs: turnEndMs
        };
        stateIndex = 0;
        totalStates = states.length;
    }

    // ── Live Spectating ──
    function initLive(gameInitInfo) {
        // Live BeginGame has data inside laneInfo[0] directly,
        // not in separate deckInfo/initInfo wrappers like S3 replays.
        // Also, live mergedDeck is empty — must build from base+randomizer names.
        var lane = {};
        if (gameInitInfo.laneInfo && gameInitInfo.laneInfo[0]) {
            lane = gameInitInfo.laneInfo[0];
        }
        var deckInfo = gameInitInfo.deckInfo || lane;
        var initInfo = gameInitInfo.initInfo || lane;

        // Build mergedDeck from card names if not provided
        var mergedDeck = gameInitInfo.mergedDeck;
        if (!mergedDeck || mergedDeck.length === 0) {
            mergedDeck = [];
            var rarityToSupply = { legendary: 1, rare: 4, normal: 10, trinket: 20 };
            var addCards = function(cardList) {
                if (!cardList) return;
                for (var i = 0; i < cardList.length; i++) {
                    var entry = cardList[i];
                    var name, supply;
                    if (typeof entry === 'string') {
                        name = entry;
                        var meta = CARD_META[name];
                        supply = meta ? (rarityToSupply[meta.rarity] || 10) : 10;
                    } else if (Array.isArray(entry)) {
                        // [name, supply] format
                        name = entry[0]; supply = entry[1];
                    } else if (entry && entry.UIName) {
                        name = entry.UIName;
                        supply = entry.supply || (rarityToSupply[entry.rarity] || 10);
                    } else continue;
                    mergedDeck.push({ UIName: name, supply: supply, rarity: (CARD_META[name] || {}).rarity || 'normal' });
                }
            };
            // base is array of arrays: [[cards for set 0], [cards for set 1]]
            var base = deckInfo.base || lane.base || [];
            for (var bi = 0; bi < base.length; bi++) {
                if (Array.isArray(base[bi])) addCards(base[bi]);
                else addCards([base[bi]]);
            }
            var rand = deckInfo.randomizer || lane.randomizer || [];
            for (var ri = 0; ri < rand.length; ri++) {
                if (Array.isArray(rand[ri])) addCards(rand[ri]);
                else addCards([rand[ri]]);
            }
        }

        var laneInfo = [{
            initResources: initInfo.initResources,
            base: deckInfo.base || lane.base,
            randomizer: deckInfo.randomizer || lane.randomizer,
            initCards: initInfo.initCards
        }];

        // Extract commandInfo for mid-game joins — the server sends all clicks
        // played so far in BeginGame.commandInfo.commandList. The Analyzer's
        // initializeAndPlayInitClicks() replays them to reach the current state.
        var commandInfo = gameInitInfo.commandInfo || lane.commandInfo || null;
        var scriptInfo = gameInitInfo.scriptInfo || lane.scriptInfo || { whiteStarts: true };

        var analyzerInit = {
            laneInfo: laneInfo,
            mergedDeck: mergedDeck,
            scriptInfo: scriptInfo,
            objectiveInfo: null,
            commandInfo: commandInfo
        };

        liveAnalyzer = new Analyzer(analyzerInit, -1, -1, null);
        liveAnalyzer.loaderInit();

        var cmdCount = commandInfo && commandInfo.commandList ? commandInfo.commandList.length : 0;
        console.log('[live] initLive: turn=' + liveAnalyzer.gameState.numTurns +
            ' instances=' + liveAnalyzer.gameState.table.size +
            ' nextInstId=' + liveAnalyzer.gameState.nextInstId +
            ' commandsReplayed=' + cmdCount);

        var p0 = 'Player 0', p1 = 'Player 1';
        if (gameInitInfo.players) { p0 = gameInitInfo.players[0] || p0; p1 = gameInitInfo.players[1] || p1; }

        REPLAY = {
            p0: p0, p1: p1, winner: -1, winnerName: '',
            turns: liveAnalyzer.gameState.numTurns, cardSet: [],
            states: [stateToCppJSON(liveAnalyzer.gameState)],
            actions: ['Start'], turnBoundaries: [0]
        };
        stateIndex = 0; totalStates = 1;
        notify();
        return getInfo();
    }

    // PUZZLE_PATCH_START
    // Build reverse lookup: UIName → internal name (codename) for CARD_LIBRARY.
    // CARD_LIBRARY keys are internal names; some have UIName properties.
    var _uiNameToInternal = null;
    function getUINameToInternal() {
        if (_uiNameToInternal) return _uiNameToInternal;
        _uiNameToInternal = {};
        for (var internalName in CARD_LIBRARY) {
            if (!CARD_LIBRARY.hasOwnProperty(internalName)) continue;
            var uiName = CARD_LIBRARY[internalName].UIName || internalName;
            _uiNameToInternal[uiName] = internalName;
            // Also map internal name to itself for direct lookups
            _uiNameToInternal[internalName] = internalName;
        }
        return _uiNameToInternal;
    }

    /**
     * Resolve card "needs" dependencies (support cards).
     * Mirrors DemoMissionReader.getSupportCards from AS3.
     */
    function getSupportCards(lib, deck) {
        var result = {};
        for (var cardName in deck) {
            if (!deck.hasOwnProperty(cardName)) continue;
            var cardDef = lib[cardName];
            if (cardDef && cardDef.needs) {
                var needed = String(cardDef.needs).split(',');
                for (var i = 0; i < needed.length; i++) {
                    var n = needed[i].trim();
                    if (n) result[n] = true;
                }
            }
        }
        return result;
    }

    /**
     * loadPuzzle(puzzleConfig) — Initialize a puzzle from configuration.
     *
     * Accepts a puzzle config object and sets up a playable game state.
     * Pattern follows DemoMissionReader.gameInitFromJSON from the SWF.
     *
     * @param {Object} puzzleConfig
     * @param {Object} puzzleConfig.startingState — board setup
     * @param {Object} [puzzleConfig.uniqueCards] — custom card definitions to merge
     * @param {Object} [puzzleConfig.cardUpdates] — patches to existing card definitions
     * @param {Object} [puzzleConfig.customTab1Hotkeys] — hotkey overrides
     * @returns {Object} ViewerInfo
     */
    function loadPuzzle(puzzleConfig) {
        var ss = puzzleConfig.startingState;
        if (!ss) throw new Error('loadPuzzle: startingState is required');

        // Local copy of name lookup — don't mutate the cached base lookup,
        // otherwise uniqueCards from a previous puzzle leak into the next one.
        var baseLookup = getUINameToInternal();
        var lookup = {};
        for (var lk in baseLookup) {
            if (baseLookup.hasOwnProperty(lk)) lookup[lk] = baseLookup[lk];
        }

        // Build the full card library, merging uniqueCards and cardUpdates
        var fullLibrary = {};
        for (var k in CARD_LIBRARY) {
            if (CARD_LIBRARY.hasOwnProperty(k)) {
                fullLibrary[k] = CARD_LIBRARY[k];
            }
        }
        if (puzzleConfig.uniqueCards) {
            for (var uk in puzzleConfig.uniqueCards) {
                if (puzzleConfig.uniqueCards.hasOwnProperty(uk)) {
                    fullLibrary[uk] = puzzleConfig.uniqueCards[uk];
                    // Register in local lookup (not cached base)
                    var ucUI = puzzleConfig.uniqueCards[uk].UIName || uk;
                    lookup[ucUI] = uk;
                    lookup[uk] = uk;
                }
            }
        }
        if (puzzleConfig.cardUpdates) {
            for (var cu in puzzleConfig.cardUpdates) {
                if (puzzleConfig.cardUpdates.hasOwnProperty(cu)) {
                    // Shallow merge: each patch property fully replaces the base property.
                    // This is intentional — cardUpdates patches are complete replacements,
                    // not deep merges into nested structures.
                    var base = fullLibrary[cu] || {};
                    var updated = {};
                    for (var bp in base) { if (base.hasOwnProperty(bp)) updated[bp] = base[bp]; }
                    var patch = puzzleConfig.cardUpdates[cu];
                    for (var pp in patch) { if (patch.hasOwnProperty(pp)) updated[pp] = patch[pp]; }
                    fullLibrary[cu] = updated;
                }
            }
        }

        // If this puzzle modified cards (via uniqueCards or cardUpdates), rebuild the card meta
        // so getCardMeta() returns accurate stats (e.g. buildTime) for the modified cards.
        // Puzzles without card modifications skip this for performance.
        if (puzzleConfig.uniqueCards || puzzleConfig.cardUpdates) {
            PUZZLE_CARD_META = buildRuntimeCardMeta(fullLibrary);
        } else {
            PUZZLE_CARD_META = null; // Use static CARD_META for unmodified puzzles
        }

        // Helper: resolve display name to internal name
        function resolve(displayName) {
            if (lookup[displayName]) return lookup[displayName];
            // Fallback: display name IS the internal name
            return displayName;
        }

        // Helper: get supply name from entry (string or [name, supply])
        function supplyToName(entry) {
            if (typeof entry === 'string') return entry;
            if (Array.isArray(entry)) return entry[0];
            throw new Error('loadPuzzle: unknown supply format');
        }

        // Collect all card names referenced in the puzzle
        var referencedCards = {};
        var allSupplyLists = [
            ss.whiteSupply || [], ss.blackSupply || [],
            ss.whiteDominionSupply || [], ss.blackDominionSupply || []
        ];
        for (var si = 0; si < allSupplyLists.length; si++) {
            for (var sj = 0; sj < allSupplyLists[si].length; sj++) {
                var sName = resolve(supplyToName(allSupplyLists[si][sj]));
                referencedCards[sName] = true;
            }
        }
        // Init cards: [[count, "DisplayName", ...modifiers], ...]
        var initLists = [ss.whiteInitCards || [], ss.blackInitCards || []];
        for (var ii = 0; ii < initLists.length; ii++) {
            for (var ij = 0; ij < initLists[ii].length; ij++) {
                var icName = resolve(initLists[ii][ij][1]);
                referencedCards[icName] = true;
            }
        }

        // Resolve support cards (cards needed by referenced cards)
        var support = getSupportCards(fullLibrary, referencedCards);

        // Build mergedDeck: full card definition objects with name property
        var mergedDeck = [];
        var allCards = {};
        for (var rc in referencedCards) {
            if (referencedCards.hasOwnProperty(rc)) allCards[rc] = true;
        }
        for (var sc in support) {
            if (support.hasOwnProperty(sc)) allCards[sc] = true;
        }
        for (var cardInternalName in allCards) {
            if (!allCards.hasOwnProperty(cardInternalName)) continue;
            var cardDef = fullLibrary[cardInternalName];
            if (!cardDef) {
                console.warn('[loadPuzzle] Card not found in library: ' + cardInternalName);
                continue;
            }
            // Clone and add name property (internal name)
            var entry = {};
            for (var dp in cardDef) {
                if (cardDef.hasOwnProperty(dp)) entry[dp] = cardDef[dp];
            }
            entry.name = cardInternalName;
            mergedDeck.push(entry);
        }

        // Build supply arrays using internal names
        function buildSupplyArray(displayNames) {
            var result = [];
            for (var i = 0; i < displayNames.length; i++) {
                var dn = displayNames[i];
                if (typeof dn === 'string') {
                    result.push(resolve(dn));
                } else if (Array.isArray(dn)) {
                    // [name, supply] format
                    result.push([resolve(dn[0]), dn[1]]);
                } else {
                    result.push(dn);
                }
            }
            return result;
        }

        // Build initCards using internal names
        function buildInitCards(initArray) {
            var result = [];
            for (var i = 0; i < initArray.length; i++) {
                var ic = initArray[i].slice(); // shallow copy
                ic[1] = resolve(ic[1]);
                result.push(ic);
            }
            return result;
        }

        var whiteBase = buildSupplyArray(ss.whiteSupply || []);
        var blackBase = buildSupplyArray(ss.blackSupply || []);
        var whiteRand = buildSupplyArray(ss.whiteDominionSupply || []);
        var blackRand = buildSupplyArray(ss.blackDominionSupply || []);
        var whiteInit = buildInitCards(ss.whiteInitCards || []);
        var blackInit = buildInitCards(ss.blackInitCards || []);

        var scriptInfo = { whiteStarts: ss.whiteStarts !== false };

        var laneInfo = [{
            base: [whiteBase, blackBase],
            randomizer: [whiteRand, blackRand],
            initResources: [ss.whiteInitResources || '0', ss.blackInitResources || '0'],
            initCards: [whiteInit, blackInit],
            infiniteSupplies: ss.infiniteSupplies || 0,
            customTab1Hotkeys: puzzleConfig.customTab1Hotkeys || {},
            AIAnimationFramesPerClick: 12
        }];

        var analyzerInit = {
            laneInfo: laneInfo,
            mergedDeck: mergedDeck,
            scriptInfo: scriptInfo,
            objectiveInfo: null,
            commandInfo: null
        };

        liveAnalyzer = new Analyzer(analyzerInit, -1, -1, null);
        liveAnalyzer.loaderInit();

        console.log('[puzzle] loadPuzzle: turn=' + liveAnalyzer.gameState.numTurns +
            ' instances=' + liveAnalyzer.gameState.table.size +
            ' nextInstId=' + liveAnalyzer.gameState.nextInstId +
            ' cards=' + mergedDeck.length);

        REPLAY = {
            p0: puzzleConfig.playerName || 'Player', p1: puzzleConfig.opponentName || 'Puzzle',
            winner: -1, winnerName: '',
            turns: liveAnalyzer.gameState.numTurns, cardSet: [],
            states: [stateToCppJSON(liveAnalyzer.gameState)],
            actions: ['Start'], turnBoundaries: [0]
        };
        stateIndex = 0; totalStates = 1;
        notify();
        return getInfo();
    }
    // PUZZLE_PATCH_END

    function checkAndUpdateWinner() {
        if (!liveAnalyzer) return;
        if (liveAnalyzer.gameState.finished && REPLAY.winner === -1) {
            var r = liveAnalyzer.gameState.result;
            // result: 0 = COLOR_WHITE wins, 1 = COLOR_BLACK wins
            if (r === 0 || r === 1) {
                REPLAY.winner = r;
            }
        }
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
                checkAndUpdateWinner();
                notify();
                return { accepted: true, info: getInfo() };
            }

            // Recovery 1 — Breach skip: stale space/end-swipe clicks during breach are harmless
            if (liveAnalyzer.gameState.glassBroken && (clickType === 'space clicked' || clickType === 'end swipe processed')) {
                console.log('[live] breach skip for', clickType, clickId);
                return { accepted: true, info: getInfo() };
            }

            // Recovery 2 — End-swipe retry: click failed while in a swipe, end the swipe first
            if (liveAnalyzer.controller.inSwipe && clickType !== 'end swipe processed') {
                console.log('[live] end-swipe retry for', clickType, clickId);
                var swipeResult = liveAnalyzer.recordClick(false, false, 'end swipe processed', -1);
                if (swipeResult.canClick) {
                    result = liveAnalyzer.recordClick(false, false, clickType, clickId, clickParams);
                    if (result.canClick) {
                        var newState2 = stateToCppJSON(liveAnalyzer.gameState);
                        REPLAY.states.push(newState2);
                        REPLAY.actions.push(describeClick({_type: clickType, _id: clickId}, liveAnalyzer.gameState, prePhase));
                        if (liveAnalyzer.gameState.numTurns !== REPLAY.turns) {
                            REPLAY.turnBoundaries.push(REPLAY.states.length - 1);
                            REPLAY.turns = liveAnalyzer.gameState.numTurns;
                        }
                        totalStates = REPLAY.states.length;
                        stateIndex = totalStates - 1;
                        checkAndUpdateWinner();
                        notify();
                        return { accepted: true, info: getInfo() };
                    }
                }
            }

            // Recovery 3 — Confirm-to-defense auto-commit: JS engine needs an extra
            // space click to transition from confirm phase to defense phase
            if (liveAnalyzer.gameState.phase === 'confirm' && !liveAnalyzer.gameState.finished &&
                clickType !== 'space clicked' && clickType !== 'revert clicked' &&
                clickType !== 'undo clicked' && clickType !== 'redo clicked') {
                console.log('[live] confirm auto-commit before', clickType, clickId);
                var commitResult = liveAnalyzer.recordClick(false, false, 'space clicked', -1);
                if (commitResult.canClick) {
                    result = liveAnalyzer.recordClick(false, false, clickType, clickId, clickParams);
                    if (result.canClick) {
                        var newState3 = stateToCppJSON(liveAnalyzer.gameState);
                        REPLAY.states.push(newState3);
                        REPLAY.actions.push(describeClick({_type: clickType, _id: clickId}, liveAnalyzer.gameState, prePhase));
                        if (liveAnalyzer.gameState.numTurns !== REPLAY.turns) {
                            REPLAY.turnBoundaries.push(REPLAY.states.length - 1);
                            REPLAY.turns = liveAnalyzer.gameState.numTurns;
                        }
                        totalStates = REPLAY.states.length;
                        stateIndex = totalStates - 1;
                        checkAndUpdateWinner();
                        notify();
                        return { accepted: true, info: getInfo() };
                    }
                }
            }

            // Diagnostic: why did this click fail?
            var gs = liveAnalyzer.gameState;
            var diag = 'phase=' + gs.phase + ' turn=' + gs.numTurns;
            if (gs.glassBroken) diag += ' glassBroken';
            if (gs.finished) diag += ' FINISHED';
            if (liveAnalyzer.controller.inSwipe) diag += ' inSwipe';
            if (clickType === 'inst clicked' || clickType === 'inst shift clicked') {
                var inst = gs.instIdToInst(clickId);
                if (inst) diag += ' | inst: ' + inst.card.UIName + ' owner=P' + inst.owner + ' role=' + inst.role;
                else diag += ' | inst NOT FOUND id=' + clickId;
            }
            if (clickType === 'card clicked') {
                if (gs.cards && clickId >= 0 && clickId < gs.cards.length) diag += ' | card: ' + gs.cards[clickId].UIName;
                else diag += ' | card OUT OF RANGE id=' + clickId + ' deckLen=' + (gs.cards ? gs.cards.length : 0);
            }
            console.warn('[live] FAILED:', clickType, 'id=' + clickId, diag);
            return { accepted: false, info: getInfo() };
        } catch (e) {
            console.error('[live] EXCEPTION:', clickType, 'id=' + clickId, e.message);
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
    function getCardMeta() { return PUZZLE_CARD_META !== null ? PUZZLE_CARD_META : CARD_META; }
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
        loadPuzzle: loadPuzzle,
        nextAction: nextAction, prevAction: prevAction,
        nextTurn: nextTurn, prevTurn: prevTurn,
        goToStart: goToStart, goToEnd: goToEnd,
        setStateIndex: setStateIndex, getInfo: getInfo,
        getGameState: getGameState, getCardMeta: getCardMeta, getReplay: getReplay,
        getAssets: function() { return SMALL_ASSETS; },
        // Puzzle mode support: expose internals for interaction layer
        get cardNameToCardId() { return liveAnalyzer ? liveAnalyzer.gameState.cardNameToCardId : null; },
        /** Resolve a display name (UIName) to card ID. cardNameToCardId uses internal names only. */
        displayNameToCardId: function(displayName) {
            if (!liveAnalyzer) return -1;
            var cards = liveAnalyzer.gameState.cards;
            for (var i = 0; i < cards.length; i++) {
                if (cards[i].UIName === displayName) return i;
            }
            return -1;
        },
        analyzerCanClick: function(type, id) { return liveAnalyzer ? liveAnalyzer.analyzerCanClick(type, id) : false; },
        analyzerWhatToHighlight: function(type, id) { return liveAnalyzer ? liveAnalyzer.analyzerWhatToHighlight(type, id) : { canClick: false }; }
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
    const smallAssets = collectSmallAssets();

    const bundle = buildBundle(moduleBundle, cardMeta, smallAssets, cardLibrary);
    fs.writeFileSync(outputPath, bundle, 'utf-8');

    const sizeMB = (Buffer.byteLength(bundle) / 1024 / 1024).toFixed(1);
    console.error(`Written: ${outputPath} (${sizeMB} MB)`);
}

main();
