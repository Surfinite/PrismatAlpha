"""CLI entry point: python -m replay_parser"""
import argparse
import json
import logging
import sys
from pathlib import Path

from replay_parser.pipeline import run_pipeline
from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate


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
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    # Single replay mode (no DB)
    if args.replay:
        raw = load_replay(args.replay)
        replay = decode(raw)
        simulate(replay)
        if args.json:
            _print_replay_json(replay)
        else:
            _print_replay_summary(replay)
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


def _print_replay_json(replay):
    """Print replay data as JSON to stdout."""
    output = {
        "code": replay.code,
        "result": replay.result,
        "player_names": replay.player_names,
        "total_turns": replay.total_global_turns,
        "turns": [
            {
                "global_turn": t.global_turn,
                "player": t.player,
                "player_turn": t.player_turn,
                "buys": t.buys,
                "abilities_used": t.abilities_used,
                "units_owned": t.units_owned,
                "resources_at_start": {
                    "gold": t.resources_at_start.gold,
                    "green": t.resources_at_start.green,
                    "blue": t.resources_at_start.blue,
                    "red": t.resources_at_start.red,
                    "energy": t.resources_at_start.energy,
                    "attack": t.resources_at_start.attack,
                },
            }
            for t in replay.turns
        ]
    }
    print(json.dumps(output, indent=2))


def _print_replay_summary(replay):
    """Print a human-readable summary of the replay."""
    print(f"Replay: {replay.code}")
    print(f"Players: {replay.player_names[0]} vs {replay.player_names[1]}")
    print(f"Result: P{replay.result} wins")
    print(f"Turns: {replay.total_global_turns}")
    print()
    for t in replay.turns[:10]:  # First 10 turns
        player_name = replay.player_names[t.player]
        buys_str = ", ".join(t.buys) if t.buys else "(none)"
        print(f"  Turn {t.global_turn} ({player_name}): {buys_str}")
    if len(replay.turns) > 10:
        print(f"  ... ({len(replay.turns) - 10} more turns)")


if __name__ == "__main__":
    main()
