"""
Replay Oracle: Run C++ replay validation and save structured per-replay results.

Creates a baseline JSON recording pass/fail status for each replay,
enabling regression detection across engine changes.

Usage:
    python tools/replay_oracle.py [--exe PATH] [--workers N] [--output PATH]

Defaults:
    --exe      bin/Prismata_Testing_pre_port.exe  (pre-port baseline binary)
    --workers  4
    --output   tools/data/replay_oracle_baseline.json
"""

import json
import sys
import os
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

SCRIPT_DIR = Path(__file__).parent.parent
BATCH_DIR = Path("c:/libraries/prismata-replay-parser/batch_validation")
CPP_CWD = SCRIPT_DIR / "bin"
DEFAULT_EXE = CPP_CWD / "Prismata_Testing_pre_port.exe"
DEFAULT_OUTPUT = SCRIPT_DIR / "tools" / "data" / "replay_oracle_baseline.json"

# Import the converter from training/
sys.path.insert(0, str(SCRIPT_DIR / "training"))
from convert_replay_for_cpp import convert_replay


def validate_one(cpp_input_path, cpp_exe, cwd):
    """Run C++ validation on a single converted replay.
    Returns dict with code, status, error_count, first_error, turn_info."""
    path = Path(cpp_input_path)
    code = path.stem.replace("_states_cpp", "")
    tmp_output = str(path.with_suffix('.tmp_oracle'))

    try:
        result = subprocess.run(
            [str(cpp_exe), '--validate-replay', str(path), '--validate-output', tmp_output],
            capture_output=True, text=True, timeout=60, cwd=str(cwd)
        )
        output = result.stdout + result.stderr
        err_count = None
        first_error = ""
        first_error_turn = -1
        total_turns = -1

        for line in output.split('\n'):
            if 'Total errors:' in line:
                try:
                    err_count = int(line.split(':')[-1].strip())
                except Exception:
                    pass
            if 'Total turns:' in line:
                try:
                    total_turns = int(line.split(':')[-1].strip())
                except Exception:
                    pass
            if not first_error and ('RESOLVE FAILED' in line or 'NOT LEGAL' in line):
                first_error = line.strip()
                # Try to extract turn number from error line
                if 'Turn ' in line:
                    try:
                        turn_part = line.split('Turn ')[1].split()[0].rstrip(':,')
                        first_error_turn = int(turn_part)
                    except Exception:
                        pass

        try:
            os.remove(tmp_output)
        except Exception:
            pass

        if err_count is None:
            return {"code": code, "status": "ERROR", "errors": -1,
                    "first_error": "NO_OUTPUT", "first_error_turn": -1,
                    "total_turns": -1}

        status = "PASS" if err_count == 0 else "FAIL"
        return {"code": code, "status": status, "errors": err_count,
                "first_error": first_error[:200] if first_error else "",
                "first_error_turn": first_error_turn,
                "total_turns": total_turns}

    except subprocess.TimeoutExpired:
        return {"code": code, "status": "ERROR", "errors": -1,
                "first_error": "TIMEOUT", "first_error_turn": -1,
                "total_turns": -1}
    except Exception as e:
        return {"code": code, "status": "ERROR", "errors": -1,
                "first_error": str(e)[:200], "first_error_turn": -1,
                "total_turns": -1}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Replay Oracle — baseline capture")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=BATCH_DIR)
    args = parser.parse_args()

    if not args.exe.exists():
        print(f"ERROR: Exe not found: {args.exe}", file=sys.stderr)
        sys.exit(1)

    # Find all replay state files
    state_files = sorted(args.batch_dir.glob("*_states.json"))
    state_files = [f for f in state_files if not f.stem.endswith('_cpp')]
    print(f"=== Replay Oracle ===")
    print(f"Exe: {args.exe}")
    print(f"Replays: {len(state_files)}, Workers: {args.workers}")
    print(flush=True)

    # Step 1: Ensure all replays are converted to C++ format
    print("Step 1: Converting TS dumps to C++ format...", flush=True)
    converted = []
    convert_errors = 0
    for i, sf in enumerate(state_files):
        cpp_input = sf.with_name(sf.stem + "_cpp.json")
        if cpp_input.exists():
            converted.append(str(cpp_input))
            continue
        try:
            old_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            convert_replay(str(sf), str(cpp_input))
            sys.stdout.close()
            sys.stdout = old_stdout
            converted.append(str(cpp_input))
        except Exception:
            sys.stdout = old_stdout
            convert_errors += 1
        if (i + 1) % 200 == 0:
            print(f"  Converted {i+1}/{len(state_files)} ({convert_errors} errors)", flush=True)

    print(f"  Done: {len(converted)} converted, {convert_errors} errors", flush=True)

    # Step 2: Parallel C++ validation
    print(f"\nStep 2: Running C++ validation ({args.workers} workers)...", flush=True)
    results = []
    pass_count = 0
    fail_count = 0
    error_count = convert_errors
    fail_categories = Counter()
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(validate_one, p, args.exe, CPP_CWD): p for p in converted}
        done = 0
        for future in as_completed(futures):
            done += 1
            result = future.result()
            results.append(result)

            if result["status"] == "PASS":
                pass_count += 1
            elif result["status"] == "FAIL":
                fail_count += 1
                fe = result["first_error"].upper()
                if 'SNIPE' in fe:
                    fail_categories['SNIPE'] += 1
                elif 'CHILL' in fe:
                    fail_categories['CHILL'] += 1
                elif 'FRONTLINE' in fe:
                    fail_categories['FRONTLINE'] += 1
                elif 'BLOCKER' in fe:
                    fail_categories['BLOCKER'] += 1
                elif 'USE_ABILITY' in fe:
                    fail_categories['USE_ABILITY'] += 1
                elif 'END_PHASE' in fe:
                    fail_categories['END_PHASE'] += 1
                elif 'BUY' in fe:
                    fail_categories['BUY'] += 1
                else:
                    fail_categories['OTHER'] += 1
            else:
                error_count += 1

            if done % 200 == 0:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  {done}/{len(converted)} ({rate:.1f}/s) pass={pass_count} fail={fail_count} err={error_count}",
                      flush=True)

    elapsed = time.time() - start_time
    total = pass_count + fail_count + error_count

    # Summary
    print(f"\n{'='*60}")
    print(f"Replay Oracle Results ({total} replays, {elapsed:.1f}s)")
    print(f"{'='*60}")
    print(f"  PASS:   {pass_count:5d}  ({pass_count/max(total,1)*100:.1f}%)")
    print(f"  FAIL:   {fail_count:5d}  ({fail_count/max(total,1)*100:.1f}%)")
    print(f"  ERROR:  {error_count:5d}  ({error_count/max(total,1)*100:.1f}%)")
    pass_rate = pass_count / max(total, 1) * 100
    print(f"  Pass rate: {pass_rate:.1f}%")

    if fail_categories:
        print(f"\n--- Failure Category Distribution ---")
        for cat, count in fail_categories.most_common():
            print(f"  {cat:16s}: {count:5d}  ({count/max(fail_count,1)*100:.1f}%)")

    # Sort results by code for deterministic output
    results.sort(key=lambda r: r["code"])

    # Save structured results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    oracle_data = {
        "metadata": {
            "exe": str(args.exe),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(elapsed, 1),
            "total_replays": total,
        },
        "summary": {
            "pass": pass_count,
            "fail": fail_count,
            "error": error_count,
            "pass_rate_pct": round(pass_rate, 1),
            "fail_categories": dict(fail_categories.most_common()),
        },
        "results": results,
    }

    with open(args.output, 'w') as f:
        json.dump(oracle_data, f, indent=2)
    print(f"\nOracle baseline saved to: {args.output}")


if __name__ == '__main__':
    main()
