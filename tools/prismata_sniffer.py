"""
Prismata Network Protocol Sniffer / Proxy

Sits between the Prismata client and game server, decoding all AMF3 messages.
The game uses two TCP connections:
  - Port 11600: Main courier (plaintext AMF3) - game actions, chat, lobby
  - Port 11601: Secure courier (TLS + AMF3) - auth, payments

This proxy intercepts port 11600 (plaintext) to read board state in real-time.

Protocol format:
  [4 bytes: int32 big-endian message length] [AMF3 serialized array]

Message wrapping (reliable delivery):
  ["Msg", msgId, ["MessageType", param1, param2, ...]]
  ["Ping", pingId, lastMsgConfirmed]
  ["Pong", pingId, lastMsgReceived]
  ["Connected", connectionId]
  ["ClaimCourier", lastMsgReceived, courierId, hmacSignature]
  ["CourierClaimed", courierId, lastMsgReceivedByServer]

Game messages (inside Msg wrapper):
  Server->Client: Click, ManyClicks, EndTurn, StartTurn, BeginGame, GameOver, etc.
  Client->Server: Click, EndTurn, EndSwoosh, QuitGame, etc.

Usage:
  1. Add to hosts file: 127.0.0.1 ec2-3-229-49-48.compute-1.amazonaws.com
  2. Run this script
  3. Launch Prismata and play a bot game
  4. All messages will be logged to console and optionally to a file
"""

import ctypes
import ctypes.wintypes
import socket
import struct
import threading
import sys
import json
import re
import time
import os

# ============================================================
# AMF3 Decoder
# ============================================================

class AMF3Decoder:
    """Decodes AMF3 binary data into Python objects."""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.string_refs = []
        self.object_refs = []
        self.trait_refs = []

    def read_u8(self):
        val = self.data[self.pos]
        self.pos += 1
        return val

    def read_u29(self):
        result = 0
        for i in range(4):
            b = self.read_u8()
            if i < 3:
                result = (result << 7) | (b & 0x7F)
                if not (b & 0x80):
                    return result
            else:
                result = (result << 8) | b
                return result
        return result

    def read_string(self):
        ref = self.read_u29()
        if ref & 1:  # inline
            length = ref >> 1
            if length == 0:
                return ""
            s = self.data[self.pos:self.pos + length].decode('utf-8', errors='replace')
            self.pos += length
            self.string_refs.append(s)
            return s
        else:  # reference
            idx = ref >> 1
            if idx < len(self.string_refs):
                return self.string_refs[idx]
            return f"<string_ref:{idx}>"

    def read_value(self):
        marker = self.read_u8()

        if marker == 0x00:  # undefined
            return None
        elif marker == 0x01:  # null
            return None
        elif marker == 0x02:  # false
            return False
        elif marker == 0x03:  # true
            return True
        elif marker == 0x04:  # integer
            val = self.read_u29()
            if val >= 0x10000000:
                val -= 0x20000000
            return val
        elif marker == 0x05:  # double
            val = struct.unpack_from('>d', self.data, self.pos)[0]
            self.pos += 8
            return val
        elif marker == 0x06:  # string
            return self.read_string()
        elif marker == 0x07:  # XMLDocument
            return self._read_string_data("xml")
        elif marker == 0x08:  # date
            ref = self.read_u29()
            if ref & 1:
                ms = struct.unpack_from('>d', self.data, self.pos)[0]
                self.pos += 8
                self.object_refs.append(ms)
                return {"__date__": ms}
            return self.object_refs[ref >> 1]
        elif marker == 0x09:  # array
            return self._read_array()
        elif marker == 0x0A:  # object
            return self._read_object()
        elif marker == 0x0B:  # XML
            return self._read_string_data("xml")
        elif marker == 0x0C:  # ByteArray
            ref = self.read_u29()
            if ref & 1:
                length = ref >> 1
                ba = self.data[self.pos:self.pos + length]
                self.pos += length
                self.object_refs.append(ba)
                return {"__bytes__": ba.hex()[:40] + ("..." if length > 20 else "")}
            return self.object_refs[ref >> 1]
        else:
            return f"<unknown:0x{marker:02x}>"

    def _read_string_data(self, tag):
        ref = self.read_u29()
        if ref & 1:
            length = ref >> 1
            s = self.data[self.pos:self.pos + length].decode('utf-8', errors='replace')
            self.pos += length
            self.object_refs.append(s)
            return s
        return self.object_refs[ref >> 1]

    def _read_array(self):
        ref = self.read_u29()
        if ref & 1:
            count = ref >> 1
            arr = []
            self.object_refs.append(arr)
            # Associative portion
            assoc = {}
            while True:
                key = self.read_string()
                if key == "":
                    break
                assoc[key] = self.read_value()
            # Dense portion
            for _ in range(count):
                arr.append(self.read_value())
            if assoc:
                return {"__assoc__": assoc, "__dense__": arr}
            return arr
        else:
            idx = ref >> 1
            if idx < len(self.object_refs):
                return self.object_refs[idx]
            return f"<array_ref:{idx}>"

    def _read_object(self):
        ref = self.read_u29()
        if ref & 1:
            # Inline object
            traits_ref = ref >> 1
            if traits_ref & 1:
                # Inline traits
                traits_info = traits_ref >> 1
                is_externalizable = bool(traits_info & 1)
                is_dynamic = bool(traits_info & 2)
                sealed_count = traits_info >> 2
                class_name = self.read_string()
                trait = {
                    "class": class_name,
                    "externalizable": is_externalizable,
                    "dynamic": is_dynamic,
                    "sealed_members": []
                }
                for _ in range(sealed_count):
                    trait["sealed_members"].append(self.read_string())
                self.trait_refs.append(trait)
            else:
                # Trait reference
                trait_idx = traits_ref >> 1
                if trait_idx < len(self.trait_refs):
                    trait = self.trait_refs[trait_idx]
                else:
                    trait = {"class": "?", "sealed_members": [], "dynamic": False, "externalizable": False}

            obj = {}
            if trait.get("class"):
                obj["__class__"] = trait["class"]
            self.object_refs.append(obj)

            if trait.get("externalizable"):
                obj["__externalizable__"] = True
                return obj

            for member in trait.get("sealed_members", []):
                obj[member] = self.read_value()

            if trait.get("dynamic"):
                while True:
                    key = self.read_string()
                    if key == "":
                        break
                    obj[key] = self.read_value()

            return obj
        else:
            idx = ref >> 1
            if idx < len(self.object_refs):
                return self.object_refs[idx]
            return f"<object_ref:{idx}>"


def decode_amf3(data):
    """Decode an AMF3 value from bytes."""
    decoder = AMF3Decoder(data)
    return decoder.read_value()


# ============================================================
# AMF3 Encoder (minimal — for rewriting Moved messages)
# ============================================================

def encode_u29(val):
    """Encode a U29 variable-length integer."""
    if val < 0x80:
        return bytes([val])
    elif val < 0x4000:
        return bytes([(val >> 7) | 0x80, val & 0x7F])
    elif val < 0x200000:
        return bytes([(val >> 14) | 0x80, (val >> 7) | 0x80, val & 0x7F])
    else:
        return bytes([(val >> 22) | 0x80, (val >> 15) | 0x80, (val >> 8) | 0x80, val & 0xFF])


