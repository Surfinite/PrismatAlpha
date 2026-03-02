# Prismata Overlay Advisor — Standalone Context Document

This document provides all the background knowledge needed to understand and implement the overlay advisor plan (`docs/plans/2026-02-18-prismata-overlay-advisor.md`). No prior knowledge of PrismataAI is assumed.

---

## 1. What is Prismata?

Prismata is a **turn-based perfect-information strategy card game** by Lunarch Studios. Two players build armies of units (attackers, defenders, producers) and try to destroy each other's forces. Think of it like chess meets a card game — no hidden information, no luck, pure strategy.

Key facts:
- **105+ different unit types** (e.g., Tarsier = cheap attacker, Wall = basic blocker, Blastforge = tech building)
- **Turn structure**: Each turn has phases — Action (use abilities, buy units), Defense (assign blockers), Breach (when defense fails)
- **Resources**: Gold, Green, Blue, Red, Energy — units cost combinations of these
- **Perfect information**: Both players see everything. No hidden cards.
- The game client is an **Adobe AIR/Flash application** connecting to game servers over TCP

## 2. What is PrismataAI?

PrismataAI is a C++ game engine and AI system, originally developed by David Churchill at Memorial University of Newfoundland. This fork (PrismatAlpha) extends it with neural network evaluation and self-play training.

### Project structure:
```
PrismataAI/
  source/
    engine/       # Game logic (GameState, Action, Move, Card, etc.)
    ai/           # AI players (Alpha-Beta search, UCT/MCTS, neural net)
    testing/      # Benchmarks, tournaments, self-play data generation
    gui/          # SFML-based GUI for watching AI games
  bin/
    asset/config/
      config.txt           # AI player definitions & tournament configs
      cardLibrary.jso      # Master unit definitions (105 units)
      neural_weights.bin   # Neural network weights file
  training/               # Python training pipeline (PyTorch)
  tools/                  # Utility scripts
  visualstudio/           # VS solution (x86 only, 3 build targets)
  prismata_decompiled/    # Decompiled Prismata client (ActionScript)
```

### Build targets:
- **Prismata_Testing.exe** — console app for benchmarks, tournaments, self-play. This is the exe the overlay will invoke.
- **Prismata_GUI.exe** — SFML GUI for watching games
- **Prismata_Standalone.exe** — console tournament runner

Build: Visual Studio solution at `visualstudio/Prismata.sln`, **x86 only** (no x64).

## 3. How the Engine Works

### GameState
The core class. Represents a complete game position: what units are on the board, whose turn it is, what resources are available, what units can be bought.

```cpp
// source/engine/GameState.cpp
void GameState::initFromJSON(const rapidjson::Value & value)
```

This method parses a JSON object into a GameState. Fields it reads:
- `phase` — "action", "defense", or "confirm"
- `turn` — current player (0 = white, 1 = black)
- `numTurns` — how many turns have been played
- `whiteMana` / `blackMana` — resource strings like "6GBBBB" (6 gold, 1 green, 4 blue)
- `cards` — array of buyable unit names (internal engine names, see section 5)
- `table` — array of unit objects on the board (type, player, amount, status, hp, etc.)
- `whiteTotalSupply` / `blackTotalSupply` — how many of each buyable card exist

### Actions and Moves
An `Action` is a single game action (buy a unit, use an ability, assign a blocker, etc.):
```cpp
// source/engine/Action.h
namespace ActionTypes {
    enum { USE_ABILITY, BUY, END_PHASE, ASSIGN_BLOCKER, ASSIGN_BREACH,
           ASSIGN_FRONTLINE, SNIPE, CHILL, WIPEOUT, ... };
}

class Action {
    PlayerID m_player;    // who's acting
    ActionID m_type;      // what kind of action (BUY, USE_ABILITY, etc.)
    CardID   m_id;        // which card/unit (context-dependent)
    CardID   m_targetID;  // target of the action
};
```

A `Move` is a sequence of Actions that make up a complete turn:
```cpp
// source/engine/Move.h
class Move {
    std::vector<Action> m_actions;  // up to 512 actions per turn
public:
    const size_t size() const;
    const Action & getAction(const size_t index) const;
};
```

### BUY action name resolution
When an Action has type `ActionTypes::BUY`, `action.getID()` returns a CardType index. To get the human-readable unit name:
```cpp
std::string unitName = CardType(action.getID()).getUIName();
// e.g., returns "Tarsier" or "Wall" or "Blastforge"
```
This pattern is used in `source/testing/TournamentGame.cpp:57-60`.

## 4. How the AI Works

### PartialPlayer Phase Decomposition
The AI breaks each turn into phases, each handled by a specialized sub-player:
1. **Defense** — assign blockers when enemy attacks
2. **ActionAbility** — decide which units to click (activate abilities)
3. **ActionBuy** — decide what to purchase
4. **Breach** — decide which enemy units to kill when breaking through

