# DeadGameBot — Master Bot Hang Debugging Continuation

**Date:** 2026-03-31
**Status:** Ready for next session
**Context window:** Start fresh — this is a continuation prompt.
**Branch:** `ai-improvements`

## What Was Done This Session

### State Tracker Pipeline — COMPLETE AND WORKING

The full pipeline from game state → AI request → PrismataAI.exe → clicks is implemented and verified:

1. `js_engine/state_tracker.js` — Self-contained Node.js process (INIT/EXPORT/CLICKS protocol via stdin/stdout JSON lines). Copies `buildGameInitInfo` and `applyClicks` locally to avoid `matchup_clean.js` config dependency.
2. `bot/state_bridge.py` — Python subprocess wrapper with timeout-protected reads, background stderr draining.
3. `bot/ai_params.py` — Loads SWF-extracted AI parameter .bin files, selects full vs short params.
4. `bot/game_player.py` — Wired state bridge + AI params into `_build_ai_request()`. Opponent click buffering, ManyClicks handler, debug state dumping.
5. `bot/ranked_bot.py` — Passes StateBridge to GamePlayer. Handles `ExistsDisconnectedGame` → `AttemptReconnect` → `ReconnectGame` for stale game cleanup. Auto-requeues after stale game abandon.

**65 tests passing** (31 game_player, 4 state_bridge, 9 ai_params, 11 amf3, 9 steam_ai_bridge, 1 integration).

**20 commits** on `ai-improvements` branch (6 feature + 14 bugfix).

### Integration Test Results

`bot/tests/test_integration.py` — Turn 0 pipeline verified with real PrismataAI.exe:
- State tracker initializes from mergedDeck
- Exports valid game state (turn 0, action phase)
- PrismataAI.exe returns 5 clicks
- Clicks applied to state tracker, state advances to turn 1

### Live Bot Test — Partial Success

The bot successfully:
1. Connects to Prismata server, authenticates, handles Moved redirect
2. Handles stale game cleanup (ExistsDisconnectedGame → AttemptReconnect → resign)
3. Starts a new bot game, receives BeginGame
4. Correctly identifies player index (P0 or P1) using `bot` field filtering
5. Sends proper loading progress (0 → 0.99 → LoadingQueueFinished)
6. Completes grace period (Endgrace → GraceOver)
7. Receives StartTurn, sends EndSwoosh
8. Gets AI move from PrismataAI.exe (7.5s think time)
9. Converts raw SteamAI clicks to `{_type, _id}` format via state tracker
10. Sends clicks to server (server accepts them — verified via sniffer)
11. Sends EndTurn (server acknowledges)
12. Keeps connection alive during AI think time (background thread)

**Where it fails:** Master Bot (server-side P0/P1) never plays its turn after receiving StartTurn + EndSwoosh. The game hangs indefinitely.

## The Remaining Problem: Master Bot Hang

### What Happens
After our turn completes (or when Master Bot should play first as P0):
1. Server sends `StartTurn` for Master Bot's turn
2. Bot sends `EndSwoosh` for that turn
3. Server echoes `EndSwoosh [0]` to spectators (sniffer confirms)
4. Then: **nothing**. Just Pings forever. Master Bot never plays.

### What We've Ruled Out
- **Click format** — Server accepts our `{_type, _id}` clicks (sniffer shows them relayed to spectators)
- **EndTurn format** — Server acknowledges with its own EndTurn response
- **Loading timeout** — Fixed by sending proper loading progress sequence
- **Connection drops** — Keep-alive fix prevents disconnects during AI think time
- **Player identification** — Correctly identifies P0/P1 using `bot` field
- **Stale games** — Properly abandoned via AttemptReconnect flow
- **Missing EndSwoosh** — Sent on both our turns and opponent turns

### What We Haven't Ruled Out

1. **PlayerDisconnected during node switch** — Happens every game during the `StartBotGame` → `Moved` redirect. The server sends `PlayerDisconnected [player_idx]` followed by `PlayerReconnected [player_idx]` a few seconds later. This might put the game into a "paused" state that prevents Master Bot from playing. When the real Prismata client reconnects (via `AttemptReconnect` + `ReconnectGame`), Master Bot immediately plays. But for fresh games (not reconnects), there's no `AttemptReconnect` to send.

2. **Something the real client sends that we don't** — The Flash client sends:
   - `AnalyticsEvent ["Game", "game start", ...]` — probably not required
   - `AnalyticsEvent ["Timing", "loading", "ms", N, ...]` — probably not required
   - Multiple `ReportGameLoadProgress` steps (0, 0.06, 0.11, 0.99) — we now send 0 and 0.99
   - The client might send messages on the **secure** socket that we don't

3. **Secure vs main socket for game messages** — All our game messages (Click, EndSwoosh, EndTurn) go via `_send_main`. The protocol doc doesn't specify which socket to use for game messages. It's possible some messages need to go via the secure socket.

4. **The `Moved` redirect itself** — The node switch during `StartBotGame` may confuse the server's bot game setup. The real Prismata client handles `Moved` during the initial connection (before games), not during active gameplay. Our bot gets `Moved` during the `StartBotGame` flow because the server redirects to a game server.

### Key Sniffer Evidence

