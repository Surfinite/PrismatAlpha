# Self-Play 10K Generation & Training Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate 10,000 self-play games (MasterBot vs itself), train a neural net on the resulting data, and validate the model beats playout evaluation in tournament play.

**Architecture:** The C++ engine generates binary training data (feature vectors + outcomes) during self-play tournaments. A Python loader reads the binary shards into PyTorch tensors. The training script supports pure self-play and mixed (self-play + expert) modes. After training, weights are exported to a binary format the C++ engine can load for inference.

**Tech Stack:** C++ (game engine, feature extraction), Python/PyTorch (training), binary shard format (data interchange)

---

## Context & Current State

**Everything is implemented and verified.** This plan is purely execution:

- C++ `SelfPlayDataSink` writes binary shards with CRC32 validation (gate-checked: smoke, timing, thread safety)
- Python `load_selfplay.py` reads shards into numpy structured arrays
- `train.py` has `--selfplay-dir` flag with game-level train/val split and optional expert data mixing
- `export_weights.py` exports PyTorch weights to C++ binary format with round-trip verification
- Preview run: 8 games completed successfully (298 records, CRC valid, no NaN/Inf)

**Key metrics to beat:**
- Current neural net: 57.7% val accuracy on expert data, ~10% WR vs HardestAI, ~42% WR vs MediumAI
- Churchill's 2019 result: ~90% train accuracy on 500K self-play games, 58.8% WR vs playout eval
- Our target: >65% val accuracy, >55% WR vs OriginalHardestAI

**Hardware:** AMD Ryzen 7 5700X3D (8c/16t), 32 GB RAM, 518 GB free disk. No GPU (CPU training).

**Timing estimates:**
- Generation: ~12-16 hours at 8 threads, 2s/move (gate check: 30.3 sec/game at 1s)
- Training: ~30-60 min on CPU
- Tournament validation: ~2-4 hours for 500 games

---

### Task 1: Pre-Flight Checks

Verify everything is ready before kicking off the long generation run.

**Files:**
- Check: `bin/asset/config/config.txt` (tournament configs)
- Check: `bin/Prismata_Testing.exe` (Release build exists and is recent)
- Check: `bin/asset/config/neural_weights.bin` (needed for feature extraction)
- Check: `training/load_selfplay.py` (loader exists)
- Check: `training/train.py` (training script exists)

**Step 1: Verify Release exe is current**

The Release exe at `bin/Prismata_Testing.exe` was built Feb 14 21:48. Confirm it includes self-play infrastructure by checking its date is after the self-play code was added.

Run (from project root): `ls -la bin/Prismata_Testing.exe`
Expected: File exists, date is Feb 14 2026 or later.

**Step 2: Verify neural weights exist (needed for feature extraction)**

Run: `ls -la bin/asset/config/neural_weights.bin`
Expected: File exists (~8.4 MB). The self-play data sink calls `NeuralNet::Instance().extractFeatures()` which requires loaded weights.

**Step 3: Verify preview data loaded correctly**

Run (from project root):
```bash
cd c:/libraries/PrismataAI && python training/load_selfplay.py bin/training/data/selfplay_preview/
```
Expected: Summary showing 298 records from 8 games, no NaN/Inf, CRC valid.

**Step 4: Dry-run training on preview data**

Run:
```bash
cd c:/libraries/PrismataAI && python training/train.py \
  --selfplay-dir bin/training/data/selfplay_preview/ \
  --epochs 2 --batch-size 32 --patience 0
```
Expected: Loads 251 train / 47 val records, runs 2 epochs without errors. Accuracy doesn't matter — just verifying the data pipeline works end-to-end.

