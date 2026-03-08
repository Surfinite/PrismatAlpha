'use strict';

/**
 * build_replay_viewer.js — Build a self-contained HTML replay viewer.
 *
 * Bundles the JS game engine, all card art, UI textures, and cardLibrary.jso
 * into a single HTML file (~35MB) that anyone can open in a browser.
 *
 * Usage:
 *   node js_engine/build_replay_viewer.js [output.html]
 *
 * The viewer accepts drag-and-drop of .json.gz replay files from Prismata's S3 bucket.
 * No server, no Node.js needed by the recipient.
 */

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const JS_DIR = __dirname;
const BIN_DIR = path.join(JS_DIR, '..', 'bin');
const CARD_ART_DIR = path.join(BIN_DIR, 'asset', 'images', 'cards');
const CARD_BG_DIR = path.join(BIN_DIR, 'asset', 'images', 'cardbg');
const ICON_STATUS_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'status');
const ICON_RESOURCE_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'resource');
const CARD_LIBRARY_PATH = path.join(BIN_DIR, 'asset', 'config', 'cardLibrary.jso');

// ---------------------------------------------------------------------------
// Engine modules to bundle (topological order — dependencies before dependents)
// ---------------------------------------------------------------------------
const ENGINE_MODULES = [
    'C.js',
    'Mana.js',
    'Rndm.js',
    'SacDescription.js',
    'CreateDescription.js',
    'Script.js',
    'Card.js',
    'Inst.js',
    'AS3Dictionary.js',
    'Click.js',
    'ClickResult.js',
    'EndTurnObject.js',
    'Order.js',
    'StateHelper.js',
    'State.js',
    'Controller.js',
    'Analyzer.js',
    'replay_exporter.js'
];

// ---------------------------------------------------------------------------
// Read and base64-encode an image
// ---------------------------------------------------------------------------
function readImageBase64(filePath) {
    if (!fs.existsSync(filePath)) return null;
    const buf = fs.readFileSync(filePath);
    return 'data:image/png;base64,' + buf.toString('base64');
}

// ---------------------------------------------------------------------------
// Collect assets — only card art for units in cardLibrary.jso
// ---------------------------------------------------------------------------
function collectAllAssets(cardLibrary) {
    const assets = {};

    // Build set of valid UINames from cardLibrary
    const validNames = new Set();
    for (const [internalName, card] of Object.entries(cardLibrary)) {
        validNames.add(card.UIName || internalName);
    }

    // Card art — only for units in cardLibrary (skip skins/orphan PNGs)
    const cardFiles = fs.readdirSync(CARD_ART_DIR).filter(f => f.endsWith('.png'));
    let included = 0;
    for (const file of cardFiles) {
        const name = path.basename(file, '.png');
        if (!validNames.has(name)) continue;
        const data = readImageBase64(path.join(CARD_ART_DIR, file));
        if (data) { assets['card_' + name] = data; included++; }
    }
    console.error(`Card art: ${included}/${cardFiles.length} images (${cardFiles.length - included} skins/orphans skipped)`);

    // Card backgrounds
    const bgFiles = {
        'bg_default': 'Card_Blue.png',
        'bg_default_red': 'Card_Red.png',
        'bg_assigned': 'Card_Grey.png',
        'bg_construction': 'Card_Orange.png',
        'bg_dead': 'Card_Dead.png',
        'bg_border_green': 'Card_Border_Green.png',
        'bg_chilled': 'Card_Blue_Frost.png'
    };
    for (const [key, file] of Object.entries(bgFiles)) {
        const data = readImageBase64(path.join(CARD_BG_DIR, file));
        if (data) assets[key] = data;
    }

    // Status icons
    const statusFiles = {
        'icon_attack': 'icon_attack.png',
        'icon_defend': 'icon_defend.png',
        'icon_construct': 'status_construct.png',
        'icon_doom': 'status_doom.png',
        'icon_delay': 'status_delay.png',
        'icon_tap': 'status_tap.png',
        'icon_hp': 'status_hp.png',
        'icon_charge0': 'status_charge0.png',
        'icon_charge1': 'status_charge1.png',
        'icon_charge2': 'status_charge2.png',
        'icon_charge3': 'status_charge3.png',
        'icon_undefendable': 'status_undefendable.png',
        'icon_shield_blue': 'highlight_blueshield.png',
        'icon_shield_gold': 'highlight_goldshield.png',
        'icon_shield_white': 'highlight_whiteshield.png',
        'icon_clock': 'clock.png'
    };
    for (const [key, file] of Object.entries(statusFiles)) {
        const data = readImageBase64(path.join(ICON_STATUS_DIR, file));
        if (data) assets[key] = data;
    }

    // Resource icons
    const resourceFiles = {
        'res_gold': 'P.png',
        'res_blue': 'B.png',
        'res_green': 'G.png',
        'res_red': 'C.png',
        'res_energy': 'H.png',
        'res_attack': 'A.png'
    };
    for (const [key, file] of Object.entries(resourceFiles)) {
        const data = readImageBase64(path.join(ICON_RESOURCE_DIR, file));
        if (data) assets[key] = data;
    }

    console.error(`Total assets: ${Object.keys(assets).length}`);
    return assets;
}

// ---------------------------------------------------------------------------
// Build the module bundle — wraps each engine module in a factory function
// ---------------------------------------------------------------------------
function buildModuleBundle() {
    const factories = [];

    for (const modFile of ENGINE_MODULES) {
        const filePath = path.join(JS_DIR, modFile);
        let source = fs.readFileSync(filePath, 'utf-8');

        // Strip 'use strict' — we'll add it once at the top level
        source = source.replace(/^'use strict';\s*/m, '');

        // Replace require('./X') with our shim — but skip Node builtins (fs, path, etc.)
        // The shim resolves './C' → 'C', './Mana' → 'Mana', etc.
        source = source.replace(/require\('\.\/([^']+)'\)/g, '__require("$1")');

        // Neutralize any remaining require() calls to Node builtins (fs, path, zlib, etc.)
        // These are only used in CLI entry points, not in the engine core
        source = source.replace(/require\('(fs|path|zlib|https?|child_process|crypto|worker_threads)'\)/g,
            '({})');

        const modName = modFile.replace(/\.js$/, '');
        factories.push(`// --- ${modFile} ---\n__modules["${modName}"] = (function() {\n    var module = { exports: {} };\n    var exports = module.exports;\n    ${source}\n    return module.exports;\n})();\n`);
    }

    return factories.join('\n');
}

