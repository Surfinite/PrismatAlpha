"""Opening book analysis — consensus computation from expert replays.

Queries the replay database (replays, replay_units, turn_buys) to find
dominant buy sequences for each unit on turn 1.
"""
import json
import sqlite3


BASE_SET_UNITS = frozenset([
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Wall", "Steelsplitter", "Forcefield", "Gauss Cannon",
    "Tarsier", "Rhino",
])

# Expected units owned at the start of turn 1 (before any buys)
STARTING_STATES = {
    0: [("Drone", 6), ("Engineer", 2)],   # P1 turn 1
    1: [("Drone", 7), ("Engineer", 2)],   # P2 turn 1
}

# Expected units owned at the start of turn 2 after a DD opening
DD_FOLLOWUP_STATES = {
    0: [("Drone", 8), ("Engineer", 2)],   # P1 turn 2 after DD
    1: [("Drone", 9), ("Engineer", 2)],   # P2 turn 2 after DD
}


def get_dominion_units(
    conn: sqlite3.Connection,
    min_rating: float = 1500.0,
    min_samples: int = 20,
) -> list[dict]:
    """Return non-base-set units that appear in enough balanced, rated games.

    Each returned dict has keys: unit_name, game_count.
    """
    # Build parameterized NOT IN clause for base set exclusion
    base_list = sorted(BASE_SET_UNITS)
    placeholders = ",".join("?" for _ in base_list)

    sql = f"""
        SELECT ru.unit_name, COUNT(DISTINCT ru.code) AS game_count
        FROM replay_units ru
        JOIN replays r ON ru.code = r.code
        WHERE ru.unit_name NOT IN ({placeholders})
          AND r.p1_rating >= ?
          AND r.p2_rating >= ?
          AND r.balance_passed = 1
        GROUP BY ru.unit_name
        HAVING game_count >= ?
        ORDER BY game_count DESC
    """
    params = base_list + [min_rating, min_rating, min_samples]
    rows = conn.execute(sql, params).fetchall()
    return [{"unit_name": row[0], "game_count": row[1]} for row in rows]


def analyze_unit_turn1(
    conn: sqlite3.Connection,
    unit: str,
    player: int,
    min_rating: float = 1500.0,
) -> dict:
    """Analyze turn 1 buy consensus for a specific unit and player.

    Returns a dict with:
        top_buy       — most frequent buy_hash (sorted, comma-separated)
        frequency     — fraction of games using top_buy
        win_rate      — wins / (games - draws) for the top buy hash
        sample_size   — number of games with top_buy
        total_games   — total games analysed for this unit+player
        runner_up     — second-most-frequent buy dict, or None
        top_5         — list of up to 5 buy dicts (hash, sequence, freq, win_rate)
    """
    sql = """
        SELECT tb.buy_hash,
               tb.buy_sequence,
               COUNT(*) AS freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) AS draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        WHERE tb.player = ?
          AND tb.player_turn = 1
          AND r.p1_rating >= ?
          AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND r.result IN (0, 1, 2)
          AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = ?)
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """
    rows = conn.execute(sql, (player, min_rating, min_rating, unit)).fetchall()

    if not rows:
        return {
            "top_buy": None,
            "frequency": 0.0,
            "win_rate": 0.0,
            "sample_size": 0,
            "total_games": 0,
            "runner_up": None,
            "top_5": [],
            "status": "insufficient",
        }

    total_games = sum(r[2] for r in rows)

    def _make_entry(row: tuple) -> dict:
        buy_hash, buy_sequence, freq, wins, draws = row
        decisive = freq - draws
        return {
            "buy_hash": buy_hash,
            "buy_sequence": json.loads(buy_sequence),
            "frequency": freq / total_games if total_games else 0.0,
            "win_rate": wins / decisive if decisive > 0 else 0.0,
            "sample_size": freq,
        }

    top_5 = [_make_entry(r) for r in rows[:5]]
    top = top_5[0]
    runner_up = top_5[1] if len(top_5) > 1 else None

    return {
        "top_buy": top["buy_hash"],
        "frequency": top["frequency"],
        "win_rate": top["win_rate"],
        "sample_size": top["sample_size"],
        "total_games": total_games,
        "runner_up": runner_up,
        "top_5": top_5,
        "status": "ok",
    }


