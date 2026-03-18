"""Decoder: load .json.gz replay files and convert to structured ReplayData objects."""
import gzip
import json

from replay_parser.models import CardDef, ReplayData, ResourcePool
from replay_parser.resources import parse_resource_string

_SUPPLY_BY_RARITY = {
    "trinket": 20,
    "normal": 10,
    "rare": 4,
    "legendary": 1,
}


def load_replay(path: str) -> dict:
    """Open a .json.gz replay file and return the raw JSON dict."""
    with gzip.open(path, 'rt') as f:
        return json.load(f)


def _parse_card_def(deck_index: int, card: dict) -> CardDef:
    """Parse a single entry from mergedDeck into a CardDef."""
    rarity = card.get("rarity", "normal")

    # begin_turn_receive
    begin_turn_script = card.get("beginOwnTurnScript", {})
    btr_raw = begin_turn_script.get("receive")
    begin_turn_receive = parse_resource_string(btr_raw) if btr_raw is not None else None

    # ability_receive
    ability_script = card.get("abilityScript", {})
    abr_raw = ability_script.get("receive")
    ability_receive = parse_resource_string(abr_raw) if abr_raw is not None else None

    return CardDef(
        deck_index=deck_index,
        name=card.get("name"),
        rarity=rarity,
        buy_cost=parse_resource_string(card.get("buyCost", "")),
        toughness=card.get("toughness", 1),
        build_time=card.get("buildTime", 0),
        is_base_set=bool(card.get("baseSet", 0)),
        default_blocking=bool(card.get("defaultBlocking", 0)),
        begin_turn_receive=begin_turn_receive,
        begin_turn_delay=begin_turn_script.get("delay", 0),
        ability_receive=ability_receive,
        ability_selfsac=bool(ability_script.get("selfsac", False)),
        ability_create=ability_script.get("create"),
        target_action=card.get("targetAction"),
        supply=_SUPPLY_BY_RARITY.get(rarity, 10),
    )


def decode(raw: dict) -> ReplayData:
    """Parse a raw replay dict into a structured ReplayData object.

    The simulator later fills replay.turns by iterating commandInfo.
    This function only parses static structure — no simulation performed.
    """
    # Parse card definitions from mergedDeck
    merged_deck = raw["deckInfo"]["mergedDeck"]
    card_defs = [_parse_card_def(i, card) for i, card in enumerate(merged_deck)]

    # Randomizer = non-base-set cards
    randomizer = [cd.name for cd in card_defs if not cd.is_base_set]

    # init_cards: list of list of (count, name) tuples per player
    raw_init = raw["initInfo"]["initCards"]
    init_cards = [
        [(entry[0], entry[1]) for entry in player_cards]
        for player_cards in raw_init
    ]

    # Turn count from clicksPerTurn
    total_global_turns = len(raw["commandInfo"]["clicksPerTurn"])

    # Player names
    player_names = [
        raw["playerInfo"][0].get("displayName", ""),
        raw["playerInfo"][1].get("displayName", ""),
    ]

    replay = ReplayData(
        code=raw.get("code", ""),
        result=raw["result"],
        card_defs=card_defs,
        randomizer=randomizer,
        init_cards=init_cards,
        turns=[],
        total_global_turns=total_global_turns,
        start_time=raw.get("startTime"),
        player_names=player_names,
    )

    # Attach raw commandInfo for use by the simulator (private, not part of dataclass)
    replay._command_info = raw["commandInfo"]

    return replay
