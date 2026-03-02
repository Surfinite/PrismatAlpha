# Meta-Review: AS3 Faithful Port Implementation Plan

**Date:** February 23, 2026
**Plan reviewed:** `docs/plans/as3-faithful-port-implementation-plan.md`
**Reviews ingested:** 9
**Codebase validated:** Yes (full source access, all claims verified)

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Mixed-to-critical | API freeze violation (`isStagnated()` public), oracle baseline conceptually wrong, stagnation off-by-one, death script double-dispatch, phase ordering | API contract: new public methods violate the "zero signature changes" promise |
| R2 | Mostly positive, critical on execution | Phase ordering, feature match target unrealistic, "valley of despair" warning, centralize stagnation, death script queue | Valley-of-despair transition strategy — plan needs to allow temporary regressions |
| R3 | Mixed, correctness-focused | Oracle baseline conflation, beginTurn iteration semantics, death script taxonomy, ProgressEvent enum, phase ordering | Oracle serves TWO purposes: detecting regressions (vs old engine) AND measuring correctness (vs AS3 ground truth) — plan conflates these |
| R4 | Mostly positive, critical on ordering | Phase ordering, NN evaluation step needed, CardIDVector heap allocation, valley, cache miss profiling | Neural network evaluation step between Phase 5 and 6 — models trained on old engine features may destabilize |
| R5 | Positive on structure, critical on testing | State-hash differential oracle, isIsomorphic must include stagnation, serialization updates missing, UNDO_USE_ABILITY breakage, commit strategy | "Single highest-value addition": state-hash differential oracle comparing per-action state between engines |
| R6 | Positive infrastructure, critical on NN risk | Neural network destabilization CRITICAL, shadow mode / differential fuzzing, defer feature extraction to Phase 6, determinism contract | Elevated NN destabilization from footnote to critical risk — feature vectors WILL change, model must be retrained |
| R7 | Positive on safety, critical on Phase 5 | Phase 7 data regen plan, per-phase diffs, Phase 0.5 AS3 inventory, stagnation centralization, remove CUTOFFS array | Missing Phase 7: explicit data regeneration plan — the whole motivation is regenerating 722K games |
| R8 | Positive structure, concerned about overconfidence | Differential testing missing, feature flags alternative, CardData integrity validation, StateHelper-first alternative, effort estimate buffer | Feature flags vs big-bang port — wrap changes behind toggles for safer rollout |
| R9 | Positive on safety, critical on stagnation accuracy | Stagnation reset logic too crude, StateDiffValidator, staged swoosh alternative, "correcter but not accurate" | "Correcter but not accurate" framing — plan assumes faithfulness guarantees correctness, but decompiled AS3 may have its own bugs |

---

## A.2 — Consensus Points (agreement across 2+ reviewers)

Ranked by how many reviewers raised each point:

### 9/9: Phase Ordering — Swoosh Before Moves
**ALL** reviewers agree: Phase 4 (swoosh/beginTurn rewrite) should be done BEFORE Phase 3 (move processing). Rationale: swoosh is self-contained with clear AS3 mapping, provides immediate replay validation signal, and move processing depends on correct turn boundary state.

**Codebase validation:** CONFIRMED. The current C++ `beginTurn()` (GameState.cpp:1248-1309) is two-pass and directly comparable to AS3's single-pass `swoosh()` (State.as:2582-3045). This is indeed the cleanest port target.

### 9/9: Valley-of-Despair Transition Strategy
All reviewers agree the plan needs an explicit policy for temporary replay rate decreases during intermediate phases. The plan currently says "pass rate equal or better" after every phase, which is unrealistic when changing fundamental semantics.

**Codebase validation:** CONFIRMED. Changing ability cost timing (health/charge before script) and snipe kill timing (script before kill) will break replays that rely on the current (incorrect) order. These are the #1 failure category (USE_ABILITY at 40.7%).

### 9/9: Oracle Baseline Needs Splitting
The plan conflates two types of oracle testing: (1) regression detection against the OLD engine, (2) correctness measurement against AS3 ground truth. These serve different purposes and need separate baselines.

**Codebase validation:** CONFIRMED. The existing `fast_batch_validate.py` validates action legality only — it cannot detect state divergence (a replay can pass legality checks while producing wrong game states). Separate tools are needed.