def analyze_unit_turn2_dd(
    conn: sqlite3.Connection,
    unit: str,
    player: int,
    min_rating: float = 1500.0,
) -> dict:
    """Analyze turn 2 buy consensus for players who opened DD (Drone, Drone).

    Filters by the deterministic post-DD state using turn_state:
      P1 (player=0): 8 Drones + 2 Engineers
      P2 (player=1): 9 Drones + 2 Engineers

    Returns the same structure as analyze_unit_turn1 plus a ``state`` field
    describing the starting state (e.g. "8D+2E").
    """
    expected_drones, expected_engrs = DD_FOLLOWUP_STATES[player]
    state_label = f"{expected_drones[1]}D+{expected_engrs[1]}E"

    sql = """
        SELECT tb.buy_hash,
               tb.buy_sequence,
               COUNT(*) AS freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) AS draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        JOIN turn_state ts ON tb.code = ts.code AND tb.global_turn = ts.global_turn
        WHERE tb.player = ?
          AND tb.player_turn = 2
          AND r.p1_rating >= ?
          AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND r.result IN (0, 1, 2)
          AND json_extract(ts.units_owned, '$.Drone') = ?
          AND json_extract(ts.units_owned, '$.Engineer') = ?
          AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = ?)
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """
    rows = conn.execute(
        sql,
        (player, min_rating, min_rating,
         expected_drones[1], expected_engrs[1], unit),
    ).fetchall()

    if not rows:
        return {
            "top_buy": None,
            "frequency": 0.0,
            "win_rate": 0.0,
            "sample_size": 0,
            "total_games": 0,
            "runner_up": None,
            "top_5": [],
            "state": state_label,
            "status": "insufficient",
        }

    total_games = sum(r[2] for r in rows)

    def _make_entry(row: tuple) -> dict:
        buy_hash, buy_sequence, freq, wins, draws = row
        decisive = freq - draws
        return {
            "buy_hash": buy_hash,
            "buy_sequence": json.loads(buy_sequence),
            "frequency": freq / total_games if total_games else 0.0,
            "win_rate": wins / decisive if decisive > 0 else 0.0,
            "sample_size": freq,
        }

    top_5 = [_make_entry(r) for r in rows[:5]]
    top = top_5[0]
    runner_up = top_5[1] if len(top_5) > 1 else None

    return {
        "top_buy": top["buy_hash"],
        "frequency": top["frequency"],
        "win_rate": top["win_rate"],
        "sample_size": top["sample_size"],
        "total_games": total_games,
        "runner_up": runner_up,
        "top_5": top_5,
        "state": state_label,
        "status": "ok",
    }


def find_co_occurring_units(
    conn: sqlite3.Connection,
    unit: str,
    min_rating: float = 1500.0,
    limit: int = 10,
) -> list[dict]:
    """Find top Dominion units that co-occur with *unit* in the same game.

    Excludes base-set units.  Returns a list of dicts with keys:
        unit_name, co_count
    """
    base_list = sorted(BASE_SET_UNITS)
    placeholders = ",".join("?" for _ in base_list)

    sql = f"""
        SELECT ru2.unit_name, COUNT(*) AS co_count
        FROM replay_units ru1
        JOIN replay_units ru2 ON ru1.code = ru2.code
                              AND ru1.unit_name != ru2.unit_name
        JOIN replays r ON ru1.code = r.code
        WHERE ru1.unit_name = ?
          AND r.p1_rating >= ?
          AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND ru2.unit_name NOT IN ({placeholders})
        GROUP BY ru2.unit_name
        ORDER BY co_count DESC
        LIMIT ?
    """
    params = [unit, min_rating, min_rating] + base_list + [limit]
    rows = conn.execute(sql, params).fetchall()
    return [{"unit_name": row[0], "co_count": row[1]} for row in rows]


