# Meta-Review: Engine Logic Audit Plan

> 10 external reviews analyzed. Codebase validated against all claims.

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|----------|-----------|-----------------|----------------|
| R1 | Mostly positive, significant critiques | Lifespan-1 promotion, done criteria, swoosh ordering, stagnation | "Trace the swoosh" as primary audit strategy; golden state test |
| R2 | Mostly positive, structural critiques | Script/trigger ordering as P0, event timeline artifacts, phase transitions | Mandatory "event timeline + invariants" deliverable before P0 |
| R3 | Mostly positive, structural critiques | Stagnation as "single biggest misjudgment", chill formula proof, EndTurnObject.as | 4-case chill formula enumeration requirement; simultaneous death ordering |
| R4 | Mixed, strategic critique | 44.3% replay failures as starting point, terminal states, action generation | Replay failure categorization as audit data source (unique among all reviews) |
| R5 | Mixed, methodology focus | F6 differential testing, confidence metrics, exit criteria | Game state equivalence classes; risk matrix format |
| R6 | Mostly positive, practical | Large-file fatigue, coverage matrix, tooling aids | Coverage % per file; self-play impact estimator per finding |
| R7 | Mostly positive, priority reordering | Phase transitions FIRST in P0, chill proof methodology, defense fix as Phase 0 | "Burden of proof should be on equivalence" framing; property-based testing |
| R8 | Mostly positive, tightening | Lifespan-1 as "second blocking bug hiding in plain sight", negative test construction | Concrete test case table format with expected AS3 behavior |
| R9 | Mostly positive, coverage gaps | Execution order as missing P0, chill reset timing, prompt units, Spell/Exhaust/Consume | Unit-mechanic-level gaps (prompt, spell, exhaust, consume) |
| R10 | Mostly positive, verification gaps | Defense fix verification step, ALL status reset locations, energy system | Audit all status resets comprehensively, not just blocking chain |

---

## A.2 — Consensus Points

Ranked by number of reviewers raising the point:

| # | Point | Reviewers | Count |
|---|-------|-----------|-------|
| 1 | **Lifespan-1 blocking needs explicit audit** | R1,R3,R4,R7,R8,R9,R10 | 10/10 |
| 2 | **Stagnation / game-over conditions underrated** | R1,R3,R4,R5,R6,R7,R9 | 7/10 |
| 3 | **Script/trigger execution ordering missing** | R1,R2,R3,R5,R6,R8,R9 | 7/10 |
| 4 | **Phase transitions (B1) should be P0** | R2,R3,R5,R7,R8,R9,R10 | 7/10 |
| 5 | **Time estimates unrealistic** | R1,R2,R3,R4,R6,R7,R8 | 7/10 |
| 6 | **Sellable role should be promoted** | R1,R3,R5,R6,R7,R9,R10 | 7/10 |
| 7 | **P3 should be deferred/removed** | R1,R2,R5,R6,R7,R9,R10 | 7/10 |
| 8 | **Chill formula needs algebraic proof, not hand-waving** | R1,R3,R5,R7,R8,R9 | 6/10 |
| 9 | **Completion criteria / "done" definition needed** | R1,R2,R5,R6,R7,R10 | 6/10 |
| 10 | **Option B (automated cross-reference) should be removed** | R1,R2,R3,R6,R7 | 5/10 |
| 11 | **Negative testing strategy absent** | R5,R8,R9,R10 | 4/10 |
| 12 | **Simultaneous death ordering missing** | R2,R3,R8,R9 | 4/10 |
| 13 | **cardLibrary.jso parsing parity check needed** | R3,R5,R9,R10 | 4/10 |

---

## A.3 — Outlier Points

