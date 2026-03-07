# HTML Replay Viewer — Implementation Plan

**Design:** `docs/plans/2026-03-07-html-replay-viewer-design.md`
**Branch:** gui-integration

## Prerequisites

- A test replay JSON file (generate by running matchup runner with `--save-replays`)
- Card art PNGs in `bin/asset/images/cards/`
- Status/resource icon PNGs in `bin/asset/images/icons/`
- Card background PNGs in `bin/asset/images/cardbg/`

## Task 1: Generate a test replay

Run matchup runner to produce a replay JSON to develop against.

1. Run: `node js_engine/matchup_clean.js --games 1 --save-replays js_engine/test_replays/`
2. Verify a `.json` file is created in `js_engine/test_replays/`
3. Inspect the JSON to confirm it has `states`, `actions`, `turnBoundaries`, `cardSet`

**Verify:** Replay JSON exists and contains expected fields.

## Task 2: Build card metadata lookup

The replay JSON's per-card data doesn't include `hasAbility`, `isFrontline`, `canBlock` — needed for lane assignment. Extract a minimal lookup from `cardLibrary.jso`.

1. Create `js_engine/card_metadata.js` — a script that reads `cardLibrary.jso` and exports a map: `{ "Drone": { hasAbility, isFrontline, canBlock, isFragile, attack, defaultBlocking, ... }, ... }`
2. Or: build this lookup inline in `replay_to_html.js` at generation time, embedding only the units in the game
3. The Card.js already parses all properties — reuse its logic

**Verify:** Can look up lane assignment for any card name.

## Task 3: Create replay_to_html.js scaffold

The generator script that reads a replay JSON, embeds assets, and produces a self-contained HTML file.

1. Create `js_engine/replay_to_html.js`
2. Accept CLI arg: `node js_engine/replay_to_html.js <replay.json> [output.html]`
3. Read the replay JSON
4. Scan card names used across all states to determine which card art to embed
5. Read and base64-encode required PNGs:
   - Card art: `bin/asset/images/cards/{name}.png` for each unique unit
   - Card backgrounds: `Card_Blue.png`, `Card_Grey.png`, `Card_Orange.png`, `Card_Dead.png`, `Card_Border_Green.png`
   - Status icons from `bin/asset/images/icons/status/`
   - Resource icons from `bin/asset/images/icons/resource/`
6. Build HTML string with:
   - `<canvas>` element
   - Embedded base64 images as JS image objects
   - Embedded replay data as `const REPLAY_DATA = {...};`
   - Embedded card metadata for lane assignment
   - Embedded renderer JS (inline `<script>`)
7. Write to output file (default: same name as input but `.html`)

**Verify:** Run `node js_engine/replay_to_html.js js_engine/test_replays/game_001.json` and confirm HTML file is created with embedded data.

## Task 4: Canvas renderer — minimal card drawing

Get cards drawing on screen with art and names. No layout logic yet — just prove rendering works.

1. In the embedded renderer JS:
   - On page load, decode base64 images into `Image` objects
   - Set up canvas sized to window
   - Implement `drawCard(ctx, cardData, x, y, cardSize)`:
     - Draw card background rectangle (colored by status)
     - Draw card art image
     - Draw card name text (truncated to ~10 chars)
   - Render state 0's cards in a simple grid (temporary layout)

**Verify:** Open HTML in browser, see cards with art and names drawn on canvas.

## Task 5: Canvas renderer — board layout with lanes

Implement the real layout matching `setCardPositions()` from GUIState_Play.cpp.

1. Implement `getLane(cardName, cardMeta)` — returns 0/1/2 using design rules:
   - Lane 0: isFrontline OR (canBlock AND NOT hasAbility)
   - Lane 1: hasAbility OR hasTargetAbility
   - Lane 2: everything else
