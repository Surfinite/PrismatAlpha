# Meta-Review: Discord Knowledge Extraction Plan

**Synthesized from:** 7 external reviews of `docs/plans/2026-02-21-discord-knowledge-extraction.md`
**Date:** 2026-02-22
**Status:** RECOMMENDATIONS READY FOR INTEGRATION

---

## A.1 — Review Summary Table

| Reviewer | Sentiment | Key Focus Areas | Unique Insight |
|---|---|---|---|
| **R1** | Strongly critical | Uncalibrated filtering, Haiku inadequacy, crude dedup, KB bloat, temporal gap | Channel-specific proximity windows; per-category extraction passes |
| **R2** | Strongly critical | Thread reconstruction failure, Haiku lacks strategic depth, KB bloat, calibration missing | Expert-curated sampling alternative (~$0.20); structured query approach |
| **R3** | Mixed-critical | Word-overlap dedup broken, mega-threads in busy channels, quality threshold too aggressive | Anthropic Batch API (50% cost reduction); thread duration caps |
| **R4** | Mixed-critical | Haiku lacks confidence assessment, Phase 4 under-specified, thread window too short | Embedding-first approach (60-70% API reduction); reaction data as quality signal |
| **R5** | Mixed-critical | "Append everything" bloats KB, temporal validity unsolvable by prompt, fragile grouping | RAG-style storage; `temporal_validity` field; stable import IDs; data governance |
| **R6** | Mixed-critical | "Extract ALL" miscalibrated prompt, no human review gate, dedup fails, chunk too large | Quality bar in prompt; human review gate with preview doc; low-confidence routing |
| **R7** | Mixed-critical | Phase 4 dangerously underplanned, dedup fails, Haiku can't assess credibility | Unit-centric extraction; commentary_prompt.md distillation step missing; embed content extraction |

---

## A.2 — Consensus Points

### Universal Agreement (7/7)

1. **Word-overlap dedup will fail** — Paraphrased insights ("avoid chilling absorber" vs "don't freeze main block") have near-zero word overlap but identical meaning. All 7 reviewers flagged this as a fatal flaw requiring embedding-based or LLM-based replacement.

2. **Knowledge base bloat/pollution risk** — Appending 2,000-5,000 extracted insights to 5,090 curated lines will degrade signal density, make future `commentary_prompt.md` distillation harder, and create a two-tier quality problem in the KB files.

3. **Temporal context gap** — Haiku cannot judge whether a 2018 balance opinion is still relevant without patch history. The prompt instruction to "skip out-of-date balance complaints" is a no-op without reference data.

### Strong Consensus (6/7)

4. **Calibration phase essential** (R1-7) — No mechanism to validate filtering, threading, or extraction quality before committing the full API budget. A 5-10 chunk calibration run costs ~$0.05 and prevents a $1.35 run that produces garbage.

5. **Separate Discord files preferred** (R1-7) — Create `docs/commentary-knowledge/discord/` mirror files instead of appending to canonical KB. Preserves integrity, enables easy rollback, avoids bloat.

6. **AI_BEHAVIOR category redundant** (R1,R4,R6,R7 explicit) — Already completed: 596-line analysis + 2,095 matches in `discord_ai_feedback.json`. Including in prompt wastes ~50 tokens per chunk for zero marginal value.

7. **Thread grouping needs tuning** (R1-5,R7) — 5-minute window too short for strategy channels (splits discussions with 10-30 min think pauses), too long for busy chat (merges simultaneous conversations). Per-channel configurable with thread size caps.

8. **Patch history should be provided to Haiku** (R1,R2,R4-7) — Even a coarse era-based timeline ("final major patch Jul 2019, development ended ~2020") enables temporal validity assessment.

9. **Human review gate before integration** (R4-7) — Phase 5's spot-check of 10 random insights is too late (files already modified). Need approval step after Phase 3 consolidation, before any file creation.

### Moderate Consensus (5/7)

