# Meta-Review: AS3 → JavaScript Game Engine Transpilation Plan

**Plan reviewed:** `docs/plans/2026-02-25-as3-js-transpilation-plan.md`
**Reviews ingested:** 9
**Date:** February 25, 2026

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Constructively critical | Dictionary iteration order, 90% target too low, no bisection strategy, swoosh under-planned | Suggested `State.toString()` golden-test checkpoint as earliest validation gate |
| R2 | Constructively critical | Determinism contracts, Rndm porting, MCDSAI worker isolation, circular deps, name mapping | Two separate `require('MCDSAI3441.js')` for 2-player self-play isolation |
| R3 | Mixed-to-critical | 10 distinct risks, UI dependency audit, timeline optimism, mergedDeck schema | Replay→engine adapter for existing 2,127 replays; mergedDeck schema drift risk |
| R4 | Mixed-to-critical | 80% code coverage mandate, AST transpilation for Tier 1, State.js sub-modules | EndTurnObject might be stubbable (not all fields needed for PvP) |
| R5 | Critical | Stagnation non-negotiable, stratified validation, MCDSAI version pinning, rollback criteria | Stratified validation by game-length buckets (short/mid/long/stagnation) |
| R6 | Critical | Decompiled code land-mines, ~100 bugs expected, feature-flagged stagnation, TypeScript boundary | Decompiler artifacts (renamed locals, inlined constants, dead code) as systematic risk |
| R7 | Measured/constructive | Phase -1 golden reference, swoosh pre-decomposition, Rndm impl, replay adapter early | Capture AS3 golden reference data BEFORE transpiling as diff-test oracle |
| R8 | Mostly positive | Test framework + deterministic matching critical, State.js modules, instId tiebreaker | Lowest-instId tiebreaker for ambiguous instance matching; fail-hard on invalid clicks |
| R9 | Critical but precise | int/uint truncation, Apache Royale compiler, AS3Dictionary polyfill, for..in vs for each..in | Apache Royale AS3→JS compiler as partial automation; `|0` for integer truncation |

## A.2 — Consensus Points

Ranked by number of reviewers raising each point:

| # Reviewers | Point | Assessment |
|---|---|---|
| **9/9** | Dictionary/Map iteration order is the #1 determinism risk | **CONFIRMED by codebase.** `StateUtil.findInstId()` (line 142) iterates `table` with `for (val in ...)` returning first match. When identical units exist, iteration order determines which is selected. AS3 `Dictionary` uses hash-based order; JS `Map` uses insertion order. |
| **7/9** | 90% replay pass rate target is too low — should be 99%+ | **AGREED.** A faithful port should only fail on genuinely ambiguous cases (randomized defense ordering, stagnation edge cases). 90% tolerates ~200 systematic bugs. |
| **7/9** | Need automated test framework from Phase 0 | **AGREED.** Every reviewer emphasized test infrastructure must precede transpilation, not follow it. |
| **6/9** | No debugging/bisection methodology for state divergence | **AGREED.** Plan has no strategy for "first move diverges at turn 47" scenarios. Need turn-by-turn state comparison with automatic first-divergence detection. |
| **6/9** | Phase 6 (Cloud Deployment) should be separate/deferred | **AGREED.** Deployment is orthogonal to engine correctness. Including it inflates scope. |
| **5/9** | Stagnation system must be implemented, not deferred | **PARTIALLY AGREED.** Stagnation affects ~5-10% of games. For training data quality it matters — stagnated games without proper detection run 200+ turns of garbage data. But it can be Phase 5 (after core engine works). |
| **5/9** | State.as (4,490 LOC) and swoosh (~460 LOC) are under-planned | **AGREED.** The plan lists State.as as one bullet point. Swoosh alone has 8 sub-phases with complex control flow. Needs explicit breakdown. |
| **4/9** | Rndm.as "stub with throw" will crash in PvP | **CONFIRMED by codebase.** Rndm is used at State.as:3012 (`instIdsInRandomOrder` in swoosh for A.R. Groans annihilation ordering), State.as:841 (`instIdsDefense` permutation), State.as:1200 (`cardIdsInRandomOrder`). Stubbing with throw crashes any game with randomized ordering. |
| **4/9** | vectorize.py compatibility is hand-waved | **CONFIRMED by codebase.** `vectorize.py` expects `{state: {p0_units, p1_units, p0_resources, supply, card_set}}` format — completely different from `State.toString()` which outputs `{table, whiteMana, blackMana, whiteTotalSupply, ...}`. A significant adapter/converter is required. |
| **4/9** | Consider semi-automated transpilation (AST tools) for Tier 1 | **REASONABLE.** Tier 1 data classes (~1,150 LOC) are mechanical. AST tools or Apache Royale could handle 70-80% with manual cleanup. Diminishing returns for Tier 2-3 (complex control flow). |
| **4/9** | Ruffle/Flash as validation oracle worth a spike | **INTERESTING but LOW PRIORITY.** Ruffle runs AS3 in a Rust VM. Could potentially run the actual AS3 engine as a golden reference. But integration effort is unknown and we already have 2,127 replay ground truths. |
| **3/9** | MCDSAI needs separate worker processes for 2-player isolation | **VALID.** Emscripten module has global state. Two AI players in one process would share state. Need either `worker_threads` or `child_process` isolation. |
| **3/9** | Circular CommonJS module dependency risk | **LOW RISK after analysis.** The AS3 classes have clear dependency ordering: C → Mana/Click → Card/Script → Inst → State → Controller → Analyzer. Only State↔StateHelper is potentially circular, easily resolved with lazy require. |

