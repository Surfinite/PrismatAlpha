# Prismata Browser Client — Design Specification

> **Date**: 2026-03-20
> **Status**: Draft
> **Author**: Surfinite + Claude

## 1. Vision

A browser-based Prismata client that lets the community watch live games and eventually play — replacing the dead Flash client with a modern React interface that lives on the ladder site.

Think CaptureAge for Prismata: starts as a spectating tool, becomes the primary way to experience the game.

## 2. Design Principles

### 2.1 Community First
The primary goal is giving the community a way to watch and play Prismata in a browser. Every architectural decision serves this.

### 2.2 Zero Server Overhead
Spectating uses Wonderboat's existing headless spectator infrastructure. Playing uses a local proxy. Nothing adds load to Lunarch's servers beyond what a normal client would create.

### 2.3 AI Overlay — Spectating Only (Hard Gate)
AI evaluation overlays (eval bars, suggested moves, "who's winning") are **exclusively** available in spectating mode. The system enforces this architecturally:

- The `GameContext` carries a `mode` field (`"spectating"` or `"playing"`) set at connection time
- `EvalOverlay` checks `mode !== "playing"` — if playing, the component does not mount (not hidden, not disabled — absent from the DOM entirely)
- `sendClick()` is null in spectating mode; `--suggest` is null in playing mode — the eval overlay and click handler cannot coexist
- The `--suggest` AI endpoint is only exposed by the hosted spectating server, never by the local play proxy

This is a design constraint, not a guideline. We provide zero pathway from spectating analysis to live-game assistance.

## 3. Architecture

### 3.1 Hybrid Deployment (Approach C)

**Spectating** is hosted on the ladder site — one proxy, many viewers, zero friction.
**Playing** is local — each player runs their own proxy, full control, no credential sharing.

```
SPECTATING (hosted):
  Wonderboat's headless spectator
    → TCP/AMF3 → Lunarch server
    → WebSocket broadcast (read-only) → Ladder site /live page
    → Any number of browser viewers

PLAYING (local):
  Player's local proxy (Python)
    → TCP/AMF3 → Lunarch server
    ← WebSocket (bidirectional) → Browser at localhost
```

### 3.2 Shared React Component Library

Components are written once, used in both contexts:

| Component | Status | Description |
|-----------|--------|-------------|
| `UnitCard` | Built (replay viewer) | Glass-card unit tile with art, health, attack, status |
| `CardLane` | Built (replay viewer) | Row of grouped/overlapping units |
| `BuyPane` / `BuyRow` | Built (replay viewer) | Sidebar with AS3-correct sort order |
| `ResourceDisplay` | Built (replay viewer) | Player resource pips |
| `GameHeader` | Partial (replay viewer header) | Player names, ELO, turn indicator, phase, timer |
| `ChatPanel` | New | Tabbed global channels + PM conversations |
| `LiveGameList` | New | Top live games from `TopGamesUpdate`, click to spectate |
| `ConnectionStatus` | New | Proxy connection state indicator |
| `ClickHandler` | New (Phase 2) | Translates React clicks → game protocol clicks |
| `EvalOverlay` | New (Phase 3) | AI eval bar, suggested moves (spectating only) |
| `FriendList` | New (Phase 1c) | Online friends, status indicators |

All components communicate through a `GameContext` provider holding: game state, chat messages, connection status, mode (`spectating`/`playing`), and (in play mode) a `sendClick()` function.

**Note**: The "Built" components exist in `<ladder>-site/src/app/replay/[code]/page.tsx` as part of the replay viewer (inline in the page file). They will need to be extracted into a shared component library for reuse across spectating and play contexts.

### 3.3 WebSocket Protocol

Thin JSON translation layer between proxy (AMF3) and browser (JSON).

**Browser → Proxy (local play only):**
```json
{"type": "auth", "method": "password", "username": "X", "password": "Y"}
{"type": "auth", "method": "token", "token": "captured_session_data"}
{"type": "click", "_type": "card clicked", "_id": 3}
{"type": "endTurn"}
{"type": "chat", "channel": "globalEnglish", "text": "gg"}
{"type": "pm", "target": "Wonderboat", "text": "good game"}
{"type": "spectate", "gameId": "game_abc123"}
```

