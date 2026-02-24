#!/usr/bin/env python3
"""
Prismata Replay Code Extractor
===============================

Extracts ALL of your replay codes from the Prismata server.

Requirements: Python 3.8+ (no third-party packages needed)

How it works:
  1. Temporarily patches Prismata.swf so the client connects via hostname (not IP)
  2. Redirects that hostname to 127.0.0.1 (via hosts file)
  3. Runs a local TCP proxy that forwards traffic to the real server
  4. Once you log in, it asks the server for your replay codes
  5. Saves them to a text file (one code per line)
  6. Restores the SWF and hosts file when done

Usage:
  python prismata_replay_dump.py                    # Saves to my_replay_codes.txt
  python prismata_replay_dump.py --output codes.txt # Custom output file

The script needs Administrator privileges to modify the hosts file.
Run the included .bat file, which handles elevation automatically.
"""

import socket
import struct
import threading
import sys
import re
import time
import os
import shutil
import subprocess
import ctypes
import zlib

# ============================================================
# Server Configuration
# ============================================================

REAL_SERVER_IP = "3.229.49.48"
REAL_SERVER_HOST = "ec2-54-83-83-240.compute-1.amazonaws.com"
MAIN_PORT = 11600

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

        if marker == 0x00:    # undefined
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
            return self._read_string_data()
        elif marker == 0x08:  # date
            ref = self.read_u29()
            if ref & 1:
                ms = struct.unpack_from('>d', self.data, self.pos)[0]
                self.pos += 8
                self.object_refs.append(ms)
                return ms
            return self.object_refs[ref >> 1] if (ref >> 1) < len(self.object_refs) else None
        elif marker == 0x09:  # array
            return self._read_array()
        elif marker == 0x0A:  # object
            return self._read_object()
        elif marker == 0x0B:  # XML
            return self._read_string_data()
        elif marker == 0x0C:  # ByteArray
            ref = self.read_u29()
            if ref & 1:
                length = ref >> 1
                self.pos += length
                self.object_refs.append(None)
                return None
            return self.object_refs[ref >> 1] if (ref >> 1) < len(self.object_refs) else None
        else:
            return None

    def _read_string_data(self):
        ref = self.read_u29()
        if ref & 1:
            length = ref >> 1
            s = self.data[self.pos:self.pos + length].decode('utf-8', errors='replace')
            self.pos += length
            self.object_refs.append(s)
            return s
        return self.object_refs[ref >> 1] if (ref >> 1) < len(self.object_refs) else None

    def _read_array(self):
        ref = self.read_u29()
        if ref & 1:
            count = ref >> 1
            arr = []
            self.object_refs.append(arr)
            # Associative portion
            while True:
                key = self.read_string()
                if key == "":
                    break
                self.read_value()  # skip associative values
            # Dense portion
            for _ in range(count):
                arr.append(self.read_value())
            return arr
        else:
            idx = ref >> 1
            if idx < len(self.object_refs):
                return self.object_refs[idx]
            return None

    def _read_object(self):
        ref = self.read_u29()
        if ref & 1:
            traits_ref = ref >> 1
            if traits_ref & 1:
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
                trait_idx = traits_ref >> 1
                if trait_idx < len(self.trait_refs):
                    trait = self.trait_refs[trait_idx]
                else:
                    trait = {"class": "", "sealed_members": [], "dynamic": False, "externalizable": False}

            obj = {}
            self.object_refs.append(obj)

            if trait.get("externalizable"):
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
            return None


def decode_amf3(data):
    """Decode an AMF3 value from bytes."""
    return AMF3Decoder(data).read_value()


# ============================================================
# AMF3 Encoder (minimal)
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
    elif isinstance(val, bool):
        return b'\x03' if val else b'\x02'
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
    return b'\x00'


def encode_frame(payload):
    """Wrap AMF3 payload in a length-prefixed frame."""
    return struct.pack('>i', len(payload)) + payload


# ============================================================
# Message Stream Parser
# ============================================================

