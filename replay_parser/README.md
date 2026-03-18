# Prismata Replay Parser

A Python library for parsing Prismata game replays. Extracts per-turn buy sequences, resource snapshots, unit counts, and action histories from `.json.gz` replay files.

## Quick Start

```python
from replay_parser.decoder import load_replay, decode
from replay_parser.simulator import simulate

replay = decode(load_replay("game.json.gz"))
simulate(replay)

for turn in replay.turns:
    player = "P1" if turn.player == 0 else "P2"
    buys = ", ".join(turn.buys) or "(none)"
    print(f"{player} turn {turn.player_turn}: {buys}")
```

## Installation

No external dependencies — stdlib only (Python 3.10+). Just clone the repo and import:

```bash
git clone https://github.com/Surfinite/PrismatAI.git
cd PrismatAI
python -c "from replay_parser.decoder import load_replay, decode; print('OK')"
```

Optional: `pip install tqdm` for progress bars during bulk parsing.

## CLI Usage

```bash
# Parse a single replay and print summary
python -m replay_parser --replay game.json.gz

# Parse a single replay as JSON (pipe to jq, etc.)
python -m replay_parser --replay game.json.gz --json

# Bulk parse into SQLite database
python -m replay_parser --db replays.db --replays-dir ./replays_archive/

# Parse specific replays by code
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ --codes "ABC123,DEF456"

# Re-parse all (ignore already-parsed flag)
python -m replay_parser --db replays.db --replays-dir ./replays_archive/ --force
```

## What You Get Per Turn

Each `Turn` object contains:

| Field | Type | Description |
|-------|------|-------------|
| `global_turn` | int | 0-indexed turn across both players |
| `player` | int | 0 = P1, 1 = P2 |
| `player_turn` | int | 1-indexed per player |
| `buys` | list[str] | Unit names bought this turn (net, after unbuys) |
| `abilities_used` | list[str] | Unit names whose abilities were activated |
| `units_owned` | dict[str, int] | Unit counts at start of turn (before buys) |
| `resources_at_start` | ResourcePool | Gold/green/blue/red/energy/attack at turn start |
| `resources_after` | ResourcePool | Resources remaining after all actions |
| `actions` | list[Action] | Full click-by-click action history |

## Accuracy

Cross-validated against the authoritative JS game engine on 500+ replays:

| Player Turn | Buy Accuracy |
|-------------|-------------|
| 1 | **99.9%** |
| 2 | **93%** |
| 3 | **91%** |
| 4 | 77% |
| 5 | 64% |

Game result and turn count match 100%.

**Turns 1-3 are highly reliable** for opening book analysis, consensus patterns, and statistical queries. Individual replays may occasionally have a wrong buy count at turn 2-3 due to resource tracking drift (see Limitations below).

## How It Works

The parser is a **Tier 2** click-level analyzer. It reads the replay's click sequence (`commandInfo.commandList`) and simulates game state by tracking:

- **Unit roster** — which units each player owns (instance ID mapping)
- **Resources** — gold, green, blue, red, energy, attack per player
- **Supply** — remaining purchasable units per card type
- **Phase** — defense vs action vs confirm, for correct click interpretation

It does NOT run the full game engine. Instead, it processes clicks sequentially and infers state changes from click types and card definitions in the replay's `mergedDeck`.

## Limitations

### Resource Tracking Drift (main accuracy limit)

The parser tracks resources approximately. Small errors compound across turns:

1. **Confirm-phase clicks** — When a player commits their action phase (space click) then changes their mind, the game engine internally undoes the commit. The parser detects the first such click and skips it, but complex undo-rebuy chains can cause the parser's resource state to diverge from the engine's exact state.

2. **Shift-click buy quantities** — `card shift clicked` buys "as many as affordable." If the parser's resource count is off by even 1 gold, the calculated quantity may differ from reality. This is the primary cause of buy mismatches at turns 3+.

3. **Combat deaths** — The parser doesn't simulate damage resolution. Units that die in combat remain in the parser's roster as alive, which can cause incorrect ability credits in later turns.

### Things the Parser Does NOT Track

- **Chill/freeze state** — Records targeting clicks but doesn't compute accumulated chill per unit
- **Damage and HP** — No combat simulation
- **Exact confirm-phase mechanics** — The game engine's undo stack (Controller.js:111-118) converts confirm-phase clicks to undos internally. The parser approximates this but can't perfectly reproduce it without the full engine state.

### Turn Boundary Edge Case

Some replays have emote clicks that consume `clicksPerTurn` slots, pushing buy/commit clicks into the next turn's slice. The parser detects and corrects this (iteratively steals clicks from the next turn until every turn has a commit), but in rare cases with many consecutive emote-heavy turns, alignment may still be off.

### Resource Decay

Only **gold and green** persist between turns. Blue, red, energy, and attack reset to zero at the start of each turn, then passive income (`beginOwnTurnScript`) re-adds them. The parser implements this correctly.

### Supply

Drone supply is asymmetric: P1 (player 0) has 21 buyable, P2 (player 1) has 20. All other units have symmetric supply derived from rarity (trinket=20, normal=10, rare=4, legendary=1). Starting units do NOT reduce shop supply.

## Replay JSON Structure

Replays are `.json.gz` files from the Prismata S3 archive. Key fields:

- `commandInfo.commandList` — flat array of all clicks: `{_type, _id}`
- `commandInfo.clicksPerTurn` — click count per turn (slices commandList)
- `deckInfo.mergedDeck` — card definitions (index = deck ID for buy clicks)
- `initInfo.initCards` — starting units per player
- `playerInfo[n].displayName` — player names
- `result` — 0 = P1 wins, 1 = P2 wins, 2 = draw

Click types: `card clicked` (buy), `card shift clicked` (shift-buy), `inst clicked` (ability/defend/unbuy), `inst shift clicked` (shift-ability/shift-unbuy), `space clicked` (commit), `end swipe processed` (animation), `emote*` (chat).

## Module Structure

| Module | Description |
|--------|-------------|
| `models.py` | Data classes (ResourcePool, CardDef, Turn, ReplayData, etc.) |
| `resources.py` | Parse resource strings ("3H" → 3 gold + 1 energy) |
| `decoder.py` | Load .json.gz, convert to structured ReplayData |
| `simulator.py` | Walk clicks, track state, populate turns |
| `database.py` | SQLite schema migration and storage |
| `fetch.py` | Download replays from S3 |
| `pipeline.py` | Orchestrator: fetch → decode → simulate → store |
| `cross_validate.py` | Compare Python parser against JS engine ground truth |

## Running Tests

```bash
cd PrismataAI
python -m pytest replay_parser/tests/ -v
```

Tests that require the replay archive (`c:/libraries/prismata-replay-parser/replays_archive/`) are skipped if the files aren't present.
