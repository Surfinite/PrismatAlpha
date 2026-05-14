# DeepSets Training Results & Status

**Date:** 2026-05-13 (parity-gap framing refined; initial compilation 2026-05-09)
**Companion to:** `docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md`
**Status:** Models trained and exported to C++ inference. Tournament strength gated by an upstream AI parity gap whose most likely cause is opening-book modifications compiled into Steam's `PrismataAI.exe` (see Interpretation).

---

## TL;DR

A DeepSets evaluator was implemented per the March 11 design spec, trained on three data variants (MB-only, human-only, mixed), and exported into the C++ engine as five DSNN (DeepSets Neural Network) player configurations. Validation accuracy reached **78–82%** depending on data source.

Tournament strength did **not** improve correspondingly. The bottleneck is upstream of the model: a Mar 17 single-unit sweep showed our `LiveHardestAIUCT` baseline wins only **~20%** of games against Steam's `STEAMAI` (a.k.a. MasterBot), with **60% of units losing 0-of-4** in like-for-like matchups.

A May 13 follow-up trace through the SWF AS3 makes the most parsimonious explanation: Elyot's stated *"only the opening book was really changed"* is plausibly correct, but the modifications live inside the compiled `PrismataAI.exe` binary itself rather than in any externally-loadable asset. The opening book we extracted from the SWF (`LiveOpeningBook2`) and applied to our open-source AI is a different artefact — almost certainly older or never-deployed — and never closes the gap. Until Elyot's compiled-in OB is recovered (via collaboration, RE of the binary, or empirical reconstruction), a stronger evaluator on the existing open-source engine yields little.

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

### Players in the comparison

The names in this section are inherited from the engine's config and don't perfectly self-describe. To avoid confusion (config refs are `bin/asset/config/config.txt`):

- **`LiveHardestAIUCT`** is Dave Churchill's `HardestAIUCT` — the UCT/MCTS variant of his open-source `HardestAI` baseline — with one thing we built on top: the 50-entry opening book extracted from the decompiled SWF (`LiveOpeningBook2`, applied via the `LiveHardestAI_Root` move iterator). The evaluator is still Dave's original **playout eval** (`"Eval":"Playout"`) — not DSNN. The "Live" prefix originally reflected the intent of *"configured to match the live game"*, but the SWF-extracted opening book has since been shown not to be what live MasterBot actually uses (see Interpretation, below). The name is kept here for continuity with the existing config; it should not be read as *"the live MasterBot AI"* — only as *"Dave's HardestAIUCT with the SWF opening book bolted on."*
- **`DSNN_MBonly`, `DSNN_MBonly_SWA`, `DSNN_Human`, `DSNN_Mixed`, `DSNN_Mixed_SWA`** share the same engine skeleton as `LiveHardestAIUCT` (UCT search, same time limits, same `LiveHardestAI_Root` opening-book-aware move iterator) but swap the evaluator for **`"Eval":"NeuralNet"`** loading the respective DSN2 weight file. These are the players that actually use the trained DeepSets evaluator.
- **`STEAMAI`** wraps Steam's native `PrismataAI.exe` binary — the actual live MasterBot — and drives it via the same JSON request protocol that the SWF uses.

**Important caveat:** the Mar 17 single-unit sweep below was run with `LiveHardestAIUCT` (playout eval) vs `STEAMAI`, **not** with any of the `DSNN_*` variants. So the sweep measures the **playout-eval baseline's** parity gap against MasterBot, not the trained models' gap. The DSNN players' behaviour in the same matchup has not been directly measured — see *Implication for the trained models* and *Open Questions* below.

### Single-Unit Sweep — Mar 17, 2026

A natural reading of Elyot's stated claim that *"the only thing changed between Dave's code and the live game was the opening book for new units"* would predict that `LiveHardestAIUCT` (which has *an* opening book extracted from the SWF applied) should perform comparably to live MasterBot on most units. The sweep tested this directly.

**105 units × 4 games each = 418 games**, `LiveHardestAIUCT` vs `STEAMAI`. Each game had only the named unit as the variable card. Think times were **asymmetrically favourable to Live**: 10s for Live, 5s for Steam. Color-balanced via `--player-switch`.

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

The headline result — `LiveHardestAIUCT` winning ~20% of single-unit matchups with **60% of units losing 0/4** — establishes that the divergence is large and systematic. The initial reading of this data (May 2026, captured in earlier versions of this doc) was *"the gap is more than just the opening book, contradicting Elyot's claim."* A May 13 follow-up trace through the decompiled SWF shows that reading is wrong. The corrected picture:

**The SWF opening book is not what live MasterBot actually uses.** The AS3 code in `prismata_decompiled/scripts/AI/AIThreadHandler.as` (lines 297–303, 340–347) explicitly omits the opening-book portion of the AI parameter blob when the difficulty is `HardestAI` (the difficulty live MasterBot runs at). That decision is encoded in an `AI_NO_OPENINGS` list at line 110. The 50-entry `LiveOpeningBook2` we extracted from the SWF is present in the binary asset but never fed into the AI loop at runtime for the relevant difficulty. It is most likely a relic — an older opening-book version, or one that was never wired into the deployed AI path.