10. **Embedding-based dedup** (R1-5) — `sentence-transformers` (all-MiniLM-L6-v2, free, local) handles paraphrase correctly. Cosine similarity > 0.85 within (category, primary_unit) buckets.

11. **Unit reference list in extraction prompt** (R2,R4,R6,R7, implied by others) — ~500 tokens of display names from cardLibrary.jso improves entity recognition and standardization.

12. **Checkpoint/resume mechanism** (R4-7) — Track processed chunks in manifest file; skip on re-run. One if-statement per chunk prevents re-processing after crashes.

13. **COMMUNITY_JARGON should be deferred** (R5-7) — Tone-sensitive category; route to review file for manual curation rather than auto-integration.

14. **Quality scoring threshold too aggressive** (R3-7) — Score < 3 discards a normal user writing a 150-char message mentioning a unit (score = 2). Concise expert nuggets also lost.

---

## A.3 — Outlier Points

| Point | Reviewer | Merit Assessment |
|---|---|---|
| Expert-curated sampling (~$0.20, top 50 experts only) | R2 | **High merit** — excellent as a first pass before general extraction. Captures 80%+ of valuable insights at 15% of cost. |
| Anthropic Batch API for 50% cost reduction | R3 | **High merit** — real API, 24hr turnaround acceptable for batch job. Saves ~$0.65. |
| Embedding-first clustering (send only representative thread per topic) | R4 | **Medium merit** — interesting but pre-filtering already cuts volume. Adds pipeline complexity. |
| RAG-style JSON/SQLite storage | R5 | **Low merit for now** — over-engineers for this scale. Markdown matches existing workflow. |
| Unit-centric extraction (query per unit name) | R7 | **Medium merit** — maps directly to knowledge files but misses general strategy insights. Better as a complementary pass. |
| Two-stage pre-screen (cheap yes/no then full extraction) | R4,R7 | **Medium merit** — calibration + quality bar addresses root cause more simply. |
| Content safety filter | R2 | **Low merit** — Prismata Discord is a strategy game community; risk is minimal. |
| Stable import IDs (hash-based) | R5 | **High merit** — trivial to implement, prevents accidental re-append on re-run. |
| Commentary_prompt.md distillation step | R7 | **High merit** — validated against codebase. The 68-line prompt is manually curated; KB growth doesn't auto-improve the commentator. This step is genuinely missing. |
| Reaction data as quality signal | R4 | **High merit** — reactions are available in the export JSON (confirmed: `count` and `emoji` fields). Free signal boost. |

---

## A.4 — Category Breakdown

### 🏗️ Architecture & Design

| Feedback | Reviewers | Codebase Validation | Assessment |
|---|---|---|---|
| Pipeline decomposition is sound (Phase 1→2→3→4→5) | All 7 | Confirmed: matches existing `search_discord_ai_feedback.py` pattern | **Keep as-is** |
| Phase 4 integration is dangerously under-specified | R4,R5,R6,R7 | Confirmed: plan says "append" but doesn't specify placement within files, curation logic, or quality gates | **Must fix** — add human review gate + separate Discord files |
| Create separate Discord knowledge files | R1-7 | Confirmed: KB files total 5,090 lines, all hand-curated. Zero Discord sources currently | **Must do** — `docs/commentary-knowledge/discord/` directory |
| Reduce chunk size to 12-15K tokens | R6,R7 | Feasible: increases chunks from ~150 to ~200, cost +$0.20 | **Should do** — better Haiku attention coverage |
| RAG-style JSON/SQLite storage | R5 | Codebase uses markdown everywhere; commentator loads markdown file directly | **Reject** — over-engineers for this scale |

### ⚠️ Risks & Concerns

