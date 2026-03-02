# Hyperparameter Experiment Plan: Tackling Value Network Overfitting

**Date:** 2026-02-17
**Status:** SUPERSEDED by hyperparameter-experiments-v2.md (which is now COMPLETE). This v1 plan ran 3 experiments with confounds (expert data mixed in, tanh mismatch unfixed). See v2 plan for clean results.
**Goal:** Fix severe overfitting in self-play value network training, achieve >20% WR vs OriginalHardestAI

---

## 1. Problem Statement

We are training a neural network to evaluate game states in Prismata (a turn-based perfect-information strategy card game with ~10^64 possible states). The network is used as a value function inside Alpha-Beta search — it predicts win probability from a given game state.

**The overfitting problem:** The model achieves best validation accuracy at **epoch 1** and then memorizes the training data. By epoch 3-9, training accuracy hits 98%+ while validation accuracy drops. This pattern is **identical** whether we train on 10K games or 63K games — more data alone does not fix it.

**Playing strength is poor:** The current model achieves only **~3% win rate** vs OriginalHardestAI (the handcrafted baseline), compared to ~10% for an earlier expert-trained model and Churchill's published result of 58.8% WR vs playout evaluation with a similar architecture.

---

## 2. Current Architecture & Training Configuration

### Model: PrismataNet (PyTorch)

```
Input: state vector [1785 features]
  - 161 unit types × 11 features each (counts by status: ready, exhausted, constructing, blocking, supply, in_card_set)
  - 14 global features (resources for each player, turn number, active player)
  - Features normalized: counts clamped to max (e.g., 20) and divided by max

Trunk (shared representation):
  Linear(1785 → 512) → ReLU
  × num_layers (default 2) residual blocks:
    Linear(512 → 512) → LayerNorm(512) → ReLU → Dropout(p) → Linear(512 → 512) → LayerNorm(512)
    + residual skip connection → ReLU

Value Head:
  Linear(512 → 128) → ReLU → Linear(128 → 1)
  Output: raw logit (unbounded). tanh applied only in C++ inference, NOT during training.
  Loss: MSE on raw logits vs targets of ±1 (or ±label_smooth)

Policy Head (currently unused — 13% accuracy, disabled via --value-only):
  Linear(512 → 256) → ReLU → Linear(256 → 161)
  Output: raw logits per unit type (buy counts)
  Loss: MSE on counts + 0.5 × BCE on binary "did buy"
```

**Total parameters:** ~2.4M (with hidden_dim=512, num_layers=2)

### Current Training Hyperparameters

| Parameter | Value | Notes |
|---|---|---|
| Optimizer | AdamW | Separate weight decay groups (bias/norm excluded) |
| Learning rate | 3e-4 | Peak LR after warmup |
| LR schedule | Linear warmup (5 epochs) → Cosine decay | Warmup: ~6e-5 → 3e-4; decay to floor of 1e-5 |
| Batch size | 512 | |
| Dropout | 0.1 | Applied in trunk residual blocks |
| Weight decay (L2) | 1e-4 | Only on weight params, not bias/norm |
| Label smoothing | 0.95 | Targets: ±1 → ±0.95 |
| Gradient clipping | 1.0 | Hard-coded max norm |
| Early stopping | patience=15 | Stops if val_value_loss doesn't improve for 15 epochs |
| Train/val split | 90/10 by game_id | game_id % 10 == 0 → validation (deterministic, no leakage) |
| Value-only mode | Yes | Policy head not trained |

### Training Data

