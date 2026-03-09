"""
Search-position sanity check for PrismataNet (Phase 3e/5b-2).

Quick diagnostic: verifies a trained model produces sane values on basic
synthetic test cases. No training data required.

Checks:
  1. All-zeros input -> value near 0.5
  2. Mirror symmetry: value(state) + value(mirror(state)) ~ 1.0
  3. Value monotonicity: adding resources to P0 should not decrease P0 value
  4. No NaN or Inf outputs
  5. Value range: all outputs in [0, 1] after sigmoid

Usage:
  python training/sanity_check.py --model training/models/run_001/best_model.pt
  python training/sanity_check.py --model training/models/run_001/best_model.pt --schema training/schema_v1.json
"""

import argparse
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Model (must match train.py exactly)
# ---------------------------------------------------------------------------

class ResBlock(nn.Module):
    def __init__(self, dim, dropout=0.0):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.fc2 = nn.Linear(dim, dim)
        self.norm = nn.LayerNorm(dim)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        residual = x
        h = F.relu(self.fc1(x))
        h = self.dropout(h)
        h = F.relu(self.fc2(h))
        return residual + self.norm(h)


class PrismataNet(nn.Module):
    def __init__(self, state_dim, num_units, hidden_dim=256, num_layers=4,
                 dropout=0.1, value_only=False):
        super().__init__()
        self.value_only = value_only
        self.state_dim = state_dim
        self.num_units = num_units
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.input_proj = nn.Linear(state_dim, hidden_dim)
        self.trunk = nn.ModuleList([
            ResBlock(hidden_dim, dropout=dropout) for _ in range(num_layers)
        ])
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )
        if not value_only:
            self.policy_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, num_units),
            )

    def forward(self, x):
        h = F.relu(self.input_proj(x))
        for block in self.trunk:
            h = block(h)
        value_logit = self.value_head(h).squeeze(-1)
        if self.value_only:
            return None, value_logit
        policy = self.policy_head(h)
        return policy, value_logit


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def load_schema(schema_path):
    """Load schema_v1.json and extract layout info."""
    with open(schema_path) as f:
        schema = json.load(f)
    return schema


def get_schema_defaults(checkpoint):
    """Extract schema parameters from checkpoint or defaults."""
    return {
        "state_dim": checkpoint["state_dim"],
        "num_units": checkpoint["num_units"],
        "features_per_unit": 11,
        "num_global_features": 14,
    }


# ---------------------------------------------------------------------------
# Mirror operation
# ---------------------------------------------------------------------------

def mirror_state(state, num_units, features_per_unit=11):
    """Mirror a state vector by swapping P0 and P1 perspectives.

    Per-unit layout (11 features per unit):
      [0] p0_ready, [1] p0_exhausted, [2] p0_constructing, [3] p0_blocking,
      [4] p1_ready, [5] p1_exhausted, [6] p1_constructing, [7] p1_blocking,
      [8] p0_supply, [9] p1_supply, [10] in_card_set

    Mirror swaps:
      - offsets [0,1,2,3] <-> [4,5,6,7]  (P0 states <-> P1 states)
      - offset 8 <-> 9                   (P0 supply <-> P1 supply)
      - offset 10 unchanged              (in_card_set is symmetric)

    Global features (last 14, indices state_dim-14 to state_dim-1):
      [0-5]  P0 resources (gold, blue, red, green, energy, attack)
      [6-11] P1 resources
      [12]   turn_number (unchanged)
      [13]   active_player (flipped: 0->1, 1->0)
    """
    mirrored = state.clone()
    unit_dim = num_units * features_per_unit

    for u in range(num_units):
        base = u * features_per_unit
        # Swap P0 state [0:4] with P1 state [4:8]
        for off in range(4):
            mirrored[base + off] = state[base + 4 + off]
            mirrored[base + 4 + off] = state[base + off]
        # Swap P0 supply [8] with P1 supply [9]
        mirrored[base + 8] = state[base + 9]
        mirrored[base + 9] = state[base + 8]
        # offset 10 (in_card_set) stays the same

    # Global features start at unit_dim
    g = unit_dim
    # Swap P0 resources [g+0:g+6] with P1 resources [g+6:g+12]
    for i in range(6):
        mirrored[g + i] = state[g + 6 + i]
        mirrored[g + 6 + i] = state[g + i]

    # turn_number [g+12] stays the same

    # active_player [g+13]: flip 0 <-> 1
    mirrored[g + 13] = 1.0 - state[g + 13]

    return mirrored