def encode_amf3_value(val):
    """Encode a Python value as AMF3 bytes."""
    if isinstance(val, str):
        encoded = val.encode('utf-8')
        return b'\x06' + encode_u29((len(encoded) << 1) | 1) + encoded
    elif isinstance(val, int):
        if 0 <= val < 0x20000000:
            return b'\x04' + encode_u29(val)
        else:
            return b'\x05' + struct.pack('>d', float(val))
    elif isinstance(val, float):
        return b'\x05' + struct.pack('>d', val)
    elif isinstance(val, list):
        result = b'\x09' + encode_u29((len(val) << 1) | 1)
        result += b'\x01'  # empty associative portion
        for item in val:
            result += encode_amf3_value(item)
        return result
    elif val is None:
        return b'\x01'
    elif isinstance(val, bool):
        return b'\x03' if val else b'\x02'
    return b'\x00'  # undefined


def encode_frame(payload):
    """Wrap AMF3 payload in a length-prefixed frame."""
    return struct.pack('>i', len(payload)) + payload


# ============================================================
# Message Stream Parser
# ============================================================

class MessageParser:
    """Parses a TCP byte stream into length-prefixed AMF3 messages."""

    def __init__(self, label):
        self.label = label
        self.buffer = bytearray()
        self.next_msg_length = -1

    def feed(self, data):
        """Feed raw TCP data, yields decoded messages."""
        self.buffer.extend(data)
        while True:
            if self.next_msg_length == -1:
                if len(self.buffer) < 4:
                    break
                self.next_msg_length = struct.unpack('>i', self.buffer[:4])[0]
                self.buffer = self.buffer[4:]

            if len(self.buffer) < self.next_msg_length:
                break

            msg_data = bytes(self.buffer[:self.next_msg_length])
            self.buffer = self.buffer[self.next_msg_length:]
            self.next_msg_length = -1

            try:
                decoded = decode_amf3(msg_data)
                yield decoded
            except Exception as e:
                yield {"__error__": str(e), "__hex__": msg_data[:50].hex()}


# ============================================================
# TCP Proxy
# ============================================================

REAL_SERVER_IP = "3.229.49.48"
REAL_SERVER_HOST = "ec2-54-83-83-240.compute-1.amazonaws.com"
MAIN_PORT = 11600
LISTEN_PORT = 11600  # We'll listen on the same port

# Important game message types that get full logging
GAME_MSG_TYPES = {"BeginGame", "Click", "ManyClicks", "EndTurn",
                  "StartTurn", "GameOver", "GameOverDraw", "GraceOver",
                  "StartBotGame", "CreateGame", "GameCreated"}

# ============================================================
# Hook Framework
# ============================================================

class Session:
    """Thread-safe per-proxy session state, updated by message handlers."""

    def __init__(self):
        self._lock = threading.Lock()
        self.player_name = None
        self.rating = None
        self.game_id = None
        self.game_phase = None  # "lobby", "loading", "playing", "gameover"
        self.replay_codes = []
        self.messages = []
        self.replay_list = []   # Harvested from RequestReplaysResponse
        # Live game state tracking
        self.merged_deck = []       # Card definitions from BeginGame
        self.players = []           # Player names [p1, p2]
        self.randomizer = []        # Random set unit names
        self.turn_number = 0
        self.turn_buys = []         # Cards bought this turn (display names)
        self.last_f6_state = None   # Last parsed F6 clipboard state
        self._player_ids = []       # Player IDs from BeginGame (for chat injection)
        # Lobby readiness (triggered by SplashToLobby — definitive signal that client is ready)
        self._lobby_ready = threading.Event()
        # Commentary chat target — set via CHAT_TARGET env var, defaults to Surfinite (self-PM)
        self._chat_target_id = os.environ.get("CHAT_TARGET", "7709")
        # Chat injection state (thread-safe via _c2s_lock)
        self.server_sock = None         # Set by handle_client for chat injection
        self._c2s_lock = threading.Lock()  # Protects server_sock writes + ID counter
        self._c2s_offset = 0            # Offset added to real C->S msgIds (incremented per injection)
        self._c2s_last_real_id = -1     # Last real C->S msgId seen (before offset)

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def append_replay_code(self, code, result):
        with self._lock:
            self.replay_codes.append((code, result))
            return len(self.replay_codes)

    def append_replay_list(self, codes):
        with self._lock:
            self.replay_list.extend(codes)

    def append_message(self, direction, msg):
        with self._lock:
            self.messages.append((direction, msg))

    def snapshot(self):
        with self._lock:
            return {
                "player_name": self.player_name,
                "rating": self.rating,
                "game_id": self.game_id,
                "game_phase": self.game_phase,
                "replay_codes": list(self.replay_codes),
                "replay_list_count": len(self.replay_list),
                "message_count": len(self.messages),
            }

    def inject_chat(self, target_id, text):
        """Inject a private chat message into the game via the server socket.
        Thread-safe: can be called from any thread.
        Uses offset-based ID: last_real_id + offset + 1."""
        return self._inject_msg(["PrivateChat", str(target_id), str(text)], text)

    def inject_global_chat(self, channel, text):
        """Inject a global/channel chat message. Channel is e.g. 'globalen'."""
        return self._inject_msg(["Chat", str(channel), str(text)], text)

    def _inject_msg(self, inner_msg, log_text=""):
        """Inject an arbitrary message via the server socket. Thread-safe."""
        with self._c2s_lock:
            if not self.server_sock:
                return False
            msg_id = self._c2s_last_real_id + self._c2s_offset + 1
            self._c2s_offset += 1
            msg = ["Msg", msg_id, inner_msg]
            try:
                payload = encode_amf3_value(msg)
                frame = encode_frame(payload)
                self.server_sock.sendall(frame)
                print(f"  [chat] Injected msgId={msg_id}: {inner_msg[0]} {log_text[:80]}")
                return True
            except Exception as e:
                print(f"  [chat] Injection failed: {e}")
                return False


class MessageDispatcher:
    """Registry of message handlers, keyed by (msg_type, direction)."""

    def __init__(self):
        self._handlers = {}  # (msg_type, direction) -> [callable]

    def register(self, msg_type, direction, fn):
        key = (msg_type, direction)
        self._handlers.setdefault(key, []).append(fn)

    def dispatch(self, msg_type, direction, params, raw_msg):
        # Exact (type, direction) match
        for fn in self._handlers.get((msg_type, direction), []):
            try:
                fn(msg_type, direction, params, raw_msg)
            except Exception as e:
                print(f"[!] Handler error ({msg_type}): {e}")
        # Wildcard direction match (type, None)
        for fn in self._handlers.get((msg_type, None), []):
            try:
                fn(msg_type, direction, params, raw_msg)
            except Exception as e:
                print(f"[!] Handler error ({msg_type}): {e}")


def on_message(msg_type, direction=None):
    """Decorator to register a function as a handler for a message type.

    Usage:
        @on_message("GameOver")
        def handle_gameover(msg_type, direction, params, raw_msg):
            ...

        @on_message("Click", direction="C->S")
        def handle_click(msg_type, direction, params, raw_msg):
            ...
    """
    def decorator(fn):
        _dispatcher.register(msg_type, direction, fn)
        return fn
    return decorator


# Module-level singletons (initialized at import time)
session = Session()
_dispatcher = MessageDispatcher()
_log_file = None
_detail_file = None
_codes_file = None

_codes_file_lock = threading.Lock()


def _write_replay_banner(code, result, count):
    """Print replay code banner and write to codes file."""
    print()
    print(f"  ============================================")
    print(f"  REPLAY CODE: {code}")
    print(f"  Result: {result}  |  Game #{count}")
    print(f"  URL: http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{code}.json.gz")
    print(f"  ============================================")
    print()
    if _codes_file:
        with _codes_file_lock:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            _codes_file.write(f"{ts}\t{code}\t{result}\n")
            _codes_file.flush()


