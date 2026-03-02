# Plan: Full Prismata Discord Knowledge Extraction

**Status:** PLANNED
**Created:** 2026-02-21
**Estimated cost:** ~$2-4 (Haiku API for bulk extraction)
**Estimated time:** ~2-3 hours (mostly automated)

## Objective

Process all 274,000 human messages from the Prismata Discord (2016-2026, ~4.2M tokens) to extract structured game knowledge. This is the only major source NOT yet incorporated into the commentary knowledge base (which already has 280+ sources from YouTube, blogs, Reddit, wiki, Twitch).

## Data Summary

| Channel | Messages | Est. Tokens | Strategic Value |
|---|---|---|---|
| strategy_advice | 34,315 | ~543K | **Highest** — pure strategy discussion |
| unit_and_game_design | 35,050 | ~548K | **High** — unit interactions, balance theory |
| ask_a_dev | 14,553 | ~301K | **High** — authoritative game mechanics |
| alpha_player_lounge | 12,672 | ~181K | **High** — expert-only discussion |
| prismata_chat | 106,229 | ~1,514K | **Medium** — high volume, mixed quality |
| questions_and_help | 7,241 | ~109K | **Medium** — beginner/intermediate |
| general (League) | 5,891 | ~92K | **Medium** — competitive discussion |
| dev_seeking_feedback | 3,567 | ~68K | **Medium** — balance feedback |
| general_chat | 53,865 | ~843K | **Low** — off-topic channel |
| League results (4ch) | 760 | ~2K | **Low** — match scores only |
| **TOTAL** | **274,143** | **~4,208K** | |

## Architecture

```
Discord JSON exports (289 MB, 14 files)
    |
    v
[Phase 1] Python pre-filter & chunker
    |  - Remove empty/short (<20 char) messages
    |  - Remove bot messages
    |  - Group into conversation threads (5-min proximity)
    |  - Split into ~30K token chunks preserving thread boundaries
    |  - Priority-sort channels (strategy first)
    |
    v
[Phase 2] Claude Haiku extraction (batch API)
    |  - Each chunk gets a focused extraction prompt
    |  - 8 extraction categories (see below)
    |  - Output: structured JSON per chunk
    |
    v
[Phase 3] Consolidation & dedup
    |  - Merge extracted knowledge across chunks
    |  - Deduplicate similar insights
    |  - Cross-reference with existing knowledge base
    |  - Attribution (author, date, replay code)
    |
    v
[Phase 4] Integration
    - Merge into docs/commentary-knowledge/ files
    - Create new discord-specific files where appropriate
    - Update sources.md with Discord as a source
```

## Extraction Categories

These align with and extend the existing commentary knowledge base structure:

| Category | Maps To | What To Extract |
|---|---|---|
| **unit_interactions** | 03-advanced-units.md | Unit synergies, counters, combo assessments, tier opinions |
| **strategy_rules** | 04-strategy-concepts.md | Heuristics, rules of thumb, strategic principles |
| **opening_theory** | 05-openings-builds.md | Build orders, timing analysis, opening evaluation |
| **game_mechanics** | 01-game-fundamentals.md | Rules clarifications, mechanic explanations (esp. from devs) |
| **ai_behavior** | discord-masterbot-feedback-analysis.md | MB bugs/quirks (already done, skip or light pass) |
| **balance_opinions** | NEW: 08-balance-history.md | Unit balance assessments, patch reactions, meta shifts |
| **expert_assessments** | 06-meta-expert.md | Player-level analysis, set reading examples, replay breakdowns |
| **community_jargon** | 07-commentary-phrases.md | Slang, memes, catchphrases, community references |

## Phase 0: Documentation & Infrastructure Check

**Already confirmed:**
- `anthropic` Python SDK 0.83.0 installed (Claude API access)
- Discord exports at `c:/libraries/prismata-replay-parser/discord_exports_full/` (14 JSON files, 289 MB)
- JSON schema: 14 fields per message (id, type, timestamp, content, author{id,name,isBot,roles}, attachments, embeds, reactions, mentions, etc.)
- Existing search script pattern at `tools/search_discord_ai_feedback.py`
- Commentary knowledge base at `docs/commentary-knowledge/` (7 files, ~5,090 lines, 280+ sources — Discord not yet included)

**Anti-patterns to avoid:**
- Do NOT load entire export files into memory at once for LLM processing (106K messages = 1.5M tokens in prismata_chat alone)
- Do NOT use raw message text without context — conversations need thread grouping
- Do NOT send messages <20 chars to the LLM (reactions, one-word replies waste tokens)
- Do NOT process general_chat (off-topic) unless time permits — lowest ROI
- Must use `PYTHONIOENCODING=utf-8` for all Python scripts (cp1252 encoding errors on Windows)

## Phase 1: Pre-Filter & Chunk Pipeline

**Script:** `tools/discord_knowledge_extractor.py`

### 1A. Message filtering
```
For each channel JSON:
  - Skip bot messages (author.isBot == true)
  - Skip empty/whitespace-only content
  - Skip messages < 20 characters (reactions, "lol", "nice", etc.)
  - Keep messages with embeds even if content is short
  - Track reply chains via reference.messageId
```

