"""
Prismata Neural Eval Overlay

Monitors clipboard for game state JSON (F6 in Prismata), invokes
bin/Prismata_Testing.exe --suggest, and displays eval + recommendations
as a transparent always-on-top tkinter overlay.

Usage:
    python tools/prismata_advisor.py
    python tools/prismata_advisor.py --think-time 5000

Controls:
    F6 in Prismata  - Copy game state to clipboard (triggers analysis)
    Ctrl+D          - Toggle drag mode (reposition overlay)
    Escape          - Quit overlay
"""

import collections
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk

# ---------------------------------------------------------------------------
# Paths (resolved relative to this script)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_BIN_DIR = os.path.join(_PROJECT_ROOT, "bin")
_EXE_PATH = os.path.join(_BIN_DIR, "Prismata_Testing.exe")
_CONFIG_DIR = os.path.join(_BIN_DIR, "asset", "config")

REQUIRED_FILES = [
    _EXE_PATH,
    os.path.join(_CONFIG_DIR, "cardLibrary.jso"),
    os.path.join(_CONFIG_DIR, "neural_weights.bin"),
    os.path.join(_CONFIG_DIR, "config.txt"),
]

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
TRANSPARENT_COLOR = "#000001"
POLL_INTERVAL_MS = 500
EXE_TIMEOUT_S = 15
DEFAULT_THINK_MS = 3000

FONT_EVAL = ("Arial", 28, "bold")
FONT_BUY = ("Arial", 22, "bold")
FONT_DETAIL = ("Arial", 18, "bold")
FONT_STATUS = ("Arial", 14, "bold")

COLOR_WIN = "#00ff44"
COLOR_LOSE = "#ff4444"
COLOR_EVEN = "#ffee00"
COLOR_BUY = "#ffffff"
COLOR_USE = "#00ddff"
COLOR_DEF = "#4488ff"
COLOR_STATUS = "#aaaaaa"
SHADOW_COLOR = "#111111"

# Win32 constants for click-through
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020


# ============================================================
# Health check (pre-GUI)
# ============================================================

class HealthChecker:
    @staticmethod
    def run():
        missing = [f for f in REQUIRED_FILES if not os.path.isfile(f)]
        if missing:
            print("ERROR: Prismata Advisor cannot start. Missing files:")
            for f in missing:
                print(f"  {f}")
            print("\nBuild Prismata_Testing.exe (Release|x86) and ensure bin/asset/config/ is populated.")
            raise SystemExit(1)
        print("Health check passed. Starting overlay...")


# ============================================================
# Overlay window (all tkinter + Win32 ctypes)
# ============================================================

