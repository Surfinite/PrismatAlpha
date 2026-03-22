# Browser Game Viewer — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Authors:** Surfinite + Claude

## Overview

A PixiJS 8 game board renderer that replaces the current HTML/CSS board in the <ladder> React site. Renders a faithful recreation of the original Prismata Flash client's board using the decompiled AS3 source as reference.

**Target fidelity (Phase B):** Card art + full state feedback — colored backgrounds by owner/state, construction dimming with clock overlays, blocker highlighting, status icons (HP/charge/delay/doom/tap/attack), dead/chill/damage effects as static sprites. Architecture supports Phase C transitions and animations without rework.

## Phased Roadmap

| Phase | Scope | Rendering |
|---|---|---|
| **A** | Card art + clean layout | Static board with card images, proper 3-row layout, buy panel |
| **B (target)** | Card art + state feedback | All visual states: 10 background variants, 6 cover overlays, shading, status icons, effectContainer sprites |
| **C (future)** | Transitions | Smooth state transitions, purchase animations (topWhiteQuad), card movement tweens, death/attack effects |
| **D (future)** | Near-parity | Full particle system (death, chill, snipe lasers), animated card skins, 40+ AS3 effect classes |

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

Same pattern as the existing viewer. No new engine API required.

1. React page loads `prismata-engine.js` bundle (existing)
2. On state change, React calls `PrismataViewer.getGameState()` + `PrismataViewer.getCardMeta()`
3. React passes state to `BoardRenderer.updateState(gameState, cardMeta)`
4. BoardRenderer updates PixiJS sprites in-place (no teardown/rebuild)

### Code Location

**Repository:** <ladder> (alongside existing viewer code)

The renderer is a new module consumed by the existing `[gameId]/page.tsx`. The page.tsx retains its React chrome but swaps the HTML board rendering for a canvas mount point.

## Class Hierarchy

Mirrors the AS3 decompiled source class-for-class.

| PixiJS Class | AS3 Source | Responsibility |
|---|---|---|
| `BoardRenderer` | `GameScreen` | Top-level PixiJS Application, canvas management, state dispatch |
| `BoardView` | `UIBoard` | Per-player board, contains 3 rows + sword barriers |
| `RowView` | `UIRow` | Horizontal lane layout with cramming algorithm |
| `PileView` | `UIPile` | Horizontal stack of same-type unit cards |
| `UnitCard` | `UIInst` | Individual unit card, 9-layer rendering |
| `StatusOverlay` | `UIStatus` | HP/charge/delay/doom/tap/attack/spell icons |
| `BuyPanel` | `UIBuyBox` | Two always-visible columns (base + randomizer) |
| `BuyCard` | `UIPurchasable` | Card art + cost icons + supply indicator |
| `ResourceBar` | `UIPlayerMana` | Gold/B/G/C/H + attack/defense totals |

## Unit Card Rendering (UnitCard)

### Layer Stack

9 layers per card, back to front, matching AS3 `UIInst`:

| Index | Layer | AS3 Name | Description |
|---|---|---|---|
| 0 | Card background | `backMC` | 82x82px base, 10 variants by state + owner |
| 1 | Card skin | `cardSkin` | Unit art sprite. Phase B: static 300x300 PNG scaled to fit. Phase C+: animated skin sprites |
| 2 | Cover overlay | `coverMC` | 6 state overlays (clock, cage, shield, bang) |
| 3 | Shading overlay | `shadingMC` | 4 states for blocking/non-blocking visual feedback |
| 4 | Border glow | `borderMC` | Clickable highlight (yellow/white). Interactive mode only |
| 5 | Name image | `nameImage` | Pre-rendered name sprite (`instName_` + cardUIName). Phase B: BitmapFont fallback |
| 6 | Status icons | `statusContainer` | HP, charge(0-3), delay, doom, tap, attack, spell. 18px icons, 4px spacing |
| 7 | White flash | `topWhiteQuad` | Purchase landing animation. Default alpha=0. Used in Phase C |
| 8 | Effect container | `effectContainer` | Skull (41,43), chill snowflake (41,43), frontline crosshair, damage counter (3,3) |

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

