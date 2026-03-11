# DeepSets Schema Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat 1,290-dim type-aggregate feature vector with a DeepSets architecture that processes per-instance unit data through a shared encoder with sum pooling.

**Architecture:** Three sequential phases — (1) per-instance data extraction from JS engine, (2) PyTorch DeepSets model + training, (3) C++ inference engine rewrite + weight export. Each phase produces independently testable output.

**Tech Stack:** JavaScript (extraction), Python/PyTorch (model), C++ (inference), HDF5 (storage)

**Spec:** `docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md`

---

## File Structure

### New files
| File | Purpose |
|---|---|
| `training/schema_v2.json` | New schema contract for per-instance DeepSets format |
| `training/property_table.json` | Static property vectors for all 116 unit types (from cardLibrary) |
| `training/vectorize_v2.py` | New vectorizer: per-instance JSONL → HDF5 with variable-length instance lists |
| `training/model_deepsets.py` | DeepSets PyTorch model (`PrismataDeepSets`) |
| `training/export_weights_v2.py` | Weight exporter for DeepSets binary format |
| `training/tests/test_vectorize_v2.py` | Tests for new vectorizer |
| `training/tests/test_model_deepsets.py` | Tests for DeepSets model |
| `training/tests/test_export_v2.py` | Tests for weight export + cross-language verification |
| `js_engine/test_extract_instances.js` | Tests for `instToRichUnit()` in state_adapter.js |

### Modified files
| File | Change |
|---|---|
| `js_engine/state_adapter.js` | Add `instToRichUnit()` alongside existing `instToUnit()` |
| `js_engine/matchup_clean.js` | Update `extractTrainingExample()` to use rich instance format |
| `source/engine/Card.h` | Add `bool abilityUsedThisTurn() const` public getter for `m_abilityUsedThisTurn` |
| `source/ai/NeuralNet.h` | Replace structs with DeepSets architecture (embedding table, shared encoder, supply encoder, value MLP) |
| `source/ai/NeuralNet.cpp` | Ground-up rewrite of inference: loop+accumulate pattern |
| `training/train.py` | Import and use `PrismataDeepSets` from model_deepsets.py; update data loading for new HDF5 format |

### Unchanged files
| File | Why |
|---|---|
| `training/data/unit_index.json` | Canonical unit list unchanged (116 units) |
| `bin/asset/config/cardLibrary.jso` | Source of truth for static properties — read-only |

---

## Chunk 1: Per-Instance Data Extraction

This chunk produces rich per-instance JSONL from the JS engine — the foundation everything else builds on.

### Task 1: Build static property table from cardLibrary

**Files:**
- Create: `training/property_table.json`
- Create: `js_engine/build_property_table.js`

- [ ] **Step 1: Write the property table builder**

`js_engine/build_property_table.js` reads `cardLibrary.jso` and `training/data/unit_index.json`, extracts the 13 static properties for each of the 116 units, and writes `training/property_table.json`.

Properties to extract per unit (from `Card.js` constructor):
```javascript
{
  buy_cost_gold:    buyCost.pool[MANA_P] || 0,
  buy_cost_green:   buyCost.pool[MANA_G] || 0,
  buy_cost_blue:    buyCost.pool[MANA_B] || 0,
  buy_cost_red:     buyCost.pool[MANA_R] || 0,
  buy_cost_energy:  buyCost.pool[MANA_H] || 0,
  base_health:      card.startingHealth,        // from toughness field
  fragile:          card.fragile ? 1 : 0,
  default_blocking: card.defaultBlocking ? 1 : 0,
  base_build_time:  card.buildTime,             // default 1
  base_lifespan:    card.lifespan === -1 ? 0 : card.lifespan,  // map -1→0
  base_attack:      card.attackPotential >= 0 ? card.attackPotential : 0,
  has_ability:      card.hasAbility ? 1 : 0,
  max_stamina:      card.startingCharge         // 0 = unlimited/N/A
}
```

Output format:
```json
{
  "schema_version": "v2",
  "num_units": 116,
  "num_properties": 13,
  "property_names": ["buy_cost_gold", ...],
  "units": {
    "Engineer": { "index": 0, "properties": [0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 0] },
    "Drone": { "index": 1, "properties": [3, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0] },
    ...
  }
}
```

- [ ] **Step 2: Run the builder and verify output**

```bash
node js_engine/build_property_table.js
```

Verify: 116 entries, each with 13 numeric properties. Spot-check:
- Engineer: gold=0, health=1, defaultBlocking=1, buildTime=1
- Tarsier: gold=4, red_cost should be from buyCost "1R" → red=1 (VERIFY: buyCost format is `"4R"` meaning 4 gold + ... no, check `buyCost` parsing in Card.js — digits are gold, letter suffixes are colors)
- Zemora: buildTime=6, health=20, fragile=1
- Iso Kronus: buildTime=2, health=5, fragile=1, base_attack=2

