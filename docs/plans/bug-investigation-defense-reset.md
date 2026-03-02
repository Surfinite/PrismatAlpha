# Defense Phase Reset Bug — Investigation Kickoff

> **Instructions**: Paste this entire document into a new Claude Code context.
> The context has access to CLAUDE.md and the full codebase. Work through all 4 phases
> of `docs/plans/bug-investigation-prompt.md` using the bug description below.

---

## Read these files first

Before starting the investigation, read these files to orient yourself:

1. `docs/plans/bug-investigation-prompt.md` — the investigation framework (follow all 4 phases)
2. `CLAUDE.md` — project context, architecture, current status, key files
3. `source/engine/GameState.cpp` lines 1285-1314 — the buggy code
4. `source/engine/GameState.cpp` lines 452-454 — ASSIGN_BLOCKER legality check
5. `source/engine/Card.cpp` — card status lifecycle, `beginOwnTurn` reset logic
6. `source/engine/CardType.h` — `CardStatus` enum (Default, Assigned, Inert)
7. `bin/asset/config/cardLibrary.jso` — search for "Drone" to see blocking config

---

## The Bug

### Symptom
During the Defense phase, units that were **tapped** (used their ability or clicked
for gold) in the preceding Action phase are incorrectly available as blockers. In the
GUI, tapped Drones show green borders (legal blocker highlight) when they should not.
The AI's search tree also sees these as legal blocking moves.

### Location
`source/engine/GameState.cpp`, function `beginPhase()`, lines 1289-1307.

A 20-line block resets ALL cards' statuses to `Default` (for ability cards) or `Inert`
(for non-ability cards) at the start of the Defense phase. This erases the `Assigned`
status that cards get when they use abilities during Action phase.

The code has an inline comment stating:
> "units can block during defense regardless of prior ability use"

**This comment is wrong.** In Prismata, units that have been tapped (clicked for gold,
used abilities) should remain in `Assigned` status and be UNABLE to block. Only untapped
units should be available as blockers.

### When introduced
Commit `5bf57a8` on **Feb 13, 2026** — part of "Blend tournaments, engine validation
tooling" work. The reset was added based on a mistaken understanding of the blocking
rules, likely to make validation tests pass against observed game behaviour.

### What game rule it violates
In Prismata, the Drone unit (and other units with abilities) have two states:
- **Untapped** (`CardStatus::Default`/`Inert`): Can block during Defense
- **Tapped** (`CardStatus::Assigned`): Used ability or clicked for gold — CANNOT block

The bug resets tapped cards back to untapped before Defense, making everything blockable.
This means:
- Drones tapped for gold can also block (should be one or the other)
- Units that used abilities (e.g., Tarsier attacking) can also block
- Frozen/chilled units may have their chill state interfered with

### Mechanism chain
1. Player's Action phase: Drones are clicked for gold → status becomes `Assigned`
2. Action phase ends, `beginPhase(Defense)` is called
3. **BUG**: Lines 1289-1307 reset all `Assigned` cards back to `Default`/`Inert`
4. `isLegal(ASSIGN_BLOCKER)` at line 454 checks `canBlock()` → returns true (status was reset)
5. AI search explores blocking with these units, self-play records these states
6. Game outcomes are affected (more defense available than should be)

### Scope
- **Core engine** — affects ALL game simulation, not just GUI or neural net
- **Symmetric** — both self-play sides use the same engine, so both experience the bug
- **Every game** — Drones are in every Prismata game (base set), so every single game
  in the 722K-game dataset has this bug active

---

## Specific questions to answer

Beyond the standard 4-phase investigation, I need answers to these:

1. **Self-play data triage**: All ~722K games (26.7M records, 178GB in S3) were generated
   AFTER commit 5bf57a8 (Feb 13). Is ANY of this data unaffected, or is it all generated
   with the buggy engine?

2. **Tournament result validity**: The WR progression (3.6% → 26.7% → 45.3% → 51.9%)
   was measured with BOTH sides using the buggy engine. Does the relative improvement
   still hold, even if absolute WR numbers might shift after the fix?

3. **Model knowledge salvageability**: The current model (256h/3L, 722K games, 51.9% WR)
   learned Prismata strategy with slightly more defense available than the real game.
   Is this a "the model learned a variant of the game" situation (degraded but salvageable)
   or "the model learned fundamentally wrong defense evaluation" (invalidated)?

4. **Frontline penalty test**: There's an active EC2 fleet running a frontline penalty
   isolation test on branch `test/frontline-penalty`. Does that branch also have this bug?
   If so, should the fleet be terminated immediately?

5. **Quick empirical test**: Can we run a short (100-game) tournament with the fix applied
   to see if the model's WR changes significantly? This would tell us whether the bug
   actually matters in practice, regardless of theoretical analysis.

6. **Cheapest recovery path**: Given that the bug is symmetric and the model showed
   consistent improvement, what's the minimum-cost path to get back on track?
   Options to evaluate:
   - Fix engine + continue generating new self-play + retrain on mixed data
   - Fix engine + discard all old data + regenerate from scratch
   - Fix engine + fine-tune existing model on small batch of clean data
   - Accept the model as-is and just fix going forward

---

## After the investigation

Once you've completed all 4 phases, summarize your findings and proposed fix.
Do NOT apply the fix — just describe it. I'll review and approve before any
code changes are made.

If you determine the severity is "Degraded" or worse, also draft a short
status update I can add to CLAUDE.md documenting the bug and its impact.