class MessageParser:
    """Parses a TCP byte stream into length-prefixed AMF3 messages."""

    def __init__(self):
        self.buffer = bytearray()
        self.next_len = -1

    def feed(self, data):
        """Feed raw TCP data, yields decoded messages."""
        self.buffer.extend(data)
        while True:
            if self.next_len == -1:
                if len(self.buffer) < 4:
                    break
                self.next_len = struct.unpack('>i', self.buffer[:4])[0]
                self.buffer = self.buffer[4:]
            if len(self.buffer) < self.next_len:
                break
            msg_data = bytes(self.buffer[:self.next_len])
            self.buffer = self.buffer[self.next_len:]
            self.next_len = -1
            try:
                yield decode_amf3(msg_data)
            except Exception:
                pass


# ============================================================
# Session State
# ============================================================

class Session:
    """Thread-safe proxy session state."""

    def __init__(self):
        self._lock = threading.Lock()
        self.player_name = None
        self.server_sock = None
        self._lobby_ready = threading.Event()
        self._c2s_lock = threading.Lock()
        self._c2s_offset = 0
        self._c2s_last_real_id = -1

    def set_player(self, name):
        with self._lock:
            self.player_name = name

    def inject_msg(self, inner_msg, label=""):
        """Inject a C->S message through the server socket. Thread-safe."""
        with self._c2s_lock:
            if not self.server_sock:
                return False
            msg_id = self._c2s_last_real_id + self._c2s_offset + 1
            self._c2s_offset += 1
            msg = ["Msg", msg_id, inner_msg]
            try:
                payload = encode_amf3_value(msg)
                self.server_sock.sendall(encode_frame(payload))
                return True
            except Exception:
                return False


# ============================================================
# Message Routing
# ============================================================

def get_msg_type(msg):
    """Extract message type from raw decoded message."""
    if isinstance(msg, list) and len(msg) > 0:
        if msg[0] == "Msg" and len(msg) >= 3:
            inner = msg[2]
            if isinstance(inner, list) and len(inner) > 0:
                return inner[0]
            return None
        return msg[0]
    return None


def get_inner_params(msg):
    """Extract message parameters."""
    if isinstance(msg, list) and len(msg) >= 3 and msg[0] == "Msg":
        inner = msg[2]
        if isinstance(inner, list) and len(inner) > 1:
            return inner[1:]
        return []
    if isinstance(msg, list) and len(msg) > 1:
        return msg[1:]
    return []


# ============================================================
# Replay Dumper
# ============================================================

CODE_RE = re.compile(r'[A-Za-z0-9+@_-]{5}-[A-Za-z0-9+@_-]{5}')

BATCH_SIZE = 100
RATE_LIMIT = 0.3
GETREPLAYS_CAP = 5000  # Server hard cap (confirmed)