## A.3 — Outlier Points

| Reviewer | Point | Merit Assessment |
|---|---|---|
| R9 | Apache Royale AS3→JS compiler | **High merit.** Novel suggestion no other reviewer raised. Royale is an actual Apache project that compiles AS3 to JS. Even if output needs cleanup, it could accelerate Tier 1 data classes significantly. Worth a 2-hour spike. |
| R6 | TypeScript `.d.ts` boundary declarations | **Low merit.** Adds complexity for a 15-file project that prioritizes correctness over tooling. The plan correctly targets plain JS. |
| R8 | Lowest-instId tiebreaker for ambiguous matching | **High merit.** Elegant, deterministic solution for the instance matching ambiguity problem. If AS3 Dictionary happens to iterate in insertion order (which correlates with instId), this could be the correct behavior. Needs empirical validation. |
| R9 | Headless Adobe AIR as alternative to transpilation | **Low merit for our case.** Adobe AIR is EOL, requires Windows, and we want cloud-scalable Node.js. But valid as a one-time golden reference generator. |
| R5 | Stratified validation by game-length buckets | **High merit.** Short games (≤10 turns) test basic mechanics, mid games (11-40) test economy, long games (41+) test stagnation. Different failure patterns reveal different bug classes. |
| R4 | EndTurnObject might be stubbable | **Partially valid.** EndTurnObject tracks achievement stats and stagnation counters. Achievement tracking IS stubbable for PvP. But stagnation counters are NOT — they drive the progress system that determines draws. |
| R7 | Phase -1: Capture AS3 golden reference before transpiling | **High merit but we already have this.** The 2,127 Master Bot replays ARE the golden reference. However, R7's point about capturing per-turn intermediate states (not just final outcomes) is valuable — replay validation currently only tests action legality, not state correctness. |

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| Split State.js into sub-modules (init, toString, moves, phases, swoosh, defense, breach, stagnation) | R1, R4, R5, R8 | State.as is 4,490 LOC with clearly separable sections | **Should-do.** Reduces cognitive load and enables parallel work. Keep in one file but use clearly marked sections with a barrel export. |
| MCDSAI needs worker process isolation for 2-player | R2, R3, R8 | MCDSAI3441.js is Emscripten — global Module state | **Must-do.** Cannot run two AI instances in one process. `child_process.fork()` or `worker_threads` required. |
| CommonJS circular dependency management | R2, R3, R6 | Dependency graph is mostly acyclic; State↔StateHelper is the only concern | **Low risk.** Lazy `require()` in StateHelper solves this. Not worth switching to ES modules. |
| AS3Dictionary polyfill class instead of bare Map | R9 | `Dictionary` used extensively in State.as (`table`, `cardMap`) | **Should-do.** A thin wrapper that guarantees insertion-order iteration and provides `for..in`-compatible iteration matches AS3 semantics more faithfully than raw Map. |
| Barrel `index.js` for clean imports | R4 | 15 files with clear dependency order | **Consider.** Nice-to-have but not critical for correctness. |

### ⚠️ Risks & Concerns

