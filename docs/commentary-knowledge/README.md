# Commentary Knowledge Base

Knowledge base for the AI Prismata game commentator system. Extracted from official sources, community guides, wiki pages, developer blogs, and forum posts.

See: [Live Commentator Plan](../plans/2026-02-20-live-commentator-plan.md) | [Extraction Plan](../plans/2026-02-20-commentary-knowledge-extraction.md)

## Files

| File | Category | Entries | Description |
|------|----------|---------|-------------|
| [01-game-fundamentals.md](01-game-fundamentals.md) | Game Fundamentals | 12 sections | Resources, turn structure, combat, unit mechanics, starting positions, game phases (7-phase), threat types, player asymmetry, branching factor |
| [02-base-set-units.md](02-base-set-units.md) | Base Set Units | 11 units | All units present in every game — costs, stats, strategy, economic analysis |
| [03-advanced-units.md](03-advanced-units.md) | Advanced Units | ~140 entries | Tier rankings, absorber rankings (307th), big red units, alternate drones, efficiency analysis, rush units, noticeable units (Foxclear), tactical patterns, balance history |
| [04-strategy-concepts.md](04-strategy-concepts.md) | Strategy Concepts | 55+ sections | Standard Style, chill theory (6 parts), breachproof (3 parts), breach theory, set reading, granularity & abuse, gambit theory, reaction theory, rush timing, endgame theory, economy sizing |
| [05-openings-builds.md](05-openings-builds.md) | Openings & Builds | ~50 openings | Build notation, P1/P2 openings (Yujiri + 307th + Foxclear), advanced unit openings, secret opening book, transpositions |
| [06-meta-expert.md](06-meta-expert.md) | Meta & Expert | 30+ sections | Dev history, community voices, 8+ set reading examples, tournaments, Masterbot exploitation, autowin theory, player statistics |
| [07-commentary-phrases.md](07-commentary-phrases.md) | Commentary Phrases | 80+ entries | Glossary, jargon, dramatic moments, templates, quotables, gambit/granularity/freeze/reaction commentary |
| [sources.md](sources.md) | Source Tracking | 115+ sources | 27 prismatalibrary.blog articles, 12 Foxclear wiki guides, 32 chunk items, Wayback recoveries, processing notes |

## Usage

These files are designed to be loaded into the AI commentator's system prompt (Tier 1/2/3 knowledge hierarchy — see Live Commentator Plan). The commentary phrases file (07) provides ready-made language patterns. The strategy files (04, 05) provide analytical frameworks. The unit files (02, 03) provide factual reference data.

## Source Attribution

Every entry includes a `> Source:` blockquote identifying where the information came from. This enables:
- Verification against original sources
- Re-extraction with different focus (e.g., writing a human-readable guide)
- Tracking which sources contributed to which categories

## Extraction Date

February 20, 2026. Based on 6 source categories:
- 27 articles from prismatalibrary.blog (307th/Arkanishu)
- 15 archived pages from Wayback Machine (Yujiri, RuinedShadows)
- 12 wiki strategy guide files (Foxclear — 7 advanced + 5 beginner)
- 32 items from user-provided strategy content chunks (developer analysis, community insights)
- 4 batches from initial web research
- Existing project files (`docs/wiki/PRISMATA_REFERENCE.md`, `docs/wiki/` dump of 448 pages)
