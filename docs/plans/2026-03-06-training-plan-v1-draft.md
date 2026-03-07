# PrismatAI Training Plan — Version 1 Draft
**Date:** 2026-03-06
**Status:** DRAFT — For review by human players, external AI reviewers, and domain experts
**Approach:** Track A — Supervised learning on human replays first; iterative self-play in a future phase
**Author:** Surfinite + Claude Code

---

## Important Note to Reviewers

This is the first training attempt using a fully accurate JavaScript game engine — a direct transpilation of the original ActionScript 3 source code. All previous training work (AWS binary shards, old feature schemas, prior model weights, prior win-rate statistics) has been discarded and is not referenced here. Please treat this as a clean start.

### Review Incorporation Status

One external review has been received and incorporated (March 2026). Changes applied:

| Priority | Change | Phase |
|---|---|---|
| **Critical** | Soft labels: Elo-interpolated temporal labels to reduce noisy-label problem | Phase 1b |
| **High** | Rating-based sample weighting (replaces hard floor) | Phase 4a |
| **High** | C++ inference speed benchmark before architecture commitment | Phase 0e |
| **High** | Symmetry augmentation: mirror records for free 2× data | Phase 2a |
| **High** | Reviewer answers to all 6 open questions incorporated | Open Questions |
| **Medium** | Supply remaining added as a recommended feature for Option 2 | Phase 1a |
| **Medium** | Residual MLP blocks added as architecture variant to test | Phase 3c |
| **Medium** | Ablation efficiency: train to fixed budget, not convergence | Phase 3c |
| **Low** | Base-only game exclusion documented and decided | Phase 2a |
| **Low** | MCDSAI think-time scaling test added | Phase 0b / Q6 |

---

## Key Verification Items

These are facts the plan depends on. If any are wrong, assumptions about data scale, feasibility, or success criteria may need revision. Reviewers should flag anything they cannot confirm or believe to be incorrect.

- **V1 — Usable human replay count (validated, final):** Full balance validation (cost + rarity against current `cardLibrary.jso`) completed across **all 203,602 codes** on March 7, 2026. Results: **154,061 balance-passed**, 48,707 failed, 834 fetch errors (S3 404s). After applying the full quality filter (both players ≥1500 rating at game time, rating change ≠ 0 to exclude friendly/unrated games): **102,697 usable training games**. 740 unique players contribute. Post-patch pass rate: ~97.8%. Pre-patch pass rate: ~57.7% — lower because many pre-patch games used unit costs/rarities that have since changed. This is the authoritative training set size. No further verification needed — all codes validated in a single clean run with the current validator.

- **V2 — Competitive unit count:** The authoritative unit list is `bin/asset/config/valid_units.json` and contains exactly **116 units**: 11 base set units (present in every game) and 105 dominion/random set units (the ranked competitive pool). This list was derived from the live game's unit selection screen, March 2026. The `cardLibrary.jso` contains 161 entries but 45 of those are deprecated, event-mode, or removed units that no longer appear in competitive play. Any feature schema must be built on the **116-unit list**, not the raw cardLibrary count.

- **V3 — Balance validation definition:** A replay is considered balance-valid if its unit costs **and unit rarities (supply limits)** match the current `cardLibrary.jso`. The validation script (`validate_db_codes.py`) has been extended to check both `buyCost` and `rarity` for every unit in every replay — it is fully general and catches changes from any era of the game's history.

  **Decision: validate all replays at training time.** The January 14, 2019 cutoff was previously used as a fast filter (post-patch games assumed valid without checking). This approach is fragile — it relies on the boundary being correct and complete, and does not catch rarity/supply changes that happened at other points. Instead, every replay in the training set must pass the full cost+rarity validation before use, regardless of timestamp.

  **Rarity audit results (March 2026):** A sample of 6,308 replays across 133 monthly buckets identified **17 units with historical rarity changes**:
  - **Bombarder**: normal→rare (supply 20→4), affected replays dated July 2018–March 2019. Approximately 544 training-eligible replays will be flagged.
  - **16 other units**: mostly trinket→normal or trinket→legendary transitions, clustered around November 2015. These predate most high-rated play and will affect a smaller number of training-eligible replays.

  Rarity mismatches are reported as `issue: "rarity_changed"` alongside the existing `issue: "cost_changed"` failures. Both cause a replay to fail validation and be excluded from the training set. Audit data: `c:\libraries\prismata-replay-parser\rarity_audit_results.json`.

- **V4 — JS engine accuracy:** The JavaScript engine is a transpilation of the original AS3 engine and is considered authoritative. It has been validated against replay data (100% pass rate on a sample of 500 replays). VERIFY: run validation on a fresh random sample of 1,000+ balance-validated codes before using engine output as training data, and confirm the pass rate is acceptably high.

