"""
Vectorize Prismata training data from JSON Lines to PyTorch tensors.

Input: training_data.jsonl (from extract_training_data.js)
Output: tensors saved to disk for training

Uses the canonical unit index and feature layout from training/schema.json.
See training/FEATURES.md for the full feature specification.

Feature encoding (schema version 2):
  - 161 canonical unit types from cardLibrary.jso
  - Per unit type: 11 features (4 status × 2 players + 2 supply + 1 card_set)
  - 14 global features: resources (6 × 2 players) + turn_number + active_player
  - Global features normalized via clamp-then-divide (caps from 99th percentile)
  - State vector size: 161 * 11 + 14 = 1785

Handles both:
  - New per-instance format: p0_units = [{name, toughness, building, abilityUsed, blocking, ...}, ...]
  - Old aggregated format: p0_units = {"Drone": {ready: 6, exhausted: 0, constructing: 2, blocking: 0}}

Action encoding:
  - bought: multi-hot vector over unit types (which units were purchased)
  - For value: +1 if active player won, -1 if lost
"""

import hashlib
import json
import os
import random
import re
import sys
from collections import defaultdict
from multiprocessing import Pool, cpu_count

sys.path.insert(0, "C:/libraries/torch_pkg")
import torch

# Normalization caps from schema.json (derived from 99th percentile of training data)
# See FEATURES.md for percentile rationale
GLOBAL_CAPS = {
    "gold": 20.0,
    "blue": 5.0,
    "red": 5.0,
    "green": 15.0,
    "energy": 10.0,
    "attack": 25.0,
    "turn_number": 30.0,
}


def clamp_divide(value, cap):
    """Normalize: clamp to [0, cap] then divide by cap → [0, 1]."""
    return min(float(value), cap) / cap


def load_schema(schema_path):
    """Load and validate the schema contract."""
    with open(schema_path, "r") as f:
        schema = json.load(f)

    required = ["feature_version", "state_dim", "num_units", "features_per_unit",
                 "num_global_features", "policy_dim", "unit_index_hash"]
    for key in required:
        if key not in schema:
            raise ValueError(f"Schema missing required key: {key}")

    return schema


def load_canonical_unit_index(index_path, expected_hash):
    """Load the canonical unit index and verify its hash."""
    with open(index_path, "r") as f:
        data = json.load(f)

    if "units" not in data or "version" not in data:
        raise ValueError(f"unit_index.json missing 'units' or 'version' key")

    unit_index = data["units"]

    # Verify hash matches schema
    sorted_names = sorted(unit_index.keys())
    hash_input = "\n".join(sorted_names).encode("utf-8")
    computed_hash = hashlib.sha256(hash_input).hexdigest()

    if computed_hash != expected_hash:
        raise ValueError(
            f"unit_index hash mismatch!\n"
            f"  Computed: {computed_hash}\n"
            f"  Expected: {expected_hash}\n"
            f"  This means unit_index.json is out of sync with schema.json"
        )

    if computed_hash != data["version"]:
        raise ValueError(
            f"unit_index.json internal hash mismatch!\n"
            f"  version field: {data['version']}\n"
            f"  Computed: {computed_hash}"
        )

    return unit_index


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


