# DSNN-in-Dave Port Audit — Findings

**Scope:** port-faithfulness / measurement-platform review of commit `829dcac`
("ai: port DSNN_MBonly NeuralNet eval into Player_UCT") on branch `dave-master-jsonclean`.
**Date:** 2026-05-29. **Reviewer task:** establish that DSNN's measured strength reflects the
model, not a porting bug or a weakened/unfair baseline — *not* to bless any win rate.

---

## Verdict (TL;DR)

**The measurement platform is TRUSTWORTHY.** The DSNN port is numerically faithful
(C++ value = PyTorch to 1.3e-6), the internal baselines are provably uncorrupted,
multi-threading is safe, and the harness is fair on every surface checked. The **one
substantive caveat is labeling**, not correctness: the circulating **42.2% "vs HardestAI"
conflates search algorithm *and* evaluator** and must not be presented as an evaluator
ablation.

All existing win-rates remain **provisional** — the doc figures
(`deepsets-training-results.md`, May-14, engine_v2) are stale for the dave tree. Numbers
below were re-derived at reduced think time (500 ms / 1000 ms) for tractability; **re-derive
at the paper's 7 s** before publication.

---

## 1. Objective backbone — PyTorch ↔ C++ value parity: PASS (never measured before)

Harness (this directory): C++ `dumpFeaturesJSON` hook (+ `--dump-features` CLI),
`compare_parity.py` (Tier B: PyTorch + numpy vs C++), `tier_a_check.py` (Tier A: feature
build vs source state), 5 fixed states.

**Reference `.pt` pinned:** of 19 candidates, only
`training/cloud-runs/deepsets_12M_full/2026-03-13_05-44-21/models/best_model.pt`
(ep98, val 0.8231) re-exports byte-identical to `neural_weights_mbonly.bin`
(695,411 B, sha256 `817ab7f9…`). `training/models/best_model.pt` is a 2-epoch smoke test —
wrong weights despite matching size+header.

```
state                          N    val_cpp  val_torch    |dval|  logit_cpp logit_torch  logit_np drop verdict
out_state_01_turn1            19   0.492601   0.492602  1.33e-06    1.07898     1.07898   1.07898    0   PASS
out_state_02_constr_damage    94   1.000000   1.000000  7.33e-12   26.33286    26.33284  26.33285    0   PASS
out_state_03_charges_lifespan 47  -0.999807  -0.999807  2.41e-08   -9.24729    -9.24729  -9.24729    0   PASS
out_state_04_high_resources   39  -0.480882  -0.480881  1.07e-06   -1.04826    -1.04826  -1.04826    0   PASS
out_state_05_late_large      121   1.000000   1.000000  0.00e+00   60.22665    60.22662  60.22667    0   PASS
worst |value_cpp - value_torch| = 1.33e-06  (tol 1e-3);  Tier-A: ALL PASS (alive==mapped, 0 dropped)
```

C++ matches both PyTorch(.pt) and numpy(.bin); raw logits agree to ~1e-5 (N up to 121).
Tier-A independently confirms the C++ tokens correctly represent the state (name→index,
owner, per-owner counts, hp_ratio bounds) — so this is not garbage-in/garbage-out parity.
`unit_index` provenance settled: all three `unit_index.json` are byte-identical
(sha256 `c86aac39…` = `schema_v2`'s hash; the `54cdda43…` token is the internal name-list
field, not file bytes — no train/serve skew).

## 2. Internal baseline integrity: PASS — no overstatement from a weakened baseline

`git diff 829dcac~1 829dcac -- source/ai/Eval.cpp source/ai/Heuristics.cpp source/ai/StackAlphaBetaSearch.cpp` → **EMPTY**.
`StackAlphaBetaSearch::eval()` dispatches only Playout/WillScore/WillScoreInflation
(else→ASSERT), never NeuralNet; the NeuralNet code is scoped to the `Player_UCT` branch;
`clone()→deepClone()` is a null-no-op for HardestAI; the `EvaluationMethods` enum is
append-only (Playout=0 preserved). The 149→116 cardLibrary swap hits both seats (not an
asymmetry); the active library is the 116-unit training set, semantically identical to the
main repo (0 differing records).

## 3. The confound (the headline caveat) — empirically demonstrated

The circulating **42.2% = DSNN(Player_UCT+NeuralNet) vs HardestAI(Player_StackAlphaBeta+Playout)**
varies *both* search algorithm and evaluator. The clean evaluator control is **HardestAIUCT**
(Player_UCT+Playout, identical iterators/limits). Dave-runner A/B (500 ms, 64 games each):

| Matchup | DSNN result |
|---|---|
| DSNN vs **HardestAIUCT** (clean ablation) | **35 %** (loses) |
| DSNN vs **HardestAI** (StackAlphaBeta, = 42.2% surface) | **53 %** (wins) |
| HardestAIUCT vs HardestAI | HardUCT 41 % |

These three baselines are **non-transitive** (HardUCT > DSNN > HardAB > HardUCT). "vs
StackAlphaBeta" gives a different and more flattering picture than the clean UCT control,
so the 42.2% is **not** an evaluator ablation. Report DSNN-vs-HardestAIUCT, labeled, at the
paper's think time.

## 4. Targeted risk surfaces

