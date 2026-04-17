# Viewer Visual Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the PixiJS replay/live viewer to visual parity with the original Flash (SWF) client, addressing all 10 of Wonderboat's feedback items and adding board HUD rendering.

**Architecture:** Incremental fixes to the existing 10-layer UnitCard/StatusOverlay system in `game-renderer/`, guided by pixel-comparison against decompiled SWF source (`UIInst.as`, `UIStatus.as`, `UIInstNumber.as`). Each task is independently deployable. Tests use the existing Vitest setup with visual-state unit tests.

**Tech Stack:** PixiJS 8, TypeScript, Vitest, Next.js 16 (<ladder>-site)

**Spec:** `c:\libraries\PrismataAI\docs\plans\2026-03-24-viewer-visual-fidelity-plan-prompt.md`

**Repo:** `<LADDER_REPO_PATH>\` (branch from `feature/live-viewer`)

---

## File Structure

All changes are in `<ladder>-site/src/components/game-renderer/`. Abbreviated as `gr/` below.

| File | Action | Responsibility |
|------|--------|---------------|
| `gr/constants.ts` | Modify | Add SWF-accurate positioning constants, font config |
| `gr/StatusOverlay.ts` | Modify | Fix icon sizing, number positioning, text styling, sword direction |
| `gr/UnitCard.ts` | Modify | Fix name label stroke, damage label stroke, snowflake position |
| `gr/BuyCard.ts` | Modify | Fix supply display if needed (P2 Drone offset) |
| `gr/BuyPanel.ts` | Modify | Pass player context for supply calculation if needed |
| `gr/BoardRenderer.ts` | Modify | Move attack/defense/chill HUD into PixiJS canvas, add danger indicator |
| `gr/types.ts` | Modify | Add fields to interfaces as needed |
| `gr/__tests__/visual-state.test.ts` | Modify | Add tests for new visual state logic |
| `gr/__tests__/status-overlay.test.ts` | Create | Unit tests for status icon positioning and text styling |
| `gr/__tests__/buy-panel.test.ts` | Create | Tests for supply count P2 offset |

### SWF Reference Files (read-only)

| File | What to extract |
|------|----------------|
| `prismata_decompiled/scripts/starlingUI/game/board/UIInst.as` | Layer order, positioning, alpha values |
| `prismata_decompiled/scripts/starlingUI/game/board/UIStatus.as` | Icon positions, stacking order, sizing |
| `prismata_decompiled/scripts/starlingUI/game/board/UIInstNumber.as` | Kerning tables, digit rendering |
| `prismata_decompiled/scripts/CardFont.as` | Drop shadow params, font metrics |

---

## Stream 1: Unit Card Polish

### Task 1: Add Black Outline/Stroke to All Numbers

Wonderboat feedback items #2 (fatter font), #10 (black outline). The SWF renders status numbers as pre-rendered bitmap digit sprites (`UIInstNumber.as` with `CommonAssets.NUMBERS_SMALL/LARGE`), not text — they appear bold and crisp. Name labels use `CardFont.as` with a DropShadowFilter (angle 45°, alpha 0.8, strength 3). Since our PixiJS renderer uses `Text` objects for all numbers, we approximate the SWF's visual weight by applying a consistent black stroke to all text. The construction timer already has `stroke: { width: 3 }` but variable/fixed status labels and the damage counter lack it.

**Files:**
- Modify: `gr/constants.ts`
- Modify: `gr/StatusOverlay.ts`
- Modify: `gr/UnitCard.ts`
- Read: `prismata_decompiled/scripts/CardFont.as` (drop shadow params)

**SWF reference (CardFont.as):** Drop shadow filter — angle 45°, distance 2px, alpha 0.8, color 0x000000. All numbers use white fill + black stroke for contrast.

- [ ] **Step 1: Add font constants to constants.ts**

Add a `FONT_CONFIG` object to `gr/constants.ts`:

```typescript
/** SWF-faithful font styling for card numbers */
export const FONT_CONFIG = {
  /** Black outline width on all numbers (SWF uses 2px drop shadow) */
  STROKE_WIDTH: 3,
  STROKE_COLOR: 0x000000,
  /** Construction timer */
  CONSTRUCTION: { SIZE: 14, COLOR: 0xFFFFFF, WEIGHT: 'bold' as const },
  /** Status count labels (HP, delay, doom, charge, chill) */
  STATUS_COUNT: { SIZE: 11, COLOR: 0xFFFFFF, WEIGHT: 'bold' as const },
  /** Damage counter */
  DAMAGE: { SIZE: 12, COLOR: 0xFF0000, WEIGHT: 'bold' as const },
  /** Name label */
  NAME: { SIZE: 8, COLOR: 0xFFFFFF, WEIGHT: 'bold' as const },
} as const;
```

- [ ] **Step 2: Update StatusOverlay.ts to use FONT_CONFIG with stroke**

In `StatusOverlay.ts`, update all `Text` style objects to include `stroke` and use `FONT_CONFIG`:

For the construction timer text (currently `fontSize: 14, fontWeight: 'bold'`):
```typescript
import { FONT_CONFIG } from './constants';

