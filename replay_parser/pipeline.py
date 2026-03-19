"""Pipeline orchestrator: fetch -> JS extract -> ingest."""
import json
import logging
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from replay_parser.database import migrate, ingest, PARSER_VERSION_JS
from replay_parser.fetch import code_to_filename

logger = logging.getLogger(__name__)

JS_BULK_EXTRACT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "js_engine", "bulk_extract.js"
)


def run_js_extraction(codes, replays_dir):
    """Spawn node bulk_extract.js and yield parsed JSON entries.

    Writes codes to a temp file, runs the JS extractor in batch mode,
    and yields one dict per JSONL line from stdout.

    CRITICAL: stderr goes to a temp FILE (not subprocess.PIPE) to avoid
    deadlock when the stderr buffer fills while we read stdout line-by-line.
    """
    fd, codes_file = tempfile.mkstemp(suffix='.txt')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(codes) + '\n')

        stderr_fd, stderr_file = tempfile.mkstemp(suffix='.log')
        try:
            stderr_fh = os.fdopen(stderr_fd, 'w')
            proc = subprocess.Popen(
                ['node', JS_BULK_EXTRACT, '--batch', codes_file,
                 '--replays-dir', replays_dir],
                stdout=subprocess.PIPE, stderr=stderr_fh,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    yield json.loads(line)
            proc.wait()
            stderr_fh.close()
            # Log stderr contents
            with open(stderr_file, 'r') as f:
                for err_line in f:
                    if err_line.strip():
                        logger.info("[JS] %s", err_line.strip())
        finally:
            try:
                os.unlink(stderr_file)
            except OSError:
                pass
    finally:
        try:
            os.unlink(codes_file)
        except OSError:
            pass


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
                    logger.warning("Failed to fetch %s: %s", code, e)

    # Run JS extraction and ingest results
    for entry in run_js_extraction(codes, replays_dir):
        code = entry.get("code", "unknown")
        if entry.get("error"):
            _mark_error(conn, code, entry["error"])
            stats["errors"] += 1
            continue
        try:
            ingest(conn, entry)
            stats["parsed"] += 1
        except Exception as e:
            logger.warning("Error ingesting %s: %s", code, e)
            _mark_error(conn, code, str(e))
            stats["errors"] += 1

    conn.commit()
    conn.close()

    logger.info(
        "Done: %d parsed, %d skipped, %d errors out of %d",
        stats['parsed'], stats['skipped'], stats['errors'], stats['total']
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
        "INSERT OR REPLACE INTO replay_parse_status "
        "(code, parsed, error, parse_date, parser_version) "
        "VALUES (?, 0, ?, datetime('now'), ?)",
        (code, error_msg, PARSER_VERSION_JS)
    )
    conn.commit()
