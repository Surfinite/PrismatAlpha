# Meta-Review: PrismatAI Training Plan V3

**Plan:** PrismatAI Training Plan V3 — Supervised learning on ~103K human expert replays to train a neural evaluation function for Alpha-Beta HPS search, targeting >50% win rate vs MasterBot.

**Reviews analyzed:** 3 (main) + 2 (symmetry augmentation follow-up)
**Date:** 2026-03-09

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|----------|-----------|----------------|----------------|
| **R1** | Strongly positive — "ready to implement after addressing three blocking concerns" | Label/mirror symmetry, C++ scaling, mid-turn evaluation, inference benchmarking | Card-set holdout test (reserve ~10% of unit types for unseen-combination testing) |
| **R2** | Strongly positive — "ready to execute," "one of the most thorough I've seen" | Active player encoding consistency, gradient suppression from stacked weighting, data loader verification | Player-heldout diagnostic split (740 players = style memorization risk) |
| **R3** | Positive — "good plan, would approve after fixing 3-4 issues" | Loss/output stack inconsistency, offline metrics vs playing strength, long-game overrepresentation, policy head action target | Per-game correlation reducing effective sample size; mini-arena in Phase 3; neutral 0.5-prior as cleaner soft-label baseline |

---

## A.2 — Consensus Points (2+ reviewers)

Ranked by number of reviewers raising the issue:

### All 3 reviewers

1. **Active player / value target encoding must be explicitly specified and verified across all three codebases (JS, Python, C++).** R1 calls it a "critical logical flaw," R2 calls it a "blocking concern," R3 proposes side-to-move canonicalization. **Codebase verdict:** C++ uses absolute player numbering (P0 = Player_One, P1 = Player_Two) with active_player as a separate flag. This is confirmed in `NeuralNet.cpp:283-285`. The plan must document this convention and ensure JS/Python match.

2. **Mixup augmentation on discrete game states is questionable.** All three are skeptical — "2.3 Tarsiers" is not a valid state. R1: "lower priority than other regularization." R2: "I'd predict it hurts or is neutral." R3: "I would deprioritize mixup early." **Recommendation:** Downgrade from default regularization to low-priority optional ablation.

3. **Inference benchmark must measure actual search depth at realistic think times, not just raw evals/sec.** R1: "measure effective search depth." R2: "measure actual nodes searched at 3s and 7s." R3: "benchmark inference in the actual search loop." **Recommendation:** Phase 0e must include search-depth-at-think-time measurements.

### 2 of 3 reviewers

4. **Loss/output/activation stack inconsistency is a real risk.** R1 flags the x100 scaling; R3 identifies the tanh/BCE/probability triple as inconsistent and proposes two canonical paths. **Codebase verdict:** Current C++ uses `tanhf()` → [-1,1] scaled by ×100. Current training code uses MSE on [-1,1]. The plan proposes BCE on [0,1] — this IS inconsistent with the existing codebase. Must pick one canonical path.

5. **Offline validation loss alone is insufficient for model selection — add play testing in Phase 3.** R3 proposes a mini-arena (64-128 paired games). R2 agrees that tournament win rate is the real metric. **Recommendation:** Add cheap mini-arena to Phase 3e decision gate.

6. **Resignation handling needs a stronger default.** R1: "trim last N positions, always apply." R3: "heteroscedastic label noise correlated with player identity." Both say measure-and-report isn't enough.

7. **Rare-unit handling needs training-time mitigation, not just reporting.** R3 explicitly proposes unit-aware oversampling. R1 implicitly through card-set stratified evaluation.

8. **Canonical test states / tactical regression suite for verification.** R2: "10 canonical test states, not just 1." R3: "20-50 known positions with expected qualitative behavior."

9. **Data loader / feature extraction parity needs explicit verification.** R2: "three-way parity test (JS→Python→C++)." R3: "no plan for monitoring training data loader correctness."

10. **Residual MLP preferred at 4+ layers, plain MLP fine at 2-3.** R2 and R3 agree. Both recommend plain 2-layer baseline + 4-block residual as main contender.

---

## A.3 — Outlier Points (single reviewer, with merit assessment)

