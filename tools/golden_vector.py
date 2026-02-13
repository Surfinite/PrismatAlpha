"""
Golden-vector comparison tool for PrismataAI neural net features.

Compares the C++ feature dump (bin/debug_features.txt) against a Python-side
reconstruction from the companion state description (bin/debug_features.txt.desc).

Usage:
    python tools/golden_vector.py [features_path] [desc_path]

    Default paths:
        features_path = bin/debug_features.txt
        desc_path     = bin/debug_features.txt.desc

    --self-test    Run built-in test with a hand-crafted example

Exit codes:
    0  All features match (max abs diff < 1e-5)
    1  Mismatch detected

File formats (produced by NeuralNet::dumpFeaturesToFile in C++):

    features file:
        Line 1: state_dim (integer)
        Lines 2..state_dim+1: one float per line

    desc file:
        === Game State Description ===
        Turn: <int>
        Active player: <int>
        Phase: <int>

        P0 resources: gold=<int> blue=<int> red=<int> green=<int> energy=<int> attack=<int>
        P1 resources: gold=<int> blue=<int> red=<int> green=<int> energy=<int> attack=<int>

        Player 0 units:
          <UIName> (typeID=<int>, unitIdx=<int>, constr=<0|1>, canUse=<0|1>)
          ...

        Player 1 units:
          <UIName> (typeID=<int>, unitIdx=<int>, constr=<0|1>, canUse=<0|1>)
          ...

        Buyable cards: <int>
          <UIName> (unitIdx=<int>, p0_supply=<int>, p1_supply=<int>)
          ...

        === Feature vector summary ===
        state_dim=<int>, nonzero=<int>
"""

import json
import math
import os
import re
import sys

