# Browser Game Viewer — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Authors:** Surfinite + Claude

## Overview

A PixiJS 8 game board renderer that replaces the current HTML/CSS board in the <ladder> React site. Renders a faithful recreation of the original Prismata Flash client's board using the decompiled AS3 source as reference.

**Target fidelity (Phase B):** Card art + full state feedback — colored backgrounds by owner/state, construction dimming with clock overlays, blocker highlighting, status icons (HP/charge/delay/doom/tap/attack), dead/chill/damage effects as static sprites. Architecture supports Phase C transitions and animations without rework.

## Phased Roadmap

| Phase | Scope | Rendering | AS3 toggle equivalent |
|---|---|---|---|
| **A** | Card art + clean layout | Static board with card images, proper 3-row layout, buy panel | — |
| **B (target)** | Card art + state feedback | All visual states: 10 background variants, 6 cover overlays, shading, status icons, effectContainer sprites | `PARTICLE_QUALITY=OFF`, `ANIMATIONS_ON=false`, `DISABLE_ANIMATED_SKINS=true` |
| **C (future)** | Transitions | Smooth state transitions, purchase animations (topWhiteQuad), card movement tweens, death/attack effects | `ANIMATIONS_ON=true`, `PARTICLE_QUALITY=LOW` |
| **D (future)** | Near-parity | Full particle system (death, chill, snipe lasers), animated card skins, 40+ AS3 effect classes | `PARTICLE_QUALITY=NORMAL`, `DISABLE_ANIMATED_SKINS=false`, `BREACHFLASH_ON=true` |

**AS3 quality toggles (from Options.as):** The original client has explicit settings that gate visual features into the same tiers as our phases. This validates our phase boundaries and provides clear implementation guidance — Phase B renders what the client renders with all effects disabled. Key toggles:
- **`PARTICLE_QUALITY`**: NORMAL (full) / LOW (0.3x emission) / OFF (no particles). Checked in `PDParticleSystem` constructor.
- **`ANIMATIONS_ON`**: Master switch for all animation events (arrival, death, damage, mana). Gates UIEvent emission in `Game.as`.
- **`DISABLE_ANIMATED_SKINS`**: Static card art vs animated skin sprites.
- **`BREACHFLASH_ON`**: Screen flash on breach (accessibility toggle).
- **`ANIMATION_SPEED`**: NORMAL (1x) / SLOW (1.3x) / VSLOW (1.6x) duration multipliers.

## Architecture

### Integration Model

PixiJS canvas embedded in the existing React page. React owns the page chrome (player info, playback controls, turn counter, phase indicator). PixiJS renders the entire game board including resource bars and buy panel.

```
┌─────────────────────────────────────────────┐
│  React: Player info, turn counter, phase    │
├─────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────┐│
│ │  P1 Resources (gold/B/G/C/H/atk/def)    ││
│ │┌───────┬─────────────────────────────────┐│
│ ││ Buy   │  P1 Back row                    ││
│ ││ Panel │  P1 Middle row                  ││
│ ││ (base │  P1 Front row [sword]   [sword] ││
│ ││  +    │  ──── center divider ────       ││
│ ││ rand) │  P0 Front row [sword]   [sword] ││
│ ││       │  P0 Middle row                  ││
│ ││       │  P0 Back row                    ││
│ │└───────┴─────────────────────────────────┘│
│ │  P0 Resources (gold/B/G/C/H/atk/def)    ││
│ └──────────────────────────────────────────┘│
│  PixiJS Canvas                              │
├─────────────────────────────────────────────┤
│  React: Playback controls, state index      │
└─────────────────────────────────────────────┘
```

### Data Flow

Same pattern as the existing viewer, with minor engine export additions (see Engine Bundle Changes).

1. React page loads `prismata-engine.js` bundle (existing)
2. On state change, React calls `PrismataViewer.getGameState()` + `PrismataViewer.getCardMeta()`
3. React passes state to `BoardRenderer.updateState(gameState, cardMeta)`
4. BoardRenderer updates PixiJS sprites in-place using `id` to correlate units across states (no teardown/rebuild)

### Code Location

