# Opening Book Analysis — Python Replay Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python replay parser library (`replay_parser/`) that extracts per-turn actions, resources, and buy sequences from Prismata replays into SQLite, enabling opening book analysis across 102k expert games.

**Architecture:** Modular Python package with 7 focused modules (models, resources, decoder, simulator, database, fetch, pipeline). Tier 2 click-level parser with resource tracking. Extends existing `replays.db` with 4 new tables. TDD throughout — each module gets its tests first.

**Tech Stack:** Python 3.10+, stdlib only (sqlite3, gzip, json, dataclasses, pathlib, argparse, urllib, logging). Optional tqdm for progress bars.

**Spec:** `docs/superpowers/specs/2026-03-18-opening-book-analysis-design.md`

---

## File Map

```
replay_parser/                    # NEW — Python package
├── __init__.py                   # Package version, public API exports
├── __main__.py                   # CLI: python -m replay_parser
├── models.py                     # Dataclasses: ResourcePool, CardDef, UnitInstance, Action, Turn, ReplayData
├── resources.py                  # parse_resource_string(), ResourcePool arithmetic
├── decoder.py                    # load_replay(), decode() — .json.gz → ReplayData (no simulation)
├── simulator.py                  # simulate() — walk clicks, track state, populate turns
├── database.py                   # migrate(), store(), query helpers
├── fetch.py                      # fetch_replay() — S3 download
├── pipeline.py                   # run() — orchestrator: fetch → decode → simulate → store
└── tests/
    ├── __init__.py
    ├── conftest.py               # Shared fixtures: sample replay data, temp DB
    ├── test_resources.py         # Resource string parsing
    ├── test_models.py            # Model construction and helpers
    ├── test_decoder.py           # Replay loading and decoding
    ├── test_simulator.py         # Click processing, state tracking
    ├── test_database.py          # Schema migration, store/query
    └── test_pipeline.py          # End-to-end pipeline
```

**Test replay for validation:** `++A4h-1QDmB` in `replays_archive/` — flopflop vs Mmsven, 23 turns, 319 clicks. Known turn-0 buy: shift-click Drone (deck[5]). Known turn-2 buys: shift-click Drone + shift-click Engineer.

---

## Task 1: Package Skeleton & Models

**Files:**
- Create: `replay_parser/__init__.py`
- Create: `replay_parser/models.py`
- Create: `replay_parser/tests/__init__.py`
- Create: `replay_parser/tests/test_models.py`

- [ ] **Step 1: Create package skeleton**

```python
# replay_parser/__init__.py
"""Prismata replay parser — click-level analysis with resource tracking."""
__version__ = "0.1.0"
```

```python
# replay_parser/tests/__init__.py
```

- [ ] **Step 2: Write model tests**

```python
# replay_parser/tests/test_models.py
from replay_parser.models import ResourcePool, CardDef, UnitInstance, Action, Turn, ReplayData

def test_resource_pool_defaults():
    r = ResourcePool()
    assert r.gold == 0 and r.green == 0 and r.blue == 0
    assert r.red == 0 and r.energy == 0 and r.attack == 0

def test_resource_pool_add():
    a = ResourcePool(gold=3, green=1)
    b = ResourcePool(gold=2, blue=1)
    c = a + b
    assert c.gold == 5 and c.green == 1 and c.blue == 1

def test_resource_pool_can_afford():
    pool = ResourcePool(gold=6, green=2, blue=1)
    cost = ResourcePool(gold=4, green=1)
    assert pool.can_afford(cost)
    expensive = ResourcePool(gold=10)
    assert not pool.can_afford(expensive)

def test_resource_pool_subtract():
    pool = ResourcePool(gold=6, green=2)
    cost = ResourcePool(gold=3, green=1)
    result = pool - cost
    assert result.gold == 3 and result.green == 1

def test_resource_pool_max_affordable():
    pool = ResourcePool(gold=10, blue=3)
    cost = ResourcePool(gold=4, blue=1)
    assert pool.max_affordable(cost) == 2  # 10//4=2, 3//1=3, min=2

def test_card_def_construction():
    cd = CardDef(
        deck_index=5, name="Drone", rarity="trinket",
        buy_cost=ResourcePool(gold=3, energy=1), toughness=1,
        build_time=0, is_base_set=True, default_blocking=True,
        begin_turn_receive=None,
        ability_receive=ResourcePool(gold=1),
        ability_selfsac=False, ability_create=None,
        target_action=None, supply=20
    )
    assert cd.name == "Drone"
    assert cd.supply == 20

def test_unit_instance_construction():
    cd = CardDef(
        deck_index=5, name="Drone", rarity="trinket",
        buy_cost=ResourcePool(gold=3, energy=1), toughness=1,
        build_time=0, is_base_set=True, default_blocking=True,
        begin_turn_receive=None,
        ability_receive=ResourcePool(gold=1),
        ability_selfsac=False, ability_create=None,
        target_action=None, supply=20
    )
    unit = UnitInstance(
        instance_id=0, card_def=cd, owner=0,
        turns_until_ready=0, is_alive=True,
        used_ability_this_turn=False
    )
    assert unit.instance_id == 0
    assert unit.card_def.name == "Drone"
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_models.py -v`
Expected: FAIL — `models.py` doesn't exist yet.

- [ ] **Step 4: Implement models.py**

Create `replay_parser/models.py` with all dataclasses from spec Section 3.1:
- `ResourcePool` with `__add__`, `__sub__`, `can_afford(cost)`, `max_affordable(cost)`, `copy()`
- `CardDef`, `UnitInstance`, `Action`, `Turn`, `ReplayData`

