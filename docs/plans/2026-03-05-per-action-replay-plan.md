# Per-Action Replay Stepping — Implementation Plan

**Goal:** Run MCDSAI vs itself (or any player combination) via CLI, capture per-action state snapshots, and step through individual actions in the GUI using arrow keys.

**Current behavior:** GUI replay viewer steps through one GameState per turn (Right/Left arrows).
**New behavior:** Arrow keys step through individual actions within turns. Turn boundaries are visually indicated in the HUD.

---

## Phase 0: Documentation Discovery — Summary

### Allowed APIs (JS side)
- `analyzer.recordClick(false, false, type, id, params)` — applies one click, mutates `analyzer.gameState` in-place (Analyzer.js:300-364)
- `stateToCppJSON(state)` — converts JS State to C++ GameState JSON (replay_exporter.js:62-113)
- `buildReplayJSON(states, p0, p1, winner, turns, cardSet)` — builds replay file (replay_exporter.js:129-142)
- `State.clone()` — deep-copies state, O(board size), <1ms (State.js:1671-1673)
- Click types: `CLICK_CARD` ("card clicked"), `CLICK_INST` ("inst clicked"), `CLICK_SPACE` ("space clicked"), `CLICK_END_SWIPE` ("end swipe processed") (C.js:14-27)

### Allowed APIs (C++ GUI side)
- `GUIState_Play(game, vector<GameState>, p0, p1, winner)` — replay constructor (GUIState_Play.cpp:33-52)
- `GameState(rapidjson::Value)` — constructs from JSON (GameState.cpp:11-15)
- `loadReplay(filepath)` — reads JSON with keys `p0`, `p1`, `winner`, `states` (GUIState_Menu.cpp:94-135)
- `advanceReplayState()` / `rewindReplayState()` — increment/decrement `m_replayIndex` (GUIState_Play.cpp:269-282)
- `drawReplayHUD()` — displays turn info at top, controls at bottom (GUIState_Play.cpp:285-308)
- `GUITools::DrawString(pos, text, color, window, size)` — text rendering

### Anti-patterns
- Do NOT call `stateToCppJSON()` on temporary/validation analyzers (StateUtil.convertToClicks creates a temp one)
- Do NOT clone state before EACH click — snapshot AFTER each successful click only
- Do NOT change the `states` array format — keep backward compatible (old per-turn replays still work)

---

## Phase 1: JS — Capture Per-Action States in Matchup Runner

### What to implement

Modify the click application functions to optionally return intermediate state snapshots after each successful click.

### Files to modify

#### 1a. `js_engine/matchup_clean.js` — `playMCDSAITurn()` (lines 440-503)

In the primary click loop (lines 451-461), after each successful `analyzer.recordClick()`, capture a state snapshot with action metadata:

```javascript
// After line 453: const result = analyzer.recordClick(...)
if (result.canClick) {
    applied++;
    details.push(`  [${i}] OK: ${click._type} id=${click._id}`);
    // NEW: capture per-action state
    if (actionStates) {
        actionStates.push({
            state: stateToCppJSON(analyzer.gameState),
            action: describeClick(click, analyzer.gameState)
        });
    }
}
```

Also capture for the auto-confirm click (lines 495-502) and the fallback path (lines 464-491).

Add `actionStates` parameter to function signature. Return it alongside existing return value.

#### 1b. `js_engine/matchup_clean.js` — `applyClicks()` (lines 252-286)

Same pattern — after each successful `recordClick()`, snapshot state + action label. Add `actionStates` parameter.

#### 1c. `js_engine/matchup_clean.js` — New helper `describeClick(click, state)`

Create a small helper that generates a human-readable label for each click:

| Click Type | Label Format | Example |
|---|---|---|
| `"card clicked"` | `"Buy {cardName}"` | `"Buy Tarsier"` |
| `"inst clicked"` (action phase) | `"Use {cardName}"` | `"Use Drone"` |
| `"inst clicked"` (defense phase) | `"Block with {cardName}"` | `"Block with Wall"` |
| `"space clicked"` | `"End Phase"` | `"End Phase"` |
| `"end swipe processed"` | `"End Defense"` | `"End Defense"` |

