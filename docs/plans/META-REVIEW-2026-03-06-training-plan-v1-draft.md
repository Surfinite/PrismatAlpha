# Meta-Review: PrismatAI Training Plan V1 Draft

**Date:** 2026-03-07
**Plan reviewed:** `docs/plans/2026-03-06-training-plan-v1-draft.md`
**Reviews ingested:** 7
**Reviewer context document:** `docs/plans/TrainingPlanBlurb.txt`

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Mostly positive, methodologically rigorous | Start-of-turn-only states; Elo labels as ablation not default; card-set holdout split; paired tournaments | Calibration as first-class architecture criterion; SPRT sequential testing |
| R2 | Mostly positive, detail-oriented | Active-player-relative encoding; `total_turns` label leakage; BCE over MSE; temporal split; feature normalization | First-player advantage adjustment to Elo prior; SWA; Mixup augmentation; schema checksum in filenames |
| R3 | Mixed, strong methodological concerns | Distribution shift at search leaves; property-based encoding (Option 4); permutation augmentation; SIMD/batched inference | Option 4 as the long-term answer; permutation augmentation for random-pool units |
| R4 | Mostly positive | Soft-label causality direction; supply remaining blocking; 1K-2K game tournaments; EMA checkpoint averaging | Elo prior may be predictive at turn 1 (not just 0.5); outcome blurring (Gaussian kernel) |
| R5 | Mostly positive, infrastructure-focused | Record granularity cascading; label smoothing + Elo redundancy; temporal split; turn number feature; inference normalization consistency | JSONL too slow — use HDF5/memmap; pre-norm ResBlock placement; Kendall's τ on late-game positions; wall-clock budget for ablations |
| R6 | Very positive | Supply remaining "most important missing feature"; turn-level correlation; mirror correctness test; calibration for search; policy head underestimated | Huber loss; action availability features (buyable/affordable flags); permutation importance/SHAP; FP16 inference |
| R7 | Mostly positive | Engine validation sample size; `total_turns` documentation; symmetry split ordering; Mixup augmentation; secondary eval metrics | Exponential decay label formula; sigmoid rating weight; Polyak checkpoint averaging; Bayes factor; "Failure Modes" section |

---

## A.2 — Consensus Points (agreement across multiple reviewers)

Ranked by number of reviewers raising the point:

| # | Point | Reviewers | Count |
|---|---|---|---|
| 1 | **Supply remaining must be in the default feature schema** | R1, R2, R3, R4, R5, R6, R7 | 7/7 |
| 2 | **Feature normalization strategy must be specified explicitly** | R1, R2, R4, R5, R6 | 5/7 |
| 3 | **Temporal split should be primary (or at least tested)** | R1, R2, R4, R5 | 4/7 |
| 4 | **512 games insufficient — need 1,000-2,000 for reliable eval** | R1, R3, R4, R5, R7 | 5/7 |
| 5 | **Turn number / game phase should be a feature** | R1, R5, R6 | 3/7 |
| 6 | **Distribution shift between training positions and search positions** | R1, R3, R4, R7 | 4/7 |
| 7 | **`total_turns` in label formula encodes outcome-correlated info** | R1, R2, R3, R5, R7 | 5/7 |
| 8 | **BCE is more principled than MSE for soft probability targets** | R1, R2, R4, R5 | 4/7 |
| 9 | **Elo-interpolated labels should be ablated, not assumed default** | R1, R2, R3, R4 | 4/7 |
| 10 | **Mirror augmentation needs correctness test: mirror(mirror(x)) == x** | R1, R2, R5, R6 | 4/7 |
| 11 | **Record granularity (per-turn vs per-action) must be resolved** | R1, R5, R3 | 3/7 |
| 12 | **Card-set leakage — track seen vs unseen set performance** | R1, R4, R6, R7 | 4/7 |
| 13 | **Checkpoint averaging (SWA/EMA/Polyak)** | R2, R4, R5, R7 | 4/7 |
| 14 | **Policy head should be medium priority, not optional** | R3, R6, R7 | 3/7 |
| 15 | **Label smoothing + Elo soft labels are redundant** | R1, R5 | 2/7 |
| 16 | **Mixup augmentation for data efficiency** | R2, R5, R7 | 3/7 |
| 17 | **Draws/timeouts/resignations handling** | R3, R4, R5 | 3/7 |
| 18 | **Search-in-the-loop benchmark, not just offline metrics** | R1, R6, R7 | 3/7 |

