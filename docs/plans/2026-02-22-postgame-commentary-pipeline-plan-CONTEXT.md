# Context Document: Post-Game Replay Commentary Pipeline

**Plan file:** `2026-02-22-postgame-commentary-pipeline-plan.md` (provided alongside this document)

---

## 1. Reviewer Brief

You are receiving **two documents**: this context document and an implementation plan.

**Your role:** Critically analyze the plan given the context provided. You should:
- Identify: weaknesses, risks, missing considerations, better alternatives, unnecessary complexity, things that should be removed, and things that are good and should be preserved.
- Suggest additions, potential future features worth considering, and architectural improvements.
- Be constructively critical — not rubber-stamping.
- Your review will be synthesized in a meta-review to improve the plan, so be specific and actionable.

**Important:** You do NOT have direct access to the codebase. You are working from this context document only. The plan author has full codebase access and will validate all suggestions against the actual code during the meta-review. Flag where you feel uncertain due to limited visibility and note any assumptions you are making about the code.

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

Be specific. Reference section names or step numbers from the plan. Don't soften your criticism — the goal is to improve the plan, not to be polite about it.

---

## 2. Project Overview

### What is PrismataAI?

PrismataAI is a C++ game engine and AI for **Prismata**, a turn-based, perfect-information strategy card game by Lunarch Studios (game is live, playable at prismata.net). The project includes:

- A C++ engine simulating game states with AI players (Alpha-Beta search, UCT/MCTS)
- A neural network evaluation system (ResNet, 1785 input features, trained via self-play)
- A Python training pipeline (PyTorch)
- A suite of Python tools for game analysis, live commentary, and community knowledge extraction

### Current Stage

The project is **mature and actively developed** by a solo developer. The AI has reached 45.3% win rate vs the game's hardest built-in AI (OriginalHardestAI) using self-play training with 305K games. Key infrastructure is production-tested: cloud training (AWS/GCP), self-play data generation (722K games, 178 GB), and a persistent monitoring system (TheWatcher).

### What This Plan Is About

The plan proposes building an **automated post-game commentary pipeline**: given a Prismata replay code, produce multi-message Discord-ready commentary analyzing the game. This pivots from the existing live commentary system (which generates 1-2 sentences per turn during live games) to a more thorough offline analysis.

### Constraints

- **Solo developer** — implementation, testing, and iteration are all one person
- **Cost-conscious** — API costs matter; the developer experienced a $805 AWS bill shock. Haiku ($1/MTok in, $5/MTok out) preferred over Sonnet ($3/$15) where quality permits
- **Prismata community is small** — commentary will be posted to Discord channels with maybe dozens of active readers. Quality matters more than scale.
- **No timeline pressure** — this is a passion project, not a product with deadlines

---

## 3. Architecture & Tech Stack

### Languages & Frameworks

| Component | Technology | Purpose |
|---|---|---|
| Game engine & AI | C++ (x86, Visual Studio 2022) | Game simulation, neural net inference, AI search |
| Training pipeline | Python + PyTorch | Neural network training from self-play data |
| Tools & commentary | Python (stdlib + `anthropic` SDK) | Replay analysis, commentary generation, Discord knowledge extraction |
| Dashboard | Node.js + Express | Fleet monitoring web UI |

### High-Level Architecture for Commentary

```
                     Existing (working)                    Proposed (this plan)
                     ==================                    ====================

Replay Code ──→ [S3 fetch + cache] ──→ Replay JSON
                                            │
                                            ├──→ [C++ --eval]    → Per-turn neural eval
                                            ├──→ [C++ --analyze] → AI comparison per turn
                                            ├──→ [Python ResourceTracker] → Validated buys
                                            │
                                            ▼
                                    Structured Game Data ──────→ [NEW: Phase 1 JSON output]
                                                                        │
                                                                        ▼
                                                              [NEW: Stage 1 — Analysis]
                                                               Claude Haiku structured output
                                                               Identify phases, turning points
                                                                        │
                                                                        ▼
                                                              [NEW: Stage 2 — Narrative]
                                                               Claude Haiku free-form
                                                               Few-shot examples + analysis
                                                                        │
                                                                        ▼
                                                              Discord-ready commentary
                                                              (== MESSAGE N == format)
```

