# Handoff prompt — add train.py resume + clean re-run of the 35-prop mixed model (2026-05-31)

Paste everything below into a fresh session.

---

You're resuming PrismataAI DeepSets value-net work on branch **`feature/production-vectors`**
(repo `c:\libraries\PrismataAI`, Windows, Intel Arc B580 XPU via IPEX).

## Where things stand
The 35-prop "production-vector" retrain (Steps 0–3) is done except the final training run.
- **Schema wired + committed**: `71b4e87` (35-prop schema: `training/property_table.json` 13→35,
  `schema_v2.json` token_dim 77, `model_deepsets.py` default num_properties=35, `train.py` reads
  num_properties from the table). `f141801` (shared `js_engine/training_example.js` V2 extractor).
- **Corpora (re-vectorized, current vectorizer)** in `training/data/`:
  `human_1800_v2.h5` (1,648,072 recs), `fleet_v3_v2.h5` (5,908,728), `fleet_v4_v2.h5` (5,909,260),
  `local_mbvmb_v2.h5` (413,951, val). Train ~13.47M.
- **Full mixed run CRASHED at epoch 40** — XPU OOM (`level_zero … UR_RESULT_ERROR_OUT_OF_RESOURCES`)
  during the eval pass. Output in `training/models/deepsets_mixed_35prop/` (`best_model.pt` = epoch 30,
  VaVA 81.4%, val_loss 0.3521; `checkpoint_ep10..40.pt`). It was STILL improving (ep39 val_loss
  0.3524 vs best 0.3521; the baseline mixed run kept setting bests to epoch 96) — the crash robbed us
  of the real trajectory, so we are re-running properly. Already exported + numpy-verified:
  `docs/scratch/deepsets_mixed_35prop.bin` (round-trip PASSED) — but that's the epoch-30 model.

## Task A — add proper checkpoint/resume to train.py (DO FIRST), + the OOM fix
`train.py` has NO resume logic today. Checkpoints (`periodic_ckpt`, train.py ~1341-1358; best ckpt
~1261-1283) save only `epoch, global_step, model_state_dict, optimizer_state_dict`. They MISS the
resume-critical state.

1. **Extend the periodic checkpoint** to also save: `scheduler.state_dict()`, `best_val_vloss`,
   `best_epoch`, `patience_counter`, the SWA state (`swa_model.state_dict()` + `swa_active` +
   `swa_scheduler.state_dict()`), and RNG states (`torch`, `torch.xpu`, `numpy`, `random`).
2. **Add `--resume <checkpoint.pt>`** that restores all of the above, fast-forwards/recreates the
   scheduler to `global_step`, and starts the epoch loop at `checkpoint_epoch + 1`
   (the loop is `for epoch in range(1, args.epochs+1)` at train.py ~1210 — make the start dynamic).
   Confirm SWA (`swa_start_epoch = int(0.8*epochs)`, train.py ~1124) restores correctly if resuming
   past epoch 80.
3. **OOM fix** (root cause of the crash; needed for any long XPU run): add
   `torch.xpu.empty_cache()` + `gc.collect()` once per epoch (guard `if device.type=="xpu"`),
   e.g. right after `eval_epoch` (~1236) or at end of the loop (~1364).
4. **Verify the resume**: tiny run (`--max-records 50000 --epochs 4 --output-dir /tmp/resume_test`),
   kill it at epoch 2, `--resume` from the ep checkpoint, confirm it continues at epoch 3 with
   matching LR/best/patience and finishes cleanly. Commit Task A separately.

## Task B — clean re-run of the full mixed training to completion
Run from scratch (seed 42 reproduces ep1-40 then continues past the old crash point). Keep config
identical to the crashed run; keep patience 15 HONEST (do not disable to force SWA — let it run; it
will likely reach SWA@80 like the baseline did, or early-stop legitimately). New output dir:
```
cd c:/libraries/PrismataAI
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 python training/train.py \
  --model deepsets --property-table training/property_table.json --value-only \
  --train-file training/data/fleet_v3_v2.h5 \
  --extra-train-files training/data/fleet_v4_v2.h5 training/data/human_1800_v2.h5 \
  --val-file training/data/local_mbvmb_v2.h5 \
  --label-strategy A --epochs 100 --batch-size 512 --lr 3e-4 \
  --weight-decay 1e-4 --warmup-steps 1000 --patience 15 --seed 42 \
  --streaming --device xpu --num-workers 2 \
  --output-dir training/models/deepsets_mixed_35prop_v2
```
Run in background (~9 min/epoch → ~15h for 100; less if it early-stops). If it crashes again,
`--resume` from the latest `checkpoint_ep*.pt`. When done, export the better of best/SWA:
```
python training/export_weights_v2.py training/models/deepsets_mixed_35prop_v2/<best_or_swa>_model.pt \
  bin/asset/config/neural_weights_mixed_35prop.bin --property-table training/property_table.json
```
(the exporter prints a numpy↔PyTorch round-trip check — expect max diff <1e-3).

## Task C — Step 3d: C++↔PyTorch parity on the 35-prop model
The parity harness is on branch **`dave-master-jsonclean`** under `tools/parity/` (commit 164bc0a),
and it uses the **dave-line** engine (engine_v1 / `source/engine`, NOT engine_v2). Build that engine
(its own `CMakeLists.txt`, x64, `-DPRISMATA_BUILD_GUI=OFF` → `Prismata_Standalone` with the
`--dump-features` hook; or the VS "Standalone Release" → `bin/PrismataAI.exe`), then:
`PrismataAI.exe --dump-features <state.json> <out.json> <new 35-prop .bin>` for the 5 states, then
`python tools/parity/compare_parity.py out_state_*.json`. Header-driven → NO C++ edit needed for 35
props. Confirms the deployment engine reproduces the model (prior audit was 13-prop only).

## Gotchas / honest-verification notes
- **Wrapper masks exit code**: a `nohup bash -c '…python…'; echo` wrapper exits 0 even if python
  crashed — always check the LOG TAIL for the real status, not the task exit code.
- Background bash cwd can reset between calls — use absolute paths or `cd` first.
- LF→CRLF git warnings are benign.
- The 35-prop benefit is NOT measurable on MB-flavoured val (val acc will land ~82%); its payoff is
  RL. Don't over-read the supervised number — this model is the RL **init**.
- **Verify in code before asserting** — the prior session made several overclaims (filter contents,
  "would definitely crash", "converged at ep30/SWA unreachable"). State facts you've checked; flag
  inferences as inferences.

## Reference
- RL roadmap (next phase after this): `docs/plans/2026-05-31-linux-rl-bringup-and-go-no-go.md`
  (Linux/WSL2 build of the dave engine, action-space widening, cValue sweep, curriculum, £400 AWS).
- Engine choice: use **engine_v1 / Dave's clean** (`dave-master-jsonclean`), NOT engine_v2, for
  parity/deployment/RL.
- cValue: DSNN players use the Playout-tuned default `cValue=2.0`, which over-explores the [0,1]
  DSNN value → understates strength; sweep infra exists (`PrismatAI_UCT_c03/05/07/10` +
  `NeuralUCT_cValue` tournament, `run:false`). Free pre-RL win.
