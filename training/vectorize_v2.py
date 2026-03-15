"""
Vectorize Prismata V2 training data from JSONL to HDF5 format (DeepSets layout).

Input: JSONL file where each line is a JSON object with schema_version="v2",
       containing instances[], supply{}, p0/p1_resources, p0/p1_attack,
       turn_number, active_player, outcome_p0, etc.

Output: HDF5 file with:
  - instance_features: float32 (N, MAX_INSTANCES, 10)  — padded instance tokens
  - instance_unit_ids: uint8  (N, MAX_INSTANCES)        — unit type index per slot
  - instance_counts:   uint16 (N,)                      — actual instance count
  - supply:            float32 (N, 116, 3)              — [p0_sup, p1_sup, in_set]
  - globals:           float32 (N, 14)                  — normalized global features
  - label_A/B/C/D:    float32 (N,)                      — label strategies
  - replay_codes, ply_index, total_plies, rating_p0, rating_p1, game_date

Schema: training/schema_v2.json

Usage:
    python training/vectorize_v2.py --input training/data/raw_states.jsonl \\
                                    --output training/data/dataset_v2.h5
    python training/vectorize_v2.py --input data.jsonl --output data.h5 \\
                                    --schema training/schema_v2.json
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict

import h5py
import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ordered list of instance feature names (must match schema_v2.json exactly)
INSTANCE_FEATURE_NAMES = [
    "owner",
    "is_constructing",
    "turns_until_ready",
    "is_blocking",
    "ability_used",
    "current_hp",
    "hp_fraction",
    "is_frozen",
    "lifespan_remaining",
    "stamina_remaining",
]

NUM_INSTANCE_FEATURES = len(INSTANCE_FEATURE_NAMES)  # 10

# Global feature order (must match schema_v2.json global_features)
GLOBAL_FEATURE_NAMES = [
    "p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
    "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
    "turn_number", "active_player",
]

NUM_GLOBAL_FEATURES = len(GLOBAL_FEATURE_NAMES)  # 14

# Reference game length for Strategy B temporal weighting
REFERENCE_LENGTH = 40

# Default max instances (can be overridden by schema)
DEFAULT_MAX_INSTANCES = 200


# ---------------------------------------------------------------------------
# Core vectorization functions (importable for tests)
# ---------------------------------------------------------------------------

def clamp_divide(value, cap):
    """Normalize: clamp to [0, cap] then divide by cap -> [0, 1]."""
    return min(float(value), float(cap)) / float(cap)


def vectorize_instances(instances, unit_index, max_instances=DEFAULT_MAX_INSTANCES):
    """Convert a list of instance dicts to padded arrays.

    P0 units are placed first, then P1 units (within each player, order
    follows the input list — deterministic for debugging, irrelevant for
    DeepSets which is permutation-invariant).

    Args:
        instances: list of instance dicts from V2 JSONL record
        unit_index: dict mapping unit display name -> int index (0-115)
        max_instances: padded slot count

    Returns:
        inst_feats: float32 ndarray shape (max_instances, NUM_INSTANCE_FEATURES)
        inst_ids:   uint8  ndarray shape (max_instances,)  — 255 = padding
        count:      int    — actual (non-padded) instance count
    """
    inst_feats = np.zeros((max_instances, NUM_INSTANCE_FEATURES), dtype=np.float32)
    inst_ids = np.full(max_instances, 255, dtype=np.uint8)

    # Separate P0 and P1 units for deterministic ordering
    p0_instances = [inst for inst in instances if inst.get("owner", 0) == 0]
    p1_instances = [inst for inst in instances if inst.get("owner", 0) == 1]
    ordered = p0_instances + p1_instances

    slot = 0
    for inst in ordered:
        if slot >= max_instances:
            break

        name = inst.get("name", "")
        if name not in unit_index:
            continue  # silently drop unknown units

        unit_id = unit_index[name]

        # Build the 10-feature token
        lifespan = inst.get("lifespan_remaining", 0)
        if lifespan < 0:
            lifespan = 0  # -1 means permanent; map to 0

        token = np.array([
            float(inst.get("owner", 0)),
            float(inst.get("is_constructing", 0)),
            float(inst.get("turns_until_ready", 0)),
            float(inst.get("is_blocking", 0)),
            float(inst.get("ability_used", 0)),
            float(inst.get("current_hp", 0)),
            float(inst.get("hp_fraction", 1.0)),
            float(inst.get("is_frozen", 0)),
            float(lifespan),
            float(inst.get("stamina_remaining", 0)),
        ], dtype=np.float32)

        inst_feats[slot] = token
        inst_ids[slot] = unit_id if unit_id < 255 else 254
        slot += 1

    return inst_feats, inst_ids, slot


def vectorize_supply(supply, unit_index, num_units=116):
    """Convert supply dict to (num_units, 3) float32 array.

    Each row is [p0_supply, p1_supply, in_card_set] for the corresponding unit.
    Unknown units in the supply dict are silently ignored.

    Args:
        supply: dict mapping unit display name -> [p0_sup, p1_sup, in_set]
        unit_index: dict mapping unit display name -> int index
        num_units: total number of unit types (default 116)

    Returns:
        float32 ndarray shape (num_units, 3)
    """
    sup_arr = np.zeros((num_units, 3), dtype=np.float32)

    for name, vals in supply.items():
        if name not in unit_index:
            continue  # silently drop unknown units

        idx = unit_index[name]
        if idx >= num_units:
            continue

        if isinstance(vals, list) and len(vals) >= 3:
            sup_arr[idx, 0] = float(vals[0] if vals[0] is not None else 0)
            sup_arr[idx, 1] = float(vals[1] if vals[1] is not None else 0)
            sup_arr[idx, 2] = float(vals[2] if vals[2] is not None else 0)
        elif isinstance(vals, dict):
            sup_arr[idx, 0] = float(vals.get("p0", 0))
            sup_arr[idx, 1] = float(vals.get("p1", 0))
            sup_arr[idx, 2] = float(vals.get("in_set", 0))

    return sup_arr


def vectorize_globals(record, caps):
    """Convert a V2 record to the 14-dim global feature vector.

    Feature order (matching schema_v2.json global_features):
      p0_gold, p0_blue, p0_red, p0_green, p0_energy, p0_attack,
      p1_gold, p1_blue, p1_red, p1_green, p1_energy, p1_attack,
      turn_number, active_player

    Note: blue, red, green order is NOT alphabetical. Matches schema.

    Args:
        record: V2 JSONL record dict
        caps: normalization caps dict (keys: gold, blue, red, green, energy, attack, turn_number)

    Returns:
        float32 ndarray shape (14,)
    """
    p0_res = record.get("p0_resources", {})
    p1_res = record.get("p1_resources", {})

    gvec = np.array([
        clamp_divide(p0_res.get("gold", 0),   caps["gold"]),
        clamp_divide(p0_res.get("blue", 0),   caps["blue"]),
        clamp_divide(p0_res.get("red", 0),    caps["red"]),
        clamp_divide(p0_res.get("green", 0),  caps["green"]),
        clamp_divide(p0_res.get("energy", 0), caps["energy"]),
        clamp_divide(record.get("p0_attack", 0), caps["attack"]),
        clamp_divide(p1_res.get("gold", 0),   caps["gold"]),
        clamp_divide(p1_res.get("blue", 0),   caps["blue"]),
        clamp_divide(p1_res.get("red", 0),    caps["red"]),
        clamp_divide(p1_res.get("green", 0),  caps["green"]),
        clamp_divide(p1_res.get("energy", 0), caps["energy"]),
        clamp_divide(record.get("p1_attack", 0), caps["attack"]),
        clamp_divide(record.get("turn_number", 0), caps["turn_number"]),
        float(record.get("active_player", 0)),
    ], dtype=np.float32)

    return gvec


def mirror_record(record):
    """Return a new record with P0↔P1 symmetry applied.

    Used for data augmentation. Swaps:
      - instance owner values (0↔1)
      - supply p0_supply↔p1_supply
      - p0_resources↔p1_resources
      - p0_attack↔p1_attack
      - active_player (0↔1)
      - outcome_p0 (0↔1, since perspective flips)

    Args:
        record: V2 JSONL record dict (not mutated)

    Returns:
        new record dict with P0↔P1 swapped
    """
    import copy
    mirrored = copy.deepcopy(record)

    # Flip instance owners
    for inst in mirrored["instances"]:
        inst["owner"] = 1 - inst["owner"]

    # Flip supply p0↔p1
    for name, vals in mirrored["supply"].items():
        if isinstance(vals, list) and len(vals) >= 2:
            vals[0], vals[1] = vals[1], vals[0]
        elif isinstance(vals, dict):
            p0 = vals.get("p0", 0)
            p1 = vals.get("p1", 0)
            vals["p0"] = p1
            vals["p1"] = p0

    # Flip resources
    mirrored["p0_resources"], mirrored["p1_resources"] = (
        mirrored["p1_resources"], mirrored["p0_resources"]
    )

    # Flip attack
    mirrored["p0_attack"], mirrored["p1_attack"] = (
        mirrored["p1_attack"], mirrored["p0_attack"]
    )

    # Flip active player
    mirrored["active_player"] = 1 - mirrored.get("active_player", 0)

    # Flip outcome (P0 win → P1 win from mirrored perspective)
    mirrored["outcome_p0"] = 1 - mirrored.get("outcome_p0", 0)

    return mirrored


def compute_labels(outcome_p0, ply_index, total_plies, rating_p0, rating_p1):
    """Compute all 4 label strategies for a single record.

    Returns: (label_A, label_B_weight, label_C, label_D)
      A: hard binary outcome
      B: temporal sample weight (0.3..1.0 ramp)
      C: Elo-interpolated toward outcome
      D: neutral prior (0.5) interpolated toward outcome
    """
    # Strategy A: raw binary outcome
    label_a = float(outcome_p0)

    # Strategy B: sample weight = 0.3 + 0.7 * min(1, ply / REFERENCE_LENGTH)
    label_b_weight = 0.3 + 0.7 * min(1.0, ply_index / REFERENCE_LENGTH)

    # Strategy C: Elo-interpolated
    rating_diff = float(rating_p1) - float(rating_p0)
    p0_win_prior = 1.0 / (1.0 + math.pow(10.0, rating_diff / 400.0))
    t_c = min(1.0, ply_index / 40.0)
    label_c = (1.0 - t_c) * p0_win_prior + t_c * float(outcome_p0)

    # Strategy D: neutral prior
    t_d = min(1.0, ply_index / 40.0)
    label_d = (1.0 - t_d) * 0.5 + t_d * float(outcome_p0)

    return label_a, label_b_weight, label_c, label_d


# ---------------------------------------------------------------------------
# Schema / unit index loading
# ---------------------------------------------------------------------------

def load_schema(schema_path):
    """Load and validate the V2 schema."""
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    required = ["schema_version", "num_units", "max_instances",
                "num_instance_features", "num_global_features",
                "normalization_caps"]
    for key in required:
        if key not in schema:
            raise ValueError(f"Schema missing required key: {key}")

    return schema


def load_unit_index(index_path):
    """Load the canonical unit index.

    Note: V2 does NOT verify hash against schema (schema_v2 hash may differ
    from the hash stored in unit_index.json). The unit_index is loaded as-is.
    """
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "units" not in data:
        raise ValueError("unit_index.json missing 'units' key")

    return data["units"]


def compute_schema_hash(schema):
    """Compute a deterministic hash of the schema for provenance tracking."""
    key_fields = {
        "schema_version": schema["schema_version"],
        "num_units": schema["num_units"],
        "max_instances": schema["max_instances"],
        "num_instance_features": schema["num_instance_features"],
        "num_global_features": schema["num_global_features"],
    }
    raw = json.dumps(key_fields, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def count_lines(filepath):
    """Count non-empty lines in a file efficiently."""
    count = 0
    with open(filepath, "rb") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_file(input_path, unit_index, output_path, schema, chunk_size=5000):
    """Stream-process V2 JSONL input into HDF5 output in chunks.

    Args:
        input_path:  path to input JSONL file
        unit_index:  dict mapping unit display name -> int index
        output_path: path to output HDF5 file
        schema:      schema dict (loaded from schema_v2.json or inline)
        chunk_size:  records per processing chunk
    """
    num_units = schema["num_units"]
    max_instances = schema.get("max_instances", DEFAULT_MAX_INSTANCES)
    caps = schema["normalization_caps"]

    schema_hash = compute_schema_hash(schema)

    print(f"  Counting lines in {input_path}...")
    total_lines = count_lines(input_path)
    print(f"  Total lines: {total_lines}")

    if total_lines == 0:
        print("  ERROR: Input file is empty.")
        sys.exit(1)

    # Create output directory if needed
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n  Creating HDF5 file: {output_path}")
    with h5py.File(output_path, "w") as hf:
        N = total_lines
        cs = min(chunk_size, N)

        # --- Instance data ---
        ds_inst_feats = hf.create_dataset(
            "instance_features",
            shape=(N, max_instances, NUM_INSTANCE_FEATURES),
            dtype="float32",
            maxshape=(None, max_instances, NUM_INSTANCE_FEATURES),
            chunks=(cs, max_instances, NUM_INSTANCE_FEATURES),
            compression="gzip", compression_opts=4,
        )
        ds_inst_ids = hf.create_dataset(
            "instance_unit_ids",
            shape=(N, max_instances),
            dtype="uint8",
            maxshape=(None, max_instances),
            chunks=(cs, max_instances),
            compression="gzip", compression_opts=4,
        )
        ds_inst_counts = hf.create_dataset(
            "instance_counts",
            shape=(N,), dtype="uint16",
            maxshape=(None,), chunks=(cs,),
        )

        # --- Supply ---
        ds_supply = hf.create_dataset(
            "supply",
            shape=(N, num_units, 3),
            dtype="float32",
            maxshape=(None, num_units, 3),
            chunks=(cs, num_units, 3),
            compression="gzip", compression_opts=4,
        )

        # --- Globals ---
        ds_globals = hf.create_dataset(
            "globals",
            shape=(N, NUM_GLOBAL_FEATURES),
            dtype="float32",
            maxshape=(None, NUM_GLOBAL_FEATURES),
            chunks=(cs, NUM_GLOBAL_FEATURES),
        )

        # --- Labels ---
        ds_label_a = hf.create_dataset("label_A", shape=(N,), dtype="float32",
                                        maxshape=(None,), chunks=(cs,))
        ds_label_b = hf.create_dataset("label_B_weight", shape=(N,), dtype="float32",
                                        maxshape=(None,), chunks=(cs,))
        ds_label_c = hf.create_dataset("label_C", shape=(N,), dtype="float32",
                                        maxshape=(None,), chunks=(cs,))
        ds_label_d = hf.create_dataset("label_D", shape=(N,), dtype="float32",
                                        maxshape=(None,), chunks=(cs,))

        # --- Metadata ---
        dt_str = h5py.string_dtype()
        ds_replay = hf.create_dataset("replay_codes", shape=(N,), dtype=dt_str,
                                       maxshape=(None,))
        ds_ply = hf.create_dataset("ply_index", shape=(N,), dtype="uint16",
                                    maxshape=(None,), chunks=(cs,))
        ds_total_plies = hf.create_dataset("total_plies", shape=(N,), dtype="uint16",
                                            maxshape=(None,), chunks=(cs,))
        ds_rp0 = hf.create_dataset("rating_p0", shape=(N,), dtype="uint16",
                                    maxshape=(None,), chunks=(cs,))
        ds_rp1 = hf.create_dataset("rating_p1", shape=(N,), dtype="uint16",
                                    maxshape=(None,), chunks=(cs,))
        ds_date = hf.create_dataset("game_date", shape=(N,), dtype=dt_str,
                                     maxshape=(None,))

        # --- Process in chunks ---
        print("  Vectorizing records...")
        t_start = time.time()
        record_idx = 0
        skipped = 0
        max_count_seen = 0

        with open(input_path, "r", encoding="utf-8") as f:
            while True:
                # Accumulate a chunk
                chunk_inst_feats = []
                chunk_inst_ids = []
                chunk_inst_counts = []
                chunk_supply = []
                chunk_globals = []
                chunk_la = []
                chunk_lb = []
                chunk_lc = []
                chunk_ld = []
                chunk_replay = []
                chunk_ply = []
                chunk_tplies = []
                chunk_rp0 = []
                chunk_rp1 = []
                chunk_date = []

                eof = False
                while len(chunk_la) < chunk_size:
                    line = f.readline()
                    if not line:
                        eof = True
                        break
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        skipped += 1
                        continue

                    # Check schema version
                    if rec.get("schema_version") != "v2":
                        skipped += 1
                        continue

                    # Vectorize instances
                    instances = rec.get("instances", [])
                    inst_feats, inst_ids, count = vectorize_instances(
                        instances, unit_index, max_instances=max_instances
                    )
                    max_count_seen = max(max_count_seen, count)

                    # Vectorize supply
                    supply = rec.get("supply", {})
                    sup_arr = vectorize_supply(supply, unit_index, num_units=num_units)

                    # Vectorize globals
                    gvec = vectorize_globals(rec, caps)

                    # Labels — draws (outcome_p0=2) mapped to 0.5
                    outcome_p0 = rec.get("outcome_p0", 0)
                    if outcome_p0 == 2:
                        outcome_p0 = 0.5
                    ply = rec.get("ply_index", 0)
                    total_p = rec.get("total_plies", 0)
                    r0 = rec.get("rating_p0", 1500)
                    r1 = rec.get("rating_p1", 1500)
                    la, lb, lc, ld = compute_labels(outcome_p0, ply, total_p, r0, r1)

                    chunk_inst_feats.append(inst_feats)
                    chunk_inst_ids.append(inst_ids)
                    chunk_inst_counts.append(count)
                    chunk_supply.append(sup_arr)
                    chunk_globals.append(gvec)
                    chunk_la.append(la)
                    chunk_lb.append(lb)
                    chunk_lc.append(lc)
                    chunk_ld.append(ld)
                    chunk_replay.append(rec.get("replay_code", ""))
                    chunk_ply.append(min(ply, 65535))
                    chunk_tplies.append(min(total_p, 65535))
                    chunk_rp0.append(min(int(r0), 65535))
                    chunk_rp1.append(min(int(r1), 65535))
                    chunk_date.append(str(rec.get("game_date", "")))

                if not chunk_la:
                    break

                n = len(chunk_la)
                end_idx = record_idx + n

                # Write chunk
                ds_inst_feats[record_idx:end_idx] = np.array(chunk_inst_feats, dtype=np.float32)
                ds_inst_ids[record_idx:end_idx] = np.array(chunk_inst_ids, dtype=np.uint8)
                ds_inst_counts[record_idx:end_idx] = np.array(chunk_inst_counts, dtype=np.uint16)
                ds_supply[record_idx:end_idx] = np.array(chunk_supply, dtype=np.float32)
                ds_globals[record_idx:end_idx] = np.array(chunk_globals, dtype=np.float32)
                ds_label_a[record_idx:end_idx] = np.array(chunk_la, dtype=np.float32)
                ds_label_b[record_idx:end_idx] = np.array(chunk_lb, dtype=np.float32)
                ds_label_c[record_idx:end_idx] = np.array(chunk_lc, dtype=np.float32)
                ds_label_d[record_idx:end_idx] = np.array(chunk_ld, dtype=np.float32)
                ds_replay[record_idx:end_idx] = chunk_replay
                ds_ply[record_idx:end_idx] = np.array(chunk_ply, dtype=np.uint16)
                ds_total_plies[record_idx:end_idx] = np.array(chunk_tplies, dtype=np.uint16)
                ds_rp0[record_idx:end_idx] = np.array(chunk_rp0, dtype=np.uint16)
                ds_rp1[record_idx:end_idx] = np.array(chunk_rp1, dtype=np.uint16)
                ds_date[record_idx:end_idx] = chunk_date

                record_idx = end_idx

                if record_idx % (chunk_size * 5) == 0 or eof:
                    elapsed = time.time() - t_start
                    rate = record_idx / max(elapsed, 0.001)
                    print(f"    {record_idx:>8d} / {total_lines} records "
                          f"({100*record_idx/total_lines:.1f}%) "
                          f"[{rate:.0f} rec/s]")

                if eof:
                    break

        # Resize if actual < estimated (e.g. skipped lines or non-v2 records)
        actual_records = record_idx
        if actual_records < N:
            print(f"  NOTE: {N - actual_records} records skipped ({skipped} parse errors "
                  f"/ schema mismatches). Resizing to {actual_records}.")
            with h5py.File(output_path, "a") as hf:
                for ds_name in [
                    "instance_features", "instance_unit_ids", "instance_counts",
                    "supply", "globals",
                    "label_A", "label_B_weight", "label_C", "label_D",
                    "replay_codes", "ply_index", "total_plies",
                    "rating_p0", "rating_p1", "game_date",
                ]:
                    if ds_name in hf:
                        hf[ds_name].resize(actual_records, axis=0)

        # Write HDF5 attributes
        with h5py.File(output_path, "a") as hf:
            hf.attrs["schema_version"] = schema["schema_version"]
            hf.attrs["schema_hash"] = schema_hash
            hf.attrs["num_records"] = actual_records
            hf.attrs["num_units"] = num_units
            hf.attrs["max_instances"] = max_instances
            hf.attrs["num_instance_features"] = NUM_INSTANCE_FEATURES
            hf.attrs["num_global_features"] = NUM_GLOBAL_FEATURES
            if max_count_seen > 0:
                hf.attrs["max_instances_seen"] = max_count_seen

        elapsed = time.time() - t_start
        print(f"\n  Done. {actual_records} records written in {elapsed:.1f}s")
        if max_count_seen > 0:
            print(f"  Max instances seen in any record: {max_count_seen} "
                  f"({'OK' if max_count_seen <= max_instances else 'WARNING: TRUNCATED'})")
        if skipped:
            print(f"  Skipped: {skipped} records (parse errors / non-v2 schema)")
        print(f"  Output: {output_path}")
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  File size: {file_size_mb:.1f} MB")

        # Summary
        print(f"\n  --- Summary ---")
        print(f"  Records: {actual_records}")
        print(f"  Instance slots: {max_instances} (padded)")
        print(f"  Supply shape: ({num_units}, 3)")
        print(f"  Global features: {NUM_GLOBAL_FEATURES}")
        print(f"  Schema version: {schema['schema_version']}")
        print(f"  Schema hash: {schema_hash[:16]}...")


def main():
    parser = argparse.ArgumentParser(
        description="Vectorize Prismata V2 JSONL training data to HDF5 (DeepSets format)."
    )
    parser.add_argument("--input", required=True, help="Path to input V2 JSONL file")
    parser.add_argument("--output", required=True, help="Path to output HDF5 file")
    parser.add_argument("--schema", default=None,
                        help="Path to schema JSON (default: training/schema_v2.json)")
    parser.add_argument("--chunk-size", type=int, default=5000,
                        help="Records per processing chunk (default: 5000)")
    args = parser.parse_args()

    # Resolve schema path
    if args.schema:
        schema_path = args.schema
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(script_dir, "schema_v2.json")

    # Resolve unit index path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(script_dir, "data", "unit_index.json")

    print(f"Input:      {args.input}")
    print(f"Output:     {args.output}")
    print(f"Schema:     {schema_path}")
    print(f"Unit index: {index_path}")
    print()

    # Load schema
    print("Loading schema...")
    schema = load_schema(schema_path)
    print(f"  Schema version: {schema['schema_version']}")
    print(f"  Num units: {schema['num_units']}")
    print(f"  Max instances: {schema.get('max_instances', DEFAULT_MAX_INSTANCES)}")

    # Load unit index
    print("Loading unit index...")
    unit_index = load_unit_index(index_path)
    print(f"  {len(unit_index)} canonical unit types")

    # Process
    print(f"\nProcessing {args.input}...")
    process_file(args.input, unit_index, args.output, schema,
                 chunk_size=args.chunk_size)

    print("\nDone.")


if __name__ == "__main__":
    main()
