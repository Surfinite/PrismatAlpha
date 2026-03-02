# Phase 3.5: cardLibrary.jso Parsing Parity Audit (AS3 vs C++)

**Date:** 2026-02-22
**Scope:** All 161 units in `bin/asset/config/cardLibrary.jso`
**Files examined:**
- `source/engine/CardTypeInfo.cpp` / `.h` -- C++ JSON parsing constructor
- `source/engine/JSONTools.cpp` / `.h` -- C++ JSON helper functions
- `source/engine/Condition.cpp` / `.h` -- C++ targeting condition parsing
- `source/engine/Script.cpp` / `.h` -- C++ script (delay, selfsac) parsing
- `source/engine/ScriptEffect.cpp` / `.h` -- C++ script effect parsing
- `source/engine/CardType.cpp` -- C++ accessors (notably `getChargeUsed()`)
- `source/engine/Constants.h` -- Supply/rarity constants
- `prismata_decompiled/scripts/mcds/engine/Card.as` -- AS3 card data parsing
- `prismata_decompiled/scripts/mcds/engine/State.as` -- AS3 game state logic
- `prismata_decompiled/scripts/mcds/engine/Controller.as` -- AS3 game controller
- `prismata_decompiled/scripts/mcds/engine/Inst.as` -- AS3 instance logic

---

## 1. Field Inventory Table

All 34 unique keys found in `cardLibrary.jso` across 161 units:

| JSON Field | Count | C++ Reads? | C++ Target | Default if Missing (C++) | AS3 Reads? | Default if Missing (AS3) | Gameplay? |
|---|---|---|---|---|---|---|---|
| `rarity` | 161 | Yes | `rarity` (string) | `"unbuyable"` | Yes | `RARITY_UNBUYABLE` (int) | Yes |
| `defaultBlocking` | 161 | Yes | `defaultBlocking` (bool via ReadIntBool) | `false` | Yes | `false` (spell) / direct (unit) | Yes |
| `buyCost` | 158 | Yes | `buyCost` (Resources via ReadMana) | empty Resources | Yes | empty Mana | Yes |
| `toughness` | 156 | Yes | `startingHealth` AND `healthMax` | `1` (header default) | Yes | `1` | Yes |
| `assignedBlocking` | 93 | Yes | `assignedBlocking` (bool via ReadIntBool) | `false` | Yes | `false` | Yes |
| `abilityScript` | 85 | Yes | `abilityScript` (Script + ScriptEffect) | NullScript | Yes | `null` | Yes |
| `UIName` | 78 | Yes | `uiName` (string) | cardName | Yes | cardName | No (display) |
| `beginOwnTurnScript` | 69 | Yes | `beginOwnTurnScript` (Script + ScriptEffect) | NullScript | Yes | `null` | Yes |
| `needs` | 66 | **No** | -- | -- | Yes | empty Array | No (deck composition hint) |
| `buildTime` | 58 | Yes | `buildTime` (TurnType) | `1` (header default); `0` if spell | Yes | `1`; spell sets it from JSON if present | Yes |
| `score` | 49 | **No** | -- | -- | **No** | -- | No (AI heuristic, unused by either) |
| `abilityCost` | 35 | Yes | `abilityCost` (Resources via ReadMana) | empty Resources | Yes | empty Mana | Yes |
| `fragile` | 32 | Yes | `fragile` (bool via ReadIntBool) | `false` | Yes | `false` | Yes |
| `lifespan` | 29 | Yes | `lifespan` (TurnType) | `0` (meaning unlimited) | Yes | `-1` (meaning unlimited) | Yes |
| `UIShortname` | 19 | Yes | `uiShortName` (string) | uiName | Yes | UIName | No (display) |
| `buyScript` | 19 | Yes | `buyScript` (Script + ScriptEffect) | NullScript | Yes | `null` | Yes |
| `buySac` | 18 | Yes | `buySac` (vector<SacDescription>) | empty vector | Yes | empty Vector | Yes |
| `abilitySac` | 15 | Yes | `abilitySac` (vector<SacDescription>) | empty vector | Yes | empty Vector | Yes |
| `targetAction` | 12 | Yes | `targetAction` (string) + `targetActionType` (enum) | `""` / `ActionTypes::NONE` | Yes | `TARGETACTION_NONE` | Yes |
| `baseSet` | 11 | Yes | `isBaseSet` (bool via ReadIntBool) | `false` | Yes | `false` | No (UI grouping) |
| `undefendable` | 11 | Yes | `frontline` (bool via ReadIntBool) | `false` | Yes | `false` | Yes |
| `targetAmount` | 10 | Yes | `targetAmount` (HealthType via ReadInt) | `0` | Yes | direct read | Yes |
| `charge` | 9 | Yes | `startingCharge` (ChargeType via ReadInt) | `0` | Yes | `0` | Yes |
| `spell` | 9 | Yes | `isSpell` (bool via ReadIntBool) | `false` | Yes | check via `hasOwnProperty` | Yes |
| `description` | 8 | Yes | `description` (string) | `""` | Yes | `null` | No (tooltip text) |
| `HPUsed` | 5 | Yes | `healthUsed` (HealthType via ReadInt) | `0` | Yes (only if fragile) | `0` | Yes |
| `group` | 5 | **No** | -- | -- | **No** | -- | No (UI grouping) |
| `resonate` | 4 | Yes | `resonateCardName` (string) + resonate effect | `""` | Yes | `null` | Yes |
| `HPGained` | 3 | Yes | `healthGained` (HealthType via ReadInt) | `0` | Yes (only if fragile) | `0` | Yes |
| `condition` | 2 | Yes | `targetAbilityCondition` (Condition) | default Condition | Yes | `null` then populated | Yes |
| `HPMax` | 2 | Yes | `healthMax` (HealthType via ReadInt) | `startingHealth` (toughness) | Yes (only if fragile) | `startingHealth` | Yes |
| `potentiallyMoreAttack` | 1 | Yes | `potentiallyMoreAttack` (bool via ReadIntBool) | `false` | Yes | `false` | No (AI hint) |
| `goldResonate` | 1 | Yes | `resonateCardName` (string) + gold resonate effect | `""` | Yes | `null` | Yes |
| `abilityNetherfy` | 1 | Yes | Special-case Deadeye script injection | -- | Yes | `false` | Yes |

### Fields in AS3 but NOT in cardLibrary.jso (latent capabilities)

| AS3 Field | In cardLibrary.jso? | In C++? | Impact |
|---|---|---|---|
| `chargeUsed` | No (0 units) | No (hardcoded to `1`) | **Latent gap** -- see Finding F1 |
| `chargeGained` | No (0 units) | No | **Latent gap** -- see Finding F2 |
| `chargeMax` | No (0 units) | No | **Latent gap** -- see Finding F2 |
| `deathScript` | No (0 units) | No | **Latent gap** -- see Finding F3 |
| `nameIn` (condition) | No (0 units) | No | Latent gap (no current units use it) |
| `isEngineerTempHack` (condition) | No (0 units) | No | Latent gap (no current units use it) |
| `plural` | No (0 units) | No | No (display only) |
| `UIArt` | No (0 units) | No | No (display only) |
| `fullDescription` | No (0 units) | No | No (display only) |
| `ignoreFullDescription` | No (0 units) | No | No (display only) |
| `irregular` | No (0 units) | No | No (display only) |
| `position` | No (0 units) | No | No (UI layout only) |

---

## 2. Missing Fields (AS3 reads, C++ ignores)

### Gameplay-affecting fields absent from C++

**F1: `chargeUsed` -- NOT PARSED, HARDCODED**