### Key Architectural Decisions Already Made

1. **Two-stage LLM pipeline** (analysis then narrative) rather than single-pass — justified by WSC Sports production system research and academic survey findings
2. **Claude Haiku 4.5** as default model — cost optimization; Sonnet available as upgrade flag
3. **Structured output for analysis, free-form for narrative** — JSON guarantees parseable intermediates; free prose avoids mechanical-sounding commentary
4. **Extends existing tools** rather than rewriting — `generate_commentary_data.py` already handles replay fetch, resource validation, and C++ eval

### External Services

| Service | Purpose | Cost |
|---|---|---|
| Anthropic Claude API | LLM generation (analysis + narrative) | ~$0.02/game sync, ~$0.01/game batch |
| S3 (Lunarch-hosted) | Replay JSON storage | Free (public read) |
| C++ engine (local) | Neural evaluation, AI comparison | Free (local compute) |

---

## 4. Codebase Map

### Directory Structure (relevant subset)

```
PrismataAI/
├── bin/
│   ├── asset/config/
│   │   ├── config.txt               # AI player definitions, tournament configs
│   │   ├── cardLibrary.jso           # Master unit definitions (105+ units)
│   │   └── neural_weights.bin        # Neural network weights (8.8 MB)
│   ├── commentary/                   # Output: generated commentary files (7 existing)
│   │   ├── commentary_FxCfR-K49T+.txt
│   │   ├── commentary_WjhmP-WWdXx.txt
│   │   └── commentary_uP8mG-tr75d.txt (+ iterations)
│   ├── replays_test/                 # Cached replay JSONs from S3
│   ├── Prismata_Testing_d.exe        # Debug build with --eval / --analyze modes
│   └── prismata_capture_codes.txt    # Sniffer-captured replay codes (TSV)
├── tools/
│   ├── generate_commentary_data.py   # [690 lines] Replay analysis: S3 fetch, resource validation, C++ eval
│   ├── prismata_commentator.py       # [370 lines] Live commentary engine (sniffer + Haiku)
│   ├── prismata_game_state.py        # [175 lines] Shared game state model (TurnRecord, GameContext)
│   ├── prismata_sniffer.py           # TCP proxy for Prismata protocol (hook framework)
│   ├── commentary_prompt.md          # [67 lines] Condensed knowledge base (~2,400 tokens)
│   ├── discord_knowledge_extractor.py # [2,634 lines] Batch API extraction pipeline (proven pattern)
│   └── (14 other Python tools)
├── docs/
│   ├── commentary-knowledge/         # Full knowledge base (5,090 lines across 7 category files)
│   │   ├── 01-game-fundamentals.md   # [433 lines] Resources, combat, phases
│   │   ├── 02-base-set-units.md      # [205 lines] 11 core units
│   │   ├── 03-advanced-units.md      # [1,266 lines] 80+ unit profiles & tier rankings
│   │   ├── 04-strategy-concepts.md   # [1,203 lines] Standard Style, chill theory, set reading
│   │   ├── 05-openings-builds.md     # [511 lines] Build notation, P1/P2 openers
│   │   ├── 06-meta-expert.md         # [744 lines] Tournament players, Masterbot analysis
│   │   ├── 07-commentary-phrases.md  # [728 lines] Glossary + dramatic templates
│   │   └── sources.md               # 400+ source attributions
│   ├── plans/
│   │   ├── commentary-generation-instructions.md  # [233 lines] Manual workflow + format spec
│   │   └── 2026-02-22-postgame-commentary-pipeline-plan.md  # THE PLAN
│   └── prismata-strategy-guide.md    # 17-chapter human-readable strategy guide
├── source/                           # C++ engine source
│   ├── ai/                           # AI players, search, neural net
│   ├── engine/                       # Game state, card types, actions
│   └── testing/                      # Tournament runner, benchmarks (--eval, --analyze)
└── training/                         # Python training pipeline (PyTorch)
```

### Key Files Directly Involved in the Plan

**Will be modified:**
- `tools/generate_commentary_data.py` (690 lines) — Add `--json-output` flag for structured data extraction

