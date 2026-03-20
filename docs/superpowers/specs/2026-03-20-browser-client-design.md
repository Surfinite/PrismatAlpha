# Prismata Browser Client — Design Specification

> **Date**: 2026-03-20
> **Status**: Draft (post-review v2)
> **Author**: Surfinite + Claude

## 1. Vision

A browser-based Prismata client that lets the community watch live games and eventually play — replacing the dead Flash client with a modern React interface that lives on the ladder site.

Think CaptureAge for Prismata: starts as a spectating tool, becomes the primary way to experience the game.

## 2. Design Principles

### 2.1 Community First
The primary goal is giving the community a way to watch and play Prismata in a browser. Every architectural decision serves this.

### 2.2 Minimal Lunarch Server Impact
Playing adds exactly one normal client connection per player. Spectating uses Wonderboat's existing headless accounts (already connecting). The ladder site has its own operational overhead (WebSocket fanout, session management, spectator pool) but this is on Wonderboat's infrastructure, not Lunarch's.

### 2.3 AI Overlay — Deferred (Anti-Cheat Unresolved)
AI evaluation overlays (eval bars, suggested moves) are **deferred to a future phase** pending resolution of the anti-cheat problem.

**The core problem**: Even if the play client contains no analysis, a player in a live game can open the spectator page for that same game in another tab/device. If the spectator shows live eval, it becomes a live assistance channel.

**Prerequisite policies before AI overlays ship** (one must be chosen):
- **Safest**: AI overlays only on completed replays, never live games
- **Acceptable**: AI overlays on live games with a fixed delay (e.g. 2 minutes behind)
- **Niche**: AI overlays only for organizer-approved observer/cast sessions
- **Insufficient**: Disabling overlays when the authenticated user is a participant (does not stop second-device abuse)

**Architectural enforcement** (ready for when the policy is decided):
- `GameContext` carries a `mode` field (`"spectating"` or `"playing"`)
- `sendClick()` is null in spectating mode; AI endpoints are null in playing mode
- The play client does not import the suggest/eval codepath in production builds
- The `--suggest` endpoint is only exposed by the hosted spectating server, never the local proxy

This is a design constraint, not a guideline. Community trust is existential — any perception of cheating enablement would be fatal to adoption.

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
    Play UI served FROM the local proxy (same-origin)
```

**Play mode same-origin**: The local proxy serves the play UI itself (static files on the same port as the WebSocket). This avoids cross-origin issues between HTTPS pages and `ws://localhost`, and simplifies the security model.

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
| `FriendList` | New (Phase 1c) | Online friends, status indicators |

All components communicate through a `GameContext` provider holding: game state, chat messages, connection status, mode (`spectating`/`playing`), and (in play mode) a `sendClick()` function.

**Note**: The "Built" components exist in `<ladder>-site/src/app/replay/[code]/page.tsx` as part of the replay viewer (inline in the page file). They will need to be extracted into a shared component library for reuse across spectating and play contexts.

### 3.3 WebSocket Protocol

JSON translation layer between proxy (AMF3) and browser, with envelope for reliability.

#### Message Envelope

All messages use a standard envelope:
```json
{
  "v": 1,
  "seq": 1842,
  "sessionId": "spectator_7",
  "gameId": "game_abc123",
  "turnNum": 14,
  "type": "click",
  "payload": { "_type": "inst clicked", "_id": 42 }
}
```

| Field | Purpose |
|-------|---------|
| `v` | Protocol version (allows future evolution) |
| `seq` | Monotonic sequence number (detect dropped/duplicated messages) |
| `sessionId` | Identifies the viewer session (for reconnect) |
| `gameId` | Which game this message belongs to |
| `turnNum` | Game turn number (for ordering and resync) |
| `type` | Message type (see below) |
| `payload` | Type-specific data |

#### Browser → Proxy (local play only)
```
type: "auth"       → payload: { method, username?, password?, token? }
type: "click"      → payload: { _type, _id }
type: "endTurn"    → payload: {}
type: "chat"       → payload: { channel, text }
type: "pm"         → payload: { target, text }
type: "spectate"   → payload: { gameId }
type: "resync"     → payload: { lastSeq } (request resync from this point)
```

