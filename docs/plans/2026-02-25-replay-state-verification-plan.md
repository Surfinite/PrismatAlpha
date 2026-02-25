# Replay State Verification Plan — AS3 Ground Truth Comparison

**Goal:** Build an automated system that verifies the C++ engine produces identical game states to the live Prismata AS3 engine, using the replay viewer + F6 state capture as ground truth.

**Why this matters:** The existing replay oracle only validates action _legality_ (can our engine accept move X?). It does NOT verify that the game _state_ matches. Bugs that make more moves legal (e.g., the defense-reset bug) pass validation silently. True verification requires comparing intermediate game states against the AS3 engine.

**Approach:** Capture F6 state snapshots at every turn boundary from the Prismata client's replay viewer (AS3 ground truth), then compare against C++ engine state dumps from the same replay.

---

## Phase 0: Documentation Discovery (COMPLETE)

### Allowed APIs & Infrastructure

**F6 Capture (Python, existing):**
- `_send_f6_to_prismata()` — `tools/prismata_sniffer.py:1123-1148`. SendInput with VK_F6=0x75. Focus steal: SetForegroundWindow + 50ms + SendInput + 50ms + restore.
- `_read_clipboard_win32()` — `tools/prismata_sniffer.py:1276-1296`. Win32 API: OpenClipboard → GetClipboardData(CF_UNICODETEXT=13) → GlobalLock → wstring_at.
- `_sanitize_gamestate()` — `tools/prismata_sniffer.py:1306-1344`. Brace-matching extractor for F6 JSON (handles both full F6 and Shift+F6 formats).
- `_looks_like_gamestate()` — `tools/prismata_sniffer.py:1299-1303`. Validator: len>50 AND ("CurrentInfo" OR "gameState") AND "mergedDeck".
- Hash-and-wait pattern — `tools/prismata_sniffer.py:1510-1521`. Snapshot clipboard, send F6, poll 100ms intervals, 1s timeout, check hash changed AND valid gamestate.

**Keyboard Automation (Python, to build):**
- Shift+Right = next turn in replay viewer. VK_SHIFT=0x10, VK_RIGHT=0x27.
- Pattern: Send 4 INPUT structs (Shift down, Right down, Right up, Shift up) via SendInput.
- Replay stepping is **client-side only** — no server messages, state updates instantly.
- F6 can be sent immediately after Shift+Right (add 100-150ms safety delay).
- Source: `prismata_decompiled/scripts/starlingUI/game/UIReplayControl.as:75-83`.

**Replay Loading (Python, via sniffer injection):**
- `session._inject_msg(["MenuReplay", code])` — sends replay request to server.
- Server responds with `BeginMenuReplay` containing full replay data.
- Only works from lobby/menu (not during active game).
- Source: `prismata_decompiled/scripts/starlingUI/lobby/lobbyPages/UIReplayCodePage.as:79-83`.

**C++ State Serialization (existing):**
- `GameState::toJSONString()` — `source/engine/GameState.cpp:2850-2958`. Outputs: whiteMana, blackMana, turn (active player), numTurns, phase, cards (buyable, UI names), supply arrays, table (Card::toJSONString per unit).
- `Card::toJSONString()` — `source/engine/Card.cpp:1019-1082`. Outputs: owner, cardName (**internal name**, e.g., "Tesla Tower"), health, disruptDamage (chill), deadness, role, constructionTime, charge, delay, lifespan, blocking.
- `GameState::debugStateHash()` — `source/engine/GameState.cpp:2430-2469`. XOR hash of: turn, player, phase, game-over, resources (6×2), stagnation (4×2), card states.
- `ReplayStepper` — `source/testing/ReplayStepper.h/cpp`. Steps through S3 replay JSONs turn-by-turn. `getState()` returns current GameState. `advanceTurn()` progresses.

**C++ CLI (existing):**
- `--analyze <file>` — uses ReplayStepper, has `stepper.getState()` at each turn (Benchmarks.cpp:1719). Currently does AI search per turn (slow). State is accessible but not dumped.
- `--validate-replay <file> --validate-output <file>` — dumps full state JSONL after each turn, but requires pre-converted validation JSON format.

### Critical Name Mapping Issue