| Point | Reviewer | Merit | Notes |
|-------|----------|-------|-------|
| Card-set holdout (reserve ~10% of unit types for unseen-combination test) | R1-E | **High** | Tests generalization to unseen units — directly relevant to deployment |
| Curriculum learning on game phase (train on late-game first) | R1-I | Medium | Interesting but adds complexity; temporal weighting (Strategy B) partially addresses this |
| Attention mechanism for card-set encoding | R1-J | Low for V1 | Medium-term idea; Option 4 in the plan already covers this direction |
| Feature importance analysis (SHAP/permutation) after Phase 3 | R1-K | Medium | Useful diagnostic, low effort |
| Player-heldout diagnostic split | R3-M2 | **High** | 740 players = real memorization risk; cheap to implement |
| Recency weighting ablation | R3-D6 | Medium | Game is dead (meta frozen), but still captures style evolution |
| Neutral 0.5-prior as label strategy baseline | R3-D2 | **High** | Simpler than Elo-interpolated, avoids injecting player-skill info into targets |
| Per-game inverse-length weighting | R3-B3 | **High** | Long games dominating gradients is a real statistical concern |
| Fixed-epoch ablations instead of wall-clock | R2-2A, R3 | Medium | Valid argument that training cost is one-time; inference speed is separate constraint |
| Draw rate measurement | R2-3A | Low-Medium | Draws are rare in Prismata but worth measuring |
| SteamAI determinism check | R1-M | Medium | If deterministic, paired matches produce correlated results |
| Historical ability changes beyond cost/rarity | R3-M6 | Low | Extraction-time engine validation catches these |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewer(s) | Codebase Check | Analysis |
|----------|-------------|----------------|----------|
| Side-to-move canonicalization (current player in P0 slots) | R3-D1 | C++ uses absolute P0/P1 (`NeuralNet.cpp:283-285`). Changing would require C++ modifications. | **Not recommended as default** — would break existing C++ inference. Worth one ablation in Python-only Phase 3 to see if it helps, but deployment requires matching C++. |
| Residual 4-block as main contender, plain 2-layer baseline | R2, R3 | C++ already supports residual blocks with LayerNorm (`NeuralNet.cpp:146-154, 442-459`). Training code already uses residual connections (`train.py:140`). | **Agree.** Both C++ and Python already implement this. Make it the recommended default comparison. |
| BatchNorm vs LayerNorm | R2 | C++ uses LayerNorm in residual blocks. | **LayerNorm confirmed correct.** No change needed. |

### ⚠️ Risks & Concerns