| Risk | Reviewers | Codebase Validation | Assessment |
|---|---|---|---|
| Haiku lacks Prismata domain expertise | R1,R2,R4,R6,R7 | Confirmed: commentator uses hardcoded model `claude-haiku-4-5-20251001` (line 32). Haiku handles commentary OK with good prompts, but extraction is harder | **Mitigate** — provide unit list + patch history + expert list in prompt |
| KB bloat degrades commentator | R1-7 | **Partially validated**: `tools/commentary_prompt.md` is 68-line manually curated file. KB bloat doesn't directly break commentator, but makes future distillation harder | **Mitigate** — separate files + distillation step |
| Temporal irrelevance (outdated advice) | R1,R2,R4-7 | Confirmed: Prismata had ~20 balance patches; final major patch Jul 2019, development ended ~2020 | **Mitigate** — patch timeline in prompt + `temporal_validity` field |
| Thread grouping fragility | All 7 | Confirmed: messages are chronologically ordered, timestamps have ms precision. Reply references exist (type="Reply") but only 0.8% of messages | **Mitigate** — per-channel windows + thread caps |
| Expert list incomplete / username changes | R5,R7 | **Validated**: Discord export has `author.name` (stable lowercase handle) AND `author.nickname` (display name). Roles are objects: `{"name": "Alpha Player"}`. Expert names should match `author.name` field. Role-based detection is feasible | **Should fix** — augment with role-based detection |

### 🗑️ Suggested Removals / Simplifications

| Suggestion | Reviewers | Assessment |
|---|---|---|
| Remove AI_BEHAVIOR category | R1,R4,R6,R7 | **Accept** — confirmed redundant with existing 596-line analysis |
| Remove general_chat entirely | R1,R2,R3,R5 | **Accept** — 843K tokens, off-topic, negative ROI |
| Remove word-overlap dedup | R1-7 | **Accept** — replace with embedding-based |
| Remove "no category zero" success criterion | R5 | **Accept** — incentivizes filler. Keep as informational metric only |
| Remove orphan message filter for ask_a_dev | R4,R6,R7 | **Accept** — standalone expert statements are high-value |
| Remove "+500 lines minimum" success criterion | R6 | **Accept** — lines added ≠ value. Replace with "100+ high-confidence novel insights" |
| Simplify Phase 3C cross-reference | R4 | **Accept** — searching KB files for semantic overlap is harder than plan implies. Flag as "new" by default, handle conflicts during manual review |

### ➕ Suggested Additions / Features

| Addition | Reviewers | Feasibility | Assessment |
|---|---|---|---|
| Calibration phase (Phase 1.5) | R1-7 | Easy, ~$0.05, 30 min | **Must do** |
| Patch history in prompt | R1,R2,R4-7 | Trivial, ~100 tokens | **Must do** |
| Human review gate (Phase 3.5) | R4-7 | Easy, adds ~1hr review time | **Must do** |
| Quality bar in extraction prompt | R6 | Easy, prompt rewrite | **Must do** |
| Unit reference list in prompt | R2,R4,R6,R7 | Easy, ~500 tokens from cardLibrary.jso | **Should do** |
| Checkpoint/resume | R4-7 | Easy, one file per chunk + manifest | **Should do** |
| Dry-run mode | R3,R6 | Easy, CLI flag | **Should do** |
| `temporal_validity` field | R5,R6 | Easy, schema addition | **Should do** |
| Low-confidence routing to separate file | R6 | Easy, post-consolidation split | **Should do** |
| Expert list in Haiku prompt | R6,R7 | Trivial, ~100 tokens | **Should do** |
| Commentary_prompt.md distillation step | R7 | Manual, ~30 min after integration | **Should do** |
| JSON schema validation | R4-7 | Medium, validation library | **Should do** |
| Reaction data as quality signal | R4 | Trivial, field exists in export | **Consider** — lean yes |
| Batch API for 50% savings | R3 | Small, SDK supports it | **Consider** — lean yes |
| Stable import IDs | R5 | Trivial, hash function | **Consider** — lean yes |

### 🔄 Alternative Approaches

