# DeadGameBot — State Conversion Continuation Prompt

**Date:** 2026-03-31
**Status:** Ready for next session
**Context window:** Start fresh — this is a continuation prompt.

## What Was Done

### Implementation Complete (13 of 15 tasks)

All code scaffolding for DeadGameBot is written and committed on the `ai-improvements` branch:

**Bot-side (`bot/`):**
- `config.py` — all constants and env var configuration
- `amf3.py` — AMF3 binary codec (encode/decode) for Prismata server protocol
- `client.py` — `PrismataClient` with auth, connection, and all game protocol messages
- `steam_ai_bridge.py` — `SteamAIBridge` spawns PrismataAI.exe, sends state via stdin, reads clicks
- `game_player.py` — `GamePlayer` handles BeginGame → turns → GameOver, resignation logic
- `trigger_poller.py` — polls deadgame.prismata.live for queue requests, sends heartbeats
- `ranked_bot.py` — main entry point with IDLE→QUEUING→PLAYING state machine, `--bot-game` flag

**Site-side (`deadgame/`):**
- `server.js` — Express on port 3101
- `lib/db.js` — SQLite audit log (requests + bot_state tables), ladder DB queries
- `lib/auth.js` — JWT session verification, bot API key middleware
- `routes/bot.js` — full API: status, queue (with gating), heartbeat, kill switch
- `public/index.html` — frontend SPA with status indicator, queue button, all gating states
- `deadgame.service`, `deadgame.nginx.conf`, `deploy.sh` — deployment infrastructure

**Tests passing:** SteamAI bridge (9/9), AMF3 codec (11/11), Game player resignation (22/22)

### Integration Test Results

The bot successfully:
1. Connects to Prismata server (3.229.49.48)
2. Authenticates as DeadGameBot
3. Handles server redirect (Moved) during login
4. Reaches lobby (SplashToLobby)
5. Sends StartBotGame and receives BeginGame
6. Sends loading progress and receives StartGrace/GraceOver
7. Receives StartTurn

**Where it fails:** `_build_ai_request()` in `game_player.py` — PrismataAI.exe crashes (exit code 0xC0000409 stack buffer overrun) because the raw BeginGame init_info is NOT the format PrismataAI.exe expects.

## The Problem: State Conversion

PrismataAI.exe expects this format via stdin:
```json
{
    "mergedDeck": [...card definitions...],
    "gameState": {
        "table": [{instId, cardName, owner, role, blocking, health, ...}, ...],
        "nextInstId": 19,
        "cards": ["Drone", "Engineer", ...],
        "whiteTotalSupply": [21, 20, 10, ...],
        "blackTotalSupply": [20, 20, 10, ...],
        "whiteSupplySpent": [2, 0, 0, ...],
        "blackSupplySpent": [0, 0, 0, ...],
        "whiteMana": "0",
        "blackMana": "HH",
        "numTurns": 2,
        "turn": 1,
        "phase": "action",
        "glassBroken": false,
        "result": 2,
        "timeRemainingMS": -1
    },
    "aiParameters": {...AI config...},
    "aiPlayerName": "HardestAI"
}
```

The BeginGame init_info gives us:
- `mergedDeck` — card definitions (can pass directly)
- `laneInfo[0].initCards` — starting units per player: `[[6, "Drone"], [2, "Engineer"]]`
- `laneInfo[0].base` — base supply per player
- `laneInfo[0].randomizer` — random units
- `laneInfo[0].initResources` — starting resources (`"0"` for both)

**What we need to build:**
1. **`table` array** — one entry per unit instance with all fields (instId, cardName, owner, role, blocking, health, etc.)
2. **`cards` array** — ordered list of card type names
3. **Supply arrays** — whiteTotalSupply, blackTotalSupply, whiteSupplySpent, blackSupplySpent
4. **Mana strings** — whiteMana, blackMana
5. **Turn tracking** — numTurns, turn, phase