| Point | Reviewer | Merit Assessment |
|-------|----------|-----------------|
| **44.3% replay failures as starting point** | R4 | **High merit but nuanced.** The 849 remaining failures are categorized by type (USE_ABILITY 276, SNIPE 173, etc.) and could guide the audit. However, these failures represent C++ being MORE STRICT than AS3 (rejecting moves), while the blocking bug was C++ being MORE PERMISSIVE. The replay failures catch a different bug class than what this audit targets. Still worth checking as a diagnostic signal. |
| **Energy system audit** | R10 | **Low merit.** Energy is reset in `beginTurn()` alongside Blue/Red/Attack (GameState.cpp:1220). It follows the same pattern as other transient resources. No special handling in AS3 either. Not a unique risk area. |
| **Prompt unit handling** | R9 | **Medium merit.** Prompt (buildtime=0) units are handled implicitly — they have `constructionTime=0` so they pass all blocking/ability checks immediately. The `isPrompt()` check in CardType.cpp (line 89) confirms: `canBlock(false) && (getConstructionTime() == 0)`. Not a separate mechanic requiring dedicated audit. |
| **Spell/Exhaust/Consume mechanics** | R9 | **Low merit for Spell** (just lifespan=1, already covered). **Medium merit for Exhaust** (delay-like mechanic, probably maps to `m_currentDelay`). **Medium merit for Consume** (sac-with-constraints, covered by script ordering audit). |
| **Property-based fuzzing** | R2,R7 | **Medium merit.** Could catch invariant violations without AS3 comparison. But requires significant setup effort and won't prove equivalence — only catches internal consistency bugs. Better as a Phase 3 addition than a substitute. |
| **Context window limitations for LLM auditors** | R4 | **Valid concern.** State.as (4,490 lines) + GameState.cpp (2,388 lines) together exceed comfortable single-pass reading. The plan should recommend chunking by function, not whole-file reads. |
| **Defense-reset fix as Phase 0 prerequisite** | R7 | **Rejected.** The bug is on a separate branch (`feature/postgame-commentary` currently checked out, fix planned for `master`). The audit should DOCUMENT the bug and verify the fix plan is correct, not block on applying it first. The audit may find additional bugs that should be fixed together. |
| **AST extraction for coverage analysis** | R6,R8 | **Low merit.** Cross-language AST comparison (AS3↔C++) would require custom tooling for two very different languages. Simple `grep` for function names provides 80% of the coverage signal at 1% of the effort. |
| **Coverage matrix artifact** | R6 | **Medium merit.** Tracking "% of relevant code read" per file is a reasonable audit hygiene measure, though percentage-of-lines is a poor proxy for coverage depth. Function-level tracking is better. |

---

## A.4 — Category Breakdown

### Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality | Recommendation |
|----------|-------------|-----------------|----------------|
| B1 (Phase Transitions) should be P0, not P1 | R2,R3,R5,R7,R8,R9,R10 | **VALIDATED.** C++ has 5 explicit phases (Action, Breach, Confirm, Defense, Swoosh) where AS3 has 3 phases + swoosh function. The known bug IS a phase-boundary bug. `beginPhase()` at GameState.cpp:1278 and `endPhase()` at line 1328 implement the full state machine. Phase transitions determine when `beginTurn()` runs (Swoosh only), when `calculateGameOver()` runs (Confirm only), and when status resets occur. All other P0 items depend on phase boundaries being correct. | **Must-do: Promote to P0 and execute first.** |
| Phase transitions should be the organizing principle | R1 | Architecturally sound — the known bug was a phase-boundary bug, and tracing phase transitions covers blocking, chill, breach all implicitly. | **Should-do: Reorganize P0 around phase boundaries.** |
| "Burden of proof should be on equivalence" | R7 | Correct framing. The defense-reset bug shows that "looks similar" ≠ equivalent. | **Should-do: Require explicit proof per area.** |
| Add event timeline + state invariants as mandatory artifact | R2 | Good idea — a side-by-side "what happens at each phase boundary" document would catch ordering bugs. | **Must-do: Add as Phase 1 prerequisite deliverable.** |

### Risks & Concerns

