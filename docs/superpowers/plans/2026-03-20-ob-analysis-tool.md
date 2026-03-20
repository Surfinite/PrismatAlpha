# Opening Book Analysis Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that analyzes expert replays in `replays.db` to generate data-driven opening book entries with consensus evidence.

**Architecture:** Two new Python files — `ob_analysis.py` (SQL queries, consensus computation, CLI) and `ob_format.py` (report/config JSON formatting, validation against existing OB). Read-only against existing DB tables. Outputs human-readable summary to stdout, optionally saves report JSON and config-ready OB entries to files.

**Tech Stack:** Python 3.10+, sqlite3 (read-only), json, argparse

**Spec:** `docs/superpowers/specs/2026-03-20-ob-analysis-tool-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `replay_parser/ob_analysis.py` | SQL queries, consensus computation, pair analysis, turn 2 analysis, CLI entry point |
| `replay_parser/ob_format.py` | Format report JSON, config-ready OB entries, stdout summary, validate against existing LiveOpeningBook2 |
| `replay_parser/tests/test_ob_analysis.py` | Unit tests for consensus logic with mock data |

### Key Reference Files (read-only)

| File | Why |
|---|---|
| `bin/asset/config/config.txt` | Existing OB entries (LiveOpeningBook2, etc.) for validation comparison |
| `replay_parser/database.py` | DB schema reference (turn_buys, turn_state, replay_units, replays tables) |
| `c:/libraries/prismata-replay-parser/replays.db` | Live database with 102k parsed replays |

---

## Task 1: Core Consensus Computation

The foundation — query the DB for per-unit buy frequencies and compute consensus metrics.

**Files:**
- Create: `replay_parser/ob_analysis.py`
- Create: `replay_parser/tests/test_ob_analysis.py`

- [ ] **Step 1: Create `ob_analysis.py` with constants and `get_dominion_units()`**

```python
"""Opening book analysis — generate data-driven OB entries from expert replays."""
import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

BASE_SET_UNITS = frozenset([
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Wall", "Steelsplitter", "Forcefield", "Gauss Cannon",
    "Tarsier", "Rhino"
])

STARTING_STATES = {
    0: [("Drone", 6), ("Engineer", 2)],
    1: [("Drone", 7), ("Engineer", 2)],
}
DD_FOLLOWUP_STATES = {
    0: [("Drone", 8), ("Engineer", 2)],
    1: [("Drone", 9), ("Engineer", 2)],
}


def get_dominion_units(conn: sqlite3.Connection, min_rating: int,
                       min_samples: int) -> list[dict]:
    """Get Dominion units with enough games at the rating threshold."""
    placeholders = ",".join("?" for _ in BASE_SET_UNITS)
    rows = conn.execute(f"""
        SELECT ru.unit_name, COUNT(DISTINCT ru.code) as games
        FROM replay_units ru
        JOIN replays r ON ru.code = r.code
        WHERE r.p1_rating >= ? AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND ru.unit_name NOT IN ({placeholders})
        GROUP BY ru.unit_name
        HAVING games >= ?
        ORDER BY games DESC
    """, (min_rating, min_rating, *BASE_SET_UNITS, min_samples)).fetchall()
    return [{"unit": row[0], "games": row[1]} for row in rows]
```

- [ ] **Step 2: Add `analyze_unit_turn1()` — per-unit consensus query**

```python
def analyze_unit_turn1(conn: sqlite3.Connection, unit: str, player: int,
                       min_rating: int) -> dict:
    """Analyze turn 1 buy consensus for a unit and player position.

    Groups by buy_hash (order-independent) for consensus computation.
    Returns dict with top_buy, frequency, win_rate, consensus label, etc.
    """
    rows = conn.execute("""
        SELECT tb.buy_hash, tb.buy_sequence, COUNT(*) as freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) as draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        WHERE tb.player = ? AND tb.player_turn = 1
          AND r.p1_rating >= ? AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND r.result IN (0, 1, 2)
          AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = ?)
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """, (player, min_rating, min_rating, unit)).fetchall()

    if not rows:
        return {"total_games": 0, "consensus": "insufficient"}

    total = sum(r[2] for r in rows)
    top = rows[0]
    top_freq = top[2] / total
    top_wins = top[3]
    top_draws = top[4]
    non_draw = top[2] - top_draws
    win_rate = top_wins / non_draw if non_draw > 0 else 0.0

    # For the buy sequence, pick the most common ordering for this hash
    # (buy_hash groups order-independent, but we need one representative order)
    top_buy = json.loads(top[1])

    result = {
        "top_buy": top_buy,
        "top_buy_hash": top[0],
        "frequency": round(top_freq, 4),
        "win_rate": round(win_rate, 4),
        "sample_size": top[2],
        "total_games": total,
    }

    if len(rows) > 1:
        runner = rows[1]
        result["runner_up"] = json.loads(runner[1])
        result["runner_up_freq"] = round(runner[2] / total, 4)

    # Top 5 for the report
    result["top_5"] = []
    for r in rows[:5]:
        freq = r[2]
        wins = r[3]
        draws = r[4]
        nd = freq - draws
        result["top_5"].append({
            "buy": json.loads(r[1]),
            "buy_hash": r[0],
            "freq": round(freq / total, 4),
            "wins": round(wins / nd, 4) if nd > 0 else 0.0,
            "count": freq,
        })

    return result
