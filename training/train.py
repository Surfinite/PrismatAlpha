"""
Train PrismataNet neural network evaluation function on HDF5 data.

Architecture (schema_v1):
  - Input: 1290-dim feature vector (116 units x 11 + 14 global)
  - Shared trunk: MLP with residual blocks + LayerNorm
  - Value head: raw logit output (Path A — BCEWithLogitsLoss)
  - Policy head: buy count prediction per unit type (MSE)

Supports:
  - Intel Arc GPU via native PyTorch XPU (torch.xpu)
  - NVIDIA GPU via CUDA (torch.cuda)
  - CPU fallback with multi-worker DataLoader
  - Value-only mode (--value-only)
  - Label strategies A/B/C/D from HDF5 datasets
  - Rating-based and per-game sample weighting
  - SWA (Stochastic Weight Averaging) from last 20% of epochs
  - Early stopping, gradient clipping, LR warmup + cosine decay
  - DeepSets model (--model deepsets) with V2 HDF5 data format

Usage:
  python training/train.py --train-file training/data/splits/train.h5 \\
      --val-file training/data/splits/val.h5 --output-dir training/models/run_001 \\
      --hidden-dim 256 --num-layers 4 --epochs 100 --batch-size 512 --lr 3e-4 \\
      --patience 10 --value-only --label-strategy D

  # DeepSets model (V2 HDF5 format):
  python training/train.py --model deepsets \\
      --train-file training/data/splits/train_v2.h5 \\
      --val-file training/data/splits/val_v2.h5 \\
      --property-table training/property_table.json \\
      --output-dir training/models/deepsets_001 \\
      --epochs 100 --batch-size 512 --lr 3e-4 --patience 10
"""

import argparse
import atexit
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime

import h5py
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim.swa_utils import AveragedModel, SWALR
from torch.utils.data import DataLoader, Dataset, IterableDataset

