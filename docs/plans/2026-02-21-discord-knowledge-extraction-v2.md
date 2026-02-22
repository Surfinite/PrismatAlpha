# Plan: Full Prismata Discord Knowledge Extraction (v2)

**Status:** PLANNED
**Created:** 2026-02-21
**Updated:** 2026-02-22 (v2 — incorporates 7 external reviews via meta-review + enhancements 1,6,7,8,9,10,12,13)
**Estimated cost:** ~$0.35-0.50 (Haiku API via Batch API at 50% discount)
**Estimated time:** ~3-4 hours (mostly automated, plus ~1hr human review)
**Meta-review:** `META-REVIEW-2026-02-21-discord-knowledge-extraction.md`

## Objective

Process all ~222,000 human messages from the Prismata Discord (2015-2026, ~3.4M tokens, excluding general_chat) to extract structured game knowledge. This is the only major source NOT yet incorporated into the commentary knowledge base (which already has 280+ sources from YouTube, blogs, Reddit, wiki, Twitch).

<!-- CHANGED: removed general_chat from scope (843K tokens, off-topic, negative ROI) — Reviewers 1,2,3,5 -->

## Data Summary

<!-- CHANGED: removed general_chat row, updated totals — Reviewers 1,2,3,5 -->

| Channel | Messages | Est. Tokens | Strategic Value | Thread Window |
|---|---|---|---|---|
| strategy_advice | 34,963 | ~543K | **Highest** — pure strategy (2018-2026) | 10 min |
| unit_and_game_design | 35,210 | ~548K | **High** — unit interactions, balance theory (2018-2024) | 10 min |
| ask_a_dev | 14,666 | ~301K | **High** — authoritative game mechanics (2017-2025) | 10 min |
| alpha_player_lounge | 12,769 | ~181K | **High** — expert-only discussion (2018-2023) | 10 min |
| prismata_chat | 107,701 | ~1,514K | **Medium** — high volume, mixed quality (2016-2026) | 3 min |
| questions_and_help | 7,296 | ~109K | **Medium** — beginner/intermediate (2017-2026) | 5 min |
| general (League) | 5,898 | ~92K | **Medium** — competitive discussion (2018-2025) | 5 min |
| dev_seeking_feedback | 3,591 | ~68K | **Medium** — balance feedback (2018-2020) | 5 min |
| ~~general_chat~~ | ~~54,550~~ | ~~843K~~ | **SKIP** — off-topic, zero strategic ROI | — |
| League results (4ch) | 760 | ~2K | **Low** — match scores only (2018) | 5 min |
| **TOTAL (processed)** | **~222,854** | **~3,358K** | | |

<!-- CHANGED: added per-channel thread window column — Reviewers 1,3,4,5 -->

## Architecture

```
Discord JSON exports (289 MB, 14 files — general_chat SKIPPED)
    |
    v
[Phase 0] Infrastructure check
    |
    v
[Phase 1] Python pre-filter & chunker
    |  - Remove empty/short (<20 char) messages (keep embeds)
    |  - Remove bot messages
    |  - Per-channel thread grouping (10/5/3 min windows)
    |  - Quality scoring with expert/role/reaction signals
    |  - Split into ~15K token chunks preserving thread boundaries
    |  - Dry-run mode: stats only, no API calls
    |  - Checkpoint/resume via processed_chunks.json
    |
    v
[Phase 1.5] Calibration (NEW)                              <-- CHANGED
    |  - Process 5-10 chunks from strategy_advice
    |  - Manual review of extraction quality
    |  - Go/no-go gate before full budget commitment
    |
    v
[Phase 2] Claude Haiku extraction
    |  - Quality-bar prompt (specific, non-obvious, backed by reasoning)
    |  - 7 extraction categories (AI_BEHAVIOR removed)
    |  - Unit reference list + patch timeline + expert list in prompt
    |  - temporal_validity tagging (timeless/patch_dependent/historical)
    |  - JSON schema validation per insight
    |  - Low-confidence routed to separate file
    |  - Output: structured JSON per chunk
    |
    v
[Phase 3] Consolidation & dedup
    |  - Embedding-based dedup (sentence-transformers, free, local)
    |  - Cross-reference with existing knowledge base
    |  - Contradiction flagging
    |
    v
[Phase 3.5] Human Review Gate (NEW)                        <-- CHANGED
    |  - Preview doc: top 50, contradictions, stats
    |  - Developer approval before file creation
    |
    v
[Phase 4] Integration (Discord mirror directory)
    - Write to docs/commentary-knowledge/discord/ (NOT main files)
    - COMMUNITY_JARGON to manual review file
    - Replay code index
    - Manual promotion to main KB is a separate step
    - commentary_prompt.md update is manual
```