Key implementation details:
- `ResourcePool.max_affordable(cost)`: For each non-zero resource in cost, compute `pool.X // cost.X`. Return min across all. Returns 0 if can't afford even one.
- `ResourcePool.__sub__`: Does NOT clamp to zero — negative values indicate a bug, which tests should catch.
- `CardDef` must include `begin_turn_delay: int = 0` — some units (Chrono Filter, Iso Kronus) have `beginOwnTurnScript.delay` meaning passive income doesn't fire until N turns after construction completes.
- All dataclasses use `@dataclass` from `dataclasses` module.

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_models.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add replay_parser/__init__.py replay_parser/models.py replay_parser/tests/__init__.py replay_parser/tests/test_models.py
git commit -m "feat(replay_parser): add package skeleton and data models"
```

---

## Task 2: Resource String Parser

**Files:**
- Create: `replay_parser/resources.py`
- Create: `replay_parser/tests/test_resources.py`

- [ ] **Step 1: Write resource parser tests**

```python
# replay_parser/tests/test_resources.py
from replay_parser.resources import parse_resource_string
from replay_parser.models import ResourcePool

def test_parse_gold_only():
    assert parse_resource_string("6") == ResourcePool(gold=6)

def test_parse_multi_digit_gold():
    assert parse_resource_string("15") == ResourcePool(gold=15)

def test_parse_drone_cost():
    # "3H" = 3 gold + 1 energy
    assert parse_resource_string("3H") == ResourcePool(gold=3, energy=1)

def test_parse_complex():
    # "6GGGRBB" = 6 gold + 3 green + 1 red + 2 blue
    assert parse_resource_string("6GGGRBB") == ResourcePool(gold=6, green=3, red=1, blue=2)

def test_parse_attack():
    assert parse_resource_string("AA") == ResourcePool(attack=2)

def test_parse_mixed_resources_and_attack():
    # "8AAAAAAAA" = 8 gold + 8 attack (Zemora)
    assert parse_resource_string("8AAAAAAAA") == ResourcePool(gold=8, attack=8)

def test_parse_gold_with_letters():
    # "5GGG" = 5 gold + 3 green
    assert parse_resource_string("5GGG") == ResourcePool(gold=5, green=3)

def test_parse_integer_input():
    # Some replay fields use int instead of str
    assert parse_resource_string(3) == ResourcePool(gold=3)

def test_parse_none():
    assert parse_resource_string(None) == ResourcePool()

def test_parse_empty_string():
    assert parse_resource_string("") == ResourcePool()

def test_parse_zero():
    assert parse_resource_string("0") == ResourcePool()

def test_parse_red_is_c():
    # "C" = red in replay encoding
    assert parse_resource_string("4C") == ResourcePool(gold=4, red=1)

def test_parse_blastforge_cost():
    # Blastforge: "5" = 5 gold
    assert parse_resource_string("5") == ResourcePool(gold=5)

def test_parse_colossus_cost():
    # "15GBBCC" = 15 gold + 1 green + 2 blue + 2 red
    assert parse_resource_string("15GBBCC") == ResourcePool(gold=15, green=1, blue=2, red=2)

def test_parse_all_resource_types():
    # Exercise every letter
    assert parse_resource_string("1GBCAH") == ResourcePool(
        gold=1, green=1, blue=1, red=1, attack=1, energy=1
    )
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_resources.py -v`
Expected: FAIL — `resources.py` doesn't exist.

- [ ] **Step 3: Implement resources.py**

```python
# replay_parser/resources.py
from replay_parser.models import ResourcePool

_CHAR_MAP = {
    'G': 'green',
    'B': 'blue',
    'C': 'red',
    'A': 'attack',
    'H': 'energy',
}

def parse_resource_string(value: str | int | None) -> ResourcePool:
    """Parse Prismata resource string into ResourcePool.

    Format: digits = gold, G = green, B = blue, C = red, A = attack, H = energy.
    Examples: "3H" → 3 gold + 1 energy. "15GBBCC" → 15 gold + 1 green + 2 blue + 2 red.
    Also accepts int (treated as gold) or None (returns empty pool).
    """
    if value is None:
        return ResourcePool()
    if isinstance(value, int):
        return ResourcePool(gold=value)

    result = ResourcePool()
    gold_digits = []
    for ch in value:
        if ch.isdigit():
            gold_digits.append(ch)
        elif ch in _CHAR_MAP:
            # Flush any accumulated gold digits first
            if gold_digits:
                result.gold += int(''.join(gold_digits))
                gold_digits = []
            field = _CHAR_MAP[ch]
            setattr(result, field, getattr(result, field) + 1)
        # else: unknown char, skip
    # Flush remaining gold digits
    if gold_digits:
        result.gold += int(''.join(gold_digits))
    return result
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_resources.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add replay_parser/resources.py replay_parser/tests/test_resources.py
git commit -m "feat(replay_parser): add resource string parser"
```

---

## Task 3: Test Fixtures

**Files:**
- Create: `replay_parser/tests/conftest.py`

This task creates shared fixtures used by decoder and simulator tests.

- [ ] **Step 1: Create conftest with replay fixtures**

```python
# replay_parser/tests/conftest.py
import pytest
import gzip
import json
import os
import sqlite3
import tempfile

# Path to a known test replay
TEST_REPLAY_CODE = "++A4h-1QDmB"
REPLAYS_ARCHIVE = "c:/libraries/prismata-replay-parser/replays_archive"
TEST_REPLAY_PATH = os.path.join(REPLAYS_ARCHIVE, f"{TEST_REPLAY_CODE}.json.gz")

