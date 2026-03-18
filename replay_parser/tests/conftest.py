import pytest
import gzip
import json
import os
import sqlite3
import tempfile

# Path to a known test replay
TEST_REPLAY_CODE = "++A4h-1QDmB"
REPLAYS_ARCHIVE = "c:/libraries/prismata-replay-parser/replays_archive"
TEST_REPLAY_PATH = os.path.join(REPLAYS_ARCHIVE, f"{TEST_REPLAY_CODE}.json.gz")

@pytest.fixture
def raw_replay_data():
    """Load the raw JSON from test replay file."""
    if not os.path.exists(TEST_REPLAY_PATH):
        pytest.skip(f"Test replay not found: {TEST_REPLAY_PATH}")
    with gzip.open(TEST_REPLAY_PATH, 'rt') as f:
        return json.load(f)

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with the replays table schema."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
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
    conn.commit()
    conn.close()  # Close setup connection before yielding (tests open their own)
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass  # Windows may still hold the file briefly
