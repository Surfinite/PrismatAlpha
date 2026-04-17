# Godot 3D Battlefield Viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Godot 4 application that renders Prismata replays as a 3D battlefield with free camera controls, using pre-baked snapshot JSON from a Node.js preprocessor.

**Architecture:** Event-driven replay viewer with 4 layers: Provider (file-based), ReplayController (navigation/cache), Battlefield (authoritative reconciliation), VisualHooks (decorative effects). Preprocessor converts existing replay JSON → BoardSnapshot array using the JS engine.

**Tech Stack:** Godot 4.x (GDScript), Node.js (preprocessor), existing PrismataAI JS engine

**Spec:** `docs/superpowers/specs/2026-03-26-godot-3d-battlefield-viewer-design.md`

### Execution Order

**Phase A — Godot viewer with handcrafted fixtures (Tasks 1-9):**
Builds the complete viewer against a small hand-written snapshot JSON. Proves the architecture works end-to-end before touching the JS engine.

**Phase B — Node.js preprocessor (Tasks 10-13):**
Builds the preprocessor to generate real snapshot data from replays. Swaps real output into the already-working viewer.

| Task | Component | Phase |
|------|-----------|-------|
| 1 | Godot project setup | A |
| 2 | Handcrafted test fixture | A |
| 3 | Provider (base + file) | A |
| 4 | Replay controller | A |
| 5 | Battlefield + unit nodes | A |
| 6 | Camera system | A |
| 7 | Visual hooks | A |
| 8 | UI / HUD | A |
| 9 | Phase A integration test | A |
| 10 | Card ID mapping | B |
| 11 | Position calculator port | B |
| 12 | Preprocessor core + schema | B |
| 13 | Phase B integration with real replays | B |

### Key Implementation Rules

1. **Connect provider signals BEFORE loading data.** GDScript signals are synchronous — `load_file()` emits during the call. ReplayController must be connected first.
2. **Never mutate snapshot dictionaries.** They're cached and shared. Build local wrapper data instead.
3. **Hooks dispatch on forward transitions only.** Backward steps and jumps do snap-only reconciliation.
4. **Snapshot seq 0 may not exist.** Navigate to min available seq, not hardcoded 0.
5. **Event detection is heuristic for MVP.** Only guarantee `buy` and `kill` events. All other event types may be empty/no-op.

---

## File Map

### Preprocessor (Node.js — in PrismataAI repo)

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/replay_to_snapshots.js` | Create | Main preprocessor script: replay JSON → snapshot array |
| `tools/snapshot_schema.js` | Create | Schema validation for BoardSnapshot output |
| `tools/position_calculator.js` | Create | Port of position-calculator.ts (row/slot assignment) |
| `tools/card_id_map.js` | Create | Internal name → snake_case cardId + displayName mapping |

### Godot Project (new repo: `prismata-3d/`)

| File | Action | Responsibility |
|------|--------|---------------|
| `project.godot` | Create | Godot project config |
| `main.tscn` / `main.gd` | Create | Root scene: wires provider → replay → battlefield → hooks |
| `providers/base_provider.gd` | Create | Abstract provider interface (signals + methods) |
| `providers/file_provider.gd` | Create | Loads pre-baked snapshot JSON from disk |
| `replay/replay_controller.gd` | Create | Seq navigation, cache, playback, transition_type |
| `battlefield/battlefield.gd` | Create | Reconciler + scene owner, unit registry |
| `battlefield/battlefield.tscn` | Create | Terrain plane, lighting, skybox |
| `battlefield/unit_node.gd` | Create | Single unit: sprite, label, state display |
| `battlefield/unit_node.tscn` | Create | Unit scene template (Sprite3D + labels) |
| `visual/visual_context.gd` | Create | Context object passed to hooks |
| `visual/visual_hooks.gd` | Create | Event dispatcher, hook registry |
| `visual/hooks/buy_hook.gd` | Create | MVP: spawn flash on buy |
| `visual/hooks/kill_hook.gd` | Create | MVP: spawn flash on death |
| `camera/orbit_camera.gd` | Create | Orbit, zoom, pan controls |
| `camera/camera_modes.gd` | Create | Top-down toggle, cinematic focus, shake |
| `ui/replay_hud.gd` | Create | Scrubber, turn counter, playback controls |
| `ui/replay_hud.tscn` | Create | HUD layout scene |
| `ui/resource_bar.gd` | Create | Per-player resource display |
| `data/` | Create dir | Sample snapshot JSON fixtures |
| `assets/card_sprites/` | Create dir | Extracted 2D card art (PNG) |

### Reference Files (read-only, for preprocessor development)

| File | Purpose |
|------|---------|
| `js_engine/Analyzer.js` | Replay state machine, click processing |
| `js_engine/State.js` | Game state (table, mana, phase, turn) |
| `js_engine/Inst.js` | Unit instances (instId, health, role, deadness) |
| `js_engine/replay_validator.js` | `replayToGameInitInfo()` — replay JSON → engine format |
| `js_engine/replay_exporter.js` | State→JSON serialization reference |
| `<ladder>-site/src/components/game-renderer/position-calculator.ts` | Position algorithm to port |
| `bin/asset/config/cardLibrary.jso` | Unit definitions, internal→display name mapping |
| `source/engine/GameState.cpp` | C++ engine cross-reference for edge cases |

---

## Task 9B: Phase A Integration Test

**Files:** No new files.

Validate the complete viewer works end-to-end with the handcrafted fixture before building the real preprocessor.

- [ ] **Step 1: Full playthrough with handcrafted data**

Launch the project. Verify all systems work together:
- [ ] Units appear on correct sides (P0 south, P1 north)
- [ ] Units in correct rows (front/middle/back)
- [ ] Arrow keys step forward/backward
- [ ] Space toggles auto-play
- [ ] Camera orbit, zoom, pan, top-down toggle
- [ ] Buy events show flash effect (forward only)
- [ ] Kill events show death flash (forward only)
- [ ] Backward stepping has NO visual effects (snap-only)
- [ ] Scrubber tracks position
- [ ] Turn counter updates
- [ ] Resource bars update

- [ ] **Step 2: Fix any issues found**

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Phase A complete — viewer working with handcrafted fixtures"
```

---

## Task 10: Card ID Mapping

**Files:**
- Create: `tools/card_id_map.js`
- Read: `bin/asset/config/cardLibrary.jso`

This builds the mapping from internal engine names to stable snake_case `cardId` and `displayName`. Must be done first — everything else depends on it.

- [ ] **Step 1: Write card_id_map.js**

```javascript
// tools/card_id_map.js
// Loads cardLibrary.jso and builds cardId mapping
//
// cardId rules:
//   - lowercase snake_case derived from UIName (display name)
//   - e.g., "Tarsier" → "tarsier", "Tesla Tower" → "tesla_tower"
//   - spaces → underscores, lowercase, strip non-alphanumeric except underscore

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

    // cardLibrary.jso has cards keyed by internal name
    for (const [internalName, cardDef] of Object.entries(library)) {
        if (typeof cardDef !== 'object' || !cardDef.UIName) continue;
        const displayName = cardDef.UIName;
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
        console.log(`Mapped ${Object.keys(map).length} cards`);
        // Print a few examples
        const examples = ['Drone', 'Tesla Tower', 'Vivid Drone', 'Antima Comet'];
        for (const name of examples) {
            if (map[name]) {
                console.log(`  ${name} → cardId: "${map[name].cardId}", display: "${map[name].displayName}"`);
            }
        }
    }
}

module.exports = { buildCardIdMap, toCardId };
```

- [ ] **Step 2: Test the mapping**

