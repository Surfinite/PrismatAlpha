# SWF Modification Plan: Remove Dummy Game + Auto-Spectate

**Created:** Feb 24, 2026
**Status:** DRAFT
**Goal:** Edit Prismata.swf to (1) remove the dummy "DerpyMcLongName" game from Top Live Games, and (2) add F8 auto-spectate functionality directly in the SWF.

---

## Phase 0: Documentation Discovery (COMPLETE)

### Findings

#### Dummy Game Source (CRITICAL)
- **File:** `prismata_decompiled/scripts/client/LocalUser.as:664-673`
- The dummy game is pushed into `topGames` vector ONLY when `FlashBuildOptions.developerVersion == true`
- It's 10 lines of code inside an `if` block at the end of `topGamesUpdated()`
- The dummy has NO `gameid` field (undefined) — clicking it sends `ObserveTopGame(undefined)` to server
- Ratings are 333/444 (bogus) — score-based sorting puts it LAST in the list

#### How Spectating Works (INTERNAL vs EXTERNAL)
- **Internal call:** `Client.sayToServer("ObserveTopGame", gameid)` (UIFeaturedGameButton.as:285)
- Server responds with `BeginGame` message
- `GameDispatcher.beginGame()` (GameDispatcher.as:93) handles it — creates `MultiplayerGame`, transitions to game screen
- **CRITICAL INSIGHT:** Internal `sayToServer()` WORKS for GUI transition. External TCP injection does NOT (client state machine not ready). So adding the call INSIDE the SWF will work.

#### Keyboard Architecture
- `UIKeyboard.as:37-136` — F8 is in the switch statement (line 88) but has no special handler
- F6 handler is inside `if(FlashBuildOptions.developerVersion)` block (lines 122-135) — same pattern for F8
- `pressedEvent()` dispatches `KeyEvent.sayJustPressed(Key.F8, data)` — any component can listen

#### Game-Over Flow
- `GameOverAction.lobby()` fires `UIEvent.say(UIEvent.LEAVE_GAME)` (GameOverAction.as:64)
- `Game.leaveGame()` handles LEAVE_GAME — cleans up game, returns to lobby (Game.as:1072)
- `MultiplayerGame.leaveGame()` overrides — plays sound, sends QuitGame to server (MultiplayerGame.as:449)

