# Visual Fidelity Audit Tool — Design Spec (v2.1)

**Goal:** Build a structural audit tool that compares what the PixiJS viewer renders per-card against what the Godot viewer currently supports, producing a quantified gap report. This creates infrastructure for systematically closing visual gaps — now for obvious differences, and later as the PixiJS viewer itself improves.

**Approach:** Pure Node.js data comparison. No screenshots, no rendering. Ports the PixiJS visual-state and status-overlay logic to JS pure functions, runs them on replay snapshots, and diffs against a Godot capability checklist.

**Parity target:** Current PixiJS viewer (not the original SWF client directly). The PixiJS viewer is itself an AS3 port and may differ from the SWF in edge cases. The audit measures Godot-vs-PixiJS parity, not Godot-vs-SWF parity.

**PixiJS reference version:** `<ladder>-site/src/components/game-renderer/` — commit hash recorded in every audit report JSON.

---

## Architecture

```
replay.json.gz
     │
     ▼
replay_to_snapshots.js  (existing, modified — adds delay/charge)
     │
     ▼
audit_visual_fidelity.js  (new — the audit runner)
     ├── visual_state.js     (new — port of visual-state.ts)
     ├── status_overlay.js   (new — port of StatusOverlay.ts logic)
     └── GODOT_CAPABILITIES  (inline — what Godot currently handles)
     │
     ▼
Gap Report (stdout + JSON file)
```

---