For **turn 0** this is relatively straightforward — build initial state from initCards. For **subsequent turns**, we need to track state changes from clicks. The JS matchup runner does this via the full JS engine (`State.js`), which is ~2000 lines.

## Possible Approaches

### Approach A: Build Initial State + Node.js State Tracker

Build the turn-0 state in Python from BeginGame data. For subsequent turns, spawn a Node.js subprocess that uses the existing JS engine to apply clicks and export the state.

**Pros:** Reuses proven JS engine code, handles all edge cases
**Cons:** Two-language subprocess chain (Python → Node.js → PrismataAI.exe)

### Approach B: Build Initial State + Incremental Python State Tracker

Build turn-0 in Python, then track clicks incrementally in Python (apply buys, abilities, combat, etc.).

**Pros:** Single language, no Node.js dependency
**Cons:** Reimplementing ~2000 lines of game logic in Python, high risk of bugs

### Approach C: Use JS Engine End-to-End

Have a long-running Node.js process that maintains the game state. Python sends it clicks via stdin/stdout, Node.js applies them and returns the state for PrismataAI.exe.

**Pros:** Clean separation, JS engine handles all state
**Cons:** Another long-running subprocess to manage

### Approach D: F6 Clipboard Format via Prismata_Testing.exe --suggest

Use `Prismata_Testing.exe --suggest` instead of `PrismataAI.exe`. It accepts the F6 clipboard format which might be easier to build. But this uses YOUR engine's AI, not Steam's Master Bot — which contradicts the "it's literally Master Bot" framing.

### Recommended: Approach A