#### JPEXS FFDec Capabilities (v25.0.0)
- **`-export script:pcode`** — exports P-code (AVM2 bytecode text representation)
- **`-export script:as`** — exports decompiled AS3 source
- **`-importScript <in.swf> <out.swf> <scripts_dir>`** — imports modified .as files (has built-in compiler)
- **`-replace <in> <out> <scriptName> <file> script:pcode <methodIndex>`** — replaces specific method P-code
- **`-dumpAS3`** — lists all scripts and method body indices
- **`-air`** flag — use AIR global SWC (Prismata is an AIR app, likely needed)
- Installed at `C:\Program Files (x86)\FFDec\`

#### Allowed APIs (from AS3 source)
| API | Location | Purpose |
|-----|----------|---------|
| `Client.sayToServer("ObserveTopGame", gameid)` | UIFeaturedGameButton.as:285 | Start spectating a game |
| `Client.localUser.topGames` | LocalUser.as:100 | Vector.\<GameStub\> of live games |
| `UIEvent.say(UIEvent.LEAVE_GAME)` | GameOverAction.as:64 | Leave game and return to lobby |
| `UIEvent.say(UIEvent.FEATURED_GAMES_UPDATED)` | LocalUser.as:674 | Notify UI of new game list |
| `FlashBuildOptions.developerVersion` | FlashBuildOptions.as:50 | Dev mode gate (our SWF patch) |
| `KeyEvent.sayJustPressed(Key.F8, data)` | UIKeyboard.as:184 | F8 key event dispatch |

#### Anti-Patterns
- **DO NOT inject ObserveTopGame via TCP proxy** — server processes it but client GUI doesn't transition
- **DO NOT modify FlashBuildOptions.developerVersion itself** — needed for F6 clipboard, other dev tools
- **DO NOT use `-importScript` without `-air` flag** — Prismata is AIR, needs AIR globals for compilation
- **DO NOT assume method body index** — always verify with `-dumpAS3` first

---

## Phase 1: JPEXS Tooling Verification & P-code Export

**Goal:** Verify we can export, modify, and re-import code into the SWF without breaking it.

### Tasks

1. **Export all AS3 script names:**
   ```bash
   "C:\Program Files (x86)\FFDec\ffdec-cli.exe" -dumpAS3 "C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf" > swf_dump.txt
   ```
   Find `client.LocalUser` and `starlingUI.UIKeyboard` — note their script indices and method body indices.

2. **Export P-code for target methods:**
   ```bash
   # Export all P-code
   "C:\Program Files (x86)\FFDec\ffdec-cli.exe" -format script:pcode -export script C:\tmp_pcode_export "C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf"
   ```
   Find and save:
   - `client/LocalUser.as` P-code → examine `topGamesUpdated` method
   - `starlingUI/UIKeyboard.as` P-code → examine `keyPressed` method

3. **Round-trip test (no changes):**
   - Copy SWF to working copy: `Prismata_test.swf`
   - Import unchanged P-code back:
     ```bash
     "C:\Program Files (x86)\FFDec\ffdec-cli.exe" -replace Prismata_test.swf Prismata_roundtrip.swf "client.LocalUser" LocalUser_pcode.txt script:pcode <methodIndex>
     ```
   - Compare file sizes (should be identical or nearly identical)
   - Launch and verify game still works

4. **Identify the dummy game block in P-code:**
   In the P-code for `topGamesUpdated`, look for:
   - `getlex FlashBuildOptions` followed by `getproperty developerVersion`
   - An `iffalse` jump (this jumps PAST the dummy game block)
   - The target label of `iffalse` = where execution resumes after the block
   - Between the `iffalse` and the target: the "DerpyMcLongName" string constant ref, `newobject`, `constructprop GameStub`, `callpropvoid push`

### Verification Checklist
- [ ] `-dumpAS3` output captured with script names and indices
- [ ] P-code exported for both LocalUser and UIKeyboard
- [ ] Dummy game block identified in P-code (annotated with comments)
- [ ] Round-trip test passes (game launches, no crashes)
- [ ] Method body indices for both target methods documented

### Deliverables
- `swf_dump.txt` — full script listing
- `C:\tmp_pcode_export\` — exported P-code files
- Notes documenting: method body indices, dummy game block line range in P-code

---

## Phase 2: Remove Dummy Game from SWF

**Goal:** Patch `LocalUser.topGamesUpdated()` to skip the dummy game insertion. Dev mode features (F6, etc.) remain intact.

### Approach A: AS3 Source Edit (Try First — Simplest)

1. **Copy the decompiled source** for LocalUser.as
2. **Delete lines 664-673** (the entire `if(FlashBuildOptions.developerVersion)` block in `topGamesUpdated`)
3. **Import via JPEXS:**
   ```bash
   # Create scripts directory matching package structure
   mkdir -p C:\tmp_swf_scripts\client
   cp modified_LocalUser.as C:\tmp_swf_scripts\client\LocalUser.as

   # Import (try with -air flag for AIR app)
   "C:\Program Files (x86)\FFDec\ffdec-cli.exe" -air -importScript \
     "C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf" \
     Prismata_patched.swf \
     C:\tmp_swf_scripts\
   ```
4. **If compilation fails** (missing types, AIR imports), fall back to Approach B.

### Approach B: P-code Edit (Reliable Fallback)

1. **In the P-code for `topGamesUpdated`**, find the block:
   ```
   ; if(FlashBuildOptions.developerVersion)
   getlex QName(PackageNamespace(""),"FlashBuildOptions")
   getproperty QName(PackageNamespace(""),"developerVersion")
   iffalse ofs0XXX   ; jump to after the block
   ; ... dummy game creation code ...
   ofs0XXX:           ; target label
   ```

2. **Patch: Change `iffalse` to `jump`** (unconditional):
   Replace:
   ```
   iffalse ofs0XXX
   ```
   With:
   ```
   jump ofs0XXX
   pop   ; balance the stack (remove the boolean from getproperty)
   ```

   OR simpler — replace `getproperty developerVersion` + `iffalse` with `pop` + `jump`:
   ```
   ; Before: getlex FlashBuildOptions / getproperty developerVersion / iffalse
   ; After:  getlex FlashBuildOptions / pop / jump ofs0XXX
   ```
   This avoids stack imbalance.

3. **Re-import the modified P-code:**
   ```bash
   "C:\Program Files (x86)\FFDec\ffdec-cli.exe" -replace \
     Prismata.swf Prismata_patched.swf \
     "client.LocalUser" modified_topGamesUpdated.pcode script:pcode <methodBodyIndex>
   ```

### Approach C: Binary Byte Patch (Simplest If Offset Found)

If we can locate the `iffalse` instruction byte offset in the decompressed SWF:
1. The `iffalse` opcode in AVM2 is `0x12` followed by a 3-byte signed offset
2. Change `0x12` to `0x10` (unconditional `jump`)
3. Add this offset to the Python patcher alongside the existing dev mode patch

This is the same approach as the existing dev mode patch. Finding the offset requires:
- Searching for the "DerpyMcLongName" string in the SWF constant pool
- Tracing back to the method body that references it
- Finding the `iffalse` instruction before the reference

### Verification Checklist
- [ ] Patched SWF launches without crash
- [ ] Watch tab shows ONLY real games (no DerpyMcLongName)
- [ ] F6 clipboard export still works (dev mode intact)
- [ ] Game navigation and lobby work normally
- [ ] Sniffer proxy mode still connects through patched SWF
- [ ] TopGamesUpdate in sniffer log shows only real games

### Deliverables
- Patched `Prismata.swf` with dummy game removed
- Documentation of which approach worked (A, B, or C)
- The exact edit applied (for reproduction)

---

## Phase 3: F8 Auto-Spectate Handler

**Goal:** Press F8 to instantly spectate the highest-rated live game. Press F8 again during spectating to leave and return to lobby.

### Why This Works
The INTERNAL `Client.sayToServer("ObserveTopGame", gameid)` call triggers the full client state machine:
1. Server receives ObserveTopGame → sends BeginGame
2. `GameDispatcher.beginGame()` handles it → creates MultiplayerGame → transitions to game screen
3. Client GUI properly enters spectator mode

This is different from external TCP injection (which bypasses the client state machine).

### Implementation

Add to `UIKeyboard.keyPressed()` inside the existing `if(FlashBuildOptions.developerVersion)` block (after the F6 handler at line 134):

```actionscript
// Auto-spectate on F8
if(e.keyCode == Key.F8)
{
    // If currently in a game, leave it
    if(Client.game != null)
    {
        UIEvent.say(UIEvent.LEAVE_GAME);
    }
    else
    {
        // In lobby — spectate the first available game
        if(Client.localUser && Client.localUser.topGames && Client.localUser.topGames.length > 0)
        {
            Client.sayToServer("ObserveTopGame", Client.localUser.topGames[0].gameid);
        }
    }
}
```

### P-code Implementation

The AS3 above translates to approximately this P-code (will need exact multiname references from the SWF dump):

```
; if(e.keyCode == Key.F8)
getlocal1                          ; e (KeyboardEvent parameter)
getproperty keyCode
getlex Key
getproperty F8
ifne skip_f8                       ; jump if not F8

