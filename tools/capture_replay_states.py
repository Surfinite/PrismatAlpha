#!/usr/bin/env python
"""Capture F6 game states at every turn boundary from Prismata's replay viewer.

Usage:
    1. Open Prismata client (developer-mode SWF patch required)
    2. Load a replay in the replay viewer
    3. Rewind to the beginning (Home key or drag slider)
    4. Run this script:
       python tools/capture_replay_states.py --output f6_ground_truth.json

The tool automates: F6 (capture state) -> Shift+Right (step turn) -> repeat.
It detects end-of-replay when numTurns stops increasing.

Requires: Windows, ctypes (no external deps).
Does NOT require the sniffer proxy.
"""

import argparse
import ctypes
import hashlib
import json
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

_VK_F6 = 0x75
_VK_SHIFT = 0x10
_VK_RIGHT = 0x27
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002


# ---------------------------------------------------------------------------
# Win32 structures for SendInput
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Win32 helpers
# ---------------------------------------------------------------------------

def _find_prismata_hwnd():
    """Find the Prismata window handle by title substring."""
    found = []

    def _cb(hwnd, _lparam):  # noqa: unused callback param required by EnumWindows
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        if "Prismata" in buf.value and buf.value != "Prismata Sniffer":
            found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found[0] if found else None


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


# ---------------------------------------------------------------------------
# Keystroke helpers
# ---------------------------------------------------------------------------

def _send_keystroke(vk_code):
    """Send a single key press/release to Prismata, briefly stealing focus.

    Returns True on success, False if Prismata window not found.
    """
    hwnd = _find_prismata_hwnd()
    if not hwnd:
        _log("Prismata window not found")
        return False

    user32 = ctypes.windll.user32
    prev_hwnd = user32.GetForegroundWindow()

    if not user32.SetForegroundWindow(hwnd):
        _log("Cannot steal focus")
        return False
    time.sleep(0.05)

    inputs = (_INPUT * 2)(
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=vk_code, dwFlags=0)),
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=vk_code, dwFlags=_KEYEVENTF_KEYUP)),
    )
    user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))
    time.sleep(0.05)

    if prev_hwnd and prev_hwnd != hwnd:
        user32.SetForegroundWindow(prev_hwnd)

    return True


def _send_shift_right():
    """Send Shift+Right Arrow to step to the next turn in the replay viewer.

    Uses 4 INPUT structs: Shift down, Right down, Right up, Shift up.
    Returns True on success, False if Prismata window not found.
    """
    hwnd = _find_prismata_hwnd()
    if not hwnd:
        _log("Prismata window not found")
        return False

    user32 = ctypes.windll.user32
    prev_hwnd = user32.GetForegroundWindow()

    if not user32.SetForegroundWindow(hwnd):
        _log("Cannot steal focus")
        return False
    time.sleep(0.05)

    inputs = (_INPUT * 4)(
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_SHIFT, dwFlags=0)),
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_RIGHT, dwFlags=0)),
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_RIGHT, dwFlags=_KEYEVENTF_KEYUP)),
        _INPUT(type=_INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=_VK_SHIFT, dwFlags=_KEYEVENTF_KEYUP)),
    )
    user32.SendInput(4, inputs, ctypes.sizeof(_INPUT))
    time.sleep(0.05)

    if prev_hwnd and prev_hwnd != hwnd:
        user32.SetForegroundWindow(prev_hwnd)

    return True


# ---------------------------------------------------------------------------
# F6 capture with hash-and-wait
# ---------------------------------------------------------------------------

def _clipboard_hash():
    """Return a hash of the current clipboard text for change detection."""
    text = _read_clipboard_win32()
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _capture_f6_state(timeout=2.0):
    """Send F6 and wait for clipboard to change to a gamestate.

    Snapshots clipboard before F6, then polls every 100ms for up to
    `timeout` seconds until the clipboard changes AND looks like gamestate.

    Returns parsed dict on success, None on failure.
    """
    before_hash = _clipboard_hash()

    if not _send_keystroke(_VK_F6):
        return None

    deadline = time.monotonic() + timeout
    poll_interval = 0.1

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        text = _read_clipboard_win32()
        current_hash = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
        if current_hash != before_hash and _looks_like_gamestate(text):
            sanitized = _sanitize_gamestate(text)
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                _log("F6 clipboard changed but JSON parse failed")
                return None

    return None


def _extract_turn_number(data):
    """Extract numTurns from F6 JSON. Returns -1 if not found."""
    inner = data.get("CurrentInfo", data)
    gs = inner.get("gameState", inner)
    return gs.get("numTurns", -1)