---

## A.3 — Outlier Points (raised by only one reviewer)

| Point | Reviewer | Merit Assessment |
|---|---|---|
| **Option 4 (property-based encoding) as long-term direction** | R3 | **High merit.** Solves rare-unit sparsity and generalizes to balance patches. But correctly scoped as future work — too complex for V1. |
| **Permutation augmentation for random-pool unit ordering** | R3 | **Low merit for Option 2.** With fixed 116-slot encoding, unit order is already canonical. Only relevant for Option 4-style variable-slot encoding. |
| **Huber loss instead of MSE** | R6 | **Moderate merit.** Handles outlier labels more gracefully. Worth a Phase 3 ablation slot but not blocking. |
| **Action availability features (buyable/affordable flags)** | R6 | **High merit.** Directly encodes strategic information. Worth adding to Option 2 schema. |
| **First-player advantage adjustment to Elo prior** | R2 | **High merit.** P2 wins 57.3% in self-play data (CLAUDE.md). Human data will show asymmetry too. Easy fix. |
| **Gaussian "outcome blurring" soft labels** | R4 | **Low merit.** More complex than alternatives with no clear advantage over fixed-reference-length interpolation. |
| **JSONL too slow — use HDF5/memmap** | R5 | **Validated by codebase.** The existing selfplay pipeline uses binary shards + memmap (`load_selfplay.py`). JSONL at 6.2M records would be very slow. Recommend binary format. |
| **Pre-norm ResBlock placement** | R5 | **Contradicted by codebase.** Current C++ NeuralNet.cpp uses post-norm (norm after each linear). Changing would require C++ changes. Not worth it for V1. |
| **SIMD/BLAS for C++ inference** | R3 | **Moderate merit but out of scope.** Current C++ uses naive loops. SIMD would help but is an optimization task, not a training plan concern. |
| **FP16 inference in C++** | R6 | **Low priority.** x86 FP16 support is limited (no native half-precision ALU on most CPUs). Not practical without GPU inference. |
| **Exponential decay label formula** | R7 | **Moderate merit.** Shorter games resolve uncertainty faster. Worth testing as a Phase 3 ablation variant. |
| **SHAP/permutation importance post-training** | R6 | **Moderate merit.** Good diagnostic but not a training plan concern — it's a post-hoc analysis tool. |
| **Bayes factor alongside Wilson CI** | R7 | **Low merit.** Wilson CI is standard and well-understood. Adding Bayesian analysis adds complexity without changing decisions. |
| **Sequential SPRT testing** | R1 | **Moderate merit.** More efficient than fixed game counts. But adds implementation complexity. Consider for future iterations. |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewer(s) | Codebase Reality Check | Analysis |
|---|---|---|---|
| **Supply remaining in feature schema** | All 7 | **ALREADY IN C++ CODE.** `NeuralNet.cpp:350-351` encodes `P0 supply` and `P1 supply` per unit (feature indices 8,9). Also has `in_card_set` flag (index 10). | The C++ inference engine already supports this. The plan's Option 2 lists only 5 features per unit, but the C++ already uses 11. The plan should be updated to match reality. |
| **Turn number as feature** | R1, R5, R6 | **ALREADY IN C++ CODE.** `NeuralNet.cpp:383-384` encodes `turn_number / 30.0` as global feature 12. Active player is global feature 13. | Already implemented. Plan should document this as part of the schema. |
| **Feature normalization** | R1, R2, R4, R5, R6 | **ALREADY IN C++ CODE.** `NeuralNet.cpp:367-384` uses `clamp_divide` normalization with specific caps (gold/20, blue/5, red/5, green/15, energy/10, attack/25, turn/30). | Already implemented with specific cap values. The JS extraction pipeline must use identical caps. Plan should document the normalization constants explicitly. |
| **Active-player-relative encoding** | R2 | C++ encodes P0 features first (offset 0), P1 features second (offset 4), with `active_player` as a separate global feature. This is canonical P0/P1 encoding, NOT active-player-relative. | R2's suggestion to use active-player-relative encoding would conflict with the existing C++ implementation. The current approach (canonical P0/P1 + active_player flag) is valid and already deployed. Symmetry augmentation (swap P0/P1 blocks, invert label) is the correct way to handle this. |
| **BCE vs MSE for soft labels** | R1, R2, R4, R5 | No loss function is hardcoded in C++ (inference only). Training loss is a Python-side choice. | Valid ablation. BCE is theoretically cleaner for probability estimation. Worth testing in Phase 3. |
| **ResBlock placement (pre-norm vs post-norm)** | R5 | C++ uses post-norm: `relu(fc1) → norm1 → relu(fc2) → norm2 → residual add` (NeuralNet.cpp:499-515). | Changing to pre-norm would require C++ inference changes. Stay with post-norm for V1. |
| **LayerNorm overhead in C++** | R2 | C++ already has `layerNormForward()` (NeuralNet.cpp:442-459). It's a simple mean/var computation. | Already implemented. The overhead is minimal at these dimensions (256-512). Not a concern. |
| **Residual MLP architecture** | R1, R3, R5, R6 | C++ trunk is already residual blocks with dual LayerNorm. Fully deployed and working. | The plan correctly identifies residual blocks as a variant to test. The C++ infrastructure is already in place. |
| **Option 4 (property-based encoding)** | R3 | Would require a completely different feature extraction approach. Not compatible with current C++ 116-slot fixed encoding. | Interesting long-term direction but correctly scoped as future work in the plan. |

