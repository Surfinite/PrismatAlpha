"""
Tests for export_weights_v2.py — PrismataDeepSets weight exporter (DSN2 format).

Run: cd training && python -m pytest tests/test_export_v2.py -v
"""

import io
import os
import struct
import sys
import tempfile

import numpy as np
import pytest
import torch

# Add training/ to path so we can import local modules
TRAINING_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TRAINING_DIR)
# Also ensure PyTorch is findable
sys.path.insert(0, "C:/libraries/torch_pkg")

from model_deepsets import PrismataDeepSets
import export_weights_v2 as exv2


# ---------------------------------------------------------------------------
# Constants (must match export_weights_v2.py)
# ---------------------------------------------------------------------------

MAGIC_DSN2 = 0x44534E32  # "DSN2"
HEADER_FIELDS = 9  # number of uint32s in header
HEADER_BYTES = HEADER_FIELDS * 4  # 36 bytes

# Expected tensor names in order
EXPECTED_TENSOR_NAMES = [
    "unit_embedding.weight",
    "instance_encoder.0.weight",
    "instance_encoder.0.bias",
    "instance_encoder.2.weight",
    "instance_encoder.2.bias",
    "supply_encoder.0.weight",
    "supply_encoder.0.bias",
    "supply_encoder.2.weight",
    "supply_encoder.2.bias",
    "value_head.0.weight",
    "value_head.0.bias",
    "value_head.3.weight",
    "value_head.3.bias",
    "value_head.6.weight",
    "value_head.6.bias",
    "property_table",
]

