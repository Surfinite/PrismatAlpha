"""Compare training runs across different random seeds.

Usage:
  python training/compare_seeds.py training/runs/20260217_*.json
  python training/compare_seeds.py run1.json run2.json run3.json
"""

import json
import os
import sys
from statistics import mean, stdev


def load_run(path):
    with open(path) as f:
        return json.load(f)


def best_val_acc(run):
    """Extract best val accuracy from the epoch matching best_epoch."""
    best_ep = run.get("best_epoch", 0)
    for ep in run.get("epochs", []):
        if ep["epoch"] == best_ep:
            return ep.get("val_value_acc", None)
    # Fallback: check step_evals
    best_step = run.get("best_step", 0)
    for se in run.get("step_evals", []):
        if se["step"] == best_step:
            return se.get("val_value_acc", None)
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_seeds.py <run1.json> [run2.json] ...")
        sys.exit(1)

    paths = sys.argv[1:]
    runs = []
    for p in paths:
        if not os.path.exists(p):
            print(f"Warning: {p} not found, skipping")
            continue
        runs.append((p, load_run(p)))

    if not runs:
        print("No valid run files found.")
        sys.exit(1)

    # Check hyperparameter consistency (exclude seed)
    hp_keys_to_compare = None
    hp_mismatch = False
    for path, run in runs:
        hp = {k: v for k, v in run.get("hyperparameters", {}).items() if k != "seed"}
        if hp_keys_to_compare is None:
            hp_keys_to_compare = hp
        elif hp != hp_keys_to_compare:
            hp_mismatch = True

    if hp_mismatch:
        print("WARNING: Hyperparameters differ between runs!\n")
    else:
        hp = runs[0][1].get("hyperparameters", {})
        print(f"Comparing {len(runs)} runs (identical hyperparameters confirmed):")
        parts = []
        if "loss_fn" in hp:
            parts.append(f"Loss: {hp['loss_fn']}")
        if "lr" in hp:
            parts.append(f"LR: {hp['lr']}")
        if "hidden_dim" in hp:
            parts.append(f"Hidden: {hp['hidden_dim']}")
        if "dropout" in hp:
            parts.append(f"Dropout: {hp['dropout']}")
        if hp.get("tanh_in_training"):
            parts.append("tanh-in-training")
        if parts:
            print(f"  {', '.join(parts)}")
        print()

    # Build table
    headers = ["Seed", "Best Val Loss", "Best Val Acc", "Best Epoch", "Wall Time"]
    rows = []
    losses = []
    accs = []
    epochs = []
    times = []

    for path, run in runs:
        hp = run.get("hyperparameters", {})
        seed = hp.get("seed", "?")
        loss = run.get("best_val_value_loss")
        acc = best_val_acc(run)
        ep = run.get("best_epoch", "?")
        wt = run.get("total_wall_time_s")

        rows.append([
            str(seed),
            f"{loss:.6f}" if loss is not None else "?",
            f"{acc:.1f}%" if acc is not None else "?",
            str(ep),
            f"{wt:.0f}s" if wt is not None else "?",
        ])
        if loss is not None:
            losses.append(loss)
        if acc is not None:
            accs.append(acc)
        if isinstance(ep, (int, float)):
            epochs.append(ep)
        if wt is not None:
            times.append(wt)

    # Column widths
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]

    def fmt_row(vals):
        return "  " + " | ".join(v.rjust(w) for v, w in zip(vals, widths))

    sep = "  " + "-+-".join("-" * w for w in widths)

    print(fmt_row(headers))
    print(sep)
    for r in rows:
        print(fmt_row(r))

    if len(runs) >= 2:
        print(sep)
        summary_mean = [
            "Mean",
            f"{mean(losses):.6f}" if losses else "?",
            f"{mean(accs):.1f}%" if accs else "?",
            f"{mean(epochs):.1f}" if epochs else "?",
            f"{mean(times):.0f}s" if times else "?",
        ]
        print(fmt_row(summary_mean))

        if len(runs) >= 3:
            summary_std = [
                "Std",
                f"{stdev(losses):.6f}" if len(losses) >= 2 else "?",
                f"{stdev(accs):.1f}%" if len(accs) >= 2 else "?",
                f"{stdev(epochs):.1f}" if len(epochs) >= 2 else "?",
                f"{stdev(times):.0f}s" if len(times) >= 2 else "?",
            ]
            print(fmt_row(summary_std))


if __name__ == "__main__":
    main()