@pytest.fixture
def raw_replay_data():
    """Load the raw JSON from test replay file."""
    if not os.path.exists(TEST_REPLAY_PATH):
        pytest.skip(f"Test replay not found: {TEST_REPLAY_PATH}")
    with gzip.open(TEST_REPLAY_PATH, 'rt') as f:
        return json.load(f)

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with the replays table schema."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE replays (
            code TEXT PRIMARY KEY,
            p1_name TEXT, p2_name TEXT,
            p1_rating REAL, p2_rating REAL,
            result INTEGER, deck TEXT,
            balance_passed INTEGER DEFAULT 1,
            min_rating REAL
        )
    """)
    conn.execute("""
        CREATE TABLE replay_units (
            code TEXT NOT NULL REFERENCES replays(code),
            unit_name TEXT NOT NULL,
            PRIMARY KEY (code, unit_name)
        )
    """)
    conn.execute("""
        CREATE TABLE db_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()  # Close setup connection before yielding (tests open their own)
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass  # Windows may still hold the file briefly
```

- [ ] **Step 2: Commit**

```bash
git add replay_parser/tests/conftest.py
git commit -m "feat(replay_parser): add test fixtures for replay data and temp DB"
```

---

## Task 4: Replay Decoder

**Files:**
- Create: `replay_parser/decoder.py`
- Create: `replay_parser/tests/test_decoder.py`

The decoder loads `.json.gz` files and converts raw JSON into structured `ReplayData` objects. No simulation — just parsing and structuring.

- [ ] **Step 1: Write decoder tests**

```python
# replay_parser/tests/test_decoder.py
from replay_parser.decoder import load_replay, decode
from replay_parser.models import ResourcePool
from replay_parser.tests.conftest import TEST_REPLAY_PATH
import os
import pytest

