# Meta-Review: PrismatAI Training Plan V1

**Plan:** `docs/plans/2026-03-06-training-plan-v1.md`
**Date:** 2026-03-07
**Reviews ingested:** 6
**Reviewer profiles:** General ML practitioner (R1), Game AI/ML systems specialist (R2), Risk/execution analyst (R3), PyTorch/ML engineering practitioner (R4), ML engineering / game AI evaluation specialist (R5), ML systems / search integration specialist (R6)

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| R1 | Very positive | Data quality, verification rigor, label strategy elegance | "Best-prepared ML plan I've seen" — emphasized verification gates |
| R2 | Very positive | Architecture predictions, inference speed, feature schema | Predicted residual MLP + LayerNorm; validated single-sample inference context |
| R3 | Positive, structured | Risk enumeration (R1-R5), execution priority ordering | Recommended Phase 0 execution order: 0e -> 0d -> 0c -> 0f |
| R4 | Strongly positive | PyTorch implementation details, numerical stability | BCEWithLogitsLoss for soft labels; Mixup on categorical features; float32 export |
| R5 | Strongly positive, substantive | Mid-turn evaluation gap, resignation noise, paired statistics | Deepest technical probe; Mixup skepticism; multi-think-time evaluation |
| R6 | Positive, 6 blocking items | Search integration, score calibration, total_turns leakage | Eval score mapping for alpha-beta; Option 1.5; pairwise/ranking losses |

---

## A.2 — Consensus Points

Items raised by 2+ reviewers, ranked by frequency:

| # | Point | Reviewers | Count |
|---|---|---|---|
| 1 | **Mixup questionable / deprioritize** — interpolated game states are illegal; likely low value | R5, R6, (R4 noted categorical interaction) | 3 |
| 2 | **Paired statistical tests needed** — use McNemar's/sign test on pair outcomes, not simple binomial | R5, R6 | 2 |
| 3 | **Opening book: extract early, test with/without** — extract in Phase 0, compare tournament results | R3, R5, R6 | 3 |
| 4 | **REFERENCE_LENGTH=40 must be verified against actual data** | R3, R5 | 2 |
| 5 | **Gradient clipping (max norm 1.0) as default** | R4 (implied via stability), R5 | 2 |
| 6 | **Report results at multiple think times** (1s, 3s, 7s) | R5, R6 | 2 |
| 7 | **Resignation/forfeit label noise is significant** — trim or flag late pre-resignation turns | R5, R6 | 2 |
| 8 | **Elo-interpolated labels (Strategy C) has risks** — bakes player identity; treat as ablation not favorite | R5, R6 | 2 |
| 9 | **Symmetry augmentation + Strategy C interaction** — verify mirror labels sum to 1.0 exactly | R3, R5 | 2 |
| 10 | **Rare unit coverage** — units with <300-500 games are essentially untrained; flag in evaluation | R5, R6 | 2 |
| 11 | **SWA timing** — start in last ~20% of epochs, not earlier | R3, R4 | 2 |
| 12 | **LR warmup** — 500-2000 steps linear warmup for stability | R4 (implied), R5 | 2 |
| 13 | **Turn-bucketed metrics from the start** — label entropy and performance by turn bucket | R5, R6 | 2 |

---

## A.3 — Outlier Points

Items raised by only one reviewer. Stars indicate my assessment of merit.