class ReplayDumper:
    """Extracts ALL replay codes via hybrid approach:
    1. /getreplays command -> first 5000 codes (instant)
    2. RequestReplays protocol -> remaining codes (batched)
    """

    def __init__(self, session, output_path):
        self.session = session
        self.output_path = output_path
        self.total_count = None
        self.stubs = {}
        self._total_event = threading.Event()
        self._batch_events = {}
        self._pending_lock = threading.Lock()
        self._getreplays_codes = []
        self._getreplays_event = threading.Event()

    def on_total_count(self, total):
        self.total_count = total
        self._total_event.set()

    def on_batch(self, start_index, stubs):
        self.stubs[start_index] = stubs
        with self._pending_lock:
            evt = self._batch_events.get(start_index)
            if evt:
                evt.set()

    def on_server_msg(self, text):
        codes = CODE_RE.findall(text)
        if len(codes) >= 10:
            self._getreplays_codes.extend(codes)
            self._getreplays_event.set()

    def run(self):
        """Main extraction loop."""
        print()
        print("=" * 60)
        print("  REPLAY CODE EXTRACTOR")
        print("=" * 60)
        print()
        print("Waiting for Prismata login...")
        print("(Launch Prismata and log in normally)")
        print()

        if not self.session._lobby_ready.wait(timeout=120):
            print("ERROR: Timed out waiting for login (120s)")
            print("Make sure Prismata is connecting through this proxy.")
            return False

        time.sleep(1)
        name = self.session.player_name or "(unknown)"
        print(f"Logged in as: {name}")

        # Update output filename to include player name
        if name and name not in ("(unknown)", "(resumed)"):
            base, ext = os.path.splitext(self.output_path)
            self.output_path = f"{base}_{name}{ext}"
        print()

        # Step 1: Get total count
        self.session.inject_msg(["RequestNumReplays"])
        if not self._total_event.wait(timeout=15):
            print("ERROR: Server did not respond to replay count request.")
            return False

        total = self.total_count
        print(f"Total replays on server: {total}")

        if total == 0:
            print("No replays to extract!")
            return True

        # Step 2: /getreplays for first batch (instant, up to 5000)
        getreplays_count = min(total, GETREPLAYS_CAP)
        print(f"Requesting first {getreplays_count} codes (instant)...")
        self.session.inject_msg(["Command", f"getreplays {getreplays_count}"])

        if not self._getreplays_event.wait(timeout=30):
            print("WARNING: /getreplays did not respond. Using batch mode for all codes.")
            getreplays_codes = []
        else:
            # Wait for all chunks to arrive
            prev_count = 0
            stable_ticks = 0
            for _ in range(60):
                time.sleep(0.5)
                cur = len(self._getreplays_codes)
                if cur == prev_count:
                    stable_ticks += 1
                    if stable_ticks >= 3:
                        break
                else:
                    stable_ticks = 0
                prev_count = cur
            getreplays_codes = list(self._getreplays_codes)
            print(f"Got {len(getreplays_codes)} codes instantly.")

        # Step 3: Fetch remaining via protocol
        remaining = total - len(getreplays_codes)
        if remaining > 0 and len(getreplays_codes) > 0:
            print(f"Fetching remaining {remaining} codes...")
            extra_codes = self._fetch_batches(len(getreplays_codes), total)
            all_codes = getreplays_codes + extra_codes
        elif len(getreplays_codes) == 0:
            print(f"Fetching all {total} codes via protocol...")
            all_codes = self._fetch_batches(0, total)
        else:
            all_codes = getreplays_codes

        # Step 4: Write output
        print(f"\nWriting {len(all_codes)} codes to {self.output_path}")
        with open(self.output_path, "w", encoding="utf-8") as f:
            for code in all_codes:
                f.write(code + "\n")

        print()
        print("=" * 60)
        print(f"  DONE! {len(all_codes)} replay codes saved")
        print(f"  File: {self.output_path}")
        print("=" * 60)
        print()
        return True

    def _fetch_batches(self, start_from, total):
        remaining = total - start_from
        num_batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
        eta = num_batches * 2
        print(f"  {num_batches} batches, estimated {eta}s")

        codes = []
        for i in range(num_batches):
            start = start_from + i * BATCH_SIZE
            count = min(BATCH_SIZE, total - start)

            evt = threading.Event()
            with self._pending_lock:
                self._batch_events[start] = evt

            self.session.inject_msg(["RequestReplays", start, count])

            if not evt.wait(timeout=30):
                if not self.session.server_sock:
                    print(f"\n  ERROR: Connection to Prismata lost!")
                    break
                # Retry once
                self.session.inject_msg(["RequestReplays", start, count])
                if not evt.wait(timeout=30):
                    time.sleep(RATE_LIMIT)
                    continue

            for stub in self.stubs.get(start, []):
                if isinstance(stub, dict):
                    code = stub.get("hash") or stub.get("code") or stub.get("hashCode")
                    if code and isinstance(code, str) and len(code) > 3:
                        codes.append(code)

            pct = (i + 1) * 100 // num_batches
            print(f"\r  Progress: {len(codes)}/{remaining} ({pct}%)", end="", flush=True)
            time.sleep(RATE_LIMIT)

        print()
        return codes


# ============================================================
# TCP Proxy
# ============================================================

# Global state
_session = Session()
_dumper = None


def _read_u29_at(data, pos):
    """Read a U29 at position in raw bytes."""
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


