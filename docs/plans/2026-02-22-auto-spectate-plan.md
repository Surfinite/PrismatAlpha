# Auto-Spectate Feature Plan

**Goal**: F8 hotkey initiates continuous spectating of the highest-rated ranked game. When each game ends, automatically find and spectate the next highest-rated game.

**Branch**: `feature/auto-spectate` (from current `feature/mb-issues-extraction` or `master`)

## Phase 0: Documentation Discovery — Protocol & Existing Infrastructure

### Protocol Messages (from decompiled ActionScript)

| Message | Direction | Format | Source |
|---------|-----------|--------|--------|
| `TopGamesUpdate` | S→C | `[[ {gameid, players, ratings, started, timeControl, units, ...}, ... ]]` | `LocalUser.as:124,653-675` |
| `ObserveTopGame` | C→S | `["ObserveTopGame", gameid]` | `UIFeaturedGameButton.as:285` |
| `ObserveGame` | C→S | `["ObserveGame", gameID]` | `PeerAction.as:66` |
| `QuitGame` | C→S | `["QuitGame", serverID]` | `Game.as:1094` |
| `BeginGame` | S→C | `[{liveGameID, mergedDeck, laneInfo, commandInfo, ...}]` | `GameInitializationInfo.as:128` |
| `GameOver` | S→C | `[winner, loser, replayCode, ...]` | Sniffer line 527 |

### Key Facts

- **TopGamesUpdate is server-pushed** — no client request needed. Arrives periodically while in lobby.
- **`serverID` == `liveGameID`** from BeginGame params (`GameInitializationInfo.as:128`).
- **Game scoring formula** (`GameStub.as:52-57`): `score = avg_rating - 100 * started_ms / 60000` — higher-rated, newer games sort first.
- **After GameOver**, client calls `exitGame()` → returns to lobby automatically (`Game.as:1052-1062`).
- **Sniffer already has**: `_inject_msg()` (line 407), msgId offset tracking (line 364), Ping rewrite (line 1176), `@on_message` decorator, `Session` class, chat trigger polling loop (line 1467).
- **No `TopGamesUpdate` handler exists yet** in sniffer.
- **No keyboard listener exists** — only F6 send via `SendInput`.
- **F8 virtual key code**: `0x77`.

### Anti-Pattern Guards

- **Do NOT send a request to get TopGamesUpdate** — server pushes it automatically. Just listen.
- **Do NOT try to click UI buttons** — inject protocol messages directly via `_inject_msg()`.
- **Do NOT use `ObserveGame`** for featured games — use `ObserveTopGame` (the server distinguishes them; `ObserveGame` is for peer spectating).
- **Do NOT use external keyboard libraries** (`pynput`, `keyboard`) — use Win32 `GetAsyncKeyState` in the existing polling loop. Zero new dependencies.

---

## Phase 1: Capture TopGamesUpdate & Store Game List

**What to implement**: Add a `@on_message("TopGamesUpdate")` handler that parses the game list, scores each game, and stores the sorted list on the Session object.

### Tasks

1. **Add Session fields** (after line 365):
   ```python
   self.top_games = []         # Sorted list of {gameid, players, ratings, score}
   self.live_game_id = None    # serverID/liveGameID of current spectated game
   self.auto_spectate = False  # Whether auto-spectate loop is active
   ```

2. **Add `@on_message("TopGamesUpdate")` handler** (near line 550):
   - Parse `params[0]` as array of game objects
   - Filter games with `started < 15 * 60 * 1000` (match client filter, `LocalUser.as:660`)
   - Score each game: `score = (ratings[0] + ratings[1]) / 2 - 100 * started / (1000 * 60)`
   - Sort descending by score
   - Store on `session.top_games`
   - Print count: `[spectate] {N} top games available (best: {players} {avg_rating})`

3. **Capture `liveGameID` from BeginGame** — extend `_handle_begin_game_live` (line 836):
   - Extract `info.get("liveGameID")` and store as `session.live_game_id`

### Verification

- Run sniffer, go to lobby, check console prints `[spectate] N top games available`
- Verify games are sorted by score (highest first)

---

## Phase 2: F8 Hotkey Detection & ObserveTopGame Injection

**What to implement**: Poll for F8 keypress in the existing trigger loop. On F8, pick the best game and inject `ObserveTopGame`.

### Tasks

1. **Add `GetAsyncKeyState` setup** (near the existing Win32 constants, ~line 600):
   ```python
   _VK_F8 = 0x77
   _user32 = ctypes.windll.user32
   ```

2. **Add `inject_observe_top_game()` to Session** (after `inject_global_chat`, ~line 405):
   ```python
   def inject_observe_top_game(self, gameid):
       """Inject ObserveTopGame to start spectating a featured game."""
       return self._inject_msg(["ObserveTopGame", str(gameid)], f"spectate {gameid[:8]}")

   def inject_quit_game(self):
       """Inject QuitGame to leave current game and return to lobby."""
       with self._lock:
           gid = self.live_game_id
       if gid:
           return self._inject_msg(["QuitGame", str(gid)], "quit game")
       return False
   ```

