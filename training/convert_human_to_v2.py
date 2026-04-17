"""
Convert human replay training data (V1 JSONL from extract_training_data.js)
to V2 JSONL format compatible with vectorize_v2.py for DeepSets training.

Input:  V1 JSONL from prismata-replay-parser/extract_training_data.js
        Each line: {replay_code, turn, active_player, result, p0_rating, p1_rating,
                    state: {p0_units, p1_units, supply, blueprints, card_set,
                            p0_resources, p1_resources, p0_attack, p1_attack},
                    action: {...}}

Output: V2 JSONL compatible with vectorize_v2.py
        Each line: {schema_version: "v2", instances: [...], supply: {...},
                    p0_resources, p1_resources, p0_attack, p1_attack,
                    turn_number, active_player, outcome_p0, ...}

Usage:
    python training/convert_human_to_v2.py \\
        --input c:/libraries/prismata-replay-parser/training_data.jsonl \\
        --output training/data/human_expert_v2.jsonl

    # With rating filter:
    python training/convert_human_to_v2.py \\
        --input training_data.jsonl --output expert_v2.jsonl --min-rating 1500
"""

import argparse
import json
import os
import sys
import time


def convert_unit_to_instance(unit, owner, blueprints):
    """Convert a V1 unit dict to a V2 instance dict.

    Args:
        unit: dict from state.p0_units or state.p1_units
        owner: 0 or 1
        blueprints: state.blueprints dict for hp_fraction lookup

    Returns:
        V2 instance dict with 10 features + name + owner
    """
    name = unit.get("name", "")
    if not name:
        return None

    # Base health from blueprints (for hp_fraction)
    bp = blueprints.get(name, {})
    base_health = bp.get("toughness", 1) or 1
    toughness = unit.get("toughness", 1)
    hp_fraction = float(toughness) / float(base_health) if base_health > 0 else 1.0

    # is_constructing: building flag or delay > 0
    building = unit.get("building", False)
    delay = unit.get("delay", 0) or 0
    is_constructing = 1 if building else 0
    turns_until_ready = delay if building else 0

    # ability_used
    ability_used = 1 if unit.get("abilityUsed", False) else 0

    # is_blocking
    is_blocking = 1 if unit.get("blocking", False) else 0

    # is_frozen: disruption > 0 means chilled
    is_frozen = 1 if (unit.get("disruption", 0) or 0) > 0 else 0

    # lifespan_remaining: null means permanent -> 0
    lifespan = unit.get("lifespan")
    lifespan_remaining = max(0, lifespan) if lifespan is not None else 0

    # stamina_remaining: charge count, null -> 0
    charge = unit.get("charge")
    stamina_remaining = charge if charge is not None else 0

    return {
        "name": name,
        "owner": owner,
        "is_constructing": is_constructing,
        "turns_until_ready": turns_until_ready,
        "is_blocking": is_blocking,
        "ability_used": ability_used,
        "current_hp": toughness,
        "hp_fraction": round(hp_fraction, 4),
        "is_frozen": is_frozen,
        "lifespan_remaining": lifespan_remaining,
        "stamina_remaining": stamina_remaining,
    }


def convert_supply(v1_supply, card_set):
    """Convert V1 supply format to V2.

    V1: {unitName: {p0: count, p1: count}}
    V2: {unitName: [p0_supply, p1_supply, in_card_set]}
    """
    card_set_names = set(card_set) if card_set else set()
    v2_supply = {}
    for name, counts in v1_supply.items():
        p0 = counts.get("p0", 0) if isinstance(counts, dict) else 0
        p1 = counts.get("p1", 0) if isinstance(counts, dict) else 0
        in_set = 1 if name in card_set_names else 0
        v2_supply[name] = [p0, p1, in_set]
    return v2_supply