# ============================================================
# Built-in Message Handlers
# ============================================================

@on_message("LoggedIn")
def _handle_logged_in(msg_type, direction, params, raw_msg):
    """Track player identity when they log in."""
    if params:
        name = params[0] if len(params) > 0 else None
        session.update(player_name=name, game_phase="lobby")
        print(f"  [session] Logged in as: {name}")


@on_message("CourierClaimed")
def _handle_courier_claimed(msg_type, direction, params, raw_msg):
    """Handle session resume — set player_name so dump-replays can proceed."""
    if not session.player_name:
        session.update(player_name="(resumed)", game_phase="lobby")
        print(f"  [session] Session resumed (CourierClaimed)")


@on_message("SplashToLobby")
def _handle_splash_to_lobby(msg_type, direction, params, raw_msg):
    """Client is fully loaded and in the lobby — safe to inject commands."""
    session._lobby_ready.set()


@on_message("UserInfo")
def _handle_user_info(msg_type, direction, params, raw_msg):
    """Extract rating from UserInfo response."""
    if params and isinstance(params[0], dict):
        info = params[0]
        rating = info.get("rating") or info.get("tierInfo", {}).get("displayTier")
        if rating is not None:
            session.update(rating=rating)
            print(f"  [session] Rating: {rating}")


@on_message("BeginGame")
def _handle_begin_game(msg_type, direction, params, raw_msg):
    """Track game start."""
    game_id = params[0] if params else None
    session.update(game_id=game_id, game_phase="playing")
    print(f"  [session] Game started: {game_id}")


@on_message("GameOver")
def _handle_game_over(msg_type, direction, params, raw_msg):
    """Extract replay code from GameOver message."""
    # GameOver: [winner, loser, hashCode, showDaily, showStreak, ...]
    if len(params) >= 3:
        code = params[2]
        if isinstance(code, str) and len(code) > 3:
            count = session.append_replay_code(code, "WIN/LOSS")
            session.update(game_phase="gameover")
            _write_replay_banner(code, "WIN/LOSS", count)


@on_message("GameOverDraw")
def _handle_game_over_draw(msg_type, direction, params, raw_msg):
    """Extract replay code from GameOverDraw message."""
    # GameOverDraw: [hashCode]
    if len(params) >= 1:
        code = params[0]
        if isinstance(code, str) and len(code) > 3:
            count = session.append_replay_code(code, "DRAW")
            session.update(game_phase="gameover")
            _write_replay_banner(code, "DRAW", count)


@on_message("RequestReplaysResponse")
def _handle_replay_list(msg_type, direction, params, raw_msg):
    """Harvest replay codes from RequestReplaysResponse.
    Wire format: [startIndex, [array of replay stub objects]]
    Each stub has .hash = replay code (AS3 ReplayStub.as:264)."""
    if not params or len(params) < 2:
        return
    start_index = params[0]
    stubs = params[1]
    if not isinstance(stubs, list):
        return
    codes = []
    for stub in stubs:
        if isinstance(stub, dict):
            # Primary key is "hash" (AS3 source), fallback to others
            code = stub.get("hash") or stub.get("code") or stub.get("hashCode")
            if code and isinstance(code, str) and len(code) > 3:
                codes.append(code)
    if codes:
        session.append_replay_list(codes)
        print(f"  [replay-dump] Batch at index {start_index}: {len(codes)} codes")
    # Notify replay dumper if active
    if _replay_dumper:
        _replay_dumper.on_batch(start_index, stubs)


@on_message("RequestNumReplaysResponse")
def _handle_num_replays(msg_type, direction, params, raw_msg):
    """Handle total replay count response. Wire: [totalCount]."""
    if params and isinstance(params[0], (int, float)):
        total = int(params[0])
        print(f"  [replay-dump] Server reports {total} total replays")
        if _replay_dumper:
            _replay_dumper.on_total_count(total)


@on_message("ServerMsg")
def _handle_server_msg_dump(msg_type, direction, params, raw_msg):
    """Capture /getreplays response for replay dumper.
    Wire: ["_NORMAL_", ["text with \\n-separated codes"], -1]"""
    if not _replay_dumper:
        return
    if params and len(params) >= 2 and isinstance(params[1], list):
        # params[1] is a format string array — first element has the raw text
        text = params[1][0] if params[1] else ""
        if isinstance(text, str):
            _replay_dumper.on_server_msg(text)


# ============================================================
# Replay Dumper — batch-extract ALL replay codes via protocol injection
# ============================================================

