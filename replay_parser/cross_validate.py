"""Cross-validate Python replay parser against JS engine.

Runs the same replays through both the Python parser and JS engine,
compares per-turn buy sequences, unit counts, and resources,
then reports divergence rates by turn tier.

Usage:
    python -m replay_parser.cross_validate \
        --db c:/libraries/prismata-replay-parser/replays.db \
        --replays-dir c:/libraries/prismata-replay-parser/replays_archive/ \
        --sample 500

    # Or with a specific list of codes:
    python -m replay_parser.cross_validate \
        --replays-dir c:/libraries/prismata-replay-parser/replays_archive/ \
        --codes-file codes.txt
"""

import argparse
import json
import logging
import os
import random
import sqlite3
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the JS extraction script
JS_EXTRACT = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          'js_engine', 'extract_turn_data.js')


def get_sample_codes(db_path: str, sample_size: int, seed: int = 42) -> list[str]:
    """Get a random sample of parsed replay codes from the database."""
    conn = sqlite3.connect(db_path)
    codes = [row[0] for row in conn.execute(
        "SELECT code FROM replay_parse_status WHERE parsed = 1"
    ).fetchall()]
    conn.close()

    random.seed(seed)
    if len(codes) <= sample_size:
        return codes
    return random.sample(codes, sample_size)


def run_js_extraction(codes: list[str], replays_dir: str) -> dict[str, dict]:
    """Run the JS engine extraction on a list of replay codes.

    Returns dict of code → JS turn data.
    """
    # Write codes to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('\n'.join(codes) + '\n')
        codes_file = f.name

    try:
        logger.info(f"Running JS extraction on {len(codes)} replays...")
        result = subprocess.run(
            ['node', JS_EXTRACT, '--batch', codes_file,
             '--replays-dir', replays_dir],
            capture_output=True, text=True, timeout=600
        )

        if result.returncode != 0:
            logger.error(f"JS extraction stderr: {result.stderr[-500:]}")

        # Parse JSONL output
        js_data = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get('error'):
                    logger.warning(f"JS error for {entry['code']}: {entry['error']}")
                    continue
                js_data[entry['code']] = entry
            except json.JSONDecodeError:
                continue

        logger.info(f"JS extraction complete: {len(js_data)} replays")
        return js_data
    finally:
        os.unlink(codes_file)


def run_python_parsing(codes: list[str], replays_dir: str) -> dict[str, dict]:
    """Run the Python parser on a list of replay codes.

    Returns dict of code → Python parsed data (as dicts matching JS structure).
    """
    from replay_parser.decoder import load_replay, decode
    from replay_parser.simulator import simulate
    from replay_parser.fetch import code_to_filename

    py_data = {}
    for code in codes:
        filename = code_to_filename(code)
        filepath = os.path.join(replays_dir, filename)
        if not os.path.exists(filepath):
            continue

        try:
            raw = load_replay(filepath)
            replay = decode(raw)
            simulate(replay)

            turns = []
            for turn in replay.turns:
                turns.append({
                    'global_turn': turn.global_turn,
                    'player': turn.player,
                    'player_turn': turn.player_turn,
                    'buys': turn.buys,
                    'units_owned': turn.units_owned,
                    'resources': {
                        'gold': turn.resources_at_start.gold,
                        'green': turn.resources_at_start.green,
                        'blue': turn.resources_at_start.blue,
                        'red': turn.resources_at_start.red,
                        'energy': turn.resources_at_start.energy,
                        'attack': turn.resources_at_start.attack,
                    }
                })

            py_data[code] = {
                'code': code,
                'result': replay.result,
                'totalTurns': replay.total_global_turns,
                'turns': turns
            }
        except Exception as e:
            logger.warning(f"Python parse error for {code}: {e}")

    logger.info(f"Python parsing complete: {len(py_data)} replays")
    return py_data


def compare_buys(py_buys: list[str], js_buys: list[str]) -> tuple[bool, str]:
    """Compare buy sequences (order-independent — compare as sorted lists)."""
    py_sorted = sorted(py_buys)
    js_sorted = sorted(js_buys)
    if py_sorted == js_sorted:
        return True, ""
    return False, f"PY={py_sorted} JS={js_sorted}"