### ⚠️ Risks & Concerns

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **`total_turns` leakage in label formula** | R1, R2, R3, R5, R7 | **Strong consensus, valid concern.** `total_turns` is outcome-correlated — short games are stomps. Using it to scale `t` means the label schedule itself encodes future information. **Fix: use a fixed reference length** (e.g., `t = min(1.0, turn_number / 40)` where 40 ≈ 75th percentile game length). This eliminates the leakage while preserving the temporal interpolation. |
| **Distribution shift at search leaves** | R1, R3, R4, R7 | Valid long-term concern. The model sees expert human positions in training but AI-generated positions at inference. **Cannot be fully solved in supervised learning** — this is the fundamental motivation for Phase 6 (self-play). The plan should acknowledge this explicitly as a known limitation. |
| **Record granularity ambiguity** | R1, R3, R5 | The plan says "one record per player-turn" (Phase 2a) but also mentions "mid-turn states" (Phase 1a Option 1 note). **This must be resolved.** Start-of-turn-only is the safe, defensible choice for V1. |
| **Label smoothing + Elo soft labels redundancy** | R1, R5 | Valid. Both soften targets. Using both may over-smooth, especially late-game positions where hard outcomes are the correct signal. **Fix: if Elo-interpolated labels are used, skip separate label smoothing.** |
| **Card-set leakage / memorization** | R1, R4, R6, R7 | Valid diagnostic concern. Some card sets will dominate training. **Add to Phase 5: report eval metrics stratified by seen vs unseen card sets.** |
| **Forfeit/timeout label validity** | R4, R5 | Replays include forfeit and timeout games where the label may be misleading. **Investigate during Phase 0d audit.** |
| **Engine validation sample size** | R7 | Currently 500 replays with "run 1,000+" as a V4 verification. R7 argues for 5,000+. Given that each replay passes through the engine during extraction anyway, **validate all replays during extraction** (log any failures). |
| **Mirror augmentation correctness** | R1, R2, R5, R6 | Add `mirror(mirror(x)) == x` unit test and `label_original + label_mirror ≈ 1.0` check. Simple and catches bugs. |
| **Elo prior direction** | R4 | Interesting point: if Elo predicts early-game advantage accurately, interpolating FROM Elo TOWARD outcome is the wrong direction — it adds noise. **Empirical check needed:** measure Elo-vs-WR correlation by turn bucket. |

### 🗑️ Suggested Removals / Simplifications

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **Drop separate label smoothing if using Elo soft labels** | R1, R5 | Agree. Redundant double-smoothing. Remove label smoothing from Phase 4b when Elo-interpolated labels are active. |
| **Simplify rating weight formula** | R4, R5, R7 | Current `((sum/4000)**2)` is unintuitive and produces weights >1.0 for high-rated games. However, with 98.8% of games having combined rating ≥3200 (weight ≥0.64), the effect is minimal. **Keep simple or drop entirely** — the natural distribution already heavily favors high-rated games. Make this a Phase 3 ablation. |
| **Drop symmetry augmentation as explicit step** | R2 | If using canonical P0/P1 encoding (which we are — confirmed in C++), symmetry augmentation IS needed and produces genuine 2× data. R2's alternative (active-player-relative) would eliminate the need, but conflicts with existing C++ encoding. **Keep augmentation.** |