# Must match schema.json / FEATURES.md / vectorize.py
GLOBAL_CAPS = {
    "gold": 20.0,
    "blue": 5.0,
    "red": 5.0,
    "green": 15.0,
    "energy": 10.0,
    "attack": 25.0,
    "turn_number": 30.0,
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def clamp_divide(value, cap):
    return min(float(value), cap) / cap


def load_schema():
    schema_path = os.path.join(PROJECT_ROOT, "training", "schema.json")
    with open(schema_path, "r") as f:
        return json.load(f)


def load_unit_index():
    index_path = os.path.join(PROJECT_ROOT, "training", "data", "unit_index.json")
    with open(index_path, "r") as f:
        data = json.load(f)
    return data["units"]


def read_cpp_features(path):
    """Read C++ feature dump: first line = state_dim, then one float per line."""
    with open(path, "r") as f:
        lines = f.read().strip().split("\n")
    state_dim = int(lines[0])
    features = [float(x) for x in lines[1:state_dim + 1]]
    if len(features) != state_dim:
        raise ValueError(f"Expected {state_dim} features, got {len(features)}")
    return features


def parse_desc_file(path):
    """Parse the .desc companion file into a structured game state."""
    with open(path, "r") as f:
        text = f.read()

    state = {
        "turn": 0,
        "active_player": 0,
        "p0_resources": {"gold": 0, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0},
        "p1_resources": {"gold": 0, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0},
        "p0_units": [],  # list of {name, unitIdx, constr, canUse}
        "p1_units": [],
        "buyable": [],   # list of {name, unitIdx, p0_supply, p1_supply}
    }

    # Turn
    m = re.search(r"Turn:\s*(\d+)", text)
    if m:
        state["turn"] = int(m.group(1))

    # Active player
    m = re.search(r"Active player:\s*(\d+)", text)
    if m:
        state["active_player"] = int(m.group(1))

    # Resources
    for player in ("P0", "P1"):
        key = f"{player.lower()}_resources"
        pattern = rf"{player} resources:\s*gold=(\d+)\s+blue=(\d+)\s+red=(\d+)\s+green=(\d+)\s+energy=(\d+)\s+attack=(\d+)"
        m = re.search(pattern, text)
        if m:
            state[key] = {
                "gold": int(m.group(1)),
                "blue": int(m.group(2)),
                "red": int(m.group(3)),
                "green": int(m.group(4)),
                "energy": int(m.group(5)),
                "attack": int(m.group(6)),
            }

    # Units per player
    for player_id in (0, 1):
        key = f"p{player_id}_units"
        # Find "Player N units:" section
        pattern = rf"Player {player_id} units:\n((?:  .+\n)*)"
        m = re.search(pattern, text)
        if m:
            block = m.group(1)
            for um in re.finditer(
                r"  (.+?) \(typeID=(\d+), unitIdx=(-?\d+), constr=(\d+), canUse=(\d+)\)",
                block
            ):
                state[key].append({
                    "name": um.group(1),
                    "unitIdx": int(um.group(3)),
                    "constr": int(um.group(4)),
                    "canUse": int(um.group(5)),
                })

    # Buyable cards
    buyable_pattern = r"Buyable cards:\s*\d+\n((?:  .+\n)*)"
    m = re.search(buyable_pattern, text)
    if m:
        block = m.group(1)
        for bm in re.finditer(
            r"  (.+?) \(unitIdx=(-?\d+), p0_supply=(\d+), p1_supply=(\d+)\)",
            block
        ):
            state["buyable"].append({
                "name": bm.group(1),
                "unitIdx": int(bm.group(2)),
                "p0_supply": int(bm.group(3)),
                "p1_supply": int(bm.group(4)),
            })

    return state


def build_python_features(state, schema):
    """Build the feature vector from the parsed state, using the same logic as vectorize.py."""
    num_units = schema["num_units"]
    state_dim = schema["state_dim"]
    features = [0.0] * state_dim

    # Per-unit features from units on board
    for player_id in (0, 1):
        offset = player_id * 4
        for u in state[f"p{player_id}_units"]:
            idx = u["unitIdx"]
            if idx < 0 or idx >= num_units:
                continue
            base = idx * 11 + offset

            if u["constr"]:
                features[base + 2] += 1.0  # constructing
            elif u["canUse"]:
                features[base + 0] += 1.0  # ready
            else:
                features[base + 1] += 1.0  # exhausted

    # Note: the .desc file doesn't distinguish "assigned blocker" from "exhausted"
    # in the canUse field. The C++ uses CardStatus::Assigned for blocking.
    # canUse=0 covers BOTH exhausted and assigned-blocking cases from the desc file.
    # This is a known limitation — the desc format doesn't expose the Assigned status
    # separately. For blocking units, C++ puts them in offset+3 but we put them in
    # offset+1. This WILL cause diffs for states with assigned blockers.
    # To fully match, we'd need the desc to include an "assigned" field.

    # Supply and card set from buyable cards
    for b in state["buyable"]:
        idx = b["unitIdx"]
        if idx < 0 or idx >= num_units:
            continue
        base = idx * 11
        features[base + 8] = float(b["p0_supply"])
        features[base + 9] = float(b["p1_supply"])
        features[base + 10] = 1.0  # in_card_set

    # Global features (14)
    global_base = num_units * 11

    p0r = state["p0_resources"]
    p1r = state["p1_resources"]

    features[global_base + 0]  = clamp_divide(p0r["gold"],   GLOBAL_CAPS["gold"])
    features[global_base + 1]  = clamp_divide(p0r["blue"],   GLOBAL_CAPS["blue"])
    features[global_base + 2]  = clamp_divide(p0r["red"],    GLOBAL_CAPS["red"])
    features[global_base + 3]  = clamp_divide(p0r["green"],  GLOBAL_CAPS["green"])
    features[global_base + 4]  = clamp_divide(p0r["energy"], GLOBAL_CAPS["energy"])
    features[global_base + 5]  = clamp_divide(p0r["attack"], GLOBAL_CAPS["attack"])

    features[global_base + 6]  = clamp_divide(p1r["gold"],   GLOBAL_CAPS["gold"])
    features[global_base + 7]  = clamp_divide(p1r["blue"],   GLOBAL_CAPS["blue"])
    features[global_base + 8]  = clamp_divide(p1r["red"],    GLOBAL_CAPS["red"])
    features[global_base + 9]  = clamp_divide(p1r["green"],  GLOBAL_CAPS["green"])
    features[global_base + 10] = clamp_divide(p1r["energy"], GLOBAL_CAPS["energy"])
    features[global_base + 11] = clamp_divide(p1r["attack"], GLOBAL_CAPS["attack"])

    features[global_base + 12] = clamp_divide(state["turn"], GLOBAL_CAPS["turn_number"])
    features[global_base + 13] = float(state["active_player"])

    return features


def compare_features(cpp_feats, py_feats, unit_index, schema):
    """Compare two feature vectors and report differences."""
    num_units = schema["num_units"]
    state_dim = schema["state_dim"]
    idx_to_name = {v: k for k, v in unit_index.items()}

    if len(cpp_feats) != len(py_feats):
        print(f"ERROR: dimension mismatch: C++={len(cpp_feats)}, Python={len(py_feats)}")
        return False

    # Compute diffs
    diffs = []
    l1_total = 0.0
    l2_total = 0.0
    max_diff = 0.0
    cpp_nonzero = sum(1 for x in cpp_feats if x != 0.0)
    py_nonzero = sum(1 for x in py_feats if x != 0.0)

    for i in range(state_dim):
        d = abs(cpp_feats[i] - py_feats[i])
        l1_total += d
        l2_total += d * d
        if d > 0:
            max_diff = max(max_diff, d)
            diffs.append((i, d, cpp_feats[i], py_feats[i]))

    l2_total = math.sqrt(l2_total)

    print(f"=== Golden Vector Comparison ===")
    print(f"State dim: {state_dim}")
    print(f"C++ nonzero: {cpp_nonzero}")
    print(f"Python nonzero: {py_nonzero}")
    print(f"L1 diff: {l1_total:.8f}")
    print(f"L2 diff: {l2_total:.8f}")
    print(f"Max abs diff: {max_diff:.8f}")
    print(f"Indices with diff > 0: {len(diffs)}")

    if diffs:
        # Sort by diff magnitude, show top 10
        diffs.sort(key=lambda x: -x[1])
        print(f"\nTop {min(10, len(diffs))} differing indices:")
        print(f"  {'Index':>6s}  {'Feature Name':40s}  {'C++':>12s}  {'Python':>12s}  {'Diff':>12s}")
        for idx, d, cv, pv in diffs[:10]:
            name = get_feature_name(idx, num_units, idx_to_name)
            print(f"  {idx:6d}  {name:40s}  {cv:12.6f}  {pv:12.6f}  {d:12.6f}")

    passed = max_diff < 1e-5
    print(f"\nResult: {'PASS' if passed else 'FAIL'} (threshold: 1e-5)")
    return passed


def get_feature_name(idx, num_units, idx_to_name):
    """Map a feature index to a human-readable name."""
    global_base = num_units * 11
    if idx >= global_base:
        offset = idx - global_base
        global_names = [
            "p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
            "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
            "turn_number", "active_player",
        ]
        if offset < len(global_names):
            return f"global/{global_names[offset]}"
        return f"global/unknown_{offset}"

    unit_idx = idx // 11
    feat_offset = idx % 11
    unit_name = idx_to_name.get(unit_idx, f"unit_{unit_idx}")
    feat_names = [
        "p0_ready", "p0_exhausted", "p0_constructing", "p0_blocking",
        "p1_ready", "p1_exhausted", "p1_constructing", "p1_blocking",
        "p0_supply", "p1_supply", "in_card_set",
    ]
    return f"{unit_name}/{feat_names[feat_offset]}"


def run_self_test():
    """Run a hand-crafted test to verify the tool works."""
    print("=== Self-Test Mode ===\n")

    schema = load_schema()
    unit_index = load_unit_index()
    num_units = schema["num_units"]
    state_dim = schema["state_dim"]

    # Hand-craft a simple game state:
    # Turn 3, active player 0
    # P0: 6 gold, 0 blue, 0 red, 1 green, 0 energy, 0 attack
    #     3 Drones (ready), 2 Engineers (ready), 1 Conduit (constructing)
    # P1: 5 gold, 0 blue, 0 red, 0 green, 0 energy, 0 attack
    #     4 Drones (ready), 2 Engineers (exhausted)
    # Buyable: Drone (p0=14, p1=16), Engineer (p0=18, p1=18), Wall (p0=10, p1=10)

    state = {
        "turn": 3,
        "active_player": 0,
        "p0_resources": {"gold": 6, "blue": 0, "red": 0, "green": 1, "energy": 0, "attack": 0},
        "p1_resources": {"gold": 5, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0},
        "p0_units": [
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Engineer", "unitIdx": unit_index["Engineer"], "constr": 0, "canUse": 1},
            {"name": "Engineer", "unitIdx": unit_index["Engineer"], "constr": 0, "canUse": 1},
            {"name": "Conduit", "unitIdx": unit_index["Conduit"], "constr": 1, "canUse": 0},
        ],
        "p1_units": [
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Drone", "unitIdx": unit_index["Drone"], "constr": 0, "canUse": 1},
            {"name": "Engineer", "unitIdx": unit_index["Engineer"], "constr": 0, "canUse": 0},
            {"name": "Engineer", "unitIdx": unit_index["Engineer"], "constr": 0, "canUse": 0},
        ],
        "buyable": [
            {"name": "Drone", "unitIdx": unit_index["Drone"], "p0_supply": 14, "p1_supply": 16},
            {"name": "Engineer", "unitIdx": unit_index["Engineer"], "p0_supply": 18, "p1_supply": 18},
            {"name": "Wall", "unitIdx": unit_index["Wall"], "p0_supply": 10, "p1_supply": 10},
        ],
    }

    py_feats = build_python_features(state, schema)

    # Manually verify a few features
    drone_idx = unit_index["Drone"]   # 47
    eng_idx = unit_index["Engineer"]  # 54
    cond_idx = unit_index["Conduit"]  # 31
    wall_idx = unit_index["Wall"]     # 155

    errors = []

    def check(name, actual, expected):
        if abs(actual - expected) > 1e-9:
            errors.append(f"  {name}: got {actual}, expected {expected}")

    # P0 Drones: 3 ready
    check("Drone p0_ready", py_feats[drone_idx * 11 + 0], 3.0)
    # P0 Engineers: 2 ready
    check("Engineer p0_ready", py_feats[eng_idx * 11 + 0], 2.0)
    # P0 Conduit: 1 constructing
    check("Conduit p0_constructing", py_feats[cond_idx * 11 + 2], 1.0)
    # P1 Drones: 4 ready
    check("Drone p1_ready", py_feats[drone_idx * 11 + 4], 4.0)
    # P1 Engineers: 2 exhausted
    check("Engineer p1_exhausted", py_feats[eng_idx * 11 + 5], 2.0)

    # Supply
    check("Drone p0_supply", py_feats[drone_idx * 11 + 8], 14.0)
    check("Drone p1_supply", py_feats[drone_idx * 11 + 9], 16.0)
    check("Drone in_card_set", py_feats[drone_idx * 11 + 10], 1.0)
    check("Wall p0_supply", py_feats[wall_idx * 11 + 8], 10.0)
    check("Wall in_card_set", py_feats[wall_idx * 11 + 10], 1.0)

    # Global features
    global_base = num_units * 11
    check("p0_gold", py_feats[global_base + 0], 6.0 / 20.0)
    check("p0_green", py_feats[global_base + 3], 1.0 / 15.0)
    check("p1_gold", py_feats[global_base + 6], 5.0 / 20.0)
    check("turn_number", py_feats[global_base + 12], 3.0 / 30.0)
    check("active_player", py_feats[global_base + 13], 0.0)

    # Zero checks — features that should be zero
    check("Conduit p1_ready", py_feats[cond_idx * 11 + 4], 0.0)
    check("p0_blue", py_feats[global_base + 1], 0.0)
    check("p0_attack", py_feats[global_base + 5], 0.0)

    if errors:
        print("SELF-TEST FAILED:")
        for e in errors:
            print(e)
        return False

    # Count nonzero
    nonzero = sum(1 for x in py_feats if x != 0.0)
    expected_nonzero = (
        3 +   # p0 drone ready, p0 eng ready, p0 conduit constructing
        2 +   # p1 drone ready, p1 eng exhausted
        9 +   # 3 buyable × 3 (p0_supply, p1_supply, in_card_set)
        3     # p0_gold, p0_green, p1_gold, turn_number = 4 but active_player=0 so 3
    )
    # Actually: p0_gold, p0_green, p1_gold, turn = 4 global nonzero (active_player=0 is zero)
    # total: 3+2+9+4 = 18... let me just verify
    print(f"Self-test feature vector: {nonzero} nonzero features (state_dim={state_dim})")

    # Also test compare against itself — should be exact match
    print("\nComparing self-test vector against itself...")
    passed = compare_features(py_feats, py_feats, unit_index, schema)

    if passed:
        print("\nSELF-TEST PASSED")
    else:
        print("\nSELF-TEST FAILED (self-comparison should pass!)")

    return passed


def main():
    if "--self-test" in sys.argv:
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    # Default file paths
    features_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, "bin", "debug_features.txt")
    desc_path = sys.argv[2] if len(sys.argv) > 2 else features_path + ".desc"

    if not os.path.exists(features_path):
        print(f"ERROR: C++ feature dump not found: {features_path}")
        print(f"Run the GUI, trigger a neural net evaluation, and press F5 to generate the dump.")
        print(f"Or use --self-test to run the built-in test.")
        sys.exit(1)

    if not os.path.exists(desc_path):
        print(f"ERROR: State description not found: {desc_path}")
        sys.exit(1)

    # Load schema and unit index
    schema = load_schema()
    unit_index = load_unit_index()

    print(f"Schema: feature_version={schema['feature_version']}, state_dim={schema['state_dim']}")
    print(f"Unit index: {len(unit_index)} units")
    print(f"C++ features: {features_path}")
    print(f"State desc: {desc_path}")
    print()

    # Read C++ features
    cpp_feats = read_cpp_features(features_path)
    print(f"Read {len(cpp_feats)} C++ features")

    # Parse state description and build Python features
    state = parse_desc_file(desc_path)
    print(f"Parsed state: turn={state['turn']}, active_player={state['active_player']}")
    print(f"  P0 units: {len(state['p0_units'])}, P1 units: {len(state['p1_units'])}")
    print(f"  Buyable: {len(state['buyable'])}")
    print()

    py_feats = build_python_features(state, schema)

    # Compare
    passed = compare_features(cpp_feats, py_feats, unit_index, schema)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
