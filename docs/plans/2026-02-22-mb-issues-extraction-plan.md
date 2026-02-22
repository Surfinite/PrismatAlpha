# Master Bot Community Issues Extraction Plan

**Goal:** Produce an improved and expanded version of `docs/discord-masterbot-feedback-analysis.md` by reprocessing all Discord data with a better extraction approach.

**Secondary goal:** If all Discord data gets beneficially processed along the way (general strategy knowledge), that's a win.

---

## Clarification: Why Sonnet, Not "8192 Context Window"

The `EXTRACTION_MAX_TOKENS = 8192` setting in the pipeline is the **output** token limit — it controls how many tokens the model can write in its response. This was increased from 4096 because Haiku's JSON responses were getting truncated mid-object on content-rich chunks. Both Haiku and Sonnet have 200K+ input context windows — that's not the bottleneck.

The reason to consider Sonnet is **extraction quality**:
- Better at catching **implicit** bot feedback ("it always goes gauss cannon" without saying "bot")
- Fewer **false positives** (distinguishes "mb" = "maybe" from "MB" = Master Bot)
- Better **nuanced categorization** (e.g., distinguishing a genuine bug report from casual venting)
- More reliable **JSON output** (fewer parse failures, better schema adherence)

---

## Cost Comparison

### What We Have
- **#strategy_advice** processed with Haiku: 67 chunks, ~$2, yielded 1,426 general strategy insights
- **Keyword search** across all 13 channels: 2,095 matches, manually synthesized into 38 MB issues

### What Needs Processing
Unprocessed channels with MB-relevant content (estimated from export sizes):

| Channel | Size | Est. Chunks | MB Relevance |
|---|---|---|---|
| prismata_chat | 113 MB | ~220 | HIGH (1,204 keyword hits) |
| unit_and_game_design | 36 MB | ~70 | HIGH (137 hits, dev discussion) |
| alpha_player_lounge | 14 MB | ~28 | HIGH (expert observations) |
| questions_and_help | 7.7 MB | ~15 | MEDIUM (beginner observations) |
| ask_a_dev | 4.2 MB | ~8 | MEDIUM (dev responses about bot) |
| dev_seeking_feedback | 4.2 MB | ~8 | LOW (game design, not bot) |
| general_chat | 59 MB | ~115 | LOW (off-topic, high noise) |
| League channels (5) | ~1 MB | ~2 | LOW (results only) |
| **Total new** | **~239 MB** | **~466 chunks** | |

Plus re-processing strategy_advice (67 chunks) with the MB-focused prompt.

### Cost Estimates (all channels, ~533 total chunks)

| Approach | Sync API | Batch API (50% off) |
|---|---|---|
| **Haiku on all** | ~$16 | ~$8 |
| **Sonnet on all** | ~$48 | ~$24 |
| **Sonnet on HIGH+MED only** (~341 chunks) | ~$31 | ~$15 |
| **Hybrid: Haiku general + Sonnet MB-focused** | ~$32 | ~$16 |

Estimates based on strategy_advice calibration: 67 chunks cost ~$2 Haiku / ~$6 Sonnet.

### Recommendation

**Sonnet on HIGH+MEDIUM channels via Batch API: ~$15**

Rationale:
- 3x quality improvement over Haiku for nuanced extraction
- Batch API halves the cost
- Skip LOW-relevance channels (general_chat is 59MB of noise, league results are tiny)
- Re-process strategy_advice with MB-focused prompt (Haiku run was general knowledge, not MB-targeted)
- $15 is reasonable for a significant quality upgrade over keyword search

---

## Approach: Dual-Purpose Extraction

Rather than two separate passes, use a **single Sonnet extraction** with an expanded schema that captures both:

1. **General strategy knowledge** (existing categories: STRATEGY_RULE, UNIT_INTERACTION, OPENING_THEORY, GAME_MECHANIC, META_KNOWLEDGE, BALANCE_HISTORY)
2. **MB-specific feedback** (new categories: MB_BUG_REPORT, MB_WEAKNESS, MB_EXPLOIT_STRATEGY, MB_COMPARISON, MB_FEATURE_REQUEST)

This means one pass yields both goals: expanded MB issues AND general knowledge from new channels.

---

## Phase 0: Facts Gathered (Do Not Re-Gather)

### Pipeline Architecture
- **Script**: `tools/discord_knowledge_extractor.py` (~2,400 lines)
- **Model**: Currently `claude-haiku-4-5-20251001` (line ~170)
- **Output tokens**: `EXTRACTION_MAX_TOKENS = 8192` (line 180)
- **Processing**: Sync API (not batch — batch was considered but sync chosen for immediate results)
- **Chunking**: Thread-aware, respects token limits, preserves conversation context
- **Dedup**: sentence-transformers `all-MiniLM-L6-v2`, cosine similarity >= 0.85
- **Output**: JSON per chunk → consolidation → category markdown files