### AI Players
The AI system supports multiple player types. The key ones:

- **PrismatAlpha_AB** — Alpha-Beta search with neural net evaluation. This is our best AI and the one the overlay will use.
- **OriginalHardestAI** — The original strongest AI (playout-based evaluation). Used as the baseline opponent.
- **HardestAIUCT** — UCT/MCTS search variant

Getting an AI player and asking it for a move:
```cpp
// source/ai/AIParameters.h
PlayerPtr AIParameters::Instance().getPlayer(PlayerID player, std::string name);

// Then call getMove:
Move move;
player->getMove(state, move);
// 'move' is now populated with the AI's recommended sequence of actions
```

### Neural Network
A 2-layer ResNet trained on self-play data. Used for position evaluation.

```cpp
// source/ai/NeuralNet.h
struct NeuralOutput {
    std::vector<float> policy;  // per-unit buy probabilities (weak, not used for ordering yet)
    float value;                // [-1, 1] win probability for the active player
};

NeuralOutput NeuralNet::Instance().evaluate(const GameState & state);
```

Key properties:
- `value` ranges from -1 (certain loss) to +1 (certain win)
- ~2,000 evaluations per second per core
- Hidden dimension is dynamic (read from weight file) — currently 256 neurons (E2b model)
- Current strength: 26.7% win rate vs OriginalHardestAI (the strongest non-neural AI)

The weight file is loaded at startup from `bin/asset/config/neural_weights.bin`.

## 5. Internal Name System

**Critical gotcha**: The engine uses internal codenames for all units, not their display names. The clipboard JSON and `cardLibrary.jso` use internal names.

| Internal Name | Display Name | | Internal Name | Display Name |
|---|---|---|---|---|
| Tesla Tower | Tarsier | | Brooder | Blastforge |
| Treant | Steelsplitter | | Elephant | Rhino |
| Blood Barrier | Forcefield | | Minicannon | Gauss Cannon |
| House | Husk | | Flame Kin | Gauss Charge |

Full 105-unit mapping in `bin/asset/config/cardLibrary.jso`.

`CardType::getUIName()` handles the conversion from internal to display name.

## 6. The Prismata Client

The live Prismata game client is an **Adobe AIR/Flash application**. The game logic runs as C++ compiled to AVM2 bytecode via CrossBridge (Alchemy/FlasCC). This means:
- Memory reading/injection is impractical
- The client communicates with game servers over TCP ports 11600 (plaintext AMF3) and 11601 (TLS)

### Clipboard Export
The client has built-in clipboard export functions (from decompiled ActionScript):

```actionscript
// prismata_decompiled/scripts/client/Game.as
public function getAIDebugJsonString(long:Boolean = true) : String
{
    var mergedDeckString:String = mcdsJSON.encode(Client.game.gameInitInfo.simpleMergedDeck);
    var gameStateString:String = gameState.toString(0);
    var aiParamsString:String = mcdsJSON.encode(mcdsJSON.decode(AIThreadHandler.aiParameters));
    var aiPlayerName:String = AIThreadHandler.aiDifficulty;
    return "{\"mergedDeck\":" + mergedDeckString + ",\"gameState\":" + gameStateString
         + ",\"aiParameters\":" + aiParamsString + ",\"aiPlayerName\":\"" + aiPlayerName + "\"}";
}
```

Triggered by keyboard:
- **F6** — compact AI format (`copyGamestateToClipboard`)
- **F5** — verbose format (`copyGamestateToClipboardLong`)
- **Developer build only** — gated behind `FlashBuildOptions.developerVersion`

The JSON output contains:
- `mergedDeck` — the randomized set of 8 units available in this game
- `gameState` — full board position (resources, units, supply, phase)
- `aiParameters` — AI configuration
- `aiPlayerName` — which AI difficulty is being played against

### Network Proxy (alternative approach)
`tools/prismata_sniffer.py` is a 511-line TCP proxy that intercepts AMF3 game traffic. It works by:
1. Adding `127.0.0.1 ec2-3-229-49-48.compute-1.amazonaws.com` to the Windows hosts file
2. Listening on ports 11600/11601/11619
3. Forwarding traffic to the real server at `3.229.49.48`
4. Decoding and logging AMF3 messages (clicks, turns, game starts/ends)

This is a fallback if clipboard export isn't available.

**Server status (confirmed Feb 18, 2026):** Game server `ec2-3-229-49-48.compute-1.amazonaws.com` resolves to `3.229.49.48` and ports 11600/11601 are reachable. The client connects successfully when no hosts file redirect is present.

