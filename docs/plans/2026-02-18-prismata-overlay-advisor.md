# Prismata Neural Eval Overlay — Implementation Plan

**Date:** 2026-02-18
**Branch:** `feature/watcher-enhancements-v2`
**Status:** COMPLETE (Feb 18, 2026) — C++ --suggest mode, Python overlay, launcher bat all implemented and tested
**Context doc:** `docs/plans/2026-02-18-overlay-context.md`

## Goal

An always-on-top transparent overlay that shows neural eval scores and AI move recommendations while playing Prismata against the masterbot. The overlay reads game state from the clipboard (triggered by a hotkey in Prismata), runs our AI (PrismatAlpha_AB with E2b neural eval), and displays results as bright bold text on a fully transparent window — similar to the pink debug numbers in our GUI.

## Architecture

```
Prismata Client (play game, press F6 to copy state)
        | clipboard (JSON)
        v
Python Overlay Tool (tools/prismata_advisor.py)
        | writes JSON to temp file
        v
C++ Engine (bin/Prismata_Testing.exe --suggest state.json)
        | stdout JSON
        v
Python Overlay Tool (parses, displays)
        |
        v
Transparent overlay window (tkinter, always-on-top, bold text)
```

## Part 1: C++ `--suggest` CLI Mode

**File: `source/testing/main.cpp`** — add new `--suggest <state_file>` command

### What it does:
1. Read JSON game state from the file argument
2. Parse via `GameState::initFromJSON()` (already works — `source/engine/GameState.cpp:17`)
3. Run neural eval: `NeuralNet::Instance().evaluate(state)` -> value score
4. Run AI move: `AIParameters::Instance().getPlayer(activePlayer, "PrismatAlpha_AB")` -> `player->getMove(state, move)`
5. Extract buy actions: filter `ActionTypes::BUY`, convert via `CardType(action.getID()).getUIName()` (pattern from `source/testing/TournamentGame.cpp:57-60`)
6. Extract defense, ability, breach actions similarly
7. Output as JSON to stdout

### JSON input format (from Prismata F6 clipboard — VERIFIED Feb 18):

**Note:** F6 output has a `"CurrentInfo"` wrapper key. The `--suggest` parser must handle this.

```json
{
  "CurrentInfo": {
    "mergedDeck": [
      {"name": "Tarsier", "UIName": "Tarsier", "buyCost": "4C", "toughness": 1,
       "rarity": "normal", "buildTime": 2, "defaultBlocking": 0,
       "beginOwnTurnScript": {"receive": "A"}, "score": "5C", "baseSet": 1},
      ...
    ],
    "gameState": {
      "phase": "action",
      "turn": 0,
      "numTurns": 5,
      "whiteMana": "0",
      "blackMana": "0",
      "glassBroken": false,
      "result": 2,
      "cards": ["Tarsier", "Asteri Cannon", "Drake", ...],
      "table": [
        {"cardName": "Drone", "owner": 0, "instId": 0, "health": 1,
         "constructionTime": 0, "role": "assigned", "blocking": false,
         "lifespan": -1, "dead": false, "charge": 0, ...},
        ...
      ],
      "whiteTotalSupply": [10, 4, 4, 10, 21, ...],
      "blackTotalSupply": [10, 4, 4, 10, 20, ...],
      "whiteSupplySpent": [0, 0, 0, 0, 6, ...],
      "blackSupplySpent": [0, 0, 0, 0, 4, ...]
    },
    "aiParameters": { ... }
  }
}
```

**Key differences from original plan estimate:**
- Wrapper key is `"CurrentInfo"`, not bare top-level
- Card names use **display names** (e.g., "Tarsier"), not internal names (e.g., "Tesla Tower")
- Table entries use `cardName` (not `type`), `owner` (not `player`), per-instance fields (not aggregated)
- Each table entry is a full card instance with `instId`, `constructionTime`, `role`, `blocking`, `health`, `damage`, `charge`, `lifespan`, `dead`/`deadness`, `sniperId`, `disruptDamage`, etc.
- Supply arrays are parallel to the `cards` array (index 0 = first card in set)
- Mana is a string like `"6GBBBB"` or `"0"` (not structured)
- `result: 2` means game in progress (not finished)
- `aiParameters` contains the FULL masterbot AI config (move iterators, partial players, opening books, buy limits, player definitions) — could be used to replicate the masterbot's strategy