// Construction timer text style
const style = new TextStyle({
  fontFamily: 'Arial',
  fontSize: FONT_CONFIG.CONSTRUCTION.SIZE,
  fontWeight: FONT_CONFIG.CONSTRUCTION.WEIGHT,
  fill: FONT_CONFIG.CONSTRUCTION.COLOR,
  stroke: { color: FONT_CONFIG.STROKE_COLOR, width: FONT_CONFIG.STROKE_WIDTH },
});
```

For count labels next to status icons (currently `fontSize: 10`):
```typescript
const countStyle = new TextStyle({
  fontFamily: 'Arial',
  fontSize: FONT_CONFIG.STATUS_COUNT.SIZE,
  fontWeight: FONT_CONFIG.STATUS_COUNT.WEIGHT,
  fill: FONT_CONFIG.STATUS_COUNT.COLOR,
  stroke: { color: FONT_CONFIG.STROKE_COLOR, width: FONT_CONFIG.STROKE_WIDTH },
});
```

- [ ] **Step 3: Update UnitCard.ts damage label to use stroke**

The damage label in `UnitCard.ts` (red number at top-left) needs stroke too:
```typescript
const damageStyle = new TextStyle({
  fontFamily: 'Arial',
  fontSize: FONT_CONFIG.DAMAGE.SIZE,
  fontWeight: FONT_CONFIG.DAMAGE.WEIGHT,
  fill: FONT_CONFIG.DAMAGE.COLOR,
  stroke: { color: FONT_CONFIG.STROKE_COLOR, width: FONT_CONFIG.STROKE_WIDTH },
});
```

- [ ] **Step 4: Verify name label already has stroke, update to FONT_CONFIG**

The name label in `UnitCard.ts` already has `strokeThickness: 2`. Update to use the shared constant:
```typescript
const nameStyle = new TextStyle({
  fontFamily: 'Arial',
  fontSize: FONT_CONFIG.NAME.SIZE,
  fontWeight: FONT_CONFIG.NAME.WEIGHT,
  fill: FONT_CONFIG.NAME.COLOR,
  stroke: { color: FONT_CONFIG.STROKE_COLOR, width: FONT_CONFIG.STROKE_WIDTH },
});
```

- [ ] **Step 5: Build and visually verify**

Run: `cd <LADDER_REPO_PATH>/<ladder>-site && npx next build --webpack`
Expected: Build succeeds. Load a replay in browser — all numbers should have visible black outlines, bolder appearance.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "fix(renderer): add black outline stroke to all card numbers

Addresses Wonderboat feedback #2 (fatter font) and #10 (black outline).
All card numbers (construction timer, status counts, damage, name) now
use consistent FONT_CONFIG with 3px black stroke matching SWF styling."
```

---

### Task 2: Fix Sword Icon Direction

Wonderboat feedback #3. The attack sword icon faces the wrong direction.

**Files:**
- Modify: `gr/StatusOverlay.ts`
- Read: `prismata_decompiled/scripts/starlingUI/game/board/UIStatus.as` (sword rendering)

- [ ] **Step 1: Identify sword rendering in StatusOverlay.ts**

Read `StatusOverlay.ts` and find where `icon_attack` is rendered. The sword sprite likely needs `scale.x = -1` to flip horizontally, or the texture itself needs replacing.

- [ ] **Step 2: Flip the sword sprite**