```

Note: This query groups by `buy_hash` (sorted, order-independent) per the spec. SQLite's `buy_sequence` selection alongside `GROUP BY buy_hash` returns an indeterminate row's value. In practice, the buy ordering within a turn is almost always the same across replays (determined by click order), so this produces the correct result. If strict ordering is needed, add a follow-up query: `SELECT buy_sequence, COUNT(*) FROM turn_buys WHERE buy_hash = :hash GROUP BY buy_sequence ORDER BY COUNT(*) DESC LIMIT 1`.

- [ ] **Step 3: Add `classify_consensus()` helper**

```python
def classify_consensus(frequency: float, strong_threshold: float,
                       pair_threshold: float) -> str:
    """Classify consensus level from frequency."""
    if frequency >= strong_threshold:
        return "strong"
    elif frequency >= pair_threshold:
        return "moderate"
    else:
        return "contested"
```

- [ ] **Step 4: Write tests for consensus computation**

Create `replay_parser/tests/test_ob_analysis.py`:

```python
import sqlite3
import json
import pytest
from replay_parser.ob_analysis import (
    BASE_SET_UNITS, get_dominion_units, analyze_unit_turn1,
    classify_consensus, STARTING_STATES, DD_FOLLOWUP_STATES,
)


@pytest.fixture
def analysis_db(tmp_path):
    """Create a test DB with mock replay data for OB analysis."""
    db_path = str(tmp_path / "test_ob.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE replays (code TEXT PRIMARY KEY, p1_rating REAL, p2_rating REAL, result INTEGER, balance_passed INTEGER, min_rating REAL)")
    conn.execute("CREATE TABLE replay_units (code TEXT, unit_name TEXT, PRIMARY KEY (code, unit_name))")
    conn.execute("CREATE TABLE turn_buys (code TEXT, global_turn INTEGER, player INTEGER, player_turn INTEGER, buy_sequence TEXT, buy_hash TEXT, PRIMARY KEY (code, global_turn))")
    conn.execute("CREATE TABLE turn_state (code TEXT, global_turn INTEGER, player INTEGER, player_turn INTEGER, gold INTEGER, green INTEGER, blue INTEGER, red INTEGER, energy INTEGER, attack INTEGER, units_owned TEXT, total_units INTEGER, PRIMARY KEY (code, global_turn))")

    # Insert 100 mock games with "Wild Drone" in set
    # 70 games: P1 buys ["Drone", "Engineer", "Wild Drone"] and wins
    # 20 games: P1 buys ["Drone", "Drone"] and loses
    # 10 games: P1 buys ["Drone", "Drone"] and wins
    for i in range(100):
        code = f"WD{i:03d}"
        if i < 70:
            buy = '["Drone", "Engineer", "Wild Drone"]'
            buy_hash = "Drone,Engineer,Wild Drone"
            result = 0  # P1 wins
        elif i < 90:
            buy = '["Drone", "Drone"]'
            buy_hash = "Drone,Drone"
            result = 1  # P2 wins
        else:
            buy = '["Drone", "Drone"]'
            buy_hash = "Drone,Drone"
            result = 0  # P1 wins
        conn.execute("INSERT INTO replays VALUES (?, 2100, 2050, ?, 1, 2050)", (code, result))
        conn.execute("INSERT INTO replay_units VALUES (?, 'Wild Drone')", (code,))
        conn.execute("INSERT INTO turn_buys VALUES (?, 0, 0, 1, ?, ?)", (code, buy, buy_hash))

    conn.commit()
    conn.close()
    return db_path


def test_classify_consensus():
    assert classify_consensus(0.72, 0.60, 0.40) == "strong"
    assert classify_consensus(0.55, 0.60, 0.40) == "moderate"
    assert classify_consensus(0.30, 0.60, 0.40) == "contested"
    assert classify_consensus(0.60, 0.60, 0.40) == "strong"
    assert classify_consensus(0.40, 0.60, 0.40) == "moderate"


def test_base_set_has_11_units():
    assert len(BASE_SET_UNITS) == 11
    assert "Drone" in BASE_SET_UNITS
    assert "Wild Drone" not in BASE_SET_UNITS


def test_starting_states():
    assert STARTING_STATES[0] == [("Drone", 6), ("Engineer", 2)]
    assert STARTING_STATES[1] == [("Drone", 7), ("Engineer", 2)]
    assert DD_FOLLOWUP_STATES[0] == [("Drone", 8), ("Engineer", 2)]


def test_get_dominion_units(analysis_db):
    conn = sqlite3.connect(analysis_db)
    units = get_dominion_units(conn, min_rating=2000, min_samples=30)
    conn.close()
    assert len(units) == 1
    assert units[0]["unit"] == "Wild Drone"
    assert units[0]["games"] == 100