### F6 JSON Compatibility (verified against C++ source, Feb 18):

| Aspect | Status | Details |
|--------|--------|---------|
| Display names (e.g. "Tarsier") | **FULLY COMPATIBLE** | `CardTypes::GetCardType()` checks both `getName()` (internal) and `getUIName()` (display) — dual lookup at `CardTypes.cpp:74-87` |
| `mergedDeck` field | **REQUIRES SPECIAL INIT** | Must call `Prismata::InitFromMergedDeckJSON(mergedDeck)` separately before creating GameState. See `Prismata.cpp:23-31`, `CardTypeData.cpp:117-122`. |
| `gameState.cards` string array | **FULLY COMPATIBLE** | Parsed at `GameState.cpp:111-119`, resolved via `GetCardType()` |
| `gameState.table[].cardName` | **FULLY COMPATIBLE** | Parsed at `Card.cpp:20-29`, resolved via `GetCardType()` |
| `CurrentInfo` wrapper | **NOT HANDLED** | `initFromJSON()` expects the raw gameState object. Caller must unwrap: `doc["CurrentInfo"]["gameState"]` |
| Mana format (`"6GBBBB"`) | **COMPATIBLE** | Same format the engine uses internally |
| Supply arrays | **COMPATIBLE** | Parallel to `cards` array; parsed at `GameState.cpp:152-165` |

**Bottom line:** No translation layer needed. The `--suggest` parser must: (1) unwrap `CurrentInfo`, (2) call `InitFromMergedDeckJSON` with the `mergedDeck` array, (3) pass the `gameState` sub-object to `GameState::initFromJSON()`.

### JSON output format:

Use `RapidJSON::Writer` (not printf) to ensure proper JSON escaping. **All non-JSON output (logs, warnings) goes to stderr.** Stdout must contain exactly one JSON line and nothing else.

```json
{
  "ok": true,
  "eval": 0.34,
  "eval_pct": "67%",
  "active_player": 0,
  "phase": "action",
  "buy": ["Tarsier", "Tarsier", "Husk"],
  "abilities": ["Blastforge"],
  "defense": ["Wall blocks"],
  "breach": [],
  "think_ms": 1200,
  "timing_ms": {"parse": 5, "eval": 12, "search": 1183},
  "full_move": "Player 0 Uses Ability of Card 3\nPlayer 0 Buys Card 5\n..."
}
```

**On error:**
```json
{"ok": false, "error": "Failed to parse game state: missing 'cards' field"}
```

**Eval value semantics:** `eval` is the raw `NeuralOutput::value` in range [-1, +1] where +1 = certain win for active player. The Python overlay converts to percentage: `eval_pct = (eval + 1) / 2 * 100`. Example: `eval: 0.34` → `eval_pct: "67%"` (active player has 67% estimated win probability).

### Key implementation details:
- **mergedDeck initialization**: Must call `Prismata::InitFromMergedDeckJSON(mergedDeck)` to register the game's card set before parsing the gameState. Without this, `GetCardType()` may not find the cards.
- **CurrentInfo unwrap**: F6 clipboard wraps everything in `"CurrentInfo"`. The parser checks for this and unwraps before calling `initFromJSON()`.
- **Display names work natively**: `CardTypes::GetCardType()` checks both `getName()` and `getUIName()` — no translation layer needed.
- The `--suggest` mode needs a player name arg too: `--suggest state.json --player PrismatAlpha_AB`
- Think time: use 3 seconds (configurable via `--think-time 3000`)
- **Stdout is JSON-only**: Use `RapidJSON::Writer<StringBuffer>` for output. All logging/warnings go to stderr. This prevents the Python overlay from choking on mixed stdout.
- **`full_move` must be JSON-escaped**: Newlines in the move string must be `\n` in JSON, not raw newlines. RapidJSON Writer handles this automatically.
- **Error handling**: On any exception/failure, output `{"ok": false, "error": "..."}` to stdout and exit with code 1. Never output partial/broken JSON.
- Exit immediately after (no tournament loop)

### Files to modify:
| File | Change |
|------|--------|
| `source/testing/main.cpp` | Add `--suggest` CLI handler (~50 lines) |
| `source/testing/Benchmarks.h` | Add `DoSuggestMove()` declaration |
| `source/testing/Benchmarks.cpp` | Add `DoSuggestMove()` implementation (~80 lines) |