def _find_msg_id(payload):
    """Find msgId position in a Msg frame. Returns (offset, len, id) or None."""
    if len(payload) < 9 or payload[0] != 0x09:
        return None
    pos = 1
    arr_u29, pos = _read_u29_at(payload, pos)
    if arr_u29 is None or not (arr_u29 & 1) or (arr_u29 >> 1) < 3:
        return None
    if pos >= len(payload) or payload[pos] != 0x01:
        return None
    pos += 1
    if pos >= len(payload) or payload[pos] != 0x06:
        return None
    pos += 1
    str_u29, pos = _read_u29_at(payload, pos)
    if str_u29 is None or not (str_u29 & 1) or (str_u29 >> 1) != 3:
        return None
    if pos + 3 > len(payload) or payload[pos:pos + 3] != b'Msg':
        return None
    pos += 3
    if pos >= len(payload) or payload[pos] != 0x04:
        return None
    pos += 1
    id_start = pos
    msg_id, pos = _read_u29_at(payload, pos)
    if msg_id is None:
        return None
    return (id_start, pos - id_start, msg_id)


def _patch_msg_id(payload, new_id):
    """Rewrite msgId in raw Msg frame bytes."""
    result = _find_msg_id(payload)
    if result is None:
        return payload
    offset, old_len, _ = result
    new_u29 = encode_u29(new_id)
    return bytes(payload[:offset]) + new_u29 + bytes(payload[offset + old_len:])


def _dispatch_message(direction, msg):
    """Route decoded messages to the dumper's handlers."""
    msg_type = get_msg_type(msg)
    if not msg_type or not _dumper:
        return

    params = get_inner_params(msg)

    if msg_type == "LoggedIn" and params:
        name = params[0] if params else None
        _session.set_player(name)

    elif msg_type == "CourierClaimed":
        if not _session.player_name:
            _session.set_player("(resumed)")

    elif msg_type == "SplashToLobby":
        _session._lobby_ready.set()

    elif msg_type == "RequestNumReplaysResponse":
        if params and isinstance(params[0], (int, float)):
            _dumper.on_total_count(int(params[0]))

    elif msg_type == "RequestReplaysResponse":
        if params and len(params) >= 2:
            start_index = params[0]
            stubs = params[1]
            if isinstance(stubs, list):
                _dumper.on_batch(start_index, stubs)

    elif msg_type == "ServerMsg":
        if params and len(params) >= 2 and isinstance(params[1], list):
            text = params[1][0] if params[1] else ""
            if isinstance(text, str):
                _dumper.on_server_msg(text)


