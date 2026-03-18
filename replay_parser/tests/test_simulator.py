from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate
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