### 9/9: Stagnation System Centralization
All reviewers want stagnation event tracking centralized rather than scattered across 12+ call sites. Most suggest an enum-based `reportProgressEvent()` API.

**Codebase validation:** STRONGLY CONFIRMED. Reading AS3 State.as:1895-1954 reveals that stagnation is MORE complex than the plan describes:
- THREE distinct reset functions: `resetTurnNoProgressCounters(level)`, `resetOppNoProgressCounters(level)`, `resetColorNoProgressCounters(color, level)` — the plan only has ONE (`resetStagnation(player, level)`)
- The MOVE_ENTER_CONFIRM logic is a complex if-else chain (NOT independent event checks) that depends on StateHelper computed properties (`oppDefense`, `maxOppDefenderHealth`, `partiallyDamagedInst`, `totalProducedThisTurn`)
- Gas storage checks are unit-specific (Cluster Bolt, Gauss Charge, Zemora, Gaussite Symbiote)

### 8/9: State-Level Differential Testing
Nearly all reviewers want per-action state comparison between old and new engines, not just replay pass/fail.

**Codebase validation:** CONFIRMED. `isIsomorphic()` (GameState.cpp:2173-2238) exists and performs order-independent semantic state equality. `getStateString()` (line 2107) is too sparse (only buyable names + card name + health). `toJSONString()` (line 2336) provides richer state output. A state-hash differential tool is feasible using existing infrastructure.

### 7/9: Spell/Mana Rot Should Be Deferred
Most reviewers agree Phase 5 (spell collection, mana rot) is under-specified and should wait until core port is validated.

**Codebase validation:** CONFIRMED. 8 units in cardLibrary.jso have `"spell": 1`. These are real game-relevant units but affect a small fraction of games. Deferring is safe.

### 5/9: isStagnated() Public Violates API Freeze
R1, R3, R5, R7, R8 note that adding `isStagnated()` as a new public method contradicts the "zero signature changes" guarantee.

**Codebase validation:** CONFIRMED. No such method exists in GameState.h. The plan's own Phase 0 anti-pattern guard #1 says "NEVER change public method signatures." Adding a new public method isn't changing a signature, but it does expand the API surface. Make it private or use `calculateGameOver()` internally.

### 5/9: Death Script Single-Dispatch
R1, R2, R3, R6, R7 argue death scripts should be dispatched from `killCardByID()` (single site) not from each caller (breach, wipeout separately).

**Codebase validation:** CONFIRMED valid concern, but **practically moot**: grep of cardLibrary.jso shows ZERO cards with `deathScript`. The infrastructure should still be correct for future-proofing, and single-dispatch is cleaner.

### 4/9: Neural Network Destabilization Risk
R4, R5, R6, R8 warn that changing engine internals will change feature vectors, destabilizing the neural net. R6 elevates this to CRITICAL.

**Codebase validation:** CONFIRMED. Feature extraction reads from GameState via `getResources()`, `getCardByID()` (status, health, chill). Changes to ability cost timing, swoosh order, and status reset WILL produce different intermediate states. The 305K-game model (51.9% WR) will need retraining. However, ALL 722K games need regeneration anyway (defense reset bug), so retraining was already planned.

### 3/9: UNDO_USE_ABILITY Breakage Risk
R5, R8, R9 note that changing ability cost timing may break the undo path.

**Codebase validation:** CONFIRMED. `UNDO_USE_ABILITY` is a live code path (GameState.cpp:747-793) that uses `runScriptUndo()`. If ability costs are deducted in `doAction(USE_ABILITY)` instead of `Card::useAbility()`, the undo must mirror this change. The plan doesn't mention updating the undo path.

---

## A.3 — Outlier Points (raised by only one reviewer)