### ➕ Suggested Additions / Features

| Feedback | Reviewer(s) | Priority | Analysis |
|---|---|---|---|
| **Store `card_set` (8 unit IDs) in each record** | R2, R5, R7 | High | Enables post-hoc stratified analysis. Trivial to add. |
| **Store `game_date` in each record** | R5 | Medium | Enables temporal split and retroactive filtering. Small field. |
| **Action availability features (buyable, affordable)** | R6 | Medium | Adds strategic information. But increases feature complexity. Consider for V2. |
| **Turn-bucketed evaluation metrics** | R1, R5 | High | Report val loss by turn quartile (opening/mid/late). Catches phase-specific failures. |
| **"Failure Modes" section in plan** | R7 | Medium | Mode collapse, overfitting to early game, card-set memorization. Good documentation. |
| **Phase 3 decision rule for ambiguous results** | R5 | Medium | What if results are contradictory? Define tie-breaking criteria. |
| **Move agreement metric** | R2, R7 | Medium | How often does neural-guided AI choose same move as expert? Useful diagnostic. |
| **Mixup augmentation** | R2, R5, R7 | Medium | Cheap, effective for tabular regression. Worth a Phase 3 ablation. |
| **Checkpoint averaging (SWA/EMA/Polyak)** | R2, R4, R5, R7 | Medium | Nearly free, often improves robustness. Add to Phase 4. |

### 🔄 Alternative Approaches

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **Temporal sample weighting instead of soft labels** | R1, R3, R6 | Keep hard 0/1 labels but weight loss by `0.3 + 0.7 × (turn/ref_length)`. Simpler, avoids Elo bias concerns. **Run as Phase 3 ablation alongside Elo-interpolated labels.** |
| **Fixed reference length for `t` calculation** | R1, R2, R7 | `t = min(1.0, turn_number / 40)` instead of `turn_number / total_turns`. Eliminates outcome-correlated leakage. **Must-do fix.** |
| **Exponential/quadratic/sigmoid ramp instead of linear** | R2, R6, R7 | `t**2` or sigmoid ramp concentrates label authority in late game. Worth testing. **Phase 3 ablation.** |
| **TD(λ) bootstrapped labels** | R1, R5, R7 | Train initial model → use its predictions as soft labels for second pass. Higher ceiling but requires iterative pipeline. **Consider for Phase 6.** |
| **Wall-clock budget for ablations instead of fixed epochs** | R2, R5 | Fairer comparison across model sizes. **Agree — adopt wall-clock budget.** |
| **Temporal train/test split** | R1, R2, R4, R5 | Most recent 10% test, next 10% val. Better reflects deployment. **Adopt as primary split with random split as secondary diagnostic.** |

### ✅ Confirmed Good / Keep As-Is

| Feedback | Reviewer(s) |
|---|---|
| **Option 2 as starting point** | All 7 |
| **Phased approach with verification gates** | R4, R5, R6, R7 |
| **Clean restart with validated JS engine** | R5, R7 |
| **Balance validation thoroughness** | R5 |
| **Churchill baseline as lower bound (Phase 3a)** | R2, R3, R5, R7 |
| **Base-only game exclusion** | All who mentioned it |
| **Opening book extraction from training data only** | R2, R4 |
| **Dropout + weight decay + early stopping for regularization** | R1, R6 |
| **MCDSAI as primary benchmark (with caveats)** | R1, R3, R6, R7 |
| **Split by replay code to prevent game-level leakage** | R1, R2 |

### 🔧 Implementation Details & Nits

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **JSONL will be too slow at 6.2M records** | R5 | Valid. Existing selfplay pipeline uses binary shards. JS extraction should output binary or HDF5, not JSONL. |
| **Phase 0e should include residual MLP variants** | R2 | Already planned in Phase 3c. Add residual configs to Phase 0e speed benchmark for completeness. |
| **Schema checksum in output filenames** | R2 | Nice-to-have. Prevents schema mixing. Low effort. |
| **Extraction parallelization (embarrassingly parallel)** | R7 | Each replay is independent. 8 workers → ~2 hours instead of ~14. Worth noting in Phase 2a. |
| **Version training runs with unique IDs** | R7 | Already done in the existing pipeline (`training/runs/` with timestamps). Note in plan. |
| **Phase 0e: benchmark at realistic think times** | R5 | Good addition — measure actual search depth at 3s/7s, not just raw evals/sec. |

