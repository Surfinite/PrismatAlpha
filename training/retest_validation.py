"""Quick re-test of failed replays against the fixed C++ engine.

Usage: python retest_validation.py <batch_dir> [max_replays]
"""
import json, subprocess, sys, os, re
from pathlib import Path

def main():
    batch_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("c:/libraries/prismata-replay-parser/batch_validation")
    max_replays = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    results_file = batch_dir / "validation_results.json"
    with open(results_file) as f:
        results = json.load(f)

    failed = [r['code'] for r in results['results'] if r['status'] == 'FAIL']
    test_codes = failed[:max_replays]

    exe = "c:/libraries/PrismataAI/bin/Prismata_Testing.exe"
    cwd = "c:/libraries/PrismataAI/bin"
    tmp_output = str(Path(cwd) / "tmp_retest_output.jsonl")

    pass_count = 0
    fail_count = 0
    errors = 0
    fail_details = {}

    print(f"Re-testing {len(test_codes)} failed replays...", flush=True)

    for i, code in enumerate(test_codes):
        base = re.sub(r'[^a-zA-Z0-9]', '_', code) + '_states'
        cpp_input = batch_dir / f'{base}_cpp.json'

        if not cpp_input.exists():
            errors += 1
            continue

        try:
            result = subprocess.run(
                [exe, '--validate-replay', str(cpp_input.resolve()),
                 '--validate-output', tmp_output],
                capture_output=True, text=True, timeout=30, cwd=cwd
            )

            output = result.stdout + result.stderr
            err_count = None
            for line in output.split('\n'):
                if 'Total errors:' in line:
                    err_count = int(line.split(':')[-1].strip())
                    break

            if err_count is None:
                errors += 1
                continue

            if err_count == 0:
                pass_count += 1
            else:
                fail_count += 1
                # Categorize failures
                snipe_fails = output.count('SNIPE')
                frontline_fails = output.count('ASSIGN_FRONTLINE')
                blocker_fails = output.count('ASSIGN_BLOCKER')
                first_error = ""
                for line in output.split('\n'):
                    if 'RESOLVE FAILED' in line or 'NOT LEGAL' in line:
                        first_error = line.strip().split(']')[-1].strip() if ']' in line else line.strip()
                        break
                fail_details[code] = {
                    'errors': err_count,
                    'first_error': first_error[:80],
                    'has_snipe': snipe_fails > 0,
                }

        except subprocess.TimeoutExpired:
            errors += 1
        except Exception as e:
            errors += 1

        if (i+1) % 25 == 0:
            total = pass_count + fail_count + errors
            print(f"  Progress: {i+1}/{len(test_codes)} (pass={pass_count}, fail={fail_count}, err={errors})", flush=True)

    total = pass_count + fail_count + errors
    print(f"\n{'='*60}")
    print(f"Re-test Results ({total} replays)")
    print(f"{'='*60}")
    print(f"  PASS (0 errors):  {pass_count:4d}  ({pass_count/max(total,1)*100:.1f}%)")
    print(f"  FAIL (>0 errors): {fail_count:4d}  ({fail_count/max(total,1)*100:.1f}%)")
    print(f"  ERROR:            {errors:4d}")

    if fail_details:
        # First error category distribution
        from collections import Counter
        categories = Counter()
        for d in fail_details.values():
            fe = d['first_error']
            if 'SNIPE' in fe:
                categories['SNIPE'] += 1
            elif 'FRONTLINE' in fe:
                categories['FRONTLINE'] += 1
            elif 'BLOCKER' in fe:
                categories['BLOCKER'] += 1
            elif 'USE_ABILITY' in fe:
                categories['USE_ABILITY'] += 1
            elif 'BUY' in fe:
                categories['BUY'] += 1
            elif 'END_PHASE' in fe:
                categories['END_PHASE'] += 1
            else:
                categories['OTHER'] += 1

        print(f"\n--- First Error Category Distribution ---")
        for cat, count in categories.most_common():
            print(f"  {cat:16s}: {count:4d}")

    # Cleanup
    try:
        os.remove(tmp_output)
    except:
        pass

if __name__ == '__main__':
    main()