**C++ `Card::toJSONString()` uses `getType().getName()`** → internal names (e.g., "Tesla Tower", "Brooder")
**F6 JSON from AS3 uses display names** (e.g., "Tarsier", "Blastforge")
**C++ `GameState::toJSONString()` uses `getUIName()`** for buyable cards list → display names

The comparison tool must map between these. Full 105-unit mapping is in `bin/asset/config/cardLibrary.jso`.

### Anti-Patterns to Avoid

- Do NOT assume F6 JSON keys match C++ JSON keys exactly (they're close but differ in naming).
- Do NOT send F6 during an active game — only during replay viewing or lobby.
- Do NOT inject MenuReplay while already in a game (only works from lobby).
- Do NOT use `_parse_f6_state()` from sniffer — it's a summary parser that loses detail. Parse the raw gameState JSON directly.
- Do NOT modify `Card::toJSONString()` to use UI names — that would break existing validation output. Handle mapping in Python comparison tool.

---

## Phase 1: C++ State Dump Mode (`--dump-states`)

**Objective:** Add a new CLI mode that processes a replay and outputs full game state at every turn boundary — fast, no AI search.

### Tasks

1. **Add `--dump-states` CLI argument** to `source/testing/main.cpp`
   - Copy the `--analyze` argument pattern (main.cpp:128-129)
   - New variable: `std::string dumpStatesFile`
   - Parse: `if (std::string(argv[i]) == "--dump-states" && i + 1 < argc) dumpStatesFile = argv[++i];`
   - Add `--dump-output` for output file (default: `state_dump.jsonl`)
   - Call: `Benchmarks::DoDumpStates(dumpStatesFile, dumpOutputFile)`

2. **Implement `Benchmarks::DoDumpStates()`** in `source/testing/Benchmarks.cpp`
   - Copy the replay-loading setup from `DoAnalyze()` (lines 1570-1695): mergedDeck parsing, initInfo, commandInfo, ReplayStepper init
   - Strip out ALL AI search, neural eval, move comparison logic
   - Per-turn loop:
     ```cpp
     while (stepper.hasNextTurn()) {
         const GameState & state = stepper.getState();
         int turn = stepper.getCurrentTurn();
         int player = (int)stepper.getActivePlayer();
         uint64_t hash = state.debugStateHash();
         std::string stateJson = state.toJSONString();

         // Write JSONL line
         fprintf(out, "{\"turn\":%d,\"player\":%d,\"hash\":\"%016llx\",\"state\":%s}\n",
                 turn, player, hash, stateJson.c_str());

         stepper.advanceTurn();
     }
     ```
   - Also output an initial state line (turn -1) before the loop
   - Output a final summary line: `{"total_turns": N, "final_hash": "...", "game_over": true/false}`

3. **Add declaration** to `source/testing/Benchmarks.h`
   - `static void DoDumpStates(const std::string & replayFile, const std::string & outputFile);`

### Verification Checklist

- [ ] `Prismata_Testing.exe --dump-states bin/replays_test/XXXXX.json --dump-output test_dump.jsonl` produces JSONL output
- [ ] Each line is valid JSON with keys: turn, player, hash, state
- [ ] `state` object contains: whiteMana, blackMana, turn, numTurns, phase, cards, table
- [ ] Table entries have: owner, cardName (internal name), health, disruptDamage, role, constructionTime, charge, delay, lifespan
- [ ] Turn count matches replay length (grep `"turn":` | wc -l should be ~N turns)
- [ ] No AI search time overhead — should complete in <0.5s per replay
- [ ] Build succeeds in both Debug and Release configurations

### Anti-Pattern Guards

- Do NOT add AI search or neural eval — this mode is pure state extraction
- Do NOT change the ReplayStepper init pattern — copy exactly from DoAnalyze
- Do NOT use cout for JSONL output — use fprintf to output file (stdout has init noise)
- Do NOT forget to close the output file

---

## Phase 2: F6 Ground Truth Capture Tool

**Objective:** Build a Python tool that automates the Prismata client's replay viewer to capture F6 game state at every turn boundary.

### Prerequisites
- Prismata client running with SWF dev mode patch
- Sniffer proxy running (`python tools/prismata_sniffer.py proxy`)
- Client connected through proxy (hosts in proxy mode)
- Client in lobby (not in a game)

### Tasks

1. **Create `tools/capture_replay_states.py`** — standalone tool (not part of sniffer)
   - Copy Win32 infrastructure from `tools/prismata_autopilot.py:80-167`:
     - `_KEYBDINPUT`, `_INPUT` structures
     - `_find_prismata_hwnd()`
     - `_read_clipboard_win32()` (= `_get_clipboard_text()`)
     - `_looks_like_gamestate()`
     - `_sanitize_gamestate()` (copy from `tools/prismata_sniffer.py:1306-1344`)
   - Add new function `_send_shift_right()`:
     ```python
     def _send_shift_right():
         """Send Shift+Right Arrow to Prismata (next turn in replay viewer)."""
         VK_SHIFT, VK_RIGHT = 0x10, 0x27
         hwnd = _find_prismata_hwnd()
         if not hwnd: return False
         user32 = ctypes.windll.user32
         prev = user32.GetForegroundWindow()
         user32.SetForegroundWindow(hwnd)
         time.sleep(0.05)
         inputs = (_INPUT * 4)(
             _INPUT(type=1, ki=_KEYBDINPUT(wVk=VK_SHIFT, dwFlags=0)),
             _INPUT(type=1, ki=_KEYBDINPUT(wVk=VK_RIGHT, dwFlags=0)),
             _INPUT(type=1, ki=_KEYBDINPUT(wVk=VK_RIGHT, dwFlags=0x0002)),
             _INPUT(type=1, ki=_KEYBDINPUT(wVk=VK_SHIFT, dwFlags=0x0002)),
         )
         user32.SendInput(4, inputs, ctypes.sizeof(_INPUT))
         time.sleep(0.05)
         if prev and prev != hwnd: user32.SetForegroundWindow(prev)
         return True
     ```
   - Add `_send_f6()` — copy from `tools/prismata_sniffer.py:1123-1148`
   - Add `_capture_f6_state()` — hash-and-wait pattern:
     ```python
     def _capture_f6_state(timeout=2.0):
         old = _read_clipboard_win32()
         if not _send_f6(): return None
         deadline = time.time() + timeout
         while time.time() < deadline:
             time.sleep(0.1)
             new = _read_clipboard_win32()
             if new != old and _looks_like_gamestate(new):
                 return _sanitize_gamestate(new)
             time.sleep(0.1)
         return None
     ```

2. **Main capture loop:**
   ```python
   def capture_replay(max_turns=200, delay_between_turns=0.3):
       """Step through replay in Prismata client, capturing F6 state at each turn."""
       states = []

       # Capture initial state (turn 0)
       initial = _capture_f6_state()
       if initial:
           states.append({"turn": -1, "label": "initial", "f6_json": json.loads(initial)})

       prev_turn = -1
       stall_count = 0
       for step in range(max_turns):
           # Step to next turn
           if not _send_shift_right():
               break
           time.sleep(delay_between_turns)

           # Capture state
           f6_raw = _capture_f6_state()
           if not f6_raw:
               print(f"  Step {step}: F6 capture failed (timeout)")
               stall_count += 1
               if stall_count >= 3:
                   print("  3 consecutive failures — stopping")
                   break
               continue

           stall_count = 0
           data = json.loads(f6_raw)
           gs = data.get("CurrentInfo", data).get("gameState", data)
           current_turn = gs.get("numTurns", -1)

           # Detect end of replay (turn didn't advance)
           if current_turn == prev_turn:
               print(f"  Turn {current_turn} repeated — end of replay")
               break

           prev_turn = current_turn
           states.append({
               "turn": current_turn,
               "player": gs.get("turn", -1),  # active player (confusing name)
               "f6_json": data
           })
           print(f"  Turn {current_turn} (P{gs.get('turn',0)+1}) captured")

       return states
   ```

3. **CLI interface:**
   ```
   python tools/capture_replay_states.py --output states_XXXXX.json [--max-turns 200] [--delay 0.3]
   ```
   - User manually loads replay in Prismata client first (or we add injection later)
   - Tool captures states from current replay viewer position
   - Outputs JSON array of per-turn F6 states

4. **Optional: Replay injection via sniffer** (Phase 2b, stretch goal)
   - Connect to sniffer's injection API (if exposed) to send `["MenuReplay", code]`
   - Wait for replay to load (detect via F6 showing turn 0 state)
   - This allows fully automated end-to-end: code → capture → output
   - Skip if sniffer API not easily accessible from standalone tool

### Verification Checklist

- [ ] `python tools/capture_replay_states.py --output test_states.json` produces JSON output
- [ ] Each entry has: turn number, active player, full F6 JSON including gameState and mergedDeck
- [ ] Turn numbers are sequential (0, 1, 2, ... N)
- [ ] Tool stops when replay ends (turn number repeats)
- [ ] Tool handles F6 capture failures gracefully (retries, reports, continues)
- [ ] State JSON contains: whiteMana/blackMana (resources), table (unit instances), phase, numTurns
- [ ] Unit entries in table have: cardName (display name), health, role, owner, charge, disruptDamage, constructionTime

### Anti-Pattern Guards

- Do NOT import from prismata_sniffer.py — keep tool standalone (per CLAUDE.md: intentional duplication)
- Do NOT rely on network messages for turn detection — replay viewer is client-side only
- Do NOT use tkinter or any GUI framework — this is a CLI tool
- Do NOT send Shift+Right too fast (< 200ms) — client may not process keyboard events in time
- Do NOT forget to handle the initial state (before any stepping)

---

## Phase 3: State Comparison Tool

**Objective:** Build a Python tool that compares F6 ground truth states against C++ state dumps, producing a detailed mismatch report.

### Tasks

1. **Create `tools/compare_engine_states.py`**

2. **Build name mapping from cardLibrary.jso:**
   ```python
   def load_name_mapping(card_library_path):
       """Build internal_name → display_name mapping from cardLibrary.jso."""
       with open(card_library_path) as f:
           lib = json.load(f)
       mapping = {}
       for card in lib.get("Cards", []):
           internal = card.get("name", "")
           display = card.get("UIName", card.get("uiname", internal))
           if internal and display:
               mapping[internal] = display
       return mapping
   ```
   - Source: `bin/asset/config/cardLibrary.jso` — each card has `name` (internal) and `UIName` (display)

3. **Parse F6 state (AS3 ground truth):**
   ```python
   def parse_f6_state(f6_data):
       """Extract comparable state from F6 JSON."""
       gs = f6_data.get("CurrentInfo", f6_data).get("gameState", f6_data)
       state = {
           "turn": gs.get("numTurns"),
           "active_player": gs.get("turn"),  # confusing: "turn" = active player
           "phase": gs.get("phase", ""),
           "resources": [gs.get("whiteMana", "0"), gs.get("blackMana", "0")],
           "units": []
       }
       for unit in gs.get("table", []):
           state["units"].append({
               "name": unit.get("cardName", ""),  # display name
               "owner": unit.get("owner", -1),
               "health": unit.get("health", 0),
               "chill": unit.get("disruptDamage", 0),
               "role": unit.get("role", ""),
               "charge": unit.get("charge", 0),
               "construction": unit.get("constructionTime", 0),
               "delay": unit.get("delay", 0),
               "lifespan": unit.get("lifespan", 0),
               "dead": unit.get("deadness", "alive"),
           })
       # Sort units for order-independent comparison
       state["units"].sort(key=lambda u: (u["owner"], u["name"], u["health"]))
       return state
   ```

4. **Parse C++ state dump:**
   ```python
   def parse_cpp_state(cpp_state, name_map):
       """Extract comparable state from C++ JSONL state dump. Maps internal→display names."""
       st = cpp_state.get("state", cpp_state)
       state = {
           "turn": st.get("numTurns"),
           "active_player": st.get("turn"),
           "phase": st.get("phase", ""),
           "resources": [st.get("whiteMana", "0"), st.get("blackMana", "0")],
           "units": []
       }
       for unit in st.get("table", []):
           internal_name = unit.get("cardName", "")
           display_name = name_map.get(internal_name, internal_name)
           state["units"].append({
               "name": display_name,  # mapped to display name
               "owner": unit.get("owner", -1),
               "health": unit.get("health", 0),
               "chill": unit.get("disruptDamage", 0),
               "role": unit.get("role", ""),
               "charge": unit.get("charge", 0),
               "construction": unit.get("constructionTime", 0),
               "delay": unit.get("delay", 0),
               "lifespan": unit.get("lifespan", 0),
               "dead": unit.get("deadness", "alive"),
           })
       state["units"].sort(key=lambda u: (u["owner"], u["name"], u["health"]))
       return state
   ```

5. **Comparison function:**
   ```python
   def compare_states(f6_state, cpp_state, turn):
       """Compare two normalized states. Returns list of mismatches."""
       mismatches = []

       # Top-level fields
       for field in ["active_player", "phase"]:
           if f6_state[field] != cpp_state[field]:
               mismatches.append({"turn": turn, "field": field,
                                  "f6": f6_state[field], "cpp": cpp_state[field]})

       # Resources
       for i, label in enumerate(["P1", "P2"]):
           if f6_state["resources"][i] != cpp_state["resources"][i]:
               mismatches.append({"turn": turn, "field": f"resources_{label}",
                                  "f6": f6_state["resources"][i], "cpp": cpp_state["resources"][i]})

       # Unit count
       if len(f6_state["units"]) != len(cpp_state["units"]):
           mismatches.append({"turn": turn, "field": "unit_count",
                              "f6": len(f6_state["units"]), "cpp": len(cpp_state["units"])})
           return mismatches  # Can't do per-unit comparison with different counts

       # Per-unit comparison (sorted, so index-aligned)
       for i, (f6u, cppu) in enumerate(zip(f6_state["units"], cpp_state["units"])):
           for field in ["name", "owner", "health", "chill", "role", "charge",
                         "construction", "delay", "lifespan", "dead"]:
               if f6u[field] != cppu[field]:
                   mismatches.append({"turn": turn, "field": f"unit[{i}].{field}",
                                      "unit": f6u["name"], "f6": f6u[field], "cpp": cppu[field]})

       return mismatches
   ```

6. **CLI interface:**
   ```
   python tools/compare_engine_states.py \
       --f6 states_XXXXX.json \
       --cpp state_dump_XXXXX.jsonl \
       --card-library bin/asset/config/cardLibrary.jso \
       [--output comparison_report.json]
   ```
   - Align states by turn number
   - Report per-turn match/mismatch
   - Summary: total turns, matching turns, first mismatch turn, mismatch categories

### Verification Checklist

- [ ] Tool loads both F6 and C++ state files without errors
- [ ] Name mapping correctly converts internal → display names (spot-check: "Tesla Tower" → "Tarsier")
- [ ] When run on identical states, reports 0 mismatches
- [ ] When states differ (manually edit one field), correctly identifies the mismatch field
- [ ] Summary output shows: total_turns, matching_turns, mismatch_count, first_mismatch_turn
- [ ] Unit comparison is order-independent (sorted by owner+name+health)

### Anti-Pattern Guards

- Do NOT assume unit ordering matches between F6 and C++ — always sort before comparing
- Do NOT compare `blocking` field — F6 may have stale values (per docs)
- Do NOT compare `instId` — C++ assigns IDs differently than the client
- Do NOT hardcode name mappings — load dynamically from cardLibrary.jso
- Do NOT compare supply arrays without careful alignment — card ordering may differ

---

## Phase 4: End-to-End Validation Runner

**Objective:** Orchestrate the full pipeline: select replays → C++ state dump → F6 capture → compare → report.

### Tasks

1. **Create `tools/validate_engine_states.py`** — orchestrator script
   ```
   python tools/validate_engine_states.py \
       --replays replay_code1 replay_code2 ... \
       [--replay-file codes.txt] \
       --exe bin/Prismata_Testing.exe \
       --output validation_results/ \
       [--skip-f6]  # Use existing F6 captures, skip live capture
   ```

2. **Per-replay pipeline:**
   - Download replay JSON from S3 (if not cached): `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz`
   - Run C++ state dump: `Prismata_Testing.exe --dump-states replay.json --dump-output states.jsonl`
   - If not `--skip-f6`: Prompt user to load replay in client, then run F6 capture
   - Run comparison tool
   - Aggregate results

3. **Batch summary report:**
   ```json
   {
     "total_replays": 10,
     "fully_matching": 7,
     "mismatching": 3,
     "total_turns_compared": 483,
     "total_mismatches": 12,
     "mismatch_categories": {
       "resources": 5,
       "unit.health": 3,
       "unit.role": 2,
       "phase": 2
     },
     "per_replay": [...]
   }
   ```

4. **Curated test set selection:**
   - Pick 10-20 replays covering diverse scenarios:
     - Simple games (Drone/Engi/Tarsier only)
     - Games with targeting abilities (Rhino, Drake, Scorchilla)
     - Games with death scripts (Centurion, Valkyrion)
     - Games with chill (Frostbite, Shiver Yeti)
     - Games ending by breach, stagnation, resignation
     - Short games (<15 turns) and long games (>40 turns)
   - Store codes in `tools/data/verification_test_replays.txt`

### Verification Checklist

- [ ] Full pipeline runs end-to-end on at least 1 replay
- [ ] C++ state dump + F6 capture + comparison all produce expected output files
- [ ] Batch summary aggregates results correctly
- [ ] Report identifies specific divergence points (turn number + field)
- [ ] Results saved to `validation_results/` directory

### Anti-Pattern Guards

- Do NOT run F6 capture automatically without user confirmation — the client must be in the right state
- Do NOT download replays without URL-encoding special characters (+ → %2B, @ → %40)
- Do NOT assume all replays will work — some may fail in ReplayStepper (handle gracefully)

---

## Phase 5: Regression Test Integration

**Objective:** Make state verification a reusable regression test for future engine changes.

### Tasks

1. **Store F6 ground truth permanently:**
   - After initial capture of 10-20 replays, save F6 states to `tools/data/f6_ground_truth/`
   - These become permanent reference — don't need to re-capture unless AS3 engine changes

2. **Quick regression mode:**
   ```
   python tools/validate_engine_states.py --regression --exe bin/Prismata_Testing.exe
   ```
   - Uses stored F6 ground truth (no live capture needed)
   - Runs C++ state dump on all test replays
   - Compares against stored ground truth
   - Pass/fail with summary

3. **CI integration potential:**
   - Store test replay JSONs in repo (small, ~5-50KB each)
   - Store F6 ground truth in repo
   - Add to build verification: after engine changes, run regression

4. **Document the verification system:**
   - Add to CLAUDE.md under a new "Engine State Verification" section
   - Document the ground truth capture process
   - Document how to add new test replays

### Verification Checklist

- [ ] Regression mode runs without requiring Prismata client
- [ ] Detects intentional state changes (e.g., revert a port fix, verify it catches the difference)
- [ ] Ground truth files committed to repo
- [ ] Documentation updated

---

## Timing Estimates

| Phase | Effort | Dependencies |
|-------|--------|-------------|
| Phase 1: C++ --dump-states | Small (copy from --analyze, strip AI) | None |
| Phase 2: F6 capture tool | Medium (new tool, keyboard automation) | Prismata client running |
| Phase 3: Comparison tool | Medium (name mapping, field comparison) | Phase 1 + Phase 2 output |
| Phase 4: E2E runner | Small (orchestration, shell out to tools) | Phases 1-3 |
| Phase 5: Regression | Small (store ground truth, add --regression) | Phase 4 complete |

**Recommended execution order:** Phase 1 → Phase 3 (can develop with manual test data) → Phase 2 → Phase 4 → Phase 5

**Quick win:** Phase 1 alone gives us C++ state dumps we can manually inspect. Even without F6 automation, we can manually capture a few F6 states and compare by eye to validate the approach.

---

## Known Limitations

1. **F6 doesn't include stagnation counters** — can't verify the stagnation system via F6. Would need AS3 source analysis or specialized test cases.
2. **F6 timing at phase boundaries** — capturing during phase transitions may show inconsistent phases. Capture at start of Action phase (after swoosh) is safest.
3. **Dead unit inclusion** — F6 includes dead units in the table. C++ `toJSONString()` also includes them. But filtering dead units from comparison may reduce noise.
4. **Lifespan encoding** — C++ outputs -1 when lifespan=0 (no limit). F6 may output 0. Need to normalize in comparison.
5. **Name mapping edge cases** — Some units may have identical internal and display names. The mapping handles this (maps to self).
6. **Replay viewer automation is sequential** — ~0.5s per turn (step + F6 + poll). A 60-turn game takes ~30s. Not fast, but acceptable for 10-20 test replays.
