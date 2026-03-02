# Commentary Generation Instructions

You are writing post-game commentary for a Prismata replay. This document tells you how to extract data from any replay, understand the game, and write engaging commentary suitable for Discord.

## Replay Code

You will be given a replay code to commentate. If no code is specified, use the **standard test replay**:

> **`FxCfR-K49T+`** — Surfinite (1856) vs Kolento (2222), P1 wins. Deck includes Animus, Vai Mauronax, Plasmafier, Ebb Turbine, Forcefield. This is our default comparison replay for evaluating commentary quality.

Replace `CODE` in all commands below with the actual replay code.

## Step 1: Extract Game Data

Run these commands from the project root (`c:\libraries\PrismataAI`):

### 1a. C++ Analysis (AI comparison + neural eval)

```bash
python tools/generate_commentary_data.py "CODE" --think-time 50
```

This fetches the replay from S3, runs the C++ engine's `--analyze` mode, and outputs:
- Players, ratings, result, deck
- Per-turn neural evaluation (P1 win probability)
- Per-turn human buys vs AI-recommended buys
- Agreement rate and biggest eval swings

**Note:** The C++ click application rate is ~40-60% for most replays. Buys extracted from `--analyze` handle `revert clicked` (undo) correctly but may overcount because `card clicked` events don't always succeed (sold-out or insufficient resources).

### 1b. Python Resource Validation (accurate buy tracking)

```bash
python tools/generate_commentary_data.py "CODE" --validate --verbose
```

This runs a pure-Python resource tracker that simulates the game economy turn by turn:
- Tracks gold (persists), green (persists), blue/red/energy (use-or-lose)
- Validates each BUY click against available resources
- Handles build times, ability activations, buySac requirements
- Rejects clicks that the server would have silently failed

The `--verbose` flag shows resource state before and after each click. The `--validate` output is the ground truth for what was actually purchased each turn.

### 1c. Raw Replay Data (manual inspection)

If you need to check specific details, the replay JSON is cached after first fetch at:
```
bin/replays_test/{CODE_WITH_ENCODING}.json
```
(Special characters are encoded: `+` → `_PLUS_`, `@` → `_at_`)

Key fields:
- `deckInfo.mergedDeck` — all cards available in this game (stats, costs, abilities)
- `initInfo.initCards` — starting cards per player `[[count, "Name"], ...]`
- `initInfo.initResources` — starting resources per player
- `commandList` — every click in the game (card clicked, inst clicked, revert clicked, space clicked)
- `clicksPerTurn` — array slicing commandList into per-turn segments
- `ratingInfo.finalRatings[i].displayRating` — player ratings (float, use int())
- `playerInfo` — player names (array index = player number, NO `playerNumber` key)

### Turn Numbering

The output uses **shared round numbering**: T1 P1, T1 P2, T2 P1, T2 P2, etc. Each "T" is a shared round, and each player takes one turn per round. A 15-round game has 30 player-turns total.

## Step 2: Understand the Game

### Prismata Basics

Prismata is a turn-based, perfect-information strategy game. Two players buy units from a shared pool: 11 base-set units always available, plus 5-11 random units chosen for each game. No luck, no hidden information. Goal: destroy all enemy units (or force resignation).

**P1** starts with 6 Drones + 2 Engineers. **P2** starts with 7 Drones + 2 Engineers (extra Drone compensates for going second).

Each turn: **Defense** (assign blockers) then **Action** (use abilities, buy units). Attack pools across all your attackers. Biggest non-fragile blocker absorbs non-lethal damage (heals next turn). If attack exceeds total defense: **breach** — attacker picks which units die.

### Resources

| Resource | Persists? | Producer | Key Rule |
|----------|-----------|----------|----------|
| Gold | yes | Drone (1/turn) | Float 1-2 OK, 3+ wasteful |
| Green | yes | Conduit (1/turn) | Cheapest tech, stockpiles |
| Blue | NO | Blastforge (1/turn) | Must spend or lose it |
| Red | NO | Animus (2/turn) | Must spend or lose it |
| Energy | NO | Engineer (1/turn) | Mainly matters early game |

