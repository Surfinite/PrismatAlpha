# Context 4: Engine Fidelity Validation

## Goal

Verify that the PrismataAI C++ engine correctly simulates the same game as live Prismata. If the engine has mechanical bugs, everything downstream (AI evaluation, training data, tournament results) is built on a broken foundation.

## Approach

Replay 100 real games (Surfinite vs various opponents, including masterbot) through both:
1. The **TypeScript replay parser** (trusted reference — reconstructs states from the live game's replay format)
2. The **C++ PrismataAI engine** (our implementation — needs validation)

Compare game states at every turn. Any divergence reveals an engine bug.

## Surfinite's Replay Codes (100 games)

```
Dvv7p-OGUGb VirAP-ocfTB hMwfO-jP+BO 03uyp-vcH@i izF+o-y@Ujh
fGVKQ-h6qg5 zB5WR-SMx2P HQDim-x1GOS MmPPA-ANywI PxrPA-pa3kN
tVIo4-E3Jq1 Ni4y4-ixrpQ vqb7N-eIMgk nWeHQ-oL7U6 0aG6z-lD2Qp
nerls-ypgT0 nBlx7-PZCI7 BL+J9-3aEOk v6jI9-5s5Bb 75+00-WyQ6x
7jinu-78NZ4 bsBib-84OeO wqlNr-JpfhA xl85a-8FCpb 8G68S-@yR4o
M6ROr-8PStV 14i9d-aHyJI FOp6p-4FvAe W6ID8-Hz8AQ zheOV-IC7Ly
G85Pe-SdtBt bvyMx-FH8fU N37rL-+W1Ap zK8YF-6+2ae pdAB1-wCOhM
aCJkk-F9N5I Q4nfF-UJUhh jqAGt-w8rs0 d0AGb-Pwip5 Yctp9-iP2YT
A6MH3-gvoww JGts0-8ibdr DLG8W-CRgJ9 78P1h-I@6Ga OQG4w-v0NY4
zbdr1-uT5Yz pF3gi-AbkJc vIaUr-NmeU@ ocnn1-iHwxf lr96N-O@ASA
eamUj-+3HUx Y5@wt-ScWSF LwW9w-cgkD2 dabBn-Aoea7 QnGzy-Qkupt
Rx4OC-y1UQn HdxeO-NxQ4t VviLt-b+987 h@fnk-BwZBS +udI7-qFN27
jUzPY-wR3Gw jUxei-bH21Z cvJv3-@YJW0 rHbZ4-Zh6mt r0Ppz-RcgWI
XFVr0-LTbv7 7RXU0-RQHxs ejvpA-jhBe5 xionQ-XYvnH l2QNv-Adrtn
aj3lN-pYoQF MMHNv-JD3Eg sBT05-kXgD+ @cmK8-SMm6Y @@q9R-RJSwb
Smyz9-tTImv 9SBfe-b86Zk 6h1fp-H0pDD jqpd3-D1x65 42NIB-5i59l
iZpDL-7tpv6 mh3m+-DX5rg yxSuK-scu7h k8OpC-KqsNn 5E50G-v6G2I
EhGat-DNq@n QBuRH-2Op5@ ZKBo2-bCIVq oYsUH-zpsMb vKMCl-mljiS
qDmlz-2Npi1 qEtqO-5qijb OkHth-Iizde QRvgh-fGt41 Cm6Eg-13KOw
3PZUZ-Y3gFX ECENg-UAjTs vXm75-aRZJi gVzoI-rbTxt ckGnb-2S68y
```

Replays are fetched from S3: `http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz`
Special characters (`+`, `@`) must be URL-encoded (`%2B`, `%40`).

## Player Info

- **Username**: Surfinite
- **Rating**: ~1596–1938 (below 2000, so in the existing dataset as the non-expert player)
- **362 filtered games** in the existing expert_2000_replays.json dataset
- Some of these 100 codes may overlap with the existing dataset; many may not (these could include games vs masterbot at any rating)

## Background: What's Already Been Verified

From sections 1 and 4 of CLAUDE.md:
- **105 competitive non-base-set units** present with current balance stats
- **Dominion card whitelist** includes all competitive units
- **Unit costs, HP, abilities** synced from Jan 2019 balance patch via replay API data

What has NOT been verified:
- **Game phase transitions** (action → breach → defense → swoosh → confirm)
- **Ability execution mechanics** (scripts, targeting, sacrifice costs)
- **Resource generation** (begin-turn income, gold from Drones, colored resources)
- **Construction delay** and lifespan countdown
- **Chill/freeze mechanics**
- **Breach mechanics** (damage assignment, overkill, frontline ordering)
- **Defense mechanics** (blocker assignment, absorb)
- **Edge cases** (resonance, gold resonate, condition scripts, targetAction)

## Step-by-Step Plan

### Step 1: Fetch and Parse All 100 Replays (TypeScript side)

Create a script `validate_replays.js` in `c:\libraries\prismata-replay-parser\` that:

1. Downloads each replay from S3 (use existing `fetchReplay()` pattern from extract_training_data.js)
2. Parses with the TypeScript replay parser
3. For each turn, captures a **state snapshot**:
   - Per-player resources: `{ gold, blue, red, green, energy, attack }`
   - Per-player unit list: for each unit → `{ name, toughness, toughnessMax, delay, lifespan, charge, disruption, abilityUsed, blocking, building, frozen, frontline, defaultBlocking, fragile }`
   - Per-player attack totals
   - Supply remaining per buyable card type
   - Active player
   - Game phase (if accessible)
4. Also captures the **action sequence** for each turn:
   - Action type (Purchase, UseAbility, AssignDefense, AssignAttack, SelectForTargeting, EndTurn, CommitTurn, etc.)
   - Target unit name and/or blueprint name
   - Whether it was cancelled/undone
5. Outputs to `validation_data/{CODE}.json` with structure:
```json
{
  "code": "Dvv7p-OGUGb",
  "p0": "Surfinite",
  "p1": "opponent_name",
  "result": 0,
  "card_set": ["Drone", "Engineer", ..., "Venge Cannon"],
  "turns": [
    {
      "turn": 0,
      "active_player": 0,
      "pre_state": { /* state snapshot before actions */ },
      "actions": [
        { "type": "Purchase", "unit": "Drone" },
        { "type": "Purchase", "unit": "Drone" },
        { "type": "UseAbility", "unit": "Drone", "index": 0 },
        { "type": "EndTurn" },
        { "type": "CommitTurn" }
      ],
      "post_state": { /* state snapshot after all actions committed */ }
    },
    ...
  ]
}
```

**Key considerations:**
- Handle undo/redo/revert: only emit the FINAL committed actions (after all cancels resolved)
- URL-encode special characters in replay codes (`+` → `%2B`, `@` → `%40`)
- Rate-limit S3 fetches (already handled in existing scripts)
- Log any replays that fail to parse

### Step 2: Build a C++ Validation Harness

Create `source/testing/ReplayValidator.cpp` and `.h` that:

1. Reads a `validation_data/{CODE}.json` file
2. Constructs the initial GameState from the card set (using the JSON state constructor)
3. For each turn, applies the action sequence to the C++ GameState
4. After each turn, serializes the C++ state and compares against the TypeScript post_state

**The hard part: Action Translation**

The TypeScript replay parser uses high-level action types that don't map 1:1 to C++ ActionTypes:

| TypeScript Action | C++ ActionType | Translation Notes |
|---|---|---|
| Purchase(unit_name) | BUY(buyable_id) | Look up buyable ID by unit type name |
| UseAbility(unit_name, index) | USE_ABILITY(card_id) | Find the Nth unit of that type owned by active player |
| AssignDefense(unit_name, index) | ASSIGN_BLOCKER(card_id) | Find the Nth unit that can block |
| AssignAttack(unit_name, index) | ASSIGN_BREACH(card_id) | Find the Nth enemy unit of that type |
| SelectForTargeting(unit_name) | SNIPE(card_id) or CHILL(card_id) | Context-dependent on the ability being used |
| EndTurn | END_PHASE | May need multiple END_PHASE calls depending on current phase |
| CommitTurn | END_PHASE | Advances through remaining phases |

**Unit identification challenge:** The TypeScript parser identifies units by name + instance index. The C++ engine uses CardID integers. The validator needs to maintain a mapping, e.g., "the 3rd Drone owned by player 0" → CardID 7.

**Recommended approach:** Don't try to translate actions 1:1. Instead:

**Option A (state-based comparison — RECOMMENDED):**
- Only compare **post-turn states** (after both players commit)
- Don't try to replay individual actions through C++
- Instead, for each turn: record what units were bought, what abilities were activated, what defense was assigned
- Apply those decisions at a higher level using the existing PartialPlayer infrastructure
- Compare the resulting state

**Option B (action-level replay — harder but more thorough):**
- Build a full action translator that maps TypeScript actions → C++ Actions
- Feed each action through `GameState::doAction()`
- Compare state after every action (not just end-of-turn)
- This catches phase transition bugs, but is significantly more complex

**I recommend starting with Option A** for initial validation, then escalating to Option B if discrepancies are found that need deeper diagnosis.

### Step 3: State Comparison

For each turn, compare these fields between TypeScript and C++ states:

**Critical (must match exactly):**
- Per-player resource counts (gold, blue, red, green, energy, attack)
- Per-player unit counts by type (how many Drones, Engineers, Tarsiers, etc.)
- Per-unit HP (toughness) — aggregate by type or per-instance if possible
- Supply remaining per buyable card type
- Active player
- Game over status and winner

**Important (should match):**
- Per-unit construction delay (is the unit still building?)
- Per-unit lifespan remaining
- Per-unit frozen/chill status
- Per-unit blocking status

**Nice to have:**
- Per-unit charge counts
- Exact ability-used status

**Comparison output format:**
```
Replay Dvv7p-OGUGb, Turn 7:
  MATCH: resources, units, supply, active_player

Replay Dvv7p-OGUGb, Turn 12:
  MISMATCH: P0 resources
    TypeScript: { gold: 5, blue: 2, red: 0, green: 1, energy: 0, attack: 3 }
    C++:        { gold: 5, blue: 2, red: 0, green: 0, energy: 0, attack: 3 }
    Diff: green (TS=1, C++=0)
  MISMATCH: P0 units
    TypeScript: Drone×8, Engineer×2, Conduit×1, Steelsplitter×1
    C++:        Drone×8, Engineer×2, Conduit×1
    Diff: Missing Steelsplitter×1 in C++
```

### Step 4: Analyze Divergences

Categorize any mismatches by likely cause:

1. **Missing/wrong unit stats** — a unit in cardLibrary.jso has wrong HP, cost, ability, etc.
2. **Phase transition bug** — C++ engine doesn't advance phases correctly
3. **Ability script bug** — an ability script doesn't execute the same effect
4. **Resource generation bug** — begin-turn income calculation differs
5. **Construction/lifespan bug** — delay countdown or expiration differs
6. **Breach/defense bug** — damage assignment or blocking works differently
7. **Frontline bug** — frontline units handled differently (we already found and fixed one such bug)
8. **Chill/freeze bug** — freeze duration or effect differs
9. **Supply bug** — supply tracking differs

For each divergence, identify:
- First turn where it appears
- Which replay(s) it affects
- The specific unit types and game mechanics involved
- Whether it's a systematic bug (affects all games) or situational

### Step 5: Fix Engine Bugs

For each confirmed divergence:
1. Identify the root cause in the C++ engine source
2. Fix it
3. Re-run the validation on the affected replays to confirm the fix
4. Check if the fix affects AI tournament results (re-run a small tournament before/after)

### Step 6: Summary Report

Produce a summary:
- **N/100 replays** parsed successfully
- **X% of turns** match perfectly
- **Top divergence categories** ranked by frequency
- **Confidence level**: "Engine matches live game for N% of game mechanics tested"

## Key Files

| File | Description |
|---|---|
| `c:\libraries\prismata-replay-parser\src\replayParser.ts` | TypeScript replay parser (trusted reference) |
| `c:\libraries\prismata-replay-parser\src\gameState.ts` | TypeScript game state management |
| `c:\libraries\prismata-replay-parser\src\unit.ts` | TypeScript unit representation |
| `c:\libraries\prismata-replay-parser\extract_training_data.js` | Existing replay extraction (reference for S3 fetch pattern) |
| `source/engine/GameState.cpp` | C++ game state implementation |
| `source/engine/GameState.h` | C++ game state header |
| `source/engine/Action.h` | C++ action types and Action class |
| `source/engine/Card.cpp` | C++ card (unit instance) implementation |
| `bin/asset/config/cardLibrary.jso` | Unit definitions (costs, HP, abilities, scripts) |

## Implementation Notes

### TypeScript Parser Action Types (for reference)

From `replayParser.ts`:
```
AssignDefense = 1, CancelAssignDefense = 2, EndDefense = 3,
SelectForTargeting = 4, CancelTargeting = 5,
UseAbility = 6, CancelUseAbility = 7,
Purchase = 8, CancelPurchase = 9,
ProceedToDamage = 10, OverrunDefenses = 11, CancelOverrunDefenses = 12,
AssignAttack = 13, CancelAssignAttack = 14,
EndTurn = 15, CommitTurn = 16,
Undo = 17, Redo = 18, Revert = 19
```

### C++ Engine Action Types

From `Action.h`:
```
USE_ABILITY, BUY, END_PHASE, ASSIGN_BLOCKER, ASSIGN_BREACH,
ASSIGN_FRONTLINE, SNIPE, CHILL, WIPEOUT,
UNDO_USE_ABILITY, UNDO_CHILL, UNDO_BREACH, SELL
```

### C++ GameState Key Methods

- `doAction(Action)` — apply a single action
- `isLegal(Action)` — check if action is legal in current state
- `toJSONString()` — serialize full state to JSON
- `isIsomorphic(GameState)` — compare two states for equivalence
- `getActivePlayer()` — who moves next
- `getActivePhase()` — current phase
- `numCards(player)` / `getCardByID(id)` — unit access
- `getResources(player)` — resource access
- `numCardsBuyable()` / `getCardBuyableByIndex(i)` — supply access

### Recommended Starting Point

Start with the **simplest possible validation**:
1. Fetch ONE replay (e.g., `Dvv7p-OGUGb`)
2. Parse it in TypeScript, extract per-turn unit counts and resources
3. Manually construct the same game in C++ (set up initial state, apply buy decisions turn by turn)
4. Compare unit counts and resources after each round

This avoids the full action-translation complexity and gives a quick signal on whether the engine is fundamentally correct.

### Alternative Approach: State-Only Comparison

Instead of replaying actions, compare **states only**:

1. TypeScript parser produces per-turn state snapshots (unit lists, resources)
2. C++ engine's `toJSONString()` produces state snapshots from tournament/replay data
3. Write a comparison script (Python or Node.js) that loads both and diffs them

This works for validating our EXISTING tournament games but doesn't validate against LIVE Prismata games. For live validation, we need to feed live replay actions into our engine.

### Scope Estimate

| Phase | Effort | Description |
|---|---|---|
| Step 1 (TypeScript extraction) | 2-3 hours | Adapt existing extract_training_data.js |
| Step 2 (C++ validator, Option A) | 1-2 days | State-level comparison framework |
| Step 2 (C++ validator, Option B) | 3-5 days | Full action-level replay |
| Step 3 (comparison logic) | 2-3 hours | Diff script |
| Step 4-5 (analysis & fixes) | Depends on findings | Could be 0 bugs or 20 bugs |
| Step 6 (report) | 1 hour | Summary |

**Recommended: Start with Step 1 + Option A for Step 2.** Get quick results in ~1 day. Escalate to Option B only if systematic divergences need action-level diagnosis.
