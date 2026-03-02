# Meta-Review: Clean Room Rebuild Plan

**Date:** 2026-03-02
**Reviews analyzed:** 8 external reviewers (no codebase access)
**Codebase validation:** Full access — claims verified against actual code

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|----------|-----------|-----------------|----------------|
| R1 | Constructively critical | Shift-click gap, Phase 2 scope, Card.h instId tension | Card type+index output alternative for DoSuggest |
| R2 | Technically deep, rigorous | Click contract spec, 3-layer Phase 2 split, ban shift in C++ output | Long-lived subprocess protocol; PRISMATA_ASSERT silent corruption risk |
| R3 | Practical, focused | Shift-click, Phase 2, color-symmetry testing | C++ ClickTranslator class; WASM compilation long-term; dead code purge phase |
| R4 | Methodical | Phase 7 underspecified, supply verification, rollback | Phase 0.5 baseline verification; test-first for Phase 7 |
| R5 | Strongest language | Phase 2 "train wreck", Phase 7 "handwave", MCDSAI pin in-repo | Strangler fig pattern; feature flags; comparison harness (old vs new) |
| R6 | Pragmatic | Pre-flight script, fix existing matchup surgically, NeuralNet for AB only | Fix matchup_main.js instead of rewrite (contrarian) |
| R7 | Sharp-eyed, scope-focused | SkipColorSwap scope creep, S3 replay dependency, DoSuggest format ambiguity | playersHaveSameConfig violates minimal-footprint; rootDiagnostics is dead code |
| R8 | Comprehensive, methodical | Integration testing gap, NeuralUCTSearch subclass, PID seeding | Structured JSON logging; matchup configuration file; documentation session |

---

## A.2 — Consensus Points

### Unanimous (8/8)

**1. Shift-click expansion gap is critical**
All reviewers flagged this as the #1 issue.

**CODEBASE REALITY CHECK: This concern is LARGELY INVALID.**

The current DoSuggest in Benchmarks.cpp (lines 993-1016) **already expands shift-clicks into individual `inst clicked` entries**. When the AI generates a shift-flagged action (e.g., "activate all Drones"), DoSuggest iterates all cards of that type and emits one `{"_type":"inst clicked","_id":<instId>}` per matching instance. No "shift" flag appears in the JSON output.

Additionally, the JS engine at 99d39fe **natively supports shift-clicks** via `CLICK_INST_SHIFT` and `CLICK_CARD_SHIFT` constants in C.js, with full expansion logic in Controller.recordClick().

**The real issue:** The plan says "Remove shift-click expansion code (the buggy part)" — this instruction would INTRODUCE the gap reviewers flagged. The expansion code in DoSuggest is correct; the bugs were in `suggest_adapter.js` (the JS-side translation layer being discarded in the rewrite). **Recommendation: KEEP the C++ expansion code; don't remove it.**

**2. Phase 2 is overloaded and needs splitting**
All reviewers flagged this.

**CODEBASE REALITY CHECK: VALID, but less severe than reviewers feared.** `traverse()` has only 2 call sites, both internal to UCTSearch.cpp. No external files call it. All UCT additions (`_policyPrior`, `_usePUCT`, `computeRootPriors()`) are self-contained. The "cascading API breakage" concern is overstated. However, splitting is still correct practice — it enables bisection and incremental confidence.

**3. MCDSAI availability risk**
All reviewers flagged this.

**CODEBASE REALITY CHECK: VALID but manageable.** The existing binary at `tmp_browser_client/MCDSAI3441.js` is on disk with a SHA256 hash pinned in `mcdsai_wrapper.js`. The "download fresh" instruction adds risk for no benefit unless the binary is suspected corrupted. **Recommendation: Use existing binary as primary; fresh download as optional validation.**

### Strong Consensus (5-7 reviewers)

**4. Phase 7 needs more specification (7/8)**
VALID. Phase 7 describes intent but not interface contracts, error handling, or data formats.