| Metric | Value |
|---|---|
| Source | Self-play (AI vs itself using current neural eval) |
| Total records | ~6.57M positions |
| Total games | ~177K games |
| Records per game | ~37 (both players' turns, average game length ~18 turns) |
| Binary format | 7152 bytes/record (1785 float32 features + metadata) |
| Data-to-parameter ratio | ~2.7:1 |
| Win/loss balance | ~50/50 (self-play is symmetric) |

### Observed Overfitting Pattern

**Iteration 1 (10K games, 370K records):**
- Epoch 1: 76.9% val accuracy (BEST)
- Epoch 3: 98%+ train accuracy, val accuracy declining
- Early stopping triggered at epoch 16

**Iteration 2 (63K games, 2.3M records):**
- Epoch 1: 81.9% val accuracy (BEST)
- Epoch 3: 98%+ train accuracy, val accuracy declining
- Same pattern despite 6× more data

**Key observation:** The "best at epoch 1" pattern means epoch 1's effective LR during warmup (~6e-5) is the only safe learning rate. By epoch 2, the warmed-up LR (rising toward 3e-4) already causes memorization.

### Tournament Evaluation Results

| Model | Games | WR vs OriginalHardestAI | Notes |
|---|---|---|---|
| Expert-trained (57.7% val acc) | 64 | ~10% | UCT search |
| Self-play v2 (81.9% val acc) | 296 | ~4.1% | AB search |
| Self-play v2 (current eval) | 232 | ~3% | AB search, 3 parallel instances |

Higher validation accuracy is producing **worse** playing strength — a clear sign the model is learning spurious patterns rather than generalizable state evaluation.

---

## 3. Reference: What Churchill Did (Campbell & Churchill, 2019)

Paper: "Machine Learning State Evaluation in Prismata" (AIIDE 2019 Workshop)
Full thesis: Rory Campbell, MSc, Memorial University of Newfoundland, 2020

### Churchill's Architecture & Training

| Parameter | Churchill | Us | Gap |
|---|---|---|---|
| Architecture | Plain 2-layer MLP (no residual, no LayerNorm) | 2-layer ResNet + LayerNorm | Ours more complex |
| Hidden dim | 512 | 512 | Same |
| Activation | Unknown (likely ReLU) | ReLU | Same |
| Dropout | None documented | 0.1 | - |
| Weight decay | None documented | 1e-4 | - |
| **Learning rate** | **1e-5** | **3e-4** | **Ours is 30× higher** |
| Optimizer | Adam | AdamW | Similar |
| LR schedule | None documented | Warmup + cosine | - |
| Batch size | Not documented | 512 | - |
| **Training data** | **15M records (500K games)** | **6.5M (177K games)** | **2.3× less** |
| Parameter count | ~1.1M (estimate, no residual/norm) | ~2.4M | Ours 2× larger |
| Data-to-param ratio | ~13.6:1 | ~2.7:1 | **5× worse** |
| Training accuracy | ~90% | 98%+ (memorized) | Ours overfits |
| Input encoding | One-hot (max 40 per count) | Clamp-divide normalized | Different |
| C++ inference | Frugally Deep (Keras→C++) | Custom native | Different |
| Framework | TensorFlow/Keras | PyTorch | Different |

### Churchill's Results

| Matchup | Games | Win Rate |
|---|---|---|
| Neural eval vs WillScore (formula-based) | 12,800 | **66.4%** |
| Neural eval vs Playout eval | 12,800 | **58.8%** |

Key insight: Churchill used **no explicit regularization** — he relied entirely on massive data volume (15M records). His LR of 1e-5 is 30× lower than ours, which naturally limits how fast the model can memorize.

### Churchill's Self-Play Methodology

- Single iteration: MasterBot plays itself for 500K games
- MasterBot = Portfolio of 12 Partial Players + 3000ms UCT search
- No iterative improvement loop (not AlphaZero-style)
- Value targets: game outcome (+1 win, -1 loss) from current player's perspective

---

## 4. Reference: What Other Game AI Systems Do

### AlphaZero (DeepMind, 2018)

| Parameter | Value |
|---|---|
| Optimizer | SGD with momentum 0.9 |
| Batch size | 4,096 |
| Weight decay | 1e-4 |
| Dropout | **None** |
| LR schedule | Step decay: 0.2 → 0.02 → 0.002 → 0.0002 |
| Architecture | 19-39 residual blocks, 256 filters (convolutional) |
| Training data | Billions of positions from continuous self-play |
| Anti-overfitting | Massive data, batch normalization, replay buffer (1M most recent) |

### Leela Chess Zero (Lc0) — MOST RELEVANT PRECEDENT

Lc0 experienced **the exact same value head overfitting problem** we have.

**The problem:** Value head strongly overfit, causing visible strength regression. Each training position was seen ~12 times. Despite massive self-play data, the value head memorized positions rather than learning generalizable evaluations.

**Failed fixes:**
- Lowering LR (0.001 → 0.0005 cyclic to 0.0005 → 0.0001): Arrested progression but didn't reverse it
- Bug fixes: Temporary improvements that quickly regressed

**The fix that worked:** Reducing `value_loss_weight` from 1.0 to **0.25** caused immediate recovery of both value head quality and playing strength. Theory: the value head is extremely sensitive to overtraining; reducing its loss contribution effectively reduces the effective LR for the value head specifically.

**Key finding about sampling rate:** Lc0 analysis concluded that seeing each position once during training (sampling rate = 1.0) is at the **very top end of workable**. Adjacent positions in the same game are highly correlated, amplifying memorization. Earlier DeepMind papers specifically mentioned sampling **less than once per position**.

| Parameter | Value |
|---|---|
| value_loss_weight | 0.25 (was 1.0) |
| policy_loss_weight | 1.0 |
| LR | Cyclic 0.001/0.0005, later reduced |
| Batch size | 1,024 |
| Dropout | None |
| Optimizer | Adam |

### KataGo (Lightvector, 2019)

| Parameter | Value |
|---|---|
| Optimizer | SGD with momentum 0.9 |
| Per-sample LR | 6e-5 (per-batch: 256 × 6e-5 = 0.01536) |
| LR warmup | 3× reduction for first 5M samples |
| Weight decay | 3e-5 |
| Batch size | 256 |
| Gradient clipping | Yes |
| **Architecture progression** | **(6,96) → (10,128) → (15,192) → (20,256)** |
| Stochastic weight averaging | EMA with decay=0.75, every 250K samples |
| Gating | Candidate must win ≥100/200 games vs current net |
| Training data window | 250K initially, growing to 22M |

**Key innovation:** Progressive model scaling — start small, grow capacity as data accumulates. This prevents overfitting in early stages when data is limited.

**Auxiliary targets as regularization:** Opponent's next move prediction (weight=0.15), score prediction, territory/ownership prediction. These multi-task targets prevent the value head from memorizing.

---

## 5. Root Cause Analysis

Based on the research, the overfitting likely has **multiple contributing causes**:

### Cause 1: Learning Rate Too High (HIGH CONFIDENCE)
Churchill's LR is 30× lower (1e-5 vs 3e-4). Our warmup schedule means epoch 1 trains at ~6e-5 (close to Churchill's), which is why epoch 1 is always the best. By epoch 2 the LR rises to ~1.2e-4 and memorization begins.

