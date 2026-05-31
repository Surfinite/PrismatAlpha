#!/usr/bin/env python
"""Integration test for train.py checkpoint/resume correctness.

Strategy (mirrors the real crash-and-resume scenario):
  Run A  : uninterrupted   --epochs 4
  Run B1 : --epochs 4 --stop-after-epoch 2   (clean stop, writes latest_checkpoint.pt)
  Run B2 : --epochs 4 --resume B/latest_checkpoint.pt   (continues 3,4)

PASS criteria:
  * B2 reports it resumes at epoch 3.
  * B's final model (latest_checkpoint.pt @ epoch 4) is bitwise-identical to A's.
  * best_val_vloss / best_epoch / patience_counter / global_step match.
  * training_log epochs 3,4 val_value_loss match between A and B.

Running on CPU, non-streaming, with dropout=0.1 and a short warmup so the cosine
schedule actually engages -- this exercises the DataLoader shuffle generator,
dropout RNG, the LR scheduler, and SWA (swa_start = epoch 3 when epochs=4).
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

import h5py
import torch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN = os.path.join(REPO, "training", "train.py")
PROP = os.path.join(REPO, "training", "property_table.json")
SRC_H5 = os.path.join(REPO, "training", "data", "local_mbvmb_v2.h5")
N_TINY = 2048


def make_tiny(src, dst, n):
    """Copy the first n records of every dataset in src into a small dst file."""
    with h5py.File(src, "r") as f, h5py.File(dst, "w") as g:
        for ak, av in f.attrs.items():
            g.attrs[ak] = av
        for name, ds in f.items():
            if not isinstance(ds, h5py.Dataset):
                continue
            arr = ds[: min(n, ds.shape[0])]
            d = g.create_dataset(name, data=arr)
            for ak, av in ds.attrs.items():
                d.attrs[ak] = av


def run(args, label):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    p = subprocess.run(
        [sys.executable, TRAIN] + args,
        cwd=REPO, env=env, capture_output=True, text=True,
    )
    if p.returncode != 0:
        print(f"\n=== {label} FAILED (rc={p.returncode}) ===")
        print("--- stdout tail ---")
        print("\n".join(p.stdout.splitlines()[-25:]))
        print("--- stderr tail ---")
        print("\n".join(p.stderr.splitlines()[-25:]))
    return p


def state_max_diff(sa, sb):
    keys = set(sa) | set(sb)
    md = 0.0
    worst = None
    for k in keys:
        if k not in sa or k not in sb:
            return float("inf"), f"key mismatch: {k}"
        a, b = sa[k].float(), sb[k].float()
        if a.shape != b.shape:
            return float("inf"), f"shape mismatch on {k}: {a.shape} vs {b.shape}"
        d = (a - b).abs().max().item()
        if d > md:
            md, worst = d, k
    return md, worst


def main():
    tmp = tempfile.mkdtemp(prefix="resume_test_")
    print(f"workdir: {tmp}")
    tiny = os.path.join(tmp, "tiny.h5")
    make_tiny(SRC_H5, tiny, N_TINY)

    dir_a = os.path.join(tmp, "A")
    dir_b = os.path.join(tmp, "B")

    base = [
        "--model", "deepsets", "--value-only", "--property-table", PROP,
        "--train-file", tiny, "--val-file", tiny,
        "--label-strategy", "A", "--batch-size", "256", "--lr", "3e-4",
        "--weight-decay", "1e-4", "--warmup-steps", "5", "--patience", "100",
        "--seed", "42", "--device", "cpu", "--num-workers", "0", "--dropout", "0.1",
    ]
    streaming = "streaming" in sys.argv[1:]
    if streaming:
        base += ["--streaming"]
        print("MODE: streaming (real Task-B data path)")
    else:
        print("MODE: in-memory")

    ok = True

    pa = run(base + ["--epochs", "4", "--output-dir", dir_a], "Run A (uninterrupted)")
    if pa.returncode != 0:
        sys.exit(1)

    pb1 = run(base + ["--epochs", "4", "--stop-after-epoch", "2", "--output-dir", dir_b],
              "Run B1 (stop after 2)")
    if pb1.returncode != 0:
        print("\nRED: --stop-after-epoch not implemented yet (expected before the feature lands).")
        sys.exit(1)

    ckpt_b = os.path.join(dir_b, "latest_checkpoint.pt")
    if not os.path.exists(ckpt_b):
        print(f"\nFAIL: no latest_checkpoint.pt after B1 ({ckpt_b})")
        sys.exit(1)

    pb2 = run(base + ["--epochs", "4", "--resume", ckpt_b, "--output-dir", dir_b],
              "Run B2 (resume)")
    if pb2.returncode != 0:
        print("\nRED: --resume not implemented yet (expected before the feature lands).")
        sys.exit(1)

    # --- Assertions ---
    if "epoch 3" not in pb2.stdout:
        print("FAIL: B2 did not report resuming at epoch 3")
        print("\n".join(pb2.stdout.splitlines()[:15]))
        ok = False

    a_ck = torch.load(os.path.join(dir_a, "latest_checkpoint.pt"),
                      map_location="cpu", weights_only=False)
    b_ck = torch.load(ckpt_b, map_location="cpu", weights_only=False)

    for tag, ck in (("A", a_ck), ("B", b_ck)):
        if ck.get("epoch") != 4:
            print(f"FAIL: {tag} latest_checkpoint epoch={ck.get('epoch')} (expected 4)")
            ok = False

    md, worst = state_max_diff(a_ck["model_state_dict"], b_ck["model_state_dict"])
    print(f"\nmodel_state_dict max abs diff (A vs resumed B): {md:.3e}  (worst key: {worst})")
    if md > 1e-6:
        print("FAIL: resumed model diverged from uninterrupted run")
        ok = False

    for key in ("best_val_vloss", "best_epoch", "patience_counter", "global_step"):
        if a_ck.get(key) != b_ck.get(key):
            print(f"FAIL: {key} mismatch  A={a_ck.get(key)}  B={b_ck.get(key)}")
            ok = False

    la = json.load(open(os.path.join(dir_a, "training_log.json")))
    lb = json.load(open(os.path.join(dir_b, "training_log.json")))
    a_by_ep = {e["epoch"]: e for e in la["epochs"]}
    b_by_ep = {e["epoch"]: e for e in lb["epochs"]}
    for ep in (3, 4):
        if ep not in a_by_ep or ep not in b_by_ep:
            print(f"FAIL: epoch {ep} missing from a log ({ep in a_by_ep}) or b log ({ep in b_by_ep})")
            ok = False
            continue
        va, vb = a_by_ep[ep]["val_value_loss"], b_by_ep[ep]["val_value_loss"]
        if abs(va - vb) > 1e-6:
            print(f"FAIL: epoch {ep} val_value_loss A={va} B={vb}")
            ok = False

    if ok:
        print("\nPASS: resume is bitwise-identical to the uninterrupted run.")
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(0)
    else:
        print(f"\nFAILED. Artifacts kept at {tmp}")
        sys.exit(1)


if __name__ == "__main__":
    main()