**Repository:** <ladder> (alongside existing viewer code)

The renderer is a new module consumed by the existing `[gameId]/page.tsx`. The page.tsx retains its React chrome but swaps the HTML board rendering for a canvas mount point.

## Class Hierarchy

Mirrors the AS3 decompiled source class-for-class. One intentional deviation: BuyPanel uses `STATE_DOUBLE` (both columns always visible) rather than the AS3 default `STATE_SINGLE` with tab switching, since this is more convenient for a viewer.

| PixiJS Class | AS3 Source | Responsibility |
|---|---|---|
| `BoardRenderer` | `GameScreen` | Top-level PixiJS Application, canvas management, state dispatch |
| `BoardView` | `UIBoard` | Per-player board, contains 3 rows + sword barriers |
| `RowView` | `UIRow` | Horizontal lane layout with cramming algorithm |
| `PileView` | `UIPile` | Horizontal stack of same-type unit cards |
| `UnitCard` | `UIInst` | Individual unit card, 10-layer rendering |
| `StatusOverlay` | `UIStatus` | HP/charge/delay/doom/tap/attack/spell icons |
| `BuyPanel` | `UIBuyBox` | Two always-visible columns (base + randomizer) |
| `BuyCard` | `UIPurchasable` | Card art + cost icons + supply indicator |
| `ResourceBar` | `UIPlayerMana` | Gold/B/G/C/H + attack/defense totals |

## Unit Card Rendering (UnitCard)

### Layer Stack

10 layers per card, back to front, matching AS3 `UIInst.createUIComponents()` (UIInst.as lines 419-426). Note: indices 5-6 are status then name (not the reverse — verified against AS3 `addChild` order):

| Index | Layer | AS3 Name | Description |
|---|---|---|---|
| 0 | Card background | `backMC` | 82x82px base, 10 variants by state + owner |
| 1 | Card skin | `cardSkin` | Unit art sprite (inserted via `addChildAt` at index 1). Phase B: static 300x300 PNG scaled to fit. Phase C+: animated skin sprites (`DISABLE_ANIMATED_SKINS` toggle) |
| 2 | Cover overlay | `coverMC` | 6 state overlays (clock, cage, shield, bang) |
| 3 | Shading overlay | `shadingMC` | 5 states including SHADING_EMPTY (`emptypixel`) for blocking/non-blocking visual feedback |
| 4 | Border glow | `borderMC` | Clickable highlight (yellow/white). Interactive mode only |
| 5 | Status icons | `statusContainer` | 14 status types (HP, frontline, delay, doom, charge 0-3, tap/tap_on, attack, spell, defend). 18px icons, 4px spacing. Positioned at (2, 17) in card space. Has `fixedStatusContainer` and `variableStatusContainer` sub-containers — port `UIStatus.changed()` from AS3 source |
| 6 | Name image | `nameImage` | Pre-rendered name sprite (`instName_` + cardUIName). Phase B: BitmapFont fallback |
| 7 | White flash | `topWhiteQuad` | Purchase landing animation. Default alpha=0. Used in Phase C |
| 8 | Effect container | `effectContainer` | Skull (41,43), chill snowflake (41,43), frontline crosshair |
| 9* | Damage counter | `damageCounter` | `UIInstNumber` at (3,3). Direct child of UnitCard, NOT inside effectContainer. Renders numbers via bitmap font atlas (`CommonAssets.NUMBERS_SMALL`) |

### Card Background Variants (10 frames)

| Frame | Constant | Texture | When |
|---|---|---|---|
| 0 | BACK_DEAD | `Card_Inver` | Dead/greyed out |
| 1 | BACK_BLOCK | `Card_Blue` | Blocking (blue player) |
| 2 | BACK_BUSY | `Card_Grey` | Generic grey (NOT default) |
| 3 | BACK_ABSORB | `Card_Orange` | Absorbing damage |
| 4 | BACK_BLOCK_FROST | `Card_Blue_Frost` | Chilled + blocking |
| 5 | BACK_BOUGHT | `Card_Trans` | Under construction (transparent) |
| 6 | BACK_WHITEPINK | `Card_WhitePink` | Fully damaged |
| 7 | BACK_BLOCKRED | `Card_Red` | Blocking (red player) |
| 8 | BACK_BUSYBLUE | `Card_BlueGrey` | **Normal active (blue player) — DEFAULT P0** |
| 9 | BACK_BUSYRED | `Card_RedGrey` | **Normal active (red player) — DEFAULT P1** |

