"""Opening book explorer — data layer.

Pure Python module (no Streamlit dependency). Bulk-fetches turn data
from replays.db and builds an in-memory prefix tree for opening book
analysis. Caching is handled by the Streamlit app, not this module.
"""
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
