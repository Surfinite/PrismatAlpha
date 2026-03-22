# Browser Game Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PixiJS 8 game board renderer that replaces the HTML/CSS board in the <ladder> site, faithfully recreating the original Prismata Flash client's board.

**Architecture:** PixiJS canvas embedded in the existing React page. Pure rendering logic (visual state mapping, position calculation, layout cramming) is separated from PixiJS components for testability. All layout and state algorithms are faithful ports from the decompiled AS3 source.

**Tech Stack:** PixiJS 8, TypeScript, React 19, Next.js 16, Vitest (testing)

**Spec:** `docs/superpowers/specs/2026-03-22-browser-game-viewer-design.md`

---

## File Structure

### PrismataAI repo (engine bundle changes)

```
js_engine/
├── replay_exporter.js          # MODIFY: Add instId, damage, dead units, boughtThisPhase
├── build_viewer_bundle.js      # MODIFY: Add position to cardMeta, fix asset labels, add missing textures
├── Card.js                     # READ ONLY: Reference for position assignment (lines 269-324)
├── C.js                        # READ ONLY: Reference for constants (POSITION_*, DEADNESS_*, ROLE_*)
├── Inst.js                     # READ ONLY: Reference for instId (line 34), damage (line 53), creatorIdFromBuyOrAbility (line 103)
└── viewer_smoke_test.js        # CREATE: Replay batch smoke test runner
```

### <ladder> repo (PixiJS renderer)

```
<ladder>-site/src/
├── components/game-renderer/
│   ├── index.ts                # Public exports
│   ├── PrismataBoard.tsx       # React wrapper — mounts PixiJS canvas, bridges state
│   ├── BoardRenderer.ts        # Top-level PixiJS Application, state dispatch
│   ├── BoardView.ts            # Per-player board (3 rows + sword barriers)
│   ├── RowView.ts              # Horizontal lane layout — port of UIRow.performCramming()
│   ├── PileView.ts             # Horizontal unit stack — port of UIPile.stretchFactorAmount()
│   ├── UnitCard.ts             # 10-layer card rendering — port of UIInst
│   ├── StatusOverlay.ts        # Status icons — port of UIStatus.changed()
│   ├── BuyPanel.ts             # Two always-visible columns (base + randomizer)
│   ├── BuyCard.ts              # Individual purchasable card (art + cost + supply)
│   ├── ResourceBar.ts          # Gold/B/G/C/H + attack/defense per player
│   ├── visual-state.ts         # Pure function: game state → visual decisions (port of UIInst.update)
│   ├── position-calculator.ts  # Pure function: card properties → board position (port of Card.as)
│   ├── layout-engine.ts        # Pure functions: cramming, stretch factors, big gap (port of UIRow/UIPile)
│   ├── asset-loader.ts         # Texture loading, caching, fallback placeholders
│   ├── constants.ts            # All layout constants from AS3 source
│   └── types.ts                # TypeScript interfaces for game state, visual state, card meta
├── components/game-renderer/__tests__/
│   ├── visual-state.test.ts    # Visual state mapping unit tests
│   ├── position-calculator.test.ts  # Position assignment unit tests
│   └── layout-engine.test.ts   # Cramming + stretch factor tests
└── app/live/[gameId]/
    └── page.tsx                # MODIFY: Replace HTML board with PrismataBoard component
```

---

## Task 1: Engine — Add missing fields to state export

**Repo:** PrismataAI
**Files:**
- Modify: `js_engine/replay_exporter.js:40-54` (instToCardJSON)
- Modify: `js_engine/replay_exporter.js:62-113` (stateToCppJSON)

- [ ] **Step 1: Add `instId` to instToCardJSON**

In `replay_exporter.js`, add `instId` to the returned object at line 41:

```javascript
// replay_exporter.js:instToCardJSON — add after line 41
instId: inst.instId,
```

The JS Inst class uses `this.instId` (Inst.js line 34), NOT `.id`.

- [ ] **Step 2: Add `damage` to instToCardJSON**

```javascript
// replay_exporter.js:instToCardJSON — add after instId
damage: inst.damage,
```

Required for BACK_ABSORB, BACK_WHITEPINK, COVER_BANG, and damage counter rendering.

- [ ] **Step 3: Add `boughtThisPhase` to instToCardJSON**

```javascript
// replay_exporter.js:instToCardJSON — add after damage
boughtThisPhase: inst.creatorIdFromBuyOrAbility >= 0,
```

Maps to AS3 `wasBoughtOrClickCreatedThisPhase()`. Required for big gap pile spacing.

- [ ] **Step 4: Include dead units in stateToCppJSON**

In `stateToCppJSON`, the filter at approximately line 95 currently reads:
```javascript
if (inst.deadness === C.DEADNESS_ALIVE) {
```

Change this to include all units (or at minimum, include dead units too):
```javascript
// Include all units — dead units render on board with BACK_DEAD + skull until swoosh
```

Remove or comment out the alive-only filter. Dead units already have `deadness` exported.

- [ ] **Step 5: Verify with a quick test**

```bash
cd c:/libraries/PrismataAI
node -e "
const RE = require('./js_engine/replay_exporter');
// Load a test state and check the new fields exist
console.log('Fields check passed');
"
```

- [ ] **Step 6: Commit**

```bash
git add js_engine/replay_exporter.js
git commit -m "feat(engine): add instId, damage, boughtThisPhase to state export; include dead units"
```

---

## Task 2: Engine — Add position to card metadata & fix bundle assets

**Repo:** PrismataAI
**Files:**
- Modify: `js_engine/build_viewer_bundle.js:50-72` (buildCardMetadata)
- Modify: `js_engine/build_viewer_bundle.js:74-110` (collectSmallAssets)
- Reference: `js_engine/Card.js:269-324` (position assignment logic)
- Reference: `js_engine/C.js:97-114` (POSITION_* constants)

- [ ] **Step 1: Add position to buildCardMetadata()**

Port the position assignment logic from Card.js lines 269-324. This is a priority chain based on card properties. Add to the metadata object returned per card:

```javascript
// build_viewer_bundle.js:buildCardMetadata — add position field
position: computePosition(card),
```

Where `computePosition(card)` implements the 19-priority chain from the spec (Card.as). The JS Card.js already has this logic at lines 269-324 — reference it directly. The position constants are in C.js lines 97-114.

- [ ] **Step 2: Fix asset labels and add missing textures in collectSmallAssets()**

Current mislabel: `bg_construction` maps to `Card_Orange.png` (actually BACK_ABSORB).

Fix and extend the bgFiles map:

```javascript
const bgFiles = {
    'bg_dead':       'Card_Dead.png',      // BACK_DEAD (0) — verify Card_Dead.png vs Card_Inver.png are same image
    'bg_block':      'Card_Blue.png',      // BACK_BLOCK (1)
    'bg_busy':       'Card_Grey.png',      // BACK_BUSY (2)
    'bg_absorb':     'Card_Orange.png',    // BACK_ABSORB (3) — was mislabeled bg_construction
    'bg_chilled':    'Card_Blue_Frost.png',// BACK_BLOCK_FROST (4)
    'bg_bought':     'Card_Trans.png',     // BACK_BOUGHT (5) — NEW
    'bg_whitepink':  'Card_WhitePink.png', // BACK_WHITEPINK (6) — NEW
    'bg_blockred':   'Card_Red.png',       // BACK_BLOCKRED (7)
    'bg_busyblue':   'Card_BlueGrey.png',  // BACK_BUSYBLUE (8) — NEW (was bg_default)
    'bg_busyred':    'Card_RedGrey.png',   // BACK_BUSYRED (9) — NEW (was bg_default_red)
    'bg_border_green': 'Card_Border_Green.png',
    'border_yellow':        'border_yellow.png',       // NEW
    'border_yellow_urgent': 'border_yellow_urgent.png',// NEW
};
```

Also add cover, shading textures from `bin/asset/images/icons/status/` and `bin/asset/images/cardbg/`.

- [ ] **Step 3: Verify assets exist on disk**

```bash
ls bin/asset/images/cardbg/Card_Trans.png bin/asset/images/cardbg/Card_WhitePink.png bin/asset/images/cardbg/Card_BlueGrey.png bin/asset/images/cardbg/Card_RedGrey.png
```

- [ ] **Step 4: Commit**

```bash
git add js_engine/build_viewer_bundle.js
git commit -m "feat(engine): add position to cardMeta, fix asset labels, add all 10 background textures"
```

---

## Task 3: Engine — Rebuild bundle

**Repo:** PrismataAI
**Files:**
- Read: `js_engine/build_viewer_bundle.js`
- Output: `<LADDER_REPO_PATH>/<ladder>-site/public/js/prismata-engine.js`

- [ ] **Step 1: Rebuild the bundle**

```bash
cd c:/libraries/PrismataAI
node js_engine/build_viewer_bundle.js
```

- [ ] **Step 2: Verify new fields in output**

```bash
node -e "
require('./js_engine/build_viewer_bundle.js');
// or load the output bundle and check PrismataViewer.getCardMeta() has position field
"
```

- [ ] **Step 3: Copy to ladder site**

```bash
cp js_engine/prismata-engine.js <LADDER_REPO_PATH>/<ladder>-site/public/js/prismata-engine.js
```

- [ ] **Step 4: Commit in ladder repo**

```bash
cd <LADDER_REPO_PATH>
git add <ladder>-site/public/js/prismata-engine.js
git commit -m "build: update engine bundle with position, instId, damage fields"
```

Note: `build_viewer_bundle.js` was already committed in Task 2.

---

## Task 4: Ladder — Project setup

**Repo:** <ladder>
**Files:**
- Modify: `<ladder>-site/package.json`
- Create: `<ladder>-site/src/components/game-renderer/constants.ts`
- Create: `<ladder>-site/src/components/game-renderer/types.ts`
- Create: `<ladder>-site/src/components/game-renderer/index.ts`

- [ ] **Step 1: Install PixiJS 8**

```bash
cd <LADDER_REPO_PATH>/<ladder>-site
npm install pixi.js@^8
```

- [ ] **Step 2: Install Vitest for testing**

```bash
npm install -D vitest
```

- [ ] **Step 2b: Create vitest.config.ts**

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
  },
  resolve: {
    alias: { '@': './src' },
  },
});
```

Add `"test": "vitest run"` to package.json scripts.

- [ ] **Step 3: Create constants.ts**

Port all layout constants from AS3 source. Reference files:
- UIInst.as lines 56-100 (card/layer constants)
- UIRow.as lines 12-30 (spacing/margin constants)
- UIPile.as lines 39-73 (gap/speed constants)
- UIBoard.as lines 52-72 (field dimensions)
- UIStatus.as lines 17-55 (status icon constants)
- C.js lines 97-114 (POSITION_* constants)

```typescript
// constants.ts
export const CARD_WIDTH = 83;  // UIInst.WIDTH
export const CARD_HEIGHT = 82; // UIInst.HEIGHT

// Card background frame indices (UIInst.as lines 56-66)
export const BACK_DEAD = 0;
export const BACK_BLOCK = 1;
export const BACK_BUSY = 2;
export const BACK_ABSORB = 3;
export const BACK_BLOCK_FROST = 4;
export const BACK_BOUGHT = 5;
export const BACK_WHITEPINK = 6;
export const BACK_BLOCKRED = 7;
export const BACK_BUSYBLUE = 8;
export const BACK_BUSYRED = 9;

// Cover overlay frame indices (UIInst.as lines 68-73)
export const COVER_EMPTY = 0;
export const COVER_INVSPAWN = 1;
export const COVER_INVBOUGHT = 2;
export const COVER_ASSIGNED = 3;
export const COVER_PROMPT = 4;
export const COVER_BANG = 5;

// Shading frame indices
export const SHADING_EMPTY = 0;
export const SHADING_NOTBLOCK = 1;
export const SHADING_BLOCK = 2;
export const SHADING_DEAD_BLOCK = 3;
export const SHADING_REDBLOCK = 4;

// Status icon indices (UIStatus.as lines 26-42)
export const STATUS_EMPTYPIXEL = 0;
export const STATUS_HP = 1;
export const STATUS_FRONTLINE = 2;
export const STATUS_DELAY = 3;
export const STATUS_DOOM = 4;
export const STATUS_CHARGE0 = 5;
export const STATUS_CHARGE1 = 6;
export const STATUS_CHARGE2 = 7;
export const STATUS_CHARGE3 = 8;
export const STATUS_TAP_ON = 9;
export const STATUS_TAP = 10;
export const STATUS_ATTACK = 11;
export const STATUS_SPELL = 12;
export const STATUS_DEFEND = 13;
export const STATUS_SIZE = 18;
export const STATUS_SPACING = 4;

// Row layout (UIRow.as lines 12-30)
export const CARDSPACING = [0, 18, 18, 18, 17, 17, 17, 16];
export const DEFAULTCARDSPACING = 16;
export const CRAMMEDCARDSPACING = 13;
export const DEFAULTMARGIN = 20;
export const NICEMARGIN = 3;
export const CRAMMEDMARGIN = -40;
export const MIN_CRAM_PERCENT = 0.8;