| Point | Reviewer | Merit Assessment |
|---|---|---|
| Phase 0.5: AS3 code inventory with line-by-line mapping | R7 | **HIGH MERIT** — Forces the implementer to read ALL relevant AS3 before writing C++. Prevents "translate as you go" mistakes. |
| Feature flags vs big-bang port | R8 | **MEDIUM MERIT** — Theoretically safer but doubles code paths during port. The git-based rollback is simpler for a solo developer. |
| "Correcter but not accurate" — AS3 may have bugs | R9 | **HIGH MERIT** — Important philosophical framing. AS3 IS the ground truth for replay compatibility, even if it has quirks. The plan should acknowledge this. |
| Staged swoosh (run both passes, compare) | R9 | **LOW MERIT** — Adds complexity for temporary validation. The differential oracle achieves the same goal. |
| StateHelper-first alternative approach | R8 | **LOW MERIT** — StateHelper is a cache layer, not core logic. Porting it first provides less validation signal than swoosh-first. |
| CardData integrity validation post-port | R8 | **MEDIUM MERIT** — Worth adding as a debug assertion (card count consistency, no orphans) but not a separate task. |
| Cache miss profiling | R4 | **LOW MERIT** — Premature optimization. Profile only if >10% regression materializes. |
| Effort estimate needs 50% buffer | R8 | **HIGH MERIT** — Plan says 7-12 sessions. With swoosh complexity, stagnation's 3-function design, and StateHelper dependencies, 10-18 sessions is more realistic. |

---

## A.4 — Category Breakdown

### Architecture & Design

| Item | Reviewer(s) | Codebase Validation | Analysis |
|---|---|---|---|
| Single-pass swoosh | All (9/9) | CONFIRMED: AS3 swoosh (State.as:2614-2770) is single-pass per-card. C++ (GameState.cpp:1276-1306) is two-pass. | **Must-do.** Already in plan as Decision 2.1. No change needed to the decision, only to phase ordering. |
| Stagnation centralization (ProgressEvent enum) | R1-R9 (9/9) | STRONGLY CONFIRMED: AS3 has THREE reset functions (turn/opp/color), not one. MOVE_ENTER_CONFIRM has complex if-else chain with StateHelper deps. | **Must-do.** The plan's single `resetStagnation(player, level)` is insufficient. Need 3 variants matching AS3. |
| Death script dispatch from killCardByID | R1,R2,R3,R6,R7 (5/9) | CONFIRMED: No cards have deathScript. Infrastructure still needed. Single dispatch site is cleaner. | **Should-do.** Move death script execution into `killCardByID()` with a CauseOfDeath parameter check. |
| Phase architecture (keep 5-phase) | Plan + R2,R7 | CONFIRMED: C++ 5-phase is compatible with AS3 3-phase + glassBroken. | **Stays.** Decision 2.7 is correct. |
| isStagnated() as private, not public | R1,R3,R5,R7,R8 (5/9) | CONFIRMED: No existing public method. Adding one expands API surface. | **Must-do.** Make it private or check inline in `calculateGameOver()`. |

### Risks & Concerns

| Item | Reviewer(s) | Codebase Validation | Analysis |
|---|---|---|---|
| Neural network destabilization | R4,R5,R6,R8 (4/9) | CONFIRMED: Feature vectors will change. Model needs retraining. | **Must-do** to acknowledge in plan. Not blocking — retraining already planned due to defense bug. |
| UNDO_USE_ABILITY breakage | R5,R8,R9 (3/9) | CONFIRMED: Live code path at line 747. Uses runScriptUndo. | **Must-do.** Add explicit undo path update task to Phase 3. |
| Valley of despair — replay rate may decrease | All (9/9) | CONFIRMED: USE_ABILITY timing change will break replays that relied on wrong order. | **Must-do.** Add valley-allowed policy with regression-vs-AS3 categorization. |
| Effort underestimate | R8, implied by R7,R9 | CONFIRMED: Stagnation's 3 reset functions + StateHelper deps add significant scope. | **Should-do.** Update estimate to 10-18 sessions. |
| Decompiled AS3 may not be fully accurate | R9 | VALID concern but mitigated — replay compatibility IS the acceptance test. | **Consider.** Add a note acknowledging AS3 is ground truth for replays, not necessarily "correct" in abstract. |

### Suggested Removals / Simplifications

