"""Opening book explorer — data layer.

Pure Python module (no Streamlit dependency). Bulk-fetches turn data
from replays.db and builds an in-memory prefix tree for opening book
analysis. Caching is handled by the Streamlit app, not this module.
"""
import copy
import json
import math
import os
import sqlite3
import time

from replay_parser.ob_analysis import BASE_SET_UNITS
from replay_parser.ob_format import _abbrev_buy

__all__ = [
    "get_connection", "get_dominion_units", "get_max_rating",
    "fetch_turn_data", "build_tree", "prune_tree", "count_nodes",
    "wilson_ci", "build_sql_for_debug",
]

DB_PATH = os.getenv("PRISMATA_DB", "c:/libraries/prismata-replay-parser/replays.db")


def get_connection():
    """Open read-only SQLite connection via URI mode."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = 1")
    return conn


def get_dominion_units(conn):
    """Get sorted list of Dominion unit names from DB (excludes base set)."""
    base_list = sorted(BASE_SET_UNITS)
    placeholders = ",".join("?" for _ in base_list)
    rows = conn.execute(
        f"SELECT DISTINCT unit_name FROM replay_units "
        f"WHERE unit_name NOT IN ({placeholders}) ORDER BY unit_name",
        base_list,
    ).fetchall()
    return [r[0] for r in rows]


def get_max_rating(conn):
    """Get the maximum player rating in OB-eligible games."""
    row = conn.execute(
        "SELECT MAX(max_rating) FROM replays "
        "WHERE format = 200 AND balance_passed = 1"
    ).fetchone()
    return int(row[0]) if row[0] else 2400


# ---------------------------------------------------------------------------
# Task 2: Bulk Fetch
# ---------------------------------------------------------------------------

def fetch_turn_data(
    conn,
    primary_unit: str,
    player: int,
    min_rating: float,
    max_rating: float,
    include_units: tuple,
    exclude_units: tuple,
    max_depth: int,
) -> list:
    """Layer 1: Fetch all matching turn_buys rows in a single query.

    Returns list of tuples: (code, player_turn, buy_hash, buy_sequence_json, result)
    This is a pure function — caching is handled by the Streamlit app.
    """
    all_include = (primary_unit,) + include_units
    include_clauses = []
    include_params = []
    for unit in all_include:
        include_clauses.append(
            "AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = ?)"
        )
        include_params.append(unit)

    exclude_clauses = []
    exclude_params = []
    for unit in exclude_units:
        exclude_clauses.append(
            "AND tb.code NOT IN (SELECT code FROM replay_units WHERE unit_name = ?)"
        )
        exclude_params.append(unit)

    sql = f"""
        SELECT tb.code, tb.player_turn, tb.buy_hash, tb.buy_sequence, r.result
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        WHERE tb.player = ?
          AND tb.player_turn <= ?
          AND r.format = 200
          AND r.balance_passed = 1
          AND r.p1_rating >= ? AND r.p1_rating <= ?
          AND r.p2_rating >= ? AND r.p2_rating <= ?
          AND r.result IN (0, 1, 2)
          {' '.join(include_clauses)}
          {' '.join(exclude_clauses)}
        ORDER BY tb.code, tb.player_turn
    """
    params = [
        player, max_depth, min_rating, max_rating, min_rating, max_rating,
        *include_params, *exclude_params,
    ]
    return conn.execute(sql, params).fetchall()


def build_sql_for_debug(
    primary_unit: str,
    player: int,
    min_rating: float,
    max_rating: float,
    include_units: tuple,
    exclude_units: tuple,
    max_depth: int,
) -> str:
    """Return the SQL query string with parameters substituted, for debug display."""
    all_include = (primary_unit,) + include_units
    include_clauses = "\n  ".join(
        f"AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = '{u}')"
        for u in all_include
    )
    exclude_clauses = "\n  ".join(
        f"AND tb.code NOT IN (SELECT code FROM replay_units WHERE unit_name = '{u}')"
        for u in exclude_units
    )

    return f"""SELECT tb.code, tb.player_turn, tb.buy_hash, tb.buy_sequence, r.result
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
WHERE tb.player = {player}
  AND tb.player_turn <= {max_depth}
  AND r.format = 200
  AND r.balance_passed = 1
  AND r.p1_rating >= {min_rating} AND r.p1_rating <= {max_rating}
  AND r.p2_rating >= {min_rating} AND r.p2_rating <= {max_rating}
  AND r.result IN (0, 1, 2)
  {include_clauses}
  {exclude_clauses}
ORDER BY tb.code, tb.player_turn"""