- **AS3 behavior:** Reads `chargeUsed` from JSON (Card.as:186-192). Defaults to `1` if absent. Uses it throughout: ability legality check (Controller.as:1433), charge deduction (State.as:1467-1469), undo (State.as:1555-1557), StateHelper attack potential calculations (StateHelper.as:236, 332, 392, 514).
- **C++ behavior:** `CardType::getChargeUsed()` is **hardcoded to `return 1;`** (CardType.cpp:302-305). Not read from JSON at all.
- **Current impact: NONE.** No units in `cardLibrary.jso` specify `chargeUsed`. All charge-using units (Elephant/Rhino, Charged Drone, Deadeye, Twin-Barrel Mech, Corpus, Elephant Graveyard, Ephemeron, Sentinel, Bombarder) have the implicit default of 1.
- **Risk:** If a future unit requires `chargeUsed != 1`, the C++ engine would silently use 1, producing incorrect ability legality checks.

**F2: `chargeGained` and `chargeMax` -- NOT PARSED**

- **AS3 behavior:** Reads `chargeGained` (Card.as:194-196) and `chargeMax` (Card.as:198-204). `chargeMax` defaults to `startingCharge` if absent. Used for per-turn charge regeneration (State.as:2726-2731) and charge cap enforcement (State.as:3987-3989). StateHelper uses these to predict future ability availability (StateHelper.as:236, 392, 514).
- **C++ behavior:** Neither field is read from JSON. No charge regeneration mechanism exists. `m_currentCharges` only decreases (on ability use) and increases (on undo).
- **Current impact: NONE.** No units in `cardLibrary.jso` specify `chargeGained` or `chargeMax`. All current charge-using units have non-regenerating stamina.
- **Risk:** If a future unit requires charge regeneration (e.g., "regain 1 stamina per turn"), the C++ engine would not support it. The game has no such unit currently, but the AS3 engine fully supports the mechanic.

**F3: `deathScript` -- NOT PARSED**

- **AS3 behavior:** Reads `deathScript` (Card.as:320-322) and executes it when a unit dies during breach/overkill (State.as:1805-1807, Controller.as:1753, 1770, 1782, 1820, 1837, 1849, and many more). The deathScript is run forward on kill and backward on undo. It's also set as the abilityScript (`this.abilityScript = this.deathScript = new Script(obj.deathScript)`).
- **C++ behavior:** No reference to `deathScript` anywhere in the C++ codebase.
- **Current impact: NONE.** No units in `cardLibrary.jso` have `deathScript`.
- **Risk:** If a future unit has a death trigger, the C++ engine would silently ignore it.

### Non-gameplay fields absent from C++

- `needs` (66 units): Deck composition hints for the randomizer. Not needed for game simulation.
- `score` (49 units): Heuristic scoring values. C++ has its own `customScore` system (not present in this dataset). AS3 also ignores `score`.
- `group` (5 units): UI grouping labels. Display only.

---

## 3. Type Coercion Risks

### 3a: Boolean fields stored as integers in JSON

All boolean-like fields in `cardLibrary.jso` are stored as **JSON integers** (0 or 1), except `abilityNetherfy` which is a JSON `true` (boolean).

| Field | JSON Type | C++ Parser | AS3 Parser | Risk |
|---|---|---|---|---|
| `defaultBlocking` | int (0/1) | `ReadIntBool` -- asserts IsInt, converts `!= 0` | Direct truthy assignment (`obj.defaultBlocking`) | **SAFE** -- both interpret correctly |
| `assignedBlocking` | int (0/1) | `ReadIntBool` | `obj.assignedBlocking == true` | **SAFE** -- AS3 `1 == true` is truthy in Flash |
| `fragile` | int (1 only) | `ReadIntBool` | `obj.fragile == true` | **SAFE** |
| `undefendable` | int (1 only) | `ReadIntBool` | `obj.undefendable == true` | **SAFE** |
| `spell` | int (1 only) | `ReadIntBool` | `obj.spell == true` | **SAFE** |
| `baseSet` | int (1 only) | `ReadIntBool` | `obj.baseSet == true` | **SAFE** |
| `potentiallyMoreAttack` | int (1 only) | `ReadIntBool` | `obj.potentiallyMoreAttack == true` | **SAFE** |
| `abilityNetherfy` | **bool** (true) | Special case: `value["abilityNetherfy"].IsBool() && .GetBool()` | `obj.abilityNetherfy == true` | **SAFE** -- C++ explicitly checks IsBool() |

