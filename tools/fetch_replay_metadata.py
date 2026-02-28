#!/usr/bin/env python
"""Fetch replay metadata from S3 for codes that lack it in the replay DB."""
import sqlite3
import json
import gzip
import time

DB_PATH = r'c:\libraries\prismata-replay-parser\replays.db'


def fetch_one(code):
    """Fetch replay from S3 using curl (works in background shells where urllib fails)."""
    import subprocess
    encoded = code.replace('+', '%2B').replace('@', '%40')
    url = f'http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{encoded}.json.gz'
    for attempt in range(2):
        try:
            result = subprocess.run(
                ['curl', '-sS', '-m', '15', url],
                capture_output=True, timeout=20,
            )
            if result.returncode != 0 or not result.stdout:
                if attempt == 0:
                    time.sleep(2)
                continue

            data = gzip.decompress(result.stdout)
            replay = json.loads(data)

            pi = replay.get('playerInfo', [None, None])
            ri = replay.get('ratingInfo', {})
            di = replay.get('deckInfo', {})

            # playerInfo: list of dicts (new) or dict with playerNames (old)
            if isinstance(pi, list):
                p1_name = pi[0].get('displayName') if isinstance(pi[0], dict) else None
                p2_name = pi[1].get('displayName') if isinstance(pi[1], dict) else None
            elif isinstance(pi, dict):
                names = pi.get('playerNames', [None, None])
                p1_name = names[0] if len(names) > 0 else None
                p2_name = names[1] if len(names) > 1 else None
            else:
                p1_name, p2_name = None, None

            init_ratings = ri.get('initialRatings', [None, None])
            # initialRatings dicts may have 'displayRating' (new) or 'dominionELO' (old)
            def _get_rating(r):
                if not isinstance(r, dict):
                    return None
                return r.get('displayRating') or r.get('dominionELO')
            p1_rating = _get_rating(init_ratings[0]) if len(init_ratings) > 0 else None
            p2_rating = _get_rating(init_ratings[1]) if len(init_ratings) > 1 else None

            # ratingChanges can be dict (rated) or list (unrated) — handle both
            rc = ri.get('ratingChanges', [None, None])
            p1_rc = None
            p2_rc = None
            if isinstance(rc[0], dict) and isinstance(init_ratings[0], dict):
                p1_rc = rc[0].get('displayRating') - init_ratings[0].get('displayRating')
            if isinstance(rc[1], dict) and isinstance(init_ratings[1], dict):
                p2_rc = rc[1].get('displayRating') - init_ratings[1].get('displayRating')

            merged = di.get('mergedDeck', [])
            deck_names = [u.get('UIName', u.get('name', ''))
                          for u in merged if not u.get('baseSet')]
            deck_json = json.dumps(deck_names) if deck_names else None

            return {
                'p1_name': p1_name, 'p2_name': p2_name,
                'p1_rating': p1_rating, 'p2_rating': p2_rating,
                'p1_rating_change': p1_rc, 'p2_rating_change': p2_rc,
                'result': replay.get('result'), 'deck': deck_json,
                'start_time': replay.get('startTime'),
                'end_time': replay.get('endTime'),
                'format': replay.get('format'),
                'end_condition': replay.get('endCondition'),
            }
        except Exception:
            if attempt == 0:
                time.sleep(2)
    return 'error'


def update_db(cur, code, result):
    """Update a single replay record with fetched metadata."""
    cur.execute('''
        UPDATE replays SET
            p1_name = COALESCE(?, p1_name),
            p2_name = COALESCE(?, p2_name),
            p1_rating = COALESCE(?, p1_rating),
            p2_rating = COALESCE(?, p2_rating),
            p1_rating_change = COALESCE(?, p1_rating_change),
            p2_rating_change = COALESCE(?, p2_rating_change),
            result = COALESCE(?, result),
            deck = COALESCE(?, deck),
            start_time = COALESCE(?, start_time),
            end_time = COALESCE(?, end_time),
            format = COALESCE(?, format),
            end_condition = COALESCE(?, end_condition)
        WHERE code = ?
    ''', (
        result['p1_name'], result['p2_name'],
        result['p1_rating'], result['p2_rating'],
        result['p1_rating_change'], result['p2_rating_change'],
        result['result'], result['deck'],
        result['start_time'], result['end_time'],
        result['format'], result['end_condition'],
        code,
    ))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=0, help='0 = all')
    parser.add_argument('--delay', type=float, default=0.2)
    parser.add_argument('--query', default="p1_name IS NULL AND sources LIKE '%getreplays%'")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"SELECT code FROM replays WHERE {args.query}")
    all_codes = [row[0] for row in cur.fetchall()]

    codes = all_codes[args.offset:]
    if args.limit > 0:
        codes = codes[:args.limit]
    print(f'Fetching {len(codes)} codes (offset={args.offset}, delay={args.delay}s)...', flush=True)

    success = 0
    errors = 0
    not_found = 0

    for i, code in enumerate(codes):
        result = fetch_one(code)
        if result is None:
            not_found += 1
        elif result == 'error':
            errors += 1
        else:
            update_db(cur, code, result)
            success += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f'  {i+1}/{len(codes)}: {success} ok, {not_found} 404, {errors} err',
                  flush=True)

        time.sleep(args.delay)

    conn.commit()
    remaining = cur.execute(
        "SELECT COUNT(*) FROM replays WHERE p1_name IS NULL AND sources LIKE '%getreplays%'"
    ).fetchone()[0]
    total = cur.execute('SELECT COUNT(*) FROM replays').fetchone()[0]
    with_meta = cur.execute(
        'SELECT COUNT(*) FROM replays WHERE p1_name IS NOT NULL'
    ).fetchone()[0]
    print(f'\nDone: {success} ok, {not_found} 404, {errors} errors')
    print(f'DB: {total:,} total, {with_meta:,} with metadata, {remaining} still without')
    conn.close()


if __name__ == '__main__':
    main()