**Important:** buyCost parsing in Card.js: digits = gold (`MANA_P`), `G` = green, `B` = blue, `C` = red, `H` = energy. Need to parse via the Card/Mana constructor, not manual string parsing.

- [ ] **Step 3: Commit**

```bash
git add js_engine/build_property_table.js training/property_table.json
git commit -m "feat: build static property table for DeepSets (116 units × 13 properties)"
```

---

### Task 2: Rich per-instance extraction in JS engine

**Files:**
- Modify: `js_engine/state_adapter.js` (add `instToRichUnit()`)
- Create: `js_engine/test_extract_instances.js`

- [ ] **Step 1: Add `instToRichUnit()` to state_adapter.js**

Add alongside existing `instToUnit()` (which stays for backward compat). New function extracts all 10 instance state features from an `Inst` object:

```javascript
function instToRichUnit(inst) {
    const card = inst.card;
    const isBuilding = inst.constructionTime > 0;
    const baseHealth = card.startingHealth || 1;
    const currentHp = card.fragile ? inst.health : (inst.health - inst.damage);

    return {
        name:               card.UIName,
        owner:              inst.owner,           // 0 or 1
        is_constructing:    isBuilding ? 1 : 0,
        turns_until_ready:  Math.max(inst.constructionTime, inst.delay),
        is_blocking:        (inst.blocking && inst.role === C.ROLE_ASSIGNED) ? 1 : 0,
        ability_used:       (inst.role === C.ROLE_ASSIGNED && !inst.blocking) ? 1 : 0,  // NOTE: inst.abilityUsed does NOT exist on Inst; role-based inference matches state_adapter.js. At start-of-turn snapshots this is typically 0.
        current_hp:         Math.max(0, currentHp),
        hp_fraction:        baseHealth > 0 ? Math.max(0, currentHp) / baseHealth : 0,
        is_frozen:          inst.disruptDamage > 0 ? 1 : 0,
        lifespan_remaining: inst.lifespan === -1 ? 0 : Math.max(0, inst.lifespan),
        stamina_remaining:  inst.charge || 0
    };
}
```

Export it from state_adapter.js.

- [ ] **Step 2: Write test for instToRichUnit**

`js_engine/test_extract_instances.js` — construct mock Inst objects matching known game states and verify extraction output:

```javascript
// Test 1: Fresh Drone (ready, healthy, no special state)
// Test 2: Constructing Tarsier (buildTime=2, constructionTime=2)
// Test 3: Frozen Wall (disruptDamage > 0)
// Test 4: Iso Kronus with delay=2 (cycle timer)
// Test 5: Fragile unit (Zemora) with health=15 of 20
// Test 6: Forcefield with lifespan=2
// Test 7: Dead unit (should be excluded before reaching this function)
```

- [ ] **Step 3: Run tests**

```bash
cd js_engine && node test_extract_instances.js
```

Expected: All 7 cases pass.

- [ ] **Step 4: Commit**

```bash
git add js_engine/state_adapter.js js_engine/test_extract_instances.js
git commit -m "feat: add instToRichUnit() for per-instance feature extraction"
```

---

### Task 3: Update extractTrainingExample to use rich format

**Files:**
- Modify: `js_engine/matchup_clean.js` (function `extractTrainingExample`, ~line 1289)

- [ ] **Step 1: Create `extractTrainingExampleV2()` alongside existing function**

Keep `extractTrainingExample()` for backward compat. New function uses `instToRichUnit()`:

```javascript
function extractTrainingExampleV2(gameState, cardSet, plyIndex) {
    const instances = [];

    gameState.table.forEach((inst) => {
        if (inst.deadness !== C.DEADNESS_ALIVE) return;  // not inst.dead — match state_adapter.js pattern
        instances.push(instToRichUnit(inst));
    });

    const p0Mana = gameState.playerMana(C.COLOR_WHITE);
    const p1Mana = gameState.playerMana(C.COLOR_BLACK);

    // Supply — include ALL units in card set, even sold-out (supply=0).
    // in_card_set flag must persist so model knows the unit was available.
    const supply = {};
    for (let i = 0; i < gameState.cards.length; i++) {
        const card = gameState.cards[i];
        const ws = gameState.whiteSupply[i] || 0;
        const bs = gameState.blackSupply[i] || 0;
        const inSet = cardSet.includes(card.UIName) ? 1 : 0;
        // Include if unit has supply OR is in the card set (even if sold out)
        if (ws > 0 || bs > 0 || inSet) {
            supply[card.UIName] = [ws, bs, inSet];
        }
    }

    return {
        schema_version: "v2",
        ply_index: plyIndex,
        card_set: cardSet,
        instances: instances,   // NEW: per-instance list
        supply: supply,
        p0_resources: manaToResources(p0Mana),
        p1_resources: manaToResources(p1Mana),
        p0_attack: p0Mana.pool[C.MANA_A],
        p1_attack: p1Mana.pool[C.MANA_A],
        turn_number: gameState.numTurns,
        active_player: gameState.turn
    };
}
```

