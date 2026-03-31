"""
Prismata headless game client for DeadGameBot.

Connects to the Prismata game server via dual TCP connections (main + TLS),
authenticates with PBKDF2 password hashing, and provides methods for playing
ranked games and bot games.

Adapted from <ladder>'s headless_client.py, stripped of spectating
and ladder-tracking code.
"""

import socket
import ssl
import struct
import hmac
import hashlib
import base64
import time
import logging
import warnings

from bot.config import (
    PRISMATA_SERVER_HOST,
    PRISMATA_MAIN_PORT,
    PRISMATA_TLS_PORT,
    PRISMATA_CLIENT_VERSION,
)
from bot.amf3 import encode_amf3_value, decode_amf3

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PBKDF2 -- Prismata's custom derivation (1000 iterations, HMAC-SHA256)
# ---------------------------------------------------------------------------

def prismata_pbkdf2(password: str, salt: str) -> str:
    """Derive password hash using Prismata's custom PBKDF2.

    From decompiled PBKDF2.as:
    - key = password as UTF-8
    - u = HMAC-SHA256(key, salt as UTF-8)
    - accum = u
    - for 1000 iterations: u = HMAC-SHA256(key, u), accum ^= u
    - return Base64(accum)
    """
    key = password.encode("utf-8")
    u = hmac.new(key, salt.encode("utf-8"), hashlib.sha256).digest()
    accum = bytearray(u)
    for _ in range(1000):
        u = hmac.new(key, u, hashlib.sha256).digest()
        for i in range(len(accum)):
            accum[i] ^= u[i]
    return base64.b64encode(bytes(accum)).decode("ascii")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PrismataClient:
    """Dual-connection Prismata client with auth and game-playing protocol."""

    def __init__(self):
        # Sockets
        self.secure_sock = None
        self.main_sock = None

        # Sequence tracking -- last received msg id per socket
        self.secure_last_msg = -1
        self.main_last_msg = -1

        # Outbound sequence ids
        self.sec_msg_id = 0
        self.main_msg_id = 0

        # Auth state
        self.authenticated = False
        self.username = None

        # Lobby state
        self.lobby_ready = False

        # Courier credentials (kept for node-switch reconnect)
        self._main_courier_id = None
        self._main_courier_key = None
        self._sec_courier_id = None
        self._sec_courier_key = None

        # External message callback -- set by GamePlayer / RankedBot
        self.on_message = None

    # ------------------------------------------------------------------
    # Low-level send / recv
    # ------------------------------------------------------------------

    def _send(self, sock, msg):
        """Send a length-prefixed AMF3 message."""
        payload = encode_amf3_value(msg)
        frame = struct.pack(">I", len(payload)) + payload
        sock.sendall(frame)

    def _recv(self, sock, timeout=10):
        """Receive one length-prefixed AMF3 message. Returns None on EOF."""
        sock.settimeout(timeout)
        header = b""
        while len(header) < 4:
            chunk = sock.recv(4 - len(header))
            if not chunk:
                return None
            header += chunk
        length = struct.unpack(">I", header)[0]
        payload = b""
        while len(payload) < length:
            chunk = sock.recv(length - len(payload))
            if not chunk:
                return None
            payload += chunk
        try:
            return decode_amf3(payload)
        except Exception as e:
            log.error("AMF3 decode error: %s (payload %d bytes)", e, len(payload))
            raise

    # ------------------------------------------------------------------
    # Courier helpers
    # ------------------------------------------------------------------

    def _compute_signature(self, courier_key_b64, connection_id_b64):
        """HMAC-SHA256 signature for ClaimCourier."""
        key = base64.b64decode(courier_key_b64)
        data = base64.b64decode(connection_id_b64)
        sig = hmac.new(key, data, hashlib.sha256).digest()
        return base64.b64encode(sig).decode("ascii")

    def _send_secure(self, inner_msg):
        """Send a message via secure courier."""
        msg = ["Msg", self.sec_msg_id, inner_msg]
        msg_type = inner_msg[0] if isinstance(inner_msg, list) and inner_msg else "?"
        log.debug("C->S secure #%d: %s", self.sec_msg_id, msg_type)
        self.sec_msg_id += 1
        self._send(self.secure_sock, msg)

    def _send_main(self, inner_msg):
        """Send a message via main courier."""
        msg = ["Msg", self.main_msg_id, inner_msg]
        msg_type = inner_msg[0] if isinstance(inner_msg, list) and inner_msg else "?"
        log.info("C->S main #%d: %s", self.main_msg_id, msg_type)
        self.main_msg_id += 1
        self._send(self.main_sock, msg)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _make_tls_socket(self, host, port):
        """Create a TLS-wrapped TCP socket."""
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(30)
        raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):
            raw_sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 30000, 10000))
        raw_sock.connect((host, port))

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_ciphers("DEFAULT:@SECLEVEL=0:AES128-SHA:AES256-SHA")
        context.minimum_version = ssl.TLSVersion.TLSv1
        context.maximum_version = ssl.TLSVersion.TLSv1_2

        return context.wrap_socket(raw_sock, server_hostname=host)

    def _make_plain_socket(self, host, port):
        """Create a plain TCP socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 30000, 10000))
        sock.connect((host, port))
        return sock

    def connect(self, host=None, main_port=None, tls_port=None):
        """Establish dual connections and claim couriers.

        Args:
            host: Server IP (default from config).
            main_port: Main port (default from config).
            tls_port: TLS port (default from config).
        """
        host = host or PRISMATA_SERVER_HOST
        main_port = main_port or PRISMATA_MAIN_PORT
        tls_port = tls_port or PRISMATA_TLS_PORT

        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # --- TLS connection (secure courier) ---
        self.secure_sock = self._make_tls_socket(host, tls_port)

        msg = self._recv(self.secure_sock)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Expected Connected, got: {msg}")
        sec_conn_id = msg[1]

        # Request couriers
        self._send(self.secure_sock, ["NewCouriers"])
        msg = self._recv(self.secure_sock)
        if not msg or msg[0] != "CouriersCreated":
            raise ConnectionError(f"Expected CouriersCreated, got: {msg}")

        main_id, main_key, sec_id, sec_key = msg[1], msg[2], msg[3], msg[4]
        self._main_courier_id = main_id
        self._main_courier_key = main_key
        self._sec_courier_id = sec_id
        self._sec_courier_key = sec_key

        # Claim secure courier
        sig = self._compute_signature(sec_key, sec_conn_id)
        self._send(self.secure_sock, ["ClaimCourier", -1, sec_id, sig])
        msg = self._recv(self.secure_sock)
        if not msg or msg[0] != "CourierClaimed":
            raise ConnectionError(f"Secure courier claim failed: {msg}")

        # --- Main connection (plain TCP) ---
        self.main_sock = self._make_plain_socket(host, main_port)

        msg = self._recv(self.main_sock)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Expected Connected on main, got: {msg}")
        main_conn_id = msg[1]

        sig = self._compute_signature(main_key, main_conn_id)
        self._send(self.main_sock, ["ClaimCourier", -1, main_id, sig])
        msg = self._recv(self.main_sock)
        if not msg or msg[0] != "CourierClaimed":
            raise ConnectionError(f"Main courier claim failed: {msg}")

        log.info("Connected to %s (main %d, tls %d)", host, main_port, tls_port)
        return True

    # ------------------------------------------------------------------
    # Node switch (Moved handling)
    # ------------------------------------------------------------------

    def _handle_node_switch(self, new_host, new_port, new_secure_port):
        """Reconnect to a different server node, re-claiming existing couriers."""
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        for sock in (self.main_sock, self.secure_sock):
            try:
                sock.close()
            except Exception:
                pass

        # Secure
        self.secure_sock = self._make_tls_socket(new_host, new_secure_port)
        msg = self._recv(self.secure_sock)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Node switch: Expected Connected, got: {msg}")
        sec_conn_id = msg[1]

        sig = self._compute_signature(self._sec_courier_key, sec_conn_id)
        self._send(self.secure_sock, ["ClaimCourier", self.secure_last_msg, self._sec_courier_id, sig])
        msg = self._recv(self.secure_sock)
        if not msg or msg[0] != "CourierClaimed":
            raise ConnectionError(f"Node switch: Secure claim failed: {msg}")

        # Main
        self.main_sock = self._make_plain_socket(new_host, new_port)
        msg = self._recv(self.main_sock)
        if not msg or msg[0] != "Connected":
            raise ConnectionError(f"Node switch: Expected Connected on main, got: {msg}")
        main_conn_id = msg[1]

        sig = self._compute_signature(self._main_courier_key, main_conn_id)
        self._send(self.main_sock, ["ClaimCourier", self.main_last_msg, self._main_courier_id, sig])
        msg = self._recv(self.main_sock)
        if not msg or msg[0] != "CourierClaimed":
            raise ConnectionError(f"Node switch: Main claim failed: {msg}")

        log.info("Node switch to %s:%d/%d complete", new_host, new_port, new_secure_port)

    def _handle_moved(self, msg):
        """Parse Moved message and perform node switch."""
        new_host = msg[1] if len(msg) > 1 else None
        new_port = int(msg[2]) if len(msg) > 2 else PRISMATA_MAIN_PORT
        new_secure_port = int(msg[3]) if len(msg) > 3 else PRISMATA_TLS_PORT
        if new_host:
            log.info("Server redirect to %s:%d/%d", new_host, new_port, new_secure_port)
            self._handle_node_switch(new_host, new_port, new_secure_port)

    # ------------------------------------------------------------------
    # Ping handling
    # ------------------------------------------------------------------

    def _handle_ping(self, sock, msg, last_msg):
        """Respond to a Ping with Pong."""
        self._send(sock, ["Pong", msg[1], last_msg])

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """Authenticate with the Prismata server.

        Handles Salt/LoginPassword flow and Moved redirects during login.
        """
        self._send_secure(["LookupSalt", username])

        # --- Wait for Salt ---
        salt = None
        end_time = time.time() + 15
        while time.time() < end_time:
            # Secure socket
            try:
                msg = self._recv(self.secure_sock, timeout=1)
                if msg:
                    if msg[0] == "Ping":
                        self._handle_ping(self.secure_sock, msg, self.secure_last_msg)
                    elif msg[0] == "Msg":
                        self.secure_last_msg = msg[1]
                        inner = msg[2]
                        if inner[0] in ("Salt", "PasswordSalt"):
                            salt = inner[1]
                            break
                        elif inner[0] == "NoAccount":
                            raise ConnectionError(f"Account not found: {username}")
                        elif inner[0] == "LoginFailed":
                            reason = inner[1] if len(inner) > 1 else "Unknown"
                            raise ConnectionError(f"Login failed: {reason}")
            except socket.timeout:
                pass

            # Main socket -- Moved can arrive here during login
            try:
                msg = self._recv(self.main_sock, timeout=0.1)
                if msg:
                    if msg[0] == "Ping":
                        self._handle_ping(self.main_sock, msg, self.main_last_msg)
                    elif msg[0] == "Moved":
                        self._handle_moved(msg)
                        self._send_secure(["LookupSalt", username])
                    elif msg[0] == "Msg":
                        self.main_last_msg = msg[1]
            except Exception:
                pass

        if not salt:
            raise ConnectionError("Failed to get salt from server")

        # --- Hash and send login ---
        password_hash = prismata_pbkdf2(password, salt)
        self._send_secure(["LoginPassword", username, password_hash, False, PRISMATA_CLIENT_VERSION])

        # --- Wait for LoggedIn ---
        end_time = time.time() + 15
        while time.time() < end_time:
            # Secure socket
            try:
                msg = self._recv(self.secure_sock, timeout=1)
                if msg:
                    if msg[0] == "Ping":
                        self._handle_ping(self.secure_sock, msg, self.secure_last_msg)
                    elif msg[0] == "Msg":
                        self.secure_last_msg = msg[1]
                        inner = msg[2]
                        if inner[0] == "LoggedIn":
                            self.username = inner[1]
                            self.authenticated = True
                            log.info("Logged in as %s", self.username)
                            return True
                        elif inner[0] == "LoginFailed":
                            reason = inner[1] if len(inner) > 1 else "Unknown"
                            raise ConnectionError(f"Login failed: {reason}")
            except socket.timeout:
                pass

            # Main socket -- LoggedIn can arrive here too
            try:
                msg = self._recv(self.main_sock, timeout=0.1)
                if msg:
                    if msg[0] == "Ping":
                        self._handle_ping(self.main_sock, msg, self.main_last_msg)
                    elif msg[0] == "Moved":
                        self._handle_moved(msg)
                        self._send_secure(["LoginPassword", username, password_hash, False, PRISMATA_CLIENT_VERSION])
                    elif msg[0] == "Msg":
                        self.main_last_msg = msg[1]
                        inner = msg[2]
                        if inner[0] == "LoggedIn":
                            self.username = inner[1]
                            self.authenticated = True
                            log.info("Logged in as %s", self.username)
                            return True
                        elif inner[0] == "LoginFailed":
                            reason = inner[1] if len(inner) > 1 else "Unknown"
                            raise ConnectionError(f"Login failed: {reason}")
            except socket.timeout:
                pass
            except ConnectionError:
                raise
            except Exception:
                pass

        raise ConnectionError("Login timeout")

    # ------------------------------------------------------------------
    # Message pump
    # ------------------------------------------------------------------

    def pump_messages(self, timeout=1):
        """Read and dispatch messages from both sockets.

        Messages wrapped as ["Msg", seqId, innerMessage] are unwrapped
        and forwarded to self.on_message(inner).

        Ping/Pong, Moved, and SplashToLobby are handled internally.
        """
        # Re-read socket refs each iteration (node switch may replace them mid-loop)
        for name in ("main", "secure"):
            sock = self.main_sock if name == "main" else self.secure_sock
            try:
                msg = self._recv(sock, timeout=timeout)
                if not msg:
                    continue

                if msg[0] == "Ping":
                    # Use current socket ref for Pong (not stale `sock`)
                    current_sock = self.main_sock if name == "main" else self.secure_sock
                    last = self.main_last_msg if name == "main" else self.secure_last_msg
                    self._handle_ping(current_sock, msg, last)
                elif msg[0] == "Moved":
                    self._handle_moved(msg)
                    break  # sockets replaced — stop iterating this cycle
                elif msg[0] == "Msg":
                    seq_id = msg[1]
                    if name == "main":
                        self.main_last_msg = seq_id
                    else:
                        self.secure_last_msg = seq_id

                    inner = msg[2]
                    if not inner:
                        continue

                    msg_type = inner[0] if isinstance(inner, list) and inner else None
                    if msg_type not in ("ServerPeerInfo", "TopGamesUpdate",
                                        "PersonalLeaderboardUpdate", "EmoteParamsUpdate",
                                        "UpdateLeaderboard", "ServerMsg", "ShowAgreements",
                                        "ProfileUpdated", "UpdateEventLeaderboard",
                                        "PlayerEventUpdate", "PlayerEventScheduleText",
                                        "clientVersion"):
                        log.info("Msg on %s: %s (seq=%d)", name, msg_type, seq_id)

                    # Internal handling
                    if msg_type == "SplashToLobby":
                        self.lobby_ready = True
                        log.info("Lobby ready")
                    elif msg_type == "ExistsDisconnectedGame":
                        log.info("Server reports disconnected game — sending AttemptReconnect")
                        self._send_main(["AttemptReconnect"])

                    # Forward everything to callback
                    if self.on_message:
                        self.on_message(inner)

            except socket.timeout:
                pass
            except OSError as e:
                log.warning("Socket error on %s: %s", name, e)

    # ------------------------------------------------------------------
    # Game-playing protocol
    # ------------------------------------------------------------------

    def start_bot_game(self):
        """Start a game vs Master Bot (HardestAI)."""
        self._send_main(["StartBotGame", "HardestAI", {
            "randomizeBotUnits": False,
            "enablePause": True,
            "enableAnalysis": True,
            "firstPlayer": 0,  # 0=us first, 1=opponent first, 2=random
            "useBase": True,
            "randomizerSet": [],
            "fastBotAnimation": True,
            "randomizerNumRandom": 5,
            "banSet": [],
            "deckName": "Standard",
            "handicap": 0,
            "vendiumScrap": False,
            "infiniteSupplies": False,
            "players": [
                {"time": {"increment": 1000000, "bank": 0, "bankDilution": 0, "initial": 1000000}},
                {"time": {"increment": 1000000, "bank": 0, "bankDilution": 0, "initial": 1000000}},
            ],
            "gracePeriod": 10,
        }])

    def queue_ranked(self, time_controls=None):
        """Queue for ranked play.

        Args:
            time_controls: List of time control names. Defaults to all
                except Bullet.
        """
        if time_controls is None:
            time_controls = [
                "Extra Slow", "Slow", "Medium Slow", "Normal",
                "Quick", "Rapid", "Blitz",
            ]
        self._send_main(["AutomatchEnqueue", {
            "r8": time_controls,
            "r5": time_controls,
        }])

    def cancel_queue(self):
        """Cancel ranked queue."""
        self._send_main(["AutomatchCancel"])

    def send_click(self, game_id, click_data, turn_number):
        """Send a click action to the server.

        Args:
            game_id: UUID string from BeginGame.
            click_data: dict like {"_type": "card clicked", "_id": 0}.
            turn_number: 0-based turn index.
        """
        self._send_main(["Click", game_id, click_data, turn_number])

    def send_end_turn(self, game_id, duration, turn_number, last_click):
        """Send EndTurn to the server.

        Args:
            game_id: UUID string.
            duration: float, seconds the turn took.
            turn_number: 0-based turn index.
            last_click: the final click object (typically
                {"_type": "space clicked", "_id": -1}).
        """
        self._send_main(["EndTurn", game_id, duration, turn_number, last_click])

    def send_end_swoosh(self, game_id, turn_number):
        """Send EndSwoosh -- must be sent before clicks each turn.

        Args:
            game_id: UUID string.
            turn_number: 0-based turn index.
        """
        self._send_main(["EndSwoosh", game_id, turn_number])

    def send_endgrace(self, game_id):
        """Send Endgrace to skip the pre-game countdown."""
        self._send_main(["Endgrace", game_id])

    def send_loading_complete(self, game_id):
        """Report loading complete to the server.

        Sends incremental progress updates matching the real Prismata client:
        0 → 0.99, then LoadingQueueFinished. The server needs to see this
        progression or it declares a loading timeout.
        """
        self._send_main(["ReportGameLoadProgress", game_id, 0])
        self._send_main(["ReportGameLoadProgress", game_id, 0.99])
        self._send_main(["LoadingQueueFinished", game_id])

    def send_finish_game(self, game_id, winner_index, player_index, duration, resigned=False):
        """Acknowledge game end.

        Args:
            game_id: UUID string.
            winner_index: 0 or 1 indicating which player won.
            player_index: Our player index (0 or 1).
            duration: Total game duration in seconds.
            resigned: Whether we resigned.
        """
        self._send_main(["finishGame", game_id, winner_index, player_index, duration, resigned])

    def send_standup_game(self, game_id):
        """Leave the game results screen."""
        self._send_main(["StandUpGame", game_id])
        self._send_main(["QuitMPGame", game_id])

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def disconnect(self):
        """Close both sockets."""
        for sock in (self.main_sock, self.secure_sock):
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        self.main_sock = None
        self.secure_sock = None
        self.authenticated = False
        self.lobby_ready = False
        log.info("Disconnected")