| Feedback | Reviewer(s) | Codebase Check | Analysis |
|----------|-------------|----------------|----------|
| Loss/output stack inconsistency (tanh vs BCE vs probability) | R1-B, R3-B1 | C++ uses `tanhf()` → [-1,1] × 100.0 (`Eval.cpp:78`). Current `train.py` uses MSE on [-1,1] (`train.py:169`). Plan proposes BCE on [0,1]. | **CONFIRMED REAL.** Must pick one path. R3's Path A (train in logit space, convert at export) is cleanest. Must-do change. |
| C++ x100 scaling produces "201 distinct integer values" | R1-B | `Eval.cpp:78` returns `double`, not `int`. Alpha-beta uses `double` comparisons throughout (`StackAlphaBetaSearch.cpp`). | **INVALID.** R1 assumes integer truncation that doesn't exist. The x100 factor preserves full double precision (~15 significant digits). The plan's suggestion to consider x10000 for alpha-beta compatibility is reasonable but NOT blocking. |
| Mid-turn evaluation risk | R1-C | `MoveIterator_PPPortfolio.cpp` completes all 4 PP phases before returning. `StackAlphaBetaSearch.cpp:131` only evaluates at terminal/leaf states. No mid-turn eval calls exist. | **INVALID.** Verified: HPS never evaluates mid-turn states. The plan's statement is correct. |
| Mirror label rating assignment bug risk | R2-1A | JS extraction uses `inst.owner === 0/1` for P0/P1 (`state_adapter.js:186`). Ratings come from replay metadata. | **Valid concern.** An integration test (extract same replay with swapped players, verify mirrored pairs match) is cheap and catches real bugs. Should-do. |
| Gradient suppression from stacked weighting | R2-1B | No existing implementation to check; this is about the plan's proposed combination. | **Valid.** Logging effective weight histograms is trivial and catches silent data starvation. Should-do. |
| Active player encoding ambiguity | R2-1C | C++ uses absolute P0=Player_One, P1=Player_Two, active_player as raw flag. Consistent across all three codebases (see Agent 2 findings). | **Valid concern, but codebase is already consistent.** The gap is documentation, not implementation. Must-do to document in schema. |
| Long-game overrepresentation / within-game correlation | R3-B3, R3-M7 | Current `load_selfplay.py` has no per-game weighting (`train.py:519-541` — all records treated equally). | **CONFIRMED REAL.** A 50-turn game contributes 2.5x more gradient than a 20-turn game. Adjacent turns are correlated. Must-do ablation. |
| 102K count provisional | R3-B5 | Plan already says extraction-time validation will exclude failures. | **Agree** — just a caution to note in the plan. |
| Policy head action target underspecified | R3-B4 | C++ policy predicts **buy counts per unit type** (not full move). PUCT sums logits per bought unit in a move (`UCTSearch.cpp:218-230`). `train.py` uses MSE + BCE hybrid on buy counts (`train.py:151-164`). | **Partially addressed by codebase.** The target IS defined (buy counts), but the plan doesn't mention this. The composite-turn concern is real for full-move imitation but doesn't apply to the existing buy-count approach. Should-do: document that policy = buy-count prediction, not full-turn imitation. |

### 🗑️ Suggested Removals / Simplifications

| Feedback | Reviewer(s) | Analysis |
|----------|-------------|----------|
| Deprioritize mixup | R1, R2, R3 | **Agree.** All three skeptical. Downgrade to low-priority optional ablation. |
| Softer/no rating weighting | R3-D4 | **Agree in spirit.** The plan already notes the effect is likely small. Keep as ablation but don't default to quadratic. |
| Temporal split may be unnecessarily pessimistic (dead game) | R2-2D | **Partially agree.** Game meta is frozen, but temporal split is still more conservative. Keep as primary, elevate random-split diagnostic. |

### ➕ Suggested Additions

| Feedback | Reviewer(s) | Priority | Analysis |
|----------|-------------|----------|----------|
| Mini-arena (64-128 paired games) in Phase 3 | R3-B2 | **Must-do** | Offline metrics ≠ playing strength. Cheap insurance. |
| Per-game weighting / inverse-game-length sampling | R3-B3 | **Must-do** | Real statistical bias. Add as Phase 3 ablation. |
| 3-way feature parity test (JS→Python→C++) | R2-G | **Should-do** | Catches silent extraction/serialization bugs. |
| Data loader verification (load → decode → verify) | R2-3C, R3 | **Should-do** | Nets fit garbage silently. |
| Neutral 0.5-prior label strategy as ablation | R3-D2 | **Should-do** | Cleaner than Elo-interpolated, avoids player-skill injection. Add as Strategy D. |
| Effective weight histogram logging | R2-1B | **Should-do** | Trivial, catches data starvation. |
| Canonical test fixtures (10 states) for cross-lang verification | R2-5.3, R3-M5 | **Should-do** | Better than single-state verification. |
| Tactical regression suite (20-50 positions) | R3-M5 | **Should-do** | Fast regression harness for integration changes. |
| V9 failure triage plan | R2-3D | **Should-do** | Prevents open-ended debugging if click protocol fails. |
| Feature extraction bug row in failure modes table | R2-5.4 | **Should-do** | Easy addition, catches real bugs. |
| Reproducibility checklist | R3-S3 | **Should-do** | Standard practice, saves future debugging. |
| Rare-unit-aware sampling | R3-M1 | **Should-do** | Prevents blind spots for infrequent units. |
| Search-position OOD check in Phase 3 | R3-M3 | **Should-do** | Catch distribution shift before full training. |
| Player-heldout diagnostic split | R3-M2 | **Consider** | 740 players = real memorization risk, but secondary diagnostic. |
| Card-set holdout (reserve ~10% unit types) | R1-E | **Consider** | Tests unseen-combination generalization. |
| Recency weighting | R3-D6 | **Consider** | Meta is frozen but styles evolved. |
| Curriculum learning (late-game first) | R1-I | **Consider** | Lightweight, partially addressed by Strategy B. |
| Feature importance (SHAP) after Phase 3 | R1-K | **Consider** | Good diagnostic. |
| Draw rate measurement in Phase 0d | R2-3A | **Consider** | Quick measurement. |
| Pairwise ranking metric | R3-S5 | **Consider** | May correlate with search utility better than BCE. |
| SteamAI determinism check | R1-M | **Consider** | Affects confidence intervals. |

