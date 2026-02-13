"""
Batch validation pipeline: convert TS state dumps → C++ validation → comparison.

Usage:
    python batch_validate_pipeline.py <batch_dir> [--cpp-exe <path>]

Processes all *_states.json files in <batch_dir>:
  1. convert_replay_for_cpp.py → *_states_cpp.json
  2. C++ binary --validate-replay → *_cpp_output.jsonl
  3. compare_states.py → comparison results

Reports aggregate pass/fail stats.
"""

import json
import sys
import os
import subprocess
import glob
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONVERT_SCRIPT = SCRIPT_DIR / "convert_replay_for_cpp.py"
COMPARE_SCRIPT = SCRIPT_DIR / "compare_states.py"
DEFAULT_CPP_EXE = Path("c:/libraries/PrismataAI/bin/Prismata_Testing_d.exe")


def run_pipeline(batch_dir, cpp_exe=None):
    if cpp_exe is None:
        cpp_exe = DEFAULT_CPP_EXE

    batch_path = Path(batch_dir)
    state_files = sorted(batch_path.glob("*_states.json"))

    if not state_files:
        print(f"No *_states.json files found in {batch_dir}")
        return

    print(f"=== Batch Validation Pipeline ===")
    print(f"State dumps: {len(state_files)}")
    print(f"C++ exe:     {cpp_exe}")
    print()

    results = []
    pass_count = 0
    fail_count = 0
    error_count = 0

    for i, state_file in enumerate(state_files):
        base = state_file.stem  # e.g., XT93s_KquW2_states
        code = base.replace("_states", "")

        # Step 1: Convert TS → C++ format
        cpp_input = state_file.with_name(base + "_cpp.json")
        if not cpp_input.exists():
            try:
                subprocess.run(
                    [sys.executable, str(CONVERT_SCRIPT), str(state_file), str(cpp_input)],
                    check=True, capture_output=True, text=True, timeout=30
                )
            except subprocess.CalledProcessError as e:
                print(f"  [{i+1}/{len(state_files)}] {code}: CONVERT ERROR — {e.stderr[:200]}")
                results.append({"code": code, "status": "convert_error", "error": e.stderr[:500]})
                error_count += 1
                continue
            except subprocess.TimeoutExpired:
                print(f"  [{i+1}/{len(state_files)}] {code}: CONVERT TIMEOUT")
                results.append({"code": code, "status": "convert_timeout"})
                error_count += 1
                continue

        # Step 2: C++ validation
        cpp_output = state_file.with_name(base + "_cpp_output.jsonl")
        if not cpp_output.exists():
            try:
                subprocess.run(
                    [str(cpp_exe), "--validate-replay", str(cpp_input),
                     "--validate-output", str(cpp_output)],
                    check=True, capture_output=True, text=True, timeout=120,
                    cwd=str(Path(cpp_exe).parent)
                )
            except subprocess.CalledProcessError as e:
                print(f"  [{i+1}/{len(state_files)}] {code}: C++ ERROR — {e.stderr[:200]}")
                results.append({"code": code, "status": "cpp_error", "error": e.stderr[:500]})
                error_count += 1
                continue
            except subprocess.TimeoutExpired:
                print(f"  [{i+1}/{len(state_files)}] {code}: C++ TIMEOUT")
                results.append({"code": code, "status": "cpp_timeout"})
                error_count += 1
                continue

        # Step 3: Compare
        try:
            proc = subprocess.run(
                [sys.executable, str(COMPARE_SCRIPT), str(cpp_output), str(cpp_input)],
                capture_output=True, text=True, timeout=30
            )
            output = proc.stdout

            # Parse match rate from compare output
            match_rate = None
            total_mismatches = None
            for line in output.split('\n'):
                if 'Match rate:' in line:
                    try:
                        match_rate = float(line.split(':')[1].strip().replace('%', ''))
                    except:
                        pass
                if 'Total mismatches:' in line:
                    try:
                        total_mismatches = int(line.split(':')[1].strip())
                    except:
                        pass

            passed = (total_mismatches == 0)
            status = "PASS" if passed else "FAIL"

            if passed:
                pass_count += 1
            else:
                fail_count += 1
                # Show first few lines of comparison output for failures
                print(f"  [{i+1}/{len(state_files)}] {code}: FAIL — {total_mismatches} mismatches")
                for line in output.split('\n'):
                    if 'mismatch' in line.lower() or 'C++=' in line:
                        print(f"    {line.strip()}")

            results.append({
                "code": code,
                "status": status,
                "match_rate": match_rate,
                "total_mismatches": total_mismatches,
            })

        except subprocess.TimeoutExpired:
            print(f"  [{i+1}/{len(state_files)}] {code}: COMPARE TIMEOUT")
            results.append({"code": code, "status": "compare_timeout"})
            error_count += 1
            continue

        if (i + 1) % 25 == 0:
            print(f"  Progress: {i+1}/{len(state_files)} — {pass_count} pass, {fail_count} fail, {error_count} error")

    # Summary
    print(f"\n=== Batch Validation Summary ===")
    print(f"Total replays: {len(state_files)}")
    print(f"PASS:          {pass_count}")
    print(f"FAIL:          {fail_count}")
    print(f"ERRORS:        {error_count}")
    print(f"Pass rate:     {pass_count / len(state_files) * 100:.1f}%")

    if fail_count > 0:
        print(f"\nFailed replays:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  {r['code']}: {r['total_mismatches']} mismatches (match rate: {r['match_rate']}%)")

    if error_count > 0:
        print(f"\nError replays:")
        for r in results:
            if r["status"] not in ("PASS", "FAIL"):
                print(f"  {r['code']}: {r['status']}")

    # Save results
    results_file = batch_path / "validation_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "total": len(state_files),
            "pass": pass_count,
            "fail": fail_count,
            "errors": error_count,
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved to: {results_file}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python batch_validate_pipeline.py <batch_dir> [--cpp-exe <path>]")
        sys.exit(1)

    batch_dir = sys.argv[1]
    cpp_exe = None
    for i, arg in enumerate(sys.argv):
        if arg == "--cpp-exe" and i + 1 < len(sys.argv):
            cpp_exe = sys.argv[i + 1]

    run_pipeline(batch_dir, cpp_exe)
