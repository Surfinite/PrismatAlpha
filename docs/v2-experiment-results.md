# V2 Hyperparameter Experiment Results

**Date:** Feb 17, 2026
**Data:** ~1M records (~27K games) from self-play, `--max-records 1000000`
**Base config:** value-only, batch_size=512, dropout=0.1, weight_decay=1e-4, eval-every-steps=1000

## Consolidated Results

| Exp ID | Run Timestamp | LR | Hidden | Loss | Tanh | Subsample | Best Val Loss | Best Brier | Best Epoch | Best Step |
|--------|---------------|-----|--------|------|------|-----------|---------------|------------|------------|-----------|
| (pre) | 20260217_082528 | 3e-4 | 256 | MSE | false | 1 | 0.5633 | N/A | 1 | N/A |
| E0c | 20260217_090701 | 3e-4 | 512 | MSE | false | 1 | 0.5068 | 0.1256 | 1 | 1000 |
| **E0a** | 20260217_091108 | 3e-4 | 512 | MSE | **true** | 1 | 0.4875 | 0.1230 | 1 | 1000 |
| E0b | 20260217_091628 | 3e-4 | 512 | BCE | false | 1 | 0.4534 | 0.1241 | 1 | 1000 |
| E1c | 20260217_092339 | 1e-5 | 512 | MSE | true | 1 | 0.4966 | 0.1259 | 3 | 5000 |
| E1a | 20260217_092353 | 1e-4 | 512 | MSE | true | 1 | 0.4954 | 0.1250 | 1 | 1000 |
| E1b | 20260217_100526 | 3e-5 | 512 | MSE | true | 1 | 0.4876 | 0.1236 | 2 | 2000 |
| E2a-512 | 20260217_100811 | 1e-5 | 512 | MSE | true | 3 | 0.5056 | 0.1275 | 10 | 6000 |
| **E2b** | 20260217_100819 | 1e-5 | 256 | MSE | true | 1 | 0.4769 | **0.1213** | 6 | 10000 |
| E2a-256 | 20260217_102444 | 1e-5 | 256 | MSE | true | 3 | 0.4921 | 0.1250 | 14 | 8000 |
| E1b-re | 20260217_104425 | 3e-5 | 512 | MSE | true | 1 | 0.4920 | 0.1255 | 2 | 2000 |
| **E2b-final** | 20260217_105447 | 1e-5 | 256 | MSE | true | 1 | 0.4752 | **0.1210** | 6 | 10656 |

## Key Findings

1. **Tanh fix works** (E0a vs E0c): Brier 0.1230 vs 0.1256. Applying tanh during training improves loss landscape.
2. **MSE vs BCE is a wash**: E0a (Brier 0.1230) vs E0b (Brier 0.1241). Sticking with tanh+MSE.
3. **LR controls overfitting speed, not ceiling**: All LRs with 512h converge to ~0.125 Brier.
4. **Smaller model wins**: E2b (256h) achieves Brier 0.1210, best overall. 512h is overparameterized.
5. **Subsampling hurts**: E2a worsens Brier at both model sizes. More data helps even if correlated.
6. **Step-level eval essential**: Best step ranges from 1000 (high LR) to 10656 (E2b winner).

## Winner: E2b (256h, LR=1e-5, tanh+MSE)

- Best Brier: 0.1210
- Best Val Loss: 0.4752
- Best Val Acc: 78.6%
- Model params: 739K (vs 2M for 512h)
- Weights exported to: `bin/asset/config/neural_weights_E2b.bin`

## Tournament Evaluation — INCOMPLETE

Launched Feb 17 ~11:15, 500 rounds each, 4 threads:
- `bin_eval_256/`: E2b weights (256h) vs OriginalHardestAI — games in progress, no final WR
- `bin_eval_512/`: E1b weights (512h) vs OriginalHardestAI — games in progress, no final WR

## Experiment Plan Reference

See `docs/plans/hyperparameter-experiments-v2.md` for the original experiment design.
Run JSON files: `training/runs/20260217_*.json`