### Cause 2: Insufficient Data-to-Parameter Ratio (HIGH CONFIDENCE)
Churchill had ~13.6:1 (15M records / 1.1M params). We have ~2.7:1 (6.5M records / 2.4M params). Our model has 5× less data per parameter. With 2.4M parameters and 6.5M records, the model has enough capacity to memorize a significant fraction of the training set.

### Cause 3: Temporal Correlation in Training Data (MEDIUM CONFIDENCE)
Per Lc0's analysis: adjacent positions in the same game are highly correlated. With ~37 positions per game and position-level shuffling, the model can "cheat" by learning game-specific patterns (e.g., "this combination of unit counts = this specific game = this outcome") rather than generalizable evaluation.

### Cause 4: No Regularization Beyond Dropout 0.1 (MEDIUM CONFIDENCE)
Churchill needed no regularization because data volume was sufficient. With 2.3× less data and 2× more parameters, we need explicit regularization that Churchill could skip.

### Cause 5: Architecture Overly Expressive (LOW-MEDIUM CONFIDENCE)
Residual connections + LayerNorm make optimization easier, which paradoxically makes memorization easier too. Churchill's plain MLP with no skip connections or normalization has a harder time fitting noise.

---

## 6. Experiment Plan

### Design Principles
- **One variable at a time** where possible (exceptions noted)
- **All runs use current ~6.5M records** (~177K games) for consistency
- **Each run takes ~30 min on CPU** (AMD Ryzen 7 5700X3D)
- **Results logged to** `training/runs/{timestamp}.json` (per-epoch metrics, all hyperparameters)
- **Primary metric:** `val_value_loss` (lower = better)
- **Secondary metric:** `best_epoch` (higher = less overfitting)
- **Ultimate metric:** WR vs OriginalHardestAI (requires export → rebuild → tournament, only for top candidates)

