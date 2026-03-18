"""Pipeline orchestrator: fetch -> decode -> simulate -> store."""
import logging
import sqlite3
from pathlib import Path

from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate
from replay_parser.database import migrate, store
from replay_parser.fetch import code_to_filename

logger = logging.getLogger(__name__)


def run_pipeline(
    db_path: str,
    replays_dir: str,
    codes: list[str] | None = None,
    force: bool = False,
    fetch: bool = False,
    batch_size: int = 1000,
) -> dict:
    """Run the parse pipeline. Returns stats dict."""
    conn = sqlite3.connect(db_path)
    migrate(conn)

    if codes is None:
        codes = _get_eligible_codes(conn, force)
        skipped = 0
    elif not force:
        original_count = len(codes)
        codes = _filter_unparsed(conn, codes)
        skipped = original_count - len(codes)
    else:
        skipped = 0

    stats = {
        "parsed": 0,
        "skipped": skipped,
        "errors": 0,
        "fetched": 0,
        "total": skipped + len(codes),
    }
    replays_path = Path(replays_dir)

    # Fetch missing replays from S3 if requested
    if fetch and codes:
        from replay_parser.fetch import fetch_replay
        for code in codes:
            if not (replays_path / code_to_filename(code)).exists():
                try:
                    fetch_replay(code, replays_path)
                    stats["fetched"] += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch {code}: {e}")

    for i, code in enumerate(codes):
        try:
            filename = code_to_filename(code)
            filepath = replays_path / filename
            if not filepath.exists():
                logger.warning(f"File not found for {code}: {filepath}")
                _mark_error(conn, code, f"File not found: {filepath}")
                stats["errors"] += 1
                continue

            raw = load_replay(str(filepath))
            replay = decode(raw)
            simulate(replay)
            store(conn, replay)
            stats["parsed"] += 1

            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.info(f"Progress: {i+1}/{len(codes)}")
        except Exception as e:
            logger.warning(f"Error parsing {code}: {e}")
            _mark_error(conn, code, str(e))
            stats["errors"] += 1

    conn.commit()
    conn.close()

    logger.info(
        f"Done: {stats['parsed']} parsed, {stats['skipped']} skipped, "
        f"{stats['errors']} errors out of {stats['total']}"
    )
    return stats


def _get_eligible_codes(conn, force):
    """Get codes eligible for parsing from the replays table."""
    if force:
        query = """
            SELECT r.code FROM replays r
            WHERE r.balance_passed = 1
              AND r.p1_rating > 1 AND r.p2_rating > 1
        """
    else:
        query = """
            SELECT r.code FROM replays r
            LEFT JOIN replay_parse_status rps ON r.code = rps.code
            WHERE r.balance_passed = 1
              AND (rps.parsed IS NULL OR rps.parsed = 0)
              AND r.p1_rating > 1 AND r.p2_rating > 1
        """
    return [row[0] for row in conn.execute(query).fetchall()]


def _filter_unparsed(conn, codes):
    """Filter out already-parsed codes. Return only unparsed ones."""
    if not codes:
        return codes
    placeholders = ",".join("?" for _ in codes)
    already_parsed = set(
        row[0] for row in conn.execute(
            f"SELECT code FROM replay_parse_status WHERE code IN ({placeholders}) AND parsed = 1",
            codes
        ).fetchall()
    )
    return [c for c in codes if c not in already_parsed]


def _mark_error(conn, code, error_msg):
    """Record a parse error in replay_parse_status."""
    conn.execute(
        "INSERT OR REPLACE INTO replay_parse_status (code, parsed, error, parse_date) "
        "VALUES (?, 0, ?, datetime('now'))",
        (code, error_msg)
    )
    conn.commit()
