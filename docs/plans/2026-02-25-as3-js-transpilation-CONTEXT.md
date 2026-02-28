# Context Document: AS3 → JavaScript Game Engine Transpilation

## 1. Reviewer Brief

You are receiving two documents:
1. **This context document** — background, architecture, and codebase details
2. **The plan** — `2026-02-25-as3-js-transpilation-plan.md` (AS3 → JS game engine transpilation)

**Your role:** Critically analyze the plan given the context provided. Identify weaknesses, risks, missing considerations, better alternatives, unnecessary complexity, things that should be removed, and things that are good and should be preserved. Suggest additions, potential future features worth considering, and architectural improvements. Be constructively critical — not rubber-stamping.

Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable.

**Important:** You do NOT have direct access to the codebase. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making about the code.

### Review Output Format

1. **One-line verdict**: Your overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess. The plan author will validate these.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

**PrismataAI** is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game by Lunarch Studios. The project trains a neural network evaluation function via self-play, then plugs it into Alpha-Beta / UCT search to play the game at a high level.

**The problem:** The C++ engine has bugs — it only passes 50% of replays when validated against the AS3 ground truth engine (the actual game logic from the live Prismata client). Training data generated on this buggy engine teaches the AI strategies that exploit engine bugs. When engine fixes were applied, the AI's win rate **collapsed from 51.9% to ~11%**. This proves that engine faithfulness is the critical blocker — we cannot generate useful training data until we have a perfectly faithful game engine.

**Current stage:** The AI training pipeline is mature (722K self-play games generated, cloud compute infrastructure built), but ALL existing training data is suspect due to engine bugs. This plan addresses the root cause.

**Key constraints:**
- Solo developer (hobbyist, cost-conscious — previous AWS bill was $805)
- The Lunarch MCDSAI3441.js (1.83MB Emscripten module) is the actual Master Bot AI from the live game — a proven, correct move selector. It's a black box with only 2 API functions.
- The AS3 game engine source is available (decompiled from the game client SWF). It is the ground truth for game rules.
- Target: a Node.js self-play system that pairs a faithful JS game engine with the official Lunarch AI, generating training data on cloud compute.

## 3. Architecture & Tech Stack

### Current Stack
- **C++ game engine** (x86 Windows, Visual Studio) — buggy, 50% replay pass rate
- **Python training pipeline** (PyTorch) — reads binary shard files (7,152 bytes/record, 1,785-dim feature vectors)
- **Self-play infrastructure** — AWS EC2 (Spot), GCP, Azure compute for parallel game generation
- **S3 storage** — centralized data lake for selfplay shards, training results

### Proposed Addition (this plan)
- **JavaScript game engine** — faithful transpilation of AS3 source (~10,600 LOC)
- **MCDSAI3441.js** — official Lunarch AI (Emscripten-compiled C++ → JS), runs in Node.js
- **Node.js orchestration** — game loop, JSONL output
- **Python post-processing** — existing `vectorize.py` converts JSONL → binary shards

### Data Flow

