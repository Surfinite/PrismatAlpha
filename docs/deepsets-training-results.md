# DeepSets Training Results & Status

**Date:** 2026-05-14
**Companion to:** `docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md`

---

## TL;DR

A DeepSets evaluator was implemented per the March 11 design spec, trained on three data variants (MB-only, human-only, mixed), and exported into the C++ engine as five DSNN player configurations. Validation accuracy reached **78–82%** depending on data source.

Tournament strength did not improve correspondingly. A Mar 17 single-unit sweep showed `LiveHardestAIUCT` winning only ~20% of games against Steam's `STEAMAI`, with 60% of units losing 0-of-4. A May 14 head-to-head ablation showed `DSNN_MBonly` losing 30% to 66.9% against the playout-eval baseline on the same engine.

---

## Architecture Summary

Per the [design spec](superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md):

- **Per-instance tokens** (55 floats): 32-dim learned unit embedding + 13 static properties from `cardLibrary.jso` + 10 instance-state features (HP, build-timer, freeze, lifespan, charges, etc.)
- **Shared encoder MLP** (55 → 128 → 128 with ReLU)
- **Sum-pool by owner** → P0_pool, P1_pool (128-dim each)
- **Separate supply pathway** (3 floats per unit type → 32, summed across all 116 types)
- **Value MLP head** (302 → 256 → 256 → 1, dropout 0.1) → P(P0 wins)
- **~172K trainable parameters**

Code on master: [training/model_deepsets.py](../training/model_deepsets.py), [training/vectorize_v2.py](../training/vectorize_v2.py), [training/export_weights_v2.py](../training/export_weights_v2.py). C++ inference in [source/ai/NeuralNet.cpp](../source/ai/NeuralNet.cpp).

---

## Training Runs

All three runs used: lr=3e-4, batch=512, dropout=0.1, weight_decay=1e-4, label_strategy=A (hard binary outcome), 100 epoch cap with patience=15.

| Run | Compute | Train data | Train examples | Val file | Best epoch | **Val acc** | Brier | Wall time |
|---|---|---|---|---|---|---|---|---|
| **MB-only** | AWS (g6.2xlarge spot) | MB-fleet self-play (`fleet_v3` + `fleet_v4`) | ~12M | local_mbvmb.h5 | 98 (SWA) | **82.4%** | 0.113 | ~1 day |
| **Human-only** | local XPU | 97K expert replays | 2.49M | local_mbvmb.h5 | 26 (early stop) | **78.2%** | 0.138 | 8,536 s |
| **Mixed** | AWS (g6.2xlarge spot) | MB self-play + human | 14.7M | local_mbvmb.h5 | — | **82.2%** | — | ~1 day |

Human filter: both players rated ≥1500 on the live ladder; 5-card-format games excluded.

**Label-inversion bug fixed before these runs.** An earlier human pipeline mapped `result=0` (P1 wins) to `outcome_p0=0`, which was inverted. Detected via P0 win rate diverging from MB pipeline (51.1% vs 43.1%). Fixed by `outcome_p0 = 1.0 - float(result)` for win/loss, 0.5 for draws.

All three runs validated against the same MB-flavoured val set (`local_mbvmb.h5`). Human-only's 78.2% is therefore a transfer measurement, not in-distribution accuracy.

---

## Exported Weights

Five DSNN player configurations live in `bin/asset/config/`:

| Player | Weights | Source run |
|---|---|---|
| `DSNN_MBonly` | `neural_weights_mbonly.bin` | MB-only ep98 |
| `DSNN_MBonly_SWA` | `neural_weights_mbonly_swa.bin` | MB-only SWA average |
| `DSNN_Human` | `neural_weights_human.bin` | Human-only ep26 |
| `DSNN_Mixed` | `neural_weights_mixed.bin` | Mixed final |
| `DSNN_Mixed_SWA` | `neural_weights_mixed_swa.bin` | Mixed SWA |

Weight format: DSN2 binary, [docs/WEIGHT_FORMAT.md](WEIGHT_FORMAT.md).

---

## Players in the comparison

| Player | What it is |
|---|---|
| `LiveHardestAIUCT` | `HardestAIUCT` + `LiveOpeningBook2` (extracted from SWF) + playout eval |
| `DSNN_*` | Same engine and OB as above; eval swapped to `"Eval":"NeuralNet"` with the respective weights file |
| `STEAMAI` | Steam's `PrismataAI.exe` driven via the SWF's JSON request protocol |

