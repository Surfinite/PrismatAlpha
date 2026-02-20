# C++ Replay Ingestion & Analysis Mode -- Context Document

**Purpose:** This document provides all context needed to review [the implementation plan](2026-02-20-cpp-replay-mode.md) without prior knowledge of the codebase. It covers the game, the engine architecture, the replay format, the training pipeline, and the existing `--suggest` CLI mode that serves as the template for the new `--replay` mode.

---

## 1. What Is Prismata?

Prismata is a turn-based, perfect-information strategy card game (no hidden information, no RNG). Two players alternate turns buying units and attacking. Each turn has phases:

1. **Action Phase** -- activate abilities (tap units for resources, attack, special effects), then buy new units
2. **Breach Phase** -- if enemy defense is overwhelmed, choose which enemy units to destroy
3. **Confirm Phase** -- confirm breach targets
4. **Defense Phase** -- assign blockers against incoming attack
5. **Swoosh Phase** -- animations resolve, units construct, turn passes to opponent

The game has ~105 unique unit types. Each game uses a random subset of 8 "dominion" units plus ~11 base set units shared across all games.

**Targeting abilities** are two-step: click the source unit (USE_ABILITY), then click the enemy target (SNIPE or CHILL). The engine tracks this via a `m_targetAbilityCardClicked` flag on GameState.

## 2. The Problem We're Solving

### Current Training Pipeline

We train a neural network (value prediction) from game data. There are two data sources:

1. **Self-play data** (722K games) -- The C++ engine plays against itself, producing binary training shards directly. This works perfectly.
2. **Expert replay data** (32K replays from human players rated 2000+) -- Currently parsed by a **TypeScript replay parser** that simulates game state and extracts features.

### The TS Parser Failure Problem

The TS parser fails on **~44% of expert replays**. The failure modes are:

| Failure Type | Count | Description |
|---|---|---|
| USE_ABILITY | 276 | Complex ability resolution (multi-step, sac costs) |
| SNIPE | 173 | Two-step targeting not fully implemented |
| END_PHASE | 130 | Phase transition edge cases |
| BUY | 116 | Resource calculation mismatches |
| ASSIGN_BLOCKER | 58 | Defense assignment edge cases |
| Other | 96 | Redo (not implemented at all), undo state corruption |

**Critical insight from the user:** These aren't random failures -- they're *systematic*. The parser consistently fails on the same patterns (complex targeting, undo/redo, multi-step abilities). This means the training data has a systematic blind spot: the model never sees positions arising from exactly the complex plays that expert players use most.

### Partial Recovery (Already Implemented)

We modified the TS parser to save turns *before* the error point, recovering 2,653 additional training examples from 121 failed replays. This helps but doesn't fix the root cause.

### Proposed Solution

Build a C++ replay stepping mode that uses the **same engine** as self-play. The C++ engine is ground truth -- it already handles all of these cases correctly. A C++ `ReplayStepper` class would:
- Get near-100% extraction rate (vs 56% with TS parser)
- Output binary shards directly (same format as self-play, no JSONL intermediary)
- Serve as reusable infrastructure for analysis, opening books, and live game tools

## 3. Replay JSON Format

Replays are stored as gzipped JSON on S3. Here is the structure (simplified):

```json
{
  "deckInfo": {
    "mergedDeck": [
      { "UIName": "Drone", "buyCost": "3", "supply": 10, ... },
      { "UIName": "Engineer", "buyCost": "1G", "supply": 10, ... },
      { "UIName": "Tarsier", "buyCost": "4GG", "supply": 4, ... },
      ...
    ]
  },
  "initInfo": {
    "initCards": [...],
    "initResources": [...]
  },
  "commandInfo": {
    "commandList": [
      { "_type": "card clicked", "_id": 0 },
      { "_type": "card clicked", "_id": 0 },
      { "_type": "space clicked", "_id": -1 },
      { "_type": "card clicked", "_id": 0 },
      { "_type": "card clicked", "_id": 0 },
      { "_type": "card clicked", "_id": 0 },
      { "_type": "space clicked", "_id": -1 },
      { "_type": "inst clicked", "_id": 42 },
      { "_type": "inst clicked", "_id": 87 },
      { "_type": "revert clicked", "_id": -1 },
      { "_type": "redo clicked", "_id": -1 },
      ...
    ],
    "clicksPerTurn": [2, 3, 5, 4, ...]
  },
  "playerInfo": [
    { "name": "FlopFlop", "bot": false },
    { "name": "307th", "bot": false }
  ],
  "ratingInfo": {
    "finalRatings": [
      { "displayRating": 2214 },
      { "displayRating": 2198 }
    ]
  },
  "result": 1
}
```