## Extraction Categories

<!-- CHANGED: removed AI_BEHAVIOR (already done), added temporal_validity context — Reviewers 1,4,6,7 -->

These align with and extend the existing commentary knowledge base structure:

| Category | Maps To | What To Extract |
|---|---|---|
| **UNIT_INTERACTION** | discord/03-advanced-units-discord.md | Unit synergies, counters, combo assessments, tier opinions |
| **STRATEGY_RULE** | discord/04-strategy-concepts-discord.md | Heuristics, rules of thumb, strategic principles |
| **OPENING_THEORY** | discord/05-openings-builds-discord.md | Build orders, timing analysis, opening evaluation |
| **GAME_MECHANIC** | discord/01-game-fundamentals-discord.md | Rules clarifications, mechanic explanations (esp. from devs) |
| **BALANCE_OPINION** | discord/08-balance-history-discord.md | Unit balance assessments, patch reactions, meta shifts |
| **EXPERT_ASSESSMENT** | discord/06-meta-expert-discord.md | High-level game analysis, set reading examples, replay breakdowns |
| **COMMUNITY_JARGON** | discord/discord_jargon_review.md | Slang, memes, catchphrases — manual review only |

**AI_BEHAVIOR category REMOVED.** Already completed: 596-line analysis at `docs/discord-masterbot-feedback-analysis.md` + 2,095 matches in `bin/discord_ai_feedback.json`. Not re-extracted here.
<!-- CHANGED: AI_BEHAVIOR removed — Reviewers 1,4,6,7 -->

**COMMUNITY_JARGON:** Extracted but routed to `discord_jargon_review.md` for manual tone review before any integration. Not auto-integrated.
<!-- CHANGED: COMMUNITY_JARGON deferred — Reviewers 5,6,7 -->

## Phase 0: Documentation & Infrastructure Check

**Already confirmed:**
- `anthropic` Python SDK 0.83.0 installed (Claude API access)
- Discord exports at `c:/libraries/prismata-replay-parser/discord_exports_full/` (14 JSON files, 289 MB)
- JSON schema: `author.name` = stable lowercase handle (for expert matching), `author.nickname` = display name <!-- CHANGED: clarified field usage — Reviewers 6,7 -->
- Roles are structured objects: `{"name": "Alpha Player", "id": "...", ...}` — match on `role.name` <!-- CHANGED: role structure — Reviewers 6,7 -->
- Reactions available: `count` and `emoji` fields per message <!-- CHANGED: noted reactions — Reviewer 4 -->
- `reference.messageId` present for Reply messages (type="Reply")
- Messages are chronologically ordered within each file
- Existing search script pattern at `tools/search_discord_ai_feedback.py`
- Commentary knowledge base at `docs/commentary-knowledge/` (7 files, ~5,090 lines, 280+ sources — Discord not yet included)
- `tools/commentary_prompt.md` is 68 lines, manually curated, ~2,400 tokens. NOT auto-generated from KB <!-- CHANGED: noted — Reviewer 7 -->
- Haiku model ID: `claude-haiku-4-5-20251001` (confirmed in codebase)

**Pre-run setup:**
```bash
pip install sentence-transformers  # for embedding-based dedup (~80MB model)
pip install tiktoken               # for exact token counting before API calls
```

**Anti-patterns to avoid:**
- Do NOT load entire export files into LLM context (106K messages = 1.5M tokens in prismata_chat alone)
- Do NOT use raw message text without context — conversations need thread grouping
- Do NOT send messages <20 chars to the LLM (reactions, one-word replies waste tokens)
- Do NOT process general_chat — off-topic, 843K tokens, negative ROI <!-- CHANGED: absolute prohibition — Reviewers 1,2,3,5 -->
- Do NOT directly modify existing `docs/commentary-knowledge/*.md` files — write to `discord/` mirror first <!-- CHANGED: — Reviewers 1-7 -->
- Must use `PYTHONIOENCODING=utf-8` for all Python scripts (cp1252 encoding errors on Windows)

## Phase 1: Pre-Filter & Chunk Pipeline

**Script:** `tools/discord_knowledge_extractor.py`

### 1A. Dry-run mode
<!-- CHANGED: added dry-run capability — Reviewers 3,6 -->