def vectorize_state(state, unit_index, num_units, turn, active_player):
    """Convert a state dict to a fixed-size float tensor.

    Layout matches FEATURES.md and schema.json exactly.
    """
    # Per-unit features: [p0_ready, p0_exhausted, p0_constructing, p0_blocking,
    #                     p1_ready, p1_exhausted, p1_constructing, p1_blocking,
    #                     p0_supply, p1_supply, in_card_set]
    unit_features = torch.zeros(num_units, 11)

    for player_idx, key in enumerate(("p0_units", "p1_units")):
        offset = player_idx * 4
        units = state.get(key, [])

        if isinstance(units, list):
            # New per-instance format: aggregate into counts
            for u in units:
                name = clean_unit_name(u["name"])
                if name not in unit_index:
                    continue
                idx = unit_index[name]

                if u.get("building", False):
                    unit_features[idx, offset + 2] += 1.0  # constructing
                elif u.get("blocking", False) and u.get("abilityUsed", False):
                    unit_features[idx, offset + 3] += 1.0  # assigned blocker
                elif u.get("abilityUsed", False):
                    unit_features[idx, offset + 1] += 1.0  # exhausted
                else:
                    unit_features[idx, offset + 0] += 1.0  # ready

        elif isinstance(units, dict):
            # Old aggregated format: {"Drone": {ready: 6, exhausted: 0, ...}}
            for name, counts in units.items():
                cname = clean_unit_name(name)
                if cname not in unit_index:
                    continue
                idx = unit_index[cname]
                unit_features[idx, offset + 0] = counts.get("ready", 0)
                unit_features[idx, offset + 1] = counts.get("exhausted", 0)
                unit_features[idx, offset + 2] = counts.get("constructing", 0)
                unit_features[idx, offset + 3] = counts.get("blocking", 0)

    # Supply
    for name, supply in state.get("supply", {}).items():
        cname = clean_unit_name(name)
        if cname not in unit_index:
            continue
        idx = unit_index[cname]
        if isinstance(supply, dict):
            p0_sup = supply.get("p0", 0)
            p1_sup = supply.get("p1", 0)
        else:
            p0_sup = supply
            p1_sup = supply
        unit_features[idx, 8] = p0_sup if p0_sup is not None else 0
        unit_features[idx, 9] = p1_sup if p1_sup is not None else 0

    # Card set
    for name in state.get("card_set", []):
        cname = clean_unit_name(name)
        if cname in unit_index:
            unit_features[unit_index[cname], 10] = 1.0

    # Flatten unit features
    flat = unit_features.view(-1)

    # Global features (14 total) — order MUST match C++ extractFeatures()
    # and schema.json feature_layout
    p0_res = state.get("p0_resources", {})
    p1_res = state.get("p1_resources", {})
    global_feats = torch.tensor([
        clamp_divide(p0_res.get("gold", 0), GLOBAL_CAPS["gold"]),
        clamp_divide(p0_res.get("blue", 0), GLOBAL_CAPS["blue"]),
        clamp_divide(p0_res.get("red", 0), GLOBAL_CAPS["red"]),
        clamp_divide(p0_res.get("green", 0), GLOBAL_CAPS["green"]),
        clamp_divide(p0_res.get("energy", 0), GLOBAL_CAPS["energy"]),
        clamp_divide(state.get("p0_attack", p0_res.get("attack", 0)), GLOBAL_CAPS["attack"]),
        clamp_divide(p1_res.get("gold", 0), GLOBAL_CAPS["gold"]),
        clamp_divide(p1_res.get("blue", 0), GLOBAL_CAPS["blue"]),
        clamp_divide(p1_res.get("red", 0), GLOBAL_CAPS["red"]),
        clamp_divide(p1_res.get("green", 0), GLOBAL_CAPS["green"]),
        clamp_divide(p1_res.get("energy", 0), GLOBAL_CAPS["energy"]),
        clamp_divide(state.get("p1_attack", p1_res.get("attack", 0)), GLOBAL_CAPS["attack"]),
        clamp_divide(turn, GLOBAL_CAPS["turn_number"]),
        float(active_player),
    ], dtype=torch.float32)

    return torch.cat([flat, global_feats])


def vectorize_action_buys(action, unit_index, num_units):
    """Convert buy action to multi-hot vector over unit types."""
    buys = torch.zeros(num_units)
    for name in action.get("bought", []):
        cname = clean_unit_name(name)
        if cname in unit_index:
            buys[unit_index[cname]] += 1.0  # Count (can buy multiples)
    return buys


def vectorize_example(ex, unit_index, num_units):
    """Convert one training example to tensors."""
    turn = ex.get("turn", 0)
    active_player = ex.get("active_player", 0)

    state_vec = vectorize_state(ex["state"], unit_index, num_units, turn, active_player)

    # Action targets
    buy_vec = vectorize_action_buys(ex.get("action", {}), unit_index, num_units)

    # Value target: +1 if active player won, -1 if lost
    result = ex["result"]
    if result == 2:
        value = 0.0
    elif active_player == 0:
        value = 1.0 if result == 0 else -1.0
    else:
        value = 1.0 if result == 1 else -1.0

    return state_vec, buy_vec, torch.tensor(value), torch.tensor(turn, dtype=torch.long)


def process_chunk(args):
    """Process a chunk of JSONL lines (for multiprocessing)."""
    lines, unit_index, num_units = args
    states = []
    buy_targets = []
    values = []
    turns = []

    for line in lines:
        ex = json.loads(line)
        s, b, v, t = vectorize_example(ex, unit_index, num_units)
        states.append(s)
        buy_targets.append(b)
        values.append(v)
        turns.append(t)

    return (
        torch.stack(states),
        torch.stack(buy_targets),
        torch.stack(values),
        torch.stack(turns),
    )


