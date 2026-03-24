# Prismata Viewer Visual Fidelity — Planning Prompt

> Give this to Claude to create a detailed implementation plan for improving the PixiJS viewer to match the SWF client.

## Context

We have a working PixiJS-based Prismata game viewer that renders both replays (`/replay/[code]`) and live games (`/live/[gameId]`). The viewer uses a shared component library (`src/components/game-viewer/` for React, `src/components/game-renderer/` for PixiJS canvas). It correctly renders game state but lacks the visual polish of the original Flash (SWF) client.

**Goal:** Incrementally bring the PixiJS renderer to visual parity with the SWF client, prioritizing changes that most improve the viewing experience.

## What We Have

### Codebase
- **PixiJS renderer**: `<ladder>-site/src/components/game-renderer/` — BoardRenderer, BoardView, UnitCard (10-layer), PileView, RowView, BuyPanel, ResourceBar, StatusOverlay, asset-loader
- **React shared components**: `<ladder>-site/src/components/game-viewer/` — BuyRow, UnitCard, CardLane, ResourceDisplay, PlayerStats
- **JS engine**: `js_engine/` — full AS3→JS transpiled engine (Analyzer, Controller, GameState, Card, Click, etc.)
- **Card library**: `bin/asset/config/cardLibrary.jso` — all 105+11 units with full metadata
- **Engine bundle builder**: `js_engine/build_viewer_bundle.js` — builds card metadata, embeds assets

### Reference Material
- **Decompiled SWF source**: Available for reference (AS3 ActionScript). Key UI classes:
  - `UIInst` — unit card rendering (10 layers: background, art, overlays, numbers, status icons)
  - `UIBoard` — board layout (3 rows per player: front/middle/back)
  - `UIPile` — card stacking within rows
  - `UIRow` — row cramming algorithm
  - `UIBuyColumn` — buy panel sidebar
  - `UIStatus` — status overlay (construction timer, lifespan, delay, chill, charge)
  - `UIAnimQueue` — animation sequencing
  - `UIResourceBar` — resource display at bottom of each player area
- **Card art**: `/public/images/units/` — HD card art for all units
- **Background textures**: 10 board backgrounds embedded in engine bundle
- **Icon assets**: Resource icons (gold, blue, green, red, energy), shield icons, status icons

### Testing Infrastructure
- **~100k replays** in `c:\libraries\prismata-replay-parser\replays_archive/` (balance-validated, 1500+ rated)
- **Replay fetch**: `node fetch_expert_replays.js` (from S3)
- **JS engine replay**: Can replay any game click-by-click via `Analyzer`
- **Cross-validation**: `replay_parser/` Python parser with known accuracy limits
- **Bulk extraction**: `js_engine/bulk_extract.js` — extracts training data from replays, useful for finding specific game scenarios

### Wonderboat's Feedback (from Discord, Mar 22 2026)
Specific visual issues identified:
1. Unit icons smaller and bottom-right aligned (should be centered?)
2. Fatter font on numbers
3. Sword facing wrong way on units
4. Fragile HP text goes inside heart on bottom left
5. Left column (status panel) — unit icon art going into it too much
6. Stress test complicated units with multiple effects (e.g., Tia has stamina AND blocker)
7. Drone supply indicator should have 1 less for P2 than P1
8. Non-fragile HP text more to the right (slightly inside plus sign)
9. Same with sword text positioning
10. Black outline/stroke on numbers

## Prioritized Work Streams

### Stream 1: Unit Card Polish (highest visual impact)
Fix the 10-layer UnitCard rendering to match SWF more closely:
- Number font weight and positioning (HP, attack, construction timer)
- Black outline/stroke on all numbers
- Sword icon direction
- Fragile HP inside heart positioning
- Status icon sizing and alignment
- Multiple simultaneous statuses (stamina + blocker, chill + lifespan, etc.)

**Reference**: Compare `src/components/game-renderer/UnitCard.ts` against decompiled `UIInst` class.
**Test approach**: Find replays with complex unit states (use bulk_extract to find games with Tia, Aegis, Centurion, etc.)

### Stream 2: Board HUD (attack/defense/chill in PixiJS)
Move the attack/chill/defense stats from the React header into the PixiJS canvas, matching SWF layout:
- Sword icon with attack number between player areas
- Shield icon with defense number
- Snowflake with chill total
- Red (!) danger indicator when attack > total defense
- Resource bar at bottom of each player's area

**Reference**: SWF renders these in the board area, not in a header bar.

### Stream 3: Animation System
Port the animation queue from SWF:
- Swoosh transition between turns (cards untap, resources refresh)
- Buy animation (card appears in construction)
- Attack animation (sword slash effect)
- Death animation (card fades/shatters)
- Breach effect (red overlay, screen shake)

**Reference**: `UIAnimQueue` in decompiled SWF. Start with swoosh only — it's the most visible.

### Stream 4: Skins & Cosmetics
- Alternate card art (skins are in the SWF assets as variant textures)
- Player avatars (shown in SWF bottom bar)
- Emotes (SWF has ~20 emote images, triggered by `ServerEmote` messages)
- Player frames/badges