**Will be created:**
- `tools/generate_postgame_commentary.py` — New main pipeline script
- `tools/commentary_schema.json` — JSON schema for structured game data
- `tools/prompts/analysis_system.md` — Analysis stage system prompt
- `tools/prompts/narrative_system.md` — Narrative stage system prompt
- `tools/prompts/narrative_user_template.md` — User message template

**Read-only dependencies:**
- `tools/commentary_prompt.md` — Loaded as part of LLM system prompts
- `docs/commentary-knowledge/*.md` — Unit knowledge looked up per game
- `bin/commentary/*.txt` — Used as few-shot examples
- `docs/plans/commentary-generation-instructions.md` — Tone/format specification

**Pattern to follow (not modified):**
- `tools/discord_knowledge_extractor.py` — Proven Batch API pattern (submission, polling, checkpointing)

---

## 5. Relevant Existing Patterns & Conventions

### Python Tooling Conventions

- All tools in `tools/` are standalone CLI scripts with `argparse`
- No shared requirements.txt for tools — each imports only stdlib + `anthropic` SDK
- File paths are relative to project root, resolved via `os.path.dirname(__file__)`
- Replay codes have special character encoding: `+` → `_PLUS_`, `@` → `_AT_` for filenames
- Output to stderr for progress/debug, stdout for primary output
- UTF-8 throughout (Windows `cp1252` is a known gotcha — use `PYTHONIOENCODING=utf-8`)

### Claude API Usage Patterns (from existing code)

**Live commentator** (`prismata_commentator.py`):
```python
# Synchronous call with prompt caching
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=120,
    system=[
        {"type": "text", "text": knowledge_base, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": per_game_set_info},
    ],
    messages=[{"role": "user", "content": user_content}],
)
```

**Discord extractor** (`discord_knowledge_extractor.py`):
```python
# Batch API submission
batch = client.messages.batches.create(requests=[
    {"custom_id": chunk_id, "params": {"model": model, "max_tokens": 8192, "messages": [...]}}
    for chunk_id in chunks
])

# Polling loop
while batch.processing_status == "in_progress":
    time.sleep(60)
    batch = client.messages.batches.retrieve(batch_id)

# Results collection
for result in client.messages.batches.results(batch_id):
    text = result.result.message.content[0].text
```

### Error Handling

- Live commentary: silent fail (log error, skip turn, game continues)
- Batch extraction: 3 retries with exponential backoff (2, 4, 8s), then skip chunk
- C++ subprocess: timeout (300s for --analyze, 60s for --eval), check return code

### Testing

- No automated test suite for Python tools
- Manual testing against known replay codes (standard test: `FxCfR-K49T+`)
- Quality verified by human review of output

### Configuration & Auth

- `ANTHROPIC_API_KEY` from environment variable (no config files)
- No other secrets required — replay S3 is public
- C++ exe path derived from relative directory structure

---

## 6. Current State & Known Issues

### What Works Today

1. **Data extraction** (`generate_commentary_data.py`) — Fetches replays from S3, runs C++ neural eval per turn, runs AI comparison search, validates buys via pure-Python resource tracker. All three modes working (`--analyze`, `--eval-only`, `--validate`).

2. **Live commentary** (`prismata_commentator.py`) — Per-turn Haiku commentary injected as in-game chat during live games via sniffer proxy. Tested Feb 20, community reception positive.

3. **Knowledge base** (`docs/commentary-knowledge/`) — 5,090 lines across 7 categories, extracted from 400+ sources (YouTube transcripts, blogs, Reddit, Discord, wiki). Comprehensive coverage of strategy, units, and commentary language.

4. **Manual post-game commentary** — 3 unique replays commentated by hand using the data extraction tool + Claude. Quality is excellent (see Section 7 for examples). This is the quality baseline the automated pipeline must match.

### Known Issues / Technical Debt

- **Resource validation is not 100% accurate** — The `ResourceTracker` class handles most cases but may miss edge cases around `buySac` (units that require sacrificing another unit to purchase) and complex ability interactions. The stepper reliability metric (>80% click application rate) flags unreliable games.

- **C++ --analyze timeout** — The 300s timeout for `--analyze` mode can be hit on very long games (40+ turns). The `--eval-only` mode (60s timeout) is a reliable fallback.