```
default (alive, idle)  → back: BACK_BUSYBLUE (owner=0) or BACK_BUSYRED (owner=1)
                         cover: COVER_EMPTY

if dead                → back: BACK_DEAD
                         effectContainer: skull icon at (41, 43)

if blocking            → back: BACK_BLOCK (owner=0) or BACK_BLOCKRED (owner=1)
                         shading: SHADING_BLOCK

if constructing        → back: BACK_BOUGHT (Card_Trans)
                         card alpha: 0.87
                         cover: COVER_INVBOUGHT (just purchased) or
                                COVER_INVSPAWN (spawning from ability)

if disruptDamage >= health && health > 0
                       → back: BACK_BLOCK_FROST
                         effectContainer: chill snowflake at (41, 43)

if taking damage       → cover: COVER_BANG
                         effectContainer: damage counter at (3, 3)

if fully damaged       → back: BACK_WHITEPINK
```

## Board Layout

### 3 Rows Per Player

| Row | Content | Y offset from center |
|---|---|---|
| Front (row 0/3) | Units with POSITION_FRONT_* (0-7) | -(82 + 4) |
| Middle (row 1/4) | Units with POSITION_MIDDLE_* (10-18) | -(2×82 + 5 + 4) |
| Back (row 2/5) | Units with POSITION_BACK_* (20-29) | -(3×82 + 2×5 + 4) |

Row gap: 5 (normal) or 1 (replay mode). Center gutter: 4 (normal) or 2 (replay mode).

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
- "Big gap" mechanic: 2.5x normal gap inserted between bought and non-bought cards during action phase only
- Negative margin (-40) causes piles to overlap horizontally with per-card spacing recalculated

**This algorithm must be faithfully ported from the AS3 source, not approximated.**

### Responsive Scaling

PixiJS renderer uses a fixed logical resolution matching the original client's board area. CSS scales the canvas element to fit the viewport, following the same approach as the current `updateBoardScale()`.

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
| Card backgrounds | Engine bundle (base64) | Small PNG sprites | 7 (need 3 more) |
| Status icons | Engine bundle (base64) | 18x18 PNG sprites | 12 |
| Resource icons | Engine bundle (base64) | Small PNG sprites | 6 |
| Card art (engine) | `bin/asset/images/cards/` | 300x300 RGBA PNG | 143 |
| UI icons | `bin/asset/images/icons/` | Various PNG | 97 |
| Background (1) | `bin/asset/images/bgs/abyss.png` | 1.8MB PNG | 1 |

### Needs Extraction / Creation

| Asset | Source | Method |
|---|---|---|
| ATF backgrounds (20+) | `C:\Files\SteamLibrary\steamapps\common\Prismata\backgroundFinal\atf1080\` | `extract_atf_backgrounds.py` |
| Missing card backgrounds (3) | SWF or recreate | BACK_WHITEPINK, BACK_BUSYBLUE, BACK_BUSYRED |
| Cover overlay textures (6) | SWF or recreate | highlight_blackclock, goldclock, cage2, goldshield, damagebang, emptypixel |
| Shading overlay textures (4) | SWF or recreate | NOTBLOCK, BLOCK, DEAD_BLOCK, REDBLOCK |
| Border glow textures (2) | SWF or recreate | CLICKABLE, CLICKABLE_URGENT |
| Skull / snowflake / crosshair sprites | SWF or recreate | Effect container sprites |
| Name sprites (105+) | Generate via BitmapFont | Phase B fallback; extract from SWF for full fidelity |

### Asset Delivery

- Card art PNGs loaded at runtime from `/images/units/` (already served by ladder site)
- Small sprites (backgrounds, icons, overlays) embedded in a sprite atlas or loaded as individual textures
- Lazy loading for card art — load on first appearance, cache in PixiJS texture cache
- Consider WebP conversion for bandwidth optimization (300x300 PNG → WebP saves ~60%)

## Engine Bundle Changes

One addition required: **`position` field in `getCardMeta()`**.

Compute each card type's static position from cardLibrary.jso properties using the priority chain from Card.as. This is a one-time computation at load time, exported alongside existing card metadata (attack, toughness, abilities, costs, rarity).

No other engine API changes needed — `getGameState()` already provides all fields required for rendering.

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