| Feedback | Reviewer(s) | Codebase Reality | Recommendation |
|----------|-------------|-----------------|----------------|
| Stagnation (C1) should be P0/P1 | R1,R3,R4,R5,R6,R7,R9 | **VALIDATED.** AS3 has 4-level stagnation system (`incrementTurnNoProgressCounters`, cutoffs [2,8,20,40]) + "all opponent units doomed" instant-win (`checkWin()` in State.as:3298). C++ has ONLY `m_turnLimit = 200` (Game.h:17) + card-count-zero check (GameState.cpp:1207-1213). The "all units doomed" instant-win is **confirmed missing**. Games where one side has only lifespan-1 units would end in AS3 but continue 1 extra turn in C++. Impact: training data includes 1 extra turn of garbage signal in already-won games. The stagnation counters have larger impact: positions near economic stalemates get different game-length outcomes. | **Must-do: Promote "all units doomed" instant-win to P0. Promote stagnation counters to P1.** |
| Script/trigger ordering is missing and could be P0 | R1,R2,R3,R5,R6,R8,R9 | **PARTIALLY VALIDATED.** Script.as (104 lines) and Trigger.as (95 lines) are data containers — no ordering logic inside them. Script EXECUTION happens in State.as swoosh and GameState.cpp `runScript()`. C++ Script.cpp (143 lines) is also data-only. The real risk is in `beginTurn()` ordering: C++ runs beginOwnTurnScripts in a SECOND PASS after all card beginTurns (GameState.cpp:1256-1273), while AS3 swoosh intermixes lifespan/delay/script processing in a single pass. **This is a genuine ordering difference.** | **Must-do: Add as P1 audit area.** |
| Simultaneous death ordering | R2,R3,R8,R9 | **VALIDATED as a real concern.** C++ processes cards via `getCardIDs()` iteration order. AS3 uses `copyOfInstIds` (State.as swoosh). If units with death triggers die in different orders, post-death state differs. However, Prismata has very few death-trigger units, limiting practical impact. | **Should-do: Add as P1 sub-item under breach/swoosh audit.** |
| Time estimates unrealistic | R1,R2,R3,R4,R6,R7,R8 | State.as alone is 4,490 lines. GameState.cpp is 2,388 lines. Card.cpp is ~1,000 lines. Thorough P0 comparison of these is not a 2-hour task. | **Must-do: Remove fixed time estimates, use per-area timeboxes.** |
| Manual audit "looks equivalent" failure mode | R2,R4,R5 | The defense-reset bug proves this risk is real — 19 lines that "look like they help" were actually wrong. | **Must-do: Require concrete test cases per P0 area, not just "read and confirm."** |

### Suggested Removals / Simplifications

| Feedback | Reviewer(s) | Recommendation |
|----------|-------------|----------------|
| Remove Option B (Automated Cross-Reference) | R1,R2,R3,R6,R7 | **Agree.** Keep as one-liner mention, not a full option. |
| Remove P3 entirely | R2,R5,R6,R7,R9,R10 | **Agree.** D1 (Resonance), D2 (Invulnerability), D3 (Mass Chill) are unit-specific edge cases. Defer to future work. |
| Condense Options A-C | R3,R7,R10 | **Agree.** Only Option D is used. |
| Remove GUI verification as formal step | R7,R10 | **Agree.** F6 export + `--suggest` is more reliable than visual spot-checking. |
| Remove "CAN read / CANNOT modify" (redundant) | R3 | **Disagree.** It's 2 lines and prevents confusion. Keep. |

### Suggested Additions / Features

| Feedback | Reviewer(s) | Codebase Reality | Recommendation |
|----------|-------------|-----------------|----------------|
| Verify defense-reset bug fix | R7,R10 | The bug at GameState.cpp:1289-1307 is still present (confirmed in code). The plan should include verifying the fix once applied. | **Should-do: Add as Phase 3 item.** |
| Audit ALL status reset locations | R10 | **HIGH VALUE.** `grep -n "setStatus" Card.cpp GameState.cpp` reveals resets in: beginPhase:Defense (the bug), Card::beginTurn() (line 632-639), Card constructor (lines 200-236), and useAbility. A comprehensive scan would catch other phase-boundary resets. | **Must-do: Add as P0 sub-task.** |
| Sellable role to P1 | R1,R3,R5,R6,R7,R9,R10 | **VALIDATED.** C++ sets `m_sellable = true` on buy (Card.cpp:206), clears in `beginTurn()` (line 577). AS3 uses `role = "sellable"` string. The transition timing matters: C++ clears sellable at Swoosh (beginTurn), AS3 also clears at swoosh. But the question is whether `m_sellable` is checked in all the same code paths as AS3's `role == "sellable"`. Sellable units can be "sold" (undone) in AS3 — C++ has limited undo. | **Should-do: Promote to P1.** |
| Chill formula algebraic proof | R1,R3,R5,R7,R8,R9 | **VALIDATED as needed.** C++ `isFrozen() = currentChill() >= currentHealth()` where `currentHealth()` returns `m_currentHealth` (health minus accumulated damage). AS3 formula uses `disruptDamage >= damageItCanTake + damage`. These LOOK different. Need formal proof for all 4 cases (fragile×damaged). | **Must-do: Require 4-case verification table.** |
| Negative testing strategy | R5,R8,R9,R10 | For each P0 area, construct a state where a bug WOULD manifest. This directly addresses the "extra legality" pattern of the known bug. | **Should-do: Add to methodology.** |
| cardLibrary.jso parsing parity | R3,R5,R9,R10 | Both engines parse the same JSON but through different code (CardTypeInfo.cpp vs Card.as). Missing/defaulted fields could diverge. | **Consider.** |
| Replay failure categorization | R4 | The 849 failures (USE_ABILITY 276, SNIPE 173, END_PHASE 130, BUY 116, BLOCKER 58) are already categorized. These show C++ being STRICTER than AS3 — a different bug class from the blocking bug (permissive). Still useful diagnostic data. | **Consider.** |

