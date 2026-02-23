"""
Compare neural net evaluations between pre-port and ported Prismata engines.

Runs --analyze on the same replays with both engines and compares per-turn
eval values to detect any divergence introduced by the AS3 faithful port.

Usage:
    python tools/compare_analyze_evals.py [--num-replays 20] [--think-time 100]
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

BIN_DIR = Path("c:/libraries/PrismataAI/bin")
REPLAY_DIR = BIN_DIR / "replays_test"
PRE_PORT_EXE = BIN_DIR / "Prismata_Testing_pre_port.exe"
PORTED_EXE = BIN_DIR / "Prismata_Testing.exe"


def select_replays(num: int, seed: int = 42) -> list[Path]:
    """Select diverse replays — pick evenly spaced from sorted list."""
    all_replays = sorted(REPLAY_DIR.glob("*.json"))
    if not all_replays:
        print("ERROR: No replay files found in", REPLAY_DIR)
        sys.exit(1)

    # Use deterministic seed for reproducibility
    rng = random.Random(seed)
    selected = rng.sample(all_replays, min(num, len(all_replays)))
    return selected


def run_analyze(exe: Path, replay: Path, think_time: int) -> dict | None:
    """Run --analyze on a replay and return parsed JSON, or None on failure."""
    cmd = [
        str(exe),
        "--analyze",
        str(replay),
        "--think-time",
        str(think_time),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BIN_DIR),
        )
        if result.returncode != 0:
            return None

        stdout = result.stdout.strip()
        if not stdout:
            return None

        # Output may have multiple lines; the JSON is the last non-empty line
        lines = [l for l in stdout.split("\n") if l.strip()]
        if not lines:
            return None

        return json.loads(lines[-1])

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"  ERROR running {exe.name} on {replay.name}: {e}")
        return None


def extract_eval_by_turn(data: dict) -> dict[tuple[int, int], float]:
    """
    Extract (turn, player) -> eval mapping.
    If duplicate (turn, player) entries exist (from fatal error retries),
    take the FIRST occurrence since that's the state before the retry.
    """
    evals = {}
    for t in data.get("turns", []):
        key = (t["turn"], t["player"])
        if key not in evals:
            evals[key] = t["eval"]
    return evals


def compare_evals(
    pre_evals: dict[tuple[int, int], float],
    post_evals: dict[tuple[int, int], float],
) -> list[dict]:
    """Compare eval values for matching turns. Return list of diffs."""
    common_keys = sorted(set(pre_evals.keys()) & set(post_evals.keys()))
    diffs = []
    for key in common_keys:
        pre_v = pre_evals[key]
        post_v = post_evals[key]
        diff = abs(pre_v - post_v)
        diffs.append({
            "turn": key[0],
            "player": key[1],
            "pre_eval": pre_v,
            "post_eval": post_v,
            "abs_diff": diff,
        })
    return diffs


def main():
    parser = argparse.ArgumentParser(description="Compare engine eval outputs")
    parser.add_argument("--num-replays", type=int, default=20)
    parser.add_argument("--think-time", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Verify executables exist
    for exe in [PRE_PORT_EXE, PORTED_EXE]:
        if not exe.exists():
            print(f"ERROR: {exe} not found")
            sys.exit(1)

    replays = select_replays(args.num_replays, args.seed)
    print(f"Selected {len(replays)} replays for comparison")
    print(f"Pre-port exe: {PRE_PORT_EXE.name}")
    print(f"Ported exe:   {PORTED_EXE.name}")
    print(f"Think time:   {args.think_time} ms")
    print()

    # ── Per-replay comparison ──────────────────────────────────────────────

    all_diffs = []           # Flat list of all turn-level diffs
    replay_summaries = []    # Per-replay summary
    skipped_replays = []

    for i, replay in enumerate(replays):
        code = replay.stem
        print(f"[{i+1}/{len(replays)}] {code} ...", end="", flush=True)

        # Run pre-port
        pre_data = run_analyze(PRE_PORT_EXE, replay, args.think_time)
        if pre_data is None or not pre_data.get("ok", False):
            print(f" SKIP (pre-port failed)")
            skipped_replays.append(code)
            continue

        # Run ported (sequential — cannot run both at once, they share config)
        post_data = run_analyze(PORTED_EXE, replay, args.think_time)
        if post_data is None or not post_data.get("ok", False):
            print(f" SKIP (ported failed)")
            skipped_replays.append(code)
            continue

        # Extract and compare evals
        pre_evals = extract_eval_by_turn(pre_data)
        post_evals = extract_eval_by_turn(post_data)

        if not pre_evals or not post_evals:
            print(f" SKIP (no turns)")
            skipped_replays.append(code)
            continue

        diffs = compare_evals(pre_evals, post_evals)
        if not diffs:
            print(f" SKIP (no common turns)")
            skipped_replays.append(code)
            continue

        abs_diffs = [d["abs_diff"] for d in diffs]
        mean_diff = sum(abs_diffs) / len(abs_diffs)
        max_diff = max(abs_diffs)
        n_nonzero = sum(1 for d in abs_diffs if d > 0.0001)

        # Count turns that only exist in one engine
        pre_only = len(set(pre_evals.keys()) - set(post_evals.keys()))
        post_only = len(set(post_evals.keys()) - set(pre_evals.keys()))

        summary = {
            "code": code,
            "common_turns": len(diffs),
            "mean_abs_diff": mean_diff,
            "max_abs_diff": max_diff,
            "nonzero_diffs": n_nonzero,
            "pre_only_turns": pre_only,
            "post_only_turns": post_only,
            "pre_fatal_errors": pre_data.get("fatal_errors", 0),
            "post_fatal_errors": post_data.get("fatal_errors", 0),
        }
        replay_summaries.append(summary)

        # Tag each diff with its replay code
        for d in diffs:
            d["code"] = code
        all_diffs.extend(diffs)

        status = "OK" if max_diff < 0.001 else f"DIVERGED (max={max_diff:.4f})"
        print(f" {len(diffs)} turns, mean_diff={mean_diff:.6f}, max={max_diff:.6f} [{status}]")

    # ── Aggregate statistics ───────────────────────────────────────────────

    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)

    if not all_diffs:
        print("No data to analyze — all replays failed or were skipped.")
        return

    all_abs = [d["abs_diff"] for d in all_diffs]
    n_total = len(all_abs)
    n_exact = sum(1 for d in all_abs if d == 0.0)
    n_near_zero = sum(1 for d in all_abs if d < 0.0001)
    n_small = sum(1 for d in all_abs if 0.0001 <= d < 0.01)
    n_medium = sum(1 for d in all_abs if 0.01 <= d < 0.05)
    n_large = sum(1 for d in all_abs if d >= 0.05)

    mean_all = sum(all_abs) / n_total
    max_all = max(all_abs)
    # Compute stdev
    variance = sum((d - mean_all) ** 2 for d in all_abs) / n_total
    stdev_all = variance ** 0.5

    print(f"\nReplays analyzed:   {len(replay_summaries)}")
    print(f"Replays skipped:    {len(skipped_replays)}")
    print(f"Total turn-evals:   {n_total}")
    print()
    print(f"Mean |diff|:        {mean_all:.6f}")
    print(f"Max |diff|:         {max_all:.6f}")
    print(f"Stdev |diff|:       {stdev_all:.6f}")
    print()
    print(f"Exact match (0.0):  {n_exact:5d} ({100*n_exact/n_total:.1f}%)")
    print(f"Near-zero (<0.0001):{n_near_zero:5d} ({100*n_near_zero/n_total:.1f}%)")
    print(f"Small (0.0001-0.01):{n_small:5d} ({100*n_small/n_total:.1f}%)")
    print(f"Medium (0.01-0.05): {n_medium:5d} ({100*n_medium/n_total:.1f}%)")
    print(f"Large (>=0.05):     {n_large:5d} ({100*n_large/n_total:.1f}%)")

    # ── Top 10 largest divergences ─────────────────────────────────────────

    print("\n" + "-" * 80)
    print("TOP 10 LARGEST EVAL DIVERGENCES")
    print("-" * 80)
    sorted_diffs = sorted(all_diffs, key=lambda d: d["abs_diff"], reverse=True)
    print(f"{'Replay':<32s} {'Turn':>4s} {'P':>1s} {'Pre':>8s} {'Post':>8s} {'Diff':>8s}")
    for d in sorted_diffs[:10]:
        print(f"{d['code']:<32s} {d['turn']:>4d} {d['player']:>1d} "
              f"{d['pre_eval']:>8.4f} {d['post_eval']:>8.4f} {d['abs_diff']:>8.4f}")

    # ── Per-replay summary table ───────────────────────────────────────────

    print("\n" + "-" * 80)
    print("PER-REPLAY SUMMARY")
    print("-" * 80)
    print(f"{'Replay':<32s} {'Turns':>5s} {'MeanDiff':>9s} {'MaxDiff':>9s} "
          f"{'Nonzero':>7s} {'PreErr':>6s} {'PostErr':>7s}")
    for s in sorted(replay_summaries, key=lambda x: x["max_abs_diff"], reverse=True):
        print(f"{s['code']:<32s} {s['common_turns']:>5d} "
              f"{s['mean_abs_diff']:>9.6f} {s['max_abs_diff']:>9.6f} "
              f"{s['nonzero_diffs']:>7d} {s['pre_fatal_errors']:>6d} "
              f"{s['post_fatal_errors']:>7d}")

    # ── Divergence by turn number ──────────────────────────────────────────

    print("\n" + "-" * 80)
    print("MEAN |DIFF| BY TURN NUMBER (first 30 turns)")
    print("-" * 80)
    from collections import defaultdict
    turn_diffs = defaultdict(list)
    for d in all_diffs:
        turn_diffs[d["turn"]].append(d["abs_diff"])

    for t in sorted(turn_diffs.keys())[:30]:
        vals = turn_diffs[t]
        m = sum(vals) / len(vals)
        mx = max(vals)
        bar = "#" * int(m * 200)  # scale for visibility
        print(f"  Turn {t:>3d}: mean={m:.6f} max={mx:.6f} n={len(vals):>3d} {bar}")

    # ── Fatal error comparison ─────────────────────────────────────────────

    print("\n" + "-" * 80)
    print("FATAL ERROR COMPARISON")
    print("-" * 80)
    total_pre_err = sum(s["pre_fatal_errors"] for s in replay_summaries)
    total_post_err = sum(s["post_fatal_errors"] for s in replay_summaries)
    print(f"Total fatal errors (pre-port):  {total_pre_err}")
    print(f"Total fatal errors (ported):    {total_post_err}")
    diff_err = total_post_err - total_pre_err
    if diff_err > 0:
        print(f"  >> Ported engine has {diff_err} MORE fatal errors")
    elif diff_err < 0:
        print(f"  >> Ported engine has {-diff_err} FEWER fatal errors")
    else:
        print(f"  >> Same number of fatal errors")

    # ── Conclusion ─────────────────────────────────────────────────────────

    print("\n" + "=" * 80)
    if max_all < 0.0001:
        print("CONCLUSION: Evals are IDENTICAL between pre-port and ported engines.")
    elif max_all < 0.01:
        print(f"CONCLUSION: Minor eval differences detected (max {max_all:.6f}).")
        print("  Likely caused by different game states from engine logic changes.")
    elif max_all < 0.1:
        print(f"CONCLUSION: Moderate eval differences detected (max {max_all:.6f}).")
        print("  Engine logic changes are producing meaningfully different game states.")
    else:
        print(f"CONCLUSION: LARGE eval differences detected (max {max_all:.6f}).")
        print("  Investigate the top divergences — may indicate a bug.")
    print("=" * 80)

    # ── Save JSON results ──────────────────────────────────────────────────

    output_path = Path("c:/libraries/PrismataAI/tools/data/eval_comparison_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = {
        "num_replays": len(replay_summaries),
        "num_skipped": len(skipped_replays),
        "total_turns": n_total,
        "mean_abs_diff": mean_all,
        "max_abs_diff": max_all,
        "stdev_abs_diff": stdev_all,
        "exact_match_pct": 100 * n_exact / n_total,
        "replay_summaries": replay_summaries,
        "top_divergences": sorted_diffs[:20],
        "skipped_replays": skipped_replays,
    }
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