In `StatusOverlay.ts`, where the attack icon is added to `fixedContainer`, flip it:
```typescript
// After creating the attack icon sprite
attackIcon.scale.x = -1;
attackIcon.x += STATUS_SIZE; // Compensate for flip pivot
```

If the SWF sword points **left** (toward the opponent) and ours points right, this flip corrects it. Verify against SWF reference.

- [ ] **Step 3: Build and visually verify**

Load a replay with attacking units (e.g., Tarsier). Sword should now point in the same direction as SWF.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "fix(renderer): flip sword icon to match SWF direction"
```

---

### Task 3: Fix Status Icon Positioning — Attack and Defense Numbers

Wonderboat feedback #8 (non-fragile HP/defense text positioning) and #9 (sword text positioning). The SWF positions attack and defense icons at the bottom-right corner with numbers offset into the icon.

**Files:**
- Modify: `gr/StatusOverlay.ts`
- Modify: `gr/constants.ts`
- Read: `prismata_decompiled/scripts/starlingUI/game/board/UIStatus.as` (lines 191-204)

**SWF reference (UIStatus.as lines 219-222):**
- X: `iconX = INST_SIZE - STATUS_SIZE - SPACING + offset - this.x` where `INST_SIZE=82, STATUS_SIZE=18, SPACING=4, this.x=2`
- Y: `iconY = INST_SIZE - STATUS_SIZE - SPACING + 1 - this.y` where `this.y=17` → `82 - 18 - 4 + 1 - 17 = 44`

Positions (relative to StatusOverlay container at (2,17)):
- **Attack** (`offset = -STATUS_SIZE * 2 = -36`): X = `82 - 18 - 4 - 36 - 2 = 22`, Y = `44` → position `(22, 44)`
- **Defend/Spell** (`offset = 0`): X = `82 - 18 - 4 - 0 - 2 = 58`, Y = `44` → position `(58, 44)`

Number text for **fixed** statuses (lines 221-222): `numberX = iconX - 7`, `numberY = iconY + 4`
(Different from variable status numbers which use `iconX - 2`, `iconY + 7`)

- [ ] **Step 1: Add positioning constants**

In `gr/constants.ts`:
```typescript
/** SWF-accurate fixed status icon positioning (bottom area) */
export const FIXED_STATUS = {
  /** Attack icon position — left of defend (SWF: offset=-STATUS_SIZE*2) */
  ATTACK_X: 22,
  ATTACK_Y: 44,
  /** Defense/spell icon position — right side (SWF: offset=0) */
  DEFEND_X: 58,
  DEFEND_Y: 44,
  /** Fixed status number offset (SWF lines 221-222: iconX-7, iconY+4) */
  NUMBER_OFFSET_X: -7,
  NUMBER_OFFSET_Y: 4,
} as const;

/** SWF-accurate variable status number offset (lines 228-229) */
export const VARIABLE_STATUS = {
  NUMBER_OFFSET_X: -2,
  NUMBER_OFFSET_Y: 7,
  /** Baseline Y offset (SWF line 227: +4 always present) */
  Y_BASELINE: 4,
} as const;
```

- [ ] **Step 2: Update fixed status positioning in StatusOverlay.ts**

Replace the current positioning math for attack and defense icons with the SWF-accurate constants. Key changes:
1. Attack icon at `(22, 44)` — left of defend icon
2. Defend icon at `(58, 44)` — bottom area, right side
3. Fixed number text at `iconX - 7, iconY + 4` (overlapping the icon)

- [ ] **Step 3: Build and verify with Tarsier, Wall, other units**

Check: attack number slightly inside sword icon, defense number slightly inside shield icon, matching SWF layout.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "fix(renderer): correct attack/defense number positioning to match SWF

Numbers now render slightly inside their icons rather than beside them."
```

---

### Task 4: Fix Fragile HP Number Positioning

Wonderboat feedback #4 ("Fragile HP text goes inside heart on bottom left"). The SWF renders fragile HP as a variable status in the top-left stack (same as delay, doom, charge), with the HP number overlapping the heart icon using `UIInstNumber` at `numberX = iconX - 2`. The key fix is ensuring the HP count number renders overlapping/inside the heart icon, not as a separate label beside it.

**Files:**
- Modify: `gr/StatusOverlay.ts`
- Read: `prismata_decompiled/scripts/starlingUI/game/board/UIStatus.as` (lines 144-157, 226-230)