def proxy_stream(src, dst, parser, direction, on_moved=None, rewrite_c2s=False):
    """Forward TCP data between client and server, intercepting protocol messages."""
    intercept = (direction == "S->C" and on_moved is not None)
    frame_buf = bytearray()

    try:
        while True:
            data = src.recv(65536)
            if not data:
                break

            if not intercept and not rewrite_c2s:
                dst.sendall(data)
                for msg in parser.feed(data):
                    _dispatch_message(direction, msg)
            else:
                frame_buf.extend(data)
                while len(frame_buf) >= 4:
                    msg_length = struct.unpack('>i', frame_buf[:4])[0]
                    if len(frame_buf) < 4 + msg_length:
                        break

                    raw_payload = bytes(frame_buf[4:4 + msg_length])
                    frame_buf = frame_buf[4 + msg_length:]

                    try:
                        decoded = decode_amf3(raw_payload)
                    except Exception:
                        decoded = None

                    # S->C: Intercept Moved redirect
                    if (intercept and isinstance(decoded, list) and len(decoded) >= 4
                            and decoded[0] == "Moved"):
                        real_ip = decoded[1]
                        port_main = int(decoded[2])
                        port_tls = int(decoded[3])

                        # Start proxying new ports BEFORE forwarding
                        on_moved(real_ip, port_main, port_tls)

                        # Rewrite IP to localhost
                        new_msg = ["Moved", "127.0.0.1", port_main, port_tls]
                        dst.sendall(encode_frame(encode_amf3_value(new_msg)))
                        decoded = new_msg

                    # S->C: Rewrite Ping confirmation to exclude injected messages
                    elif (intercept and isinstance(decoded, list) and len(decoded) >= 3
                            and decoded[0] == "Ping"):
                        with _session._c2s_lock:
                            offset = _session._c2s_offset
                        if offset > 0 and isinstance(decoded[2], (int, float)) and decoded[2] >= 0:
                            adjusted = max(-1, int(decoded[2]) - offset)
                            new_ping = list(decoded)
                            new_ping[2] = adjusted
                            dst.sendall(encode_frame(encode_amf3_value(new_ping)))
                            decoded = new_ping
                        else:
                            dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    # C->S: Track and rewrite msgIds
                    elif rewrite_c2s:
                        id_info = _find_msg_id(raw_payload)
                        if id_info is not None:
                            original_id = id_info[2]
                            with _session._c2s_lock:
                                _session._c2s_last_real_id = original_id
                                offset = _session._c2s_offset
                            if offset != 0:
                                patched = _patch_msg_id(raw_payload, original_id + offset)
                                dst.sendall(encode_frame(patched))
                            else:
                                dst.sendall(struct.pack('>i', msg_length) + raw_payload)
                        else:
                            dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    else:
                        dst.sendall(struct.pack('>i', msg_length) + raw_payload)

                    if decoded is not None:
                        _dispatch_message(direction, decoded)

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def start_dynamic_proxy(real_ip, port, handler, handler_args=()):
    """Start a listener for dynamically-assigned ports (after Moved redirect)."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(5)

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

        threading.Thread(target=accept_loop, daemon=True).start()
    except OSError:
        pass


def handle_client(client_sock, real_ip, real_port):
    """Handle a proxied client connection."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.connect((real_ip, real_port))

    _session.server_sock = server_sock
    with _session._c2s_lock:
        _session._c2s_offset = 0
        _session._c2s_last_real_id = -1

    def on_moved(real_ip, port_main, port_tls):
        start_dynamic_proxy(real_ip, port_main, handle_client)
        start_dynamic_proxy(real_ip, port_tls, blind_forward_handler)

    c2s_parser = MessageParser()
    s2c_parser = MessageParser()

    t1 = threading.Thread(target=proxy_stream,
                          args=(client_sock, server_sock, c2s_parser, "C->S"),
                          kwargs={"rewrite_c2s": True}, daemon=True)
    t2 = threading.Thread(target=proxy_stream,
                          args=(server_sock, client_sock, s2c_parser, "S->C"),
                          kwargs={"on_moved": on_moved}, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def blind_forward(src, dst):
    """Forward bytes without decoding (TLS passthrough)."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def blind_forward_handler(client_sock, real_ip, real_port):
    """Blind TCP forwarder for TLS/policy ports."""
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((real_ip, real_port))
        t1 = threading.Thread(target=blind_forward, args=(client_sock, server_sock), daemon=True)
        t2 = threading.Thread(target=blind_forward, args=(server_sock, client_sock), daemon=True)
        t1.start()
        t2.start()
    except Exception:
        pass


def listen_port(port, real_ip, handler, handler_args=()):
    """Listen on a port and spawn handler threads."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    while True:
        client_sock, _ = srv.accept()
        threading.Thread(target=handler,
                         args=(client_sock, real_ip, port) + handler_args,
                         daemon=True).start()


# ============================================================
# SWF Patching
# ============================================================
# The regular Steam SWF connects by hardcoded IP, bypassing hosts
# file redirects. Patching one byte disables load balancing, forcing
# the client to use the hostname we can redirect.

SWF_FILENAME = "Prismata.swf"
SWF_BACKUP_SUFFIX = ".replay_capture_backup"
SWF_PATCH_OFFSET = 0x1580196   # Offset in decompressed (FWS) file
SWF_PATCH_FROM = 0x27           # AVM2 pushfalse
SWF_PATCH_TO = 0x26             # AVM2 pushtrue

STEAM_SEARCH_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Prismata",
    r"C:\Program Files\Steam\steamapps\common\Prismata",
    r"D:\Steam\steamapps\common\Prismata",
    r"D:\SteamLibrary\steamapps\common\Prismata",
    r"E:\Steam\steamapps\common\Prismata",
    r"E:\SteamLibrary\steamapps\common\Prismata",
]


