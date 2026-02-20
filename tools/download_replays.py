#!/usr/bin/env python3
"""
Download expert replay JSONs from S3 for C++ replay ingestion.

Usage:
    python tools/download_replays.py \
        --codes c:/libraries/prismata-replay-parser/expert_replays.json \
        --output-dir replays/ \
        --min-rating 2000 \
        --threads 10 \
        --limit 1000

Downloads replay JSONs from:
    saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz

Uses expert_replays.json (key format: Code, P1RatingIni, P2RatingIni)
for the code list and rating filter. Skips already-downloaded files.
"""

import argparse
import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://saved-games-alpha.s3-website-us-east-1.amazonaws.com"


def encode_code(code):
    """URL-encode replay code (+ -> %2B, @ -> %40, etc.)."""
    return urllib.parse.quote(code, safe="")


def download_replay(code, output_dir):
    """Download and decompress a single replay. Returns (code, success, error)."""
    safe_filename = code.replace("+", "_plus_").replace("@", "_at_").replace("/", "_slash_")
    output_path = os.path.join(output_dir, safe_filename + ".json")

    # Skip if already downloaded
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return (code, True, "skipped")

    encoded = encode_code(code)
    url = f"{BASE_URL}/{encoded}.json.gz"

    try:
        req = urllib.request.Request(url)
        req.add_header("Accept-Encoding", "identity")
        with urllib.request.urlopen(req, timeout=30) as resp:
            compressed = resp.read()

        # Decompress gzip
        data = gzip.decompress(compressed)

        # Validate it's valid JSON
        json.loads(data)

        # Write to output
        with open(output_path, "wb") as f:
            f.write(data)

        return (code, True, None)

    except Exception as e:
        return (code, False, str(e))


def main():
    parser = argparse.ArgumentParser(description="Download expert replay JSONs from S3")
    parser.add_argument("--codes", required=True,
                        help="Path to expert_replays.json (or file with one code per line)")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to save replay JSONs")
    parser.add_argument("--min-rating", type=int, default=0,
                        help="Minimum rating filter (both players must meet)")
    parser.add_argument("--threads", type=int, default=10,
                        help="Number of download threads")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max replays to download (0=all)")
    args = parser.parse_args()

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Load codes
    codes_path = args.codes
    codes = []

    if codes_path.endswith(".json"):
        with open(codes_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    code = entry.get("Code", entry.get("code", ""))
                    if not code:
                        continue

                    # Rating filter
                    if args.min_rating > 0:
                        r1 = entry.get("P1RatingIni", entry.get("p1RatingIni", 0))
                        r2 = entry.get("P2RatingIni", entry.get("p2RatingIni", 0))
                        if min(r1, r2) < args.min_rating:
                            continue

                    codes.append(code)
                elif isinstance(entry, str):
                    codes.append(entry)
    else:
        # Plain text file with one code per line
        with open(codes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    codes.append(line)

    if args.limit > 0:
        codes = codes[:args.limit]

    print(f"Codes to download: {len(codes)}")
    print(f"Output directory:  {args.output_dir}")
    print(f"Threads:           {args.threads}")
    if args.min_rating > 0:
        print(f"Min rating:        {args.min_rating}")

    # Download with thread pool
    success = 0
    skipped = 0
    failed = 0
    errors = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(download_replay, code, args.output_dir): code
                   for code in codes}

        for future in as_completed(futures):
            code, ok, err = future.result()
            if ok:
                if err == "skipped":
                    skipped += 1
                else:
                    success += 1
            else:
                failed += 1
                errors.append((code, err))

            total_done = success + skipped + failed
            if total_done % 100 == 0 or total_done == len(codes):
                elapsed = time.time() - start_time
                rate = total_done / elapsed if elapsed > 0 else 0
                print(f"  [{total_done}/{len(codes)}] "
                      f"{success} new, {skipped} skipped, {failed} failed "
                      f"({rate:.0f}/s)")

    elapsed = time.time() - start_time
    print(f"\n=== Download Summary ===")
    print(f"Total codes:   {len(codes)}")
    print(f"Downloaded:    {success}")
    print(f"Skipped:       {skipped}")
    print(f"Failed:        {failed}")
    print(f"Time:          {elapsed:.1f}s")
    print(f"Output dir:    {args.output_dir}")

    if errors:
        print(f"\nFirst 10 errors:")
        for code, err in errors[:10]:
            print(f"  {code}: {err}")


if __name__ == "__main__":
    main()
