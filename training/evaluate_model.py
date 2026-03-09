"""
Offline model evaluation for PrismataNet (Phase 5).

Evaluates a trained checkpoint on a test HDF5 file and produces diagnostic
reports: BCE loss, Brier score, value accuracy, ply-bucketed metrics,
calibration data, label distribution, and pairwise ranking accuracy.

Usage:
  python training/evaluate_model.py \
      --model training/models/run_001/best_model.pt \
      --test-file training/data/splits/test.h5 \
      --output training/models/run_001/eval_results.json
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict

import h5py
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


# ---------------------------------------------------------------------------
# Model (must match train.py exactly)
# ---------------------------------------------------------------------------

class ResBlock(nn.Module):
    def __init__(self, dim, dropout=0.0):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.fc2 = nn.Linear(dim, dim)
        self.norm = nn.LayerNorm(dim)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        residual = x
        h = F.relu(self.fc1(x))
        h = self.dropout(h)
        h = F.relu(self.fc2(h))
        return residual + self.norm(h)


class PrismataNet(nn.Module):
    def __init__(self, state_dim, num_units, hidden_dim=256, num_layers=4,
                 dropout=0.1, value_only=False):
        super().__init__()
        self.value_only = value_only
        self.state_dim = state_dim
        self.num_units = num_units
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.input_proj = nn.Linear(state_dim, hidden_dim)
        self.trunk = nn.ModuleList([
            ResBlock(hidden_dim, dropout=dropout) for _ in range(num_layers)
        ])
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )
        if not value_only:
            self.policy_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, num_units),
            )

    def forward(self, x):
        h = F.relu(self.input_proj(x))
        for block in self.trunk:
            h = block(h)
        value_logit = self.value_head(h).squeeze(-1)
        if self.value_only:
            return None, value_logit
        policy = self.policy_head(h)
        return policy, value_logit


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class TestDataset(Dataset):
    """Read-only HDF5 dataset for evaluation. Loads all data into RAM."""

    def __init__(self, h5_path, label_strategy="A"):
        self.h5_path = h5_path
        self.label_strategy = label_strategy

        with h5py.File(h5_path, "r") as f:
            self.features = f["features"][:].astype(np.float32)
            label_key = {"A": "label_A", "B": "label_A",
                         "C": "label_C", "D": "label_D"}[label_strategy]
            self.labels = f[label_key][:].astype(np.float32)

            # Metadata for ply-bucketed and pairwise analysis
            self.ply_index = None
            self.total_plies = None
            self.replay_code = None

            if "ply_index" in f:
                self.ply_index = f["ply_index"][:].astype(np.int32)
            if "total_plies" in f:
                self.total_plies = f["total_plies"][:].astype(np.int32)
            if "replay_codes" in f:
                # Could be stored as bytes or variable-length string
                raw = f["replay_codes"][:]
                if raw.dtype.kind in ("S", "O"):
                    self.replay_code = np.array([
                        x.decode("utf-8") if isinstance(x, bytes) else str(x)
                        for x in raw
                    ])
                else:
                    self.replay_code = raw.astype(str)

        self.n = self.features.shape[0]
        self.state_dim = self.features.shape[1]

    def __len__(self):
        return self.n

    def __getitem__(self, idx):
        return (torch.from_numpy(self.features[idx]),
                torch.tensor(self.labels[idx], dtype=torch.float32))


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

@torch.no_grad()
def run_inference(model, dataset, device, batch_size=1024):
    """Run model on full dataset, return (logits, labels) as numpy arrays."""
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False,
                        num_workers=0)
    all_logits = []
    all_labels = []

    model.eval()
    for features, labels in loader:
        features = features.to(device)
        _, logits = model(features)
        all_logits.append(logits.cpu().numpy())
        all_labels.append(labels.numpy())

    return np.concatenate(all_logits), np.concatenate(all_labels)


def compute_bce_loss(logits, labels):
    """Binary cross-entropy loss (with logits)."""
    t_logits = torch.from_numpy(logits)
    t_labels = torch.from_numpy(labels)
    return F.binary_cross_entropy_with_logits(t_logits, t_labels).item()


def compute_brier_score(logits, labels):
    """Mean squared error between sigmoid(logit) and label."""
    probs = 1.0 / (1.0 + np.exp(-logits))
    return float(np.mean((probs - labels) ** 2))


def compute_value_accuracy(logits, labels):
    """Fraction where predicted winner matches actual winner."""
    pred_p0_wins = logits > 0  # sigmoid(logit) > 0.5
    actual_p0_wins = labels > 0.5
    return float(np.mean(pred_p0_wins == actual_p0_wins))


def compute_ply_bucketed_metrics(logits, labels, ply_indices):
    """Report loss and accuracy bucketed by game phase.

    Buckets: early (plies 1-8), mid (9-18), late (19+).
    """
    buckets = {
        "early_1_8": (1, 8),
        "mid_9_18": (9, 18),
        "late_19_plus": (19, 999999),
    }
    results = {}
    for name, (lo, hi) in buckets.items():
        mask = (ply_indices >= lo) & (ply_indices <= hi)
        n = int(mask.sum())
        if n == 0:
            results[name] = {"n": 0, "bce_loss": None, "brier": None,
                             "accuracy": None}
            continue
        bl = logits[mask]
        bt = labels[mask]
        results[name] = {
            "n": n,
            "bce_loss": round(compute_bce_loss(bl, bt), 6),
            "brier": round(compute_brier_score(bl, bt), 6),
            "accuracy": round(compute_value_accuracy(bl, bt), 4),
        }
    return results


def compute_calibration_data(logits, labels, n_bins=10):
    """Binned calibration: predicted probability vs actual win rate.

    Returns list of dicts with bin edges, mean predicted, mean actual, count.
    """
    probs = 1.0 / (1.0 + np.exp(-logits))
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n = int(mask.sum())
        if n == 0:
            bins.append({
                "bin_lo": round(float(lo), 2),
                "bin_hi": round(float(hi), 2),
                "n": 0,
                "mean_predicted": None,
                "mean_actual": None,
            })
        else:
            bins.append({
                "bin_lo": round(float(lo), 2),
                "bin_hi": round(float(hi), 2),
                "n": n,
                "mean_predicted": round(float(probs[mask].mean()), 4),
                "mean_actual": round(float(labels[mask].mean()), 4),
            })
    return bins


def compute_label_distribution(labels):
    """Analyze label distribution."""
    return {
        "n": int(len(labels)),
        "mean": round(float(labels.mean()), 4),
        "std": round(float(labels.std()), 4),
        "min": round(float(labels.min()), 4),
        "max": round(float(labels.max()), 4),
        "p0_wins_frac": round(float((labels > 0.5).mean()), 4),
        "draws_frac": round(float((labels == 0.5).mean()), 4),
        "p1_wins_frac": round(float((labels < 0.5).mean()), 4),
        "median": round(float(np.median(labels)), 4),
    }


def compute_pairwise_ranking_accuracy(logits, labels, replay_codes):
    """Pairwise ranking: for positions from the same game, how often does
    the model assign higher value to the winner's-turn position vs the
    loser's-turn position.

    Groups positions by replay_code (game). Within each game, forms pairs
    (winner-turn position, loser-turn position) and checks if the model
    correctly ranks the winner's position higher.

    Returns accuracy and number of pairs evaluated.
    """
    if replay_codes is None:
        return {"accuracy": None, "n_pairs": 0,
                "note": "No replay_code in test file; cannot compute pairwise"}

    probs = 1.0 / (1.0 + np.exp(-logits))

    # Group indices by game
    game_indices = defaultdict(list)
    for i, code in enumerate(replay_codes):
        game_indices[code].append(i)

    correct = 0
    total = 0

    for code, indices in game_indices.items():
        if len(indices) < 2:
            continue

        idx_arr = np.array(indices)
        game_labels = labels[idx_arr]
        game_probs = probs[idx_arr]

        # Separate winner-turn positions (label > 0.5) from loser-turn
        winner_mask = game_labels > 0.5
        loser_mask = game_labels < 0.5

        if not winner_mask.any() or not loser_mask.any():
            continue

        winner_probs = game_probs[winner_mask]
        loser_probs = game_probs[loser_mask]

        # Compare every winner position with every loser position
        # For efficiency, use broadcasting on small arrays (per-game)
        n_w = len(winner_probs)
        n_l = len(loser_probs)

        # Cap pairs per game to avoid O(n^2) explosion on long games
        max_pairs_per_game = 100
        if n_w * n_l > max_pairs_per_game:
            # Sample a subset
            w_sample = np.random.choice(n_w, min(n_w, 10), replace=False)
            l_sample = np.random.choice(n_l, min(n_l, 10), replace=False)
            winner_probs = winner_probs[w_sample]
            loser_probs = loser_probs[l_sample]

        # winner_probs[:, None] > loser_probs[None, :] broadcasts
        comparisons = winner_probs[:, None] > loser_probs[None, :]
        correct += int(comparisons.sum())
        total += comparisons.size

    if total == 0:
        return {"accuracy": None, "n_pairs": 0,
                "note": "No valid pairs found"}

    return {
        "accuracy": round(correct / total, 4),
        "n_pairs": total,
        "n_games_with_pairs": sum(
            1 for indices in game_indices.values()
            if len(indices) >= 2
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate PrismataNet on test data")
    parser.add_argument("--model", type=str, required=True,
                        help="Path to model checkpoint (.pt)")
    parser.add_argument("--test-file", type=str, required=True,
                        help="Path to test HDF5 file")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: eval_results.json "
                             "next to model)")
    parser.add_argument("--batch-size", type=int, default=1024,
                        help="Inference batch size (default 1024)")
    parser.add_argument("--device", type=str, default="auto",
                        choices=["auto", "cpu", "xpu", "cuda"],
                        help="Device (default: auto-detect)")
    parser.add_argument("--label-strategy", type=str, default=None,
                        help="Label strategy override (default: read from "
                             "checkpoint)")
    parser.add_argument("--calibration-bins", type=int, default=10,
                        help="Number of calibration bins (default 10)")
    args = parser.parse_args()

    # --- Load checkpoint ---
    print(f"Loading checkpoint: {args.model}")
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=False)

    state_dim = checkpoint["state_dim"]
    num_units = checkpoint["num_units"]
    hidden_dim = checkpoint.get("hidden_dim", 256)
    num_layers = checkpoint.get("num_layers", 4)
    value_only = checkpoint.get("value_only", False)
    dropout = checkpoint.get("dropout", 0.1)
    label_strategy = args.label_strategy or checkpoint.get("label_strategy", "A")

    print(f"  state_dim={state_dim}, num_units={num_units}, "
          f"hidden_dim={hidden_dim}, num_layers={num_layers}")
    print(f"  value_only={value_only}, label_strategy={label_strategy}")
    if "epoch" in checkpoint:
        print(f"  checkpoint epoch={checkpoint['epoch']}")

    # --- Device ---
    if args.device == "auto":
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            device = torch.device("xpu")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)
    print(f"  device={device}")

    # --- Build model ---
    model = PrismataNet(state_dim, num_units, hidden_dim=hidden_dim,
                        num_layers=num_layers, dropout=dropout,
                        value_only=value_only)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  parameters={param_count:,}")

    # --- Load test data ---
    print(f"\nLoading test data: {args.test_file}")
    dataset = TestDataset(args.test_file, label_strategy=label_strategy)
    print(f"  {dataset.n:,} examples, state_dim={dataset.state_dim}")

    if dataset.state_dim != state_dim:
        print(f"  ERROR: Test state_dim={dataset.state_dim} != "
              f"model state_dim={state_dim}")
        sys.exit(1)

    # --- Run inference ---
    print("\nRunning inference...")
    t0 = time.time()
    logits, labels = run_inference(model, dataset, device,
                                   batch_size=args.batch_size)
    elapsed = time.time() - t0
    print(f"  {dataset.n:,} examples in {elapsed:.1f}s "
          f"({dataset.n / elapsed:.0f} examples/s)")

    # --- Compute metrics ---
    print("\nComputing metrics...")

    # Overall metrics
    bce = compute_bce_loss(logits, labels)
    brier = compute_brier_score(logits, labels)
    accuracy = compute_value_accuracy(logits, labels)
    print(f"  BCE loss:       {bce:.6f}")
    print(f"  Brier score:    {brier:.6f}")
    print(f"  Value accuracy: {accuracy:.4f} ({accuracy:.1%})")

    # Prediction distribution
    probs = 1.0 / (1.0 + np.exp(-logits))
    pred_stats = {
        "mean": round(float(probs.mean()), 4),
        "std": round(float(probs.std()), 4),
        "min": round(float(probs.min()), 4),
        "max": round(float(probs.max()), 4),
        "median": round(float(np.median(probs)), 4),
    }

    # Label distribution
    label_dist = compute_label_distribution(labels)
    print(f"  Label dist: mean={label_dist['mean']:.4f}, "
          f"P0 wins={label_dist['p0_wins_frac']:.1%}")

    # Ply-bucketed metrics
    ply_metrics = None
    if dataset.ply_index is not None:
        print("\n  Ply-bucketed metrics:")
        ply_metrics = compute_ply_bucketed_metrics(
            logits, labels, dataset.ply_index)
        for bucket, m in ply_metrics.items():
            if m["n"] > 0:
                print(f"    {bucket:16s}: n={m['n']:>6,}  "
                      f"BCE={m['bce_loss']:.4f}  "
                      f"Brier={m['brier']:.4f}  "
                      f"Acc={m['accuracy']:.1%}")
            else:
                print(f"    {bucket:16s}: (no examples)")
    else:
        print("\n  Ply-bucketed metrics: SKIPPED (no ply_index in test file)")

    # Calibration
    calibration = compute_calibration_data(logits, labels,
                                            n_bins=args.calibration_bins)
    print(f"\n  Calibration ({args.calibration_bins} bins):")
    print(f"    {'Bin':>10s}  {'N':>7s}  {'Predicted':>9s}  {'Actual':>7s}  "
          f"{'Gap':>6s}")
    for b in calibration:
        if b["n"] > 0:
            gap = abs(b["mean_predicted"] - b["mean_actual"])
            print(f"    [{b['bin_lo']:.1f},{b['bin_hi']:.1f})  "
                  f"{b['n']:>7,}  "
                  f"{b['mean_predicted']:>9.4f}  "
                  f"{b['mean_actual']:>7.4f}  "
                  f"{gap:>6.4f}")
        else:
            print(f"    [{b['bin_lo']:.1f},{b['bin_hi']:.1f})  "
                  f"{'---':>7s}  {'---':>9s}  {'---':>7s}  {'---':>6s}")

    # Pairwise ranking accuracy
    print("\n  Pairwise ranking accuracy:")
    pairwise = compute_pairwise_ranking_accuracy(
        logits, labels, dataset.replay_code)
    if pairwise["accuracy"] is not None:
        print(f"    Accuracy: {pairwise['accuracy']:.4f} "
              f"({pairwise['accuracy']:.1%})")
        print(f"    Pairs evaluated: {pairwise['n_pairs']:,}")
        print(f"    Games with pairs: {pairwise.get('n_games_with_pairs', '?')}")
    else:
        print(f"    {pairwise.get('note', 'N/A')}")

    # --- Build results dict ---
    results = {
        "model_path": os.path.abspath(args.model),
        "test_file": os.path.abspath(args.test_file),
        "n_examples": dataset.n,
        "state_dim": state_dim,
        "num_units": num_units,
        "hidden_dim": hidden_dim,
        "num_layers": num_layers,
        "value_only": value_only,
        "label_strategy": label_strategy,
        "parameters": param_count,
        "checkpoint_epoch": checkpoint.get("epoch"),
        "inference_time_s": round(elapsed, 2),
        "overall_metrics": {
            "bce_loss": round(bce, 6),
            "brier_score": round(brier, 6),
            "value_accuracy": round(accuracy, 4),
        },
        "prediction_distribution": pred_stats,
        "label_distribution": label_dist,
        "calibration_bins": calibration,
        "pairwise_ranking": pairwise,
    }
    if ply_metrics is not None:
        results["ply_bucketed_metrics"] = ply_metrics

    # --- Save results ---
    if args.output is None:
        output_path = os.path.join(os.path.dirname(args.model),
                                    "eval_results.json")
    else:
        output_path = args.output

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  BCE Loss:          {bce:.6f}")
    print(f"  Brier Score:       {brier:.6f}  "
          f"(chance=0.2500)")
    print(f"  Value Accuracy:    {accuracy:.1%}  "
          f"(chance=50.0%)")
    if pairwise["accuracy"] is not None:
        print(f"  Pairwise Ranking:  {pairwise['accuracy']:.1%}  "
              f"(chance=50.0%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