**5. Explicit JSON/click schema needed (7/8)**
VALID. The C++↔JS interface is the critical integration seam.

**6. Supply verification in Phase 7 (6/8)**
VALID. The headline bug (supply=20) that triggered the rebuild has no programmatic regression test.

**7. PlatformToolset — pick one (6/8)**
VALID. Local environment has VS 2025 (v145). CI uses VS 2022 (v143). Plan should specify v145 with v143 CI note.

**8. No rollback/checkpoint strategy (5/8)**
VALID. Git tags after each phase cost nothing and enable bisection.

**9. CardLibrary scripted verification (5/8)**
VALID. Manual screenshot comparison for 105+ units is error-prone.

**10. CardLibrary diff for modified units (5/8)**
VALID. Origin/master has 78 UINames. Plan needs a rule for units that exist upstream but may differ from the live game.

### Moderate Consensus (3-4 reviewers)

**11. Defer rootDiagnostics (3/8)**
**CODEBASE CONFIRMS: Dead code.** Written in UCTSearch.cpp but never read by any consumer. Safe to remove.

**12. Defer LiveHardestAI opening books from Phase 2 (3/8)**
PARTIALLY VALID. Opening books are configuration, not algorithmic changes. They can be added in a separate config-only commit.

**13. Remove .github/ from Phase 1 copy (3/8)**
**CODEBASE CONFIRMS: .github/ does NOT exist on origin/master.** The copy command would fail. Must be brought from master explicitly.

---

## A.3 — Outlier Points

| Point | Reviewer | Merit Assessment |
|-------|----------|-----------------|
| SkipColorSwap is unexplained scope creep | R7 | **Has merit.** `playersHaveSameConfig()` is optional — explicit `"SkipColorSwap":true` in config.txt works without it. However, auto-detection is a convenience. Document purpose and keep. |
| S3 dependency for replay validation | R7 | **Minor.** S3 bucket is public and stable. Not worth committing 500 replays locally. |
| DoSuggest input format ambiguity (F6 vs bare) | R7 | **Valid.** DoSuggest handles both, but plan should specify which format matchup_v2.js writes. |
| Fix existing matchup_main.js surgically | R6 | **Rejected.** Contradicts the entire rebuild rationale. The accumulated bugs are WHY we're rebuilding. |
| NeuralUCTSearch subclass | R8 | **Rejected.** UCT changes are deeply embedded (traverse return type, PUCT formula in UCTNodeSelect). Subclassing would require duplicating most of UCTSearch. |
| WASM compilation of C++ engine | R3 | **Future consideration only.** Major engineering effort, not relevant to baseline rebuild. |
| CSPRNG instead of PID seeding | R8 | **Rejected.** PID seeding is adequate for AI search (not cryptographic). Matches existing codebase convention. |
| PRISMATA_ASSERT silent corruption | R2 | **Acknowledged but not actionable.** Changing assert behavior is out of scope — it's Churchill's convention used throughout. |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewers | Codebase Check | Assessment |
|----------|-----------|----------------|------------|
| "C++ = brain, JS = truth" is correct | All 8 | N/A | **Confirmed good. Keep.** |
| Long-lived subprocess vs CLI per-turn | R2, R7 | Current design spawns exe per turn | **Defer.** CLI is simpler for baseline. Subprocess is a Phase 7e optimization. |
| Click protocol specification document | R2, R5, R7 | No formal spec exists | **Must-do.** Write `docs/suggest_protocol.md` before Phase 7. |
| NeuralUCTSearch subclass | R8 | UCT changes are deeply interleaved | **Reject.** Would require duplicating ~400 lines of UCTSearch. |
| Keep shift-click expansion in C++ | R3, R6 | Code at Benchmarks.cpp:993-1016 is correct | **Must-do.** Reverses plan's "remove expansion" instruction. |