def test_get_dominion_units_excludes_base_set(analysis_db):
    conn = sqlite3.connect(analysis_db)
    # Add a base set unit to replay_units — should be excluded
    conn.execute("INSERT INTO replay_units VALUES ('WD000', 'Drone')")
    conn.commit()
    units = get_dominion_units(conn, min_rating=2000, min_samples=1)
    conn.close()
    unit_names = [u["unit"] for u in units]
    assert "Drone" not in unit_names


def test_analyze_unit_turn1(analysis_db):
    conn = sqlite3.connect(analysis_db)
    result = analyze_unit_turn1(conn, "Wild Drone", player=0, min_rating=2000)
    conn.close()
    assert result["total_games"] == 100
    assert result["top_buy"] == ["Drone", "Engineer", "Wild Drone"]
    assert result["frequency"] == 0.70
    # Win rate: 70 wins out of 70 non-draw games with this buy
    assert result["win_rate"] == 1.0
    assert result["runner_up"] == ["Drone", "Drone"]
    assert result["runner_up_freq"] == 0.30
    assert len(result["top_5"]) == 2


def test_analyze_unit_turn1_insufficient(analysis_db):
    conn = sqlite3.connect(analysis_db)
    result = analyze_unit_turn1(conn, "Nonexistent Unit", player=0, min_rating=2000)
    conn.close()
    assert result["consensus"] == "insufficient"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest replay_parser/tests/test_ob_analysis.py -v`

Expected: All 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add replay_parser/ob_analysis.py replay_parser/tests/test_ob_analysis.py
git commit -m "feat: add core OB consensus computation (turn 1, single-unit)"
```

---

## Task 2: Turn 2 Analysis and Pair Analysis

Extend `ob_analysis.py` with turn 2 DD follow-up analysis and pair analysis for contested units.

**Files:**
- Modify: `replay_parser/ob_analysis.py`
- Modify: `replay_parser/tests/test_ob_analysis.py`

- [ ] **Step 1: Add `analyze_unit_turn2_dd()` — turn 2 after DD opening**

```python
def analyze_unit_turn2_dd(conn: sqlite3.Connection, unit: str, player: int,
                          min_rating: int) -> dict:
    """Analyze turn 2 buy consensus for players who opened DD.

    Filters for the deterministic post-DD state:
    P1: 8 Drones + 2 Engineers, P2: 9 Drones + 2 Engineers.
    """
    expected_drones = 8 if player == 0 else 9
    rows = conn.execute("""
        SELECT tb.buy_hash, tb.buy_sequence, COUNT(*) as freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) as draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        JOIN turn_state ts ON tb.code = ts.code AND tb.global_turn = ts.global_turn
        WHERE tb.player = ? AND tb.player_turn = 2
          AND r.p1_rating >= ? AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND json_extract(ts.units_owned, '$.Drone') = ?
          AND json_extract(ts.units_owned, '$.Engineer') = 2
          AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = ?)
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """, (player, min_rating, min_rating, expected_drones, unit)).fetchall()

    if not rows:
        return {"total_games": 0, "consensus": "insufficient"}

    total = sum(r[2] for r in rows)
    top = rows[0]
    top_freq = top[2] / total
    top_wins = top[3]
    top_draws = top[4]
    non_draw = top[2] - top_draws

    return {
        "top_buy": json.loads(top[1]),
        "top_buy_hash": top[0],
        "frequency": round(top_freq, 4),
        "win_rate": round(top_wins / non_draw, 4) if non_draw > 0 else 0.0,
        "sample_size": top[2],
        "total_games": total,
        "state": f"{expected_drones}D+2E",
    }
```

- [ ] **Step 2: Add `find_co_occurring_units()` and `analyze_pair_turn1()`**

