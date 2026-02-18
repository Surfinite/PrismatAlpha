# GPU Training Plan v2 — Feb 18, 2026

*Revised after 6 independent expert reviews. Changes from v1 marked with* **[CHANGED]**.

## Situation

- **Data:** 356K games (13.2M records) — **5.7x more than when E2b was trained** (63K games, 2.3M records)
- **Current best:** E2b (hidden_dim=256, LR=1e-5, MSE, 739K params) = **26.7% WR** vs OriginalHardestAI
- **305K-game retrain already done:** 256h model on 305K games = **45.3% WR** (4,032 games). This is our actual baseline now.
- **512h comparison IN PROGRESS** locally on XPU (330K games, epoch 5, step 55000, 85.1% val acc)
- **Key insight:** Churchill achieved 58.8% WR with 500K games. Our 45.3% with 330K games is on track.
- **Data/param ratios:** 256h (739K params): 356K/739K = **0.48:1** (Churchill was 0.45:1 — at parity). 512h (1.08M params): 0.33:1.

## What Changed from v1 (Review Summary)

Six independent reviews identified these issues. Here's what we're changing and what we're not:

### Accepted Changes

| Issue | Reviews | Action |
|-------|---------|--------|
| **Sequential sweep misses HP interactions** | 1,2,3,5,6 | Merge capacity + LR into a joint 2×3 grid |
| **Missing depth experiments** | 1,2,4,5,6 | Add `--num-layers 3` and `--num-layers 4` runs |
| **128h run is wasted compute** | 1,2,4,6 | Dropped — 192K params at 1.86:1 ratio is capacity-limited, not informative |
| **Cosine schedule misconfigured** | 1,3 | `--epochs 100` with early stopping at ~20 means cosine barely decays. Fix: `--epochs 40` |
| **Warmup epochs changed meaning** | 3 | 5 warmup epochs = 129K steps now (was 22K). Reduce to `--warmup-epochs 2` |
| **Tournament needs more games** | 1,2,5,6 | Increase to 4,000 games (our 305K eval already used 4,032) |
| **LR scaling rule wrong for Adam** | 1,3,6 | Don't scale LR with batch size — AdamW is robust to batch changes |
| **Add label_smooth=1.0 test** | 1,6 | Test no smoothing (hard targets ±1.0) now that data is larger |
| **S3→GCP egress ~$8.50** | 1 | Stage data on GCS once, or preferentially run on AWS |

### Rejected (Reviewers Were Wrong)

| Suggestion | Reviews | Why We Reject |
|------------|---------|---------------|
| **Policy head might help via multi-task** | 2,5,6 | Policy head is **not constructed** in `--value-only` mode (verified in code). No gradients. Self-play moves are from deterministic AB search — point mass, not a distribution. 13% accuracy confirms this is not learnable. |
| **Data augmentation (unit permutation, mixup)** | 2,5,6 | Units are NOT equivalent — each has unique abilities/costs/roles. Can't permute 161 unit type features. Mixup interpolation (0.7 of a Tarsier?) makes no physical sense. Game asymmetry prevents mirroring. |
| **Curriculum learning** | 2,5 | Would require significant streaming loader changes for unclear benefit. Shuffle already mixes all game phases. |
| **Test GELU/SiLU hidden activation** | 5,6 | C++ inference engine uses ReLU. Changing requires rebuilding the C++ code + engine integration. Marginal gain doesn't justify the engineering. |
| **Weights & Biases logging** | 2 | Already log per-epoch metrics to JSON. For 15 runs at 2 min each, W&B adds overhead without benefit. |
| **SAM (Sharpness-Aware Minimization)** | 5 | Doubles training cost. More data should naturally improve generalization. Overkill for this scale. |
| **Online game evaluation during training** | 6 | C++ engine isn't on GPU instances. Tournament eval is a separate phase by design. |

### Already Correct (Reviewers Didn't Know)

| Concern | Reviews | Actual Implementation |
|---------|---------|----------------------|
| **Train/val split by game, not record** | 3,4,6 | `game_id % 10 == 0 → val` — split is by game. No leakage. |
| **Streaming shuffle quality** | 3,4,5 | DataLoader `shuffle=True` on global memmap indices = true random access across all shards. Shard ordering irrelevant. |
| **Adam vs AdamW** | 4,5 | Already using `torch.optim.AdamW` with separate param groups (bias/norm excluded from decay). |
| **`--num-layers` flag for depth** | 1,2,4,5,6 | Flag exists: `--num-layers N` controls residual block count. Default 2. |
| **Policy head gradient leakage** | 1 | Head is not constructed. `forward()` returns `None` for policy. Zero gradient risk. |