#### Proxy → Browser (both modes)
```
type: "gameInit"   → payload: { deckInfo, players, initInfo, ratings, randomizer }
type: "click"      → payload: { player, _type, _id }
type: "manyClicks" → payload: { player, clicks: [{_type, _id}, ...] }
type: "gameOver"   → payload: { winner, replayCode }
type: "chat"       → payload: { channel, from, text }
type: "pm"         → payload: { from, text }
type: "topGames"   → payload: { games: [...] }
type: "turnStart"  → payload: { player, timeRemaining, bankRemaining }
type: "connected"  → payload: { username }
type: "error"      → payload: { code: number, message: string }
type: "checkpoint" → payload: { state: {...fullGameState...}, clicksSinceInit: number }
type: "resync"     → payload: { gameInit, clicks: [...allClicksSinceInit...] }
```

#### Reconnect/Resync Behavior

| Scenario | Behavior |
|----------|----------|
| Browser refresh | Browser sends `resync` with `lastSeq: -1`. Proxy sends full `resync` (gameInit + all clicks). |
| WebSocket drop | Browser auto-reconnects, sends `resync` with last received `seq`. Proxy replays missed messages. |
| AMF3 `Moved` redirect | Proxy handles transparently — reconnects to new server, WebSocket stays up. |
| `FixLateClicks` from server | Proxy sends corrected clicks with appropriate `seq`/`turnNum`. Browser replays from affected turn. |
| Headless spectator replaced | New spectator picks up game from server; proxy sends fresh `resync` to viewers. |

#### Checkpoints
For DVR-like playback (pause, rewind, catch-up):
- Proxy caches a full state checkpoint at every turn boundary
- `checkpoint` messages sent at turn boundaries allow browsers to jump to any point
- Catch-up: browser receives checkpoint + clicks since checkpoint, not full history
- This is Phase 1a.5 work (after basic spectating works)

### 3.4 Local Proxy Security

The local proxy is a powerful endpoint (receives credentials, sends game actions, can inject chat). It must be defended against "malicious website talks to localhost" attacks.

**Required security measures:**
- **Bind only to 127.0.0.1** — never `0.0.0.0`
- **Random high port per launch** — not a fixed predictable port
- **Per-launch session nonce** — generated at startup, displayed in terminal, required on every browser→proxy request (WebSocket URL includes nonce: `ws://127.0.0.1:{port}/?nonce={secret}`)
- **Strict Origin checks** — reject WebSocket connections from origins other than the local proxy's own served pages
- **Command whitelist** — only the defined JSON message types are accepted; never arbitrary AMF3 injection from the browser
- **Same-origin serving** — the play UI is served by the local proxy itself, so browser and WebSocket share the same origin

**What the proxy NEVER exposes to the browser:**
- Raw AMF3 message injection
- Direct socket access to the Lunarch server
- Credential storage read access
- Message ID manipulation

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
| `EndSwoosh` | C→S | `["EndSwoosh", serverId, turnNum]` | Defense phase complete |
| `Click` | S→C | `["Click", {_type, _id}]` | Opponent's action |
| `ManyClicks` | S→C | `["ManyClicks", [{_type, _id}, ...]]` | Opponent's batch actions |
| `BeginGame` | S→C | `["BeginGame", gameInfo]` | Game init (players, deck, randomizer) |
| `GameOver` | S→C | `["GameOver", winner, loser, replayCode, ...]` | Game result |
| `TopGamesUpdate` | S→C | `["TopGamesUpdate", gamesList]` | Live game list |
| `ObserveTopGame` | C→S | `["ObserveTopGame", gameId]` | Start spectating |
| `Chat` | Both | `["Chat", channel, text]` | Global chat |
| `PrivateChat` | Both | `["PrivateChat", targetId, text]` | Private message |
| `StartTurn` | S→C | `["StartTurn", serverTime]` | Turn begins |
| `Moved` | S→C | `["Moved", newIp, mainPort, tlsPort]` | Server redirect (load balancing) |
| `FixLateClicks` | S→C | `["FixLateClicks", turnNum, [clicks]]` | Server corrections |

