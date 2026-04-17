# Opening Book Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit-based interactive visualization tool for exploring opening book consensus data from 26k+ expert Prismata replays, with decision tree, sunburst, icicle, and path table views.

**Architecture:** Three Python files — data layer (bulk SQL + in-memory prefix tree), visualization layer (Plotly charts + table), and Streamlit app (controls + layout). Queries `replays.db` read-only via SQLite. Three cacheable layers: DB rows → unpruned tree → pruned viz data. `st.form` for data filters, instant threshold/chart switching outside form.

**Tech Stack:** Python 3.13, Streamlit, Plotly, Pillow, SQLite3

**Spec:** `docs/superpowers/specs/2026-04-10-opening-book-explorer-design-v2.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `tools/requirements-explorer.txt` | Pip dependencies |
| `tools/ob_explorer_data.py` | DB connection, bulk SQL query, prefix tree construction, pruning, Wilson CI |
| `tools/ob_explorer_viz.py` | Plotly scatter tree, sunburst, icicle, path table renderers |
| `tools/ob_explorer.py` | Streamlit app: sidebar form, presentation controls, layout, debug section |

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

```
streamlit
plotly
Pillow
```

Write to `tools/requirements-explorer.txt`.

- [ ] **Step 2: Install dependencies**

Run: `pip install -r tools/requirements-explorer.txt`
Expected: successful install of streamlit, plotly, Pillow.

- [ ] **Step 3: Create data module skeleton**

```python
"""Opening book explorer — data layer.

Bulk-fetches turn data from replays.db and builds an in-memory prefix tree
for opening book analysis. Three cacheable layers:
  Layer 1: Filtered DB rows (cached, keyed on filter params)
  Layer 2: Unpruned full tree (built from Layer 1)
  Layer 3: Pruned tree (built from Layer 2 + thresholds)
"""
import math
import sqlite3
import time
from collections import Counter

import streamlit as st

from replay_parser.ob_analysis import BASE_SET_UNITS
from replay_parser.ob_format import UNIT_ABBREVS, _abbrev_buy

DB_PATH = "c:/libraries/prismata-replay-parser/replays.db"


def get_connection():
    """Open read-only SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
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
Streamlit-renderable dataframes.
"""
import plotly.graph_objects as go


def wr_delta_color(delta):
    """Map WR delta to RGB color. Red (negative) → grey (zero) → green (positive)."""
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

```python
@st.cache_data(ttl=None)
def fetch_turn_data(
    primary_unit: str,
    player: int,
    min_rating: float,
    max_rating: float,
    include_units: tuple[str, ...],
    exclude_units: tuple[str, ...],
    max_depth: int,
) -> tuple[list[tuple], float]:
    """Layer 1: Fetch all matching turn_buys rows in a single query.

    Returns (rows, query_time_ms). Each row is:
      (code, player_turn, buy_hash, buy_sequence_json, result)

    Args use tuples (not lists) for hashability with @st.cache_data.
    """
    t0 = time.perf_counter()
    conn = get_connection()

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

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    elapsed = (time.perf_counter() - t0) * 1000
    return rows, elapsed
```

- [ ] **Step 2: Verify the query works**

Run a quick test in Python:

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import fetch_turn_data
rows, ms = fetch_turn_data.__wrapped__(
    'Wild Drone', 0, 2000.0, 2400.0, (), (), 3
)
print(f'{len(rows)} rows in {ms:.0f}ms')
print('First row:', rows[0] if rows else 'empty')
"
```

Expected: ~5000-9000 rows, <500ms.

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer Layer 1 — bulk SQL fetch with caching"
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

- [ ] **Step 2: Add tree construction function**

Append to `tools/ob_explorer_data.py`:

```python
import json as _json