---

## Compute Resources

### GCP — Primary (free $300 credit, ~$240 remaining)

- **GPU:** NVIDIA L4 (Ada Lovelace, 24GB VRAM, ~30 TFLOPS FP32) in us-central1
- **Quota:** `NVIDIA_L4_GPUS=1`, `GPUS_ALL_REGIONS=1` — **1 GPU at a time**, sequential runs only
- **Instance:** `g2-standard-4` + 1x L4 (~$0.70/hr on-demand)
- **Why on-demand, not preemptible:** Runs are <3 min each. Preemptible saves ~$0.50/hr but risks losing a completed run. Not worth it. **[CHANGED]**
- **Data staging:** One-time sync of selfplay shards from S3 to GCS bucket (~94GB, ~$8.50 egress). All subsequent GCP runs read from GCS. **[CHANGED]**

### AWS — Secondary (spot only, pending quota)

- **GPU:** NVIDIA T4 via g4dn.xlarge (16GB VRAM, 4 vCPUs per instance)
- **Quota:** G and VT Spot = **0 vCPUs** (request for 40 pending, CASE_OPENED Feb 18 5:52 PM)
- **When approved:** 40 vCPUs = **10 parallel T4 spot instances** (~$0.16/hr each)
- **Advantage:** S3 access is free within region — no data staging needed
- **Infrastructure:** `aws/launch_training.sh` ready, auto-terminates, uploads results to S3
- **Use for:** Parallel grid runs (Phase 2) if quota arrives in time

### Fallback: Local Intel Arc B580

- ~13s/epoch, free. Use if both cloud options are unavailable.
- 512h comparison already running locally (330K games, in progress).

### Execution Strategy

| Phase | Where | Why |
|-------|-------|-----|
| Phase 1 (baseline) | **GCP L4** | Highest priority, run immediately, free |
| Phase 2 (capacity × LR grid) | **AWS spot** (parallel) or GCP L4 (sequential, ~12 min) | 6 runs benefit from parallelism |
| Phase 3 (depth) | **GCP L4** | 2 sequential runs, ~4 min |
| Phase 4 (regularization) | **GCP L4** | Lower priority, sequential fine |
| Phase 5 (tournament eval) | **AWS c5.2xlarge fleet** | Existing fleet, no GPU needed |

---

## Performance Estimates

| GPU | TFLOPS FP32 | VRAM | Est. epoch time (13.2M records, bs=512) | Est. run time (~25 epochs) |
|-----|------------|------|----------------------------------------|--------------------------|
| Intel Arc B580 (local) | ~8 | 12GB | 13s | ~5.4 min |
| NVIDIA T4 (AWS) | 8.1 | 16GB | ~12s | ~5 min |
| **NVIDIA L4 (GCP)** | **30** | **24GB** | **~5s** | **~2 min** |

Total plan (~15 experiments) on L4: **~30 min GPU time** (~$0.35 from free credit).

---

## Training Command Template **[CHANGED]**

```bash
python training/train.py training/data training/models \
  --selfplay-dir selfplay_data/ \
  --streaming \
  --value-only \
  --hidden-dim {HIDDEN_DIM} \
  --num-layers {NUM_LAYERS} \
  --epochs 40 \
  --batch-size 512 \
  --lr {LR} \
  --warmup-epochs 2 \
  --tanh-in-training \
  --loss-fn mse \
  --patience 15 \
  --num-workers 4 \
  --eval-every-steps 5000 \
  --seed 42 \
  --device cuda
```

**Changes from v1:**
- `--epochs 40` (was 100) — cosine decay now reaches meaningful LR reduction before early stopping fires **[CHANGED]**
- `--warmup-epochs 2` (was 5) — 5 warmup epochs at 356K games = 129K warmup steps, far too long. 2 epochs = ~52K steps, closer to E2b's effective warmup **[CHANGED]**
- `--num-layers {NUM_LAYERS}` added — depth is now a variable **[CHANGED]**

