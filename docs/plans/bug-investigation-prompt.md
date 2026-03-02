# PrismataAI Critical Bug Investigation Prompt

> **Usage**: Copy this entire document into a new Claude Code context when you discover
> a bug that may have affected training data, tournament results, or AI behaviour.
> Fill in the `[PLACEHOLDERS]` in the Bug Description section, then let CC work through
> all four phases. Save this context's output — it becomes your decision document.

---

## Context

I have identified a potential bug in the PrismataAI codebase that may have affected
training runs and/or tournament evaluations I've already invested significant compute
into. Treat this as a high-priority investigation.

**Project overview (for orientation):**
- C++ game engine + AI for Prismata (turn-based strategy game)
- Alpha-Beta search + UCT/MCTS with neural net evaluation
- Self-play data generation pipeline → PyTorch training → C++ weight export
- Multi-cloud fleet (AWS/GCP/Azure) for both self-play generation and GPU training
- Current dataset: check `aws/watcher_status.json` for latest shard count and S3 audit
- Current best model WR: check CLAUDE.md "Current Status" section
- All self-play uses the same core engine (`GameState.cpp`, `Card.cpp`, `CardType.cpp`)
- Neural net is value-only (policy head exists but unused in search)

**Key architectural facts:**
- Self-play generates data via `SelfPlay_CI` tournament (playout eval, not neural net)
- The neural net is used ONLY for position evaluation during search, not for data generation
- Both sides of self-play use identical engine code — bugs are symmetric
- Tournament eval runs `PrismatAlpha_AB` (neural) vs `OriginalHardestAI` (playout, legacy)
- Game phases: Action → Breach → Confirm → Defense → Swoosh → next player
- `PartialPlayer` decomposition: Defense, ActionAbility, ActionBuy, Breach

## The Bug

[FILL THIS IN — describe the bug. Be specific about:]
- [What you observed (symptom)]
- [Where you think it is (file, function, line if known)]
- [When you think it was introduced (commit hash, date, or "always")]
- [What game rule or behaviour it violates]

---

## Phase 1: Root Cause Analysis

### 1.1 Trace the bug precisely

Identify the exact file(s), function(s), and line(s) where the faulty behaviour originates.

**Key engine files to check:**
- `source/engine/GameState.cpp` — core game logic, phase transitions, action legality
- `source/engine/Card.cpp` — card state, status transitions, turn lifecycle
- `source/engine/CardType.cpp` — card type properties, blocking rules
- `source/engine/CardType.h` — `CardStatus` enum (Default, Assigned, Inert)
- `source/engine/Constants.h` — game constants, phase enum
- `bin/asset/config/cardLibrary.jso` — master unit definitions (105+11 units)

**Key AI files that consume engine state:**
- `source/ai/Eval.cpp` — evaluation functions (WillScore, Playout, NeuralNet)
- `source/ai/Heuristics.cpp` — Will Score heuristic and resource values
- `source/ai/StackAlphaBetaSearch.cpp` — Alpha-Beta search
- `source/ai/UCTSearch.cpp` — UCT/MCTS search
- `source/ai/PartialPlayer*.cpp` — phase-decomposed move generation (Defense, ActionBuy, etc.)

**Key data pipeline files:**
- `source/testing/TournamentGame.cpp` — game runner + self-play data export
- `source/testing/SelfPlayDataSink.h/cpp` — binary shard writer (feature vectors)
- `training/train.py` — PyTorch training loop
- `training/load_selfplay.py` — binary shard loader
- `training/export_weights.py` — PyTorch → C++ weight format
- `training/schema.json` — feature schema contract (state_dim=1785)

### 1.2 Determine when it was introduced

Check git history:
```bash
# Commits touching the suspected file(s):
git log --oneline --follow -- source/engine/GameState.cpp
git log --oneline --follow -- source/engine/Card.cpp

# Show the diff for a specific commit:
git show <commit_hash> -- <file>

# Search for when specific code was added:
git log -S "suspicious_string" --oneline -- source/engine/
```