- **Click counting ≠ buy counting** — `card clicked` events in the replay don't guarantee successful purchases (sold-out cards, insufficient resources). The plan addresses this by using resource-validated buys as ground truth.

- **x86 OOM at high think times** — The C++ exe is x86 (4GB address space). Think times above 200ms can OOM. Default is 50ms, which is sufficient for eval comparison.

- **No automated quality testing** — Commentary quality is currently assessed by human review only. The plan proposes a programmatic quality rubric (Phase 6) but it covers factual accuracy, not prose quality.

### Recent Changes

- Feb 22: Discord knowledge extraction completed (1,426 insights from 67 chunks)
- Feb 20: Live commentator Phase 1 complete and tested
- Feb 20: Post-game commentary manual workflow established (3 replays)
- Feb 20: Sniffer live game state tracking and chat injection working

---

## 7. Context Specific to the Plan

### Existing Commentary Examples (Quality Baseline)

The plan must produce commentary matching or exceeding these manually-written examples. All three were written using output from `generate_commentary_data.py` (resource-validated buys + neural eval) combined with manual Claude prompting.

**Example 1: "Giant Killer"** (`FxCfR-K49T+`)
Surfinite (1856) vs Kolento (2222) — 366-point upset, 15 rounds. Commentary is 46 lines, covers opening through verdict, identifies 3 key decisions. Written in analytical esports commentator style with specific turn references and strategic reasoning.

Key excerpt:
> *"T8 is Surfinite's power turn: Conduit, three Engineers, three Galvani Drones, and a Wall. Eight units in one turn — that's a full economic conversion into granularity plus Wall absorb."*

**Example 2: "Protoplasm Is King"** (`WjhmP-WWdXx`)
Wonderboat (2298) vs Homeless (2228) — Master-tier match, 16 turns. Commentary uses `== MESSAGE N ==` Discord format (4 messages). Analyzes Protoplasm burst vs Blood Phage grind strategies. Includes time-pressure analysis.

Key excerpt:
> *"Both Master-tier veterans (Homeless has 31,884 rated games). Wonderboat identified Protoplasm as dominant within 30 seconds and never deviated."*

**Example 3: "xYotsu vs Hey"** (`uP8mG-tr75d`)
39-turn grind. Commentary covers Apollo mirror, Mega Drone economy advantage, time pressure analysis. Most detailed of the three at 64 lines across 4 Discord messages.

### The Pivot from Live to Post-Game

