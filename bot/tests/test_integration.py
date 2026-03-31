"""Integration test — full pipeline from state init to AI move.

Requires PrismataAI.exe at the configured path.
Run with: pytest bot/tests/test_integration.py -v -s -m integration
"""

import json
import os
import pytest
from bot.config import PRISMATA_AI_EXE
from bot.state_bridge import StateBridge
from bot.steam_ai_bridge import SteamAIBridge
from bot.ai_params import load_params
from bot.config import AI_SHORT_PARAMS_PATH

SUGGEST_STATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'js_engine', '_suggest_state.json'
)


def load_test_deck():
    with open(SUGGEST_STATE_PATH, 'r') as f:
        data = json.load(f)
    return data["CurrentInfo"]["mergedDeck"]


@pytest.mark.integration
class TestFullPipeline:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        if not os.path.isfile(PRISMATA_AI_EXE):
            pytest.skip(f"PrismataAI.exe not found at {PRISMATA_AI_EXE}")
        if not os.path.isfile(SUGGEST_STATE_PATH):
            pytest.skip(f"Reference state not found at {SUGGEST_STATE_PATH}")

    def test_turn_0_produces_clicks(self):
        """Full pipeline: init → export → AI request → PrismataAI.exe → clicks."""
        deck = load_test_deck()
        bridge = StateBridge()
        try:
            result = bridge.start(deck)
            assert result["ok"], f"INIT failed: {result}"

            export = bridge.export_state()
            assert export["ok"], f"EXPORT failed: {export}"
            state = export["state"]
            assert state["turn"] == 0
            assert state["phase"] == "action"

            short_params = load_params(AI_SHORT_PARAMS_PATH)
            ai_params = json.loads(short_params)
            request = {
                "mergedDeck": deck,
                "gameState": state,
                "aiParameters": ai_params,
                "aiPlayerName": "HardestAI",
            }

            steam = SteamAIBridge()
            response = steam.get_move(request)

            clicks = response.get("aiclicks", [])
            assert len(clicks) > 0, f"No clicks returned: {response}"

            apply_result = bridge.apply_clicks(clicks)
            assert apply_result["ok"], f"CLICKS failed: {apply_result}"
            assert apply_result["applied"] > 0

            export2 = bridge.export_state()
            assert export2["ok"]

            print(f"\nTurn 0: {len(clicks)} clicks, "
                  f"eval={response.get('eval_pct', '?')}, "
                  f"applied={apply_result['applied']}, failed={apply_result.get('failed', 0)}")
        finally:
            bridge.close()
