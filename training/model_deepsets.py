"""
PrismataDeepSets — DeepSets neural network model for Prismata game state evaluation.

Architecture:
  - Unit-type embedding (learned, 116 × 32)
  - Shared instance encoder: [embedding | static_properties | instance_state] → 128-d vector
  - Sum pooling by owner (P0 pool, P1 pool)
  - Supply encoder: per-unit [p0_sup, p1_sup, in_set] → 32-d, then sum across all 116 types
  - Value MLP: [P0_pool | P1_pool | supply_pool | globals] → scalar logit

Input shapes (all batched with batch dim B):
  instance_features:  (B, MAX_INST, 10)  — per-instance state features
  instance_unit_ids:  (B, MAX_INST)      — unit type index (long)
  instance_counts:    (B,)               — actual (non-padded) instance count per sample
  supply:             (B, 116, 3)        — [p0_sup, p1_sup, in_set] per unit type
  globals_vec:        (B, 14)            — global game features

Output:
  value_logit: (B, 1) — raw logit for P(P0 wins); apply sigmoid for probability

Parameter count: ~172K trainable (property_table is a non-trainable buffer)
"""

import json
import os

import torch
import torch.nn as nn


class PrismataDeepSets(nn.Module):
    def __init__(
        self,
        num_units: int = 116,
        d_embed: int = 32,
        num_properties: int = 13,
        num_instance_features: int = 10,
        encoder_hidden: int = 128,
        supply_hidden: int = 32,
        value_hidden: int = 256,
        dropout: float = 0.1,
    ):
        """
        Args:
            num_units:             Number of distinct unit types (embedding vocab size).
            d_embed:               Dimensionality of unit-type embeddings.
            num_properties:        Number of static (non-learnable) unit properties.
            num_instance_features: Number of per-instance state features (owner, hp, etc.).
            encoder_hidden:        Hidden/output dim of the shared instance encoder.
            supply_hidden:         Hidden/output dim of the supply encoder.
            value_hidden:          Hidden dim of the value MLP head.
            dropout:               Dropout probability applied only in the value head.
        """
        super().__init__()

        # ------------------------------------------------------------------ #
        # Unit-type embedding (learned)
        # ------------------------------------------------------------------ #
        self.unit_embedding = nn.Embedding(num_units, d_embed)

        # ------------------------------------------------------------------ #
        # Shared instance encoder
        # Input: [embedding | static_properties | instance_state]
        # Dims:  [d_embed   | num_properties    | num_instance_features]
        #      = [32        | 13               | 10] = 55
        # ------------------------------------------------------------------ #
        token_dim = d_embed + num_properties + num_instance_features  # 55
        self.instance_encoder = nn.Sequential(
            nn.Linear(token_dim, encoder_hidden),
            nn.ReLU(),
            nn.Linear(encoder_hidden, encoder_hidden),
            nn.ReLU(),
        )

        # ------------------------------------------------------------------ #
        # Supply encoder (separate pathway)
        # Input per unit type: [p0_supply, p1_supply, in_card_set]  (3 values)
        # ------------------------------------------------------------------ #
        self.supply_encoder = nn.Sequential(
            nn.Linear(3, supply_hidden),
            nn.ReLU(),
            nn.Linear(supply_hidden, supply_hidden),
            nn.ReLU(),
        )

        # ------------------------------------------------------------------ #
        # Value MLP head
        # Input: P0_pool (encoder_hidden) + P1_pool (encoder_hidden)
        #        + supply_pool (supply_hidden) + globals (14)
        # ------------------------------------------------------------------ #
        value_input_dim = encoder_hidden * 2 + supply_hidden + 14  # 302
        self.value_head = nn.Sequential(
            nn.Linear(value_input_dim, value_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(value_hidden, value_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(value_hidden, 1),
        )

        # ------------------------------------------------------------------ #
        # Static property table — buffer (NOT a trainable parameter)
        # Shape: (num_units, num_properties) — loaded from property_table.json
        # ------------------------------------------------------------------ #
        self.register_buffer(
            "property_table", torch.zeros(num_units, num_properties)
        )

        # Store config for load_property_table and introspection
        self._num_units = num_units
        self._num_properties = num_properties

    # ---------------------------------------------------------------------- #
    # Property table loading
    # ---------------------------------------------------------------------- #

    def load_property_table(self, path: str) -> None:
        """Load static property vectors from property_table.json.

        The JSON format expected:
          {
            "num_units": 116,
            "num_properties": 13,
            "units": {
              "Engineer": {"index": 0, "properties": [...]},
              ...
            }
          }
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        units = data["units"]
        num_units = data.get("num_units", self._num_units)
        num_props = data.get("num_properties", self._num_properties)

        table = torch.zeros(num_units, num_props, dtype=torch.float32)
        for name, info in units.items():
            idx = info["index"]
            table[idx] = torch.tensor(info["properties"], dtype=torch.float32)

        self.property_table.copy_(table)

    @classmethod
    def from_property_table(cls, property_table_path: str, **kwargs) -> "PrismataDeepSets":
        """Convenience constructor: create model and immediately load property table."""
        model = cls(**kwargs)
        model.load_property_table(property_table_path)
        return model

    # ---------------------------------------------------------------------- #
    # Forward pass
    # ---------------------------------------------------------------------- #

    def forward(
        self,
        instance_features: torch.Tensor,
        instance_unit_ids: torch.Tensor,
        instance_counts: torch.Tensor,
        supply: torch.Tensor,
        globals_vec: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            instance_features: (B, MAX_INST, 10) — per-instance state features.
                                Feature 0 is owner: 0.0 = P0, 1.0 = P1.
            instance_unit_ids: (B, MAX_INST) — unit type index per instance (long).
            instance_counts:   (B,) — actual (non-padded) instance count per sample.
            supply:            (B, 116, 3) — [p0_sup, p1_sup, in_set] per unit type.
            globals_vec:       (B, 14) — global game features.

        Returns:
            value_logit: (B, 1) — raw logit for P(P0 wins).
                          Apply sigmoid for a probability, or pass directly to
                          BCEWithLogitsLoss during training.
        """
        B, MAX_INST, _ = instance_features.shape

        # ------------------------------------------------------------------ #
        # Build padding mask: True for real (non-padded) instances
        # ------------------------------------------------------------------ #
        idx = torch.arange(MAX_INST, device=instance_features.device).unsqueeze(0)  # (1, MAX_INST)
        mask = idx < instance_counts.unsqueeze(1)  # (B, MAX_INST) — bool

        # ------------------------------------------------------------------ #
        # Token construction: [embedding | static_properties | instance_state]
        # ------------------------------------------------------------------ #
        # Unit-type embeddings: (B, MAX_INST, d_embed)
        embeddings = self.unit_embedding(instance_unit_ids)

        # Static properties from buffer: (B, MAX_INST, num_properties)
        # property_table[instance_unit_ids] does a batched gather
        properties = self.property_table[instance_unit_ids]

        # Concatenate to form token: (B, MAX_INST, token_dim=55)
        tokens = torch.cat([embeddings, properties, instance_features], dim=-1)

        # ------------------------------------------------------------------ #
        # Encode all instances through the shared MLP
        # ------------------------------------------------------------------ #
        encoded = self.instance_encoder(tokens)  # (B, MAX_INST, encoder_hidden)

        # Zero out contributions from padded positions
        encoded = encoded * mask.unsqueeze(-1).float()  # (B, MAX_INST, encoder_hidden)

        # ------------------------------------------------------------------ #
        # Sum-pool by owner
        # owner = instance_features[:, :, 0]: 0.0 → P0, 1.0 → P1
        # ------------------------------------------------------------------ #
        owner = instance_features[:, :, 0]  # (B, MAX_INST)

        p0_mask = (mask & (owner < 0.5)).unsqueeze(-1).float()   # (B, MAX_INST, 1)
        p1_mask = (mask & (owner >= 0.5)).unsqueeze(-1).float()  # (B, MAX_INST, 1)

        p0_pool = (encoded * p0_mask).sum(dim=1)  # (B, encoder_hidden)
        p1_pool = (encoded * p1_mask).sum(dim=1)  # (B, encoder_hidden)

        # ------------------------------------------------------------------ #
        # Supply encoding
        # supply: (B, 116, 3) → encode each unit's supply tuple → sum over units
        #
        # Note: ~93 of 116 unit types have [0,0,0] supply in any given game
        # (not in the card set). The bias terms in supply_encoder mean those
        # contribute a constant offset to supply_pool. This is a learned constant
        # and doesn't harm training; masking zero-input types is a future ablation
        # candidate if supply signal appears weak.
        # ------------------------------------------------------------------ #
        supply_flat = supply.view(B * self._num_units, 3)                    # (B*116, 3)
        supply_encoded = self.supply_encoder(supply_flat)                     # (B*116, supply_hidden)
        supply_encoded = supply_encoded.view(B, self._num_units, -1)         # (B, 116, supply_hidden)
        supply_pool = supply_encoded.sum(dim=1)                              # (B, supply_hidden)

        # ------------------------------------------------------------------ #
        # Value head: concatenate all signals and predict
        # ------------------------------------------------------------------ #
        combined = torch.cat([p0_pool, p1_pool, supply_pool, globals_vec], dim=-1)  # (B, 302)
        value_logit = self.value_head(combined)  # (B, 1)

        return value_logit
