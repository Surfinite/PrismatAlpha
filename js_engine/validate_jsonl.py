#!/usr/bin/env python3
"""Validate JS engine JSONL output against vectorize.py format requirements."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'training'))

def validate_example(ex, line_num):
    """Validate one training example. Returns list of issues."""
    issues = []

    # Required top-level fields
    for field in ('state', 'turn', 'active_player', 'result'):
        if field not in ex:
            issues.append(f"L{line_num}: Missing required field '{field}'")

    state = ex.get('state', {})

    # Required state fields
    for field in ('p0_units', 'p1_units', 'p0_resources', 'p1_resources', 'card_set'):
        if field not in state:
            issues.append(f"L{line_num}: Missing state field '{field}'")

    # Check units format (should be list of dicts with 'name')
    for pkey in ('p0_units', 'p1_units'):
        units = state.get(pkey, [])
        if not isinstance(units, list):
            issues.append(f"L{line_num}: {pkey} should be list, got {type(units).__name__}")
        else:
            for i, u in enumerate(units):
                if not isinstance(u, dict):
                    issues.append(f"L{line_num}: {pkey}[{i}] should be dict")
                elif 'name' not in u:
                    issues.append(f"L{line_num}: {pkey}[{i}] missing 'name'")

    # Check resources format
    for pkey in ('p0_resources', 'p1_resources'):
        res = state.get(pkey, {})
        if not isinstance(res, dict):
            issues.append(f"L{line_num}: {pkey} should be dict")
        else:
            for field in ('gold', 'green', 'blue', 'red', 'energy', 'attack'):
                if field not in res:
                    issues.append(f"L{line_num}: {pkey} missing '{field}'")

    # Check card_set
    card_set = state.get('card_set', [])
    if not isinstance(card_set, list):
        issues.append(f"L{line_num}: card_set should be list")

    # Check result values
    result = ex.get('result')
    if result not in (0, 1, 2, None):
        issues.append(f"L{line_num}: Invalid result: {result}")

    # Check turn and active_player
    turn = ex.get('turn', -1)
    if not isinstance(turn, int) or turn < 0:
        issues.append(f"L{line_num}: Invalid turn: {turn}")

    ap = ex.get('active_player', -1)
    if ap not in (0, 1):
        issues.append(f"L{line_num}: Invalid active_player: {ap}")

    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_jsonl.py <file.jsonl>")
        sys.exit(1)

    jsonl_path = sys.argv[1]
    total = 0
    issues = []
    results = {0: 0, 1: 0, 2: 0, None: 0}
    unit_names = set()
    card_sets = set()

    with open(jsonl_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
            except json.JSONDecodeError as e:
                issues.append(f"L{line_num}: JSON parse error: {e}")
                continue

            total += 1
            line_issues = validate_example(ex, line_num)
            issues.extend(line_issues)

            result = ex.get('result')
            results[result] = results.get(result, 0) + 1

            for pkey in ('p0_units', 'p1_units'):
                for u in ex.get('state', {}).get(pkey, []):
                    if isinstance(u, dict):
                        unit_names.add(u.get('name', '?'))

            card_set = tuple(sorted(ex.get('state', {}).get('card_set', [])))
            card_sets.add(card_set)

    print(f"\n=== JSONL Validation Report ===")
    print(f"File: {jsonl_path}")
    print(f"Total examples: {total}")
    print(f"Issues: {len(issues)}")
    print(f"Results: P0={results.get(0, 0)} P1={results.get(1, 0)} Draw={results.get(2, 0)} Ongoing={results.get(None, 0)}")
    print(f"Unique unit names: {len(unit_names)}")
    print(f"Unique card sets: {len(card_sets)}")

    if issues:
        print(f"\n--- Issues ---")
        for issue in issues[:20]:
            print(f"  {issue}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more")
    else:
        print(f"\nAll examples valid!")

    # Try vectorize if available
    try:
        from vectorize import vectorize_example
        unit_index_path = os.path.join(os.path.dirname(__file__), '..', 'training', 'data', 'unit_index.json')
        with open(unit_index_path, 'r') as f:
            data = json.load(f)
        unit_index = data.get('units', data)  # Handle nested format
        num_units = len(unit_index)

        # Test first example
        with open(jsonl_path, 'r') as f:
            first_line = f.readline().strip()
        if first_line:
            ex = json.loads(first_line)
            state_vec, buy_vec, value, turn = vectorize_example(ex, unit_index, num_units)
            print(f"\n--- Vectorize Test (first example) ---")
            print(f"State vector: shape={state_vec.shape}, min={state_vec.min():.3f}, max={state_vec.max():.3f}")
            print(f"Buy vector: shape={buy_vec.shape}, sum={buy_vec.sum():.0f}")
            print(f"Value: {value.item():.1f}")
            print(f"Turn: {turn.item()}")
            print(f"Vectorize: PASS")
    except ImportError:
        print(f"\n(torch not available, skipping vectorize test)")
    except Exception as e:
        print(f"\n--- Vectorize Test ---")
        print(f"FAIL: {e}")

    return 0 if len(issues) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
