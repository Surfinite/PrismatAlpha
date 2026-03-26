# Godot Visual Parity — Phase 1: Card Layers (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace approximate card rendering (colored quads + text labels) with asset-matched layered card rendering using real textures from the PixiJS viewer.

**Architecture:** Extract PNG assets from `bin/asset/images/` to `prismata-3d/assets/`. Separate concerns into three files: `card_visual_state.gd` (pure visual-state decision tree), `card_visual_assets.gd` (centralized texture cache), `unit_node.gd` (scene application only). This is a **major parity increase**, still approximate in places — not a 1:1 port of every PixiJS edge case.

**Tech Stack:** Godot 4.6 (GDScript), Node.js (extraction script)

**Spec:** `docs/superpowers/specs/2026-03-26-godot-visual-parity-design.md`

**Baseline:** 51.8% combined weighted parity (1000-replay audit). Target: ~75%.

**Regression replays:** After each task, verify these 3 specific replays in Godot:
- `data/current_replay.json` — the default loaded replay
- `data/real_replay.json` — a full-length game (1.8MB)
- Generate a fresh one: `node tools/replay_to_snapshots.js <any replay> -o c:/libraries/prismata-3d/data/test_phase1.json`

---

## File Plan

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/extract_viewer_assets.js` | Create | Copy + rename PNGs, generate manifest JSON |
| `prismata-3d/assets/backgrounds/*.png` | Create (10) | Background frame textures (82×82) |
| `prismata-3d/assets/overlays/*.png` | Create (~10) | Cover + shading overlay textures |
| `prismata-3d/assets/icons/*.png` | Create (~15) | Status icons (sword, shield, heart, etc.) |
| `prismata-3d/assets/effects/*.png` | Create (1) | Chill snowflake only (skull is a hook effect, not Phase 1) |
| `prismata-3d/battlefield/card_visual_state.gd` | Create | Pure function: snapshot data → visual state dictionary. No scene/node refs. |
| `prismata-3d/battlefield/card_visual_assets.gd` | Create | Singleton texture cache. All textures loaded once, accessed by key. |
| `prismata-3d/battlefield/unit_node.gd` | Rewrite | Scene application only: reads visual state, sets textures/visibility |
| `prismata-3d/battlefield/unit_node.tscn` | Rewrite | Layered Sprite3D scene tree |
| `tools/audit_visual_fidelity.js` | Modify | Update GODOT_CAPABILITIES (conservative — only what's measured) |

### What's NOT in Phase 1

- **Skull death overlay** — dead units are removed during reconciliation; death visuals stay in `kill_hook.gd` as detached effects
- **`boughtThisPhase` distinction** — INVSPAWN used for all construction (INVBOUGHT deferred)
- **`sellable` / COVER_PROMPT** — deferred, marked unauditable
- **`SHADING_NOTBLOCK`** — requires `defaultBlocking` from card metadata (deferred)
- **`phase`-dependent logic** — snowflake suppression during defense phase (deferred)
- **P1 card flip** — deferred to Phase 4

---

### Task 1: Extract and Verify Assets

**Files:**
- Create: `tools/extract_viewer_assets.js`
- Create: `prismata-3d/assets/{backgrounds,overlays,icons,effects}/*.png`

Source paths verified against `build_viewer_bundle.js` (lines 133-203). Key finding: overlays and shields live in `icons/status/`, cage lives in `cardbg/`, HD sprites in `icons/extracted_hd/`.

- [ ] **Step 1: Write the extraction script with manifest**

```javascript
#!/usr/bin/env node
// tools/extract_viewer_assets.js
// Extracts PixiJS viewer assets to Godot project directories.
// Generates a manifest JSON for verification.
'use strict';
const fs = require('fs');
const path = require('path');

const BIN_IMAGES = path.join(__dirname, '..', 'bin', 'asset', 'images');
const DST_ROOT = path.resolve(__dirname, '..', '..', 'prismata-3d', 'assets');

// Source directories (matching build_viewer_bundle.js constants)
const CARDBG = 'cardbg';
const STATUS = 'icons/status';
const MOUSEOVER = 'icons/mouseover';
const HD = 'icons/extracted_hd';

// Verified mappings: bundle_key → [source_subdir, source_filename]
const ASSETS = {
    backgrounds: {
        'bg_dead.png':       [CARDBG, 'Card_Inver.png'],
        'bg_block.png':      [CARDBG, 'Card_Blue.png'],
        'bg_busy.png':       [CARDBG, 'Card_Grey.png'],
        'bg_absorb.png':     [CARDBG, 'Card_Orange.png'],
        'bg_chilled.png':    [CARDBG, 'Card_Blue_Frost.png'],
        'bg_bought.png':     [CARDBG, 'Card_Trans.png'],
        'bg_whitepink.png':  [CARDBG, 'Card_WhitePink.png'],
        'bg_blockred.png':   [CARDBG, 'Card_Red.png'],
        'bg_busyblue.png':   [CARDBG, 'Card_BlueGrey.png'],
        'bg_busyred.png':    [CARDBG, 'Card_RedGrey.png'],
    },
    overlays: {
        // Cover overlays
        'cover_blackclock.png':   [STATUS, 'highlight_blackclock.png'],
        'cover_goldclock.png':    [STATUS, 'highlight_goldclock.png'],
        'cover_cage.png':         [CARDBG, 'highlight_cage2.png'],      // cage2 lives in cardbg/
        'cover_goldshield.png':   [STATUS, 'highlight_goldshield.png'],
        'cover_damagebang.png':   [STATUS, 'highlight_damagebang.png'],
        // Shading overlays
        'shade_whiteshield.png':  [STATUS, 'highlight_whiteshield.png'],
        'shade_blueshield.png':   [STATUS, 'highlight_blueshield.png'],
        'shade_whiteshieldB.png': [STATUS, 'highlight_whiteshieldB.png'],
        'shade_redshield.png':    [STATUS, 'highlight_redshield.png'],
    },
    icons: {
        // Fixed icons (bottom-right)
        'sword_blue.png':         [MOUSEOVER, 'attack_big_blue.png'],
        'icon_defend.png':        [STATUS, 'icon_defend.png'],
        'icon_clock.png':         [STATUS, 'clock.png'],
        // Variable icons (left stack)
        'icon_hp.png':            [STATUS, 'status_hp.png'],
        'icon_undefendable.png':  [STATUS, 'status_undefendable.png'],
        'icon_delay.png':         [STATUS, 'status_delay.png'],
        'icon_doom.png':          [STATUS, 'status_doom.png'],
        'icon_charge0.png':       [STATUS, 'status_charge0.png'],
        'icon_charge1.png':       [STATUS, 'status_charge1.png'],
        'icon_charge2.png':       [STATUS, 'status_charge2.png'],
        'icon_charge3.png':       [STATUS, 'status_charge3.png'],
        'icon_tap.png':           [STATUS, 'status_tap.png'],
        'icon_attack.png':        [STATUS, 'icon_attack.png'],
    },
    effects: {
        'chill_snowflake.png':    [CARDBG, 'Card_Chilled.png'],
        // skull_death omitted — death effects handled by kill_hook.gd, not card layers
    },
};

function readPngDimensions(filepath) {
    const buf = fs.readFileSync(filepath);
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const manifest = {};
let copied = 0, missing = 0;

for (const [subdir, mapping] of Object.entries(ASSETS)) {
    const dstDir = path.join(DST_ROOT, subdir);
    fs.mkdirSync(dstDir, { recursive: true });
    manifest[subdir] = {};

    for (const [dstName, [srcSubdir, srcFile]] of Object.entries(mapping)) {
        const srcPath = path.join(BIN_IMAGES, srcSubdir, srcFile);
        const dstPath = path.join(dstDir, dstName);

        if (fs.existsSync(srcPath)) {
            fs.copyFileSync(srcPath, dstPath);
            const dims = readPngDimensions(srcPath);
            manifest[subdir][dstName] = {
                source: `${srcSubdir}/${srcFile}`,
                width: dims.width,
                height: dims.height,
            };
            copied++;
        } else {
            console.error(`MISSING: ${srcSubdir}/${srcFile}`);
            manifest[subdir][dstName] = { source: `${srcSubdir}/${srcFile}`, error: 'NOT FOUND' };
            missing++;
        }
    }
}

const manifestPath = path.join(DST_ROOT, 'asset_manifest.json');
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

console.log(`Extracted ${copied} assets (${missing} missing)`);
console.log(`Manifest written to ${manifestPath}`);
if (missing > 0) process.exit(1);
```

- [ ] **Step 2: Run the extraction script**

```bash
cd c:/libraries/PrismataAI && node tools/extract_viewer_assets.js
```

Expected: `Extracted NN assets (0 missing)` and a manifest JSON.

- [ ] **Step 3: Inspect the manifest to verify dimensions**

```bash
cat c:/libraries/prismata-3d/assets/asset_manifest.json
```

Check that:
- Backgrounds are all the same dimensions (likely 82×82 or 164×164)
- Overlays are the same dimensions as backgrounds
- Icons are smaller (likely 18×18 or 36×36)
- Record the actual background width — this determines `pixel_size` in the scene

- [ ] **Step 4: Commit extraction script**

```bash
cd c:/libraries/PrismataAI && git add tools/extract_viewer_assets.js && git commit -m "feat(tools): verified asset extraction with manifest for Godot viewer"
```

---

### Task 2: Create Centralized Texture Cache

**Files:**
- Create: `prismata-3d/battlefield/card_visual_assets.gd`

All textures loaded once at startup. No `load()` or `ResourceLoader.exists()` calls during `update_state()`.

- [ ] **Step 1: Write card_visual_assets.gd**

```gdscript
class_name CardVisualAssets
extends RefCounted

## Centralized texture cache for card rendering.
## Load once, access by key. No per-frame resource loading.

var backgrounds: Array = []    # Indexed by BACK_* constants (0-9)
var covers: Array = []         # Indexed by COVER_* constants (0-5)
var shadings: Array = []       # Indexed by SHADING_* constants (0-4)
var icons: Dictionary = {}     # Keyed by icon name string
var effects: Dictionary = {}   # Keyed by effect name string

const BG_FILES = [
    "bg_dead", "bg_block", "bg_busy", "bg_absorb", "bg_chilled",
    "bg_bought", "bg_whitepink", "bg_blockred", "bg_busyblue", "bg_busyred"
]

const COVER_FILES = [
    "", "cover_blackclock", "cover_goldclock", "cover_cage",
    "cover_goldshield", "cover_damagebang"
]

const SHADING_FILES = [
    "", "shade_whiteshield", "shade_blueshield",
    "shade_whiteshieldB", "shade_redshield"
]

const ICON_FILES = [
    "sword_blue", "icon_defend", "icon_clock",
    "icon_hp", "icon_undefendable", "icon_delay", "icon_doom",
    "icon_charge0", "icon_charge1", "icon_charge2", "icon_charge3",
    "icon_tap", "icon_attack",
]

const EFFECT_FILES = ["chill_snowflake"]

func _init() -> void:
    _load_indexed("res://assets/backgrounds/", BG_FILES, backgrounds)
    _load_indexed("res://assets/overlays/", COVER_FILES, covers)
    _load_indexed("res://assets/overlays/", SHADING_FILES, shadings)
    _load_keyed("res://assets/icons/", ICON_FILES, icons)
    _load_keyed("res://assets/effects/", EFFECT_FILES, effects)

func _load_indexed(dir: String, names: Array, target: Array) -> void:
    for name in names:
        if name == "":
            target.append(null)
        else:
            var tex_path = "%s%s.png" % [dir, name]
            if ResourceLoader.exists(tex_path):
                target.append(load(tex_path))
            else:
                push_warning("CardVisualAssets: missing %s" % tex_path)
                target.append(null)

func _load_keyed(dir: String, names: Array, target: Dictionary) -> void:
    for name in names:
        var tex_path = "%s%s.png" % [dir, name]
        if ResourceLoader.exists(tex_path):
            target[name] = load(tex_path)
        else:
            push_warning("CardVisualAssets: missing %s" % tex_path)

func get_background(index: int) -> Texture2D:
    if index >= 0 and index < backgrounds.size():
        return backgrounds[index]
    return null

func get_cover(index: int) -> Texture2D:
    if index >= 0 and index < covers.size():
        return covers[index]
    return null

func get_shading(index: int) -> Texture2D:
    if index >= 0 and index < shadings.size():
        return shadings[index]
    return null

func get_icon(key: String) -> Texture2D:
    return icons.get(key)

func get_effect(key: String) -> Texture2D:
    return effects.get(key)
```

- [ ] **Step 2: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/card_visual_assets.gd && git commit -m "feat: centralized texture cache for card rendering"
```

---

### Task 3: Create Pure Visual State Function

**Files:**
- Create: `prismata-3d/battlefield/card_visual_state.gd`

Pure function: snapshot data in → visual state dictionary out. No scene/node references. No texture loading. Testable in isolation.

- [ ] **Step 1: Write card_visual_state.gd**

```gdscript
class_name CardVisualState
extends RefCounted

## Pure visual-state decision tree.
## Port of tools/visual_state.js — stateless, deterministic.
## Input: snapshot unit data + owner.
## Output: dictionary describing what each layer should show.

# Background frame indices (matches PixiJS UnitCard.ts)
const BACK_DEAD = 0
const BACK_BLOCK = 1
const BACK_BUSY = 2
const BACK_ABSORB = 3
const BACK_BLOCK_FROST = 4
const BACK_BOUGHT = 5
const BACK_WHITEPINK = 6
const BACK_BLOCKRED = 7
const BACK_BUSYBLUE = 8
const BACK_BUSYRED = 9

# Cover overlay indices
const COVER_EMPTY = 0
const COVER_INVSPAWN = 1
const COVER_INVBOUGHT = 2
const COVER_ASSIGNED = 3
const COVER_PROMPT = 4
const COVER_BANG = 5

# Shading overlay indices
const SHADING_EMPTY = 0
const SHADING_NOTBLOCK = 1
const SHADING_BLOCK = 2
const SHADING_DEAD_BLOCK = 3
const SHADING_REDBLOCK = 4

## Compute the full visual state for a single unit.
## Returns a dictionary with all layer decisions.
static func compute(state: Dictionary, stats: Dictionary, owner: int) -> Dictionary:
    var mode = str(state.get("mode", "idle"))
    var blocking = state.get("blocking", false)
    var attacking = state.get("attacking", false)
    var chilled = int(state.get("chilled", 0))
    var hp = int(stats.get("hp", 0))
    var max_hp = int(stats.get("maxHp", 0))
    var damage = max_hp - hp
    var build_turns = int(state.get("buildTurnsRemaining", 0))
    var fragile = state.get("fragile", false)
    var attack_val = int(stats.get("attack", 0))
    var is_bottom = (owner == 0)

    # Dead units shouldn't reach here (removed during reconciliation),
    # but handle defensively.
    var is_dead = (mode == "dead")
    var is_fully_chilled = chilled >= hp and hp > 0

    # --- Phase 1: Base background frame ---
    var back_frame: int
    var show_snowflake = false
    var card_alpha = 1.0

    if is_dead:
        back_frame = BACK_DEAD
    elif is_fully_chilled:
        back_frame = BACK_BLOCK_FROST
        show_snowflake = true
    elif blocking:
        back_frame = BACK_BLOCK if is_bottom else BACK_BLOCKRED
    else:
        back_frame = BACK_BUSYBLUE if is_bottom else BACK_BUSYRED

    # --- Phase 2: Construction / role overrides ---
    var cover_frame = COVER_EMPTY
    var shading_frame = SHADING_EMPTY

    if build_turns >= 1:
        back_frame = BACK_BOUGHT
        cover_frame = COVER_INVSPAWN  # No boughtThisPhase yet — always INVSPAWN
        card_alpha = 0.87
    elif attacking:
        cover_frame = COVER_ASSIGNED

    # Shading: blocking shields
    # Note: SHADING_NOTBLOCK requires defaultBlocking from card metadata (deferred)
    if blocking and not is_dead:
        shading_frame = SHADING_BLOCK if is_bottom else SHADING_REDBLOCK

    # --- Phase 3: Damage overrides ---
    var damage_counter = 0
    if damage > 0 and not is_dead:
        cover_frame = COVER_BANG
        shading_frame = SHADING_EMPTY
        damage_counter = damage
        if blocking:
            back_frame = BACK_ABSORB
        else:
            back_frame = BACK_ABSORB
        # Note: full PixiJS logic distinguishes BACK_WHITEPINK for dead+damaged.
        # Dead units are removed here, so this case doesn't arise in practice.

    return {
        "back_frame": back_frame,
        "cover_frame": cover_frame,
        "shading_frame": shading_frame,
        "card_alpha": card_alpha,
        "show_snowflake": show_snowflake,
        "damage_counter": damage_counter,
        # Pass through stats for status icon logic
        "attack": attack_val,
        "hp": hp,
        "max_hp": max_hp,
        "damage": damage,
        "fragile": fragile,
        "build_turns": build_turns,
        "is_dead": is_dead,
        "chilled": chilled,
        "delay": int(state.get("delay", 0)),
        "lifespan": int(state.get("lifespan", -1)),
        "charge": int(state.get("charge", 0)),
        "frontline": state.get("frontline", false),
    }
```

- [ ] **Step 2: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/card_visual_state.gd && git commit -m "feat: pure visual-state decision tree (port of visual_state.js)"
```

---

### Task 4: Refactor UnitNode Scene and Script

**Files:**
- Rewrite: `prismata-3d/battlefield/unit_node.tscn`
- Rewrite: `prismata-3d/battlefield/unit_node.gd`

Scene application only — reads visual state from `CardVisualState`, textures from `CardVisualAssets`.

**Important Sprite3D settings for layered transparency:**
- All sprites: `shading_mode = UNSHADED` (BaseMaterial3D) — prevents lighting darkening transparent layers
- All sprites: `alpha_cut = ALPHA_CUT_DISABLED` — use default alpha blending
- All sprites: `texture_filter = NEAREST` for pixel-crisp rendering
- Y-position separation prevents z-fighting (0.001 → 0.035 range is sufficient for orthographic camera)

- [ ] **Step 1: Write the scene file**

The `pixel_size` values depend on actual extracted image dimensions. If backgrounds are 82×82: `pixel_size = 1.0/82 ≈ 0.01220`. If they're 164×164 (2x): `pixel_size = 1.0/164 ≈ 0.00610`. Check the manifest from Task 1 Step 3.

Replace `prismata-3d/battlefield/unit_node.tscn`:

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://battlefield/unit_node.gd" id="1"]

[node name="UnitNode" type="Node3D"]
script = ExtResource("1")

[node name="BackgroundFrame" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
shading_mode = 0
texture_filter = 0
alpha_cut = 0
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0.001, 0)

[node name="CardSkin" type="Sprite3D" parent="."]
pixel_size = 0.0078125
billboard = 0
shading_mode = 0
texture_filter = 0
alpha_cut = 0
transform = Transform3D(0.878, 0, 0, 0, 0, -0.878, 0, 0.878, 0, 0, 0.01, 0)

[node name="CoverOverlay" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
shading_mode = 0
texture_filter = 0
alpha_cut = 0
visible = false
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0.015, 0)

[node name="ShadingOverlay" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
shading_mode = 0
texture_filter = 0
alpha_cut = 0
visible = false
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0.018, 0)

[node name="StatusOverlay" type="Node3D" parent="."]

[node name="NameLabel" type="Label3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, -0.25, 0.022, -0.35)
pixel_size = 0.005
font_size = 10
outline_size = 4
billboard = 0
modulate = Color(1, 1, 1, 1)
outline_modulate = Color(0, 0, 0, 1)
horizontal_alignment = 0
visible = false

[node name="EffectContainer" type="Node3D" parent="."]

[node name="DamageLabel" type="Label3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, -0.4, 0.035, -0.4)
pixel_size = 0.005
font_size = 14
outline_size = 4
billboard = 0
modulate = Color(1, 0, 0, 1)
outline_modulate = Color(0, 0, 0, 1)
horizontal_alignment = 1
visible = false
```

Notes:
- NameLabel `visible = false` — hidden by default, not viewer-faithful
- CardSkin transform scaled by 0.878 (72/82) — card art shows border
- `shading_mode = 0` = UNSHADED, `texture_filter = 0` = NEAREST
- Verify these Godot enum values match: check `SpriteBase3D` docs if scene fails to parse

- [ ] **Step 2: Write unit_node.gd (scene application only)**

```gdscript
class_name UnitNode
extends Node3D

## Card renderer — applies visual state to scene layers.
## Visual decisions made by CardVisualState (pure function).
## Textures loaded from CardVisualAssets (shared cache).

@onready var bg_frame: Sprite3D = $BackgroundFrame
@onready var card_skin: Sprite3D = $CardSkin
@onready var cover_overlay: Sprite3D = $CoverOverlay
@onready var shading_overlay: Sprite3D = $ShadingOverlay
@onready var status_container: Node3D = $StatusOverlay
@onready var name_label: Label3D = $NameLabel
@onready var effect_container: Node3D = $EffectContainer
@onready var damage_label: Label3D = $DamageLabel

var unit_id: int = -1
var card_id: String = ""
var unit_owner: int = 0

# Flat rotation for dynamically created child nodes
const FLAT_BASIS = Basis(Vector3(1, 0, 0), Vector3(0, 0, -1), Vector3(0, 1, 0))

# Shared across all instances (set by battlefield before first unit created)
static var assets: CardVisualAssets = null

# Status icon arrays: [Sprite3D, Label3D] pairs
var _fixed_icons: Array = []
var _variable_icons: Array = []
var _snowflake_sprite: Sprite3D = null

func _ready() -> void:
    if assets == null:
        assets = CardVisualAssets.new()
    _setup_effects()
    _setup_status_icons()

func _setup_effects() -> void:
    _snowflake_sprite = Sprite3D.new()
    _snowflake_sprite.pixel_size = 0.01220
    _snowflake_sprite.billboard = 0
    _snowflake_sprite.transform = Transform3D(FLAT_BASIS, Vector3(0, 0.03, 0))
    _snowflake_sprite.visible = false
    var tex = assets.get_effect("chill_snowflake")
    if tex:
        _snowflake_sprite.texture = tex
    effect_container.add_child(_snowflake_sprite)

func _setup_status_icons() -> void:
    # Fixed icons (bottom-right area)
    _create_fixed_icon(Vector3(0.15, 0.025, 0.32), "sword_blue")
    _create_fixed_icon(Vector3(0.35, 0.025, 0.32), "icon_defend")

    # Variable icons (left stack — repositioned dynamically per visible set)
    _variable_icons.append(_create_variable_icon("icon_hp"))
    _variable_icons.append(_create_variable_icon("icon_undefendable"))
    _variable_icons.append(_create_variable_icon("icon_delay"))
    _variable_icons.append(_create_variable_icon("icon_doom"))
    _variable_icons.append(_create_variable_icon("icon_charge0"))
    _variable_icons.append(_create_variable_icon("icon_tap"))

func _create_fixed_icon(pos: Vector3, icon_key: String) -> void:
    var icon_sprite = Sprite3D.new()
    icon_sprite.pixel_size = 0.012
    icon_sprite.billboard = 0
    icon_sprite.transform = Transform3D(FLAT_BASIS, pos)
    icon_sprite.visible = false
    var tex = assets.get_icon(icon_key)
    if tex:
        icon_sprite.texture = tex
    status_container.add_child(icon_sprite)

    var num_label = Label3D.new()
    num_label.pixel_size = 0.004
    num_label.font_size = 14
    num_label.modulate = Color.WHITE
    num_label.outline_size = 4
    num_label.outline_modulate = Color.BLACK
    num_label.billboard = 0
    num_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    num_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    num_label.transform = Transform3D(FLAT_BASIS, pos + Vector3(0, 0.005, 0.08))
    num_label.visible = false
    status_container.add_child(num_label)
    _fixed_icons.append([icon_sprite, num_label])

func _create_variable_icon(icon_key: String) -> Array:
    var icon_sprite = Sprite3D.new()
    icon_sprite.pixel_size = 0.012
    icon_sprite.billboard = 0
    icon_sprite.transform = Transform3D(FLAT_BASIS, Vector3.ZERO)
    icon_sprite.visible = false
    var tex = assets.get_icon(icon_key)
    if tex:
        icon_sprite.texture = tex
    status_container.add_child(icon_sprite)

    var num_label = Label3D.new()
    num_label.pixel_size = 0.004
    num_label.font_size = 12
    num_label.modulate = Color.WHITE
    num_label.outline_size = 4
    num_label.outline_modulate = Color.BLACK
    num_label.billboard = 0
    num_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    num_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    num_label.transform = Transform3D(FLAT_BASIS, Vector3.ZERO)
    num_label.visible = false
    status_container.add_child(num_label)
    return [icon_sprite, num_label]

func setup(unit_data: Dictionary, p_owner: int) -> void:
    unit_id = int(unit_data["id"])
    card_id = unit_data["cardId"]
    unit_owner = p_owner

    var sprite_path = "res://assets/card_sprites/%s.png" % card_id
    if ResourceLoader.exists(sprite_path):
        card_skin.texture = load(sprite_path)

func update_state(unit_data: Dictionary, p_owner: int) -> void:
    unit_owner = p_owner
    var state = unit_data.get("state", {})
    var stats = unit_data.get("stats", {})

    var vs = CardVisualState.compute(state, stats, unit_owner)
    _apply_layers(vs)
    _apply_status_icons(vs)

func _apply_layers(vs: Dictionary) -> void:
    # Layer 0: Background frame
    var bg_tex = assets.get_background(int(vs["back_frame"]))
    if bg_tex:
        bg_frame.texture = bg_tex

    # Layer 1: Card art alpha
    card_skin.modulate = Color(1, 1, 1, vs["card_alpha"])

    # Layer 2: Cover overlay
    var cover_idx = int(vs["cover_frame"])
    if cover_idx > 0:
        var cover_tex = assets.get_cover(cover_idx)
        if cover_tex:
            cover_overlay.texture = cover_tex
            cover_overlay.visible = true
        else:
            cover_overlay.visible = false
    else:
        cover_overlay.visible = false

    # Layer 3: Shading overlay
    var shading_idx = int(vs["shading_frame"])
    if shading_idx > 0:
        var shade_tex = assets.get_shading(shading_idx)
        if shade_tex:
            shading_overlay.texture = shade_tex
            shading_overlay.visible = true
        else:
            shading_overlay.visible = false
    else:
        shading_overlay.visible = false

    # Layer 8: Snowflake effect
    _snowflake_sprite.visible = vs["show_snowflake"]

    # Layer 9: Damage counter
    var dmg = int(vs["damage_counter"])
    if dmg > 0:
        damage_label.text = str(dmg)
        damage_label.visible = true
    else:
        damage_label.visible = false

func _apply_status_icons(vs: Dictionary) -> void:
    var attack_val = int(vs["attack"])
    var max_hp = int(vs["max_hp"])
    var hp = int(vs["hp"])
    var fragile = vs["fragile"]
    var is_dead = vs["is_dead"]
    var build_turns = int(vs["build_turns"])
    var damage = int(vs["damage"])

    # Fixed icon 0: Attack (sword)
    _set_fixed(0, attack_val > 0 and not is_dead, str(attack_val))

    # Fixed icon 1: Defense (shield, non-fragile only)
    # Note: PixiJS uses card metadata toughness; we use maxHp as proxy
    _set_fixed(1, not fragile and max_hp > 0 and not is_dead, str(max_hp))

    # Hide all variable icons, then show applicable ones
    for pair in _variable_icons:
        pair[0].visible = false
        pair[1].visible = false

    if is_dead:
        return

    # Construction override: suppress variable icons, show only build timer + fragile HP
    if build_turns > 0 and damage == 0:
        # Construction timer: show build_turns as the number on the construction icon
        # The cover overlay (clock) is already shown via cover_frame.
        # Show the countdown number centered on the card via damage_label position repurposed:
        # Actually, use a dedicated approach — show build timer via the first variable icon slot
        if fragile and hp > 0:
            _show_var_at(0, 0, str(hp))
        return

    # Normal variable icon display (stacked top-to-bottom on left side)
    var slot = 0

    if fragile and hp > 0:
        _show_var_at(0, slot, str(hp))
        slot += 1
    if vs["frontline"]:
        _show_var_at(1, slot, "")
        slot += 1
    if int(vs["delay"]) > 0:
        _show_var_at(2, slot, str(vs["delay"]))
        slot += 1
    if int(vs["lifespan"]) > 0:
        _show_var_at(3, slot, str(vs["lifespan"]))
        slot += 1

    var charge = int(vs["charge"])
    if charge > 0:
        var charge_tex = assets.get_icon("icon_charge%d" % mini(charge, 3))
        if charge_tex:
            _variable_icons[4][0].texture = charge_tex
        _show_var_at(4, slot, str(charge))
        slot += 1

    var chilled = int(vs["chilled"])
    if chilled > 0:
        var tap_key = "icon_tap" # icon_tap_on not separately extracted; same source
        var tap_tex = assets.get_icon(tap_key)
        if tap_tex:
            _variable_icons[5][0].texture = tap_tex
        _show_var_at(5, slot, str(chilled))
        slot += 1

func _set_fixed(idx: int, show: bool, text: String) -> void:
    _fixed_icons[idx][0].visible = show
    _fixed_icons[idx][1].visible = show and text != ""
    if show and text != "":
        _fixed_icons[idx][1].text = text

func _show_var_at(icon_idx: int, slot: int, text: String) -> void:
    var pos = Vector3(-0.38, 0.025, -0.3 + slot * 0.18)
    _variable_icons[icon_idx][0].transform = Transform3D(FLAT_BASIS, pos)
    _variable_icons[icon_idx][0].visible = true
    if text != "":
        _variable_icons[icon_idx][1].transform = Transform3D(FLAT_BASIS, pos + Vector3(0, 0.005, 0.08))
        _variable_icons[icon_idx][1].text = text
        _variable_icons[icon_idx][1].visible = true
```

- [ ] **Step 3: Verify in Godot — no parse errors, cards render with textures**

Open `prismata-3d`, press Play. Check:
- No errors in Output panel
- Background frame textures appear (colored borders around cards)
- Card art is visibly inset (border visible around edges)
- Navigate to turn 5+ to see construction clocks, blocking shields

If Sprite3D properties `shading_mode`, `texture_filter`, `alpha_cut` fail to parse in the tscn, remove them from the scene file and set them in `_ready()` instead via code:
```gdscript
bg_frame.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
```

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/unit_node.gd battlefield/unit_node.tscn battlefield/card_visual_state.gd battlefield/card_visual_assets.gd && git commit -m "refactor: layered card renderer with separated visual state and asset cache"
```

---

### Task 5: Construction Timer Display

**Files:**
- Modify: `prismata-3d/battlefield/unit_node.gd`

The construction timer is a **large centered number** showing turns remaining. It's separate from the cover overlay clock icon (which provides the visual "under construction" signal). The PixiJS viewer shows both: clock overlay + timer number.

- [ ] **Step 1: Add construction timer label to scene setup**

Add to `_ready()` in `unit_node.gd`, after the existing label setup:

```gdscript
var _build_timer_label: Label3D = null

# In _ready(), after _setup_status_icons():
func _setup_build_timer() -> void:
    _build_timer_label = Label3D.new()
    _build_timer_label.pixel_size = 0.005
    _build_timer_label.font_size = 28
    _build_timer_label.modulate = Color.WHITE
    _build_timer_label.outline_size = 6
    _build_timer_label.outline_modulate = Color.BLACK
    _build_timer_label.billboard = 0
    _build_timer_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    _build_timer_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    _build_timer_label.transform = Transform3D(FLAT_BASIS, Vector3(0, 0.028, 0.05))
    _build_timer_label.visible = false
    add_child(_build_timer_label)
```

- [ ] **Step 2: Show/hide in _apply_layers()**

Add at the end of `_apply_layers()`:

```gdscript
    # Construction timer number
    var build_turns = int(vs["build_turns"])
    if build_turns > 0:
        _build_timer_label.text = str(build_turns)
        _build_timer_label.visible = true
    else:
        _build_timer_label.visible = false
```

- [ ] **Step 3: Verify in Godot**

Navigate to a turn where units are under construction. Should see:
- Gold background (BACK_BOUGHT)
- Clock overlay (COVER_INVSPAWN)
- Large centered number showing turns remaining
- Slightly transparent card art (alpha 0.87)

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/unit_node.gd && git commit -m "feat: construction timer number overlay"
```

---

### Task 6: Update Audit Capabilities (Conservative)

**Files:**
- Modify: `tools/audit_visual_fidelity.js`

Only mark capabilities as `exact` where the implementation actually matches the audit logic. Where we know the implementation is approximate (missing edge cases), mark `approximate`.

- [ ] **Step 1: Update GODOT_CAPABILITIES**

```javascript
const GODOT_CAPABILITIES = {
    // === STATE PARITY ===
    layout_position:      'exact',
    card_sprite:          'exact',
    player_color_frame:   'approximate',   // Real textures but not pixel-identical to PixiJS
    construction_signal:  'approximate',   // BACK_BOUGHT + clock, but no INVBOUGHT distinction
    blocking_signal:      'approximate',   // Shield overlays, but missing NOTBLOCK
    attack_signal:        'approximate',   // Cage overlay, but no sellable handling
    chill_signal:         'approximate',   // Frost bg + snowflake, but no phase suppression
    damage_signal:        'approximate',   // ABSORB + BANG, but no WHITEPINK
    attack_icon:          'approximate',   // Real sprite + number, positioning may differ
    defense_icon:         'approximate',   // Real sprite + number, uses maxHp not metadata toughness
    construction_timer:   'approximate',   // Number shown, positioning may differ
    hp_icon:              'approximate',   // Real sprite + number
    frontline_icon:       'approximate',   // Real sprite
    delay_icon:           'approximate',   // Real sprite + number
    lifespan_icon:        'approximate',   // Real sprite + number
    charge_icon:          'approximate',   // Real sprite + number
    chill_icon:           'approximate',   // Real sprite + number
    p1_card_flip:         'unsupported',
    name_label:           'excluded',
    sellable_prompt:      'excluded',

    // === TRANSITION PARITY ===
    buy_effect:           'approximate',
    death_effect:         'approximate',
    damage_effect:        'unsupported',
    breach_effect:        'unsupported',
};
```

- [ ] **Step 2: Run 50-replay quick audit**

```bash
cd c:/libraries/PrismataAI && node tools/audit_visual_fidelity.js --batch 50 --seed 42
```

Record combined weighted parity. Should be significantly higher than 51.8% baseline.

- [ ] **Step 3: Run 1000-replay official audit**

```bash
cd c:/libraries/PrismataAI && node tools/audit_visual_fidelity.js --batch 1000 --seed 42
```

Record result as the Phase 1 official baseline for Phase 2 planning.

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/PrismataAI && git add tools/audit_visual_fidelity.js && git commit -m "feat: update Godot capabilities after Phase 1 (conservative ratings)"
```

---

## Verification Checklist

Use the 3 regression replays. Navigate through each, checking:

- [ ] Background frames show real textures (blue/red idle, gold construction, frost chilled, blocking colors, absorb orange)
- [ ] Card art visibly inset from background frame (colored border visible around edges)
- [ ] Clock overlay appears on units under construction
- [ ] Construction timer number visible on units being built (large, centered)
- [ ] Cage overlay appears on units assigned to attack
- [ ] Shield overlays appear on blocking units (blue P0, red P1)
- [ ] Damage bang overlay appears on damaged units
- [ ] Damage counter (red number, top-left) on damaged units
- [ ] Attack sword icon + number on attackers (bottom-right)
- [ ] Defense shield icon + number on non-fragile units (bottom-right)
- [ ] HP heart icon + number on fragile units (left stack)
- [ ] Variable icons (delay, doom, charge, chill) appear when applicable
- [ ] Snowflake overlay on fully-chilled units
- [ ] No z-fighting or visual artifacts from layered sprites
- [ ] No per-frame performance issues (no `load()` during update)
- [ ] NameLabel hidden by default (not cluttering the display)
- [ ] Audit weighted parity > 65% (conservative — "approximate" ratings limit the ceiling)