| Point | Reviewer | Merit |
|---|---|---|
| **Eval score calibration for alpha-beta** — NN outputs [-100, +100] but Playout uses [-10000, +10000] | R6 | **HIGH** — validated by codebase. Real mismatch in `Eval.cpp`. |
| **Mid-turn evaluation gap** — model never sees states the search evaluates | R5 | **MOOT** — codebase confirms HPS evaluates only end-of-turn states |
| **Option 1.5** — type counts + constructing + supply + in_card_set + globals | R6 | Medium — interesting but adds ablation complexity; Option 1 vs 2 already planned |
| **Pairwise/ranking losses** — auxiliary ordering objective | R6 | Medium — theoretically sound but implementation complexity; consider for iteration 2 |
| **Per-game weight normalization** — prevent long games dominating | R6 | Low-Medium — valid concern but with temporal weighting (Strategy B) the effect is partially addressed |
| **Value monotonicity probes** — extra resources shouldn't reduce value | R6 | Medium — good sanity check, cheap to implement |
| **Noise injection instead of Mixup** — small Gaussian noise on normalized features | R5 | Low — dropout already provides similar regularization |
| **Heuristic+net blend as Phase 5 ablation** | R6 | **HIGH** — existing C++ supports `NeuralNetPlusPlayout`; practically free to test |
| **BCEWithLogitsLoss** (not BCELoss after sigmoid) | R4 | **HIGH** — standard best practice, prevents numerical instability |
| **Stratify test by card-set novelty** | R6 | Medium — plan already has card-set stratified evaluation; this refines it |
| **W&B/MLflow for ablation tracking** | R5 | Medium — good practice but not blocking |
| **Define primary offline metric upfront** | R6 | Medium — BCE is the implicit default; making it explicit is cheap |
| **Search interaction ablations** (raw/net/blend/ordering) | R6 | **HIGH** — determines optimal deployment mode |
| **Minimal viable path one-pager** | R6 | Low — plan is already structured in phases |

---

## A.4 — Category Breakdown

### Architecture & Design

| Item | Reviewer(s) | Codebase Reality | Analysis |
|---|---|---|---|
| Eval score calibration for alpha-beta | R6 | **VALIDATED.** `Eval.cpp:77` scales NN output by ×100 to [-100,+100]. `Eval.cpp:226` scales by ×10000 for NeuralNetPlusPlayout blend. Playout returns [-10000,+10000]. WillScore is unbounded. Pure NeuralNet mode has a compressed dynamic range that will produce different search behavior than Playout. | **Must address.** Add explicit documentation of the score mapping and recommend using either NeuralNetPlusPlayout blend mode or updating the ×100 factor to ×10000 for pure NN evaluation. |
| Mid-turn evaluation gap | R5 | **MOOT.** `MoveIterator_PPPortfolio.cpp:22-71` completes all 4 PartialPlayer phases (Defense, ActionAbility, ActionBuy, Breach) before returning a child state. `StackAlphaBetaSearch.cpp:129-131` only calls eval at depth-limit terminal nodes. UCTSearch same pattern. The search **never** evaluates mid-turn states. | **Reject concern.** Start-of-turn-only training data is exactly correct for this search architecture. |
| Option 1.5 intermediate feature set | R6 | Option 1 vs Option 2 ablation already planned in Phase 3b. | **Consider.** If the Option 1 vs 2 gap is large, Option 1.5 could help identify which features drive the gain. But adds ablation complexity. |
| Search interaction ablations | R6 | C++ already supports `NeuralNet`, `NeuralNetPlusPlayout`, `Playout`, and `WillScore` eval modes. Blend weight is configurable. | **Should add.** Comparing net-only vs net+playout blend vs playout-only in tournament is practically free. |
| Residual MLP + LayerNorm validated | R2, R5 | `NeuralNet.cpp:146-154, 442-459` already implements residual blocks with LayerNorm. | **Confirmed correct.** LayerNorm is appropriate for single-sample inference. |

### Risks & Concerns

| Item | Reviewer(s) | Analysis |
|---|---|---|
| Resignation label noise | R5, R6 | Valid concern. Last 3-5 turns before resignation carry biased labels. Plan mentions identifying forfeit/timeout in Phase 0d but doesn't specify mitigation. **Should add** trimming or flagging guidance. |
| `total_turns` leakage risk | R6 | Plan already says "used only for label computation, never an input feature." But should be more explicit: store as metadata, add to extraction test that it never appears in feature vector. |
| Rare unit coverage | R5, R6 | Plan already measures per-unit frequency in Phase 0d. **Should add** reporting win rate separately for rare-unit card sets in Phase 5a. |
| Feature-to-data ratio | R3 | 1,290 features with ~4,800 records per dimension. Plan already includes dropout and bottleneck. Adequate. |
| Long-game overrepresentation | R6 | Valid but mild. With temporal weighting (Strategy B), late-game positions are already upweighted intentionally. Per-game normalization could conflict with that intent. **Consider** but don't default to it. |

### Suggested Removals / Simplifications