### 1B. Thread grouping
```
Group sequential messages into "threads":
  - Same channel, messages within 5 minutes of each other = same thread
  - Explicit Reply references extend threads across time gaps
  - Each thread has: participants, timestamps, full text, replay codes
  - Minimum thread size: 2 messages (skip orphan messages <100 chars)
```

### 1C. Quality scoring & filtering
```
Score each thread:
  - +2 per message from known expert (amalloy, mrguy888, velizar_, masn6811,
    awaclus, apooche, elyot, liadahlia, .holyfire, 307th, spiritfryer,
    .bky_1556, p0lari, mtanzer, steel0229e, shadourow, extratricky,
    crash_overlord, mqp, silentslayers, namington)
  - +1 per message from Alpha Player role
  - +1 per message > 100 characters
  - +2 per message > 200 characters
  - +1 per replay code detected (regex: [A-Za-z0-9+@]{5}-[A-Za-z0-9+@]{5})
  - +1 per unit name mentioned (from cardLibrary.jso display names)
  - -1 per message from "Deleted User" (can't verify expertise)

  Discard threads with score < 3
```

### 1D. Chunking
```
Assemble threads into chunks targeting ~25K tokens each:
  - Never split a thread across chunks
  - Group by channel (process strategy_advice first, then unit_and_game_design, etc.)
  - Each chunk includes: channel name, date range, thread count
  - Estimated chunks: ~120-150 total across all channels
```

### 1E. Output
```
Output: chunks/ directory with numbered JSON files
Each chunk: {
  channel, date_range, thread_count,
  threads: [{ participants, timestamp_start, timestamp_end, messages: [{author, content, timestamp}] }]
}
```

**Verification:**
- Total messages after filtering should be ~40-80K (15-30% of raw 274K)
- No chunk exceeds 30K tokens
- strategy_advice and unit_and_game_design channels produce the most chunks
- Print summary stats: messages filtered, threads created, chunks generated

## Phase 2: LLM Extraction (Claude Haiku Batch)

### 2A. Extraction prompt template

```
You are analyzing Prismata Discord conversations for strategic knowledge.
Prismata is a deterministic turn-based strategy card game.

Extract ALL actionable game knowledge from these conversations.
For each insight, classify into one of these categories:

1. UNIT_INTERACTION: How specific units work together or against each other
2. STRATEGY_RULE: General strategic principle or rule of thumb
3. OPENING_THEORY: Build order, timing, or opening evaluation
4. GAME_MECHANIC: Rules clarification or mechanic explanation
5. BALANCE_OPINION: Unit balance assessment or meta shift observation
6. EXPERT_ASSESSMENT: High-level game analysis, set reading, position evaluation
7. COMMUNITY_JARGON: Slang, memes, catchphrases used by the community
8. AI_BEHAVIOR: Master Bot bugs, quirks, or behavioral observations

For each extracted insight, provide:
- category: one of the 8 above
- insight: the actual knowledge (1-3 sentences, precise)
- units: list of unit names mentioned (display names)
- confidence: high/medium/low (based on author expertise and community agreement)
- author: who said it (or "consensus" if multiple agree)
- date: approximate date
- replay_code: if a replay code was cited as evidence (null otherwise)
- context: brief note on the discussion context

Skip:
- Pure social chat, jokes without game content
- Repetitive basic advice ("buy drones", "defend properly")
- Speculation without reasoning
- Out-of-date balance complaints about units that were later patched
  (unless the complaint itself is historically interesting)

Output: JSON array of insight objects. If a conversation has no extractable
knowledge, return an empty array [].

--- CONVERSATIONS ---
{chunk_content}
```

### 2B. Processing
```
For each chunk file:
  - Format threads as readable conversation text
  - Send to Claude Haiku via anthropic SDK
  - Parse JSON response
  - Save raw response to extractions/{chunk_id}.json
  - Rate limit: ~5 requests/sec (Haiku is fast)
  - Cost estimate: ~150 chunks × ~25K input + ~2K output ≈ $0.50-1.50 on Haiku
```

### 2C. Error handling
```
- Retry on API errors (3 attempts with exponential backoff)
- Log any chunks that fail after retries
- Validate JSON output (must be array of objects with required fields)
- If output is truncated, split chunk and re-process halves
```

**Verification:**
- All chunks processed (no failures)
- Each extraction file contains valid JSON
- Total insights extracted: estimate 2,000-5,000 across all chunks
- Print category distribution

## Phase 3: Consolidation & Dedup

### 3A. Merge all extractions
```
Load all extraction JSONs → single list of insights
Sort by category, then by confidence (high first)
```

### 3B. Deduplication
```
For each pair of insights in the same category:
  - If units overlap AND insight text is semantically similar (>80% overlap
    after normalization), merge:
    - Keep higher-confidence version
    - Combine authors ("amalloy, mrguy888")
    - Keep earliest date
    - Keep all replay codes

  Use simple text similarity (word overlap ratio) — no LLM needed for dedup
```