**Verified correct (no changes needed):**
- `--streaming` shuffles via global index permutation on memmap — true random access
- Train/val split is by `game_id % 10 == 0` — no cross-game leakage
- AdamW optimizer with proper param groups (bias/norm excluded from decay)
- `--patience 15` counts evaluation points, not raw epochs
- `--eval-every-steps 5000` = ~5 evals per epoch — fine-grained checkpoint selection

---

## Phase 1: Baseline Retrain (HIGHEST PRIORITY)

**Where:** GCP L4 (run immediately)

**Goal:** Establish new baseline with 5.7x more data, same winning config.

| Run | Hidden | Layers | LR | Batch | Label | Rationale |
|-----|--------|--------|-----|-------|-------|-----------|
| **R1** | 256 | 2 | 1e-5 | 512 | `baseline_256h_356k` | Exact E2b config on full 356K games |

**Why this is #1:** More data is the single biggest lever. The 305K-game retrain already jumped from 26.7% to 45.3% WR. Full 356K games should give another incremental boost and establish the definitive baseline.

**Expected:** Val loss well below E2b's 0.338. Best epoch should shift later (epoch 15-25) due to more data + fixed cosine schedule.

**Decision gate:** If val_loss > 0.30, something is wrong — investigate before proceeding. If val_loss < 0.25, proceed confidently to Phase 2.

---

## Phase 2: Capacity × LR Joint Grid **[CHANGED — was separate Phases 2+3]**

**Where:** AWS spot T4s (6 parallel) if quota approved, else GCP L4 sequential (~12 min)

**Goal:** Test capacity and learning rate simultaneously to catch interactions. The optimal LR for 512h may differ from 256h — sweeping them independently would miss this. **[CHANGED]**

| Run | Hidden | Layers | LR | Params | Data:Param | Label |
|-----|--------|--------|-----|--------|-----------|-------|
| R1 | 256 | 2 | 1e-5 | 739K | 0.48:1 | *(from Phase 1)* |
| **R2** | 256 | 2 | 5e-6 | 739K | 0.48:1 | `grid_256h_lr5e6` |
| **R3** | 256 | 2 | 2e-5 | 739K | 0.48:1 | `grid_256h_lr2e5` |
| **R4** | 512 | 2 | 5e-6 | 1.08M | 0.33:1 | `grid_512h_lr5e6` |
| **R5** | 512 | 2 | 1e-5 | 1.08M | 0.33:1 | `grid_512h_lr1e5` |
| **R6** | 512 | 2 | 2e-5 | 1.08M | 0.33:1 | `grid_512h_lr2e5` |

**Why this design:**
- **2×3 grid** ({256h, 512h} × {5e-6, 1e-5, 2e-5}) captures the interaction that sequential sweeps miss
- **Dropped 128h** — at 192K params / 356K games (1.86:1 ratio), it's capacity-constrained. We know from V2 that smaller = worse at this data scale. Not informative. **[CHANGED]**
- **Dropped 384h** — if 512h now beats 256h, we'll interpolate later. If 256h still wins, 384h is irrelevant.
- **Dropped 5e-5 LR** — V1 showed 3e-4 was catastrophic. 5e-5 is a 5x jump from 1e-5 and likely too aggressive even with more data. 2e-5 is the safer upper bound.
- R1 counts as one cell of the grid (256h/1e-5), so only **5 new runs**.

**Expected:** 256h/1e-5 likely still best, but 512h may now be competitive. If 512h wins at a different LR than 256h, the joint grid caught an interaction that sequential would have missed.

---

## Phase 3: Depth Experiments **[NEW]**

**Where:** GCP L4 (sequential, ~4 min)

**Goal:** Test whether deeper networks learn better representations with 356K games. All 6 reviewers flagged this as the biggest omission in v1.

| Run | Hidden | Layers | LR | Label | Rationale |
|-----|--------|--------|-----|-------|-----------|
| **R7** | best | 3 | best | `depth_3blocks` | Modest depth increase — more hierarchical features |
| **R8** | best | 4 | best | `depth_4blocks` | Deeper still — higher capacity with same width |

Uses the winning hidden_dim and LR from Phase 2.

