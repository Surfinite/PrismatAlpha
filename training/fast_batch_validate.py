"""
Fast batch validation: in-process conversion + parallel C++ validation.

Usage: python fast_batch_validate.py <batch_dir> [--workers N]

Much faster than batch_validate_pipeline.py:
  - In-process conversion (no subprocess per replay)
  - Parallel C++ validation (4 workers by default)
"""

import json
import sys
import os
import subprocess
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from convert_replay_for_cpp import convert_replay

CPP_EXE = Path("c:/libraries/PrismataAI/bin/Prismata_Testing_d.exe")
CPP_CWD = Path("c:/libraries/PrismataAI/bin")


def validate_one(cpp_input_path, cpp_exe=str(CPP_EXE), cwd=str(CPP_CWD)):
    """Run C++ validation on a single converted replay. Returns (code, err_count, first_error)."""
    path = Path(cpp_input_path)
    code = path.stem.replace("_states_cpp", "")
    tmp_output = str(path.with_suffix('.tmp_out'))

    try:
        result = subprocess.run(
            [cpp_exe, '--validate-replay', str(path), '--validate-output', tmp_output],
            capture_output=True, text=True, timeout=60, cwd=cwd
        )
        output = result.stdout + result.stderr
        err_count = None
        first_error = ""
        for line in output.split('\n'):
            if 'Total errors:' in line:
                try:
                    err_count = int(line.split(':')[-1].strip())
                except:
                    pass
            if not first_error and ('RESOLVE FAILED' in line or 'NOT LEGAL' in line):
                first_error = line.strip().split(']')[-1].strip() if ']' in line else line.strip()

        try:
            os.remove(tmp_output)
        except:
            pass

        if err_count is None:
            return (code, -1, "NO_OUTPUT")
        return (code, err_count, first_error[:120])

    except subprocess.TimeoutExpired:
        return (code, -1, "TIMEOUT")
    except Exception as e:
        return (code, -1, str(e)[:120])


def main():
    batch_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("c:/libraries/prismata-replay-parser/batch_validation")
    workers = 4
    for i, arg in enumerate(sys.argv):
        if arg == '--workers' and i + 1 < len(sys.argv):
            workers = int(sys.argv[i + 1])

    state_files = sorted(batch_dir.glob("*_states.json"))
    # Exclude files that are already converted outputs
    state_files = [f for f in state_files if not f.stem.endswith('_cpp')]
    print(f"=== Fast Batch Validation ===")
    print(f"Replays: {len(state_files)}, Workers: {workers}")
    print(flush=True)

    # Step 1: In-process conversion
    print("Step 1: Converting TS dumps to C++ format...", flush=True)
    converted = []
    convert_errors = 0
    for i, sf in enumerate(state_files):
        cpp_input = sf.with_name(sf.stem + "_cpp.json")
        if cpp_input.exists():
            converted.append(str(cpp_input))
            continue
        try:
            # Redirect stdout to suppress per-file output
            old_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            convert_replay(str(sf), str(cpp_input))
            sys.stdout.close()
            sys.stdout = old_stdout
            converted.append(str(cpp_input))
        except Exception as e:
            sys.stdout = old_stdout
            convert_errors += 1
        if (i + 1) % 100 == 0:
            print(f"  Converted {i+1}/{len(state_files)} ({convert_errors} errors)", flush=True)

    print(f"  Done: {len(converted)} converted, {convert_errors} errors", flush=True)

    # Step 2: Parallel C++ validation
    print(f"\nStep 2: Running C++ validation ({workers} workers)...", flush=True)
    pass_count = 0
    fail_count = 0
    error_count = convert_errors
    fail_categories = Counter()
    fail_details = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(validate_one, p): p for p in converted}
        done = 0
        for future in as_completed(futures):
            done += 1
            code, err_count, first_error = future.result()
            if err_count == 0:
                pass_count += 1
            elif err_count < 0:
                error_count += 1
            else:
                fail_count += 1
                # Categorize
                fe = first_error.upper()
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
                fail_details.append((code, err_count, first_error))

            if done % 100 == 0:
                total = pass_count + fail_count + error_count
                print(f"  {done}/{len(converted)} validated (pass={pass_count}, fail={fail_count}, err={error_count})", flush=True)

    # Summary
    total = pass_count + fail_count + error_count
    print(f"\n{'='*60}")
    print(f"Batch Validation Results ({total} replays)")
    print(f"{'='*60}")
    print(f"  PASS:   {pass_count:5d}  ({pass_count/max(total,1)*100:.1f}%)")
    print(f"  FAIL:   {fail_count:5d}  ({fail_count/max(total,1)*100:.1f}%)")
    print(f"  ERROR:  {error_count:5d}  ({error_count/max(total,1)*100:.1f}%)")
    print(f"  Pass rate: {pass_count/max(total,1)*100:.1f}%")

    if fail_categories:
        print(f"\n--- First Error Category Distribution ---")
        for cat, count in fail_categories.most_common():
            print(f"  {cat:16s}: {count:5d}  ({count/max(fail_count,1)*100:.1f}%)")

    # Save results
    results_file = batch_dir / "validation_results.json"
    results = []
    # Rebuild results list
    for code, err_count, first_error in fail_details:
        results.append({"code": code, "status": "FAIL", "errors": err_count, "first_error": first_error})
    with open(results_file, 'w') as f:
        json.dump({
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "errors": error_count,
            "fail_categories": dict(fail_categories),
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved to: {results_file}")


if __name__ == '__main__':
    main()