```python
def find_co_occurring_units(conn: sqlite3.Connection, unit: str,
                            min_rating: int, limit: int = 10) -> list[dict]:
    """Find the most common Dominion units co-occurring with a given unit."""
    placeholders = ",".join("?" for _ in BASE_SET_UNITS)
    rows = conn.execute(f"""
        SELECT ru2.unit_name, COUNT(*) as co_count
        FROM replay_units ru1
        JOIN replay_units ru2 ON ru1.code = ru2.code AND ru1.unit_name != ru2.unit_name
        JOIN replays r ON ru1.code = r.code
        WHERE ru1.unit_name = ?
          AND r.p1_rating >= ? AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND ru2.unit_name NOT IN ({placeholders})
        GROUP BY ru2.unit_name
        ORDER BY co_count DESC LIMIT ?
    """, (unit, min_rating, min_rating, *BASE_SET_UNITS, limit)).fetchall()
    return [{"unit": row[0], "co_count": row[1]} for row in rows]


def analyze_pair_turn1(conn: sqlite3.Connection, unit1: str, unit2: str,
                       player: int, min_rating: int) -> dict:
    """Analyze turn 1 consensus conditioned on BOTH units being present."""
    rows = conn.execute("""
        SELECT tb.buy_hash, tb.buy_sequence, COUNT(*) as freq,
               SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) as draws
        FROM turn_buys tb
        JOIN replays r ON tb.code = r.code
        WHERE tb.player = ? AND tb.player_turn = 1
          AND r.p1_rating >= ? AND r.p2_rating >= ?
          AND r.balance_passed = 1
          AND tb.code IN (
              SELECT ru1.code FROM replay_units ru1
              JOIN replay_units ru2 ON ru1.code = ru2.code
              WHERE ru1.unit_name = ? AND ru2.unit_name = ?
          )
        GROUP BY tb.buy_hash
        ORDER BY freq DESC
    """, (player, min_rating, min_rating, unit1, unit2)).fetchall()

    if not rows:
        return {"total_games": 0, "consensus": "insufficient"}

    total = sum(r[2] for r in rows)
    top = rows[0]
    top_freq = top[2] / total
    top_wins = top[3]
    top_draws = top[4]
    non_draw = top[2] - top_draws

    return {
        "top_buy": json.loads(top[1]),
        "top_buy_hash": top[0],
        "frequency": round(top_freq, 4),
        "win_rate": round(top_wins / non_draw, 4) if non_draw > 0 else 0.0,
        "sample_size": top[2],
        "total_games": total,
    }
```

- [ ] **Step 3: Add `run_full_analysis()` — orchestrates the entire pipeline**

```python
def run_full_analysis(conn: sqlite3.Connection, min_rating: int = 2000,
                      min_samples: int = 30, strong_threshold: float = 0.60,
                      pair_threshold: float = 0.40,
                      unit_filter: list[str] | None = None) -> dict:
    """Run the full OB analysis pipeline. Returns the complete analysis dict."""
    # Step 1: Get Dominion units
    units = get_dominion_units(conn, min_rating, min_samples)
    if unit_filter:
        units = [u for u in units if u["unit"] in unit_filter]

    # Step 2: Per-unit turn 1 consensus
    turn1_results = []
    contested_units = []

    for u in units:
        unit_name = u["unit"]
        p1 = analyze_unit_turn1(conn, unit_name, player=0, min_rating=min_rating)
        p2 = analyze_unit_turn1(conn, unit_name, player=1, min_rating=min_rating)

        p1["consensus"] = classify_consensus(
            p1.get("frequency", 0), strong_threshold, pair_threshold)
        p2["consensus"] = classify_consensus(
            p2.get("frequency", 0), strong_threshold, pair_threshold)

        turn1_results.append({
            "unit": unit_name,
            "games": u["games"],
            "p1": p1,
            "p2": p2,
        })

        # Flag for pair analysis if either side is contested
        if p1["consensus"] == "contested" or p2["consensus"] == "contested":
            contested_units.append(unit_name)

    # Step 3: Turn 2 analysis for DD follow-up states
    turn2_results = []
    for u in units:
        unit_name = u["unit"]
        for player in (0, 1):
            t2 = analyze_unit_turn2_dd(conn, unit_name, player, min_rating)
            if t2.get("total_games", 0) >= min_samples:
                t2["consensus"] = classify_consensus(
                    t2.get("frequency", 0), strong_threshold, pair_threshold)
                t2["unit"] = unit_name
                t2["player"] = player
                turn2_results.append(t2)

    # Step 4: Pair analysis for contested units
    pair_results = []
    for unit_name in contested_units:
        co_units = find_co_occurring_units(conn, unit_name, min_rating)
        for co in co_units[:5]:  # Check top 5 co-occurring
            co_name = co["unit"]
            for player in (0, 1):
                pair = analyze_pair_turn1(conn, unit_name, co_name, player, min_rating)
                if pair.get("total_games", 0) >= min_samples:
                    pair_consensus = classify_consensus(
                        pair.get("frequency", 0), strong_threshold, pair_threshold)
                    if pair_consensus != "contested":
                        pair["consensus"] = pair_consensus
                        pair["units"] = sorted([unit_name, co_name])
                        pair["player"] = player
                        pair["reason"] = f"{unit_name} single-unit contested"
                        pair_results.append(pair)

    # Count total replays at threshold
    total_replays = conn.execute(
        "SELECT COUNT(*) FROM replays WHERE p1_rating >= ? AND p2_rating >= ? AND balance_passed = 1",
        (min_rating, min_rating)
    ).fetchone()[0]

    return {
        "parameters": {
            "min_rating": min_rating,
            "min_samples": min_samples,
            "strong_threshold": strong_threshold,
            "pair_threshold": pair_threshold,
            "total_replays_at_threshold": total_replays,
        },
        "turn1_analysis": turn1_results,
        "turn2_analysis": turn2_results,
        "pair_analysis": pair_results,
    }
```

- [ ] **Step 4: Add tests for turn 2 and pair analysis**

Add to `replay_parser/tests/test_ob_analysis.py`:

```python
from replay_parser.ob_analysis import (
    analyze_unit_turn2_dd, find_co_occurring_units,
    analyze_pair_turn1, run_full_analysis,
)


def test_analyze_unit_turn2_dd(analysis_db):
    """Turn 2 analysis requires turn_state with 8D+2E for P1."""
    conn = sqlite3.connect(analysis_db)
    # Add turn 2 data: P1 with 8D+2E buys Drone+Tarsier
    for i in range(50):
        code = f"T2_{i:03d}"
        conn.execute("INSERT INTO replays VALUES (?, 2100, 2050, 0, 1, 2050)", (code,))
        conn.execute("INSERT INTO replay_units VALUES (?, 'Tarsier')", (code,))
        conn.execute("INSERT INTO turn_buys VALUES (?, 2, 0, 2, ?, ?)",
                     (code, '["Drone", "Tarsier"]', "Drone,Tarsier"))
        conn.execute("INSERT INTO turn_state VALUES (?, 2, 0, 2, 8, 0, 0, 0, 2, 0, ?, 10)",
                     (code, json.dumps({"Drone": 8, "Engineer": 2})))
    conn.commit()
    result = analyze_unit_turn2_dd(conn, "Tarsier", player=0, min_rating=2000)
    conn.close()
    assert result["total_games"] == 50
    assert result["top_buy"] == ["Drone", "Tarsier"]
    assert result["state"] == "8D+2E"


def test_run_full_analysis(analysis_db):
    conn = sqlite3.connect(analysis_db)
    result = run_full_analysis(conn, min_rating=2000, min_samples=30)
    conn.close()
    assert len(result["turn1_analysis"]) == 1  # Wild Drone only
    assert result["turn1_analysis"][0]["unit"] == "Wild Drone"
    assert result["turn1_analysis"][0]["p1"]["consensus"] == "strong"
    assert result["parameters"]["min_rating"] == 2000
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest replay_parser/tests/test_ob_analysis.py -v`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add replay_parser/ob_analysis.py replay_parser/tests/test_ob_analysis.py
git commit -m "feat: add turn 2 DD analysis, pair analysis, and full pipeline orchestrator"
```

---

## Task 3: Output Formatting

Create `ob_format.py` with report JSON, config-ready OB entries, validation, and stdout summary.

**Files:**
- Create: `replay_parser/ob_format.py`

- [ ] **Step 1: Create `ob_format.py` with `generate_ob_entries()`**

```python
"""Format OB analysis results into report JSON, config entries, and stdout summary."""
import json
from replay_parser.ob_analysis import (
    STARTING_STATES, DD_FOLLOWUP_STATES, classify_consensus,
)


def generate_ob_entries(analysis: dict) -> list[dict]:
    """Generate config.txt-ready OB entries from analysis results.

    Produces entries for strong and moderate consensus results.
    Each unit generates up to 2 turn 1 entries (P1 + P2) and
    up to 2 turn 2 entries (P1 + P2 after DD).
    """
    entries = []
    params = analysis["parameters"]
    strong = params["strong_threshold"]
    pair = params["pair_threshold"]

    # Turn 1 single-unit entries
    for item in analysis["turn1_analysis"]:
        unit = item["unit"]
        for player, key in [(0, "p1"), (1, "p2")]:
            data = item[key]
            consensus = data.get("consensus", "insufficient")
            if consensus in ("strong", "moderate"):
                freq = data["frequency"]
                games = item["games"]
                entries.append({
                    "_comment": f"{unit} (P{player+1} T1) -- {freq:.0%} consensus, {games} games, {consensus}",
                    "self": [list(t) for t in STARTING_STATES[player]],
                    "enemy": [],
                    "buyable": [unit],
                    "buy": data["top_buy"],
                })

    # Turn 2 DD follow-up entries
    for item in analysis["turn2_analysis"]:
        consensus = item.get("consensus", "insufficient")
        if consensus in ("strong", "moderate"):
            unit = item["unit"]
            player = item["player"]
            freq = item["frequency"]
            games = item["total_games"]
            entries.append({
                "_comment": f"{unit} (P{player+1} T2 after DD) -- {freq:.0%} consensus, {games} games, {consensus}",
                "self": [list(t) for t in DD_FOLLOWUP_STATES[player]],
                "enemy": [],
                "buyable": [unit],
                "buy": item["top_buy"],
            })

    # Pair entries from pair analysis
    for item in analysis["pair_analysis"]:
        consensus = item.get("consensus", "insufficient")
        if consensus in ("strong", "moderate"):
            units = item["units"]
            player = item["player"]
            freq = item["frequency"]
            games = item["total_games"]
            entries.append({
                "_comment": f"{'+'.join(units)} (P{player+1} T1) -- {freq:.0%} consensus, {games} games, {consensus}",
                "self": [list(t) for t in STARTING_STATES[player]],
                "enemy": [],
                "buyable": units,
                "buy": item["top_buy"],
            })

    return entries
```

- [ ] **Step 2: Add `validate_against_existing()`**

```python
def load_existing_ob(config_path: str) -> list[dict]:
    """Load LiveOpeningBook2 entries from config.txt.

    Config structure: {"Opening Books": {"LiveOpeningBook2": [...]}}
    """
    with open(config_path, 'r') as f:
        config = json.load(f)
    ob = config.get("Opening Books", {})
    return ob.get("LiveOpeningBook2", [])


