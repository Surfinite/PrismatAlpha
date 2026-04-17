"""Verify which replays are rated by checking ratingInfo in S3 JSON files.

Reads local .json.gz replay files, extracts ratingInfo.ratingChanges,
and updates the replays table with p1_rating_change, p2_rating_change,
and rating_verified flag.

Usage:
    python -m replay_parser.verify_rated --db <path> --replays-dir <dir> [--limit N]
"""
import argparse
import gzip
import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_rating_changes(filepath: Path) -> dict | None:
    """Extract rating changes from a replay .json.gz file.

    Returns dict with p1_rating_change, p2_rating_change if ratingInfo exists,
    or None if the file has no ratingInfo (unrated game).
    """
    try:
        with gzip.open(filepath, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except (gzip.BadGzipFile, json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", filepath, e)
        return None

    rating_info = data.get("ratingInfo")
    if not rating_info:
        return None

    changes = rating_info.get("ratingChanges")
    if not changes or len(changes) < 2:
        return None

    # ratingChanges[player][0] = display rating change
    # ratingChanges[player][1] = shalevU change (not needed)
    p1_change = changes[0][0] if isinstance(changes[0], list) and len(changes[0]) > 0 else None
    p2_change = changes[1][0] if isinstance(changes[1], list) and len(changes[1]) > 0 else None

    if p1_change is None and p2_change is None:
        return None

    return {"p1_rating_change": p1_change, "p2_rating_change": p2_change}


def verify_replays(db_path: str, replays_dir: str, limit: int | None = None) -> dict:
    """Scan unchecked replays, extract rating data, update DB.

    Returns stats dict with counts.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")

    # Find replays that haven't been verified yet
    query = "SELECT code FROM replays WHERE rating_verified = 0"
    if limit:
        query += f" LIMIT {limit}"
    codes = [row[0] for row in conn.execute(query).fetchall()]

    logger.info("Found %d unverified replays", len(codes))

    stats = {"total": len(codes), "rated": 0, "unrated": 0, "missing_file": 0, "errors": 0}
    batch = []

    for i, code in enumerate(codes):
        filepath = Path(replays_dir) / f"{code}.json.gz"
        if not filepath.exists():
            stats["missing_file"] += 1
            continue

        result = extract_rating_changes(filepath)
        if result is None:
            # File exists but no ratingInfo — unrated
            batch.append((None, None, -1, code))
            stats["unrated"] += 1
        else:
            batch.append((result["p1_rating_change"], result["p2_rating_change"], 1, code))
            stats["rated"] += 1

        # Commit in batches of 500
        if len(batch) >= 500:
            _flush_batch(conn, batch)
            batch = []
            logger.info(
                "Progress: %d/%d (rated=%d, unrated=%d, missing=%d)",
                i + 1, len(codes), stats["rated"], stats["unrated"], stats["missing_file"],
            )

    if batch:
        _flush_batch(conn, batch)

    conn.close()
    logger.info(
        "Done: %d rated, %d unrated, %d missing file, %d errors",
        stats["rated"], stats["unrated"], stats["missing_file"], stats["errors"],
    )
    return stats


def _flush_batch(conn: sqlite3.Connection, batch: list[tuple]) -> None:
    """Write a batch of rating updates to the DB."""
    with conn:
        conn.executemany(
            """UPDATE replays SET
                p1_rating_change = COALESCE(p1_rating_change, ?),
                p2_rating_change = COALESCE(p2_rating_change, ?),
                rating_verified = ?
            WHERE code = ?""",
            batch,
        )


def main():
    parser = argparse.ArgumentParser(description="Verify rated status of replays")
    parser.add_argument("--db", required=True, help="Path to replays.db")
    parser.add_argument("--replays-dir", required=True, help="Path to replays archive")
    parser.add_argument("--limit", type=int, help="Max replays to check")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    stats = verify_replays(args.db, args.replays_dir, args.limit)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