**Proxy → Browser (both modes):**
```json
{"type": "gameInit", "deckInfo": {...}, "players": [...], "initInfo": {...}}
{"type": "click", "player": 1, "_type": "inst clicked", "_id": 42}
{"type": "gameStart", "players": [...], "ratings": [...], "randomizer": [...]}
{"type": "gameOver", "winner": 0, "replayCode": "XXXXX-XXXXX"}
{"type": "chat", "channel": "globalEnglish", "from": "Player1", "text": "gl hf"}
{"type": "pm", "from": "Wonderboat", "text": "good game"}
{"type": "topGames", "games": [{...}]}
{"type": "turnStart", "player": 0, "timeRemaining": 45}
{"type": "connected", "username": "Surfinite"}
{"type": "error", "message": "Auth failed"}
```

## 4. Protocol Details

### 4.1 Lunarch Server Communication
- **Transport**: TCP sockets, ports 11600 (game) and 11601 (TLS auth)
- **Serialization**: AMF3 (binary Flash format)
- **Wire format**: 4-byte big-endian length prefix + AMF3-encoded array
- **Reliability**: Courier layer with message IDs, Ping/Pong keepalive every 6 seconds, Fibonacci reconnection backoff

### 4.2 Key Server Messages

| Message | Direction | Format | Purpose |
|---------|-----------|--------|---------|
| `Click` | C→S | `["Click", serverId, {_type, _id}, turnNum]` | Player action |
| `EndTurn` | C→S | `["EndTurn", serverId, timeTaken, turnNum, finalClick]` | End turn |
| `Click` | S→C | `["Click", {_type, _id}]` | Opponent's action |
| `ManyClicks` | S→C | `["ManyClicks", [{_type, _id}, ...]]` | Opponent's batch |
| `BeginGame` | S→C | `["BeginGame", gameInfo]` | Game init (players, deck, randomizer) |
| `GameOver` | S→C | `["GameOver", winner, loser, replayCode, ...]` | Game result |
| `TopGamesUpdate` | S→C | `["TopGamesUpdate", gamesList]` | Live game list |
| `ObserveTopGame` | C→S | `["ObserveTopGame", gameId]` | Start spectating |
| `ManyClicks` | S→C | `["ManyClicks", [{_type, _id}, ...]]` | Batch opponent clicks |
| `EndSwoosh` | C→S | `["EndSwoosh", serverId, turnNum]` | Defense phase complete |
| `Chat` | Both | `["Chat", channel, text]` | Global chat |
| `PrivateChat` | Both | `["PrivateChat", targetId, text]` | Private message |
| `StartTurn` | S→C | `["StartTurn", serverTime]` | Turn begins |
| `Moved` | S→C | `["Moved", newIp, mainPort, tlsPort]` | Server redirect (load balancing) |
| `FixLateClicks` | S→C | `["FixLateClicks", turnNum, [clicks]]` | Server corrections |

### 4.3 Authentication
Two supported paths:
1. **Username/password**: PBKDF2 hash (HMAC-SHA256, 1000 iterations) sent via secure courier on TLS port
2. **Captured Steam token**: Session token from existing client connection, replayed on new connection

### 4.4 Message Injection
Wonderboat's proxy already supports `_inject_msg()` for sending arbitrary AMF3 messages to the server. This is the mechanism for click submission in play mode. Message ID tracking with offset patching ensures injected messages don't break the client↔server sequence.

### 4.5 State Reconstruction Architecture
The Lunarch server does NOT push full game state — it sends `BeginGame` (initial deck/players) then individual clicks. Game state must be reconstructed by replaying clicks from the initial state.

**Architecture**: The browser runs the JS engine locally. The proxy sends raw clicks over WebSocket. The browser applies each click to its local JS engine state and re-renders. This matches the existing replay viewer pattern and avoids the proxy needing to run Node.js server-side.

- `gameInit` WebSocket message carries the full `BeginGame` data (deck, players, init info)
- Subsequent `click` messages carry individual opponent actions
- Browser's JS engine (`PrismataViewer`) processes each click and updates React state
- This is the same pipeline as the replay viewer, just fed from live WebSocket instead of S3

