# Engine V2 Clean-Room Port — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the buggy C++ game engine with a correct clean-room port from the validated JS/AS3 engine, producing a CMake-based Linux build for headless RL self-play.

**Architecture:** New `source/engine_v2/` directory implements the same public interface as `source/engine/` so the AI layer links against it with zero functional changes. Game logic is ported function-by-function from `js_engine/` (reference oracle) with `prismata_decompiled/scripts/mcds/engine/` (AS3) as tiebreaker. Bottom-up build order: types → resources → cards → state machine → validation → AI integration.

**Tech Stack:** C++17, CMake, RapidJSON (embedded), std::thread. No external dependencies.

**Spec:** `docs/superpowers/specs/2026-03-17-engine-v2-clean-room-port-design.md`

---

## File Structure

### New files in `source/engine_v2/`

Files carried from `source/engine/` (data containers, no game logic — copy with minimal edits):
- `BaseTypes.hpp` — core typedefs (CardID, PlayerID, HealthType, etc.)
- `Common.h` — standard includes + Constants + PrismataAssert
- `Constants.h` — phase/action/player enums
- `PrismataAssert.h/cpp` — soft assert macro
- `Action.h/cpp` — action data tuple
- `Move.h/cpp` — vector of actions
- `Player.h/cpp` — base player class
- `Resources.h/cpp` — resource pool arithmetic
- `Condition.h/cpp` — conditional script logic
- `CreateDescription.h/cpp` — token creation descriptor
- `DestroyDescription.h/cpp` — unit destruction descriptor
- `SacDescription.h/cpp` — sacrifice cost descriptor
- `Script.h/cpp` — script definition
- `ScriptEffect.h/cpp` — script effect definition
- `CardTypeInfo.h/cpp` — card type metadata storage
- `CardTypeData.h/cpp` — singleton card type registry
- `CardType.h/cpp` — card type wrapper
- `CardTypes.h/cpp` — global card type vectors
- `CardBuyable.h/cpp` — supply tracking
- `CardBuyableData.h/cpp` — buyable card registry (used by CardData)
- `CardData.h/cpp` — card storage container (NOT header-only — .cpp has 330 lines)
- `GenericValue.h/cpp` — generic value type (used by AI's CardFilterCondition)
- `Common.cpp` — if exists in old engine, copy it
- `Game.h/cpp` — game orchestrator
- `Prismata.h/cpp` — global init + umbrella header
- `Timer.h/cpp` — cross-platform timing
- `FileUtils.h/cpp` — file I/O
- `JSONTools.h/cpp` — RapidJSON helpers

Files ported from JS (game logic — clean-room implementation):
- `Card.h/cpp` — card instance (from `js_engine/Inst.js`)
- `GameState.h/cpp` — game state machine (from `js_engine/State.js`, `Controller.js`, `Analyzer.js`, `StateHelper.js`, `EndTurnObject.js`)

### New files in project root
- `CMakeLists.txt` — Linux-first build

### New files for testing
- `source/engine_v2/tests/test_resources.cpp`
- `source/engine_v2/tests/test_card_library.cpp`
- `source/engine_v2/tests/test_card.cpp`
- `source/engine_v2/tests/test_game_state.cpp`
- `source/engine_v2/tests/test_main.cpp` — test runner entry point

### Modified files in `source/ai/`
- `AIParameters.h` — change `#include "../engine/Prismata.h"` → `"../engine_v2/Prismata.h"`
- `PrismataAI.h` — same include path change
- `NeuralNet.h/cpp` — singleton→instance refactor (Task 12)
- `Eval.h/cpp` — add NeuralNet* parameter to evaluation functions (Task 12)
- All Player_*.cpp files that call Eval functions — update signatures (Task 12)

---

## Critical Notes for Implementers

### Mana Index Order Differs Between JS and C++

JS `Mana.js` uses: `[Gold=0, Green=1, Blue=2, Red=3, Energy=4, Attack=5]`
C++ `Resources` uses: `[Gold=0, Energy=1, Blue=2, Red=3, Green=4, Attack=5]`

Green and Energy are **swapped**. When porting JS logic that indexes into mana arrays, always use the C++ `Resources::` enum constants, never hardcoded indices from JS.

### Internal Names vs Display Names

C++ engine uses internal names ("Factory", "Tesla Tower"). JS engine and replays use display names ("Synthesizer", "Tarsier"). The mapping is in `bin/asset/config/cardLibrary.jso` — JSON key = internal name, `"UIName"` field = display name. When UIName is absent, they're the same.

### Phase Model

JS has 3 phases + glassBroken flag. C++ AI expects 5 phase enum values. See spec Section 4.1 for the full `getActivePhase()` contract. The turn order from one player's perspective is: Defense → Swoosh → Action → [Breach] → Confirm.

### Include Path Resolution

CMake sets include path to `source/engine_v2/` (not `source/engine/`). Bare includes like `#include "GameState.h"` resolve to engine_v2 files. Two AI files use hardcoded relative paths that must be updated: `AIParameters.h` and `PrismataAI.h`.

---

## Task 0: Interface Audit

**Goal:** Produce a locked interface spec — every symbol the AI layer imports from the engine.

**Files:**
- Create: `docs/engine_v2_interface_spec.md`

- [ ] **Step 1: Grep all engine includes from AI layer**

```bash
cd c:/libraries/PrismataAI
grep -rn '#include' source/ai/ | grep -E '(engine/|"Common\.h"|"GameState\.h"|"Game\.h"|"Player\.h"|"Card|"Resources|"Move\.h"|"Action\.h"|"Timer\.h"|"Prismata\.h"|"Constants\.h"|"FileUtils"|"JSONTools"|"BaseTypes"|"Script")'
```

- [ ] **Step 2: Grep path-qualified includes**

```bash
grep -rn '../engine/' source/ai/ source/testing/
```

Expected: `AIParameters.h` and `PrismataAI.h` have `../engine/Prismata.h`. No others.

- [ ] **Step 3: Check testing/main.cpp for Windows-specific code**

Read `source/testing/main.cpp`. Known issues: `_dup()`, `_dup2()`, `_fileno()`, `_close()`, `#include <process.h>`, `#include <io.h>`. These need `#ifdef _WIN32` guards (some may already exist — verify).

- [ ] **Step 4: Document the interface spec**

Write `docs/engine_v2_interface_spec.md` listing every engine header imported by AI, with the public symbols used. Group by header file. This document is the contract that engine_v2 must satisfy.

- [ ] **Step 5: Commit**

```bash
git add docs/engine_v2_interface_spec.md
git commit -m "feat: document engine_v2 interface spec from AI layer audit"
```

---

## Task 1: CMake Stub + Foundation Types

**Goal:** Create the CMake build system and copy foundational type headers. Verify it compiles on Linux (or at least locally with CMake).

**Files:**
- Create: `CMakeLists.txt`
- Create: `source/engine_v2/BaseTypes.hpp` (copy from `source/engine/BaseTypes.hpp`)
- Create: `source/engine_v2/Constants.h` (copy from `source/engine/Constants.h`)
- Create: `source/engine_v2/PrismataAssert.h` (copy from `source/engine/PrismataAssert.h`)
- Create: `source/engine_v2/PrismataAssert.cpp` (copy from `source/engine/PrismataAssert.cpp`)
- Create: `source/engine_v2/Common.h` (copy from `source/engine/Common.h`)

- [ ] **Step 1: Create `source/engine_v2/` directory**

```bash
mkdir -p source/engine_v2/tests
```

- [ ] **Step 2: Copy foundation headers**

Copy these files from `source/engine/` to `source/engine_v2/`:
- `BaseTypes.hpp` — no changes needed
- `Constants.h` — no changes needed
- `PrismataAssert.h` — no changes needed
- `PrismataAssert.cpp` — no changes needed
- `Common.h` — no changes needed

Verify: `Common.h` includes `BaseTypes.hpp`, `Constants.h`, `PrismataAssert.h` via bare includes. These will resolve within `source/engine_v2/` via CMake include path.

- [ ] **Step 3: Create CMakeLists.txt**

```cmake
cmake_minimum_required(VERSION 3.16)
project(PrismataAI LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include paths — engine_v2 headers resolve here (not source/engine/)
include_directories(
    ${CMAKE_SOURCE_DIR}/source/engine_v2
    ${CMAKE_SOURCE_DIR}/source/ai
    ${CMAKE_SOURCE_DIR}/source/testing
    ${CMAKE_SOURCE_DIR}/source/rapidjson
)

# Engine V2 sources — CONFIGURE_DEPENDS so cmake re-globs when files are added
file(GLOB ENGINE_V2_SOURCES CONFIGURE_DEPENDS "source/engine_v2/*.cpp")

# Static library to avoid compiling engine_v2 twice
add_library(engine_v2 STATIC ${ENGINE_V2_SOURCES})
target_compile_definitions(engine_v2 PRIVATE
    $<$<CONFIG:Debug>:PRISMATA_ASSERT_ALL>
)

# Test sources
file(GLOB TEST_SOURCES CONFIGURE_DEPENDS "source/engine_v2/tests/*.cpp")

# Engine V2 test executable
add_executable(prismata_engine_v2_tests ${TEST_SOURCES})
target_link_libraries(prismata_engine_v2_tests engine_v2)
```

Note: Even with `CONFIGURE_DEPENDS`, you must re-run `cmake -B build` after adding new `.cpp` files on some generators. If `cmake --build build` doesn't pick up new files, re-configure first.

- [ ] **Step 4: Create minimal test runner**

Create `source/engine_v2/tests/test_main.cpp`:

```cpp
#include "Common.h"
#include <iostream>

int main()
{
    std::cout << "Engine V2 foundation types compile OK" << std::endl;
    std::cout << "Players::Player_One = " << Players::Player_One << std::endl;
    std::cout << "Phases::Action = " << Phases::Action << std::endl;
    std::cout << "Phases::Defense = " << Phases::Defense << std::endl;
    std::cout << "Phases::Breach = " << Phases::Breach << std::endl;
    std::cout << "Phases::Confirm = " << Phases::Confirm << std::endl;
    std::cout << "Phases::Swoosh = " << Phases::Swoosh << std::endl;
    return 0;
}
```

- [ ] **Step 5: Build and verify**

```bash
cd c:/libraries/PrismataAI
cmake -B build -G "Unix Makefiles"
cmake --build build
./build/prismata_engine_v2_tests
```

Expected output: Phase enum values printed. No errors.

- [ ] **Step 6: Commit**

```bash
git add CMakeLists.txt source/engine_v2/
git commit -m "feat: create engine_v2 directory with CMake build and foundation types"
```

---

## Task 2: Resources

**Goal:** Port the resource pool. Copy from old C++ (it's a data container), then write unit tests verifying arithmetic matches JS `Mana.js`.

**Files:**
- Create: `source/engine_v2/Resources.h` (copy from `source/engine/Resources.h`)
- Create: `source/engine_v2/Resources.cpp` (copy from `source/engine/Resources.cpp`)
- Create: `source/engine_v2/tests/test_resources.cpp`

- [ ] **Step 1: Copy Resources files**

Copy `source/engine/Resources.h` and `source/engine/Resources.cpp` to `source/engine_v2/`.

No changes needed — the C++ Resources class is a correct data container. The resource enum order (Gold=0, Energy=1, Blue=2, Red=3, Green=4, Attack=5) is the interface the AI depends on.

- [ ] **Step 2: Write resource tests**

Create `source/engine_v2/tests/test_resources.cpp`:

```cpp
#include "Resources.h"
#include <cassert>
#include <iostream>

void test_parse_string()
{
    // JS: "6BGGG" = 6 gold, 1 blue, 3 green
    // C++ string format uses same letters but different order internally
    Prismata::Resources r("6BGGG");
    assert(r.amountOf(Prismata::Resources::Gold) == 6);
    assert(r.amountOf(Prismata::Resources::Blue) == 1);
    assert(r.amountOf(Prismata::Resources::Green) == 3);
    assert(r.amountOf(Prismata::Resources::Energy) == 0);
    assert(r.amountOf(Prismata::Resources::Red) == 0);
    assert(r.amountOf(Prismata::Resources::Attack) == 0);
    std::cout << "  PASS: test_parse_string" << std::endl;
}

void test_has_and_subtract()
{
    Prismata::Resources pool("10GG");  // 10 gold, 2 green
    Prismata::Resources cost("5G");    // 5 gold, 1 green
    assert(pool.has(cost));
    pool.subtract(cost);
    assert(pool.amountOf(Prismata::Resources::Gold) == 5);
    assert(pool.amountOf(Prismata::Resources::Green) == 1);
    assert(pool.has(cost));  // still enough
    pool.subtract(cost);
    assert(!pool.has(cost)); // not enough anymore
    std::cout << "  PASS: test_has_and_subtract" << std::endl;
}

void test_add()
{
    Prismata::Resources a("3B");
    Prismata::Resources b("2BH");
    a.add(b);
    assert(a.amountOf(Prismata::Resources::Gold) == 5);
    assert(a.amountOf(Prismata::Resources::Blue) == 2);
    assert(a.amountOf(Prismata::Resources::Energy) == 1);
    std::cout << "  PASS: test_add" << std::endl;
}

void test_empty()
{
    Prismata::Resources empty;
    assert(empty.empty());
    Prismata::Resources notempty("1");
    assert(!notempty.empty());
    std::cout << "  PASS: test_empty" << std::endl;
}

void test_get_string_roundtrip()
{
    Prismata::Resources r("12HBBCGA");
    std::string s = r.getString();
    Prismata::Resources r2(s);
    assert(r == r2);
    std::cout << "  PASS: test_get_string_roundtrip" << std::endl;
}

void run_resource_tests()
{
    std::cout << "Running Resource tests..." << std::endl;
    test_parse_string();
    test_has_and_subtract();
    test_add();
    test_empty();
    test_get_string_roundtrip();
    std::cout << "All Resource tests PASSED" << std::endl;
}
```

- [ ] **Step 3: Wire tests into test_main.cpp**

Update `source/engine_v2/tests/test_main.cpp`:

```cpp
#include <iostream>

extern void run_resource_tests();

int main()
{
    run_resource_tests();
    std::cout << "\nAll tests PASSED" << std::endl;
    return 0;
}
```

- [ ] **Step 4: Build and run tests**

```bash
cmake --build build
./build/prismata_engine_v2_tests
```

Expected: All Resource tests PASS.

- [ ] **Step 5: Commit**

```bash
git add source/engine_v2/Resources.* source/engine_v2/tests/test_resources.cpp source/engine_v2/tests/test_main.cpp
git commit -m "feat(engine_v2): add Resources with unit tests"
```

---

## Task 3: Action, Move

**Goal:** Copy Action and Move data containers from old engine.

**Files:**
- Create: `source/engine_v2/Action.h` (copy from `source/engine/Action.h`)
- Create: `source/engine_v2/Action.cpp` (copy from `source/engine/Action.cpp`)
- Create: `source/engine_v2/Move.h` (copy from `source/engine/Move.h`)
- Create: `source/engine_v2/Move.cpp` (copy from `source/engine/Move.cpp`)

- [ ] **Step 1: Copy files**

Copy `Action.h`, `Action.cpp`, `Move.h`, `Move.cpp` from `source/engine/` to `source/engine_v2/`. No changes needed — these are pure data types.

- [ ] **Step 2: Verify build**

```bash
cmake --build build
./build/prismata_engine_v2_tests
```

- [ ] **Step 3: Commit**

```bash
git add source/engine_v2/Action.* source/engine_v2/Move.*
git commit -m "feat(engine_v2): add Action and Move data types"
```

---

## Task 4: Script, ScriptEffect, Descriptors

**Goal:** Copy script and descriptor data types from old engine.

**Files:**
- Copy from `source/engine/`: `Script.h/cpp`, `ScriptEffect.h/cpp`, `Condition.h/cpp`, `CreateDescription.h/cpp`, `DestroyDescription.h/cpp`, `SacDescription.h/cpp`, `JSONTools.h/cpp`, `FileUtils.h/cpp`

- [ ] **Step 1: Copy all descriptor files**

Copy these files from `source/engine/` to `source/engine_v2/`:
- `Script.h`, `Script.cpp`
- `ScriptEffect.h`, `ScriptEffect.cpp`
- `Condition.h`, `Condition.cpp`
- `CreateDescription.h`, `CreateDescription.cpp`
- `DestroyDescription.h`, `DestroyDescription.cpp`
- `SacDescription.h`, `SacDescription.cpp`
- `JSONTools.h`, `JSONTools.cpp`
- `FileUtils.h`, `FileUtils.cpp`
- `GenericValue.h`, `GenericValue.cpp` (used by AI's `CardFilterCondition.h`)
- `Common.cpp` (if it exists in `source/engine/`)

These depend on RapidJSON (included via `source/rapidjson/` in the CMake include path) and on `Common.h` (already in engine_v2).

- [ ] **Step 2: Verify build**

```bash
cmake --build build
./build/prismata_engine_v2_tests
```

Fix any include issues. Most likely cause: missing includes or RapidJSON path.

- [ ] **Step 3: Commit**

```bash
git add source/engine_v2/Script.* source/engine_v2/ScriptEffect.* source/engine_v2/Condition.* source/engine_v2/CreateDescription.* source/engine_v2/DestroyDescription.* source/engine_v2/SacDescription.* source/engine_v2/JSONTools.* source/engine_v2/FileUtils.* source/engine_v2/GenericValue.* source/engine_v2/Common.cpp
git commit -m "feat(engine_v2): add Script, ScriptEffect, descriptors, and JSON utilities"
```

---

## Task 5: CardTypeInfo, CardTypeData, CardType, CardTypes

**Goal:** Copy the card type system and verify 116 units load from `cardLibrary.jso`.

**Files:**
- Copy from `source/engine/`: `CardTypeInfo.h/cpp`, `CardTypeData.h/cpp`, `CardType.h/cpp`, `CardTypes.h/cpp`
- Create: `source/engine_v2/tests/test_card_library.cpp`

- [ ] **Step 1: Copy card type files**

Copy from `source/engine/` to `source/engine_v2/`:
- `CardTypeInfo.h`, `CardTypeInfo.cpp`
- `CardTypeData.h`, `CardTypeData.cpp`
- `CardType.h`, `CardType.cpp`
- `CardTypes.h`, `CardTypes.cpp`

These are the registry system for loading `cardLibrary.jso`. They contain no game logic — just data parsing and storage. The `CardStatus` namespace is defined in `CardType.h`.

- [ ] **Step 2: Write card library loading test**

Create `source/engine_v2/tests/test_card_library.cpp`:

```cpp
#include "CardTypeData.h"
#include "CardTypes.h"
#include "CardType.h"
#include <cassert>
#include <iostream>

void test_load_card_library()
{
    // Load from the master card library
    Prismata::CardTypeData::Instance().InitFromCardLibraryFile(
        "bin/asset/config/cardLibrary.jso"
    );
    Prismata::CardTypes::Init();

    size_t numTypes = Prismata::CardTypeData::Instance().numCardTypes();
    std::cout << "  Loaded " << numTypes << " card types" << std::endl;
    assert(numTypes == 116);  // 11 base + 105 dominion

    // Verify a known base set card
    Prismata::CardType drone = Prismata::CardTypes::GetCardType("Drone");
    assert(drone.getUIName() == "Drone");

    // Verify a known dominion card with UIName mapping
    Prismata::CardType teslaTower = Prismata::CardTypes::GetCardType("Tesla Tower");
    assert(teslaTower.getUIName() == "Tarsier");

    Prismata::CardType factory = Prismata::CardTypes::GetCardType("Factory");
    assert(factory.getUIName() == "Synthesizer");

    std::cout << "  PASS: test_load_card_library" << std::endl;
}

void test_card_type_properties()
{
    // Drone: base set, 1 health, produces 1 gold, can block
    Prismata::CardType drone = Prismata::CardTypes::GetCardType("Drone");
    assert(drone.getHealthAmount() == 1);
    assert(drone.canBlock(false));
    assert(!drone.isFragile());

    // Tarsier (Tesla Tower): 1 health, fragile
    // NOTE: Tarsier's attack comes from beginOwnTurnScript, not a frontline attack value.
    // CardType::getAttack() may return 0 or 1 depending on whether it pre-computes
    // script-derived attack. Verify empirically and adjust assertion if needed.
    Prismata::CardType tarsier = Prismata::CardTypes::GetCardType("Tesla Tower");
    assert(tarsier.getHealthAmount() == 1);
    assert(tarsier.isFragile());

    std::cout << "  PASS: test_card_type_properties" << std::endl;
}

void run_card_library_tests()
{
    std::cout << "Running Card Library tests..." << std::endl;
    test_load_card_library();
    test_card_type_properties();
    std::cout << "All Card Library tests PASSED" << std::endl;
}
```

- [ ] **Step 3: Wire into test_main.cpp and run**

Add `extern void run_card_library_tests();` to test_main.cpp and call it. Build and run.

Note: Tests must run from `c:/libraries/PrismataAI/` (or wherever `bin/asset/config/cardLibrary.jso` is relative to).

- [ ] **Step 4: Commit**

```bash
git add source/engine_v2/CardType* source/engine_v2/tests/test_card_library.cpp
git commit -m "feat(engine_v2): add card type system, verify 116 units load"
```

---

## Task 6: Card (Unit Instance)

**Goal:** Port the Card class from `js_engine/Inst.js`. This is where the first real game logic lives — status transitions, damage model, ability lifecycle.

**Files:**
- Create: `source/engine_v2/Card.h` — port from old `source/engine/Card.h` (interface) + `js_engine/Inst.js` (logic)
- Create: `source/engine_v2/Card.cpp` — port logic from `js_engine/Inst.js`
- Create: `source/engine_v2/tests/test_card.cpp`

**Reference files:**
- `js_engine/Inst.js` — primary reference for card instance behavior
- `js_engine/C.js` — constants (DEADNESS_*, ROLE_*)
- `source/engine/Card.h` — C++ interface that AI expects (40+ public methods)
- `source/engine/Card.cpp` — old implementation (may have bugs — use JS as truth)

### Key porting decisions:

**Status model:**
- JS `role` string (ROLE_DEFAULT, ROLE_ASSIGNED, ROLE_INERT, ROLE_SELLABLE) → C++ `CardStatus` enum (Default=0, Assigned=1, Inert=2). Note: ROLE_SELLABLE has no direct C++ enum — track via `m_sellable` bool.

**Deadness model:**
- JS `deadness` string (DEADNESS_ALIVE, DEADNESS_SELFSACCED, etc.) → C++ `AliveStatus` enum + `CauseOfDeath` enum.

**Damage model (from Inst.js):**
- Fragile cards: `damageItCanTake = health` (damage directly reduces health)
- Non-fragile cards: `damageItCanTake = health - damage` (damage accumulates separately)
- Frozen when: `currentChill >= currentHealth`
- Snipe: instant kill via sniped deadness

- [ ] **Step 1: Copy Card.h from old engine as starting point**

Copy `source/engine/Card.h` to `source/engine_v2/Card.h`. The **public interface** must be preserved exactly (the AI depends on it). The private implementation will be rewritten to match JS logic.

- [ ] **Step 2: Port Card.cpp from Inst.js**

Copy `source/engine/Card.cpp` to `source/engine_v2/Card.cpp` as starting point, then systematically verify each method against `js_engine/Inst.js`:

**Methods to verify/rewrite against JS:**
- `beginTurn()` — compare with Inst.js turn-start logic: lifespan tick, construction tick, delay tick, status reset, health regen. **Must be single-pass** (per-card, not two-pass).
- `useAbility()` — compare with Inst.js ability usage: set status=Assigned, decrease health/charges, apply delay
- `undoUseAbility()` — restore state
- `canBlock()` — compare with `_canBlockAtStartOfPhase()` in State.js: must check construction, delay, alive, AND that status is not Assigned (the defense-reset bug fix)
- `takeDamage()` — fragile vs non-fragile logic from Inst.js
- `isFrozen()` — `currentChill >= currentHealth`
- `isBreachable()` / `canBreachFor()` / `canOverkillFor()` — breach damage calculations

**Critical: `canBlock()` must NOT include the old defense-reset bug.** In JS, a card that used its ability (role=ASSIGNED) cannot block. The old C++ incorrectly reset all statuses before defense.

- [ ] **Step 3: Write Card tests**

Create `source/engine_v2/tests/test_card.cpp`:

```cpp
#include "Card.h"
#include "CardTypeData.h"
#include "CardTypes.h"
#include <cassert>
#include <iostream>

void test_card_construction()
{
    // Create a Drone card
    // Card constructor: (CardType, PlayerID, creationMethod, delay, lifespan)
    Prismata::CardType droneType = Prismata::CardTypes::GetCardType("Drone");
    Prismata::Card drone(droneType, Players::Player_One, 0, 0, 0);

    assert(drone.getType() == droneType);
    assert(drone.getPlayer() == Players::Player_One);
    assert(drone.currentHealth() == 1);
    assert(!drone.isDead());
    assert(drone.canBlock());
    assert(!drone.isUnderConstruction());
    std::cout << "  PASS: test_card_construction" << std::endl;
}

void test_ability_blocks_blocking()
{
    // After using ability, card should NOT be able to block
    // This is the defense-reset bug fix
    Prismata::CardType droneType = Prismata::CardTypes::GetCardType("Drone");
    Prismata::Card drone(droneType, Players::Player_One, 0, 0, 0);

    assert(drone.canBlock());
    assert(drone.canUseAbility());
    drone.useAbility();  // Drone taps for gold
    assert(drone.getStatus() == CardStatus::Assigned);
    assert(!drone.canBlock());  // CRITICAL: assigned cards cannot block
    std::cout << "  PASS: test_ability_blocks_blocking" << std::endl;
}

void test_damage_fragile()
{
    // Tarsier (Tesla Tower): fragile, 1 health
    Prismata::CardType tarsierType = Prismata::CardTypes::GetCardType("Tesla Tower");
    Prismata::Card tarsier(tarsierType, Players::Player_One, 0, 0, 0);

    assert(tarsier.currentHealth() == 1);
    assert(tarsierType.isFragile());
    // Fragile: damage directly reduces health
    std::cout << "  PASS: test_damage_fragile" << std::endl;
}

void test_freeze()
{
    // A card is frozen when currentChill >= currentHealth
    Prismata::CardType wallType = Prismata::CardTypes::GetCardType("Wall");
    Prismata::Card wall(wallType, Players::Player_One, 0, 0, 0);

    assert(!wall.isFrozen());
    // Apply chill damage equal to health
    // (exact chill application depends on GameState, this tests the query)
    std::cout << "  PASS: test_freeze" << std::endl;
}

void run_card_tests()
{
    // Ensure card library is loaded first
    std::cout << "Running Card tests..." << std::endl;
    test_card_construction();
    test_ability_blocks_blocking();
    test_damage_fragile();
    test_freeze();
    std::cout << "All Card tests PASSED" << std::endl;
}
```

- [ ] **Step 4: Build, run, iterate**

Fix any compilation errors. Verify all tests pass. The `test_ability_blocks_blocking` test is the most important — it validates the defense-reset bug is fixed.

- [ ] **Step 5: Commit**

```bash
git add source/engine_v2/Card.* source/engine_v2/tests/test_card.cpp
git commit -m "feat(engine_v2): port Card from Inst.js with defense-reset fix"
```

---

## Task 7: CardBuyable, CardBuyableData, CardData

**Goal:** Copy supply tracking and card storage container. `CardData.h` includes `CardBuyableData.h`, so both must be present.

**Files:**
- Copy from `source/engine/`: `CardBuyable.h/cpp`, `CardBuyableData.h/cpp`, `CardData.h`, `CardData.cpp`

**Important:** `CardData` is NOT header-only. `CardData.cpp` (~330 lines) contains card ID management, killed card removal, and live card tracking. `CardBuyableData` wraps a `vector<CardBuyable>` with lookup methods.

- [ ] **Step 1: Copy files**

Copy from `source/engine/` to `source/engine_v2/`:
- `CardBuyable.h`, `CardBuyable.cpp`
- `CardBuyableData.h`, `CardBuyableData.cpp`
- `CardData.h`, `CardData.cpp`

- [ ] **Step 2: Verify build**

```bash
cmake -B build && cmake --build build
./build/prismata_engine_v2_tests
```

- [ ] **Step 3: Commit**

```bash
git add source/engine_v2/CardBuyable.* source/engine_v2/CardBuyableData.* source/engine_v2/CardData.*
git commit -m "feat(engine_v2): add CardBuyable, CardBuyableData, and CardData"
```

---

## Task 8: GameState — The Core Port

This is the largest task, broken into 7 sub-tasks. GameState is ported from `js_engine/State.js` (1,686 lines), `Controller.js` (2,268 lines), `Analyzer.js` (889 lines), `StateHelper.js` (525 lines), and `EndTurnObject.js` (~204 lines).

**Files:**
- Create: `source/engine_v2/GameState.h` — start from old `source/engine/GameState.h` (public interface), rewrite internals
- Create: `source/engine_v2/GameState.cpp` — clean-room port from JS
- Create: `source/engine_v2/tests/test_game_state.cpp`

**Reference mapping:**

| C++ Method | JS Source | JS Function/Section |
|---|---|---|
| `doAction()` | `State.js:processMove()` + `Controller.js:processClick()` | Switch on move type |
| `isLegal()` | `Controller.js:canAssign()`, `canBuy()`, `canDefend()` etc. | Legality checks |
| `generateLegalActions()` | `Analyzer.js` | Legal move enumeration |
| `beginTurn()` | `State.js:swoosh()` | Resource refresh, card refresh, scripts |
| `endPhase()` | `State.js:MOVE_ENTER_CONFIRM`, `MOVE_COMMIT`, `MOVE_END_DEFENSE` | Phase transitions |
| `calculateGameOver()` | `EndTurnObject.js:checkWin` + stagnation | Win/draw detection |
| Helper queries | `StateHelper.js:update()` | Defense totals, attack potential |

### Task 8a: Phase State Machine

**Goal:** Implement phase transitions: Defense → Swoosh → Action → [Breach] → Confirm.

- [ ] **Step 1: Create GameState.h**

Copy `source/engine/GameState.h` to `source/engine_v2/GameState.h`. The **public interface** must be preserved exactly. Private members will be reimplemented.

- [ ] **Step 2: Create GameState.cpp skeleton**

Create `source/engine_v2/GameState.cpp` with the phase state machine. Reference `State.js` lines 1350-1428 for phase transitions.

Key implementation points:
- `endPhase()` switches on `m_activePhase`:
  - `Phases::Action` → `Phases::Confirm` (runs mana rot, collects bodies, checks win)
  - `Phases::Confirm` → check win, then `++m_turnNumber`, switch active player. If enemy attack > 0: `Phases::Defense`. Else: run `swoosh()`, `Phases::Action`.
  - `Phases::Defense` → run swoosh(), `Phases::Action`
  - `Phases::Breach` → `Phases::Confirm` (collect bodies)
- `m_turnNumber` increments AFTER win check (follows JS, not old C++)
- Defense belongs to the INCOMING player's turn

- [ ] **Step 3: Write phase transition tests**

```cpp
void test_action_to_confirm()
{
    // After Action END_PHASE, should be in Confirm
    // (requires minimal GameState setup)
}

void test_confirm_to_defense()
{
    // After Confirm END_PHASE with enemy attack > 0,
    // active player switches and enters Defense
}

void test_confirm_to_action_skip_defense()
{
    // After Confirm END_PHASE with no enemy attack,
    // active player switches, swoosh runs, enters Action
}
```

- [ ] **Step 4: Build and test**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(engine_v2): implement GameState phase state machine"
```

### Task 8b: Action Handlers

**Goal:** Implement `doAction()` for each ActionType.

**Reference files and line ranges:**
- `State.js:processMove()` — lines 1157-1500, the main switch on move type
- `Controller.js:processClick()` — lines 400-1020, click routing to move handlers
- `Controller.js:canAssign()` — lines 100-200, ability legality
- `Controller.js:canBuy()` — lines 200-300, purchase legality

**Action handler mapping (all 13 ActionTypes):**

| C++ ActionType | JS Handler | JS Location | Key Logic |
|---|---|---|---|
| `BUY` | `MOVE_BUY` | `State.js:~1200` | Create card instance, deduct resources, deduct sac costs, decrement supply |
| `USE_ABILITY` | `MOVE_ASSIGN` | `State.js:~1160` | Call card.useAbility(), run ability script. If card has targetAction, set `m_targetAbilityCardClicked` and wait for SNIPE/CHILL |
| `ASSIGN_BLOCKER` | `MOVE_DEFEND` | `State.js:~1290` | Set card blocking=true, reduce enemy attack by card health. **No status reset before defense.** |
| `ASSIGN_FRONTLINE` | `MOVE_MELEE` | `State.js:~1250` | Assign attacker to frontline |
| `ASSIGN_BREACH` | `MOVE_BREACH_OR_OVERKILL` | `State.js:~1350` | Apply breach/overkill damage to enemy card |
| `WIPEOUT` | `MOVE_WIPEOUT` | `State.js:~1340` | Set glassBroken flag, transition to Breach sub-phase |
| `SNIPE` | targeting | `State.js:~1170` | Kill target card (second step of targeting ability) |
| `CHILL` | targeting | `State.js:~1175` | Apply chill damage to target (second step of targeting) |
| `END_PHASE` | `MOVE_ENTER_CONFIRM`, `MOVE_COMMIT`, `MOVE_END_DEFENSE` | `State.js:~1380-1428` | Delegates to phase state machine (Task 8a) |
| `UNDO_USE_ABILITY` | `MOVE_UNASSIGN` | `State.js:~1180` | Restore card state before ability |
| `UNDO_BREACH` | `MOVE_UNBREACH` | `State.js:~1360` | Undo breach damage |
| `UNDO_CHILL` | `MOVE_UNDISRUPT` | Controller.js | Undo chill damage |
| `SELL` | `MOVE_SELL` | `State.js:~1230` | Return card to supply, refund resources |

- [ ] **Step 1: Implement BUY action**

Port from JS `MOVE_BUY`. Create new card instance, deduct resources (including gold + colored costs), process sac costs (destroy sacrificed cards), decrement supply. Handle buy scripts (some units create other units on purchase).

- [ ] **Step 2: Implement USE_ABILITY and targeting (SNIPE, CHILL)**

Port from JS `MOVE_ASSIGN`. Two-step process:
1. USE_ABILITY on source card: calls `card.useAbility()`, runs ability script. If card has `targetAction` (12 units), set `m_targetAbilityCardClicked = true` and store source card ID.
2. SNIPE: kill target card instantly (deadness = SNIPED).
3. CHILL: apply chill damage to target. Card frozen when `currentChill >= currentHealth`.

- [ ] **Step 3: Implement ASSIGN_BLOCKER**

Port from JS `MOVE_DEFEND`. Card must pass `canBlock()` (not assigned, not under construction, not delayed, alive). Set blocking flag, reduce incoming attack.

- [ ] **Step 4: Implement ASSIGN_BREACH, ASSIGN_FRONTLINE, WIPEOUT**

- WIPEOUT: set `glassBroken` equivalent, report `Phases::Breach` via `getActivePhase()`
- ASSIGN_BREACH: apply breach damage to undefended enemy card
- ASSIGN_FRONTLINE: assign card as frontline attacker

- [ ] **Step 5: Implement END_PHASE**

Delegates to phase state machine from Task 8a based on current phase.

- [ ] **Step 6: Implement undo/sell actions**

UNDO_USE_ABILITY, UNDO_BREACH, UNDO_CHILL, SELL — restore state. Only undo actions the AI actually uses need full implementation.

- [ ] **Step 7: Implement `getClickAction()`**

Port from old `GameState.cpp`. Maps card + current phase → appropriate Action. Used by `AITools.cpp` (2 call sites). ~50 lines.

- [ ] **Step 8: Write per-action tests**

Test each action type in isolation with manually constructed game states. Key test scenarios:
- BUY with sac cost (e.g., buying a unit that requires sacrificing a Drone)
- USE_ABILITY → SNIPE two-step sequence
- ASSIGN_BLOCKER after USE_ABILITY (must fail — defense-reset bug test)
- WIPEOUT → ASSIGN_BREACH sequence

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(engine_v2): implement all action handlers in doAction()"
```

### Task 8c: Swoosh / BeginTurn Scripts

**Goal:** Implement `swoosh()` — resource refresh, card lifecycle, script execution.

Reference: `State.js` swoosh function (lines ~1500-1686).

- [ ] **Step 1: Implement swoosh()**

Port from JS `swoosh()`. **Must be single-pass** (not old C++ two-pass). Per-card in order:
1. Clear damage and chill
2. Tick construction time (if under construction)
3. Tick delay (if delayed)
4. Tick lifespan (if has lifespan) — kill if expired
5. Reset status (Default if has ability, Inert otherwise)
6. Apply health regeneration
7. Run `beginOwnTurnScript` if applicable
8. Process resonance effects

- [ ] **Step 2: Implement script execution**

Port script execution from `State.js`. Scripts can: grant resources, create units, destroy units, apply attack.

- [ ] **Step 3: Write swoosh tests**

Test resource generation (Drone produces gold), attack generation (Tarsier produces attack), lifespan expiry, construction completion.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(engine_v2): implement swoosh with single-pass script execution"
```

### Task 8d: Legality

**Goal:** Implement `isLegal()` and `generateLegalActions()`.

Reference: `Controller.js` (legality checks) and `Analyzer.js` (enumeration).

- [ ] **Step 1: Implement isLegal()**

Port legality checks from `Controller.js`. Each action type has specific conditions:
- BUY: has resources, has supply, correct phase
- USE_ABILITY: card can use ability, not already used, correct phase
- ASSIGN_BLOCKER: card can block, defense phase, card not already assigned
- etc.

- [ ] **Step 2: Implement generateLegalActions()**

Port from `Analyzer.js`. Enumerate all legal actions for the current phase. This is what the AI's MoveIterators call.

- [ ] **Step 3: Write legality tests**

Test that legal actions match expected set for known game states.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(engine_v2): implement isLegal and generateLegalActions"
```

### Task 8e: Win Detection and JSON Serialization

**Goal:** Implement game-over detection including all-units-doomed (missing from old C++), plus `initFromJSON()` / `toJSONString()`.

**Win detection reference:** `State.js:_checkWin()` (line ~1432) — NOT `EndTurnObject.js` (which only stores the result). `StateHelper.js:allOppUnitsDoomed` for the doomed-units check.

- [ ] **Step 1: Implement calculateGameOver()**

Port win detection from `State.js:_checkWin()`:
- Player has 0 alive cards → opponent wins
- **All units doomed** (from `StateHelper.js`): all opponent's units will die (lifespan expiring, no blockers) → instant win. **This is new — missing from old C++.**
- Both players eliminated simultaneously → draw (mutual elimination)

- [ ] **Step 2: Implement initFromJSON() / toJSONString()**

These are critical for the validation harness (Task 10) and `--suggest` CLI mode. The JSON format must be compatible with `js_engine/replay_exporter.js` — the JS→C++ state exchange format. Reference the old `GameState::initFromJSON()` for the expected JSON schema: card arrays with type/health/status/player fields, resources, supply, phase state. Port the parsing logic from the old C++ (it's correct for reading JSON, the bugs are in game logic).

- [ ] **Step 3: Implement isIsomorphic() / isPlayerIsomorphic()**

Used by UCT search for transposition detection. Port from old C++ — these are comparison functions, not game logic. Also ensure `DestroyCardCompare` (card destruction priority comparator, defined in `GameState.h` lines 113-150) compiles against engine_v2 types.

- [ ] **Step 4: Write win detection tests**

Test standard win, all-units-doomed win, mutual elimination draw.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(engine_v2): implement win detection, JSON serialization, isomorphism"
```

### Task 8f: Stagnation Detection

**Goal:** Implement 4-level stagnation counters (missing from old C++).

Reference: `State.js` stagnation constants and logic.

- [ ] **Step 1: Add stagnation tracking to GameState**

From `State.js`:
- `NUM_LEVELS_OF_DRAW_VARIABLES = 4`
- `CUTOFFS_FOR_DRAW = [2, 8, 20, 40]`
- Track 4 levels of progress counters
- Progress events: delay ticked, money stored, lifespan ticked, etc.
- Each level has a cutoff — if no progress at that level for N turns, it's a draw

Add private members for stagnation counters and progress tracking.

- [ ] **Step 2: Integrate stagnation into endPhase/swoosh**

Update progress counters during swoosh and phase transitions.

- [ ] **Step 3: Write stagnation tests**

Test that stagnation is detected at correct thresholds.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(engine_v2): implement 4-level stagnation detection"
```

### Task 8g: Derived/Cached State

**Goal:** Implement cached queries from `StateHelper.js` — defense totals, blockable units, attack potential.

Reference: `StateHelper.js:update()`.

- [ ] **Step 1: Implement helper computations**

Port the key queries the AI uses:
- `getTotalAvailableDefense()` — sum of blockable units' health
- `getAttack()` — current attack pool
- `hasBreachableCard()` / `canOverkillEnemyCard()` — breach phase queries
- Card counting: `numCardsOfType()`, `numCompletedCardsOfType()`

These can be computed on-demand or cached and invalidated when state changes.

- [ ] **Step 2: Write integration test with manually constructed game state**

Create a test that constructs a GameState programmatically (via `initFromJSON()` with a hand-crafted JSON state), plays a short sequence of actions (e.g., Drone ability → buy Tarsier → end phase → commit), and verifies the resulting state. This validates that all sub-systems work together before the replay harness exists.

Note: Full replay validation happens in Task 10, which adds the name translation layer and replay loader.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(engine_v2): implement derived state queries and integration test"
```

---

## Task 9: Player, Game, Prismata Init

**Goal:** Copy remaining infrastructure and verify full engine compiles.

**Files:**
- Copy from `source/engine/`: `Player.h/cpp`, `Game.h/cpp`, `Prismata.h/cpp`, `Timer.h/cpp`

- [ ] **Step 1: Copy infrastructure files**

Copy from `source/engine/` to `source/engine_v2/`:
- `Player.h`, `Player.cpp`
- `Game.h`, `Game.cpp`
- `Prismata.h`, `Prismata.cpp`
- `Timer.h`, `Timer.cpp`

- [ ] **Step 2: Update Prismata.h umbrella includes**

Verify `Prismata.h` includes point to the correct engine_v2 headers (they should, via bare includes resolved by CMake include path).

- [ ] **Step 3: Verify full engine compiles**

```bash
cmake --build build
./build/prismata_engine_v2_tests
```

All tests from previous tasks should still pass.

- [ ] **Step 4: Commit**

```bash
git add source/engine_v2/Player.* source/engine_v2/Game.* source/engine_v2/Prismata.* source/engine_v2/Timer.*
git commit -m "feat(engine_v2): add Player, Game, Prismata init, Timer"
```

---

## Task 10: Validation Harness

**Goal:** Build the replay validation harness with per-turn state comparison and name translation.

**Files:**
- Create: `source/engine_v2/tests/replay_validator.cpp`
- Create: `source/engine_v2/tests/name_translation.h` — hardcoded UIName↔internal name map

### Name Translation Table

The 116-unit mapping is frozen. Source: `bin/asset/config/cardLibrary.jso`.

- [ ] **Step 1: Build name translation table**

Create `source/engine_v2/tests/name_translation.h` with a hardcoded `std::unordered_map<std::string, std::string>` mapping display names to internal names. Generate this by parsing `cardLibrary.jso` once and hardcoding the result.

For base units where UIName is absent, internal name = display name (e.g., "Drone" → "Drone").
For dominion units, map UIName → key (e.g., "Tarsier" → "Tesla Tower", "Synthesizer" → "Factory").

- [ ] **Step 2: Build replay loader**

Create `source/engine_v2/tests/replay_validator.cpp`:
- Load replay JSON (from `c:\libraries\prismata-replay-parser\replays_archive\` or `training/data/dataset_validation.json`)
- Initialize GameState from replay's initial state
- Apply each action (translating display names to internal names)
- At each turn boundary, capture full state snapshot

- [ ] **Step 3: Implement per-turn state comparison**

At each turn boundary, compare:
- Resources (all 6 types, both players)
- Card states (health, chill, damage, status, lifespan, charges, delay, construction)
- Phase, active player
- Attack totals
- Supply counts
- Game outcome

On mismatch, dump both states and the diverging action.

- [ ] **Step 4: Add CLI arg handling to test runner**

Update `test_main.cpp` to parse `--validate-replays <tier>` arguments. When present, run the replay validator instead of unit tests. Tiers: `smoke` (100-500 replays), `milestone` (~5,000), `full` (102,697).

- [ ] **Step 5: Run smoke tier (~100-500 replays)**

```bash
./build/prismata_engine_v2_tests --validate-replays smoke
```

Fix failures iteratively. Each failure should pinpoint the exact turn and action where divergence occurs.

- [ ] **Step 6: Run milestone tier (~5,000 replays)**

```bash
./build/prismata_engine_v2_tests --validate-replays milestone
```

- [ ] **Step 6: Commit**

```bash
git add source/engine_v2/tests/replay_validator.cpp source/engine_v2/tests/name_translation.h
git commit -m "feat(engine_v2): add replay validation harness with name translation"
```

---

## Task 11: AI Layer Integration

**Goal:** Link `source/ai/` against `engine_v2/` and run tournament games.

**Files:**
- Modify: `source/ai/AIParameters.h` — update include path
- Modify: `source/ai/PrismataAI.h` — update include path
- Modify: `CMakeLists.txt` — add AI and testing sources

- [ ] **Step 1: Update hardcoded include paths**

In `source/ai/AIParameters.h`: change `#include "../engine/Prismata.h"` → `#include "../engine_v2/Prismata.h"`
In `source/ai/PrismataAI.h`: change `#include "../engine/Prismata.h"` → `#include "../engine_v2/Prismata.h"`

- [ ] **Step 2: Update CMakeLists.txt**

Add AI and testing sources to the build:

```cmake
# AI sources
file(GLOB AI_SOURCES CONFIGURE_DEPENDS "source/ai/*.cpp")

# Testing sources (tournament runner, --suggest CLI)
file(GLOB TESTING_SOURCES CONFIGURE_DEPENDS "source/testing/*.cpp")

# Full selfplay/tournament executable — links engine_v2 static library
add_executable(prismata_selfplay
    ${AI_SOURCES}
    ${TESTING_SOURCES}
)
target_link_libraries(prismata_selfplay engine_v2)

target_compile_definitions(prismata_selfplay PRIVATE
    $<$<CONFIG:Debug>:PRISMATA_ASSERT_ALL>
)
```

- [ ] **Step 3: Fix compilation errors**

Build and fix any interface mismatches. Common issues:
- Missing methods in engine_v2 that AI expects
- Enum value differences
- Return type mismatches
- Missing `#include` paths

Each fix goes in `source/engine_v2/`, NOT in `source/ai/`.

- [ ] **Step 4: Fix source/testing/main.cpp Linux portability**

The Windows-specific `_dup()`, `_dup2()`, `_fileno()`, `_close()` calls need `#ifdef _WIN32` / `#else` guards using POSIX equivalents (`dup()`, `dup2()`, `fileno()`, `close()`).

- [ ] **Step 5: Run a tournament**

```bash
./build/prismata_selfplay
```

With a tournament config in `bin/asset/config/config.txt`, run a small tournament (e.g., `OriginalHardestAI` vs `OriginalHardestAI`, 10 games). Verify games complete without crashes.

- [ ] **Step 6: Run full replay validation**

```bash
./build/prismata_engine_v2_tests --validate-replays full
```

Run the full 102,697 replay archive. Target: 100% pass rate.

- [ ] **Step 7: Commit**

```bash
git add source/ai/AIParameters.h source/ai/PrismataAI.h CMakeLists.txt source/testing/main.cpp
git commit -m "feat: integrate AI layer with engine_v2, fix Linux portability"
```

---

## Task 12: NeuralNet Singleton → Instance Refactor

**Goal:** Allow two different NN players in one process.

**Files:**
- Modify: `source/ai/NeuralNet.h`
- Modify: `source/ai/NeuralNet.cpp`
- Modify: `source/ai/Eval.h`
- Modify: `source/ai/Eval.cpp`
- Modify: `source/ai/AIParameters.cpp`
- Modify: All Player files that call Eval functions with NN

- [ ] **Step 1: Audit NeuralNet mutable state**

Read `source/ai/NeuralNet.h/cpp`. Confirmed: `mutable ScratchBuffers _scratch` exists. This means concurrent reads on the same instance are NOT safe. Players on different threads need separate instances.

- [ ] **Step 2: Grep all NeuralNet::Instance() call sites**

```bash
grep -rn "NeuralNet::Instance" source/ai/
```

Build the complete change list.

- [ ] **Step 3: Refactor NeuralNet class**

Remove the singleton pattern:
- Remove `static NeuralNet& Instance()`
- Make constructor public
- Add `loadWeights(const std::string& path)` if not already public
- Keep scratch buffers as instance members (each instance gets its own)

- [ ] **Step 4: Update Eval function signatures**

Change Eval functions from calling `NeuralNet::Instance()` internally to accepting a `NeuralNet*` parameter:

```cpp
// Before:
EvaluationType Eval::NeuralNetEval(const GameState& state, PlayerID maxPlayer);

// After:
EvaluationType Eval::NeuralNetEval(const GameState& state, PlayerID maxPlayer, NeuralNet* nn);
```

- [ ] **Step 5: Update all call sites**

Update UCTSearch, StackAlphaBetaSearch, and Player classes to pass their NeuralNet instance through to Eval functions.

- [ ] **Step 6: Update AIParameters to construct NeuralNet instances**

`AIParameters` already parses per-player `"WeightsFile"` config. Add logic to:
- Create a **separate `NeuralNet` instance per player** (not per weight file)
- Each instance loads its own copy of the weights and has its own scratch buffers
- This is required because `mutable ScratchBuffers _scratch` makes concurrent reads on the same instance unsafe (see spec Section 6.5)
- A weight-deduplication optimization (sharing read-only weight data across instances while keeping separate scratch buffers) is possible but deferred — just load independently for now

- [ ] **Step 7: Test with two different NN players**

Configure two players with different weight files in `config.txt`. Run a tournament. Both should load their respective weights and play without crashes.

- [ ] **Step 8: Commit**

```bash
git add source/ai/NeuralNet.* source/ai/Eval.* source/ai/AIParameters.cpp source/ai/Player_*.cpp source/ai/UCTSearch.cpp source/ai/StackAlphaBetaSearch.cpp
git commit -m "feat: refactor NeuralNet from singleton to instance-based"
```

---

## Completion Checklist

After all tasks are complete, verify:

- [ ] Engine_v2 compiles on Linux via CMake
- [ ] All unit tests pass
- [ ] Full replay archive (102,697 replays) validates at 100% pass rate
- [ ] Tournament games complete without crashes
- [ ] Two NN players with different weights can play in one process
- [ ] Old VS solution still builds `Prismata_GUI.exe` against `source/engine/` (untouched)
- [ ] `--suggest` CLI mode works with engine_v2