class ReplayDumper:
    """Extracts ALL replay codes via hybrid approach:

    1. /getreplays chat command → first 5000 codes (instant)
    2. RequestReplays protocol → remaining codes beyond 5000 (batched)
    """

    BATCH_SIZE = 100    # Larger batches for faster extraction (server handles up to 500)
    RATE_LIMIT = 0.3    # Slightly more than AS3 default to be gentle on server
    GETREPLAYS_CAP = 5000  # Confirmed server-side cap (tested Feb 23 — returns max 5000)

    # Replay code pattern: XXXXX-XXXXX (5 chars, dash, 5 chars)
    CODE_RE = re.compile(r'[A-Za-z0-9+@_-]{5}-[A-Za-z0-9+@_-]{5}')

    def __init__(self, output_path):
        self.output_path = output_path
        self.total_count = None
        self.stubs = {}           # startIndex -> list of stub dicts
        self.codes = []           # All extracted codes in order
        self._total_event = threading.Event()
        self._batch_events = {}   # startIndex -> Event
        self._pending_lock = threading.Lock()
        self._getreplays_codes = []  # Codes from /getreplays ServerMsg
        self._getreplays_event = threading.Event()
        self._done = False

    def on_total_count(self, total):
        """Called by RequestNumReplaysResponse handler."""
        self.total_count = total
        self._total_event.set()

    def on_batch(self, start_index, stubs):
        """Called by RequestReplaysResponse handler."""
        self.stubs[start_index] = stubs
        with self._pending_lock:
            evt = self._batch_events.get(start_index)
            if evt:
                evt.set()

    def on_server_msg(self, text):
        """Called by ServerMsg handler — captures /getreplays response."""
        codes = self.CODE_RE.findall(text)
        if len(codes) >= 10:  # Only trigger on bulk code messages, not random chat
            self._getreplays_codes.extend(codes)
            self._getreplays_event.set()

    def run(self):
        """Main dumper loop — call from a background thread."""
        print()
        print("=" * 60)
        print("  REPLAY DUMPER — Extracting ALL replay codes")
        print("=" * 60)
        print()

        # Wait for SplashToLobby — definitive signal that client is fully loaded
        print("[replay-dump] Waiting for Prismata login...")
        print("[replay-dump] (Launch Prismata and log in normally)")
        if not session._lobby_ready.wait(timeout=120):
            print("[replay-dump] ERROR: Timed out waiting for lobby (120s)")
            return
        # Small settle time for remaining post-lobby messages
        time.sleep(1)
        name = session.player_name or "(unknown)"
        print(f"[replay-dump] Logged in as: {name}")

        # Step 1: Get total replay count
        session._inject_msg(["RequestNumReplays"], "RequestNumReplays")
        if not self._total_event.wait(timeout=15):
            print("[replay-dump] ERROR: No response to RequestNumReplays (timeout 15s)")
            return
        total = self.total_count
        print(f"[replay-dump] Total replays: {total}")
        if total == 0:
            print("[replay-dump] No replays to dump!")
            return

        # Step 2: /getreplays 5000 for the first batch (instant, server cap = 5000)
        getreplays_count = min(total, self.GETREPLAYS_CAP)
        print(f"[replay-dump] Sending /getreplays {getreplays_count}...")
        session._inject_msg(["Command", f"getreplays {getreplays_count}"],
                            f"getreplays {getreplays_count}")
        if not self._getreplays_event.wait(timeout=30):
            print("[replay-dump] WARNING: No /getreplays response — falling back to batch mode")
            getreplays_codes = []
        else:
            # Wait for all ServerMsg chunks to arrive (server may split into multiple messages)
            # With large requests (>5000), server may send many chunks — give it more time
            prev_count = 0
            stable_ticks = 0
            for _ in range(60):  # Up to 30 seconds
                time.sleep(0.5)
                cur = len(self._getreplays_codes)
                if cur == prev_count:
                    stable_ticks += 1
                    if stable_ticks >= 3:  # 1.5s of no new codes = done
                        break
                else:
                    stable_ticks = 0
                prev_count = cur
            getreplays_codes = list(self._getreplays_codes)
            print(f"[replay-dump] /getreplays returned {len(getreplays_codes)} codes")

        # Step 3: If we need more, use RequestReplays for the rest
        remaining = total - len(getreplays_codes)
        if remaining > 0 and len(getreplays_codes) > 0:
            print(f"[replay-dump] Fetching remaining {remaining} codes via protocol...")
            start_from = len(getreplays_codes)
            extra_codes = self._fetch_batches(start_from, total)
            all_codes = getreplays_codes + extra_codes
        elif len(getreplays_codes) == 0:
            # Fallback: fetch everything via protocol
            print(f"[replay-dump] Fetching all {total} codes via protocol...")
            all_codes = self._fetch_batches(0, total)
        else:
            all_codes = getreplays_codes

        self.codes = all_codes

        # Step 4: Write to file
        print(f"\n[replay-dump] Writing {len(all_codes)} replay codes to {self.output_path}")
        with open(self.output_path, "w", encoding="utf-8") as f:
            for code in all_codes:
                f.write(code + "\n")

        print()
        print("=" * 60)
        print(f"  DONE! {len(all_codes)} replay codes saved")
        print(f"  File: {self.output_path}")
        print("=" * 60)
        print()
        print("[replay-dump] You can now close this window or press Ctrl+C.")
        self._done = True

    def _fetch_batches(self, start_from, total):
        """Fetch codes via RequestReplays protocol in batches."""
        remaining = total - start_from
        num_batches = (remaining + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        eta_secs = num_batches * 2  # ~2s per batch (rate limit + server response)
        print(f"[replay-dump] {num_batches} batches of {self.BATCH_SIZE}, ~{eta_secs:.0f}s estimated")

        codes = []
        for batch_idx in range(num_batches):
            start = start_from + batch_idx * self.BATCH_SIZE
            count = min(self.BATCH_SIZE, total - start)

            evt = threading.Event()
            with self._pending_lock:
                self._batch_events[start] = evt

            session._inject_msg(["RequestReplays", start, count],
                                f"RequestReplays({start}, {count})")

            if not evt.wait(timeout=30):
                # Check if socket is dead (Prismata disconnected)
                if not session.server_sock:
                    print(f"\n  [replay-dump] ERROR: Connection lost!")
                    break
                session._inject_msg(["RequestReplays", start, count],
                                    f"RequestReplays({start}, {count}) RETRY")
                if not evt.wait(timeout=30):
                    print(f"\n  [replay-dump] SKIP: No response for index {start}")
                    time.sleep(self.RATE_LIMIT)
                    continue

            stubs = self.stubs.get(start, [])
            for stub in stubs:
                if isinstance(stub, dict):
                    code = stub.get("hash") or stub.get("code") or stub.get("hashCode")
                    if code and isinstance(code, str) and len(code) > 3:
                        codes.append(code)

            pct = (batch_idx + 1) * 100 // num_batches
            print(f"\r  [replay-dump] Batch progress: {len(codes)}/{remaining} ({pct}%)", end="", flush=True)
            time.sleep(self.RATE_LIMIT)

        print()
        return codes


# Global replay dumper instance (set when --dump-replays mode is active)
_replay_dumper = None


# Replay code pattern: 5+ alphanumeric chars with hyphens/pluses
_REPLAY_CODE_RE = re.compile(r'(?<!\w)([A-Za-z0-9+@_-]{5,15})(?!\w)')

@on_message("UserChat")
def _handle_user_chat(msg_type, direction, params, raw_msg):
    """Scan chat messages for shared replay codes."""
    # UserChat: [username, message, ...]
    if len(params) >= 2 and isinstance(params[1], str):
        text = params[1]
        matches = _REPLAY_CODE_RE.findall(text)
        for code in matches:
            # Heuristic: replay codes contain both letters and digits/special chars
            has_letter = any(c.isalpha() for c in code)
            has_other = any(not c.isalpha() for c in code)
            if has_letter and has_other:
                session.append_replay_code(code, "CHAT")
                print(f"  [session] Chat replay code: {code} (from {params[0]})")
                if _codes_file:
                    with _codes_file_lock:
                        ts = time.strftime("%Y-%m-%d %H:%M:%S")
                        _codes_file.write(f"{ts}\t{code}\tCHAT:{params[0]}\n")
                        _codes_file.flush()


# ============================================================
# Live Game State Tracking
# ============================================================

# Win32 constants for SendInput
_VK_F6 = 0x75
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

_LIVE_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "bin", "live_game_state.json")


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT)]
    _anonymous_ = ("_u",)
    _fields_ = [("type", ctypes.c_ulong), ("_u", _U)]


def _find_prismata_hwnd():
    """Find the Prismata window handle by title substring."""
    found = []
    def _cb(hwnd, _lparam):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        if "Prismata" in buf.value and buf.value != "Prismata Sniffer":
            found.append(hwnd)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found[0] if found else None


def _send_f6_to_prismata():
    """Send F6 keystroke to Prismata, briefly stealing focus then restoring."""
    hwnd = _find_prismata_hwnd()
    if not hwnd:
        print("  [live] Prismata window not found — skipping F6")
        return False

    user32 = ctypes.windll.user32
    prev_hwnd = user32.GetForegroundWindow()

    if not user32.SetForegroundWindow(hwnd):
        print("  [live] Cannot steal focus — skipping F6")
        return False
    time.sleep(0.05)

    inputs = (_INPUT * 2)(
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_F6, dwFlags=0)),
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_F6, dwFlags=_KEYEVENTF_KEYUP)),
    )
    user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))
    time.sleep(0.05)

    if prev_hwnd and prev_hwnd != hwnd:
        user32.SetForegroundWindow(prev_hwnd)

    return True


def _read_clipboard_win32():
    """Read Unicode text from clipboard using pure win32 API (no tkinter needed)."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _looks_like_gamestate(text):
    """Check if text looks like Prismata F6 game state JSON."""
    if len(text) < 50:
        return False
    return ('"CurrentInfo"' in text or '"gameState"' in text) and '"mergedDeck"' in text


def _sanitize_gamestate(text):
    """Convert F6 clipboard format to valid JSON.

    F6 produces:   "CurrentInfo" : { ... }\\n"TurnStartInfo" : { ... }
    Shift+F6:      { "mergedDeck": ..., "gameState": ..., "aiParameters": ... }
    """
    text = text.strip()
    if text.startswith("{"):
        return text

    brace_start = text.find("{")
    if brace_start == -1:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(brace_start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                inner_json = text[brace_start:i + 1]
                return '{ "CurrentInfo" : ' + inner_json + ' }'

    return text


def _parse_f6_state(json_str):
    """Parse F6 JSON into a structured game state dict."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    # Unwrap CurrentInfo if present
    if "CurrentInfo" in data:
        data = data["CurrentInfo"]

    gs = data.get("gameState", data)

    # Extract resources from gameState
    resources = gs.get("resources", [])

    # Extract cards/units on the board
    cards = gs.get("cards", [])

    # Count units per player
    p1_units = {}
    p2_units = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        name = card.get("type") or card.get("name", "?")
        player = card.get("player", 0)
        target = p1_units if player == 0 else p2_units
        target[name] = target.get(name, 0) + 1

    return {
        "turn": gs.get("turnNumber", "?"),
        "active_player": gs.get("activePlayer", 0),
        "phase": gs.get("activePhase", "?"),
        "resources": resources,
        "p1_units": p1_units,
        "p2_units": p2_units,
        "raw_gameState": gs,
    }