### Click Types in `commandList`

| Click `_type` | `_id` Meaning | What It Does |
|---|---|---|
| `card clicked` | mergedDeck array index | Buy a unit |
| `card shift clicked` | mergedDeck array index | Shift-buy (buy all affordable copies) |
| `inst clicked` | Client instance ID | Use ability / assign blocker / assign breach (context-dependent) |
| `inst shift clicked` | Client instance ID | Shift-click (activate all units of same type) |
| `space clicked` | -1 | End current phase |
| `revert clicked` | -1 | Undo last action |
| `redo clicked` | -1 | Redo undone action |

### Key Complication: Two ID Systems

The replay uses **client IDs**. The engine uses **engine IDs**. They are different:

1. **mergedDeck index** (client) vs **CardBuyable index** (engine): The client's `mergedDeck` array is ordered by UI layout. The engine's buyable list is ordered by registration. A `card clicked` with `_id=5` means "buy the 6th card in mergedDeck", not "buy engine buyable #5".

2. **Client instId** (client) vs **CardID** (engine): The client assigns instance IDs (`instId`) when units are created. The engine assigns sequential `CardID`s. An `inst clicked` with `_id=42` means "the unit with client instId 42", not "engine CardID 42".

Both mappings must be maintained as the replay is stepped through.

## 4. Engine Architecture

### Core Types

```cpp
// Constants.h — Player IDs
namespace Players { enum { Player_One = 0, Player_Two = 1, Player_Both = 2, Player_None = 3 }; }

// Constants.h — Game Phases
namespace Phases { enum { Action, Defense, Breach, Confirm, Swoosh }; }

// Action.h — All possible action types
namespace ActionTypes {
    enum {
        USE_ABILITY,      // Activate a unit's ability
        BUY,              // Buy a unit from the supply
        END_PHASE,        // End the current phase
        ASSIGN_BLOCKER,   // Assign a unit to block during defense
        ASSIGN_BREACH,    // Assign breach target during breach
        ASSIGN_FRONTLINE, // Kill a frontline unit with leftover attack
        SNIPE,            // Target-kill an enemy unit (step 2 of targeting)
        CHILL,            // Freeze an enemy unit (step 2 of targeting)
        WIPEOUT,          // Auto-block when defense is overwhelming

        UNDO_USE_ABILITY, // Undo an ability activation
        UNDO_CHILL,       // Undo a chill
        UNDO_BREACH,      // Undo a breach assignment
        SELL,             // Sell back a just-bought unit
    };
}
```

### Action Class

```cpp
class Action {
    PlayerID m_player;    // Which player
    ActionID m_type;      // ActionTypes enum
    CardID   m_id;        // BUY: buyable index; USE_ABILITY/BLOCKER/BREACH: card ID
    CardID   m_targetID;  // SNIPE/CHILL: target card ID
    bool     m_shift;     // Shift-click (batch activate/buy)
public:
    Action(PlayerID player, ActionID type, CardID id = 0);
    Action(PlayerID player, ActionID type, CardID id, CardID target); // for SNIPE/CHILL
};
```

### GameState — Key Interface