### 4.3 Authentication
Two supported paths:
1. **Username/password**: PBKDF2 hash (HMAC-SHA256, 1000 iterations) sent via secure courier on TLS port. Browser sends password over `ws://127.0.0.1` (local only, never leaves machine). Proxy performs PBKDF2 and forwards hash to Lunarch.
2. **Captured Steam token** (experimental): Session token from existing client connection, replayed on new connection. Token lifetime, IP-binding, and invalidation behavior are undocumented — needs empirical testing before relying on this path. Label as experimental in UI.

**Credential storage**: The headless client uses base64 "obfuscation" (not encryption). Adequate for local single-user use; not suitable for shared/hosted systems.

### 4.4 Message Injection
The proxy uses `_inject_msg()` for sending game actions to the server. The browser never accesses this directly — it sends typed JSON commands, and the proxy translates to AMF3. Message ID tracking with offset patching ensures injected messages don't break the client↔server sequence.

### 4.5 State Reconstruction Architecture
The Lunarch server does NOT push full game state — it sends `BeginGame` (initial deck/players) then individual clicks. Game state must be reconstructed by replaying clicks from the initial state.

**Architecture**: The browser runs the JS engine locally. The proxy sends raw clicks over WebSocket. The browser applies each click to its local JS engine state and re-renders. This matches the existing replay viewer pattern and avoids the proxy needing to run Node.js server-side.

- `gameInit` WebSocket message carries the full `BeginGame` data
- Subsequent `click` / `manyClicks` messages carry player actions
- Browser's JS engine processes each click and updates React state
- Same pipeline as the replay viewer, fed from live WebSocket instead of S3

### 4.6 AMF3 Encoder Gaps
The existing AMF3 encoder handles `str`, `int`, `float`, `list`, `None`, `bool` — but NOT `dict`. Click messages to the server contain dict objects (`{_type, _id}`). The encoder must be extended with AMF3 dynamic object support before Phase 2 (live play). The decoder already handles this (sniffer lines 177-230), so the format is understood. This is non-trivial — AMF3 object encoding requires trait management.

### 4.7 Scaling Constraints
One headless spectator account can spectate one game at a time. To show N concurrent live games, N headless accounts are needed. `headless_multi.py` already coordinates multiple accounts.

### 4.8 Observer Pool Policy

| Scenario | Behavior |
|----------|----------|
| More live games than accounts | Show available games only; indicate others are in progress but not viewable |
| Viewer clicks a game with no free account | Queue the request; switch when an account frees up, or show "spectator slots full" |
| Multiple viewers want the same game | One account spectates, WebSocket broadcasts to all viewers (fan-out) |
| Game stops being "top" but has viewers | Keep spectating until game ends or all viewers leave |
| Headless account disconnects mid-game | Auto-reconnect (existing Fibonacci backoff); viewers see "reconnecting" status |

### 4.9 Server-Side Credential Management
Headless spectator account credentials live on Wonderboat's server. These are real Prismata accounts. Credential rotation, access control, and protection should be agreed with Wonderboat before deployment.

## 5. Verification Strategy

### 5.1 Click Legality Validation
During spectating, the browser's JS engine processes each relayed click. If a click is rejected (illegal action), this indicates proxy relay corruption — a click garbled, lost, or out of order. This catches transport errors in real-time.

**Important**: This validates click legality, not full state equivalence. The server doesn't send state snapshots to compare against. True state comparison happens post-game via S3 (Section 5.2).

### 5.2 Post-Game Replay Comparison
After any live game completes, the replay becomes available on S3:
1. Proxy logs all AMF3 messages during the game
2. After `GameOver`, fetch the S3 replay
3. Replay the logged messages through `replay_validator.js`
4. Compare final state and winner against S3 replay
5. Report any discrepancies