### Stream 5: Automated Visual Testing
Build a regression test pipeline:
1. Select 50 diverse replays (different unit sets, game lengths, breach scenarios)
2. Replay through engine to specific turns
3. Render via PixiJS (headless with node-canvas or Playwright screenshot)
4. Compare against baseline screenshots
5. Flag visual regressions on PR

## Recommended Starting Point

Start with **Stream 1** (unit card polish) — it's the highest-impact, most self-contained work. Wonderboat's feedback is mostly about this. Each fix is independently testable and deployable.

Then **Stream 2** (board HUD) — the data is already computed, just needs PixiJS rendering instead of React.

## How to Find Specific Test Cases

```bash
# Find replays with a specific unit (e.g., Tia for stamina+blocker testing)
cd c:/libraries/prismata-replay-parser
node -e "
const fs = require('fs');
const zlib = require('zlib');
const dir = 'replays_archive';
const target = 'Tia';
let found = 0;
for (const f of fs.readdirSync(dir).slice(0, 5000)) {
  if (!f.endsWith('.json.gz')) continue;
  const data = JSON.parse(zlib.gunzipSync(fs.readFileSync(dir + '/' + f)));
  const deck = (data.deckInfo?.mergedDeck || []).map(d => d.UIName || d);
  if (deck.includes(target)) { console.log(f.replace('.json.gz','')); found++; }
  if (found >= 5) break;
}
"
```

## SWF Reference Screenshot Pipeline

The original Prismata client (Adobe AIR/Flash) is available and patched with dev mode. This gives us a pixel-perfect ground truth to compare against. There are several ways to use it:

### Approach A: Manual Baseline Capture (recommended starting point)

The patched SWF has dev mode enabled (byte patch at offset `0x1580196`: `0x27`→`0x26`). This enables:
- **F6 clipboard export** — dumps full game state JSON (`CurrentInfo` with `mergedDeck`, `gameState`, `aiParameters`). Card names are **display names**.
- **Replay viewing** — load any replay code, step through with arrow keys

Workflow:
1. Open Prismata client, load a replay code
2. Step to a specific turn/state
3. Screenshot the client window
4. F6 → paste game state JSON into a file
5. Load the same replay in our PixiJS viewer at the same state
6. Screenshot our viewer
7. Pixel-diff the two (e.g., using `pixelmatch` or ImageMagick `compare`)

This is manual (~1 hour for 50 key states) but gives perfect ground truth with matching state data. The F6 JSON export is the killer feature — it lets us verify both visual AND data accuracy.

### Approach B: Flash Player Debug Projector

Adobe's standalone debug Flash Player can run the SWF outside of AIR:
- Outputs all `trace()` calls to `%APPDATA%\Macromedia\Flash Player\Logs\flashlog.txt`
- Can be paired with a Flash debugger (FlashDevelop/IntelliJ) for breakpoints
- Could potentially be modified to add `trace()` calls that dump rendering state at each frame
- The SWF could be further patched to auto-step through replays and save screenshots

This is more complex to set up but enables semi-automated capture.

### Approach C: Automated PixiJS Screenshot Pipeline (Playwright)

For our side of the comparison, Playwright (available as MCP tool) can automate screenshot capture:

```javascript
// Pseudocode: capture our viewer at specific replay states
const codes = ['CqzRO-eAlbS', 'P1rq4-L+@Ai', ...]; // diverse replays
for (const code of codes) {
  await page.goto(`/replay/${code}`);
  await page.waitForSelector('[data-loaded="true"]');
  // Step to specific turns
  for (const turn of [1, 5, 10, 15, 20]) {
    await page.keyboard.press('ArrowRight'); // step to turn
    await page.screenshot({ path: `baseline/${code}_turn${turn}.png` });
  }
}
```

Combined with Approach A baselines, this enables automated visual regression: every PR runs the Playwright pipeline and diffs against SWF reference screenshots.

### Approach D: Ruffle (Flash Emulator — experimental)

Ruffle is an open-source Rust/WASM Flash emulator. If it can run Prismata's SWF (even partially), it could be automated headlessly for screenshot capture. However, Prismata uses complex AS3 (AMF3 networking, Adobe AIR APIs) so this is unlikely to work without significant Ruffle patches. Worth a quick feasibility test but don't invest heavily.

### Recommended Pipeline

1. **Phase 1**: Manual Approach A — capture 50 reference screenshots from the SWF client at diverse game states (different unit sets, breach scenarios, complex boards). Store in `tests/visual-baselines/`.
2. **Phase 2**: Automated Approach C — Playwright pipeline screenshots our viewer at the same states. Run `pixelmatch` to generate diff images.
3. **Phase 3**: CI integration — visual regression on every PR. Flag any screenshots where diff exceeds threshold.

The F6 JSON export from Phase 1 also feeds directly into unit tests — verify our engine produces the same game state as the SWF at each step.

## Key Files to Read Before Starting

1. `src/components/game-renderer/UnitCard.ts` — current 10-layer card rendering
2. `src/components/game-renderer/BoardView.ts` — board layout (3 rows per player)
3. `src/components/game-renderer/StatusOverlay.ts` — status icons/numbers
4. `src/components/game-renderer/constants.ts` — sizing, colors, layer config
5. `js_engine/build_viewer_bundle.js` — card metadata builder (lines 51-107)
6. Decompiled SWF `UIInst` class — the gold standard for card rendering
