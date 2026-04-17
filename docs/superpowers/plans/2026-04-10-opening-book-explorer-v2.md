# Opening Book Explorer Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit-based interactive visualization tool for exploring opening book consensus data from 26k+ expert Prismata replays, with decision tree, sunburst, icicle, and path table views.

**Architecture:** Three Python files — pure data layer (bulk SQL + in-memory prefix tree, no Streamlit dependency), visualization layer (Plotly charts + table), and Streamlit app (controls, caching wrappers, layout). Queries `replays.db` read-only via SQLite URI mode. Three cacheable layers: DB rows → unpruned tree (both cached in `st.session_state`) → pruned viz data (recomputed from cached tree when thresholds change). `st.form` for data filters, instant threshold/chart switching outside form.

<!-- CHANGED: Data layer decoupled from Streamlit, caching via st.session_state, SQLite read-only URI — Reviewers 2, 3 -->

**Tech Stack:** Python 3.13, Streamlit, Plotly, Pillow, pandas, SQLite3

**Spec:** `docs/superpowers/specs/2026-04-10-opening-book-explorer-design-v2.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `tools/requirements-explorer.txt` | Pip dependencies |
| `tools/ob_explorer_data.py` | Pure Python: DB queries, prefix tree construction, pruning, Wilson CI. No Streamlit imports. |
| `tools/ob_explorer_viz.py` | Plotly scatter tree, sunburst, icicle, path table renderers |
| `tools/ob_explorer.py` | Streamlit app: caching wrappers, sidebar form, presentation controls, layout, debug |
| `tools/tests/test_ob_explorer_data.py` | Data layer tests |

<!-- CHANGED: Data module has no Streamlit dep. Test file added. — Reviewers 2, 3 -->

### Existing Files Referenced (read-only)

| File | Usage |
|---|---|
| `c:/libraries/prismata-replay-parser/replays.db` | Game data (turn_buys, replays, replay_units) |
| `replay_parser/ob_format.py` | Import `_abbrev_buy()`, `UNIT_ABBREVS` |
| `replay_parser/ob_analysis.py` | Import `BASE_SET_UNITS` |
| `bin/asset/images/cards/` | Unit card art PNGs |

---

## Task 1: Requirements + Skeleton

**Files:**
- Create: `tools/requirements-explorer.txt`
- Create: `tools/ob_explorer_data.py`
- Create: `tools/ob_explorer_viz.py`
- Create: `tools/ob_explorer.py`

- [ ] **Step 1: Create requirements file**

<!-- CHANGED: Added pandas explicitly — Reviewer 3 -->

```
streamlit
plotly
Pillow
pandas
```

Write to `tools/requirements-explorer.txt`.

- [ ] **Step 2: Install dependencies**

Run: `pip install -r tools/requirements-explorer.txt`
Expected: successful install of streamlit, plotly, Pillow, pandas.

- [ ] **Step 3: Create data module skeleton**

<!-- CHANGED: No Streamlit import. Pure Python. SQLite read-only URI. — Reviewer 3 -->

```python
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
```

Write to `tools/ob_explorer_data.py`.

- [ ] **Step 4: Create viz module skeleton**

```python
"""Opening book explorer — visualization layer.

Plotly chart builders (scatter tree, sunburst, icicle) and path table.
All functions take a pruned tree dict and return Plotly figures or
pandas DataFrames.
"""
import pandas as pd
import plotly.graph_objects as go

__all__ = [
    "wr_delta_color", "render_tree", "render_sunburst",
    "render_icicle", "build_path_table",
]


def wr_delta_color(delta):
    """Map WR delta to RGB color. Red (negative) -> grey (zero) -> green (positive)."""
    clamped = max(-0.15, min(0.15, delta))
    t = (clamped + 0.15) / 0.30  # 0..1
    r = int(220 - 170 * t)
    g = int(50 + 170 * t)
    b = 80
    return f"rgb({r},{g},{b})"
```

Write to `tools/ob_explorer_viz.py`.

- [ ] **Step 5: Create app skeleton**

```python
"""Opening Book Explorer — Streamlit app."""
import streamlit as st

