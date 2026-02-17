# Hyperparameter Experiment Plan v2: Fixing Value Network Training

**Date:** 2026-02-17
**Status:** IN PROGRESS — v1 experiments completed (inconclusive), v2 Phase 0 not yet started
**Goal:** Fix overfitting + training/inference mismatch; achieve >20% WR vs OriginalHardestAI
**Revision:** Consolidated from v1 + six independent expert critiques

---

## 0. Prior Experiments (v1 Plan, Feb 17) — COMPLETED, INCONCLUSIVE

Three experiments were run from the v1 plan before v2 was finalized. They are useful data points but have significant confounds:

### What Was Run

| Exp | Config | Val Acc (Best) | LR | Warmup | Hidden | Records |
|-----|--------|---------|-----|--------|--------|---------|
| 1 | No warmup, flat LR | 75.1% (ep1) | 6e-5 | No | 512 | 1M |
| 2 | Strong regularization | 75.5% (ep1) | 3e-4 | Yes (5 ep) | 512 | 1M |
| 3 | Smaller model | 75.3% (ep1) | 3e-4 | Yes (5 ep) | 256 | 1M |

All three showed the same pattern: best at epoch 1, train accuracy 98%+ by epoch 3-4, val accuracy declining. All converged to ~75.3-75.5% val ceiling.

### Key Finding

Regularization strength and model capacity don't change the val accuracy ceiling with 1M records. The gap vs iter 2's 81.9% (2.3M records) suggests data volume matters.

### Why These Results Are Inconclusive

1. **Tanh mismatch not fixed (Cause 0)** — All experiments trained MSE on unbounded logits while C++ deploys with tanh. This is the v2 plan's #1 issue (unanimous across 6 reviewers) and was never tested.
2. **Expert data mixed in (unplanned confound)** — 226K expert examples at 20% effective weight were blended into all 3 runs. Prior iterations were pure self-play, making these not directly comparable.
3. **No tournament evaluation** — Zero WR data from any of these models. Val accuracy is a demonstrated poor proxy for strength (82% val → 3% WR).
4. **No step-level evaluation** — Only epoch-level metrics. "Best at epoch 1" may mean "best at step ~1500" but we can't tell.
5. **Exp 2 & 3 kept the broken LR** — Only Exp 1 used a low LR (6e-5). Exp 2 and 3 used 3e-4 with warmup, which was already known to cause rapid memorization.
6. **The "more data = better" conclusion is dangerous** — Going from iter 1 (77% val, 10% WR) to iter 2 (82% val, 3% WR) showed that higher val accuracy produces *worse* playing strength. Scaling data without fixing the training procedure may worsen this.

### What This Tells Us

- Regularization and model capacity are NOT the bottleneck (confirmed)
- Data volume does affect the val accuracy ceiling (confirmed)
- The loss function fix (Phase 0 below) is still untested and remains the top priority
- A streaming data loader is needed for full dataset access (useful infrastructure regardless)

### Logs

- `training/exp1_no_warmup.log` — Exp 1 (killed at epoch 9)
- `training/exp2_strong_reg.log` — Exp 2 (killed at epoch 8)
- `training/exp3_small_model.log` — Exp 3 (early stopped at epoch 16)

---

## 1. Problem Statement

We are training a neural network to evaluate game states in Prismata. The network predicts win probability and is used inside Alpha-Beta search.

**Three interacting problems:**

1. **Training/inference mismatch (BUG):** The model trains MSE on unbounded logits against ±0.95 targets, but applies `tanh` only at C++ inference time. The model is not trained on the function it deploys. This means calibration found during training is distorted by tanh at deployment, and the model is penalized for being too confident in the correct direction (a logit of +2.0 for a won position has *higher* loss than a logit of 0.0).

2. **Severe overfitting:** Best validation performance occurs at epoch 1 regardless of dataset size (10K→63K games made no difference). Training accuracy hits 98%+ by epoch 3 while validation degrades.

3. **Validation doesn't predict strength:** The self-play v2 model achieves 81.9% validation accuracy but only ~3% win rate vs OriginalHardestAI. An older expert-trained model with 57.7% accuracy achieves ~10% WR. Higher validation accuracy is producing *worse* playing strength.

---

## 2. Root Cause Analysis (Updated)

Based on the original analysis plus six independent reviews, here are the causes ranked by confidence:

### Cause 0: Training ≠ Inference (CRITICAL — unanimous across all reviewers)
Training optimizes raw logits with MSE. Inference applies `tanh`. Two models with identical val_loss can behave completely differently after tanh (especially when one produces larger-magnitude logits). The model has no incentive to produce well-calibrated post-tanh values. **This is a bug, not a hyperparameter.**

### Cause 1: Learning Rate 30× Too High (HIGH CONFIDENCE)
Churchill used 1e-5. Our warmup starts at ~6e-5 (explaining why epoch 1 is best) then ramps to 3e-4, triggering memorization. All six reviewers confirmed this diagnosis.

### Cause 2: Temporal Correlation Destroys Effective Sample Size (HIGH CONFIDENCE)
With ~37 positions per game all sharing the same outcome label, adjacent positions are 90%+ correlated. The effective independent sample count is ~177K games, not 6.57M positions. This makes the true data-to-parameter ratio **0.07:1** (177K games / 2.4M params), not 2.7:1. This reframing (identified by 5/6 reviewers) makes overfitting entirely expected and elevates position subsampling from "future direction" to primary intervention.

### Cause 3: Model Overparameterized for Data (HIGH CONFIDENCE)
2.4M parameters vs ~177K effective independent samples. Churchill had 1.1M params with 500K games (0.45:1 on a per-game basis). Our ratio is 6× worse.

### Cause 4: Self-Play Data Quality (MEDIUM-HIGH CONFIDENCE)
A 3% WR agent generates its own training data. Churchill used MasterBot (a competent portfolio player with 3000ms UCT search). Our agent's game outcomes are far noisier training signals — many positions are roughly equal, with the outcome determined by later blunders. As one reviewer put it: "overfitting might actually be the model correctly learning that the dataset is garbage."

### Cause 5: Validation Metric Misaligned (MEDIUM-HIGH CONFIDENCE)
Binary accuracy at a 0.5 threshold measures whether the model gets the sign right, which rewards memorized models that are confidently wrong. A value network used in alpha-beta search cares about ranking, calibration, and the ability to distinguish close positions — not just the sign. The current val set is a 10% slice of the same self-play distribution, which doesn't measure generalization to real opponent play.

### Cause 6: MSE Loss Poorly Suited to Binary Outcomes (MEDIUM CONFIDENCE)
MSE on a Bernoulli target (game outcome ±1) creates bizarre gradients in the presence of label noise. BCE with logits is the standard choice for win probability prediction and provides better calibration.

### Cause 7: Epoch-Level Evaluation Too Coarse (MEDIUM CONFIDENCE)
One epoch = ~12,800 optimizer steps. "Best at epoch 1" may really mean "best at step ~1,500." We may be missing the actual generalization peak and only seeing the aftermath.

---

## 3. Current Architecture & Configuration

### Model: PrismataNet (PyTorch)

```
Input: state vector [1785 features]
  - 161 unit types × 11 features each
  - 14 global features
  - Features normalized: counts clamped to max, divided by max

Trunk:
  Linear(1785 → 512) → ReLU
  × 2 residual blocks:
    Linear(512 → 512) → LayerNorm(512) → ReLU → Dropout(p) → Linear(512 → 512) → LayerNorm(512)
    + residual skip → ReLU

Value Head:
  Linear(512 → 128) → ReLU → Linear(128 → 1)
  Output: raw logit (unbounded). tanh applied only in C++ inference.
  Loss: MSE on raw logits vs targets of ±label_smooth

Policy Head: disabled (--value-only), 13% accuracy
```

**Total parameters:** ~2.4M (hidden_dim=512, num_layers=2)

### Current Training Hyperparameters

| Parameter | Value |
|---|---|
| Optimizer | AdamW |
| Learning rate | 3e-4 (peak after warmup) |
| LR schedule | Linear warmup (5 epochs) → Cosine decay to 1e-5 |
| Batch size | 512 |
| Dropout | 0.1 |
| Weight decay | 1e-4 |
| Label smoothing | 0.95 (targets ±0.95) |
| Gradient clipping | 1.0 max norm |
| Early stopping | patience=15 on val_value_loss |
| Train/val split | 90/10 by game_id % 10 |

### Training Data

| Metric | Value |
|---|---|
| Source | Self-play (neural eval AI vs itself) |
| Total positions | ~6.57M |
| Total games | ~177K |
| Positions per game | ~37 |
| Effective independent samples | ~177K (one outcome per game) |
| Data-to-param ratio (positions) | 2.7:1 |
| Data-to-param ratio (games) | **0.07:1** |