3. **Add F8 polling in trigger loop** (inside `while True` at line 1467):
   ```python
   # Check F8 for auto-spectate toggle
   if _user32.GetAsyncKeyState(_VK_F8) & 0x0001:  # Key was pressed since last check
       session.auto_spectate = not session.auto_spectate
       if session.auto_spectate:
           print("[spectate] Auto-spectate ENABLED — looking for games...")
           _start_spectating_best(session)
       else:
           print("[spectate] Auto-spectate DISABLED")
   ```

4. **Implement `_start_spectating_best(session)`**:
   - Check `session.top_games` is non-empty
   - If currently in a game (`session.game_phase == "playing"`), send `QuitGame` first, sleep 1s
   - Pick `top_games[0]` (highest scored)
   - Skip if it's the same game we're already watching (`gameid == session.live_game_id`)
   - Call `session.inject_observe_top_game(gameid)`
   - Print: `[spectate] Observing: {players[0]} ({rating0}) vs {players[1]} ({rating1})`

### Verification

- Run sniffer, be in lobby, press F8
- Console should show "Auto-spectate ENABLED" then "Observing: ..."
- Client should transition into spectator mode
- Press F8 again to toggle off

---

## Phase 3: Auto-Cycle on GameOver

**What to implement**: When a spectated game ends and auto-spectate is active, automatically find and watch the next best game after a brief delay.

### Tasks

1. **Extend GameOver handler** (`_handle_game_over`, line 527):
   - After capturing replay code, check `session.auto_spectate`
   - If active, schedule next spectate after 3s delay (let client return to lobby and receive fresh TopGamesUpdate):
     ```python
     if session.auto_spectate:
         threading.Timer(3.0, _start_spectating_best, args=[session]).start()
         print("[spectate] Next game in 3s...")
     ```

2. **Same for `_handle_game_over_draw`** (line 539):
   - Add identical auto-cycle logic

3. **Handle "no games available"**:
   - If `session.top_games` is empty when trying to spectate, print `[spectate] No ranked games — waiting...`
   - Use a retry: check again after 10s (the server will push fresh TopGamesUpdate)
   - Max 6 retries (1 minute), then print `[spectate] Giving up — press F8 to retry`

4. **Avoid re-spectating the same game**:
   - Track `session._last_spectated_id`
   - Skip games matching this ID (the GameOver just fired for it, but TopGamesUpdate might still list it briefly)

### Verification

- Enable auto-spectate, watch a game finish
- Console should show "Next game in 3s..." then auto-start spectating
- If no games available, should see retry messages
- Replay codes should accumulate in `bin/prismata_capture_codes.txt`

---

## Phase 4: Polish & Edge Cases

### Tasks

1. **Status display**: When auto-spectate is active, show a periodic heartbeat in console:
   - Every 30s while spectating: `[spectate] Watching: {players} (turn {N}) — {M} games in queue`

2. **Skip non-ranked games**: TopGamesUpdate may include casual games. Filter by `timeControl` containing "Ranked" or check for rating presence (both players should have ratings > 0).
   - **NOTE**: Need to verify what `timeControl` values look like for ranked vs casual. The screenshot shows "Relaxed (60s)" — check if ranked games have a different format or if there's a `ranked` field in GameStub.

3. **Console output**: Print `[spectate] ON` / `[spectate] OFF` status on F8 toggle. When cycling, show game count: `[spectate] Game 3 — Observing: ...`

4. **Graceful shutdown**: On Ctrl+C, if auto-spectate is active, mention total games watched.

### Verification

- Full end-to-end: F8 → spectate → game ends → auto-cycle → spectate → F8 to stop
- Verify replay codes captured for all spectated games
- Verify no crashes from rapid game transitions or empty game lists

---

## Implementation Notes

- **All changes in ONE file**: `tools/prismata_sniffer.py` — no new files needed
- **~80-120 lines of new code** estimated
- **Zero new dependencies** — Win32 GetAsyncKeyState is already available via ctypes
- **Thread safety**: All Session access through `_lock` or `_c2s_lock`. Timer callbacks use `_start_spectating_best()` which calls `_inject_msg()` (already thread-safe).
- **The client handles all UI transitions** — we just inject protocol messages, the Adobe AIR app does the rendering/transitions.

## Open Questions

1. **Ranked vs casual filter**: Does TopGamesUpdate include a `ranked` field, or do we infer from `timeControl` string? May need to check a captured TopGamesUpdate message to see the exact fields. The screenshot shows "Relaxed (60s)" which is a time control, not a game mode indicator.
2. **F8 focus**: `GetAsyncKeyState` works globally (no focus required). This means F8 will trigger even if Prismata isn't focused. This is probably desirable (can be in Claude Code and press F8) but worth noting.
3. **Multiple proxied connections**: If client reconnects (Moved redirect), the Session persists but `server_sock` changes. `_inject_msg` already handles this correctly.