The live commentary system was designed for real-time constraints:
- 40-120 tokens per turn (1-2 sentences)
- No future context (can't reference upcoming turns)
- Condensed 67-line knowledge base (~2,400 tokens)
- Single Haiku call per turn, no multi-pass

The post-game pipeline removes all these constraints:
- Full game context (can reference any turn)
- Multi-thousand token output
- Full 5,090-line knowledge base available
- Multiple LLM calls with different purposes
- Few-shot examples from existing high-quality commentaries

### Replay Data Available

| Source | Count | Description |
|---|---|---|
| Expert replays | 31,506 | 2000+ rating, from prismata-stats API |
| Sniffer captures | 25+ | TSV file, auto-appended during live play |
| Discord codes | 93 | Extracted from strategy discussions |
| Community (Reddit + tournament) | 4,586 | Various sources |

All replays stored as gzipped JSON on S3. Fetching is free (public bucket). Each replay contains complete game data: card definitions, player actions, per-turn clicks, player info, ratings.

### Batch API Pattern (Proven)

The `discord_knowledge_extractor.py` is the project's most sophisticated API integration. It handles:
- Batch submission (`messages.batches.create`)
- Polling with 60s intervals
- Checkpoint/resume via JSON file
- Cost tracking with pricing constants
- Schema validation on responses
- Retry with exponential backoff for sync mode

The post-game commentary batch mode (Phase 5) should follow this exact pattern.

### C++ Engine Capabilities

The C++ exe provides two analysis modes accessible via subprocess:

**`--eval replay.json`** — Fast neural evaluation per turn (~10s). Outputs JSON with per-turn eval percentages, biggest eval swing, and mistake detection. No AI search — just the neural net's position assessment.

**`--analyze replay.json`** — Full analysis (~30-60s). Adds AI-recommended buys per turn, agreement rate, and validated click application. More data but slower and can timeout on long games.

Both output clean JSON to stdout with stderr suppressed.

---

## 8. Scope Boundaries

### Explicitly Out of Scope

- **TTS audio generation** — Phase 2 of the live commentary plan. Not relevant to text-based post-game commentary.
- **OBS/streaming integration** — Phase 3 of the live commentary plan. Post-game commentary targets Discord, not live streams.
- **Live commentary changes** — The existing live commentator is not modified. It remains a separate system.
- **Automatic Discord posting** — The pipeline produces text files. Manual copy-paste to Discord is acceptable for now.
- **Commentary for non-expert audiences** — The target audience understands Prismata basics. Beginner-friendly explanations are out of scope.
- **Multi-language support** — English only.

### Fixed / Non-Negotiable

- **Claude API** — The LLM provider is Anthropic Claude. No OpenAI, no local LLMs. The anthropic SDK is already installed and used throughout.
- **Haiku as default model** — Cost sensitivity means Haiku is the default. Sonnet is opt-in via flag.
- **`== MESSAGE N ==` output format** — Matches the existing manual commentary format and is designed for Discord's 2000-char message limit.
- **Replay S3 format** — The replay JSON structure is owned by Lunarch Studios and cannot be changed. We consume it as-is.
- **C++ exe is x86 only** — No 64-bit build. The 4GB address limit and 50ms think-time default are constraints we work within.

### Accepted Trade-offs

- **Two LLM calls per game** — Adds ~5s latency and doubles API cost vs single-pass, but research strongly supports quality improvement.
- **Haiku may produce worse prose than Sonnet** — Accepted for cost reasons. The `--model sonnet` flag is the escape hatch.
- **No automated prose quality testing** — Factual accuracy can be checked programmatically, but narrative quality requires human review. This is acceptable given the small community.
- **Few-shot examples add ~3-4K tokens per call** — Increases cost by ~30% but dramatically improves style matching based on research.

---

## 9. Success Criteria

### Must-Have (Plan is successful if all of these are met)

1. **Single command** produces complete commentary from a replay code: `python tools/generate_postgame_commentary.py "CODE"`
2. **Factual accuracy >95%** — All referenced turn numbers exist, all unit names are in the deck, winner is correctly identified
3. **Quality parity** with manually-written examples — Subjective, assessed by the developer comparing automated vs manual output on the same 3 test replays
4. **Cost under $0.03/game** (Haiku sync mode) — Based on estimated ~10K input + ~5K output tokens across two stages
5. **Works without C++ exe** — `--validate-only` mode produces commentary using only Python resource validation (no neural eval data, but still usable)

### Nice-to-Have

6. **Batch mode** processes 10+ games at 50% cost discount
7. **Intermediate caching** — Re-running narrative stage without re-running C++ analysis
8. **Quality rubric** catches bad commentary automatically (factual checks, structure validation)
9. **Commentary style options** — at least `analytical` and one alternative

### Measurable Outcomes

- Time: <60s per game (sync), <30 min for 100-game batch
- Cost: ~$0.02/game sync, ~$0.01/game batch (Haiku 4.5)
- Output: 4-8 Discord messages per game, each <2000 chars
- Factual: Zero invented turn numbers, zero non-deck unit names

---

## 10. Key Questions for Reviewers

1. **Is the two-stage LLM pipeline (analysis → narrative) justified?** The plan cites research from WSC Sports and academic surveys. But for a 15-turn game producing 4-5 Discord messages, could a single well-prompted call with few-shot examples achieve comparable quality at half the cost? Under what circumstances would one stage suffice vs require two?

2. **Is the unit knowledge lookup strategy sound?** The plan proposes extracting per-unit strategic notes from the 1,266-line advanced units file and injecting them into the LLM context. Is this the right granularity? Should we include more context (opening theory for units in the set, known synergies) or less (just stats from the card definitions)?

3. **Are the few-shot examples a good approach for style control?** The plan uses 1-2 of the 3 existing manually-written commentaries as in-context examples. At ~3-4K tokens each, this is a significant portion of the input. Are there better approaches to style transfer? Should we extract a "style guide" from the examples instead?

4. **Is the programmatic verification pass (Phase 2c) sufficient for hallucination prevention?** The plan checks turn numbers, unit names, and eval values against game data. What other factual claims might the LLM hallucinate that this wouldn't catch? Should we consider a second LLM call specifically for verification?

5. **What's the right failure mode for long/unusual games?** Games range from 8 turns (rushes) to 40+ turns (grinds). Should the pipeline handle these differently (e.g., different prompts for short vs long games, or abort with a warning if the game is too complex)?

---

## 11. Glossary / Domain Terms

| Term | Definition |
|---|---|
| **Prismata** | Turn-based, perfect-information strategy card game by Lunarch Studios. Two players buy units from a shared pool. |
| **Replay code** | Alphanumeric identifier (e.g., `FxCfR-K49T+`) that uniquely identifies a game. Used to fetch replay data from S3. |
| **Random set** | 5-11 units randomly selected for each game, in addition to the 11 base-set units always available. |
| **Base set** | The 11 units available in every game: Drone, Engineer, Conduit, Blastforge, Animus, Tarsier, Rhino, Wall, Steelsplitter, Gauss Cannon, Forcefield. |
| **mergedDeck** | JSON array in the replay data containing all card definitions for a game (base set + random set), with costs, stats, and abilities. |
| **commandList** | JSON array containing every player click/action in chronological order. |
| **clicksPerTurn** | Array that slices `commandList` into per-turn segments. |
| **Neural eval** | The C++ neural network's assessment of a position. Output as a percentage (50% = equal, >50% = P1 favored). |
| **--analyze mode** | C++ engine mode that replays a game, running AI search at each turn to produce recommended moves and eval scores. |
| **--eval mode** | Faster C++ mode that only runs neural net evaluation (no search). |
| **ResourceTracker** | Pure-Python class that simulates the game economy turn-by-turn to validate which card purchases actually succeeded. |
| **Absorb** | Non-lethal damage on the biggest non-fragile blocker; the blocker heals next turn. A key strategic concept. |
| **Breach** | When attack exceeds total defense — the attacker picks which enemy units die. Usually game-ending. |
| **Chill** | Prevents a unit from blocking. Chill >= unit HP = unit is completely frozen for the turn. |
| **Prompt** | Zero build time — a unit can block the same turn it's purchased. Critical for defense timing. |
| **Fragile** | Unit does not heal after taking damage. One hit and it's gone. |
| **Tech** | Resource-producing buildings (Conduit for green, Blastforge for blue, Animus for red). |
| **Changing gears** | The transition from buying economy (Drones) to buying attackers/defense. Timing this is the core skill. |
| **Float** | Unspent resources at end of turn. Floating 1-2 gold is normal; 3+ is wasteful. |
| **Granularity** | Having enough small blockers to efficiently match any incoming damage amount. |
| **Set reading** | Analyzing the random units to determine optimal strategy before the game starts. |
| **OriginalHardestAI** | The game's built-in hardest AI. Used as the evaluation baseline — our neural net achieves 45.3% WR against it. |
| **Haiku 4.5** | Claude claude-haiku-4-5-20251001. Anthropic's fastest/cheapest model. $1/MTok input, $5/MTok output. |
| **Sonnet 4.5** | Claude claude-sonnet-4-5-20241022. Higher quality, 3x cost. Used as opt-in upgrade. |
| **Batch API** | Anthropic's asynchronous processing API. 50% cost discount, results within 24h (usually <1h). |
| **Prompt caching** | Anthropic feature where repeated system prompt prefixes are cached, reducing input cost by 90% on cache hits. |
| **Structured output** | Claude feature forcing responses into a JSON schema. Guarantees parseable output but can constrain reasoning. |
| **Discord message limit** | 2000 characters per message. Commentary must be split into multiple messages. |
| **TheWatcher** | Persistent monitor script (PowerShell, Task Scheduler) managing cloud compute fleet. Not directly relevant to this plan but mentioned in project docs. |
| **Self-play** | AI vs AI game generation for training data. 722K games generated so far. |
| **sniffer** | TCP proxy (`prismata_sniffer.py`) that intercepts Prismata network traffic. Used by the live commentator. Not needed for post-game commentary. |