### Alternative Approaches

| Alternative | Reviewer(s) | Assessment |
|-------------|-------------|------------|
| "Trace the swoosh" as organizing principle | R1 | **Strong.** Aligns with the phase-boundary bug pattern. Incorporated into the reorganized P0. |
| Golden state test (complex F6 state) | R1 | **Good supplement.** One carefully crafted state exercising multiple mechanics is high-value low-effort. |
| F6 differential testing harness | R1,R4,R5 | **Good but limited.** F6 export is manual (clipboard). Semi-automated via sniffer, but can't drive AS3 programmatically. Useful for spot-checks, not systematic testing. |
| Focused replay failure analysis | R4,R7 | **Worth considering.** The 849 failures are pre-categorized diagnostic data. |
| Property-based invariant testing | R2,R5,R7 | **Medium value.** Catches C++ internal inconsistencies but not AS3 divergences. |
| State machine diagram | R3,R5 | **Should-do.** Text-based state machine diagram for both engines makes transition gaps immediately visible. |
| AS3-as-spec micro-spec extraction | R2 | **Good.** Extract explicit formulas from AS3 into markdown, then verify C++ against the spec. |

### Confirmed Good / Keep As-Is

| Element | Reviewer(s) |
|---------|-------------|
| Priority tiering (P0-P3) concept | All 10 |
| File mapping table | R1,R2,R3,R5,R6,R10 |
| Naming dictionary | R1,R2,R3,R5,R6,R7 |
| Known divergences table | R1,R3,R7,R10 |
| Scope boundaries (in/out) | R1,R2,R3,R5,R10 |
| Hybrid execution (Option D) | R1,R2,R3,R5,R6 |
| "How to Use This Plan" instructions | R6,R10 |
| Already-known divergences format | R1,R8 |

### Implementation Details & Nits

| Nit | Reviewer(s) | Action |
|-----|-------------|--------|
| Line numbers are fragile | R1,R2,R6,R8,R10 | Use function name + distinctive snippet + line range |
| Inconsistent table formats | R5,R10 | Standardize all tables with Risk column |
| "1 context" terminology unclear | R10 | Clarify as "1 Claude Code session" |
| cardLibrary.jso vs .json extension | R5,R10 | Standardize to .jso (correct) |
| Phase/function terminology mixing | R2 | Standardize to "transition boundary" language |
| "~2-4 hours" scattered estimates | R1,R2,R3,R4,R6,R7 | Remove or replace with per-area timeboxes |

---

## A.5 — Conflicts & Contradictions

### Conflict 1: Lifespan-1 Blocking Severity

**R1,R3,R8 say**: Lifespan-1 blocker exclusion is potentially P0-critical, "a second blocking bug hiding in plain sight."

**R6,R9 say**: It needs verification but may be an edge case.

**Codebase reality**: **Neither side is fully correct.** The AS3 `StateHelper.as` (lines 191, 385) excludes lifespan-1 units from "ownStuffAfterDefensePhase" — but this is the **analysis/evaluation helper**, NOT the actual game rule. The actual blocking logic in AS3 (`State.as:1451`, `inst.blocking = card.assignedBlocking`) has **no lifespan check**. The C++ `Card::canBlock()` (Card.cpp:484-512) also has no lifespan check. **Both engines correctly allow lifespan-1 units to block.** The plan's question was misleading.

However, the "all opponent units doomed" instant-win (`State.as:3298`, `helper.allOppUnitsDoomed`) IS real and missing from C++. This is the actual lifespan-1-related divergence.

**Recommendation**: Demote lifespan-1 BLOCKING to verified-match. Promote "all units doomed" instant-win to P0.

### Conflict 2: Stagnation Priority

**R3,R4,R7 say**: P0 (critical for training data).
**R1,R5,R6,R9 say**: P1 (high but not P0).

**Codebase reality**: C++ has `m_turnLimit = 200` (Game.h:17) which prevents infinite games. AS3 has 4-level stagnation with cutoffs [2,8,20,40]. These are different mechanisms but both prevent infinite games. The 200-turn limit means C++ games CAN run much longer than AS3 would allow in stagnation scenarios. The impact depends on how often self-play games approach stagnation.

