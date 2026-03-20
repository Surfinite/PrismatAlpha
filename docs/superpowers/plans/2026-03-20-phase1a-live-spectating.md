# Phase 1a: Live Spectating MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let anyone visit the ladder site's `/live` page, see a list of active top games, click one, and watch it in real-time using the React game board.

**Architecture:** Wonderboat's headless spectator receives game clicks from Lunarch via TCP/AMF3. A new WebSocket broadcast module runs alongside it, pushing game events as JSON to all connected browsers. The browser runs the JS engine locally to reconstruct game state from clicks, then renders with the existing React components.

**Tech Stack:** Python 3.10+ (asyncio, `websockets` library), Next.js 16 / React 19 / Tailwind CSS 4, prismata-engine.js bundle (0.4MB)

**Spec:** `docs/superpowers/specs/2026-03-20-browser-client-design.md`

---

## File Structure

### Python (<ladder> repo: `<LADDER_REPO_PATH>\`)

| File | Action | Responsibility |
|------|--------|---------------|
| `ws_broadcast.py` | **Create** | Asyncio WebSocket server. Accepts browser connections, broadcasts game events per-game, handles subscribe/unsubscribe. |
| `spectator_bridge.py` | **Create** | Glue between headless spectator and WebSocket broadcast. Translates AMF3 game events → JSON, pushes to broadcast queue. Thread-safe queue bridges sync (spectator thread) → async (WebSocket event loop). |
| `headless_multi.py` | **Modify** | Add callback hooks for `spectator_bridge` to receive game events. |
| `requirements.txt` | **Create** | Pin `websockets>=12.0` |

### React (<ladder>-site: `<LADDER_REPO_PATH>\<ladder>-site\`)

| File | Action | Responsibility |
|------|--------|---------------|
| `src/app/live/page.tsx` | **Create** | `/live` route. WebSocket connection, game list, game viewer. |
| `src/lib/useWebSocket.ts` | **Create** | React hook for WebSocket connection with auto-reconnect. |
| `src/lib/gameTypes.ts` | **Create** | Shared TypeScript interfaces (GameState, CardInstance, CardMeta, ViewerInfo, etc.) extracted from replay viewer. |

### Shared (already exists, referenced)

| File | Repo | Used For |
|------|------|----------|
| `public/js/prismata-engine.js` | ladder-site | JS engine for click processing in browser |
| `prismata_sniffer.py` | <ladder> | AMF3 codec, MessageDispatcher, Session |
| `headless_client.py` | <ladder> | Auth, connection management |

---

## Task 1: WebSocket Broadcast Server

**Files:**
- Create: `<LADDER_REPO_PATH>\ws_broadcast.py`
- Create: `<LADDER_REPO_PATH>\tests\test_ws_broadcast.py`

This is a standalone asyncio WebSocket server that browsers connect to. It knows nothing about AMF3 or Prismata — it just broadcasts JSON messages to subscribers grouped by game ID.

- [ ] **Step 1: Create `requirements.txt`**

```
websockets>=12.0
```

Run: `cd <LADDER_REPO_PATH> && pip install -r requirements.txt`

- [ ] **Step 2: Write test for broadcast server**

```python
# tests/test_ws_broadcast.py
import asyncio
import json
import pytest
import websockets
from ws_broadcast import BroadcastServer

@pytest.fixture
async def server():
    srv = BroadcastServer(host="127.0.0.1", port=0)  # port=0 = random
    task = asyncio.create_task(srv.start())
    await asyncio.sleep(0.1)  # let server bind
    yield srv
    srv.stop()
    await task

@pytest.mark.asyncio
async def test_subscribe_and_receive(server):
    url = f"ws://127.0.0.1:{server.port}"
    async with websockets.connect(url) as ws:
        # Subscribe to a game
        await ws.send(json.dumps({"type": "subscribe", "gameId": "test_game"}))

        # Server broadcasts an event for that game
        server.broadcast("test_game", {"type": "click", "payload": {"_type": "card clicked", "_id": 1}})

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "click"
        assert msg["payload"]["_id"] == 1

@pytest.mark.asyncio
async def test_no_crosstalk(server):
    url = f"ws://127.0.0.1:{server.port}"
    async with websockets.connect(url) as ws1, websockets.connect(url) as ws2:
        await ws1.send(json.dumps({"type": "subscribe", "gameId": "game_A"}))
        await ws2.send(json.dumps({"type": "subscribe", "gameId": "game_B"}))

        server.broadcast("game_A", {"type": "click", "payload": {}})

        msg = json.loads(await asyncio.wait_for(ws1.recv(), timeout=2.0))
        assert msg["type"] == "click"

        # ws2 should NOT receive anything
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws2.recv(), timeout=0.5)
```