def validate_against_existing(analysis: dict, existing_entries: list[dict]) -> dict:
    """Compare generated analysis against existing LiveOpeningBook2 entries."""
    validation = {
        "confirmed": 0,
        "contradicted": 0,
        "new": 0,
        "unmatched": 0,
        "insufficient": 0,
        "contradictions": [],
        "details": [],
    }

    # Build lookup from analysis: (buyable_key, player) -> top_buy_hash
    analysis_lookup = {}
    for item in analysis["turn1_analysis"]:
        unit = item["unit"]
        for player, key in [(0, "p1"), (1, "p2")]:
            data = item[key]
            if data.get("total_games", 0) > 0:
                analysis_lookup[(frozenset([unit]), player)] = data

    # Build turn 2 lookup: (buyable_key, player) -> data
    t2_lookup = {}
    for item in analysis.get("turn2_analysis", []):
        if item.get("total_games", 0) > 0:
            unit = item["unit"]
            player = item["player"]
            t2_lookup[(frozenset([unit]), player)] = item

    # Check each existing entry
    for entry in existing_entries:
        buyable = entry.get("buyable", [])
        self_state = dict(entry.get("self", []))
        existing_buy = entry.get("buy", [])

        # Determine player and turn from self state
        drones = self_state.get("Drone", 0)
        if drones == 6:
            player, turn = 0, 1
        elif drones == 7:
            player, turn = 1, 1
        elif drones == 8:
            player, turn = 0, 2  # P1 turn 2 after DD
        elif drones == 9:
            player, turn = 1, 2  # P2 turn 2 after DD
        else:
            # Non-standard state — can't match
            validation["unmatched"] += 1
            continue

        if not buyable:
            validation["unmatched"] += 1
            continue

        lookup_key = (frozenset(buyable), player)
        # Try turn 1 lookup first, then turn 2
        if turn == 1:
            data = analysis_lookup.get(lookup_key)
        else:
            data = t2_lookup.get(lookup_key)

        if data is None:
            # Pair condition or unit not analyzed
            if len(buyable) > 1:
                validation["unmatched"] += 1
            else:
                validation["insufficient"] += 1
            continue

        if data.get("consensus") == "insufficient":
            validation["insufficient"] += 1
            continue

        # Compare buy sequences (order-independent via buy_hash)
        existing_hash = ",".join(sorted(existing_buy))
        analysis_hash = data.get("top_buy_hash", "")

        if existing_hash == analysis_hash:
            validation["confirmed"] += 1
        else:
            validation["contradicted"] += 1
            # Find what frequency the existing buy has in our data
            existing_freq = 0.0
            for t5 in data.get("top_5", []):
                if t5["buy_hash"] == existing_hash:
                    existing_freq = t5["freq"]
                    break
            validation["contradictions"].append({
                "existing_buyable": buyable,
                "existing_buy": existing_buy,
                "expert_buy": data["top_buy"],
                "expert_freq": data["frequency"],
                "existing_freq": existing_freq,
            })

    # Count new entries (in analysis but not in existing)
    existing_buyables = set()
    for entry in existing_entries:
        buyable = entry.get("buyable", [])
        self_state = dict(entry.get("self", []))
        drones = self_state.get("Drone", 0)
        player = 0 if drones == 6 else (1 if drones == 7 else -1)
        if buyable and player >= 0:
            existing_buyables.add((frozenset(buyable), player))

    for key in analysis_lookup:
        if key not in existing_buyables:
            data = analysis_lookup[key]
            if data.get("consensus") in ("strong", "moderate"):
                validation["new"] += 1

    return validation