## File Plan

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/visual_state.js` | Create | Pure function: `computeVisualState(unit, cardMeta, phase, colorOnBottom)` → visual state object. 1:1 port of `visual-state.ts`. |
| `tools/status_overlay.js` | Create | Pure function: `computeStatusIcons(unit, cardMeta)` → icon/number list. 1:1 port of `StatusOverlay.ts` update() logic (data only). |
| `tools/audit_visual_fidelity.js` | Create | CLI runner. Loads replay, generates snapshots, computes PixiJS visual state per unit, diffs against Godot capability model. Outputs human-readable + JSON reports. |
| `tools/compare_layouts.js` | Existing | Layout position audit (built and validated — 100% match across 20 replays). |
| `tools/replay_to_snapshots.js` | Modify | Add `delay` and `charge` fields to snapshot unit state. |
| `tools/__tests__/visual_state.test.js` | Create | Fixture tests for visual_state.js against known PixiJS outputs. |
| `tools/__tests__/status_overlay.test.js` | Create | Fixture tests for status_overlay.js against known PixiJS outputs. |

---

## Five-State Support Model

Every visual feature for every unit-render is classified into exactly one of:

| State | Meaning | Example |
|-------|---------|---------|
| `exact` | Godot renders this identically to PixiJS | `layout_position` (verified by compare_layouts.js) |
| `approximate` | Godot communicates the same information differently | `blocking_signal` via blue tint vs blue shield overlay |
| `unsupported` | PixiJS renders this, Godot doesn't | `player_color_frame`, `attack_icon` |
| `excluded` | Intentionally not part of Godot viewer design | `name_label` (hidden by choice) |
| `unauditable` | Snapshot data insufficient to determine PixiJS output | `sellable_prompt` when `boughtThisPhase` needed |

## State Parity vs Transition Parity

The audit has two separate buckets:

**State parity** — persistent per-unit visuals derived from snapshot state:
- Backgrounds, icons, alpha, orientation, status markers
- Audited from: current snapshot unit data

**Transition parity** — effects that fire during state changes:
- Buy flash, death skull, damage bang, breach emphasis
- Audited from: `events[]` array comparing prev/current snapshot
- Maps to Godot's visual hooks system

These are scored separately. A high state-parity score with low transition-parity is a different problem than the reverse.

---

## `visual_state.js` — PixiJS Visual State Port

Port of `<ladder>-site/src/components/game-renderer/visual-state.ts`.

**Input:** Snapshot unit data + card metadata from cardLibrary.jso + game phase + player perspective.

**Output:**
```javascript
{
    backFrame: 8,           // BACK_BUSYBLUE (0-9, maps to background texture)
    coverFrame: 0,          // COVER_EMPTY (0-5, maps to overlay texture)
    shadingFrame: 0,        // SHADING_EMPTY (0-4, maps to shield overlay)
    cardAlpha: 0.999,       // 1.0 normal, 0.87 under construction
    showSkull: false,       // death skull overlay
    showChillSnowflake: false, // chill snowflake overlay
    damageCounter: 0,       // red damage number (0 = hidden)
    auditable: true,        // false if snapshot data was insufficient
    unauditableReason: null, // e.g. 'missing boughtThisPhase'
}
```

**Mapping snapshot fields to PixiJS CardInstance:**
- `unit.state.mode` → `deadness` (alive/dead), `constructionTime`
- `unit.state.blocking` → `blocking`
- `unit.state.chilled` → `disruptDamage`
- `unit.state.attacking` → `role === 'assigned'`
- `unit.stats.hp` → `health`
- `unit.stats.maxHp - unit.stats.hp` → `damage` (positive when hp < maxHp, 0 otherwise)
- `unit.state.delay` → `delay` (new field — added to snapshots)
- `unit.state.charge` → `charge` (new field — added to snapshots)
- Snapshot `phase` → phase string
- Unit `owner` → determine isBottomPlayer (P0 = bottom)
- `boughtThisPhase` → **not available** — mark cover_overlay as `unauditable` when sellable/bought logic would diverge

**Card metadata** comes from `cardLibrary.jso` via `card_id_map.js` (existing).

**Background frame enum** (from AS3 UIInst.as — 10 states):
| Value | Constant | Texture | When |
|-------|----------|---------|------|
| 0 | BACK_DEAD | Card_Dead.png | Unit killed (gray) |
| 1 | BACK_BLOCK | Card_Block.png | Blocking (white, P0/bottom) |
| 2 | BACK_BUSY | Card_Blue.png | Default idle (unused in practice — see BUSYBLUE/BUSYRED) |
| 3 | BACK_ABSORB | Card_Orange.png | Absorbing damage (orange) |
| 4 | BACK_BLOCK_FROST | Card_Chilled.png | Fully chilled (frost overlay) |
| 5 | BACK_BOUGHT | Card_Pink.png | Under construction (pink/gold) |
| 6 | BACK_WHITEPINK | Card_WhitePink.png | Dead with damage (white-pink) |
| 7 | BACK_BLOCKRED | Card_Red.png | Blocking (red, P1/top) |
| 8 | BACK_BUSYBLUE | Card_Blue.png | Idle — P0/bottom player (blue) |
| 9 | BACK_BUSYRED | Card_Red.png | Idle — P1/top player (red) |

**Cover frame enum** (6 states):
| Value | Constant | Texture | When |
|-------|----------|---------|------|
| 0 | COVER_EMPTY | none | Default — no overlay |
| 1 | COVER_INVSPAWN | highlight_blackclock.png | Under construction (black clock) |
| 2 | COVER_INVBOUGHT | highlight_goldclock.png | Just bought (gold clock) |
| 3 | COVER_ASSIGNED | highlight_cage2.png | Assigned to attack (cage) |
| 4 | COVER_PROMPT | highlight_goldshield.png | Sellable blocker (gold shield) |
| 5 | COVER_BANG | highlight_damagebang.png | Taking damage (bang burst) |

**Shading frame enum** (5 states):
| Value | Constant | Texture | When |
|-------|----------|---------|------|
| 0 | SHADING_EMPTY | none | Default — no shield overlay |
| 1 | SHADING_NOTBLOCK | highlight_whiteshield.png | Can block but isn't (white) |
| 2 | SHADING_BLOCK | highlight_blueshield.png | Blocking (blue, P0) |
| 3 | SHADING_DEAD_BLOCK | highlight_whiteshieldB.png | Dead blocker (white variant) |
| 4 | SHADING_REDBLOCK | highlight_redshield.png | Blocking (red, P1) |

---

## `status_overlay.js` — Status Icon Computation

Port of `<ladder>-site/src/components/game-renderer/StatusOverlay.ts` update() method.

**Input:** Same as visual_state.js.

**Output:**
```javascript
{
    constructionTimer: 2,       // null if not under construction
    variableIcons: [            // left-column stacked icons
        { type: 'hp', count: 3 },
        { type: 'delay', count: 1 },
    ],
    fixedIcons: {               // bottom-right corner
        attack: { value: 2 },   // null if no attack
        defense: { value: 4 },  // null if fragile or no toughness
        spell: true,            // clock icon for spells (mutually exclusive with defense)
    },
}
```

**Variable icon types** (from StatusOverlay.ts):
- `frontline` — if `cardMeta.isFrontline` (no count)
- `hp` — if `cardMeta.isFragile` (count = health)
- `delay` — if `inst.delay > 0`
- `lifespan` — if `inst.lifespan > 0`
- `charge` — if charge > 0 (icon varies by level 0-3)
- `chill` — if `disruptDamage > 0` (full vs partial based on health comparison)

**Construction timer** takes precedence: when `constructionTime > 0 && damage === 0`, only the timer number and (for fragile units) HP icon are shown.

---

## Godot Capability Model

Inline in `audit_visual_fidelity.js`. Updated as features are implemented in Godot.

Features are defined **semantically** — what information the player sees — not by PixiJS render layers. This avoids double-counting when Godot uses a different mechanism (e.g. tint) to communicate the same thing.

Each value is one of: `'exact'`, `'approximate'`, `'unsupported'`, `'excluded'`.

```javascript
const GODOT_CAPABILITIES = {
    // === STATE PARITY (per-unit, per-snapshot) ===

    // Layout
    layout_position: 'exact',       // verified by compare_layouts.js
    card_sprite: 'exact',           // card art loaded for all units

    // Player identity signal — PixiJS: blue/red background frame
    player_color_frame: 'unsupported',

    // Construction signal — PixiJS: pink bg + clock overlay + timer number + 0.87 alpha
    construction_signal: 'approximate',  // Godot: gray dim tint (no timer, no clock)

    // Blocking signal — PixiJS: white/blue/red bg + shield shading overlay
    blocking_signal: 'approximate',      // Godot: blue tint

    // Attack commitment signal — PixiJS: cage overlay (COVER_ASSIGNED)
    attack_signal: 'approximate',        // Godot: red tint

    // Chill signal — PixiJS: frost bg + snowflake + chill icon with number
    chill_signal: 'approximate',         // Godot: light blue tint (no number)

    // Damage signal — PixiJS: orange/dead bg + bang overlay + red damage number
    damage_signal: 'unsupported',

    // Status numbers (bottom-right corner)
    attack_icon: 'unsupported',          // sword + attack value
    defense_icon: 'unsupported',         // shield + toughness value

    // Status numbers (left column, variable)
    construction_timer: 'unsupported',   // build countdown number
    hp_icon: 'unsupported',              // fragile unit HP
    frontline_icon: 'unsupported',       // undefendable marker
    delay_icon: 'unsupported',           // delay counter
    lifespan_icon: 'unsupported',        // doom counter
    charge_icon: 'unsupported',          // charge level
    chill_icon: 'unsupported',           // disruption number (separate from chill_signal tint)

    // Card orientation
    p1_card_flip: 'unsupported',         // SWF flips P1 cards

    // Intentionally excluded
    name_label: 'excluded',              // exists in Godot but hidden by design
    sellable_prompt: 'excluded',         // gold shield — interactive feature, not replay-relevant

    // === TRANSITION PARITY (event-driven, per-snapshot-pair) ===

    // Buy effect — PixiJS: gold clock cover on new unit
    buy_effect: 'approximate',           // Godot: scale flash via visual hook

    // Death effect — PixiJS: skull overlay at death position
    death_effect: 'approximate',         // Godot: red sphere flash via visual hook

    // Damage effect — PixiJS: bang overlay + damage counter
    damage_effect: 'unsupported',

    // Breach effect — PixiJS: red flash + skull rain
    breach_effect: 'unsupported',
};
```

---

## Report Output

### Human-readable (stdout)

```
=== Visual Fidelity Audit ===
Replay: R2ss+-3St7a
PixiJS: <ladder>-site @ abc1234
Godot:  prismata-3d @ def5678  (capability model 2026-03-26)
Snapshots: 73  |  Unit-renders: 4299

