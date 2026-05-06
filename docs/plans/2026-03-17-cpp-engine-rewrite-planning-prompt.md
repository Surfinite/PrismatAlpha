# Planning Prompt: C++ Engine Rewrite for Linux RL Self-Play

> **Purpose**: Hand this prompt to a fresh Claude context to produce a full implementation plan.
> **Skills to invoke**: `superpowers:brainstorming` first, then `superpowers:writing-plans`.

---

## Context

You are working on **PrismataAI** at `c:\libraries\PrismataAI`. This is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game.

**Please start by invoking `superpowers:brainstorming` before planning, to explore design options. Then invoke `superpowers:writing-plans` to produce the actual plan.**

---

## Background

The project currently has two parallel game engine implementations:

1. **JS engine** (`js_engine/`) — ported from the decompiled AS3 source. Validated at 100% pass rate against 500 real game replays. This is the **source of truth** for runtime behaviour.

2. **Decompiled AS3 source** (`prismata_decompiled/scripts/mcds/engine/`) — the original production game engine AS3 files decompiled from `Prismata.swf` via JPEXS. 1,819 AS3 files total. The core engine lives in `mcds/engine/`: `State.as`, `Controller.as`, `Analyzer.as`, `Card.as`, `Inst.as`, `Mana.as`, `Script.as`. **This is the primary reference for the rewrite** — prefer reading AS3 over JS when they diverge or when JS transpilation is unclear.

2. **C++ engine** (`source/engine/`) — an independent C++ implementation of the same game. Has a ~50% batch validation pass rate (genuine divergences from the AS3/JS reference). Used by the AI search (UCT, Alpha-Beta, PartialPlayers). **Contains bugs but the AI layer on top of it is correct and valuable.**

### The Problem

For RL self-play training we need:
- **Speed**: the current matchup runner (`js_engine/matchup_clean.js`) spawns a fresh `Prismata_Testing.exe` subprocess every turn. Process creation overhead dominates at short think times, making it ~3–5x slower than native C++.
- **Linux compatibility**: Windows instances on AWS/GCP cost 20–40% more due to licensing. The codebase is already almost Linux-ready (Timer.h has `#ifdef WIN32` guards, no Win32 threading anywhere — Benchmarks.cpp uses `std::thread`). The only real blocker is the MSVC `.vcxproj` build system.
- **Correctness**: RL training needs a consistent, trustworthy engine. The JS engine is that; the C++ engine isn't fully there yet.

### The Goal

**Produce an in depth plan to replace the buggy C++ game engine layer with a corrected implementation using the JS engine as the reference oracle — while fully preserving the C++ AI layer (UCT, Alpha-Beta, PartialPlayers, NeuralNet) — and deliver a CMake-based Linux-compatible build targeting headless RL self-play. Prepare the plan so that it can be executed using `superpowers:executing-plans`**

---

## What Exists (explore these before planning)

### JS Engine — source of truth (~7,300 lines)

| File | Lines | Role |
|------|-------|------|
| `js_engine/Controller.js` | 2,268 | Click handling, legality (`canAssign`, `canBuy`, `processClick` ~1020 lines) |
| `js_engine/State.js` | 1,686 | Game state, `swoosh()`, `processMove()`, script execution |
| `js_engine/Analyzer.js` | 889 | Legal move generation / AI interface |
| `js_engine/StateHelper.js` | 525 | Derived display state |
| `js_engine/Card.js` | 517 | Card/CardType data |
| `js_engine/Inst.js` | 405 | Unit instance state |
| `js_engine/C.js` | 475 | Constants |
| `js_engine/Mana.js` | 182 | Resource handling |
| `js_engine/StateUtil.js` | 184 | Utility functions |
| `js_engine/Script.js` | 89 | Script execution helpers |

### Existing C++ Engine — buggy but structurally relevant (~4,500 lines)

| File | Lines |
|------|-------|
| `source/engine/GameState.cpp` | 2,342 |
| `source/engine/Card.cpp` | 993 |
| `source/engine/CardType.cpp` | 359 |
| `source/engine/Resources.cpp` | 234 |
| `source/engine/Script.cpp` | 143 |
| `source/engine/Game.cpp` | 105 |
| + headers, Action, Move, SacDescription, CreateDescription, Condition, etc. | |

### C++ AI Layer — fully reusable, do NOT touch

- `source/ai/` — UCT search, Stack Alpha-Beta, all PartialPlayers, NeuralNet (DSN2), AIParameters, Heuristics, Eval
- `source/testing/Tournament.cpp` — self-play runner (uses `std::thread`)
- `bin/asset/config/config.txt` — AI player configs
- `bin/asset/config/cardLibrary.jso` — 116-unit card library (11 base + 105 Dominion)
- `bin/asset/config/neural_weights_*.bin` — trained NN weight files

### Known C++ engine bugs