# ---------------------------------------------------------------------------
# Inference helper
# ---------------------------------------------------------------------------

@torch.no_grad()
def get_value_prob(model, state_tensor, device):
    """Return P(P0 wins) = sigmoid(logit) for a single state vector."""
    if state_tensor.dim() == 1:
        state_tensor = state_tensor.unsqueeze(0)
    state_tensor = state_tensor.to(device)
    _, logit = model(state_tensor)
    prob = torch.sigmoid(logit).item()
    return prob, logit.item()


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def check_zeros_input(model, state_dim, device):
    """Check 1: All-zeros input should produce value near 0.5."""
    print("\n[Check 1] All-zeros input -> value near 0.5")
    state = torch.zeros(state_dim)
    prob, logit = get_value_prob(model, state, device)
    deviation = abs(prob - 0.5)
    passed = deviation < 0.25  # within [0.25, 0.75]

    status = "PASS" if passed else "WARN"
    print(f"  Value: {prob:.4f} (logit={logit:.4f})")
    print(f"  Deviation from 0.5: {deviation:.4f}")
    print(f"  [{status}] {'Within acceptable range [0.25, 0.75]' if passed else 'Outside acceptable range [0.25, 0.75]'}")
    return passed, {"value": round(prob, 4), "logit": round(logit, 4),
                    "deviation": round(deviation, 4)}


def check_mirror_symmetry(model, state_dim, num_units, device, n_tests=20,
                           tolerance=0.15):
    """Check 2: value(state) + value(mirror(state)) should be ~ 1.0."""
    print(f"\n[Check 2] Mirror symmetry: v(s) + v(mirror(s)) ~ 1.0 "
          f"(tolerance={tolerance})")

    features_per_unit = 11
    unit_dim = num_units * features_per_unit
    rng = np.random.RandomState(42)
    violations = []
    all_sums = []

    for i in range(n_tests):
        # Generate a random-ish state with some structure
        state = torch.zeros(state_dim)

        # Randomly populate some units for both players
        n_active_units = rng.randint(3, min(20, num_units))
        active_units = rng.choice(num_units, n_active_units, replace=False)

        for u in active_units:
            base = u * features_per_unit
            # Random counts for P0 (offsets 0-3)
            for off in range(4):
                state[base + off] = float(rng.randint(0, 4))
            # Random counts for P1 (offsets 4-7)
            for off in range(4, 8):
                state[base + off] = float(rng.randint(0, 4))
            # Supply
            state[base + 8] = float(rng.randint(0, 10))
            state[base + 9] = float(rng.randint(0, 10))
            # in_card_set
            state[base + 10] = 1.0

        # Global features
        g = unit_dim
        # P0 resources (normalized)
        state[g + 0] = rng.uniform(0, 1)   # gold
        state[g + 1] = rng.uniform(0, 1)   # blue
        state[g + 2] = rng.uniform(0, 1)   # red
        state[g + 3] = rng.uniform(0, 1)   # green
        state[g + 4] = rng.uniform(0, 1)   # energy
        state[g + 5] = rng.uniform(0, 1)   # attack
        # P1 resources
        state[g + 6] = rng.uniform(0, 1)
        state[g + 7] = rng.uniform(0, 1)
        state[g + 8] = rng.uniform(0, 1)
        state[g + 9] = rng.uniform(0, 1)
        state[g + 10] = rng.uniform(0, 1)
        state[g + 11] = rng.uniform(0, 1)
        # turn number
        state[g + 12] = rng.uniform(0, 1)
        # active player
        state[g + 13] = float(rng.choice([0, 1]))

        mirrored = mirror_state(state, num_units, features_per_unit)

        prob_orig, _ = get_value_prob(model, state, device)
        prob_mirror, _ = get_value_prob(model, mirrored, device)

        pair_sum = prob_orig + prob_mirror
        all_sums.append(pair_sum)
        deviation = abs(pair_sum - 1.0)

        if deviation > tolerance:
            violations.append({
                "test": i,
                "v_original": round(prob_orig, 4),
                "v_mirrored": round(prob_mirror, 4),
                "sum": round(pair_sum, 4),
                "deviation": round(deviation, 4),
            })

    mean_sum = float(np.mean(all_sums))
    max_deviation = float(np.max(np.abs(np.array(all_sums) - 1.0)))
    n_violations = len(violations)
    passed = n_violations == 0

    status = "PASS" if passed else "WARN"
    print(f"  Mean sum: {mean_sum:.4f} (ideal=1.0)")
    print(f"  Max deviation: {max_deviation:.4f}")
    print(f"  Violations: {n_violations}/{n_tests}")
    if violations:
        for v in violations[:5]:
            print(f"    Test {v['test']}: v={v['v_original']:.4f}, "
                  f"v_mirror={v['v_mirrored']:.4f}, "
                  f"sum={v['sum']:.4f}, dev={v['deviation']:.4f}")
    print(f"  [{status}]")

    return passed, {
        "mean_sum": round(mean_sum, 4),
        "max_deviation": round(max_deviation, 4),
        "n_violations": n_violations,
        "n_tests": n_tests,
        "tolerance": tolerance,
    }