| # | Risk | Verdict | Evidence |
|---|---|---|---|
| 1 | UCT swap perturbed Playout leaf | PASS (static) | `UCTSearch.cpp` byte-identical to main repo (sha256 `8d0b77f7…` after CRLF-normalize); Playout/terminal mapping refactored leaf-ward but behavior-preserving (winner→1.0/draw→0.5/loser→0.0). Empirical pre/post blocked by a pre-port (6429686) link error (`Random::Seed`/`PortfolioGreedySearch` unresolved — project-file quirk, unrelated to the port). |
| 2 | Double-valued `addWins` | PASS | Playout/terminal `addWins(stateEval)`, `stateEval ∈ {1.0,0.5,0.0}`. |
| 3 | Value scale / round-trip | PASS | `2·sigmoid(logit)−1` → UCT `(v+1)/2`; no WillScore ±10000; verified numerically (logit_cpp = logit_torch). |
| 4 | Sign / perspective | PASS | Single negation; features in fixed P0 frame (not double-counted); value-transform region byte-identical to main repo; parity holds in P0 frame. (Explicit `eval(P1)==−eval(P2)` runtime check not separately run — code unambiguous + byte-identical to verified reference.) |
| 5 | Silent feature dropout | PASS | `dropped=0` on all 5 states; live tournament 104/106 and smoke 116/118, the 2 unmapped are `None` sentinels, no `UNMAPPED` lines. (Those `printf`s go to stdout — harmless in tournament/dump paths and contained by `main.cpp`'s redirect on the JSON path, but a latent footgun for consumers outside that window.) |
| 6 | Weights actually loaded | PASS | stderr `AIParameters: created per-player NeuralNet from asset/config/neural_weights_mbonly.bin` in tournament and in `smoke_dsnn` against the dave binary; no fallback WARNING; `steam_ai.js` spawns with `cwd=dirname(exe)` (no cwd bug). |
| 7 | NN thread-safety (the gate) | PASS | DSNN vs HardestAIUCT: **Threads:1 = 34.4 % vs Threads:8 = 35.2 %** (Δ0.8 pp, within 64-game noise). Per-player `deepClone` + own `ScratchBuffers`; 8c/16t so no compute-starvation confound. |
| 8 | Harness seat-balance | PASS | Swap bug found+fixed May-17; worker swaps `difficultyWhite↔Black` with seats; seat-independent tally. Serial Steam run: white *seat* won 2/2 (real P1/P2 asymmetry) yet per-player attribution = 50/50. |

## 5. cValue confound (claimable margin left on the table — flag prominently)

Both DSNN and HardestAIUCT use default `cValue=2.0`, tuned for the discrete Playout signal.
NN values are smoother/lower-variance, so the same constant over-explores relative to the
NN — systematically **penalizing the DSNN arm**. Every DSNN win rate here is therefore a
**lower bound** on the NN's UCT performance. Not a correctness bug; but since the paper
maximizes margin, it is claimable margin left on the table. Highest-value follow-up: a small
`cValue` sweep for DSNN. At minimum, caveat DSNN numbers as *exploration-unoptimized*.

## 6. Per-surface trustworthiness

- **DSNN vs SteamAI (headline, `matchup_clean.js`): TRUSTWORTHY platform; numbers PROVISIONAL.**
  Routing confirmed (`SteamAI for Black: …dave-master/bin/PrismataAI.exe`; White = 2016 Steam
  exe, sha256 `0a70b198…`, 721,920 B); DSNN weights load via the Steam protocol; 0 click
  failures, 0 invalid; seat balance correct. The 62.5 % (n=16, 1000 ms) is noisy directional
  only (95% CI includes 50%) — re-run at scale + 7 s.
- **DSNN vs HardestAIUCT (Dave runner): TRUSTWORTHY.** The clean evaluator ablation the paper
  should report (~35 % @500 ms; re-run @7 s).
- **DSNN vs HardestAI (Dave runner): TRUSTWORTHY-WITH-CAVEAT** — conflates algorithm + evaluator.
  The 42.2 % lives here; label it accordingly.

## 7. Direction of every artifact

- **Understates DSNN (claimable margin left):** the `cValue=2.0` over-exploration penalty.
  (A silent dropout would understate, but `dropped=0` everywhere — none present.)
- **Overstates DSNN (can't defend):** none found. Baseline uncorrupted; seat balance correct.
  (At 500 ms the "vs StackAlphaBeta" surface flatters DSNN vs the clean UCT control, but that
  is a labeling issue, not a platform fault.)

## 8. Residual uncertainty

- Re-derived numbers are at 500 ms / 1000 ms — re-derive at 7 s for the paper.
- `is_frozen` (chill) instance dim isn't exercised by the 5 action-phase states (chill is
  transient); trivial boolean (`currentChill()>0`), low risk but unverified by parity.
- Pre-port empirical regression (risk 1) not run — risk 1 rests on the conclusive static proof.

---

## Harness footprint (this review)

- `source/ai/NeuralNet.cpp` / `.h` — `dumpFeaturesJSON` + 1 logit-capture instrumentation line
  (cannot change the in-play return value).
- `source/standalone/main.cpp` — `--dump-features` entry point.
- `bin/asset/config/config.txt` — dormant matched-think-time fast variants (`DSNN_F500`,
  `HardUCT_F500`, `HardAB_F500`) + dormant `PV_*` tournament blocks (all `run:false`).
- `tools/parity/` — comparators, 5 states, dumps, this report, `README.md`.