**Important git context:**
- Two remotes: `origin` (davechurchill upstream), `PrismatAlpha` (Surfinite's fork)
- Branch can switch unexpectedly — always `git branch --show-current` first
- The baseline `OriginalHardestAI` must NEVER be modified (legacy mode)

### 1.3 Explain the mechanism

Walk through the data flow step by step. For engine bugs, trace:
1. How the game state becomes incorrect (which function mutates it wrong)
2. How the AI search tree explores the incorrect state
3. How self-play data export captures it (features in `SelfPlayDataSink`)
4. How the neural net trains on the corrupted signal

For training pipeline bugs, trace:
1. How data is loaded (`load_selfplay.py` → numpy arrays)
2. How features are constructed (`schema.json`, state_dim=1785)
3. How the loss is computed (`train.py` — MSE on value head)
4. How weights are exported (`export_weights.py` → 26 tensors)

### 1.4 Identify the blast radius

Map what consumes the buggy output:

```
Engine bug in GameState
  ├─ AI search (Alpha-Beta / UCT) — explores wrong game tree
  │   ├─ Self-play data generation (SelfPlay_CI tournament)
  │   │   └─ Binary shards in S3 (check watcher_status.json for count)
  │   ├─ Tournament evaluation (PrismatAlpha vs OriginalHardestAI)
  │   │   └─ Win rate results in tests/*.html
  │   ├─ Live advisor overlay (--suggest mode)
  │   └─ Autopilot (click injection)
  ├─ Neural net training (trains on buggy game outcomes)
  │   └─ Deployed weights (bin/asset/config/neural_weights.bin)
  └─ GUI display (card highlighting, legal move indicators)
```

---

## Phase 2: Impact Assessment on Past Training

**This is the most important phase.** Honest, evidence-based answers only.

### 2.1 Did this bug affect training data?

- Was the buggy code path exercised during self-play generation?
- Self-play uses `SelfPlay_CI` config — check `bin/asset/config/config.txt` for which
  tournament config is active and which AI players it uses
- Does the bug affect playout evaluation (used in self-play) or only neural eval?
- Is the bug symmetric (both players affected equally) or asymmetric?

**Critical distinction:** If the bug is in core engine logic (`GameState.cpp`),
it affects ALL game simulation including self-play. If it's only in the neural net
path (`NeuralNet.cpp`, `Eval.cpp`), self-play data generated via playout eval is clean.

### 2.2 How did it affect the training signal?

For engine bugs:
- Did it change game outcomes (who wins/loses)?
- Did it change the value of positions (the training target)?
- Did it make illegal moves legal or vice versa?
- Did it affect both players symmetrically?

For training bugs:
- Did it corrupt gradients or shift the loss landscape?
- Did it introduce noise, label leakage, or systematic bias?

### 2.3 Severity estimation

Rate the severity with justification:

- **Negligible** — Training results are still valid/usable. The bug exists but
  its effect on game outcomes and position values is minimal. Both sides are
  affected equally, so relative model strength comparisons hold.
- **Degraded** — Models are suboptimal but partially salvageable. The AI learned
  slightly incorrect behaviour but the general strategic understanding is intact.
  Tournament WR comparisons between models (relative rankings) still hold even if
  absolute WR vs baseline is slightly off.
- **Invalidated** — Training results cannot be trusted. The bug fundamentally
  changes the game being played, making learned evaluations meaningless for the
  real game.

**Key question for symmetric bugs:** If both sides of self-play had the same bug,
the AI learned to play a slightly different game. The model's relative improvement
over time may still be valid even if absolute play quality is slightly off. Consider
whether fixing the bug and continuing training (with the existing model as starting
point) is viable vs full retrain.

### 2.4 Check for partial salvation

- Are any training checkpoints from BEFORE the bug was introduced?
  Check `training/models/` and `s3://prismata-selfplay-data/training-runs/`
- Were different experiment configs unaffected?
  Check `training/runs/*.json` for per-experiment metadata
- Is the 305K-game model (45.3% WR) or the 722K-game model (51.9% WR) affected?
- If the bug was introduced at a known commit, how many self-play games were
  generated BEFORE that commit? Check S3 shard timestamps vs commit date.

---

## Phase 3: Evidence Gathering

### 3.1 Find empirical signals

- Check tournament results: `docs/blend-tournament-results.md`, and any `tests/*.html`
- Check training curves: `training/runs/*.json` (per-epoch metrics)
- Check S3 audit: `s3://prismata-selfplay-data/audit-results/`
- Check self-play win rate balance: P0 vs P1 win rates in audit data
  (known baseline: P0=43.9%, P1=57.3% — significant deviation suggests bug)
- Look for anomalies in the 26.7M record dataset statistics

### 3.2 Design a verification test

Options for engine bugs:
```bash
# Run a short tournament with the fix vs without:
# 1. Build with the fix applied
# 2. Run a 100-game tournament: Fixed engine vs OriginalHardestAI
# 3. Compare WR with known baselines

# Or use --suggest mode to compare AI decisions:
bin/Prismata_Testing.exe --suggest test_state.json
# Compare output before/after fix on the same game state
```

Options for training bugs:
```bash
# Quick smoke test on a small shard set:
python training/train.py --selfplay-dir bin/training/data/selfplay/2026-02-15_11-31-33/ \
  --value-only --epochs 5 --batch-size 512 --max-records 1000
# Compare loss curves before/after fix
```

### 3.3 Quantify the delta

- For engine bugs: How many game states per game are affected? (e.g., "every
  defense phase" = ~18 states per game, vs "only when specific unit is in play")
- For value estimation: What's the eval difference on affected positions?
  Use `--suggest` with `DoAnalyze` to compare eval_pct before/after fix.
- For game outcomes: Run a fixed-vs-unfixed tournament to measure WR impact.

---

## Phase 4: Fix & Mitigation Plan

### 4.1 Propose the fix

Show the exact code change. Keep it minimal and surgical. Do NOT:
- Refactor unrelated code
- Change the OriginalHardestAI baseline (legacy mode must be preserved)
- Modify the feature schema (state_dim=1785 contract)
- Break the binary shard format

### 4.2 Assess retraining necessity

Given the severity rating, recommend one of:

| Option | When to use | Estimated cost |
|--------|-------------|----------------|
| **No retrain** | Bug doesn't affect training signal | £0 |
| **Continue from checkpoint** | Bug is symmetric, model has valid strategic knowledge. Fix engine, generate NEW self-play data with fixed engine, resume training | Cost of N new self-play games + training run |
| **Fine-tune to recover** | Model learned mostly-correct behaviour. Short corrective run on fixed data | ~10-20% of full retrain cost |
| **Full retrain** | Bug fundamentally corrupts game semantics | Full cost of regenerating self-play data + training |

**Cost reference points (from CLAUDE.md):**
- Self-play generation: ~4 games/min/process locally (free), $0.32/1K games on AWS spot
- GPU training: ~$0.20/hr on AWS g4dn.xlarge spot, ~$0.40/hr on GCP g6.2xlarge spot
- Current dataset: ~722K games, 26.7M records, 178GB in S3
- Full retrain from scratch at current scale: ~£200-300 in cloud compute
- Regenerating 722K games on AWS spot: ~£75 ($0.32 × 722)

**Critical consideration:** If the bug is symmetric (both self-play sides affected)
and the model has shown consistent WR improvement (3.6% → 26.7% → 45.3% → 51.9%),
the relative signal is likely valid. The most cost-effective path is usually:
1. Fix the engine bug
2. Deploy fixed exe to S3 (`aws/deploy_for_eval.sh`)
3. Generate NEW self-play data with fixed engine
4. Continue training the existing model on the combined (old + new) data
5. Re-evaluate WR — if it improves, the old data wasn't wasted

### 4.3 Preventive measures

Suggest specific tests or assertions. Examples for this project:
- Add a C++ unit test in the testing framework that verifies the game rule
- Add a PRISMATA_ASSERT in the relevant code path
- Add a Python validation in `tools/verify_selfplay.py`
- Add a check to the `/preflight` slash command
- Document the gotcha in CLAUDE.md under "Gotchas & Non-Obvious Patterns"

### 4.4 Downstream updates needed

If the fix changes engine behaviour, check these downstream consumers:
- [ ] Self-play exe deployed to S3 (`aws/deploy_for_eval.sh`)
- [ ] Any running EC2/GCP/Azure fleet (check `aws/watcher_status.json`)
- [ ] Tournament eval fleet (terminate and relaunch with fixed exe)
- [ ] Live advisor overlay (`tools/prismata_advisor.py`)
- [ ] Autopilot (`tools/prismata_autopilot.py`)
- [ ] Live commentator (`tools/prismata_commentator.py`)
- [ ] Frontline penalty test (if running on `test/frontline-penalty` branch)
- [ ] GUI display (`source/gui/GUICard.cpp`, `GUIState_Play.cpp`)

---

## Output Format

Structure your response with clear headers matching the phases above.
Lead with a **TL;DR** summary giving:
- What the bug is (one sentence)
- Severity rating (Negligible / Degraded / Invalidated)
- Recommended action (which mitigation path)
- Estimated cost to resolve

**Be brutally honest.** Do NOT downplay severity. If training data is toast,
say so clearly — I need to know now so I can stop wasting money on cloud compute
that's using buggy data or a buggy engine.

---

## Reference: Key Files Quick Index

| Category | Files |
|----------|-------|
| **Engine core** | `GameState.cpp`, `Card.cpp`, `CardType.cpp/.h`, `Constants.h` |
| **Card data** | `bin/asset/config/cardLibrary.jso` |
| **AI search** | `StackAlphaBetaSearch.cpp`, `UCTSearch.cpp`, `Eval.cpp`, `Heuristics.cpp` |
| **AI players** | `AIParameters.cpp`, `PartialPlayer_Defense_*.cpp` |
| **Data export** | `TournamentGame.cpp`, `SelfPlayDataSink.h/cpp` |
| **Training** | `train.py`, `load_selfplay.py`, `export_weights.py`, `schema.json` |
| **Config** | `bin/asset/config/config.txt`, `aws/watcher_config.json` |
| **Verification** | `tools/verify_selfplay.py`, `tools/audit_selfplay_s3.py` |
| **Cloud deploy** | `aws/deploy_for_eval.sh`, `aws/launch_selfplay.sh`, `gcp/launch_selfplay.sh` |
| **Project docs** | `CLAUDE.md`, `docs/PROJECT_HISTORY.md` |