def build_tree(rows: list[tuple], player: int) -> dict:
    """Layer 2: Build unpruned prefix tree from bulk-fetched rows.

    Groups rows by game code to get per-game turn paths, then walks
    each game's sequence to build the nested tree. Computes frequency,
    win rate, WR delta, Wilson CI, and sample codes at each node.

    Returns the root node dict.
    """
    # Group rows by code: {code: [(player_turn, buy_hash, buy_seq_json, result), ...]}
    games: dict[str, list[tuple]] = {}
    for code, player_turn, buy_hash, buy_seq_json, result in rows:
        games.setdefault(code, []).append((player_turn, buy_hash, buy_seq_json, result))

    total_games = len(games)
    if total_games == 0:
        return _empty_root(player)

    # Compute root-level baseline win rate
    total_wins = sum(
        1 for turns in games.values()
        if turns and turns[0][3] == player  # result == player means this player won
    )
    total_draws = sum(
        1 for turns in games.values()
        if turns and turns[0][3] == 2
    )
    total_decisive = total_games - total_draws
    root_wr = total_wins / total_decisive if total_decisive > 0 else 0.5

    root = {
        "path_id": "root",
        "buy": [],
        "buy_abbrev": "Start",
        "count": total_games,
        "count_decisive": total_decisive,
        "count_draws": total_draws,
        "frequency_parent": 1.0,
        "frequency_root": 1.0,
        "win_rate": root_wr,
        "win_rate_delta": 0.0,
        "win_rate_ci_low": wilson_ci(total_wins, total_decisive)[0],
        "win_rate_ci_high": wilson_ci(total_wins, total_decisive)[1],
        "sample_codes": list(games.keys())[:10],
        "children": [],
        "other_count": 0,
        "other_frequency": 0.0,
    }

    # Build tree recursively by turn depth
    _build_children(root, games, 1, root_wr, total_games)

    return root


def _build_children(
    parent: dict,
    games: dict[str, list[tuple]],
    turn: int,
    root_wr: float,
    root_total: int,
):
    """Recursively add children for the given turn depth."""
    # Group games by their buy_hash at this turn
    groups: dict[str, list[str]] = {}  # buy_hash -> [code, ...]
    buy_seq_map: dict[str, str] = {}  # buy_hash -> buy_sequence_json (first seen)

    for code, turns in games.items():
        for player_turn, buy_hash, buy_seq_json, result in turns:
            if player_turn == turn:
                groups.setdefault(buy_hash, []).append(code)
                if buy_hash not in buy_seq_map:
                    buy_seq_map[buy_hash] = buy_seq_json
                break

    parent_count = parent["count"]
    parent_path = parent["path_id"]

    for buy_hash, codes in sorted(groups.items(), key=lambda x: -len(x[1])):
        count = len(codes)
        buy_list = _json.loads(buy_seq_map[buy_hash])

        # Compute WR for this node
        wins = 0
        draws = 0
        for code in codes:
            turns = games[code]
            if turns:
                result = turns[0][3]  # result is same across all rows for a code
                if result == turns[0][3]:  # always true, just access result
                    pass
            result = games[code][0][3]
            if result == 2:
                draws += 1
            elif result == int(buy_hash is not None and False):  # dummy, see below
                pass
        # Recompute properly
        wins = 0
        draws = 0
        for code in codes:
            result = games[code][0][3]  # result is constant per game
            if result == 2:
                draws += 1
            # player field from parent context — we need it
            # The player is encoded in the query, so result == player means win
        # We need the player value. Extract from the rows.
        # All rows have the same player (query filtered). Get it from any row.
        sample_row = games[codes[0]]
        # Actually, result semantics: result=0 means P1 wins, result=1 means P2 wins
        # The `player` param was used in the SQL query. We need to pass it through.
        # Let's refactor: pass `player` into _build_children.
        pass

    # This needs a cleaner implementation — see next step.
```

Actually, let me write this more carefully. Let me replace the above with a clean version.

- [ ] **Step 2 (revised): Add tree construction function**

Append to `tools/ob_explorer_data.py` (replacing the draft above):

```python
import json as _json