// ---------------------------------------------------------------------------
// Build card metadata from cardLibrary.jso (same as replay_to_html.js)
// ---------------------------------------------------------------------------
function buildCardMetadata(cardLibrary) {
    const byUIName = {};

    for (const [internalName, card] of Object.entries(cardLibrary)) {
        const uiName = card.UIName || internalName;

        let autoAttack = 0;
        let abilityAttack = 0;
        if (card.beginOwnTurnScript && typeof card.beginOwnTurnScript.receive === 'string') {
            for (const ch of card.beginOwnTurnScript.receive) {
                if (ch === 'A') autoAttack++;
            }
        }
        if (card.abilityScript && typeof card.abilityScript.receive === 'string') {
            for (const ch of card.abilityScript.receive) {
                if (ch === 'A') abilityAttack++;
            }
        }

        byUIName[uiName] = {
            attack: autoAttack + abilityAttack,
            autoAttack,
            abilityAttack,
            toughness: card.toughness || 0,
            hasAbility: !!(card.abilityScript || card.targetAction),
            hasTargetAbility: !!card.targetAction,
            isFrontline: !!card.undefendable,
            canBlock: !!card.defaultBlocking,
            isFragile: !!card.fragile,
            defaultBlocking: !!card.defaultBlocking,
            buyCost: card.buyCost || '',
            buildTime: card.buildTime || 1,
            lifespan: card.lifespan || -1,
            charge: card.startingCharge || 0,
            baseSet: !!card.baseSet,
            rarity: card.rarity || 'normal'
        };
    }

    return byUIName;
}

// ---------------------------------------------------------------------------
// Generate the HTML
// ---------------------------------------------------------------------------
function buildHTML(moduleBundle, assets, cardMeta) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prismata Replay Viewer</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a2e; overflow: hidden; font-family: Consolas, monospace; color: #ccc; }
canvas { display: block; }
#dropzone {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    z-index: 100;
}
#dropzone.hidden { display: none; }
#dropzone .box {
    border: 3px dashed #555; border-radius: 20px; padding: 60px 80px;
    text-align: center; transition: border-color 0.2s, background 0.2s;
    background: rgba(20, 20, 50, 0.9);
}
#dropzone.dragover .box { border-color: #FFD700; background: rgba(40, 40, 80, 0.95); }
#dropzone h1 { font-size: 28px; color: #FFD700; margin-bottom: 16px; }
#dropzone p { font-size: 16px; color: #888; margin-bottom: 8px; }
#dropzone .hint { font-size: 13px; color: #555; margin-top: 16px; }
#dropzone .divider { color: #444; margin: 20px 0; font-size: 14px; }
#dropzone .code-section { margin-top: 4px; }
#dropzone input[type="text"] {
    background: #1a1a2e; border: 1px solid #555; border-radius: 6px;
    color: #FFD700; font-family: Consolas, monospace; font-size: 16px;
    padding: 8px 14px; width: 260px; text-align: center; outline: none;
}
#dropzone input[type="text"]:focus { border-color: #FFD700; }
#dropzone input[type="text"]::placeholder { color: #444; }
#dropzone button {
    background: #2a2a5e; border: 1px solid #555; border-radius: 6px;
    color: #ccc; font-family: Consolas, monospace; font-size: 14px;
    padding: 8px 18px; cursor: pointer; margin-left: 8px;
}
#dropzone button:hover { background: #3a3a7e; border-color: #FFD700; color: #FFD700; }
#dropzone .download-link { display: none; margin-top: 12px; }
#dropzone .download-link a { color: #4488ff; font-size: 13px; }
#status { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    font-size: 14px; color: #FFD700; z-index: 200; display: none; }
</style>
</head>
<body>
<div id="dropzone">
    <div class="box">
        <h1>Prismata Replay Viewer</h1>
        <p>Drop a <code>.json.gz</code> replay file here</p>
        <div class="divider">- or -</div>
        <div class="code-section">
            <p>Enter a replay code:</p>
            <div style="margin-top: 8px;">
                <input type="text" id="replayCode" placeholder="e.g. 2feHk-9nh9S">
                <button id="loadBtn">Load</button>
            </div>
            <div class="download-link" id="downloadLink"></div>
        </div>
        <p class="hint">Replay codes from Prismata game history or community</p>
    </div>
</div>
<div id="status"></div>
<canvas id="board"></canvas>

<script>
'use strict';

// === MODULE SYSTEM ===
var __modules = {};
function __require(name) {
    name = name.replace(/\\.js$/, '');
    if (__modules[name]) return __modules[name];
    throw new Error('Module not found: ' + name);
}

// === ENGINE MODULES ===
${moduleBundle}

// === CARD METADATA ===
var CARD_META = ${JSON.stringify(cardMeta)};

// === ASSETS ===
var ASSET_DATA = ${JSON.stringify(assets)};

