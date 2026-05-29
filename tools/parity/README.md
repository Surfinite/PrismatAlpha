# DSNN PyTorch ↔ C++ value-parity harness

Proves the DSNN port's C++ DeepSets inference reproduces the PyTorch reference value
numerically. Built for the port-faithfulness review of commit `829dcac`.

## Components

- **C++ dump hook** (committed into the engine):
  - `source/ai/NeuralNet.cpp` / `.h`: `dumpFeaturesJSON(state, path)` — runs the *real*
    in-play `evaluateValue(state, Player_One)` (so the dumped value IS the value the UCT
    search uses), then emits the P0-perspective value, the raw value-head logit, the
    14 normalized globals, every alive instance's `unit_index` + 10 instance features, the
    buyable supply, and any alive card that mapped to `-1` (`dropped_instances`, risk 5).
    A single instrumentation line in `evaluateValue` captures the logit
    (`_scratch.lastLogit = logit;`) — it stores an already-computed value and cannot change
    the return value.
  - `source/standalone/main.cpp`: `--dump-features <gameState.json> <out.json> [weights.bin]`
    entry point (built into Release `bin/PrismataAI.exe`). Run from `bin/`.
- **Python comparators** (this dir):
  - `compare_parity.py` — Tier B: feeds the C++-emitted tokens into (1) the tied-out
    PyTorch `.pt` and (2) the numpy forward over the shipped `.bin`, and compares logits +
    values to the C++ dump. Isolates forward-math + weight-load faithfulness.
  - `tier_a_check.py` — Tier A: verifies the C++ tokens correctly represent the state
    (name→unit_index mapping, owner feature, per-owner instance counts vs the source
    gameState, hp_ratio bounds, no dropped instances). Catches feature-build bugs that
    Tier B alone cannot.
- `states/state_0{1..5}_*.json` — five fixed gameStates (turn-1 opener; near-terminal with
  construction+damage; charges+lifespan; high resources; large late-game N=121), extracted
  from real engine-produced `_suggest_state` snapshots.
- `out_state_*.json` — the C++ dumps for those states.

## Reference checkpoint

The `.pt` proven to re-export byte-identical to `bin/asset/config/neural_weights_mbonly.bin`
(695,411 B, sha256 `817ab7f9…`) is the **only** match of 19 candidates:
`C:/libraries/PrismataAI/training/cloud-runs/deepsets_12M_full/2026-03-13_05-44-21/models/best_model.pt`
(ep98, val_value_acc 0.8231). NOTE: `training/models/best_model.pt` is a 2-epoch smoke test
— wrong weights despite matching size+header. `compare_parity.py` pins the correct path.

## Reproduce

```bash
# 1. C++ dumps (from dave bin/, Release PrismataAI.exe with the hook):
cd c:/libraries/PrismataAI-dave-master/bin
for s in 01_turn1 02_constr_damage 03_charges_lifespan 04_high_resources 05_late_large; do
  ./PrismataAI.exe --dump-features ../tools/parity/states/state_${s}.json ../tools/parity/out_state_${s}.json
done

# 2. Tier B (PyTorch + numpy vs C++):
cd c:/libraries/PrismataAI-dave-master/tools/parity
python compare_parity.py out_state_*.json

# 3. Tier A (feature build vs source state):
python tier_a_check.py states/state_01_turn1.json out_state_01.json   # ...repeat per state
```

## Result (this review)

All 5 states PASS. Worst `|value_cpp − value_torch| = 1.33e-6` (tol 1e-3); logits agree with
PyTorch and numpy to ~1e-5. Tier A: every alive card mapped 1:1, 0 dropped, owner/index
correct. Conclusion: the C++ DeepSets value is a faithful reproduction of the PyTorch model.
