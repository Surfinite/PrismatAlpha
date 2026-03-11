# DeepSets Schema Redesign — Design Spec

**Date:** 2026-03-11
**Status:** Approved design, pending implementation planning
**Supersedes:** Option 2 (flat 116×11 type-count schema) from Training Plan V3
**Author:** Surfinite + Claude Code

---

## Motivation

The current training schema (Option 2) encodes game state as a flat 1,290-dim vector: 116 unit types × 11 aggregate features + 14 globals. This loses critical instance-level information:

- **Build time remaining** — "2 constructing Tarsiers" doesn't say if they finish next turn or in 3 turns
- **Current HP** — fragile units at different health levels are strategically different (Xaetron cycle)
- **Freeze/chill status** — frozen units can't act but are counted as "ready"
- **Lifespan remaining** — a Forcefield about to expire vs one with 3 turns left
- **Stamina/charges** — units with limited uses (Wincer threat-holding)
- **Exhaust/cooldown** — Iso Kronus cycle timing, Scorch/Wincer cooldown

Community feedback (Spyrfyr, Discord) confirmed these gaps are strategically significant. Expanding the flat schema to capture all instance properties (Spyrfyr's proposal: 87 features × 116 = 10,106 dim) is wasteful — most slots are zero, and the model can't generalise across units (each unit type's features are independent input neurons).

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | DeepSets (shared encoder + sum pooling) | Prismata mechanics are additive (damage pooled, freeze pooled). No pairwise unit interactions → attention overhead unjustified. |
| Unit identity | Hybrid (learned embedding + static properties) | Embedding captures abilities/synergies. Properties enable cross-unit transfer for rare units and future new units. |
| Deployment target | Rewrite C++ NeuralNet.cpp | Accept slower inference for more expressive evaluation. 45s think time is the human benchmark. |
| Inference speed priority | Quality over speed | A superhuman model at 2-minute think time is a massive win. RL self-play uses shorter think times independently. |
| Data sources | Single pipeline from replays | Human S3 replays, matchup_clean replays, and future self-play replays all go through one extraction path. |
| Modified ability-spawned units | Same unit type, different instance properties | Endotherm Kit Frostbites (lifespan=4) are just Frostbites with lifespan_remaining=4. No special handling needed. |
| Max instances | TBD from replay data analysis | Pad to a fixed MAX_INSTANCES (estimated 80-100 per player). Excess dropped by strategic priority. |

## Architecture

### Overview

```
Board state (N unit instances + supply + resources)
    │
    ├── Each instance: [embedding(32) | properties(13) | state(10)] = 55 floats
    │       → Shared Encoder MLP (55→128→128)
    │       → Pool by owner: P0_pool(128), P1_pool(128)
    │
    ├── Supply: 116 types × [p0_sup, p1_sup, in_set] = 3 floats each
    │       → Shared Supply MLP (3→32→32)
    │       → Sum all → supply_pool(32)
    │
    └── Globals: [resources(12) + turn(1) + player(1)] = 14 floats

Concatenate: [P0_pool | P1_pool | supply_pool | globals] = 302-dim
    → Value MLP (302→256→256→1)
    → sigmoid → P(P0 wins)
```

### Per-Instance Token (55 floats)

Each unit instance on the board becomes a token with three concatenated parts:

#### Unit-Type Embedding (learned, 32 floats)

Lookup table: 116 unit types → 32-dim learned vector. The canonical unit list is `training/data/unit_index.json` (11 base set + 105 competitive random set). Units outside this list (the ~45 deprecated/event units in `cardLibrary.jso`) are dropped during extraction — they never appear in competitive play. If a replay contains an unknown unit type (e.g., ability-spawned tokens not in the index), it is silently excluded from the instance list (the game outcome label remains valid). Captures abilities, synergies, and meta-game role — things that static properties can't express (Apollo snipe, Endotherm Kit spawning, Centurion death triggers). Initialized randomly, trained end-to-end.

#### Static Property Vector (from cardLibrary, 13 floats)

Fixed properties of the unit **type**, looked up at extraction time:

| # | Property | Description | Encoding |
|---|---|---|---|
| 0 | buy_cost_gold | Gold cost | raw / normalized |
| 1 | buy_cost_green | Green cost | raw |
| 2 | buy_cost_blue | Blue cost | raw |
| 3 | buy_cost_red | Red cost | raw |
| 4 | buy_cost_energy | Energy cost | raw |
| 5 | base_health | Max HP (startingHealth) | raw |
| 6 | fragile | Is fragile | 0/1 |
| 7 | default_blocking | Starts as blocker | 0/1 |
| 8 | base_build_time | Turns to construct | raw |
| 9 | base_lifespan | Base turns before expiry (0=permanent) | raw (JS engine uses -1 for permanent; map to 0 during extraction) |
| 10 | base_attack | Attack produced per turn (if any) | raw |
| 11 | has_ability | Has an activated ability | 0/1 |
| 12 | max_stamina | Max charges — JS: `Card.startingCharge` (0=unlimited or N/A) | raw |

These are identical for every instance of the same unit type. They provide cross-unit transfer — the model learns "units with 5 HP and fragile behave like X" even for rarely-seen units.

#### Instance State Vector (dynamic, 10 floats)

The actual state of this specific unit right now:

| # | Feature | Description | Encoding |
|---|---|---|---|
| 0 | owner | Which player owns this | 0/1 |
| 1 | is_constructing | Under construction | 0/1 |
| 2 | turns_until_ready | max(constructionTime, delay) — build, exhaust, or cycle timer | raw (0=ready) |
| 3 | is_blocking | Assigned as blocker | 0/1 |
| 4 | ability_used | Used ability this turn | 0/1 |
| 5 | current_hp | Effective health (health - damage for non-fragile, health for fragile) | raw |
| 6 | hp_fraction | current_hp / base_health (0.0 if base_health=0) | 0.0–1.0 |
| 7 | is_frozen | Currently frozen/disrupted (disruptDamage > 0) | 0/1 |
| 8 | lifespan_remaining | Turns until expiry (0=permanent) | raw (JS uses -1 for permanent; map to 0) |
| 9 | stamina_remaining | Charges left — JS: `Inst.charge` (0=N/A or unlimited) | raw |

**Key design note on `turns_until_ready`:** The JS engine `delay` field is overloaded — it represents build delay (non-invulnerable units), ability exhaust (Scorch/Wincer cooldown), and passive cycle timers (Iso Kronus). In all cases the semantic is "this unit can't act for N more turns." The unit-type embedding provides context for what happens when delay reaches 0.

### Shared Instance Encoder

All instances (both players) go through the same 2-layer MLP:

```
token (55 floats)
    → Linear(55, 128) → ReLU
    → Linear(128, 128) → ReLU
    → 128-dim encoded vector
```

Shared weights enable cross-unit transfer. The encoder learns general concepts ("low HP = vulnerable", "1 turn from ready = about to contribute") that apply across all unit types.

### Player Pooling

After encoding, **sum** all instances by owner:

```
P0_pool = Σ encoded(inst) for all inst where owner=0    (128-dim)
P1_pool = Σ encoded(inst) for all inst where owner=1    (128-dim)
```

Sum (not mean) preserves magnitude — 6 Drones should produce a bigger signal than 3. This aligns with Prismata's additive mechanics (total attack, total freeze, total blocking HP are all sums).

### Supply Encoding (Separate Pathway)

Supply is per-unit-type, not per-instance. A separate small shared MLP encodes it:

For each of the 116 unit types:
```
[P0_supply_remaining, P1_supply_remaining, in_card_set] (3 floats)
    → Linear(3, 32) → ReLU
    → Linear(32, 32) → ReLU
    → 32-dim vector
```

Sum across all 116 types → `supply_pool` (32-dim).

This tells the model "Tarsier supply is running low" without needing a Tarsier instance on the board.

### Global Features (14 floats)

| # | Feature | Encoding |
|---|---|---|
| 0-5 | P0 resources (gold, blue, red, green, energy, attack) | clamp/normalize |
| 6-11 | P1 resources (same) | clamp/normalize |
| 12 | Turn number | normalized (/50) |
| 13 | Active player indicator | 0 or 1 |

### Value MLP

```
[P0_pool(128) | P1_pool(128) | supply_pool(32) | globals(14)] = 302-dim
    → Linear(302, 256) → ReLU
    → Linear(256, 256) → ReLU
    → Linear(256, 1) → raw logit
    → sigmoid → P(P0 wins)
```

### Parameter Count

| Component | Parameters |
|---|---|
| Unit embeddings (116 × 32) | ~3,700 |
| Shared encoder (55→128→128) | ~23,500 |
| Supply encoder (3→32→32) | ~1,200 |
| Value MLP (302→256→256→1) | ~143,000 |
| **Total** | **~171,000** |

Compact model. Smaller than a 1,290→512→512→1 MLP (~920K params).

## C++ Inference Implementation

The implementation is a simple loop + accumulate pattern:

1. **Build token** for each instance: embedding lookup (table in memory) + property lookup (static table from cardLibrary) + state features (from GameState)
2. **Forward through shared encoder** (two matrix multiplies + ReLU)
3. **Accumulate** into P0_pool or P1_pool (running sum — no need to store all encoded instances)
4. **Forward supply tokens** through supply encoder, accumulate into supply_pool
5. **Concatenate** P0_pool + P1_pool + supply_pool + globals
6. **Forward through value MLP** (three matrix multiplies + ReLU + sigmoid)

Memory usage is constant regardless of board size — only the accumulators (128+128+32 floats) persist across instances. No attention matrices, no padding, no variable-size allocations.

**Scope note:** This is a ground-up replacement of the current `NeuralNet.cpp`, not a modification. The current code implements a flat MLP with residual blocks, LayerNorm, and a 1,785-dim fixed input. The DeepSets architecture requires: embedding table storage, a shared encoder forward pass in a loop, accumulation by player, a separate supply encoder loop, and a new value MLP. The binary weight format (`export_weights.py` → `.bin`) must also be redesigned — the current PNET format with named tensors for residual blocks does not apply. Both `NeuralNet.cpp` and `export_weights.py` need full rewrites.

## Training Considerations

### Label Design

Unchanged from Training Plan V3 — P(P0 wins) with the 4-way label strategy ablation (hard binary, temporal weighting, Elo-interpolated, neutral prior).

### Symmetry Augmentation

Mirror augmentation requires swapping P0/P1 pools and inverting the label. With DeepSets this is trivial: swap which instances are labeled owner=0 vs owner=1, swap P0/P1 supply values, swap P0/P1 resources. Produces a valid training example.

### Data Requirements

The model has ~171K parameters. Training data: ~100K human replay games (~3M records at ~30 turns/game) + ~420K self-play games (~12M records at ~30 turns/game) = ~15M total records. This is a very healthy ratio. The shared encoder means rare units benefit from transfer learning across all units — a rare unit with 2K games still gets gradient signal from the shared encoder weights trained on millions of instances of other units.

### Extraction Pipeline

A single extraction pipeline processes all replay sources:

1. **Human replays** — fetched from S3, stepped through JS engine
2. **Matchup replays** — saved by matchup_clean.js
3. **Future self-play replays** — same format

Each replay is stepped through the JS engine. At each start-of-turn state, the full `Inst` object is read for every unit on the board. All instance properties (`constructionTime`, `delay`, `health`, `damage`, `lifespan`, `charge`, `disruptDamage`, `blocking`, `role`) are extracted.

Output format: JSONL with per-instance unit data (replacing the current aggregate format), or a binary format for efficiency at scale. Schema version bump required.

### Discarded Data

Games without full replays (missing S3 data, fetch errors) must be discarded — per-instance extraction requires stepping through the full game. This is a small fraction of the dataset.

## Relationship to Training Plan V3

This design **replaces Phase 1a (Unit Representation)** in Training Plan V3. Specifically:

- **Option 2 is superseded** by the DeepSets architecture
- **Phase 1b (Label Design)** is unchanged
- **Phase 1c (Schema Versioning)** needs a new schema version (v2) reflecting the per-instance format
- **Phase 2 (Data Extraction)** needs a new extraction pipeline producing per-instance JSONL/binary
- **Phase 3 (Architecture Search)** ablations should compare: (a) DeepSets vs (b) flat Option 2 as baseline
- **Phase 4-6** are largely unchanged — training, evaluation, and self-play iteration work with any architecture

## Open Questions

1. **MAX_INSTANCES cap** — needs analysis of replay data to determine practical upper bound. Estimated 80-100 per player.
2. **Instance drop priority** — when exceeding MAX_INSTANCES, which units to drop? Likely excess Drones/Engineers (least unique strategic value).
3. **Normalization strategy** — should property features be normalized? Instance state features? Needs ablation.
4. **Encoder depth/width** — 2×128 is a starting point. Phase 3 ablations should explore 2×64, 2×256, 3×128.
5. **Policy head** — can be added later as a separate head on the pooled representation. Not in scope for initial design.
6. **C++ inference speed benchmark** — must be measured before committing to deployment think times.