Note: `ReadIntBool` would fail (PRISMATA_ASSERT) if `abilityNetherfy` were parsed through it, since it asserts `IsInt()`. The special-case handling in CardTypeInfo.cpp:85 correctly uses `IsBool()` + `GetBool()`. This is intentional.

### 3b: `toughness` / `healthMax` double-read pattern

C++ reads `toughness` into **both** `startingHealth` and `healthMax` (CardTypeInfo.cpp:25-26), then reads `HPMax` to override `healthMax` (line 29). This means:
- If no `HPMax`: `healthMax = startingHealth` (from toughness). Matches AS3 (Card.as:180-181).
- If `HPMax` present: `healthMax` is overridden. Matches AS3 (Card.as:175-177).

This is correct and safe. The double-read is an optimization to avoid a separate "if HPMax is absent, set healthMax = startingHealth" block.

### 3c: `lifespan` sentinel value difference

- **C++:** `0` means unlimited (no lifespan). Field default is `0`.
- **AS3:** `-1` means unlimited (no lifespan). Set to `-1` for spells and for units without `lifespan` in JSON.
- **Conversion:** C++ outputs `-1` in game state JSON (`lifespan == 0 ? -1 : lifespan`, Card.cpp:988). C++ reads `-1` from game state JSON and converts to `0` (Card.cpp:87: `lifespanVal == -1 ? 0 : val.GetInt()`).
- **Risk: NONE for cardLibrary.jso parsing.** Both engines correctly handle units with and without `lifespan`. The sentinel difference only matters at the game state JSON interchange layer, which is already handled.

### 3d: `condition.isABC` -- int in JSON, bool in AS3 comparison

- JSON: `"isABC": 1` (integer)
- C++: `value["isABC"].IsInt()` then `GetInt() == 1` (Condition.cpp:34-36). Correct.
- AS3: `obj.condition.isABC == true` (Card.as:353). In AS3, `1 == true` evaluates to `true` due to type coercion.
- **Risk: NONE.** Both interpret correctly.

### 3e: `receive` field in scripts -- string vs int

Some units have `"receive"` as a string (`"receive":"1"`), others as an int (`"receive":1`). Examples:
- Drone: `"receive":"1"` (string)
- Wild Drone: `"receive":1` (int)
- Flying Drone: `"receive":1` (int)
- Trinity Drone: `"receive":3` (int)

C++ `Resources` constructor handles both via `ReadMana`: asserts `IsString() || IsInt()` (JSONTools.cpp:73). AS3 Mana constructor handles both via dynamic typing.
- **Risk: NONE.** Both engines handle both types correctly.

### 3f: `HPUsed`/`HPGained`/`HPMax` -- C++ reads unconditionally, AS3 reads only if fragile

- **C++:** Reads `HPUsed`, `HPGained`, `HPMax` unconditionally for all units (CardTypeInfo.cpp:27-29).
- **AS3:** Only reads these inside the `if(this.fragile)` block (Card.as:163-181). Non-fragile units never get these fields set.
- **Current impact: NONE.** All 5 units with `HPUsed`, all 3 with `HPGained`, and both with `HPMax` are fragile. If a non-fragile unit ever had `HPUsed`, C++ would read it but AS3 would ignore it. However, `HPUsed` for non-fragile units is semantically meaningless in Prismata's game rules.

