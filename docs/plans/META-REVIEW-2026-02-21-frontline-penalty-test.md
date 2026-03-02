# Meta-Review: Frontline Penalty Isolation Test Plan

**Plan:** `docs/plans/2026-02-21-frontline-penalty-test.md`
**Reviews:** 7 external reviewers
**Date:** 2026-02-22

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Constructively critical | Heuristic mapping, BuySafeguard, head-to-head design | Detailed statistical comparison of shared-opponent vs head-to-head sensitivity |
| R2 | Constructively critical | Resample-on-skip, constructor defaults, paired design | Suggested resample instead of skip-and-waste; RapidJSON `IsNumber()` robustness |
| R3 | Constructively critical | Hit rate math, head-to-head, EC2 safety timeout | Max-runtime background job for cost protection |
| R4 | Focused, direct | Insertion point scope, BuySafeguard, constructor sentinel | `continue` could skip wrong loop level |
| R5 | Thorough, analytical | Penalty fire rate, parameter sweep, indirect comparison noise | SkipNonFrontline doesn't check enemy attack potential (second penalty condition) |
| R6 | Analytical | Local-first validation, config simplification, BuyEconTech audit | Suggested dropping BaseIterator_FLLegacy; hit-rate calculator script |
| R7 | Most opinionated | Over-engineering, remove SkipNonFrontline, temporary hack | Argued general config key is over-engineered for one experiment |

---

## A.2 — Consensus Points

| Point | Reviewers | Verdict |
|---|---|---|
| **BuySafeguard contamination must be fixed** | 7/7 | **TRUE — and worse than identified** (see A.4) |
| **Frontline hit rate ~60%, not ~83%** | 7/7 | **TRUE** — 10 buyable frontline in ~94 dominion pool |
| **Head-to-head tournament recommended** | 6/7 | **ADOPT** — as secondary arm alongside paired design |
| **GameState scope at insertion point** | 4/7 | **FALSE** — `state` IS in scope (line 98), but insertion point should move before player-pair loops |
| **Skip counter / logging** | 4/7 | **ADOPT** — essential for validating hit rate |
| **Constructor default regression risk** | 3/7 | **FALSE** — only 3 call sites exist (all in AIParameters.cpp), but sentinel default is cheap insurance |
| **Use dedicated branch** | 3/7 | **ADOPT** — `test/frontline-penalty`, not pollute `feature/cpp-replay-stepper` |

---

## A.3 — Outlier Points

| Point | Reviewer | Merit Assessment |
|---|---|---|
| EC2 max-runtime safety timeout | R3 | **Has merit** — given $805 bill shock history, a 3-hour `Stop-Computer` safety net costs nothing |
| RapidJSON `IsNumber()` fallback | R2 | **Minor merit** — plan already uses `100000.0`; codebase consistently uses `IsDouble()` |
| Parameter sweep {1, 5, 10, 100, 100K} | R2, R5 | **Future work** — good follow-up if binary test shows an effect |
| Instrumentation for penalty fire count | R2 | **Has merit** — confirms experiment isn't vacuous; consider-tier |
| Config inheritance/macro system | R6 | **Future work** — not relevant to this experiment |
| Remove SkipNonFrontline entirely | R7 | **Reject** — post-hoc filtering requires card-set data in results, which the HTML format doesn't include |

---

## A.4 — Category Breakdown (with Codebase Validation)

### 🏗️ Architecture & Design

**Heuristic function mapping concern (R1, R2, R3, R4, R7):**
All 5 reviewers worried that `"heuristic":"BuyAttackValue"` with `legacy=false` would select the OLD function.

**Codebase reality (AIParameters.cpp:537-545):**
```cpp
else if (heuristic == "BuyAttackValue")
{
    auto fn = legacy ? &Heuristics::BuyAttackValue : &Heuristics::BuyAttackValue_Improved;
    playerPtr = PPPtr(new PartialPlayer_ActionBuy_GreedyKnapsack(player, filter, fn, legacy));
}
```
**The `legacy` flag controls function selection, NOT the string.** With `legacy=false` (the FLLegacy entries omit `"legacy":true`), `"BuyAttackValue"` maps to `BuyAttackValue_Improved`. **The plan's config entries are correct.** All 5 reviewers were wrong on this point. No change needed.

**Constructor call site regression (R2, R3, R4):**
Grep confirms exactly 3 call sites in `AIParameters.cpp` (lines 535, 540, 545) plus the copy constructor in `clone()`. **No other direct instantiations exist.** The risk is theoretical, not real. However, a sentinel default (`-1.0`) is cheap insurance and makes the API self-documenting. Adopt as should-do.

**BaseIterator_FLLegacy can be dropped (R6):**
**Incorrect.** `HardIterator` uses `"include":"BaseIterator"` (config.txt line 166). The non-root iterator inherits from BaseIterator, so `HardIterator_FLLegacy` must include `BaseIterator_FLLegacy`. Both are needed.

### ⚠️ Risks & Concerns