```
Add --dry-run flag to the script.
When active: run Phase 1 entirely (filter, thread, chunk) but:
  - Print per-channel stats table:
    | Channel | Raw | Filtered | Threads | Chunks | Est. Tokens |
    (one row per channel, totals row at bottom)
  - Print expert frequency by channel:
    | Channel | amalloy | mrguy888 | elyot | ... | Total Expert Msgs |
    (helps calibrate which channels to prioritize)
  - Print total estimated cost (at $0.25/MTok input, $1.25/MTok output)
  - Use tiktoken for exact token counts (not rough word-based estimates)
  - Do NOT make any API calls
  - Do NOT write chunk files

Recommended first run to validate pipeline before spending API credits.
```

### 1B. Message filtering

```
For each channel JSON (general_chat: SKIP entirely):
  - Skip bot messages (author.isBot == true)
  - Skip empty/whitespace-only content
  - Skip messages < 20 characters UNLESS message has embeds
  - For messages with embeds: extract embed title, description, and field values
    (pattern: search_discord_ai_feedback.py already handles embed.title/description/fields)
  - Concatenate embed text with message content for thread grouping and LLM context
  - Track reply chains via reference.messageId
```

### 1C. Thread grouping
<!-- CHANGED: per-channel time windows and thread caps — Reviewers 1,3,4,5 -->

```
Group sequential messages into "threads" using per-channel proximity windows:

  Strategy channels (10 min): strategy_advice, unit_and_game_design,
                               ask_a_dev, alpha_player_lounge
  Medium channels (5 min):    questions_and_help, dev_seeking_feedback,
                               general (League), League results
  Fast channels (3 min):      prismata_chat

  - Explicit Reply references (reference.messageId) extend threads across time gaps
  - Each thread: participants, timestamps, full text, replay codes, reaction counts
  - Max thread size: 50 messages OR 5,000 tokens (whichever first — split into sub-threads)
```

### 1D. Orphan message handling
<!-- CHANGED: expert-aware orphan retention — Reviewers 4,6,7 -->

```
A single message not part of any thread is an "orphan." KEEP orphans if ANY of:
  (a) author.name is in the expert list
  (b) author has role matching "Alpha Player" or "Developers"
  (c) message content >= 100 characters
  (d) channel is ask_a_dev or alpha_player_lounge

Discard orphans that fail ALL conditions above.
(Previously: discard all orphans <100 chars — too aggressive for short expert insights)
```

### 1E. Quality scoring & filtering

```
Score each thread:
  - +2 per message from known expert (match author.name):
    amalloy, mrguy888, velizar_, masn6811, awaclus, apooche, elyot,
    liadahlia, .holyfire, 307th, spiritfryer, .bky_1556, p0lari,
    mtanzer, steel0229e, shadourow, extratricky, crash_overlord, mqp,
    silentslayers, namington
  - +2 per message from author with "Developers" role
  - +1 per message from author with "Alpha Player" role
  - +1 per message > 100 characters
  - +2 per message > 200 characters
  - +1 per replay code detected (regex: [A-Za-z0-9+@]{5}-[A-Za-z0-9+@]{5})
  - +1 per unit name mentioned (from cardLibrary.jso display names)
  - -1 per message from "Deleted User" (can't verify expertise)

  Discard threads with score < 3 (tunable — validate during calibration)
```

### 1F. Chunking
<!-- CHANGED: chunk size reduced 25K → 15K — Reviewers 6,7 -->

```
Assemble threads into chunks targeting ~15K tokens each:
  - Use tiktoken (cl100k_base encoding) for exact token counting per thread
  - Never split a thread across chunks
  - Group by channel (process strategy_advice first)
  - Each chunk includes: channel name, date range, thread count, exact token count
  - Reject chunks >18K tokens (hard cap — split oversized threads if needed)
  - Estimated chunks: ~180-220 total (more than original due to smaller size)
```

### 1G. Checkpoint/resume
<!-- CHANGED: added — Reviewers 4,5,6,7 -->

```
Write processed_chunks.json after each successful chunk extraction:
  { "processed": ["chunk_0001.json", ...], "last_updated": "..." }
On re-run: load manifest, skip already-processed chunks.
Makes the pipeline safe to interrupt and resume at any point.
```

### 1H. Output

```
Output: chunks/ directory with numbered JSON files
Each chunk: {
  channel, date_range, thread_count,
  threads: [{ participants, timestamp_start, timestamp_end,
              messages: [{author, content, timestamp, reactions}] }]
}
```

**Verification (dry-run output):**
- Total messages after filtering should be ~40-80K (15-30% of raw 222K)
- No chunk exceeds 18K tokens (15K target + thread-rounding buffer)
- strategy_advice and unit_and_game_design channels produce the most chunks
- Per-channel stats printed: messages_raw → messages_filtered, threads, chunks

