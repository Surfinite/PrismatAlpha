"""
Export PrismataNet weights to a binary format for C++ inference.

See docs/WEIGHT_FORMAT.md for the full format specification.

Binary format summary:
  Header (32 bytes): magic, version, state_dim, num_units, hidden_dim, num_layers,
                     num_tensors, num_unit_names
  Tensors: named tensors in C++ load order (input_proj, trunk blocks, policy, value)
  Unit index: unit display name -> index mapping

Includes round-trip verification: loads exported weights back in Python, runs
forward pass on fixed inputs, asserts max absolute difference < 1e-5 vs the
original PyTorch model.

Usage:
  python export_weights.py [model_path] [output_path] [unit_index_path]
"""

import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, "C:/libraries/torch_pkg")
import torch

from train import PrismataNet


def write_tensor(f, name, tensor):
    """Write a single tensor to the binary file."""
    data = tensor.detach().cpu().float().contiguous().numpy()
    name_bytes = name.encode("utf-8") + b"\x00"

    f.write(struct.pack("<I", len(name_bytes)))
    f.write(name_bytes)
    f.write(struct.pack("<I", len(data.shape)))
    for dim in data.shape:
        f.write(struct.pack("<I", dim))
    f.write(data.tobytes())


def read_tensor_from_binary(f):
    """Read a single tensor from the binary file. Returns (name, data, shape)."""
    name_len = struct.unpack("<I", f.read(4))[0]
    name = f.read(name_len).decode("utf-8").rstrip("\x00")
    num_dims = struct.unpack("<I", f.read(4))[0]
    shape = []
    for _ in range(num_dims):
        shape.append(struct.unpack("<I", f.read(4))[0])
    total = 1
    for s in shape:
        total *= s
    data = np.frombuffer(f.read(total * 4), dtype=np.float32).copy()
    return name, data.reshape(shape) if shape else data, shape


def python_forward(weights, state_dim, hidden_dim, num_layers, num_units, features):
    """Pure-numpy forward pass mimicking C++ NeuralNet::evaluate.

    This validates that the exported weights produce the same output as C++ would.
    """
    def linear(w, b, x):
        return x @ w.T + b

    def layer_norm(gamma, beta, x, eps=1e-5):
        mean = x.mean()
        var = ((x - mean) ** 2).mean()
        return gamma * (x - mean) / np.sqrt(var + eps) + beta

    def relu(x):
        return np.maximum(x, 0)

    # Input projection
    h = relu(linear(weights["input_proj.weight"], weights["input_proj.bias"], features))

    # Trunk blocks
    for i in range(num_layers):
        prefix = f"trunk.{i}"
        tmp = linear(weights[f"{prefix}.linear1.weight"], weights[f"{prefix}.linear1.bias"], h)
        tmp = layer_norm(weights[f"{prefix}.norm1.weight"], weights[f"{prefix}.norm1.bias"], tmp)
        tmp = relu(tmp)
        tmp = linear(weights[f"{prefix}.linear2.weight"], weights[f"{prefix}.linear2.bias"], tmp)
        tmp = layer_norm(weights[f"{prefix}.norm2.weight"], weights[f"{prefix}.norm2.bias"], tmp)
        h = h + relu(tmp)

    # Policy head (skip if value-only model)
    if "policy.linear1.weight" in weights:
        ph = relu(linear(weights["policy.linear1.weight"], weights["policy.linear1.bias"], h))
        policy = linear(weights["policy.linear2.weight"], weights["policy.linear2.bias"], ph)
    else:
        policy = np.zeros(num_units, dtype=np.float32)

    # Value head (tanh applied here, matching C++)
    vh = relu(linear(weights["value.linear1.weight"], weights["value.linear1.bias"], h))
    raw_value = linear(weights["value.linear2.weight"], weights["value.linear2.bias"], vh)
    value = np.tanh(raw_value.item())

    return policy, value


