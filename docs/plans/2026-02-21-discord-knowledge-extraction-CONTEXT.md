# Context Document: Full Prismata Discord Knowledge Extraction

**Accompanying plan:** `2026-02-21-discord-knowledge-extraction.md`

---

## 1. Reviewer Brief

You are receiving two documents: this context document and a plan for extracting structured game knowledge from 274,000 Discord messages.

Your role is to **critically analyze** the plan given the context provided. You should identify: weaknesses, risks, missing considerations, better alternatives, unnecessary complexity, things that should be removed, and things that are good and should be preserved.

You should also suggest additions, potential future features worth considering, and architectural improvements. Be constructively critical -- not rubber-stamping. Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable.

**Important**: You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making about the code.

### Review Output Format

Structure your review as follows:

1. **One-line verdict**: Your overall assessment in a single sentence.
2. **What's good**: What should be kept as-is and why.
3. **Concerns & risks**: What worries you, ranked by severity.
4. **Suggested changes**: Specific, actionable modifications to the plan.
5. **Alternatives**: Different approaches worth considering.
6. **Additions**: Things missing from the plan that should be there.
7. **Removals**: Things in the plan that shouldn't be.
8. **Minor / nits**: Low-priority observations.
9. **Assumptions you're making**: Where you lacked visibility into the codebase and had to guess. The plan author will validate these.

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism -- the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

### What It Is

**PrismataAI** is a C++ game engine and AI system for **Prismata**, a deterministic turn-based perfect-information strategy card game by Lunarch Studios. The engine simulates game states, and the AI uses Alpha-Beta search, UCT/MCTS, and a neural network evaluation function trained via self-play.

### Current Stage

Mature codebase (originally by David Churchill, academic research) being extended with:
- A neural network evaluation function trained on ~722K self-play games (45.3% win rate vs the original strongest AI)
- A live AI commentator that watches games and generates strategic commentary via Claude Haiku
- Heuristic improvements to the move generation system based on community feedback

### What This Plan Does

The plan processes the **entire Prismata Discord community archive** (274K messages, 2016-2026) to extract structured game knowledge. This knowledge feeds two systems:
1. **Commentary knowledge base** -- used in the AI commentator's system prompt so it can discuss strategy intelligently
2. **Heuristic improvement roadmap** -- community-reported AI behavioral issues that inform C++ code fixes

### Constraints
- **Budget**: ~$1-4 for LLM API costs (user is cost-conscious)
- **Timeline**: A few hours (mostly automated pipeline)
- **Team**: Solo developer + Claude Code AI assistant
- **Platform**: Windows 11, Python 3.13, Git Bash

---

## 3. Architecture & Tech Stack

### Languages & Frameworks
- **C++** (game engine, ~80K LOC, x86 only, Visual Studio 2022)
- **Python** (training pipeline, tools, scripts)
- **Node.js** (dashboard/monitoring server)
- **Claude API** (Haiku model for commentary and extraction)

### Relevant Architecture for This Plan

```
Discord JSON exports (289 MB)          Commentary Knowledge Base
  |                                      (docs/commentary-knowledge/)
  |  14 channel export files              7 markdown files, ~5,090 lines
  |  DiscordChatExporter v2.46            280+ sources (YouTube, blogs,
  |  274K messages, ~4.2M tokens          Reddit, wiki, Twitch -- NO Discord yet)
  |                                      |
  v                                      v
[Python extraction pipeline]  ------>  [Merged knowledge files]
  |  tools/discord_knowledge_extractor.py    |
  |  Claude Haiku API for categorization     v
  |  Local Python for filtering/dedup     [AI Commentator]
  |                                        tools/prismata_commentator.py
  v                                        Uses knowledge base in system prompt
[Structured JSON extractions]              Generates per-turn game commentary
  |
  v
[Master Bot improvement roadmap]
  docs/discord-masterbot-feedback-analysis.md
  Already completed: 596-line analysis of MB behavioral issues
```

