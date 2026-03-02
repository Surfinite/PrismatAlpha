# --suggest Click Protocol Specification

## Overview

The `--suggest` CLI mode allows the JS matchup code to request AI move suggestions from the C++ engine. The C++ process reads a game state JSON file, runs AI search, and outputs a JSON response with the recommended actions encoded as clicks.

## Usage

```bash
Prismata_Testing.exe --suggest <state_file> [--player <name>] [--think-time <ms>]
```

- `<state_file>` — Path to a JSON file containing the game state
- `--player` — AI player name from config.txt (default: `HardestAI`)
- `--think-time` — Search time limit in milliseconds (default: 3000)

## Input: State JSON

### Bare Format (standard for matchup code)

The state JSON is produced by the JS engine's `state_adapter.js`. It contains `mergedDeck` (card definitions), `cards` (instances on the board), `resources`, phase info, etc.

The key fields the C++ engine reads:
- `mergedDeck` — Array of card type definitions (name, cost, stats)
- `cards` — Array of card instances with `instId`, `cardName`, `owner`, status fields
- `resources` — Per-player resource counts
- `turnNumber`, `activePlayer`, `phase`

### F6 Format (clipboard/debug)

Wraps the bare state in a `CurrentInfo` object:
```json
{"CurrentInfo": { ...bare state... }}
```

DoSuggest handles both formats — it detects the `CurrentInfo` wrapper automatically.

## Output: JSON Response

### Success Response

```json
{
  "ok": true,
  "eval": 0.4053,
  "eval_pct": "70%",
  "active_player": 0,
  "phase": "action",
  "buy": ["Drone", "Drone"],
  "abilities": ["Drone"],
  "defense": [],
  "breach": [],
  "clicks": [
    {"_type": "inst clicked", "_id": 0},
    {"_type": "card clicked", "_id": 0},
    {"_type": "card clicked", "_id": 0},
    {"_type": "space clicked", "_id": -1}
  ],
  "think_ms": 1006,
  "timing_ms": {"parse": 0, "eval": 0, "search": 1006},
  "full_move": "Player 0 Uses Ability of Card 0\n..."
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `ok` | bool | `true` if suggestion succeeded |
| `eval` | float | Raw neural net evaluation (0-1 scale, 0.5 = even) |
| `eval_pct` | string | Win probability as percentage string with `%` suffix (e.g., `"70%"`) |
| `active_player` | int | Player whose turn it is (0 or 1) |
| `phase` | string | Current game phase: `"action"`, `"defense"`, `"confirm"`, `"swoosh"` |
| `buy` | string[] | Display names of units to buy |
| `abilities` | string[] | Display names of units whose abilities to use |
| `defense` | string[] | Display names of units to assign as blockers |
| `breach` | string[] | Display names of units to target during breach |
| `clicks` | object[] | Ordered click sequence for the JS engine (see Click Types below) |
| `think_ms` | int | Total AI search time in milliseconds |
| `timing_ms` | object | Breakdown: `parse` (JSON parsing), `eval` (neural eval), `search` (AI search) |
| `full_move` | string | Human-readable move description (debug) |

### Error Response

```json
{"ok": false, "error": "Cannot read file: missing.json"}
```

## Click Types

Each click in the `clicks` array has `_type` (string) and `_id` (int).

### `"card clicked"` — BUY

- `_id` = index into the `mergedDeck` array (0-based)
- The JS engine looks up `mergedDeck[_id]` to determine which card type to buy
- Multiple clicks for the same `_id` = buy multiple copies

### `"inst clicked"` — USE_ABILITY / ASSIGN_BLOCKER / ASSIGN_FRONTLINE / BREACH

- `_id` = client instance ID (`instId` from the state JSON's `cards` array)
- Used for all instance-level actions: activating abilities, assigning blockers, frontline attacks, breach targets
- For **targeting abilities** (SNIPE/CHILL): two consecutive `inst clicked` entries — first is the source unit, second is the target

### `"space clicked"` — END_PHASE

- `_id` = -1 (always)
- Signals the end of the current phase
- **End-turn requires TWO `space clicked` entries**: one to enter confirm phase, one to commit the turn

### `"end swipe processed"` — END_TURN (alternative)

- `_id` = -1 (always)
- Alternative end-turn signal used in some contexts

## Multi-Instance Handling

The C++ engine **expands shift-flagged actions** into individual `inst clicked` entries. When the AI wants to use the ability of multiple units of the same type, the output contains one `inst clicked` per instance (each with its own `_id`). The JS engine receives and applies these sequentially — no shift-click handling needed on the JS side.

## Determinism

Same state + same player + same think-time produces the same output. The RNG is seeded with `time(NULL) ^ (PID << 4)`, so different processes at the same time produce different results, but a single invocation is deterministic.

## Stdout Considerations

- Init messages (card library loading, neural weight loading, config parsing) are redirected to stderr
- Only the JSON response goes to stdout
- **Known issue:** `PRISMATA_ASSERT` soft asserts may leak "Assertion thrown!" lines to stdout (e.g., opening book references to cards not in the current set). Consumers should find the line starting with `{` for the JSON response.

## Integration Pattern

The JS matchup code follows this loop:

```
for each turn:
  1. Export current JS engine state to JSON file (bare format)
  2. Spawn: Prismata_Testing.exe --suggest state.json --player <name> --think-time <ms>
  3. Parse JSON response from stdout (find line starting with '{')
  4. For each click in response.clicks:
     - Call analyzer.recordClick({_type: click._type, _id: click._id})
  5. Check state.gameover
```