- **V5 — MCDSAI as success benchmark:** The target for supervised training is: the trained model, used as the evaluation function in Alpha-Beta HPS search, wins a statistically significant majority of games against MCDSAI. MCDSAI's strength relative to LiveHardestAI (our strongest C++ reference) is being established by the currently-running 512-game LiveHardestAI vs MCDSAI matchup. This also serves as V11 click-failure verification — the two concerns are addressed in the same run. If MCDSAI proves to be a poor benchmark (too weak or too strong relative to LiveHardestAI), the success criterion should be revised before committing to training. MasterBot (the in-game Steam AI) would be the most meaningful real-world reference point but requires Steam move injection, which is currently unfinished and may not be feasible. MasterBot is excluded from the plan as a blocking requirement; it can be added later if injection is completed.

- **V7 — Dataset composition, record scale, and supplementary data:**

  - **PvP status confirmed:** The 102,697 usable training games are all PvP — already verified. MasterBot has a rating ≈1.0 and is excluded by the `rating ≥ 1500` filter, so no human-vs-bot games appear in the primary training set.

  - **Record count estimate:** At approximately 30 turns average game length, the 102,697 games yield roughly **6.2 million training records** (102,697 × 30 × 2 players / 2). For comparison, Churchill (2019) generated 15 million records from 500,000 AI self-play games — our human dataset is roughly 2.4× smaller in record count. VERIFY actual average game length from a sample of balance-validated replays; the 30-turn estimate is unconfirmed and the record count scales directly with it.

  - **"Grey data" — human vs MasterBot replays:** A potentially large pool of human-vs-MasterBot games may exist in the replay database. These are lower-confidence than PvP data: the human player is typically stronger than MasterBot (so the win-probability target is informative), but strategic intent is unknown — the human may have been experimenting, testing unusual strategies, or playing casually. This data could supplement training if the primary 103K dataset proves insufficient, but should not be mixed into the primary training set without a separate quality gate. Assess the size of this pool from the replay database and note as a contingency data source.

- **V8 — Rating distribution (measured, confirmed):** The usable training dataset (102,697 games, both players ≥1500, rated) has a mean combined rating of approximately **3,909** (per-player average ~1,954). Distribution: 2000+ = 38.9%, 1800–1999 = 47.2%, 1600–1799 = 13.6%, 1500–1599 = 0.2%. Only ~230 games fall in the 1500–1599 bracket. This is strong news: the imitation ceiling concern (reviewer Q3) is largely addressed. The dataset is dominated by high-level play, not diluted by low-rated games. The 1500 floor adds almost no weak games. These figures are stable.

- **V10 — Unit properties available for set-based encoding:** All 105 random-pool units have structured properties in `cardLibrary.jso`: buy cost (broken down by resource type), toughness, build time, default blocking, lifespan, fragile flag, and other numeric stats. These are encodeable as a fixed-length property vector per unit. Unit *abilities*, however, are defined as scripts rather than numeric values — encoding them requires either simplification (e.g. "does this unit generate attack? how much?") or omission. This is relevant to the set-based encoder approach described in Phase 1a Option 4. VERIFY: is there a clean mapping from the cardLibrary ability scripts to a small set of numeric features that captures the strategically relevant information without manual labelling of each unit?

- **V11 — C++ AI ↔ JS engine click protocol correctness (hard gate for Phase 5 and Phase 6):** This is distinct from V4 (JS engine rule correctness). V4 verifies that the JS engine implements game rules correctly by stepping through replays. V11 verifies that the C++ Alpha-Beta AI can successfully communicate its chosen moves to the JS engine through the click protocol — i.e., that the click sequences the C++ AI generates are correctly interpreted, executed without failures, and produce the move the AI intended.

  In practice, the click protocol translates C++ `Action` objects into wire-format `{_type, _id}` click sequences consumed by `StateUtil.js`. Failures manifest as `skippedBuys` in the JS engine (clicks that were legal in C++ but rejected by JS) or as incorrect game state after ability activation. Move types that must all work correctly: BUY, USE_ABILITY (including shift-click variants), UNDO_USE_ABILITY, ASSIGN_BLOCKER, SNIPE/CHILL (two-step targeting), END_PHASE.

  **~~Known blocker — resource accounting bug~~ FIXED (March 2026):** Two fixes applied:
  - `PartialPlayer_ActionBuy_GreedyKnapsack.cpp` — `_totalAbilityActivateCost` was not reset before the accumulation loop in `calculateStateData()`, causing stale values to carry across turns. Fixed by resetting to `Resources()` before the loop. This was the root cause of over-planned buys after ability-cost units fire.
  - `Benchmarks.cpp` — added `UNDO_USE_ABILITY` click encoding. When the AI plan includes deactivating a unit (e.g. Perforator being un-fired by `AbilityAvoidAttackWaste`), the JS engine now receives the matching toggle click so resources reconcile correctly.

  Smoke test: 5-game Perforator set — 0 `skippedBuys`, 0 over-plan warnings. Clean.

  **Verification protocol (pending):** The 512-game LiveHardestAI vs MCDSAI matchup currently running (Phase 0b) will serve as the full V11 verification run. Before Phase 5 or Phase 6 begins, confirm from those results:
  - Zero `skippedBuys` logged across all games
  - Zero click failures for all move types: BUY, USE_ABILITY, UNDO_USE_ABILITY, ASSIGN_BLOCKER, SNIPE/CHILL (two-step targeting), END_PHASE
  - Game outcomes are plausible under human expert review (a sample of games reviewed by an experienced Prismata player)

  Phase 5 (evaluation) and Phase 6 (self-play) remain hard-gated on the full verification run completing cleanly.

