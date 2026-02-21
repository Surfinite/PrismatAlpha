# Context Document: PrismataAI Training Plan (Feb 19, 2026)

*For reviewers with no prior knowledge of this project. Provides all context needed to understand and critique the training plan at `docs/plans/2026-02-19-training-next-steps.md`.*

*Final (v3): incorporates 9 expert reviews + code-verified corrections.*

---

## 1. What Is This Project?

**PrismataAI** is an AI system for **Prismata**, a two-player turn-based perfect-information strategy card game by Lunarch Studios. There is no hidden information and no randomness after the initial unit pool selection. Think chess-like decision complexity but with a branching factor of ~5 possible actions per move and games lasting ~70 player-turns (~35 per side).

The AI combines:
- **Alpha-Beta search** (or UCT/MCTS) for exploring the game tree
- **Neural network position evaluation** to score board states at the leaves of the search tree

The neural net acts as the **value function** inside the search — it takes a game state and outputs a scalar in [-1, +1] predicting who will win (from the perspective of the current player to move). It does NOT select moves directly (no end-to-end RL). This is the same role as the value head in AlphaZero/Leela Chess Zero, but paired with a more traditional search algorithm.

### Why It Matters
The strongest existing AI for Prismata, **OriginalHardestAI**, uses a hand-crafted heuristic evaluation function (the "Will Score" — material counting with manually-tuned resource weights). Replacing this heuristic with a learned neural evaluation has been shown in other games (chess, Go, Hex) to dramatically improve play quality. Our goal is to exceed the hand-crafted AI's strength using a neural evaluator trained on self-play data.

---

## 2. The Neural Network

### Architecture
A small ResNet-style MLP (NOT convolutional — Prismata states are vectors, not grids):

- **Input:** 1,785-dimensional feature vector (161 unit types × 11 features each + 14 global features like resources, attack power, turn number)
- **Trunk:** Linear projection → N residual blocks (each: Linear → LayerNorm → ReLU → Dropout → Linear → LayerNorm + skip connection)
- **Value head:** Linear(hidden_dim, hidden_dim/4) → ReLU → Linear(hidden_dim/4, 1) → tanh → outputs [-1, +1]
- **Policy head:** Exists but currently unused (13% accuracy — too weak to guide search). Training uses value-only mode. Worth revisiting if accuracy improves past ~20-30% with more data.

### Model Variants Under Consideration

| Name | hidden_dim | num_layers | Parameters | Notes |
|------|-----------|------------|------------|-------|
| E2b (current best) | 256 | 2 | 739K | Deployed, 45.3% WR |
| R12_smooth90 | 256 | 3 | 871K | Best val_loss in hyperparameter sweep, untested on full data |
| 512h/2L (capacity test) | 512 | 2 | 2.6M | Previously underperformed with less data — needs retest |

The hidden dimension and number of layers are **read from the weight file header** at runtime — no C++ recompilation needed to switch between model sizes.

### How The AI Uses the Neural Net
During a game, the Alpha-Beta search explores ~2,000 positions per second per CPU core. At each leaf node, the neural net evaluates the position. The search then backs up these evaluations through the game tree using minimax to choose the best move. Search depth and time limit are configurable (typically 1-7 seconds per move).

---

## 3. Training Data

### What the Data Is
Self-play games between two copies of **OriginalHardestAI** (the hand-crafted AI, NOT the neural net). Each game produces ~37 labeled positions (one per player-turn for both sides). Each position is labeled with the eventual game outcome (+1 = current player wins, -1 = current player loses, from the perspective of the player to move).

**Crucially:** The neural net is NOT involved in data generation. This is purely supervised learning on game outcomes from the strongest hand-crafted AI playing itself. In AlphaZero terminology, this is "iteration 0" — bootstrapping from an existing strong player.

**Position correlation:** The 26.8M records are NOT independent samples. They are ~37 correlated positions per game from the same trajectory. The effective sample diversity is closer to **~726K independent games**, not 26.8M independent positions. This is important when assessing model capacity requirements.

### Data Format
Binary shards with variable size (average **23 MB**, range 0.2-51 MB), containing:
- 64-byte header (magic number, version, feature dimensions, record count)
- N records of 7,152 bytes each (1,785 floats for game state features + policy targets + value label)
- 4-byte CRC32 footer

7,804 .bin shards totaling **177 GiB** on S3. Loaded via memory-mapped streaming (numpy `mmap`) for datasets too large to fit in RAM.

### Data Volume Over Time

