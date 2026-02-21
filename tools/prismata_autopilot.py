"""
Prismata Autopilot — AI Move Injection via TCP Proxy

Takes the neural AI's recommended moves (from --suggest) and executes them
in the live Prismata client by injecting protocol messages through the sniffer
proxy.  No screen reader, no mouse automation — pure protocol injection.

Architecture:
    Sniffer proxy (StartTurn) -> Autopilot (F6 capture -> --suggest -> parse)
                              -> Inject Click/EndTurn messages back through proxy

Usage:
    # Integrated with sniffer:
    python tools/prismata_sniffer.py proxy --autopilot

    # Standalone dry-run (logs clicks without injecting):
    python tools/prismata_autopilot.py --dry-run

Controls:
    F7              - Trigger one AI turn (semi-auto mode)
    Ctrl+A          - Toggle full-auto mode
    Escape          - Quit (handled by sniffer/advisor)
"""

import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_BIN_DIR = os.path.join(_PROJECT_ROOT, "bin")
_EXE_PATH = os.path.join(_BIN_DIR, "Prismata_Testing.exe")
_TRIGGER_FILE = os.path.join(_BIN_DIR, "autopilot_trigger.txt")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_THINK_MS = 3000
EXE_TIMEOUT_S = 30
CLICK_DELAY_MS = 80          # Delay between injected clicks (ms)
ENDTURN_DELAY_MS = 200        # Extra delay before EndTurn
F6_POLL_TIMEOUT_S = 2.0       # Max wait for clipboard after F6

# Win32 input constants
VK_F6 = 0x75
VK_F7 = 0x76
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

# SendInput structures
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.wintypes.WORD),
                ("wScan", ctypes.wintypes.WORD),
                ("dwFlags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _fields_ = [("type", ctypes.wintypes.DWORD),
                ("_input", _INPUT)]


def _send_key(vk):
    """Send a single keypress via Win32 SendInput."""
    inputs = (INPUT * 2)()
    # Key down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0]._input.ki.wVk = vk
    # Key up
    inputs[1].type = INPUT_KEYBOARD
    inputs[1]._input.ki.wVk = vk
    inputs[1]._input.ki.dwFlags = KEYEVENTF_KEYUP
    ctypes.windll.user32.SendInput(2, ctypes.pointer(inputs[0]),
                                    ctypes.sizeof(INPUT))


