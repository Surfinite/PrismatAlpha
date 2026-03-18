"""Tests for replay_parser.decoder — load and decode .json.gz replay files."""
import os

import pytest

from replay_parser.decoder import decode, load_replay
from replay_parser.models import ResourcePool

TEST_REPLAY_CODE = "++A4h-1QDmB"
REPLAYS_ARCHIVE = "c:/libraries/prismata-replay-parser/replays_archive"
TEST_REPLAY_PATH = os.path.join(REPLAYS_ARCHIVE, f"{TEST_REPLAY_CODE}.json.gz")

needs_replay = pytest.mark.skipif(
    not os.path.exists(TEST_REPLAY_PATH),
    reason="Test replay not found",
)


@needs_replay
def test_load_replay():
    raw = load_replay(TEST_REPLAY_PATH)
    assert "deckInfo" in raw
    assert "commandInfo" in raw
    assert "initInfo" in raw


@needs_replay
def test_decode_card_defs():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert len(replay.card_defs) > 10
    drone = next(cd for cd in replay.card_defs if cd.name == "Drone")
    assert drone.rarity == "trinket"
    assert drone.buy_cost == ResourcePool(gold=3, energy=1)
    assert drone.ability_receive == ResourcePool(gold=1)
    assert drone.is_base_set is True


@needs_replay
def test_decode_randomizer():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    for name in replay.randomizer:
        cd = next(c for c in replay.card_defs if c.name == name)
        assert cd.is_base_set is False


@needs_replay
def test_decode_init_cards():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    p0_init = replay.init_cards[0]
    assert (6, "Drone") in p0_init
    assert (2, "Engineer") in p0_init
    p1_init = replay.init_cards[1]
    assert (7, "Drone") in p1_init
    assert (2, "Engineer") in p1_init


@needs_replay
def test_decode_clicks_and_turns():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.total_global_turns == 23
    assert len(replay.turns) == 0  # turns empty before simulation


@needs_replay
def test_decode_result():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.result == 1  # P2 won


@needs_replay
def test_decode_player_names():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.player_names[0] == "flopflop"
    assert replay.player_names[1] == "Mmsven"


@needs_replay
def test_decode_supply():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    drone = next(cd for cd in replay.card_defs if cd.name == "Drone")
    assert drone.supply == 20  # trinket rarity
