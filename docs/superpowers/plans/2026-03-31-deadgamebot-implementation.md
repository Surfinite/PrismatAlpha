# DeadGameBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an on-demand ranked bot that queues when a player presses a button on deadgame.prismata.live

**Architecture:** Python bot on Windows PC connects to Prismata server, plays games using Steam's PrismataAI.exe. Express trigger site on site box handles queue requests with login gating, activity detection, and audit logging. Bot polls site for triggers.

**Tech Stack:** Python 3 (bot), Node.js/Express (trigger site), SQLite (audit log), PrismataAI.exe (game AI), AMF3 protocol (Prismata server comms)

**Spec:** `docs/superpowers/specs/2026-03-30-ranked-bot-deadgamebot-design.md`

---

## File Map

### Bot (Windows PC) — `bot/`

| File | Responsibility |
|---|---|
| `bot/amf3.py` | AMF3 binary codec (encode/decode), adapted from <ladder> |
| `bot/client.py` | Prismata server connection, auth, message send/receive |
| `bot/steam_ai_bridge.py` | Spawn PrismataAI.exe, send state via stdin, read clicks from stdout |
| `bot/game_player.py` | Game lifecycle: BeginGame → turns → GameOver, state conversion |
| `bot/trigger_poller.py` | Poll deadgame.prismata.live for queue requests, send heartbeats |
| `bot/ranked_bot.py` | Main entry point, state machine (IDLE→QUEUING→PLAYING), orchestrates everything |
| `bot/config.py` | Paths, credentials, constants |
| `bot/protocol_messages.md` | Documented protocol messages (filled during Phase 1 capture) |
| `bot/tests/test_steam_ai_bridge.py` | Tests for PrismataAI.exe bridge |
| `bot/tests/test_game_player.py` | Tests for state conversion and click translation |

### Trigger Site (site box) — `deadgame/`

| File | Responsibility |
|---|---|
| `deadgame/server.js` | Express server, route mounting, health endpoint |
| `deadgame/lib/db.js` | SQLite schema, query helpers (requests table, bot_state table) |
| `deadgame/lib/activity.js` | Activity detection — query ladder DB for recent sub-1600 games |
| `deadgame/lib/auth.js` | JWT verification (shared secret with prismata.live), bot API key check |
| `deadgame/routes/bot.js` | Bot API: status, queue, heartbeat, update-status, kill |
| `deadgame/public/index.html` | Frontend SPA |
| `deadgame/deadgame.service` | systemd unit file |
| `deadgame/deadgame.nginx.conf` | nginx vhost config |
| `deadgame/deploy.sh` | Deployment script |
| `deadgame/package.json` | Dependencies |

---

## Phase 1: Protocol Capture & SteamAI Bridge

### Task 1: Protocol Capture — Play vs Bot

This is a **manual step** requiring the user to run the Prismata client through the sniffer.

**Files:**
- Read: `<LADDER_REPO_PATH>\prismata_amf3.py` (the sniffer/proxy)
- Create: `bot/protocol_messages.md`

- [ ] **Step 1: Set up the sniffer**

Add to `C:\Windows\System32\drivers\etc\hosts`:
```
127.0.0.1 ec2-3-229-49-48.compute-1.amazonaws.com
```

Run the sniffer:
```bash
cd <LADDER_REPO_PATH>
python prismata_amf3.py 2>&1 | tee bot_game_capture.log
```

- [ ] **Step 2: Play a game vs Master Bot**

Launch Prismata via Steam. Start a game vs Master Bot (any difficulty). Play a few turns, then let the game finish (win or lose). The sniffer will log all messages.

- [ ] **Step 3: Capture ranked queue messages**

After the bot game, go to Play → Ranked. Queue for ranked, wait a few seconds, then cancel. The sniffer will capture the queue/cancel messages.

If you have two accounts available (e.g., DeadGameBot + WonderYacht), try to actually match them together to capture the full ranked game flow.

- [ ] **Step 4: Document the protocol**

From the sniffer log, identify and document in `bot/protocol_messages.md`:

```markdown
# Prismata Protocol Messages — DeadGameBot

## Discovered from sniffer capture on [DATE]

### Play vs Bot
- Start bot game: `["???", ...]` — exact message name and params
- BeginGame payload: document the full structure
- Client→Server Click format: `["Click", ...]` — exact structure
- Client→Server EndTurn: `["EndTurn"]` or `["EndTurn", ...]`
- Client→Server EndSwoosh: when sent, format
- Turn signal: how client knows it's their turn
- GameOver: format and fields
- QuitGame: `["QuitGame", gameId]`

### Ranked Queue
- Queue for ranked: `["???", ...]` — message name and params
- Cancel queue: `["???", ...]`
- Match found: what message arrives
- Any differences from bot game flow

### Key Observations
- Does Click use `{_type, _id}` or a different format?
- Does the server send a StartTurn message?
- When is EndSwoosh needed?
- What data is in BeginGame that we need for PrismataAI.exe input?
```

- [ ] **Step 5: Remove hosts entry**

Remove the `127.0.0.1 ec2-3-229-49-48.compute-1.amazonaws.com` line from hosts file so normal Prismata works again.

- [ ] **Step 6: Commit**

```bash
git add bot/protocol_messages.md
git commit -m "docs: protocol capture for DeadGameBot game-playing messages"
```

---

### Task 2: SteamAI Bridge — Python Implementation

**Files:**
- Create: `bot/steam_ai_bridge.py`
- Create: `bot/config.py`
- Create: `bot/tests/test_steam_ai_bridge.py`

- [ ] **Step 1: Create config module**

```python
# bot/config.py
"""DeadGameBot configuration."""

import os

# PrismataAI.exe — Steam's Master Bot binary
PRISMATA_AI_EXE = os.environ.get(
    "PRISMATA_AI_EXE",
    r"C:\libraries\Prismata\AI\PrismataAI.exe"
)

# Think time in milliseconds
THINK_TIME_MS = 7000

# SteamAI subprocess timeout (think time + overhead)
STEAM_AI_TIMEOUT_S = 15

# Trigger site
TRIGGER_SITE_URL = os.environ.get(
    "TRIGGER_SITE_URL",
    "https://deadgame.prismata.live"
)
TRIGGER_POLL_INTERVAL_S = 5
HEARTBEAT_INTERVAL_S = 10

# Bot API key for authenticated endpoints
BOT_API_KEY = os.environ.get("BOT_API_KEY", "")

# Prismata server
PRISMATA_SERVER_HOST = "3.229.49.48"
PRISMATA_MAIN_PORT = 11600
PRISMATA_TLS_PORT = 11601
PRISMATA_CLIENT_VERSION = "3433"

# Bot account credentials (set via environment)
BOT_USERNAME = os.environ.get("BOT_USERNAME", "DeadGameBot")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "")

# Ranked queue timeout
QUEUE_TIMEOUT_S = 60

# Resignation threshold
RESIGN_EVAL_PCT_THRESHOLD = 5.0  # resign if eval_pct < 5% for N consecutive turns
RESIGN_CONSECUTIVE_TURNS = 3
```

- [ ] **Step 2: Write the failing test**

```python
# bot/tests/test_steam_ai_bridge.py
"""Tests for SteamAI bridge — PrismataAI.exe subprocess wrapper."""

import json
import os
import pytest
from bot.steam_ai_bridge import SteamAIBridge

# Skip if PrismataAI.exe not available
PRISMATA_AI_EXE = os.environ.get(
    "PRISMATA_AI_EXE",
    r"C:\libraries\Prismata\AI\PrismataAI.exe"
)
HAS_EXE = os.path.exists(PRISMATA_AI_EXE)


@pytest.mark.skipif(not HAS_EXE, reason="PrismataAI.exe not found")
class TestSteamAIBridge:
    def test_get_move_returns_clicks(self):
        """Send a known game state and verify we get clicks back."""
        bridge = SteamAIBridge(exe_path=PRISMATA_AI_EXE, timeout_s=15)

        # Minimal turn-1 state: just base set, player 0's action phase
        request = {
            "mergedDeck": [
                {"name": "Drone", "UIName": "Drone", "buyCost": "3H", "rarity": "trinket"},
                {"name": "Engineer", "UIName": "Engineer", "buyCost": "1G", "rarity": "trinket"},
                {"name": "Conduit", "UIName": "Conduit", "buyCost": "4", "rarity": "trinket"},
                {"name": "Blastforge", "UIName": "Blastforge", "buyCost": "5", "rarity": "trinket"},
                {"name": "Animus", "UIName": "Animus", "buyCost": "6", "rarity": "trinket"},
                {"name": "Wall", "UIName": "Wall", "buyCost": "5B", "rarity": "trinket"},
                {"name": "Steelsplitter", "UIName": "Steelsplitter", "buyCost": "6B", "rarity": "trinket"},
                {"name": "Rhino", "UIName": "Rhino", "buyCost": "5GG", "rarity": "trinket"},
                {"name": "Tarsier", "UIName": "Tarsier", "buyCost": "4R", "rarity": "trinket"},
                {"name": "Forcefield", "UIName": "Forcefield", "buyCost": "1G", "rarity": "trinket"},
                {"name": "Gauss Cannon", "UIName": "Gauss Cannon", "buyCost": "6BG", "rarity": "trinket"}
            ],
            "gameState": "THIS_NEEDS_REAL_STATE",
            "aiParameters": {},
            "aiPlayerName": "HardestAI"
        }

        # NOTE: This test will only work with a real game state.
        # For now, we test that the bridge correctly spawns the process
        # and handles the response format. A real game state fixture
        # should be captured during Phase 1 protocol capture and saved
        # to bot/tests/fixtures/turn1_state.json.
        # TODO: Replace with real fixture after protocol capture.

    def test_strips_control_characters(self):
        """Verify control character stripping from stdout."""
        bridge = SteamAIBridge(exe_path=PRISMATA_AI_EXE, timeout_s=15)
        # Test the internal clean method
        raw = '\x00\x1f{"aiclicks": [], "aithinktime": 100}\n'
        clean = bridge._clean_response(raw)
        parsed = json.loads(clean)
        assert "aiclicks" in parsed
        assert parsed["aithinktime"] == 100

    def test_timeout_raises(self):
        """Verify timeout is enforced."""
        bridge = SteamAIBridge(exe_path=PRISMATA_AI_EXE, timeout_s=0.001)
        with pytest.raises(TimeoutError):
            bridge.get_move('{"invalid": true}')
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_steam_ai_bridge.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'bot.steam_ai_bridge'`