def _send_shift_f6():
    """Send Shift+F6 via Win32 SendInput (compact clipboard format)."""
    VK_SHIFT = 0x10
    inputs = (INPUT * 4)()
    # Shift down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0]._input.ki.wVk = VK_SHIFT
    # F6 down
    inputs[1].type = INPUT_KEYBOARD
    inputs[1]._input.ki.wVk = VK_F6
    # F6 up
    inputs[2].type = INPUT_KEYBOARD
    inputs[2]._input.ki.wVk = VK_F6
    inputs[2]._input.ki.dwFlags = KEYEVENTF_KEYUP
    # Shift up
    inputs[3].type = INPUT_KEYBOARD
    inputs[3]._input.ki.wVk = VK_SHIFT
    inputs[3]._input.ki.dwFlags = KEYEVENTF_KEYUP
    ctypes.windll.user32.SendInput(4, ctypes.pointer(inputs[0]),
                                    ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# Clipboard capture with hash-and-wait
# ---------------------------------------------------------------------------

def _get_clipboard_text():
    """Read clipboard text via Win32 API (no tkinter dependency)."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(0):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _hash_text(text):
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _looks_like_gamestate(text):
    if len(text) < 50:
        return False
    return ('"CurrentInfo"' in text or '"gameState"' in text) and '"mergedDeck"' in text


def capture_f6_state(timeout_s=F6_POLL_TIMEOUT_S):
    """Send Shift+F6 to Prismata and poll clipboard for game state JSON.

    Returns the JSON string, or None on timeout.
    Uses hash-and-wait: snapshot clipboard before F6, poll for change.
    """
    # Snapshot current clipboard
    before_hash = _hash_text(_get_clipboard_text())

    # Send Shift+F6
    _send_shift_f6()

    # Poll for clipboard change
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(0.05)
        text = _get_clipboard_text()
        if _hash_text(text) != before_hash and _looks_like_gamestate(text):
            return text

    return None


def _sanitize_gamestate(text):
    """Convert F6 clipboard format to valid JSON (same as advisor)."""
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


# ============================================================
# AI Analysis (subprocess)
# ============================================================

def run_suggest(state_json, think_ms=DEFAULT_THINK_MS, player_name="PrismatAI_AB"):
    """Run --suggest and return parsed JSON result.

    Returns dict with 'ok', 'clicks', 'buy', etc. on success.
    Returns dict with 'ok': False, 'error': ... on failure.
    """
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".json", dir=_BIN_DIR,
                                          prefix="_autopilot_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(state_json)

        cmd = [
            _EXE_PATH,
            "--suggest", temp_path,
            "--player", player_name,
            "--think-time", str(think_ms),
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_BIN_DIR,
        )
        try:
            stdout_text, _ = proc.communicate(timeout=EXE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return {"ok": False, "error": f"Exe timed out after {EXE_TIMEOUT_S}s"}

        stdout_text = stdout_text.strip()
        if not stdout_text:
            return {"ok": False, "error": f"Exe produced no output (exit={proc.returncode})"}

        json_line = stdout_text.split("\n")[-1].strip()
        data = json.loads(json_line)
        return data

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid JSON from exe: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# ============================================================
# Autopilot Engine
# ============================================================

class AutopilotEngine:
    """Orchestrates: state capture -> AI analysis -> protocol injection.

    Registers with the sniffer Session for StartTurn events and injects
    clicks through the existing _inject_msg infrastructure.
    """

    def __init__(self, session, think_ms=DEFAULT_THINK_MS, dry_run=False,
                 auto_mode=False, player_name="PrismatAI_AB"):
        self._session = session
        self._think_ms = think_ms
        self._dry_run = dry_run
        self._auto_mode = auto_mode
        self._player_name = player_name
        self._lock = threading.Lock()
        self._busy = False
        self._enabled = True
        self._is_bot_game = False

        # File trigger polling
        self._trigger_thread = None

    @property
    def auto_mode(self):
        return self._auto_mode

    def toggle_auto_mode(self):
        self._auto_mode = not self._auto_mode
        mode = "FULL-AUTO" if self._auto_mode else "SEMI-AUTO"
        print(f"  [autopilot] Mode: {mode}")
        return self._auto_mode

    # -- Sniffer event callbacks --

    def on_begin_game(self, msg_type, direction, params, raw_msg):
        """Called when a game starts. Detect bot games."""
        # BeginGame params structure varies, but bot games come from StartBotGame
        # We'll track this via the session's game state
        self._is_bot_game = True  # Default to enabled; safer for testing
        print(f"  [autopilot] Game detected (bot_game={self._is_bot_game})")

    def on_start_turn(self, msg_type, direction, params, raw_msg):
        """Called on each StartTurn from server.

        In auto mode: immediately trigger AI analysis + injection.
        In semi-auto mode: wait for file trigger or F7 keypress.
        """
        if not self._enabled:
            return
        if not self._is_bot_game:
            print("  [autopilot] Skipping — not a bot game")
            return

        if self._auto_mode:
            self._trigger_turn()

    def on_game_over(self, msg_type, direction, params, raw_msg):
        """Reset state on game end."""
        self._is_bot_game = False
        with self._lock:
            self._busy = False

    # -- Trigger mechanisms --

    def start_file_trigger_polling(self):
        """Poll for trigger file (semi-auto mode)."""
        self._trigger_thread = threading.Thread(
            target=self._poll_trigger_file, daemon=True)
        self._trigger_thread.start()

    def _poll_trigger_file(self):
        """Check for autopilot_trigger.txt every 500ms."""
        while self._enabled:
            time.sleep(0.5)
            if os.path.exists(_TRIGGER_FILE):
                try:
                    os.unlink(_TRIGGER_FILE)
                except OSError:
                    pass
                print("  [autopilot] Trigger file detected")
                self._trigger_turn()

    def manual_trigger(self):
        """Trigger from external source (e.g., F7 hotkey in advisor)."""
        print("  [autopilot] Manual trigger (F7)")
        self._trigger_turn()

    # -- Core execution --

    def _trigger_turn(self):
        """Execute one full AI turn: capture -> analyze -> inject."""
        with self._lock:
            if self._busy:
                print("  [autopilot] Already busy, skipping")
                return
            self._busy = True

        t = threading.Thread(target=self._execute_turn, daemon=True)
        t.start()

    def _execute_turn(self):
        """Worker thread: full turn execution."""
        try:
            print("  [autopilot] Capturing game state (Shift+F6)...")
            state_json = capture_f6_state()
            if not state_json:
                print("  [autopilot] ERROR: F6 clipboard capture timed out")
                return

            state_json = _sanitize_gamestate(state_json)
            print(f"  [autopilot] State captured ({len(state_json)} bytes)")

            print(f"  [autopilot] Running AI (think={self._think_ms}ms)...")
            result = run_suggest(state_json, self._think_ms, self._player_name)

            if not result.get("ok"):
                print(f"  [autopilot] AI error: {result.get('error', 'unknown')}")
                return

            clicks = result.get("clicks", [])
            phase = result.get("phase", "action")
            eval_pct = result.get("eval_pct", "?")
            buy_list = result.get("buy", [])

            print(f"  [autopilot] AI recommends: eval={eval_pct}, "
                  f"buys={buy_list}, {len(clicks)} clicks, phase={phase}")

            if not clicks:
                print("  [autopilot] No clicks to inject (pass turn)")
                # Still need to send EndSwoosh + space + EndTurn for a pass
                clicks = [{"_type": "space clicked", "_id": -1}]

            # Inject the clicks
            self._inject_turn(clicks, result)

        except Exception as e:
            print(f"  [autopilot] ERROR: {e}")
        finally:
            with self._lock:
                self._busy = False

    def _inject_turn(self, clicks, result):
        """Inject EndSwoosh + all clicks + EndTurn through the proxy."""
        game_id = self._session.game_id
        turn = self._session.turn_number

        if not game_id:
            print("  [autopilot] ERROR: No game_id in session")
            return

        if self._dry_run:
            print(f"  [autopilot] DRY RUN — would inject {len(clicks)} clicks:")
            for i, c in enumerate(clicks):
                print(f"    [{i}] {c['_type']} id={c['_id']}")
            print(f"    [+] EndTurn game={game_id} turn={turn}")
            return

        # 1. EndSwoosh (required before any clicks)
        print(f"  [autopilot] Injecting EndSwoosh (turn={turn})...")
        ok = self._inject_raw(["EndSwoosh", game_id, turn], "EndSwoosh")
        if not ok:
            print("  [autopilot] ERROR: EndSwoosh injection failed")
            return

        time.sleep(CLICK_DELAY_MS / 1000.0)

        # 2. Inject each click
        for i, click in enumerate(clicks):
            click_type = click["_type"]
            click_id = click["_id"]

            ok = self._inject_raw(
                ["Click", game_id, {"_type": click_type, "_id": click_id}, turn],
                f"Click {click_type} id={click_id}"
            )
            if not ok:
                print(f"  [autopilot] ERROR: Click injection failed at index {i}")
                return

            time.sleep(CLICK_DELAY_MS / 1000.0)

        # 3. EndTurn
        time.sleep(ENDTURN_DELAY_MS / 1000.0)
        think_s = result.get("think_ms", self._think_ms) / 1000.0
        final_click = {"_type": "space clicked", "_id": -1}
        ok = self._inject_raw(
            ["EndTurn", game_id, think_s, turn, final_click],
            f"EndTurn turn={turn}"
        )
        if ok:
            print(f"  [autopilot] Turn {turn} injected successfully "
                  f"({len(clicks)} clicks)")
        else:
            print(f"  [autopilot] ERROR: EndTurn injection failed")

    def _inject_raw(self, inner_msg, log_text=""):
        """Inject an arbitrary message through the proxy."""
        return self._session._inject_msg(inner_msg, log_text)


# ============================================================
# Sniffer integration helpers
# ============================================================

def register_autopilot(session, dispatcher, think_ms=DEFAULT_THINK_MS,
                       dry_run=False, auto_mode=False, player_name="PrismatAI_AB"):
    """Create and register an AutopilotEngine with the sniffer dispatcher.

    Called from prismata_sniffer.py when --autopilot is passed.
    Returns the engine instance for external control (e.g., F7 hotkey).
    """
    engine = AutopilotEngine(
        session=session,
        think_ms=think_ms,
        dry_run=dry_run,
        auto_mode=auto_mode,
        player_name=player_name,
    )

    # Register on sniffer message events
    dispatcher.register("BeginGame", "S->C", engine.on_begin_game)
    dispatcher.register("StartTurn", "S->C", engine.on_start_turn)
    dispatcher.register("GameOver", "S->C", engine.on_game_over)

    # Start file trigger polling (for semi-auto mode)
    engine.start_file_trigger_polling()

    mode = "FULL-AUTO" if auto_mode else "SEMI-AUTO (F7 or trigger file)"
    dr = " [DRY RUN]" if dry_run else ""
    print(f"  [autopilot] Registered: think={think_ms}ms, "
          f"mode={mode}{dr}")

    return engine


# ============================================================
# Standalone entry point (for testing)
# ============================================================

def main():
    """Standalone mode: read state from file/clipboard, run suggest, print clicks."""
    import argparse
    parser = argparse.ArgumentParser(description="Prismata Autopilot (standalone)")
    parser.add_argument("state_file", nargs="?",
                        help="F6 state JSON file (or omit to capture from clipboard)")
    parser.add_argument("--think-time", type=int, default=DEFAULT_THINK_MS,
                        help=f"AI think time in ms (default: {DEFAULT_THINK_MS})")
    parser.add_argument("--player", default="PrismatAI_AB",
                        help="AI player name (default: PrismatAI_AB)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log clicks without injecting")
    args = parser.parse_args()

    if args.state_file:
        with open(args.state_file, "r", encoding="utf-8") as f:
            state_json = f.read()
    else:
        print("Press Shift+F6 in Prismata to capture game state...")
        state_json = capture_f6_state(timeout_s=10.0)
        if not state_json:
            print("ERROR: No game state captured from clipboard")
            return

    state_json = _sanitize_gamestate(state_json)
    print(f"State: {len(state_json)} bytes")

    result = run_suggest(state_json, args.think_time, args.player)

    if not result.get("ok"):
        print(f"ERROR: {result.get('error', 'unknown')}")
        return

    print(f"\nEval: {result.get('eval_pct', '?')}")
    print(f"Phase: {result.get('phase', '?')}")
    print(f"Buy: {result.get('buy', [])}")
    print(f"Abilities: {result.get('abilities', [])}")
    print(f"Defense: {result.get('defense', [])}")
    print(f"Think: {result.get('think_ms', '?')}ms")

    clicks = result.get("clicks", [])
    print(f"\nClick sequence ({len(clicks)} clicks):")
    for i, c in enumerate(clicks):
        print(f"  [{i:2d}] {c['_type']:25s} id={c['_id']}")

    print("\nWire messages that would be injected:")
    print(f"  C->S EndSwoosh [gameId, turn]")
    for c in clicks:
        print(f"  C->S Click [gameId, "
              f"{{_type: \"{c['_type']}\", _id: {c['_id']}}}, turn]")
    print(f"  C->S EndTurn [gameId, thinkTime, turn, "
          f"{{_type: \"space clicked\", _id: -1}}]")


if __name__ == "__main__":
    main()