### Observed Results

| Model | Val Acc | Games | WR vs OriginalHardestAI |
|---|---|---|---|
| Expert-trained | 57.7% | 64 | ~10% |
| Self-play v2 | 81.9% | 296 | ~4.1% |
| Self-play v2 (current) | ~82% | 232 | ~3% |

---

## 4. Reference Systems

### Churchill & Campbell (2019)

| Parameter | Churchill | Ours | Gap |
|---|---|---|---|
| Architecture | Plain 2-layer MLP | 2-layer ResNet + LayerNorm | Ours more complex |
| Hidden dim | 512 | 512 | Same |
| Dropout | None | 0.1 | — |
| **Learning rate** | **1e-5** | **3e-4** | **30× higher** |
| Optimizer | Adam | AdamW | Similar |
| **Data (games)** | **500K** | **177K** | **2.8× less** |
| **Parameters** | **~1.1M** | **~2.4M** | **2.2× more** |
| **Games-to-param ratio** | **0.45:1** | **0.07:1** | **6.4× worse** |
| Training accuracy | ~90% | 98%+ (memorized) | — |
| Self-play agent | MasterBot (competent) | Neural eval (3% WR) | Far weaker |
| Result | 58.8% WR vs playout | 3% WR vs baseline | — |

### Lc0 (Most Relevant Precedent)

Experienced identical value head overfitting. Key findings:
- `value_loss_weight=0.25` (from 1.0) caused immediate recovery — but this worked because policy head dominated representation learning. **In our value-only setup, this is approximately equivalent to reducing LR** (confirmed by 3/6 reviewers).
- Seeing each position once during training is at the **very top end of workable**.
- Adjacent positions amplify memorization.

### KataGo

- Progressive model scaling: start small, grow with data.
- EMA (decay=0.75) for weight averaging.
- Auxiliary targets as regularization (multi-task learning).

---

## 5. Infrastructure Prerequisites (BEFORE any experiments)

These changes are required before the experiment sweep. They are fixes and instrumentation, not experiments.

### P0: Fix Training/Inference Mismatch

**In `training/train.py` (or model definition):**

Apply `tanh` during training so the model trains on the function it deploys.

```python
# In model forward():
value_logit = self.value_head(trunk_out)  # raw logit
value = torch.tanh(value_logit)           # bounded [-1, 1]
return value  # train on this

# Loss: MSE on tanh output vs targets in [-1, 1]
# OR: switch to BCEWithLogitsLoss on raw logit, targets mapped to {0, 1}
```

**Two options (test both as E0a/E0b below):**
- **Option A:** `tanh` in training + MSE/Huber on bounded output vs ±0.95 targets
- **Option B:** `BCEWithLogitsLoss` on raw logit, targets mapped to {0, 1} (or {0.025, 0.975} for smoothing)

**In C++ inference:** Verify `tanh` is still applied (or removed consistently if using Option B with sigmoid).

### P1: Step-Level Evaluation & Checkpointing

Modify the training loop to evaluate on the validation set every N optimizer steps (not just every epoch), and save checkpoints at evaluation points.

```python
EVAL_EVERY_STEPS = 1000  # ~1 eval per 512K positions processed
# At each eval point: compute val_loss, val_acc, save checkpoint
# Save: model_step_{N}.pt
```

This turns the opaque "best at epoch 1" into a visible curve showing exactly where generalization peaks.

### P2: Implement Position Subsampling

Add a `--subsample-rate` or `--positions-per-game` argument to the training data loader.

```python
# Option A: Keep every Nth position per game
--subsample-every 3  # keeps ~12 positions/game instead of 37

# Option B: Sample K random positions per game per epoch
--positions-per-game 10
```

This is trivial to implement in the data loader and directly attacks temporal correlation.

### P3: Generate Shifted Validation Set

Generate a small dataset (~2K-5K games) from **OriginalHardestAI playing against itself**. Use this as a second validation set (`val_baseline`) that measures generalization to competent play, not just self-play consistency.

```bash
# Modify tournament config to run OriginalHardestAI vs OriginalHardestAI
# with data capture enabled, then designate all output as validation-only
```

Report metrics on BOTH `val_selfplay` and `val_baseline` for every experiment. Select models based on `val_baseline` performance.

### P4: Add Better Metrics