- [ ] **Step 4: Implement the bridge**

```python
# bot/steam_ai_bridge.py
"""SteamAI Bridge — spawn PrismataAI.exe and get AI moves.

PrismataAI.exe is Steam's Master Bot binary. It's a one-shot process:
- Receives game state JSON via stdin (newline-terminated)
- Returns click response JSON via stdout (newline-terminated)
- Process exits after each response

Input format:
  {"mergedDeck": [...], "gameState": {...}, "aiParameters": {...}, "aiPlayerName": "HardestAI"}

Output format:
  {"aiclicks": [{_type, _id}, ...], "aithinktime": N, "eval": 0.5, "eval_pct": "50%"}
"""

import json
import re
import subprocess
from bot.config import PRISMATA_AI_EXE, STEAM_AI_TIMEOUT_S


class SteamAIBridge:
    def __init__(self, exe_path=None, timeout_s=None):
        self.exe_path = exe_path or PRISMATA_AI_EXE
        self.timeout_s = timeout_s or STEAM_AI_TIMEOUT_S

    def get_move(self, request_json):
        """Send game state to PrismataAI.exe and return parsed response.

        Args:
            request_json: JSON string or dict with mergedDeck, gameState,
                          aiParameters, aiPlayerName

        Returns:
            dict with keys: aiclicks, aithinktime, eval, eval_pct

        Raises:
            TimeoutError: if process doesn't respond within timeout
            RuntimeError: if process exits with error or returns invalid JSON
        """
        if isinstance(request_json, dict):
            request_json = json.dumps(request_json)

        payload = request_json if request_json.endswith('\n') else request_json + '\n'

        try:
            result = subprocess.run(
                [self.exe_path],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"PrismataAI.exe did not respond within {self.timeout_s}s"
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"PrismataAI.exe exited with code {result.returncode}: "
                f"{result.stderr[:200] if result.stderr else 'no stderr'}"
            )

        stdout = result.stdout
        if not stdout.strip():
            raise RuntimeError("PrismataAI.exe returned empty output")

        clean = self._clean_response(stdout)

        try:
            response = json.loads(clean)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid JSON from PrismataAI.exe: {e}\nRaw: {stdout[:200]}"
            )

        return response

    def _clean_response(self, raw):
        """Strip control characters from stdout before JSON parsing.

        PrismataAI.exe may emit control characters or debug output before
        the JSON response. Find the first '{' and strip control chars.
        """
        # Find first JSON object
        idx = raw.find('{')
        if idx == -1:
            return raw
        raw = raw[idx:]
        # Strip control characters (same pattern as matchup_clean.js)
        return re.sub(r'[\x00-\x1f]', ' ', raw).strip()

    def parse_eval_pct(self, response):
        """Extract numeric eval percentage from response.

        PrismataAI.exe returns eval_pct as a string like "70%".
        Returns float (e.g., 70.0) or None if not present.
        """
        eval_pct = response.get('eval_pct', '')
        if isinstance(eval_pct, str) and eval_pct.endswith('%'):
            try:
                return float(eval_pct[:-1])
            except ValueError:
                return None
        return None
```

- [ ] **Step 5: Create `__init__.py` files**

```python
# bot/__init__.py
# (empty)
```

```python
# bot/tests/__init__.py
# (empty)
```

- [ ] **Step 6: Run tests**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_steam_ai_bridge.py -v
```

Expected: `test_strips_control_characters` PASSES, `test_get_move_returns_clicks` SKIPPED (needs real fixture), `test_timeout_raises` PASSES or SKIPPED depending on exe availability.

- [ ] **Step 7: Commit**

```bash
git add bot/
git commit -m "feat(bot): SteamAI bridge and config module

Spawns PrismataAI.exe as subprocess, sends game state via stdin,
reads click response from stdout. One-shot per turn."
```

---

## Phase 2: Bot Plays vs Master Bot

### Task 3: AMF3 Protocol Layer

**Files:**
- Create: `bot/amf3.py`
- Source: `<LADDER_REPO_PATH>\prismata_amf3.py`

- [ ] **Step 1: Extract AMF3 codec from <ladder>**

Copy the AMF3 encoder/decoder from `prismata_amf3.py`. We need only the codec — not the sniffer/proxy functionality. Extract these classes/functions:
- `AMF3Decoder` class (binary → Python objects)
- `encode_amf3_value()` function (Python objects → binary)
- Supporting helpers: `encode_u29`, `encode_amf3_string`, etc.

```bash
# Copy the file and strip everything except the codec
cd c:/libraries/PrismataAI
```

Create `bot/amf3.py` by extracting just the AMF3Decoder class and encode_amf3_value function from `<LADDER_REPO_PATH>\prismata_amf3.py`. The file is ~1500 lines — you want approximately lines 50-350 (the decoder) and lines 350-550 (the encoder). Remove all sniffer/proxy/session code.

The resulting file should export:
- `decode_amf3(data: bytes) -> object` — decode a single AMF3 value from bytes
- `encode_amf3_value(value) -> bytes` — encode a Python object to AMF3 bytes

- [ ] **Step 2: Write a quick validation test**

```python
# bot/tests/test_amf3.py
"""Smoke test for AMF3 codec — roundtrip encode/decode."""

from bot.amf3 import encode_amf3_value, decode_amf3

def test_roundtrip_string():
    data = encode_amf3_value("hello")
    result = decode_amf3(data)
    assert result == "hello"

def test_roundtrip_list():
    msg = ["Msg", 42, ["Click", {"_type": "card clicked", "_id": 0}]]
    data = encode_amf3_value(msg)
    result = decode_amf3(data)
    assert result[0] == "Msg"
    assert result[1] == 42
    assert result[2][0] == "Click"

def test_roundtrip_nested_dict():
    obj = {"name": "Drone", "buyCost": "3H", "supply": 20}
    data = encode_amf3_value(obj)
    result = decode_amf3(data)
    assert result["name"] == "Drone"
    assert result["supply"] == 20
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest bot/tests/test_amf3.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bot/amf3.py bot/tests/test_amf3.py
git commit -m "feat(bot): AMF3 binary codec extracted from <ladder>"
```

---

### Task 4: Headless Game Client

**Files:**
- Create: `bot/client.py`
- Reference: `<LADDER_REPO_PATH>\headless_client.py`

- [ ] **Step 1: Implement the client**

Adapt `headless_client.py` into a focused game-playing client. Strip all spectating, TopGamesUpdate, and ladder tracker code. Keep:
- Dual TCP connection (main 11600, TLS 11601)
- PBKDF2 password hashing + HMAC courier claiming
- `Moved` handling during login
- Ping/Pong keepalive
- `_send_main()` / `_send_secure()` for outbound messages
- `_recv()` with timeout

Add new game-playing methods:
- `queue_ranked(time_controls)` — sends queue message (message name from protocol capture)
- `cancel_queue()` — cancels queue
- `send_click(click_data)` — sends `["Click", click_data]`
- `send_end_turn()` — sends `["EndTurn"]`
- `send_end_swoosh()` — sends `["EndSwoosh"]`
- `send_quit_game(game_id)` — sends `["QuitGame", game_id]`
- `start_bot_game()` — initiates a Play vs Bot game (message name from protocol capture)

```python
# bot/client.py
"""Headless Prismata client for game-playing.

Connects to the Prismata server, authenticates, and provides methods
for queuing ranked games and sending game actions (clicks, end turn).

Adapted from <ladder>/headless_client.py — stripped to only
game-playing functionality.
"""

import socket
import ssl
import struct
import hmac
import hashlib
import time
import threading
from bot.amf3 import encode_amf3_value, decode_amf3
from bot.config import (
    PRISMATA_SERVER_HOST, PRISMATA_MAIN_PORT, PRISMATA_TLS_PORT,
    PRISMATA_CLIENT_VERSION,
)


def prismata_pbkdf2(password, salt):
    """Hash password using Prismata's PBKDF2 scheme."""
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        1000,
    )
    import base64
    return base64.b64encode(key).decode('ascii')


