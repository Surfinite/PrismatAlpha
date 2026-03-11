"""
Tests for model_deepsets.py — PrismataDeepSets model.

Run: cd training && python -m pytest tests/test_model_deepsets.py -v
"""

import os
import sys

import pytest
import torch
import torch.nn as nn

# Add training/ to path so we can import model_deepsets
TRAINING_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TRAINING_DIR)

from model_deepsets import PrismataDeepSets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_batch(batch_size=4, max_instances=200, instance_features=10,
               num_units=116, globals_dim=14):
    """Create a random batch of model inputs."""
    instance_feats = torch.randn(batch_size, max_instances, instance_features)
    # Set owner (feature 0) to 0 or 1
    instance_feats[:, :, 0] = (torch.rand(batch_size, max_instances) > 0.5).float()

    instance_unit_ids = torch.randint(0, num_units, (batch_size, max_instances))
    instance_counts = torch.full((batch_size,), 50, dtype=torch.long)
    supply = torch.rand(batch_size, num_units, 3)
    globals_vec = torch.rand(batch_size, globals_dim)

    return instance_feats, instance_unit_ids, instance_counts, supply, globals_vec


# ---------------------------------------------------------------------------
# Test 1: Model forward pass with random data
# ---------------------------------------------------------------------------

class TestForwardPass:
    def test_output_shape(self):
        """Forward pass produces (B, 1) raw logit output."""
        model = PrismataDeepSets()
        model.eval()

        batch_size = 4
        feats, ids, counts, supply, globs = make_batch(batch_size=batch_size)

        with torch.no_grad():
            out = model(feats, ids, counts, supply, globs)

        assert out.shape == (batch_size, 1), f"Expected ({batch_size}, 1), got {out.shape}"

    def test_output_is_float(self):
        """Output tensor is float32."""
        model = PrismataDeepSets()
        model.eval()

        feats, ids, counts, supply, globs = make_batch()
        with torch.no_grad():
            out = model(feats, ids, counts, supply, globs)

        assert out.dtype == torch.float32, f"Expected float32, got {out.dtype}"

    def test_output_is_finite(self):
        """Output values are finite (no NaN or Inf)."""
        model = PrismataDeepSets()
        model.eval()

        feats, ids, counts, supply, globs = make_batch()
        with torch.no_grad():
            out = model(feats, ids, counts, supply, globs)

        assert torch.all(torch.isfinite(out)), "Output contains NaN or Inf"


# ---------------------------------------------------------------------------
# Test 2: Permutation invariance
# ---------------------------------------------------------------------------

class TestPermutationInvariance:
    def test_shuffled_instances_same_output(self):
        """Shuffling instance order within a sample does not change the output."""
        model = PrismataDeepSets()
        model.eval()

        feats, ids, counts, supply, globs = make_batch(batch_size=1, max_instances=20)
        # Only use 10 real instances
        counts = torch.tensor([10], dtype=torch.long)

        with torch.no_grad():
            out_orig = model(feats, ids, counts, supply, globs)

        # Shuffle the first 10 instances
        perm = torch.randperm(10)
        # Pad perm with identity for remaining slots
        full_perm = torch.cat([perm, torch.arange(10, 20)])

        feats_shuffled = feats[:, full_perm, :]
        ids_shuffled = ids[:, full_perm]

        with torch.no_grad():
            out_shuffled = model(feats_shuffled, ids_shuffled, counts, supply, globs)

        assert torch.allclose(out_orig, out_shuffled, atol=1e-5), (
            f"Permutation changed output: orig={out_orig.item():.6f}, "
            f"shuffled={out_shuffled.item():.6f}"
        )


# ---------------------------------------------------------------------------
# Test 3: Zero-padded instances don't affect output
# ---------------------------------------------------------------------------

class TestPaddingInvariance:
    def test_zero_padding_does_not_change_output(self):
        """Adding zero-padded instances beyond instance_counts does not change output."""
        model = PrismataDeepSets()
        model.eval()

        # Create 5 real instances in a 200-slot tensor
        feats_5 = torch.zeros(1, 200, 10)
        ids_5 = torch.zeros(1, 200, dtype=torch.long)

        # Fill first 5 with real data
        real_feats = torch.randn(5, 10)
        real_ids = torch.randint(0, 116, (5,))
        feats_5[0, :5] = real_feats
        ids_5[0, :5] = real_ids
        # Slots 5-199 are already zero (padded)

        counts_5 = torch.tensor([5], dtype=torch.long)
        supply = torch.rand(1, 116, 3)
        globs = torch.rand(1, 14)

        # Now create a version with extra non-zero data in the padded region
        # but instance_counts still says 5 — the model should ignore them
        feats_5_noisy = feats_5.clone()
        feats_5_noisy[0, 5:] = torch.randn(195, 10)  # noise in padded region
        ids_5_noisy = ids_5.clone()
        ids_5_noisy[0, 5:] = torch.randint(0, 116, (195,))

        with torch.no_grad():
            out_clean = model(feats_5, ids_5, counts_5, supply, globs)
            out_noisy = model(feats_5_noisy, ids_5_noisy, counts_5, supply, globs)

        assert torch.allclose(out_clean, out_noisy, atol=1e-5), (
            f"Noisy padding changed output: clean={out_clean.item():.6f}, "
            f"noisy={out_noisy.item():.6f}"
        )


