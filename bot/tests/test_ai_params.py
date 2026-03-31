"""Tests for AI parameter loading and selection."""

import json
import pytest
from bot.ai_params import load_params, select_params
from bot.config import AI_FULL_PARAMS_PATH, AI_SHORT_PARAMS_PATH


class TestLoadParams:
    def test_load_full_params_is_valid_json(self):
        raw = load_params(AI_FULL_PARAMS_PATH)
        data = json.loads(raw)
        assert "Players" in data
        assert "HardestAI" in data["Players"]

    def test_load_short_params_is_valid_json(self):
        raw = load_params(AI_SHORT_PARAMS_PATH)
        data = json.loads(raw)
        assert "Players" in data
        assert "HardestAI" in data["Players"]

    def test_hardest_ai_has_time_limit(self):
        raw = load_params(AI_SHORT_PARAMS_PATH)
        data = json.loads(raw)
        assert "TimeLimit" in data["Players"]["HardestAI"]
        assert isinstance(data["Players"]["HardestAI"]["TimeLimit"], int)

    def test_whitespace_stripped(self):
        raw = load_params(AI_FULL_PARAMS_PATH)
        assert '\t' not in raw
        assert '\n' not in raw
        assert '\r' not in raw


class TestSelectParams:
    def test_hardest_ai_always_short(self):
        assert select_params("HardestAI", 0, "full", "short") == "short"
        assert select_params("HardestAI", 5, "full", "short") == "short"
        assert select_params("HardestAI", 20, "full", "short") == "short"

    def test_docile_ai_gets_full_params(self):
        assert select_params("DocileAI", 0, "full", "short") == "full"
        assert select_params("DocileAI", 10, "full", "short") == "full"

    def test_docile_ai_gets_short_after_turn_16(self):
        assert select_params("DocileAI", 17, "full", "short") == "short"

    def test_unknown_ai_gets_full_early(self):
        assert select_params("CustomAI", 0, "full", "short") == "full"

    def test_unknown_ai_gets_short_late(self):
        assert select_params("CustomAI", 17, "full", "short") == "short"