class HeadlessGameClient:
    """Prismata game client — connects, authenticates, plays games."""

    def __init__(self):
        self.main_sock = None
        self.secure_sock = None
        self.main_msg_id = 0
        self.sec_msg_id = 0
        self.main_last_msg = -1
        self.secure_last_msg = -1
        self.username = None
        self.authenticated = False
        self.lobby_ready = False

        # Game state
        self.in_game = False
        self.game_id = None

        # Message callback — set by game_player to handle game messages
        self.on_message = None

    def connect(self):
        """Establish dual TCP connections to Prismata server."""
        # Main courier (plaintext)
        self.main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.main_sock.connect((PRISMATA_SERVER_HOST, PRISMATA_MAIN_PORT))

        # Wait for Connected
        msg = self._recv(self.main_sock, timeout=10)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Expected Connected, got: {msg}")
        connection_id = msg[1]

        # Secure courier (TLS)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.secure_sock = ctx.wrap_socket(raw_sock)
        self.secure_sock.connect((PRISMATA_SERVER_HOST, PRISMATA_TLS_PORT))

        # Wait for Connected on secure
        msg = self._recv(self.secure_sock, timeout=10)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Secure: expected Connected, got: {msg}")

        # Request courier credentials
        self._send(self.main_sock, ["NewCouriers"])

        # Wait for CouriersCreated
        end_time = time.time() + 10
        while time.time() < end_time:
            msg = self._recv(self.main_sock, timeout=1)
            if msg and msg[0] == "CouriersCreated":
                main_id, main_key = msg[1], msg[2]
                sec_id, sec_key = msg[3], msg[4]
                break
            if msg and msg[0] == "Ping":
                self._handle_ping(self.main_sock, msg, self.main_last_msg)
        else:
            raise ConnectionError("Timed out waiting for CouriersCreated")

        # Claim couriers
        self._claim_courier(self.main_sock, main_id, main_key)
        self._claim_courier(self.secure_sock, sec_id, sec_key)

        print(f"[client] Connected to {PRISMATA_SERVER_HOST}")

    def _claim_courier(self, sock, courier_id, courier_key):
        """Claim a courier with HMAC signature."""
        last_msg = 0
        sig_data = f"{last_msg},{courier_id}".encode('utf-8')
        sig = hmac.new(courier_key.encode('utf-8'), sig_data, hashlib.sha256).hexdigest()
        self._send(sock, ["ClaimCourier", last_msg, courier_id, sig])

        # Wait for CourierClaimed
        end_time = time.time() + 10
        while time.time() < end_time:
            msg = self._recv(sock, timeout=1)
            if msg and msg[0] == "CourierClaimed":
                return
            if msg and msg[0] == "Ping":
                self._handle_ping(sock, msg, 0)

    def login(self, username, password):
        """Authenticate with username and password.

        Handles the full login flow including Salt lookup, PBKDF2 hashing,
        and Moved (server node switch) during authentication.
        """
        # Request salt
        self._send_secure(["LookupSalt", username])

        # Wait for Salt response
        salt = self._wait_for_login_message("Salt", timeout=15)
        if not salt:
            raise ConnectionError("Failed to get salt from server")

        # Hash and send login
        password_hash = prismata_pbkdf2(password, salt)
        self._send_secure(["LoginPassword", username, password_hash, False, PRISMATA_CLIENT_VERSION])

        # Wait for LoggedIn — may come on main or secure socket
        end_time = time.time() + 15
        while time.time() < end_time:
            for sock, label in [(self.secure_sock, "sec"), (self.main_sock, "main")]:
                try:
                    msg = self._recv(sock, timeout=0.5)
                    if not msg:
                        continue
                    if msg[0] == "Ping":
                        last = self.secure_last_msg if label == "sec" else self.main_last_msg
                        self._handle_ping(sock, msg, last)
                    elif msg[0] == "Moved":
                        self._handle_moved(msg)
                        self._send_secure(["LookupSalt", username])
                    elif msg[0] == "Msg":
                        if label == "sec":
                            self.secure_last_msg = msg[1]
                        else:
                            self.main_last_msg = msg[1]
                        inner = msg[2]
                        if inner[0] == "LoggedIn":
                            self.username = inner[1]
                            self.authenticated = True
                            print(f"[client] Logged in as {self.username}")
                            return True
                        elif inner[0] == "SplashToLobby":
                            self.lobby_ready = True
                        elif inner[0] in ("LoginFailed", "NoAccount"):
                            raise ConnectionError(f"Login failed: {inner}")
                except socket.timeout:
                    pass

        raise ConnectionError("Login timed out")

    def _wait_for_login_message(self, msg_type, timeout=15):
        """Wait for a specific inner message during login, handling Ping/Moved."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            for sock, label in [(self.secure_sock, "sec"), (self.main_sock, "main")]:
                try:
                    msg = self._recv(sock, timeout=0.5)
                    if not msg:
                        continue
                    if msg[0] == "Ping":
                        last = self.secure_last_msg if label == "sec" else self.main_last_msg
                        self._handle_ping(sock, msg, last)
                    elif msg[0] == "Moved":
                        self._handle_moved(msg)
                    elif msg[0] == "Msg":
                        if label == "sec":
                            self.secure_last_msg = msg[1]
                        else:
                            self.main_last_msg = msg[1]
                        inner = msg[2]
                        if inner[0] == msg_type or inner[0] == "PasswordSalt":
                            return inner[1]
                        elif inner[0] == "SplashToLobby":
                            self.lobby_ready = True
                except socket.timeout:
                    pass
        return None

    def wait_for_lobby(self, timeout=15):
        """Wait for SplashToLobby, processing messages along the way."""
        if self.lobby_ready:
            return True
        end_time = time.time() + timeout
        while time.time() < end_time:
            self._pump_messages(timeout=1)
            if self.lobby_ready:
                return True
        return False

    def _pump_messages(self, timeout=1):
        """Read and dispatch messages from both sockets."""
        for sock, label in [(self.main_sock, "main"), (self.secure_sock, "sec")]:
            try:
                msg = self._recv(sock, timeout=min(timeout, 0.5))
                if not msg:
                    continue
                if msg[0] == "Ping":
                    last = self.main_last_msg if label == "main" else self.secure_last_msg
                    self._handle_ping(sock, msg, last)
                elif msg[0] == "Msg":
                    if label == "main":
                        self.main_last_msg = msg[1]
                    else:
                        self.secure_last_msg = msg[1]
                    inner = msg[2]
                    self._dispatch_message(inner)
            except socket.timeout:
                pass

    def _dispatch_message(self, inner):
        """Route an inner message to the appropriate handler."""
        msg_type = inner[0] if inner else None
        if msg_type == "SplashToLobby":
            self.lobby_ready = True
            self.in_game = False
        if self.on_message:
            self.on_message(inner)

    # --- Send helpers ---

    def _send(self, sock, msg):
        payload = encode_amf3_value(msg)
        frame = struct.pack(">I", len(payload)) + payload
        sock.sendall(frame)

    def _send_main(self, inner_msg):
        msg = ["Msg", self.main_msg_id, inner_msg]
        self.main_msg_id += 1
        self._send(self.main_sock, msg)

    def _send_secure(self, inner_msg):
        msg = ["Msg", self.sec_msg_id, inner_msg]
        self.sec_msg_id += 1
        self._send(self.secure_sock, msg)

    def _handle_ping(self, sock, msg, last_msg):
        self._send(sock, ["Pong", msg[1], last_msg])

    def _handle_moved(self, msg):
        """Handle server node switch during login."""
        new_host = msg[1] if len(msg) > 1 else None
        new_port = int(msg[2]) if len(msg) > 2 else PRISMATA_MAIN_PORT
        new_sec_port = int(msg[3]) if len(msg) > 3 else PRISMATA_TLS_PORT
        if new_host:
            print(f"[client] Node switch to {new_host}:{new_port}/{new_sec_port}")
            # Reconnect to new node
            self.main_sock.close()
            self.secure_sock.close()
            self.main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.main_sock.connect((new_host, new_port))
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.secure_sock = ctx.wrap_socket(raw)
            self.secure_sock.connect((new_host, new_sec_port))

    def _recv(self, sock, timeout=10):
        sock.settimeout(timeout)
        try:
            header = b''
            while len(header) < 4:
                chunk = sock.recv(4 - len(header))
                if not chunk:
                    return None
                header += chunk
            length = struct.unpack(">I", header)[0]
            data = b''
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk
            return decode_amf3(data)
        except socket.timeout:
            return None

    # --- Game actions ---
    # Message names are placeholders — replace with actual names from protocol capture

    def send_click(self, click_data):
        """Send a click action to the server."""
        self._send_main(["Click", click_data])

    def send_end_turn(self):
        """Send EndTurn to the server."""
        self._send_main(["EndTurn"])

    def send_end_swoosh(self):
        """Send EndSwoosh to the server."""
        self._send_main(["EndSwoosh"])

    def send_quit_game(self, game_id):
        """Send QuitGame to leave a finished game."""
        self._send_main(["QuitGame", str(game_id)])

    def start_bot_game(self):
        """Start a game vs the in-game Master Bot.
        Message name TBD from protocol capture — update after Task 1.
        """
        # TODO: Replace with actual message from protocol capture
        # self._send_main(["StartBotGame", ...])
        raise NotImplementedError("Update after protocol capture — see bot/protocol_messages.md")

    def queue_ranked(self, time_controls=None):
        """Queue for ranked play.
        Message name TBD from protocol capture — update after Task 1.

        Args:
            time_controls: list of time control values to queue for
                           (e.g., [45, 60]). Excludes bullet.
        """
        # TODO: Replace with actual message from protocol capture
        # self._send_main(["QueueRanked", ...])
        raise NotImplementedError("Update after protocol capture — see bot/protocol_messages.md")

    def cancel_queue(self):
        """Cancel ranked queue.
        Message name TBD from protocol capture — update after Task 1.
        """
        # TODO: Replace with actual message from protocol capture
        raise NotImplementedError("Update after protocol capture — see bot/protocol_messages.md")

    def disconnect(self):
        """Close connections."""
        for sock in [self.main_sock, self.secure_sock]:
            if sock:
                try:
                    sock.close()
                except:
                    pass
        self.main_sock = None
        self.secure_sock = None
        self.authenticated = False
```

**Note:** The `start_bot_game()`, `queue_ranked()`, and `cancel_queue()` methods are stubs. After the protocol capture in Task 1, replace the `raise NotImplementedError` with the actual message sends. The protocol capture document (`bot/protocol_messages.md`) will have the exact message names and parameters.

- [ ] **Step 2: Commit**

```bash
git add bot/client.py
git commit -m "feat(bot): headless game client with auth and message handling

Dual TCP connection to Prismata server, PBKDF2 auth, message dispatch.
Game action stubs to be filled after protocol capture."
```

---

### Task 5: Game Player — Turn Loop and State Conversion

**Files:**
- Create: `bot/game_player.py`
- Create: `bot/tests/test_game_player.py`

- [ ] **Step 1: Write test for eval_pct resignation tracking**

```python
# bot/tests/test_game_player.py
"""Tests for GamePlayer — resignation logic and state tracking."""

from bot.game_player import GamePlayer


class TestResignation:
    def test_no_resign_above_threshold(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(50.0)
        gp.record_eval(45.0)
        gp.record_eval(30.0)
        assert not gp.should_resign()

    def test_resign_after_three_low_evals(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.0)
        assert not gp.should_resign()
        gp.record_eval(3.0)
        assert not gp.should_resign()
        gp.record_eval(2.0)
        assert gp.should_resign()

    def test_resign_resets_on_high_eval(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(4.0)
        gp.record_eval(3.0)
        gp.record_eval(50.0)  # recovered
        gp.record_eval(4.0)
        gp.record_eval(3.0)
        assert not gp.should_resign()  # only 2 consecutive low evals

    def test_reset_clears_evals(self):
        gp = GamePlayer(bridge=None, client=None)
        gp.record_eval(2.0)
        gp.record_eval(1.0)
        gp.reset()
        gp.record_eval(3.0)
        gp.record_eval(2.0)
        assert not gp.should_resign()  # only 2, not 3
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest bot/tests/test_game_player.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GamePlayer**

```python
# bot/game_player.py
"""Game player — manages a single game from BeginGame to GameOver.