**Rationale:** The current architecture has only 2 residual blocks — shallow for a 1,785-dim input representing a complex strategy game. Deeper networks learn hierarchical abstractions (unit interactions, strategic patterns) that wide-but-shallow networks may miss. A 256h×4-block model has similar parameter count to 512h×2-block but distributes capacity through depth rather than width.

**The `--num-layers` flag already exists** in train.py and controls trunk residual block count. Each block is 2 linear layers + LayerNorm + ReLU + dropout + skip connection. No code changes needed.

---

## Phase 4: Regularization Tuning

**Where:** GCP L4 (sequential, ~8 min)

**Goal:** With best config from Phases 2-3, test regularization variants.

| Run | Dropout | Weight Decay | Label Smooth | Label | Rationale |
|-----|---------|-------------|-------------|-------|-----------|
| **R9** | 0.05 | 1e-4 | 0.95 | `reg_dropout05` | Less dropout — more data may reduce need for regularization |
| **R10** | 0.2 | 1e-4 | 0.95 | `reg_dropout20` | More dropout — stronger regularization |
| **R11** | 0.1 | 1e-4 | 1.0 | `reg_smooth100` | **No label smoothing** — hard targets ±1.0. More data = more confident labels **[CHANGED]** |
| **R12** | 0.1 | 1e-4 | 0.90 | `reg_smooth90` | Softer labels — may help calibration |

**Changes from v1:**
- Replaced R10 (weight decay 1e-3) with smooth=1.0 test. **Rationale:** Multiple reviewers noted that label smoothing 0.95 with tanh output pushes targets into the shallow-gradient region of tanh. With 5.7x more data, hard labels may be appropriate. Testing 1.0 is more informative than testing aggressive weight decay. **[CHANGED]**
- Dropped "may be underfitting" framing for R9. **Correct framing:** "more data reduces overfitting, so we can afford less regularization." Prior training always showed overfitting, never underfitting. **[CHANGED]**

---

## Phase 5: Tournament Evaluation **[CHANGED — batch size phase dropped]**

**Where:** AWS c5.2xlarge fleet (CPU, no GPU needed) or local

**Goal:** Validate the best 2-3 models via tournament against OriginalHardestAI.

1. Export weights: `python training/export_weights.py training/models/best_model.pt bin/asset/config/neural_weights.bin`
2. Run tournament: `aws/launch_tournament.sh` or local eval — **4,000 games** per model **[CHANGED]**
3. Compare WR against current best (45.3% at 305K games)

**Changes from v1:**
- **4,000 games** (was 1,000). At 30% WR, SE ≈ 0.007, 95% CI ≈ ±1.4%. At 45% WR, CI ≈ ±1.5%. This reliably distinguishes 2-3pp differences. Our 305K eval already used 4,032 games — this is the proven standard. **[CHANGED]**
- **Evaluate top 2-3 models**, not just best val_loss. Sometimes a model with slightly higher val_loss plays better in tournament (different evaluation at critical positions). **[CHANGED]**
- **Batch size phase dropped** entirely. Reviewers correctly noted: (a) runs are already <3 min, wall-clock optimization is pointless; (b) large batches tend to find sharp minima with worse generalization; (c) linear LR scaling rule doesn't apply to AdamW. Low priority, low expected value. **[CHANGED]**