| Feedback | Reviewer(s) | Codebase Reality | Assessment |
|---|---|---|---|
| Dictionary iteration order → silent divergence | ALL 9 | `findInstId()` returns FIRST match in Dictionary iteration. `instIdsInRandomOrder()` also iterates Dictionary. | **CRITICAL. Must-do: implement AS3Dictionary wrapper with deterministic ordering from day 1.** |
| AS3 int/uint truncation vs JS Number | R9, R6 | 228 `int`/`uint` occurrences in State.as. Key areas: resource arithmetic, damage calc, turn counters | **Should-do.** Most are loop counters (harmless), but resource calculations like `mana.p[i]` could accumulate float drift. Use `|0` for integer truncation in arithmetic paths. Audit the 228 sites and annotate critical ones. |
| Decompiled code quality (renamed vars, dead code) | R6 | Decompiled AS3 is readable but has `_loc_3`, `_loc_4` style locals in some methods | **Real risk, mitigated.** The decompiler output is readable (JPEXS produces decent AS3). Dead code and renamed locals exist but are identifiable. Not as bad as R6 fears for our decompilation quality. |
| Rndm.as stub-with-throw crashes PvP | R2, R6, R7, R9 | Rndm used at State.as:3012 (swoosh), :841 (defense), :1200 (card ordering) via `instIdsInRandomOrder()` and `cardIdsInRandomOrder()` | **CRITICAL. Must-do: implement Rndm faithfully.** BitmapData.noise() uses a Lehmer/Park-Miller PRNG internally. Need to reverse-engineer the exact algorithm or use a JS equivalent seeded identically. |
| Timeline optimism (plan says 7-10 sessions) | R3, R5, R6 | 10,600 LOC with 4,490 in State.as alone; swoosh is ~460 LOC of dense control flow | **Agreed.** Realistic estimate is 12-18 sessions for core engine + validation. Phase 6 separately. |
| UI dependency hidden in State.as / Controller.as | R3 | **Validated:** All UI deps are stubbable. `Progression.inMissionWithName()` → `false`. `Game.gameInfo` → stub object. `CheatCodes` → `false`. `UIEvent.say` → no-op. Controller.as only has `dispatch()` (no-op when `update=false`) and one `UIEvent.say` (emote, no-op). | **Lower risk than feared.** R3 was right to flag it, but codebase inspection shows clean separation. |
| mergedDeck schema drift between cardLibrary.jso and MCDSAI | R3 | cardLibrary.jso has 161 units with `UIName` matching unit_index.json display names | **Low risk.** Both are from the same game version (build 3441). Schema is stable. |

### 🗑️ Suggested Removals / Simplifications

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Remove Phase 6 (Cloud Deployment) from this plan | R1, R3, R5, R6, R7, R8 | **Should-do.** 6/9 reviewers agree. Cloud deployment is a separate concern. End the plan at "first complete self-play game runs end-to-end" + validation. |
| EndTurnObject achievement tracking can be stubbed | R4 | **Partially agree.** Achievement fields (first kill, longest turn) are stubbable. Stagnation counter fields are NOT — they feed the progress system. Split: stub achievements, implement stagnation counters. |
| Exclude `MCDSEvent`, `Errorbang`, `Trigger`, `Objective` | Plan (original) | **Confirmed correct by all reviewers.** These are UI/campaign-only. |

### ➕ Suggested Additions / Features

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Phase 0 test harness: replay runner, state comparator, bisection tool | R1, R3, R4, R5, R7, R8 | **Must-do.** Unanimous. Build replay validation infrastructure BEFORE transpiling game logic. |
| Turn-by-turn state comparison (not just action legality) | R1, R7 | **Must-do.** Current replay validation only checks if actions are legal — it doesn't verify the resulting game state matches. Need `State.toString()` comparison at each turn boundary. |
| Stratified validation buckets (short/mid/long/stagnation games) | R5 | **Should-do.** Different game lengths exercise different code paths. Failures in long games likely indicate stagnation bugs; failures in short games indicate basic mechanic bugs. |
| Rollback/abort criteria for each phase | R5 | **Should-do.** Define what failure looks like and when to change strategy (e.g., "if Phase 2 takes >5 sessions, evaluate AST transpilation for remaining files"). |
| MCDSAI version pinning (hash check on load) | R5 | **Should-do.** Pin to exact MCDSAI3441.js SHA256 hash. Document which version. Trivial to implement. |
| Golden `State.toString()` test fixtures from live game | R1, R2, R7 | **Must-do.** Capture 5-10 game states at known positions via F6, run through both AS3 (live game) and JS engines, compare serialization byte-for-byte. This is the earliest validation gate. |
| `vectorize.py` adapter layer (State.toString → vectorize format) | R1, R3, R4, R5 | **Must-do.** vectorize.py expects `{p0_units, p1_units, p0_resources, supply, card_set}` — completely different from `State.toString()` format `{table, whiteMana, blackMana, ...}`. Need an explicit converter. |
| Rndm.as faithful implementation (not stub) | R2, R6, R7, R9 | **Must-do.** See Risks section. BitmapData.noise() algorithm must be reverse-engineered or approximated. |
| Stagnation system implementation | R5, R6, R7, R8 | **Should-do (Phase 5).** 4-level progress counter system is complex but necessary for training data quality. Games that should draw at turn 50 instead run to turn 200 without it, generating garbage data. Feature-flag approach (R6) is pragmatic. |