### 📦 Dependencies & Integration

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **C++ weight export must include normalization constants** | R2, R5 | **Already handled.** C++ hardcodes normalization caps (gold/20, blue/5, etc.) in `NeuralNet.cpp`. The JS extraction must use identical caps. Export the caps in `schema_v1.json`. |
| **Smoke test: same state evaluated in Python and C++ must match** | R2, R5 | Essential. Already partially implemented (export_weights.py has verification). Add explicit cross-language test. |
| **26 tensors required by C++ loader** | Plan already states this | Confirmed in NeuralNet.cpp — input_proj + N×(linear1,norm1,linear2,norm2) + policy(2) + value(2). |

### 🔮 Future Considerations

| Feedback | Reviewer(s) | Analysis |
|---|---|---|
| **Self-play to address distribution shift** | R1, R3, R4, R7 | Already planned as Phase 6. Reviewers confirm it's necessary. |
| **Option 4 (property encoding) for long-term** | R3 | Interesting but correctly deferred. |
| **TD(λ) bootstrapped labels** | R1, R5, R7 | Best for Phase 6 / iteration 2. |
| **SIMD-optimized inference** | R3 | Out of scope for training plan but worth noting. |
| **Leaf-node batching in search** | R3 | Significant engineering change to Alpha-Beta. Future optimization. |

---

## A.5 — Conflicts & Contradictions

### Conflict 1: BCE vs MSE

- **R2, R5 (pro-BCE):** BCE is the proper scoring rule for probability estimation. With soft labels in [0.3, 0.7], BCE penalizes confident wrong predictions more appropriately.
- **R4 (pro-MSE):** MSE handles soft label range naturally without sigmoid saturation, penalizes less severely (good when labels are noisy), and is the AlphaZero standard.
- **R1, R6:** Neither strongly commits.

**Recommendation:** Run both as a Phase 3 ablation. The theoretical argument for BCE is sound for calibrated probability targets, but Churchill's finding of no difference may hold. Low cost to test. Default to BCE in the plan with MSE as ablation.

### Conflict 2: Elo-interpolated labels — direction of causality

- **R1, R3:** Elo labels should be an ablation, not the default. Risk of player-identity bias.
- **R4:** The Elo prior may already be predictive at turn 1, so interpolating FROM it TOWARD the outcome might add noise.
- **R2, R7:** The approach is sound but needs a fixed reference length.
- **R5:** Elo labels and label smoothing are redundant — pick one.

**Recommendation:** Keep Elo-interpolated labels as one arm of a three-way Phase 3 ablation: (1) hard binary labels, (2) hard labels + temporal sample weighting, (3) Elo-interpolated labels with fixed reference length. Let data decide. The plan should present all three, not commit to one.

### Conflict 3: Game count for evaluation

- **R1:** 512 is "very reasonable" if matches are paired.
- **R3, R4, R5:** 512 is "absolute bare minimum" or "insufficient" — need 1,000-2,000.
- **R6:** 512 is "very reasonable", suggests SPRT.
- **R7:** 512 is "adequate for detecting ≥5pp differences", suggests extending to 1,024 if borderline.

**Recommendation:** Set 1,024 as the primary target for Phase 5 main evaluation (vs MCDSAI). 512 is acceptable for secondary comparisons (vs LiveHardestAI). Note that extending is cheap — C++ vs C++ games are fast.

### Conflict 4: Policy head priority

- **R3, R6:** Should be medium priority — even 20% accuracy helps move ordering significantly.
- **Plan + R7:** Optional / low priority.
- **R2:** Medium priority ablation in Phase 3.

**Recommendation:** Upgrade from "optional" to "recommended Phase 3 ablation." Even weak policy priors help in high-branching-factor games. The existing C++ PUCT infrastructure is already implemented.

### Conflict 5: ResBlock norm placement

- **R5:** Pre-norm (norm before first linear) trains more stably.
- **C++ codebase:** Post-norm is already implemented and deployed.

**Recommendation:** Keep post-norm. Changing would require C++ infrastructure changes with uncertain benefit at this model depth (2-4 blocks).

---

## A.6 — Recommended Plan Changes

### Must-Do (high consensus, high impact, or addresses real risks)