### Cover Overlay Variants (6 frames)

| Frame | Constant | Texture | When |
|---|---|---|---|
| 0 | COVER_EMPTY | `emptypixel` | Nothing |
| 1 | COVER_INVSPAWN | `highlight_blackclock` | Spawning/constructing |
| 2 | COVER_INVBOUGHT | `highlight_goldclock` | Just purchased |
| 3 | COVER_ASSIGNED | `highlight_cage2` | Assigned for ability |
| 4 | COVER_PROMPT | `highlight_goldshield` | Blocker prompt |
| 5 | COVER_BANG | `highlight_damagebang` | Taking damage |

### State Mapping

**Port `UIInst.update()` (UIInst.as lines 800-960) faithfully.** The full state machine is ~150 lines with complex nested branching that cannot be accurately summarized. The simplified version below captures the major branches for reference, but the implementation must follow the AS3 source.

**Player color convention:** The AS3 uses `colorOnBottom` to determine which player gets blue vs. red backgrounds. For the replay viewer, `colorOnBottom = 0` (P0 is always blue/bottom). Background and shading colors are selected by `owner == colorOnBottom`, not by raw owner index.

**Key branches (reference only — see AS3 source for complete logic):**

```
# Default state
alive, idle            → back: BACK_BUSYBLUE (owner==colorOnBottom) or BACK_BUSYRED
                         cover: COVER_EMPTY

# Constructing
constructing           → back: BACK_BOUGHT (Card_Trans)
                         card alpha: 0.87
                         cover: COVER_INVBOUGHT or COVER_INVSPAWN

# Dead
dead                   → back: BACK_DEAD
                         effectContainer: skull icon at (41, 43)

# Blocking (alive, not constructing)
blocking               → back: BACK_BLOCK (blue player) or BACK_BLOCKRED (red player)
                         shading: SHADING_BLOCK or SHADING_REDBLOCK (by player color)

# Chill (disruptDamage >= health && health > 0 && phase != DEFENSE)
fully chilled          → back: BACK_BLOCK_FROST
                         effectContainer: chill snowflake at (41, 43)
                         (snowflake hidden during defense phase)

# Damage states (requires `damage` field — see Engine Bundle Changes)
blocking + partial dmg + defense phase + !fragile
                       → back: BACK_ABSORB (Card_Orange), COVER_BANG
                         effectContainer: damage counter at (3, 3)
blocking + dead (dmg)  → back: BACK_DEAD, skull
partial dmg (not dead) → back: BACK_ABSORB
fully damaged          → back: BACK_WHITEPINK, skull

# Sellable role (blocker assignment phase)
ROLE_SELLABLE + blocking    → COVER_PROMPT + SHADING_BLOCK or SHADING_DEAD_BLOCK
ROLE_SELLABLE + !blocking   → SHADING_NOTBLOCK
ROLE_SELLABLE + spell       → no cover/shading

# Assigned role (ability targeting)
ROLE_ASSIGNED          → COVER_ASSIGNED

# Could-block-but-isn't
defaultBlocking + !blocking → SHADING_NOTBLOCK
```

**Note on `Card_Orange`:** The existing engine bundle labels this as `bg_construction`, but it is actually BACK_ABSORB (absorbing partial damage). Construction uses BACK_BOUGHT (`Card_Trans`).

## Board Layout

### 3 Rows Per Player

| Row | Content | Y offset (top player, upward from center) | Y offset (bottom player, downward from center) |
|---|---|---|---|
| Front (row 0/3) | POSITION_FRONT_* (0-7) | -(82 + gutter) | +(gutter) |
| Middle (row 1/4) | POSITION_MIDDLE_* (10-18) | -(2×82 + gap + gutter) | +(82 + gap + gutter) |
| Back (row 2/5) | POSITION_BACK_* (20-29) | -(3×82 + 2×gap + gutter) | +(2×82 + 2×gap + gutter) |