### Baseline

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 3e-4 --patience 15 \
  --dropout 0.1 --weight-decay 1e-4 --label-smooth 0.95 --warmup-epochs 5
```

**Known result:** 81.9% val accuracy, best at epoch 1, memorizes by epoch 3.

---

### Experiment 1: Learning Rate (Highest Priority)

**Hypothesis:** Our LR of 3e-4 is far too high. Churchill used 1e-5 and didn't overfit. Reducing LR will spread learning across more epochs and reduce memorization.

**Rationale:** The "best at epoch 1" pattern directly correlates with LR warmup — epoch 1's effective LR (~6e-5) is close to Churchill's 1e-5. All experiments in this group remove warmup to isolate the LR effect.

```bash
# E1a: Match Churchill's exact LR (1e-5)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-5 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0

# E1b: Intermediate LR (3e-5, 10× lower than current)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 3e-5 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0

# E1c: Moderate reduction (1e-4, 3× lower than current)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0
```

**Success criteria:**
- Best epoch moves from 1 to 5+ (learning is distributed across epochs)
- Val loss curve stays flat or improves for multiple epochs before degrading
- Val accuracy at best epoch ≥ 82% (at least matching current)

**Risk:** LR=1e-5 may be too slow for our architecture (Churchill had a simpler MLP). If val accuracy is significantly lower than baseline, the model is underfitting at this LR.

---

### Experiment 2: Regularization Strength

**Hypothesis:** With 5× less data per parameter than Churchill, we need stronger explicit regularization.

```bash
# E2a: Higher dropout (0.3, from small-data best practices)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --dropout 0.3 --weight-decay 1e-4 --warmup-epochs 0

# E2b: Higher weight decay (10×, compensating for less data)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --dropout 0.1 --weight-decay 1e-3 --warmup-epochs 0

# E2c: Combined — low LR + high dropout + high weight decay
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 3e-5 --patience 20 \
  --dropout 0.25 --weight-decay 5e-4 --warmup-epochs 0
```

**Success criteria:** Train/val accuracy gap narrows (currently ~16% at epoch 3). Best epoch moves later.

**Risk:** Over-regularization → underfitting (val accuracy drops below 75%). If this happens, the model needs more capacity or more data, not more regularization.

---

### Experiment 3: Model Capacity (KataGo-Inspired)

**Hypothesis:** Our model is too large for our data. KataGo's progressive scaling approach suggests starting with a smaller model and growing with data.

**Parameter counts (approximate):**
- hidden_dim=512, num_layers=2: ~2.4M params → 2.7:1 data ratio
- hidden_dim=256, num_layers=2: ~700K params → 9.4:1 data ratio
- hidden_dim=128, num_layers=2: ~230K params → 28.6:1 data ratio

```bash
# E3a: 256 hidden (halve capacity, improve data ratio to ~9:1)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --hidden-dim 256 --num-layers 2 --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0

# E3b: 256 hidden + stronger regularization
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 3e-5 --patience 20 \
  --hidden-dim 256 --num-layers 2 --dropout 0.2 --weight-decay 5e-4 --warmup-epochs 0