; if(Client.game != null)
getlex Client
getproperty game
pushnull
ifstricteq no_game                 ; jump if game == null

; UIEvent.say(UIEvent.LEAVE_GAME)
getlex UIEvent
getlex UIEvent
getproperty LEAVE_GAME
callpropvoid say 1
jump skip_f8

no_game:
; if(Client.localUser && Client.localUser.topGames && Client.localUser.topGames.length > 0)
getlex Client
getproperty localUser
iffalse skip_f8
getlex Client
getproperty localUser
getproperty topGames
iffalse skip_f8
getlex Client
getproperty localUser
getproperty topGames
getproperty length
pushbyte 0
ifle skip_f8

; Client.sayToServer("ObserveTopGame", Client.localUser.topGames[0].gameid)
getlex Client
pushstring "ObserveTopGame"
getlex Client
getproperty localUser
getproperty topGames
pushbyte 0
getproperty []                     ; topGames[0]
getproperty gameid
callpropvoid sayToServer 2

skip_f8:
```

### Approach

1. **Try AS3 source import first** — modify the decompiled `UIKeyboard.as`, add the F8 block after line 134, import via `-importScript`
2. **If that fails**, construct the P-code manually using the exported P-code as template (copy the F6 handler pattern, adapt for F8)
3. **Insert the P-code** into the `keyPressed` method body using `-replace`

### Required Imports (for AS3 compilation)
The F8 handler references:
- `client.Client` (already imported in UIKeyboard context via `pressedEvent` dispatch chain)
- `starlingUI.UIEvent` (already used for F6 handler)
- `client.Game` (already imported)

Check if these are accessible from `UIKeyboard.as` context. If not, the P-code approach bypasses import issues (uses `getlex` for any class).

### Verification Checklist
- [ ] F8 in lobby with live games → enters spectator mode for highest-rated game
- [ ] F8 in lobby with NO live games → nothing happens (no crash)
- [ ] F8 while spectating → returns to lobby
- [ ] F8 while in game-over screen → returns to lobby
- [ ] F6 still works (no regression)
- [ ] Normal game flow unaffected (ranked, casual, etc.)

---

## Phase 4: Game-Over Auto-Cycle (STRETCH GOAL)

**Goal:** After a spectated game ends, automatically leave and spectate the next available game — full hands-free looping.

### Approach Options

#### Option A: Timer-Based (In SWF)
Add a static boolean + event listener:
```actionscript
// In a new utility class or added to an existing one
public static var autoSpectateEnabled:Boolean = false;