---

## 4. Sample Verification

### Sample 1: Drone (simple base-set unit)

**JSON:**
```json
"Drone" : {
    "baseSet" : 1, "rarity" : "trinket", "toughness" : 1,
    "defaultBlocking" : 1, "assignedBlocking" : 0,
    "buyCost" : "3H", "abilityScript" : {"receive":"1"}
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `startingHealth` | 1 (from toughness) | OK |
| `healthMax` | 1 (toughness, no HPMax) | OK |
| `defaultBlocking` | true (ReadIntBool, 1 != 0) | OK |
| `assignedBlocking` | false (ReadIntBool, 0 == 0) | OK |
| `fragile` | false (absent) | OK |
| `buyCost` | Resources("3H") = 3 gold + 1 energy | OK |
| `abilityScript` | Script with ScriptEffect.receive = Resources("1") = 1 gold | OK |
| `supply` | 20 (trinket) | OK |
| `buildTime` | 1 (default, absent) | OK |
| `lifespan` | 0 (default, unlimited) | OK |
| `isBaseSet` | true | OK |
| `isEconCard` | true (hasAbility, produces gold, no cost, no attack, no sac) | OK |

**PASS**

### Sample 2: Conduit (fragile, beginOwnTurnScript, no ability)

**JSON:**
```json
"Conduit" : {
    "baseSet" : 1, "rarity" : "normal", "toughness" : 3,
    "defaultBlocking" : 0, "fragile" : 1,
    "buyCost" : "4", "beginOwnTurnScript" : {"receive":"G"}, "score" : "3"
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `startingHealth` | 3 | OK |
| `healthMax` | 3 (toughness, no HPMax, no HPGained) | OK |
| `defaultBlocking` | false | OK |
| `fragile` | true | OK |
| `buyCost` | Resources("4") = 4 gold | OK |
| `beginOwnTurnScript` | Script with receive = Resources("G") = 1 green | OK |
| `hasBeginOwnTurnScript` | true | OK |
| `supply` | 10 (normal) | OK |
| `buildTime` | 1 (default) | OK |
| `isTech` | false -- wait, Constants say Academy/Brooder/Conduit are tech! | **SEE NOTE** |
| `score` | ignored by C++ (no `customScore` key) | OK (field not gameplay) |

**NOTE on isTech:** CardTypeInfo.cpp:129 hardcodes `isTech = true` for "Academy", "Brooder", and "Conduit". This correctly identifies Conduit (the internal name) as tech. The check uses the internal `name` parameter, which is "Conduit" for the JSON key. **OK.**

**PASS**

### Sample 3: Xaetron (fragile + HPUsed + HPGained + HPMax + ability create)

**JSON:**
```json
"Xaetron" : {
    "rarity" : "legendary", "toughness" : 4,
    "defaultBlocking" : 1, "assignedBlocking" : 0, "fragile" : 1,
    "buyCost" : "11GGGGG", "buildTime" : 0,
    "HPGained" : 4, "HPMax" : 12, "HPUsed" : 7,
    "abilityScript" : {"create":[["Flame Kin","own",5]]},
    "needs" : ["Flame Kin"]
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `startingHealth` | 4 (from toughness) | OK |
| `healthMax` | 12 (toughness sets to 4, then HPMax overrides to 12) | OK |
| `healthGained` | 4 | OK |
| `healthUsed` | 7 | OK |
| `fragile` | true | OK |
| `defaultBlocking` | true | OK |
| `assignedBlocking` | false | OK |
| `buyCost` | Resources("11GGGGG") = 11 gold + 5 green | OK |
| `buildTime` | 0 | OK |
| `supply` | 1 (legendary) | OK |
| `abilityScript` | Script with ScriptEffect containing CreateDescription("Flame Kin", own, 5) | OK |
| `isAbilityHealthUserOnly` | Check: hasAbility=true, fragile=true, !defaultBlocking=**false**. Fails `!defaultBlocking` check. Result: **false** | OK (correctly not flagged) |

**PASS**

### Sample 4: Arsonist / Kinetic Driver (snipe + condition + lifespan + abilityCost)

**JSON:**
```json
"Arsonist" : {
    "rarity" : "rare", "toughness" : 1,
    "defaultBlocking" : 0, "assignedBlocking" : 0,
    "lifespan" : 6, "buyCost" : "5G",
    "beginOwnTurnScript" : {"receive":"A"},
    "abilityScript" : {"selfsac":true},
    "abilityCost" : "2",
    "targetAction" : "snipe",
    "condition" : {"isABC":1},
    "description" : "Destroy any Animus, Blastforge, or Conduit.",
    "UIName" : "Kinetic Driver"
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `startingHealth` | 1 | OK |
| `lifespan` | 6 | OK |
| `targetAction` | "snipe" | OK |
| `targetActionType` | `ActionTypes::SNIPE` (CardTypeInfo.cpp:126) | OK |
| `targetAbilityCondition._isTech` | true (isABC=1, Condition.cpp:35) | OK |
| `targetAbilityCondition._notBlocking` | false (absent) | OK |
| `targetAbilityCondition._hasHealthCondition` | false (absent) | OK |
| `abilityScript` | Script with `_selfSac = true`, no ScriptEffect | OK |
| `abilityCost` | Resources("2") = 2 gold | OK |
| `beginOwnTurnScript` | Script with receive = Resources("A") = 1 attack | OK |
| `supply` | 4 (rare) | OK |
| `uiName` | "Kinetic Driver" | OK |

**PASS**

### Sample 5: Distractocell / Cryo Cell (disrupt + lifespan + target amount)

**JSON:**
```json
"Distractocell" : {
    "rarity" : "trinket", "toughness" : 1,
    "defaultBlocking" : 0, "assignedBlocking" : 0,
    "buyCost" : "G", "abilityScript" : {"selfsac":true},
    "targetAction" : "disrupt", "targetAmount" : 1,
    "lifespan" : 1, "UIName" : "Cryo Cell"
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `startingHealth` | 1 | OK |
| `lifespan` | 1 | OK |
| `targetAction` | "disrupt" | OK |
| `targetActionType` | `ActionTypes::CHILL` (CardTypeInfo.cpp:127) | OK |
| `targetAmount` | 1 | OK |
| `abilityScript` | Script with `_selfSac = true` | OK |
| `supply` | 20 (trinket) | OK |
| `buyCost` | Resources("G") = 1 green | OK |
| `isAbilityHealthUserOnly` | Check: targetActionType != NONE (true), fragile=**false**. Fails. Result: **false** | OK |

**PASS**

### Bonus: Nether Warrior / Deadeye Operative (abilityNetherfy special case)

**JSON:**
```json
"Nether Warrior" : {
    "UIName" : "Deadeye Operative", "rarity" : "rare", "toughness" : 2,
    "defaultBlocking" : 1, "assignedBlocking" : 0, "buyCost" : "5BB",
    "description" : "Destroy a non-blocking Drone.",
    "abilityScript" : {}, "abilityNetherfy" : true,
    "UIShortname" : "Deadeye Op.", "needs" : ["Drone"], "charge" : 3
}
```

| Field | Expected C++ Value | Verified |
|---|---|---|
| `abilityNetherfy` | true (JSON bool, CardTypeInfo.cpp:85 checks IsBool + GetBool) | OK |
| Special-case script | Hardcoded destroy script injected (CardTypeInfo.cpp:87-94) | OK |
| `startingCharge` | 3 | OK |
| `supply` | 4 (rare) | OK |

C++ parses the empty `abilityScript: {}` first (producing a ScriptEffect with no effect), then the abilityNetherfy special case replaces the script effect with a hardcoded `destroy` targeting non-blocking Drone. This matches AS3's behavior where `abilityNetherfy` triggers special-case Drone destruction logic.

**PASS**

---

## 5. Additional Findings

### F4: C++ reads `HPUsed`/`HPGained`/`HPMax` unconditionally; AS3 only reads if fragile

C++ (CardTypeInfo.cpp:27-29) reads these three fields for all units without checking `fragile` first. AS3 (Card.as:163-181) only reads them inside the `if(this.fragile)` block. Since all units with these fields are fragile in the current dataset, behavior is equivalent. If a non-fragile unit ever had `HPUsed`, C++ would apply it as an ability health cost while AS3 would ignore it. This is an academic difference only.

### F5: Spell `buildTime` handling differs slightly

- **C++:** Reads `buildTime` from JSON first (line 31), then overrides to `0` if `spell` is present (lines 70-73). The JSON value is read but immediately overwritten.
- **AS3:** Reads `buildTime` outside the spell/unit branch (lines 220-227), so spells can have `buildTime` from JSON.
- **Current impact: NONE.** All 9 spells in cardLibrary.jso either have `"buildTime": 0` explicitly or don't specify it (default 1, but C++ overrides to 0). The AS3 engine would use the JSON value for spells; C++ always forces 0. Since all spells are instant (buildTime 0 in JSON), no difference occurs.
- **Risk:** If a spell ever had `buildTime > 0` in JSON (a delayed spell), C++ would force it to 0 while AS3 would respect it. This would be a gameplay difference. However, Prismata's game rules define spells as always instant, so this is purely theoretical.

### F6: `abilityScript: {}` (empty object) handling

Nether Warrior has `"abilityScript": {}`. In C++, `ReadScript` creates a Script, `ReadScriptEffect` creates a ScriptEffect -- both with no effect. Then the `abilityNetherfy` special case overrides the script effect. In AS3, `Boolean(obj.abilityScript)` evaluates to `true` for an empty object, so `new Script({})` is created, then `deathScript` check (not present) is skipped, and the empty script remains. The `abilityNetherfy` flag triggers separate Drone destruction logic elsewhere.

Both engines correctly handle this unit, just through different mechanisms.

### F7: `Condition.nameIn` not parsed by C++

AS3 Card.as:349 reads `condition.nameIn` for snipe targeting. C++ Condition.cpp does not parse `nameIn`. No current units use this field. If a future unit required snipe targeting by name list, C++ would silently ignore the condition, making the snipe target any unit instead of the restricted set.

---

## 6. Summary of Gaps

| Gap | Severity | Current Impact | Future Risk |
|---|---|---|---|
| F1: `chargeUsed` hardcoded to 1 | Low | None (all units default to 1) | Low (no known planned units need != 1) |
| F2: `chargeGained`/`chargeMax` missing | Medium | None (no current units) | Medium (charge regen mechanic unsupported) |
| F3: `deathScript` missing | Medium | None (no current units) | Medium (death triggers unsupported) |
| F4: `HPUsed` read unconditionally | Negligible | None | Negligible |
| F5: Spell `buildTime` forced to 0 | Negligible | None | Negligible |
| F7: `Condition.nameIn` missing | Low | None (no current units) | Low |

---

## 7. Verdict

**PASS** -- For the current 161-unit `cardLibrary.jso` dataset, C++ parsing parity with AS3 is **complete for all gameplay-relevant fields**. Every field present in the current JSON data is correctly read by the C++ engine with correct types, defaults, and semantic behavior.

The three latent gaps (`chargeUsed` hardcoding, `chargeGained`/`chargeMax` absence, `deathScript` absence) are capabilities that the AS3 engine supports but the C++ engine does not. None of these gaps affect any current unit. They would only become bugs if the `cardLibrary.jso` data were extended with units using these features, which is unlikely given that Prismata is no longer in active development.

No code changes are recommended.