# Expected tensor shapes for default model config
EXPECTED_SHAPES = {
    "unit_embedding.weight":      (116, 32),
    "instance_encoder.0.weight":  (128, 55),
    "instance_encoder.0.bias":    (128,),
    "instance_encoder.2.weight":  (128, 128),
    "instance_encoder.2.bias":    (128,),
    "supply_encoder.0.weight":    (32, 3),
    "supply_encoder.0.bias":      (32,),
    "supply_encoder.2.weight":    (32, 32),
    "supply_encoder.2.bias":      (32,),
    "value_head.0.weight":        (256, 302),
    "value_head.0.bias":          (256,),
    "value_head.3.weight":        (256, 256),
    "value_head.3.bias":          (256,),
    "value_head.6.weight":        (1, 256),
    "value_head.6.bias":          (1,),
    "property_table":             (116, 13),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_random_model():
    """Create a freshly initialized PrismataDeepSets model (random weights)."""
    model = PrismataDeepSets()
    model.eval()
    return model


def read_header(f):
    """Read and unpack the 9-field DSN2 header from an open binary file."""
    raw = f.read(HEADER_BYTES)
    assert len(raw) == HEADER_BYTES, f"Header too short: {len(raw)} bytes"
    fields = struct.unpack("<9I", raw)
    keys = ["magic", "version", "num_units", "d_embed", "num_properties",
            "encoder_hidden", "supply_hidden", "value_hidden", "num_tensors"]
    return dict(zip(keys, fields))


def read_tensor(f):
    """Read a single tensor record from an open binary file.
    Returns (name, ndarray).
    """
    name_len = struct.unpack("<I", f.read(4))[0]
    name = f.read(name_len).decode("utf-8").rstrip("\x00")
    ndims = struct.unpack("<I", f.read(4))[0]
    shape = tuple(struct.unpack("<I", f.read(4))[0] for _ in range(ndims))
    total = int(np.prod(shape)) if shape else 1
    data = np.frombuffer(f.read(total * 4), dtype=np.float32).copy()
    return name, data.reshape(shape) if shape else data


def load_all_tensors(path):
    """Open DSN2 binary file and return (header_dict, {name: ndarray})."""
    tensors = {}
    with open(path, "rb") as f:
        hdr = read_header(f)
        for _ in range(hdr["num_tensors"]):
            name, arr = read_tensor(f)
            tensors[name] = arr
    return hdr, tensors


# ---------------------------------------------------------------------------
# Numpy forward pass (mirrors PrismataDeepSets.forward exactly)
# ---------------------------------------------------------------------------

def numpy_forward(tensors, instance_features, instance_unit_ids, instance_count,
                  supply, globals_vec):
    """Pure numpy implementation of PrismataDeepSets.forward for a single sample.

    Args:
        tensors:            dict of {name: ndarray} from load_all_tensors
        instance_features:  (MAX_INST, 10) float32
        instance_unit_ids:  (MAX_INST,) int
        instance_count:     int — number of real (non-padded) instances
        supply:             (116, 3) float32
        globals_vec:        (14,) float32

    Returns:
        value_logit: scalar float32
    """
    embed_w     = tensors["unit_embedding.weight"]        # (116, 32)
    prop_table  = tensors["property_table"]               # (116, 13)

    ie_w1 = tensors["instance_encoder.0.weight"]          # (128, 55)
    ie_b1 = tensors["instance_encoder.0.bias"]            # (128,)
    ie_w2 = tensors["instance_encoder.2.weight"]          # (128, 128)
    ie_b2 = tensors["instance_encoder.2.bias"]            # (128,)

    se_w1 = tensors["supply_encoder.0.weight"]            # (32, 3)
    se_b1 = tensors["supply_encoder.0.bias"]              # (32,)
    se_w2 = tensors["supply_encoder.2.weight"]            # (32, 32)
    se_b2 = tensors["supply_encoder.2.bias"]              # (32,)

    vh_w1 = tensors["value_head.0.weight"]                # (256, 302)
    vh_b1 = tensors["value_head.0.bias"]                  # (256,)
    vh_w2 = tensors["value_head.3.weight"]                # (256, 256)
    vh_b2 = tensors["value_head.3.bias"]                  # (256,)
    vh_w3 = tensors["value_head.6.weight"]                # (1, 256)
    vh_b3 = tensors["value_head.6.bias"]                  # (1,)

    MAX_INST = instance_features.shape[0]
    mask = np.arange(MAX_INST) < instance_count           # (MAX_INST,) bool

    # Token construction: [embedding | static_properties | instance_state]
    embeddings = embed_w[instance_unit_ids]               # (MAX_INST, 32)
    properties = prop_table[instance_unit_ids]            # (MAX_INST, 13)
    tokens = np.concatenate([embeddings, properties, instance_features], axis=-1)  # (MAX_INST, 55)

    # Instance encoder: two Linear+ReLU layers
    h1 = np.maximum(0.0, tokens @ ie_w1.T + ie_b1)       # (MAX_INST, 128)
    encoded = np.maximum(0.0, h1 @ ie_w2.T + ie_b2)      # (MAX_INST, 128)

    # Zero out padded positions
    encoded = encoded * mask[:, np.newaxis]               # (MAX_INST, 128)

    # Sum-pool by owner (feature index 0: 0.0 = P0, 1.0 = P1)
    owner = instance_features[:, 0]                       # (MAX_INST,)
    p0_mask = (mask & (owner < 0.5))[:, np.newaxis]      # (MAX_INST, 1)
    p1_mask = (mask & (owner >= 0.5))[:, np.newaxis]     # (MAX_INST, 1)

    p0_pool = (encoded * p0_mask).sum(axis=0)             # (128,)
    p1_pool = (encoded * p1_mask).sum(axis=0)             # (128,)

    # Supply encoder (flat over all 116 unit types, then sum)
    supply_h1 = np.maximum(0.0, supply @ se_w1.T + se_b1)   # (116, 32)
    supply_enc = np.maximum(0.0, supply_h1 @ se_w2.T + se_b2)  # (116, 32)
    supply_pool = supply_enc.sum(axis=0)                  # (32,)

    # Value head: 3-layer MLP (ReLU between, no activation on final)
    combined = np.concatenate([p0_pool, p1_pool, supply_pool, globals_vec])  # (302,)
    vh1 = np.maximum(0.0, combined @ vh_w1.T + vh_b1)    # (256,)
    vh2 = np.maximum(0.0, vh1 @ vh_w2.T + vh_b2)         # (256,)
    value_logit = (vh2 @ vh_w3.T + vh_b3)[0]             # scalar

    return np.float32(value_logit)


def pytorch_forward_single(model, instance_features, instance_unit_ids, instance_count,
                            supply, globals_vec):
    """Run PrismataDeepSets.forward on a single sample (adds batch dim).

    Returns raw value_logit scalar (float).
    """
    model.eval()
    with torch.no_grad():
        feats_t = torch.from_numpy(instance_features).unsqueeze(0)  # (1, MAX_INST, 10)
        ids_t   = torch.from_numpy(instance_unit_ids).unsqueeze(0)  # (1, MAX_INST)
        counts_t = torch.tensor([instance_count], dtype=torch.long)
        supply_t = torch.from_numpy(supply).unsqueeze(0)            # (1, 116, 3)
        globs_t  = torch.from_numpy(globals_vec).unsqueeze(0)       # (1, 14)

        out = model(feats_t, ids_t, counts_t, supply_t, globs_t)    # (1, 1)
        return out[0, 0].item()


def make_test_inputs(max_instances=200, num_units=116):
    """Generate a reproducible test input (single sample, no batch dim)."""
    rng = np.random.RandomState(42)

    instance_count = 50
    instance_features = rng.randn(max_instances, 10).astype(np.float32)
    # Owner feature is 0 or 1
    instance_features[:, 0] = (rng.rand(max_instances) > 0.5).astype(np.float32)

    instance_unit_ids = rng.randint(0, num_units, size=max_instances).astype(np.int64)
    supply = rng.rand(num_units, 3).astype(np.float32)
    globals_vec = rng.rand(14).astype(np.float32)

    return instance_features, instance_unit_ids, instance_count, supply, globals_vec


# ---------------------------------------------------------------------------
# Test 1: Binary file creation and header validation
# ---------------------------------------------------------------------------

class TestFileCreation:
    def test_binary_file_is_created(self, tmp_path):
        """export_model() creates a binary file at the specified path."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")

        exv2.export_model(model, out_path)

        assert os.path.exists(out_path), "Binary file was not created"
        assert os.path.getsize(out_path) > 0, "Binary file is empty"

    def test_header_magic(self, tmp_path):
        """Binary file starts with magic number 0x44534E32 ('DSN2')."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        with open(out_path, "rb") as f:
            hdr = read_header(f)

        assert hdr["magic"] == MAGIC_DSN2, \
            f"Expected magic 0x{MAGIC_DSN2:08X}, got 0x{hdr['magic']:08X}"

    def test_header_version(self, tmp_path):
        """Header version field is 2."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        with open(out_path, "rb") as f:
            hdr = read_header(f)

        assert hdr["version"] == 2, f"Expected version=2, got {hdr['version']}"

    def test_header_dimensions(self, tmp_path):
        """Header fields correctly reflect default model dimensions."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        with open(out_path, "rb") as f:
            hdr = read_header(f)

        assert hdr["num_units"]      == 116,  f"num_units: {hdr['num_units']}"
        assert hdr["d_embed"]        == 32,   f"d_embed: {hdr['d_embed']}"
        assert hdr["num_properties"] == 13,   f"num_properties: {hdr['num_properties']}"
        assert hdr["encoder_hidden"] == 128,  f"encoder_hidden: {hdr['encoder_hidden']}"
        assert hdr["supply_hidden"]  == 32,   f"supply_hidden: {hdr['supply_hidden']}"
        assert hdr["value_hidden"]   == 256,  f"value_hidden: {hdr['value_hidden']}"

    def test_header_num_tensors(self, tmp_path):
        """Header num_tensors field equals 16 (15 weight tensors + property_table)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        with open(out_path, "rb") as f:
            hdr = read_header(f)

        assert hdr["num_tensors"] == 16, \
            f"Expected 16 tensors, got {hdr['num_tensors']}"


# ---------------------------------------------------------------------------
# Test 2: Round-trip verification
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_numpy_matches_pytorch_zeros(self, tmp_path):
        """Numpy forward on all-zeros input matches PyTorch to 4+ decimal places."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        max_instances = 200
        instance_features = np.zeros((max_instances, 10), dtype=np.float32)
        instance_unit_ids = np.zeros(max_instances, dtype=np.int64)
        instance_count = 0
        supply = np.zeros((116, 3), dtype=np.float32)
        globals_vec = np.zeros(14, dtype=np.float32)

        np_val = numpy_forward(tensors, instance_features, instance_unit_ids,
                               instance_count, supply, globals_vec)
        pt_val = pytorch_forward_single(model, instance_features, instance_unit_ids,
                                        instance_count, supply, globals_vec)

        diff = abs(float(np_val) - float(pt_val))
        assert diff < 1e-4, \
            f"All-zeros: numpy={np_val:.6f}, pytorch={pt_val:.6f}, diff={diff:.2e}"

    def test_numpy_matches_pytorch_random(self, tmp_path):
        """Numpy forward on random input matches PyTorch to 4+ decimal places."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        instance_features, instance_unit_ids, instance_count, supply, globals_vec = \
            make_test_inputs()

        np_val = numpy_forward(tensors, instance_features, instance_unit_ids,
                               instance_count, supply, globals_vec)
        pt_val = pytorch_forward_single(model, instance_features, instance_unit_ids,
                                        instance_count, supply, globals_vec)

        diff = abs(float(np_val) - float(pt_val))
        assert diff < 1e-4, \
            f"Random input: numpy={np_val:.6f}, pytorch={pt_val:.6f}, diff={diff:.2e}"

    def test_numpy_matches_pytorch_nonzero_supply(self, tmp_path):
        """Numpy forward on input with varied supply matches PyTorch to 4+ decimal places."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        rng = np.random.RandomState(123)
        max_instances = 200
        instance_count = 30
        instance_features = rng.randn(max_instances, 10).astype(np.float32)
        instance_features[:, 0] = (rng.rand(max_instances) > 0.5).astype(np.float32)
        instance_unit_ids = rng.randint(0, 116, size=max_instances).astype(np.int64)
        # Realistic supply: a few units in-set with small counts
        supply = np.zeros((116, 3), dtype=np.float32)
        for i in [0, 1, 5, 10, 20]:
            supply[i, 0] = rng.randint(0, 8)   # p0 supply
            supply[i, 1] = rng.randint(0, 8)   # p1 supply
            supply[i, 2] = 1.0                  # in card set
        globals_vec = rng.rand(14).astype(np.float32)

        np_val = numpy_forward(tensors, instance_features, instance_unit_ids,
                               instance_count, supply, globals_vec)
        pt_val = pytorch_forward_single(model, instance_features, instance_unit_ids,
                                        instance_count, supply, globals_vec)

        diff = abs(float(np_val) - float(pt_val))
        assert diff < 1e-4, \
            f"Supply input: numpy={np_val:.6f}, pytorch={pt_val:.6f}, diff={diff:.2e}"


# ---------------------------------------------------------------------------
# Test 3: All expected tensors are present with correct shapes
# ---------------------------------------------------------------------------

class TestTensorInventory:
    def test_all_tensors_present(self, tmp_path):
        """All 16 expected tensors are present in the binary file."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        for name in EXPECTED_TENSOR_NAMES:
            assert name in tensors, f"Missing tensor: {name}"

    def test_no_extra_tensors(self, tmp_path):
        """No extra (unexpected) tensors are present in the binary file."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        extra = set(tensors.keys()) - set(EXPECTED_TENSOR_NAMES)
        assert len(extra) == 0, f"Unexpected tensors: {extra}"

    def test_tensor_order(self, tmp_path):
        """Tensors appear in the correct fixed order in the binary file."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        actual_names = []
        with open(out_path, "rb") as f:
            hdr = read_header(f)
            for _ in range(hdr["num_tensors"]):
                name, _ = read_tensor(f)
                actual_names.append(name)

        assert actual_names == EXPECTED_TENSOR_NAMES, (
            f"Tensor order mismatch.\n"
            f"Expected: {EXPECTED_TENSOR_NAMES}\n"
            f"Got:      {actual_names}"
        )

    def test_tensor_shapes(self, tmp_path):
        """Each tensor has the expected shape."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)

        for name, expected_shape in EXPECTED_SHAPES.items():
            assert name in tensors, f"Missing tensor: {name}"
            actual_shape = tensors[name].shape
            assert actual_shape == expected_shape, (
                f"{name}: expected shape {expected_shape}, got {actual_shape}"
            )

    def test_unit_embedding_shape(self, tmp_path):
        """unit_embedding.weight is (116, 32)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        w = tensors["unit_embedding.weight"]
        assert w.shape == (116, 32), f"unit_embedding shape: {w.shape}"

    def test_instance_encoder_layer1_shapes(self, tmp_path):
        """instance_encoder linear1: weight (128, 55), bias (128,)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        assert tensors["instance_encoder.0.weight"].shape == (128, 55)
        assert tensors["instance_encoder.0.bias"].shape   == (128,)

    def test_instance_encoder_layer2_shapes(self, tmp_path):
        """instance_encoder linear2: weight (128, 128), bias (128,)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        assert tensors["instance_encoder.2.weight"].shape == (128, 128)
        assert tensors["instance_encoder.2.bias"].shape   == (128,)

    def test_supply_encoder_shapes(self, tmp_path):
        """supply_encoder: linear1 (32,3)/(32,), linear2 (32,32)/(32,)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        assert tensors["supply_encoder.0.weight"].shape == (32, 3)
        assert tensors["supply_encoder.0.bias"].shape   == (32,)
        assert tensors["supply_encoder.2.weight"].shape == (32, 32)
        assert tensors["supply_encoder.2.bias"].shape   == (32,)

    def test_value_head_shapes(self, tmp_path):
        """value_head layers: layer0 (256,302)/(256,), layer3 (256,256)/(256,), layer6 (1,256)/(1,)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        assert tensors["value_head.0.weight"].shape == (256, 302)
        assert tensors["value_head.0.bias"].shape   == (256,)
        assert tensors["value_head.3.weight"].shape == (256, 256)
        assert tensors["value_head.3.bias"].shape   == (256,)
        assert tensors["value_head.6.weight"].shape == (1, 256)
        assert tensors["value_head.6.bias"].shape   == (1,)

    def test_property_table_shape(self, tmp_path):
        """property_table buffer is (116, 13)."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        assert tensors["property_table"].shape == (116, 13), \
            f"property_table shape: {tensors['property_table'].shape}"

    def test_property_table_values_match_model(self, tmp_path):
        """Exported property_table matches the model's buffer values."""
        model = make_random_model()
        # Set a distinctive non-zero property table
        with torch.no_grad():
            model.property_table.fill_(0.0)
            model.property_table[5, 3] = 42.0
            model.property_table[10, 7] = -1.5

        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        pt = tensors["property_table"]

        assert abs(pt[5, 3] - 42.0) < 1e-6, f"property_table[5,3] = {pt[5,3]}, expected 42.0"
        assert abs(pt[10, 7] - (-1.5)) < 1e-6, f"property_table[10,7] = {pt[10,7]}, expected -1.5"

    def test_tensor_dtype_is_float32(self, tmp_path):
        """All tensor data is stored as float32."""
        model = make_random_model()
        out_path = str(tmp_path / "weights.bin")
        exv2.export_model(model, out_path)

        hdr, tensors = load_all_tensors(out_path)
        for name, arr in tensors.items():
            assert arr.dtype == np.float32, \
                f"{name}: expected float32, got {arr.dtype}"