STATE PARITY (sorted by unsupported count):
  player_color_frame
    applicable: 4299  exact: 0  approximate: 0  unsupported: 4299  unauditable: 0
  attack_icon
    applicable: 3841  exact: 0  approximate: 0  unsupported: 3841  unauditable: 0
  blocking_signal
    applicable:  298  exact: 0  approximate: 298  unsupported: 0   unauditable: 0
  construction_signal
    applicable:  412  exact: 0  approximate: 412  unsupported: 0   unauditable: 0
  name_label
    excluded (intentional)

TRANSITION PARITY:
  buy_effect
    applicable: 52   exact: 0  approximate: 52  unsupported: 0
  death_effect
    applicable: 23   exact: 0  approximate: 23  unsupported: 0
  breach_effect
    applicable:  3   exact: 0  approximate: 0   unsupported: 3

GAP CLASSIFICATION:
  Renderer gaps:    8 features (need Godot implementation)
  Data-model gaps:  2 features (need snapshot schema: boughtThisPhase, sellable)

SCORES:
  State:      exact 34.2%  |  exact+approx 42.1%  |  weighted 39.2%
  Transition: exact  0.0%  |  exact+approx 44.8%  |  weighted 22.4%
  Combined:   exact 31.0%  |  exact+approx 42.4%  |  weighted 37.1%
