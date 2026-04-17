# Godot Visual Parity — Alpha Session

## Goal

Make the Godot 3D replay viewer (`c:\libraries\prismata-3d\`) look like a credible alpha by closing the highest-impact visual gaps identified by the audit tool. Target: recognizable game state at a glance.

## Context

The visual fidelity audit tool (`tools/audit_visual_fidelity.js`) was just built and run across 1000 replays. Current baseline scores:

- **State parity:** 41.6% exact, weighted 32.9%
- **3,252,714 unit-renders** audited

### Current Godot capabilities (what already works)
- Layout positions: **exact** (verified by compare_layouts.js)
- Card sprites: **exact** (143 card art images loaded)
- Construction/blocking/attack/chill: **approximate** (tint-based signals)
- Top-down orthographic camera (SWF-faithful)
- Event-driven architecture with visual hooks (buy flash, death effect)

### Gaps by impact (from 1000-replay batch audit)

| # | Feature | Missing renders | What to add |
|---|---------|----------------|-------------|
| 1 | `player_color_frame` | 3,252,714 | Blue/red card background behind sprite |
| 2 | `defense_icon` | 2,845,212 | Shield icon + toughness number (bottom-right) |
| 3 | `attack_icon` | 686,538 | Sword icon + attack number (bottom-right) |
| 4 | `hp_icon` | 385,624 | Heart icon + HP for fragile units |
| 5 | `construction_timer` | 341,981 | Build countdown number overlay |
| 6 | `lifespan_icon` | 102,796 | Doom counter |
| 7 | `delay_icon` | 65,464 | Delay counter |
| 8 | `charge_icon` | 41,129 | Charge level indicator |
| 9 | `frontline_icon` | 35,648 | Undefendable marker |
| 10 | `chill_icon` | 3,020 | Disruption number |
| 11 | `damage_signal` | 532 | Orange/dead bg + bang + damage number |
| 12 | `p1_card_flip` | (all P1 units) | Flip P1 card art |

### Recommended session priorities

**Must-have for alpha (items 1-3):**
1. **Player color frames** — colored rectangle behind each card sprite. Blue for P0, red for P1. Transforms the board from "pile of card art" to "two armies."
2. **Attack + defense icons** — sword and shield with numbers in bottom-right corner. Makes unit stats readable.

**Nice-to-have (items 4-5):**
3. **Construction timer** — number overlay showing build countdown
4. **HP icon** — heart + number for fragile units

Items 2-5 are all status overlays — building one label/icon system on the unit node covers them all.

## Key files in prismata-3d

| File | Purpose |
|------|---------|
| `battlefield/battlefield.gd` | Unit lifecycle, layout, reconciliation |
| `battlefield/battlefield.tscn` | Battlefield scene (terrain, divider) |
| `battlefield/unit_node.tscn` | Unit scene (sprite, collision) |
| `battlefield/unit_node.gd` | Unit script (if exists) |
| `camera/orbit_camera.gd` | Camera system |
| `hud/hud.gd` | HUD overlay |

## Reference files in PrismataAI

| File | Purpose |
|------|---------|
| `tools/visual_state.js` | Pure-function port of PixiJS visual state logic |
| `tools/status_overlay.js` | Pure-function port of PixiJS status overlay logic |
| `tools/audit_visual_fidelity.js` | Audit tool (run after changes to measure improvement) |
| `docs/superpowers/specs/2026-03-26-visual-fidelity-audit-design.md` | Full audit spec with enums, mappings |

## How to measure progress

After implementing changes in Godot, update the `GODOT_CAPABILITIES` object in `tools/audit_visual_fidelity.js` and re-run:

```bash
node tools/audit_visual_fidelity.js --batch 50 --seed 42
```

Compare scores against baseline (41.6% exact state, 32.9% combined weighted).

## Snapshot data available per unit

The preprocessor (`tools/replay_to_snapshots.js`) provides:
- `stats.hp`, `stats.maxHp`, `stats.attack`, `stats.chill`
- `state.mode`, `state.blocking`, `state.attacking`, `state.chilled`
- `state.buildTurnsRemaining`, `state.lifespan`, `state.delay`, `state.charge`
- `state.fragile`, `state.frontline`
- `owner` (0=P0/bottom/blue, 1=P1/top/red)
- `render.row`, `render.slot`

All the data needed for items 1-12 is already in the snapshots.