def find_swf():
    """Find Prismata.swf in common Steam install locations."""
    for search_dir in STEAM_SEARCH_PATHS:
        path = os.path.join(search_dir, SWF_FILENAME)
        if os.path.isfile(path):
            return path
    return None


def _swf_read_patch_byte(swf_data):
    """Read the byte at the patch offset, handling CWS compression."""
    if swf_data[:3] == b"CWS":
        body = zlib.decompress(swf_data[8:])
        return body[SWF_PATCH_OFFSET - 8]
    elif swf_data[:3] == b"FWS":
        return swf_data[SWF_PATCH_OFFSET]
    return None


def _swf_apply_patch(swf_data, new_byte):
    """Apply a patch byte, handling CWS compression."""
    if swf_data[:3] == b"CWS":
        header = swf_data[:8]
        body = zlib.decompress(swf_data[8:])
        offset = SWF_PATCH_OFFSET - 8
        body = body[:offset] + bytes([new_byte]) + body[offset + 1:]
        return header + zlib.compress(body)
    elif swf_data[:3] == b"FWS":
        offset = SWF_PATCH_OFFSET
        return swf_data[:offset] + bytes([new_byte]) + swf_data[offset + 1:]
    return swf_data


def patch_swf(swf_path):
    """Patch Prismata.swf to disable load balancing. Returns True if patched."""
    backup_path = swf_path + SWF_BACKUP_SUFFIX

    with open(swf_path, "rb") as f:
        data = f.read()

    if data[:3] not in (b"CWS", b"FWS"):
        print(f"  WARNING: Not a valid SWF file — skipping patch")
        return False

    current = _swf_read_patch_byte(data)
    if current == SWF_PATCH_TO:
        print("  SWF already patched — OK")
        return True

    if current != SWF_PATCH_FROM:
        print(f"  WARNING: Unexpected byte at patch offset ({current:#x})")
        print(f"  SWF may be a different version — skipping patch")
        return False

    # Create backup
    if not os.path.exists(backup_path):
        shutil.copy2(swf_path, backup_path)

    new_data = _swf_apply_patch(data, SWF_PATCH_TO)
    with open(swf_path, "wb") as f:
        f.write(new_data)

    print("  SWF patched (load balancing disabled)")
    return True


def restore_swf(swf_path):
    """Restore SWF from backup."""
    backup_path = swf_path + SWF_BACKUP_SUFFIX
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, swf_path)
        os.remove(backup_path)
        print("  SWF restored from backup")
        return True

    # No backup — try to reverse the patch directly
    with open(swf_path, "rb") as f:
        data = f.read()
    if _swf_read_patch_byte(data) == SWF_PATCH_TO:
        new_data = _swf_apply_patch(data, SWF_PATCH_FROM)
        with open(swf_path, "wb") as f:
            f.write(new_data)
        print("  SWF unpatched (reversed in-place)")
        return True

    print("  SWF already in original state")
    return True


# ============================================================
# Hosts File Management
# ============================================================

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
HOSTS_ENTRY_PROXY = f"127.0.0.1 {REAL_SERVER_HOST}"
HOSTS_ENTRY_DIRECT = f"{REAL_SERVER_IP} {REAL_SERVER_HOST}"