```

### Machine-readable (JSON file)

Written to `<replay>_audit.json` or `--output <path>`. Enables tracking over time, graphing, CI.

```json
{
    "auditVersion": 2,
    "pixiReference": {
        "repo": "<ladder>-site",
        "path": "src/components/game-renderer/",
        "commit": "abc1234"
    },
    "godotReference": {
        "repo": "prismata-3d",
        "capabilityModelVersion": "2026-03-26",
        "commit": "def5678"
    },
    "replayId": "R2ss+-3St7a",
    "snapshotCount": 73,
    "unitRenderCount": 4299,
    "stateParity": {
        "player_color_frame": {
            "applicable": 4299,
            "exact": 0,
            "approximate": 0,
            "unsupported": 4299,
            "excluded": 0,
            "unauditable": 0,
            "weight": 1.0
        },
        "blocking_signal": {
            "applicable": 298,
            "exact": 0,
            "approximate": 298,
            "unsupported": 0,
            "excluded": 0,
            "unauditable": 0,
            "weight": 0.7
        }
    },
    "transitionParity": {
        "buy_effect": {
            "applicable": 52,
            "exact": 0,
            "approximate": 52,
            "unsupported": 0,
            "excluded": 0,
            "unauditable": 0,
            "weight": 0.5
        }
    },
    "scores": {
        "state": { "rawExact": 0.34, "rawExactApproximate": 0.42, "weighted": 0.39 },
        "transition": { "rawExact": 0.00, "rawExactApproximate": 0.45, "weighted": 0.22 },
        "combined": { "rawExact": 0.31, "rawExactApproximate": 0.42, "weighted": 0.37 }
    },
    "gapClassification": {
        "rendererGaps": ["player_color_frame", "damage_signal", "attack_icon"],
        "dataModelGaps": ["boughtThisPhase", "sellable"]
    }
}
```

### Batch report (--batch N)

Combined report across N replays. Use `--seed` for reproducibility.

```
=== Batch Visual Fidelity Audit (50 replays, seed=42) ===
Total unit-renders: 187,432

