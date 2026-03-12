"""
Export PrismataDeepSets weights to a binary format for C++ inference (DSN2 format).

Binary format:
  Header (9 × uint32 = 36 bytes):
    magic:          0x44534E32  ("DSN2")
    version:        2
    num_units:      116
    d_embed:        32
    num_properties: 13
    encoder_hidden: 128
    supply_hidden:  32
    value_hidden:   256
    num_tensors:    16

  Tensors (16, in fixed order):
    1.  unit_embedding.weight        (116, 32)
    2.  instance_encoder.0.weight    (128, 55)
    3.  instance_encoder.0.bias      (128,)
    4.  instance_encoder.2.weight    (128, 128)
    5.  instance_encoder.2.bias      (128,)
    6.  supply_encoder.0.weight      (32, 3)
    7.  supply_encoder.0.bias        (32,)
    8.  supply_encoder.2.weight      (32, 32)
    9.  supply_encoder.2.bias        (32,)
    10. value_head.0.weight          (256, 302)
    11. value_head.0.bias            (256,)
    12. value_head.3.weight          (256, 256)
    13. value_head.3.bias            (256,)
    14. value_head.6.weight          (1, 256)
    15. value_head.6.bias            (1,)
    16. property_table               (116, 13)

  Each tensor record:
    name_len (uint32)  — length of name bytes (including null terminator)
    name     (bytes)   — UTF-8, null-terminated
    ndims    (uint32)  — number of dimensions
    shape    (ndims × uint32)
    data     (float32[]) — row-major (C) order

NOTE on value_head indexing:
  The value_head Sequential has Dropout at indices 2 and 5, so the three
  Linear layers are at indices 0, 3, and 6.

Usage:
  python export_weights_v2.py <model.pt> <output.bin> [--property-table property_table.json]

Examples:
  python training/export_weights_v2.py training/models/best_deepsets.pt bin/asset/config/deepsets_weights.bin
  python training/export_weights_v2.py training/models/best_deepsets.pt out.bin --property-table training/property_table.json
"""

import argparse
import os
import struct
import sys

import numpy as np

# PyTorch may be in a non-standard location on this machine
sys.path.insert(0, "C:/libraries/torch_pkg")
import torch

# Import PrismataDeepSets from the training module
_train_dir = os.path.dirname(os.path.abspath(__file__))
if _train_dir not in sys.path:
    sys.path.insert(0, _train_dir)
from model_deepsets import PrismataDeepSets


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC   = 0x44534E32  # "DSN2"
VERSION = 2


# ---------------------------------------------------------------------------
# Binary I/O helpers
# ---------------------------------------------------------------------------

def write_tensor(f, name: str, tensor) -> None:
    """Write a single named tensor to the open binary file.

    Accepts either a torch.Tensor or a numpy ndarray.

    Record format:
      name_len (uint32) — number of bytes including null terminator
      name     (bytes)  — UTF-8, null-terminated
      ndims    (uint32) — number of shape dimensions
      shape    (ndims × uint32)
      data     (float32, row-major)
    """
    if isinstance(tensor, torch.Tensor):
        data = tensor.detach().cpu().float().contiguous().numpy()
    else:
        data = np.asarray(tensor, dtype=np.float32)

    name_bytes = name.encode("utf-8") + b"\x00"
    f.write(struct.pack("<I", len(name_bytes)))
    f.write(name_bytes)
    f.write(struct.pack("<I", data.ndim))
    for dim in data.shape:
        f.write(struct.pack("<I", int(dim)))
    f.write(data.tobytes())


def read_tensor(f):
    """Read a single tensor record from an open binary file.

    Returns: (name: str, data: np.ndarray)
    """
    name_len = struct.unpack("<I", f.read(4))[0]
    name     = f.read(name_len).decode("utf-8").rstrip("\x00")
    ndims    = struct.unpack("<I", f.read(4))[0]
    shape    = tuple(struct.unpack("<I", f.read(4))[0] for _ in range(ndims))
    total    = int(np.prod(shape)) if shape else 1
    data     = np.frombuffer(f.read(total * 4), dtype=np.float32).copy()
    return name, data.reshape(shape) if shape else data


# ---------------------------------------------------------------------------
# Tensor collection
# ---------------------------------------------------------------------------