st.set_page_config(page_title="OB Explorer", layout="wide")
st.title("Opening Book Explorer")
st.write("Loading...")
```

Write to `tools/ob_explorer.py`.

- [ ] **Step 6: Verify Streamlit launches**

Run: `cd c:/libraries/PrismataAI && streamlit run tools/ob_explorer.py --server.headless true`

Expected: server starts, prints URL. Kill with Ctrl+C.

- [ ] **Step 7: Commit**

```bash
git add tools/requirements-explorer.txt tools/ob_explorer_data.py tools/ob_explorer_viz.py tools/ob_explorer.py
git commit -m "feat(tools): opening book explorer skeleton and dependencies"
```

---

## Task 2: Data Layer — Bulk Fetch (Layer 1)

**Files:**
- Modify: `tools/ob_explorer_data.py`

- [ ] **Step 1: Add the bulk fetch function**

Append to `tools/ob_explorer_data.py`:

<!-- CHANGED: No @st.cache_data here. Pure function. Timing measured by caller. — Reviewer 3 -->

```python
def fetch_turn_data(
    conn,
    primary_unit: str,
    player: int,
    min_rating: float,
    max_rating: float,
    include_units: tuple[str, ...],
    exclude_units: tuple[str, ...],
    max_depth: int,
) -> list[tuple]:
    """Layer 1: Fetch all matching turn_buys rows in a single query.

    Returns list of tuples: (code, player_turn, buy_hash, buy_sequence_json, result)

    This is a pure function — caching is handled by the Streamlit app.
    """
    # Build dynamic include/exclude subqueries
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
```

- [ ] **Step 2: Add SQL debug string builder**

Append to `tools/ob_explorer_data.py`:

```python
def build_sql_for_debug(
    primary_unit: str,
    player: int,
    min_rating: float,
    max_rating: float,
    include_units: tuple[str, ...],
    exclude_units: tuple[str, ...],
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
```

- [ ] **Step 3: Verify the query works**

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import get_connection, fetch_turn_data
conn = get_connection()
import time; t0 = time.perf_counter()
rows = fetch_turn_data(conn, 'Wild Drone', 0, 2000.0, 2400.0, (), (), 3)
ms = (time.perf_counter() - t0) * 1000
conn.close()
print(f'{len(rows)} rows in {ms:.0f}ms')
print('First row:', rows[0] if rows else 'empty')
"
```

Expected: ~5000-9000 rows, <500ms.

- [ ] **Step 4: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer Layer 1 — bulk SQL fetch"
```

---

## Task 3: Data Layer — Prefix Tree Construction (Layer 2)

**Files:**
- Modify: `tools/ob_explorer_data.py`

- [ ] **Step 1: Add Wilson CI helper**

Append to `tools/ob_explorer_data.py`:

```python
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
```

- [ ] **Step 2: Add tree construction functions**

<!-- CHANGED: Removed abandoned draft code. Single clean implementation only. — Reviewer 2 -->

Append to `tools/ob_explorer_data.py`:

```python
def build_tree(rows: list[tuple], player: int, max_depth: int) -> dict:
    """Layer 2: Build unpruned prefix tree from bulk-fetched rows.

    Args:
        rows: Tuples of (code, player_turn, buy_hash, buy_seq_json, result)
        player: 0 or 1 — needed for win rate computation
        max_depth: Maximum turn depth to build

    Returns the root node dict.
    """
    # Group rows by code
    games: dict[str, list[tuple]] = {}
    result_by_code: dict[str, int] = {}
    for code, player_turn, buy_hash, buy_seq_json, result in rows:
        games.setdefault(code, []).append((player_turn, buy_hash, buy_seq_json))
        result_by_code[code] = result

    total_games = len(games)
    if total_games == 0:
        return _empty_root(player)

    # Sort each game's turns by player_turn
    for code in games:
        games[code].sort(key=lambda t: t[0])

    # Root-level stats
    total_wins = sum(1 for r in result_by_code.values() if r == player)
    total_draws = sum(1 for r in result_by_code.values() if r == 2)
    total_decisive = total_games - total_draws
    root_wr = total_wins / total_decisive if total_decisive > 0 else 0.5

    # Root label matches player starting state
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
    games: dict[str, list[tuple]],
    result_by_code: dict[str, int],
    player: int,
    turn_index: int,
    root_wr: float,
    root_total: int,
    max_depth: int,
):
    """Recursively add children for turn at turn_index in each game's sorted turn list."""
    if turn_index >= max_depth:
        return

    # Group codes by their buy_hash at this turn_index
    groups: dict[str, list[str]] = {}
    buy_seq_map: dict[str, str] = {}

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

        # Recurse into next turn with subset of games
        sub_games = {c: games[c] for c in codes}
        _build_level(sub_games, sub_games, result_by_code, player,
                     turn_index + 1, root_wr, root_total, max_depth)
```

Wait — there's a bug in that recursive call. The first arg should be `node`, not `sub_games`. Let me fix:

```python
        _build_level(node, sub_games, result_by_code, player,
                     turn_index + 1, root_wr, root_total, max_depth)