### `DoSuggestMove()` pseudocode:
```cpp
void Benchmarks::DoSuggestMove(const std::string& stateFile,
                                const std::string& playerName,
                                int thinkTimeMs)
{
    try {
        // 1. Read and parse JSON file
        std::ifstream f(stateFile);
        std::string json((std::istreambuf_iterator<char>(f)), ...);
        rapidjson::Document doc;
        doc.Parse(json.c_str());
        if (doc.HasParseError()) { outputError("JSON parse error"); return; }

        // 2. Unwrap CurrentInfo wrapper (F6 clipboard format)
        const auto& root = doc.HasMember("CurrentInfo")
            ? doc["CurrentInfo"] : doc;

        // 3. Initialize mergedDeck card set (REQUIRED before GameState parsing)
        if (root.HasMember("mergedDeck")) {
            Prismata::InitFromMergedDeckJSON(root["mergedDeck"]);
        }

        // 4. Extract and build GameState
        const auto& stateVal = root.HasMember("gameState")
            ? root["gameState"] : root;
        Timer parseTimer; parseTimer.start();
        GameState state(stateVal);
        double parseMs = parseTimer.getElapsedTimeInMilliSec();

        // 5. Neural eval
        Timer evalTimer; evalTimer.start();
        auto evalOutput = NeuralNet::Instance().evaluate(state);
        double evalMs = evalTimer.getElapsedTimeInMilliSec();

        // 6. Get AI move
        Timer searchTimer; searchTimer.start();
        PlayerPtr player = AIParameters::Instance().getPlayer(
            state.getActivePlayer(), playerName);
        Move move;
        player->getMove(state, move);
        double searchMs = searchTimer.getElapsedTimeInMilliSec();

        // 7. Categorize actions by type
        //    Note: action.getID() semantics vary by ActionType:
        //    - BUY: getID() = CardType index → use CardType(id).getUIName()
        //    - USE_ABILITY: getID() = card instance index in GameState
        //    - ASSIGN_BLOCKER: getID() = card instance index
        //    - SNIPE/CHILL: getID() = source, getTargetID() = target
        std::vector<std::string> buys, abilities, defense, breach;
        for (size_t i = 0; i < move.size(); i++) {
            const Action& a = move.getAction(i);
            switch (a.getType()) {
                case ActionTypes::BUY:
                    buys.push_back(CardType(a.getID()).getUIName());
                    break;
                case ActionTypes::USE_ABILITY:
                    abilities.push_back(state.getCardByID(a.getID()).getType().getUIName());
                    break;
                case ActionTypes::ASSIGN_BLOCKER:
                    defense.push_back(state.getCardByID(a.getID()).getType().getUIName());
                    break;
                // ... SNIPE, CHILL, ASSIGN_BREACH, etc.
            }
        }

        // 8. Build JSON output with RapidJSON Writer (ensures proper escaping)
        rapidjson::StringBuffer sb;
        rapidjson::Writer<rapidjson::StringBuffer> w(sb);
        w.StartObject();
        w.Key("ok"); w.Bool(true);
        w.Key("eval"); w.Double(evalOutput.value);  // [-1, +1]
        w.Key("active_player"); w.Int(state.getActivePlayer());
        w.Key("phase"); w.String(/* phase string */);
        w.Key("buy"); w.StartArray(); for (auto& b : buys) w.String(b); w.EndArray();
        w.Key("abilities"); w.StartArray(); for (auto& a : abilities) w.String(a); w.EndArray();
        w.Key("defense"); w.StartArray(); for (auto& d : defense) w.String(d); w.EndArray();
        w.Key("breach"); w.StartArray(); for (auto& b : breach) w.String(b); w.EndArray();
        w.Key("think_ms"); w.Int((int)searchMs);
        w.Key("timing_ms"); w.StartObject();
            w.Key("parse"); w.Int((int)parseMs);
            w.Key("eval"); w.Int((int)evalMs);
            w.Key("search"); w.Int((int)searchMs);
        w.EndObject();
        w.Key("full_move"); w.String(move.toString());  // Writer auto-escapes \n
        w.EndObject();
        fprintf(stdout, "%s\n", sb.GetString());

    } catch (const std::exception& e) {
        outputError(e.what());  // {"ok": false, "error": "..."}
    }
}

// Helper for error output
void outputError(const std::string& msg) {
    rapidjson::StringBuffer sb;
    rapidjson::Writer<rapidjson::StringBuffer> w(sb);
    w.StartObject();
    w.Key("ok"); w.Bool(false);
    w.Key("error"); w.String(msg);
    w.EndObject();
    fprintf(stdout, "%s\n", sb.GetString());
}
```

