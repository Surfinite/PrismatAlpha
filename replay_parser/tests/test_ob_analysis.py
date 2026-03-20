"""Tests for opening book consensus analysis."""
import json
import sqlite3
import tempfile
import os

import pytest

from replay_parser.ob_analysis import (
    BASE_SET_UNITS,
    STARTING_STATES,
    DD_FOLLOWUP_STATES,
    get_dominion_units,
    analyze_unit_turn1,
    analyze_unit_turn2_dd,
    find_co_occurring_units,
    analyze_pair_turn1,
    run_full_analysis,
    classify_consensus,
)
from replay_parser.database import migrate


@pytest.fixture
def analysis_db():
    """Build a mock SQLite DB with 100 games containing Wild Drone.

    Game distribution (all P0 = player 0, turn 1):
      - 70 games buy ["Drone", "Engineer", "Wild Drone"]
            buy_hash = "Drone,Engineer,Wild Drone"
            All 70 are P1 wins (result=0, meaning player 0 wins)
      - 30 games buy ["Drone", "Drone"]
            buy_hash = "Drone,Drone"
            20 are P2 wins (result=1), 10 are P1 wins (result=0)

    Turn 2 data (P0, player_turn=2):
      - 50 of the 70 "Wild Drone opener" games also have turn 2 data
        with 8D+2E state (post-DD), buying ["Drone", "Tarsier"]
        buy_hash = "Drone,Tarsier"
        All 50 are P1 wins (result=0)

    Also includes "Electrovore" in all 100 games for pair analysis testing.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)

    # Core tables
    conn.execute("""
        CREATE TABLE replays (
            code TEXT PRIMARY KEY,
            p1_name TEXT, p2_name TEXT,
            p1_rating REAL, p2_rating REAL,
            result INTEGER, deck TEXT,
            balance_passed INTEGER DEFAULT 1,
            min_rating REAL
        )
    """)
    conn.execute("""
        CREATE TABLE replay_units (
            code TEXT NOT NULL REFERENCES replays(code),
            unit_name TEXT NOT NULL,
            PRIMARY KEY (code, unit_name)
        )
    """)
    conn.execute("""
        CREATE TABLE db_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Apply parser schema migration (creates turn_buys, turn_state, etc.)
    migrate(conn)

    # Insert 100 replays, all 2000+ rated, balance_passed=1
    for i in range(100):
        code = f"GAME_{i:04d}"
        if i < 70:
            result = 0  # P1 (player 0) wins
        elif i < 90:
            result = 1  # P2 (player 1) wins
        else:
            result = 0  # P1 wins

        conn.execute(
            "INSERT INTO replays (code, p1_name, p2_name, p1_rating, p2_rating, "
            "result, balance_passed) VALUES (?, 'Alice', 'Bob', 2100.0, 2050.0, ?, 1)",
            (code, result),
        )

        # Every game has Wild Drone, Drone, and Electrovore in the set
        conn.execute(
            "INSERT INTO replay_units (code, unit_name) VALUES (?, 'Wild Drone')",
            (code,),
        )
        conn.execute(
            "INSERT INTO replay_units (code, unit_name) VALUES (?, 'Drone')",
            (code,),
        )
        conn.execute(
            "INSERT INTO replay_units (code, unit_name) VALUES (?, 'Electrovore')",
            (code,),
        )

    # Insert turn_buys for player 0, turn 1
    for i in range(100):
        code = f"GAME_{i:04d}"
        if i < 70:
            buy_seq = json.dumps(["Drone", "Engineer", "Wild Drone"])
            buy_hash = "Drone,Engineer,Wild Drone"
        else:
            buy_seq = json.dumps(["Drone", "Drone"])
            buy_hash = "Drone,Drone"

        conn.execute(
            "INSERT INTO turn_buys (code, global_turn, player, player_turn, "
            "buy_sequence, buy_hash) VALUES (?, 0, 0, 1, ?, ?)",
            (code, buy_seq, buy_hash),
        )

    # Insert turn 2 data for first 50 games (P0, player_turn=2)
    # These simulate post-DD state: 8 Drones + 2 Engineers
    for i in range(50):
        code = f"GAME_{i:04d}"
        buy_seq = json.dumps(["Drone", "Tarsier"])
        buy_hash = "Drone,Tarsier"

        # global_turn=2 for P0's second turn (turns go: P0-t1=0, P1-t1=1, P0-t2=2)
        conn.execute(
            "INSERT INTO turn_buys (code, global_turn, player, player_turn, "
            "buy_sequence, buy_hash) VALUES (?, 2, 0, 2, ?, ?)",
            (code, buy_seq, buy_hash),
        )

        # Corresponding turn_state with 8D+2E
        units_owned = json.dumps({"Drone": 8, "Engineer": 2})
        conn.execute(
            "INSERT INTO turn_state (code, global_turn, player, player_turn, "
            "gold, green, blue, red, energy, attack, units_owned, total_units) "
            "VALUES (?, 2, 0, 2, 8, 0, 0, 0, 0, 0, ?, 10)",
            (code, units_owned),
        )

    conn.commit()
    yield conn
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