### Base Set Units

| Unit | Cost | Build Time | HP | Role |
|------|------|-----------|-----|------|
| Drone | 3+E | 1 | 1 | Economy. Click for 1 gold. |
| Engineer | 1 | 1 | 1 | Blocker. Produces 1 energy. |
| Conduit | 4 | 1 | - | 1 green/turn. Least committal tech. |
| Blastforge | 5+E | 1 | - | 1 blue/turn. Needed for Walls. |
| Animus | 6 | 1 | - | 2 red/turn. Expensive to maintain. |
| Tarsier | 4+R | 2 | 1 | Auto-attack 1. Efficient, breach-vulnerable. |
| Rhino | 5+R | 1 | 2 | Prompt blocker. Click-attack 1. Versatile. |
| Wall | 5+B | 1 | 3 | Prompt. Best base absorber (absorbs 2). |
| Steelsplitter | 6+B | 1 | 3 | Blocker. Click to attack 1. Jack of all trades. |
| Gauss Cannon | 6+G | 1 | 4F | Auto-attack 1. Fragile, high HP. Breachproof. |
| Forcefield | 1G (eats Drone) | 0 | 1F | Prompt fragile blocker. Emergency defense. |

BT=build time, F=fragile, E=energy, R=red, B=blue, G=green. "Prompt" = 0 build time, can block immediately.

### Strategy Principles

- **Spend everything.** Unspent resources are wasted tempo. Float 1-2 gold is fine, 3+ is a mistake.
- **Delay defense.** Buy prompt blockers (Wall, Rhino) at the last possible moment. Every gold spent on economy early compounds.
- **Absorb is king.** The biggest non-fragile blocker absorbs damage each turn. Getting Wall online = absorb 2 damage/turn for free.
- **Changing gears.** Once you have enough economy, stop buying Drones and switch to attackers/defense. Timing this transition is the core skill.
- **Tech math.** 1 Conduit needs 3G/turn to spend efficiently. 1 Blastforge needs 5G/turn. 1 Animus needs 8G/turn. Don't overtech.
- **Drone count.** With Wall absorb (2 HP): 12-15 Drones. With 4+ HP absorber: 15-20 Drones. With 5+ HP: 20+, get 3rd Engineer.

### Key Commentary Terms

| Term | Meaning |
|------|---------|
| Absorb | Non-lethal damage on biggest blocker; heals next turn |
| Breach | Attack > total defense; attacker picks targets |
| Soak | Deliberately sacrificing a blocker for lethal damage |
| Exploit | Attacking for an amount that denies good absorb |
| Float | Unspent resources at end of turn |
| Granularity | Ability to block any damage amount efficiently |
| Tech | Conduit/Blastforge/Animus (resource producers) |
| Tempo play | Aggressive, aims to end quickly |
| Econ play | Defensive, aims to outscale |
| Breachproof | High-HP units that survive breach |
| Chill | Prevents blocking; chill >= HP = unit frozen |
| Prompt | Zero build time, can block immediately |
| Frontline | Targetable by attacker even through blockers |
| Gambit | Deliberately underdefending to save resources |

## Step 3: Read Unit-Specific Knowledge

For any random set units in the game's deck, look up strategic notes in:
- `docs/commentary-knowledge/03-advanced-units.md` — 80+ unit profiles with tier rankings, strategy notes
- `docs/commentary-knowledge/04-strategy-concepts.md` — chill theory, breachproof strategy, rush timing
- `docs/commentary-knowledge/05-openings-builds.md` — common opening sequences
- `docs/prismata-strategy-guide.md` — comprehensive 17-chapter strategy guide

Also check the Prismata wiki for unit-specific details:
```
https://prismata.fandom.com/wiki/UNIT_NAME
```