Card name resolution: For `card clicked`, look up `state.cards[click._id].UIName`. For `inst clicked`, look up the instance from `state.table` by instId and get its `card.UIName`.

#### 1d. `js_engine/matchup_worker.js` — Game loop (lines 245-408)

Currently (line 260):
```javascript
try { replayStates.push(stateToCppJSON(analyzer.gameState)); }
```

Change to: collect per-action states from `playMCDSAITurn()` / `playSingleTurnSlot()` return values, and accumulate them into a single flat array. Also track turn boundaries (the index in the flat array where each new turn begins).

```javascript
const allActionStates = [];   // replaces replayStates
const turnBoundaries = [];    // index into allActionStates where each turn starts
const actionLabels = [];      // parallel to allActionStates

// Before each turn:
turnBoundaries.push(allActionStates.length);
// Capture pre-turn state
allActionStates.push(stateToCppJSON(analyzer.gameState));
actionLabels.push('Start of Turn');

// After turn execution, append the per-action states from the turn function
```

#### 1e. `js_engine/replay_exporter.js` — `buildReplayJSON()`

Extend to accept optional `actions` and `turnBoundaries` arrays:

```javascript
function buildReplayJSON(gameStateJSONs, p0, p1, winner, turns, cardSet, actions, turnBoundaries) {
    return {
        replay: true,
        p0, p1, winner,
        winnerName: winner === 0 ? p0 : winner === 1 ? p1 : 'Draw',
        turns,
        cardSet,
        states: gameStateJSONs,
        // NEW — only present for per-action replays
        actions: actions || undefined,           // string[] parallel to states
        turnBoundaries: turnBoundaries || undefined  // int[] indices into states where turns start
    };
}
```

### Verification
- Run: `node js_engine/matchup_clean.js --games 2 --save-replays action_test`
- Check a saved JSON file:
  - `states` array should have many more entries than `turns` value (e.g., turns=20, states=200+)
  - `actions` array should exist and be same length as `states`
  - `turnBoundaries` array should have `turns + 1` entries
  - Actions should include recognizable labels like "Buy Drone", "Use Tarsier", "End Phase"

---

## Phase 2: C++ GUI — Per-Action Replay Display

### What to implement

The basic stepping already works (more states = more steps via arrow keys). The main changes are:
1. Parse new `actions` and `turnBoundaries` fields from JSON
2. Update HUD to show action context
3. Add turn-jump controls (skip to next/previous turn boundary)

### Files to modify

#### 2a. `source/gui/GUIState_Play.h` — New member variables

Add after line 76:
```cpp
// Per-action replay metadata (empty for legacy per-turn replays)
std::vector<std::string>    m_actionLabels;      // Human-readable label per state
std::vector<size_t>         m_turnBoundaries;    // Indices where turns start
```

#### 2b. `source/gui/GUIState_Menu.cpp` — `loadReplay()` (lines 94-135)

After parsing `states`, also parse `actions` and `turnBoundaries` if present:

```cpp
// After building replayStates vector:
std::vector<std::string> actionLabels;
if (doc.HasMember("actions") && doc["actions"].IsArray()) {
    const auto & actions = doc["actions"];
    for (rapidjson::SizeType i = 0; i < actions.Size(); ++i) {
        actionLabels.push_back(actions[i].GetString());
    }
}

std::vector<size_t> turnBoundaries;
if (doc.HasMember("turnBoundaries") && doc["turnBoundaries"].IsArray()) {
    const auto & tb = doc["turnBoundaries"];
    for (rapidjson::SizeType i = 0; i < tb.Size(); ++i) {
        turnBoundaries.push_back(static_cast<size_t>(tb[i].GetInt()));
    }
}
```

Pass these to `GUIState_Play` constructor (add parameters).

#### 2c. `source/gui/GUIState_Play.cpp` — Updated constructor

Accept and store `actionLabels` and `turnBoundaries`. Add a second constructor overload or extend existing:

```cpp
GUIState_Play(GUIEngine & game, std::vector<GameState> replayStates,
              const std::string & p0, const std::string & p1, int winner,
              std::vector<std::string> actionLabels = {},
              std::vector<size_t> turnBoundaries = {});
```