Run: `cd <LADDER_REPO_PATH> && python -m pytest tests/test_ws_broadcast.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement BroadcastServer**

```python
# ws_broadcast.py
"""
WebSocket broadcast server for Prismata live spectating.

Browsers connect, subscribe to game IDs, and receive JSON events.
Thread-safe: broadcast() can be called from any thread.
"""
import asyncio
import json
import logging
import threading
from collections import defaultdict
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

log = logging.getLogger(__name__)


class BroadcastServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self._host = host
        self._port = port
        self._clients: dict[str, set[WebSocketServerProtocol]] = defaultdict(set)
        self._global_clients: set[WebSocketServerProtocol] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server = None
        self._seq = 0

    @property
    def port(self) -> int:
        return self._port

    async def start(self):
        """Start the WebSocket server (run in asyncio loop)."""
        self._loop = asyncio.get_running_loop()
        self._server = await websockets.serve(
            self._handle_client, self._host, self._port
        )
        # Update port if we used port=0
        for sock in self._server.sockets:
            self._port = sock.getsockname()[1]
            break
        log.info(f"WebSocket server listening on ws://{self._host}:{self._port}")
        await self._server.wait_closed()

    def stop(self):
        if self._server:
            self._server.close()

    async def _handle_client(self, ws: WebSocketServerProtocol):
        """Handle a single browser connection."""
        subscribed_games: set[str] = set()
        try:
            # Send current top games on connect
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")
                if msg_type == "subscribe":
                    game_id = msg.get("gameId")
                    if game_id:
                        with self._lock:
                            self._clients[game_id].add(ws)
                        subscribed_games.add(game_id)
                elif msg_type == "unsubscribe":
                    game_id = msg.get("gameId")
                    if game_id:
                        with self._lock:
                            self._clients[game_id].discard(ws)
                        subscribed_games.discard(game_id)
                elif msg_type == "subscribeGlobal":
                    with self._lock:
                        self._global_clients.add(ws)
        finally:
            # Cleanup on disconnect
            with self._lock:
                for gid in subscribed_games:
                    self._clients[gid].discard(ws)
                self._global_clients.discard(ws)

    def broadcast(self, game_id: str, event: dict[str, Any]):
        """Thread-safe: broadcast a JSON event to all subscribers of a game."""
        with self._lock:
            self._seq += 1
            event["v"] = 1
            event["seq"] = self._seq
            event["gameId"] = game_id
            data = json.dumps(event, default=str)
            targets = set(self._clients.get(game_id, set()))

        if targets and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_to_all(targets, data), self._loop
            )

    def broadcast_global(self, event: dict[str, Any]):
        """Thread-safe: broadcast to all globally-subscribed clients."""
        with self._lock:
            self._seq += 1
            event["v"] = 1
            event["seq"] = self._seq
            data = json.dumps(event, default=str)
            targets = set(self._global_clients)

        if targets and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_to_all(targets, data), self._loop
            )

    @staticmethod
    async def _send_to_all(clients: set[WebSocketServerProtocol], data: str):
        for ws in clients:
            try:
                await ws.send(data)
            except Exception:
                pass  # Client disconnected; cleanup happens in _handle_client
```

- [ ] **Step 4: Run tests**

Run: `cd <LADDER_REPO_PATH> && python -m pytest tests/test_ws_broadcast.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd <LADDER_REPO_PATH>
git add ws_broadcast.py tests/test_ws_broadcast.py requirements.txt
git commit -m "feat: add WebSocket broadcast server for live spectating"
```

---

## Task 2: Spectator Bridge

**Files:**
- Create: `<LADDER_REPO_PATH>\spectator_bridge.py`
- Create: `<LADDER_REPO_PATH>\tests\test_spectator_bridge.py`

Translates headless spectator game events into JSON for the WebSocket broadcast. Understands Prismata message types. Thread-safe queue bridges sync → async.

- [ ] **Step 1: Write test**

```python
# tests/test_spectator_bridge.py
import json
import pytest
from unittest.mock import MagicMock
from spectator_bridge import SpectatorBridge