**Recommendation**: P1 for stagnation counters (200-turn limit provides a safety net, but games may run longer than they should). P0 for "all units doomed" instant-win (confirmed missing, changes game outcomes).

### Conflict 3: Defense-Reset Fix Timing

**R7 says**: Fix should be Phase 0 (before audit).
**R10 says**: Audit should verify the fix.

**Codebase reality**: The bug is still present at GameState.cpp:1289-1307. The fix is straightforward (remove lines 1289-1307). The audit may find additional bugs that should be fixed together.

**Recommendation**: Document the fix in the audit. Apply fix in Phase 3 along with any other fixes found. Running the audit BEFORE fixing lets the auditor see the full picture of divergences.

### Conflict 4: Replay Failures as Audit Input

**R4 says**: Start with the 44.3% failures — they're quantifiable divergence data.
**Others**: Don't mention replay failures.

**Codebase reality**: The 849 failures represent C++ being **stricter** than AS3 (rejecting human moves). The blocking bug is C++ being **more permissive**. These are complementary diagnostic signals — the failures catch one bug class, the audit catches another.

**Recommendation**: Consider-tier. Reference the failure categories in the plan as supplementary data, but don't make it the primary methodology.

---

## A.6 — Recommended Plan Changes

### Must-Do (high consensus + high impact + validated by codebase)

| # | Change | Reviewers | Rationale |
|---|--------|-----------|-----------|
| M1 | **Promote B1 (Phase Transitions) to P0, execute FIRST** | R2,R3,R5,R7,R8,R9,R10 | All other P0 items depend on knowing phase boundaries match. The known bug IS a phase-boundary bug. |
| M2 | **Add "All Units Doomed" instant-win as P0 item** | R1,R3,R4,R7,R9 | Confirmed missing from C++ `calculateGameOver()`. Changes game termination. |
| M3 | **Add event timeline deliverable before P0 items** | R2,R7 | Side-by-side "what happens at each phase boundary" document catches ordering bugs — the exact class of the known bug. |
| M4 | **Add completion criteria per audit area** | R1,R2,R5,R6,R7,R10 | Define what "verified" means: traced all code paths, documented line pairs, produced test case. |
| M5 | **Require chill formula 4-case proof** | R1,R3,R5,R7,R8,R9 | Replace "might be equivalent" with mandatory (fragile/non-fragile) x (damaged/undamaged) verification table. |
| M6 | **Add comprehensive status reset scan to P0** | R10 | Search ALL `setStatus()` calls in C++ and all `inst.role =` in AS3. The known bug was ONE reset; there may be others. |
| M7 | **Remove fixed time estimates** | R1,R2,R3,R4,R6,R7,R8 | Replace "~2 hours" with per-area timeboxes or remove entirely. |
| M8 | **Defer P3 to future work** | R2,R5,R6,R7,R9,R10 | D1/D2/D3 are low-impact unit-specific edge cases. Focus on P0+P1. |
| M9 | **Condense Options A-C to one-liners** | R1,R2,R3,R6,R7,R10 | Only Option D matters. Rejected options create noise. |
| M10 | **Require concrete test cases per P0 area** | R2,R5,R7,R8,R10 | "Read and confirm" is insufficient. Each area needs at minimum 1 normal + 1 edge case. |

### Should-Do (strong suggestions, meaningfully improve the plan)

| # | Change | Reviewers | Rationale |
|---|--------|-----------|-----------|
| S1 | **Add script/trigger execution ordering as P1** | R1,R2,R3,R5,R6,R8,R9 | C++ runs beginOwnTurnScripts in second pass after all card beginTurns; AS3 intermixes in single swoosh pass. Genuine ordering difference. |
| S2 | **Promote sellable role to P1** | R1,R3,R5,R6,R7,R9,R10 | C++ `m_sellable` bool vs AS3 `role="sellable"` string. Transition timing needs verification. |
| S3 | **Add simultaneous death ordering to P1** | R2,R3,R8,R9 | Death triggers during breach/swoosh could differ in execution order. |
| S4 | **Promote stagnation counters to P1** | R1,R3,R4,R5,R6,R7,R9 | C++ has 200-turn limit but no progress-tracking stagnation system. Games may run longer than AS3 would allow. |
| S5 | **Add negative testing strategy** | R5,R8,R9,R10 | For each P0 area, construct a state where the bug pattern (extra legality) would manifest. |
| S6 | **Add state machine diagram deliverable** | R3,R5,R7 | Text-based diagram of both engines' phase transitions makes gaps immediately visible. |
| S7 | **Verify defense-reset fix correctness in Phase 3** | R7,R10 | Once fix is applied, verify it matches AS3 behavior exactly. |
| S8 | **Use stable references (function + snippet), not just line numbers** | R1,R2,R6,R8,R10 | Line numbers drift. Function names + distinctive code phrases are stable. |
| S9 | **Add severity rubric for findings** | R1 | CRITICAL (>5% games affected), HIGH (edge cases), MEDIUM (theoretical), LOW (cosmetic). |