---

## Single-Unit Sweep — Mar 17, 2026

**105 units × 4 games each = 418 games**, `LiveHardestAIUCT` vs `STEAMAI`. Each game had only the named unit as the variable card. Think times: 10 s for Live, 5 s for Steam. Colour-balanced via `--player-switch`.

| Bucket | Units | % of total |
|---|---|---|
| Live loses 0/4 | 63 | **60%** |
| Live underperforms (>0%, <40% WR) | 4 | 4% |
| Roughly even (40–60% WR) | 36 | 34% |
| Live wins ≥75% | 2 | 2% |

**Overall `LiveHardestAIUCT` WR vs `STEAMAI`: 20.1%.**

Raw data: [js_engine/sweep_results.jsonl](../js_engine/sweep_results.jsonl).
Replays: `bin/asset/replays/2026-03-17_*_LiveUCTVsMB_SingleUnit_UnevenThink_*`.

---

## DSNN vs Playout — Head-to-Head Ablation (May 14, 2026)

```bash
node matchup_clean.js \
  --games 800 --parallel 8 --think-time 5000 --player-switch \
  --player-white DSNN_MBonly --player-black LiveHardestAIUCT \
  --save-replays DSNNvsLiveHardestAIUCT-800
```

- **800 games**, organised as 400 colour-swapped pairs via `--player-switch`
- **5 s think time per turn**, 8 parallel workers
- Both players use UCT search with the `LiveHardestAI_Root` move iterator (so `LiveOpeningBook2` is consulted by both sides) and the same time / max-traversal limits
- The only difference between the two players is the evaluator:
  - `DSNN_MBonly`: `"Eval":"NeuralNet"` with `neural_weights_mbonly.bin` (DeepSets MB-only model, epoch 98 SWA, val acc 82.4%)
  - `LiveHardestAIUCT`: `"Eval":"Playout"` with the `Live_Playout` partial-player

| Metric | Value |
|---|---|
| Total games | 800 |
| **`DSNN_MBonly` WR (seat-independent)** | **30.0%** |
| **`LiveHardestAIUCT` WR (seat-independent)** | **66.9%** |
| Draws | 25 (3.1%) |
| Avg game length | 36 turns |
| Invalid games | 0 |

Pair breakdown (400 pairs):

| Outcome | Count |
|---|---|
| `LiveHardestAIUCT` sweeps 2-0 | 193 |
| Split (1-1) | 174 |
| `DSNN_MBonly` sweeps 2-0 | 33 |

Raw colour tally:

| Colour | Wins | % |
|---|---|---|
| White | 330 | 41.3% |
| Black | 445 | 55.6% |

Replays: `bin/asset/replays/2026-05-14_12-50-09_DSNNvsLiveHardestAIUCT-800/`. Run log: `js_engine/DSNNvsLiveHardestAIUCT-800_2026_05_14.log`.

Interpretation deferred.

---

## Planned next steps

A May 14 inspection of the SWF showed that the 50-entry `LiveOpeningBook2` used by `LiveHardestAIUCT` is not the opening book live MasterBot uses. The OB actually fed to `PrismataAI.exe` at `HardestAI` difficulty comes from the SWF's *short*-params blob (`93_*.bin`) and contains 120 different entries.

- Extract those 120 entries into `config.txt`, wire them into a new player config, and re-run the single-unit sweep against `STEAMAI` to see whether the parity gap closes.
- Re-run the DSNN-vs-playout ablation with the corrected OB applied to both sides.

---

## Related artefacts

- [training/model_deepsets.py](../training/model_deepsets.py) — model
- [training/models/deepsets_human_local/training_log.json](../training/models/deepsets_human_local/training_log.json) — per-epoch metrics for human-only run
- [docs/superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md](superpowers/specs/2026-03-11-deepsets-schema-redesign-design.md) — design rationale
- [docs/superpowers/plans/2026-03-11-deepsets-implementation.md](superpowers/plans/2026-03-11-deepsets-implementation.md) — task breakdown
- [js_engine/run_single_unit_sweep.js](../js_engine/run_single_unit_sweep.js) + [js_engine/sweep_results.jsonl](../js_engine/sweep_results.jsonl) — sweep runner and raw data
