#!/usr/bin/env python
"""End-to-end engine state verification orchestrator.

Ties together three tools into a single pipeline:
  1. Download replay from S3
  2. Run C++ --dump-states to produce engine state dumps
  3. Get F6 ground-truth states (from existing captures or interactive capture)
  4. Run compare_engine_states.py to produce a mismatch report

Usage:
    # Single replay, skip F6 (C++ dump only)
    python tools/validate_engine_states.py Abc12-defgh --skip-f6

    # Multiple replays with existing F6 captures
    python tools/validate_engine_states.py Code1 Code2 --f6-dir my_captures/

    # Batch from file
    python tools/validate_engine_states.py --replay-file codes.txt --skip-f6

    # Full pipeline (will prompt for F6 capture)
    python tools/validate_engine_states.py Abc12-defgh --verbose

All intermediate files (replays, C++ dumps, F6 captures, reports) are cached
under --output-dir so re-runs skip completed steps.

Requires only stdlib (no external packages).
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg, file=sys.stderr):
    print(msg, file=file, flush=True)


# ---------------------------------------------------------------------------
# Step 1: Download replay
# ---------------------------------------------------------------------------

def download_replay(code, output_dir):
    """Download replay JSON from S3 if not already cached.

    Returns path to the cached replay file, or None on failure.
    """
    cache_dir = os.path.join(output_dir, "replays")
    os.makedirs(cache_dir, exist_ok=True)
    replay_path = os.path.join(cache_dir, f"{code}.json")

    if os.path.exists(replay_path):
        _log(f"  [download] Using cached: {replay_path}")
        return replay_path

    # URL-encode special characters in replay codes
    encoded = code.replace("+", "%2B").replace("@", "%40")
    url = f"http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{encoded}.json.gz"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            compressed = resp.read()
        data = gzip.decompress(compressed)
        with open(replay_path, "wb") as f:
            f.write(data)
        _log(f"  [download] Downloaded: {code}")
        return replay_path
    except Exception as e:
        _log(f"  [download] FAILED for {code}: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 2: Run C++ dump
# ---------------------------------------------------------------------------

def run_cpp_dump(exe_path, replay_path, output_dir, code):
    """Run Prismata_Testing --dump-states on a replay.

    Returns path to the JSONL output file, or None on failure.
    """
    dump_dir = os.path.join(output_dir, "cpp_dumps")
    os.makedirs(dump_dir, exist_ok=True)
    output_path = os.path.join(dump_dir, f"{code}.jsonl")

    # Skip if already dumped
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        _log(f"  [cpp] Using cached: {output_path}")
        return output_path

    # The C++ exe needs to run from its own directory (bin/) so it can find
    # asset/config/cardLibrary.jso and config.txt.  All paths passed on the
    # command line must therefore be absolute.
    exe_dir = os.path.dirname(exe_path)
    abs_replay = os.path.abspath(replay_path)
    abs_output = os.path.abspath(output_path)

    try:
        result = subprocess.run(
            [exe_path, "--dump-states", abs_replay, "--dump-output", abs_output],
            capture_output=True, text=True, timeout=120,
            cwd=exe_dir or None,
        )
    except FileNotFoundError:
        _log(f"  [cpp] FAILED: exe not found: {exe_path}")
        return None
    except subprocess.TimeoutExpired:
        _log(f"  [cpp] FAILED: timed out after 120s")
        return None

    if result.returncode != 0:
        stderr_snippet = result.stderr[:300].strip() if result.stderr else "(no stderr)"
        _log(f"  [cpp] FAILED (exit {result.returncode}): {stderr_snippet}")
        return None

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        _log(f"  [cpp] FAILED: output file missing or empty")
        return None

    # Count lines for progress feedback
    with open(output_path, "r", encoding="utf-8") as f:
        line_count = sum(1 for line in f if line.strip())
    _log(f"  [cpp] Dumped {line_count} state entries to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Step 3: Get F6 states
# ---------------------------------------------------------------------------

def get_f6_states(code, output_dir, skip_f6, f6_dir):
    """Get F6 ground truth states -- from existing captures or interactive prompt.

    Returns path to the F6 JSON file, or None if unavailable.
    """
    f6_dir_actual = f6_dir or os.path.join(output_dir, "f6_captures")

    # Check for existing capture
    f6_path = os.path.join(f6_dir_actual, f"{code}.json")
    if os.path.exists(f6_path):
        _log(f"  [f6] Using existing: {f6_path}")
        return f6_path

    if skip_f6:
        _log(f"  [f6] Skipped (--skip-f6). No F6 data for {code}.")
        return None

    # Interactive: prompt user to load replay and run capture
    _log(f"\n{'=' * 60}")
    _log(f"  F6 CAPTURE REQUIRED for replay: {code}")
    _log(f"  1. Open Prismata client (developer-mode SWF patch required)")
    _log(f"  2. Load replay {code} in the replay viewer")
    _log(f"  3. Rewind to the beginning (Home key)")
    _log(f"  4. Press Enter here to start F6 capture...")
    _log(f"{'=' * 60}")

    try:
        input()  # Wait for user
    except (EOFError, KeyboardInterrupt):
        _log(f"  [f6] Capture cancelled by user")
        return None

    os.makedirs(f6_dir_actual, exist_ok=True)

    # Run the capture tool as subprocess
    try:
        result = subprocess.run(
            [sys.executable, "tools/capture_replay_states.py",
             "--output", f6_path,
             "--max-turns", "200"],
            timeout=300
        )
    except subprocess.TimeoutExpired:
        _log(f"  [f6] Capture TIMED OUT after 300s for {code}")
        return None
    except Exception as e:
        _log(f"  [f6] Capture FAILED for {code}: {e}")
        return None

    if result.returncode != 0:
        _log(f"  [f6] Capture exited with code {result.returncode} for {code}")
        return None

    if not os.path.exists(f6_path) or os.path.getsize(f6_path) == 0:
        _log(f"  [f6] Capture produced no output for {code}")
        return None

    _log(f"  [f6] Captured to {f6_path}")
    return f6_path


# ---------------------------------------------------------------------------
# Step 4: Run comparison
# ---------------------------------------------------------------------------

def run_comparison(f6_path, cpp_path, card_library, output_dir, code, verbose):
    """Run compare_engine_states.py and parse the JSON report.

    Returns parsed report dict, or a failure dict.
    """
    report_dir = os.path.join(output_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{code}_report.json")

    cmd = [
        sys.executable, "tools/compare_engine_states.py",
        "--f6", f6_path,
        "--cpp", cpp_path,
        "--card-library", card_library,
        "--output", report_path,
    ]
    if verbose:
        cmd.append("--verbose")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        _log(f"  [compare] TIMED OUT after 60s for {code}")
        return {"code": code, "status": "comparison_timeout"}
    except Exception as e:
        _log(f"  [compare] FAILED for {code}: {e}")
        return {"code": code, "status": "comparison_failed", "error": str(e)}

    # Print the human-readable summary (stdout from comparison tool)
    if result.stdout:
        print(result.stdout)

    # Print stderr from comparison tool (info messages)
    if result.stderr and verbose:
        _log(result.stderr.rstrip())

    # Parse the JSON report
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            report["code"] = code
            report["status"] = "ok"
            return report
        except (json.JSONDecodeError, OSError) as e:
            _log(f"  [compare] Could not parse report JSON: {e}")
            return {"code": code, "status": "report_parse_failed", "error": str(e)}

    stderr_snippet = result.stderr[:500].strip() if result.stderr else ""
    return {"code": code, "status": "comparison_failed", "stderr": stderr_snippet}


# ---------------------------------------------------------------------------
# Per-replay orchestration
# ---------------------------------------------------------------------------

def validate_replay(code, exe_path, output_dir, card_library, skip_f6, f6_dir, verbose):
    """Run the full validation pipeline for one replay code.

    Returns a result dict with at minimum {"code", "status"}.
    """
    # Step 1: Download replay
    replay_path = download_replay(code, output_dir)
    if not replay_path:
        return {"code": code, "status": "download_failed"}

    # Step 2: Run C++ dump
    cpp_output = run_cpp_dump(exe_path, replay_path, output_dir, code)
    if not cpp_output:
        return {"code": code, "status": "cpp_dump_failed"}

    # Step 3: Get F6 states
    f6_path = get_f6_states(code, output_dir, skip_f6, f6_dir)
    if not f6_path:
        return {"code": code, "status": "f6_missing", "cpp_dump": cpp_output}

    # Step 4: Run comparison
    report = run_comparison(f6_path, cpp_output, card_library, output_dir, code, verbose)
    return report


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------

def print_batch_summary(results, output_dir):
    """Print and save aggregate results across all replays."""
    total = len(results)

    # Classify outcomes
    fully_matching = 0
    with_mismatches = 0
    failed = 0
    f6_missing = 0

    all_categories = Counter()
    total_turns_compared = 0
    total_mismatches = 0

    for r in results:
        status = r.get("status", "unknown")

        if status == "ok":
            mismatch_count = r.get("mismatch_count", 0)
            if mismatch_count == 0:
                fully_matching += 1
            else:
                with_mismatches += 1
            total_turns_compared += r.get("aligned_turn_count", 0)
            total_mismatches += mismatch_count
            for cat, count in r.get("category_counts", {}).items():
                all_categories[cat] += count

        elif status == "f6_missing":
            f6_missing += 1

        else:
            failed += 1

    # Print summary
    _log(f"\n{'=' * 60}", file=sys.stdout)
    _log(f"BATCH SUMMARY", file=sys.stdout)
    _log(f"{'=' * 60}", file=sys.stdout)
    _log(f"Total replays:      {total}", file=sys.stdout)
    _log(f"Fully matching:     {fully_matching}", file=sys.stdout)
    _log(f"With mismatches:    {with_mismatches}", file=sys.stdout)
    _log(f"F6 data missing:    {f6_missing}", file=sys.stdout)
    _log(f"Failed:             {failed}", file=sys.stdout)
    _log(f"Turns compared:     {total_turns_compared}", file=sys.stdout)
    _log(f"Total mismatches:   {total_mismatches}", file=sys.stdout)

    if all_categories:
        _log(f"\nMismatch categories:", file=sys.stdout)
        for cat, count in all_categories.most_common():
            _log(f"  {cat}: {count}", file=sys.stdout)

    # Per-replay status line
    compared_results = [r for r in results if r.get("status") == "ok"]
    if compared_results:
        _log(f"\nPer-replay results:", file=sys.stdout)
        for r in compared_results:
            code = r.get("code", "?")
            aligned = r.get("aligned_turn_count", 0)
            match_count = r.get("match_count", 0)
            mismatch_count = r.get("mismatch_count", 0)
            match_rate = r.get("match_rate", 0)
            first_mm = r.get("first_mismatch_turn")
            status_icon = "PASS" if mismatch_count == 0 else "FAIL"
            first_mm_str = f", first mismatch turn {first_mm}" if first_mm is not None else ""
            _log(
                f"  {status_icon}  {code}: {match_count}/{aligned} turns match "
                f"({match_rate:.1f}%){first_mm_str}",
                file=sys.stdout,
            )

    # Save batch summary JSON
    summary = {
        "total_replays": total,
        "fully_matching": fully_matching,
        "with_mismatches": with_mismatches,
        "f6_missing": f6_missing,
        "failed": failed,
        "total_turns_compared": total_turns_compared,
        "total_mismatches": total_mismatches,
        "mismatch_categories": dict(all_categories.most_common()),
        "per_replay": results,
    }
    summary_path = os.path.join(output_dir, "batch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str, ensure_ascii=False)
    _log(f"\nDetailed results: {summary_path}", file=sys.stdout)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end engine state verification pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # C++ dump only (no F6)\n"
            "  python tools/validate_engine_states.py Abc12-defgh --skip-f6\n"
            "\n"
            "  # Batch with existing F6 captures\n"
            "  python tools/validate_engine_states.py --replay-file codes.txt --f6-dir my_captures/\n"
            "\n"
            "  # Full pipeline (interactive F6 capture)\n"
            "  python tools/validate_engine_states.py Abc12-defgh --verbose\n"
        ),
    )
    parser.add_argument(
        "codes", nargs="*",
        help="Replay codes to validate",
    )
    parser.add_argument(
        "--replay-file",
        help="File with replay codes (one per line, # comments allowed)",
    )
    parser.add_argument(
        "--exe",
        default=None,
        help="Path to Prismata_Testing exe (default: auto-detect bin/Prismata_Testing_d.exe or .exe)",
    )
    parser.add_argument(
        "--output-dir",
        default="validation_results",
        help="Directory for all output (default: validation_results/)",
    )
    parser.add_argument(
        "--card-library",
        default="bin/asset/config/cardLibrary.jso",
        help="Path to cardLibrary.jso (default: bin/asset/config/cardLibrary.jso)",
    )
    parser.add_argument(
        "--skip-f6",
        action="store_true",
        help="Skip F6 capture, only run C++ dumps",
    )
    parser.add_argument(
        "--f6-dir",
        help="Directory with existing F6 captures (files named {code}.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Pass --verbose to comparison tool for detailed mismatch output",
    )
    args = parser.parse_args()

    # Collect replay codes
    codes = list(args.codes)
    if args.replay_file:
        try:
            with open(args.replay_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        codes.append(line)
        except OSError as e:
            _log(f"ERROR: Cannot read replay file: {e}")
            sys.exit(1)

    if not codes:
        _log("No replay codes provided. Use positional args or --replay-file.")
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Resolve all paths to absolute (Windows subprocess.run needs absolute paths
    # to find executables -- forward-slash relative paths cause FileNotFoundError)
    if args.exe:
        exe_path = os.path.abspath(args.exe)
    else:
        # Auto-detect: prefer Debug build (_d.exe) since it's typically newer
        for candidate in ["bin/Prismata_Testing_d.exe", "bin/Prismata_Testing.exe"]:
            if os.path.isfile(candidate):
                exe_path = os.path.abspath(candidate)
                break
        else:
            _log("ERROR: No Prismata_Testing exe found in bin/")
            _log("  Build with MSBuild or provide --exe path.")
            sys.exit(1)
    output_dir = os.path.abspath(args.output_dir)
    card_library = os.path.abspath(args.card_library)
    f6_dir = os.path.abspath(args.f6_dir) if args.f6_dir else None

    # Validate exe exists
    if not os.path.isfile(exe_path):
        _log(f"ERROR: Exe not found: {exe_path}")
        _log(f"  Build with MSBuild or provide --exe path to Debug/Release exe.")
        sys.exit(1)

    # Validate card library exists (only needed when F6 comparison will run)
    if not args.skip_f6 and not os.path.isfile(card_library):
        _log(f"WARNING: Card library not found: {card_library}")
        _log(f"  Comparison step will fail. Use --card-library or --skip-f6.")

    os.makedirs(output_dir, exist_ok=True)

    _log(f"Engine State Verification Pipeline")
    _log(f"==================================")
    _log(f"Replays: {len(codes)}")
    _log(f"Exe: {exe_path}")
    _log(f"Output: {output_dir}")
    _log(f"F6 mode: {'skip' if args.skip_f6 else ('from ' + f6_dir if f6_dir else 'interactive')}")
    _log(f"")

    # Process each replay
    results = []
    for i, code in enumerate(codes, 1):
        _log(f"\n[{i}/{len(codes)}] Processing {code}...")
        result = validate_replay(
            code, exe_path, output_dir, card_library,
            args.skip_f6, f6_dir, args.verbose,
        )
        results.append(result)

        # Brief status after each replay
        status = result.get("status", "unknown")
        if status == "ok":
            mm = result.get("mismatch_count", 0)
            aligned = result.get("aligned_turn_count", 0)
            if mm == 0:
                _log(f"  => PASS ({aligned} turns match)")
            else:
                rate = result.get("match_rate", 0)
                _log(f"  => FAIL ({mm} mismatches in {aligned} turns, {rate:.1f}% match)")
        elif status == "f6_missing":
            _log(f"  => C++ dump complete, F6 data missing")
        else:
            _log(f"  => {status.upper()}")

    # Batch summary
    print_batch_summary(results, output_dir)


if __name__ == "__main__":
    main()
