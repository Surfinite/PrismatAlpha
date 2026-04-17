# DeadGameBot State Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the bot to play full games by tracking game state via a long-running Node.js process (Approach C) and building proper AI requests for PrismataAI.exe.

**Architecture:** A Node.js subprocess (`state_tracker.js`) manages game state using the existing JS engine. Python communicates with it via stdin/stdout JSON lines. On each turn, Python exports the state, combines it with AI parameters, sends it to PrismataAI.exe, and applies the resulting clicks back to the state tracker.

**Tech Stack:** Node.js (existing JS engine), Python 3 (bot), PrismataAI.exe (Steam's Master Bot)

---

## Required Context

**Files to inspect before coding** (read these to verify assumptions — do NOT skip):

| File | Why |
|------|-----|
| `js_engine/Analyzer.js` | Constructor signature, `loaderInit()` behavior |
| `js_engine/State.js` | `toString()` method — output shape for EXPORT |
| `js_engine/matchup_clean.js:484-642` | `applyClicks()` — click handling logic to port |
| `js_engine/matchup_clean.js:1153-1192` | `buildGameInitInfo()` — game init from mergedDeck |
| `js_engine/card_library.js:270-275` | `getSupply()` — supply-from-rarity logic |
| `js_engine/C.js` | Click type constants (`CLICK_SPACE`, `PHASE_CONFIRM`, etc.) |
| `js_engine/_suggest_state.json` | Known-good state that PrismataAI.exe accepts |
| `bot/game_player.py` | Current constructor, handler dispatch, `_build_ai_request()` |
| `bot/ranked_bot.py` | Where GamePlayer is constructed |
| `bot/config.py` | Current config structure |
| `bot/tests/test_game_player.py` | Current test helpers and structure |
| `bot/steam_ai_bridge.py` | `get_move()` input/output contract |
| `tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin` | AI params format |

**Known-good reference data:**
- `js_engine/_suggest_state.json` — real turn-1 state that PrismataAI.exe accepts (wrapped in `CurrentInfo`)
- The mergedDeck inside that file can be used as test input

## Assumptions to Verify

Before implementing, confirm each of these. If any are false, adjust the plan.

| # | Assumption | How to verify |
|---|-----------|---------------|
| A1 | `new Analyzer(gameInitInfo, -1, -1, null)` + `loaderInit()` creates a valid starting state | Read Analyzer.js constructor (confirmed: -1 = replay/analysis mode) |
| A2 | `gameState.toString()` returns JSON matching PrismataAI.exe's expected `gameState` format | Compare `toString()` output fields against `_suggest_state.json` |
| A3 | `buildGameInitInfo(mergedDeck)` is a pure function with no CLI dependencies | Confirmed: only calls `getSupply()` from card_library.js |
| A4 | `matchup_clean.js` **cannot** be required safely — line 120 reads `matchup_config.json` unconditionally | **Confirmed blocker.** Must copy `buildGameInitInfo` into state_tracker.js |
| A5 | `applyClicks` uses module-level `recoveryStats` — returns `{applied, failed, details}` | **Confirmed.** Must port a simplified version, not require it |
| A6 | `GamePlayer.__init__` currently takes `(bridge, client)` — adding `state_bridge` is backward-compatible | Read current constructor |
| A7 | Opponent clicks arrive via `Click` AND `ManyClicks` messages between turns | Read `_handle_click` in game_player.py; check <ladder> protocol docs for `ManyClicks` |
| A8 | The SWF-extracted AI param .bin files exist at `tmp_swf_extract/` | Check files exist |
| A9 | No JS engine module (Analyzer, State, Controller, etc.) uses `console.log` | **Confirmed clean.** 196 `console.log` calls exist but only in CLI/test files, not engine modules |

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `js_engine/state_tracker.js` | **Self-contained** Node.js process: INIT/EXPORT/CLICKS protocol |
| Create | `bot/state_bridge.py` | Python wrapper: subprocess lifecycle + JSON line protocol |
| Create | `bot/ai_params.py` | Load AI parameter .bin files, select full vs short |
| Create | `bot/tests/test_state_bridge.py` | Integration test: Python ↔ Node.js state tracker |
| Create | `bot/tests/test_ai_params.py` | Unit tests for AI param loading and selection |
| Modify | `bot/game_player.py` | Wire state bridge + AI params into `_build_ai_request()` |
| Modify | `bot/tests/test_game_player.py` | Add tests for new `_build_ai_request()` with mocked bridge |
| Modify | `bot/config.py` | Add AI params file paths |

---

### Task 1: Create `js_engine/state_tracker.js`

**Files:**
- Create: `js_engine/state_tracker.js`

**Important:** This script must be **self-contained** — do NOT `require('./matchup_clean')`. That module reads `matchup_config.json` at load time and will throw if the file is missing. Instead, copy the needed functions (`buildGameInitInfo`, click-application logic) directly.

**Protocol:**
- `{"cmd":"INIT","mergedDeck":[...]}` → initialize game from mergedDeck
- `{"cmd":"EXPORT"}` → return current gameState as JSON
- `{"cmd":"CLICKS","clicks":[...]}` → apply clicks, return `{ok, applied, failed}`

- [ ] **Step 1a: Verify JS engine APIs**

Before writing code, confirm these by reading the files:

```bash
# Verify Analyzer constructor accepts (gameInitInfo, -1, -1, null)
# Read js_engine/Analyzer.js, check constructor signature and -1 handling

# Verify gameState.toString() output matches PrismataAI.exe format
# Read js_engine/State.js toString() method, compare with _suggest_state.json

# Verify C.js has CLICK_SPACE, PHASE_CONFIRM, CLICK_END_SWIPE, CLICK_CARD
# Read js_engine/C.js, find click/phase constants

# Check getSupply and SUPPLY_BY_RARITY in card_library.js
# Read js_engine/card_library.js:270-275
```

Document any discrepancies before proceeding.

- [ ] **Step 1b: Create state_tracker.js**

The script must include its own copies of:
1. `buildGameInitInfo(mergedDeck)` — ~40 lines, from matchup_clean.js:1153-1192
2. `getSupply(card)` — ~5 lines, from card_library.js:270-275
3. `SUPPLY_BY_RARITY` — constant from card_library.js:24-29
4. Simplified click-application function — ~60 lines, adapted from matchup_clean.js:484-642

The click-application needs these behaviors from the original `applyClicks`:
- Auto-commit: insert space click when in PHASE_CONFIRM and next click is non-space (lines 507-516)
- Core click: `analyzer.recordClick(false, false, clickType, clickId)` (line 524)
- Breach space skip: skip space clicks during `glassBroken` (lines 533-537)
- End-swipe retry: if click fails while in swipe, end swipe and retry (lines 542-558)
- Auto-breach: exhaust remaining breach damage on weakest units (lines 614-620, calls `autoBreachIfNeeded`)
- Final auto-commit: if in PHASE_CONFIRM after all clicks, commit (lines 624-638)

**Note:** Check what `autoBreachIfNeeded` does (matchup_clean.js:320) and port it if needed, or simplify.

```javascript
'use strict';

/**
 * state_tracker.js — Long-running Node.js process for game state management.
 *
 * Self-contained: copies buildGameInitInfo and click-application logic locally
 * to avoid requiring matchup_clean.js (which reads matchup_config.json at load).
 *
 * Protocol (JSON lines on stdin/stdout):
 *   {"cmd":"INIT","mergedDeck":[...]}  → init game, respond {ok:true}
 *   {"cmd":"EXPORT"}                   → respond {ok:true, state:{...}}
 *   {"cmd":"CLICKS","clicks":[...]}    → apply clicks, respond {ok:true, applied:N, failed:N}
 */

const readline = require('readline');
const Analyzer = require('./Analyzer');
const C = require('./C');

// Redirect console.log to stderr so it can't corrupt the JSON-line protocol on stdout.
// Engine modules don't use console.log (verified), but this is a defensive measure.
console.log = (...args) => console.error('[log]', ...args);

// --- Copied from card_library.js (to avoid matchup_clean.js dependency) ---

const SUPPLY_BY_RARITY = { legendary: 1, rare: 4, normal: 10, trinket: 20 };

function getSupply(card) {
    if (card.rarity === 'unbuyable') return 0;
    return SUPPLY_BY_RARITY[card.rarity] || 20;
}

// --- Copied from matchup_clean.js:1153-1192 ---

function buildGameInitInfo(mergedDeck) {
    const baseWhite = [];
    const baseBlack = [];
    const randomizer = [];

    for (const card of mergedDeck) {
        const supply = card._needsOnly ? 0 : getSupply(card);
        if (card.baseSet) {
            if (card.name === 'Drone') {
                baseWhite.push([card.name, supply + 1]);  // 21
                baseBlack.push([card.name, supply]);       // 20
            } else {
                baseWhite.push([card.name, supply]);
                baseBlack.push([card.name, supply]);
            }
        } else {
            randomizer.push([card.name, supply]);
        }
    }

    return {
        laneInfo: [{
            initResources: ['0', '0'],
            base: [baseWhite, baseBlack],
            randomizer: [randomizer, randomizer],
            initCards: [
                [[6, 'Drone'], [2, 'Engineer']],
                [[7, 'Drone'], [2, 'Engineer']]
            ]
        }],
        mergedDeck: mergedDeck,
        scriptInfo: { whiteStarts: true },
        objectiveInfo: null,
        commandInfo: null
    };
}

// --- Auto-breach (ported from matchup_clean.js:320-380) ---

function autoBreachIfNeeded(analyzer) {
    const gs = analyzer.gameState;
    if (!gs.glassBroken || gs.inEndBO || gs.finished || gs.phase !== C.PHASE_ACTION) {
        return;
    }
    const opponent = 1 - gs.turn;
    let safety = 200;
    while (gs.glassBroken && !gs.inEndBO && !gs.finished && safety-- > 0) {
        if (analyzer.controller.inSwipe) {
            analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
        }
        const atk = gs.turnMana.attack;
        let weakest = null;
        let weakestDmg = Infinity;
        gs.table.forEach((inst) => {
            if (inst.owner === opponent && !inst.dead &&
                inst.constructionTime === 0 &&
                inst.damageReqdToInjure <= atk &&
                inst.damageReqdToInjure < weakestDmg) {
                weakest = inst;
                weakestDmg = inst.damageReqdToInjure;
            }
        });
        if (!weakest) break;
        const result = analyzer.recordClick(false, false, C.CLICK_INST, weakest.instId);
        if (!result.canClick) break;
    }
}

// --- Simplified click application (adapted from matchup_clean.js:484-642) ---

function applyClicks(analyzer, clicks) {
    let applied = 0;
    let failed = 0;

    for (let i = 0; i < clicks.length; i++) {
        const click = clicks[i];
        const clickType = click._type;
        const clickId = click._id !== undefined ? click._id : -1;

        // Auto-commit: C++ AI has ONE space click for action→confirm,
        // JS engine needs TWO (action→confirm + confirm→commit→defense).
        if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished &&
            clickType !== C.CLICK_SPACE && clickType !== 'revert clicked' &&
            clickType !== 'undo clicked' && clickType !== 'redo clicked') {
            const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
            if (commitResult.canClick) applied++;
        }

        let result = analyzer.recordClick(false, false, clickType, clickId);

        // Breach space skip: SteamAI emits space clicks during breach that JS rejects
        if (!result.canClick && clickType === C.CLICK_SPACE && analyzer.gameState.glassBroken) {
            continue;
        }

        // End-swipe retry: if click failed while in a swipe, end swipe and retry
        if (!result.canClick && analyzer.controller && analyzer.controller.inSwipe &&
            clickType !== C.CLICK_END_SWIPE) {
            const swipeResult = analyzer.recordClick(false, false, C.CLICK_END_SWIPE, -1);
            if (swipeResult.canClick) {
                applied++;
                result = analyzer.recordClick(false, false, clickType, clickId);
            }
        }

        if (result.canClick) {
            applied++;
        } else {
            failed++;
            // Log to stderr for debugging (won't interfere with JSON protocol on stdout)
            const gs = analyzer.gameState;
            console.error(`[state_tracker] Click failed: ${clickType} id=${clickId} phase=${gs.phase} glassBroken=${gs.glassBroken}`);
        }
    }

    // Auto-breach: PrismataAI.exe may not emit all breach target clicks.
    // The matchup runner includes this as a safety net. Port from matchup_clean.js:320-380.
    autoBreachIfNeeded(analyzer);

    // Final auto-commit: if still in confirm phase, commit to end the turn
    if (analyzer.gameState.phase === C.PHASE_CONFIRM && !analyzer.gameState.finished) {
        const commitResult = analyzer.recordClick(false, false, C.CLICK_SPACE, -1);
        if (commitResult.canClick) applied++;
    }

    return { applied, failed };
}

// --- State management ---

let analyzer = null;

function handleInit(msg) {
    const mergedDeck = msg.mergedDeck;
    if (!mergedDeck || !Array.isArray(mergedDeck)) {
        return { ok: false, error: 'mergedDeck must be an array' };
    }

    const gameInitInfo = buildGameInitInfo(mergedDeck);
    analyzer = new Analyzer(gameInitInfo, -1, -1, null);
    analyzer.loaderInit();

    return { ok: true };
}

function handleExport() {
    if (!analyzer) {
        return { ok: false, error: 'Not initialized — send INIT first' };
    }

    const stateStr = analyzer.gameState.toString();
    const state = JSON.parse(stateStr);
    return { ok: true, state };
}

function handleClicks(msg) {
    if (!analyzer) {
        return { ok: false, error: 'Not initialized — send INIT first' };
    }

    const clicks = msg.clicks;
    if (!clicks || !Array.isArray(clicks)) {
        return { ok: false, error: 'clicks must be an array' };
    }

    const result = applyClicks(analyzer, clicks);
    return { ok: true, applied: result.applied, failed: result.failed };
}

// --- Uncaught exception handler ---

process.on('uncaughtException', (err) => {
    console.error('[state_tracker] FATAL:', err.stack || err.message);
    process.exit(1);
});

// --- Main loop ---

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', (line) => {
    let response;
    try {
        const msg = JSON.parse(line);
        switch (msg.cmd) {
            case 'INIT':   response = handleInit(msg);   break;
            case 'EXPORT': response = handleExport();     break;
            case 'CLICKS': response = handleClicks(msg);  break;
            default:       response = { ok: false, error: `Unknown command: ${msg.cmd}` };
        }
    } catch (e) {
        response = { ok: false, error: e.message };
    }

    process.stdout.write(JSON.stringify(response) + '\n');
});

rl.on('close', () => process.exit(0));
```

- [ ] **Step 1c: Smoke-test manually**

```bash
cd c:/libraries/PrismataAI
echo '{"cmd":"EXPORT"}' | node js_engine/state_tracker.js
```

Expected: `{"ok":false,"error":"Not initialized — send INIT first"}`

If this throws a require error, check which import fails and fix it.

- [ ] **Step 1d: Commit**

```bash
git add js_engine/state_tracker.js
git commit -m "feat(bot): add Node.js state tracker for game state management

Self-contained long-running process using JS engine Analyzer.
INIT/EXPORT/CLICKS JSON-line protocol on stdin/stdout.
Copies buildGameInitInfo and click-application logic locally
to avoid matchup_clean.js config file dependency."
```

---

### Task 2: Create `bot/state_bridge.py` + tests

**Files:**
- Create: `bot/state_bridge.py`
- Create: `bot/tests/test_state_bridge.py`

Python wrapper that manages the Node.js subprocess and provides a clean API.

- [ ] **Step 1: Write the test file**

```python
"""Tests for StateBridge — Python ↔ Node.js state tracker integration."""

import pytest
from bot.state_bridge import StateBridge

# Minimal mergedDeck: just Drone and Engineer (base set cards).
# Taken from the real mergedDeck format that BeginGame sends.
MINI_DECK = [
    {
        "baseSet": 1, "rarity": "trinket", "toughness": 1,
        "defaultBlocking": 1, "assignedBlocking": 0,
        "buyCost": "3H", "abilityScript": {"receive": "1"},
        "name": "Drone", "UIName": "Drone"
    },
    {
        "baseSet": 1, "rarity": "trinket", "toughness": 1,
        "defaultBlocking": 1, "buyCost": "2",
        "beginOwnTurnScript": {"receive": "H"}, "score": "2.01",
        "name": "Engineer", "UIName": "Engineer"
    },
]


class TestStateBridgeLifecycle:
    def test_init_and_export(self):
        """INIT with a valid deck, then EXPORT should return a valid state."""
        bridge = StateBridge()
        try:
            result = bridge.start(MINI_DECK)
            assert result["ok"] is True

            export = bridge.export_state()
            assert export["ok"] is True
            state = export["state"]

            # Verify basic state structure (acceptance criteria, not exact values)
            assert "table" in state
            assert "cards" in state
            assert "whiteMana" in state
            assert "blackMana" in state
            assert "turn" in state
            assert "phase" in state
            assert state["phase"] == "action"
            assert state["turn"] == 0  # White's turn first

            # Should have starting units on the table
            # Standard game: 6+2 (P0) + 7+2 (P1) = 17, but verify > 0
            assert len(state["table"]) > 0
        finally:
            bridge.close()

    def test_apply_empty_clicks(self):
        """Applying empty clicks should succeed with 0 applied."""
        bridge = StateBridge()
        try:
            bridge.start(MINI_DECK)
            result = bridge.apply_clicks([])
            assert result["ok"] is True
            assert result["applied"] == 0
            assert result["failed"] == 0
        finally:
            bridge.close()

    def test_export_without_start_fails(self):
        """EXPORT before start() should return an error about process not running."""
        bridge = StateBridge()
        try:
            result = bridge.export_state()
            assert result["ok"] is False
            assert "error" in result
        finally:
            bridge.close()

    def test_close_is_idempotent(self):
        """Calling close() multiple times should not raise."""
        bridge = StateBridge()
        bridge.start(MINI_DECK)
        bridge.close()
        bridge.close()  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_state_bridge.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'bot.state_bridge'`

- [ ] **Step 3: Write state_bridge.py**

```python
"""StateBridge — manages a Node.js state tracker subprocess.

Spawns js_engine/state_tracker.js as a long-running child process.
Communicates via JSON lines on stdin/stdout.
"""

import json
import logging
import os
import subprocess
import threading

log = logging.getLogger(__name__)

_STATE_TRACKER_JS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'js_engine', 'state_tracker.js'
))

# Timeout for each JSON-line round trip (seconds).
_SEND_TIMEOUT_S = 30


class StateBridge:
    """Manage a Node.js state tracker subprocess."""

    def __init__(self, node_path='node'):
        self.node_path = node_path
        self.proc = None
        self._stderr_thread = None

    def start(self, merged_deck):
        """Spawn the state tracker and initialize with merged_deck.

        Idempotent: closes any existing process before starting a new one.

        Args:
            merged_deck: list of card definition dicts from BeginGame.

        Returns:
            dict with 'ok' key.
        """
        self.close()  # idempotent: clean up any prior process

        try:
            self.proc = subprocess.Popen(
                [self.node_path, _STATE_TRACKER_JS],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
                cwd=os.path.dirname(_STATE_TRACKER_JS),
            )
        except (FileNotFoundError, OSError) as e:
            return {'ok': False, 'error': f'Failed to start state tracker: {e}'}

        # Drain stderr in background thread to prevent pipe buffer fill-up.
        # Captured lines are logged and available for error diagnostics.
        self._stderr_lines = []
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        self._stderr_thread.start()

        return self._send({'cmd': 'INIT', 'mergedDeck': merged_deck})

    def _drain_stderr(self):
        """Read stderr lines in background (prevents pipe buffer fill)."""
        try:
            for line in self.proc.stderr:
                line = line.rstrip('\n')
                if line:
                    self._stderr_lines.append(line)
                    # Keep bounded (last 100 lines)
                    if len(self._stderr_lines) > 100:
                        self._stderr_lines.pop(0)
                    log.debug("state_tracker: %s", line)
        except (ValueError, OSError):
            pass  # pipe closed

    def export_state(self):
        """Export current game state.

        Returns:
            dict with 'ok' and 'state' keys.
        """
        return self._send({'cmd': 'EXPORT'})

    def apply_clicks(self, clicks):
        """Apply clicks to advance the game state.

        Args:
            clicks: list of click dicts, e.g. [{"_type": "card clicked", "_id": 0}]

        Returns:
            dict with 'ok', 'applied', 'failed' keys.
        """
        return self._send({'cmd': 'CLICKS', 'clicks': clicks})

    def close(self):
        """Shut down the Node.js subprocess."""
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def _send(self, msg, timeout=None):
        """Send a JSON command and read the JSON response.

        Uses a background thread + timeout to avoid hanging forever
        if the Node.js process wedges.
        """
        timeout = timeout or _SEND_TIMEOUT_S

        if not self.proc or self.proc.poll() is not None:
            return {'ok': False, 'error': 'State tracker process not running'}

        line = json.dumps(msg, separators=(',', ':')) + '\n'
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            return {'ok': False, 'error': f'Pipe error writing: {e}'}

        # Read with timeout via a thread
        result = [None]
        def read_response():
            try:
                result[0] = self.proc.stdout.readline()
            except Exception:
                pass

        reader = threading.Thread(target=read_response, daemon=True)
        reader.start()
        reader.join(timeout=timeout)

        if reader.is_alive():
            stderr_tail = '\n'.join(self._stderr_lines[-5:]) if hasattr(self, '_stderr_lines') else ''
            return {'ok': False, 'error': f'Timeout ({timeout}s) waiting for state tracker. stderr: {stderr_tail}'}

        response_line = result[0]
        if not response_line:
            stderr_tail = '\n'.join(self._stderr_lines[-5:]) if hasattr(self, '_stderr_lines') else ''
            return {'ok': False, 'error': f'No response from state tracker. stderr: {stderr_tail}'}

        try:
            return json.loads(response_line)
        except json.JSONDecodeError as e:
            return {'ok': False, 'error': f'Invalid JSON response: {e}'}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_state_bridge.py -v
```

Expected: 4 passed. If any fail, check stderr from the Node.js process for clues.

- [ ] **Step 5: Commit**

```bash
git add bot/state_bridge.py bot/tests/test_state_bridge.py
git commit -m "feat(bot): add StateBridge for Python-Node.js state tracking

Manages state_tracker.js subprocess with JSON line protocol.
Integration tests verify INIT/EXPORT/CLICKS lifecycle."
```

---

### Task 3: Create `bot/ai_params.py` + tests

**Files:**
- Create: `bot/ai_params.py`
- Create: `bot/tests/test_ai_params.py`
- Modify: `bot/config.py` (add paths)

Loads the AI parameter files (JSON text in .bin files extracted from SWF) and selects full vs short params based on difficulty and turn number.

- [ ] **Step 1: Verify AI param files exist**

```bash
ls -la c:/libraries/PrismataAI/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin
ls -la c:/libraries/PrismataAI/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin
```

If missing, check `tmp_swf_extract/` for similar filenames.

- [ ] **Step 2: Add paths to config.py**

Read current `bot/config.py` first to find the right place to add. Add these constants:

```python
# AI parameter files (JSON text extracted from SWF via JPEXS FFDec)
AI_FULL_PARAMS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'tmp_swf_extract',
    '148_AI.AIThreadHandler_aiParamTextLoad.bin'
)
AI_SHORT_PARAMS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'tmp_swf_extract',
    '93_AI.AIThreadHandler_aiParam_shortTextLoad.bin'
)
```

- [ ] **Step 3: Write the test file**

```python
"""Tests for AI parameter loading and selection."""

import json
import pytest
from bot.ai_params import load_params, select_params
from bot.config import AI_FULL_PARAMS_PATH, AI_SHORT_PARAMS_PATH


class TestLoadParams:
    def test_load_full_params_is_valid_json(self):
        """Full params file should parse as valid JSON with Players section."""
        raw = load_params(AI_FULL_PARAMS_PATH)
        data = json.loads(raw)
        assert "Players" in data
        assert "HardestAI" in data["Players"]

    def test_load_short_params_is_valid_json(self):
        """Short params file should parse as valid JSON with Players section."""
        raw = load_params(AI_SHORT_PARAMS_PATH)
        data = json.loads(raw)
        assert "Players" in data
        assert "HardestAI" in data["Players"]

    def test_hardest_ai_has_time_limit(self):
        """HardestAI should have a TimeLimit field."""
        raw = load_params(AI_SHORT_PARAMS_PATH)
        data = json.loads(raw)
        assert "TimeLimit" in data["Players"]["HardestAI"]
        assert isinstance(data["Players"]["HardestAI"]["TimeLimit"], int)

    def test_whitespace_stripped(self):
        """Loaded params should have no tabs or newlines (matching AS3 behavior)."""
        raw = load_params(AI_FULL_PARAMS_PATH)
        assert '\t' not in raw
        assert '\n' not in raw
        assert '\r' not in raw


class TestSelectParams:
    def test_hardest_ai_always_short(self):
        """HardestAI is in AI_NO_OPENINGS at index > 0, always gets short params."""
        assert select_params("HardestAI", 0, "full", "short") == "short"
        assert select_params("HardestAI", 5, "full", "short") == "short"
        assert select_params("HardestAI", 20, "full", "short") == "short"

    def test_docile_ai_gets_full_params(self):
        """DocileAI at index 0 — AS3 bug means it gets full params early."""
        assert select_params("DocileAI", 0, "full", "short") == "full"
        assert select_params("DocileAI", 10, "full", "short") == "full"

    def test_docile_ai_gets_short_after_turn_16(self):
        """Even DocileAI gets short params after turn 16."""
        assert select_params("DocileAI", 17, "full", "short") == "short"

    def test_unknown_ai_gets_full_early(self):
        """Unknown AI names get full params for early turns."""
        assert select_params("CustomAI", 0, "full", "short") == "full"

    def test_unknown_ai_gets_short_late(self):
        """Unknown AI names get short params after turn 16."""
        assert select_params("CustomAI", 17, "full", "short") == "short"
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_ai_params.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'bot.ai_params'`

- [ ] **Step 5: Write ai_params.py**

```python
"""AI parameter loading and selection for PrismataAI.exe.

Loads AI parameters from SWF-extracted .bin files (plain JSON text).
Matches the AS3 logic in AIThreadHandler.as for selecting full vs short
params based on difficulty and turn number.
"""

import re

# AI names that should NOT use opening books (use short params).
# From AIThreadHandler.as:110. Order matters — index 0 (DocileAI) is
# special due to an AS3 bug (uses > 0, not !== -1).
AI_NO_OPENINGS = [
    'DocileAI', 'RandomAI', 'EasyAI', 'MediumAI', 'ExpertAI', 'HardAI', 'HardestAI',
    'BL_HighEcon_Basic', 'BL_HighEcon_Adept', 'BL_HighEcon_Expert', 'BL_HighEcon_Master',
    'BL_Blue_Rusher', 'BL_Red_Rusher', 'BL_Green_Rusher',
    'BL_Red_Master', 'BL_Blue_Master', 'BL_Green_Master',
    'Mission_Giselle_Hard', 'Mission_Xelgudu1_Hard', 'Mission_Rube', 'Mission_Rube_Hard',
]


def load_params(path):
    """Load and clean AI parameters JSON string from a .bin file.

    Strips whitespace to match AS3 behavior (AIThreadHandler.as:206).

    Args:
        path: path to the .bin file (plain JSON text).

    Returns:
        Cleaned JSON string with no tabs/newlines.
    """
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    return re.sub(r'[\r\n\t]+', '', raw)


def select_params(difficulty, turn_number, full_params, short_params):
    """Select which AI parameters to use.

    Matches AIThreadHandler.as:297-303 and :340-347 logic.
    NOTE: AS3 uses indexOf > 0, so DocileAI (index 0) gets full params.

    Args:
        difficulty: AI name (e.g. "HardestAI").
        turn_number: current numTurns value from game state.
        full_params: full params string (for early turns with opening books).
        short_params: short params string (no opening books).

    Returns:
        The selected params string.
    """
    try:
        idx = AI_NO_OPENINGS.index(difficulty)
    except ValueError:
        idx = -1

    if idx > 0 or turn_number > 16:
        return short_params
    return full_params
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_ai_params.py -v
```

Expected: All passed.

- [ ] **Step 7: Commit**

```bash
git add bot/config.py bot/ai_params.py bot/tests/test_ai_params.py
git commit -m "feat(bot): add AI parameter loading and selection

Reads SWF-extracted .bin files, strips whitespace (AS3 compat),
selects full vs short params based on difficulty and turn number."
```

---

### Task 4: Update `bot/game_player.py` — wire state bridge + AI params

**Files:**
- Modify: `bot/game_player.py`
- Modify: `bot/tests/test_game_player.py`

**IMPORTANT:** Read the current `bot/game_player.py` and `bot/tests/test_game_player.py` BEFORE implementing. The code below describes the intended changes, but exact line numbers, constructor shape, and method names must be verified against the current file.

The key changes:
1. Accept `state_bridge` as an optional constructor parameter
2. Initialize state tracker on BeginGame
3. Rewrite `_build_ai_request()` to EXPORT state and combine with AI params
4. Buffer opponent clicks separately, flush to state tracker before our turns
5. Apply our own clicks to state tracker after playing
6. Handle `ManyClicks` server message (batch of clicks in one message)
7. Dump debug artifacts to disk on AI or click-application failure

- [ ] **Step 1: Read current files**

Read `bot/game_player.py` and `bot/tests/test_game_player.py` in full. Note:
- Current constructor signature
- Current `_build_ai_request()` implementation
- Current `_handle_click()` behavior
- Current `_play_turn()` flow
- Test helper `_make_init_info()` structure
- How existing tests construct GamePlayer

- [ ] **Step 2: Write new tests**

Add a `FakeStateBridge` mock class and new test classes to `bot/tests/test_game_player.py`. The mock should implement `start()`, `export_state()`, `apply_clicks()`, `close()` with canned responses.

**Acceptance criteria for new tests:**
- `TestBuildAIRequest.test_builds_valid_request` — after BeginGame, `_build_ai_request()` returns a dict with keys `mergedDeck`, `gameState`, `aiParameters`, `aiPlayerName`
- `TestBuildAIRequest.test_state_bridge_initialized_on_begin_game` — BeginGame calls `state_bridge.start()` with the merged deck
- `TestBuildAIRequest.test_returns_none_without_state_bridge` — with `state_bridge=None`, returns None
- `TestOpponentClickFlushing.test_opponent_clicks_flushed` — opponent Click messages are buffered and flushed to state bridge
- `TestOpponentClickFlushing.test_flush_clears_buffer` — buffer is empty after flush
- `TestOpponentClickFlushing.test_flush_empty_is_noop` — flushing with no clicks doesn't call apply_clicks
- `TestManyClicks.test_many_clicks_buffered` — `ManyClicks` message buffers all clicks for state bridge flushing

- [ ] **Step 3: Run new tests to verify they fail**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_game_player.py -v -k "TestBuildAIRequest or TestOpponentClickFlushing"
```

Expected: FAIL (new tests reference new constructor param and methods)

- [ ] **Step 4: Implement changes to game_player.py**

Changes to make (adapt to current file structure):

**a) Add imports:**
```python
import json
from bot.ai_params import load_params, select_params
from bot.config import AI_FULL_PARAMS_PATH, AI_SHORT_PARAMS_PATH
```

**b) Update constructor** — add `state_bridge=None` parameter (keyword-only to avoid breaking existing callers). Add `_pending_opponent_clicks = []` buffer. Load and **parse** AI params once at construction (not every turn):
```python
def _load_ai_params(self):
    try:
        full_str = load_params(AI_FULL_PARAMS_PATH)
        short_str = load_params(AI_SHORT_PARAMS_PATH)
        self._full_params = json.loads(full_str)
        self._short_params = json.loads(short_str)
    except FileNotFoundError:
        log.warning("AI param files not found — _build_ai_request will fail")
        self._full_params = None
        self._short_params = None
```

**c) Update `_handle_begin_game`** — after extracting init_info and merged_deck, call `self.state_bridge.start(self.merged_deck)` if state_bridge is set.

**d) Replace `_build_ai_request`** — flush opponent clicks, export state from bridge, combine with pre-parsed AI params. Use `select_params` with the string versions for selection, but pass the pre-parsed dict:
```python
def _build_ai_request(self):
    if not self.state_bridge:
        log.error("No state bridge configured")
        return None
    if not self._short_params:
        log.error("AI parameters not loaded")
        return None
    self._flush_opponent_clicks()
    export = self.state_bridge.export_state()
    if not export.get("ok"):
        log.error("State export failed: %s", export.get("error"))
        return None
    game_state = export["state"]
    # HardestAI always gets short params (index 6 in AI_NO_OPENINGS).
    # Keep select_params for correctness if difficulty becomes configurable.
    ai_params = self._short_params  # pre-parsed at construction
    return {
        "mergedDeck": self.merged_deck,
        "gameState": game_state,
        "aiParameters": ai_params,
        "aiPlayerName": "HardestAI",
    }
```

**e) Add `_flush_opponent_clicks` method** — sends buffered clicks to state bridge, clears buffer.

**f) Update `_handle_click`** — also append to `_pending_opponent_clicks` buffer.

**g) Add `_handle_many_clicks` handler** — the server can send `ManyClicks` (batch of clicks in one message) as an alternative to individual `Click` messages. Format: `["ManyClicks", game_id, [click1, click2, ...]]`. Add to handler dispatch table:
```python
def _handle_many_clicks(self, msg):
    """Handle ManyClicks — batch of opponent clicks in one message."""
    if len(msg) >= 3 and isinstance(msg[2], list):
        for click_data in msg[2]:
            self.command_list.append(click_data)
            self._pending_opponent_clicks.append(click_data)
        log.debug("ManyClicks: %d opponent clicks", len(msg[2]))
```
Add `"ManyClicks": _handle_many_clicks` to the `_HANDLERS` dispatch table.

**h) Update `_play_turn`** — after sending clicks to server, also `apply_clicks` to state bridge. On click-application failure, log error and dump debug artifacts:
```python
# Apply our clicks to state tracker
if self.state_bridge and clicks:
    result = self.state_bridge.apply_clicks(clicks)
    if not result.get("ok") or result.get("failed", 0):
        log.error("Click application failed: %s", result)
        self._dump_debug_state("our_clicks_failed")
```

**i) Add `_dump_debug_state` method** — saves game state and AI request to disk for post-mortem debugging:
```python
def _dump_debug_state(self, label):
    """Dump current state and recent data to disk for debugging."""
    import json, time
    ts = int(time.time())
    path = f"bot_debug_{label}_{ts}.json"
    try:
        export = self.state_bridge.export_state() if self.state_bridge else {}
        data = {
            "label": label,
            "game_id": self.game_id,
            "current_turn": self.current_turn,
            "our_player_index": self.our_player_index,
            "state": export.get("state") if export.get("ok") else None,
            "command_list_tail": self.command_list[-20:],
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        log.info("Debug state dumped to %s", path)
    except Exception as e:
        log.warning("Failed to dump debug state: %s", e)
```

**j) Update `reset`** — clear `_pending_opponent_clicks`, close state bridge.

- [ ] **Step 5: Run ALL game_player tests**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_game_player.py -v
```

Expected: All tests pass — both existing and new. Existing tests should still pass because `state_bridge=None` is the default.

- [ ] **Step 6: Commit**

```bash
git add bot/game_player.py bot/tests/test_game_player.py
git commit -m "feat(bot): wire state tracker and AI params into GamePlayer

_build_ai_request() exports state from Node.js tracker, selects
AI params, builds proper PrismataAI.exe request format.
Opponent clicks buffered and flushed before each turn."
```

---

### Task 5: Update `bot/ranked_bot.py` — pass state bridge to GamePlayer

**Files:**
- Modify: `bot/ranked_bot.py`

- [ ] **Step 1: Read current ranked_bot.py**

Read `bot/ranked_bot.py` to find where GamePlayer is constructed.

- [ ] **Step 2: Add StateBridge import and pass to GamePlayer**

```python
from bot.state_bridge import StateBridge
```

Where GamePlayer is constructed, add:
```python
state_bridge = StateBridge()
# Pass to GamePlayer (adapt to current constructor call)
```

- [ ] **Step 3: Commit**

```bash
git add bot/ranked_bot.py
git commit -m "feat(bot): pass StateBridge to GamePlayer in ranked bot"
```

---

### Task 6: Integration test — bot plays turn 0

**Files:**
- Create: `bot/tests/test_integration.py`

End-to-end test: init state tracker → export state → build AI request → PrismataAI.exe responds with clicks. **Requires PrismataAI.exe and Node.js to be present.**

- [ ] **Step 1: Write integration test**

```python
"""Integration test — full pipeline from state init to AI move.

Requires PrismataAI.exe at the configured path.
Run with: pytest bot/tests/test_integration.py -v -s -m integration
"""

import json
import os
import pytest
from bot.config import PRISMATA_AI_EXE
from bot.state_bridge import StateBridge
from bot.steam_ai_bridge import SteamAIBridge
from bot.ai_params import load_params
from bot.config import AI_SHORT_PARAMS_PATH

# Load mergedDeck from the reference state file
SUGGEST_STATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'js_engine', '_suggest_state.json'
)


def load_test_deck():
    with open(SUGGEST_STATE_PATH, 'r') as f:
        data = json.load(f)
    return data["CurrentInfo"]["mergedDeck"]


@pytest.mark.integration
class TestFullPipeline:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        if not os.path.isfile(PRISMATA_AI_EXE):
            pytest.skip(f"PrismataAI.exe not found at {PRISMATA_AI_EXE}")
        if not os.path.isfile(SUGGEST_STATE_PATH):
            pytest.skip(f"Reference state not found at {SUGGEST_STATE_PATH}")

    def test_turn_0_produces_clicks(self):
        """Full pipeline: init → export → AI request → PrismataAI.exe → clicks."""
        deck = load_test_deck()

        bridge = StateBridge()
        try:
            # 1. Init state tracker
            result = bridge.start(deck)
            assert result["ok"], f"INIT failed: {result}"

            # 2. Export state
            export = bridge.export_state()
            assert export["ok"], f"EXPORT failed: {export}"
            state = export["state"]
            assert state["turn"] == 0, f"Expected turn 0, got {state['turn']}"
            assert state["phase"] == "action", f"Expected action phase, got {state['phase']}"

            # 3. Build AI request
            short_params = load_params(AI_SHORT_PARAMS_PATH)
            ai_params = json.loads(short_params)
            request = {
                "mergedDeck": deck,
                "gameState": state,
                "aiParameters": ai_params,
                "aiPlayerName": "HardestAI",
            }

            # 4. Send to PrismataAI.exe
            steam = SteamAIBridge()
            response = steam.get_move(request)

            # 5. Should get clicks back
            clicks = response.get("aiclicks", [])
            assert len(clicks) > 0, f"No clicks returned: {response}"

            # 6. Apply clicks to state tracker
            apply_result = bridge.apply_clicks(clicks)
            assert apply_result["ok"], f"CLICKS failed: {apply_result}"
            assert apply_result["applied"] > 0

            # 7. State should advance (turn or numTurns changed)
            export2 = bridge.export_state()
            assert export2["ok"]

            print(f"\nTurn 0: {len(clicks)} clicks, "
                  f"eval={response.get('eval_pct', '?')}, "
                  f"applied={apply_result['applied']}, failed={apply_result.get('failed', 0)}")
        finally:
            bridge.close()
```

- [ ] **Step 2: Run integration test**

```bash
cd c:/libraries/PrismataAI
python -m pytest bot/tests/test_integration.py -v -s -m integration
```

Expected: 1 passed. If PrismataAI.exe crashes, the state format needs debugging — compare the exported state against `_suggest_state.json` field by field.

- [ ] **Step 3: Commit**

```bash
git add bot/tests/test_integration.py
git commit -m "test(bot): add integration test for full turn-0 pipeline

Verifies: state tracker init → export → AI request → PrismataAI.exe
response → click application → state advance."
```

---

### Task 7: Live bot test — play a full bot game

**Files:** (no code changes — manual test)

- [ ] **Step 1: Run the bot with `--bot-game`**

```powershell
cd c:/libraries/PrismataAI
$env:BOT_USERNAME="DeadGameBot"
$env:BOT_PASSWORD="DeadGameBot123"
python -m bot --bot-game
```

Watch the logs for:
- `State tracker initialized` — state bridge started
- `Played turn N: M clicks` — turns executing successfully
- `GameOver: result=...` — game completed

- [ ] **Step 2: Debug common issues**

| Symptom | Likely cause |
|---------|-------------|
| `"error":"mergedDeck must be an array"` | BeginGame mergedDeck format issue — check what server sends |
| PrismataAI.exe crash (0xC0000409) | State format mismatch — compare exported state vs `_suggest_state.json` |
| `"failed": N` in click application | JS engine rejecting clicks — check stderr from state_tracker.js |
| State stuck on same turn | Clicks not advancing state — missing final commit click? |
| Opponent turn hangs | Not receiving opponent clicks — check `_handle_click` routing |

- [ ] **Step 3: Commit any fixes discovered during testing**