```
┌─────────────────────────────────────────────────────┐
│  selfplay_main.js (Node.js)                          │
│  ┌──────────────┐     ┌──────────────────────────┐  │
│  │ JS Game Engine│◄───►│ MCDSAI3441.js             │  │
│  │ (AS3 port)    │     │ Real Master Bot AI         │  │
│  │               │     │ InitializeAI / GetAIMove   │  │
│  └───────┬───────┘     └──────────────────────────┘  │
│          │                                            │
│          ▼                                            │
│  ┌──────────────┐     ┌──────────────────────────┐  │
│  │ JSONL Output  │────►│ Python vectorize → shards │  │
│  │ (per position)│     │ (existing pipeline)       │  │
│  └──────────────┘     └──────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Game loop:** JS engine manages state → serializes to `State.toString()` JSON → sends to MCDSAI → gets click sequence back → applies clicks via Controller → records position → repeat until game ends.

### Key Architectural Decision: Why Not Fix C++?

The C++ engine has been audited against the AS3 ground truth (22 audit areas checked, 4 fixes applied). Despite fixes, replay pass rate only went from 55.7% to 50.4% (actually regressed — fixes made the engine stricter). The remaining failures are deep semantic differences: script execution ordering, stagnation detection (AS3 has a 4-level progress counter system; C++ has flat 200-turn limit), death scripts, and at least 4 condition types. These are pervasive, cross-cutting concerns that would require essentially rewriting the C++ engine logic. The AS3→JS transpilation is faster and more reliable because the AS3 IS the ground truth.

## 4. Codebase Map

### Directory Structure (relevant portions)

```
PrismataAI/
├── bin/                              # Executables, configs, data
│   └── asset/config/
│       ├── cardLibrary.jso           # Master unit definitions (161 units)
│       ├── config.txt                # AI player definitions, tournament configs
│       └── neural_weights.bin        # Current deployed neural net weights
├── source/                           # C++ engine + AI (existing, NOT touched by this plan)
│   ├── engine/GameState.cpp          # C++ game logic (buggy)
│   ├── ai/NeuralNet.cpp             # Neural net inference
│   └── testing/                     # Tournament runner, self-play data sink
├── training/                         # Python ML pipeline
│   ├── train.py                     # PyTorch training
│   ├── load_selfplay.py             # Binary shard loader
│   ├── vectorize.py                 # Expert JSONL → features (will reuse for JS JSONL)
│   ├── export_weights.py            # PyTorch → C++ weight format
│   ├── schema.json                  # Feature schema (state_dim=1785)
│   └── data/unit_index.json         # 161 canonical unit names
├── prismata_decompiled/             # Decompiled Prismata client source
│   └── scripts/mcds/engine/         # ★ AS3 game engine — THE GROUND TRUTH
│       ├── State.as                 # Core state machine (4,490 LOC)
│       ├── Controller.as            # Click routing (2,574 LOC)
│       ├── Analyzer.as              # Click validation (662 LOC)
│       ├── Card.as                  # Card type definition (753 LOC)
│       ├── StateHelper.as           # Computed properties (649 LOC)
│       ├── Inst.as                  # Unit instance (504 LOC)
│       ├── EndTurnObject.as         # Turn stats (310 LOC)
│       ├── C.as                     # Constants (625 LOC)
│       ├── Mana.as                  # Resource pool (224 LOC)
│       ├── Script.as                # Ability scripts (104 LOC)
│       ├── CreateDescription.as     # Token creation (95 LOC)
│       ├── Order.as                 # Move/undo (88 LOC)
│       ├── ClickResult.as           # Click validation result (61 LOC)
│       ├── StateUtil.as             # AI ↔ engine bridge (156 LOC)
│       ├── SacDescription.as        # Sacrifice cost (39 LOC)
│       ├── Click.as                 # Click data (21 LOC)
│       ├── Rndm.as                  # Flash RNG (166 LOC) — NOT NEEDED
│       ├── Trigger.as               # Campaign triggers (95 LOC) — NOT NEEDED
│       ├── Objective.as             # Mission objectives (44 LOC) — NOT NEEDED
│       ├── RaidAnalyzer.as          # Raid mode (648 LOC) — NOT NEEDED
│       ├── RaidSpawn.as             # Raid spawning (44 LOC) — NOT NEEDED
│       ├── MCDSEvent.as             # Flash UI events (50 LOC) — STUB AS NO-OP
│       └── Errorbang.as             # UI error display (55 LOC) — STUB AS console.error
├── tmp_browser_client/              # Downloaded Lunarch assets
│   ├── MCDSAI3441.js                # ★ Official AI module (1.83MB, Emscripten)
│   ├── AIworker3441.js              # Web worker wrapper (shows cwrap interface)
│   └── PrismataAI_Lunarch.exe       # Native Windows AI (721KB, stdin/stdout pipe)
├── tmp_swf_extract/                 # Extracted SWF binary data
│   ├── 148_*.bin                    # Full AI parameters (JSON text)
│   └── 93_*.bin                     # Short AI parameters (post-turn-16)
├── js_engine/                       # ★ NEW — transpiled JS engine goes here
├── aws/                             # Cloud compute infrastructure
├── gcp/                             # GCP compute infrastructure
└── docs/plans/                      # Implementation plans
```

**Total AS3 source:** 12,457 LOC across 24 files. Plan targets 15 files (~10,600 LOC). 8 files are excluded (campaign/raid/UI-only).

### Key Files the Plan Touches or Creates

| File | Role | LOC |
|---|---|---|
| `prismata_decompiled/scripts/mcds/engine/State.as` | Ground truth game engine — phases, moves, swoosh, defense, breach, stagnation, win check, `toString()` serialization | 4,490 |
| `prismata_decompiled/scripts/mcds/engine/Controller.as` | Click processing — routes inst/card/space clicks, undo/redo, phase transitions, swipe mode | 2,574 |
| `prismata_decompiled/scripts/mcds/engine/Analyzer.as` | Click validation layer — `analyzerFromState()` clones state, `noUpdateClick()` applies moves | 662 |
| `prismata_decompiled/scripts/mcds/engine/Card.as` | Card type definitions — properties parsed from mergedDeck JSON entries | 753 |
| `prismata_decompiled/scripts/mcds/engine/StateHelper.as` | Computed properties — defense, blocker eligibility, attack potential, "all units doomed" check | 649 |
| `prismata_decompiled/scripts/mcds/engine/Inst.as` | Unit instances — state (health, role, blocking, charge), `toObject()`, `compareWithJSON()` | 504 |
| `prismata_decompiled/scripts/mcds/engine/StateUtil.as` | MCDSAI ↔ engine bridge — `convertToClicks()` translates AI output to engine clicks | 156 |
| `prismata_decompiled/scripts/mcds/engine/C.as` | Constants — phases, roles, click types, mana indices, error codes | 625 |
| `prismata_decompiled/scripts/mcds/engine/Mana.as` | Resource pool — parse/serialize "6HBG" format, arithmetic, comparison | 224 |
| `tmp_browser_client/MCDSAI3441.js` | Official Lunarch AI (Emscripten binary) — consumed as-is, not modified | 1,832,069 bytes |
| `tmp_browser_client/AIworker3441.js` | Reference for `cwrap` interface and message protocol | 101 |
| `prismata_decompiled/scripts/AI/AIThreadHandler.as` | Reference for initialization and move request protocol | ~400 |
| `bin/asset/config/cardLibrary.jso` | Unit definitions — 161 units with costs, stats, scripts | ~3,000 |
| `training/vectorize.py` | Python feature extraction — reuse for JSONL→shards conversion | ~400 |

## 5. Relevant Existing Patterns & Conventions

### AS3 Source Patterns

The AS3 engine uses string-typed enums throughout:
- **Phases**: `"action"`, `"defense"`, `"confirm"` (constants in `C.as`: `PHASE_ACTION`, `PHASE_DEFENSE`, `PHASE_CONFIRM`)
- **Roles**: `"default"`, `"assigned"`, `"sellable"`, `"inert"` (constants: `ROLE_DEFAULT`, `ROLE_ASSIGNED`, etc.)
- **Deadness**: `"alive"`, `"selfsacced"`, `"sacced"`, `"blocked"`, `"meleed"`, `"breached"`, `"sniped"`, `"autosniped"`, `"aged"`
- **Click types**: `"inst clicked"`, `"card clicked"`, `"space clicked"`, `"card shift clicked"`, `"inst shift clicked"`, `"end swipe processed"`

**Internal vs Display names**: The engine internally uses codenames (e.g., "Tesla Tower" = Tarsier, "Brooder" = Blastforge). `cardLibrary.jso` maps internal→display via `UIName` field. The MCDSAI expects display names in its protocol.

**State cloning pattern**: `State.clone()` creates a new State via `new State(null,null,null,null,0,0,this)` — the last parameter triggers a deep-copy constructor path that copies table (Dictionary of Inst), mana, supply vectors, etc. The `cards` array (card types) is shared by reference (immutable).

**Dispatch pattern**: `state.dispatch(update, animate, eventType)` sends UI events. When `update=false`, it's a no-op. The `noUpdateClick()` path always passes `update=false`, so all dispatches during AI click application are dead code. The JS port can stub `dispatch()` as a no-op.

**Dictionary (Hash Map) usage**: AS3's `flash.utils.Dictionary` is used for the unit table (`state.table`), keyed by `instId`. Iteration uses `for (var key in dict)` syntax. JS equivalent: `Map` or plain `Object`.

### Resource (Mana) System

6 resource types indexed as: P=0 (gold), G=1 (green), B=2 (blue), R=3 (red), H=4 (energy), A=5 (attack).

String format: leading digits = gold, then letter codes. Examples:
- `"3H"` = 3 gold + 1 energy (Drone cost)
- `"6BGGG"` = 6 gold + 1 blue + 3 green
- `"0"` = empty

**Important quirk:** The letter for red is `"C"` internally (not `"R"`). The "public-facing" format uses `"R"` for red and `"E"` for energy (instead of `"H"`). `toString()` uses the internal format (what MCDSAI sees); `toPublicFacingString()` uses the display format.

### Instance Matching (Critical for AI Integration)

The MCDSAI identifies units by **properties** (cardName, owner, role, health, etc.), NOT by `instId`. When the AI says "click this Tarsier", `StateUtil.findInstId()` searches the state table for a matching instance via `Inst.compareWithJSON()`:

```actionscript
public function compareWithJSON(obj:Object) : Boolean
{
    if (obj.hasOwnProperty("cardName") && obj.cardName != this.card.cardName) return false;
    if (obj.hasOwnProperty("owner") && obj.owner != this.owner) return false;
    if (obj.hasOwnProperty("role") && obj.role != this.role) return false;
    if (obj.hasOwnProperty("blocking") && obj.blocking != this.blocking) return false;
    if (obj.hasOwnProperty("deadness") && obj.deadness != this.deadness) return false;
    if (obj.hasOwnProperty("health") && obj.health != this.health) return false;
    if (obj.hasOwnProperty("damage") && obj.damage != this.damage) return false;
    if (obj.hasOwnProperty("disruptDamage") && obj.disruptDamage != this.disruptDamage) return false;
    if (obj.hasOwnProperty("charge") && obj.charge != this.charge) return false;
    if (obj.hasOwnProperty("constructionTime") && obj.constructionTime != this.constructionTime) return false;
    if (obj.hasOwnProperty("delay") && obj.delay != this.delay) return false;
    if (obj.hasOwnProperty("lifespan") && obj.lifespan != this.lifespan) return false;
    return true;
}
```

This returns the **first match** — if multiple instances share identical properties, the one encountered first during Dictionary iteration wins. Deterministic ordering matters.

### MCDSAI Protocol (Verified from AIThreadHandler.as)

**Initialization** (once per game):
```javascript
const payload = JSON.stringify({
    mergedDeck: simpleMergedDeck,  // Array of card objects
    aiParameters: aiParams         // JSON text from tmp_swf_extract/148_*.bin
});
CPPAI_InitializeAI(payload);
```

**Move request** (each turn):
```javascript
// Full params used for turns 1-16, short params after turn 16
const payload = JSON.stringify({
    gameState: state.toString(timeRemainingMS),
    aiPlayerName: "HardestAI"
});
const response = JSON.parse(CPPAI_GetAIMove(payload));
// response.aiclicks = [{type: "card clicked", args: "Tarsier"}, ...]
// response.aithinktime, response.aimovesize
```

**Click application** (`StateUtil.convertToClicks` pattern):
```javascript
const analyzer = Analyzer.analyzerFromState(state);  // Clones state
for (const click of response.aiclicks) {
    if (analyzer.controller.inSwipe) {  // daveAI auto-inserts end-swipe
        analyzer.noUpdateClick(C.CLICK_END_SWIPE);
    }
    if (click.type === "inst clicked") {
        const id = StateUtil.findInstId(click.args, analyzer);
        analyzer.noUpdateClick("inst clicked", id);
    } else if (click.type === "card clicked") {
        const cardId = analyzer.gameState.cardNameToCard(click.args).cardId;
        analyzer.noUpdateClick("card clicked", cardId);
    } else if (click.type === "space clicked") {
        analyzer.noUpdateClick("space clicked", -1);
    }
}
state = analyzer.gameState;  // Post-move state
```

**Turn 16 parameter switch:** After turn 16, the live game switches from full AI parameters (148_*.bin) to short parameters (93_*.bin). The short params are a strict subset of full — no HardestAI-relevant differences.

**200+ units safety valve:** If either player has >200 unit instances, the game bypasses the AI and uses `AutoClicks.luckClickFromStart()` (essentially random legal moves) to prevent timeouts.

### State Serialization (`State.toString()`)

The `toString(timeRemainingMS)` method produces a JSON object with:
- `table`: Array of unit instances (each via `Inst.toObject()`)
- `nextInstId`: Counter for new instance IDs
- `cards`: Array of card internal names (from mergedDeck)
- `whiteTotalSupply` / `blackTotalSupply`: Per-card supply counts
- `whiteSupplySpent` / `blackSupplySpent`: Per-card purchase counts
- `whiteMana` / `blackMana`: Resource strings (e.g., `"6HBG"`)
- `numTurns`: Total turns elapsed
- `turn`: Current player index (computed getter, not stored)
- `phase`: String (`"action"`, `"defense"`, `"confirm"`)
- `glassBroken`: Boolean (breach occurred this turn)
- `result`: Game outcome (0=ongoing, 1=white win, etc.)
- `timeRemainingMS`: Think time hint for AI

### Swoosh (End-of-Turn Resolution)

The `swoosh()` method (State.as:2582-3045, ~460 lines) is the most complex single method. It handles:
1. Clear damage/chill on current player's units
2. Tick down construction time, lifespan
3. Execute begin-own-turn scripts (resource production, token creation)
4. Process resonance effects
5. Handle annihilation (mutual kill between specific units)
6. Check for stagnation (no-progress counters)
7. Increment turn counter
8. Update helper state
9. Check win conditions

The swoosh uses a deterministic pseudo-random seed derived from the card list (`numTurns * cardName.length % 49979687`). This is used for RNG-dependent effects (rare in PvP, but exists for annihilation ordering).

### Stagnation System

AS3 has a 4-level progress counter system (constants at State.as:76-104):
- **Cutoffs:** [2, 8, 20, 40] turns without progress at each level
- **12+ event types** tracked as "progress" at different levels (card bought = level 3, damage dealt > healing = level 1, lifespan ticked = level 3, etc.)
- When all 4 levels exceed their cutoffs → stalemate draw

The C++ engine only has a flat 200-turn limit. This is a known mismatch.

### Testing Strategy

- **Replay validation:** 2,127 Master Bot replays validated against the C++ engine. Each click is applied; illegal clicks = failure. Current C++ pass rate: 50.4%.
- **The JS engine will be validated the same way**, targeting >90% pass rate.
- **No unit test framework** currently exists for the AS3 code or the planned JS port. The plan proposes manual checkpoint tests at each phase boundary.

## 6. Current State & Known Issues

### What Works Today
- C++ engine runs self-play games (~4 games/min per 4-thread process)
- Training pipeline: binary shards → PyTorch → exported weights → C++ inference
- Cloud infrastructure: AWS EC2, GCP, Azure launchers + TheWatcher auto-monitor
- 722K self-play games generated (26.7M records, 178 GB in S3)
- Best model: 51.9% WR vs OriginalHardestAI (256h/3L, 722K games)

### Critical Issue: Training Data Quality
- **ALL 722K games** were generated with the buggy C++ engine
- When engine bugs were fixed, AI win rate collapsed from 51.9% to ~11%
- The AI had learned to exploit engine bugs, not play Prismata correctly
- This is the entire motivation for this plan

### Known C++ Engine Bugs (vs AS3 Ground Truth)
1. **Script execution ordering** — C++ and AS3 execute ability/buy/turn scripts in different orders
2. **Stagnation detection** — AS3 has 4-level progress counters; C++ has flat 200-turn limit
3. **Death scripts** — AS3 runs `deathScript` when units die from breach; C++ just marks them dead
4. **4 Condition types** — AS3 checks conditions like `"is blocking"`, `"healthAtMost"`, `"nameIn"`, `"isABC"` that C++ doesn't implement
5. **USE_ABILITY timing** — accounts for 40.7% of remaining validation failures

### AS3 Source Quality
The AS3 source is decompiled — variable names are mostly preserved, but:
- Some local variables are decompiler artifacts (`_loc6_`, `_loc7_`)
- The decompiled `for...in` loops over Dictionaries may have slightly restructured control flow vs original
- Imports include UI classes (`starlingUI.*`, `client.*`) that are not used in core game logic paths — the `dispatch()` no-op pattern handles this

### State.as UI Dependencies
State.as imports 10 UI/client classes:
```actionscript
import client.AutoClicks, client.CheatCodes, client.Client, client.Game,
       client.MissionGame, client.Progression;