def _write_live_state(state_dict):
    """Write live state to JSON file and print formatted console output."""
    # Write JSON file
    try:
        with open(_LIVE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=2, default=str)
    except OSError as e:
        print(f"  [live] Failed to write state file: {e}")

    # Console output
    ts = time.strftime("%H:%M:%S")
    turn = state_dict.get("turn", "?")
    active = state_dict.get("active_player", 0)
    players = state_dict.get("players", ["P1", "P2"])
    p_name = players[active] if active < len(players) else f"P{active + 1}"

    print()
    print(f"  ========== TURN {turn} — {p_name}'s turn ==========")

    # Resources
    resources = state_dict.get("resources", [])
    res_labels = ["gold", "energy", "green", "blue", "red", "attack"]
    for i, res in enumerate(resources):
        pn = players[i] if i < len(players) else f"P{i + 1}"
        if isinstance(res, list):
            parts = [f"{res_labels[j]}={v}" for j, v in enumerate(res) if j < len(res_labels) and v]
            print(f"  {pn}: {', '.join(parts) if parts else '(no resources)'}")
        elif isinstance(res, dict):
            parts = [f"{k}={v}" for k, v in res.items() if v]
            print(f"  {pn}: {', '.join(parts) if parts else '(no resources)'}")

    # Unit counts
    for i, units in enumerate([state_dict.get("p1_units", {}), state_dict.get("p2_units", {})]):
        pn = players[i] if i < len(players) else f"P{i + 1}"
        if units:
            parts = [f"{name} x{count}" if count > 1 else name for name, count in units.items()]
            print(f"  {pn} units: {', '.join(parts)}")

    print(f"  ================================================")
    print()


def _card_name_from_id(card_id):
    """Look up display name from mergedDeck by card index."""
    deck = session.merged_deck
    if not deck or card_id < 0 or card_id >= len(deck):
        return f"card#{card_id}"
    entry = deck[card_id]
    return entry.get("UIName") or entry.get("name", f"card#{card_id}")


# -- Live state handlers --

_capture_seq = 0
_capture_seq_lock = threading.Lock()

@on_message("BeginGame", direction="S->C")
def _handle_begin_game_live(msg_type, direction, params, raw_msg):
    """Store mergedDeck and player names for live tracking."""
    if not params or not isinstance(params[0], dict):
        return
    info = params[0]

    merged_deck = info.get("mergedDeck", [])
    session.update(merged_deck=merged_deck, turn_number=0, turn_buys=[],
                   last_f6_state=None)

    # Extract player names and IDs from laneInfo
    players = []
    player_ids = []
    lane_info = info.get("laneInfo", [])
    if lane_info and isinstance(lane_info[0], dict):
        for p in lane_info[0].get("players", []):
            players.append(p.get("displayName") or p.get("name", "?"))
            player_ids.append(str(p.get("id", "")))

    session._player_ids = player_ids

    # Extract randomizer set
    randomizer = []
    if lane_info and isinstance(lane_info[0], dict):
        rand_sets = lane_info[0].get("randomizer", [])
        if rand_sets and isinstance(rand_sets[0], list):
            randomizer = rand_sets[0]

    session.update(players=players, randomizer=randomizer)

    p_str = " vs ".join(players) if players else "unknown"
    r_str = ", ".join(randomizer) if randomizer else "none"
    print(f"\n  [live] Game started: {p_str}")
    print(f"  [live] Set: {r_str}")
    print(f"  [live] Deck has {len(merged_deck)} card types")


@on_message("StartTurn", direction="S->C")
def _handle_start_turn_live(msg_type, direction, params, raw_msg):
    """Auto-send F6, capture clipboard, parse and output game state."""
    global _capture_seq

    if not session.merged_deck:
        return  # no active game

    with session._lock:
        session.turn_number += 1
        session.turn_buys = []
        turn = session.turn_number

    with _capture_seq_lock:
        _capture_seq += 1
        my_seq = _capture_seq

    print(f"\n  [live] Turn {turn} started — sending F6...")

    # Send F6 and read clipboard in a background thread to avoid blocking proxy
    def _capture():
        # Snapshot clipboard before F6 to detect when it changes
        old_clip = _read_clipboard_win32()

        if not _send_f6_to_prismata():
            return

        # Poll clipboard until it changes (up to 1s)
        clip = ""
        deadline = time.time() + 1.0
        while time.time() < deadline:
            time.sleep(0.10)
            new_clip = _read_clipboard_win32()
            if new_clip != old_clip and _looks_like_gamestate(new_clip):
                clip = new_clip
                break
        else:
            print("  [live] Clipboard did not update after F6 (timeout)")
            return

        # Debounce: skip if a newer StartTurn has fired
        with _capture_seq_lock:
            if my_seq != _capture_seq:
                return

        sanitized = _sanitize_gamestate(clip)
        state = _parse_f6_state(sanitized)
        if not state:
            print("  [live] Failed to parse game state from clipboard")
            return

        with session._lock:
            state["players"] = list(session.players)
            state["randomizer"] = list(session.randomizer)
            state["turn_buys"] = list(session.turn_buys)
        session.update(last_f6_state=state)

        _write_live_state(state)

    t = threading.Thread(target=_capture, daemon=True)
    t.start()


@on_message("Click", direction="S->C")
def _handle_click_live(msg_type, direction, params, raw_msg):
    """Track opponent buys from server-echoed Click messages."""
    if not params or not session.merged_deck:
        return
    click = params[0] if isinstance(params[0], dict) else None
    if not click:
        return

    click_type = click.get("_type", "")
    card_id = click.get("_id", -1)

    if click_type in ("card clicked", "card shift clicked") and card_id >= 0:
        name = _card_name_from_id(card_id)
        cost = ""
        if session.merged_deck and card_id < len(session.merged_deck):
            cost = session.merged_deck[card_id].get("buyCost", "")
        with session._lock:
            session.turn_buys.append(name)
        cost_str = f" ({cost})" if cost else ""
        print(f"  [live] BUY: {name}{cost_str}")


@on_message("EndTurn", direction="S->C")
def _handle_end_turn_live(msg_type, direction, params, raw_msg):
    """Log turn summary on EndTurn."""
    if not session.merged_deck:
        return
    with session._lock:
        buys = list(session.turn_buys)
        turn = session.turn_number

    time_used = params[0] if params else "?"
    time_bank = params[2] if len(params) > 2 else "?"

    if buys:
        counts = {}
        for b in buys:
            counts[b] = counts.get(b, 0) + 1
        buy_str = ", ".join(f"{n} x{c}" if c > 1 else n for n, c in counts.items())
    else:
        buy_str = "(none)"

    print(f"  [live] Turn {turn} ended | time={time_used}s | bank={time_bank}s | buys: {buy_str}")


