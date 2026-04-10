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


# ---------------------------------------------------------------------------
# Task 3: Prefix Tree Construction
# ---------------------------------------------------------------------------

def wilson_ci(wins, n, z=1.96):
    """Wilson score 95% confidence interval for a proportion.
    Returns (lower, upper). If n=0, returns (0.0, 0.0).
    """
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, centre - spread), min(1.0, centre + spread)


def build_tree(rows: list, player: int, max_depth: int) -> dict:
    """Layer 2: Build unpruned prefix tree from bulk-fetched rows.

    Args:
        rows: Tuples of (code, player_turn, buy_hash, buy_seq_json, result)
        player: 0 or 1 — needed for win rate computation
        max_depth: Maximum turn depth to build

    Returns the root node dict.
    """
    games: dict = {}
    result_by_code: dict = {}
    for code, player_turn, buy_hash, buy_seq_json, result in rows:
        games.setdefault(code, []).append((player_turn, buy_hash, buy_seq_json))
        result_by_code[code] = result

    total_games = len(games)
    if total_games == 0:
        return _empty_root(player)

    for code in games:
        games[code].sort(key=lambda t: t[0])

    total_wins = sum(1 for r in result_by_code.values() if r == player)
    total_draws = sum(1 for r in result_by_code.values() if r == 2)
    total_decisive = total_games - total_draws
    root_wr = total_wins / total_decisive if total_decisive > 0 else 0.5

    root_label = "6D+2E" if player == 0 else "7D+2E"

    root = _make_node(
        path_id="root",
        buy_list=[],
        label=root_label,
        count=total_games,
        wins=total_wins,
        draws=total_draws,
        parent_count=total_games,
        root_total=total_games,
        root_wr=root_wr,
        codes=list(games.keys()),
    )

    _build_level(root, games, result_by_code, player, 0, root_wr, total_games, max_depth)

    return root


def _build_level(
    parent: dict,
    games: dict,
    result_by_code: dict,
    player: int,
    turn_index: int,
    root_wr: float,
    root_total: int,
    max_depth: int,
):
    """Recursively add children for turn at turn_index in each game's sorted turn list."""
    if turn_index >= max_depth:
        return

    groups: dict = {}
    buy_seq_map: dict = {}

    for code, turns in games.items():
        if turn_index < len(turns):
            _, buy_hash, buy_seq_json = turns[turn_index]
            groups.setdefault(buy_hash, []).append(code)
            if buy_hash not in buy_seq_map:
                buy_seq_map[buy_hash] = buy_seq_json

    parent_count = parent["count"]

    for buy_hash, codes in sorted(groups.items(), key=lambda x: -len(x[1])):
        count = len(codes)
        buy_list = json.loads(buy_seq_map[buy_hash])
        wins = sum(1 for c in codes if result_by_code[c] == player)
        draws = sum(1 for c in codes if result_by_code[c] == 2)

        path_id = f"{parent['path_id']}/{buy_hash}"

        node = _make_node(
            path_id=path_id,
            buy_list=buy_list,
            label=_abbrev_buy(sorted(buy_list)),
            count=count,
            wins=wins,
            draws=draws,
            parent_count=parent_count,
            root_total=root_total,
            root_wr=root_wr,
            codes=codes,
        )
        parent["children"].append(node)

        sub_games = {c: games[c] for c in codes}
        _build_level(node, sub_games, result_by_code, player,
                     turn_index + 1, root_wr, root_total, max_depth)


def _make_node(
    path_id: str,
    buy_list: list,
    label: str,
    count: int,
    wins: int,
    draws: int,
    parent_count: int,
    root_total: int,
    root_wr: float,
    codes: list,
) -> dict:
    """Create a single tree node with computed stats."""
    decisive = count - draws
    wr = wins / decisive if decisive > 0 else 0.5
    ci_low, ci_high = wilson_ci(wins, decisive)

    return {
        "path_id": path_id,
        "buy": buy_list,
        "buy_abbrev": label,
        "count": count,
        "count_decisive": decisive,
        "count_draws": draws,
        "frequency_parent": count / parent_count if parent_count > 0 else 0.0,
        "frequency_root": count / root_total if root_total > 0 else 0.0,
        "win_rate": wr,
        "win_rate_delta": wr - root_wr,
        "win_rate_ci_low": ci_low,
        "win_rate_ci_high": ci_high,
        "sample_codes": codes[:10],
        "children": [],
        "other_count": 0,
        "other_frequency": 0.0,
    }


def _empty_root(player: int) -> dict:
    """Return an empty root node for zero-game results."""
    label = "6D+2E" if player == 0 else "7D+2E"
    return {
        "path_id": "root",
        "buy": [],
        "buy_abbrev": label,
        "count": 0,
        "count_decisive": 0,
        "count_draws": 0,
        "frequency_parent": 1.0,
        "frequency_root": 1.0,
        "win_rate": 0.0,
        "win_rate_delta": 0.0,
        "win_rate_ci_low": 0.0,
        "win_rate_ci_high": 0.0,
        "sample_codes": [],
        "children": [],
        "other_count": 0,
        "other_frequency": 0.0,
    }


def count_nodes(node: dict) -> int:
    """Count total nodes in a tree."""
    total = 1
    for child in node.get("children", []):
        total += count_nodes(child)
    return total


# ---------------------------------------------------------------------------
# Task 4: Pruning
# ---------------------------------------------------------------------------

def prune_tree(
    tree: dict,
    min_freq_per_turn: list,
    max_branches: int = 8,
) -> dict:
    """Layer 3: Prune tree by per-turn frequency thresholds and branch cap.

    Returns a new tree (does not mutate the input). Pruned branches are
    aggregated into an 'Other' node at each level.
    """
    pruned = copy.deepcopy(tree)
    _prune_level(pruned, min_freq_per_turn, max_branches, 0)
    return pruned


def _prune_level(node: dict, thresholds: list, max_branches: int, depth: int):
    """Recursively prune children at each level."""
    if not node["children"]:
        return

    threshold = thresholds[depth] if depth < len(thresholds) else thresholds[-1]

    node["children"].sort(key=lambda c: -c["count"])

    kept = []
    other_count = 0
    for child in node["children"]:
        if child["frequency_parent"] >= threshold and len(kept) < max_branches:
            kept.append(child)
        else:
            other_count += child["count"]

    other_count += node["other_count"]
    parent_count = node["count"]

    node["children"] = kept
    node["other_count"] = other_count
    node["other_frequency"] = other_count / parent_count if parent_count > 0 else 0.0

    for child in kept:
        _prune_level(child, thresholds, max_branches, depth + 1)
