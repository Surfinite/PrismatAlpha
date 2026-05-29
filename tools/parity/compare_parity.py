"""
PyTorch <-> C++ DeepSets value-parity comparator.

Reads one or more C++ dump JSONs produced by:
    bin/PrismataAI.exe --dump-features <gameState.json> <out.json> [weights.bin]

For each dump it reconstructs the model inputs from the EXACT tokens the C++ forward
used (per-instance unit_index + 10 instance floats, the 116x3 supply, the 14 globals),
then runs:
  (1) the reference PyTorch model loaded from the tied-out .pt   -> logit_torch
  (2) the numpy forward over the shipped DSN2 .bin tensors        -> logit_numpy
and compares both to the C++-emitted logit/value.

This isolates faithfulness of the C++ inference (forward math + weight load) GIVEN
identical inputs.  Token-build faithfulness is checked separately (Tier A) on a couple
of states.

Acceptance (per the review spec):
  |value_cpp - value_torch| < 1e-3   (final P0-positive scalar)
  |logit_cpp - logit_torch| small    (tail-robust, reported)

Usage:
  python compare_parity.py <dump1.json> [dump2.json ...]
"""

import json
import os
import sys

# PyTorch lives in a non-standard location on this machine (mirrors export_weights_v2.py)
sys.path.insert(0, "C:/libraries/torch_pkg")
import numpy as np
import torch

TRAIN_DIR = "C:/libraries/PrismataAI/training"
sys.path.insert(0, TRAIN_DIR)
from model_deepsets import PrismataDeepSets
import export_weights_v2 as ew  # numpy_forward + load_binary

# The .pt proven (Phase 1) to re-export byte-identical to neural_weights_mbonly.bin (ep98, val 0.8231)
PT_PATH  = "C:/libraries/PrismataAI/training/cloud-runs/deepsets_12M_full/2026-03-13_05-44-21/models/best_model.pt"
BIN_PATH = "C:/libraries/PrismataAI-dave-master/bin/asset/config/neural_weights_mbonly.bin"

VALUE_TOL = 1e-3


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def value_from_logit(logit):
    return 2.0 * sigmoid(logit) - 1.0


def load_model(pt_path):
    ckpt = torch.load(pt_path, map_location="cpu", weights_only=True)
    cfg = ckpt.get("model_config", {})
    model = PrismataDeepSets(**cfg)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, cfg


def build_inputs(dump, num_units):
    insts = dump["instances"]
    N = len(insts)
    if N == 0:
        feats = np.zeros((1, 10), dtype=np.float32)
        ids = np.zeros((1,), dtype=np.int64)
        count = 0
    else:
        feats = np.array([i["instance"] for i in insts], dtype=np.float32).reshape(N, 10)
        ids = np.array([i["unit_index"] for i in insts], dtype=np.int64)
        count = N
    supply = np.zeros((num_units, 3), dtype=np.float32)
    for s in dump["supply"]:
        u = s["unit_index"]
        supply[u, 0] = s["p0"]
        supply[u, 1] = s["p1"]
        supply[u, 2] = 1.0
    globs = np.array(dump["globals"], dtype=np.float32)
    assert globs.shape == (14,), f"expected 14 globals, got {globs.shape}"
    return feats, ids, count, supply, globs


def torch_logit(model, feats, ids, count, supply, globs):
    with torch.no_grad():
        ft = torch.from_numpy(feats).unsqueeze(0).float()
        it = torch.from_numpy(ids).unsqueeze(0)
        ct = torch.tensor([count], dtype=torch.long)
        st = torch.from_numpy(supply).unsqueeze(0).float()
        gt = torch.from_numpy(globs).unsqueeze(0).float()
        return model(ft, it, ct, st, gt)[0, 0].item()


def main():
    if len(sys.argv) < 2:
        print("usage: python compare_parity.py <dump1.json> [dump2.json ...]")
        sys.exit(2)

    print(f"PyTorch reference .pt : {PT_PATH}")
    print(f"DSN2 .bin             : {BIN_PATH}")
    model, cfg = load_model(PT_PATH)
    num_units = cfg.get("num_units", 116)
    hdr, bin_tensors = ew.load_binary(BIN_PATH)
    print(f"loaded model (cfg num_units={num_units}) and .bin (hdr num_units={hdr['num_units']}, tensors={hdr['num_tensors']})")
    print()

    hdr_fmt = (f"{'state':28s} {'N':>3s} {'val_cpp':>10s} {'val_torch':>10s} "
               f"{'|dval|':>9s} {'logit_cpp':>10s} {'logit_torch':>11s} {'logit_np':>10s} "
               f"{'drop':>4s} {'verdict':>8s}")
    print(hdr_fmt)
    print("-" * len(hdr_fmt))

    worst_dval = 0.0
    any_fail = False
    any_drop = False

    for path in sys.argv[1:]:
        with open(path) as f:
            dump = json.load(f)
        feats, ids, count, supply, globs = build_inputs(dump, num_units)

        lt = torch_logit(model, feats, ids, count, supply, globs)
        # numpy forward over the shipped .bin (3rd cross-check)
        ln = ew.numpy_forward(bin_tensors, feats, ids, count, supply, globs)

        vc = dump["value_p0"]
        lc = dump["logit_p0"]
        vt = value_from_logit(lt)
        dval = abs(vc - vt)
        drop = len(dump.get("dropped_instances", []))
        worst_dval = max(worst_dval, dval)
        if drop:
            any_drop = True
        ok = dval < VALUE_TOL and drop == 0
        if not ok:
            any_fail = True
        name = os.path.basename(path)
        print(f"{name:28s} {count:3d} {vc:10.6f} {vt:10.6f} {dval:9.2e} "
              f"{lc:10.5f} {lt:11.5f} {ln:10.5f} {drop:4d} {'PASS' if ok else 'FAIL':>8s}")

    print("-" * len(hdr_fmt))
    print(f"worst |value_cpp - value_torch| = {worst_dval:.2e}  (tol {VALUE_TOL:.0e})")
    print(f"overall: {'ALL PASS' if not any_fail else 'FAIL'}"
          + ("  [DROPPED INSTANCES PRESENT]" if any_drop else ""))
    sys.exit(0 if not any_fail else 1)


if __name__ == "__main__":
    main()