// Pile (UIPile.as lines 39-43)
export const GAP_SIZE = 2.5;

// Board layout (UIBoard.as lines 149-155)
export const MID_LINE_GUTTER_NORMAL = 4;
export const MID_LINE_GUTTER_REPLAY = 2;
export const ROW_GAP_NORMAL = 5;
export const ROW_GAP_REPLAY = 1;

// Position constants (C.js lines 97-114)
export const POSITION_FRONT_FAR_LEFT = 0;
export const POSITION_FRONT_FAR_LEFT_ONE = 1;
export const POSITION_FRONT_FAR_LEFT_TWO = 2;
export const POSITION_FRONT_LEFT = 3;
export const POSITION_FRONT_LEFT_ONE = 4;
export const POSITION_FRONT_RIGHT = 6;
export const POSITION_FRONT_RIGHT_ONE = 7;
export const POSITION_MIDDLE_FAR_LEFT = 10;
export const POSITION_MIDDLE_FAR_LEFT_ONE = 11;
export const POSITION_MIDDLE_LEFT = 13;
export const POSITION_MIDDLE_RIGHT = 16;
export const POSITION_MIDDLE_FAR_RIGHT = 18;
export const POSITION_BACK_FAR_LEFT = 20;
export const POSITION_BACK_FAR_LEFT_ONE = 21;
export const POSITION_BACK_FAR_LEFT_TWO = 22;
export const POSITION_BACK_LEFT = 23;
export const POSITION_BACK_RIGHT = 26;
export const POSITION_BACK_FAR_RIGHT = 29;
```

- [ ] **Step 4: Create types.ts**

```typescript
// types.ts — interfaces matching the engine's getGameState() and getCardMeta() output

export interface CardInstance {
  instId: number;
  cardName: string;
  owner: number;           // 0 or 1
  health: number;
  damage: number;
  role: string;            // 'default' | 'assigned' | 'sellable' | 'inert'
  deadness: string;        // 'alive' | 'selfsacced' | 'sacced' | 'blocked' | 'meleed' | 'breached' | 'sniped' | 'autosniped' | 'aged'
  constructionTime: number;
  charge: number;
  delay: number;
  lifespan: number;        // -1 = infinite
  disruptDamage: number;
  blocking: boolean;
  boughtThisPhase: boolean;
}

export interface GameState {
  whiteMana: string;
  blackMana: string;
  turn: number;            // 0 = P0/white, 1 = P1/black
  numTurns: number;
  phase: string;           // 'defense' | 'action' | 'confirm'
  cards: string[];         // purchasable card display names
  whiteTotalSupply: number[];
  blackTotalSupply: number[];
  whiteSupplySpent: number[];
  blackSupplySpent: number[];
  table: CardInstance[];
}

export interface CardMeta {
  attack: number;
  autoAttack: number;
  abilityAttack: number;
  toughness: number;
  hasAbility: boolean;
  hasTargetAbility: boolean;
  isFrontline: boolean;
  canBlock: boolean;
  isFragile: boolean;
  defaultBlocking: boolean;
  buyCost: string;
  buildTime: number;
  lifespan: number;
  charge: number;
  baseSet: boolean;
  rarity: string;
  position: number;        // NEW — static board position from Card.as priority chain
}

export interface CardMetaMap {
  [cardName: string]: CardMeta;
}

export interface VisualState {
  backFrame: number;       // 0-9 (BACK_* constants)
  coverFrame: number;      // 0-5 (COVER_* constants)
  shadingFrame: number;    // 0-4 (SHADING_* constants)
  cardAlpha: number;       // 0.87 for construction, 1.0 otherwise
  showSkull: boolean;
  showChillSnowflake: boolean;
  damageCounter: number;   // 0 = hidden
  statusIcons: number[];   // array of STATUS_* constants to display
}
```

- [ ] **Step 5: Create index.ts**

```typescript
// index.ts
export { PrismataBoard } from './PrismataBoard';
export type { GameState, CardInstance, CardMeta, CardMetaMap, VisualState } from './types';
```

- [ ] **Step 6: Commit**

```bash
git add -A src/components/game-renderer/
git commit -m "feat: scaffold game renderer with PixiJS dep, constants, and types"
```

---

## Task 5: Ladder — Position calculator (TDD)

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/position-calculator.ts`
- Create: `<ladder>-site/src/components/game-renderer/__tests__/position-calculator.test.ts`
- Reference: `c:/libraries/PrismataAI/js_engine/Card.js:269-324`

**Note:** The engine bundle (Task 2) already precomputes `position` in `getCardMeta()`. This module provides `getRow()` utility and can serve as a fallback if CardMeta is unavailable. The main value is the `getRow()` function used by BoardView to route units to rows.

- [ ] **Step 1: Write failing tests**

```typescript
// __tests__/position-calculator.test.ts
import { describe, it, expect } from 'vitest';
import { computePosition } from '../position-calculator';
import * as C from '../constants';

describe('computePosition', () => {
  it('returns explicit position when card has one', () => {
    expect(computePosition({ position: 15 } as any)).toBe(15);
  });

  it('assigns Conduit to BACK_FAR_LEFT (20)', () => {
    expect(computePosition({ UIName: 'Conduit' } as any)).toBe(C.POSITION_BACK_FAR_LEFT);
  });

  it('assigns Drone to MIDDLE_FAR_LEFT (10)', () => {
    expect(computePosition({ UIName: 'Drone' } as any)).toBe(C.POSITION_MIDDLE_FAR_LEFT);
  });

  it('assigns Engineer to FRONT_FAR_LEFT (0)', () => {
    expect(computePosition({ UIName: 'Engineer' } as any)).toBe(C.POSITION_FRONT_FAR_LEFT);
  });

  it('assigns spell to BACK_FAR_RIGHT (29)', () => {
    expect(computePosition({ cardType: 'spell' } as any)).toBe(C.POSITION_BACK_FAR_RIGHT);
  });

  it('assigns undefendable attacker to FRONT_RIGHT_ONE (7)', () => {
    expect(computePosition({ undefendable: true, attackPotential: 1 } as any)).toBe(C.POSITION_FRONT_RIGHT_ONE);
  });

  it('assigns default blocker to FRONT_FAR_LEFT_ONE (1)', () => {
    expect(computePosition({ defaultBlocking: true } as any)).toBe(C.POSITION_FRONT_FAR_LEFT_ONE);
  });

  it('assigns plain attacker to BACK_RIGHT (26)', () => {
    expect(computePosition({ attackPotential: 2 } as any)).toBe(C.POSITION_BACK_RIGHT);
  });

  it('assigns boring unit to BACK_LEFT (23)', () => {
    expect(computePosition({} as any)).toBe(C.POSITION_BACK_LEFT);
  });

  it('derives row from position: floor(pos/10)', () => {
    expect(Math.floor(C.POSITION_FRONT_LEFT / 10)).toBe(0);    // front
    expect(Math.floor(C.POSITION_MIDDLE_RIGHT / 10)).toBe(1);  // middle
    expect(Math.floor(C.POSITION_BACK_LEFT / 10)).toBe(2);     // back
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd <LADDER_REPO_PATH>/<ladder>-site
npx vitest run src/components/game-renderer/__tests__/position-calculator.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement position-calculator.ts**

Port the priority chain from Card.js lines 269-324. This is a direct 1:1 port with TypeScript types.

```typescript
// position-calculator.ts
import * as C from './constants';
import type { CardMeta } from './types';