| Item | Reviewer(s) | Codebase Validation | Analysis |
|---|---|---|---|
| Remove CUTOFFS array from Constants.h | R7 | AS3 has `CUTOFFS_FOR_DRAW = [2, 8, 20, 40]` as a constant. | **Reject.** The array is directly from AS3 and makes the stagnation check readable. |
| Defer spell/mana rot to later phase | R2,R3,R5,R7,R8,R9 (6/9) | CONFIRMED: 8 spell units exist but affect few games. | **Should-do.** Move to Phase 5 "optional" or defer entirely. |
| Defer feature extraction snapshot to Phase 6 | R6 | VALID: Feature vectors WILL change; testing them early creates noise. | **Should-do.** Feature snapshot comparison is only meaningful after all changes. |

### Suggested Additions / Features

| Item | Reviewer(s) | Codebase Validation | Analysis |
|---|---|---|---|
| State-hash differential oracle (Task 1.6) | R3,R5,R6,R7,R8 (5/9) | FEASIBLE: `isIsomorphic()` exists but needs stagnation. `toJSONString()` available for state dumps. | **Must-do.** Highest-value addition per R5. Add as Task 1.6. |
| Per-phase diff reports (what changed) | R7 | FEASIBLE: Git diffs + replay oracle re-run at each phase boundary. | **Should-do.** Formalize as phase gate process. |
| Phase 7: Data Regeneration Plan | R7 | VALID: The whole motivation is regenerating 722K games. Plan stops at validation. | **Must-do.** Add Phase 7 outline covering regeneration strategy. |
| Update isIsomorphic() for stagnation counters | R5 | CONFIRMED: Current isIsomorphic (GameState.cpp:2173-2238) does NOT compare stagnation. | **Must-do.** Required for transposition table correctness. |
| Update serialization (toJSONString, getStateString) | R5,R6 | CONFIRMED: getStateString is sparse (name+health only). toJSONString is richer. | **Should-do.** Add task to update both for new fields (stagnation counters). |
| Phase 0.5: AS3 code inventory | R7 | VALID: Reading all AS3 before writing prevents translation errors. | **Consider.** Useful but may be too rigid as a formal phase. |
| Commit strategy (per-move-type commits) | R5 | VALID: Fine-grained commits aid bisection if something breaks. | **Should-do.** Add commit discipline guidance. |
| Debug assertion: card count consistency | R8 | FEASIBLE: PRISMATA_ASSERT already exists. | **Consider.** Add lightweight assertions, not a separate task. |

### Confirmed Good / Keep As-Is

| Item | Reviewer(s) | Notes |
|---|---|---|
| 56-method API preservation contract | R1,R3,R5,R7,R8 (5/9) | Core strength of the plan. Clear boundary. |
| 4 oracle validation strategy | R2,R5,R7 (3/9) | Strong safety net approach. |
| Git baseline + tag + pre-port binary | All (9/9) | Unanimous approval. |
| Anti-pattern guards (no UI, no undo, no campaign) | R3,R5,R7 (3/9) | Clear scope boundaries. |
| Decision 2.7: Keep 5-phase architecture | R2,R7 (2/9) | Pragmatic — compatible with AS3 semantics. |
| Naming dictionary (Appendix A) | R1,R3 (2/9) | Valuable reference for implementer. |
| Phase 6 tournament smoke test | R4,R5 (2/9) | Important integration test. |

### Implementation Details & Nits

| Item | Reviewer(s) | Analysis |
|---|---|---|
| CardIDVector copy in beginTurn is heap allocation | R4 | **Valid.** `std::vector<CardID>` copy allocates. Use `reserve()` or stack buffer for small card counts. Not blocking but worth noting. |
| Stagnation level indices are 1-based in AS3 | R1 | **Confirmed.** Levels are 1,2,3,4 in AS3 (LEVEL_DELAY_TICKED=1, etc.). C++ uses array[0..3]. Plan's mapping is correct — `resetStagnation(p, level)` resets indices `0..level-1`. |
| Snapshot iteration uses `getCardIDs()` copy | R4 | **Already done.** C++ beginTurn (line 1262-1267) already copies the card ID vector. AS3 swoosh (line 2613) also copies `copyOfInstIds`. |

### Dependencies & Integration