def build_tree(rows: list[tuple], player: int) -> dict:
    """Layer 2: Build unpruned prefix tree from bulk-fetched rows.

    Args:
        rows: Tuples of (code, player_turn, buy_hash, buy_seq_json, result)
        player: 0 or 1 — needed for win rate computation

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
    ci_low, ci_high = wilson_ci(total_wins, total_decisive)

    root = _make_node(
        path_id="root",
        buy_list=[],
        count=total_games,
        wins=total_wins,
        draws=total_draws,
        parent_count=total_games,
        root_total=total_games,
        root_wr=root_wr,
        codes=list(games.keys()),
    )

    _build_level(root, games, result_by_code, player, 0, root_wr, total_games)

    return root


def _build_level(
    parent: dict,
    games: dict[str, list[tuple]],
    result_by_code: dict[str, int],
    player: int,
    turn_index: int,
    root_wr: float,
    root_total: int,
):
    """Recursively add children for turn at turn_index in each game's sorted turn list."""
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
    parent_path = parent["path_id"]

    for buy_hash, codes in sorted(groups.items(), key=lambda x: -len(x[1])):
        count = len(codes)
        buy_list = _json.loads(buy_seq_map[buy_hash])
        wins = sum(1 for c in codes if result_by_code[c] == player)
        draws = sum(1 for c in codes if result_by_code[c] == 2)

        path_id = f"{parent_path}/{buy_hash}"

        node = _make_node(
            path_id=path_id,
            buy_list=buy_list,
            count=count,
            wins=wins,
            draws=draws,
            parent_count=parent_count,
            root_total=root_total,
            root_wr=root_wr,
            codes=codes,
        )
        parent["children"].append(node)

        # Recurse into next turn
        sub_games = {c: games[c] for c in codes if c in games}
        _build_level(node, sub_games, result_by_code, player, turn_index + 1, root_wr, root_total)


