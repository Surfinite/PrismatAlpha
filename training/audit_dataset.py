"""
Phase 0d: Dataset Composition Audit
====================================
Queries replays.db to compute all statistics required by the training plan
before extraction begins.

Required measurements (from training plan V3-R2, Phase 0d):
  - PvP vs PvAI ratio
  - Rating distribution (1500-1799, 1800-1999, 2000+)
  - Game length distribution (wall-clock; ply count requires replay sampling)
  - Card set distribution (base-only vs random-set)
  - Draw rate
  - First-player win rate
  - Per-unit frequency (flag units in <500 games)
  - Resignation vs timeout (if distinguishable)
  - Unique player count

Usage:
  python training/audit_dataset.py [--db PATH] [--output PATH]
"""

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path


# Training-eligible filter matching the plan:
# both players >= 1500, rated (rating_change != 0), balance-passed
ELIGIBLE_WHERE = """
    balance_passed = 1
    AND p1_rating IS NOT NULL AND p2_rating IS NOT NULL
    AND p1_rating >= 1500 AND p2_rating >= 1500
    AND p1_rating > 1 AND p2_rating > 1
    AND (p1_rating_change != 0 OR p2_rating_change != 0)
    AND result IS NOT NULL
    AND deck IS NOT NULL
"""

# Base set unit names (display names as stored in DB deck JSON)
BASE_SET = {
    "Engineer", "Drone", "Conduit", "Blastforge", "Animus",
    "Forcefield", "Gauss Cannon", "Wall", "Steelsplitter", "Tarsier", "Rhino"
}


def connect_db(db_path):
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def total_counts(conn):
    """Total replays, balance-passed, training-eligible."""
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM replays").fetchone()[0]
    bal_passed = cur.execute("SELECT COUNT(*) FROM replays WHERE balance_passed = 1").fetchone()[0]
    eligible = cur.execute(f"SELECT COUNT(*) FROM replays WHERE {ELIGIBLE_WHERE}").fetchone()[0]

    # PvP check: format=200 is ranked PvP, format=201 is bot
    pvp = cur.execute(f"""
        SELECT COUNT(*) FROM replays
        WHERE {ELIGIBLE_WHERE} AND format = 200
    """).fetchone()[0]
    bot = cur.execute(f"""
        SELECT COUNT(*) FROM replays
        WHERE {ELIGIBLE_WHERE} AND format = 201
    """).fetchone()[0]
    # Also check for Master Bot by rating ~1.0
    masterbot = cur.execute(f"""
        SELECT COUNT(*) FROM replays
        WHERE balance_passed = 1 AND result IS NOT NULL
        AND (p1_rating <= 1.5 OR p2_rating <= 1.5)
    """).fetchone()[0]

    return {
        "total_replays": total,
        "balance_passed": bal_passed,
        "training_eligible": eligible,
        "pvp_ranked": pvp,
        "bot_matches_format201": bot,
        "masterbot_rating_matches": masterbot,
    }


def rating_distribution(conn):
    """Rating distribution in buckets."""
    cur = conn.cursor()
    rows = cur.execute(f"""
        SELECT
            CASE
                WHEN min_rating >= 2000 THEN '2000+'
                WHEN min_rating >= 1800 THEN '1800-1999'
                WHEN min_rating >= 1600 THEN '1600-1799'
                WHEN min_rating >= 1500 THEN '1500-1599'
                ELSE 'below_1500'
            END AS bucket,
            COUNT(*) AS count,
            ROUND(AVG(avg_rating), 1) AS mean_avg_rating
        FROM replays
        WHERE {ELIGIBLE_WHERE}
        GROUP BY bucket
        ORDER BY bucket DESC
    """).fetchall()

    result = {}
    total = 0
    for row in rows:
        result[row["bucket"]] = {"count": row["count"], "mean_avg_rating": row["mean_avg_rating"]}
        total += row["count"]

    # Add percentages
    for bucket in result:
        result[bucket]["pct"] = round(100 * result[bucket]["count"] / total, 1) if total > 0 else 0

    # Overall stats
    stats = cur.execute(f"""
        SELECT
            AVG(p1_rating + p2_rating) AS mean_combined,
            AVG(avg_rating) AS mean_avg,
            MIN(min_rating) AS min_rating,
            MAX(max_rating) AS max_rating
        FROM replays
        WHERE {ELIGIBLE_WHERE}
    """).fetchone()

    result["_summary"] = {
        "mean_combined_rating": round(stats["mean_combined"], 1) if stats["mean_combined"] else None,
        "mean_per_player": round(stats["mean_avg"], 1) if stats["mean_avg"] else None,
        "min_rating_in_set": stats["min_rating"],
        "max_rating_in_set": stats["max_rating"],
    }

    return result