| Item | Reviewer(s) | Analysis |
|---|---|---|
| Rating-based sample weighting | R5 suggests drop entirely | Plan already notes the effect is mild (98.8% of games have weight >= 0.64). Plan already says "if ablation shows negligible difference, drop for simplicity." No change needed — the ablation will settle it. |
| Elo-interpolated labels as "presumptive favorite" | R6 | Plan already frames it as a 3-way ablation, not a default. No demotion needed. |

### Suggested Additions

| Item | Reviewer(s) | Priority | Analysis |
|---|---|---|---|
| Gradient clipping (max norm 1.0) | R4, R5 | **Must-do** | Cheap insurance, never harmful, prevents training collapse from confident-but-wrong predictions. |
| LR warmup (500-2000 steps) | R4, R5 | **Should-do** | Standard practice for Adam + BCE on noisy labels. |
| BCEWithLogitsLoss | R4 | **Must-do** | Numerically stable for soft targets. Standard PyTorch best practice. |
| McNemar's / paired test | R5, R6 | **Must-do** | Plan says paired matches but doesn't specify paired analysis method. |
| Multi-think-time evaluation | R5, R6 | **Should-do** | Report at 1s, 3s, 7s to distinguish eval quality from search depth. |
| Offline search-position sanity check | R6 | **Should-do** | Run HPS + new eval on self-generated positions; check value consistency before expensive tournaments. |
| Heuristic+net blend tournament | R6 | **Should-do** | Test NeuralNetPlusPlayout mode; may outperform pure NN eval. |
| Value monotonicity probes | R6 | **Consider** | Sanity tests: extra resources shouldn't reduce value. |
| Pairwise/ranking losses | R6 | **Consider** | Auxiliary objective for search ordering. |
| W&B/MLflow tracking | R5 | **Consider** | Good practice for 15+ ablation runs. |

### Confirmed Good / Keep As-Is

| Item | Reviewer(s) |
|---|---|
| REFERENCE_LENGTH=40 fix (eliminating total_turns leakage) | R1, R2, R3, R4 |
| 3-way label ablation structure | R1, R2, R4 |
| Temporal train/val/test split | R1, R5, R6 |
| Symmetry augmentation as true 2x | R1, R5, R6 |
| 1,024 paired games for primary evaluation | R2, R5, R6 |
| Option 2 as starting feature set | R1, R2, R5 |
| Known failure modes matrix | R1, R4 |
| Phase 0 verification-first approach | R1, R2, R3 |
| Start-of-turn-only training data | R5 (after codebase verification) |
| Residual MLP for depth >= 3 | R2, R5, R6 |
| SWA inclusion | R3, R4 |
| Opening book from expert replays | R3, R5, R6 |

---

## A.5 — Conflicts & Contradictions

### 1. Mixup: Keep or Drop?

- **R4** says it's a "top-tier recommendation for tabular, highly correlated data" but notes categorical feature interaction
- **R5** says it's "questionable" — interpolated game states are illegal, wastes capacity
- **R6** says "de-emphasize unless ablations clearly support it"

**Recommendation:** The plan already treats Mixup as an ablation, not a default. Keep it in the ablation list but lower expectations. R5's point about illegal interpolated states is valid — a Wall count of 1.8 is never seen at inference. However, the plan uses low alpha (0.1-0.2) which keeps interpolation close to real states. No plan change needed; the ablation will decide.

### 2. Rating-Based Sample Weighting: Keep or Drop?

- **R5** argues lower-rated games have *clearer* signal (blunders create informative position trajectories)
- **R6** suggests per-game normalization instead
- **Plan** already says "compare vs unweighted baseline; drop if negligible"

**Recommendation:** No change. The plan's ablation approach handles this correctly. R5's argument has merit but doesn't account for the fact that lower-rated play also contains more rule-ignorant positions that teach bad heuristics.

### 3. Strategy C (Elo-Interpolated Labels): Favorite or Just an Ablation?

- **R5** says "Strategy B is the safest bet" — simpler, no Elo dependency
- **R6** says Elo labels "bake in player identity" — model learns "stronger player wins" not "this position wins"
- **R4** says it's "theoretically sound" but implementation matters
- **Plan** frames as 3-way ablation, no presumptive favorite

**Recommendation:** No change. The plan correctly treats this as an ablation. R6's concern about player-identity leakage is theoretically valid but the effect should be small: at deployment there are no ratings, so any learned Elo bias manifests as a constant offset (approximately the Elo prior at equal ratings = 0.5), which is benign. The ablation will reveal if Strategy C actually helps.