Beyond val_value_loss and val_value_acc, log:
- **Brier score** (calibration-aware: mean of (predicted_prob - actual_outcome)²)
- **AUC** (ranking quality — does the model correctly order positions?)
- **Per-turn-bucket metrics** (loss by early/mid/late game — reveals if late-game is trivial and early-game is noise)

### P5: Reduce Early Stopping Patience

Change patience from 15 to 5 epochs (or 5,000 steps) during the sweep. With step-level evaluation, we'll detect overfitting much faster and waste less time on doomed runs.

---

## 6. Experiment Plan

### Design Principles
- Fix bugs first (P0), then sweep hyperparameters
- Each run trains on current ~6.5M positions (~177K games) for consistency
- Evaluate every 1,000 steps (not just epochs)
- Report metrics on both val_selfplay and val_baseline
- **Primary metric:** `val_baseline_loss` (shifted validation set)
- **Secondary metrics:** `best_step`, `train/val gap`, Brier score, AUC
- **Ultimate metric:** WR vs OriginalHardestAI (tournament, 400+ games, for finalists only)
- **Smoke test:** 40-game mini-tournament after each run as a fast gate

---

### Phase 0: Bug Fixes + Loss Function (60-90 min)

These must run first. Everything downstream depends on getting the loss right.

#### E0a: Tanh in Training + MSE (Recommended Starting Point)

Apply `tanh` in the forward pass. Keep MSE loss. Keep all other hyperparameters at baseline values except remove warmup.

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 50 --batch-size 512 --lr 3e-4 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0 \
  --tanh-in-training --eval-every-steps 1000
```

**Purpose:** Establish whether fixing the mismatch alone changes the overfitting pattern.

#### E0b: BCEWithLogitsLoss

Replace MSE with BCE. Targets mapped to {0, 1}. No tanh in forward pass (sigmoid is implicit in BCE).

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 50 --batch-size 512 --lr 3e-4 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0 \
  --loss-fn bce --eval-every-steps 1000
```

**Purpose:** Test whether a proper probabilistic loss changes training dynamics.

#### E0c: Warmup-Only Ablation (Isolation Test)

Keep original MSE-on-logits loss (no tanh fix). Only remove warmup. This isolates whether warmup removal alone helps.

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 50 --batch-size 512 --lr 3e-4 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 0 \
  --eval-every-steps 1000
```

**Purpose:** Isolate whether warmup removal (vs LR reduction, vs loss fix) is the key variable.

**Decision gate after Phase 0:** Pick the best loss function (E0a vs E0b). All subsequent experiments use that loss. If E0c alone fixes overfitting, we've saved hours.

---

### Phase 1: Learning Rate Sweep (60-90 min)

Using the winning loss function from Phase 0. All experiments use 1-epoch warmup to a low peak (training stability insurance) + cosine decay.

#### E1a: LR=1e-5 (Match Churchill)

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-5 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --eval-every-steps 1000
```

#### E1b: LR=3e-5

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 3e-5 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --eval-every-steps 1000
```

#### E1c: LR=1e-4

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr 1e-4 --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --eval-every-steps 1000
```

**Success criteria:**
- best_step moves significantly past first evaluation point
- val_baseline_loss improves over multiple evaluations before degrading
- Train/val gap stays below 15%

**Decision gate:** Pick the best LR. If ALL still overfit at step 1, the problem is deeper than LR (proceed to Phase 2 with urgency on subsampling).

---

### Phase 2: Data & Capacity (60-90 min)

Using the best loss function AND best LR from above.

#### E2a: Position Subsampling (Every 3rd Position)

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr <best> --patience 5 \
  --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --subsample-every 3 --eval-every-steps 1000
```

**Purpose:** Reduce temporal correlation. Cuts dataset to ~2.2M positions but from the same 177K games. If val_baseline improves despite fewer positions, correlation was a major driver.

#### E2b: Reduced Model Capacity (hidden_dim=256)

**Note:** v1 Exp 3 tested hidden_dim=256 with the broken loss function and showed no improvement (75.3% val). This re-test with the fixed loss function will reveal whether model capacity matters when training is correct.

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr <best> --patience 5 \
  --hidden-dim 256 --num-layers 2 --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --eval-every-steps 1000
```

**Purpose:** ~700K params, games-to-param ratio improves to 0.25:1 (from 0.07:1). Note: changing hidden_dim requires re-exporting weights and rebuilding C++ exe.