## Part 2: Python Overlay Tool

**New file: `tools/prismata_advisor.py`** (~200-300 lines)

### Features:
1. **Clipboard monitor** — polls every 500ms for new JSON game state, with `try/except TclError` safety
2. **Async C++ exe invocation** — runs `Prismata_Testing.exe --suggest` in a background thread (does not block tkinter main loop)
3. **Transparent overlay** — tkinter window, `#000001` transparent background, bright bold text with drop shadow
4. **Always-on-top** — stays above Prismata window
5. **Two interaction modes** (toggle via Ctrl+D):
   - **Click-through mode** (default): overlay passes all mouse events through to the game (uses `ctypes` Win32 `WS_EX_LAYERED | WS_EX_TRANSPARENT`)
   - **Drag mode**: overlay captures mouse for repositioning, then reverts to click-through
6. **State deduplication** — hashes clipboard content, skips re-analysis if state unchanged
7. **"ANALYZING..." indicator** — shown immediately when new state detected, before C++ results arrive
8. **Phase-aware display** — hides irrelevant sections (e.g., no DEF line during action phase, no BUY during defense)
9. **Startup health check** — verifies exe, cardLibrary.jso, neural_weights.bin, config.txt exist before entering main loop
10. **Escape key** — quits the overlay (no title bar = no close button)
11. **Debounce** — if a new clipboard state arrives while analysis is running, cancels stale result and re-queues

### Overlay display (bright bold text with drop shadow, ~24-32pt):

Positioned in the right margin or as a detachable panel to avoid covering the board.
The Prismata layout has: left sidebar (card set), center (boards), right (attack/defense circles).

```
+---------------------------+
|  EVAL: 67% ^              |  <- Green/Red/Yellow, 28pt bold
|  BUY: Tarsier x2, Husk   |  <- White, 22pt bold
|  USE: Blastforge          |  <- Cyan, 18pt (abilities to click)
|  DEF: Wall (3hp)          |  <- Blue, 18pt (if defense phase)
+---------------------------+
   (fully transparent bg, just floating text)
```

- Green text when eval > 55% (our side winning), red when < 45%, yellow near 50%
- Arrow showing trend vs previous eval (use `self.last_eval is not None` — not bare truthiness, since 0.0 is a valid eval)
- Buy list shows unit display names with grouped counts (e.g. "Tarsier x2" not "Tarsier, Tarsier") — use `collections.Counter`
- Abilities and defense shown only when relevant to the current phase
- Text has 1px dark drop shadow for readability against varied game backgrounds
- Draggable via Ctrl+D toggle; click-through by default so game keeps focus

### Dependencies:
- `tkinter` (built-in Python)
- `subprocess`, `threading`, `hashlib`, `tempfile`, `collections`, `ctypes` (all built-in)
- `json` (built-in)
- No external packages needed

### Click-through implementation (Windows):
```python
import ctypes
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20

def set_click_through(hwnd, enabled):
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enabled:
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
```

