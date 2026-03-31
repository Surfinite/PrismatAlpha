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
