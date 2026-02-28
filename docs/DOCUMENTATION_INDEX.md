# PrismataAI — Documentation Index

> Complete index of all plan documents, context docs, and meta-reviews.
> CLAUDE.md contains only the most important references. This file has the full list.
> Updated: Feb 28, 2026

## Active Plans & References

| Document | Description |
|---|---|
| `docs/PROJECT_HISTORY.md` | Full chronological dev history (sections 1-29) + historical tournament results |
| `docs/plans/2026-02-15-selfplay-training-master-plan.md` | Current execution plan (iteration 1 complete, iteration 2 pending) |
| `docs/cloud-ops-reference.md` | Cloud provider operational gotchas (AWS/GCP/Azure) |
| `docs/selfplay-worker-instructions.md` | Source-verified self-play implementation spec |
| `docs/WEIGHT_FORMAT.md` | Binary weight format specification |
| `docs/wiki/PRISMATA_REFERENCE.md` | Curated game knowledge reference (from wiki) |
| `docs/prismata-strategy-guide.md` | Comprehensive human-readable strategy guide (17 chapters) |
| `docs/commentary-knowledge/` | Extracted Prismata strategy knowledge (8 canonical files + discord/ subdir + README) |
| `docs/commentary-knowledge/RESEARCH-HANDOFF.md` | Instructions for delegating further research |

## Training & Hyperparameter Plans

| Document | Description |
|---|---|
| `docs/plans/2026-02-19-training-next-steps.md` | Training plan v3 FINAL — 9 expert reviews, 3 parallel runs |
| `docs/plans/2026-02-18-t4-training-plan.md` | GPU training experiment plan (L4 on GCP, T4 spot on AWS) |
| `docs/plans/hyperparameter-experiments-v2.md` | Experiment plan v2 (COMPLETE — tanh fix, phased approach) |
| `docs/plans/2026-02-17-hyperparameter-experiments.md` | Experiment plan v1 (Churchill/Lc0 research) |
| `docs/plans/reproducibility-plan.md` | Training reproducibility standard (seeds, determinism) |
| `~/.claude/plans/intel-arc-b580-xpu-acceleration-v2.md` | Intel Arc B580 GPU plan (DONE — 4.5x speedup) |
| `docs/blend-tournament-results.md` | Blend tournament results (CONCLUDED) |

## Feature Plans

| Document | Description |
|---|---|
| `docs/plans/2026-02-25-as3-js-transpilation-plan-v2.md` | AS3→JS transpilation plan (COMPLETE) |
| `docs/plans/engine-logic-audit-plan-v2.md` | Engine logic audit v2 (COMPLETE — 4 fixes applied) |
| `docs/plans/2026-02-22-postgame-commentary-pipeline-plan-v2.md` | Post-game commentary pipeline (Phases 1-3 COMPLETE) |
| `docs/plans/2026-02-20-live-commentator-plan.md` | Live AI commentator (Phase 1 DONE) |
| `docs/plans/2026-02-18-prismata-overlay-advisor.md` | Neural eval overlay (DONE) |
| `docs/plans/2026-02-23-replay-database-plan-v2.md` | Replay code database (COMPLETE) |
| `docs/plans/2026-02-22-mb-issues-extraction-plan.md` | MB-focused Discord extraction (V2 generated) |
| `docs/plans/2026-02-21-discord-knowledge-extraction-v2.md` | Discord knowledge extraction v2 |
| `docs/plans/2026-02-22-auto-spectate-plan.md` | Auto-spectate feature plan |
| `docs/plans/2026-02-21-frontline-penalty-test-v2.md` | Frontline penalty isolation test (COMPLETE) |

## Infrastructure Plans

| Document | Description |
|---|---|
| `docs/plans/2026-02-14-selfplay-10k-generation-and-training.md` | Earlier 10K-game generation plan (superseded) |
| `docs/plans/opening-book-plan.md` | Opening book extraction (DONE) |
| `docs/plans/engine-validation-plan.md` | Engine validation (DONE) |
| `docs/plans/2026-02-16-azure-compute-plan.md` | Azure compute integration (DONE) |
| `docs/plans/2026-02-19-selfplay-audit-plan.md` | S3 selfplay data integrity audit |
| `~/.claude/plans/bubbly-tinkering-kahan.md` | Prioritized development guide (roadmap synthesis) |
| `~/.claude/plans/roadmap-phase2-instructions.md` | Phase 2 execution instructions |
| `~/.claude/plans/prismata-command-center-build.md` | Command Center build plan |

## Context Documents (for external review)

| Document | Description |
|---|---|
| `docs/plans/2026-02-25-as3-js-transpilation-CONTEXT.md` | Context for AS3→JS transpilation review |
| `docs/plans/2026-02-19-training-plan-context.md` | Context for training plan review |
| `docs/plans/2026-02-18-training-plan-context.md` | Context for GPU training review |
| `docs/plans/2026-02-18-overlay-context.md` | Context for overlay plan review |
| `docs/plans/2026-02-23-replay-database-plan-CONTEXT.md` | Context for replay database review |
| `docs/plans/commentary-pipeline-kickoff-prompt.md` | Kickoff prompt for commentary pipeline |
| `docs/plans/2026-02-20-commentary-knowledge-extraction.md` | Instructions for knowledge extraction |
| `docs/plans/bug-investigation-prompt.md` | Reusable bug investigation template |
| `docs/plans/bug-investigation-defense-reset.md` | Kickoff for defense-reset bug |
| `docs/claude-app-instructions.md` | Instructions for Claude Windows app |

## Meta-Reviews

| Document | Description |
|---|---|
| `docs/plans/META-REVIEW-2026-02-25-as3-js-transpilation-plan.md` | AS3→JS transpilation meta-review |
| `docs/plans/META-REVIEW-engine-logic-audit-plan.md` | Engine logic audit meta-review (10 reviews) |
| `docs/plans/META-REVIEW-2026-02-22-postgame-commentary-pipeline-plan.md` | Commentary pipeline meta-review (13 reviews) |
| `docs/plans/META-REVIEW-2026-02-21-discord-knowledge-extraction.md` | Discord extraction meta-review (7 reviews) |
| `docs/plans/META-REVIEW-2026-02-23-replay-database-plan.md` | Replay database meta-review (5 reviews) |

## Historical & Archives

| Document | Description |
|---|---|
| `docs/session-logs/` | Historical parallel session logs (ctx1-4, selfplay progress) |
| `docs/backup_claude_md_2026-02-14/` | Backup of all original CLAUDE*.md files |
| `docs/wiki/` | Full wiki dump (448 pages, raw wikitext) |
| `docs/recovered-sources/` | Full-text archive of recovered wiki guides + Wayback Machine content (21 files) |
| `docs/discord-masterbot-feedback-analysis.md` | MB analysis v1 (Haiku, strategy_advice only) |
| `docs/discord-masterbot-feedback-analysis-v2.md` | MB analysis v2 (Sonnet, 6 channels, 350 insights) |
| `docs/discord-knowledge-extraction-preview.md` | Human-reviewable preview of extracted Discord insights |
| `docs/discord-replay-codes.json` | 93 replay codes from Discord |
| `docs/spiritfryer_stats.excalidraw` | SpiritFryer stats visualization |
| `docs/wonderboat_stats.excalidraw` | Wonderboat stats visualization |
| `docs/plans/engine-logic-audit-plan.md` | Engine logic audit plan v1 (superseded by v2) |