def win_rate_analysis(conn):
    """First-player win rate and draw rate."""
    cur = conn.cursor()

    stats = cur.execute(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN result = 0 THEN 1 ELSE 0 END) AS p1_wins,
            SUM(CASE WHEN result = 1 THEN 1 ELSE 0 END) AS p2_wins,
            SUM(CASE WHEN result = 2 THEN 1 ELSE 0 END) AS draws,
            SUM(CASE WHEN result NOT IN (0, 1, 2) THEN 1 ELSE 0 END) AS other
        FROM replays
        WHERE {ELIGIBLE_WHERE}
    """).fetchone()

    total = stats["total"]
    p1_wins = stats["p1_wins"]
    p2_wins = stats["p2_wins"]
    draws = stats["draws"]

    # In the DB, result=0 means P1 wins, result=1 means P2 wins
    # But in Prismata, P1 goes first and P2 goes second with extra Drone
    # P1 = first mover, P2 = second mover (has extra Drone)
    p1_wr = p1_wins / total if total > 0 else 0
    p2_wr = p2_wins / total if total > 0 else 0
    draw_rate = draws / total if total > 0 else 0

    # Seat bias for Elo prior (if P2 advantage > 2pp)
    seat_bias_elo = None
    if abs(p1_wr - 0.5) > 0.02 and total > 1000:
        # Convert win rate to Elo advantage
        if p2_wr > 0 and p2_wr < 1:
            seat_bias_elo = round(-400 * math.log10(p1_wr / p2_wr), 1)

    return {
        "total_games": total,
        "p1_wins": p1_wins,
        "p2_wins": p2_wins,
        "draws": draws,
        "other": stats["other"],
        "p1_win_rate": round(p1_wr, 4),
        "p2_win_rate": round(p2_wr, 4),
        "draw_rate": round(draw_rate, 4),
        "draw_pct": round(100 * draw_rate, 2),
        "seat_bias_elo": seat_bias_elo,
        "_note": "P1=first mover, P2=second mover (extra Drone). result=0 means P1 wins."
    }


def game_length_distribution(conn):
    """Wall-clock game duration distribution.
    Ply count requires replay sampling (not available from DB alone).
    """
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT
            (end_time - start_time) AS duration_seconds
        FROM replays
        WHERE {ELIGIBLE_WHERE}
            AND end_time IS NOT NULL AND start_time IS NOT NULL
            AND end_time > start_time
    """).fetchall()

    if not rows:
        return {"_note": "No duration data available"}

    durations = [r["duration_seconds"] for r in rows]
    durations.sort()

    n = len(durations)
    result = {
        "games_with_duration": n,
        "mean_seconds": round(sum(durations) / n, 1),
        "median_seconds": durations[n // 2],
        "p25_seconds": durations[n // 4],
        "p75_seconds": durations[3 * n // 4],
        "p95_seconds": durations[int(n * 0.95)],
        "min_seconds": durations[0],
        "max_seconds": durations[-1],
    }

    # Bucket by minute
    minute_buckets = Counter()
    for d in durations:
        minute_buckets[d // 60] += 1

    result["by_minute"] = {f"{m}min": c for m, c in sorted(minute_buckets.items()) if m <= 30}
    result["over_30min"] = sum(c for m, c in minute_buckets.items() if m > 30)

    return result


def card_set_analysis(conn):
    """Card set composition: base-only vs random-set, deck size distribution."""
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT deck, deck_size FROM replays
        WHERE {ELIGIBLE_WHERE}
    """).fetchall()

    base_only = 0
    random_set = 0
    deck_sizes = Counter()

    for row in rows:
        deck = json.loads(row["deck"]) if row["deck"] else []
        deck_sizes[len(deck)] += 1

        # Base-only = all units in deck are base set units
        non_base = [u for u in deck if u not in BASE_SET]
        if len(non_base) == 0:
            base_only += 1
        else:
            random_set += 1

    total = base_only + random_set
    return {
        "base_only_games": base_only,
        "random_set_games": random_set,
        "base_only_pct": round(100 * base_only / total, 2) if total > 0 else 0,
        "deck_size_distribution": dict(sorted(deck_sizes.items())),
        "_note": "Base-only games should be excluded from training per plan."
    }


def unit_frequency(conn):
    """Per-unit frequency across training-eligible games.
    Flag units in <500 games as low-data units.
    """
    cur = conn.cursor()

    # Use replay_units junction table if populated, else parse deck JSON
    has_junction = cur.execute(
        "SELECT COUNT(*) FROM replay_units"
    ).fetchone()[0] > 0

    if has_junction:
        rows = cur.execute(f"""
            SELECT ru.unit_name, COUNT(*) AS frequency
            FROM replay_units ru
            JOIN replays r ON ru.code = r.code
            WHERE {ELIGIBLE_WHERE}
            GROUP BY ru.unit_name
            ORDER BY frequency DESC
        """).fetchall()
        freq = {row["unit_name"]: row["frequency"] for row in rows}
    else:
        # Fallback: parse deck JSON
        rows = cur.execute(f"""
            SELECT deck FROM replays WHERE {ELIGIBLE_WHERE}
        """).fetchall()
        freq = Counter()
        for row in rows:
            deck = json.loads(row["deck"]) if row["deck"] else []
            for unit in deck:
                freq[unit] += 1

    # Separate base set (always present) from random set
    base_freq = {u: f for u, f in freq.items() if u in BASE_SET}
    random_freq = {u: f for u, f in freq.items() if u not in BASE_SET}

    # Sort random by frequency
    random_sorted = dict(sorted(random_freq.items(), key=lambda x: x[1], reverse=True))

    # Flag low-data units (<500 games)
    low_data = {u: f for u, f in random_sorted.items() if f < 500}

    return {
        "base_set_units": base_freq,
        "random_set_top20": dict(list(random_sorted.items())[:20]),
        "random_set_bottom20": dict(list(sorted(random_freq.items(), key=lambda x: x[1]))[:20]),
        "low_data_units_under_500": low_data,
        "low_data_count": len(low_data),
        "total_unique_units": len(freq),
    }


def unique_players(conn):
    """Count unique players contributing to the training set."""
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT COUNT(DISTINCT name) AS unique_players FROM (
            SELECT p1_name AS name FROM replays WHERE {ELIGIBLE_WHERE}
            UNION
            SELECT p2_name AS name FROM replays WHERE {ELIGIBLE_WHERE}
        )
    """).fetchone()

    # Top contributors
    top = cur.execute(f"""
        SELECT name, COUNT(*) AS games FROM (
            SELECT p1_name AS name FROM replays WHERE {ELIGIBLE_WHERE}
            UNION ALL
            SELECT p2_name AS name FROM replays WHERE {ELIGIBLE_WHERE}
        )
        GROUP BY name
        ORDER BY games DESC
        LIMIT 20
    """).fetchall()

    return {
        "unique_players": rows["unique_players"],
        "top_20_contributors": {r["name"]: r["games"] for r in top}
    }


def temporal_distribution(conn):
    """Date distribution for temporal train/val/test split planning."""
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT
            strftime('%Y-%m', datetime(start_time, 'unixepoch')) AS month,
            COUNT(*) AS count
        FROM replays
        WHERE {ELIGIBLE_WHERE} AND start_time IS NOT NULL
        GROUP BY month
        ORDER BY month
    """).fetchall()

    monthly = {r["month"]: r["count"] for r in rows}

    # Date range
    date_range = cur.execute(f"""
        SELECT
            MIN(start_time) AS earliest,
            MAX(start_time) AS latest
        FROM replays
        WHERE {ELIGIBLE_WHERE} AND start_time IS NOT NULL
    """).fetchone()

    return {
        "monthly_counts": monthly,
        "earliest_unix": date_range["earliest"],
        "latest_unix": date_range["latest"],
        "_note": "Temporal split: oldest 80% = train, next 10% = val, newest 10% = test"
    }


def export_code_list(conn, output_dir):
    """Export the canonical training-eligible code list (Phase 0a deliverable)."""
    cur = conn.cursor()
    rows = cur.execute(f"""
        SELECT code FROM replays
        WHERE {ELIGIBLE_WHERE}
        ORDER BY start_time ASC
    """).fetchall()

    codes = [r["code"] for r in rows]

    output_path = os.path.join(output_dir, "balance_validated_1500plus.json")
    with open(output_path, "w") as f:
        json.dump({"count": len(codes), "codes": codes}, f, indent=2)

    print(f"  Exported {len(codes)} codes to {output_path}")
    return len(codes)


def main():
    parser = argparse.ArgumentParser(description="Phase 0d: Dataset Composition Audit")
    parser.add_argument("--db", default="c:/libraries/prismata-replay-parser/replays.db",
                        help="Path to replays.db")
    parser.add_argument("--output", default="c:/libraries/PrismataAI/training/data/audit_results.json",
                        help="Output path for audit results JSON")
    parser.add_argument("--export-codes", action="store_true",
                        help="Export canonical code list (balance_validated_1500plus.json)")
    args = parser.parse_args()

    conn = connect_db(args.db)
    results = {}

    print("=" * 60)
    print("Phase 0d: Dataset Composition Audit")
    print("=" * 60)

    print("\n[1/8] Total counts and PvP ratio...")
    results["counts"] = total_counts(conn)
    c = results["counts"]
    print(f"  Total replays: {c['total_replays']:,}")
    print(f"  Balance passed: {c['balance_passed']:,}")
    print(f"  Training eligible: {c['training_eligible']:,}")
    print(f"  PvP ranked: {c['pvp_ranked']:,}")
    print(f"  MasterBot matches (rating<=1.5): {c['masterbot_rating_matches']:,}")

    print("\n[2/8] Rating distribution...")
    results["ratings"] = rating_distribution(conn)
    for bucket, data in results["ratings"].items():
        if bucket.startswith("_"):
            continue
        print(f"  {bucket}: {data['count']:,} ({data['pct']}%)")
    s = results["ratings"]["_summary"]
    print(f"  Mean combined rating: {s['mean_combined_rating']}")

    print("\n[3/8] Win rate and draw analysis...")
    results["win_rates"] = win_rate_analysis(conn)
    w = results["win_rates"]
    print(f"  P1 (first mover) win rate: {w['p1_win_rate']:.1%}")
    print(f"  P2 (second mover) win rate: {w['p2_win_rate']:.1%}")
    print(f"  Draw rate: {w['draw_pct']}%")
    if w["seat_bias_elo"]:
        print(f"  Seat bias (Elo equivalent): {w['seat_bias_elo']}")

    print("\n[4/8] Game length distribution (wall-clock)...")
    results["game_length"] = game_length_distribution(conn)
    gl = results["game_length"]
    if "mean_seconds" in gl:
        print(f"  Games with duration data: {gl['games_with_duration']:,}")
        print(f"  Mean: {gl['mean_seconds']}s ({gl['mean_seconds']/60:.1f}min)")
        print(f"  Median: {gl['median_seconds']}s ({gl['median_seconds']/60:.1f}min)")
        print(f"  P75: {gl['p75_seconds']}s ({gl['p75_seconds']/60:.1f}min)")

    print("\n[5/8] Card set composition...")
    results["card_sets"] = card_set_analysis(conn)
    cs = results["card_sets"]
    print(f"  Base-only games: {cs['base_only_games']:,} ({cs['base_only_pct']}%)")
    print(f"  Random-set games: {cs['random_set_games']:,}")

    print("\n[6/8] Unit frequency...")
    results["unit_frequency"] = unit_frequency(conn)
    uf = results["unit_frequency"]
    print(f"  Total unique units: {uf['total_unique_units']}")
    print(f"  Low-data units (<500 games): {uf['low_data_count']}")
    if uf["low_data_units_under_500"]:
        for u, f in sorted(uf["low_data_units_under_500"].items(), key=lambda x: x[1]):
            print(f"    {u}: {f}")

    print("\n[7/8] Unique players...")
    results["players"] = unique_players(conn)
    print(f"  Unique players: {results['players']['unique_players']}")

    print("\n[8/8] Temporal distribution...")
    results["temporal"] = temporal_distribution(conn)
    months = results["temporal"]["monthly_counts"]
    if months:
        print(f"  Date range: {min(months.keys())} to {max(months.keys())}")
        print(f"  Months with data: {len(months)}")

    # Export code list if requested
    if args.export_codes:
        print("\n[+] Exporting canonical code list...")
        export_code_list(conn, os.path.dirname(args.output))

    # Save results
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {args.output}")

    # Plan-relevant warnings
    print("\n" + "=" * 60)
    print("Plan-Relevant Checks:")
    print("=" * 60)

    if w["draw_pct"] > 2.0:
        print(f"  WARNING: Draw rate {w['draw_pct']}% exceeds 2% threshold.")
        print("  Consider label=0.5 for draws rather than forcing win/loss.")
    else:
        print(f"  OK: Draw rate {w['draw_pct']}% is below 2% threshold.")

    p1_deviation = abs(w["p1_win_rate"] - 0.5)
    if p1_deviation > 0.02:
        print(f"  NOTE: First-player win rate deviates by {p1_deviation:.1%} from 50%.")
        print(f"  Seat bias Elo correction recommended: {w['seat_bias_elo']}")
    else:
        print(f"  OK: First-player win rate within 2pp of 50%.")

    if cs["base_only_games"] > 0:
        print(f"  NOTE: {cs['base_only_games']} base-only games will be excluded from training.")

    if uf["low_data_count"] > 0:
        print(f"  NOTE: {uf['low_data_count']} units appear in <500 games (low data).")
        print("  Evaluation quality for sets with these units will be poor.")

    conn.close()
    print("\nAudit complete.")


if __name__ == "__main__":
    main()