### Discord Export Data
- **Location**: `c:/libraries/prismata-replay-parser/discord_exports_full/`
- **13 JSON files**, 290 MB total, exported Feb 21 via DiscordChatExporter CLI
- **Servers**: Prismata (112616041175089152), Prismata League (412991183355248640)
- **Export script**: `tools/export_discord_full.sh`

### Existing Chunk Data
- **Chunks**: `tools/discord_extraction/chunks/` — 67 chunks from #strategy_advice only
- **Manifest**: `tools/discord_extraction/chunk_manifest.json`
- **Extractions**: `tools/discord_extraction/extractions/high/` (67 files), `low/` (24 files)

### Existing MB Analysis
- **File**: `docs/discord-masterbot-feedback-analysis.md` (595 lines)
- **Source**: `bin/discord_ai_feedback.json` (2,095 keyword-matched messages)
- **Tool**: `tools/search_discord_ai_feedback.py` (6 keyword categories, regex-based)
- **Issues**: 38 subsections across 7 categories, 18 unique replay codes
- **Weakness**: High false positive rate, misses implicit references, keyword-only

### Pricing (Feb 2026)
| Model | Input/MTok | Output/MTok | Batch Input | Batch Output |
|---|---|---|---|---|
| Haiku 4.5 | $1.00 | $5.00 | $0.50 | $2.50 |
| Sonnet 4.6 | $3.00 | $15.00 | $1.50 | $7.50 |

---

## Phase 1: Chunk All Target Channels

**Goal**: Extend the chunking pipeline to process prismata_chat, unit_and_game_design, alpha_player_lounge, questions_and_help, ask_a_dev, and re-chunk strategy_advice.

**Work**:
1. Modify `discord_knowledge_extractor.py` to accept a channel list parameter or iterate over multiple export files
2. Create separate chunk directories per channel: `tools/discord_extraction/chunks_{channel}/`
3. Generate chunk manifests per channel
4. Keep existing strategy_advice chunks intact (they have Haiku results already)

**Output**: ~466 new chunks across 5-6 channels + 67 existing strategy_advice chunks = ~533 total.

**Verification**:
- [ ] Each channel has a `chunk_manifest.json` with token counts
- [ ] Total chunk count matches estimates (within 20%)
- [ ] Spot-check: 3 random chunks per channel have valid JSON with `threads` array

**Anti-patterns**:
- Do NOT delete existing strategy_advice chunks/extractions
- Do NOT mix chunks from different channels in the same directory

---

## Phase 2: Design MB-Focused Extraction Prompt

**Goal**: Create a dual-purpose extraction prompt that captures both general knowledge AND MB-specific feedback in a single pass.

**Work**:
1. Add new insight categories to the extraction schema:
   - `MB_BUG_REPORT` — Specific reproducible bot misbehavior (with replay code if available)
   - `MB_WEAKNESS` — Strategic weakness or pattern the bot exhibits
   - `MB_EXPLOIT_STRATEGY` — Known strategies to beat MB / exploitable patterns
   - `MB_COMPARISON` — Comparisons to other bots (BottyMcBotFace, Wacky Bot, Adept Bot)
   - `MB_FEATURE_REQUEST` — Community wishes for bot improvement
2. Modify the extraction prompt to specifically instruct the model to:
   - Look for IMPLICIT bot references (not just "master bot" / "MB")
   - Extract replay codes when mentioned alongside bot feedback
   - Note the Discord username and date for attribution
   - Distinguish genuine bug reports from casual complaints
   - Rate confidence: HIGH (specific reproducible issue), MEDIUM (pattern observation), LOW (vague complaint)
3. Keep ALL existing general categories (STRATEGY_RULE, UNIT_INTERACTION, etc.) so we get dual benefit

**Output**: Updated extraction prompt template, updated JSON schema with new categories.

**Verification**:
- [ ] New schema validates against existing consolidation pipeline
- [ ] Prompt tested on 3 chunks manually before full run
- [ ] MB categories produce meaningful output (not empty)

**Anti-patterns**:
- Do NOT remove existing categories — this is additive
- Do NOT make the prompt so long it crowds out the chunk content (keep system prompt under 2,000 tokens)

---

## Phase 3: Sonnet Extraction Run

**Goal**: Process all target channel chunks through Claude Sonnet 4.6 with the dual-purpose prompt.

**Work**:
1. Update `discord_knowledge_extractor.py` to support model selection (add `--model` flag: `haiku` or `sonnet`)
2. Set model to `claude-sonnet-4-6` when `--model sonnet` is passed
3. Run extraction on all ~533 chunks (sync API — batch API would save 50% but adds 24hr delay)
4. Store results in `tools/discord_extraction/extractions_sonnet/` to keep Haiku results intact
5. Monitor for JSON parse failures, retry as needed

**Estimated cost**: ~$30 sync / ~$15 batch
**Estimated time**: ~2 hours sync (based on strategy_advice taking 41 min for 67 chunks, scaled to 533)