| # | Change | Reviewer(s) | Rationale |
|---|---|---|---|
| M1 | **Fix `total_turns` leakage: use fixed reference length** (`t = min(1.0, turn_number / 40)`) in Elo-interpolated label formula | R1, R2, R3, R5, R7 | 5/7 reviewers flagged this. `total_turns` is outcome-correlated. Fixed reference eliminates leakage entirely. |
| M2 | **Resolve record granularity: commit to start-of-turn-only for V1** | R1, R3, R5 | Ambiguity cascades to record count, label validity, augmentation design. Start-of-turn is safe and matches Churchill. |
| M3 | **Update Option 2 feature spec to match C++ reality: 11 features per unit** (ready, exhausted, constructing, blocking × 2 players + P0 supply, P1 supply, in_card_set) + 14 global features | All 7 | C++ already implements this. Plan's Option 2 lists only 5 values. Aligning the plan with reality prevents confusion. |
| M4 | **Remove label smoothing from Phase 4b when using Elo soft labels** | R1, R5 | Redundant double-smoothing. If ablation shows hard labels win, re-add label smoothing. |
| M5 | **Adopt temporal train/test split as primary** | R1, R2, R4, R5 | 4/7 reviewers. Prismata meta evolved over time. Random split lets model see same-era games across partitions. Keep random split as secondary diagnostic. |
| M6 | **Increase Phase 5 evaluation to 1,024 games minimum** | R3, R4, R5, R7 | 5/7 reviewers raised concern about 512. 1,024 detects ≥3pp differences reliably. Games are cheap. |
| M7 | **Document normalization constants in schema** | R1, R2, R4, R5, R6 | C++ uses specific clamp-divide caps. JS extraction must use identical values. Export caps in `schema_v1.json`. |
| M8 | **Add mirror augmentation correctness test** | R1, R2, R5, R6 | `mirror(mirror(x)) == x` and `label + mirror_label ≈ 1.0`. 4/7 reviewers. Simple, catches bugs. |
| M9 | **Present Elo-interpolated labels as one arm of a 3-way ablation**, not the default | R1, R2, R3, R4 | 4/7 reviewers skeptical of defaulting to Elo labels. Three arms: (1) hard binary, (2) hard + temporal weighting, (3) Elo-interpolated with fixed ref length. |

### Should-Do (strong suggestions that meaningfully improve the plan)

| # | Change | Reviewer(s) | Rationale |
|---|---|---|---|
| S1 | **Add `card_set` and `game_date` to record schema** | R2, R5, R7 | Enables temporal split, post-hoc stratified analysis. Trivial storage cost. |
| S2 | **Add turn-bucketed evaluation metrics** (report val loss by turn quartile) | R1, R5 | Catches phase-specific failures the aggregate metric misses. |
| S3 | **Upgrade policy head from "optional" to "recommended ablation"** | R3, R6, R7 | Even 20% accuracy helps move ordering. PUCT infrastructure exists in C++. |
| S4 | **Add distribution shift acknowledgment** as explicit known limitation | R1, R3, R4, R7 | Cannot be solved in supervised learning. Important context for interpreting results. |
| S5 | **Use wall-clock budget for ablations** instead of fixed epoch count | R2, R5 | Fairer comparison across model sizes. |
| S6 | **Add checkpoint averaging (SWA/Polyak)** to Phase 4 | R2, R4, R5, R7 | Nearly free, often improves robustness. PyTorch has `swa_utils` built in. |
| S7 | **Add "Failure Modes" section** | R7 | Document mode collapse, phase-specific overfitting, card-set memorization. Helps diagnose failures. |
| S8 | **Check forfeit/timeout/resignation handling** during Phase 0d | R4, R5 | Label validity concern. Identify and quantify these in the dataset audit. |
| S9 | **Validate engine on all replays during extraction** (not just 1,000 sample) | R7 | Each replay passes through the engine anyway. Log failures. Makes V4 verification comprehensive. |
| S10 | **Add card-set stratified evaluation** to Phase 5 | R1, R4, R6, R7 | Report performance on seen vs unseen card sets. Detects memorization. |
| S11 | **Use binary format (not JSONL) for extracted records** | R5 | JSONL at 6.2M records is impractically slow. Existing selfplay pipeline uses binary shards — reuse that format. |
| S12 | **Add first-player advantage measurement** to Phase 0d, adjust Elo prior if >2pp asymmetry | R2 | P2 wins 57.3% in self-play data. Human data likely shows asymmetry too. Easy to measure, easy to adjust. |
| S13 | **Default to BCE loss**, with MSE as Phase 3 ablation | R1, R2, R4, R5 | Theoretically more principled for probability estimation. Low cost to ablate. |