## Step 4: Write Commentary

### Format Requirements

Write the commentary as a series of Discord messages. Each message must be under 2000 characters (Discord limit). Use `== MESSAGE N ==` delimiters between messages.

### Structure

1. **Message 1: Introduction** — Players, ratings, deck analysis (which random units are in the set and what strategy they encourage), prediction of likely game plan for each side.

2. **Messages 2-4: Opening & Development** (turns 1-5ish) — Economy decisions, tech choices, when each player gets their first attacker online. Note any deviations from standard openings.

3. **Messages 4-7: Midgame** — Attack/defense buildup, key purchases, eval swings. Where the C++ AI agrees/disagrees with the human player. When does each player "change gears" from economy to attack?

4. **Messages 7-9: Endgame & Climax** — Decisive moments, breach threats, final attack. Who had the critical advantage and when did it crystallize?

5. **Final Message: Summary** — Overall assessment, key turning point, what decided the game.

### Tone Guidelines

- Write as an enthusiastic but knowledgeable esports commentator. Think chess commentary meets competitive gaming.
- Use Prismata terminology naturally (absorb, breach, float, tech, etc.)
- Reference specific turn numbers and purchases: "At T5, Kolento picks up two Blastforges — committing hard to a Wall-based defense."
- Point out interesting decisions: agreements and disagreements with the AI, resource efficiency, timing of gear changes.
- Use the neural eval to create narrative tension: "The eval swings from 52% to 41% here — that Tarsier buy may have been premature."
- Be specific about WHY moves are good/bad, not just that they are.
- Keep it engaging for readers who understand Prismata basics but aren't experts.

### What NOT to Do

- Don't just list every purchase mechanically ("T1: Drone Drone, T2: Drone Drone Drone").
- Don't comment on every single turn — focus on the interesting ones.
- Don't make up information. If the data is ambiguous, say so.
- Don't reference any previous commentary for this game — generate everything fresh from the data.

## Step 5: Output

Save the commentary to:
```
bin/commentary/commentary_{CODE}.txt
```

**Preserve previous versions:** If `commentary_{CODE}.txt` already exists, rename it to `commentary_{CODE}_{TIMESTAMP}.txt` (e.g. `commentary_FxCfR-K49T+_2026-02-21_1530.txt`) before writing the new version. This keeps a history of all commentary iterations for the same replay.

Use the `== MESSAGE N ==` delimiter format. Example:

```
== MESSAGE 1 ==
**{CODE}** — Player1 (rating) vs Player2 (rating)

Today we're looking at a fascinating matchup between...

== MESSAGE 2 ==
**Opening Phase (T1-T3)**

Both players open with standard double-Drone...
```

## Reference: Command Cheat Sheet

```bash
# Full analysis (AI comparison, ~30s)
python tools/generate_commentary_data.py "CODE" --think-time 50

# Resource-validated buys only (instant, no C++ needed)
python tools/generate_commentary_data.py "CODE" --validate

# Resource validation with debug output
python tools/generate_commentary_data.py "CODE" --validate --verbose

# Neural eval only (fast, no AI search)
python tools/generate_commentary_data.py "CODE" --eval-only

# Read raw replay JSON (cached after first fetch)
python -m json.tool bin/replays_test/{CODE_WITH_ENCODING}.json
```

## Appendix: Replay Sources

Replays are stored as gzipped JSON on S3. The tool fetches them automatically. URL format:
```
http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{CODE}.json.gz
```
Special characters must be URL-encoded (`+` → `%2B`, `@` → `%40`). The tool handles this.

To find interesting replays to commentate, check:
- `c:\libraries\prismata-replay-parser\expert_replays.json` — 31K+ expert replays (2000+ rating)
- `bin/prismata_capture_codes.txt` — sniffer-captured replay codes (TSV: timestamp, code, source)
- `bin/all_replay_codes.txt` — aggregated codes from various sources