```

- [ ] **Step 3: Add `format_summary()` — human-readable stdout output**

```python
def build_summary(analysis: dict, entries: list[dict], validation: dict) -> str:
    """Build human-readable summary string for stdout."""
    params = analysis["parameters"]
    lines = []
    lines.append("Opening Book Analysis Report")
    lines.append(f"Rating threshold: {params['min_rating']}+ ({params['total_replays_at_threshold']:,} replays)")

    # Count categories
    strong = moderate = contested = insufficient = 0
    for item in analysis["turn1_analysis"]:
        for key in ("p1", "p2"):
            c = item[key].get("consensus", "insufficient")
            if c == "strong": strong += 1
            elif c == "moderate": moderate += 1
            elif c == "contested": contested += 1
            elif c == "insufficient": insufficient += 1

    lines.append(f"Units analyzed: {len(analysis['turn1_analysis'])}")
    lines.append("")

    # Strong consensus
    strong_items = [i for i in analysis["turn1_analysis"]
                    if i["p1"].get("consensus") == "strong" or i["p2"].get("consensus") == "strong"]
    if strong_items:
        lines.append(f"=== Turn 1 Strong Consensus (>{params['strong_threshold']:.0%}) -- {len(strong_items)} units ===")
        for item in strong_items[:20]:
            p1 = item["p1"]
            p2 = item["p2"]
            p1_str = f"P1: {_abbrev_buy(p1.get('top_buy', []))} ({p1.get('frequency', 0):.0%})"
            p2_str = f"P2: {_abbrev_buy(p2.get('top_buy', []))} ({p2.get('frequency', 0):.0%})"
            lines.append(f"  {item['unit']:<20} {p1_str}  {p2_str}  {item['games']} games")
        lines.append("")

    # Turn 2
    if analysis["turn2_analysis"]:
        t2_with_consensus = [t for t in analysis["turn2_analysis"]
                            if t.get("consensus") in ("strong", "moderate")]
        if t2_with_consensus:
            lines.append(f"=== Turn 2 After DD -- {len(t2_with_consensus)} entries ===")
            for item in t2_with_consensus[:20]:
                buy_str = _abbrev_buy(item["top_buy"])
                lines.append(f"  {item['unit']} (P{item['player']+1} {item['state']}): "
                           f"{buy_str} ({item['frequency']:.0%})  {item['total_games']} games  {item['consensus']}")
            lines.append("")

    # Pair analysis
    if analysis["pair_analysis"]:
        lines.append(f"=== Pair Analysis -- {len(analysis['pair_analysis'])} resolved ===")
        for item in analysis["pair_analysis"][:20]:
            units_str = " + ".join(item["units"])
            lines.append(f"  {units_str} P{item['player']+1}: "
                       f"{_abbrev_buy(item['top_buy'])} ({item['frequency']:.0%})  "
                       f"{item['total_games']} games  {item['consensus']}")
        lines.append("")

    # Validation
    if validation:
        lines.append("=== Validation vs LiveOpeningBook2 ===")
        lines.append(f"  Confirmed: {validation['confirmed']}  "
                   f"Contradicted: {validation['contradicted']}  "
                   f"New: {validation['new']}  "
                   f"Unmatched: {validation['unmatched']}  "
                   f"Insufficient: {validation['insufficient']}")
        if validation["contradictions"]:
            lines.append("  Contradictions:")
            for c in validation["contradictions"]:
                lines.append(f"    {c['existing_buyable']}: existing={_abbrev_buy(c['existing_buy'])}, "
                           f"expert={_abbrev_buy(c['expert_buy'])} ({c['expert_freq']:.0%})")
        lines.append("")

    lines.append(f"Generated {len(entries)} OB entries")
    return "\n".join(lines)


def _abbrev_buy(buy_list: list[str]) -> str:
    """Abbreviate a buy list for display: ['Drone', 'Engineer', 'Wild Drone'] -> 'D+E+WDr'."""
    # Base set units get single letters; Dominion units get 3-char abbreviations
    # to avoid ambiguity (e.g., "Wall" vs "Wild Drone", "Drone" vs "Doomed Drone")
    abbrevs = {
        "Drone": "D", "Engineer": "E", "Conduit": "C", "Blastforge": "B",
        "Animus": "A", "Wall": "W", "Tarsier": "T", "Rhino": "R",
        "Steelsplitter": "SS", "Forcefield": "FF", "Gauss Cannon": "GC",
    }
    parts = [abbrevs.get(name, name[:3]) for name in buy_list] if buy_list else ["(none)"]
    return "+".join(parts)
```

- [ ] **Step 4: Add `build_report()` — full report JSON**

```python
def build_report(analysis: dict, entries: list[dict], validation: dict) -> dict:
    """Build the full analysis report dict."""
    # Compute summary counts
    strong = moderate = contested = insufficient = 0
    for item in analysis["turn1_analysis"]:
        for key in ("p1", "p2"):
            c = item[key].get("consensus", "insufficient")
            if c == "strong": strong += 1
            elif c == "moderate": moderate += 1
            elif c == "contested": contested += 1
            elif c == "insufficient": insufficient += 1

    t1_entries = sum(1 for e in entries if "T1" in e.get("_comment", ""))
    t2_entries = sum(1 for e in entries if "T2" in e.get("_comment", ""))

    return {
        "parameters": analysis["parameters"],
        "summary": {
            "units_analyzed": len(analysis["turn1_analysis"]),
            "units_strong_consensus": strong,
            "units_moderate_consensus": moderate,
            "units_contested": contested,
            "units_insufficient_data": insufficient,
            "pairs_analyzed": len(analysis["pair_analysis"]),
            "pairs_resolved": sum(1 for p in analysis["pair_analysis"]
                                 if p.get("consensus") in ("strong", "moderate")),
            "turn1_entries_generated": t1_entries,
            "turn2_entries_generated": t2_entries,
            "total_entries_generated": len(entries),
        },
        "turn1_analysis": analysis["turn1_analysis"],
        "turn2_analysis": analysis["turn2_analysis"],
        "pair_analysis": analysis["pair_analysis"],
        "validation": validation,
    }
