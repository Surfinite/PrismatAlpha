## Context 1 — C++ Feature Extraction Debug
**Status:** COMPLETE (all assigned tasks done)
**Phase 1:** COMPLETE
**Phase 2:** COMPLETE

---

### Phase 1 Summary: extractFeatures() Investigation

#### Key Finding: "All Zeros" Was a Misdiagnosis
The CLAUDE.md stated `extractFeatures()` produces an all-zero feature vector at runtime. **This was incorrect.** Running the actual Testing binary proved:
- **38 non-zero features** produced from a base-set game state (state_dim=1290, 116 units)
- Policy head differentiates units: `policy_nonzero=106/116`
- Value head functional: values of 0.06, -0.57, 0.72 across different states
- The N:-0.1 GUI observation was from a specific context, not a universal zero-vector bug

The "all zeros" was inferred from GUI N:-0.1 values matching Python all-zero-input behavior — never directly measured.

#### Bugs Found and Fixed

1. **Missing bounds checks** — unit feature writes and supply feature writes had no bounds validation against `_numUnits * 11`. Could cause out-of-bounds writes with mismatched weight files.
   - **Fix:** Added `if (base + 3 >= _numUnits * 11)` guard with skip + diagnostic logging
   - **Fix:** Added `if (base + 10 >= _numUnits * 11)` guard for supply features

2. **Global feature OOB writes** — Code wrote 14 global features unconditionally, but older weight files had state_dim sized for only 2 global features → 12 OOB writes.
   - **Fix:** Dynamic `numGlobalSlots = _stateDim - globalBase` check with conditional branching for 14-feature vs 2-feature layout

3. **No schema validation** — No check that weight file dimensions match training schema.
   - **Fix:** Added `validateSchema()` that loads `../training/schema.json` and checks `feature_version`, `state_dim`, and `unit_index_hash`

4. **State_dim layout validation** — Added to `loadWeights()`: validates `numGlobalFeatures = _stateDim - _numUnits * 11` is non-negative, warns if not 14 or 2

### Phase 2 Summary: Feature Schema Alignment

#### Completed Work

1. **Updated global feature normalization** to match FEATURES.md clamp_divide spec:
   ```
   p0_gold:   min(val, 20) / 20
   p0_blue:   min(val,  5) /  5
   p0_red:    min(val,  5) /  5
   p0_green:  min(val, 15) / 15
   p0_energy: min(val, 10) / 10
   p0_attack: min(val, 25) / 25
   (same for p1)
   turn:      min(val, 30) / 30
   active_player: raw (0 or 1)
   ```
   Previously used raw values. Now matches Python vectorize.py normalization.

2. **Added `dumpFeaturesToFile()`** — writes feature vector to binary `.bin` file + companion `.txt` with state description (units, resources, card set, dimensions). Used for cross-language golden-vector testing against Python.

3. **Added `stateDim()` accessor** to NeuralNet.h public interface.

4. **Verified build** — Full solution builds successfully with all changes via MSBuild.

5. **Verified runtime** — Testing binary shows:
   - Schema validation fires correctly: `"ERROR: state_dim mismatch! schema=1785, weights=1290"` (expected — weights not retrained yet)
   - Normalization working: energy=0.2 (was 2 raw, now min(2,10)/10)
   - 38 non-zero features still present, no regressions

6. **Updated test_features.cpp** — Fixed `"turn/50"` → `"turn/30"` label, replaced TODO schema check with full schema.json parsing (reads state_dim, num_units, num_global_features, feature_version and compares against loaded weight file), fixed stateDim references to use `net.stateDim()` accessor.

#### Out of Scope

- **Wire F5 → dumpFeaturesToFile()** — The function exists in NeuralNet.cpp but the GUI F5 handler is in `source/gui/GUIState_Play.cpp` which is NOT in Context 1's file ownership.

---

### Files Modified (Context 1 Ownership)

| File | Changes |
|---|---|
| `source/ai/NeuralNet.cpp` | Bounds checks, dynamic global slots, clamp_divide normalization, validateSchema(), dumpFeaturesToFile(), diagnostic logging |
| `source/ai/NeuralNet.h` | Added validateSchema() private, stateDim() public, dumpFeaturesToFile() public |
| `source/testing/test_features.cpp` | Created: 3 tests + schema validation + diagnostic dump (not wired into any vcxproj yet) |

Files READ but NOT modified: `source/ai/Eval.cpp`, `source/ai/Eval.h`

### Current Weight File State

The binary weight file on disk (`bin/asset/config/neural_weights.bin`) has:
- state_dim = 1290 (116 units × 11 + 14 global)
- 116 unit names, 256 hidden dim, 2 layers
- Does NOT match new schema (161 units, state_dim=1785)
- Needs retrain by Context 3 with new 161-unit index

### Dependencies on Other Contexts

- **From Context 2 (received):** `training/schema.json` and `training/FEATURES.md` — used to align C++ normalization
- **From Context 3 (pending):** Retrained weights with state_dim=1785 and 161-unit index — needed before neural net can produce meaningful output at the new dimensionality
- **To Context 3:** C++ extractFeatures() now matches FEATURES.md normalization; dumpFeaturesToFile() ready for golden-vector comparison

### Log
```
> Phase 1: Read all source files (NeuralNet.cpp/h, Eval.cpp/h, vectorize.py, etc.)
> Phase 1: Proved extractFeatures() NOT all-zeros (38/1290 non-zero) — misdiagnosis corrected
> Phase 1: Added bounds checks for unit and supply features
> Phase 1: Added dynamic global feature slot counting (14 vs 2 layout)
> Phase 1: Added state_dim layout validation in loadWeights()
> Phase 1: Added validateSchema() — loads schema.json, checks state_dim + feature_version
> Phase 1: Created test_features.cpp with 3 tests + diagnostic dump
> Phase 1: Full solution built and verified
> Phase 2: Updated extractFeatures() global features to clamp_divide normalization
> Phase 2: Added dumpFeaturesToFile() implementation
> Phase 2: Added stateDim() accessor
> Phase 2: Rebuilt and verified — schema validation fires, normalization correct
> RESUMED: Fixed test_features.cpp — "turn/50" → "turn/30", added schema.json parsing, fixed stateDim refs
> ALL TASKS COMPLETE
```
