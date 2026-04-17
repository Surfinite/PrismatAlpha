# Godot 3D Battlefield Viewer — Continuation Prompt v2

## Context

Implementing a Godot 4 application that renders Prismata replays as a 3D battlefield. Collaboration with community member "homander" (Discord) who will handle visual design/3D models once the framework is solid.

## Key Files

- **Design spec:** `docs/superpowers/specs/2026-03-26-godot-3d-battlefield-viewer-design.md`
- **Implementation plan (original):** `docs/superpowers/plans/2026-03-26-godot-3d-battlefield-viewer.md`
- **Project memory:** `project_godot_3d_viewer.md` in claude-mem

## What's Done (Session 1 — Mar 26, 2026)

### Godot Viewer (`c:\libraries\prismata-3d\`, master branch, 15 commits)

**All core layers implemented and running:**
- **Provider**: BaseProvider + FileProvider (loads pre-baked JSON snapshots)
- **ReplayController**: Seq navigation, turn index, playback with speed control
- **Battlefield**: Snapshot reconciliation with SWF-faithful layout engine port
- **Camera**: Orbit camera, defaults to top-down, T key toggles 3D view
- **VisualHooks**: Buy flash + kill flash effects (MVP)
- **UI/HUD**: Turn counter, scrubber, playback controls, resource bars, buy panel
- **143 card sprites** extracted from PrismataAI card art
- **Layout engine** ported from AS3 UIPile.as + UIRow.as (cramming algorithm)

**Live replay loading working:**
- `node tools/fetch_and_preprocess.js --latest` fetches from prismata-stats API
- Outputs to `prismata-3d/data/current_replay.json`
- main.gd auto-loads current_replay.json if present

### Preprocessor (`PrismataAI/tools/`, ai-improvements branch)

- `card_id_map.js` — 116 cards, internal→snake_case mapping
- `position_calculator.js` — faithful port of position-calculator.ts
- `snapshot_schema.js` — BoardSnapshot validator
- `replay_to_snapshots.js` — full preprocessor with event detection
- `fetch_and_preprocess.js` — fetches latest from prismata-stats + preprocesses
- `validate_snapshots_batch.js` — Tier 1 batch invariant checker

### Validation Results (1000 replays)

- **State correctness: 97.4%** (974/1000 pass all invariants)
- **Click acceptance: 98.5%** (393,205/399,339 clicks accepted)
- **Zero HP/resource/phase/uniqueness violations** across all 1000 replays
- **25 replays end early** due to click rejection cascade (targeting mode edge cases)
- **Event heuristics need work** (buy/kill detection has false positives — cosmetic, not logical)

### Known Bugs Fixed During Session

1. HUD missed initial snapshot (signal wiring order)
2. RefCounted hook objects garbage collected (stored as member vars)
3. Units stacked on same position (added layout engine)

## What To Do Next

### Priority 1: Systematic Visual Comparison Tool

Build an automated tool to compare unit layout between PixiJS viewer and Godot viewer for the same replay at the same turn. This replaces manual screenshot iteration.

**Approach:**
1. For a given replay + turn, run the PixiJS layout engine (from <ladder>) to get per-unit pixel positions
2. Run the Godot preprocessor + layout engine to get per-unit world positions
3. Convert between coordinate systems (pixel → world-space normalization)
4. Compare: every unit should be in the same relative position within its row and pile
5. Output: per-unit diff report, overall match percentage

**Files involved:**
- `<ladder>-site/src/components/game-renderer/layout-engine.ts` (reference)
- `<ladder>-site/src/components/game-renderer/RowView.ts` (reference)
- `<ladder>-site/src/components/game-renderer/BoardView.ts` (reference)
- `prismata-3d/battlefield/layout_engine.gd` (Godot port)
- `prismata-3d/battlefield/battlefield.gd` (position calculation)
- New: `tools/compare_layouts.js` (comparison tool)

**Note:** The PixiJS viewer is our best reference but NOT ground truth. It's a port of the AS3 decompiled source, not the original. Some differences may be PixiJS bugs, not Godot bugs.

### Priority 2: Top-Down Visual Polish

Fix remaining visual issues to match SWF client in top-down view:
- Sprite rotation correctness (may need tweaking based on how they render)
- Sprite scale matching the layout engine's card width
- Player color tinting (P0=blue side, P1=red side) on the terrain
- Row background shading to distinguish front/middle/back
- Under-construction visual treatment (dimming + construction overlay)

### Priority 3: Event Detection Improvements

The batch validation showed event heuristics have issues:
- `buy_events_have_units` (20/20 fail) — units bought then immediately consumed (spells, sacrifice costs)
- `kill_events_remove_units` (12/20 fail) — events spanning snapshot boundaries

Fix: Track unit creation/destruction more carefully within the click loop, not just by diffing alive sets at snapshot boundaries.

### Priority 4: Additional HUD Features

From spec review:
- Player names (from matchMeta) in the HUD
- Loading/error/game-over states
- Base set units in buy panel (optionally)
- Supply counters on buy panel cards

### Future: Click Fix (JS Engine)

The 1.5% click rejection rate is from known JS engine edge cases:
- "cancel target when not in target mode" (targeting abilities)
- Some undo interactions
- See CLAUDE.md Click Fix Status section

Fixing these would bring click acceptance to ~100% and eliminate the 2.5% of replays that end early.

## Critical Implementation Rules (Carried Forward)

1. Connect provider signals BEFORE loading data (GDScript signals are synchronous)
2. Never mutate snapshot dictionaries (they're cached and shared)
3. Hooks dispatch on forward transitions only
4. Store RefCounted objects as member vars to prevent GC
5. Event detection is heuristic for MVP — snapshot state is authoritative

## Quick Start

```bash
# Fetch latest replay and preprocess
node tools/fetch_and_preprocess.js --latest

# Or use a specific replay code
node tools/fetch_and_preprocess.js PYFg2-yGsBE

# Run batch validation
node tools/validate_snapshots_batch.js --count 100

# Open Godot project
# Import c:\libraries\prismata-3d\ in Godot 4.6+, press F5
```
