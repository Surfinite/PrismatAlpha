"""Tests for StateBridge — Python ↔ Node.js state tracker integration."""

import pytest
from bot.state_bridge import StateBridge

MINI_DECK = [
    {
        "baseSet": 1, "rarity": "trinket", "toughness": 1,
        "defaultBlocking": 1, "assignedBlocking": 0,
        "buyCost": "3H", "abilityScript": {"receive": "1"},
        "name": "Drone", "UIName": "Drone"
    },
    {
        "baseSet": 1, "rarity": "trinket", "toughness": 1,
        "defaultBlocking": 1, "buyCost": "2",
        "beginOwnTurnScript": {"receive": "H"}, "score": "2.01",
        "name": "Engineer", "UIName": "Engineer"
    },
]


class TestStateBridgeLifecycle:
    def test_init_and_export(self):
        bridge = StateBridge()
        try:
            result = bridge.start(MINI_DECK)
            assert result["ok"] is True
            export = bridge.export_state()
            assert export["ok"] is True
            state = export["state"]
            assert "table" in state
            assert "cards" in state
            assert "whiteMana" in state
            assert "blackMana" in state
            assert state["phase"] == "action"
            assert state["turn"] == 0
            assert len(state["table"]) > 0
        finally:
            bridge.close()

    def test_apply_empty_clicks(self):
        bridge = StateBridge()
        try:
            bridge.start(MINI_DECK)
            result = bridge.apply_clicks([])
            assert result["ok"] is True
            assert result["applied"] == 0
            assert result["failed"] == 0
        finally:
            bridge.close()

    def test_export_without_start_fails(self):
        bridge = StateBridge()
        try:
            result = bridge.export_state()
            assert result["ok"] is False
            assert "error" in result
        finally:
            bridge.close()

    def test_close_is_idempotent(self):
        bridge = StateBridge()
        bridge.start(MINI_DECK)
        bridge.close()
        bridge.close()


class TestReinit:
    def test_reinit_with_empty_clicks(self):
        """REINIT with no clicks should produce a fresh initial state."""
        bridge = StateBridge()
        try:
            bridge.start(MINI_DECK)
            result = bridge.reinit_from_clicks(MINI_DECK, {
                "commandList": [],
                "clicksPerTurn": [],
            })
            assert result["ok"] is True
            # numTurns starts at 1 in the Analyzer (turn 0 = P0's first turn)
            assert result["turn"] >= 0
        finally:
            bridge.close()

    def test_reinit_replays_clicks(self):
        """REINIT with clicks should advance the state past turn 0."""
        bridge = StateBridge()
        try:
            bridge.start(MINI_DECK)
            # Play a minimal turn: shift-click Drones (inst 0), buy Drone (card 0),
            # then space to commit. This is the standard opening.
            clicks = [
                {"_type": "inst shift clicked", "_id": 0},
                {"_type": "card clicked", "_id": 0},
                {"_type": "card clicked", "_id": 0},
                {"_type": "space clicked", "_id": -1},
            ]
            result = bridge.reinit_from_clicks(MINI_DECK, {
                "commandList": clicks,
                "clicksPerTurn": [4],
            })
            assert result["ok"] is True
            assert result["turn"] >= 1
        finally:
            bridge.close()

    def test_reinit_overwrites_previous_state(self):
        """REINIT should create a fresh state, not build on old state."""
        bridge = StateBridge()
        try:
            bridge.start(MINI_DECK)
            # Apply some clicks first
            bridge.apply_clicks([
                {"_type": "inst shift clicked", "_id": 0},
                {"_type": "card clicked", "_id": 0},
            ])
            # REINIT with empty clicks — should be back to initial state
            result = bridge.reinit_from_clicks(MINI_DECK, {
                "commandList": [],
                "clicksPerTurn": [],
            })
            assert result["ok"] is True
            # Verify export shows fresh initial state (turn 0, action phase)
            export = bridge.export_state()
            assert export["ok"] is True
            assert export["state"]["turn"] == 0
            assert export["state"]["phase"] == "action"
        finally:
            bridge.close()

    def test_reinit_without_start_works(self):
        """REINIT should work even if the process was already started (idempotent)."""
        bridge = StateBridge()
        try:
            # Start once
            bridge.start(MINI_DECK)
            # REINIT directly
            result = bridge.reinit_from_clicks(MINI_DECK, {
                "commandList": [],
                "clicksPerTurn": [],
            })
            assert result["ok"] is True
        finally:
            bridge.close()
