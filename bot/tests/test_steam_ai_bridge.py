"""Tests for SteamAI bridge — PrismataAI.exe subprocess wrapper."""

import json
import os
import pytest
from bot.steam_ai_bridge import SteamAIBridge

PRISMATA_AI_EXE = os.environ.get(
    "PRISMATA_AI_EXE",
    r"C:\libraries\Prismata\AI\PrismataAI.exe"
)
HAS_EXE = os.path.exists(PRISMATA_AI_EXE)


class TestCleanResponse:
    def test_strips_control_characters(self):
        bridge = SteamAIBridge()
        raw = '\x00\x1f{"aiclicks": [], "aithinktime": 100}\n'
        clean = bridge._clean_response(raw)
        parsed = json.loads(clean)
        assert "aiclicks" in parsed
        assert parsed["aithinktime"] == 100

    def test_finds_json_after_debug_output(self):
        bridge = SteamAIBridge()
        raw = 'PRISMATA_ASSERT: something\n{"aiclicks": [{"_type": "card clicked", "_id": 0}]}'
        clean = bridge._clean_response(raw)
        parsed = json.loads(clean)
        assert len(parsed["aiclicks"]) == 1

    def test_no_json_returns_raw(self):
        bridge = SteamAIBridge()
        raw = 'no json here'
        assert bridge._clean_response(raw) == 'no json here'


class TestParseEvalPct:
    def test_parses_percentage_string(self):
        bridge = SteamAIBridge()
        assert bridge.parse_eval_pct({"eval_pct": "70%"}) == 70.0

    def test_parses_low_percentage(self):
        bridge = SteamAIBridge()
        assert bridge.parse_eval_pct({"eval_pct": "3%"}) == 3.0

    def test_returns_none_for_missing(self):
        bridge = SteamAIBridge()
        assert bridge.parse_eval_pct({}) is None

    def test_returns_none_for_invalid(self):
        bridge = SteamAIBridge()
        assert bridge.parse_eval_pct({"eval_pct": "abc%"}) is None


class TestGetMove:
    def test_accepts_dict_input(self):
        """Verify dict input is JSON-serialized (doesn't test exe)."""
        bridge = SteamAIBridge(exe_path="nonexistent.exe", timeout_s=1)
        # We can't actually run PrismataAI.exe in CI, but we can verify
        # the method accepts dicts without error before the subprocess call
        # This will raise FileNotFoundError or similar, not a JSON error
        with pytest.raises((FileNotFoundError, OSError, RuntimeError)):
            bridge.get_move({"test": True})

    @pytest.mark.skipif(not HAS_EXE, reason="PrismataAI.exe not found")
    def test_timeout_with_bad_input(self):
        """PrismataAI.exe with garbage input should exit quickly (not hang)."""
        bridge = SteamAIBridge(exe_path=PRISMATA_AI_EXE, timeout_s=5)
        # Bad input — exe should exit with error, not hang
        with pytest.raises((RuntimeError, TimeoutError)):
            bridge.get_move('{"invalid": true}')