// Listen for game-over
UIEvent.listen(UIEvent.GAME_OVER, function():void {
    if(autoSpectateEnabled) {
        // Delay 3 seconds, then leave and re-spectate
        Starling.juggler.add(new DelayedCall(function():void {
            UIEvent.say(UIEvent.LEAVE_GAME);
            // After lobby loads, spectate again
            Starling.juggler.add(new DelayedCall(function():void {
                if(Client.localUser.topGames && Client.localUser.topGames.length > 0) {
                    Client.sayToServer("ObserveTopGame", Client.localUser.topGames[0].gameid);
                }
            }, 2));
        }, 3));
    }
});
```

**Complexity:** HIGH — requires adding new event listeners and timer callbacks in P-code. Anonymous functions in P-code are represented as separate method bodies with closure scoping.

#### Option B: Keep Sniffer for Cycling (RECOMMENDED)
With the dummy game removed (Phase 2), the sniffer's existing click-based auto-cycle works reliably:
- Sniffer detects GameOver → waits → clicks center screen to dismiss
- Clicks Watch tab → clicks game card (which is now ALWAYS a real game)
- No SWF modification needed for cycling

#### Option C: Hybrid — F8 Toggle + Sniffer Cycle
- F8 in SWF sets a flag and spectates first game (Phase 3)
- Sniffer detects game-over and presses F8 via SendInput
- F8 handler in SWF leaves game and re-spectates
- Best of both worlds: SWF handles the reliable part, sniffer handles the timing

### Recommendation
Start with **Option B** (sniffer handles cycling with dummy game removed). If the click timing is still unreliable, implement **Option C** (sniffer sends F8 keystroke, SWF handles it). Option A is the cleanest but most complex — defer unless the others prove insufficient.

### Verification Checklist (if implemented)
- [ ] Game ends → automatic transition to next game within 5 seconds
- [ ] Works when multiple games are live
- [ ] Works when only 1 game is live (re-spectates same game)
- [ ] Handles edge case: no games live after current game ends
- [ ] F8 press during auto-cycle disables/stops the loop

---

## Phase 5: Python Automation Script

**Goal:** Create a script that applies all SWF patches (dev mode + dummy removal + F8 handler) programmatically.

### Implementation

Create `tools/patch_swf_autospectate.py`:

```python
"""
Patch Prismata.swf for auto-spectate functionality:
1. Enable developer mode (existing byte patch at 0x1580196)
2. Remove dummy game from Top Live Games
3. Add F8 auto-spectate handler
"""

