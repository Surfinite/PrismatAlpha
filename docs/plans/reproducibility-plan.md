# Implementation Plan: Reproducibility Standard for Training

**Date:** 2026-02-17
**Status:** PLANNED
**Goal:** Enable reproducible multi-seed training runs so finalist configurations can be validated with 3+ seeds
**Source:** v2 experiment plan Section 11 "Reproducibility" (`docs/plans/hyperparameter-experiments-v2.md:585-586`)

---

## Phase 0: Documentation Discovery — COMPLETE

### Current State (verified via code inspection)

**No seed control exists in `training/train.py`.** Zero calls to `torch.manual_seed`, `np.random.seed`, or `random.seed`.

### Randomness Sources in train.py

| Source | Location | Seeded? |
|--------|----------|---------|
| PyTorch weight init (`nn.Linear`, `nn.LayerNorm`) | train.py:88-115 (model creation) | No |
| Dropout masks | train.py:95 (`nn.Dropout`) | No |
| DataLoader shuffle | train.py:816 (`shuffle=True`) | No — no `generator` arg |
| Expert subsampling | train.py:729 (`torch.randperm`) | No |
| numpy (not used directly) | — | N/A |

### Already Deterministic (no changes needed)

| Component | Why |
|-----------|-----|
| Data loading order | `load_selfplay.py:145` uses `sorted(glob.glob(...))` |
| Train/val split | `train.py:487` uses `game_id % 10 == 0` (deterministic modulo) |
| Shard game_id namespacing | `load_selfplay.py` offsets 1M per directory (stable for same dataset) |

### Existing Experiment Logging

- Run logs: `training/runs/{timestamp}.json` (train.py:875-878)
- Hyperparameters dict: train.py:883-903 — **no seed field**
- Log write: single `json.dump` at end of training (train.py:1151-1152) — **crash loses log**
- No `--seed` CLI argument exists

### Anti-Patterns to Avoid

- Do NOT use `torch.backends.cudnn.deterministic = True` — we train on CPU, this is irrelevant and adds confusion
- Do NOT use `torch.use_deterministic_algorithms(True)` — this can break operations and is not needed for statistical reproducibility across seeds (we want *controlled* randomness, not eliminated randomness)
- Do NOT create a separate multi-seed runner script — keep it simple with a `--seed` arg and a bash loop

---

## Phase 1: Add `--seed` CLI Arg + Seed-Setting Function

**What to implement:**

### 1a. Add `--seed` argument to argparse

**File:** `training/train.py`, after line 674 (last current argument)

```python
parser.add_argument("--seed", type=int, default=None,
                    help="Random seed for reproducibility. If not set, uses random seed and logs it.")
```

### 1b. Add seed-setting function

**File:** `training/train.py`, add near top-level functions (before `main()`)

```python
def set_seed(seed):
    """Set all random seeds for reproducibility."""
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
```

This covers:
- `torch.manual_seed` → weight init, dropout masks, `torch.randperm`, DataLoader shuffle (via default generator)
- `np.random.seed` → any future numpy randomness
- `random.seed` → Python stdlib

### 1c. Call seed function early in `main()`

**File:** `training/train.py`, after line 675 (`args = parser.parse_args()`) and before line 677 (overfit test)

```python
# Seed for reproducibility
if args.seed is None:
    args.seed = torch.randint(0, 2**31, (1,)).item()
actual_seed = args.seed
set_seed(actual_seed)
print(f"Random seed: {actual_seed}")
```

This ensures: if no seed given, a random one is chosen and **logged**, so any run can be reproduced after the fact.

### 1d. Add DataLoader `generator` for deterministic shuffle

**File:** `training/train.py`, before line 816 (train_loader creation)

```python
g = torch.Generator()
g.manual_seed(actual_seed)
```

Then modify line 816:
```python
train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                          drop_last=True, num_workers=use_workers,
                          persistent_workers=use_workers > 0, pin_memory=True,
                          generator=g)
```

**Why:** `torch.manual_seed` seeds the *default* generator, but DataLoader creates its own if not provided. Passing an explicit generator ensures the shuffle order is controlled.

### Verification Checklist

- [ ] `python training/train.py --seed 42 --selfplay-dir ... --value-only --epochs 1` prints "Random seed: 42"
- [ ] Running the same command twice produces identical epoch 1 metrics (val_value_loss, val_value_acc)
- [ ] Running without `--seed` prints a random seed and logs it
- [ ] `grep -n "seed" training/train.py` shows the new code
- [ ] No `cudnn` or `deterministic_algorithms` calls added

---

## Phase 2: Log Seed in Experiment JSON

**What to implement:**

### 2a. Add seed to hyperparameters dict

**File:** `training/train.py`, in the `run_log` dict at line 883

Add to the hyperparameters dict (after line 902):
```python
"seed": actual_seed,
```

### 2b. Make `actual_seed` available at log-writing scope

