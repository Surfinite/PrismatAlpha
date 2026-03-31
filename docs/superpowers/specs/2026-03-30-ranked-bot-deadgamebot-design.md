# DeadGameBot — On-Demand Ranked Bot

**Date:** 2026-03-30
**Status:** Design approved
**Repo:** PrismataAI

## Problem

Prismata's player base is small. New players (like Tasselfoot) queue for ranked and find no opponents. Creating smurf accounts requires leveling to 20 and has matchmaking cooldowns. There's no way to get a ranked game on demand.

## Solution

An always-listening bot account (**DeadGameBot**) that queues ranked on demand when a player presses a button on `deadgame.prismata.live`. The bot plays using Steam's `PrismataAI.exe` (Master Bot) with 7s think time — the same AI that's already in the game, just available in ranked.

## Architecture

```
deadgame.prismata.live              Your PC (Windows)
┌──────────────────────┐           ┌──────────────────────────┐
│  "Queue DeadGameBot" │  polling  │  ranked_bot.py           │
│   button             │◄─────────│                          │
│                      │  status   │  ┌─ TriggerPoller ────┐  │
│  GET /api/bot/status │◄─────────│  │ polls site /5s      │  │
│  POST /api/bot/queue │           │  │ sends heartbeats    │  │
│                      │           │  └────────┬────────────┘  │
│  Status indicator:   │           │           │               │
│  Online/Offline      │           │  ┌────────▼────────────┐  │
│  Idle/Playing        │           │  │ HeadlessGameClient   │  │
└──────────────────────┘           │  │                      │  │
                                   │  │ • AMF3 protocol      │  │
                                   │  │ • Auth + connection   │  │
                                   │  │ • Queue ranked        │  │
                                   │  │ • Receive game state  │  │
                                   │  │ • Send clicks         │  │
                                   │  └────────┬────────────┘  │
                                   │           │               │
                                   │  ┌────────▼────────────┐  │
                                   │  │ PrismataAI.exe       │  │
                                   │  │ (Steam Master Bot)   │  │
                                   │  │ stdin → stdout       │  │
                                   │  │ 7s think time        │  │
                                   │  └─────────────────────┘  │
                                   └──────────────────────────┘
```

## Bot Process (`ranked_bot.py`)

