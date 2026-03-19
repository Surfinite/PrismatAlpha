import sqlite3
import json
from replay_parser.database import migrate, store, ingest, SCHEMA_VERSION, PARSER_VERSION_JS
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


def test_ingest_from_json(temp_db):
    """Test ingesting JS extraction JSON output into the database."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    # Insert a replay row for FK constraints
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating) "
        "VALUES (?, ?, ?, ?)",
        ("JS_TEST01", 0, 1, 1600.0)
    )
    conn.commit()

    entry = {
        "code": "JS_TEST01",
        "result": 0,
        "totalTurns": 2,
        "error": None,
        "turns": [
            {
                "global_turn": 0,
                "player": 0,
                "player_turn": 1,
                "buys": ["Drone", "Drone"],
                "resources": {"gold": 6, "green": 0, "blue": 0, "red": 0, "energy": 2, "attack": 0},
                "units_owned": {"Drone": 6, "Engineer": 2},
                "total_units": 8,
                "actions": [
                    {"type": "commit"},
                    {"type": "ability", "unit": "Drone", "count": 1},
                    {"type": "buy", "unit": "Drone", "count": 1},
                    {"type": "buy", "unit": "Drone", "count": 1},
                ],
                "verification": {"consistent": True}
            },
            {
                "global_turn": 1,
                "player": 1,
                "player_turn": 1,
                "buys": ["Drone", "Drone", "Drone"],
                "resources": {"gold": 7, "green": 0, "blue": 0, "red": 0, "energy": 2, "attack": 0},
                "units_owned": {"Drone": 7, "Engineer": 2},
                "total_units": 9,
                "actions": [
                    {"type": "commit"},
                    {"type": "buy_shift", "unit": "Drone", "count": 3},
                ],
                "verification": {"consistent": True}
            },
        ]
    }

    ingest(conn, entry)

    # Verify replay_parse_status
    row = conn.execute(
        "SELECT parsed, parser_version, total_turns FROM replay_parse_status WHERE code='JS_TEST01'"
    ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == PARSER_VERSION_JS
    assert row[2] == 2

    # Verify turn_buys
    buys = conn.execute(
        "SELECT global_turn, player, buy_sequence, buy_hash FROM turn_buys "
        "WHERE code='JS_TEST01' ORDER BY global_turn"
    ).fetchall()
    assert len(buys) == 2
    # Turn 0: P0 buys ["Drone", "Drone"]
    assert buys[0][0] == 0
    assert buys[0][1] == 0
    assert json.loads(buys[0][2]) == ["Drone", "Drone"]
    assert buys[0][3] == "Drone,Drone"
    # Turn 1: P1 buys ["Drone", "Drone", "Drone"]
    assert buys[1][0] == 1
    assert buys[1][1] == 1
    assert json.loads(buys[1][2]) == ["Drone", "Drone", "Drone"]
    assert buys[1][3] == "Drone,Drone,Drone"

    # Verify turn_state
    states = conn.execute(
        "SELECT global_turn, player, gold, energy, units_owned, total_units FROM turn_state "
        "WHERE code='JS_TEST01' ORDER BY global_turn"
    ).fetchall()
    assert len(states) == 2
    assert states[0][0] == 0  # global_turn
    assert states[0][1] == 0  # player
    assert states[0][2] == 6  # gold
    assert states[0][3] == 2  # energy
    assert json.loads(states[0][4]) == {"Drone": 6, "Engineer": 2}
    assert states[0][5] == 8  # total_units
    assert states[1][2] == 7  # P1 gold
    assert states[1][5] == 9  # P1 total_units

    # Verify turn_actions
    actions = conn.execute(
        "SELECT global_turn, action_index, action_type, unit_name, quantity, deck_index, instance_id "
        "FROM turn_actions WHERE code='JS_TEST01' ORDER BY global_turn, action_index"
    ).fetchall()
    assert len(actions) == 6  # 4 from turn 0, 2 from turn 1
    # Turn 0, action 0: commit (no unit)
    assert actions[0][2] == "commit"
    assert actions[0][3] is None
    # Turn 0, action 1: ability Drone
    assert actions[1][2] == "ability"
    assert actions[1][3] == "Drone"
    assert actions[1][4] == 1
    # Turn 0, action 2: buy Drone
    assert actions[2][2] == "buy"
    assert actions[2][3] == "Drone"
    # Turn 1, action 1: buy_shift Drone count=3
    assert actions[5][2] == "buy_shift"
    assert actions[5][3] == "Drone"
    assert actions[5][4] == 3
    # deck_index and instance_id should be NULL
    assert actions[0][5] is None
    assert actions[0][6] is None

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