### Implementation structure:
```python
import tkinter as tk
import subprocess, threading, json, hashlib, tempfile, os, collections, ctypes

EXE_PATH = os.path.abspath('bin/Prismata_Testing.exe')
BIN_DIR = os.path.abspath('bin')
REQUIRED_FILES = [EXE_PATH,
    os.path.join(BIN_DIR, 'asset/config/cardLibrary.jso'),
    os.path.join(BIN_DIR, 'asset/config/neural_weights.bin'),
    os.path.join(BIN_DIR, 'asset/config/config.txt')]
TRANSPARENT_COLOR = '#000001'

class PrismataAdvisor:
    def __init__(self):
        self.startup_health_check()
        self.root = tk.Tk()
        self.setup_overlay()
        self.last_clipboard_hash = ""
        self.last_eval = None
        self.analyzing = False
        self.analysis_seq = 0       # For debouncing stale results
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        self.root.bind('<Control-d>', self.toggle_drag_mode)
        self.poll_clipboard()

    def startup_health_check(self):
        missing = [f for f in REQUIRED_FILES if not os.path.isfile(f)]
        if missing:
            raise FileNotFoundError(f"Missing: {', '.join(missing)}")

    def setup_overlay(self):
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', TRANSPARENT_COLOR)
        self.root.configure(bg=TRANSPARENT_COLOR)
        # Labels with drop shadow (dark text behind, bright text on top)
        self.eval_label = tk.Label(..., fg='lime', bg=TRANSPARENT_COLOR,
                                    font=('Arial', 28, 'bold'))
        self.buy_label = tk.Label(..., fg='white', bg=TRANSPARENT_COLOR,
                                   font=('Arial', 22, 'bold'))
        self.ability_label = tk.Label(..., fg='cyan', bg=TRANSPARENT_COLOR,
                                      font=('Arial', 18, 'bold'))
        self.defense_label = tk.Label(..., fg='#4488ff', bg=TRANSPARENT_COLOR,
                                      font=('Arial', 18, 'bold'))
        # Enable click-through by default
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        set_click_through(hwnd, True)

    def poll_clipboard(self):
        try:
            content = self.root.clipboard_get()
        except tk.TclError:
            content = ""  # Clipboard empty or unavailable
        content_hash = hashlib.md5(content.encode('utf-8', errors='replace')).hexdigest()
        if content_hash != self.last_clipboard_hash and looks_like_gamestate(content):
            self.last_clipboard_hash = content_hash
            self.analyze_async(content)
        self.root.after(500, self.poll_clipboard)

    def analyze_async(self, json_str):
        """Run analysis in background thread to avoid blocking tkinter."""
        self.analysis_seq += 1
        seq = self.analysis_seq
        self.show_analyzing()  # Show "ANALYZING..." immediately
        thread = threading.Thread(target=self._run_analysis,
                                  args=(json_str, seq), daemon=True)
        thread.start()

    def _run_analysis(self, json_str, seq):
        """Background thread: write temp file, invoke C++ exe, parse result."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                              dir=BIN_DIR, delete=False) as f:
                f.write(json_str)
                temp_path = f.name
            result = subprocess.run(
                [EXE_PATH, '--suggest', temp_path,
                 '--player', 'PrismatAlpha_AB', '--think-time', '3000'],
                capture_output=True, text=True, cwd=BIN_DIR, timeout=10
            )
            os.unlink(temp_path)
            if seq != self.analysis_seq:
                return  # Stale result — newer analysis already queued
            data = json.loads(result.stdout)
            if data.get('ok', False):
                self.root.after(0, self.update_display, data)
            else:
                self.root.after(0, self.show_error, data.get('error', 'Unknown'))
        except subprocess.TimeoutExpired:
            os.unlink(temp_path)
            self.root.after(0, self.show_error, 'C++ exe timed out (10s)')
        except Exception as e:
            self.root.after(0, self.show_error, str(e))

    def show_analyzing(self):
        self.eval_label.config(text="ANALYZING...", fg='yellow')

    def update_display(self, data):
        eval_pct = (data['eval'] + 1) / 2 * 100  # [-1,1] -> [0,100]%
        color = 'lime' if eval_pct > 55 else 'red' if eval_pct < 45 else 'yellow'
        arrow = ''
        if self.last_eval is not None:  # Explicit None check (0.0 is valid)
            arrow = ' ^' if eval_pct > self.last_eval else ' v'
        self.eval_label.config(text=f"EVAL: {eval_pct:.0f}%{arrow}", fg=color)

        # Group buys with counts: ["Tarsier", "Tarsier", "Husk"] -> "Tarsier x2, Husk"
        counts = collections.Counter(data.get('buy', []))
        buy_parts = [f"{name} x{n}" if n > 1 else name for name, n in counts.items()]
        self.buy_label.config(text=f"BUY: {', '.join(buy_parts) or '(nothing)'}")

        # Phase-aware: show/hide sections based on current phase
        phase = data.get('phase', 'action')
        abilities = data.get('abilities', [])
        self.ability_label.config(text=f"USE: {', '.join(abilities)}" if abilities else "")
        defense = data.get('defense', [])
        if phase == 'defense' and defense:
            self.defense_label.config(text=f"DEF: {', '.join(defense)}")
        else:
            self.defense_label.config(text="")

        self.last_eval = eval_pct
```