---

## Overview

The goal is to train a neural network evaluation function for Prismata that, when used inside the existing Alpha-Beta Hierarchical Portfolio Search (HPS) engine, produces an AI stronger than the MCDSAI baseline.

Churchill (2019) demonstrated this approach works — training on 500K AI self-play games produced an evaluator that beat both the resource heuristic and the playout evaluator. We are building on that result with three key differences:

1. **Accurate engine:** The JS engine correctly implements all game rules. Prior C++ approximations had known errors.
2. **Human replay data:** Human expert games carry stronger strategic signal than AI self-play (the AI being trained against will be stronger than prior AI self-play partners were).
3. **Architecture exploration:** Churchill's 2-layer, 512-neuron MLP was chosen without exhaustive search. We will run targeted ablations before committing to a full training run.

Self-play iteration (AlphaZero-style) is planned as a future phase. This plan covers supervised training only.

A reviewer note (received during initial draft review) is worth highlighting here: *"The Stratego paper (Sokota et al. 2025) is probably the closest analog to what you're attempting in terms of game complexity and budget constraints — their approach of self-play RL + test-time search on an accessible budget maps almost directly to Prismata."* We agree, and it is the primary reference for the self-play phase (Phase 6). Readers are encouraged to review it before evaluating the self-play section.

---

## A Note on Code Cleanup

The `cardLibrary.jso` contains 161 entries, of which 45 are deprecated, event-mode, or non-competitive units. These units never appear in balance-validated competitive replays and should not appear in any training feature vector.

**Recommendation:** Before finalising the feature schema, prune `cardLibrary.jso` to remove the 45 non-competitive entries. This is not strictly required (the `valid_units.json` whitelist already filters them out at runtime), but it reduces confusion, eliminates a source of latent bugs, and produces cleaner code going forward. This can be done as a standalone task independently of the training pipeline.

---

## Phase 0: Prerequisites and Baseline Measurements

**Goal:** Complete all setup before any training work begins. Nothing in Phase 1+ should start until all items here are done and recorded.

### 0a. Complete Balance Validation ✓ DONE
- Full re-validation of all 203,602 codes completed March 7, 2026 — single clean run with current cost+rarity validator.
- Results: 154,061 balance-passed, 48,707 failed, 834 S3 fetch errors.
- Results imported into `replays.db`. Final usable training set: **102,697 games** (both players ≥1500, rated, balance-passed, all eras).
- Produce final canonical code list: `balance_validated_1500plus.json` — pending export from DB.

### 0b. Benchmark Tournament ✓ IN PROGRESS
- **512-game LiveHardestAI vs MCDSAI matchup currently running.** This serves dual purpose: (1) establishes MCDSAI's strength relative to LiveHardestAI as the primary C++ reference, and (2) provides click-failure data for V11 verification.
- After completion: human expert visual review of a sample of games to confirm strategic coherence (moves look sensible, no obviously broken game states).
- Record win rate with Wilson confidence interval.
- **Decision gate:** If MCDSAI wins at an unexpectedly high or low rate vs LiveHardestAI, reassess whether it is the right primary benchmark before proceeding to training.
- **MasterBot (Steam):** Excluded as a blocking requirement. Comparing against the in-game Steam AI would be the most meaningful real-world reference but requires Steam client move injection, which is currently unfinished and may not be feasible. If injection work is completed in a future session, a MasterBot benchmark run can be added to Phase 5 secondary evaluations.

### 0c. JS Engine Validation on Representative Sample
- Run replay validation on a fresh random sample of 1,000 balance-validated codes
- Record pass rate
- **Decision gate:** If pass rate is below 95%, investigate failures before proceeding. Systematic failures indicate an engine correctness issue that would corrupt training data.

### 0d. Dataset Composition Audit
- For the final code list: measure PvP vs PvAI ratio (V7)
- Measure rating distribution (how many 1500–1799, 1800–1999, 2000+)
- Measure game length distribution (average turns per game for record count estimate V6)
- Measure card set distribution (base-only vs random-set games)
- Record all findings. They directly inform feature schema choices and training split decisions.

### 0e. C++ Inference Speed Benchmark (Add Before Architecture Commitment)

Before Phase 3 architecture decisions are finalised, benchmark how quickly the C++ `NeuralNet.cpp` inference engine evaluates positions at different model sizes. This trade-off — model quality vs. search depth — is the central tension and should be measured, not assumed.

- Benchmark: evaluate 10,000 positions with models of sizes 128h/2L, 256h/2L, 256h/3L, 512h/2L, 1024h/2L. Record milliseconds per evaluation.
- If a 1024h model takes 0.5ms but a 256h model takes 0.05ms, the smaller model gets 10× more search depth at fixed think time. At 7 seconds think time, this is likely worth more than the quality gain from a larger model.
- Record results and use them as a constraint on Phase 3 architecture selection. Any architecture too slow to evaluate at least ~500 positions/second should be deprioritised regardless of validation accuracy.

