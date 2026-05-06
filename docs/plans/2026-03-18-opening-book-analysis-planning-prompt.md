# Planning Prompt: Opening Book Analysis Database

> **Purpose**: Hand this prompt to a fresh Claude context to produce a full implementation plan.
> **Skills to invoke**: `superpowers:brainstorming` first, then `superpowers:writing-plans`.

---

## Context

You are working on **PrismataAI** at `c:\libraries\PrismataAI`. This is a C++ game engine and AI for **Prismata**, a turn-based perfect-information strategy card game.

The replay parser lives at `c:\libraries\prismata-replay-parser\`. The two repositories work together.

---

## Background

### The Replay Dataset

- **102,697 training-eligible replays** in `c:\libraries\prismata-replay-parser\replays_archive\` (both players 1500+ rated, balance-validated, pre-patch-cutoff)
- Replays are stored as `.json.gz` files
- Metadata is in `c:\libraries\prismata-replay-parser\replays.db` (SQLite) — includes `code`, `p1_rating`, `p2_rating`, `result`, `timestamp`, `balance_ok`
- The existing JS replay parser infrastructure is at `c:\libraries\prismata-replay-parser\`

### The Game

- Each game uses a **set** of 8 randomly chosen **Dominion cards** (from 105 possible) plus the 11 base units (always present)
- A game is 2 players alternating turns. Player 1 starts with 6 Drones + 2 Engineers. Player 2 starts with 7 Drones + 2 Engineers (extra Drone compensates for going second)
- **Buying** happens during the Action phase. Players can buy 0, 1, or more units per turn from the active supply
- The first 5 turns per player are the "opening" — this is when economy is established, tech buildings are purchased, and strategic direction is set. After turn 5 the game diverges too much for opening book guidance

### The Current Opening Books

The AI has opening book entries in `bin/asset/config/config.txt` (`LiveOpeningBook2` — 50 entries). These hardcode what to buy on turns 1-3 based on:
- Current units owned (`self` condition: e.g. `[["Drone", 7], ["Engineer", 2]]`)
- Which special units are in the set (`buyable` condition: e.g. `["Blastforge", "Tarsier"]`)
- Buy sequence to execute (`buy`: e.g. `["Drone", "Drone"]`)

Current OBs only extend to turn ~3. They cover special cases (Wild Drone present, Doomed Drone present, etc.) and generic fallbacks (`["Drone", "Drone"]`). Coverage is incomplete — many set compositions fall through to the generic fallback when a better specific entry exists.

### The Goal

**Build a database of opening buy sequences from all 102,697 expert replays, covering the first 5 turns per player, linked to set composition — enabling complete analysis freedom for deriving improved opening book entries.**

This feeds into a longer-term RL self-play training pipeline where well-calibrated opening books:
1. Provide a strong starting policy for early turns
2. Are gradually relaxed as the RL value function matures
3. Are derived from human expert consensus rather than theorycrafting

---

## What the Plan Should Cover

1. **Schema design**: The database schema for storing opening data. Key entities:
   - Per-replay set composition (which 8 Dominion cards are active)
   - Per-player, per-turn buy sequences for turns 1-5
   - Starting state context at each turn (how many Drones/Engineers the player has — needed to match OB `self` conditions)
   - Winner information (to filter to winning-side openings)
   - Join path to existing `replays.db` metadata (ratings, result)

2. **Extraction script**: A new Node.js script (or Python — choose what fits best given existing infrastructure) at `c:\libraries\prismata-replay-parser\` that:
   - Iterates over all 102,697 eligible replays
   - Parses the replay JSON (handling `.json.gz`)
   - Extracts set composition, per-turn buy sequences, and starting state per turn
   - Writes into the new database
   - Handles errors/missing data gracefully (incremental, resumable)

3. **Analysis queries**: Example SQL queries demonstrating the intended use:
   - "What do 1500+ players buy on turn 1 when Blastforge is in the set?" (frequency table)
   - "What is the consensus turn-2 buy sequence when Synthesizer AND Blood Phage are both present?"
   - "Which set compositions have no consensus (high variance in buy choices)?"
   - "Winning-side turn 1-3 sequence frequency for sets containing Tarsier"

4. **OB derivation workflow**: How to go from the database to candidate opening book entries — what consensus threshold to use, how to handle the `self` condition (starting units), how to handle set composition matching (exact match vs. key-unit presence)

5. **Integration with existing infrastructure**: Whether to extend `replays.db` with new tables or create a separate `openings.db`. The plan should justify the choice.

---

## Existing Infrastructure to Be Aware Of

**At `c:\libraries\prismata-replay-parser\`:**
- `replays.db` — SQLite with replay metadata (`code`, `p1_rating`, `p2_rating`, `result`, `balance_ok`, `timestamp`)
- `replays_archive/` — 102,697 `.json.gz` replay files
- `fetch_expert_replays.js` — fetches replays from API
- `filter_expert_replays.js` — filters by rating/balance
- `extract_training_data.js` — extracts training positions (V1 JSONL format)

**Replay JSON structure (key fields):**
- `deckInfo.mergedDeck` — array of cards in the set (display names, includes base units)
- `commandList` — flat array of all clicks across the entire game: `{_type, _id}`
- `clicksPerTurn` — array of click counts per turn (slices commandList into turns)
- `playerInfo` — array indexed by player (0=P1, 1=P2). NO `playerNumber` key — use array index
- `result` — 0=P1 wins, 1=P2 wins, 2=draw
- Click `_type` values for buys: `"card clicked"` with `_id` matching a card in mergedDeck
- Supply limit by rarity: legendary=1, rare=4, normal=20

**Key gotcha — click counting ≠ buy counting**: `"card clicked"` does NOT guarantee a purchase. A click on an already-maxed supply slot is rejected. Must enforce supply limits when counting actual buys.

**Card names in replays use display names** (e.g. "Synthesizer", "Tarsier"). The internal C++ engine uses codenames ("Factory", "Tesla Tower"). For this analysis, display names are fine — we're working entirely in JS/Python and the OB entries in config.txt already use display names.

---

## Constraints

- Cost-conscious — prefer local compute, no cloud for this task
- The extraction should be **incremental and resumable** — 102k replays may take a while; should be able to stop and restart
- Output should support **arbitrary SQL queries** — the database is the analysis artifact, not pre-computed summaries
- The existing `replays.db` and replay archive must not be modified or corrupted

---

## Key Questions for Brainstorming

- New tables in `replays.db` vs. separate `openings.db`?
- Node.js (consistent with existing parser infra) vs. Python (more natural for data analysis)?
- What granularity for "set composition" — store all 8 cards, or only the Dominion cards (excluding always-present base units)?
- How to handle the `self` condition (starting state) — store full resource snapshot, or just unit counts?
- Turn numbering: game turns vs. per-player turns (player 1's turn 1 = game turn 1, player 2's turn 1 = game turn 2)