# E3c: 128 hidden (aggressive reduction, 28:1 data ratio)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --hidden-dim 128 --num-layers 2 --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0
```

**Important note:** Changing hidden_dim requires re-exporting weights and rebuilding the C++ exe (the binary weight header encodes hidden_dim). This is straightforward:
```bash
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
# Then rebuild the solution
```

**Success criteria:** Train accuracy peaks lower (closer to val accuracy), training curve is smoother, best epoch is later.

**Risk:** Too small → underfitting. 128 hidden may not have enough capacity for 1785 input features. If val accuracy drops below 70%, the model is too small.

---

### Experiment 4: Batch Size

**Hypothesis:** Smaller batches provide implicit regularization through gradient noise, finding flatter minima that generalize better (Keskar et al., 2017).

```bash
# E4a: Batch 128 (4× smaller, more gradient noise)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 128 --lr 1e-4 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0

# E4b: Batch 64 (8× smaller, maximum gradient noise)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 64 --lr 5e-5 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0
```

**Note:** Smaller batches = more gradient updates per epoch = slower wall-clock time. Batch 64 will take ~8× longer per epoch than batch 512. LR should generally scale down with batch size (linear scaling rule).

**Success criteria:** Smoother validation loss curve, later best epoch.

---

### Experiment 5: Label Smoothing

**Hypothesis:** Current label_smooth=0.95 maps ±1 → ±0.95. The model learns to output extreme logits. Softer targets may reduce memorization.

```bash
# E5a: Aggressive smoothing (targets ±0.85)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 20 \
  --dropout 0.1 --weight-decay 1e-4 --label-smooth 0.85 --warmup-epochs 0
```

**Rationale:** With targets at ±0.85 instead of ±0.95, the model doesn't need to push logits as far, reducing the pressure to memorize exact outcomes.

---

### Experiment 6: Best Combination

After running experiments 1-5, combine the best settings from each:

```bash
# E6: Combined best settings (placeholder — fill in after experiments 1-5)
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size <best> --lr <best> --patience 20 \
  --hidden-dim <best> --num-layers 2 --dropout <best> --weight-decay <best> \
  --label-smooth <best> --warmup-epochs 0
```

---

## 7. Execution Order & Time Budget

| Priority | ID | Experiment | Time | Why First |
|---|---|---|---|---|
| 1 | E1a | LR=1e-5, no warmup | ~30 min | Match Churchill, test biggest known gap |
| 2 | E1c | LR=1e-4, no warmup | ~30 min | Find sweet spot |
| 3 | E2c | LR=3e-5, dropout=0.25, WD=5e-4 | ~30 min | Multi-lever approach |
| 4 | E3a | hidden_dim=256, LR=1e-4 | ~20 min | Test capacity hypothesis |
| 5 | E4a | batch_size=128, LR=1e-4 | ~60 min | Test gradient noise |
| 6 | E6 | Best combination | ~30 min | Combine winners |

**Total: ~3.5 hours.** Can run E1a and E1c first (1 hour) and decide whether to continue based on results.

---

## 8. How to Compare Results

### Quick comparison script
```bash
python -c "
import json, glob, os
runs = sorted(glob.glob('training/runs/*.json'))[-15:]
print(f'{'File':40s} {'LR':>8s} {'DO':>5s} {'WD':>8s} {'HD':>4s} {'BS':>4s} {'BstEp':>5s} {'ValLoss':>8s} {'ValAcc':>7s}')
print('-' * 100)
for f in runs:
    d = json.load(open(f, encoding='utf-8-sig'))
    hp = d.get('hyperparameters', {})
    print(f'{os.path.basename(f):40s} {str(hp.get(\"lr\",\"?\")):>8s} {str(hp.get(\"dropout\",\"?\")):>5s} {str(hp.get(\"weight_decay\",\"?\")):>8s} {str(hp.get(\"hidden_dim\",\"?\")):>4s} {str(hp.get(\"batch_size\",\"?\")):>4s} {str(d.get(\"best_epoch\",\"?\")):>5s} {str(d.get(\"best_val_value_loss\",\"?\")):>8s} {str(round(d.get(\"epochs\",[[]])[d.get(\"best_epoch\",1)-1].get(\"val_value_acc\",0)*100,1) if d.get(\"epochs\") else \"?\"):>7s}')
