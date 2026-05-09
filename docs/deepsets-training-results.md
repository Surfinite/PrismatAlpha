# DeepSets Training Results & Status

**Date:** 2026-05-09 (compiled from on-disk training logs and matchup data, March 2026)
**Companion to:** `docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md`
**Status:** Models trained and exported to C++ inference. Tournament strength gated by upstream AI parity gap.

---

## TL;DR

A DeepSets evaluator was implemented per the March 11 design spec, trained on three data variants (MB-only, human-only, mixed), and exported into the C++ engine as five DSNN (DeepSets Neural Network) player configurations. Validation accuracy reached **78–82%** depending on data source.

Tournament strength did **not** improve correspondingly. The bottleneck is upstream of the model: a Mar 17 single-unit sweep showed our `LiveHardestAIUCT` baseline wins only **~20%** of games against Steam's `STEAMAI` (a.k.a. MasterBot), with **60% of units losing 0-of-4** in like-for-like matchups. Until that parity gap closes, a stronger evaluator on a weaker engine yields little.

---

## Architecture Summary

Per the [design spec](superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md):

- **Per-instance tokens** (55 floats): 32-dim learned unit embedding + 13 static properties from `cardLibrary.jso` + 10 instance-state features (HP, build-timer, freeze, lifespan, charges, etc.)
- **Shared encoder MLP** (55 → 128 → 128 with ReLU)
- **Sum-pool by owner** → P0_pool, P1_pool (128-dim each)
- **Separate supply pathway** (3 floats per unit type → 32, summed across all 116 types)
- **Value MLP head** (302 → 256 → 256 → 1, dropout 0.1) → P(P0 wins)
- **~172K trainable parameters** (vs ~920K for the prior flat MLP baseline)

All code on master: [training/model_deepsets.py](../training/model_deepsets.py), [training/vectorize_v2.py](../training/vectorize_v2.py), [training/export_weights_v2.py](../training/export_weights_v2.py). C++ inference rewrite in [source/ai/NeuralNet.cpp](../source/ai/NeuralNet.cpp).

---

## Training Runs

All three runs used: lr=3e-4, batch=512, dropout=0.1, weight_decay=1e-4, label_strategy=A (hard binary outcome), 100 epoch cap with patience=15.

| Run | Compute | Train data | Train examples | Val file | Best epoch | **Val acc** | Brier | Wall time |
|---|---|---|---|---|---|---|---|---|
| **MB-only** | AWS (g6.2xlarge spot) | MB-fleet self-play (`fleet_v3` + `fleet_v4`) | ~12M | local_mbvmb.h5 | 98 (SWA¹) | **82.4%** | 0.113 | ~1 day |
| **Human-only** | local XPU | 97K expert replays² | 2.49M | local_mbvmb.h5 | 26 (early stop) | **78.2%** | 0.138 | 8,536s (2.4h) |
| **Mixed** | AWS (g6.2xlarge spot) | MB self-play + human | 14.7M | local_mbvmb.h5 | — | **82.2%** | — | ~1 day |

¹ SWA = Stochastic Weight Averaging (Izmailov et al, 2018) — running average of weights over the late training trajectory.
² Filter: both players rated ≥1500 on the live ladder; games using the 6-card fixed-set format excluded.

Local artifact for the human-only run: `training/models/deepsets_human_local/`. Full per-epoch metrics in `training_log.json` there.

### Notes & caveats

- **Label-inversion bug fixed before these runs.** An earlier human pipeline mapped `result=0` (P1-wins) directly to `outcome_p0=0`, which was inverted. Detected via P0 win rate diverging from MB pipeline (51.1% vs 43.1%). Fixed by `outcome_p0 = 1.0 - float(result)` for win/loss, 0.5 for draws. The 78.2% figure above is post-fix.
- **All three runs validated against the same MB-flavoured val set** (`local_mbvmb.h5`). Human-only's 78.2% on an MB-distribution validation set is therefore a transfer measurement, not in-distribution accuracy.
- **Mixed barely beats MB-only** (82.2% vs 82.4%). Adding human data to the MB corpus did not meaningfully raise headline accuracy — though it may help on game phases or matchups underrepresented in self-play, which wasn't measured.
- **172K parameters across all variants.** No architecture sweep was run within DeepSets (encoder depth/width, embedding dim, value-head width). The Open Questions in the spec list these as deferred ablations.

### Exported weights

Five DSNN player configurations live in `bin/asset/config/`:

| Player | Weights | Source run |
|---|---|---|
| `DSNN_MBonly` | `neural_weights_mbonly.bin` | MB-only ep98 |
| `DSNN_MBonly_SWA` | `neural_weights_mbonly_swa.bin` | MB-only SWA average |
| `DSNN_Human` | `neural_weights_human.bin` | Human-only ep26 |
| `DSNN_Mixed` | `neural_weights_mixed.bin` | Mixed final |
| `DSNN_Mixed_SWA` | `neural_weights_mixed_swa.bin` | Mixed SWA |