### 🔄 Alternative Approaches

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Apache Royale AS3→JS compiler | R9 | **Consider (2-hour spike).** Could automate Tier 1 data classes. Unknown output quality for game engine code. |
| AST-based transpiler for Tier 1 | R4, R9 | **Consider.** `as3-to-ts` or custom jscodeshift transforms for mechanical data classes. Diminishing returns for complex logic. |
| Ruffle (Rust Flash VM) as golden oracle | R4, R5, R6, R7 | **Consider (half-day spike).** If Ruffle can run our AS3 engine headless, it becomes a perfect golden reference. Integration effort unknown. |
| Headless Adobe AIR for golden reference | R9 | **Reject.** AIR is EOL, Windows-only, not scalable. We already have live game F6 capture for golden states. |
| Fix C++ engine instead of transpiling | R4 | **Reject.** Plan context document explains this thoroughly — 50.4% replay pass rate after audit, deep semantic mismatches, AI collapsed to 11% WR when bugs fixed. The C++ engine has too many intertwined issues. |
| WASM embedding of AS3 engine | R4 | **Reject.** No mature AS3→WASM pipeline exists. Would still need the same understanding of the code. |

### ✅ Confirmed Good / Keep As-Is

| Feedback | Reviewer(s) |
|---|---|
| Core strategy is correct: AS3 is ground truth, JS is natural port target, MCDSAI integration is sound | R1, R2, R3, R5, R7, R8 |
| Phased approach with testable milestones | R1, R4, R7, R8 |
| File tier decomposition (data classes → core → click processing) | R1, R3, R8 |
| Protocol-first integration (MCDSAI init/move format) | R2, R7 |
| Excluded files list (Trigger, Objective, RaidAnalyzer, etc.) | ALL |
| CommonJS modules (no TypeScript, no bundler) | R1, R2, R7, R8 (R6 dissented — TypeScript) |
| ES2020+ target | ALL |
| JSONL output format for training pipeline | R3, R5, R7 |
| Performance estimates (~0.8 games/min) | R3, R5 |
| Preserving AS3 class/method names | R1, R7, R8 |

### 🔧 Implementation Details & Nits

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| Use `|0` for integer truncation in arithmetic | R9 | **Should-do** for resource calculations, damage, and turn counters. Not needed for loop variables. |
| `for..in` (keys) vs `for each..in` (values) mapping | R9 | **Must-do.** AS3 `for..in` iterates keys, `for each..in` iterates values. Confusing these silently produces wrong results. Document the mapping convention. |
| Fail-hard on invalid/unexpected clicks | R8 | **Should-do.** `throw` on unrecognized click types rather than silently ignoring. Surfaces bugs early. |
| Deterministic instance matching: sort by instId | R8 | **Should-do.** When `findInstId()` has multiple matches, use lowest instId as tiebreaker. Needs empirical validation against live game behavior. |
| Explicit `null` vs `undefined` convention | R6 | **Consider.** AS3 has `null` but not `undefined`. Using strict `=== null` checks is cleaner. |

### 📦 Dependencies & Integration

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| cardLibrary.jso parser as Phase 0 deliverable | R3, R7 | **Must-do.** mergedDeck construction from cardLibrary.jso is prerequisite for everything. Already in Phase 0 but should be explicit checkpoint. |
| AI parameter loading from `148_*.bin` | R2 | Already in Phase 0. Confirmed working (plain JSON text, not binary). |
| vectorize.py format adapter | R1, R3, R4, R5 | **Must-do.** See Additions section. |
| unit_index.json name alignment | R2 | **Non-issue.** Verified: unit_index.json uses display names (Tarsier, Blastforge, etc.) matching MCDSAI. |

### 🔮 Future Considerations