import starlingUI.UIEvent, starlingUI.UIScreen;
import starlingUI.game.board.UIInst;
import starlingUI.game.mission.MissionScreen, MissionScreen_buyboxPopoutLate;
import starlingUI.lobby.collection.badges.Badge;
```
Most of these are only used in tutorial/mission/UI paths that won't execute in headless mode. However, some references exist in core paths:
- `Game.gameState` — referenced in `StateUtil.findCard()` fallback (line 139) — must be stubbed
- `State.score` — static Dictionary used for campaign scoring — can be null
- `AutoClicks.luckClickFromStart()` — emergency fallback for >200 units — might need implementation or a simpler fallback
- `CheatCodes` — dev testing only, not called in normal paths

## 7. Context Specific to the Plan

### MCDSAI3441.js Integration Details

The Emscripten module exports exactly 2 functions via `cwrap`:
```javascript
CPPAI_InitializeAI = Module.cwrap('CPPAI_JS_InitializeAI', 'string', ['string']);
CPPAI_GetAIMove = Module.cwrap('CPPAI_JS_GetAIMove', 'string', ['string']);
```

Both take a single JSON string and return a JSON string. The module is 1.83MB of minified JavaScript. It was compiled from C++ (the same codebase as `PrismataAI_Lunarch.exe`). It has been tested and confirmed working in Node.js — a test initialization and move request both succeed.

The native Windows exe (721KB) uses stdin/stdout pipe with the same JSON protocol. It could serve as an alternative for Windows-only deployments but won't work on Linux cloud instances.

### cardLibrary.jso Format

```json
{
    "Drone": {
        "baseSet": 1, "rarity": "trinket", "toughness": 1,
        "defaultBlocking": 1, "assignedBlocking": 0,
        "buyCost": "3H", "abilityScript": {"receive": "1"}
    },
    "Brooder": {
        "baseSet": 1, "rarity": "normal", "toughness": 3,
        "defaultBlocking": 0, "buyCost": "5",
        "beginOwnTurnScript": {"receive": "B"}, "UIName": "Blastforge"
    },
    ...
}
```

Keys are internal names. `UIName` field provides the display name (if different from internal name). 161 units total. The `mergedDeck` sent to MCDSAI must use display names as `cardName`.

### Prior Rejected Approaches

1. **Keep fixing C++ engine** — Rejected. After a full audit (22 areas, 4 fixes), pass rate went DOWN (55.7% → 50.4%). Remaining bugs are deep semantic mismatches (script ordering, stagnation, death scripts). Estimated effort to fully fix C++ exceeds the transpilation effort.

2. **Reverse-engineer MCDSAI3441.js** — Rejected. 1.83MB of Emscripten-compiled code with no symbols. Only 57 internal exports visible. The game engine logic is compiled into the binary — extracting it would be more effort than transpiling from readable AS3 source.

3. **Headless Flash automation** — Rejected. Would require running the SWF in a Flash emulator (Ruffle, etc.), extracting state via instrumentation. Fragile, slow, and Flash is EOL.

4. **Use PrismataAI_Lunarch.exe directly** — Partially applicable. The native exe uses the same protocol but only works on Windows. The JS module works on any platform (critical for Linux cloud instances).

### Performance Considerations

- MCDSAI think time: ~1s per turn (configurable via `timeRemainingMS`)
- Average game length: ~74 turns total (~37 per player)
- Estimated throughput: ~0.8 games/min per Node.js process
- JS engine overhead: negligible compared to AI think time
- Memory: MCDSAI3441.js requires ~50-100MB heap; game state is small (<1MB)
- Multiple processes per machine (Node.js is single-threaded; use `cluster` or separate processes)

### Existing Validation Infrastructure

- 2,127 Master Bot replay JSONs available on S3 (`saved-games-alpha.s3-website-us-east-1.amazonaws.com`)
- Each replay contains: `commandInfo.commandList` (full click sequence), `deckInfo.mergedDeck`, `ratingInfo`
- Replay click format: `{_type: "card clicked", _id: 5}` — uses mergedDeck index, not display name
- Existing Python tools: `fast_batch_validate.py`, `convert_replay_for_cpp.py`, `retest_validation.py`
- These tools target the C++ engine; they'll need adaptation for JS engine validation

## 8. Scope Boundaries

### Explicitly Out of Scope
- **Modifying MCDSAI3441.js** — it's a compiled binary; we consume it as-is
- **Replacing the C++ engine** — the C++ engine continues to serve the GUI, tournaments, and existing AI. The JS engine is a parallel system for training data generation only.
- **Campaign/mission/raid modes** — PvP self-play only. Files excluded: `Trigger.as`, `Objective.as`, `RaidAnalyzer.as`, `RaidSpawn.as`
- **UI rendering** — headless only. All `dispatch()`, `MCDSEvent`, `UIEvent`, `UIScreen` calls are no-ops.
- **Randomness** — PvP Prismata has no randomness (all abilities are deterministic). `Rndm.as` can be stubbed. The swoosh RNG seed is deterministic from game state.
- **TypeScript / bundler / build system** — plain JavaScript, CommonJS modules. Correctness over elegance.
- **Feature extraction in JS** — features are extracted in Python from the JSONL output, not in JS.

### Fixed and Non-Negotiable
- **AS3 source is the ground truth** — do not invent game rules or "improve" the AS3 logic. Port it faithfully.
- **MCDSAI protocol is fixed** — the AI expects specific JSON formats for init, move request, and click types. These cannot be changed.
- **Display names in protocol** — MCDSAI uses display names ("Tarsier"), not internal names ("Tesla Tower"). The mergedDeck must map correctly.
- **Training data format** — output must be convertible to the existing 1,785-dim binary shard format via the Python pipeline.

### Accepted Trade-offs
- **Slower than C++**: ~0.8 games/min (JS) vs ~4 games/min (C++). Acceptable because data quality > speed.
- **Duplicate game logic**: JS engine coexists with C++ engine. No attempt to unify or share code.
- **Manual transpilation**: No AST-based automated transpiler. AI-assisted manual conversion, file by file.

## 9. Success Criteria

1. **Replay pass rate >90%** on the 2,127 Master Bot replays (currently C++ achieves 50.4%)
2. **100 complete self-play games** between two MCDSAI instances end-to-end without crashes
3. **Training data format compatibility**: JSONL output → Python vectorize → binary shards → `train.py` loads without error
4. **Game result sanity**: Self-play games end within 200 turns, win/loss/draw ratios are reasonable (~50/50 between identical AIs)
5. **Cloud deployable**: Single Node.js package runs on Linux EC2 instances, uploads shards to S3
6. **Feature parity with key replay positions**: For a sample of 10 replay positions, the JS `State.toString()` output matches the expected MCDSAI input format field-by-field

## 10. Key Questions for Reviewers

1. **Transpilation approach**: The plan proposes manual AI-assisted transpilation of 15 files (~10,600 LOC). Is this the right granularity? Should we consider a more automated approach (e.g., an AST-based AS3→JS transpiler), or is manual file-by-file the most reliable path for this specific codebase?

2. **Instance matching ambiguity**: `compareWithJSON()` returns the first match in Dictionary iteration order. If the MCDSAI sends properties that match multiple instances (e.g., two identical Tarsiers), the match depends on iteration order. How should the JS engine handle this? Is Dictionary iteration order in AS3 deterministic? Does the JS port need to replicate it exactly?

3. **Stagnation system complexity**: The 4-level progress counter system (12+ event types, cutoffs [2,8,20,40]) is a significant implementation effort. Since we're generating training data (not a user-facing product), could we skip stagnation and use a simple turn limit? What are the risks?

4. **Validation strategy completeness**: The plan validates via replay pass rate and self-play smoke tests. Are there additional validation approaches that would catch subtle state drift (e.g., comparing `toString()` output at every turn of a replay against the AS3 engine's output)?

5. **JSONL → binary shard pipeline**: The plan assumes `vectorize.py` can convert JS JSONL output to binary shards. The existing pipeline was built for C++ binary output. What adaptations are needed, and how much effort is that?

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **AS3** | ActionScript 3 — the programming language of Flash/AIR. The Prismata game client is written in AS3. |
| **MCDSAI** | The Lunarch-built AI module. "MCDS" appears to be an internal project codename. Compiled from C++ to JavaScript via Emscripten. |
| **Emscripten** | Compiler toolchain that compiles C/C++ to JavaScript/WebAssembly. Used to create MCDSAI3441.js from C++ source. |
| **cwrap** | Emscripten utility function that wraps a C function for JavaScript calling. `Module.cwrap('funcName', 'returnType', ['argTypes'])`. |
| **mergedDeck** | The complete list of card types available in a game — base set (11 units always present) plus 8 randomly selected advanced units. Array of objects with card properties. |
| **cardLibrary.jso** | Master database of all 161 unit types with their costs, stats, and scripts. `.jso` = JSON Object (Lunarch convention). |
| **Inst** | Instance — a specific unit on the board. Each Inst has an `instId`, references a `Card` type, and tracks mutable state (health, role, blocking, etc.). |
| **Card** | Card type — the immutable template for a unit type (cost, starting health, scripts). Multiple Insts can share the same Card. |
| **Swoosh** | End-of-turn resolution phase. Clears damage, ticks timers, runs production scripts, checks win conditions, advances to next player. |
| **Phase** | Game phase within a turn: Action (buy/use abilities) → Confirm (optional) → Defense (assign blockers) → Swoosh → next player's Action. |
| **Breach** | When the attacker's damage exceeds the defender's total blocking HP, excess damage "breaches" through to unblocked units. |
| **Chill** | A debuff that reduces a unit's blocking ability. Applied by units with `targetAction: "disrupt"` (mapped to `ActionTypes::CHILL` in C++). |
| **Frontline** | Attacking with a unit that has assigned blocking — it "charges forward" and can be killed in the process. |
| **Role** | Unit status: `"default"` (idle), `"assigned"` (frontline/attacking), `"sellable"` (just bought, can undo), `"inert"` (token, can't sell). |
| **Deadness** | How a unit died: `"alive"`, `"selfsacced"`, `"sacced"`, `"blocked"` (killed while blocking), `"meleed"` (frontlined), `"breached"`, `"sniped"`, `"autosniped"`, `"aged"` (lifespan expired). |
| **Swipe** | Multi-click mode for assigning multiple blockers or using shift-click patterns. Controller tracks `swipePurpose` state. |
| **Playout** | AI evaluation method — simulate a game to completion using simple heuristics, then score the result. Used as the evaluation function in the current self-play. |
| **Alpha-Beta / UCT** | Search algorithms. Alpha-Beta prunes a minimax tree. UCT (Upper Confidence Trees) is a Monte Carlo tree search variant. Both use evaluation functions to score leaf positions. |
| **Binary shard** | Training data file format: 64-byte header + N × 7,152-byte records + 4-byte CRC32 footer. Each record contains a 1,785-dim feature vector + policy + value label. |
| **State.toString()** | Serializes game state to JSON string for MCDSAI communication. The format is THE protocol contract between engine and AI. |
| **dispatch()** | AS3 event system call — sends UI update events. In headless mode, this is a no-op. |
| **OriginalHardestAI** | Dave Churchill's original AI configuration — the primary benchmark opponent for win rate evaluation. |
| **Master Bot** | The AI opponent in the live Prismata game, powered by the MCDSAI module. |
| **Replay pass rate** | Percentage of historical replays where every recorded click is legal in the engine being tested. Measures engine faithfulness. |
