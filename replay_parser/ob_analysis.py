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