**BuySafeguard contamination (all 7 reviewers):**
Confirmed and **WORSE than any reviewer identified.** Tracing the full reachability chain from `PrismatAI_AB`:

```
PrismatAI_AB → HardIterator_Root → BuyEconTech → BuySafeguard → BuyGK_AttackValue (penalty=5.0)
PrismatAI_AB → HardIterator_Root → BuyTechEcon → BuySafeguard → BuyGK_AttackValue (penalty=5.0)
PrismatAI_AB → HardIterator (include BaseIterator) → BuyEconTech → BuySafeguard → BuyGK_AttackValue
PrismatAI_AB → HardIterator (include BaseIterator) → BuyTechEcon → BuySafeguard → BuyGK_AttackValue
```

The plan's FLLegacy config entries reference `BuySafeguard` (in the combo entries) and `BuySafeguardRoot` (in the BCG root entries), AND `BuyEconTech`/`BuyTechEcon` in the iterators — **all four** leak penalty=5.0. The Legacy chain in config.txt properly duplicates all four (`BuySafeguard_Legacy`, `BuySafeguardRoot_Legacy`, `BuyEconTech_Legacy`, `BuyTechEcon_Legacy`). The FLLegacy chain must do the same.

**Fix: 4 additional config entries** (BuySafeguard_FLLegacy, BuySafeguardRoot_FLLegacy, BuyEconTech_FLLegacy, BuyTechEcon_FLLegacy), plus updates to all combo/BCG/iterator entries to reference them. Total new entries increases from 15 to 20.

**Frontline hit rate (all 7):**
Confirmed. `setStartingState()` (GameState.cpp:2016-2045) draws 8 cards from `GetDominionCardTypes()` pool. 10 buyable frontline units (Behemoth is unbuyable) in ~94 dominion cards. **No base set units are frontline** (verified all 11).

P(≥1 frontline) = 1 - C(84,8)/C(94,8) ≈ **61%**

At 500 rounds × 6 instances: 6000 × 2 games × 0.61 = ~7,320 total games, ~3,660 per arm. **Must increase rounds to 700** for ~5,100 per arm.

**GameState scope (R1, R3, R4, R5):**
**The concern is unfounded** — `state` is created at line 98 from `stateTemplate` (which has random cards from `setStartingState()` called in `run()` at line 246). However, the reviewers' scrutiny reveals the insertion point should be improved: the check belongs **before the player-pair loops** (after line 98, before line 100), using `return` to skip the entire round, not `continue` inside the inner loop. This is cleaner and avoids the loop-nesting ambiguity R4 flagged.

### 🔄 Alternative Approaches

**Paired tournament design (R2, R5, R6):**
Put both `PrismatAI_AB` (group 1) and `PrismatAI_AB_FrontlineLegacy` (group 1) vs `OriginalHardestAI` (group 2) in ONE tournament. Each round plays both arms against the same opponent with the **same card set**. Strictly superior: paired data, half the instances, same statistical power. The tournament system supports this — same-group players don't face each other, and `TournamentGame` copies the state (the original `state` is preserved across game pairs).

**Head-to-head (R1, R3, R4, R5, R7):**
Direct AB vs FLLegacy as a secondary tournament. Most sensitive test for detecting the penalty's effect.

**Post-hoc filtering (R2, R5, R7):**
**Reject.** Tournament HTML output does not include per-game card sets. Implementing post-hoc filtering would require additional C++ changes to log card sets — arguably more complex than SkipNonFrontline.

**Temporary hack instead of FrontlinePenalty config key (R7):**
**Reject.** The config key is ~15 lines across 3 files, backward-compatible, and enables future parameter sweeps. The "hack" alternatives (hardcoded player ID checks, `#define`s) are ugly and disposable. R1-R6 all praised the general-purpose approach. The code investment is minimal; the payoff is reusability.

### ✅ Confirmed Good / Keep As-Is

- Phase 0 pre-gathered facts (all reviewers)
- `FrontlinePenalty` as general-purpose config key (R1-R6)
- Anti-pattern sections (R1, R3)
- Config chain duplication approach (all reviewers)
- AWS `TOURNAMENT_NAME` parameterization (R1, R2, R6)
- Phase-by-phase verification steps (R1, R3, R6)
- Cost-conscious spot instance design (R5, R6)

---

## A.5 — Conflicts & Contradictions

### General config key vs temporary hack
- **R7** argues `FrontlinePenalty` is over-engineering for a one-time experiment
- **R1-R6** praise it as good permanent infrastructure

**Recommendation:** Side with R1-R6. The code investment (15 lines) is trivial. The parameter enables future sweeps (R2, R5 both suggest testing intermediate values). Temporary hacks create technical debt.

### Keep SkipNonFrontline vs remove it
- **R1, R2, R3, R6** say keep (with logging)
- **R5, R7** say remove, use post-hoc filtering

**Recommendation:** Keep. Post-hoc filtering requires card-set data that isn't in the HTML output. Adding card-set logging to the tournament output would be a larger change than SkipNonFrontline itself.