def convert_record(v1_record, game_plies):
    """Convert a single V1 record to V2 format.

    Args:
        v1_record: parsed V1 JSONL record
        game_plies: dict mapping replay_code -> total_plies for the game

    Returns:
        V2 record dict, or None if invalid
    """
    state = v1_record.get("state")
    if not state:
        return None

    replay_code = v1_record.get("replay_code", "")
    blueprints = state.get("blueprints", {})

    # Build instances from p0_units + p1_units
    instances = []
    for unit in state.get("p0_units", []):
        inst = convert_unit_to_instance(unit, 0, blueprints)
        if inst:
            instances.append(inst)
    for unit in state.get("p1_units", []):
        inst = convert_unit_to_instance(unit, 1, blueprints)
        if inst:
            instances.append(inst)

    # Convert supply
    card_set = state.get("card_set", [])
    supply = convert_supply(state.get("supply", {}), card_set)

    # Resources (already in the right format)
    p0_res = state.get("p0_resources", {})
    p1_res = state.get("p1_resources", {})

    # Strip attack from resources (it's a separate field in V2)
    p0_resources = {
        "gold": p0_res.get("gold", 0),
        "blue": p0_res.get("blue", 0),
        "red": p0_res.get("red", 0),
        "green": p0_res.get("green", 0),
        "energy": p0_res.get("energy", 0),
    }
    p1_resources = {
        "gold": p1_res.get("gold", 0),
        "blue": p1_res.get("blue", 0),
        "red": p1_res.get("red", 0),
        "green": p1_res.get("green", 0),
        "energy": p1_res.get("energy", 0),
    }

    p0_attack = state.get("p0_attack", p0_res.get("attack", 0))
    p1_attack = state.get("p1_attack", p1_res.get("attack", 0))

    # Replay format: result=0 means P1 wins (first player), result=1 means P2 wins, result=2 means draw
    # Training format: outcome_p0 = 1 means P0 (first player) won
    # So we invert: result=0 (P1/first wins) → outcome_p0=1, result=1 (P2/second wins) → outcome_p0=0
    result = v1_record.get("result")
    if result is None:
        return None
    if result == 2:
        outcome_p0 = 0.5
    else:
        outcome_p0 = 1.0 - float(result)

    turn = v1_record.get("turn", 0)
    active_player = v1_record.get("active_player", 0)
    total_plies = game_plies.get(replay_code, turn + 1)

    return {
        "schema_version": "v2",
        "instances": instances,
        "supply": supply,
        "p0_resources": p0_resources,
        "p1_resources": p1_resources,
        "p0_attack": p0_attack,
        "p1_attack": p1_attack,
        "turn_number": turn,
        "active_player": active_player,
        "outcome_p0": outcome_p0,
        "replay_code": replay_code,
        "ply_index": turn,
        "total_plies": total_plies,
        "rating_p0": int(v1_record.get("p0_rating", 0)),
        "rating_p1": int(v1_record.get("p1_rating", 0)),
        "game_date": "",
        "card_set": card_set,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert human replay V1 JSONL to V2 format for DeepSets vectorization."
    )
    parser.add_argument("--input", required=True,
                        help="Input V1 JSONL file (from extract_training_data.js)")
    parser.add_argument("--output", required=True,
                        help="Output V2 JSONL file")
    parser.add_argument("--min-rating", type=int, default=0,
                        help="Minimum player rating (skip if either player below)")
    parser.add_argument("--max-records", type=int, default=0,
                        help="Maximum records to output (0 = all)")
    args = parser.parse_args()

    print(f"Input:      {args.input}")
    print(f"Output:     {args.output}")
    if args.min_rating > 0:
        print(f"Min rating: {args.min_rating}")
    print()

    # First pass: count plies per game (for total_plies field)
    print("Pass 1: counting plies per game...")
    t0 = time.time()
    game_plies = {}
    total_lines = 0
    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            try:
                rec = json.loads(line)
                code = rec.get("replay_code", "")
                turn = rec.get("turn", 0)
                if code not in game_plies or turn + 1 > game_plies[code]:
                    game_plies[code] = turn + 1
            except json.JSONDecodeError:
                continue
    print(f"  {total_lines:,} records, {len(game_plies):,} unique games")

    # Second pass: convert
    print("Pass 2: converting to V2 format...")
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    converted = 0
    skipped_rating = 0
    skipped_invalid = 0
    instance_counts = []

    with open(args.input, "r", encoding="utf-8") as fin, \
         open(args.output, "w", encoding="utf-8") as fout:
        for line in fin:
            try:
                v1_rec = json.loads(line)
            except json.JSONDecodeError:
                skipped_invalid += 1
                continue

            # Rating filter
            if args.min_rating > 0:
                r0 = v1_rec.get("p0_rating", 0)
                r1 = v1_rec.get("p1_rating", 0)
                if r0 < args.min_rating or r1 < args.min_rating:
                    skipped_rating += 1
                    continue

            v2_rec = convert_record(v1_rec, game_plies)
            if v2_rec is None:
                skipped_invalid += 1
                continue

            fout.write(json.dumps(v2_rec, separators=(",", ":")) + "\n")
            instance_counts.append(len(v2_rec["instances"]))
            converted += 1

            if converted % 50000 == 0:
                elapsed = time.time() - t0
                print(f"  {converted:,} converted ({converted/max(elapsed,1):.0f} rec/s)")

            if args.max_records > 0 and converted >= args.max_records:
                break

    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"Conversion complete!")
    print(f"  Converted:      {converted:,}")
    print(f"  Skipped (rating): {skipped_rating:,}")
    print(f"  Skipped (invalid): {skipped_invalid:,}")
    print(f"  Time:           {elapsed:.1f}s")

    if instance_counts:
        import statistics
        print(f"\n  Instance counts:")
        print(f"    Min:    {min(instance_counts)}")
        print(f"    Max:    {max(instance_counts)}")
        print(f"    Mean:   {statistics.mean(instance_counts):.1f}")
        print(f"    Median: {statistics.median(instance_counts):.1f}")

    file_size_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"\n  Output: {args.output} ({file_size_mb:.1f} MB)")
    print(f"\n  Next step: vectorize with:")
    print(f"    python training/vectorize_v2.py --input {args.output} "
          f"--output {args.output.replace('.jsonl', '.h5')}")


if __name__ == "__main__":
    main()
