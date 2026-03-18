"""Prismata replay parser — click-level analysis with resource tracking.

Usage:
    from replay_parser import decoder, simulator
    replay = decoder.decode(decoder.load_replay("game.json.gz"))
    simulator.simulate(replay)
    for turn in replay.turns:
        print(f"Turn {turn.global_turn}: buys={turn.buys}")
"""
__version__ = "0.1.0"

from replay_parser.models import (
    ResourcePool, CardDef, UnitInstance, Action, Turn, ReplayData
)
from replay_parser.resources import parse_resource_string
from replay_parser import decoder, simulator, database, fetch, pipeline