// === REPLAY VIEWER ===
(function() {
    var C = __require('C');
    var Analyzer = __require('Analyzer');
    var replay_exporter = __require('replay_exporter');
    var stateToCppJSON = replay_exporter.stateToCppJSON;

    var REPLAY = null;  // Set after replay is loaded
    var canvas = document.getElementById('board');
    var ctx = canvas.getContext('2d');
    var dropzone = document.getElementById('dropzone');
    var statusEl = document.getElementById('status');

    // State
    var stateIndex = 0;
    var totalStates = 0;

    // Images
    var images = {};
    var imagesLoaded = 0;
    var totalImages = 0;

    function showStatus(msg) {
        statusEl.style.display = 'block';
        statusEl.textContent = msg;
    }
    function hideStatus() { statusEl.style.display = 'none'; }

    // -----------------------------------------------------------------------
    // Load images from base64 asset data
    // -----------------------------------------------------------------------
    function loadImages(callback) {
        var keys = Object.keys(ASSET_DATA);
        totalImages = keys.length;
        imagesLoaded = 0;
        if (totalImages === 0) { callback(); return; }
        for (var ki = 0; ki < keys.length; ki++) {
            var img = new Image();
            img.onload = function() { imagesLoaded++; if (imagesLoaded >= totalImages) callback(); };
            img.onerror = function() { imagesLoaded++; if (imagesLoaded >= totalImages) callback(); };
            img.src = ASSET_DATA[keys[ki]];
            images[keys[ki]] = img;
        }
    }

    // -----------------------------------------------------------------------
    // Drag-and-drop handling
    // -----------------------------------------------------------------------
    dropzone.addEventListener('dragover', function(e) {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', function() {
        dropzone.classList.remove('dragover');
    });
    dropzone.addEventListener('drop', function(e) {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        var file = e.dataTransfer.files[0];
        if (!file) return;
        showStatus('Loading ' + file.name + '...');
        processFile(file);
    });

    // -----------------------------------------------------------------------
    // Replay code input — fetch from S3
    // -----------------------------------------------------------------------
    var S3_BASE = 'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/';
    var codeInput = document.getElementById('replayCode');
    var loadBtn = document.getElementById('loadBtn');
    var downloadLinkEl = document.getElementById('downloadLink');

    function buildS3Url(code) {
        // URL-encode special chars: + → %2B, @ → %40, etc.
        return S3_BASE + encodeURIComponent(code) + '.json.gz';
    }

    function loadReplayCode() {
        var code = codeInput.value.trim();
        if (!code) return;
        var url = buildS3Url(code);
        showStatus('Fetching ' + code + ' from S3...');

        // Show download link as fallback (in case CORS blocks fetch)
        downloadLinkEl.innerHTML = 'Direct link: <a href="' + url + '" target="_blank">' + url + '</a>';
        downloadLinkEl.style.display = 'block';

        fetch(url).then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status + ' — replay not found');
            return resp.arrayBuffer();
        }).then(function(buf) {
            downloadLinkEl.style.display = 'none';
            showStatus('Decompressing...');
            return processArrayBuffer(buf);
        }).catch(function(err) {
            showStatus('Fetch failed: ' + err.message + ' — use the download link below, then drop the file here');
        });
    }

    loadBtn.addEventListener('click', loadReplayCode);
    codeInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') loadReplayCode();
    });

    // -----------------------------------------------------------------------
    // Decompress and parse a .json.gz or .json file
    // -----------------------------------------------------------------------
    async function processFile(file) {
        try {
            var arrayBuf = await file.arrayBuffer();
            await processArrayBuffer(arrayBuf);
        } catch (err) {
            showStatus('Error: ' + err.message);
            console.error(err);
        }
    }

    async function processArrayBuffer(arrayBuf) {
        try {
            var jsonStr;
            // Check for gzip magic bytes (1f 8b)
            var header = new Uint8Array(arrayBuf.slice(0, 2));
            if (header[0] === 0x1f && header[1] === 0x8b) {
                showStatus('Decompressing...');
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

            showStatus('Parsing replay...');
            var replayData = JSON.parse(jsonStr);

            // Check if this is an S3 replay (has deckInfo + commandInfo) or a matchup replay (has states[])
            if (replayData.states && replayData.states.length > 0) {
                // Already a matchup-runner replay with pre-computed states
                loadMatchupReplay(replayData);
            } else if (replayData.deckInfo && replayData.commandInfo) {
                // S3 replay — needs engine processing
                showStatus('Replaying game (' + replayData.commandInfo.commandList.length + ' clicks)...');
                await new Promise(function(r) { setTimeout(r, 10); }); // let UI update
                processS3Replay(replayData);
            } else {
                showStatus('Error: Unrecognized replay format');
                return;
            }
        } catch (err) {
            showStatus('Error: ' + err.message);
            console.error(err);
        }
    }

    // -----------------------------------------------------------------------
    // Load a matchup-runner replay (pre-computed states)
    // -----------------------------------------------------------------------
    function loadMatchupReplay(data) {
        REPLAY = {
            p0: data.p0 || 'Player 0',
            p1: data.p1 || 'Player 1',
            winner: data.winner,
            winnerName: data.winnerName || (data.winner === 0 ? data.p0 : data.winner === 1 ? data.p1 : 'Draw'),
            turns: data.turns || 0,
            cardSet: data.cardSet || [],
            states: data.states,
            actions: data.actions || [],
            turnBoundaries: data.turnBoundaries || []
        };
        startViewer();
    }

    // -----------------------------------------------------------------------
    // Process an S3 replay through the JS engine
    // -----------------------------------------------------------------------
    function processS3Replay(replay) {
        // Build gameInitInfo (same as replay_validator.js replayToGameInitInfo)
        var laneInfo = [{
            initResources: replay.initInfo.initResources,
            base: replay.deckInfo.base,
            randomizer: replay.deckInfo.randomizer,
            initCards: replay.initInfo.initCards
        }];
        var scriptInfo = { whiteStarts: true };

        var gameInitInfo = {
            laneInfo: laneInfo,
            mergedDeck: replay.deckInfo.mergedDeck,
            scriptInfo: scriptInfo,
            objectiveInfo: null,
            commandInfo: null  // Don't auto-replay
        };

        var analyzer = new Analyzer(gameInitInfo, -1, -1, null);
        analyzer.loaderInit();

        // Capture initial state
        var states = [stateToCppJSON(analyzer.gameState)];
        var actions = ['Start'];
        var turnBoundaries = [0];
        var lastTurn = analyzer.gameState.numTurns;

        var cmdList = replay.commandInfo.commandList;
        var clicksPerTurn = replay.commandInfo.clicksPerTurn;

        // Derive player names from playerInfo
        var p0 = 'Player 0', p1 = 'Player 1';
        if (replay.playerInfo) {
            if (replay.playerInfo[0]) p0 = replay.playerInfo[0].displayName || replay.playerInfo[0].name || 'Player 0';
            if (replay.playerInfo[1]) p1 = replay.playerInfo[1].displayName || replay.playerInfo[1].name || 'Player 1';
        }

        // Replay each click
        for (var i = 0; i < cmdList.length; i++) {
            var cmd = cmdList[i];
            var cmdType = String(cmd._type);

            // Skip emotes
            if (cmdType.indexOf(String(C.CLICK_REPLAY_EMOTE)) === 0) continue;
            if (analyzer.gameState.finished) break;

            // Capture pre-click phase for label
            var prePhase = analyzer.gameState.phase;

            try {
                var clickResult = analyzer.recordClick(false, false, cmd._type, cmd._id, cmd._params);
                if (clickResult.canClick) {
                    // Build action label
                    var label = describeClick(cmd, analyzer.gameState, prePhase);
                    states.push(stateToCppJSON(analyzer.gameState));
                    actions.push(label);

                    // Track turn boundaries
                    if (analyzer.gameState.numTurns !== lastTurn) {
                        turnBoundaries.push(states.length - 1);
                        lastTurn = analyzer.gameState.numTurns;
                    }
                }
            } catch (err) {
                // Skip failed clicks (same as AS3 soft assert behavior)
            }
        }

        // Determine winner
        var winner = -1;
        var winnerName = 'Draw';
        if (replay.result !== undefined && replay.result !== null) {
            if (replay.result === C.COLOR_WHITE || replay.result === 0) { winner = 0; winnerName = p0; }
            else if (replay.result === C.COLOR_BLACK || replay.result === 1) { winner = 1; winnerName = p1; }
        } else if (analyzer.gameState.finished) {
            var r = analyzer.gameState.result;
            if (r === C.COLOR_WHITE) { winner = 0; winnerName = p0; }
            else if (r === C.COLOR_BLACK) { winner = 1; winnerName = p1; }
        }

        // Derive card set from deckInfo
        var cardSet = [];
        if (replay.deckInfo && replay.deckInfo.randomizer) {
            for (var ri = 0; ri < replay.deckInfo.randomizer.length; ri++) {
                var rz = replay.deckInfo.randomizer[ri];
                if (rz) {
                    for (var rj = 0; rj < rz.length; rj++) {
                        if (rz[rj].UIName) cardSet.push(rz[rj].UIName);
                        else if (rz[rj].name) cardSet.push(rz[rj].name);
                    }
                }
            }
        }

        var totalTurns = 0;
        if (clicksPerTurn) totalTurns = clicksPerTurn.length;

        REPLAY = {
            p0: p0,
            p1: p1,
            winner: winner,
            winnerName: winnerName,
            turns: totalTurns,
            cardSet: cardSet,
            states: states,
            actions: actions,
            turnBoundaries: turnBoundaries
        };

        showStatus('Processed ' + states.length + ' states, ' + totalTurns + ' turns');
        setTimeout(startViewer, 200);
    }

    // -----------------------------------------------------------------------
    // Describe a click for the action label
    // -----------------------------------------------------------------------
    function describeClick(click, state, prePhase) {
        var type = click._type;
        var id = click._id;

        switch (type) {
            case C.CLICK_CARD:
            case C.CLICK_CARD_SHIFT: {
                // Buy card — find card name from state.cards by deck index
                if (state.cards && id >= 0 && id < state.cards.length) {
                    return 'Buy ' + state.cards[id].UIName;
                }
                return 'Buy card ' + id;
            }
            case C.CLICK_INST:
            case C.CLICK_INST_SHIFT: {
                var inst = state.table.get(id);
                if (inst) {
                    var name = inst.card.UIName;
                    var phase = state.phase;
                    if (phase === C.PHASE_DEFENSE) {
                        return 'Block with ' + name;
                    }
                    if (inst.owner !== state.turn) {
                        return name;  // opponent's unit — no "Use" prefix
                    }
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
            default:
                return 'Click ' + type;
        }
    }

    // -----------------------------------------------------------------------
    // Start the canvas viewer
    // -----------------------------------------------------------------------
    function startViewer() {
        dropzone.classList.add('hidden');
        hideStatus();
        stateIndex = 0;
        totalStates = REPLAY.states.length;
        document.title = REPLAY.p0 + ' vs ' + REPLAY.p1 + ' — Prismata Replay';
        resize();
    }

    // -----------------------------------------------------------------------
    // Layout constants
    // -----------------------------------------------------------------------
    var BUY_COL_WIDTH = 200;
    var BUY_PANE_WIDTH = BUY_COL_WIDTH * 2;
    var CARD_W = 110;
    var CARD_H = 110;
    var BUYABLE_ROW_H = 60;
    var SAME_OVERLAP = -CARD_W * 4 / 5;
    var DIFF_BUFFER_X = CARD_W / 5;

    // -----------------------------------------------------------------------
    // Lane assignment
    // -----------------------------------------------------------------------
    function getLane(cardName) {
        var meta = CARD_META[cardName];
        if (!meta) return 1;
        if (meta.isFrontline) return 0;
        if (meta.hasAbility || meta.hasTargetAbility) return 1;
        if (meta.canBlock) return 0;
        return 2;
    }

    // -----------------------------------------------------------------------
    // Parse mana string
    // -----------------------------------------------------------------------
    function parseMana(manaStr) {
        var res = { gold: 0, blue: 0, green: 0, red: 0, energy: 0, attack: 0 };
        if (!manaStr) return res;
        var numBuf = '';
        for (var i = 0; i < manaStr.length; i++) {
            var ch = manaStr[i];
            if (ch >= '0' && ch <= '9') {
                numBuf += ch;
            } else {
                if (numBuf) { res.gold += parseInt(numBuf); numBuf = ''; }
                switch (ch) {
                    case 'B': res.blue++; break;
                    case 'G': res.green++; break;
                    case 'C': res.red++; break;
                    case 'H': res.energy++; break;
                    case 'A': res.attack++; break;
                }
            }
        }
        if (numBuf) res.gold += parseInt(numBuf);
        return res;
    }

    // -----------------------------------------------------------------------
    // Compute attack/defense
    // -----------------------------------------------------------------------
    function computeAttack(state, player) {
        var isActive = state.turn === player;
        if (isActive) {
            var mana = player === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            return mana.attack;
        }
        var predicted = 0;
        if (!state.table) return predicted;
        for (var i = 0; i < state.table.length; i++) {
            var card = state.table[i];
            if (card.owner !== player) continue;
            if (card.deadness !== 'alive') continue;
            if (card.delay > 0) continue;
            var meta = CARD_META[card.cardName];
            if (!meta) continue;
            if (card.constructionTime <= 1) predicted += (meta.autoAttack || 0);
            if (card.constructionTime === 0) predicted += (meta.abilityAttack || 0);
        }
        return predicted;
    }

    function computeDefense(state, player) {
        var total = 0;
        if (!state.table) return total;
        for (var i = 0; i < state.table.length; i++) {
            var card = state.table[i];
            if (card.owner !== player) continue;
            if (card.constructionTime > 0) continue;
            if (card.deadness !== 'alive') continue;
            if (card.blocking) total += card.health;
        }
        return total;
    }

    // -----------------------------------------------------------------------
    // Sort cards by type
    // -----------------------------------------------------------------------
    function sortCards(cards) {
        return cards.slice().sort(function(a, b) {
            if (a.cardName !== b.cardName) return a.cardName < b.cardName ? -1 : 1;
            if (a.constructionTime !== b.constructionTime) return b.constructionTime - a.constructionTime;
            return 0;
        });
    }

    // -----------------------------------------------------------------------
    // Draw a single card tile
    // -----------------------------------------------------------------------
    function drawCard(x, y, w, h, card, owner) {
        var meta = CARD_META[card.cardName] || {};
        var isConstruction = card.constructionTime > 0;
        var isDead = card.deadness !== 'alive';
        var isAssigned = card.role === 'assigned';

        var bgKey = owner === 1 ? 'bg_default_red' : 'bg_default';
        if (isDead) bgKey = 'bg_dead';
        else if (isConstruction) bgKey = 'bg_construction';
        else if (isAssigned || !card.blocking) bgKey = 'bg_assigned';

        if (images[bgKey]) {
            ctx.drawImage(images[bgKey], x, y, w, h);
        } else {
            ctx.fillStyle = isDead ? '#333' : isConstruction ? '#8B6914' : isAssigned ? '#555' : '#2244aa';
            ctx.fillRect(x, y, w, h);
        }

        var artKey = 'card_' + card.cardName;
        var artOffset = w / 5;
        var artSize = w - artOffset - 5;
        if (images[artKey]) {
            ctx.globalAlpha = isConstruction ? 0.6 : 1.0;
            ctx.drawImage(images[artKey], x + artOffset, y + artOffset, artSize, artSize);
            ctx.globalAlpha = 1.0;
        }

        ctx.fillStyle = '#fff';
        ctx.font = '12px Consolas, monospace';
        var displayName = card.cardName.length > 14 ? card.cardName.substring(0, 14) : card.cardName;
        ctx.fillText(displayName, x + artOffset + 6, y + 13);

        if (isConstruction) {
            var clockSize = w / 5;
            if (images['icon_clock']) ctx.drawImage(images['icon_clock'], x + 2, y + 14, clockSize, clockSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            ctx.fillText(String(card.constructionTime), x + 3, y + 14 + clockSize + 4);
        }

        if (!isConstruction && !isDead) {
            if (card.blocking && meta.canBlock) {
                var shieldKey = card.role === 'sellable' ? 'icon_shield_gold' : 'icon_shield_blue';
                if (images[shieldKey]) ctx.drawImage(images[shieldKey], x, y, w, h);
            } else if (meta.canBlock && !card.blocking) {
                if (images['icon_shield_white']) ctx.drawImage(images['icon_shield_white'], x, y, w, h);
            }
        }

        if (meta.attack > 0) {
            var iconSize = w / 3;
            var ax = x + artOffset + 2;
            var ay = y + h - iconSize - 2;
            if (images['icon_attack']) ctx.drawImage(images['icon_attack'], ax, ay, iconSize, iconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            var atkStr = String(meta.attack);
            var atkTextW = ctx.measureText(atkStr).width;
            ctx.fillText(atkStr, ax + (iconSize - atkTextW) / 2, ay + iconSize - 4);
        }

        if (card.health > 0) {
            var iconSz = w / 3;
            var dy = y + h - iconSz - 2;
            var dx = x + w - iconSz - 2;
            if (meta.isFragile) {
                if (images['icon_hp']) ctx.drawImage(images['icon_hp'], dx, dy, iconSz, iconSz);
            } else {
                if (images['icon_defend']) ctx.drawImage(images['icon_defend'], dx, dy, iconSz, iconSz);
            }
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            var hpStr = String(card.health);
            var hpTextW = ctx.measureText(hpStr).width;
            ctx.fillText(hpStr, dx + (iconSz - hpTextW) / 2, dy + iconSz - 4);
        }

        var statusY = y + w / 5 + 5;
        var statusIconSize = w / 5;
        var statusX = x + 2;

        if (card.lifespan > 0 && !isConstruction) {
            if (images['icon_doom']) ctx.drawImage(images['icon_doom'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.lifespan), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        if (card.delay > 0 && !isConstruction) {
            if (images['icon_delay']) ctx.drawImage(images['icon_delay'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.delay), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        if (card.disruptDamage > 0 && !isConstruction) {
            if (images['icon_tap']) ctx.drawImage(images['icon_tap'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.disruptDamage), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        if (meta.isFrontline && !isConstruction) {
            if (images['icon_undefendable']) ctx.drawImage(images['icon_undefendable'], statusX, statusY, statusIconSize, statusIconSize);
        }

        if (card.charge > 0 && !isConstruction) {
            var chargeKey = 'icon_charge' + Math.min(card.charge, 3);
            if (images[chargeKey]) ctx.drawImage(images[chargeKey], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.charge), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
        }
    }

    // -----------------------------------------------------------------------
    // Draw board
    // -----------------------------------------------------------------------
    function drawBoard() {
        if (!REPLAY) return;
        var W = canvas.width;
        var H = canvas.height;
        var state = REPLAY.states[stateIndex];

        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, W, H);

        var playX = BUY_PANE_WIDTH;
        var midY = H / 2;

        ctx.fillStyle = '#2e1a1a';
        ctx.fillRect(playX, 28, W - playX, midY - 28);
        var playW = W - BUY_PANE_WIDTH;
        var midX = playX + playW / 2;

        var scale = Math.min(1.0, (playW - 40) / (CARD_W * 12));
        var cw = CARD_W * scale;
        var ch = CARD_H * scale;
        var sameOverlap = SAME_OVERLAP * scale;
        var diffBuffer = DIFF_BUFFER_X * scale;

        var playerCards = [[], []];
        if (state.table) {
            for (var ti = 0; ti < state.table.length; ti++) {
                var tc = state.table[ti];
                if (tc.deadness === 'alive') playerCards[tc.owner].push(tc);
            }
        }

        playerCards[0] = sortCards(playerCards[0]);
        playerCards[1] = sortCards(playerCards[1]);

        var playerAreaH = H / 2 - 30;
        var bottomBuffer = 60;
        var laneSpacing = (playerAreaH - bottomBuffer - 3 * ch) / 4;

        for (var player = 0; player < 2; player++) {
            var cards = playerCards[player];
            var lanes = [[], [], []];
            for (var ci = 0; ci < cards.length; ci++) {
                var lane = getLane(cards[ci].cardName);
                lanes[lane].push(cards[ci]);
            }

            var laneY = [];
            for (var li = 0; li < 3; li++) {
                if (player === 1) {
                    laneY[li] = midY - (li + 1) * laneSpacing - (li + 1) * ch + 15;
                } else {
                    laneY[li] = midY + (li + 1) * laneSpacing + li * ch + 15;
                }
            }

            for (var laneIdx = 0; laneIdx < 3; laneIdx++) {
                var laneCards = lanes[laneIdx];
                if (laneCards.length === 0) continue;

                var totalWidth = cw;
                var lastCardName = laneCards[0].cardName;
                for (var lj = 1; lj < laneCards.length; lj++) {
                    if (laneCards[lj].cardName === lastCardName) {
                        totalWidth += cw + sameOverlap;
                    } else {
                        totalWidth += cw + diffBuffer;
                    }
                    lastCardName = laneCards[lj].cardName;
                }

                var lx = midX - totalWidth / 2;
                var ly = laneY[laneIdx];
                lastCardName = null;
                for (var lk = 0; lk < laneCards.length; lk++) {
                    var lc = laneCards[lk];
                    if (lk > 0) {
                        if (lc.cardName === lastCardName) {
                            lx += cw + sameOverlap;
                        } else {
                            lx += cw + diffBuffer;
                        }
                    }
                    drawCard(lx, ly, cw, ch, lc, player);
                    lastCardName = lc.cardName;
                }
            }

            // Resources
            var mana = player === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            var resIconSize = 22;
            var resY = player === 1 ? 50 : H - 18;
            var resStartX = playX + 10;
            var resParts = [
                { val: mana.gold, icon: 'res_gold', color: '#FFD700' },
                { val: mana.blue, icon: 'res_blue', color: '#4488ff' },
                { val: mana.green, icon: 'res_green', color: '#44dd44' },
                { val: mana.red, icon: 'res_red', color: '#ff4444' },
                { val: mana.energy, icon: 'res_energy', color: '#ff8800' }
            ];
            var rx = resStartX;
            ctx.font = 'bold 16px Consolas, monospace';
            for (var rpi = 0; rpi < resParts.length; rpi++) {
                var rp = resParts[rpi];
                if (images[rp.icon]) ctx.drawImage(images[rp.icon], rx, resY - resIconSize + 4, resIconSize, resIconSize);
                ctx.fillStyle = rp.color;
                ctx.fillText(String(rp.val), rx + resIconSize + 2, resY);
                rx += resIconSize + 30;
            }
        }

        // Attack/Defense indicators
        var p0atk = computeAttack(state, 0);
        var p1atk = computeAttack(state, 1);
        var p0def = computeDefense(state, 0);
        var p1def = computeDefense(state, 1);

        ctx.strokeStyle = '#444';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(playX + 20, midY);
        ctx.lineTo(W - 20, midY);
        ctx.stroke();

        ctx.font = 'bold 24px Consolas, monospace';
        var indXLeft = BUY_PANE_WIDTH + 15;
        var indXRight = W - 100;

        ctx.fillStyle = '#ff6644';
        ctx.fillText('\\u2694 ' + p1atk, indXLeft, midY - 8);
        ctx.fillStyle = '#4488ff';
        ctx.fillText('\\ud83d\\udee1 ' + p1def, indXRight, midY - 8);

        ctx.fillStyle = '#4488ff';
        ctx.fillText('\\ud83d\\udee1 ' + p0def, indXLeft, midY + 26);
        ctx.fillStyle = '#ff6644';
        ctx.fillText('\\u2694 ' + p0atk, indXRight, midY + 26);

        // Defense phase sword overlay
        if (state.phase === 'defense' || state.phase === 'confirm') {
            var defender = state.turn;
            var attacker = 1 - defender;
            var atkMana = attacker === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            if (atkMana.attack > 0) {
                var swordSize = 200;
                var centerXs = playX + (W - playX) / 2;
                var swordY = defender === 0
                    ? midY + (H - midY) / 2 - swordSize / 2
                    : midY / 2 - swordSize / 2 + 20;

                ctx.globalAlpha = 0.4;
                if (images['icon_attack']) ctx.drawImage(images['icon_attack'], centerXs - swordSize / 2, swordY, swordSize, swordSize);
                ctx.globalAlpha = 1.0;

                ctx.fillStyle = '#fff';
                ctx.font = 'bold 64px Consolas, monospace';
                var bigAtkStr = String(atkMana.attack);
                var bigAtkW = ctx.measureText(bigAtkStr).width;
                ctx.fillText(bigAtkStr, centerXs - bigAtkW / 2, swordY + swordSize / 2 + 22);
            }
        }

        drawBuyPane(state);
        drawHUD(state);
    }

    // -----------------------------------------------------------------------
    // Buy pane
    // -----------------------------------------------------------------------
    var BASE_SET_NAMES = {
        'Drone': 1, 'Engineer': 1, 'Blastforge': 1, 'Animus': 1, 'Conduit': 1,
        'Steelsplitter': 1, 'Wall': 1, 'Rhino': 1, 'Tarsier': 1, 'Forcefield': 1, 'Gauss Cannon': 1
    };

    function drawBuyPaneColumn(state, cards, indices, colX) {
        var H = canvas.height;
        var y = 30;
        var rowH = BUYABLE_ROW_H;
        var thumbSize = rowH - 4;
        var colW = BUY_COL_WIDTH;

        for (var j = 0; j < cards.length; j++) {
            var cardName = cards[j];
            var idx = indices[j];
            var meta = CARD_META[cardName] || {};

            ctx.fillStyle = (j % 2 === 0) ? '#181830' : '#1a1a35';
            ctx.fillRect(colX, y, colW, rowH);

            var artKey = 'card_' + cardName;
            if (images[artKey]) {
                ctx.globalAlpha = 0.8;
                ctx.drawImage(images[artKey], colX + colW - thumbSize - 2, y + 2, thumbSize, thumbSize);
                ctx.globalAlpha = 1.0;
            }

            ctx.fillStyle = '#ddd';
            ctx.font = '13px Consolas, monospace';
            var shortName = cardName.length > 14 ? cardName.substring(0, 14) : cardName;
            ctx.fillText(shortName, colX + 4, y + 15);

            if (meta.buyCost) {
                var cx = colX + 4;
                var costY = y + 20;
                var costIconSize = 14;
                var goldAmount = '';
                var costParts = [];
                for (var ci = 0; ci < meta.buyCost.length; ci++) {
                    var bch = meta.buyCost[ci];
                    if (bch >= '0' && bch <= '9') {
                        goldAmount += bch;
                    } else {
                        if (goldAmount) { costParts.push({ type: 'gold', val: parseInt(goldAmount) }); goldAmount = ''; }
                        costParts.push({ type: bch });
                    }
                }
                if (goldAmount) costParts.push({ type: 'gold', val: parseInt(goldAmount) });

                for (var cpi = 0; cpi < costParts.length; cpi++) {
                    var part = costParts[cpi];
                    var iconKey = null;
                    switch (part.type) {
                        case 'gold': iconKey = 'res_gold'; break;
                        case 'B': iconKey = 'res_blue'; break;
                        case 'G': iconKey = 'res_green'; break;
                        case 'C': iconKey = 'res_red'; break;
                        case 'H': iconKey = 'res_energy'; break;
                    }
                    if (iconKey && images[iconKey]) {
                        if (part.type === 'gold') {
                            ctx.drawImage(images[iconKey], cx, costY, costIconSize, costIconSize);
                            ctx.fillStyle = '#FFD700';
                            ctx.font = 'bold 12px Consolas, monospace';
                            ctx.fillText(String(part.val), cx + costIconSize + 1, costY + costIconSize - 2);
                            cx += costIconSize + 16;
                        } else {
                            ctx.drawImage(images[iconKey], cx, costY, costIconSize, costIconSize);
                            cx += costIconSize + 3;
                        }
                    }
                }
            }

            // Supply bar
            var whiteTotal = state.whiteTotalSupply ? state.whiteTotalSupply[idx] : 0;
            var blackTotal = state.blackTotalSupply ? state.blackTotalSupply[idx] : 0;
            var whiteSpent = state.whiteSupplySpent ? state.whiteSupplySpent[idx] : 0;
            var blackSpent = state.blackSupplySpent ? state.blackSupplySpent[idx] : 0;
            var whiteRemain = whiteTotal - whiteSpent;
            var blackRemain = blackTotal - blackSpent;
            var maxSupply = Math.max(whiteTotal, blackTotal, 1);

            var barX = colX + 4;
            var barY = y + rowH - 12;
            var barW = colW - thumbSize - 12;
            var pipW = Math.max(2, (barW / maxSupply) - 1);

            for (var s = 0; s < maxSupply; s++) {
                var px = barX + s * (pipW + 1);
                ctx.fillStyle = s < whiteRemain ? '#44dd44' : '#222';
                ctx.fillRect(px, barY, pipW, 3);
                ctx.fillStyle = s < blackRemain ? '#ff4444' : '#222';
                ctx.fillRect(px, barY + 4, pipW, 3);
            }

            y += rowH;
            if (y + rowH > H) break;
        }
    }

    function drawBuyPane(state) {
        var H = canvas.height;
        ctx.fillStyle = '#111122';
        ctx.fillRect(0, 0, BUY_PANE_WIDTH, H);

        if (!state.cards) return;

        var baseCards = [];
        var baseIndices = [];
        var addCards = [];
        var addIndices = [];

        for (var i = 0; i < state.cards.length; i++) {
            if (BASE_SET_NAMES[state.cards[i]]) {
                baseCards.push(state.cards[i]);
                baseIndices.push(i);
            } else {
                addCards.push(state.cards[i]);
                addIndices.push(i);
            }
        }

        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(BUY_COL_WIDTH, 30);
        ctx.lineTo(BUY_COL_WIDTH, H);
        ctx.stroke();

        drawBuyPaneColumn(state, baseCards, baseIndices, 0);
        drawBuyPaneColumn(state, addCards, addIndices, BUY_COL_WIDTH);
    }

    // -----------------------------------------------------------------------
    // HUD
    // -----------------------------------------------------------------------
    function drawHUD(state) {
        var W = canvas.width;
        var H = canvas.height;

        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(BUY_PANE_WIDTH, 0, W - BUY_PANE_WIDTH, 28);

        var turnStr = '\\u2191 ' + REPLAY.p1 + ' vs ' + REPLAY.p0 + ' \\u2193';

        if (REPLAY.turnBoundaries && REPLAY.turnBoundaries.length > 0) {
            var turnIdx = 0;
            for (var i = 1; i < REPLAY.turnBoundaries.length; i++) {
                if (REPLAY.turnBoundaries[i] <= stateIndex) turnIdx = i;
                else break;
            }
            var turnStart = REPLAY.turnBoundaries[turnIdx];
            var turnEnd = (turnIdx + 1 < REPLAY.turnBoundaries.length) ? REPLAY.turnBoundaries[turnIdx + 1] : totalStates;
            var actionInTurn = stateIndex - turnStart + 1;
            var actionsInTurn = turnEnd - turnStart;

            turnStr += '   Turn ' + (turnIdx + 1) + '/' + REPLAY.turns;
            turnStr += '   [' + actionInTurn + '/' + actionsInTurn + ']';

            if (REPLAY.actions && stateIndex < REPLAY.actions.length) {
                turnStr += '   ' + REPLAY.actions[stateIndex];
            }
        }

        turnStr += '   Winner: ' + REPLAY.winnerName;

        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 16px Consolas, monospace';
        ctx.fillText(turnStr, BUY_PANE_WIDTH + 10, 20);

        // Player name labels
        ctx.font = 'bold 14px Consolas, monospace';
        var stepStr = 'Step ' + stateIndex + '/' + (totalStates - 1);
        var stepW = ctx.measureText(stepStr).width;
        var stepX = W - stepW - 10;

        ctx.fillStyle = '#ff8866';
        var p1Label = REPLAY.p1;
        var p1LabelW = ctx.measureText(p1Label).width;
        ctx.fillText(p1Label, stepX - p1LabelW - 15, 20);

        ctx.fillStyle = '#888';
        ctx.font = '14px Consolas, monospace';
        ctx.fillText(stepStr, stepX, 20);

        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(stepX - p1LabelW - 25, H - 28, W - stepX + p1LabelW + 25, 28);
        ctx.font = 'bold 14px Consolas, monospace';
        ctx.fillStyle = '#6688ff';
        var p0Label = REPLAY.p0;
        var p0LabelW = ctx.measureText(p0Label).width;
        ctx.fillText(p0Label, stepX - p0LabelW - 15, H - 10);
        ctx.fillStyle = '#888';
        ctx.font = '14px Consolas, monospace';
        ctx.fillText(stepStr, stepX, H - 10);

        // Phase label
        var phaseLabels = {
            'action': 'ACTION PHASE',
            'defense': 'DEFENSE PHASE - ASSIGN BLOCKERS',
            'confirm': 'CONFIRM PHASE',
            'breach': 'BREACH PHASE'
        };
        var phaseText = phaseLabels[state.phase] || (state.phase ? state.phase.toUpperCase() : '');
        ctx.font = 'bold 16px Consolas, monospace';
        ctx.fillStyle = '#fff';
        var phaseW = ctx.measureText(phaseText).width;
        var phaseCenterX = BUY_PANE_WIDTH + (W - BUY_PANE_WIDTH) / 2;
        var phaseY = state.turn === 1 ? 46 : H - 10;
        ctx.fillText(phaseText, phaseCenterX - phaseW / 2, phaseY);

        // Controls hint
        ctx.fillStyle = '#555';
        ctx.font = '11px Consolas, monospace';
        var hints = [
            'Right/Space: Next Action',
            'Left/Z:      Prev Action',
            'Up:          Next Turn',
            'Down:        Prev Turn',
            'Home/End:    Start/End'
        ];
        var hintY = H - 80;
        for (var hi = 0; hi < hints.length; hi++) {
            ctx.fillText(hints[hi], BUY_COL_WIDTH + 4, hintY + hi * 14);
        }
    }

    // -----------------------------------------------------------------------
    // Navigation
    // -----------------------------------------------------------------------
    function getCurrentTurnIndex() {
        if (!REPLAY || !REPLAY.turnBoundaries || REPLAY.turnBoundaries.length === 0) return stateIndex;
        var turnIdx = 0;
        for (var i = 1; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] <= stateIndex) turnIdx = i;
            else break;
        }
        return turnIdx;
    }

    function jumpToNextTurn() {
        if (!REPLAY || !REPLAY.turnBoundaries) return;
        for (var i = 0; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] > stateIndex) {
                stateIndex = REPLAY.turnBoundaries[i];
                return;
            }
        }
    }

    function jumpToPrevTurn() {
        if (!REPLAY || !REPLAY.turnBoundaries) return;
        var currentTurn = getCurrentTurnIndex();
        if (currentTurn > 0) {
            stateIndex = REPLAY.turnBoundaries[currentTurn - 1];
        } else {
            stateIndex = 0;
        }
    }

    // -----------------------------------------------------------------------
    // Keyboard handling
    // -----------------------------------------------------------------------
    document.addEventListener('keydown', function(e) {
        if (!REPLAY) return;
        var changed = false;
        switch (e.key) {
            case 'ArrowRight':
            case ' ':
                if (e.ctrlKey) { jumpToNextTurn(); changed = true; }
                else if (stateIndex < totalStates - 1) { stateIndex++; changed = true; }
                break;
            case 'ArrowLeft':
            case 'z':
            case 'Z':
                if (e.ctrlKey) { jumpToPrevTurn(); changed = true; }
                else if (stateIndex > 0) { stateIndex--; changed = true; }
                break;
            case 'ArrowUp':
                jumpToNextTurn(); changed = true;
                break;
            case 'ArrowDown':
                jumpToPrevTurn(); changed = true;
                break;
            case 'Home':
                stateIndex = 0; changed = true;
                break;
            case 'End':
                stateIndex = totalStates - 1; changed = true;
                break;
        }
        if (changed) {
            e.preventDefault();
            drawBoard();
        }
    });

    // -----------------------------------------------------------------------
    // Resize
    // -----------------------------------------------------------------------
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        drawBoard();
    }

    window.addEventListener('resize', resize);

    // -----------------------------------------------------------------------
    // Init — load images then show dropzone
    // -----------------------------------------------------------------------
    loadImages(function() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
})();
</script>
</body>
</html>`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
    const args = process.argv.slice(2);
    const outputPath = args[0] || path.join(BIN_DIR, 'prismata_replay_viewer.html');

    console.error('Building self-contained replay viewer...');
    console.error('Bundling engine modules...');
    const moduleBundle = buildModuleBundle();

    console.error('Loading card library...');
    const cardLibrary = JSON.parse(fs.readFileSync(CARD_LIBRARY_PATH, 'utf-8'));
    const cardMeta = buildCardMetadata(cardLibrary);

    console.error('Embedding assets (this takes a moment)...');
    const assets = collectAllAssets(cardLibrary);

    console.error('Generating HTML...');
    const html = buildHTML(moduleBundle, assets, cardMeta);

    fs.writeFileSync(outputPath, html, 'utf-8');
    const sizeMB = (Buffer.byteLength(html, 'utf-8') / 1024 / 1024).toFixed(1);
    console.error('Written: ' + outputPath + ' (' + sizeMB + ' MB)');
}

main();