| Feedback | Reviewer(s) | Assessment |
|---|---|---|
| JS engine could replace C++ for all training | R3, R5 | True long-term but 10x slower. C++ remains primary for self-play once fixed. |
| JS engine enables browser-based play | R3 | Nice side benefit. Not a goal for this plan. |
| Could integrate with neural net WASM for full browser AI | R4 | Very far future. Noted. |

## A.5 — Conflicts & Contradictions

### TypeScript vs Plain JavaScript
- **R6** advocates TypeScript `.d.ts` boundary declarations for type safety
- **R1, R2, R7, R8** support plain JavaScript (matches plan)
- **Recommendation:** Stay with plain JS. TypeScript adds build complexity and the project is 15 files. Type bugs are caught by tests, not type annotations. R6 is outnumbered 4:1.

### Stagnation: Implement Now vs Phase 5 vs Feature-Flag
- **R5** says stagnation is "non-negotiable" and must be in core phases
- **R6** suggests feature-flag approach (implement behind toggle)
- **R7, R8** agree it's needed but accept phasing
- **Recommendation:** Implement in Phase 5 (after core engine works) with feature flag. R6's pragmatic approach is best — core engine without stagnation can still generate useful training data for games that don't stagnate. The flag lets us ship earlier and add stagnation incrementally.

### AST Transpilation vs Manual
- **R4, R9** advocate automated/semi-automated transpilation
- **R1, R7, R8** implicitly accept manual (focus on test infrastructure instead)
- **Recommendation:** Try Apache Royale or `as3-to-ts` on ONE Tier 1 file as a spike. If output quality is >70% correct, use for remaining Tier 1. Manual for Tier 2-3 regardless (too complex for automated tools).

### Replay Pass Rate Target
- **R5** says 99%+ is the only acceptable target
- **R8** suggests 95% with characterized remaining failures
- **R1, R3** say 99% but accept phased approach
- **Recommendation:** Target **99%+ with all failures characterized.** Remaining 1% must be explained (randomized ordering, known edge cases). This is a faithful port — unknown failures indicate bugs.

### Ruffle Spike Priority
- **R5, R6, R7** think Ruffle spike is worth exploring
- **R4** mentions it as alternative
- **R1, R2, R8** don't mention it
- **Recommendation:** **Consider** — half-day spike. If Ruffle can run AS3 headless, it's an invaluable oracle. But don't block the plan on it. We already have F6 golden states and 2,127 replays.

## A.6 — Recommended Plan Changes

### Must-Do (high consensus, high impact, or addresses real risks)

1. **Add Phase 0.5: Test Infrastructure** — Build replay runner, turn-by-turn state comparator, and automatic first-divergence bisection tool BEFORE transpiling game logic. (R1, R3, R4, R5, R7, R8)

2. **Implement Rndm.as faithfully** — Port BitmapData.noise() PRNG algorithm to JS. Stub-with-throw crashes any game reaching `instIdsInRandomOrder()` or `cardIdsInRandomOrder()`. **Codebase confirms:** 5 call sites in PvP paths. (R2, R6, R7, R9)

3. **Implement AS3Dictionary wrapper** — Thin class guaranteeing deterministic iteration order matching AS3 Dictionary semantics. Use for `table`, `cardMap`, and all Dictionary-typed fields. This is the #1 risk. (ALL 9 reviewers)

4. **Add vectorize.py adapter** — Explicit converter from `State.toString()` format to vectorize.py's expected `{p0_units, p1_units, p0_resources, supply, card_set}` format. Document both schemas. **Codebase confirms:** formats are completely different. (R1, R3, R4, R5)

5. **MCDSAI worker process isolation** — Use `child_process.fork()` for each AI player. Emscripten global state prevents two instances in one process. (R2, R3, R8)

6. **Raise replay validation target to 99%+** with all remaining failures characterized and explained. (R1, R3, R5, R7, R8)

7. **Add golden State.toString() test fixtures** — Capture 5-10 game states via F6 at known positions. Compare JS serialization against live game output byte-for-byte. Earliest validation gate. (R1, R2, R7)

8. **Document `for..in` vs `for each..in` mapping convention** — AS3 `for..in` = keys, `for each..in` = values. Getting this wrong silently produces incorrect iteration. Must be documented and enforced. (R9)

### Should-Do (strong suggestions that meaningfully improve the plan)

9. **Break State.js into clearly marked sections** — Init, toString, moves, phases, swoosh, defense, breach, stagnation. Keep in one file (matching AS3) but with explicit section headers and a breakdown in the plan. (R1, R4, R5, R8)