### ⚠️ Risks & Concerns

| Feedback | Reviewers | Codebase Check | Assessment |
|----------|-----------|----------------|------------|
| Phase 2 blast radius | All 8 | traverse() self-contained (2 internal call sites) | **Must-do: Split.** Less severe than feared but still correct practice. |
| Phase 7 underspecified | 7/8 | Plan has 5 sub-phases but no interface contracts | **Must-do: Add error handling, format specs.** |
| MCDSAI binary fragility | All 8 | Binary on disk, hash pinned in code | **Should-do: Invert primary/fallback.** |
| x86 memory pressure | R2, R5, R8 | 4GB limit, neural weights + MCDSAI workers | **Consider.** Add memory check to Phase 2 verification. |
| Card.h instId modifies core engine | R1 | instId is a single int field, read-only in game logic | **Acceptable.** DoSuggest needs instIds for click _id mapping. No engine behavior change. |

### 🗑️ Suggested Removals

| Feedback | Reviewers | Codebase Check | Assessment |
|----------|-----------|----------------|------------|
| Remove rootDiagnostics | R4, R5, R7 | Written but never read. Dead code. | **Should-do.** Remove from Phase 2. |
| Remove .github/ from Phase 1 copy | R5, R7, R8 | Does NOT exist on origin/master | **Must-do.** Command would fail. Copy from master explicitly. |
| Remove debugStateHash mention in Phase 3 | R5, R7, R8 | Excluded by plan, but step 6 still discusses it | **Must-do.** Delete the crossed-out step entirely. |
| Defer LiveHardestAI opening books | R4, R5 | Config-only, no code impact | **Should-do.** Separate commit from search changes. |
| Remove "download fresh MCDSAI" as primary | R5, R7 | Existing binary verified and hash-pinned | **Should-do.** |

### ➕ Suggested Additions

| Feedback | Reviewers | Assessment |
|----------|-----------|------------|
| Supply regression test in Phase 7 | R2, R3, R4, R5, R6, R8 | **Must-do.** Assert supply values at game init. |
| Git tags per phase | R4, R5, R6, R8 | **Must-do.** Zero cost, enables rollback. |
| Click protocol spec document | R2, R5, R7 | **Must-do.** Before Phase 7. |
| CardLibrary validation script | R1, R2, R6, R7, R8 | **Should-do.** Check required fields, token refs, duplicates. |
| Phase 7 error handling spec | R4, R5, R6, R8 | **Should-do.** AI crash, timeout, stuck detection. |
| Color-symmetry testing in Phase 7d | R3, R4 | **Should-do.** Test MCDSAI as both P0 and P1. |
| Neural weight validation (known input→output) | R5, R7, R8 | **Consider.** Verify eval returns plausible values for known state. |
| Performance/memory baseline | R2, R5, R8 | **Consider.** Log memory after each phase. |
| Phase 0.5 baseline tournament | R4 | **Consider.** Run origin/master tournament before modifications. |
| Structured JSON logging for matchups | R5, R8 | **Consider.** Valuable for debugging but adds scope. |

### 🔄 Alternative Approaches

| Alternative | Reviewers | Assessment |
|-------------|-----------|------------|
| Fix matchup_main.js surgically | R6 | **Reject.** Contradicts rebuild rationale. |
| Strangler fig pattern | R5 | **Reject.** Overkill for single-developer project. |
| Feature flags for excluded features | R5 | **Reject.** Unnecessary complexity. |
| C++ vs C++ matchups before MCDSAI | R1, R2 | **Already in plan.** Sub-phase 7b uses --suggest for both players. MCDSAI only added in 7d. |
| Parse card data from SWF/Steam install | R7, R8 | **Consider.** JPEXS already extracted AI params; card data may be available too. |
| matchup_clean.js naming | R7 | **Adopt.** Better than matchup_v2.js during transition. |

### ✅ Confirmed Good / Keep As-Is