### Key Architectural Decisions
- **Claude Haiku** for extraction (not Sonnet/Opus): cost optimization. 274K messages at Haiku pricing = ~$1.35 vs ~$15+ on Sonnet.
- **Pre-filter in Python before LLM**: Most messages are short social chat (<20 chars). Sending everything to Haiku would waste ~60% of the budget on noise.
- **Thread grouping**: Discord conversations are not threaded (mostly sequential messages). Grouping by time proximity preserves conversational context that individual messages lack.
- **Chunk-based processing**: No single LLM call can handle 4.2M tokens. Chunking at ~25K tokens per call with thread-boundary preservation is the standard approach.

---

## 4. Codebase Map

### Directory Structure (relevant portions)

```
PrismataAI/
  docs/
    commentary-knowledge/       # TARGET: knowledge base to enrich
      01-game-fundamentals.md   #   433 lines - game rules, mechanics
      02-base-set-units.md      #   205 lines - 11 base units
      03-advanced-units.md      # 1,266 lines - 80+ advanced unit profiles
      04-strategy-concepts.md   # 1,203 lines - strategy theory
      05-openings-builds.md     #   511 lines - build orders
      06-meta-expert.md         #   744 lines - meta/player analysis
      07-commentary-phrases.md  #   728 lines - jargon, templates
      sources.md                #   292 lines - source attribution
      README.md                 #    47 lines - index
    discord-masterbot-feedback-analysis.md  # DONE: 596-line MB issue analysis
    plans/
      2026-02-21-discord-knowledge-extraction.md  # THE PLAN
  tools/
    search_discord_ai_feedback.py    # Existing: regex-based Discord search (243 lines)
    prismata_commentator.py          # Consumer: live commentary engine
    prismata_game_state.py           # Shared game state model
    commentary_prompt.md             # Condensed knowledge for system prompt (~2,400 tokens)
  bin/
    discord_ai_feedback.json         # Output: 2,095 bot-behavior matches
    asset/config/
      cardLibrary.jso                # Master unit definitions (105+ units, display names)

c:/libraries/prismata-replay-parser/
  discord_exports_full/              # SOURCE: 14 JSON files, 289 MB total
    Prismata - prismata_chat [...].json        # 107K msgs, 113 MB
    Prismata - strategy_advice [...].json      #  35K msgs,  34 MB
    Prismata - unit_and_game_design [...].json  #  35K msgs,  35 MB
    Prismata - ask_a_dev [...].json             #  15K msgs,  18 MB
    Prismata - alpha_player_lounge [...].json   #  13K msgs,  13 MB
    ... (9 more channels)
```

### Key Files for This Plan

| File | Role | Size |
|---|---|---|
| `tools/search_discord_ai_feedback.py` | Existing pattern to build on (regex search, context windows, JSON output) | 243 lines |
| `tools/discord_knowledge_extractor.py` | **To be created** -- main extraction pipeline | ~400-600 lines est. |
| `docs/commentary-knowledge/*.md` | Target files for knowledge integration | 5,090 lines total |
| `docs/commentary-knowledge/sources.md` | Source tracking -- Discord to be added | 292 lines |
| `bin/asset/config/cardLibrary.jso` | Unit name reference (display names for matching) | ~3,000 lines |
| `tools/prismata_commentator.py` | Consumer of the knowledge base (reads via system prompt) | ~300 lines |

---

## 5. Relevant Existing Patterns & Conventions

### Knowledge Base Format

Each knowledge file uses this pattern:
```markdown
## Section Title

**Subsection**
- Bullet point insight
- Another insight with specific unit names

> Source: prismatalibrary.blog -- 307th (2018)
```

Every entry has a `> Source:` attribution line. The plan must maintain this convention.

### Existing Search Script Pattern

`tools/search_discord_ai_feedback.py` demonstrates:
- Loading all Discord export JSONs from a directory
- Regex-based keyword matching by category
- Context window extraction (2 messages before/after)
- Embed text scanning (title + description + fields)
- Per-author and per-category statistics
- JSON output with summary + results

The new extraction script should follow this pattern for Phase 1 (filtering) but adds LLM-based extraction in Phase 2.

