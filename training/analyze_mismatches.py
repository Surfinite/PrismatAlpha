"""
Aggregate mismatch analysis across all failed replay validations.

Reads validation_results.json to find FAILed replays, then re-parses
the C++ output and TS input to categorize mismatch patterns.

Usage:
    python analyze_mismatches.py <batch_dir>
"""

import json
import sys
import re
from pathlib import Path
from collections import Counter, defaultdict

# Import comparison helpers from compare_states
sys.path.insert(0, str(Path(__file__).parent))
from compare_states import (
    extract_cpp_state, extract_ts_state,
    parse_mana_string, normalize_name,
    BEGIN_TURN_DEATH_UNITS,
    DISPLAY_TO_INTERNAL, INTERNAL_TO_DISPLAY
)


def parse_multiline_jsonl(filepath):
    """Parse C++ JSONL output which uses pretty-printed multi-line JSON objects."""
    with open(filepath, 'r') as f:
        content = f.read()

    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(content):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objects.append(json.loads(content[start:i+1]))
                except json.JSONDecodeError:
                    pass
                start = None
    return objects


def analyze_single_replay(batch_dir, code):
    """Analyze mismatches for a single failed replay. Returns structured mismatch data."""
    base = f"{code}_states"
    cpp_output_path = batch_dir / f"{base}_cpp_output.jsonl"
    cpp_input_path = batch_dir / f"{base}_cpp.json"

    if not cpp_output_path.exists() or not cpp_input_path.exists():
        return None

    # Parse C++ output
    cpp_states = parse_multiline_jsonl(cpp_output_path)
    if not cpp_states:
        return None

    # Parse TS input
    with open(cpp_input_path, 'r') as f:
        validation = json.load(f)
    turns = validation.get('turns', [])

    PHASE_DEFENSE = 1
    mismatches = []
    first_diverge_turn = None

    for cpp_entry in cpp_states:
        cpp_turn = cpp_entry.get('turn', -1)

        if cpp_turn == -1:
            # Initial state
            if not turns:
                continue
            ts_state = extract_ts_state(turns[0]['ts_state_before'])
            cpp_state = extract_cpp_state(cpp_entry['state'])
        else:
            next_turn_idx = cpp_turn + 1
            if next_turn_idx >= len(turns):
                continue
            ts_state = extract_ts_state(turns[next_turn_idx]['ts_state_before'])
            cpp_state = extract_cpp_state(cpp_entry['state'])

        phase_after = cpp_entry.get('phase_after', 0)
        active_after = cpp_entry.get('active_player_after', -1)
        in_defense = (phase_after == PHASE_DEFENSE)

        # Compare resources
        for player in [0, 1]:
            pkey = f'p{player}_resources'
            cpp_res = cpp_state[pkey]
            ts_res = ts_state[pkey]
            skip_transient = (active_after != player) or in_defense
            persistent = ['gold', 'green']
            transient = ['energy', 'blue', 'red', 'attack']
            resources_to_check = persistent if skip_transient else persistent + transient

            for res_type in resources_to_check:
                cpp_val = cpp_res.get(res_type, 0)
                ts_val = ts_res.get(res_type, 0)
                if cpp_val != ts_val:
                    mismatches.append({
                        'turn': cpp_turn,
                        'category': 'resource',
                        'field': f'p{player}_{res_type}',
                        'cpp': cpp_val,
                        'ts': ts_val,
                        'diff': cpp_val - ts_val,
                    })
                    if first_diverge_turn is None:
                        first_diverge_turn = cpp_turn

        # Compare unit counts
        for player in [0, 1]:
            pkey = f'p{player}_unit_counts'
            cpp_counts = cpp_state[pkey]
            ts_counts = ts_state[pkey]
            all_types = set(list(cpp_counts.keys()) + list(ts_counts.keys()))

            for unit_type in sorted(all_types):
                cpp_val = cpp_counts.get(unit_type, 0)
                ts_val = ts_counts.get(unit_type, 0)
                if cpp_val != ts_val:
                    # Check for selfsac timing tolerance
                    if (unit_type in BEGIN_TURN_DEATH_UNITS and cpp_val < ts_val
                            and player == active_after):
                        continue  # Tolerated

                    mismatches.append({
                        'turn': cpp_turn,
                        'category': 'unit',
                        'field': f'p{player}_{unit_type}',
                        'unit_type': unit_type,
                        'player': player,
                        'cpp': cpp_val,
                        'ts': ts_val,
                        'diff': cpp_val - ts_val,
                    })
                    if first_diverge_turn is None:
                        first_diverge_turn = cpp_turn

        # Compare supply
        cpp_supply = cpp_state.get('supply', {})
        ts_supply = ts_state.get('supply', {})
        all_supply_types = set(list(cpp_supply.keys()) + list(ts_supply.keys()))
        for unit_type in sorted(all_supply_types):
            cpp_entry_s = cpp_supply.get(unit_type, {'p0': 0, 'p1': 0})
            ts_entry_s = ts_supply.get(unit_type, {'p0': 0, 'p1': 0})
            for pk in ['p0', 'p1']:
                cpp_val = cpp_entry_s.get(pk, 0)
                ts_val = ts_entry_s.get(pk, 0)
                if cpp_val != ts_val:
                    mismatches.append({
                        'turn': cpp_turn,
                        'category': 'supply',
                        'field': f'supply_{unit_type}_{pk}',
                        'unit_type': unit_type,
                        'cpp': cpp_val,
                        'ts': ts_val,
                        'diff': cpp_val - ts_val,
                    })
                    if first_diverge_turn is None:
                        first_diverge_turn = cpp_turn

    total_turns = len(turns)
    return {
        'code': code,
        'total_turns': total_turns,
        'total_mismatches': len(mismatches),
        'first_diverge_turn': first_diverge_turn,
        'mismatches': mismatches,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_mismatches.py <batch_dir>")
        sys.exit(1)

    batch_dir = Path(sys.argv[1])
    results_file = batch_dir / "validation_results.json"

    with open(results_file, 'r') as f:
        results = json.load(f)

    failed = [r for r in results['results'] if r['status'] == 'FAIL']
    print(f"Analyzing {len(failed)} failed replays from {batch_dir}")
    print()

    # Aggregation counters
    unit_mismatch_counts = Counter()      # unit_type -> total mismatches
    unit_cpp_more = Counter()             # unit_type -> times C++ has more
    unit_ts_more = Counter()              # unit_type -> times TS has more
    unit_replays_affected = defaultdict(set)  # unit_type -> set of replay codes
    resource_mismatch_counts = Counter()  # resource field -> total mismatches
    resource_cpp_more = Counter()
    resource_ts_more = Counter()
    supply_mismatch_counts = Counter()    # unit_type -> total supply mismatches
    supply_replays_affected = defaultdict(set)
    first_diverge_turns = []
    category_counts = Counter()           # resource/unit/supply -> total
    replays_by_first_category = Counter() # first mismatch category -> count

    errors = 0
    analyzed = 0

    for i, r in enumerate(failed):
        code = r['code']
        result = analyze_single_replay(batch_dir, code)
        if result is None:
            errors += 1
            continue
        analyzed += 1

        if result['first_diverge_turn'] is not None:
            first_diverge_turns.append(result['first_diverge_turn'])

        # Track first mismatch category per replay
        first_cat = None
        for m in result['mismatches']:
            cat = m['category']
            category_counts[cat] += 1
            if first_cat is None:
                first_cat = cat

            if cat == 'unit':
                ut = m['unit_type']
                unit_mismatch_counts[ut] += 1
                unit_replays_affected[ut].add(code)
                if m['diff'] > 0:
                    unit_cpp_more[ut] += 1
                else:
                    unit_ts_more[ut] += 1

            elif cat == 'resource':
                field = m['field']
                resource_mismatch_counts[field] += 1
                if m['diff'] > 0:
                    resource_cpp_more[field] += 1
                else:
                    resource_ts_more[field] += 1

            elif cat == 'supply':
                ut = m.get('unit_type', m['field'])
                supply_mismatch_counts[ut] += 1
                supply_replays_affected[ut].add(code)

        if first_cat:
            replays_by_first_category[first_cat] += 1

        if (i + 1) % 200 == 0:
            print(f"  Progress: {i+1}/{len(failed)} analyzed...")

    print(f"\n{'='*70}")
    print(f"MISMATCH ANALYSIS SUMMARY")
    print(f"{'='*70}")
    print(f"Failed replays analyzed: {analyzed} (skipped: {errors})")
    print()

    # Category breakdown
    print(f"--- Mismatch Categories (total individual mismatches) ---")
    for cat, count in category_counts.most_common():
        pct = count / sum(category_counts.values()) * 100
        print(f"  {cat:12s}: {count:6d}  ({pct:.1f}%)")
    print()

    print(f"--- First Mismatch Category Per Replay ---")
    for cat, count in replays_by_first_category.most_common():
        pct = count / analyzed * 100
        print(f"  {cat:12s}: {count:4d} replays  ({pct:.1f}%)")
    print()

    # First divergence turn distribution
    if first_diverge_turns:
        from statistics import mean, median
        print(f"--- First Divergence Turn ---")
        print(f"  Mean:   {mean(first_diverge_turns):.1f}")
        print(f"  Median: {median(first_diverge_turns):.0f}")
        print(f"  Min:    {min(first_diverge_turns)}")
        print(f"  Max:    {max(first_diverge_turns)}")

        # Distribution buckets
        buckets = Counter()
        for t in first_diverge_turns:
            if t == -1:
                buckets['initial'] += 1
            elif t <= 2:
                buckets['0-2'] += 1
            elif t <= 5:
                buckets['3-5'] += 1
            elif t <= 10:
                buckets['6-10'] += 1
            elif t <= 20:
                buckets['11-20'] += 1
            else:
                buckets['21+'] += 1
        print(f"  Distribution:")
        for label in ['initial', '0-2', '3-5', '6-10', '11-20', '21+']:
            count = buckets.get(label, 0)
            bar = '#' * (count // 5)
            print(f"    {label:>8s}: {count:4d}  {bar}")
        print()

    # Top mismatched unit types
    print(f"--- Top 25 Mismatched Unit Types ---")
    print(f"  {'Unit':<25s} {'Total':>6s} {'C++>TS':>7s} {'TS>C++':>7s} {'Replays':>8s}")
    print(f"  {'-'*25} {'-'*6} {'-'*7} {'-'*7} {'-'*8}")
    for ut, count in unit_mismatch_counts.most_common(25):
        cpp_m = unit_cpp_more.get(ut, 0)
        ts_m = unit_ts_more.get(ut, 0)
        replays = len(unit_replays_affected[ut])
        selfsac = " [selfsac/lifespan]" if ut in BEGIN_TURN_DEATH_UNITS else ""
        print(f"  {ut:<25s} {count:6d} {cpp_m:7d} {ts_m:7d} {replays:8d}{selfsac}")
    print()

    # Resource mismatches
    print(f"--- Resource Mismatches ---")
    print(f"  {'Field':<20s} {'Total':>6s} {'C++>TS':>7s} {'TS>C++':>7s}")
    print(f"  {'-'*20} {'-'*6} {'-'*7} {'-'*7}")
    for field, count in resource_mismatch_counts.most_common():
        cpp_m = resource_cpp_more.get(field, 0)
        ts_m = resource_ts_more.get(field, 0)
        print(f"  {field:<20s} {count:6d} {cpp_m:7d} {ts_m:7d}")
    print()

    # Supply mismatches
    print(f"--- Top 25 Supply Mismatches ---")
    print(f"  {'Unit':<25s} {'Total':>6s} {'Replays':>8s}")
    print(f"  {'-'*25} {'-'*6} {'-'*8}")
    for ut, count in supply_mismatch_counts.most_common(25):
        replays = len(supply_replays_affected[ut])
        print(f"  {ut:<25s} {count:6d} {replays:8d}")
    print()

    # Identify units that are ONLY C++>TS or ONLY TS>C++ (strong directional signal)
    print(f"--- Directional Unit Signals (>90% one direction, 50+ mismatches) ---")
    for ut, count in unit_mismatch_counts.most_common():
        if count < 50:
            continue
        cpp_m = unit_cpp_more.get(ut, 0)
        ts_m = unit_ts_more.get(ut, 0)
        if cpp_m > 0 and cpp_m / count > 0.9:
            print(f"  C++ has MORE {ut}: {cpp_m}/{count} ({cpp_m/count*100:.0f}%) — {len(unit_replays_affected[ut])} replays")
        elif ts_m > 0 and ts_m / count > 0.9:
            print(f"  TS has MORE {ut}: {ts_m}/{count} ({ts_m/count*100:.0f}%) — {len(unit_replays_affected[ut])} replays")
    print()

    # Cross-reference: which unit types co-occur with resource mismatches?
    print(f"--- Done ---")
    print(f"Total individual mismatches: {sum(category_counts.values())}")


if __name__ == '__main__':
    main()