All 8 reviewers confirmed these elements are solid:
- "C++ = AI brain, JS = game truth" principle
- Starting from known-good baselines (origin/master + 99d39fe)
- "What We're NOT Bringing Back" exclusion table
- Anti-pattern lists in each phase
- Phase 7 incremental sub-phasing (7a→7e)
- Key learnings from previous bugs in Phase 7
- Per-phase verification checklists
- Supply bug root-cause documentation

---

## A.5 — Conflicts & Contradictions

### Shift-click: Keep in C++ vs move to JS vs ban entirely

- **R1**: Keep expansion in JS (Card type+index output)
- **R2**: Ban shift semantics in C++ output entirely
- **R3**: Keep in C++ but rewrite as clean ClickTranslator class
- **R6**: Keep in C++ as-is

**Resolution (codebase-informed):** The C++ expansion code at Benchmarks.cpp:993-1016 is correct and working. It iterates cards of the same type and emits individual `inst clicked` entries — exactly what the JS engine expects. The bugs were in `suggest_adapter.js` (being discarded). **Keep the C++ expansion code as-is.** This is the simplest path: JS receives individual clicks and applies them sequentially. No new protocol, no new module, no gap.

### Fix existing matchup vs rewrite from scratch

- **R6**: Fix matchup_main.js surgically — rewrite risks reintroducing fixed bugs
- **All others**: Rewrite is correct

**Resolution:** The accumulated bugs (supply=20, color deadlocks, undefined property crashes) are layered across multiple files with unknown interactions. Surgical fixes have been tried and failed — that's what triggered this rebuild. The validated working parts (MCDSAI control-char stripping, click type constants) are in modules being copied from 99d39fe, not in matchup_main.js. **Rewrite is correct.**

### deepClone: Keep vs defer

- **R4, R5**: Defer deepClone() to Phase 7e (parallel workers)
- **Codebase**: deepClone() is called by Player clone() for EVERY tournament thread

**Resolution:** **deepClone is CRITICAL and must stay in Phase 2.** Without it, multi-threaded tournaments have race conditions on shared MoveIterator/Player objects. The default tournament config uses 4 threads. Deferring it would cause immediate crashes.

---

## A.6 — Recommended Plan Changes

### Must-do (high consensus + high impact)

1. **KEEP shift-click expansion in DoSuggest** — reverse the plan's "remove expansion" instruction. The code is correct. (All 8 reviewers flagged the gap this removal would create)

2. **Split Phase 2 into 3 sub-phases** with separate commits:
   - 2a: NeuralNet files + Constants.h enum + Eval.h/cpp + AB/SAB cases
   - 2b: UCT changes (traverse, PUCT, priors, node members, parameters)
   - 2c: AIParameters parsing + config.txt + Player deepClone
   (8/8 reviewers)

3. **Remove .github/ from Phase 1 copy** — it doesn't exist on origin/master. Copy from master explicitly as a separate step. (Confirmed by codebase)

4. **Delete Phase 3 Step 6** (debugStateHash crossed-out item) — confusing to include something you're NOT doing. (R5, R7, R8)

5. **Add supply regression test** in Phase 7a — `assert(getSupply(legendaryCard) === 1)` before any game logic runs. (6/8 reviewers)

6. **Add git tags after each phase** — `git tag phase-N-complete` for rollback/bisection. (5/8 reviewers)

7. **Fix PlatformToolset** — specify v145 (VS 2025, local) with note that CI uses v143. Remove ambiguity. (6/8 reviewers)

8. **Add click protocol specification** — write `docs/suggest_protocol.md` documenting --suggest input/output JSON schemas before Phase 7. (7/8 reviewers)

### Should-do (strong suggestions)

9. **Invert MCDSAI primary/fallback** — use existing on-disk binary as primary, fresh download as optional validation. (8/8 reviewers)