Run: `node tools/card_id_map.js`
Expected: ~105+ cards mapped, examples like `Tesla Tower → "tarsier"` (note: Tesla Tower's UIName IS "Tarsier" per cardLibrary.jso).

- [ ] **Step 3: Verify edge cases**

Run: `node tools/card_id_map.js --json | node -e "const m=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')); const ids=Object.values(m).map(v=>v.cardId); const dupes=ids.filter((v,i)=>ids.indexOf(v)!==i); console.log('Duplicates:', dupes.length ? dupes : 'none'); console.log('Total:', ids.length)"`
Expected: No duplicate cardIds. If there are, add a suffix rule.

- [ ] **Step 4: Commit**

```bash
git add tools/card_id_map.js
git commit -m "feat(tools): card ID mapping from cardLibrary.jso internal names to snake_case"
```

---

## Task 11: Position Calculator Port

**Files:**
- Create: `tools/position_calculator.js`
- Read: `<ladder>-site/src/components/game-renderer/position-calculator.ts`
- Read: `bin/asset/config/cardLibrary.jso`

Port the TypeScript position calculator to Node.js. This assigns `render.row` and `render.slot` based on unit properties.

- [ ] **Step 1: Read the existing position-calculator.ts**

Read `<LADDER_REPO_PATH>\<ladder>-site\src\components\game-renderer\position-calculator.ts` and understand the `computePosition(cardMeta)` function. Note the position constants (FRONT_FAR_LEFT=0, MIDDLE_FAR_LEFT=10, BACK_FAR_LEFT=20, etc.) and the row derivation (`Math.floor(position / 10)`).

- [ ] **Step 2: Write position_calculator.js**

```javascript
// tools/position_calculator.js
// Port of position-calculator.ts — assigns render.row and render.slot
// based on unit properties from cardLibrary.jso
//
// Row mapping: positions 0-9 = "front", 10-19 = "middle", 20-29 = "back"

// [Port the computePosition function from position-calculator.ts here]
// The exact logic depends on reading the TypeScript source.
// Key: takes card properties (defaultBlocking, hasAbility, attack, undefendable, spell)
// and returns a position integer 0-29.

function positionToRow(position) {
    const rowIndex = Math.floor(position / 10);
    return ['front', 'middle', 'back'][rowIndex] || 'back';
}

function computeRenderInfo(cardMeta) {
    const slot = computePosition(cardMeta);
    return {
        row: positionToRow(slot),
        slot: slot
    };
}

module.exports = { computePosition, computeRenderInfo, positionToRow };
```

Note: The actual `computePosition` body must be ported 1:1 from the TypeScript source. Do NOT invent logic — copy the exact branching from position-calculator.ts.

- [ ] **Step 3: Test with known units**

Write a quick sanity check: Drone should be `middle` (slot ~10), Engineer should be `front` (slot ~0), Tarsier should be `back`, Conduit should be `back` (slot ~20).

- [ ] **Step 4: Commit**

```bash
git add tools/position_calculator.js
git commit -m "feat(tools): port position calculator from TS to Node.js"
```

---

## Task 12A: Snapshot Schema Validator

**Files:**
- Create: `tools/snapshot_schema.js`

Validates BoardSnapshot objects against the spec (Section 2). Used by the preprocessor to catch bugs before they reach Godot.

- [ ] **Step 1: Write snapshot_schema.js**

```javascript
// tools/snapshot_schema.js
// Validates a BoardSnapshot object against the spec schema.
// Returns { valid: bool, errors: string[] }

function validateSnapshot(snapshot) {
    const errors = [];

    // Required top-level fields
    if (typeof snapshot.schemaVersion !== 'number') errors.push('missing schemaVersion');
    if (snapshot.schemaVersion !== 1) errors.push(`unsupported schemaVersion: ${snapshot.schemaVersion}`);
    if (typeof snapshot.seq !== 'number') errors.push('missing seq');
    if (typeof snapshot.turn !== 'number') errors.push('missing turn');
    if (!['action', 'defense', 'confirm'].includes(snapshot.phase)) {
        errors.push(`invalid phase: ${snapshot.phase}`);
    }
    if (![0, 1].includes(snapshot.activePlayer)) errors.push(`invalid activePlayer: ${snapshot.activePlayer}`);
    if (!Array.isArray(snapshot.players) || snapshot.players.length !== 2) {
        errors.push('players must be array of length 2');
    }
    if (!Array.isArray(snapshot.events)) errors.push('events must be array');

    // Validate players
    if (snapshot.players) {
        for (let p = 0; p < snapshot.players.length; p++) {
            const player = snapshot.players[p];
            if (!player) { errors.push(`players[${p}] is null`); continue; }
            if (player.id !== p) errors.push(`players[${p}].id should be ${p}, got ${player.id}`);

            // Resources
            const res = player.resources;
            if (!res) { errors.push(`players[${p}].resources missing`); continue; }
            for (const key of ['gold', 'green', 'blue', 'red', 'energy', 'attack']) {
                if (typeof res[key] !== 'number') errors.push(`players[${p}].resources.${key} missing`);
            }

            // Units
            if (!Array.isArray(player.units)) {
                errors.push(`players[${p}].units must be array`);
                continue;
            }
            for (let u = 0; u < player.units.length; u++) {
                const unit = player.units[u];
                if (typeof unit.id !== 'number') errors.push(`players[${p}].units[${u}].id missing`);
                if (typeof unit.cardId !== 'string') errors.push(`players[${p}].units[${u}].cardId missing`);
                if (typeof unit.displayName !== 'string') errors.push(`players[${p}].units[${u}].displayName missing`);
                if (!unit.stats) errors.push(`players[${p}].units[${u}].stats missing`);
                if (!unit.state) errors.push(`players[${p}].units[${u}].state missing`);
                if (!unit.render) errors.push(`players[${p}].units[${u}].render missing`);
                if (unit.render && !['front', 'middle', 'back'].includes(unit.render.row)) {
                    errors.push(`players[${p}].units[${u}].render.row invalid: ${unit.render.row}`);
                }
            }
        }
    }

    // Validate events
    const validEventTypes = [
        'buy', 'kill', 'sacrifice', 'assign_blocker',
        'breach_start', 'breach_kill', 'ability',
        'phase_change', 'turn_start'
    ];
    if (snapshot.events) {
        for (let e = 0; e < snapshot.events.length; e++) {
            const evt = snapshot.events[e];
            if (!validEventTypes.includes(evt.type)) {
                errors.push(`events[${e}].type unknown: ${evt.type}`);
            }
        }
    }

    return { valid: errors.length === 0, errors };
}

module.exports = { validateSnapshot };
```

- [ ] **Step 2: Quick smoke test**

```bash
node -e "
const {validateSnapshot} = require('./tools/snapshot_schema');
const good = {schemaVersion:1,seq:0,turn:1,phase:'action',activePlayer:0,players:[{id:0,resources:{gold:6,green:0,blue:0,red:0,energy:0,attack:0},units:[]},{id:1,resources:{gold:6,green:0,blue:0,red:0,energy:0,attack:0},units:[]}],events:[]};
console.log('Valid:', validateSnapshot(good));
const bad = {seq:0};
console.log('Invalid:', validateSnapshot(bad));
"
```

Expected: First = `{ valid: true, errors: [] }`. Second = multiple errors.

- [ ] **Step 3: Commit**

```bash
git add tools/snapshot_schema.js
git commit -m "feat(tools): BoardSnapshot schema validator"
```

---

## Task 12B: Preprocessor — Core

**Files:**
- Create: `tools/replay_to_snapshots.js`
- Read: `js_engine/Analyzer.js`, `js_engine/State.js`, `js_engine/Inst.js`
- Read: `js_engine/replay_validator.js` (for `replayToGameInitInfo`)
- Use: `tools/card_id_map.js`, `tools/position_calculator.js`, `tools/snapshot_schema.js`

The main preprocessor. Loads a replay, replays click-by-click, emits a BoardSnapshot after each click batch / phase transition.

- [ ] **Step 1: Write the preprocessor skeleton**

```javascript
// tools/replay_to_snapshots.js
// Converts replay JSON → array of BoardSnapshot objects
//
// Usage: node tools/replay_to_snapshots.js <replay.json[.gz]> [-o output.json]
//
// Uses the existing JS engine (Analyzer.js) to replay click-by-click,
// extracting board state at each phase transition.

const fs = require('fs');
const zlib = require('zlib');
const path = require('path');

// JS engine imports — paths relative to js_engine/
// NOTE: The JS engine modules may need to be loaded from js_engine/ working dir
// or require path adjustments. Check require paths during implementation.
const { buildCardIdMap } = require('./card_id_map');
const { computeRenderInfo } = require('./position_calculator');
const { validateSnapshot } = require('./snapshot_schema');

// Load card ID map once
const cardIdMap = buildCardIdMap(
    path.join(__dirname, '..', 'bin', 'asset', 'config', 'cardLibrary.jso')
);

function loadReplay(filePath) {
    let raw = fs.readFileSync(filePath);
    if (filePath.endsWith('.gz')) {
        raw = zlib.gunzipSync(raw);
    }
    return JSON.parse(raw.toString('utf-8'));
}

function extractResources(mana) {
    // IMPORTANT: Mana class uses indexed pool[] array, NOT named properties.
    // See js_engine/Mana.js and js_engine/C.js for constants.
    // mana.money = gold (getter on pool[0])
    // mana.pool[C.MANA_G] = green (index 1)
    // mana.pool[C.MANA_B] = blue (index 2)
    // mana.pool[C.MANA_R] = red (index 3)
    // mana.pool[C.MANA_H] = energy (index 4)
    // mana.attack = attack (getter on pool[5])
    //
    // Import C constants at top of file to get MANA_G, MANA_B, etc.
    return {
        gold: mana.money || 0,
        green: mana.pool ? mana.pool[1] || 0 : 0,   // C.MANA_G = 1
        blue: mana.pool ? mana.pool[2] || 0 : 0,     // C.MANA_B = 2
        red: mana.pool ? mana.pool[3] || 0 : 0,      // C.MANA_R = 3
        energy: mana.pool ? mana.pool[4] || 0 : 0,    // C.MANA_H = 4
        attack: mana.attack || 0
    };
}

function extractUnit(inst, cardIdMap) {
    const internalName = inst.card.name; // or inst.card.internalName — verify during implementation
    const mapping = cardIdMap[internalName] || {
        cardId: internalName.toLowerCase().replace(/\s+/g, '_'),
        displayName: inst.card.UIName || internalName,
        internalName
    };

    const renderInfo = computeRenderInfo({
        // Pass card properties needed by position calculator
        // Exact property names depend on cardLibrary.jso structure
        name: internalName,
        defaultBlocking: inst.card.defaultBlocking,
        hasAbility: inst.card.hasAbility,
        attack: inst.card.attack,
        undefendable: inst.card.undefendable,
        spell: inst.card.spell,
        UIName: inst.card.UIName
    });

    // IMPORTANT: HP tracking in JS engine:
    // - inst.health = base/max HP (from card definition)
    // - inst.damage = accumulated damage
    // - Current HP = inst.health - inst.damage (for non-fragile)
    // - Fragile units: damage is permanent, HP doesn't regen
    // See Inst.js for details.
    //
    // IMPORTANT: Role/status mapping:
    // - inst.role === 'assigned' means assigned as BLOCKER (defense), NOT attacking
    // - inst.blocking = true means currently blocking
    // - Attack commitment: units with attack > 0 are committed when their
    //   player's action phase ends. Check inst.role or gameState.phase context.
    // - inst.role === 'inert' = exhausted/used this turn
    const currentHp = Math.max(0, (inst.health || 0) - (inst.damage || 0));

    return {
        id: inst.instId,
        cardId: mapping.cardId,
        displayName: mapping.displayName,
        internalName: mapping.internalName,
        stats: {
            hp: currentHp,
            maxHp: inst.health || 0,
            attack: inst.card.attack || 0,
            chill: inst.card.chill || 0
        },
        state: {
            mode: inst.constructionTime > 0 ? 'under_construction'
                : inst.role === 'inert' ? 'exhausted'
                : 'idle',
            blocking: inst.blocking || false,
            attacking: false, // TODO: derive from game phase + unit attack value
            chilled: inst.disruptDamage || 0,
            buildTurnsRemaining: inst.constructionTime || 0,
            lifespan: inst.lifespan != null ? inst.lifespan : -1,
            fragile: inst.card.fragile || false,
            frontline: inst.card.undefendable || false
        },
        render: renderInfo
    };
}

function extractSnapshot(gameState, seq, events, matchMeta) {
    const players = [0, 1].map(p => {
        const units = [];
        gameState.table.forEach(inst => {
            if (inst.owner === p && inst.deadness === 'alive') {
                units.push(extractUnit(inst, cardIdMap));
            }
        });
        return {
            id: p,
            resources: extractResources(p === 0 ? gameState.whiteMana : gameState.blackMana),
            units
        };
    });

    const snapshot = {
        schemaVersion: 1,
        seq,
        turn: gameState.numTurns || 0,
        phase: gameState.phase || 'action',
        presentationFlags: {
            glassBroken: gameState.glassBroken || false,
            swoosh: false // set by caller when beginTurn detected
        },
        activePlayer: gameState.turn || 0,
        viewPlayer: 0,
        players,
        events,
        actionOptions: null
    };

    // Include matchMeta on first snapshot
    if (seq === 0 && matchMeta) {
        snapshot.matchMeta = matchMeta;
    }

    return snapshot;
}

// Main: replay click-by-click, emit snapshots at phase transitions
function processReplay(replayPath, outputPath) {
    const replay = loadReplay(replayPath);

    // Convert replay to engine format
    // NOTE: This requires loading the JS engine modules.
    // The exact import mechanism depends on how Analyzer.js and its
    // dependencies are structured. May need to set working directory
    // or adjust module paths. See js_engine/replay_validator.js for
    // reference on how it loads the engine.
    //
    // Implementation must:
    // 1. Create Analyzer from replay
    // 2. Initialize game state
    // 3. Step through commandList click-by-click
    // 4. After each click, check if phase changed
    // 5. If phase changed (or certain events occurred), emit snapshot
    // 6. Track events (buy, kill, sacrifice, etc.) between snapshots
    //
    // This is the most complex part — the exact event detection
    // requires comparing state before/after each click to identify
    // what happened (unit bought, unit died, etc.)

    // TODO: Implement the click-by-click replay loop
    // See js_engine/replay_validator.js lines 88-111 for replayToGameInitInfo
    // See js_engine/Analyzer.js lines 36-100 for Analyzer usage

    console.log(`Processing: ${replayPath}`);
    // ... implementation here ...

    // Validate all snapshots
    const snapshots = []; // filled by replay loop
    for (const snap of snapshots) {
        const result = validateSnapshot(snap);
        if (!result.valid) {
            console.error(`Snapshot seq=${snap.seq} validation errors:`, result.errors);
        }
    }

    // Write output
    const outPath = outputPath || replayPath.replace(/\.json(\.gz)?$/, '_snapshots.json');
    fs.writeFileSync(outPath, JSON.stringify(snapshots, null, 2));
    console.log(`Wrote ${snapshots.length} snapshots to ${outPath}`);
}

// CLI
if (require.main === module) {
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.log('Usage: node tools/replay_to_snapshots.js <replay.json[.gz]> [-o output.json]');
        process.exit(1);
    }
    const replayPath = args[0];
    const outIdx = args.indexOf('-o');
    const outputPath = outIdx >= 0 ? args[outIdx + 1] : null;
    processReplay(replayPath, outputPath);
}

module.exports = { processReplay, extractSnapshot, extractUnit };
```

Note: Spec requirement 5 ("Cache unit positions before each reconciliation step") is fulfilled Godot-side in `battlefield.gd`'s `_prev_positions` dictionary, NOT by the preprocessor. The preprocessor only provides `render.row` and `render.slot`; Godot converts these to world-space Vector3 and caches them before reconciliation.

Note: The `processReplay` function's click-by-click loop is the hardest part. It must:
- Load the replay via `replayToGameInitInfo()` from `replay_validator.js`
- Create an `Analyzer` instance
- Step through `commandList` using `analyzer.recordClick()`
- Track phase changes and events between snapshots
- Detect unit births/deaths by comparing `state.table` before/after each click

The exact implementation depends on JS engine module loading, which varies. Check `replay_validator.js` and `matchup_clean.js` for working examples of engine initialization.

- [ ] **Step 2: Implement the click-by-click replay loop**

This is the core implementation step. Study `replay_validator.js` to understand how it replays clicks, then extend it to extract state and detect events.

Key references:
- `js_engine/replay_validator.js` lines 88-111: `replayToGameInitInfo()`
- `js_engine/Analyzer.js` lines 36-100: constructor, `loaderInit()`, `recordClick()`
- `js_engine/State.js`: `gameState.table.forEach()`, `gameState.phase`, `gameState.turn`
- `js_engine/Inst.js`: `inst.instId`, `inst.deadness`, `inst.owner`

Event detection approach:
- Before each click: snapshot the set of alive unit IDs
- After each click: compare against new alive unit IDs
- New IDs = `buy` events. Missing IDs = `kill`/`sacrifice` events
- Phase change detection: compare `gameState.phase` before/after
- `glassBroken` detection: check `gameState.glassBroken` flag

- [ ] **Step 3: Test with a real replay**

Pick a replay from `bin/asset/replays/` or fetch one from S3:
```bash
node tools/replay_to_snapshots.js bin/asset/replays/2026-03-05_02-30-09_Frontline/game_0001.json -o data/test_snapshots.json
```

Expected: Valid JSON array of snapshots. Each snapshot has schemaVersion=1, units with cardId/row/slot, events array.

- [ ] **Step 4: Validate output**

```bash
node -e "
const snaps = JSON.parse(require('fs').readFileSync('data/test_snapshots.json','utf8'));
console.log('Snapshots:', snaps.length);
console.log('First seq:', snaps[0].seq, 'Last seq:', snaps[snaps.length-1].seq);
console.log('P0 units at end:', snaps[snaps.length-1].players[0].units.length);
console.log('P1 units at end:', snaps[snaps.length-1].players[1].units.length);
console.log('Sample unit:', JSON.stringify(snaps[5]?.players[0]?.units[0], null, 2));
console.log('Sample event:', JSON.stringify(snaps[5]?.events[0], null, 2));
"
```

- [ ] **Step 5: Commit**

```bash
git add tools/replay_to_snapshots.js
git commit -m "feat(tools): replay-to-snapshots preprocessor for Godot 3D viewer"
```

---

## Task 1: Godot Project Setup

**Files:**
- Create: `prismata-3d/project.godot`
- Create: `prismata-3d/main.tscn`
- Create: `prismata-3d/main.gd`

Bootstrap the Godot 4 project. Verify it launches and shows a basic 3D scene.

- [ ] **Step 1: Create project directory structure**

```bash
mkdir -p prismata-3d/{providers,replay,battlefield,visual/hooks,visual/effects,visual/utils,camera,ui,data,assets/card_sprites,assets/models}
```

- [ ] **Step 2: Create project.godot**

Create `prismata-3d/project.godot` with basic Godot 4 config. Set window size 1920x1080, project name "Prismata 3D Viewer".

Note: The exact format of `project.godot` depends on your Godot 4 version. Best to create the project in Godot Editor first, then modify. Alternatively, create a minimal `project.godot`:

```ini
; Engine configuration file.
; It's best edited using the editor UI and not directly,
; but it can also be edited manually.

[application]
config/name="Prismata 3D Viewer"
run/main_scene="res://main.tscn"
config/features=PackedStringArray("4.3")

[display]
window/size/viewport_width=1920
window/size/viewport_height=1080
window/stretch/mode="canvas_items"

[rendering]
renderer/rendering_method="forward_plus"
```

- [ ] **Step 3: Create main scene**

Create `prismata-3d/main.tscn` and `prismata-3d/main.gd`. The main scene wires together the high-level components. For now, just show a gray 3D environment with a camera to verify the project runs.

```gdscript
# main.gd
extends Node3D

func _ready():
    print("Prismata 3D Viewer loaded")
```

- [ ] **Step 4: Verify project launches**

Open `prismata-3d/project.godot` in Godot Editor. Press F5 to run. Should show an empty 3D viewport with console output "Prismata 3D Viewer loaded".

- [ ] **Step 5: Commit**

- [ ] **Step 6: Commit**

```bash
cd prismata-3d && git init && git add -A
git commit -m "feat: initial Godot 4 project setup for Prismata 3D Viewer"
```

---

## Task 2: Handcrafted Test Fixture

**Files:**
- Create: `prismata-3d/data/test_match.json`

Hand-write a small snapshot JSON to bootstrap the viewer without depending on the preprocessor. This lets us validate the entire Godot architecture immediately.

- [ ] **Step 1: Write test_match.json**

Create `prismata-3d/data/test_match.json` with 5-6 snapshots that exercise: initial state, buying units, phase changes, a kill, and breach. Use the spec's BoardSnapshot schema (Section 2). Example structure:

```json
[
  {
    "schemaVersion": 1, "seq": 0, "turn": 1, "phase": "action", "activePlayer": 0,
    "presentationFlags": { "glassBroken": false, "swoosh": false },
    "viewPlayer": 0,
    "matchMeta": { "matchId": "test_001", "players": [{"id": 0, "name": "Blue"}, {"id": 1, "name": "Red"}] },
    "players": [
      { "id": 0, "resources": {"gold": 6, "green": 0, "blue": 0, "red": 0, "energy": 0, "attack": 0},
        "units": [
          {"id": 1, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 10}},
          {"id": 2, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 11}},
          {"id": 3, "cardId": "engineer", "displayName": "Engineer", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "front", "slot": 0}}
        ]
      },
      { "id": 1, "resources": {"gold": 7, "green": 0, "blue": 0, "red": 0, "energy": 0, "attack": 0},
        "units": [
          {"id": 101, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 10}},
          {"id": 102, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 11}},
          {"id": 103, "cardId": "engineer", "displayName": "Engineer", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "front", "slot": 0}}
        ]
      }
    ],
    "events": [],
    "actionOptions": null
  },
  {
    "schemaVersion": 1, "seq": 1, "turn": 1, "phase": "action", "activePlayer": 0,
    "presentationFlags": { "glassBroken": false, "swoosh": false },
    "viewPlayer": 0,
    "players": [
      { "id": 0, "resources": {"gold": 4, "green": 0, "blue": 0, "red": 0, "energy": 0, "attack": 0},
        "units": [
          {"id": 1, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 10}},
          {"id": 2, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 11}},
          {"id": 3, "cardId": "engineer", "displayName": "Engineer", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "front", "slot": 0}},
          {"id": 4, "cardId": "tarsier", "displayName": "Tarsier", "stats": {"hp": 1, "maxHp": 1, "attack": 1, "chill": 0}, "state": {"mode": "under_construction", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 1, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "back", "slot": 26}}
        ]
      },
      { "id": 1, "resources": {"gold": 7, "green": 0, "blue": 0, "red": 0, "energy": 0, "attack": 0},
        "units": [
          {"id": 101, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 10}},
          {"id": 102, "cardId": "drone", "displayName": "Drone", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "middle", "slot": 11}},
          {"id": 103, "cardId": "engineer", "displayName": "Engineer", "stats": {"hp": 1, "maxHp": 1, "attack": 0, "chill": 0}, "state": {"mode": "idle", "blocking": false, "attacking": false, "chilled": 0, "buildTurnsRemaining": 0, "lifespan": -1, "fragile": false, "frontline": false}, "render": {"row": "front", "slot": 0}}
        ]
      }
    ],
    "events": [{"type": "buy", "player": 0, "cardId": "tarsier", "unitId": 4}],
    "actionOptions": null
  }
]
```

Add 3-4 more snapshots showing: P1's turn (phase change), a unit finishing construction, a kill event (unit disappears), and optionally breach. Each snapshot must be a complete board state — not a diff.

- [ ] **Step 2: Validate fixture manually**

Open the JSON, verify: seq is monotonic, every snapshot has all required fields, units appear/disappear consistently between snapshots.

- [ ] **Step 3: Commit**

```bash
git add data/test_match.json
git commit -m "feat: handcrafted test fixture for viewer bootstrapping"
```

---

## Task 3: Provider — Base + File

**Files:**
- Create: `prismata-3d/providers/base_provider.gd`
- Create: `prismata-3d/providers/file_provider.gd`

Implement the provider interface and the FileProvider that loads pre-baked snapshots.

- [ ] **Step 1: Write base_provider.gd**

```gdscript
# providers/base_provider.gd
class_name BaseProvider
extends RefCounted

signal snapshot_available(seq: int)
signal provider_reset()
signal provider_error(message: String)

func request_snapshot(_seq: int) -> void:
    push_error("BaseProvider.request_snapshot not implemented")

func get_snapshot(_seq: int) -> Variant:
    push_error("BaseProvider.get_snapshot not implemented")
    return null

func has_snapshot(_seq: int) -> bool:
    return false

func get_latest_seq() -> int:
    return -1

func is_live() -> bool:
    return false

func can_seek() -> bool:
    return false

func get_total_seqs() -> int:
    return -1
```

- [ ] **Step 2: Write file_provider.gd**

```gdscript
# providers/file_provider.gd
class_name FileProvider
extends BaseProvider

var _snapshots: Dictionary = {}  # seq -> snapshot dict
var _latest_seq: int = -1

func load_file(file_path: String) -> void:
    var file = FileAccess.open(file_path, FileAccess.READ)
    if not file:
        provider_error.emit("Failed to open: " + file_path)
        return

    var json = JSON.new()
    var err = json.parse(file.get_as_text())
    file.close()

    if err != OK:
        provider_error.emit("JSON parse error: " + json.get_error_message())
        return

    var data = json.get_data()
    if not data is Array:
        provider_error.emit("Expected array of snapshots")
        return

    _snapshots.clear()
    _latest_seq = -1

    for snapshot in data:
        if not snapshot is Dictionary or not snapshot.has("seq"):
            continue
        if snapshot.get("schemaVersion", 0) != 1:
            provider_error.emit("Unsupported schema version: " + str(snapshot.get("schemaVersion")))
            return
        var seq = int(snapshot["seq"])
        _snapshots[seq] = snapshot
        if seq > _latest_seq:
            _latest_seq = seq

    print("FileProvider: loaded %d snapshots (seq 0-%d)" % [_snapshots.size(), _latest_seq])

    # Emit availability AFTER all snapshots are cached
    # (GDScript signals are synchronous — emitting during the loop
    # would cause ReplayController to navigate before loading completes)
    for seq in _snapshots:
        snapshot_available.emit(seq)

func get_snapshot(seq: int) -> Variant:
    return _snapshots.get(seq)

func has_snapshot(seq: int) -> bool:
    return _snapshots.has(seq)

func get_latest_seq() -> int:
    return _latest_seq

func request_snapshot(seq: int) -> void:
    if has_snapshot(seq):
        snapshot_available.emit(seq)

func is_live() -> bool:
    return false

func can_seek() -> bool:
    return true

func get_total_seqs() -> int:
    return _snapshots.size()
```

- [ ] **Step 3: Test in main.gd**

Update `main.gd` to load a snapshot file and print some info:

```gdscript
func _ready():
    var provider = FileProvider.new()
    provider.load_file("res://data/test_match.json")
    print("Latest seq: ", provider.get_latest_seq())
    var snap = provider.get_snapshot(0)
    if snap:
        print("First snapshot turn: ", snap.get("turn"))
        print("P0 units: ", snap["players"][0]["units"].size())
```

Run the project. Should print snapshot info.

- [ ] **Step 4: Commit**

```bash
git add providers/
git commit -m "feat: base provider interface and file provider"
```

---

## Task 4: Replay Controller

**Files:**
- Create: `prismata-3d/replay/replay_controller.gd`

Navigation, caching, playback. Emits `snapshot_changed(prev, current, transition_type)`.

- [ ] **Step 1: Write replay_controller.gd**

```gdscript
# replay/replay_controller.gd
class_name ReplayController
extends Node

signal snapshot_changed(prev_snapshot: Variant, current_snapshot: Variant, transition_type: String)

var _provider: BaseProvider
var _cache: Dictionary = {}       # seq -> snapshot
var _turn_index: Dictionary = {}  # turn -> first seq
var _current_seq: int = -1
var _latest_seq: int = -1
var _playing: bool = false
var _play_speed: float = 1.0
var _play_timer: float = 0.0
var _base_interval: float = 0.5   # seconds per seq at 1x speed

func init(provider: BaseProvider) -> void:
    _provider = provider
    _provider.snapshot_available.connect(_on_snapshot_available)
    _provider.provider_reset.connect(_on_provider_reset)

func _on_snapshot_available(seq: int) -> void:
    var snapshot = _provider.get_snapshot(seq)
    if snapshot == null:
        return
    _cache[seq] = snapshot
    if seq > _latest_seq:
        _latest_seq = seq
    # Build turn index
    var turn = int(snapshot.get("turn", 0))
    if not _turn_index.has(turn) or seq < _turn_index[turn]:
        _turn_index[turn] = seq
    # Auto-navigate to first available snapshot (don't assume seq 0 exists)
    if _current_seq == -1:
        var min_seq = seq
        for cached_seq in _cache:
            if cached_seq < min_seq:
                min_seq = cached_seq
        _navigate_to(min_seq, "forward")

func _on_provider_reset() -> void:
    _cache.clear()
    _turn_index.clear()
    _current_seq = -1
    _latest_seq = -1
    _playing = false

func _navigate_to(seq: int, transition_type: String) -> void:
    if not _cache.has(seq):
        return
    var prev = _cache.get(_current_seq)
    var current = _cache[seq]
    _current_seq = seq
    snapshot_changed.emit(prev, current, transition_type)

func step_forward() -> void:
    var next_seq = _current_seq + 1
    if _cache.has(next_seq):
        _navigate_to(next_seq, "forward")

func step_backward() -> void:
    var prev_seq = _current_seq - 1
    if prev_seq >= 0 and _cache.has(prev_seq):
        _navigate_to(prev_seq, "backward")

func jump_to_seq(seq: int) -> void:
    var target = clampi(seq, 0, _latest_seq)
    if _cache.has(target):
        _navigate_to(target, "jump")

func jump_to_turn(turn: int) -> void:
    if _turn_index.has(turn):
        _navigate_to(_turn_index[turn], "jump")

func toggle_play() -> void:
    _playing = not _playing
    _play_timer = 0.0

func set_speed(speed: float) -> void:
    _play_speed = speed

func get_current_seq() -> int:
    return _current_seq

func get_latest_seq() -> int:
    return _latest_seq

func is_playing() -> bool:
    return _playing

func _process(delta: float) -> void:
    if not _playing:
        return
    _play_timer += delta * _play_speed
    if _play_timer >= _base_interval:
        _play_timer -= _base_interval
        var next_seq = _current_seq + 1
        if _cache.has(next_seq):
            _navigate_to(next_seq, "forward")
        else:
            _playing = false  # End of replay
```

- [ ] **Step 2: Wire into main.gd and test navigation**

Update `main.gd` to create provider + controller, step forward/back with arrow keys:

```gdscript
var _replay: ReplayController

func _ready():
    # IMPORTANT: Connect signals BEFORE loading data.
    # GDScript signals are synchronous — load_file() emits during the call.
    var provider = FileProvider.new()

    _replay = ReplayController.new()
    add_child(_replay)
    _replay.snapshot_changed.connect(_on_snapshot_changed)
    _replay.init(provider)

    # Load AFTER controller is connected
    provider.load_file("res://data/test_match.json")

func _on_snapshot_changed(prev, current, transition_type):
    print("Seq %d | Turn %d | Phase: %s | Type: %s" % [
        current["seq"], current["turn"], current["phase"], transition_type
    ])

func _input(event):
    if event.is_action_pressed("ui_right"):
        _replay.step_forward()
    elif event.is_action_pressed("ui_left"):
        _replay.step_backward()
    elif event.is_action_pressed("ui_accept"):  # Enter/Space
        _replay.toggle_play()
```

Run. Arrow keys should step through snapshots, printing seq/turn/phase.

- [ ] **Step 3: Commit**

```bash
git add replay/ main.gd
git commit -m "feat: replay controller with navigation and playback"
```

---

## Task 5: Battlefield — Terrain + Unit Nodes

**Files:**
- Create: `prismata-3d/battlefield/battlefield.gd`
- Create: `prismata-3d/battlefield/battlefield.tscn`
- Create: `prismata-3d/battlefield/unit_node.gd`
- Create: `prismata-3d/battlefield/unit_node.tscn`

The battlefield reconciles snapshots into 3D nodes. Units are upright 2D sprites (cardboard standees).

- [ ] **Step 1: Create battlefield.tscn**

In Godot Editor, create a scene with:
- `Node3D` root (named "Battlefield")
- `MeshInstance3D` child: flat plane mesh (20x12 units), dark green/gray material = terrain
- `DirectionalLight3D`: angled sunlight
- `WorldEnvironment` with basic sky

Save as `battlefield/battlefield.tscn`.

- [ ] **Step 2: Create unit_node.tscn**

In Godot Editor, create a scene with:
- `Node3D` root (named "UnitNode")
- `Sprite3D` child: billboard mode, will show card art
- `Label3D` child: positioned below sprite, shows unit name

Save as `battlefield/unit_node.tscn`.

- [ ] **Step 3: Write unit_node.gd**

```gdscript
# battlefield/unit_node.gd
class_name UnitNode
extends Node3D

@onready var sprite: Sprite3D = $Sprite3D
@onready var label: Label3D = $Label3D

var unit_id: int = -1
var card_id: String = ""

func setup(unit_data: Dictionary) -> void:
    unit_id = int(unit_data["id"])
    card_id = unit_data["cardId"]
    label.text = unit_data["displayName"]

    # Try to load card sprite
    var sprite_path = "res://assets/card_sprites/%s.png" % card_id
    if ResourceLoader.exists(sprite_path):
        sprite.texture = load(sprite_path)
    else:
        # Placeholder: colored square based on unit type
        # Will be replaced with actual card art
        pass

func update_state(unit_data: Dictionary) -> void:
    # Update visual indicators based on state
    var state = unit_data.get("state", {})
    var mode = state.get("mode", "idle")

    # Dim if under construction
    if mode == "under_construction":
        sprite.modulate = Color(0.5, 0.5, 0.5, 0.7)
    elif state.get("chilled", 0) > 0:
        sprite.modulate = Color(0.5, 0.7, 1.0)  # blue tint for chilled
    else:
        sprite.modulate = Color.WHITE
```

- [ ] **Step 4: Write battlefield.gd**

```gdscript
# battlefield/battlefield.gd
class_name Battlefield
extends Node3D

const UNIT_NODE_SCENE = preload("res://battlefield/unit_node.tscn")

# Row Z positions (distance from center)
const ROW_Z = {
    "front": 1.0,
    "middle": 3.0,
    "back": 5.0
}
const ROW_SPACING_X = 1.2  # horizontal spacing between units
const CENTER_Z = 0.0

var _unit_registry: Dictionary = {}           # unitId -> UnitNode
var _prev_positions: Dictionary = {}          # unitId -> Vector3 (for death effects)
var _visual_hooks: VisualHooks = null

func set_visual_hooks(hooks: VisualHooks) -> void:
    _visual_hooks = hooks

func apply_snapshot(prev_snapshot: Variant, current_snapshot: Variant, transition_type: String) -> void:
    # Cache positions before reconciliation (for death effect positioning)
    _prev_positions.clear()
    for unit_id in _unit_registry:
        _prev_positions[unit_id] = _unit_registry[unit_id].global_position

    # Reconcile
    _reconcile(prev_snapshot, current_snapshot)

    # Dispatch hooks only on forward transitions
    if transition_type == "forward" and current_snapshot and _visual_hooks:
        var context = _build_visual_context(prev_snapshot, current_snapshot)
        _visual_hooks.dispatch(current_snapshot.get("events", []), context)

func _reconcile(prev_snapshot: Variant, current_snapshot: Variant) -> void:
    if current_snapshot == null:
        return

    # Build set of current unit IDs with owner (DO NOT mutate snapshot dicts — they're cached)
    var current_units: Dictionary = {}  # unitId -> { "unit": dict, "owner": int }
    for p in range(current_snapshot["players"].size()):
        var player = current_snapshot["players"][p]
        for unit in player["units"]:
            current_units[int(unit["id"])] = { "unit": unit, "owner": p }

    # Build set of previous unit IDs
    var prev_units: Dictionary = {}
    if prev_snapshot:
        for p in range(prev_snapshot["players"].size()):
            var player = prev_snapshot["players"][p]
            for unit in player["units"]:
                prev_units[int(unit["id"])] = { "unit": unit, "owner": p }

    # Remove: in prev but not current
    var to_remove: Array = []
    for unit_id in _unit_registry:
        if not current_units.has(unit_id):
            to_remove.append(unit_id)
    for unit_id in to_remove:
        _unit_registry[unit_id].queue_free()
        _unit_registry.erase(unit_id)

    # Spawn or update
    for unit_id in current_units:
        var entry = current_units[unit_id]
        var unit_data = entry["unit"]
        var owner = entry["owner"]
        if _unit_registry.has(unit_id):
            # Update existing
            var node = _unit_registry[unit_id]
            node.update_state(unit_data)
            node.position = _calculate_position(unit_data, owner)
        else:
            # Spawn new
            var node = UNIT_NODE_SCENE.instantiate() as UnitNode
            add_child(node)
            node.setup(unit_data)
            node.position = _calculate_position(unit_data, owner)
            _unit_registry[unit_id] = node

func _calculate_position(unit_data: Dictionary, owner: int) -> Vector3:
    var render = unit_data.get("render", {})
    var row = render.get("row", "middle")
    var slot = int(render.get("slot", 15))

    var z_offset = ROW_Z.get(row, 3.0)
    # Player 0 (blue) = south (positive Z), Player 1 (red) = north (negative Z)
    if owner == 1:
        z_offset = -z_offset

    # X position from slot within row
    var slot_in_row = slot % 10
    var x_pos = (slot_in_row - 4.5) * ROW_SPACING_X  # center around 0

    return Vector3(x_pos, 0.5, z_offset)

func _build_visual_context(prev_snapshot: Variant, current_snapshot: Variant) -> VisualContext:
    var ctx = VisualContext.new()
    ctx.prev_snapshot = prev_snapshot
    ctx.current_snapshot = current_snapshot
    ctx._unit_registry = _unit_registry
    ctx._prev_positions = _prev_positions
    ctx.battlefield_root = self
    # ctx.camera set by main scene
    return ctx

func get_unit_node(unit_id: int) -> UnitNode:
    return _unit_registry.get(unit_id)

func get_prev_position(unit_id: int) -> Vector3:
    return _prev_positions.get(unit_id, Vector3.ZERO)
```

- [ ] **Step 5: Wire battlefield into main.gd**

Update `main.gd` to instantiate the battlefield scene and connect it to the replay controller's `snapshot_changed` signal.

- [ ] **Step 6: Test — run project, step through turns, see units appear/disappear**

Arrow keys should now show 3D unit sprites appearing on the terrain plane as you step through the replay.

- [ ] **Step 7: Commit**

```bash
git add battlefield/ main.gd main.tscn
git commit -m "feat: battlefield scene with unit reconciliation and 3D placement"
```

---

## Task 6: Camera System

**Files:**
- Create: `prismata-3d/camera/orbit_camera.gd`
- Create: `prismata-3d/camera/camera_modes.gd`

Free orbit camera with Mechabellum-style controls + top-down toggle.

- [ ] **Step 1: Write orbit_camera.gd**

```gdscript
# camera/orbit_camera.gd
class_name OrbitCamera
extends Camera3D

@export var focus_point: Vector3 = Vector3.ZERO
@export var distance: float = 15.0
@export var pitch: float = -45.0  # degrees, negative = looking down
@export var yaw: float = 0.0

@export var min_distance: float = 5.0
@export var max_distance: float = 40.0
@export var zoom_speed: float = 2.0
@export var orbit_speed: float = 0.3
@export var pan_speed: float = 0.02

var _dragging_orbit: bool = false
var _dragging_pan: bool = false
var _user_active: bool = false
var _top_down: bool = false
var _stored_pitch: float = -45.0

# Cinematic
var _focus_start: Vector3 = Vector3.ZERO
var _focus_target: Vector3 = Vector3.ZERO
var _focus_active: bool = false
var _focus_timer: float = 0.0
var _focus_duration: float = 1.0

# Shake
var _shake_intensity: float = 0.0
var _shake_timer: float = 0.0

func _ready():
    _update_transform()

func _input(event):
    if event is InputEventMouseButton:
        if event.button_index == MOUSE_BUTTON_LEFT:
            _dragging_orbit = event.pressed
            _user_active = event.pressed
            if event.pressed:
                _focus_active = false  # Cancel cinematic
        elif event.button_index == MOUSE_BUTTON_MIDDLE:
            _dragging_pan = event.pressed
            _user_active = event.pressed
        elif event.button_index == MOUSE_BUTTON_RIGHT:
            _dragging_pan = event.pressed
            _user_active = event.pressed
        elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
            distance = clampf(distance - zoom_speed, min_distance, max_distance)
            _update_transform()
        elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
            distance = clampf(distance + zoom_speed, min_distance, max_distance)
            _update_transform()

    elif event is InputEventMouseMotion:
        if _dragging_orbit and not _top_down:
            yaw -= event.relative.x * orbit_speed
            pitch = clampf(pitch - event.relative.y * orbit_speed, -89.0, -10.0)
            _update_transform()
        elif _dragging_pan:
            var right = global_transform.basis.x
            var forward = Vector3(global_transform.basis.z.x, 0, global_transform.basis.z.z).normalized()
            focus_point -= right * event.relative.x * pan_speed * distance * 0.01
            focus_point += forward * event.relative.y * pan_speed * distance * 0.01
            _update_transform()

    elif event is InputEventKey and event.pressed:
        if event.keycode == KEY_T:
            toggle_top_down()

func toggle_top_down():
    _top_down = not _top_down
    if _top_down:
        _stored_pitch = pitch
        pitch = -89.0
    else:
        pitch = _stored_pitch
    _update_transform()

func _update_transform():
    var pitch_rad = deg_to_rad(pitch)
    var yaw_rad = deg_to_rad(yaw)

    var offset = Vector3(
        sin(yaw_rad) * cos(pitch_rad) * distance,
        -sin(pitch_rad) * distance,
        cos(yaw_rad) * cos(pitch_rad) * distance
    )

    var shake_offset = Vector3.ZERO
    if _shake_intensity > 0:
        shake_offset = Vector3(
            randf_range(-1, 1) * _shake_intensity,
            randf_range(-1, 1) * _shake_intensity * 0.5,
            randf_range(-1, 1) * _shake_intensity
        )

    global_position = focus_point + offset + shake_offset
    look_at(focus_point)

func _process(delta):
    # Shake decay
    if _shake_timer > 0:
        _shake_timer -= delta
        if _shake_timer <= 0:
            _shake_intensity = 0.0
        _update_transform()

    # Cinematic focus (lerp from stored start to target)
    if _focus_active and not _user_active:
        _focus_timer += delta
        var t = clampf(_focus_timer / _focus_duration, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)  # smoothstep
        focus_point = _focus_start.lerp(_focus_target, t)
        _update_transform()
        if t >= 1.0:
            _focus_active = false

# Camera API (for hooks)
func request_focus(target: Vector3, duration: float = 1.0) -> void:
    if _user_active:
        return  # User input takes priority
    _focus_start = focus_point  # Store start position for clean lerp
    _focus_target = target
    _focus_duration = duration
    _focus_timer = 0.0
    _focus_active = true

func shake(intensity: float = 0.5, duration: float = 0.3) -> void:
    _shake_intensity = intensity
    _shake_timer = duration

func is_user_active() -> bool:
    return _user_active
```

- [ ] **Step 2: Add camera to battlefield.tscn**

Add the OrbitCamera as a child of the main scene (not battlefield, so it persists). Set initial focus_point to Vector3(0, 0, 0) — center of the battlefield.

- [ ] **Step 3: Test camera controls**

Run project. Verify:
- Left-drag orbits
- Scroll zooms
- Middle/right-drag pans
- T toggles top-down
- Default view shows angled battlefield

- [ ] **Step 4: Commit**

```bash
git add camera/
git commit -m "feat: orbit camera with zoom, pan, top-down toggle"
```

---

## Task 7: Visual Hooks System

**Files:**
- Create: `prismata-3d/visual/visual_context.gd`
- Create: `prismata-3d/visual/visual_hooks.gd`
- Create: `prismata-3d/visual/hooks/buy_hook.gd`
- Create: `prismata-3d/visual/hooks/kill_hook.gd`

The pluggable hook system. MVP: simple particle flash for buy/kill.

- [ ] **Step 1: Write visual_context.gd**

```gdscript
# visual/visual_context.gd
class_name VisualContext
extends RefCounted

var prev_snapshot: Variant
var current_snapshot: Variant
var camera: OrbitCamera
var battlefield_root: Node3D

# Internal — set by battlefield, not for hook modification
var _unit_registry: Dictionary = {}
var _prev_positions: Dictionary = {}

func get_unit_node(unit_id: int) -> UnitNode:
    return _unit_registry.get(unit_id)

func has_unit_node(unit_id: int) -> bool:
    return _unit_registry.has(unit_id)

func get_all_unit_nodes_for_player(player_id: int) -> Array:
    var result: Array = []
    if current_snapshot == null:
        return result
    var player_units = current_snapshot["players"][player_id]["units"]
    for unit in player_units:
        var uid = int(unit["id"])
        if _unit_registry.has(uid):
            result.append(_unit_registry[uid])
    return result

func get_unit_world_position(unit_id: int) -> Vector3:
    var node = get_unit_node(unit_id)
    if node:
        return node.global_position
    return Vector3.ZERO

func get_prev_unit_world_position(unit_id: int) -> Vector3:
    return _prev_positions.get(unit_id, Vector3.ZERO)

func spawn_effect(effect_scene: PackedScene, pos: Vector3) -> Node3D:
    var effect = effect_scene.instantiate() as Node3D
    battlefield_root.add_child(effect)
    effect.global_position = pos
    return effect
```

- [ ] **Step 2: Write visual_hooks.gd**

```gdscript
# visual/visual_hooks.gd
class_name VisualHooks
extends RefCounted

var _hooks: Dictionary = {}  # event_type -> Array[Callable]

func register(event_type: String, handler: Callable) -> void:
    if not _hooks.has(event_type):
        _hooks[event_type] = []
    _hooks[event_type].append(handler)

func dispatch(events: Array, context: VisualContext) -> void:
    for event in events:
        var type = event.get("type", "")
        if _hooks.has(type):
            for handler in _hooks[type]:
                handler.call(event, context)
```

- [ ] **Step 3: Write buy_hook.gd and kill_hook.gd**

```gdscript
# visual/hooks/buy_hook.gd
class_name BuyHook
extends RefCounted

func handle_event(event: Dictionary, context: VisualContext) -> void:
    var unit_id = int(event.get("unitId", -1))
    var node = context.get_unit_node(unit_id)
    if node:
        # Simple flash: scale up then back to normal
        var tween = node.create_tween()
        tween.tween_property(node, "scale", Vector3(1.3, 1.3, 1.3), 0.1)
        tween.tween_property(node, "scale", Vector3.ONE, 0.2)
```

```gdscript
# visual/hooks/kill_hook.gd
class_name KillHook
extends RefCounted

func handle_event(event: Dictionary, context: VisualContext) -> void:
    var unit_id = int(event.get("unitId", -1))
    var pos = context.get_prev_unit_world_position(unit_id)
    if pos != Vector3.ZERO:
        # Simple flash at death position using a temporary sprite
        # A proper particle effect would be better, but this works for MVP
        _spawn_death_flash(context.battlefield_root, pos)

func _spawn_death_flash(parent: Node3D, pos: Vector3) -> void:
    var mesh = MeshInstance3D.new()
    mesh.mesh = SphereMesh.new()
    mesh.mesh.radius = 0.3
    mesh.mesh.height = 0.6
    var mat = StandardMaterial3D.new()
    mat.albedo_color = Color(1.0, 0.3, 0.3, 0.8)
    mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    mesh.material_override = mat
    parent.add_child(mesh)
    mesh.global_position = pos

    var tween = mesh.create_tween()
    tween.tween_property(mat, "albedo_color:a", 0.0, 0.5)
    tween.tween_callback(mesh.queue_free)
```

- [ ] **Step 4: Register hooks in main.gd**

```gdscript
var _hooks: VisualHooks

func _ready():
    # ... after creating battlefield ...
    _hooks = VisualHooks.new()
    var buy_hook = BuyHook.new()
    _hooks.register("buy", buy_hook.handle_event)
    var kill_hook = KillHook.new()
    _hooks.register("kill", kill_hook.handle_event)
    _hooks.register("sacrifice", kill_hook.handle_event)  # same visual as kill
    _hooks.register("breach_kill", kill_hook.handle_event)  # same visual as kill
    _battlefield.set_visual_hooks(_hooks)
```

- [ ] **Step 5: Test — step forward through replay, see buy flashes and kill flashes**

- [ ] **Step 6: Commit**

```bash
git add visual/
git commit -m "feat: visual hook system with MVP buy/kill effects"
```

---

## Task 8: UI — Replay HUD

**Files:**
- Create: `prismata-3d/ui/replay_hud.gd`
- Create: `prismata-3d/ui/replay_hud.tscn`
- Create: `prismata-3d/ui/resource_bar.gd`

Turn counter, scrubber, playback controls, resource bars.

- [ ] **Step 1: Create replay_hud.tscn in Godot Editor**

Create a CanvasLayer with:
- `HBoxContainer` at bottom: play/pause button, step back button, step forward button, speed label
- `HSlider` at bottom: scrubber bar (min=0, max=latest_seq)
- `Label` at top-center: "Turn 4 — P0 Action"
- `VBoxContainer` at bottom-left: P0 resources
- `VBoxContainer` at top-left: P1 resources

- [ ] **Step 2: Write replay_hud.gd**

```gdscript
# ui/replay_hud.gd
class_name ReplayHUD
extends CanvasLayer

@onready var turn_label: Label = $TurnLabel
@onready var scrubber: HSlider = $Scrubber
@onready var play_button: Button = $Controls/PlayButton
@onready var speed_label: Label = $Controls/SpeedLabel

var _replay: ReplayController
var _scrubbing: bool = false
var _speeds: Array = [0.5, 1.0, 2.0, 4.0]
var _speed_index: int = 1

func init(replay: ReplayController) -> void:
    _replay = replay
    _replay.snapshot_changed.connect(_on_snapshot_changed)
    play_button.pressed.connect(_on_play_pressed)
    scrubber.drag_started.connect(func(): _scrubbing = true)
    scrubber.drag_ended.connect(_on_scrub_ended)

func _on_snapshot_changed(_prev, current, _transition_type):
    if current == null:
        return
    var phase = current.get("phase", "?")
    var player = "P%d" % current.get("activePlayer", 0)
    turn_label.text = "Turn %d — %s %s" % [current.get("turn", 0), player, phase.capitalize()]
    if not _scrubbing:
        scrubber.max_value = _replay.get_latest_seq()
        scrubber.value = _replay.get_current_seq()

func _on_play_pressed():
    _replay.toggle_play()
    play_button.text = "⏸" if _replay.is_playing() else "▶"

func _on_scrub_ended(_value_changed: bool):
    _scrubbing = false
    _replay.jump_to_seq(int(scrubber.value))

func _input(event):
    if event is InputEventKey and event.pressed:
        if event.keycode == KEY_BRACKETRIGHT:  # ] = speed up
            _speed_index = mini(_speed_index + 1, _speeds.size() - 1)
            _replay.set_speed(_speeds[_speed_index])
            speed_label.text = "%sx" % _speeds[_speed_index]
        elif event.keycode == KEY_BRACKETLEFT:  # [ = speed down
            _speed_index = maxi(_speed_index - 1, 0)
            _replay.set_speed(_speeds[_speed_index])
            speed_label.text = "%sx" % _speeds[_speed_index]
```

- [ ] **Step 3: Write resource_bar.gd**

```gdscript
# ui/resource_bar.gd
class_name ResourceBar
extends VBoxContainer

@onready var gold_label: Label = $Gold
@onready var green_label: Label = $Green
@onready var blue_label: Label = $Blue
@onready var red_label: Label = $Red
@onready var energy_label: Label = $Energy
@onready var attack_label: Label = $Attack

func update_resources(resources: Dictionary) -> void:
    gold_label.text = "Gold: %d" % resources.get("gold", 0)
    green_label.text = "Green: %d" % resources.get("green", 0)
    blue_label.text = "Blue: %d" % resources.get("blue", 0)
    red_label.text = "Red: %d" % resources.get("red", 0)
    energy_label.text = "Energy: %d" % resources.get("energy", 0)
    attack_label.text = "Attack: %d" % resources.get("attack", 0)
```

- [ ] **Step 4: Wire HUD into main scene, test full playback UI**

- [ ] **Step 5: Commit**

```bash
git add ui/
git commit -m "feat: replay HUD with scrubber, playback controls, resource bars"
```

---

## Task 9A: Card Sprite Extraction

**Files:**
- Populate: `prismata-3d/assets/card_sprites/`

Extract card art from the existing PrismataAI asset pipeline for use as placeholder textures.

- [ ] **Step 1: Identify card art source**

Card art exists in multiple places:
- `bin/asset/images/icons/` — extracted HD icons from SWF
- The PixiJS viewer's asset loader
- `<ladder>-site/public/` — web-optimized PNGs

Pick the source with the best quality PNG files at reasonable resolution (128x128 or 256x256).

- [ ] **Step 2: Copy and rename to snake_case cardId**

Write a script or manually copy card art PNGs, renaming to match the `cardId` format:
- `Tarsier.png` → `tarsier.png`
- `Tesla Tower.png` → `tarsier.png` (using display name, not internal name)
- etc.

Use `tools/card_id_map.js` output to generate the rename mapping.

- [ ] **Step 3: Verify a few units load in Godot**

Run the project — units with matching card sprites should display the actual card art instead of the placeholder.

- [ ] **Step 4: Commit**

```bash
git add assets/card_sprites/
git commit -m "feat: card sprite assets for 3D unit placeholders"
```

---

## Task 13: Integration Test — Real Replay Playthrough

**Files:**
- No new files — integration testing of all components together

This is the final MVP validation. Load a real replay, play through it, verify everything works end-to-end.

- [ ] **Step 1: Generate snapshots from a diverse replay**

Pick a replay with: buys, kills, breach, abilities, multiple unit types.

```bash
node tools/replay_to_snapshots.js <diverse_replay.json> -o prismata-3d/data/test_match.json
```

- [ ] **Step 2: Run full playthrough in Godot**

Launch the project. Verify:
- [ ] Units appear as they're bought (with flash effect)
- [ ] Units disappear when killed (with death flash)
- [ ] Unit positions match expected rows (defenders in front, attackers in back)
- [ ] Camera orbit, zoom, pan work
- [ ] Top-down toggle (T key) works
- [ ] Arrow keys step forward/backward
- [ ] Space/Enter toggles auto-play
- [ ] Scrubber bar shows progress and allows jumping
- [ ] Turn counter shows current turn and phase
- [ ] Resource bars update per player
- [ ] Backward stepping shows correct state (no visual glitches)
- [ ] Jumping to arbitrary turns works via scrubber

- [ ] **Step 3: Fix any issues found**

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: MVP integration — full replay playthrough working"
```

---

## Completion Checklist

All MVP items from spec Section 11:

- [ ] Load pre-baked snapshot JSON from file
- [ ] Step through seqs with arrow keys
- [ ] 3 rows per player rendered as 3D lanes on flat terrain
- [ ] Units displayed as upright 2D sprites (card art) — cardboard standees
- [ ] Free orbit camera with zoom/pan + top-down toggle
- [ ] Units appear/disappear as bought/destroyed (with simple particle flash)
- [ ] Turn counter and phase indicator
- [ ] Resource bars for both players
- [ ] Scrubber bar for navigation
- [ ] Play/pause auto-advance