All use UCT search + NeuralNet eval + LiveHardestAI opening book. Weight format: `DSN2` binary (header + named tensors) per [docs/WEIGHT_FORMAT.md](WEIGHT_FORMAT.md).

---

## The Tournament-Strength Gap

Validation accuracy on the local val set is not the same as tournament strength against the live game's MasterBot. The model trains successfully, but downstream play strength is gated by the search engine and policy stack it sits on top of.

### Single-Unit Sweep — Mar 17, 2026

The hypothesis from community feedback (e.g. Elyot's claim that "the only thing changed between Dave's code and the live game was the opening book for new units") would predict that `LiveHardestAIUCT` should perform comparably to live MasterBot on most units, with divergences concentrated in post-launch units lacking opening-book entries.

The sweep tested this directly: **105 units × 4 games each = 418 games**, `LiveHardestAIUCT` vs `STEAMAI` (the wrapper for Steam's `PrismataAI.exe`, i.e. live MasterBot). Each game had only the named unit as the variable card. Think times were **asymmetrically favourable to Live**: 10s for Live, 5s for Steam. Color-balanced via `--player-switch`.

Raw data: [js_engine/sweep_results.jsonl](../js_engine/sweep_results.jsonl).

### Headline numbers

| Bucket | Units | % of total |
|---|---|---|
| Live loses 0/4 (≤0% WR) | 63 | **60%** |
| Live underperforms (>0%, <40% WR) | 4 | 4% |
| Roughly even (40–60% WR) | 36 | 34% |
| Live wins ≥75% (≥3/4) | 2 | 2% |

**Overall LiveHardestAIUCT win rate vs STEAMAI: 20.1%.**

### Interpretation

The community claim that only the opening book differs between Dave's published code and the live game is **not supported by this data**. If it were, we'd expect a small set of post-launch units (those without opening-book entries) to show parity gaps and the rest to be near 50/50. Instead:

- Approximately **two-thirds of all units** (67/105) show Live materially underperforming Steam.
- The 0/4 outcomes are concentrated heavily, suggesting systemic AI-behavior differences rather than opening-book-only divergence.
- Only ~36% of units show genuine parity.

Whether the divergences are heuristic-weight changes, partial-player ordering, ability-targeting logic, or evaluation tuning is not yet known — the sweep identifies *where* parity fails but not *why*. Replays for each per-unit run are saved under `bin/asset/replays/2026-03-17_*_LiveUCTVsMB_SingleUnit_UnevenThink_*` for inspection.

### Implication for the trained models

A neural evaluator improves play strength only to the extent that the surrounding search and policy stack can act on its evaluations effectively. With a base AI losing ~80% of these single-unit matchups against MasterBot — and 100% on a majority of units — the upstream parity gap dominates whatever signal the value head provides. The DSNN players are therefore in a holding pattern: the eval works as a research artefact, but won't translate to tournament results until the engine's AI behaviour matches the live game more closely.

This re-orders the practical roadmap: **AI parity work has to come before further training data investment.**

---

## Open Questions

- **Source of the parity gap.** The single-unit sweep tells us *where* divergence appears but not *why*. Reading the engine-logic audit findings ([docs/audit/](audit/)) plus inspecting per-unit replays where Live loses 0/4 should narrow this. Likely candidates: heuristic resource weights, the `Ability_Filter` set, partial-player ordering, defense assignment logic.
- **Architecture ablations.** Encoder depth/width, embedding dim, value-head width were not swept within DeepSets. The 172K-param baseline is a starting point, not a tuned configuration. Listed as deferred in the spec's Open Questions.
- **Policy head.** Not implemented. The current model is value-only. A policy head on the pooled representation could enable PUCT (currently disabled in `config.txt` pending policy >30% accuracy).
- **Mixed run gain analysis.** Headline accuracy was indistinguishable from MB-only; whether human data helps in specific subsets (early game, particular matchups) was not measured.
- **In-distribution human accuracy.** All three runs validated on the MB-flavoured set. Human-only's 78.2% there is a transfer measurement; in-distribution accuracy on a held-out human val set was not separately reported.

---

## Related artefacts

- [training/model_deepsets.py](../training/model_deepsets.py) — model
- [training/models/deepsets_human_local/training_log.json](../training/models/deepsets_human_local/training_log.json) — full per-epoch metrics for the human-only run
- [docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md](superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md) — design rationale
- [docs/superpowers/plans/2026-03-11-deepsets-implementation.md](superpowers/plans/2026-03-11-deepsets-implementation.md) — task breakdown
- [docs/discord-masterbot-feedback-analysis.md](discord-masterbot-feedback-analysis.md) — community-documented MasterBot behavioural quirks (relevant to the parity gap)
- [js_engine/run_single_unit_sweep.js](../js_engine/run_single_unit_sweep.js) + [js_engine/sweep_results.jsonl](../js_engine/sweep_results.jsonl) — sweep runner and raw data