Receives server messages, tracks game state, calls SteamAI bridge
for moves, sends clicks back to server.

State conversion (server → PrismataAI.exe input) will be implemented
after protocol capture reveals the exact BeginGame payload format.
"""

import json
from bot.config import RESIGN_EVAL_PCT_THRESHOLD, RESIGN_CONSECUTIVE_TURNS


class GamePlayer:
    """Manages one game session."""

    def __init__(self, bridge, client):
        """
        Args:
            bridge: SteamAIBridge instance (or None for testing)
            client: HeadlessGameClient instance (or None for testing)
        """
        self.bridge = bridge
        self.client = client
        self.reset()

    def reset(self):
        """Reset state for a new game."""
        self.game_id = None
        self.our_player_index = None  # 0 or 1
        self.merged_deck = None
        self.init_info = None
        self.turn_number = 0
        self.game_over = False
        self.replay_code = None
        self.result = None  # 'win', 'loss', 'draw', 'resign'
        self.opponent_name = None

        # Resignation tracking
        self._low_eval_streak = 0

    # --- Resignation logic ---

    def record_eval(self, eval_pct):
        """Track eval percentage for resignation decisions.

        Args:
            eval_pct: float, the AI's evaluation as a percentage (0-100)
        """
        if eval_pct < RESIGN_EVAL_PCT_THRESHOLD:
            self._low_eval_streak += 1
        else:
            self._low_eval_streak = 0

    def should_resign(self):
        """Returns True if we should resign (eval too low for too long)."""
        return self._low_eval_streak >= RESIGN_CONSECUTIVE_TURNS

    # --- Message handling ---

    def handle_message(self, inner):
        """Process an incoming server message.

        Called by the client's message dispatch. Routes to specific handlers
        based on message type.

        Args:
            inner: list — the inner message (unwrapped from Msg envelope)
        """
        if not inner:
            return

        msg_type = inner[0]
        params = inner[1:] if len(inner) > 1 else []

        if msg_type == "BeginGame":
            self._on_begin_game(params)
        elif msg_type == "Click":
            self._on_click(params)
        elif msg_type == "ManyClicks":
            self._on_many_clicks(params)
        elif msg_type == "EndTurn":
            self._on_end_turn(params)
        elif msg_type == "GameOver":
            self._on_game_over(params)
        elif msg_type == "GameOverDraw":
            self._on_game_over_draw(params)
        # Add more handlers as discovered during protocol capture

    def _on_begin_game(self, params):
        """Handle BeginGame — store game init data.

        The exact payload structure will be determined during protocol capture.
        This stub extracts what we expect based on the spectator client.
        """
        init_info = params[0] if params else {}
        self.init_info = init_info
        self.game_over = False
        self.turn_number = 0
        self._low_eval_streak = 0

        # Extract game ID
        if 'laneInfo' in init_info:
            lane = init_info['laneInfo'][0] if init_info['laneInfo'] else {}
            self.game_id = lane.get('gameId')

            # Extract player info to determine which side we are
            players_info = lane.get('playersInfo', [])
            if len(players_info) >= 2:
                for i, pi in enumerate(players_info):
                    name = pi.get('displayName', pi.get('name', ''))
                    if name == self.client.username:
                        self.our_player_index = i
                    else:
                        self.opponent_name = name

        print(f"[game] BeginGame: we are player {self.our_player_index}, "
              f"opponent: {self.opponent_name}, game_id: {self.game_id}")

    def _on_click(self, params):
        """Handle incoming Click from opponent. Track state."""
        # During protocol capture, determine if we need to do anything here
        pass

    def _on_many_clicks(self, params):
        """Handle ManyClicks from opponent."""
        pass

    def _on_end_turn(self, params):
        """Handle EndTurn — if opponent's turn ended, it's now our turn."""
        self.turn_number += 1
        # TODO: Determine from protocol capture how to know it's our turn
        # For now, assume EndTurn means it's our turn to play
        if not self.game_over:
            self._play_turn()

    def _on_game_over(self, params):
        """Handle GameOver."""
        self.game_over = True
        winner_idx = params[0] if len(params) > 0 else None
        self.replay_code = params[2] if len(params) > 2 else None

        if winner_idx == self.our_player_index:
            self.result = 'win'
        else:
            self.result = 'loss'

        print(f"[game] GameOver: {self.result}, replay: {self.replay_code}")
        self._leave_game()

    def _on_game_over_draw(self, params):
        """Handle GameOverDraw."""
        self.game_over = True
        self.replay_code = params[0] if params else None
        self.result = 'draw'
        print(f"[game] Draw, replay: {self.replay_code}")
        self._leave_game()

    def _leave_game(self):
        """Quit the game and return to lobby."""
        if self.game_id and self.client:
            self.client.send_quit_game(self.game_id)

    # --- Turn execution ---

    def _play_turn(self):
        """Execute one turn: build AI request, get clicks, send them.

        This is the core loop. State conversion happens here.
        """
        if not self.bridge or not self.client:
            return

        # Check resignation
        if self.should_resign():
            print(f"[game] Resigning (eval too low for {RESIGN_CONSECUTIVE_TURNS} turns)")
            self.result = 'resign'
            self.game_over = True
            self._leave_game()
            return

        # Build the PrismataAI.exe request
        request = self._build_ai_request()
        if not request:
            print("[game] ERROR: Could not build AI request")
            return

        # Get AI move
        try:
            response = self.bridge.get_move(request)
        except Exception as e:
            print(f"[game] ERROR: AI bridge failed: {e}")
            return

        # Track eval for resignation
        eval_pct = self.bridge.parse_eval_pct(response)
        if eval_pct is not None:
            self.record_eval(eval_pct)

        # Send clicks
        clicks = response.get('aiclicks', [])
        print(f"[game] Turn {self.turn_number}: {len(clicks)} clicks, "
              f"eval={response.get('eval_pct', '?')}, "
              f"think={response.get('aithinktime', '?')}ms")

        for click in clicks:
            self.client.send_click(click)

        # End our turn
        self.client.send_end_turn()

    def _build_ai_request(self):
        """Convert current game state to PrismataAI.exe input format.

        This is the critical state conversion function. The exact mapping
        depends on the BeginGame payload structure, which will be determined
        during protocol capture.

        Returns:
            dict suitable for json.dumps and sending to PrismataAI.exe stdin,
            or None if state is not ready.
        """
        # TODO: Implement after protocol capture reveals BeginGame format.
        # The server's game state needs to be converted to the F6 clipboard
        # export format that PrismataAI.exe expects:
        # {
        #   "mergedDeck": [...],
        #   "gameState": {...},
        #   "aiParameters": {},
        #   "aiPlayerName": "HardestAI"
        # }
        #
        # Key questions to answer from protocol capture:
        # 1. Does BeginGame contain the full game state, or just initial setup?
        # 2. Do we need to track state incrementally from Click/EndTurn messages?
        # 3. Does the server send us the full state each turn (like F6 export)?
        #
        # For now, return None — this will be filled in during Phase 2 testing.
        print("[game] WARNING: _build_ai_request() not yet implemented")
        return None
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest bot/tests/test_game_player.py -v
```

Expected: All 4 resignation tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/game_player.py bot/tests/test_game_player.py
git commit -m "feat(bot): game player with turn loop and resignation logic

Handles BeginGame/Click/EndTurn/GameOver message routing.
State conversion stub to be implemented after protocol capture."
```

---

### Task 6: Main Bot Process — State Machine

**Files:**
- Create: `bot/ranked_bot.py`

- [ ] **Step 1: Implement the main bot**

```python
# bot/ranked_bot.py
"""DeadGameBot — on-demand ranked bot for Prismata.