def is_admin():
    """Check if running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def read_hosts():
    """Read the current hosts file content."""
    try:
        with open(HOSTS_PATH, "r", encoding="utf-8-sig") as f:
            return f.read()
    except Exception:
        return ""


def set_hosts_proxy():
    """Set hosts file to redirect Prismata through our proxy."""
    content = read_hosts()
    lines = content.splitlines()

    # Remove any existing entries for this host
    new_lines = [l for l in lines if REAL_SERVER_HOST not in l]
    new_lines.append(HOSTS_ENTRY_PROXY)

    new_content = "\n".join(new_lines) + "\n"
    try:
        # Use WriteAllText to avoid truncation issues
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        # Flush DNS cache
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        return True
    except PermissionError:
        return False


def set_hosts_direct():
    """Restore hosts file for direct Prismata connection."""
    content = read_hosts()
    lines = content.splitlines()

    # Remove any existing entries for this host
    new_lines = [l for l in lines if REAL_SERVER_HOST not in l]
    new_lines.append(HOSTS_ENTRY_DIRECT)

    new_content = "\n".join(new_lines) + "\n"
    try:
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        return True
    except PermissionError:
        return False


def check_hosts_mode():
    """Check current hosts file state. Returns 'proxy', 'direct', or 'none'."""
    content = read_hosts()
    if HOSTS_ENTRY_PROXY in content:
        return "proxy"
    elif HOSTS_ENTRY_DIRECT in content:
        return "direct"
    elif REAL_SERVER_HOST in content:
        return "unknown"
    return "none"


# ============================================================
# Main
# ============================================================

def main():
    global _dumper

    # Parse args
    output_path = "my_replay_codes.txt"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--output" and i < len(sys.argv) - 1:
            output_path = sys.argv[i + 1]
        elif not arg.startswith("-") and i == 1:
            output_path = arg

    output_path = os.path.abspath(output_path)

    print()
    print("=" * 60)
    print("  Prismata Replay Code Extractor")
    print("=" * 60)
    print()
    print(f"  Output: {output_path}")
    print(f"  Server: {REAL_SERVER_IP}")
    print()

    # Check admin privileges
    if not is_admin():
        print("ERROR: This script needs Administrator privileges to modify")
        print("the Windows hosts file. Please run as Administrator.")
        print()
        print("If using the .bat file, right-click -> Run as administrator")
        input("Press Enter to exit...")
        return 1

    # Patch SWF (so client uses hostname instead of hardcoded IP)
    print("Setting up...")
    swf_path = find_swf()
    swf_patched = False
    if swf_path:
        swf_patched = patch_swf(swf_path)
    else:
        print("  WARNING: Could not find Prismata.swf — skipping SWF patch")
        print("  The tool may not work if Prismata uses IP-based connections.")

    # Set hosts to proxy mode
    prev_mode = check_hosts_mode()
    if not set_hosts_proxy():
        print("ERROR: Could not modify hosts file.")
        if swf_patched:
            restore_swf(swf_path)
        input("Press Enter to exit...")
        return 1
    print("  Hosts file: proxy mode (127.0.0.1)")
    print()

    # Create dumper
    _dumper = ReplayDumper(_session, output_path)

    # Start proxy listeners
    print("Starting proxy...")
    for port, handler in [(MAIN_PORT, handle_client),
                          (11601, blind_forward_handler),
                          (11619, blind_forward_handler)]:
        threading.Thread(target=listen_port,
                         args=(port, REAL_SERVER_IP, handler),
                         daemon=True).start()
    print("  Proxy ready on ports 11600, 11601, 11619")
    print()

    # Run the dumper
    try:
        success = _dumper.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        success = False
    except Exception as e:
        print(f"\nError: {e}")
        success = False

    # Restore everything
    print("\nRestoring settings...")

    # Restore hosts file
    if prev_mode == "direct":
        set_hosts_direct()
        print("  Hosts file: direct mode (restored)")
    elif prev_mode == "none":
        # Remove our entry entirely
        content = read_hosts()
        lines = [l for l in content.splitlines() if REAL_SERVER_HOST not in l]
        try:
            with open(HOSTS_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        except Exception:
            pass
        print("  Hosts file: cleaned up")
    else:
        set_hosts_direct()
        print("  Hosts file: direct mode")

    # Restore SWF
    if swf_patched and swf_path:
        restore_swf(swf_path)

    print()
    if success:
        # Dumper may have appended player name to the output path
        actual_path = _dumper.output_path if _dumper else output_path
        try:
            total = sum(1 for _ in open(actual_path))
            print(f"Your replay codes are in: {actual_path}")
            print(f"Total: {total} codes")
        except FileNotFoundError:
            print(f"Your replay codes are in: {output_path}")
    else:
        print("Extraction did not complete successfully.")
        print("You can try running the script again.")

    print()
    print("Please restart Prismata before playing again.")
    print()
    input("Press Enter to exit...")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
