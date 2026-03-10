#!/usr/bin/env python3
"""
split_dataset.py — Phase 2b: Temporal Train/Val/Test Split

Splits an HDF5 dataset into train (80%), val (10%), test (10%) by game date,
maintaining replay-level integrity (all records from one game stay together).

Also computes a random 10% diagnostic holdout for comparison.

Usage:
    python training/split_dataset.py --input training/data/dataset.h5 --output-dir training/data/splits/
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

import h5py
import numpy as np


def load_replay_metadata(hf):
    """Extract per-replay metadata: game_date, record indices, ratings."""
    replay_codes = hf["replay_codes"][:]
    game_dates = hf["game_date"][:]
    rating_p0 = hf["rating_p0"][:]
    rating_p1 = hf["rating_p1"][:]
    n = len(replay_codes)

    # Group record indices by replay_code
    replay_info = {}  # code -> {date, indices, rating_p0, rating_p1}
    for i in range(n):
        code = replay_codes[i]
        if isinstance(code, bytes):
            code = code.decode("utf-8")

        if code not in replay_info:
            replay_info[code] = {
                "date": int(game_dates[i]),
                "indices": [],
                "rating_p0": int(rating_p0[i]),
                "rating_p1": int(rating_p1[i]),
            }
        replay_info[code]["indices"].append(i)

    return replay_info


def temporal_split(replay_info, train_frac=0.80, val_frac=0.10):
    """
    Sort replays by game_date, split temporally.
    Oldest 80% = train, next 10% = val, newest 10% = test.
    """
    # Sort replay codes by date, then code for stable ordering
    sorted_codes = sorted(replay_info.keys(), key=lambda c: (replay_info[c]["date"], c))

    n = len(sorted_codes)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))

    splits = {
        "train": sorted_codes[:train_end],
        "val": sorted_codes[train_end:val_end],
        "test": sorted_codes[val_end:],
    }
    return splits


def random_holdout(replay_info, holdout_frac=0.10, seed=42):
    """Compute a random 10% holdout for diagnostic comparison."""
    codes = sorted(replay_info.keys())
    rng = np.random.RandomState(seed)
    rng.shuffle(codes)
    n_holdout = int(len(codes) * holdout_frac)
    return {
        "random_holdout": codes[:n_holdout],
        "random_remainder": codes[n_holdout:],
    }


def collect_indices(replay_info, code_list):
    """Collect all record indices for a list of replay codes."""
    indices = []
    for code in code_list:
        indices.extend(replay_info[code]["indices"])
    return sorted(indices)


def write_split_h5(hf_in, indices, output_path):
    """Write a subset of the input HDF5 to a new file, preserving structure."""
    indices = np.array(indices, dtype=np.int64)
    n = len(indices)

    # Aggregate stats datasets (not per-record) — copy as-is
    aggregate_datasets = {"feature_mean", "feature_std", "feature_min", "feature_max"}

    with h5py.File(output_path, "w") as hf_out:
        for name in hf_in.keys():
            ds_in = hf_in[name]
            data = ds_in[:]

            # Skip per-record indexing for aggregate stats
            if name in aggregate_datasets:
                hf_out.create_dataset(name, data=data, dtype=ds_in.dtype)
                continue

            # Index into the data
            subset = data[indices]

            # Determine chunking
            if subset.ndim == 1:
                chunk_shape = (min(n, 10000),)
            else:
                chunk_shape = (min(n, 10000),) + subset.shape[1:]

            # Preserve dtype and compression where applicable
            kwargs = {"dtype": ds_in.dtype}
            if ds_in.dtype.kind == "f":  # float
                kwargs["compression"] = "gzip"
                kwargs["compression_opts"] = 4

            if n > 0:
                hf_out.create_dataset(
                    name, data=subset, chunks=chunk_shape, **kwargs
                )
            else:
                # Empty split — write empty dataset with correct shape
                if subset.ndim == 1:
                    shape = (0,)
                else:
                    shape = (0,) + subset.shape[1:]
                hf_out.create_dataset(name, shape=shape, **kwargs)

        # Copy attributes from root
        for attr_name, attr_val in hf_in.attrs.items():
            hf_out.attrs[attr_name] = attr_val

        # Add split metadata
        hf_out.attrs["split_source"] = os.path.basename(hf_in.filename)
        hf_out.attrs["split_records"] = n


def compute_split_stats(replay_info, code_list, split_name):
    """Compute statistics for a split."""
    if not code_list:
        return {
            "split": split_name,
            "num_replays": 0,
            "num_records": 0,
            "date_range": [None, None],
            "rating_distribution": {},
        }

    dates = [replay_info[c]["date"] for c in code_list]
    records = sum(len(replay_info[c]["indices"]) for c in code_list)
    ratings = []
    for c in code_list:
        ratings.append(replay_info[c]["rating_p0"])
        ratings.append(replay_info[c]["rating_p1"])
    ratings = np.array(ratings)

    return {
        "split": split_name,
        "num_replays": len(code_list),
        "num_records": records,
        "date_range": [int(min(dates)), int(max(dates))],
        "date_range_readable": [
            time.strftime("%Y-%m-%d", time.gmtime(min(dates))),
            time.strftime("%Y-%m-%d", time.gmtime(max(dates))),
        ],
        "rating_distribution": {
            "min": int(np.min(ratings)),
            "max": int(np.max(ratings)),
            "mean": round(float(np.mean(ratings)), 1),
            "median": int(np.median(ratings)),
            "p25": int(np.percentile(ratings, 25)),
            "p75": int(np.percentile(ratings, 75)),
        },
    }


def print_stats(stats):
    """Pretty-print split statistics."""
    s = stats
    print(f"\n  {s['split']}:")
    print(f"    Replays:  {s['num_replays']:,}")
    print(f"    Records:  {s['num_records']:,}")
    if s["date_range"][0] is not None:
        print(f"    Dates:    {s['date_range_readable'][0]} to {s['date_range_readable'][1]}")
        rd = s["rating_distribution"]
        print(f"    Ratings:  min={rd['min']}, p25={rd['p25']}, median={rd['median']}, "
              f"mean={rd['mean']}, p75={rd['p75']}, max={rd['max']}")


def main():
    parser = argparse.ArgumentParser(description="Split HDF5 dataset temporally into train/val/test")
    parser.add_argument("--input", required=True, help="Path to input HDF5 dataset")
    parser.add_argument("--output-dir", required=True, help="Output directory for split files")
    parser.add_argument("--train-frac", type=float, default=0.80, help="Training set fraction (default: 0.80)")
    parser.add_argument("--val-frac", type=float, default=0.10, help="Validation set fraction (default: 0.10)")
    parser.add_argument("--random-holdout-frac", type=float, default=0.10,
                        help="Random holdout fraction for diagnostic (default: 0.10)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for holdout (default: 42)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Loading dataset: {args.input}")
    with h5py.File(args.input, "r") as hf:
        total_records = len(hf["features"])
        print(f"  Total records: {total_records:,}")

        # 1. Load replay metadata
        print("  Extracting replay metadata...")
        replay_info = load_replay_metadata(hf)
        total_replays = len(replay_info)
        print(f"  Total unique replays: {total_replays:,}")

        # 2. Temporal split
        print(f"\n  Computing temporal split ({args.train_frac:.0%}/{args.val_frac:.0%}/"
              f"{1.0 - args.train_frac - args.val_frac:.0%})...")
        splits = temporal_split(replay_info, args.train_frac, args.val_frac)

        # 3. Random holdout
        print(f"  Computing random {args.random_holdout_frac:.0%} diagnostic holdout (seed={args.seed})...")
        random_splits = random_holdout(replay_info, args.random_holdout_frac, args.seed)

        # 4. Compute and print statistics
        all_stats = {}
        print("\n== Temporal Split Statistics ==")
        for split_name in ["train", "val", "test"]:
            stats = compute_split_stats(replay_info, splits[split_name], split_name)
            all_stats[split_name] = stats
            print_stats(stats)

        print("\n== Random Holdout Statistics ==")
        rh_stats = compute_split_stats(
            replay_info, random_splits["random_holdout"], "random_holdout"
        )
        all_stats["random_holdout"] = rh_stats
        print_stats(rh_stats)

        # 5. Write split HDF5 files
        split_files = {
            "train": os.path.join(args.output_dir, "train.h5"),
            "val": os.path.join(args.output_dir, "val.h5"),
            "test": os.path.join(args.output_dir, "test.h5"),
        }

        for split_name, filepath in split_files.items():
            indices = collect_indices(replay_info, splits[split_name])
            print(f"\n  Writing {split_name}.h5 ({len(indices):,} records)...")
            write_split_h5(hf, indices, filepath)
            print(f"    -> {filepath}")

        # 6. Write split manifest (JSON)
        manifest = {
            "source": os.path.abspath(args.input),
            "split_method": "temporal",
            "split_fractions": {
                "train": args.train_frac,
                "val": args.val_frac,
                "test": round(1.0 - args.train_frac - args.val_frac, 4),
            },
            "random_holdout_fraction": args.random_holdout_frac,
            "random_holdout_seed": args.seed,
            "splits": {
                "train": sorted(splits["train"]),
                "val": sorted(splits["val"]),
                "test": sorted(splits["test"]),
                "random_holdout": sorted(random_splits["random_holdout"]),
            },
            "statistics": all_stats,
        }

        manifest_path = os.path.join(args.output_dir, "split_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)
        print(f"\n  Manifest written: {manifest_path}")

        # 7. Verify no replay leaks between splits
        train_set = set(splits["train"])
        val_set = set(splits["val"])
        test_set = set(splits["test"])
        assert train_set.isdisjoint(val_set), "Train/Val overlap detected!"
        assert train_set.isdisjoint(test_set), "Train/Test overlap detected!"
        assert val_set.isdisjoint(test_set), "Val/Test overlap detected!"
        assert len(train_set) + len(val_set) + len(test_set) == total_replays, \
            "Replay count mismatch after split!"
        print("\n  Integrity check: PASSED (no replay overlap between splits)")

        # 8. Verify record counts match
        total_split_records = sum(s["num_records"] for s in all_stats.values()
                                  if s["split"] in ("train", "val", "test"))
        assert total_split_records == total_records, \
            f"Record count mismatch: {total_split_records} vs {total_records}"
        print(f"  Record count check: PASSED ({total_split_records:,} = {total_records:,})")

    print("\nDone.")


if __name__ == "__main__":
    main()