### 🔄 Alternative Approaches

| Feedback | Reviewer(s) | Analysis |
|----------|-------------|----------|
| Fixed-epoch ablations instead of wall-clock | R2-2A, R3 | **Compelling argument.** Training is one-time; inference speed is the real constraint. Recommend: use fixed epochs for architecture comparison, apply inference speed as a separate hard filter. |
| 500 evals/sec floor should be derived from measured search budget | R2-2B | **Agree.** The 500 number is a guess. Derive from actual HPS branching factor measurement. |
| Elo prior may train "probability this human wins" not "value under strong play" | R3-D2 | **Valid concern.** AI won't know player ratings at inference time. Add 0.5-prior as a cleaner alternative ablation. |
| Resignation: player-specific trimming (frequent resigners → trim more) | R3-3F | **Interesting but complex.** Fixed trimming (3-5 turns) is simpler first pass. |

### ✅ Confirmed Good / Keep As-Is

| Element | Confirmed By | Notes |
|---------|-------------|-------|
| Option 2 feature set as starting point | R1, R2, R3 | All agree. Option 1 as baseline is correct. |
| Temporal split as primary | R1, R2, R3 | All endorse (R2 notes dead-game caveat). |
| Paired tournament design | R2, R3 | Halves variance, correct approach. |
| 1,024+ games for primary evaluation | R2, R3 | Sufficient for moderate effects. |
| Schema versioning approach | R2 | Called out as "exactly the right instinct." |
| Failure modes table | R2, R3 | "Excellent" (R2). |
| Symmetry augmentation (true 2x) | R1, R2, R3 | All agree it's free and correct. |
| Opening book as independent component | R3 | Isolate from model selection. |
| MasterBot as primary benchmark | R2, R3 | Meaningful milestone + right primary metric. |
| Residual blocks already in C++ | R2, R3 | No implementation cost. |
| LayerNorm (not BatchNorm) | R2 | Correct for variable-batch C++ inference. |
| Mid-turn state exclusion | Codebase | Verified: HPS never evaluates mid-turn. Plan is correct. |

### 🔧 Implementation Details & Nits

| Feedback | Reviewer(s) | Action |
|----------|-------------|--------|
| `.jso` extension — intentional or typo? | R2-5.2 | **Intentional** — Lunarch's proprietary JSON format. No change. |
| Turn normalization /30 vs REFERENCE_LENGTH 40 — document difference | R2-3B | **Agree.** Add explicit note that these are intentionally different. |
| Standardize naming (MasterBot = opponent, SteamAI = wrapper) | R3-S2 | **Agree.** Quick cleanup. |
| Record count labels (3.1M raw vs 6.2M mirrored) | R3-S1 | **Agree.** Label explicitly. |
| Sokota citation incomplete | R2-5.5 | **Agree.** Fix citation. |
| Game length measurement — promote to Phase 0a subtask | R2-5.1 | **Agree.** It's a single DB query and the record count depends on it. |
| Opening book comparisons must use same book for both candidates | R3-M8, S6 | **Agree.** Already partially in plan, make more explicit. |
| SWA + BCE calibration interaction | R2-3E | **Note only.** Weight averaging + sigmoid nonlinearity affects calibration. Worth documenting. |
| Policy head target = buy counts (already implemented) | R3-B4 | Document in plan. Existing codebase defines this. |

### 📦 Dependencies & Integration

