"""
Train policy (buy prediction) and value (win prediction) networks
on vectorized Prismata expert replay data.

Architecture:
  - Shared trunk: MLP with residual connections + dropout
  - Policy head: predicts buy counts per unit type (regression/Poisson)
  - Value head: predicts win probability for active player (tanh)

Supports:
  - Intel Arc GPU via native PyTorch XPU (torch.xpu)
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
import random
import subprocess
import sys
import time
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset, ConcatDataset


def set_seed(seed):
    """Set all random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


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


def get_device(force=None):
    """Detect best available device: Intel XPU > CUDA > CPU.

    Args:
        force: Override device selection ('cpu', 'xpu', 'cuda', or None/'auto')
    """
    if force and force != "auto":
        dev = torch.device(force)
        if force == "xpu":
            print(f"Device: Intel XPU ({torch.xpu.get_device_name(0)})")
        elif force == "cuda":
            print(f"Device: CUDA ({torch.cuda.get_device_name(0)})")
        else:
            print(f"Device: {force}")
        return dev

    # Try Intel Arc (native PyTorch XPU — no IPEX needed)
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        dev = torch.device("xpu")
        print(f"Device: Intel XPU ({torch.xpu.get_device_name(0)})")
        return dev

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
                 dropout=0.1, value_only=False, use_tanh=False):
        super().__init__()
        self.value_only = value_only
        self.use_tanh = use_tanh

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

        # Value head: predict win probability
        # When use_tanh=True: applies tanh in forward (matches C++ inference)
        # When use_tanh=False: raw logit (original behavior, or for BCE loss)
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
        )

    def forward(self, x):
        h = F.relu(self.input_proj(x))

        for layer in self.trunk_layers:
            h = h + F.relu(layer(h))  # Residual

        value_logit = self.value_head(h).squeeze(-1)  # Raw logit
        value_out = torch.tanh(value_logit) if self.use_tanh else value_logit

        if self.value_only:
            return None, value_out

        policy = self.policy_head(h)  # Raw logits / counts
        return policy, value_out


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


def compute_value_accuracy(pred, target, bce_mode=False):
    """Accuracy: what fraction correctly predict winner.

    For MSE mode: compare signs (works for both raw logit and tanh output).
    For BCE mode: pred > 0 means P(win) > 0.5, target > 0.5 means actual win.
    """
    if bce_mode:
        pred_wins = (pred > 0).float()
        target_wins = (target > 0.5).float()
        return (pred_wins == target_wins).float().mean().item()
    pred_sign = (pred > 0).float() * 2 - 1  # Convert to {-1, 1}
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