### 4.6 AMF3 Encoder Gaps
The existing AMF3 encoder (`prismata_sniffer.py`) handles `str`, `int`, `float`, `list`, `None`, `bool` — but NOT `dict`. Click messages to the server contain dict objects (`{_type, _id}`). The encoder must be extended with AMF3 dynamic object support before Phase 2 (live play). The decoder already handles this complexity (sniffer lines 177-230), so the format is understood.

### 4.7 WebSocket Bridge — New Infrastructure
The WebSocket layer between proxy and browser is new code. It requires:
- WebSocket server (Python `websockets` or `aiohttp` library)
- JSON serialization of AMF3-decoded messages
- Connection management (broadcast to multiple spectators)
- Bidirectional routing for play mode
- Reconnection handling (separate from the AMF3 courier's Fibonacci backoff)
- `Moved` message transparency — server load-balancing redirects must be handled by the proxy without disrupting the WebSocket connection

### 4.8 Scaling Constraints
One headless spectator account can spectate one game at a time (`currently_spectating = None` in `headless_client.py`). To show N concurrent live games on the ladder site, N headless accounts are needed. `headless_multi.py` already coordinates multiple accounts. The number of simultaneously viewable games is bounded by available accounts.

### 4.9 Auth UX Detail
**Password auth**: Browser sends credentials over `ws://localhost` (plaintext WebSocket). This is acceptable because traffic never leaves the local machine. The proxy performs PBKDF2 and communicates with Lunarch over TLS (port 11601).

**Steam token capture**: Player runs the real Steam client with the proxy active. Proxy captures session token at login and saves to `headless_session.json`. Player then pastes or auto-loads this token in the browser. Token lifetime and IP-binding are not fully documented — needs empirical testing.

**Credential storage**: The headless client uses base64 "obfuscation" (not encryption). This is a known limitation — adequate for local use, not for shared/hosted systems.

### 4.10 Server-Side Credential Management
Headless spectator account credentials live on Wonderboat's server. These are real Prismata accounts. Credential rotation, access control, and protection of these accounts should be agreed with Wonderboat before deployment.

## 5. Verification Strategy

### 5.1 Click Legality Validation
During spectating, the browser's JS engine processes each relayed click. If a click is rejected by the engine (illegal action), this indicates proxy relay corruption — a click was garbled, lost, or delivered out of order. This catches transport errors in real-time. Note: this validates click legality, not full state comparison (the server doesn't send state snapshots to compare against).

### 5.2 Post-Game Replay Comparison
After any live game completes, the replay becomes available on S3. The verification pipeline:
1. Proxy logs all AMF3 messages during the game
2. After `GameOver`, fetch the S3 replay
3. Replay the logged messages through `replay_validator.js`
4. Compare final state and winner against S3 replay
5. Report any discrepancies

### 5.3 Batch Validation
`batch_validate.py` already validates 1000 random replays at 99.5% pass rate. This same infrastructure validates that the JS engine (shared by the React viewer) processes games correctly.

### 5.4 AMF3 Round-Trip Testing
Unit tests for the AMF3 codec: encode a message, decode it, verify it matches the original. Critical because a single byte error in AMF3 encoding would corrupt game actions.

## 6. Phases

### Phase 1a — Live Spectating
- WebSocket broadcast layer added to `prismata_sniffer.py`
- `/live` page on ladder site: `LiveGameList` → click → React board with real-time clicks
- Parallel JS engine validation running alongside
- Playback controls: pause live feed, rewind, catch up to live
- `ConnectionStatus` component

### Phase 1b — Chat
- `ChatPanel` component: tabbed global channels + PM conversations
- Proxy relays `Chat` and `PrivateChat` messages bidirectionally
- Same component used in both spectating and play contexts
- All global channels supported (English, French, etc.), English as default tab

### Phase 1c — Social Features (can be parallel with Phase 2)
- Friend list (`FriendsList` server message research from AS3 source needed)
- Chat commands: `/whisper`, `/block`, `/friend`, `/unfriend`
- Online status indicators
- Requires additional server message types to be reverse-engineered
- **Non-blocking**: Phase 2 does not depend on 1c. Can be developed in parallel or deferred.

### Phase 2 — Live Play
- Local proxy launcher script: starts proxy + WebSocket bridge, opens browser
- Auth flow: password entry in browser or captured Steam token
- `ClickHandler`: translates React UI interactions → `["Click", ...]` protocol messages
- Game queue / accept challenge flow
- Turn timer display with bank time
- Verification: record all games, validate against S3 replay after completion

