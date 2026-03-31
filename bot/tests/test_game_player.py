"""Tests for GamePlayer -- resignation logic, BeginGame parsing, state bridge."""

import pytest
from bot.game_player import GamePlayer


# ------------------------------------------------------------------
# Fake state bridge for testing
# ------------------------------------------------------------------

class FakeStateBridge:
    """Mock StateBridge that records calls and returns canned responses."""

    def __init__(self, start_ok=True, export_state=None, apply_clicks_ok=True):
        self._start_ok = start_ok
        self._export_state = export_state or {
            "ok": True,
            "state": {"turnNumber": 0, "phase": "action"},
        }
        self._apply_clicks_ok = apply_clicks_ok
        self.started_with = None
        self.applied_clicks = []
        self.closed = False

    def start(self, merged_deck):
        self.started_with = merged_deck
        return {"ok": self._start_ok}

    def export_state(self):
        return dict(self._export_state)

    def apply_clicks(self, clicks):
        self.applied_clicks.extend(clicks)
        applied = len(clicks)
        failed = 0 if self._apply_clicks_ok else len(clicks)
        return {"ok": self._apply_clicks_ok, "applied": applied, "failed": failed}

    def close(self):
        self.closed = True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_init_info(game_id="abc-123", fmt=201, players=None, username="TestBot"):
    """Build a minimal BeginGame init_info dict."""
    if players is None:
        players = [
            {"displayName": username, "name": username, "bot": ""},
            {"displayName": "Master Bot", "name": username, "bot": "HardestAI"},
        ]
    return {
        "liveGameID": game_id,
        "format": fmt,
        "mergedDeck": [],
        "laneInfo": [{
            "players": players,
            "initCards": [[[6, "Drone"]], [[7, "Drone"]]],
            "base": [[], []],
            "randomizer": [[], []],
            "initResources": ["0", "0"],
        }],
        "commandInfo": {"commandList": [], "clicksPerTurn": []},
        "timeInfo": {"turnNumber": -1},
    }


# ------------------------------------------------------------------
# Resignation logic
# ------------------------------------------------------------------