def train_epoch(model, loader, optimizer, device, policy_weight=0.5,
                value_criterion=None, bce_mode=False, use_amp=False):
    """Train one epoch, return (policy_loss, value_loss, policy_acc, value_acc, value_stats)."""
    if value_criterion is None:
        value_criterion = nn.MSELoss()
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
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=use_amp):
            policy_pred, value_pred = model(states)

            vloss = value_criterion(value_pred, values_target)

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
        total_vacc += compute_value_accuracy(value_pred, values_target, bce_mode)
        all_vpreds.append(value_pred.detach().cpu())
        n_batches += 1

    # Compute value prediction statistics for saturation monitoring
    all_vpreds = torch.cat(all_vpreds)
    if bce_mode:
        # For BCE mode, apply sigmoid for display
        all_vpreds_bounded = torch.sigmoid(all_vpreds)
        value_stats = {
            "mean": all_vpreds_bounded.mean().item(),
            "std": all_vpreds_bounded.std().item(),
            "min": all_vpreds_bounded.min().item(),
            "max": all_vpreds_bounded.max().item(),
            "saturated_frac": ((all_vpreds_bounded - 0.5).abs() > 0.45).float().mean().item(),
        }
    else:
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
def eval_epoch(model, loader, device, policy_weight=0.5,
               value_criterion=None, bce_mode=False, use_amp=False):
    """Evaluate one epoch, return (policy_loss, value_loss, policy_acc, value_acc, value_stats)."""
    if value_criterion is None:
        value_criterion = nn.MSELoss()
    model.eval()
    total_ploss = 0
    total_vloss = 0
    total_pacc = 0
    total_vacc = 0
    n_batches = 0
    n_policy_batches = 0
    all_vpreds = []
    all_targets = []

    for batch in loader:
        states, buys, values_target = batch[0], batch[1], batch[2]
        has_policy = batch[4] if len(batch) > 4 else torch.ones(states.shape[0])

        states = states.to(device)
        buys = buys.to(device)
        values_target = values_target.to(device)
        has_policy = has_policy.to(device)

        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=use_amp):
            policy_pred, value_pred = model(states)

            vloss = value_criterion(value_pred, values_target)

            if policy_pred is not None:
                policy_mask = has_policy > 0.5
                if policy_mask.any():
                    ploss = policy_loss_fn(policy_pred[policy_mask], buys[policy_mask])
                    total_ploss += ploss.item()
                    total_pacc += compute_policy_accuracy(policy_pred[policy_mask], buys[policy_mask])
                    n_policy_batches += 1

        total_vloss += vloss.item()
        total_vacc += compute_value_accuracy(value_pred, values_target, bce_mode)
        all_vpreds.append(value_pred.cpu())
        all_targets.append(values_target.cpu())
        n_batches += 1

    all_vpreds = torch.cat(all_vpreds)
    all_targets = torch.cat(all_targets)

    if bce_mode:
        all_vpreds_bounded = torch.sigmoid(all_vpreds)
        value_stats = {
            "mean": all_vpreds_bounded.mean().item(),
            "std": all_vpreds_bounded.std().item(),
            "min": all_vpreds_bounded.min().item(),
            "max": all_vpreds_bounded.max().item(),
            "saturated_frac": ((all_vpreds_bounded - 0.5).abs() > 0.45).float().mean().item(),
        }
        # Brier score: mean( (predicted_prob - actual_outcome)^2 )
        brier = ((all_vpreds_bounded - all_targets) ** 2).mean().item()
        value_stats["brier_score"] = brier
    else:
        all_vpreds_tanh = torch.tanh(all_vpreds)
        value_stats = {
            "mean": all_vpreds_tanh.mean().item(),
            "std": all_vpreds_tanh.std().item(),
            "min": all_vpreds_tanh.min().item(),
            "max": all_vpreds_tanh.max().item(),
            "saturated_frac": ((all_vpreds_tanh.abs() > 0.95).float().mean().item()),
        }
        # Brier score: convert to [0,1] probabilities first
        pred_prob = (all_vpreds_tanh + 1) / 2
        target_prob = (all_targets + 1) / 2
        brier = ((pred_prob - target_prob) ** 2).mean().item()
        value_stats["brier_score"] = brier

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