### 0f. Optional: cardLibrary Cleanup
- Identify and remove the 45 non-competitive unit entries from `cardLibrary.jso`
- Update any code that references them (JS engine, C++ loader)
- This is independent of the training pipeline; can be parallelised with other Phase 0 work

---

## Phase 1: Feature Schema Design

**Goal:** Define a canonical, versioned feature vector before any data extraction begins. This schema must be agreed upon and frozen before Phase 2 starts. Changing the schema after extraction requires full re-extraction.

### 1a. The Unit Representation Problem

A game of Prismata uses 11 base set units plus 8 randomly selected units from the 105-unit dominion pool — so at most 19 unit types are present in any given game. However, different games use different random units. For the feature vector to be universal (usable across all card sets), it must accommodate all 116 possible unit types, with zero-counts for types not present in the current game.

Three representation options are presented for reviewer input:

---

**Option 1 — Type-Count (Churchill 2019 Baseline)**

For each of the 116 unit types, record how many units of that type each player owns. Add resource counts and the current player indicator.

- **Feature vector size:** 116 × 2 (count per player) + 12 (resources: 6 types × 2 players) + 1 (player to move) = **~245 features**
- **Advantages:** Simple, fast inference, established precedent. Churchill achieved competitive results with this approach.
- **Disadvantages:** Loses all instance-level information: which units are under construction, which have been used this turn, which are currently blocking, which have taken partial damage.
- **Churchill's note:** "This encoding discards information such as which units may be activated, individual unit instance properties... since the states are all recorded at the beginning of each turn when units are not yet activated, much of the effect of this information loss is alleviated." However, our training data may include mid-turn states (one record per action, not only per turn), making this loss more significant.

---

**Option 2 — Type-Count with Aggregate Instance Flags (Recommended Starting Point)**

Extend Option 1 with per-type aggregate flags. For each unit type and each player, also encode: count under construction, count with ability used, count currently blocking, count with partial damage.

- **Feature vector size:** 116 × 2 players × 5 values (total, building, ability-used, blocking, damaged) + 12 resources + 1 player = **~1,173 features**
- **Advantages:** Captures tactically relevant state without per-instance complexity. Encodes information the model genuinely needs: e.g. how many Rhinos are tapped, how many Forcefields are still building, how many units took partial breach damage.
- **Disadvantages:** ~5× larger than Option 1; more expensive to extract and slower to infer (though still well within C++ inference speed requirements at this scale).
- **Why this is the recommended starting point:** The JS engine reliably exposes all these per-instance fields. Using them is the primary advantage of the accurate JS engine over the prior C++ approximation. Option 1 would replicate Churchill but not use our engine's accuracy advantage.

---

**Option 3 — Per-Instance Encoding with Set Aggregation**

Encode each unit instance individually and aggregate using a permutation-invariant method (sum/mean pooling, or an attention mechanism as explored in the SAINT paper (2025)).

- **Advantages:** Maximum expressiveness; no information loss.
- **Disadvantages:** More complex architecture and more difficult C++ deployment. Variable-length input requires careful handling.
- **Recommendation:** Treat as a future experiment if Options 1 and 2 plateau. Not the starting point for iteration 1.

---

**Option 4 — Set-Based / Property Encoding**

Rather than encoding unit *identity* (which unit is present), encode unit *properties* (what each unit does). For each slot in the card set, provide a vector of numeric properties: buy cost by resource type, toughness, build time, blocking flag, lifespan, attack generated, ability type (simplified), etc.

- **Feature vector size:** 19 active unit types × ~15 property features × 2 players (counts + properties) — roughly **~600–800 features**, but structured differently from the identity-based options.
- **Advantages:** Generalises across card sets. A model trained on this representation learns "what does a cheap fast attacker do?" rather than "what is Rhino?", which may transfer better to unseen card combinations and produce more coherent strategic reasoning.
- **Disadvantages:** Requires careful manual feature design for ability scripts. Not all abilities reduce cleanly to numeric values without losing information. Harder to validate. No prior precedent in Prismata ML work.
- **Note:** Unit stats and costs are directly available from `cardLibrary.jso` (V10). Ability encoding is the hard part and would need a defined schema before this option is feasible. This approach is most compelling if the model needs to generalise to card combinations not well-represented in training data.
- **Recommendation:** A promising medium-term direction, but not the starting point. Best pursued in parallel with Phase 3 ablations once basic results are in.

---

**Reviewer question:** Is Option 2 the right starting point, or is there a strong argument for starting with Churchill-exact (Option 1) or one of the more expressive options (3 or 4)?

### 1b. Label Design

- **Training target:** probability that the active player wins the game from this state
- **Raw label:** 1 if active player won, 0 if lost (draw = 0.5)
- **Output activation:** sigmoid (range 0–1) or tanh (range −1 to 1) — both work; Churchill used tanh. Standardise and document before training.
- **Loss function:** MSE on value prediction. Churchill found MSE and binary cross-entropy produce similar results for this task.

#### The Noisy Label Problem (Critical)

Binary game outcomes are a very noisy signal for early-turn positions. A turn-1 position from a game Player 1 eventually won gets label 1.0, but the true win probability at turn 1 is close to 0.5 for both players. The model must average out this noise, and it is working from a very poor signal-to-noise ratio in the opening and midgame — precisely where evaluation quality matters most for search.