class OverlayWindow:
    def __init__(self, root):
        self._root = root
        self._drag_mode = False
        self._drag_start = (0, 0)
        self._hwnd = None
        self._labels = {}
        self._shadows = {}

        self._setup_window()
        self._create_labels()
        self._bind_keys()

    def _setup_window(self):
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self._root.configure(bg=TRANSPARENT_COLOR)
        self._root.geometry("440x200+520+180")

    def _create_labels(self):
        rows = [
            ("eval", FONT_EVAL, COLOR_WIN),
            ("buy", FONT_BUY, COLOR_BUY),
            ("use", FONT_DETAIL, COLOR_USE),
            ("def", FONT_DETAIL, COLOR_DEF),
            ("status", FONT_STATUS, COLOR_STATUS),
        ]
        y = 4
        for name, font, color in rows:
            # Shadow label (1px offset)
            shadow = tk.Label(self._root, text="", font=font, fg=SHADOW_COLOR,
                              bg=TRANSPARENT_COLOR, anchor="w")
            shadow.place(x=9, y=y + 1)
            self._shadows[name] = shadow
            # Foreground label
            lbl = tk.Label(self._root, text="", font=font, fg=color,
                           bg=TRANSPARENT_COLOR, anchor="w")
            lbl.place(x=8, y=y)
            self._labels[name] = lbl
            y += font[1] + 8  # font size + padding

    def _bind_keys(self):
        self._root.bind("<Escape>", lambda _: self._root.destroy())
        self._root.bind("<Control-d>", lambda _: self._toggle_drag_mode())
        self._root.bind("<ButtonPress-1>", self._on_drag_start)
        self._root.bind("<B1-Motion>", self._on_drag_motion)

    # -- Win32 click-through --

    def _get_hwnd(self):
        if self._hwnd is None:
            wid = self._root.winfo_id()
            self._hwnd = ctypes.windll.user32.GetParent(wid)
            if not self._hwnd:
                self._hwnd = wid
        return self._hwnd

    def set_click_through(self, enabled):
        hwnd = self._get_hwnd()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if enabled:
            style |= (_WS_EX_LAYERED | _WS_EX_TRANSPARENT)
        else:
            style &= ~_WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)

    # -- Drag mode --

    def _toggle_drag_mode(self):
        self._drag_mode = not self._drag_mode
        self.set_click_through(not self._drag_mode)
        if self._drag_mode:
            self._set_label("status", "[DRAG MODE - Ctrl+D to lock]", COLOR_STATUS)
        else:
            self._set_label("status", "", COLOR_STATUS)

    def _on_drag_start(self, event):
        if self._drag_mode:
            self._drag_start = (event.x_root - self._root.winfo_x(),
                                event.y_root - self._root.winfo_y())

    def _on_drag_motion(self, event):
        if self._drag_mode:
            x = event.x_root - self._drag_start[0]
            y = event.y_root - self._drag_start[1]
            self._root.geometry(f"+{x}+{y}")

    # -- Display API --

    def _set_label(self, name, text, color=None):
        self._labels[name].config(text=text)
        self._shadows[name].config(text=text)
        if color:
            self._labels[name].config(fg=color)

    def show_analyzing(self):
        self._set_label("eval", "ANALYZING...", COLOR_EVEN)
        self._set_label("buy", "")
        self._set_label("use", "")
        self._set_label("def", "")
        self._set_label("status", "")

    def show_error(self, msg):
        short = msg[:60] + ("..." if len(msg) > 60 else "")
        self._set_label("eval", "ERROR", COLOR_LOSE)
        self._set_label("buy", "")
        self._set_label("use", "")
        self._set_label("def", "")
        self._set_label("status", short, COLOR_STATUS)

    def update_result(self, data, prev_eval_pct):
        eval_raw = data.get("eval", 0.0)
        eval_pct = (eval_raw + 1.0) / 2.0 * 100.0

        color = (COLOR_WIN if eval_pct > 55 else
                 COLOR_LOSE if eval_pct < 45 else
                 COLOR_EVEN)

        arrow = ""
        if prev_eval_pct is not None:  # Explicit None check: 0.0 is valid
            if eval_pct > prev_eval_pct + 1:
                arrow = " ^"
            elif eval_pct < prev_eval_pct - 1:
                arrow = " v"

        self._set_label("eval", f"EVAL: {eval_pct:.0f}%{arrow}", color)

        # Group buys: ["Tarsier", "Tarsier", "Husk"] -> "Tarsier x2, Husk"
        buy_text = format_buy_list(data.get("buy", []))
        self._set_label("buy", f"BUY: {buy_text}" if buy_text else "BUY: (pass)", COLOR_BUY)

        abilities = data.get("abilities", [])
        self._set_label("use", f"USE: {', '.join(abilities)}" if abilities else "", COLOR_USE)

        phase = data.get("phase", "action")
        defense = data.get("defense", [])
        if phase == "defense" and defense:
            self._set_label("def", f"DEF: {', '.join(defense)}", COLOR_DEF)
        else:
            self._set_label("def", "")

        think = data.get("think_ms", "?")
        mode = "[DRAG]" if self._drag_mode else "[click-through]"
        player_num = data.get('active_player', -1) + 1  # 0-indexed -> 1-indexed
        self._set_label("status", f"think: {think}ms | P{player_num} | {mode}",
                        COLOR_STATUS)

        return eval_pct


# ============================================================
# Analysis engine (clipboard + subprocess)
# ============================================================

