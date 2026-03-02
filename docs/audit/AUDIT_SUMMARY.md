# Engine Logic Audit Summary: C++ vs AS3 Ground Truth

> **Completed**: 2026-02-22
> **Scope**: 22 audit areas across 6 phases, comparing ~4,000 lines C++ against ~12,500 lines AS3
> **Branch**: `feature/engine-logic-audit`

---

## 1. Executive Summary

A systematic comparison of the C++ AI engine (`source/engine/`) against the decompiled AS3
ground-truth client engine (`prismata_decompiled/scripts/mcds/engine/`) was conducted across
22 audit areas in 6 phases. The audit produced 15 deliverable documents totaling ~9,500 lines
of analysis with code path traces, test cases, and verdicts.

**Key results:**
- **4 code fixes applied** (1 CRITICAL, 1 HIGH, 2 MEDIUM)
- **3 confirmed divergences** that affect game outcomes (defense reset, all-units-doomed, mutual elimination)
- **5 structural differences** with no current gameplay impact (script ordering, death scripts, stagnation, etc.)
- **14 areas verified as MATCH** — the C++ engine correctly implements the core game rules

The most impactful finding was the already-known defense-reset bug (commit 5bf57a8), which the
audit confirmed as the ONLY status change in C++ with no AS3 counterpart. The "all units doomed"
game-over condition was a new CRITICAL finding — C++ was missing an instant-win check.

---

## 2. Fixes Applied (Phase 4)

All fixes in `source/engine/GameState.cpp`:

### Fix 1: Remove Defense Phase Status Reset (CRITICAL)
- **Removed**: Lines 1289-1307 in `beginPhase(Defense)` — a `for` loop that reset all
  defending player card statuses to Default/Inert before defense
- **Root cause**: Commit 5bf57a8 (Feb 13, 2026) incorrectly assumed the live game resets
  statuses before defense. The AS3 ground truth shows statuses persist through Defense —
  tapped units use `assignedBlocking` (usually false) for block eligibility
- **Impact**: ~40-60% extra defense per Defense phase across 722K self-play games
- **Audit reference**: `docs/audit/A1_blocking_eligibility.md`

### Fix 2: WIPEOUT Fall-Through Break (MEDIUM)
- **Added**: `break;` after `endPhase()` in the `ActionTypes::WIPEOUT` case
- **Root cause**: Missing break caused fall-through into `UNDO_CHILL`, running unnecessary
  chill-undo logic on every wipeout action
- **Impact**: Code correctness — no measurable game outcome effect (guard code prevented worst case)
- **Audit reference**: `docs/audit/P0_1_phase_transition_state_machines.md`, D-06

### Fix 3: "All Units Doomed" Game-Over Check (CRITICAL)
- **Added**: Loop in `calculateGameOver()` checking if all units of either player have
  `lifespan==1` with `constructionTime==0` and `delay==0`
- **Root cause**: C++ only checked `numCards == 0`. AS3 `checkWin()` has 4 conditions including
  `helper.allOppUnitsDoomed` which ends the game immediately when all opponent units will die
  next swoosh
- **Impact**: Games with doomed opponents continue 1 extra turn in C++, producing incorrect
  value targets for training data
- **Audit reference**: `docs/audit/A5_game_over_conditions.md`

### Fix 4: Mutual Elimination Draw (HIGH)
- **Fixed**: `winner()` now checks both-dead before either-dead, returning `Player_None` (draw)
  instead of incorrectly awarding P2 the win due to first-check ordering bias
- **Also added**: "All units doomed" winner determination in `winner()` — the OTHER player wins
- **Impact**: Extremely rare (mutual elimination almost never occurs), but now correct
- **Audit reference**: `docs/audit/A5_game_over_conditions.md`

---

## 3. Master Findings Table

