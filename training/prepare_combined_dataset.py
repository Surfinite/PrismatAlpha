"""
Prepare combined Human + MasterBot training dataset.

1. Filter MB JSONL to only games using indexed units
2. Fix game_date format (ISO string → unix timestamp)
3. Vectorize filtered MB data → HDF5
4. Merge human temporal_train.h5 + MB HDF5 → combined_train.h5
5. Keep human temporal_val.h5 as validation (clean baseline)

Usage:
    python training/prepare_combined_dataset.py
"""

import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

import h5py
import numpy as np


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT_INDEX_PATH = os.path.join(REPO, "training", "data", "unit_index.json")
MB_FLEET_DIR = os.path.join(REPO, "training", "data", "masterbot_fleet")
FILTERED_JSONL = os.path.join(REPO, "training", "data", "mb_fleet_filtered.jsonl")
MB_HDF5 = os.path.join(REPO, "training", "data", "mb_fleet.h5")
HUMAN_TRAIN = os.path.join(REPO, "training", "data", "splits", "temporal_train.h5")
HUMAN_VAL = os.path.join(REPO, "training", "data", "splits", "temporal_val.h5")
COMBINED_TRAIN = os.path.join(REPO, "training", "data", "splits", "combined_train.h5")
COMBINED_VAL = os.path.join(REPO, "training", "data", "splits", "combined_val.h5")
SCHEMA_PATH = os.path.join(REPO, "training", "schema_v1.json")
VECTORIZE_SCRIPT = os.path.join(REPO, "training", "vectorize.py")


def clean_unit_name(name):
    """Match vectorize.py's cleaning logic."""
    if name.startswith('*'):
        name = name[1:]
    name = re.sub(r'^\d+-?', '', name)
    return name


def iso_to_unix(date_str):
    """Convert ISO date string to unix timestamp."""
    if not date_str or isinstance(date_str, (int, float)):
        return int(date_str) if date_str else 0
    try:
        # Handle "2026-03-10T00:43:54.255Z" format
        date_str = date_str.rstrip('Z')
        if '.' in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        return int(dt.timestamp())
    except (ValueError, OSError):
        return 0


def step1_filter_mb_data():
    """Filter MB fleet JSONL to only games with indexed units, fix dates."""
    print("=" * 60)
    print("STEP 1: Filter MB fleet data to indexed units only")
    print("=" * 60)

    # Load unit index
    with open(UNIT_INDEX_PATH, "r", encoding="utf-8") as f:
        unit_index = json.load(f)["units"]
    indexed_names = set(unit_index.keys())
    print(f"  Unit index: {len(indexed_names)} units")

    # Find all JSONL files
    pattern = os.path.join(MB_FLEET_DIR, "**", "*.jsonl")
    files = sorted(glob.glob(pattern, recursive=True))
    print(f"  Found {len(files)} JSONL files in fleet dir")

    if not files:
        print("  ERROR: No JSONL files found!")
        return False

    # Single pass: check each record's card_set, write valid ones.
    # Note: replay codes (e.g. "matchup_g0001") are NOT unique across instances,
    # so we must check every record individually.
    total = 0
    kept = 0
    skipped = 0
    unk_units = set()
    t0 = time.time()

    print(f"  Filtering to {FILTERED_JSONL}")
    with open(FILTERED_JSONL, "w", encoding="utf-8") as out:
        for fi, fpath in enumerate(files):
            with open(fpath, "r", encoding="utf-8") as f:
                # Check card_set of first record per file to determine if entire file is valid
                # (all records in a file share the same instance, and each worker generates
                # games with different card sets, so we need per-record checking)
                for line in f:
                    total += 1
                    ex = json.loads(line)

                    # Check card_set for non-indexed units
                    has_unknown = False
                    card_set = ex.get("card_set", [])
                    for card_name in card_set:
                        cname = clean_unit_name(card_name)
                        if cname not in indexed_names:
                            has_unknown = True
                            unk_units.add(cname)
                            break

                    if has_unknown:
                        skipped += 1
                        continue

                    # Fix game_date: ISO string → unix timestamp
                    ex["game_date"] = iso_to_unix(ex.get("game_date", 0))

                    # MB data has no ratings — set to 0
                    ex.setdefault("rating_p0", 0)
                    ex.setdefault("rating_p1", 0)

                    out.write(json.dumps(ex, separators=(',', ':')) + "\n")
                    kept += 1

            if (fi + 1) % 50 == 0:
                elapsed = time.time() - t0
                print(f"    Processed {fi+1}/{len(files)} files, kept {kept:,}/{total:,}, "
                      f"{elapsed:.0f}s")

    elapsed = time.time() - t0
    pct = 100 * kept / total if total else 0
    print(f"  Done: {kept:,}/{total:,} records kept ({pct:.1f}%), {skipped:,} skipped, {elapsed:.0f}s")
    if unk_units:
        print(f"  {len(unk_units)} non-indexed card_set unit types found: {sorted(unk_units)[:10]}...")
    return True