**SWF reference (UIStatus.as):** Fragile HP is in the variable stack at `(iconX=1, iconY=numVar*20+offset)`. The number is at `(iconX-2, iconY+7)` — overlapping the icon from the left. This is the same pattern as all other variable statuses.

- [ ] **Step 1: Check current variable status number positioning**

Read `StatusOverlay.ts` and find where variable status count labels are positioned relative to their icons. Currently the count label is at `x = STATUS_SIZE + 2` (to the right of the icon). The SWF places it at `iconX - 2` (overlapping the left edge of the icon).

- [ ] **Step 2: Adjust HP number to overlap heart icon**

The number should overlap the icon. Update the count label positioning for all variable statuses:
```typescript
// SWF lines 228-229: numberX = iconX - 2, numberY = iconY + 7
countLabel.x = icon.x + VARIABLE_STATUS.NUMBER_OFFSET_X;
countLabel.y = icon.y + VARIABLE_STATUS.NUMBER_OFFSET_Y;
```

This applies to all variable statuses (HP, delay, doom, charge, chill), not just fragile HP. Verify this looks correct for all icon types.

**Note:** If numbers-overlapping-icons looks wrong at our scale, keep the current right-of-icon layout but document the difference. Wonderboat's specific complaint was about HP + heart, so at minimum ensure the HP heart icon is large enough and the number is visually "inside" it.

- [ ] **Step 3: Test with fragile units**

Find a replay with fragile units (e.g., Rhino, Forcefield):
```bash
cd c:/libraries/prismata-replay-parser && node -e "const fs=require('fs'),z=require('zlib');for(const f of fs.readdirSync('replays_archive').slice(0,5000)){if(!f.endsWith('.json.gz'))continue;const d=JSON.parse(z.gunzipSync(fs.readFileSync('replays_archive/'+f)));if((d.deckInfo?.mergedDeck||[]).some(c=>(c.UIName||c)==='Rhino')){console.log(f.replace('.json.gz',''));break;}}"
```
Verify the HP number appears overlapping/inside the heart icon.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "fix(renderer): adjust fragile HP number to overlap heart icon

SWF renders status numbers overlapping their icons. Updated positioning
for all variable status labels to match."
```

---

### Task 5: Fix Status Icon Sizing and Variable Stack Layout

Wonderboat feedback #1 (icons smaller and misaligned) and #5 (left column overlap). Status icons are 18×18 in SWF. The variable status stack starts at (2, 17) with 20px vertical spacing.

**Files:**
- Modify: `gr/StatusOverlay.ts`
- Modify: `gr/constants.ts`

**SWF reference (UIStatus.as):**
- Icon size: 18×18
- Variable container position: (2, 17)
- Vertical spacing: 20px per entry
- Count label: x = icon_width + 2 (20px from left), y = aligned with icon center

- [ ] **Step 1: Verify icon sizes match SWF**

Check that `STATUS_SIZE = 18` in constants.ts. If icons are appearing smaller, the issue may be in how sprites are scaled. Ensure icon sprites are rendered at exactly 18×18 without additional scaling.

- [ ] **Step 2: Fix variable stack positioning**

In `StatusOverlay.ts`, verify the variable container is at (2, 17) and each entry is spaced 20px apart. The count label should be at `x = STATUS_SIZE + 2` (right of icon), vertically centered with the icon.

```typescript
// Each variable status entry (SWF line 227: numVar * 20 + offset + 4)
const entryY = numVariable * 20 + VARIABLE_STATUS.Y_BASELINE;
icon.x = 1;
icon.y = entryY;
icon.width = STATUS_SIZE;
icon.height = STATUS_SIZE;

countLabel.x = STATUS_SIZE + 4; // Right of icon with small gap
countLabel.y = entryY + (STATUS_SIZE - countLabel.height) / 2; // Vertically centered
```

- [ ] **Step 3: Verify left column doesn't overlap card art**

The status container at x=2 keeps icons within the left edge. If card art extends into the status area, the issue is in `ART_INSET` (should be 5px). Verify art sprite positioning.

- [ ] **Step 4: Build and verify with multi-status units**

Load a replay with Tia (stamina + blocker), Aegis (charge + blocker), or other multi-status units.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "fix(renderer): correct status icon sizing and variable stack layout

Icons render at exact 18x18 SWF size, variable stack properly spaced."
```

