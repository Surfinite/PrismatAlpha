# C++ Replay Ingestion & Analysis Mode (v2 — Post-Review)

**Status:** PLANNING (v2)
**Date:** 2026-02-20
**Goal:** Build a C++ replay stepper that converts replay JSON click sequences into GameState transitions, enabling near-100% training data extraction and reusable game analysis infrastructure.
**Revision:** Incorporates feedback from 6 independent expert reviews. Major changes: undo/redo via snapshots (mandatory Phase 1), full instId lifecycle design, multi-process parallelism only, strict error handling with benign skip whitelist, shift-click support, clicksPerTurn-driven turn boundaries.

---

## Motivation

The TS replay parser fails on ~44% of expert replays (Redo, destroyed units, targeting edge cases). This means:
- 32,082 expert replays -> only ~17,966 attempted, ~13,117 successfully parsed
- Systematic blind spot: complex targeting, undo/redo, and multi-step abilities are exactly the situations high-level players use most
- The partial recovery fix (Feb 20) helps but doesn't solve the root cause

The C++ engine is the ground truth -- it handles all these cases correctly during self-play. A C++ replay mode would:
1. Get near-100% extraction rate (target: >95% Phase 1, >99% iterative)
2. Output binary shards directly (same format as self-play, no JSONL intermediary)
3. Build a reusable **ReplayStepper** class that serves multiple future needs

**Expected impact:** ~1.2M new training records from 32K replays (vs ~250K from TS parser). Same 1785-dim features, same binary shard format, directly loadable by `train.py --selfplay-dir`.

---

## Architecture Overview

### Core Primitive: `ReplayStepper`

A class that takes a replay's `commandList` (click sequence) + `mergedDeck` (card definitions) + `initInfo` (starting state) and steps through the game turn-by-turn, producing a `GameState` at each turn boundary.

```
ReplayStepper stepper;
stepper.init(mergedDeck, initInfo, commandList, clicksPerTurn, playerInfo);

while (stepper.hasNextTurn())
{
    // State is captured BEFORE applying clicks (pre-turn = decision point)
    const GameState& state = stepper.getState();
    sink.onTurnStart(state);

    // Apply all clicks for this turn
    StepResult result = stepper.advanceTurn();
    if (result == StepResult::FatalError)
        break;  // Flush partial data and move on
}
```

### Three Subsystems

1. **Click-to-Action Mapping** -- converts UI clicks to engine Actions using phase context
2. **instId Lifecycle Tracking** -- maintains bidirectional instId<->CardID mapping as cards are created/destroyed
3. **Snapshot Undo/Redo** -- handles `revert clicked` / `redo clicked` via full state snapshots

### What This Primitive Enables

| Use Case | How It Uses ReplayStepper | Phase |
|---|---|---|
| **Training data extraction** (`--replay`) | Step through game, call `SelfPlayDataSink::onTurnStart()` at each turn | **Phase 1** |
| **Neural evaluation** (`--eval`) | Step through + `NeuralNet::evaluate()` at each turn, output eval curve JSON | Phase 2 |
| **AI move comparison** (`--analyze`) | Step through + run AI search at each turn, compare with human move | Phase 3 |
| **Opening book extraction** | Step first N turns, record buy sequences | Phase 2+ |
| **Replay validation** | Step through, measure error rates, compare to TS parser | Phase 1 |

---

## The Three Hard Problems

### Problem 1: Click -> Action Mapping

The replay `commandList` contains UI clicks, not engine Actions. The full mapping table:

| Click `_type` | `_id` Meaning | Engine Action(s) | Notes |
|---|---|---|---|
| `card clicked` | mergedDeck index | `BUY` | CardType ID = `_id + 2` |
| `card shift clicked` | mergedDeck index | `BUY` (shift=true) | Engine loops internally, buys all affordable |
| `inst clicked` | client instId | Context-dependent (see decision tree below) | |
| `inst shift clicked` | client instId | Context-dependent (shift=true) | Engine activates all same-type |
| `space clicked` | -1 | `END_PHASE` | May cascade through multiple phases |
| `revert clicked` | -1 | Snapshot restore (undo) | Not mapped to engine UNDO_* actions |
| `redo clicked` | -1 | Snapshot restore (redo) | |

**`inst clicked` — delegate to `GameState::getClickAction()`:**

Rather than reimplementing the full click-to-action decision tree, the stepper delegates to the engine's existing `getClickAction(card)` method (`GameState.cpp:2197-2269`), which already handles all 13 action types correctly:

```
inst clicked with _id = instId:
  cardId = m_instIdToCardId[instId]   // ABORT if unknown
  card = state.getCardByID(cardId)
  action = state.getClickAction(card)  // engine's authoritative mapping
```

`getClickAction()` handles the full action space:

| Phase | Condition | Action |
|---|---|---|
| Action | Own card, sellable | SELL |
| Action | Own card, status=Assigned | UNDO_USE_ABILITY (un-tap) |
| Action | Own card, otherwise | USE_ABILITY |
| Action | Enemy card, chilled | UNDO_CHILL |
| Action | Enemy card, frontline | ASSIGN_FRONTLINE |
| Action | Enemy card, otherwise | WIPEOUT |
| Action | Target pending (any card) | SNIPE or CHILL (source card's type) |
| Defense | Any card | ASSIGN_BLOCKER |
| Breach | Enemy card, already breached | UNDO_BREACH |
| Breach | Enemy card, frozen+!canBreach | UNDO_CHILL |
| Breach | Enemy card, otherwise | ASSIGN_BREACH |
| Breach | Own card | USE_ABILITY |

**Key design decisions:**
- SNIPE vs CHILL is determined by the **source card** (`m_targetAbilityCardID`), not the target. The source's `CardType::getTargetAbilityType()` returns `ActionTypes::SNIPE` (for `"snipe"` in cardLibrary) or `ActionTypes::CHILL` (for `"disrupt"` in cardLibrary). This is handled inside `getClickAction()`.
- UNDO_USE_ABILITY (un-tapping) occurs when clicking an already-Assigned allied card during Action phase. This is common at high level (untapping drones to use as blockers).
- Shift variants set `action.setShift(true)`. The engine's `doAction()` handles expansion internally -- it loops buying/activating all copies. The stepper does NOT expand shift clicks into multiple actions.
- `END_PHASE` can cascade: Action -> (Breach if wipeout) -> Confirm -> Defense/Swoosh -> Swoosh -> next Action. This happens internally within a single `doAction(END_PHASE)` call.

**Cancel targeting edge case:** If `isTargetAbilityCardClicked()` is true but the `inst clicked` is illegal as SNIPE/CHILL (e.g., targets allied unit), try `UNDO_USE_ABILITY` on `m_targetAbilityCardID` first (clears the pending flag), then re-interpret the click via `getClickAction()`. If the reinterpretation is also illegal, treat as BenignSkip (the click just cancelled targeting with no further effect).

### Problem 2: instId <-> CardID Lifecycle

**The fundamental divergence:** The client uses monotonic `nextInstId++` (never reuses, starts at 0). The C++ engine uses slot reuse via `getFreeCardID()` (lowest available index, reuses dead card slots after `removeKilledCards()`).

**Client instId assignment order** (confirmed from decompiled `State.as`):
1. Game start: P1 (white) initCards in array order, then P2 (black) initCards in array order
2. Each `createInst()` call: `this.nextInstId++`
3. Every card creation (buy, script token, ability spawn, beginTurnScript) increments
4. instIds are NEVER reused, even after card death

**C++ card creation paths** (all must be tracked):

| Path | Trigger | Detection |
|---|---|---|
| BUY | `doAction(BUY)` | New CardID in liveCardIDs |
| BuyScript token | `runScript(..., BuyScript)` inside BUY | Same -- detected after doAction returns |
| AbilityScript token | `runScript(..., AbilityScript)` inside USE_ABILITY | Same |
| BeginTurnScript token | `runScript(..., BeginTurnScript)` inside beginTurn | Created during END_PHASE cascade (Swoosh) |
| Shift-BUY multiple | `doAction(BUY, shift=true)` loop | Multiple new CardIDs after one doAction |

**The instId tracking algorithm:**

```cpp
void ReplayStepper::updateInstIdMappings()
{
    // Step 1: Collect all currently live CardIDs
    std::unordered_set<CardID> liveCardIds;
    for (int p = 0; p < 2; p++)
        for (CardID id : m_state.getCardIDs(p))
            liveCardIds.insert(id);

    // Step 2: Remove mappings for cards no longer live
    //   (handles slot reuse: dead card's slot freed by removeKilledCards,
    //    then reused by a new card in the same doAction cascade)
    std::vector<CardID> toRemove;
    for (auto& [cardId, instId] : m_cardIdToInstId)
        if (liveCardIds.find(cardId) == liveCardIds.end())
            toRemove.push_back(cardId);

    for (CardID cardId : toRemove)
    {
        m_instIdToCardId.erase(m_cardIdToInstId[cardId]);
        m_cardIdToInstId.erase(cardId);
    }

    // Step 3: Find new live cards not yet mapped
    std::vector<CardID> newCards;
    for (int p = 0; p < 2; p++)
        for (CardID id : m_state.getCardIDs(p))
            if (m_cardIdToInstId.find(id) == m_cardIdToInstId.end())
                newCards.push_back(id);

    // Step 4: Sort ascending by CardID (matches engine creation order
    //   because getFreeCardID returns lowest available slot, and cards
    //   are created sequentially within a doAction call)
    std::sort(newCards.begin(), newCards.end());

    // Step 5: Assign instIds in order
    for (CardID id : newCards)
    {
        m_cardIdToInstId[id] = m_nextInstId;
        m_instIdToCardId[m_nextInstId] = id;
        m_nextInstId++;
    }
}
```

**Called after EVERY `doAction()` return** -- not just after BUY. This catches tokens from scripts, beginTurnScript creations, and multi-card events from shift clicks.

**Initialization seeding:**
```
for each entry in initCards[0]:   // P1 first
    for i in 0..count:
        Add card via state.addCard(P1, type, ...)
        -> new CardID appears in getCardIDs(P1)
        -> assign m_nextInstId++ (starts at 0)

for each entry in initCards[1]:   // P2 second
    for i in 0..count:
        Add card via state.addCard(P2, type, ...)
        -> assign m_nextInstId++
```

For a standard game: P1 gets instIds 0-3 (4 Drones) + 4 (Engineer), P2 gets 5-9 (5 Drones) + 10 (Engineer). `m_nextInstId` = 11 after init.

**On unknown instId from `inst clicked`:** Immediately abort the replay. Log the failure with full context (click index, instId, expected vs actual mapping state). No heuristic fallback -- silent corruption is worse than losing one replay.

### Problem 3: Undo/Redo via Snapshots

**Why NOT use engine UNDO_* actions:** The engine's undo actions (`UNDO_USE_ABILITY`, `SELL`, `UNDO_CHILL`, `UNDO_BREACH`) are semantic-level, not UI-level. A single `revert clicked` from the client corresponds to "undo last UI click" which is a different concept. Mapping revert to the correct engine undo action requires knowing what the last action was, whether it was a BUY (use SELL), USE_ABILITY (use UNDO_USE_ABILITY), or something else. Some client-undoable actions have no engine UNDO equivalent (e.g., undo END_PHASE, undo across complex targeting sequences). The engine UNDO actions also have preconditions that may not hold (e.g., can't SELL if you already spent the resources the buy produced).