/**
 * Compute a card type's static board position.
 * Port of Card.as position assignment (lines 269-324).
 * Row = floor(position / 10): 0=front, 1=middle, 2=back.
 */
export function computePosition(card: Partial<CardMeta> & Record<string, any>): number {
  // Priority 1: Explicit position
  if (card.position != null && card.position >= 0) return card.position;

  // Priority 2-6: Named base units
  const name = card.UIName || card.cardName || '';
  if (name === 'Conduit')    return C.POSITION_BACK_FAR_LEFT;
  if (name === 'Blastforge') return C.POSITION_BACK_FAR_LEFT_ONE;
  if (name === 'Animus')     return C.POSITION_BACK_FAR_LEFT_TWO;
  if (name === 'Drone')      return C.POSITION_MIDDLE_FAR_LEFT;
  if (name === 'Engineer')   return C.POSITION_FRONT_FAR_LEFT;

  // Priority 7: Spell
  if (card.cardType === 'spell') return C.POSITION_BACK_FAR_RIGHT;

  const hasAbility = !!card.hasAbility || !!card.abilityScript || !!card.targetAction;
  const attacks = (card.attackPotential || card.attack || 0) > 0;
  const targets = !!card.hasTargetAbility || !!card.targetAction;
  const attacksOrTargets = attacks || targets;

  // Priority 8-9: Undefendable
  if (card.undefendable || card.isFrontline) {
    return attacksOrTargets ? C.POSITION_FRONT_RIGHT_ONE : C.POSITION_FRONT_RIGHT;
  }

  // Priority 10-15: Has ability
  if (hasAbility) {
    if (card.defaultBlocking && card.assignedBlocking) {
      return attacksOrTargets ? C.POSITION_FRONT_LEFT_ONE : C.POSITION_FRONT_LEFT;
    }
    if (card.defaultBlocking) {
      return attacksOrTargets ? C.POSITION_MIDDLE_RIGHT : C.POSITION_MIDDLE_FAR_LEFT_ONE;
    }
    return attacksOrTargets ? C.POSITION_MIDDLE_FAR_RIGHT : C.POSITION_MIDDLE_LEFT;
  }

  // Priority 16-17: Default blocking (no ability)
  if (card.defaultBlocking || card.canBlock) {
    return attacksOrTargets ? C.POSITION_FRONT_FAR_LEFT_TWO : C.POSITION_FRONT_FAR_LEFT_ONE;
  }

  // Priority 18: Attacks/targets only
  if (attacksOrTargets) return C.POSITION_BACK_RIGHT;

  // Priority 19: Default
  return C.POSITION_BACK_LEFT;
}

