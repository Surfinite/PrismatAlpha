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

import socket
import struct
import threading
import sys
import json
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

REAL_SERVER = "ec2-3-229-49-48.compute-1.amazonaws.com"
MAIN_PORT = 11600
LISTEN_PORT = 11600  # We'll listen on the same port

# Game state tracking
game_messages = []
current_game = None

# Important game message types that get full logging
GAME_MSG_TYPES = {"BeginGame", "Click", "ManyClicks", "EndTurn",
                  "StartTurn", "GameOver", "GameOverDraw", "GraceOver",
                  "StartBotGame", "CreateGame", "GameCreated"}


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


def proxy_stream(src, dst, parser, direction, log_file=None, detail_file=None):
    """Forward data from src to dst while decoding messages."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
            for msg in parser.feed(data):
                line = format_message(direction, msg, truncate=True)
                print(line)
                if log_file:
                    log_file.write(line + "\n")
                    log_file.flush()
                # Write full untruncated version of game messages to detail file
                msg_type = get_msg_type(msg)
                if detail_file and msg_type in GAME_MSG_TYPES:
                    full_line = format_message(direction, msg, truncate=False)
                    detail_file.write(full_line + "\n")
                    detail_file.flush()
                game_messages.append((direction, msg))
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


def handle_client(client_sock, real_server_host, real_server_port, log_file=None, detail_file=None):
    """Handle a client connection by proxying to the real server."""
    print(f"[*] Client connected from {client_sock.getpeername()}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.connect((real_server_host, real_server_port))
    print(f"[*] Connected to real server {real_server_host}:{real_server_port}")

    c2s_parser = MessageParser("C->S")
    s2c_parser = MessageParser("S->C")

    t1 = threading.Thread(target=proxy_stream,
                          args=(client_sock, server_sock, c2s_parser, "C->S", log_file, detail_file),
                          daemon=True)
    t2 = threading.Thread(target=proxy_stream,
                          args=(server_sock, client_sock, s2c_parser, "S->C", log_file, detail_file),
                          daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("[*] Connection closed")


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
    log_file = None
    detail_file = None
    if log_path:
        log_file = open(log_path, "a", encoding="utf-8")
        # Detail log: full untruncated game messages
        detail_path = log_path.replace(".log", "_detail.log")
        detail_file = open(detail_path, "a", encoding="utf-8")
        print(f"[*] Detail log: {detail_path}")

    print(f"[*] Prismata proxy starting")
    print(f"[*] Real server: {real_ip}")
    print()

    # Port 11600: Main courier (plaintext AMF3 - decode messages)
    t_main = threading.Thread(
        target=listen_port,
        args=(MAIN_PORT, real_ip, MAIN_PORT, handle_client, (log_file, detail_file)),
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
    print("[*] All ports ready. Launch Prismata and play a bot game.")
    print("[*] Press Ctrl+C to stop.")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down")
    finally:
        if log_file:
            log_file.close()
        if detail_file:
            detail_file.close()


# ============================================================
# Passive Sniffer (connect as client, read server messages)
# ============================================================

def run_passive_test():
    """Connect to the server and decode the initial handshake."""
    print(f"[*] Connecting to {REAL_SERVER}:{MAIN_PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect((REAL_SERVER, MAIN_PORT))
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
    elif len(sys.argv) > 1 and sys.argv[1] == "proxy":
        # Hardcoded real IP (hosts file redirects DNS to 127.0.0.1)
        real_ip = "3.229.49.48"
        log_path = os.path.join(os.path.dirname(__file__), "..", "bin", "prismata_capture.log")
        run_proxy(real_ip, log_path)
    else:
        print("Usage:")
        print("  python prismata_sniffer.py test   - Connect and decode server greeting")
        print("  python prismata_sniffer.py proxy  - Run as TCP proxy (requires hosts file redirect)")
        print()
        print("For proxy mode:")
        print(f"  1. Resolve IP first: nslookup {REAL_SERVER}")
        print(f"  2. Add to hosts: 127.0.0.1 {REAL_SERVER}")
        print(f"  3. Run: python prismata_sniffer.py proxy")
        print(f"  4. Launch Prismata and play a bot game")
        print(f"  5. When done, remove the hosts entry")