| Milestone | Games | Records | Date | Notes |
|-----------|-------|---------|------|-------|
| Expert replays (human games) | ~13K | ~251K | Pre-project | Online ranked games from skilled players |
| Self-play v1 | 10K | ~370K | Feb 13 | First self-play run |
| Self-play 63K | 63K | ~2.3M | Feb 15 | First big dataset |
| 305K model training data | 330K | ~12.2M | Feb 17 | Trained current best model |
| **Current dataset** | **726K** | **26.8M** | **Feb 19** | Growing at ~37K games/day |

### Data Generation Fleet
A fleet of cloud VMs runs the C++ game engine in self-play mode, generating binary shards that are uploaded to Amazon S3:

| Provider | Fleet Size | Type | Cost/hr | Status |
|----------|-----------|------|---------|--------|
| AWS EC2 | 37 spot instances | c5.2xlarge (8 vCPU) | $5.18 | Active (plan reduces to 10) |
| GCP | 6 instances | n2-standard-8 (8 vCPU) | $2.34 | Active — **plan pauses these** |
| Azure | 0 | — | $0 | Paused (too expensive) |
| **Total** | **43 instances** | **344 vCPUs** | **$7.52/hr** | **~$180/day** |

The fleet produces roughly **37,000 games per day** (empirically measured from S3 growth). Per-instance rate is ~860 games/day including boot/upload overhead.

**Credit conflict:** GCP selfplay (6× n2-standard-8) costs $56/day from the same $240 credit pool needed for GPU training. The plan pauses GCP selfplay entirely and reserves credits for training runs (~$2/run on L4). Without this change, GCP credits would be exhausted in ~4 days.

### Train/Val Split
The split is by **game**, not by record. `game_id % 10 == 0` assigns entire game trajectories (~37 records) to the validation set. This prevents leakage — no positions from the same game appear in both train and validation. Split: ~90% train (24.1M records) / ~10% val (2.7M records). The split is deterministic and stable across runs.

**game_id uniqueness:** The data loader (`load_selfplay.py`) offsets game_ids by 1,000,000 per source directory, ensuring global uniqueness even when individual generator processes start local IDs at 0. The modulo split operates on these globally-unique IDs.

---

## 4. Training Infrastructure

### Available Compute for Training (NOT data generation)

| Resource | GPU | System RAM | Local Storage | Cost | Quota/Limits |
|----------|-----|-----------|---------------|------|-------------|
| **AWS g6.2xlarge** (spot) | NVIDIA L4 (24GB VRAM, 30 TFLOPS) | 32 GB | 450 GB NVMe | ~$0.40/hr | 8 vCPU quota (1 instance) |
| **AWS g4dn.xlarge** (spot) | NVIDIA T4 (16GB VRAM, 8 TFLOPS) | 16 GB | 125 GB NVMe | ~$0.20/hr | Shares same 8 vCPU quota |
| **GCP g2-standard-4** | NVIDIA L4 (24GB VRAM) | 16 GB | 250 GB disk | ~$0.70/hr | 1 GPU globally (free credits) |
| **Local** (developer machine) | Intel Arc B580 (12GB VRAM) | 32 GB | SSD | Free | Always available |

**Key constraints:**
- AWS GPU quota = 8 vCPUs for G/VT spot (1 g6.2xlarge at a time). Increase pending.
- GCP = 1 GPU globally. ~$240 free credits remaining.
- Local XPU = free, always available, but serial only.

### Training Time Estimates (CORRECTED)

**Important:** An "epoch" in `train.py` is a **full pass over all training records** — with 24.1M training records at batch_size=512, that is **~47,100 batches per epoch**. Earlier estimates of "5s/epoch" and "13s/epoch" were measured on a 100K-record subset, not the full dataset.

| Platform | Per-Epoch Time (26.8M records) | Typical Run (early stop at 5-15 epochs) | Data Download |
|----------|-------------------------------|---------------------------------------|---------------|
| **NVIDIA L4** (AWS/GCP, NVMe) | ~10-15 min | **1-4 hours** | ~22 min from S3 |
| **NVIDIA T4** (AWS) | ~15-20 min | **1.5-5 hours** | ~22 min from S3 |
| **Intel Arc B580** (local XPU) | ~30 min | **2.5-7.5 hours** | 0 (data local) |
| **CPU only** (Ryzen 7) | ~90 min | **7.5-22 hours** | 0 |

**With `--eval-every-steps 5000`:** Step-level evaluation (full val set each time, ~2 min on L4, ~6 min on XPU) gives faster feedback (~9.4 evals per epoch). With patience=25, early stopping triggers after ~2.7 epochs (~80 min on XPU, ~30 min on L4) of no improvement, reducing typical run time to **1-4 hours**.

