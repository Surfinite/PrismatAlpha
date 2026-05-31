# Linux RL Bring-up + Go/No-Go Plan (2026-05-31)

> Companion to the production-vector retrain (Step 3, branch `feature/production-vectors`).
> Hand this to the next session when the supervised mixed run (`deepsets_mixed_35prop`) finishes.

## Decision frame

Decide, within **~£400 (~$500)/month**, whether RL self-play meaningfully improves the
Prismata AI beyond the supervised value-net baseline. **Goal = a defensible go/no-go signal,
not a finished agent.** Decent results → keep spending monthly; flat → stop.

## Guiding principle: spend free engineering before paid compute

The £400 ROI is dominated by *free, local, one-time engineering* (Linux build, action-space
widening, card-set curriculum, eval harness). The failure mode is paying AWS GPU/CPU rates to
debug a loop — or running self-play over an un-widened action space and concluding "RL did
nothing" (a false negative). So: **prove the loop + first signal locally (£0), then spend the
£400 to scale the answer.**

---

## Phase 0 — Linux / WSL2 bring-up (free, local)

- Use **WSL2** (not a heavyweight VM): real Linux kernel, sees the repo directly, builds the
  CMake project, runs CPU self-play and PyTorch-CPU smokes. (Arc-GPU passthrough in WSL2 is
  unreliable — not needed for build/loop validation; GPU training is what AWS is for. A working
  x64 WSL2 build *also* gives a faster-than-current-x86 local self-play path for Phase 4.)