| Alternative | Reviewer | Assessment |
|---|---|---|
| Per-category extraction passes (8 prompts) | R1 | **Reject** — 8x cost for marginal precision gain. Quality bar fix is simpler |
| Expert-only extraction first | R2,R7 | **Consider** — excellent first pass. ~$0.20 for top-50 experts' messages |
| Embedding-first clustering | R4 | **Consider** — interesting but adds complexity. Pre-filtering already cuts 60-70% |
| Two-stage pre-screen | R4,R7 | **Consider** — calibration + quality bar addresses root cause more simply |
| Structured query approach | R2 | **Consider** — interesting for unit-specific knowledge but misses broader strategy |
| Sonnet for consolidation only | R5 | **Reject** — adds cost, Haiku merge pass is cheaper for dedup edge cases |

### ✅ Confirmed Good / Keep As-Is

All 7 reviewers validated these elements:
- Pipeline decomposition (Phase 1→2→3→4→5)
- Channel prioritization order (strategy_advice first)
- Pre-filtering before LLM (correct cost optimization)
- Haiku model choice (right for $1-4 budget)
- Cost structure and estimates (~$1.35 realistic)
- Replay code index (Phase 4C) — high-value side artifact
- Source attribution convention (`> Source: Discord #channel — author (date)`)
- Anti-patterns section in Phase 0
- Quality scoring concept (needs calibration, not replacement)
- Expert name list concept (needs augmentation, not replacement)
- Verification steps per phase (need strengthening, not removal)

### 🔧 Implementation Details & Nits

- Expert names with leading dots (`.holyfire`, `.bky_1556`) — verify against `author.name` field in export JSON (R4)
- Replay code regex may produce false positives — test against actual codes (R3,R4,R7)
- Prompt should instruct "no markdown fences in JSON output" (R3)
- Normalize text before dedup (lowercase, strip punctuation) (R3)
- Token counts: plan says 120-150 chunks but math suggests 24-48 after filtering. Reconcile (R4)
- Source attribution should include message ID for traceability (R4)
- Multi-author threads: use "consensus" for attribution (R7)
- Script size estimate 400-600 lines is optimistic; budget 800-1,000 (R7)
- Phase 5 "run commentary system" needs specifics (R7)
- Haiku pricing ($0.25/$1.25 per MTok) should be verified (R3,R6)

### 📦 Dependencies & Integration

- `sentence-transformers` library needed for embedding-based dedup (free, ~80MB model) — confirmed feasible on 32GB system
- `tiktoken` for token counting before API calls (R4,R6)
- Anthropic SDK v0.83.0 already installed — Batch API support needs verification
- Commentary prompt distillation is manual — KB growth doesn't auto-improve commentator (R7, validated)
- cardLibrary.jso display names available but community uses abbreviations not in the file (validated)

### 🔮 Future Considerations

- Phase 2 follow-up: unit-centric extraction pass for deeper unit profiles (R7)
- RAG-style storage if knowledge base grows past 20K lines (R5)
- Continuous Discord monitoring via bot (out of scope, noted in plan)
- Image/screenshot analysis for board state discussions (R1,R2 — deferred, high complexity)
- Replay code index enables future replay analysis pipeline (R4,R7)

---

## A.5 — Conflicts & Contradictions

### 1. Thread Grouping Window Size

- **R1**: Channel-specific (15 min slow / 2 min fast)
- **R3**: Channel-specific (15 min slow / 2 min fast) + duration caps
- **R4**: 15 min base + participant-continuity heuristic (same author within 30 min extends thread)
- **R5**: Topic-shift markers (unit-name set changes, @mention shifts)

**Resolution**: Per-channel configurable with sensible defaults (10 min strategy, 3 min chat) + thread caps (50 messages or 5K tokens). Participant continuity is nice-to-have but adds complexity — skip for v1.

### 2. Separate Files vs RAG Storage

- **R1-4,R6-7**: Separate Discord markdown files
- **R5**: JSON/SQLite with runtime retrieval