"
```

### Tournament evaluation (for top 1-2 candidates only)
```bash
# Export weights
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin

# Rebuild (if hidden_dim changed)
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI/visualstudio/Prismata.sln" //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m

# Run tournament (from bin/ directory — takes ~2 hours for 200 games)
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing_d.exe
```

---

## 9. What NOT to Do (Anti-Patterns)

1. **Don't just add more data without fixing LR** — the 10K→63K increase (6× more data) didn't fix overfitting. More data helps, but the LR is the primary issue.

2. **Don't train for more epochs hoping it'll improve** — once the model memorizes, it won't recover. The validation loss curve is monotonically increasing after epoch 1.

3. **Don't remove LayerNorm or residual connections to "match Churchill"** — these architectural features help optimization and are unlikely to be the cause of overfitting. The LR difference is 30×; the architecture differences are second-order.

4. **Don't enable the policy head** — at 13% accuracy it just adds noise to the training signal. Policy training should wait until policy data quality improves.

5. **Don't use a learning rate schedule that increases LR** (i.e., warmup) — the evidence shows that the model's best performance is at the lowest LR during warmup. Any LR increase triggers memorization.

6. **Don't confuse validation accuracy with playing strength** — the current model has 82% val accuracy but only 3% WR. Higher val accuracy from a memorized model produces worse play. Focus on val_loss (continuous) not val_accuracy (binary threshold).

---

## 10. Future Directions (Post-Experiment)

### If experiments succeed (best_epoch > 5, val_loss improves):
1. Export best model, run tournament eval (target: >10% WR vs OriginalHardestAI)
2. Continue data generation toward 500K games (Churchill's data volume)
3. Retrain with more data using the winning hyperparameters
4. Consider progressive scaling: start with smaller model, grow as data increases (KataGo approach)

### If experiments fail (still overfitting at epoch 1):
1. **Position subsampling:** Use every Nth position per game (e.g., every 3rd) to reduce temporal correlation. This addresses the Lc0 finding about correlated adjacent positions.
2. **Input noise:** Add small Gaussian noise to continuous features during training (data augmentation analog).
3. **Simpler architecture:** Try a plain MLP (no residual, no LayerNorm) matching Churchill exactly.
4. **Mixed data:** Train on self-play + expert data together (`--expert-weight 0.3`). Expert data has different distribution characteristics that may break memorization patterns.
5. **Fundamentally different approach:** The self-play data may simply be too self-referential. The AI plays itself, learning to evaluate positions from games it created — a feedback loop that rewards consistency over correctness. Consider training on expert data (human 2000+ games) as a corrective signal.

---

## 11. Technical Notes

### Weight Export for Different Hidden Dims
The C++ binary weight format encodes `hidden_dim` in the header. If experiments show a smaller model is better, the export and C++ inference will work automatically — the C++ loader reads the header and allocates accordingly. No C++ code changes needed.

```bash
# Export works for any hidden_dim:
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
```

### Running Experiments in Parallel
Training is CPU-bound (~30 min per run). Only one training run at a time (uses all cores). However, tournament evaluation can run concurrently with training since it uses separate processes.

### Experiment Logging
All runs auto-save to `training/runs/{timestamp}.json` with:
- Full hyperparameter set
- Per-epoch metrics (train/val loss, accuracy, saturation fraction)
- Git hash at time of training
- Best epoch and best val loss
- Data statistics (record counts, game counts)

### Self-Play Data Continues Growing
The fleet (24 AWS + 8 Azure + 2 GCP + local) is generating ~177K games and growing. By the time experiments complete, there may be significantly more data available. Consider re-running the best configuration on the larger dataset.