#### E2c: Subsampling + Smaller Model (Combined)

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr <best> --patience 5 \
  --hidden-dim 256 --num-layers 2 --dropout 0.1 --weight-decay 1e-4 --warmup-epochs 1 \
  --loss-fn <best> --subsample-every 3 --eval-every-steps 1000
```

**Purpose:** Combined attack on both data correlation and model capacity.

---

### Phase 3: Regularization (30-60 min, if needed)

Run only if Phases 1-2 still show overfitting. **Note:** v1 experiments already showed that dropout 0.3 + WD 1e-3 doesn't help with the broken loss function. These re-tests with the fixed loss are only needed if Phases 1-2 are insufficient.

#### E3a: Stronger Dropout (0.25) + Weight Decay (5e-4)

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr <best> --patience 5 \
  --dropout 0.25 --weight-decay 5e-4 --warmup-epochs 1 \
  --loss-fn <best> --eval-every-steps 1000
```

#### E3b: SWA/EMA (Stochastic Weight Averaging)

Add EMA to the best configuration from Phases 1-2:

```bash
PYTHONUNBUFFERED=1 python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --value-only --epochs 100 --batch-size 512 --lr <best> --patience 5 \
  --dropout <best> --weight-decay <best> --warmup-epochs 1 \
  --loss-fn <best> --use-ema --ema-decay 0.995 --eval-every-steps 1000
```

**Note:** SWA/EMA is ~10 lines of code with `torch.optim.swa_utils` and reliably improves generalization by 1-2%.

---

### Phase 4: Tournament Validation (2-4 hours)

For the top 2-3 candidates from Phases 0-3:

#### 4a: Multi-Checkpoint Tournament

From the single best training run, export checkpoints at 3 different points (e.g., step 1000, step 5000, best_step) and tournament-evaluate each. This validates whether val_baseline_loss predicts playing strength.

```bash
# For each checkpoint:
python training/export_weights.py training/models/model_step_N.pt \
  --output bin/asset/config/neural_weights.bin

# Rebuild if hidden_dim changed
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Debug //p:Platform=x86 //m

# Tournament: 400+ games (target: 95% CI width < 10%)
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing_d.exe
```

#### 4b: Head-to-Head Finalist Tournament

Top 2 candidates play 400+ games vs OriginalHardestAI each. Report win rates with 95% confidence intervals.

---

## 7. Quick Diagnostics (Run Anytime, ~5 min each)

These are cheap sanity checks that can reveal bugs or fundamental issues. Run before or during the sweep.

### D1: Feature Leakage Test
Train a tiny model (linear or 1-hidden-layer of 64 units) on the same data. If it achieves surprisingly high accuracy, features may encode near-terminal certainty or there's leakage.

### D2: Duplicate Detection
Hash the 1785-float feature vectors (after quantization to e.g. 3 decimal places). Estimate duplicate rate across train/val. If game A (train) and game B (val) share identical states, validation metrics are inflated.

### D3: Per-Turn Metrics
Report loss/accuracy by turn bucket (turns 1-5, 6-10, 11-15, 16+). If late-game is trivially easy and early-game is pure noise, rebalance sampling or weight the loss by turn.

### D4: One-Position-Per-Game Diagnostic
Train on just 1 random position per game (177K positions total, same 177K games). If validation *improves* despite 37× less data, correlation is confirmed as a dominant factor.

---

## 8. Execution Summary

| Phase | Experiments | Time | Depends On |
|---|---|---|---|
| Prerequisites | P0-P5 (code changes) | 1-2 hours coding | Nothing |
| Phase 0 | E0a, E0b, E0c | ~90 min | Prerequisites |
| Phase 1 | E1a, E1b, E1c | ~90 min | Phase 0 decision |
| Phase 2 | E2a, E2b, E2c | ~90 min | Phase 1 decision |
| Phase 3 | E3a, E3b (if needed) | ~60 min | Phase 2 |
| Phase 4 | Tournaments | ~2-4 hours | Top candidates |
| Diagnostics | D1-D4 | ~20 min | Anytime |

**Total: ~8-12 hours** (including code changes and tournaments). Can stop after Phase 1 if results are clear.

**40-game smoke test after EVERY training run.** Even noisy WR at 40 games is enough to reject clearly-bad directions and catches the "val improves, strength degrades" trap.

---

## 9. Success Metrics