/** Get row index (0=front, 1=middle, 2=back) from position value */
export function getRow(position: number): number {
  return Math.floor(position / 10);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/components/game-renderer/__tests__/position-calculator.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/components/game-renderer/position-calculator.ts src/components/game-renderer/__tests__/position-calculator.test.ts
git commit -m "feat: position calculator with TDD (port of Card.as position assignment)"
```

---

## Task 6: Ladder — Visual state mapper (TDD)

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/visual-state.ts`
- Create: `<ladder>-site/src/components/game-renderer/__tests__/visual-state.test.ts`
- Reference: `c:/libraries/PrismataAI/prismata_decompiled/scripts/starlingUI/game/board/UIInst.as:766-960` (updateBeforeRender / update)

This is the most complex port. The full state machine is ~150 lines in AS3. Port it faithfully from UIInst.as.

- [ ] **Step 1: Write failing tests for key state combinations**

```typescript
// __tests__/visual-state.test.ts
import { describe, it, expect } from 'vitest';
import { computeVisualState } from '../visual-state';
import * as C from '../constants';

const base = {
  instId: 1, cardName: 'Wall', owner: 0, health: 3, damage: 0,
  role: 'default', deadness: 'alive', constructionTime: 0,
  charge: 0, delay: 0, lifespan: -1, disruptDamage: 0,
  blocking: false, boughtThisPhase: false,
};

const wallMeta = {
  defaultBlocking: true, isFragile: false, hasAbility: false,
  attack: 0, toughness: 3, rarity: 'normal', position: 1,
} as any;

describe('computeVisualState', () => {
  it('default idle P0 → BACK_BUSYBLUE', () => {
    const vs = computeVisualState(base, wallMeta, 'action', 0);
    expect(vs.backFrame).toBe(C.BACK_BUSYBLUE);
    expect(vs.coverFrame).toBe(C.COVER_EMPTY);
  });

  it('default idle P1 → BACK_BUSYRED', () => {
    const vs = computeVisualState({ ...base, owner: 1 }, wallMeta, 'action', 0);
    expect(vs.backFrame).toBe(C.BACK_BUSYRED);
  });

  it('dead → BACK_DEAD + skull', () => {
    const vs = computeVisualState({ ...base, deadness: 'blocked' }, wallMeta, 'action', 0);
    expect(vs.backFrame).toBe(C.BACK_DEAD);
    expect(vs.showSkull).toBe(true);
  });

  it('constructing → BACK_BOUGHT + alpha 0.87 + clock overlay', () => {
    const vs = computeVisualState({ ...base, constructionTime: 2 }, wallMeta, 'action', 0);
    expect(vs.backFrame).toBe(C.BACK_BOUGHT);
    expect(vs.cardAlpha).toBeCloseTo(0.87);
    expect([C.COVER_INVBOUGHT, C.COVER_INVSPAWN]).toContain(vs.coverFrame);
  });

  it('blocking P0 → BACK_BLOCK + SHADING_BLOCK', () => {
    const vs = computeVisualState({ ...base, blocking: true }, wallMeta, 'defense', 0);
    expect(vs.backFrame).toBe(C.BACK_BLOCK);
    expect(vs.shadingFrame).toBe(C.SHADING_BLOCK);
  });

  it('blocking P1 → BACK_BLOCKRED + SHADING_REDBLOCK', () => {
    const vs = computeVisualState({ ...base, owner: 1, blocking: true }, wallMeta, 'defense', 0);
    expect(vs.backFrame).toBe(C.BACK_BLOCKRED);
    expect(vs.shadingFrame).toBe(C.SHADING_REDBLOCK);
  });

  it('fully chilled (not defense) → BACK_BLOCK_FROST + snowflake', () => {
    const vs = computeVisualState({ ...base, disruptDamage: 3, health: 3 }, wallMeta, 'action', 0);
    expect(vs.backFrame).toBe(C.BACK_BLOCK_FROST);
    expect(vs.showChillSnowflake).toBe(true);
  });

  it('fully chilled during defense → no snowflake', () => {
    const vs = computeVisualState({ ...base, disruptDamage: 3, health: 3 }, wallMeta, 'defense', 0);
    expect(vs.showChillSnowflake).toBe(false);
  });

  it('partial damage blocking defense → BACK_ABSORB + COVER_BANG + damage counter', () => {
    const vs = computeVisualState({ ...base, blocking: true, damage: 1, health: 3 }, wallMeta, 'defense', 0);
    expect(vs.backFrame).toBe(C.BACK_ABSORB);
    expect(vs.coverFrame).toBe(C.COVER_BANG);
    expect(vs.damageCounter).toBe(1);
  });

  it('sellable blocking → COVER_PROMPT + SHADING_EMPTY', () => {
    const vs = computeVisualState({ ...base, role: 'sellable', blocking: true }, wallMeta, 'defense', 0);
    expect(vs.coverFrame).toBe(C.COVER_PROMPT);
    expect(vs.shadingFrame).toBe(C.SHADING_EMPTY);  // UIInst.as line 858: shading stays EMPTY for sellable+blocking
  });

  it('assigned → COVER_ASSIGNED', () => {
    const vs = computeVisualState({ ...base, role: 'assigned' }, wallMeta, 'action', 0);
    expect(vs.coverFrame).toBe(C.COVER_ASSIGNED);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npx vitest run src/components/game-renderer/__tests__/visual-state.test.ts
```

- [ ] **Step 3: Implement visual-state.ts**

Port `UIInst.updateBeforeRender()` (UIInst.as lines 766-960) faithfully. This is the core ~150-line state machine. Read the AS3 source and translate each branch. Key considerations:

- `colorOnBottom = 0` for replay viewer (P0 is always blue/bottom)
- Owner color: `owner === colorOnBottom` → blue, else → red
- Dead check: `deadness !== 'alive'`
- Phase string: matches C.js PHASE_* constants

```typescript
// visual-state.ts
import type { CardInstance, VisualState } from './types';
import * as K from './constants';

/**
 * Compute the visual state for a unit card.
 * Port of UIInst.updateBeforeRender() — UIInst.as lines 766-960.
 * This is a pure function: game state in, visual decisions out.
 */
export function computeVisualState(
  inst: CardInstance,
  cardMeta: CardMeta,
  phase: string,
  colorOnBottom: number = 0,
): VisualState {
  // Port the full AS3 state machine here.
  // Reference: prismata_decompiled/scripts/starlingUI/game/board/UIInst.as
  // ... (full implementation from AS3 source)
}
```

The implementation must cover ALL branches from UIInst.as lines 766-960, including:
- ROLE_SELLABLE branches (spell, blocking, non-blocking)
- ROLE_ASSIGNED branch
- defaultBlocking + !blocking → SHADING_NOTBLOCK
- damage sub-branches (partially damaged, dead-from-damage, fully damaged)
- Chill snowflake phase condition (hidden during defense)
- Owner-based color selection via colorOnBottom

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/components/game-renderer/__tests__/visual-state.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add src/components/game-renderer/visual-state.ts src/components/game-renderer/__tests__/visual-state.test.ts
git commit -m "feat: visual state mapper with TDD (port of UIInst.update state machine)"
```

---

## Task 7: Ladder — Layout engine (TDD)

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/layout-engine.ts`
- Create: `<ladder>-site/src/components/game-renderer/__tests__/layout-engine.test.ts`
- Reference: `c:/libraries/PrismataAI/prismata_decompiled/scripts/starlingUI/game/board/UIRow.as:121-265`
- Reference: `c:/libraries/PrismataAI/prismata_decompiled/scripts/starlingUI/game/board/UIPile.as:998-1048`

- [ ] **Step 1: Write failing tests for stretchFactorAmount**

```typescript
// __tests__/layout-engine.test.ts
import { describe, it, expect } from 'vitest';
import { stretchFactorAmount, instsNeedABigGap, performCramming } from '../layout-engine';

describe('stretchFactorAmount', () => {
  it('returns 1.0 for single card in pile', () => {
    expect(stretchFactorAmount(0, 1, 1.0)).toBeCloseTo(1.0);
  });

  it('compresses inner cards at high cram factor', () => {
    const inner = stretchFactorAmount(0, 10, 2.0);
    const outer = stretchFactorAmount(9, 10, 2.0);
    expect(inner).toBeLessThan(outer);
  });

  it('rightmost card gets full width', () => {
    const last = stretchFactorAmount(9, 10, 2.0);
    expect(last).toBeGreaterThanOrEqual(1.0);
  });
});

describe('instsNeedABigGap', () => {
  it('returns true when left is bought and right is not', () => {
    expect(instsNeedABigGap(true, false, true, 'action')).toBe(true);
  });

  it('returns false during defense phase', () => {
    expect(instsNeedABigGap(true, false, true, 'defense')).toBe(false);
  });

  it('returns false when both bought', () => {
    expect(instsNeedABigGap(true, true, true, 'action')).toBe(false);
  });

  it('returns false when not active player', () => {
    expect(instsNeedABigGap(true, false, false, 'action')).toBe(false);
  });
});

describe('performCramming', () => {
  it('returns positions for simple row (3 piles)', () => {
    const piles = [
      { width: 83, cardCount: 1 },
      { width: 83, cardCount: 1 },
      { width: 83, cardCount: 1 },
    ];
    const result = performCramming(piles, 600, 0, 0);
    expect(result.length).toBe(3);
    expect(result[0].x).toBeGreaterThanOrEqual(0);
    expect(result[2].x).toBeLessThanOrEqual(600);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement layout-engine.ts**

Port three functions from AS3:

1. `stretchFactorAmount()` — UIPile.as lines 998-1034. Three ranges (cramFactor < 1, 1-1.5, >= 1.5), special handling for piles > 28 cards, progressive gradient for last 10 cards.

2. `instsNeedABigGap()` — UIPile.as lines 1036-1039. Checks bought status, active player, and phase.

3. `performCramming()` — UIRow.as lines 121-265. The full cramming algorithm with exponential transition, margin constraints, and per-pile positioning.

All three must be **faithful ports** from the AS3 source. Do not approximate.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add src/components/game-renderer/layout-engine.ts src/components/game-renderer/__tests__/layout-engine.test.ts
git commit -m "feat: layout engine with TDD (port of UIRow.performCramming + UIPile.stretchFactorAmount)"
```

---

## Task 8: Ladder — Asset loader

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/asset-loader.ts`

- [ ] **Step 1: Implement asset-loader.ts**

Responsible for:
1. Loading small sprite textures (backgrounds, covers, shading, status icons) from the engine bundle's base64 data
2. Loading card art PNGs from `/images/units/` with lazy loading and caching
3. Providing magenta placeholder textures for missing assets

```typescript
// asset-loader.ts
import { Assets, Texture, Graphics } from 'pixi.js';

// Texture key constants matching the engine bundle's asset keys
export const TEXTURE_KEYS = {
  // Card backgrounds (10)
  BG_DEAD: 'bg_dead',
  BG_BLOCK: 'bg_block',
  BG_BUSY: 'bg_busy',
  BG_ABSORB: 'bg_absorb',
  BG_CHILLED: 'bg_chilled',
  BG_BOUGHT: 'bg_bought',
  BG_WHITEPINK: 'bg_whitepink',
  BG_BLOCKRED: 'bg_blockred',
  BG_BUSYBLUE: 'bg_busyblue',
  BG_BUSYRED: 'bg_busyred',
  // ... covers, shading, status, resource icons
} as const;

/** Load all small assets from the engine bundle's embedded base64 data */
export async function loadBundleAssets(bundleAssets: Record<string, string>): Promise<void> {
  // bundleAssets is the object from window.PrismataViewer assets
  // Each value is a data:image/png;base64,... URL
  for (const [key, dataUrl] of Object.entries(bundleAssets)) {
    if (!Assets.cache.has(key)) {
      await Assets.load({ alias: key, src: dataUrl });
    }
  }
}

/** Load card art for a specific unit (lazy, cached) */
export async function loadCardArt(cardName: string): Promise<Texture> {
  const key = `card_art_${cardName}`;
  if (Assets.cache.has(key)) return Assets.get(key);
  const url = `/images/units/${encodeURIComponent(cardName)}_Regular_infoHD.png`;
  try {
    return await Assets.load({ alias: key, src: url });
  } catch {
    return getPlaceholderTexture();
  }
}

/** Magenta placeholder for missing assets */
let _placeholder: Texture | null = null;
export function getPlaceholderTexture(): Texture {
  if (!_placeholder) {
    const g = new Graphics().rect(0, 0, 82, 82).fill(0xFF00FF);
    // Generate texture from graphics
    // ... PixiJS 8 API for this
  }
  return _placeholder!;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/game-renderer/asset-loader.ts
git commit -m "feat: asset loader with lazy card art loading and magenta placeholders"
```

---

## Task 9: Ladder — UnitCard + StatusOverlay

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/UnitCard.ts`
- Create: `<ladder>-site/src/components/game-renderer/StatusOverlay.ts`
- Reference: `UIInst.as:416-434` (createUIComponents)
- Reference: `UIStatus.as:124-207` (changed)

- [ ] **Step 1: Implement StatusOverlay**

Port UIStatus.changed() (UIStatus.as lines 124-207). Creates/updates status icon sprites based on card state.

```typescript
// StatusOverlay.ts
import { Container, Sprite, Texture } from 'pixi.js';
import * as K from './constants';

export class StatusOverlay extends Container {
  private fixedContainer: Container;
  private variableContainer: Container;

  constructor() {
    super();
    this.position.set(2, 17); // UIInst.as line 245
    this.fixedContainer = new Container();
    this.variableContainer = new Container();
    this.addChild(this.fixedContainer, this.variableContainer);
  }

  /** Port of UIStatus.changed() — UIStatus.as lines 124-207 */
  update(inst: CardInstance, cardMeta: CardMeta): void {
    // Clear and rebuild status icons based on inst state
    // ... faithful port from AS3
  }
}
```

- [ ] **Step 2: Implement UnitCard**

The 10-layer card, port of UIInst.createUIComponents (lines 416-434).

```typescript
// UnitCard.ts
import { Container, Sprite, Graphics } from 'pixi.js';
import { StatusOverlay } from './StatusOverlay';
import { computeVisualState } from './visual-state';
import { loadCardArt } from './asset-loader';
import type { CardInstance, CardMeta, VisualState } from './types';

export class UnitCard extends Container {
  // Layers (indices match AS3 UIInst.createUIComponents addChild order)
  private backMC: Sprite;           // 0
  private cardSkin: Sprite;         // 1
  private coverMC: Sprite;          // 2
  private shadingMC: Sprite;        // 3
  private borderMC: Sprite;         // 4
  private statusContainer: StatusOverlay; // 5
  private nameImage: Sprite;        // 6
  private topWhiteQuad: Graphics;   // 7
  private effectContainer: Container; // 8
  private damageCounter: Container;  // 9 — direct child, NOT in effectContainer

  private _instId: number = -1;

  constructor() {
    super();
    // Create all 10 layers in correct order
    // ... matching UIInst.as lines 416-434
  }

  get instId(): number { return this._instId; }

  /** Update card visuals from game state */
  update(inst: CardInstance, cardMeta: CardMeta, phase: string, colorOnBottom: number): void {
    this._instId = inst.instId;
    const vs = computeVisualState(inst, phase, colorOnBottom);
    this.applyVisualState(vs, inst, cardMeta);
  }

  private applyVisualState(vs: VisualState, inst: CardInstance, cardMeta: CardMeta): void {
    // Set backMC texture based on vs.backFrame
    // Set coverMC texture based on vs.coverFrame
    // Set shadingMC texture based on vs.shadingFrame
    // Set alpha based on vs.cardAlpha
    // Show/hide skull, snowflake, damage counter
    // Update status icons
    // Load card art if not loaded
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/game-renderer/UnitCard.ts src/components/game-renderer/StatusOverlay.ts
git commit -m "feat: UnitCard (10-layer) and StatusOverlay (port of UIInst + UIStatus)"
```

---

## Task 10: Ladder — PileView + RowView

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/PileView.ts`
- Create: `<ladder>-site/src/components/game-renderer/RowView.ts`
- Reference: `UIPile.as` (stacking, stretchFactorAmount)
- Reference: `UIRow.as` (performCramming, margins, barriers)

- [ ] **Step 1: Implement PileView**

Horizontal stack of same-type UnitCards. Uses stretchFactorAmount from layout-engine.ts.

```typescript
// PileView.ts
import { Container } from 'pixi.js';
import { UnitCard } from './UnitCard';
import { stretchFactorAmount } from './layout-engine';
import * as K from './constants';

export class PileView extends Container {
  private cards: UnitCard[] = [];
  cardName: string = '';
  boardPosition: number = 0; // board position constant (NOT PixiJS .position)

  /** Update with new card instances, returns used width */
  update(instances: CardInstance[], cardMeta: CardMeta, phase: string,
         colorOnBottom: number, cramFactor: number): number {
    // Sync UnitCard pool to match instances
    // Position cards horizontally using stretchFactorAmount
    // Return total pile width
  }
}
```

- [ ] **Step 2: Implement RowView**

Horizontal lane containing piles. Uses performCramming from layout-engine.ts.

```typescript
// RowView.ts
import { Container } from 'pixi.js';
import { PileView } from './PileView';
import { performCramming } from './layout-engine';

export class RowView extends Container {
  private piles: Map<string, PileView> = new Map();
  private rowWidth: number;
  private leftBarrier: number;
  private rightBarrier: number;

  constructor(rowWidth: number, leftBarrier: number = 0, rightBarrier: number = 0) {
    super();
    this.rowWidth = rowWidth;
    this.leftBarrier = leftBarrier;
    this.rightBarrier = rightBarrier;
  }

  /** Update with grouped instances, sorted by position */
  update(groupedInstances: Map<string, CardInstance[]>, cardMetaMap: CardMetaMap,
         phase: string, colorOnBottom: number, turn: number): void {
    // Group instances into piles by cardName
    // Sort piles by position value
    // Run performCramming to get pile x-positions
    // Update each pile
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/game-renderer/PileView.ts src/components/game-renderer/RowView.ts
git commit -m "feat: PileView and RowView (port of UIPile stacking + UIRow cramming)"
```

---

## Task 11: Ladder — BoardView

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/BoardView.ts`
- Reference: `UIBoard.as:143-209` (row creation, positioning)

- [ ] **Step 1: Implement BoardView**

Per-player board with 3 rows. Port of UIBoard.

```typescript
// BoardView.ts
import { Container } from 'pixi.js';
import { RowView } from './RowView';
import { getRow } from './position-calculator';
import * as K from './constants';

export class BoardView extends Container {
  private rows: RowView[] = [];  // [front, middle, back]
  private isTop: boolean;        // top player (rows go upward)

  constructor(fieldWidth: number, isTop: boolean, isReplay: boolean = true) {
    super();
    this.isTop = isTop;

    const gutter = isReplay ? K.MID_LINE_GUTTER_REPLAY : K.MID_LINE_GUTTER_NORMAL;
    const gap = isReplay ? K.ROW_GAP_REPLAY : K.ROW_GAP_NORMAL;
    const swordWidth = 40; // TODO: derive from texture

    // Create 3 rows with correct Y positions (UIBoard.as lines 183-188)
    // Front row has sword barriers, middle and back don't
    // Y offsets differ for top vs bottom player
    // ...
  }

  /** Update all rows from game state for this player */
  update(instances: CardInstance[], cardMetaMap: CardMetaMap,
         phase: string, colorOnBottom: number, turn: number): void {
    // Split instances into 3 rows by getRow(cardMeta.position)
    // Update each row
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/game-renderer/BoardView.ts
git commit -m "feat: BoardView with 3 rows per player (port of UIBoard)"
```

---

## Task 12: Ladder — BuyPanel + BuyCard + ResourceBar

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/BuyCard.ts`
- Create: `<ladder>-site/src/components/game-renderer/BuyPanel.ts`
- Create: `<ladder>-site/src/components/game-renderer/ResourceBar.ts`

- [ ] **Step 1: Implement BuyCard**

Individual purchasable card: art + cost + supply indicator.

- [ ] **Step 2: Implement BuyPanel**

Two columns (base + randomizer), always both visible. Iterates over `GameState.cards[]`, creates BuyCards, positions in columns.

- [ ] **Step 3: Implement ResourceBar**

Gold/B/G/C/H + attack/defense per player. Parses mana string, renders icon + number pairs.

- [ ] **Step 4: Commit**

```bash
git add src/components/game-renderer/BuyCard.ts src/components/game-renderer/BuyPanel.ts src/components/game-renderer/ResourceBar.ts
git commit -m "feat: BuyPanel, BuyCard, ResourceBar (buy panel + resources in canvas)"
```

---

## Task 13: Ladder — BoardRenderer (top-level orchestrator)

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/BoardRenderer.ts`

- [ ] **Step 1: Implement BoardRenderer**

Top-level PixiJS Application. Owns the canvas, creates all child components, dispatches state updates.

```typescript
// BoardRenderer.ts
import { Application, Container } from 'pixi.js';
import { BoardView } from './BoardView';
import { BuyPanel } from './BuyPanel';
import { ResourceBar } from './ResourceBar';
import { loadBundleAssets } from './asset-loader';
import type { GameState, CardMetaMap } from './types';

export class BoardRenderer {
  private app: Application;
  private topBoard: BoardView;     // P1 (opponent)
  private bottomBoard: BoardView;  // P0 (player)
  private buyPanel: BuyPanel;
  private topResources: ResourceBar;
  private bottomResources: ResourceBar;

  constructor() {
    this.app = new Application();
  }

  /** Initialize PixiJS and create all child components */
  async init(canvas: HTMLCanvasElement, bundleAssets: Record<string, string>): Promise<void> {
    await this.app.init({
      canvas,
      width: 900,  // TODO: derive from layout constants
      height: 600,
      background: 0x0a1628,
      antialias: true,
    });

    await loadBundleAssets(bundleAssets);

    // Create child components and add to stage
    // Position according to screen composition from spec
  }

  /** Update all visuals from game state */
  updateState(gameState: GameState, cardMetaMap: CardMetaMap): void {
    const { table, phase, turn } = gameState;
    const p0Units = table.filter(u => u.owner === 0);
    const p1Units = table.filter(u => u.owner === 1);

    this.bottomBoard.update(p0Units, cardMetaMap, phase, 0, turn);
    this.topBoard.update(p1Units, cardMetaMap, phase, 0, turn);
    this.buyPanel.update(gameState, cardMetaMap);
    this.bottomResources.update(gameState.whiteMana, /* attack/defense */ );
    this.topResources.update(gameState.blackMana, /* attack/defense */ );
  }

  /** Clean up PixiJS resources */
  destroy(): void {
    this.app.destroy(true);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/game-renderer/BoardRenderer.ts
git commit -m "feat: BoardRenderer top-level orchestrator"
```

---

## Task 14: Ladder — React wrapper + page.tsx integration

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/PrismataBoard.tsx`
- Modify: `<ladder>-site/src/app/live/[gameId]/page.tsx`

- [ ] **Step 1: Implement PrismataBoard React wrapper**

```tsx
// PrismataBoard.tsx
'use client';
import { useRef, useEffect } from 'react';
import { BoardRenderer } from './BoardRenderer';
import type { GameState, CardMetaMap } from './types';

interface Props {
  gameState: GameState | null;
  cardMeta: CardMetaMap | null;
  bundleAssets: Record<string, string> | null;
}

export function PrismataBoard({ gameState, cardMeta, bundleAssets }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<BoardRenderer | null>(null);

  // Initialize PixiJS on mount
  useEffect(() => {
    if (!canvasRef.current || !bundleAssets) return;
    const renderer = new BoardRenderer();
    rendererRef.current = renderer;
    renderer.init(canvasRef.current, bundleAssets);
    return () => renderer.destroy();
  }, [bundleAssets]);

  // Update on state change
  useEffect(() => {
    if (rendererRef.current && gameState && cardMeta) {
      rendererRef.current.updateState(gameState, cardMeta);
    }
  }, [gameState, cardMeta]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: 'auto' }} />;
}
```

- [ ] **Step 2: Integrate into page.tsx**

In `src/app/live/[gameId]/page.tsx`, replace the HTML board rendering section with:

```tsx
import { PrismataBoard } from '@/components/game-renderer';

// In the component JSX, replace the board div with:
<PrismataBoard
  gameState={gameState}
  cardMeta={cardMeta}
  bundleAssets={bundleAssets}
/>
```

Keep all existing React chrome (player info, playback controls, phase indicator).

- [ ] **Step 3: Test in browser**

```bash
cd <LADDER_REPO_PATH>/<ladder>-site
npm run dev
```

Open http://localhost:3000/live/test — verify the PixiJS canvas renders.

- [ ] **Step 4: Commit**

```bash
git add src/components/game-renderer/PrismataBoard.tsx src/app/live/\\[gameId\\]/page.tsx
git commit -m "feat: PrismataBoard React wrapper + page.tsx integration"
```

---

## Task 15: Testing — Replay batch smoke tests

**Repo:** PrismataAI
**Files:**
- Create: `js_engine/viewer_smoke_test.js`

- [ ] **Step 1: Create smoke test runner**

Extends the `replay_validator.js` pattern. Loads replays, steps through every state, and validates the state export for renderer compatibility.

```javascript
// viewer_smoke_test.js
// Usage: node js_engine/viewer_smoke_test.js --count 50

// For each replay:
// 1. Load and replay all clicks
// 2. At each state, call stateToCppJSON
// 3. Verify: all table entries have instId, damage, deadness fields
// 4. Verify: no NaN in numeric fields
// 5. Verify: phase is one of 'defense', 'action', 'confirm'
// 6. Verify: supply arrays match cards array length
// 7. Count dead units included
// 8. Report: replays tested, states checked, errors found
```

- [ ] **Step 2: Run against test replays**

```bash
cd c:/libraries/PrismataAI
node js_engine/viewer_smoke_test.js --count 50
```

Expected: All replays pass with new fields present.

- [ ] **Step 3: Commit**

```bash
git add js_engine/viewer_smoke_test.js
git commit -m "test: replay batch smoke test for viewer state export"
```

---

## Task 16: Testing — Layout snapshot tests

**Repo:** <ladder>
**Files:**
- Create: `<ladder>-site/src/components/game-renderer/__tests__/layout-snapshots.test.ts`

- [ ] **Step 1: Create snapshot tests**

Use golden JSON files for known game states. Compare computed layout positions against snapshots.

```typescript
// __tests__/layout-snapshots.test.ts
import { describe, it, expect } from 'vitest';
import { performCramming } from '../layout-engine';

// Golden test: 5 piles in a 600px row
const FIVE_PILES = [
  { width: 83, cardCount: 3 },
  { width: 83, cardCount: 1 },
  { width: 83, cardCount: 5 },
  { width: 83, cardCount: 1 },
  { width: 83, cardCount: 2 },
];

describe('layout snapshots', () => {
  it('5 piles in 600px row matches golden positions', () => {
    const result = performCramming(FIVE_PILES, 600, 0, 0);
    expect(result).toMatchSnapshot();
  });

  it('cramming activates with 8+ piles in 400px row', () => {
    const manyPiles = Array(8).fill({ width: 83, cardCount: 2 });
    const result = performCramming(manyPiles, 400, 0, 0);
    // Verify cramming reduced margins
    const totalWidth = result[result.length - 1].x + 83 - result[0].x;
    expect(totalWidth).toBeLessThanOrEqual(400);
  });
});
```

- [ ] **Step 2: Generate initial snapshots**

```bash
npx vitest run --update src/components/game-renderer/__tests__/layout-snapshots.test.ts
```

- [ ] **Step 3: Commit**

```bash
git add src/components/game-renderer/__tests__/layout-snapshots.test.ts
git commit -m "test: layout snapshot tests for cramming algorithm"
```

---

## Execution Order Summary

| # | Task | Repo | Dependency |
|---|---|---|---|
| 1 | Engine state export fields | PrismataAI | — |
| 2 | Engine position + asset fixes | PrismataAI | — |
| 3 | Rebuild bundle | PrismataAI | 1, 2 |
| 4 | Project setup (PixiJS, constants, types) | <ladder> | — |
| 5 | Position calculator (TDD) | <ladder> | 4 |
| 6 | Visual state mapper (TDD) | <ladder> | 4 |
| 7 | Layout engine (TDD) | <ladder> | 4 |
| 8 | Asset loader | <ladder> | 4 |
| 9 | UnitCard + StatusOverlay | <ladder> | 5, 6, 8 |
| 10 | PileView + RowView | <ladder> | 7, 9 |
| 11 | BoardView | <ladder> | 10 |
| 12 | BuyPanel + BuyCard + ResourceBar | <ladder> | 8 |
| 13 | BoardRenderer | <ladder> | 11, 12 |
| 14 | React wrapper + page.tsx | <ladder> | 3, 13 |
| 15 | Replay smoke tests | PrismataAI | 1, 2 |
| 16 | Layout snapshot tests | <ladder> | 7 |

**Parallelism:** Tasks 1-2 can run in parallel with Tasks 4-8. Tasks 5, 6, 7 are independent of each other. Tasks 15-16 can run after their dependencies without blocking the main chain.
