# Context Document: DeadGameBot State Tracker Implementation

## 1. Reviewer Brief

You are receiving two documents:
1. **This context document** — background on the project, codebase, and technical environment
2. **The plan** — `2026-03-31-state-tracker-implementation.md` — a 7-task implementation plan for adding game state tracking to a Prismata game bot

**Your role** is to critically analyze the plan given the context provided. You should identify:
- Weaknesses, risks, and missing considerations
- Better alternatives or unnecessary complexity
- Things that should be removed and things that should be preserved
- Architectural improvements and potential future considerations

Your review will be synthesized in a meta-review to improve the plan. Be specific and actionable — reference task numbers and step names from the plan.

**Important:** You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during meta-review. Flag where you feel uncertain due to limited visibility, and note assumptions you are making about the code.

### Review Output Format

1. **One-line verdict**: Your overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess. The plan author will validate these.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

**PrismataAI** is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game. The project includes:
- A C++ engine with Alpha-Beta and UCT/MCTS search
- A transpiled JavaScript engine (from the original ActionScript 3 game client) used for replay validation, matchup running, and training data extraction
- A Python training pipeline (PyTorch DeepSets models)
- A Python bot (`bot/`) that connects to Prismata's live game server to play ranked games

**Current stage:** The bot infrastructure is 85% complete (13 of 15 implementation tasks done). The bot can connect, authenticate, start games, and receive turns. It fails at the point where it needs to ask the AI (PrismataAI.exe, Steam's Master Bot binary) for moves, because the game state format conversion is missing.

**Key constraint:** Single developer (hobbyist). Cost-conscious — prefer local compute. The bot is a community project ("DeadGameBot") to give remaining Prismata players an on-demand ranked opponent in a game whose servers are winding down.

**Target users:** A handful of active Prismata players who want ranked games on demand.

---

## 3. Architecture & Tech Stack

### Languages & Dependencies
- **C++** — core AI engine (`source/`), builds to `Prismata_Testing.exe`
- **JavaScript (Node.js)** — transpiled game engine (`js_engine/`), ~18 modules from AS3
- **Python 3** — bot client (`bot/`), training pipeline (`training/`)
- **PrismataAI.exe** — Steam's closed-source Master Bot binary (third-party, one-shot process)

### High-Level Data Flow (Current — Working)

```
Prismata Server ──AMF3/TCP──> bot/client.py ──> bot/ranked_bot.py ──> bot/game_player.py
                                                                            │
                                                                            ▼
                                                                    _build_ai_request()
                                                                            │
                                                                            ▼ (BROKEN)
                                                                    bot/steam_ai_bridge.py
                                                                            │
                                                                            ▼
                                                                    PrismataAI.exe (stdin/stdout JSON)
```

### Proposed Data Flow (The Plan)

```
Prismata Server ──AMF3/TCP──> bot/client.py ──> bot/ranked_bot.py ──> bot/game_player.py
                                                                            │
                                                    ┌───────────────────────┤
                                                    ▼                       ▼
                                            bot/state_bridge.py      bot/ai_params.py
                                              (subprocess mgr)       (load .bin files)
                                                    │
                                                    ▼ (stdin/stdout JSON lines)
                                            js_engine/state_tracker.js
                                              (long-running Node.js)
                                              (uses Analyzer, State)
                                                    │
                                                    ▼ (EXPORT)
                                            game state JSON ──────> bot/steam_ai_bridge.py
                                                                            │
                                                                            ▼
                                                                    PrismataAI.exe
                                                                            │
                                                                            ▼ (clicks)
                                                                    applied back to state_tracker.js
```

### Key Architectural Decisions

1. **Approach C (long-running Node.js state tracker)** chosen over:
   - Approach A (Python initial state + Node.js for subsequent turns) — rejected because Python would need to manually construct the complex initial game state
   - Approach B (full Python reimplementation) — rejected as too large (~2000 lines of game logic)
   - Approach D (use our own C++ AI instead of Steam's) — rejected because the bot should match Steam's Master Bot exactly

2. **Self-contained state_tracker.js** — cannot `require('./matchup_clean')` because that module reads `matchup_config.json` at load time (line 120) and throws if the file is missing. Functions must be copied locally.

3. **PrismataAI.exe is one-shot** — spawns a fresh process per turn, receives full game state via stdin, returns clicks via stdout, exits. Cannot maintain state between turns.

---

## 4. Codebase Map

### Directory Structure (relevant parts)

```
PrismataAI/
├── bot/                          # Python bot package (new, ~1300 LOC)
│   ├── __init__.py
│   ├── __main__.py               # Entry: python -m bot
│   ├── amf3.py                   # AMF3 binary codec for server protocol
│   ├── client.py                 # PrismataClient (TCP, auth, message send/recv) — 576 LOC
│   ├── config.py                 # Constants and env var config — 43 LOC
│   ├── game_player.py            # GamePlayer (game lifecycle, click handling) — 393 LOC
│   ├── ranked_bot.py             # DeadGameBot orchestrator (state machine) — 201 LOC
│   ├── steam_ai_bridge.py        # SteamAIBridge (spawn PrismataAI.exe) — 103 LOC
│   ├── trigger_poller.py         # Polls deadgame site for queue requests
│   └── tests/
│       ├── test_amf3.py          # 11 tests
│       ├── test_game_player.py   # 22 tests
│       └── test_steam_ai_bridge.py  # 9 tests
├── js_engine/                    # Transpiled AS3 game engine (~45 files)
│   ├── Analyzer.js               # Game analyzer/click dispatcher — 889 LOC
│   ├── State.js                  # Core game state (units, supply, mana) — 1686 LOC
│   ├── Controller.js             # Click routing and phase transitions
│   ├── C.js                      # Constants (click types, phases, colors)
│   ├── Inst.js                   # Unit instance
│   ├── Mana.js                   # Resource/mana system
│   ├── card_library.js           # Card definitions, supply computation — 385 LOC
│   ├── matchup_clean.js          # Matchup runner (CLI + game logic) — 3024 LOC
│   ├── ai_params.js              # AI parameter loading from SWF .bin files
│   ├── steam_ai.js               # SteamAI wrapper (one-shot process)
│   ├── _suggest_state.json       # Reference: known-good state for PrismataAI.exe
│   └── matchup_config.json       # Config for matchup runner (exe path, etc.)
├── tmp_swf_extract/              # Extracted data from Prismata SWF
│   ├── 148_AI.AIThreadHandler_aiParamTextLoad.bin   # Full AI params (JSON text, 200KB)
│   └── 93_AI.AIThreadHandler_aiParam_shortTextLoad.bin  # Short AI params (JSON text, 48KB)
├── bin/                          # Build output, assets, configs
│   └── asset/config/
│       ├── config.txt            # AI player definitions
│       └── cardLibrary.jso       # Master unit definitions (105+ units)
├── source/                       # C++ engine and AI source
├── training/                     # Python training pipeline
└── deadgame/                     # Express.js site for queue management
```

### Key Files the Plan Touches

| File | LOC | Role in plan |
|------|-----|-------------|
| `js_engine/state_tracker.js` | NEW (~170) | Core: long-running Node.js state manager |
| `bot/state_bridge.py` | NEW (~80) | Python subprocess wrapper for state tracker |
| `bot/ai_params.py` | NEW (~45) | AI parameter file loading |
| `bot/game_player.py` | 393 | Major modification: new constructor param, rewritten `_build_ai_request()`, opponent click buffering |
| `bot/ranked_bot.py` | 201 | Minor modification: pass StateBridge to GamePlayer |
| `bot/config.py` | 43 | Minor: add 2 path constants |
| `bot/tests/test_game_player.py` | 259 | Add ~60 lines of new tests |

---

## 5. Relevant Existing Patterns & Conventions

### Python (bot/)
- **Style:** Standard Python 3, logging via `logging.getLogger(__name__)`
- **Testing:** pytest, tests in `bot/tests/`, test helpers like `_make_init_info()` build minimal fixture dicts
- **Config:** Environment variables with defaults in `bot/config.py`, no config files
- **Error handling:** Log and continue (bot must stay alive). `_build_ai_request` returns `None` on failure, caller sends empty turn.
- **No type annotations** in existing code

### JavaScript (js_engine/)
- **Style:** `'use strict'`, CommonJS `require/module.exports`
- **Engine modules:** Transpiled from ActionScript 3, preserve AS3 line references in comments
- **Constants:** `C.js` exports string constants for click types (`'space clicked'`, `'card clicked'`, etc.) and phase names (`'action'`, `'defense'`, `'confirm'`)
- **State serialization:** `State.toString(timeRemainingMS)` returns a JSON string. Optional param defaults to -1.
- **Click processing:** `analyzer.recordClick(update, animate, clickType, clickId)` returns `{canClick: bool, ...}`. First two params always `false` in headless mode.

### Subprocess Communication
- **SteamAIBridge pattern:** spawn process, write to stdin, read from stdout, parse JSON. One-shot (process exits after response).
- **The plan's StateBridge differs:** long-running process, JSON-line protocol, multiple round trips.

### Testing Strategy
- 42 existing tests across 3 test files, all passing
- Tests use `bridge=None, client=None` to test GamePlayer in isolation
- No integration tests currently (the plan adds one)
- No pytest markers configured (the plan uses `@pytest.mark.integration`)

---

## 6. Current State & Known Issues

### What Works Today
- Bot connects to Prismata server, authenticates, handles server redirect
- Bot starts bot games (vs Master Bot) and receives BeginGame, StartTurn messages
- Bot sends EndSwoosh, loading progress, EndGrace correctly
- AMF3 codec, resignation logic, turn tracking all tested and working
- JS engine can play full matchups via `matchup_clean.js` (SteamAI games work end-to-end in the matchup runner)

### What's Broken
- **`_build_ai_request()` in `game_player.py`** — currently passes raw `init_info` from BeginGame, which is NOT the format PrismataAI.exe expects. PrismataAI.exe crashes with stack buffer overrun (0xC0000409).

### Known Technical Concerns

1. **`matchup_clean.js` cannot be safely required** — line 120 reads `matchup_config.json` at module load time. If the file is missing or the format changes, requiring it will throw. The plan addresses this by copying functions locally into `state_tracker.js`.

2. **`applyClicks` depends on module-level `recoveryStats`** — a mutable object that accumulates statistics. The plan's copy won't have this, which is fine but means the auto-breach function (which also writes to `recoveryStats`) needs adaptation.

3. **`autoBreachIfNeeded` is non-trivial** (~60 lines) — it finds the weakest breachable opponent unit and clicks it when breach damage remains. The plan mentions it but defers porting: "For now, skip — PrismataAI.exe should emit breach target clicks." This may or may not be correct — PrismataAI.exe handles breach in its move generation, but the JS engine may need the auto-breach for state tracking after applying those clicks.

4. **`numTurns` semantics are confusing** — `loaderInit()` calls `runTriggersAndGotoW1()` which increments `numTurns` by 1, then `swoosh()` may increment again. The `_suggest_state.json` reference shows `numTurns: 2` for what looks like turn 1 (P1's first action). The plan uses `numTurns` for AI param selection (full vs short cutoff at turn 16).

5. **Drone supply asymmetry** — `buildGameInitInfo` gives White 21 Drones and Black 20 (because White starts with 6 and Black with 7, totaling 27 each). This logic must be correctly copied into `state_tracker.js`.

6. **`ManyClicks` server message** — the server can send opponent clicks as either individual `Click` messages OR as a single `ManyClicks` batch message. The bot's handler dispatch table only handles `Click`, not `ManyClicks`. Confirmed in <ladder> protocol docs and headless_client.py:766. Must be handled.

---

## 7. Context Specific to the Plan

### PrismataAI.exe Input Format

PrismataAI.exe expects a flat JSON object on stdin (newline-terminated):
```json
{
    "mergedDeck": [<card definitions from BeginGame>],
    "gameState": {
        "table": [<unit instances with 23+ fields each>],
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
    "aiParameters": {<full AI config JSON>},
    "aiPlayerName": "HardestAI"
}
```

A known-good example of `gameState` exists in `_suggest_state.json` (wrapped in `CurrentInfo` — that wrapper is for a different executable). The `gameState` inside it represents P1's first action phase after P0 bought 2 Drones on turn 0.

### PrismataAI.exe Output Format

```json
{
    "aiclicks": [{"_type": "card clicked", "_id": 0}, ...],
    "aithinktime": 1234,
    "eval": 0.5,
    "eval_pct": "50%"
}
```

`eval_pct` is a string with `%` suffix. Clicks use `_type` and `_id` (underscore prefix). The last click is typically `{"_type": "space clicked", "_id": -1}` (commit). However, the JS engine needs TWO space clicks (action→confirm + confirm→commit), while PrismataAI.exe only emits ONE. The `applyClicks` function handles this via auto-commit logic.

### AI Parameters

Two JSON files extracted from the Prismata SWF:
- **Full params** (200KB) — includes opening books, used for turns 1-16
- **Short params** (48KB) — no opening books, used after turn 16

Selection logic (from AS3 `AIThreadHandler.as`):
- If AI name is in `AI_NO_OPENINGS` at index > 0, use short params
- If turn number > 16, use short params
- Otherwise, use full params
- **HardestAI is at index 6** in `AI_NO_OPENINGS`, so it **always** gets short params regardless of turn number

### Prior Approach (Rejected)

The original `_build_ai_request()` attempted to pass the raw BeginGame `init_info` to PrismataAI.exe. This doesn't work because `init_info` contains server protocol fields (liveGameID, format, players, timeInfo) and uses a different structure for game state (initCards/base/randomizer) rather than the table/supply/mana format PrismataAI.exe expects.

### Click Flow Per Turn

**Our turn:**
1. Server sends `StartTurn` with turn number
2. Bot sends `EndSwoosh` to server (protocol requirement)
3. Bot asks state tracker for `EXPORT` (current game state)
4. Bot builds AI request (state + AI params + mergedDeck + aiPlayerName)
5. Bot spawns PrismataAI.exe, sends request, gets clicks back
6. Bot sends each click to server
7. Bot sends clicks to state tracker (`CLICKS` command)
8. Bot sends `EndTurn` to server

**Opponent's turn:**
1. Server sends `Click` messages for each opponent action
2. Bot buffers these in `_pending_opponent_clicks`
3. When our next turn starts, bot flushes buffer to state tracker before EXPORT

---

## 8. Scope Boundaries

### Out of Scope
- **Full Python game engine** — deferred to future work. The Node.js bridge is the pragmatic solution for now.
- **Reconnection/resume** — if the bot disconnects mid-game, it will lose that game. No state persistence.
- **Multiple concurrent games** — one game at a time.
- **Custom AI difficulty** — hardcoded to HardestAI (Steam's strongest).
- **Ranked queue integration** — the trigger polling system exists but isn't part of this plan (already implemented).

### Fixed / Non-Negotiable
- **Must use PrismataAI.exe** (Steam's binary) — the whole point is "play against the real Master Bot"
- **Must use the existing JS engine** for state tracking — reimplementing 2000 lines of game logic is not viable
- **Self-contained `state_tracker.js`** — cannot require `matchup_clean.js` due to the config file load-time crash (verified)
- **Python bot + Node.js subprocess** — the bot is Python, the engine is JS, this is the integration path

### Accepted Trade-offs
- **Two-language subprocess chain** (Python → Node.js → PrismataAI.exe) — adds complexity but avoids reimplementation
- **Copied code in state_tracker.js** — `buildGameInitInfo` and click-application logic are copied from `matchup_clean.js` rather than shared. This means future changes to the matchup runner won't automatically propagate. Acceptable for a bot that plays one game at a time.
- **Auto-breach may be deferred** — the plan notes PrismataAI.exe should emit its own breach clicks. If it doesn't, this will need to be added later.

---

## 9. Success Criteria

1. **Turn 0 works:** Bot exports initial state → PrismataAI.exe returns valid clicks → clicks apply successfully to state tracker → state advances to P1's turn
2. **Full game works:** Bot plays an entire bot game (vs Master Bot) from start to GameOver without crashing
3. **State stays in sync:** After each turn, the state tracker's state matches what the server expects (no desync causing click failures)
4. **Existing tests pass:** All 42 existing bot tests continue to pass (backward compatibility via `state_bridge=None` default)
5. **New tests pass:** Integration test verifies the full pipeline (state tracker → PrismataAI.exe → click application)

**Observable outcome:** Run `python -m bot --bot-game` and see the bot play a complete game with logged turns and a final GameOver result.

---

## 10. Key Questions for Reviewers

1. **Subprocess lifecycle management:** The plan has Python manage a long-running Node.js process via stdin/stdout pipes. What failure modes should be handled that aren't in the plan? (Process crash mid-game, pipe buffering issues on Windows, Node.js stderr interleaving with stdout, etc.)

2. **Auto-breach omission:** The plan defers porting `autoBreachIfNeeded` (~60 lines) with the assumption that PrismataAI.exe emits its own breach target clicks. Is this a reasonable assumption, or is it likely to cause state tracking desync? The matchup runner includes auto-breach as a safety net — should the state tracker do the same?

3. **State format compatibility:** The plan assumes `State.toString()` output is directly compatible with what PrismataAI.exe expects as `gameState`. The `_suggest_state.json` reference was generated by the same JS engine and is known to work. Is there any reason the output might differ when the state is initialized via `buildGameInitInfo` + `loaderInit()` vs the matchup runner's normal flow?

4. **Error recovery:** If PrismataAI.exe returns clicks that partially fail when applied to the state tracker, the plan logs a warning and continues. Should there be a harder failure mode (resign the game, restart the state tracker, etc.)?

5. **Testing sufficiency:** The plan has unit tests (mocked bridge), integration test (real PrismataAI.exe), and manual test (live server). Is this sufficient coverage for the complexity of the state tracking, or should there be additional tests (e.g., multi-turn sequences, specific game scenarios)?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|------|-----------|
| **PrismataAI.exe** | Steam's closed-source Master Bot binary. One-shot process: receives game state via stdin, returns clicks via stdout, exits. |
| **mergedDeck** | Array of card definitions for the current game. Contains all buyable unit types with properties (cost, health, abilities, rarity). Sent by the server in BeginGame. |
| **gameState** | JSON object describing the current board: all unit instances (table), supply pools, mana/resources, turn number, active player, phase. |
| **Click** | A player action in the Prismata protocol. Types: `card clicked` (buy), `inst clicked` (activate unit), `inst shift clicked` (alternative activation), `space clicked` (commit/end phase), `end swipe processed` (end targeting mode). |
| **Phase** | Game phase within a turn: `defense` (assign blockers), `action` (use abilities, buy units), `confirm` (commit turn). |
| **Swoosh** | The between-turns transition where units produce resources, construction timers tick down, and lifespan units die. Handled internally by the JS engine. |
| **Breach / glassBroken** | When a player can't block all incoming damage, the attacker clicks through undefended units directly. `glassBroken` is the flag indicating breach is active. |
| **AMF3** | Action Message Format 3 — binary serialization used by the Prismata server protocol (originally Flash/AIR). |
| **BeginGame** | Server message containing full game initialization: mergedDeck, laneInfo (starting units, supply), player info. |
| **StartTurn** | Server message indicating a new turn has started, with turn number. |
| **EndSwoosh** | Client message acknowledging the swoosh animation is complete (bot sends immediately since it has no UI). |
| **numTurns** | Counter incremented each half-turn. Not the same as "round number." After `loaderInit()`, starts at 1 or 2 depending on initialization sequence. Used for AI param selection (full vs short cutoff). |
| **HardestAI** | The strongest AI difficulty level in Prismata. Uses Stack Alpha-Beta search with 7000ms time limit. |
| **initCards** | Starting units per player from BeginGame laneInfo: `[[6, "Drone"], [2, "Engineer"]]` for White, `[[7, "Drone"], [2, "Engineer"]]` for Black. |
| **Supply** | How many copies of each unit type are available for purchase. Derived from rarity: trinket=20, normal=10, rare=4, legendary=1. |
| **Mana** | Resource string format. Digits = gold, `G` = green, `B` = blue, `C` = red, `H` = energy. E.g., `"6"` = 6 gold, `"HH"` = 2 energy. |
| **Auto-commit** | The JS engine needs two space clicks to end a turn (action→confirm, confirm→commit), but PrismataAI.exe only emits one. The click-application logic auto-inserts the second. |
| **DeadGameBot** | The bot being built. Named because Prismata is a "dead game" with few remaining players. Provides on-demand ranked opponents. |
| **Trigger site** | `deadgame.prismata.live` — a web frontend where players can request a game. The bot polls this site for queue requests. |