10. **Remove rootDiagnostics** from Phase 2 — confirmed dead code, never read. (3/8 reviewers + codebase confirmation)

11. **Separate config.txt changes** from search code changes in Phase 2 — LiveHardestAI definitions and opening books in their own commit (Phase 2c). (R4, R5, R7)

12. **Add cardLibrary validation script** in Phase 4 — check required fields, token references, no duplicate names. (5/8 reviewers)

13. **Add Phase 7 error handling specification** — AI crash recovery, timeout handling, stuck detection, resource cleanup. (R4, R5, R6, R8)

14. **Add color-symmetry testing** in Phase 7d — test MCDSAI as both P0 and P1. (R3, R4)

15. **Clarify Phase 4 merge strategy** — for units existing in both origin/master and live game, live game screenshots are authoritative for field values. (5/8 reviewers)

16. **Specify DoSuggest input format** — clarify that matchup code writes bare format (no CurrentInfo wrapper). (R7)

### Consider (presented as pick list in updated plan)

17. Phase 0.5 baseline tournament verification (R4)
18. Neural weight validation test — known input → plausible output (R5, R7, R8)
19. Performance/memory baseline logging per phase (R2, R5, R8)
20. Structured JSON logging for matchup games (R5, R8)
21. Long-lived subprocess protocol for Phase 7e (R2, R7)
22. Parse card data from SWF extraction for automated Phase 4 verification (R7, R8)
23. Matchup configuration file for Phase 7 parameters (R8)

### Reject (with reason)

| Suggestion | Reason for Rejection |
|------------|---------------------|
| Fix matchup_main.js surgically (R6) | Contradicts rebuild rationale. Accumulated bugs are WHY we rebuild. |
| NeuralUCTSearch subclass (R8) | UCT changes are deeply interleaved (traverse return type, PUCT formula). Would duplicate ~400 lines. |
| Strangler fig pattern (R5) | Overkill for single developer. The old code is being completely replaced. |
| Feature flags for excluded features (R5) | Unnecessary complexity. Hard exclusion is cleaner and matches single-developer workflow. |
| Ban shift semantics in C++ output (R2) | The C++ expansion code works correctly. Banning it would create a new protocol requirement. |
| CSPRNG instead of PID seeding (R8) | PID seeding is adequate for AI search randomness. Matches existing codebase convention. |
| Defer deepClone() (R4, R5) | **CRITICAL for threading.** Tournament defaults to 4 threads. Without deepClone, race conditions crash immediately. |
| Pin MCDSAI binary in repo (R5) | License unclear. Hash pinning + local copy is sufficient. |
| Local replay fixtures for Phase 5 (R7) | S3 bucket is public and stable. 500 replays × ~50KB each = 25MB committed for marginal benefit. |
| Pre-flight check script (R6) | Over-engineering for single developer who knows their environment. |

---

## A.7 — What Stays

The following plan elements were confirmed as solid by reviewers and codebase validation:

1. **"C++ = AI brain, JS = game truth" principle** — all 8 reviewers endorsed this
2. **Starting from origin/master (C++) and 99d39fe (JS)** — correct baselines
3. **"What We're NOT Bringing Back" exclusion table** — all 8 reviewers praised this
4. **Anti-pattern sections** — "DO NOT add stagnation", "DO NOT add improved heuristics", etc.
5. **Phase 7 sub-phase decomposition** (7a→7e) — incremental approach is correct
6. **Key learnings block in Phase 7** — supply bug root cause, click protocol details
7. **Per-phase verification checklists** — concrete, testable criteria
8. **Phase 0 API reference** — documenting verified APIs prevents scope creep
9. **Phase 5 mechanical copy from validated commit** — low risk, high confidence
10. **Card.h instId addition** — necessary for DoSuggest click mapping, minimal engine impact
11. **deepClone() in Player clone methods** — critical for multi-threaded tournaments
12. **SkipColorSwap support** — important for self-play efficiency