**Success criteria:**
- **Good:** >48% WR (meaningful improvement over 45.3% baseline from data scaling alone)
- **Great:** >55% WR (closing on Churchill's 58.8%)
- **Exceptional:** >60% WR (surpassing Churchill with fewer games)

*Note: Targets raised from v1 since our actual baseline is now 45.3%, not 26.7%.* **[CHANGED]**

---

## Execution Order

1. **R1** — Baseline retrain on GCP L4 (highest priority, ~2 min)
2. **R2-R6** — Capacity × LR grid on AWS spot (parallel) or GCP L4 (sequential, ~12 min)
3. **R7-R8** — Depth experiments on GCP L4 (~4 min)
4. **R9-R12** — Regularization on GCP L4 (~8 min) — *only if Phases 1-3 show room for improvement*
5. **Tournament** — Top 2-3 models, 4,000 games each

**Decision gates (after each phase):**
- After R1: If val_loss > 0.30 → investigate before proceeding
- After Phase 2: If 512h clearly wins (>3% val_acc advantage at best LR), carry 512h forward. If 256h wins, carry 256h.
- After Phase 3: If depth=4 clearly beats depth=2 (>2% val_acc), use deeper model going forward. Otherwise keep depth=2.
- After Phase 4: If no regularization variant beats the Phase 2-3 winner, go directly to tournament.

**Total: 12 training runs + tournament eval.** Under budget, well within time constraints.

---

## Data Transfer Plan **[NEW]**

**Problem:** 13.2M records × 7,152 bytes ≈ **94GB**. S3→GCP egress costs ~$0.09/GB = **~$8.50** — more than the entire compute budget.

**Solutions (pick one):**

| Option | Cost | Latency | Best for |
|--------|------|---------|----------|
| **A: Run on AWS** | $0 (S3 in-region) | None | If AWS GPU quota approved |
| **B: Stage on GCS** | ~$8.50 one-time | ~30 min transfer | Multiple GCP runs |
| **C: Use `--max-records 5000000`** | $0 | None | Quick tests on GCP (5M records = ~180K games, still 3x more than E2b) |

**Recommendation:** Use **Option A** (AWS) for the grid runs if quota arrives. Use **Option C** for the GCP baseline (R1) to validate quickly, then decide whether to pay for Option B.

---

## GCP L4 Setup Notes

Need a `gcp/launch_training.sh` script (similar to `aws/launch_training.sh`). Key differences:

1. **Instance:** `g2-standard-4` + `--accelerator type=nvidia-l4,count=1` in us-central1-a
2. **Image:** GCP Deep Learning VM (PyTorch 2.x, Linux — NOT Windows)
3. **Data transfer:** See Data Transfer Plan above
4. **Training code:** Upload to S3 first (already done: `s3://prismata-selfplay-data/deploy/training/`)
5. **On-demand** (not preemptible) — runs are <3 min, not worth preemption risk **[CHANGED]**
6. **Auto-terminate:** `sudo shutdown -h now` after training + results upload
7. **Results:** Upload to S3 bucket (`s3://prismata-selfplay-data/training-runs/$LABEL/`)

---

## Cost Budget **[CHANGED]**

| Resource | Rate | Est. Usage | Cost |
|----------|------|-----------|------|
| GCP L4 on-demand | ~$0.70/hr | ~0.5 hr | ~$0.35 |
| AWS T4 spot (×6) | ~$0.16/hr each | ~0.2 hr | ~$0.19 |
| GCS data staging (if needed) | ~$0.09/GB | 94GB one-time | ~$8.50 |
| **Total (without staging)** | | | **< $1.00** |
| **Total (with GCS staging)** | | | **< $10.00** |

Prefer AWS for data-heavy runs to avoid the staging cost.

---

## Quick Reference: Baseline Numbers **[UPDATED]**

| Metric | E2b (63K games) | 305K retrain | Target (356K, optimized) |
|--------|-----------------|-------------|--------------------------|
| Val value loss | 0.338 | — | < 0.25 |
| Val value accuracy | 86.1% | — | > 89% |
| Brier score | 0.089 | — | < 0.07 |
| Best epoch | 9 | — | 15-25 (more data + fixed schedule) |
| Tournament WR | 26.7% | **45.3%** (4,032 games) | > 48% |
| Model params | 738,945 | 738,945 | 738,945+ (if depth/capacity helps) |

---

## Appendix: Reviewer Critique Summary

Six independent reviews were solicited. Consensus themes (4+ reviewers agreeing):

1. **Joint grid > sequential sweeps** for capacity + LR (5/6 reviewers)
2. **Test depth** — 2 residual blocks is shallow (5/6)
3. **Drop 128h** — capacity-constrained, not informative (4/6)
4. **More tournament games** — 1,000 insufficient for <5pp differences (4/6)
5. **LR scaling rule doesn't apply to Adam** (3/6)
6. **Verify train/val split by game** (3/6 — already correct)
7. **Fix cosine schedule interaction with early stopping** (2/6)
8. **S3→GCP egress is expensive** (1/6 — valid, now addressed)

Key areas where reviewers lacked codebase access and made incorrect assumptions:
- Train/val split, optimizer choice, streaming shuffle, policy head isolation — all already correctly implemented
- Data augmentation suggestions (permutation, mixup) — physically invalid for this game
- GELU activation — would require C++ engine changes