def check_monotonicity(model, state_dim, num_units, device, n_tests=10):
    """Check 3: Adding resources to P0 should not decrease P0's value
    significantly.

    Tests: increase P0 gold, P0 attack, P0 unit counts. Each should
    either increase or maintain P0 win probability.
    """
    print("\n[Check 3] Value monotonicity: more P0 resources -> higher P0 value")

    features_per_unit = 11
    unit_dim = num_units * features_per_unit
    rng = np.random.RandomState(123)

    violations = []
    total_tests = 0
    decrease_threshold = -0.05  # Allow tiny decreases from noise

    for i in range(n_tests):
        # Create a baseline state with some content
        state = torch.zeros(state_dim)

        # Populate a few units
        n_active = rng.randint(3, min(15, num_units))
        active = rng.choice(num_units, n_active, replace=False)
        for u in active:
            base = u * features_per_unit
            state[base + 0] = float(rng.randint(0, 3))  # p0_ready
            state[base + 4] = float(rng.randint(0, 3))  # p1_ready
            state[base + 8] = float(rng.randint(1, 8))  # p0_supply
            state[base + 9] = float(rng.randint(1, 8))  # p1_supply
            state[base + 10] = 1.0  # in_card_set

        g = unit_dim
        state[g + 0] = rng.uniform(0.1, 0.5)  # p0_gold
        state[g + 6] = rng.uniform(0.1, 0.5)  # p1_gold
        state[g + 12] = 0.2  # turn
        state[g + 13] = 0.0  # p0's turn

        base_prob, _ = get_value_prob(model, state, device)

        # Test: increase P0 gold
        mod = state.clone()
        mod[g + 0] = min(1.0, state[g + 0] + 0.3)
        prob_more_gold, _ = get_value_prob(model, mod, device)
        delta_gold = prob_more_gold - base_prob
        total_tests += 1
        if delta_gold < decrease_threshold:
            violations.append({
                "test": i, "perturbation": "p0_gold+0.3",
                "base": round(base_prob, 4),
                "perturbed": round(prob_more_gold, 4),
                "delta": round(delta_gold, 4),
            })

        # Test: increase P0 attack
        mod = state.clone()
        mod[g + 5] = min(1.0, state[g + 5] + 0.3)
        prob_more_attack, _ = get_value_prob(model, mod, device)
        delta_attack = prob_more_attack - base_prob
        total_tests += 1
        if delta_attack < decrease_threshold:
            violations.append({
                "test": i, "perturbation": "p0_attack+0.3",
                "base": round(base_prob, 4),
                "perturbed": round(prob_more_attack, 4),
                "delta": round(delta_attack, 4),
            })

        # Test: increase P0 unit count (add ready units)
        if len(active) > 0:
            u = active[0]
            base_off = u * features_per_unit
            mod = state.clone()
            mod[base_off + 0] = state[base_off + 0] + 2.0  # +2 ready units
            prob_more_units, _ = get_value_prob(model, mod, device)
            delta_units = prob_more_units - base_prob
            total_tests += 1
            if delta_units < decrease_threshold:
                violations.append({
                    "test": i, "perturbation": f"p0_ready[unit{u}]+2",
                    "base": round(base_prob, 4),
                    "perturbed": round(prob_more_units, 4),
                    "delta": round(delta_units, 4),
                })

    n_violations = len(violations)
    violation_rate = n_violations / max(total_tests, 1)
    passed = violation_rate < 0.3  # Allow up to 30% violations (untrained models)

    status = "PASS" if passed else "WARN"
    print(f"  Tests: {total_tests}, Violations: {n_violations} "
          f"({violation_rate:.0%})")
    if violations:
        for v in violations[:5]:
            print(f"    Test {v['test']}: {v['perturbation']} -> "
                  f"base={v['base']:.4f}, new={v['perturbed']:.4f}, "
                  f"delta={v['delta']:.4f}")
    print(f"  [{status}] {'Monotonicity mostly holds' if passed else 'Significant monotonicity violations'}")

    return passed, {
        "total_tests": total_tests,
        "n_violations": n_violations,
        "violation_rate": round(violation_rate, 4),
        "threshold": decrease_threshold,
    }