@on_message("GameOver")
def _handle_game_over_live(msg_type, direction, params, raw_msg):
    """Clear live state on game end."""
    session.update(merged_deck=[], turn_number=0, turn_buys=[],
                   last_f6_state=None)
    # Clean up state file
    try:
        if os.path.exists(_LIVE_STATE_PATH):
            os.unlink(_LIVE_STATE_PATH)
    except OSError:
        pass


def format_message(direction, msg, truncate=True):
    """Format a decoded message for display. If truncate=False, write full content."""
    ts = time.strftime("%H:%M:%S")
    limit = 200 if truncate else 999999

    if isinstance(msg, list) and len(msg) > 0:
        msg_type = msg[0]

        # Unwrap Msg envelope
        if msg_type == "Msg" and len(msg) >= 3:
            msg_id = msg[1]
            inner = msg[2]
            if isinstance(inner, list) and len(inner) > 0:
                inner_type = inner[0]
                inner_params = inner[1:] if len(inner) > 1 else []

                # Highlight important game messages
                if inner_type in GAME_MSG_TYPES:
                    return f"[{ts}] {direction} #{msg_id} ** {inner_type} ** {json.dumps(inner_params, default=str)[:limit]}"
                return f"[{ts}] {direction} #{msg_id} {inner_type} {json.dumps(inner_params, default=str)[:limit]}"

            return f"[{ts}] {direction} #{msg_id} {json.dumps(inner, default=str)[:limit]}"

        # Protocol messages
        if msg_type in ("Connected", "ClaimCourier", "CourierClaimed", "Ping", "Pong",
                         "RequestServerTime", "ServerTime", "PingMe"):
            params = msg[1:] if len(msg) > 1 else []
            return f"[{ts}] {direction} [{msg_type}] {json.dumps(params, default=str)[:100]}"

        return f"[{ts}] {direction} {json.dumps(msg, default=str)[:limit]}"

    return f"[{ts}] {direction} {json.dumps(msg, default=str)[:limit]}"


def get_msg_type(msg):
    """Extract the message type from a raw message."""
    if isinstance(msg, list) and len(msg) > 0:
        if msg[0] == "Msg" and len(msg) >= 3:
            inner = msg[2]
            if isinstance(inner, list) and len(inner) > 0:
                return inner[0]
            return None
        return msg[0]
    return None


def get_inner_params(msg):
    """Extract message parameters (from Msg envelope or bare message)."""
    if isinstance(msg, list) and len(msg) >= 3 and msg[0] == "Msg":
        inner = msg[2]
        if isinstance(inner, list) and len(inner) > 1:
            return inner[1:]
        return []
    # Bare message (not Msg-wrapped): return params directly
    if isinstance(msg, list) and len(msg) > 1:
        return msg[1:]
    return []


def _read_u29_at(data, pos):
    """Read a U29 variable-length integer at position. Returns (value, new_pos) or (None, pos)."""
    val = 0
    for i in range(4):
        if pos >= len(data):
            return None, pos
        b = data[pos]
        pos += 1
        if i < 3:
            val = (val << 7) | (b & 0x7F)
            if not (b & 0x80):
                return val, pos
        else:
            val = (val << 8) | b
            return val, pos
    return val, pos


def _find_msg_id_in_frame(payload):
    """Find the msgId U29 position in a Msg frame's raw AMF3 bytes.
    Returns (byte_offset, old_u29_len, old_msg_id) or None if not a Msg frame."""
    if len(payload) < 9 or payload[0] != 0x09:
        return None  # Not an array
    pos = 1
    arr_u29, pos = _read_u29_at(payload, pos)
    if arr_u29 is None or not (arr_u29 & 1):
        return None
    if (arr_u29 >> 1) < 3:
        return None  # Too few elements for ["Msg", N, ...]
    if pos >= len(payload) or payload[pos] != 0x01:
        return None  # Missing empty associative portion
    pos += 1
    if pos >= len(payload) or payload[pos] != 0x06:
        return None  # First element not a string
    pos += 1
    str_u29, pos = _read_u29_at(payload, pos)
    if str_u29 is None or not (str_u29 & 1):
        return None  # String reference, not inline
    str_len = str_u29 >> 1
    if str_len != 3 or pos + 3 > len(payload):
        return None
    if payload[pos:pos + 3] != b'Msg':
        return None
    pos += 3
    if pos >= len(payload) or payload[pos] != 0x04:
        return None  # Second element not an integer
    pos += 1
    id_start = pos
    msg_id, pos = _read_u29_at(payload, pos)
    if msg_id is None:
        return None
    return (id_start, pos - id_start, msg_id)


def _patch_msg_id(payload, new_id):
    """Rewrite the msgId U29 in a Msg frame's raw bytes. Returns patched payload."""
    result = _find_msg_id_in_frame(payload)
    if result is None:
        return payload
    offset, old_len, _ = result
    new_u29 = encode_u29(new_id)
    return bytes(payload[:offset]) + new_u29 + bytes(payload[offset + old_len:])


def proxy_stream(src, dst, parser, direction, log_file=None, detail_file=None, codes_file=None,
                 on_moved=None, rewrite_c2s=False):
    """Forward data from src to dst while decoding messages.

    For S->C direction with on_moved set, intercepts Moved messages and rewrites
    the server IP to 127.0.0.1 so the client reconnects through our proxy.

    For C->S direction with rewrite_c2s set, tracks Msg IDs and rewrites them
    to account for injected chat messages (keeps server-side sequence consistent).
    """
    intercept = (direction == "S->C" and on_moved is not None)
    frame_buf = bytearray()

    try:
        while True:
            data = src.recv(65536)
            if not data:
                break

            if not intercept and not rewrite_c2s:
                # Fast path: forward immediately, decode for logging
                dst.sendall(data)
                for msg in parser.feed(data):
                    _log_message(direction, msg, log_file, detail_file, codes_file)
            else:
                # Frame-buffered path: S->C Moved interception or C->S msgId rewriting
                frame_buf.extend(data)
                while len(frame_buf) >= 4:
                    msg_length = struct.unpack('>i', frame_buf[:4])[0]
                    if len(frame_buf) < 4 + msg_length:
                        break  # incomplete frame

                    raw_payload = bytes(frame_buf[4:4 + msg_length])
                    frame_buf = frame_buf[4 + msg_length:]

                    try:
                        decoded = decode_amf3(raw_payload)
                    except Exception as e:
                        decoded = {"__error__": str(e)}

                    # S->C: Check for Moved message: ["Moved", ip, port1, port2]
                    if (intercept and isinstance(decoded, list) and len(decoded) >= 4
                            and decoded[0] == "Moved"):
                        real_ip = decoded[1]
                        port_main = int(decoded[2])
                        port_tls = int(decoded[3])
                        print(f"\n[*] INTERCEPTED Moved -> {real_ip}:{port_main}/{port_tls}")
                        print(f"[*] Rewriting to 127.0.0.1 and proxying new ports...\n")

                        # Start proxying the new ports BEFORE forwarding
                        on_moved(real_ip, port_main, port_tls)

                        # Rewrite and forward
                        new_msg = ["Moved", "127.0.0.1", port_main, port_tls]
                        new_payload = encode_amf3_value(new_msg)
                        dst.sendall(encode_frame(new_payload))
                        decoded = new_msg  # for logging

                    # S->C: Rewrite Ping confirmation to exclude injected messages
                    # Server Ping = ["Ping", pingId, lastC2SMsgConfirmed]
                    # If we injected N messages, server confirms N more than client sent.
                    # Client asserts: "Confirmation cannot be received before sending a message"
                    elif (intercept and isinstance(decoded, list) and len(decoded) >= 3
                            and decoded[0] == "Ping"):
                        with session._c2s_lock:
                            offset = session._c2s_offset
                        if offset > 0 and isinstance(decoded[2], (int, float)) and decoded[2] >= 0:
                            adjusted = max(-1, int(decoded[2]) - offset)
                            new_ping = list(decoded)
                            new_ping[2] = adjusted
                            new_payload = encode_amf3_value(new_ping)
                            dst.sendall(encode_frame(new_payload))
                            decoded = new_ping  # for logging
                        else:
                            dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    elif rewrite_c2s:
                        # C->S: track real msgIds and apply offset for chat injection
                        id_info = _find_msg_id_in_frame(raw_payload)
                        if id_info is not None:
                            original_id = id_info[2]
                            with session._c2s_lock:
                                session._c2s_last_real_id = original_id
                                offset = session._c2s_offset
                            if offset != 0:
                                new_id = original_id + offset
                                patched = _patch_msg_id(raw_payload, new_id)
                                dst.sendall(encode_frame(patched))
                            else:
                                # No injections yet — forward unchanged
                                dst.sendall(struct.pack('>i', msg_length) + raw_payload)
                        else:
                            # Non-Msg frame (Pong, etc.) — forward as-is
                            dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    else:
                        # Forward original frame unchanged
                        dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    _log_message(direction, decoded, log_file, detail_file, codes_file)

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            src.close()
        except:
            pass
        try:
            dst.close()
        except:
            pass