Single Python script in PrismataAI repo. Extends headless client connection logic (copied/adapted from <ladder>'s `headless_client.py` and `prismata_amf3.py`).

### States

```
IDLE ──trigger──→ QUEUING ──matched──→ PLAYING ──game over──→ IDLE
                     │                                          ▲
                     └──timeout 60s─────────────────────────────┘
```

- **IDLE**: Connected to Prismata server, authenticated, polling deadgame.prismata.live for queue requests. Not in any queue.
- **QUEUING**: Sent ranked queue message, waiting for match. Times out after ~60s and returns to IDLE.
- **PLAYING**: In a game. Each turn: convert server state → call PrismataAI.exe → send clicks back. Returns to IDLE after GameOver.
- **OFFLINE**: Bot process not running (site shows "offline").

### Components

**1. AMF3 Protocol Layer**

Copied from `<ladder>/prismata_amf3.py`:
- `encode_amf3_value()` / `decode_amf3_value()` — binary serialization
- Message framing: 4-byte big-endian length prefix + AMF3 payload
- `["Msg", msgId, innerMessage]` wrapper for reliable delivery

**2. HeadlessGameClient**

Adapted from `<ladder>/headless_client.py`:
- Dual TCP connection (main port 11600, TLS port 11601)
- PBKDF2 auth with HMAC-SHA256 courier claiming
- `Moved` handling during login (server load balancing)
- Ping/Pong keepalive
- `_send_main(msg)` / `_send_secure(msg)` for outbound messages

New capabilities:
- `queue_ranked()` — sends ranked queue message (protocol TBD from sniffer capture)
- `cancel_queue()` — cancels queue if timeout
- `send_click(click_data)` — sends `["Click", click_data]` to server
- `send_end_turn()` — sends `["EndTurn"]` to server
- `send_end_swoosh()` — sends `["EndSwoosh"]` to server

**3. GamePlayer**

Manages the game lifecycle:
- On `BeginGame`: stores `mergedDeck`, card definitions, player index (which side are we?)
- On opponent's `Click`/`ManyClicks`/`EndTurn`: tracks turn state
- On our turn (`StartTurn` or equivalent): calls SteamAIBridge, sends resulting clicks
- On `GameOver`/`GameOverDraw`: sends `QuitGame`, transitions to IDLE

**4. SteamAIBridge**

Python reimplementation of `js_engine/steam_ai.js` (~30 lines):
- Spawns `PrismataAI.exe` as subprocess
- Writes JSON to stdin: `{ mergedDeck, gameState, aiParameters, aiPlayerName: "HardestAI" }`
- Reads JSON from stdout: `{ aiclicks: [...], aithinktime, eval, eval_pct }`
- One-shot process per turn (fresh spawn each time)
- Timeout: 15s (7s think + 8s overhead)
- Strips control characters from stdout before JSON parsing

**5. TriggerPoller**

- Polls `GET https://deadgame.prismata.live/api/bot/status` every 5s
- When `pending_request` is true, transitions bot to QUEUING
- Sends heartbeat via `POST /api/bot/heartbeat` every 10s (so site knows bot is online)
- Reports state changes: `POST /api/bot/update-status { state: "idle"|"queuing"|"playing" }`

### Turn Flow

```
Server → Bot:  BeginGame(init_info)
  Bot stores: mergedDeck, playerInfo, our player index

Server → Bot:  Click / ManyClicks / EndTurn  (opponent moves, if we're P2)
  Bot: tracks that it's now our turn

Server → Bot:  [Our turn signal - exact message TBD from sniffer]
  Bot → PrismataAI.exe:  { mergedDeck, gameState, aiParameters, aiPlayerName: "HardestAI" }
  PrismataAI.exe → Bot:  { aiclicks: [{_type, _id}, ...], eval, aithinktime }
  Bot → Server:  ["Click", {_type, _id}]  × N clicks
  Bot → Server:  ["EndTurn"]

Server → Bot:  GameOver(winner, loser, replayCode)
  Bot → Server:  ["QuitGame", gameId]
  Bot: logs result, transitions to IDLE
```

### State Conversion

The critical transformation is: server's `BeginGame` init_info → PrismataAI.exe input format.

The server sends game state in its own format. `PrismataAI.exe` expects the format that the F6 clipboard export produces:
```json
{
  "mergedDeck": [...card definitions...],
  "gameState": { "table": [...], "cards": [...], "whiteMana": "...", ... },
  "aiParameters": { ...standard HardestAI params... },
  "aiPlayerName": "HardestAI"
}
```

The exact mapping between server format and PrismataAI input format needs to be determined during the protocol capture phase. The sniffer already logs the full `BeginGame` payload, and we know the PrismataAI input format from `matchup_clean.js`.

### Click Translation

Server clicks may use a different format than PrismataAI output clicks. PrismataAI outputs:
```json
{ "_type": "card clicked", "_id": 0 }
{ "_type": "inst clicked", "_id": 42 }
{ "_type": "space clicked", "_id": -1 }
```

The server's `Click` message format will be captured during protocol sniffing. If the format differs, a translation layer converts between them.

## Access Gating

The button is gated behind the prismata.live login system. Only players who have linked a Prismata account can use it, with a rating-based restriction.

### Gating Logic

```
Player presses "Queue DeadGameBot" button
  → Must be logged in with linked Prismata account
  → Look up player's most recent rating in ladder DB
  → If no data found: ALLOW (assume new player, exactly the target user)
  → If rating < 1600: ALLOW
  → If rating >= 1600: DENY ("You're in the human pool now!")
```

### Rating Lookup

Query the <ladder> SQLite DB on the site box for the player's most recent game. The spectator bots record every game with ratings, so any player who has played ranked while the bots were watching will have data.

### Rationale

- **1600 cutoff**: Master Bot is ~1200 ELO. Players start at 1200. Getting from 1200 to 1600 requires ~30+ wins against the bot (small ELO gains from even matchup), providing real practice. At 1600, the 500-ELO matching window reaches up to 2100, where the active human players are.
- **No data = allow**: Brand new players are the exact target audience. They have no replay history.
- **Login required**: Prevents anonymous spam, creates accountability, links to a real Prismata account.
- **Anti-abuse**: High-rated players can't use the bot. Combined with 10-min cooldown per account.

## Trigger Site (`deadgame.prismata.live`)

### Backend

Minimal Express app on the site box (port 3101), or additional routes on the existing fabricate server (port 3100). In-memory state only for bot state — rating lookups hit the ladder DB.

**Endpoints:**
- `GET /` — serves single-page frontend
- `GET /api/bot/status` — returns `{ state, last_game, last_request, online }`
- `POST /api/bot/queue` — sets pending queue request (requires login, rating check, 10-min cooldown per account)
- `POST /api/bot/heartbeat` — bot reports it's alive (called every 10s)
- `POST /api/bot/update-status` — bot reports state changes

**State (in-memory):**
```js
{
  bot_state: "idle" | "queuing" | "playing" | "offline",
  pending_request: false,
  last_heartbeat: timestamp,
  last_request_by_user: { username: timestamp },  // cooldown tracking (per-account, not per-IP)
  last_game: { opponent, result, replay_code, timestamp }  // most recent game
}
```

Bot is "online" if `last_heartbeat` < 30s ago. If offline, the queue button is disabled.

### Frontend

Single HTML page. Requires login:
- Status indicator: green dot = online/idle, yellow = queuing, red = playing, grey = offline
- One big button: "Queue DeadGameBot"
- Cooldown timer shown after pressing (10 min)
- Last game result (opponent, win/loss, replay code link)
- Brief explanation text: "DeadGameBot is Master Bot (7s) on a ranked account. Press the button and it'll queue up for you."
- If rating >= 1600: button disabled with message "Your rating is high enough to find human opponents!"
- If not logged in: button disabled with "Log in with your Prismata account to use this"

### Nginx + SSL

Same pattern as `fabricate.prismata.live`:
- nginx vhost on site box proxying to port 3101
- certbot SSL certificate
- Or: add `/deadgame/` routes to the existing fabricate Express server to avoid a separate service

### Deployment

Either:
- **Separate service**: `deadgame.service` on port 3101, own nginx vhost
- **Shared with fabricate**: add routes to fabricate's Express server, reuse port 3100

Recommendation: **separate service** — keeps concerns isolated, easy to stop/start independently.

## Protocol Capture Plan

Before implementation, we need to capture two sets of protocol messages using the sniffer/proxy:

### Capture 1: Play vs Bot

1. Start `prismata_amf3.py` sniffer (or run Prismata through the proxy)
2. In Prismata client, start a game vs Master Bot
3. Play a few turns, let the game finish
4. Capture the full message log

**Looking for:**
- How "Play vs Bot" is initiated (what message starts the game?)
- `BeginGame` payload format for a real game
- How `Click` messages look when sent from client → server
- `EndTurn` / `EndSwoosh` client → server format
- Turn transition signals (how does the client know it's its turn?)
- `GameOver` and post-game flow

### Capture 2: Ranked Queue

1. Same sniffer setup
2. Queue for ranked (may need two accounts to actually get a match, or just capture the queue/cancel messages)
3. Capture queue initiation and cancellation messages

**Looking for:**
- Message name and format for joining ranked queue
- Message for cancelling/leaving queue
- Match found notification format
- Any differences from "Play vs Bot" game flow

## Implementation Phases

### Phase 1: Protocol Capture & SteamAI Bridge
- Run sniffer, capture Play vs Bot + ranked queue messages
- Document all discovered message formats
- Implement Python SteamAI bridge (spawn PrismataAI.exe, stdin/stdout)
- Unit test: feed a known game state, verify click output

### Phase 2: Bot Plays vs Master Bot
- Copy/adapt AMF3 codec and connection logic from <ladder>
- Implement HeadlessGameClient with auth and game-playing messages
- Implement GamePlayer turn loop
- Implement state conversion (server format → PrismataAI input)
- Bot connects, starts a game vs in-game Master Bot, plays to completion
- Validate via console output (turns, clicks, eval, result)

### Phase 3: Bot Plays Ranked
- Add ranked queue/cancel messages
- Test: bot queues ranked, plays a game (spectatable from another account)
- Handle edge cases: queue timeout, disconnect during game, opponent resignation

### Phase 4: Trigger Site (deadgame.prismata.live)
- Express server on site box with status/queue/heartbeat endpoints
- Single-page frontend with button, status, cooldown
- nginx vhost + SSL
- Bot polls trigger endpoint, queues on demand

### Phase 5: Polish
- Status indicator on site (online/offline/playing)
- Last game result display
- Error recovery (reconnect on disconnect, re-auth on session expire)
- Logging and monitoring
- Move bot to Windows VPS if demand warrants it

## Key Files (Planned)

| Path | Description |
|---|---|
| `bot/ranked_bot.py` | Main bot process |
| `bot/amf3.py` | AMF3 codec (adapted from <ladder>) |
| `bot/headless_game_client.py` | Server connection + game-playing protocol |
| `bot/steam_ai_bridge.py` | PrismataAI.exe subprocess wrapper |
| `bot/game_player.py` | Turn loop and state conversion |
| `bot/trigger_poller.py` | Polls deadgame.prismata.live for queue requests |
| `bot/config.py` | Account credentials, paths, settings |
| `deadgame/server.js` | Express trigger server (site box) |
| `deadgame/public/index.html` | Frontend SPA |
| `deadgame/deadgame.service` | systemd unit |
| `deadgame/deadgame.nginx.conf` | nginx vhost |

## Account

- **Name:** DeadGameBot
- **Purpose:** Ranked games only, on-demand via trigger
- **AI:** Steam's PrismataAI.exe (Master Bot), 7s think time
- **Framing:** "It's literally the in-game Master Bot, just queuing ranked so you have someone to play against"

## Open Questions

1. **Server game state format**: Exact `BeginGame` payload structure — will be determined during protocol capture.
2. **Click message format**: Whether server clicks use the same `{_type, _id}` format as PrismataAI output — will be determined during protocol capture.
3. **Turn signal**: How the server tells the client it's their turn — `StartTurn` message? Or inferred from `EndTurn` of opponent? Will be determined during protocol capture.
4. **EndSwoosh**: When/if the bot needs to send `EndSwoosh` — the swoosh animation is client-side, but the server may wait for it. Will be determined during protocol capture.
5. **Account level requirement**: Does the bot account need to reach level 20 for ranked? If so, how to level it up efficiently.
6. **Defense/breach handling**: PrismataAI.exe handles defense and breach clicks. Need to verify the server accepts these in the same format. The auto-breach logic in matchup_clean.js may or may not be needed depending on how the server handles breach assignment.