def step2_vectorize_mb():
    """Vectorize filtered MB JSONL → HDF5."""
    print("\n" + "=" * 60)
    print("STEP 2: Vectorize filtered MB data")
    print("=" * 60)

    cmd = [
        sys.executable, VECTORIZE_SCRIPT,
        "--input", FILTERED_JSONL,
        "--output", MB_HDF5,
        "--schema", SCHEMA_PATH
    ]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO)
    if result.returncode != 0:
        print("  ERROR: Vectorization failed!")
        return False
    print("  Vectorization complete.")
    return True


def step3_merge_datasets():
    """Merge human temporal_train + MB HDF5 → combined_train.h5."""
    print("\n" + "=" * 60)
    print("STEP 3: Merge human (80%) + MasterBot datasets")
    print("=" * 60)

    if not os.path.exists(HUMAN_TRAIN):
        print(f"  ERROR: Human train not found: {HUMAN_TRAIN}")
        return False
    if not os.path.exists(MB_HDF5):
        print(f"  ERROR: MB HDF5 not found: {MB_HDF5}")
        return False

    with h5py.File(HUMAN_TRAIN, "r") as hf:
        n_human = hf["features"].shape[0]
        state_dim = hf["features"].shape[1]
        print(f"  Human train: {n_human:,} examples, state_dim={state_dim}")

    with h5py.File(MB_HDF5, "r") as mf:
        n_mb = mf["features"].shape[0]
        mb_dim = mf["features"].shape[1]
        print(f"  MB data: {n_mb:,} examples, state_dim={mb_dim}")

    if state_dim != mb_dim:
        print(f"  ERROR: State dim mismatch! Human={state_dim}, MB={mb_dim}")
        return False

    n_total = n_human + n_mb
    print(f"  Combined: {n_total:,} examples")
    print(f"  Mix: {100*n_human/n_total:.1f}% human, {100*n_mb/n_total:.1f}% MB")

    # Datasets to merge
    datasets_config = {
        "features": ("float32", (state_dim,)),
        "label_A": ("float32", ()),
        "label_B_weight": ("float32", ()),
        "label_C": ("float32", ()),
        "label_D": ("float32", ()),
        "labels": ("float32", ()),
        "ply_index": ("uint16", ()),
        "total_plies": ("uint16", ()),
        "rating_p0": ("uint16", ()),
        "rating_p1": ("uint16", ()),
        "game_date": ("uint32", ()),
        "card_set_indices": ("uint8", (11,)),
    }

    chunk_size = 10000
    print(f"  Writing combined dataset to {COMBINED_TRAIN}")
    t0 = time.time()

    with h5py.File(COMBINED_TRAIN, "w") as out:
        with h5py.File(HUMAN_TRAIN, "r") as hf:
            with h5py.File(MB_HDF5, "r") as mf:
                # Create datasets
                for name, (dtype, extra_shape) in datasets_config.items():
                    if name not in hf or name not in mf:
                        print(f"    Skipping {name} (not in both files)")
                        continue
                    if extra_shape:
                        shape = (n_total,) + extra_shape
                    else:
                        shape = (n_total,)

                    compression = "gzip" if name == "features" else None
                    comp_opts = 4 if name == "features" else None
                    ds = out.create_dataset(
                        name, shape=shape, dtype=dtype,
                        chunks=(min(chunk_size, n_total),) + extra_shape if extra_shape else (min(chunk_size, n_total),),
                        compression=compression, compression_opts=comp_opts
                    )

                    # Copy human data in chunks
                    for start in range(0, n_human, chunk_size):
                        end = min(start + chunk_size, n_human)
                        ds[start:end] = hf[name][start:end]

                    # Copy MB data in chunks
                    for start in range(0, n_mb, chunk_size):
                        end = min(start + chunk_size, n_mb)
                        ds[n_human + start:n_human + end] = mf[name][start:end]

                    print(f"    {name}: {shape}")

                # Handle replay_codes (variable-length strings) separately
                if "replay_codes" in hf and "replay_codes" in mf:
                    dt_str = h5py.string_dtype()
                    ds = out.create_dataset("replay_codes", shape=(n_total,), dtype=dt_str)
                    for start in range(0, n_human, chunk_size):
                        end = min(start + chunk_size, n_human)
                        ds[start:end] = hf["replay_codes"][start:end]
                    for start in range(0, n_mb, chunk_size):
                        end = min(start + chunk_size, n_mb)
                        ds[n_human + start:n_human + end] = mf["replay_codes"][start:end]
                    print(f"    replay_codes: ({n_total},)")

                # Copy feature stats from human data (normalization reference)
                for stat_name in ["feature_mean", "feature_std", "feature_min", "feature_max"]:
                    if stat_name in hf:
                        out.create_dataset(stat_name, data=hf[stat_name][:])

    elapsed = time.time() - t0
    size_mb = os.path.getsize(COMBINED_TRAIN) / (1024 * 1024)
    print(f"  Done: {size_mb:.0f} MB, {elapsed:.0f}s")

    # Copy validation set (human only — clean baseline)
    print(f"\n  Copying validation set (human only): {COMBINED_VAL}")
    import shutil
    shutil.copy2(HUMAN_VAL, COMBINED_VAL)
    val_size = os.path.getsize(COMBINED_VAL) / (1024 * 1024)
    print(f"  Done: {val_size:.0f} MB")

    return True


def main():
    print("=" * 60)
    print("COMBINED DATASET PREPARATION")
    print(f"  Human source: {HUMAN_TRAIN}")
    print(f"  MB source: {MB_FLEET_DIR}")
    print(f"  Output: {COMBINED_TRAIN}")
    print("=" * 60)

    if not step1_filter_mb_data():
        sys.exit(1)
    if not step2_vectorize_mb():
        sys.exit(1)
    if not step3_merge_datasets():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ALL DONE — Ready to train!")
    print("=" * 60)
    print(f"\n  Train file: {COMBINED_TRAIN}")
    print(f"  Val file:   {COMBINED_VAL}")
    print(f"\n  Example training command:")
    print(f"  python training/train.py \\")
    print(f'    --train-file "{COMBINED_TRAIN}" \\')
    print(f'    --val-file "{COMBINED_VAL}" \\')
    print(f"    --output-dir training/models/combined_human_mb \\")
    print(f"    --hidden-dim 256 --num-layers 4 --epochs 100 --batch-size 512 \\")
    print(f"    --lr 3e-4 --weight-decay 1e-4 --warmup-steps 1000 \\")
    print(f"    --patience 15 --value-only --label-strategy D --device xpu")


if __name__ == "__main__":
    main()