```

<!-- CHANGED: buy label uses _abbrev_buy(sorted(buy_list)) for canonical ordering. Root label is "6D+2E"/"7D+2E" everywhere. max_depth guard added. — Reviewers 2, 3 -->

- [ ] **Step 3: Add helper functions**

Append to `tools/ob_explorer_data.py`:

```python
def _make_node(
    path_id: str,
    buy_list: list[str],
    label: str,
    count: int,
    wins: int,
    draws: int,
    parent_count: int,
    root_total: int,
    root_wr: float,
    codes: list[str],
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
```

- [ ] **Step 4: Verify tree construction**

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import get_connection, fetch_turn_data, build_tree
conn = get_connection()
rows = fetch_turn_data(conn, 'Wild Drone', 0, 2000.0, 2400.0, (), (), 3)
conn.close()
tree = build_tree(rows, 0, 3)
print(f'Root: {tree[\"count\"]} games, WR={tree[\"win_rate\"]:.3f}, label={tree[\"buy_abbrev\"]}')
for c in tree['children'][:3]:
    print(f'  {c[\"buy_abbrev\"]}: {c[\"count\"]} ({c[\"frequency_parent\"]*100:.1f}%) WR={c[\"win_rate\"]:.3f} delta={c[\"win_rate_delta\"]:+.3f}')
    for cc in c['children'][:2]:
        print(f'    {cc[\"buy_abbrev\"]}: {cc[\"count\"]} ({cc[\"frequency_parent\"]*100:.1f}%)')
"
```

Expected: Root ~1700 games with label "6D+2E", DD ~75%, E+Wil+Wil ~20%, with children at turn 2.

- [ ] **Step 5: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer Layer 2 — prefix tree construction"
```

---

## Task 4: Data Layer — Pruning (Layer 3)

**Files:**
- Modify: `tools/ob_explorer_data.py`

- [ ] **Step 1: Add pruning function**

Append to `tools/ob_explorer_data.py`:

```python
import copy


def prune_tree(
    tree: dict,
    min_freq_per_turn: list[float],
    max_branches: int = 8,
) -> dict:
    """Layer 3: Prune tree by per-turn frequency thresholds and branch cap.

    Returns a new tree (does not mutate the input). Pruned branches are
    aggregated into an 'Other' node at each level.
    """
    pruned = copy.deepcopy(tree)
    _prune_level(pruned, min_freq_per_turn, max_branches, 0)
    return pruned


def _prune_level(node: dict, thresholds: list[float], max_branches: int, depth: int):
    """Recursively prune children at each level."""
    if not node["children"]:
        return

    threshold = thresholds[depth] if depth < len(thresholds) else thresholds[-1]

    # Sort children by count descending
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
```

- [ ] **Step 2: Verify pruning**

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import get_connection, fetch_turn_data, build_tree, prune_tree
conn = get_connection()
rows = fetch_turn_data(conn, 'Wild Drone', 0, 2000.0, 2400.0, (), (), 3)
conn.close()
tree = build_tree(rows, 0, 3)
pruned = prune_tree(tree, [0.05, 0.05, 0.10], max_branches=8)
total_freq = sum(c['frequency_parent'] for c in pruned['children']) + pruned['other_frequency']
print(f'Branches: {len(pruned[\"children\"])}, Other: {pruned[\"other_count\"]} ({pruned[\"other_frequency\"]*100:.1f}%)')
print(f'Total freq check: {total_freq:.4f} (should be ~1.0)')
for c in pruned['children']:
    print(f'  {c[\"buy_abbrev\"]}: {c[\"count\"]} — {len(c[\"children\"])} sub-branches, other={c[\"other_count\"]}')
"
```

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer Layer 3 — tree pruning with Other node"
```

---

## Task 5: Data Layer Tests

**Files:**
- Create: `tools/tests/__init__.py`
- Create: `tools/tests/test_ob_explorer_data.py`

<!-- CHANGED: Added test task — Reviewers 2, 3 -->

- [ ] **Step 1: Create test file**

```python
"""Tests for ob_explorer_data — tree construction, pruning, Wilson CI."""
import sys
sys.path.insert(0, ".")

from tools.ob_explorer_data import (
    build_tree,
    count_nodes,
    prune_tree,
    wilson_ci,
)


def test_wilson_ci_zero():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_perfect():
    lo, hi = wilson_ci(100, 100)
    assert lo > 0.95
    assert hi == 1.0


def test_wilson_ci_half():
    lo, hi = wilson_ci(50, 100)
    assert 0.39 < lo < 0.41
    assert 0.59 < hi < 0.61


def test_build_tree_empty():
    tree = build_tree([], 0, 3)
    assert tree["count"] == 0
    assert tree["buy_abbrev"] == "6D+2E"
    assert tree["children"] == []


def test_build_tree_single_game():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("game1", 2, "Drone,Drone,Engineer", '["Drone","Drone","Engineer"]', 0),
    ]
    tree = build_tree(rows, 0, 3)
    assert tree["count"] == 1
    assert tree["win_rate"] == 1.0  # player 0 won (result=0)
    assert len(tree["children"]) == 1
    assert tree["children"][0]["buy_abbrev"] == "D+D"
    assert tree["children"][0]["count"] == 1
    assert len(tree["children"][0]["children"]) == 1
    assert tree["children"][0]["children"][0]["buy_abbrev"] == "D+D+E"


def test_build_tree_p2_win_rate():
    """P2 wins when result=1."""
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 1),  # P2 wins
        ("game2", 1, "Drone,Drone", '["Drone","Drone"]', 0),  # P1 wins
    ]
    tree = build_tree(rows, 1, 1)  # analyzing as P2
    assert tree["count"] == 2
    assert tree["win_rate"] == 0.5  # 1 win out of 2
    assert tree["children"][0]["win_rate"] == 0.5


def test_build_tree_draws_excluded_from_wr():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),  # P1 wins
        ("game2", 1, "Drone,Drone", '["Drone","Drone"]', 2),  # draw
    ]
    tree = build_tree(rows, 0, 1)
    assert tree["count"] == 2
    assert tree["count_decisive"] == 1
    assert tree["count_draws"] == 1
    assert tree["win_rate"] == 1.0  # 1 win / 1 decisive


def test_build_tree_multiset_buys_preserved():
    """buy_hash 'Drone,Drone' should NOT collapse to single 'Drone'."""
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
    ]
    tree = build_tree(rows, 0, 1)
    child = tree["children"][0]
    assert child["buy"] == ["Drone", "Drone"]
    assert "D+D" in child["buy_abbrev"]  # not just "D"