The `actual_seed` variable from Phase 1c is set in `main()` scope, same as where `run_log` is built — no extra plumbing needed.

### Verification Checklist

- [ ] Run training, check `training/runs/{latest}.json` contains `"seed": <number>` in hyperparameters
- [ ] Seed value matches what was printed to console

---

## Phase 3: Multi-Seed Comparison Utility

**What to implement:** A lightweight script that reads multiple run JSONs and compares metrics across seeds.

### 3a. Create `training/compare_seeds.py`

**File:** New file `training/compare_seeds.py`

Accepts a list of run JSON paths (or a glob pattern). Outputs:
- Table of key metrics per run: seed, best_val_value_loss, best_val_value_acc (from best epoch), best_epoch, wall_time
- Mean and std across runs
- Whether the runs used identical hyperparameters (warn if not)

Example usage:
```bash
# After running 3 seeds:
PYTHONUNBUFFERED=1 python training/train.py --seed 42 --selfplay-dir ... --value-only --epochs 100 ...
PYTHONUNBUFFERED=1 python training/train.py --seed 123 --selfplay-dir ... --value-only --epochs 100 ...
PYTHONUNBUFFERED=1 python training/train.py --seed 456 --selfplay-dir ... --value-only --epochs 100 ...

# Compare:
python training/compare_seeds.py training/runs/20260217_*.json
```

Expected output format:
```
Comparing 3 runs (identical hyperparameters confirmed):
  Loss fn: mse, LR: 1e-05, Hidden: 512, Dropout: 0.1

  Seed   | Best Val Loss | Best Val Acc | Best Epoch | Wall Time
  -------|---------------|-------------|------------|----------
  42     | 0.5032        | 78.4%       | 8          | 702s
  123    | 0.5089        | 78.1%       | 11         | 715s
  456    | 0.5011        | 78.7%       | 9          | 698s
  -------|---------------|-------------|------------|----------
  Mean   | 0.5044        | 78.4%       | 9.3        | 705s
  Std    | 0.0040        | 0.3%        | 1.5        | 8.9s
```

### Implementation notes

- Read each JSON, extract `hyperparameters`, `best_val_value_loss`, `best_epoch`, `total_wall_time_s`
- For `best_val_value_acc`: look up the epoch entry matching `best_epoch` in the `epochs` array (field: `val_value_acc`)
- Compare hyperparameters dicts (exclude `seed`) — warn if they differ
- Use only stdlib (`json`, `os`, `sys`, `statistics`) — no external dependencies

### Verification Checklist

- [ ] `python training/compare_seeds.py training/runs/file1.json training/runs/file2.json` produces formatted table
- [ ] Warns when hyperparameters differ between runs
- [ ] Handles single-file input gracefully (no std calculation)
- [ ] Script is <100 lines

---

## Phase 4: Final Verification

### Reproducibility Proof

Run the same configuration with `--seed 42` twice. Verify:

```bash
# Run 1
PYTHONUNBUFFERED=1 python training/train.py --seed 42 --selfplay-dir bin/training/data/selfplay/ --value-only --epochs 2 --batch-size 512 --lr 1e-5 --patience 0 --max-records 100000 --num-workers 0

# Run 2 (identical)
PYTHONUNBUFFERED=1 python training/train.py --seed 42 --selfplay-dir bin/training/data/selfplay/ --value-only --epochs 2 --batch-size 512 --lr 1e-5 --patience 0 --max-records 100000 --num-workers 0
```

Both runs should produce **identical** val_value_loss and val_value_acc at epoch 1 and 2.

**Note:** Use `--num-workers 0` for deterministic verification. With `num_workers > 0`, PyTorch DataLoader worker seeding can introduce platform-dependent variation. For production multi-seed runs, `num_workers > 0` is fine — the goal is statistical reproducibility (same seed = same result), not cross-platform bit-exactness.

### Grep Checks

```bash
# Seed control exists
grep -n "manual_seed\|set_seed\|--seed" training/train.py

# No anti-patterns
grep -n "cudnn\|deterministic_algorithms" training/train.py  # should return nothing

# Seed logged in JSON
python -c "import json; d=json.load(open('training/runs/<latest>.json')); print('seed' in d['hyperparameters'])"
```

### End State

After all phases:
- Every training run logs its seed (auto-generated or user-specified)
- Any run can be reproduced by passing the same `--seed`
- Multi-seed comparison is a one-liner: `python training/compare_seeds.py <glob>`
- v2 plan's reproducibility standard is met: "rerun with 3 different random seeds" is trivial

---

## Scope & Complexity

| Phase | Changes | Est. Lines | Files |
|-------|---------|-----------|-------|
| 1 | Seed arg + set_seed + DataLoader generator | ~20 | train.py |
| 2 | Log seed in JSON | ~1 | train.py |
| 3 | compare_seeds.py | ~80 | new file |
| 4 | Verification only | 0 | — |

**Total: ~100 lines of code across 2 files.** No architectural changes. No dependencies added.