def process_jsonl(jsonl_path, unit_index, num_units, max_lines=None, num_workers=None):
    """Process full JSONL file into tensor arrays."""
    if num_workers is None:
        num_workers = min(cpu_count() - 2, 14)  # Leave 2 cores free

    print(f"  Using {num_workers} workers for vectorization")

    # Read all lines
    print("  Reading JSONL...")
    lines = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if max_lines and len(lines) >= max_lines:
                break
            lines.append(line)

    total = len(lines)
    print(f"  Read {total} lines")

    if num_workers <= 1 or total < 10000:
        # Single-threaded for small data
        states = []
        buy_targets = []
        values_list = []
        turns = []
        for i, line in enumerate(lines):
            ex = json.loads(line)
            s, b, v, t = vectorize_example(ex, unit_index, num_units)
            states.append(s)
            buy_targets.append(b)
            values_list.append(v)
            turns.append(t)
            if (i + 1) % 10000 == 0:
                print(f"  Vectorized {i + 1} / {total} examples...")
        return torch.stack(states), torch.stack(buy_targets), torch.stack(values_list), torch.stack(turns)

    # Split into chunks for parallel processing
    chunk_size = max(1000, total // num_workers)
    chunks = []
    for i in range(0, total, chunk_size):
        chunks.append((lines[i:i + chunk_size], unit_index, num_units))

    print(f"  Processing {len(chunks)} chunks across {num_workers} workers...")

    with Pool(num_workers) as pool:
        results = pool.map(process_chunk, chunks)

    # Merge results
    print("  Merging results...")
    all_states = torch.cat([r[0] for r in results])
    all_buys = torch.cat([r[1] for r in results])
    all_values = torch.cat([r[2] for r in results])
    all_turns = torch.cat([r[3] for r in results])

    return all_states, all_buys, all_values, all_turns


def main():
    jsonl_path = sys.argv[1] if len(sys.argv) > 1 else "c:/libraries/prismata-replay-parser/training_data.jsonl"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "c:/libraries/PrismataAI/training/data"
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")
    index_path = os.path.join(output_dir, "unit_index.json")

    os.makedirs(output_dir, exist_ok=True)

    print(f"Input: {jsonl_path}")
    print(f"Output: {output_dir}")
    print(f"Schema: {schema_path}")

    # Step 1: Load and validate schema
    print("\nLoading schema...")
    schema = load_schema(schema_path)
    print(f"  Feature version: {schema['feature_version']}")
    print(f"  Expected state_dim: {schema['state_dim']}")
    print(f"  Expected num_units: {schema['num_units']}")

    # Step 2: Load canonical unit index (validated against schema hash)
    print("\nLoading canonical unit index...")
    unit_index = load_canonical_unit_index(index_path, schema["unit_index_hash"])
    num_units = len(unit_index)
    print(f"  {num_units} canonical unit types")
    print(f"  Hash verified: {schema['unit_index_hash'][:16]}...")

    # Verify dimensions match schema
    expected_dim = num_units * schema["features_per_unit"] + schema["num_global_features"]
    if expected_dim != schema["state_dim"]:
        raise ValueError(f"Schema state_dim={schema['state_dim']} but computed {expected_dim}")
    print(f"  State dim: {expected_dim} ({num_units} × {schema['features_per_unit']} + {schema['num_global_features']})")

    # Step 3: Count UNK names and collect replay_codes (for train/val split)
    print("\nScanning for unknown unit names...")
    unk_count = 0
    unk_examples = 0
    unk_names = {}
    replay_codes = []
    total_scanned = 0
    with open(jsonl_path, "r") as f:
        for line in f:
            ex = json.loads(line)
            replay_codes.append(ex.get("replay_code", f"unknown_{total_scanned}"))
            has_unk = False
            for key in ("p0_units", "p1_units"):
                units = ex["state"].get(key, [])
                if isinstance(units, list):
                    for u in units:
                        cname = clean_unit_name(u["name"])
                        if cname not in unit_index:
                            unk_names[cname] = unk_names.get(cname, 0) + 1
                            unk_count += 1
                            has_unk = True
            if has_unk:
                unk_examples += 1
            total_scanned += 1
    print(f"  Scanned {total_scanned} examples")
    print(f"  UNK unit occurrences: {unk_count}")
    print(f"  Examples with UNK: {unk_examples} ({100*unk_examples/max(total_scanned,1):.2f}%)")
    if unk_names:
        print(f"  UNK names: {dict(sorted(unk_names.items(), key=lambda x: -x[1])[:10])}")
    unique_games = len(set(replay_codes))
    print(f"  Unique replay codes: {unique_games}")

    # Step 4: Vectorize all examples
    print("\nVectorizing training data...")
    states, buy_targets, values, turns = process_jsonl(jsonl_path, unit_index, num_units)

    state_dim = states.shape[1]
    print(f"  Examples: {states.shape[0]}")
    print(f"  State dimension: {state_dim} (schema expects {schema['state_dim']})")
    if state_dim != schema["state_dim"]:
        raise ValueError(f"State dim mismatch: got {state_dim}, schema says {schema['state_dim']}")
    print(f"  Buy target dimension: {buy_targets.shape[1]} (schema expects {schema['policy_dim']})")

    # Value distribution
    win_count = (values > 0).sum().item()
    loss_count = (values < 0).sum().item()
    draw_count = (values == 0).sum().item()
    total = len(values)
    print(f"  Value distribution: win={win_count} ({100*win_count/total:.1f}%), "
          f"loss={loss_count} ({100*loss_count/total:.1f}%), "
          f"draw={draw_count} ({100*draw_count/total:.1f}%)")
    print(f"  Value mean={values.mean():.4f}, std={values.std():.4f}, "
          f"min={values.min():.1f}, max={values.max():.1f}")

    # Check global features are populated and normalized
    global_start = num_units * 11
    global_feats = states[:, global_start:]
    print(f"\n  Global feature stats (all examples):")
    labels = ["p0_gold", "p0_blue", "p0_red", "p0_green", "p0_energy", "p0_attack",
              "p1_gold", "p1_blue", "p1_red", "p1_green", "p1_energy", "p1_attack",
              "turn/30", "active_player"]
    for i, label in enumerate(labels):
        col = global_feats[:, i]
        print(f"    {label:15s}: mean={col.mean():.4f}  min={col.min():.3f}  max={col.max():.3f}  "
              f"nonzero={((col != 0).sum().item()):>7d}")

    # Step 5: Train/val split by replay_code (90/10)
    # Split by game, not by example, to prevent data leakage.
    # All turns from a single game go entirely into train or val.
    code_to_indices = defaultdict(list)
    for i, code in enumerate(replay_codes):
        code_to_indices[code].append(i)

    unique_codes = list(code_to_indices.keys())
    random.seed(42)
    random.shuffle(unique_codes)
    split = int(len(unique_codes) * 0.9)
    train_codes = set(unique_codes[:split])

    train_idx = []
    val_idx = []
    for code, indices in code_to_indices.items():
        if code in train_codes:
            train_idx.extend(indices)
        else:
            val_idx.extend(indices)

    train_idx = torch.tensor(train_idx, dtype=torch.long)
    val_idx = torch.tensor(val_idx, dtype=torch.long)

    print(f"\n  Split by replay_code: {len(train_codes)} train games, "
          f"{len(unique_codes) - len(train_codes)} val games")
    print(f"  Train: {len(train_idx)} examples, Val: {len(val_idx)} examples")

    # Step 6: Save tensors with metadata
    print("\nSaving tensors...")
    metadata = {
        "schema_version": schema["feature_version"],
        "state_dim": state_dim,
        "num_units": num_units,
        "policy_dim": schema["policy_dim"],
        "unit_index_hash": schema["unit_index_hash"],
    }

    torch.save({
        "states": states[train_idx],
        "buy_targets": buy_targets[train_idx],
        "values": values[train_idx],
        "turns": turns[train_idx],
        "metadata": metadata,
    }, os.path.join(output_dir, "train.pt"))

    torch.save({
        "states": states[val_idx],
        "buy_targets": buy_targets[val_idx],
        "values": values[val_idx],
        "turns": turns[val_idx],
        "metadata": metadata,
    }, os.path.join(output_dir, "val.pt"))

    # Summary
    print(f"\nSaved to {output_dir}/")
    print(f"  train.pt: {len(train_idx)} examples")
    print(f"  val.pt: {len(val_idx)} examples")
    print(f"  state_dim: {state_dim}")
    print(f"  policy_dim: {schema['policy_dim']}")
    print(f"  schema_version: {schema['feature_version']}")

    # Top purchased units
    total_buys = buy_targets.sum(dim=0)
    top_bought = torch.argsort(total_buys, descending=True)[:15]
    idx_to_name = {v: k for k, v in unit_index.items()}
    print(f"\nTop 15 most purchased units across all examples:")
    for idx in top_bought:
        name = idx_to_name[idx.item()]
        count = total_buys[idx.item()].item()
        print(f"  {name:30s} {count:.0f}")


if __name__ == "__main__":
    main()