**The bottleneck is I/O, not GPU compute.** The model is tiny (~800K params); forward/backward passes are microseconds per batch. Training speed is dominated by reading 177 GiB of memory-mapped data from disk. NVMe (g6.2xlarge: 450GB) is fastest; local SSD is adequate; HDD would be very slow.

### Storage & RAM

**Storage:** g6.2xlarge (450GB NVMe) fits the 177GB dataset easily. GCP (250GB disk) is tighter — ~73GB free after data download; works but approaching the limit as data grows. S3 download time is linear: ~22 min now, ~30 min by Day 7 as data grows to ~240GB.

**RAM:** Streaming mode (`--streaming` flag) uses memory-mapped files with ~12GB peak RAM, regardless of dataset size. All platforms have ≥16GB. No RAM upgrade needed. The only scenario requiring more RAM is non-streaming mode (loads all data into memory), which needs >50GB for the full dataset — not practical on any current hardware.

---

## 5. Results So Far

### Win Rate Progression (vs OriginalHardestAI)

This is our primary metric. The opponent is the strongest hand-crafted AI, using Alpha-Beta search with the manually-tuned "Will Score" heuristic. Higher is better. 50% means we match the hand-crafted AI.

| Model | Training Data | Win Rate | Games Played | Date |
|-------|--------------|----------|-------------|------|
| Pre-fix model | ~13K expert games | 3.6% | 1,120 | Feb 16 |
| E1b (512h/2L) | 63K games (2.3M records) | 19.6% | 1,008 | Feb 17 |
| E2b (256h/2L) | 63K games (2.3M records) | 26.7% | 1,008 | Feb 17 |
| R12_smooth90 (256h/3L) | **14K games (500K records)** | 19.3% | 11,060 | Feb 19 |
| **E2b (256h/2L)** | **330K games (12.2M records)** | **45.3%** | **4,032** | **Feb 18** |

### Key Observations

1. **Data quantity dominates everything else.** The same E2b architecture went from 26.7% → 45.3% WR just by training on 5x more data. Meanwhile R12_smooth90 (better architecture, better hyperparameters) achieved only 19.3% WR because it was limited to 500K records due to a RAM constraint on GCP.

2. **The 256h/3L (R12) architecture has the best validation loss** in hyperparameter sweeps but has never been tested on the full dataset. It was crippled by the GCP instance's 16GB RAM limit, which forced `--max-records 500000`. The `--streaming` flag now removes this limitation.

3. **The 512h model previously underperformed (19.6% vs 26.7% for 256h)** — but it was trained on the same small 63K-game dataset. With 726K games, the larger model may outperform the smaller one. This is a critical test (Run C in the plan).

4. **Position correlation matters for capacity assessment.** The 256h model has ~800K params trained on ~726K effectively-independent games. This is a 1:1 ratio — tight for neural networks. The 512h model (2.6M params) has a 3.6:1 ratio, which may be better positioned to extract more signal from the data.

### Data Scaling Projection

Based on two data points and power-law scaling research (Neumann et al. 2024, Jones 2021):

```
Empirical:     63K games → 26.7% WR  (~-180 Elo)
               330K games → 45.3% WR (~-35 Elo)    (+145 Elo from 5.2x data)

Conservative:  726K games → 48-56% WR (wide range — only 2 data points)
```

**Why the wide range:** Power-law scaling works well in Elo space (log-linear in data), but converting back to WR introduces non-linearity. Additionally, model capacity saturation could flatten the curve at any point. The estimate is intentionally conservative.

### Note on Churchill's Published Result
David Churchill (the original Prismata AI researcher) reported achieving **58.8% WR with 500K games** in his published work. However, this was measured against a **playout AI** (symmetric playouts to game end), which is a **weaker opponent** than our benchmark (OriginalHardestAI = Alpha-Beta + Will Score heuristic). **These numbers are not directly comparable.** Churchill's result demonstrates that self-play data can produce strong neural evaluators for Prismata, but should not be used as a numeric target for our WR metric.

---

## 6. What the Plan Proposes

### 24-Hour Plan (constrained: no new compute for 24h)

1. **Train three models on the full 726K-game dataset** — 256h/2L (baseline), 256h/3L (best architecture), and 512h/2L (capacity test). Run locally on XPU and on GCP (free credits) in parallel. Expected training time: 2-5 hours per run. Results by morning.