**Successful game (real client reconnecting to stale game):**
```
C->S  AttemptReconnect []
S->C  ReconnectGame [{full state}]
C->S  ReportGameLoadProgress [id, 0]
C->S  ReportGameLoadProgress [id, 0.99]
C->S  LoadingQueueFinished [id]
...
C->S  Click [...] (plays turn)
S->C  EndTurn (acknowledged)
S->C  StartTurn (Master Bot's turn)
S->C  EndSwoosh [0] (Master Bot plays immediately)
```

**Our bot (fresh game, Master Bot hangs):**
```
S->C  BeginGame
C->S  ReportGameLoadProgress [id, 0]
C->S  ReportGameLoadProgress [id, 0.99]
C->S  LoadingQueueFinished [id]
S->C  PlayerDisconnected [our_idx]
S->C  PlayerReconnected [our_idx]
S->C  StartGrace → cancelGrace → GraceOver
S->C  StartTurn (turn 0)
C->S  EndSwoosh [id, 0]
... (hangs — Master Bot never plays)
```

**When we play first (P0) and it works partially:**
```
S->C  StartTurn (turn 0, our turn)
C->S  EndSwoosh, Click(s), EndTurn
S->C  EndTurn (acknowledged)
S->C  StartTurn (turn 1, Master Bot)
C->S  EndSwoosh [id, 1]
... (hangs — Master Bot never plays turn 1 either)
```

### Suggested Investigation for Next Session

1. **Compare full message sequences** — Capture a complete successful bot game from the real Prismata client (human playing vs Master Bot). Compare every C->S message against what our bot sends. Focus on the messages between `LoadingQueueFinished` and Master Bot playing turn 0.

2. **Try sending game messages on secure socket** — The real client might use the secure socket for game commands. Try changing `send_click`, `send_end_swoosh`, `send_end_turn` to use `_send_secure` instead of `_send_main`.

3. **Try AnalyticsEvent messages** — Send the `AnalyticsEvent ["Game", "game start", ...]` and timing events that the real client sends. Long shot, but easy to test.

4. **Investigate the node switch timing** — The `PlayerDisconnected` during node switch might be the root cause. If we could avoid the node switch during `StartBotGame`, the problem might go away. One approach: connect to the game server port directly instead of going through the redirect.

5. **Check if `Endgrace` needs to go on secure socket** — The grace period flow might require messages on both sockets.

## Key Files

| Path | Description |
|------|-------------|
| `bot/game_player.py` | Game lifecycle — `_play_turn`, `_build_ai_request`, click handling |
| `bot/ranked_bot.py` | Bot orchestrator — state machine, stale game handling |
| `bot/client.py` | Network layer — `_send_main`, `_send_secure`, `pump_messages` |
| `bot/state_bridge.py` | Python↔Node.js subprocess wrapper |
| `bot/steam_ai_bridge.py` | PrismataAI.exe one-shot subprocess |
| `bot/ai_params.py` | AI parameter loading |
| `bot/config.py` | All configuration constants |
| `js_engine/state_tracker.js` | Node.js state tracker (INIT/EXPORT/CLICKS) |
| `bot/tests/test_integration.py` | Full pipeline integration test |
| `<LADDER_REPO_PATH>\docs\PRISMATA_PROTOCOL.md` | Full protocol reference |

## How to Test

```powershell
# Run all tests
cd c:/libraries/PrismataAI
python -m pytest bot/tests/ -v

# Run integration test (requires PrismataAI.exe)
python -m pytest bot/tests/test_integration.py -v -s

# Run bot against live server
$env:BOT_USERNAME="DeadGameBot"
$env:BOT_PASSWORD="DeadGameBot123"
python -m bot --bot-game
```

```bash
# Run sniffer (in <ladder> repo, separate terminal)
cd <LADDER_REPO_PATH>
python prismata_amf3.py proxy --capture-all
```

## What to Watch For

- `State tracker initialized` — state bridge started
- `player_index=0` or `player_index=1` — which player we are
- `Sent loading complete` — loading progress sent
- `Sent Endgrace` — grace period acknowledged
- `StartTurn: turn=N our_turn=True/False` — turn received
- `Sent EndSwoosh for opponent turn N` — EndSwoosh for Master Bot's turn
- `Sending N clicks to server: [...]` — our clicks being sent
- `Played turn N: M clicks in Xs` — our turn completed
- **NO** `PlayerDisconnected` in sniffer during gameplay = success
- Master Bot's clicks appearing in sniffer = game is progressing

## Protocol Reference

Bot game turn flow (from working real client captures):
```
=== P0 TURN (Human/Bot as P0) ===
S->C  StartTurn [timestamp]
C->S  EndSwoosh [game_id, turn_number]
C->S  Click [game_id, {_type, _id}, turn_number]  (repeat)
C->S  EndTurn [game_id, duration, turn_number, last_click]
S->C  EndTurn [duration, p0_time, p1_time, num_clicks]

=== P1 TURN (Master Bot internal) ===
S->C  StartTurn [timestamp]
(Master Bot plays internally — no clicks visible)
(Immediately proceeds to next turn)

=== P0 TURN AGAIN ===
S->C  StartTurn [timestamp]
C->S  EndSwoosh [game_id, turn_number]
...
```

Key: In bot games, Master Bot plays **instantly** with no visible clicks. The `StartTurn` for our next turn arrives together with the Master Bot turn's `StartTurn`. The human client doesn't need to send EndSwoosh for Master Bot's turn — it just arrives.