# Fixed export order — must match what C++ NeuralNet loads
_TENSOR_SPECS = [
    # (attr_path, layer_attr)
    # For Embedding: .weight
    # For Sequential layers: .[index].weight / .[index].bias
    # For buffer: .property_table
]

def collect_tensors(model: PrismataDeepSets) -> list:
    """Return list of (name, tensor_or_ndarray) in the fixed DSN2 export order."""
    tensors = []

    # 1. Unit embedding
    tensors.append(("unit_embedding.weight", model.unit_embedding.weight))

    # 2-5. Instance encoder (Sequential: 0=Linear, 1=ReLU, 2=Linear, 3=ReLU)
    tensors.append(("instance_encoder.0.weight", model.instance_encoder[0].weight))
    tensors.append(("instance_encoder.0.bias",   model.instance_encoder[0].bias))
    tensors.append(("instance_encoder.2.weight", model.instance_encoder[2].weight))
    tensors.append(("instance_encoder.2.bias",   model.instance_encoder[2].bias))

    # 6-9. Supply encoder (Sequential: 0=Linear, 1=ReLU, 2=Linear, 3=ReLU)
    tensors.append(("supply_encoder.0.weight", model.supply_encoder[0].weight))
    tensors.append(("supply_encoder.0.bias",   model.supply_encoder[0].bias))
    tensors.append(("supply_encoder.2.weight", model.supply_encoder[2].weight))
    tensors.append(("supply_encoder.2.bias",   model.supply_encoder[2].bias))

    # 10-15. Value head (Sequential: 0=Linear, 1=ReLU, 2=Dropout, 3=Linear, 4=ReLU, 5=Dropout, 6=Linear)
    tensors.append(("value_head.0.weight", model.value_head[0].weight))
    tensors.append(("value_head.0.bias",   model.value_head[0].bias))
    tensors.append(("value_head.3.weight", model.value_head[3].weight))
    tensors.append(("value_head.3.bias",   model.value_head[3].bias))
    tensors.append(("value_head.6.weight", model.value_head[6].weight))
    tensors.append(("value_head.6.bias",   model.value_head[6].bias))

    # 16. Property table buffer (non-trainable)
    tensors.append(("property_table", model.property_table))

    return tensors


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_model(model: PrismataDeepSets, output_path: str,
                 verbose: bool = False) -> None:
    """Export a PrismataDeepSets model to the DSN2 binary format.

    Args:
        model:       PrismataDeepSets instance (any weights, eval or train mode).
        output_path: Path to write the binary file.
        verbose:     If True, print tensor names and shapes.
    """
    model.eval()

    # Infer dimensions from model structure
    num_units      = model._num_units       # 116
    d_embed        = model.unit_embedding.embedding_dim  # 32
    num_properties = model._num_properties  # 13
    encoder_hidden = model.instance_encoder[0].out_features  # 128
    supply_hidden  = model.supply_encoder[0].out_features    # 32
    value_hidden   = model.value_head[0].out_features        # 256

    tensors = collect_tensors(model)
    num_tensors = len(tensors)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "wb") as f:
        # Header: 9 × uint32 = 36 bytes
        f.write(struct.pack("<I", MAGIC))
        f.write(struct.pack("<I", VERSION))
        f.write(struct.pack("<I", num_units))
        f.write(struct.pack("<I", d_embed))
        f.write(struct.pack("<I", num_properties))
        f.write(struct.pack("<I", encoder_hidden))
        f.write(struct.pack("<I", supply_hidden))
        f.write(struct.pack("<I", value_hidden))
        f.write(struct.pack("<I", num_tensors))

        for name, tensor in tensors:
            write_tensor(f, name, tensor)
            if verbose:
                if isinstance(tensor, torch.Tensor):
                    shape_str = str(list(tensor.shape))
                else:
                    shape_str = str(list(tensor.shape))
                print(f"  {name:40s} {shape_str}")

    if verbose:
        file_size = os.path.getsize(output_path)
        print(f"\nWrote {output_path} ({file_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# Round-trip verification (numpy forward pass)
# ---------------------------------------------------------------------------

def numpy_forward(tensors_dict: dict, instance_features, instance_unit_ids,
                  instance_count: int, supply, globals_vec) -> float:
    """Pure numpy forward pass matching PrismataDeepSets.forward exactly.

    Args:
        tensors_dict:       dict of {name: np.ndarray} from loading the binary.
        instance_features:  (MAX_INST, 10) float32.
        instance_unit_ids:  (MAX_INST,) int — unit type indices.
        instance_count:     int — number of real (non-padded) instances.
        supply:             (116, 3) float32.
        globals_vec:        (14,) float32.

    Returns:
        Raw value logit (scalar float).
    """
    embed_w    = tensors_dict["unit_embedding.weight"]        # (116, 32)
    prop_table = tensors_dict["property_table"]               # (116, 13)
    ie_w1 = tensors_dict["instance_encoder.0.weight"]         # (128, 55)
    ie_b1 = tensors_dict["instance_encoder.0.bias"]           # (128,)
    ie_w2 = tensors_dict["instance_encoder.2.weight"]         # (128, 128)
    ie_b2 = tensors_dict["instance_encoder.2.bias"]           # (128,)
    se_w1 = tensors_dict["supply_encoder.0.weight"]           # (32, 3)
    se_b1 = tensors_dict["supply_encoder.0.bias"]             # (32,)
    se_w2 = tensors_dict["supply_encoder.2.weight"]           # (32, 32)
    se_b2 = tensors_dict["supply_encoder.2.bias"]             # (32,)
    vh_w1 = tensors_dict["value_head.0.weight"]               # (256, 302)
    vh_b1 = tensors_dict["value_head.0.bias"]                 # (256,)
    vh_w2 = tensors_dict["value_head.3.weight"]               # (256, 256)
    vh_b2 = tensors_dict["value_head.3.bias"]                 # (256,)
    vh_w3 = tensors_dict["value_head.6.weight"]               # (1, 256)
    vh_b3 = tensors_dict["value_head.6.bias"]                 # (1,)

    MAX_INST = instance_features.shape[0]
    mask = np.arange(MAX_INST) < instance_count               # (MAX_INST,) bool

    # Token: [embedding | properties | instance_state]
    embeddings = embed_w[instance_unit_ids]                   # (MAX_INST, 32)
    properties = prop_table[instance_unit_ids]                # (MAX_INST, 13)
    tokens = np.concatenate([embeddings, properties, instance_features], axis=-1)  # (MAX_INST, 55)

    # Instance encoder
    h1      = np.maximum(0.0, tokens @ ie_w1.T + ie_b1)      # (MAX_INST, 128)
    encoded = np.maximum(0.0, h1     @ ie_w2.T + ie_b2)      # (MAX_INST, 128)

    # Mask out padding
    encoded = encoded * mask[:, np.newaxis]                   # (MAX_INST, 128)

    # Sum-pool by owner (feature 0: 0.0 = P0, 1.0 = P1)
    owner  = instance_features[:, 0]                          # (MAX_INST,)
    p0_mask = (mask & (owner < 0.5))[:, np.newaxis]
    p1_mask = (mask & (owner >= 0.5))[:, np.newaxis]
    p0_pool = (encoded * p0_mask).sum(axis=0)                 # (128,)
    p1_pool = (encoded * p1_mask).sum(axis=0)                 # (128,)

    # Supply encoder (per-unit, then sum)
    s_h1       = np.maximum(0.0, supply @ se_w1.T + se_b1)   # (116, 32)
    s_enc      = np.maximum(0.0, s_h1   @ se_w2.T + se_b2)   # (116, 32)
    supply_pool = s_enc.sum(axis=0)                           # (32,)

    # Value head
    combined = np.concatenate([p0_pool, p1_pool, supply_pool, globals_vec])  # (302,)
    vh1          = np.maximum(0.0, combined @ vh_w1.T + vh_b1)  # (256,)
    vh2          = np.maximum(0.0, vh1      @ vh_w2.T + vh_b2)  # (256,)
    value_logit  = (vh2 @ vh_w3.T + vh_b3)[0]                   # scalar

    return float(value_logit)


def load_binary(path: str) -> tuple:
    """Load a DSN2 binary file.

    Returns: (header_dict, {name: np.ndarray})
    """
    tensors = {}
    with open(path, "rb") as f:
        raw = f.read(36)
        fields = struct.unpack("<9I", raw)
        keys = ["magic", "version", "num_units", "d_embed", "num_properties",
                "encoder_hidden", "supply_hidden", "value_hidden", "num_tensors"]
        hdr = dict(zip(keys, fields))

        for _ in range(hdr["num_tensors"]):
            name, arr = read_tensor(f)
            tensors[name] = arr

    return hdr, tensors


def verify_export(output_path: str, model: PrismataDeepSets,
                  tol: float = 1e-4) -> bool:
    """Verify the exported binary by running a numpy forward pass and comparing
    to PyTorch output.

    Returns True if all tests pass, False otherwise.
    """
    print("\n--- Round-trip verification ---")
    hdr, tensors = load_binary(output_path)

    print(f"  Header: num_units={hdr['num_units']}, d_embed={hdr['d_embed']}, "
          f"num_properties={hdr['num_properties']}, encoder_hidden={hdr['encoder_hidden']}, "
          f"supply_hidden={hdr['supply_hidden']}, value_hidden={hdr['value_hidden']}, "
          f"num_tensors={hdr['num_tensors']}")
    print(f"  Loaded {len(tensors)} tensors")

    model.eval()

    def run_pytorch(inst_feats, inst_ids, inst_count, supply, globals_vec):
        with torch.no_grad():
            feats_t  = torch.from_numpy(inst_feats).unsqueeze(0).float()
            ids_t    = torch.from_numpy(inst_ids).unsqueeze(0)
            counts_t = torch.tensor([inst_count], dtype=torch.long)
            supply_t = torch.from_numpy(supply).unsqueeze(0).float()
            globs_t  = torch.from_numpy(globals_vec).unsqueeze(0).float()
            return model(feats_t, ids_t, counts_t, supply_t, globs_t)[0, 0].item()

    max_instances = 200
    num_units     = hdr["num_units"]

    test_cases = []

    # Case 1: all zeros
    test_cases.append(("all-zeros", (
        np.zeros((max_instances, 10), dtype=np.float32),
        np.zeros(max_instances, dtype=np.int64),
        0,
        np.zeros((num_units, 3), dtype=np.float32),
        np.zeros(14, dtype=np.float32),
    )))

    # Case 2: random non-zero
    rng = np.random.RandomState(7)
    inst_feats = rng.randn(max_instances, 10).astype(np.float32)
    inst_feats[:, 0] = (rng.rand(max_instances) > 0.5).astype(np.float32)
    test_cases.append(("random", (
        inst_feats,
        rng.randint(0, num_units, size=max_instances).astype(np.int64),
        50,
        rng.rand(num_units, 3).astype(np.float32),
        rng.rand(14).astype(np.float32),
    )))

    all_passed = True
    max_diff_seen = 0.0

    for label, (inst_feats, inst_ids, inst_count, supply, globs) in test_cases:
        np_val = numpy_forward(tensors, inst_feats, inst_ids, inst_count, supply, globs)
        pt_val = run_pytorch(inst_feats, inst_ids, inst_count, supply, globs)
        diff = abs(np_val - pt_val)
        max_diff_seen = max(max_diff_seen, diff)
        status = "OK" if diff < tol else "FAIL"
        print(f"  {label:12s}: numpy={np_val:.6f}, pytorch={pt_val:.6f}, "
              f"diff={diff:.2e} [{status}]")
        if diff >= tol:
            all_passed = False

    if all_passed:
        print(f"  Verification PASSED (max diff = {max_diff_seen:.2e})")
    else:
        print(f"  Verification FAILED (max diff = {max_diff_seen:.2e})")

    return all_passed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Export PrismataDeepSets weights to DSN2 binary format")
    parser.add_argument("model_path",
                        help="Path to PyTorch checkpoint (.pt) or 'random' for a fresh model")
    parser.add_argument("output_path",
                        help="Path to write the binary weights file")
    parser.add_argument("--property-table", default=None,
                        help="Path to property_table.json (loads into model before export)")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.model_path == "random":
        print("Creating randomly initialized PrismataDeepSets model")
        model = PrismataDeepSets()
    else:
        print(f"Loading model from {args.model_path}")
        checkpoint = torch.load(args.model_path, map_location="cpu", weights_only=True)
        cfg = checkpoint.get("model_config", {})
        model = PrismataDeepSets(**cfg)
        model.load_state_dict(checkpoint["model_state_dict"])

    model.eval()

    if args.property_table:
        print(f"Loading property table from {args.property_table}")
        model.load_property_table(args.property_table)

    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Parameters: {total_params:,}")

    print(f"\nWriting DSN2 binary to {args.output_path}")
    export_model(model, args.output_path, verbose=True)

    verify_export(args.output_path, model)

    print("\nDone!")


if __name__ == "__main__":
    main()