def test_begin_game_translation():
    broadcaster = MagicMock()
    bridge = SpectatorBridge(broadcaster)

    # Simulate BeginGame params (simplified)
    game_info = {
        "laneInfo": [{"players": [
            {"displayName": "Alice", "name": "alice"},
            {"displayName": "Bob", "name": "bob"}
        ]}],
        "deckInfo": {"mergedDeck": [{"UIName": "Drone"}], "randomizer": [[{"UIName": "Tarsier"}]]}
    }
    bridge.on_message("BeginGame", "S->C", [game_info], None)

    broadcaster.broadcast.assert_called_once()
    call_args = broadcaster.broadcast.call_args
    game_id = call_args[0][0]
    event = call_args[0][1]
    assert event["type"] == "gameInit"
    assert "Alice" in str(event["payload"]["players"])

def test_click_translation():
    broadcaster = MagicMock()
    bridge = SpectatorBridge(broadcaster)
    bridge._current_game_id = "test_game"

    bridge.on_message("Click", "S->C", [{"_type": "card clicked", "_id": 3}], None)

    broadcaster.broadcast.assert_called_once()
    event = broadcaster.broadcast.call_args[0][1]
    assert event["type"] == "click"
    assert event["payload"]["_type"] == "card clicked"

def test_top_games_broadcast():
    broadcaster = MagicMock()
    bridge = SpectatorBridge(broadcaster)

    games = [{"gameid": "g1", "players": ["A", "B"], "ratings": [2000, 2100]}]
    bridge.on_message("TopGamesUpdate", "S->C", [games], None)

    broadcaster.broadcast_global.assert_called_once()
    event = broadcaster.broadcast_global.call_args[0][0]
    assert event["type"] == "topGames"
```

Run: `python -m pytest tests/test_spectator_bridge.py -v`
Expected: FAIL

- [ ] **Step 2: Implement SpectatorBridge**

```python
# spectator_bridge.py
"""
Bridges headless spectator game events to WebSocket broadcast.

Translates AMF3-decoded Prismata messages into JSON events
suitable for browser consumption.
"""
import logging
import time
from typing import Any

log = logging.getLogger(__name__)