```cpp
class GameState {
    // Internal state
    TurnType    m_turnNumber;
    PlayerID    m_activePlayer;
    int         m_activePhase;               // Phases::Action, Defense, Breach, etc.
    bool        m_targetAbilityCardClicked;   // True after clicking a targeting unit
    CardID      m_targetAbilityCardID;        // Which targeting unit was clicked
    bool        m_gameOver;

public:
    // Construction
    GameState();
    GameState(const rapidjson::Value & value);  // From JSON (F6 clipboard format)

    // Action execution
    bool isLegal(const Action & action) const;  // Validates action against all game rules
    bool doAction(const Action & action);        // Execute action, mutate state
    // WARNING: doAction() calls PRISMATA_ASSERT if action is illegal — crashes the process

    // State queries
    bool isGameOver() const;
    PlayerID getActivePlayer() const;
    int getActivePhase() const;
    TurnType getTurnNumber() const;
    bool isTargetAbilityCardClicked() const;     // Is a targeting ability pending?

    // Card queries
    const Card & getCardByID(CardID id) const;
    const CardBuyable & getCardBuyableByIndex(CardID index) const;
    const CardBuyable & getCardBuyableByID(CardID cardID) const;
};
```

**Critical: `doAction()` crashes on illegal actions.** It uses `PRISMATA_ASSERT(isLegal(action), ...)` which prints an error and continues (soft assert), but the state becomes corrupted. The ReplayStepper must always call `isLegal()` first and skip illegal actions gracefully.

### Card Class (Relevant Parts)

```cpp
class Card {
    CardType m_type;
    CardID   m_id;              // Engine-assigned sequential ID
    int      m_clientInstId;    // Client instId from F6 JSON (-1 if not set)
    // ... health, status, construction time, etc.
public:
    int getClientInstId() const;  // Returns -1 if not set (non-F6 states)
    CardID getID() const;
    const CardType getType() const;
    bool canUseAbility() const;
    bool hasTarget() const;       // True if this unit's targeting ability was used
    bool isDead() const;
};
```

The `m_clientInstId` field was added recently specifically to support protocol integration. It stores the instId from F6 clipboard JSON but is only populated when loading from that format. For replay stepping, new instIds must be assigned as cards are created.

### Card Initialization from mergedDeck

```cpp
// Used in --suggest mode and needed for --replay mode
Prismata::InitFromMergedDeckJSON(mergedDeck);  // Registers all card types from the replay's deck
NeuralNet::Instance().buildCardTypeMapping();   // Rebuilds the feature extraction mapping
```

This is critical: each game uses a different subset of units. The engine must be re-initialized with the specific game's `mergedDeck` before processing.

## 5. The `isLegal()` Validation Logic

The engine validates actions based on current phase and game state:

```
isLegal(BUY)            — Must be Action phase, have resources, have supply remaining
isLegal(USE_ABILITY)    — Must be Action phase, card alive, can use ability, no target pending
isLegal(SNIPE/CHILL)    — Must have target pending (isTargetAbilityCardClicked), target alive
isLegal(END_PHASE)      — Phase-dependent: always OK in Action, needs 0 attack in Defense, etc.
isLegal(ASSIGN_BLOCKER) — Must be Defense phase, card can block
isLegal(ASSIGN_BREACH)  — Must be Breach phase, card is breachable
```

The `isTargetAbilityCardClicked()` check is important: SNIPE/CHILL actions are only legal *after* a USE_ABILITY on a targeting unit has set the `m_targetAbilityCardClicked` flag. This is the two-step targeting system.

## 6. Existing `--suggest` CLI Mode (Template for `--replay`)

The `--suggest` mode reads a game state JSON, runs the AI, and outputs a suggested move. It demonstrates all the patterns needed:

### Entry Point (main.cpp)

```cpp
// Early stdout redirection (prevent init noise in JSON output)
if (isSuggestMode) {
    fflush(stdout);
    savedStdout = _dup(_fileno(stdout));
    _dup2(_fileno(stderr), _fileno(stdout));
}

// Standard initialization
Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");
NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin");
NeuralNet::Instance().buildCardTypeMapping();
AIParameters::Instance().parseFile(configDir + "config.txt");

// Restore stdout, dispatch to handler
if (!suggestFile.empty()) {
    Benchmarks::DoSuggest(suggestFile, suggestPlayer, suggestThinkTime);
}
```

### DoSuggest Implementation (Benchmarks.cpp, 235 lines)

The function follows this flow:
1. Read JSON file with `std::ifstream` (not `FileUtils` — avoids stdout noise)
2. Parse with `rapidjson::Document`
3. Unwrap `CurrentInfo` wrapper if present (F6 clipboard format)
4. Call `Prismata::InitFromMergedDeckJSON(mergedDeck)` to register card types
5. Construct `GameState` from the JSON
6. Run neural evaluation: `NeuralNet::Instance().evaluate(state)`
7. Run AI search: `player->getMove(state, move)`
8. Build click array from the Move (maps engine IDs back to client protocol)
9. Output JSON to stdout