# --- classify_consensus tests ---

def test_classify_consensus_strong():
    assert classify_consensus(0.80) == "strong"
    assert classify_consensus(0.70) == "strong"


def test_classify_consensus_moderate():
    assert classify_consensus(0.60) == "moderate"
    assert classify_consensus(0.50) == "moderate"


def test_classify_consensus_contested():
    assert classify_consensus(0.40) == "contested"
    assert classify_consensus(0.10) == "contested"
    assert classify_consensus(0.0) == "contested"


# --- Constants tests ---

def test_base_set_has_11_units():
    assert len(BASE_SET_UNITS) == 11
    assert "Drone" in BASE_SET_UNITS
    assert "Rhino" in BASE_SET_UNITS
    assert "Wild Drone" not in BASE_SET_UNITS


def test_starting_states():
    # P1 starts with 6 Drone, 2 Engineer
    assert STARTING_STATES[0] == [("Drone", 6), ("Engineer", 2)]
    # P2 starts with 7 Drone, 2 Engineer
    assert STARTING_STATES[1] == [("Drone", 7), ("Engineer", 2)]


def test_dd_followup_states():
    assert DD_FOLLOWUP_STATES[0] == [("Drone", 8), ("Engineer", 2)]
    assert DD_FOLLOWUP_STATES[1] == [("Drone", 9), ("Engineer", 2)]


# --- get_dominion_units tests ---

def test_get_dominion_units(analysis_db):
    units = get_dominion_units(analysis_db, min_rating=1500.0, min_samples=20)
    names = [u["unit_name"] for u in units]
    assert "Wild Drone" in names
    # Verify game count
    wd = next(u for u in units if u["unit_name"] == "Wild Drone")
    assert wd["game_count"] == 100


def test_get_dominion_units_excludes_base_set(analysis_db):
    units = get_dominion_units(analysis_db, min_rating=1500.0, min_samples=1)
    names = [u["unit_name"] for u in units]
    assert "Drone" not in names
    assert "Engineer" not in names


def test_get_dominion_units_min_samples(analysis_db):
    # Require more samples than exist — should return empty
    units = get_dominion_units(analysis_db, min_rating=1500.0, min_samples=200)
    assert len(units) == 0


# --- analyze_unit_turn1 tests ---

def test_analyze_unit_turn1(analysis_db):
    result = analyze_unit_turn1(analysis_db, "Wild Drone", player=0, min_rating=1500.0)

    assert result["status"] == "ok"
    assert result["total_games"] == 100
    assert result["top_buy"] == "Drone,Engineer,Wild Drone"
    assert result["sample_size"] == 70

    # frequency = 70 / 100
    assert abs(result["frequency"] - 0.70) < 1e-9

    # win_rate for top buy: 70 wins / 70 decisive games (no draws in this group)
    assert abs(result["win_rate"] - 1.0) < 1e-9

    # Runner-up exists
    assert result["runner_up"] is not None
    assert result["runner_up"]["buy_hash"] == "Drone,Drone"
    assert result["runner_up"]["sample_size"] == 30

    # Runner-up win rate: 10 wins for player 0 out of 30 decisive games
    assert abs(result["runner_up"]["win_rate"] - 10.0 / 30.0) < 1e-9

    # top_5 has 2 entries
    assert len(result["top_5"]) == 2


def test_analyze_unit_turn1_insufficient(analysis_db):
    result = analyze_unit_turn1(
        analysis_db, "Nonexistent Unit", player=0, min_rating=1500.0
    )
    assert result["status"] == "insufficient"
    assert result["total_games"] == 0
    assert result["top_buy"] is None
    assert result["runner_up"] is None
    assert result["top_5"] == []


def test_analyze_unit_turn1_wrong_player(analysis_db):
    """Player 1 has no turn_buys rows — should return insufficient."""
    result = analyze_unit_turn1(
        analysis_db, "Wild Drone", player=1, min_rating=1500.0
    )
    assert result["status"] == "insufficient"
    assert result["total_games"] == 0


# --- analyze_unit_turn2_dd tests ---

def test_analyze_unit_turn2_dd(analysis_db):
    """50 games with 8D+2E state for P1 turn 2, all buying Drone+Tarsier."""
    result = analyze_unit_turn2_dd(
        analysis_db, "Wild Drone", player=0, min_rating=1500.0
    )

    assert result["status"] == "ok"
    assert result["state"] == "8D+2E"
    assert result["total_games"] == 50
    assert result["top_buy"] == "Drone,Tarsier"
    assert result["sample_size"] == 50

    # frequency = 50 / 50 (all games have the same buy)
    assert abs(result["frequency"] - 1.0) < 1e-9

    # win_rate: all 50 are P0 wins (result=0), so 50/50
    assert abs(result["win_rate"] - 1.0) < 1e-9

    # No runner-up (only one buy hash)
    assert result["runner_up"] is None
    assert len(result["top_5"]) == 1