Row gap: 5 (normal) or 1 (replay mode). Center gutter (`midLineGutter`): 4 (normal) or 2 (replay mode). Top player rows extend upward from center; bottom player rows extend downward. Card height = 82px.

Front rows reserve SWORD_WIDTH pixels on left and right for attack/defense sword barriers. Middle and back rows use full width.

### Unit Position Assignment

Each card type has a **static** `position` constant computed once from card JSON properties. This determines row and ordering — it does NOT change based on runtime state.

Row is `floor(position / 10)`: 0=front, 1=middle, 2=back. Within a row, piles sort by ascending position value, ties broken by creation order.

**Priority chain (from Card.as, first match wins):**

| Priority | Condition | Position | Value |
|---|---|---|---|
| 1 | Explicit JSON `position` field | as specified | varies |
| 2 | Conduit | BACK_FAR_LEFT | 20 |
| 3 | Blastforge | BACK_FAR_LEFT_ONE | 21 |
| 4 | Animus | BACK_FAR_LEFT_TWO | 22 |
| 5 | Drone | MIDDLE_FAR_LEFT | 10 |
| 6 | Engineer | FRONT_FAR_LEFT | 0 |
| 7 | Spell | BACK_FAR_RIGHT | 29 |
| 8 | Undefendable + attacks/targets | FRONT_RIGHT_ONE | 7 |
| 9 | Undefendable, no attack | FRONT_RIGHT | 6 |
| 10 | Ability + defaultBlocking + assignedBlocking + attacks | FRONT_LEFT_ONE | 4 |
| 11 | Ability + defaultBlocking + assignedBlocking | FRONT_LEFT | 3 |
| 12 | Ability + defaultBlocking + !assignedBlocking + attacks | MIDDLE_RIGHT | 16 |
| 13 | Ability + defaultBlocking + !assignedBlocking | MIDDLE_FAR_LEFT_ONE | 11 |
| 14 | Ability + !defaultBlocking + attacks/targets | MIDDLE_FAR_RIGHT | 18 |
| 15 | Ability + !defaultBlocking | MIDDLE_LEFT | 13 |
| 16 | defaultBlocking + attacks/targets | FRONT_FAR_LEFT_TWO | 2 |
| 17 | defaultBlocking | FRONT_FAR_LEFT_ONE | 1 |
| 18 | Attacks/targets, no blocking, no ability | BACK_RIGHT | 26 |
| 19 | Default (nothing special) | BACK_LEFT | 23 |

**Implementation:** Add `position` field to `getCardMeta()` in the engine bundle, computed from cardLibrary.jso properties using this priority chain.

### Pile Stacking

**Horizontal** — same-type units overlap left-to-right within a pile. Each card peeks out by the gap amount. Rightmost card is fully visible.

```
GAP_SIZE: 2.5px         // horizontal offset between stacked cards
DEFAULT_SPACING: 17px   // normal horizontal stagger
CRAMMED_SPACING: 13px   // tight mode when row is full
```

### Row Layout & Cramming

**Constants (from UIRow):**

```
CARDSPACING: [0, 18, 18, 18, 17, 17, 17, 16]  // per pile count
DEFAULTMARGIN: 20
NICEMARGIN: 3
CRAMMEDMARGIN: -40
```

**Cramming algorithm:** Faithfully ported from AS3 `UIRow.performCramming()`. Includes:

- Smooth exponential transition: `0.8 + 0.2 * (1 - exp(-2 * ...))`
- Per-card compression via `stretchFactorAmount()` — inner cards compress to 58% width, rightmost cards stay full-width
- "Big gap" mechanic: GAP_SIZE (2.5px) gap inserted between bought/created-this-phase and non-bought cards, only for the active player's units when phase != DEFENSE (i.e., action and confirm phases)
- Negative margin (-40) causes piles to overlap horizontally with per-card spacing recalculated

**This algorithm must be faithfully ported from AS3 source (`UIRow.performCramming()`, `UIPile.stretchFactorAmount()`).**