- **Build the CORRECT engine** — `dave-master-jsonclean`'s `CMakeLists.txt` (NOT the
  `feature/production-vectors` one, which globs `engine_v2` = the indicted weaker engine):
  - It is x64-only, cross-platform (pthreads via `Threads::Threads`; `WIN32` defined only on
    Windows → `Timer.h`'s Unix branch kicks in; MSVC-only flags guarded), and globs
    `source/engine` (engine_v1 / Dave's clean line).
  - Configure headless: `cmake -DPRISMATA_BUILD_GUI=OFF ...` → **no SFML dependency**.
  - Targets needed: `Prismata_Standalone` (console self-play / tournament) and
    `Prismata_Testing` (`--suggest`). NN inference is CPU-side C++ (portable).
- **Validate (all £0):** compiles on Linux; self-play binary runs and emits
  `SelfPlayDataExport`; the scaffolding self-play → export → `train.py` → `export_weights_v2`
  → re-load `.bin` round-trips.
- **Deliverable:** known-good Linux build + a tiny working end-to-end loop.

## Phase 1 — Action-space widening (free; the real unlock)

RL only learns what the move generator *proposes*. The current generator collapses rich
decisions into ~5 greedy whole-turn plans, so widening generation is make-or-break.

**Principle (from the May-31 recon):** *keep the rules that prune strictly-dominated moves;
open up the rules that pre-commit among non-dominated tradeoffs.*

- **Keep** the waste-prunes — `AvoidAttackWaste` (no overkill), `AvoidResourceWaste` (don't let
  decaying red expire), `AvoidDefenseWaste` (don't burn Asteri-Cannon HP for an unneeded
  Barrier). They remove provably-worse moves → a gift to RL exploration.
- **Open up** the gates that suppress legitimate (non-dominated) choices. Three explicit,
  config-level gates (`bin/asset/config/config.txt`):
  - `Ability_Filter` / `Live_Ability_Filter` — Drake, Grenade Mech, Odin (ability use).
  - Buy-limit `0`-caps — e.g. `Chrono Filter`/`Animus` in `GreenBlueLimits`,
    `Conduit`/`Blastforge` in `RedRushLimits`.
  - Filter `stateConditions` — named, board-state-gated: Amporilla, Savior, Ferritin Sac.
- **Emergent long tail** (e.g. Bombarder — not filtered anywhere, just never *generated* on a
  sensible line): widen the ACTION_BUY portfolio (more / randomized buy partial-players) and/or
  drop the opening book so self-play actually constructs those builds.
- **Curriculum:** widen ONE axis at a time (e.g. the red buy-vs-click split first), let
  self-play stabilize, then widen the next. Unblocking everything at once makes the AI flail.
- Recommended: a new `RL_Explore` player config (widened/randomized buy+ability portfolio,
  cleared ability filter, no opening book) — leave `LiveHardestAI` / `DSNN_*` untouched.

## Phase 2 — Card-set curriculum (force the tested units in)

Pure B+8-random wastes cycles: a specific unit appears in only ~8/105 ≈ **7.6%** of games
(~13× inefficiency for targeted learning). So:

- **Force ≥1 of the test-pool units into each game's random set** (the other 7 random) — keeps
  full context diversity while guaranteeing the unit appears. (Self-play is symmetric — both
  players share the set.)
- **Blend, don't replace:** ~40% forced-set + ~60% normal random per round, to preserve general
  strength and match the deployment distribution.
- **Rehearse the broad distribution:** keep the supervised mixed corpus (and some random
  self-play) in the training mix to prevent catastrophic forgetting on non-target units.
- **Stage:** higher forced-fraction early (learn the unit at all) → dial toward random later
  (consolidate, match deployment).
- The dual-eval (Phase 3) is what *catches* over-specialization if the blend is wrong.

## Phase 3 — Eval harness (free; safety net + the go/no-go meter)

- **Win-rate A/B** (reuse `matchup_clean.js` style head-to-head): RL-tuned model vs
  (a) the supervised baseline, (b) MasterBot / `LiveHardestAI`, (c) the previous RL iteration.
- **Evaluate on BOTH** forced-set games (did the target units improve?) AND general random /
  held-out sets (did anything regress? — catches forgetting). Instrument this FIRST so you know
  early whether it's working.
- Cheap to run; it is the number that decides go/no-go.

## Phase 4 — Free local proof-of-life

After the current supervised run frees the box: a small RL loop on the **local** machine
(WSL2 x64 self-play + Arc B580 XPU training) over the Phase-1 widened axis + Phase-2 curriculum.

- **Go-criterion to justify AWS spend:** the RL-tuned model shows *any* measurable improvement
  on the target units **without** regressing on general sets. Zero movement → diagnose
  (usually action-space or eval), don't spend £400 yet.

## Phase 5 — £400 AWS scale (the go/no-go)

Once the loop shows life locally, scale for volume.

- **Cost anchors:** a supervised retrain is cheap (~$15–30, g6.2xlarge spot, was ~29h for the
  mixed run). The driver is self-play (CPU-bound). Use **spot** (project history: eu-north-1
  g6.2xlarge stable for long runs). Self-play wants many cores → either a many-vCPU instance
  for self-play + a g-instance for training, or the g6's 8 vCPU if modest.
- **Rough what $500 buys:** ~250–500 instance-hours → several RL iterations + ~100k–1M
  self-play games (wide error bars; depends on MCTS sims/move). For a *small* game with a
  *warm-started* value net, that is plausibly enough to move a measurable needle.
- **Per-iteration:** self-play batch → retrain value net → export `.bin` → eval harness →
  log win-rate vs baseline. Track the trajectory across iterations.
- **Go/No-Go by end of £400:** improving win-rate trajectory → continue monthly; flat →
  stop or rethink the action space.

---

## Honest caveats / risks

- **Action-space widening is make-or-break.** RL can't learn moves the generator never emits.
- **Forced-set fine-tuning can cause forgetting** — controlled by blend + rehearsal + dual-eval.
- **Unknowns with wide error bars:** MCTS sims/move, games-to-first-signal. £400 buys a
  *go/no-go*, not a strong agent.
- **Engine:** use engine_v1 / Dave's clean (`dave-master-jsonclean`), NOT engine_v2.
- **Policy head:** NOT required for value-based self-play RL (Phases 1–5). It has no policy head
  in the DeepSets model today, and PUCT is off. Defer it — it's the later *efficiency*
  multiplier once the action space is wide enough that plain MCTS struggles (see the
  May-31 policy/PUCT recon for the mapping problem).

## Why the 35-prop value net (training now) is the right substrate

The production-vector features (auto/click production split, costs, sac, chill) give the value
net the inputs to judge the units MB never used — so when Phase-1 unblocking + Phase-2 forcing
make self-play actually explore those units, the net can learn their worth from the features
rather than being blind. The supervised ~82% is just a health check; the props' payoff is here.

## Cost summary

| Phase | Cost | Output |
|---|---|---|
| 0 Linux/WSL2 build | £0 | known-good headless Linux engine + loop |
| 1 Action-space widening | £0 | `RL_Explore` config, widened generation |
| 2 Card-set curriculum | £0 | forced-set + blend + rehearsal sampler |
| 3 Eval harness | £0 | win-rate A/B (forced + general) |
| 4 Local proof-of-life | £0 | first signal on the Arc B580 |
| 5 AWS scale | **£400** | the go/no-go win-rate trajectory |