> **WARNING — HOSTS FILE LOCKOUT RISK:** The sniffer's hosts file redirect (`127.0.0.1 ec2-3-229-49-48.compute-1.amazonaws.com`) silently locks the user out of the live Prismata client if not removed. This happened on Feb 18 — a previous session added the entry and never cleaned it up. The client shows "Connection Error" with no indication that the hosts file is the cause. Removal requires admin/UAC elevation. **Any future proxy-based approach MUST include automated cleanup** (atexit handler, context manager, or startup stale-entry check). See the main plan doc's "CRITICAL WARNING" section for full mitigation steps.

## 7. Existing Entry Point (`main.cpp`)

The `Prismata_Testing.exe` entry point at `source/testing/main.cpp`:

```cpp
int main(int argc, char* argv[])
{
    // 1. Initialize card library (unit definitions)
    Prismata::InitFromCardLibrary(configDir + "cardLibrary.jso");

    // 2. Load neural network weights
    NeuralNet::Instance().loadWeights(configDir + "neural_weights.bin");
    NeuralNet::Instance().buildCardTypeMapping();

    // 3. Parse AI player configurations
    Prismata::AIParameters::Instance().parseFile(configDir + "config.txt");

    // 4. Handle command-line flags
    // Existing: --fixedset, --fixedset-legacy, --validate-replay, --validate-output
    // PLANNED: --suggest <state_file> --player <name> --think-time <ms>

    // 5. Run the appropriate mode
    if (runFixedSet) Benchmarks::DoFixedSetTest(...);
    else Benchmarks::DoBenchmarks(...);
}
```

All three initialization steps (card library, neural weights, AI parameters) must complete before any game state can be parsed or evaluated.

## 8. Benchmarks System

`source/testing/Benchmarks.h/cpp` contains standalone test/eval functions:

```cpp
namespace Benchmarks {
    void DoBenchmarks(const std::string & filename);
    void DoFixedSetTest(const std::vector<std::string> & dominionCards,
                        const std::string & playerName, size_t numGames, size_t trackTurns);
    void DoReplayValidation(const std::string & validationFile, const std::string & outputFile);
    // PLANNED: void DoSuggestMove(const std::string& stateFile,
    //                              const std::string& playerName, int thinkTimeMs);
}
```

The overlay plan adds `DoSuggestMove()` here — it follows the same pattern as `DoFixedSetTest()` but reads a JSON state file instead of running a full game.

## 9. Config Files

Three config files must be present in the working directory at `bin/asset/config/`:

1. **`cardLibrary.jso`** — JSON definitions for all 105+ units. Maps internal names to display names, costs, stats, abilities. Required for `InitFromCardLibrary()`.

2. **`neural_weights.bin`** — Binary file with neural network weights. ~8.8 MB. Header specifies hidden dimension. Required for neural eval.

3. **`config.txt`** — AI player definitions in JSON format. Defines named players like `"PrismatAlpha_AB"` with their search parameters, evaluation method, think time limits. Required for `AIParameters::Instance().parseFile()`.

## 10. Python Environment

- Windows 11, Git Bash as shell
- Python available as `python` (not `python3`)
- `tkinter` is built-in (no pip install needed)
- For subprocess calls to the C++ exe, set `cwd` to the `bin/` directory so config files are found
- `PYTHONUNBUFFERED=1` recommended for long-running processes
- No external Python packages needed for the overlay tool

## 11. Build Instructions

```bash
# MSBuild path on this system:
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
```

- **x86 only** — no x64 configurations exist
- Always use `/t:Rebuild` (incremental builds may not relink)
- Cannot rebuild while exe is running (file lock error)
- Output: `bin/Prismata_Testing.exe`

## 12. What the Overlay Actually Does

When complete, the workflow is:

1. User plays a Prismata game against the bot
2. User presses F6 (or manually copies game state JSON to clipboard)
3. Python overlay detects new clipboard content (polls every 500ms)
4. Python writes JSON to a temp file
5. Python runs `bin/Prismata_Testing.exe --suggest _advisor_state.json --player PrismatAlpha_AB --think-time 3000`
6. C++ exe parses the game state, runs neural eval and AI search (~3 seconds)
7. C++ exe outputs JSON to stdout: eval score, recommended buys, abilities, defense
8. Python parses the JSON output
9. Python updates the transparent overlay window:
   - **EVAL: 67%** (green if winning, red if losing, yellow if close)
   - **BUY: Tarsier x2, Husk** (what to purchase)
   - **USE: Blastforge** (what abilities to activate)
   - **DEF: Wall** (how to assign blockers, if in defense phase)

The overlay is:
- Fully transparent background (only text visible)
- Always-on-top (floats over the Prismata window)
- Draggable (reposition by clicking and dragging)
- Click-through (doesn't steal focus from the game)
- Bright bold text in large font (similar to the debug numbers shown in the GUI)

Total latency target: under 5 seconds from clipboard to display update.