### 5.3 Batch Validation
`batch_validate.py` validates engine correctness across large replay corpora. Current: 99.5% pass rate on 1000 random replays (5 failures are known JS↔C++ edge cases in targeting abilities).

### 5.4 AMF3 Round-Trip Testing
Unit tests for the AMF3 codec: encode a message, decode it, verify it matches the original. Critical because a single byte error would corrupt game actions.

### 5.5 Phase 2 Exit Criteria (Live Play Correctness Bar)
For replay tooling, 99.5% is acceptable. For a live play client, a higher bar is required:
- **0 known unresolved desync categories** in current protocol coverage
- **99.99%+ parity** on a recent replay corpus (post-patch replays only)
- **Golden tests** for all action-bearing message types (Click, EndTurn, EndSwoosh, auth, Moved)
- **Byte-level or semantic parity tests** against captured real-client traffic for the above message types
- **No regressions** from the existing 102K replay validation baseline

## 6. Phases

### Phase 1a — Live Spectating (MVP)
- WebSocket broadcast layer added to proxy
- `/live` page on ladder site: `LiveGameList` → click → React board with real-time clicks
- JS engine click legality validation running in browser
- `ConnectionStatus` component
- **No rewind/DVR yet** — live-only to minimize scope

**Exit criteria**: Can watch a live top game in the browser. Clicks render correctly. Connection survives server `Moved` redirects. Post-game replay matches.

### Phase 1a.5 — Reconnect, Resync, DVR
- Message sequencing (envelope `seq` / `turnNum`)
- Reconnect/resync on browser refresh or WebSocket drop
- Turn-boundary checkpoints for pause/rewind/catch-up
- Playback controls: pause live feed, rewind to any turn, catch up to live

**Exit criteria**: Viewer survives network interruptions. Can pause, rewind 5 turns, and catch up to live without desyncing.

### Phase 1b — Chat
- `ChatPanel` component: tabbed global channels + PM conversations
- Proxy relays `Chat` and `PrivateChat` messages bidirectionally
- Same component used in both spectating and play contexts
- All global channels supported, English as default tab

**Exit criteria**: Can send and receive global chat and PMs. Messages appear in correct channels.

### Phase 1c — Social Features (can be parallel with Phase 2)
- `FriendList` (server message research from AS3 source needed)
- Chat commands: `/whisper`, `/block`, `/friend`, `/unfriend`
- Online status indicators
- Requires additional server message types to be reverse-engineered
- **Non-blocking**: Phase 2 does not depend on 1c.

**Exit criteria**: Friend list displays. Chat commands work. Online status updates.

### Phase 2 — Live Play
- Local proxy launcher: starts proxy + serves play UI + opens browser
- Auth flow: password entry or captured Steam token (labeled experimental)
- `ClickHandler`: translates React UI interactions → protocol messages
- AMF3 encoder extended with dict/object support
- Game queue / accept challenge flow
- Turn timer display with bank time
- Per-launch session nonce, origin checks, command whitelist (see Section 3.4)
- Verification: record all games, validate against S3 replay after completion

**Exit criteria**: Can play a full rated game. Post-game S3 replay comparison shows 0 discrepancies. Correctness bar from Section 5.5 met. Security review of local proxy completed.

### Phase 3 — AI Overlays (DEFERRED)
**Deferred** pending resolution of the anti-cheat problem (Section 2.3). Will not be implemented until:
1. A specific anti-cheat policy is chosen (replay-only, delayed, or cast-only)
2. Community consensus that the chosen policy is acceptable
3. Phases 1-2 have shipped and established trust

When eventually implemented:
- AI on completed replays first (safest path)
- `--suggest` calls for eval + best move display
- Hard-gated by `GameContext.mode`
- Play client production builds do not import suggest/eval codepath

### Phase 4 — AI Play
- AI player mode: proxy auto-submits AI-computed clicks each turn
- Uses `--suggest` CLI mode: spawns fresh `Prismata_Testing.exe` per turn (NeuralNet singleton — cannot reuse process)
- Configurable AI backend (SteamAI, DSNN, LiveHardestAI, UCT)
- Think time controls and rate limiting
- Uses same local proxy infrastructure as Phase 2
- Only after community fully trusts Phases 1-2