This problem is more acute for high-rated human games than for Churchill's AI self-play. AI self-play games are shorter and more decisive (errors compound faster at lower skill). Human 2000-rated games are longer and closer, meaning the true win probability drifts slowly from 0.5, making the binary label noisier for more turns.

**Recommended mitigation: Elo-interpolated temporal labels (Option B)**

Instead of hard 0/1 labels, blend the game outcome with an Elo-based prior that decays over the course of the game:

```python
# At turn 0, label ≈ Elo win probability; at game end, label = actual outcome
elo_prior = 1 / (1 + 10 ** ((opponent_rating - player_rating) / 400))
t = turn_number / total_turns   # 0.0 at game start, 1.0 at game end
label = (1 - t) * elo_prior + t * actual_outcome
```

This gives early positions a sensible prior grounded in observed player strength, while letting the actual outcome dominate late-game positions where the result is more informative. Rating data is available for every game in the training set (V8), making this a zero-cost addition.

**Implementation note:** When both players have equal ratings, `elo_prior = 0.5`, which is exactly correct. The interpolation then becomes a linear ramp from 0.5 toward the actual outcome — equivalent to temporal discounting without requiring a pre-trained model.

**Alternatives (for future iterations):**
- *Temporal weighting only* (simpler): keep binary labels but weight each sample by `0.3 + 0.7 × (turn / total_turns)`, downweighting noisy early positions without changing the labels. Lower ceiling than Option B but requires zero label schema changes.
- *TD(λ) bootstrapping* (higher ceiling, more complex): use an initial model's own predictions to generate soft labels for a second pass. Standard in game AI but requires an iterative training loop. Consider for self-play iteration 2+ (Phase 6).

**Comparison:** Run Phase 3 ablations with both binary labels and Elo-interpolated labels. If Elo-interpolated labels reduce validation MSE, use them for the Phase 4 full training run.

### 1c. Schema Versioning

- Schema stored as a single versioned JSON file: `training/schema_v1.json`
- Must include: unit list (ordered), feature names and indices, value ranges, normalisation method, label encoding
- Any change to the feature vector = new version. Old data cannot be mixed with new schema.
- The canonical unit ordering comes from `valid_units.json` (base set first, then random set alphabetically, or by some consistent ordering). This ordering must be fixed and documented.

---

## Phase 2: Data Extraction Pipeline

**Goal:** Extract all usable human replay data through the accurate JS engine into a single canonical dataset. All previous JSONL files are considered legacy and are not mixed into this output.

### 2a. Extraction

- **Input:** `balance_validated_1500plus.json` from Phase 0a
- **Process:** For each replay code, fetch from S3, step through game using JS engine, record one training record per player-turn
- **Output:** Single canonical JSONL: `training/data/human_replays_v1.jsonl` (chunked if needed for size)
- **Record format:** `{ "features": [...], "label": 0.0–1.0, "replay_code": "...", "turn": N, "rating_p0": X, "rating_p1": Y, "total_turns": T }`
- **Include `total_turns`** in each record: required to compute Elo-interpolated labels (Phase 1b) at training time without re-parsing replays.
- **Note:** Store raw state fields alongside the feature vector in each record if feasible. This allows re-vectorisation (re-running the featurisation step without re-fetching replays) if the schema changes during Phase 3 ablations.

**Symmetry augmentation (free 2× data):**

Prismata is symmetric between players. For every training record from Player 0's perspective, generate a mirror record from Player 1's perspective: swap all P0/P1 features and invert the label (1 − label). This doubles the effective dataset at zero additional extraction cost.

For this to work, the feature vector must be structured so the swap is trivial. **Requirement:** design the Phase 1 schema with P0 features in a contiguous block followed by P1 features in the same layout. The mirror record is then a single slice-and-swap operation. Document this requirement explicitly in `training/schema_v1.json`.

**Base-only game exclusion:**

Base-only games (no random units — both players use only the 11 base-set cards) are strategically very different from the random-set format that constitutes all competitive play. Including them introduces a distribution the model must learn that has near-zero relevance to the target deployment context. Exclude base-only games from the primary training set. Measure their count during Phase 0d so the exclusion can be quantified. If enough base-only games exist (500+), they can be used for a side experiment with a separate model.

### 2b. Train / Validation / Test Split

- Split by replay code (not by individual record) to prevent game-level data leakage
- Suggested split: 80% train / 10% validation / 10% test
- Test set held out entirely — not used during Phase 3 architecture search
- Consider a temporal split (earlier games train, more recent validate/test) as an alternative that better reflects deployment conditions

### 2c. Deduplication

- Some codes may appear across multiple source lists. Deduplicate by code before extraction begins.
- After extraction, verify no duplicate records (same replay_code + turn combination)

### 2d. Post-Extraction Validation

- Spot-check 100 random records against expected game outcomes
- Verify label distribution (~50/50 expected given symmetrically-rated games)
- Verify feature value ranges (no NaN, no Inf, no obviously wrong counts)
- Verify total record count is consistent with estimate from V6