Main entry point. Connects to Prismata server, authenticates, and waits
for queue triggers from deadgame.prismata.live.

State machine:
  IDLE → QUEUING → PLAYING → IDLE

Usage:
  python -m bot.ranked_bot

Environment variables:
  BOT_USERNAME — Prismata account username (default: DeadGameBot)
  BOT_PASSWORD — Prismata account password (required)
  BOT_API_KEY — API key for deadgame.prismata.live (optional until Phase 4)
  PRISMATA_AI_EXE — Path to PrismataAI.exe
"""

import sys
import time
import signal
from bot.config import (
    BOT_USERNAME, BOT_PASSWORD, QUEUE_TIMEOUT_S,
)
from bot.client import HeadlessGameClient
from bot.steam_ai_bridge import SteamAIBridge
from bot.game_player import GamePlayer


class DeadGameBot:
    """Main bot orchestrator."""

    # States
    IDLE = "idle"
    QUEUING = "queuing"
    PLAYING = "playing"

    def __init__(self):
        self.state = self.IDLE
        self.running = True
        self.client = HeadlessGameClient()
        self.bridge = SteamAIBridge()
        self.player = GamePlayer(self.bridge, self.client)

        # Wire up message handling
        self.client.on_message = self._on_message

    def start(self):
        """Connect, authenticate, and enter main loop."""
        if not BOT_PASSWORD:
            print("ERROR: BOT_PASSWORD environment variable not set")
            sys.exit(1)

        print(f"[bot] Starting DeadGameBot as {BOT_USERNAME}")

        # Connect and authenticate
        self.client.connect()
        self.client.login(BOT_USERNAME, BOT_PASSWORD)

        # Wait for lobby
        if not self.client.wait_for_lobby(timeout=30):
            print("[bot] WARNING: Did not receive SplashToLobby within 30s")

        print(f"[bot] Ready. State: {self.state}")

        # Main loop
        self._main_loop()

    def _main_loop(self):
        """Main event loop — pump messages and handle state transitions."""
        while self.running:
            try:
                self.client._pump_messages(timeout=1)

                if self.state == self.IDLE:
                    # TODO: In Phase 4, poll trigger site here
                    pass

                elif self.state == self.QUEUING:
                    # Check for timeout
                    if time.time() - self._queue_start > QUEUE_TIMEOUT_S:
                        print("[bot] Queue timed out, returning to IDLE")
                        self.client.cancel_queue()
                        self._set_state(self.IDLE)

                elif self.state == self.PLAYING:
                    # Game is in progress — messages handled by GamePlayer
                    if self.player.game_over:
                        print(f"[bot] Game over: {self.player.result}")
                        self.player.reset()
                        self._set_state(self.IDLE)

            except KeyboardInterrupt:
                print("\n[bot] Interrupted, shutting down...")
                self.running = False
            except Exception as e:
                print(f"[bot] Error in main loop: {e}")
                time.sleep(1)

        self.client.disconnect()
        print("[bot] Shut down.")

    def _on_message(self, inner):
        """Handle messages from the Prismata server."""
        if not inner:
            return

        msg_type = inner[0]

        # BeginGame transitions us to PLAYING
        if msg_type == "BeginGame":
            self._set_state(self.PLAYING)
            self.player.handle_message(inner)
        elif self.state == self.PLAYING:
            self.player.handle_message(inner)

    def _set_state(self, new_state):
        """Transition to a new state."""
        old = self.state
        self.state = new_state
        print(f"[bot] State: {old} → {new_state}")

    # --- Manual triggers (for testing before Phase 4) ---

    def queue_for_bot_game(self):
        """Start a game vs the in-game Master Bot (for testing)."""
        print("[bot] Starting bot game...")
        self.player.reset()
        self.client.start_bot_game()
        self._set_state(self.QUEUING)
        self._queue_start = time.time()

    def queue_for_ranked(self):
        """Queue for ranked play."""
        print("[bot] Queuing for ranked...")
        self.player.reset()
        self.client.queue_ranked()
        self._set_state(self.QUEUING)
        self._queue_start = time.time()


def main():
    """Entry point."""
    bot = DeadGameBot()

    # Handle SIGINT gracefully
    def handle_sigint(sig, frame):
        bot.running = False
    signal.signal(signal.SIGINT, handle_sigint)

    bot.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add bot/ranked_bot.py
git commit -m "feat(bot): main bot process with state machine

IDLE→QUEUING→PLAYING state machine. Orchestrates client, bridge,
and game player. Manual trigger methods for testing."
```

---

### Task 7: Integration Test — Bot vs Master Bot

This task depends on **protocol capture being complete** (Task 1). After the protocol messages are documented:

**Files:**
- Modify: `bot/client.py` — fill in `start_bot_game()`, `queue_ranked()`, `cancel_queue()` with real message names
- Modify: `bot/game_player.py` — implement `_build_ai_request()` with real state conversion

- [ ] **Step 1: Update client.py with captured protocol messages**

Replace the `NotImplementedError` stubs in `bot/client.py` with the actual message sends discovered during protocol capture. For example (message names are guesses — use actual captured names):

```python
def start_bot_game(self):
    # Replace with actual message from protocol capture
    self._send_main(["ACTUAL_MESSAGE_NAME", "ACTUAL_PARAMS"])
```

- [ ] **Step 2: Implement state conversion in game_player.py**

After examining the BeginGame payload from protocol capture, implement `_build_ai_request()` to convert the server's game state format into PrismataAI.exe's expected input format.

The key mapping will depend on what the server sends. Likely:
- The server sends initial card set in BeginGame
- Each turn, the server sends the full game state (or we need to reconstruct it from clicks)
- PrismataAI.exe expects `{mergedDeck, gameState, aiParameters, aiPlayerName}`

- [ ] **Step 3: Run the bot against Master Bot**

```bash
cd c:/libraries/PrismataAI
set BOT_USERNAME=WonderYacht
set BOT_PASSWORD=<password>
python -m bot.ranked_bot
```

Then in the Python console or via a separate script, call `bot.queue_for_bot_game()`. Watch the console output for:
- BeginGame received
- Turn-by-turn clicks and evals
- GameOver with result

- [ ] **Step 4: Debug and iterate**

This step will likely require multiple iterations. Common issues:
- Click format mismatch (server uses different format than PrismataAI output)
- State conversion errors (missing fields, wrong field names)
- Timing issues (need to send EndSwoosh at the right time)
- Turn detection (how to know when it's our turn)

- [ ] **Step 5: Commit working integration**

```bash
git add bot/client.py bot/game_player.py
git commit -m "feat(bot): bot plays vs Master Bot end-to-end

Protocol messages filled from capture, state conversion working.
Tested against in-game Master Bot."
```

---

## Phase 3: Bot Plays Ranked

### Task 8: Ranked Queue Support

**Files:**
- Modify: `bot/client.py` — fill in `queue_ranked()` and `cancel_queue()` if not done in Task 7

- [ ] **Step 1: Update queue methods with captured protocol**

```python
def queue_ranked(self, time_controls=None):
    if time_controls is None:
        time_controls = [45, 60]  # all except bullet
    # Replace with actual message from protocol capture
    self._send_main(["ACTUAL_QUEUE_MESSAGE", time_controls])
```

- [ ] **Step 2: Test ranked queue**

```bash
set BOT_USERNAME=WonderYacht
set BOT_PASSWORD=<password>
python -m bot.ranked_bot
```

Queue for ranked. On another account (DeadGameBot or your main), also queue for ranked. They should match. Watch the game play out. Spectate from a third account if possible.

- [ ] **Step 3: Handle edge cases**

Test and handle:
- Queue timeout (no opponent found) → return to IDLE
- Opponent resigns → GameOver with appropriate result
- Opponent disconnects → server sends GameOver
- Bot resignation → eval_pct < 5% for 3 turns → leave game

- [ ] **Step 4: Commit**

```bash
git add bot/
git commit -m "feat(bot): ranked queue support with edge case handling"
```

---

## Phase 4: Trigger Site

### Task 9: Express Server + SQLite

**Files:**
- Create: `deadgame/package.json`
- Create: `deadgame/server.js`
- Create: `deadgame/lib/db.js`
- Create: `deadgame/lib/auth.js`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "deadgame",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "better-sqlite3": "^11.0.0",
    "cookie-parser": "^1.4.6",
    "express": "^4.21.0",
    "jose": "^5.2.0"
  }
}
```

- [ ] **Step 2: Create database module**

```javascript
// deadgame/lib/db.js
'use strict';

const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'deadgame.db');
const LADDER_DB_PATH = process.env.LADDER_DB_PATH || '/opt/prismata/<ladder>.db';
const RATING_THRESHOLD = parseInt(process.env.RATING_THRESHOLD || '1600', 10);
const DAILY_CAP = parseInt(process.env.DAILY_CAP || '5', 10);

let db;
let ladderDb;

function getDb() {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    db.exec(`
      CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        rating_snapshot REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        status TEXT NOT NULL DEFAULT 'pending',
        deny_reason TEXT,
        matched_opponent TEXT,
        replay_code TEXT,
        result TEXT,
        bot_rating_before REAL,
        bot_rating_after REAL,
        completed_at TEXT
      );

      CREATE TABLE IF NOT EXISTS bot_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );

      CREATE INDEX IF NOT EXISTS idx_requests_username ON requests(username);
      CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
      CREATE INDEX IF NOT EXISTS idx_requests_created ON requests(created_at DESC);
    `);

    // Initialize bot_state
    const upsert = db.prepare(`
      INSERT INTO bot_state (key, value, updated_at)
      VALUES (?, ?, datetime('now'))
      ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
    `);
    const state = db.prepare("SELECT value FROM bot_state WHERE key = 'state'").get();
    if (!state) {
      upsert.run('state', 'offline');
      upsert.run('last_heartbeat', '');
      upsert.run('killed', 'false');
    }
  }
  return db;
}

function getLadderDb() {
  if (!ladderDb) {
    try {
      ladderDb = new Database(LADDER_DB_PATH, { readonly: true });
    } catch (e) {
      console.error(`[db] Cannot open ladder DB at ${LADDER_DB_PATH}: ${e.message}`);
      return null;
    }
  }
  return ladderDb;
}

// --- Bot state ---

function getBotState() {
  const d = getDb();
  const rows = d.prepare("SELECT key, value, updated_at FROM bot_state").all();
  const state = {};
  for (const row of rows) {
    state[row.key] = row.value;
    state[row.key + '_at'] = row.updated_at;
  }
  return state;
}

function setBotState(key, value) {
  getDb().prepare(`
    INSERT INTO bot_state (key, value, updated_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
  `).run(key, value);
}

function isBotOnline() {
  const state = getBotState();
  if (state.killed === 'true') return false;
  const hb = state.last_heartbeat;
  if (!hb) return false;
  const elapsed = (Date.now() - new Date(hb + 'Z').getTime()) / 1000;
  return elapsed < 30;
}

function isBotAvailable() {
  if (!isBotOnline()) return false;
  const state = getBotState();
  return state.state === 'idle';
}

// --- Requests ---

function createRequest(username, ratingSnapshot) {
  return getDb().prepare(`
    INSERT INTO requests (username, rating_snapshot, status)
    VALUES (?, ?, 'pending')
  `).run(username, ratingSnapshot);
}

function createDeniedRequest(username, ratingSnapshot, reason) {
  return getDb().prepare(`
    INSERT INTO requests (username, rating_snapshot, status, deny_reason)
    VALUES (?, ?, 'denied', ?)
  `).run(username, ratingSnapshot, reason);
}

function getPendingRequest() {
  return getDb().prepare(
    "SELECT * FROM requests WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
  ).get();
}

function consumeRequest(id, opponent) {
  getDb().prepare(`
    UPDATE requests SET status = 'consumed', matched_opponent = ? WHERE id = ?
  `).run(opponent, id);
}

function completeRequest(id, replayCode, result, botRatingBefore, botRatingAfter) {
  getDb().prepare(`
    UPDATE requests SET replay_code = ?, result = ?,
      bot_rating_before = ?, bot_rating_after = ?,
      completed_at = datetime('now')
    WHERE id = ?
  `).run(replayCode, result, botRatingBefore, botRatingAfter, id);
}

function expirePendingRequests() {
  // Expire requests older than 2 minutes
  getDb().prepare(`
    UPDATE requests SET status = 'expired'
    WHERE status = 'pending' AND created_at < datetime('now', '-2 minutes')
  `).run();
}

function getDailyCount(username) {
  const row = getDb().prepare(`
    SELECT COUNT(*) as cnt FROM requests
    WHERE username = ? AND status = 'consumed'
    AND date(created_at) = date('now')
  `).get(username);
  return row ? row.cnt : 0;
}

function getLastRequestTime(username) {
  const row = getDb().prepare(`
    SELECT created_at FROM requests
    WHERE username = ? AND status IN ('pending', 'consumed')
    ORDER BY created_at DESC LIMIT 1
  `).get(username);
  return row ? row.created_at : null;
}

function getLastGame() {
  return getDb().prepare(`
    SELECT * FROM requests
    WHERE status = 'consumed' AND completed_at IS NOT NULL
    ORDER BY completed_at DESC LIMIT 1
  `).get();
}

// --- Rating lookup ---

function getPlayerRating(prismataUsername) {
  const ldb = getLadderDb();
  if (!ldb) return null;
  try {
    // Find most recent game where this player participated
    const row = ldb.prepare(`
      SELECT p1_name, p2_name, p1_elo, p2_elo FROM games
      WHERE p1_name = ? OR p2_name = ?
      ORDER BY played_at DESC LIMIT 1
    `).get(prismataUsername, prismataUsername);
    if (!row) return null;
    if (row.p1_name === prismataUsername) return row.p1_elo;
    return row.p2_elo;
  } catch (e) {
    console.error(`[db] Rating lookup failed: ${e.message}`);
    return null;
  }
}

// --- Activity detection ---

function hasRecentLowRatedActivity() {
  const ldb = getLadderDb();
  if (!ldb) return false;
  try {
    const row = ldb.prepare(`
      SELECT COUNT(*) as cnt FROM games
      WHERE played_at > datetime('now', '-30 minutes')
      AND (p1_elo < ? OR p2_elo < ?)
    `).get(RATING_THRESHOLD, RATING_THRESHOLD);
    return row && row.cnt > 0;
  } catch (e) {
    console.error(`[db] Activity check failed: ${e.message}`);
    return false;
  }
}

module.exports = {
  getDb, getBotState, setBotState, isBotOnline, isBotAvailable,
  createRequest, createDeniedRequest, getPendingRequest,
  consumeRequest, completeRequest, expirePendingRequests,
  getDailyCount, getLastRequestTime, getLastGame,
  getPlayerRating, hasRecentLowRatedActivity,
  RATING_THRESHOLD, DAILY_CAP,
};
```

- [ ] **Step 3: Create auth module**

```javascript
// deadgame/lib/auth.js
'use strict';

const { jwtVerify } = require('jose');

const SESSION_COOKIE = 'prismata_session';
const SESSION_SECRET = new TextEncoder().encode(
  process.env.SESSION_SECRET || 'dev-secret-change-in-production'
);
const BOT_API_KEY = process.env.BOT_API_KEY || '';

/**
 * Extract and verify the user session from the prismata_session JWT cookie.
 * Returns the SessionUser object or null.
 */
async function getSessionFromRequest(req) {
  const token = req.cookies?.[SESSION_COOKIE];
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, SESSION_SECRET);
    return payload.user || null;
  } catch {
    return null;
  }
}

/**
 * Express middleware: require a logged-in user with a linked Prismata account.
 * Sets req.user on success.
 */
function requireLogin(req, res, next) {
  getSessionFromRequest(req).then(user => {
    if (!user) {
      return res.status(401).json({ error: 'Not logged in' });
    }
    if (!user.prismata_username) {
      return res.status(403).json({ error: 'No Prismata account linked' });
    }
    req.user = user;
    next();
  }).catch(() => {
    res.status(401).json({ error: 'Invalid session' });
  });
}

/**
 * Express middleware: require bot API key in Authorization header.
 */
function requireBotKey(req, res, next) {
  if (!BOT_API_KEY) {
    return res.status(500).json({ error: 'Bot API key not configured' });
  }
  const key = req.headers['authorization']?.replace('Bearer ', '');
  if (key !== BOT_API_KEY) {
    return res.status(401).json({ error: 'Invalid bot API key' });
  }
  next();
}

module.exports = { getSessionFromRequest, requireLogin, requireBotKey };
```

- [ ] **Step 4: Create Express server**

```javascript
// deadgame/server.js
'use strict';

const express = require('express');
const path = require('path');
const cookieParser = require('cookie-parser');

const app = express();
app.use(express.json());
app.use(cookieParser());
app.set('trust proxy', 'loopback');

const PORT = process.env.PORT || 3101;

// Routes
const botRoutes = require('./routes/bot');
app.use('/api/bot', botRoutes);

// Health check
app.get('/healthz', (req, res) => res.json({ ok: true }));

// API 404
app.use('/api', (req, res) => res.status(404).json({ error: 'Not found' }));

// Static files
app.use(express.static(path.join(__dirname, 'public')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start
app.listen(PORT, () => {
  console.log(`[deadgame] Server listening on port ${PORT}`);
});
```

- [ ] **Step 5: Commit**

```bash
git add deadgame/
git commit -m "feat(deadgame): Express server with SQLite audit log and auth

Database schema for requests and bot_state tables.
Rating lookup and activity detection via ladder DB.
JWT session verification for login gating.
Bot API key auth for heartbeat/status endpoints."
```

---

### Task 10: Bot API Routes

**Files:**
- Create: `deadgame/routes/bot.js`

- [ ] **Step 1: Implement bot routes**

```javascript
// deadgame/routes/bot.js
'use strict';

const express = require('express');
const db = require('../lib/db');
const { requireLogin, requireBotKey } = require('../lib/auth');

const router = express.Router();

const COOLDOWN_MS = 10 * 60 * 1000; // 10 minutes

// GET /api/bot/status — public, returns bot state
router.get('/status', (req, res) => {
  db.expirePendingRequests();

  const state = db.getBotState();
  const online = db.isBotOnline();
  const available = db.isBotAvailable();
  const pending = db.getPendingRequest();
  const lastGame = db.getLastGame();
  const activityDetected = db.hasRecentLowRatedActivity();

  res.json({
    state: online ? state.state : 'offline',
    online,
    available,
    pending_request: !!pending,
    activity_detected: activityDetected,
    last_game: lastGame ? {
      opponent: lastGame.matched_opponent,
      result: lastGame.result,
      replay_code: lastGame.replay_code,
      completed_at: lastGame.completed_at,
    } : null,
  });
});

// POST /api/bot/queue — requires login, creates a queue request
router.post('/queue', requireLogin, (req, res) => {
  const username = req.user.prismata_username;

  // Check kill switch
  const state = db.getBotState();
  if (state.killed === 'true') {
    return res.status(503).json({ error: 'Bot has been disabled' });
  }

  // Check bot online and available
  if (!db.isBotOnline()) {
    return res.status(503).json({ error: 'Bot is offline' });
  }
  if (!db.isBotAvailable()) {
    db.createDeniedRequest(username, null, 'bot_busy');
    return res.status(409).json({ error: 'Bot is busy — if multiple people want to play, try queuing ranked normally!' });
  }

  // Activity detection
  if (db.hasRecentLowRatedActivity()) {
    db.createDeniedRequest(username, null, 'activity_detected');
    return res.status(503).json({ error: 'Players are active right now — try queuing normally first!' });
  }

  // Rating check
  const rating = db.getPlayerRating(username);
  if (rating !== null && rating >= db.RATING_THRESHOLD) {
    db.createDeniedRequest(username, rating, 'rating_too_high');
    return res.status(403).json({
      error: `Your rating (${Math.round(rating)}) is high enough to find human opponents!`,
    });
  }

  // Daily cap
  const dailyCount = db.getDailyCount(username);
  if (dailyCount >= db.DAILY_CAP) {
    db.createDeniedRequest(username, rating, 'daily_cap');
    return res.status(429).json({
      error: `Daily limit reached (${db.DAILY_CAP} games per day)`,
      uses_today: dailyCount,
      daily_cap: db.DAILY_CAP,
    });
  }

  // Cooldown
  const lastReq = db.getLastRequestTime(username);
  if (lastReq) {
    const elapsed = Date.now() - new Date(lastReq + 'Z').getTime();
    if (elapsed < COOLDOWN_MS) {
      const remaining = Math.ceil((COOLDOWN_MS - elapsed) / 1000);
      return res.status(429).json({
        error: `Cooldown active — try again in ${remaining}s`,
        cooldown_remaining_s: remaining,
      });
    }
  }

  // Create request
  db.createRequest(username, rating);
  const usesRemaining = db.DAILY_CAP - dailyCount - 1;

  console.log(`[bot] Queue request from ${username} (rating: ${rating || 'new'}, remaining: ${usesRemaining})`);

  res.json({
    ok: true,
    message: 'Bot will queue for ranked shortly',
    disclaimer: 'You are not guaranteed to be matched against the bot — another player may get the match.',
    uses_remaining: usesRemaining,
    daily_cap: db.DAILY_CAP,
  });
});

// POST /api/bot/heartbeat — bot reports it's alive (requires API key)
router.post('/heartbeat', requireBotKey, (req, res) => {
  db.setBotState('last_heartbeat', new Date().toISOString());
  res.json({ ok: true });
});

// POST /api/bot/update-status — bot reports state change (requires API key)
router.post('/update-status', requireBotKey, (req, res) => {
  const { state, matched_opponent, replay_code, result, request_id } = req.body;

  if (state) {
    db.setBotState('state', state);
  }

  // If game completed, update the request record
  if (request_id && (replay_code || result)) {
    db.completeRequest(request_id, replay_code, result, null, null);
  }

  // If matched, mark request as consumed
  if (request_id && matched_opponent) {
    db.consumeRequest(request_id, matched_opponent);
  }

  res.json({ ok: true });
});

// POST /api/bot/kill — remote kill switch (requires API key)
router.post('/kill', requireBotKey, (req, res) => {
  db.setBotState('killed', 'true');
  db.setBotState('state', 'killed');
  console.log('[bot] KILL SWITCH ACTIVATED');
  res.json({ ok: true, message: 'Bot killed' });
});

// POST /api/bot/unkill — re-enable bot (requires API key)
router.post('/unkill', requireBotKey, (req, res) => {
  db.setBotState('killed', 'false');
  console.log('[bot] Kill switch deactivated');
  res.json({ ok: true });
});

module.exports = router;
```

- [ ] **Step 2: Commit**

```bash
git add deadgame/routes/bot.js
git commit -m "feat(deadgame): bot API routes with full gating and audit

Queue endpoint: login, rating check, daily cap, cooldown, activity detection.
Heartbeat/status/kill endpoints with API key auth.
All requests logged to SQLite."
```

---

### Task 11: Trigger Poller — Bot Polls Site

**Files:**
- Create: `bot/trigger_poller.py`
- Modify: `bot/ranked_bot.py` — integrate poller

- [ ] **Step 1: Implement trigger poller**

```python
# bot/trigger_poller.py
"""Trigger poller — polls deadgame.prismata.live for queue requests.

