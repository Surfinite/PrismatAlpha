# Godot Visual Parity — Phase 1: Card Layers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the approximate card rendering (colored quads + text labels) with asset-matched 10-layer card rendering using real textures from the PixiJS viewer.

**Architecture:** Extract PNG assets from `bin/asset/images/` to `prismata-3d/assets/`, refactor `unit_node.gd` from procedural mesh+labels to a layered Sprite3D stack matching the PixiJS UnitCard.ts 10-layer system. Port the visual-state decision tree from `tools/visual_state.js`.

**Tech Stack:** Godot 4.6 (GDScript), Node.js (extraction script)

**Spec:** `docs/superpowers/specs/2026-03-26-godot-visual-parity-design.md`

**Baseline:** 51.8% combined weighted parity (1000-replay audit). Target: ~75%.

---

## File Plan

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/extract_viewer_assets.js` | Create | Copy + rename PNGs from source dirs to Godot asset dirs |
| `prismata-3d/assets/backgrounds/*.png` | Create (10 files) | Background frame textures |
| `prismata-3d/assets/overlays/*.png` | Create (~10 files) | Cover + shading overlay textures |
| `prismata-3d/assets/icons/*.png` | Create (~15 files) | Status icons (sword, shield, heart, etc.) |
| `prismata-3d/assets/effects/*.png` | Create (2 files) | Skull + snowflake |
| `prismata-3d/battlefield/unit_node.gd` | Rewrite | 10-layer card renderer with visual state logic |
| `prismata-3d/battlefield/unit_node.tscn` | Modify | Add Sprite3D layer nodes |
| `tools/audit_visual_fidelity.js` | Modify | Update GODOT_CAPABILITIES |

---

### Task 1: Extract Assets

**Files:**
- Create: `tools/extract_viewer_assets.js`
- Create: `prismata-3d/assets/backgrounds/` (10 PNGs)
- Create: `prismata-3d/assets/overlays/` (10 PNGs)
- Create: `prismata-3d/assets/icons/` (15 PNGs)
- Create: `prismata-3d/assets/effects/` (2 PNGs)

The source PNGs already exist on disk — `build_viewer_bundle.js` reads from `bin/asset/images/` to create base64 bundles. We copy and rename.

- [ ] **Step 1: Write the extraction script**

```javascript
// tools/extract_viewer_assets.js
'use strict';
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'bin', 'asset', 'images');
const DST = path.resolve(__dirname, '..', '..', 'prismata-3d', 'assets');

const ASSETS = {
    backgrounds: {
        'bg_dead.png':       'cardbg/Card_Inver.png',
        'bg_block.png':      'cardbg/Card_Blue.png',
        'bg_busy.png':       'cardbg/Card_Grey.png',
        'bg_absorb.png':     'cardbg/Card_Orange.png',
        'bg_chilled.png':    'cardbg/Card_Blue_Frost.png',
        'bg_bought.png':     'cardbg/Card_Trans.png',
        'bg_whitepink.png':  'cardbg/Card_WhitePink.png',
        'bg_blockred.png':   'cardbg/Card_Red.png',
        'bg_busyblue.png':   'cardbg/Card_BlueGrey.png',
        'bg_busyred.png':    'cardbg/Card_RedGrey.png',
    },
    overlays: {
        'cover_blackclock.png':   'icons/extracted_hd/highlight_blackclock.png',
        'cover_goldclock.png':    'icons/extracted_hd/highlight_goldclock.png',
        'cover_cage.png':         'icons/extracted_hd/highlight_cage2.png',
        'cover_goldshield.png':   'icons/extracted_hd/highlight_goldshield.png',
        'cover_damagebang.png':   'icons/extracted_hd/highlight_damagebang.png',
        'shade_whiteshield.png':  'icons/extracted_hd/highlight_whiteshield.png',
        'shade_blueshield.png':   'icons/extracted_hd/highlight_blueshield.png',
        'shade_whiteshieldB.png': 'icons/extracted_hd/highlight_whiteshieldB.png',
        'shade_redshield.png':    'icons/extracted_hd/highlight_redshield.png',
    },
    icons: {
        'sword_blue.png':         'icons/mouseover/attack_big_blue.png',
        'icon_defend.png':        'icons/extracted_hd/icon_defend.png',
        'icon_clock.png':         'icons/extracted_hd/clock.png',
        'icon_hp.png':            'icons/status/status_hp.png',
        'icon_undefendable.png':  'icons/status/status_undefendable.png',
        'icon_delay.png':         'icons/status/status_delay.png',
        'icon_doom.png':          'icons/status/status_doom.png',
        'icon_charge0.png':       'icons/status/status_charge0.png',
        'icon_charge1.png':       'icons/status/status_charge1.png',
        'icon_charge2.png':       'icons/status/status_charge2.png',
        'icon_charge3.png':       'icons/status/status_charge3.png',
        'icon_tap.png':           'icons/status/status_tap.png',
        'icon_tap_on.png':        'icons/status/status_tap.png',
        'icon_attack.png':        'icons/status/icon_attack.png',
    },
    effects: {
        'skull_death.png':        'cardbg/Card_Dead.png',
        'chill_snowflake.png':    'cardbg/Card_Chilled.png',
    },
};

let copied = 0, missing = 0;
for (const [subdir, mapping] of Object.entries(ASSETS)) {
    const dstDir = path.join(DST, subdir);
    fs.mkdirSync(dstDir, { recursive: true });
    for (const [dstName, srcRel] of Object.entries(mapping)) {
        const srcPath = path.join(SRC, srcRel);
        const dstPath = path.join(dstDir, dstName);
        if (fs.existsSync(srcPath)) {
            fs.copyFileSync(srcPath, dstPath);
            copied++;
        } else {
            console.error(`MISSING: ${srcRel}`);
            missing++;
        }
    }
}
console.log(`Extracted ${copied} assets (${missing} missing)`);
```

- [ ] **Step 2: Run the extraction script**

Run: `cd c:/libraries/PrismataAI && node tools/extract_viewer_assets.js`
Expected: `Extracted NN assets (0 missing)` — all source PNGs found and copied.

If files are missing, check alternate paths in `bin/asset/images/`. The `icons/extracted_hd/` directory may use different naming — adjust the mapping.

- [ ] **Step 3: Verify extracted assets exist in Godot project**

Run: `ls c:/libraries/prismata-3d/assets/backgrounds/ c:/libraries/prismata-3d/assets/overlays/ c:/libraries/prismata-3d/assets/icons/ c:/libraries/prismata-3d/assets/effects/`

Expected: 10 background PNGs, ~9 overlay PNGs, ~14 icon PNGs, 2 effect PNGs.

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/PrismataAI && git add tools/extract_viewer_assets.js && git commit -m "feat(tools): asset extraction script for Godot viewer"
```

Note: The extracted PNGs live in the `prismata-3d` repo, not PrismataAI. Commit them there separately if that repo is tracked.

---

### Task 2: Refactor UnitNode to Layered Sprite3D Architecture

**Files:**
- Rewrite: `prismata-3d/battlefield/unit_node.gd`
- Modify: `prismata-3d/battlefield/unit_node.tscn`

Replace the current QuadMesh background + Label3D stats with a proper layered Sprite3D architecture. This task sets up the scene tree structure; Tasks 3-5 add the visual logic.

- [ ] **Step 1: Update the scene file to add layer nodes**

Replace `prismata-3d/battlefield/unit_node.tscn` with:

```
[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://battlefield/unit_node.gd" id="1"]

[node name="UnitNode" type="Node3D"]
script = ExtResource("1")

[node name="BackgroundFrame" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0.001, 0)

[node name="CardSkin" type="Sprite3D" parent="."]
pixel_size = 0.0078125
billboard = 0
transform = Transform3D(0.878, 0, 0, 0, 0, -0.878, 0, 0.878, 0, 0, 0.01, 0)

[node name="CoverOverlay" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
visible = false
transform = Transform3D(1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0.015, 0)

[node name="ShadingOverlay" type="Sprite3D" parent="."]
pixel_size = 0.01220
billboard = 0
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
visible = true

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

Key sizing decisions:
- BackgroundFrame: `pixel_size = 1/82 ≈ 0.01220` → 82px texture renders at 1.0 world units
- CardSkin: kept at `pixel_size = 0.0078125` (1/128) but transform scaled by 0.878 (72/82) so card art shows the border
- Cover/Shading overlays: same pixel_size as background (82px textures)
- NameLabel position: top-left area of card (-0.25, 0.022, -0.35)
- DamageLabel position: top-left corner (-0.4, 0.035, -0.4)

- [ ] **Step 2: Write the new unit_node.gd skeleton**

```gdscript
class_name UnitNode
extends Node3D

# Scene nodes
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

# Flat rotation for dynamic child nodes
const FLAT_BASIS = Basis(Vector3(1, 0, 0), Vector3(0, 0, -1), Vector3(0, 1, 0))

# Background textures (loaded once, shared across instances)
static var _bg_textures: Array = []
static var _bg_loaded: bool = false

# Background frame indices
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

# Status icon sprites (created dynamically)
var _fixed_icons: Array = []   # [Sprite3D, Label3D] pairs
var _variable_icons: Array = [] # [Sprite3D, Label3D] pairs
var _skull_sprite: Sprite3D = null
var _snowflake_sprite: Sprite3D = null

func _ready() -> void:
    _load_bg_textures()
    _setup_effects()
    _setup_status_icons()

static func _load_bg_textures() -> void:
    if _bg_loaded:
        return
    _bg_textures.resize(10)
    for i in range(BG_FILES.size()):
        var tex_path = "res://assets/backgrounds/%s.png" % BG_FILES[i]
        if ResourceLoader.exists(tex_path):
            _bg_textures[i] = load(tex_path)
        else:
            _bg_textures[i] = null
    _bg_loaded = true

func _setup_effects() -> void:
    # Skull death overlay
    _skull_sprite = Sprite3D.new()
    _skull_sprite.pixel_size = 0.01220
    _skull_sprite.billboard = 0
    _skull_sprite.transform = Transform3D(FLAT_BASIS, Vector3(0, 0.03, 0))
    _skull_sprite.visible = false
    var skull_path = "res://assets/effects/skull_death.png"
    if ResourceLoader.exists(skull_path):
        _skull_sprite.texture = load(skull_path)
    effect_container.add_child(_skull_sprite)

    # Chill snowflake overlay
    _snowflake_sprite = Sprite3D.new()
    _snowflake_sprite.pixel_size = 0.01220
    _snowflake_sprite.billboard = 0
    _snowflake_sprite.transform = Transform3D(FLAT_BASIS, Vector3(0, 0.03, 0))
    _snowflake_sprite.visible = false
    var snow_path = "res://assets/effects/chill_snowflake.png"
    if ResourceLoader.exists(snow_path):
        _snowflake_sprite.texture = load(snow_path)
    effect_container.add_child(_snowflake_sprite)

func _setup_status_icons() -> void:
    # Fixed icons: attack (bottom-right-left) and defense (bottom-right-right)
    # These are created as Sprite3D + Label3D pairs
    _create_fixed_icon(Vector3(0.15, 0.025, 0.32), "sword_blue")   # attack
    _create_fixed_icon(Vector3(0.35, 0.025, 0.32), "icon_defend")   # defense

func _create_fixed_icon(pos: Vector3, icon_key: String) -> void:
    var icon_sprite = Sprite3D.new()
    icon_sprite.pixel_size = 0.012
    icon_sprite.billboard = 0
    icon_sprite.transform = Transform3D(FLAT_BASIS, pos)
    icon_sprite.visible = false
    var tex_path = "res://assets/icons/%s.png" % icon_key
    if ResourceLoader.exists(tex_path):
        icon_sprite.texture = load(tex_path)
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

func setup(unit_data: Dictionary, p_owner: int) -> void:
    unit_id = int(unit_data["id"])
    card_id = unit_data["cardId"]
    unit_owner = p_owner
    name_label.text = unit_data.get("displayName", "")

    var sprite_path = "res://assets/card_sprites/%s.png" % card_id
    if ResourceLoader.exists(sprite_path):
        card_skin.texture = load(sprite_path)

func update_state(unit_data: Dictionary, p_owner: int) -> void:
    unit_owner = p_owner
    var state = unit_data.get("state", {})
    var stats = unit_data.get("stats", {})

    var vs = _compute_visual_state(state, stats)
    _apply_visual_state(vs, state, stats)

func _compute_visual_state(state: Dictionary, stats: Dictionary) -> Dictionary:
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
    var is_bottom = (unit_owner == 0)
    var is_dead = (mode == "dead")
    var is_fully_chilled = chilled >= hp and hp > 0

    # Phase 1: Base background frame
    var back_frame: int
    var show_skull = false
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

    # Phase 2: Construction override
    var cover_frame = COVER_EMPTY
    var shading_frame = SHADING_EMPTY

    if build_turns >= 1:
        back_frame = BACK_BOUGHT
        cover_frame = COVER_INVSPAWN  # Use INVSPAWN for all construction (no boughtThisPhase yet)
        card_alpha = 0.87
    elif attacking:
        cover_frame = COVER_ASSIGNED

    # Shading logic
    if blocking and not is_dead:
        shading_frame = SHADING_BLOCK if is_bottom else SHADING_REDBLOCK
    # Note: SHADING_NOTBLOCK requires defaultBlocking from card metadata (not yet available)

    # Phase 3: Damage override
    var damage_counter = 0
    if damage > 0 and not is_dead:
        cover_frame = COVER_BANG
        shading_frame = SHADING_EMPTY
        damage_counter = damage
        if blocking:
            back_frame = BACK_ABSORB
        else:
            back_frame = BACK_ABSORB

    return {
        "back_frame": back_frame,
        "cover_frame": cover_frame,
        "shading_frame": shading_frame,
        "card_alpha": card_alpha,
        "show_skull": show_skull,
        "show_snowflake": show_snowflake,
        "damage_counter": damage_counter,
        "attack": attack_val,
        "hp": hp,
        "max_hp": max_hp,
        "fragile": fragile,
        "build_turns": build_turns,
        "is_dead": is_dead,
        "damage": damage,
        "chilled": chilled,
        "delay": int(state.get("delay", 0)),
        "lifespan": int(state.get("lifespan", -1)),
        "charge": int(state.get("charge", 0)),
        "frontline": state.get("frontline", false),
    }

func _apply_visual_state(vs: Dictionary, state: Dictionary, stats: Dictionary) -> void:
    # Background frame
    var bg_idx = int(vs["back_frame"])
    if bg_idx >= 0 and bg_idx < _bg_textures.size() and _bg_textures[bg_idx] != null:
        bg_frame.texture = _bg_textures[bg_idx]

    # Card art alpha
    card_skin.modulate = Color(1, 1, 1, vs["card_alpha"])

    # Cover overlay
    var cover_idx = int(vs["cover_frame"])
    if cover_idx > 0 and cover_idx < COVER_FILES.size():
        var cover_path = "res://assets/overlays/%s.png" % COVER_FILES[cover_idx]
        if ResourceLoader.exists(cover_path):
            cover_overlay.texture = load(cover_path)
            cover_overlay.visible = true
        else:
            cover_overlay.visible = false
    else:
        cover_overlay.visible = false

    # Shading overlay
    var shading_idx = int(vs["shading_frame"])
    if shading_idx > 0 and shading_idx < SHADING_FILES.size():
        var shade_path = "res://assets/overlays/%s.png" % SHADING_FILES[shading_idx]
        if ResourceLoader.exists(shade_path):
            shading_overlay.texture = load(shade_path)
            shading_overlay.visible = true
        else:
            shading_overlay.visible = false
    else:
        shading_overlay.visible = false

    # Skull overlay
    _skull_sprite.visible = vs["show_skull"]

    # Snowflake overlay
    _snowflake_sprite.visible = vs["show_snowflake"]

    # Damage counter
    if int(vs["damage_counter"]) > 0:
        damage_label.text = str(vs["damage_counter"])
        damage_label.visible = true
    else:
        damage_label.visible = false

    # Name label
    name_label.text = name_label.text  # already set in setup()

    # --- Status icons ---
    _update_status_icons(vs)

func _update_status_icons(vs: Dictionary) -> void:
    var attack_val = int(vs["attack"])
    var max_hp = int(vs["max_hp"])
    var hp = int(vs["hp"])
    var fragile = vs["fragile"]
    var is_dead = vs["is_dead"]
    var build_turns = int(vs["build_turns"])

    # Fixed icon 0: Attack (sword)
    if attack_val > 0 and not is_dead:
        _fixed_icons[0][0].visible = true
        _fixed_icons[0][1].text = str(attack_val)
        _fixed_icons[0][1].visible = true
    else:
        _fixed_icons[0][0].visible = false
        _fixed_icons[0][1].visible = false

    # Fixed icon 1: Defense (shield) — non-fragile only
    if not fragile and max_hp > 0 and not is_dead:
        _fixed_icons[1][0].visible = true
        _fixed_icons[1][1].text = str(max_hp)
        _fixed_icons[1][1].visible = true
    else:
        _fixed_icons[1][0].visible = false
        _fixed_icons[1][1].visible = false

    # Variable icons: HP for fragile units, build timer
    # TODO in future tasks: add variable icon Sprite3D nodes for HP, delay, doom, charge, chill, frontline
    # For now, reuse the existing approach of creating labels dynamically
```

- [ ] **Step 3: Verify the scene loads in Godot**

Open `prismata-3d` in Godot, press Play. Verify:
- No script parse errors in the Output panel
- Cards render with background frame textures (if assets extracted)
- Card art is slightly smaller than background frame (0.878 scale shows border)

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/unit_node.gd battlefield/unit_node.tscn && git commit -m "refactor: layered Sprite3D card architecture with visual state"
```

---

### Task 3: Fix Asset Paths and Verify Rendering

This task handles the inevitable path mismatches from Task 1 extraction. Source PNG filenames may differ from what's expected.

**Files:**
- Modify: `tools/extract_viewer_assets.js` (fix paths)

- [ ] **Step 1: Run extraction and check for missing files**

```bash
cd c:/libraries/PrismataAI && node tools/extract_viewer_assets.js
```

Check output for `MISSING:` lines. For each missing file:
1. Search `bin/asset/images/` for alternate names: `find bin/asset/images -iname "*shield*"`, `find bin/asset/images -iname "*cage*"`, etc.
2. Update the mapping in `extract_viewer_assets.js`
3. Re-run until 0 missing

- [ ] **Step 2: Check extracted image dimensions**

```bash
# Use Node.js to check PNG dimensions of backgrounds (should be ~82x82)
node -e "const fs=require('fs'); const files=fs.readdirSync('c:/libraries/prismata-3d/assets/backgrounds'); files.forEach(f => { const buf=fs.readFileSync('c:/libraries/prismata-3d/assets/backgrounds/'+f); const w=buf.readUInt32BE(16); const h=buf.readUInt32BE(20); console.log(f, w+'x'+h); });"
```

If dimensions aren't 82×82, adjust `pixel_size` in `unit_node.tscn` accordingly:
- `pixel_size = 1.0 / actual_width` for backgrounds and overlays
- CardSkin transform scale = `(actual_bg_width - 10) / actual_bg_width` (5px inset each side)

- [ ] **Step 3: Launch Godot and verify visual output**

Open `prismata-3d`, play the scene. Navigate to turn 5+ using arrow keys. Verify:
- Background frames show colored textures (not solid color quads)
- Card art has visible border from background frame
- Cover overlays appear during construction (clock icon)
- Cover overlays appear for attacking units (cage)
- Shading overlays appear for blocking units (blue/red shield)

- [ ] **Step 4: Commit any path fixes**

```bash
cd c:/libraries/PrismataAI && git add tools/extract_viewer_assets.js && git commit -m "fix: correct asset extraction paths after verification"
```

---

### Task 4: Add Variable Status Icons

**Files:**
- Modify: `prismata-3d/battlefield/unit_node.gd`

Add the variable icon stack (left side of card) for HP, frontline, delay, doom, charge, and chill.

- [ ] **Step 1: Add variable icon creation to _setup_status_icons()**

Add this method to `unit_node.gd`:

```gdscript
func _create_variable_icon(y_offset: float, icon_key: String) -> Array:
    var pos = Vector3(-0.38, 0.025, -0.3 + y_offset * 0.18)
    var icon_sprite = Sprite3D.new()
    icon_sprite.pixel_size = 0.012
    icon_sprite.billboard = 0
    icon_sprite.transform = Transform3D(FLAT_BASIS, pos)
    icon_sprite.visible = false
    var tex_path = "res://assets/icons/%s.png" % icon_key
    if ResourceLoader.exists(tex_path):
        icon_sprite.texture = load(tex_path)
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
    num_label.transform = Transform3D(FLAT_BASIS, pos + Vector3(0, 0.005, 0.08))
    num_label.visible = false
    status_container.add_child(num_label)

    return [icon_sprite, num_label]
```

Update `_setup_status_icons()` to create variable icons:

```gdscript
func _setup_status_icons() -> void:
    # Fixed icons (bottom-right)
    _create_fixed_icon(Vector3(0.15, 0.025, 0.32), "sword_blue")
    _create_fixed_icon(Vector3(0.35, 0.025, 0.32), "icon_defend")

    # Variable icons (left stack) — created with placeholder positions,
    # repositioned dynamically in _update_status_icons based on which are visible
    _variable_icons.append(_create_variable_icon(0, "icon_hp"))
    _variable_icons.append(_create_variable_icon(1, "icon_undefendable"))
    _variable_icons.append(_create_variable_icon(2, "icon_delay"))
    _variable_icons.append(_create_variable_icon(3, "icon_doom"))
    _variable_icons.append(_create_variable_icon(4, "icon_charge0"))
    _variable_icons.append(_create_variable_icon(5, "icon_tap"))
```

- [ ] **Step 2: Update _update_status_icons() to show/hide variable icons**

```gdscript
func _update_status_icons(vs: Dictionary) -> void:
    var attack_val = int(vs["attack"])
    var max_hp = int(vs["max_hp"])
    var hp = int(vs["hp"])
    var fragile = vs["fragile"]
    var is_dead = vs["is_dead"]
    var build_turns = int(vs["build_turns"])
    var damage = int(vs["damage"])

    # Fixed icon 0: Attack
    _set_fixed_icon(0, attack_val > 0 and not is_dead, str(attack_val))

    # Fixed icon 1: Defense (non-fragile only)
    _set_fixed_icon(1, not fragile and max_hp > 0 and not is_dead, str(max_hp))

    # Variable icons — hide all first, then show applicable ones
    for pair in _variable_icons:
        pair[0].visible = false
        pair[1].visible = false

    if is_dead:
        return

    # Construction override: only show build timer + HP (if fragile)
    if build_turns > 0 and damage == 0:
        if fragile and hp > 0:
            _show_variable_icon(0, str(hp))  # HP
        return

    # Normal display
    var slot = 0
    # HP (fragile)
    if fragile and hp > 0:
        _show_variable_icon_at(0, slot, str(hp))
        slot += 1
    # Frontline
    if vs["frontline"]:
        _show_variable_icon_at(1, slot, "")
        slot += 1
    # Delay
    if int(vs["delay"]) > 0:
        _show_variable_icon_at(2, slot, str(vs["delay"]))
        slot += 1
    # Doom (lifespan)
    if int(vs["lifespan"]) > 0:
        _show_variable_icon_at(3, slot, str(vs["lifespan"]))
        slot += 1
    # Charge
    var charge = int(vs["charge"])
    if charge > 0:
        # Swap charge icon texture based on level
        var charge_level = mini(charge, 3)
        var tex_path = "res://assets/icons/icon_charge%d.png" % charge_level
        if ResourceLoader.exists(tex_path):
            _variable_icons[4][0].texture = load(tex_path)
        _show_variable_icon_at(4, slot, str(charge))
        slot += 1
    # Chill
    var chilled = int(vs["chilled"])
    if chilled > 0:
        var tap_key = "icon_tap_on" if chilled >= hp else "icon_tap"
        var tex_path = "res://assets/icons/%s.png" % tap_key
        if ResourceLoader.exists(tex_path):
            _variable_icons[5][0].texture = load(tex_path)
        _show_variable_icon_at(5, slot, str(chilled))
        slot += 1

func _set_fixed_icon(idx: int, show: bool, text: String) -> void:
    _fixed_icons[idx][0].visible = show
    _fixed_icons[idx][1].visible = show and text != ""
    if show:
        _fixed_icons[idx][1].text = text

func _show_variable_icon(idx: int, text: String) -> void:
    _variable_icons[idx][0].visible = true
    if text != "":
        _variable_icons[idx][1].text = text
        _variable_icons[idx][1].visible = true

func _show_variable_icon_at(icon_idx: int, slot: int, text: String) -> void:
    var pos = Vector3(-0.38, 0.025, -0.3 + slot * 0.18)
    _variable_icons[icon_idx][0].transform = Transform3D(FLAT_BASIS, pos)
    _variable_icons[icon_idx][0].visible = true
    if text != "":
        _variable_icons[icon_idx][1].transform = Transform3D(FLAT_BASIS, pos + Vector3(0, 0.005, 0.08))
        _variable_icons[icon_idx][1].text = text
        _variable_icons[icon_idx][1].visible = true
```

- [ ] **Step 3: Test in Godot**

Navigate to a turn with:
- Tarsiers (should show attack sword + HP heart for fragile)
- Walls (should show defense shield)
- Units under construction (should show build timer number)
- Navigate to defense phase to see blocking shields

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/prismata-3d && git add battlefield/unit_node.gd && git commit -m "feat: variable status icons (HP, delay, doom, charge, chill, frontline)"
```

---

### Task 5: Update Audit Capabilities and Verify Parity

**Files:**
- Modify: `tools/audit_visual_fidelity.js` (GODOT_CAPABILITIES)

- [ ] **Step 1: Update capability model**

In `tools/audit_visual_fidelity.js`, update GODOT_CAPABILITIES:

```javascript
const GODOT_CAPABILITIES = {
    // === STATE PARITY ===
    layout_position:      'exact',
    card_sprite:          'exact',
    player_color_frame:   'exact',         // was 'approximate' — now real textures
    construction_signal:  'exact',         // was 'approximate' — now BACK_BOUGHT + clock overlay
    blocking_signal:      'exact',         // was 'approximate' — now shield overlays
    attack_signal:        'exact',         // was 'approximate' — now cage overlay
    chill_signal:         'exact',         // was 'approximate' — now frost bg + snowflake
    damage_signal:        'approximate',   // BACK_ABSORB + COVER_BANG, but no WHITEPINK distinction
    attack_icon:          'exact',         // real sword sprite + number
    defense_icon:         'exact',         // real shield sprite + number
    construction_timer:   'exact',         // build timer number
    hp_icon:              'exact',         // heart sprite + number
    frontline_icon:       'exact',         // undefendable icon
    delay_icon:           'exact',         // delay icon + number
    lifespan_icon:        'exact',         // doom icon + number
    charge_icon:          'exact',         // charge icon + number
    chill_icon:           'exact',         // tap icon + number
    p1_card_flip:         'unsupported',   // still not implemented
    name_label:           'excluded',
    sellable_prompt:      'excluded',

    // === TRANSITION PARITY ===
    buy_effect:           'approximate',
    death_effect:         'approximate',
    damage_effect:        'unsupported',
    breach_effect:        'unsupported',
};
```

- [ ] **Step 2: Run 50-replay audit**

```bash
cd c:/libraries/PrismataAI && node tools/audit_visual_fidelity.js --batch 50 --seed 42
```

Expected: Combined weighted parity should jump significantly — target ~75%.

- [ ] **Step 3: Run 1000-replay audit for official baseline**

```bash
cd c:/libraries/PrismataAI && node tools/audit_visual_fidelity.js --batch 1000 --seed 42
```

Record the result. This becomes the Phase 1 baseline for Phase 2 planning.

- [ ] **Step 4: Commit**

```bash
cd c:/libraries/PrismataAI && git add tools/audit_visual_fidelity.js && git commit -m "feat: update Godot capabilities after Phase 1 card layers"
```

---

## Verification Checklist

After all tasks, verify in Godot by navigating through a full replay:

- [ ] Background frames change color based on unit state (blue idle, red idle, gold construction, frost chilled, blocking colors)
- [ ] Card art is visibly inset from background frame (border visible)
- [ ] Clock overlay appears on units under construction
- [ ] Cage overlay appears on units assigned to attack
- [ ] Shield overlays appear on blocking units (blue for P0, red for P1)
- [ ] Damage bang overlay appears on damaged units
- [ ] Attack sword icon + number visible on attackers (bottom-right area)
- [ ] Defense shield icon + number visible on non-fragile units
- [ ] HP heart icon + number visible on fragile units (left side)
- [ ] Construction timer number visible on units being built
- [ ] Skull overlay on dead units (if any appear in snapshot)
- [ ] Variable icons (delay, doom, charge, chill) appear when applicable
- [ ] Audit weighted parity > 70%