**The most parsimonious explanation for the parity gap is therefore:** Elyot's opening-book modifications live inside the compiled `PrismataAI.exe` binary itself, not in any externally-loadable asset. The SWF OB we extracted is a different artefact — likely older or never-deployed. Under this theory, Elyot's *"only the opening book was really changed"* claim is plausibly correct, but the modified opening book is not recoverable from any public source: it is compiled into the .exe.

This explanation accommodates all the observations:
- Elyot's stated claim that "only the opening book was changed"
- AS3 not feeding the SWF OB to `PrismataAI.exe` for `HardestAI`
- `LiveHardestAIUCT` losing 60% of units 0/4 despite having `LiveOpeningBook2` applied (it has the *wrong* OB — different from whatever is compiled into the .exe)
- Our training data (PrismataAI.exe self-play) accurately reflecting live MasterBot behaviour — the .exe's compiled-in OB is in effect regardless of what aiParameters we pass it

What we **don't yet have** is direct verification that `PrismataAI.exe` actually contains a compiled-in opening book. That is the next concrete test (see Open Questions).

Replays for each per-unit run are saved under `bin/asset/replays/2026-03-17_*_LiveUCTVsMB_SingleUnit_UnevenThink_*` for inspection.

### Implication for the trained models

A neural evaluator improves play strength only to the extent that the surrounding search and policy stack can act on its evaluations effectively. With the playout-eval baseline losing ~80% of single-unit matchups against MasterBot, the upstream parity gap dominates whatever signal a value head sitting on top of the same engine could provide.

Under the OB-in-binary theory, the practical roadmap looks like:

- **Recovering Elyot's modified opening book** is the most likely-shaped lever to close the gap against MasterBot.
- **Recovery paths**, in rough order of effort: (a) Elyot sharing the source modifications, (b) extracting compiled-in OB data from `PrismataAI.exe` via reverse-engineering (strings dump, disassembly), (c) reconstructing the OB empirically from observed MasterBot play across many positions.
- **Additional training will not fix this.** The trained models are already learning to reproduce `PrismataAI.exe` behaviour — including whatever OB it has compiled in. The bottleneck for the *MasterBot-parity* goal is the open-source engine's playing strategy on OB-relevant positions, not the evaluator's accuracy.

**Untested but important — the DSNN evaluator ablations:** because the sweep used `LiveHardestAIUCT` (playout eval) and not any `DSNN_*` variant, we do not yet have data on:

- **Does DSNN beat the playout baseline?** `DSNN_MBonly` vs `LiveHardestAIUCT` head-to-head with the same OB and same search would isolate the evaluator's contribution from the parity gap. A clear DSNN win means the eval *is* adding signal within the broken engine, and recovering the OB would unlock it. A wash means the eval isn't doing useful work even with everything else held equal.
- **Does DSNN narrow the gap to MasterBot?** Re-running the single-unit sweep with `DSNN_MBonly` instead of `LiveHardestAIUCT` would tell us whether the evaluator buys back any of the ~80% loss rate. Even a marginal improvement here would be informative.

Without those ablations, this doc's claims about "the DSNN players are in a holding pattern" are inferred from the playout-eval result, not measured. Worth doing the head-to-head ablation before any further training data investment.

The DSNN players are therefore in a holding pattern: the eval is a usable research artefact, but won't translate to tournament results until the open-source engine has access to the same opening-book information that's compiled into the deployed binary.

---

## Open Questions

- **Verifying the OB-in-binary theory.** The current working theory (May 13 SWF trace) is that the parity gap is opening-book-shaped and that Elyot's modifications are compiled into `PrismataAI.exe`. Direct verification path: a strings dump of `PrismataAI.exe` looking for OB-shaped data (e.g. `strings PrismataAI.exe | grep -B1 -A3 'self":'` to find embedded JSON-formatted OB entries). Low effort, potentially conclusive. If structured OB data turns up, the theory is confirmed and the next question becomes how to extract and apply it. If nothing OB-shaped is found, the gap is somewhere else and earlier candidates re-enter the picture: heuristic resource weights, the `Ability_Filter` set, partial-player ordering, defense assignment logic.
- **DSNN ablation 1 — does the evaluator help the search?** `DSNN_MBonly` vs `LiveHardestAIUCT` head-to-head (same search, same OB, only eval differs). 400 games with `--player-switch` is enough to detect a ~5% WR difference. A clear DSNN win means the eval is adding signal even within the broken engine; a wash means it isn't. This experiment has no dependency on MasterBot and can run locally any time.
- **DSNN ablation 2 — does the evaluator narrow the gap to MasterBot?** Re-run the Mar 17 single-unit sweep methodology but with `DSNN_MBonly` (and/or other variants) instead of `LiveHardestAIUCT`. Tells us whether the evaluator buys back any of the ~80% loss rate against `STEAMAI`. Combined with ablation 1, this gives a clean read of where DSNN's value (if any) lives.
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