**Snapshot approach** (simple, correct, handles all cases):

```cpp
struct StepperSnapshot
{
    GameState state;
    std::unordered_map<int, CardID> instIdToCardId;
    std::unordered_map<CardID, int> cardIdToInstId;
    int nextInstId;
};

// In ReplayStepper:
std::vector<StepperSnapshot> m_snapshots;    // Post-click state history
int m_snapshotCursor;                        // Current position
```

**GameState is safe to copy:** Confirmed by codebase inspection -- all members are value types (`CardData` containing `std::vector<Card>`, `Resources[2]`, primitive ints/bools). No pointers, no shared_ptr, no references. The compiler-generated copy constructor produces a full deep copy. This is the same mechanism Alpha-Beta search uses for state tree exploration.

**Algorithm:**

```
Initialize:
  m_snapshots = [initial_snapshot]   // state after init, before any clicks
  m_snapshotCursor = 0

On normal click (card/inst/space):
  m_snapshots.resize(m_snapshotCursor + 1)   // truncate redo future
  m_snapshots.push_back(captureSnapshot())   // save PRE-click state (before mutation)
  m_snapshotCursor = m_snapshots.size() - 1
  Apply click -> state mutated
  updateInstIdMappings()

On "revert clicked":
  m_snapshotCursor--
  Restore state from m_snapshots[m_snapshotCursor]

On "redo clicked":
  m_snapshotCursor++
  Restore state from m_snapshots[m_snapshotCursor]
```

Snapshots store **pre-click** state. Undo restores the state before the last action was applied. Example: initial=[S0], after click1=[S0, S_pre1], cursor=1. Undo → cursor=0, restore S0 (correct).

**Memory cost:** ~10KB per snapshot (40 cards x 100 bytes + maps + misc) x ~200 clicks per game = ~2MB per replay. Trivial for single-replay or batch processing.