def load_selfplay_data(selfplay_dir, num_units, label_smooth=0.95, max_records=0,
                       subsample_every=1):
    """Load self-play binary data and split into train/val by game_id.

    Split: game_id % 10 == 0 goes to val (deterministic, stable across runs).
    CRITICAL: Split by game_id, NOT by record — all records from same game share
    the same outcome label, so per-record splitting causes massive data leakage.

    Self-play records have no policy targets — buy_targets are set to zero.
    A has_policy mask tensor is included so the loss function can skip policy
    loss on self-play records.

    Args:
        subsample_every: Keep every Nth position per game (1=all, 3=every 3rd).
            Reduces temporal correlation between adjacent positions.

    Returns:
        (train_data, val_data) dicts with keys: states, buy_targets, values, turns, has_policy
    """
    # Import here to avoid circular dependency at module level
    from load_selfplay import load_all_shards

    records = load_all_shards(selfplay_dir, validate_crc=False, max_records=max_records)
    if records is None:
        print("FATAL: No self-play data loaded.")
        sys.exit(1)

    # Position subsampling: keep every Nth position per game
    if subsample_every > 1:
        game_ids_raw = records['game_id']
        # Compute position index within each game
        # Vectorized: compute position-within-game for each record
        order = np.argsort(game_ids_raw, kind='stable')
        _, starts, sizes = np.unique(game_ids_raw[order], return_index=True, return_counts=True)
        position_in_game = np.empty(len(game_ids_raw), dtype=np.int32)
        for start, size in zip(starts, sizes):
            position_in_game[order[start:start + size]] = np.arange(size, dtype=np.int32)
        keep_mask = (position_in_game % subsample_every) == 0
        original_count = len(records)
        records = records[keep_mask]
        print(f"  Subsampled: {original_count:,} -> {len(records):,} records "
              f"(every {subsample_every}th position per game)")

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

    device = get_device(args.device)

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
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                        help="Weight decay for non-bias/norm params (default 1e-4)")
    parser.add_argument("--max-records", type=int, default=0,
                        help="Max training records to load (0=all). Use to cap memory on large datasets.")
    parser.add_argument("--patience", type=int, default=10,
                        help="Early stopping patience on val value loss (0=disabled)")
    parser.add_argument("--num-workers", type=int, default=2,
                        help="DataLoader workers (default 2, safe for 16GB cloud; use 4 for 32GB+ local)")
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint path")
    parser.add_argument("--overfit-test", action="store_true",
                        help="Run tiny-subset overfit test and exit")
    parser.add_argument("--selfplay-dir", type=str, default=None,
                        help="Directory with binary self-play shards (selfplay_t*_s*.bin)")
    parser.add_argument("--expert-weight", type=float, default=0.5,
                        help="Fraction of training data from expert replays when mixing (default 0.5)")
    parser.add_argument("--tanh-in-training", action="store_true",
                        help="Apply tanh in forward pass during training (fixes mismatch with C++ inference)")
    parser.add_argument("--loss-fn", choices=["mse", "bce"], default="mse",
                        help="Value loss function: mse (default) or bce (BCEWithLogitsLoss)")
    parser.add_argument("--eval-every-steps", type=int, default=0,
                        help="Evaluate every N optimizer steps (0=epoch-level only)")
    parser.add_argument("--subsample-every", type=int, default=1,
                        help="Keep every Nth position per game to reduce temporal correlation (1=all)")
    parser.add_argument("--streaming", action="store_true",
                        help="Use memory-mapped streaming loader (for large datasets that don't fit in RAM)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility. If not set, uses random seed and logs it.")
    parser.add_argument("--device", type=str, default="auto",
                        choices=["auto", "cpu", "xpu", "cuda"],
                        help="Force device selection (default: auto-detect)")
    parser.add_argument("--compile", action="store_true",
                        help="Use torch.compile for XPU kernel optimization (requires MSVC)")
    parser.add_argument("--amp", action="store_true",
                        help="Use BF16 mixed precision (recommended for XPU)")
    args = parser.parse_args()

    # Seed for reproducibility (before any randomness)
    if args.seed is None:
        args.seed = torch.randint(0, 2**31, (1,)).item()
    set_seed(args.seed)
    print(f"Random seed: {args.seed}")

    # Overfit test: quick architecture validation
    if args.overfit_test:
        run_overfit_test(args)
        return

    os.makedirs(args.model_dir, exist_ok=True)

    device = get_device(args.device)
    use_amp = args.amp and device.type in ("xpu", "cuda")
    if use_amp:
        print(f"  Mixed precision: BF16 autocast enabled")

    # Load data
    print("Loading training data...")

    unit_index = load_unit_index(os.path.join(args.data_dir, "unit_index.json"))
    num_units = len(unit_index)

    streaming_mode = args.streaming and args.selfplay_dir

    if streaming_mode:
        # Streaming mode: memory-mapped access, no RAM limit
        from load_selfplay import MemmapShardIndex, MemmapSelfPlayDataset

        print(f"  Streaming mode: building shard index...")
        shard_index = MemmapShardIndex(args.selfplay_dir,
                                       subsample_every=args.subsample_every)
        state_dim = shard_index.get_feature_dim()
        train_indices, val_indices = shard_index.get_train_val_indices()

        if args.max_records > 0 and len(train_indices) > args.max_records:
            rng = np.random.RandomState(args.seed)
            train_indices = rng.choice(train_indices, args.max_records, replace=False)
            train_indices.sort()
            print(f"  Capped training records to {args.max_records:,}")

        est_games_per_record = 1 / 37  # ~37 records per game
        print(f"    Train: {len(train_indices):,} records (~{int(len(train_indices) * est_games_per_record):,} games)")
        print(f"    Val:   {len(val_indices):,} records (~{int(len(val_indices) * est_games_per_record):,} games)")

        if args.expert_weight > 0:
            print(f"  WARNING: --expert-weight ignored in streaming mode (use --expert-weight 0)")

    elif args.selfplay_dir:
        # Self-play mode: load binary shards, optionally mix with expert data
        sp_train, sp_val = load_selfplay_data(
            args.selfplay_dir, num_units, label_smooth=args.label_smooth,
            max_records=args.max_records, subsample_every=args.subsample_every)

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

    # Set up loss function mode
    bce_mode = args.loss_fn == 'bce'
    if bce_mode:
        value_criterion = nn.BCEWithLogitsLoss()
        if args.tanh_in_training:
            print("  WARNING: --tanh-in-training ignored with --loss-fn bce (BCE uses sigmoid internally)")
    else:
        value_criterion = nn.MSELoss()
        if args.tanh_in_training:
            print(f"  Tanh-in-training ENABLED: model applies tanh in forward pass")

    if streaming_mode:
        # Streaming: create MemmapSelfPlayDataset directly
        train_ds = MemmapSelfPlayDataset(shard_index, train_indices,
                                         label_smooth=args.label_smooth,
                                         num_units=num_units, bce_mode=bce_mode)
        val_ds = MemmapSelfPlayDataset(shard_index, val_indices,
                                       label_smooth=args.label_smooth,
                                       num_units=num_units, bce_mode=bce_mode)

        print(f"  Train: {len(train_ds)} examples")
        print(f"  Val: {len(val_ds)} examples")
        print(f"  State dim: {state_dim}")
        print(f"  Unit types: {num_units}")
        print(f"  Mode: {'value-only' if args.value_only else 'policy+value'} (streaming)")

        # Streaming label sanity check: sample a small batch to catch corrupt data early
        print("\n--- Streaming Label Sanity Check ---")
        sample_size = min(10000, len(train_ds))
        sample_indices = np.random.choice(len(train_ds), sample_size, replace=False)
        sample_values = []
        for idx in sample_indices:
            item = train_ds[int(idx)]
            sample_values.append(item[2].item())  # value target is 3rd tensor
        sample_values = np.array(sample_values)
        v_std = sample_values.std()
        v_min, v_max = sample_values.min(), sample_values.max()
        n_pos = (sample_values > 0).sum()
        n_neg = (sample_values < 0).sum()
        print(f"  Sample values (n={sample_size}): min={v_min:.3f}, max={v_max:.3f}, "
              f"std={v_std:.3f}, +1: {n_pos} ({100*n_pos/sample_size:.1f}%), "
              f"-1: {n_neg} ({100*n_neg/sample_size:.1f}%)")
        if v_std < 0.01:
            print(f"  FATAL: Streaming value labels have std={v_std:.6f} < 0.01 — data appears corrupt!")
            sys.exit(1)
        if v_min == v_max:
            print(f"  FATAL: All sampled value labels are identical ({v_min})!")
            sys.exit(1)
        print("  Streaming label sanity check: PASSED\n")

        # Multi-worker streaming supported via lazy init (each worker opens own memmap handles)
        use_workers = args.num_workers if device.type == "cpu" else min(args.num_workers, 4)
        shuffle_gen = torch.Generator()
        shuffle_gen.manual_seed(args.seed)
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                                  drop_last=True, num_workers=use_workers,
                                  generator=shuffle_gen, pin_memory=True,
                                  persistent_workers=use_workers > 0)
        val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                                num_workers=use_workers, pin_memory=True,
                                persistent_workers=use_workers > 0)

        # Stub for run_log data section
        train_n = len(train_ds)
        val_n = len(val_ds)
    else:
        print(f"  Train: {train_data['states'].shape[0]} examples")
        print(f"  Val: {val_data['states'].shape[0]} examples")
        print(f"  State dim: {state_dim}")
        print(f"  Unit types: {num_units}")
        print(f"  Mode: {'value-only' if args.value_only else 'policy+value'}")

        # Pre-training label sanity check
        check_label_sanity(train_data, val_data)

        if bce_mode:
            # Remap targets from [-smooth, +smooth] to [0, 1] for BCE
            train_data["values"] = (train_data["values"] + 1) / 2
            val_data["values"] = (val_data["values"] + 1) / 2
            print(f"  BCE mode: targets remapped to [{val_data['values'].min():.3f}, {val_data['values'].max():.3f}]")

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
        shuffle_gen = torch.Generator()
        shuffle_gen.manual_seed(args.seed)
        train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                                  drop_last=True, num_workers=use_workers, generator=shuffle_gen,
                                  persistent_workers=use_workers > 0, pin_memory=True)
        val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                                num_workers=use_workers,
                                persistent_workers=use_workers > 0, pin_memory=True)

        train_n = train_data["states"].shape[0]
        val_n = val_data["states"].shape[0]

    # Create model
    use_tanh = args.tanh_in_training and not bce_mode
    model = PrismataNet(state_dim, num_units, hidden_dim=args.hidden_dim,
                        num_layers=args.num_layers, dropout=args.dropout,
                        value_only=args.value_only, use_tanh=use_tanh).to(device)
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
        {'params': decay_params, 'weight_decay': args.weight_decay},
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
        if "scheduler_state_dict" in ckpt:
            scheduler.load_state_dict(ckpt["scheduler_state_dict"])
            print(f"  Restored LR scheduler state")
        print(f"  Resuming from epoch {start_epoch}")

    # Optional: torch.compile for Intel XPU kernel optimization
    if getattr(args, 'compile', False) and device.type == "xpu":
        try:
            model = torch.compile(model)
            print("  Applied torch.compile() for Intel XPU")
        except Exception as e:
            print(f"  torch.compile() skipped: {e}")

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
            "weight_decay": args.weight_decay,
            "selfplay_dir": args.selfplay_dir,
            "expert_weight": args.expert_weight,
            "loss_fn": args.loss_fn,
            "tanh_in_training": args.tanh_in_training,
            "use_tanh": use_tanh,
            "eval_every_steps": args.eval_every_steps,
            "subsample_every": args.subsample_every,
            "seed": args.seed,
            "streaming": args.streaming,
        },
        "data": {
            "train_examples": train_n,
            "val_examples": val_n,
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
    best_step = 0
    patience_counter = 0
    global_step = 0
    early_stopped = False

    mode_str = "value-only" if args.value_only else "policy+value"
    loss_str = f"loss={args.loss_fn}" + ("+tanh" if use_tanh else "")
    print(f"\nTraining {mode_str} for {args.epochs} epochs "
          f"(batch={args.batch_size}, lr={args.lr}, {loss_str}, "
          f"label_smooth={args.label_smooth}, patience={args.patience})")
    if args.eval_every_steps > 0:
        print(f"  Step-level eval every {args.eval_every_steps} steps")
    print()

    # Header
    if args.value_only:
        print(f"{'Ep':>4} {'TrVL':>7} {'TrVA':>6} {'VaVL':>7} {'VaVA':>6} "
              f"{'Brier':>6} {'VPred':>12} {'Sat%':>5} {'LR':>9} {'Step':>6} {'Time':>5} {'Note':>8}")
        print("-" * 96)
    else:
        print(f"{'Ep':>4} {'TrPL':>7} {'TrVL':>7} {'TrPA':>6} {'TrVA':>6} "
              f"{'VaPL':>7} {'VaVL':>7} {'VaPA':>6} {'VaVA':>6} "
              f"{'Brier':>6} {'VPred':>12} {'Sat%':>5} {'LR':>9} {'Step':>6} {'Time':>5} {'Note':>8}")
        print("-" * 132)

    def save_checkpoint(tag, epoch, step, va_vl, va_va, va_vs):
        """Save model checkpoint with full metadata."""
        torch.save({
            "epoch": epoch,
            "global_step": step,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "state_dim": state_dim,
            "num_units": num_units,
            "hidden_dim": args.hidden_dim,
            "num_layers": args.num_layers,
            "value_only": args.value_only,
            "use_tanh": use_tanh,
            "loss_fn": args.loss_fn,
            "dropout": args.dropout,
            "unit_index": unit_index,
            "val_value_loss": va_vl,
            "val_value_acc": va_va,
            "label_smooth": args.label_smooth,
            "policy_weight": args.policy_weight,
        }, os.path.join(args.model_dir, f"{tag}.pt"))

    def do_eval(epoch, step):
        """Run evaluation and handle best tracking. Returns (va_vl, improved)."""
        nonlocal best_val_vloss, best_epoch, best_step, patience_counter
        va_pl, va_vl, va_pa, va_va, va_vs = eval_epoch(
            model, val_loader, device, args.policy_weight,
            value_criterion=value_criterion, bce_mode=bce_mode,
            use_amp=use_amp)

        note = ""
        improved = False
        if va_vl < best_val_vloss:
            best_val_vloss = va_vl
            best_epoch = epoch
            best_step = step
            patience_counter = 0
            note = "*best"
            improved = True
            save_checkpoint("best_model", epoch, step, va_vl, va_va, va_vs)
        else:
            patience_counter += 1

        if va_vs["saturated_frac"] > 0.5:
            note += " !sat"

        vpred_str = f"[{va_vs['min']:+.2f},{va_vs['max']:+.2f}]"
        brier_str = f"{va_vs.get('brier_score', 0):.4f}"

        return va_pl, va_vl, va_pa, va_va, va_vs, vpred_str, brier_str, note, improved

    wall_start = time.time()
    run_log["step_evals"] = []

    for epoch in range(start_epoch, args.epochs + 1):
        if device.type == "xpu":
            torch.xpu.synchronize()
        t0 = time.time()

        # --- Train epoch with optional step-level eval ---
        if args.eval_every_steps > 0:
            # Batch-level training with step-level evaluation
            model.train()
            epoch_vloss_sum = 0
            epoch_vacc_sum = 0
            n_epoch_batches = 0

            for batch in train_loader:
                states, buys, values_target = batch[0], batch[1], batch[2]
                has_policy = batch[4] if len(batch) > 4 else torch.ones(states.shape[0])

                states = states.to(device)
                buys = buys.to(device)
                values_target = values_target.to(device)
                has_policy = has_policy.to(device)

                optimizer.zero_grad()
                with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=use_amp):
                    policy_pred, value_pred = model(states)
                    vloss = value_criterion(value_pred, values_target)

                    if policy_pred is not None:
                        policy_mask = has_policy > 0.5
                        if policy_mask.any():
                            ploss = policy_loss_fn(policy_pred[policy_mask], buys[policy_mask])
                            loss = vloss + args.policy_weight * ploss
                        else:
                            loss = vloss
                    else:
                        loss = vloss

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                epoch_vloss_sum += vloss.item()
                epoch_vacc_sum += compute_value_accuracy(value_pred, values_target, bce_mode)
                n_epoch_batches += 1
                global_step += 1

                # Step-level evaluation
                if global_step % args.eval_every_steps == 0:
                    va_pl, va_vl, va_pa, va_va, va_vs, vpred_str, brier_str, note, _ = do_eval(epoch, global_step)

                    # Save step checkpoint for multi-checkpoint tournament later
                    save_checkpoint(f"model_step_{global_step}", epoch, global_step,
                                    va_vl, va_va, va_vs)

                    lr = optimizer.param_groups[0]["lr"]
                    print(f"  S{global_step:6d} "
                          f"val_loss={va_vl:.4f} val_acc={va_va:.1%} "
                          f"brier={brier_str} {vpred_str} "
                          f"lr={lr:.6f} {note}")

                    run_log["step_evals"].append({
                        "step": global_step,
                        "epoch": epoch,
                        "val_value_loss": round(va_vl, 6),
                        "val_value_acc": round(va_va, 4),
                        "brier_score": round(va_vs.get("brier_score", 0), 6),
                        "val_value_pred_mean": round(va_vs["mean"], 4),
                        "val_value_pred_min": round(va_vs["min"], 4),
                        "val_value_pred_max": round(va_vs["max"], 4),
                        "lr": lr,
                    })

                    model.train()  # Resume training

                    # Step-level early stopping
                    if args.patience > 0 and patience_counter >= args.patience:
                        early_stopped = True
                        break

            if early_stopped:
                print(f"\nEarly stopping at step {global_step} (no improvement for "
                      f"{args.patience} eval points)")
                print(f"Best val value loss: {best_val_vloss:.4f} at step {best_step}")
                break

            # Epoch summary line (training stats from this epoch)
            tr_vl = epoch_vloss_sum / max(n_epoch_batches, 1)
            tr_va = epoch_vacc_sum / max(n_epoch_batches, 1)
            tr_pl = 0  # Not tracked in step-level mode
            tr_pa = 0
        else:
            # Standard epoch-level training (original behavior)
            tr_pl, tr_vl, tr_pa, tr_va, tr_vs = train_epoch(
                model, train_loader, optimizer, device, args.policy_weight,
                value_criterion=value_criterion, bce_mode=bce_mode,
                use_amp=use_amp)
            global_step += len(train_loader)

        # End-of-epoch evaluation
        va_pl, va_vl, va_pa, va_va, va_vs, vpred_str, brier_str, note, _ = do_eval(epoch, global_step)
        lr = optimizer.param_groups[0]["lr"]
        scheduler.step()

        if device.type == "xpu":
            torch.xpu.synchronize()
        elapsed = time.time() - t0

        # Print epoch line
        if args.value_only:
            print(f"{epoch:4d} {tr_vl:7.4f} {tr_va:6.1%} {va_vl:7.4f} {va_va:6.1%} "
                  f"{brier_str:>6s} {vpred_str:>12s} {va_vs['saturated_frac']:5.1%} "
                  f"{lr:9.6f} {global_step:6d} {elapsed:4.0f}s {note:>8s}")
        else:
            print(f"{epoch:4d} {tr_pl:7.4f} {tr_vl:7.4f} {tr_pa:6.1%} {tr_va:6.1%} "
                  f"{va_pl:7.4f} {va_vl:7.4f} {va_pa:6.1%} {va_va:6.1%} "
                  f"{brier_str:>6s} {vpred_str:>12s} {va_vs['saturated_frac']:5.1%} "
                  f"{lr:9.6f} {global_step:6d} {elapsed:4.0f}s {note:>8s}")

        # Log epoch data
        epoch_log = {
            "epoch": epoch,
            "global_step": global_step,
            "train_value_loss": round(tr_vl, 6),
            "val_value_loss": round(va_vl, 6),
            "val_value_acc": round(va_va, 4),
            "brier_score": round(va_vs.get("brier_score", 0), 6),
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
            save_checkpoint(f"checkpoint_ep{epoch}", epoch, global_step,
                            va_vl, va_va, va_vs)

        # Epoch-level early stopping (only when not using step-level)
        if args.eval_every_steps == 0 and args.patience > 0 and patience_counter >= args.patience:
            print(f"\nEarly stopping at epoch {epoch} (no improvement for {args.patience} epochs)")
            print(f"Best val value loss: {best_val_vloss:.4f} at epoch {best_epoch}")
            break

    wall_time = time.time() - wall_start

    # Final summary
    print(f"\nDone! Best val value loss: {best_val_vloss:.4f} at epoch {best_epoch} (step {best_step})")
    print(f"Total wall time: {wall_time:.0f}s ({wall_time/60:.1f}min)")
    print(f"Model saved to {args.model_dir}/best_model.pt")

    # Save experiment log
    run_log["total_wall_time_s"] = round(wall_time, 1)
    run_log["best_val_value_loss"] = round(best_val_vloss, 6)
    run_log["best_epoch"] = best_epoch
    run_log["best_step"] = best_step
    run_log["final_epoch"] = epoch

    with open(run_log_path, "w") as f:
        json.dump(run_log, f, indent=2)
    print(f"Experiment log: {run_log_path}")


if __name__ == "__main__":
    main()
