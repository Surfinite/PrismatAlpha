"""
Tests for vectorize_v2.py — DeepSets HDF5 format vectorizer.

Run: cd training && python -m pytest tests/test_vectorize_v2.py -v
"""

import json
import os
import sys
import tempfile

import h5py
import numpy as np
import pytest

# Add training/ to path so we can import vectorize_v2
TRAINING_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TRAINING_DIR)

import vectorize_v2 as v2


# ---------------------------------------------------------------------------
# Minimal valid record helpers
# ---------------------------------------------------------------------------

def make_instance(name, owner, **kwargs):
    """Create a minimal instance dict."""
    defaults = {
        "name": name,
        "owner": owner,
        "is_constructing": 0,
        "turns_until_ready": 0,
        "is_blocking": 0,
        "ability_used": 0,
        "current_hp": 1,
        "hp_fraction": 1.0,
        "is_frozen": 0,
        "lifespan_remaining": 0,
        "stamina_remaining": 0,
    }
    defaults.update(kwargs)
    return defaults


def make_record(instances, supply=None, **kwargs):
    """Create a minimal V2 JSONL record."""
    if supply is None:
        supply = {
            "Drone": [20, 20, 0],
            "Engineer": [20, 20, 0],
            "Wall": [20, 20, 1],
        }
    defaults = {
        "schema_version": "v2",
        "instances": instances,
        "supply": supply,
        "p0_resources": {"gold": 4, "green": 0, "blue": 0, "red": 0, "energy": 0},
        "p1_resources": {"gold": 4, "green": 0, "blue": 0, "red": 0, "energy": 0},
        "p0_attack": 0,
        "p1_attack": 0,
        "turn_number": 1,
        "active_player": 0,
        "card_set": ["Wall"],
        "ply_index": 5,
        "outcome_p0": 1,
        "total_plies": 40,
        "replay_code": "test123",
        "game_date": "2026-03-11",
        "rating_p0": 1800,
        "rating_p1": 1800,
    }
    defaults.update(kwargs)
    return defaults