**Edge cases:**
- Multiple consecutive reverts: cursor keeps decrementing. If it reaches 0, the next revert is a benign skip (can't undo past start).
- Redo after new action: the `resize(cursor+1)` truncates the redo history, matching client behavior.
- Revert past the initial snapshot: treat as error, skip the revert click.

---

## Phase 1: ReplayStepper + `--replay` CLI

### 1A: ReplayStepper Core Class

**Files to create:**
- `source/testing/ReplayStepper.h`
- `source/testing/ReplayStepper.cpp`

**Why `testing/`, not `engine/`:** ReplayStepper depends on `NeuralNet::buildCardTypeMapping()` (in `ai/`) and uses `SelfPlayDataSink` (in `testing/`). The engine layer has zero AI/training imports — placing ReplayStepper there would break the existing `engine/ → ai/ → testing/` layered architecture.

**Class interface:**

```cpp
class ReplayStepper
{
public:

    enum class StepResult { OK, BenignSkip, FatalError, GameOver };

    ReplayStepper();

    // Initialize from replay JSON components.
    // Calls InitFromMergedDeckJSON internally.
    // Returns false if init fails (malformed JSON, unknown cards).
    bool init(const rapidjson::Value& mergedDeck,
              const rapidjson::Value& initInfo,
              const rapidjson::Value& commandList,
              const rapidjson::Value& clicksPerTurn,
              const rapidjson::Value& playerInfo);

    // Turn-level stepping (preferred API)
    bool hasNextTurn() const;
    StepResult advanceTurn();          // Apply all clicks for current turn
    int getTurnClickCount() const;     // Clicks in current turn (from clicksPerTurn)

    // Click-level stepping (lower-level, used by advanceTurn)
    bool hasNextClick() const;
    StepResult applyNextClick();

    // State access
    const GameState& getState() const;
    int getCurrentTurn() const;
    PlayerID getActivePlayer() const;
    int getClickIndex() const;
    bool isGameOver() const;

    // Error/stats
    int getTotalClicks() const;
    int getAppliedClicks() const;
    int getBenignSkips() const;
    int getFatalErrors() const;
    const std::vector<std::string>& getErrors() const;

private:

    // Core state
    GameState m_state;
    int m_clickIndex;
    int m_turnIndex;
    bool m_gameOver;

    // Replay data (owned)
    rapidjson::Document m_replayDoc;
    const rapidjson::Value* m_commandList;
    std::vector<int> m_clicksPerTurn;   // Pre-parsed turn boundaries

    // instId tracking
    int m_nextInstId;
    std::unordered_map<int, CardID> m_instIdToCardId;
    std::unordered_map<CardID, int> m_cardIdToInstId;

    // Undo/redo snapshots
    struct Snapshot
    {
        GameState state;
        std::unordered_map<int, CardID> instIdToCardId;
        std::unordered_map<CardID, int> cardIdToInstId;
        int nextInstId;
    };
    std::vector<Snapshot> m_snapshots;
    int m_snapshotCursor;

    // Error tracking
    int m_appliedClicks;
    int m_benignSkips;
    int m_fatalErrors;
    std::vector<std::string> m_errors;

    // Internal methods
    Action clickToAction(const rapidjson::Value& click);  // delegates to getClickAction()
    void updateInstIdMappings();
    void saveSnapshot();
    void restoreSnapshot(int cursor);
    Snapshot captureSnapshot() const;
    bool initGameState(const rapidjson::Value& mergedDeck,
                       const rapidjson::Value& initInfo);
    void logError(const std::string& msg);
};
```

**GameState initialization from initInfo** (`initGameState()`):

Replay JSON uses `initInfo` format (not F6 clipboard JSON). We build GameState via the public API:

```cpp
bool ReplayStepper::initGameState(const rapidjson::Value& mergedDeck,
                                   const rapidjson::Value& initInfo)
{
    // 1. Register card types from this game's deck (global state)
    Prismata::InitFromMergedDeckJSON(mergedDeck);
    NeuralNet::Instance().buildCardTypeMapping();

    // 2. Empty default GameState
    m_state = GameState();

    // 3. Add buyable cards from mergedDeck
    //    InitFromMergedDeckJSON assigns CardType IDs starting at 2
    //    in mergedDeck array order. So mergedDeck[i] = CardType(i+2).
    for (rapidjson::SizeType i = 0; i < mergedDeck.Size(); i++)
    {
        CardType type(i + 2);
        if (type.getSupply() > 0)
            m_state.addCardBuyable(type);
    }

    // 4. Add initial units from initCards
    //    Format: initCards[player] = [[count, name, ...attrs], ...]
    //    Client assigns instIds: P1 first, then P2, monotonic from 0
    const auto& initCards = initInfo["initCards"];
    m_nextInstId = 0;

    for (int player = 0; player < 2; player++)
    {
        const auto& playerCards = initCards[player];
        for (rapidjson::SizeType i = 0; i < playerCards.Size(); i++)
        {
            const auto& entry = playerCards[i];
            int count = entry[0].GetInt();
            const std::string cardName = entry[1].GetString();
            CardType type = CardTypes::GetCardType(cardName);

            // Parse optional attributes (delay, buildTime, role, etc.)
            int delay = 0;
            int lifespan = 0;
            int buildTime = 0;
            for (rapidjson::SizeType k = 2; k + 1 < entry.Size(); k += 2)
            {
                std::string key = entry[k].GetString();
                if (key == "delay") delay = entry[k+1].GetInt();
                else if (key == "lifespan") lifespan = entry[k+1].GetInt();
                else if (key == "buildTime") buildTime = entry[k+1].GetInt();
            }

            int creationDelay = (buildTime > 0) ? buildTime : delay;

            for (int c = 0; c < count; c++)
            {
                m_state.addCard(player, type, 1, CardCreationMethod::Manual,
                                creationDelay, lifespan);
            }
        }

        // Assign instIds to all currently unmapped live cards (both players).
        // After P1 pass: only P1 cards are unmapped -> assigned.
        // After P2 pass: P1 already mapped, only P2 cards -> assigned.
        // (addCard uses getFreeCardID -> ascending CardIDs for fresh state)
        updateInstIdMappings();
    }

    // 5. Set starting resources
    const auto& initResources = initInfo["initResources"];
    if (initResources[0].IsString())
        m_state.setMana(Players::Player_One,
                        Resources(std::string(initResources[0].GetString())));
    if (initResources[1].IsString())
        m_state.setMana(Players::Player_Two,
                        Resources(std::string(initResources[1].GetString())));

    // 6. Trigger initial turn setup
    //    beginPhase() is PRIVATE in GameState. Use the public beginTurn()
    //    which is what beginPhase(Swoosh) calls internally (GameState.cpp:1317).
    //    beginTurn() runs removeKilledCards, beginOwnTurnScript, then endPhase
    //    transitions to Action phase.
    m_state.beginTurn(Players::Player_One);

    // beginTurn may create cards (beginOwnTurnScript) -- track them
    updateInstIdMappings();

    return true;
}
```

**Note on mergedDeck reordering:** Players can drag-and-drop to reorder units in the sidebar. The replay's `mergedDeck` reflects the actual order for that game. `card clicked` `_id` indexes into this array. Since we call `InitFromMergedDeckJSON` with the replay's own mergedDeck, the mapping is self-consistent: `mergedDeck[i]` gets CardType ID `i+2`, and `card clicked` with `_id=i` maps to `BUY` with CardType `i+2`. No name matching is needed.

**Error handling philosophy:**

Two categories of illegal actions:

| Category | Examples | Response |
|---|---|---|
| **Benign skip** | `card clicked` on sold-out supply, double-click, buying with insufficient resources | Log, skip, continue. These are clicks the client recorded but the server silently rejected. |
| **Fatal desync** | Unknown instId, illegal `END_PHASE` (phase mismatch), illegal `inst clicked` after correct instId mapping | Log with full context, abort replay. All subsequent positions would be from a diverged state -- worse than no data. |

```cpp
StepResult ReplayStepper::applyNextClick()
{
    const auto& click = (*m_commandList)[m_clickIndex++];
    const std::string type = click["_type"].GetString();

    // Handle undo/redo via snapshots (not engine actions)
    if (type == "revert clicked")
    {
        if (m_snapshotCursor > 0)
        {
            m_snapshotCursor--;
            restoreSnapshot(m_snapshotCursor);
        }
        return StepResult::OK;
    }
    if (type == "redo clicked")
    {
        if (m_snapshotCursor + 1 < (int)m_snapshots.size())
        {
            m_snapshotCursor++;
            restoreSnapshot(m_snapshotCursor);
        }
        return StepResult::OK;
    }

    // Map click to engine action (delegates to getClickAction for inst clicks)
    Action action = clickToAction(click);
    if (action == Action())  // unmappable click
        return StepResult::FatalError;

    // Check legality
    if (!m_state.isLegal(action))
    {
        // Benign: BUY on sold-out supply, double-click, insufficient resources
        if (action.getType() == ActionTypes::BUY)
        {
            m_benignSkips++;
            return StepResult::BenignSkip;
        }

        // Cancel-targeting fallback: if target pending and inst click is
        // illegal as SNIPE/CHILL, try cancelling the targeting first
        if (m_state.isTargetAbilityCardClicked()
            && (action.getType() == ActionTypes::SNIPE
                || action.getType() == ActionTypes::CHILL))
        {
            Action cancel(m_state.getActivePlayer(),
                          ActionTypes::UNDO_USE_ABILITY,
                          m_state.getTargetAbilityCardClicked().getID());
            if (m_state.isLegal(cancel))
            {
                m_state.doAction(cancel);
                // UNDO_USE_ABILITY when isTargetAbilityCardClicked() only
                // clears the flag (GameState.cpp:746-751), no card changes.
                // updateInstIdMappings() not needed here.

                // Re-interpret via getClickAction (targeting flag now cleared)
                CardID cardId = m_instIdToCardId[click["_id"].GetInt()];
                const Card& card = m_state.getCardByID(cardId);
                Action reinterp = m_state.getClickAction(card);
                if (m_state.isLegal(reinterp))
                {
                    action = reinterp;
                    // Fall through to apply below
                }
                else
                {
                    // Click just cancelled targeting with no further effect
                    m_benignSkips++;
                    return StepResult::BenignSkip;
                }
            }
        }
        else
        {
            // Fatal: desync detected
            logError("Illegal action: " + actionToString(action));
            m_fatalErrors++;
            return StepResult::FatalError;
        }
    }

    // Save PRE-action snapshot (for undo — restoring undoes this action)
    m_snapshots.resize(m_snapshotCursor + 1);  // truncate redo history
    m_snapshots.push_back(captureSnapshot());
    m_snapshotCursor = (int)m_snapshots.size() - 1;

    // Apply action
    m_state.doAction(action);
    updateInstIdMappings();

    m_appliedClicks++;

    if (m_state.isGameOver())
    {
        m_gameOver = true;
        return StepResult::GameOver;
    }

    return StepResult::OK;
}
```

**Turn-level stepping with clicksPerTurn:**

```cpp
StepResult ReplayStepper::advanceTurn()
{
    if (m_turnIndex >= (int)m_clicksPerTurn.size())
        return StepResult::GameOver;

    int clicksThisTurn = m_clicksPerTurn[m_turnIndex];

    for (int i = 0; i < clicksThisTurn && hasNextClick(); i++)
    {
        StepResult result = applyNextClick();
        if (result == StepResult::FatalError)
            return result;
        if (result == StepResult::GameOver)
            return result;
    }

    m_turnIndex++;
    return StepResult::OK;
}
```

**Validation cross-checks** (inside advanceTurn or at turn boundaries):
- Compare `m_turnIndex` vs `m_state.getTurnNumber()` -- log warning on mismatch
- Track expected turn count from `clicksPerTurn.size()` vs actual turns processed

### 1B: `--replay` CLI Mode

**Files to modify:**
- `source/testing/main.cpp` -- Add `--replay` and `--replay-dir` argument parsing
- `source/testing/Benchmarks.cpp` -- Add `DoReplay()` and `DoReplayBatch()`

**Stdout suppression:** Like `--suggest`, `--replay` and `--replay-dir` modes should suppress stdout during initialization (PRISMATA_ASSERT prints to stdout). Add `isReplayMode` detection to the early arg-scan loop in `main.cpp` alongside `isSuggestMode`, using the same `_dup2` redirect pattern.

**CLI interface:**
```bash
# Single replay
Prismata_Testing.exe --replay replay.json --output-dir training/data/expert/

# Batch mode (single-threaded per process)
Prismata_Testing.exe --replay-dir replays/ --output-dir training/data/expert/

# Filter by minimum rating
Prismata_Testing.exe --replay-dir replays/ --output-dir training/data/expert/ --min-rating 2000
```

**No `--threads` flag.** `InitFromMergedDeckJSON` mutates global singletons (CardTypeData, CardTypes vectors, NeuralNet mapping). Multi-threaded batch mode would produce silent data corruption. Parallelize externally:

```bash
# Process in parallel via multiple processes
ls replays/*.json | split -n l/4 -d - /tmp/replay_chunk_
for chunk in /tmp/replay_chunk_*; do
    Prismata_Testing.exe --replay-dir $(cat $chunk | head -1 | xargs dirname) \
        --output-dir training/data/expert/chunk_${chunk##*_}/ &
done
wait
```

Or with a Python wrapper (see download helper below).

**DoReplay() flow** (single replay):

```
1. Read replay JSON with std::ifstream (same pattern as DoSuggest)
2. Parse with rapidjson::Document
3. Extract deckInfo.mergedDeck, initInfo, commandInfo.commandList,
   commandInfo.clicksPerTurn, playerInfo, result, ratingInfo
4. Optional: skip if rating < --min-rating threshold
5. Create ReplayStepper, call init()
6. Create SelfPlayDataSink (or reuse existing one for batch mode)
7. For each turn:
     sink.onTurnStart(stepper.getState())    // pre-turn capture
     result = stepper.advanceTurn()
     if result == FatalError: break
8. sink.onGameEnd(winner) using replay's "result" field
   - result=0 means P1 wins, result=1 means P2 wins (verify!)
9. Log stats to stderr: turns extracted, clicks applied, skips, errors
```

**DoReplayBatch() flow** (directory):

```
1. Scan directory for *.json and *.json.gz files
2. Create shared game counter and sink:
     std::atomic<uint32_t> gameCounter{0};
     SelfPlayDataSink sink(0, outputDir, gameCounter);
   threadIndex=0 for single-process. Parallel processes must use
   different threadIndex values to avoid shard filename collisions.
3. For each file:
     - DoReplay() with shared sink
     - On fatal error: flush partial data, continue to next file
     - Progress reporting every 100 replays to stderr
4. sink.finalize() at end
5. Print summary: total replays, success count, failure count,
   records extracted, errors by category
```

**Long-lived sink rationale:** One sink per batch process, not per replay. Avoids generating 32K tiny shard files. The sink rotates at `SHARD_MAX_BYTES` (existing behavior), producing a small number of large shards matching the self-play format.

**Partial success policy:** If a replay aborts at turn 15/30, `onGameEnd()` is still called with the real game outcome. Turns 1-14 are labeled with the true winner. This is mathematically valid for value networks (the outcome is a fact about those board states) and matches the TS parser's partial recovery behavior.

**Output format:** Binary `.bin` shards identical to self-play output. Directly loadable by `train.py --selfplay-dir`. No Python changes needed.

### 1C: Replay Download Helper (Python)

**File to create:** `tools/download_replays.py`

```bash
# Download expert replays from S3
python tools/download_replays.py \
    --codes c:/libraries/prismata-replay-parser/expert_replays.json \
    --output-dir replays/ \
    --min-rating 2000 \
    --threads 10 \
    --limit 1000   # optional: for testing
```

Downloads replay JSONs from `saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz`, decompresses, saves as individual `.json` files. Uses `expert_replays.json` (key format: `Code`, `P1RatingIni`, `P2RatingIni`) for the code list and rating filter.

Handles URL encoding (`+` -> `%2B`, `@` -> `%40`). Uses `concurrent.futures.ThreadPoolExecutor` for parallel downloads. Skips already-downloaded files (idempotent).

### 1D: Verification Plan

**Tier 1 -- Golden Replay Tests (before bulk processing):**

Build a corpus of ~20 replays intentionally covering edge cases:
- Standard openings (Drone/Drone/Engineer)
- Targeting chains (USE_ABILITY -> SNIPE, USE_ABILITY -> CHILL)
- Shift-buy and shift-activate
- Undo/redo sequences (single, double, redo-after-new-action)
- Breach/Confirm/Defense transitions
- Direct ability undo (click Assigned card to un-tap, produces UNDO_USE_ABILITY)
- UNDO_BREACH (click already-breached card) and UNDO_CHILL (click frozen card)
- SELL action (click sellable card during Action phase)
- Units with beginOwnTurnScript tokens (Vivid Drone, etc.)
- Complex sac-cost abilities
- Games ending by resignation (no gameOver in engine?)

For each: verify step count matches `clicksPerTurn`, final state `isGameOver()` matches expected, winner matches `result`, and extracted turn count is reasonable (~37 per game average).

**Tier 2 -- Determinism Tests:**
- Process the same replay twice, assert identical feature vector hashes at each turn
- Assert identical shard contents (byte-for-byte)

**Tier 3 -- TS Cross-Check:**
- For replays the TS parser handles successfully, compare extracted feature vectors turn-by-turn
- Allow for sampling semantic differences (both should capture pre-turn state)
- Report any mismatches as potential bugs in either parser

**Tier 4 -- Bulk Processing:**
- Run all 32K expert replays through the stepper
- Track: success rate, failure rate, failures by error category
- Target: >95% success rate in Phase 1, >99% iteratively
- Write per-replay stats to CSV sidecar: `{code, turns_total, turns_extracted, clicks_applied, benign_skips, fatal_errors, error_messages}`

**Tier 5 -- Training Validation:**
- Train a model on C++-extracted expert data
- Compare val accuracy to TS-extracted baseline
- Train on combined self-play + expert data, measure improvement

---

## Phase 2: `--eval` CLI Mode (Neural Evaluation)

**Builds on Phase 1 ReplayStepper.**

```bash
Prismata_Testing.exe --eval replay.json
```

**Output (JSON to stdout):**
```json
{
  "ok": true,
  "code": "MVTgU-FfOgz",
  "players": ["FlopFlop", "307th"],
  "ratings": [2098, 2198],
  "winner": 1,
  "turns": [
    { "turn": 0, "player": 0, "eval": 0.02, "eval_pct": "51%" },
    { "turn": 1, "player": 1, "eval": -0.05, "eval_pct": "47%" },
    ...
  ],
  "eval_swing": 0.35,
  "biggest_mistake": { "turn": 12, "eval_drop": -0.28 }
}
```

Cheap: just `NeuralNet::evaluate()` at each turn (~2000 evals/sec). No AI search. Uses the same stdout suppression pattern as `--suggest`.

**Uses:** Post-game commentary, eval curve visualization, data quality validation.

---

## Phase 3: `--analyze` CLI Mode (Full AI Comparison)

**Builds on Phase 2.**

```bash
Prismata_Testing.exe --analyze replay.json --player PrismatAlpha_AB --think-time 1000
```

Adds to Phase 2 output:
- `human_move`: The clicks the human played this turn (from commandList)
- `ai_move`: What the AI would have played (from `getMove()`)
- `agreement`: Whether human and AI chose the same action sequence
- `agreement_rate`: Fraction of turns where human and AI agreed

Expensive: runs full Alpha-Beta or UCT search at each turn position. Only for single-replay analysis, not batch processing.

**Uses:** Commentator integration, Discord bot, teaching tool.

---

## Dependency Analysis

```
Phase 1: ReplayStepper + --replay (training data extraction)
    |-- New files: testing/ReplayStepper.h/.cpp, tools/download_replays.py
    |-- Modifies: main.cpp, Benchmarks.cpp
    |-- Uses: GameState, Action, CardTypes, InitFromMergedDeckJSON,
    |         SelfPlayDataSink, NeuralNet (feature extraction only)
    |-- No external dependencies (replays pre-downloaded by Python helper)
    |
Phase 2: --eval (neural evaluation)
    |-- Depends on: Phase 1 (ReplayStepper)
    |-- Modifies: Benchmarks.cpp
    |-- Uses: NeuralNet::evaluate()
    |
Phase 3: --analyze (full AI comparison)
    |-- Depends on: Phase 2
    |-- Modifies: Benchmarks.cpp
    |-- Uses: AI players (AlphaBeta, UCT)
```

---

## Risk Assessment

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| instId ordering doesn't match client for multi-card creates | Medium | High | Sort new CardIDs ascending. Validate with golden replays. Abort on mismatch. |
| Old replays (pre-2018) have different card stats | Medium | Low | `mergedDeck` in replay includes costs; `InitFromMergedDeckJSON` uses those values. Ability/rule changes NOT in mergedDeck may cause failures. Log replay dates, quantify by era. |
| Snapshot memory pressure on long games | Low | Low | ~2MB per 200-click game. Trivial on 32GB RAM. |
| `beginPhase(Swoosh)` at init creates unexpected cards | Low | Medium | `updateInstIdMappings()` after init catches all card creation paths. |
| Some games end by resignation (not engine gameOver) | Medium | Low | Use replay `result` field for outcome, not `state.isGameOver()`. Cross-check when both are available. |
| Feature mismatch between replay-extracted and self-play | Low | Low | Same `NeuralNet::extractFeatures()` code path. Only difference: self-play captures during Action phase; replay captures at clicksPerTurn boundaries (which should also be Action phase starts). |

---

## Parallelism Model

**Single-threaded per process.** This is a hard constraint from the architecture:

- `InitFromMergedDeckJSON` writes 3 global singletons (`CardTypeData::Instance()`, `CardTypes::allCardTypes`, `Prismata::PRISMATA_INITIALIZED`)
- `NeuralNet::Instance().buildCardTypeMapping()` writes to the singleton's `_cardTypeToUnitIndex`
- Each replay has a different `mergedDeck` requiring re-initialization
- No mutexes exist on any of these paths

**The existing Tournament threading pattern works because** all games share the same card library (initialized once before threads spawn). Replays break this assumption -- each game uses a different deck.

**External parallelism options:**

1. **Shell-level:** Split replay files across N processes
2. **Python wrapper:** `tools/batch_replay.py` launches N `Prismata_Testing.exe --replay-dir` processes, each handling a partition
3. **Future refactor (not planned):** Make card type registry + feature mapping per-instance or thread-local

**Expected performance:** Without AI search, replay stepping is fast (~10K clicks/sec). Bottleneck is file I/O (32K files). A single process should handle all 32K replays in under an hour. Parallelism is nice-to-have, not critical.

---

## Estimated Effort

| Component | LOC | Complexity | Notes |
|---|---|---|---|
| `ReplayStepper.h/.cpp` | 350-450 | Medium | Delegates click mapping to getClickAction() + instId lifecycle + snapshots |
| `initGameState()` | 80-100 | Medium | Parse initInfo, build state from public API |
| `DoReplay()` / `DoReplayBatch()` | 150-200 | Low | Wire up existing components |
| `main.cpp` arg parsing | 30-50 | Low | Copy --suggest pattern |
| `download_replays.py` | 80-100 | Low | S3 fetch with threading |
| Golden replay test corpus | 20 files | Low | Manual selection |
| Verification scripts | 50-100 | Low | Stats collection, CSV output |

Total: ~800-1050 LOC C++, ~150-200 LOC Python.

---

## Key References

| Component | File | Key Lines / Notes |
|---|---|---|
| --suggest entry point | `source/testing/main.cpp` | 23-38, 94-117 |
| --suggest implementation | `source/testing/Benchmarks.cpp` | 795-1036 |
| --suggest click generation | `source/testing/Benchmarks.cpp` | 941-1011 (reverse mapping reference) |
| getClickAction (inst->Action) | `source/engine/GameState.cpp` | 2197-2269 (authoritative click mapping) |
| GameState public API | `source/engine/GameState.h` | addCard, addCardBuyable, setMana, beginTurn |
| GameState from F6 JSON | `source/engine/GameState.cpp` | 11-187 (initFromJSON -- reference, not used directly) |
| setStartingState pattern | `source/engine/GameState.cpp` | 2016-2044 (template for init from scratch) |
| Card instId field | `source/engine/Card.h` | m_clientInstId, getClientInstId() |
| CardID assignment | `source/engine/CardData.cpp` | 304-316 (getFreeCardID -- slot reuse!) |
| Card creation paths | `source/engine/GameState.cpp` | 559 (BUY), 966 (scripts), 1256 (beginTurnScript) |
| InitFromMergedDeckJSON | `source/engine/CardTypeData.cpp` | 106+ (global singleton mutation) |
| CardTypes globals | `source/engine/CardTypes.cpp` | 8-13 (4 module-level vectors) |
| NeuralNet singleton | `source/ai/NeuralNet.cpp` | 20 (Instance), 203 (buildCardTypeMapping) |
| SelfPlayDataSink | `source/testing/SelfPlayDataSink.h/.cpp` | Full file -- reuse as-is |
| IDataSink interface | `source/testing/IDataSink.h` | 9-24 |
| TournamentGame hookup | `source/testing/TournamentGame.cpp` | 35-73 (onTurnStart/onGameEnd pattern) |
| Tournament threading | `source/testing/Tournament.cpp` | 178-293 (init-once, read-only workers) |
| Feature extraction | `source/ai/NeuralNet.cpp` | 273-424 |
| Action types | `source/engine/Constants.h` | ActionTypes enum (13 types) |
| Phase transitions | `source/engine/GameState.cpp` | 1278-1412 (beginPhase, endPhase) |
| Targeting mechanics | `source/engine/GameState.cpp` | 580-586 (USE_ABILITY flag set), 662-697 (SNIPE/CHILL) |
| Targeting detection | `source/engine/CardTypeInfo.cpp` | 126-127 (targetAction -> SNIPE/CHILL) |
| Client instId scheme | `prismata_decompiled/.../State.as` | 345, 2066-2072, 3144-3157 |
| Replay JSON format | Context doc | Section 3 |
| initInfo format | `prismata-replay-parser/src/replayData.ts` | 162-173 |
| Replay download URL | CLAUDE.md | `saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz` |

---

## Appendix A: initInfo JSON Format

```json
{
  "initInfo": {
    "initCards": [
      [[4, "Drone"], [1, "Engineer"]],
      [[5, "Drone"], [1, "Engineer"]]
    ],
    "initResources": ["0", "0"]
  }
}
```

- `initCards[0]` = Player 1 starting units, `initCards[1]` = Player 2
- Each entry: `[count, cardName, ...optional_attrs]`
- Optional attrs: `"delay"`, `"buildTime"`, `"role"`, `"blocking"`, `"lifespan"`, `"charge"`, `"hp"` (key-value pairs at positions 2+)
- `initResources`: resource strings per player (same format as `buyCost`: digits=gold, G=green, B=blue, C=red, H=energy). `"0"` = no starting resources (normal game).
- **No instIds in initInfo.** Client assigns them monotonically (P1 first, then P2).

## Appendix B: instId Assignment Trace (Standard Game)

```
initCards[0] = [[4, "Drone"], [1, "Engineer"]]
initCards[1] = [[5, "Drone"], [1, "Engineer"]]

Client assigns:
  P1 Drone  -> instId 0  (CardID 0)
  P1 Drone  -> instId 1  (CardID 1)
  P1 Drone  -> instId 2  (CardID 2)
  P1 Drone  -> instId 3  (CardID 3)
  P1 Engineer -> instId 4  (CardID 4)
  P2 Drone  -> instId 5  (CardID 5)
  P2 Drone  -> instId 6  (CardID 6)
  P2 Drone  -> instId 7  (CardID 7)
  P2 Drone  -> instId 8  (CardID 8)
  P2 Drone  -> instId 9  (CardID 9)
  P2 Engineer -> instId 10 (CardID 10)

nextInstId = 11

Turn 1: P1 buys Tarsier (card clicked, _id=<mergedDeck index>)
  -> Engine creates CardID 11 (next free slot)
  -> Stepper assigns instId 11 to CardID 11
  -> nextInstId = 12

Turn 3: P1's Tarsier dies in breach (CardID 11 killed)
  -> After removeKilledCards: CardID 11 slot freed
  -> Stepper removes mapping: instId 11 -> CardID 11

Turn 4: P1 buys another Tarsier
  -> Engine reuses slot: CardID 11 (lowest free)
  -> Stepper assigns instId 12 to CardID 11 (new card, new instId!)
  -> nextInstId = 13
```

## Appendix C: Critique Response Matrix

How each of the 6 reviews' critical issues are addressed:

| Issue | Raised By | Resolution |
|---|---|---|
| Undo/redo must be Phase 1 | All 6 | Snapshot-based, mandatory in Phase 1 |
| instId mapping underspecified | All 6 | Full lifecycle design with scan-clean-assign algorithm |
| Multi-threaded batch unsafe | 4/6 | Multi-process only, no --threads flag |
| Shift clicks missing | 5/6 | Full click type table, shift flag on Action |
| Skip vs abort distinction | 5/6 | Benign (BUY) vs fatal (desync). Abort on fatal. |
| Turn sampling mismatch | 3/6 | Pre-turn capture using clicksPerTurn array |
| GameState init from initInfo | 3/6 | Public API build (addCard, addCardBuyable, setMana, beginPhase) |
| SNIPE/CHILL from source card | 3/6 | Source card's getTargetAbilityType() determines action |
| Phase 3 scope creep | 3/6 | Split into Phase 2 (--eval, cheap) and Phase 3 (--analyze, expensive) |
| 95% target too low | 2/6 | 95% initial target, iterate toward 99%. Track failures by category. |
| Game version compatibility | 3/6 | mergedDeck carries costs; log dates; quantify failures by era |
| Shard output granularity | 1/6 | Long-lived sink per batch process, not per replay |
| Partial success policy | 2/6 | Keep partial data, label with real outcome |
| std::map hot path | 1/6 | Use unordered_map for instId lookups |
| Cancel targeting edge case | 1/6 | Try UNDO_USE_ABILITY then reinterpret as USE_ABILITY |
| ASSIGN_FRONTLINE ambiguity | 1/6 | Handled by getClickAction() delegation (all 13 action types) |
| rapidjson ownership | 1/6 | ReplayStepper owns Document, stores parsed clicksPerTurn |
| Regression testing | 1/6 | Golden replay corpus + determinism tests |
| **Post-review additions** | | |
| Click tree incomplete (UNDO_USE_ABILITY, SELL, WIPEOUT, UNDO_BREACH, UNDO_CHILL) | Quality review | Delegate to getClickAction() — engine's authoritative mapping |
| beginPhase() is private | Quality review | Use public beginTurn() instead |
| SelfPlayDataSink constructor needs atomic | Quality review | Explicit gameCounter + threadIndex in pseudocode |
| File placement (engine/ vs testing/) | Quality review | Moved to source/testing/ to preserve layered architecture |
| Cancel-targeting FatalError too aggressive | Quality review | BenignSkip when reinterpretation also fails |
| Stdout suppression for --replay | Quality review | Same _dup2 pattern as --suggest |