| Feedback | Reviewer(s) | Analysis |
|----------|-------------|----------|
| V9 failure triage plan | R2-3D | No contingency described. Add triage: is the bug in C++ move gen, JS click adapter, or both? |
| Historical ability changes beyond cost/rarity | R3-M6 | Extraction-time engine validation catches these. Low risk. |
| Export must cast to float32 | Plan already covers | R2 confirms. |

### 🔮 Future Considerations

| Feedback | Reviewer(s) | Notes |
|----------|-------------|-------|
| Attention mechanism for card-set encoding | R1-J | Option 4 territory. Future iteration. |
| KataGo multi-target reference | R2-Q3 | Prismata lacks natural score margin. Interesting for self-play phase. |
| TD-style bootstrapping | R3-Q3-D | Both R2 and R3 mention. Deferred to self-play phase. |
| Teacher bootstrapping (two-pass soft labels) | R3-Q3-C | Higher effort, better signal. Future iteration. |

---

## A.5 — Conflicts & Contradictions

### 1. Wall-clock vs fixed-epoch ablation budgets

- **Plan + R1:** Wall-clock is "fairer" (measures quality at same compute cost)
- **R2, R3:** Fixed-epoch is better — training is one-time, inference speed is the real constraint

**Recommendation:** R2/R3 are right. What matters is which architecture *learns best* and which architecture *infers fastest* — these are separate questions. Use fixed epochs (e.g., 30 with early stopping) for architecture comparison, then apply the Phase 0e inference speed constraint as a hard filter. Document both validation-loss-at-epoch-N and validation-loss-at-time-T.

### 2. Elo-interpolated labels (Strategy C) — useful or risky?

- **Plan:** Strategy C is a primary ablation candidate
- **R2:** Predicts Strategy B (temporal weighting) will tie or beat C
- **R3:** Prefers neutral 0.5-prior; worried Elo prior trains "probability this human wins" not "value under strong play"

**Recommendation:** Keep Strategy C as an ablation but add R3's neutral 0.5-prior as **Strategy D** (simpler, avoids player-skill injection). R3's concern is valid: the deployed evaluator won't know player ratings. The 0.5-prior captures the same early-game uncertainty without the Elo dependency. Run all four strategies (A, B, C, D) in the label ablation.

### 3. Mixup augmentation — worth trying?

- **Plan:** Default regularization technique
- **R1, R2, R3:** All skeptical for discrete game states

**Recommendation:** Unanimous skepticism is strong signal. Downgrade to optional low-priority ablation. Prioritize dropout, weight decay, SWA, and per-game sampling first.

### 4. Rating-based sample weighting — quadratic or simpler?

- **Plan:** Quadratic weighting `((sum/4000)**2)`
- **R3:** Prefers linear, clipped, or no weighting

**Recommendation:** Plan already notes the effect is likely small (98.8% of games have weight >=0.64). Keep as an ablation with simpler alternatives (linear, none). Don't default to quadratic.

### 5. 500 evals/sec floor — derived or arbitrary?

- **Plan:** 500 evals/sec as a heuristic floor
- **R2, R3:** Should be derived from actual search budget at target think time

**Recommendation:** R2/R3 are right. Measure actual nodes searched at 3s/7s with a constant evaluator, then derive the floor from `search_budget / think_time`.

---

## A.6 — Recommended Plan Changes

### Must-Do (high consensus or addresses real risks)

1. **Specify canonical loss/output path.** Train in logit/probability space (BCE), convert to tanh at export. Document the full stack: model outputs raw logit → training uses `BCEWithLogitsLoss` → export applies `tanh(logit)` → C++ scales by ×100 or ×10000. *(R1-B, R3-B1)*

2. **Document value target as "probability P0 wins" with P0 = Player_One (absolute index), not active player.** Add to `schema_v1.json`. Verify all three codebases use the same convention (codebase check confirms they already do). *(R1-A, R2-1C, R3-D1)*

3. **Add per-game weighting / inverse-game-length sampling as Phase 3 ablation.** Long games silently dominate gradients. Options: weight by `1/total_turns`, cap per-game contribution, or sample uniformly by game then by turn. *(R3-B3)*

