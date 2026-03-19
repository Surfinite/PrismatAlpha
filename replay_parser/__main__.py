"""CLI entry point: python -m replay_parser"""
import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from replay_parser.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Prismata replay parser - extract game data into SQLite"
    )
    parser.add_argument("--db", help="Path to replays.db")
    parser.add_argument("--replays-dir", help="Path to replays archive directory")
    parser.add_argument("--codes", help="Comma-separated replay codes to parse")
    parser.add_argument("--codes-file", help="File containing replay codes (one per line)")
    parser.add_argument("--replay", help="Parse single replay file, output to stdout")
    parser.add_argument("--json", action="store_true", help="Output as JSON (with --replay)")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing replays from S3")
    parser.add_argument("--force", action="store_true", help="Re-parse already-parsed replays")
    parser.add_argument("--verify", action="store_true",
                        help="Run verification on existing parsed data (no extraction)")
    parser.add_argument("--cross-validate", action="store_true",
                        help="Run cross-validation: JS vs Python parser comparison")
    parser.add_argument("--sample", type=int, default=500,
                        help="Sample size for cross-validation (default: 500)")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    # Single replay mode (no DB) — uses JS extraction
    if args.replay:
        js_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'js_engine', 'bulk_extract.js')
        result = subprocess.run(['node', js_script, args.replay],
                              capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(result.stdout)
        else:
            data = json.loads(result.stdout)
            _print_replay_summary_from_json(data)
        return

    # Verify mode — check self-consistency of existing parsed data
    if args.verify:
        if not args.db:
            parser.error("--db is required for --verify mode")
        from replay_parser.cross_validate import run_self_consistency_check
        report = run_self_consistency_check(args.db)
        print(json.dumps(report, indent=2))
        return

    # Cross-validate mode — compare JS vs Python parser
    if args.cross_validate:
        if not args.db or not args.replays_dir:
            parser.error("--db and --replays-dir are required for --cross-validate")
        from replay_parser.cross_validate import (
            get_sample_codes, run_js_extraction as cv_run_js,
            run_python_parsing, run_comparison, print_report
        )
        codes = get_sample_codes(args.db, args.sample)
        js_data = cv_run_js(codes, args.replays_dir)
        py_data = run_python_parsing(codes, args.replays_dir)
        report = run_comparison(py_data, js_data)
        print_report(report)
        return

    # Pipeline mode
    if not args.db:
        parser.error("--db is required for pipeline mode")
    if not args.replays_dir:
        parser.error("--replays-dir is required for pipeline mode")

    codes = None
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    elif args.codes_file:
        codes = Path(args.codes_file).read_text().strip().splitlines()

    stats = run_pipeline(
        db_path=args.db,
        replays_dir=args.replays_dir,
        codes=codes,
        force=args.force,
        fetch=args.fetch,
    )
    print(json.dumps(stats, indent=2))


def _print_replay_summary_from_json(data):
    """Print a human-readable summary from JS extraction JSON."""
    print(f"Replay: {data['code']}")
    print(f"Result: P{data['result']} wins")
    print(f"Turns: {data['totalTurns']}")
    if data.get('error'):
        print(f"Error: {data['error']}")
        return
    print()
    for t in data['turns'][:10]:
        buys_str = ", ".join(t['buys']) if t['buys'] else "(none)"
        print(f"  Turn {t['global_turn']} (P{t['player']} t{t['player_turn']}): {buys_str}")
    if len(data['turns']) > 10:
        print(f"  ... ({len(data['turns']) - 10} more turns)")


if __name__ == "__main__":
    main()
