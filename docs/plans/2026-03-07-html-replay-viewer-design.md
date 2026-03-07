# HTML Replay Viewer — Design Document

**Date:** 2026-03-07
**Branch:** gui-integration
**Status:** Approved for implementation

## Goal

Share AI game replays with Prismata experts on Discord without requiring them to install the GUI. A single self-contained HTML file that opens in any browser with arrow-key navigation through game states.

## Approach

**Self-contained HTML file.** One `.html` file per game containing:
- All card art and UI textures as base64-embedded images (only units used in that game)
- Game state data as embedded JSON (from existing replay format)
- Canvas renderer replicating the C++ GUI layout
- Keyboard navigation handler

**Generation pipeline:**
```
matchup_clean.js --save-replays dir/
        |
  replay_0001.json  (existing format, per-action state snapshots)
        |
  node js_engine/replay_to_html.js replay_0001.json
        |
  game_0001.html  (~1-3MB, drag into Discord)
```

No changes needed to the replay JSON format or matchup runner. The HTML generator reads existing replay files and bundles them with assets.

## Board Layout

Replicates the C++ GUI layout (`GUIState_Play.cpp`, `GUICard.cpp`).

```
+--------------------------------------------------------------------+
| HUD: "P0 vs P1 | Turn 12/38 | [11/12] End_Phase | Winner: MCDSAI" |
+------------+-------------------------------------------------------+
|            |  P1 Resources: 1G 0B 0R 0E                            |
| Buy Pane   |  P1 Lane 2: [non-blocking, non-ability units]         |
|            |  P1 Lane 1: [ability units - Drones, Tarsiers, etc]   |
| Unit Name  |  P1 Lane 0: [frontline + blockers - Engis, Walls]     |
|  cost icons|            P1 Atk [sword]  |  P1 Def [shield]         |
|  supply bar|  ----------------center-divider-------------------    |
|  card thumb|            P0 Def [shield] |  P0 Atk [sword]         |
|  count     |  P0 Lane 0: [frontline + blockers]                    |
|            |  P0 Lane 1: [ability units]                           |
|            |  P0 Lane 2: [non-blocking, non-ability units]         |
|            |  P0 Resources                                         |
+------------+-------------------------------------------------------+
| Controls: <- -> Action | up/down Turn | Step 93/524                |
+--------------------------------------------------------------------+
```

### Three lanes per player

Determined by card type (from `GUICard::getLane()`):

| Lane | Assignment Rule | Examples |
|------|----------------|----------|
| 0 (nearest center) | `isFrontline` OR (`canBlock` AND NOT `hasAbility`) | Engineer, Wall, Forcefield |
| 1 (middle) | `hasAbility` OR `hasTargetAbility` | Drone, Tarsier, Rhino, tech buildings |
| 2 (furthest) | Everything else (no block, no ability) | Rarely populated |

Lanes mirror vertically: P1 lanes go upward from center, P0 lanes go downward.
Each lane is horizontally centered in the play area.

### Card overlap

Identical card types overlap horizontally showing ~20% of each duplicate (a sliver of the left edge), with the rightmost card fully visible. Matches the C++ GUI's `sameBuffer` of `-4*CardSize.x/5`. Drones overlap slightly more tightly.

### Attack/Defense indicators at center

```
         P1 Attack [sword]   |   P1 Defense [shield]
         -------center-divider---------
         P0 Defense [shield]  |   P0 Attack [sword]
```

Attack faces the opponent's defense across the midline.

### Buy pane sidebar (left, 200px)

Always visible. Each buyable unit shown as a row (200x60) containing:
- Unit name
- Cost icons (gold/blue/green/red/energy)
- Card portrait thumbnail (60x60, right side)
- Supply bar: green pips (P0 remaining) / red pips (P1 remaining)
- Count owned by each player
- Green border highlight if purchasable by active player

### Card tile rendering

Each card tile shows (from `GUICard::draw()`):
- Background texture based on status (default/assigned/construction/dead)
- Card art portrait
- Card name (truncated to ~10 chars)
- Attack value (bottom-left, with attack icon)
- HP/defense value (bottom-right, with defense icon)
- Status icons stacked vertically: construction time, shield type (blue/gold/white), charge count, lifespan, delay, chill, frontline marker

### Resources

Parsed from mana string (digits=gold, G=green, B=blue, C=red, H=energy). Displayed as colored number badges near each player area, matching the GUI's top-bar resource display.

## Keyboard Navigation

| Key | Action |
|-----|--------|
| Right / Space | Next action (step forward one state) |
| Left / Z | Previous action (step back one state) |
| Up / Ctrl+Right | Jump to next turn boundary |
| Down / Ctrl+Left | Jump to previous turn boundary |
| Home | Jump to start |
| End | Jump to end |

Uses existing `turnBoundaries` array from replay JSON for turn-jump navigation.

## HUD Display

Matches `GUIState_Play::drawReplayHUD()`:

- **Top bar (yellow text):** `"P0 vs P1 | Turn X/Y | [action/total] | action_label | Winner: name"`
- **Top-right (grey):** `"Step N/total"`
- **Bottom-left (grey):** Keyboard control hints
- **Action labels:** Already generated by `describeClick()` in matchup_clean.js — "Buy Tarsier", "Use Drone", "Block with Wall", "End Phase", etc.

## Embedded Assets

Per game, the HTML file embeds only what's needed:

- **Card art:** ~8 random units + ~5 base set units used = ~13-18 PNGs from `bin/asset/images/cards/`
- **Card backgrounds:** ~5 textures from `bin/asset/images/cardbg/` (default, assigned, construction, dead, border)
- **Status icons:** ~8 small PNGs (attack, defense, shield variants, charge, doom, delay, chill, frontline)
- **Resource icons:** ~6 small PNGs (gold, blue, green, red, energy, attack orbs)

Estimated total: 500KB-1.5MB base64. Well under Discord's 25MB file limit.

## Rendering

HTML5 Canvas, redrawn on each state change. Single `<canvas>` element that scales to fit browser window width while maintaining aspect ratio. Dark background matching the GUI aesthetic.

## File Structure

```
js_engine/
  replay_to_html.js        -- Generator script (new)
  replay_viewer_template.js -- Canvas renderer + keyboard handler (new, embedded into HTML)
  replay_exporter.js        -- Existing, no changes
  matchup_clean.js          -- Existing, no changes
```

## Future Extensions (not in scope)

- `--save-html` flag on matchup_clean.js to generate HTML directly after each game
- Hosted version on GitHub Pages (share URL instead of file)
- Mouseover card tooltips showing full unit stats
- Support for replays from Prismata API (human games)