import subprocess, shutil, os, sys

FFDEC_CLI = r"C:\Program Files (x86)\FFDec\ffdec-cli.exe"
SWF_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf",
    # Add other Steam library paths
]

def find_swf():
    """Find Prismata.swf in standard locations."""
    ...

def backup_swf(swf_path):
    """Create backup if not exists."""
    ...

def apply_dev_mode_patch(swf_path):
    """Apply the 0x1580196 byte patch (pushfalse → pushtrue)."""
    # Reuse existing logic from replay_capture.py
    ...

def apply_dummy_game_removal(swf_path):
    """Use JPEXS CLI to remove dummy game block from topGamesUpdated."""
    # Approach depends on Phase 2 findings
    ...

def apply_f8_handler(swf_path):
    """Use JPEXS CLI to add F8 auto-spectate to keyPressed."""
    # Approach depends on Phase 3 findings
    ...

def restore_swf(swf_path):
    """Restore from backup."""
    ...
```

### Integration with Existing Workflow
- `replay_capture.py` already patches SWF + manages hosts file + starts sniffer
- This script should be callable from `replay_capture.py`
- OR replace the simple byte patch in `replay_capture.py` with a call to this script

### Verification Checklist
- [ ] Script finds SWF in standard Steam locations
- [ ] Creates backup before any modifications
- [ ] All patches applied successfully
- [ ] Restore works correctly
- [ ] Integrates with `replay_capture.py` workflow

---

## Phase 6: End-to-End Verification

### Test Protocol

1. **Backup state:**
   - [ ] Original SWF backed up
   - [ ] Hosts file in correct mode (proxy or direct)

2. **Dummy game removal:**
   - [ ] Launch Prismata with patched SWF
   - [ ] Navigate to Watch tab
   - [ ] Verify ONLY real games shown (no DerpyMcLongName)
   - [ ] Check page counter (should show "X of Y" where Y = real games only)
   - [ ] Verify prev/next cycling works with only real games

3. **F8 functionality (if Phase 3 complete):**
   - [ ] Press F8 in lobby → enters spectator view of live game
   - [ ] Press F8 while spectating → returns to lobby
   - [ ] Press F8 in game-over → returns to lobby
   - [ ] Rapid F8 presses don't crash
   - [ ] F8 with no live games → graceful no-op

4. **Regression checks:**
   - [ ] F6 clipboard export still works
   - [ ] F6 with Shift (AI params) still works
   - [ ] Normal gameplay unaffected (Campaign, Battle, etc.)
   - [ ] Sniffer proxy mode connects and captures traffic
   - [ ] Replay code capture still works
   - [ ] Chat still works

5. **Auto-cycle (if Phase 4 complete):**
   - [ ] Spectated game ends → auto-transitions to next game
   - [ ] Multiple game transitions without manual input

### Rollback Plan
- Restore SWF from backup: `copy Prismata.swf.backup Prismata.swf`
- OR: Steam → Prismata → Properties → Local Files → Verify Integrity

### Known Risks
- JPEXS AS3 compilation may fail on complex classes (LocalUser has many dependencies)
- P-code editing requires exact multiname/namespace references from the SWF dump
- SWF compression changes may alter file size (functionally equivalent)
- Any future Prismata update invalidates all patches (need to re-apply)

---

## Summary

| Phase | Complexity | Priority | Outcome |
|-------|-----------|----------|---------|
| 1. JPEXS Tooling | Low | Required | Verified we can modify the SWF |
| 2. Remove Dummy Game | Medium | **CRITICAL** | Sniffer auto-spectate becomes reliable |
| 3. F8 Auto-Spectate | Medium-High | Nice-to-have | One-press spectate from any screen |
| 4. Auto-Cycle | High | Stretch | Hands-free continuous spectating |
| 5. Python Script | Low | Useful | Reproducible patching workflow |
| 6. Verification | Low | Required | Confidence everything works |

**Critical path:** Phase 1 → Phase 2 → Phase 6 (partial)
**Full path:** Phase 1 → Phase 2 → Phase 3 → Phase 4 (optional) → Phase 5 → Phase 6