### 4. LayerNorm: Yes or No?

- **R2** validates LayerNorm for single-sample inference
- **R6** says "test without LN" — may interact oddly with small tabular MLPs

**Recommendation:** The plan already includes LayerNorm in the residual block code. R6's suggestion to test without is reasonable. Add "with/without LayerNorm" as a sub-ablation if time permits, but don't prioritize it — the C++ inference engine already supports it.

---

## A.6 — Recommended Plan Changes

### Must-Do (High consensus or validated by codebase)

1. **Add gradient clipping (max norm 1.0) as default for all training runs** (R4, R5)
   - Add to Phase 4a training configuration

2. **Specify BCEWithLogitsLoss** instead of generic "BCE" (R4)
   - Update Phase 1b loss function description

3. **Document eval score calibration for alpha-beta integration** (R6)
   - Codebase confirms: pure NeuralNet uses ×100 [-100,+100], Playout uses [-10000,+10000], NeuralNetPlusPlayout uses ×10000. Add to Phase 4e and Phase 5.
   - Recommend testing both ×100 and ×10000 scale factors, or using NeuralNetPlusPlayout blend mode

4. **Add McNemar's test / paired sign test to evaluation protocol** (R5, R6)
   - Update Phase 5a to specify paired analysis method

5. **Update mirror correctness test to explicitly cover Strategy C labels** (R5)
   - Phase 2d test must verify `label_original + label_mirror == 1.0` exactly (not approximately) for all three label strategies

6. **Confirm HPS evaluates only end-of-turn states** (R5 — resolved by codebase)
   - Add a note in Phase 1a confirming this, citing MoveIterator_PPPortfolio.cpp

### Should-Do (Strong suggestions that improve the plan)

7. **Add LR warmup (500-2000 steps)** (R4, R5)
   - Add to Phase 4c learning rate schedule

8. **Add multi-think-time tournament evaluation** (R5, R6)
   - Phase 5a: report at 1s, 3s, 7s think times

9. **Add search interaction ablations to Phase 5** (R6)
   - Compare: pure NeuralNet eval, NeuralNetPlusPlayout blend, pure Playout baseline
   - The C++ infrastructure already supports all three modes

10. **Add resignation label noise mitigation to Phase 0d** (R5, R6)
    - Identify resignation games; measure how many exist
    - If >5% of games end by resignation: trim last 3-5 positions before resignation from training, or flag for ablation

11. **Add offline search-position sanity check before Phase 5 tournaments** (R6)
    - Run HPS + new eval on a batch of self-generated positions
    - Check value consistency, mirror symmetry, and tactical sanity

12. **Add with/without opening book comparison to Phase 5** (R3, R5, R6)
    - Every primary tournament result should note whether opening book was active

13. **Add rare-unit stratified reporting to Phase 5a** (R5, R6)
    - Report tournament win rate separately for card sets containing low-frequency units (<500 games)

14. **Explicitly separate state features from metadata in schema** (R6)
    - `total_turns`, `rating_p0`, `rating_p1`, `game_date`, `replay_code` must be in a metadata block, not features
    - Add extraction test that verifies these never enter the feature vector

15. **Add float32 casting requirement to Phase 4e export** (R4)
    - Cast PyTorch model to float32 before export; C++ uses float, Python defaults to float64

### Consider (Good ideas, not critical)

