# Streaming DataLoader Silent Crash Analysis

**Date:** Feb 19, 2026
**Status:** Investigation complete, fixes not yet applied
**Commit context:** Post-9fc9587 (streaming mode mmap-to-file-IO fix)

## Problem

`train.py --streaming` dies silently after printing the training header. No error, no traceback, even with `PYTHONFAULTHANDLER=1`. Non-streaming mode works. Crash reproduces on both `--device xpu` and `--device cpu`, and with `--num-workers 0`.

## Key Facts

- 27.4M records indexed across 8,000+ shards (182 GB)
- Shard indexing works (10s)
- Single 512-record batch loads fine in isolation
- Process dies between sanity check output and first training step output

## Root Causes (4 interacting issues)

### 1. `all_vpreds` accumulation in `train_epoch()` — LIKELY CRASH TRIGGER

`train.py:258` initializes `all_vpreds = []`, and `train.py:295` appends every batch's predictions:

```python
all_vpreds.append(value_pred.detach().cpu())  # called 48,242 times
```

Then `train.py:299` concatenates all of them:

```python
all_vpreds = torch.cat(all_vpreds)  # 48K tensors -> 24.7M elements
```

Creates 48,242 individual tensor objects in a Python list, then tries to `torch.cat` them into one contiguous tensor. In non-streaming mode, this same code handles only ~195 tensors (250x fewer). The massive number of tensor objects creates GC pressure and the `torch.cat` over 48K inputs is an unusual workload.

### 2. `torch.randperm(N).tolist()` — 890 MB memory spike

PyTorch's `RandomSampler.__iter__()` internally does:

```python
yield from torch.randperm(24_700_000, generator=generator).tolist()
```

`.tolist()` converts to a Python list of 24.7M individual int objects = ~890 MB. This is the single largest memory allocation, happening before the first batch. Non-streaming equivalent: ~3.6 MB.

### 3. 24.7M file open/close operations per epoch — extreme I/O

Each `__getitem__` (`load_selfplay.py:319-321`) does individual `open()/seek()/read()/close()`:

```python
with open(shard['path'], 'rb') as f:
    f.seek(offset)
    record_bytes = f.read(shard['record_size'])
```

With batch_size=512 and ~48K batches = 24.7M file operations per epoch. At ~1-2ms each on Windows NTFS = **7-14 hours per epoch** with zero output. File system cache gets thrashed across 8,000+ shards with random access.

### 4. `pin_memory=True` with XPU runtime

Both streaming (`train.py:898`) and non-streaming (`train.py:941`) use `pin_memory=True`. DataLoader passes `device=None` to `tensor.pin_memory()`. With PyTorch 2.10.0+xpu installed, `torch.xpu.is_available()` returns True regardless of `--device cpu`, so pin_memory may use XPU-specific pinning on every batch. Any resource leak gets amplified 250x (48K vs 195 batches).

## Why Silent Death

Most likely scenario:

1. Process enters `train_epoch()`, RandomSampler allocates ~890 MB
2. Iteration begins — 512 file I/O ops per batch, zero output (default `eval_every_steps=0`)
3. Process killed by one of:
   - **Windows OOM-terminate** (commit charge exceeds limits — no traceback, no faulthandler)
   - **XPU pin_memory native crash** (structured exception bypasses Python faulthandler)
   - **`torch.cat` over 48K tensors** never reached because process dies during iteration

Key differentiator: **48,242 batches vs ~195 batches**. Everything that works at 195 becomes 250x more demanding.

## Recommended Fixes (priority order)

### Fix 1: `pin_memory=False` for streaming mode
Eliminates XPU pin_memory risk. Streaming I/O is already the bottleneck — pinned memory provides zero benefit.

```python
# train.py line 896-902
pin = not streaming_mode  # or: pin_memory=(device.type != "cpu")
train_loader = DataLoader(..., pin_memory=pin, ...)
val_loader = DataLoader(..., pin_memory=pin, ...)
```

### Fix 2: Don't accumulate `all_vpreds` in streaming mode
Replace the 48K-tensor list + `torch.cat` with running statistics:

```python
# In train_epoch(), replace all_vpreds list with running stats:
vpred_sum = 0.0
vpred_sq_sum = 0.0
vpred_min = float('inf')
vpred_max = float('-inf')
vpred_count = 0
# ... update per batch instead of appending tensors
```

### Fix 3: Default `eval_every_steps` for streaming
When `--streaming` is used and `eval_every_steps` is not explicitly set, default to ~5000 steps. Gives output every ~5 minutes instead of every ~13 hours.

### Fix 4: Batch file I/O by shard
Sort each batch's record indices by shard ID, read all records from the same shard in one `open()` call. Could use a custom collate function or a `BatchSampler` that groups by shard.

More ambitious: pre-read entire shards into a cache (LRU cache of N most recent shards in memory).

## Files to Modify

| File | Change |
|---|---|
| `training/train.py:896-902` | `pin_memory=False` for streaming DataLoaders |
| `training/train.py:246-326` | Running value stats instead of `all_vpreds` accumulation |
| `training/train.py:330-409` | Same for `eval_epoch` (`all_vpreds` + `all_targets` lists) |
| `training/train.py:691` | Auto-set `eval_every_steps` when streaming |
| `training/load_selfplay.py:310-342` | (Optional) Batch I/O optimization in `__getitem__` |