- [ ] **Step 2: Wire up V2 extraction via `--schema-v2` flag**

Add CLI flag `--schema-v2` to matchup_clean.js. When set, use `extractTrainingExampleV2()` instead of `extractTrainingExample()`. Default to v1 for backward compat.

- [ ] **Step 3: Test with a short matchup run**

```bash
node js_engine/matchup_clean.js --games 2 --export-training /tmp/test_v2/ --schema-v2
```

Inspect output JSONL: verify `instances` array contains rich per-instance data, each instance has all 10 state features + `name` + `owner`.

- [ ] **Step 4: Commit**

```bash
git add js_engine/matchup_clean.js
git commit -m "feat: add V2 per-instance training data extraction (--schema-v2)"
```

---

### Task 4: New schema contract (schema_v2.json)

**Files:**
- Create: `training/schema_v2.json`

- [ ] **Step 1: Write schema_v2.json**

```json
{
    "schema_version": "v2",
    "architecture": "deepsets",
    "num_units": 116,
    "unit_index_hash": "54cdda43ffa8a14f49bef59c7b735d26aa44dd569191d1e6fa82e8da2d73cfca",
    "token_dim": 55,
    "embedding_dim": 32,
    "num_static_properties": 13,
    "num_instance_features": 10,
    "num_supply_features": 3,
    "num_global_features": 14,
    "normalization_caps": {
        "gold": 20, "blue": 5, "red": 5, "green": 15,
        "energy": 10, "attack": 25, "turn_number": 50
    },
    "instance_features": [
        "owner", "is_constructing", "turns_until_ready", "is_blocking",
        "ability_used", "current_hp", "hp_fraction", "is_frozen",
        "lifespan_remaining", "stamina_remaining"
    ],
    "static_properties": [
        "buy_cost_gold", "buy_cost_green", "buy_cost_blue", "buy_cost_red",
        "buy_cost_energy", "base_health", "fragile", "default_blocking",
        "base_build_time", "base_lifespan", "base_attack", "has_ability",
        "max_stamina"
    ],
    "supply_features": ["p0_supply", "p1_supply", "in_card_set"],
    "global_features": [
        "p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
        "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
        "turn_number", "active_player"
    ],
    "label_strategies": {
        "A": "hard_binary_outcome_p0",
        "B": "temporal_sample_weight",
        "C": "elo_interpolated",
        "D": "neutral_prior"
    },
    "loss": "BCEWithLogitsLoss"
}
```

- [ ] **Step 2: Commit**

```bash
git add training/schema_v2.json
git commit -m "feat: add schema_v2.json for DeepSets per-instance format"
```

---

### Task 5: New vectorizer (vectorize_v2.py)

**Files:**
- Create: `training/vectorize_v2.py`
- Create: `training/tests/test_vectorize_v2.py`

- [ ] **Step 1: Write test_vectorize_v2.py**

Key tests:
```python
# Test 1: vectorize a minimal state (2 Drones, 1 Engineer per player)
#   - Verify instance count matches
#   - Verify each instance token is 10 floats (state only; embedding+props added at training time)
#   - Verify owner field is correct

# Test 2: verify supply encoding (3 floats × 116 types)

# Test 3: verify global features (14 floats, normalized)

# Test 4: unknown unit in instance list is silently dropped

# Test 5: lifespan -1 maps to 0

# Test 6: fragile unit HP calculation (health, not health-damage)

# Test 7: symmetry: mirror(state) swaps owners and supply correctly
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd training && python -m pytest tests/test_vectorize_v2.py -v
```

Expected: ImportError or similar — module doesn't exist yet.

- [ ] **Step 3: Write vectorize_v2.py**

Key differences from vectorize.py:
- **Input**: same JSONL but with `schema_version: "v2"` records containing `instances` array
- **HDF5 output structure**:
  - `instance_features`: float32, shape `(N, MAX_INSTANCES, 10)` — padded, per-record
  - `instance_unit_ids`: uint8, shape `(N, MAX_INSTANCES)` — unit type index per instance (for embedding lookup)
  - `instance_counts`: uint16, shape `(N,)` — actual instance count before padding
  - `supply`: float32, shape `(N, 116, 3)` — [p0_sup, p1_sup, in_set] per type
  - `globals`: float32, shape `(N, 14)`
  - Labels: same 4 strategies as v1
  - Metadata: same as v1 (replay_code, ply_index, etc.)
