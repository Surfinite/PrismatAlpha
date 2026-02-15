## Context 3 — Training Investigation + Infrastructure
**Status:** DONE — All deliverables complete, model trained and exported
**Current task:** None remaining

**Completed:**
- **Task A: Value head collapse diagnosed and FIXED** (train.py)
- **Task A: Pre-training label sanity check** (train.py `check_label_sanity()`)
- **Task A: Overfit test** — PASSES on both old AND new data (state_dim=1785)
- **Task A: Per-epoch logging** with both losses, saturation monitoring, value pred stats
- **Task A: Training config** — label smoothing, early stopping, experiment logging
- **Task B: Weight format documented** (docs/WEIGHT_FORMAT.md)
- **Task B: export_weights.py rewritten** with round-trip forward-pass verification
- **Task B: Experiment logging** (training/runs/<timestamp>.json per training run)
- **Task B: scripts/smoke_test.sh** (10 fixed-set games, crash/sanity check)
- **Task B: scripts/tournament.sh** (N games, CSV output, Wilson CI)
- **Compatibility fix:** `load_unit_index()` helper for new `{"version":..., "units":{...}}` format
- **FULL TRAINING COMPLETED** — best model at epoch 70, early stopped at epoch 80
- **WEIGHTS EXPORTED** — `neural_weights.bin` (8.4 MB), round-trip verified (max diff 2.38e-07)

### Training Results (Final)

| Metric | Value |
|---|---|
| Best epoch | 70 (early stopped at 80, patience=10) |
| Best val value loss | **0.000635** |
| Val value accuracy | **99.9%** (correctly predicts game winner) |
| Val policy accuracy | ~13.3% (exact buy set match) |
| Train value accuracy | 99.8% |
| Train policy accuracy | 14.1% |
| Tanh saturation | **0.0%** throughout all epochs |
| Value prediction range | [-0.79, +0.78] (healthy, no saturation) |
| Total wall time | 23.1 minutes (CPU, 8 workers) |
| Model parameters | 2,207,650 |
| Architecture | 2-layer ResNet, 512 hidden, dropout=0.1 |

**Training config used:**
```bash
python train.py --epochs 100 --lr 3e-4 --batch-size 512 \
  --policy-weight 0.5 --label-smooth 0.95 --patience 10 \
  --hidden-dim 512 --num-layers 2 --dropout 0.1
```

**Data:** 225,995 train + 25,111 val examples, state_dim=1785 (161 units × 11 + 14 global features), schema_version=2

**Exported weights:** `bin/asset/config/neural_weights.bin`
- 8.4 MB, 26 tensors, 161 unit names
- Header: state_dim=1785, num_units=161, hidden=512, layers=2
- Round-trip verification: max abs diff = 2.38e-07 (threshold: 1e-5) — **PASSED**

**Experiment log:** `training/runs/20260213_045023.json` (80 epochs of per-epoch metrics)

### Key decisions/findings:

### Value Head Collapse — ROOT CAUSE AND FIX

**Root cause: `nn.Tanh()` in value head Sequential causes gradient death with MSE loss.**

The overfit test confirmed this definitively:
- WITH Tanh in Sequential: model saturates to -1.0 within epoch 1, loss INCREASES from 0.998 to 1.799, predictions stuck at [-1.000, -1.000]. COMPLETELY broken.
- WITHOUT Tanh: loss drops from 0.993 to 0.0000 (100% reduction), predictions span [-0.97, +0.96]. PASSES.

**The fix:** Removed `nn.Tanh()` from `self.value_head` Sequential. The model now outputs raw logits during training. `tanhf()` is applied only at inference time in C++ (`NeuralNet.cpp` line 474/519), which already did this — so the C++ side needs NO changes.

### Compatibility Fix for New unit_index.json Format

Context 2's new `unit_index.json` uses wrapper format: `{"version": "...", "count": 161, "units": {"Drone": 0, ...}}`. Added `load_unit_index()` helper in train.py and export_weights.py to detect and handle both formats.

### Files Changed

| File | Changes |
|---|---|
| `training/train.py` | Removed Tanh from value_head, added: check_label_sanity(), --overfit-test, label smoothing, early stopping, saturation monitoring, per-epoch value prediction stats, experiment logging, load_unit_index(), changed default policy_weight from 0.25 to 0.5 |
| `training/export_weights.py` | Round-trip verification with numpy forward pass, load_unit_index() for new format |
| `docs/WEIGHT_FORMAT.md` | New file: full binary format spec for neural_weights.bin |
| `scripts/smoke_test.sh` | New file: runs 10 fixed-set games, asserts no crash |
| `scripts/tournament.sh` | New file: N games with configurable players, CSV output, Wilson CI |
| `bin/asset/config/neural_weights.bin` | New trained model weights (8.4 MB, state_dim=1785, 161 units) |
| `training/runs/20260213_045023.json` | Experiment log with 80 epochs of metrics |

**Log:**
> Started: Reading all source files and training data
> Completed: Data distribution analysis — value labels balanced, labels are fine
> Completed: Checkpoint analysis — epoch 5, val_value_loss=2.01, state_dict key mismatch
> Completed: Root cause diagnosis — tanh gradient death in value head
> Completed: FIX — removed nn.Tanh() from value_head Sequential
> Completed: Overfit test — PASSES (loss 0.993 → 0.000, range coverage 100.8%)
> Completed: All Task A deliverables (sanity check, overfit test, logging, config)
> Completed: All Task B deliverables (weight format doc, export verification, smoke/tournament scripts)
> Resumed: Blocker resolved — Context 2 delivered clean train.pt/val.pt (state_dim=1785)
> Fixed: train.py/export_weights.py load_unit_index() for new {"units": {...}} format
> Completed: Overfit test on NEW data PASSES (loss 1.17 → 0.000, coverage 101.2%)
> Completed: Full training — best val_value_loss=0.000635 at epoch 70, early stopped at 80
> Completed: Weight export — neural_weights.bin (8.4 MB), round-trip verified (diff 2.38e-07)
> Status: ALL DONE