10. **Remove Phase 6 (Cloud Deployment)** — End plan at "validated self-play games running locally." Deployment is a separate plan. (R1, R3, R5, R6, R7, R8)

11. **Add rollback/abort criteria per phase** — Define what failure looks like and when to pivot. E.g., "if Phase 2 exceeds 5 sessions, evaluate AST tooling for remaining files." (R5)

12. **Pin MCDSAI version** — SHA256 hash check of MCDSAI3441.js on load. Document exact version. (R5)

13. **Add `|0` integer truncation** for AS3 `int`/`uint` arithmetic paths — resource calculations, damage, turn counters. Not needed for loop variables. (R9)

14. **Implement stagnation system in Phase 5** with feature flag — 4-level progress counter system. Behind toggle so core engine can ship without it. (R5, R6, R7, R8)

15. **Stratified validation** — Categorize replay results by game length (short ≤10, mid 11-40, long 41+, stagnation). Different failure patterns reveal different bug classes. (R5)

16. **Fail-hard on unexpected clicks** — `throw` on unrecognized click types in Controller rather than silent ignore. (R8)

17. **Deterministic instId tiebreaker** — When `findInstId()` has multiple matches, use lowest instId. Needs empirical validation. (R8)

18. **Strengthen Phase 2 checkpoint** — "Can serialize initial state" is too weak. Should be: "Can create state from mergedDeck, apply 5 turns of hardcoded moves, serialize, and match golden reference at each step." (R7)

### Consider (good ideas, presented as pick-list in updated plan)

19. **Apache Royale / AST spike for Tier 1** — 2-hour spike to test automated transpilation of one data class. (R4, R9)

20. **Ruffle spike for golden oracle** — Half-day to test if Ruffle can run AS3 engine headless for state comparison. (R4, R5, R6, R7)

21. **Barrel index.js** for clean imports. (R4)

22. **Explicit `null` vs `undefined` convention** in JS port. (R6)

23. **Phase -1: Capture per-turn intermediate states from live game** — Beyond F6 snapshots, record full state at every turn boundary for a set of reference games. (R7)

24. **EndTurnObject partial stub** — Stub achievement tracking fields, implement only stagnation-relevant counters. (R4)

### Reject (with reason)

25. **TypeScript boundary declarations** (R6) — Adds build complexity for a 15-file project. Type safety comes from tests, not annotations. 4:1 reviewer consensus against.

26. **Headless Adobe AIR** (R9) — EOL, Windows-only, not cloud-scalable. We have better alternatives (F6 capture, replay validation, potential Ruffle).

27. **Fix C++ engine instead** (R4) — Plan context document thoroughly explains why this was abandoned. 50.4% pass rate, deep semantic mismatches, AI collapsed to 11% WR when bugs partially fixed. The root cause is architectural, not individual bugs.

28. **WASM embedding of AS3** (R4) — No mature toolchain. Would require the same code understanding as manual transpilation.

29. **80% code coverage mandate** (R4) — Aspirational but impractical for a transpilation project. Replay validation at 99%+ is a much stronger correctness guarantee than unit test coverage metrics. Test critical paths, not coverage numbers.

## A.7 — What Stays

The following elements were confirmed as solid by multiple reviewers and remain unchanged:

1. **Core strategy**: AS3 → JS transpilation to get ground-truth engine, paired with MCDSAI3441.js for self-play
2. **File tier decomposition**: Tier 1 (data classes) → Tier 2 (core engine) → Tier 3 (click processing)
3. **Technology choices**: ES2020+ JavaScript, CommonJS modules, no TypeScript, no bundler
4. **Excluded files**: Rndm (now included, not excluded), Trigger, Objective, RaidAnalyzer, MCDSEvent, Errorbang
5. **MCDSAI protocol documentation**: Init payload, move request, click application — all correct and well-documented
6. **Instance matching via `compareWithJSON()`**: Correct approach, needs determinism guarantees
7. **Preserving AS3 class/method/variable names**: Aids traceability
8. **JSONL output format** for training pipeline
9. **Performance estimates**: ~0.8 games/min realistic for Node.js + MCDSAI
10. **Transpilation conventions**: `dispatch()` → no-op, `Vector.<T>` → Array, etc.
11. **Key insight**: `StateUtil.convertToClicks()` pattern for MCDSAI↔engine bridge

**Notable change from "Excluded"**: Rndm.as moves from excluded (stub-with-throw) to **included** (faithful implementation). This was the single biggest factual error in the original plan, confirmed by codebase inspection.