AGGREGATED STATE PARITY:
  player_color_frame  187432/187432 (100.0%) unsupported
  attack_icon         164221/187432 (87.6%)  unsupported
  blocking_signal      14221/187432  (7.6%)  approximate
  ...

SCORES (across 50 replays):
  State:      exact avg 33.8% (min 28.1%, max 41.2%)
  Transition: exact avg  0.0% (min  0.0%, max  0.0%)
  Combined weighted: avg 37.1% (min 31.9%, max 43.3%)
```

The JSON batch report includes the list of sampled replay IDs and seed for exact reproduction.

---

## Scoring

### Denominators

- One "unit-render" = one unit in one snapshot
- Each feature has an **applicable** count: how many unit-renders where that feature is relevant
  - `attack_icon`: applicable only when card has attack > 0
  - `construction_timer`: applicable only when buildTurnsRemaining > 0
  - `background_frame`: applicable for every alive unit (always)
  - `hp_icon`: applicable only for fragile units
- Percentages use applicable count as denominator, not total unit-renders

### Weights

Features have importance weights for the weighted score. Defined semantically (no double-counting):

**State features:**
| Feature | Weight | Rationale |
|---------|--------|-----------|
| player_color_frame | 1.0 | Every card, most visible element |
| attack_icon | 0.9 | High frequency, important game info |
| defense_icon | 0.9 | High frequency, important game info |
| construction_signal | 0.8 | Medium frequency, critical game info |
| construction_timer | 0.8 | The number itself (subset of construction signal) |
| blocking_signal | 0.7 | Medium frequency, blocking info |
| attack_signal | 0.7 | Medium frequency, commitment info |
| damage_signal | 0.7 | Important game state |
| chill_signal | 0.6 | Includes tint + number + snowflake |
| hp_icon | 0.8 | Low frequency but critical for fragile units |
| frontline_icon | 0.5 | Low frequency |
| delay_icon | 0.5 | Low frequency |
| lifespan_icon | 0.5 | Low frequency |
| charge_icon | 0.5 | Low frequency |
| p1_card_flip | 0.4 | Orientation, not information |

**Transition features:**
| Feature | Weight | Rationale |
|---------|--------|-----------|
| buy_effect | 0.5 | Transient, cosmetic |
| death_effect | 0.6 | Important feedback |
| damage_effect | 0.6 | Important feedback |
| breach_effect | 0.7 | Major game event |

Features with state `excluded` are omitted from scoring entirely.

### Score formulas

- **Raw exact** = sum(exact counts) / sum(applicable counts) across all features
- **Raw exact+approximate** = sum(exact + approximate) / sum(applicable) across all features
- **Weighted** = sum(weight × (exact + 0.5×approximate) / applicable) / sum(weights) across features with applicable > 0

---

## CLI Interface

```bash
# Single replay audit (human-readable stdout + JSON file)
node tools/audit_visual_fidelity.js <replay.json.gz>

# Specific turn
node tools/audit_visual_fidelity.js <replay.json.gz> --turn 15

# Batch mode (N random replays from archive, reproducible)
node tools/audit_visual_fidelity.js --batch 50 --seed 42

# Verbose per-unit details
node tools/audit_visual_fidelity.js <replay.json.gz> --turn 15 --verbose

# JSON output to specific path
node tools/audit_visual_fidelity.js <replay.json.gz> --output report.json