## Phase 1.5: Calibration
<!-- CHANGED: NEW PHASE — Reviewers 1-7 -->

**Objective:** Validate extraction quality before committing full API budget.
**Cost:** ~$0.05. **Time:** ~30 min.

### Steps

1. Run Phase 1 (dry-run) on strategy_advice to verify filtering.
2. Run Phase 1 (real) on strategy_advice only — generates chunks.
3. Select 5-10 representative chunks (first 5 + 2-3 from later dates).
4. Run Phase 2 extraction on these chunks only.
5. Manually review extracted insights:
   - Are they specific enough? ("defense matters" = too vague, reject)
   - Is confidence calibrated? (High = expert agreement or dev confirmation)
   - Are unit names matched correctly?
   - Are categories correct? (UNIT_INTERACTION vs STRATEGY_RULE is common confusion)
   - Are temporal_validity tags reasonable?
6. Tune extraction prompt if needed:
   - Tighten quality threshold wording
   - Adjust category boundary descriptions
   - Add few-shot examples if helpful
7. If >50% of insights are vague/obvious: raise quality bar further.
8. If <10% of conversations yield insights: lower threshold or check chunking.

**Go/no-go gate:** Proceed to full Phase 2 only if calibration extractions look useful to a Prismata player.

## Phase 2: LLM Extraction (Claude Haiku)

### 2A. Extraction prompt template

<!-- CHANGED: quality bar raised, AI_BEHAVIOR removed, patch timeline added, unit reference added, expert list added, temporal_validity field added — Reviewers 1,2,4,5,6,7 -->

```
You are analyzing Prismata Discord conversations for strategic game knowledge.
Prismata is a deterministic turn-based strategy card game (no RNG, perfect information).
Two players build economies, armies, and defenses from a random set of units each game.

=== PATCH HISTORY (for temporal_validity tagging) ===
Pre-2018: Early beta, many units and mechanics different from final game.
2018-2019: Active balance patches. Major rebalance Dec 2017. Venge rework Aug 2018.
           Final major balance patch Jul 2019.
2020+: Game development ended. No further balance changes. All post-2020 advice is current.
If discussing unit strength/weakness that may have changed: tag patch_dependent.
If discussing timeless mechanics or principles: tag timeless.
If discussing pre-2020 meta that may no longer apply: tag historical.
======================

=== KNOWN EXPERTS (high-confidence by default) ===
amalloy, mrguy888, velizar_, masn6811, awaclus, apooche, elyot, liadahlia,
.holyfire, 307th, spiritfryer, .bky_1556, p0lari, mtanzer, steel0229e,
shadourow, extratricky, crash_overlord, mqp, silentslayers, namington
Authors with "Developers" role are authoritative on game mechanics.
======================

=== UNIT NAMES (for entity recognition) ===
Base set: Drone, Engineer, Conduit, Blastforge, Animus, Tarsier, Rhino, Wall,
          Steelsplitter, Gauss Cannon, Forcefield.
Advanced (80+ exist, common abbreviations in chat):
Shadowfang, Pixie, Cauterizer, Cynestra, Drake, Doomed Mech, Borehole Patroller,
Corpus, Husk, Galvani Drone, Zemora Voidbringer, Venge Cannon, Plasmafier,
Wincer, Infestor, Centurion, Grimbotch, Scorchilla, Gaussite Symbiote,
Iso Kronus, Tia Threnody, Plexo Cell, Vai Mauronax, Tatsu Nullifier,
Shiver Yeti, Omega Splitter, Thorium Dynamo, Lucent Hellion, Cryo Ray,
Fission Turret, Grenade Mech, Blood Pact, Apollo, Phase Tiger, Endotherm Kit,
Barrager, Savior, Tantalum Ray, Militia, Cluster Bolt, Manticore, Wild Drone,
Chrono Filter, Tera Sentinel, Research Net, Bloodrager, Thunderhead,
Antima Comet, Vivid Drone, Deadeye Operative, Cataclysm, Colossus.
(Do not hallucinate unit names. Use names as-is if ambiguous.)
======================

=== EXTRACTION TASK ===
Extract game knowledge from these conversations. Apply HIGH quality standards:

Only extract insights that meet ALL of:
  (1) Specific to named units or named strategic concepts — not generic
  (2) Not obvious to any player who has read the basic game rules
  (3) Backed by reasoning, examples, or community agreement in the conversation

Do NOT extract:
  - "Buy drones early" or similar obvious economy advice
  - Pure social chat, jokes without game content
  - Speculation without reasoning or support
  - Balance complaints without citing why or what changed

For each insight, provide:
- category: UNIT_INTERACTION | STRATEGY_RULE | OPENING_THEORY | GAME_MECHANIC |
            BALANCE_OPINION | EXPERT_ASSESSMENT | COMMUNITY_JARGON
- insight: the knowledge (1-3 sentences, precise, name specific units)
- units: array of unit display names mentioned ([] if none)
- confidence: "high" (expert/dev, or strong consensus) /
              "medium" (reasonable player, some agreement) /
              "low" (single unverified claim)
- author: who said it, or "consensus" if multiple agree
- date: approximate date (YYYY-MM)
- replay_code: cited replay code, or null
- context: one sentence on the discussion context
- temporal_validity: "timeless" | "patch_dependent" | "historical"
- source_message_ids: array of Discord message IDs that support this insight (for traceability)

Return ONLY valid JSON. No markdown fences. No commentary outside the array.
Output: JSON array of insight objects. If no qualifying knowledge: [].

--- CONVERSATIONS ---
{chunk_content}
```