### Insertion point: inner loop vs round level
- **Plan** puts check inside p2 loop with `continue`
- **R4** flags `continue` could skip wrong scope
- **Code inspection** shows `state` is at round scope (line 98)

**Recommendation:** Move check before player-pair loops, use `return` to exit `playRound()`. Cleaner, unambiguous, functionally equivalent for any number of players.

---

## A.6 — Recommended Plan Changes

### Must-do

| # | Change | Reviewers | Rationale |
|---|---|---|---|
| M1 | **Fix full contamination chain**: add BuySafeguard_FLLegacy, BuySafeguardRoot_FLLegacy, BuyEconTech_FLLegacy, BuyTechEcon_FLLegacy; update all combo/BCG/iterator entries | All 7 | Without this, the FLLegacy arm leaks penalty=5.0 through 4 paths. Experiment is invalid. |
| M2 | **Fix hit rate to ~61% and increase rounds to 700** | All 7 | At 500 rounds: ~3,660 games/arm. At 700: ~5,120 games/arm. |
| M3 | **Move skip logic before player-pair loops** using `return` | R1, R3, R4, R5 + code inspection | Avoids inner-loop ambiguity. `state` confirmed in scope at line 98. |
| M4 | **Add skip counter** (`std::atomic<size_t> _skippedNonFrontlineRounds`) with periodic logging | R1, R2, R3, R6 | Essential for validating hit rate and debugging. |

### Should-do

| # | Change | Reviewers | Rationale |
|---|---|---|---|
| S1 | **Adopt paired tournament design**: 3-player tournament (AB + FLLegacy in group 1 vs Original in group 2) | R2, R5, R6 | Same card sets for both arms. Half the instances. Strictly superior. |
| S2 | **Add head-to-head tournament** as secondary arm | R1, R3, R4, R5, R7 | Most sensitive test. 3 instances, ~$0.84. |
| S3 | **Constructor sentinel default** (`frontlinePenalty = -1.0`, ternary fallback in initializer) | R1, R2, R4 | Cheap insurance, self-documenting API. |
| S4 | **Use branch `test/frontline-penalty`** | R1, R3, R6 | Don't pollute `feature/cpp-replay-stepper`. |
| S5 | **Add TimeLimit patching** for `PrismatAI_AB` and `PrismatAI_AB_FrontlineLegacy` in launch script | Code inspection | Existing script only patches `PrismatAI_AB_Legacy` and `OriginalHardestAI`. |

### Consider (presented as pick list in updated plan)

| # | Change | Reviewers | Effort | Recommendation |
|---|---|---|---|---|
| C1 | Local sanity check (50-100 rounds) before AWS | R3, R5, R6 | Small | Lean yes |
| C2 | Python result analysis script (WR + CI + z-test) | R1, R5, R6 | Medium | Lean yes |
| C3 | EC2 max-runtime safety timeout (3hr) | R3 | Trivial | Lean yes |
| C4 | RapidJSON `IsNumber()` fallback for robustness | R2 | Trivial | Neutral |
| C5 | Rollback plan documentation | R1, R3, R5 | Trivial | Lean yes |
| C6 | List all 11 frontline units in plan | R3 | Trivial | Lean yes |
| C7 | Penalty fire instrumentation (count times penalty applied) | R2, R5 | Small | Lean yes |
| C8 | Parameter sweep follow-up plan | R2, R5 | Trivial (doc only) | Neutral |

### Reject (with reason)

| Suggestion | Reviewers | Reason |
|---|---|---|
| Remove SkipNonFrontline, use post-hoc filtering only | R5, R7 | Tournament HTML doesn't include per-game card sets. Would need bigger C++ changes. |
| Temporary hack instead of FrontlinePenalty config key | R7 | 15 lines of permanent infrastructure vs disposable code. All other reviewers praised the general approach. |
| Drop BaseIterator_FLLegacy | R6 | HardIterator uses `"include":"BaseIterator"` — must have FLLegacy variant. |
| Heuristic string names are wrong | R1-R5, R7 | **Code confirms:** `legacy` flag controls function selection, not the string. `"BuyAttackValue"` with `legacy=false` → `BuyAttackValue_Improved`. Plan is correct. |
| Remove base-set anti-pattern note | R3 | Valid clarification since `numCardsBuyable()` includes base set. No base set units are frontline (verified), but the note prevents future confusion. |

---

## A.7 — What Stays

These plan elements were praised by multiple reviewers and should remain unchanged:

- **Phase 0 facts gathering** — prevents re-research, pinpoints exact locations
- **C++ `FrontlinePenalty` as general config key** — correct engineering investment
- **Config chain duplication approach** — correctly isolates the variable
- **Anti-pattern sections** — prevent common mistakes
- **AWS `TOURNAMENT_NAME` parameterization** — backward-compatible, scalable
- **Phase-by-phase verification steps** — thorough engineering hygiene
- **Cost-conscious spot instance design** — appropriate given budget constraints
- **SkipNonFrontline tournament flag** — follows established `SkipColorSwap` pattern
- **Decision rules** (3% threshold, CI-based) — explicit and actionable
