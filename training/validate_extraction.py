#!/usr/bin/env python3
"""
validate_extraction.py — Phase 2d: Post-Extraction Validation

Validates an HDF5 dataset against training plan requirements.

Checks:
  1. Spot-check 100 random records against expected game outcomes
  2. Verify label distribution (~50/50 expected)
  3. Verify feature value ranges (no NaN, no Inf, no obviously wrong counts)
  4. Verify total record count is consistent with game length estimate (~30 plies/game)
  5. Per-feature statistics: mean, std, min, max for ALL features. Flag zero-variance.
  6. Seat asymmetry audit: P0-active vs P1-active counts, first-player win rate per split
  7. Verify no duplicate records (same replay_code + ply_index)
  8. Verify metadata fields don't leak into feature vectors
  9. Verify all label strategies are in expected ranges

Usage:
    python training/validate_extraction.py --input training/data/dataset.h5 [--schema training/schema_v1.json]
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

import h5py
import numpy as np


# --- Schema defaults (used if no schema file provided) ---
DEFAULT_STATE_DIM = 1290
DEFAULT_NUM_UNITS = 116
DEFAULT_FEATURES_PER_UNIT = 11
DEFAULT_NUM_GLOBAL = 14
REFERENCE_LENGTH = 40  # from training plan


def load_schema(schema_path):
    """Load schema or return defaults."""
    if schema_path and os.path.isfile(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_feature_names(schema, state_dim, num_units, features_per_unit):
    """Generate human-readable feature names."""
    names = []
    unit_names = None

    # Try to load unit index
    if schema and "unit_index_file" in schema:
        ui_path = schema["unit_index_file"]
        # Try relative to CWD and relative to schema
        for candidate in [ui_path, os.path.join(os.path.dirname(schema.get("_path", "")), ui_path)]:
            if os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    uid = json.load(f)
                    unit_names = {v: k for k, v in uid["units"].items()}
                break

    per_unit_feat_names = [
        "p0_ready", "p0_exhausted", "p0_constructing", "p0_blocking",
        "p1_ready", "p1_exhausted", "p1_constructing", "p1_blocking",
        "p0_supply", "p1_supply", "in_card_set"
    ]

    for u in range(num_units):
        uname = unit_names.get(u, f"unit_{u}") if unit_names else f"unit_{u}"
        for fi, fn in enumerate(per_unit_feat_names):
            names.append(f"{uname}/{fn}")

    global_names = [
        "p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
        "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
        "turn_number", "active_player"
    ]
    num_global = state_dim - num_units * features_per_unit
    for i in range(num_global):
        if i < len(global_names):
            names.append(global_names[i])
        else:
            names.append(f"global_{i}")

    return names


class ValidationResult:
    """Collects validation check results."""
    def __init__(self):
        self.checks = []
        self.warnings = []
        self.errors = []

    def check(self, name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        self.checks.append({"name": name, "status": status, "detail": detail})
        if not passed:
            self.errors.append(f"{name}: {detail}")

    def warn(self, name, detail):
        self.warnings.append({"name": name, "detail": detail})

    def summary(self):
        n_pass = sum(1 for c in self.checks if c["status"] == "PASS")
        n_fail = sum(1 for c in self.checks if c["status"] == "FAIL")
        return {
            "total_checks": len(self.checks),
            "passed": n_pass,
            "failed": n_fail,
            "warnings": len(self.warnings),
            "checks": self.checks,
            "warning_details": self.warnings,
            "error_details": self.errors,
        }

    def print_report(self):
        print("\n" + "=" * 70)
        print("VALIDATION REPORT")
        print("=" * 70)
        for c in self.checks:
            marker = "[PASS]" if c["status"] == "PASS" else "[FAIL]"
            print(f"  {marker} {c['name']}")
            if c["detail"]:
                # Indent multiline details
                for line in c["detail"].split("\n"):
                    print(f"         {line}")
        if self.warnings:
            print(f"\n  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"    - {w['name']}: {w['detail']}")
        s = self.summary()
        print(f"\n  Result: {s['passed']}/{s['total_checks']} passed, "
              f"{s['failed']} failed, {s['warnings']} warnings")
        print("=" * 70)


def check_1_spot_check_outcomes(hf, result, n_samples=100):
    """Spot-check records: label_A should be 0 or 1, consistent within replay."""
    label_a = hf["label_A"][:]
    replay_codes = hf["replay_codes"][:]
    n = len(label_a)

    rng = np.random.RandomState(123)
    sample_idx = rng.choice(n, size=min(n_samples, n), replace=False)

    # Check that label_A is binary
    sampled_labels = label_a[sample_idx]
    all_binary = np.all((sampled_labels == 0.0) | (sampled_labels == 1.0))

    # Check within-replay consistency: all records from same replay should have same label_A
    replay_label_map = defaultdict(set)
    for i in sample_idx:
        code = replay_codes[i]
        if isinstance(code, bytes):
            code = code.decode("utf-8")
        replay_label_map[code].add(float(label_a[i]))

    inconsistent = [c for c, labels in replay_label_map.items() if len(labels) > 1]

    detail = f"Sampled {len(sample_idx)} records. "
    detail += f"All binary (0/1): {all_binary}. "
    detail += f"Replays with inconsistent labels: {len(inconsistent)}"
    if inconsistent:
        detail += f" (examples: {inconsistent[:3]})"

    result.check(
        "1. Spot-check outcomes",
        all_binary and len(inconsistent) == 0,
        detail
    )


def check_2_label_distribution(hf, result):
    """Verify label distribution is approximately 50/50."""
    label_a = hf["label_A"][:]
    n = len(label_a)
    n_wins = np.sum(label_a == 1.0)
    n_losses = np.sum(label_a == 0.0)
    n_other = n - n_wins - n_losses
    win_pct = n_wins / n * 100 if n > 0 else 0

    detail = (f"P0 wins: {n_wins:,} ({win_pct:.1f}%), "
              f"P0 losses: {n_losses:,} ({100 - win_pct:.1f}%)")
    if n_other > 0:
        detail += f", other: {n_other:,}"

    # Allow up to 10% deviation from 50/50
    balanced = 40 <= win_pct <= 60
    result.check("2. Label distribution (~50/50)", balanced, detail)
    if not balanced:
        result.warn("Label distribution", f"P0 win rate {win_pct:.1f}% deviates from 50%")


def check_3_feature_ranges(hf, result, state_dim):
    """Verify no NaN, no Inf, no obviously wrong values in features."""
    features = hf["features"]
    n = features.shape[0]
    chunk = 10000
    has_nan = False
    has_inf = False
    global_min = np.inf
    global_max = -np.inf
    negative_count = 0

    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        batch = features[start:end]
        if np.any(np.isnan(batch)):
            has_nan = True
        if np.any(np.isinf(batch)):
            has_inf = True
        global_min = min(global_min, np.min(batch))
        global_max = max(global_max, np.max(batch))
        negative_count += int(np.sum(batch < 0))

    detail = (f"Range: [{global_min:.4f}, {global_max:.4f}], "
              f"NaN: {has_nan}, Inf: {has_inf}, "
              f"negative values: {negative_count:,}")

    passed = not has_nan and not has_inf
    result.check("3. Feature value ranges (no NaN/Inf)", passed, detail)

    if negative_count > 0:
        result.warn("Negative features",
                     f"{negative_count:,} negative values found (global features may be normalized, check schema)")


def check_4_record_count(hf, result):
    """Verify total record count is consistent with ~30 plies/game."""
    n = len(hf["features"])
    replay_codes = hf["replay_codes"][:]
    unique_replays = len(set(
        c.decode("utf-8") if isinstance(c, bytes) else c for c in replay_codes
    ))
    if unique_replays > 0:
        avg_plies = n / unique_replays
    else:
        avg_plies = 0

    # Expect roughly 20-50 plies per game
    reasonable = 10 <= avg_plies <= 80

    detail = (f"Total records: {n:,}, unique replays: {unique_replays:,}, "
              f"avg plies/game: {avg_plies:.1f} (expect ~30)")
    result.check("4. Record count vs game length", reasonable, detail)


def check_5_per_feature_stats(hf, result, state_dim, feature_names):
    """Per-feature statistics: mean, std, min, max. Flag zero-variance."""
    features = hf["features"]
    n = features.shape[0]

    # Compute stats in chunks to manage memory
    feat_sum = np.zeros(state_dim, dtype=np.float64)
    feat_sum_sq = np.zeros(state_dim, dtype=np.float64)
    feat_min = np.full(state_dim, np.inf, dtype=np.float64)
    feat_max = np.full(state_dim, -np.inf, dtype=np.float64)

    chunk = 10000
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        batch = features[start:end].astype(np.float64)
        feat_sum += batch.sum(axis=0)
        feat_sum_sq += (batch ** 2).sum(axis=0)
        feat_min = np.minimum(feat_min, batch.min(axis=0))
        feat_max = np.maximum(feat_max, batch.max(axis=0))

    feat_mean = feat_sum / n
    feat_var = feat_sum_sq / n - feat_mean ** 2
    feat_var = np.maximum(feat_var, 0)  # numerical safety
    feat_std = np.sqrt(feat_var)

    # Zero-variance features
    zero_var_mask = feat_std < 1e-10
    zero_var_indices = np.where(zero_var_mask)[0]
    zero_var_names = [feature_names[i] if i < len(feature_names) else f"feat_{i}"
                      for i in zero_var_indices]

    # Separate truly-constant features from legitimately all-zero features
    always_zero = [i for i in zero_var_indices if abs(feat_mean[i]) < 1e-10]
    constant_nonzero = [i for i in zero_var_indices if abs(feat_mean[i]) >= 1e-10]

    detail = (f"Computed stats for {state_dim} features. "
              f"Zero-variance: {len(zero_var_indices)} "
              f"(always-zero: {len(always_zero)}, constant-nonzero: {len(constant_nonzero)})")

    # Zero-variance is expected for rare units' in_card_set flags — not necessarily a failure
    # But constant-nonzero IS suspicious
    passed = len(constant_nonzero) == 0
    result.check("5. Per-feature statistics (zero-variance check)", passed, detail)

    if zero_var_indices.size > 0:
        # Report up to 20 examples
        examples = zero_var_names[:20]
        result.warn("Zero-variance features",
                     f"{len(zero_var_indices)} features: {examples}"
                     + (" ..." if len(zero_var_indices) > 20 else ""))
    if constant_nonzero:
        names = [feature_names[i] if i < len(feature_names) else f"feat_{i}"
                 for i in constant_nonzero[:10]]
        result.warn("Constant non-zero features (suspicious)",
                     f"{len(constant_nonzero)} features always = same nonzero value: {names}")

    # Build per-feature stats table
    per_feature_stats = []
    for i in range(state_dim):
        per_feature_stats.append({
            "index": i,
            "name": feature_names[i] if i < len(feature_names) else f"feat_{i}",
            "mean": round(float(feat_mean[i]), 6),
            "std": round(float(feat_std[i]), 6),
            "min": round(float(feat_min[i]), 6),
            "max": round(float(feat_max[i]), 6),
            "zero_variance": bool(zero_var_mask[i]),
        })

    return per_feature_stats


def check_6_seat_asymmetry(hf, result):
    """
    Seat asymmetry audit: P0-active vs P1-active counts,
    first-player win rate.
    """
    features = hf["features"]
    label_a = hf["label_A"][:]
    n = features.shape[0]
    state_dim = features.shape[1]

    # Active player is the last feature (index state_dim - 1)
    active_player_idx = state_dim - 1

    # Read active_player column in chunks
    p0_active_count = 0
    p1_active_count = 0
    p0_active_wins = 0
    p1_active_wins = 0

    chunk = 50000
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        active = features[start:end, active_player_idx]
        labels = label_a[start:end]

        p0_mask = active < 0.5  # active_player == 0
        p1_mask = ~p0_mask

        p0_active_count += int(np.sum(p0_mask))
        p1_active_count += int(np.sum(p1_mask))
        p0_active_wins += int(np.sum(labels[p0_mask] == 1.0))
        p1_active_wins += int(np.sum(labels[p1_mask] == 1.0))

    # First-player (P0) overall win rate
    overall_p0_wins = int(np.sum(label_a == 1.0))
    # Win rate per game: use replay-level data
    replay_codes = hf["replay_codes"][:]
    replay_outcomes = {}
    for i in range(n):
        code = replay_codes[i]
        if isinstance(code, bytes):
            code = code.decode("utf-8")
        if code not in replay_outcomes:
            replay_outcomes[code] = float(label_a[i])

    n_games = len(replay_outcomes)
    p0_game_wins = sum(1 for v in replay_outcomes.values() if v == 1.0)
    p0_game_wr = p0_game_wins / n_games * 100 if n_games > 0 else 0

    detail = (f"P0-active records: {p0_active_count:,}, P1-active records: {p1_active_count:,}\n"
              f"P0 wins when P0-active: {p0_active_wins:,}/{p0_active_count:,}\n"
              f"P0 wins when P1-active: {p1_active_wins:,}/{p1_active_count:,}\n"
              f"P0 game win rate: {p0_game_wr:.1f}% ({p0_game_wins:,}/{n_games:,} games)")

    # P2 (Player_Two = P1) wins ~57.3% — P0 should win ~42.7%
    # Allow wide range since this is informational
    result.check("6. Seat asymmetry audit", True, detail)

    if abs(p0_game_wr - 50.0) > 15:
        result.warn("Seat asymmetry",
                     f"P0 game win rate {p0_game_wr:.1f}% far from 50% (expected ~42.7%)")


def check_7_duplicates(hf, result):
    """Verify no duplicate records (same replay_code + ply_index)."""
    replay_codes = hf["replay_codes"][:]
    ply_indices = hf["ply_index"][:]
    n = len(replay_codes)

    seen = set()
    duplicates = 0
    dup_examples = []

    for i in range(n):
        code = replay_codes[i]
        if isinstance(code, bytes):
            code = code.decode("utf-8")
        key = (code, int(ply_indices[i]))
        if key in seen:
            duplicates += 1
            if len(dup_examples) < 5:
                dup_examples.append(key)
        seen.add(key)

    detail = f"Checked {n:,} records. Duplicates: {duplicates:,}"
    if dup_examples:
        detail += f" (examples: {dup_examples})"

    result.check("7. No duplicate records", duplicates == 0, detail)


def check_8_metadata_leakage(hf, result, num_units, features_per_unit):
    """
    Verify metadata fields don't leak into feature vectors.
    Check that rating, game_date, total_plies values don't appear in feature slots.
    """
    features = hf["features"]
    n = features.shape[0]

    # Sample records to check
    rng = np.random.RandomState(456)
    sample_idx = rng.choice(n, size=min(200, n), replace=False)

    rating_p0 = hf["rating_p0"][:]
    rating_p1 = hf["rating_p1"][:]
    game_date = hf["game_date"][:]
    total_plies = hf["total_plies"][:]

    leaks_found = 0
    leak_examples = []

    for i in sample_idx:
        fvec = features[i]
        r0 = float(rating_p0[i])
        r1 = float(rating_p1[i])
        gd = float(game_date[i])
        tp = float(total_plies[i])

        # Check if any feature value exactly equals a metadata value
        # (ratings are typically 1500-2500, dates are unix timestamps ~1.5e9,
        #  these would be very unusual as feature values)
        for meta_name, meta_val in [("rating_p0", r0), ("rating_p1", r1),
                                     ("game_date", gd), ("total_plies", tp)]:
            if meta_val <= 1:
                continue  # Skip trivial values that could legitimately appear

            matches = np.where(np.abs(fvec - meta_val) < 0.01)[0]
            if len(matches) > 0:
                # Ratings > 100 and dates > 1e6 shouldn't appear as raw features
                if meta_val > 100:
                    leaks_found += 1
                    if len(leak_examples) < 5:
                        leak_examples.append({
                            "record": int(i),
                            "field": meta_name,
                            "value": meta_val,
                            "feature_indices": matches.tolist()
                        })

    detail = f"Checked {len(sample_idx)} records for metadata leakage. Suspicious matches: {leaks_found}"
    if leak_examples:
        detail += f"\n  Examples: {leak_examples}"

    result.check("8. No metadata leakage into features", leaks_found == 0, detail)


def check_9_label_ranges(hf, result):
    """Verify all label strategies are in expected ranges."""
    checks_ok = True
    details = []

    # Strategy A: hard binary, should be 0 or 1
    label_a = hf["label_A"][:]
    a_valid = np.all((label_a >= 0.0) & (label_a <= 1.0))
    a_binary = np.all((label_a == 0.0) | (label_a == 1.0))
    details.append(f"A (hard_binary): range [{label_a.min():.4f}, {label_a.max():.4f}], "
                   f"all binary: {a_binary}")
    if not a_valid:
        checks_ok = False

    # Strategy B weight: should be in [0.3, 1.0]
    if "label_B_weight" in hf:
        label_b = hf["label_B_weight"][:]
        b_min, b_max = label_b.min(), label_b.max()
        b_valid = b_min >= 0.3 - 0.01 and b_max <= 1.0 + 0.01
        details.append(f"B_weight (temporal_weight): range [{b_min:.4f}, {b_max:.4f}], "
                       f"expected [0.3, 1.0]: {b_valid}")
        if not b_valid:
            checks_ok = False
    else:
        details.append("B_weight: NOT FOUND in dataset")

    # Strategy C: Elo-interpolated, should be in [0, 1]
    if "label_C" in hf:
        label_c = hf["label_C"][:]
        c_min, c_max = label_c.min(), label_c.max()
        c_valid = c_min >= -0.01 and c_max <= 1.01
        details.append(f"C (elo_interpolated): range [{c_min:.4f}, {c_max:.4f}], "
                       f"expected [0, 1]: {c_valid}")
        if not c_valid:
            checks_ok = False
    else:
        details.append("C: NOT FOUND in dataset")

    # Strategy D: neutral prior, should be in [0, 1]
    if "label_D" in hf:
        label_d = hf["label_D"][:]
        d_min, d_max = label_d.min(), label_d.max()
        d_valid = d_min >= -0.01 and d_max <= 1.01
        details.append(f"D (neutral_prior): range [{d_min:.4f}, {d_max:.4f}], "
                       f"expected [0, 1]: {d_valid}")
        if not d_valid:
            checks_ok = False
    else:
        details.append("D: NOT FOUND in dataset")

    result.check("9. Label strategy ranges", checks_ok, "\n".join(details))


def main():
    parser = argparse.ArgumentParser(description="Validate HDF5 training dataset")
    parser.add_argument("--input", required=True, help="Path to HDF5 dataset")
    parser.add_argument("--schema", default=None, help="Path to schema_v1.json (optional)")
    parser.add_argument("--output-json", default=None,
                        help="Path to write JSON results (default: <input>_validation.json)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Load schema
    schema = load_schema(args.schema)
    if schema:
        state_dim = schema.get("state_dim", DEFAULT_STATE_DIM)
        num_units = schema.get("num_units", DEFAULT_NUM_UNITS)
        features_per_unit = schema.get("features_per_unit", DEFAULT_FEATURES_PER_UNIT)
        num_global = schema.get("num_global_features", DEFAULT_NUM_GLOBAL)
        print(f"Schema loaded: state_dim={state_dim}, num_units={num_units}")
        schema["_path"] = args.schema
    else:
        state_dim = DEFAULT_STATE_DIM
        num_units = DEFAULT_NUM_UNITS
        features_per_unit = DEFAULT_FEATURES_PER_UNIT
        num_global = DEFAULT_NUM_GLOBAL
        print(f"No schema file — using defaults: state_dim={state_dim}, num_units={num_units}")

    feature_names = get_feature_names(schema, state_dim, num_units, features_per_unit)

    result = ValidationResult()

    print(f"\nValidating: {args.input}")
    with h5py.File(args.input, "r") as hf:
        # Basic info
        n = len(hf["features"])
        actual_dim = hf["features"].shape[1]
        print(f"  Records: {n:,}, Feature dim: {actual_dim}")

        # Check feature dim matches schema
        result.check(
            "0. Feature dimension matches schema",
            actual_dim == state_dim,
            f"Dataset dim={actual_dim}, schema dim={state_dim}"
        )

        # List all datasets present
        ds_names = list(hf.keys())
        print(f"  Datasets: {ds_names}")

        # Required datasets
        required = ["features", "label_A", "replay_codes", "ply_index",
                     "total_plies", "rating_p0", "rating_p1", "game_date"]
        missing = [r for r in required if r not in hf]
        result.check(
            "0b. Required datasets present",
            len(missing) == 0,
            f"Missing: {missing}" if missing else f"All {len(required)} required datasets present"
        )

        if missing:
            print("FATAL: Missing required datasets. Cannot continue.")
            result.print_report()
            sys.exit(1)

        print("\nRunning validation checks...")

        # Check 1: Spot-check outcomes
        print("  [1/9] Spot-checking outcomes...")
        check_1_spot_check_outcomes(hf, result)

        # Check 2: Label distribution
        print("  [2/9] Label distribution...")
        check_2_label_distribution(hf, result)

        # Check 3: Feature ranges
        print("  [3/9] Feature value ranges...")
        check_3_feature_ranges(hf, result, state_dim)

        # Check 4: Record count
        print("  [4/9] Record count consistency...")
        check_4_record_count(hf, result)

        # Check 5: Per-feature statistics
        print("  [5/9] Per-feature statistics (this may take a moment)...")
        per_feature_stats = check_5_per_feature_stats(
            hf, result, state_dim, feature_names
        )

        # Check 6: Seat asymmetry
        print("  [6/9] Seat asymmetry audit...")
        check_6_seat_asymmetry(hf, result)

        # Check 7: Duplicates
        print("  [7/9] Checking for duplicates...")
        check_7_duplicates(hf, result)

        # Check 8: Metadata leakage
        print("  [8/9] Metadata leakage check...")
        check_8_metadata_leakage(hf, result, num_units, features_per_unit)

        # Check 9: Label ranges
        print("  [9/9] Label strategy ranges...")
        check_9_label_ranges(hf, result)

    # Print console report
    result.print_report()

    # Write JSON output
    json_path = args.output_json
    if json_path is None:
        base = os.path.splitext(args.input)[0]
        json_path = base + "_validation.json"

    json_output = {
        "input_file": os.path.abspath(args.input),
        "schema_file": os.path.abspath(args.schema) if args.schema else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_records": n,
        "feature_dim": actual_dim,
        "validation": result.summary(),
        "per_feature_stats": per_feature_stats,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, default=str)
    print(f"\nJSON results written to: {json_path}")

    # Exit with error code if any checks failed
    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
