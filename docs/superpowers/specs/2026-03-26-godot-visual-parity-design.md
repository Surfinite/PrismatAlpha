# Godot Visual Parity Renderer — Design Spec

**Goal:** Bring the Godot 3D replay viewer (`c:\libraries\prismata-3d\`) to full visual parity with the PixiJS replay viewer, implementing the complete AS3/PixiJS card rendering pipeline and board-level HUD elements.

**Approach:** Asset-matched — use real textures extracted from the PixiJS bundle/SWF, not procedural approximations. The hard work is the rendering logic (state machines, positioning, layering); using real assets costs the same implementation effort as placeholders.

**Parity target:** PixiJS viewer at `<ladder>-site/src/components/game-renderer/`. Measured by the visual fidelity audit tool (`tools/audit_visual_fidelity.js`).

**Platform:** Desktop first (Godot editor / exported executable). Web export viability preserved but not primary target.

**Snapshot schema:** Extended as needed per phase, not front-loaded. Missing fields (`boughtThisPhase`, `sellable`, `deadness` cause) added when the layer that needs them is implemented.

---

## Current Baseline

| Metric | Value |
|--------|-------|
| Audit weighted parity | 52.2% |
| Exact state parity | 41.6% |
| Card layers implemented | 3/8 (backMC approximate, cardSkin exact, statusOverlay approximate) |
| Board HUD elements | 0/6 |

---

## Architecture

### UnitCard Scene Tree

Each unit is a layered `Node3D` scene mirroring the PixiJS 10-layer `UnitCard`:

```
UnitNode (Node3D)
 ├─ BackgroundFrame   (Sprite3D)   Layer 0: 82x82 texture, 10 frame variants
 ├─ CardSkin          (Sprite3D)   Layer 1: 72x72 card art, inset 5px from edge
 ├─ CoverOverlay      (Sprite3D)   Layer 2: 82x82, 6 states (clock/cage/bang/shield/empty)
 ├─ ShadingOverlay    (Sprite3D)   Layer 3: 82x82, 5 states (block shields)
 ├─ StatusOverlay     (Node3D)     Layer 5: icon + number container
 │   ├─ FixedIcons    (Node3D)     Bottom-right: attack sword, defense shield
 │   └─ VariableIcons (Node3D)     Left stack: HP, delay, doom, charge, chill, frontline
 ├─ NameLabel         (Label3D)    Layer 6: card name, 8px bold white, black outline
 ├─ EffectContainer   (Node3D)     Layer 8: skull (54x54), chill snowflake (44x44)
 └─ DamageLabel       (Label3D)    Layer 9: red damage number, top-left, on-demand
```

Layer 4 (borderMC) is unused in PixiJS — omitted.
Layer 7 is reserved — omitted.

All sprite layers lie flat (rotated to face orthographic top-down camera) with Y-position controlling z-order:
- BackgroundFrame: Y=0.001
- CardSkin: Y=0.01
- CoverOverlay: Y=0.015
- ShadingOverlay: Y=0.018
- StatusOverlay icons: Y=0.025
- NameLabel: Y=0.022
- EffectContainer: Y=0.03
- DamageLabel: Y=0.035

### Board Scene Tree

```
Battlefield (Node3D)
 ├─ TurnIndicator     (MeshInstance3D)   Colored wash over active player's half
 ├─ TopBoard          (Node3D)           P1 unit rows (front/middle/back)
 ├─ Divider           (MeshInstance3D)   Center line (exists)
 ├─ BottomBoard       (Node3D)           P0 unit rows (front/middle/back)
 ├─ MidlineHUD        (Node3D)           Attack swords, defense shields, breach warnings
 ├─ BigSword          (Sprite3D)         Large sword + attack number (defense/breach phases)
 ├─ ResourceBars      (Control)          Mana gems + counts, both players (2D HUD overlay)
 └─ BuyPanel          (Control)          Card list with cost pips + supply bars (2D HUD overlay)
```

ResourceBars and BuyPanel use Godot's 2D Control system (CanvasLayer HUD) rather than 3D nodes, since they're fixed-position UI elements unaffected by the camera.

---

## Card Dimensions

All measurements from AS3/PixiJS constants:

| Constant | Value | Description |
|----------|-------|-------------|
| CARD_HEIGHT | 82px | Full card size (background frame) |
| CARD_WIDTH | 83px | Layout grid (1px wider for spacing) |
| ART_INSET | 5px | Card art offset from background edge |
| ART_SIZE | 72px | Card art image size (82 - 2×5) |
| STATUS_SIZE | 18px | Icon sprite size |
| SKULL_SIZE | 54px | Death skull sprite |
| SNOWFLAKE_SIZE | 44px | Chill snowflake sprite (0.3 scale of 148px source) |

In Godot world units, the existing `pixel_size = 0.0078125` (1/128) makes a 128px sprite = 1.0 world unit. Card sprites are currently 128x128px textures rendered at 1.0×1.0 world units. The background frame (82×82px native) should be scaled to match — either by using 82px textures at `pixel_size = 1.0/82` or by scaling within the existing coordinate system.

---

## Layer 0: Background Frame (backMC)

### Frame States

10 texture variants driven by unit state:

| Index | Constant | Texture File | Condition |
|-------|----------|-------------|-----------|
| 0 | BACK_DEAD | bg_dead.png | `deadness !== 'alive'` |
| 1 | BACK_BLOCK | bg_block.png | `blocking && isBottomPlayer` |
| 2 | BACK_BUSY | bg_busy.png | Default (unused in practice) |
| 3 | BACK_ABSORB | bg_absorb.png | Partially damaged, blocking, defense phase |
| 4 | BACK_BLOCK_FROST | bg_chilled.png | `disruptDamage >= health && health > 0` |
| 5 | BACK_BOUGHT | bg_bought.png | `constructionTime >= 1` |
| 6 | BACK_WHITEPINK | bg_whitepink.png | Dead with damage |
| 7 | BACK_BLOCKRED | bg_blockred.png | `blocking && isTopPlayer` |
| 8 | BACK_BUSYBLUE | bg_busyblue.png | Idle, bottom player (P0) |
| 9 | BACK_BUSYRED | bg_busyred.png | Idle, top player (P1) |

### State Selection Logic

Four-phase decision tree (from `visual-state.ts`):

**Phase 1 — Base frame:**
1. If dead → BACK_DEAD
2. Else if fully chilled → BACK_BLOCK_FROST
3. Else if blocking → BACK_BLOCK (converted to BACK_BLOCKRED if top player)
4. Else → BACK_BUSYBLUE (bottom) or BACK_BUSYRED (top)

**Phase 2 — Construction/role override:**
- If `constructionTime >= 1` → BACK_BOUGHT, alpha=0.87
- If `role='assigned'` → keep base frame (cover overlay handles the cage)

**Phase 3 — Damage override (if damage > 0):**
- Partially damaged + blocking + defense phase → BACK_ABSORB
- Blocking + killed → BACK_DEAD + skull
- Partially damaged + not dead → BACK_ABSORB
- Otherwise → BACK_WHITEPINK + skull

### Alpha Values

- Normal: 0.999 (PixiJS hack for Flash rendering — Godot can use 1.0)
- Under construction: 0.87

---

## Layer 2: Cover Overlay (coverMC)

6 states, full-card (82×82px) overlay sprites:

| Index | Constant | Texture File | Condition |
|-------|----------|-------------|-----------|
| 0 | COVER_EMPTY | (none) | Default — invisible |
| 1 | COVER_INVSPAWN | highlight_blackclock.png | Under construction (spawned) |
| 2 | COVER_INVBOUGHT | highlight_goldclock.png | Under construction (just bought) |
| 3 | COVER_ASSIGNED | highlight_cage2.png | Assigned to attack |
| 4 | COVER_PROMPT | highlight_goldshield.png | Sellable blocker prompt |
| 5 | COVER_BANG | highlight_damagebang.png | Taking damage |

**Snapshot schema needed:** `boughtThisPhase` for INVBOUGHT vs INVSPAWN distinction; `role='sellable'` for PROMPT. Until added, use INVSPAWN for all construction and skip PROMPT (mark as unauditable).

---

## Layer 3: Shading Overlay (shadingMC)

5 states, full-card (82×82px) shield overlay sprites:

| Index | Constant | Texture File | Condition |
|-------|----------|-------------|-----------|
| 0 | SHADING_EMPTY | (none) | Default — invisible |
| 1 | SHADING_NOTBLOCK | highlight_whiteshield.png | Can block but isn't |
| 2 | SHADING_BLOCK | highlight_blueshield.png | Blocking (P0) |
| 3 | SHADING_DEAD_BLOCK | highlight_whiteshieldB.png | Dead blocker |
| 4 | SHADING_REDBLOCK | highlight_redshield.png | Blocking (P1) |

**Selection logic:**
- `defaultBlocking && !blocking` → NOTBLOCK
- Dead + blocking + damage=0 → DEAD_BLOCK
- Blocking → BLOCK (converted to REDBLOCK if top player)
- Otherwise → EMPTY

---

## Layer 5: Status Overlay

### Fixed Icons (Bottom-Right Corner)

| Icon | Asset Key | Position (px) | Condition |
|------|-----------|---------------|-----------|
| Attack | sword_blue (18×18) | x=22, y=44 | `attack > 0` |
| Defense | icon_defend (18×18) | x=58, y=44 | `!fragile && toughness > 0` |
| Spell | icon_clock (18×18) | x=58, y=44 | `!fragile && isSpell` |

Numbers rendered at icon position + offset (-7, +4), 11px bold white with 3px black stroke.

### Variable Icons (Left Side, Vertical Stack)

Stacked top-to-bottom at x=1, each icon 18×18px with 20px vertical spacing:

| Priority | Icon | Asset Key | Count | Condition |
|----------|------|-----------|-------|-----------|
| 1 | Frontline | icon_undefendable | — | `isFrontline` |
| 2 | HP | icon_hp | health | `isFragile` |
| 3 | Delay | icon_delay | delay | `delay > 0` |
| 4 | Doom | icon_doom | lifespan | `lifespan > 0` |
| 5 | Charge | icon_charge{0-3} | charge | `charge > 0` |
| 6 | Chill | icon_tap / icon_tap_on | disruptDamage | `disruptDamage > 0` |

**Construction override:** When `constructionTime > 0 && damage === 0`, suppress all variable icons except HP (for fragile units). Show construction timer number (14px bold white) instead.

Numbers at icon position + offset (-2, +7), 11px bold white with 3px black stroke.

---

## Layer 6: Name Label

- Position: (20, 6) relative to card top-left (in 82px card space)
- Font: 8px, bold, white
- Stroke: 3px black outline
- Text: card display name

---

## Layer 8: Effect Container

### Skull (Death)
- Size: 54×54px, centered at (14, 16) within card
- Asset: `skull_death`
- Visible when: `isDead` (any deadness except 'alive')
- Animation: scale 0.3→1.0 over 300ms with ease-out-back overshoot (Phase 3)

### Chill Snowflake
- Size: 44×44px (0.3 scale of 148px source), centered at (19, 21)
- Asset: `chill_snowflake`
- Visible when: `disruptDamage >= health && phase !== 'defense'`

---

## Layer 9: Damage Counter

- Position: (3, 3) — top-left corner
- Font: 12px, bold, red (0xFF0000)
- Stroke: 3px black outline
- Visible when: `damageCounter > 0`
- Created on-demand (not present when no damage)

---

## Board HUD: Resource Bars

2D HUD overlay (CanvasLayer), one bar per player:

- **Position:** Top-left (P1) and bottom-left (P0)
- **Layout:** Horizontal row of mana gem icons (24×24px each), 28px apart
- **Resources:** Gold, Green, Blue, Red, Energy — each with gem icon + count number
- **Gold estimate:** Optional "(min-max)" text in yellow (0xFFDD44), left of gold gem
- **Number font:** 14px bold white, centered on gem, y-offset 8px

### Mana String Parsing

Cost strings use format: `digits + [G|B|C|H]*`
- Digits = gold count
- G = green, B = blue, C = red (Crimson), H = energy

---

## Board HUD: Midline HUD

3D nodes positioned at the center divider line:

### Attack/Defense Icons
- Size: 44×44px
- **Left side:** P1 attack sword (above divider), P0 defense shield (below divider)
- **Right side:** P0 attack sword (below divider), P1 defense shield (above divider)
- Numbers: 30px bold white, 6px black stroke, centered on icon
- Gap: 4px between icons vertically

### Breach Warning
- Trigger: attack > defense for that side
- Shield swaps to `shield_big_glow` texture
- Breach octagon icon (`interro`, 28×28) appears right of shield

### Chill Display
- Snowflake icon (22×22) with count number (16px)
- Shown when player has chill > 0

---

## Board HUD: Buy Panel

2D HUD overlay (CanvasLayer), right side of screen:

### BuyCard Layout (per card)
- Size: 130×36px, dark background (0x0e1e2e, alpha 0.85), rounded corners
- **Art thumbnail:** 28×28px, right side (x=100, y=1)
- **Name:** 9px bold white, top-left (x=3, y=2)
- **Cost pips:** 10×10px colored circles, horizontal row at (x=3, y=13)
  - Gold: 0xFFCC00, Green: 0x44CC44, Blue: 0x4488FF, Red: 0xCC3333, Energy: 0x9966FF
- **Supply bar:** 5px height at bottom, segmented, green fill for remaining supply
- **Supply label:** 8px, right-aligned (x=98, y=14), remaining count
- **Sold out:** alpha=0.4 when remaining=0

### Card Order
1. Base cards: Drone, Engineer, Conduit, Blastforge, Animus
2. 4px separator line
3. Randomizer cards (from deck)

---

## Board HUD: Turn Indicator

- Full-width colored rectangle covering active player's board half
- Alpha: 0.08 (very subtle wash)
- Color by phase:
  - `defense` → 0x3399FF (blue)
  - `action` → 0xFFCC00 (yellow)
  - `confirm` → 0xFFFFFF (white)
  - `breach` → 0xFF3333 (red)

---

## Board HUD: Big Sword

- Shown during defense/breach phases when attack > 0
- Size: 180×180px (scaled from 461px source), alpha 0.7
- Position: Centered horizontally, vertically centered on defending player's board half
- Attack number: 64px bold white, 8px black stroke, alpha 0.85, centered on sword

---

## Asset Pipeline

### Source
- PixiJS bundle: base64-encoded assets in the JS bundle
- SWF extraction: existing pipeline (`extract_swf_sprites.py`)
- Card art: already extracted to `prismata-3d/assets/card_sprites/`

### Target Directories

```
prismata-3d/assets/
 ├─ card_sprites/       (existing — 143 card art PNGs)
 ├─ backgrounds/        (new — 10 background frame PNGs, 82×82)
 ├─ overlays/           (new — cover + shading overlay PNGs, 82×82)
 ├─ icons/              (new — status icon PNGs, 18×18)
 ├─ effects/            (new — skull 54×54, snowflake 44×44)
 └─ hud/                (new — sword, shield, gems, breach octagon)
```

### Extraction Script

New tool: `tools/extract_viewer_assets.js` — reads the PixiJS bundle's base64-encoded assets, decodes to PNG files, saves to the target directories. One-time extraction with re-run capability.

---

## Phased Delivery

### Phase 1: Card Layers (target: ~75% parity)
- Extract background, overlay, icon, effect assets from PixiJS bundle
- Refactor UnitNode to layered scene tree (10 layers)
- Implement full visual-state decision tree (4-phase logic from `visual-state.ts`)
- Implement complete status overlay system: fixed icons (attack, defense, spell) + all variable icons (HP, frontline, delay, doom, charge, chill) with real sprites and positioned numbers
- Add name label, damage counter, skull overlay, chill snowflake
- Update audit tool capabilities → most features become `exact`

### Phase 2: Board HUD (target: ~85% parity)
- Add ResourceBar as 2D HUD (CanvasLayer)
- Add MidlineHUD (attack/defense/chill/breach)
- Add TurnIndicator (phase-colored wash)
- Add BuyPanel as 2D HUD
- Add BigSword overlay for defense/breach phases

### Phase 3: Effects & Animation
- Skull pop-in animation (300ms, ease-out-back)
- Floating damage text (880ms, float + fade)
- Breach red flash (400ms fade)
- BigSword tween animations

### Phase 4: Visual Polish
- P1 card art vertical flip
- Background images with color matrix filters
- Player portraits + rings
- Gold estimate display

---

## Measurement

After each phase, update `GODOT_CAPABILITIES` in `tools/audit_visual_fidelity.js` and run:

```bash
node tools/audit_visual_fidelity.js --batch 50 --seed 42
```

Compare weighted parity against baseline (52.2%) and phase targets.

---

## Key Files

### Godot (prismata-3d)
| File | Role |
|------|------|
| `battlefield/unit_node.gd` | Card rendering (refactored to 10-layer system) |
| `battlefield/unit_node.tscn` | Card scene (add layer nodes) |
| `battlefield/battlefield.gd` | Board layout, reconciliation, HUD orchestration |
| `hud/resource_bar.gd` | Resource display (new) |
| `hud/buy_panel.gd` | Buy panel (new) |
| `hud/midline_hud.gd` | Attack/defense/breach display (new) |

### PrismataAI (reference + tools)
| File | Role |
|------|------|
| `tools/visual_state.js` | Reference implementation of visual-state decision tree |
| `tools/status_overlay.js` | Reference implementation of status icon logic |
| `tools/audit_visual_fidelity.js` | Parity measurement tool |
| `tools/extract_viewer_assets.js` | Asset extraction from PixiJS bundle (new) |
| `tools/replay_to_snapshots.js` | Snapshot generator (extended per phase as needed) |

### PixiJS (reference only)
| File | Role |
|------|------|
| `game-renderer/UnitCard.ts` | 10-layer card renderer |
| `game-renderer/visual-state.ts` | Visual state decision tree |
| `game-renderer/StatusOverlay.ts` | Status icon system |
| `game-renderer/BoardRenderer.ts` | Board layout + HUD orchestration |
| `game-renderer/BuyPanel.ts` + `BuyCard.ts` | Buy panel |
| `game-renderer/ResourceBar.ts` | Resource display |
| `game-renderer/BreachEffects.ts` | Animated effects |
| `game-renderer/constants.ts` | All constants, colors, font configs |