### Phase 3 — AI Overlays (Spectating Only)
- `EvalOverlay`: calls `--suggest` on current state, displays eval + best move
- Attack/defense prediction for next turn
- "Who's winning" indicator from DSNN evaluation
- Hard-gated to spectating mode (see Section 2.3)

### Phase 4 — AI Play
- AI player mode: proxy auto-submits AI-computed clicks each turn
- Uses `--suggest` CLI mode: spawns fresh `Prismata_Testing.exe` per turn (NeuralNet singleton constraint — cannot reuse process)
- Configurable AI backend (SteamAI, DSNN, LiveHardestAI, UCT)
- Think time controls and rate limiting to be respectful of server
- Uses same local proxy infrastructure as Phase 2

## 7. User Experience

### 7.1 Spectating (hosted — zero install)
1. Visit ladder site → `/live` page
2. See list of live games (auto-updating)
3. Click a game → watch in real-time with React board
4. Chat visible alongside the game

### 7.2 Playing (local — launcher script)
1. Run `python prismata_launcher.py` (or double-click a script)
2. Browser opens to `localhost:3000`
3. Enter username/password OR paste captured Steam token
4. See lobby: live games, chat, game queue
5. Queue for a game or accept a challenge
6. Play using the React board — clicks sent through local proxy to Lunarch server
7. After game: replay code shown, game validated against S3 replay

### 7.3 Future: Desktop App (Phase 5+)
Wrap the local proxy + browser in an Electron shell or PyInstaller + WebView. Same code, packaged as a one-click install. No architectural changes needed — purely a distribution concern.

## 8. Dependencies & Risks

### 8.1 Lunarch Server Availability
The live game features depend on Lunarch's servers. If they shut down, live play and spectating against human opponents would stop. However, the community has a viable fallback: the JS engine contains the complete game rules (validated against 102K replays), the React board handles rendering, and the AMF3 protocol is fully understood. A community-hosted game server using the JS engine for click validation and a WebSocket relay for player matching is architecturally straightforward. This is a contingency, not a current goal — but it significantly reduces the existential risk.

### 8.2 Protocol Changes
If Lunarch updates the server protocol, the AMF3 codec and message handling may need updates. Mitigated by the AMF3 round-trip tests and post-game validation catching issues quickly.

### 8.3 Server-Side Validation
Lunarch's server validates all clicks. Malformed or illegal clicks will be rejected. The verification layer catches these during testing so they never reach production.

### 8.4 Community Trust
The AI overlay restriction (Section 2.3) is critical for community acceptance. Any perception that this tool enables cheating would be fatal to adoption.

## 9. Existing Infrastructure Leveraged

| Component | Location | Reused For |
|-----------|----------|------------|
| React game board | `<ladder>-site/src/app/replay/[code]/page.tsx` (ladder repo) | Spectating + play rendering (needs extraction to shared lib) |
| JS engine bundle | `PrismataAI/js_engine/build_viewer_bundle.js` → `prismata-engine.js` (0.4MB) | Parallel validation, replay processing |
| AMF3 codec | `<ladder>/prismata_sniffer.py` (ladder repo) | All server communication. **Encoder needs dict support for Phase 2.** |
| Headless client | `<ladder>/headless_client.py` (ladder repo) | Auth + connection management |
| Headless multi | `<ladder>/headless_multi.py` (ladder repo) | Multi-account spectating coordinator |
| Message dispatcher | `<ladder>/prismata_sniffer.py` MessageDispatcher | Event handling for all message types |
| `_inject_msg()` | `<ladder>/prismata_sniffer.py` Session | Click submission for play mode |
| `replay_validator.js` | `PrismataAI/js_engine/replay_validator.js` | Post-game verification |
| `batch_validate.py` | `PrismataAI/js_engine/batch_validate.py` | Bulk engine validation |
| Card art + metadata | `<ladder>-site/public/images/units/` (ladder repo) | Unit rendering |

**Cross-repo dependency**: The headless client imports `decode_amf3`, `encode_amf3_value` from `prismata_sniffer.py`. Both live in the ladder repo. The PrismataAI repo contains the JS engine, build tooling, and AI infrastructure.