def analyze_pair_turn1(
    conn: sqlite3.Connection,
    unit1: str,
    unit2: str,
    player: int,
    min_rating: float = 1500.0,
) -> dict:
    """Analyze turn 1 buy consensus when BOTH unit1 and unit2 are in the set.

    Same return structure as analyze_unit_turn1.
    """
    sql = """
        SELECT tb.buy_hash,
               tb.buy_sequence,
               COUNT(*) AS freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) AS draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        WHERE tb.player = ?
          AND tb.player_turn = 1
          AND r.p1_rating >= ?
          AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND r.result IN (0, 1, 2)
          AND tb.code IN (
              SELECT ru1.code
              FROM replay_units ru1
              JOIN replay_units ru2 ON ru1.code = ru2.code
              WHERE ru1.unit_name = ? AND ru2.unit_name = ?
          )
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """
    rows = conn.execute(
        sql, (player, min_rating, min_rating, unit1, unit2)
    ).fetchall()

    if not rows:
        return {
            "top_buy": None,
            "frequency": 0.0,
            "win_rate": 0.0,
            "sample_size": 0,
            "total_games": 0,
            "runner_up": None,
            "top_5": [],
            "status": "insufficient",
        }

    total_games = sum(r[2] for r in rows)

    def _make_entry(row: tuple) -> dict:
        buy_hash, buy_sequence, freq, wins, draws = row
        decisive = freq - draws
        return {
            "buy_hash": buy_hash,
            "buy_sequence": json.loads(buy_sequence),
            "frequency": freq / total_games if total_games else 0.0,
            "win_rate": wins / decisive if decisive > 0 else 0.0,
            "sample_size": freq,
        }

    top_5 = [_make_entry(r) for r in rows[:5]]
    top = top_5[0]
    runner_up = top_5[1] if len(top_5) > 1 else None

    return {
        "top_buy": top["buy_hash"],
        "frequency": top["frequency"],
        "win_rate": top["win_rate"],
        "sample_size": top["sample_size"],
        "total_games": total_games,
        "runner_up": runner_up,
        "top_5": top_5,
        "status": "ok",
    }


def run_full_analysis(
    conn: sqlite3.Connection,
    min_rating: float = 1500.0,
    min_samples: int = 20,
    strong_threshold: float = 0.70,
    pair_threshold: float = 0.50,
    unit_filter: list[str] | None = None,
) -> dict:
    """Run the complete opening-book consensus analysis pipeline.

    Steps:
      1. Get Dominion units via get_dominion_units().
      2. Run analyze_unit_turn1() for each unit, both players.
      3. Classify consensus; flag contested units.
      4. Run analyze_unit_turn2_dd() for each unit, both players.
      5. For contested units: find co-occurring units, run pair analysis,
         keep resolved pairs.
      6. Return full analysis dict.

    Parameters:
        unit_filter — optional list of unit names to restrict analysis to.
    """
    # 1. Dominion units
    dom_units = get_dominion_units(conn, min_rating=min_rating,
                                   min_samples=min_samples)
    unit_names = [u["unit_name"] for u in dom_units]
    if unit_filter is not None:
        unit_names = [u for u in unit_names if u in unit_filter]

    # 2 & 3. Turn 1 analysis
    turn1_analysis: dict[str, dict] = {}
    contested_units: list[str] = []

    for uname in unit_names:
        unit_result: dict = {}
        for player in (0, 1):
            result = analyze_unit_turn1(conn, uname, player,
                                        min_rating=min_rating)
            consensus = classify_consensus(result["frequency"],
                                           strong_threshold, pair_threshold)
            result["consensus"] = consensus
            unit_result[f"p{player}"] = result
        turn1_analysis[uname] = unit_result

        # Flag as contested if either side is contested
        for side in ("p0", "p1"):
            if unit_result[side]["consensus"] == "contested":
                contested_units.append(uname)
                break

    # 4. Turn 2 DD follow-up analysis
    turn2_analysis: dict[str, dict] = {}
    for uname in unit_names:
        unit_result = {}
        for player in (0, 1):
            result = analyze_unit_turn2_dd(conn, uname, player,
                                           min_rating=min_rating)
            if result["total_games"] >= min_samples:
                consensus = classify_consensus(result["frequency"],
                                               strong_threshold,
                                               pair_threshold)
                result["consensus"] = consensus
                unit_result[f"p{player}"] = result
        if unit_result:
            turn2_analysis[uname] = unit_result

    # 5. Pair analysis for contested units
    pair_analysis: dict[str, list[dict]] = {}
    for uname in contested_units:
        co_units = find_co_occurring_units(conn, uname,
                                           min_rating=min_rating, limit=10)
        resolved_pairs: list[dict] = []
        for co in co_units:
            partner = co["unit_name"]
            for player in (0, 1):
                pr = analyze_pair_turn1(conn, uname, partner, player,
                                        min_rating=min_rating)
                if pr["total_games"] < min_samples:
                    continue
                consensus = classify_consensus(pr["frequency"],
                                               strong_threshold,
                                               pair_threshold)
                if consensus != "contested":
                    resolved_pairs.append({
                        "partner": partner,
                        "player": player,
                        "consensus": consensus,
                        "top_buy": pr["top_buy"],
                        "frequency": pr["frequency"],
                        "win_rate": pr["win_rate"],
                        "sample_size": pr["sample_size"],
                        "total_games": pr["total_games"],
                    })
        if resolved_pairs:
            pair_analysis[uname] = resolved_pairs

    return {
        "parameters": {
            "min_rating": min_rating,
            "min_samples": min_samples,
            "strong_threshold": strong_threshold,
            "pair_threshold": pair_threshold,
        },
        "turn1_analysis": turn1_analysis,
        "turn2_analysis": turn2_analysis,
        "pair_analysis": pair_analysis,
    }