| ID | Area | Severity | Finding | Verdict | Fix Status |
|---|---|---|---|---|---|
| A0 | Phase Transitions | — | Phase sequence matches except defense entry | MATCH | N/A |
| A1-BUG | Blocking Eligibility | **CRITICAL** | Defense reset allows tapped Drones to block | MISMATCH | **FIXED** |
| A1-REST | Blocking (other checks) | — | canBlock, frozen, defense calc all match | MATCH | N/A |
| A2 | Chill/Freeze Formula | — | Mathematically equivalent in all reachable states | MATCH | N/A |
| A3-WIPE | Wipeout Threshold | — | `attack >= defense` identical | MATCH | N/A |
| A3-BREACH | Breach Architecture | LOW | glassBroken flag vs Phases::Breach enum | STRUCTURAL | N/A |
| A3-DEATH | Death Script in Breach | LOW | C++ has no deathScript support | LATENT GAP | Not fixed (no units use it) |
| A4 | Damage Application | — | Different architecture, same behavior | MATCH | N/A |
| A5-DOOMED | All-Units-Doomed | **CRITICAL** | Missing instant-win condition | MISMATCH | **FIXED** |
| A5-DRAW | Mutual Elimination | **HIGH** | P1 checked first, P2 incorrectly wins | MISMATCH | **FIXED** |
| A5-STAG | Stagnation System | MEDIUM | 4-level system vs 200-turn limit | GAP | Not fixed (see B6) |
| B1 | Script Execution Order | MEDIUM | Two-pass vs single-pass | STRUCTURAL | Not fixed (no current impact) |
| B2 | Resource Reset Order | — | Same resources cleared | MATCH | N/A |
| B3-COST | Ability Cost Timing | MEDIUM | Health/charge deducted before (AS3) vs after (C++) script | MISMATCH | Not fixed (no current impact) |
| B4-SNIPE | Snipe Kill Timing | MEDIUM | Kill-then-script (C++) vs script-then-kill (AS3) | MISMATCH | Not fixed (no current impact) |
| B5 | Sellable Role | — | No divergence | MATCH | N/A |
| B6 | Stagnation Detection | HIGH | No progress counters, no 4-level system | GAP | Not fixed (200-turn limit sufficient) |
| B7-ORDER | Death Ordering | — | Same iteration order | MATCH | N/A |
| B7-SCRIPT | Death Triggers | LOW | No deathScript support | LATENT GAP | Not fixed (no units use it) |
| B8-BLOCK | Legal ASSIGN_BLOCKER | **CRITICAL** | Defense reset enables illegal blocking | MISMATCH | **FIXED** (via Fix 1) |
| B8-COND | Missing Conditions | MEDIUM | IS_BLOCKING, NAME_IN, IS_ABC, IS_ENGINEER_TEMP | GAP | Not fixed (affects ~4 units) |
| B8-NETH | Missing Netherfy Check | LOW | No valid-target check for netherfy | GAP | Not fixed |
| WIPEOUT | WIPEOUT Fall-Through | MEDIUM | Missing break in switch case | CODE SMELL | **FIXED** |
| CARDLIB | cardLibrary.jso Parsing | — | All gameplay fields parsed correctly | PASS | N/A |
| C1 | Construction/Delay | — | Mutually exclusive, same behavior | MATCH | N/A |
| C2 | Healing | — | Same formula | MATCH | N/A |
| C3 | Charge System | — | chargeGained not implemented but unused | MATCH | N/A |
| C4 | Supply Tracking | — | Identical rarity mapping | MATCH | N/A |
| C5 | Frontline/Melee | — | Same mechanics | MATCH | N/A |

---

## 4. Self-Play Impact Assessment

| Divergence | Affected Units | Frequency | Symmetry | Data Regen? |
|---|---|---|---|---|
| **Defense reset bug** | All units with `defaultBlocking=true` + ability (Drone, Steelsplitter, Rhino, Lancetooth, Shredder, Cauterizer, etc. — 50+ units) | ~100% of games with Defense phase | Symmetric (both sides) | **Yes** — all 722K games affected, but symmetric so impact is partially self-canceling |
| **All-units-doomed missing** | Any game ending with doomed lifespan units | ~5-15% of games (estimated) | Symmetric | Partial — affects late-game value targets |
| **Mutual elimination draw** | Both players reach 0 simultaneously | <0.1% of games | Symmetric | No — too rare to affect training |
| **Stagnation system** | Games near economic stalemate | ~1-3% of games (late-game draws) | Symmetric | No — 200-turn limit catches most cases |

**Recommendation**: Regenerate self-play data with the fixed engine. The defense reset bug
affects every game and inflates defense values, but since both sides have the same bug,
the neural net learned an internally-consistent (but wrong) game. Re-training with correct
rules will produce more realistic defense evaluations.

---

## 5. Success Criteria Checklist