def compare_units(py_units: dict, js_units: dict) -> tuple[bool, str]:
    """Compare unit count dicts."""
    # Normalize: remove zero-count entries
    py_clean = {k: v for k, v in py_units.items() if v > 0}
    js_clean = {k: v for k, v in js_units.items() if v > 0}
    if py_clean == js_clean:
        return True, ""

    diffs = []
    all_keys = set(py_clean.keys()) | set(js_clean.keys())
    for key in sorted(all_keys):
        pv = py_clean.get(key, 0)
        jv = js_clean.get(key, 0)
        if pv != jv:
            diffs.append(f"{key}: PY={pv} JS={jv}")
    return False, "; ".join(diffs)


def compare_resources(py_res: dict, js_res: dict) -> tuple[bool, str]:
    """Compare resource pools."""
    fields = ['gold', 'green', 'blue', 'red', 'energy', 'attack']
    diffs = []
    for f in fields:
        pv = py_res.get(f, 0)
        jv = js_res.get(f, 0)
        if pv != jv:
            diffs.append(f"{f}: PY={pv} JS={jv}")
    if not diffs:
        return True, ""
    return False, "; ".join(diffs)


def classify_turn(player_turn: int) -> str:
    """Classify a turn into a tier for reporting."""
    if player_turn <= 5:
        return "1-5"
    elif player_turn <= 10:
        return "6-10"
    else:
        return "11+"


def run_comparison(py_data: dict, js_data: dict) -> dict:
    """Compare Python and JS outputs, return detailed report."""
    common_codes = set(py_data.keys()) & set(js_data.keys())
    logger.info(f"Comparing {len(common_codes)} replays (both parsed successfully)")

    # Per-tier stats
    tiers = ["1-5", "6-10", "11+"]
    stats = {
        tier: {
            'total': 0,
            'buy_match': 0, 'buy_mismatch': 0,
            'unit_match': 0, 'unit_mismatch': 0,
            'resource_match': 0, 'resource_mismatch': 0,
        }
        for tier in tiers
    }

    # Detailed divergences (first N per category)
    divergences = {
        'buy': [],
        'unit': [],
        'resource': [],
    }
    MAX_DIVERGENCES = 20  # Keep first N examples per category

    result_match = 0
    result_mismatch = 0
    turn_count_match = 0
    turn_count_mismatch = 0

    for code in sorted(common_codes):
        py = py_data[code]
        js = js_data[code]

        # Compare game result
        if py['result'] == js['result']:
            result_match += 1
        else:
            result_mismatch += 1

        # Compare turn count
        py_turns = len(py['turns'])
        js_turns = len(js['turns'])
        if py_turns == js_turns:
            turn_count_match += 1
        else:
            turn_count_mismatch += 1

        # Compare per-turn data (up to the shorter of the two)
        min_turns = min(py_turns, js_turns)
        for i in range(min_turns):
            py_turn = py['turns'][i]
            js_turn = js['turns'][i]
            player_turn = py_turn['player_turn']
            tier = classify_turn(player_turn)
            stats[tier]['total'] += 1

            # Buy comparison
            buy_ok, buy_diff = compare_buys(
                py_turn.get('buys', []),
                js_turn.get('buys', [])
            )
            if buy_ok:
                stats[tier]['buy_match'] += 1
            else:
                stats[tier]['buy_mismatch'] += 1
                if len(divergences['buy']) < MAX_DIVERGENCES:
                    divergences['buy'].append({
                        'code': code, 'turn': i, 'player_turn': player_turn,
                        'detail': buy_diff
                    })

            # Unit count comparison
            unit_ok, unit_diff = compare_units(
                py_turn.get('units_owned', {}),
                js_turn.get('units_owned', {})
            )
            if unit_ok:
                stats[tier]['unit_match'] += 1
            else:
                stats[tier]['unit_mismatch'] += 1
                if len(divergences['unit']) < MAX_DIVERGENCES:
                    divergences['unit'].append({
                        'code': code, 'turn': i, 'player_turn': player_turn,
                        'detail': unit_diff
                    })

            # Resource comparison
            res_ok, res_diff = compare_resources(
                py_turn.get('resources', {}),
                js_turn.get('resources', {})
            )
            if res_ok:
                stats[tier]['resource_match'] += 1
            else:
                stats[tier]['resource_mismatch'] += 1
                if len(divergences['resource']) < MAX_DIVERGENCES:
                    divergences['resource'].append({
                        'code': code, 'turn': i, 'player_turn': player_turn,
                        'detail': res_diff
                    })

    return {
        'replays_compared': len(common_codes),
        'result_match': result_match,
        'result_mismatch': result_mismatch,
        'turn_count_match': turn_count_match,
        'turn_count_mismatch': turn_count_mismatch,
        'per_tier': stats,
        'divergences': divergences,
    }


