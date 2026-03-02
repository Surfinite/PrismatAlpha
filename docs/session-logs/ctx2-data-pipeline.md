## Context 2 — Data Pipeline, Feature Spec, and Golden-Vector Tool
**Status:** DONE
**Current task:** All deliverables complete
**Completed:**
- **Deliverable 1: `training/data/unit_index.json`** — 161 canonical display names from `cardLibrary.jso`, SHA-256 hash `2ec440f25ef669b001dceb0ae5bd5c52fbc22d4dd7e01b2acfbbedebc1f6cda1`. Zero UNK names in training data.
- **Deliverable 2: `training/FEATURES.md`** — Full feature spec: index ranges, names, normalization formulas, POV convention, percentile rationale
- **Deliverable 2: `training/schema.json`** — Machine-readable schema contract, feature_version=2, state_dim=1785 (161×11+14), unit_index_hash, normalization caps
- **Deliverable 3: Updated `training/vectorize.py`** — Uses canonical unit index, schema validation at startup, clamp-divide normalization on global features
- **Deliverable 3: Regenerated `training/data/train.pt` and `training/data/val.pt`** — 225,995 train + 25,111 val examples, state_dim=1785, schema_version=2
- **Deliverable 4: UNK report** — 0 UNK names in 251,106 examples (0.00%). All 116 unique replay names are canonical.
- **Deliverable 4: Value label distribution** — Win: 144,471 (57.5%), Loss: 105,514 (42.0%), Draw: 1,121 (0.4%). Mean=0.155, Std=0.986. NOT imbalanced (no >70% flag).
- **Deliverable 5: `tools/golden_vector.py`** — Comparison tool with self-test. Reads C++ feature dump + .desc companion, reconstructs Python features, compares L1/L2/max diff/top-10 indices. Self-test PASSED. Awaits C++ dump from Context 1 for cross-language validation.
**Blockers:**
- (none — ALL DONE)
**Key decisions/findings:**
- **state_dim = 1785** (161 units × 11 + 14 global features)
- **161 canonical units** from cardLibrary.jso (display names: UIName if present, else internal name)
- **0 UNK names** in 251,106 training examples — all 116 unique replay names are canonical
- **45 canonical names** never seen in training data (campaign/token/non-competitive) — reserved but zero-valued
- **Value labels: 57.5% win / 42.0% loss / 0.4% draw** — NOT imbalanced
- **Global feature normalization** uses clamp-then-divide with data-driven caps: gold/20, blue/5, red/5, green/15, energy/10, attack/25, turn/30
- Previous vectorize.py had NO normalization on global features (raw values) — new version normalizes to [0,1]
- Context 1 has already updated NeuralNet.cpp with matching normalization caps and schema validation
- **golden_vector.py known limitation**: .desc format doesn't distinguish CardStatus::Assigned (blocking) from exhausted via canUse=0. Both show as canUse=0 in the desc. The Python tool places them in exhausted (offset+1) while C++ places Assigned in blocking (offset+3). This will cause expected diffs on states with assigned blockers. For full match, Context 1 would need to add an "assigned" field to the .desc output.
- **Top 15 purchased units**: Drone (192K), Engineer (122K), Wall (80K), Forcefield (50K), Tarsier (41K), Conduit (33K), Blastforge (31K), Rhino (25K), Animus (17K), Steelsplitter (16K)
**Files delivered:**
- `training/data/unit_index.json` — canonical name→index mapping (161 units)
- `training/FEATURES.md` — feature specification document
- `training/schema.json` — machine-readable schema contract
- `training/vectorize.py` — updated with canonical index + normalization
- `training/data/train.pt` — 225,995 training examples (state_dim=1785)
- `training/data/val.pt` — 25,111 validation examples (state_dim=1785)
- `tools/golden_vector.py` — cross-language feature comparison tool
**Log:**
> Explored cardLibrary.jso, unit_index.json, vectorize.py, NeuralNet.cpp
> Parsed cardLibrary.jso → 161 unique display names, no collisions
> Scanned 251K training examples → 0 UNK, computed percentiles
> Wrote canonical unit_index.json (161 units, hash verified)
> Wrote FEATURES.md and schema.json (state_dim=1785, feature_version=2)
> **Contexts 1 and 3 UNBLOCKED** — schema.json and FEATURES.md delivered
> Updated vectorize.py with canonical index, schema validation, normalization
> Regenerated train.pt (225,995) and val.pt (25,111) — state_dim=1785, all checks passed
> Created tools/golden_vector.py with self-test — PASSED
> ALL DELIVERABLES COMPLETE