needs_replay = pytest.mark.skipif(
    not os.path.exists(TEST_REPLAY_PATH),
    reason="Test replay not found"
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
    # mergedDeck should have base + randomizer cards
    assert len(replay.card_defs) > 10
    # Drone should be present
    drone = next(cd for cd in replay.card_defs if cd.name == "Drone")
    assert drone.rarity == "trinket"
    assert drone.buy_cost == ResourcePool(gold=3, energy=1)
    assert drone.ability_receive == ResourcePool(gold=1)
    assert drone.is_base_set is True

@needs_replay
def test_decode_randomizer():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    # Should only contain non-base units
    for name in replay.randomizer:
        cd = next(c for c in replay.card_defs if c.name == name)
        assert cd.is_base_set is False

@needs_replay
def test_decode_init_cards():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    # P0: 6 Drones + 2 Engineers
    p0_init = replay.init_cards[0]
    assert (6, "Drone") in p0_init
    assert (2, "Engineer") in p0_init
    # P1: 7 Drones + 2 Engineers
    p1_init = replay.init_cards[1]
    assert (7, "Drone") in p1_init
    assert (2, "Engineer") in p1_init

@needs_replay
def test_decode_clicks_and_turns():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.total_global_turns == 23
    # turns list is empty before simulation
    assert len(replay.turns) == 0

@needs_replay
def test_decode_result():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.result == 1  # P2 (Mmsven) won

@needs_replay
def test_decode_player_names():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    assert replay.player_names[0] == "flopflop"
    assert replay.player_names[1] == "Mmsven"

@needs_replay
def test_decode_supply_drone_asymmetry():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    drone = next(cd for cd in replay.card_defs if cd.name == "Drone")
    # Drone supply is stored as base rarity supply (20 for trinket)
    # Per-player asymmetry (P0=21, P1=20) is handled by simulator, not decoder
    assert drone.supply == 20
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_decoder.py -v`
Expected: FAIL — `decoder.py` doesn't exist.

- [ ] **Step 3: Implement decoder.py**

Key implementation points:
- `load_replay(path: str) -> dict`: Open `.json.gz`, parse JSON, return raw dict.
- `decode(raw: dict) -> ReplayData`: Parse `deckInfo.mergedDeck` into `CardDef` list. Extract `initInfo.initCards`. Parse `commandInfo.clicksPerTurn` for turn count. Populate `randomizer` (cards where `baseSet` is not set/falsy). Extract `playerInfo[n].displayName`. Set `turns = []` (simulator populates this). Extract `result`, `code`, `startTime`.
- Supply from rarity: `{"trinket": 20, "normal": 10, "rare": 4, "legendary": 1}`.
- `CardDef.begin_turn_receive`: Parse `beginOwnTurnScript.receive` via `parse_resource_string()`. Handle `delay` field (store as separate attribute or ignore at decoder level — simulator handles timing).
- `CardDef.ability_receive`: Parse `abilityScript.receive`. Note `selfsac` and `create` fields.
- `CardDef.target_action`: From `targetAction` field if present.
- Handle missing fields gracefully — many cards lack `buildTime`, `abilityScript`, `beginOwnTurnScript`, etc. Default to 0/None/False.

Store the raw `commandInfo` on `ReplayData` as a private `_command_info` attribute — the simulator needs it but external callers don't.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_decoder.py -v`
Expected: All PASS (or skip if replay file absent).

- [ ] **Step 5: Commit**

```bash
git add replay_parser/decoder.py replay_parser/tests/test_decoder.py
git commit -m "feat(replay_parser): add replay decoder (json.gz → ReplayData)"
```

---

## Task 5: Simulator — Core State Tracking

**Files:**
- Create: `replay_parser/simulator.py`
- Create: `replay_parser/tests/test_simulator.py`

The simulator is the most complex module. This task covers initialization and basic ability/buy processing. Task 6 adds undo/revert handling and edge cases.

- [ ] **Step 1: Write simulator tests — initialization and turn 0**

```python
# replay_parser/tests/test_simulator.py
from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate
from replay_parser.models import ResourcePool
from replay_parser.tests.conftest import TEST_REPLAY_PATH
import os
import pytest

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
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    # P0 starts with 6 Drones + 2 Engineers
    assert t0.units_owned["Drone"] == 6
    assert t0.units_owned["Engineer"] == 2

@needs_replay
def test_simulate_turn0_resources():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    # P0 turn 0: 6 Drones clicked (shift-click) = 6 gold
    # Engineer passive: 2 * H = 2 energy
    # Drone passive: none (Drone has no beginOwnTurnScript)
    # Engineer beginOwnTurnScript: {"receive": "H"}
    assert t0.resources_at_start.energy == 2
    # Gold comes from clicking Drones (ability), not passive
    # resources_at_start is BEFORE clicks, so gold = 0 at start
    assert t0.resources_at_start.gold == 0

@needs_replay
def test_simulate_turn0_buys():
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    t0 = replay.turns[0]
    # Turn 0 clicks: inst shift clicked 0, card shift clicked 5(Drone), space, space
    # shift-click Drone with 6 gold (from shift-clicking all Drones) and 2 energy
    # Drone costs 3H (3 gold + 1 energy). Can afford: min(6//3, 2//1) = 2
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
    # P1 starts with 7 Drones + 2 Engineers
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
    # Turn 0 has "inst shift clicked" = ability activation
    assert "Drone" in t0.abilities_used
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_simulator.py -v`
Expected: FAIL — `simulator.py` doesn't exist.

- [ ] **Step 3: Implement simulator.py — core structure**

Key implementation:

```python
# replay_parser/simulator.py
"""Tier 2 game state simulator — walks clicks, tracks units/resources/supply."""

from replay_parser.models import (
    ReplayData, Turn, Action, UnitInstance, CardDef, ResourcePool
)
from replay_parser.resources import parse_resource_string
import copy
import logging

logger = logging.getLogger(__name__)

# Drone supply asymmetry: P0=21, P1=20. All others symmetric.
DRONE_SUPPLY = {0: 21, 1: 20}


class SimState:
    """Mutable simulation state."""

    def __init__(self, replay: ReplayData):
        self.replay = replay
        self.card_defs_by_name: dict[str, CardDef] = {
            cd.name: cd for cd in replay.card_defs
        }
        # Per-player unit rosters: instance_id → UnitInstance
        self.units: dict[int, UnitInstance] = {}
        self.next_instance_id = 0
        # Shared supply: deck_index → remaining
        self.supply: dict[int, int] = {}
        # Per-player Drone supply override
        self.drone_supply: dict[int, int] = dict(DRONE_SUPPLY)
        # Per-player resources
        self.resources: list[ResourcePool] = [ResourcePool(), ResourcePool()]

        self._init_supply()
        self._init_units()

    def _init_supply(self):
        for cd in self.replay.card_defs:
            self.supply[cd.deck_index] = cd.supply

    def _init_units(self):
        for player, player_init in enumerate(self.replay.init_cards):
            for count, name in player_init:
                cd = self.card_defs_by_name[name]
                for _ in range(count):
                    uid = self.next_instance_id
                    self.next_instance_id += 1
                    self.units[uid] = UnitInstance(
                        instance_id=uid, card_def=cd, owner=player,
                        turns_until_ready=0, is_alive=True,
                        used_ability_this_turn=False
                    )

    def get_supply(self, deck_index: int, player: int) -> int:
        """Get remaining supply for a card, handling Drone asymmetry."""
        cd = self.replay.card_defs[deck_index]
        if cd.name == "Drone":
            return self.drone_supply[player]
        return self.supply[deck_index]

    def decrement_supply(self, deck_index: int, player: int):
        cd = self.replay.card_defs[deck_index]
        if cd.name == "Drone":
            self.drone_supply[player] -= 1
        else:
            self.supply[deck_index] -= 1


def simulate(replay: ReplayData) -> None:
    """Process all clicks and populate replay.turns in-place."""
    state = SimState(replay)
    command_info = replay._command_info
    command_list = command_info["commandList"]
    clicks_per_turn = command_info["clicksPerTurn"]

    click_offset = 0
    for global_turn, click_count in enumerate(clicks_per_turn):
        player = global_turn % 2
        player_turn = global_turn // 2 + 1
        turn_clicks = command_list[click_offset:click_offset + click_count]
        click_offset += click_count

        turn = _process_turn(state, global_turn, player, player_turn, turn_clicks)
        replay.turns.append(turn)


def _process_turn(state, global_turn, player, player_turn, clicks):
    """Process one player-turn's clicks."""
    # 1. Credit passive income (BEFORE advancing construction —
    #    units that finish building this turn do NOT produce income yet)
    _credit_passive_income(state, player)

    # 2. Advance construction (units reaching 0 become ready next turn)
    _advance_construction(state, player)

    # 3. Snapshot resources at start
    resources_at_start = copy.copy(state.resources[player])

    # 4. Snapshot units owned at start of turn
    units_owned = _count_units(state, player)

    # 5. Process clicks
    actions = []
    buys = []
    abilities_used = []
    space_count = 0  # Phase tracking

    for click in clicks:
        click_type = click["_type"]
        click_id = click["_id"]

        # Skip emotes
        if click_type.startswith("emote"):
            continue

        if click_type == "space clicked":
            space_count += 1
            actions.append(Action(
                action_type="commit", unit_name=None,
                deck_index=None, instance_id=None,
                quantity=1, raw_click=click
            ))

        elif click_type == "end swipe processed":
            actions.append(Action(
                action_type="end_swipe", unit_name=None,
                deck_index=None, instance_id=None,
                quantity=1, raw_click=click
            ))

        elif click_type in ("inst clicked", "inst shift clicked"):
            if space_count == 0:
                # Defense phase — blocker assignment
                actions.append(Action(
                    action_type="defend", unit_name=_instance_name(state, click_id),
                    deck_index=None, instance_id=click_id,
                    quantity=1, raw_click=click
                ))
            else:
                # Action phase — ability activation
                is_shift = "shift" in click_type
                _process_ability(state, player, click_id, is_shift,
                                actions, abilities_used, click)

        elif click_type in ("card clicked", "card shift clicked"):
            is_shift = "shift" in click_type
            _process_buy(state, player, click_id, is_shift,
                        actions, buys, click)

        elif click_type == "undo clicked":
            actions.append(Action(
                action_type="undo", unit_name=None,
                deck_index=None, instance_id=None,
                quantity=1, raw_click=click
            ))
            # Undo handling: see Task 6

        elif click_type == "revert clicked":
            actions.append(Action(
                action_type="revert", unit_name=None,
                deck_index=None, instance_id=None,
                quantity=1, raw_click=click
            ))
            # Revert handling: see Task 6

        elif click_type == "cancel target processed":
            actions.append(Action(
                action_type="cancel_target", unit_name=None,
                deck_index=None, instance_id=None,
                quantity=1, raw_click=click
            ))

    # 6. Snapshot resources after
    resources_after = copy.copy(state.resources[player])

    # 7. Reset per-turn flags
    for unit in state.units.values():
        if unit.owner == player:
            unit.used_ability_this_turn = False

    return Turn(
        global_turn=global_turn, player=player,
        player_turn=player_turn, actions=actions,
        buys=buys, abilities_used=abilities_used,
        resources_at_start=resources_at_start,
        resources_after=resources_after,
        units_owned=units_owned  # Start-of-turn state (before buys)
    )
```

Also implement the helper functions:
- `_advance_construction(state, player)`: Decrement `turns_until_ready` for all this player's constructing units.
- `_credit_passive_income(state, player)`: For each ready, alive unit owned by player, credit `begin_turn_receive`.
- `_count_units(state, player)`: Return `dict[str, int]` of unit name → count for alive units.
- `_instance_name(state, instance_id)`: Look up instance → card_def.name. Return "unknown" if not found.
- `_process_ability(state, player, instance_id, is_shift, actions, abilities_used, raw_click)`: Credit ability receive. Handle shift (find all same-type units). Handle selfsac.
- `_process_buy(state, player, deck_index, is_shift, actions, buys, raw_click)`: Check supply and affordability. Deduct cost and supply. Create new UnitInstance. For shift-buys, loop until can't afford or no supply.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_simulator.py -v`
Expected: All PASS (or skip if replay absent).

- [ ] **Step 5: Commit**

```bash
git add replay_parser/simulator.py replay_parser/tests/test_simulator.py
git commit -m "feat(replay_parser): add Tier 2 simulator with resource tracking"
```

---

## Task 6: Simulator — Undo/Revert & Edge Cases

**Files:**
- Modify: `replay_parser/simulator.py`
- Modify: `replay_parser/tests/test_simulator.py`

- [ ] **Step 1: Write tests for undo/revert and edge cases**

Add to `test_simulator.py`:

```python
def test_simulate_no_crash_on_full_replay():
    """Simulator should process all 23 turns without errors."""
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    assert len(replay.turns) == 23
    # No negative supply
    # (internal check — access state if exposed, or validate turns)
    for turn in replay.turns:
        for name, count in turn.units_owned.items():
            assert count >= 0, f"Negative unit count: {name}={count} at turn {turn.global_turn}"

def test_simulate_emotes_ignored():
    """Emote clicks should not produce actions."""
    raw = load_replay(TEST_REPLAY_PATH)
    replay = decode(raw)
    simulate(replay)
    # Turn 1 has emotes — they should be skipped
    t1 = replay.turns[1]
    for action in t1.actions:
        assert not action.action_type.startswith("emote")
```

- [ ] **Step 2: Implement undo/revert in simulator.py**

Undo/revert strategy for Tier 2 parser:

**Approach**: Rather than maintaining a full rollback stack, use a simpler strategy:
1. **First pass**: Identify undo/revert clicks in the turn
2. **Second pass**: Remove undone actions — an `undo clicked` cancels the most recent non-undo action; `revert clicked` cancels ALL prior actions in the turn
3. **Third pass**: Process only the surviving clicks through the state machine

This is implemented as a preprocessing step in `_process_turn()` before the main click loop. The `_preprocess_clicks(clicks)` function returns a filtered click list with undo/revert pairs removed.

For `revert clicked`: discard all clicks before the revert (player started over). Keep clicks after the revert.

For `undo clicked`: discard the most recent actionable click (card/inst click). If multiple undos appear in sequence, each removes one more.

The filtered clicks then go through the normal processing pipeline.

- [ ] **Step 3: Run full test suite**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/ -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add replay_parser/simulator.py replay_parser/tests/test_simulator.py
git commit -m "feat(replay_parser): add undo/revert handling and edge case tests"
```

---

## Task 7: Database Schema & Migration

**Files:**
- Create: `replay_parser/database.py`
- Create: `replay_parser/tests/test_database.py`

- [ ] **Step 1: Write database tests**

```python
# replay_parser/tests/test_database.py
import sqlite3
from replay_parser.database import migrate, store, SCHEMA_VERSION
from replay_parser.models import (
    ReplayData, Turn, Action, ResourcePool, CardDef
)

def test_migrate_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "replay_parse_status" in tables
    assert "turn_actions" in tables
    assert "turn_state" in tables
    assert "turn_buys" in tables
    conn.close()

def test_migrate_sets_version(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    version = conn.execute(
        "SELECT value FROM db_meta WHERE key='parser_schema_version'"
    ).fetchone()[0]
    assert version == str(SCHEMA_VERSION)
    conn.close()

def test_migrate_idempotent(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    migrate(conn)  # Should not error
    conn.close()

def test_store_and_query(temp_db):
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    # Insert a dummy replay into replays table first
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating) "
        "VALUES (?, ?, ?, ?)",
        ("TEST001", 0, 1, 1600.0)
    )
    # Create minimal ReplayData
    replay = _make_test_replay("TEST001")
    store(conn, replay)

    # Verify parse status
    row = conn.execute(
        "SELECT parsed, total_turns FROM replay_parse_status WHERE code='TEST001'"
    ).fetchone()
    assert row[0] == 1
    assert row[1] == 2

    # Verify turn_buys
    buys = conn.execute(
        "SELECT buy_sequence, buy_hash FROM turn_buys WHERE code='TEST001' ORDER BY global_turn"
    ).fetchall()
    assert len(buys) == 2

    conn.close()

def _make_test_replay(code):
    """Create a minimal ReplayData for testing DB storage."""
    drone_def = CardDef(
        deck_index=5, name="Drone", rarity="trinket",
        buy_cost=ResourcePool(gold=3, energy=1), toughness=1,
        build_time=0, is_base_set=True, default_blocking=True,
        begin_turn_receive=None, ability_receive=ResourcePool(gold=1),
        ability_selfsac=False, ability_create=None,
        target_action=None, supply=20
    )
    t0 = Turn(
        global_turn=0, player=0, player_turn=1,
        actions=[], buys=["Drone", "Drone"],
        abilities_used=["Drone"],
        resources_at_start=ResourcePool(energy=2),
        resources_after=ResourcePool(),
        units_owned={"Drone": 8, "Engineer": 2}
    )
    t1 = Turn(
        global_turn=1, player=1, player_turn=1,
        actions=[], buys=["Drone", "Drone"],
        abilities_used=["Drone"],
        resources_at_start=ResourcePool(energy=2),
        resources_after=ResourcePool(),
        units_owned={"Drone": 9, "Engineer": 2}
    )
    return ReplayData(
        code=code, result=0, card_defs=[drone_def],
        randomizer=[], init_cards=[[(6, "Drone"), (2, "Engineer")],
                                    [(7, "Drone"), (2, "Engineer")]],
        turns=[t0, t1], total_global_turns=2,
        start_time=None, player_names=["Alice", "Bob"]
    )
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_database.py -v`
Expected: FAIL — `database.py` doesn't exist.

- [ ] **Step 3: Implement database.py**

Key functions:
- `SCHEMA_VERSION = 1`
- `migrate(conn)`: Check `db_meta` for `parser_schema_version`. If < SCHEMA_VERSION, run migration SQL (CREATE TABLE IF NOT EXISTS for all 4 tables + indexes). Update version.
- `store(conn, replay: ReplayData)`: INSERT into `replay_parse_status`, `turn_actions`, `turn_state`, `turn_buys`. Use `executemany` for turn rows. Compute `buy_hash` as sorted comma-joined buy names. Compute `total_units` as sum of `units_owned` values. Store `units_owned` as JSON string. Store `buy_sequence` as JSON array string.
- Wrap per-replay inserts in a transaction (BEGIN/COMMIT per replay for atomicity).

Schema DDL is taken directly from spec Section 5.1 and 5.2.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_database.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add replay_parser/database.py replay_parser/tests/test_database.py
git commit -m "feat(replay_parser): add database schema migration and storage"
```

---

## Task 8: S3 Fetch Module

**Files:**
- Create: `replay_parser/fetch.py`
- Create: `replay_parser/tests/test_fetch.py`

- [ ] **Step 1: Write fetch tests**

```python
# replay_parser/tests/test_fetch.py
from replay_parser.fetch import code_to_filename, code_to_s3_url

def test_code_to_filename_simple():
    assert code_to_filename("ABC-DEF") == "ABC-DEF.json.gz"

def test_code_to_filename_special_chars():
    assert code_to_filename("++A4h-1QDmB") == "++A4h-1QDmB.json.gz"

def test_code_to_s3_url_encodes_plus():
    url = code_to_s3_url("a+b")
    assert "%2B" in url

def test_code_to_s3_url_encodes_at():
    url = code_to_s3_url("a@b")
    assert "%40" in url

def test_code_to_s3_url_base():
    url = code_to_s3_url("simple")
    assert url.startswith("http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/")
    assert url.endswith(".json.gz")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_fetch.py -v`

- [ ] **Step 3: Implement fetch.py**

```python
# replay_parser/fetch.py
"""Fetch replays from S3."""
import gzip
import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

S3_BASE = "http://saved-games-alpha.s3-website-us-east-1.amazonaws.com"

def code_to_filename(code: str) -> str:
    return f"{code}.json.gz"

def code_to_s3_url(code: str) -> str:
    encoded = code.replace("+", "%2B").replace("@", "%40")
    return f"{S3_BASE}/{encoded}.json.gz"

def fetch_replay(code: str, output_dir: Path) -> Path:
    """Download a replay from S3 to output_dir. Returns path to saved file."""
    url = code_to_s3_url(code)
    filename = code_to_filename(code)
    output_path = output_dir / filename
    if output_path.exists():
        logger.debug(f"Already exists: {output_path}")
        return output_path
    logger.info(f"Fetching {code} from S3...")
    urllib.request.urlretrieve(url, str(output_path))
    return output_path
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_fetch.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add replay_parser/fetch.py replay_parser/tests/test_fetch.py
git commit -m "feat(replay_parser): add S3 replay fetch module"
```

---

## Task 9: Pipeline Orchestrator & CLI

**Files:**
- Create: `replay_parser/pipeline.py`
- Create: `replay_parser/__main__.py`
- Create: `replay_parser/tests/test_pipeline.py`

- [ ] **Step 1: Write pipeline tests**

```python
# replay_parser/tests/test_pipeline.py
import sqlite3
import os
from replay_parser.pipeline import run_pipeline
from replay_parser.database import migrate
from replay_parser.tests.conftest import TEST_REPLAY_CODE, REPLAYS_ARCHIVE, TEST_REPLAY_PATH
import pytest

needs_replay = pytest.mark.skipif(
    not os.path.exists(TEST_REPLAY_PATH),
    reason="Test replay not found"
)

@needs_replay
def test_pipeline_single_replay(temp_db):
    """Parse a single replay end-to-end."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    # Insert a dummy replays row for the test replay
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()

    stats = run_pipeline(
        db_path=temp_db,
        replays_dir=REPLAYS_ARCHIVE,
        codes=[TEST_REPLAY_CODE]
    )
    assert stats["parsed"] == 1
    assert stats["errors"] == 0

    # Verify data was stored
    turns = conn.execute(
        "SELECT COUNT(*) FROM turn_buys WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert turns > 0

    # Verify parse status
    parsed = conn.execute(
        "SELECT parsed FROM replay_parse_status WHERE code=?", (TEST_REPLAY_CODE,)
    ).fetchone()[0]
    assert parsed == 1
    conn.close()

@needs_replay
def test_pipeline_incremental(temp_db):
    """Second run should skip already-parsed replays."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()

    stats1 = run_pipeline(db_path=temp_db, replays_dir=REPLAYS_ARCHIVE,
                          codes=[TEST_REPLAY_CODE])
    stats2 = run_pipeline(db_path=temp_db, replays_dir=REPLAYS_ARCHIVE,
                          codes=[TEST_REPLAY_CODE])
    assert stats1["parsed"] == 1
    assert stats2["skipped"] == 1
    assert stats2["parsed"] == 0
    conn.close()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_pipeline.py -v`

- [ ] **Step 3: Implement pipeline.py**

```python
# replay_parser/pipeline.py
"""Orchestrator: fetch → decode → simulate → store."""
import sqlite3
import logging
from pathlib import Path
from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate
from replay_parser.database import migrate, store
from replay_parser.fetch import code_to_filename

logger = logging.getLogger(__name__)

def run_pipeline(
    db_path: str,
    replays_dir: str,
    codes: list[str] | None = None,
    force: bool = False,
    fetch: bool = False,
    batch_size: int = 1000,
) -> dict:
    """Run the parse pipeline. Returns stats dict."""
    conn = sqlite3.connect(db_path)
    migrate(conn)

    if codes is None:
        # Query eligible unparsed replays
        codes = _get_eligible_codes(conn, force)
    elif not force:
        # Filter out already-parsed codes
        codes = _filter_unparsed(conn, codes)

    stats = {"parsed": 0, "skipped": 0, "errors": 0, "fetched": 0, "total": len(codes)}
    replays_path = Path(replays_dir)

    # Fetch missing replays from S3 if requested
    if fetch and codes:
        from replay_parser.fetch import fetch_replay, code_to_filename
        for code in codes:
            if not (replays_path / code_to_filename(code)).exists():
                try:
                    fetch_replay(code, replays_path)
                    stats["fetched"] += 1
                except Exception as e:
                    logger.warning(f"Failed to fetch {code}: {e}")

    for i, code in enumerate(codes):
        try:
            filename = code_to_filename(code)
            filepath = replays_path / filename
            if not filepath.exists():
                logger.warning(f"File not found for {code}: {filepath}")
                _mark_error(conn, code, f"File not found: {filepath}")
                stats["errors"] += 1
                continue

            raw = load_replay(str(filepath))
            replay = decode(raw)
            simulate(replay)
            store(conn, replay)
            stats["parsed"] += 1

            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.info(f"Progress: {i+1}/{len(codes)}")
        except Exception as e:
            logger.warning(f"Error parsing {code}: {e}")
            _mark_error(conn, code, str(e))
            stats["errors"] += 1

    conn.commit()
    conn.close()

    logger.info(
        f"Done: {stats['parsed']} parsed, {stats['skipped']} skipped, "
        f"{stats['errors']} errors out of {stats['total']}"
    )
    return stats
```

Also implement `_get_eligible_codes(conn, force)`, `_filter_unparsed(conn, codes)`, `_mark_error(conn, code, msg)`.

- [ ] **Step 4: Implement __main__.py**

```python
# replay_parser/__main__.py
"""CLI entry point: python -m replay_parser"""
import argparse
import logging
import json
import sys
from pathlib import Path
from replay_parser.pipeline import run_pipeline
from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate

def main():
    parser = argparse.ArgumentParser(
        description="Prismata replay parser — extract game data into SQLite"
    )
    parser.add_argument("--db", help="Path to replays.db")
    parser.add_argument("--replays-dir", help="Path to replays archive directory")
    parser.add_argument("--codes", help="Comma-separated replay codes to parse")
    parser.add_argument("--codes-file", help="File containing replay codes (one per line)")
    parser.add_argument("--replay", help="Parse single replay file, output to stdout")
    parser.add_argument("--json", action="store_true", help="Output as JSON (with --replay)")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing replays from S3 before parsing")
    parser.add_argument("--force", action="store_true", help="Re-parse already-parsed replays")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    # Single replay mode (no DB)
    if args.replay:
        raw = load_replay(args.replay)
        replay = decode(raw)
        simulate(replay)
        if args.json:
            _print_replay_json(replay)
        else:
            _print_replay_summary(replay)
        return

    # Pipeline mode (requires DB)
    if not args.db:
        parser.error("--db is required for pipeline mode")
    if not args.replays_dir:
        parser.error("--replays-dir is required for pipeline mode")

    codes = None
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    elif args.codes_file:
        codes = Path(args.codes_file).read_text().strip().splitlines()

    stats = run_pipeline(
        db_path=args.db,
        replays_dir=args.replays_dir,
        codes=codes,
        force=args.force,
        fetch=args.fetch,
    )
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
```

Also implement `_print_replay_json(replay)` and `_print_replay_summary(replay)` helper functions.

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/test_pipeline.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add replay_parser/pipeline.py replay_parser/__main__.py replay_parser/tests/test_pipeline.py
git commit -m "feat(replay_parser): add pipeline orchestrator and CLI"
```

---

## Task 10: Integration Test — Full Parse of Test Replay

**Files:**
- Modify: `replay_parser/tests/test_pipeline.py`

End-to-end validation using the known test replay.

- [ ] **Step 1: Write integration test**

Add to `test_pipeline.py`:

```python
@needs_replay
def test_full_parse_validates_opening(temp_db):
    """Validate parsed data against known game state."""
    conn = sqlite3.connect(temp_db)
    migrate(conn)
    conn.execute(
        "INSERT INTO replays (code, result, balance_passed, min_rating, p1_rating, p2_rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (TEST_REPLAY_CODE, 1, 1, 1600.0, 1700.0, 1600.0)
    )
    conn.commit()

    run_pipeline(db_path=temp_db, replays_dir=REPLAYS_ARCHIVE,
                 codes=[TEST_REPLAY_CODE])

    # P0 turn 1 state should be 6 Drone + 2 Engineer
    row = conn.execute(
        "SELECT units_owned, gold, energy FROM turn_state "
        "WHERE code=? AND global_turn=0",
        (TEST_REPLAY_CODE,)
    ).fetchone()
    import json as json_mod
    units = json_mod.loads(row[0])
    assert units.get("Drone") == 6  # Starting units (before buys this turn are reflected in units_owned_after)

    # P0 turn 0 buys should include Drone
    buy_row = conn.execute(
        "SELECT buy_sequence FROM turn_buys WHERE code=? AND global_turn=0",
        (TEST_REPLAY_CODE,)
    ).fetchone()
    buy_seq = json_mod.loads(buy_row[0])
    assert "Drone" in buy_seq

    # P0 turn 2 buys should include Drone and Engineer
    buy_row2 = conn.execute(
        "SELECT buy_sequence FROM turn_buys WHERE code=? AND global_turn=2",
        (TEST_REPLAY_CODE,)
    ).fetchone()
    buy_seq2 = json_mod.loads(buy_row2[0])
    assert "Drone" in buy_seq2
    assert "Engineer" in buy_seq2

    conn.close()
```

- [ ] **Step 2: Run all tests**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Manual CLI test**

```bash
cd c:/libraries/PrismataAI
python -m replay_parser --replay c:/libraries/prismata-replay-parser/replays_archive/++A4h-1QDmB.json.gz --json
```

Expected: JSON output showing all turns with buys, abilities, resources.

- [ ] **Step 4: Commit**

```bash
git add replay_parser/tests/test_pipeline.py
git commit -m "test(replay_parser): add integration test for full replay parse"
```

---

## Task 11: Bulk Parse — All 102k Replays

**Files:** No new files — uses CLI built in Task 9.

- [ ] **Step 1: Back up the database**

```bash
cp c:/libraries/prismata-replay-parser/replays.db c:/libraries/prismata-replay-parser/replays.db.bak.20260318
```

- [ ] **Step 2: Run full parse**

```bash
cd c:/libraries/PrismataAI
PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 python -m replay_parser \
    --db c:/libraries/prismata-replay-parser/replays.db \
    --replays-dir c:/libraries/prismata-replay-parser/replays_archive/ \
    -v
```

Expected: ~102k replays parsed in 2-10 minutes. Monitor for errors. Some replays may fail (abandoned/corrupt games) — that's expected.

- [ ] **Step 3: Run bulk consistency checks**

```bash
cd c:/libraries/PrismataAI && python -c "
import sqlite3, json
conn = sqlite3.connect('c:/libraries/prismata-replay-parser/replays.db')

# Total parsed
parsed = conn.execute('SELECT COUNT(*) FROM replay_parse_status WHERE parsed=1').fetchone()[0]
errors = conn.execute('SELECT COUNT(*) FROM replay_parse_status WHERE error IS NOT NULL').fetchone()[0]
print(f'Parsed: {parsed}, Errors: {errors}')

# P0 turn 1 state should always be 6D+2E
wrong_p0 = conn.execute('''
    SELECT COUNT(*) FROM turn_state
    WHERE player=0 AND player_turn=1
    AND (json_extract(units_owned, \"$.Drone\") != 6
         OR json_extract(units_owned, \"$.Engineer\") != 2)
''').fetchone()[0]
print(f'P0 turn 1 wrong starting state: {wrong_p0}')

# P1 turn 1 state should always be 7D+2E
wrong_p1 = conn.execute('''
    SELECT COUNT(*) FROM turn_state
    WHERE player=1 AND player_turn=1
    AND (json_extract(units_owned, \"$.Drone\") != 7
         OR json_extract(units_owned, \"$.Engineer\") != 2)
''').fetchone()[0]
print(f'P1 turn 1 wrong starting state: {wrong_p1}')

# No negative resources
neg_res = conn.execute('''
    SELECT COUNT(*) FROM turn_state
    WHERE gold < 0 OR green < 0 OR blue < 0 OR red < 0 OR energy < 0
''').fetchone()[0]
print(f'Negative resource states: {neg_res}')
"
```

Expected: 0 wrong starting states. Very few (ideally 0) negative resources.

- [ ] **Step 4: Run a sample analysis query**

```bash
cd c:/libraries/PrismataAI && python -c "
import sqlite3
conn = sqlite3.connect('c:/libraries/prismata-replay-parser/replays.db')
print('Top P0 turn-1 buys (1500+ games):')
for row in conn.execute('''
    SELECT tb.buy_sequence, COUNT(*) as freq,
           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
    FROM turn_buys tb
    JOIN replays r ON tb.code = r.code
    WHERE tb.player = 0 AND tb.player_turn = 1
      AND r.min_rating >= 1500 AND r.balance_passed = 1
    GROUP BY tb.buy_sequence
    ORDER BY freq DESC
    LIMIT 10
''').fetchall():
    print(f'  {row[0]}: {row[1]} ({row[2]}%)')
"
```

- [ ] **Step 5: Commit any fixes from bulk parse**

If the bulk parse revealed bugs, fix and re-run. Commit fixes.

```bash
git add -A replay_parser/
git commit -m "fix(replay_parser): fixes from bulk parse validation"
```

---

## Task 12: Documentation & Cleanup

**Files:**
- Modify: `replay_parser/__init__.py` — finalize public API exports

- [ ] **Step 1: Add public API exports to __init__.py**

```python
# replay_parser/__init__.py
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
```

- [ ] **Step 2: Final test suite run**

Run: `cd c:/libraries/PrismataAI && python -m pytest replay_parser/tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add replay_parser/__init__.py
git commit -m "feat(replay_parser): finalize public API exports"
```