| Item | Reviewer(s) | Analysis |
|---|---|---|
| StateHelper computed properties needed for stagnation | R9 | **CONFIRMED.** AS3 MOVE_ENTER_CONFIRM stagnation logic needs `oppDefense`, `maxOppDefenderHealth`, `partiallyDamagedInst`, `totalProducedThisTurn`. These don't exist in C++. Must either port StateHelper or compute inline. |
| Stagnation depends on StateHelper which depends on port | R8,R9 | **Valid circular dependency.** Solution: port stagnation incrementally — do counter storage and simple events first, complex ENTER_CONFIRM events (requiring StateHelper) last. |

### Future Considerations

| Item | Reviewer(s) | Analysis |
|---|---|---|
| NN evaluation gate between port and data regen | R4,R6 | **Must-do (as Phase 7 item).** Feature extraction will change. Verify NN can still evaluate states before regenerating 722K games. |
| Replay compatibility as ongoing regression test | R3,R7 | **Good practice.** Make replay oracle a CI check. |
| StateHelper port for advanced stagnation + future features | R8,R9 | **Future.** Not required for initial port if complex stagnation events are deferred. |

---

## A.5 — Conflicts & Contradictions

### Conflict 1: Phase Ordering — Move Processing vs Swoosh First
- **Plan:** Phase 3 (moves) → Phase 4 (swoosh)
- **All 9 reviewers:** Phase 4 (swoosh) → Phase 3 (moves)
- **Recommendation:** Reviewers are correct. Swoosh is self-contained, has clear AS3 mapping, provides immediate replay validation signal. Move processing depends on correct turn boundary state.

### Conflict 2: Feature Extraction Timing
- **Plan + R4:** Feature snapshot in Phase 1, compare in Phase 6
- **R6:** Defer feature snapshot to Phase 6 entirely — intermediate comparisons produce noise
- **R3,R5:** Keep Phase 1 baseline for regression detection
- **Recommendation:** Keep Phase 1 baseline capture but note it as a REGRESSION DETECTOR (against old engine), not a CORRECTNESS measure. Feature comparison is only meaningful in Phase 6 against the SAME positions re-evaluated.

### Conflict 3: Feature Flags vs Big-Bang Port
- **R8:** Feature flags for safer rollout
- **R5,R7:** Git-based rollback is simpler
- **Recommendation:** Git-based rollback is sufficient for a solo developer. Feature flags double complexity for marginal safety. Use per-move-type commits for bisection instead.

### Conflict 4: Stagnation Complexity — Simple vs Faithful
- **Plan:** Simple `resetStagnation(player, level)` at 12 call sites
- **R9:** Crude approach risks inaccuracy
- **Codebase evidence:** AS3 has 3 reset functions + complex if-else chain + StateHelper deps
- **Recommendation:** Phase the stagnation port: (1) counter storage + increment + simple cutoff check in Phase 2, (2) simple events (buildtime, delay, lifespan, charge, buy) in swoosh/move port phases, (3) complex ENTER_CONFIRM events (requiring StateHelper) as a separate task. This avoids blocking the core port on StateHelper.

### Conflict 5: isStagnated() Visibility
- **Plan:** Public method
- **R1,R3,R5,R7,R8:** Should be private
- **Recommendation:** Make the stagnation check private (inline in `calculateGameOver()`). If external access is needed later, add a public getter — expanding API is always possible, contracting it is not.

---

## A.6 — Recommended Plan Changes

### Must-Do (High consensus, high impact, or real risk)

1. **Swap Phase 3 and Phase 4** — Do swoosh/beginTurn rewrite BEFORE move processing. (9/9 reviewers)

2. **Split oracle into regression + ground-truth baselines** — Phase 1 captures the OLD engine's behavior (for regression detection). Phase 6 compares against AS3 ground truth (for correctness). Remove "pass rate equal or better" from intermediate phases; replace with "zero unexplained NEW regressions." (9/9)

3. **Add Task 1.6: State-Hash Differential Oracle** — Run replays through both old and new engines, compare per-action state via `isIsomorphic()` or JSON diff. This catches state divergence that replay-pass/fail misses. (8/9)

4. **Expand stagnation to 3 reset functions** matching AS3 (`resetTurnProgress`, `resetOppProgress`, `resetColorProgress`). Phase the complex ENTER_CONFIRM events (which need StateHelper) separately from simple events. Centralize behind a `ProgressEvent` enum. (9/9)

5. **Make isStagnated() private** — Check stagnation inline in `calculateGameOver()`. (5/9)