**Exit criteria**: AI can play a full rated game. Post-game validation passes. Think time is configurable and respected.

## 7. User Experience

### 7.1 Spectating (hosted — zero install)
1. Visit ladder site → `/live` page
2. See list of live games (auto-updating)
3. Click a game → watch in real-time with React board
4. Chat visible alongside the game

### 7.2 Playing (local — launcher script)
1. Run `python prismata_launcher.py` (or double-click a script)
2. Terminal shows: proxy started, nonce displayed, browser opens
3. Browser loads play UI from `http://127.0.0.1:{port}`
4. Enter username/password OR load captured Steam token (labeled experimental)
5. See lobby: live games, chat, game queue
6. Queue for a game or accept a challenge
7. Play using the React board — clicks sent through local proxy to Lunarch server
8. After game: replay code shown, game validated against S3 replay

### 7.3 Future: Desktop App
Wrap the local proxy + browser in an Electron shell or PyInstaller + WebView. Same code, packaged as a one-click install. No architectural changes needed — purely a distribution/packaging concern.

## 8. Dependencies & Risks

### 8.1 Lunarch Server Availability
The live features depend on Lunarch's servers. If they shut down, live play and spectating stop. However, the community has a viable fallback: the JS engine contains the complete game rules (validated against 102K replays), the React board handles rendering, and the AMF3 protocol is fully understood. A community-hosted game server using the JS engine for click validation and a WebSocket relay for player matching is **tractable** — authoritative multiplayer, timing, reconnection, ratings, matchmaking, persistence, and moderation are real work, but the hardest part (game rules) is done. This is a contingency, not a current goal.

### 8.2 Protocol Changes
If Lunarch updates the server protocol, the AMF3 codec and message handling may need updates. Mitigated by round-trip tests and post-game validation catching issues quickly.

### 8.3 Server-Side Validation
Lunarch's server validates all clicks. Malformed or illegal clicks will be rejected. The verification layer catches these during testing.

### 8.4 Community Trust
The most important risk. AI overlay restrictions (Section 2.3) and the deferred status of Phase 3 reflect this. Any perception of cheating enablement would be fatal to adoption.

### 8.5 Steam Token Stability
Steam token capture is labeled experimental. Token lifetime, invalidation behavior, IP/device binding, and reusability across sessions are undocumented. These are product-shaping unknowns, not just implementation details. Password auth is the reliable path.

## 9. Existing Infrastructure Leveraged

| Component | Location | Reused For |
|-----------|----------|------------|
| React game board | `<ladder>-site/src/app/replay/[code]/page.tsx` (ladder repo) | Spectating + play rendering (needs extraction to shared lib) |
| JS engine bundle | `PrismataAI/js_engine/build_viewer_bundle.js` → `prismata-engine.js` (0.4MB) | Click validation, state reconstruction |
| AMF3 codec | `<ladder>/prismata_sniffer.py` (ladder repo) | All server communication. **Encoder needs dict support for Phase 2.** |
| Headless client | `<ladder>/headless_client.py` (ladder repo) | Auth + connection management |
| Headless multi | `<ladder>/headless_multi.py` (ladder repo) | Multi-account spectating coordinator |
| Message dispatcher | `<ladder>/prismata_sniffer.py` MessageDispatcher | Event handling for all message types |
| `_inject_msg()` | `<ladder>/prismata_sniffer.py` Session | Click submission for play mode |
| `replay_validator.js` | `PrismataAI/js_engine/replay_validator.js` | Post-game verification |
| `batch_validate.py` | `PrismataAI/js_engine/batch_validate.py` | Bulk engine validation |
| Card art + metadata | `<ladder>-site/public/images/units/` (ladder repo) | Unit rendering |

**Cross-repo dependency**: The headless client imports `decode_amf3`, `encode_amf3_value` from `prismata_sniffer.py`. Both live in the ladder repo. The PrismataAI repo contains the JS engine, build tooling, and AI infrastructure.