| # | Item | Reviewer(s) | Effort | Recommendation |
|---|---|---|---|---|
| C1 | Option 1.5 intermediate feature set | R6 | Small | Lean no — Option 1 vs 2 ablation sufficient |
| C2 | Pairwise/ranking auxiliary loss | R6 | Medium | Lean yes for iteration 2 |
| C3 | Value monotonicity probes | R6 | Small | Lean yes — cheap sanity check |
| C4 | W&B/MLflow for ablation tracking | R5 | Small | Lean yes |
| C5 | Per-game weight normalization | R6 | Small | Neutral — may conflict with temporal weighting |
| C6 | Noise injection (Gaussian sigma=0.05) as alternative to Mixup | R5 | Trivial | Neutral |
| C7 | Stratify test by card-set novelty (seen/unseen/rare) | R6 | Small | Lean yes — refines existing card-set stratification |
| C8 | Endgame oversampling if turn 25+ positions are <10% of data | R5 | Small | Neutral — temporal weighting partially addresses |
| C9 | Define primary offline metric (BCE/Brier/calibration) upfront | R6 | Trivial | Lean yes |
| C10 | Minimal viable path one-pager | R6 | Small | Lean no — phases already ordered |
| C11 | Compute budget estimates per phase | R6 | Small | Lean yes |
| C12 | Heuristic+net blend as Phase 5 ablation | R6 | Trivial | Lean yes — C++ already supports it |
| C13 | Fix V-numbering gap (V6, V9 missing) | R6 | Trivial | Lean yes — presentation cleanup |
| C14 | Turn-bucketed label entropy reporting in Phase 0d | R5, R6 | Small | Lean yes |
| C15 | Schema hash in binary shard headers (not just filenames) | R5 | Small | Lean yes |

### Reject (with reason)

| Item | Reviewer | Reason |
|---|---|---|
| Mid-turn evaluation concern | R5 | **Codebase disproves.** `MoveIterator_PPPortfolio.cpp` completes all 4 PartialPlayer phases before returning child states. Search evaluates only end-of-turn states. Training on start-of-turn states is correct. |
| Drop Mixup entirely | R5, R6 | Plan already treats as ablation with low alpha. Let the ablation decide. |
| Demote Strategy C from ablation lineup | R6 | Already framed as one of three equal ablation candidates, not the favorite. |
| Run Option 1 immediately alongside Option 2 | R6 | Already planned as Phase 3a (Churchill baseline). |
| Policy head action canonicalization sub-plan | R6 | Out of scope for value-only Phase 3-5. The plan already gates policy on 20%+ accuracy. |

---

## A.7 — What Stays

The following elements received explicit positive confirmation and should remain unchanged:

1. **Phase 0 verification-first structure** — all reviewers praised this
2. **REFERENCE_LENGTH=40 fix** — universally endorsed
3. **3-way label ablation (Strategies A/B/C)** — correct approach
4. **Option 2 feature set as starting point** — validated
5. **Temporal train/val/test split** — standard and correct
6. **Symmetry augmentation with post-split application** — correct implementation
7. **1,024 paired games for primary evaluation** — adequate statistical power
8. **Known failure modes matrix** — defensive engineering praised
9. **Residual MLP blocks with C++ support** — validated
10. **SWA integration** — endorsed
11. **Wall-clock ablation budgets** — fairer than fixed epochs
12. **Opening book extraction from expert replays** — endorsed
13. **Phase 5 success criteria (Wilson CI > 0.50)** — sound
14. **Phase 6 self-play outline** — appropriate scope for this document

---

## Codebase Verification Notes

These findings come from direct code inspection, giving them higher confidence than reviewer speculation:

1. **HPS end-of-turn evaluation confirmed.** `MoveIterator_PPPortfolio.cpp:22-71` iterates through all 4 PartialPlayer phases (DEFENSE, ACTION_ABILITY, ACTION_BUY, BREACH) and asserts the result is in Confirm phase before returning. `StackAlphaBetaSearch.cpp:129-131` only calls `eval()` at depth-limit terminal nodes. UCT follows the same pattern. **No mid-turn evaluation occurs.**

2. **Score scale mismatch confirmed.** `Eval.cpp:77-78` returns `NeuralNet::evaluateValue() * 100.0` for pure NeuralNet mode (range [-100, +100]). `Eval.cpp:226-239` uses `nnValue * Eval::WinScore` (×10000) for NeuralNetPlusPlayout blend (range [-10000, +10000]). Playout returns `10000 - turns_played` for wins. This means pure NeuralNet evaluation has ~100x less dynamic range than Playout, which will affect search behavior. The blend mode is correctly calibrated.

3. **NeuralNet output uses tanh** (`NeuralNet.cpp:531-535`): `tanhf(rawValue)` produces [-1, 1]. The plan's discussion of sigmoid output needs reconciling — the existing C++ code uses tanh, matching Churchill's original. Training should match: use tanh output with MSE (Churchill's approach) or sigmoid output with BCE, but be explicit about which.

4. **C++ float precision confirmed.** `NeuralNet.cpp` uses `float` (32-bit) throughout. PyTorch export must use `torch.float32`.