**Note on `stretchFactorAmount()`:** The actual function (UIPile.as lines 998-1034) has three ranges based on `cramFactor` (< 1, 1-1.5, >= 1.5), with special handling for piles > 28 cards and a progressive gradient for the last 10 cards. The "58% width" figure is only the `fullyCrammedAmount` for inner cards. Port the full function, do not approximate.

**Note on big gap:** Requires knowing whether a unit was bought in the current phase (`wasBoughtOrClickCreatedThisPhase` in AS3). This needs a `boughtThisPhase` field in the state export, or the big gap mechanic is deferred. See Engine Bundle Changes.

### Responsive Scaling

PixiJS renderer uses a fixed logical resolution. The AS3 client computes board dimensions dynamically from `GameScreen` guides; the implementation should derive the logical resolution from the same layout constants (6 rows × 82px + gaps + resource bars + buy panel width). CSS scales the canvas element to fit the viewport, following the same approach as the current `updateBoardScale()`.

## Buy Panel

Two always-visible columns (base + randomizer). No tab switching — both columns shown at all times for both replay viewer and live spectating.

**BuyCard rendering:**
- Card art image (300x300 PNG scaled to buy panel size)
- Cost display with resource icons (gold digits + G/B/C/H colored icons)
- Supply indicator per player (from UISupplyBar)
- Affordability state — dimmed if active player can't afford, highlighted if purchasable

**Data source:**
- `GameState.cards[]` — purchasable card names
- `whiteTotalSupply[]` / `blackTotalSupply[]` — initial supply per card
- `whiteSupplySpent[]` / `blackSupplySpent[]` — purchased counts
- `whiteMana` / `blackMana` — current resources for affordability

## Resource Bar

Inside the PixiJS canvas (not React DOM) to support future transition animations.

Per player: Gold (numeric) + Blue (B) + Green (G) + Red (C) + Energy (H) + Attack total + Defense total.

Rendered as icon + number pairs using the resource icon sprites already base64-embedded in the engine bundle (P/B/G/C/H/A). Numbers via PixiJS BitmapFont.

P1 resources at top of canvas, P0 resources at bottom.

## Asset Pipeline

### Available Now

| Asset | Location | Format | Count |
|---|---|---|---|
| Unit card art | `/images/units/` (ladder site) | 300x300 RGBA PNG | 255 |
| Card backgrounds (all 10) | `bin/asset/images/cardbg/` (on disk) | Small PNG sprites | 18+ files (7 loaded in bundle, rest on disk) |
| Cover overlay textures (all 6) | `bin/asset/images/cardbg/` + `icons/status/` | Small PNG sprites | All present on disk |
| Shading overlay textures (all 5) | `bin/asset/images/icons/status/` | Small PNG sprites | All present on disk (highlight_whiteshield, blueshield, whiteshieldB, redshield, emptypixel) |
| Border glow textures (2) | `bin/asset/images/cardbg/` | Small PNG sprites | border_yellow.png, border_yellow_urgent.png |
| Status icons | `bin/asset/images/icons/status/` | 18x18 PNG sprites | 28 files (14 status types) |
| Resource icons | Engine bundle (base64) | Small PNG sprites | 6 |
| Card art (engine) | `bin/asset/images/cards/` | 300x300 RGBA PNG | 143 |
| Background (1) | `bin/asset/images/bgs/abyss.png` | 1.8MB PNG | 1 |

**Note:** The engine bundle currently only loads 7 of the 18+ card background files. The remaining assets exist on disk in `bin/asset/images/` but need to be added to the bundle or loaded separately. `Card_Trans.png` (BACK_BOUGHT, the construction background) exists on disk but is NOT in the bundle — needs to be added. The bundle mislabels `Card_Orange` as `bg_construction`; it's actually BACK_ABSORB.

### Needs Extraction / Creation

