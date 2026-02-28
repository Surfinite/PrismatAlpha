# Expert Data Training — New Context Prompt

## What You're Doing

Train the PrismataAI neural network on **expert replay data extracted via the faithful JS engine**. This is the first training run on CORRECT data — all previous models were trained on buggy C++ engine data (50% replay pass rate) and their win rates were meaningless.

## Background

The project uses a ResNet-style policy+value network for a game called Prismata. Previous models achieved up to 51.9% WR vs OriginalHardestAI but collapsed to ~11% when C++ engine bugs were fixed. We've now extracted training data using a faithful JavaScript engine transpiled from the original AS3 source code, producing high-quality state vectors.

## Data Ready to Train

Two vectorized datasets at `training/data_expert_1500_full/` and `training/data_expert_2000_full/`:

| Dataset | Location | Train | Val | State Dim |
|---|---|---|---|---|
| **1500+ rated** | `training/data_expert_1500_full/` | 1,331,339 | 148,547 | 1785 |
| **2000+ rated** | `training/data_expert_2000_full/` | 923,081 | 101,885 | 1785 |

Format: PyTorch `.pt` files with keys `states`, `policies`, `values`, `active_players`.

**NOTE**: A parallel context is extracting ~30K additional balance-validated pre-patch games. When complete, these will be combined and re-vectorized. Start training now with the 1500+ dataset — we can retrain with the expanded dataset later.

## Recommended Training Approach

### Step 1: Quick sanity check with overfit test
```bash
cd c:/libraries/PrismataAI
python training/train.py training/data_expert_1500_full training/models/expert_1500_overfit \
  --overfit-test --hidden-dim 256 --num-layers 3 --device xpu
```
This trains on a tiny subset to verify the architecture can learn. Should see loss dropping rapidly.

### Step 2: Full training run — R12 architecture (proven best)
```bash
python training/train.py training/data_expert_1500_full training/models/expert_1500_R12 \
  --epochs 100 --batch-size 512 --lr 2e-5 \
  --hidden-dim 256 --num-layers 3 \
  --dropout 0.20 --label-smooth 0.90 \
  --patience 15 --device xpu --num-workers 4
```

Architecture rationale: R12_smooth90 (256h/3L, lr=2e-5, d=0.20, s=0.90) was the T4 hyperparameter sweep winner (best val_loss=0.4875 among 12 configs). But it was previously limited to 500K records by RAM. Now training on the full 1.33M dataset.

### Step 3: Also try E2b architecture for comparison
```bash
python training/train.py training/data_expert_1500_full training/models/expert_1500_E2b \
  --epochs 100 --batch-size 512 --lr 1e-5 \
  --hidden-dim 256 --num-layers 2 \
  --patience 15 --device xpu --num-workers 4
```

E2b (256h/2L, lr=1e-5, no smoothing) held the WR record (28.9%) on buggy data with 2.3M records. Good baseline comparison against R12.

### Step 4: Export best weights
```bash
python training/export_weights.py training/models/expert_1500_R12/best_model.pt \
  bin/asset/config/neural_weights_expert_js.bin
```

### Step 5: Tournament evaluation
Edit `bin/asset/config/config.txt` to set up a tournament:
- Player 1: `PrismatAlpha_AB` (uses neural_weights_expert_js.bin)
- Player 2: `OriginalHardestAI` (baseline)
- At least 1,000 games for statistical significance

Run: `cd bin && ./Prismata_Testing.exe > tournament.log 2>&1`

## Key Gotchas

- **XPU training**: `--device xpu --num-workers 4` gives 3.2x speedup on Intel Arc B580. If XPU unavailable, CPU works fine (just slower).
- **RAM**: 1.33M examples fits in 32GB RAM without streaming. No need for `--streaming` flag.
- **best_model.pt gets overwritten**: Each run writes to the model directory. Use separate model dirs per experiment.
- **Label smoothing**: `--label-smooth 0.90` prevents tanh saturation for value head. R12 uses this; E2b doesn't.
- **Value-only mode**: `--value-only` skips policy head (policy accuracy is weak at 13%). Can try both ways.
- **Training lock**: Only one training job per model directory (lock file prevents conflicts).
- **Export requires all 26 tensors**: `export_weights.py` exports zero-initialized policy tensors for value-only models. C++ loader needs all 26.

## What Success Looks Like

- Val value accuracy > 60% (previous best was 57.7% on buggy data, but that model's WR collapsed)
- Val value loss < 0.45 (R12 got 0.4875 on 500K records — more data should improve this)
- After export + tournament: **any positive WR vs OriginalHardestAI** would be a genuine achievement, since this is the first model trained on correct data
- Compare R12 vs E2b to confirm which architecture works better with the larger dataset

## Files Reference

| File | Purpose |
|---|---|
| `training/train.py` | Main training script |
| `training/export_weights.py` | PyTorch → C++ binary weight format |
| `training/data_expert_1500_full/train.pt` | Training data (1.33M examples, 9.7GB) |
| `training/data_expert_1500_full/val.pt` | Validation data (148K examples, 1.1GB) |
| `training/schema.json` | Feature schema (state_dim=1785) |
| `bin/asset/config/config.txt` | Tournament configuration |
| `bin/asset/config/neural_weights.bin` | Current deployed weights (from buggy data) |