def check_nan_inf(model, state_dim, device, n_tests=100):
    """Check 4: No NaN or Inf outputs on random inputs."""
    print(f"\n[Check 4] No NaN/Inf outputs ({n_tests} random inputs)")

    rng = np.random.RandomState(999)
    nan_count = 0
    inf_count = 0

    # Test with various input distributions
    test_inputs = []

    # Zeros
    test_inputs.append(torch.zeros(state_dim))

    # Ones
    test_inputs.append(torch.ones(state_dim))

    # Random uniform [0, 1]
    for _ in range(n_tests // 4):
        test_inputs.append(torch.from_numpy(
            rng.uniform(0, 1, state_dim).astype(np.float32)))

    # Random with large values
    for _ in range(n_tests // 4):
        test_inputs.append(torch.from_numpy(
            rng.uniform(0, 20, state_dim).astype(np.float32)))

    # Sparse (mostly zeros)
    for _ in range(n_tests // 4):
        x = np.zeros(state_dim, dtype=np.float32)
        n_nonzero = rng.randint(5, 50)
        indices = rng.choice(state_dim, n_nonzero, replace=False)
        x[indices] = rng.uniform(0, 5, n_nonzero).astype(np.float32)
        test_inputs.append(torch.from_numpy(x))

    # Random negative values (shouldn't happen in practice but tests robustness)
    for _ in range(n_tests // 4):
        test_inputs.append(torch.from_numpy(
            rng.uniform(-1, 1, state_dim).astype(np.float32)))

    for inp in test_inputs:
        prob, logit = get_value_prob(model, inp, device)
        if np.isnan(prob) or np.isnan(logit):
            nan_count += 1
        if np.isinf(prob) or np.isinf(logit):
            inf_count += 1

    passed = nan_count == 0 and inf_count == 0
    status = "PASS" if passed else "FAIL"
    print(f"  Tested {len(test_inputs)} inputs")
    print(f"  NaN outputs: {nan_count}")
    print(f"  Inf outputs: {inf_count}")
    print(f"  [{status}]")

    return passed, {"n_tested": len(test_inputs), "nan_count": nan_count,
                    "inf_count": inf_count}


def check_value_range(model, state_dim, device, n_tests=100):
    """Check 5: All outputs should be in [0, 1] after sigmoid."""
    print(f"\n[Check 5] Value range [0, 1] after sigmoid ({n_tests} inputs)")

    rng = np.random.RandomState(777)
    out_of_range = 0
    all_probs = []

    for _ in range(n_tests):
        x = torch.from_numpy(
            rng.uniform(0, 5, state_dim).astype(np.float32))
        prob, _ = get_value_prob(model, x, device)
        all_probs.append(prob)
        if prob < 0.0 or prob > 1.0:
            out_of_range += 1

    probs_arr = np.array(all_probs)
    passed = out_of_range == 0
    status = "PASS" if passed else "FAIL"
    print(f"  Range: [{probs_arr.min():.6f}, {probs_arr.max():.6f}]")
    print(f"  Out of [0,1]: {out_of_range}/{n_tests}")
    print(f"  [{status}]")

    return passed, {
        "n_tested": n_tests,
        "out_of_range": out_of_range,
        "min_value": round(float(probs_arr.min()), 6),
        "max_value": round(float(probs_arr.max()), 6),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PrismataNet model sanity check")
    parser.add_argument("--model", type=str, required=True,
                        help="Path to model checkpoint (.pt)")
    parser.add_argument("--schema", type=str, default=None,
                        help="Path to schema JSON (default: auto-detect "
                             "training/schema_v1.json)")
    parser.add_argument("--device", type=str, default="cpu",
                        help="Device (default: cpu)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print extra detail")
    args = parser.parse_args()

    print("=" * 60)
    print("PrismataNet Sanity Check")
    print("=" * 60)

    # --- Load checkpoint ---
    print(f"\nLoading: {args.model}")
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=False)

    state_dim = checkpoint["state_dim"]
    num_units = checkpoint["num_units"]
    hidden_dim = checkpoint.get("hidden_dim", 256)
    num_layers = checkpoint.get("num_layers", 4)
    value_only = checkpoint.get("value_only", False)
    dropout = checkpoint.get("dropout", 0.1)

    print(f"  state_dim={state_dim}, num_units={num_units}, "
          f"hidden_dim={hidden_dim}, num_layers={num_layers}")

    # --- Load schema for reference ---
    if args.schema:
        schema_path = args.schema
    else:
        # Auto-detect
        script_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(script_dir, "schema_v1.json")

    if os.path.exists(schema_path):
        schema = load_schema(schema_path)
        print(f"  Schema: {schema_path} (v{schema.get('schema_version', '?')})")
        if schema["state_dim"] != state_dim:
            print(f"  WARNING: Schema state_dim={schema['state_dim']} != "
                  f"checkpoint state_dim={state_dim}")
        if schema["num_units"] != num_units:
            print(f"  WARNING: Schema num_units={schema['num_units']} != "
                  f"checkpoint num_units={num_units}")
    else:
        print(f"  Schema: not found at {schema_path}")

    # --- Build model ---
    device = torch.device(args.device)
    model = PrismataNet(state_dim, num_units, hidden_dim=hidden_dim,
                        num_layers=num_layers, dropout=dropout,
                        value_only=value_only)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {param_count:,}")

    # --- Run checks ---
    results = {}
    all_passed = True

    p1, r1 = check_zeros_input(model, state_dim, device)
    results["zeros_input"] = {"passed": p1, **r1}
    if not p1:
        all_passed = False

    p2, r2 = check_mirror_symmetry(model, state_dim, num_units, device)
    results["mirror_symmetry"] = {"passed": p2, **r2}
    if not p2:
        all_passed = False

    p3, r3 = check_monotonicity(model, state_dim, num_units, device)
    results["monotonicity"] = {"passed": p3, **r3}
    if not p3:
        all_passed = False

    p4, r4 = check_nan_inf(model, state_dim, device)
    results["nan_inf"] = {"passed": p4, **r4}
    if not p4:
        all_passed = False

    p5, r5 = check_value_range(model, state_dim, device)
    results["value_range"] = {"passed": p5, **r5}
    if not p5:
        all_passed = False

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SANITY CHECK SUMMARY")
    print("=" * 60)
    checks = [
        ("Zeros input ~0.5", p1),
        ("Mirror symmetry", p2),
        ("Monotonicity", p3),
        ("No NaN/Inf", p4),
        ("Value range [0,1]", p5),
    ]
    for name, passed in checks:
        status = "PASS" if passed else "WARN/FAIL"
        print(f"  {name:25s} [{status}]")

    overall = "ALL CHECKS PASSED" if all_passed else "SOME CHECKS FAILED"
    print(f"\n  Overall: {overall}")
    print("=" * 60)

    # --- Save results ---
    output_path = os.path.join(os.path.dirname(args.model),
                                "sanity_check_results.json")
    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump({"model": os.path.abspath(args.model),
                        "all_passed": all_passed,
                        "checks": results}, f, indent=2)
        print(f"\nResults saved to: {output_path}")
    except Exception as e:
        print(f"\nCould not save results: {e}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