### Click Generation (Reverse Mapping)

The existing `--suggest` mode already solves the **reverse** of what `--replay` needs:

```
--suggest: Engine Action → Client Click (for protocol injection)
  BUY action with CardType ID → "card clicked" with mergedDeck index (ID - 2)
  USE_ABILITY with CardID → "inst clicked" with Card.getClientInstId()

--replay: Client Click → Engine Action (the inverse)
  "card clicked" with mergedDeck index → BUY action with buyable index
  "inst clicked" with client instId → USE_ABILITY/BLOCKER/BREACH with CardID
```

The `--suggest` click generation code (lines 941-1011 of Benchmarks.cpp) is the reference for this reverse mapping.

## 7. Training Data Pipeline (SelfPlayDataSink)

### Interface

```cpp
class IDataSink {
public:
    virtual void onTurnStart(const GameState & state) {}  // Called before AI acts
    virtual void onGameEnd(PlayerID winner) {}             // Called when game ends
    virtual void finalize() {}                             // Called after all games
};
```

### SelfPlayDataSink Implementation

```cpp
class SelfPlayDataSink : public IDataSink {
public:
    SelfPlayDataSink(int threadIndex, const std::string & outputDir,
                     std::atomic<uint32_t> & globalGameCounter,
                     uint32_t featureDim = 1785);

    void onTurnStart(const GameState & state) override;   // Extract features, accumulate
    void onGameEnd(PlayerID winner) override;              // Label all turns, write to shard
    void finalize() override;                              // Write CRC footer
};
```

**`onTurnStart()`**: Calls `NeuralNet::Instance().extractFeatures(state, features)` to convert the GameState into a 1785-dimensional float vector. Stores in a pending record list.

**`onGameEnd()`**: Labels all pending records with the outcome (+1 = this player won, -1 = lost, 0 = draw). Writes all records to the binary shard file.

### Binary Shard Format

```
[Header: 64 bytes]
  Magic:        0x50534450 ("PSDP")
  Version:      1
  FeatureDim:   1785
  RecordSize:   7152 bytes
  RecordCount:  (updated on finalize; sentinel 0xFFFFFFFF... while writing)
  EndianCheck:  0x01020304

[Records: RecordSize bytes each]
  features:     1785 x float32 = 7140 bytes
  outcome:      float32 = 4 bytes
  game_id:      uint32 = 4 bytes
  turn_number:  uint16 = 2 bytes
  player_index: uint8 = 1 byte
  flags:        uint8 = 1 byte

[Footer: 4 bytes]
  CRC32:        IEEE 802.3 polynomial
```

### How It's Used in Self-Play (TournamentGame.cpp)

```cpp
void TournamentGame::playGame() {
    while (!_game.gameOver()) {
        PlayerID playerToMove = _game.getState().getActivePlayer();

        // Hook: capture state BEFORE AI acts
        if (_dataSink) {
            _dataSink->onTurnStart(_game.getState());
        }

        _game.playNextTurn();  // AI generates and executes a move
    }

    // Hook: record outcome
    if (_dataSink) {
        _dataSink->onGameEnd(_game.getState().winner());
    }
}
```

**For `--replay` mode, the pattern is identical:** step through the replay, call `onTurnStart()` at each turn boundary, and `onGameEnd()` with the replay's recorded result. The output shards are byte-identical in format to self-play data.

## 8. Feature Extraction

`NeuralNet::extractFeatures()` converts a GameState into 1785 floats:

- **Per-unit features** (161 units x 11 features = 1771): For each of the 161 known unit types, encode:
  - 4 counts per player (ready, exhausted, constructing, blocking) = 8
  - 2 supply values (remaining for each player)
  - 1 "in card set" flag (is this unit in the current game?)
- **Global features** (14): Resources (gold, green, blue, red, energy x 2 players), total attack x 2, turn number, active player

This extraction is deterministic and identical for self-play and replay-sourced data -- it depends only on the GameState, not how the state was reached.