| Metric | Current (Baseline) | Success | Excellent |
|---|---|---|---|
| best_step | ~first eval point | >5,000 | >10,000 |
| train_acc at best_step | 98%+ | ≤92% | ≤88% |
| val_baseline_loss | N/A (new metric) | improves ≥5% over self-play val | improves ≥10% |
| WR vs OriginalHardestAI | ~3% | >10% | >20% |
| 95% CI on WR (400 games) | [1.2%, 6.3%] | distinguishable from baseline | — |

---

## 10. What NOT to Do (Anti-Patterns)

1. **Don't optimize val_accuracy.** Binary sign accuracy rewards memorized models and doesn't predict playing strength. Use val_loss, Brier score, and AUC.

2. **Don't train more epochs hoping for improvement.** Once the model memorizes, it won't recover. Step-level checkpointing means we catch the peak precisely.

3. **Don't add more data without fixing LR and loss function.** The 10K→63K increase didn't help. Fix the training procedure first, then scale data.

4. **Don't confound variables.** If you change the LR, don't also change the schedule, the loss function, and the regularization in the same run. The warmup ablation (E0c) exists to isolate one specific variable.

5. **Don't select models on self-play validation alone.** The shifted validation set (val_baseline) and 40-game smoke tests exist because self-play val is a demonstrated poor proxy for strength.

6. **Don't enable the policy head yet.** At 13% accuracy with the current formulation it adds noise. However, *lightweight auxiliary tasks* (predict game phase, resource deltas) are worth exploring as regularizers in a later phase.

7. **Don't change batch size as a regularization lever.** It's confounded with step count per epoch and 4-8× slower. Use dropout, weight decay, or subsampling instead.

---

## 11. Future Directions (Post-Experiment)

### If experiments succeed (WR >10%):
1. Scale data generation toward 500K games (Churchill's volume)
2. Retrain with winning hyperparameters on larger dataset
3. Progressive model scaling: start at hidden=256, grow to 512 as data accumulates (KataGo approach)
4. Re-evaluate policy head with better formulation

### If experiments partially succeed (best_step >5K but WR still <10%):
1. **Mixed training data:** Blend self-play + expert data (70/30) to anchor the value function to human-quality evaluations
2. **Teacher targets:** Use AB search with current best eval to generate soft value targets instead of pure ±1 game outcomes
3. **Auxiliary tasks:** Add lightweight heads predicting game phase, resource state, or "can force lethal within N turns" — forces trunk to learn causally useful features
4. **Plain MLP (Churchill architecture):** Strip residual connections and LayerNorm as a diagnostic — if it overfits less, the architecture was too expressive

### If experiments fail (still overfitting at first eval point):
1. **The data is the problem.** A 3% WR agent generating its own training data creates a feedback loop rewarding consistency over correctness. Pivot to generating data from OriginalHardestAI self-play (competent agent, diverse play patterns)
2. **Input noise augmentation:** Add Gaussian noise (σ=0.02) to normalized features during training — cheap data augmentation for count-based features
3. **Dramatically smaller model:** hidden=64 or even linear value function as a floor test

---

## 12. Technical Notes

### Weight Export
The C++ binary weight format encodes `hidden_dim` in the header. Export works for any size:
```bash
python training/export_weights.py training/models/best_model.pt --output bin/asset/config/neural_weights.bin
```
Changing hidden_dim requires rebuilding the C++ exe.

### C++ Inference Changes
If switching from `tanh` to `sigmoid` (BCEWithLogits), the C++ inference code in `source/ai/` needs to be updated to match. Verify the activation function matches what was trained.

### Streaming Data Loader (Parallel Track)
The current data loader OOMs on the full dataset (6.5M records = 44GB raw, 32GB RAM). A streaming/memory-mapped data loader is needed to use all available data. This is useful infrastructure regardless of experiment outcomes and can be developed in parallel with Phase 0-1. Use `--max-records 1000000` as a workaround until the streaming loader is ready. See CLAUDE.md "Training RAM limit" gotcha.

### Self-Play Data Fleet
The fleet (24 AWS + 8 Azure + 2 GCP + local) continues generating ~175K+ games and growing. By the time experiments complete, more data may be available. Re-run the best configuration on the larger dataset as a final step — but only after the training procedure is fixed.

### Experiment Logging
All runs save to `training/runs/{timestamp}.json` with full hyperparameters, per-step metrics, git hash, and data statistics. The step-level logging (P1) adds checkpoints at `training/models/model_step_{N}.pt`.

### Reproducibility
For the top 2-3 finalist configurations, rerun with 3 different random seeds. With AdamW + dropout + shuffling, single-run results can be misleading.