class SpectatorBridge:
    """Receives Prismata message events, translates to JSON, broadcasts via WebSocket."""

    def __init__(self, broadcaster):
        self._broadcaster = broadcaster
        self._current_game_id: str | None = None
        self._turn_num = 0

    def on_message(self, msg_type: str, direction: str, params: list, raw_msg: Any):
        """Called by the spectator/proxy message dispatcher."""
        if direction != "S->C":
            return

        handler = getattr(self, f"_handle_{msg_type}", None)
        if handler:
            try:
                handler(params)
            except Exception as e:
                log.error(f"Bridge error handling {msg_type}: {e}")

    def _handle_BeginGame(self, params):
        game_info = params[0] if params else {}

        # Extract player info
        players = []
        ratings = []
        lane_info = game_info.get("laneInfo", [{}])
        if lane_info:
            player_list = lane_info[0].get("players", [])
            for p in player_list:
                players.append(p.get("displayName", p.get("name", "Unknown")))
                ratings.append(p.get("rating", 0))

        # Generate a game ID
        self._current_game_id = f"live_{int(time.time())}_{'-'.join(players)}"
        self._turn_num = 0

        self._broadcaster.broadcast(self._current_game_id, {
            "type": "gameInit",
            "turnNum": 0,
            "payload": {
                "players": players,
                "ratings": ratings,
                "gameInfo": game_info,
            }
        })

    def _handle_Click(self, params):
        if not self._current_game_id:
            return
        click = params[0] if params else {}
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "click",
            "turnNum": self._turn_num,
            "payload": click if isinstance(click, dict) else {"_type": click, "_id": 0}
        })

    def _handle_ManyClicks(self, params):
        if not self._current_game_id:
            return
        clicks = params[0] if params else []
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "manyClicks",
            "turnNum": self._turn_num,
            "payload": {"clicks": clicks}
        })

    def _handle_StartTurn(self, params):
        self._turn_num += 1
        if not self._current_game_id:
            return
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "turnStart",
            "turnNum": self._turn_num,
            "payload": {"serverTime": params[0] if params else 0}
        })

    def _handle_EndTurn(self, params):
        if not self._current_game_id:
            return
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "endTurn",
            "turnNum": self._turn_num,
            "payload": {}
        })

    def _handle_GameOver(self, params):
        if not self._current_game_id:
            return
        replay_code = params[2] if len(params) > 2 else None
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "gameOver",
            "turnNum": self._turn_num,
            "payload": {
                "winner": params[0] if params else None,
                "replayCode": replay_code
            }
        })
        self._current_game_id = None

    def _handle_GameOverDraw(self, params):
        if not self._current_game_id:
            return
        replay_code = params[0] if params else None
        self._broadcaster.broadcast(self._current_game_id, {
            "type": "gameOver",
            "turnNum": self._turn_num,
            "payload": {"winner": None, "replayCode": replay_code}
        })
        self._current_game_id = None

    def _handle_TopGamesUpdate(self, params):
        games = params[0] if params else []
        self._broadcaster.broadcast_global({
            "type": "topGames",
            "payload": {"games": games}
        })
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_spectator_bridge.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add spectator_bridge.py tests/test_spectator_bridge.py
git commit -m "feat: add spectator bridge — translates game events to JSON"
```

---

## Task 3: Hook Bridge into Headless Multi

**Files:**
- Modify: `<LADDER_REPO_PATH>\headless_client.py` (~3 lines)
- Modify: `<LADDER_REPO_PATH>\headless_multi.py` (~15 lines)

Three architectural fixes from review:
1. **Raw message hook** — `HeadlessClient` doesn't expose raw messages. Add a `_raw_message_hook` callback.
2. **One bridge per CoordinatedClient** — each spectator tracks one game, so each gets its own bridge.
3. **TopGamesUpdate routing** — handled in `CoordinatedClient.run()`, not through `HeadlessClient`. Forward explicitly.

- [ ] **Step 1: Add raw message hook to HeadlessClient**

In `headless_client.py`, add to `__init__`:
```python
self._raw_message_hook = None  # Optional: (msg_type, params, raw_msg) -> None
```

In `headless_client.py`, in `_handle_game_message()` (the method that processes incoming server messages), add at the very top, before any other processing:
```python
if self._raw_message_hook:
    try:
        self._raw_message_hook(msg_type, params, raw_msg)
    except Exception:
        pass  # Never let hook errors break the client
```

This gives the bridge access to raw `BeginGame` (with full `deckInfo`, `mergedDeck`, `initInfo`), `Click`, `ManyClicks`, `StartTurn`, `EndTurn`, `GameOver` — everything it needs.

- [ ] **Step 2: Add WebSocket server + per-client bridges to headless_multi**

In `headless_multi.py` main/startup:
```python
import asyncio
import threading
from ws_broadcast import BroadcastServer
from spectator_bridge import SpectatorBridge

# Start WebSocket server in background thread
broadcast_server = BroadcastServer(host="127.0.0.1", port=8765)
ws_thread = threading.Thread(
    target=lambda: asyncio.run(broadcast_server.start()),
    daemon=True, name="ws-broadcast"
)
ws_thread.start()
```

In `CoordinatedClient.__init__`, create a per-client bridge:
```python
self.bridge = SpectatorBridge(broadcast_server)
self.client._raw_message_hook = self.bridge.on_message
```

- [ ] **Step 3: Forward TopGamesUpdate through bridge**

In `CoordinatedClient.run()`, where `TopGamesUpdate` is currently handled (~line 610), add after the existing processing:
```python
# Forward to WebSocket broadcast
if self.bridge:
    self.bridge.on_top_games(games_list)
```

And add `on_top_games` to `SpectatorBridge`:
```python
def on_top_games(self, games: list):
    """Called directly from coordinator (not through raw message hook)."""
    self._broadcaster.broadcast_global({
        "type": "topGames",
        "payload": {"games": games}
    })
```

- [ ] **Step 4: Manual integration test**

Start the headless multi-spectator with WebSocket:
```bash
cd <LADDER_REPO_PATH>
python headless_multi.py
```

In another terminal, connect with a WebSocket test client:
```bash
python -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://127.0.0.1:8765') as ws:
        await ws.send(json.dumps({'type': 'subscribeGlobal'}))
        while True:
            msg = json.loads(await ws.recv())
            print(json.dumps(msg, indent=2))