### 2B. Schema validation
<!-- CHANGED: added JSON schema validation — Reviewers 4,5,6,7 -->

```python
REQUIRED_FIELDS = ["category", "insight", "units", "confidence", "author",
                   "date", "replay_code", "context", "temporal_validity",
                   "source_message_ids"]
VALID_CATEGORIES = {"UNIT_INTERACTION", "STRATEGY_RULE", "OPENING_THEORY",
                    "GAME_MECHANIC", "BALANCE_OPINION", "EXPERT_ASSESSMENT",
                    "COMMUNITY_JARGON"}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_TEMPORAL = {"timeless", "patch_dependent", "historical"}

For each insight object:
  - All REQUIRED_FIELDS present
  - category in VALID_CATEGORIES
  - confidence in VALID_CONFIDENCE
  - temporal_validity in VALID_TEMPORAL
  - If replay_code not null: must match [A-Za-z0-9+@]{5}-[A-Za-z0-9+@]{5}
  - source_message_ids must be an array of strings (Discord message IDs)
  - If insight > 400 chars: flag as "_flagged: insight_too_long"
```

### 2C. Processing (Batch API — default)

```
Default mode uses Anthropic Message Batches API for 50% cost reduction:

1. Build all requests:
   For each chunk file:
     - Format threads as readable conversation text
     - Prepend: "Channel: {channel} | Date range: {date_range}"
     - Create request object with custom_id = chunk filename

2. Submit batch:
   - client.batches.create(requests=[...])  # up to 10,000 per batch
   - Model: claude-haiku-4-5-20251001
   - Save batch_id to batch_status.json

3. Poll for completion:
   - client.batches.retrieve(batch_id) — check processing_status
   - Poll every 60s. Typical completion: 1-6 hours for ~200 requests.
   - Print progress: "Batch {id}: {succeeded}/{total} complete"

4. Download results:
   - client.batches.results(batch_id) — iterate result stream
   - Parse and validate JSON response per chunk
   - Route by confidence:
       high/medium → extractions/high/{chunk_id}.json
       low → extractions/low/{chunk_id}.json (NOT auto-integrated)
   - Mark chunk as processed in processed_chunks.json

Cost at Batch API pricing (50% off):
  ~200 chunks × ~15K input + ~1.5K output ≈ $0.30-0.50

Use --no-batch flag for synchronous processing (Phase 1.5 calibration
uses this — need instant results for prompt tuning).
```

<!-- CHANGED: low-confidence routing — Reviewer 6 -->

### 2D. Error handling

```
- Retry on API errors (3 attempts with exponential backoff: 2s, 4s, 8s)
- Log failures to failed_chunks.log
- Validate JSON output with schema above
- If output is truncated/invalid: split chunk in half and re-process
- If schema validation fails on a field: log warning, keep insight with _flagged marker
- Strip markdown fences (```json) if present in response
```

**Verification:**
- All chunks processed (check processed_chunks.json)
- Each extraction file contains valid JSON
- Total insights extracted (high/medium): estimate 1,000-3,000
- Print category distribution and temporal_validity distribution

## Phase 3: Consolidation & Dedup

### 3A. Merge all extractions

```
Load all high/medium extraction JSONs → single list of insights
Sort by category, then by confidence (high first)
(Low-confidence insights remain in extractions/low/ — reviewed separately)
```

### 3B. Embedding-based deduplication
<!-- CHANGED: replaced word-overlap with embedding similarity — Reviewers 1-7 -->

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # free, local, ~80MB

# Dedup within (category, primary_unit) buckets for efficiency
# primary_unit = units[0] if units else "__none__"

for (category, primary_unit), group in grouped_insights:
    texts = [i["insight"] for i in group]
    embeddings = model.encode(texts)

    # Pairwise cosine similarity
    # If sim(A, B) >= 0.85: merge
    #   - Keep higher-confidence version
    #   - Combine authors ("amalloy, mrguy888")
    #   - Keep earliest date
    #   - Union all replay codes and source_message_ids
    # Threshold 0.85 catches paraphrases while preserving distinct insights

    # Assign stable import IDs (hash-based, for idempotent re-runs)
    # import_id = sha256(category + insight[:50]).hexdigest()[:12]
    # On re-run: skip insights whose import_id already exists in consolidated JSON
```