# Just show the capability model
node tools/audit_visual_fidelity.js --capabilities
```

---

## Tests for Pure-Function Ports

Fixture tests verify `visual_state.js` and `status_overlay.js` match PixiJS output for known scenarios:

### `visual_state.test.js` fixtures

| Scenario | Key inputs | Expected backFrame | Expected coverFrame |
|----------|-----------|-------------------|-------------------|
| Idle P0 drone | alive, no damage, P0 | BACK_BUSYBLUE (8) | COVER_EMPTY (0) |
| Idle P1 drone | alive, no damage, P1 | BACK_BUSYRED (9) | COVER_EMPTY (0) |
| Under construction | constructionTime=2 | BACK_BOUGHT (5) | COVER_INVSPAWN (1) |
| Blocking P0 | blocking=true, P0 | BACK_BLOCK (1) | COVER_EMPTY (0) |
| Blocking P1 | blocking=true, P1 | BACK_BLOCKRED (7) | COVER_EMPTY (0) |
| Fully chilled | disruptDamage >= health | BACK_BLOCK_FROST (4) | COVER_EMPTY (0) |
| Taking damage (defense) | damage > 0, partial, defense phase | BACK_ABSORB (3) | COVER_BANG (5) |
| Dead with damage | damage >= health | BACK_WHITEPINK (6) | COVER_BANG (5) |
| Assigned to attack | role=assigned | any | COVER_ASSIGNED (3) |

### `status_overlay.test.js` fixtures

| Scenario | Expected output |
|----------|----------------|
| Idle drone (no special properties) | fixedIcons: no attack, defense with toughness |
| Tarsier (2 attack) | fixedIcons: attack=2, no defense (fragile) |
| Under construction (timer=2) | constructionTimer=2, no variable icons |
| Fragile unit under construction | constructionTimer + hp icon |
| Chilled unit (disrupt=3, health=5) | variableIcons: chill(partial, 3) |
| Unit with delay=1 | variableIcons: delay(1) |

---

## Implementation Notes

- `visual_state.js` needs access to `cardLibrary.jso` for card metadata (defaultBlocking, isFragile, cardType, toughness, attack). Use existing `card_id_map.js` to resolve cardId → internal name → library entry.
- Snapshot units store HP as `stats.hp` (current) and `stats.maxHp`. Damage = `maxHp - hp`. The PixiJS visual-state uses `inst.damage` directly, so compute it.
- The snapshot doesn't have `boughtThisPhase` or `role === 'sellable'` — these are PixiJS-specific instance fields not in the snapshot schema. The audit marks dependent features as `unauditable` for those unit-renders (not false negatives).
- `lifespan` is in the snapshot (`state.lifespan`, -1 = infinite). `delay` and `charge` are added to `replay_to_snapshots.js` as part of this work (trivially extractable from `inst.delay` and `inst.charge`).
- Update the BoardSnapshot schema in the design spec (`2026-03-26-godot-3d-battlefield-viewer-design.md`) to reflect the new `delay` and `charge` fields under `state`.
- PixiJS reference commit hash: read from `git -C <<ladder>-path> rev-parse HEAD` at audit time.
- Godot reference commit hash: read from `git -C <prismata-3d-path> rev-parse HEAD` at audit time. Both commits recorded in JSON output for reproducibility.

### Gap classification

The report separates two kinds of gaps:
- **Renderer gaps** — Godot doesn't render something it could (the snapshot has the data). Fix: implement in Godot.
- **Data-model gaps** — the snapshot doesn't carry information the PixiJS viewer uses. Fix: add fields to `replay_to_snapshots.js`.

This tells you whether the next task is "modify the Godot viewer" or "modify the preprocessor."

---

## Immediate Fix Targets

Once the audit quantifies the gaps, the highest-impact Godot improvements (by frequency and visual prominence):

1. **Card backgrounds** — replace flat sprite with layered rendering (background frame + card art)
2. **Attack/defense icons** — sword and shield in bottom corners with numbers
3. **Construction timer** — build countdown number overlay
4. **HP for fragile units** — heart icon + number

These are all additive — they layer on top of the existing card sprite without changing the layout or reconciliation logic.