4. **Add mini-arena (64-128 paired games) to Phase 3e decision gate.** Every serious architecture candidate gets a cheap play test before full training. Offline loss alone doesn't predict playing strength. *(R3-B2)*

5. **Expand Phase 0e to benchmark actual search depth at 3s and 7s think times.** Measure nodes searched, not just evals/sec. Derive the inference speed floor from the actual HPS branching factor. *(R1-D, R2-2B, R3-M4)*

6. **Downgrade mixup from default regularization to optional low-priority ablation.** Unanimous reviewer skepticism for discrete game states. *(R1-H, R2-2C, R3-D3)*

### Should-Do (strong suggestions that meaningfully improve the plan)

7. **Add neutral 0.5-prior as Strategy D in the label ablation.** `label = (1-t) * 0.5 + t * outcome`. Simpler than Elo-interpolated, avoids injecting player-skill information. *(R3-D2)*

8. **Add 3-way feature parity test (JS→Python→C++) in Phase 2d.** Same game state must produce identical feature vectors across all three. *(R2-G)*

9. **Add data loader verification step.** Load 100 records via training pipeline, decode back to human-readable features, verify against extraction output. *(R2-3C, R3)*

10. **Add canonical test fixture set (10 diverse states) for cross-language verification.** Opening, mid-game, late-game near-lethal, empty board, etc. Store as fixtures. *(R2-5.3, R3-M5)*

11. **Add tactical regression suite (20-50 known positions) for fast sanity checks.** Forced lethal, obvious defense, clearly dominant buy, mirror-symmetric, free-resource probes. *(R3-M5)*

12. **Move search-position OOD check from Phase 5 to Phase 3.** Run on 200+ positions during architecture search. Catches distribution shift early. *(R3-M3)*

13. **Log effective weight distributions when combining weighting schemes.** Verify >=80% of samples have weight >0.3. *(R2-1B)*

14. **Add rare-unit-aware sampling as Phase 3 ablation.** Oversampling or card-set-stratified batch sampling for games containing low-frequency units. *(R3-M1)*

15. **Add V9 click-protocol failure triage plan.** If `skippedBuys` appear: is the bug in C++ move generation, JS click adapter, or state deserialization? Document triage steps. *(R2-3D)*

16. **Add feature extraction bug row to failure modes table.** Detection: per-feature mean/std with zero variance or implausible statistics. *(R2-5.4)*

17. **Document policy head target as buy-count prediction.** The codebase already implements this (`train.py:151-164`, `UCTSearch.cpp:218-230`). The plan should state it explicitly to prevent confusion about "full-turn imitation." *(R3-B4)*

18. **Add reproducibility checklist.** Log: schema hash, code commit, split manifest, random seed, opening-book setting, search params, normalization constants, model export checksum. *(R3-S3)*

19. **Use fixed epochs for Phase 3 architecture comparison, not wall-clock.** Apply inference speed constraint as a separate hard filter from Phase 0e. *(R2-2A, R3)*

20. **Standardize naming.** MasterBot = opponent, SteamAI = integration wrapper. Label record counts explicitly (3.1M raw / ~6.2M after mirroring). *(R3-S1, S2)*

21. **Add integration test for mirror label correctness.** Extract 100 replays normally and with P0/P1 swapped at replay level; verify identical mirrored pairs. *(R2-1A)*

22. **Document turn normalization /30 vs REFERENCE_LENGTH 40 as intentionally different constants.** *(R2-3B)*

23. **Add resignation trimming default.** If >5% of games end by resignation, trim last 3-5 pre-resignation positions from training by default. Run one ablation without trimming. *(R1-F, R3-3F)*

### Consider (good ideas, not critical — presented as pick list in updated plan)