**Resolution**: Separate markdown files. Simpler, matches existing workflow. The commentary prompt is manually curated anyway — RAG retrieval adds no value for the current consumer.

### 3. Per-Category Prompts vs Single Prompt

- **R1**: 8 separate prompts (8x cost, higher precision)
- **R6**: 3 grouped prompts
- **R7**: 2-stage pre-screen

**Resolution**: Single prompt with improved quality bar (R6's suggestion). Addresses the root cause (prompt calibration) rather than adding architectural complexity. Per-category is overkill at Haiku prices.

### 4. Embeddings vs LLM for Dedup

- **R1-2,R4-5**: Local embeddings (sentence-transformers)
- **R3**: Either embeddings or Haiku
- **R6**: Two-pass: word overlap first, then Haiku merge

**Resolution**: Local embeddings as primary. Free, fast, handles paraphrase. Optional Haiku merge pass for edge cases if calibration shows embeddings miss things.

### 5. Deleted User Handling

- **R1**: Exclude entirely
- **Plan**: -1 penalty (keep with downweight)
- **R5**: Make penalty tunable

**Resolution**: Keep -1 penalty but make it a configurable parameter validated during calibration. Some deleted accounts were expert players.

### 6. prismata_chat Inclusion

- **R3**: Remove entirely from initial run
- **R7**: Process but deprioritize
- **Plan**: Channel #8 of 9, stop if budget constrained

**Resolution**: Keep as deprioritized (channel #7 after general_chat removal). prismata_chat has real strategy discussion intermixed with social chat. The pre-filtering and quality scoring should handle signal extraction. But general_chat is removed entirely.

---

## A.6 — Recommended Plan Changes

### Must-Do (high consensus, high impact)

| # | Change | Reviewers | Impact |
|---|---|---|---|
| 1 | **Add Phase 1.5: Calibration** — 5-10 chunks from strategy_advice, manual review, tune thresholds | R1-7 | Prevents $1.35 wasted on miscalibrated pipeline |
| 2 | **Replace word-overlap dedup** with embedding-based similarity (sentence-transformers, free) | R1-7 | Fixes fatal dedup flaw |
| 3 | **Create separate Discord knowledge files** in `docs/commentary-knowledge/discord/` | R1-7 | Prevents KB pollution, enables rollback |
| 4 | **Remove AI_BEHAVIOR category** from extraction prompt | R1,R4,R6,R7 | Eliminates redundant work |
| 5 | **Add patch history/timeline** to extraction prompt (~100 tokens) | R1,R2,R4-7 | Enables temporal validity assessment |
| 6 | **Add human review gate** (Phase 3.5) with preview doc before file creation | R4-7 | Prevents unreviewed integration |
| 7 | **Raise quality bar** in extraction prompt — replace "extract ALL" with specific criteria | R6 | Cuts extraction noise by 60-70% |
| 8 | **Remove general_chat** from plan entirely | R1,R2,R3,R5 | Eliminates negative-ROI channel |

### Should-Do (strong suggestions, meaningful improvement)

| # | Change | Reviewers | Impact |
|---|---|---|---|
| 9 | **Add unit reference list** to extraction prompt (~500 tokens) | R2,R4,R6,R7 | Improves entity recognition |
| 10 | **Add checkpoint/resume** — track processed chunks, skip on re-run | R4-7 | Crash recovery |
| 11 | **Add dry-run mode** — Phase 1 stats before API spend | R3,R6 | Cost validation |
| 12 | **Per-channel thread windows** (10 min strategy, 3 min chat) + thread caps (50 msg / 5K tok) | R1,R3,R4,R5 | Better thread quality |
| 13 | **Add `temporal_validity` field** (`timeless\|patch_dependent\|historical`) | R5,R6 | Enables temporal routing |
| 14 | **Fix orphan message handling** — keep expert/dev singles and msgs ≥100 chars | R4,R6,R7 | Preserves high-value standalone insights |
| 15 | **Route low-confidence** to separate file, not auto-integrated | R6 | Quality gate |
| 16 | **Defer COMMUNITY_JARGON** to manual review file | R5,R6,R7 | Protects commentary tone |
| 17 | **Pass expert list** to Haiku in prompt (not just pre-filtering) | R6,R7 | Improves confidence assignment |
| 18 | **Add commentary_prompt.md distillation step** after integration | R7 | Ensures commentator actually improves |
| 19 | **Validate JSON output** with schema (fields, categories, formats) | R4-7 | Catches malformed extractions |
| 20 | **Reduce chunk size** from 25K to 15K tokens | R6,R7 | Better Haiku attention |

### Consider (good ideas, presented as pick list in updated plan)

| # | Change | Reviewers | Effort | Recommendation |
|---|---|---|---|---|
| 1 | Anthropic Batch API for 50% cost reduction | R3 | Small | Lean yes |
| 2 | Reaction data as quality signal (+1/reaction, cap +3) | R4 | Trivial | Lean yes |
| 3 | Two-stage extraction (cheap classify then targeted) | R4,R7 | Medium | Lean no |
| 4 | Embedding-first clustering (60-70% API reduction) | R4 | Medium | Lean no |
| 5 | Unit-centric extraction for UNIT_INTERACTION | R7 | Medium | Lean no |
| 6 | Verbatim_evidence field with message IDs | R5 | Trivial | Lean yes |
| 7 | Stable import IDs (hash-based) | R5 | Small | Lean yes |
| 8 | Data governance section | R5 | Trivial | Lean yes |
| 9 | Expert frequency-by-channel report | R7 | Trivial | Lean yes |
| 10 | Embed content extraction (richer embed handling) | R7 | Trivial | Lean yes |
| 11 | Sonnet for consolidation-only pass | R5 | Small | Lean no |
| 12 | Per-channel stats after Phase 1 | R7 | Trivial | Lean yes |
| 13 | Token counting with tiktoken | R4,R6 | Small | Lean yes |

### Reject (with reason)

| Suggestion | Reviewer | Reason |
|---|---|---|
| RAG-style JSON/SQLite storage | R5 | Over-engineers for this scale; markdown matches existing workflow |
| Per-category extraction prompts (8x cost) | R1 | Quality bar fix is simpler and more cost-effective |
| Skip prismata_chat entirely | R3 | Too aggressive — strategy discussions happen there. Deprioritize, don't skip |
| Exclude Deleted User entirely | R1 | Some were expert players. -1 penalty (tunable) is reasonable compromise |
| Content safety filter | R2 | Minimal risk for strategy game community |
| "No category zero" as hard criterion | R5 | Partially agree — keep as informational metric, remove as hard requirement |

---

## A.7 — What Stays

The following elements were validated by multiple reviewers and should remain unchanged:

1. **Pipeline decomposition** (Phase 1→2→3→4→5) — all 7 praised the modular design
2. **Channel prioritization order** — strategy_advice first, correct targeting
3. **Pre-filtering before LLM** — massive cost savings, right economics
4. **Haiku model choice** — correct for $1-4 budget constraint
5. **Cost structure and estimates** — realistic and well-broken-down
6. **Replay code index** (Phase 4C) — high-value side artifact, multiple reviewers praised
7. **Source attribution convention** — `> Source: Discord #channel — author (date)` matches existing KB pattern
8. **Anti-patterns section** in Phase 0 — encoding quirks, memory limits
9. **Quality scoring concept** — right signals (expert presence, length, unit mentions, replay codes). Needs calibration, not replacement
10. **Expert name list concept** — strong domain knowledge signal. Needs augmentation with role-based detection, not replacement
11. **Verification steps per phase** — actionable and regression-proof. Need strengthening, not removal

---

**Document Version:** 1.0
**Date:** 2026-02-22
**Reviewer Count:** 7
**Overall Consensus:** Plan structure is sound; execution mechanics need significant tightening before deployment