asyncio.run(test())
"
```

Expected: See `topGames` events when games are live. See `gameInit` / `click` events when a game is being spectated.

- [ ] **Step 5: Commit**

```bash
cd <LADDER_REPO_PATH>
git add headless_client.py headless_multi.py
git commit -m "feat: wire spectator bridge + WebSocket broadcast into headless multi

- Add _raw_message_hook to HeadlessClient for bridge access to raw game messages
- One SpectatorBridge per CoordinatedClient (multi-game support)
- TopGamesUpdate forwarded explicitly from coordinator"
```

---

## Task 4: React `/live` Page — Game List

**Files:**
- Create: `<LADDER_REPO_PATH>\<ladder>-site\src\lib\useWebSocket.ts`
- Create: `<LADDER_REPO_PATH>\<ladder>-site\src\lib\gameTypes.ts`
- Create: `<LADDER_REPO_PATH>\<ladder>-site\src\app\live\page.tsx`

- [ ] **Step 1: Create shared types**

```typescript
// src/lib/gameTypes.ts
export interface LiveGame {
  gameid: string;
  players: string[];
  ratings: number[];
  started?: number;
  timeControl?: string;
  score?: number;
}

export interface WsMessage {
  seq: number;
  gameId?: string;
  turnNum?: number;
  type: string;
  payload: any;
}
```

- [ ] **Step 2: Create WebSocket hook**

```typescript
// src/lib/useWebSocket.ts
'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import type { WsMessage } from './gameTypes';