### 3C. Cross-reference with existing knowledge base

```
For each merged insight, search docs/commentary-knowledge/*.md:
  - Match on: unit names from insight["units"] + key terms
  - Flag as:
    "new": not found in existing files
    "confirms_existing": corroborates existing content
    "contradicts_existing": conflicts (requires manual review)
  - Store in insight["kb_status"]
```

### 3D. Output

```
discord_knowledge_consolidated.json:
{
  "summary": {
    "total_raw": N, "total_after_dedup": M,
    "by_category": {...}, "by_confidence": {...},
    "by_temporal_validity": {...},
    "kb_status": {"new": K, "confirms": J, "contradicts": L}
  },
  "insights": [ sorted by category then confidence ]
}
```

**Verification:**
- Dedup reduces count by 20-40%
- All 7 categories have some insights (sparse categories OK, not forced)
- Contradictions flagged for manual review

## Phase 3.5: Human Review Gate
<!-- CHANGED: NEW PHASE — Reviewers 4,5,6,7 -->

**STOP. Do not proceed to Phase 4 until this review is complete.**

### Preview document

Script generates `docs/discord-knowledge-extraction-preview.md`:

```markdown
# Discord Knowledge Extraction Preview
Generated: {timestamp}

## Statistics
- Raw insights extracted: N
- After dedup: M  |  New: K  |  Confirms: J  |  Contradicts: L
- Category distribution: [table]
- Temporal validity: [table]

## Contradictions (ALL require review)
[Each: existing KB text vs Discord insight, author, date]

## Top 50 High-Confidence New Insights
[Sorted by confidence, with category/author/date/temporal_validity]

## Category Samples (5 random per category)
[Verify extraction quality across all categories]
```

### Developer checklist

- [ ] Top 50 insights look genuinely useful to a Prismata player
- [ ] No category is producing systematically bad extractions
- [ ] Contradictions reviewed (decide: keep Discord version or KB version)
- [ ] Confidence levels feel appropriately calibrated
- [ ] COMMUNITY_JARGON samples look tone-appropriate
- [ ] Spot-check 5 insights against original Discord messages

**If review fails:** Return to Phase 1.5 and recalibrate. Do NOT proceed with bad extractions.

## Phase 4: Integration (Discord Mirror Directory)
<!-- CHANGED: write to discord/ mirror instead of modifying canonical KB — Reviewers 1-7 -->

**Important:** Phase 4 creates NEW files in a mirror directory. It does NOT modify existing `docs/commentary-knowledge/*.md` files. Promotion to main files is a separate manual step.

### 4A. Create discord mirror directory

```
docs/commentary-knowledge/discord/
  01-game-fundamentals-discord.md    ← GAME_MECHANIC
  03-advanced-units-discord.md       ← UNIT_INTERACTION
  04-strategy-concepts-discord.md    ← STRATEGY_RULE
  05-openings-builds-discord.md      ← OPENING_THEORY
  06-meta-expert-discord.md          ← EXPERT_ASSESSMENT
  08-balance-history-discord.md      ← BALANCE_OPINION (new category)
  discord_jargon_review.md           ← COMMUNITY_JARGON (manual review)
  discord_low_confidence.json        ← low-confidence insights (manual review)
```

### 4B. Source attribution

```
Each new entry gets:
> Source: Discord #{channel} — {author} ({date})

Update sources.md:
### Tier 4: Discord Community Discussion
~222,854 messages from Prismata Discord (2015-2026) — general_chat excluded.
Channels: strategy_advice, unit_and_game_design, ask_a_dev, alpha_player_lounge,
prismata_chat, questions_and_help, dev_seeking_feedback, Prismata League general.
```

### 4C. Replay code index

```
All replay codes from Discord with context:
  { code, channel, author, date, discussion_topic, units_mentioned }

Output: docs/discord-replay-codes.json
```

### 4D. Manual promotion (NOT automated)
<!-- CHANGED: explicit promotion step — Reviewers 1-7 -->

