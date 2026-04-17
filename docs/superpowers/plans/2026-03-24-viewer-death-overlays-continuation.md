# Viewer Death/Breach Overlays — Continuation Prompt

> **Use this prompt to resume work in a new session.**

## Context

The Prismata Design System (React buy panel components) is complete and merged to `master`. The next priority is fixing visual overlays for dying/dead units in the PixiJS game board renderer, to match the SWF client's death feedback.

**Repo:** `<LADDER_REPO_PATH>` on `master` branch (38 commits ahead of `origin/master` — not yet pushed)

## What Was Completed (Mar 24 Sessions)

### Session 1 — Viewer Visual Fidelity
- **Resource bar**: Numbers overlaid on gem icons, gold estimate in parentheses `(min-max)` matching SWF
- **Breach effects**: `BreachEffects.ts` created — skull pop-in, floating damage numbers, red flash overlay
- **PixiJS buy panel prototype**: `BuyCard.ts`/`BuyPanel.ts` (ready, not in active use — React version used instead)
- **Chill overlay**: Snowflake texture on chilled units

### Session 2 — Design System + Supply Bars
- **Prismata Design System**: Full React component library at `src/components/prismata/`
  - Tokens (`tokens.ts`): AS3 Palette.as visual DNA — player colors (blue/red), resource colors, panel styling
  - Utils (`utils.ts`): parseCost, sortBuyPanel, getUnitImgPath (typed versions returning ResourceType)
  - 6 Primitives: ResourcePip, ResourceCost, SupplyBar, CardArtBg, PrismataPanel, CardInfoPopup
  - 2 Composites: BuyRow, BuyPanel
  - 7 test files, 116 tests passing
- **Buy panel integration**: Replaced inline JSX in `page.tsx` with `<BuyPanel>` component
- **Dual supply bars**: Both P1 (blue) and P2 (red) supply bars visible (4px each, 2px gap)
- **Panel width**: Reduced from 380px to 300px (dead space eliminated)

### Design System Code Review Findings (deferred)
- CardInfoPopup not wired into BuyPanel yet (spec says "deferred to later phase")
- Old `game-viewer/utils.ts` still has duplicate functions (used by other components, intentional)
- Component tests test logic not DOM rendering (no JSDOM configured)

## What Needs Doing — Death/Breach Visual Overlays

### The Problem
Comparing our viewer to the SWF client at the same game state (Turn 12 of `++Lz6-V00@a`):
- **SWF**: Dying units (e.g., Engineers assigned to block) have a red tint overlay and skull death indicator. Dead units after breach show skulls and red damage effects.
- **Our viewer**: Units that are dying/blocking show no visual death feedback. They render the same as healthy units.

### Key Files
| File | Description |
|---|---|
| `src/components/game-renderer/BoardRenderer.ts` | Main board render loop — iterates over `gameState.table` |
| `src/components/game-renderer/UnitCard.ts` | Individual unit card rendering (PixiJS sprites) |
| `src/components/game-renderer/BreachEffects.ts` | Skull/damage/flash effects (created in session 1 but may need fixes) |
| `src/components/game-renderer/StatusOverlay.ts` | Status icons on units (chill, lifespan, delay, charge) |
| `src/components/game-renderer/constants.ts` | Visual constants, colors |
| `src/components/game-renderer/types.ts` | `CardInstance.deadness` and `CardInstance.blocking` fields |

### CardInstance State Fields
```ts
interface CardInstance {
  deadness: 'alive' | 'selfsacced' | 'sacced' | 'blocked' | 'meleed' | 'breached' | 'sniped' | 'autosniped' | 'aged';
  blocking: boolean;  // true when assigned as blocker
  role: 'default' | 'assigned' | 'sellable' | 'inert';
  health: number;
  // ...
}
```

### Visual States to Implement
1. **Blocking units** (`blocking: true`, `deadness: 'alive'`): Blue/cyan tint or shield overlay — these units are assigned to defend
2. **Dead units** (`deadness !== 'alive'`): Red tint, reduced opacity, skull icon. Different death types could have subtle variations:
   - `blocked` — died absorbing damage
   - `breached` — killed during breach
   - `sniped`/`autosniped` — targeted kill
   - `selfsacced`/`sacced` — sacrificed for ability
3. **Breach flash**: Red screen overlay when breach occurs (already partially in BreachEffects.ts)

### SWF Reference
The AS3 source is decompiled at `c:\libraries\PrismataAI\prismata_decompiled\`. Key files:
- `scripts/game/UIPurchasable.as` — unit card rendering
- `scripts/game/UICard.as` — card visual states
- `scripts/starlingUI/Palette.as` — color constants

### How to Test
```bash
cd <LADDER_REPO_PATH>/<ladder>-site
npx next dev --webpack
# Open http://localhost:3000/replay/++Lz6-V00@a
# Navigate to Turn 12 — blue's Engineers are dying from incoming attack
# Compare visually to SWF client at same turn
```

## Quick Start
```bash
cd <LADDER_REPO_PATH>
git branch --show-current  # should be 'master'
cd <ladder>-site
npx next dev --webpack
```

## Current State Summary
- `master` branch, 38 commits ahead of `origin/master` (not pushed)
- 116 tests passing
- Design system complete, buy panel working with dual supply bars
- Next priority: death/breach visual overlays on PixiJS board units