def _make_node(
    path_id: str,
    buy_list: list[str],
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
        "buy_abbrev": _abbrev_buy(buy_list) if buy_list else "Start",
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
```

- [ ] **Step 3: Verify tree construction**

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import fetch_turn_data, build_tree
rows, ms = fetch_turn_data.__wrapped__('Wild Drone', 0, 2000.0, 2400.0, (), (), 3)
tree = build_tree(rows, 0)
print(f'Root: {tree[\"count\"]} games, WR={tree[\"win_rate\"]:.3f}')
for c in tree['children'][:3]:
    print(f'  {c[\"buy_abbrev\"]}: {c[\"count\"]} ({c[\"frequency_parent\"]*100:.1f}%) WR={c[\"win_rate\"]:.3f} delta={c[\"win_rate_delta\"]:+.3f}')
    for cc in c['children'][:2]:
        print(f'    {cc[\"buy_abbrev\"]}: {cc[\"count\"]} ({cc[\"frequency_parent\"]*100:.1f}%)')
"
```

Expected: Root ~1700 games, DD ~75%, EWW ~20%, with children at turn 2.

- [ ] **Step 4: Commit**

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
def prune_tree(
    tree: dict,
    min_freq_per_turn: list[float],
    max_branches: int = 8,
) -> dict:
    """Layer 3: Prune tree by per-turn frequency thresholds and branch cap.

    Returns a new tree (does not mutate the input). Pruned branches are
    aggregated into an 'Other' node at each level.
    """
    import copy
    pruned = copy.deepcopy(tree)
    _prune_level(pruned, min_freq_per_turn, max_branches, 0)
    return pruned


def _prune_level(node: dict, thresholds: list[float], max_branches: int, depth: int):
    """Recursively prune children at each level."""
    if not node["children"]:
        return

    threshold = thresholds[depth] if depth < len(thresholds) else thresholds[-1]

    # Sort children by count descending (stable)
    node["children"].sort(key=lambda c: -c["count"])

    kept = []
    other_count = 0
    for i, child in enumerate(node["children"]):
        if child["frequency_parent"] >= threshold and len(kept) < max_branches:
            kept.append(child)
        else:
            other_count += child["count"]

    # Add existing other_count from the node (in case of nested pruning)
    other_count += node["other_count"]
    parent_count = node["count"]

    node["children"] = kept
    node["other_count"] = other_count
    node["other_frequency"] = other_count / parent_count if parent_count > 0 else 0.0

    # Recurse into kept children
    for child in kept:
        _prune_level(child, thresholds, max_branches, depth + 1)
```

- [ ] **Step 2: Verify pruning**

```bash
cd c:/libraries/PrismataAI && python -c "
import sys; sys.path.insert(0, '.')
from tools.ob_explorer_data import fetch_turn_data, build_tree, prune_tree
rows, _ = fetch_turn_data.__wrapped__('Wild Drone', 0, 2000.0, 2400.0, (), (), 3)
tree = build_tree(rows, 0)
pruned = prune_tree(tree, [0.05, 0.05, 0.10], max_branches=8)
total_freq = sum(c['frequency_parent'] for c in pruned['children']) + pruned['other_frequency']
print(f'Branches: {len(pruned[\"children\"])}, Other: {pruned[\"other_count\"]} ({pruned[\"other_frequency\"]*100:.1f}%)')
print(f'Total freq check: {total_freq:.4f} (should be ~1.0)')
for c in pruned['children']:
    n_sub = len(c['children'])
    print(f'  {c[\"buy_abbrev\"]}: {c[\"count\"]} — {n_sub} sub-branches, other={c[\"other_count\"]}')
"
```

Expected: 2-3 turn 1 branches (DD, EWW, maybe EEV). Total freq ~1.0.

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer Layer 3 — tree pruning with Other node"
```

---

## Task 5: Data Layer — SQL Generation for Debug

**Files:**
- Modify: `tools/ob_explorer_data.py`

- [ ] **Step 1: Add SQL generation function**

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
    """Return the SQL query string with parameters substituted, for display."""
    all_include = (primary_unit,) + include_units
    include_clauses = []
    for unit in all_include:
        include_clauses.append(
            f"AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = '{unit}')"
        )
    exclude_clauses = []
    for unit in exclude_units:
        exclude_clauses.append(
            f"AND tb.code NOT IN (SELECT code FROM replay_units WHERE unit_name = '{unit}')"
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
  {chr(10).join('  ' + c for c in include_clauses)}
  {chr(10).join('  ' + c for c in exclude_clauses)}
ORDER BY tb.code, tb.player_turn"""
```

- [ ] **Step 2: Commit**

```bash
git add tools/ob_explorer_data.py
git commit -m "feat(tools): OB explorer debug SQL generation"
```

---

## Task 6: Visualization — Scatter Tree

**Files:**
- Modify: `tools/ob_explorer_viz.py`

- [ ] **Step 1: Add tree layout + rendering**

Append to `tools/ob_explorer_viz.py`:

```python
def render_tree(tree: dict, title: str = "") -> go.Figure:
    """Render a pruned tree as an interactive Plotly scatter plot.

    Nodes are markers, edges are line traces. Top-down layout with
    root at top. Color by WR delta, size by frequency.
    """
    if tree["count"] == 0:
        return _empty_figure("No games match filters")

    # Compute layout positions
    positions = {}  # path_id -> (x, y)
    _layout_tree(tree, positions, x=0.0, y=0.0, x_span=1.0, depth=0)

    # Collect node and edge data
    node_x, node_y, node_text, node_hover, node_color, node_size = [], [], [], [], [], []
    edge_x, edge_y = [], []

    def _collect(node, depth=0):
        px, py = positions[node["path_id"]]
        node_x.append(px)
        node_y.append(-py)  # invert y so root is at top

        label = node["buy_abbrev"]
        node_text.append(label)

        ci_str = f"CI: [{node['win_rate_ci_low']:.1%}, {node['win_rate_ci_high']:.1%}]"
        confidence = "" if node["count_decisive"] >= 30 else " ⚠️ LOW SAMPLE"
        hover = (
            f"<b>{label}</b><br>"
            f"Buy: {', '.join(node['buy']) if node['buy'] else 'Start'}<br>"
            f"Games: {node['count']} ({node['frequency_parent']:.1%} of parent, "
            f"{node['frequency_root']:.1%} of root)<br>"
            f"WR: {node['win_rate']:.1%} (Δ{node['win_rate_delta']:+.1%})<br>"
            f"{ci_str}<br>"
            f"Decisive: {node['count_decisive']}, Draws: {node['count_draws']}"
            f"{confidence}"
        )
        if node["other_count"] > 0:
            hover += f"<br>Other: {node['other_count']} ({node['other_frequency']:.1%})"
        node_hover.append(hover)

        node_color.append(wr_delta_color(node["win_rate_delta"]))
        # Size: min 10, max 40, scaled by frequency_root
        node_size.append(max(10, min(40, 10 + 30 * node["frequency_root"])))

        for child in node["children"]:
            cx, cy = positions[child["path_id"]]
            edge_x.extend([px, cx, None])
            edge_y.extend([-py, -cy, None])
            _collect(child, depth + 1)

    _collect(tree)

    fig = go.Figure()

    # Edges
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="#888", width=1),
        hoverinfo="none",
    ))

    # Nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=node_size, color=node_color, line=dict(width=1, color="#333")),
        text=node_text, textposition="top center", textfont=dict(size=10),
        hovertext=node_hover, hoverinfo="text",
    ))

    fig.update_layout(
        title=title,
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=40, b=20),
        height=500,
    )

    return fig


def _layout_tree(node, positions, x, y, x_span, depth):
    """Recursive tree layout: constant y-spacing per depth, distribute children on x."""
    positions[node["path_id"]] = (x, y)
    children = node["children"]
    if not children:
        return
    n = len(children)
    child_span = x_span / n
    start_x = x - x_span / 2 + child_span / 2
    for i, child in enumerate(children):
        cx = start_x + i * child_span
        _layout_tree(child, positions, cx, y + 1, child_span, depth + 1)


def _empty_figure(message: str) -> go.Figure:
    """Return a figure with a centered message."""
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=16, color="#888"))
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20), height=300,
    )
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
import plotly.express as px


def _flatten_tree_for_plotly(tree: dict) -> tuple[list, list, list, list, list, list]:
    """Flatten tree into parallel lists for Plotly hierarchical charts.

    Returns: (ids, labels, parents, values, colors, hovers)
    """
    ids, labels, parents, values, colors, hovers = [], [], [], [], [], []

    def _walk(node, parent_id=""):
        nid = node["path_id"]
        ids.append(nid)
        labels.append(node["buy_abbrev"])
        parents.append(parent_id)
        values.append(node["count"])
        colors.append(node["win_rate_delta"])

        confidence = "" if node["count_decisive"] >= 30 else " ⚠️"
        hover = (
            f"{node['buy_abbrev']}: {node['count']} games "
            f"({node['frequency_parent']:.1%})<br>"
            f"WR: {node['win_rate']:.1%} (Δ{node['win_rate_delta']:+.1%}){confidence}"
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
            hovers.append(f"Pruned: {node['other_count']} games ({node['other_frequency']:.1%})")

    _walk(tree)
    return ids, labels, parents, values, colors, hovers


def render_sunburst(tree: dict, title: str = "") -> go.Figure:
    """Render pruned tree as a Plotly sunburst chart."""
    if tree["count"] == 0:
        return _empty_figure("No games match filters")

    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)

    fig = go.Figure(go.Sunburst(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(
            colors=[wr_delta_color(c) for c in colors],
        ),
        hovertext=hovers,
        hoverinfo="text",
        branchvalues="total",
    ))

    fig.update_layout(
        title=title,
        margin=dict(l=20, r=20, t=40, b=20),
        height=500,
    )
    return fig


def render_icicle(tree: dict, title: str = "") -> go.Figure:
    """Render pruned tree as a Plotly icicle chart."""
    if tree["count"] == 0:
        return _empty_figure("No games match filters")

    ids, labels, parents, values, colors, hovers = _flatten_tree_for_plotly(tree)

    fig = go.Figure(go.Icicle(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(
            colors=[wr_delta_color(c) for c in colors],
        ),
        hovertext=hovers,
        hoverinfo="text",
        branchvalues="total",
    ))

    fig.update_layout(
        title=title,
        margin=dict(l=20, r=20, t=40, b=20),
        height=500,
    )
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

- [ ] **Step 1: Add path table builder**

Append to `tools/ob_explorer_viz.py`:

```python
import pandas as pd


def build_path_table(tree: dict) -> pd.DataFrame:
    """Flatten the tree into a sortable path table dataframe."""
    rows = []

    def _walk(node, path_parts):
        current_path = path_parts + ([node["buy_abbrev"]] if node["buy"] else [])

        if node["buy"]:  # skip root
            rows.append({
                "Path": " → ".join(current_path),
                "Count": node["count"],
                "Freq (parent)": f"{node['frequency_parent']:.1%}",
                "Freq (root)": f"{node['frequency_root']:.1%}",
                "Win Rate": f"{node['win_rate']:.1%}",
                "WR Delta": f"{node['win_rate_delta']:+.1%}",
                "CI": f"[{node['win_rate_ci_low']:.1%}, {node['win_rate_ci_high']:.1%}]",
                "Draws": node["count_draws"],
                "Codes": ", ".join(node["sample_codes"][:5]),
                "_sort_count": node["count"],
            })

        for child in node["children"]:
            _walk(child, current_path)

    _walk(tree, [])

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("_sort_count", ascending=False).drop(columns=["_sort_count"])
    return df.reset_index(drop=True)
```

- [ ] **Step 2: Commit**

```bash
git add tools/ob_explorer_viz.py
git commit -m "feat(tools): OB explorer path table"
```

---

## Task 9: Streamlit App — Full Assembly

**Files:**
- Modify: `tools/ob_explorer.py`

- [ ] **Step 1: Write the complete app**

Replace contents of `tools/ob_explorer.py`:

```python
"""Opening Book Explorer — Streamlit app.

Interactive visualization of opening book consensus data from expert replays.
Launch: streamlit run tools/ob_explorer.py
"""
import time

import streamlit as st
from PIL import Image

from tools.ob_explorer_data import (
    build_sql_for_debug,
    build_tree,
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


# --- Startup: load unit list and rating bounds ---
@st.cache_data(ttl=None)
def _startup():
    conn = get_connection()
    units = get_dominion_units(conn)
    max_r = get_max_rating(conn)
    conn.close()
    return units, max_r


dominion_units, max_rating = _startup()

st.title("Opening Book Explorer")

# --- Sidebar: Data Filters (inside form) ---
with st.sidebar:
    st.header("Data Filters")

    with st.form("data_filters"):
        primary_unit = st.selectbox("Primary Unit", dominion_units, index=dominion_units.index("Wild Drone") if "Wild Drone" in dominion_units else 0)

        compare_mode = st.radio("Compare Mode", ["P1 vs P2", "Unit vs Unit", "With vs Without"])

        second_unit = None
        with_unit = None
        if compare_mode == "Unit vs Unit":
            second_unit = st.selectbox("Second Unit", dominion_units, index=min(1, len(dominion_units) - 1))
        elif compare_mode == "With vs Without":
            with_unit = st.selectbox("With/Without Unit", dominion_units, index=min(1, len(dominion_units) - 1))

        include_units = st.multiselect("Include Units (must be in set)", dominion_units)
        exclude_units = st.multiselect("Exclude Units (must NOT be in set)", dominion_units)

        rating_range = st.slider("Rating Range", 1500, max_rating, (2000, max_rating), step=50)
        max_depth = st.slider("Turn Depth", 1, 5, 3)
        max_branches = st.slider("Max Branches per Level", 3, 20, 8)

        submitted = st.form_submit_button("Apply")

    # Presentation controls (outside form — instant update)
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

# --- Load card art helper ---
CARD_ART_DIR = "bin/asset/images/cards"


def load_card_art(unit_name: str, size: int = 48):
    """Load and resize card art. Returns None if missing."""
    import os
    path = os.path.join(CARD_ART_DIR, f"{unit_name}.png")
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        img.thumbnail((size, size))
        return img
    except Exception:
        return None


# --- Build panel configs based on compare mode ---
def make_panel(unit, player, label):
    return {"unit": unit, "player": player, "label": label}


if compare_mode == "P1 vs P2":
    panels = [
        make_panel(primary_unit, 0, f"P1 — {primary_unit}"),
        make_panel(primary_unit, 1, f"P2 — {primary_unit}"),
    ]
elif compare_mode == "Unit vs Unit":
    panels = [
        make_panel(primary_unit, 0, f"P1 — {primary_unit}"),
        make_panel(second_unit, 0, f"P1 — {second_unit}"),
    ]
else:  # With vs Without
    panels = [
        make_panel(primary_unit, 0, f"P1 — {primary_unit} WITH {with_unit}"),
        make_panel(primary_unit, 0, f"P1 — {primary_unit} WITHOUT {with_unit}"),
    ]


# --- Render panels ---
def render_panel(panel, include_extra=(), exclude_extra=()):
    """Fetch data, build tree, prune, and render for one panel."""
    inc = tuple(sorted(set(include_units) | set(include_extra)))
    exc = tuple(sorted(set(exclude_units) | set(exclude_extra)))

    t0 = time.perf_counter()
    rows, query_ms = fetch_turn_data(
        panel["unit"], panel["player"],
        float(rating_range[0]), float(rating_range[1]),
        inc, exc, max_depth,
    )
    tree = build_tree(rows, panel["player"])
    build_ms = (time.perf_counter() - t0) * 1000 - query_ms

    t1 = time.perf_counter()
    pruned = prune_tree(tree, thresholds, max_branches)
    prune_ms = (time.perf_counter() - t1) * 1000

    return pruned, query_ms, build_ms, prune_ms


if layout_mode == "Side-by-side":
    cols = st.columns(2)
else:
    cols = [st, st]  # stacked: both render to main area

for i, panel in enumerate(panels):
    container = cols[i] if layout_mode == "Side-by-side" else st

    with container:
        # Header with card art
        art = load_card_art(panel["unit"])
        if art:
            hcol1, hcol2 = st.columns([1, 8])
            with hcol1:
                st.image(art)
            with hcol2:
                st.subheader(panel["label"])
        else:
            st.subheader(panel["label"])

        # Build include/exclude overrides for With/Without mode
        inc_extra = ()
        exc_extra = ()
        if compare_mode == "With vs Without":
            if i == 0:
                inc_extra = (with_unit,)
            else:
                exc_extra = (with_unit,)

        with st.spinner("Querying..."):
            pruned, query_ms, build_ms, prune_ms = render_panel(panel, inc_extra, exc_extra)

        if pruned["count"] == 0:
            st.warning(f"No games match these filters for {panel['label']}.")
            continue

        st.caption(f"{pruned['count']:,} games | WR: {pruned['win_rate']:.1%}")

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
                st.dataframe(df, use_container_width=True, height=400)
        render_ms = (time.perf_counter() - t_render) * 1000

        # JSON export
        import json
        st.download_button(
            f"Export JSON ({panel['label']})",
            json.dumps(pruned, indent=2, default=str),
            f"ob_{panel['unit']}_{panel['player']}.json",
            "application/json",
        )

# --- Debug section ---
with st.expander("Debug", expanded=False):
    show_sql = st.checkbox("Show SQL")
    if show_sql:
        sql = build_sql_for_debug(
            primary_unit, 0,
            float(rating_range[0]), float(rating_range[1]),
            tuple(include_units), tuple(exclude_units), max_depth,
        )
        st.code(sql, language="sql")

    st.markdown("**Performance**")
    st.text(f"Query: {query_ms:.0f}ms | Build: {build_ms:.0f}ms | Prune: {prune_ms:.0f}ms | Render: {render_ms:.0f}ms")
    total_nodes = sum(1 for _ in _count_nodes(pruned)) if pruned["count"] > 0 else 0
    st.text(f"Total nodes rendered: {total_nodes}")
```

Wait — `_count_nodes` doesn't exist. Let me add it inline:

Add this small helper near the top of the debug section (or as a local function):

```python
def _count_nodes(node):
    """Count total nodes in tree."""
    yield node
    for child in node.get("children", []):
        yield from _count_nodes(child)
```

Actually, to keep it clean, I'll put `_count_nodes` in `ob_explorer_data.py` and import it. But for the plan, let me just define it inline in the app file. The full app above should have this function defined before the debug section uses it. Add it right after the imports:

```python
def _count_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from _count_nodes(child)
```

- [ ] **Step 2: Test the full app**

Run: `cd c:/libraries/PrismataAI && streamlit run tools/ob_explorer.py`

Expected: App loads in browser. Select "Wild Drone", click Apply. See P1 vs P2 comparison. Switch chart types. Adjust thresholds.

Verify:
- P1 Wild Drone turn 1: DD ~75%, EWW ~20%
- P2 Wild Drone turn 1: DD ~54%, DEW ~32%
- Tree/Sunburst/Icicle/Path Table all render
- Thresholds prune branches instantly (no re-query)
- Export JSON downloads a valid file
- Debug section shows SQL and timing

- [ ] **Step 3: Commit**

```bash
git add tools/ob_explorer.py
git commit -m "feat(tools): OB explorer Streamlit app — full assembly"
```

---

## Task 10: Polish and Edge Cases

**Files:**
- Modify: `tools/ob_explorer.py`
- Modify: `tools/ob_explorer_data.py`

- [ ] **Step 1: Handle "All branches pruned" state**

In `tools/ob_explorer.py`, after rendering the pruned tree, check if all children were pruned:

Add after the `if pruned["count"] == 0:` block:

```python
        if pruned["count"] > 0 and not pruned["children"]:
            st.info("All branches below threshold. Try lowering the frequency threshold.")
            continue
```

- [ ] **Step 2: Add low-confidence warning to path table**

In `tools/ob_explorer_viz.py`, update `build_path_table` to mark low-confidence rows. Change the Win Rate column:

```python
                "Win Rate": f"{node['win_rate']:.1%}" + (" *" if node["count_decisive"] < 30 else ""),
```

- [ ] **Step 3: Test edge cases**

- Set rating range very high (2300-2400) — should show fewer games, possibly zero for rare units
- Set all thresholds to 50% — should prune most branches, showing "All branches below threshold"
- Try a unit with no card art — should show text label only
- Try include + exclude overlap — should show error message

- [ ] **Step 4: Commit**

```bash
git add tools/ob_explorer.py tools/ob_explorer_viz.py
git commit -m "fix(tools): OB explorer edge cases — pruned state, low confidence, validation"
```

---

## Summary

| Task | What | Files |
|---|---|---|
| 1 | Skeleton + deps | All 4 new files |
| 2 | Layer 1: Bulk SQL fetch | `ob_explorer_data.py` |
| 3 | Layer 2: Prefix tree construction | `ob_explorer_data.py` |
| 4 | Layer 3: Pruning with Other node | `ob_explorer_data.py` |
| 5 | Debug SQL generation | `ob_explorer_data.py` |
| 6 | Scatter tree viz | `ob_explorer_viz.py` |
| 7 | Sunburst + Icicle viz | `ob_explorer_viz.py` |
| 8 | Path table | `ob_explorer_viz.py` |
| 9 | Full Streamlit app | `ob_explorer.py` |
| 10 | Edge cases + polish | All 3 app files |
