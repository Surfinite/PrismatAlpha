'use strict';

/**
 * replay_to_html.js — Generate a self-contained HTML replay viewer from a replay JSON file.
 *
 * Usage:
 *   node js_engine/replay_to_html.js <replay.json> [output.html]
 *
 * Reads a replay JSON (produced by matchup_clean.js --save-replays), embeds card art,
 * UI textures, and game state data into a single HTML file viewable in any browser.
 *
 * Keyboard controls in the viewer:
 *   Left/Right — step through actions
 *   Up/Down    — jump between turns
 *   Home/End   — jump to start/end
 */

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const BIN_DIR = path.join(__dirname, '..', 'bin');
const CARD_ART_DIR = path.join(BIN_DIR, 'asset', 'images', 'cards');
const CARD_BG_DIR = path.join(BIN_DIR, 'asset', 'images', 'cardbg');
const ICON_STATUS_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'status');
const ICON_RESOURCE_DIR = path.join(BIN_DIR, 'asset', 'images', 'icons', 'resource');
const CARD_LIBRARY_PATH = path.join(BIN_DIR, 'asset', 'config', 'cardLibrary.jso');

// ---------------------------------------------------------------------------
// Display name mapping — rename internal AI names for public-facing replays
// ---------------------------------------------------------------------------
const DISPLAY_NAMES = { 'LiveHardestAI': 'HardestAI' };
function displayName(name) { return DISPLAY_NAMES[name] || name; }

// ---------------------------------------------------------------------------
// Card metadata extraction from cardLibrary.jso
// ---------------------------------------------------------------------------