### Commentary System Prompt

The commentator loads a condensed version of the knowledge base (~2,400 tokens) into its system prompt. The full knowledge base files (5,090 lines) are too large for direct inclusion -- they're used as a reference that gets distilled into `tools/commentary_prompt.md`.

### Windows/Python Environment Quirks

- Must use `PYTHONIOENCODING=utf-8` (Windows defaults to cp1252)
- Must use `PYTHONUNBUFFERED=1` for long-running scripts in Claude Code
- `python` not `python3` on Windows
- Discord emojis contain Unicode characters that cause encoding errors without UTF-8

---

## 6. Current State & Known Issues

### What Works Today

- **Discord exports completed**: 14 channels, 289 MB, all accessible at `discord_exports_full/`
- **Bot behavior search completed**: `search_discord_ai_feedback.py` found 2,095 matches across 6 categories
- **MB feedback analysis completed**: 596-line report at `discord-masterbot-feedback-analysis.md` identifying 18+ behavioral issues with replay codes
- **Commentary knowledge base built**: 5,090 lines across 7 files from 280+ sources (YouTube, blogs, Reddit, wiki, Twitch) -- Discord is the one major missing source
- **Live commentator working**: Phase 1 tested, generates per-turn commentary via Claude Haiku

### Known Issues Relevant to This Plan

1. **Discord reply threading is sparse**: Only 0.8% of messages use Discord's Reply feature. Most conversation threading is implicit (sequential messages, @mentions). The 5-minute proximity grouping in Phase 1B is a heuristic approximation.

2. **"Deleted User" messages**: 3,500+ messages from deleted accounts. Content preserved but author expertise can't be verified. The plan's -1 scoring penalty may be too aggressive or too lenient.

3. **Image/screenshot content inaccessible**: Many strategy discussions reference screenshots of board states. These are CDN URLs in attachment fields -- the text content alone misses this visual context. No OCR or image analysis is planned.

4. **Temporal context matters**: Prismata has had ~20 balance patches over 8 years. Strategy advice from 2018 may be outdated. The plan's extraction prompt says to skip "out-of-date balance complaints about units that were later patched" but doesn't provide patch history for Haiku to reference.

5. **Community expertise varies widely**: Messages range from complete beginners to world-class players (amalloy, 307th, apooche). The quality scoring in Phase 1C helps, but Haiku may not distinguish expert-level from novice-level insights within a chunk.