```

- [ ] **Step 5: Commit**

```bash
git add replay_parser/ob_format.py
git commit -m "feat: add OB output formatting — report JSON, config entries, validation, summary"
```

---

## Task 4: CLI Entry Point

Wire everything together with argparse.

**Files:**
- Modify: `replay_parser/ob_analysis.py`

- [ ] **Step 1: Add CLI entry point to `ob_analysis.py`**

```python
def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Analyze expert replays to generate opening book entries"
    )
    parser.add_argument("--db", required=True, help="Path to replays.db")
    parser.add_argument("--min-rating", type=int, default=2000,
                        help="Minimum rating for both players (default: 2000)")
    parser.add_argument("--min-samples", type=int, default=30,
                        help="Minimum games per unit (default: 30)")
    parser.add_argument("--strong-threshold", type=float, default=0.60,
                        help="Consensus >= this is 'strong' (default: 0.60)")
    parser.add_argument("--pair-threshold", type=float, default=0.40,
                        help="Consensus < this triggers pair analysis (default: 0.40)")
    parser.add_argument("--units", help="Comma-separated unit names to analyze")
    parser.add_argument("--report", help="Save analysis report JSON to this path")
    parser.add_argument("--config", help="Save config-ready OB entries to this path")
    parser.add_argument("--config-txt",
                        default="bin/asset/config/config.txt",
                        help="Path to config.txt for validation (default: bin/asset/config/config.txt)")
    args = parser.parse_args()

    unit_filter = None
    if args.units:
        unit_filter = [u.strip() for u in args.units.split(",")]

    conn = sqlite3.connect(args.db)

    # Run analysis
    analysis = run_full_analysis(
        conn, min_rating=args.min_rating, min_samples=args.min_samples,
        strong_threshold=args.strong_threshold,
        pair_threshold=args.pair_threshold,
        unit_filter=unit_filter,
    )

    # Format outputs
    from replay_parser.ob_format import (
        generate_ob_entries, validate_against_existing,
        load_existing_ob, build_summary, build_report,
    )

    entries = generate_ob_entries(analysis)

    # Validation
    validation = {}
    try:
        existing = load_existing_ob(args.config_txt)
        validation = validate_against_existing(analysis, existing)
    except FileNotFoundError:
        logger.warning("config.txt not found at %s — skipping validation", args.config_txt)

    # Print summary to stdout
    summary = build_summary(analysis, entries, validation)
    print(summary)

    # Save report if requested
    if args.report:
        report = build_report(analysis, entries, validation)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {args.report}")

    # Save config entries if requested
    if args.config:
        with open(args.config, "w") as f:
            json.dump(entries, f, indent=2)
        print(f"Config entries saved to {args.config}")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test on live DB**

```bash
cd c:/libraries/PrismataAI
python -m replay_parser.ob_analysis --db c:/libraries/prismata-replay-parser/replays.db --units "Wild Drone,Tarsier"
```

Expected: stdout summary showing Wild Drone and Tarsier analysis with consensus labels, turn 2 data, and validation results.

- [ ] **Step 3: Full run with file output**

```bash
python -m replay_parser.ob_analysis \
    --db c:/libraries/prismata-replay-parser/replays.db \
    --report ob_report.json --config ob_entries.json
```

Expected: Full analysis, report and config files created. Inspect `ob_entries.json` — should contain OB entries with correct `self`/`buyable`/`buy` format.

- [ ] **Step 4: Commit**

```bash
git add replay_parser/ob_analysis.py
git commit -m "feat: add CLI entry point for OB analysis tool"
```

---

## Task 5: End-to-End Validation

Run the tool on the full dataset and verify results make sense.

**Files:** No code changes — validation only.

- [ ] **Step 1: Run full analysis at 2000+ rating**

```bash
python -m replay_parser.ob_analysis \
    --db c:/libraries/prismata-replay-parser/replays.db \
    --report ob_report_2000.json --config ob_entries_2000.json
```

Inspect the summary output. Check:
- Number of units analyzed should be ~80-95 (most Dominion units appear at 2000+)
- Strong consensus units should include obvious ones (Wild Drone, Doomed Drone)
- Turn 2 entries should include Blastforge (matching existing BlueTurnTwoOpeningBook)
- Validation should show some confirmed matches against LiveOpeningBook2

- [ ] **Step 2: Spot-check generated OB entries**

```bash
python -c "
import json
with open('ob_entries_2000.json') as f:
    entries = json.load(f)
print(f'Total entries: {len(entries)}')
for e in entries[:5]:
    print(f'  {e[\"buyable\"]} -> {e[\"buy\"]}  ({e[\"_comment\"]})')
"
```

Verify format is correct and buyable/buy make game sense.

- [ ] **Step 3: Compare with lower threshold**

```bash
python -m replay_parser.ob_analysis \
    --db c:/libraries/prismata-replay-parser/replays.db \
    --min-rating 1800 --report ob_report_1800.json
```

Should have more data per unit, potentially different consensus for edge cases. Compare key numbers against the 2000+ run.

- [ ] **Step 4: Clean up output files**

```bash
rm -f ob_report_2000.json ob_entries_2000.json ob_report_1800.json
```
