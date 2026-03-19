"""Database schema migration and storage for replay parse results."""
import json
import logging
import sqlite3
from datetime import datetime, timezone

from replay_parser.models import ReplayData

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
PARSER_VERSION_JS = 2


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any pending schema migrations to conn.

    Safe to call on an already-migrated database (idempotent).
    """
    row = conn.execute(
        "SELECT value FROM db_meta WHERE key='parser_schema_version'"
    ).fetchone()
    current = int(row[0]) if row else 0

    if current >= SCHEMA_VERSION:
        return

    if current < 1:
        _migrate_v0_to_v1(conn)

    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('parser_schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    logger.info("Database migrated to schema version %d", SCHEMA_VERSION)


def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    """Create the four parser tables and their indexes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS replay_parse_status (
            code            TEXT PRIMARY KEY REFERENCES replays(code),
            parsed          INTEGER DEFAULT 0,
            parse_date      TEXT,
            parser_version  INTEGER,
            total_turns     INTEGER,
            error           TEXT
        );

        CREATE TABLE IF NOT EXISTS turn_actions (
            code            TEXT NOT NULL REFERENCES replays(code),
            global_turn     INTEGER NOT NULL,
            player          INTEGER NOT NULL,
            player_turn     INTEGER NOT NULL,
            action_index    INTEGER NOT NULL,
            action_type     TEXT NOT NULL,
            unit_name       TEXT,
            quantity        INTEGER DEFAULT 1,
            deck_index      INTEGER,
            instance_id     INTEGER,
            PRIMARY KEY (code, global_turn, action_index)
        );

        CREATE TABLE IF NOT EXISTS turn_state (
            code            TEXT NOT NULL REFERENCES replays(code),
            global_turn     INTEGER NOT NULL,
            player          INTEGER NOT NULL,
            player_turn     INTEGER NOT NULL,
            gold            INTEGER NOT NULL DEFAULT 0,
            green           INTEGER NOT NULL DEFAULT 0,
            blue            INTEGER NOT NULL DEFAULT 0,
            red             INTEGER NOT NULL DEFAULT 0,
            energy          INTEGER NOT NULL DEFAULT 0,
            attack          INTEGER NOT NULL DEFAULT 0,
            units_owned     TEXT NOT NULL,
            total_units     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (code, global_turn)
        );

        CREATE TABLE IF NOT EXISTS turn_buys (
            code            TEXT NOT NULL REFERENCES replays(code),
            global_turn     INTEGER NOT NULL,
            player          INTEGER NOT NULL,
            player_turn     INTEGER NOT NULL,
            buy_sequence    TEXT NOT NULL,
            buy_hash        TEXT NOT NULL,
            PRIMARY KEY (code, global_turn)
        );

        CREATE INDEX IF NOT EXISTS idx_turn_buys_player_turn ON turn_buys(player, player_turn);
        CREATE INDEX IF NOT EXISTS idx_turn_buys_code_turn ON turn_buys(code, player_turn);
        CREATE INDEX IF NOT EXISTS idx_turn_actions_code ON turn_actions(code, global_turn);
        CREATE INDEX IF NOT EXISTS idx_parse_status_parsed ON replay_parse_status(parsed);
        CREATE INDEX IF NOT EXISTS idx_turn_buys_hash ON turn_buys(buy_hash, player_turn);
    """)


def store(conn: sqlite3.Connection, replay: ReplayData) -> None:
    """Persist parsed replay data into the database.

    Inserts/replaces rows in replay_parse_status, turn_actions, turn_state,
    and turn_buys.  Wrapped in a single transaction.
    """
    now = datetime.now(timezone.utc).isoformat()

    action_rows: list[tuple] = []
    state_rows: list[tuple] = []
    buy_rows: list[tuple] = []

    for turn in replay.turns:
        # turn_actions — one row per Action in the turn
        for idx, action in enumerate(turn.actions):
            action_rows.append((
                replay.code,
                turn.global_turn,
                turn.player,
                turn.player_turn,
                idx,
                action.action_type,
                action.unit_name,
                action.quantity,
                action.deck_index,
                action.instance_id,
            ))

        # turn_state
        r = turn.resources_at_start
        total_units = sum(turn.units_owned.values())
        state_rows.append((
            replay.code,
            turn.global_turn,
            turn.player,
            turn.player_turn,
            r.gold,
            r.green,
            r.blue,
            r.red,
            r.energy,
            r.attack,
            json.dumps(turn.units_owned),
            total_units,
        ))

        # turn_buys
        buy_sequence = json.dumps(turn.buys)
        buy_hash = ",".join(sorted(turn.buys))
        buy_rows.append((
            replay.code,
            turn.global_turn,
            turn.player,
            turn.player_turn,
            buy_sequence,
            buy_hash,
        ))

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO replay_parse_status "
            "(code, parsed, parse_date, parser_version, total_turns, error) "
            "VALUES (?, 1, ?, ?, ?, NULL)",
            (replay.code, now, SCHEMA_VERSION, len(replay.turns)),
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_actions "
            "(code, global_turn, player, player_turn, action_index, action_type, "
            "unit_name, quantity, deck_index, instance_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            action_rows,
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_state "
            "(code, global_turn, player, player_turn, gold, green, blue, red, "
            "energy, attack, units_owned, total_units) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            state_rows,
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_buys "
            "(code, global_turn, player, player_turn, buy_sequence, buy_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            buy_rows,
        )


def ingest(conn: sqlite3.Connection, entry: dict) -> None:
    """Persist JS extraction output into the database.

    Reads from a JSON dict (one JSONL line from bulk_extract.js) and inserts
    into replay_parse_status, turn_actions, turn_state, and turn_buys.
    """
    now = datetime.now(timezone.utc).isoformat()
    code = entry["code"]
    turns = entry["turns"]

    action_rows: list[tuple] = []
    state_rows: list[tuple] = []
    buy_rows: list[tuple] = []

    for turn in turns:
        global_turn = turn["global_turn"]
        player = turn["player"]
        player_turn = turn["player_turn"]

        # turn_actions — one row per action
        for idx, action in enumerate(turn.get("actions", [])):
            action_rows.append((
                code,
                global_turn,
                player,
                player_turn,
                idx,
                action["type"],
                action.get("unit"),
                action.get("count", 1),
                None,  # deck_index not in JS output
                None,  # instance_id not in JS output
            ))

        # turn_state
        res = turn.get("resources", {})
        units_owned = turn.get("units_owned", {})
        total_units = turn.get("total_units", sum(units_owned.values()))
        state_rows.append((
            code,
            global_turn,
            player,
            player_turn,
            res.get("gold", 0),
            res.get("green", 0),
            res.get("blue", 0),
            res.get("red", 0),
            res.get("energy", 0),
            res.get("attack", 0),
            json.dumps(units_owned),
            total_units,
        ))

        # turn_buys
        buys = turn.get("buys", [])
        buy_sequence = json.dumps(buys)
        buy_hash = ",".join(sorted(buys))
        buy_rows.append((
            code,
            global_turn,
            player,
            player_turn,
            buy_sequence,
            buy_hash,
        ))

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO replay_parse_status "
            "(code, parsed, parse_date, parser_version, total_turns, error) "
            "VALUES (?, 1, ?, ?, ?, NULL)",
            (code, now, PARSER_VERSION_JS, len(turns)),
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_actions "
            "(code, global_turn, player, player_turn, action_index, action_type, "
            "unit_name, quantity, deck_index, instance_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            action_rows,
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_state "
            "(code, global_turn, player, player_turn, gold, green, blue, red, "
            "energy, attack, units_owned, total_units) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            state_rows,
        )

        conn.executemany(
            "INSERT OR REPLACE INTO turn_buys "
            "(code, global_turn, player, player_turn, buy_sequence, buy_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            buy_rows,
        )