#### 2d. `source/gui/GUIState_Play.cpp` — `drawReplayHUD()` (lines 285-308)

Update the HUD display:

**If per-action data exists** (`!m_actionLabels.empty()`):
- Show: `"P0 vs P1   Turn 5/21   Action: Buy Tarsier   [3/7 in turn]   Winner: Name"`
- Turn number derived from `m_turnBoundaries` (find which turn boundary range contains `m_replayIndex`)
- Action label from `m_actionLabels[m_replayIndex]`
- Action-within-turn count: `m_replayIndex - currentTurnStart + 1` of `nextTurnStart - currentTurnStart`

**If no per-action data** (legacy replay): keep current behavior unchanged.

#### 2e. `source/gui/GUIState_Play.cpp` — Add turn-jump controls

Add two new methods and keyboard bindings:

```cpp
void GUIState_Play::jumpToNextTurn()
{
    if (!m_replayMode || m_turnBoundaries.empty()) return;
    // Find next turn boundary after current index
    for (size_t i = 0; i < m_turnBoundaries.size(); i++) {
        if (m_turnBoundaries[i] > m_replayIndex) {
            m_replayIndex = m_turnBoundaries[i];
            setState(m_stateHistory[m_replayIndex]);
            return;
        }
    }
}

void GUIState_Play::jumpToPrevTurn()
{
    if (!m_replayMode || m_turnBoundaries.empty()) return;
    // Find previous turn boundary before current index
    for (int i = (int)m_turnBoundaries.size() - 1; i >= 0; i--) {
        if (m_turnBoundaries[i] < m_replayIndex) {
            m_replayIndex = m_turnBoundaries[i];
            setState(m_stateHistory[m_replayIndex]);
            return;
        }
    }
}
```

**Keyboard bindings** (add to switch in replay mode, ~line 327):
- `Up` arrow → `jumpToNextTurn()`
- `Down` arrow → `jumpToPrevTurn()`

Update the controls hint text in `drawReplayHUD()` to show the new bindings.

### Verification
- Build: `MSBuild Prismata.sln /t:Rebuild /p:Configuration=Debug /p:Platform=x86 /m`
- Run MCDSAI games: `node js_engine/matchup_clean.js --games 2 --save-replays gui_test`
- Launch `Prismata_GUI_d.exe`, navigate to the replay folder
- Load a game — verify:
  - Right/Left steps through individual actions (board changes visibly between steps)
  - HUD shows action labels ("Buy Drone", "Use Tarsier", etc.)
  - HUD shows turn context ("Turn 5, Action 3/7")
  - Up/Down jumps between turn boundaries
  - Old per-turn replays still load and work as before (backward compat)

---

## Phase 3: Verification & Edge Cases

### Backward compatibility
- `grep -r '"actions"' bin/asset/replays/` — old replays should NOT have this field
- Load an old per-turn replay → GUI should show "Turn X/Y" (no action labels, no turn jumping)
- Load a new per-action replay → GUI should show action-level detail

### Edge cases to test
- Game that ends mid-turn (resignation / all-units-doomed)
- Turn with 0 successful clicks (MCDSAI resignation)
- Turn with failed clicks (should not generate state snapshots for failed clicks)
- Very long game (30+ turns) — verify replay file size is reasonable
- C++ player turns (via `applyClicks`) — also get per-action states

### Performance check
- A 20-turn game with ~15 actions/turn = ~300 states per replay
- Each state JSON is ~2-5 KB → ~1 MB per replay file (acceptable)
- `stateToCppJSON()` is lightweight — no performance concern

### Grep checks
- `grep -n "actionStates" js_engine/matchup_clean.js` — should appear in both `playMCDSAITurn` and `applyClicks`
- `grep -n "turnBoundaries" js_engine/matchup_worker.js` — should appear in game loop
- `grep -n "m_actionLabels" source/gui/GUIState_Play.cpp` — should appear in drawReplayHUD
- `grep -n "jumpToNextTurn\|jumpToPrevTurn" source/gui/GUIState_Play.cpp` — both methods exist
