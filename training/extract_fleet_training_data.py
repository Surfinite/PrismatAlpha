"""
Extract V2 training data from MasterBot fleet replay .json.gz files.

Reads full game replays and outputs V2-format JSONL compatible with vectorize_v2.py.
Each turn boundary produces one training record with all 10 instance features.

Usage:
    python training/extract_fleet_training_data.py \
        --replay-dir training/data/masterbot_fleet_v3/replays \
        --output training/data/fleet_v3_training.jsonl

    # Limit for testing:
    python training/extract_fleet_training_data.py \
        --replay-dir training/data/masterbot_fleet_v3/replays \
        --output test.jsonl --max-games 100
"""

import argparse
import glob
import gzip
import json
import os
import time


# ---------------------------------------------------------------------------
# Card library loading (for base_health and fragile lookup)
# ---------------------------------------------------------------------------

def load_card_library(lib_path):
    """Load cardLibrary.jso and build name -> base_health lookup.

    Returns dict mapping display name -> int (base toughness)
    """
    with open(lib_path, "r", encoding="utf-8") as f:
        lib = json.load(f)

    card_info = {}
    for internal_name, data in lib.items():
        if not isinstance(data, dict):
            continue
        ui_name = data.get("UIName", internal_name)
        card_info[ui_name] = data.get("toughness", 1)

    return card_info


# ---------------------------------------------------------------------------
# Mana string parsing
# ---------------------------------------------------------------------------

def parse_mana(mana_str):
    """Parse a Prismata mana string into resource dict.

    Format: leading digits = gold, then letter codes:
      H = energy, G = green, B = blue, C = red, A = attack

    Examples:
      "10HHGGGBCCAAAAAA" -> {gold:10, energy:2, green:3, blue:1, red:2, attack:6}
      "0" -> {gold:0, ...}
      "HH" -> {gold:0, energy:2, ...}

    Returns: dict with keys gold, blue, red, green, energy, attack
    """
    resources = {"gold": 0, "blue": 0, "red": 0, "green": 0, "energy": 0, "attack": 0}

    if not mana_str or mana_str == "0":
        return resources

    # Extract leading digits as gold
    i = 0
    while i < len(mana_str) and mana_str[i].isdigit():
        i += 1
    if i > 0:
        resources["gold"] = int(mana_str[:i])

    # Count letter codes
    letter_map = {"H": "energy", "G": "green", "B": "blue", "C": "red", "A": "attack"}
    for ch in mana_str[i:]:
        if ch in letter_map:
            resources[letter_map[ch]] += 1

    return resources


# ---------------------------------------------------------------------------
# Instance feature extraction
# ---------------------------------------------------------------------------

def extract_instance(unit, card_info):
    """Convert a replay table unit entry to V2 instance feature dict.

    Args:
        unit: dict from replay state.table[]
        card_info: dict from load_card_library()

    Returns:
        dict with V2 instance feature keys, or None if unit should be skipped
    """
    name = unit.get("cardName", "")
    if not name:
        return None

    base_health = card_info.get(name, 1)
    health = unit.get("health", 1)
    max_hp = float(base_health)
    hp_fraction = float(health) / max_hp if max_hp > 0 else 1.0

    # is_constructing: unit has remaining construction time
    construction_time = unit.get("constructionTime", 0)
    is_constructing = 1 if construction_time > 0 else 0

    # turns_until_ready: construction time + delay
    delay = unit.get("delay", 0)
    turns_until_ready = construction_time + delay

    # ability_used: role == "assigned" means ability was used this turn
    role = unit.get("role", "default")
    ability_used = 1 if role == "assigned" else 0

    # is_frozen: disruptDamage > 0 means unit has been chilled/frozen
    is_frozen = 1 if unit.get("disruptDamage", 0) > 0 else 0

    # lifespan_remaining: -1 means permanent, map to 0
    lifespan = unit.get("lifespan", -1)
    lifespan_remaining = max(0, lifespan)

    # stamina_remaining: charge count
    stamina_remaining = unit.get("charge", 0)

    # is_blocking
    is_blocking = 1 if unit.get("blocking", False) else 0

    return {
        "name": name,
        "owner": unit.get("owner", 0),
        "is_constructing": is_constructing,
        "turns_until_ready": turns_until_ready,
        "is_blocking": is_blocking,
        "ability_used": ability_used,
        "current_hp": health,
        "hp_fraction": round(hp_fraction, 4),
        "is_frozen": is_frozen,
        "lifespan_remaining": lifespan_remaining,
        "stamina_remaining": stamina_remaining,
    }