def _log_message(direction, msg, log_file=None, detail_file=None, codes_file=None):
    """Log a decoded message and dispatch to registered handlers."""
    line = format_message(direction, msg, truncate=True)
    print(line)
    if log_file:
        log_file.write(line + "\n")
        log_file.flush()
    msg_type = get_msg_type(msg)
    if detail_file and msg_type in GAME_MSG_TYPES:
        full_line = format_message(direction, msg, truncate=False)
        detail_file.write(full_line + "\n")
        detail_file.flush()
    session.append_message(direction, msg)
    if msg_type:
        params = get_inner_params(msg)
        _dispatcher.dispatch(msg_type, direction, params, msg)


def start_dynamic_proxy(real_ip, port, handler, handler_args=(), label="dynamic"):
    """Start listening on a port for dynamic proxying (e.g., after Moved redirect)."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(5)
        print(f"[*] {label}: listening on port {port} -> {real_ip}:{port}")

        def accept_loop():
            while True:
                try:
                    client_sock, _ = srv.accept()
                    t = threading.Thread(target=handler,
                                         args=(client_sock, real_ip, port) + handler_args,
                                         daemon=True)
                    t.start()
                except OSError:
                    break

        t = threading.Thread(target=accept_loop, daemon=True)
        t.start()
    except OSError as e:
        print(f"[!] {label}: failed to bind port {port}: {e}")


def handle_client(client_sock, real_server_host, real_server_port, log_file=None, detail_file=None, codes_file=None):
    """Handle a client connection by proxying to the real server."""
    print(f"[*] Client connected from {client_sock.getpeername()}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.connect((real_server_host, real_server_port))
    print(f"[*] Connected to real server {real_server_host}:{real_server_port}")

    # Store server socket for chat injection and reset C->S offset
    session.server_sock = server_sock
    with session._c2s_lock:
        session._c2s_offset = 0
        session._c2s_last_real_id = -1

    # Callback for when server sends a Moved message — start proxying new ports
    def on_moved(real_ip, port_main, port_tls):
        # Main courier on new port (with full message decoding + replay code capture)
        start_dynamic_proxy(real_ip, port_main,
                            handle_client, (log_file, detail_file, codes_file),
                            label="Moved-Main")
        # TLS courier on new port (blind passthrough)
        start_dynamic_proxy(real_ip, port_tls,
                            handle_blind_client, ("Moved-TLS",),
                            label="Moved-TLS")

    c2s_parser = MessageParser("C->S")
    s2c_parser = MessageParser("S->C")

    t1 = threading.Thread(target=proxy_stream,
                          args=(client_sock, server_sock, c2s_parser, "C->S", log_file, detail_file),
                          kwargs={"rewrite_c2s": True},
                          daemon=True)
    t2 = threading.Thread(target=proxy_stream,
                          args=(server_sock, client_sock, s2c_parser, "S->C", log_file, detail_file, codes_file),
                          kwargs={"on_moved": on_moved},
                          daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print(f"[*] Connection closed ({len(session.replay_codes)} replay codes captured this session)")


def blind_forward(src, dst, label):
    """Forward bytes without decoding (for TLS passthrough)."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            src.close()
        except:
            pass
        try:
            dst.close()
        except:
            pass


def handle_blind_client(client_sock, real_server_host, real_server_port, label):
    """Blind TCP forwarder for TLS/policy ports."""
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((real_server_host, real_server_port))
        print(f"[*] {label}: forwarding {client_sock.getpeername()} -> {real_server_host}:{real_server_port}")
        t1 = threading.Thread(target=blind_forward, args=(client_sock, server_sock, label), daemon=True)
        t2 = threading.Thread(target=blind_forward, args=(server_sock, client_sock, label), daemon=True)
        t1.start()
        t2.start()
    except Exception as e:
        print(f"[!] {label}: connection failed: {e}")