# ---------------------------------------------------------------------------
# Test 4: Symmetry augmentation (anti-symmetry in logit space)
# ---------------------------------------------------------------------------

class TestSymmetryAugmentation:
    def test_mirror_value_approximately_negated(self):
        """value(original) + value(mirror) should be close to 0 (untrained model).

        An untrained model won't be exactly anti-symmetric, but the difference
        should be within a reasonable bound (< 2.0 in absolute value).
        """
        model = PrismataDeepSets()
        model.eval()

        # Create a state with clear P0/P1 distinction
        feats = torch.zeros(1, 10, 10)
        ids = torch.zeros(1, 10, dtype=torch.long)

        # 5 P0 units
        for i in range(5):
            feats[0, i, 0] = 0.0  # owner = P0
            feats[0, i, 1:] = torch.rand(9)
            ids[0, i] = i % 116

        # 5 P1 units
        for i in range(5, 10):
            feats[0, i, 0] = 1.0  # owner = P1
            feats[0, i, 1:] = torch.rand(9)
            ids[0, i] = i % 116

        counts = torch.tensor([10], dtype=torch.long)

        # Supply: [p0_supply, p1_supply, in_set]
        supply = torch.zeros(1, 116, 3)
        supply[0, 0, 0] = 5.0  # P0 has 5 of unit 0
        supply[0, 0, 1] = 3.0  # P1 has 3 of unit 0

        # Globals: [p0_gold, p0_blue, ..., p1_gold, ...]
        globs = torch.rand(1, 14)

        # Mirror: swap owner labels, swap supply P0/P1, swap globals P0/P1
        feats_mirror = feats.clone()
        feats_mirror[0, :, 0] = 1.0 - feats[0, :, 0]  # Swap owner

        supply_mirror = supply.clone()
        supply_mirror[0, :, 0] = supply[0, :, 1]  # p0_supply = original p1_supply
        supply_mirror[0, :, 1] = supply[0, :, 0]  # p1_supply = original p0_supply

        globs_mirror = globs.clone()
        # Swap P0 resources (indices 0-5) with P1 resources (indices 6-11)
        globs_mirror[0, 0:6] = globs[0, 6:12]
        globs_mirror[0, 6:12] = globs[0, 0:6]
        # active_player (index 13) stays the same for this test

        with torch.no_grad():
            val_orig = model(feats, ids, counts, supply, globs)
            val_mirror = model(feats_mirror, ids, counts, supply_mirror, globs_mirror)

        diff = abs(val_orig.item() + val_mirror.item())
        assert diff < 2.0, (
            f"value + mirror_value = {val_orig.item():.4f} + {val_mirror.item():.4f} = "
            f"{val_orig.item() + val_mirror.item():.4f}, expected |sum| < 2.0"
        )


# ---------------------------------------------------------------------------
# Test 5: Parameter count matches spec (~171K)
# ---------------------------------------------------------------------------

class TestParameterCount:
    def test_parameter_count_within_tolerance(self):
        """Total trainable parameter count is ~171K (allow ±5K tolerance)."""
        model = PrismataDeepSets()
        total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

        target = 171_000
        tolerance = 5_000

        assert abs(total_params - target) <= tolerance, (
            f"Parameter count {total_params:,} is outside [{target-tolerance:,}, "
            f"{target+tolerance:,}]"
        )

    def test_parameter_count_logged(self, capsys):
        """Just print the parameter count for visibility."""
        model = PrismataDeepSets()
        total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"\nTotal trainable parameters: {total_params:,}")
        # Always passes — just informational
        assert total_params > 0


# ---------------------------------------------------------------------------
# Test 6: Gradient flows through all components
# ---------------------------------------------------------------------------

class TestGradientFlow:
    def test_all_parameters_have_gradients(self):
        """After loss.backward(), all trainable parameters have non-None gradients."""
        model = PrismataDeepSets()
        model.train()

        feats, ids, counts, supply, globs = make_batch(batch_size=4)

        out = model(feats, ids, counts, supply, globs)
        # Binary cross-entropy compatible loss
        target = torch.rand(4, 1)
        loss = nn.functional.binary_cross_entropy_with_logits(out, target)
        loss.backward()

        missing_grad = []
        for name, param in model.named_parameters():
            if param.requires_grad and param.grad is None:
                missing_grad.append(name)

        assert len(missing_grad) == 0, (
            f"Parameters with no gradient after backward: {missing_grad}"
        )

    def test_property_table_buffer_no_gradient(self):
        """property_table is a buffer (not parameter), so it has no gradient."""
        model = PrismataDeepSets()

        # property_table should be a buffer, not a parameter
        param_names = {name for name, _ in model.named_parameters()}
        assert "property_table" not in param_names, (
            "property_table should be a buffer, not a trainable parameter"
        )

        buffer_names = {name for name, _ in model.named_buffers()}
        assert "property_table" in buffer_names, (
            "property_table should be registered as a buffer"
        )