**Step 5: Verify SelfPlay_10K config is ready (but don't enable yet)**

Read `bin/asset/config/config.txt` and confirm SelfPlay_10K exists with:
- `"run":false` (will enable in Task 2)
- `"rounds":10000`, `"Threads":8`
- `"SelfPlayDataExport":{"Enabled":true, "OutputDir":"training/data/selfplay/"}`
- Players: `OriginalHardestAI_2s` and `OriginalHardestAI_Copy_2s`

Also confirm no other tournaments have `"run":true` (we don't want to accidentally run other tournaments too).

---

### Task 2: Enable and Launch 10K Self-Play Generation

**Files:**
- Modify: `bin/asset/config/config.txt` (set SelfPlay_10K to `run:true`)

**Step 1: Ensure no other tournaments are enabled**

Search config.txt for `"run":true` and disable any that are found (set to `"run":false`). Only SelfPlay_10K should be enabled.

**Step 2: Enable SelfPlay_10K**

In `bin/asset/config/config.txt`, change SelfPlay_10K from `"run":false` to `"run":true`.

**Step 3: Create the output directory**

The C++ code calls `create_directories()` but let's ensure the parent path exists:
```bash
mkdir -p c:/libraries/PrismataAI/bin/training/data/selfplay
```

**Step 4: Launch the generation run**

Run the Release exe from the `bin/` directory (paths in config are relative to CWD):
```bash
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing.exe
```

This will run unattended for ~12-16 hours. Output goes to `bin/training/data/selfplay/`.

Expected console output:
- `[SelfPlay] Initialized N sinks for N threads, feature_dim=1785, output_dir=training/data/selfplay/`
- Periodic progress updates every 30 seconds
- Files appearing in `bin/training/data/selfplay/selfplay_t*_s*.bin` + `.jsonl`

**Step 5: Monitor progress (optional)**

Check how many games have completed:
```bash
python c:/libraries/PrismataAI/training/load_selfplay.py c:/libraries/PrismataAI/bin/training/data/selfplay/ --no-crc
```

At 8 threads with 2s/move, expect ~60-80 games/hour based on the 30.3 sec/game timing at 1s.
With 2s/move the rate will be slower — roughly 30-50 games/hour, so 10K games takes 12-16 hours.

**Step 6: After generation completes, disable the tournament**

Set SelfPlay_10K back to `"run":false` in config.txt to prevent accidental re-runs.

---

### Task 3: Validate Self-Play Output Data

**Step 1: Load and summarize all shards**

Run:
```bash
cd c:/libraries/PrismataAI && python training/load_selfplay.py bin/training/data/selfplay/
```

Expected (approximate):
- ~300,000-400,000 total records (10K games x ~30-40 turns)
- ~10,000 unique games
- Outcomes: roughly 50/50 +1/-1 (self-play is symmetric)
- No NaN or Inf in features
- CRC validation passes on all shards
- Outcome consistency: OK

**Step 2: Check disk usage**

```bash
du -sh c:/libraries/PrismataAI/bin/training/data/selfplay/
```
Expected: ~2-3 GB (preview: 298 records = 2.1 MB, so 300K records ~ 2.1 GB).

**Step 3: Spot-check per-game details**

```bash
cd c:/libraries/PrismataAI && python training/load_selfplay.py bin/training/data/selfplay/ --dump
```

Check first 10 games: turn counts look reasonable (20-60 turns), outcomes alternate +1/-1 by player, no games with suspiciously few turns (<10) or many turns (>200).

---

### Task 4: Train on Self-Play Data (Pure Self-Play First)

Start with pure self-play training to establish a clean baseline. Expert data mixing comes in Task 5.

**Files:**
- Run: `training/train.py`
- Output: `training/models/best_model.pt`, `training/runs/<timestamp>.json`

**Step 1: Train value-only model on pure self-play**

Run:
```bash
cd c:/libraries/PrismataAI && python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --expert-weight 0.0 \
  --epochs 100 \
  --lr 3e-4 \
  --batch-size 512 \
  --patience 15 \
  --hidden-dim 512 \
  --num-layers 2 \
  --dropout 0.1 \
  --label-smooth 0.95
```

Key flags:
- `--expert-weight 0.0` — pure self-play, no expert data
- `--patience 15` — slightly more patience than previous runs (self-play may need more epochs)
- Rest matches previous successful training config

**Step 2: Evaluate training results**

Check the console output and `training/runs/<timestamp>.json` for:
- **Val value accuracy: target >65%** (Churchill got ~90% on 500K games; we have 10K so expect lower)
- **Val value loss: should be well below 0.88** (the 0.88 from expert data means "learned nothing")
- **Train accuracy shouldn't hit 99%+ early** — that would indicate overfitting again
- **Best epoch: should be >5** — if best is epoch 1, the model can't learn from this data either

**Step 3: Compare with expert-data baseline**

| Metric | Expert Data (section 23) | Self-Play Target | Self-Play Actual |
|---|---|---|---|
| Val value accuracy | 57.7% (chance) | >65% | ??? |
| Val value loss | 0.8826 | <0.7 | ??? |
| Best epoch | 1 | >5 | ??? |
| Train value accuracy | 98.8% (memorized) | <95% (generalizing) | ??? |

If val accuracy is below 60%, the self-play data has the same issue as expert data. In that case:
- Try larger `--hidden-dim 1024` or `--num-layers 3`
- Try without label smoothing (`--label-smooth 1.0`)
- Try lower learning rate (`--lr 1e-4`)
- Consider generating more data (50K or 100K games)

---

### Task 5: Train Mixed Model (Self-Play + Expert Data)

If Task 4 produces a model above 60% val accuracy, try mixing in expert data per the CLAUDE.md recommendation.

**Step 1: Train with 50/50 mix**

```bash
cd c:/libraries/PrismataAI && python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --expert-weight 0.5 \
  --epochs 100 \
  --lr 3e-4 \
  --batch-size 512 \
  --patience 15 \
  --hidden-dim 512 \
  --num-layers 2 \
  --dropout 0.1 \
  --label-smooth 0.95
```

**Step 2: Train with 20% expert mix**

```bash
cd c:/libraries/PrismataAI && python training/train.py \
  --selfplay-dir bin/training/data/selfplay/ \
  --expert-weight 0.2 \
  --epochs 100 \
  --lr 3e-4 \
  --batch-size 512 \
  --patience 15 \
  --hidden-dim 512 \
  --num-layers 2 \
  --dropout 0.1 \
  --label-smooth 0.95
```

**Step 3: Compare all three models**

Pick the model with the best val value loss across:
1. Pure self-play (Task 4)
2. 50/50 mix
3. 20% expert / 80% self-play

---

### Task 6: Export Best Weights

**Files:**
- Run: `training/export_weights.py`
- Output: `bin/asset/config/neural_weights.bin` (overwritten)

**Step 1: Back up current weights**

```bash
cp c:/libraries/PrismataAI/bin/asset/config/neural_weights.bin \
   c:/libraries/PrismataAI/bin/asset/config/neural_weights_expert_backup.bin
```

**Step 2: Export best model**

```bash
cd c:/libraries/PrismataAI && python training/export_weights.py \
  training/models/best_model.pt \
  --output bin/asset/config/neural_weights.bin
```

Expected: Round-trip max abs diff < 1e-5 (PASSED), ~8.4 MB output file, 26 tensors, 161 unit names.

---

### Task 7: Tournament Validation

Run the self-play-trained model against OriginalHardestAI to measure improvement.

**Files:**
- Modify: `bin/asset/config/config.txt` (enable tournament)

**Step 1: Enable NeuralAB vs OriginalHardestAI tournament**

The config already has `NeuralAB_vs_Original` (100 rounds). Enable it:
- Set `NeuralAB_vs_Original` to `"run":true`
- Ensure all other tournaments are `"run":false`

Also enable `NeuralTest` (PrismatAlpha_UCT vs OriginalHardestAI, 50 rounds) for UCT comparison.

**Step 2: Run tournament**

```bash
cd c:/libraries/PrismataAI/bin && ./Prismata_Testing.exe
```

This runs both tournaments sequentially. ~2-4 hours total.

**Step 3: Analyze results**

Check the console output for win rates.

**Success criteria:**
- **PrismatAlpha_AB vs OriginalHardestAI: >55% WR** (Churchill achieved 58.8%)
- **PrismatAlpha_UCT vs OriginalHardestAI: >30% WR** (up from 10.9% baseline)
- **PrismatAlpha_UCT vs MediumAI: >60% WR** (up from 41.7% baseline)

**Step 4: Disable tournaments**

Set both back to `"run":false`.

**Step 5: Record results in CLAUDE.md**

Update the Tournament Results Summary table and add a new section documenting:
- Self-play training metrics (val accuracy, val loss, best epoch)
- Which training variant won (pure vs mixed)
- Tournament WR results
- Comparison to Churchill's benchmarks

---

### Task 8: Decide Next Steps Based on Results

**If WR > 55% (success):**
- Proceed to iterative self-play RL (Phase 3 in CLAUDE.md):
  - Replace playout eval with trained neural net
  - Generate next 10K games with neural-MasterBot
  - Train on combined data
  - Repeat

**If 30% < WR < 55% (partial success):**
- Generate more data (50K-100K games) — linear scaling should help
- Try architectural improvements (larger hidden dim, more layers)
- Try different training hyperparameters

**If WR < 30% (insufficient improvement):**
- Investigate feature quality: compare self-play feature distributions with expert data
- Check for value target correctness (most critical invariant)
- Consider reducing think time to 1s to generate 3x more data
- Consider adding more features (Churchill included resources as one-hot encoded)

---

## Summary Table

| Task | Duration | Can Run Unattended | Dependencies |
|---|---|---|---|
| 1. Pre-flight checks | 5 min | No | None |
| 2. Launch 10K generation | 12-16 hours | **Yes** | Task 1 |
| 3. Validate output | 5 min | No | Task 2 |
| 4. Train (pure self-play) | 30-60 min | Yes | Task 3 |
| 5. Train (mixed) | 30-60 min | Yes | Task 3 |
| 6. Export weights | 2 min | No | Task 4 or 5 |
| 7. Tournament validation | 2-4 hours | Yes | Task 6 |
| 8. Decide next steps | 10 min | No | Task 7 |

**Total wall time:** ~16-22 hours (dominated by generation)
**Total active time:** ~30-60 minutes (mostly waiting)