---

### Task 6: Multi-Status Unit Stress Test

Wonderboat feedback #6. Verify complex units render correctly with multiple simultaneous statuses.

**Files:**
- Modify: `gr/StatusOverlay.ts` (if bugs found)
- Create: `gr/__tests__/status-overlay.test.ts`

- [ ] **Step 1: Write test cases for multi-status combinations**

Create `gr/__tests__/status-overlay.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';

describe('StatusOverlay multi-status combinations', () => {
  // Tia: stamina (lifespan) + blocker + attack
  it('handles lifespan + defaultBlocking + attack', () => {
    const statuses = computeStatuses({
      lifespan: 3,
      defaultBlocking: true,
      attack: 1,
      toughness: 3,
    });
    expect(statuses.variable).toContainEqual({ type: 'doom', count: 3 });
    expect(statuses.fixed).toContainEqual({ type: 'attack', count: 1 });
    expect(statuses.fixed).toContainEqual({ type: 'defend', count: 3 });
  });

  // Aegis: charge + blocker + fragile
  it('handles charge + defaultBlocking + fragile HP', () => {
    const statuses = computeStatuses({
      charge: 1,
      defaultBlocking: true,
      fragile: true,
      toughness: 1,
    });
    expect(statuses.variable).toContainEqual({ type: 'charge', count: 1 });
    expect(statuses.fixed).toContainEqual({ type: 'defend', count: 1 });
  });

  // Centurion: frontline + blocker + attack
  it('handles frontline + blocker + attack', () => {
    const statuses = computeStatuses({
      frontline: true,
      defaultBlocking: true,
      attack: 1,
      toughness: 3,
    });
    expect(statuses.variable).toContainEqual({ type: 'frontline' });
    expect(statuses.fixed).toContainEqual({ type: 'attack', count: 1 });
  });

  // Chilled unit with delay
  it('handles chill + delay', () => {
    const statuses = computeStatuses({
      chill: 2,
      delay: 1,
    });
    expect(statuses.variable).toContainEqual({ type: 'delay', count: 1 });
    expect(statuses.variable).toContainEqual({ type: 'chill', count: 2 });
  });
});
```

**Implementation note:** `StatusOverlay.update()` directly creates PixiJS display objects — there is no pure `computeStatuses()` function. Two options:
1. **Extract a pure function** from StatusOverlay that computes which statuses to show and their positions, then test that function. This is the preferred approach — it also makes the rendering logic more testable.
2. **Test via container inspection** — call `update()` on a StatusOverlay instance and inspect the resulting PixiJS container children.

If extracting a pure function, create it in `StatusOverlay.ts` and export it for testing.

- [ ] **Step 2: Run tests**

Run: `cd <LADDER_REPO_PATH>/<ladder>-site && npx vitest run src/components/game-renderer/__tests__/status-overlay.test.ts`

- [ ] **Step 3: Fix any rendering issues found**

If multiple statuses overlap or overflow, adjust the variable stack spacing or add overflow handling.

- [ ] **Step 4: Manual verification with complex replays**

Find replays containing multi-status units:
```bash
cd c:/libraries/prismata-replay-parser
# Find Tia games
node -e "const fs=require('fs'),z=require('zlib');let n=0;for(const f of fs.readdirSync('replays_archive').slice(0,5000)){if(!f.endsWith('.json.gz'))continue;const d=JSON.parse(z.gunzipSync(fs.readFileSync('replays_archive/'+f)));if((d.deckInfo?.mergedDeck||[]).some(c=>(c.UIName||c)==='Tia Thurnax')){console.log(f.replace('.json.gz',''));if(++n>=3)break;}}"
```

Load these in the viewer and verify all statuses display without overlap.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test(renderer): add multi-status unit stress tests