def print_report(report: dict):
    """Print a formatted cross-validation report."""
    print("\n" + "=" * 70)
    print("CROSS-VALIDATION REPORT: Python Parser vs JS Engine")
    print("=" * 70)

    print(f"\nReplays compared: {report['replays_compared']}")
    print(f"Game result match: {report['result_match']}/{report['replays_compared']}"
          f" ({100*report['result_match']/max(report['replays_compared'],1):.1f}%)")
    print(f"Turn count match:  {report['turn_count_match']}/{report['replays_compared']}"
          f" ({100*report['turn_count_match']/max(report['replays_compared'],1):.1f}%)")

    print("\n--- Per-Turn Comparison by Tier ---\n")
    print(f"{'Tier':<8} {'Turns':<8} {'Buys':<20} {'Units':<20} {'Resources':<20}")
    print("-" * 76)

    for tier in ["1-5", "6-10", "11+"]:
        s = report['per_tier'][tier]
        total = s['total']
        if total == 0:
            continue

        buy_pct = 100 * s['buy_match'] / total
        unit_pct = 100 * s['unit_match'] / total
        res_pct = 100 * s['resource_match'] / total

        print(f"{tier:<8} {total:<8} "
              f"{s['buy_match']}/{total} ({buy_pct:.1f}%)   "
              f"{s['unit_match']}/{total} ({unit_pct:.1f}%)   "
              f"{s['resource_match']}/{total} ({res_pct:.1f}%)")

    # Print divergence examples
    for category in ['buy', 'unit', 'resource']:
        divs = report['divergences'][category]
        if divs:
            print(f"\n--- First {len(divs)} {category} divergences ---\n")
            for d in divs[:10]:
                print(f"  {d['code']} turn {d['turn']} (player_turn {d['player_turn']}): {d['detail']}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Cross-validate Python replay parser against JS engine"
    )
    parser.add_argument("--db", help="Path to replays.db (for random sampling)")
    parser.add_argument("--replays-dir", required=True,
                        help="Path to replays archive directory")
    parser.add_argument("--sample", type=int, default=500,
                        help="Number of replays to sample (default: 500)")
    parser.add_argument("--codes-file", help="File of specific codes to validate")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for sampling (default: 42)")
    parser.add_argument("--output", help="Save report as JSON to this file")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    # Get codes to validate
    if args.codes_file:
        codes = Path(args.codes_file).read_text().strip().splitlines()
        codes = [c.strip() for c in codes if c.strip()]
    elif args.db:
        codes = get_sample_codes(args.db, args.sample, args.seed)
    else:
        # Fall back to listing replay files in the directory
        replays_dir = Path(args.replays_dir)
        all_files = list(replays_dir.glob('*.json.gz'))
        random.seed(args.seed)
        if len(all_files) > args.sample:
            all_files = random.sample(all_files, args.sample)
        codes = [f.stem.replace('.json', '') for f in all_files]

    logger.info(f"Selected {len(codes)} replays for cross-validation")

    # Run both parsers
    js_data = run_js_extraction(codes, args.replays_dir)
    py_data = run_python_parsing(codes, args.replays_dir)

    # Compare
    report = run_comparison(py_data, js_data)

    # Output
    print_report(report)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report saved to {args.output}")


if __name__ == '__main__':
    main()
