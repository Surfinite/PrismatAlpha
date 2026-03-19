#!/usr/bin/env python3
"""
Batch replay validation — samples random replay codes and validates them
through the JS engine to verify correct game state processing.

Since the viewer uses the exact same engine modules (bundled into prismata-engine.js),
this validates the same code path the replay viewer uses.

Usage:
    python js_engine/batch_validate.py                     # 100 random from eligible_1500
    python js_engine/batch_validate.py --count 1000        # 1000 random replays
    python js_engine/batch_validate.py --codes mylist.txt  # custom code list
    python js_engine/batch_validate.py --count 500 --concurrency 10
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VALIDATOR = SCRIPT_DIR / "replay_validator.js"
DEFAULT_CODES = Path("c:/libraries/prismata-replay-parser/eligible_1500_codes.txt")

# Alternative code lists
CODE_LISTS = {
    "eligible_1500": DEFAULT_CODES,
    "all_1500": SCRIPT_DIR / "all_codes_1500.json",
    "all_2000": SCRIPT_DIR / "all_codes_2000.json",
    "prepatch_1500": SCRIPT_DIR / "prepatch_safe_codes_1500.json",
}


def load_codes(path: Path) -> list[str]:
    """Load replay codes from a file (txt with one per line, or JSON array)."""
    text = path.read_text(encoding="utf-8-sig").strip()
    if text.startswith("["):
        codes = json.loads(text)
    else:
        codes = [line.strip().split("\t")[0] for line in text.splitlines()
                 if line.strip() and not line.startswith("#")]
    return [c for c in codes if c]


def sample_codes(codes: list[str], count: int, seed: int | None = None) -> list[str]:
    """Randomly sample N codes."""
    if seed is not None:
        random.seed(seed)
    if count >= len(codes):
        return codes
    return random.sample(codes, count)


def run_validation(codes: list[str], concurrency: int = 5, verbose: bool = False) -> dict:
    """Run the JS validator on a list of codes."""
    # Write codes to temp file
    tmp_file = SCRIPT_DIR / "_batch_validate_tmp.txt"
    tmp_file.write_text("\n".join(codes), encoding="utf-8")

    results_file = SCRIPT_DIR / "validation_results.json"
    # Remove old results
    if results_file.exists():
        results_file.unlink()

    cmd = ["node", str(VALIDATOR), "--batch", str(tmp_file)]
    if verbose:
        cmd.append("--verbose")

    print(f"Running validator on {len(codes)} replays (concurrency={concurrency})...")
    start = time.time()

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(SCRIPT_DIR),
            capture_output=not verbose,
            text=True,
            timeout=3600,  # 1 hour max
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        print("ERROR: Validation timed out after 1 hour")
        return {"error": "timeout"}
    finally:
        tmp_file.unlink(missing_ok=True)

    elapsed = time.time() - start

    if not results_file.exists():
        print(f"ERROR: No results file generated. Exit code: {proc.returncode}")
        if proc.stderr:
            print(f"stderr: {proc.stderr[:500]}")
        return {"error": "no_results", "exit_code": proc.returncode}

    results = json.loads(results_file.read_text(encoding="utf-8"))
    results["elapsed_seconds"] = round(elapsed, 1)
    results["replays_per_second"] = round(len(codes) / elapsed, 2) if elapsed > 0 else 0
    return results


def print_report(results: dict):
    """Print a human-readable summary."""
    if "error" in results:
        print(f"\n{'='*60}")
        print(f"VALIDATION FAILED: {results['error']}")
        print(f"{'='*60}")
        return

    total = results.get("totalCodes", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    errors = results.get("errors", 0)
    rate = results.get("passRate", 0)
    elapsed = results.get("elapsed_seconds", 0)
    rps = results.get("replays_per_second", 0)

    print(f"\n{'='*60}")
    print(f"  BATCH VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"  Total replays:    {total}")
    print(f"  Passed:           {passed}")
    print(f"  Failed:           {failed}")
    print(f"  Errors:           {errors}")
    print(f"  Pass rate:        {rate*100:.2f}%")
    print(f"  Time:             {elapsed:.1f}s ({rps:.1f} replays/sec)")

    by_cat = results.get("byCategory", {})
    if by_cat:
        print(f"\n  By game length:")
        for cat, data in by_cat.items():
            p, f = data.get("pass", 0), data.get("fail", 0)
            print(f"    {cat:12s}  {p:5d} pass  {f:3d} fail")

    recovery = results.get("recoveryTotals", {})
    if recovery:
        print(f"\n  Recovery events (auto-fixed by matchup runner):")
        for key, count in recovery.items():
            print(f"    {key:20s}  {count:,}")

    failures = results.get("failures", [])
    if failures:
        print(f"\n  First 10 failures:")
        for f in failures[:10]:
            code = f.get("code", "?")
            total_clicks = f.get("totalClicks", 0)
            applied = f.get("appliedClicks", 0)
            turns = f.get("totalTurns", "?")
            err = f.get("error")
            print(f"    {code:15s}  clicks={applied}/{total_clicks}  turns={turns}"
                  + (f"  ERROR: {err}" if err else ""))

    print(f"{'='*60}")

    # Verdict
    if failed == 0 and errors == 0:
        print("  RESULT: ALL PASSED")
    elif rate >= 0.99:
        print(f"  RESULT: {rate*100:.2f}% PASS (known failures only)")
    else:
        print(f"  RESULT: NEEDS INVESTIGATION ({failed} failures)")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Batch replay validation")
    parser.add_argument("--count", "-n", type=int, default=100,
                        help="Number of random replays to validate (default: 100)")
    parser.add_argument("--codes", type=str, default=None,
                        help="Path to replay code list (default: eligible_1500_codes.txt)")
    parser.add_argument("--source", choices=list(CODE_LISTS.keys()), default="eligible_1500",
                        help="Named code list to sample from")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducible sampling")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Parallel S3 fetch concurrency (default: 5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-replay output")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Save results JSON to this path")
    parser.add_argument("--all", action="store_true",
                        help="Validate ALL codes in the list (ignore --count)")
    args = parser.parse_args()

    # Load codes
    codes_path = Path(args.codes) if args.codes else CODE_LISTS.get(args.source, DEFAULT_CODES)
    if not codes_path.exists():
        print(f"ERROR: Code list not found: {codes_path}")
        sys.exit(1)

    print(f"Loading codes from: {codes_path}")
    all_codes = load_codes(codes_path)
    print(f"  Total available: {len(all_codes):,}")

    if args.all:
        codes = all_codes
    else:
        codes = sample_codes(all_codes, args.count, seed=args.seed)
    print(f"  Selected: {len(codes):,}" + (f" (seed={args.seed})" if args.seed else " (random)"))

    # Validate
    results = run_validation(codes, concurrency=args.concurrency, verbose=args.verbose)

    # Report
    print_report(results)

    # Save results
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Results saved to: {out_path}")

    # Exit code
    if "error" in results:
        sys.exit(2)
    elif results.get("failed", 0) > 0 or results.get("errors", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