- **MAX_INSTANCES**: start with 200 total across both players (padded with zeros). Spec estimates 80-100 per player; 200 provides headroom. Validate against actual replay data before large-scale training — bump to 256 if needed.
- **Instance ordering**: P0 units first, then P1 units (within each player, order doesn't matter for DeepSets — but deterministic ordering helps debugging)
- **Property vectors are NOT stored in HDF5** — they're static per unit type and loaded from `property_table.json` at training time

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd training && python -m pytest tests/test_vectorize_v2.py -v
```

- [ ] **Step 5: Test on real data**

```bash
python training/vectorize_v2.py --input training/data/test_raw_states.jsonl --output /tmp/test_v2.h5 --schema training/schema_v2.json
```

(Requires V2 JSONL input — generate a small test file first with the `--schema-v2` matchup runner from Task 3.)

- [ ] **Step 6: Commit**

```bash
git add training/vectorize_v2.py training/tests/test_vectorize_v2.py
git commit -m "feat: add vectorize_v2.py for DeepSets per-instance HDF5 format"
```

---

## Chunk 2: PyTorch DeepSets Model

### Task 6: DeepSets model implementation

**Files:**
- Create: `training/model_deepsets.py`
- Create: `training/tests/test_model_deepsets.py`

- [ ] **Step 1: Write test_model_deepsets.py**

```python
# Test 1: model forward pass with random data
#   - batch_size=4, max_instances=128, instance_features=10, supply=(116,3), globals=14
#   - output shape: (4, 1) — raw logits

# Test 2: permutation invariance
#   - shuffle instance order within a sample
#   - verify output is identical (within float tolerance)

# Test 3: zero-padded instances don't affect output
#   - state with 5 real instances + 123 zero-padded
#   - vs same 5 instances + 0 zero-padded (via instance_counts mask)
#   - verify outputs match

# Test 4: symmetry augmentation
#   - swap owner labels, swap P0/P1 supply, swap P0/P1 globals
#   - verify value(original) + value(mirror) ≈ 0 (raw logit space)
#   - (not exactly 0 due to embedding asymmetry, but close for untrained model)

# Test 5: parameter count matches spec (~171K)

# Test 6: gradient flows through all components
#   - loss.backward(), verify all parameters have non-None gradients
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd training && python -m pytest tests/test_model_deepsets.py -v
```

- [ ] **Step 3: Write model_deepsets.py**

```python
class PrismataDeepSets(nn.Module):
    def __init__(self, num_units=116, d_embed=32, num_properties=13,
                 num_instance_features=10, encoder_hidden=128,
                 supply_hidden=32, value_hidden=256, dropout=0.1):
        super().__init__()

        # Unit-type embedding (learned)
        self.unit_embedding = nn.Embedding(num_units, d_embed)

        # Shared instance encoder
        token_dim = d_embed + num_properties + num_instance_features  # 55
        self.instance_encoder = nn.Sequential(
            nn.Linear(token_dim, encoder_hidden),
            nn.ReLU(),
            nn.Linear(encoder_hidden, encoder_hidden),
            nn.ReLU()
        )

        # Supply encoder (separate pathway)
        self.supply_encoder = nn.Sequential(
            nn.Linear(3, supply_hidden),
            nn.ReLU(),
            nn.Linear(supply_hidden, supply_hidden),
            nn.ReLU()
        )

        # Value MLP
        # Input: P0_pool + P1_pool + supply_pool + globals
        value_input_dim = encoder_hidden * 2 + supply_hidden + 14
        self.value_head = nn.Sequential(
            nn.Linear(value_input_dim, value_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(value_hidden, value_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(value_hidden, 1)
        )

        # Static property table (registered as buffer, not parameter)
        # Shape: (num_units, num_properties) — loaded from property_table.json
        self.register_buffer('property_table', torch.zeros(num_units, num_properties))

    def load_property_table(self, path):
        """Load static property vectors from property_table.json."""
        import json
        with open(path) as f:
            data = json.load(f)
        table = torch.zeros(len(data['units']), data['num_properties'])
        for name, info in data['units'].items():
            table[info['index']] = torch.tensor(info['properties'], dtype=torch.float32)
        self.property_table.copy_(table)

    def forward(self, instance_features, instance_unit_ids, instance_counts,
                supply, globals_vec):
        """
        Args:
            instance_features: (B, MAX_INST, 10) — per-instance state features
            instance_unit_ids: (B, MAX_INST) — unit type index per instance (long)
            instance_counts:   (B,) — actual instance count per sample
            supply:            (B, 116, 3) — [p0_sup, p1_sup, in_set] per type
            globals_vec:       (B, 14) — global features

        Returns:
            value_logit: (B, 1) — raw logit for P(P0 wins)
        """
        B, MAX_INST, _ = instance_features.shape

        # Build mask for real (non-padded) instances
        idx = torch.arange(MAX_INST, device=instance_features.device).unsqueeze(0)  # (1, MAX_INST)
        mask = idx < instance_counts.unsqueeze(1)  # (B, MAX_INST)

        # Look up embeddings and properties for each instance
        embeddings = self.unit_embedding(instance_unit_ids)  # (B, MAX_INST, d_embed)
        properties = self.property_table[instance_unit_ids]   # (B, MAX_INST, 13)

        # Concatenate token: [embedding | properties | instance_state]
        tokens = torch.cat([embeddings, properties, instance_features], dim=-1)  # (B, MAX_INST, 55)

        # Encode all instances through shared encoder
        encoded = self.instance_encoder(tokens)  # (B, MAX_INST, 128)

        # Zero out padded instances
        encoded = encoded * mask.unsqueeze(-1).float()  # (B, MAX_INST, 128)

        # Pool by owner: owner is feature[0] of instance_features
        owner = instance_features[:, :, 0]  # (B, MAX_INST), 0=P0, 1=P1
        p0_mask = (mask & (owner < 0.5)).unsqueeze(-1).float()   # (B, MAX_INST, 1)
        p1_mask = (mask & (owner >= 0.5)).unsqueeze(-1).float()  # (B, MAX_INST, 1)

        p0_pool = (encoded * p0_mask).sum(dim=1)  # (B, 128)
        p1_pool = (encoded * p1_mask).sum(dim=1)  # (B, 128)

        # Supply encoding — NOTE: ~93 types have [0,0,0] input, but bias terms
        # mean each contributes a constant to the sum. This is a learned constant
        # offset and shouldn't hurt training, but masking zero-input types is a
        # Phase 3 ablation candidate if supply signal appears weak.
        supply_flat = supply.view(B * 116, 3)
        supply_encoded = self.supply_encoder(supply_flat).view(B, 116, -1)  # (B, 116, 32)
        supply_pool = supply_encoded.sum(dim=1)  # (B, 32)

        # Combine and predict
        combined = torch.cat([p0_pool, p1_pool, supply_pool, globals_vec], dim=-1)  # (B, 302)
        value_logit = self.value_head(combined)  # (B, 1)

        return value_logit
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd training && python -m pytest tests/test_model_deepsets.py -v
```

- [ ] **Step 5: Commit**

```bash
git add training/model_deepsets.py training/tests/test_model_deepsets.py
git commit -m "feat: add PrismataDeepSets model (shared encoder + sum pooling)"
```

---

### Task 7: Update training script for DeepSets

**Files:**
- Modify: `training/train.py` — add DeepSets data loading and model selection

- [ ] **Step 1: Add V2 HDF5 dataset class**

Add `H5DatasetV2` class to train.py (or a new `dataset_v2.py`) that loads the new HDF5 format:

```python
class H5DatasetV2(Dataset):
    """Load DeepSets per-instance HDF5 data."""
    def __init__(self, h5_path, label_strategy='A', property_table_path=None):
        self.h5 = h5py.File(h5_path, 'r')
        self.instance_features = self.h5['instance_features']    # (N, MAX_INST, 10)
        self.instance_unit_ids = self.h5['instance_unit_ids']    # (N, MAX_INST)
        self.instance_counts = self.h5['instance_counts']        # (N,)
        self.supply = self.h5['supply']                          # (N, 116, 3)
        self.globals = self.h5['globals']                        # (N, 14)
        self.labels = self.h5[f'label_{label_strategy}']         # (N,)
        # ... label_B_weight if needed

    def __len__(self):
        return self.instance_features.shape[0]

    def __getitem__(self, idx):
        return {
            'instance_features': torch.tensor(self.instance_features[idx], dtype=torch.float32),
            'instance_unit_ids': torch.tensor(self.instance_unit_ids[idx], dtype=torch.long),
            'instance_counts': torch.tensor(self.instance_counts[idx], dtype=torch.long),
            'supply': torch.tensor(self.supply[idx], dtype=torch.float32),
            'globals': torch.tensor(self.globals[idx], dtype=torch.float32),
            'label': torch.tensor(self.labels[idx], dtype=torch.float32),
        }
```

- [ ] **Step 2: Add `--model deepsets` CLI flag to train.py**

When `--model deepsets`:
- Use `H5DatasetV2` instead of `H5Dataset`
- Instantiate `PrismataDeepSets` instead of `PrismataNet`
- Call `model.load_property_table(property_table_path)`
- Training loop stays the same (BCE loss on value logit)

- [ ] **Step 3: Smoke test training on small dataset**

```bash
# Generate small V2 dataset first (from Task 3+5):
node js_engine/matchup_clean.js --games 5 --export-training /tmp/smoke_v2/ --schema-v2
python training/vectorize_v2.py --input /tmp/smoke_v2/training_data_w0.jsonl --output /tmp/smoke_v2.h5

# Train for 2 epochs:
python training/train.py --model deepsets --data /tmp/smoke_v2.h5 --property-table training/property_table.json --epochs 2 --batch-size 4
```

Verify: loss decreases, no crashes, model checkpoint saved.

- [ ] **Step 4: Commit**

```bash
git add training/train.py
git commit -m "feat: add DeepSets model support to training script (--model deepsets)"
```

---

## Chunk 3: C++ Inference and Weight Export

### Task 8: New weight export format

**Files:**
- Create: `training/export_weights_v2.py`
- Create: `training/tests/test_export_v2.py`

- [ ] **Step 1: Write test_export_v2.py**

```python
# Test 1: export a randomly initialized PrismataDeepSets model
#   - verify binary file is created
#   - verify header contains correct dimensions

# Test 2: round-trip verification
#   - export model weights
#   - load them back in pure numpy
#   - run forward pass on same input
#   - verify outputs match PyTorch to 4+ decimal places

# Test 3: verify all expected tensors are present
#   - unit_embedding (116, 32)
#   - instance_encoder: linear1_w (128, 55), linear1_b (128), linear2_w (128, 128), linear2_b (128)
#   - supply_encoder: linear1_w (32, 3), linear1_b (32), linear2_w (32, 32), linear2_b (32)
#   - value_head: linear1_w (256, 302), linear1_b (256), linear2_w (256, 256), linear2_b (256), linear3_w (1, 256), linear3_b (1)
```

- [ ] **Step 2: Run tests, verify they fail**

- [ ] **Step 3: Write export_weights_v2.py**

Binary format (new "DSN" format):
```
Header (9 × uint32):
  magic:          0x44534E32  ("DSN2")
  version:        2
  num_units:      116
  d_embed:        32
  num_properties: 13
  encoder_hidden: 128
  supply_hidden:  32
  value_hidden:   256
  num_tensors:    <count>

Tensors (in fixed order):
  1. unit_embedding.weight     (116, 32)
  2. instance_encoder.0.weight (128, 55)
  3. instance_encoder.0.bias   (128,)
  4. instance_encoder.2.weight (128, 128)
  5. instance_encoder.2.bias   (128,)
  6. supply_encoder.0.weight   (32, 3)
  7. supply_encoder.0.bias     (32,)
  8. supply_encoder.2.weight   (32, 32)
  9. supply_encoder.2.bias     (32,)
  10-15. value_head weights/biases (3 layers × weight + bias)

Each tensor: name_len(uint32) + name(bytes) + ndims(uint32) + shape(ndims × uint32) + data(float32[])
```

- [ ] **Step 4: Run tests, verify they pass**

- [ ] **Step 5: Commit**

```bash
git add training/export_weights_v2.py training/tests/test_export_v2.py
git commit -m "feat: add DeepSets weight exporter (DSN2 binary format)"
```

---

### Task 9: C++ NeuralNet rewrite

**Files:**
- Modify: `source/ai/NeuralNet.h` — new data structures
- Modify: `source/ai/NeuralNet.cpp` — ground-up inference rewrite

This is the largest single task. The current `NeuralNet.cpp` (~550 lines) gets substantially rewritten.

- [ ] **Step 1: Update NeuralNet.h with DeepSets structures**

Replace existing structs with:

```cpp
// Linear layer (reuse existing)
struct LinearLayer { ... };  // unchanged

// DeepSets architecture components
struct DeepSetsConfig
{
    int num_units;          // 116
    int d_embed;            // 32
    int num_properties;     // 13
    int num_instance_features; // 10
    int encoder_hidden;     // 128
    int supply_hidden;      // 32
    int value_hidden;       // 256
};

class NeuralNet
{
    DeepSetsConfig          _config;

    // Unit-type embedding table (num_units × d_embed)
    std::vector<float>      _embedding_table;

    // Static property table (num_units × num_properties) — loaded from property_table.json
    std::vector<float>      _property_table;

    // Shared instance encoder (2 linear layers)
    LinearLayer             _enc_linear1;    // (token_dim → encoder_hidden)
    LinearLayer             _enc_linear2;    // (encoder_hidden → encoder_hidden)

    // Supply encoder (2 linear layers)
    LinearLayer             _sup_linear1;    // (3 → supply_hidden)
    LinearLayer             _sup_linear2;    // (supply_hidden → supply_hidden)

    // Value head (3 linear layers)
    LinearLayer             _val_linear1;    // (302 → value_hidden)
    LinearLayer             _val_linear2;    // (value_hidden → value_hidden)
    LinearLayer             _val_linear3;    // (value_hidden → 1)

    // Unit index mapping
    std::vector<int>        _cardTypeToUnitIndex;

    // ... methods
};
```

- [ ] **Step 2: Implement `loadWeights()` for DSN2 format**

Read the new binary format. Parse header, validate magic/version, load each tensor into the corresponding LinearLayer or embedding table.

- [ ] **Step 3: Implement `loadPropertyTable()`**

Read `training/property_table.json` and populate `_property_table` (116 × 13 floats).

- [ ] **Step 4: Implement `evaluate()` with DeepSets forward pass**

```cpp
float NeuralNet::evaluateValue(const GameState & state)
{
    // Accumulators (zero-initialized per call)
    float p0_pool[ENCODER_HIDDEN] = {0};
    float p1_pool[ENCODER_HIDDEN] = {0};
    float supply_pool[SUPPLY_HIDDEN] = {0};

    // 1. Process each unit instance on the board
    for (each alive card in state) {
        int unitIdx = _cardTypeToUnitIndex[card.getType().getID()];
        if (unitIdx < 0) continue;  // unknown unit type, skip

        // Build token: [embedding(32) | properties(13) | state(10)] = 55 floats
        float token[TOKEN_DIM];
        // ... copy embedding from _embedding_table[unitIdx * d_embed]
        // ... copy properties from _property_table[unitIdx * num_properties]
        // ... fill instance state features from card/game state

        // Forward through shared encoder
        float hidden1[ENCODER_HIDDEN];
        linearForwardReLU(_enc_linear1, token, hidden1);
        float encoded[ENCODER_HIDDEN];
        linearForwardReLU(_enc_linear2, hidden1, encoded);

        // Accumulate into owner's pool
        float* pool = (card.getPlayer() == 0) ? p0_pool : p1_pool;
        for (int i = 0; i < ENCODER_HIDDEN; i++)
            pool[i] += encoded[i];
    }

    // 2. Process supply
    for (int u = 0; u < NUM_UNITS; u++) {
        float sup_input[3] = { p0_supply[u], p1_supply[u], in_card_set[u] };
        float sup_h1[SUPPLY_HIDDEN];
        linearForwardReLU(_sup_linear1, sup_input, sup_h1);
        float sup_enc[SUPPLY_HIDDEN];
        linearForwardReLU(_sup_linear2, sup_h1, sup_enc);
        for (int i = 0; i < SUPPLY_HIDDEN; i++)
            supply_pool[i] += sup_enc[i];
    }

    // 3. Build combined vector [p0_pool | p1_pool | supply_pool | globals]
    float combined[COMBINED_DIM];  // 128+128+32+14 = 302
    // ... concatenate

    // 4. Value MLP
    float vh1[VALUE_HIDDEN], vh2[VALUE_HIDDEN], logit[1];
    linearForwardReLU(_val_linear1, combined, vh1);
    linearForwardReLU(_val_linear2, vh1, vh2);
    linearForward(_val_linear3, vh2, logit);  // no ReLU on final layer

    // sigmoid → [0,1] → map to [-1,1] for Eval.cpp compatibility
    float prob = 1.0f / (1.0f + expf(-logit[0]));
    return 2.0f * prob - 1.0f;
}
```

- [ ] **Step 5a: Add `abilityUsedThisTurn()` getter to Card.h**

Add public getter in `source/engine/Card.h` after `wasBreached()`:
```cpp
    bool abilityUsedThisTurn() const { return m_abilityUsedThisTurn; }
```

- [ ] **Step 5b: Extract instance state features from GameState**

Map C++ card properties to the 10 instance features:

```cpp
void extractInstanceFeatures(const Card & card, int unitIdx, float* out) {
    // Getter names verified against source/engine/Card.h
    out[0] = (float)card.getPlayer();                                    // owner
    out[1] = card.isUnderConstruction() ? 1.0f : 0.0f;                  // is_constructing
    out[2] = (float)std::max(card.getConstructionTime(), card.getCurrentDelay()); // turns_until_ready
    // NOTE: canBlock() checks capability, not assignment. Use m_abilityUsedThisTurn to distinguish.
    // Requires adding public getter to Card.h: bool abilityUsedThisTurn() const { return m_abilityUsedThisTurn; }
    out[3] = (card.getStatus() == CardStatus::Assigned && !card.abilityUsedThisTurn()) ? 1.0f : 0.0f; // is_blocking
    out[4] = card.abilityUsedThisTurn() ? 1.0f : 0.0f; // ability_used

    float baseHP = _property_table[unitIdx * NUM_PROPS + 5];  // base_health
    bool fragile = _property_table[unitIdx * NUM_PROPS + 6] > 0.5f;
    float currentHP = fragile ? (float)card.currentHealth() : (float)(card.currentHealth() - card.getDamageTaken());
    out[5] = std::max(0.0f, currentHP);                                  // current_hp
    out[6] = baseHP > 0 ? std::max(0.0f, currentHP) / baseHP : 0.0f;    // hp_fraction
    out[7] = card.currentChill() > 0 ? 1.0f : 0.0f;                     // is_frozen (also: card.isFrozen())

    int lifespan = card.getCurrentLifespan();                            // Card::getCurrentLifespan(), NOT CardType::getLifespan()
    out[8] = lifespan < 0 ? 0.0f : (float)std::max(0, lifespan);        // lifespan_remaining
    out[9] = (float)card.getCurrentCharges();                            // stamina_remaining
}
```

**Note:** Exact C++ getter names must be verified against the actual `Card.h` / `GameState.h` API. The above uses plausible names — the implementer must check and adapt.

- [ ] **Step 6: Build and smoke test**

```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m
```

Run a quick evaluation test:
```bash
bin/Prismata_Testing_d.exe --suggest js_engine/_suggest_state.json --player PrismatAlpha_NN --think-time 1000
```

Verify: no crash, value output in expected range.

- [ ] **Step 7: Cross-language verification**

Using the same canonical game state:
1. Export weights from a trained model: `python training/export_weights_v2.py model.pt weights.bin`
2. Evaluate in Python: `python -c "import torch; model = ...; print(model(state))"`
3. Evaluate in C++: `bin/Prismata_Testing_d.exe --suggest js_engine/_suggest_state.json --player PrismatAlpha_NN --think-time 1000` (check the eval_pct value in output)
4. Compare: eval values must be directionally consistent. Exact numeric comparison requires adding a dedicated `--eval-state` CLI flag (optional future work).

- [ ] **Step 8: Commit**

```bash
git add source/engine/Card.h source/ai/NeuralNet.h source/ai/NeuralNet.cpp
git commit -m "feat: rewrite NeuralNet for DeepSets inference (DSN2 format)"
```

---

## Chunk 4: Integration and Validation

### Task 10: End-to-end pipeline test

- [ ] **Step 1: Generate V2 training data from matchup replays**

```bash
node js_engine/matchup_clean.js --games 50 --parallel 4 --export-training training/data/test_deepsets/ --schema-v2 --save-replays training/data/test_deepsets/replays/
```

- [ ] **Step 2: Vectorize to HDF5**

```bash
python training/vectorize_v2.py --input training/data/test_deepsets/training_data_w0.jsonl --output training/data/test_deepsets.h5
```

- [ ] **Step 3: Train for 10 epochs**

```bash
python training/train.py --model deepsets --data training/data/test_deepsets.h5 --property-table training/property_table.json --epochs 10 --batch-size 32 --lr 3e-4
```

Verify: training loss decreases, no NaN.

- [ ] **Step 4: Export weights and test in C++**

```bash
python training/export_weights_v2.py training/models/best_model.pt bin/asset/config/neural_weights_v2.bin
```

- [ ] **Step 5: Run a matchup with neural eval**

```bash
node js_engine/matchup_clean.js --player PrismatAlpha_NN --games 5 --think-time 3000
```

Verify: games complete without crashes, eval values are in expected range.

- [ ] **Step 6: Commit and tag**

```bash
# Don't commit large binary files (HDF5, .pt) — just tag the verified code state
git tag deepsets-v1
git commit --allow-empty -m "feat: end-to-end DeepSets pipeline verified (tag: deepsets-v1)"
```

---

## Dependency Graph

```
Task 1 (property table) ─────────────────────────┐
    ↓                                              │
Task 2 (instToRichUnit) → Task 3 (extractV2)      │
                               ↓                   │
Task 4 (schema_v2.json) → Task 5 (vectorize_v2) ←─┘
                               ↓
                          Task 6 (model_deepsets.py) → Task 7 (train.py update)
                               ↓
                          Task 8 (export_weights_v2) → Task 9 (C++ rewrite)
                               ↓
                          Task 10 (integration test)
```

Tasks 1, 2, and 4 can be done in parallel. Task 5 depends on Tasks 1, 3, and 4. Everything else is sequential.