def load_unit_index():
    """Load the canonical unit index."""
    index_path = os.path.join(TRAINING_DIR, "data", "unit_index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["units"]


# ---------------------------------------------------------------------------
# Test 1: Minimal state — instance count, token shape, owner field
# ---------------------------------------------------------------------------

class TestMinimalState:
    def test_instance_count(self):
        """vectorize_instances returns the correct number of instances."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0),
            make_instance("Drone", 0),
            make_instance("Engineer", 1),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        assert count == 3, f"Expected 3 instances, got {count}"

    def test_token_dim_is_10(self):
        """Each instance token is 10 floats (state features only)."""
        unit_index = load_unit_index()
        instances = [make_instance("Drone", 0)]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        assert inst_feats.shape == (200, 10), f"Expected (200, 10), got {inst_feats.shape}"
        assert inst_feats.dtype == np.float32

    def test_owner_field_correct(self):
        """Owner field is first feature and matches instance owner."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0),
            make_instance("Engineer", 1),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        # P0 units come first in ordering
        assert inst_feats[0, 0] == pytest.approx(0.0), f"P0 owner should be 0.0, got {inst_feats[0, 0]}"
        assert inst_feats[1, 0] == pytest.approx(1.0), f"P1 owner should be 1.0, got {inst_feats[1, 0]}"

    def test_padding_is_zero(self):
        """Slots beyond count are zero-padded."""
        unit_index = load_unit_index()
        instances = [make_instance("Drone", 0)]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        assert count == 1
        # Everything after index 0 should be zero
        assert np.all(inst_feats[1:] == 0.0), "Padded slots should be zero"

    def test_unit_ids_array_shape(self):
        """instance_unit_ids is uint8 with shape (MAX_INSTANCES,)."""
        unit_index = load_unit_index()
        instances = [make_instance("Drone", 0), make_instance("Engineer", 1)]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        assert inst_ids.shape == (200,), f"Expected (200,), got {inst_ids.shape}"
        assert inst_ids.dtype == np.uint8


# ---------------------------------------------------------------------------
# Test 2: Supply encoding
# ---------------------------------------------------------------------------

class TestSupplyEncoding:
    def test_supply_shape(self):
        """Supply array is (116, 3) float32."""
        unit_index = load_unit_index()
        supply = {
            "Drone": [15, 18, 0],
            "Wall": [10, 20, 1],
        }
        sup_arr = v2.vectorize_supply(supply, unit_index, num_units=116)
        assert sup_arr.shape == (116, 3), f"Expected (116, 3), got {sup_arr.shape}"
        assert sup_arr.dtype == np.float32

    def test_supply_values_drone(self):
        """Drone supply correctly encoded at its index."""
        unit_index = load_unit_index()
        supply = {"Drone": [15, 18, 0]}
        sup_arr = v2.vectorize_supply(supply, unit_index, num_units=116)
        drone_idx = unit_index["Drone"]
        assert sup_arr[drone_idx, 0] == pytest.approx(15.0)
        assert sup_arr[drone_idx, 1] == pytest.approx(18.0)
        assert sup_arr[drone_idx, 2] == pytest.approx(0.0)

    def test_supply_in_set_flag(self):
        """in_card_set flag (supply[2]) is correctly encoded."""
        unit_index = load_unit_index()
        supply = {"Wall": [10, 10, 1]}
        sup_arr = v2.vectorize_supply(supply, unit_index, num_units=116)
        wall_idx = unit_index["Wall"]
        assert sup_arr[wall_idx, 2] == pytest.approx(1.0)

    def test_supply_unknown_unit_silently_ignored(self):
        """Unknown unit in supply is silently dropped — no exception."""
        unit_index = load_unit_index()
        supply = {"Drone": [20, 20, 0], "TOTALLY_FAKE_UNIT_XYZ": [5, 5, 1]}
        # Should not raise
        sup_arr = v2.vectorize_supply(supply, unit_index, num_units=116)
        assert sup_arr.shape == (116, 3)


# ---------------------------------------------------------------------------
# Test 3: Global features
# ---------------------------------------------------------------------------

class TestGlobalFeatures:
    def test_global_shape(self):
        """Global feature vector is 14 floats."""
        caps = {"gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50}
        record = make_record([])
        gvec = v2.vectorize_globals(record, caps)
        assert gvec.shape == (14,), f"Expected (14,), got {gvec.shape}"
        assert gvec.dtype == np.float32

    def test_global_order(self):
        """Global features follow schema order: p0_gold,p0_blue,p0_red,p0_green,p0_energy,p0_attack,..."""
        caps = {"gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50}
        record = make_record(
            [],
            p0_resources={"gold": 10, "blue": 2, "red": 1, "green": 3, "energy": 5},
            p0_attack=8,
            p1_resources={"gold": 0, "blue": 0, "red": 0, "green": 0, "energy": 0},
            p1_attack=0,
            turn_number=25,
            active_player=1,
        )
        gvec = v2.vectorize_globals(record, caps)
        # p0_gold = 10/20 = 0.5
        assert gvec[0] == pytest.approx(10.0 / 20.0), f"p0_gold expected 0.5, got {gvec[0]}"
        # p0_blue = 2/5 = 0.4
        assert gvec[1] == pytest.approx(2.0 / 5.0), f"p0_blue expected 0.4, got {gvec[1]}"
        # p0_red = 1/5
        assert gvec[2] == pytest.approx(1.0 / 5.0)
        # p0_green = 3/15
        assert gvec[3] == pytest.approx(3.0 / 15.0)
        # p0_energy = 5/10
        assert gvec[4] == pytest.approx(5.0 / 10.0)
        # p0_attack = 8/25
        assert gvec[5] == pytest.approx(8.0 / 25.0)
        # p1 all zeros
        assert gvec[6] == pytest.approx(0.0)
        # turn_number = 25/50 = 0.5
        assert gvec[12] == pytest.approx(25.0 / 50.0)
        # active_player = 1.0
        assert gvec[13] == pytest.approx(1.0)

    def test_global_normalization_clamped(self):
        """Values exceeding cap are clamped to 1.0."""
        caps = {"gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50}
        record = make_record(
            [],
            p0_resources={"gold": 999, "blue": 0, "red": 0, "green": 0, "energy": 0},
            p0_attack=0,
        )
        gvec = v2.vectorize_globals(record, caps)
        assert gvec[0] == pytest.approx(1.0), "Over-cap gold should clamp to 1.0"


# ---------------------------------------------------------------------------
# Test 4: Unknown unit in instance list silently dropped
# ---------------------------------------------------------------------------

class TestUnknownUnit:
    def test_unknown_unit_dropped(self):
        """Unknown unit in instances is silently dropped."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0),
            make_instance("TOTALLY_FAKE_UNIT_XYZ_9999", 0),  # Unknown
            make_instance("Engineer", 1),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        # Only 2 known units
        assert count == 2, f"Expected 2 (unknown dropped), got {count}"

    def test_unknown_unit_no_exception(self):
        """vectorize_instances does not raise on unknown units."""
        unit_index = load_unit_index()
        instances = [make_instance("TOTALLY_FAKE_UNIT_XYZ_9999", 0)]
        # Should not raise
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        assert count == 0


# ---------------------------------------------------------------------------
# Test 5: lifespan -1 maps to 0
# ---------------------------------------------------------------------------

class TestLifespanMapping:
    def test_lifespan_minus_one_maps_to_zero(self):
        """lifespan_remaining = -1 (permanent units) maps to feature value 0."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0, lifespan_remaining=-1),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        # lifespan_remaining is feature index 9 (0-indexed)
        lifespan_idx = v2.INSTANCE_FEATURE_NAMES.index("lifespan_remaining")
        assert inst_feats[0, lifespan_idx] == pytest.approx(0.0), (
            f"lifespan -1 should map to 0.0, got {inst_feats[0, lifespan_idx]}"
        )

    def test_positive_lifespan_preserved(self):
        """Positive lifespan_remaining is stored as-is."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0, lifespan_remaining=3),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        lifespan_idx = v2.INSTANCE_FEATURE_NAMES.index("lifespan_remaining")
        assert inst_feats[0, lifespan_idx] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Test 6: Fragile unit HP calculation (health, not health-damage)
# ---------------------------------------------------------------------------

class TestFragileHP:
    def test_hp_fraction_is_used_directly(self):
        """hp_fraction from the instance is used directly as the feature value."""
        unit_index = load_unit_index()
        # hp_fraction=0.5 means unit is at 50% health
        instances = [
            make_instance("Wall", 0, current_hp=2, hp_fraction=0.5),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        hp_frac_idx = v2.INSTANCE_FEATURE_NAMES.index("hp_fraction")
        assert inst_feats[0, hp_frac_idx] == pytest.approx(0.5)

    def test_full_hp(self):
        """Full HP unit has hp_fraction=1.0."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Wall", 0, current_hp=4, hp_fraction=1.0),
        ]
        inst_feats, inst_ids, count = v2.vectorize_instances(instances, unit_index, max_instances=200)
        hp_frac_idx = v2.INSTANCE_FEATURE_NAMES.index("hp_fraction")
        assert inst_feats[0, hp_frac_idx] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 7: Symmetry — mirror(state) swaps owners and supply
# ---------------------------------------------------------------------------

class TestSymmetry:
    def test_mirror_swaps_owners(self):
        """mirror_record swaps instance owner values (0↔1)."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0),
            make_instance("Drone", 0),
            make_instance("Engineer", 1),
        ]
        record = make_record(instances)
        mirrored = v2.mirror_record(record)

        # Check that owners are swapped
        orig_owners = [inst["owner"] for inst in record["instances"]]
        mir_owners = [inst["owner"] for inst in mirrored["instances"]]
        assert orig_owners == [0, 0, 1], f"Orig owners: {orig_owners}"
        assert mir_owners == [1, 1, 0], f"Mirrored owners: {mir_owners}"

    def test_mirror_swaps_supply(self):
        """mirror_record swaps p0_supply and p1_supply in supply dict."""
        instances = [make_instance("Drone", 0)]
        supply = {
            "Drone": [15, 10, 0],  # p0_supply=15, p1_supply=10
            "Wall": [20, 5, 1],    # p0_supply=20, p1_supply=5
        }
        record = make_record(instances, supply=supply)
        mirrored = v2.mirror_record(record)

        # Drone supply should be swapped
        assert mirrored["supply"]["Drone"][0] == 10, "p0_supply should become p1_supply"
        assert mirrored["supply"]["Drone"][1] == 15, "p1_supply should become p0_supply"
        assert mirrored["supply"]["Drone"][2] == 0, "in_set unchanged"

        # Wall supply should be swapped
        assert mirrored["supply"]["Wall"][0] == 5
        assert mirrored["supply"]["Wall"][1] == 20
        assert mirrored["supply"]["Wall"][2] == 1

    def test_mirror_swaps_resources(self):
        """mirror_record swaps p0_ and p1_ resources and attack."""
        instances = [make_instance("Drone", 0)]
        record = make_record(
            instances,
            p0_resources={"gold": 8, "green": 2, "blue": 1, "red": 0, "energy": 3},
            p1_resources={"gold": 4, "green": 0, "blue": 2, "red": 1, "energy": 0},
            p0_attack=5,
            p1_attack=2,
            active_player=0,
            outcome_p0=1,
        )
        mirrored = v2.mirror_record(record)

        # Resources swapped
        assert mirrored["p0_resources"]["gold"] == 4
        assert mirrored["p1_resources"]["gold"] == 8
        assert mirrored["p0_attack"] == 2
        assert mirrored["p1_attack"] == 5
        # Active player flipped
        assert mirrored["active_player"] == 1
        # Outcome flipped (mirror perspective)
        assert mirrored["outcome_p0"] == 0

    def test_mirror_double_inversion(self):
        """Mirroring twice returns to original state."""
        unit_index = load_unit_index()
        instances = [
            make_instance("Drone", 0),
            make_instance("Engineer", 1),
        ]
        supply = {"Drone": [15, 10, 0], "Wall": [20, 5, 1]}
        record = make_record(
            instances,
            supply=supply,
            p0_resources={"gold": 8, "green": 2, "blue": 1, "red": 0, "energy": 3},
            p1_resources={"gold": 4, "green": 0, "blue": 2, "red": 1, "energy": 0},
            p0_attack=5, p1_attack=2, active_player=0, outcome_p0=1,
        )
        double_mirrored = v2.mirror_record(v2.mirror_record(record))

        # Compare owners
        assert [i["owner"] for i in double_mirrored["instances"]] == [0, 1]
        # Compare supply
        assert double_mirrored["supply"]["Drone"] == [15, 10, 0]
        # Compare resources
        assert double_mirrored["p0_resources"]["gold"] == 8
        assert double_mirrored["p1_resources"]["gold"] == 4
        # Compare attack
        assert double_mirrored["p0_attack"] == 5
        assert double_mirrored["p1_attack"] == 2
        # Compare active player and outcome
        assert double_mirrored["active_player"] == 0
        assert double_mirrored["outcome_p0"] == 1


# ---------------------------------------------------------------------------
# Test 8: End-to-end HDF5 output structure
# ---------------------------------------------------------------------------

class TestHDF5Output:
    def _write_jsonl(self, records, path):
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def test_hdf5_datasets_exist(self):
        """process_file creates all required HDF5 datasets."""
        unit_index = load_unit_index()
        schema_path = os.path.join(TRAINING_DIR, "schema_v2.json")

        instances = [
            make_instance("Drone", 0),
            make_instance("Engineer", 1),
        ]
        records = [make_record(instances)]

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "test.jsonl")
            out_path = os.path.join(tmpdir, "test.h5")
            self._write_jsonl(records, in_path)

            v2.process_file(in_path, unit_index, out_path, schema={
                "schema_version": "v2",
                "num_units": 116,
                "max_instances": 200,
                "num_supply_features": 3,
                "num_global_features": 14,
                "num_instance_features": 10,
                "normalization_caps": {
                    "gold": 20, "blue": 5, "red": 5, "green": 15,
                    "energy": 10, "attack": 25, "turn_number": 50
                }
            })

            with h5py.File(out_path, "r") as hf:
                required = [
                    "instance_features", "instance_unit_ids", "instance_counts",
                    "supply", "globals",
                    "label_A", "label_B_weight", "label_C", "label_D",
                    "replay_codes", "ply_index", "total_plies",
                ]
                for ds_name in required:
                    assert ds_name in hf, f"Missing dataset: {ds_name}"

    def test_hdf5_shapes(self):
        """HDF5 datasets have correct shapes for N=2 records."""
        unit_index = load_unit_index()

        instances_a = [make_instance("Drone", 0), make_instance("Engineer", 1)]
        instances_b = [make_instance("Drone", 0), make_instance("Drone", 0), make_instance("Wall", 1)]
        records = [make_record(instances_a), make_record(instances_b)]

        schema = {
            "schema_version": "v2",
            "num_units": 116,
            "max_instances": 200,
            "num_supply_features": 3,
            "num_global_features": 14,
            "num_instance_features": 10,
            "normalization_caps": {
                "gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "test.jsonl")
            out_path = os.path.join(tmpdir, "test.h5")
            self._write_jsonl(records, in_path)
            v2.process_file(in_path, unit_index, out_path, schema=schema)

            with h5py.File(out_path, "r") as hf:
                N = 2
                MAX_I = 200
                NUM_U = 116

                assert hf["instance_features"].shape == (N, MAX_I, 10)
                assert hf["instance_unit_ids"].shape == (N, MAX_I)
                assert hf["instance_counts"].shape == (N,)
                assert hf["supply"].shape == (N, NUM_U, 3)
                assert hf["globals"].shape == (N, 14)
                assert hf["label_A"].shape == (N,)
                assert hf["label_B_weight"].shape == (N,)
                assert hf["label_C"].shape == (N,)
                assert hf["label_D"].shape == (N,)

    def test_instance_counts_correct(self):
        """instance_counts reflects actual (non-padded) instance count per record."""
        unit_index = load_unit_index()

        instances_a = [make_instance("Drone", 0), make_instance("Engineer", 1)]  # 2
        instances_b = [make_instance("Drone", 0), make_instance("Drone", 0), make_instance("Wall", 1)]  # 3

        records = [make_record(instances_a), make_record(instances_b)]
        schema = {
            "schema_version": "v2",
            "num_units": 116,
            "max_instances": 200,
            "num_supply_features": 3,
            "num_global_features": 14,
            "num_instance_features": 10,
            "normalization_caps": {
                "gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "test.jsonl")
            out_path = os.path.join(tmpdir, "test.h5")
            self._write_jsonl(records, in_path)
            v2.process_file(in_path, unit_index, out_path, schema=schema)

            with h5py.File(out_path, "r") as hf:
                counts = hf["instance_counts"][:]
                assert counts[0] == 2, f"Expected 2, got {counts[0]}"
                assert counts[1] == 3, f"Expected 3, got {counts[1]}"

    def test_label_a_correct(self):
        """label_A is raw outcome_p0."""
        unit_index = load_unit_index()
        records = [
            make_record([make_instance("Drone", 0)], outcome_p0=1),
            make_record([make_instance("Drone", 0)], outcome_p0=0),
        ]
        schema = {
            "schema_version": "v2",
            "num_units": 116,
            "max_instances": 200,
            "num_supply_features": 3,
            "num_global_features": 14,
            "num_instance_features": 10,
            "normalization_caps": {
                "gold": 20, "blue": 5, "red": 5, "green": 15,
                "energy": 10, "attack": 25, "turn_number": 50
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "test.jsonl")
            out_path = os.path.join(tmpdir, "test.h5")
            self._write_jsonl(records, in_path)
            v2.process_file(in_path, unit_index, out_path, schema=schema)

            with h5py.File(out_path, "r") as hf:
                labels = hf["label_A"][:]
                assert labels[0] == pytest.approx(1.0)
                assert labels[1] == pytest.approx(0.0)