def listen_port(port, real_ip, real_port, handler, handler_args=()):
    """Listen on a port and spawn handler threads for each connection."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"[*] Listening on port {port} -> {real_ip}:{real_port}")
    while True:
        client_sock, _ = srv.accept()
        t = threading.Thread(target=handler,
                             args=(client_sock, real_ip, real_port) + handler_args,
                             daemon=True)
        t.start()


def run_proxy(real_ip, log_path=None):
    """Run the multi-port TCP proxy."""
    global _log_file, _detail_file, _codes_file
    if log_path:
        _log_file = open(log_path, "a", encoding="utf-8")
        # Detail log: full untruncated game messages
        detail_path = log_path.replace(".log", "_detail.log")
        _detail_file = open(detail_path, "a", encoding="utf-8")
        print(f"[*] Detail log: {detail_path}")
        # Replay codes log
        codes_path = log_path.replace(".log", "_codes.txt")
        _codes_file = open(codes_path, "a", encoding="utf-8")
        print(f"[*] Replay codes: {codes_path}")

    print(f"[*] Prismata proxy starting")
    print(f"[*] Real server: {real_ip}")
    print(f"[*] Replay codes will be captured from GameOver messages")
    print()

    # Port 11600: Main courier (plaintext AMF3 - decode messages)
    t_main = threading.Thread(
        target=listen_port,
        args=(MAIN_PORT, real_ip, MAIN_PORT, handle_client, (_log_file, _detail_file, _codes_file)),
        daemon=True)
    t_main.start()

    # Port 11601: Secure courier (TLS - blind passthrough)
    t_secure = threading.Thread(
        target=listen_port,
        args=(11601, real_ip, 11601, handle_blind_client, ("TLS",)),
        daemon=True)
    t_secure.start()

    # Port 11619: Flash policy server (blind passthrough)
    t_policy = threading.Thread(
        target=listen_port,
        args=(11619, real_ip, 11619, handle_blind_client, ("Policy",)),
        daemon=True)
    t_policy.start()

    print()
    print("[*] All ports ready. Launch Prismata and play a game.")
    print("[*] Replay codes will appear here when games finish.")
    print("[*] Press Ctrl+C to stop.")
    print()

    # Ensure module is importable by name (when running as __main__)
    sys.modules.setdefault('prismata_sniffer', sys.modules[__name__])

    # Live commentary engine (optional — requires anthropic package)
    # Set COMMENTARY=1 env var to enable; disabled by default for chat testing
    if os.environ.get("COMMENTARY", "0") == "1":
        try:
            import prismata_commentator
            if prismata_commentator.start():
                print("[*] Live commentary: ACTIVE")
            else:
                print("[*] Live commentary: disabled (no API key)")
        except ImportError:
            print("[*] Live commentary: not available (pip install anthropic)")
        except Exception as e:
            print(f"[*] Live commentary: failed to start: {e}")
    else:
        print("[*] Live commentary: OFF (set COMMENTARY=1 to enable)")

    # Autopilot engine (optional — --autopilot flag or AUTOPILOT=1 env var)
    _autopilot_engine = None
    autopilot_flag = "--autopilot" in sys.argv or os.environ.get("AUTOPILOT", "0") == "1"
    if autopilot_flag:
        try:
            import prismata_autopilot
            dry_run = "--dry-run" in sys.argv
            auto = "--auto" in sys.argv
            _autopilot_engine = prismata_autopilot.register_autopilot(
                session=session,
                dispatcher=_dispatcher,
                dry_run=dry_run,
                auto_mode=auto,
            )
            mode = "FULL-AUTO" if auto else "SEMI-AUTO"
            dr = " [DRY RUN]" if dry_run else ""
            print(f"[*] Autopilot: {mode}{dr}")
        except ImportError as e:
            print(f"[*] Autopilot: import failed: {e}")
        except Exception as e:
            print(f"[*] Autopilot: failed to start: {e}")
    else:
        print("[*] Autopilot: OFF (pass --autopilot to enable)")

    print()

    # File-trigger for controlled chat injection testing
    # Write a message to bin/chat_trigger.txt and it will be injected once then deleted
    _chat_trigger_path = os.path.join(os.path.dirname(__file__), "..", "bin", "chat_trigger.txt")
    print(f"[*] Chat trigger: write message to {os.path.abspath(_chat_trigger_path)}")
    print(f"[*] C->S msgId rewriting: ENABLED")

    try:
        while True:
            time.sleep(0.5)
            # Check for chat trigger file
            if os.path.exists(_chat_trigger_path):
                try:
                    with open(_chat_trigger_path, "r", encoding="utf-8") as f:
                        chat_text = f.read().strip()
                    os.unlink(_chat_trigger_path)
                    if chat_text:
                        # Support "cmd:command" prefix for server commands (e.g., /getreplays)
                        if chat_text.startswith("cmd:"):
                            cmd_text = chat_text[4:].strip()
                            print(f"  [cmd] Injecting command: {cmd_text}")
                            ok = session._inject_msg(["Command", cmd_text], f"Command: {cmd_text}")
                            if ok:
                                print(f"  [cmd] Sent: {cmd_text}")
                            else:
                                print(f"  [cmd] Failed (no connection?)")
                        # Support "global:message" prefix for global chat
                        elif chat_text.startswith("global:"):
                            global_text = chat_text[7:].strip()
                            print(f"  [chat-test] Sending to global chat: {global_text}")
                            ok = session.inject_global_chat("globalEnglish", global_text)
                            if ok:
                                print(f"  [chat-test] Global sent: {global_text}")
                            else:
                                print(f"  [chat-test] inject_global_chat failed")
                        else:
                            # Private chat — pick first non-empty player ID
                            target_id = None
                            ids = getattr(session, '_player_ids', [])
                            for pid in ids:
                                if pid:
                                    target_id = pid
                                    break
                            print(f"  [chat-test] player_ids={ids}, target={target_id}, server_sock={session.server_sock is not None}")
                            if target_id:
                                ok = session.inject_chat(target_id, chat_text)
                                if ok:
                                    print(f"  [chat-test] Sent: {chat_text}")
                                else:
                                    print(f"  [chat-test] inject_chat failed (no server_sock?)")
                            else:
                                print(f"  [chat-test] No player ID available yet (start a game first)")
                                print(f"  [chat-test] Message was: {chat_text}")
                except Exception as e:
                    print(f"  [chat-test] Error: {e}")
    except KeyboardInterrupt:
        snap = session.snapshot()
        codes = snap["replay_codes"]
        print(f"\n[*] Shutting down. {len(codes)} codes captured:")
        for i, (code, result) in enumerate(codes, 1):
            print(f"  {i}. {code} ({result})")
        print(f"[*] Session: {json.dumps(snap, indent=2)}")
    finally:
        if _log_file:
            _log_file.close()
        if _detail_file:
            _detail_file.close()
        if _codes_file:
            _codes_file.close()


# ============================================================
# Passive Sniffer (connect as client, read server messages)
# ============================================================

def run_passive_test():
    """Connect to the server and decode the initial handshake."""
    print(f"[*] Connecting to {REAL_SERVER_IP}:{MAIN_PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((REAL_SERVER_IP, MAIN_PORT))
    print("[*] Connected!")

    parser = MessageParser("S->C")
    data = s.recv(4096)
    for msg in parser.feed(data):
        print(f"  Server says: {json.dumps(msg, default=str)}")

    s.close()
    print("[*] Done")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        run_passive_test()
    elif len(sys.argv) > 1 and sys.argv[1] in ("proxy", "dump-replays"):
        # Hardcoded real IP (hosts file redirects DNS to 127.0.0.1)
        real_ip = "3.229.49.48"
        log_path = os.path.join(os.path.dirname(__file__), "..", "bin", "prismata_capture.log")

        # --dump-replays mode: extract all replay codes then exit
        if sys.argv[1] == "dump-replays" or "--dump-replays" in sys.argv:
            output_path = os.path.join(os.path.dirname(__file__), "..", "bin", "my_replay_codes.txt")
            # Allow custom output path: dump-replays [output_file]
            for i, arg in enumerate(sys.argv):
                if arg == "--output" and i + 1 < len(sys.argv):
                    output_path = sys.argv[i + 1]
                    break
                elif arg == "dump-replays" and i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("-"):
                    output_path = sys.argv[i + 1]
                    break
            _replay_dumper = ReplayDumper(os.path.abspath(output_path))
            # Start proxy in background, dumper runs after login
            proxy_thread = threading.Thread(target=run_proxy, args=(real_ip, log_path), daemon=True)
            proxy_thread.start()
            # Run dumper on main thread
            _replay_dumper.run()
        else:
            run_proxy(real_ip, log_path)
    else:
        print("Usage:")
        print("  python prismata_sniffer.py test          - Connect and decode server greeting")
        print("  python prismata_sniffer.py proxy         - Run as TCP proxy (captures replay codes)")
        print("  python prismata_sniffer.py dump-replays  - Extract ALL replay codes and save to file")
        print()
        print("Dump replays options:")
        print("  python prismata_sniffer.py dump-replays [output_file]")
        print("  python prismata_sniffer.py dump-replays --output my_codes.txt")
        print(f"  Default output: bin/my_replay_codes.txt")
        print()
        print("For proxy/dump-replays mode:")
        print(f"  1. Add to hosts: 127.0.0.1 {REAL_SERVER_HOST}")
        print(f"  2. Run: python prismata_sniffer.py proxy (or dump-replays)")
        print(f"  3. Launch Prismata and log in")
        print(f"  4. Replay codes appear in console + saved to bin/prismata_capture_codes.txt")
        print(f"  5. When done, restore hosts: 3.229.49.48 {REAL_SERVER_HOST}")