After Phase 4, the developer reviews `docs/commentary-knowledge/discord/` and manually promotes the best insights to the main canonical KB files. Criteria:
- High confidence + timeless or post-2019 relevant
- Not already covered in main files
- Specific enough to be actionable

### 4E. Commentary prompt update (NOT automated)
<!-- CHANGED: explicit distillation note — Reviewer 7 -->

After any main KB files are updated, `tools/commentary_prompt.md` (68 lines, ~2,400 tokens, manually curated) must be updated to incorporate the best new insights. The commentator reads this file directly — it is NOT auto-generated from the KB.

**Verification:**
- `docs/commentary-knowledge/discord/` directory created with all expected files
- No existing knowledge files modified: `git diff docs/commentary-knowledge/*.md` shows zero changes (except sources.md)
- Replay code index created
- Sources.md updated
- `grep -c "Source: Discord" docs/commentary-knowledge/discord/*.md` shows distribution

## Phase 5: Final Verification

1. Count insights per category — verify reasonable distribution
2. Spot-check 10 random insights against original Discord messages
3. Verify no existing knowledge was accidentally overwritten: `git diff docs/commentary-knowledge/*.md`
4. If any insights were promoted to main files: run commentary system on 3 known game states, verify no hallucinated unit names or contradictory advice
5. Save processing stats to `docs/discord-knowledge-extraction-stats.json`

## Channel Processing Priority

Process in this order (stop if budget constrained):

1. **strategy_advice** (~543K tokens) — pure strategy gold, calibration channel
2. **unit_and_game_design** (~548K tokens) — unit theory
3. **ask_a_dev** (~301K tokens) — authoritative mechanics
4. **alpha_player_lounge** (~181K tokens) — expert discussion
5. **dev_seeking_feedback** (~68K tokens) — balance feedback
6. **questions_and_help** (~109K tokens) — intermediate strategy
7. **general (League)** (~92K tokens) — competitive context
8. **prismata_chat** (~1,514K tokens) — high volume, lower density
9. ~~**general_chat**~~ — **SKIP entirely. Off-topic, 843K tokens, zero strategic ROI.**

## Cost Estimate

<!-- CHANGED: updated for general_chat removal, 15K chunks, calibration phase, AI_BEHAVIOR removal — Reviewers 1-7 -->

| Component | Input Tokens | Output Tokens | Cost (Haiku Batch) |
|---|---|---|---|
| Phase 1.5: Calibration (10 chunks, synchronous) | ~150K | ~15K | ~$0.06 |
| Phase 2: Extraction (channels 1-7, batch) | ~1.3M | ~200K | ~$0.29 |
| Phase 2: Extraction (prismata_chat, batch) | ~0.7M | ~100K | ~$0.15 |
| Phase 3: Consolidation (local Python + sentence-transformers) | 0 | 0 | $0.00 |
| **Total (channels 1-7 + calibration)** | | | **~$0.35** |
| **Total (all channels)** | | | **~$0.50** |

Haiku pricing Feb 2026: $0.25/MTok input, $1.25/MTok output.
**Batch API: 50% off** — $0.125/MTok input, $0.625/MTok output. Results within 24hrs.
Calibration phase uses synchronous (full price) for instant feedback; all other extraction uses batch.
After Phase 1 filtering, actual tokens sent are ~40-60% of raw estimates.

## Success Criteria

<!-- CHANGED: replaced "+500 lines" with "100+ novel insights", added human review gate — Reviewers 1-7 -->

| Criterion | Target | How to Measure |
|---|---|---|
| Messages processed | >150K of 222K | Script logs |
| API cost | <$1.00 (batch pricing) | Anthropic dashboard |
| High-confidence novel insights | 100+ | consolidated JSON count |
| Category coverage | All 7 categories populated | Category distribution |
| Temporal validity mix | Has timeless + patch_dependent + historical | JSON output |
| Source attribution | 100% new entries have `> Source: Discord` | grep count |
| No data loss | Existing KB files unchanged (except sources.md) | `git diff` |
| Replay code index | Created with 50+ entries | File existence |
| Human review gate | Developer signs off on preview | Manual checkbox |
| Pipeline re-runnable | processed_chunks.json + embedding dedup | Re-run test |

## Files Created/Modified

<!-- CHANGED: discord/ mirror directory, low-confidence file, jargon review — Reviewers 1-7 -->

