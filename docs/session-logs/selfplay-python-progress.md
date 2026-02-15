# Self-Play Python Pipeline — Progress Tracker

## Status: COMPLETE

| # | Task | Status |
|---|------|--------|
| 1 | Create `CLAUDE_selfplay_python_progress.md` | DONE |
| 2 | Create `training/load_selfplay.py` — Binary shard loader | DONE |
| 3 | Create synthetic test binary generator (`training/generate_synthetic_selfplay.py`) | DONE |
| 4 | Modify `training/train.py` — `--selfplay-dir`, `--expert-weight` args | DONE |
| 5 | Test full pipeline with synthetic data (load, train, overfit) | DONE |

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `training/load_selfplay.py` | NEW | Binary shard loader (header/CRC validation, numpy parsing, multi-shard concat) |
| `training/generate_synthetic_selfplay.py` | NEW | Synthetic test data generator (matching C++ binary format) |
| `training/train.py` | MODIFIED | Added `--selfplay-dir`, `--expert-weight`, `has_policy` mask, mixed data support |
| `CLAUDE_selfplay_python_progress.md` | NEW | This file |

## Test Results

### Synthetic data generation
- 10 games, 339 records, 2.31 MB binary file
- CRC32 validates correctly
- Outcome consistency check passes

### Self-play only training (overfit test)
```
Epochs: 50, batch=64, lr=1e-3, dropout=0.0
Train value loss: 1.08 → 0.0000 (complete memorization ✓)
Train value accuracy: 59% → 92% (high ✓)
Policy loss: 0.0 throughout (no policy targets in self-play ✓)
No NaN/Inf, no crashes ✓
```

### Mixed self-play + expert training
```
316 self-play + 316 expert (50/50 mix)
Policy loss computed only on expert records (has_policy mask ✓)
Value loss computed on all records ✓
Both heads training correctly ✓
```

### Backward compatibility (expert-only)
```
226,049 train examples, no regressions
Same metrics as before the changes ✓
```

## Notes
- Python 3.13, PyTorch 2.10.0+cpu
- Binary format: 64-byte header + N x 7152-byte records + 4-byte CRC32 footer
- feature_dim = 1785, record_size = 7152
- Split by game_id % 10 == 0 for val (deterministic, stable across runs)
- Self-play data has no policy targets — `has_policy` mask ensures policy loss only on expert records
- Expert data `train.pt` contains a `metadata` dict — handled by skipping non-tensor values during subsampling/concat