24. Player-heldout diagnostic split *(R3-M2)*
25. Card-set holdout test (reserve ~10% of unit types) *(R1-E)*
26. Recency weighting ablation *(R3-D6)*
27. Curriculum learning on game phase *(R1-I)*
28. Feature importance analysis (SHAP/permutation) after Phase 3 *(R1-K)*
29. Draw rate measurement in Phase 0d *(R2-3A)*
30. Pairwise ranking metric logged during training *(R3-S5)*
31. SteamAI determinism check *(R1-M)*
32. Side-to-move canonicalization ablation *(R3-D1)*
33. Softer rating weighting alternatives (linear, clipped, none) *(R3-D4)*
34. Fixed-epoch ablations report both loss-at-epoch and loss-at-time *(R2 supplement)*

### Reject (with reason)

- **R1-B: "201 distinct integer values" in alpha-beta.** REJECTED. Codebase uses `double` throughout (`Eval.cpp:78` returns `double`, `StackAlphaBetaSearch.cpp` compares `double`). No integer truncation occurs. The x100 scaling preserves full floating-point precision. The plan's suggestion to consider x10000 scaling for alpha-beta compatibility is kept as a future consideration, not a blocking concern.

- **R1-C: Mid-turn evaluation risk.** REJECTED. Verified: `MoveIterator_PPPortfolio.cpp` completes all 4 PartialPlayer phases before returning child states. `StackAlphaBetaSearch.cpp:131` only evaluates terminal/leaf states. HPS never calls the evaluator on mid-turn positions.

- **R3-D2: Remove Elo-interpolated labels entirely.** REJECTED as stated — but the recommendation to add a neutral 0.5-prior alternative is accepted. Keep Elo-interpolated as one of four ablation candidates (A, B, C, D); don't pre-select or pre-reject any.

---

## A.8 — Post-Review Amendment: Symmetry Augmentation (R4/R5)

Two additional reviewers were consulted specifically on mirror augmentation after the user identified that Prismata has **asymmetric starting positions** (P0: 6 Drones, P1: 7 Drones). Both reviewers agreed the "free 2x data" claim was incorrect:

- **R4:** Recommends turn-gated mirroring (only after turn 8-10) or ablation. The early-game noise from impossible states is real but mid/late-game mirroring is approximately valid.
- **R5:** More aggressive — recommends removing mirror augmentation entirely from V1 and switching to active-player-relative encoding.

**Decision:**
- Mirror augmentation **removed from the default pipeline**
- Added as a **Phase 3 ablation** with three variants: no mirroring (baseline), turn-gated (turns 8-10+), full (to quantify damage)
- **Kept absolute P0/P1 encoding** — switching to active-player encoding would contradict the schema decision (Must-do #2), require C++ changes, and lose its primary motivation (making mirroring structurally simpler) now that mirroring is no longer default
- Added `ply_index` (half-turn index) as a metadata field for more precise tempo tracking
- The "Symmetry augmentation" was the only item in A.7 (What Stays) that was overturned by post-review analysis

---

## A.7 — What Stays

The following elements were confirmed as solid by multiple reviewers and should remain unchanged:

- **Option 2 feature set** (type-count + instance flags + supply + card-set indicator) as the starting point, with Option 1 as Phase 3a baseline
- **Temporal split** as primary train/val/test partitioning, with random-split diagnostic
- **Paired tournament design** (same card set, swapped players) for variance reduction
- **1,024+ games** for primary Phase 5 evaluation, with extension protocol for borderline results
- **Schema versioning** with JSON file, hash in headers
- **Failure modes table** — reviewers called it "excellent"
- ~~**Symmetry augmentation**~~ — *overturned by R4/R5 post-review (see A.8). Seat asymmetry makes naive mirroring incorrect for early-game positions. Now a Phase 3 ablation, not a default.*
- **Opening book** as independent component, evaluated with/without
- **MasterBot via SteamAI** as primary benchmark
- **Residual block support** in C++ inference — no implementation cost
- **LayerNorm** (not BatchNorm) for C++ inference compatibility
- **Mid-turn state exclusion** — verified correct against codebase
- **Phase 0b benchmark tournament** design
- **Phase 2a extraction pipeline** architecture (fetch → engine-step → featurize → shard)
- **Phase 2d post-extraction validation** framework (augmented with new tests)
- **Known limitation section** on distribution shift
- **Phase 6 self-play outline** for future work
- **Deferred enhancements** section (pairwise ranking loss)