## 9. The Training Data Consumer (Python)

```python
# training/load_selfplay.py — loads binary shards into numpy arrays
def load_all_shards(data_dir, max_records=None, validate_crc=False):
    # Scans recursively for .bin files
    # Reads 64-byte header, validates magic/version
    # Reads fixed-size records into structured numpy array
    # Returns features (N x 1785), outcomes (N,), game_ids (N,), etc.
```

The Python loader doesn't care whether shards came from self-play or replays -- it reads the same binary format. **No Python changes are needed** for the replay pipeline.

## 10. Scale and Performance Context

| Metric | Value |
|---|---|
| Total expert replays available | 32,082 |
| Currently parseable by TS | ~56% (17,966) |
| Average game length | ~37 turns (both players combined) |
| Expected records from 32K replays | ~1.2M |
| Existing self-play records | 26.7M (722K games) |
| Self-play shard size | 178 GB total |
| Processing speed (self-play) | ~4 games/min/4-thread process |
| Expected replay processing speed | Faster (no AI search, just feature extraction) |

## 11. Summary of What the Plan Proposes

### Phase 1: `ReplayStepper` Class

A reusable class that converts a replay's click sequence into GameState transitions:

```
Input:  mergedDeck + initInfo + commandList (from replay JSON)
Output: GameState at each turn boundary
```

The hard work is the click-to-action mapping (section 4 above, in reverse) and maintaining the instId-to-CardID mapping as new units appear.

### Phase 2: `--replay` CLI Mode

Wire ReplayStepper into SelfPlayDataSink to produce binary training shards:

```
replay.json → ReplayStepper → GameState per turn → SelfPlayDataSink → .bin shard
```

### Phase 3: `--analyze` CLI Mode

Add neural evaluation and AI move comparison at each turn:

```
replay.json → ReplayStepper → GameState per turn → NeuralNet::evaluate() + AI search → JSON analysis
```

---

## Appendix A: File Inventory

| File | LOC | Role |
|---|---|---|
| `source/engine/GameState.h` | 120 | GameState class declaration |
| `source/engine/GameState.cpp` | ~700 | Game logic: initFromJSON, isLegal, doAction |
| `source/engine/Action.h` | 70 | Action class (type, id, target, shift) |
| `source/engine/Constants.h` | 37 | Enums: Players, Phases, ActionTypes |
| `source/engine/Card.h` | 120 | Card class (instId, type, health, status) |
| `source/testing/main.cpp` | 147 | Entry point, arg parsing, --suggest dispatch |
| `source/testing/Benchmarks.cpp` | 1036 | DoSuggest (802-1036), DoReplayValidation |
| `source/testing/SelfPlayDataSink.h` | 72 | Binary shard writer declaration |
| `source/testing/SelfPlayDataSink.cpp` | 267 | Binary shard writer implementation |
| `source/testing/IDataSink.h` | 27 | Virtual interface for game event capture |
| `source/testing/TournamentGame.cpp` | 80+ | Game runner with IDataSink integration |
| `source/ai/NeuralNet.cpp` | ~500 | Feature extraction (1785-dim) + inference |
| `training/load_selfplay.py` | ~200 | Python binary shard loader |

## Appendix B: Glossary

| Term | Meaning |
|---|---|
| **mergedDeck** | Array of card definitions for a specific game (client format) |
| **CardBuyable** | Engine representation of a purchasable card type (with supply tracking) |
| **CardID** | Engine-assigned sequential integer for each card instance |
| **instId** | Client-assigned integer for each card instance (different numbering than CardID) |
| **CardType** | Static definition of a unit type (stats, abilities, cost) |
| **shard** | Binary file containing training records (up to 1GB) |
| **F6 JSON** | Game state snapshot captured via F6 key in Prismata client |
| **PRISMATA_ASSERT** | Soft assertion: prints error to stdout but does NOT abort |
| **playout eval** | AI evaluation by simulating random games to completion |
| **value prediction** | Neural network output: probability of winning from current position |
| **targeting ability** | Two-step ability: click source unit, then click enemy target |
| **InitFromMergedDeckJSON** | Re-initializes the engine's card type registry from a replay's deck |