def classify_consensus(
    frequency: float,
    strong_threshold: float = 0.70,
    pair_threshold: float = 0.50,
) -> str:
    """Classify buy consensus strength.

    Returns:
        "strong"    — frequency >= strong_threshold
        "moderate"  — frequency >= pair_threshold
        "contested" — frequency < pair_threshold
    """
    if frequency >= strong_threshold:
        return "strong"
    if frequency >= pair_threshold:
        return "moderate"
    return "contested"


def main():
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Opening book consensus analysis from expert replays."
    )
    parser.add_argument("--db", required=True, help="Path to replays.db")
    parser.add_argument("--min-rating", type=float, default=2000,
                        help="Minimum rating for both players (default: 2000)")
    parser.add_argument("--min-samples", type=int, default=30,
                        help="Minimum games per unit (default: 30)")
    parser.add_argument("--strong-threshold", type=float, default=0.60,
                        help="Consensus >= this is 'strong' (default: 0.60)")
    parser.add_argument("--pair-threshold", type=float, default=0.40,
                        help="Consensus < this triggers pair analysis (default: 0.40)")
    parser.add_argument("--units", default=None,
                        help="Comma-separated unit names to analyze (default: all)")
    parser.add_argument("--report", default=None,
                        help="Save report JSON to this path")
    parser.add_argument("--config", default=None,
                        help="Save config entries JSON to this path")
    parser.add_argument("--config-txt", default="bin/asset/config/config.txt",
                        help="Path to config.txt for validation (default: bin/asset/config/config.txt)")

    args = parser.parse_args()

    unit_filter = None
    if args.units:
        unit_filter = [u.strip() for u in args.units.split(",")]

    conn = sqlite3.connect(args.db)

    # Run analysis
    analysis = run_full_analysis(
        conn,
        min_rating=args.min_rating,
        min_samples=args.min_samples,
        strong_threshold=args.strong_threshold,
        pair_threshold=args.pair_threshold,
        unit_filter=unit_filter,
    )

    # Format outputs
    from replay_parser.ob_format import (
        generate_ob_entries,
        validate_against_existing,
        load_existing_ob,
        build_summary,
        build_report,
    )

    entries = generate_ob_entries(analysis)

    # Validation (optional -- skip if config.txt not found)
    validation = {}
    try:
        existing = load_existing_ob(args.config_txt)
        validation = validate_against_existing(analysis, existing)
    except FileNotFoundError:
        pass

    # Print summary to stdout
    summary = build_summary(analysis, entries, validation)
    print(summary)

    # Save files if requested
    if args.report:
        report = build_report(analysis, entries, validation)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {args.report}")

    if args.config:
        with open(args.config, "w") as f:
            json.dump(entries, f, indent=2)
        print(f"Config entries saved to {args.config}")

    conn.close()


if __name__ == "__main__":
    main()