Sends heartbeats so the site knows the bot is online.
Reports state changes back to the site.
"""

import time
import json
import urllib.request
import urllib.error
from bot.config import (
    TRIGGER_SITE_URL, TRIGGER_POLL_INTERVAL_S,
    HEARTBEAT_INTERVAL_S, BOT_API_KEY,
)


class TriggerPoller:
    """Polls the trigger site for queue requests."""

    def __init__(self):
        self.base_url = TRIGGER_SITE_URL.rstrip('/')
        self.last_heartbeat = 0
        self.last_poll = 0

    def poll(self):
        """Check for pending queue requests.

        Returns True if a queue request is pending.
        Also sends heartbeat if enough time has elapsed.
        """
        now = time.time()

        # Send heartbeat if due
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL_S:
            self._send_heartbeat()
            self.last_heartbeat = now

        # Poll for status
        if now - self.last_poll < TRIGGER_POLL_INTERVAL_S:
            return False
        self.last_poll = now

        try:
            data = self._get('/api/bot/status')
            return data.get('pending_request', False)
        except Exception as e:
            print(f"[poller] Poll failed: {e}")
            return False

    def update_status(self, state, **kwargs):
        """Report state change to the trigger site.

        Args:
            state: 'idle', 'queuing', 'playing'
            **kwargs: optional fields: matched_opponent, replay_code, result, request_id
        """
        body = {'state': state, **kwargs}
        try:
            self._post('/api/bot/update-status', body)
        except Exception as e:
            print(f"[poller] Status update failed: {e}")

    def _send_heartbeat(self):
        """Send heartbeat to the site."""
        try:
            self._post('/api/bot/heartbeat', {})
        except Exception as e:
            print(f"[poller] Heartbeat failed: {e}")

    def _get(self, path):
        """HTTP GET with timeout."""
        url = self.base_url + path
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {BOT_API_KEY}')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def _post(self, path, body):
        """HTTP POST with JSON body."""
        url = self.base_url + path
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {BOT_API_KEY}')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
```

- [ ] **Step 2: Integrate poller into ranked_bot.py**

Add to the IDLE state in `_main_loop()`:

```python
# In __init__:
self.poller = TriggerPoller()

# In _main_loop(), IDLE state:
if self.state == self.IDLE:
    if self.poller.poll():
        print("[bot] Queue request received from trigger site!")
        self.queue_for_ranked()
```

Also update `_set_state()` to report to the trigger site:

```python
def _set_state(self, new_state):
    old = self.state
    self.state = new_state
    print(f"[bot] State: {old} → {new_state}")
    self.poller.update_status(new_state)
```

And add import at top:
```python
from bot.trigger_poller import TriggerPoller
```

- [ ] **Step 3: Commit**

```bash
git add bot/trigger_poller.py bot/ranked_bot.py
git commit -m "feat(bot): trigger poller integration

Bot polls deadgame.prismata.live for queue requests.
Sends heartbeats every 10s, reports state changes."
```

---

### Task 12: Frontend

**Files:**
- Create: `deadgame/public/index.html`

- [ ] **Step 1: Create the frontend SPA**

Single HTML page with:
- Status indicator (colored dot + text)
- Queue button (disabled states for various conditions)
- Uses remaining counter
- Last game result
- Explanation text and disclaimers
- Service policy section

The page should poll `/api/bot/status` every 5 seconds to update the UI. The queue button posts to `/api/bot/queue`. Login state is checked via cookie presence.

Create `deadgame/public/index.html` — a self-contained SPA similar in structure to the fabricate frontend (`c:\libraries\prismata-3d\infra\frontend\index.html`). Use vanilla JS, no frameworks. Clean minimal design.

Key UI states:
- **Not logged in**: button disabled, "Log in with your Prismata account"
- **Logged in, bot offline**: button disabled, grey dot, "Bot is offline"
- **Logged in, bot available**: button enabled, green dot, "Queue DeadGameBot"
- **Logged in, bot busy**: button disabled, yellow/red dot, "Bot is queuing/playing"
- **Logged in, rating too high**: button disabled, "Your rating is high enough to find human opponents!"
- **Logged in, activity detected**: button disabled, "Players are active — try queuing first!"
- **Cooldown active**: button disabled, countdown timer
- **Daily cap reached**: button disabled, "Daily limit reached (X/5)"

- [ ] **Step 2: Commit**

```bash
git add deadgame/public/index.html
git commit -m "feat(deadgame): frontend SPA with status, gating, and disclaimers"
```

---

### Task 13: Deployment Infrastructure

**Files:**
- Create: `deadgame/deadgame.service`
- Create: `deadgame/deadgame.nginx.conf`
- Create: `deadgame/deploy.sh`

- [ ] **Step 1: Create systemd service**

```ini
# deadgame/deadgame.service
[Unit]
Description=DeadGameBot Trigger Site
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/deadgame
ExecStart=/usr/bin/node server.js
Environment=NODE_ENV=production
Environment=PORT=3101
Environment=DB_PATH=/opt/deadgame/deadgame.db
Environment=LADDER_DB_PATH=/opt/prismata/<ladder>.db
EnvironmentFile=-/opt/deadgame/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create nginx vhost**

```nginx
# deadgame/deadgame.nginx.conf
server {
    listen 80;
    server_name deadgame.prismata.live;

    location / {
        proxy_pass http://127.0.0.1:3101;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

- [ ] **Step 3: Create deploy script**

```bash
#!/usr/bin/env bash
# deadgame/deploy.sh — Deploy DeadGameBot trigger site to site box
set -euo pipefail

KEY=~/.ssh/<SSH_KEY>.pem
HOST=ubuntu@<SITE_EIP>
SSH="ssh -i $KEY $HOST"
SCP="scp -i $KEY"

echo "=== Deploying DeadGameBot trigger site ==="

# Create directories
$SSH "sudo mkdir -p /opt/deadgame/public /opt/deadgame/lib /opt/deadgame/routes"

# Upload server files
$SCP deadgame/server.js $HOST:/tmp/deadgame-server.js
$SCP deadgame/package.json $HOST:/tmp/deadgame-package.json
$SCP deadgame/lib/db.js $HOST:/tmp/deadgame-db.js
$SCP deadgame/lib/auth.js $HOST:/tmp/deadgame-auth.js
$SCP deadgame/routes/bot.js $HOST:/tmp/deadgame-bot.js
$SCP deadgame/public/index.html $HOST:/tmp/deadgame-index.html

# Upload infrastructure
$SCP deadgame/deadgame.service $HOST:/tmp/deadgame.service
$SCP deadgame/deadgame.nginx.conf $HOST:/tmp/deadgame.nginx.conf

# Fetch secrets from SSM
BOT_API_KEY=$(aws ssm get-parameter --name /deadgame/bot-api-key --region us-east-1 --with-decryption --query "Parameter.Value" --output text 2>/dev/null || echo "")
SESSION_SECRET=$(aws ssm get-parameter --name /<service>/session-secret --region us-east-1 --with-decryption --query "Parameter.Value" --output text 2>/dev/null || echo "dev-secret-change-in-production")

# Install files
$SSH "
  sudo cp /tmp/deadgame-server.js /opt/deadgame/server.js
  sudo cp /tmp/deadgame-package.json /opt/deadgame/package.json
  sudo cp /tmp/deadgame-db.js /opt/deadgame/lib/db.js
  sudo cp /tmp/deadgame-auth.js /opt/deadgame/lib/auth.js
  sudo cp /tmp/deadgame-bot.js /opt/deadgame/routes/bot.js
  sudo cp /tmp/deadgame-index.html /opt/deadgame/public/index.html
  sudo chown -R ubuntu:ubuntu /opt/deadgame
"

# Write .env
$SSH "echo 'BOT_API_KEY=$BOT_API_KEY
SESSION_SECRET=$SESSION_SECRET' | sudo tee /opt/deadgame/.env > /dev/null && sudo chmod 600 /opt/deadgame/.env"

# Install dependencies
$SSH "cd /opt/deadgame && npm install --omit=dev"

# Install systemd service
$SSH "sudo cp /tmp/deadgame.service /etc/systemd/system/deadgame.service && sudo systemctl daemon-reload && sudo systemctl enable deadgame && sudo systemctl restart deadgame"

# Install nginx vhost
$SSH "sudo cp /tmp/deadgame.nginx.conf /etc/nginx/sites-available/deadgame.prismata.live && sudo ln -sf /etc/nginx/sites-available/deadgame.prismata.live /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx"

# SSL
$SSH "sudo certbot --nginx -d deadgame.prismata.live --non-interactive --agree-tos"

# Verify
sleep 2
$SSH "sudo systemctl status deadgame --no-pager" || true
echo ""
echo "=== Checking health ==="
$SSH "curl -s http://localhost:3101/healthz" || echo "Health check failed"

echo ""
echo "=== Deploy complete ==="
echo "Site: https://deadgame.prismata.live"
```

- [ ] **Step 4: Create SSM parameter for bot API key**

```bash
# Generate a random API key
BOT_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
aws ssm put-parameter --name /deadgame/bot-api-key --value "$BOT_KEY" --type SecureString --region us-east-1
echo "Bot API key: $BOT_KEY"
echo "Set this as BOT_API_KEY environment variable on the bot machine"
```

- [ ] **Step 5: Add DNS record**

Add `deadgame.prismata.live` A record pointing to `<SITE_EIP>` (the site box EIP) in your DNS provider.

- [ ] **Step 6: Deploy**

```bash
cd c:/libraries/PrismataAI
bash deadgame/deploy.sh
```

- [ ] **Step 7: Commit**

```bash
git add deadgame/
git commit -m "feat(deadgame): deployment infrastructure

systemd service, nginx vhost, deploy script with SSM secrets.
DNS and SSL setup for deadgame.prismata.live."
```

---

## Phase 5: Polish

### Task 14: Error Recovery and Monitoring

**Files:**
- Modify: `bot/ranked_bot.py`

- [ ] **Step 1: Add reconnect logic**

In the main loop's exception handler, add reconnection:

```python
except ConnectionError as e:
    print(f"[bot] Connection lost: {e}")
    print("[bot] Reconnecting in 5s...")
    self.poller.update_status('offline')
    time.sleep(5)
    try:
        self.client.disconnect()
        self.client = HeadlessGameClient()
        self.player = GamePlayer(self.bridge, self.client)
        self.client.on_message = self._on_message
        self.client.connect()
        self.client.login(BOT_USERNAME, BOT_PASSWORD)
        self.client.wait_for_lobby()
        self._set_state(self.IDLE)
    except Exception as e2:
        print(f"[bot] Reconnect failed: {e2}")
```

- [ ] **Step 2: Commit**

```bash
git add bot/ranked_bot.py
git commit -m "feat(bot): auto-reconnect on connection loss"
```

---

### Task 15: Last Game Display

**Files:**
- Modify: `deadgame/routes/bot.js` — already returns last_game in status
- Modify: `deadgame/public/index.html` — display last game result

- [ ] **Step 1: Update frontend to show last game**

Add a section below the button that displays:
- "Last game: DeadGameBot vs [opponent] — [result] — [replay link]"
- Replay code links to the replay viewer

- [ ] **Step 2: Commit**

```bash
git add deadgame/public/index.html
git commit -m "feat(deadgame): show last game result on frontend"
```

---

## Checklist Summary

| Phase | Task | Description | Depends On |
|---|---|---|---|
| 1 | 1 | Protocol capture (manual) | — |
| 1 | 2 | SteamAI bridge | — |
| 2 | 3 | AMF3 codec | — |
| 2 | 4 | Headless game client | 3 |
| 2 | 5 | Game player + resignation | 2 |
| 2 | 6 | Main bot process | 4, 5 |
| 2 | 7 | Integration test vs Master Bot | 1, 6 |
| 3 | 8 | Ranked queue support | 7 |
| 4 | 9 | Express server + SQLite | — |
| 4 | 10 | Bot API routes | 9 |
| 4 | 11 | Trigger poller | 10 |
| 4 | 12 | Frontend | 10 |
| 4 | 13 | Deployment | 9-12 |
| 5 | 14 | Error recovery | 8 |
| 5 | 15 | Last game display | 13 |

**Parallel opportunities:**
- Tasks 1-3 can run in parallel (protocol capture is manual, bridge and codec are independent)
- Tasks 9-12 (trigger site) can be built in parallel with Phase 2-3 (bot), connected at Task 11