**Decision point**: Sync vs Batch API
- Sync: ~$30, results in ~2 hours, can monitor progress
- Batch: ~$15, results in up to 24 hours, submit-and-wait
- **Recommendation**: Use sync for the first channel (strategy_advice, 67 chunks, ~$6) as a quality validation. If quality is good, switch to batch for remaining channels to save cost.

**Verification**:
- [ ] All chunks processed (0 failures after retries)
- [ ] Spot-check 5 random results: JSON valid, categories populated, MB categories present where expected
- [ ] Compare 10 strategy_advice Sonnet results vs Haiku results — document quality differences
- [ ] Total cost within 20% of estimate

**Anti-patterns**:
- Do NOT overwrite Haiku extraction results
- Do NOT skip the strategy_advice quality comparison — this is how we validate the Sonnet upgrade
- Do NOT use `max_tokens` below 8192 (truncation risk)

---

## Phase 4: Consolidation & Deduplication

**Goal**: Merge all Sonnet extractions into a consolidated dataset, dedup against existing Haiku results.

**Work**:
1. Run consolidation pipeline on Sonnet extractions (existing `run_consolidation()` logic)
2. Cross-reference with existing Haiku extractions to avoid duplicates
3. Separate MB-specific insights (new categories) from general knowledge
4. For general knowledge: merge into existing `docs/commentary-knowledge/discord/` files
5. For MB insights: create new structured dataset for Phase 5

**Output**:
- `tools/discord_extraction/mb_insights_consolidated.json` — All MB-specific insights, deduplicated
- Updated `docs/commentary-knowledge/discord/` files with new general insights
- Statistics: total insights, by category, by channel, duplicate rate

**Verification**:
- [ ] Dedup rate reasonable (expect 10-30% overlap with Haiku results for strategy_advice)
- [ ] MB insight count > 200 (current keyword search found 2,095 messages, but most are noise)
- [ ] General insight count > existing 1,426 (new channels should add significantly)
- [ ] No duplicate insights between Haiku and Sonnet outputs

---

## Phase 5: Generate Expanded MB Issues Document

**Goal**: Produce `docs/discord-masterbot-feedback-analysis-v2.md` — a significantly improved version of the original.

**Work**:
1. Start from the existing analysis structure (7 sections, 38 subsections)
2. Incorporate all new MB_BUG_REPORT, MB_WEAKNESS, MB_EXPLOIT_STRATEGY insights
3. For each existing issue: add new supporting evidence (quotes, replay codes, reporter names)
4. Add NEW issues not in the original analysis (Sonnet should catch things keyword search missed)
5. Update severity ratings based on expanded evidence
6. Update "Already Fixed" section with current fix status from our codebase
7. Add new section: "Community-Reported Replay Codes" with expanded code list
8. Add new section: "Exploitable Patterns" consolidating all known MB-beating strategies
9. Cross-reference with our existing heuristic fixes to mark which issues we've addressed

**Output**: `docs/discord-masterbot-feedback-analysis-v2.md`

**Verification**:
- [ ] Every issue has attribution (Discord username, date, channel)
- [ ] Every replay code is listed in the appendix
- [ ] Fixed issues are correctly marked with our fix description
- [ ] New issues (not in v1) are clearly marked
- [ ] Document is self-contained and readable without prior context

---

## Deferred: Replay Code Validation (Future Work)

**Not in scope for this plan**, but noted for follow-up:

The analysis documents reference ~20+ replay codes where community members reported specific MB bugs. These codes can be validated against our current AI using the `--analyze` and `--eval` CLI modes:

```bash
# For each replay code in the appendix:
bin/Prismata_Testing_d.exe --eval REPLAY_CODE          # Neural eval curve, find big mistakes
bin/Prismata_Testing_d.exe --analyze REPLAY_CODE \
  --player PrismatAI_AB --think-time 500                # AI vs human buy comparison
```

**What this would tell us:**
- Which community-reported bugs our heuristic fixes (EffectiveBuyCost, partial-value density, frontline penalty) have actually addressed
- Which bugs remain in our current AI
- New bugs visible in eval curves that the community didn't explicitly report
- Quantified agreement rate between our AI and expert play on these specific positions

**Estimated effort**: ~30 minutes local compute (20 replays × ~90 seconds each for --analyze). No cloud cost.

**Prerequisite**: Merge `test/frontline-penalty` results first so the AI includes all latest heuristic fixes.

This would be a powerful validation step — producing a "before/after" comparison showing which community complaints we've fixed.

---

## Summary

| Phase | What | Estimated Cost | Time |
|---|---|---|---|
| 1 | Chunk all target channels | Free (local) | ~10 min |
| 2 | Design MB-focused prompt | Free (local) | ~20 min |
| 3 | Sonnet extraction run | ~$15-30 | 2-24 hrs |
| 4 | Consolidation & dedup | Free (local) | ~15 min |
| 5 | Generate expanded MB doc | Free (local) | ~30 min |
| **Total** | | **~$15-30** | **~3-25 hrs** |

The main cost variable is sync ($30) vs batch API ($15). Recommend starting with a sync quality validation on strategy_advice (~$6), then batch for the rest (~$9-15).