6. **prismata_chat is 61% of all messages but lowest signal density**: The plan correctly deprioritizes it (channel #8 of 9) but it still contains valuable content intermixed with social chat. The pre-filter's effectiveness on this channel is uncertain.

### Recent Changes

- **Heuristic fixes deployed to AWS eval fleet** (12 spot instances running, results pending): Fixed Borehole/Pixie cost, Corpus/Husk cost, Galvani breach targeting, health/stamina in breach targeting. These changes were informed by the MB feedback analysis.
- **Commentary knowledge base created 24 hours ago** (Feb 20, 2026): 280+ sources processed. The Discord extraction would be the first major addition.

---

## 7. Context Specific to the Plan

### What the Plan Touches

1. **Creates** `tools/discord_knowledge_extractor.py` -- new Python script (~400-600 lines)
2. **Creates** `docs/commentary-knowledge/08-balance-history.md` -- new knowledge category
3. **Modifies** all 7 existing knowledge files (appending Discord-sourced entries)
4. **Modifies** `sources.md` and `README.md` (adding Discord as a source)
5. **Creates** `docs/discord-replay-codes.json` -- index of replay codes mentioned in Discord

### Dependencies

- **Claude API key**: Already configured and working (used by commentator)
- **anthropic Python SDK**: v0.83.0 installed
- **Discord export data**: Already exported and available
- **cardLibrary.jso**: Needed for unit name matching in Phase 1C quality scoring

### Prior Approaches

1. **Regex keyword search** (completed): `search_discord_ai_feedback.py` with 6 keyword categories found 2,095 matches (0.8% of messages). Good for targeted bot behavior search, but misses the vast majority of strategic knowledge that doesn't mention "bot" or "AI."

2. **Commentary knowledge extraction from other sources** (completed, Feb 20): 280+ sources processed using a multi-pass approach with Claude. YouTube transcripts, blog articles, Reddit posts, wiki pages, and Twitch VODs. Discord was listed in the plan but not yet processed.

### Performance Considerations

- **Memory**: The largest export file (prismata_chat) is 113 MB of JSON. Python can load this in memory (~200-300 MB RAM) -- not a problem on a 32GB system.
- **API rate limits**: Haiku has generous rate limits. At ~5 req/sec, 150 chunks would take ~30 seconds of API time. The bottleneck is the Python pre-processing, not the API.
- **Disk space**: Intermediate files (chunks + extractions) will be ~50-100 MB. Trivial.

---

## 8. Scope Boundaries

### Explicitly Out of Scope

- **Image/screenshot analysis**: Discord messages reference game state screenshots. Extracting visual information would require image download + multimodal analysis. High complexity, low marginal value over text-only extraction.
- **Real-time Discord monitoring**: This is a one-shot batch extraction of historical data. Continuous monitoring would be a separate system.
- **Retraining the neural net on extracted knowledge**: The extracted knowledge improves the commentator and informs heuristic fixes, but does not directly feed into the training pipeline.
- **Cross-server Discord data**: Only the Prismata (112616041175089152) and Prismata League (412991183355248640) servers are exported.

### Fixed and Non-Negotiable

- **Claude Haiku for extraction** (not Sonnet): Budget constraint. ~$1.35 vs ~$15+.
- **Python as the implementation language**: Existing tooling is all Python, Claude API SDK is Python.
- **Append-only to existing knowledge files**: No restructuring of the existing 7 knowledge files. New Discord entries are appended with source attribution.
- **DiscordChatExporter JSON format**: The export format is fixed. We work with what we have.

### Known Trade-offs

- **Thread grouping by 5-min proximity is imperfect**: Some conversations span hours with gaps. We accept some context loss at thread boundaries in exchange for manageable chunk sizes.
- **Haiku may miss nuanced strategic insights**: Haiku is optimized for speed/cost, not deep domain expertise. Some expert-level insights may be miscategorized or missed entirely. Accepted because the volume (274K messages) makes manual review infeasible.
- **"Deleted User" content is included with a penalty**: We could exclude it entirely, but some deleted accounts were active expert players. The -1 penalty in quality scoring is a compromise.

---

## 9. Success Criteria

| Criterion | Target | How to Measure |
|---|---|---|
| Messages processed | >200K of 274K | Script logs |
| API cost | <$4 | Anthropic dashboard |
| Insights extracted | 2,000-5,000 | JSON output count |
| Category coverage | All 8 categories populated | Category distribution report |
| Knowledge base growth | +500 lines minimum | `wc -l` before/after |
| Source attribution | 100% of new entries have `> Source: Discord` | `grep -c "Source: Discord"` |
| No data loss | Existing knowledge files unchanged except for appends | `git diff` shows only additions |
| Replay code index | Created with 50+ entries | File existence + count |
| Pipeline is re-runnable | Can process new exports without duplicating | Dedup in Phase 3 handles this |

---

## 10. Key Questions for Reviewers

1. **Thread grouping quality**: The plan uses 5-minute proximity as the thread boundary. Is this too aggressive (splits real conversations) or too lenient (merges unrelated messages)? What alternative grouping strategies should we consider? The reply reference field is only present on 0.8% of messages.

2. **Quality scoring calibration**: Phase 1C scores threads based on expert presence, message length, unit mentions, and replay codes. The threshold (discard < 3) was chosen intuitively. Is this scoring system likely to filter the right content? Should the weights be different? Should we use a calibration sample first?

3. **LLM extraction prompt design**: The Phase 2A prompt asks Haiku to extract insights across 8 categories from conversation chunks. Is the prompt well-structured for reliable extraction? Should we use separate prompts per category for better precision? Should we provide Haiku with game reference material (unit list, resource types) to improve classification?

4. **Deduplication approach**: Phase 3B uses word overlap ratio for dedup. Given that the same strategic insight may be expressed in very different ways by different players, is this sufficient? Should we use embeddings or an LLM dedup pass?

5. **Integration strategy**: Phase 4 appends to existing knowledge files. With potentially 2,000-5,000 new insights, will the knowledge files become unwieldy? Should Discord-sourced knowledge go in separate files instead (e.g., `03-advanced-units-discord.md`)? Or should we use a more selective integration that only adds genuinely novel insights?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **Prismata** | Deterministic turn-based strategy card game. No hidden information, no RNG. Two players build economies, armies, and defenses from a shared random set of 8 advanced units (plus 11 base units always available). |
| **Master Bot (MB)** | The strongest built-in AI opponent in Prismata. Uses Alpha-Beta search with heuristic move generation. Community estimates it at ~1400 Elo. |
| **Unit** | A card that can be purchased and placed on the board. Units have costs (gold + colored resources), health, abilities, lifespan/stamina, and may be attackers, defenders, or economic. |
| **Set / Random set** | The 8 randomly selected advanced units available in a particular game, in addition to the 11 base units. Strategy depends heavily on which units are in the set. |
| **Breach** | When a player cannot fully defend against incoming attack damage, the excess damage is assigned to their non-blocking units (attackers, economy, tech buildings). |
| **Absorb** | The highest-health defender blocks damage each turn. Absorbing on the right unit (the one that survives to absorb again) is critical. |
| **Stamina** | How many times a unit can block before dying. A 0-stamina unit will die at end of turn regardless -- absorbing on it wastes the absorb. |
| **Chill / Freeze** | Mechanic that disables a defender for one turn, preventing it from blocking. Targeting the main absorber with chill is high-value. |
| **Will Score** | The heuristic evaluation function used by the AI. Values units based on resource costs (ATTACK=2.25, BLUE=1.50, GREEN=1.20, GOLD=1.00, RED=0.90, ENERGY=0.50). |
| **GreedyKnapsack** | The buy-phase heuristic that selects which units to purchase. Evaluates units by value-per-cost, which can overvalue expensive units that create sub-units (e.g., Borehole creates a Pixie). |
| **PartialPlayer** | AI architecture that decomposes each turn into phases (Defense, ActionAbility, ActionBuy, Breach) and uses specialized heuristics for each. |
| **Opening** | The first few turns of a game, usually following established build orders (e.g., "DD/DDE/DDA" = Drone Drone / Drone Drone Engineer / Drone Drone Animus). |
| **Replay code** | A 11-character code (format: `XXXXX-XXXXX`) that identifies a stored game. Games can be replayed by entering this code. |
| **Commentary knowledge base** | 7 markdown files (~5,090 lines) containing extracted game knowledge from 280+ sources. Used to inform the AI commentator's system prompt. |
| **Claude Haiku** | Anthropic's fastest/cheapest model. Used for high-volume extraction tasks. Model ID: `claude-haiku-4-5-20251001`. |
| **DiscordChatExporter** | Third-party tool for exporting Discord channel history to JSON. Located at `c:\libraries\DiscordChatExporter\cli\`. |
| **cardLibrary.jso** | Master unit definition file with 105+ units. Contains both internal codenames (e.g., "Tesla Tower") and display names (e.g., "Tarsier"). |
| **Self-play** | Training data generation method where the AI plays games against itself. Currently ~722K games generated, used to train the neural evaluation function. |
| **Borehole Patroller** | Unit that creates a Pixie sub-unit when purchased. The AI historically overvalued it because the cost proxy included the Pixie's cost. Recently fixed. |
| **Corpus** | Unit that creates a Husk sub-unit when purchased. Same overvaluation bug as Borehole, recently fixed. |
| **Galvani Drone** | Cheap economy unit (3GB). AI historically targeted it during breach instead of more valuable units. Recently fixed via health/stamina-aware breach targeting. |
