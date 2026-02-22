# Commentary Knowledge Base

Knowledge base for the AI Prismata game commentator system. Extracted from official sources, community guides, wiki pages, developer blogs, and forum posts.

See: [Live Commentator Plan](../plans/2026-02-20-live-commentator-plan.md) | [Extraction Plan](../plans/2026-02-20-commentary-knowledge-extraction.md)

## Files

| File | Category | Lines | Description |
|------|----------|-------|-------------|
| [01-game-fundamentals.md](01-game-fundamentals.md) | Game Fundamentals | 402 | Resources, turn structure, combat, unit mechanics, starting positions, game phases, threat types, player asymmetry, branching factor, game complexity, tech tree philosophy, developer design insights |
| [02-base-set-units.md](02-base-set-units.md) | Base Set Units | 181 | All 11 units in every game — costs, stats, strategy, economic analysis, developer design commentary, resource spending rules, top player assessments |
| [03-advanced-units.md](03-advanced-units.md) | Advanced Units | 728 | Tier rankings, absorber rankings, big red units, alternate drones, efficiency analysis, rush units, noticeable units, balance history, legendary purchase frequency, unit profiles (50+ units), developer case studies, top player assessments |
| [04-strategy-concepts.md](04-strategy-concepts.md) | Strategy Concepts | 911 | Standard Style, chill theory (6 parts), breachproof (3 parts), breach theory, set reading, granularity, gambit theory, reaction theory, rush timing, endgame theory, economy sizing, SDR, minimax defense, tempo, disruption tactics, beginner pitfalls |
| [05-openings-builds.md](05-openings-builds.md) | Openings & Builds | 384 | Build notation, P1/P2 openings, advanced unit openings, secret opening book, transpositions, Tia Thurnax theory, Shadowfang rush, Cluster Bolt counter, Arka Sodara dynamics |
| [06-meta-expert.md](06-meta-expert.md) | Meta & Expert | 552 | Dev history, community voices, 16+ set reading examples, tournaments, Masterbot exploitation, autowin theory, player statistics, Msven 9-part framework, argeiphontes teaching content, developer insights |
| [07-commentary-phrases.md](07-commentary-phrases.md) | Commentary Phrases | 440 | Glossary, jargon, dramatic moments, templates, quotables, disruption/finesse/investment/supply/reactive play commentary templates, expert quotables |
| [sources.md](sources.md) | Source Tracking | 260+ sources | 148 YouTube transcripts, 45 blog articles, 629 Reddit posts, 27 prismatalibrary.blog articles, 12 Foxclear wiki guides, 24 Wayback recoveries, Twitch VODs |

## Usage

These files are designed to be loaded into the AI commentator's system prompt (Tier 1/2/3 knowledge hierarchy — see Live Commentator Plan). The commentary phrases file (07) provides ready-made language patterns. The strategy files (04, 05) provide analytical frameworks. The unit files (02, 03) provide factual reference data.

## Source Attribution

Every entry includes a `> Source:` blockquote identifying where the information came from. This enables:
- Verification against original sources
- Re-extraction with different focus (e.g., writing a human-readable guide)
- Tracking which sources contributed to which categories

## Extraction Date

February 20, 2026. Based on 12+ source categories (~3,600 lines across 7 KB files):

**Text sources (Passes 1-3):**
- 27 articles from prismatalibrary.blog (307th/Arkanishu)
- 24 archived pages from Wayback Machine (Yujiri, RuinedShadows, Strategy Guide wiki)
- 12 wiki strategy guide files (Foxclear — 7 advanced + 5 beginner)
- 32 items from user-provided strategy content chunks
- 9 recovered source files (Yujiri analyses 2-9 + Punf)
- Existing project files (`docs/wiki/PRISMATA_REFERENCE.md`, 448-page wiki dump)

**Multimedia sources (Pass 4):**
- 148 YouTube video transcripts (auto-generated): Msven (17), argeiphontes (40), amalloy (41), Wonderboat (5), Lunarch Studios (44), Jean Ventura (1)
- 45 Lunarch Studios blog articles (recovered via Wayback Machine CDX API)
- 629 Reddit r/Prismata posts (retrieved via PullPush API)
- Twitch VODs: Apooche league commentary (in progress — 7 videos)


### Discord Extractions
- `discord/` -- Extracted insights from Prismata Discord (mirror directory, not yet promoted)
  - Requires manual review and promotion to main KB files