- `killCardByID` may have cleanup bugs — originally documented as "missing death scripts" but Prismata has no on-death triggers (confirmed: Centurion and Valkyrion have no such mechanic). Actual nature of the bug is unconfirmed.
- Missing stagnation detection: AS3 has 4-level progress counter; C++ has flat 200-turn limit
- Various state divergences causing ~50% batch validation failures

### Validation tooling that exists

- `js_engine/replay_validator.js` — validates click-by-click against real replays
- `js_engine/replay_stats.js` — batch replay statistics
- `training/data/dataset_validation.json` — validation dataset
- Real replay archive at `c:\libraries\prismata-replay-parser\replays_archive\`

### Previous related work

- `docs/plans/as3-faithful-port-implementation-plan.md` — a prior attempt at porting. Read this before planning; understand what was tried and why it may not have been completed. The new plan has a different goal (Linux RL, drop MCDSAI, preserve AI layer) so may differ significantly.
- The full decompiled AS3 source lives at `prismata_decompiled/scripts/mcds/engine/` (1,819 AS3 files total from JPEXS). The JS engine was produced by porting these AS3 files to JS. When planning the rewrite, the AS3 is the primary reference — it is the original production code with original variable names and logic intact.
- `docs/plans/engine-logic-audit-plan-v2.md` — engine audit findings, useful for understanding known divergences.

---

## What the Plan Should Cover

1. **Audit phase**: map JS engine structure → existing C++ structure. Which C++ files are approximately correct? Which need full rewrite? What is the interface the AI layer depends on?

2. **Interface contract**: Define the boundary between the new engine layer and the existing AI layer. The AI calls things like `state.isLegal(action)`, `state.doAction(move)`, move iterators, win detection. This interface must be preserved exactly.

3. **Rewrite strategy**: For each engine file, decide: keep-and-fix vs rewrite-from-JS-reference vs keep-as-is. The JS is the reference oracle, not a line-by-line transliteration target.

4. **CMakeLists.txt structure**: Linux-first build. Two targets minimum: `prismata_engine_tests` (validation) and `prismata_selfplay` (RL training binary). No SFML. No GUI. No MCDSAI protocol.

5. **What to drop**: GUI (`source/gui/`), MCDSAI protocol, `--suggest` CLI mode can be simplified or dropped, SFML dependency entirely, Windows-specific build files.

6. **Validation strategy**: The new C++ engine must pass replay validation. Plan for a test harness that can run the same replays through both JS engine and new C++ engine and diff the results.

7. **NeuralNet singleton**: `NeuralNet::Instance()` currently prevents two NN players in one process. RL self-play with NN on both sides requires this to be addressed. The plan should include a decision on how to handle it (instance-based, shared read-only weights, or defer).

8. **Migration sequence**: What order to tackle the files so the AI layer can be plugged back in incrementally and tested at each step.

9. **Linux deployment**: CMake config, dependencies (RapidJSON is embedded, no SFML needed), compiler flags, CI considerations.

---

## Constraints

- The user is cost-conscious (prior AWS bill shock). Prefer local development and testing before cloud runs.
- The C++ AI layer (PartialPlayers, UCT, NeuralNet) must be fully preserved — it represents significant validated work.
- MCDSAI compatibility is explicitly **not needed**. The new engine only needs to support the internal C++ AI.
- The JS engine is the reference, not the AS3 source directly. Use JS as oracle.
- Build must target Linux x64 (cloud instances). Windows builds are a bonus, not a requirement.
- No SFML dependency in the self-play target.
- `std::thread` is already used in Benchmarks.cpp — C++17 or later is fine.

---

## Key Gotchas to Be Aware Of

- **Internal name system**: C++ engine uses codenames (e.g. "Tesla Tower" = Tarsier, "Factory" = Synthesizer). `cardLibrary.jso` maps internal names to `UIName` display names. JS engine uses display names externally. The plan must address name mapping consistency.
- **NeuralNet singleton**: `NeuralNet::Instance()` — two NN players can't coexist in one C++ process currently. RL self-play with NN on both sides will require this to be addressed.
- **AS3↔C++ naming dictionary** in `docs/plans/engine-logic-audit-plan.md`: `role`=`CardStatus`, `disruptDamage`=`m_currentChill`, `MOVE_MELEE`=`ASSIGN_FRONTLINE`, `glassBroken`=`Phases::Breach`, `MOVE_ASSIGN`=`USE_ABILITY`, `MOVE_DEFEND`=`ASSIGN_BLOCKER`.
- **Targeting abilities are two-step**: USE_ABILITY on source, then SNIPE/CHILL on target. 12 units have `targetAction`.
- **`beginOwnTurnScript` vs `abilityScript`**: automatic (no click) vs player-activated (click). The C++ engine must correctly distinguish these.
- **Timer.h** already has `#ifdef WIN32` / `#else` Linux guards — Linux portability was already partially considered.
- **x86-only constraint in VS project is not a code constraint** — on Linux compile x64 natively.