---

## Phase 3: Architecture Search and Ablation

**Goal:** Determine a good architecture before a full training run. Use a representative subset of training data. Do not proceed to Phase 4 without reviewing results here.

This phase is the primary place where the plan should be adjusted based on empirical findings.

### 3a. Churchill Baseline (Lower Bound)

Replicate Churchill (2019) as closely as possible on our data:
- Feature set: Option 1 (type-count, ~245 features)
- Architecture: 2 hidden layers, 512 neurons, tanh activation
- Optimiser: Adam, LR = 1e-5
- Loss: MSE, value prediction only

This is the lower bound. If a more complex model cannot beat it, something is wrong with the model, the data, or the problem formulation.

### 3b. Feature Richness Ablation

Train same Churchill architecture on Option 2 features (~1,173 features) and compare validation accuracy.
- If Option 2 adds less than ~1 percentage point: consider whether the complexity is justified
- If Option 2 adds ≥2 percentage points: Option 2 is likely the better starting point

### 3c. Capacity Search and Architecture Variants

Vary hidden dimension: 128, 256, 512, 1024. Vary depth: 2, 3, 4 layers. Use the winning feature set from 3b.

Key question: is 512 neurons (Churchill's choice) actually optimal, or is it over/under-powered for a ~245 or ~1,173-feature input? A smaller model infers faster in C++ (directly increases search depth at fixed think time). A 256-neuron model may be preferable to a 512-neuron one if accuracy is similar. Cross-reference against the Phase 0e inference speed benchmark.

**Residual MLP blocks:** Include at least one run with skip connections (residual blocks) alongside the plain MLP:

```python
class ResBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.fc2 = nn.Linear(dim, dim)
        self.norm = nn.LayerNorm(dim)
    def forward(self, x):
        return x + self.norm(F.relu(self.fc2(F.relu(self.fc1(x)))))
```

Skip connections allow 4–6 block depth without degradation and are trivially portable to C++. They do not add significant inference overhead at these model sizes. Compare a 4-block residual MLP against the plain MLP winner from the depth/width search.

**Ablation efficiency:** Do not train each ablation to convergence. Train for a fixed budget (e.g., 15 epochs) and compare validation loss curves. Relative ordering of architectures is stable long before convergence. This allows more configurations to be tested at the same compute cost.

### 3d. Policy Head Experiment (Optional)

Optionally add a policy head predicting which move the human took. If move-prediction accuracy reaches ~30%+, this head may improve search quality via PUCT-style move ordering (AlphaZero approach). If accuracy is below ~20%, the signal is too weak to help. Low priority for iteration 1 but worth a quick test.

### 3e. Architecture Decision Gate

Before Phase 4, review:
- Which feature set won (Option 1 vs 2)?
- What is the optimal depth and width?
- Does validation accuracy plateau before the full dataset? (If yes: data-limited, not capacity-limited — consider self-play data generation sooner)
- Is a policy head worth including?

---

## Phase 4: Full Training Run

**Goal:** Train the chosen architecture from Phase 3 on the full training set.

### 4a. Training

- Full training set (80% of extracted records)
- Validate every epoch on validation set
- Save best checkpoint by validation accuracy
- Early stopping with patience ~10 epochs

**Rating-based sample weighting:** Rather than a hard rating floor, weight each sample by the combined rating of both players. This lets the 2200-rated games dominate gradient updates while still retaining all 102,697 games. Suggested formula:

```python
weight = ((p0_rating + p1_rating) / 4000) ** 2
# 2000+2000 → weight 1.00; 1800+1800 → weight 0.81; 1500+1500 → weight 0.56
```

This is strictly better than a hard cutoff — keeps all data but lets high-rated games dominate. Pass as `sample_weight` to the loss function. Compare vs. unweighted baseline in Phase 3.

### 4b. Regularisation

With ~6.2M records vs Churchill's 15M, overfitting risk is higher. Apply:
- Dropout: 0.1–0.3 on hidden layers
- Weight decay: L2 regularisation (1e-4 to 1e-5)
- Label smoothing: 0.05–0.15 (replaces hard 0/1 targets with softened values)

Specific values should be set based on Phase 3 observations.

### 4c. Learning Rate Schedule

Churchill used a fixed Adam LR of 1e-5. Cosine decay or step decay may improve convergence — worth a quick comparison during Phase 3 before locking in.

### 4d. Infrastructure

- Local: Intel Arc B580 (12GB VRAM, XPU backend)
- Cloud: AWS g4dn.xlarge or GCP g2-standard-4 if local is insufficient
- Monitor training vs validation curves throughout; any run where training accuracy significantly exceeds validation accuracy early should be investigated before completing

### 4e. Export and C++ Integration

- Export weights to binary format compatible with `NeuralNet.cpp`
- Verify all expected tensors are present (26 tensors required by C++ loader)
- Smoke test: load weights in C++, evaluate a known state, confirm output is in expected range

---

## Phase 5: Evaluation

**Goal:** Measure trained model strength against MCDSAI and assess whether success criteria are met.

### 5a. Tournament Setup

- Players: `PrismatAlpha_AB` with trained neural net eval vs. MCDSAI
- Games: minimum 500 for a meaningful confidence interval (at 500 games, a 5pp win rate difference is detectable at 95% confidence)
- Card sets: random card sets matching MCDSAI's normal play conditions
- Think time: 3 seconds per turn (consistent with Phase 0b benchmark)
- Report Wilson confidence interval, not just point estimate

### 5b. Success Criteria

- **Pass:** Win rate vs MCDSAI above 50% with 95% confidence (lower bound of Wilson CI > 0.50)
- **Partial pass:** Above 50% but not yet statistically significant — run more games
- **Fail:** Below 50% — investigate data pipeline and Phase 3 findings before concluding model is fundamentally too weak

### 5c. Secondary Evaluations

- Run model vs itself (expected ~50%, confirms basic sanity)
- Run vs LiveHardestAI as a stable C++ reference for future comparability
- If Prismata players are available, qualitative play sessions against the model are valuable for assessing strategic coherence that statistics may miss
- Run vs MasterBot (Steam) if move injection has been completed by this point — most meaningful real-world reference but not a blocking requirement

### 5d. Decision Gate: Proceed or Iterate?

- **Success:** Proceed to Phase 6 (self-play iteration)
- **Failure:** Diagnose root cause. Return to Phase 3 (architecture) if model architecture is suspected; Phase 1 (feature schema) if features seem inadequate; Phase 2 (data quality) if the pipeline seems suspect.
- **Partial success:** Begin self-play data generation with current model and assess whether one iteration of self-play improves it before fully rearchitecting.

---

## Opening Book

### Current State

The HPS search engine uses an opening book to bypass search for the first few turns, playing pre-computed strong sequences instead. The current book has two tiers, both extracted from the live game's AI parameters (`Prismata.swf`):

- **LiveOpeningBook** — 4 general entries: default sequences for when no specific unit triggers apply (e.g., "if Vivid Drone is in the set, open with X")
- **LiveOpeningBook2** — 50 unit-specific entries: if a particular unit appears in the card set, play a specific buy sequence for turns 1–3 (e.g., "if Tarsier is in the set, open with Animus on turn 1")

These were hand-coded by Lunarch Studios and reflect the meta-knowledge of professional game designers. They cover 50 of the 105 random-pool units explicitly. Configuration: `bin/asset/config/config.txt` under `LiveOpeningBook` and `LiveOpeningBook2`.

### Opportunity: Data-Driven Opening Book from Expert Replays

The 102,697 expert replays provide a much larger and more empirically grounded source for opening book extraction. For each card set, we can observe what 2000+ rated players actually do on turns 1–3. The existing `training/opening_book.py` was written for a previous attempt at this and may be adaptable.

**Approach:**
- Group replays by which random units are present in the card set
- For each unit (or combination of units), extract the turn-1 and turn-2 buy decisions from games in the top rating bracket (2000+)
- Find the most common buy sequence(s) for each triggering unit
- Generate opening book entries in the format already used by `config.txt`

**Why this is valuable:**
- Covers all 105 random-pool units, not just the 50 in the current hand-coded book
- Reflects actual high-level play rather than designer intuition
- Can be extracted independently of the neural training pipeline — a pure combinatorial analysis of opening data
- Strong openings reduce the importance of the early-game evaluation function, where the noisy label problem (Phase 1b) is worst

**Risks and considerations:**
- Opening book data should be extracted from the **training set only** — not from validation or test games. The validation/test split must be applied before extraction begins.
- An opening book biases the AI toward specific positions early in the game. If those positions are exactly the ones represented in training data, this could cause overfitting to the opening without improving evaluation quality more broadly. Monitor whether tournament performance depends on opening-book-covered card sets.
- Some card sets may have no clear consensus opening (multiple good lines exist). In those cases, it may be better to omit a book entry and let search find the move rather than forcing a suboptimal commitment.

**Relationship to neural training:** The opening book and the neural evaluation function are independent. Either can be improved without changing the other. However, a strong opening book effectively reduces the turns that the neural evaluator must handle well, which may make early-game label noise less consequential in practice.

**Recommended action:** Extract a data-driven opening book as a standalone Phase 0 or Phase 5 task, independent of the neural training schedule. Compare tournament results with and without the expanded book.

---

## Phase 6: Self-Play Iteration (Future Phase — Outline Only)

Out of scope for this draft but documented so reviewers can assess whether the Track A plan sets it up correctly.

### 6a. Self-Play Data Generation

- Use trained model as evaluation function in the JS engine matchup runner
- Generate a target of at least 100,000 self-play games (roughly matching human dataset size) before retraining
- Store in same schema format as human replay training data for compatibility

### 6b. Iterative Training

- Retrain on a mix of human replay data + self-play data
- Maintain human replay data in the mix throughout (never below 20% human data, following AlphaZero practice)
- Evaluate each iteration against its predecessor and against MCDSAI

### 6c. Gumbel AlphaZero Consideration

The Gumbel AlphaZero paper (Danihelka et al., ICLR 2022) proposes improved exploration during self-play by sampling actions without replacement, providing policy improvement guarantees even with few simulations. This is directly applicable to the HPS search framework and should be evaluated for self-play iteration 2+.

---

## Open Questions for Reviewers

The following questions were open in the original draft. Reviewer answers are incorporated below. Further input is welcome, particularly on Q6 which remains empirically unresolved.

1. **Feature richness:** Is Option 2 (type-count + aggregate instance flags) the right starting point, or should we begin with Churchill-exact (Option 1)? Is there a strong argument for starting with per-instance encoding (Option 3)?

   **Reviewer answer:** Start with Option 2, but run the Churchill-exact Option 1 baseline first as a Phase 3a sanity check. Option 2's instance-level flags (building, tapped, damaged) encode information that directly affects tactical evaluation — "3 Rhinos, 2 tapped" is strategically very different from "3 Rhinos, 0 tapped." The model needs these to correctly evaluate defensive positions. One addition to Option 2 worth considering: encode the **supply remaining** for each purchasable unit type (how many more can be bought). Supply exhaustion is a major strategic factor — knowing the opponent has bought 3 of 4 available Tarsiers is qualitatively different from knowing they've bought 3 of 20.

2. **Rating floor:** Should training use 1500+ (~103K games) or 1800+ (~72K games)? Higher-quality data vs. more data — what does practical Prismata experience suggest about the strategic soundness of 1500-rated play?

   **Reviewer answer:** Keep the 1500 floor, but use rating-based sample weighting (see Phase 4a) rather than a hard cutoff. V8 data shows only 0.2% of games (≈230) fall in the 1500–1599 bracket — raising the floor gains almost nothing and loses real data. Weighting is strictly better.

3. **Card set filtering:** Should training be limited to games that use the standard random-set format? Base-only games (no random units, both players use only the 11 base set cards) are strategically very different. Should they be excluded, used separately, or included?

   **Reviewer answer:** Yes, exclude base-only games from the primary training set. Base-only Prismata is a strategically distinct subgame with no relevance to competitive play (which always includes random units). Measure their count in Phase 0d. If there are enough (500+), they can be used for a side experiment. Do not contaminate the main dataset.

4. **Value target:** Churchill predicted game winner as the training target. An alternative is to predict final resource advantage (a graded signal rather than binary). Which is more appropriate for Prismata, where games are often strategically decided well before they technically end?

   **Reviewer answer:** Binary win outcome (with the soft-label modification from Phase 1b) is correct. A graded resource-advantage target has significant problems: it requires defining "resource advantage" in a unit-composition-dependent way, and games where one player sacrifices short-term resources for a strategic position (breaching to kill key units) would be mislabelled. Win prediction is the right target — the soft-labelling fixes the noise issue without changing what the model learns to predict.

5. **Architecture prior:** Churchill used a plain MLP. Leela Chess Zero and AlphaZero use residual networks. Is there a theoretical or empirical reason to prefer ResNet-style skip connections for this problem, or is a plain MLP sufficient given the flat (non-sequential) nature of the feature vector?

   **Reviewer answer:** Residual (skip) connections in an MLP are nearly free and do help. Full ResNets are designed for spatial/grid inputs — Prismata's state doesn't have that structure, so convolutions add nothing. However, residual MLP blocks (see Phase 3c) allow going deeper without degradation and are trivially portable to C++. Test this against the plain MLP winner in Phase 3.

6. **MCDSAI calibration:** Is beating MCDSAI a meaningful training milestone? What do experienced Prismata players estimate MCDSAI's skill level to be in terms of human rating equivalence?

   **Status: partially resolved — Phase 0b tournament is currently in progress (512 games, LiveHardestAI vs MCDSAI).** Results will anchor the success criterion with a concrete win rate reference. One addition from reviewers: also run MCDSAI vs. itself at different think times (1s vs 7s) to see how much search depth matters for MCDSAI specifically. If MCDSAI gains substantially from more think time, the eval function is the bottleneck (good — that's what this project addresses). If it barely improves, the search framework itself may be the ceiling.

---

## What This Plan Does Not Cover

- Specific hyperparameter grid search methodology (to be detailed after architecture is selected in Phase 3)
- Cloud compute provisioning specifics (to be planned once data scale is confirmed in Phase 0)
- C++ NeuralNet integration changes (existing infrastructure reused; only weight file format must remain compatible)
- Multi-GPU training (not needed at this data scale)
- Policy learning beyond move ordering in search

---

## References

- Churchill, D. & Buro, M. (2015). *Hierarchical Portfolio Search: Prismata's Robust AI Architecture for Games with Large Search Spaces.* AIIDE 2015.
- Churchill, D. (2019). *Machine Learning State Evaluation in Prismata.* AIIDE Workshop 2019.
- Danihelka, I. et al. (2022). *Policy Improvement by Planning with Gumbel.* ICLR 2022.
- Hubert, T. et al. (2021). *Learning and Planning in Complex Action Spaces (Sampled MuZero).* ICML 2021.
- Landers, M. et al. (2025). *SAINT: Attention-Based Policies for Discrete Combinatorial Action Spaces.*
- Sokota, S. et al. (2025). *Superhuman AI for Stratego Using Self-Play Reinforcement Learning and Test-Time Search.*