6. **Add UNDO_USE_ABILITY update task** to Phase 3 — If ability cost timing changes, the undo path must mirror it. (3/9, confirmed by codebase)

7. **Add Phase 7: Data Regeneration outline** — Self-play regeneration strategy, NN retraining gate, deployment plan. (R7, supported by R4, R6)

8. **Update isIsomorphic() for stagnation counters** — Transposition table correctness requires comparing stagnation state. (R5, confirmed by codebase)

9. **Allow valley-of-despair** — Replace "pass rate ≥ baseline" with "categorize regressions: if new failures are AS3-correct, they are expected; only AS3-incorrect regressions are blockers." (9/9)

### Should-Do (Strong suggestions, meaningful improvement)

10. **Move death script dispatch into killCardByID()** with CauseOfDeath check — Single dispatch site, cleaner than per-caller. (5/9)

11. **Defer feature extraction comparison to Phase 6** — Intermediate feature comparisons produce noise when internals are changing. Keep Phase 1 baseline capture. (R6, supported by R3)

12. **Defer spell/mana rot** — Move to optional Phase 5 or defer entirely. Low impact on replay rate. (6/9)

13. **Add commit discipline** — One commit per move type in Phase 3, one commit per swoosh sub-system in Phase 4. Enables git bisect. (R5)

14. **Update serialization methods** — `toJSONString()` and `getStateString()` must include new fields (stagnation counters). (R5, R6)

15. **Increase effort estimate** — 10-18 sessions (from 7-12). Stagnation's 3-function design, StateHelper dependencies, and undo path updates add significant scope. (R8)

16. **Add per-phase diff reports** — At each phase boundary: git diff stats, replay oracle delta, categorized new failures. (R7)

### Consider (presented as pick list in v2 plan)

17. Phase 0.5: AS3 code inventory with line-by-line mapping before coding starts (R7)
18. Feature flags for incremental rollout (R8)
19. CardData integrity assertions (card count consistency, no orphans) (R8)
20. "Correcter but not accurate" acknowledgment — AS3 is ground truth for replays, not necessarily "correct" in abstract (R9)
21. Cache miss profiling infrastructure for performance phase (R4)
22. Staged swoosh — run both passes and compare before switching to single-pass (R9)
23. Debug state hash (cheap hash for state comparison, lighter than isIsomorphic) (R5)
24. Determinism contract — document which operations are order-dependent (R6)

### Reject (with reason)

25. **Remove CUTOFFS array** (R7) — The array is directly from AS3 (`CUTOFFS_FOR_DRAW = [2, 8, 20, 40]`). Readable and faithful. No reason to remove.

26. **StateHelper-first approach** (R8) — StateHelper is a cache/computed-property layer. Porting it first provides less validation signal than swoosh-first. Can be added incrementally as stagnation needs it.

---

## A.7 — What Stays

The following aspects of the plan were confirmed good by multiple reviewers and should remain unchanged:

1. **56-method public API preservation contract** — Core architectural decision. Clear boundary between engine internals and AI/testing consumers.

2. **4-oracle validation strategy** (replay, feature, legality, performance) — Strong safety net. Enhanced by Must-do additions (state-hash differential, split baselines).

3. **Git baseline + tag + pre-port binary** — Unanimous approval. Clean rollback path.

4. **Anti-pattern guards** — No UI, no undo ports, no campaign, no lane system. Correct scope boundaries.

5. **Decision 2.7: Keep 5-phase architecture** — Pragmatic choice. C++ phases are compatible with AS3 semantics.

6. **Decision 2.1: Single-pass swoosh** — Unanimous agreement this is correct.

7. **Decision 2.5: Ability cost before script** — Matches AS3 ground truth. Audit finding B3.

8. **Decision 2.6: Snipe script before kill** — Matches AS3 ground truth. Audit finding B4.

9. **AS3→C++ naming dictionary (Appendix A)** — Valuable implementer reference.

10. **Rollback strategy** — Git-based, with per-phase commits and pre-port binary. Sufficient for solo developer.

11. **Tournament smoke test in Phase 6** — Essential integration test.

12. **Resonator processing** (Decision 2.4) — Already parsed in CardTypeInfo.cpp. Port is straightforward.