2. Implement `layoutCards(state, canvasWidth, canvasHeight)`:
   - Buy pane occupies left 200px
   - Play area = remaining width
   - Split vertically: P1 top half, P0 bottom half
   - Per player, 3 lanes spaced evenly
   - P1: lane 0 nearest center (bottom of P1 area), lane 2 at top
   - P0: lane 0 nearest center (top of P0 area), lane 2 at bottom
   - Cards sorted by type within lanes
   - Same-type cards overlap horizontally (show ~20% per duplicate)
   - Each lane horizontally centered in play area
3. Dark background (match GUI aesthetic)

**Verify:** Open HTML, see cards in correct lanes for both players, overlapping correctly.

## Task 6: Canvas renderer — card status overlays

Add the status information that makes cards useful to read.

1. Add to `drawCard()`:
   - Background texture selection: default (blue), assigned (grey), construction (orange-faded), dead (dark)
   - Attack value with icon (bottom-left)
   - HP/defense value with icon (bottom-right)
   - Construction time number (top-left, with construction overlay)
   - Shield icon: blue (blocker ready), gold (sellable ready), white (blocker exhausted)
   - Status stack (vertically): charge count, lifespan, delay, chill, frontline marker
   - Green border for cards belonging to active player (subtle, replay context)

**Verify:** Cards show attack/HP, construction timers, shield status, chill indicators.

## Task 7: Buy pane sidebar

1. Implement `drawBuyPane(ctx, state, cardMeta)`:
   - Left 200px column, dark background
   - One row (200x60) per buyable unit
   - Each row: unit name, cost icons, card portrait (60x60), supply bar (green/red pips), owned count per player
   - Skip or include base set units (include all — match the always-open sidebar from Steam)
2. Need card cost info — embed from cardLibrary.jso (buyCost per unit)

**Verify:** Sidebar shows all game units with costs, supply, and ownership counts.

## Task 8: HUD and info display

1. Top bar (yellow text on dark): `"P0 vs P1 | Turn X/Y | [action/total] | action_label | Winner: name"`
2. Top-right (grey): `"Step N/total"`
3. Bottom-left (grey): Keyboard control hints
4. Bottom resource bar: Resource orb icons with current values per active player

**Verify:** HUD shows correct turn/action info, updates when navigating.

## Task 9: Attack/defense indicators

1. At center divider, draw:
   - Left side: P1 attack (sword icon + number) above divider, P0 defense (shield icon + number) below
   - Right side: P1 defense (shield icon + number) above divider, P0 attack (sword icon + number) below
2. Compute from state: sum attack of each player's ready attackers, sum HP of available blockers

**Verify:** Attack/defense numbers update correctly as game progresses.

## Task 10: Keyboard navigation

1. Add keydown listener:
   - Right/Space: advance to next state
   - Left/Z: go back one state
   - Up/Ctrl+Right: jump to next turn boundary
   - Down/Ctrl+Left: jump to previous turn boundary
   - Home: jump to state 0
   - End: jump to last state
2. On state change, re-render entire canvas
3. Use `turnBoundaries` array from replay data for turn jumps

**Verify:** All keyboard controls work. Turn jumps land on correct boundaries.

## Task 11: Responsive canvas and polish

1. Canvas resizes on window resize, maintaining aspect ratio
2. Prevent default on arrow keys (no page scrolling)
3. Test in Chrome, Firefox, Edge
4. Test file size — should be 1-3MB for a typical game

**Verify:** HTML file works when opened from Discord download. File size under 5MB.

## Task 12: End-to-end test

1. Run a full matchup game: `node js_engine/matchup_clean.js --games 1 --save-replays js_engine/test_replays/`
2. Generate HTML: `node js_engine/replay_to_html.js js_engine/test_replays/game_001.json`
3. Open in browser, navigate through full game
4. Verify: layout matches GUI screenshots, all cards render correctly, navigation is smooth

**Verify:** Complete game viewable in browser with correct layout and navigation.