def verify_export(output_path, model, state_dim, hidden_dim, num_layers, num_units):
    """Load exported binary weights, run forward pass, compare to PyTorch model."""
    print("\n--- Round-trip verification ---")

    # Load binary weights
    weights = {}
    with open(output_path, "rb") as f:
        header = struct.unpack("<8I", f.read(32))
        magic, version, sd, nu, hd, nl, nt, nn_ = header
        assert magic == 0x504E4554, f"Bad magic: {magic:#x}"
        assert sd == state_dim, f"state_dim mismatch: {sd} vs {state_dim}"
        assert nu == num_units, f"num_units mismatch: {nu} vs {num_units}"

        print(f"  Header: state_dim={sd}, num_units={nu}, hidden={hd}, "
              f"layers={nl}, tensors={nt}, names={nn_}")

        for _ in range(nt):
            name, data, shape = read_tensor_from_binary(f)
            weights[name] = data

        # Read unit index
        unit_names = {}
        for _ in range(nn_):
            idx = struct.unpack("<I", f.read(4))[0]
            name_len = struct.unpack("<I", f.read(4))[0]
            name = f.read(name_len).decode("utf-8").rstrip("\x00")
            unit_names[idx] = name

    print(f"  Loaded {len(weights)} tensors, {len(unit_names)} unit names")

    # Test inputs: all-zeros and a hand-crafted non-zero vector
    test_inputs = []

    # Test 1: all zeros
    test_inputs.append(("all-zeros", np.zeros(state_dim, dtype=np.float32)))

    # Test 2: non-zero realistic-ish input
    nz = np.zeros(state_dim, dtype=np.float32)
    # Set some unit features as if player has 6 drones ready
    nz[0] = 6.0  # Unit 0, player 0, ready
    nz[11] = 2.0  # Unit 1, player 0, ready
    nz[44] = 3.0  # Unit 4, player 0, ready
    # Set some global features at the end
    nz[-14] = 5.0  # p0 gold
    nz[-2] = 0.1   # turn/50
    nz[-1] = 0.0   # active player
    test_inputs.append(("non-zero", nz))

    max_diff = 0.0
    all_passed = True

    for name, inp in test_inputs:
        # Python numpy forward pass (mimics C++)
        np_policy, np_value = python_forward(
            weights, state_dim, hidden_dim, num_layers, num_units, inp)

        # PyTorch forward pass
        with torch.no_grad():
            pt_inp = torch.from_numpy(inp).unsqueeze(0)
            pt_policy, pt_value_logit = model(pt_inp)
            pt_value = torch.tanh(pt_value_logit).item()

        # Compare
        value_diff = abs(np_value - pt_value)
        if pt_policy is not None:
            policy_diff = np.abs(np_policy.flatten() - pt_policy[0].numpy()).max()
        else:
            policy_diff = 0.0  # value-only model, no policy to compare
        max_diff = max(max_diff, policy_diff, value_diff)

        status = "OK" if max(policy_diff, value_diff) < 1e-5 else "FAIL"
        print(f"  {name}: value_diff={value_diff:.2e}, policy_diff={policy_diff:.2e} [{status}]")

        if max(policy_diff, value_diff) >= 1e-5:
            all_passed = False

    if all_passed:
        print(f"  Verification PASSED (max diff = {max_diff:.2e})")
    else:
        print(f"  Verification FAILED (max diff = {max_diff:.2e})")
        sys.exit(1)


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else "c:/libraries/PrismataAI/training/models/best_model.pt"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "c:/libraries/PrismataAI/bin/asset/config/neural_weights.bin"
    unit_index_path = sys.argv[3] if len(sys.argv) > 3 else "c:/libraries/PrismataAI/training/data/unit_index.json"

    # Load checkpoint
    print(f"Loading model from {model_path}")
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)

    state_dim = checkpoint["state_dim"]
    num_units = checkpoint["num_units"]
    hidden_dim = checkpoint.get("hidden_dim", 512)
    num_layers = checkpoint.get("num_layers", 4)
    value_only = checkpoint.get("value_only", False)
    dropout = checkpoint.get("dropout", 0.1)

    # unit_index may be in checkpoint (best_model) or loaded from file
    if "unit_index" in checkpoint:
        unit_index = checkpoint["unit_index"]
    else:
        with open(unit_index_path) as uf:
            data = json.load(uf)
        # Support both formats: {"units": {...}} (new) and {"name": idx, ...} (old)
        unit_index = data["units"] if "units" in data and "version" in data else data
        num_units = len(unit_index)

    # Reconstruct model to get proper parameter names
    model = PrismataNet(state_dim, num_units, hidden_dim=hidden_dim,
                        num_layers=num_layers, dropout=dropout,
                        value_only=value_only)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    print(f"  State dim: {state_dim}")
    print(f"  Num units: {num_units}")
    print(f"  Hidden dim: {hidden_dim}")
    print(f"  Num layers: {num_layers}")
    print(f"  Value only: {value_only}")
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Collect tensors in the order C++ expects
    tensors = []

    # Input projection
    tensors.append(("input_proj.weight", model.input_proj.weight))
    tensors.append(("input_proj.bias", model.input_proj.bias))

    # Trunk residual blocks
    # Sequential: [0]=Linear, [1]=LayerNorm, [2]=ReLU, [3]=Dropout, [4]=Linear, [5]=LayerNorm
    for i, block in enumerate(model.trunk_layers):
        tensors.append((f"trunk.{i}.linear1.weight", block[0].weight))
        tensors.append((f"trunk.{i}.linear1.bias", block[0].bias))
        tensors.append((f"trunk.{i}.norm1.weight", block[1].weight))
        tensors.append((f"trunk.{i}.norm1.bias", block[1].bias))
        tensors.append((f"trunk.{i}.linear2.weight", block[4].weight))
        tensors.append((f"trunk.{i}.linear2.bias", block[4].bias))
        tensors.append((f"trunk.{i}.norm2.weight", block[5].weight))
        tensors.append((f"trunk.{i}.norm2.bias", block[5].bias))

    # Policy head: [0]=Linear, [1]=ReLU, [2]=Linear
    # Always export policy tensors — C++ loader expects all 26 tensors.
    # For value-only models, export zero-initialized policy weights.
    if not value_only:
        tensors.append(("policy.linear1.weight", model.policy_head[0].weight))
        tensors.append(("policy.linear1.bias", model.policy_head[0].bias))
        tensors.append(("policy.linear2.weight", model.policy_head[2].weight))
        tensors.append(("policy.linear2.bias", model.policy_head[2].bias))
    else:
        print("  (Value-only model: exporting zero-initialized policy head)")
        tensors.append(("policy.linear1.weight", torch.zeros(hidden_dim // 2, hidden_dim)))
        tensors.append(("policy.linear1.bias", torch.zeros(hidden_dim // 2)))
        tensors.append(("policy.linear2.weight", torch.zeros(num_units, hidden_dim // 2)))
        tensors.append(("policy.linear2.bias", torch.zeros(num_units)))

    # Value head: [0]=Linear, [1]=ReLU, [2]=Linear (tanh applied in C++ at inference)
    tensors.append(("value.linear1.weight", model.value_head[0].weight))
    tensors.append(("value.linear1.bias", model.value_head[0].bias))
    tensors.append(("value.linear2.weight", model.value_head[2].weight))
    tensors.append(("value.linear2.bias", model.value_head[2].bias))

    # Build sorted unit names (index -> name)
    idx_to_name = {v: k for k, v in unit_index.items()}

    print(f"\nWriting {len(tensors)} tensors to {output_path}")

    with open(output_path, "wb") as f:
        # Header
        f.write(struct.pack("<I", 0x504E4554))  # magic "PNET"
        f.write(struct.pack("<I", 1))            # version
        f.write(struct.pack("<I", state_dim))
        f.write(struct.pack("<I", num_units))
        f.write(struct.pack("<I", hidden_dim))
        f.write(struct.pack("<I", num_layers))
        f.write(struct.pack("<I", len(tensors)))
        f.write(struct.pack("<I", len(idx_to_name)))

        # Tensors
        for name, tensor in tensors:
            write_tensor(f, name, tensor)
            print(f"  {name:40s} {list(tensor.shape)}")

        # Unit index
        for idx in range(len(idx_to_name)):
            name = idx_to_name[idx]
            name_bytes = name.encode("utf-8") + b"\x00"
            f.write(struct.pack("<I", idx))
            f.write(struct.pack("<I", len(name_bytes)))
            f.write(name_bytes)

    file_size = os.path.getsize(output_path)
    print(f"\nDone! File size: {file_size / 1024 / 1024:.1f} MB")

    # Round-trip verification
    verify_export(output_path, model, state_dim, hidden_dim, num_layers, num_units)


if __name__ == "__main__":
    main()