Covers Tia (lifespan+blocker+attack), Aegis (charge+blocker+fragile),
Centurion (frontline+blocker+attack), and chill+delay combinations."
```

---

### Task 7: Fix Chill Snowflake Position

The SWF positions the chill snowflake at (41, 43) — center of the card. Verify our position matches.

**Files:**
- Modify: `gr/UnitCard.ts`

**SWF reference (UIInst.as):** `chill snowflake at (41, 43)` — approximately center of 82×82 card.

- [ ] **Step 1: Check current snowflake position in UnitCard.ts**

Read the snowflake sprite positioning. It should be approximately centered at (41, 43).

- [ ] **Step 2: Fix if misaligned**

```typescript
// Chill snowflake — SWF position (41, 43), centered on 82×82 card
chillSprite.x = 41;
chillSprite.y = 43;
chillSprite.anchor.set(0.5, 0.5);
```

- [ ] **Step 3: Commit if changed**

```bash
git add -A && git commit -m "fix(renderer): correct chill snowflake position to SWF (41, 43)"
```

---

### Task 8: Fix Drone Supply Count for P2

Wonderboat feedback #7. P2 starts with one more Drone than P1, so the supply counter should show 1 fewer available for P2.

**Files:**
- Modify: `gr/BuyCard.ts`
- Modify: `gr/BuyPanel.ts`
- Modify: `gr/BoardRenderer.ts` (to pass player info)
- Create: `gr/__tests__/buy-panel.test.ts`

**Context:** Supply is derived from rarity (legendary=1, rare=4, normal=10, trinket=20). P2 starts with an extra Drone, so at game start, Drone supply shows 3 remaining (not 4). The engine's `whiteSupplySpent`/`blackSupplySpent` arrays in the game state may already track this correctly. Check first.

- [ ] **Step 1: Verify existing supply computation**

Read `BuyPanel.ts` lines 55-70. It already computes remaining supply from `totalSupply - spent` using the engine's supply arrays. Check whether these arrays already account for starting units (Drone, Engineer, Conduit, Blastforge, Animus).

Load a replay at turn 1 in the browser and check: does the Drone supply already show the correct count? If yes, this task is done — just document it and skip to Step 5.

- [ ] **Step 2: If supply is wrong, trace the data path**

If the engine supply arrays don't account for starting units, compute remaining from instances:
```typescript
const totalOnBoard = gameState.instances.filter(
  i => i.cardName === cardName
).length;
const remaining = maxSupply - totalOnBoard;
```

- [ ] **Step 3: Write test if a fix was needed**

Create `gr/__tests__/buy-panel.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';

describe('Buy panel supply display', () => {
  it('accounts for starting units in supply count', () => {
    // P1: 6 Drones, P2: 7 Drones, supply 10 → 10 - 13 = can't go negative
    // Supply is shared: 10 total for both players combined is wrong
    // Actually: supply is per-player. Each player has supply 10.
    // P1 spent 6 → 4 remaining. P2 spent 7 → 3 remaining.
    // Verify the display shows the correct count for the active player.
  });
});
```

- [ ] **Step 4: Visually verify**

Load a replay at turn 1. Drone supply for P1 should show 4 (10 - 6 starting), for P2 should show 3 (10 - 7 starting).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "fix(renderer): verify Drone supply accounts for P2 extra starting unit"
```

---

## Stream 2: Board HUD — Attack/Defense/Chill in PixiJS Canvas

### Task 9: Enhance Midline Attack/Defense Display

The current `BoardRenderer.ts` already has a midline display with attack/defense icons. This task enhances it to match SWF styling with proper sizing, coloring, and a danger indicator.

**Files:**
- Modify: `gr/BoardRenderer.ts`
- Modify: `gr/constants.ts`

**SWF reference:** Between player areas:
- Sword icon (red) with attack number
- Shield icon (blue) with defense number
- Snowflake with total chill
- Red `(!)` danger indicator when attack > total defense

- [ ] **Step 1: Add chill display to midline**

In `BoardRenderer.ts`, extend the midline container to include a snowflake icon with total chill count for each player:

```typescript
// Add to midline update:
const p0Chill = gameState.instances
  .filter(i => i.owner === 0 && i.chill > 0)
  .reduce((sum, i) => sum + i.chill, 0);
// Display snowflake + count between attack and defense
```

- [ ] **Step 2: Add danger indicator**

When a player's incoming attack exceeds their total available defense, show a red warning:

```typescript
const totalDefense = gameState.instances
  .filter(i => i.owner === playerIdx && i.canBlock && !i.blocking && i.constructionTime === 0)
  .reduce((sum, i) => sum + (i.toughness || 0), 0);

if (incomingAttack > totalDefense) {
  dangerIcon.visible = true;
  dangerIcon.tint = 0xFF3333;
}
```