export function useWebSocket(url: string | null) {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<NodeJS.Timeout>();

  const connect = useCallback(() => {
    if (!url) return;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try { setLastMessage(JSON.parse(e.data)); }
      catch {}
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { connected, lastMessage, send };
}
```

- [ ] **Step 3: Create `/live` page with game list**

```typescript
// src/app/live/page.tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useWebSocket } from '@/lib/useWebSocket';
import type { LiveGame, WsMessage } from '@/lib/gameTypes';

// Configure WebSocket URL — for dev, localhost; for production, Wonderboat's server
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8765';

export default function LivePage() {
  const { connected, lastMessage, send } = useWebSocket(WS_URL);
  const [games, setGames] = useState<LiveGame[]>([]);

  // Subscribe to global events on connect
  useEffect(() => {
    if (connected) send({ type: 'subscribeGlobal' });
  }, [connected, send]);

  // Handle incoming messages
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'topGames') {
      setGames(lastMessage.payload.games || []);
    }
  }, [lastMessage]);

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #050d18 0%, #0a1628 50%, #0d1f35 100%)' }}>
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'rgba(0,212,255,0.1)', background: 'rgba(5,13,24,0.7)' }}>
        <div className="flex items-center gap-3">
          <Link href="/" className="text-[#6b9ac4] hover:text-[#00d4ff] text-sm transition-colors">← Ladder</Link>
          <span className="font-bold text-sm tracking-widest text-[#00d4ff]" style={{ fontFamily: 'var(--font-orbitron)' }}>LIVE GAMES</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-[#00ff88]' : 'bg-[#ff3366]'}`} />
          <span className="text-xs text-[#6b9ac4]">{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </nav>

      {/* Game list */}
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-6">
          <h1 className="text-2xl font-bold text-white tracking-wide" style={{ fontFamily: 'var(--font-orbitron)' }}>
            LIVE <span className="text-[#00d4ff]">GAMES</span>
          </h1>
          <div className="flex-1 h-px ml-4" style={{ background: 'linear-gradient(to right, rgba(0,212,255,0.5), transparent)' }} />
        </div>

        {games.length === 0 ? (
          <div className="text-center py-16 text-[#6b9ac4]">
            {connected ? 'No live games right now. Check back soon!' : 'Connecting to spectator server...'}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {games.map((game) => (
              <Link key={game.gameid} href={`/live/${encodeURIComponent(game.gameid)}`}
                className="glass-card rounded-xl p-4 border border-[#1e3a5f] hover:border-[#00d4ff]/50 hover:shadow-[0_0_20px_rgba(0,212,255,0.15)] transition-all cursor-pointer">
                <div className="flex items-center justify-center gap-3 mb-2">
                  <div className="text-center">
                    <div className="font-bold text-white text-sm">{game.players?.[0] || '?'}</div>
                    <div className="text-[#ffd700] font-semibold text-xs">{Math.round(game.ratings?.[0] || 0)}</div>
                  </div>
                  <div className="text-[#6b9ac4] font-bold text-sm">vs</div>
                  <div className="text-center">
                    <div className="font-bold text-white text-sm">{game.players?.[1] || '?'}</div>
                    <div className="text-[#ffd700] font-semibold text-xs">{Math.round(game.ratings?.[1] || 0)}</div>
                  </div>
                </div>
                <div className="flex items-center justify-center gap-2">
                  <span className="text-[10px] px-2 py-0.5 rounded font-bold tracking-wider"
                    style={{ fontFamily: 'var(--font-orbitron)', background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}>
                    LIVE
                  </span>
                  {game.timeControl && <span className="text-xs text-[#6b9ac4]">{game.timeControl}</span>}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

Run: `cd <LADDER_REPO_PATH>\<ladder>-site && npx next build 2>&1 | tail -20`
Expected: Build succeeds, `/live` route listed

- [ ] **Step 5: Commit**

```bash
cd <LADDER_REPO_PATH>
git add <ladder>-site/src/lib/useWebSocket.ts <ladder>-site/src/lib/gameTypes.ts <ladder>-site/src/app/live/page.tsx
git commit -m "feat: add /live page with live game list"
```

---

## Task 5: Live Game Viewer Page

**Files:**
- Create: `<LADDER_REPO_PATH>\<ladder>-site\src\app\live\[gameId]\page.tsx`

This page subscribes to a specific game's WebSocket events, runs clicks through the JS engine, and renders the game board using the existing React components from the replay viewer.

- [ ] **Step 1: Create the live viewer page**

This reuses the existing replay viewer components (UnitCard, CardLane, BuyPane, etc.) from `src/app/replay/[code]/page.tsx`. For the MVP, we inline the needed components or import the shared types. The key difference from the replay viewer: instead of loading a complete replay from S3, we receive clicks in real-time over WebSocket and process them incrementally.

The page must:
1. Connect to WebSocket and subscribe to the game ID
2. Wait for `gameInit` event (contains deck info, player info)
3. Initialize the JS engine with the game init data
4. Process each incoming `click` / `manyClicks` through the engine
5. Re-render the React game board on each state change
6. Show game result when `gameOver` arrives

```typescript
// src/app/live/[gameId]/page.tsx — skeleton (full implementation based on replay viewer)
'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Script from 'next/script';
import { useWebSocket } from '@/lib/useWebSocket';
import type { WsMessage } from '@/lib/gameTypes';

// Import game board components (same as replay viewer)
// For MVP: duplicate key components inline; extract to shared lib in next iteration

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8765';

export default function LiveGamePage() {
  const params = useParams();
  const gameId = decodeURIComponent(params.gameId as string);
  const { connected, lastMessage, send } = useWebSocket(WS_URL);

  const [status, setStatus] = useState<'connecting' | 'waiting' | 'live' | 'ended'>('connecting');
  const [gameState, setGameState] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);

  // Subscribe to this game on connect
  useEffect(() => {
    if (connected) {
      send({ type: 'subscribe', gameId });
      setStatus('waiting');
    }
  }, [connected, send, gameId]);

  // Process incoming events
  useEffect(() => {
    if (!lastMessage || lastMessage.gameId !== gameId) return;

    switch (lastMessage.type) {
      case 'gameInit':
        // Initialize JS engine with game data
        // window.PrismataViewer would need a new method for live init
        setStatus('live');
        break;
      case 'click':
      case 'manyClicks':
        // Feed click(s) to JS engine
        // Update game state
        break;
      case 'gameOver':
        setStatus('ended');
        break;
    }
  }, [lastMessage, gameId]);

  // ... render game board (same components as replay viewer) ...
  // Full implementation follows same pattern as src/app/replay/[code]/page.tsx
  // but fed from WebSocket instead of S3 replay
}
```

**Implementation note**: This page mirrors `src/app/replay/[code]/page.tsx` but with a WebSocket data source instead of S3 replay loading. The game board components (UnitCard, CardLane, BuyPane, ResourceDisplay, etc.) are reused — for the MVP, copy the needed component code from the replay viewer page. Extraction into a shared library is a follow-up task.

**Click legality validation (spec requirement 5.1)**: When the JS engine rejects a click (`canClick: false`), the viewer must display a visible warning — this indicates proxy relay corruption. Track a `failedClicks` counter and show it in a warning badge when > 0.

- [ ] **Step 2: Add `initLive` and `processClick` to engine bundle**

Modify `js_engine/build_viewer_bundle.js`. In the PrismataViewer IIFE, add `var liveAnalyzer = null;` alongside the existing `var REPLAY = null;` declaration. Then add these functions before the Navigation section:

```javascript
function initLive(gameInitInfo) {
    // gameInitInfo comes from BeginGame — reformat to match Analyzer constructor
    // (same structure as processS3Replay uses)
    var laneInfo = [{
        initResources: gameInitInfo.initInfo ? gameInitInfo.initInfo.initResources : undefined,
        base: gameInitInfo.deckInfo ? gameInitInfo.deckInfo.base : undefined,
        randomizer: gameInitInfo.deckInfo ? gameInitInfo.deckInfo.randomizer : undefined,
        initCards: gameInitInfo.initInfo ? gameInitInfo.initInfo.initCards : undefined
    }];
    var analyzerInit = {
        laneInfo: laneInfo,
        mergedDeck: gameInitInfo.deckInfo ? gameInitInfo.deckInfo.mergedDeck : [],
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null, commandInfo: null
    };

    liveAnalyzer = new Analyzer(analyzerInit, -1, -1, null);
    liveAnalyzer.loaderInit();

    var p0 = 'Player 0', p1 = 'Player 1';
    if (gameInitInfo.players) { p0 = gameInitInfo.players[0] || p0; p1 = gameInitInfo.players[1] || p1; }

    REPLAY = {
        p0: p0, p1: p1, winner: -1, winnerName: '',
        turns: 0, cardSet: [],
        states: [stateToCppJSON(liveAnalyzer.gameState)],
        actions: ['Start'], turnBoundaries: [0]
    };
    stateIndex = 0; totalStates = 1;
    notify();
    return getInfo();
}

function processClick(clickType, clickId, clickParams) {
    if (!liveAnalyzer) return { accepted: false, info: getInfo() };
    var prePhase = liveAnalyzer.gameState.phase;
    try {
        var result = liveAnalyzer.recordClick(false, false, clickType, clickId, clickParams);
        if (result.canClick) {
            var newState = stateToCppJSON(liveAnalyzer.gameState);
            REPLAY.states.push(newState);
            REPLAY.actions.push(describeClick({_type: clickType, _id: clickId}, liveAnalyzer.gameState, prePhase));
            if (liveAnalyzer.gameState.numTurns !== REPLAY.turns) {
                REPLAY.turnBoundaries.push(REPLAY.states.length - 1);
                REPLAY.turns = liveAnalyzer.gameState.numTurns;
            }
            totalStates = REPLAY.states.length;
            stateIndex = totalStates - 1;
            notify();
            return { accepted: true, info: getInfo() };
        }
        return { accepted: false, info: getInfo() };
    } catch (e) {
        return { accepted: false, error: e.message, info: getInfo() };
    }
}
```

Add to the return object:
```javascript
return {
    init: init, loadFromCode: loadFromCode,
    initLive: initLive, processClick: processClick,  // ← NEW
    nextAction: nextAction, prevAction: prevAction,
    // ... rest unchanged
};
```

Rebuild:
```bash
cd C:\libraries\PrismataAI && node js_engine/build_viewer_bundle.js
```

- [ ] **Step 3: Verify build**

Run: `cd <LADDER_REPO_PATH>\<ladder>-site && npx next build 2>&1 | tail -20`
Expected: Build succeeds, `/live/[gameId]` route listed

- [ ] **Step 4: Commit**

```bash
cd <LADDER_REPO_PATH>
git add <ladder>-site/src/app/live/[gameId]/page.tsx
git commit -m "feat: add live game viewer page with WebSocket + JS engine"

cd C:\libraries\PrismataAI
git add js_engine/build_viewer_bundle.js
git commit -m "feat: add initLive + processClick to engine bundle for live spectating"
```

---

## Task 6: End-to-End Integration Test

**Files:**
- Create: `<LADDER_REPO_PATH>\tests\test_e2e_spectating.py`

Test the full pipeline: mock spectator feeds events → bridge translates → WebSocket broadcasts → client receives.

- [ ] **Step 1: Write E2E test**

```python
# tests/test_e2e_spectating.py
import asyncio
import json
import pytest
import websockets
from ws_broadcast import BroadcastServer
from spectator_bridge import SpectatorBridge

@pytest.mark.asyncio
async def test_full_spectating_pipeline():
    """Simulate: spectator receives game → bridge translates → WS broadcasts → client receives."""
    server = BroadcastServer(host="127.0.0.1", port=0)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.2)

    bridge = SpectatorBridge(server)

    async with websockets.connect(f"ws://127.0.0.1:{server.port}") as ws:
        # Subscribe globally first to get game IDs
        await ws.send(json.dumps({"type": "subscribeGlobal"}))

        # Simulate BeginGame
        game_info = {
            "laneInfo": [{"players": [
                {"displayName": "Alice", "name": "alice", "rating": 2100},
                {"displayName": "Bob", "name": "bob", "rating": 2200}
            ]}],
            "deckInfo": {"mergedDeck": [], "randomizer": []}
        }
        bridge.on_message("BeginGame", "S->C", [game_info], None)

        # Should NOT receive gameInit (we're global, not subscribed to this game)
        # But we should be able to subscribe to the game now

        # Get the game ID from the bridge
        game_id = bridge._current_game_id
        await ws.send(json.dumps({"type": "subscribe", "gameId": game_id}))
        await asyncio.sleep(0.1)

        # Simulate clicks
        bridge.on_message("Click", "S->C", [{"_type": "card clicked", "_id": 2}], None)

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "click"
        assert msg["payload"]["_type"] == "card clicked"

        # Simulate game over
        bridge.on_message("GameOver", "S->C", [0, 1, "ABC12-DEF34"], None)

        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert msg["type"] == "gameOver"
        assert msg["payload"]["replayCode"] == "ABC12-DEF34"

    server.stop()
    await task
```

- [ ] **Step 2: Run E2E test**

Run: `python -m pytest tests/test_e2e_spectating.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_spectating.py
git commit -m "test: add end-to-end spectating pipeline test"
```

---

## Task 7: Manual Live Test

No files to create — this is a manual verification with the real Lunarch server.

- [ ] **Step 1: Start the headless multi-spectator with WebSocket**

```bash
cd <LADDER_REPO_PATH>
python headless_multi.py
```

Verify in terminal: "WebSocket server listening on ws://127.0.0.1:8765"

- [ ] **Step 2: Start the ladder site dev server**

```bash
cd <LADDER_REPO_PATH>\<ladder>-site
npx next dev --webpack -p 3000
```

- [ ] **Step 3: Open `/live` in browser**

Navigate to `http://localhost:3000/live`

Expected:
- Green "Connected" indicator
- List of live games (if any are being played right now)
- If no games: "No live games right now" message

- [ ] **Step 4: Click a live game**

If a game is available, click it.

Expected:
- Game board renders with player names
- Clicks appear in real-time as they happen
- Turn number updates
- Game ends with replay code shown

- [ ] **Step 5: Verify post-game replay comparison (spec requirement 5.2)**

After the game ends:
1. Copy the replay code shown in the game over message
2. Load it in the replay viewer at `/replay/{code}` — verify it plays correctly
3. Compare: does the replay viewer's final state match what the live viewer showed?
4. Check the click count: number of clicks in S3 replay should match clicks received over WebSocket

- [ ] **Step 6: Verify `Moved` redirect survival (spec exit criteria)**

During long spectating sessions, the server may send `Moved` messages (load balancing). The headless client already handles reconnection. Verify:
1. WebSocket connection to the browser stays up during a server redirect
2. Game state is not lost
3. If the headless client reconnects to a new server node, the bridge continues broadcasting

(This may require waiting for a natural `Moved` event, or testing with a mock.)

---

## Summary

| Task | Description | Output |
|------|-------------|--------|
| 1 | WebSocket broadcast server | `ws_broadcast.py` — standalone, tested |
| 2 | Spectator bridge | `spectator_bridge.py` — translates AMF3 → JSON, tested |
| 3 | Hook into headless multi | Modified `headless_multi.py` |
| 4 | React `/live` page + game list | `/live` route with WebSocket connection |
| 5 | Live game viewer | `/live/[gameId]` + engine `processClick` |
| 6 | E2E integration test | Pipeline test: mock spectator → WS → client |
| 7 | Manual live test | Real server verification |
