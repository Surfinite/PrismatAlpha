# Feature Specification — PrismataAI Neural Network

**Feature version:** 2
**State dimension:** 1785 (161 units × 11 per-unit + 14 global)
**Policy dimension:** 161 (one per canonical unit)

## Overview

The feature vector encodes a Prismata game state as a fixed-size float vector.
Both Python (`training/vectorize.py`) and C++ (`source/ai/NeuralNet.cpp`)
must produce identical vectors for the same game state. The schema contract
(`training/schema.json`) is the single source of truth for layout agreement.

## POV Convention

Features are **absolute** (not relative to active player):
- Player 0 (P0/White) features always come first
- Player 1 (P1/Black) features always come second
- `active_player` field indicates whose turn it is

The value head output is from the **active player's perspective**:
- +1 = active player wins
- -1 = active player loses

## Canonical Unit Index

Source: `bin/asset/config/cardLibrary.jso` (the engine's master card database).
For each card entry, the display name is `UIName` if present, else the internal
engine name. All 161 display names are sorted alphabetically and assigned
indices 0–160.

The canonical index is stored in `training/data/unit_index.json` with metadata:
```json
{
  "version": "<sha256 of sorted names>",
  "count": 161,
  "units": { "A.R. Groans": 0, "Aegis": 1, ... }
}
```

Hash algorithm: SHA-256 of newline-joined sorted unit names, UTF-8 encoded,
no trailing newline. Example: names `["Drone", "Wall"]` → hash of `"Drone\nWall"`.

Of the 161 canonical units, 116 appear in the training data (expert replays).
The remaining 45 are campaign/token/non-competitive units — their feature
slots will be zero in training but are reserved for completeness (the C++
engine can instantiate all 161 types).

## Feature Layout

### Per-Unit Features (indices 0–1770)

For each of the 161 canonical units (index `u` = 0..160), 11 features at
positions `u*11 + 0` through `u*11 + 10`:

| Offset | Name              | Description                                  | Normalization |
|--------|-------------------|----------------------------------------------|---------------|
| 0      | p0_ready          | P0's count of this unit: ready (can act)     | Raw count     |
| 1      | p0_exhausted      | P0's count: exhausted (ability used/frozen)  | Raw count     |
| 2      | p0_constructing   | P0's count: under construction               | Raw count     |
| 3      | p0_blocking       | P0's count: assigned as blocker              | Raw count     |
| 4      | p1_ready          | P1's count of this unit: ready               | Raw count     |
| 5      | p1_exhausted      | P1's count: exhausted                        | Raw count     |
| 6      | p1_constructing   | P1's count: under construction               | Raw count     |
| 7      | p1_blocking       | P1's count: assigned as blocker              | Raw count     |
| 8      | p0_supply         | P0's remaining supply of this unit           | Raw count     |
| 9      | p1_supply         | P1's remaining supply of this unit           | Raw count     |
| 10     | in_card_set       | 1.0 if this unit is buyable in this game     | Binary 0/1    |

**Unit status classification (Python):**
- `building=True` → constructing
- `blocking=True AND abilityUsed=True` → blocking
- `abilityUsed=True` (only) → exhausted
- Otherwise → ready

**Unit status classification (C++):**
- `isUnderConstruction()` → constructing
- `getStatus() == CardStatus::Assigned` → blocking
- `canUseAbility()` → ready
- Otherwise → exhausted

### Global Features (indices 1771–1784)

| Index | Name           | Description                        | Normalization        | Cap  |
|-------|----------------|------------------------------------|----------------------|------|
| 1771  | p0_gold        | P0's current gold                  | Clamp then ÷ 20     | 20   |
| 1772  | p0_blue        | P0's current blue                  | Clamp then ÷ 5      | 5    |
| 1773  | p0_red         | P0's current red                   | Clamp then ÷ 5      | 5    |
| 1774  | p0_green       | P0's current green                 | Clamp then ÷ 15     | 15   |
| 1775  | p0_energy      | P0's current energy                | Clamp then ÷ 10     | 10   |
| 1776  | p0_attack      | P0's current attack                | Clamp then ÷ 25     | 25   |
| 1777  | p1_gold        | P1's current gold                  | Clamp then ÷ 20     | 20   |
| 1778  | p1_blue        | P1's current blue                  | Clamp then ÷ 5      | 5    |
| 1779  | p1_red         | P1's current red                   | Clamp then ÷ 5      | 5    |
| 1780  | p1_green       | P1's current green                 | Clamp then ÷ 15     | 15   |
| 1781  | p1_energy      | P1's current energy                | Clamp then ÷ 10     | 10   |
| 1782  | p1_attack      | P1's current attack                | Clamp then ÷ 25     | 25   |
| 1783  | turn_number    | Current turn number (per-player)   | Clamp then ÷ 30     | 30   |
| 1784  | active_player  | Whose turn: 0 = P0, 1 = P1        | Raw (0 or 1)        | —    |

**Normalization formula:** `min(value, cap) / cap` (clamp to [0, cap] then divide).
Exception: `active_player` is binary (0 or 1), no normalization.

### Normalization Rationale (from 251,106 training examples)

Caps are set above the 99th percentile to avoid information loss on typical
states while keeping the range [0, 1] for stable training:

| Feature     | p1   | p50  | p99   | max   | Cap  | Reasoning                        |
|-------------|------|------|-------|-------|------|----------------------------------|
| gold        | 0    | 0    | 12    | 155   | 20   | 99th=12, generous margin         |
| blue        | 0    | 0    | 2     | 14    | 5    | 99th=2, rare to have >5          |
| red         | 0    | 0    | 2     | 20    | 5    | 99th=2, rare to have >5          |
| green       | 0    | 0    | 9     | 101   | 15   | 99th=9, green can spike          |
| energy      | 0    | 0    | 5     | 38    | 10   | 99th=5, moderate margin          |
| attack      | 0    | 0    | 18–19 | 79    | 25   | 99th≈19, generous for late game  |
| turn_number | 1    | 7    | 19    | 39    | 30   | 99th=19, most games end by 30    |

## Value Label Distribution

From 251,106 training examples (expert replays, at least one player ≥2000 ELO):

| Label    | Count   | Percentage |
|----------|---------|------------|
| Win (+1) | 144,471 | 57.5%      |
| Loss (-1)| 105,514 | 42.0%      |
| Draw (0) |   1,121 |  0.4%      |

**Mean:** 0.155, **Std:** 0.986. Distribution is NOT imbalanced (no class >70%).
Win rate >50% is expected: only expert (2000+) player turns are included, so
those players win more often.

## UNK Handling

No unknown unit names were found in the training data (0 out of 251,106
examples). All 116 unique unit names in the training data are canonical
engine names. No UNK index is needed.

## File Cross-References

| File | Role |
|------|------|
| `training/schema.json` | Machine-readable schema contract (loaded by Python + C++) |
| `training/data/unit_index.json` | Canonical name→index mapping with hash |
| `training/vectorize.py` | Python feature extraction (training pipeline) |
| `source/ai/NeuralNet.cpp` | C++ feature extraction (inference) |
| `bin/asset/config/cardLibrary.jso` | Canonical source of all unit display names |