# DeepSets model — imported lazily in main() to keep V1 path unchanged
# from model_deepsets import PrismataDeepSets


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def set_seed(seed):
    """Set all random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

def get_device(force=None):
    """Detect best available device: Intel XPU > CUDA > CPU."""
    if force and force != "auto":
        dev = torch.device(force)
        if force == "xpu":
            print(f"Device: Intel XPU ({torch.xpu.get_device_name(0)})")
        elif force == "cuda":
            print(f"Device: CUDA ({torch.cuda.get_device_name(0)})")
            # Disable TF32 — L4 GPUs with PyTorch 2.7+ default to TF32
            # which caused loss explosion (NaN/divergence) in DeepSets training
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            print("  TF32 disabled (using full FP32 precision)")
        else:
            print(f"Device: {force}")
        return dev

    if hasattr(torch, "xpu") and torch.xpu.is_available():
        dev = torch.device("xpu")
        print(f"Device: Intel XPU ({torch.xpu.get_device_name(0)})")
        return dev

    if torch.cuda.is_available():
        dev = torch.device("cuda")
        print(f"Device: CUDA ({torch.cuda.get_device_name(0)})")
        # Disable TF32 — L4 GPUs with PyTorch 2.7+ default to TF32
        # which caused loss explosion (NaN/divergence) in DeepSets training
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        print("  TF32 disabled (using full FP32 precision)")
        return dev

    print("Device: CPU")
    return torch.device("cpu")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ResBlock(nn.Module):
    """Residual block with LayerNorm, matching C++ NeuralNet.cpp inference."""

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
    """Combined policy + value network for Prismata.

    Architecture:
      input_proj -> [ResBlock x num_layers] -> value_head / policy_head

    Value head outputs a raw logit (no tanh). BCEWithLogitsLoss handles
    sigmoid internally. For C++ inference: 2*sigmoid(z)-1 maps to [-1,1].

    Policy head outputs buy count predictions per unit type.
    """

    def __init__(self, state_dim, num_units, hidden_dim=256, num_layers=4,
                 dropout=0.1, value_only=False):
        super().__init__()
        self.value_only = value_only
        self.state_dim = state_dim
        self.num_units = num_units
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        # Input projection
        self.input_proj = nn.Linear(state_dim, hidden_dim)

        # Shared trunk: residual blocks
        self.trunk = nn.ModuleList([
            ResBlock(hidden_dim, dropout=dropout) for _ in range(num_layers)
        ])

        # Value head: Linear -> ReLU -> Linear -> raw logit
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

        # Policy head: Linear -> ReLU -> Linear -> buy counts
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
# HDF5 Dataset
# ---------------------------------------------------------------------------

class H5Dataset(Dataset):
    """Lazy-loading dataset backed by an HDF5 file.

    Expected HDF5 structure:
      - features:      float32 [N, state_dim]
      - label_A:       float32 [N]         (hard binary 0/1)
      - label_B_weight: float32 [N]        (sample weight for strategy B)
      - label_C:       float32 [N]         (Elo-interpolated)
      - label_D:       float32 [N]         (neutral-prior blended)
      - policy_target: float32 [N, num_units] (buy counts)
      - rating_p0:     uint16  [N]
      - rating_p1:     uint16  [N]
      - total_plies:   uint16  [N]

    The file is opened lazily per-worker to support multi-worker DataLoader.
    """

    def __init__(self, h5_path, label_strategy="A", value_only=False,
                 rating_weight=False, game_weight=False, max_records=None):
        self.label_strategy = label_strategy
        self.value_only = value_only

        # Load into memory (optionally capped to max_records via random sample)
        print(f"    Loading {h5_path} into memory...")
        with h5py.File(h5_path, "r") as f:
            n_total = f["features"].shape[0]
            self.state_dim = f["features"].shape[1]

            # Subsample if max_records specified
            if max_records and max_records < n_total:
                print(f"    Subsampling {max_records:,} / {n_total:,} records...")
                rng = np.random.default_rng(42)
                indices = np.sort(rng.choice(n_total, max_records, replace=False))
            else:
                indices = None

            if indices is not None:
                self.features = torch.from_numpy(f["features"][indices].astype(np.float32))
            else:
                self.features = torch.from_numpy(f["features"][:].astype(np.float32))
            self.n_examples = self.features.shape[0]

            label_key = self._label_key()
            if label_key not in f:
                raise ValueError(f"HDF5 file missing dataset '{label_key}' "
                                 f"for label strategy {label_strategy}")
            if indices is not None:
                self.value_labels = torch.from_numpy(f[label_key][indices].astype(np.float32))
            else:
                self.value_labels = torch.from_numpy(f[label_key][:].astype(np.float32))

            if not value_only and "policy_target" in f:
                if indices is not None:
                    self.policy = torch.from_numpy(f["policy_target"][indices].astype(np.float32))
                else:
                    self.policy = torch.from_numpy(f["policy_target"][:].astype(np.float32))
            else:
                self.policy = None

            # Precompute sample weights
            if indices is not None:
                weights = np.ones(self.n_examples, dtype=np.float32)
                if label_strategy == "B" and "label_B_weight" in f:
                    weights *= f["label_B_weight"][indices].astype(np.float32)
                if rating_weight and "rating_p0" in f:
                    r0 = f["rating_p0"][indices].astype(np.float32)
                    r1 = f["rating_p1"][indices].astype(np.float32)
                    weights *= ((r0 + r1) / 4000.0) ** 2
                if game_weight and "total_plies" in f:
                    tp = f["total_plies"][indices].astype(np.float32)
                    tp = np.maximum(tp, 1.0)
                    weights *= 1.0 / tp
            else:
                weights = np.ones(self.n_examples, dtype=np.float32)
                if label_strategy == "B" and "label_B_weight" in f:
                    weights *= f["label_B_weight"][:].astype(np.float32)
                if rating_weight and "rating_p0" in f:
                    r0 = f["rating_p0"][:].astype(np.float32)
                    r1 = f["rating_p1"][:].astype(np.float32)
                    weights *= ((r0 + r1) / 4000.0) ** 2
                if game_weight and "total_plies" in f:
                    tp = f["total_plies"][:].astype(np.float32)
                    tp = np.maximum(tp, 1.0)
                    weights *= 1.0 / tp
            self.weights = torch.from_numpy(weights)

        print(f"    Loaded: {self.n_examples:,} examples, {self.features.nbytes/1e6:.0f} MB")

    def _label_key(self):
        """Return the HDF5 dataset name for the chosen label strategy."""
        if self.label_strategy == "A":
            return "label_A"
        elif self.label_strategy == "B":
            return "label_A"  # B uses A's labels with B's weights
        elif self.label_strategy == "C":
            return "label_C"
        elif self.label_strategy == "D":
            return "label_D"
        else:
            raise ValueError(f"Unknown label strategy: {self.label_strategy}")

    def __len__(self):
        return self.n_examples

    def __getitem__(self, idx):
        features = self.features[idx]
        value_label = self.value_labels[idx]
        policy = self.policy[idx] if self.policy is not None else torch.zeros(1)
        weight = self.weights[idx]
        return features, policy, value_label, weight


# ---------------------------------------------------------------------------
# HDF5 Dataset V2 (DeepSets per-instance format)
# ---------------------------------------------------------------------------

class H5DatasetV2(Dataset):
    """Load DeepSets per-instance HDF5 data (schema_v2 format).

    Expected HDF5 structure:
      - instance_features: float32 (N, MAX_INST, 10) — per-instance state features
      - instance_unit_ids: int32   (N, MAX_INST)      — unit type index per instance
      - instance_counts:   int32   (N,)               — actual (non-padded) count
      - supply:            float32 (N, 116, 3)        — [p0_sup, p1_sup, in_set] per type
      - globals:           float32 (N, 14)            — global game features
      - label_A:           float32 (N,)               — hard binary winner label
      (or label_B / label_C / label_D depending on strategy)

    Data is loaded entirely into memory for performance. For very large datasets
    use --max-records to cap the number of records loaded.
    """

    def __init__(self, h5_path, label_strategy='A', max_records=None):
        self.label_strategy = label_strategy

        print(f"    Loading V2 dataset {h5_path} into memory...")
        with h5py.File(h5_path, 'r') as f:
            n_total = f['instance_features'].shape[0]

            # Subsample if max_records specified
            if max_records and max_records < n_total:
                print(f"    Subsampling {max_records:,} / {n_total:,} records "
                      f"(contiguous slice for fast I/O)...")
                sl = slice(0, max_records)
            else:
                sl = slice(None)

            def _load(key):
                return f[key][sl]

            self.instance_features = torch.from_numpy(_load('instance_features').astype(np.float32))
            self.instance_unit_ids = torch.from_numpy(_load('instance_unit_ids').astype(np.int64))
            self.instance_counts   = torch.from_numpy(_load('instance_counts').astype(np.int64))
            self.supply            = torch.from_numpy(_load('supply').astype(np.float32))
            self.globals           = torch.from_numpy(_load('globals').astype(np.float32))

            label_key = self._label_key()
            if label_key not in f:
                raise ValueError(
                    f"HDF5 file missing dataset '{label_key}' "
                    f"for label strategy '{label_strategy}'"
                )
            self.labels = torch.from_numpy(_load(label_key).astype(np.float32))

        self.n_examples = self.instance_features.shape[0]
        mem_mb = (
            self.instance_features.nbytes
            + self.instance_unit_ids.nbytes
            + self.instance_counts.nbytes
            + self.supply.nbytes
            + self.globals.nbytes
            + self.labels.nbytes
        ) / 1e6
        print(f"    Loaded V2: {self.n_examples:,} examples, {mem_mb:.0f} MB")

    def _label_key(self):
        """Return the HDF5 dataset name for the chosen label strategy."""
        return H5DatasetV2._label_key_static(self.label_strategy)

    @staticmethod
    def _label_key_static(strategy):
        """Return the HDF5 dataset name for a label strategy."""
        if strategy in ('A', 'B'):
            return 'label_A'   # B uses A's labels with B's weights (weights not yet in V2)
        elif strategy == 'C':
            return 'label_C'
        elif strategy == 'D':
            return 'label_D'
        else:
            raise ValueError(f"Unknown label strategy: {strategy}")

    def __len__(self):
        return self.n_examples

    def __getitem__(self, idx):
        return {
            'instance_features': self.instance_features[idx],
            'instance_unit_ids': self.instance_unit_ids[idx],
            'instance_counts':   self.instance_counts[idx],
            'supply':            self.supply[idx],
            'globals':           self.globals[idx],
            'label':             self.labels[idx],
        }


# ---------------------------------------------------------------------------
# HDF5 Dataset V2 Streaming (chunk-buffered for large datasets)
# ---------------------------------------------------------------------------

class H5DatasetV2Streaming(IterableDataset):
    """Streaming DeepSets dataset that reads HDF5 in chunk-aligned batches.

    Instead of loading everything into RAM, reads one HDF5 chunk at a time
    (~5000 records), shuffles within it, and yields individual records.
    Inter-chunk order is also shuffled per epoch.

    Supports multiple H5 source files concatenated logically.
    Call set_epoch(n) before each epoch for deterministic shuffling.
    """

    def __init__(self, h5_paths, label_strategy='A', max_records=None,
                 chunk_size=5000):
        super().__init__()
        if isinstance(h5_paths, str):
            h5_paths = [h5_paths]
        self.h5_paths = h5_paths
        self.label_key = H5DatasetV2._label_key_static(label_strategy)
        self.chunk_size = chunk_size
        self._epoch = 0

        # Build chunk list across all files
        self.chunks = []  # [(path_idx, start, end)]
        self.n_total = 0
        for i, path in enumerate(h5_paths):
            with h5py.File(path, 'r') as f:
                n = f['instance_features'].shape[0]
            for start in range(0, n, chunk_size):
                end = min(start + chunk_size, n)
                self.chunks.append((i, start, end))
            self.n_total += n

        if max_records and max_records < self.n_total:
            self.n_examples = max_records
        else:
            self.n_examples = self.n_total

        mem_est = self.chunk_size * (200 * 10 * 4 + 200 * 8 + 8 + 116 * 3 * 4 + 14 * 4 + 4) / 1e6
        print(f"    Streaming V2: {len(h5_paths)} file(s), "
              f"{len(self.chunks)} chunks of {chunk_size}, "
              f"{self.n_examples:,} / {self.n_total:,} records "
              f"(~{mem_est:.0f} MB per chunk)")

    def set_epoch(self, epoch):
        """Set epoch for deterministic chunk shuffling."""
        self._epoch = epoch

    def __len__(self):
        return self.n_examples

    def __iter__(self):
        worker_info = torch.utils.data.get_worker_info()

        # Deterministic per-epoch shuffle of chunk order
        rng = np.random.RandomState(self._epoch * 7919 + 42)
        chunk_order = rng.permutation(len(self.chunks))

        # Partition chunks across DataLoader workers
        if worker_info is not None:
            n_workers = worker_info.num_workers
            wid = worker_info.id
            chunk_order = chunk_order[wid::n_workers]

        # Open file handles (one per source file, per worker)
        handles = {}
        yielded = 0
        try:
            for ci in chunk_order:
                if yielded >= self.n_examples:
                    break

                path_idx, start, end = self.chunks[ci]

                # Lazy open
                if path_idx not in handles:
                    handles[path_idx] = h5py.File(self.h5_paths[path_idx], 'r')
                f = handles[path_idx]

                n = end - start

                # Read entire chunk into memory (one decompression per chunk)
                try:
                    inst_feat = f['instance_features'][start:end]
                    inst_ids  = f['instance_unit_ids'][start:end]
                    inst_cnt  = f['instance_counts'][start:end]
                    supply    = f['supply'][start:end]
                    globals_  = f['globals'][start:end]
                    labels    = f[self.label_key][start:end]
                except OSError:
                    # Skip corrupt gzip chunks (h5py version/transfer issues)
                    self._skipped_chunks = getattr(self, '_skipped_chunks', 0) + 1
                    self._skipped_records = getattr(self, '_skipped_records', 0) + n
                    if self._skipped_chunks <= 5 or self._skipped_chunks % 100 == 0:
                        print(f"    [streaming] Skipped corrupt chunk {ci} "
                              f"(file={path_idx}, rows={start}:{end}), "
                              f"total skipped: {self._skipped_chunks} chunks "
                              f"({self._skipped_records:,} records)")
                    continue

                # Shuffle within chunk
                order = rng.permutation(n)

                for i in order:
                    if yielded >= self.n_examples:
                        break
                    yield {
                        'instance_features': torch.from_numpy(inst_feat[i].astype(np.float32)),
                        'instance_unit_ids': torch.from_numpy(inst_ids[i].astype(np.int64)),
                        'instance_counts':   torch.tensor(int(inst_cnt[i]), dtype=torch.int64),
                        'supply':            torch.from_numpy(supply[i].astype(np.float32)),
                        'globals':           torch.from_numpy(globals_[i].astype(np.float32)),
                        'label':             torch.tensor(float(labels[i]), dtype=torch.float32),
                    }
                    yielded += 1
        finally:
            for h in handles.values():
                h.close()


# ---------------------------------------------------------------------------
# Loss functions
# ---------------------------------------------------------------------------

def compute_value_accuracy(pred_logit, target):
    """Accuracy: fraction correctly predicting winner.

    pred_logit > 0 means P(P0 wins) > 0.5.
    target > 0.5 means P0 actually won.
    """
    pred_wins = (pred_logit > 0).float()
    target_wins = (target > 0.5).float()
    return (pred_wins == target_wins).float().mean().item()


def compute_brier_score(pred_logit, target):
    """Brier score: mean squared error between predicted probability and label.

    Lower is better. Chance-level (always predict 0.5) = 0.25.
    """
    pred_prob = torch.sigmoid(pred_logit)
    return ((pred_prob - target) ** 2).mean().item()


def compute_policy_accuracy(pred, target):
    """Accuracy: fraction of examples with exact same buy set (bought/not)."""
    pred_set = (pred > 0.5).float()
    target_set = (target > 0).float()
    match = (pred_set == target_set).all(dim=1).float()
    return match.mean().item()


# ---------------------------------------------------------------------------
# Training and evaluation
# ---------------------------------------------------------------------------

def _forward_deepsets(model, batch, device):
    """Run a DeepSets forward pass from a V2 dict batch.

    Returns (value_logit, value_target, batch_size).
    value_logit is squeezed to (B,) to match the V1 convention.
    """
    inst_feat = batch['instance_features'].to(device)
    inst_ids  = batch['instance_unit_ids'].to(device)
    inst_cnt  = batch['instance_counts'].to(device)
    supply    = batch['supply'].to(device)
    glb       = batch['globals'].to(device)
    label     = batch['label'].to(device)
    logit = model(inst_feat, inst_ids, inst_cnt, supply, glb).squeeze(-1)  # (B,)
    return logit, label, inst_feat.shape[0]


def train_epoch(model, loader, optimizer, device, value_criterion,
                policy_weight=0.5, grad_clip=1.0, warmup_scheduler=None,
                global_step=0, model_type='v1'):
    """Train one epoch. Returns (metrics_dict, updated_global_step).

    model_type: 'v1' uses flat feature batches (H5Dataset);
                'deepsets' uses dict batches (H5DatasetV2).
    """
    model.train()
    total_vloss = 0.0
    total_ploss = 0.0
    total_vacc = 0.0
    total_pacc = 0.0
    n_batches = 0
    n_policy_batches = 0
    n_samples = 0

    for batch in loader:
        optimizer.zero_grad()

        if model_type == 'deepsets':
            value_pred, value_target, bs = _forward_deepsets(model, batch, device)
            sample_weight = torch.ones(bs, device=device)
            policy_pred = None
        else:
            features, policy_target, value_target, sample_weight = [
                b.to(device) for b in batch
            ]
            policy_pred, value_pred = model(features)
            bs = features.shape[0]

        # Weighted BCE loss
        if sample_weight.sum() > 0:
            bce_unreduced = F.binary_cross_entropy_with_logits(
                value_pred, value_target, reduction="none")
            vloss = (bce_unreduced * sample_weight).sum() / sample_weight.sum()
        else:
            vloss = value_criterion(value_pred, value_target)

        loss = vloss

        if policy_pred is not None:
            ploss = F.mse_loss(policy_pred, policy_target)
            loss = vloss + policy_weight * ploss
            total_ploss += ploss.item()
            total_pacc += compute_policy_accuracy(policy_pred, policy_target)
            n_policy_batches += 1

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()

        if warmup_scheduler is not None:
            warmup_scheduler.step()

        total_vloss += vloss.item()
        total_vacc += compute_value_accuracy(value_pred, value_target)
        n_batches += 1
        n_samples += bs
        global_step += 1

    metrics = {
        "train_value_loss": total_vloss / max(n_batches, 1),
        "train_value_acc": total_vacc / max(n_batches, 1),
        "train_policy_loss": total_ploss / max(n_policy_batches, 1),
        "train_policy_acc": total_pacc / max(n_policy_batches, 1),
    }
    return metrics, global_step


@torch.no_grad()
def eval_epoch(model, loader, device, value_criterion, policy_weight=0.5,
               model_type='v1'):
    """Evaluate one epoch. Returns metrics dict.

    model_type: 'v1' uses flat feature batches (H5Dataset);
                'deepsets' uses dict batches (H5DatasetV2).
    """
    model.eval()
    total_vloss = 0.0
    total_ploss = 0.0
    total_vacc = 0.0
    total_pacc = 0.0
    total_brier = 0.0
    n_batches = 0
    n_policy_batches = 0
    n_samples = 0

    # Running stats for value predictions
    vpred_sum = 0.0
    vpred_sq_sum = 0.0
    vpred_min = float("inf")
    vpred_max = float("-inf")
    vpred_count = 0

    for batch in loader:
        if model_type == 'deepsets':
            value_pred, value_target, bs = _forward_deepsets(model, batch, device)
        else:
            features, policy_target, value_target, sample_weight = [
                b.to(device) for b in batch
            ]
            policy_pred, value_pred = model(features)
            bs = features.shape[0]

        vloss = value_criterion(value_pred, value_target)
        total_vloss += vloss.item()
        total_vacc += compute_value_accuracy(value_pred, value_target)

        # Brier score
        total_brier += compute_brier_score(value_pred, value_target) * bs
        n_samples += bs

        if model_type != 'deepsets' and policy_pred is not None:
            ploss = F.mse_loss(policy_pred, policy_target)
            total_ploss += ploss.item()
            total_pacc += compute_policy_accuracy(policy_pred, policy_target)
            n_policy_batches += 1

        n_batches += 1

        # Value prediction stats (as probabilities)
        vp = torch.sigmoid(value_pred).cpu()
        vpred_sum += vp.sum().item()
        vpred_sq_sum += (vp ** 2).sum().item()
        vpred_min = min(vpred_min, vp.min().item())
        vpred_max = max(vpred_max, vp.max().item())
        vpred_count += vp.numel()

    vpred_mean = vpred_sum / max(vpred_count, 1)
    vpred_var = max((vpred_sq_sum / max(vpred_count, 1)) - vpred_mean ** 2, 0)

    metrics = {
        "val_value_loss": total_vloss / max(n_batches, 1),
        "val_value_acc": total_vacc / max(n_batches, 1),
        "val_policy_loss": total_ploss / max(n_policy_batches, 1),
        "val_policy_acc": total_pacc / max(n_policy_batches, 1),
        "val_brier": total_brier / max(n_samples, 1),
        "val_vpred_mean": vpred_mean,
        "val_vpred_std": vpred_var ** 0.5,
        "val_vpred_min": vpred_min,
        "val_vpred_max": vpred_max,
    }
    return metrics


# ---------------------------------------------------------------------------
# LR schedule: linear warmup + cosine decay
# ---------------------------------------------------------------------------

class WarmupCosineScheduler(torch.optim.lr_scheduler._LRScheduler):
    """Linear warmup for warmup_steps, then cosine decay to min_lr."""

    def __init__(self, optimizer, warmup_steps, total_steps, min_lr=1e-6,
                 last_epoch=-1):
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.min_lr = min_lr
        super().__init__(optimizer, last_epoch)

    def get_lr(self):
        step = self.last_epoch
        if step < self.warmup_steps:
            # Linear warmup
            scale = (step + 1) / max(self.warmup_steps, 1)
        else:
            # Cosine decay
            progress = (step - self.warmup_steps) / max(
                1, self.total_steps - self.warmup_steps)
            progress = min(progress, 1.0)
            scale = 0.5 * (1.0 + math.cos(math.pi * progress))
        return [max(self.min_lr, base_lr * scale) for base_lr in self.base_lrs]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

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


def get_schema_hash():
    """Hash the schema_v1.json file if it exists."""
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "schema_v1.json")
    if os.path.exists(schema_path):
        with open(schema_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    return "no_schema"


def get_schema_version():
    """Read schema version from schema_v1.json."""
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "schema_v1.json")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            data = json.load(f)
        return data.get("schema_version", "unknown")
    return "unknown"


def check_data_sanity(h5_path, label_strategy, n_sample=10000):
    """Quick sanity check on an HDF5 file: label distribution, NaN/Inf."""
    print(f"  Sanity check: {os.path.basename(h5_path)}")
    with h5py.File(h5_path, "r") as f:
        n = f["features"].shape[0]
        state_dim = f["features"].shape[1]

        # Sample a subset for quick checks
        sample_n = min(n_sample, n)
        indices = np.sort(np.random.choice(n, sample_n, replace=False))

        features_sample = f["features"][indices]
        if np.any(np.isnan(features_sample)):
            print("  FATAL: NaN in features!")
            sys.exit(1)
        if np.any(np.isinf(features_sample)):
            print("  FATAL: Inf in features!")
            sys.exit(1)

        # Label distribution
        label_key = {
            "A": "label_A", "B": "label_A", "C": "label_C", "D": "label_D"
        }[label_strategy]
        labels = f[label_key][indices]
        l_min, l_max = labels.min(), labels.max()
        l_mean, l_std = labels.mean(), labels.std()
        n_high = (labels > 0.5).sum()
        n_low = (labels <= 0.5).sum()

        print(f"    N={n:,}, state_dim={state_dim}")
        print(f"    Labels ({label_key}): min={l_min:.4f}, max={l_max:.4f}, "
              f"mean={l_mean:.4f}, std={l_std:.4f}")
        print(f"    P0 wins (>0.5): {n_high} ({100*n_high/sample_n:.1f}%), "
              f"P0 loses (<=0.5): {n_low} ({100*n_low/sample_n:.1f}%)")

        if l_std < 0.01:
            print(f"  FATAL: Labels have std={l_std:.6f} < 0.01 - data corrupt!")
            sys.exit(1)

        print("    Sanity check: PASSED")
    return n, state_dim


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Train PrismataNet neural network evaluation function")

    # Data
    parser.add_argument("--train-file", type=str, required=True,
                        help="Path to training HDF5 file (train.h5)")
    parser.add_argument("--val-file", type=str, required=True,
                        help="Path to validation HDF5 file (val.h5)")
    parser.add_argument("--output-dir", type=str,
                        default="c:/libraries/PrismataAI/training/models",
                        help="Output directory for checkpoints and logs")

    # Model selection
    parser.add_argument("--model", type=str, default="v1",
                        choices=["v1", "flat", "deepsets"],
                        help="Model architecture: 'v1'/'flat' = PrismataNet (default), "
                             "'deepsets' = PrismataDeepSets (requires --property-table)")
    parser.add_argument("--property-table", type=str, default=None,
                        help="Path to property_table.json (required for --model deepsets)")

    # Architecture
    parser.add_argument("--hidden-dim", type=int, default=256,
                        help="Hidden dimension for trunk (default 256)")
    parser.add_argument("--num-layers", type=int, default=4,
                        help="Number of residual blocks (default 4)")
    parser.add_argument("--dropout", type=float, default=0.1,
                        help="Dropout rate (default 0.1)")
    parser.add_argument("--value-only", action="store_true",
                        help="Train value head only (skip policy)")

    # Training
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4,
                        help="Peak learning rate (default 3e-4)")
    parser.add_argument("--weight-decay", type=float, default=1e-4,
                        help="L2 weight decay (default 1e-4)")
    parser.add_argument("--warmup-steps", type=int, default=1000,
                        help="Linear LR warmup steps (default 1000)")
    parser.add_argument("--patience", type=int, default=10,
                        help="Early stopping patience in epochs (0=disabled)")
    parser.add_argument("--policy-weight", type=float, default=0.5,
                        help="Weight for policy loss (default 0.5)")

    # Labels & weighting
    parser.add_argument("--label-strategy", type=str, default="A",
                        choices=["A", "B", "C", "D"],
                        help="Label strategy from HDF5 (default A)")
    parser.add_argument("--rating-weight", action="store_true",
                        help="Weight samples by ((r0+r1)/4000)^2")
    parser.add_argument("--game-weight", action="store_true",
                        help="Weight samples by 1/total_plies (uniform per game)")

    # System
    parser.add_argument("--device", type=str, default="auto",
                        choices=["auto", "cpu", "xpu", "cuda"],
                        help="Device (default: auto-detect)")
    parser.add_argument("--num-workers", type=int, default=2,
                        help="DataLoader workers (default 2)")
    parser.add_argument("--max-records", type=int, default=None,
                        help="Cap training set to N records (random sample). Saves RAM.")
    parser.add_argument("--streaming", action="store_true",
                        help="Stream V2 data from disk instead of loading into RAM. "
                             "Required for large DeepSets datasets (>2M records on 32GB).")
    parser.add_argument("--extra-train-files", nargs="*", default=[],
                        help="Additional H5 training files (same schema). "
                             "Combined with --train-file for streaming mode.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed (random if not set)")

    args = parser.parse_args()

    # Normalize model type
    use_deepsets = args.model == 'deepsets'

    # Validate DeepSets requirements
    if use_deepsets and not args.property_table:
        parser.error("--model deepsets requires --property-table <path>")
    if use_deepsets and args.property_table and not os.path.exists(args.property_table):
        parser.error(f"--property-table path does not exist: {args.property_table}")

    # --- Seed ---
    if args.seed is None:
        args.seed = torch.randint(0, 2**31, (1,)).item()
    set_seed(args.seed)
    print(f"Random seed: {args.seed}")

    # --- Output directory ---
    os.makedirs(args.output_dir, exist_ok=True)

    # Lock file
    lock_path = os.path.join(args.output_dir, "training.lock")
    if os.path.exists(lock_path):
        try:
            with open(lock_path, "r") as lf:
                lock_info = json.load(lf)
            lock_pid = lock_info.get("pid", "?")
            pid_alive = False
            try:
                os.kill(int(lock_pid), 0)
                pid_alive = True
            except (OSError, ValueError):
                pass
            if pid_alive:
                print(f"\nERROR: Another training process (PID {lock_pid}) "
                      f"is using {args.output_dir}")
                print(f"If stale, delete {lock_path} and retry.")
                sys.exit(1)
            else:
                print(f"  WARNING: Stale lock from dead PID {lock_pid}. Removing.")
                os.remove(lock_path)
        except (json.JSONDecodeError, IOError):
            print("  WARNING: Corrupt lock file. Removing.")
            os.remove(lock_path)

    lock_info = {
        "pid": os.getpid(),
        "started": datetime.now().isoformat(),
        "output_dir": args.output_dir,
    }
    with open(lock_path, "w") as lf:
        json.dump(lock_info, lf)

    def _remove_lock():
        try:
            os.remove(lock_path)
        except OSError:
            pass
    atexit.register(_remove_lock)

    # --- Device ---
    device = get_device(args.device)

    # --- Load data ---
    print("\nLoading data...")

    if use_deepsets:
        # V2 HDF5 format — skip V1 sanity check, load V2 datasets directly
        schema_version = "v2_deepsets"

        if args.streaming:
            # Streaming mode: read from disk in chunks, minimal RAM usage
            train_paths = [args.train_file] + (args.extra_train_files or [])
            train_ds = H5DatasetV2Streaming(
                train_paths, label_strategy=args.label_strategy,
                max_records=args.max_records)
            val_ds = H5DatasetV2Streaming(
                args.val_file, label_strategy=args.label_strategy)
        else:
            train_ds = H5DatasetV2(args.train_file, label_strategy=args.label_strategy,
                                   max_records=args.max_records)
            val_ds = H5DatasetV2(args.val_file, label_strategy=args.label_strategy)

        train_n = len(train_ds)
        val_n = len(val_ds)
        state_dim = None  # not used for DeepSets
        num_units = 116   # canonical fixed value

        print(f"\n  Train: {train_n:,} examples  (V2 DeepSets {'streaming' if args.streaming else 'in-memory'})")
        print(f"  Val:   {val_n:,} examples")
        print(f"  Num units: {num_units}")
        print(f"  Label strategy: {args.label_strategy}")
        print(f"  Model: DeepSets (property_table={args.property_table})")
    else:
        train_n, train_state_dim = check_data_sanity(
            args.train_file, args.label_strategy)
        val_n, val_state_dim = check_data_sanity(
            args.val_file, args.label_strategy)

        assert train_state_dim == val_state_dim, \
            f"State dim mismatch: train={train_state_dim}, val={val_state_dim}"
        state_dim = train_state_dim

        # Read num_units from schema
        schema_version = get_schema_version()
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "schema_v1.json")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                schema = json.load(f)
            num_units = schema["num_units"]
            expected_dim = schema["state_dim"]
            if state_dim != expected_dim:
                print(f"  WARNING: HDF5 state_dim={state_dim} != "
                      f"schema state_dim={expected_dim}")
        else:
            num_units = (state_dim - 14) // 11
            print(f"  WARNING: No schema_v1.json found. Inferred num_units={num_units}")

        train_ds = H5Dataset(args.train_file, label_strategy=args.label_strategy,
                             value_only=args.value_only,
                             rating_weight=args.rating_weight,
                             game_weight=args.game_weight,
                             max_records=args.max_records)
        val_ds = H5Dataset(args.val_file, label_strategy=args.label_strategy,
                           value_only=args.value_only,
                           rating_weight=False, game_weight=False)

        print(f"\n  Train: {train_n:,} examples")
        print(f"  Val:   {val_n:,} examples")
        print(f"  State dim: {state_dim}")
        print(f"  Num units: {num_units}")
        print(f"  Label strategy: {args.label_strategy}")
        print(f"  Mode: {'value-only' if args.value_only else 'policy+value'}")

    use_workers = args.num_workers
    shuffle_gen = torch.Generator()
    shuffle_gen.manual_seed(args.seed)

    # pin_memory=True for CUDA/CPU, False for XPU (avoids pin_memory bugs)
    pin_mem = device.type != "xpu"

    is_streaming = isinstance(train_ds, IterableDataset)

    if is_streaming:
        # IterableDataset handles its own shuffling via set_epoch()
        train_loader = DataLoader(
            train_ds, batch_size=args.batch_size, shuffle=False,
            drop_last=True, num_workers=use_workers,
            pin_memory=pin_mem, persistent_workers=False)
        val_loader = DataLoader(
            val_ds, batch_size=args.batch_size, shuffle=False,
            num_workers=use_workers, pin_memory=pin_mem,
            persistent_workers=False)
    else:
        train_loader = DataLoader(
            train_ds, batch_size=args.batch_size, shuffle=True,
            drop_last=True, num_workers=use_workers, generator=shuffle_gen,
            pin_memory=pin_mem, persistent_workers=use_workers > 0)
        val_loader = DataLoader(
            val_ds, batch_size=args.batch_size, shuffle=False,
            num_workers=use_workers, pin_memory=pin_mem,
            persistent_workers=use_workers > 0)

    # --- Model ---
    if use_deepsets:
        from model_deepsets import PrismataDeepSets
        model = PrismataDeepSets(
            num_units=num_units,
            dropout=args.dropout,
        ).to(device)
        model.load_property_table(args.property_table)
        param_count = sum(p.numel() for p in model.parameters())
        print(f"\nModel: PrismataDeepSets — {param_count:,} parameters")
    else:
        model = PrismataNet(
            state_dim, num_units, hidden_dim=args.hidden_dim,
            num_layers=args.num_layers, dropout=args.dropout,
            value_only=args.value_only).to(device)
        param_count = sum(p.numel() for p in model.parameters())
        print(f"\nModel: PrismataNet — {param_count:,} parameters "
              f"(hidden={args.hidden_dim}, layers={args.num_layers})")

    # --- Optimizer (exclude bias and LayerNorm from weight decay) ---
    decay_params = []
    no_decay_params = []
    for name, param in model.named_parameters():
        if "bias" in name or "norm" in name:
            no_decay_params.append(param)
        else:
            decay_params.append(param)
    optimizer = torch.optim.AdamW([
        {"params": decay_params, "weight_decay": args.weight_decay},
        {"params": no_decay_params, "weight_decay": 0.0},
    ], lr=args.lr)

    # --- LR Schedule: per-step warmup + cosine decay ---
    steps_per_epoch = max(1, train_n // args.batch_size)
    total_steps = steps_per_epoch * args.epochs
    scheduler = WarmupCosineScheduler(
        optimizer, warmup_steps=args.warmup_steps,
        total_steps=total_steps, min_lr=1e-6)

    # --- Value criterion ---
    value_criterion = nn.BCEWithLogitsLoss()

    # --- SWA setup (last 20% of epochs) ---
    swa_start_epoch = max(1, int(args.epochs * 0.8))
    swa_model = AveragedModel(model)
    swa_scheduler = SWALR(optimizer, swa_lr=args.lr * 0.1)
    swa_active = False

    # --- Run metadata ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hparams = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "warmup_steps": args.warmup_steps,
        "dropout": args.dropout,
        "policy_weight": args.policy_weight,
        "patience": args.patience,
        "weight_decay": args.weight_decay,
        "label_strategy": args.label_strategy,
        "seed": args.seed,
        "model": args.model,
    }
    if use_deepsets:
        hparams["property_table"] = os.path.abspath(args.property_table)
    else:
        hparams["hidden_dim"] = args.hidden_dim
        hparams["num_layers"] = args.num_layers
        hparams["value_only"] = args.value_only
        hparams["rating_weight"] = args.rating_weight
        hparams["game_weight"] = args.game_weight

    run_metadata = {
        "timestamp": timestamp,
        "git_hash": get_git_hash(),
        "schema_version": schema_version,
        "schema_hash": get_schema_hash(),
        "hyperparameters": hparams,
        "data": {
            "train_file": os.path.abspath(args.train_file),
            "val_file": os.path.abspath(args.val_file),
            "train_examples": train_n,
            "val_examples": val_n,
            "state_dim": state_dim,
            "num_units": num_units,
        },
        "model_params": param_count,
        "device": str(device),
    }

    # Save metadata immediately
    metadata_path = os.path.join(args.output_dir, "run_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(run_metadata, f, indent=2)

    # --- Training log ---
    training_log = {"epochs": [], "best_epoch": None, "best_val_loss": None}
    log_path = os.path.join(args.output_dir, "training_log.json")

    def save_log():
        with open(log_path, "w") as f:
            json.dump(training_log, f, indent=2)

    # --- Training loop ---
    best_val_vloss = float("inf")
    best_epoch = 0
    patience_counter = 0
    global_step = 0

    model_type_str = 'deepsets' if use_deepsets else 'v1'
    mode_str = "deepsets" if use_deepsets else ("value-only" if args.value_only else "policy+value")
    print(f"\nTraining {mode_str} for {args.epochs} epochs "
          f"(batch={args.batch_size}, lr={args.lr}, "
          f"patience={args.patience}, swa_from={swa_start_epoch})")
    print()

    # Header — DeepSets and value-only both use the compact value-only format
    if use_deepsets or args.value_only:
        print(f"{'Ep':>4} {'TrVL':>7} {'TrVA':>6} {'VaVL':>7} {'VaVA':>6} "
              f"{'Brier':>6} {'VPred':>14} {'LR':>9} {'Time':>5} {'Note':>8}")
        print("-" * 88)
    else:
        print(f"{'Ep':>4} {'TrPL':>7} {'TrVL':>7} {'TrPA':>6} {'TrVA':>6} "
              f"{'VaPL':>7} {'VaVL':>7} {'VaPA':>6} {'VaVA':>6} "
              f"{'Brier':>6} {'LR':>9} {'Time':>5} {'Note':>8}")
        print("-" * 112)

    wall_start = time.time()

    for epoch in range(1, args.epochs + 1):
        # Update streaming dataset epoch for chunk shuffling
        if is_streaming:
            train_ds.set_epoch(epoch)

        if device.type == "xpu":
            torch.xpu.synchronize()
        t0 = time.time()

        # Train
        # Use per-batch scheduler stepping for smooth cosine decay.
        # SWA has its own scheduler that steps per-epoch.
        active_scheduler = swa_scheduler if swa_active else scheduler
        train_metrics, global_step = train_epoch(
            model, train_loader, optimizer, device, value_criterion,
            policy_weight=args.policy_weight, grad_clip=1.0,
            warmup_scheduler=active_scheduler if not swa_active else None,
            global_step=global_step, model_type=model_type_str)

        # SWA scheduler steps per-epoch (not per-batch)
        if swa_active:
            swa_scheduler.step()

        # Evaluate
        val_metrics = eval_epoch(model, val_loader, device, value_criterion,
                                 policy_weight=args.policy_weight,
                                 model_type=model_type_str)

        # SWA
        if epoch >= swa_start_epoch:
            if not swa_active:
                swa_active = True
                print(f"\n  SWA activated at epoch {epoch}")
            swa_model.update_parameters(model)

        lr = optimizer.param_groups[0]["lr"]

        if device.type == "xpu":
            torch.xpu.synchronize()
        elapsed = time.time() - t0

        # Check improvement
        note = ""
        va_vl = val_metrics["val_value_loss"]
        if va_vl < best_val_vloss:
            best_val_vloss = va_vl
            best_epoch = epoch
            patience_counter = 0
            note = "*best"

            # Save best checkpoint
            ckpt = {
                "epoch": epoch,
                "global_step": global_step,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "model_type": model_type_str,
                "num_units": num_units,
                "dropout": args.dropout,
                "schema_version": schema_version,
                "label_strategy": args.label_strategy,
                "val_value_loss": va_vl,
                "val_value_acc": val_metrics["val_value_acc"],
                "val_brier": val_metrics["val_brier"],
                "hyperparameters": run_metadata["hyperparameters"],
            }
            if use_deepsets:
                ckpt["property_table_path"] = os.path.abspath(args.property_table)
            else:
                ckpt["state_dim"] = state_dim
                ckpt["hidden_dim"] = args.hidden_dim
                ckpt["num_layers"] = args.num_layers
                ckpt["value_only"] = args.value_only
            torch.save(ckpt, os.path.join(args.output_dir, "best_model.pt"))
        else:
            patience_counter += 1

        vpred_str = f"[{val_metrics['val_vpred_min']:.3f},{val_metrics['val_vpred_max']:.3f}]"
        brier_str = f"{val_metrics['val_brier']:.4f}"

        # Print epoch
        tr = train_metrics
        va = val_metrics
        if use_deepsets or args.value_only:
            print(f"{epoch:4d} {tr['train_value_loss']:7.4f} "
                  f"{tr['train_value_acc']:6.1%} "
                  f"{va['val_value_loss']:7.4f} {va['val_value_acc']:6.1%} "
                  f"{brier_str:>6s} {vpred_str:>14s} "
                  f"{lr:9.6f} {elapsed:4.0f}s {note:>8s}")
        else:
            print(f"{epoch:4d} {tr['train_policy_loss']:7.4f} "
                  f"{tr['train_value_loss']:7.4f} "
                  f"{tr['train_policy_acc']:6.1%} "
                  f"{tr['train_value_acc']:6.1%} "
                  f"{va['val_policy_loss']:7.4f} "
                  f"{va['val_value_loss']:7.4f} "
                  f"{va['val_policy_acc']:6.1%} "
                  f"{va['val_value_acc']:6.1%} "
                  f"{brier_str:>6s} {lr:9.6f} {elapsed:4.0f}s {note:>8s}")

        # Log epoch
        epoch_log = {
            "epoch": epoch,
            "global_step": global_step,
            "train_value_loss": round(tr["train_value_loss"], 6),
            "train_value_acc": round(tr["train_value_acc"], 4),
            "val_value_loss": round(va["val_value_loss"], 6),
            "val_value_acc": round(va["val_value_acc"], 4),
            "val_brier": round(va["val_brier"], 6),
            "val_vpred_mean": round(va["val_vpred_mean"], 4),
            "val_vpred_std": round(va["val_vpred_std"], 4),
            "val_vpred_min": round(va["val_vpred_min"], 4),
            "val_vpred_max": round(va["val_vpred_max"], 4),
            "lr": lr,
            "time_s": round(elapsed, 1),
        }
        if not args.value_only:
            epoch_log["train_policy_loss"] = round(tr["train_policy_loss"], 6)
            epoch_log["train_policy_acc"] = round(tr["train_policy_acc"], 4)
            epoch_log["val_policy_loss"] = round(va["val_policy_loss"], 6)
            epoch_log["val_policy_acc"] = round(va["val_policy_acc"], 4)

        training_log["epochs"].append(epoch_log)
        training_log["best_epoch"] = best_epoch
        training_log["best_val_loss"] = round(best_val_vloss, 6)

        # Save log every epoch (so partial runs are recoverable)
        save_log()

        # Periodic checkpoint
        if epoch % 10 == 0:
            periodic_ckpt = {
                "epoch": epoch,
                "global_step": global_step,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "model_type": model_type_str,
                "num_units": num_units,
                "dropout": args.dropout,
                "schema_version": schema_version,
            }
            if use_deepsets:
                periodic_ckpt["property_table_path"] = os.path.abspath(args.property_table)
            else:
                periodic_ckpt["state_dim"] = state_dim
                periodic_ckpt["hidden_dim"] = args.hidden_dim
                periodic_ckpt["num_layers"] = args.num_layers
                periodic_ckpt["value_only"] = args.value_only
            torch.save(periodic_ckpt, os.path.join(args.output_dir, f"checkpoint_ep{epoch}.pt"))

        # Early stopping
        if args.patience > 0 and patience_counter >= args.patience:
            print(f"\nEarly stopping at epoch {epoch} "
                  f"(no improvement for {args.patience} epochs)")
            break

    wall_time = time.time() - wall_start

    # --- Save SWA model ---
    if swa_active:
        print("\nSaving SWA model...")
        # Update batch normalization statistics (SWA requirement)
        # We run a forward pass through training data with the averaged model
        try:
            torch.optim.swa_utils.update_bn(train_loader, swa_model, device)
        except Exception as e:
            print(f"  WARNING: SWA BN update failed ({e}), saving without BN update")

        swa_ckpt = {
            "epoch": epoch,
            "global_step": global_step,
            "model_state_dict": swa_model.module.state_dict(),
            "model_type": model_type_str,
            "num_units": num_units,
            "dropout": args.dropout,
            "schema_version": schema_version,
            "swa_start_epoch": swa_start_epoch,
        }
        if use_deepsets:
            swa_ckpt["property_table_path"] = os.path.abspath(args.property_table)
        else:
            swa_ckpt["state_dim"] = state_dim
            swa_ckpt["hidden_dim"] = args.hidden_dim
            swa_ckpt["num_layers"] = args.num_layers
            swa_ckpt["value_only"] = args.value_only
        torch.save(swa_ckpt, os.path.join(args.output_dir, "swa_model.pt"))
        print(f"  SWA model saved to {args.output_dir}/swa_model.pt")

        # Evaluate SWA model
        swa_val = eval_epoch(swa_model, val_loader, device, value_criterion,
                             model_type=model_type_str)
        print(f"  SWA val_loss={swa_val['val_value_loss']:.4f}, "
              f"val_acc={swa_val['val_value_acc']:.1%}, "
              f"brier={swa_val['val_brier']:.4f}")

    # --- Final summary ---
    print(f"\nDone! Best val loss: {best_val_vloss:.4f} at epoch {best_epoch}")
    print(f"Total wall time: {wall_time:.0f}s ({wall_time/60:.1f}min)")
    print(f"Best model: {args.output_dir}/best_model.pt")

    # Update metadata with results
    run_metadata["results"] = {
        "best_val_loss": round(best_val_vloss, 6),
        "best_epoch": best_epoch,
        "final_epoch": epoch,
        "total_wall_time_s": round(wall_time, 1),
        "early_stopped": patience_counter >= args.patience if args.patience > 0 else False,
    }
    if swa_active:
        run_metadata["results"]["swa_val_loss"] = round(
            swa_val["val_value_loss"], 6)
        run_metadata["results"]["swa_val_acc"] = round(
            swa_val["val_value_acc"], 4)
        run_metadata["results"]["swa_brier"] = round(
            swa_val["val_brier"], 6)

    with open(metadata_path, "w") as f:
        json.dump(run_metadata, f, indent=2)
    print(f"Metadata: {metadata_path}")

    # Final log save
    training_log["total_wall_time_s"] = round(wall_time, 1)
    save_log()
    print(f"Training log: {log_path}")


if __name__ == "__main__":
    main()
