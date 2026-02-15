"""
Train policy (buy prediction) and value (win prediction) networks
on vectorized Prismata expert replay data.

Architecture:
  - Shared trunk: MLP with residual connections + dropout
  - Policy head: predicts buy counts per unit type (regression/Poisson)
  - Value head: predicts win probability for active player (tanh)

Supports:
  - Intel Arc GPU via IPEX (torch.xpu)
  - NVIDIA GPU via CUDA (torch.cuda)
  - CPU fallback with multi-worker DataLoader
  - Value-only mode (--value-only) for faster training/inference
  - Configurable architecture (--hidden-dim, --num-layers)
  - Overfit test (--overfit-test) to verify architecture can learn
  - Label smoothing (--label-smooth) to prevent tanh saturation
  - Early stopping (--patience) on validation value loss

Usage:
  python train.py [data_dir] [model_dir] [--epochs 100] [--batch-size 512]
  python train.py --overfit-test  # Quick architecture validation
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, "C:/libraries/torch_pkg")
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset, ConcatDataset


def load_unit_index(path):
    """Load unit name->index mapping, supporting both old and new formats.

    Old format: {"Drone": 0, "Engineer": 1, ...}
    New format: {"version": "...", "count": 161, "units": {"Drone": 0, ...}}
    """
    with open(path) as f:
        data = json.load(f)
    if "units" in data and "version" in data:
        return data["units"]
    return data


def get_device():
    """Detect best available device: Intel XPU > CUDA > CPU."""
    # Try Intel Arc (IPEX)
    try:
        import intel_extension_for_pytorch as ipex
        if torch.xpu.is_available():
            dev = torch.device("xpu")
            print(f"Device: Intel XPU ({torch.xpu.get_device_name(0)})")
            return dev
    except (ImportError, AttributeError):
        pass

    # Try NVIDIA CUDA
    if torch.cuda.is_available():
        dev = torch.device("cuda")
        print(f"Device: CUDA ({torch.cuda.get_device_name(0)})")
        return dev

    print("Device: CPU")
    return torch.device("cpu")


class PrismataNet(nn.Module):
    """Combined policy + value network for Prismata."""

    def __init__(self, state_dim, num_units, hidden_dim=512, num_layers=4,
                 dropout=0.1, value_only=False):
        super().__init__()
        self.value_only = value_only

        # Shared trunk with residual connections
        self.input_proj = nn.Linear(state_dim, hidden_dim)
        self.trunk_layers = nn.ModuleList()
        for _ in range(num_layers):
            self.trunk_layers.append(nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
            ))

        # Policy head: predict buy counts for each unit type
        if not value_only:
            self.policy_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, num_units),
            )

        # Value head: predict win probability (raw logit, NO tanh here)
        # Tanh is applied manually for metrics/inference only.
        # Training loss uses raw logit to avoid gradient death through saturated tanh.
        # C++ NeuralNet.cpp applies tanhf() during inference, matching this design.
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
        )

    def forward(self, x):
        h = F.relu(self.input_proj(x))

        for layer in self.trunk_layers:
            h = h + F.relu(layer(h))  # Residual

        value_logit = self.value_head(h).squeeze(-1)  # Raw logit, unbounded

        if self.value_only:
            return None, value_logit

        policy = self.policy_head(h)  # Raw logits / counts
        return policy, value_logit


def policy_loss_fn(pred, target):
    """Loss for buy prediction.

    Target is buy counts (e.g., [0, 0, 2, 0, 1, ...] meaning 2 Drones, 1 Wall).
    Use Poisson-like loss: MSE on counts, plus cross-entropy on "did buy anything".
    """
    # MSE on buy counts
    mse = F.mse_loss(pred, target)

    # Also penalize predicting buys for units not bought and vice versa
    target_binary = (target > 0).float()
    bce = F.binary_cross_entropy_with_logits(pred, target_binary)

    return mse + 0.5 * bce


def value_loss_fn(pred, target):
    """Loss for win prediction. MSE on [-1, 1] range."""
    return F.mse_loss(pred, target)


def compute_policy_accuracy(pred, target):
    """Accuracy: what fraction of examples have the exact same buy set."""
    pred_set = (pred > 0.5).float()
    target_set = (target > 0).float()
    # Match if all unit buy/no-buy decisions are correct
    match = (pred_set == target_set).all(dim=1).float()
    return match.mean().item()


def compute_value_accuracy(pred_logit, target):
    """Accuracy: what fraction correctly predict winner.

    pred_logit is the raw pre-tanh value. Sign of logit matches sign of tanh(logit),
    so we can compare signs directly without applying tanh.
    """
    pred_sign = (pred_logit > 0).float() * 2 - 1  # Convert to {-1, 1}
    target_sign = (target > 0).float() * 2 - 1
    return (pred_sign == target_sign).float().mean().item()


def check_label_sanity(train_data, val_data):
    """Pre-training sanity check on labels. Refuses to train if labels look broken."""
    print("\n--- Label Sanity Check ---")
    ok = True

    for name, data in [("Train", train_data), ("Val", val_data)]:
        values = data["values"]
        buys = data["buy_targets"]

        # Value label stats
        v_min = values.min().item()
        v_max = values.max().item()
        v_mean = values.mean().item()
        v_std = values.std().item()
        n_pos = (values > 0).sum().item()
        n_neg = (values < 0).sum().item()
        n_zero = (values == 0).sum().item()
        n_total = len(values)

        print(f"  {name} values: n={n_total}, min={v_min:.3f}, max={v_max:.3f}, "
              f"mean={v_mean:.3f}, std={v_std:.3f}")
        print(f"    +1: {n_pos} ({100*n_pos/n_total:.1f}%), "
              f"-1: {n_neg} ({100*n_neg/n_total:.1f}%), "
              f"0: {n_zero} ({100*n_zero/n_total:.1f}%)")

        if v_std < 0.01:
            print(f"  FATAL: {name} value labels have std={v_std:.6f} < 0.01 — all labels are ~constant!")
            ok = False

        if v_min == v_max:
            print(f"  FATAL: {name} value labels are all identical ({v_min})!")
            ok = False

        # Policy label stats
        sparsity = (buys == 0).float().mean().item()
        avg_types = (buys > 0).float().sum(dim=1).mean().item()
        avg_total = buys.sum(dim=1).mean().item()
        top_k_freq = buys.sum(dim=0).topk(5)
        idx_to_name = None  # We don't have unit_index here, just show indices

        print(f"  {name} policy: sparsity={sparsity:.4%}, avg_types_bought={avg_types:.2f}, "
              f"avg_total_buys={avg_total:.2f}")

    if not ok:
        print("\nFATAL: Label sanity check failed. Refusing to train.")
        print("Check your data pipeline (vectorize.py) and training data.")
        sys.exit(1)

    print("  Label sanity check: PASSED\n")


def train_epoch(model, loader, optimizer, device, policy_weight=0.5):
    """Train one epoch, return (policy_loss, value_loss, policy_acc, value_acc, value_stats)."""
    model.train()
    total_ploss = 0
    total_vloss = 0
    total_pacc = 0
    total_vacc = 0
    n_batches = 0
    n_policy_batches = 0
    all_vpreds = []

    for batch in loader:
        states, buys, values_target = batch[0], batch[1], batch[2]
        has_policy = batch[4] if len(batch) > 4 else torch.ones(states.shape[0])

        states = states.to(device)
        buys = buys.to(device)
        values_target = values_target.to(device)
        has_policy = has_policy.to(device)

        optimizer.zero_grad()
        policy_pred, value_pred = model(states)

        vloss = value_loss_fn(value_pred, values_target)

        if policy_pred is not None:
            # Only compute policy loss on records that have policy targets
            policy_mask = has_policy > 0.5
            if policy_mask.any():
                ploss = policy_loss_fn(policy_pred[policy_mask], buys[policy_mask])
                loss = vloss + policy_weight * ploss
                total_ploss += ploss.item()
                total_pacc += compute_policy_accuracy(policy_pred[policy_mask], buys[policy_mask])
                n_policy_batches += 1
            else:
                loss = vloss
        else:
            loss = vloss

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        total_vloss += vloss.item()
        total_vacc += compute_value_accuracy(value_pred, values_target)
        all_vpreds.append(value_pred.detach().cpu())
        n_batches += 1

    # Compute value prediction statistics for saturation monitoring
    # Apply tanh for display/monitoring purposes (training uses raw logits)
    all_vpreds = torch.cat(all_vpreds)
    all_vpreds_tanh = torch.tanh(all_vpreds)
    value_stats = {
        "mean": all_vpreds_tanh.mean().item(),
        "std": all_vpreds_tanh.std().item(),
        "min": all_vpreds_tanh.min().item(),
        "max": all_vpreds_tanh.max().item(),
        "saturated_frac": ((all_vpreds_tanh.abs() > 0.95).float().mean().item()),
    }

    return (
        total_ploss / max(n_policy_batches, 1),
        total_vloss / max(n_batches, 1),
        total_pacc / max(n_policy_batches, 1),
        total_vacc / max(n_batches, 1),
        value_stats,
    )


@torch.no_grad()
def eval_epoch(model, loader, device, policy_weight=0.5):
    """Evaluate one epoch, return (policy_loss, value_loss, policy_acc, value_acc, value_stats)."""
    model.eval()
    total_ploss = 0
    total_vloss = 0
    total_pacc = 0
    total_vacc = 0
    n_batches = 0
    n_policy_batches = 0
    all_vpreds = []

    for batch in loader:
        states, buys, values_target = batch[0], batch[1], batch[2]
        has_policy = batch[4] if len(batch) > 4 else torch.ones(states.shape[0])

        states = states.to(device)
        buys = buys.to(device)
        values_target = values_target.to(device)
        has_policy = has_policy.to(device)

        policy_pred, value_pred = model(states)

        vloss = value_loss_fn(value_pred, values_target)

        if policy_pred is not None:
            policy_mask = has_policy > 0.5
            if policy_mask.any():
                ploss = policy_loss_fn(policy_pred[policy_mask], buys[policy_mask])
                total_ploss += ploss.item()
                total_pacc += compute_policy_accuracy(policy_pred[policy_mask], buys[policy_mask])
                n_policy_batches += 1

        total_vloss += vloss.item()
        total_vacc += compute_value_accuracy(value_pred, values_target)
        all_vpreds.append(value_pred.cpu())
        n_batches += 1

    all_vpreds = torch.cat(all_vpreds)
    all_vpreds_tanh = torch.tanh(all_vpreds)
    value_stats = {
        "mean": all_vpreds_tanh.mean().item(),
        "std": all_vpreds_tanh.std().item(),
        "min": all_vpreds_tanh.min().item(),
        "max": all_vpreds_tanh.max().item(),
        "saturated_frac": ((all_vpreds_tanh.abs() > 0.95).float().mean().item()),
    }

    return (
        total_ploss / max(n_policy_batches, 1),
        total_vloss / max(n_batches, 1),
        total_pacc / max(n_policy_batches, 1),
        total_vacc / max(n_batches, 1),
        value_stats,
    )


def apply_label_smoothing(values, smooth=0.95):
    """Smooth binary value targets to avoid tanh saturation.

    Maps +1 -> +smooth, -1 -> -smooth, 0 stays 0.
    This prevents the tanh output from needing to saturate to match targets,
    keeping gradients alive throughout training.
    """
    return values * smooth


def get_git_hash():
    """Get current git commit hash, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def get_schema_hash(data_dir):
    """Hash the schema.json file if it exists."""
    schema_path = os.path.join(data_dir, "..", "schema.json")
    if os.path.exists(schema_path):
        with open(schema_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    return "no_schema"


def load_selfplay_data(selfplay_dir, num_units, label_smooth=0.95):
    """Load self-play binary data and split into train/val by game_id.

    Split: game_id % 10 == 0 goes to val (deterministic, stable across runs).
    CRITICAL: Split by game_id, NOT by record — all records from same game share
    the same outcome label, so per-record splitting causes massive data leakage.

    Self-play records have no policy targets — buy_targets are set to zero.
    A has_policy mask tensor is included so the loss function can skip policy
    loss on self-play records.

    Returns:
        (train_data, val_data) dicts with keys: states, buy_targets, values, turns, has_policy
    """
    # Import here to avoid circular dependency at module level
    from load_selfplay import load_all_shards

    records = load_all_shards(selfplay_dir)
    if records is None:
        print("FATAL: No self-play data loaded.")
        sys.exit(1)

    # Validate
    features = records['features']
    if np.any(np.isnan(features)):
        print("FATAL: NaN found in self-play features")
        sys.exit(1)
    if np.any(np.isinf(features)):
        print("FATAL: Inf found in self-play features")
        sys.exit(1)

    outcomes = records['outcome']
    game_ids = records['game_id']
    turn_numbers = records['turn_number']

    n = len(records)
    state_dim = features.shape[1]

    # Split by game_id
    val_mask = (game_ids % 10) == 0
    train_mask = ~val_mask

    def make_dict(mask):
        states = torch.from_numpy(features[mask].copy())
        values = torch.from_numpy(outcomes[mask].copy())
        turns = torch.from_numpy(turn_numbers[mask].astype(np.float32).copy())
        buy_targets = torch.zeros(mask.sum(), num_units)  # no policy targets for self-play
        has_policy = torch.zeros(mask.sum())  # 0 = skip policy loss

        # Apply label smoothing
        if label_smooth < 1.0:
            values = values * label_smooth

        return {
            'states': states,
            'buy_targets': buy_targets,
            'values': values,
            'turns': turns,
            'has_policy': has_policy,
        }

    train_data = make_dict(train_mask)
    val_data = make_dict(val_mask)

    n_train = train_mask.sum()
    n_val = val_mask.sum()
    n_games = len(np.unique(game_ids))
    n_train_games = len(np.unique(game_ids[train_mask]))
    n_val_games = len(np.unique(game_ids[val_mask]))

    print(f"  Self-play data loaded from {selfplay_dir}")
    print(f"    Total: {n:,} records from {n_games:,} games")
    print(f"    Train: {n_train:,} records from {n_train_games:,} games")
    print(f"    Val:   {n_val:,} records from {n_val_games:,} games")
    print(f"    Outcomes: +1: {(outcomes > 0.5).sum():,}  "
          f"-1: {(outcomes < -0.5).sum():,}  "
          f"0: {(np.abs(outcomes) < 0.5).sum():,}")

    return train_data, val_data


def run_overfit_test(args):
    """Tiny-subset overfit test: verify the architecture can learn.

    Takes 256 examples, trains for 200 epochs with high LR,
    asserts training loss drops >50% and predictions span >80% of target range.
    """
    print("\n=== OVERFIT TEST ===")
    print("Testing that the architecture can learn from a tiny subset...\n")

    device = get_device()

    # Load data
    train_data = torch.load(os.path.join(args.data_dir, "train.pt"), weights_only=True)

    unit_index = load_unit_index(os.path.join(args.data_dir, "unit_index.json"))

    state_dim = train_data["states"].shape[1]
    num_units = len(unit_index)

    # Take 256 examples
    n_subset = min(256, train_data["states"].shape[0])
    states = train_data["states"][:n_subset].to(device)
    buys = train_data["buy_targets"][:n_subset].to(device)
    values = train_data["values"][:n_subset].to(device)

    # Apply label smoothing
    values_smooth = apply_label_smoothing(values, args.label_smooth)

    print(f"  Subset: {n_subset} examples, state_dim={state_dim}, num_units={num_units}")
    print(f"  Value targets: min={values.min():.3f}, max={values.max():.3f}, "
          f"mean={values.mean():.3f}, std={values.std():.3f}")
    print(f"  Label smoothing: {args.label_smooth}")

    model = PrismataNet(state_dim, num_units, hidden_dim=args.hidden_dim,
                        num_layers=args.num_layers, dropout=0.0,  # No dropout for overfit test
                        value_only=args.value_only).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    initial_vloss = None
    final_vloss = None

    for epoch in range(1, 201):
        model.train()
        optimizer.zero_grad()

        policy_pred, value_pred = model(states)
        vloss = value_loss_fn(value_pred, values_smooth)

        if policy_pred is not None:
            ploss = policy_loss_fn(policy_pred, buys)
            loss = vloss + args.policy_weight * ploss
        else:
            loss = vloss

        loss.backward()
        optimizer.step()

        vl = vloss.item()
        if epoch == 1:
            initial_vloss = vl
        final_vloss = vl

        if epoch % 50 == 0 or epoch == 1:
            with torch.no_grad():
                _, vp = model(states)
            print(f"  Epoch {epoch:3d}: vloss={vl:.4f}, vpred range=[{vp.min():.3f}, {vp.max():.3f}], "
                  f"vpred mean={vp.mean():.3f}, vpred std={vp.std():.3f}")

    # Final evaluation
    model.eval()
    with torch.no_grad():
        _, final_vpred_logit = model(states)

    # Apply tanh for range comparison (model outputs raw logits)
    final_vpred = torch.tanh(final_vpred_logit)
    pred_range = final_vpred.max().item() - final_vpred.min().item()
    # Compare against tanh-applied smoothed targets
    target_tanh = torch.tanh(values_smooth)
    target_range = target_tanh.max().item() - target_tanh.min().item()
    range_coverage = pred_range / target_range if target_range > 0 else 0
    loss_reduction = 1.0 - (final_vloss / initial_vloss) if initial_vloss > 0 else 0

    print(f"\n  Results:")
    print(f"    Initial value loss: {initial_vloss:.4f}")
    print(f"    Final value loss:   {final_vloss:.4f}")
    print(f"    Loss reduction:     {loss_reduction:.1%} (need >50%)")
    print(f"    Prediction range:   {pred_range:.3f} (tanh) / {target_range:.3f} = {range_coverage:.1%} coverage (need >80%)")
    print(f"    Prediction stats:   mean={final_vpred.mean():.3f}, std={final_vpred.std():.3f} (tanh-applied)")

    # Assertions
    passed = True
    if loss_reduction < 0.50:
        print(f"\n  FAIL: Loss only reduced by {loss_reduction:.1%}, need >50%")
        passed = False
    if range_coverage < 0.80:
        print(f"\n  FAIL: Predictions only span {range_coverage:.1%} of target range, need >80%")
        passed = False

    if passed:
        print(f"\n  OVERFIT TEST PASSED")
    else:
        print(f"\n  OVERFIT TEST FAILED")
        print(f"  The architecture may not be able to learn from this data.")
        print(f"  Check: label encoding, feature encoding, architecture dimensions.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Train Prismata neural network")
    parser.add_argument("data_dir", nargs="?", default="c:/libraries/PrismataAI/training/data")
    parser.add_argument("model_dir", nargs="?", default="c:/libraries/PrismataAI/training/models")
    parser.add_argument("--value-only", action="store_true", help="Train value head only (no policy)")
    parser.add_argument("--hidden-dim", type=int, default=512)
    parser.add_argument("--num-layers", type=int, default=2, help="Trunk residual blocks (default 2, matching Churchill)")
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--warmup-epochs", type=int, default=5)
    parser.add_argument("--policy-weight", type=float, default=0.5,
                        help="Weight for policy loss relative to value loss (default 0.5)")
    parser.add_argument("--label-smooth", type=float, default=0.95,
                        help="Label smoothing for value targets: +/-1 -> +/-smooth (default 0.95)")
    parser.add_argument("--patience", type=int, default=10,
                        help="Early stopping patience on val value loss (0=disabled)")
    parser.add_argument("--num-workers", type=int, default=8, help="DataLoader workers")
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint path")
    parser.add_argument("--overfit-test", action="store_true",
                        help="Run tiny-subset overfit test and exit")
    parser.add_argument("--selfplay-dir", type=str, default=None,
                        help="Directory with binary self-play shards (selfplay_t*_s*.bin)")
    parser.add_argument("--expert-weight", type=float, default=0.5,
                        help="Fraction of training data from expert replays when mixing (default 0.5)")
    args = parser.parse_args()

    # Overfit test: quick architecture validation
    if args.overfit_test:
        run_overfit_test(args)
        return

    os.makedirs(args.model_dir, exist_ok=True)

    device = get_device()

    # Load data
    print("Loading training data...")

    unit_index = load_unit_index(os.path.join(args.data_dir, "unit_index.json"))
    num_units = len(unit_index)

    if args.selfplay_dir:
        # Self-play mode: load binary shards, optionally mix with expert data
        sp_train, sp_val = load_selfplay_data(
            args.selfplay_dir, num_units, label_smooth=args.label_smooth)

        state_dim = sp_train["states"].shape[1]

        if args.expert_weight > 0:
            # Also load expert data and mix
            expert_train_path = os.path.join(args.data_dir, "train.pt")
            expert_val_path = os.path.join(args.data_dir, "val.pt")
            if os.path.exists(expert_train_path):
                print(f"  Loading expert data for mixing (weight={args.expert_weight})...")
                expert_train = torch.load(expert_train_path, weights_only=True)
                expert_val = torch.load(expert_val_path, weights_only=True)

                # Apply label smoothing to expert data
                if args.label_smooth < 1.0:
                    expert_train["values"] = apply_label_smoothing(
                        expert_train["values"], args.label_smooth)
                    expert_val["values"] = apply_label_smoothing(
                        expert_val["values"], args.label_smooth)

                # Add has_policy=1 marker to expert data (expert has policy targets)
                expert_train["has_policy"] = torch.ones(expert_train["states"].shape[0])
                expert_val["has_policy"] = torch.ones(expert_val["states"].shape[0])

                # Subsample to achieve desired expert_weight ratio
                # expert_weight = expert_n / (expert_n + selfplay_n)
                # => expert_n = selfplay_n * expert_weight / (1 - expert_weight)
                sp_n = sp_train["states"].shape[0]
                desired_expert_n = int(sp_n * args.expert_weight / max(1e-9, 1.0 - args.expert_weight))
                available_expert_n = expert_train["states"].shape[0]

                if desired_expert_n < available_expert_n:
                    # Subsample expert data (only tensor values, skip metadata dicts)
                    perm = torch.randperm(available_expert_n)[:desired_expert_n]
                    expert_train = {
                        k: v[perm] if isinstance(v, torch.Tensor) else v
                        for k, v in expert_train.items()
                    }
                    print(f"    Expert subsampled: {available_expert_n:,} -> {desired_expert_n:,}")
                else:
                    print(f"    Using all {available_expert_n:,} expert examples "
                          f"(effective weight: {available_expert_n / (available_expert_n + sp_n):.2f})")

                # Concatenate self-play and expert data (only shared tensor keys)
                shared_keys = [k for k in sp_train if k in expert_train
                               and isinstance(sp_train[k], torch.Tensor)
                               and isinstance(expert_train[k], torch.Tensor)]
                train_data = {
                    k: torch.cat([sp_train[k], expert_train[k]], dim=0)
                    for k in shared_keys
                }
                val_data = {
                    k: torch.cat([sp_val[k], expert_val[k]], dim=0)
                    for k in shared_keys
                }
                print(f"  Mixed training data: {train_data['states'].shape[0]:,} train, "
                      f"{val_data['states'].shape[0]:,} val")
            else:
                print(f"  WARNING: Expert data not found at {expert_train_path}, using self-play only")
                train_data = sp_train
                val_data = sp_val
        else:
            train_data = sp_train
            val_data = sp_val
    else:
        # Standard expert-only mode
        train_data = torch.load(os.path.join(args.data_dir, "train.pt"), weights_only=True)
        val_data = torch.load(os.path.join(args.data_dir, "val.pt"), weights_only=True)

        state_dim = train_data["states"].shape[1]

        # Add has_policy=1 for expert data (all have policy targets)
        train_data["has_policy"] = torch.ones(train_data["states"].shape[0])
        val_data["has_policy"] = torch.ones(val_data["states"].shape[0])

        # Apply label smoothing to value targets
        if args.label_smooth < 1.0:
            print(f"  Label smoothing: {args.label_smooth} (targets +/-1 -> +/-{args.label_smooth})")
            train_data["values"] = apply_label_smoothing(train_data["values"], args.label_smooth)
            val_data["values"] = apply_label_smoothing(val_data["values"], args.label_smooth)

    print(f"  Train: {train_data['states'].shape[0]} examples")
    print(f"  Val: {val_data['states'].shape[0]} examples")
    print(f"  State dim: {state_dim}")
    print(f"  Unit types: {num_units}")
    print(f"  Mode: {'value-only' if args.value_only else 'policy+value'}")

    # Pre-training label sanity check
    check_label_sanity(train_data, val_data)

    # Create datasets and loaders (now includes has_policy as 5th tensor)
    train_ds = TensorDataset(
        train_data["states"], train_data["buy_targets"],
        train_data["values"], train_data["turns"],
        train_data["has_policy"]
    )
    val_ds = TensorDataset(
        val_data["states"], val_data["buy_targets"],
        val_data["values"], val_data["turns"],
        val_data["has_policy"]
    )

    # Use persistent_workers for faster epoch transitions
    use_workers = args.num_workers if device.type == "cpu" else min(args.num_workers, 4)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              drop_last=True, num_workers=use_workers,
                              persistent_workers=use_workers > 0, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                            num_workers=use_workers,
                            persistent_workers=use_workers > 0, pin_memory=True)

    # Create model
    model = PrismataNet(state_dim, num_units, hidden_dim=args.hidden_dim,
                        num_layers=args.num_layers, dropout=args.dropout,
                        value_only=args.value_only).to(device)
    param_count = sum(p.numel() for p in model.parameters())
    print(f"\nModel: {param_count:,} parameters (hidden={args.hidden_dim}, layers={args.num_layers})")

    # Optimizer — exclude bias and LayerNorm params from weight decay
    decay_params = []
    no_decay_params = []
    for name, param in model.named_parameters():
        if 'bias' in name or 'norm' in name:
            no_decay_params.append(param)
        else:
            decay_params.append(param)
    optimizer = torch.optim.AdamW([
        {'params': decay_params, 'weight_decay': 1e-4},
        {'params': no_decay_params, 'weight_decay': 0.0},
    ], lr=args.lr)

    # LR schedule: linear warmup then cosine decay
    def lr_lambda(epoch):
        if epoch < args.warmup_epochs:
            return (epoch + 1) / args.warmup_epochs
        progress = (epoch - args.warmup_epochs) / max(1, args.epochs - args.warmup_epochs)
        return max(1e-5 / args.lr, 0.5 * (1.0 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    start_epoch = 1

    # Resume from checkpoint
    if args.resume:
        print(f"\nResuming from {args.resume}")
        ckpt = torch.load(args.resume, map_location=device, weights_only=True)
        model.load_state_dict(ckpt["model_state_dict"])
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt.get("epoch", 0) + 1
        print(f"  Resuming from epoch {start_epoch}")

    # Optimize for Intel XPU if available
    if device.type == "xpu":
        try:
            import intel_extension_for_pytorch as ipex
            model, optimizer = ipex.optimize(model, optimizer=optimizer)
            print("  Applied IPEX optimization for Intel XPU")
        except Exception as e:
            print(f"  IPEX optimize failed: {e}")

    # --- Experiment logging setup ---
    runs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
    os.makedirs(runs_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_path = os.path.join(runs_dir, f"{timestamp}.json")
    run_log = {
        "timestamp": timestamp,
        "git_hash": get_git_hash(),
        "schema_hash": get_schema_hash(args.data_dir),
        "hyperparameters": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "warmup_epochs": args.warmup_epochs,
            "hidden_dim": args.hidden_dim,
            "num_layers": args.num_layers,
            "dropout": args.dropout,
            "policy_weight": args.policy_weight,
            "label_smooth": args.label_smooth,
            "patience": args.patience,
            "value_only": args.value_only,
            "weight_decay": 1e-4,
            "selfplay_dir": args.selfplay_dir,
            "expert_weight": args.expert_weight,
        },
        "data": {
            "train_examples": train_data["states"].shape[0],
            "val_examples": val_data["states"].shape[0],
            "state_dim": state_dim,
            "num_units": num_units,
        },
        "model_params": param_count,
        "device": str(device),
        "epochs": [],
    }

    # Training loop
    best_val_vloss = float("inf")
    best_epoch = 0
    patience_counter = 0

    mode_str = "value-only" if args.value_only else "policy+value"
    print(f"\nTraining {mode_str} for {args.epochs} epochs "
          f"(batch={args.batch_size}, lr={args.lr}, policy_wt={args.policy_weight}, "
          f"label_smooth={args.label_smooth}, patience={args.patience})...\n")

    # Header
    if args.value_only:
        print(f"{'Ep':>4} {'TrVL':>7} {'TrVA':>6} {'VaVL':>7} {'VaVA':>6} "
              f"{'VPred':>12} {'Sat%':>5} {'LR':>9} {'Time':>5} {'Note':>8}")
        print("-" * 82)
    else:
        print(f"{'Ep':>4} {'TrPL':>7} {'TrVL':>7} {'TrPA':>6} {'TrVA':>6} "
              f"{'VaPL':>7} {'VaVL':>7} {'VaPA':>6} {'VaVA':>6} "
              f"{'VPred':>12} {'Sat%':>5} {'LR':>9} {'Time':>5} {'Note':>8}")
        print("-" * 118)

    wall_start = time.time()

    for epoch in range(start_epoch, args.epochs + 1):
        t0 = time.time()

        tr_pl, tr_vl, tr_pa, tr_va, tr_vs = train_epoch(
            model, train_loader, optimizer, device, args.policy_weight)
        va_pl, va_vl, va_pa, va_va, va_vs = eval_epoch(
            model, val_loader, device, args.policy_weight)
        lr = optimizer.param_groups[0]["lr"]
        scheduler.step()

        elapsed = time.time() - t0

        # Note column for best/early-stop tracking
        note = ""
        if va_vl < best_val_vloss:
            best_val_vloss = va_vl
            best_epoch = epoch
            patience_counter = 0
            note = "*best"

            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "state_dim": state_dim,
                "num_units": num_units,
                "hidden_dim": args.hidden_dim,
                "num_layers": args.num_layers,
                "value_only": args.value_only,
                "dropout": args.dropout,
                "unit_index": unit_index,
                "val_policy_loss": va_pl,
                "val_value_loss": va_vl,
                "val_value_acc": va_va,
                "label_smooth": args.label_smooth,
                "policy_weight": args.policy_weight,
            }, os.path.join(args.model_dir, "best_model.pt"))
        else:
            patience_counter += 1

        # Saturation warning
        if va_vs["saturated_frac"] > 0.5:
            note += " !sat"

        # Value prediction summary string
        vpred_str = f"[{va_vs['min']:+.2f},{va_vs['max']:+.2f}]"

        # Print epoch line
        if args.value_only:
            print(f"{epoch:4d} {tr_vl:7.4f} {tr_va:6.1%} {va_vl:7.4f} {va_va:6.1%} "
                  f"{vpred_str:>12s} {va_vs['saturated_frac']:5.1%} {lr:9.6f} {elapsed:4.0f}s {note:>8s}")
        else:
            print(f"{epoch:4d} {tr_pl:7.4f} {tr_vl:7.4f} {tr_pa:6.1%} {tr_va:6.1%} "
                  f"{va_pl:7.4f} {va_vl:7.4f} {va_pa:6.1%} {va_va:6.1%} "
                  f"{vpred_str:>12s} {va_vs['saturated_frac']:5.1%} {lr:9.6f} {elapsed:4.0f}s {note:>8s}")

        # Log epoch data
        epoch_log = {
            "epoch": epoch,
            "train_value_loss": round(tr_vl, 6),
            "train_policy_loss": round(tr_pl, 6),
            "train_value_acc": round(tr_va, 4),
            "train_policy_acc": round(tr_pa, 4),
            "val_value_loss": round(va_vl, 6),
            "val_policy_loss": round(va_pl, 6),
            "val_value_acc": round(va_va, 4),
            "val_policy_acc": round(va_pa, 4),
            "val_value_pred_mean": round(va_vs["mean"], 4),
            "val_value_pred_std": round(va_vs["std"], 4),
            "val_value_pred_min": round(va_vs["min"], 4),
            "val_value_pred_max": round(va_vs["max"], 4),
            "val_saturated_frac": round(va_vs["saturated_frac"], 4),
            "lr": lr,
            "time_s": round(elapsed, 1),
        }
        run_log["epochs"].append(epoch_log)

        # Save periodic checkpoints
        if epoch % 10 == 0:
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "state_dim": state_dim,
                "num_units": num_units,
                "hidden_dim": args.hidden_dim,
                "num_layers": args.num_layers,
                "value_only": args.value_only,
                "dropout": args.dropout,
            }, os.path.join(args.model_dir, f"checkpoint_ep{epoch}.pt"))

        # Early stopping
        if args.patience > 0 and patience_counter >= args.patience:
            print(f"\nEarly stopping at epoch {epoch} (no improvement for {args.patience} epochs)")
            print(f"Best val value loss: {best_val_vloss:.4f} at epoch {best_epoch}")
            break

    wall_time = time.time() - wall_start

    # Final summary
    print(f"\nDone! Best val value loss: {best_val_vloss:.4f} at epoch {best_epoch}")
    print(f"Total wall time: {wall_time:.0f}s ({wall_time/60:.1f}min)")
    print(f"Model saved to {args.model_dir}/best_model.pt")

    # Save experiment log
    run_log["total_wall_time_s"] = round(wall_time, 1)
    run_log["best_val_value_loss"] = round(best_val_vloss, 6)
    run_log["best_epoch"] = best_epoch
    run_log["final_epoch"] = epoch

    with open(run_log_path, "w") as f:
        json.dump(run_log, f, indent=2)
    print(f"Experiment log: {run_log_path}")


if __name__ == "__main__":
    main()