Build the initial state in Python (it's mechanical — create table entries from initCards, compute supply from rarity, set mana from initResources). For turn 0, this is all we need.

For subsequent turns, the simplest path is a small Node.js helper script that:
1. Receives the BeginGame init_info
2. Initializes the JS engine State
3. Receives clicks (piped from Python)
4. Exports State.toString() on demand

This reuses the battle-tested JS engine for state tracking.

## Reference Files

### PrismataAI.exe Input Format
- Working example: `js_engine/_suggest_state.json` — a real turn-1 state that PrismataAI.exe accepts
- JS state serialization: `js_engine/matchup_clean.js:197-209` (`exportStateForSuggest()`)
- JS state object: `js_engine/State.js` (the full state class with `toString()`)
- Steam AI request building: `js_engine/matchup_clean.js:749-780` (`playSteamAITurn()`)

### AI Parameters
- `js_engine/ai_params.js` — `selectParams()` function that picks full vs short params based on turn number
- AI parameter JSON files in `bin/asset/config/` or embedded in `ai_params.js`
- PrismataAI.exe needs `aiParameters` with the full HardestAI config

### BeginGame Format
- Protocol doc: `<LADDER_REPO_PATH>\docs\PRISMATA_PROTOCOL.md` (sections: BeginGame, mergedDeck, laneInfo)
- `laneInfo[0].initCards` format: `[[count, "CardName"], ...]` per player
- `laneInfo[0].base` format: `["Engineer", ["Drone", 21], "Conduit", ...]` — card names, optionally `[name, customSupply]`

### Unit Instance Fields (from _suggest_state.json)
Each entry in the `table` array:
```json
{
    "instId": 0,           // sequential integer
    "cardName": "Drone",   // internal name
    "owner": 0,            // 0 = P0 (white), 1 = P1 (black)
    "role": "assigned",    // "default", "assigned", "inert", "sellable"
    "blocking": false,
    "deadness": "alive",
    "dead": false,
    "health": 1,           // from mergedDeck toughness
    "damage": 0,
    "disruptDamage": 0,
    "charge": 0,
    "constructionTime": 0, // 0 = ready
    "delay": 0,
    "lifespan": -1,        // -1 = no lifespan
    "target": -1,
    "buyCreateIds": [],
    "beginOwnTurnCreateIds": [],
    "abilityCreateIds": [],
    "creatorIdFromBuyOrAbility": -1,
    "creatorIdFromBeginTurn": -1,
    "disruptorIds": [],
    "sniperId": -1,
    "laneId": 0
}
```

### Supply Computation
- Supply from rarity: trinket=20, normal=10, rare=4, legendary=1
- `base` array can override: `["Drone", 21]` means Drone has supply 21 for that player
- `whiteSupplySpent` tracks how many have been purchased (initCards count toward this)

### Initial Mana
- `initResources` is `["0", "0"]` — starting gold for each player
- P0 turn 0 has resources from their Drones (6 Drones = 6 gold after swoosh)
- Actually at the very start of turn 0, before swoosh, mana is from initResources

### Turn 0 State
For P0's first turn (turn 0, action phase):
- P0's Drones have `role: "assigned"` (already tapped for gold), `blocking: false`
- P0's Engineers have `role: "inert"`, `blocking: true`
- P1's units have `role: "default"`, `blocking: true`
- `whiteMana: "0"` (P0 hasn't collected resources yet — or has? Check _suggest_state.json)
- `numTurns: 0` or `2`? (Check actual working state)
- `turn: 0` (P0's turn), `phase: "action"`

**IMPORTANT**: Check `_suggest_state.json` for the exact turn-0 values. The `numTurns` field is tricky — in the fixture it shows `numTurns: 2` for what appears to be turn 1.

## Key Files

| Path | Description |
|---|---|
| `bot/game_player.py` | GamePlayer — needs `_build_ai_request()` implemented |
| `bot/steam_ai_bridge.py` | SteamAIBridge — spawns PrismataAI.exe |
| `bot/client.py` | PrismataClient — connection and protocol |
| `bot/ranked_bot.py` | Main entry point — run with `python -m bot --bot-game` |
| `js_engine/_suggest_state.json` | Working PrismataAI.exe input (reference) |
| `js_engine/matchup_clean.js` | JS matchup runner (state export, click application) |
| `js_engine/State.js` | JS engine state class |
| `js_engine/ai_params.js` | AI parameter selection |
| `<LADDER_REPO_PATH>\docs\PRISMATA_PROTOCOL.md` | Full protocol reference |

## How to Test

```powershell
# In terminal 1: sniffer (optional but recommended)
cd <LADDER_REPO_PATH>
python prismata_amf3.py proxy --capture-all

# In terminal 2: bot
cd c:/libraries/PrismataAI
$env:BOT_USERNAME="DeadGameBot"
$env:BOT_PASSWORD="DeadGameBot123"
python -m bot --bot-game
```

Watch for:
- "AI bridge error" = PrismataAI.exe rejected the input format
- "Played turn X: N clicks" = success, clicks were generated
- Sniffer shows the clicks being sent to the server

## Suggested Approach for Next Session

1. **Examine `_suggest_state.json` carefully** — understand every field, especially the turn-0 values
2. **Build a `build_initial_state()` function** that creates the gameState from BeginGame laneInfo
3. **Test with PrismataAI.exe** — write the state to a temp file and verify PrismataAI.exe accepts it
4. **Get turn 0 working** — bot plays its first turn successfully
5. **Figure out subsequent turns** — either track state incrementally or use Node.js helper
6. **Test full game** — bot plays entire game vs Master Bot

The hard part is step 5. For a quick win, see if PrismataAI.exe can accept a state with the full commandInfo (all clicks replayed) — then we'd just need to accumulate clicks and pass them each turn. This might work because PrismataAI.exe might replay the clicks internally to reconstruct state.

## Spec and Plan References
- Design spec: `docs/superpowers/specs/2026-03-30-ranked-bot-deadgamebot-design.md`
- Implementation plan: `docs/superpowers/plans/2026-03-31-deadgamebot-implementation.md`