| File | Action |
|---|---|
| `tools/discord_knowledge_extractor.py` | **CREATE** — main pipeline (~700-900 lines) |
| `docs/commentary-knowledge/discord/01-game-fundamentals-discord.md` | **CREATE** |
| `docs/commentary-knowledge/discord/03-advanced-units-discord.md` | **CREATE** |
| `docs/commentary-knowledge/discord/04-strategy-concepts-discord.md` | **CREATE** |
| `docs/commentary-knowledge/discord/05-openings-builds-discord.md` | **CREATE** |
| `docs/commentary-knowledge/discord/06-meta-expert-discord.md` | **CREATE** |
| `docs/commentary-knowledge/discord/08-balance-history-discord.md` | **CREATE** — new category |
| `docs/commentary-knowledge/discord/discord_jargon_review.md` | **CREATE** — manual review |
| `docs/commentary-knowledge/discord/discord_low_confidence.json` | **CREATE** — low-confidence insights |
| `docs/commentary-knowledge/sources.md` | **MODIFY** — add Discord as Tier 4 |
| `docs/commentary-knowledge/README.md` | **MODIFY** — add discord/ to index |
| `docs/discord-replay-codes.json` | **CREATE** — replay code index |
| `docs/discord-knowledge-extraction-stats.json` | **CREATE** — processing stats |
| `docs/discord-knowledge-extraction-preview.md` | **CREATE** — Phase 3.5 review doc |
| `docs/commentary-knowledge/01-07*.md` | **DO NOT MODIFY** — promotion is manual |
| `tools/commentary_prompt.md` | **DO NOT MODIFY** — update manually after promotion |

## Data Governance

**What data is stored:**
- Discord message exports (JSON) at `c:/libraries/prismata-replay-parser/discord_exports_full/` — full message content, author handles, timestamps, reactions. These are one-time exports, not continuously synced.
- Extracted insights (JSON) at `docs/commentary-knowledge/discord/` — structured game knowledge with source attribution. Contains author handles and message IDs linking back to Discord.
- Consolidated knowledge base files (Markdown) — anonymized where possible (uses "expert consensus" rather than attributing individuals for merged insights).

**Who has access:** Local development machine only. Not uploaded to any cloud service. Git repository is private (Surfinite/PrismatAlpha fork).

**Retention:** Discord exports are reference data — kept indefinitely for re-extraction if needed. Extracted insights are project artifacts. No PII beyond Discord usernames (public handles).

**Community content usage:** All extracted content originates from public Discord channels. Insights are transformed (summarized, categorized) rather than quoted verbatim. Source attribution preserved for verification.

---

## Optional Enhancements (pick what you want)

The following were suggested by reviewers. Items marked APPLIED have been integrated into the plan above. Remaining items are for future consideration.

| # | Enhancement | Reviewers | Status | Notes |
|---|---|---|---|---|
| 1 | **Anthropic Batch API** for 50% cost reduction (~24hr turnaround) | R3 | **APPLIED** | Default mode for Phase 2. Calibration uses --no-batch for instant results. |
| 2 | **Reaction data as quality signal** | R4 | Already in base plan | Phase 1E: +1 per positive reaction, cap +3 |
| 3 | **Two-stage extraction** (classify then extract) | R4,R7 | Not applied | Medium effort, not worth it at Haiku pricing |
| 4 | **Embedding-first clustering** to reduce API calls | R4 | Not applied | Complex to implement, already getting embedding value from dedup |
| 5 | **Unit-centric extraction** per-unit queries | R7 | Not applied | 105x more API calls. Consider for targeted follow-up |
| 6 | **Verbatim evidence field** (`source_message_ids`) | R5 | **APPLIED** | Added to extraction schema and validation |
| 7 | **Stable import IDs** (hash-based) | R5 | **APPLIED** | Added to Phase 3B dedup — sha256(category + insight[:50]) |
| 8 | **Data governance section** | R5 | **APPLIED** | Added as standalone section before this table |
| 9 | **Expert frequency-by-channel report** | R7 | **APPLIED** | Added to dry-run output (Phase 1A) |
| 10 | **Embed content extraction** | R7 | **APPLIED** | Added to Phase 1B — extract embed title/description/fields |
| 11 | **Sonnet for consolidation** — quality review pass | R5 | **INVESTIGATE LATER** | ~$1-2 cost. Sonnet reviews batches of 50-100 insights for miscategorization, vague items, confidence miscalibration. Worth doing if Haiku extraction quality is borderline after calibration. |
| 12 | **Per-channel stats** in dry-run output | R7 | **APPLIED** | Added to Phase 1A dry-run table output |
| 13 | **Token counting with tiktoken** | R4,R6 | **APPLIED** | Added to pre-run setup, dry-run, and Phase 1F chunking. Independent from Batch API (#1). |
