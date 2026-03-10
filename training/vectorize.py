"""
Vectorize Prismata training data from JSONL to HDF5 format.

Input: JSONL file where each line is a JSON object with replay_code, ply_index,
       total_plies, rating_p0, rating_p1, game_date, card_set, outcome_p0, state.

Output: HDF5 file with feature vectors, labels (4 strategies), metadata, and
        per-feature statistics.

Schema: training/schema_v1.json (116 units x 11 features + 14 global = 1290-dim)

Usage:
    python training/vectorize.py --input training/data/raw_states.jsonl --output training/data/dataset.h5
    python training/vectorize.py --input data.jsonl --output data.h5 --schema training/schema_v1.json
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import h5py
import numpy as np


# Reference game length for Strategy B temporal weighting
REFERENCE_LENGTH = 40


def clamp_divide(value, cap):
    """Normalize: clamp to [0, cap] then divide by cap -> [0, 1]."""
    return min(float(value), cap) / cap


def clean_unit_name(name):
    """Clean unit names from replay parser artifacts.

    Strips:
      - '*' prefix (script-created units like '*Thorium Dynamo')
      - Numbered prefixes like '1-Apollo', '10Wall Of Fortune', '8-Polywall'
    """
    if name.startswith('*'):
        name = name[1:]
    name = re.sub(r'^\d+-?', '', name)
    return name


def load_schema(schema_path):
    """Load and validate the schema contract."""
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    required = ["schema_version", "state_dim", "num_units", "features_per_unit",
                "num_global_features", "unit_index_hash"]
    for key in required:
        if key not in schema:
            raise ValueError(f"Schema missing required key: {key}")

    return schema


def load_unit_index(index_path, expected_hash):
    """Load the canonical unit index and verify its hash matches schema.

    The hash is a pre-agreed token stored in both unit_index.json and schema_v1.json.
    We verify that both files agree on the same hash value (not recomputed).
    """
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "units" not in data:
        raise ValueError("unit_index.json missing 'units' key")

    unit_index = data["units"]

    # Verify the unit_index.json's own hash matches the schema's expected hash
    stored_hash = data.get("unit_index_hash", "")
    if stored_hash != expected_hash:
        raise ValueError(
            f"unit_index hash mismatch with schema!\n"
            f"  unit_index.json hash: {stored_hash}\n"
            f"  schema expected:      {expected_hash}\n"
            f"  unit_index.json is out of sync with schema"
        )

    return unit_index


def compute_schema_hash(schema):
    """Compute a deterministic hash of the schema for provenance tracking."""
    # Hash the key structural fields
    key_fields = {
        "state_dim": schema["state_dim"],
        "num_units": schema["num_units"],
        "features_per_unit": schema["features_per_unit"],
        "num_global_features": schema["num_global_features"],
        "unit_index_hash": schema["unit_index_hash"],
    }
    raw = json.dumps(key_fields, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def vectorize_state(state, unit_index, num_units, caps):
    """Convert a state dict to a 1290-dim float32 numpy array.

    Per-unit layout (11 features per unit at unitIdx*11):
      +0: p0_ready, +1: p0_exhausted, +2: p0_constructing, +3: p0_blocking,
      +4: p1_ready, +5: p1_exhausted, +6: p1_constructing, +7: p1_blocking,
      +8: p0_supply, +9: p1_supply, +10: in_card_set

    Status classification (matching C++ NeuralNet.cpp):
      building=true -> constructing
      blocking=true AND abilityUsed=true -> blocking
      abilityUsed=true (only) -> exhausted
      neither -> ready

    Global features (14): resources (6x2 players) + turn_number + active_player
    """
    vec = np.zeros(num_units * 11 + 14, dtype=np.float32)

    # Per-unit features: units
    for player_idx, key in enumerate(("p0_units", "p1_units")):
        offset = player_idx * 4
        units = state.get(key, [])

        if isinstance(units, list):
            for u in units:
                name = clean_unit_name(u["name"])
                if name not in unit_index:
                    continue
                idx = unit_index[name]
                base = idx * 11

                if u.get("building", False):
                    vec[base + offset + 2] += 1.0  # constructing
                elif u.get("blocking", False) and u.get("abilityUsed", False):
                    vec[base + offset + 3] += 1.0  # blocking
                elif u.get("abilityUsed", False):
                    vec[base + offset + 1] += 1.0  # exhausted
                else:
                    vec[base + offset + 0] += 1.0  # ready

        elif isinstance(units, dict):
            # Old aggregated format: {"Drone": {ready: 6, exhausted: 0, ...}}
            for name, counts in units.items():
                cname = clean_unit_name(name)
                if cname not in unit_index:
                    continue
                idx = unit_index[cname]
                base = idx * 11
                vec[base + offset + 0] = counts.get("ready", 0)
                vec[base + offset + 1] = counts.get("exhausted", 0)
                vec[base + offset + 2] = counts.get("constructing", 0)
                vec[base + offset + 3] = counts.get("blocking", 0)

    # Supply
    for name, supply in state.get("supply", {}).items():
        cname = clean_unit_name(name)
        if cname not in unit_index:
            continue
        idx = unit_index[cname]
        base = idx * 11
        if isinstance(supply, dict):
            p0_sup = supply.get("p0", 0)
            p1_sup = supply.get("p1", 0)
        else:
            p0_sup = supply
            p1_sup = supply
        vec[base + 8] = float(p0_sup if p0_sup is not None else 0)
        vec[base + 9] = float(p1_sup if p1_sup is not None else 0)

    # Card set indicator
    for name in state.get("card_set", []):
        cname = clean_unit_name(name)
        if cname in unit_index:
            vec[unit_index[cname] * 11 + 10] = 1.0

    # Global features (14 total) at offset num_units * 11
    g = num_units * 11
    p0_res = state.get("p0_resources", {})
    p1_res = state.get("p1_resources", {})

    vec[g + 0] = clamp_divide(p0_res.get("gold", 0), caps["gold"])
    vec[g + 1] = clamp_divide(p0_res.get("blue", 0), caps["blue"])
    vec[g + 2] = clamp_divide(p0_res.get("red", 0), caps["red"])
    vec[g + 3] = clamp_divide(p0_res.get("green", 0), caps["green"])
    vec[g + 4] = clamp_divide(p0_res.get("energy", 0), caps["energy"])
    vec[g + 5] = clamp_divide(state.get("p0_attack", p0_res.get("attack", 0)), caps["attack"])
    vec[g + 6] = clamp_divide(p1_res.get("gold", 0), caps["gold"])
    vec[g + 7] = clamp_divide(p1_res.get("blue", 0), caps["blue"])
    vec[g + 8] = clamp_divide(p1_res.get("red", 0), caps["red"])
    vec[g + 9] = clamp_divide(p1_res.get("green", 0), caps["green"])
    vec[g + 10] = clamp_divide(p1_res.get("energy", 0), caps["energy"])
    vec[g + 11] = clamp_divide(state.get("p1_attack", p1_res.get("attack", 0)), caps["attack"])
    vec[g + 12] = clamp_divide(state.get("turn_number", 0), caps["turn_number"])
    vec[g + 13] = float(state.get("active_player", 0))

    return vec


def compute_labels(outcome_p0, ply_index, total_plies, rating_p0, rating_p1):
    """Compute all 4 label strategies for a single record.

    Returns: (label_A, label_B_weight, label_C, label_D)
    """
    # Strategy A: raw binary outcome
    label_a = float(outcome_p0)

    # Strategy B: sample weight = 0.3 + 0.7 * min(1.0, ply_index / REFERENCE_LENGTH)
    label_b_weight = 0.3 + 0.7 * min(1.0, ply_index / REFERENCE_LENGTH)

    # Strategy C: Elo-interpolated
    # p0_win_prior = 1 / (1 + 10^((r1-r0)/400))
    # t = min(1, ply_index / 40)
    # label = (1-t)*p0_win_prior + t*outcome_p0
    rating_diff = rating_p1 - rating_p0
    p0_win_prior = 1.0 / (1.0 + math.pow(10.0, rating_diff / 400.0))
    t_c = min(1.0, ply_index / 40.0)
    label_c = (1.0 - t_c) * p0_win_prior + t_c * outcome_p0

    # Strategy D: neutral prior
    # (1-t)*0.5 + t*outcome_p0
    t_d = min(1.0, ply_index / 40.0)
    label_d = (1.0 - t_d) * 0.5 + t_d * outcome_p0

    return label_a, label_b_weight, label_c, label_d


def resolve_card_set_indices(card_set, unit_index, max_random=11):
    """Convert card_set names to unit indices, padded to max_random.

    Returns uint8 array of length max_random. Unknown/empty slots get index 255.
    """
    indices = np.full(max_random, 255, dtype=np.uint8)
    for i, name in enumerate(card_set[:max_random]):
        cname = clean_unit_name(name)
        if cname in unit_index:
            idx = unit_index[cname]
            if idx < 255:
                indices[i] = idx
    return indices


def count_lines(filepath):
    """Count lines in a file efficiently."""
    count = 0
    with open(filepath, "rb") as f:
        for _ in f:
            count += 1
    return count


def process_file(input_path, unit_index, num_units, caps, output_path, schema,
                 chunk_size=10000):
    """Stream-process JSONL input into HDF5 output in chunks."""

    schema_hash = compute_schema_hash(schema)
    state_dim = num_units * 11 + 14

    print(f"  Counting lines in {input_path}...")
    total_lines = count_lines(input_path)
    print(f"  Total lines: {total_lines}")

    if total_lines == 0:
        print("  ERROR: Input file is empty.")
        sys.exit(1)

    # Pre-scan for unknown unit names
    print("  Scanning for unknown unit names...")
    unk_names = defaultdict(int)
    unk_examples = 0
    scan_count = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            ex = json.loads(line)
            has_unk = False
            for key in ("p0_units", "p1_units"):
                units = ex.get("state", {}).get(key, [])
                if isinstance(units, list):
                    for u in units:
                        cname = clean_unit_name(u["name"])
                        if cname not in unit_index:
                            unk_names[cname] += 1
                            has_unk = True
            if has_unk:
                unk_examples += 1
            scan_count += 1

    # Collect replay codes that contain unknown units — these will be skipped entirely
    skip_codes = set()
    if unk_names:
        print(f"  Found {len(unk_names)} unknown unit names ({sum(unk_names.values())} occurrences)")
        top_unk = sorted(unk_names.items(), key=lambda x: -x[1])[:10]
        for name, count in top_unk:
            print(f"    {name}: {count}")
        # Second pass: collect replay codes to skip
        with open(input_path, "r", encoding="utf-8") as f2:
            for line in f2:
                ex2 = json.loads(line)
                for key in ("p0_units", "p1_units"):
                    units = ex2.get("state", {}).get(key, [])
                    if isinstance(units, list):
                        for u in units:
                            cname = clean_unit_name(u["name"])
                            if cname not in unit_index:
                                skip_codes.add(ex2.get("replay_code", ""))
                                break
                    if ex2.get("replay_code", "") in skip_codes:
                        break
        print(f"  Skipping {len(skip_codes)} replays ({unk_examples} records) with unknown units")
        total_lines -= unk_examples
        print(f"  Adjusted record count: {total_lines}")
    else:
        print(f"  No unknown unit names in {scan_count} records.")

    # Create HDF5 file with resizable datasets
    print(f"\n  Creating HDF5 file: {output_path}")
    with h5py.File(output_path, "w") as hf:
        # Main datasets — create with initial size, resize as we go
        ds_features = hf.create_dataset(
            "features", shape=(total_lines, state_dim), dtype="float32",
            maxshape=(None, state_dim),
            chunks=(min(chunk_size, total_lines), state_dim),
            compression="gzip", compression_opts=4
        )
        ds_label_a = hf.create_dataset(
            "label_A", shape=(total_lines,), dtype="float32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_label_b = hf.create_dataset(
            "label_B_weight", shape=(total_lines,), dtype="float32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_label_c = hf.create_dataset(
            "label_C", shape=(total_lines,), dtype="float32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_label_d = hf.create_dataset(
            "label_D", shape=(total_lines,), dtype="float32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_labels = hf.create_dataset(
            "labels", shape=(total_lines,), dtype="float32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )

        # Metadata datasets
        dt_str = h5py.string_dtype()
        ds_replay = hf.create_dataset("replay_codes", shape=(total_lines,), dtype=dt_str,
                                       maxshape=(None,))
        ds_ply = hf.create_dataset(
            "ply_index", shape=(total_lines,), dtype="uint16",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_total_plies = hf.create_dataset(
            "total_plies", shape=(total_lines,), dtype="uint16",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_rating_p0 = hf.create_dataset(
            "rating_p0", shape=(total_lines,), dtype="uint16",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_rating_p1 = hf.create_dataset(
            "rating_p1", shape=(total_lines,), dtype="uint16",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_game_date = hf.create_dataset(
            "game_date", shape=(total_lines,), dtype="uint32",
            maxshape=(None,), chunks=(min(chunk_size, total_lines),)
        )
        ds_card_set = hf.create_dataset(
            "card_set_indices", shape=(total_lines, 11), dtype="uint8",
            maxshape=(None, 11), chunks=(min(chunk_size, total_lines), 11)
        )

        # Running statistics accumulators
        feat_sum = np.zeros(state_dim, dtype=np.float64)
        feat_sum_sq = np.zeros(state_dim, dtype=np.float64)
        feat_min = np.full(state_dim, np.inf, dtype=np.float64)
        feat_max = np.full(state_dim, -np.inf, dtype=np.float64)

        # Process in chunks
        print("  Vectorizing records...")
        t_start = time.time()
        record_idx = 0

        with open(input_path, "r", encoding="utf-8") as f:
            while True:
                # Read a chunk of lines
                chunk_features = []
                chunk_label_a = []
                chunk_label_b = []
                chunk_label_c = []
                chunk_label_d = []
                chunk_replay = []
                chunk_ply = []
                chunk_total_plies = []
                chunk_rp0 = []
                chunk_rp1 = []
                chunk_date = []
                chunk_cardset = []

                eof = False
                while len(chunk_features) < chunk_size:
                    line = f.readline()
                    if not line:
                        eof = True
                        break

                    ex = json.loads(line)

                    # Skip replays with unknown units
                    if ex.get("replay_code", "") in skip_codes:
                        continue

                    state = ex["state"]

                    # Vectorize state
                    fvec = vectorize_state(state, unit_index, num_units, caps)
                    chunk_features.append(fvec)

                    # Extract metadata
                    outcome_p0 = ex.get("outcome_p0", 0)
                    ply = ex.get("ply_index", 0)
                    total_p = ex.get("total_plies", 0)
                    r0 = ex.get("rating_p0", 1500)
                    r1 = ex.get("rating_p1", 1500)

                    # Labels
                    la, lb, lc, ld = compute_labels(outcome_p0, ply, total_p, r0, r1)
                    chunk_label_a.append(la)
                    chunk_label_b.append(lb)
                    chunk_label_c.append(lc)
                    chunk_label_d.append(ld)

                    chunk_replay.append(ex.get("replay_code", ""))
                    chunk_ply.append(min(ply, 65535))
                    chunk_total_plies.append(min(total_p, 65535))
                    chunk_rp0.append(min(r0, 65535))
                    chunk_rp1.append(min(r1, 65535))
                    chunk_date.append(ex.get("game_date", 0))

                    # Card set indices (from outer card_set, not state.card_set)
                    card_set = ex.get("card_set", [])
                    chunk_cardset.append(resolve_card_set_indices(card_set, unit_index))

                if not chunk_features:
                    break  # EOF with no remaining records

                n = len(chunk_features)
                end_idx = record_idx + n

                # Write features
                feat_arr = np.array(chunk_features, dtype=np.float32)
                ds_features[record_idx:end_idx] = feat_arr

                # Accumulate statistics
                feat_sum += feat_arr.sum(axis=0).astype(np.float64)
                feat_sum_sq += (feat_arr.astype(np.float64) ** 2).sum(axis=0)
                feat_min = np.minimum(feat_min, feat_arr.min(axis=0).astype(np.float64))
                feat_max = np.maximum(feat_max, feat_arr.max(axis=0).astype(np.float64))

                # Write labels
                ds_label_a[record_idx:end_idx] = np.array(chunk_label_a, dtype=np.float32)
                ds_label_b[record_idx:end_idx] = np.array(chunk_label_b, dtype=np.float32)
                ds_label_c[record_idx:end_idx] = np.array(chunk_label_c, dtype=np.float32)
                ds_label_d[record_idx:end_idx] = np.array(chunk_label_d, dtype=np.float32)
                ds_labels[record_idx:end_idx] = np.array(chunk_label_a, dtype=np.float32)

                # Write metadata
                ds_replay[record_idx:end_idx] = chunk_replay
                ds_ply[record_idx:end_idx] = np.array(chunk_ply, dtype=np.uint16)
                ds_total_plies[record_idx:end_idx] = np.array(chunk_total_plies, dtype=np.uint16)
                ds_rating_p0[record_idx:end_idx] = np.array(chunk_rp0, dtype=np.uint16)
                ds_rating_p1[record_idx:end_idx] = np.array(chunk_rp1, dtype=np.uint16)
                ds_game_date[record_idx:end_idx] = np.array(chunk_date, dtype=np.uint32)
                ds_card_set[record_idx:end_idx] = np.array(chunk_cardset, dtype=np.uint8)

                record_idx = end_idx

                if record_idx % (chunk_size * 5) == 0 or record_idx == total_lines:
                    elapsed = time.time() - t_start
                    rate = record_idx / max(elapsed, 0.001)
                    print(f"    {record_idx:>8d} / {total_lines} records "
                          f"({100*record_idx/total_lines:.1f}%) "
                          f"[{rate:.0f} rec/s]")

        # Handle case where actual records < total_lines (e.g., blank lines)
        actual_records = record_idx
        if actual_records < total_lines:
            print(f"  NOTE: {total_lines - actual_records} blank/invalid lines skipped. "
                  f"Resizing datasets to {actual_records}.")
            for ds in [ds_features, ds_label_a, ds_label_b, ds_label_c, ds_label_d,
                       ds_labels, ds_replay, ds_ply, ds_total_plies, ds_rating_p0,
                       ds_rating_p1, ds_game_date, ds_card_set]:
                ds.resize(actual_records, axis=0)

        # Compute and store per-feature statistics
        print("\n  Computing per-feature statistics...")
        n = actual_records
        feat_mean = (feat_sum / n).astype(np.float32)
        feat_var = (feat_sum_sq / n - (feat_sum / n) ** 2)
        feat_var = np.maximum(feat_var, 0.0)  # numerical safety
        feat_std = np.sqrt(feat_var).astype(np.float32)
        feat_min_f = feat_min.astype(np.float32)
        feat_max_f = feat_max.astype(np.float32)

        hf.create_dataset("feature_mean", data=feat_mean)
        hf.create_dataset("feature_std", data=feat_std)
        hf.create_dataset("feature_min", data=feat_min_f)
        hf.create_dataset("feature_max", data=feat_max_f)

        # Warn about zero-variance features
        zero_var_indices = np.where(feat_std == 0.0)[0]
        if len(zero_var_indices) > 0:
            print(f"  WARNING: {len(zero_var_indices)} zero-variance features detected:")
            # Group by type for readability
            idx_to_name = {v: k for k, v in unit_index.items()}
            unit_feat_names = ["p0_ready", "p0_exhausted", "p0_constructing", "p0_blocking",
                               "p1_ready", "p1_exhausted", "p1_constructing", "p1_blocking",
                               "p0_supply", "p1_supply", "in_card_set"]
            global_names = ["p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
                            "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
                            "turn_number", "active_player"]

            unit_dim = num_units * 11
            zero_unit = [i for i in zero_var_indices if i < unit_dim]
            zero_global = [i for i in zero_var_indices if i >= unit_dim]

            if zero_unit:
                # Summarize by feature type
                by_feat = defaultdict(int)
                for i in zero_unit:
                    feat_offset = i % 11
                    by_feat[unit_feat_names[feat_offset]] += 1
                for feat_name, count in sorted(by_feat.items()):
                    print(f"    {feat_name}: {count}/{num_units} units have zero variance")

            if zero_global:
                for i in zero_global:
                    gi = i - unit_dim
                    print(f"    global[{gi}] ({global_names[gi]}): zero variance "
                          f"(value={feat_mean[i]:.4f})")

        # HDF5 attributes
        hf.attrs["schema_version"] = schema["schema_version"]
        hf.attrs["schema_hash"] = schema_hash
        hf.attrs["num_records"] = actual_records
        hf.attrs["state_dim"] = state_dim
        hf.attrs["num_units"] = num_units

        elapsed = time.time() - t_start
        print(f"\n  Done. {actual_records} records written in {elapsed:.1f}s")
        print(f"  Output: {output_path}")
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  File size: {file_size_mb:.1f} MB")

        # Summary statistics
        print(f"\n  --- Summary ---")
        print(f"  Records: {actual_records}")
        print(f"  State dim: {state_dim} ({num_units} x 11 + 14)")
        print(f"  Schema version: {schema['schema_version']}")
        print(f"  Schema hash: {schema_hash[:16]}...")

        label_a_arr = ds_label_a[:]
        print(f"\n  Label A (outcome_p0): mean={label_a_arr.mean():.4f}, "
              f"p0_wins={label_a_arr.sum():.0f}/{actual_records} "
              f"({100*label_a_arr.mean():.1f}%)")

        label_c_arr = ds_label_c[:]
        print(f"  Label C (Elo-interp): mean={label_c_arr.mean():.4f}, "
              f"std={label_c_arr.std():.4f}, min={label_c_arr.min():.4f}, "
              f"max={label_c_arr.max():.4f}")

        label_d_arr = ds_label_d[:]
        print(f"  Label D (neutral):    mean={label_d_arr.mean():.4f}, "
              f"std={label_d_arr.std():.4f}, min={label_d_arr.min():.4f}, "
              f"max={label_d_arr.max():.4f}")

        # Print global feature stats
        print(f"\n  Global feature stats:")
        global_start = num_units * 11
        global_names = ["p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
                        "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
                        "turn/50", "active_player"]
        for i, gname in enumerate(global_names):
            fi = global_start + i
            print(f"    {gname:15s}: mean={feat_mean[fi]:.4f}  std={feat_std[fi]:.4f}  "
                  f"min={feat_min_f[fi]:.3f}  max={feat_max_f[fi]:.3f}")


def main():
    parser = argparse.ArgumentParser(
        description="Vectorize Prismata JSONL training data to HDF5 format."
    )
    parser.add_argument("--input", required=True, help="Path to input JSONL file")
    parser.add_argument("--output", required=True, help="Path to output HDF5 file")
    parser.add_argument("--schema", default=None,
                        help="Path to schema JSON (default: training/schema_v1.json)")
    parser.add_argument("--chunk-size", type=int, default=10000,
                        help="Records per processing chunk (default: 10000)")
    args = parser.parse_args()

    # Resolve schema path
    if args.schema:
        schema_path = args.schema
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(script_dir, "schema_v1.json")

    # Resolve unit index path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(script_dir, "data", "unit_index.json")

    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Schema: {schema_path}")
    print(f"Unit index: {index_path}")
    print()

    # Load schema
    print("Loading schema...")
    schema = load_schema(schema_path)
    print(f"  Schema version: {schema['schema_version']}")
    print(f"  State dim: {schema['state_dim']}")
    print(f"  Num units: {schema['num_units']}")

    # Load unit index
    print("Loading unit index...")
    unit_index = load_unit_index(index_path, schema["unit_index_hash"])
    num_units = len(unit_index)
    print(f"  {num_units} canonical unit types")
    print(f"  Hash verified: {schema['unit_index_hash'][:16]}...")

    # Verify dimensions
    expected_dim = num_units * schema["features_per_unit"] + schema["num_global_features"]
    if expected_dim != schema["state_dim"]:
        raise ValueError(f"Schema state_dim={schema['state_dim']} but computed {expected_dim}")

    # Extract normalization caps from schema
    caps = schema["normalization_caps"]

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    # Process
    print(f"\nProcessing {args.input}...")
    process_file(args.input, unit_index, num_units, caps, args.output, schema,
                 chunk_size=args.chunk_size)

    print("\nDone.")


if __name__ == "__main__":
    main()