### Launcher:
**New file: `run_advisor.bat`** — one-click launch
```bat
@echo off
cd /d c:\libraries\PrismataAI
python tools/prismata_advisor.py
```

### Fair play note:
This tool is for offline analysis and learning against the built-in masterbot. The Prismata multiplayer servers are no longer actively maintained, and this overlay is not intended for use against human opponents.

## Part 3: Clipboard Trigger from Prismata

### Developer Mode SWF Patch (DONE — Feb 18)

The clipboard hotkeys are gated behind `FlashBuildOptions.developerVersion` (set to `false` in production). We successfully patched the SWF to re-enable it:

**How it works:** The decompiled source (`prismata_decompiled/scripts/FlashBuildOptions.as`) shows `developerVersion` is declared as `true` (line 50) but overridden to `false` in a static initializer (line 119). In the compiled SWF bytecode, this is a single `pushfalse` (0x27) instruction before `setproperty developerVersion`.

**Patch details:**
- **File:** `C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf` (18.9 MB, CWS compressed)
- **Change:** Single byte in decompressed bytecode at offset `0x1580196`: `0x27` (pushfalse) → `0x26` (pushtrue)
- **Backup:** Original saved as `Prismata.swf.backup` in the same directory
- **Restore:** Copy backup over the SWF, or use Steam "Verify integrity of game files"
- **Context:** The bytecode sequence is `setproperty serverToConnectTo` / `findproperty developerVersion` / **`pushfalse`** / `setproperty developerVersion` / `findproperty hideUglyStuff` / `pushtrue` / `setproperty hideUglyStuff` — matching source lines 118-120

### Hotkey Mapping (from `prismata_decompiled/scripts/starlingUI/UIKeyboard.as:122-135`)

| Shortcut | Function | Output |
|----------|----------|--------|
| **F6** | `copyGamestateToClipboard` | Full game state JSON (mergedDeck, gameState, aiParameters, TurnStartInfo, AI Status Log) |
| **Shift+F6** | `copyGamestateToClipboardAI` | Compact JSON (mergedDeck, gameState, aiParameters, aiPlayerName only) |

Both call `Game.getAIDebugJsonString()` (`Game.as:1226-1239`) which constructs JSON and copies it to the system clipboard via `Clipboard.generalClipboard.setData()`.

**Event chain:** UIKeyboard dispatches `UIEvent.COPY_GAMESTATE_TO_CLIPBOARD` / `UIEvent.COPY_GAMESTATE_TO_CLIPBOARD_AI` → Game class listens for these (`Game.as:215-216`) → calls clipboard functions.

### Other Developer Hotkeys (now active)

Enabling `developerVersion` also unlocks other debug keybindings defined in `UIKeyboard.as`. These may include debug overlays, state inspection tools, etc. Worth exploring but not required for the overlay.

### Hosts File Redirect (DONE — Feb 18)

Enabling `developerVersion` disables load balancing (`useLoadBalancing` getter checks `!developerVersion`, line 129). The client then connects directly to `serverURL_amazonAlpha` (`<PRISMATA_SERVER_HOST>`) which is a dead server. Fix: hosts file entry redirecting the dead hostname to the live server IP:

```
<PRISMATA_SERVER_IP> <PRISMATA_SERVER_HOST>  # Prismata dev mode - redirect dead amazonAlpha to live server
```

Added via `tmp_restore_hosts.ps1` (requires UAC elevation). Safe — the old hostname is dead and not used by anything else.

### Status: CONFIRMED WORKING (Feb 18)