# ---------------------------------------------------------------------------
# Supply extraction
# ---------------------------------------------------------------------------

def extract_supply(state):
    """Extract supply dict from replay state.

    Returns: dict mapping unit display name -> [p0_supply, p1_supply, in_card_set]
    where p0 = white, p1 = black.
    """
    cards = state.get("cards", [])
    white_total = state.get("whiteTotalSupply", [])
    black_total = state.get("blackTotalSupply", [])
    white_spent = state.get("whiteSupplySpent", [])
    black_spent = state.get("blackSupplySpent", [])

    supply = {}
    for i, card_name in enumerate(cards):
        p0_avail = (white_total[i] if i < len(white_total) else 0) - \
                   (white_spent[i] if i < len(white_spent) else 0)
        p1_avail = (black_total[i] if i < len(black_total) else 0) - \
                   (black_spent[i] if i < len(black_spent) else 0)
        # in_card_set: base set units are always available, others are in the card set
        in_card_set = 1  # all cards in the state.cards list are in the card set
        supply[card_name] = [max(0, p0_avail), max(0, p1_avail), in_card_set]

    return supply


# ---------------------------------------------------------------------------
# Single replay processing
# ---------------------------------------------------------------------------

def process_replay(replay_data, card_info, game_id=""):
    """Process a single replay into V2 JSONL records.

    Extracts one record per turn boundary (start of each player-turn).

    Args:
        replay_data: parsed JSON from .json.gz
        card_info: from load_card_library()
        game_id: identifier for the replay (filename)

    Returns:
        list of V2-format record dicts
    """
    states = replay_data.get("states", [])
    turn_boundaries = replay_data.get("turnBoundaries", [])
    winner = replay_data.get("winner", -1)  # 0 or 1

    if not states or not turn_boundaries:
        return []

    # outcome_p0: 1.0 if P0 (white) won, 0.0 if P1 (black) won
    if winner == 0:
        outcome_p0 = 1.0
    elif winner == 1:
        outcome_p0 = 0.0
    else:
        return []  # skip draws or unknown outcomes

    total_plies = len(turn_boundaries)
    card_set = replay_data.get("cardSet", [])

    records = []

    for ply_idx, state_idx in enumerate(turn_boundaries):
        if state_idx >= len(states):
            break

        state = states[state_idx]
        table = state.get("table", [])
        turn = state.get("turn", 0)  # 0 = P0 (white), 1 = P1 (black)

        # Extract instances from table
        instances = []
        for unit in table:
            inst = extract_instance(unit, card_info)
            if inst is not None:
                instances.append(inst)

        # Parse resources
        white_res = parse_mana(state.get("whiteMana", "0"))
        black_res = parse_mana(state.get("blackMana", "0"))

        p0_resources = {
            "gold": white_res["gold"],
            "blue": white_res["blue"],
            "red": white_res["red"],
            "green": white_res["green"],
            "energy": white_res["energy"],
        }
        p1_resources = {
            "gold": black_res["gold"],
            "blue": black_res["blue"],
            "red": black_res["red"],
            "green": black_res["green"],
            "energy": black_res["energy"],
        }

        p0_attack = white_res["attack"]
        p1_attack = black_res["attack"]

        # Extract supply
        supply = extract_supply(state)

        record = {
            "schema_version": "v2",
            "instances": instances,
            "supply": supply,
            "p0_resources": p0_resources,
            "p1_resources": p1_resources,
            "p0_attack": p0_attack,
            "p1_attack": p1_attack,
            "turn_number": ply_idx,  # sequential ply index as turn number
            "active_player": turn,   # 0 = P0 (white), 1 = P1 (black)
            "outcome_p0": outcome_p0,
            "replay_code": game_id,
            "ply_index": ply_idx,
            "total_plies": total_plies,
            "rating_p0": 1500,  # MasterBot has no rating; use neutral
            "rating_p1": 1500,
            "game_date": "",
            "card_set": card_set,
        }

        records.append(record)

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_replay_files(replay_dir):
    """Find all .json.gz and .json replay files recursively."""
    gz_pattern = os.path.join(replay_dir, "**", "*.json.gz")
    json_pattern = os.path.join(replay_dir, "**", "*.json")
    files = glob.glob(gz_pattern, recursive=True) + glob.glob(json_pattern, recursive=True)
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(
        description="Extract V2 training data from fleet replay .json.gz files."
    )
    parser.add_argument("--replay-dir", required=True,
                        help="Root directory containing .json.gz replay files")
    parser.add_argument("--output", required=True,
                        help="Output JSONL file path")
    parser.add_argument("--card-library", default=None,
                        help="Path to cardLibrary.jso (default: bin/asset/config/cardLibrary.jso)")
    parser.add_argument("--max-games", type=int, default=0,
                        help="Max games to process (0 = all)")
    parser.add_argument("--progress-interval", type=int, default=1000,
                        help="Print progress every N games")
    args = parser.parse_args()

    # Resolve card library path
    if args.card_library:
        lib_path = args.card_library
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        lib_path = os.path.join(script_dir, "..", "bin", "asset", "config", "cardLibrary.jso")

    print(f"Replay dir:    {args.replay_dir}")
    print(f"Output:        {args.output}")
    print(f"Card library:  {lib_path}")
    print()

    # Load card library
    print("Loading card library...")
    card_info = load_card_library(lib_path)
    print(f"  {len(card_info)} unit types loaded")

    # Find replay files
    print(f"Scanning for replay files in {args.replay_dir}...")
    replay_files = find_replay_files(args.replay_dir)
    total_files = len(replay_files)
    print(f"  Found {total_files} replay files")

    if args.max_games > 0:
        replay_files = replay_files[:args.max_games]
        print(f"  Limited to {len(replay_files)} games")

    # Process replays
    print(f"\nExtracting training data...")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    t_start = time.time()
    total_records = 0
    games_processed = 0
    games_skipped = 0
    instance_counts = []

    with open(args.output, "w", encoding="utf-8") as out_f:
        for i, gz_path in enumerate(replay_files):
            try:
                if gz_path.endswith(".gz"):
                    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                        replay_data = json.load(f)
                else:
                    with open(gz_path, "r", encoding="utf-8") as f:
                        replay_data = json.load(f)
            except Exception:
                games_skipped += 1
                continue

            game_id = os.path.splitext(os.path.basename(gz_path))[0]
            # Include parent dir for uniqueness
            parent = os.path.basename(os.path.dirname(gz_path))
            game_id = f"{parent}/{game_id}"

            records = process_replay(replay_data, card_info, game_id=game_id)

            for rec in records:
                out_f.write(json.dumps(rec, separators=(",", ":")) + "\n")
                instance_counts.append(len(rec["instances"]))
                total_records += 1

            games_processed += 1

            if (i + 1) % args.progress_interval == 0:
                elapsed = time.time() - t_start
                rate = (i + 1) / max(elapsed, 0.001)
                print(f"  {i+1:>8d} / {len(replay_files)} games "
                      f"({100*(i+1)/len(replay_files):.1f}%) "
                      f"[{rate:.0f} games/s, {total_records} records]")

    elapsed = time.time() - t_start

    # Summary
    print(f"\n{'='*60}")
    print(f"Extraction complete!")
    print(f"  Games processed: {games_processed}")
    print(f"  Games skipped:   {games_skipped}")
    print(f"  Total records:   {total_records}")
    print(f"  Records/game:    {total_records/max(games_processed,1):.1f}")
    print(f"  Time:            {elapsed:.1f}s ({games_processed/max(elapsed,1):.0f} games/s)")

    if instance_counts:
        import statistics
        print(f"\n  Instance counts:")
        print(f"    Min:    {min(instance_counts)}")
        print(f"    Max:    {max(instance_counts)}")
        print(f"    Mean:   {statistics.mean(instance_counts):.1f}")
        print(f"    Median: {statistics.median(instance_counts):.1f}")
        print(f"    P95:    {sorted(instance_counts)[int(len(instance_counts)*0.95)]}")
        print(f"    P99:    {sorted(instance_counts)[int(len(instance_counts)*0.99)]}")

    file_size_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"\n  Output: {args.output} ({file_size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
