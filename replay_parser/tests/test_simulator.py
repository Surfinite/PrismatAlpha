from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate, _preprocess_clicks
from replay_parser.models import ResourcePool
import os
import pytest

TEST_REPLAY_CODE = "++A4h-1QDmB"
REPLAYS_ARCHIVE = "c:/libraries/prismata-replay-parser/replays_archive"
TEST_REPLAY_PATH = os.path.join(REPLAYS_ARCHIVE, f"{TEST_REPLAY_CODE}.json.gz")

needs_replay = pytest.mark.skipif(
    not os.path.exists(TEST_REPLAY_PATH),
    reason="Test replay not found"
)

@needs_replay
def test_simulate_populates_turns():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    assert len(replay.turns) == 23

@needs_replay
def test_simulate_turn0_is_p0():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    assert t0.player == 0
    assert t0.global_turn == 0
    assert t0.player_turn == 1

@needs_replay
def test_simulate_turn0_starting_state():
    """units_owned is start-of-turn, before any buys."""
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    assert t0.units_owned["Drone"] == 6
    assert t0.units_owned["Engineer"] == 2

@needs_replay
def test_simulate_turn0_resources():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    # Engineer has beginOwnTurnScript: {"receive": "H"} -> 2 energy passive
    # Drone has NO beginOwnTurnScript (gold comes from ability click, not passive)
    assert t0.resources_at_start.energy == 2
    assert t0.resources_at_start.gold == 0  # no passive gold

@needs_replay
def test_simulate_turn0_buys():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    # Turn 0 clicks: inst shift clicked 0, card shift clicked 5(Drone), space, space
    assert "Drone" in t0.buys

@needs_replay
def test_simulate_turn1_is_p1():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t1 = replay.turns[1]
    assert t1.player == 1
    assert t1.global_turn == 1
    assert t1.player_turn == 1

@needs_replay
def test_simulate_turn1_starting_state():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t1 = replay.turns[1]
    assert t1.units_owned["Drone"] == 7
    assert t1.units_owned["Engineer"] == 2

@needs_replay
def test_simulate_turn2_buys_drone_and_engineer():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t2 = replay.turns[2]
    # Turn 2 (P0): inst shift clicked 0, card shift clicked 5(Drone),
    #              card shift clicked 19(Engineer), space, space
    assert "Drone" in t2.buys
    assert "Engineer" in t2.buys

@needs_replay
def test_simulate_abilities_tracked():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    assert "Drone" in t0.abilities_used

@needs_replay
def test_simulate_no_crash_on_full_replay():
    """Simulator should process all 23 turns without errors."""
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    assert len(replay.turns) == 23
    for turn in replay.turns:
        for name, count in turn.units_owned.items():
            assert count >= 0, f"Negative unit count: {name}={count} at turn {turn.global_turn}"

# ------------------------------------------------------------------
# Unit tests for _preprocess_clicks (no replay file required)
# ------------------------------------------------------------------

def _click(t, id=0):
    return {"_type": t, "_id": id}


def test_preprocess_clicks_no_undo():
    """With no undo/revert, clicks pass through unchanged."""
    clicks = [
        _click("inst shift clicked", 0),
        _click("card clicked", 5),
        _click("space clicked"),
    ]
    result = _preprocess_clicks(clicks)
    assert result == clicks


def test_preprocess_clicks_undo_removes_last_actionable():
    clicks = [
        _click("inst shift clicked", 0),
        _click("card clicked", 5),
        _click("undo clicked"),
    ]
    result = _preprocess_clicks(clicks)
    # "card clicked" should be removed; space and inst shift survive
    types = [c["_type"] for c in result]
    assert "card clicked" not in types
    assert "inst shift clicked" in types
    assert "undo clicked" not in types


def test_preprocess_clicks_double_undo():
    clicks = [
        _click("inst shift clicked", 0),
        _click("card clicked", 5),
        _click("undo clicked"),
        _click("undo clicked"),
    ]
    result = _preprocess_clicks(clicks)
    types = [c["_type"] for c in result]
    assert "card clicked" not in types
    assert "inst shift clicked" not in types
    assert len(result) == 0


def test_preprocess_clicks_revert_clears_actionable():
    clicks = [
        _click("inst shift clicked", 0),
        _click("card clicked", 5),
        _click("revert clicked"),
        _click("card clicked", 7),
    ]
    result = _preprocess_clicks(clicks)
    # Only the post-revert card click should survive
    types = [c["_type"] for c in result]
    assert types == ["card clicked"]
    assert result[0]["_id"] == 7


def test_preprocess_clicks_revert_keeps_post_revert_spaces():
    clicks = [
        _click("card clicked", 5),
        _click("space clicked"),
        _click("revert clicked"),
        _click("inst shift clicked", 0),
        _click("space clicked"),
    ]
    result = _preprocess_clicks(clicks)
    types = [c["_type"] for c in result]
    assert types == ["inst shift clicked", "space clicked"]


def test_preprocess_clicks_undo_skips_non_actionable():
    """Undo should skip over space clicks to find the actionable click."""
    clicks = [
        _click("card clicked", 5),
        _click("space clicked"),
        _click("undo clicked"),
    ]
    result = _preprocess_clicks(clicks)
    types = [c["_type"] for c in result]
    assert "card clicked" not in types
    assert "space clicked" in types


@needs_replay
def test_simulate_emotes_ignored():
    """Emote clicks should not produce actions."""
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t1 = replay.turns[1]
    for action in t1.actions:
        assert not action.action_type.startswith("emote")