- SWF patch loads without issues (no signature check, Steam doesn't auto-revert)
- Hosts redirect connects the dev-mode client to the live server successfully
- F6 copies full game state JSON to clipboard during a live game vs Master Bot
- JSON contains `mergedDeck` (21 card defs), `gameState` (full board + supply + mana), and `aiParameters` (complete masterbot AI config)
- Top-level key is `"CurrentInfo"` (not just the gameState — plan's JSON input format section should account for this wrapper)

**If Steam overwrites the SWF** (e.g., after an update or "Verify integrity"), just re-run the patcher. The backup is at `Prismata.swf.backup`.

## Implementation Order

1. **C++ `--suggest` mode** (~80 lines in Benchmarks.cpp + 15 lines in main.cpp)
   - Parse `--suggest` flag in main.cpp
   - Implement `DoSuggestMove()` in Benchmarks.cpp
   - Test with a hand-crafted JSON state file
   - Build in Release|x86

2. **Python overlay** (~250 lines in tools/prismata_advisor.py)
   - Clipboard monitoring loop
   - C++ exe invocation
   - Transparent overlay window with bold text
   - Draggable positioning

3. **Integration test**
   - Copy a game state JSON to clipboard manually
   - Verify overlay picks it up, runs AI, displays result
   - Test with Prismata client if clipboard export hotkey is found

4. **Launcher script** (run_advisor.bat)

## Verification

1. **C++ unit test**: Create a test JSON file with a known game state, run `Prismata_Testing.exe --suggest test_state.json`, verify output contains valid eval and buy list
2. **Overlay test**: Copy test JSON to clipboard, verify overlay updates within 1-2s
3. **End-to-end**: Play a bot game in Prismata, trigger clipboard export, see eval + buy recommendations appear in overlay
4. **Performance**: Ensure total latency (clipboard detect + file write + exe startup + AI think + display) is under 5 seconds

## Confirmed Server Details (Feb 18, 2026)

- **Game server**: `<PRISMATA_SERVER_HOST>` → `<PRISMATA_SERVER_IP>`
- **Ports**: 11600 (plaintext AMF3 — game traffic), 11601 (TLS — auth/payment), 11619 (Flash policy)
- **Status**: Server DNS resolves and ports are reachable (confirmed Feb 18). Client connects successfully when hosts file is clean.
- **S3 replay API**: Still live — `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz`. Used daily by our self-play pipeline.
- **Offline mode**: Client has "Play in Airplane Mode" button on the login screen — can play bot games without server connection. Useful for overlay testing if server goes down.

## CRITICAL WARNING: Network Proxy Hosts File Lockout

**Incident (Feb 18):** The `prismata_sniffer.py` proxy adds `127.0.0.1 <PRISMATA_SERVER_HOST>` to the Windows hosts file. A previous Claude Code session added this entry and **never removed it**, locking the user out of the Prismata client for an unknown duration. The client showed "Connection Error — Can't connect to the Prismata server" because all traffic was being redirected to localhost.

**Root cause:** The sniffer instructions (in the script comments) say to manually add/remove the hosts entry, but there's no automated cleanup. If the session ends without removing it, the user is silently locked out.

**Mitigation for any future sniffer-based approach:**
1. **Never modify the hosts file without explicit user consent**
2. **Automated cleanup is mandatory** — use an `atexit` handler, context manager, or finally block that removes the entry
3. **Startup check** — the overlay tool should verify the hosts file doesn't already have a stale redirect before adding one
4. **Prefer non-hosts-file approaches** — e.g., configure the sniffer as a SOCKS proxy, or use Windows Firewall redirect rules that are scoped to the proxy process
5. **Removing the entry requires admin (UAC elevation)** — `Start-Process powershell -Verb RunAs` with a cleanup script, then `ipconfig /flushdns`

This warning applies to Part 3 (clipboard trigger fallback) and the "Auto-detection via network proxy" future upgrade below.

## Future Upgrades (not in this plan)

- **Persistent `--suggest-server` mode**: Keep the C++ engine running as a long-lived process with JSON-line stdin/stdout streaming. Eliminates ~1-2s startup overhead per query (card library load, neural weight load). Would require a simple protocol: write JSON line to stdin, read JSON line from stdout.
- **Event-driven clipboard**: Replace 500ms polling with `AddClipboardFormatListener` Win32 API via ctypes for instant detection (zero latency, zero CPU). Polling is fine for v1 but this is a clean improvement.
- **Auto-detection via network proxy**: Use prismata_sniffer.py to detect turn changes and auto-trigger analysis (no manual hotkey needed). **See hosts file lockout warning above** — any proxy approach MUST include automated cleanup.
- **Full game state reconstruction**: Replay network messages through our engine for fully automatic state tracking
- **Dashboard integration**: Add eval panel to Command Center
- **Move animation**: Show recommended clicks as highlighted units in the overlay