### Consider (presented as pick list in updated plan)

| # | Change | Reviewers | Effort | Recommendation |
|---|--------|-----------|--------|----------------|
| C1 | Replay failure categorization as audit input | R4 | Small | Lean yes — free diagnostic data |
| C2 | F6 golden state test | R1,R5 | Medium | Lean yes — high value if crafted well |
| C3 | cardLibrary.jso parsing parity check | R3,R5,R9,R10 | Small | Lean yes — quick sanity check |
| C4 | Coverage tracking (functions verified per file) | R6 | Trivial | Neutral |
| C5 | Self-play impact estimator per finding | R6 | Trivial | Lean yes — helps prioritize fixes |
| C6 | Property-based invariant tests for C++ | R2,R5,R7 | Large | Lean no — high effort, doesn't prove AS3 equivalence |
| C7 | Legal action generation comparison | R4 | Medium | Lean yes — different bug class worth checking |
| C8 | Prompt unit handling as explicit check | R9 | Trivial | Lean no — handled implicitly by constructionTime=0 |
| C9 | Resource overflow/cap behavior | R3,R9 | Small | Neutral |

### Reject (with reason)

| # | Suggestion | Reviewer(s) | Reason for Rejection |
|---|-----------|-------------|---------------------|
| X1 | Defense-reset fix as Phase 0 prerequisite | R7 | Audit should document full divergence picture BEFORE fixes. Fixing first loses the ability to verify the bug exists where expected. |
| X2 | Energy system as dedicated audit area | R10 | Energy is reset in `beginTurn()` alongside Blue/Red/Attack (GameState.cpp:1220-1223). Same code pattern, same risk level. Not a special case. |
| X3 | Lifespan-1 blocking exclusion as standalone P0 | R1,R3,R8,R9 | **Invalidated by codebase.** AS3 StateHelper exclusion is for ANALYSIS/EVALUATION, not game rules. Actual AS3 blocking (`inst.blocking`) has no lifespan check. C++ `canBlock()` also has no lifespan check. Both engines correctly allow lifespan-1 units to block. The plan's question was misleading. |
| X4 | AST extraction script for coverage analysis | R6,R8 | Cross-language AST tooling (AS3↔C++) would require significant custom development. Simple grep provides 80% of the signal. |
| X5 | Remove "CAN read / CANNOT modify" instruction | R3 | It's 2 lines and prevents auditor mistakes. Keep it. |
| X6 | Undo system affects defense generation | R4 | C++ undo is by-design limited. AI search doesn't use undo. Not a divergence risk. |

---

## A.7 — What Stays

The following elements were confirmed good by multiple reviewers and validated by codebase inspection:

1. **Priority tiering concept (P0→P3)** — Correct risk model for training-data corruption
2. **File mapping table** — Accurate file sizes and correspondence confirmed
3. **Naming dictionary** — Critical for cross-referencing; `disruptDamage`↔`m_currentChill`, `glassBroken`↔`Phases::Breach`, etc.
4. **Known divergences table (#1-#4)** — Accurate and useful baseline
5. **Scope boundaries** — UI, undo, raid correctly excluded
6. **Hybrid execution strategy (Option D)** — Correct given AS3 runtime constraints
7. **A1 blocking chain audit structure** — The table format with AS3/C++ cross-references is the right granularity
8. **A2 chill/freeze as P0** — Confirmed different representations need verification
9. **A3 wipeout/breach as P0** — Architectural difference (glassBroken flag vs Phases::Breach) confirmed
10. **A4 fragile damage as P0** — Fragile handling confirmed to differ in representation
11. **"How to Use This Plan" section** — Practical and clear
12. **"CANNOT modify" constraint** — Prevents auditor from accidentally fixing bugs during audit