def test_analyze_unit_turn2_dd_insufficient(analysis_db):
    """Player 1 has no turn 2 data — should return insufficient."""
    result = analyze_unit_turn2_dd(
        analysis_db, "Wild Drone", player=1, min_rating=1500.0
    )
    assert result["status"] == "insufficient"
    assert result["state"] == "9D+2E"
    assert result["total_games"] == 0


def test_analyze_unit_turn2_dd_wrong_unit(analysis_db):
    """Non-existent unit returns insufficient with correct state label."""
    result = analyze_unit_turn2_dd(
        analysis_db, "Nonexistent Unit", player=0, min_rating=1500.0
    )
    assert result["status"] == "insufficient"
    assert result["state"] == "8D+2E"


# --- find_co_occurring_units tests ---

def test_find_co_occurring_units(analysis_db):
    """Wild Drone co-occurs with Electrovore in all 100 games."""
    co_units = find_co_occurring_units(
        analysis_db, "Wild Drone", min_rating=1500.0, limit=10
    )

    names = [u["unit_name"] for u in co_units]
    assert "Electrovore" in names

    # Base set units should be excluded
    for u in co_units:
        assert u["unit_name"] not in BASE_SET_UNITS

    ev = next(u for u in co_units if u["unit_name"] == "Electrovore")
    assert ev["co_count"] == 100


def test_find_co_occurring_units_limit(analysis_db):
    co_units = find_co_occurring_units(
        analysis_db, "Wild Drone", min_rating=1500.0, limit=1
    )
    assert len(co_units) <= 1


def test_find_co_occurring_units_nonexistent(analysis_db):
    co_units = find_co_occurring_units(
        analysis_db, "Nonexistent Unit", min_rating=1500.0, limit=10
    )
    assert co_units == []


# --- analyze_pair_turn1 tests ---

def test_analyze_pair_turn1(analysis_db):
    """Wild Drone + Electrovore pair — same data as single-unit analysis."""
    result = analyze_pair_turn1(
        analysis_db, "Wild Drone", "Electrovore", player=0, min_rating=1500.0
    )

    assert result["status"] == "ok"
    assert result["total_games"] == 100
    assert result["top_buy"] == "Drone,Engineer,Wild Drone"
    assert result["sample_size"] == 70
    assert abs(result["frequency"] - 0.70) < 1e-9


def test_analyze_pair_turn1_nonexistent_partner(analysis_db):
    """One unit doesn't exist — should return insufficient."""
    result = analyze_pair_turn1(
        analysis_db, "Wild Drone", "Nonexistent", player=0, min_rating=1500.0
    )
    assert result["status"] == "insufficient"
    assert result["total_games"] == 0


def test_analyze_pair_turn1_symmetry(analysis_db):
    """Order of unit1/unit2 shouldn't matter."""
    r1 = analyze_pair_turn1(
        analysis_db, "Wild Drone", "Electrovore", player=0, min_rating=1500.0
    )
    r2 = analyze_pair_turn1(
        analysis_db, "Electrovore", "Wild Drone", player=0, min_rating=1500.0
    )
    assert r1["total_games"] == r2["total_games"]
    assert r1["top_buy"] == r2["top_buy"]


# --- run_full_analysis tests ---

def test_run_full_analysis(analysis_db):
    """Run full pipeline on mock data; verify structure and Wild Drone result."""
    result = run_full_analysis(
        analysis_db,
        min_rating=1500.0,
        min_samples=20,
        strong_threshold=0.70,
        pair_threshold=0.50,
        unit_filter=["Wild Drone"],
    )

    # Parameters recorded
    assert result["parameters"]["min_rating"] == 1500.0
    assert result["parameters"]["min_samples"] == 20
    assert result["parameters"]["strong_threshold"] == 0.70
    assert result["parameters"]["pair_threshold"] == 0.50

    # Turn 1 analysis present
    assert "Wild Drone" in result["turn1_analysis"]
    wd_t1 = result["turn1_analysis"]["Wild Drone"]
    assert "p0" in wd_t1
    assert "p1" in wd_t1

    # P0 has strong consensus (frequency=0.70, threshold=0.70)
    assert wd_t1["p0"]["consensus"] == "strong"
    assert wd_t1["p0"]["top_buy"] == "Drone,Engineer,Wild Drone"

    # P1 has no data -> insufficient -> contested
    assert wd_t1["p1"]["consensus"] == "contested"

    # Turn 2 analysis: P0 has 50 games (>= min_samples=20)
    assert "Wild Drone" in result["turn2_analysis"]
    wd_t2 = result["turn2_analysis"]["Wild Drone"]
    assert "p0" in wd_t2
    assert wd_t2["p0"]["state"] == "8D+2E"
    assert wd_t2["p0"]["top_buy"] == "Drone,Tarsier"


def test_run_full_analysis_no_filter(analysis_db):
    """Run without unit_filter — should include all Dominion units."""
    result = run_full_analysis(
        analysis_db,
        min_rating=1500.0,
        min_samples=20,
    )

    # Both Wild Drone and Electrovore should appear
    assert "Wild Drone" in result["turn1_analysis"]
    assert "Electrovore" in result["turn1_analysis"]