| # | Criterion | Status |
|---|---|---|
| 1 | Phase transition diagram produced and verified | **PASS** — P0.1 |
| 2 | All P0 areas have Match/Mismatch/Uncertain verdict with code references | **PASS** — A0-A5 |
| 3 | At least 2 concrete test cases per P0 area | **PASS** — all P0 areas have 2+ cases |
| 4 | Mathematical equivalence for formula comparisons | **PASS** — A2 chill/freeze 4-case proof |
| 5 | Comprehensive status reset scan completed | **PASS** — P0.2, 9 anomalies documented |
| 6 | All findings reproducible (function names + code snippets) | **PASS** — all use function+snippet format |
| 7 | Regression test cases proposed for each confirmed divergence | **PARTIAL** — test cases documented but not yet implemented as automated C++ tests |
| 8 | Negative tests constructed for each P0 area | **PASS** — negative test table in audit plan |
| 9 | Self-play impact estimate per divergence | **PASS** — Section 4 above |
| 10 | cardLibrary.jso parsing parity check | **PASS** — Phase 3.5 |

**Overall: 9/10 PASS, 1 PARTIAL** (automated regression tests deferred)

---

## 6. Remaining Gaps (Not Fixed)

### Will NOT Fix (by design or zero current impact)

| Gap | Reason |
|---|---|
| Script execution ordering (two-pass vs single-pass) | No current card combination triggers divergence. Would require architectural change. |
| Ability cost timing (before vs after script) | No current card has health cost that kills + script that observes death. |
| Snipe kill timing (reversed) | No current snipe unit has script that observes target alive/dead. |
| deathScript support | No units in cardLibrary.jso define deathScript. |
| chargeGained/chargeMax | No units use per-turn charge restoration. |
| Missing Condition types (IS_BLOCKING, etc.) | Affects ~4 exotic units for target validation only. |
| Trigger system | Campaign/tutorial only, no PvP impact. |

### Should Fix Eventually (not blocking but meaningful)

| Gap | Impact | Effort |
|---|---|---|
| Stagnation detection system | Late-game draws detected too late, wrong value targets | HIGH — need 4-level progress counter system |
| Missing netherfy target check | AI could attempt illegal netherfy with no target | LOW — add target existence check |

---

## 7. Recommendations

1. **Regenerate self-play data** with the fixed engine. The 722K existing games all have
   the defense reset bug. New data will have correct blocking behavior.

2. **Run A/B tournament** comparing old engine vs fixed engine (100 games each vs
   OriginalHardestAI) to quantify the defense fix impact on game lengths and win rates.

3. **Implement automated regression tests** for the 4 fixes — currently test cases are
   documented but not implemented as C++ unit tests.

4. **Consider stagnation implementation** if late-game draw scenarios become problematic
   for training data quality.

---

## Deliverables Index

| Phase | File | Content |
|---|---|---|
| 1 | `P0_1_phase_transition_state_machines.md` | State machine diagrams, 12 differences |
| 1 | `P0_2_status_reset_scan.md` | All status changes, 9 anomalies |
| 1 | `P0_3_swoosh_beginTurn_timeline.md` | Turn transition timeline, 9 differences |
| 2 | `A0_phase_transition_sequence.md` | Phase transitions audit (7 checks) |
| 2 | `A1_blocking_eligibility.md` | Blocking chain audit (6 checks) |
| 2 | `A2_chill_freeze_formula.md` | Chill formula 4-case mathematical proof |
| 2 | `A3_wipeout_breach.md` | Wipeout/breach audit (5 checks) |
| 2 | `A4_damage_application.md` | Damage application audit (3 checks) |
| 2 | `A5_game_over_conditions.md` | Game-over conditions audit (3 checks) |
| 3 | `B1_script_execution_ordering.md` | Script ordering audit (5 checks) |
| 3 | `B2_B3_B4_resources_ability_snipe.md` | Resources, abilities, snipe (12 checks) |
| 3 | `B5_B6_B7_sellable_stagnation_death.md` | Sellable, stagnation, death (11 checks) |
| 3 | `B8_legal_action_generation.md` | Legal action generation (13 action types) |
| 3.5 | `Phase3_5_cardLibrary_parity.md` | cardLibrary.jso parsing parity (20+ fields) |
| 5 | `C1_C5_P2_sweep.md` | P2 edge cases (5 areas) |
| — | `AUDIT_SUMMARY.md` | This document |