- [ ] **Step 3: Style numbers to match SWF**

Apply `FONT_CONFIG` stroke styling to midline numbers. Use larger font size (16-18pt) for visibility.

- [ ] **Step 4: Build and verify**

Load a replay with attack happening. Verify sword/shield/snowflake icons display correctly between player areas with danger indicator appearing when attack > defense.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(renderer): add chill display and danger indicator to board HUD

Midline now shows chill totals and red warning when attack > defense."
```

---

### Task 10: Resource Bar Polish

Verify resource bars match SWF positioning and styling.

**Files:**
- Modify: `gr/ResourceBar.ts`

**SWF reference (UIResourceBar):** Resource bar at bottom of each player's area showing gold, blue, green, red, energy with icons and counts.

- [ ] **Step 1: Read current ResourceBar.ts**

Verify icon ordering, sizing, and number styling match SWF.

- [ ] **Step 2: Apply FONT_CONFIG stroke to resource numbers**

```typescript
const resourceStyle = new TextStyle({
  fontFamily: 'Arial',
  fontSize: 12,
  fontWeight: 'bold',
  fill: 0xFFFFFF,
  stroke: { color: FONT_CONFIG.STROKE_COLOR, width: 2 },
});
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "fix(renderer): apply consistent font styling to resource bar numbers"
```

---

## Stream 5 (Foundation): Visual Regression Infrastructure

### Task 11: Curate Test Replay Set

Select diverse replays for manual visual comparison and future automated testing.

**Files:**
- Create: `<ladder>-site/tests/visual-baselines/replay-codes.txt`

- [ ] **Step 1: Find replays covering key visual scenarios**

```bash
cd c:/libraries/prismata-replay-parser
# Find replays with diverse unit types for visual testing
node -e "
const fs = require('fs'), z = require('zlib');
const targets = ['Tia Thurnax', 'Centurion', 'Aegis', 'Rhino', 'Odin', 'Drake', 'Tatsu Nullifier'];
const found = {};
for (const f of fs.readdirSync('replays_archive').slice(0, 10000)) {
  if (!f.endsWith('.json.gz')) continue;
  try {
    const d = JSON.parse(z.gunzipSync(fs.readFileSync('replays_archive/' + f)));
    const deck = (d.deckInfo?.mergedDeck || []).map(c => c.UIName || c);
    for (const t of targets) {
      if (!found[t] && deck.includes(t)) {
        found[t] = f.replace('.json.gz', '');
        console.log(t + ': ' + found[t]);
      }
    }
  } catch {}
  if (Object.keys(found).length === targets.length) break;
}
"
```

- [ ] **Step 2: Create replay codes file**

Save the found codes plus a few manually-selected diverse replays (short games, long games, breach games) into `tests/visual-baselines/replay-codes.txt`, one code per line with a comment describing what it tests.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "test(renderer): curate visual regression replay set

Diverse replays covering multi-status units, breach, complex boards."
```

---

## Verification Checklist

After all tasks, verify against Wonderboat's 10 feedback items:

| # | Feedback | Task | Status |
|---|----------|------|--------|
| 1 | Icons smaller/misaligned | Task 5 | |
| 2 | Fatter font on numbers | Task 1 | |
| 3 | Sword facing wrong way | Task 2 | |
| 4 | Fragile HP inside heart | Task 4 | |
| 5 | Left column overlap | Task 5 | |
| 6 | Multi-status stress test | Task 6 | |
| 7 | Drone supply P2 offset | Task 8 | |
| 8 | Non-fragile HP positioning | Task 3 | |
| 9 | Sword text positioning | Task 3 | |
| 10 | Black outline on numbers | Task 1 | |

## Post-Plan Notes

- Each task is independently deployable and testable
- Tasks 1-8 are Stream 1 (unit card polish) — highest priority
- Tasks 9-10 are Stream 2 (board HUD) — can be done after Stream 1
- Task 11 is infrastructure for future automated visual regression
- Streams 3 (animations) and 4 (skins/cosmetics) are deferred — plan separately when Stream 1+2 are complete
- All work is in `<LADDER_REPO_PATH>\` repo, branch from `feature/live-viewer`
