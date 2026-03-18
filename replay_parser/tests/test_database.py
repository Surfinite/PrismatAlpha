import sqlite3
import json
from replay_parser.database import migrate, store, SCHEMA_VERSION
from replay_parser.models import (
    ReplayData, Turn, Action, ResourcePool, CardDef
)


def test_migrate_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "replay_parse_status" in tables
    assert "turn_actions" in tables
    assert "turn_state" in tables
    assert "turn_buys" in tables
    conn.close()


def test_migrate_sets_version(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    version = conn.execute(
        "SELECT value FROM db_meta WHERE key='parser_schema_version'"
    ).fetchone()[0]
    assert version == str(SCHEMA_VERSION)
    conn.close()


def test_migrate_idempotent(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    migrate(conn)  # Should not error
    conn.close()


def test_store_and_query(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating) "
        "VALUES (?, ?, ?, ?)",
        ("TEST001", 0, 1, 1600.0)
    )
    replay = _make_test_replay("TEST001")
    store(conn, replay)

    row = conn.execute(
        "SELECT parsed, total_turns FROM replay_parse_status WHERE code='TEST001'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 2

    buys = conn.execute(
        "SELECT buy_sequence, buy_hash FROM turn_buys WHERE code='TEST001' ORDER BY global_turn"
    ).fetchall()
    assert len(buys) == 2

    conn.close()


def _make_test_replay(code):
    t0 = Turn(
        global_turn=0, player=0, player_turn=1,
        buys=["Drone", "Drone"],
        abilities_used=["Drone"],
        resources_at_start=ResourcePool(energy=2),
        resources_after=ResourcePool(),
        units_owned={"Drone": 6, "Engineer": 2}
    )
    t1 = Turn(
        global_turn=1, player=1, player_turn=1,
        buys=["Drone", "Drone"],
        abilities_used=["Drone"],
        resources_at_start=ResourcePool(energy=2),
        resources_after=ResourcePool(),
        units_owned={"Drone": 7, "Engineer": 2}
    )
    return ReplayData(
        code=code, result=0, card_defs=[],
        randomizer=[], init_cards=[[(6, "Drone"), (2, "Engineer")],
                                    [(7, "Drone"), (2, "Engineer")]],
        turns=[t0, t1], total_global_turns=2,
        start_time=None, player_names=["Alice", "Bob"]
    )