2. **Reduce selfplay fleet** from 43 to 10 AWS instances and pause GCP selfplay (saving ~$146/day). We have enough data; training is the bottleneck. GCP credits reserved for GPU training.

3. **Tournament evaluation** — play 8,000+ games per model vs OriginalHardestAI to measure WR with statistical confidence (±1.1% at 50% WR).

### 7-Day Plan

Days 1-2: Three baseline runs + 2³ factorial hyperparameter sweep (LR × dropout × smoothing, 8 runs on capped data for speed).
Days 3-4: Tournament evaluation, crown a champion, secondary evaluations (weaker opponents, head-to-head).
Days 5-6: Iteration 2 engineering prep only — benchmark C++ NN inference speed, design self-play config. Do NOT start neural self-play data generation until model achieves >55% WR.
Day 7: Assess trajectory, plan forward.

---

## 7. Concepts a Reviewer Should Know

### Alpha-Beta Search
A game tree search algorithm that evaluates positions by looking ahead many moves and assuming both players play optimally (minimax). Prunes branches that can't affect the result (alpha-beta cutoff). Requires an **evaluation function** to score positions at the search frontier — this is what the neural net provides.

### Self-Play Data Generation
Two copies of the same AI play against each other. Each game produces training examples: (board state, game outcome) pairs. The AI used for generation does NOT need to be the neural net — it can be any AI. Currently we use the hand-crafted OriginalHardestAI. In iteration 2, we would switch to the neural-net-guided AI to generate higher-quality data — but this carries risks (see below).

### Model Gating (AlphaZero Pattern)
Before deploying a new model for self-play data generation, it must demonstrate it's actually stronger than the current model. Standard practice: play 1,000+ evaluation games between old and new models. Only deploy if the new model wins >55%. This prevents **regression cascades** — a slightly weaker model generating subtly worse data, which trains an even worse model, amplifying errors. Model gating is the safety valve.

### Streaming / Memory-Mapped Training
When the dataset is too large to fit in RAM (177GB >> 32GB), the data is stored on disk and accessed via memory-mapped files. The operating system's virtual memory manager pages data in and out as needed. This is transparent to the training code — it just looks like a very large array. The trade-off is slower random access (disk reads vs RAM reads), mitigated by NVMe storage and DataLoader prefetching.

### Win Rate vs Elo
Win rate (WR) is our primary metric but has a non-linear relationship with skill difference:
- 45% WR ≈ -35 Elo below the opponent
- 50% WR = equal strength
- 55% WR ≈ +35 Elo above
- 60% WR ≈ +72 Elo above

This means going from 45% → 50% is a smaller skill improvement than going from 50% → 55%, even though both are +5 percentage points. The practical implication: early WR gains are "easier" than later ones. Scaling analysis should be done in **Elo space** (roughly linear in log(data)) rather than WR space.

### Data Scaling Laws
Research on AlphaZero, Leela Chess Zero, and other game AIs shows that performance (measured in Elo) scales as a **power law** with training data: `Elo ∝ data^α` where α is typically 0.3-0.7. This means each doubling of data gives a roughly fixed Elo increment. But since WR is a sigmoid function of Elo, the WR improvement per doubling **decreases as the model gets stronger**. Eventually, model capacity becomes the bottleneck and more data stops helping — at that point, a larger model is needed.

### Label Smoothing
Instead of training on hard labels (+1 win, -1 loss), we soften them slightly (e.g., +0.95, -0.95 with smoothing=0.95). This prevents the model from becoming overconfident and improves generalization. Our hyperparameter sweep found that smoothing=0.90 gave the best validation loss (on a small subset — may differ on full data).

### Early Stopping & Patience
Training runs for up to N epochs, stopping early if validation loss hasn't improved for P consecutive evaluation cycles ("patience"). With `--eval-every-steps 5000`, each evaluation cycle runs the **full validation set** (2.7M records, ~5,300 forward-pass batches — no gradients) every 5,000 training steps. There are ~9.4 eval cycles per epoch. With patience=25, the model must go ~2.7 full epochs without improvement before stopping. This is more conservative than epoch-level patience (where patience=25 would be 25 full epochs) but gives faster feedback than waiting for full-epoch evaluations.

---

## 8. Key Constraints & Trade-offs

### Compute Budget
| Resource | Constraint | Impact |
|----------|-----------|--------|
| AWS GPU spot quota | 8 vCPUs (1 g6.2xlarge at a time) | Can't run parallel training on AWS |
| GCP GPU quota | 1 GPU globally | Can't run parallel on GCP either |
| GCP free credits | ~$240 remaining | Primary training resource (free) |
| Selfplay fleet | $180/day ongoing (plan reduces to $34/day) | GCP selfplay paused, AWS cut to 10 |
| Local GPU (Arc B580) | Always available, free | ~30 min/epoch, serial only |