| Asset | Source | Method |
|---|---|---|
| ATF backgrounds (20+) | `C:\Files\SteamLibrary\steamapps\common\Prismata\backgroundFinal\atf1080\` | `extract_atf_backgrounds.py` (script exists at `C:\Users\Surfinite\Downloads\`) |
| Chill snowflake sprite | ChillSnowflake.as effect class | Extract from SWF or recreate |
| Frontline crosshair sprite | FrontlineEffect.as effect class | Extract from SWF or recreate |
| Name sprites (105+) | Generate via BitmapFont | Phase B fallback; extract from SWF for full fidelity |

**Note on skull effect:** The skull uses `Card_Dead` (`Card_Inver.png`) texture at 0.3x scale, tweened to 1x (SkullEffect.as line 61). It is NOT a separate sprite — it reuses the existing BACK_DEAD texture. No extraction needed.

### Asset Delivery

- Card art PNGs loaded at runtime from `/images/units/` (already served by ladder site)
- Small sprites (backgrounds, icons, overlays) embedded in a sprite atlas or loaded as individual textures
- Lazy loading for card art — load on first appearance, cache in PixiJS texture cache
- Consider WebP conversion for bandwidth optimization (300x300 PNG → WebP saves ~60%)

### Missing Asset Fallback

For assets that haven't been extracted yet (overlays, shading textures, effect sprites): render a colored semi-transparent rectangle as a placeholder. This allows development and testing to proceed while asset extraction happens in parallel. The placeholder should be visually distinct (e.g., magenta tint) so missing assets are obvious, not silently invisible.

## Engine Bundle Changes

### `getCardMeta()` additions

- **`position`** field per card type: Static board position computed from cardLibrary.jso properties using the priority chain from Card.as. One-time computation at load time.

### `instToCardJSON()` additions (in `replay_exporter.js`)

The current state export is missing fields required for correct rendering:

- **`instId`** (`inst.instId`): Stable instance identifier. Required for in-place sprite updates — without it, the renderer cannot correlate units across state changes when multiple instances of the same card type exist. Note: the JS engine Inst class uses `this.instId` (Inst.js line 34), not `.id`.
- **`damage`** (`inst.damage`): Current damage on the unit. Required for BACK_ABSORB, BACK_WHITEPINK, COVER_BANG, damage counter, and the full `UIInst.update()` state machine branching.
- **`boughtThisPhase`** (optional): Whether the unit was purchased or created by ability script in the current phase. Maps to AS3 `wasBoughtOrClickCreatedThisPhase()` which also checks `creatorIdFromBuyOrAbility >= 0` (covering units spawned by another unit's buy/ability script, e.g. Pixie from Animus). The JS Inst object has `creatorIdFromBuyOrAbility` (Inst.js line 103) which could be exported directly as an alternative. Required for the "big gap" pile spacing mechanic. If omitted, the big gap visual is deferred.

### `stateToCppJSON()` changes

- **Include dead units**: Currently filters `inst.deadness === C.DEADNESS_ALIVE` only. Dead units must be included in the `table[]` array (with their `deadness` field preserved) because the AS3 client renders dead units on the board with BACK_DEAD + skull icon until the next swoosh.

### Bundle asset fixes

- Relabel `bg_construction` → `bg_absorb` (it maps to `Card_Orange.png` = BACK_ABSORB, not construction)
- Add `Card_Trans.png` to bundle as `bg_bought` (BACK_BOUGHT, actual construction background — exists on disk but missing from bundle)
- Add remaining card background, cover, shading, and border textures from `bin/asset/images/` (all exist on disk, just not loaded by the bundle yet)

## Future Extensions

### Phase C: Transitions & Animations

- Tween library (gsap or tween.js) for smooth state interpolation
- topWhiteQuad flash on purchase
- Card position tweens when piles reflow
- Resource counter animations
- Death/damage particle effects via `@pixi/particle-emitter`

### Phase D: Live Spectating Enhancements

- Border glow layers activated for clickable state feedback
- Emote system — effectContainer layer and React overlay both serve as mounting points for emotes. Emote system design (set, permissions, rate limiting, positioning) is a separate spec.

### Phase D+: Animated Skins

- CardSkin layer upgraded from static PNG to animated sprite sequences
- SkinConfig system for loading per-unit skin variants
- 25+ skin variants from AS3 source (Regular, Snowy, Disco, Erebos, etc.)