function buildCardMetadata(cardLibrary, usedCardNames) {
    // cardLibrary keys are internal names, but replay JSON uses UIName (display names).
    // Build a map: UIName -> { lane properties, attack, cost, etc. }
    const byUIName = {};

    for (const [internalName, card] of Object.entries(cardLibrary)) {
        const uiName = card.UIName || internalName;
        if (!usedCardNames.has(uiName)) continue;

        // Determine attack: auto-attack from beginOwnTurnScript, ability-attack from abilityScript
        let autoAttack = 0;
        let abilityAttack = 0;
        if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
            for (const ch of card.beginOwnTurnScript.receive) {
                if (ch === 'A') autoAttack++;
            }
        }
        if (card.abilityScript && card.abilityScript.receive) {
            for (const ch of card.abilityScript.receive) {
                if (ch === 'A') abilityAttack++;
            }
        }
        const attack = autoAttack + abilityAttack;

        // Lane assignment properties (matching GUICard::getLane())
        const hasAbility = !!(card.abilityScript || card.targetAction);
        const hasTargetAbility = !!card.targetAction;
        const isFrontline = !!card.undefendable;
        const canBlock = !!card.defaultBlocking;
        const isFragile = !!card.fragile;

        byUIName[uiName] = {
            attack,
            autoAttack,
            abilityAttack,
            toughness: card.toughness || 0,
            hasAbility,
            hasTargetAbility,
            isFrontline,
            canBlock,
            isFragile,
            defaultBlocking: !!card.defaultBlocking,
            assignedBlocking: card.assignedBlocking !== undefined ? !!card.assignedBlocking : !!card.defaultBlocking,
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
// Asset embedding (base64)
// ---------------------------------------------------------------------------

function readImageBase64(filePath) {
    if (!fs.existsSync(filePath)) {
        console.error(`Warning: image not found: ${filePath}`);
        return null;
    }
    const buf = fs.readFileSync(filePath);
    return 'data:image/png;base64,' + buf.toString('base64');
}

function collectAssets(usedCardNames) {
    const assets = {};

    // Card art
    for (const name of usedCardNames) {
        const artPath = path.join(CARD_ART_DIR, name + '.png');
        const data = readImageBase64(artPath);
        if (data) assets['card_' + name] = data;
    }

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

    return assets;
}

// ---------------------------------------------------------------------------
// Determine all card names used across all states
// ---------------------------------------------------------------------------

function findUsedCardNames(replay) {
    const names = new Set();

    // Cards from the card set (buyable units)
    if (replay.cardSet) replay.cardSet.forEach(n => names.add(n));

    // Base set cards that appear in any state
    for (const state of replay.states) {
        if (state.cards) state.cards.forEach(n => names.add(n));
        if (state.table) {
            for (const card of state.table) {
                names.add(card.cardName);
            }
        }
    }

    return names;
}

// ---------------------------------------------------------------------------
// HTML template with embedded renderer
// ---------------------------------------------------------------------------

function buildHTML(replay, assets, cardMeta) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${displayName(replay.p0)} vs ${displayName(replay.p1)} — Prismata Replay</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a2e; overflow: hidden; font-family: Consolas, monospace; }
canvas { display: block; }
</style>
</head>
<body>
<canvas id="board"></canvas>
<script>
// === EMBEDDED DATA ===
const REPLAY = ${JSON.stringify({
        p0: displayName(replay.p0),
        p1: displayName(replay.p1),
        winner: replay.winner,
        winnerName: displayName(replay.winnerName),
        turns: replay.turns,
        cardSet: replay.cardSet,
        states: replay.states,
        actions: replay.actions,
        turnBoundaries: replay.turnBoundaries
    })};

const CARD_META = ${JSON.stringify(cardMeta)};

// === EMBEDDED ASSETS ===
const ASSET_DATA = ${JSON.stringify(assets)};

// === RENDERER ===
(function() {
    const canvas = document.getElementById('board');
    const ctx = canvas.getContext('2d');

    // State
    let stateIndex = 0;
    const totalStates = REPLAY.states.length;

    // Images (loaded from base64)
    const images = {};
    let imagesLoaded = 0;
    let totalImages = 0;

    function loadImages(callback) {
        const keys = Object.keys(ASSET_DATA);
        totalImages = keys.length;
        if (totalImages === 0) { callback(); return; }
        for (const key of keys) {
            const img = new Image();
            img.onload = function() {
                imagesLoaded++;
                if (imagesLoaded >= totalImages) callback();
            };
            img.onerror = function() {
                imagesLoaded++;
                if (imagesLoaded >= totalImages) callback();
            };
            img.src = ASSET_DATA[key];
            images[key] = img;
        }
    }

    // ---------------------------------------------------------------------------
    // Layout constants (matching C++ GUI proportions)
    // ---------------------------------------------------------------------------
    const BUY_COL_WIDTH = 200;
    const BUY_PANE_WIDTH = BUY_COL_WIDTH * 2; // two columns: base set + additional
    const CARD_W = 110;
    const CARD_H = 110;
    const BUYABLE_ROW_H = 60;
    const SAME_OVERLAP = -CARD_W * 4 / 5;   // same-type cards overlap 80%
    const DIFF_BUFFER_X = CARD_W / 5;        // different-type gap

    // ---------------------------------------------------------------------------
    // Lane assignment (GUICard::getLane)
    // ---------------------------------------------------------------------------
    function getLane(cardName) {
        const meta = CARD_META[cardName];
        if (!meta) return 1; // default to middle lane
        if (meta.isFrontline) return 0;
        if (meta.hasAbility || meta.hasTargetAbility) return 1;
        if (meta.canBlock) return 0;
        return 2;
    }

    // ---------------------------------------------------------------------------
    // Parse mana string into resource object
    // ---------------------------------------------------------------------------
    function parseMana(manaStr) {
        const res = { gold: 0, blue: 0, green: 0, red: 0, energy: 0, attack: 0 };
        if (!manaStr) return res;
        let numBuf = '';
        for (const ch of manaStr) {
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

    // ---------------------------------------------------------------------------
    // Compute attack totals — matches GUIState_Play.cpp:675-687
    // Active player: current attack from mana resources
    // Inactive player: predict next-turn attack from card abilities
    // ---------------------------------------------------------------------------
    function computeAttack(state, player) {
        const isActive = state.turn === player;
        if (isActive) {
            // Active player: attack is the 'A' count in their mana string
            const mana = player === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            return mana.attack;
        }
        // Inactive player: predict next-turn attack (approximates PredictEnemyNextTurn).
        // At start of their turn: construction ticks down (const 1→0), beginOwnTurnScript
        // fires (autoAttack), and abilities become usable (abilityAttack).
        let predicted = 0;
        if (!state.table) return predicted;
        for (const card of state.table) {
            if (card.owner !== player) continue;
            if (card.deadness !== 'alive') continue;
            if (card.delay > 0) continue;
            const meta = CARD_META[card.cardName];
            if (!meta) continue;
            if (card.constructionTime <= 1) {
                // Ready now or finishing next turn — autoAttack will fire
                predicted += (meta.autoAttack || 0);
            }
            if (card.constructionTime === 0) {
                // Already ready — can use ability next turn
                predicted += (meta.abilityAttack || 0);
            }
        }
        return predicted;
    }

    // ---------------------------------------------------------------------------
    // Compute defense totals from table
    // ---------------------------------------------------------------------------
    function computeDefense(state, player) {
        let total = 0;
        if (!state.table) return total;
        for (const card of state.table) {
            if (card.owner !== player) continue;
            if (card.constructionTime > 0) continue;
            if (card.deadness !== 'alive') continue;
            if (card.blocking) {
                total += card.health;
            }
        }
        return total;
    }

    // ---------------------------------------------------------------------------
    // Sort cards by type (matching GUICard sort: type ID, then construction time, then ID)
    // We sort by cardName as proxy for typeID, then constructionTime desc
    // ---------------------------------------------------------------------------
    function sortCards(cards) {
        return cards.slice().sort((a, b) => {
            if (a.cardName !== b.cardName) return a.cardName < b.cardName ? -1 : 1;
            if (a.constructionTime !== b.constructionTime) return b.constructionTime - a.constructionTime;
            return 0;
        });
    }

    // ---------------------------------------------------------------------------
    // Draw a single card tile
    // ---------------------------------------------------------------------------
    function drawCard(x, y, w, h, card, owner) {
        const meta = CARD_META[card.cardName] || {};
        const isConstruction = card.constructionTime > 0;
        const isDead = card.deadness !== 'alive';
        const isAssigned = card.role === 'assigned';

        // Background — P1 (top) uses red, P0 (bottom) uses blue
        let bgKey = owner === 1 ? 'bg_default_red' : 'bg_default';
        if (isDead) bgKey = 'bg_dead';
        else if (isConstruction) bgKey = 'bg_construction';
        else if (isAssigned || !card.blocking) bgKey = 'bg_assigned';

        if (images[bgKey]) {
            ctx.drawImage(images[bgKey], x, y, w, h);
        } else {
            ctx.fillStyle = isDead ? '#333' : isConstruction ? '#8B6914' : isAssigned ? '#555' : '#2244aa';
            ctx.fillRect(x, y, w, h);
        }

        // Card art
        const artKey = 'card_' + card.cardName;
        const artOffset = w / 5;
        const artSize = w - artOffset - 5;
        if (images[artKey]) {
            ctx.globalAlpha = isConstruction ? 0.6 : 1.0;
            ctx.drawImage(images[artKey], x + artOffset, y + artOffset, artSize, artSize);
            ctx.globalAlpha = 1.0;
        }

        // Card name (offset right to avoid shield icon overlap)
        ctx.fillStyle = '#fff';
        ctx.font = '12px Consolas, monospace';
        const displayName = card.cardName.length > 14 ? card.cardName.substring(0, 14) : card.cardName;
        ctx.fillText(displayName, x + artOffset + 6, y + 13);

        // Construction time overlay — small clock icon with number below
        if (isConstruction) {
            const clockSize = w / 5;
            if (images['icon_clock']) {
                ctx.drawImage(images['icon_clock'], x + 2, y + 14, clockSize, clockSize);
            }
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            ctx.fillText(String(card.constructionTime), x + 3, y + 14 + clockSize + 4);
        }

        // Shield icon (blocker status)
        if (!isConstruction && !isDead) {
            if (card.blocking && meta.canBlock) {
                // Ready blocker — blue or gold shield
                const shieldKey = card.role === 'sellable' ? 'icon_shield_gold' : 'icon_shield_blue';
                if (images[shieldKey]) {
                    ctx.drawImage(images[shieldKey], x, y, w, h);
                }
            } else if (meta.canBlock && !card.blocking) {
                // Exhausted blocker — white shield
                if (images['icon_shield_white']) {
                    ctx.drawImage(images['icon_shield_white'], x, y, w, h);
                }
            }
        }

        // Attack value (bottom-left) — number overlapping icon
        if (meta.attack > 0) {
            const iconSize = w / 3;
            const ax = x + artOffset + 2;
            const ay = y + h - iconSize - 2;
            if (images['icon_attack']) ctx.drawImage(images['icon_attack'], ax, ay, iconSize, iconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            const atkStr = String(meta.attack);
            const atkTextW = ctx.measureText(atkStr).width;
            ctx.fillText(atkStr, ax + (iconSize - atkTextW) / 2, ay + iconSize - 4);
        }

        // HP/Defense value (bottom-right) — number overlapping icon
        if (card.health > 0) {
            const iconSize = w / 3;
            const dy = y + h - iconSize - 2;
            const dx = x + w - iconSize - 2;
            if (meta.isFragile) {
                if (images['icon_hp']) ctx.drawImage(images['icon_hp'], dx, dy, iconSize, iconSize);
            } else {
                if (images['icon_defend']) ctx.drawImage(images['icon_defend'], dx, dy, iconSize, iconSize);
            }
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 16px Consolas, monospace';
            const hpStr = String(card.health);
            const hpTextW = ctx.measureText(hpStr).width;
            ctx.fillText(hpStr, dx + (iconSize - hpTextW) / 2, dy + iconSize - 4);
        }

        // Status icons (stacked vertically from top-left)
        let statusY = y + w / 5 + 5;
        const statusIconSize = w / 5;
        const statusX = x + 2;

        // Lifespan (doom)
        if (card.lifespan > 0 && !isConstruction) {
            if (images['icon_doom']) ctx.drawImage(images['icon_doom'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.lifespan), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        // Delay
        if (card.delay > 0 && !isConstruction) {
            if (images['icon_delay']) ctx.drawImage(images['icon_delay'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.delay), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        // Chill (disruptDamage)
        if (card.disruptDamage > 0 && !isConstruction) {
            if (images['icon_tap']) ctx.drawImage(images['icon_tap'], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.disruptDamage), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
            statusY += statusIconSize + 3;
        }

        // Frontline
        if (meta.isFrontline && !isConstruction) {
            if (images['icon_undefendable']) ctx.drawImage(images['icon_undefendable'], statusX, statusY, statusIconSize, statusIconSize);
        }

        // Charge
        if (card.charge > 0 && !isConstruction) {
            const chargeKey = 'icon_charge' + Math.min(card.charge, 3);
            if (images[chargeKey]) ctx.drawImage(images[chargeKey], statusX, statusY, statusIconSize, statusIconSize);
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Consolas, monospace';
            ctx.fillText(String(card.charge), statusX + statusIconSize + 2, statusY + statusIconSize - 3);
        }
    }

    // ---------------------------------------------------------------------------
    // Draw board layout with lanes
    // ---------------------------------------------------------------------------
    function drawBoard() {
        const W = canvas.width;
        const H = canvas.height;
        const state = REPLAY.states[stateIndex];

        // Clear — bottom half dark blue, top half dark red
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, W, H);

        // Play area dimensions
        const playX = BUY_PANE_WIDTH;
        const midY = H / 2;

        // Top half (P1) dark red tint
        ctx.fillStyle = '#2e1a1a';
        ctx.fillRect(playX, 28, W - playX, midY - 28);
        const playW = W - BUY_PANE_WIDTH;
        const midX = playX + playW / 2;

        // Scale card size to fit
        const scale = Math.min(1.0, (playW - 40) / (CARD_W * 12));
        const cw = CARD_W * scale;
        const ch = CARD_H * scale;
        const sameOverlap = SAME_OVERLAP * scale;
        const diffBuffer = DIFF_BUFFER_X * scale;

        // Separate cards by player
        const playerCards = [[], []];
        if (state.table) {
            for (const card of state.table) {
                if (card.deadness === 'alive') {
                    playerCards[card.owner].push(card);
                }
            }
        }

        // Sort each player's cards
        playerCards[0] = sortCards(playerCards[0]);
        playerCards[1] = sortCards(playerCards[1]);

        // Lane spacing
        const playerAreaH = H / 2 - 30; // leave space for HUD
        const bottomBuffer = 60;
        const laneSpacing = (playerAreaH - bottomBuffer - 3 * ch) / 4;

        // Draw each player's cards
        for (let player = 0; player < 2; player++) {
            const cards = playerCards[player];

            // Assign cards to lanes
            const lanes = [[], [], []];
            for (const card of cards) {
                const lane = getLane(card.cardName);
                lanes[lane].push(card);
            }

            // Calculate lane Y positions
            // Player 1 (top): lane 0 nearest center (bottom of top half)
            // Player 0 (bottom): lane 0 nearest center (top of bottom half)
            const laneY = [];
            for (let i = 0; i < 3; i++) {
                if (player === 1) {
                    // Top player: lanes go up from center
                    laneY[i] = midY - (i + 1) * laneSpacing - (i + 1) * ch + 15;
                } else {
                    // Bottom player: lanes go down from center
                    laneY[i] = midY + (i + 1) * laneSpacing + i * ch + 15;
                }
            }

            // Draw each lane
            for (let laneIdx = 0; laneIdx < 3; laneIdx++) {
                const laneCards = lanes[laneIdx];
                if (laneCards.length === 0) continue;

                // Calculate total width of this lane
                let totalWidth = cw; // first card
                let lastCardName = laneCards[0].cardName;
                for (let j = 1; j < laneCards.length; j++) {
                    if (laneCards[j].cardName === lastCardName) {
                        totalWidth += cw + sameOverlap;
                    } else {
                        totalWidth += cw + diffBuffer;
                    }
                    lastCardName = laneCards[j].cardName;
                }

                // Center the lane in play area
                let x = midX - totalWidth / 2;
                const y = laneY[laneIdx];

                lastCardName = null;
                for (let j = 0; j < laneCards.length; j++) {
                    const card = laneCards[j];
                    if (j > 0) {
                        if (card.cardName === lastCardName) {
                            x += cw + sameOverlap;
                        } else {
                            x += cw + diffBuffer;
                        }
                    }
                    drawCard(x, y, cw, ch, card, player);
                    lastCardName = card.cardName;
                }
            }

            // Resources — draw icon + number for each resource type
            const mana = player === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            const resIconSize = 22;
            const resY = player === 1 ? 50 : H - 18;
            const resStartX = playX + 10;
            const resParts = [
                { val: mana.gold, icon: 'res_gold', color: '#FFD700' },
                { val: mana.blue, icon: 'res_blue', color: '#4488ff' },
                { val: mana.green, icon: 'res_green', color: '#44dd44' },
                { val: mana.red, icon: 'res_red', color: '#ff4444' },
                { val: mana.energy, icon: 'res_energy', color: '#ff8800' }
            ];
            let rx = resStartX;
            ctx.font = 'bold 16px Consolas, monospace';
            for (const r of resParts) {
                if (images[r.icon]) {
                    ctx.drawImage(images[r.icon], rx, resY - resIconSize + 4, resIconSize, resIconSize);
                }
                ctx.fillStyle = r.color;
                ctx.fillText(String(r.val), rx + resIconSize + 2, resY);
                rx += resIconSize + 30;
            }
        }

        // ---------------------------------------------------------------------------
        // Attack/Defense indicators at center
        // ---------------------------------------------------------------------------
        const p0atk = computeAttack(state, 0);
        const p1atk = computeAttack(state, 1);
        const p0def = computeDefense(state, 0);
        const p1def = computeDefense(state, 1);

        // Center divider line
        ctx.strokeStyle = '#444';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(playX + 20, midY);
        ctx.lineTo(W - 20, midY);
        ctx.stroke();

        // P1 attack (left, near additional units col) | P1 defense (right, near screen edge)
        // P0 defense (left, near additional units col) | P0 attack (right, near screen edge)
        ctx.font = 'bold 24px Consolas, monospace';
        const indXLeft = BUY_PANE_WIDTH + 15;   // near the additional units column
        const indXRight = W - 100;               // near right edge of screen

        // Above center
        ctx.fillStyle = '#ff6644';
        ctx.fillText('⚔ ' + p1atk, indXLeft, midY - 8);
        ctx.fillStyle = '#4488ff';
        ctx.fillText('🛡 ' + p1def, indXRight, midY - 8);

        // Below center
        ctx.fillStyle = '#4488ff';
        ctx.fillText('🛡 ' + p0def, indXLeft, midY + 26);
        ctx.fillStyle = '#ff6644';
        ctx.fillText('⚔ ' + p0atk, indXRight, midY + 26);

        // ---------------------------------------------------------------------------
        // Defense phase: big sword overlay showing remaining incoming attack
        // Matches GUIState_Play.cpp:651-674 — TexAttackBig drawn during Defense/Breach
        // ---------------------------------------------------------------------------
        if (state.phase === 'defense' || state.phase === 'confirm') {
            // The defending player is the active player (turn owner)
            const defender = state.turn;
            const attacker = 1 - defender;
            const incomingAttack = computeAttack(state, attacker);
            // Only draw if there's actual incoming attack (mana 'A' from attacker)
            const atkMana = attacker === 0 ? parseMana(state.whiteMana) : parseMana(state.blackMana);
            if (atkMana.attack > 0) {
                // Position sword on the defender's side of the board
                const swordSize = 200;
                const centerX = playX + (W - playX) / 2;
                const swordY = defender === 0
                    ? midY + (H - midY) / 2 - swordSize / 2    // P0 bottom half
                    : midY / 2 - swordSize / 2 + 20;           // P1 top half

                // Draw sword icon at 40% opacity
                ctx.globalAlpha = 0.4;
                if (images['icon_attack']) {
                    ctx.drawImage(images['icon_attack'], centerX - swordSize / 2, swordY, swordSize, swordSize);
                }
                ctx.globalAlpha = 1.0;

                // Draw remaining attack number — large, white, centered on sword
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 64px Consolas, monospace';
                const atkStr = String(atkMana.attack);
                const atkTextW = ctx.measureText(atkStr).width;
                ctx.fillText(atkStr, centerX - atkTextW / 2, swordY + swordSize / 2 + 22);
            }
        }

        // ---------------------------------------------------------------------------
        // Buy pane sidebar
        // ---------------------------------------------------------------------------
        drawBuyPane(state);

        // ---------------------------------------------------------------------------
        // HUD
        // ---------------------------------------------------------------------------
        drawHUD(state);
    }

    // ---------------------------------------------------------------------------
    // Buy pane
    // ---------------------------------------------------------------------------
    // Base set card names (the 11 standard units always available)
    const BASE_SET_NAMES = new Set([
        'Drone', 'Engineer', 'Blastforge', 'Animus', 'Conduit',
        'Steelsplitter', 'Wall', 'Rhino', 'Tarsier', 'Forcefield', 'Gauss Cannon'
    ]);

    function drawBuyPaneColumn(state, cards, indices, colX) {
        const H = canvas.height;
        let y = 30; // leave room for HUD
        const rowH = BUYABLE_ROW_H;
        const thumbSize = rowH - 4;
        const colW = BUY_COL_WIDTH;

        for (let j = 0; j < cards.length; j++) {
            const cardName = cards[j];
            const i = indices[j]; // original index into state.cards for supply lookup
            const meta = CARD_META[cardName] || {};

            // Row background
            ctx.fillStyle = (j % 2 === 0) ? '#181830' : '#1a1a35';
            ctx.fillRect(colX, y, colW, rowH);

            // Card thumbnail (right side)
            const artKey = 'card_' + cardName;
            if (images[artKey]) {
                ctx.globalAlpha = 0.8;
                ctx.drawImage(images[artKey], colX + colW - thumbSize - 2, y + 2, thumbSize, thumbSize);
                ctx.globalAlpha = 1.0;
            }

            // Card name
            ctx.fillStyle = '#ddd';
            ctx.font = '13px Consolas, monospace';
            const shortName = cardName.length > 14 ? cardName.substring(0, 14) : cardName;
            ctx.fillText(shortName, colX + 4, y + 15);

            // Buy cost — use resource icons
            if (meta.buyCost) {
                let cx = colX + 4;
                const costY = y + 20;
                const costIconSize = 14;
                // Parse cost string: digits are gold amount, letters are resource types
                let goldAmount = '';
                const costParts = [];
                for (const ch of meta.buyCost) {
                    if (ch >= '0' && ch <= '9') {
                        goldAmount += ch;
                    } else {
                        if (goldAmount) {
                            costParts.push({ type: 'gold', val: parseInt(goldAmount) });
                            goldAmount = '';
                        }
                        costParts.push({ type: ch });
                    }
                }
                if (goldAmount) costParts.push({ type: 'gold', val: parseInt(goldAmount) });

                for (const part of costParts) {
                    let iconKey = null;
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
            const whiteTotal = state.whiteTotalSupply ? state.whiteTotalSupply[i] : 0;
            const blackTotal = state.blackTotalSupply ? state.blackTotalSupply[i] : 0;
            const whiteSpent = state.whiteSupplySpent ? state.whiteSupplySpent[i] : 0;
            const blackSpent = state.blackSupplySpent ? state.blackSupplySpent[i] : 0;
            const whiteRemain = whiteTotal - whiteSpent;
            const blackRemain = blackTotal - blackSpent;
            const maxSupply = Math.max(whiteTotal, blackTotal, 1);

            const barX = colX + 4;
            const barY = y + rowH - 12;
            const barW = colW - thumbSize - 12;
            const pipW = Math.max(2, (barW / maxSupply) - 1);

            for (let s = 0; s < maxSupply; s++) {
                const px = barX + s * (pipW + 1);
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
        const H = canvas.height;

        // Dark background for both columns
        ctx.fillStyle = '#111122';
        ctx.fillRect(0, 0, BUY_PANE_WIDTH, H);

        if (!state.cards) return;

        // Split cards into base set (col 0) and additional (col 1)
        const baseCards = [];
        const baseIndices = [];
        const addCards = [];
        const addIndices = [];

        for (let i = 0; i < state.cards.length; i++) {
            if (BASE_SET_NAMES.has(state.cards[i])) {
                baseCards.push(state.cards[i]);
                baseIndices.push(i);
            } else {
                addCards.push(state.cards[i]);
                addIndices.push(i);
            }
        }

        // Column divider
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(BUY_COL_WIDTH, 30);
        ctx.lineTo(BUY_COL_WIDTH, H);
        ctx.stroke();

        drawBuyPaneColumn(state, baseCards, baseIndices, 0);
        drawBuyPaneColumn(state, addCards, addIndices, BUY_COL_WIDTH);
    }

    // ---------------------------------------------------------------------------
    // HUD
    // ---------------------------------------------------------------------------
    function drawHUD(state) {
        const W = canvas.width;
        const H = canvas.height;

        // Top bar background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(BUY_PANE_WIDTH, 0, W - BUY_PANE_WIDTH, 28);

        // Turn info
        let turnStr = '\u2191 ' + REPLAY.p1 + ' vs ' + REPLAY.p0 + ' \u2193';

        if (REPLAY.turnBoundaries && REPLAY.turnBoundaries.length > 0) {
            // Find current turn
            let turnIdx = 0;
            for (let i = 1; i < REPLAY.turnBoundaries.length; i++) {
                if (REPLAY.turnBoundaries[i] <= stateIndex) turnIdx = i;
                else break;
            }
            const turnStart = REPLAY.turnBoundaries[turnIdx];
            const turnEnd = (turnIdx + 1 < REPLAY.turnBoundaries.length) ? REPLAY.turnBoundaries[turnIdx + 1] : totalStates;
            const actionInTurn = stateIndex - turnStart + 1;
            const actionsInTurn = turnEnd - turnStart;

            turnStr += '   Turn ' + (turnIdx + 1) + '/' + REPLAY.turns;
            turnStr += '   [' + actionInTurn + '/' + actionsInTurn + ']';

            // Action label
            if (REPLAY.actions && stateIndex < REPLAY.actions.length) {
                turnStr += '   ' + REPLAY.actions[stateIndex];
            }
        }

        turnStr += '   Winner: ' + REPLAY.winnerName;

        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 16px Consolas, monospace';
        ctx.fillText(turnStr, BUY_PANE_WIDTH + 10, 20);

        // Player name labels — top player (P1) left of step counter, bottom player (P0) mirrored
        ctx.font = 'bold 14px Consolas, monospace';
        const stepStr = 'Step ' + stateIndex + '/' + (totalStates - 1);
        const stepW = ctx.measureText(stepStr).width;
        const stepX = W - stepW - 10;

        // P1 label (top) — to the left of step counter
        ctx.fillStyle = '#ff8866';
        const p1Label = REPLAY.p1;
        const p1LabelW = ctx.measureText(p1Label).width;
        ctx.fillText(p1Label, stepX - p1LabelW - 15, 20);

        // Step counter (top-right)
        ctx.fillStyle = '#888';
        ctx.font = '14px Consolas, monospace';
        ctx.fillText(stepStr, stepX, 20);

        // P0 label (bottom) — mirrored position at bottom-right
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(stepX - p1LabelW - 25, H - 28, W - stepX + p1LabelW + 25, 28);
        ctx.font = 'bold 14px Consolas, monospace';
        ctx.fillStyle = '#6688ff';
        const p0Label = REPLAY.p0;
        const p0LabelW = ctx.measureText(p0Label).width;
        ctx.fillText(p0Label, stepX - p0LabelW - 15, H - 10);
        ctx.fillStyle = '#888';
        ctx.font = '14px Consolas, monospace';
        ctx.fillText(stepStr, stepX, H - 10);

        // Phase label — on active player's side, matching GUIState_Play.cpp:678
        // Active player 1 (top) → near top; active player 0 (bottom) → near bottom
        const phaseLabels = {
            'action': 'ACTION PHASE',
            'defense': 'DEFENSE PHASE - ASSIGN BLOCKERS',
            'confirm': 'CONFIRM PHASE',
            'breach': 'BREACH PHASE'
        };
        const phaseText = phaseLabels[state.phase] || state.phase.toUpperCase();
        ctx.font = 'bold 16px Consolas, monospace';
        ctx.fillStyle = '#fff';
        const phaseW = ctx.measureText(phaseText).width;
        const phaseCenterX = BUY_PANE_WIDTH + (W - BUY_PANE_WIDTH) / 2;
        const phaseY = state.turn === 1 ? 46 : H - 10;
        ctx.fillText(phaseText, phaseCenterX - phaseW / 2, phaseY);

        // Controls hint (inside the second buy pane column, below the additional units)
        ctx.fillStyle = '#555';
        ctx.font = '11px Consolas, monospace';
        const hints = [
            'Right/Space: Next Action',
            'Left/Z:      Prev Action',
            'Up:          Next Turn',
            'Down:        Prev Turn',
            'Home/End:    Start/End'
        ];
        const hintY = H - 80;
        for (let i = 0; i < hints.length; i++) {
            ctx.fillText(hints[i], BUY_COL_WIDTH + 4, hintY + i * 14);
        }
    }

    // ---------------------------------------------------------------------------
    // Navigation
    // ---------------------------------------------------------------------------
    function getCurrentTurnIndex() {
        if (!REPLAY.turnBoundaries || REPLAY.turnBoundaries.length === 0) return stateIndex;
        let turnIdx = 0;
        for (let i = 1; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] <= stateIndex) turnIdx = i;
            else break;
        }
        return turnIdx;
    }

    function jumpToNextTurn() {
        if (!REPLAY.turnBoundaries) return;
        for (let i = 0; i < REPLAY.turnBoundaries.length; i++) {
            if (REPLAY.turnBoundaries[i] > stateIndex) {
                stateIndex = REPLAY.turnBoundaries[i];
                return;
            }
        }
    }

    function jumpToPrevTurn() {
        if (!REPLAY.turnBoundaries) return;
        const currentTurn = getCurrentTurnIndex();
        if (currentTurn > 0) {
            stateIndex = REPLAY.turnBoundaries[currentTurn - 1];
        } else {
            stateIndex = 0;
        }
    }

    // ---------------------------------------------------------------------------
    // Keyboard handling
    // ---------------------------------------------------------------------------
    document.addEventListener('keydown', function(e) {
        let changed = false;
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

    // ---------------------------------------------------------------------------
    // Resize handling
    // ---------------------------------------------------------------------------
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        drawBoard();
    }

    window.addEventListener('resize', resize);

    // ---------------------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------------------
    loadImages(function() {
        resize();
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
    if (args.length < 1) {
        console.error('Usage: node replay_to_html.js <replay.json> [output.html]');
        process.exit(1);
    }

    const replayPath = args[0];
    const outputPath = args[1] || replayPath.replace(/\.json$/i, '.html');

    console.error('Reading replay:', replayPath);
    const replay = JSON.parse(fs.readFileSync(replayPath, 'utf-8'));

    console.error('States:', replay.states.length, 'Turns:', replay.turns);

    // Find all card names used
    const usedNames = findUsedCardNames(replay);
    console.error('Unique cards:', usedNames.size, '-', [...usedNames].join(', '));

    // Load card library and build metadata
    console.error('Loading card library...');
    const cardLibrary = JSON.parse(fs.readFileSync(CARD_LIBRARY_PATH, 'utf-8'));
    const cardMeta = buildCardMetadata(cardLibrary, usedNames);

    // Collect and encode assets
    console.error('Embedding assets...');
    const assets = collectAssets(usedNames);
    console.error('Assets embedded:', Object.keys(assets).length);

    // Generate HTML
    console.error('Generating HTML...');
    const html = buildHTML(replay, assets, cardMeta);

    fs.writeFileSync(outputPath, html, 'utf-8');
    const sizeMB = (Buffer.byteLength(html, 'utf-8') / 1024 / 1024).toFixed(1);
    console.error('Written:', outputPath, '(' + sizeMB + ' MB)');
}

main();