def _extract_active_player(data):
    """Extract active player (0 or 1) from F6 JSON. Returns -1 if not found."""
    inner = data.get("CurrentInfo", data)
    gs = inner.get("gameState", inner)
    return gs.get("turn", -1)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg):
    """Print a progress message to stderr."""
    print(f"  [capture] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------

def capture_replay(max_turns=200, delay_between_turns=0.3):
    """Capture F6 game states from the currently loaded replay.

    Steps:
      1. Capture initial state (F6 without stepping)
      2. Loop: Shift+Right to step, then F6 to capture
      3. Stop when numTurns doesn't increase (end of replay)
      4. Stop after 3 consecutive capture failures

    Returns list of state dicts suitable for the output JSON.
    """
    states = []
    consecutive_failures = 0
    max_consecutive_failures = 3
    last_turn_number = -999  # sentinel

    # -- Capture initial state --
    _log("Capturing initial state (F6)...")
    data = _capture_f6_state(timeout=3.0)
    if data is None:
        _log("FAILED to capture initial state. Is Prismata open with a replay loaded?")
        _log("Make sure developer mode is enabled (SWF patched) and a replay is showing.")
        return states

    turn_num = _extract_turn_number(data)
    _log(f"Initial state captured: numTurns={turn_num}")
    states.append({
        "turn": -1,
        "label": "initial",
        "f6_json": data,
    })
    last_turn_number = turn_num

    # -- Step through turns --
    for step in range(1, max_turns + 1):
        # Step to next turn
        if not _send_shift_right():
            _log("Cannot send Shift+Right -- stopping")
            break

        time.sleep(delay_between_turns)

        # Capture state
        data = _capture_f6_state(timeout=2.0)
        if data is None:
            consecutive_failures += 1
            _log(f"Turn step {step}: capture FAILED ({consecutive_failures}/{max_consecutive_failures})")
            if consecutive_failures >= max_consecutive_failures:
                _log(f"Stopping after {max_consecutive_failures} consecutive failures")
                break
            continue

        consecutive_failures = 0
        turn_num = _extract_turn_number(data)
        player = _extract_active_player(data)

        # Detect end of replay: numTurns didn't increase
        if turn_num <= last_turn_number:
            _log(f"Turn step {step}: numTurns={turn_num} (unchanged) -- end of replay")
            break

        _log(f"Turn step {step}: numTurns={turn_num}, player={player}")
        states.append({
            "turn": turn_num,
            "player": player,
            "f6_json": data,
        })
        last_turn_number = turn_num

    return states


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Capture F6 game states from Prismata replay viewer at every turn boundary."
    )
    parser.add_argument(
        "--output", "-o",
        default="f6_ground_truth.json",
        help="Output JSON file (default: f6_ground_truth.json)",
    )
    parser.add_argument(
        "--max-turns", "-n",
        type=int,
        default=200,
        help="Maximum turns to capture (default: 200)",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.3,
        help="Delay between turns in seconds (default: 0.3)",
    )
    args = parser.parse_args()

    _log("Prismata Replay State Capture Tool")
    _log("-----------------------------------")
    _log("Prerequisites:")
    _log("  - Prismata client open with developer-mode SWF patch")
    _log("  - Replay loaded and rewound to start (Home key)")
    _log("")

    # Check that Prismata is running
    hwnd = _find_prismata_hwnd()
    if not hwnd:
        _log("ERROR: Prismata window not found. Please open Prismata first.")
        sys.exit(1)
    _log(f"Found Prismata window (hwnd=0x{hwnd:X})")

    _log(f"Starting capture (max_turns={args.max_turns}, delay={args.delay}s)...")
    _log("")

    states = capture_replay(
        max_turns=args.max_turns,
        delay_between_turns=args.delay,
    )

    if not states:
        _log("No states captured. Exiting.")
        sys.exit(1)

    # Build output
    output = {
        "capture_time": datetime.now().isoformat(timespec="seconds"),
        "total_turns": len(states),
        "states": states,
    }

    # Write output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    _log("")
    _log(f"Captured {len(states)} states (including initial)")
    _log(f"Output written to: {args.output}")

    # Summary of turn range
    turn_numbers = [s["turn"] for s in states if s["turn"] >= 0]
    if turn_numbers:
        _log(f"Turn range: {min(turn_numbers)} to {max(turn_numbers)}")


if __name__ == "__main__":
    main()