class TestResignation:
    def test_no_resign_above_threshold(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(50.0)
        gp.record_eval(45.0)
        gp.record_eval(30.0)
        assert not gp.should_resign()

    def test_resign_after_three_low_evals(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.0)
        assert not gp.should_resign()
        gp.record_eval(3.0)
        assert not gp.should_resign()
        gp.record_eval(2.0)
        assert gp.should_resign()

    def test_resign_resets_on_high_eval(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.0)
        gp.record_eval(3.0)
        gp.record_eval(50.0)  # recovered
        gp.record_eval(4.0)
        gp.record_eval(3.0)
        assert not gp.should_resign()

    def test_reset_clears_evals(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(2.0)
        gp.record_eval(1.0)
        gp.reset()
        gp.record_eval(3.0)
        gp.record_eval(2.0)
        assert not gp.should_resign()

    def test_none_eval_resets_counter(self):
        """None eval (missing from response) should reset the counter."""
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.0)
        gp.record_eval(3.0)
        gp.record_eval(None)  # missing eval
        gp.record_eval(2.0)
        gp.record_eval(1.0)
        assert not gp.should_resign()

    def test_exactly_at_threshold_not_low(self):
        """Eval exactly at threshold (5.0) should NOT count as low."""
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(5.0)
        gp.record_eval(5.0)
        gp.record_eval(5.0)
        assert not gp.should_resign()

    def test_just_below_threshold(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.99)
        gp.record_eval(4.99)
        gp.record_eval(4.99)
        assert gp.should_resign()


# ------------------------------------------------------------------
# BeginGame parsing
# ------------------------------------------------------------------

class TestBeginGameParsing:
    def test_extracts_game_id(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        init_info = _make_init_info(game_id="abc-123", fmt=201)
        gp.handle_message(["BeginGame", init_info])
        assert gp.game_id == "abc-123"
        assert gp.our_player_index == 0
        assert gp.opponent_name == "Master Bot"
        assert gp.format == 201

    def test_identifies_as_p1(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        players = [
            {"displayName": "SomePlayer", "name": "SomePlayer", "bot": ""},
            {"displayName": "TestBot", "name": "TestBot", "bot": ""},
        ]
        init_info = _make_init_info(game_id="xyz", fmt=202, players=players)
        gp.handle_message(["BeginGame", init_info])
        assert gp.our_player_index == 1
        assert gp.opponent_name == "SomePlayer"

    def test_stores_merged_deck(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        info = _make_init_info()
        info["mergedDeck"] = [{"name": "Drone"}, {"name": "Engineer"}]
        gp.handle_message(["BeginGame", info])
        assert len(gp.merged_deck) == 2

    def test_stores_lane_info(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        info = _make_init_info()
        gp.handle_message(["BeginGame", info])
        assert gp.lane_info is not None
        assert "players" in gp.lane_info

    def test_restores_command_list(self):
        """BeginGame with existing commandInfo (reconnection) should restore clicks."""
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        info = _make_init_info()
        info["commandInfo"] = {
            "commandList": [
                {"_type": "card clicked", "_id": 0},
                {"_type": "space clicked", "_id": -1},
            ],
            "clicksPerTurn": [2],
        }
        gp.handle_message(["BeginGame", info])
        assert len(gp.command_list) == 2
        assert len(gp.clicks_per_turn) == 1

    def test_unknown_username_no_crash(self):
        """If username doesn't match any player, should not crash."""
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "UnknownBot"
        info = _make_init_info()
        gp.handle_message(["BeginGame", info])
        assert gp.our_player_index is None
        assert gp.game_id == "abc-123"


# ------------------------------------------------------------------
# Turn tracking
# ------------------------------------------------------------------

class TestTurnTracking:
    def test_is_our_turn_p0(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.our_player_index = 0
        gp.current_turn = 0
        assert gp._is_our_turn()
        gp.current_turn = 1
        assert not gp._is_our_turn()
        gp.current_turn = 2
        assert gp._is_our_turn()

    def test_is_our_turn_p1(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.our_player_index = 1
        gp.current_turn = 0
        assert not gp._is_our_turn()
        gp.current_turn = 1
        assert gp._is_our_turn()
        gp.current_turn = 3
        assert gp._is_our_turn()

    def test_is_our_turn_no_index(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.our_player_index = None
        gp.current_turn = 0
        assert not gp._is_our_turn()


# ------------------------------------------------------------------
# Opponent click tracking
# ------------------------------------------------------------------

class TestOpponentClicks:
    def test_click_appended_to_command_list(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 5}])
        assert len(gp.command_list) == 1
        assert gp.command_list[0]["_id"] == 5

    def test_multiple_clicks_accumulated(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 1}])
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 2}])
        gp.handle_message(["Click", "game-id", {"_type": "space clicked", "_id": -1}])
        assert len(gp.command_list) == 3


# ------------------------------------------------------------------
# Message routing
# ------------------------------------------------------------------

class TestMessageRouting:
    def test_empty_message_no_crash(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.handle_message([])
        gp.handle_message(None)
        gp.handle_message("not a list")

    def test_unknown_message_no_crash(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.handle_message(["SomeFutureMessage", {"data": 1}])

    def test_begin_game_missing_payload(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.handle_message(["BeginGame"])  # no init_info
        assert gp.game_id is None


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all_state(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.client_username = "TestBot"
        gp.handle_message(["BeginGame", _make_init_info()])
        gp.command_list.append({"_type": "card clicked", "_id": 0})
        gp.record_eval(2.0)

        gp.reset()

        assert gp.game_id is None
        assert gp.our_player_index is None
        assert gp.command_list == []
        assert gp._consecutive_low_evals == 0
        assert not gp.game_over

    def test_reset_closes_state_bridge(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp.reset()
        assert fake.closed

    def test_reset_clears_pending_opponent_clicks(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp._pending_opponent_clicks = [{"_type": "card clicked", "_id": 1}]
        gp.reset()
        assert gp._pending_opponent_clicks == []


# ------------------------------------------------------------------
# Build AI request
# ------------------------------------------------------------------

class TestBuildAIRequest:
    def test_builds_valid_request(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp.client_username = "TestBot"
        info = _make_init_info()
        info["mergedDeck"] = [{"name": "Drone"}, {"name": "Engineer"}]
        gp.handle_message(["BeginGame", info])

        req = gp._build_ai_request()
        assert req is not None
        assert "mergedDeck" in req
        assert "gameState" in req
        assert "aiParameters" in req
        assert "aiPlayerName" in req
        assert req["aiPlayerName"] == "HardestAI"

    def test_state_bridge_initialized_on_begin_game(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp.client_username = "TestBot"
        info = _make_init_info()
        info["mergedDeck"] = [{"name": "Drone"}]
        gp.handle_message(["BeginGame", info])
        assert fake.started_with == [{"name": "Drone"}]

    def test_returns_none_without_state_bridge(self):
        gp = GamePlayer(bridge=None, client=None, state_bridge=None)
        gp.client_username = "TestBot"
        gp.handle_message(["BeginGame", _make_init_info()])
        assert gp._build_ai_request() is None


# ------------------------------------------------------------------
# Opponent click flushing
# ------------------------------------------------------------------

class TestOpponentClickFlushing:
    def test_opponent_clicks_flushed(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 5}])
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 6}])
        gp._flush_opponent_clicks()
        assert len(fake.applied_clicks) == 2
        assert fake.applied_clicks[0]["_id"] == 5
        assert fake.applied_clicks[1]["_id"] == 6

    def test_flush_clears_buffer(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp.handle_message(["Click", "game-id", {"_type": "card clicked", "_id": 1}])
        gp._flush_opponent_clicks()
        assert gp._pending_opponent_clicks == []

    def test_flush_empty_is_noop(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        gp._flush_opponent_clicks()
        assert fake.applied_clicks == []


# ------------------------------------------------------------------
# ManyClicks
# ------------------------------------------------------------------

class TestManyClicks:
    def test_many_clicks_buffered(self):
        fake = FakeStateBridge()
        gp = GamePlayer(bridge=None, client=None, state_bridge=fake)
        clicks = [
            {"_type": "card clicked", "_id": 1},
            {"_type": "card clicked", "_id": 2},
            {"_type": "space clicked", "_id": -1},
        ]
        gp.handle_message(["ManyClicks", "game-id", clicks])
        assert len(gp._pending_opponent_clicks) == 3
        assert len(gp.command_list) == 3