def test_prune_frequency():
    rows = [
        ("g1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g2", 1, "Drone,Drone", '["Drone","Drone"]', 1),
        ("g3", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g4", 1, "Drone,Drone", '["Drone","Drone"]', 1),
        ("g5", 1, "Drone,Engineer", '["Drone","Engineer"]', 0),  # 20% = 1/5
    ]
    tree = build_tree(rows, 0, 1)
    # Threshold 25% should prune the 20% branch
    pruned = prune_tree(tree, [0.25])
    assert len(pruned["children"]) == 1  # only DD survives
    assert pruned["other_count"] == 1
    # Total should still add up
    total = sum(c["count"] for c in pruned["children"]) + pruned["other_count"]
    assert total == 5


def test_prune_max_branches():
    # Create 5 branches, cap at 3
    rows = []
    buys = ["Drone,Drone", "Drone,Engineer", "Conduit,Drone",
            "Blastforge,Drone", "Animus"]
    seqs = ['["Drone","Drone"]', '["Drone","Engineer"]', '["Conduit","Drone"]',
            '["Blastforge","Drone"]', '["Animus"]']
    for i, (bh, bs) in enumerate(zip(buys, seqs)):
        for j in range(5 - i):  # DD=5, DE=4, CD=3, BD=2, A=1
            rows.append((f"g{i}_{j}", 1, bh, bs, 0))

    tree = build_tree(rows, 0, 1)
    pruned = prune_tree(tree, [0.01], max_branches=3)
    assert len(pruned["children"]) == 3
    assert pruned["other_count"] == 3  # BD(2) + A(1) pruned


def test_count_nodes():
    tree = build_tree([], 0, 1)
    assert count_nodes(tree) == 1  # just root

    rows = [
        ("g1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g1", 2, "Drone,Drone,Engineer", '["Drone","Drone","Engineer"]', 0),
    ]
    tree = build_tree(rows, 0, 2)
    assert count_nodes(tree) == 3  # root + DD + DDE


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
```

Write to `tools/tests/test_ob_explorer_data.py`. Also create empty `tools/tests/__init__.py`.

- [ ] **Step 2: Run tests**

Run: `cd c:/libraries/PrismataAI && python -m pytest tools/tests/test_ob_explorer_data.py -v`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tools/tests/
git commit -m "test(tools): OB explorer data layer tests"
```

---

## Task 6: Visualization — Scatter Tree

**Files:**
- Modify: `tools/ob_explorer_viz.py`

- [ ] **Step 1: Add tree layout + rendering**

Append to `tools/ob_explorer_viz.py`:

```python
def render_tree(tree: dict, title: str = "") -> go.Figure:
    """Render a pruned tree as an interactive Plotly scatter plot."""
    if tree["count"] == 0:
        return _empty_figure("No games match filters")

    positions = {}
    _layout_tree(tree, positions, x=0.0, y=0.0, x_span=1.0)

    node_x, node_y, node_text, node_hover, node_color, node_size = [], [], [], [], [], []
    edge_x, edge_y = [], []

    def _collect(node):
        px, py = positions[node["path_id"]]
        node_x.append(px)
        node_y.append(-py)

        node_text.append(node["buy_abbrev"])

        confidence = " [LOW SAMPLE]" if node["count_decisive"] < 30 else ""
        hover = (
            f"<b>{node['buy_abbrev']}</b><br>"
            f"Buy: {', '.join(node['buy']) if node['buy'] else 'Start'}<br>"
            f"Games: {node['count']} ({node['frequency_parent']:.1%} of parent, "
            f"{node['frequency_root']:.1%} of all)<br>"
            f"WR: {node['win_rate']:.1%} ({node['win_rate_delta']:+.1%} vs baseline)<br>"
            f"CI: [{node['win_rate_ci_low']:.1%}, {node['win_rate_ci_high']:.1%}]<br>"
            f"Decisive: {node['count_decisive']}, Draws: {node['count_draws']}"
            f"{confidence}"
        )
        if node["other_count"] > 0:
            hover += f"<br>Other: {node['other_count']} ({node['other_frequency']:.1%})"
        node_hover.append(hover)

        node_color.append(wr_delta_color(node["win_rate_delta"]))
        import math as _math
        node_size.append(max(10, min(40, 10 + 30 * _math.sqrt(node["frequency_root"]))))

        for child in node["children"]:
            cx, cy = positions[child["path_id"]]
            edge_x.extend([px, cx, None])
            edge_y.extend([-py, -cy, None])
            _collect(child)

    _collect(tree)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="#888", width=1), hoverinfo="none",
    ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=node_size, color=node_color, line=dict(width=1, color="#333")),
        text=node_text, textposition="top center", textfont=dict(size=10),
        hovertext=node_hover, hoverinfo="text",
    ))
    fig.update_layout(
        title=title, showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=40, b=20), height=500,
    )
    return fig


def _leaf_count(node):
    """Count leaf nodes in subtree (for weighted layout)."""
    if not node["children"]:
        return 1
    return sum(_leaf_count(c) for c in node["children"])


def _layout_tree(node, positions, x, y, x_span):
    """Recursive tree layout: y-spacing per depth, x-space weighted by subtree leaf count."""
    positions[node["path_id"]] = (x, y)
    children = node["children"]
    if not children:
        return
    # Allocate x-space proportional to subtree leaf count
    leaf_counts = [_leaf_count(c) for c in children]
    total_leaves = sum(leaf_counts)
    if total_leaves == 0:
        total_leaves = len(children)
        leaf_counts = [1] * len(children)
    cursor_x = x - x_span / 2
    for child, leaves in zip(children, leaf_counts):
        child_span = x_span * leaves / total_leaves
        child_x = cursor_x + child_span / 2
        _layout_tree(child, positions, child_x, y + 1, child_span)
        cursor_x += child_span


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=16, color="#888"))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False),
                      margin=dict(l=20, r=20, t=20, b=20), height=300)
    return fig
```

- [ ] **Step 2: Commit**

```bash
git add tools/ob_explorer_viz.py
git commit -m "feat(tools): OB explorer scatter tree visualization"
```

---

## Task 7: Visualization — Sunburst + Icicle

**Files:**
- Modify: `tools/ob_explorer_viz.py`

- [ ] **Step 1: Add sunburst and icicle renderers**

Append to `tools/ob_explorer_viz.py`:

```python
def _flatten_tree_for_plotly(tree: dict) -> tuple[list, list, list, list, list, list]:
    """Flatten tree into parallel lists for Plotly hierarchical charts."""
    ids, labels, parents, values, colors, hovers = [], [], [], [], [], []

    def _walk(node, parent_id=""):
        nid = node["path_id"]
        ids.append(nid)
        labels.append(node["buy_abbrev"])
        parents.append(parent_id)
        values.append(node["count"])
        colors.append(node["win_rate_delta"])

        confidence = " [LOW]" if node["count_decisive"] < 30 else ""
        hover = (
            f"{node['buy_abbrev']}: {node['count']} games "
            f"({node['frequency_parent']:.1%})<br>"
            f"WR: {node['win_rate']:.1%} ({node['win_rate_delta']:+.1%}){confidence}"
        )
        hovers.append(hover)

        for child in node["children"]:
            _walk(child, nid)

        if node["other_count"] > 0:
            other_id = f"{nid}/__other__"
            ids.append(other_id)
            labels.append(f"Other ({node['other_count']})")
            parents.append(nid)
            values.append(node["other_count"])
            colors.append(0.0)
            hovers.append(f"Pruned: {node['other_count']} ({node['other_frequency']:.1%})")

    _walk(tree)
    return ids, labels, parents, values, colors, hovers


def render_sunburst(tree: dict, title: str = "") -> go.Figure:
    if tree["count"] == 0:
        return _empty_figure("No games match filters")
    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)
    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=[wr_delta_color(c) for c in colors]),
        hovertext=hovers, hoverinfo="text", branchvalues="total",
    ))
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=40, b=20), height=500)
    return fig


def render_icicle(tree: dict, title: str = "") -> go.Figure:
    if tree["count"] == 0:
        return _empty_figure("No games match filters")
    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)
    fig = go.Figure(go.Icicle(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=[wr_delta_color(c) for c in colors]),
        hovertext=hovers, hoverinfo="text", branchvalues="total",
    ))
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=40, b=20), height=500)
    return fig
```

- [ ] **Step 2: Commit**

```bash
git add tools/ob_explorer_viz.py
git commit -m "feat(tools): OB explorer sunburst + icicle visualization"
```

---

## Task 8: Visualization — Path Table

**Files:**
- Modify: `tools/ob_explorer_viz.py`

<!-- CHANGED: Keep columns numeric. Format for display via column_config. — Reviewer 3 -->

- [ ] **Step 1: Add path table builder**

Append to `tools/ob_explorer_viz.py`:

```python
def build_path_table(tree: dict) -> pd.DataFrame:
    """Flatten tree into a sortable path table with numeric columns."""
    rows = []

    def _walk(node, path_parts):
        current_path = path_parts + ([node["buy_abbrev"]] if node["buy"] else [])

        if node["buy"]:  # skip root
            rows.append({
                "Path": " > ".join(current_path),
                "Count": node["count"],
                "Freq (parent)": node["frequency_parent"],
                "Freq (root)": node["frequency_root"],
                "Win Rate": node["win_rate"],
                "WR Delta": node["win_rate_delta"],
                "CI Low": node["win_rate_ci_low"],
                "CI High": node["win_rate_ci_high"],
                "Draws": node["count_draws"],
                "Codes": ", ".join(node["sample_codes"][:5]),
            })

        for child in node["children"]:
            _walk(child, current_path)

        # Add "Other" row if pruned branches exist
        if node["other_count"] > 0 and node["buy"]:
            rows.append({
                "Path": " > ".join(current_path + ["(Other)"]),
                "Count": node["other_count"],
                "Freq (parent)": node["other_frequency"],
                "Freq (root)": node["other_count"] / tree["count"] if tree["count"] > 0 else 0,
                "Win Rate": None,
                "WR Delta": None,
                "CI Low": None,
                "CI High": None,
                "Draws": None,
                "Codes": "",
            })

    _walk(tree, [])

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df.sort_values("Count", ascending=False).reset_index(drop=True)


# Column config for st.dataframe display formatting
PATH_TABLE_COLUMN_CONFIG = {
    "Freq (parent)": st.column_config.NumberColumn(format="%.1%%"),
    "Freq (root)": st.column_config.NumberColumn(format="%.1%%"),
    "Win Rate": st.column_config.NumberColumn(format="%.1%%"),
    "WR Delta": st.column_config.NumberColumn(format="%+.1%%"),
    "CI Low": st.column_config.NumberColumn(format="%.1%%"),
    "CI High": st.column_config.NumberColumn(format="%.1%%"),
}
```

Wait — `st.column_config` requires importing streamlit in the viz module. That contradicts keeping viz pure. Let me put the column config in the app instead.

Remove `PATH_TABLE_COLUMN_CONFIG` from the viz module. It will be defined in the app file.

- [ ] **Step 2: Commit**

```bash
git add tools/ob_explorer_viz.py
git commit -m "feat(tools): OB explorer path table with numeric columns"
```

---

## Task 9: Streamlit App — Full Assembly

**Files:**
- Modify: `tools/ob_explorer.py`

- [ ] **Step 1: Write the complete app**

Replace contents of `tools/ob_explorer.py`:

<!-- CHANGED: Caching via st.session_state for Layer 2. Timing measured outside cached fns. Stacked layout uses st.container(). Per-panel debug. Player selector for all modes. Compare mode validation. Card art cached. Imports at top. — Reviewers 1, 2, 3 -->

```python
"""Opening Book Explorer — Streamlit app.

Interactive visualization of opening book consensus data from expert replays.
Launch: streamlit run tools/ob_explorer.py
"""
import json
import os
import time

import streamlit as st
from PIL import Image

from tools.ob_explorer_data import (
    build_sql_for_debug,
    build_tree,
    count_nodes,
    fetch_turn_data,
    get_connection,
    get_dominion_units,
    get_max_rating,
    prune_tree,
)
from tools.ob_explorer_viz import (
    build_path_table,
    render_icicle,
    render_sunburst,
    render_tree,
)

st.set_page_config(page_title="OB Explorer", layout="wide")

CARD_ART_DIR = "bin/asset/images/cards"


# --- Startup data (cached for session) ---
@st.cache_data(ttl=None)
def _startup():
    conn = get_connection()
    units = get_dominion_units(conn)
    max_r = get_max_rating(conn)
    conn.close()
    return units, max_r


@st.cache_data(ttl=None)
def _load_card_art(unit_name: str, size: int = 48):
    path = os.path.join(CARD_ART_DIR, f"{unit_name}.png")
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        img.thumbnail((size, size))
        return img
    except Exception:
        return None


dominion_units, max_rating = _startup()

st.title("Opening Book Explorer")

# --- URL params for bookmarking ---
qp = st.query_params
default_unit = qp.get("unit", "Wild Drone") if qp.get("unit") in dominion_units else "Wild Drone"
default_mode = qp.get("mode", "P1 vs P2")

# --- Sidebar: Data Filters (inside form) ---
with st.sidebar:
    st.header("Data Filters")

    with st.form("data_filters"):
        primary_unit = st.selectbox(
            "Primary Unit", dominion_units,
            index=dominion_units.index(default_unit) if default_unit in dominion_units else 0,
        )

        compare_mode = st.radio("Compare Mode", ["P1 vs P2", "Unit vs Unit", "With vs Without"])

        second_unit = None
        with_unit = None
        # Player selector for non-default modes
        compare_player = 0
        if compare_mode == "Unit vs Unit":
            second_unit = st.selectbox("Second Unit", dominion_units, index=min(1, len(dominion_units) - 1))
            compare_player = st.radio("Player", ["P1", "P2"], horizontal=True, key="uvsu_player")
            compare_player = 0 if compare_player == "P1" else 1
        elif compare_mode == "With vs Without":
            with_unit = st.selectbox("With/Without Unit", dominion_units, index=min(1, len(dominion_units) - 1))
            compare_player = st.radio("Player", ["P1", "P2"], horizontal=True, key="wvwo_player")
            compare_player = 0 if compare_player == "P1" else 1

        include_units = st.multiselect("Include Units (must be in set)", dominion_units)
        exclude_units = st.multiselect("Exclude Units (must NOT be in set)", dominion_units)

        rating_range = st.slider("Rating Range", 1500, max_rating, (2000, max_rating), step=50)
        max_depth = st.slider("Turn Depth", 1, 5, 3)
        max_branches = st.slider("Max Branches per Level", 3, 20, 8)

        st.form_submit_button("Apply")

    # Presentation controls (outside form)
    st.header("Display")
    chart_type = st.radio("Chart Type", ["Tree", "Sunburst", "Icicle", "Path Table"])

    st.subheader("Frequency Thresholds")
    defaults = [0.05, 0.05, 0.10, 0.15, 0.20]
    thresholds = []
    for i in range(max_depth):
        default = defaults[i] if i < len(defaults) else 0.20
        val = st.slider(f"Turn {i+1}", 0.01, 0.50, default, 0.01, key=f"thresh_{i}")
        thresholds.append(val)

    layout_mode = st.radio("Layout", ["Side-by-side", "Stacked"])

# --- Validation ---
overlap = set(include_units) & set(exclude_units)
if overlap:
    st.error(f"Include/exclude overlap: {', '.join(overlap)}. Remove conflicting units.")
    st.stop()

if compare_mode == "Unit vs Unit" and second_unit == primary_unit:
    st.error("Second unit must be different from primary unit.")
    st.stop()

if compare_mode == "With vs Without" and with_unit == primary_unit:
    st.error("With/Without unit must be different from primary unit.")
    st.stop()

if compare_mode == "With vs Without" and with_unit in include_units:
    st.warning(f"{with_unit} is in the Include list — the 'Without' panel will force-exclude it.")

if compare_mode == "With vs Without" and with_unit in exclude_units:
    st.warning(f"{with_unit} is in the Exclude list — the 'With' panel will force-include it.")

# --- Build panel configs ---
def make_panel(unit, player, label):
    return {"unit": unit, "player": player, "label": label}


if compare_mode == "P1 vs P2":
    panels = [
        make_panel(primary_unit, 0, f"P1 — {primary_unit}"),
        make_panel(primary_unit, 1, f"P2 — {primary_unit}"),
    ]
elif compare_mode == "Unit vs Unit":
    p_label = "P1" if compare_player == 0 else "P2"
    panels = [
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit}"),
        make_panel(second_unit, compare_player, f"{p_label} — {second_unit}"),
    ]
else:  # With vs Without
    p_label = "P1" if compare_player == 0 else "P2"
    panels = [
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit} WITH {with_unit}"),
        make_panel(primary_unit, compare_player, f"{p_label} — {primary_unit} WITHOUT {with_unit}"),
    ]


# --- Caching helpers ---
def _cache_key(panel, include_extra=(), exclude_extra=()):
    inc = tuple(sorted(set(include_units) | set(include_extra)))
    exc = tuple(sorted(set(exclude_units) | set(exclude_extra)))
    return (panel["unit"], panel["player"], rating_range[0], rating_range[1],
            inc, exc, max_depth)


def get_cached_tree(panel, include_extra=(), exclude_extra=()):
    """Get or build the unpruned tree (Layer 2), cached in session_state."""
    key = _cache_key(panel, include_extra, exclude_extra)
    state_key = f"tree_{key}"

    if state_key not in st.session_state:
        inc = tuple(sorted(set(include_units) | set(include_extra)))
        exc = tuple(sorted(set(exclude_units) | set(exclude_extra)))

        t0 = time.perf_counter()
        conn = get_connection()
        rows = fetch_turn_data(
            conn, panel["unit"], panel["player"],
            float(rating_range[0]), float(rating_range[1]),
            inc, exc, max_depth,
        )
        conn.close()
        query_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        tree = build_tree(rows, panel["player"], max_depth)
        build_ms = (time.perf_counter() - t1) * 1000

        st.session_state[state_key] = tree
        st.session_state[f"timing_{state_key}"] = {"query_ms": query_ms, "build_ms": build_ms}
    else:
        # Cache hit — no fresh timing
        if f"timing_{state_key}" not in st.session_state:
            st.session_state[f"timing_{state_key}"] = {"query_ms": 0, "build_ms": 0}

    return st.session_state[state_key], st.session_state[f"timing_{state_key}"]


# --- Path table column formatting ---
PATH_TABLE_COLUMN_CONFIG = {
    "Freq (parent)": st.column_config.NumberColumn(format="%.1%%"),
    "Freq (root)": st.column_config.NumberColumn(format="%.1%%"),
    "Win Rate": st.column_config.NumberColumn(format="%.1%%"),
    "WR Delta": st.column_config.NumberColumn(format="%+.1%%"),
    "CI Low": st.column_config.NumberColumn(format="%.1%%"),
    "CI High": st.column_config.NumberColumn(format="%.1%%"),
}


# --- Render panels ---
if layout_mode == "Side-by-side":
    cols = st.columns(2)
else:
    cols = [st.container(), st.container()]

panel_debug_info = []

for i, panel in enumerate(panels):
    with cols[i]:
        # Header with card art
        art = _load_card_art(panel["unit"])
        if art:
            hcol1, hcol2 = st.columns([1, 8])
            with hcol1:
                st.image(art)
            with hcol2:
                st.subheader(panel["label"])
        else:
            st.subheader(panel["label"])

        # Include/exclude overrides for With/Without mode
        inc_extra = ()
        exc_extra = ()
        if compare_mode == "With vs Without":
            if i == 0:
                inc_extra = (with_unit,)
            else:
                exc_extra = (with_unit,)

        with st.spinner("Loading..."):
            tree, timing = get_cached_tree(panel, inc_extra, exc_extra)

        if tree["count"] == 0:
            st.warning("No games match these filters.")
            panel_debug_info.append({"label": panel["label"], "count": 0})
            continue

        # Prune
        t_prune = time.perf_counter()
        pruned = prune_tree(tree, thresholds, max_branches)
        prune_ms = (time.perf_counter() - t_prune) * 1000

        if not pruned["children"]:
            st.info("All branches below threshold. Try lowering frequency thresholds.")
            panel_debug_info.append({"label": panel["label"], "count": tree["count"]})
            continue

        # Panel metadata
        pruned_mass = pruned["other_count"]
        total_visible = sum(c["count"] for c in pruned["children"])
        coverage = total_visible / pruned["count"] * 100 if pruned["count"] > 0 else 0
        st.caption(
            f"{pruned['count']:,} games | "
            f"WR: {pruned['win_rate']:.1%} | "
            f"Decisive: {pruned['count_decisive']:,} | "
            f"Draws: {pruned['count_draws']} | "
            f"Coverage: {coverage:.0f}%"
        )

        # Render chart
        t_render = time.perf_counter()
        if chart_type == "Tree":
            fig = render_tree(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "Sunburst":
            fig = render_sunburst(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "Icicle":
            fig = render_icicle(pruned, panel["label"])
            st.plotly_chart(fig, use_container_width=True)
        else:  # Path Table
            df = build_path_table(pruned)
            if df.empty:
                st.info("All branches below threshold.")
            else:
                st.dataframe(df, use_container_width=True, height=400,
                             column_config=PATH_TABLE_COLUMN_CONFIG)
        render_ms = (time.perf_counter() - t_render) * 1000

        # Update URL params for bookmarking
        st.query_params.update(unit=primary_unit, mode=compare_mode)

        # Export buttons (with filter summary metadata)
        filter_summary = {
            "unit": panel["unit"], "player": panel["player"],
            "rating_range": list(rating_range), "depth": max_depth,
            "include": list(include_units) + list(inc_extra),
            "exclude": list(exclude_units) + list(exc_extra),
            "thresholds": thresholds, "max_branches": max_branches,
        }
        export_data = {"filters": filter_summary, "tree": pruned}

        col_json, col_csv = st.columns(2)
        with col_json:
            st.download_button(
                f"Export JSON",
                json.dumps(export_data, indent=2, default=str),
                f"ob_{panel['unit']}_{panel['player']}.json",
                "application/json",
            )
        with col_csv:
            df_export = build_path_table(pruned)
            if not df_export.empty:
                st.download_button(
                    "Export CSV",
                    df_export.to_csv(index=False),
                    f"ob_{panel['unit']}_{panel['player']}.csv",
                    "text/csv",
                )

        panel_debug_info.append({
            "label": panel["label"],
            "count": pruned["count"],
            "nodes": count_nodes(pruned),
            "query_ms": timing["query_ms"],
            "build_ms": timing["build_ms"],
            "prune_ms": prune_ms,
            "render_ms": render_ms,
        })


# --- Debug section (per-panel) ---
with st.expander("Debug", expanded=False):
    show_sql = st.checkbox("Show SQL")
    if show_sql:
        for panel in panels:
            inc_extra = ()
            exc_extra = ()
            if compare_mode == "With vs Without":
                idx = panels.index(panel)
                if idx == 0:
                    inc_extra = (with_unit,)
                else:
                    exc_extra = (with_unit,)
            inc = tuple(sorted(set(include_units) | set(inc_extra)))
            exc = tuple(sorted(set(exclude_units) | set(exc_extra)))
            st.markdown(f"**{panel['label']}**")
            sql = build_sql_for_debug(
                panel["unit"], panel["player"],
                float(rating_range[0]), float(rating_range[1]),
                inc, exc, max_depth,
            )
            st.code(sql, language="sql")

    st.markdown("**Performance (per panel)**")
    for info in panel_debug_info:
        if info.get("nodes"):
            st.text(
                f"{info['label']}: {info['count']:,} games, {info['nodes']} nodes | "
                f"Query: {info['query_ms']:.0f}ms, Build: {info['build_ms']:.0f}ms, "
                f"Prune: {info['prune_ms']:.0f}ms, Render: {info['render_ms']:.0f}ms"
            )
        else:
            st.text(f"{info['label']}: {info.get('count', 0)} games (no chart rendered)")
```

- [ ] **Step 2: Test the full app**

Run: `cd c:/libraries/PrismataAI && streamlit run tools/ob_explorer.py`

Expected: App loads. Select "Wild Drone", click Apply. Verify:
- P1 Wild Drone turn 1: DD ~75%, EWW ~20%
- P2 Wild Drone turn 1: DD ~54%, DEW ~32%
- All four chart types render
- Threshold sliders prune instantly (no re-query — check debug timing shows 0ms query on threshold change)
- Side-by-side and stacked layouts both work
- Export JSON and CSV download valid files
- Debug shows per-panel timings and SQL

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer.py
git commit -m "feat(tools): OB explorer Streamlit app — full assembly with caching"
```

---

## Task 10: Edge Cases + Polish

**Files:**
- Modify: `tools/ob_explorer.py`
- Modify: `tools/ob_explorer_viz.py`

- [ ] **Step 1: Test edge cases**

- Set rating range very high (2300–2400) — fewer games, possibly zero for rare units
- Set all thresholds to 50% — should prune most branches, showing "All branches below threshold"
- Try a unit with no card art — should show text label only
- Try include + exclude overlap — should show error message
- Try Unit vs Unit with same unit — should show error
- Switch chart type after applying — should be instant (0ms query in debug)

- [ ] **Step 2: Fix any issues found during testing**

Address whatever edge cases surface. Common fixes:
- Ensure `st.session_state` tree cache clears when form is resubmitted (it does — new key is generated from new params)
- Handle units that have very few games (< 30) — low-confidence indicators should appear

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer.py tools/ob_explorer_viz.py
git commit -m "fix(tools): OB explorer edge cases and polish"
```

---

## Summary

| Task | What | Files |
|---|---|---|
| 1 | Skeleton + deps | All 4 new files |
| 2 | Layer 1: Bulk SQL fetch | `ob_explorer_data.py` |
| 3 | Layer 2: Prefix tree construction | `ob_explorer_data.py` |
| 4 | Layer 3: Pruning with Other node | `ob_explorer_data.py` |
| 5 | Data layer tests | `tools/tests/test_ob_explorer_data.py` |
| 6 | Scatter tree viz | `ob_explorer_viz.py` |
| 7 | Sunburst + Icicle viz | `ob_explorer_viz.py` |
| 8 | Path table (numeric columns) | `ob_explorer_viz.py` |
| 9 | Full Streamlit app with caching | `ob_explorer.py` |
| 10 | Edge cases + polish | App + viz files |

---

## Applied Optional Enhancements

All optional items accepted and integrated:

1. CSV export — already in Task 9
2. `os.getenv("PRISMATA_DB")` fallback — Task 1 Step 3
3. `sqrt(frequency)` node sizing — Task 6 Step 1
4. URL params via `st.query_params` — Task 9 Step 1
5. `__all__` exports — Tasks 2, 6
6. Filter summary in exports — Task 9 Step 1
7. Subtree-weighted tree layout — Task 6 Step 1
