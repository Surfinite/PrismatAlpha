import json
import sqlite3
import os
from replay_parser.pipeline import run_pipeline
from replay_parser.database import migrate, PARSER_VERSION_JS

TEST_REPLAY_CODE = "++A4h-1QDmB"
REPLAYS_ARCHIVE = "c:/libraries/prismata-replay-parser/replays_archive"
TEST_REPLAY_PATH = os.path.join(REPLAYS_ARCHIVE, f"{TEST_REPLAY_CODE}.json.gz")

import pytest
needs_replay = pytest.mark.skipif(
    not os.path.exists(TEST_REPLAY_PATH),
    reason="Test replay not found"
)


@needs_replay
def test_pipeline_single_replay(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()
    conn.close()

    stats = run_pipeline(
        db_path=temp_db,
        replays_dir=REPLAYS_ARCHIVE,
        codes=[TEST_REPLAY_CODE]
    )
    assert stats["parsed"] == 1
    assert stats["errors"] == 0

    conn = sqlite3.connect(temp_db)
    turns = conn.execute(
        "SELECT COUNT(*) FROM turn_buys WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert turns > 0

    parsed = conn.execute(
        "SELECT parsed FROM replay_parse_status WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert parsed == 1

    # Verify parser_version is PARSER_VERSION_JS (2)
    parser_version = conn.execute(
        "SELECT parser_version FROM replay_parse_status WHERE code=?",
        (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert parser_version == PARSER_VERSION_JS

    # Verify turn_actions are populated
    action_count = conn.execute(
        "SELECT COUNT(*) FROM turn_actions WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert action_count > 0

    conn.close()


@needs_replay
def test_pipeline_incremental(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()
    conn.close()

    stats1 = run_pipeline(db_path=temp_db, replays_dir=REPLAYS_ARCHIVE,
                          codes=[TEST_REPLAY_CODE])
    stats2 = run_pipeline(db_path=temp_db, replays_dir=REPLAYS_ARCHIVE,
                          codes=[TEST_REPLAY_CODE])
    assert stats1["parsed"] == 1
    assert stats2["skipped"] == 1
    assert stats2["parsed"] == 0


@needs_replay
def test_p1_turn1_starting_state(temp_db):
    """Verify P1 turn 1 starting state is 6 Drones + 2 Engineers."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()
    conn.close()

    stats = run_pipeline(
        db_path=temp_db,
        replays_dir=REPLAYS_ARCHIVE,
        codes=[TEST_REPLAY_CODE]
    )
    assert stats["parsed"] == 1

    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT units_owned FROM turn_state WHERE code=? AND global_turn=0",
        (TEST_REPLAY_CODE,)
    ).fetchone()
    assert row is not None
    units = json.loads(row[0])
    assert units == {"Drone": 6, "Engineer": 2}
    conn.close()