### The Data-vs-Compute Trade-off
Data generation costs **$180/day** (before reduction). Training costs **$0-2 per run** (free locally, ~$2 on GCP credits). Each training run takes **2-5 hours**. This means:

- The most expensive activity is generating data we may not need
- The cheapest activity is running more training experiments
- The highest-ROI action is training on the 726K games we already have
- Parallelism matters: with local XPU + GCP L4, we can run 2 experiments simultaneously for free
- The plan reduces fleet to 10 AWS instances ($34/day) and pauses GCP selfplay to preserve training credits

### Storage Is Tight on GCP
The g6.2xlarge has 450GB NVMe (177GB dataset = 39% used). GCP has 250GB total — after OS (~20GB) and data (177GB), only **~53GB free**. Sufficient for training artifacts (checkpoints ~4MB each, logs tiny) but fragile if data grows. If data exceeds ~200GB at launch time, GCP training should cap records with `--max-records`. Storage becomes a hard constraint on GCP around ~230GB of data — several weeks away at current growth rate. AWS (450GB NVMe) has no such constraint.

### RAM Is Not a Problem
Streaming mode keeps peak RAM at ~12GB regardless of dataset size. All platforms have ≥16GB. No upgrade needed.

---

## 9. What Could Go Wrong

| Risk | Explanation | Likelihood |
|------|------------|------------|
| **Model capacity saturation** | The 256h model (~800K params) has roughly 1 parameter per independent game (~726K games). This is tight. Symptom: WR barely improves despite 2.2x more data. Mitigation: 512h model (Run C) tested proactively on Day 1. | Medium-High |
| **Diminishing returns on data** | Power-law scaling means each doubling gives less WR improvement. We may be on the diminishing-returns tail. | Medium |
| **Data quality ceiling** | Self-play from the hand-crafted AI can only teach patterns the heuristic AI exhibits. Iteration 2 (neural self-play) would break this ceiling — but carries engineering and regression risks. | Medium-term |
| **Iteration 2 regression cascade** | If we start neural self-play too early (model ≤50% WR), the data quality may decrease rather than increase, leading to a downward spiral. Mitigation: strict model gating (>55% WR) and small pilot (10K games). | Medium (if attempted prematurely) |
| **NN inference too slow for self-play** | The C++ engine evaluates ~2,000 positions/sec with playout eval. Neural eval may be slower, reducing self-play throughput. Must benchmark before committing to iteration 2. | Medium |
| **Training takes longer than expected** | Full-dataset training takes hours, not minutes. A run that takes 6 hours instead of 3 delays the evaluation pipeline. Mitigation: use `--eval-every-steps` for faster feedback; start runs in parallel on local + GCP. | Low-Medium |
| **Overfitting** | Unlikely with early stopping (patience=25 eval cycles ≈ 2.7 epochs tolerance). Train/val split is by game (no leakage, game_ids globally unique). The ~2.7M validation records provide a reliable signal. | Low |
| **Cloud-init timeout** | AWS spot instances kill scripts after ~22 min. S3 download takes ~22 min. Workaround: `nohup` pattern (tested). | Medium (known, mitigated) |

---

## 10. Questions for the Reviewer

1. **Is the data scaling projection reasonable?** We extrapolate 726K games → 48-56% WR from two data points. The wide range reflects genuine uncertainty. Does this seem appropriately calibrated?

2. **Is 256h likely to saturate?** ~800K params / ~726K independent games ≈ 1:1 ratio. Is this tight enough to warrant prioritising 512h (3.6:1 ratio)?

3. **Fleet reduction: how aggressive?** The plan proposes cutting from 43 to 10 AWS instances ($34/day) and pausing GCP selfplay entirely (preserving credits for training). A full 12-24h pause is also an option. Is 726K games enough to answer all the questions we need to, or should we keep generating?

4. **Iteration 2 timing and gating:** We defer neural self-play to >55% WR with a 10K-game pilot. Too conservative? Too aggressive? Should the threshold be higher (60%)?

5. **Evaluation methodology:** Primary: WR vs OriginalHardestAI (8,000 games). Secondary: head-to-head vs previous model. Should we add other opponents (weaker AIs, different time controls) for generalization checks?

6. **Architecture priority:** We test 256h/2L, 256h/3L, and 512h/2L in parallel on Day 1. If we had to pick only two, which pair is most informative?