### 3C. Cross-reference with existing knowledge base
```
For each insight, check if it's already in docs/commentary-knowledge/:
  - Search existing files for unit names + key terms
  - Flag as "new" or "confirms existing" or "contradicts existing"
  - Contradictions get manual review flag
```

### 3D. Output
```
discord_knowledge_consolidated.json:
{
  summary: { total_insights, by_category, by_confidence, new_vs_existing },
  insights: [ sorted by category then confidence ]
}
```

**Verification:**
- Dedup reduces insight count by 20-40%
- Cross-reference identifies which existing knowledge is confirmed
- No category has zero insights
- New insights that contradict existing knowledge are flagged

## Phase 4: Integration

### 4A. Merge into existing knowledge base files

For each category, append new Discord-sourced insights to the matching file:

| Category | Target File | Action |
|---|---|---|
| UNIT_INTERACTION | 03-advanced-units.md | Append unit profiles, add synergy/counter notes |
| STRATEGY_RULE | 04-strategy-concepts.md | Append new concepts, enrich existing sections |
| OPENING_THEORY | 05-openings-builds.md | Add new openings, validate existing ones |
| GAME_MECHANIC | 01-game-fundamentals.md | Add clarifications (esp. dev-confirmed) |
| BALANCE_OPINION | **NEW** 08-balance-history.md | Create new file with balance meta timeline |
| EXPERT_ASSESSMENT | 06-meta-expert.md | Add set reading examples, player analyses |
| COMMUNITY_JARGON | 07-commentary-phrases.md | Add slang, memes, community references |
| AI_BEHAVIOR | discord-masterbot-feedback-analysis.md | Already done — skip or light merge |

### 4B. Source attribution
```
Each new entry gets:
> Source: Discord #{channel} — {author} ({date})

Add Discord to sources.md:
### Tier 4: Discord Community Discussion
274,143 messages from Prismata Discord (2016-2026).
Channels: prismata_chat, strategy_advice, unit_and_game_design,
ask_a_dev, alpha_player_lounge, questions_and_help,
dev_seeking_feedback, Prismata League general.
```

### 4C. Create replay code index
```
All replay codes mentioned in Discord with context:
  { code, channel, author, date, discussion_topic, units_mentioned }

Output: docs/discord-replay-codes.json
This enables future replay analysis of community-discussed games.
```

**Verification:**
- All commentary-knowledge files updated with Discord source marker
- sources.md lists Discord as a source
- Replay code index created
- No existing knowledge was accidentally deleted or overwritten
- `grep -c "Source: Discord" docs/commentary-knowledge/*.md` shows distribution

## Phase 5: Final Verification

1. Count insights per category — ensure reasonable distribution
2. Spot-check 10 random insights against original Discord messages
3. Verify no duplicate entries between Discord-sourced and pre-existing knowledge
4. Run the commentary system with updated knowledge to ensure no regressions
5. Save processing stats to `docs/discord-knowledge-extraction-stats.json`

## Channel Processing Priority

Process in this order (highest value first, stop if time/budget constrained):

1. **strategy_advice** (~543K tokens) — pure strategy gold
2. **unit_and_game_design** (~548K tokens) — unit theory
3. **ask_a_dev** (~301K tokens) — authoritative mechanics
4. **alpha_player_lounge** (~181K tokens) — expert discussion
5. **dev_seeking_feedback** (~68K tokens) — balance feedback
6. **questions_and_help** (~109K tokens) — intermediate strategy
7. **general (League)** (~92K tokens) — competitive context
8. **prismata_chat** (~1,514K tokens) — high volume, lower density
9. **general_chat** (~843K tokens) — off-topic, skip unless time permits

## Cost Estimate

| Component | Input Tokens | Output Tokens | Cost (Haiku) |
|---|---|---|---|
| Phase 2: Extraction (high-value channels 1-7) | ~1.9M | ~300K | ~$0.80 |
| Phase 2: Extraction (prismata_chat) | ~1.0M | ~200K | ~$0.45 |
| Phase 3: Consolidation (local Python) | 0 | 0 | $0.00 |
| Phase 4: Integration (optional Haiku for formatting) | ~200K | ~100K | ~$0.10 |
| **Total (channels 1-7)** | | | **~$0.90** |
| **Total (all channels)** | | | **~$1.35** |

Note: Haiku pricing as of Feb 2026: $0.25/MTok input, $1.25/MTok output.
After quality filtering (Phase 1), actual tokens sent will be ~40-60% of raw estimates.

## Files Created/Modified

| File | Action |
|---|---|
| `tools/discord_knowledge_extractor.py` | **CREATE** — main extraction pipeline |
| `docs/commentary-knowledge/08-balance-history.md` | **CREATE** — balance meta timeline |
| `docs/commentary-knowledge/01-07*.md` | **MODIFY** — append Discord insights |
| `docs/commentary-knowledge/sources.md` | **MODIFY** — add Discord source |
| `docs/commentary-knowledge/README.md` | **MODIFY** — add 08 to index |
| `docs/discord-replay-codes.json` | **CREATE** — replay code index |
| `docs/discord-knowledge-extraction-stats.json` | **CREATE** — processing stats |