class AnalysisEngine:
    def __init__(self, root, think_ms, on_analyzing, on_result, on_error):
        self._root = root
        self._think_ms = think_ms
        self._on_analyzing = on_analyzing
        self._on_result = on_result
        self._on_error = on_error
        self._last_hash = ""
        self._seq = 0
        self._lock = threading.Lock()

    def start_polling(self):
        self._poll()

    def _poll(self):
        try:
            content = self._root.clipboard_get()
        except tk.TclError:
            content = ""

        content_hash = _hash_text(content)
        if content_hash != self._last_hash and _looks_like_gamestate(content):
            self._last_hash = content_hash
            self._dispatch(content)

        self._root.after(POLL_INTERVAL_MS, self._poll)

    def _dispatch(self, json_str):
        json_str = _sanitize_gamestate(json_str)
        with self._lock:
            self._seq += 1
            seq = self._seq
        self._on_analyzing()
        t = threading.Thread(target=self._run_analysis,
                             args=(json_str, seq), daemon=True)
        t.start()

    def _run_analysis(self, json_str, seq):
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".json", dir=_BIN_DIR,
                                             prefix="_advisor_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json_str)

            cmd = [
                _EXE_PATH,
                "--suggest", temp_path,
                "--player", "PrismatAI_AB",
                "--think-time", str(self._think_ms),
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
                proc.communicate()  # drain pipes
                raise

            # Debounce check
            with self._lock:
                if seq != self._seq:
                    return

            # Parse last line of stdout (resilient to any pre-JSON noise)
            stdout_text = stdout_text.strip()
            if not stdout_text:
                raise ValueError(
                    f"Exe produced no output (exit={proc.returncode})")

            json_line = stdout_text.split("\n")[-1].strip()
            data = json.loads(json_line)

            if data.get("ok"):
                self._root.after(0, self._on_result, data)
            else:
                err = data.get("error", "Unknown error from exe")
                self._root.after(0, self._on_error, err)

        except subprocess.TimeoutExpired:
            self._root.after(0, self._on_error,
                             f"Exe timed out after {EXE_TIMEOUT_S}s")
        except json.JSONDecodeError as e:
            self._root.after(0, self._on_error,
                             f"Invalid JSON from exe: {e}")
        except Exception as e:
            self._root.after(0, self._on_error, str(e))
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass


# ============================================================
# Coordinator
# ============================================================

class PrismataAdvisor:
    def __init__(self, think_ms=DEFAULT_THINK_MS):
        self._last_eval_pct = None

        self._root = tk.Tk()
        self._root.title("Prismata Advisor")
        self._window = OverlayWindow(self._root)

        self._engine = AnalysisEngine(
            root=self._root,
            think_ms=think_ms,
            on_analyzing=self._on_analyzing,
            on_result=self._on_result,
            on_error=self._on_error,
        )

        # Delay click-through until HWND is available
        self._root.after(100, self._apply_initial_click_through)
        self._window.show_analyzing()
        self._window._set_label("eval", "READY", COLOR_STATUS)
        self._window._set_label("status", "Press Shift+F6 in Prismata | Esc=quit | Ctrl+D=drag",
                                COLOR_STATUS)
        self._engine.start_polling()

    def _apply_initial_click_through(self):
        self._window.set_click_through(True)

    def _on_analyzing(self):
        self._window.show_analyzing()

    def _on_result(self, data):
        self._last_eval_pct = self._window.update_result(data, self._last_eval_pct)

    def _on_error(self, msg):
        self._window.show_error(msg)

    def run(self):
        self._root.mainloop()


# ============================================================
# Pure helpers
# ============================================================

def format_buy_list(buys):
    if not buys:
        return ""
    counts = collections.Counter(buys)
    parts = [f"{name} x{counts[name]}" if counts[name] > 1 else name
             for name in dict.fromkeys(buys)]
    return ", ".join(parts)


def _hash_text(text):
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _looks_like_gamestate(text):
    if len(text) < 50:
        return False
    return ('"CurrentInfo"' in text or '"gameState"' in text) and '"mergedDeck"' in text


def _sanitize_gamestate(text):
    """Convert F6 clipboard format to valid JSON for the C++ --suggest parser.

    F6 produces:   "CurrentInfo" : { ... }\n"TurnStartInfo" : { ... }\nAI Status Log...
    Shift+F6 produces: { "mergedDeck": ..., "gameState": ..., "aiParameters": ... }

    The C++ parser handles both { "CurrentInfo": {...} } and bare { gameState }
    formats, but F6 isn't valid JSON because sections are concatenated.
    Fix: extract the first top-level JSON object (the CurrentInfo block).
    """
    text = text.strip()

    # Shift+F6 format: already valid JSON starting with {
    if text.startswith("{"):
        return text

    # F6 format: starts with "CurrentInfo" : { ... }
    # Find the opening brace and brace-match to find the end of that object
    brace_start = text.find("{")
    if brace_start == -1:
        return text  # not JSON at all, let the exe report the error

    # Brace-match to find the complete JSON object
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
                # Found the complete first JSON object, wrap with CurrentInfo key
                inner_json = text[brace_start:i + 1]
                return '{ "CurrentInfo" : ' + inner_json + ' }'

    return text  # unbalanced braces, pass through as-is


# ============================================================
# Entry point
# ============================================================

def main():
    think_ms = DEFAULT_THINK_MS
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--think-time" and i < len(sys.argv) - 1:
            try:
                think_ms = int(sys.argv[i + 1])
            except ValueError:
                print(f"WARNING: Invalid --think-time value, using {DEFAULT_THINK_MS}ms")

    HealthChecker.run()
    advisor = PrismataAdvisor(think_ms=think_ms)
    advisor.run()


if __name__ == "__main__":
    main()
