# DeadGameBot — State Tracker Fix Continuation

**Date:** 2026-03-31
**Status:** Ready for next session
**Branch:** `ai-improvements`

## What Was Done This Session

### Protocol Fixes — COMPLETE AND WORKING

Three critical fixes that enable full bot games vs Master Bot:

1. **Deferred loading**: `ReportGameLoadProgress` must be sent AFTER `PlayerReconnected`, not immediately after `BeginGame`. The node switch during `StartBotGame` causes `PlayerDisconnected` which drops earlier loading messages. Implementation: track `_saw_disconnect` flag, send loading on `PlayerReconnected`. Fallback: 3s timeout for games without node switch.

2. **Every StartTurn is ours** (format 201): In bot games, Master Bot plays silently server-side between `EndTurn` and the next `StartTurn`. There are no "Master Bot turns" from the client's perspective. Fixed `_is_our_turn()` to always return `True` for `format == 201`. This was THE root cause of the "Master Bot hang" — the bot was sitting idle waiting for a turn that had already happened.

3. **Config**: `firstPlayer=0` (us first, for testing), `fastBotAnimation=true`.

**Evidence**: Sniffer capture of Surfinite playing a full human-vs-MB game showed that P1 (Surfinite) played EVERY turn (0-7), with Master Bot never getting a visible turn. This proved both the turn ownership model and the loading timing.

### Test Results

- **65 tests passing** (31 game_player, 4 state_bridge, 9 ai_params, 11 amf3, 9 steam_ai_bridge, 1 integration)
- **21+ commits** on `ai-improvements` branch
- **Two complete games played**: `gTJ3F-3wpVK` (74 turns, first game), `bibeT-drmUK` (41 turns)
- Bot successfully: connects, authenticates, handles stale games, loads, plays turns, sends clicks that server accepts, receives EndTurn acknowledgments

### Remaining Issue: State Tracker Divergence

The Node.js state tracker (`js_engine/state_tracker.js`) only knows about OUR clicks. Master Bot's clicks are never sent to the client in bot games. So the state tracker's view of the board diverges from reality after turn 0.

**Symptoms:**
- PrismataAI.exe receives a game state that doesn't match the real board
- AI returns suboptimal or empty moves (pass = just `space clicked:-1`)
- From ~turn 20 onwards, alternating between real moves and passes
- Some clicks may reference wrong card IDs (state tracker card IDs != server card IDs)

**Root cause**: The state tracker uses incremental click application. Without MB's clicks, our state diverges more each turn. By turn 20, the exported state is nonsensical.

## The State Tracker Problem — Solutions

### Option A: Self-Observe (Recommended)
After each EndTurn, send `ObserveGame [game_id]` to get a `BeginGame` response with `commandInfo.commandList` containing ALL clicks (both players). Re-initialize the state tracker from this data each turn.

**Pros**: Simple, uses existing infrastructure, gets authoritative state
**Cons**: Extra server message per turn, slight latency

### Option B: ReconnectGame Each Turn
Send `AttemptReconnect` to get `ReconnectGame` with full state — but this is designed for crash recovery, not per-turn use. May have side effects.

### Option C: Skip State Tracker for Bot Games
Use a different approach: since PrismataAI.exe works with full game state JSON, and the `commandInfo` from observation/reconnect has all clicks, we could replay all clicks through the state tracker once per turn to rebuild from scratch.

### Option D: Track MB Clicks from EndTurn
The S->C `EndTurn` message includes `num_clicks` for MB's turn. We know MB played but don't know WHAT. This is insufficient alone.

## Key Protocol Facts Discovered

1. **Bot game turn model**: Every `StartTurn` received is the client's turn. MB plays server-side between `EndTurn` and next `StartTurn`. No `Click` messages for MB.
2. **Loading must follow reconnect**: `PlayerDisconnected`/`PlayerReconnected` cycle happens during node switch. Loading before reconnect is dropped.
3. **S->C EndTurn format**: `[duration, p0_time, p1_time, num_clicks]` — includes MB's click count but not the clicks themselves.
4. **commandInfo from observation**: Contains `commandList` (ALL clicks, both players), `clicksPerTurn` (click count per turn). This is the authoritative record.
5. **`fastBotAnimation: true`** makes MB play instantly. `false` may trigger animation handshakes.
6. **Spectator client desyncs** when watching rapid bot turns — visual corruption, but server state is correct.

## Key Files

| Path | Description |
|------|-------------|
| `bot/game_player.py` | Game lifecycle, turn handling, deferred loading |
| `bot/ranked_bot.py` | Bot orchestrator, state machine, stale game handling |
| `bot/client.py` | Network layer, node switch, Moved handling |
| `bot/state_bridge.py` | Python↔Node.js subprocess wrapper |
| `bot/steam_ai_bridge.py` | PrismataAI.exe one-shot subprocess |
| `bot/ai_params.py` | AI parameter loading |
| `bot/config.py` | Configuration constants |
| `js_engine/state_tracker.js` | Node.js state tracker (INIT/EXPORT/CLICKS) |
| `<LADDER_REPO_PATH>\docs\PRISMATA_PROTOCOL.md` | Protocol reference |

## How to Test

```powershell
# Run all tests
cd c:/libraries/PrismataAI
python -m pytest bot/tests/ -v

# Run bot against live server (as P0)
$env:BOT_USERNAME="DeadGameBot"
$env:BOT_PASSWORD="DeadGameBot123"
python -m bot --bot-game

# Run sniffer (separate terminal)
cd <LADDER_REPO_PATH>
python prismata_amf3.py proxy --capture-all
```

## Replays from This Session

| Code | Turns | Notes |
|------|-------|-------|
| `gTJ3F-3wpVK` | 74 | First complete game. State diverges from ~turn 22, passes from then on. |
| `bibeT-drmUK` | 41 | Better — real moves through turn 30+. Some passes interspersed. |
| `dUseJ-SQpzI` | — | Early test, stale game from previous session |

## Next Session Priority

1. **Fix state tracker divergence** — Implement Option A (self-observe) or Option C (replay all clicks from observation) to give PrismataAI.exe the correct game state each turn.
2. **Switch to `_full_params`** for opening book support.
3. **Set `firstPlayer=2`** (random) once both P0 and P1 work reliably.
4. **Add resignation** when eval drops below threshold.
5. **Test multiple consecutive games** — verify the game loop (play → GameOver → cleanup → new game).