### Consider (good ideas worth thinking about)

| # | Change | Reviewer(s) | Effort | Recommendation |
|---|---|---|---|---|
| C1 | Mixup augmentation on feature vectors | R2, R5, R7 | Small | Lean yes — cheap, well-supported for tabular data |
| C2 | Non-linear `t` ramp (quadratic/sigmoid) for label interpolation | R2, R6, R7 | Trivial | Lean yes — easy to test alongside linear |
| C3 | Huber loss as alternative to MSE | R6 | Trivial | Neutral — low priority but free to add as ablation |
| C4 | Action availability features (buyable/affordable flags) | R6 | Medium | Lean no for V1 — adds complexity, can be added later |
| C5 | Paired tournament matches (same card set, swapped players) | R1 | Medium | Lean yes — reduces variance in evaluation |
| C6 | Noise injection on resource features for search robustness | R3, R6 | Small | Neutral — reasonable regularization |
| C7 | Turn subsampling (30-50% of turns per game) to reduce correlation | R6 | Small | Lean no — reduces data without clear benefit when using temporal weighting |
| C8 | Schema checksum in output filenames | R2 | Trivial | Lean yes — prevents accidental mixing |
| C9 | Extraction parallelization (8 workers) | R7 | Small | Lean yes — trivial speedup for embarrassingly parallel task |
| C10 | SPRT sequential testing for tournaments | R1 | Medium | Lean no for V1 — Wilson CI is sufficient |
| C11 | Phase 0e: benchmark residual MLP variants alongside plain MLP | R2 | Small | Lean yes — need speed numbers for configs we'll actually compare |
| C12 | Keep base-only games but downweight 0.5× | R6 | Trivial | Lean no — plan correctly excludes them |
| C13 | Search-depth benchmark at realistic think times (3s, 7s) | R5, R6 | Small | Lean yes — measures what actually matters |
| C14 | Move agreement metric (neural AI vs expert human moves) | R2, R7 | Medium | Lean yes — useful diagnostic for Phase 5 |
| C15 | Cross-language smoke test (Python eval == C++ eval for same state) | R2, R5 | Small | Lean yes — catches deployment bugs |

### Reject (with reason)

| Suggestion | Reviewer | Reason |
|---|---|---|
| **Switch to active-player-relative encoding** | R2 | Conflicts with existing C++ infrastructure (canonical P0/P1 encoding). Would require rewriting `NeuralNet.cpp`. The current approach with symmetry augmentation achieves the same result. |
| **Pre-norm ResBlock placement** | R5 | C++ already implements post-norm. Changing adds engineering cost with uncertain benefit at 2-4 block depth. |
| **Permutation augmentation for unit ordering** | R3 | Only relevant for variable-slot encoding (Option 4). With fixed 116-slot encoding, unit order is canonical. |
| **Option 4 as V1 starting point** | R3 | Too complex for V1. No precedent. Ability encoding unsolved. Correctly scoped as future work. |
| **FP16 inference in C++** | R6 | x86 CPUs lack native half-precision ALU. Would require GPU inference or AVX-512 FP16 extensions (rare). |
| **Bayes factor for tournament eval** | R7 | Adds analytical complexity without changing decisions. Wilson CI is standard and sufficient. |

---

## A.7 — What Stays

The following plan elements were confirmed as solid by reviewers and should remain unchanged:

1. **Overall phased structure with verification gates (V1-V11)** — praised by 4+ reviewers
2. **Clean restart with validated JS engine** — unanimous agreement this is correct
3. **Option 2 as starting feature representation** — unanimous (7/7)
4. **Churchill baseline as Phase 3a lower bound** — multiple reviewers endorsed
5. **Base-only game exclusion** — consensus
6. **Split by replay code** — confirmed necessary
7. **Opening book extraction from training data only** — confirmed correct
8. **MCDSAI as primary benchmark** (with secondary metrics added) — consensus
9. **Dropout + weight decay + early stopping** as regularization approach — confirmed appropriate
10. **Phase 6 self-play outline** — reviewers confirm it's the right next step
11. **Gumbel AlphaZero reference** for self-play — endorsed
12. **Balance validation methodology** — praised as thorough
13. **Rating-based sample weighting** over hard floor — confirmed better
14. **Residual MLP as architecture variant to test** — confirmed worth testing
